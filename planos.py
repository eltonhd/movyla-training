"""Catálogo inicial de planos MOVYLA.

Os valores são definidos no servidor. Este módulo não realiza cobrança.
Uma futura integração Pix deverá usar IDs de planos persistidos no banco
e validar novamente o preço no servidor antes de criar uma cobrança.
"""
from decimal import Decimal

PLANOS_INICIAIS = (
    {"codigo": "mensal", "nome": "Mensal", "meses": 1, "preco": Decimal("50.00")},
    {"codigo": "trimestral", "nome": "Trimestral", "meses": 3, "preco": Decimal("120.00")},
    {"codigo": "semestral", "nome": "Semestral", "meses": 6, "preco": Decimal("250.00")},
)


def criar_tabela_planos(conexao):
    """Cria o catálogo sem alterar assinaturas já existentes."""
    conexao.execute("""
        CREATE TABLE IF NOT EXISTS planos_assinatura (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            periodo_meses INTEGER NOT NULL CHECK(periodo_meses > 0),
            preco_centavos INTEGER NOT NULL CHECK(preco_centavos >= 0),
            ativo INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0, 1))
        )
    """)
    for plano in PLANOS_INICIAIS:
        centavos = int(plano["preco"] * 100)
        conexao.execute("""
            INSERT OR IGNORE INTO planos_assinatura
                (codigo, nome, periodo_meses, preco_centavos, ativo)
            VALUES (?, ?, ?, ?, 1)
        """, (plano["codigo"], plano["nome"], plano["meses"], centavos))


def listar_planos(conexao):
    """Retorna somente os planos ativos, com preços inteiros em centavos."""
    return conexao.execute("""
        SELECT id, codigo, nome, periodo_meses, preco_centavos
        FROM planos_assinatura
        WHERE ativo = 1
        ORDER BY periodo_meses
    """).fetchall()
