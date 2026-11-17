// FIN-CATEGORIAS-REORGANIZACAO-01 — reparticao por natureza gerencial: as partes somam sempre o total exibido.
import assert from 'node:assert/strict';
import test from 'node:test';

import { repartirPorNatureza, reparticaoDosIndicadores, textoDaReparticao } from '../../src/js/naturezas.js';

const NATUREZAS = new Map([[10, 'APORTE'], [20, 'NAO_DEFINIDO'], [30, 'AJUSTE_TECNICO'], [40, 'TRANSFERENCIA_INTERNA'], [50, 'CONSUMO']]);

test('lista: consumo, aportes e outras somam o total; sem natureza gravada ou sem categoria e consumo', () => {
    const despesas = [
        { categoria_id: 10, valor: 520.1 }, { categoria_id: 10, valor: 0.2 },      // aportes
        { categoria_id: 20, valor: 100 }, { categoria_id: 30, valor: 1.01 }, { categoria_id: 40, valor: 2 },  // outras
        { categoria_id: 50, valor: 33.33 }, { categoria_id: 99, valor: 10 }, { categoria_id: null, valor: 7.07 },  // consumo
    ];
    const p = repartirPorNatureza(despesas, NATUREZAS);
    assert.deepEqual(p, { consumo: 5040, aportes: 52030, outras: 10301 });
    assert.equal(p.consumo + p.aportes + p.outras, 67371);
});

test('lista: valor por funcao propria (fatura do cartao) e mapa ausente', () => {
    const despesas = [{ categoria_id: 10, valor: 1, valor_fatura: 250.5 }, { categoria_id: '10', valor: 3 }];
    assert.deepEqual(repartirPorNatureza(despesas, NATUREZAS, (d) => d.valor_fatura || d.valor), { consumo: 0, aportes: 25350, outras: 0 });
    assert.deepEqual(repartirPorNatureza(despesas, null), { consumo: 400, aportes: 0, outras: 0 });
});

test('indicadores do banco: so valem quando fecham com o total da tela', () => {
    const ind = { consumo: 900.1, aportes: 520, nao_definido: 10, ajustes_tecnicos: 1, transferencias_internas: 2, fluxo_total: 1433.1 };
    assert.deepEqual(reparticaoDosIndicadores(ind, 1433.1), { consumo: 90010, aportes: 52000, outras: 1300 });
    assert.equal(reparticaoDosIndicadores(ind, 1433.11), null);
    assert.equal(reparticaoDosIndicadores(null, 10), null);
    assert.deepEqual(reparticaoDosIndicadores({ consumo: 0, aportes: 0 }, 0), { consumo: 0, aportes: 0, outras: 0 });
});

test('texto: outras saidas so aparece quando ha valor', () => {
    const limpo = (t) => t.replace(/ /g, ' ');
    assert.equal(limpo(textoDaReparticao({ consumo: 90010, aportes: 52000, outras: 0 })), 'Consumo R$ 900,10 · Aportes R$ 520,00');
    assert.equal(limpo(textoDaReparticao({ consumo: 0, aportes: 0, outras: 1300 })), 'Consumo R$ 0,00 · Aportes R$ 0,00 · Outras saídas R$ 13,00');
});
