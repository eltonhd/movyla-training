"""Testes de regressão para os cálculos de vencimento do MOVYLA.

Executar: python -m unittest discover -s tests -v
A função é extraída por AST para não inicializar o banco ao importar app.py.
"""
import ast
import unittest
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path


def carregar_calcular_vencimento():
    codigo = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
    arvore = ast.parse(codigo)
    funcao = next(
        node for node in arvore.body
        if isinstance(node, ast.FunctionDef) and node.name == "calcular_vencimento"
    )
    modulo = ast.fix_missing_locations(ast.Module(body=[funcao], type_ignores=[]))
    contexto = {"date": date, "timedelta": timedelta, "monthrange": monthrange}
    exec(compile(modulo, "app.py", "exec"), contexto)
    return contexto["calcular_vencimento"]


class TestarVencimento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calcular = staticmethod(carregar_calcular_vencimento())

    def test_dias(self):
        self.assertEqual(self.calcular("2026-10-13", 30, "dias"), "2026-11-12")

    def test_mes_com_dia_31(self):
        self.assertEqual(self.calcular("2026-01-31", 1, "meses"), "2026-02-28")

    def test_fevereiro_bissexto(self):
        self.assertEqual(self.calcular("2024-01-31", 1, "meses"), "2024-02-29")

    def test_virada_de_ano(self):
        self.assertEqual(self.calcular("2026-12-15", 2, "meses"), "2027-02-15")

    def test_periodo_invalido(self):
        for quantidade in (0, -1):
            with self.subTest(quantidade=quantidade):
                with self.assertRaises(ValueError):
                    self.calcular("2026-10-13", quantidade, "dias")

    def test_unidade_invalida(self):
        with self.assertRaises(ValueError):
            self.calcular("2026-10-13", 1, "semanas")


if __name__ == "__main__":
    unittest.main()
