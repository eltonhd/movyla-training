
import os
import sqlite3

def criar_admin_inicial():
    if os.environ.get("MOVYLA_AMBIENTE") != "homologacao":
        return

    usuario = os.environ.get("MOVYLA_ADMIN_USUARIO", "").strip()
    nome = os.environ.get("MOVYLA_ADMIN_NOME", "").strip()
    senha_hash = os.environ.get("MOVYLA_ADMIN_SENHA_HASH", "").strip()

    if not usuario or not nome or not senha_hash:
        print("Administrador inicial nao configurado.")
        return

    caminho_banco = os.environ.get("DATABASE_PATH", "meutreino.db")

    with sqlite3.connect(caminho_banco) as conn:
        existente = conn.execute(
            "SELECT id FROM usuarios WHERE tipo = 'master' LIMIT 1"
        ).fetchone()

        if existente:
            return

        conn.execute(
            """
            INSERT INTO usuarios (nome, usuario, senha, tipo, ativo)
            VALUES (?, ?, ?, 'master', 1)
            """,
            (nome, usuario, senha_hash)
        )
        conn.commit()
        print("Administrador inicial criado com sucesso.")
