import sqlite3
import unittest

from cobrancas import criar_tabela_cupons, consultar_desconto


class TestarCupons(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        criar_tabela_cupons(self.conn)
        self.conn.execute("""
            INSERT INTO cupons_assinatura
                (codigo, desconto_centavos, personal_id, plano_id)
            VALUES ('ALE20', 2000, 7, 2)
        """)

    def tearDown(self):
        self.conn.close()

    def test_desconto_autorizado(self):
        self.assertEqual(consultar_desconto(self.conn, "ale20", 7, 2, 12000), 2000)

    def test_restricao_personal(self):
        with self.assertRaises(ValueError):
            consultar_desconto(self.conn, "ALE20", 8, 2, 12000)

    def test_restricao_plano(self):
        with self.assertRaises(ValueError):
            consultar_desconto(self.conn, "ALE20", 7, 1, 5000)

    def test_cupom_utilizado(self):
        self.conn.execute("""
            UPDATE cupons_assinatura SET usado_em = '2026-10-13' WHERE codigo = 'ALE20'
        """)
        with self.assertRaises(ValueError):
            consultar_desconto(self.conn, "ALE20", 7, 2, 12000)

    def test_desconto_nao_excede_preco(self):
        self.assertEqual(consultar_desconto(self.conn, "ALE20", 7, 2, 1000), 1000)


if __name__ == "__main__":
    unittest.main()
