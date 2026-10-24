// FIN-CARTOES-FECHAMENTO-1 — decisoes de tela da fatura sugerida (modulo puro src/js/fechamento.js).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
    confirmacoes, consolidadaDoErro, mesSemSugestao, textoConsolidada, textoRegra, textoSugestao,
} from '../../src/js/fechamento.js';

const SUGERIDA = {
    situacao: 'SUGERIDA', competencia: '2026-12-01', fechamento: '2026-11-25', vencimento: '2026-12-05',
    fatura_situacao: 'ABERTA',
};
const sp = (texto) => texto.replace(/\s/g, ' ');  // Intl usa espaco nao separavel depois de R$

test('sugestao mostra fatura, fechamento e vencimento do ciclo', () => {
    assert.deepEqual(textoSugestao(SUGERIDA), {
        texto: 'Sugerida pelo fechamento: fatura 12/2026 (fecha 25/11, vence 05/12).', alerta: false,
    });
});

test('escolha manual diferente da sugerida e sinalizada, nunca trocada', () => {
    const { texto, alerta } = textoSugestao(SUGERIDA, { manual: true, escolhido: '2027-01' });
    assert.match(texto, /Mês escolhido: 01\/2027\.$/);
    assert.equal(alerta, false);
    // escolher manualmente o mesmo mes da sugestao nao gera aviso
    assert.doesNotMatch(textoSugestao(SUGERIDA, { manual: true, escolhido: '2026-12' }).texto, /escolhido/);
});

test('fatura sugerida consolidada ou paga e avisada', () => {
    const fechada = textoSugestao({ ...SUGERIDA, fatura_situacao: 'FECHADA' });
    assert.match(fechada.texto, /consolidada: a inclusão pede confirmação/);
    assert.equal(fechada.alerta, true);
    assert.match(textoSugestao({ ...SUGERIDA, fatura_situacao: 'PAGA' }).texto, /já está paga: a compra vai para a próxima/);
});

test('sem sugestao: cartao nao confirmado, ciclo ambiguo, sem dias e falha da consulta', () => {
    for (const [situacao, trecho] of [['NAO_CONFIRMADO', /ainda não confirmado/], ['CICLO_AMBIGUO', /não definem a fatura/],
        ['SEM_CONFIGURACAO', /sem dias de fechamento/], ['INDISPONIVEL', /Não foi possível sugerir/]]) {
        const { texto, alerta } = textoSugestao({ situacao, competencia: null });
        assert.match(texto, trecho, situacao);
        assert.equal(alerta, true, situacao);
    }
    assert.deepEqual(textoSugestao(null), { texto: '', alerta: false });
    assert.deepEqual(textoSugestao({ situacao: 'SEM_DATA' }), { texto: '', alerta: false });
});

test('sem sugestao o mes nunca vem de outro cartao: ambiguo esvazia, nao confirmado volta ao padrao da tela', () => {
    assert.equal(mesSemSugestao('CICLO_AMBIGUO', '2031-05'), '');
    assert.equal(mesSemSugestao('NAO_CONFIRMADO', '2031-05'), '2031-05');
    assert.equal(mesSemSugestao('SEM_CONFIGURACAO', '2031-05'), '2031-05');
    assert.equal(mesSemSugestao('INDISPONIVEL', '2031-05'), '2031-05');
});

test('confirmacao da fatura consolidada leva o total visto, uma por fatura', () => {
    const consolidadas = [
        { fatura_id: 7, competencia: '2029-11-01', total_consolidado: 40, valor_incluido: 10, total_novo: 50, caixa: {} },
        { fatura_id: 8, competencia: '2029-12-01', total_consolidado: 1234.5, valor_incluido: 10, total_novo: 1244.5 },
    ];
    assert.deepEqual(confirmacoes(consolidadas), [
        { fatura_id: 7, total_consolidado: '40' }, { fatura_id: 8, total_consolidado: '1234.5' },
    ]);
    assert.deepEqual(confirmacoes(null), []);
    assert.equal(sp(textoConsolidada(consolidadas[1])),
        'Incluir na fatura consolidada 12/2029: total R$ 1.234,50 passa a R$ 1.244,50 (inclusão de R$ 10,00).');
});

test('erro do banco com HINT CONSOLIDADA traz a fatura; outros erros nao', () => {
    const detalhe = { fatura_id: 7, competencia: '2029-11-01', total_consolidado: 40, valor_incluido: 10, total_novo: 50 };
    assert.deepEqual(consolidadaDoErro({ code: 'P0001', hint: 'CONSOLIDADA', details: JSON.stringify(detalhe) }), detalhe);
    assert.equal(consolidadaDoErro({ code: 'P0001', hint: 'CONSOLIDADA', details: 'texto' }), null);
    assert.equal(consolidadaDoErro({ code: 'P0001', hint: null, details: JSON.stringify(detalhe) }), null);
    assert.equal(consolidadaDoErro(null), null);
});

test('regra do dia do fechamento em texto', () => {
    assert.equal(textoRegra('ATUAL'), 'Entra na fatura que está fechando');
    assert.equal(textoRegra('PROXIMO'), 'Vai para a próxima fatura');
    assert.equal(textoRegra(undefined), 'Vai para a próxima fatura');  // padrao conservador
});
