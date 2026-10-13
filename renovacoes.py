"""Renovação de assinaturas confirmadas, com controle contra duplicidade."""
from datetime import date
from calendar import monthrange


def adicionar_meses(data_iso, quantidade):
    inicio = date.fromisoformat(data_iso)
    if not isinstance(quantidade, int) or quantidade < 1:
        raise ValueError("Período inválido.")
    total = inicio.year * 12 + inicio.month - 1 + quantidade
    ano, mes = divmod(total, 12)
    mes += 1
    dia = min(inicio.day, monthrange(ano, mes)[1])
    return date(ano, mes, dia).isoformat()


def preparar_renovacoes(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS renovacoes_assinatura (
            cobranca_id INTEGER PRIMARY KEY,
            assinatura_id INTEGER NOT NULL,
            vencimento_anterior TEXT,
            vencimento_novo TEXT NOT NULL,
            registrada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def aplicar_renovacao_confirmada(conn, cobranca_id, hoje=None):
    """Aplica uma vez a renovação de uma cobrança já marcada como paga.

    Deve ser chamada somente após a verificação externa do pagamento.
    """
    preparar_renovacoes(conn)
    data_atual = date.fromisoformat(hoje) if hoje else date.today()
    conn.execute("SAVEPOINT movyla_renovacao")
    try:
        registro = conn.execute("""
            SELECT c.assinatura_id, c.periodo_meses, a.proximo_vencimento,
                   a.tipo_assinatura, COALESCE(a.isento, 0)
            FROM cobrancas_assinatura c
            JOIN assinaturas_personais a ON a.id = c.assinatura_id
            WHERE c.id = ? AND c.status = 'paga'
        """, (cobranca_id,)).fetchone()
        if registro is None:
            raise ValueError("Cobrança paga e assinatura válida são obrigatórias.")
        assinatura_id, meses, vencimento, tipo, isento = registro
        if tipo != "paga" or isento:
            raise ValueError("Assinatura isenta ou gratuita não pode ser renovada.")
        anterior = conn.execute("""
            SELECT vencimento_novo FROM renovacoes_assinatura WHERE cobranca_id = ?
        """, (cobranca_id,)).fetchone()
        if anterior is not None:
            conn.execute("RELEASE SAVEPOINT movyla_renovacao")
            return anterior[0], False
        base = data_atual
        if vencimento:
            vencimento_data = date.fromisoformat(vencimento)
            if vencimento_data > base:
                base = vencimento_data
        novo = adicionar_meses(base.isoformat(), meses)
        conn.execute("""
            INSERT INTO renovacoes_assinatura
                (cobranca_id, assinatura_id, vencimento_anterior, vencimento_novo)
            VALUES (?, ?, ?, ?)
        """, (cobranca_id, assinatura_id, vencimento, novo))
        conn.execute("""
            UPDATE assinaturas_personais SET proximo_vencimento = ?
            WHERE id = ?
        """, (novo, assinatura_id))
        conn.execute("RELEASE SAVEPOINT movyla_renovacao")
        return novo, True
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT movyla_renovacao")
        conn.execute("RELEASE SAVEPOINT movyla_renovacao")
        raise
