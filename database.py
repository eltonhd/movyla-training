import sqlite3


def conectar():
    return sqlite3.connect("meutreino.db")


def criar_banco():

    conexao = conectar()
    cursor = conexao.cursor()

    # ==============================
    # EXERCÍCIOS
    # ==============================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exercicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            grupo_muscular TEXT NOT NULL,
            equipamento TEXT,
            repeticoes_min INTEGER,
            repeticoes_max INTEGER,
            incremento_carga REAL
        )
    """)

    # ==============================
    # TREINOS
    # ==============================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS treinos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL
        )
    """)

    # ==============================
    # RELAÇÃO TREINO / EXERCÍCIOS
    # ==============================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS treino_exercicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treino_id INTEGER NOT NULL,
            exercicio_id INTEGER NOT NULL,
            ordem INTEGER NOT NULL,
            FOREIGN KEY (treino_id) REFERENCES treinos(id),
            FOREIGN KEY (exercicio_id) REFERENCES exercicios(id)
        )
    """)

    # ==============================
    # USUÁRIOS
    # ==============================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            usuario TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'aluno',
            ativo INTEGER NOT NULL DEFAULT 1
        )
    """)

    # ==============================
    # TREINOS DOS ALUNOS
    # ==============================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS treino_alunos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            treino_id INTEGER NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (treino_id) REFERENCES treinos(id),
            UNIQUE(usuario_id, treino_id)
        )
    """)

    # ==============================
    # SESSÕES REALIZADAS
    # ==============================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treino_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            FOREIGN KEY (treino_id) REFERENCES treinos(id)
        )
    """)

    # ==============================
    # SÉRIES REALIZADAS
    # ==============================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sessao_id INTEGER NOT NULL,
            exercicio_id INTEGER NOT NULL,
            numero_serie INTEGER NOT NULL,
            carga REAL NOT NULL,
            repeticoes INTEGER NOT NULL,
            rir REAL,
            rpe REAL,
            observacoes TEXT,
            FOREIGN KEY (sessao_id) REFERENCES sessoes(id),
            FOREIGN KEY (exercicio_id) REFERENCES exercicios(id)
        )
    """)

    conexao.commit()
    conexao.close()


if __name__ == "__main__":
    criar_banco()
    print("Banco de dados atualizado com sucesso!")