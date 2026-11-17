"""Offline checks for staged PostgreSQL DDL; no database or secrets needed."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIGRATIONS = ROOT / "migrations" / "postgresql"


class PostgresSchemaTests(unittest.TestCase):
    def test_migration_files_present(self):
        for number in ("001", "002", "003"):
            self.assertEqual(len(list(MIGRATIONS.glob(f"{number}_*.sql"))), 1)

    def test_no_sqlite_only_ddl(self):
        for path in sorted(MIGRATIONS.glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotRegex(sql, r"(?i)\bAUTOINCREMENT\b")
                self.assertNotRegex(sql, r"(?i)\bPRAGMA\b")
                self.assertNotRegex(sql, r"(?i)\bINSERT\s+OR\s+IGNORE\b")

    def test_required_tables_covered(self):
        sql = "\n".join(p.read_text(encoding="utf-8")
                        for p in sorted(MIGRATIONS.glob("*.sql")))
        required = {
            "usuarios", "recuperacao_senha", "exercicios", "treinos",
            "treino_exercicios", "treino_alunos", "treino_series",
            "treino_aluno_series", "sessoes", "series",
            "assinaturas_personais", "pagamentos_personais",
            "planos_assinatura", "cobrancas_assinatura",
            "cupons_assinatura", "orders_mercado_pago",
            "renovacoes_assinatura",
        }
        created = set(re.findall(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)",
            sql, flags=re.IGNORECASE,
        ))
        self.assertFalse(required - created, f"Missing tables: {required - created}")


if __name__ == "__main__":
    unittest.main()
