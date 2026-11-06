"""Registro de cobranças MOVYLA; nenhuma cobrança real é efetuada aqui."""
import sqlite3
from datetime import datetime, timezone


def criar_tabela_cobrancas(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cobrancas_assinatura (
            id INTEGER PRIMARY KEY,
            assinatura_id INTEGER NOT NULL,
            plano_id INTEGER NOT NULL,
            referencia TEXT NOT NULL UNIQUE,
            valor_centavos INTEGER NOT NULL CHECK(valor_centavos > 0),
            periodo_meses INTEGER NOT NULL CHECK(periodo_meses > 0),
            status TEXT NOT NULL DEFAULT 'pendente'
                CHECK(status IN ('pendente', 'paga', 'cancelada', 'expirada')),
            identificador_externo TEXT UNIQUE,
            criada_em TEXT NOT NULL,
            paga_em TEXT,
            FOREIGN KEY(assinatura_id) REFERENCES assinaturas_personais(id),
            FOREIGN KEY(plano_id) REFERENCES planos_assinatura(id)
        )
    """)


def registrar_cobranca(conn, assinatura_id, plano_id, referencia):
    """Congela o preço do plano no momento da criação, sem confirmar pagamento."""
    plano = conn.execute("""
        SELECT periodo_meses, preco_centavos FROM planos_assinatura
        WHERE id = ? AND ativo = 1
    """, (plano_id,)).fetchone()
    if plano is None or plano[1] <= 0:
        raise ValueError("Plano inválido ou indisponível.")
    assinatura = conn.execute("""
        SELECT id FROM assinaturas_personais
        WHERE id = ? AND COALESCE(isento, 0) = 0
          AND COALESCE(tipo_assinatura, 'paga') = 'paga'
    """, (assinatura_id,)).fetchone()
    if assinatura is None:
        raise ValueError("Assinatura não pode ser cobrada.")
    if not referencia or len(referencia) > 120:
        raise ValueError("Referência inválida.")
    try:
        cursor = conn.execute("""
            INSERT INTO cobrancas_assinatura
                (assinatura_id, plano_id, referencia, valor_centavos,
                 periodo_meses, criada_em)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (assinatura_id, plano_id, referencia, plano[1], plano[0],
              datetime.now(timezone.utc).isoformat()))
    except sqlite3.IntegrityError as exc:
        raise ValueError("Referência já utilizada.") from exc
    return cursor.lastrowid


def criar_tabela_cupons(conn):
    """Prepara cupons de valor fixo com uso único, sem aplicá-los a cobranças."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cupons_assinatura (
            id INTEGER PRIMARY KEY,
            codigo TEXT NOT NULL UNIQUE,
            desconto_centavos INTEGER NOT NULL CHECK(desconto_centavos > 0),
            personal_id INTEGER,
            plano_id INTEGER,
            ativo INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0, 1)),
            usado_em TEXT,
            cobranca_id INTEGER UNIQUE
        )
    """)
    colunas = {col[1] for col in conn.execute("PRAGMA table_info(cupons_assinatura)")}
    if "administrador_id" not in colunas:
        conn.execute("ALTER TABLE cupons_assinatura ADD COLUMN administrador_id INTEGER")


def preparar_descontos_cobrancas(conn):
    """Migração aditiva: preserva o valor original e o total após desconto."""
    colunas = {item[1] for item in conn.execute(
        "PRAGMA table_info(cobrancas_assinatura)"
    )}
    if "valor_original_centavos" not in colunas:
        conn.execute(
            "ALTER TABLE cobrancas_assinatura ADD COLUMN valor_original_centavos INTEGER"
        )
    if "desconto_centavos" not in colunas:
        conn.execute(
            "ALTER TABLE cobrancas_assinatura ADD COLUMN desconto_centavos INTEGER NOT NULL DEFAULT 0"
        )
    conn.execute("""
        UPDATE cobrancas_assinatura
        SET valor_original_centavos = valor_centavos
        WHERE valor_original_centavos IS NULL
    """)


def registrar_cobranca_com_cupom(conn, assinatura_id, plano_id, referencia,
                                codigo, personal_id, administrador_id):
    """Reserva cupom na cobrança pendente; não confirma nem liquida pagamento."""
    criar_tabela_cupons(conn)
    preparar_descontos_cobrancas(conn)
    conn.execute("SAVEPOINT movyla_reserva_cupom")
    try:
        cobranca_id = registrar_cobranca(
            conn, assinatura_id, plano_id, referencia
        )
        original = conn.execute("""
            SELECT valor_centavos FROM cobrancas_assinatura WHERE id = ?
        """, (cobranca_id,)).fetchone()[0]
        desconto = consultar_desconto(
            conn, codigo, personal_id, plano_id, original, administrador_id
        )
        if desconto >= original:
            raise ValueError("Cupom de desconto integral exige fluxo gratuito separado.")
        cursor = conn.execute("""
            UPDATE cupons_assinatura SET cobranca_id = ?
            WHERE codigo = ? AND cobranca_id IS NULL
              AND usado_em IS NULL AND ativo = 1 AND administrador_id = ?
        """, (cobranca_id, codigo.strip().upper(), administrador_id))
        if cursor.rowcount != 1:
            raise ValueError("Cupom já reservado ou indisponível.")
        conn.execute("""
            UPDATE cobrancas_assinatura
            SET valor_original_centavos = ?, desconto_centavos = ?,
                valor_centavos = ?
            WHERE id = ?
        """, (original, desconto, original - desconto, cobranca_id))
        conn.execute("RELEASE SAVEPOINT movyla_reserva_cupom")
        return cobranca_id
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT movyla_reserva_cupom")
        conn.execute("RELEASE SAVEPOINT movyla_reserva_cupom")
        raise


def cancelar_cobranca_pendente(conn, cobranca_id):
    """Cancela uma cobrança pendente e libera seu cupom sem tocar em pagamentos."""
    conn.execute("SAVEPOINT movyla_cancelamento")
    try:
        cursor = conn.execute("""
            UPDATE cobrancas_assinatura
            SET status = 'cancelada'
            WHERE id = ? AND status = 'pendente'
        """, (cobranca_id,))
        if cursor.rowcount != 1:
            raise ValueError("Cobrança inexistente ou não está pendente.")
        conn.execute("""
            UPDATE cupons_assinatura
            SET cobranca_id = NULL
            WHERE cobranca_id = ? AND usado_em IS NULL
        """, (cobranca_id,))
        conn.execute("RELEASE SAVEPOINT movyla_cancelamento")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT movyla_cancelamento")
        conn.execute("RELEASE SAVEPOINT movyla_cancelamento")
        raise


def expirar_cobranca_pendente(conn, cobranca_id):
    """Expira uma cobrança pendente e libera reserva de cupom não utilizado."""
    conn.execute("SAVEPOINT movyla_expiracao")
    try:
        cursor = conn.execute("""
            UPDATE cobrancas_assinatura SET status = 'expirada'
            WHERE id = ? AND status = 'pendente'
        """, (cobranca_id,))
        if cursor.rowcount != 1:
            raise ValueError("Cobrança inexistente ou não está pendente.")
        conn.execute("""
            UPDATE cupons_assinatura SET cobranca_id = NULL
            WHERE cobranca_id = ? AND usado_em IS NULL
        """, (cobranca_id,))
        conn.execute("RELEASE SAVEPOINT movyla_expiracao")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT movyla_expiracao")
        conn.execute("RELEASE SAVEPOINT movyla_expiracao")
        raise


def registrar_confirmacao_verificada(conn, cobranca_id, identificador_externo):
    """Registra confirmação já validada pelo provedor; não autentica webhooks."""
    if not isinstance(identificador_externo, str) or not identificador_externo.strip():
        raise ValueError("Identificador externo obrigatório.")
    identificador_externo = identificador_externo.strip()
    if len(identificador_externo) > 180:
        raise ValueError("Identificador externo muito longo.")
    conn.execute("SAVEPOINT movyla_confirmacao")
    try:
        registro = conn.execute("""
            SELECT status, identificador_externo FROM cobrancas_assinatura
            WHERE id = ?
        """, (cobranca_id,)).fetchone()
        if registro is None:
            raise ValueError("Cobrança não encontrada.")
        if registro[0] == "paga":
            if registro[1] == identificador_externo:
                conn.execute("RELEASE SAVEPOINT movyla_confirmacao")
                return False
            raise ValueError("Cobrança já confirmada com outra identificação.")
        if registro[0] != "pendente":
            raise ValueError("Cobrança não está pendente.")
        instante = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute("""
            UPDATE cobrancas_assinatura
            SET status = 'paga', identificador_externo = ?, paga_em = ?
            WHERE id = ? AND status = 'pendente'
        """, (identificador_externo, instante, cobranca_id))
        if cursor.rowcount != 1:
            raise ValueError("Cobrança já processada.")
        conn.execute("""
            UPDATE cupons_assinatura SET usado_em = ?
            WHERE cobranca_id = ? AND usado_em IS NULL
        """, (instante, cobranca_id))
        conn.execute("RELEASE SAVEPOINT movyla_confirmacao")
        return True
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT movyla_confirmacao")
        conn.execute("RELEASE SAVEPOINT movyla_confirmacao")
        raise


def consultar_desconto(conn, codigo, personal_id, plano_id, preco_centavos, administrador_id=None):
    """Calcula o desconto elegível sem consumir o cupom."""
    if not isinstance(codigo, str) or not codigo.strip():
        raise ValueError("Cupom inválido.")
    cupom = conn.execute("""
        SELECT desconto_centavos, personal_id, plano_id, administrador_id
        FROM cupons_assinatura
        WHERE codigo = ? AND ativo = 1 AND usado_em IS NULL
          AND cobranca_id IS NULL
    """, (codigo.strip().upper(),)).fetchone()
    if cupom is None:
        raise ValueError("Cupom indisponível.")
    if administrador_id is not None and cupom[3] != administrador_id:
        raise ValueError('Cupom de outro administrador.')
    if cupom[1] is not None and cupom[1] != personal_id:
        raise ValueError("Cupom restrito a outro personal.")
    if cupom[2] is not None and cupom[2] != plano_id:
        raise ValueError("Cupom restrito a outro plano.")
    if not isinstance(preco_centavos, int) or preco_centavos <= 0:
        raise ValueError("Preço inválido.")
    return min(cupom[0], preco_centavos)
