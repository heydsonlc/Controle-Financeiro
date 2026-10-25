// FIN-FIDELIDADE-CARTOES-2 — gera XLSX FICTICIO para os testes (unitarios e E2E), sem biblioteca: ZIP (deflate do Node)
// com o XML minimo de uma planilha. Celulas: texto (compartilhado ou inline), numero e data (serial com estilo de data).
import { deflateRawSync } from 'node:zlib';

const crcTabela = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
});
const crc32 = (buf) => {
    let c = 0xffffffff;
    for (const b of buf) c = crcTabela[(c ^ b) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
};

function zip(arquivos) {
    const locais = [];
    const centrais = [];
    let deslocamento = 0;
    for (const [nome, conteudo] of Object.entries(arquivos)) {
        const dados = Buffer.from(conteudo, 'utf8');
        const comprimido = deflateRawSync(dados);
        const n = Buffer.from(nome, 'utf8');
        const local = Buffer.alloc(30);
        local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt16LE(8, 8);
        local.writeUInt32LE(crc32(dados), 14); local.writeUInt32LE(comprimido.length, 18); local.writeUInt32LE(dados.length, 22);
        local.writeUInt16LE(n.length, 26);
        const central = Buffer.alloc(46);
        central.writeUInt32LE(0x02014b50, 0); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6); central.writeUInt16LE(8, 10);
        central.writeUInt32LE(crc32(dados), 16); central.writeUInt32LE(comprimido.length, 20); central.writeUInt32LE(dados.length, 24);
        central.writeUInt16LE(n.length, 28); central.writeUInt32LE(deslocamento, 42);
        locais.push(local, n, comprimido);
        centrais.push(central, n);
        deslocamento += 30 + n.length + comprimido.length;
    }
    const diretorio = Buffer.concat(centrais);
    const fim = Buffer.alloc(22);
    fim.writeUInt32LE(0x06054b50, 0); fim.writeUInt16LE(Object.keys(arquivos).length, 8);
    fim.writeUInt16LE(Object.keys(arquivos).length, 10); fim.writeUInt32LE(diretorio.length, 12); fim.writeUInt32LE(deslocamento, 16);
    return Buffer.concat([...locais, diretorio, fim]);
}

const esc = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const letra = (i) => (i < 26 ? String.fromCharCode(65 + i) : letra(Math.floor(i / 26) - 1) + String.fromCharCode(65 + (i % 26)));
// Data ISO -> serial do Excel (base 1900).
const serial = (iso) => (Date.UTC(...iso.split('-').map((x, i) => Number(x) - (i === 1 ? 1 : 0))) - Date.UTC(1899, 11, 30)) / 86400000;

// abas: [{ nome, linhas: [[celula...]] }]; celula: string | number | { data: 'AAAA-MM-DD' } | { inline: 'texto' } | null.
export function gerarXlsx(abas, { ativa = 0 } = {}) {
    const compartilhadas = [];
    const folha = (linhas) => `<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${
        linhas.map((linha, r) => `<row r="${r + 1}">${linha.map((c, i) => {
            const ref = `${letra(i)}${r + 1}`;
            if (c === null || c === undefined) return '';
            if (typeof c === 'number') return `<c r="${ref}"><v>${c}</v></c>`;
            if (c.data) return `<c r="${ref}" s="1"><v>${serial(c.data)}</v></c>`;
            if (c.inline !== undefined) return `<c r="${ref}" t="inlineStr"><is><t>${esc(c.inline)}</t></is></c>`;
            compartilhadas.push(c);
            return `<c r="${ref}" t="s"><v>${compartilhadas.length - 1}</v></c>`;
        }).join('')}</row>`).join('')}</sheetData></worksheet>`;
    const arquivos = {
        '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
    };
    abas.forEach((aba, i) => { arquivos[`xl/worksheets/sheet${i + 1}.xml`] = folha(aba.linhas); });
    arquivos['xl/workbook.xml'] = `<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView activeTab="${ativa}"/></bookViews><sheets>${
        abas.map((a, i) => `<sheet name="${esc(a.nome)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join('')}</sheets></workbook>`;
    arquivos['xl/_rels/workbook.xml.rels'] = `<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${
        abas.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join('')}</Relationships>`;
    arquivos['xl/sharedStrings.xml'] = `<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">${
        compartilhadas.map((t) => `<si><t>${esc(t)}</t></si>`).join('')}</sst>`;
    arquivos['xl/styles.xml'] = '<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="14" applyNumberFormat="1"/></cellXfs></styleSheet>';
    return zip(arquivos);
}
