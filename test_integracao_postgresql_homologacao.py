"""Integration smoke test using disposable PostgreSQL only (not Supabase).

Set TEST_POSTGRES_URL to a dedicated, throwaway database. The test creates
tables and data and must NEVER be pointed at an existing database.
"""
import os
import unittest
from pathlib import Path

from postgresql_homologacao import conectar_postgresql

ROOT = Path(__file__).resolve().parent
MIGRATIONS = ROOT / "migrations" / "postgresql"


@unittest.skipUnless(os.environ.get("TEST_POSTGRES_URL"), "Sem banco descartavel de teste")
class PostgreSQLIntegrationTests(unittest.TestCase):
    def test_schema_and_persistence_across_connections(self):
        url = os.environ["TEST_POSTGRES_URL"]
        # CI provisions a fresh, empty database. Never use DATABASE_URL.
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
