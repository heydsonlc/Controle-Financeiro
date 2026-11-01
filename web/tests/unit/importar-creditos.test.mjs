// FIN-CARTAO-NUBANK-CREDITOS-01 — previa da importacao na tela original (js/original/importar_cartao.js do Flask,
// carregado sem alteracao): o credito que o banco abate da fatura (estorno, IOF devolvido, ajuste) entra na confirmacao
// com a natureza e a compra original; mais de uma candidata pede a escolha; o pagamento recebido continua retirado, com o
// motivo; sem os campos novos (Flask), o credito fica retirado como antes. Dados FICTICIOS.
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

const APPLE = { id: 621, descricao: 'Apple.Com/Bill', valor: 799.9, data_compra: '2029-05-26', fatura: '05/2029', estornavel: 799.9 };
const APPLE2 = { id: 685, descricao: 'Apple.Com/Bill', valor: 129.9, data_compra: '2029-05-06', fatura: '05/2029', estornavel: 129.9 };
const credito = (extra) => ({
    linha_id: 'csv-1', linha_origem: 1, status: 'valido', data_compra: '2029-05-26', descricao_original: 'IOF de volta de Cloudflare',
    descricao_normalizada: 'IOF de volta de Cloudflare', descricao_exibida: 'IOF de volta de Cloudflare', valor: 0.99,
    parcela_atual: 1, total_parcelas: 1, tipo_movimento: 'credito', ignorar: false, classificacao_importacao: 'CREDITO',
    mensagens: [], credito: { natureza: 'IOF_DEVOLVIDO', rotulo: 'Devolucao de IOF', fatura_destino: '05/2029',
        compra: { id: 620, descricao: 'IOF de "Cloudflare"', valor: 0.99 }, candidatas: [{ id: 620, descricao: 'IOF de "Cloudflare"', valor: 0.99 }],
        parcial: false }, ...extra,
});
const IOF = credito();
const ESTORNO = credito({ linha_id: 'csv-2', linha_origem: 2, descricao_original: 'Estorno de "Apple.Com/Bill" (Apple)',
    descricao_normalizada: 'Estorno de "Apple.Com/Bill" (Apple)', descricao_exibida: 'Estorno de "Apple.Com/Bill" (Apple)', valor: 50.22,
    status: 'revisar', classificacao_importacao: 'REVISAR',
    credito: { natureza: 'ESTORNO', rotulo: 'Estorno de compra', fatura_destino: '05/2029', compra: null, candidatas: [APPLE, APPLE2] } });
const PAGAMENTO = credito({ linha_id: 'csv-3', linha_origem: 3, descricao_original: 'Pagamento recebido', valor: 12099.02,
    status: 'ignorado', ignorar: true, classificacao_importacao: 'IGNORADA', credito: null,
    mensagens: ['Pagamento da fatura: nao e compra nem credito desta fatura; o pagamento e registrado em Despesas (pagar fatura).'] });

function preparar(linhas) {
    estado.linhasMapeadas = linhas.map((l) => ctx.converterLinhaIntermediaria(l));
    estado.recorrenciasCartao = [];
    estado.analiseConfronto = ctx.montarAnaliseConfronto();
    ctx.alertas.length = 0;
    return estado.linhasMapeadas;
}

const enviadas = () => dados(ctx.montarPayloadImportacao().linhas).map((l) => [l.descricao_original, l.valor, l.tipo_movimento,
    l.credito_compra_id ?? null]);

test('credito do banco entra na confirmacao, com a natureza e a compra original', () => {
    preparar([IOF]);
    assert.equal(estado.analiseConfronto.creditos.length, 1);
    assert.equal(ctx.linhaRetiradaEfetivacao(estado.linhasMapeadas[0]), false);
    const info = ctx.obterInfoOperacional(estado.linhasMapeadas[0], 0);
    assert.deepEqual([info.status, info.tipo, info.categoriaEditavel], ['Crédito', 'Devolucao de IOF', false]);
    assert.match(info.sugestao, /^Devolucao de IOF · abate R\$\s0,99 da fatura 05\/2029 · compra original: IOF de "Cloudflare" \(R\$\s0,99\)$/);
    assert.deepEqual(enviadas(), [['IOF de volta de Cloudflare', '0.99', 'credito', null]]);
    assert.equal(ctx.validarNovosClassificados(), true);  // credito nao pede Categoria de Despesa
});

test('mais de uma compra candidata: revisar ate a escolha (ou sem compra vinculada)', () => {
    preparar([ESTORNO]);
    const linha = estado.linhasMapeadas[0];
    assert.equal(ctx.obterInfoOperacional(linha, 0).status, 'Revisar');
    assert.match(ctx.seletorCompraCredito(linha, 0), /Escolha a compra original.*Apple\.Com\/Bill · 2029-05-26.*Sem compra vinculada/s);
    assert.equal(ctx.validarNovosClassificados(), false);
    assert.match(ctx.alertas[0], /Escolha a compra original de 1 credito/);

    ctx.escolherCompraCredito(0, '685');
    assert.deepEqual([linha.classificacao_importacao, linha.credito.compra.id, linha.credito.parcial], ['CREDITO', 685, true]);
    assert.match(ctx.obterInfoOperacional(linha, 0).sugestao, /compra original: Apple\.Com\/Bill \(R\$\s129,90\), parcial$/);
    assert.deepEqual(enviadas(), [['Estorno de "Apple.Com/Bill" (Apple)', '50.22', 'credito', 685]]);
    assert.equal(ctx.validarNovosClassificados(), true);

    ctx.escolherCompraCredito(0, '0');
    assert.match(ctx.obterInfoOperacional(linha, 0).sugestao, /sem compra vinculada$/);
    assert.deepEqual(enviadas(), [['Estorno de "Apple.Com/Bill" (Apple)', '50.22', 'credito', 0]]);

    ctx.escolherCompraCredito(0, '');  // de volta a proposta do banco
    assert.deepEqual([linha.classificacao_importacao, linha.credito_compra_id], ['REVISAR', undefined]);
});

test('pagamento recebido continua retirado, com o motivo do banco; credito retirado pelo usuario fica fora', () => {
    preparar([PAGAMENTO, IOF]);
    const [pagamento, iof] = estado.linhasMapeadas;
    assert.equal(ctx.linhaRetiradaEfetivacao(pagamento), true);
    assert.match(ctx.observacaoRetiradaLinha(pagamento), /^Pagamento da fatura: nao e compra nem credito desta fatura/);
    iof.ignorar = true;
    estado.analiseConfronto = ctx.montarAnaliseConfronto();
    assert.deepEqual(enviadas(), []);
});

test('linha do Flask (sem a classificacao do banco): o credito fica retirado como antes', () => {
    const { classificacao_importacao, credito: _c, ...flask } = IOF;  // eslint-disable-line no-unused-vars
    preparar([flask]);
    assert.equal(ctx.linhaRetiradaEfetivacao(estado.linhasMapeadas[0]), true);
    assert.equal(ctx.motivoRetiradaLinha(estado.linhasMapeadas[0]), 'Crédito/estorno');
    assert.deepEqual(enviadas(), []);
});

test('credito repetido legitimo no arquivo (tres ajustes de R$ 0,01): mantido continua credito', () => {
    const ajuste = (n, extra) => credito({ linha_id: `csv-${n}`, linha_origem: n, descricao_original: 'AJUSTE CREDITO PARC. LOJISTAA',
        descricao_normalizada: 'AJUSTE CREDITO PARC. LOJISTAA', descricao_exibida: 'AJUSTE CREDITO PARC. LOJISTAA', valor: 0.01,
        credito: { natureza: 'AJUSTE', rotulo: 'Credito ou ajuste da fatura', fatura_destino: '05/2029', compra: null, candidatas: [] }, ...extra });
    preparar([ajuste(1), ajuste(2, { status: 'duplicado', duplicidade: 'lote', ignorar: true, classificacao_importacao: 'JA_EXISTENTE' })]);
    const repetida = estado.linhasMapeadas[1];
    assert.equal(ctx.linhaMantivel(repetida), true);
    ctx.manterComoCompraDiferente(1);
    assert.deepEqual([repetida.classificacao_importacao, estado.analiseConfronto.creditos.length], ['CREDITO', 2]);
    assert.deepEqual(dados(ctx.montarPayloadImportacao().linhas).map((l) => [l.tipo_movimento, Boolean(l.manter_duplicada)]),
        [['credito', false], ['credito', true]]);
});
