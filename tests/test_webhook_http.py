"""Testes HTTP da rota webhook com Flask isolado e mocks."""
import ast
import hashlib
import hmac
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask, request


class TestarWebhookHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fonte = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(
            encoding="utf-8"
        )
        arvore = ast.parse(fonte)
        rota = next(n for n in arvore.body if isinstance(n, ast.FunctionDef)
                    and n.name == "webhook_orders_mercado_pago")
        modulo = ast.Module(body=[rota], type_ignores=[])
        # Retira apenas o decorador Flask da função isolada.
        rota.decorator_list = []
        cls.app = Flask(__name__)
        ambiente = {
            "os": __import__("os"), "request": request,
            "validar_assinatura_webhook": __import__(
                "webhook_mercado_pago"
            ).validar_assinatura_webhook,
            "app": cls.app,
        }
        exec(compile(modulo, "<webhook-test>", "exec"), ambiente)
        cls.app.add_url_rule("/webhook", view_func=ambiente["webhook_orders_mercado_pago"],
                             methods=["POST"])
        cls.ambiente = ambiente

    def setUp(self):
        self.cliente = self.app.test_client()
        self.flag = patch.dict("os.environ", {
            "MOVYLA_WEBHOOK_TESTE_HABILITADO": "1",
            "MERCADO_PAGO_WEBHOOK_SECRET": "segredo",
        })
        self.flag.start()

    def tearDown(self):
        self.flag.stop()

    def assinatura(self, order_id="ORD123"):
        ts = str(int(time.time()))
        manifesto = f"id:{order_id};request-id:req-1;ts:{ts};"
        digest = hmac.new(b"segredo", manifesto.encode(), hashlib.sha256).hexdigest()
        return {"x-signature": f"ts={ts},v1={digest}", "x-request-id": "req-1"}

    def test_recusa_assinatura_invalida(self):
        resposta = self.cliente.post("/webhook", json={"data": {"id": "ORD123"}},
                                    headers={"x-signature": "invalida"})
        self.assertEqual(resposta.status_code, 401)

    def test_recusa_id_nao_textual(self):
        resposta = self.cliente.post("/webhook", json={"data": {"id": 123}})
        self.assertEqual(resposta.status_code, 400)

    def test_recusa_corpo_grande(self):
        resposta = self.cliente.post("/webhook", data="x" * 17000,
                                    content_type="application/json")
        self.assertEqual(resposta.status_code, 413)

    def test_notificacao_valida_sem_vinculo_nao_liquida(self):
        banco = Mock()
        banco.execute.return_value.fetchone.return_value = None
        self.ambiente["conectar"] = Mock(return_value=banco)
        resposta = self.cliente.post("/webhook", json={"data": {"id": "ORD123"}},
                                    headers=self.assinatura())
        self.assertEqual(resposta.status_code, 202)
        banco.close.assert_called_once()

    def test_notificacao_repetida_consulta_sem_liquidar(self):
        banco = Mock()
        banco.execute.return_value.fetchone.return_value = {"cobranca_id": 7}
        self.ambiente["conectar"] = Mock(return_value=banco)
        conferir = Mock(return_value=Mock(cobranca_id=7))
        self.ambiente["conferir_order_autenticada"] = conferir
        for _ in range(2):
            resposta = self.cliente.post("/webhook", json={"data": {"id": "ORD123"}},
                                        headers=self.assinatura())
            self.assertEqual(resposta.status_code, 200)
        self.assertEqual(conferir.call_count, 2)
        banco.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
