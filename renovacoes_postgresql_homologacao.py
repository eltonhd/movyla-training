"""PostgreSQL-only renewal routine for MOVYLA homologation.

Not wired into app.py. Caller must verify payment with the provider first.
The row lock serializes renewals of the same subscription across workers.
"""
from datetime import date
from renovacoes import adicionar_meses


def aplicar_renovacao_postgresql(conn, cobranca_id, hoje=None):
    """Return (new_due_date, applied_now) in a single PostgreSQL transaction."""
    data_atual = date.fromisoformat(hoje) if hoje else date.today()
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """SELECT c.assinatura_id, c.periodo_meses, a.proximo_vencimento,
                          a.tipo_assinatura, COALESCE(a.isento, 0)
                   FROM cobrancas_assinatura c
                   JOIN assinaturas_personais a ON a.id = c.assinatura_id
                   WHERE c.id = %s AND c.status = 'paga'
                   FOR UPDATE OF a""",
                (cobranca_id,),
            )
            registro = cur.fetchone()
            if registro is None:
                raise ValueError("Cobranca paga e assinatura valida sao obrigatorias.")
            assinatura_id, meses, vencimento, tipo, isento = registro
            if tipo != "paga" or isento:
                raise ValueError("Assinatura isenta ou gratuita nao pode ser renovada.")
            cur.execute(
                "SELECT vencimento_novo FROM renovacoes_assinatura WHERE cobranca_id = %s",
                (cobranca_id,),
            )
            anterior = cur.fetchone()
            if anterior is not None:
                return anterior[0], False
            base = data_atual
            if vencimento:
                vencimento_data = date.fromisoformat(vencimento)
                if vencimento_data > base:
                    base = vencimento_data
            novo = adicionar_meses(base.isoformat(), meses)
            cur.execute(
                """INSERT INTO renovacoes_assinatura
                   (cobranca_id, assinatura_id, vencimento_anterior, vencimento_novo)
                   VALUES (%s, %s, %s, %s)""",
                (cobranca_id, assinatura_id, vencimento, novo),
            )
            cur.execute(
                "UPDATE assinaturas_personais SET proximo_vencimento = %s WHERE id = %s",
                (novo, assinatura_id),
            )
            return novo, True
