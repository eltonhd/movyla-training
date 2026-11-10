"""Offline tests: no Supabase connection or credentials required."""
import unittest
from types import SimpleNamespace

from postgresql_homologacao import LinhaMovyla, fabrica_linhas_movyla, converter_parametros_sqlite


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


class ConversaoSQLTests(unittest.TestCase):
    def test_marcadores_sem_alterar_literais_e_comentarios(self):
        sql = "SELECT '?' AS texto, nome FROM usuarios WHERE id = ? -- ?\\n AND tipo = ?"
        self.assertEqual(
            converter_parametros_sqlite(sql),
            "SELECT '?' AS texto, nome FROM usuarios WHERE id = %s -- ?\\n AND tipo = %s",
        )

    def test_identificadores_e_comentario_bloco(self):
        self.assertEqual(
            converter_parametros_sqlite('SELECT "?" FROM t /* ? */ WHERE x = ?'),
            'SELECT "?" FROM t /* ? */ WHERE x = %s',
        )

    def test_rejeita_comandos_sqlite_incompativeis(self):
        for sql in ("PRAGMA table_info(usuarios)", "BEGIN IMMEDIATE",
                    "INSERT OR IGNORE INTO usuarios VALUES (?)"):
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                converter_parametros_sqlite(sql)

    def test_rejeita_literal_incompleto(self):
        with self.assertRaises(ValueError):
            converter_parametros_sqlite("SELECT 'incompleto")


if __name__ == "__main__":
    unittest.main()
