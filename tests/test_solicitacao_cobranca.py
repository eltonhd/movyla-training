"""Testes da criacao serializada de pedidos de cobranca do personal."""
import ast
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask, request, session, redirect
from cobrancas import criar_tabela_cobrancas, registrar_cobranca
from planos import criar_tabela_planos


def carregar_rota():
    arquivo = pathlib.Path(__file__).resolve().parents[1] / "app.py"
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    funcao = next(
        node for node in arvore.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "solicitar_cobranca_personal"
    )
    funcao.decorator_list = []
    modulo = ast.fix_missing_locations(ast.Module(body=[funcao], type_ignores=[]))
    namespace = {
        "session": session, "request": request, "redirect": redirect,
        "registrar_cobranca": registrar_cobranca,
        "secrets": __import__("secrets"),
        "usuario_e_personal": lambda: session.get("tipo") == "personal",
    }
    exec(compile(modulo, str(arquivo), "exec"), namespace)
    return namespace["solicitar_cobranca_personal"], namespace


class TestarSolicitacaoCobranca(unittest.TestCase):
    def setUp(self):
        self.arquivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.arquivo.close()
        self.app = Flask(__name__)
        self.app.secret_key = "somente-testes"
        conn = sqlite3.connect(self.arquivo.name)
        conn.execute("""
            CREATE TABLE assinaturas_personais (
                id INTEGER PRIMARY KEY, personal_id INTEGER UNIQUE,
                tipo_assinatura TEXT, isento INTEGER
            )
        """)
        conn.executemany("""
            INSERT INTO assinaturas_personais
                (id, personal_id, tipo_assinatura, isento)
            VALUES (?, ?, 'paga', 0)
        """, [(1, 11), (2, 22)])
        criar_tabela_planos(conn)
        criar_tabela_cobrancas(conn)
        conn.commit()
        conn.close()
        self.rota, self.namespace = carregar_rota()
        def conectar():
            conexao = sqlite3.connect(self.arquivo.name)
            conexao.row_factory = sqlite3.Row
            return conexao
        self.namespace["conectar"] = conectar

    def tearDown(self):
        pathlib.Path(self.arquivo.name).unlink(missing_ok=True)

    def solicitar(self, usuario, plano="1", token="valido"):
        with self.app.test_request_context(
            "/minha-assinatura/solicitar", method="POST",
            data={"plano_id": plano, "csrf_token": token}
        ):
            session["usuario_id"] = usuario
            session["tipo"] = "personal"
            session["csrf_financeiro"] = "valido"
            return self.rota()

    def test_pedido_repetido_cria_uma_cobranca(self):
        self.solicitar(11)
        self.solicitar(11)
        conn = self.namespace["conectar"]()
        try:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM cobrancas_assinatura WHERE assinatura_id = 1"
            ).fetchone()[0], 1)
        finally:
            conn.close()

    def test_pedido_de_outro_personal_nao_mistura_contas(self):
        self.solicitar(11)
        self.solicitar(22)
        conn = self.namespace["conectar"]()
        try:
            self.assertEqual(
                conn.execute("""
                    SELECT assinatura_id FROM cobrancas_assinatura ORDER BY assinatura_id
                """).fetchall()[0][0], 1
            )
            self.assertEqual(conn.execute(
                "SELECT COUNT(DISTINCT assinatura_id) FROM cobrancas_assinatura"
            ).fetchone()[0], 2)
        finally:
            conn.close()

    def test_token_invalido_nao_cria_cobranca(self):
        resposta = self.solicitar(11, token="invalido")
        self.assertEqual(resposta[1], 400)
        conn = self.namespace["conectar"]()
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM cobrancas_assinatura").fetchone()[0], 0
            )
        finally:
            conn.close()

    def test_plano_invalido_nao_cria_cobranca(self):
        resposta = self.solicitar(11, plano="999")
        self.assertEqual(resposta[1], 400)


if __name__ == "__main__":
    unittest.main()
