"""Verificação defensiva de Order Mercado Pago consultada via API autenticada.

Não recebe payload de webhook nem confirma pagamento por si só.
"""
from decimal import Decimal, InvalidOperation

from liquidacao_pix import PagamentoVerificado, liquidar_pagamento_verificado
from mercado_pago_pix import consultar_pagamento


def conferir_order_autenticada(conn, cobranca_id):
    """Consulta o provedor e compara ID, referência, valor, moeda e status."""
    vinculo = conn.execute("""
        SELECT o.order_id, c.referencia, c.valor_centavos
        FROM orders_mercado_pago o
        JOIN cobrancas_assinatura c ON c.id = o.cobranca_id
        WHERE c.id = ?
    """, (cobranca_id,)).fetchone()
    if vinculo is None:
        raise ValueError("Cobrança sem Order vinculada.")
    retorno = consultar_pagamento(vinculo["order_id"])
    if not isinstance(retorno, dict):
        raise ValueError("Resposta inválida do provedor.")
    if str(retorno.get("id", "")) != vinculo["order_id"]:
        raise ValueError("Order divergente.")
    if retorno.get("external_reference") != vinculo["referencia"]:
        raise ValueError("Referência externa divergente.")
    if retorno.get("currency_id") != "BRL":
        raise ValueError("Moeda não confirmada como BRL.")
    try:
        valor = Decimal(str(retorno["total_amount"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as erro:
        raise ValueError("Valor da Order inválido.") from erro
    if not valor.is_finite() or valor * 100 != vinculo["valor_centavos"]:
        raise ValueError("Valor da Order divergente.")
    pagamentos = (retorno.get("transactions") or {}).get("payments") or []
    if len(pagamentos) != 1 or not isinstance(pagamentos[0], dict):
        raise ValueError("Transação Pix não identificada de forma única.")
    pagamento = pagamentos[0]
    metodo = pagamento.get("payment_method") or {}
    if metodo.get("id") != "pix":
        raise ValueError("Método de pagamento divergente.")
    if retorno.get("status") != "processed" or pagamento.get("status") != "approved":
        raise ValueError("Pagamento ainda não confirmado pelo provedor.")
    try:
        valor_pago = Decimal(str(pagamento["amount"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as erro:
        raise ValueError("Valor pago inválido.") from erro
    if not valor_pago.is_finite() or valor_pago * 100 != vinculo["valor_centavos"]:
        raise ValueError("Valor pago divergente.")
    return PagamentoVerificado(
        cobranca_id=cobranca_id,
        identificador_externo=vinculo["order_id"],
        valor_centavos=vinculo["valor_centavos"],
        moeda="BRL",
        status="aprovado",
    )


def reconciliar_order_autenticada(conn, cobranca_id, hoje=None):
    """Liquida apenas após GET autenticado; commit pertence ao chamador."""
    comprovado = conferir_order_autenticada(conn, cobranca_id)
    return liquidar_pagamento_verificado(conn, comprovado, hoje=hoje)
