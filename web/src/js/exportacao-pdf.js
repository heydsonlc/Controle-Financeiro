// FIN-RELATORIOS-CONFIG-1 — PDF minimo, o mesmo do Flask (IrRelatorioService._pdf_simples): uma pagina A4, Helvetica 10,
// 52 linhas por bloco, texto em latin-1 ('?' no que nao cabe), ate 115 caracteres por linha. Sem biblioteca.

function latin1(texto) {
    const bytes = [];
    for (const caractere of texto) {
        const codigo = caractere.codePointAt(0);
        bytes.push(codigo <= 0xff ? codigo : 0x3f);
    }
    return bytes;
}

const ascii = (texto) => [...texto].map((c) => c.charCodeAt(0));

export function pdfSimples(linhas) {
    const seguras = linhas.map((linha) => {
        const texto = String(linha ?? '').replaceAll('\\', '\\\\').replaceAll('(', '\\(').replaceAll(')', '\\)');
        // encode('latin-1', 'replace')[:115] do Python: corta por caracteres depois da troca.
        return String.fromCharCode(...latin1(texto)).slice(0, 115);
    });
    const conteudo = ['BT', '/F1 10 Tf', '50 800 Td', '14 TL'];
    seguras.forEach((linha, indice) => {
        if (indice && indice % 52 === 0) conteudo.push('ET', 'BT', '/F1 10 Tf', '50 800 Td', '14 TL');
        conteudo.push(`(${linha}) Tj`, 'T*');
    });
    conteudo.push('ET');
    const stream = latin1(conteudo.join('\n'));
    const objetos = [
        ascii('1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n'),
        ascii('2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n'),
        ascii('3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n'),
        ascii('4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n'),
        [...ascii(`5 0 obj << /Length ${stream.length} >> stream\n`), ...stream, ...ascii('\nendstream endobj\n')],
    ];
    const saida = [...ascii('%PDF-1.4\n')];
    const deslocamentos = [];
    for (const objeto of objetos) {
        deslocamentos.push(saida.length);
        saida.push(...objeto);
    }
    const xref = saida.length;
    saida.push(...ascii(`xref\n0 ${objetos.length + 1}\n`), ...ascii('0000000000 65535 f \n'));
    for (const d of deslocamentos) saida.push(...ascii(`${String(d).padStart(10, '0')} 00000 n \n`));
    saida.push(...ascii(`trailer << /Size ${objetos.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`));
    return new Uint8Array(saida);
}
