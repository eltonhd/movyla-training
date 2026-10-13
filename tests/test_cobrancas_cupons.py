import sqlite3
import unittest

from planos import criar_tabela_planos
from cobrancas import (
    criar_tabela_cobrancas, criar_tabela_cupons,
    registrar_cobranca_com_cupom, preparar_descontos_cobrancas,
    cancelar_cobranca_pendente, expirar_cobranca_pendente
)


class TestarCobrancaComCupom(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE assinaturas_personais (
                id INTEGER PRIMARY KEY, tipo_assinatura TEXT, isento INTEGER
            )
        """)
        self.conn.execute(
            "INSERT INTO assinaturas_personais VALUES (1, 'paga', 0)"
        )
        criar_tabela_planos(self.conn)
        criar_tabela_cobrancas(self.conn)
        criar_tabela_cupons(self.conn)
        self.conn.execute("""
            INSERT INTO cupons_assinatura
                (codigo, desconto_centavos, personal_id, plano_id, administrador_id)
            VALUES ('PROMO10', 1000, 7, 1, 5)
        """)

    def tearDown(self):
        self.conn.close()

    def test_preserva_preco_e_reserva(self):
        cobranca_id = registrar_cobranca_com_cupom(
            self.conn, 1, 1, "pedido-1", "promo10", 7, 5
        )
        registro = self.conn.execute("""
            SELECT valor_original_centavos, desconto_centavos, valor_centavos, status
            FROM cobrancas_assinatura WHERE id = ?
        """, (cobranca_id,)).fetchone()
        self.assertEqual(registro, (5000, 1000, 4000, "pendente"))
        cupom = self.conn.execute("""
            SELECT cobranca_id, usado_em FROM cupons_assinatura WHERE codigo = 'PROMO10'
        """).fetchone()
        self.assertEqual(cupom, (cobranca_id, None))

    def test_nao_permite_reservar_duas_vezes(self):
        registrar_cobranca_com_cupom(self.conn, 1, 1, "pedido-1", "PROMO10", 7, 5)
        with self.assertRaises(ValueError):
            registrar_cobranca_com_cupom(self.conn, 1, 1, "pedido-2", "PROMO10", 7, 5)
        total = self.conn.execute("SELECT COUNT(*) FROM cobrancas_assinatura").fetchone()[0]
        self.assertEqual(total, 1)

    def test_administrador_incorreto_reverte(self):
        with self.assertRaises(ValueError):
            registrar_cobranca_com_cupom(self.conn, 1, 1, "pedido-3", "PROMO10", 7, 6)
        total = self.conn.execute("SELECT COUNT(*) FROM cobrancas_assinatura").fetchone()[0]
        self.assertEqual(total, 0)

    def test_cancelamento_libera_cupom(self):
        cobranca_id = registrar_cobranca_com_cupom(
            self.conn, 1, 1, "pedido-cancelado", "PROMO10", 7, 5
        )
        cancelar_cobranca_pendente(self.conn, cobranca_id)
        registro = self.conn.execute(
            "SELECT status FROM cobrancas_assinatura WHERE id = ?", (cobranca_id,)
        ).fetchone()
        reserva = self.conn.execute(
            "SELECT cobranca_id FROM cupons_assinatura WHERE codigo = 'PROMO10'"
        ).fetchone()
        self.assertEqual(registro[0], "cancelada")
        self.assertIsNone(reserva[0])

    def test_expiracao_libera_cupom(self):
        cobranca_id = registrar_cobranca_com_cupom(
            self.conn, 1, 1, "pedido-expirado", "PROMO10", 7, 5
        )
        expirar_cobranca_pendente(self.conn, cobranca_id)
        registro = self.conn.execute(
            "SELECT status FROM cobrancas_assinatura WHERE id = ?", (cobranca_id,)
        ).fetchone()
        self.assertEqual(registro[0], "expirada")
        reserva = self.conn.execute(
            "SELECT cobranca_id FROM cupons_assinatura WHERE codigo = 'PROMO10'"
        ).fetchone()
        self.assertIsNone(reserva[0])

    def test_nao_cancela_duas_vezes(self):
        cobranca_id = registrar_cobranca_com_cupom(
            self.conn, 1, 1, "pedido-unico", "PROMO10", 7, 5
        )
        cancelar_cobranca_pendente(self.conn, cobranca_id)
        with self.assertRaises(ValueError):
            cancelar_cobranca_pendente(self.conn, cobranca_id)

    def test_migracao_preserva_cobranca_antiga(self):
        from cobrancas import registrar_cobranca
        registrar_cobranca(self.conn, 1, 1, "antiga")
        preparar_descontos_cobrancas(self.conn)
        preparar_descontos_cobrancas(self.conn)
        registro = self.conn.execute("""
            SELECT valor_original_centavos, desconto_centavos, valor_centavos
            FROM cobrancas_assinatura WHERE referencia = 'antiga'
        """).fetchone()
        self.assertEqual(registro, (5000, 0, 5000))


if __name__ == "__main__":
    unittest.main()
