"""Integration smoke test using disposable PostgreSQL only (not Supabase).

Set TEST_POSTGRES_URL to a dedicated, throwaway database. The test creates
tables and data and must NEVER be pointed at an existing database.
"""
import os
import unittest
from pathlib import Path
from urllib.parse import urlparse

from postgresql_homologacao import conectar_postgresql

ROOT = Path(__file__).resolve().parent
MIGRATIONS = ROOT / "migrations" / "postgresql"


@unittest.skipUnless(os.environ.get("TEST_POSTGRES_URL"), "Sem banco descartavel de teste")
class PostgreSQLIntegrationTests(unittest.TestCase):
    def test_schema_and_persistence_across_connections(self):
        url = os.environ["TEST_POSTGRES_URL"]
        # Refuse Supabase, production, and any remote host, even if env is wrong.
        parsed = urlparse(url)
        self.assertIn(parsed.hostname, ("localhost", "127.0.0.1"),
                      "Integration test requires a LOCAL disposable database")
        self.assertEqual(parsed.path, "/movyla_ci",
                         "Integration test requires database movyla_ci")
        self.assertEqual(parsed.username, "movyla_ci",
                         "Integration test requires dedicated CI user")
        with conectar_postgresql(url) as conn:
            # Migration files own BEGIN/COMMIT: avoid nested transactions.
            conn.autocommit = True
            for path in sorted(MIGRATIONS.glob("*.sql")):
                with conn.cursor() as cur:
                    cur.execute(path.read_text(encoding="utf-8"))
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO usuarios (nome, usuario, senha, tipo) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    ("Personal Teste", "teste_pg_ci", "hash_de_teste", "personal"),
                )
                user_id = cur.fetchone()["id"]
                self.assertIsInstance(user_id, int)
            conn.commit()

        # Re-run migrations to ensure deployments can safely restart.
        with conectar_postgresql(url) as conn:
            # Migration files own BEGIN/COMMIT: avoid nested transactions.
            conn.autocommit = True
            for path in sorted(MIGRATIONS.glob("*.sql")):
                with conn.cursor() as cur:
                    cur.execute(path.read_text(encoding="utf-8"))
            conn.autocommit = False
            conn.commit()

        with conectar_postgresql(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, nome FROM usuarios WHERE usuario = %s",
                            ("teste_pg_ci",))
                registro = cur.fetchone()
                self.assertIsNotNone(registro)
                self.assertEqual(registro[0], user_id)
                self.assertEqual(registro["nome"], "Personal Teste")


    def test_renovacao_paga_idempotente(self):
        from renovacoes_postgresql_homologacao import aplicar_renovacao_postgresql
        url = os.environ["TEST_POSTGRES_URL"]
        parsed = urlparse(url)
        self.assertEqual((parsed.hostname, parsed.path, parsed.username),
                         ("localhost", "/movyla_ci", "movyla_ci"))
        with conectar_postgresql(url) as conn:
            # Migration files own BEGIN/COMMIT: avoid nested transactions.
            conn.autocommit = True
            for path in sorted(MIGRATIONS.glob("*.sql")):
                with conn.cursor() as cur:
                    cur.execute(path.read_text(encoding="utf-8"))
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO usuarios (nome, usuario, senha, tipo) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    ("Personal Renovacao", "renovacao_pg_ci", "hash_de_teste", "personal"),
                )
                personal_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO assinaturas_personais "
                    "(personal_id, plano, proximo_vencimento, tipo_assinatura) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (personal_id, "mensal", "2026-11-30", "paga"),
                )
                assinatura_id = cur.fetchone()[0]
                cur.execute(
                    "SELECT id FROM planos_assinatura WHERE codigo = %s",
                    ("mensal",),
                )
                plano_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO cobrancas_assinatura "
                    "(assinatura_id, plano_id, referencia, valor_centavos, "
                    "periodo_meses, status, criada_em) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (assinatura_id, plano_id, "renovacao-ci", 5000, 1,
                     "paga", "2026-11-10"),
                )
                cobranca_id = cur.fetchone()[0]
            conn.commit()
        with conectar_postgresql(url) as conn:
            primeiro = aplicar_renovacao_postgresql(
                conn, cobranca_id, hoje="2026-11-10")
            segundo = aplicar_renovacao_postgresql(
                conn, cobranca_id, hoje="2026-11-10")
            self.assertEqual(primeiro, ("2026-12-30", True))
            self.assertEqual(segundo, ("2026-12-30", False))
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT proximo_vencimento FROM assinaturas_personais WHERE id = %s",
                    (assinatura_id,),
                )
                self.assertEqual(cur.fetchone()[0], "2026-12-30")
                cur.execute(
                    "SELECT COUNT(*) FROM renovacoes_assinatura WHERE cobranca_id = %s",
                    (cobranca_id,),
                )
                self.assertEqual(cur.fetchone()[0], 1)


    def test_recuperacao_senha_persiste_e_email_unico(self):
        """Validate recovery-token storage and case-insensitive email uniqueness."""
        from psycopg.errors import UniqueViolation
        url = os.environ["TEST_POSTGRES_URL"]
        parsed = urlparse(url)
        self.assertEqual((parsed.hostname, parsed.path, parsed.username),
                         ("localhost", "/movyla_ci", "movyla_ci"))
        with conectar_postgresql(url) as conn:
            conn.autocommit = True
            for path in sorted(MIGRATIONS.glob("*.sql")):
                with conn.cursor() as cur:
                    cur.execute(path.read_text(encoding="utf-8"))
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO usuarios (nome, usuario, senha, tipo, email) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    ("Teste Recuperacao", "recuperacao_pg_ci", "hash", "personal",
                     "teste.recuperacao@example.invalid"),
                )
                usuario_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO recuperacao_senha (usuario_id, token_hash, expira_em) "
                    "VALUES (%s, %s, %s) RETURNING id",
                    (usuario_id, "hash_recuperacao_ci", "2026-11-15 12:00:00"),
                )
                token_id = cur.fetchone()[0]
            conn.commit()
        with conectar_postgresql(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT usuario_id, token_hash FROM recuperacao_senha WHERE id = %s",
                    (token_id,),
                )
                token = cur.fetchone()
                self.assertEqual(token["usuario_id"], usuario_id)
                self.assertEqual(token["token_hash"], "hash_recuperacao_ci")
                with self.assertRaises(UniqueViolation):
                    with conn.transaction():
                        cur.execute(
                            "INSERT INTO usuarios (nome, usuario, senha, tipo, email) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            ("Duplicado", "duplicado_pg_ci", "hash", "personal",
                             "TESTE.RECUPERACAO@EXAMPLE.INVALID"),
                        )


    def test_login_hash_werkzeug_persiste_entre_conexoes(self):
        """Exercise the actual password hashing used by MOVYLA login."""
        from werkzeug.security import generate_password_hash, check_password_hash
        url = os.environ["TEST_POSTGRES_URL"]
        parsed = urlparse(url)
        self.assertEqual((parsed.hostname, parsed.path, parsed.username),
                         ("localhost", "/movyla_ci", "movyla_ci"))
        senha = "senha_de_teste_nao_real"
        hash_senha = generate_password_hash(senha)
        with conectar_postgresql(url) as conn:
            conn.autocommit = True
            for path in sorted(MIGRATIONS.glob("*.sql")):
                with conn.cursor() as cur:
                    cur.execute(path.read_text(encoding="utf-8"))
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO usuarios (nome, usuario, senha, tipo) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    ("Login CI", "login_pg_ci", hash_senha, "personal"),
                )
                usuario_id = cur.fetchone()[0]
            conn.commit()
        with conectar_postgresql(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, senha, tipo FROM usuarios WHERE usuario = %s",
                    ("login_pg_ci",),
                )
                registro = cur.fetchone()
                self.assertEqual(registro["id"], usuario_id)
                self.assertEqual(registro["tipo"], "personal")
                self.assertTrue(check_password_hash(registro["senha"], senha))
                self.assertFalse(check_password_hash(registro["senha"], "senha_errada"))


if __name__ == "__main__":
    unittest.main()
