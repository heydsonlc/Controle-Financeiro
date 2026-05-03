-- =============================================================================
-- VEIC-2: Mobilidade — modalidade ativa em banco + origem em item_despesa
-- =============================================================================
-- Idempotente: pode ser executado mais de uma vez sem duplicar estruturas.
-- Pré-condição: CAT-MAP-4A deve estar aplicado (tabela categoria_cartao existe).
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Colunas de origem em item_despesa
--    origem_tipo  : 'VEICULO' | 'TRANSPORTE_APP' | 'ASSINATURA' | etc.
--    origem_id    : id da entidade de origem (veiculo.id, caminho app, etc.)
--    origem_contexto : sub-tipo do custo — 'combustivel_mensal', 'assinatura_mensal'
--    categoria_cartao_id : CategoriaCartao para recorrências pagas no cartão
-- ---------------------------------------------------------------------------

ALTER TABLE item_despesa
    ADD COLUMN IF NOT EXISTS origem_tipo        VARCHAR(30)  NULL,
    ADD COLUMN IF NOT EXISTS origem_id          INTEGER      NULL,
    ADD COLUMN IF NOT EXISTS origem_contexto    VARCHAR(50)  NULL,
    ADD COLUMN IF NOT EXISTS categoria_cartao_id INTEGER     NULL
        REFERENCES categoria_cartao(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_item_despesa_origem
    ON item_despesa(origem_tipo, origem_id)
    WHERE origem_tipo IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. Tabela mobilidade_cenario_ativo
--    Persiste a modalidade de mobilidade atualmente escolhida pelo usuário.
--    Apenas uma linha com status='ATIVO' é permitida por vez (enforced via
--    trigger ou lógica de service — não via UNIQUE para permitir histórico).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mobilidade_cenario_ativo (
    id                  SERIAL PRIMARY KEY,
    tipo_modalidade     VARCHAR(20)  NOT NULL,  -- VEICULO | TRANSPORTE_APP | ASSINATURA
    origem_id           INTEGER      NOT NULL,  -- veiculo.id, origem_id app, ou 0 p/ assinatura
    ativo_desde         DATE         NOT NULL   DEFAULT CURRENT_DATE,
    meio_pagamento      VARCHAR(20)  NULL,      -- cartao | pix | boleto | dinheiro | debito
    cartao_id           INTEGER      NULL       REFERENCES item_despesa(id) ON DELETE SET NULL,
    categoria_id        INTEGER      NULL       REFERENCES categoria(id) ON DELETE SET NULL,
    categoria_cartao_id INTEGER      NULL       REFERENCES categoria_cartao(id) ON DELETE SET NULL,
    recorrencia_id      INTEGER      NULL       REFERENCES item_despesa(id) ON DELETE SET NULL,
    status              VARCHAR(10)  NOT NULL   DEFAULT 'ATIVO',  -- ATIVO | INATIVO
    metadata_json       TEXT         NULL,
    created_at          TIMESTAMP    NOT NULL   DEFAULT NOW(),
    updated_at          TIMESTAMP    NOT NULL   DEFAULT NOW(),

    CONSTRAINT chk_tipo_modalidade CHECK (tipo_modalidade IN ('VEICULO','TRANSPORTE_APP','ASSINATURA')),
    CONSTRAINT chk_status          CHECK (status IN ('ATIVO','INATIVO'))
);

CREATE INDEX IF NOT EXISTS idx_mob_cenario_status
    ON mobilidade_cenario_ativo(status)
    WHERE status = 'ATIVO';

COMMIT;

-- Verificações (executar separadamente se desejar confirmar):
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name='item_despesa' AND column_name IN
--         ('origem_tipo','origem_id','origem_contexto','categoria_cartao_id');
-- SELECT table_name FROM information_schema.tables
--   WHERE table_name='mobilidade_cenario_ativo';
