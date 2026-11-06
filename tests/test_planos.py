import sqlite3
import unittest

from planos import criar_tabela_planos, listar_planos


class TestarPlanos(unittest.TestCase):
    def setUp(self):
        self.conexao = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conexao.close()

    def test_catalogo_inicial(self):
        criar_tabela_planos(self.conexao)
        planos = listar_planos(self.conexao)
        self.assertEqual(
            [(p[1], p[3], p[4]) for p in planos],
            [("mensal", 1, 5000), ("trimestral", 3, 12000), ("semestral", 6, 25000)],
        )

    def test_inicializacao_repetida_preserva_preco_personalizado(self):
        criar_tabela_planos(self.conexao)
        self.conexao.execute(
            "UPDATE planos_assinatura SET preco_centavos = 5500 WHERE codigo = 'mensal'"
        )
        criar_tabela_planos(self.conexao)
        self.assertEqual(
            self.conexao.execute(
                "SELECT preco_centavos FROM planos_assinatura WHERE codigo = 'mensal'"
            ).fetchone()[0],
            5500,
        )

    def test_inativos_nao_aparecem(self):
        criar_tabela_planos(self.conexao)
        self.conexao.execute(
            "UPDATE planos_assinatura SET ativo = 0 WHERE codigo = 'semestral'"
        )
        self.assertEqual(len(listar_planos(self.conexao)), 2)


if __name__ == "__main__":
    unittest.main()
