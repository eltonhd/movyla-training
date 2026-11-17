"""Adaptador inicial Mercado Pago Pix. Sem endpoint público ou credenciais no código.

Referência oficial: POST /v1/orders com transactions.payments Pix.
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
    if type(cobranca_id) is not int or cobranca_id <= 0:
        raise ValueError("Cobrança inválida.")
    if type(valor_centavos) is not int or valor_centavos <= 0:
        raise ValueError("Valor inválido.")
    if not isinstance(referencia, str) or not referencia.strip():
        raise ValueError("Referência inválida.")
    if not isinstance(email_pagador, str) or "@" not in email_pagador:
        raise ValueError("E-mail do pagador inválido.")
    if len(referencia) > 64:
        raise ValueError("Referência excede 64 caracteres.")
    valor = format(Decimal(valor_centavos) / 100, ".2f")
    dados = {
        "type": "online",
        "processing_mode": "automatic",
        "total_amount": valor,
        "external_reference": referencia,
        "payer": {"email": email_pagador},
        "transactions": {"payments": [{
            "amount": valor,
            "payment_method": {"id": "pix", "type": "bank_transfer"}
        }]}
    }
    retorno = _requisitar(
        "/v1/orders", metodo="POST", dados=dados,
        chave_idempotencia="movyla-pix-" + str(cobranca_id)
    )
    return extrair_dados_pix_order(retorno)


def extrair_dados_pix_order(retorno):
    """Normaliza instruções Pix sem interpretar o status como pagamento aprovado."""
    pagamentos = (retorno.get("transactions") or {}).get("payments") or []
    pagamento = pagamentos[0] if pagamentos else {}
    metodo = pagamento.get("payment_method") or {}
    dados_pix = metodo.get("transaction_data") or {}
    return {
        "id": str(retorno["id"]),
        "status": retorno.get("status"),
        "qr_code": metodo.get("qr_code") or dados_pix.get("qr_code"),
        "qr_code_base64": metodo.get("qr_code_base64") or dados_pix.get("qr_code_base64"),
        "ticket_url": metodo.get("ticket_url") or dados_pix.get("ticket_url"),
    }


def consultar_pagamento(order_id):
    """Consulta a order na API autenticada; webhook isolado não aprova nada."""
    identificador = str(order_id)
    if (not identificador.startswith("ORD") or len(identificador) > 64
            or not all(c.isalnum() or c == "-" for c in identificador)):
        raise ValueError("ID de order inválido.")
    return _requisitar("/v1/orders/" + identificador)
