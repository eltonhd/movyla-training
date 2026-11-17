"""Auditoria somente-leitura dos bloqueios SQLite para migracao PostgreSQL.

Executar: python auditar_sqlite_postgresql.py
Nao abre banco, nao importa app.py, nao acessa credenciais.
"""
from pathlib import Path
import json
import re

RAIZ = Path(__file__).resolve().parent
ARQUIVOS = (
    "app.py", "cobrancas.py", "planos.py", "renovacoes.py",
    "conciliacao_orders.py", "orders_mercado_pago.py",
    "banco_homologacao.py", "admin_inicial_homologacao.py",
    "database.py", "cupons.py",
)
PADROES = {
    "transacao_sqlite": r"\bBEGIN\s+IMMEDIATE\b",
    "introspeccao_sqlite": r"\bPRAGMA\s+table_info\b",
    "id_apos_insert": r"\.lastrowid\b",
    "insert_ignore": r"\bINSERT\s+OR\s+IGNORE\b",
    "excecao_sqlite": r"\bsqlite3\.IntegrityError\b",
    "data_sqlite": r"\bdate\s*\(\s*['\"]now['\"]",
    "ddl_autoincrement": r"\bAUTOINCREMENT\b",
    "conexao_sqlite": r"\bsqlite3\.connect\s*\(",
}


def auditar():
    resultado = {}
    for nome in ARQUIVOS:
        arquivo = RAIZ / nome
        if not arquivo.is_file():
            continue
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
        achados = []
        for numero, linha in enumerate(linhas, 1):
            for categoria, padrao in PADROES.items():
                if re.search(padrao, linha, flags=re.IGNORECASE):
                    achados.append({"linha": numero, "tipo": categoria})
        resultado[nome] = achados
    return resultado


if __name__ == "__main__":
    relatorio = auditar()
    print(json.dumps({
        "arquivos_auditados": len(relatorio),
        "bloqueios_identificados": sum(map(len, relatorio.values())),
        "por_arquivo": {
            nome: {"total": len(achados), "ocorrencias": achados}
            for nome, achados in relatorio.items()
        },
    }, indent=2, ensure_ascii=False))
