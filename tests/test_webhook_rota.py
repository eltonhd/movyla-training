"""Testes isolados da rota webhook: desabilitada por padrão e sem liquidação."""
import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch


class TestarWebhookRota(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fonte = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(
            encoding="utf-8"
        )
        arvore = ast.parse(fonte)
        rota = next(n for n in arvore.body if isinstance(n, ast.FunctionDef)
                    and n.name == "webhook_orders_mercado_pago")
        cls.fonte_rota = ast.get_source_segment(fonte, rota)

    def test_rota_desabilitada_por_padrao(self):
        self.assertIn('MOVYLA_WEBHOOK_TESTE_HABILITADO', self.fonte_rota)
        self.assertIn('return "", 404', self.fonte_rota)

    def test_exige_segredo_webhook(self):
        self.assertIn('MERCADO_PAGO_WEBHOOK_SECRET', self.fonte_rota)
        self.assertIn('return "", 503', self.fonte_rota)

    def test_exige_assinatura_criptografica(self):
        self.assertIn('validar_assinatura_webhook(', self.fonte_rota)
        self.assertIn('return "", 401', self.fonte_rota)

    def test_nao_renova_assinatura_automaticamente(self):
        self.assertNotIn('liquidar_pagamento_verificado(', self.fonte_rota)
        self.assertNotIn('confirmar_e_renovar(', self.fonte_rota)


if __name__ == "__main__":
    unittest.main()
