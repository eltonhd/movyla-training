"""Testes da consulta financeira: nenhum personal pode ver cobranças de outro."""
import ast
import pathlib
import sqlite3
import unittest

from cobrancas import criar_tabela_cobrancas
from planos import criar_tabela_planos
from orders_mercado_pago import preparar_vinculos_orders, vincular_order


def carregar_consulta():
    fonte = pathlib.Path(__file__).resolve().parents[1] / "app.py"
    arvore = ast.parse(fonte.read_text(encoding="utf-8"))
    funcao = next(
        node for node in arvore.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "obter_resumo_financeiro_personal"
    )
    modulo = ast.Module(body=[funcao], type_ignores=[])
    namespace = {}
    exec(compile(modulo, str(fonte), "exec"), namespace)
    return namespace["obter_resumo_financeiro_personal"]


class TestarIsolamentoFinanceiro(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE assinaturas_personais (
                id INTEGER PRIMARY KEY, personal_id INTEGER UNIQUE,
                plano TEXT, tipo_assinatura TEXT, isento INTEGER,
                proximo_vencimento TEXT
            )
        """)
        self.conn.executemany("""
            INSERT INTO assinaturas_personais
                (id, personal_id, plano, tipo_assinatura, isento, proximo_vencimento)
            VALUES (?, ?, 'mensal', 'paga', 0, '2026-12-01')
        """, [(1, 11), (2, 22)])
        criar_tabela_planos(self.conn)
        criar_tabela_cobrancas(self.conn)
        self.conn.executemany("""
            INSERT INTO cobrancas_assinatura
                (assinatura_id, plano_id, referencia, valor_centavos,
                 periodo_meses, status, criada_em)
            VALUES (?, 1, ?, 5000, 1, 'pendente', '2026-10-13')
        """, [(1, "somente-11"), (2, "somente-22")])
        self.conn.execute("""
            ALTER TABLE cobrancas_assinatura
            ADD COLUMN desconto_centavos INTEGER DEFAULT 0
        """)
        preparar_vinculos_orders(self.conn)
        vincular_order(self.conn, 1, "ORD-11", "action_required")
        vincular_order(self.conn, 2, "ORD-22", "action_required")
        self.consultar = carregar_consulta()

    def tearDown(self):
        self.conn.close()

    def test_personal_11_so_ve_proprios_dados(self):
        assinatura, cobrancas = self.consultar(self.conn, 11)
        self.assertEqual(assinatura["id"], 1)
        self.assertEqual([x["referencia"] for x in cobrancas], ["somente-11"])
        self.assertEqual(cobrancas[0]["mercado_pago_order_id"], "ORD-11")

    def test_personal_22_so_ve_proprios_dados(self):
        assinatura, cobrancas = self.consultar(self.conn, 22)
        self.assertEqual(assinatura["id"], 2)
        self.assertEqual([x["referencia"] for x in cobrancas], ["somente-22"])
        self.assertEqual(cobrancas[0]["mercado_pago_order_id"], "ORD-22")

    def test_sem_assinatura_nao_ve_cobrancas(self):
        assinatura, cobrancas = self.consultar(self.conn, 999)
        self.assertIsNone(assinatura)
        self.assertEqual(cobrancas, [])


if __name__ == "__main__":
    unittest.main()
