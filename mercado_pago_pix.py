"""Adaptador inicial Mercado Pago Pix. Sem endpoint público ou credenciais no código.

Referência oficial: POST /v1/payments com payment_method_id=pix.
A resposta inicial gera instruções Pix, NÃO comprova pagamento.
"""
import json
import os
import urllib.error
import urllib.request
from decimal import Decimal

API_BASE = "https://api.mercadopago.com"


def _token():
    token = os.environ.get("MERCADO_PAGO_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Configure MERCADO_PAGO_ACCESS_TOKEN no ambiente seguro.")
    return token


def _requisitar(caminho, metodo="GET", dados=None, chave_idempotencia=None):
    if not caminho.startswith("/") or caminho.startswith("//"):
        raise ValueError("Caminho de API inválido.")
    cabecalhos = {
        "Authorization": "Bearer " + _token(),
        "Accept": "application/json",
    }
    corpo = None
    if dados is not None:
        corpo = json.dumps(dados).encode("utf-8")
        cabecalhos["Content-Type"] = "application/json"
    if chave_idempotencia:
        cabecalhos["X-Idempotency-Key"] = chave_idempotencia
    requisicao = urllib.request.Request(
        API_BASE + caminho, data=corpo, headers=cabecalhos, method=metodo
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=15) as resposta:
            return json.load(resposta)
    except urllib.error.HTTPError as erro:
        raise RuntimeError("Mercado Pago recusou a operação (HTTP %s)." % erro.code) from erro


def criar_pix(cobranca_id, referencia, valor_centavos, email_pagador):
    """Cria Pix usando preço previamente calculado pelo servidor.

    Chamar somente a partir de cobrança pertencente ao personal autenticado.
    Nunca usar valor recebido do formulário.
    """
    if not isinstance(cobranca_id, int) or cobranca_id <= 0:
        raise ValueError("Cobrança inválida.")
    if not isinstance(valor_centavos, int) or valor_centavos <= 0:
        raise ValueError("Valor inválido.")
    if not isinstance(referencia, str) or not referencia.strip():
        raise ValueError("Referência inválida.")
    if not isinstance(email_pagador, str) or "@" not in email_pagador:
        raise ValueError("E-mail do pagador inválido.")
    dados = {
        "transaction_amount": float(Decimal(valor_centavos) / 100),
        "description": "Assinatura MOVYLA Training",
        "payment_method_id": "pix",
        "external_reference": referencia,
        "payer": {"email": email_pagador},
    }
    retorno = _requisitar(
        "/v1/payments", metodo="POST", dados=dados,
        chave_idempotencia="movyla-pix-" + str(cobranca_id)
    )
    return {
        "id": str(retorno["id"]),
        "status": retorno.get("status"),
        "qr_code": retorno.get("point_of_interaction", {}).get(
            "transaction_data", {}
        ).get("qr_code"),
        "qr_code_base64": retorno.get("point_of_interaction", {}).get(
            "transaction_data", {}
        ).get("qr_code_base64"),
    }


def consultar_pagamento(payment_id):
    """Consulta diretamente a API autenticada; webhook isolado não aprova nada."""
    identificador = str(payment_id)
    if not identificador.isdigit() or len(identificador) > 32:
        raise ValueError("ID de pagamento inválido.")
    return _requisitar("/v1/payments/" + identificador)
