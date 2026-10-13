"""Testes de integração transacional: Order aprovada renova uma vez."""
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

from conciliacao_orders import reconciliar_order_autenticada
from orders_mercado_pago import preparar_vinculos_orders, vincular_order
from renovacoes import preparar_renovacoes


class TestarRenovacaoOrder(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE assinaturas_personais (
                id INTEGER PRIMARY KEY, personal_id INTEGER,
                proximo_vencimento TEXT, plano TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE cobrancas_assinatura (
                id INTEGER PRIMARY KEY, assinatura_id INTEGER, referencia TEXT,
                valor_centavos INTEGER, periodo_meses INTEGER,
                status TEXT, identificador_externo TEXT, paga_em TEXT
            )
        """)
        self.conn.execute("""
            INSERT INTO assinaturas_personais
            (id, personal_id, proximo_vencimento, plano)
            VALUES (1, 11, '2026-10-20', 'Mensal')
        """)
        self.conn.execute("""
            INSERT INTO cobrancas_assinatura
            (id, assinatura_id, referencia, valor_centavos, periodo_meses, status)
            VALUES (7, 1, 'movyla-7', 5000, 1, 'pendente')
        """)
        preparar_vinculos_orders(self.conn)
        preparar_renovacoes(self.conn)
        vincular_order(self.conn, 7, "ORD-7", "action_required")
        self.conn.commit()
        self.order = {
            "id": "ORD-7", "external_reference": "movyla-7",
            "currency_id": "BRL", "total_amount": "50.00",
            "status": "processed",
            "transactions": {"payments": [{
                "amount": "50.00", "status": "approved",
                "payment_method": {"id": "pix"}
            }]}
        }

    def tearDown(self):
        self.conn.close()

    def test_duplicata_nao_renova_duas_vezes(self):
        with patch("conciliacao_orders.consultar_pagamento", return_value=self.order):
            primeiro = reconciliar_order_autenticada(
                self.conn, 7, hoje=date(2026, 10, 13)
            )
            self.conn.commit()
            segundo = reconciliar_order_autenticada(
                self.conn, 7, hoje=date(2026, 10, 13)
            )
            self.conn.commit()
        self.assertTrue(primeiro[1])
        self.assertFalse(segundo[1])
        self.assertEqual(
            self.conn.execute("SELECT status FROM cobrancas_assinatura WHERE id=7").fetchone()[0],
            "paga"
        )

    def test_pendente_nao_altera_cobranca(self):
        self.order["status"] = "action_required"
        with patch("conciliacao_orders.consultar_pagamento", return_value=self.order):
            with self.assertRaisesRegex(ValueError, "não confirmado"):
                reconciliar_order_autenticada(self.conn, 7)
        self.conn.rollback()
        self.assertEqual(
            self.conn.execute("SELECT status FROM cobrancas_assinatura WHERE id=7").fetchone()[0],
            "pendente"
        )


if __name__ == "__main__":
    unittest.main()
