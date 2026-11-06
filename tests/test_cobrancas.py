import sqlite3
import unittest

from cobrancas import criar_tabela_cobrancas, registrar_cobranca
from planos import criar_tabela_planos


class TestarCobrancas(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE assinaturas_personais (
                id INTEGER PRIMARY KEY, tipo_assinatura TEXT, isento INTEGER
            )
        """)
        criar_tabela_planos(self.conn)
        criar_tabela_cobrancas(self.conn)
        self.conn.execute(
            "INSERT INTO assinaturas_personais VALUES (1, 'paga', 0)"
        )
        self.conn.execute(
            "INSERT INTO assinaturas_personais VALUES (2, 'isenta', 1)"
        )

    def tearDown(self):
        self.conn.close()

    def test_registra_preco_do_servidor(self):
        cobranca_id = registrar_cobranca(self.conn, 1, 1, "teste-001")
        valor, status = self.conn.execute("""
            SELECT valor_centavos, status FROM cobrancas_assinatura WHERE id = ?
        """, (cobranca_id,)).fetchone()
        self.assertEqual((valor, status), (5000, "pendente"))

    def test_nao_duplica_referencia(self):
        registrar_cobranca(self.conn, 1, 1, "teste-002")
        with self.assertRaises(ValueError):
            registrar_cobranca(self.conn, 1, 1, "teste-002")

    def test_nao_cobra_isento(self):
        with self.assertRaises(ValueError):
            registrar_cobranca(self.conn, 2, 1, "teste-003")

    def test_nao_cobra_plano_inativo(self):
        self.conn.execute("UPDATE planos_assinatura SET ativo = 0 WHERE id = 1")
        with self.assertRaises(ValueError):
            registrar_cobranca(self.conn, 1, 1, "teste-004")

    def test_preco_congelado(self):
        registrar_cobranca(self.conn, 1, 1, "teste-005")
        self.conn.execute("UPDATE planos_assinatura SET preco_centavos = 9000 WHERE id = 1")
        valor = self.conn.execute("""
            SELECT valor_centavos FROM cobrancas_assinatura WHERE referencia = 'teste-005'
        """).fetchone()[0]
        self.assertEqual(valor, 5000)


if __name__ == "__main__":
    unittest.main()
