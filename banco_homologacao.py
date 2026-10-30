
import os
import sqlite3
from pathlib import Path


def inicializar_banco_homologacao():
    if os.environ.get("MOVYLA_AMBIENTE") != "homologacao":
        return

    arquivo_sql = Path(__file__).resolve().parent / "estrutura_movyla.sql"

    if not arquivo_sql.is_file():
        raise RuntimeError("Arquivo estrutura_movyla.sql nao encontrado.")

    caminho_banco = os.environ.get("DATABASE_PATH", "meutreino.db")
    sql = arquivo_sql.read_text(encoding="utf-8")

    sql = sql.replace(
        "CREATE TABLE ",
        "CREATE TABLE IF NOT EXISTS "
    )

    with sqlite3.connect(caminho_banco) as conn:
        conn.executescript(sql)

        colunas = [coluna[1] for coluna in conn.execute("PRAGMA table_info(usuarios)")]
        if "email" not in colunas:
            conn.execute("ALTER TABLE usuarios ADD COLUMN email TEXT")

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email_unico
            ON usuarios(LOWER(email)) WHERE email IS NOT NULL
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS recuperacao_senha (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expira_em TEXT NOT NULL,
                utilizado_em TEXT,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        """)
