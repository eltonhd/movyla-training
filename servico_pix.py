"""Serviço de geração Pix para cobrança persistida, sem rota pública.

Só pode ser chamado após validar a identidade do personal autenticado.
Uma Order existente nunca é recriada; o resultado pode ser consultado
na API autenticada do Mercado Pago.
"""
from mercado_pago_pix import criar_pix, consultar_pagamento
from orders_mercado_pago import vincular_order


def gerar_pix_cobranca(conn, cobranca_id, personal_id, email_pagador):
    """Usa somente o valor armazenado e verifica o titular da cobrança."""
    if (type(cobranca_id) is not int or cobranca_id <= 0
            or type(personal_id) is not int or personal_id <= 0):
        raise ValueError("Identificadores inválidos.")
    cobranca = conn.execute("""
        SELECT c.id, c.referencia, c.valor_centavos, c.status
        FROM cobrancas_assinatura c
        JOIN assinaturas_personais a ON a.id = c.assinatura_id
        WHERE c.id = ? AND a.personal_id = ?
          AND a.tipo_assinatura = 'paga' AND COALESCE(a.isento, 0) = 0
    """, (cobranca_id, personal_id)).fetchone()
    if cobranca is None:
        raise ValueError("Cobrança não pertence ao personal.")
    if cobranca["status"] != "pendente":
        raise ValueError("Cobrança não está pendente.")
    existente = conn.execute("""
        SELECT order_id FROM orders_mercado_pago WHERE cobranca_id = ?
    """, (cobranca_id,)).fetchone()
    if existente:
        return consultar_pagamento(existente["order_id"])
    retorno = criar_pix(
        cobranca["id"], cobranca["referencia"],
        cobranca["valor_centavos"], email_pagador
    )
    # O chamador deve confirmar a transação SQLite após o vínculo.
    # Se a chamada bancária funcionar e a gravação falhar, a mesma chave
    # de idempotência permite recuperar a Order sem gerar outra.
    vincular_order(conn, cobranca_id, retorno["id"], retorno.get("status") or "criada")
    return retorno
