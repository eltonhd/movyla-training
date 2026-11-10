"""Offline tests: no Supabase connection or credentials required."""
import unittest
from types import SimpleNamespace

from postgresql_homologacao import LinhaMovyla, fabrica_linhas_movyla


class LinhaMovylaTests(unittest.TestCase):
    def test_acesso_por_nome_e_indice(self):
        linha = LinhaMovyla((12, "Teste", None), ("id", "nome", "email"))
        self.assertEqual(linha["id"], 12)
        self.assertEqual(linha[0], 12)
        self.assertEqual(linha["nome"], "Teste")
        self.assertIsNone(linha[2])
        self.assertEqual(tuple(linha), (12, "Teste", None))
        self.assertEqual(linha.keys(), ["id", "nome", "email"])

    def test_fabrica_psycopg(self):
        cursor = SimpleNamespace(description=[
            SimpleNamespace(name="usuario_id"),
            SimpleNamespace(name="ativo"),
        ])
        fabrica = fabrica_linhas_movyla(cursor)
        linha = fabrica((5, 1))
        self.assertEqual(linha["usuario_id"], linha[0])
        self.assertEqual(linha["ativo"], 1)


if __name__ == "__main__":
    unittest.main()
