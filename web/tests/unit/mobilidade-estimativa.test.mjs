// FIN-MVP-MOB-01 — estimativa do comparativo de Mobilidade (js/original/veiculos.js do Flask, carregado sem alteracao): a
// previsao de combustivel coberta pela recorrencia (SUPRIMIDA) nao vira despesa, mas continua valendo para comparar.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const ORIGINAL = new URL('../../../frontend/static/js/veiculos.js', import.meta.url);

function carregarOriginal() {
    const nada = () => {};
    const contexto = { console, Set, Map, Date, addEventListener: nada,
        document: { addEventListener: nada, getElementById: () => null, querySelectorAll: () => [] },
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

// FIN-MVP-MOB-01: abastecimento. Os litros saem do valor e do preco, sem arredondar; a tela mostra tres casas.
test('litros calculados pelo valor e pelo preco', () => {
    const { calcularLitros, formatarLitros } = carregarOriginal();
    assert.equal(calcularLitros('176.00', '4.40'), 40);
    assert.equal(formatarLitros(calcularLitros(176, 4.4)), '40,000');
    assert.equal(formatarLitros(calcularLitros(150.33, 5.899)), '25,484');
    for (const [valor, preco] of [[0, 4.4], [176, 0], ['', ''], [-1, 4.4]]) assert.equal(calcularLitros(valor, preco), null);
    assert.equal(formatarLitros(null), '—');
});

test('combustiveis aceitos pelo veiculo', () => {
    const { combustiveisDoVeiculo } = carregarOriginal();
    assert.deepEqual([...combustiveisDoVeiculo({ combustivel: 'flex' })], ['gasolina', 'etanol']);
    assert.deepEqual([...combustiveisDoVeiculo({ combustivel: 'etanol' })], ['etanol']);
    assert.deepEqual([...combustiveisDoVeiculo({ combustivel: 'eletrico' })], []);
    assert.equal(combustiveisDoVeiculo({ combustivel: 'outro' }).length, 5);
});

test('conflitos da troca: cada despesa com as duas opcoes, sem escolha marcada', () => {
    const { htmlConflitosTroca } = carregarOriginal();
    assert.equal(htmlConflitosTroca(undefined), '');
    const html = htmlConflitosTroca({
        decidir: [{ natureza: 'CONTA', registro_id: 7, competencia: '2026-12-01', descricao: 'Combustivel', valor: 200 }],
        sem_alteracao: [{ natureza: 'CONTA', registro_id: 6, competencia: '2026-11-01', descricao: 'Combustivel', valor: 200 }],
    });
    assert.equal((html.match(/type="radio"/g) || []).length, 2);
    assert.match(html, /name="troca-CONTA-7" value="MANTER"/);
    assert.match(html, /name="troca-CONTA-7" value="SUBSTITUIR"/);
    assert.doesNotMatch(html, /checked/);
    assert.match(html, /Não mudam nesta troca/);
});
