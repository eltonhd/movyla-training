"""Testes de autorização e valores da geração Pix, com API simulada."""
import sqlite3
import unittest
from unittest.mock import patch

from orders_mercado_pago import preparar_vinculos_orders
from servico_pix import gerar_pix_cobranca


class TestarServicoPix(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE assinaturas_personais (
                id INTEGER PRIMARY KEY, personal_id INTEGER,
                tipo_assinatura TEXT, isento INTEGER
            )
        """)
        self.conn.execute("""
            CREATE TABLE cobrancas_assinatura (
                id INTEGER PRIMARY KEY, assinatura_id INTEGER,
                referencia TEXT, valor_centavos INTEGER, status TEXT
            )
        """)
        self.conn.executemany("""
            INSERT INTO assinaturas_personais VALUES (?, ?, 'paga', 0)
        """, [(1, 11), (2, 22)])
        self.conn.executemany("""
            INSERT INTO cobrancas_assinatura VALUES (?, ?, ?, ?, 'pendente')
        """, [(1, 1, "movyla-1", 5000), (2, 2, "movyla-2", 12000)])
        preparar_vinculos_orders(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_gera_pix_com_preco_do_banco(self):
        with patch("servico_pix.criar_pix", return_value={
            "id": "ORD-1", "status": "action_required", "qr_code": "codigo"
        }) as criar:
            resultado = gerar_pix_cobranca(self.conn, 1, 11, "p@example.com")
        self.assertEqual(resultado["qr_code"], "codigo")
        criar.assert_called_once_with(1, "movyla-1", 5000, "p@example.com")

    def test_recusa_acesso_a_cobranca_de_outro_personal(self):
        with patch("servico_pix.criar_pix") as criar:
            with self.assertRaisesRegex(ValueError, "não pertence"):
                gerar_pix_cobranca(self.conn, 2, 11, "p@example.com")
            criar.assert_not_called()

    def test_order_existente_nao_gera_outra(self):
        with patch("servico_pix.criar_pix", return_value={
            "id": "ORD-1", "status": "action_required"
        }):
            gerar_pix_cobranca(self.conn, 1, 11, "p@example.com")
        with patch("servico_pix.criar_pix") as criar, patch(
            "servico_pix.consultar_pagamento", return_value={"id": "ORD-1"}
        ) as consultar:
            retorno = gerar_pix_cobranca(self.conn, 1, 11, "p@example.com")
        self.assertEqual(retorno["id"], "ORD-1")
        criar.assert_not_called()
        consultar.assert_called_once_with("ORD-1")


if __name__ == "__main__":
    unittest.main()
