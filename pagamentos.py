"""Orquestra confirmação validada e renovação na mesma transação SQLite."""
from cobrancas import registrar_confirmacao_verificada
from renovacoes import aplicar_renovacao_confirmada


def confirmar_e_renovar(conn, cobranca_id, identificador_externo, hoje=None):
    """Uso exclusivo após validação do pagamento pelo provedor.

    Retorna (vencimento, renovacao_aplicada). A transação é responsabilidade
    do chamador, que deve realizar commit apenas após sucesso.
    """
    conn.execute("SAVEPOINT movyla_pagamento_completo")
    try:
        registrar_confirmacao_verificada(conn, cobranca_id, identificador_externo)
        vencimento, aplicada = aplicar_renovacao_confirmada(
            conn, cobranca_id, hoje=hoje
        )
        conn.execute("RELEASE SAVEPOINT movyla_pagamento_completo")
        return vencimento, aplicada
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT movyla_pagamento_completo")
        conn.execute("RELEASE SAVEPOINT movyla_pagamento_completo")
        raise
