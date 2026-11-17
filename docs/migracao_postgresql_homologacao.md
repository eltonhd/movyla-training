# MOVYLA — preparação da migração SQLite → PostgreSQL (homologação)

Estado: **levantamento técnico; migração NÃO ativada**. Não configurar DATABASE_URL no Render antes da implementação e dos testes.

## Diagnóstico confirmado
- Render gratuito usa `DATABASE_PATH=/tmp/movyla_homologacao.db`. O diretório é efêmero: dados podem desaparecer após reinício/deploy.
- O usuário de teste desapareceu e a recuperação de senha registrou "nenhum usuario ativo corresponde ao email informado"; a API Brevo não foi acionada.
- Projeto Supabase PostgreSQL gratuito criado; URI de *Session pooler* guardada pelo proprietário, **não armazenada no GitHub**.
- A branch de homologação é `desenvolvimento-seguro-20261013`. Não alterar o aplicativo principal.

## Auditoria do código (06/11/2026)
- `app.py`: ~5165 linhas; `conectar()` retorna `sqlite3.Connection` com `sqlite3.Row`.
- ~249 ocorrências de `?` no arquivo (contagem textual; nem todas são parâmetros SQL).
- `cursor.lastrowid` em quatro fluxos (treinos, exercícios e sessões).
- `BEGIN IMMEDIATE` em recuperação de senha e fluxos financeiros.
- `PRAGMA table_info` no esquema financeiro.
- Funções SQLite `date('now', 'localtime', ...)` em avisos de vencimento.
- `sqlite3.IntegrityError` tratado em fluxo financeiro.
- `banco_homologacao.py` inicializa esquema SQLite por `executescript`.
- `admin_inicial_homologacao.py` acessa SQLite diretamente.
- `estrutura_movyla.sql` usa `INTEGER PRIMARY KEY AUTOINCREMENT` e tipos/valores específicos de SQLite.
- `requirements.txt` tem Flask e gunicorn; não contém driver PostgreSQL.

## Plano de implementação seguro
1. Criar adaptador de conexão PostgreSQL com comportamento de linhas compatível e parâmetros parametrizados. Usar `psycopg` e testar transações, commit/rollback, contexto e erros de integridade.
2. Criar esquema PostgreSQL versionado e idempotente, incluindo tabelas de login, alunos, treinos, histórico, assinaturas, pagamentos e recuperação. Verificar todas as restrições, chaves estrangeiras e índices. Não executar `estrutura_movyla.sql` SQLite em PostgreSQL.
3. Adaptar chamadas específicas de SQLite (`?`, `lastrowid`, `BEGIN IMMEDIATE`, `PRAGMA`, datas, exceções), inclusive os dois módulos auxiliares e os fluxos financeiros.
4. Testar localmente em banco PostgreSQL de homologação vazio: login master, cadastro e persistência após reinício, treinos, histórico, assinaturas, recuperação de senha e segurança de tokens.
5. Publicar somente na branch de homologação. Configurar `DATABASE_URL` como segredo no Render somente depois dos testes. Nunca exibir URI nem credenciais em logs/commits.
6. Validar persistência após novo deploy e, em seguida, envio pelo Brevo, recebimento do e-mail, redefinição e login.
7. Manter rollback documentado; não migrar produção automaticamente.

## Restrições
- Plano gratuito do Supabase tem limites e políticas de inatividade; não equivale a backup garantido. Planejar exportações periódicas.
- O Supabase pode mostrar a branch principal como "PRODUÇÃO"; isso não significa que o MOVYLA principal está conectado.
- Nunca trocar apenas `DATABASE_PATH` por URI PostgreSQL: `sqlite3.connect` não aceita essa URI.
