// FIN-CARTOES-MULTIPLOS-01 — previa da importacao na tela original (js/original/importar_cartao.js do Flask, carregado
// sem alteracao): o cartao vinculado de origem vem do arquivo (final do PDF) ou e escolhido na linha ou nas selecionadas;
// sem final, a linha fica sem cartao identificado (nunca presumido). Contrato sem cartoes cadastrados (ou Flask): como
// antes. Dados FICTICIOS.
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

const FISICO = { id: 41, nome: 'Fisico', final: '1111', tipo: 'FISICO', situacao: 'CANCELADO' };
const VIRTUAL = { id: 42, nome: 'Virtual', final: '2222', tipo: 'VIRTUAL', situacao: 'ATIVO' };
const analise = (n, extra) => ({
    linha_id: `pdf-${n}`, linha_origem: n, status: 'valido', data_compra: '2029-05-12', descricao_original: `LOJA ${n}`,
    descricao_normalizada: `LOJA ${n}`, descricao_exibida: `LOJA ${n}`, valor: 10 + n, categoria_id: 952, parcela_atual: 1,
    total_parcelas: 1, tipo_movimento: 'debito', classificacao_importacao: 'COMPRA', ...extra,
});
const DO_ARQUIVO = analise(1, { cartao_final: '2222', cartao_vinculado: VIRTUAL, cartao_vinculado_id: 42, cartao_origem: 'ARQUIVO' });
const NAO_CADASTRADO = analise(2, { cartao_final: '9999' });
const SEM_FINAL = analise(3);

function preparar(linhas, cartoes = [VIRTUAL, FISICO]) {
    estado.linhasMapeadas = linhas.map((l) => ctx.converterLinhaIntermediaria(l));
    estado.cartoesContrato = cartoes;
    estado.analiseConfronto = ctx.montarAnaliseConfronto();
    estado.linhasSelecionadas = new Set();
    ctx.alertas.length = 0;
    return estado.linhasMapeadas;
}

const enviadas = () => dados(ctx.montarPayloadImportacao().linhas).map((l) => [l.descricao_original, l.cartao_final ?? null,
    l.cartao_vinculado_escolhido_id ?? null]);

test('cartao do arquivo, final nao cadastrado e linha sem final (nunca presumido)', () => {
    const [arquivo, naoCadastrado, semFinal] = preparar([DO_ARQUIVO, NAO_CADASTRADO, SEM_FINAL]);
    assert.match(ctx.seletorCartaoLinha(arquivo, 0), /<option value="" selected>•••• 2222 · virtual \(arquivo\)<\/option>/);
    assert.match(ctx.seletorCartaoLinha(naoCadastrado, 1), /Final 9999 não cadastrado/);
    assert.match(ctx.seletorCartaoLinha(semFinal, 2), /Cartão não identificado.*•••• 1111 · físico \(cancelado\).*Sem cartão identificado/s);
    assert.deepEqual(enviadas(), [['LOJA 1', '2222', null], ['LOJA 2', '9999', null], ['LOJA 3', null, null]]);
});

test('escolha na linha e nas selecionadas vai na confirmacao (0 = sem cartao)', () => {
    preparar([DO_ARQUIVO, NAO_CADASTRADO, SEM_FINAL]);
    ctx.escolherCartaoLinha(0, '0');
    ctx.aplicarCartaoSelecionadas('41');
    assert.match(ctx.alertas[0], /Selecione as linhas/);
    estado.linhasSelecionadas = new Set([1, 2]);
    ctx.aplicarCartaoSelecionadas('41');
    assert.deepEqual(enviadas(), [['LOJA 1', '2222', 0], ['LOJA 2', '9999', 41], ['LOJA 3', null, 41]]);
    assert.equal(estado.linhasMapeadas[2].cartao_vinculado.final, '1111');
    ctx.escolherCartaoLinha(0, '');  // de volta ao do arquivo
    assert.deepEqual([estado.linhasMapeadas[0].cartao_vinculado.final, enviadas()[0][2]], ['2222', null]);
});

test('contrato sem cartoes cadastrados (ou Flask): sem seletor, como antes', () => {
    const [arquivo, , semFinal] = preparar([DO_ARQUIVO, NAO_CADASTRADO, SEM_FINAL], []);
    assert.equal(ctx.seletorCartaoLinha(semFinal, 2), '');
    assert.match(ctx.seletorCartaoLinha(arquivo, 0), /Cartão 2222/);
    assert.equal(ctx.renderizarCartaoLote(), '');
});
