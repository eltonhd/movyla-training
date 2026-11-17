"""Testes do vínculo local Order-Cobrança; nenhuma API externa."""
import sqlite3
import unittest

from mercado_pago_orders import (
    preparar_orders_mercado_pago, vincular_order, localizar_cobranca_por_order
)


class TestarVinculoOrders(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE cobrancas_assinatura (
                id INTEGER PRIMARY KEY, status TEXT NOT NULL
            )
        """)
        self.conn.executemany(
            "INSERT INTO cobrancas_assinatura(id,status) VALUES (?,?)",
            [(1, "pendente"), (2, "pendente"), (3, "paga")]
        )
        preparar_orders_mercado_pago(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_vinculo_e_consulta(self):
        self.assertTrue(vincular_order(self.conn, 1, "ORD-123"))
        self.assertEqual(localizar_cobranca_por_order(self.conn, "ORD-123"), 1)

    def test_repeticao_mesma_order_e_idempotente(self):
        vincular_order(self.conn, 1, "ORD-123")
        self.assertFalse(vincular_order(self.conn, 1, "ORD-123"))

    def test_impede_troca_de_order(self):
        vincular_order(self.conn, 1, "ORD-123")
        with self.assertRaisesRegex(ValueError, "outra Order"):
            vincular_order(self.conn, 1, "ORD-456")

    def test_impede_order_em_outra_cobranca(self):
        vincular_order(self.conn, 1, "ORD-123")
        with self.assertRaises(sqlite3.IntegrityError):
            vincular_order(self.conn, 2, "ORD-123")

    def test_impede_vinculo_de_cobranca_paga(self):
        with self.assertRaises(ValueError):
            vincular_order(self.conn, 3, "ORD-123")

    def test_order_desconhecida_nao_encontra_cobranca(self):
        self.assertIsNone(localizar_cobranca_por_order(self.conn, "ORD-999"))


if __name__ == "__main__":
    unittest.main()
