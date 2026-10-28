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

function zip(arquivos) {
    const partes = [];
    const central = [];
    let deslocamento = 0;
    const u16 = (v) => [v & 0xff, (v >>> 8) & 0xff];
    const u32 = (v) => [v & 0xff, (v >>> 8) & 0xff, (v >>> 16) & 0xff, (v >>> 24) & 0xff];
    const [hora, data] = [0, (2020 - 1980) << 9 | 1 << 5 | 1];  // data fixa: o arquivo nao depende do relogio
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

function planilha(linhas, monetarias) {
    const largura = linhas.reduce((m, l) => Math.max(m, l.length), 0);
    const ultimaLinha = linhas.length;
    const larguras = [];
    for (let c = 0; c < largura; c += 1) {
        const maior = Math.max(...linhas.map((l) => textoPython(l[c] ?? null).length));
        larguras.push(Math.min(Math.max(maior + 2, 12), 42));
    }
    const corpo = [];
    linhas.forEach((linha, i) => {
        const celulas = [];
        const colunas = i === 0 ? Array.from({ length: largura }, (_, c) => linha[c] ?? null) : linha;
        colunas.forEach((valor, c) => {
            const ref = `${letra(c + 1)}${i + 1}`;
            const estilo = i === 0 ? ' s="1"' : '';
            if (valor === null || valor === undefined || valor === '') {
                if (i === 0) celulas.push(`<c r="${ref}" s="1"/>`);  // openpyxl estiliza toda a linha do cabecalho
                return;
            }
            if (typeof valor === 'object' || typeof valor === 'number') {
                const numero = typeof valor === 'number' ? valor : valor.numero;
                const decimal = typeof valor === 'object' && valor.decimal;
                const moeda = i > 0 && monetarias.has(c + 1) && !decimal ? ' s="2"' : estilo;
                celulas.push(`<c r="${ref}" t="n"${moeda}><v>${numero}</v></c>`);
            } else {
                celulas.push(`<c r="${ref}" t="inlineStr"${estilo}><is><t>${xml(valor)}</t></is></c>`);
            }
        });
        if (celulas.length) corpo.push(`<row r="${i + 1}">${celulas.join('')}</row>`);
    });
    const dimensao = `A1:${letra(largura)}${ultimaLinha}`;
    return enc.encode('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + `<dimension ref="${dimensao}"/>`
        + '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        + `<cols>${larguras.map((w, c) => `<col min="${c + 1}" max="${c + 1}" width="${w}" customWidth="1"/>`).join('')}</cols>`
        + `<sheetData>${corpo.join('')}</sheetData>`
        + `<autoFilter ref="${dimensao}"/>`
        + '</worksheet>');
}

const ESTILOS = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    + '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    + '<numFmts count="1"><numFmt numFmtId="164" formatCode="R$ #,##0.00"/></numFmts>'
    + '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="00FFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>'
    + '<fills count="3"><fill><patternFill/></fill><fill><patternFill patternType="gray125"/></fill>'
    + '<fill><patternFill patternType="solid"><fgColor rgb="001D4ED8"/></patternFill></fill></fills>'
    + '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    + '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    + '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center"/></xf>'
    + '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
    + '</styleSheet>';

// abas: [{ nome, linhas: [[celula, ...], ...], monetarias: [numero da coluna, ...] }]
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
        ...abas.map((a, i) => ({ nome: `xl/worksheets/sheet${i + 1}.xml`, conteudo: planilha(a.linhas, new Set(a.monetarias || [])) })),
    ];
    return zip(arquivos);
}

export const MIME_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
