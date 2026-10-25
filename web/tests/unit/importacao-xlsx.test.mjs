// FIN-FIDELIDADE-CARTOES-2 — leitura de XLSX no navegador (sem biblioteca), com as regras do Flask (openpyxl, data_only).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { converterTabela } from '../../src/js/importacao-csv.js';
import { lerPlanilha } from '../../src/js/importacao-xlsx.js';
import { gerarXlsx } from '../xlsx-ficticio.mjs';

const buffer = (b) => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);

test('planilha ativa, cabecalho, datas por estilo, numeros, texto compartilhado e inline, linhas vazias fora', async () => {
    const arquivo = gerarXlsx([
        { nome: 'Resumo', linhas: [['nada'], ['aqui']] },
        { nome: 'Lancamentos', linhas: [
            ['date', 'title', 'amount'],
            [{ data: '2033-03-05' }, 'Padaria & Cia', 12.5],
            [null, null, null],
            [{ data: '2033-03-06' }, { inline: 'Loja 2/5' }, 30],
            ['2033-03-07', 'Pagamento recebido', -500],
        ] },
    ], { ativa: 1 });
    const t = await lerPlanilha(buffer(arquivo));
    assert.deepEqual(t.colunas, ['date', 'title', 'amount']);
    assert.deepEqual(t.linhas_dados, [['2033-03-05', 'Padaria & Cia', '12.5'], ['2033-03-06', 'Loja 2/5', '30'],
        ['2033-03-07', 'Pagamento recebido', '-500']]);
    const conv = converterTabela(t, 'xlsx');
    assert.deepEqual(conv.linhas.map((l) => [l.data_compra, l.descricao_normalizada, l.parcela, l.valor, l.tipo_movimento, l.origem_importacao]), [
        ['2033-03-05', 'Padaria & Cia', '1/1', '12.50', 'debito', 'xlsx'],
        ['2033-03-06', 'Loja', '2/5', '30.00', 'debito', 'xlsx'],
        ['2033-03-07', 'Pagamento recebido', '1/1', '500.00', 'credito', 'xlsx'],
    ]);
});

test('perfil Caixa (credito/debito) e celulas fora de ordem com colunas vazias', async () => {
    const arquivo = gerarXlsx([{ nome: 'Fatura', linhas: [
        ['Data', 'Descritivo', 'Crédito', 'Débito'],
        [{ data: '2033-03-01' }, 'Mercado', null, 10.5],
        [{ data: '2033-03-02' }, 'Estorno mercado', 10.5, null],
    ] }]);
    const conv = converterTabela(await lerPlanilha(buffer(arquivo)), 'xlsx');
    assert.equal(conv.perfil_detectado, 'caixa_credito_debito');
    assert.deepEqual(conv.linhas.map((l) => [l.valor, l.tipo_movimento]), [['10.50', 'debito'], ['10.50', 'credito']]);
});

test('arquivo invalido, vazio ou sem lancamentos: mensagens do Flask', async () => {
    await assert.rejects(lerPlanilha(new TextEncoder().encode('nao e zip').buffer), /XLSX inválido/);
    await assert.rejects(lerPlanilha(buffer(gerarXlsx([{ nome: 'A', linhas: [[null]] }]))), /XLSX vazio ou sem dados reconheciveis/);
    await assert.rejects(lerPlanilha(buffer(gerarXlsx([{ nome: 'A', linhas: [['date', 'title', 'amount']] }]))), /XLSX sem linhas de lancamentos/);
});
