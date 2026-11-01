// FIN-CARTAO-AGRUPAMENTO-CATEGORIAS-01 — blocos do detalhe da fatura em Despesas (organizarLancamentosEmBlocos e
// calcularTotaisFatura do js/original/despesas.js do Flask, carregado sem alteracao) com as respostas no formato do
// adaptador (despesas-adaptador.js: compras_da_fatura e fatura_por_categoria). Dados FICTICIOS.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const ORIGINAL = new URL('../../../frontend/static/js/despesas.js', import.meta.url);

function carregarOriginal() {
    const nada = () => {};
    const contexto = {
        console, setTimeout, clearTimeout, URLSearchParams,
        document: { addEventListener: nada, getElementById: () => null, querySelector: () => null, querySelectorAll: () => [] },
        location: { search: '', pathname: '/contas.html' }, localStorage: { getItem: () => null, setItem: nada },
    };
    contexto.window = contexto;
    vm.createContext(contexto);
    vm.runInContext(readFileSync(ORIGINAL, 'utf8'), contexto);
    return contexto;
}

const original = carregarOriginal();
const { calcularTotaisFatura, renderizarFaturaCompleta } = original;
// Objetos criados no contexto do vm tem outro Object.prototype: comparados como dados.
const organizarLancamentosEmBlocos = (...args) => JSON.parse(JSON.stringify(original.organizarLancamentosEmBlocos(...args)));

// Resumo como fatura_por_categoria: limites ativos, categoria sem limite (limite 0) e o grupo sem Categoria do Cartao.
const RESUMO = { categorias: [
    { categoria_cartao_id: 1, categoria_cartao_nome: 'Mercado', limite_mensal: 300, gasto_atual: 150 },
    { categoria_cartao_id: 2, categoria_cartao_nome: 'Farmacia', limite_mensal: 100, gasto_atual: 0 },
    { categoria_cartao_id: 3, categoria_cartao_nome: 'Viagem', limite_mensal: 0, gasto_atual: 10 },
    { categoria_cartao_id: null, categoria_cartao_nome: 'Sem Categoria do Cartao', limite_mensal: null, gasto_atual: 45 },
] };
const compra = (descricao, valor, extra = {}) => ({
    id: descricao, descricao, valor, data_compra: '2029-05-10', numero_parcela: 1, total_parcelas: 1,
    categoria_cartao_id: null, is_recorrente: false, ...extra,
});
const COMPRAS = [
    compra('Compra A', 100, { categoria_cartao_id: 1 }),                                  // vinculada
    compra('Compra B', 50, { categoria_cartao_id: 1 }),                                   // mesma Categoria do Cartao
    compra('Sem vinculo', 40),                                                            // categoria sem vinculo
    compra('Sem limite', 10, { categoria_cartao_id: 3 }),                                 // vinculo sem limite no cartao
    compra('Parcelada', 33.34, { categoria_cartao_id: 2, numero_parcela: 1, total_parcelas: 3 }),
    compra('Fixa', 29.9, { categoria_cartao_id: 1, is_recorrente: true }),
    compra('Sem classificacao', 5),
];
const descricoes = (lista) => lista.map((l) => l.descricao);
const soma = (lista) => Math.round(lista.reduce((s, l) => s + l.valor, 0) * 100) / 100;

test('categoria vinculada: as compras agrupam na Categoria do Cartao, com o subtotal executado', () => {
    const blocos = organizarLancamentosEmBlocos(COMPRAS, RESUMO);
    assert.deepEqual(descricoes(blocos.porCategoria[1].lancamentos), ['Compra A', 'Compra B']);
    assert.equal(soma(blocos.porCategoria[1].lancamentos), 150);
    assert.equal(blocos.porCategoria[1].previsto, 300);
});

test('sem vinculo, sem limite e sem classificacao: Outros Lancamentos', () => {
    const blocos = organizarLancamentosEmBlocos(COMPRAS, RESUMO);
    assert.deepEqual(descricoes(blocos.outros), ['Sem vinculo', 'Sem limite', 'Sem classificacao']);
    assert.equal(blocos.porCategoria[3], undefined);    // categoria sem limite nao vira bloco de categoria
    assert.equal(blocos.porCategoria.null, undefined);  // nem o grupo "Sem Categoria do Cartao"
});

test('parcelada, mesmo classificada, aparece so em Compras Parceladas', () => {
    const blocos = organizarLancamentosEmBlocos(COMPRAS, RESUMO);
    assert.deepEqual(blocos.parceladas.map((p) => [p.descricao, p.numero_parcela, p.total_parcelas]), [['Parcelada', 1, 3]]);
    assert.deepEqual(blocos.porCategoria[2].lancamentos, []);  // Farmacia: so o previsto, sem a parcela
});

test('fixa (recorrencia no cartao), mesmo classificada, aparece so em Despesas Fixas', () => {
    const blocos = organizarLancamentosEmBlocos(COMPRAS, RESUMO);
    assert.deepEqual(descricoes(blocos.fixas), ['Fixa']);
    assert.ok(!descricoes(blocos.porCategoria[1].lancamentos).includes('Fixa'));
});

test('somatorio: cada compra em um bloco so; executado = soma das compras; previsto usa os limites', () => {
    const blocos = organizarLancamentosEmBlocos(COMPRAS, RESUMO);
    const nosBlocos = [...blocos.parceladas, ...blocos.fixas, ...Object.values(blocos.porCategoria).flatMap((c) => c.lancamentos),
        ...blocos.outros];
    assert.deepEqual(descricoes(nosBlocos).sort(), descricoes(COMPRAS).sort());
    assert.equal(soma(nosBlocos), soma(COMPRAS));
    const totais = calcularTotaisFatura(blocos, COMPRAS);
    assert.equal(Math.round(totais.totalExecutado * 100) / 100, 268.24);
    // Regra do Flask (fora deste pacote): parceladas 33,34 + fixas 29,90 + limites 300 e 100 + outros 55.
    assert.equal(Math.round(totais.totalFatura * 100) / 100, 518.24);
});

test('tela: subtotais dos blocos e o nome de cada Categoria do Cartao', () => {
    const blocos = organizarLancamentosEmBlocos(COMPRAS, RESUMO);
    const html = renderizarFaturaCompleta(blocos, calcularTotaisFatura(blocos, COMPRAS), '2029-05').replace(/\s+/g, ' ');
    assert.match(html, /Compras Parceladas<\/span> <span class="bloco-subtotal">R\$ 33,34/);
    assert.match(html, /Despesas Fixas<\/span> <span class="bloco-subtotal">R\$ 29,90/);
    assert.match(html, /Outros Lançamentos<\/span> <span class="bloco-subtotal">R\$ 55,00/);
    assert.match(html, /categoria-nome">Mercado</);
});

// FIN-CARTAO-DESPESAS-FIXAS-01: previsto x executado da fixa, quando o adaptador informa (compras_da_fatura).
test('fixa: previsto, executado e diferenca; prevista sem cobranca; sem os campos, como antes (Flask)', () => {
    const fixas = [
        compra('Netflix', 44.9, { is_recorrente: true, valor_previsto: 59.9, situacao_ocorrencia: 'CONFIRMADA' }),
        compra('ChatGPT', 99.9, { is_recorrente: true, valor_previsto: 99.9, situacao_ocorrencia: 'PREVISTA' }),
        compra('Claude', 109.9, { is_recorrente: true, valor_previsto: 109.9, situacao_ocorrencia: 'CONFIRMADA' }),
        compra('Antiga', 10, { is_recorrente: true }),
    ];
    const blocos = organizarLancamentosEmBlocos(fixas, RESUMO);
    assert.deepEqual(blocos.fixas.map((f) => [f.descricao, f.valor, f.valor_previsto]),
        [['Netflix', 44.9, 59.9], ['ChatGPT', 99.9, 99.9], ['Claude', 109.9, 109.9], ['Antiga', 10, null]]);
    const html = renderizarFaturaCompleta(blocos, calcularTotaisFatura(blocos, fixas), '2029-05').replace(/\s+/g, ' ');
    assert.match(html, /Netflix<\/div> <div class="linha-legenda">Previsto R\$ 59,90 · diferença −R\$ 15,00<\/div> <\/div> <div class="linha-valor">R\$ 44,90/);
    assert.match(html, /ChatGPT<\/div> <div class="linha-legenda">Previsto R\$ 99,90 · cobrança ainda não importada/);
    assert.match(html, /Claude<\/div> <div class="linha-legenda">Previsto R\$ 109,90 · confirmado/);
    assert.match(html, /<div class="linha-simples"> <div class="linha-titulo">Antiga<\/div> <div class="linha-valor">R\$ 10,00/);
    assert.match(html, /Despesas Fixas<\/span> <span class="bloco-subtotal">R\$ 264,70/);  // executado
});

test('defeito anterior: Categoria do Cartao nula e resumo vazio levavam tudo a Outros', () => {
    const semCategoria = COMPRAS.filter((c) => c.total_parcelas <= 1 && !c.is_recorrente)
        .map((c) => ({ ...c, categoria_cartao_id: null }));
    const blocos = organizarLancamentosEmBlocos(semCategoria, { categorias: [] });
    assert.deepEqual(blocos.porCategoria, {});
    assert.equal(blocos.outros.length, semCategoria.length);
});
