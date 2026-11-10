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
            for path in sorted(MIGRATIONS.glob("*.sql")):
                with conn.cursor() as cur:
                    cur.execute(path.read_text(encoding="utf-8"))
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
            for path in sorted(MIGRATIONS.glob("*.sql")):
                with conn.cursor() as cur:
                    cur.execute(path.read_text(encoding="utf-8"))
            conn.commit()

        with conectar_postgresql(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, nome FROM usuarios WHERE usuario = %s",
                            ("teste_pg_ci",))
                registro = cur.fetchone()
                self.assertIsNotNone(registro)
                self.assertEqual(registro[0], user_id)
                self.assertEqual(registro["nome"], "Personal Teste")


if __name__ == "__main__":
    unittest.main()
