// FIN-MVP-MOBILE-04 — regras de leitura das Receitas mobile (js/receitas-lista.js): a mesma lista, ordem e totais da tela
// de Receitas do desktop. A equivalencia e conferida rodando o arquivo ORIGINAL (frontend/static/js/receitas.js, o JS do
// Flask que vai para js/original/) com as adaptacoes do novo aplicativo (js/receitas-adaptacoes.js), num contexto sem tela.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

import {
    acoesDaReceita, legendaDaReceita, montarDataPrevista, montarReceitasMes, recebimentosDaLinha, separarReceitas,
    totaisDaLista, valorDaLinha,
} from '../../src/js/receitas-lista.js';

const RAIZ = new URL('../../../', import.meta.url);

// Contexto com o JS original carregado: sem elementos na tela (getElementById -> null), as funcoes de desenho saem cedo.
async function desktop() {
    const contexto = { console, Intl, Date, Math, Number, String, Map, Set, setTimeout,
        document: { addEventListener() {}, getElementById: () => null, querySelectorAll: () => [], querySelector: () => null },
        MutationObserver: class { observe() {} } };
    contexto.window = contexto;
    vm.createContext(contexto);
    for (const arquivo of ['frontend/static/js/receitas.js', 'web/src/js/receitas-adaptacoes.js']) {
        vm.runInContext(await readFile(new URL(arquivo, RAIZ), 'utf8'), contexto, { filename: arquivo });
    }
    return contexto;
}

const json = (v) => JSON.parse(JSON.stringify(v));

// Cenario ficticio com todos os caminhos da montagem (as formas que as rotas do servico devolvem)
const CONTAS = [{ id: 1, nome: 'Conta A', instituicao: 'Banco A' }, { id: 2, nome: 'Conta B', instituicao: 'Banco B' }];
const FONTES = [
    { id: 10, nome: 'Salario', tipo: 'SALARIO_FIXO', descricao: 'Mensal', ativo: true, recorrente: true, valor_base_mensal: 5000,
        dia_previsto_pagamento: 5, conta_bancaria_id: 1, de_outro_modulo: false },
    { id: 11, nome: 'Aluguel sala', tipo: 'ALUGUEL', descricao: '', ativo: true, recorrente: true, valor_base_mensal: 1200,
        dia_previsto_pagamento: 31, conta_bancaria_id: 2, de_outro_modulo: false },
    { id: 12, nome: 'Bonus', tipo: 'GRATIFICACAO', descricao: 'Anual', ativo: true, recorrente: false, valor_base_mensal: null,
        dia_previsto_pagamento: null, conta_bancaria_id: null, de_outro_modulo: false },
    { id: 13, nome: 'Rendimento', tipo: 'RENDIMENTO_FINANCEIRO', descricao: '', ativo: true, recorrente: true, valor_base_mensal: 40,
        dia_previsto_pagamento: 1, conta_bancaria_id: 1, de_outro_modulo: false },
    { id: 14, nome: 'Freela', tipo: 'RENDA_EXTRA', descricao: '', ativo: true, recorrente: false, valor_base_mensal: null,
        dia_previsto_pagamento: null, conta_bancaria_id: null, de_outro_modulo: false },
    { id: 15, nome: 'Sem previsao', tipo: 'OUTROS', descricao: '', ativo: true, recorrente: true, valor_base_mensal: 99,
        dia_previsto_pagamento: 10, conta_bancaria_id: null, de_outro_modulo: false },
    { id: 16, nome: 'Consorcio X', tipo: 'OUTROS', descricao: '', ativo: true, recorrente: false, valor_base_mensal: null,
        dia_previsto_pagamento: null, conta_bancaria_id: null, de_outro_modulo: true },
];
const orc = (id, item, mes, valor, extra = {}) => ({ id, item_receita_id: item, mes_referencia: `${mes}-01`, valor_esperado: valor,
    periodicidade: 'MENSAL_FIXA', observacoes: null, data_prevista: null, ...extra });
const ORCAMENTOS = [
    orc(1, 10, '2031-02', 5000), orc(2, 10, '2031-03', 5000), orc(3, 10, '2031-04', 5000), orc(4, 10, '2031-05', 5000),
    orc(5, 11, '2031-04', 1200), orc(6, 12, '2031-04', 800, { periodicidade: 'UNICA' }),
    orc(7, 13, '2031-04', 0, { observacoes: 'Removido pelo usuário' }),  // removida: sai da lista
    orc(8, 13, '2031-03', 40, { data_prevista: '2031-04-02' }),  // data prevista em outro mes; atrasada
    orc(9, 11, '2031-03', 1200),  // recebida acima do previsto em 03: nao aparece em 04
];
const real = (id, item, mes, valor, data, extra = {}) => ({ id, item_receita_id: item, mes_referencia: `${mes}-01`, competencia: `${mes}-01`,
    valor_recebido: valor, data_recebimento: data, conta_bancaria_id: 1, descricao: `Receb ${id}`, observacoes: '', orcamento_id: null,
    estornada: false, ...extra });
const REALIZADAS = [
    real(100, 10, '2031-02', 5000, '2031-02-05'),
    real(101, 11, '2031-04', 500, '2031-04-10', { conta_bancaria_id: 2 }),  // parcial
    real(102, 12, '2031-04', 800, '2031-04-12'),  // realizada (um recebimento)
    real(103, 11, '2031-03', 1300, '2031-03-30'),
    real(104, 14, '2031-04', 350, '2031-04-15'),  // fonte nao recorrente sem previsao: linha pontual
    real(105, null, '2031-04', 77.7, '2031-04-20', { descricao: 'Pix avulso' }),  // sem fonte
    real(106, 16, '2031-04', 9000, '2031-04-25', { conta_bancaria_id: null, observacoes: 'consorcio_id=3' }),  // aguardando confirmacao
    real(107, 15, '2031-04', 99, '2031-04-10'),  // fonte recorrente sem previsao: a linha virtual do Flask nao existe aqui
];

test('a mesma lista do desktop (receitas.js original + adaptacoes), na mesma ordem e com os mesmos campos', async () => {
    const ctx = await desktop();
    for (const anoMes of ['2031-04-01', '2031-03-01', '2031-02-01', '2031-05-01']) {
        // Como carregarReceitasMes: fontes, contas e previsoes do ano no estado antes de montar.
        vm.runInContext('estado.fontes = __f; estado.contasBancarias = __c; estado.orcamentos = __o;',
            Object.assign(ctx, { __f: FONTES, __c: CONTAS, __o: ORCAMENTOS }));
        const original = json(ctx.montarReceitasMes(ORCAMENTOS, REALIZADAS, anoMes));
        const nosso = json(montarReceitasMes({ orcamentos: ORCAMENTOS, realizadas: REALIZADAS, anoMes, fontes: FONTES, contas: CONTAS }));
        assert.deepEqual(nosso, original, anoMes);
    }
    const abril = montarReceitasMes({ orcamentos: ORCAMENTOS, realizadas: REALIZADAS, anoMes: '2031-04-01', fontes: FONTES, contas: CONTAS });
    assert.deepEqual(abril.map((r) => [r.uid, r.status, r.competencia.slice(0, 7)]), [
        // situacao (prevista, parcial, realizada), competencia e nome
        ['orc-8', 'PREVISTA', '2031-03'], ['orc-2', 'PREVISTA', '2031-03'], ['pend-real-106', 'PREVISTA', '2031-04'],
        ['orc-3', 'PREVISTA', '2031-04'], ['orc-5', 'PARCIAL', '2031-04'], ['orc-6', 'REALIZADA', '2031-04'],
        ['real-105', 'REALIZADA', '2031-04'], ['real-104', 'REALIZADA', '2031-04'],
    ]);
});

test('separacao do mes e das atrasadas, filtros Tipo e Busca, e totais: os do desktop', async () => {
    const ctx = await desktop();
    const casos = [['', ''], ['ALUGUEL', ''], ['', 'banco a'], ['', 'SALÁRIO'], ['PONTUAL', ''], ['RENDA_EXTRA', 'freela']];
    for (const [tipo, busca] of casos) {
        vm.runInContext(`estado.fontes = __f; estado.contasBancarias = __c; estado.orcamentos = __o; estado.anoAtual = 2031; estado.mesAtual = '04';
            estado.tipoFiltro = __t; estado.busca = __b; estado.receitasMes = montarReceitasMes(__o, __r, '2031-04-01');
            aplicarFiltrosLocais();`, Object.assign(ctx, { __f: FONTES, __c: CONTAS, __t: tipo, __b: busca.trim(), __o: ORCAMENTOS, __r: REALIZADAS }));
        const filtradas = json(vm.runInContext('estado.receitasFiltradas', ctx));
        const atrasadas = json(vm.runInContext('estado.receitasAtrasadas', ctx));
        const linhas = montarReceitasMes({ orcamentos: ORCAMENTOS, realizadas: REALIZADAS, anoMes: '2031-04-01', fontes: FONTES, contas: CONTAS });
        const nosso = separarReceitas(linhas, '2031-04-01', { tipo, busca });
        assert.deepEqual(json(nosso.doMes), filtradas, `mes ${tipo}/${busca}`);
        assert.deepEqual(json(nosso.atrasadas), atrasadas, `atrasadas ${tipo}/${busca}`);
        // Previsto e Realizado: renderizarKpis (soma das linhas filtradas); Pendente: a conta de "Recebimentos pendentes".
        const t = totaisDaLista(nosso.doMes);
        const c = (v) => Math.round(v * 100);
        assert.equal(t.previsto, c(filtradas.reduce((s, r) => s + r.valor_previsto, 0)));
        assert.equal(t.recebido, c(filtradas.reduce((s, r) => s + r.valor_realizado, 0)));
        assert.equal(t.pendente, c(filtradas.filter((r) => ['PREVISTA', 'PARCIAL'].includes(r.status))
            .reduce((s, r) => s + (r.valor_previsto - r.valor_realizado), 0)));
    }
    const { doMes } = separarReceitas(montarReceitasMes({ orcamentos: ORCAMENTOS, realizadas: REALIZADAS, anoMes: '2031-04-01',
        fontes: FONTES, contas: CONTAS }), '2031-04-01');
    // Previsto 5000+9000+1200+800 = 16000; recebido 500+800+350+77,70; pendente 5000+9000+700
    assert.deepEqual(totaisDaLista(doMes), { previsto: 1600000, recebido: 172770, pendente: 1470000 });
});

test('datas previstas como o desktop: dia da fonte (limitado ao mes) ou a data gravada na previsao', async () => {
    const ctx = await desktop();
    for (const [anoMes, dia] of [['2031-04-01', 31], ['2031-02-01', 30], ['2031-04-01', null], ['2031-03-01', '2031-04-02'], ['2032-02-01', 29]]) {
        assert.equal(montarDataPrevista(anoMes, dia), ctx.montarDataPrevista(anoMes, dia), `${anoMes} ${dia}`);
    }
});

test('linha: valor, legenda discreta e recebimentos; acoes so as que o desktop permite e o banco aceita', () => {
    const linhas = montarReceitasMes({ orcamentos: ORCAMENTOS, realizadas: REALIZADAS, anoMes: '2031-04-01', fontes: FONTES, contas: CONTAS });
    const por = Object.fromEntries(linhas.map((l) => [l.uid, l]));
    const leg = (uid) => legendaDaReceita(por[uid], recebimentosDaLinha(por[uid], REALIZADAS));
    assert.deepEqual(['orc-3', 'orc-8', 'orc-5', 'orc-6', 'real-104', 'pend-real-106'].map(leg),
        ['Prev. 05/04', 'Prev. 02/04', 'Prev. 30/04 · parcial', 'Receb. 12/04 · recebida', 'Receb. 15/04 · recebida',
            'Prev. 25/04 · aguardando confirmação']);
    assert.deepEqual(['orc-3', 'orc-5', 'orc-6'].map((u) => valorDaLinha(por[u])), [500000, 120000, 80000]);
    assert.deepEqual(recebimentosDaLinha(por['orc-5'], REALIZADAS).map((r) => r.id), [101]);
    const acoes = (uid) => Object.entries(acoesDaReceita(por[uid])).filter(([, v]) => v).map(([k]) => k);
    assert.deepEqual(acoes('orc-3'), ['receber', 'editar', 'cancelar']);
    assert.deepEqual(acoes('orc-5'), ['receber', 'editar'], 'parcial: sem cancelar (o banco recusa) e sem estorno (o desktop nao oferece)');
    assert.deepEqual(acoes('orc-6'), ['editar', 'estornar']);
    assert.deepEqual(acoes('real-104'), ['editar', 'estornar']);
    assert.deepEqual(acoes('real-105'), ['estornar'], 'sem fonte: nada a editar');
    assert.deepEqual(acoes('pend-real-106'), ['receber'], 'contemplacao do consorcio: so confirmar');
});
