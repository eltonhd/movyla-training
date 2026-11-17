"""Login PostgreSQL isolado para homologacao, sem alterar rotas Flask.

Nao habilitar na aplicacao enquanto as demais rotas ainda usarem SQLite.
A consulta retorna as mesmas colunas usadas pela rota /login atual.
"""
from werkzeug.security import check_password_hash

from postgresql_homologacao import conectar_postgresql


def autenticar_usuario_postgresql(usuario, senha, url=None):
    """Retorna dados do usuario ativo se a senha conferir; senao None."""
    if not isinstance(usuario, str) or not usuario.strip():
        return None
    if not isinstance(senha, str) or not senha:
        return None

    with conectar_postgresql(url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, nome, usuario, senha, tipo, foto "
                "FROM usuarios WHERE usuario = %s AND ativo = 1",
                (usuario,),
            )
            registro = cursor.fetchone()

    if registro is None:
        return None
    if not check_password_hash(registro["senha"], senha):
        return None
    return {
        "id": registro["id"],
        "nome": registro["nome"],
        "usuario": registro["usuario"],
        "tipo": registro["tipo"],
        "foto": registro["foto"],
    }
