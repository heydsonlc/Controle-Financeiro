// FIN-FIDELIDADE-CARTOES-1 — leitura do CSV no navegador com as regras do Flask (importacao_csv_parser).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
    PERFIL_CAIXA, PERFIL_MANUAL, PERFIL_NUBANK, converterTabela, decodificar, detectarDelimitador, detectarParcelamentoTexto,
    lerCsv, lerData, lerValor, normalizarClassificacao, normalizarDescricao, parcelaNubank,
} from '../../src/js/importacao-csv.js';

test('delimitador como o Sniffer do Flask (; , tab), com aspas', () => {
    assert.equal(detectarDelimitador('date,title,amount\n2029-05-01,"Loja; A",10.5\n'), ',');
    assert.equal(detectarDelimitador('Data;Descritivo;Credito;Debito\n01/05/2029;Loja, A;;10,50\n'), ';');
    assert.equal(detectarDelimitador('a\tb\n1\t2\n'), '\t');
    assert.equal(detectarDelimitador('sem delimitador\n'), ';');
});

test('leitura: cabecalho, linhas vazias fora, aspas e quebra de linha dentro do campo', () => {
    const t = lerCsv('date,title,amount\r\n2029-05-01,"Loja ""X""\nfilial",10.50\r\n\r\n,,\r\n2029-05-02,Padaria,3\r\n');
    assert.deepEqual(t.colunas, ['date', 'title', 'amount']);
    assert.equal(t.total_linhas, 2);
    assert.deepEqual(t.linhas_dados[0], ['2029-05-01', 'Loja "X"\nfilial', '10.50']);
    assert.throws(() => lerCsv('\n\n'), /CSV vazio/);
});

test('codificacao: UTF-8 (com BOM) ou Windows-1252', () => {
    assert.equal(decodificar(new Uint8Array([0xEF, 0xBB, 0xBF, 0x61, 0xC3, 0xA7])), 'aç');
    assert.equal(decodificar(new Uint8Array([0x61, 0xE7, 0xE3])), 'açã');
});

test('valores e datas como o Flask; data ambigua nunca vai para o banco interpretar', () => {
    assert.deepEqual(['1.234,56', '1234,56', '1234.56', 'R$ 10,00', '-15,90', '12,30D', '', '-', 'abc'].map(lerValor),
        ['1234.56', '1234.56', '1234.56', '10.00', '-15.90', '12.30', null, null, null]);
    assert.deepEqual(['2029-05-10', '10/05/2029', '10/05/29', '10-05-2029', '10.05.2029', '31/02/2029', '05/2029', ''].map(lerData),
        ['2029-05-10', '2029-05-10', '2029-05-10', '2029-05-10', '2029-05-10', null, null, null]);
});

test('parcelas na descricao (PARC, N/T, N DE T) e limpeza da descricao', () => {
    assert.deepEqual(normalizarDescricao('LOJA X PARC 03/10'), ['LOJA X', 3, 10]);
    assert.deepEqual(normalizarDescricao('LOJA Y 2/5 - '), ['LOJA Y', 2, 5]);
    assert.deepEqual(normalizarDescricao('CURSO 1 DE 12'), ['CURSO', 1, 12]);
    assert.deepEqual(normalizarDescricao('MERCADO'), ['MERCADO', 1, 1]);
    assert.equal(detectarParcelamentoTexto('LOJA 5/3'), null);  // fora do intervalo
    assert.equal(detectarParcelamentoTexto('LOJA 1/99'), null);  // acima de 60
    assert.equal(normalizarClassificacao('Pão de Açúcar*LJ 12'), 'pao de acucar lj 12');
});

test('perfis: Nubank (negativo e credito), Caixa (credito/debito) e manual', () => {
    const nubank = converterTabela(lerCsv('date,title,amount\n2029-05-01,Loja - Parcela 1/3,30.00\n2029-05-02,Pagamento recebido,-500.00\n2029-05-03,Zero,0\n'));
    assert.equal(nubank.perfil_detectado, PERFIL_NUBANK);
    assert.deepEqual(nubank.linhas.map((l) => [l.descricao_normalizada, l.parcela, l.valor, l.tipo_movimento, l.ignorar]),
        [['Loja', '1/3', '30.00', 'debito', false], ['Pagamento recebido', '1/1', '500.00', 'credito', true]]);
    const caixa = converterTabela(lerCsv('Data;Descritivo;Crédito;Débito\n01/05/2029;Loja;;10,50\n02/05/2029;Estorno;5,00;\n'));
    assert.equal(caixa.perfil_detectado, PERFIL_CAIXA);
    assert.deepEqual(caixa.linhas.map((l) => [l.data_compra, l.valor, l.tipo_movimento]), [['2029-05-01', '10.50', 'debito'], ['2029-05-02', '5.00', 'credito']]);
    const manual = converterTabela(lerCsv('quando;o que;quanto\n01/05/2029;Loja;10\n'));
    assert.equal(manual.perfil_detectado, PERFIL_MANUAL);
    assert.equal(manual.requer_mapeamento, true);
    assert.deepEqual(manual.linhas, []);
});

// FIN-CARTAO-NUBANK-PARCELADAS-01: o padrao efetivo do arquivo do Nubank (titulos FICTICIOS no formato real)
test('Nubank: parcela so no padrao do arquivo ("Loja - Parcela N/M"); outro numero no titulo e ambiguo', () => {
    assert.deepEqual(parcelaNubank('Haikar Veiculos - Parcela 5/6'), { parcela_atual: 5, total_parcelas: 6 });
    assert.equal(parcelaNubank('Mercado Xyz 03/10'), null);
    assert.equal(parcelaNubank('Loja - Parcela 7/5'), null);  // fora do intervalo
    const csv = ['date,title,amount', '2029-05-28,Shopee*Classic Comerci - Parcela 1/2,"79,70"',
        '2029-04-28,Mlp *Magalu-Samsung - Parcela 9/10,"482,80"', '2029-04-28,Anacapri Goiania - Parcela 3/3,"83,30"',
        '2029-05-18,Allianz Segu*02 de,"259,46"', '2029-05-10,Mercado Xyz 03/10,"50,00"', '2029-05-11,Evento 15/11,"20,00"',
        '2029-05-12,Pao de Acucar-2378,"75,78"'].join('\n');
    const linhas = converterTabela(lerCsv(csv)).linhas;
    assert.deepEqual(linhas.map((l) => [l.descricao_normalizada, l.parcela, l.parcela_ambigua || null]), [
        ['Shopee*Classic Comerci', '1/2', null], ['Mlp *Magalu-Samsung', '9/10', null], ['Anacapri Goiania', '3/3', null],
        ['Allianz Segu*02 de', '1/1', null],
        ['Mercado Xyz', '1/1', { parcela_atual: 3, total_parcelas: 10 }],  // pode ser data, codigo ou parcela: revisar
        ['Evento 15/11', '1/1', null], ['Pao de Acucar-2378', '1/1', null]]);
    // Caixa e manual seguem a regra do Flask (N/T no texto e parcela)
    const caixa = converterTabela(lerCsv('Data;Descritivo;Crédito;Débito\n01/05/2029;Loja 1/3;;10,50\n')).linhas[0];
    assert.deepEqual([caixa.parcela, caixa.parcela_ambigua], ['1/3', undefined]);
});
