"""Registro de cobranças MOVYLA; nenhuma cobrança real é efetuada aqui."""
import sqlite3
from datetime import datetime, timezone


def criar_tabela_cobrancas(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cobrancas_assinatura (
            id INTEGER PRIMARY KEY,
            assinatura_id INTEGER NOT NULL,
            plano_id INTEGER NOT NULL,
            referencia TEXT NOT NULL UNIQUE,
            valor_centavos INTEGER NOT NULL CHECK(valor_centavos > 0),
            periodo_meses INTEGER NOT NULL CHECK(periodo_meses > 0),
            status TEXT NOT NULL DEFAULT 'pendente'
                CHECK(status IN ('pendente', 'paga', 'cancelada', 'expirada')),
            identificador_externo TEXT UNIQUE,
            criada_em TEXT NOT NULL,
            paga_em TEXT,
            FOREIGN KEY(assinatura_id) REFERENCES assinaturas_personais(id),
            FOREIGN KEY(plano_id) REFERENCES planos_assinatura(id)
        )
    """)


def registrar_cobranca(conn, assinatura_id, plano_id, referencia):
    """Congela o preço do plano no momento da criação, sem confirmar pagamento."""
    plano = conn.execute("""
        SELECT periodo_meses, preco_centavos FROM planos_assinatura
        WHERE id = ? AND ativo = 1
    """, (plano_id,)).fetchone()
    if plano is None or plano[1] <= 0:
        raise ValueError("Plano inválido ou indisponível.")
    assinatura = conn.execute("""
        SELECT id FROM assinaturas_personais
        WHERE id = ? AND COALESCE(isento, 0) = 0
          AND COALESCE(tipo_assinatura, 'paga') = 'paga'
    """, (assinatura_id,)).fetchone()
    if assinatura is None:
        raise ValueError("Assinatura não pode ser cobrada.")
    if not referencia or len(referencia) > 120:
        raise ValueError("Referência inválida.")
    try:
        cursor = conn.execute("""
            INSERT INTO cobrancas_assinatura
                (assinatura_id, plano_id, referencia, valor_centavos,
                 periodo_meses, criada_em)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (assinatura_id, plano_id, referencia, plano[1], plano[0],
              datetime.now(timezone.utc).isoformat()))
    except sqlite3.IntegrityError as exc:
        raise ValueError("Referência já utilizada.") from exc
    return cursor.lastrowid
