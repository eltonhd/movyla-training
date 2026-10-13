from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import date, timedelta
from calendar import monthrange
import sqlite3
from decimal import Decimal, InvalidOperation
from planos import criar_tabela_planos
import os


# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)

UPLOAD_FOLDER = os.path.join(
    "static",
    "uploads"
)

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}

MAX_FILE_SIZE = 5 * 1024 * 1024

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# ============================================================
# BANCO DE DADOS
# ============================================================

def conectar():

    caminho_banco = os.environ.get("DATABASE_PATH", "meutreino.db")

    conn = sqlite3.connect(caminho_banco)
    conn.row_factory = sqlite3.Row

    return conn


# ============================================================
# LOGIN OBRIGATÓRIO
# ============================================================

def login_obrigatorio(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if "usuario_id" not in session:
            return redirect("/login")

        return func(*args, **kwargs)

    return wrapper


# ============================================================
# PERMISSÕES
# ============================================================

def usuario_e_owner():

    return session.get("tipo") == "master"


def usuario_e_personal():

    return session.get("tipo") == "personal"


def usuario_e_gestor():

    return session.get("tipo") in (
        "master",
        "personal"
    )


# ============================================================
# EXTENSÃO PERMITIDA
# ============================================================

def extensao_permitida(nome):

    return (
        "." in nome
        and nome.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_EXTENSIONS
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        usuario = request.form.get(
            "usuario"
        )

        senha = request.form.get(
            "senha"
        )

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM usuarios
            WHERE usuario = ?
              AND ativo = 1
        """, (
            usuario,
        ))

        usuario_db = cursor.fetchone()

        conn.close()

        if (
            usuario_db
            and check_password_hash(
                usuario_db["senha"],
                senha
            )
        ):

            session.clear()

            session["usuario_id"] = usuario_db["id"]
            session["nome"] = usuario_db["nome"]
            session["usuario"] = usuario_db["usuario"]
            session["tipo"] = usuario_db["tipo"]
            session["foto"] = usuario_db["foto"]

            return redirect("/")

        return render_template(
            "login.html",
            erro="Usuário ou senha inválidos."
        )

    return render_template(
        "login.html"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# ============================================================
# INÍCIO / DASHBOARD
# ============================================================

@app.route("/")
@login_obrigatorio
def inicio():

    conn = conectar()
    cursor = conn.cursor()

    total_alunos = 0
    total_treinos = 0
    total_exercicios = 0
    total_personais = 0
    alertas_financeiros = []
    aviso_assinatura_personal = None
    indicadores_assinaturas = {
        "pagas": 0,
        "testes": 0,
        "isentas": 0,
        "sem_assinatura": 0,
        "vencidas": 0,
        "receita_prevista": 0.0,
    }

    # ========================================================
    # OWNER
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT COUNT(*)
            FROM usuarios
            WHERE tipo = 'aluno'
              AND ativo = 1
        """)

        total_alunos = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM usuarios
            WHERE tipo = 'personal'
              AND ativo = 1
        """)

        total_personais = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM treinos
        """)

        total_treinos = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM exercicios
        """)

        total_exercicios = cursor.fetchone()[0]

        # Indicadores calculados no servidor e limitados aos profissionais
        # deste administrador, sem incluir parceiros isentos na receita.
        cursor.execute("""
            SELECT
                u.id,
                a.tipo_assinatura,
                a.isento,
                a.valor_mensal,
                a.proximo_vencimento
            FROM usuarios u
            LEFT JOIN assinaturas_personais a ON a.personal_id = u.id
            WHERE u.tipo = 'personal'
              AND u.ativo = 1
              AND u.responsavel_id = ?
        """, (session["usuario_id"],))

        hoje = date.today()
        for linha in cursor.fetchall():
            if linha["tipo_assinatura"] is None:
                indicadores_assinaturas["sem_assinatura"] += 1
                continue
            if linha["isento"] or linha["tipo_assinatura"] == "isenta":
                indicadores_assinaturas["isentas"] += 1
                continue
            vencimento = None
            try:
                if linha["proximo_vencimento"]:
                    vencimento = date.fromisoformat(linha["proximo_vencimento"])
            except (TypeError, ValueError):
                pass
            if vencimento is not None and vencimento < hoje:
                indicadores_assinaturas["vencidas"] += 1
            if linha["tipo_assinatura"] == "teste":
                indicadores_assinaturas["testes"] += 1
            elif linha["tipo_assinatura"] == "paga":
                indicadores_assinaturas["pagas"] += 1
                if vencimento is not None and vencimento >= hoje:
                    indicadores_assinaturas["receita_prevista"] += max(
                        0, linha["valor_mensal"] or 0
                    )

        # ====================================================
        # ALERTAS FINANCEIROS DO ADMINISTRADOR
        # ====================================================

        cursor.execute("""
            SELECT
                u.id AS personal_id,
                u.nome AS personal_nome,
                a.valor_mensal,
                a.proximo_vencimento,
                COALESCE(a.tipo_assinatura, 'paga') AS tipo_assinatura,
                CASE
                    WHEN date(a.proximo_vencimento) < date('now', 'localtime')
                    THEN 'vencida'
                    ELSE 'vence_amanha'
                END AS status
            FROM assinaturas_personais a
            JOIN usuarios u ON u.id = a.personal_id
            WHERE u.tipo = 'personal'
              AND u.ativo = 1
              AND u.responsavel_id = ?
              AND COALESCE(a.isento, 0) = 0
              AND COALESCE(a.tipo_assinatura, 'paga') IN ('paga', 'teste')
              AND (
                  date(a.proximo_vencimento) < date('now', 'localtime')
                  OR date(a.proximo_vencimento) = date('now', 'localtime', '+1 day')
              )
            ORDER BY a.proximo_vencimento ASC
        """, (session["usuario_id"],))

        alertas_financeiros = [
            dict(linha) for linha in cursor.fetchall()
        ]

    # ========================================================
    # PERSONAL
    # ========================================================

    elif usuario_e_personal():

        # ================================================
        # AVISO DE ASSINATURA DO PERSONAL
        # ================================================

        cursor.execute("""
            SELECT
                tipo_assinatura,
                proximo_vencimento,
                isento
            FROM assinaturas_personais
            WHERE personal_id = ?
        """, (session["usuario_id"],))

        assinatura_personal = cursor.fetchone()

        if assinatura_personal:

            tipo = assinatura_personal["tipo_assinatura"]
            vencimento = assinatura_personal["proximo_vencimento"]
            isento = assinatura_personal["isento"]

            if not isento and tipo in ("paga", "teste") and vencimento:

                # Datas antigas ou incompletas não devem derrubar o dashboard.
                try:
                    data_vencimento = date.fromisoformat(vencimento)
                except (TypeError, ValueError):
                    data_vencimento = None

                if data_vencimento is not None:
                    dias_restantes = (data_vencimento - date.today()).days

                    if dias_restantes <= 3:
                        aviso_assinatura_personal = {
                            "tipo": tipo,
                            "dias_restantes": dias_restantes,
                            "vencimento": data_vencimento.strftime("%d/%m/%Y")
                        }


        cursor.execute("""
            SELECT COUNT(*)
            FROM usuarios
            WHERE tipo = 'aluno'
              AND responsavel_id = ?
              AND ativo = 1
        """, (
            session["usuario_id"],
        ))

        total_alunos = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM treinos
            WHERE responsavel_id = ?
        """, (
            session["usuario_id"],
        ))

        total_treinos = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM exercicios
        """)

        total_exercicios = cursor.fetchone()[0]

    # ========================================================
    # ALUNO
    # ========================================================

    else:

        cursor.execute("""
            SELECT COUNT(*)
            FROM treino_alunos
            WHERE usuario_id = ?
        """, (
            session["usuario_id"],
        ))

        total_treinos = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        total_alunos=total_alunos,
        total_treinos=total_treinos,
        total_exercicios=total_exercicios,
        total_personais=total_personais,
        alertas_financeiros=alertas_financeiros,
        indicadores_assinaturas=indicadores_assinaturas,
        aviso_assinatura_personal=aviso_assinatura_personal
    )


# ============================================================
# FOTO DO PERFIL
# ============================================================

@app.route(
    "/perfil/foto",
    methods=["POST"]
)
@login_obrigatorio
def perfil_foto():

    arquivo = request.files.get(
        "foto"
    )

    if not arquivo:
        return redirect("/")

    if not arquivo.filename:
        return redirect("/")

    if not extensao_permitida(
        arquivo.filename
    ):
        return redirect("/")

    usuario_id = session["usuario_id"]

    extensao = arquivo.filename.rsplit(
        ".",
        1
    )[1].lower()

    nome_arquivo = (
        f"foto_{usuario_id}.{extensao}"
    )

    caminho = os.path.join(
        app.config["UPLOAD_FOLDER"],
        nome_arquivo
    )

    for ext in ALLOWED_EXTENSIONS:

        antigo = os.path.join(
            app.config["UPLOAD_FOLDER"],
            f"foto_{usuario_id}.{ext}"
        )

        if os.path.exists(antigo):

            try:
                os.remove(antigo)
            except:
                pass

    arquivo.save(caminho)

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET foto = ?
        WHERE id = ?
    """, (
        nome_arquivo,
        usuario_id
    ))

    conn.commit()
    conn.close()

    session["foto"] = nome_arquivo

    return redirect("/")


# ============================================================
# NOVO PERSONAL
# ============================================================

@app.route(
    "/personais/novo",
    methods=["GET", "POST"]
)
@login_obrigatorio
def personal_novo():

    if not usuario_e_owner():
        return redirect("/")

    if request.method == "POST":

        nome = request.form.get(
            "nome",
            ""
        ).strip()

        usuario = request.form.get(
            "usuario",
            ""
        ).strip()

        senha = request.form.get(
            "senha",
            ""
        ).strip()

        if not nome or not usuario or not senha:

            return render_template(
                "personal_novo.html",
                erro="Preencha todos os campos."
            )

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id
            FROM usuarios
            WHERE usuario = ?
            """,
            (usuario,)
        )

        if cursor.fetchone():

            conn.close()

            return render_template(
                "personal_novo.html",
                erro="Este usuário já está cadastrado."
            )

        senha_hash = generate_password_hash(
            senha
        )

        cursor.execute(
            """
            INSERT INTO usuarios
            (
                nome,
                usuario,
                senha,
                tipo,
                ativo,
                responsavel_id
            )
            VALUES (?, ?, ?, 'personal', 1, ?)
            """,
            (
                nome,
                usuario,
                senha_hash,
                session["usuario_id"]
            )
        )

        conn.commit()
        conn.close()

        return redirect("/personais")

    return render_template(
        "personal_novo.html"
    )


# ============================================================
# USUÁRIOS - OWNER
# ============================================================

@app.route("/usuarios")
@login_obrigatorio
def usuarios():

    if not usuario_e_owner():
        return redirect("/")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            u.id,
            u.nome,
            u.usuario,
            u.ativo,
            u.foto,
            COUNT(a.id) AS total_alunos
        FROM usuarios u

        LEFT JOIN usuarios a
            ON a.tipo = 'aluno'
            AND a.responsavel_id = u.id

        WHERE u.tipo = 'personal'
          AND u.responsavel_id = ?

        GROUP BY
            u.id,
            u.nome,
            u.usuario,
            u.ativo,
            u.foto

        ORDER BY u.nome
    """, (
        session["usuario_id"],
    ))

    personais = cursor.fetchall()

    conn.close()

    return render_template(
        "usuarios.html",
        personais=personais
    )


# ============================================================
# USUÁRIOS - ALUNOS DE UM PERSONAL
# ============================================================

@app.route("/usuarios/personal/<int:personal_id>")
@login_obrigatorio
def usuario_personal(personal_id):

    if not usuario_e_owner():
        return redirect("/")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            nome,
            usuario,
            ativo,
            foto
        FROM usuarios
        WHERE id = ?
          AND tipo = 'personal'
          AND responsavel_id = ?
    """, (
        personal_id,
        session["usuario_id"]
    ))

    personal = cursor.fetchone()

    if not personal:

        conn.close()

        return redirect("/usuarios")

    cursor.execute("""
        SELECT
            id,
            nome,
            usuario,
            ativo,
            foto
        FROM usuarios
        WHERE tipo = 'aluno'
          AND responsavel_id = ?
        ORDER BY nome
    """, (
        personal_id,
    ))

    alunos = cursor.fetchall()

    conn.close()

    return render_template(
        "usuario_personal.html",
        personal=personal,
        alunos=alunos
    )


# ============================================================
# LISTA DE PERSONAIS
# ============================================================

@app.route("/personais")
@login_obrigatorio
def personais():

    if not usuario_e_owner():
        return redirect("/")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            u.id,
            u.nome,
            u.usuario,
            u.ativo,
            u.foto,
            COUNT(a.id) AS total_alunos
        FROM usuarios u

        LEFT JOIN usuarios a
            ON a.tipo = 'aluno'
            AND a.responsavel_id = u.id

        WHERE u.tipo = 'personal'
          AND u.responsavel_id = ?

        GROUP BY
            u.id,
            u.nome,
            u.usuario,
            u.ativo,
            u.foto

        ORDER BY u.nome
    """, (
        session["usuario_id"],
    ))

    personais = cursor.fetchall()

    conn.close()

    return render_template(
        "personais.html",
        personais=personais
    )


# ============================================================
# ALUNOS
# ============================================================

@app.route("/alunos")
@login_obrigatorio
def alunos():

    if not usuario_e_gestor():
        return redirect("/")

    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # BUSCAR ALUNOS
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                ativo,
                foto,
                responsavel_id
            FROM usuarios
            WHERE tipo = 'aluno'
            ORDER BY nome
        """)

    else:

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                ativo,
                foto,
                responsavel_id
            FROM usuarios
            WHERE tipo = 'aluno'
              AND responsavel_id = ?
            ORDER BY nome
        """, (
            session["usuario_id"],
        ))

    alunos_db = cursor.fetchall()

    # ========================================================
    # BUSCAR TREINOS DE CADA ALUNO
    # ========================================================

    alunos = []

    for aluno in alunos_db:

        cursor.execute("""
            SELECT
                ta.id AS treino_aluno_id,
                ta.treino_id,
                ta.dia_semana,
                t.nome AS treino_nome
            FROM treino_alunos ta
            INNER JOIN treinos t
                ON t.id = ta.treino_id
            WHERE ta.usuario_id = ?
            ORDER BY
                CASE
                    WHEN ta.dia_semana IS NULL THEN 99
                    ELSE ta.dia_semana
                END,
                t.nome
        """, (
            aluno["id"],
        ))

        treinos = cursor.fetchall()

        aluno_dict = dict(aluno)

        aluno_dict["treinos"] = treinos

        alunos.append(aluno_dict)

    conn.close()

    return render_template(
        "alunos.html",
        alunos=alunos
    )

# ============================================================
# NOVO ALUNO
# ============================================================

@app.route(
    "/alunos/novo",
    methods=["GET", "POST"]
)
@login_obrigatorio
def aluno_novo():

    if not usuario_e_gestor():
        return redirect("/")

    if request.method == "POST":

        nome = request.form.get(
            "nome",
            ""
        ).strip()

        usuario = request.form.get(
            "usuario",
            ""
        ).strip()

        senha = request.form.get(
            "senha",
            ""
        ).strip()

        if not nome or not usuario or not senha:

            return render_template(
                "aluno_novo.html",
                erro="Preencha todos os campos."
            )

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id
            FROM usuarios
            WHERE usuario = ?
        """, (
            usuario,
        ))

        existente = cursor.fetchone()

        if existente:

            conn.close()

            return render_template(
                "aluno_novo.html",
                erro="Esse usuário já existe."
            )

        senha_hash = generate_password_hash(
            senha
        )

        responsavel_id = session["usuario_id"]

        cursor.execute("""
            INSERT INTO usuarios
            (
                nome,
                usuario,
                senha,
                tipo,
                ativo,
                responsavel_id
            )
            VALUES (?, ?, ?, 'aluno', 1, ?)
        """, (
            nome,
            usuario,
            senha_hash,
            responsavel_id
        ))

        conn.commit()
        conn.close()

        return redirect("/alunos")

    return render_template(
        "aluno_novo.html"
    )


# ============================================================
# TREINOS DE UM ALUNO ESPECÍFICO
# ============================================================

@app.route("/alunos/<int:aluno_id>/treinos")
@login_obrigatorio
def aluno_treinos(aluno_id):

    usuario_id = session["usuario_id"]

    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # LOCALIZAR ALUNO
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                ativo,
                foto,
                responsavel_id
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
        """, (
            aluno_id,
        ))

    elif usuario_e_personal():

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                ativo,
                foto,
                responsavel_id
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
              AND responsavel_id = ?
        """, (
            aluno_id,
            usuario_id
        ))

    else:

        if aluno_id != usuario_id:

            conn.close()

            return redirect("/")

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                ativo,
                foto,
                responsavel_id
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
        """, (
            aluno_id,
        ))

    aluno = cursor.fetchone()

    if not aluno:

        conn.close()

        return redirect("/alunos")

    # ========================================================
    # BUSCAR TREINOS ATRIBUÍDOS AO ALUNO
    # ========================================================

    cursor.execute("""
        SELECT
            t.id,
            t.nome,
            t.descricao,
            t.responsavel_id,
            ta.id AS treino_aluno_id,
            ta.dia_semana
        FROM treino_alunos ta

        INNER JOIN treinos t
            ON t.id = ta.treino_id

        WHERE ta.usuario_id = ?

        ORDER BY
            CASE
                WHEN ta.dia_semana IS NULL THEN 99
                ELSE ta.dia_semana
            END,
            t.nome
    """, (
        aluno_id,
    ))

    treinos_db = cursor.fetchall()

    conn.close()

    return render_template(
        "aluno_treinos.html",
        aluno=aluno,
        treinos=treinos_db
    )


# ============================================================
# ATRIBUIR TREINO A UM ALUNO
# ============================================================

@app.route(
    "/alunos/<int:aluno_id>/treinos/atribuir",
    methods=["GET", "POST"]
)
@login_obrigatorio
def atribuir_treino(aluno_id):

    usuario_id = session["usuario_id"]

    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # VERIFICAR ALUNO
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                ativo,
                foto
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
        """, (
            aluno_id,
        ))

    elif usuario_e_personal():

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                ativo,
                foto
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
              AND responsavel_id = ?
        """, (
            aluno_id,
            usuario_id
        ))

    else:

        conn.close()

        return redirect("/")

    aluno = cursor.fetchone()

    if not aluno:

        conn.close()

        return redirect("/alunos")

    # ========================================================
    # CARREGAR TREINOS DISPONÍVEIS
    # ========================================================

    def carregar_treinos():

        if usuario_e_owner():

            cursor.execute("""
                SELECT
                    id,
                    nome,
                    descricao
                FROM treinos
                ORDER BY nome
            """)

        else:

            cursor.execute("""
                SELECT
                    id,
                    nome,
                    descricao
                FROM treinos
                WHERE responsavel_id = ?
                ORDER BY nome
            """, (
                usuario_id,
            ))

        treinos_db = cursor.fetchall()

        treinos = []

        for treino in treinos_db:

            # =================================================
            # EXERCÍCIOS DO TREINO
            # =================================================

            cursor.execute("""
                SELECT
                    te.id,
                    te.exercicio_id,
                    te.ordem,
                    te.progressao,
                    te.incremento,
                    e.nome,
                    e.grupo_muscular,
                    e.equipamento,
                    e.video_url
                FROM treino_exercicios te

                INNER JOIN exercicios e
                    ON e.id = te.exercicio_id

                WHERE te.treino_id = ?

                ORDER BY
                    te.ordem,
                    te.id
            """, (
                treino["id"],
            ))

            exercicios_db = cursor.fetchall()

            exercicios = []

            for exercicio in exercicios_db:

                treino_exercicio_id = exercicio["id"]

                # =============================================
                # PRESCRIÇÃO BASE DO EXERCÍCIO
                # =============================================

                cursor.execute("""
                    SELECT
                        numero_serie,
                        repeticoes_prescritas
                    FROM treino_series
                    WHERE treino_exercicio_id = ?
                    ORDER BY numero_serie
                """, (
                    treino_exercicio_id,
                ))

                series_db = cursor.fetchall()

                # =============================================
                # GARANTIR QUE SERIES SEMPRE SEJA UMA LISTA
                # =============================================

                series = []

                for serie in series_db:

                    series.append({
                        "numero_serie": serie["numero_serie"],
                        "repeticoes_prescritas": serie[
                            "repeticoes_prescritas"
                        ]
                    })

                # =============================================
                # SE NÃO EXISTIR PRESCRIÇÃO BASE
                # =============================================

                if not series:

                    series = [
                        {
                            "numero_serie": 1,
                            "repeticoes_prescritas": 10
                        }
                    ]

                # =============================================
                # MONTAR EXERCÍCIO
                # =============================================

                exercicios.append({
                    "id": treino_exercicio_id,
                    "exercicio_id": exercicio["exercicio_id"],
                    "ordem": exercicio["ordem"],
                    "nome": exercicio["nome"],
                    "grupo_muscular": exercicio["grupo_muscular"],
                    "equipamento": exercicio["equipamento"],
                    "video_url": exercicio["video_url"],
                    "progressao": exercicio["progressao"],
                    "incremento": exercicio["incremento"],
                    "series": series
                })

            # ================================================
            # MONTAR TREINO
            # ================================================

            treino_dict = {
                "id": treino["id"],
                "nome": treino["nome"],
                "descricao": treino["descricao"],
                "exercicios": exercicios
            }

            treinos.append(
                treino_dict
            )

        return treinos

    # ========================================================
    # POST
    # ========================================================

    if request.method == "POST":

        treino_id = request.form.get(
            "treino_id",
            type=int
        )

        dia_semana = request.form.get(
            "dia_semana",
            type=int
        )

        erro = None

        # ====================================================
        # VALIDAR TREINO
        # ====================================================

        if not treino_id:

            erro = "Selecione um treino."

        # ====================================================
        # VALIDAR DIA
        # ====================================================

        elif dia_semana not in (
            1,
            2,
            3,
            4,
            5,
            6
        ):

            erro = "Selecione o dia da semana."

        if erro:

            treinos = carregar_treinos()

            conn.close()

            return render_template(
                "atribuir_treino.html",
                aluno=aluno,
                treinos=treinos,
                erro=erro
            )

        # ====================================================
        # VERIFICAR TREINO E PERMISSÃO
        # ====================================================

        if usuario_e_owner():

            cursor.execute("""
                SELECT
                    id,
                    nome,
                    descricao,
                    responsavel_id
                FROM treinos
                WHERE id = ?
            """, (
                treino_id,
            ))

        else:

            cursor.execute("""
                SELECT
                    id,
                    nome,
                    descricao,
                    responsavel_id
                FROM treinos
                WHERE id = ?
                  AND responsavel_id = ?
            """, (
                treino_id,
                usuario_id
            ))

        treino = cursor.fetchone()

        if not treino:

            conn.close()

            return redirect(
                f"/alunos/{aluno_id}/treinos/atribuir"
            )

        # ====================================================
        # VERIFICAR SE JÁ EXISTE ATRIBUIÇÃO
        # ====================================================

        cursor.execute("""
            SELECT
                id
            FROM treino_alunos
            WHERE treino_id = ?
              AND usuario_id = ?
        """, (
            treino_id,
            aluno_id
        ))

        ja_atribuido = cursor.fetchone()

        if ja_atribuido:

            treinos = carregar_treinos()

            conn.close()

            return render_template(
                "atribuir_treino.html",
                aluno=aluno,
                treinos=treinos,
                erro="Este treino já está atribuído a este aluno."
            )

        # ====================================================
        # CRIAR ATRIBUIÇÃO
        # ====================================================

        cursor.execute("""
            INSERT INTO treino_alunos
            (
                treino_id,
                usuario_id,
                dia_semana
            )
            VALUES (?, ?, ?)
        """, (
            treino_id,
            aluno_id,
            dia_semana
        ))

        treino_aluno_id = cursor.lastrowid

        # ====================================================
        # BUSCAR EXERCÍCIOS
        # ====================================================

        cursor.execute("""
            SELECT
                te.id AS treino_exercicio_id
            FROM treino_exercicios te
            WHERE te.treino_id = ?
            ORDER BY
                te.ordem,
                te.id
        """, (
            treino_id,
        ))

        exercicios_db = cursor.fetchall()

        # ====================================================
        # COPIAR PRESCRIÇÃO BASE PARA O ALUNO
        # ====================================================

        for exercicio in exercicios_db:

            te_id = exercicio[
                "treino_exercicio_id"
            ]

            cursor.execute("""
                SELECT
                    numero_serie,
                    repeticoes_prescritas
                FROM treino_series
                WHERE treino_exercicio_id = ?
                ORDER BY numero_serie
            """, (
                te_id,
            ))

            series_db = cursor.fetchall()

            # =================================================
            # SE NÃO HOUVER SÉRIES BASE
            # =================================================

            if not series_db:

                series_db = [
                    {
                        "numero_serie": 1,
                        "repeticoes_prescritas": 10
                    }
                ]

            # =================================================
            # SALVAR CADA SÉRIE INDIVIDUAL
            # =================================================

            for serie in series_db:

                numero_serie = serie[
                    "numero_serie"
                ]

                campo = (
                    f"repeticoes_"
                    f"{te_id}_"
                    f"{numero_serie}"
                )

                repeticoes = request.form.get(
                    campo
                )

                # ---------------------------------------------
                # Se o Personal não alterar, usa a base
                # ---------------------------------------------

                if repeticoes in (
                    None,
                    ""
                ):

                    repeticoes = serie[
                        "repeticoes_prescritas"
                    ]

                try:

                    repeticoes = int(
                        repeticoes
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    repeticoes = (
                        serie[
                            "repeticoes_prescritas"
                        ]
                    )

                if repeticoes is None:

                    repeticoes = 10

                if repeticoes < 1:

                    repeticoes = 1

                # ---------------------------------------------
                # GRAVAR PRESCRIÇÃO INDIVIDUAL
                # ---------------------------------------------

                cursor.execute("""
                    INSERT INTO treino_aluno_series
                    (
                        treino_aluno_id,
                        treino_exercicio_id,
                        numero_serie,
                        repeticoes_prescritas
                    )
                    VALUES (?, ?, ?, ?)
                """, (
                    treino_aluno_id,
                    te_id,
                    numero_serie,
                    repeticoes
                ))

        # ====================================================
        # SALVAR
        # ====================================================

        conn.commit()

        conn.close()

        return redirect(
            f"/alunos/{aluno_id}/treinos"
        )

    # ========================================================
    # GET
    # ========================================================

    treinos = carregar_treinos()

    conn.close()

    return render_template(
        "atribuir_treino.html",
        aluno=aluno,
        treinos=treinos
    )

# ============================================================
# EDITAR ATRIBUIÇÃO DE TREINO
# ============================================================

@app.route(
    "/alunos/<int:aluno_id>/treinos/<int:treino_id>/editar",
    methods=["GET", "POST"]
)
@login_obrigatorio
def editar_atribuicao_treino(
    aluno_id,
    treino_id
):

    usuario_id = session["usuario_id"]

    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # VERIFICAR ALUNO
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                ativo,
                foto,
                responsavel_id
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
        """, (
            aluno_id,
        ))

    elif usuario_e_personal():

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                ativo,
                foto,
                responsavel_id
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
              AND responsavel_id = ?
        """, (
            aluno_id,
            usuario_id
        ))

    else:

        conn.close()

        return redirect("/")

    aluno = cursor.fetchone()

    if not aluno:

        conn.close()

        return redirect("/alunos")

    # ========================================================
    # VERIFICAR TREINO
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT
                id,
                nome,
                descricao,
                responsavel_id
            FROM treinos
            WHERE id = ?
        """, (
            treino_id,
        ))

    else:

        cursor.execute("""
            SELECT
                id,
                nome,
                descricao,
                responsavel_id
            FROM treinos
            WHERE id = ?
              AND responsavel_id = ?
        """, (
            treino_id,
            usuario_id
        ))

    treino = cursor.fetchone()

    if not treino:

        conn.close()

        return redirect(
            f"/alunos/{aluno_id}/treinos"
        )

    # ========================================================
    # LOCALIZAR ATRIBUIÇÃO
    # ========================================================

    cursor.execute("""
        SELECT
            id,
            treino_id,
            usuario_id,
            dia_semana
        FROM treino_alunos
        WHERE treino_id = ?
          AND usuario_id = ?
    """, (
        treino_id,
        aluno_id
    ))

    atribuicao = cursor.fetchone()

    if not atribuicao:

        conn.close()

        return redirect(
            f"/alunos/{aluno_id}/treinos"
        )

    treino_aluno_id = atribuicao["id"]

    # ========================================================
    # CARREGAR EXERCÍCIOS
    # ========================================================

    cursor.execute("""
        SELECT
            te.id,
            te.exercicio_id,
            te.ordem,
            te.progressao,
            te.incremento,
            e.nome,
            e.grupo_muscular,
            e.equipamento,
            e.video_url
        FROM treino_exercicios te

        INNER JOIN exercicios e
            ON e.id = te.exercicio_id

        WHERE te.treino_id = ?

        ORDER BY
            te.ordem,
            te.id
    """, (
        treino_id,
    ))

    exercicios_db = cursor.fetchall()

    exercicios = []

    for exercicio in exercicios_db:

        treino_exercicio_id = exercicio[
            "id"
        ]

        # ----------------------------------------------------
        # PRESCRIÇÃO INDIVIDUAL
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                numero_serie,
                repeticoes_prescritas
            FROM treino_aluno_series
            WHERE treino_aluno_id = ?
              AND treino_exercicio_id = ?
            ORDER BY numero_serie
        """, (
            treino_aluno_id,
            treino_exercicio_id
        ))

        series = cursor.fetchall()

        # ----------------------------------------------------
        # FALLBACK PARA PRESCRIÇÃO BASE
        # ----------------------------------------------------

        if not series:

            cursor.execute("""
                SELECT
                    numero_serie,
                    repeticoes_prescritas
                FROM treino_series
                WHERE treino_exercicio_id = ?
                ORDER BY numero_serie
            """, (
                treino_exercicio_id,
            ))

            series = cursor.fetchall()

        # ----------------------------------------------------
        # SE NÃO HOUVER SÉRIE
        # ----------------------------------------------------

        if not series:

            series = [
                {
                    "numero_serie": 1,
                    "repeticoes_prescritas": 10
                }
            ]

        exercicios.append({
            "id": treino_exercicio_id,
            "exercicio_id": exercicio["exercicio_id"],
            "ordem": exercicio["ordem"],
            "nome": exercicio["nome"],
            "grupo_muscular": exercicio["grupo_muscular"],
            "equipamento": exercicio["equipamento"],
            "video_url": exercicio["video_url"],
            "progressao": exercicio["progressao"],
            "incremento": exercicio["incremento"],
            "series": series
        })

    # ========================================================
    # POST
    # ========================================================

    if request.method == "POST":

        dia_semana = request.form.get(
            "dia_semana",
            type=int
        )

        if dia_semana not in (
            1,
            2,
            3,
            4,
            5,
            6
        ):

            conn.close()

            return render_template(
                "editar_atribuicao.html",
                aluno=aluno,
                treino=treino,
                atribuicao=atribuicao,
                exercicios=exercicios,
                erro="Selecione um dia da semana."
            )

        # ----------------------------------------------------
        # ATUALIZAR DIA
        # ----------------------------------------------------

        cursor.execute("""
            UPDATE treino_alunos
            SET dia_semana = ?
            WHERE id = ?
        """, (
            dia_semana,
            treino_aluno_id
        ))

        # ----------------------------------------------------
        # APAGAR PRESCRIÇÃO INDIVIDUAL
        # ----------------------------------------------------

        cursor.execute("""
            DELETE FROM treino_aluno_series
            WHERE treino_aluno_id = ?
        """, (
            treino_aluno_id,
        ))

        # ----------------------------------------------------
        # RECRIAR PRESCRIÇÃO
        # ----------------------------------------------------

        for exercicio in exercicios:

            treino_exercicio_id = exercicio[
                "id"
            ]

            prefixo = (
                f"repeticoes_"
                f"{treino_exercicio_id}_"
            )

            numeros_series = []

            for chave in request.form.keys():

                if not chave.startswith(
                    prefixo
                ):
                    continue

                numero_texto = chave[
                    len(prefixo):
                ]

                try:

                    numero_serie = int(
                        numero_texto
                    )

                except ValueError:

                    continue

                if numero_serie > 0:

                    numeros_series.append(
                        numero_serie
                    )

            numeros_series = sorted(
                set(numeros_series)
            )

            # ------------------------------------------------
            # VALORES ANTERIORES
            # ------------------------------------------------

            valores_anteriores = {}

            for serie in exercicio["series"]:

                valores_anteriores[
                    serie["numero_serie"]
                ] = serie[
                    "repeticoes_prescritas"
                ]

            # ------------------------------------------------
            # SALVAR
            # ------------------------------------------------

            for numero_serie in numeros_series:

                campo = (
                    f"repeticoes_"
                    f"{treino_exercicio_id}_"
                    f"{numero_serie}"
                )

                valor = request.form.get(
                    campo,
                    ""
                ).strip()

                if valor == "":

                    repeticoes = (
                        valores_anteriores.get(
                            numero_serie,
                            10
                        )
                    )

                else:

                    try:

                        repeticoes = int(
                            valor
                        )

                    except ValueError:

                        repeticoes = (
                            valores_anteriores.get(
                                numero_serie,
                                10
                            )
                        )

                if repeticoes < 1:

                    repeticoes = 1

                cursor.execute("""
                    INSERT INTO treino_aluno_series
                    (
                        treino_aluno_id,
                        treino_exercicio_id,
                        numero_serie,
                        repeticoes_prescritas
                    )
                    VALUES (?, ?, ?, ?)
                """, (
                    treino_aluno_id,
                    treino_exercicio_id,
                    numero_serie,
                    repeticoes
                ))

        conn.commit()

        # ----------------------------------------------------
        # CONTADORES
        # ----------------------------------------------------

        cursor.execute("""
            SELECT COUNT(*)
            FROM treino_aluno_series
            WHERE treino_aluno_id = ?
        """, (
            treino_aluno_id,
        ))

        total_series = cursor.fetchone()[0]

        total_exercicios = len(
            exercicios
        )

        conn.close()

        return render_template(
            "treino_concluido.html",
            treino_id=treino_id,
            treino=treino,
            total_exercicios=total_exercicios,
            total_series=total_series,
            aluno=aluno,
            mensagem="Treino salvo com sucesso!"
        )

    # ========================================================
    # GET
    # ========================================================

    conn.close()

    return render_template(
        "editar_atribuicao.html",
        aluno=aluno,
        treino=treino,
        atribuicao=atribuicao,
        exercicios=exercicios
    )


# ============================================================
# EXCLUIR ATRIBUIÇÃO DE TREINO
# ============================================================

@app.route(
    "/alunos/<int:aluno_id>/treinos/<int:treino_id>/excluir",
    methods=["POST"]
)
@login_obrigatorio
def excluir_atribuicao_treino(
    aluno_id,
    treino_id
):

    usuario_id = session["usuario_id"]

    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # VERIFICAR ALUNO
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT id
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
        """, (
            aluno_id,
        ))

    elif usuario_e_personal():

        cursor.execute("""
            SELECT id
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
              AND responsavel_id = ?
        """, (
            aluno_id,
            usuario_id
        ))

    else:

        conn.close()

        return redirect("/")

    aluno = cursor.fetchone()

    if not aluno:

        conn.close()

        return redirect("/alunos")

    # ========================================================
    # VERIFICAR TREINO
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT id
            FROM treinos
            WHERE id = ?
        """, (
            treino_id,
        ))

    else:

        cursor.execute("""
            SELECT id
            FROM treinos
            WHERE id = ?
              AND responsavel_id = ?
        """, (
            treino_id,
            usuario_id
        ))

    treino = cursor.fetchone()

    if not treino:

        conn.close()

        return redirect(
            f"/alunos/{aluno_id}/treinos"
        )

    # ========================================================
    # LOCALIZAR ATRIBUIÇÃO
    # ========================================================

    cursor.execute("""
        SELECT id
        FROM treino_alunos
        WHERE treino_id = ?
          AND usuario_id = ?
    """, (
        treino_id,
        aluno_id
    ))

    atribuicao = cursor.fetchone()

    if atribuicao:

        treino_aluno_id = atribuicao["id"]

        # ----------------------------------------------------
        # PRIMEIRO APAGAR PRESCRIÇÕES INDIVIDUAIS
        # ----------------------------------------------------

        cursor.execute("""
            DELETE FROM treino_aluno_series
            WHERE treino_aluno_id = ?
        """, (
            treino_aluno_id,
        ))

        # ----------------------------------------------------
        # DEPOIS APAGAR ATRIBUIÇÃO
        # ----------------------------------------------------

        cursor.execute("""
            DELETE FROM treino_alunos
            WHERE id = ?
        """, (
            treino_aluno_id,
        ))

    conn.commit()

    conn.close()

    return redirect(
        f"/alunos/{aluno_id}/treinos"
    )


# ============================================================
# NOVO TREINO
# ============================================================

@app.route(
    "/treinos/novo",
    methods=["GET", "POST"]
)
@login_obrigatorio
def novo_treino():

    if not usuario_e_gestor():
        return redirect("/")

    if request.method == "POST":

        nome = request.form.get(
            "nome",
            ""
        ).strip()

        descricao = request.form.get(
            "descricao",
            ""
        ).strip()

        if not nome:

            return render_template(
                "novo_treino.html",
                erro="Informe o nome do treino."
            )

        conn = conectar()
        cursor = conn.cursor()

        responsavel_id = session["usuario_id"]

        cursor.execute("""
            INSERT INTO treinos
            (
                nome,
                descricao,
                responsavel_id
            )
            VALUES (?, ?, ?)
        """, (
            nome,
            descricao,
            responsavel_id
        ))

        treino_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return redirect(
            f"/treinos/{treino_id}/editar"
        )

    return render_template(
        "novo_treino.html"
    )


# ============================================================
# TREINOS
# ============================================================

@app.route("/treinos")
@login_obrigatorio
def treinos():

    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # OWNER
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT
                t.*,
                (
                    SELECT COUNT(*)
                    FROM treino_exercicios te
                    WHERE te.treino_id = t.id
                ) AS total_exercicios
            FROM treinos t
            ORDER BY
                t.nome
        """)

    # ========================================================
    # PERSONAL
    # ========================================================

    elif usuario_e_personal():

        cursor.execute("""
            SELECT
                t.*,
                (
                    SELECT COUNT(*)
                    FROM treino_exercicios te
                    WHERE te.treino_id = t.id
                ) AS total_exercicios
            FROM treinos t
            WHERE t.responsavel_id = ?
            ORDER BY
                t.nome
        """, (
            session["usuario_id"],
        ))

    # ========================================================
    # ALUNO
    # ========================================================

    else:

        cursor.execute("""
            SELECT
                t.*,
                (
                    SELECT COUNT(*)
                    FROM treino_exercicios te
                    WHERE te.treino_id = t.id
                ) AS total_exercicios,
                ta.dia_semana
            FROM treinos t

            INNER JOIN treino_alunos ta
                ON ta.treino_id = t.id

            WHERE ta.usuario_id = ?

            ORDER BY
                CASE
                    WHEN ta.dia_semana IS NULL THEN 99
                    ELSE ta.dia_semana
                END,
                t.nome
        """, (
            session["usuario_id"],
        ))

    treinos_db = cursor.fetchall()

    conn.close()

    return render_template(
        "treinos.html",
        treinos=treinos_db
    )


# ============================================================
# EDITAR TREINO
# ============================================================

@app.route(
    "/treinos/<int:treino_id>/editar",
    methods=["GET", "POST"]
)
@login_obrigatorio
def editar_treino(treino_id):

    if not usuario_e_gestor():
        return redirect("/")

    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # VERIFICAR TREINO E PERMISSÃO
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT *
            FROM treinos
            WHERE id = ?
        """, (
            treino_id,
        ))

    else:

        cursor.execute("""
            SELECT *
            FROM treinos
            WHERE id = ?
              AND responsavel_id = ?
        """, (
            treino_id,
            session["usuario_id"]
        ))

    treino = cursor.fetchone()

    if not treino:

        conn.close()

        return redirect("/treinos")

    # ========================================================
    # POST - SALVAR / ADICIONAR EXERCÍCIO
    # ========================================================

    if request.method == "POST":

        # ====================================================
        # VERIFICAR SE É PEDIDO PARA ADICIONAR EXERCÍCIO
        # ====================================================

        adicionar_exercicio_id = request.form.get(
            "adicionar_exercicio_id",
            type=int
        )

        if adicionar_exercicio_id:

            # ================================================
            # VERIFICAR SE O EXERCÍCIO EXISTE
            # ================================================

            cursor.execute("""
                SELECT
                    id,
                    nome,
                    grupo_muscular,
                    equipamento,
                    video_url
                FROM exercicios
                WHERE id = ?
            """, (
                adicionar_exercicio_id,
            ))

            exercicio_novo = cursor.fetchone()

            if not exercicio_novo:

                conn.close()

                return redirect(
                    f"/treinos/{treino_id}/editar"
                )

            # ================================================
            # VERIFICAR SE JÁ ESTÁ NO TREINO
            # ================================================

            cursor.execute("""
                SELECT
                    id
                FROM treino_exercicios
                WHERE treino_id = ?
                  AND exercicio_id = ?
            """, (
                treino_id,
                adicionar_exercicio_id
            ))

            ja_existe = cursor.fetchone()

            if ja_existe:

                conn.close()

                return redirect(
                    f"/treinos/{treino_id}/editar?erro=exercicio_existente"
                )

            # ================================================
            # DESCOBRIR PRÓXIMA ORDEM
            # ================================================

            cursor.execute("""
                SELECT
                    COALESCE(
                        MAX(ordem),
                        0
                    ) + 1
                FROM treino_exercicios
                WHERE treino_id = ?
            """, (
                treino_id,
            ))

            proxima_ordem = cursor.fetchone()[0]

            # ================================================
            # ADICIONAR EXERCÍCIO AO TREINO
            # ================================================

            cursor.execute("""
                INSERT INTO treino_exercicios
                (
                    treino_id,
                    exercicio_id,
                    ordem,
                    progressao,
                    incremento
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                treino_id,
                adicionar_exercicio_id,
                proxima_ordem,
                "automatica",
                2.5
            ))

            treino_exercicio_id = cursor.lastrowid

            # ================================================
            # CRIAR PRESCRIÇÃO BASE INICIAL
            # ================================================

            cursor.execute("""
                INSERT INTO treino_series
                (
                    treino_exercicio_id,
                    numero_serie,
                    repeticoes_prescritas
                )
                VALUES (?, ?, ?)
            """, (
                treino_exercicio_id,
                1,
                10
            ))

            conn.commit()

            conn.close()

            return redirect(
                f"/treinos/{treino_id}/editar"
            )

        # ====================================================
        # SALVAR PRESCRIÇÕES DOS EXERCÍCIOS EXISTENTES
        # ====================================================

        cursor.execute("""
            SELECT
                id
            FROM treino_exercicios
            WHERE treino_id = ?
            ORDER BY
                ordem,
                id
        """, (
            treino_id,
        ))

        exercicios_db = cursor.fetchall()

        for exercicio in exercicios_db:

            treino_exercicio_id = exercicio[
                "id"
            ]

            # =================================================
            # PROGRESSÃO
            # =================================================

            progressao = request.form.get(
                f"progressao_{treino_exercicio_id}",
                "automatica"
            ).strip().lower()

            if progressao not in (
                "automatica",
                "manter",
                "aumentar",
                "reduzir"
            ):

                progressao = "automatica"

            # =================================================
            # INCREMENTO
            # =================================================

            incremento_raw = request.form.get(
                f"incremento_{treino_exercicio_id}",
                "2.5"
            ).strip().replace(
                ",",
                "."
            )

            try:

                incremento = float(
                    incremento_raw
                )

            except:

                incremento = 2.5

            if incremento <= 0:

                incremento = 2.5

            # =================================================
            # SALVAR PROGRESSÃO
            # =================================================

            cursor.execute("""
                UPDATE treino_exercicios
                SET
                    progressao = ?,
                    incremento = ?
                WHERE id = ?
            """, (
                progressao,
                incremento,
                treino_exercicio_id
            ))

            # =================================================
            # APAGAR PRESCRIÇÃO BASE
            # =================================================

            cursor.execute("""
                DELETE FROM treino_series
                WHERE treino_exercicio_id = ?
            """, (
                treino_exercicio_id,
            ))

            # =================================================
            # RECRIAR PRESCRIÇÃO BASE
            # =================================================

            numero_serie = 1

            while True:

                campo = (
                    f"reps_"
                    f"{treino_exercicio_id}_"
                    f"{numero_serie}"
                )

                reps = request.form.get(
                    campo
                )

                if reps is None:
                    break

                try:

                    repeticoes = int(
                        reps
                    )

                except:

                    repeticoes = 1

                if repeticoes < 1:

                    repeticoes = 1

                cursor.execute("""
                    INSERT INTO treino_series
                    (
                        treino_exercicio_id,
                        numero_serie,
                        repeticoes_prescritas
                    )
                    VALUES (?, ?, ?)
                """, (
                    treino_exercicio_id,
                    numero_serie,
                    repeticoes
                ))

                numero_serie += 1

            # =================================================
            # GARANTIR PELO MENOS UMA SÉRIE
            # =================================================

            if numero_serie == 1:

                cursor.execute("""
                    INSERT INTO treino_series
                    (
                        treino_exercicio_id,
                        numero_serie,
                        repeticoes_prescritas
                    )
                    VALUES (?, ?, ?)
                """, (
                    treino_exercicio_id,
                    1,
                    10
                ))

        conn.commit()

        conn.close()

        return redirect(
            f"/treinos/{treino_id}/editar"
        )

    # ========================================================
    # GET - EXERCÍCIOS DO TREINO
    # ========================================================

    cursor.execute("""
        SELECT
            te.id,
            te.exercicio_id,
            te.ordem,
            te.progressao,
            te.incremento,
            e.nome,
            e.grupo_muscular,
            e.equipamento,
            e.video_url
        FROM treino_exercicios te

        INNER JOIN exercicios e
            ON e.id = te.exercicio_id

        WHERE te.treino_id = ?

        ORDER BY
            te.ordem,
            te.id
    """, (
        treino_id,
    ))

    exercicios = cursor.fetchall()

    # ========================================================
    # PRESCRIÇÕES
    # ========================================================

    series_prescritas = {}

    for exercicio in exercicios:

        treino_exercicio_id = exercicio[
            "id"
        ]

        cursor.execute("""
            SELECT
                numero_serie,
                repeticoes_prescritas
            FROM treino_series
            WHERE treino_exercicio_id = ?
            ORDER BY numero_serie
        """, (
            treino_exercicio_id,
        ))

        series_prescritas[
            treino_exercicio_id
        ] = cursor.fetchall()

    # ========================================================
    # EXERCÍCIOS DISPONÍVEIS PARA ADICIONAR
    # ========================================================

    cursor.execute("""
        SELECT
            id,
            nome,
            grupo_muscular,
            equipamento,
            video_url
        FROM exercicios
        ORDER BY
            grupo_muscular,
            nome
    """)

    exercicios_disponiveis_db = cursor.fetchall()

    # ========================================================
    # RETIRAR EXERCÍCIOS QUE JÁ ESTÃO NO TREINO
    # ========================================================

    exercicios_ids = {
        exercicio["exercicio_id"]
        for exercicio in exercicios
    }

    exercicios_disponiveis = []

    for exercicio in exercicios_disponiveis_db:

        if exercicio["id"] in exercicios_ids:
            continue

        exercicios_disponiveis.append(
            exercicio
        )

    # ========================================================
    # MENSAGEM DE ERRO
    # ========================================================

    erro = None

    if request.args.get(
        "erro"
    ) == "exercicio_existente":

        erro = (
            "Este exercício já está "
            "adicionado a este treino."
        )

    conn.close()

    return render_template(
        "editar_treino.html",
        treino=treino,
        exercicios=exercicios,
        series_prescritas=series_prescritas,
        exercicios_disponiveis=exercicios_disponiveis,
        erro=erro
    )

# ============================================================
# INICIAR TREINO DE UM ALUNO ESPECÍFICO
# ============================================================

@app.route(
    "/alunos/<int:aluno_id>/treinos/<int:treino_id>/iniciar"
)
@login_obrigatorio
def iniciar_treino(
    aluno_id,
    treino_id
):

    usuario_id = session["usuario_id"]

    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # LOCALIZAR ATRIBUIÇÃO EXATA
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT
                ta.id,
                ta.usuario_id
            FROM treino_alunos ta

            INNER JOIN usuarios u
                ON u.id = ta.usuario_id

            WHERE ta.treino_id = ?
              AND ta.usuario_id = ?
              AND u.tipo = 'aluno'
        """, (
            treino_id,
            aluno_id
        ))

    elif usuario_e_personal():

        cursor.execute("""
            SELECT
                ta.id,
                ta.usuario_id
            FROM treino_alunos ta

            INNER JOIN usuarios u
                ON u.id = ta.usuario_id

            WHERE ta.treino_id = ?
              AND ta.usuario_id = ?
              AND u.tipo = 'aluno'
              AND u.responsavel_id = ?
        """, (
            treino_id,
            aluno_id,
            usuario_id
        ))

    else:

        if aluno_id != usuario_id:

            conn.close()

            return redirect("/")

        cursor.execute("""
            SELECT
                ta.id,
                ta.usuario_id
            FROM treino_alunos ta
            WHERE ta.treino_id = ?
              AND ta.usuario_id = ?
        """, (
            treino_id,
            usuario_id
        ))

    acesso = cursor.fetchone()

    if not acesso:

        conn.close()

        if usuario_e_gestor():

            return redirect(
                f"/alunos/{aluno_id}/treinos"
            )

        return redirect("/treinos")

    treino_aluno_id = acesso["id"]

    aluno_id = acesso["usuario_id"]

    # ========================================================
    # BUSCAR TREINO
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT *
            FROM treinos
            WHERE id = ?
        """, (
            treino_id,
        ))

    elif usuario_e_personal():

        cursor.execute("""
            SELECT *
            FROM treinos
            WHERE id = ?
              AND responsavel_id = ?
        """, (
            treino_id,
            usuario_id
        ))

    else:

        cursor.execute("""
            SELECT
                t.*
            FROM treinos t

            INNER JOIN treino_alunos ta
                ON ta.treino_id = t.id

            WHERE t.id = ?
              AND ta.usuario_id = ?
        """, (
            treino_id,
            aluno_id
        ))

    treino = cursor.fetchone()

    if not treino:

        conn.close()

        if usuario_e_gestor():

            return redirect(
                f"/alunos/{aluno_id}/treinos"
            )

        return redirect("/treinos")

    # ========================================================
    # BUSCAR EXERCÍCIOS
    # ========================================================

    cursor.execute("""
        SELECT
            te.id AS treino_exercicio_id,
            te.exercicio_id,
            te.progressao,
            te.incremento,
            e.id AS exercicio_id,
            e.nome,
            e.grupo_muscular,
            e.equipamento,
            e.video_url
        FROM treino_exercicios te

        INNER JOIN exercicios e
            ON e.id = te.exercicio_id

        WHERE te.treino_id = ?

        ORDER BY
            te.ordem,
            te.id
    """, (
        treino_id,
    ))

    exercicios_db = cursor.fetchall()

    exercicios_final = []

    # ========================================================
    # PROCESSAR EXERCÍCIOS
    # ========================================================

    for exercicio in exercicios_db:

        te_id = exercicio[
            "treino_exercicio_id"
        ]

        exercicio_id = exercicio[
            "exercicio_id"
        ]

        # ====================================================
        # PRESCRIÇÃO INDIVIDUAL
        # ====================================================

        cursor.execute("""
            SELECT
                numero_serie,
                repeticoes_prescritas
            FROM treino_aluno_series
            WHERE treino_aluno_id = ?
              AND treino_exercicio_id = ?
            ORDER BY numero_serie
        """, (
            treino_aluno_id,
            te_id
        ))

        prescricoes = cursor.fetchall()

        # ====================================================
        # FALLBACK PARA PRESCRIÇÃO BASE
        # ====================================================

        if not prescricoes:

            cursor.execute("""
                SELECT
                    numero_serie,
                    repeticoes_prescritas
                FROM treino_series
                WHERE treino_exercicio_id = ?
                ORDER BY numero_serie
            """, (
                te_id,
            ))

            prescricoes = cursor.fetchall()

        # ====================================================
        # HISTÓRICO EXCLUSIVO DO ALUNO
        # ====================================================

        cursor.execute("""
            SELECT
                s.id,
                s.data
            FROM sessoes s

            INNER JOIN series se
                ON se.sessao_id = s.id

            WHERE s.treino_id = ?
              AND s.usuario_id = ?
              AND (
                    se.treino_exercicio_id = ?
                    OR (
                        se.treino_exercicio_id IS NULL
                        AND se.exercicio_id = ?
                    )
                  )

            ORDER BY
                s.id DESC

            LIMIT 1
        """, (
            treino_id,
            aluno_id,
            te_id,
            exercicio_id
        ))

        sessao_anterior = cursor.fetchone()

        historico = {
            "data": None,
            "series": []
        }

        if sessao_anterior:

            cursor.execute("""
                SELECT
                    numero_serie,
                    carga,
                    repeticoes
                FROM series

                WHERE sessao_id = ?
                  AND (
                        treino_exercicio_id = ?
                        OR (
                            treino_exercicio_id IS NULL
                            AND exercicio_id = ?
                        )
                      )

                ORDER BY
                    numero_serie
            """, (
                sessao_anterior["id"],
                te_id,
                exercicio_id
            ))

            series_historico = cursor.fetchall()

            historico = {
                "data": sessao_anterior["data"],
                "series": series_historico
            }

        # ====================================================
        # PROGRESSÃO
        # ====================================================

        sugestoes = []

        progressao = exercicio[
            "progressao"
        ]

        incremento = exercicio[
            "incremento"
        ]

        if incremento is None:

            incremento = 2.5

        incremento = float(
            incremento
        )

        for prescricao in prescricoes:

            numero = prescricao[
                "numero_serie"
            ]

            reps_previstas = prescricao[
                "repeticoes_prescritas"
            ]

            anterior = None

            for item in historico["series"]:

                if item["numero_serie"] == numero:

                    anterior = item

                    break

            carga_anterior = None
            reps_anteriores = None
            carga_sugerida = None
            tipo = None

            if anterior:

                carga_anterior = anterior[
                    "carga"
                ]

                reps_anteriores = anterior[
                    "repeticoes"
                ]

                if (
                    carga_anterior is not None
                    and reps_anteriores is not None
                    and reps_previstas is not None
                ):

                    carga_anterior = float(
                        carga_anterior
                    )

                    reps_anteriores = int(
                        reps_anteriores
                    )

                    reps_previstas = int(
                        reps_previstas
                    )

                    # ========================================
                    # AUTOMÁTICA
                    # ========================================

                    if progressao == "automatica":

                        if (
                            reps_anteriores
                            >= reps_previstas
                        ):

                            carga_sugerida = (
                                carga_anterior
                                + incremento
                            )

                            tipo = "aumentar"

                        elif (
                            reps_anteriores
                            >= (
                                reps_previstas
                                * 0.80
                            )
                        ):

                            carga_sugerida = (
                                carga_anterior
                            )

                            tipo = "manter"

                        else:

                            carga_sugerida = max(
                                0,
                                carga_anterior
                                - incremento
                            )

                            tipo = "reduzir"

                    # ========================================
                    # MANTER
                    # ========================================

                    elif progressao == "manter":

                        carga_sugerida = (
                            carga_anterior
                        )

                        tipo = "manter"

                    # ========================================
                    # AUMENTAR
                    # ========================================

                    elif progressao == "aumentar":

                        carga_sugerida = (
                            carga_anterior
                            + incremento
                        )

                        tipo = "aumentar"

                    # ========================================
                    # REDUZIR
                    # ========================================

                    elif progressao == "reduzir":

                        carga_sugerida = max(
                            0,
                            carga_anterior
                            - incremento
                        )

                        tipo = "reduzir"

                    else:

                        carga_sugerida = (
                            carga_anterior
                        )

                        tipo = "manter"

            sugestoes.append({
                "numero_serie": numero,
                "carga_anterior": carga_anterior,
                "repeticoes_anteriores": reps_anteriores,
                "carga_sugerida": carga_sugerida,
                "tipo": tipo
            })

        # ====================================================
        # MONTAR EXERCÍCIO FINAL
        # ====================================================

        exercicios_final.append({

            "treino_exercicio_id": te_id,

            "exercicio_id": exercicio_id,

            "nome": exercicio["nome"],

            "grupo_muscular": exercicio[
                "grupo_muscular"
            ],

            "equipamento": exercicio[
                "equipamento"
            ],

            "video_url": exercicio[
                "video_url"
            ],

            "series": prescricoes,

            "historico": historico,

            "sugestoes": sugestoes,

            "progressao": progressao,

            "incremento": incremento

        })

    conn.close()

    return render_template(
        "treino_iniciar.html",
        treino=treino,
        exercicios=exercicios_final,
        aluno_id=aluno_id
    )


# ============================================================
# FINALIZAR TREINO DE UM ALUNO ESPECÍFICO
# ============================================================

@app.route(
    "/alunos/<int:aluno_id>/treinos/<int:treino_id>/finalizar",
    methods=["POST"]
)
@login_obrigatorio
def finalizar_treino(
    aluno_id,
    treino_id
):

    usuario_id = session["usuario_id"]

    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # VERIFICAR ACESSO AO ALUNO
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                foto
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
        """, (
            aluno_id,
        ))

    elif usuario_e_personal():

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                foto
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
              AND responsavel_id = ?
        """, (
            aluno_id,
            usuario_id
        ))

    else:

        if aluno_id != usuario_id:

            conn.close()

            return redirect("/")

        cursor.execute("""
            SELECT
                id,
                nome,
                usuario,
                foto
            FROM usuarios
            WHERE id = ?
              AND tipo = 'aluno'
        """, (
            aluno_id,
        ))

    aluno = cursor.fetchone()

    if not aluno:

        conn.close()

        if usuario_e_gestor():

            return redirect("/alunos")

        return redirect("/treinos")

    # ========================================================
    # VERIFICAR ATRIBUIÇÃO
    # ========================================================

    cursor.execute("""
        SELECT
            id,
            usuario_id,
            treino_id
        FROM treino_alunos
        WHERE treino_id = ?
          AND usuario_id = ?
    """, (
        treino_id,
        aluno_id
    ))

    acesso = cursor.fetchone()

    if not acesso:

        conn.close()

        if usuario_e_gestor():

            return redirect(
                f"/alunos/{aluno_id}/treinos"
            )

        return redirect("/treinos")

    treino_aluno_id = acesso[
        "id"
    ]

    # ========================================================
    # BUSCAR TREINO
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT *
            FROM treinos
            WHERE id = ?
        """, (
            treino_id,
        ))

    elif usuario_e_personal():

        cursor.execute("""
            SELECT *
            FROM treinos
            WHERE id = ?
              AND responsavel_id = ?
        """, (
            treino_id,
            usuario_id
        ))

    else:

        cursor.execute("""
            SELECT
                t.*
            FROM treinos t

            INNER JOIN treino_alunos ta
                ON ta.treino_id = t.id

            WHERE t.id = ?
              AND ta.usuario_id = ?
        """, (
            treino_id,
            aluno_id
        ))

    treino_concluido = cursor.fetchone()

    if not treino_concluido:

        conn.close()

        if usuario_e_gestor():

            return redirect(
                f"/alunos/{aluno_id}/treinos"
            )

        return redirect("/treinos")

    # ========================================================
    # CRIAR SESSÃO
    # ========================================================

    cursor.execute("""
        INSERT INTO sessoes
        (
            treino_id,
            data,
            usuario_id
        )
        VALUES (?, ?, ?)
    """, (
        treino_id,
        date.today().isoformat(),
        aluno_id
    ))

    sessao_id = cursor.lastrowid

    # ========================================================
    # BUSCAR EXERCÍCIOS
    # ========================================================

    cursor.execute("""
        SELECT
            te.id AS treino_exercicio_id,
            te.exercicio_id
        FROM treino_exercicios te
        WHERE te.treino_id = ?
        ORDER BY
            te.ordem,
            te.id
    """, (
        treino_id,
    ))

    exercicios = cursor.fetchall()

    # ========================================================
    # SALVAR SÉRIES REALIZADAS
    # ========================================================

    for exercicio in exercicios:

        te_id = exercicio[
            "treino_exercicio_id"
        ]

        exercicio_id = exercicio[
            "exercicio_id"
        ]

        # ====================================================
        # PRESCRIÇÃO INDIVIDUAL
        # ====================================================

        cursor.execute("""
            SELECT
                numero_serie
            FROM treino_aluno_series
            WHERE treino_aluno_id = ?
              AND treino_exercicio_id = ?
            ORDER BY numero_serie
        """, (
            treino_aluno_id,
            te_id
        ))

        series_prescritas = cursor.fetchall()

        # ====================================================
        # FALLBACK
        # ====================================================

        if not series_prescritas:

            cursor.execute("""
                SELECT
                    numero_serie
                FROM treino_series
                WHERE treino_exercicio_id = ?
                ORDER BY numero_serie
            """, (
                te_id,
            ))

            series_prescritas = cursor.fetchall()

        # ====================================================
        # SALVAR CADA SÉRIE
        # ====================================================

        for serie in series_prescritas:

            numero = serie[
                "numero_serie"
            ]

            peso = request.form.get(
                f"peso_{te_id}_{numero}"
            )

            reps = request.form.get(
                f"reps_{te_id}_{numero}"
            )

            if peso is None and reps is None:

                continue

            if not peso and not reps:

                continue

            # ------------------------------------------------
            # PESO
            # ------------------------------------------------

            try:

                carga = (
                    float(
                        peso.replace(
                            ",",
                            "."
                        )
                    )
                    if peso
                    else 0
                )

            except:

                carga = 0

            # ------------------------------------------------
            # REPETIÇÕES
            # ------------------------------------------------

            try:

                repeticoes = (
                    int(reps)
                    if reps
                    else 0
                )

            except:

                repeticoes = 0

            # ------------------------------------------------
            # GRAVAR
            # ------------------------------------------------

            cursor.execute("""
                INSERT INTO series
                (
                    sessao_id,
                    exercicio_id,
                    treino_exercicio_id,
                    numero_serie,
                    carga,
                    repeticoes
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sessao_id,
                exercicio_id,
                te_id,
                numero,
                carga,
                repeticoes
            ))

    # ========================================================
    # TOTAL DE EXERCÍCIOS
    # ========================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM treino_exercicios
        WHERE treino_id = ?
    """, (
        treino_id,
    ))

    total_exercicios = cursor.fetchone()[0]

    # ========================================================
    # TOTAL DE SÉRIES
    # ========================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM series
        WHERE sessao_id = ?
    """, (
        sessao_id,
    ))

    total_series = cursor.fetchone()[0]

    # ========================================================
    # SALVAR
    # ========================================================

    conn.commit()

    conn.close()

    # ========================================================
    # TELA DE CONCLUSÃO
    # ========================================================

    return render_template(
        "treino_concluido.html",
        treino_id=treino_id,
        treino=treino_concluido,
        total_exercicios=total_exercicios,
        total_series=total_series,
        aluno=aluno
    )

# DE EXERCÍCIOS

@app.route("/exercicios")
@login_obrigatorio
def exercicios():

    if not usuario_e_gestor():
        return redirect("/")

    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # OWNER
    # ========================================================

    if usuario_e_owner():

        cursor.execute("""
            SELECT
                e.id,
                e.nome,
                e.grupo_muscular,
                e.video_url,
                e.responsavel_id,
                u.nome AS responsavel_nome
            FROM exercicios e
            LEFT JOIN usuarios u
                ON u.id = e.responsavel_id
            ORDER BY
                e.grupo_muscular,
                e.nome
        """)

    # ========================================================
    # PERSONAL
    # ========================================================

    else:

        cursor.execute("""
            SELECT
                e.id,
                e.nome,
                e.grupo_muscular,
                e.video_url,
                e.responsavel_id,
                u.nome AS responsavel_nome
            FROM exercicios e
            LEFT JOIN usuarios u
                ON u.id = e.responsavel_id
            WHERE
                e.responsavel_id IS NULL
                OR e.responsavel_id = ?
            ORDER BY
                e.grupo_muscular,
                e.nome
        """, (
            session["usuario_id"],
        ))

    exercicios_db = cursor.fetchall()

    conn.close()

    return render_template(
        "exercicios.html",
        exercicios=exercicios_db
    )
# ============================================================
# NOVO EXERCÍCIO
# ============================================================

@app.route(
    "/exercicios/novo",
    methods=["GET", "POST"]
)
@login_obrigatorio
def novo_exercicio():

    if not usuario_e_gestor():
        return redirect("/")

    grupos_musculares = [
        "Peito",
        "Costas",
        "Ombros",
        "Bíceps",
        "Tríceps",
        "Quadríceps",
        "Posterior de coxa",
        "Glúteos",
        "Panturrilhas",
        "Abdômen",
        "Outro"
    ]

    erro = None

    if request.method == "POST":

        nome = request.form.get(
            "nome",
            ""
        ).strip()

        grupo_muscular = request.form.get(
            "grupo_muscular",
            ""
        ).strip()

        video_url = request.form.get(
            "video_url",
            ""
        ).strip()

        # ====================================================
        # VALIDAR NOME
        # ====================================================

        if not nome:

            erro = "Informe o nome do exercício."

        # ====================================================
        # VALIDAR GRUPO MUSCULAR
        # ====================================================

        elif grupo_muscular not in grupos_musculares:

            erro = "Selecione um grupo muscular válido."

        else:

            conn = conectar()
            cursor = conn.cursor()

            # =================================================
            # VERIFICAR DUPLICIDADE
            # =================================================

            if usuario_e_owner():

                cursor.execute("""
                    SELECT
                        id
                    FROM exercicios
                    WHERE LOWER(nome) = LOWER(?)
                      AND responsavel_id IS NULL
                """, (
                    nome,
                ))

            else:

                cursor.execute("""
                    SELECT
                        id
                    FROM exercicios
                    WHERE LOWER(nome) = LOWER(?)
                      AND (
                          responsavel_id IS NULL
                          OR responsavel_id = ?
                      )
                """, (
                    nome,
                    session["usuario_id"]
                ))

            exercicio_existente = cursor.fetchone()

            if exercicio_existente:

                conn.close()

                erro = (
                    "Este exercício já está "
                    "cadastrado na sua biblioteca."
                )

            else:

                # =============================================
                # RESPONSÁVEL
                # =============================================

                if usuario_e_owner():

                    responsavel_id = None

                else:

                    responsavel_id = session[
                        "usuario_id"
                    ]

                # =============================================
                # CADASTRAR
                # =============================================

                cursor.execute("""
                    INSERT INTO exercicios
                    (
                        nome,
                        grupo_muscular,
                        equipamento,
                        repeticoes_min,
                        repeticoes_max,
                        incremento_carga,
                        video_url,
                        responsavel_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    nome,
                    grupo_muscular,
                    None,
                    None,
                    None,
                    2.5,
                    video_url if video_url else None,
                    responsavel_id
                ))

                conn.commit()

                conn.close()

                return redirect(
                    "/exercicios"
                )

    return render_template(
        "novo_exercicio.html",
        grupos_musculares=grupos_musculares,
        erro=erro
    )

# ============================================================
# EDITAR EXERCÍCIO
# ============================================================

@app.route(
    "/exercicios/<int:exercicio_id>/editar",
    methods=["GET", "POST"]
)
@login_obrigatorio
def editar_exercicio(exercicio_id):

    if not usuario_e_gestor():
        return redirect("/")

    grupos_musculares = [
        "Peito",
        "Costas",
        "Ombros",
        "Bíceps",
        "Tríceps",
        "Quadríceps",
        "Posterior de coxa",
        "Glúteos",
        "Panturrilhas",
        "Abdômen",
        "Outro"
    ]

    conn = conectar()
    cursor = conn.cursor()

    # ========================================================
    # LOCALIZAR EXERCÍCIO
    # ========================================================

    cursor.execute("""
        SELECT
            id,
            nome,
            grupo_muscular,
            video_url,
            responsavel_id
        FROM exercicios
        WHERE id = ?
    """, (
        exercicio_id,
    ))

    exercicio = cursor.fetchone()

    if not exercicio:

        conn.close()

        return redirect("/exercicios")

    # ========================================================
    # VERIFICAR PERMISSÃO
    # ========================================================

    if usuario_e_owner():

        permitido = True

    else:

        permitido = (
            exercicio["responsavel_id"] is None
            or
            exercicio["responsavel_id"]
            == session["usuario_id"]
        )

    if not permitido:

        conn.close()

        return redirect("/exercicios")

    erro = None

    # ========================================================
    # SALVAR ALTERAÇÕES
    # ========================================================

    if request.method == "POST":

        nome = request.form.get(
            "nome",
            ""
        ).strip()

        grupo_muscular = request.form.get(
            "grupo_muscular",
            ""
        ).strip()

        video_url = request.form.get(
            "video_url",
            ""
        ).strip()

        # ====================================================
        # VALIDAR NOME
        # ====================================================

        if not nome:

            erro = (
                "Informe o nome do exercício."
            )

        # ====================================================
        # VALIDAR GRUPO
        # ====================================================

        elif grupo_muscular not in grupos_musculares:

            erro = (
                "Selecione um grupo muscular válido."
            )

        else:

            # ================================================
            # VERIFICAR DUPLICIDADE
            # ================================================

            cursor.execute("""
                SELECT
                    id
                FROM exercicios
                WHERE LOWER(nome) = LOWER(?)
                  AND id <> ?
                  AND (
                      responsavel_id IS NULL
                      OR responsavel_id = ?
                  )
            """, (
                nome,
                exercicio_id,
                session["usuario_id"]
            ))

            duplicado = cursor.fetchone()

            if duplicado:

                erro = (
                    "Já existe outro exercício "
                    "com este nome na sua biblioteca."
                )

            else:

                cursor.execute("""
                    UPDATE exercicios
                    SET
                        nome = ?,
                        grupo_muscular = ?,
                        video_url = ?
                    WHERE id = ?
                """, (
                    nome,
                    grupo_muscular,
                    video_url if video_url else None,
                    exercicio_id
                ))

                conn.commit()

                conn.close()

                return redirect(
                    "/exercicios"
                )

    conn.close()

    return render_template(
        "editar_exercicio.html",
        exercicio=exercicio,
        grupos_musculares=grupos_musculares,
        erro=erro
    )

# ============================================================
# CALCULAR VENCIMENTO DA ASSINATURA
# ============================================================

def calcular_vencimento(data_inicio, quantidade, unidade):

    inicio = date.fromisoformat(data_inicio)

    quantidade = int(quantidade)

    if quantidade < 1:
        raise ValueError("Periodo invalido")

    if unidade == "dias":
        return (
            inicio + timedelta(days=quantidade)
        ).isoformat()

    if unidade == "meses":

        total_meses = (
            inicio.year * 12
            + inicio.month - 1
            + quantidade
        )

        ano = total_meses // 12
        mes = total_meses % 12 + 1

        ultimo_dia = monthrange(ano, mes)[1]

        dia = min(inicio.day, ultimo_dia)

        return date(ano, mes, dia).isoformat()

    raise ValueError("Unidade de periodo invalida")

# ============================================================
# GERENCIAR ASSINATURA DO PERSONAL
# ============================================================

@app.route("/personais/<int:personal_id>/assinatura", methods=["GET", "POST"])
@login_obrigatorio
def gerenciar_assinatura(personal_id):

    if not usuario_e_owner():
        return redirect("/")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nome, usuario
        FROM usuarios
        WHERE id = ?
          AND tipo = 'personal'
          AND responsavel_id = ?
    """, (
        personal_id,
        session["usuario_id"]
    ))

    personal = cursor.fetchone()

    if personal is None:
        conn.close()
        return redirect("/personais")

    cursor.execute("""
        SELECT *
        FROM assinaturas_personais
        WHERE personal_id = ?
    """, (personal_id,))

    assinatura = cursor.fetchone()

    # ========================================================
    # SALVAR ASSINATURA
    # ========================================================

    if request.method == "POST":

        plano = request.form.get("plano", "").strip()
        valor_texto = request.form.get("valor_mensal", "").strip()
        tipo_assinatura = request.form.get(
            "tipo_assinatura", "paga"
        ).strip()

        periodo_quantidade = request.form.get(
            "periodo_quantidade", ""
        ).strip()

        periodo_unidade = request.form.get(
            "periodo_unidade", ""
        ).strip()
        data_inicio = request.form.get("data_inicio", "").strip()
        proximo_vencimento = request.form.get(
            "proximo_vencimento", ""
        ).strip()

        isento = 1 if tipo_assinatura == "isenta" else 0

        motivo_isencao = request.form.get(
            "motivo_isencao", ""
        ).strip()

        observacoes = request.form.get(
            "observacoes", ""
        ).strip()

        try:
            valor = Decimal(valor_texto)

            if not valor.is_finite() or valor < 0:
                raise ValueError("Valor inválido")

            if valor.as_tuple().exponent < -2:
                raise ValueError("Máximo de duas casas decimais")

            if not plano or len(plano) > 100:
                raise ValueError("Plano inválido")

            if len(motivo_isencao) > 500:
                raise ValueError("Motivo muito longo")

            if len(observacoes) > 2000:
                raise ValueError("Observações muito longas")

            from datetime import datetime

            for data in (data_inicio, proximo_vencimento):
                if data:
                    datetime.strptime(data, "%Y-%m-%d")
            if tipo_assinatura not in ("paga", "teste", "isenta"):
                raise ValueError("Tipo de assinatura invalido")

            if periodo_unidade not in ("dias", "meses"):
                raise ValueError("Unidade de periodo invalida")

            quantidade = int(periodo_quantidade)

            if quantidade < 1 or quantidade > 3650:
                raise ValueError("Quantidade invalida")

            if not data_inicio:
                raise ValueError("Data de inicio obrigatoria")

            proximo_vencimento = (
                None if tipo_assinatura == "isenta"
                else calcular_vencimento(
                    data_inicio,
                    quantidade,
                    periodo_unidade
                )
            )

        except (InvalidOperation, ValueError, OverflowError):
            conn.close()
            return "Dados da assinatura inválidos.", 400

        if assinatura:

            cursor.execute("""
                UPDATE assinaturas_personais
                SET plano = ?,
                    valor_mensal = ?,
                    data_inicio = ?,
                    proximo_vencimento = ?,
                    isento = ?,
                    motivo_isencao = ?,
                    observacoes = ?,
                    tipo_assinatura = ?,
                    periodo_quantidade = ?,
                    periodo_unidade = ?
                WHERE id = ?
                  AND personal_id = ?
            """, (
                plano,
                float(valor),
                data_inicio,
                proximo_vencimento,
                isento,
                motivo_isencao,
                observacoes,
                tipo_assinatura,
                quantidade,
                periodo_unidade,
                assinatura["id"],
                personal_id
            ))

        else:

            cursor.execute("""
                INSERT INTO assinaturas_personais (
                    personal_id,
                    plano,
                    valor_mensal,
                    data_inicio,
                    proximo_vencimento,
                    isento,
                    motivo_isencao,
                    observacoes,
                    tipo_assinatura,
                    periodo_quantidade,
                    periodo_unidade
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                personal_id,
                plano,
                float(valor),
                data_inicio,
                proximo_vencimento,
                isento,
                motivo_isencao,
                observacoes,
                tipo_assinatura,
                quantidade,
                periodo_unidade
            ))

        conn.commit()
        conn.close()

        return redirect(
            f"/personais/{personal_id}/assinatura?salvo=1"
        )

    conn.close()

    return render_template(
        "gerenciar_assinatura.html",
        personal=personal,
        assinatura=assinatura,
        hoje=date.today().isoformat()
    )

# ============================================================

# ============================================================
# INICIALIZAR TABELAS FINANCEIRAS
# ============================================================

def inicializar_tabelas_financeiras():

    conn = conectar()

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assinaturas_personais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                personal_id INTEGER NOT NULL UNIQUE,
                plano TEXT NOT NULL,
                valor_mensal REAL,
                data_inicio TEXT,
                proximo_vencimento TEXT,
                isento INTEGER DEFAULT 0,
                motivo_isencao TEXT,
                observacoes TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS pagamentos_personais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assinatura_id INTEGER NOT NULL,
                competencia TEXT,
                valor_pago REAL,
                data_pagamento TEXT,
                forma_pagamento TEXT,
                observacoes TEXT
            )
        """)

        # Migração segura: adiciona campos somente se ainda não existirem.
        colunas = {
            linha[1]
            for linha in conn.execute(
                "PRAGMA table_info(assinaturas_personais)"
            )
        }
        novos_campos = {
            "tipo_assinatura": "TEXT NOT NULL DEFAULT 'paga'",
            "periodo_quantidade": "INTEGER",
            "periodo_unidade": "TEXT",
        }
        for nome, definicao in novos_campos.items():
            if nome not in colunas:
                conn.execute(
                    f"ALTER TABLE assinaturas_personais "
                    f"ADD COLUMN {nome} {definicao}"
                )

        # Registros antigos de parceiros permanecem isentos.
        conn.execute("""
            UPDATE assinaturas_personais
            SET tipo_assinatura = 'isenta'
            WHERE isento = 1
              AND tipo_assinatura = 'paga'
        """)

        criar_tabela_planos(conn)
        conn.commit()

    finally:
        conn.close()


inicializar_tabelas_financeiras()

# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
