-- MOVYLA PostgreSQL: renewal ledger (homologation only).
-- Run after 001 and 002. Not executed automatically by the Flask app.
BEGIN;
CREATE TABLE IF NOT EXISTS renovacoes_assinatura (
 cobranca_id BIGINT PRIMARY KEY REFERENCES cobrancas_assinatura(id),
 assinatura_id BIGINT NOT NULL REFERENCES assinaturas_personais(id),
 vencimento_anterior TEXT,
 vencimento_novo TEXT NOT NULL,
 registrada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::TEXT
);
COMMIT;
