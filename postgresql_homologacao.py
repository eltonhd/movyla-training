"""Isolated PostgreSQL connection prototype for MOVYLA homologation.

NOT used by app.py. Requires psycopg 3 and PostgreSQL-specific SQL with %s
parameters. Does not rewrite SQLite SQL or touch the running application.
"""
import os


class LinhaMovyla:
    """SQLite Row-like object: supports both row[0] and row['column']."""

    __slots__ = ("_values", "_indices")

    def __init__(self, values, columns):
        self._values = tuple(values)
        self._indices = {name: i for i, name in enumerate(columns)}

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._values[self._indices[key]]
        return self._values[key]

    def __len__(self):
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def keys(self):
        return list(self._indices)


def fabrica_linhas_movyla(cursor):
    """Psycopg RowFactory compatible with mixed index/name access."""
    colunas = [col.name for col in cursor.description] if cursor.description else []

    def construir(values):
        return LinhaMovyla(values, colunas)

    return construir


def conectar_postgresql(url=None):
    """Open an isolated PostgreSQL connection; never logs credentials."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg 3 nao instalado no ambiente de teste.") from exc

    endereco = url or os.environ.get("DATABASE_URL")
    if not endereco:
        raise RuntimeError("DATABASE_URL nao configurada para teste PostgreSQL.")
    return psycopg.connect(
        endereco, row_factory=fabrica_linhas_movyla, connect_timeout=10
    )


def verificar_conexao(url=None):
    """Read-only smoke test; no table changes or credentials in output."""
    with conectar_postgresql(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 AS teste")
            return cursor.fetchone()["teste"] == 1
