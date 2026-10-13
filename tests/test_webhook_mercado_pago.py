"""Testes de autenticação HMAC do webhook sem comunicação externa."""
import hashlib
import hmac
import time
import unittest
from unittest.mock import patch

from webhook_mercado_pago import validar_assinatura_webhook


class TestarAssinaturaWebhook(unittest.TestCase):
    def assinatura(self, secret="segredo", request_id="req-1", data_id="ORD123", ts=None):
        ts = str(int(time.time()) if ts is None else ts)
        manifesto = f"id:{data_id};request-id:{request_id};ts:{ts};"
        digest = hmac.new(secret.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
        return f"ts={ts},v1={digest}"

    def test_assinatura_valida(self):
        self.assertTrue(validar_assinatura_webhook(
            "segredo", self.assinatura(), "req-1", "ORD123"
        ))

    def test_assinatura_adulterada(self):
        self.assertFalse(validar_assinatura_webhook(
            "segredo", self.assinatura(), "req-1", "ORD999"
        ))

    def test_rejeita_request_id_divergente(self):
        self.assertFalse(validar_assinatura_webhook(
            "segredo", self.assinatura(), "outro", "ORD123"
        ))

    def test_rejeita_timestamp_expirado(self):
        self.assertFalse(validar_assinatura_webhook(
            "segredo", self.assinatura(ts=int(time.time()) - 3600),
            "req-1", "ORD123"
        ))

    def test_rejeita_cabecalho_malformado(self):
        self.assertFalse(validar_assinatura_webhook(
            "segredo", "ts=123,v1=invalido", "req-1", "ORD123"
        ))

    def test_rejeita_duplicidade_de_campo(self):
        sig = self.assinatura()
        self.assertFalse(validar_assinatura_webhook(
            "segredo", sig + ",ts=1234567890", "req-1", "ORD123"
        ))


if __name__ == "__main__":
    unittest.main()
