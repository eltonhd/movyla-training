"""Validação da assinatura de webhook Mercado Pago (sem depender do payload).

Documentação MP: HMAC-SHA256 sobre
'id:<data.id>;request-id:<x-request-id>;ts:<ts>;'.
"""
import hashlib
import hmac
import re


def validar_assinatura_webhook(secret, x_signature, x_request_id, data_id):
    if not all(isinstance(x, str) and x for x in (
        secret, x_signature, x_request_id, data_id
    )):
        return False
    if len(x_signature) > 512 or len(x_request_id) > 256 or len(data_id) > 128:
        return False
    partes = {}
    for item in x_signature.split(","):
        if "=" not in item:
            return False
        chave, valor = item.strip().split("=", 1)
        if chave in partes:
            return False
        partes[chave] = valor
    ts, recebido = partes.get("ts", ""), partes.get("v1", "")
    if not re.fullmatch(r"[0-9]{10,13}", ts):
        return False
    if not re.fullmatch(r"[0-9a-fA-F]{64}", recebido):
        return False
    # Rejeitar notificações antigas ou com relógio muito adiantado.
    import time
    segundos = int(ts)
    if segundos > 10**11:
        segundos //= 1000
    if abs(int(time.time()) - segundos) > 300:
        return False
    manifesto = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
    esperado = hmac.new(
        secret.encode("utf-8"), manifesto.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperado, recebido.lower())
