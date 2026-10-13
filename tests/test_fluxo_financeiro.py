"""Testes da integração inicial do catálogo e registro de cobranças."""
import sqlite3
import unittest

from planos import criar_tabela_planos
from cobrancas import criar_tabela_cobrancas, registrar_cobranca


class TesteFluxoFinanceiro(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE assinaturas_personais (
                id INTEGER PRIMARY KEY,
                tipo_assinatura TEXT NOT NULL,
                isento INTEGER NOT NULL DEFAULT 0
            )
        """)
        criar_tabela_planos(self.conn)
        criar_tabela_cobrancas(self.conn)
        self.conn.execute(
            "INSERT INTO assinaturas_personais (id, tipo_assinatura, isento) "
            "VALUES (10, 'paga', 0), (11, 'teste', 0), (12, 'isenta', 1)"
        )

    def tearDown(self):
        self.conn.close()

    def test_tres_periodos(self):
        for plano_id, preco in [(1, 5000), (2, 12000), (3, 25000)]:
            referencia = f"plano-{plano_id}"
            registrar_cobranca(self.conn, 10, plano_id, referencia)
            encontrado = self.conn.execute(
                "SELECT valor_centavos, status FROM cobrancas_assinatura "
                "WHERE referencia = ?", (referencia,)
            ).fetchone()
            self.assertEqual(encontrado, (preco, "pendente"))

    def test_teste_gratuito_nao_e_cobrado(self):
        with self.assertRaises(ValueError):
            registrar_cobranca(self.conn, 11, 1, "teste-gratis")

    def test_isento_nao_e_cobrado(self):
        with self.assertRaises(ValueError):
            registrar_cobranca(self.conn, 12, 1, "parceiro-isento")


if __name__ == "__main__":
    unittest.main()
