"""Testes do vínculo de Orders sem acesso à API do Mercado Pago."""
import sqlite3
import unittest

from orders_mercado_pago import preparar_vinculos_orders, vincular_order


class TestarVinculosOrders(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE cobrancas_assinatura (
                id INTEGER PRIMARY KEY, status TEXT NOT NULL
            )
        """)
        self.conn.executemany("""
            INSERT INTO cobrancas_assinatura (id, status) VALUES (?, ?)
        """, [(1, "pendente"), (2, "pendente"), (3, "cancelada")])
        preparar_vinculos_orders(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_vincula_order_a_cobranca(self):
        self.assertTrue(vincular_order(self.conn, 1, "ORD-123", "action_required"))
        self.assertEqual(self.conn.execute(
            "SELECT order_id FROM orders_mercado_pago WHERE cobranca_id = 1"
        ).fetchone()[0], "ORD-123")

    def test_repeticao_da_mesma_order_e_idempotente(self):
        vincular_order(self.conn, 1, "ORD-123", "action_required")
        self.assertFalse(vincular_order(self.conn, 1, "ORD-123", "action_required"))

    def test_nao_troca_order_de_uma_cobranca(self):
        vincular_order(self.conn, 1, "ORD-123", "action_required")
        with self.assertRaisesRegex(ValueError, "outra Order"):
            vincular_order(self.conn, 1, "ORD-456", "action_required")

    def test_nao_reutiliza_order_em_outra_cobranca(self):
        vincular_order(self.conn, 1, "ORD-123", "action_required")
        with self.assertRaisesRegex(ValueError, "outra cobrança"):
            vincular_order(self.conn, 2, "ORD-123", "action_required")

    def test_nao_vincula_cobranca_cancelada(self):
        with self.assertRaisesRegex(ValueError, "pendentes"):
            vincular_order(self.conn, 3, "ORD-789", "action_required")


if __name__ == "__main__":
    unittest.main()
