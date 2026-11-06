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
const { calcularTotaisFatura, renderizarAgrupadorSemanal, renderizarFaturaCompleta } = original;
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

// FIN-CARTAO-DESPESAS-FIXAS-01 / FIN-CARTAO-PREVISTO-EXECUTADO-01: previsto x executado da fixa, quando o adaptador
// informa (compras_da_fatura): a prevista (ou nao cobrada) nao e executada.
test('fixa: previsto, executado, diferenca e situacao; sem os campos, como antes (Flask)', () => {
    const fixa = (descricao, valor, executado, previsto, situacao) => compra(descricao, valor, {
        is_recorrente: true, valor_previsto: previsto, valor_executado: executado, situacao_ocorrencia: situacao });
    const fixas = [
        fixa('Netflix', 44.9, 44.9, 59.9, 'CONFIRMADA'),
        fixa('ChatGPT', 99.9, 0, 99.9, 'PREVISTA'),
        fixa('Claude', 109.9, 109.9, 109.9, 'CONFIRMADA'),
        fixa('Apple One', 59.9, 0, 59.9, 'NAO_COBRADA'),
        fixa('X Premium', 119, 119, 119, 'PAGA'),
        compra('Antiga', 10, { is_recorrente: true }),
    ];
    const blocos = organizarLancamentosEmBlocos(fixas, RESUMO);
    assert.deepEqual(blocos.fixas.map((f) => [f.descricao, f.valor, f.valor_executado, f.valor_previsto]),
        [['Netflix', 44.9, 44.9, 59.9], ['ChatGPT', 99.9, 0, 99.9], ['Claude', 109.9, 109.9, 109.9],
            ['Apple One', 59.9, 0, 59.9], ['X Premium', 119, 119, 119], ['Antiga', 10, null, null]]);
    const totais = calcularTotaisFatura(blocos, fixas);
    // executado: so o cobrado (44,90 + 109,90 + 119 + 10); previsto: a prevista pelo previsto, as demais pelo executado,
    // mais os limites do resumo (300 + 100)
    assert.equal(Math.round(totais.totalExecutado * 100) / 100, 283.8);
    assert.equal(Math.round(totais.totalFatura * 100) / 100, 783.7);
    const html = renderizarFaturaCompleta(blocos, totais, '2029-05').replace(/\s+/g, ' ');
    assert.match(html, /Netflix<\/span> <span class="linha-valor">R\$ 44,90/);
    // MVP-FIN-AJUSTES-01 (P01): antes da cobranca a linha mostra o valor definido na recorrencia, marcado como previsto
    assert.match(html, /linha-simples linha-prevista"[^>]*> <span class="linha-data">10\/05<\/span> <span class="linha-titulo">ChatGPT<\/span> <span class="linha-valor">R\$ 99,90/);
    assert.match(html, /Claude<\/span> <span class="linha-valor">R\$ 109,90/);
    assert.match(html, /Apple One<\/span> <span class="linha-valor">R\$ 0,00/);
    assert.match(html, /X Premium<\/span> <span class="linha-valor">R\$ 119,00/);
    assert.match(html, /<span class="linha-titulo">Antiga<\/span> <span class="linha-valor">R\$ 10,00/);
    // FIN-FATURA-AJUSTES-02 (P17): cabecalho = soma das linhas exibidas, igual ao rodape; so Data, Descricao e Valor
    assert.match(html, /Despesas Fixas<\/span> <span class="bloco-subtotal">R\$ 383,70<\/span>/);
    assert.match(html, /rodape-valor">R\$ 383,70<\/span> <span class="rodape-label">Despesas Fixas/);
    const bloco = html.match(/Despesas Fixas<\/span>.*?Despesas por Categoria/)[0];
    assert.doesNotMatch(bloco, /linha-legenda|Previsto|aguardando|confirmado|cobrada|paga com|diferença/i);
});

// FIN-FATURA-AJUSTES-02 (P17): o exemplo do contrato; a compra real absorve a previsao sem contar duas vezes
test('despesas fixas: recorrencias ainda sem cobranca somam no cabecalho; total executado continua sem elas', () => {
    const fixa = (descricao, valor) => compra(descricao, valor, { data_compra: '2029-11-01', is_recorrente: true, valor_previsto: valor,
        valor_executado: 0, situacao_ocorrencia: 'PREVISTA' });
    const lancamentos = [fixa('Plano Celular', 70), fixa('Servidor', 225)];
    const blocos = organizarLancamentosEmBlocos(lancamentos, { categorias: [] });
    const totais = calcularTotaisFatura(blocos, lancamentos);
    assert.equal(totais.totalFatura, 295);
    assert.equal(totais.totalExecutado, 0);
    const html = renderizarFaturaCompleta(blocos, totais, '2029-11').replace(/\s+/g, ' ');
    assert.match(html, /Despesas Fixas<\/span> <span class="bloco-subtotal">R\$ 295,00<\/span>/);
    assert.match(html, /<span class="linha-data">01\/11<\/span> <span class="linha-titulo">Plano Celular<\/span> <span class="linha-valor">R\$ 70,00/);
    assert.match(html, /<span class="linha-data">01\/11<\/span> <span class="linha-titulo">Servidor<\/span> <span class="linha-valor">R\$ 225,00/);
    assert.match(html, /title="Servidor"/);  // o texto da situacao tambem saiu do titulo da linha
});

// MVP-FIN-AJUSTES-01 (P03): a fatura Black 11/2026 da producao mostrava R$ 7.827,55 com R$ 9.114,84 no banco (contas_do_mes)
test('categoria acima do limite: o previsto usa o gasto, como o banco e o rodape', () => {
    const lancamentos = [compra('Acima', 350, { categoria_cartao_id: 1 }), compra('Abaixo', 40, { categoria_cartao_id: 2 })];
    const blocos = organizarLancamentosEmBlocos(lancamentos, RESUMO);
    const totais = calcularTotaisFatura(blocos, lancamentos);
    // Mercado: limite 300, gasto 350 (entra 350); Farmacia: limite 100, gasto 40 (entra 100)
    assert.equal(totais.totalFatura, 450);
    assert.equal(totais.totalExecutado, 390);
    const html = renderizarFaturaCompleta(blocos, totais, '2029-05').replace(/\s+/g, ' ');
    assert.match(html, /rodape-valor">R\$ 350,00<\/span> <span class="rodape-label">Mercado/);
    assert.match(html, /rodape-valor">R\$ 100,00<\/span> <span class="rodape-label">Farmacia/);
});

// FIN-FATURA-AJUSTES-02 (P16)
test('categorias: quatro colunas na ordem do cabecalho, saldo com sinal, sem os textos repetitivos', () => {
    const lancamentos = [compra('Acima', 350, { categoria_cartao_id: 1 }), compra('Exata', 100, { categoria_cartao_id: 2 })];
    const blocos = organizarLancamentosEmBlocos(lancamentos, RESUMO);
    const html = renderizarFaturaCompleta(blocos, calcularTotaisFatura(blocos, lancamentos), '2029-05').replace(/\s+/g, ' ');
    assert.match(html, /categoria-colunas"> <span>Categoria<\/span> <span>Previsto<\/span> <span>Saldo<\/span> <span>Executado<\/span> <\/div>/);
    assert.doesNotMatch(html, /[↑↓]/);
    const linha = (nome, classe, saldo, executado) => new RegExp(`categoria-nome">${nome}</span> <span class="categoria-valor"[^>]*>R\\$ ${classe}</span> `
        + `<span class="categoria-saldo${saldo.startsWith('-') ? ' negativo' : ''}"[^>]*>${saldo.replace('$', '\\$')}</span> <span class="categoria-indicador"[^>]*>R\\$ ${executado}</span>`);
    assert.match(html, linha('Mercado', '300,00', '-R$ 50,00', '350,00'));
    assert.match(html, linha('Farmacia', '100,00', 'R$ 0,00', '100,00'));
    const saldo = organizarLancamentosEmBlocos(COMPRAS, RESUMO);
    const positivo = renderizarFaturaCompleta(saldo, calcularTotaisFatura(saldo, COMPRAS), '2029-05').replace(/\s+/g, ' ');
    assert.match(positivo, linha('Mercado', '300,00', 'R$ 150,00', '150,00'));
    assert.doesNotMatch(html + positivo, /Excedente|No limite|categoria-situacao/);
    assert.doesNotMatch((html + positivo).replace(/<span>Saldo<\/span>/g, ''), />\s*Saldo\b/);
    // Sem categoria com previsao, sem o cabecalho das colunas
    const vazio = organizarLancamentosEmBlocos([], { categorias: [] });
    assert.doesNotMatch(renderizarFaturaCompleta(vazio, calcularTotaisFatura(vazio, []), '2029-05'), /categoria-colunas/);
});

// MVP-FIN-AJUSTES-01 (P04)
test('linha da fatura: DATA, DESCRICAO e VALOR nessa ordem, em todos os blocos, com a descricao escapada', () => {
    const lancamentos = [compra('<b>Loja</b>', 10), compra('Parcela', 5, { numero_parcela: 2, total_parcelas: 3 }),
        compra('Fixa', 7, { is_recorrente: true }), compra('Mercado', 3, { categoria_cartao_id: 1 })];
    const blocos = organizarLancamentosEmBlocos(lancamentos, RESUMO);
    const html = renderizarFaturaCompleta(blocos, calcularTotaisFatura(blocos, lancamentos), '2029-05').replace(/\s+/g, ' ');
    assert.equal(html.match(/class="linha-simples/g).length, 4);
    assert.equal(html.match(/class="linha-simples[^>]*> <span class="linha-data">10\/05<\/span> <span class="linha-titulo">/g).length, 4);
    assert.match(html, /&lt;b&gt;Loja&lt;\/b&gt;<\/span> <span class="linha-valor">R\$ 10,00/);
    assert.match(html, /Parcela<\/span> <span class="linha-legenda">02\/03<\/span> <span class="linha-valor">R\$ 5,00/);
});

// MVP-FIN-AJUSTES-01 (P01): a cobranca conciliada absorve a previsao (uma linha CONFIRMADA): o valor nao conta duas vezes
test('fixa conciliada: uma linha so, no previsto e no executado', () => {
    const lancamentos = [compra('Netflix', 44.9, { is_recorrente: true, valor_previsto: 59.9, valor_executado: 44.9, situacao_ocorrencia: 'CONFIRMADA' })];
    const blocos = organizarLancamentosEmBlocos(lancamentos, { categorias: [] });
    const totais = calcularTotaisFatura(blocos, lancamentos);
    assert.equal(totais.totalFatura, 44.9);
    assert.equal(totais.totalExecutado, 44.9);
    assert.equal(blocos.fixas.length, 1);
});

// MVP-FIN-AJUSTES-01 (P09)
test('agrupador semanal e ocorrencias: tres acoes; estornar so a ocorrencia paga', () => {
    const ocorrencia = (id, status) => ({ id, nome: 'Diarista', valor: 50, status, pago: status === 'Pago', data_vencimento: '2029-05-07' });
    const html = renderizarAgrupadorSemanal({ nome: 'Diarista', mes_competencia: '2029-05-01',
        ocorrencias: [ocorrencia(1, 'Pago'), ocorrencia(2, 'Pendente')] }, 0);
    const linhas = html.split('despesa-cell-acoes').slice(1, 4).map((trecho) => trecho.split('</div>')[0]);
    assert.deepEqual(linhas.map((l) => l.match(/<button/g).length), [3, 3, 3]);
    const estorno = (l) => l.match(/<button[^>]*abrirModalEstorno[^>]*>/)[0];
    assert.match(estorno(linhas[0]), /disabled/);
    assert.doesNotMatch(estorno(linhas[1]), /disabled/);
    assert.match(estorno(linhas[2]), /disabled/);
});

test('defeito anterior: Categoria do Cartao nula e resumo vazio levavam tudo a Outros', () => {
    const semCategoria = COMPRAS.filter((c) => c.total_parcelas <= 1 && !c.is_recorrente)
        .map((c) => ({ ...c, categoria_cartao_id: null }));
    const blocos = organizarLancamentosEmBlocos(semCategoria, { categorias: [] });
    assert.deepEqual(blocos.porCategoria, {});
    assert.equal(blocos.outros.length, semCategoria.length);
});
