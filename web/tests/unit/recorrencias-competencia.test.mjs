// MVP-FIN-AJUSTES-01 (P05/P06) — filtro de competencia e lista de Recorrencias (js/original/recorrencias.js do Flask,
// carregado sem alteracao). Dados FICTICIOS.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const ORIGINAL = new URL('../../../frontend/static/js/recorrencias.js', import.meta.url);

function carregarOriginal() {
    const nada = () => {};
    const contexto = { console, document: { addEventListener: nada, getElementById: () => null } };
    contexto.window = contexto;
    vm.createContext(contexto);
    vm.runInContext(readFileSync(ORIGINAL, 'utf8'), contexto);
    return contexto;
}

const { ocorreNaCompetencia, renderizarLinha } = carregarOriginal();
const item = (frequencia, raw) => ({ frequencia, raw });

test('mensal: a partir do mes de inicio, sem antecipar inicio futuro', () => {
    const mensal = item('mensal', { data_vencimento: '2031-03-31' });
    assert.equal(ocorreNaCompetencia(mensal, '2031-02'), false);
    assert.equal(ocorreNaCompetencia(mensal, '2031-03'), true);
    assert.equal(ocorreNaCompetencia(mensal, '2032-02'), true);
});

test('anual: so no mes do vencimento, a partir do inicio', () => {
    const anual = item('anual', { data_vencimento: '2031-03-10' });
    assert.equal(ocorreNaCompetencia(anual, '2030-03'), false);
    assert.equal(ocorreNaCompetencia(anual, '2031-03'), true);
    assert.equal(ocorreNaCompetencia(anual, '2031-04'), false);
    assert.equal(ocorreNaCompetencia(anual, '2032-03'), true);
});

test('semanal e a cada 2 semanas: a primeira ocorrencia e o inicio levado ao dia da semana', () => {
    // 2031-01-30 e quinta; dia 1 (segunda): a primeira ocorrencia cai em 03/02, fora de janeiro
    const semanal = item('semanal', { data_vencimento: '2031-01-30', dia_semana: 1, frequencia_semanas: 1 });
    assert.equal(ocorreNaCompetencia(semanal, '2031-01'), false);
    assert.equal(ocorreNaCompetencia(semanal, '2031-02'), true);
    // A cada 2 semanas a partir de 28/02/2031 (sexta): 14/03 e 28/03; depois 11/04
    const quinzenal = item('quinzenal', { data_vencimento: '2031-02-28', dia_semana: 5, frequencia_semanas: 2 });
    assert.equal(ocorreNaCompetencia(quinzenal, '2031-02'), true);
    assert.equal(ocorreNaCompetencia(quinzenal, '2031-03'), true);
    assert.equal(ocorreNaCompetencia(quinzenal, '2031-04'), true);
});

test('consorcio: so no prazo das parcelas', () => {
    const consorcio = item('parcelas', { mes_inicio: '2031-11-01', numero_parcelas: 3 });
    assert.equal(ocorreNaCompetencia(consorcio, '2031-10'), false);
    assert.equal(ocorreNaCompetencia(consorcio, '2031-11'), true);
    assert.equal(ocorreNaCompetencia(consorcio, '2032-01'), true);
    assert.equal(ocorreNaCompetencia(consorcio, '2032-02'), false);
});

test('sem data de inicio o cadastro continua listado', () => {
    assert.equal(ocorreNaCompetencia(item('mensal', { data_vencimento: null }), '2031-01'), true);
});

test('coluna Tipo removida da linha', () => {
    const linha = renderizarLinha({ origem: 'recorrencia', id: 1, nome: 'Plano', frequencia: 'mensal', valor: 10, categoriaNome: 'Casa',
        status: 'ativa', statusLabel: 'Ativa', meioPagamento: null, raw: { tipo_recorrencia: 'mensal' } });
    assert.doesNotMatch(linha, /recorrencias-pill type/);
});
