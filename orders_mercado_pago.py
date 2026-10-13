"""Vínculo seguro entre cobrança interna e Order do Mercado Pago.

Não cria pedidos bancários e não confirma pagamentos.
"""
import sqlite3
from datetime import datetime, timezone


def preparar_vinculos_orders(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders_mercado_pago (
            id INTEGER PRIMARY KEY,
            cobranca_id INTEGER NOT NULL UNIQUE,
            order_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            criada_em TEXT NOT NULL,
            atualizada_em TEXT NOT NULL,
            FOREIGN KEY(cobranca_id) REFERENCES cobrancas_assinatura(id)
        )
    """)


def vincular_order(conn, cobranca_id, order_id, status):
    """Vincula somente uma Order a uma cobrança pendente, com idempotência."""
    if not isinstance(cobranca_id, int) or cobranca_id <= 0:
        raise ValueError("Cobrança inválida.")
    if not isinstance(order_id, str) or not order_id.strip() or len(order_id) > 128:
        raise ValueError("Identificador de Order inválido.")
    if not isinstance(status, str) or not status.strip() or len(status) > 64:
        raise ValueError("Status inválido.")
    conn.execute("SAVEPOINT movyla_vinculo_order")
    try:
        cobranca = conn.execute("""
            SELECT status FROM cobrancas_assinatura WHERE id = ?
        """, (cobranca_id,)).fetchone()
        if cobranca is None or cobranca[0] != "pendente":
            raise ValueError("Somente cobranças pendentes podem receber Orders.")
        existente = conn.execute("""
            SELECT order_id FROM orders_mercado_pago WHERE cobranca_id = ?
        """, (cobranca_id,)).fetchone()
        if existente:
            if existente[0] != order_id:
                raise ValueError("Cobrança já vinculada a outra Order.")
            conn.execute("RELEASE SAVEPOINT movyla_vinculo_order")
            return False
        agora = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO orders_mercado_pago
                (cobranca_id, order_id, status, criada_em, atualizada_em)
            VALUES (?, ?, ?, ?, ?)
        """, (cobranca_id, order_id, status, agora, agora))
        conn.execute("RELEASE SAVEPOINT movyla_vinculo_order")
        return True
    except sqlite3.IntegrityError as erro:
        conn.execute("ROLLBACK TO SAVEPOINT movyla_vinculo_order")
        conn.execute("RELEASE SAVEPOINT movyla_vinculo_order")
        raise ValueError("Order já vinculada a outra cobrança.") from erro
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT movyla_vinculo_order")
        conn.execute("RELEASE SAVEPOINT movyla_vinculo_order")
        raise
