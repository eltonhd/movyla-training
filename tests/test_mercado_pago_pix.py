"""Testes locais do adaptador Mercado Pago, sem chamadas bancárias."""
import os
import unittest
from unittest.mock import patch

import mercado_pago_pix as mp


class TestarMercadoPagoPix(unittest.TestCase):
    def test_sem_credencial_nao_faz_requisicao(self):
        with patch.dict(os.environ, {"MERCADO_PAGO_ACCESS_TOKEN": ""}):
            with self.assertRaisesRegex(RuntimeError, "MERCADO_PAGO_ACCESS_TOKEN"):
                mp._token()

    def test_criacao_usa_valor_em_centavos_e_idempotencia(self):
        resposta = {
            "id": "ORD12345", "status": "action_required",
            "transactions": {"payments": [{"payment_method": {
                "qr_code": "000201", "qr_code_base64": "imagem-base64"
            }}]}
        }
        with patch("mercado_pago_pix._requisitar", return_value=resposta) as requisitar:
            resultado = mp.criar_pix(7, "movyla-abc", 5050, "personal@example.com")
        self.assertEqual(resultado["qr_code"], "000201")
        self.assertEqual(resultado["status"], "action_required")
        args, kwargs = requisitar.call_args
        self.assertEqual(args[0], "/v1/orders")
        self.assertEqual(kwargs["dados"]["total_amount"], "50.50")
        self.assertEqual(kwargs["dados"]["transactions"]["payments"][0]["payment_method"]["id"], "pix")
        self.assertEqual(kwargs["dados"]["external_reference"], "movyla-abc")
        self.assertEqual(kwargs["chave_idempotencia"], "movyla-pix-7")

    def test_recusa_valor_nao_inteiro(self):
        with self.assertRaises(ValueError):
            mp.criar_pix(7, "ref", 50.5, "a@example.com")

    def test_recusa_booleano_como_valor(self):
        with self.assertRaises(ValueError):
            mp.criar_pix(7, "ref", True, "a@example.com")

    def test_recusa_booleano_como_id(self):
        with self.assertRaises(ValueError):
            mp.criar_pix(True, "ref", 5000, "a@example.com")

    def test_recusa_identificador_nao_numerico(self):
        with self.assertRaises(ValueError):
            mp.consultar_pagamento("../outro")

    def test_normaliza_pix_consultado_com_hifen(self):
        resposta = {
            "id": "ORD-123", "status": "action_required",
            "transactions": {"payments": [{"payment_method": {
                "transaction_data": {"qr_code": "000201", "qr_code_base64": "abc"}
            }}]}
        }
        with patch("mercado_pago_pix._requisitar", return_value=resposta):
            bruto = mp.consultar_pagamento("ORD-123")
        self.assertEqual(bruto, resposta)
        pix = mp.extrair_dados_pix_order(bruto)
        self.assertEqual(pix["qr_code"], "000201")
        self.assertEqual(pix["qr_code_base64"], "abc")

    def test_consulta_pagamento_autenticada(self):
        with patch("mercado_pago_pix._requisitar", return_value={"status": "approved"}) as requisitar:
            self.assertEqual(mp.consultar_pagamento("ORD123")["status"], "approved")
        requisitar.assert_called_once_with("/v1/orders/ORD123")


if __name__ == "__main__":
    unittest.main()
