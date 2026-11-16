"""Recuperacao de senha PostgreSQL isolada; nao altera as rotas Flask."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash
from postgresql_homologacao import conectar_postgresql


def _agora():
    return datetime.now(timezone.utc)


def _data_utc(texto):
    try:
        valor = datetime.fromisoformat(texto)
        if valor.tzinfo is None:
            return None
        return valor.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def criar_token_postgresql(usuario_id, url=None):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expira = (_agora() + timedelta(minutes=30)).isoformat()
    with conectar_postgresql(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO recuperacao_senha (usuario_id, token_hash, expira_em) "
                "VALUES (%s, %s, %s)",
                (usuario_id, token_hash, expira),
            )
    return token


def validar_token_postgresql(token, url=None):
    if not isinstance(token, str) or not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with conectar_postgresql(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT r.usuario_id, r.expira_em, r.utilizado_em "
                "FROM recuperacao_senha r JOIN usuarios u ON u.id = r.usuario_id "
                "WHERE r.token_hash = %s AND u.ativo = 1",
                (token_hash,),
            )
            registro = cur.fetchone()
    if not registro or registro["utilizado_em"]:
        return None
    expira = _data_utc(registro["expira_em"])
    return registro["usuario_id"] if expira and expira > _agora() else None


def salvar_nova_senha_postgresql(token, nova_senha, url=None):
    if (not isinstance(token, str) or not token
            or not isinstance(nova_senha, str)
            or not 8 <= len(nova_senha) <= 128):
        return False
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with conectar_postgresql(url) as conn:
        with conn.cursor() as cur:
            # Lock the token row: concurrent requests cannot consume it twice.
            cur.execute(
                "SELECT r.usuario_id, r.expira_em, r.utilizado_em "
                "FROM recuperacao_senha r JOIN usuarios u ON u.id = r.usuario_id "
                "WHERE r.token_hash = %s AND u.ativo = 1 FOR UPDATE OF r",
                (token_hash,),
            )
            registro = cur.fetchone()
            if not registro or registro["utilizado_em"]:
                return False
            expira = _data_utc(registro["expira_em"])
            if not expira or expira <= _agora():
                return False
            cur.execute(
                "UPDATE usuarios SET senha = %s WHERE id = %s",
                (generate_password_hash(nova_senha), registro["usuario_id"]),
            )
            cur.execute(
                "UPDATE recuperacao_senha SET utilizado_em = %s "
                "WHERE token_hash = %s AND utilizado_em IS NULL",
                (_agora().isoformat(), token_hash),
            )
            if cur.rowcount != 1:
                raise RuntimeError("Token alterado durante a recuperacao")
    return True
