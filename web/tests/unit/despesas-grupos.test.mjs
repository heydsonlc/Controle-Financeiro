// FIN-MVP-MOB-01 — a lista mobile reproduz a lista de Despesas do desktop. O arquivo original da tela do desktop
// (frontend/static/js/despesas.js, o mesmo que vai para js/original/despesas.js) roda numa VM com os mesmos dados; grupos,
// ordem, valores, filtros, totais e textos de js/despesas-grupos.js tem de sair iguais.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

import {
    FORMAS_FILTRO, filtrarDespesas, formatarCompetencia, formatarTipoRecorrencia, montarGrupos, obterFormaPagamentoDespesa,
    totaisDaLista,
} from '../../src/js/despesas-grupos.js';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const ORIGINAL = path.join(RAIZ, 'frontend', 'static', 'js');

// A tela do desktop numa VM: document minimo (os elementos sao objetos com value/innerHTML/textContent).
function desktop() {
    const elementos = {};
    const elemento = (id) => {
        if (!elementos[id]) elementos[id] = { id, value: '', innerHTML: '', textContent: '', style: {}, dataset: {}, addEventListener() {} };
        return elementos[id];
    };
    const contexto = {
        console: { log() {}, error() {}, warn() {} },
        document: { addEventListener() {}, getElementById: elemento, querySelector: () => null, querySelectorAll: () => [] },
        alert() {}, confirm: () => false, fetch: async () => ({ json: async () => ({}) }),
    };
    contexto.window = contexto;
    vm.createContext(contexto);
    vm.runInContext(readFileSync(path.join(ORIGINAL, 'formas_pagamento.js'), 'utf8'), contexto);
    vm.runInContext(readFileSync(path.join(ORIGINAL, 'despesas.js'), 'utf8'), contexto);
    return { contexto, elemento, rodar: (codigo) => vm.runInContext(codigo, contexto) };
}

// Sequencia mostrada pelo desktop: titulos de grupo e, em cada grupo, as linhas (despesa ou agrupador) com o valor.
function sequenciaDoDesktop(html) {
    const padrao = /despesas-grupo-titulo">([^<]+)<|data-despesa-id="(\d+)"[\s\S]*?despesa-valor-principal">\s*R\$ ([^\s<]+)|data-agrupador-index="\d+"[\s\S]*?title="([^"]*)"[\s\S]*?despesa-valor-principal">\s*R\$ ([^\s<]+)/g;
    return [...html.matchAll(padrao)].map((m) => {
        if (m[1]) return `G:${m[1]}`;
        if (m[2]) return `D:${m[2]}=${m[3]}`;
        return `S:${m[4]}=${m[5]}`;
    });
}

const valorBR = (c) => (c / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function sequenciaDoMobile(lista) {
    return montarGrupos(lista).flatMap((g) => [`G:${g.rotulo}`, ...g.itens.map((item) => (item.tipo === 'semanal'
        ? `S:${item.agrupador.nome}=${valorBR(item.valor_centavos)}`
        : `D:${item.despesa.id}=${valorBR(item.valor_centavos)}`))]);
}

// Linhas no formato que js/despesas-servico.js entrega (linhaDoFlask), vencimento mais recente primeiro.
const cat = (id, nome) => ({ id, nome, cor: '#6e6e73' });
const base = { mes_competencia: '2026-11', ativo: true, descricao: '', numero_parcela: null, total_parcelas: null, conta_bancaria_id: null };
const LISTA = [
    { ...base, id: 11, nome: 'Fatura Nubank', tipo: 'cartao', is_fatura_cartao: true, agrupado: true, valor: 1520.4, valor_fatura: 1520.4,
        valor_planejado: 1400, valor_executado: 1520.4, data_vencimento: '2026-12-10', pago: false, meio_pagamento: 'cartao', cartao_id: 3 },
    { ...base, id: 12, nome: 'Aluguel', tipo: 'Simples', recorrente: true, tipo_recorrencia: 'mensal', valor: 2500, data_vencimento: '2026-12-05',
        pago: true, data_pagamento: '2026-11-30', categoria: cat(5, 'Moradia'), categoria_id: 5, meio_pagamento: 'boleto', descricao: 'Apto 12' },
    { ...base, id: 13, nome: 'Financiamento casa', tipo: 'Simples', financiamento_parcela_id: 13, valor: 3010.55, data_vencimento: '2026-12-01',
        pago: false, numero_parcela: 31, total_parcelas: 420, meio_pagamento: 'debito_automatico', debito_automatico: true },
    { ...base, id: 14, nome: 'Diarista - 26/11', tipo: 'Simples', recorrente: true, tipo_recorrencia: 'semanal_1_3', valor: 180, data_vencimento: '2026-11-26',
        pago: false, categoria: cat(7, 'Casa'), categoria_id: 7, meio_pagamento: 'pix', item_despesa_id: 70 },
    { ...base, id: 15, nome: 'Consórcio carro', tipo: 'Consorcio', valor: 870.1, data_vencimento: '2026-11-25', pago: false, meio_pagamento: 'boleto' },
    { ...base, id: 16, nome: 'Psicóloga - 20/11', tipo: 'Simples', recorrente: true, tipo_recorrencia: 'semanal_1_4', valor: 250, data_vencimento: '2026-11-20',
        pago: true, data_pagamento: '2026-11-20', categoria: cat(8, 'Saúde'), categoria_id: 8, meio_pagamento: 'pix', item_despesa_id: 80 },
    { ...base, id: 17, nome: 'Diarista - 19/11', tipo: 'Simples', recorrente: true, tipo_recorrencia: 'semanal_1_3', valor: 180, data_vencimento: '2026-11-19',
        pago: true, data_pagamento: '2026-11-19', categoria: cat(7, 'Casa'), categoria_id: 7, meio_pagamento: 'pix', item_despesa_id: 70 },
    { ...base, id: 18, nome: 'Conserto geladeira', tipo: 'Simples', valor: 420.33, data_vencimento: '2026-11-15', pago: false,
        categoria: cat(7, 'Casa'), categoria_id: 7, meio_pagamento: null, descricao: 'Peça trocada' },
    { ...base, id: 19, nome: 'Internet', tipo: 'Simples', recorrente: true, tipo_recorrencia: 'mensal', valor: 129.9, data_vencimento: '2026-11-12',
        pago: false, categoria: cat(9, 'Telefonia'), categoria_id: 9, meio_pagamento: 'debito_automatico', debito_automatico: true },
    { ...base, id: 20, nome: 'IPVA', tipo: 'Simples', recorrente: true, tipo_recorrencia: 'anual', valor: 1890.01, data_vencimento: '2026-11-10',
        pago: true, data_pagamento: '2026-11-09', categoria: cat(10, 'Veículo'), categoria_id: 10, meio_pagamento: 'transferencia' },
    { ...base, id: 21, nome: 'Presente', tipo: 'Simples', valor: 75.5, data_vencimento: '2026-11-08', pago: true, data_pagamento: '2026-11-08',
        categoria: null, categoria_id: null, meio_pagamento: 'dinheiro' },
    { ...base, id: 22, nome: 'Diarista - 12/11', tipo: 'Simples', recorrente: true, tipo_recorrencia: 'semanal_1_3', valor: 180, data_vencimento: '2026-11-12',
        pago: false, categoria: cat(7, 'Casa'), categoria_id: 7, meio_pagamento: 'pix', item_despesa_id: 70 },
];

test('grupos, ordem e valores iguais aos da lista do desktop (arquivo original na VM)', () => {
    const d = desktop();
    d.contexto.__lista = LISTA;
    d.rodar('renderizarDespesas(__lista)');
    const esperado = sequenciaDoDesktop(d.elemento('despesas-lista').innerHTML);
    assert.ok(esperado.length > 10, 'o desktop desenhou a lista');
    assert.deepEqual(sequenciaDoMobile(LISTA), esperado);
    // Os grupos do desktop, so eles e na ordem dele.
    assert.deepEqual(esperado.filter((s) => s.startsWith('G:')), ['G:FINANCIAMENTOS', 'G:FATURAS DE CARTÃO DE CRÉDITO',
        'G:DESPESAS RECORRENTES', 'G:DESPESAS AVULSAS', 'G:INVESTIMENTOS']);
});

test('total de cada grupo = soma das suas linhas; total geral = cartoes de resumo do desktop', () => {
    const d = desktop();
    d.contexto.__lista = LISTA;
    d.rodar('atualizarResumo(__lista)');
    const t = totaisDaLista(LISTA);
    assert.equal(d.elemento('total-geral').textContent, `R$ ${valorBR(t.total)}`);
    assert.equal(d.elemento('total-pendentes').textContent, `R$ ${valorBR(t.pendentes)}`);
    assert.equal(d.elemento('total-pagas').textContent, `R$ ${valorBR(t.pagas)}`);
    const grupos = montarGrupos(LISTA);
    for (const g of grupos) assert.equal(g.total_centavos, g.itens.reduce((s, i) => s + i.valor_centavos, 0));
    assert.equal(grupos.reduce((s, g) => s + g.total_centavos, 0), t.total);
});

test('filtros (forma de pagamento, status, vencimento ate) iguais aos do desktop', () => {
    const d = desktop();
    d.contexto.__lista = LISTA;
    d.rodar('despesas = __lista');
    const casos = [
        ...FORMAS_FILTRO.map(([forma]) => ({ forma })),
        { situacao: 'pago' }, { situacao: 'pendente' }, { vencimentoAte: '2026-11-20' },
        { forma: 'pix', situacao: 'pendente' }, { forma: 'debito_automatico', vencimentoAte: '2026-11-30' },
    ];
    for (const filtros of casos) {
        d.elemento('filtro-forma-pagamento').value = filtros.forma || '';
        d.elemento('filtro-status').value = filtros.situacao || '';
        d.elemento('filtro-vencimento-ate').value = filtros.vencimentoAte || '';
        d.elemento('filtro-competencia').value = '11/2026';
        d.rodar('aplicarFiltros()');
        const filtradas = filtrarDespesas(LISTA, filtros, d.contexto.FormasPagamentoUI);
        assert.deepEqual(sequenciaDoMobile(filtradas), sequenciaDoDesktop(d.elemento('despesas-lista').innerHTML), JSON.stringify(filtros));
        assert.equal(`R$ ${valorBR(totaisDaLista(filtradas).total)}`, d.elemento('total-geral').textContent, JSON.stringify(filtros));
    }
});

test('busca por nome, observacao ou categoria igual a do desktop', () => {
    const d = desktop();
    d.contexto.__lista = LISTA;
    d.rodar('despesas = __lista');
    for (const busca of ['diarista', 'CASA', 'peça', 'apto', 'nada-encontrado']) {
        d.contexto.__busca = busca;
        d.rodar('filtrarBusca(__busca)');
        const html = d.elemento('despesas-lista').innerHTML;
        const filtradas = filtrarDespesas(LISTA, { busca }, d.contexto.FormasPagamentoUI);
        if (!filtradas.length) assert.match(html, /Nenhuma despesa encontrada/);
        else assert.deepEqual(sequenciaDoMobile(filtradas), sequenciaDoDesktop(html), busca);
    }
});

test('forma de pagamento, competencia e recorrencia com os mesmos textos do desktop', () => {
    const d = desktop();
    const formas = d.contexto.FormasPagamentoUI;
    for (const linha of LISTA) {
        d.contexto.__linha = linha;
        assert.equal(obterFormaPagamentoDespesa(linha, formas), d.rodar('obterFormaPagamentoDespesa(__linha)'), linha.nome);
    }
    for (const tipo of [null, 'mensal', 'anual', 'semanal', 'a_cada_2_semanas', 'semanal_1_1', 'semanal_2_5', 'outro']) {
        d.contexto.__tipo = tipo;
        assert.equal(formatarTipoRecorrencia(tipo), d.rodar('formatarTipoRecorrencia(__tipo)'), String(tipo));
    }
    for (const mes of ['2026-01', '2026-11', '2027-12']) {
        d.contexto.__mes = mes;
        assert.equal(formatarCompetencia(mes), d.rodar('formatarCompetencia(__mes)'));
    }
});
