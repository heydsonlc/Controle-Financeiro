-- CAT-DESP-UX-1
-- Estrutura nao destrutiva para palavras-chave de classificacao por Categoria de Despesa.

CREATE TABLE IF NOT EXISTS categoria_palavra_chave (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria_id INTEGER NOT NULL,
    palavra VARCHAR(120) NOT NULL,
    ativo BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (categoria_id) REFERENCES categoria(id)
);

CREATE INDEX IF NOT EXISTS ix_categoria_palavra_chave_categoria
    ON categoria_palavra_chave (categoria_id);

CREATE INDEX IF NOT EXISTS ix_categoria_palavra_chave_palavra
    ON categoria_palavra_chave (palavra);

CREATE UNIQUE INDEX IF NOT EXISTS ux_categoria_palavra_chave_categoria_palavra
    ON categoria_palavra_chave (categoria_id, palavra);
