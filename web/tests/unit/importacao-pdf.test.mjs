// FIN-FIDELIDADE-CARTOES-2 — PDF da fatura Caixa: extracao pelo PDF.js (o mesmo pacote do navegador, build legacy) e
// regras do Flask (parse_texto_caixa). Conferido tambem contra o pdfplumber do Flask (mesmo texto, fatura e linhas).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs';

import { linhasDaPagina, parseTextoCaixa, textoDoPdf } from '../../src/js/importacao-pdf.js';
import { faturaCaixaFicticia, gerarPdf } from '../pdf-ficticio.mjs';

const buffer = (b) => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);

test('fatura Caixa ficticia: texto por posicao, dados da fatura e lancamentos como o Flask', async () => {
    const paginas = await textoDoPdf(buffer(faturaCaixaFicticia()), pdfjs);
    assert.ok(paginas[0].includes('10/10 APP STORE 9,99 52,30 D'));
    const r = parseTextoCaixa(paginas, '2026-11');
    assert.deepEqual([r.fatura.vencimento, r.fatura.valor_total, r.fatura.cartoes_detectados], ['2026-11-12', 457.69, ['1234']]);
    assert.deepEqual(r.linhas.map((l) => [l.data_compra, l.descricao_normalizada, l.valor, l.tipo_movimento, l.parcela, l.grupo]), [
        ['2026-10-29', 'ESTORNO LOJA FICTICIA', 15, 'credito', '1/1', 'CREDITOS'],      // credito antes do cartao
        ['2026-10-05', 'PADARIA CENTRAL', 27.4, 'debito', '1/1', 'COMPRAS'],
        ['2026-10-07', 'POSTO RODOVIA', 150, 'debito', '1/1', 'COMPRAS'],
        ['2026-08-15', 'LOJA DE MOVEIS', 120, 'debito', '3/5', 'COMPRAS PARCELADAS'],
        ['2026-10-10', 'APP STORE', 52.3, 'debito', '1/1', 'COMPRAS INTERNACIONAIS'],
        ['2026-11-01', 'ANUIDADE PARCELA', 30, 'debito', '1/12', 'ANUIDADE'],             // sem data: a competencia
        ['2026-10-11', 'AJUSTE A CREDITO', 7.99, 'credito', '1/1', 'ANUIDADE'],
    ]);
    assert.equal(r.linhas.find((l) => l.grupo === 'COMPRAS INTERNACIONAIS').metadados.cotacao, 5.235);
    assert.ok(r.linhas.every((l) => l.tipo_movimento === 'debito' || l.ignorar));  // credito nunca vira compra
});

test('arquivo invalido e PDF sem texto (escaneado): mensagens claras, nada lido', async () => {
    await assert.rejects(textoDoPdf(new TextEncoder().encode('nao e pdf').buffer, pdfjs), /Arquivo PDF inválido/);
    await assert.rejects(textoDoPdf(buffer(gerarPdf([[]])), pdfjs), /PDF sem texto extraivel/);
});

test('pagina sem "Demonstrativo" e competencia invalida', () => {
    assert.deepEqual(parseTextoCaixa(['COMPRAS\n05/10 LOJA 10,00 D'], '2026-11').linhas, []);
    assert.throws(() => parseTextoCaixa(['x'], 'novembro'), /competencia invalida/);
});

test('linhas pela posicao: mesma altura (ate 3) na mesma linha; espaco so quando ha distancia', () => {
    const item = (str, x, y, width) => ({ str, transform: [1, 0, 0, 1, x, y], width });
    assert.equal(linhasDaPagina([item('B', 50, 702, 5), item('A', 10, 700, 10), item('C', 55.5, 700, 5), item('linha 2', 10, 680, 30)]),
        'A BC\nlinha 2');
});
