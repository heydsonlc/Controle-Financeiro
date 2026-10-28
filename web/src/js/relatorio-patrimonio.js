// FIN-RELATORIOS-CONFIG-1 — relatorio de bens patrimoniais da Empresa (Excel e PDF), igual ao do Flask
// (PatrimonioRelatorioService): planilha "Resumo" (campos e totais por categoria) e "Bens"; PDF com as mesmas linhas.
// Entrada: os bens como patrimonio_bens_tela os devolve (os mesmos dicionarios do Flask, valor como float).
// Os totais imitam o Decimal do Python sobre str(float) (escala do maior numero de casas) e a moeda do Python
// (f"{Decimal:,.2f}", arredondamento meio-para-par).

import { gerarXlsx } from './exportacao-xlsx.js';
import { pdfSimples } from './exportacao-pdf.js';

// ---- Decimal(str(float)) --------------------------------------------------------------------------------------------
const textoFloat = (n) => (Number.isInteger(n) ? `${n}.0` : String(n));

function decimal(valor) {
    const n = Number(valor || 0);
    const texto = Number.isFinite(n) ? (valor === null || valor === undefined || valor === '' ? '0' : textoFloat(n)) : '0';
    const [inteiro, fracao = ''] = texto.replace('-', '').split('.');
    return { negativo: texto.startsWith('-'), digitos: BigInt(inteiro + fracao), escala: fracao.length };
}

function somar(a, b) {
    const escala = Math.max(a.escala, b.escala);
    const va = (a.negativo ? -1n : 1n) * a.digitos * 10n ** BigInt(escala - a.escala);
    const vb = (b.negativo ? -1n : 1n) * b.digitos * 10n ** BigInt(escala - b.escala);
    const s = va + vb;
    return { negativo: s < 0n, digitos: s < 0n ? -s : s, escala };
}

function textoDecimal(d) {
    let s = d.digitos.toString().padStart(d.escala + 1, '0');
    if (d.escala) s = `${s.slice(0, -d.escala)}.${s.slice(-d.escala)}`;
    return (d.negativo && d.digitos !== 0n ? '-' : '') + s;
}

const numeroDecimal = (d) => ({ numero: Number(textoDecimal(d)), decimal: true, texto: textoDecimal(d) });

// f"R$ {Decimal:,.2f}" com virgula decimal e ponto de milhar.
function moeda(valor) {
    const d = typeof valor === 'object' && valor !== null && 'digitos' in valor ? valor : decimal(valor);
    let centavos = d.digitos;
    if (d.escala > 2) {
        const fator = 10n ** BigInt(d.escala - 2);
        const resto = centavos % fator;
        centavos /= fator;
        const metade = fator / 2n;
        if (resto > metade || (resto === metade && centavos % 2n === 1n)) centavos += 1n;
    } else {
        centavos *= 10n ** BigInt(2 - d.escala);
    }
    const inteiro = (centavos / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    const fracao = (centavos % 100n).toString().padStart(2, '0');
    return `R$ ${d.negativo && centavos !== 0n ? '-' : ''}${inteiro},${fracao}`;
}

function data(valor) {
    const texto = String(valor || '').trim();
    if (!texto) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(texto);
    return m ? `${m[3]}/${m[2]}/${m[1]}` : texto.slice(0, 10);
}

function descreverFiltros(filtros) {
    const itens = ['categoria', 'status', 'documento', 'ano', 'busca'].filter((k) => filtros[k]).map((k) => `${k}=${filtros[k]}`);
    return itens.length ? itens.join('; ') : 'Sem filtros adicionais';
}

function resumo(bens) {
    let total = decimal(0);
    const porCategoria = new Map();
    let comLastro = 0;
    let pendentes = 0;
    let semDocumento = 0;
    for (const bem of bens) {
        const valor = decimal(bem.valor_aquisicao);
        total = somar(total, valor);
        const categoria = bem.categoria || 'Sem categoria';
        const atual = porCategoria.get(categoria) || { quantidade: 0, valor: decimal(0) };
        porCategoria.set(categoria, { quantidade: atual.quantidade + 1, valor: somar(atual.valor, valor) });
        const status = String(bem.status_documental || '').toUpperCase();
        if (['COM_LASTRO', 'COM_DOCUMENTO', 'VALIDADO'].includes(status)) comLastro += 1;
        if (['SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR', 'DIVERGENTE'].includes(status)) pendentes += 1;
        if (status === 'SEM_DOCUMENTO') semDocumento += 1;
    }
    return { total, porCategoria, comLastro, pendentes, semDocumento };
}

const nomeArquivo = (filtros, ano, extensao) => `Bens_Patrimoniais_Empresa_${filtros.ano || ano}.${extensao}`;

// agora: 'dd/mm/aaaa hh:mm' (hora local, como datetime.now() do Flask); anoAtual para o nome sem filtro de ano.
export function excelDeBens({ perfilNome, bens, filtros, agora, anoAtual }) {
    const r = resumo(bens);
    const linhasResumo = [
        ['Campo', 'Valor'],
        ['Perfil financeiro', perfilNome || 'Empresa'],
        ['Data de geracao', agora],
        ['Filtros aplicados', descreverFiltros(filtros)],
        ['Total de bens', bens.length],
        ['Valor total', numeroDecimal(r.total)],
        ['Com lastro/documento', r.comLastro],
        ['Pendentes de documento', r.pendentes],
        ['Sem documento', r.semDocumento],
        [],
        ['Categoria', 'Quantidade', 'Valor total'],
        ...[...r.porCategoria].map(([categoria, d]) => [categoria, d.quantidade, numeroDecimal(d.valor)]),
    ];
    const linhasBens = [
        ['Nome', 'Codigo', 'Categoria', 'Data de aquisicao', 'Valor de aquisicao', 'Fornecedor', 'Documento', 'Status',
         'Status documental', 'Centro de custo', 'Localizacao', 'Responsavel'],
        ...bens.map((b) => [b.nome ?? null, b.codigo ?? null, b.categoria ?? null, data(b.data_aquisicao),
            { numero: Number(textoDecimal(decimal(b.valor_aquisicao))), decimal: false }, b.fornecedor ?? null, b.documento_label ?? null,
            b.status_label ?? null, b.status_documental_label ?? null, b.centro_custo ?? null, b.localizacao ?? null,
            b.responsavel ?? null]),
    ];
    return {
        nome: nomeArquivo(filtros, anoAtual, 'xlsx'),
        conteudo: gerarXlsx([{ nome: 'Resumo', linhas: linhasResumo, monetarias: [2, 3] },
                             { nome: 'Bens', linhas: linhasBens, monetarias: [5] }]),
    };
}

export function pdfDeBens({ perfilNome, bens, filtros, agora, anoAtual }) {
    const r = resumo(bens);
    const linhas = [
        'Relatorio de Bens Patrimoniais',
        `Perfil financeiro: ${perfilNome || 'Empresa'}`,
        `Data de geracao: ${agora}`,
        `Filtros aplicados: ${descreverFiltros(filtros)}`,
        '',
        `Total de bens: ${bens.length}`,
        `Valor total: ${moeda(r.total)}`,
        `Com lastro/documento: ${r.comLastro}`,
        `Pendentes de documento: ${r.pendentes}`,
        '',
        'Lista de bens:',
        ...bens.map((b, i) => `${i + 1}. ${b.nome || '-'} | ${b.categoria || '-'} | ${data(b.data_aquisicao) ?? 'None'} | `
            + `${moeda(b.valor_aquisicao)} | ${b.status_documental_label || '-'}`),
    ];
    if (!bens.length) linhas.push('Nenhum bem encontrado para os filtros selecionados.');
    linhas.push('', 'Relatorio gerencial. Validar classificacao patrimonial e documental antes de uso contabil.');
    return { nome: nomeArquivo(filtros, anoAtual, 'pdf'), conteudo: pdfSimples(linhas) };
}
