// FIN-MVP-MOBILE-07 — regras de exibicao dos movimentos nas Contas mobile (js/contas-movimentos.js): natureza pelos vinculos
// gravados pelo banco, sinal pelo tipo, filtro por tipo, periodo do mes e identificacao da conta. Nenhum saldo e calculado.
import assert from 'node:assert/strict';
import test from 'node:test';

import {
    TIPOS_DO_FILTRO, ehEntrada, filtrarMovimentos, naturezaDoMovimento, periodoDoMes, rotuloDaConta, sinalDoMovimento,
} from '../../src/js/contas-movimentos.js';

const mov = (dados) => ({ tipo: 'DEBITO', origem: 'MANUAL', ajustavel: false, ...dados });

test('natureza pelos vinculos do movimento, na ordem: transferencia, estorno, ajuste, fatura, despesa, recebimento', () => {
    const casos = [
        [mov({ tipo: 'DEBITO', transferencia_id: 'a', origem: 'TRANSFERENCIA' }), 'transferencia', 'Transferência enviada'],
        [mov({ tipo: 'CREDITO', transferencia_id: 'a', origem: 'TRANSFERENCIA' }), 'transferencia', 'Transferência recebida'],
        // o estorno do pagamento de uma despesa continua vinculado a despesa, mas e um estorno
        [mov({ tipo: 'CREDITO', conta_id: 7, movimento_original_id: 3, origem: 'ESTORNO' }), 'estorno', 'Estorno'],
        [mov({ tipo: 'CREDITO', origem: 'AJUSTE', ajustavel: true }), 'ajuste', 'Ajuste de saldo'],
        [mov({ fatura_id: 9, origem: 'FATURA' }), 'fatura', 'Pagamento de fatura'],
        [mov({ conta_id: 7, origem: 'DESPESA' }), 'despesa', 'Pagamento de despesa'],
        [mov({ tipo: 'CREDITO', receita_realizada_id: 5, origem: 'RECEITA' }), 'receita', 'Recebimento'],
        [mov({ financiamento_parcela_id: 2, origem: 'FINANCIAMENTO' }), 'financiamento', 'Parcela de financiamento'],
        [mov({ tipo: 'CREDITO', origem: 'FLASK' }), 'outro', 'Entrada'],
        [mov({ tipo: 'DEBITO' }), 'outro', 'Saída'],
    ];
    for (const [m, chave, rotulo] of casos) assert.deepEqual(naturezaDoMovimento(m), { chave, rotulo }, JSON.stringify(m));
});

test('sinal pelo tipo (credito entra, debito sai) e filtro por tipo sobre o extrato do periodo', () => {
    const lista = [
        mov({ id: 1, tipo: 'CREDITO', receita_realizada_id: 5 }), mov({ id: 2, conta_id: 7 }),
        mov({ id: 3, tipo: 'CREDITO', conta_id: 7, movimento_original_id: 2 }), mov({ id: 4, transferencia_id: 'x' }),
        mov({ id: 5, fatura_id: 9 }), mov({ id: 6, tipo: 'CREDITO', origem: 'AJUSTE', ajustavel: true }),
    ];
    assert.deepEqual(lista.map(sinalDoMovimento), ['+', '−', '+', '−', '−', '+']);
    assert.deepEqual(lista.filter(ehEntrada).map((m) => m.id), [1, 3, 6]);
    const ids = (tipo) => filtrarMovimentos(lista, tipo).map((m) => m.id);
    assert.deepEqual(ids(''), [1, 2, 3, 4, 5, 6]);
    assert.deepEqual(ids('entradas'), [1, 3, 6]);
    assert.deepEqual(ids('saidas'), [2, 4, 5]);
    assert.deepEqual(ids('transferencia'), [4]);
    assert.deepEqual(ids('estorno'), [3]);
    assert.deepEqual(ids('despesa'), [2]);
    assert.deepEqual(ids('receita'), [1]);
    assert.deepEqual(ids('fatura'), [5]);
    assert.deepEqual(ids('ajuste'), [6]);
    assert.deepEqual(TIPOS_DO_FILTRO.map(([v]) => v), ['', 'entradas', 'saidas', 'transferencia', 'estorno', 'despesa', 'receita', 'fatura', 'ajuste']);
});

test('periodo do mes (inclusive fevereiro bissexto) e identificacao da conta sem agencia nem numero', () => {
    assert.deepEqual(periodoDoMes('2026-11'), { inicio: '2026-11-01', fim: '2026-11-30' });
    assert.deepEqual(periodoDoMes('2028-02'), { inicio: '2028-02-01', fim: '2028-02-29' });
    assert.deepEqual(periodoDoMes('2031-12'), { inicio: '2031-12-01', fim: '2031-12-31' });
    const corrente = { nome: 'Conta G', tipo: 'Conta Corrente', instituicao: 'Banco A', status: 'ATIVO', agencia: '1234', numero_conta: '99' };
    const poupanca = { nome: 'conta g ', tipo: 'Poupança', instituicao: 'Banco B', status: 'ATIVO' };
    const reserva = { nome: 'Reserva', tipo: 'Poupança', instituicao: 'Banco A', status: 'ATIVO' };
    // Nomes diferentes: so o nome; nomes iguais: o tipo e a instituicao para diferenciar (nunca agencia nem numero).
    assert.equal(rotuloDaConta(corrente, [corrente, reserva]), 'Conta G');
    assert.equal(rotuloDaConta(corrente, [corrente, poupanca, reserva]), 'Conta G (Conta Corrente · Banco A)');
    assert.equal(rotuloDaConta(poupanca, [corrente, poupanca]), 'conta g  (Poupança · Banco B)');
    assert.equal(rotuloDaConta({ nome: 'Antiga', tipo: '', instituicao: null, status: 'INATIVO' }, []), 'Antiga · inativa');
});
