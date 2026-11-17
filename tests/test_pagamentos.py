import sqlite3
import unittest

from cobrancas import criar_tabela_cobrancas, criar_tabela_cupons
from planos import criar_tabela_planos
from pagamentos import confirmar_e_renovar


class TestarPagamentoCompleto(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE assinaturas_personais (
                id INTEGER PRIMARY KEY, tipo_assinatura TEXT,
                isento INTEGER, proximo_vencimento TEXT
            )
        """)
        self.conn.execute(
            "INSERT INTO assinaturas_personais VALUES (1, 'paga', 0, '2026-11-10')"
        )
        criar_tabela_planos(self.conn)
        criar_tabela_cobrancas(self.conn)
        criar_tabela_cupons(self.conn)
        self.conn.execute("""
            INSERT INTO cobrancas_assinatura
                (id, assinatura_id, plano_id, referencia, valor_centavos,
                 periodo_meses, status, criada_em)
            VALUES (1, 1, 1, 'pagamento-1', 5000, 1, 'pendente', '2026-10-13')
        """)

    def tearDown(self):
        self.conn.close()

    def test_confirma_e_renova(self):
        self.assertEqual(
            confirmar_e_renovar(self.conn, 1, "pix-001", hoje="2026-10-13"),
            ("2026-12-10", True)
        )
        status = self.conn.execute(
            "SELECT status FROM cobrancas_assinatura WHERE id = 1"
        ).fetchone()[0]
        self.assertEqual(status, "paga")

    def test_repeticao_nao_renova_mais_uma_vez(self):
        confirmar_e_renovar(self.conn, 1, "pix-001", hoje="2026-10-13")
        self.assertEqual(
            confirmar_e_renovar(self.conn, 1, "pix-001", hoje="2026-10-13"),
            ("2026-12-10", False)
        )

    def test_erro_na_renovacao_reverte_confirmacao(self):
        self.conn.execute("""
            UPDATE assinaturas_personais SET tipo_assinatura = 'isenta', isento = 1
            WHERE id = 1
        """)
        with self.assertRaises(ValueError):
            confirmar_e_renovar(self.conn, 1, "pix-002", hoje="2026-10-13")
        status = self.conn.execute(
            "SELECT status FROM cobrancas_assinatura WHERE id = 1"
        ).fetchone()[0]
        self.assertEqual(status, "pendente")

    def test_identificador_divergente_nao_renova(self):
        confirmar_e_renovar(self.conn, 1, "pix-001", hoje="2026-10-13")
        with self.assertRaises(ValueError):
            confirmar_e_renovar(self.conn, 1, "pix-OUTRO", hoje="2026-10-13")
        vencimento = self.conn.execute(
            "SELECT proximo_vencimento FROM assinaturas_personais WHERE id = 1"
        ).fetchone()[0]
        self.assertEqual(vencimento, "2026-12-10")


if __name__ == "__main__":
    unittest.main()
