// FIN-MVP-MOBILE-03 — regras de leitura da fatura do cartao (js/cartoes-grupos.js): os grupos sao os do banco
// (fatura_por_categoria), na mesma ordem e com o mesmo executado; cada compra cai no grupo pelo criterio do filtro
// "Ver lancamentos" do desktop (lancamentos_fatura_por_categoria). A equivalencia com o banco real e conferida no E2E
// (mobile03_cartoes.spec.mjs); aqui, os casos de borda com dados ficticios.
import assert from 'node:assert/strict';
import test from 'node:test';

import {
    cartoesDaFatura, chaveDoLancamento, filtrarLancamentos, filtrosAtivos, legendaDaCompra, montarGruposFatura,
    rotuloCartaoDoContrato, situacaoDaCobranca, situacaoDaFatura,
} from '../../src/js/cartoes-grupos.js';

// Resumo como o banco devolve (tipo_grupo, natureza, chave do filtro em categoria_cartao_id)
const RESUMO = {
    total_compras: 1215.4, total_creditos: 20, total_fatura: 1195.4,
    por_cartao: [
        { cartao_vinculado_id: 7, final: '1234', tipo: 'FISICO', total: 900 },
        { cartao_vinculado_id: null, final: null, tipo: null, total: 295.4 },
    ],
    categorias: [
        { categoria_cartao_id: 350, categoria_cartao_nome: 'Mercado F', natureza: 'CATEGORIA', tipo_grupo: 'categoria_cartao',
            vinculada_ao_cartao: true, limite_mensal: 500, disponivel: 224.5, gasto_atual: 275.5, quantidade_lancamentos: 2 },
        { categoria_cartao_id: 352, categoria_cartao_nome: 'Viagem F', natureza: 'CATEGORIA', tipo_grupo: 'categoria_cartao',
            vinculada_ao_cartao: true, limite_mensal: 300, disponivel: 300, gasto_atual: 0, quantidade_lancamentos: 0 },
        { categoria_cartao_id: 351, categoria_cartao_nome: 'Restaurantes F', natureza: 'CATEGORIA', tipo_grupo: 'categoria_sem_limite',
            vinculada_ao_cartao: false, limite_mensal: 0, disponivel: null, gasto_atual: 120, quantidade_lancamentos: 1 },
        { categoria_cartao_id: 'compras_parceladas', categoria_cartao_nome: 'Compras parceladas', natureza: 'PARCELADA',
            tipo_grupo: 'compras_parceladas', limite_mensal: null, disponivel: null, gasto_atual: 90, quantidade_lancamentos: 1 },
        { categoria_cartao_id: 'despesas_fixas', categoria_cartao_nome: 'Despesas fixas', natureza: 'FIXA', tipo_grupo: 'despesas_fixas',
            limite_mensal: null, disponivel: null, gasto_atual: 39.9, quantidade_lancamentos: 2 },
        { categoria_cartao_id: null, categoria_cartao_nome: 'Sem Categoria do Cartao', natureza: 'OUTROS', tipo_grupo: 'sem_categoria',
            sem_categoria: true, limite_mensal: null, disponivel: null, gasto_atual: 690, quantidade_lancamentos: 1 },
        { categoria_cartao_id: 'creditos', categoria_cartao_nome: 'Creditos e ajustes', natureza: 'CREDITO', tipo_grupo: 'creditos',
            limite_mensal: null, disponivel: null, gasto_atual: -20, quantidade_lancamentos: 1 },
    ],
};

const compra = (id, natureza, extra = {}) => ({ id, natureza, descricao: `Compra ${id}`, valor: 10, valor_executado: 10,
    data: '2031-04-02', status_classificacao: 'classificado', situacao_ocorrencia: null, cartao_vinculado: null, ...extra });

const LANCAMENTOS = [
    compra(1, 'CATEGORIA', { categoria_cartao_id: 350, valor: 240, valor_executado: 240, cartao_vinculado: { id: 7, final: '1234' } }),
    compra(2, 'CATEGORIA', { categoria_cartao_id: 350, valor: 35.5, valor_executado: 35.5 }),
    compra(3, 'CATEGORIA', { categoria_cartao_id: 351, valor: 120, valor_executado: 120, status_classificacao: 'categoria_sem_limite' }),
    compra(4, 'PARCELADA', { categoria_cartao_id: 350, valor: 90, valor_executado: 90, parcela_atual: 1, parcelas_total: 6,
        cartao_vinculado: { id: 7, final: '1234' } }),
    compra(5, 'FIXA', { valor: 39.9, valor_executado: 39.9, situacao_ocorrencia: 'PREVISTA' }),
    compra(6, 'FIXA', { valor: 15, valor_executado: 0, situacao_ocorrencia: 'NAO_COBRADA' }),
    compra(7, 'OUTROS', { categoria_cartao_id: null, valor: 690, valor_executado: 690, status_classificacao: 'sem_categoria_cartao',
        cartao_vinculado: { id: 7, final: '1234' } }),
    { id: 'credito-1', natureza: 'CREDITO', descricao: 'Estorno', valor: -20, valor_executado: -20, data: '2031-04-08',
        status_classificacao: 'classificado', cartao_vinculado: null },
];

test('grupos do banco na mesma ordem, rotulos e executado; cada compra no grupo do filtro do desktop', () => {
    const grupos = montarGruposFatura(RESUMO, LANCAMENTOS);
    assert.deepEqual(grupos.map((g) => [g.chave, g.rotulo, g.quantidade, g.total_centavos]), [
        ['350', 'Mercado F', 2, 27550],
        ['352', 'Viagem F', 0, 0],  // categoria com limite e sem compra: aparece, como no desktop
        ['351', 'Restaurantes F', 1, 12000],
        ['compras_parceladas', 'Compras parceladas', 1, 9000],  // parcelada classificada fica so em parceladas
        ['despesas_fixas', 'Despesas fixas', 2, 3990],  // a nao cobrada vale 0 no executado
        ['sem_categoria', 'Sem Categoria do Cartão', 1, 69000],
        ['creditos', 'Créditos e ajustes', 1, -2000],
    ]);
    assert.deepEqual(grupos.map((g) => g.itens.map((l) => l.id)), [[1, 2], [], [3], [4], [5, 6], [7], ['credito-1']]);
    // Sem filtro, o total do grupo e o do banco e bate com a soma dos executados das compras dele.
    for (const g of grupos) {
        assert.equal(g.itens.reduce((s, l) => s + Math.round(l.valor_executado * 100), 0), g.total_centavos, g.chave);
    }
    assert.deepEqual([grupos[0].limite_centavos, grupos[0].disponivel_centavos], [50000, 22450]);
    assert.equal(grupos[2].limite_centavos, null, 'categoria sem limite: sem linha de limite');
});

test('nenhuma compra fica de fora: o que nao casa com um grupo do resumo vai para Outros lancamentos', () => {
    const extra = compra(9, 'CATEGORIA', { categoria_cartao_id: 999, valor: 5, valor_executado: 5 });
    const grupos = montarGruposFatura(RESUMO, [...LANCAMENTOS, extra]);
    const ultimo = grupos[grupos.length - 1];
    assert.deepEqual([ultimo.chave, ultimo.itens.map((l) => l.id), ultimo.total_centavos], ['outros', [9], 500]);
    assert.equal(grupos.flatMap((g) => g.itens).length, LANCAMENTOS.length + 1);
    assert.deepEqual(montarGruposFatura(null, []), []);
});

test('filtros: cartao do contrato e situacao; so grupos com compras visiveis, total das visiveis', () => {
    assert.equal(filtrosAtivos({}), false);
    assert.equal(filtrosAtivos({ vinculado: '', situacao: '' }), false);
    const doFisico = montarGruposFatura(RESUMO, LANCAMENTOS, { vinculado: '7' });
    assert.deepEqual(doFisico.map((g) => [g.chave, g.itens.map((l) => l.id), g.total_centavos]),
        [['350', [1], 24000], ['compras_parceladas', [4], 9000], ['sem_categoria', [7], 69000]]);
    // '0' = sem cartao identificado (o filtro cartao-0 do desktop), inclusive os creditos
    assert.deepEqual(filtrarLancamentos(LANCAMENTOS, { vinculado: '0' }).map((l) => l.id), [2, 3, 5, 6, 'credito-1']);
    assert.deepEqual(filtrarLancamentos(LANCAMENTOS, { situacao: 'revisar' }).map((l) => l.id), [3, 7]);
    assert.deepEqual(filtrarLancamentos(LANCAMENTOS, { situacao: 'prevista' }).map((l) => l.id), [5]);
    assert.deepEqual(montarGruposFatura(RESUMO, LANCAMENTOS, { vinculado: '7', situacao: 'prevista' }), []);
});

test('chaves, cartoes do contrato e textos da linha e do detalhe', () => {
    assert.deepEqual(LANCAMENTOS.map(chaveDoLancamento), ['350', '350', '351', 'compras_parceladas', 'despesas_fixas',
        'despesas_fixas', 'sem_categoria', 'creditos']);
    assert.deepEqual(cartoesDaFatura(RESUMO).map(rotuloCartaoDoContrato), ['•••• 1234 · Físico', 'Sem cartão identificado']);
    assert.deepEqual(cartoesDaFatura({ por_cartao: [{ cartao_vinculado_id: null, total: 10 }] }), [], 'sem cartao identificado: sem filtro');
    assert.deepEqual(LANCAMENTOS.map(legendaDaCompra), ['02/04 · à vista · •••• 1234', '02/04 · à vista', '02/04 · à vista',
        '02/04 · 1/6 · •••• 1234', '02/04 · prevista', '02/04 · não cobrada', '02/04 · à vista · •••• 1234', '08/04 · crédito']);
    assert.deepEqual(LANCAMENTOS.map(situacaoDaCobranca), ['Lançada', 'Lançada', 'Lançada', 'Lançada',
        'Prevista · aguardando cobrança', 'Prevista · não cobrada nesta fatura', 'Lançada', 'Crédito da fatura']);
    assert.equal(situacaoDaCobranca({ natureza: 'FIXA', situacao_ocorrencia: 'CONFIRMADA' }), 'Cobrada');
    assert.equal(situacaoDaCobranca({ natureza: 'CATEGORIA', origem: 'csv' }), 'Importada');
});

test('situacao da fatura: paga, vencida, fechada, aberta ou sem fatura', () => {
    assert.equal(situacaoDaFatura(null, null, '2031-04-10'), 'Sem fatura');
    assert.equal(situacaoDaFatura({ pago: true, data_pagamento: '2031-04-18' }, null, '2031-05-01'), 'Paga em 18/04');
    assert.equal(situacaoDaFatura({ pago: false, data_vencimento: '2031-04-20' }, { situacao_fatura: 'FECHADA' }, '2031-04-21'), 'Vencida');
    assert.equal(situacaoDaFatura({ pago: false, data_vencimento: '2031-04-20' }, { situacao_fatura: 'FECHADA' }, '2031-04-15'), 'Fechada');
    assert.equal(situacaoDaFatura({ pago: false, data_vencimento: '2031-04-20' }, { situacao_fatura: 'ABERTA' }, '2031-04-15'), 'Aberta');
});
