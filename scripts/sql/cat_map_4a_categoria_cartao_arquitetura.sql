-- CAT-MAP-4A
-- Banco e backend da nova arquitetura de Categorias do Cartao.
-- Idempotente para PostgreSQL.

BEGIN;

CREATE TABLE IF NOT EXISTS categoria_cartao (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL UNIQUE,
    descricao TEXT,
    cor VARCHAR(7) DEFAULT '#6c757d',
    icone VARCHAR(50),
    logo_arquivo VARCHAR(255),
    logo_mime VARCHAR(100),
    logo_tamanho INTEGER,
    logo_original_nome VARCHAR(255),
    logo_criado_em TIMESTAMP,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categoria_cartao_despesa (
    id SERIAL PRIMARY KEY,
    categoria_cartao_id INTEGER NOT NULL REFERENCES categoria_cartao(id),
    categoria_id INTEGER NOT NULL REFERENCES categoria(id),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cartao_categoria_limite (
    id SERIAL PRIMARY KEY,
    cartao_id INTEGER NOT NULL REFERENCES item_despesa(id),
    categoria_cartao_id INTEGER NOT NULL REFERENCES categoria_cartao(id),
    limite_mensal NUMERIC(10, 2) NOT NULL DEFAULT 0,
    vigencia_inicio DATE,
    vigencia_fim DATE,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE lancamento_agregado
ADD COLUMN IF NOT EXISTS categoria_cartao_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_lancamento_agregado_categoria_cartao'
          AND conrelid = 'lancamento_agregado'::regclass
    ) THEN
        ALTER TABLE lancamento_agregado
        ADD CONSTRAINT fk_lancamento_agregado_categoria_cartao
        FOREIGN KEY (categoria_cartao_id) REFERENCES categoria_cartao(id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ux_categoria_cartao_despesa_par'
          AND conrelid = 'categoria_cartao_despesa'::regclass
    ) THEN
        ALTER TABLE categoria_cartao_despesa
        ADD CONSTRAINT ux_categoria_cartao_despesa_par
        UNIQUE (categoria_cartao_id, categoria_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ux_cartao_categoria_limite_cartao_categoria'
          AND conrelid = 'cartao_categoria_limite'::regclass
    ) THEN
        ALTER TABLE cartao_categoria_limite
        ADD CONSTRAINT ux_cartao_categoria_limite_cartao_categoria
        UNIQUE (cartao_id, categoria_cartao_id);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_categoria_cartao_despesa_categoria_ativa
ON categoria_cartao_despesa (categoria_id)
WHERE ativo;

CREATE INDEX IF NOT EXISTS ix_categoria_cartao_despesa_cartao
ON categoria_cartao_despesa (categoria_cartao_id);

CREATE INDEX IF NOT EXISTS ix_categoria_cartao_despesa_categoria
ON categoria_cartao_despesa (categoria_id);

CREATE INDEX IF NOT EXISTS ix_cartao_categoria_limite_cartao
ON cartao_categoria_limite (cartao_id);

CREATE INDEX IF NOT EXISTS ix_cartao_categoria_limite_categoria
ON cartao_categoria_limite (categoria_cartao_id);

CREATE INDEX IF NOT EXISTS ix_lanc_agregado_categoria_cartao_fatura
ON lancamento_agregado (categoria_cartao_id, mes_fatura);

-- Limpeza opcional da ponte CAT-MAP-2, somente se a tabela existir e estiver vazia.
-- Revisar manualmente antes de executar.
--
-- DO $$
-- BEGIN
--     IF to_regclass('categoria_cartao_mapeamento') IS NOT NULL
--        AND NOT EXISTS (SELECT 1 FROM categoria_cartao_mapeamento) THEN
--         DROP TABLE categoria_cartao_mapeamento;
--     END IF;
-- END $$;

COMMIT;
