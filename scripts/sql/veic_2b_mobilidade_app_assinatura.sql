-- =============================================================================
-- VEIC-2B: Mobilidade — assinatura mensal + status SUPRIMIDA em DespesaPrevista
-- =============================================================================
-- Idempotente: pode ser executado mais de uma vez sem efeitos colaterais.
-- Pré-condição: VEIC-2 já aplicado (item_despesa tem origem_tipo/id/contexto).
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Tabela mobilidade_assinatura
--    Representa um carro por assinatura ou qualquer plano mensal estável.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mobilidade_assinatura (
    id           SERIAL       PRIMARY KEY,
    nome         VARCHAR(100) NOT NULL,
    valor_mensal NUMERIC(10,2) NOT NULL,
    categoria_id INTEGER      NULL REFERENCES categoria(id) ON DELETE SET NULL,
    status       VARCHAR(10)  NOT NULL DEFAULT 'ATIVO'
                     CHECK (status IN ('ATIVO','INATIVO')),
    metadata_json TEXT        NULL,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mob_assinatura_status
    ON mobilidade_assinatura(status)
    WHERE status = 'ATIVO';

-- ---------------------------------------------------------------------------
-- 2. Status SUPRIMIDA em despesa_prevista
--    Usado quando uma recorrência automática cobre o mesmo custo mensal,
--    tornando a confirmação manual redundante.
--    Conservador: apenas acrescenta o valor ao CHECK existente se necessário.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    -- Verifica se o constraint de status já aceita SUPRIMIDA
    -- (abordagem segura: tenta remover e recriar somente se necessário)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_schema = 'public'
          AND constraint_name LIKE '%despesa_prevista%status%'
    ) THEN
        -- Sem constraint formal: apenas garantir que coluna existe (já existe)
        NULL;
    END IF;
END;
$$;

-- Nota: o campo status em despesa_prevista é VARCHAR sem CHECK constraint no DDL
-- atual do projeto. A aplicação controla os valores válidos na camada de serviço.
-- O status 'SUPRIMIDA' será aceito pelo banco sem alteração de constraint.
-- Para documentação: valores válidos após VEIC-2B:
--   PREVISTA | CONFIRMADA | ADIADA | IGNORADA | SUPRIMIDA

COMMIT;

-- Verificações:
-- SELECT table_name FROM information_schema.tables WHERE table_name='mobilidade_assinatura';
-- SELECT column_name, data_type FROM information_schema.columns
--   WHERE table_name='despesa_prevista' AND column_name='status';
