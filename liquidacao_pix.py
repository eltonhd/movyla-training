"""Limite de confiança para integrar futuros provedores Pix ao MOVYLA.

Este módulo NÃO expõe endpoint HTTP nem verifica assinaturas sozinho.
O adaptador do provedor deverá validar autenticidade da notificação,
consultar o pagamento na API oficial e só então criar PagamentoVerificado.
"""
from dataclasses import dataclass
from hmac import compare_digest

from pagamentos import confirmar_e_renovar


@dataclass(frozen=True)
class PagamentoVerificado:
    cobranca_id: int
    identificador_externo: str
    valor_centavos: int
    moeda: str
    status: str


def liquidar_pagamento_verificado(conn, pagamento, hoje=None):
    """Confronta dados autenticados do provedor com a cobrança persistida.

    Não aceita dados diretamente do navegador ou webhook não verificado.
    O chamador deve executar commit depois do retorno.
    """
    if not isinstance(pagamento, PagamentoVerificado):
        raise ValueError("Pagamento não foi verificado pelo adaptador.")
    if not isinstance(pagamento.cobranca_id, int) or pagamento.cobranca_id <= 0:
        raise ValueError("Cobrança inválida.")
    if not isinstance(pagamento.valor_centavos, int) or pagamento.valor_centavos <= 0:
        raise ValueError("Valor inválido.")
    if not isinstance(pagamento.identificador_externo, str) or not pagamento.identificador_externo.strip():
        raise ValueError("Identificador externo inválido.")
    if not compare_digest(pagamento.moeda.upper(), "BRL"):
        raise ValueError("Moeda não autorizada.")
    if pagamento.status != "aprovado":
        raise ValueError("Pagamento não aprovado.")
    conn.execute("SAVEPOINT movyla_liquidacao_verificada")
    try:
        cobranca = conn.execute("""
            SELECT id, valor_centavos, status, identificador_externo
            FROM cobrancas_assinatura WHERE id = ?
        """, (pagamento.cobranca_id,)).fetchone()
        if cobranca is None:
            raise ValueError("Cobrança não encontrada.")
        if cobranca["valor_centavos"] != pagamento.valor_centavos:
            raise ValueError("Valor pago diferente da cobrança.")
        if cobranca["status"] not in ("pendente", "paga"):
            raise ValueError("Cobrança não está apta a liquidação.")
        if cobranca["status"] == "paga" and cobranca["identificador_externo"] != pagamento.identificador_externo:
            raise ValueError("Identificador externo divergente.")
        resultado = confirmar_e_renovar(
            conn, pagamento.cobranca_id, pagamento.identificador_externo,
            hoje=hoje
        )
        conn.execute("RELEASE SAVEPOINT movyla_liquidacao_verificada")
        return resultado
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT movyla_liquidacao_verificada")
        conn.execute("RELEASE SAVEPOINT movyla_liquidacao_verificada")
        raise
