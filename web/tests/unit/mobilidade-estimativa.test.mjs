// FIN-MVP-MOB-01 — estimativa do comparativo de Mobilidade (js/original/veiculos.js do Flask, carregado sem alteracao): a
// previsao de combustivel coberta pela recorrencia (SUPRIMIDA) nao vira despesa, mas continua valendo para comparar.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const ORIGINAL = new URL('../../../frontend/static/js/veiculos.js', import.meta.url);

function carregarOriginal() {
    const nada = () => {};
    const contexto = { console, Set, Map, Date, document: { addEventListener: nada, getElementById: () => null, querySelectorAll: () => [] },
        localStorage: { getItem: () => null, setItem: nada } };
    contexto.window = contexto;
    vm.createContext(contexto);
    vm.runInContext(readFileSync(ORIGINAL, 'utf8'), contexto);
    return contexto;
}

const { calcularCustoMensalEstimado, rotuloCombustivel, rotuloStatusPrevista, statusEntraNaEstimativa } = carregarOriginal();
const hoje = new Date();
const mes = (n) => new Date(hoje.getFullYear(), hoje.getMonth() + n, 1).toLocaleDateString('en-CA');
const prevista = (status, tipo, n = 0, valor = 100) => ({ status, tipo_evento: tipo, data_prevista: mes(n), valor_previsto: valor });

test('combustivel coberto pela recorrencia entra na estimativa; as demais suprimidas nao', () => {
    assert.equal(statusEntraNaEstimativa('SUPRIMIDA', 'COMBUSTIVEL'), true);
    assert.equal(statusEntraNaEstimativa('SUPRIMIDA', 'TRANSPORTE_APP'), false);
    assert.equal(statusEntraNaEstimativa('IGNORADA', 'COMBUSTIVEL'), false);
    assert.equal(statusEntraNaEstimativa('PREVISTA', 'IPVA'), true);
});

test('a estimativa mensal do veiculo nao muda quando a recorrencia e ativada', () => {
    const lista = (status) => Array.from({ length: 12 }, (_, n) => prevista(status, 'COMBUSTIVEL', n));
    assert.equal(calcularCustoMensalEstimado(lista('SUPRIMIDA')), calcularCustoMensalEstimado(lista('PREVISTA')));
    assert.equal(calcularCustoMensalEstimado(lista('SUPRIMIDA')), 100);
});

test('rotulos', () => {
    assert.equal(rotuloStatusPrevista('SUPRIMIDA'), 'Coberta pela recorrência');
    assert.equal(rotuloStatusPrevista('PREVISTA'), 'PREVISTA');
    assert.equal(rotuloCombustivel({ combustivel: 'flex', combustivel_referencia: 'etanol' }), 'flex (etanol)');
    assert.equal(rotuloCombustivel({ combustivel: 'gasolina' }), 'gasolina');
});
