// FIN-FIDELIDADE-CARTOES-2 — gera PDF FICTICIO para os testes, sem biblioteca: paginas com linhas de texto em colunas
// (Helvetica, WinAnsi), como uma fatura impressa. Cada linha: [[x, 'texto'], ...]; linhas de cima para baixo.

const latin1 = (texto) => Buffer.from(texto, 'latin1');
const escapar = (t) => t.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');

export function gerarPdf(paginas) {
    const objetos = [];
    const novo = (conteudo) => { objetos.push(conteudo); return objetos.length; };
    const catalogo = novo(null);
    const raiz = novo(null);
    const fonte = novo('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>');
    const filhos = paginas.map((linhas) => {
        let y = 800;
        const fluxo = linhas.map((linha) => {
            const texto = linha.map(([x, t]) => `BT /F1 9 Tf ${x} ${y} Td (${escapar(t)}) Tj ET`).join('\n');
            y -= 14;
            return texto;
        }).join('\n');
        const conteudo = novo(`<< /Length ${latin1(fluxo).length} >>\nstream\n${fluxo}\nendstream`);
        return novo(`<< /Type /Page /Parent ${raiz} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 ${fonte} 0 R >> >> `
            + `/Contents ${conteudo} 0 R >>`);
    });
    objetos[catalogo - 1] = `<< /Type /Catalog /Pages ${raiz} 0 R >>`;
    objetos[raiz - 1] = `<< /Type /Pages /Kids [${filhos.map((f) => `${f} 0 R`).join(' ')}] /Count ${filhos.length} >>`;
    const partes = [latin1('%PDF-1.4\n')];
    let tamanho = partes[0].length;
    const deslocamentos = [];
    objetos.forEach((o, i) => {
        deslocamentos.push(tamanho);
        const b = latin1(`${i + 1} 0 obj\n${o}\nendobj\n`);
        partes.push(b);
        tamanho += b.length;
    });
    const xref = [`xref\n0 ${objetos.length + 1}\n0000000000 65535 f \n`,
        ...deslocamentos.map((d) => `${String(d).padStart(10, '0')} 00000 n \n`),
        `trailer\n<< /Size ${objetos.length + 1} /Root ${catalogo} 0 R >>\nstartxref\n${tamanho}\n%%EOF\n`].join('');
    partes.push(latin1(xref));
    return Buffer.concat(partes);
}

// Fatura FICTICIA no layout da Caixa (as linhas que o parser do Flask le).
export function faturaCaixaFicticia() {
    return gerarPdf([[
        [[40, 'Fatura Cartão de Crédito (ficticia)']],
        [[40, 'VENCIMENTO 12/11/2026']],
        [[40, 'Valor total desta fatura'], [420, 'R$ 457,69 D']],
        [[40, 'Demonstrativo de despesas']],
        [[40, '28/10'], [90, 'OBRIGADO PELO PAGAMENTO'], [420, '500,00 C']],
        [[40, '29/10'], [90, 'ESTORNO LOJA FICTICIA'], [420, '15,00 C']],
        [[40, 'TITULAR FICTICIO (Cartão 1234)']],
        [[40, 'COMPRAS']],
        [[40, '05/10'], [90, 'PADARIA CENTRAL'], [420, '27,40 D']],
        [[40, '07/10'], [90, 'POSTO RODOVIA'], [420, '150,00 D']],
        [[40, 'Total COMPRAS'], [420, '177,40 D']],
        [[40, 'COMPRAS PARCELADAS']],
        [[40, '15/08'], [90, 'LOJA DE MOVEIS 03 DE 05'], [420, '120,00 D']],
        [[40, 'COMPRAS INTERNACIONAIS']],
        [[40, '10/10'], [90, 'APP STORE'], [330, '9,99'], [420, '52,30 D']],
        [[330, '52,30'], [420, '5,2350']],
        [[40, 'ANUIDADE']],
        [[40, 'ANUIDADE PARCELA 1 de 12'], [420, '30,00 D']],
        [[40, '11/10'], [90, 'AJUSTE A CREDITO'], [420, '7,99 C']],
        [[40, 'Total final (cartão 1234)'], [420, '372,70 D']],
    ]]);
}
