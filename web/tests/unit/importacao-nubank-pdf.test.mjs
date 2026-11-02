// FIN-CARTOES-MULTIPLOS-01 — PDF da fatura do Nubank: cada compra com o final do cartao (titular ou adicional); linhas sem
// cartao (IOF, credito, servico, pagamento) ficam sem cartao identificado. Dados FICTICIOS (finais 1111 e 2222).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs';

import { eFaturaNubank, parseTextoCaixa, parseTextoNubank, textoDoPdf } from '../../src/js/importacao-pdf.js';
import { faturaCaixaFicticia, gerarPdf } from '../pdf-ficticio.mjs';

const buffer = (b) => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);

const RESUMO = ['TITULAR FICTICIO', 'FATURA 08 JAN 2027 EMISSÃO E ENVIO 29 DEZ 2026', 'Pagamento recebido −R$ 500,00',
    'Total a pagar R$ 1.234,56', 'Nu Pagamentos S.A. SAC 0000 0000'].join('\n');
const TRANSACOES = ['TITULAR FICTICIO', 'FATURA 08 JAN 2027 EMISSÃO E ENVIO 29 DEZ 2026', 'TRANSAÇÕES DE 29 NOV A 29 DEZ',
    'Titular Ficticio R$ 100,00',
    '29 NOV •••• 1111 Loja Movel - Parcela 3/10 R$ 80,00',
    '30 NOV •••• 1111 Supermercado Ficticio R$ 50,00',
    '02 DEZ Plano Celular R$ 70,00',
    '03 DEZ IOF de "Nuvem" R$ 0,93',
    '03 DEZ IOF de volta de Nuvem −R$ 0,93',
    'USD 5.00',
    'Compras de Adicional Ficticio R$ 50,00',
    '04 DEZ •••• 2222 Supermercado Ficticio R$ 50,00',
    '05 JAN •••• 2222 Compra de Janeiro R$ 1,00',
    '02 DEZ Pagamento em 02 DEZ −R$ 500,00'].join('\n');

test('Nubank em texto: final do cartao, sem cartao, parcela, credito, ano pelo vencimento', () => {
    assert.equal(eFaturaNubank([RESUMO, TRANSACOES]), true);
    assert.equal(eFaturaNubank(['Demonstrativo Caixa']), false);
    const r = parseTextoNubank([RESUMO, TRANSACOES], '2027-01');
    assert.deepEqual([r.fatura.emissor, r.fatura.vencimento, r.fatura.valor_total, r.fatura.cartoes_detectados],
        ['Nubank', '2027-01-08', 1234.56, ['1111', '2222']]);
    assert.deepEqual(r.linhas.map((l) => [l.data_compra, l.descricao_normalizada, l.parcela, l.valor, l.tipo_movimento, l.cartao_final]), [
        ['2026-11-29', 'Loja Movel', '3/10', '80.00', 'debito', '1111'],
        ['2026-11-30', 'Supermercado Ficticio', '1/1', '50.00', 'debito', '1111'],
        ['2026-12-02', 'Plano Celular', '1/1', '70.00', 'debito', null],          // sem cartao no documento
        ['2026-12-03', 'IOF de "Nuvem"', '1/1', '0.93', 'debito', null],
        ['2026-12-03', 'IOF de volta de Nuvem', '1/1', '0.93', 'credito', null],
        ['2026-12-04', 'Supermercado Ficticio', '1/1', '50.00', 'debito', '2222'],  // a mesma compra, outro cartao
        ['2027-01-05', 'Compra de Janeiro', '1/1', '1.00', 'debito', '2222'],
        ['2026-12-02', 'Pagamento em 02 DEZ', '1/1', '500.00', 'credito', null]]); // a previa deixa o pagamento fora
    assert.ok(r.linhas.every((l) => !l.ignorar && l.origem_importacao === 'pdf'));
});

test('Nubank em PDF ficticio (texto pelo PDF.js) e a Caixa continua com o seu leitor', async () => {
    const pdf = gerarPdf([
        [[[40, 'TITULAR FICTICIO']], [[40, 'FATURA 08 JAN 2027']], [[40, 'Total a pagar R$ 99,00']], [[40, 'Nu Pagamentos S.A.']]],
        [[[40, 'FATURA 08 JAN 2027']], [[40, 'TRANSAÇÕES DE 29 NOV A 29 DEZ']],
            [[40, '29 NOV'], [90, '**** 1111'], [150, 'Padaria Ficticia'], [400, 'R$ 9,00']],
            [[40, '01 DEZ'], [150, 'Credito Ficticio'], [400, '-R$ 1,00']]],
    ]);
    const paginas = await textoDoPdf(buffer(pdf), pdfjs);
    assert.equal(eFaturaNubank(paginas), true);
    const r = parseTextoNubank(paginas, '2027-01');
    assert.deepEqual(r.linhas.map((l) => [l.data_compra, l.descricao_normalizada, l.valor, l.tipo_movimento, l.cartao_final]), [
        ['2026-11-29', 'Padaria Ficticia', '9.00', 'debito', '1111'], ['2026-12-01', 'Credito Ficticio', '1.00', 'credito', null]]);
    const caixa = await textoDoPdf(buffer(faturaCaixaFicticia()), pdfjs);
    assert.equal(eFaturaNubank(caixa), false);
    assert.ok(parseTextoCaixa(caixa, '2026-11').linhas.every((l) => l.tipo_movimento === 'credito' || l.cartao_final === '1234'));
});
