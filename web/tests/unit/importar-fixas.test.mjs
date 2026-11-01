// FIN-CARTAO-IMPORTACAO-FIXAS-01 — previa da importacao na tela original (js/original/importar_cartao.js do Flask,
// carregado sem alteracao): classificacao proposta pelo banco (despesa fixa, compra ja lancada a conciliar), correcao do
// usuario e o que vai na confirmacao. Sem os campos novos (Flask), como antes. Dados FICTICIOS.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const ORIGINAL = new URL('../../../frontend/static/js/importar_cartao.js', import.meta.url);

function carregar() {
    const nada = () => {};
    const campos = { cartaoSelect: { value: '910' }, competenciaInput: { value: '05/2029' } };
    const contexto = {
        console, setTimeout, clearTimeout, URLSearchParams, Intl, alert: nada, confirm: () => true,
        document: { addEventListener: nada, getElementById: (id) => campos[id] || null, querySelector: () => null, querySelectorAll: () => [] },
        location: { search: '', pathname: '/importar_cartao.html' }, localStorage: { getItem: () => null, setItem: nada },
    };
    contexto.window = contexto;
    vm.createContext(contexto);
    vm.runInContext(readFileSync(ORIGINAL, 'utf8'), contexto);
    // a tela (DOM) fica fora do teste; o confronto e refeito como na tela
    contexto.recalcularConfrontoAtual = () => { contexto.estadoTeste.analiseConfronto = contexto.montarAnaliseConfronto(); };
    return contexto;
}

const ctx = carregar();
const estado = vm.runInContext('estado', ctx);
ctx.estadoTeste = estado;
const dados = (v) => JSON.parse(JSON.stringify(v));  // objetos do contexto do vm, comparados como dados

const analise = (extra) => ({
    linha_id: 'csv-1', linha_origem: 1, status: 'valido', data_compra: '2029-05-12', descricao_original: 'NETFLIX.COM',
    descricao_normalizada: 'NETFLIX.COM', descricao_exibida: 'NETFLIX.COM', valor: 44.9, categoria_id: 952,
    parcela_atual: 1, total_parcelas: 1, tipo_movimento: 'debito', ...extra,
});
const FIXA = analise({
    classificacao_importacao: 'DESPESA_FIXA', recorrencia_id: 456, realiza_lancamento_id: 580,
    despesa_fixa: { recorrencia_id: 456, nome: 'Netflix', valor_previsto: 59.9, valor_cobrado: 44.9, diferenca: -15,
        competencia: '05/2029', fatura_destino: '05/2029', realiza_lancamento_id: 580, escolhida: false },
});
const COMUM = analise({ linha_id: 'csv-2', linha_origem: 2, descricao_original: 'PADARIA', descricao_normalizada: 'PADARIA',
    descricao_exibida: 'PADARIA', valor: 12, classificacao_importacao: 'COMPRA' });
const JA_LANCADA = analise({ linha_id: 'csv-3', linha_origem: 3, status: 'duplicado', descricao_original: 'NETFLIX ENTRETENIMENTO',
    descricao_normalizada: 'NETFLIX ENTRETENIMENTO', classificacao_importacao: 'JA_EXISTENTE',
    conciliacao_sugerida: { previsto_id: 580, cobranca_id: 606, recorrencia_nome: 'Netflix', valor_previsto: 59.9, valor_cobrado: 44.9 } });
const AMBIGUA = analise({ linha_id: 'csv-4', linha_origem: 4, status: 'revisar', descricao_original: 'SPOTIFY DUO SP',
    descricao_normalizada: 'SPOTIFY DUO SP', valor: 31, classificacao_importacao: 'REVISAR',
    recorrencias_candidatas: [{ id: 501, nome: 'Spotify Duo' }, { id: 502, nome: 'Spotify' }] });

function preparar(linhas) {
    estado.linhasMapeadas = linhas.map((l) => ctx.converterLinhaIntermediaria(l));
    estado.recorrenciasCartao = [{ id: 456, nome: 'Netflix', valor: 59.9 }, { id: 459, nome: 'Apple One', valor: 59.9 },
        { id: 501, nome: 'Spotify Duo', valor: 34.9 }];
    estado.analiseConfronto = ctx.montarAnaliseConfronto();
    return estado.linhasMapeadas;
}

test('conversao: campos da previa do novo aplicativo; linha do Flask sem eles fica como antes', () => {
    const [fixa, flask] = preparar([FIXA, analise({ linha_id: 'csv-9', recorrencia_id: 999 })]);
    assert.equal(fixa.classificacao_importacao, 'DESPESA_FIXA');
    assert.equal(fixa.recorrencia_id, 456);
    assert.equal(fixa.despesa_fixa.nome, 'Netflix');
    assert.equal(flask.classificacao_importacao, null);
    assert.equal(flask.recorrencia_id, undefined);  // o Flask nao recebe recorrencia_id por aqui
    assert.equal(ctx.linhaPossivelRecorrencia(flask), false);
    assert.equal(ctx.linhaPossivelRecorrencia(fixa), true);
});

test('linha da despesa fixa: status, natureza e previsto, cobrado, diferenca e fatura na propria linha', () => {
    const [fixa, comum, , ambigua] = preparar([FIXA, COMUM, JA_LANCADA, AMBIGUA]);
    const info = dados(ctx.obterInfoOperacional(fixa, 0));
    assert.deepEqual([info.status, info.tipo, info.filtro, info.fixaNova], ['Despesa fixa', 'Despesa fixa', 'recorrencias', true]);
    assert.match(info.sugestao, /^Netflix · previsto R\$\s59,90 · cobrado R\$\s44,90 · diferença −R\$\s15,00 · fatura 05\/2029$/);
    assert.equal(dados(ctx.obterInfoOperacional(comum, 1)).status, 'Novo');
    assert.equal(dados(ctx.obterInfoOperacional(ambigua, 3)).status, 'Revisar');
    const html = ctx.seletorRecorrenciaLinha(fixa, 0);
    assert.match(html, /Automática: Netflix/);
    assert.match(html, /Compra comum \(sem recorrência\)/);
    assert.match(ctx.observacaoRetiradaLinha(estado.linhasMapeadas[2]), /corresponde à previsão Netflix .*será conciliada na confirmação/);
});

test('confirmacao: fixa, compra comum e a conciliacao da compra ja lancada vao no envio; a ambigua so depois da escolha', () => {
    preparar([FIXA, COMUM, JA_LANCADA, AMBIGUA]);
    let envio = dados(ctx.montarPayloadImportacao());
    assert.deepEqual([envio.cartao_id, envio.competencia], [910, '2029-05-01']);
    assert.deepEqual(envio.linhas.map((l) => [l.descricao_original, l.recorrencia_escolhida_id ?? null, l.conciliar_previsao ?? false]),
        [['PADARIA', null, false], ['NETFLIX.COM', null, false], ['SPOTIFY DUO SP', null, false], ['NETFLIX ENTRETENIMENTO', null, true]]);
    // a ambigua sem escolha nao some do envio (o banco a recusaria); a tela pede a revisao antes de confirmar
    assert.equal(ctx.validarNovosClassificados(), false);
    // a ambigua: escolhe a recorrencia e lembra o apelido
    ctx.escolherRecorrenciaLinha(3, '501');
    ctx.alternarApelidoLinha(3, true);
    // a fixa: tratada como compra comum; a ja lancada: o usuario desmarca a conciliacao
    ctx.tratarReconhecimentoComoNovo(0);
    ctx.alternarConciliacaoLinha(2, false);
    envio = dados(ctx.montarPayloadImportacao());
    const por = Object.fromEntries(envio.linhas.map((l) => [l.descricao_original, l]));
    assert.equal(por['NETFLIX.COM'].recorrencia_escolhida_id, 0);
    assert.deepEqual([por['SPOTIFY DUO SP'].recorrencia_escolhida_id, por['SPOTIFY DUO SP'].salvar_apelido], [501, true]);
    assert.equal(por['NETFLIX ENTRETENIMENTO'], undefined);
    assert.equal(estado.linhasMapeadas[3].despesa_fixa.nome, 'Spotify Duo');
    assert.equal(ctx.validarNovosClassificados(), true);
});

test('compra retirada pela regra herdada (mesmo valor e parcela ate 5 dias, ou repetida no arquivo): o usuario a mantem', () => {
    const pelo_valor = analise({ linha_id: 'csv-5', linha_origem: 5, status: 'conciliado', ignorar: true, descricao_original: 'MERCADO BAIRRO',
        descricao_normalizada: 'MERCADO BAIRRO', valor: 50, classificacao_importacao: 'JA_EXISTENTE',
        reconhecimento_match: { tipo: 'duplicado_atual', score: 90, descricao_sugerida: 'Mercado do bairro' } });
    const repetida = analise({ linha_id: 'csv-6', linha_origem: 6, status: 'duplicado', duplicidade: 'lote', descricao_original: 'CAFE',
        descricao_normalizada: 'CAFE', valor: 5, classificacao_importacao: 'JA_EXISTENTE' });
    const reimportada = analise({ linha_id: 'csv-7', linha_origem: 7, status: 'duplicado', duplicidade: 'banco', descricao_original: 'PADARIA',
        descricao_normalizada: 'PADARIA', valor: 12, classificacao_importacao: 'JA_EXISTENTE' });
    const linhas = preparar([pelo_valor, repetida, reimportada]);
    assert.deepEqual(linhas.map((l) => ctx.linhaMantivel(l)), [true, true, false]);  // a reimportada (mesma compra) nao
    assert.match(ctx.renderizarLinhaRetirada(linhas[0], 0), /manterComoCompraDiferente\(0\)/);
    assert.equal(dados(ctx.montarPayloadImportacao()).linhas.length, 0);
    ctx.manterComoCompraDiferente(0);
    ctx.manterComoCompraDiferente(1);
    const envio = dados(ctx.montarPayloadImportacao()).linhas;
    assert.deepEqual(envio.map((l) => [l.descricao_original, l.manter_conciliada ?? false, l.manter_duplicada ?? false]),
        [['MERCADO BAIRRO', true, false], ['CAFE', false, true]]);
});

test('linha do Flask (sem classificacao do novo aplicativo) nao ganha a acao de manter', () => {
    const [flask] = preparar([analise({ status: 'conciliado', ignorar: true,
        reconhecimento_match: { tipo: 'duplicado_atual', score: 90 } })]);
    assert.equal(ctx.linhaMantivel(flask), false);
});
