-- CARTAO-CLEAN-1
-- Auditoria nao destrutiva do legado ItemAgregado / OrcamentoAgregado.
-- Nao execute DROP/ALTER destrutivo a partir deste arquivo.

SELECT
    COUNT(*) AS total_itens_agregados
FROM item_agregado;

SELECT
    COUNT(*) AS total_orcamentos_agregados
FROM orcamento_agregado;

SELECT
    COUNT(*) AS lancamentos_com_item_agregado_id
FROM lancamento_agregado
WHERE item_agregado_id IS NOT NULL;

SELECT
    COUNT(*) AS lancamentos_sem_categoria_cartao_id
FROM lancamento_agregado
WHERE categoria_cartao_id IS NULL;

SELECT
    cartao_id,
    COUNT(*) AS total_lancamentos_com_legado
FROM lancamento_agregado
WHERE item_agregado_id IS NOT NULL
GROUP BY cartao_id
ORDER BY total_lancamentos_com_legado DESC;

SELECT
    ia.item_despesa_id AS cartao_id,
    COUNT(*) AS total_categorias_legadas
FROM item_agregado ia
GROUP BY ia.item_despesa_id
ORDER BY total_categorias_legadas DESC;

SELECT
    oa.item_agregado_id,
    COUNT(*) AS total_orcamentos,
    MIN(oa.mes_referencia) AS primeiro_mes,
    MAX(oa.mes_referencia) AS ultimo_mes
FROM orcamento_agregado oa
GROUP BY oa.item_agregado_id
ORDER BY total_orcamentos DESC;
