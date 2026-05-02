-- =============================================================================
-- VEIC-HOMOLOG-2: Criar categoria "Mobilidade" e migrar despesas previstas
-- =============================================================================
-- Idempotente: pode ser executado mais de uma vez sem duplicar "Mobilidade".
-- NÃO remove "Transporte" nem afeta despesas fora do módulo de veículos.
-- Filtro seguro: apenas DespesaPrevista com origem_tipo IN ('VEICULO','TRANSPORTE_APP').
-- =============================================================================

BEGIN;

-- 1. Inserir categoria "Mobilidade" caso ainda não exista
INSERT INTO categoria (nome, descricao, cor, icone, ativo, criado_em)
SELECT
    'Mobilidade',
    'Despesas de mobilidade: veículos próprios e transporte por app',
    '#1e40af',
    'car',
    TRUE,
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM categoria WHERE nome = 'Mobilidade'
);

-- 2. Atualizar DespesaPrevista do módulo de mobilidade para a nova categoria
--    Filtro: origem_tipo IN ('VEICULO', 'TRANSPORTE_APP')
--    Condição extra: categoria_id da linha origem é a categoria "Transporte" (evita sobrescrever
--    despesas cujas categorias foram editadas manualmente pelo usuário para outro valor).
UPDATE despesa_prevista
SET categoria_id = (SELECT id FROM categoria WHERE nome = 'Mobilidade' LIMIT 1)
WHERE origem_tipo IN ('VEICULO', 'TRANSPORTE_APP')
  AND categoria_id = (SELECT id FROM categoria WHERE nome = 'Transporte' LIMIT 1);

-- 3. Atualizar campos categoria_*_id nos registros de Veiculo
--    para que novas projeções regeneradas também usem "Mobilidade"
UPDATE veiculo
SET
    categoria_combustivel_id  = (SELECT id FROM categoria WHERE nome = 'Mobilidade' LIMIT 1),
    ipva_categoria_id         = (SELECT id FROM categoria WHERE nome = 'Mobilidade' LIMIT 1),
    seguro_categoria_id       = (SELECT id FROM categoria WHERE nome = 'Mobilidade' LIMIT 1),
    licenciamento_categoria_id = (SELECT id FROM categoria WHERE nome = 'Mobilidade' LIMIT 1)
WHERE categoria_combustivel_id = (SELECT id FROM categoria WHERE nome = 'Transporte' LIMIT 1)
   OR ipva_categoria_id        = (SELECT id FROM categoria WHERE nome = 'Transporte' LIMIT 1)
   OR seguro_categoria_id      = (SELECT id FROM categoria WHERE nome = 'Transporte' LIMIT 1)
   OR licenciamento_categoria_id = (SELECT id FROM categoria WHERE nome = 'Transporte' LIMIT 1);

COMMIT;

-- Verificação (executar separadamente se desejar confirmar):
-- SELECT id, nome FROM categoria WHERE nome IN ('Mobilidade', 'Transporte');
-- SELECT COUNT(*) FROM despesa_prevista WHERE origem_tipo IN ('VEICULO','TRANSPORTE_APP')
--   AND categoria_id = (SELECT id FROM categoria WHERE nome = 'Mobilidade');
