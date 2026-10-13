import sqlite3
import unittest

from renovacoes import adicionar_meses, aplicar_renovacao_confirmada
from cobrancas import criar_tabela_cobrancas
from planos import criar_tabela_planos


class TestarRenovacoes(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE assinaturas_personais (
                id INTEGER PRIMARY KEY, tipo_assinatura TEXT,
                isento INTEGER, proximo_vencimento TEXT
            )
        """)
        self.conn.execute("""
            INSERT INTO assinaturas_personais VALUES (1, 'paga', 0, '2026-11-10')
        """)
        criar_tabela_planos(self.conn)
        criar_tabela_cobrancas(self.conn)
        self.conn.execute("""
            INSERT INTO cobrancas_assinatura
                (id, assinatura_id, plano_id, referencia, valor_centavos,
                 periodo_meses, status, criada_em)
            VALUES (1, 1, 1, 'renovacao-1', 5000, 1, 'paga', '2026-10-13')
        """)

    def tearDown(self):
        self.conn.close()

    def test_renovacao_preserva_dias_ja_pagos(self):
        vencimento, aplicada = aplicar_renovacao_confirmada(
            self.conn, 1, hoje="2026-10-13"
        )
        self.assertEqual((vencimento, aplicada), ("2026-12-10", True))

    def test_nao_renova_duas_vezes(self):
        aplicar_renovacao_confirmada(self.conn, 1, hoje="2026-10-13")
        vencimento, aplicada = aplicar_renovacao_confirmada(
            self.conn, 1, hoje="2026-10-13"
        )
        self.assertEqual((vencimento, aplicada), ("2026-12-10", False))

    def test_cobranca_pendente_nao_renova(self):
        self.conn.execute(
            "UPDATE cobrancas_assinatura SET status = 'pendente' WHERE id = 1"
        )
        with self.assertRaises(ValueError):
            aplicar_renovacao_confirmada(self.conn, 1, hoje="2026-10-13")

    def test_renovacao_vencida_parte_de_hoje(self):
        self.conn.execute("""
            UPDATE assinaturas_personais SET proximo_vencimento = '2026-09-01'
            WHERE id = 1
        """)
        vencimento, aplicada = aplicar_renovacao_confirmada(
            self.conn, 1, hoje="2026-10-13"
        )
        self.assertEqual((vencimento, aplicada), ("2026-11-13", True))

    def test_fim_de_mes(self):
        self.assertEqual(adicionar_meses("2026-01-31", 1), "2026-02-28")


if __name__ == "__main__":
    unittest.main()
