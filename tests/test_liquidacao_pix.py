"""Testes do limite de confiança da liquidação Pix, sem gateway real."""
import sqlite3
import unittest
from unittest.mock import patch

from liquidacao_pix import PagamentoVerificado, liquidar_pagamento_verificado


class TestarLiquidacaoPix(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE cobrancas_assinatura (
                id INTEGER PRIMARY KEY, valor_centavos INTEGER NOT NULL,
                status TEXT, identificador_externo TEXT
            )
        """)
        self.conn.execute("""
            INSERT INTO cobrancas_assinatura
            (id, valor_centavos, status) VALUES (1, 5000, 'pendente')
        """)

    def tearDown(self):
        self.conn.close()

    def pagamento(self, **campos):
        dados = dict(
            cobranca_id=1, identificador_externo="pix-confirmado-1",
            valor_centavos=5000, moeda="BRL", status="aprovado"
        )
        dados.update(campos)
        return PagamentoVerificado(**dados)

    def test_aceita_pagamento_correspondente(self):
        with patch("liquidacao_pix.confirmar_e_renovar", return_value=("2026-11-13", True)) as renovar:
            resultado = liquidar_pagamento_verificado(self.conn, self.pagamento())
        self.assertEqual(resultado, ("2026-11-13", True))
        renovar.assert_called_once()

    def test_recusa_valor_divergente(self):
        with self.assertRaisesRegex(ValueError, "Valor pago"):
            liquidar_pagamento_verificado(self.conn, self.pagamento(valor_centavos=4900))

    def test_recusa_moeda_divergente(self):
        with self.assertRaisesRegex(ValueError, "Moeda"):
            liquidar_pagamento_verificado(self.conn, self.pagamento(moeda="USD"))

    def test_recusa_pagamento_nao_aprovado(self):
        with self.assertRaisesRegex(ValueError, "não aprovado"):
            liquidar_pagamento_verificado(self.conn, self.pagamento(status="pendente"))

    def test_recusa_cobranca_cancelada(self):
        self.conn.execute("UPDATE cobrancas_assinatura SET status = 'cancelada' WHERE id = 1")
        with self.assertRaisesRegex(ValueError, "não está apta"):
            liquidar_pagamento_verificado(self.conn, self.pagamento())

    def test_recusa_identificador_diferente_em_repeticao(self):
        self.conn.execute("""
            UPDATE cobrancas_assinatura
            SET status = 'paga', identificador_externo = 'pix-original' WHERE id = 1
        """)
        with self.assertRaisesRegex(ValueError, "divergente"):
            liquidar_pagamento_verificado(self.conn, self.pagamento())

    def test_recusa_objeto_nao_verificado(self):
        with self.assertRaisesRegex(ValueError, "não foi verificado"):
            liquidar_pagamento_verificado(self.conn, {"status": "aprovado"})


if __name__ == "__main__":
    unittest.main()
