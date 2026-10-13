
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
