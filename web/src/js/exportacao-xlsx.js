// FIN-RELATORIOS-CONFIG-1 — planilha XLSX sem biblioteca, com a formatacao que o Flask aplica com openpyxl
// (_formatar_planilha): cabecalho azul (1D4ED8) em negrito branco centralizado, painel congelado em A2, autofiltro nas
// dimensoes, largura = maior texto + 2 (entre 12 e 42) e 'R$ #,##0.00' nas colunas monetarias.
// Celulas: texto, numero ({ numero, decimal }) ou null (vazia). decimal=true imita Decimal do Python: o openpyxl nao
// aplica o formato monetario a Decimal (so a int/float); o texto da largura e o str() do Python.

const enc = new TextEncoder();

// ---- ZIP (armazenado, sem compressao) -------------------------------------------------------------------------------
const TABELA_CRC = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n += 1) {
        let c = n;
        for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        t[n] = c >>> 0;
    }
    return t;
})();

function crc32(bytes) {
    let c = 0xffffffff;
    for (const b of bytes) c = TABELA_CRC[(c ^ b) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
}

// quando: Date (hora local) gravada nas entradas; sem ela, data fixa (o arquivo nao depende do relogio).
function zip(arquivos, quando = null) {
    const partes = [];
    const central = [];
    let deslocamento = 0;
    const u16 = (v) => [v & 0xff, (v >>> 8) & 0xff];
    const u32 = (v) => [v & 0xff, (v >>> 8) & 0xff, (v >>> 16) & 0xff, (v >>> 24) & 0xff];
    const [hora, data] = quando
        ? [quando.getHours() << 11 | quando.getMinutes() << 5 | quando.getSeconds() >> 1,
           Math.max(quando.getFullYear() - 1980, 0) << 9 | (quando.getMonth() + 1) << 5 | quando.getDate()]
        : [0, (2020 - 1980) << 9 | 1 << 5 | 1];
    for (const { nome, conteudo } of arquivos) {
        const n = enc.encode(nome);
        const crc = crc32(conteudo);
        const local = [...u32(0x04034b50), ...u16(20), ...u16(0x0800), ...u16(0), ...u16(hora), ...u16(data), ...u32(crc),
            ...u32(conteudo.length), ...u32(conteudo.length), ...u16(n.length), ...u16(0)];
        partes.push(Uint8Array.from(local), n, conteudo);
        central.push(Uint8Array.from([...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0x0800), ...u16(0), ...u16(hora), ...u16(data),
            ...u32(crc), ...u32(conteudo.length), ...u32(conteudo.length), ...u16(n.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0),
            ...u32(0), ...u32(deslocamento)]), n);
        deslocamento += local.length + n.length + conteudo.length;
    }
    const tamanhoCentral = central.reduce((s, p) => s + p.length, 0);
    const fim = Uint8Array.from([...u32(0x06054b50), ...u16(0), ...u16(0), ...u16(arquivos.length), ...u16(arquivos.length),
        ...u32(tamanhoCentral), ...u32(deslocamento), ...u16(0)]);
    const todas = [...partes, ...central, fim];
    const saida = new Uint8Array(todas.reduce((s, p) => s + p.length, 0));
    let i = 0;
    for (const p of todas) { saida.set(p, i); i += p.length; }
    return saida;
}

// ---- Planilha --------------------------------------------------------------------------------------------------------
const xml = (texto) => String(texto).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function letra(coluna) {
    let s = '';
    for (let c = coluna; c > 0; c = Math.floor((c - 1) / 26)) s = String.fromCharCode(65 + ((c - 1) % 26)) + s;
    return s;
}

// str(valor or '') do Python: zero e vazio contam como ''; float inteiro sai com '.0'; Decimal com o texto dado.
function textoPython(valor) {
    if (valor === null || valor === undefined || valor === '' || valor === 0) return '';
    if (typeof valor === 'object' && Number(valor.numero) === 0) return '';
    if (typeof valor === 'object') return valor.texto ?? (valor.decimal ? String(valor.numero) : textoFloat(valor.numero));
    return String(valor);
}

const textoFloat = (n) => (Number.isInteger(n) ? `${n}.0` : String(n));

// Estilos (cellXfs): 0 normal; 1 cabecalho azul centralizado; 2 moeda; 3 normal com quebra de linha e topo;
// 4 cabecalho azul com quebra e topo; 5 moeda com quebra e topo; 6 cabecalho escuro centralizado.
// FIN-REG-03/04 — variantes do _formatar_planilha do Flask, por aba (opcoes.estilo):
//   'padrao'    PatrimonioRelatorioService: cabecalho so na linha 1, moeda pelas colunas `monetarias`.
//   'relatorio' IrRelatorioService e LastroRelatorioService: quebra de linha e topo em toda celula; cabecalho na linha 1 e
//               em toda celula cujo texto esteja em `rotulos`; moeda em toda celula float (objeto { numero }), nunca em
//               inteiro (numero simples); autofiltro so com mais de uma linha e mais de uma coluna.
//   'indice'    DocumentoZipService: cabecalho escuro centralizado na linha 1; moeda nas celulas float.
const VARIANTES = {
    padrao: { normal: null, cabecalho: 1, moeda: 2, moedaPorCelula: false },
    relatorio: { normal: 3, cabecalho: 4, moeda: 5, moedaPorCelula: true },
    indice: { normal: null, cabecalho: 6, moeda: 2, moedaPorCelula: true },
};

function planilha(linhas, monetarias, opcoes = {}) {
    const v = VARIANTES[opcoes.estilo || 'padrao'];
    const rotulos = opcoes.rotulos || null;
    const [larguraMinima, larguraMaxima] = [opcoes.larguraMinima ?? 12, opcoes.larguraMaxima ?? 42];
    const largura = linhas.reduce((m, l) => Math.max(m, l.length), 0);
    const ultimaLinha = linhas.length;
    const larguras = [];
    for (let c = 0; c < largura; c += 1) {
        const maior = Math.max(...linhas.map((l) => textoPython(l[c] ?? null).length));
        larguras.push(Math.min(Math.max(maior + 2, larguraMinima), larguraMaxima));
    }
    const s = (id) => (id === null ? '' : ` s="${id}"`);
    const corpo = [];
    linhas.forEach((linha, i) => {
        const celulas = [];
        const colunas = i === 0 ? Array.from({ length: largura }, (_, c) => linha[c] ?? null) : linha;
        colunas.forEach((valor, c) => {
            const ref = `${letra(c + 1)}${i + 1}`;
            const cabecalho = i === 0 || (rotulos !== null && typeof valor === 'string' && rotulos.has(valor));
            const estilo = s(cabecalho ? v.cabecalho : v.normal);
            if (valor === null || valor === undefined || valor === '') {
                if (i === 0) celulas.push(`<c r="${ref}"${s(v.cabecalho)}/>`);  // openpyxl estiliza toda a linha do cabecalho
                return;
            }
            if (typeof valor === 'object' || typeof valor === 'number') {
                const numero = typeof valor === 'number' ? valor : valor.numero;
                const decimal = typeof valor === 'object' && valor.decimal;
                const emMoeda = v.moedaPorCelula ? typeof valor === 'object' && !decimal
                    : i > 0 && monetarias.has(c + 1) && !decimal;
                celulas.push(`<c r="${ref}" t="n"${emMoeda ? s(v.moeda) : estilo}><v>${numero}</v></c>`);
            } else {
                celulas.push(`<c r="${ref}" t="inlineStr"${estilo}><is><t xml:space="preserve">${xml(valor)}</t></is></c>`);
            }
        });
        if (celulas.length) corpo.push(`<row r="${i + 1}">${celulas.join('')}</row>`);
    });
    const dimensao = `A1:${letra(largura)}${ultimaLinha}`;
    const comFiltro = opcoes.estilo !== 'relatorio' || (ultimaLinha > 1 && largura > 1);
    return enc.encode('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + `<dimension ref="${dimensao}"/>`
        + '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        + `<cols>${larguras.map((w, c) => `<col min="${c + 1}" max="${c + 1}" width="${w}" customWidth="1"/>`).join('')}</cols>`
        + `<sheetData>${corpo.join('')}</sheetData>`
        + (comFiltro ? `<autoFilter ref="${dimensao}"/>` : '')
        + '</worksheet>');
}

const ESTILOS = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    + '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    + '<numFmts count="1"><numFmt numFmtId="164" formatCode="R$ #,##0.00"/></numFmts>'
    + '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="00FFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>'
    + '<fills count="4"><fill><patternFill/></fill><fill><patternFill patternType="gray125"/></fill>'
    + '<fill><patternFill patternType="solid"><fgColor rgb="001D4ED8"/></patternFill></fill>'
    + '<fill><patternFill patternType="solid"><fgColor rgb="001F2937"/></patternFill></fill></fills>'
    + '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    + '<cellXfs count="7"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    + '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center"/></xf>'
    + '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    + '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
    + '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
    + '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
    + '<xf numFmtId="0" fontId="1" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center"/></xf></cellXfs>'
    + '</styleSheet>';

// abas: [{ nome, linhas: [[celula, ...], ...], monetarias: [numero da coluna, ...] }]
// Opcionais por aba: estilo ('padrao' | 'relatorio' | 'indice'), rotulos (Set de textos de cabecalho), larguraMinima, larguraMaxima.
export function gerarXlsx(abas) {
    const arquivos = [
        { nome: '[Content_Types].xml', conteudo: enc.encode('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            + '<Default Extension="xml" ContentType="application/xml"/>'
            + '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + abas.map((a, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('')
            + '</Types>') },
        { nome: '_rels/.rels', conteudo: enc.encode('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            + '</Relationships>') },
        { nome: 'xl/workbook.xml', conteudo: enc.encode('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            + `<sheets>${abas.map((a, i) => `<sheet name="${xml(a.nome)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join('')}</sheets>`
            + '</workbook>') },
        { nome: 'xl/_rels/workbook.xml.rels', conteudo: enc.encode('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + abas.map((a, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join('')
            + `<Relationship Id="rId${abas.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>`
            + '</Relationships>') },
        { nome: 'xl/styles.xml', conteudo: enc.encode(ESTILOS) },
        ...abas.map((a, i) => ({ nome: `xl/worksheets/sheet${i + 1}.xml`, conteudo: planilha(a.linhas, new Set(a.monetarias || []), a) })),
    ];
    return zip(arquivos);
}

// FIN-REG-04: o mesmo empacotador ZIP (armazenado, sem compressao: os bytes dos arquivos ficam como estao).
export { zip as empacotarZip, crc32 };

export const MIME_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
