"""Testes da conferência autenticada de Orders, sem rede bancária."""
import sqlite3
import unittest
from unittest.mock import patch

from conciliacao_orders import conferir_order_autenticada
from orders_mercado_pago import preparar_vinculos_orders, vincular_order


class TestarConciliacaoOrders(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE cobrancas_assinatura (
                id INTEGER PRIMARY KEY, referencia TEXT,
                valor_centavos INTEGER, status TEXT
            )
        """)
        self.conn.execute("""
            INSERT INTO cobrancas_assinatura VALUES
            (1, 'movyla-abc', 5000, 'pendente')
        """)
        preparar_vinculos_orders(self.conn)
        vincular_order(self.conn, 1, "ORD-1", "action_required")
        self.order = {
            "id": "ORD-1", "external_reference": "movyla-abc",
            "currency_id": "BRL", "total_amount": "50.00",
            "status": "processed",
            "transactions": {"payments": [{
                "amount": "50.00", "status": "approved",
                "payment_method": {"id": "pix"}
            }]}
        }

    def tearDown(self):
        self.conn.close()

    def conferir(self, order):
        with patch("conciliacao_orders.consultar_pagamento", return_value=order):
            return conferir_order_autenticada(self.conn, 1)

    def test_order_aprovada_e_identica(self):
        comprovado = self.conferir(self.order)
        self.assertEqual(comprovado.valor_centavos, 5000)
        self.assertEqual(comprovado.status, "aprovado")

    def test_recusa_referencia_divergente(self):
        self.order["external_reference"] = "outra"
        with self.assertRaisesRegex(ValueError, "Referência"):
            self.conferir(self.order)

    def test_recusa_valor_divergente(self):
        self.order["total_amount"] = "49.99"
        with self.assertRaisesRegex(ValueError, "Valor"):
            self.conferir(self.order)

    def test_recusa_moeda_ausente(self):
        self.order.pop("currency_id")
        with self.assertRaisesRegex(ValueError, "Moeda"):
            self.conferir(self.order)

    def test_recusa_pagamento_pendente(self):
        self.order["transactions"]["payments"][0]["status"] = "pending"
        with self.assertRaisesRegex(ValueError, "ainda não confirmado"):
            self.conferir(self.order)

    def test_recusa_metodo_nao_pix(self):
        self.order["transactions"]["payments"][0]["payment_method"]["id"] = "credit_card"
        with self.assertRaisesRegex(ValueError, "Método"):
            self.conferir(self.order)

    def test_recusa_valor_pago_divergente(self):
        self.order["transactions"]["payments"][0]["amount"] = "1.00"
        with self.assertRaisesRegex(ValueError, "Valor pago"):
            self.conferir(self.order)


if __name__ == "__main__":
    unittest.main()
