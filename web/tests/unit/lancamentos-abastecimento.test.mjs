// FIN-MOB-ABAST-LANCAMENTOS-01 — litros do bloco "Dados do Abastecimento" (js/lancamentos-abastecimento.js, script classico
// carregado como na pagina, sem o formulario). Dados FICTICIOS.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

function carregar() {
    const contexto = { console, document: { readyState: 'complete', getElementById: () => null, addEventListener: () => {} } };
    contexto.window = contexto;
    vm.createContext(contexto);
    vm.runInContext(readFileSync(new URL('../../src/js/lancamentos-abastecimento.js', import.meta.url), 'utf8'), contexto);
    return contexto;
}

const { calcularLitrosAbastecimento: litros, formatarLitrosAbastecimento: formatar, dadosAbastecimentoDoFormulario } = carregar();

test('litros = valor total / preco por litro, sem arredondar', () => {
    assert.equal(litros(176, 4.4), 40);
    assert.equal(litros('200', '4.40'), 200 / 4.4);
    assert.equal(formatar(litros(200, 4.4)), '45,455 L');
    assert.equal(formatar(litros(150, 3.759)), '39,904 L');
});

test('sem valor ou preco positivo nao ha litros', () => {
    for (const [valor, preco] of [[0, 4], [176, 0], [176, -1], ['', 4], [176, '']]) {
        assert.equal(litros(valor, preco), null);
    }
    assert.equal(formatar(null), '—');
});

test('fora da tela nao quebra o adaptador', () => {
    assert.equal(typeof dadosAbastecimentoDoFormulario, 'function');
});
