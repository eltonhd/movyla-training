"""Vincula Orders do Mercado Pago a cobranças internas, sem ativar cobrança real.

Somente o servidor pode registrar IDs recebidos da API autenticada.
"""
import re


def preparar_orders_mercado_pago(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mercado_pago_orders (
            id INTEGER PRIMARY KEY,
            cobranca_id INTEGER NOT NULL UNIQUE,
            order_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'criada',
            criada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(cobranca_id) REFERENCES cobrancas_assinatura(id)
        )
    """)


def vincular_order(conn, cobranca_id, order_id):
    """Impede troca da Order vinculada ou associação a outra cobrança."""
    if type(cobranca_id) is not int or cobranca_id <= 0:
        raise ValueError("Cobrança inválida.")
    if not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", order_id):
        raise ValueError("Order ID inválido.")
    preparar_orders_mercado_pago(conn)
    conn.execute("SAVEPOINT movyla_vincular_order")
    try:
        cobranca = conn.execute("""
            SELECT status FROM cobrancas_assinatura WHERE id = ?
        """, (cobranca_id,)).fetchone()
        if cobranca is None or cobranca[0] != "pendente":
            raise ValueError("Apenas cobranças pendentes aceitam nova Order.")
        atual = conn.execute("""
            SELECT order_id FROM mercado_pago_orders WHERE cobranca_id = ?
        """, (cobranca_id,)).fetchone()
        if atual is not None:
            if atual[0] != order_id:
                raise ValueError("Cobrança já vinculada a outra Order.")
            conn.execute("RELEASE SAVEPOINT movyla_vincular_order")
            return False
        conn.execute("""
            INSERT INTO mercado_pago_orders(cobranca_id, order_id)
            VALUES (?, ?)
        """, (cobranca_id, order_id))
        conn.execute("RELEASE SAVEPOINT movyla_vincular_order")
        return True
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT movyla_vincular_order")
        conn.execute("RELEASE SAVEPOINT movyla_vincular_order")
        raise


def localizar_cobranca_por_order(conn, order_id):
    """Busca vínculo persistido; nunca confia em cobranca_id enviado por webhook."""
    if not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", order_id):
        raise ValueError("Order ID inválido.")
    registro = conn.execute("""
        SELECT cobranca_id FROM mercado_pago_orders WHERE order_id = ?
    """, (order_id,)).fetchone()
    return registro[0] if registro else None
