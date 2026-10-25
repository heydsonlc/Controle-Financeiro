// FIN-FIDELIDADE-CARTOES-2 — leitura de XLSX no navegador sem biblioteca nova (I1, parte XLSX). O XLSX e um ZIP de XML:
// o ZIP e lido aqui e descompactado pelo proprio navegador (DecompressionStream 'deflate-raw'); o XML da planilha e lido
// por expressoes simples (arquivo gerado por programa). Mesmas regras do Flask (parsers/importacao_xlsx_parser.py com
// openpyxl, data_only): planilha ativa, valores gravados (nao formulas), primeira linha preenchida = cabecalho, linhas
// vazias fora, datas como AAAA-MM-DD. O resultado vai para a mesma conversao do CSV (importacao-csv.js).

const u16 = (v, i) => v.getUint16(i, true);
const u32 = (v, i) => v.getUint32(i, true);

async function inflar(bytes) {
    const fluxo = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
    return new Uint8Array(await new Response(fluxo).arrayBuffer());
}

// Arquivos do ZIP (diretorio central): nome -> funcao que devolve o texto descompactado.
export function lerZip(buffer) {
    const bytes = new Uint8Array(buffer);
    const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let fim = -1;
    for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i -= 1) {
        if (u32(v, i) === 0x06054b50) { fim = i; break; }
    }
    if (fim < 0) throw new Error('Arquivo XLSX inválido.');
    const total = u16(v, fim + 10);
    let p = u32(v, fim + 16);
    const arquivos = new Map();
    const decodificar = new TextDecoder('utf-8');
    for (let n = 0; n < total; n += 1) {
        if (u32(v, p) !== 0x02014b50) throw new Error('Arquivo XLSX inválido.');
        const metodo = u16(v, p + 10);
        const tamanho = u32(v, p + 20);
        const nome = decodificar.decode(bytes.subarray(p + 46, p + 46 + u16(v, p + 28)));
        const local = u32(v, p + 42);
        p += 46 + u16(v, p + 28) + u16(v, p + 30) + u16(v, p + 32);
        arquivos.set(nome, async () => {
            if (u32(v, local) !== 0x04034b50) throw new Error('Arquivo XLSX inválido.');
            const inicio = local + 30 + u16(v, local + 26) + u16(v, local + 28);
            const dados = bytes.subarray(inicio, inicio + tamanho);
            if (metodo === 0) return decodificar.decode(dados);
            if (metodo === 8) return decodificar.decode(await inflar(dados));
            throw new Error('Compressão do XLSX não suportada.');
        });
    }
    return arquivos;
}

const ENTIDADES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" };
const texto = (xml) => xml.replace(/&(amp|lt|gt|quot|apos|#\d+|#x[0-9a-f]+);/gi, (_, e) => (e[0] === '#'
    ? String.fromCodePoint(e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : Number(e.slice(1))) : ENTIDADES[e]));
const atributo = (tag, nome) => (new RegExp(`\\s${nome}="([^"]*)"`).exec(tag) || [])[1];
// Texto de <si> / <is>: concatena os <t> (ignora a pronuncia <rPh>).
const textoRico = (xml) => [...xml.replace(/<rPh\b[\s\S]*?<\/rPh>/g, '').matchAll(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g)]
    .map((m) => texto(m[1])).join('');

const FORMATOS_DATA = new Set([14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47]);

function estilosDeData(xml) {
    if (!xml) return [];
    const proprios = new Map([...xml.matchAll(/<numFmt\b[^>]*>/g)].map((m) => [Number(atributo(m[0], 'numFmtId')),
        texto(atributo(m[0], 'formatCode') || '')]));
    const xfs = /<cellXfs\b[^>]*>([\s\S]*?)<\/cellXfs>/.exec(xml);
    if (!xfs) return [];
    return [...xfs[1].matchAll(/<xf\b[^>]*>/g)].map((m) => {
        const id = Number(atributo(m[0], 'numFmtId') || 0);
        // Formato proprio com dia/mes/ano (sem o que esta entre aspas ou colchetes, como cores e textos).
        return FORMATOS_DATA.has(id) || /[dmy]/i.test((proprios.get(id) || '').replace(/"[^"]*"|\[[^\]]*\]/g, ''));
    });
}

function dataDoSerial(serial, base1904) {
    const dias = Math.floor(serial) + (base1904 ? 1462 : 0);
    const data = new Date(Date.UTC(1899, 11, 30) + dias * 86400000);
    return data.toISOString().slice(0, 10);
}

function coluna(referencia) {
    let n = 0;
    for (const c of /^[A-Z]+/.exec(referencia)[0]) n = n * 26 + c.charCodeAt(0) - 64;
    return n - 1;
}

// Linhas da planilha ativa (texto de cada celula, como o _valor_para_texto do Flask).
export async function lerPlanilha(buffer) {
    const zip = lerZip(buffer);
    const ler = async (nome) => (zip.has(nome) ? zip.get(nome)() : null);
    const livro = await ler('xl/workbook.xml');
    if (!livro) throw new Error('Arquivo XLSX inválido.');
    const abas = [...livro.matchAll(/<sheet\b[^>]*>/g)].map((m) => atributo(m[0], 'r:id'));
    const ativa = Number(atributo((/<workbookView\b[^>]*>/.exec(livro) || [''])[0], 'activeTab') || 0);
    const base1904 = /<workbookPr\b[^>]*date1904="(1|true)"/.test(livro);
    const rels = (await ler('xl/_rels/workbook.xml.rels')) || '';
    const relacao = [...rels.matchAll(/<Relationship\b[^>]*>/g)].find((m) => atributo(m[0], 'Id') === abas[ativa]);
    if (!relacao) throw new Error('Arquivo XLSX inválido.');
    const alvo = atributo(relacao[0], 'Target').replace(/^\/?(xl\/)?/, '');
    const folha = await ler(`xl/${alvo}`);
    if (!folha) throw new Error('Arquivo XLSX inválido.');
    const compartilhadas = [...((await ler('xl/sharedStrings.xml')) || '').matchAll(/<si>([\s\S]*?)<\/si>/g)].map((m) => textoRico(m[1]));
    const datas = estilosDeData(await ler('xl/styles.xml'));

    const linhas = [];
    for (const [, corpo] of folha.matchAll(/<row\b[^>]*>([\s\S]*?)<\/row>/g)) {
        const valores = [];
        for (const m of corpo.matchAll(/<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
            const tag = m[1];
            const interno = m[2] || '';
            const ref = atributo(` ${tag}`, 'r');
            const tipo = atributo(` ${tag}`, 't');
            const bruto = (/<v>([\s\S]*?)<\/v>/.exec(interno) || [])[1];
            let valor = '';
            if (tipo === 's') valor = compartilhadas[Number(bruto)] ?? '';
            else if (tipo === 'inlineStr') valor = textoRico(interno);
            else if (tipo === 'b') valor = bruto === '1' ? 'True' : 'False';
            else if (tipo === 'str' || tipo === 'e') valor = bruto === undefined ? '' : texto(bruto);
            else if (bruto !== undefined) {
                const numero = Number(bruto);
                valor = datas[Number(atributo(` ${tag}`, 's') || 0)] ? dataDoSerial(numero, base1904) : String(numero);
            }
            valores[ref ? coluna(ref) : valores.length] = String(valor).trim();
        }
        const linha = Array.from(valores, (x) => x ?? '');
        if (linha.some((x) => x)) linhas.push(linha);
    }
    if (!linhas.length) throw new Error('XLSX vazio ou sem dados reconheciveis.');
    const dados = linhas.slice(1).filter((l) => l.some((c) => String(c).trim()));
    if (!dados.length) throw new Error('XLSX sem linhas de lancamentos.');
    return { colunas: linhas[0], linhas_dados: dados, linhas_amostra: dados.slice(0, 5), total_linhas: dados.length };
}
