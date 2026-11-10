"""PostgreSQL adapter for MOVYLA homologation (NOT wired into app.py).

Requires psycopg>=3 and a DATABASE_URL configured only in a controlled test.
This adapter deliberately refuses to rewrite SQLite SQL automatically: PRAGMA,
BEGIN IMMEDIATE, AUTOINCREMENT, and SQLite date expressions need explicit
migration. No credentials are logged.
"""
import os

def conectar_postgresql(url=None):
    """Return a psycopg connection with dict-like AND indexable rows.

    Use only with SQL explicitly converted to PostgreSQL (%s placeholders).
    This module does not alter the existing SQLite application.
    """
    try:
        import psycopg
        from psycopg.rows import namedtuple_row
    except ImportError as exc:
        raise RuntimeError("Instale psycopg[binary] no ambiente de teste PostgreSQL.") from exc

    endereco = url or os.environ.get("DATABASE_URL")
    if not endereco:
        raise RuntimeError("DATABASE_URL nao configurada para teste PostgreSQL.")
    # namedtuple_row is indexable and allows attribute access, but not row['id'].
    # Therefore use dict_row for MOVYLA routes that expect row['id']; these
    # must be audited for numeric indexing before activation.
    from psycopg.rows import dict_row
    return psycopg.connect(endereco, row_factory=dict_row, connect_timeout=10)


def verificar_conexao(url=None):
    """Read-only connectivity probe. Never creates tables or prints secrets."""
    with conectar_postgresql(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 AS teste")
            return cursor.fetchone()["teste"] == 1
