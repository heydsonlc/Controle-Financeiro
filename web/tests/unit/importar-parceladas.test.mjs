// FIN-CARTAO-NUBANK-PARCELADAS-01 — previa da importacao na tela original (js/original/importar_cartao.js do Flask,
// carregado sem alteracao): a compra parcelada classificada pelo banco entra na confirmacao (antes ficava retida como
// "possivel parcelamento fora deste MVP"); o numero ambiguo pede a decisao; sem os campos novos (Flask), como antes.
// Dados FICTICIOS.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const ORIGINAL = new URL('../../../frontend/static/js/importar_cartao.js', import.meta.url);

function carregar() {
    const nada = () => {};
    const campos = { cartaoSelect: { value: '910' }, competenciaInput: { value: '05/2029' } };
    const contexto = {
        console, setTimeout, clearTimeout, URLSearchParams, Intl, alert: (m) => contexto.alertas.push(m), confirm: () => true,
        document: { addEventListener: nada, getElementById: (id) => campos[id] || null, querySelector: () => null, querySelectorAll: () => [] },
        location: { search: '', pathname: '/importar_cartao.html' }, localStorage: { getItem: () => null, setItem: nada },
        alertas: [],
    };
    contexto.window = contexto;
    vm.createContext(contexto);
    vm.runInContext(readFileSync(ORIGINAL, 'utf8'), contexto);
    contexto.recalcularConfrontoAtual = () => { contexto.estadoTeste.analiseConfronto = contexto.montarAnaliseConfronto(); };
    return contexto;
}

const ctx = carregar();
const estado = vm.runInContext('estado', ctx);
ctx.estadoTeste = estado;
const dados = (v) => JSON.parse(JSON.stringify(v));

const analise = (extra) => ({
    linha_id: 'csv-1', linha_origem: 1, status: 'valido', data_compra: '2029-04-28', descricao_original: 'Haikar Veiculos - Parcela 5/6',
    descricao_normalizada: 'Haikar Veiculos', descricao_exibida: 'Haikar Veiculos', valor: 416.81, categoria_id: 952,
    parcela_atual: 5, total_parcelas: 6, parcela: '5/6', tipo_movimento: 'debito', classificacao_importacao: 'PARCELADA', ...extra,
});
const PARCELADA = analise();
const SEM_CATEGORIA = analise({ linha_id: 'csv-2', linha_origem: 2, descricao_original: 'Detroit T9 - Parcela 2/4',
    descricao_normalizada: 'Detroit T9', descricao_exibida: 'Detroit T9', valor: 314.07, parcela_atual: 2, total_parcelas: 4,
    parcela: '2/4', categoria_id: null, status: 'revisar', categoria_pendente: true });
const AMBIGUA = analise({ linha_id: 'csv-3', linha_origem: 3, descricao_original: 'Mercado Xyz 03/10', descricao_normalizada: 'Mercado Xyz',
    descricao_exibida: 'Mercado Xyz', valor: 50, parcela_atual: 1, total_parcelas: 1, parcela: '1/1', status: 'revisar',
    classificacao_importacao: 'REVISAR', parcela_ambigua: { parcela_atual: 3, total_parcelas: 10, rotulo: '03/10' } });
const COMUM = analise({ linha_id: 'csv-4', linha_origem: 4, descricao_original: 'Padaria', descricao_normalizada: 'Padaria',
    descricao_exibida: 'Padaria', valor: 8, parcela_atual: 1, total_parcelas: 1, parcela: '1/1', classificacao_importacao: 'COMPRA' });

function preparar(linhas) {
    estado.linhasMapeadas = linhas.map((l) => ctx.converterLinhaIntermediaria(l));
    estado.recorrenciasCartao = [{ id: 456, nome: 'Netflix', valor: 59.9 }];
    estado.analiseConfronto = ctx.montarAnaliseConfronto();
    ctx.alertas.length = 0;
    return estado.linhasMapeadas;
}

const enviadas = () => dados(ctx.montarPayloadImportacao().linhas).map((l) => [l.descricao, l.numero_parcela, l.total_parcelas,
    l.natureza_parcela || null]);

test('compra parcelada do banco entra na confirmacao (nao fica retida como possivel parcelamento)', () => {
    preparar([PARCELADA, COMUM]);
    assert.equal(estado.analiseConfronto.parcelamentos.length, 0);
    assert.equal(estado.analiseConfronto.parceladas.length, 1);
    const info = ctx.obterInfoOperacional(estado.linhasMapeadas[0], 0);
    assert.deepEqual([info.status, info.tipo, info.filtro, info.sugestao, info.categoriaEditavel],
        ['Compra parcelada', 'Compra parcelada', 'parcelados', 'Parcela 05/06', true]);
    assert.deepEqual(enviadas(), [['Padaria', 1, 1, null], ['Haikar Veiculos', 5, 6, null]]);
    assert.equal(ctx.validarNovosClassificados(), true);
});

test('categoria da despesa obrigatoria tambem na parcela', () => {
    preparar([SEM_CATEGORIA]);
    assert.equal(ctx.novasSemCategoriaDespesa().length, 1);
    assert.equal(ctx.validarNovosClassificados(), false);
    assert.match(ctx.alertas[0], /categoria da despesa/);
    estado.linhasMapeadas[0].categoria_id = 952;  // escolhida na celula da linha
    assert.equal(ctx.novasSemCategoriaDespesa().length, 0);
    assert.deepEqual(enviadas(), [['Detroit T9', 2, 4, null]]);
});

test('numero ambiguo: revisar ate a decisao; parcelada (com o numero do texto) ou a vista', () => {
    preparar([AMBIGUA]);
    const linha = estado.linhasMapeadas[0];
    const info = ctx.obterInfoOperacional(linha, 0);
    assert.deepEqual([info.status, info.sugestao], ['Revisar', 'Possível parcela 03/10: parcelada ou à vista?']);
    assert.equal(ctx.validarNovosClassificados(), false);
    assert.match(ctx.alertas[0], /possivel\(is\) parcela/);
    assert.deepEqual(enviadas(), [['Mercado Xyz', 1, 1, null]]);  // o banco recusa sem a decisao (nada em silencio)

    ctx.definirNaturezaParcela(0, 'PARCELADA');
    assert.deepEqual([linha.classificacao_importacao, linha.parcela, ctx.obterInfoOperacional(linha, 0).status],
        ['PARCELADA', '3/10', 'Compra parcelada']);
    assert.deepEqual(enviadas(), [['Mercado Xyz', 3, 10, 'PARCELADA']]);
    assert.equal(ctx.validarNovosClassificados(), true);

    preparar([AMBIGUA]);
    ctx.definirNaturezaParcela(0, 'AVISTA');
    assert.deepEqual([estado.linhasMapeadas[0].classificacao_importacao, estado.analiseConfronto.novos.length], ['COMPRA', 1]);
    assert.deepEqual(enviadas(), [['Mercado Xyz', 1, 1, 'AVISTA']]);
    assert.equal(dados(ctx.montarPayloadImportacao().linhas)[0].parcela_ambigua.rotulo, '03/10');
});

test('parcela mantida como compra diferente volta como compra parcelada', () => {
    preparar([analise({ status: 'conciliado', classificacao_importacao: 'PARCELA_EXISTENTE',
        conciliacao: { lancamento_id: 7, descricao: 'Haikar', valor: 416.81 } })]);
    const linha = estado.linhasMapeadas[0];
    linha.reconhecimento_match = { tipo: 'duplicado_atual', score: 90 };
    assert.equal(ctx.linhaMantivel(linha), true);
    ctx.manterComoCompraDiferente(0);
    assert.equal(estado.analiseConfronto.parceladas.length, 1);
    assert.equal(dados(ctx.montarPayloadImportacao().linhas)[0].manter_conciliada, true);
});

test('linha do Flask (sem a classificacao do banco) fica como antes: possivel parcelamento, fora da confirmacao', () => {
    const { classificacao_importacao, ...flask } = PARCELADA;  // eslint-disable-line no-unused-vars
    preparar([flask]);
    assert.equal(estado.analiseConfronto.parcelamentos.length, 1);
    assert.equal(ctx.obterInfoOperacional(estado.linhasMapeadas[0], 0).status, 'Parcelado');
    assert.deepEqual(enviadas(), []);
});
