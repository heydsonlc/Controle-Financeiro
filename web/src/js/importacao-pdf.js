// FIN-FIDELIDADE-CARTOES-2 — PDF da fatura Caixa lido no navegador (I1). Mesmas regras do Flask
// (parsers/importacao_pdf_caixa_parser.py com pdfplumber): o texto de cada pagina e montado pela posicao dos trechos
// (tolerancias x = 1 e y = 3, como extract_text), e as linhas do "Demonstrativo" viram lancamentos (grupos, cartao,
// compras internacionais com cotacao, creditos "C", parcelas, anuidade sem data). PDF sem texto (escaneado) fica fora,
// como no Flask: nao ha OCR. O PDF.js entra so para extrair o texto: sem desenhar paginas, sem eval, sem fonte externa.
// parseTextoCaixa e linhasDaPagina sao puras (tests/unit/importacao-pdf.test.mjs).

const GRUPOS = new Set(['ANUIDADE', 'COMPRAS', 'COMPRAS PARCELADAS', 'COMPRAS INTERNACIONAIS']);
const DINHEIRO = '(\\d{1,3}(?:\\.\\d{3})*,\\d{2})';
const reDinheiroDC = new RegExp(`${DINHEIRO}\\s*([DC])\\b`, 'gi');
const reData = /(?<!\d)(\d{2}\/\d{2})(?!\d)/;

const limpar = (linha) => String(linha || '').replace(/\s+/g, ' ').trim();
const valor = (texto) => {
    const n = Number(String(texto || '').replace(/\./g, '').replace(',', '.'));
    return Number.isFinite(n) ? n : null;
};
const iso = (a, m, d) => `${a}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

function dataComAno(curta, competencia) {
    const [dia, mes] = curta.split('/').map(Number);
    const ano = mes > competencia.mes ? competencia.ano - 1 : competencia.ano;
    const d = new Date(Date.UTC(ano, mes - 1, dia));
    if (d.getUTCMonth() !== mes - 1 || d.getUTCDate() !== dia) return null;
    return iso(ano, mes, dia);
}

function lerCompetencia(texto) {
    let m = /^(\d{4})-(\d{2})(?:-\d{2})?$/.exec(String(texto || ''));
    if (m) return { ano: Number(m[1]), mes: Number(m[2]) };
    m = /^(\d{2})\/(\d{4})$/.exec(String(texto || ''));
    if (m) return { ano: Number(m[2]), mes: Number(m[1]) };
    throw new Error('competencia invalida para parser PDF.');
}

function metadados(textoTotal) {
    const fatura = { emissor: 'Caixa', vencimento: null, valor_total: null, cartoes_detectados: [], totais_por_cartao: {},
        totais_por_grupo: {}, boleto: null, titular: null };
    const venc = /VENCIMENTO\s+(\d{2})\/(\d{2})\/(\d{4})/i.exec(textoTotal);
    if (venc) fatura.vencimento = iso(venc[3], venc[2], venc[1]);
    const total = new RegExp(`VALOR TOTAL DESTA FATURA[\\s\\S]{0,160}?R\\$\\s*${DINHEIRO}`, 'i').exec(textoTotal)
        || new RegExp(`Valor total desta fatura\\s+R\\$\\s*${DINHEIRO}`, 'i').exec(textoTotal);
    if (total) fatura.valor_total = valor(total[1]);
    const boleto = /(104\d{2}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d+)/.exec(textoTotal);
    if (boleto) fatura.boleto = boleto[1];
    fatura.cartoes_detectados = [...new Set([...textoTotal.matchAll(/Cart[aã]o\s+(\d{4})/gi)].map((m) => m[1]))].sort();
    return fatura;
}

function detectarGrupo(linha) {
    const t = linha.toUpperCase();
    if (t.includes('TOTAL COMPRAS')) return null;
    if (t.includes('COMPRAS INTERNACIONAIS')) return 'COMPRAS INTERNACIONAIS';
    if (t.includes('COMPRAS PARCELADAS')) return 'COMPRAS PARCELADAS';
    if (/(^|\s)COMPRAS(\s|\(|$)/.test(t)) return 'COMPRAS';
    if (/\bANUIDADE\b/.test(t)) return 'ANUIDADE';
    return null;
}

function parcelaDaDescricao(descricao) {
    for (const padrao of [/(\d{1,2})\s+DE\s+(\d{1,2})/i, /(\d{1,2})\s*\/\s*(\d{1,2})/]) {
        const m = padrao.exec(descricao);
        if (m) {
            const atual = Number(m[1]);
            const total = Number(m[2]);
            if (atual >= 1 && atual <= total) {
                return [(descricao.slice(0, m.index) + descricao.slice(m.index + m[0].length)).trim().replace(/\s+/g, ' '), atual, total];
            }
        }
    }
    return [descricao, 1, 1];
}

function anexarCotacao(linha, lancamento) {
    if (!lancamento || lancamento.grupo !== 'COMPRAS INTERNACIONAIS') return false;
    if (new RegExp(`${DINHEIRO}\\s*[DC]\\b`, 'i').test(linha)) return false;
    const m = /(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d+,\d{4})$/.exec(linha);
    if (!m) return false;
    lancamento.metadados.valor_original_brl = valor(m[1]);
    lancamento.metadados.cotacao = Number(m[2].replace(',', '.'));
    return true;
}

function base(id, numero, dados) {
    return { linha_id: id, linha_origem: numero, cartao_final: null, categoria_detectada: null, categoria_despesa_id: null,
        categoria_cartao_id: null, confianca_categoria: 'baixa', duplicidade: null, origem_importacao: 'pdf',
        gerar_parcelas_futuras: false, ...dados };
}

function lancamentoDaLinha(linha, cartao, grupo, competencia, pagina, numero) {
    if (!cartao || !GRUPOS.has(grupo)) return null;
    const t = linha.toUpperCase();
    if (t.includes('TOTAL ') || t.includes('VALOR TOTAL DESTA FATURA')) return null;
    if (t.startsWith('DATA ') || t.startsWith('CRÉDITO/DÉBITO') || t.startsWith('CREDITO/DEBITO')) return null;
    const valores = [...linha.matchAll(reDinheiroDC)];
    if (!valores.length) return null;
    const ultimo = valores[valores.length - 1];
    const v = valor(ultimo[1]);
    if (v === null) return null;
    const sufixo = ultimo[2].toUpperCase();
    const data = reData.exec(linha);
    const mensagens = [];
    let dataCompra;
    let inicio;
    if (data) {
        dataCompra = dataComAno(data[1], competencia);
        inicio = data.index + data[0].length;
    } else if (grupo === 'ANUIDADE') {
        dataCompra = iso(competencia.ano, competencia.mes, 1);
        inicio = 0;
        mensagens.push('Data nao informada na anuidade; usada a competencia da fatura.');
    } else return null;
    let descricao = linha.slice(inicio, ultimo.index).trim()
        .replace(/^(Programa de Pontos|Pontos Fatura|Pontos a Expirar|Saldo Anterior)\s+\d+\s+/i, '').replace(/\s+/g, ' ').trim();
    const meta = { pagina, linha_pdf: numero, linha_texto: linha };
    if (grupo === 'COMPRAS INTERNACIONAIS') {
        const moeda = new RegExp(`\\s${DINHEIRO}$`).exec(descricao);
        if (moeda) {
            meta.moeda_original = 'USD';
            meta.valor_moeda_original = valor(moeda[1]);
            descricao = descricao.slice(0, moeda.index).trim();
        }
    }
    const [semParcela, atual, total] = parcelaDaDescricao(descricao);
    const tipo = sufixo === 'C' ? 'credito' : 'debito';
    const ignorado = tipo === 'credito' || v === 0;
    if (tipo === 'credito') mensagens.push('Credito identificado; nao sera importado como despesa por padrao.');
    if (v === 0) mensagens.push('Lancamento com valor zero ignorado por padrao.');
    return base(`pdf-${pagina}-${numero}`, numero, {
        status: ignorado ? 'ignorado' : 'revisar', data_compra: dataCompra, descricao_original: descricao,
        descricao_normalizada: semParcela || descricao, descricao_exibida: semParcela || descricao, cartao_final: cartao, grupo,
        parcela_atual: atual, total_parcelas: total, parcela: `${atual}/${total}`, valor: Math.abs(v), tipo_movimento: tipo,
        mensagens, metadados: meta, ignorar: ignorado,
    });
}

function creditoAntesDoCartao(linha, competencia, pagina, numero) {
    const t = linha.toUpperCase();
    if (t.includes('TOTAL DA FATURA ANTERIOR') || t.includes('OBRIGADO PELO PAGAMENTO')) return null;
    const v = new RegExp(`${DINHEIRO}\\s*C\\b`, 'i').exec(linha);
    const data = reData.exec(linha);
    if (!v || !data || valor(v[1]) === null) return null;
    const descricao = linha.slice(data.index + data[0].length, v.index).trim().replace(/\s+/g, ' ');
    return base(`pdf-${pagina}-${numero}`, numero, {
        status: 'ignorado', data_compra: dataComAno(data[1], competencia), descricao_original: descricao, descricao_normalizada: descricao,
        descricao_exibida: descricao, grupo: 'CREDITOS', parcela_atual: 1, total_parcelas: 1, parcela: '1/1', valor: Math.abs(valor(v[1])),
        tipo_movimento: 'credito', mensagens: ['Credito identificado; nao sera importado como despesa por padrao.'],
        metadados: { pagina, linha_pdf: numero, linha_texto: linha }, ignorar: true,
    });
}

// parse_texto_caixa do Flask: paginasTexto = texto de cada pagina (linhas separadas por \n).
export function parseTextoCaixa(paginasTexto, competenciaTexto) {
    const competencia = lerCompetencia(competenciaTexto);
    const fatura = metadados((paginasTexto || []).join('\n'));
    const linhas = [];
    let ultimoInternacional = null;
    (paginasTexto || []).forEach((texto, i) => {
        const pagina = i + 1;
        if (!texto.includes('Demonstrativo')) return;
        let cartao = null;
        let grupo = null;
        texto.split(/\r?\n/).forEach((bruta, j) => {
            const numero = j + 1;
            const linha = limpar(bruta);
            if (!linha || anexarCotacao(linha, ultimoInternacional)) return;
            const c = /\(Cart[aã]o\s+(\d{4})\)/i.exec(linha);
            if (c) {
                cartao = c[1];
                if (!fatura.cartoes_detectados.includes(cartao)) fatura.cartoes_detectados.push(cartao);
            }
            const totalCartao = new RegExp(`Total final\\s+\\(cart[aã]o\\s+(\\d{4})\\)\\s+${DINHEIRO}\\s*([DC])`, 'i').exec(linha);
            if (totalCartao) {
                fatura.totais_por_cartao[totalCartao[1]] = { valor: valor(totalCartao[2]), tipo: totalCartao[3].toUpperCase() === 'C' ? 'credito' : 'debito' };
                return;
            }
            const totalGrupo = new RegExp(`Total\\s+(COMPRAS INTERNACIONAIS|COMPRAS PARCELADAS|COMPRAS)\\s+${DINHEIRO}\\s*([DC])`, 'i').exec(linha);
            if (totalGrupo && cartao) {
                fatura.totais_por_grupo[`${cartao}:${totalGrupo[1].toUpperCase()}`] = { valor: valor(totalGrupo[2]),
                    tipo: totalGrupo[3].toUpperCase() === 'C' ? 'credito' : 'debito' };
                return;
            }
            const totalFatura = new RegExp(`Valor total desta fatura\\s+R\\$\\s*${DINHEIRO}\\s*([DC])`, 'i').exec(linha);
            if (totalFatura) {
                fatura.valor_total = valor(totalFatura[1]);
                return;
            }
            if (!cartao) {
                const credito = creditoAntesDoCartao(linha, competencia, pagina, numero);
                if (credito) linhas.push(credito);
                return;
            }
            const detectado = detectarGrupo(linha);
            if (detectado) {
                grupo = detectado;
                if (!new RegExp(`${DINHEIRO}\\s*[DC]\\b`, 'i').test(linha)) return;
            }
            const lancamento = lancamentoDaLinha(linha, cartao, grupo, competencia, pagina, numero);
            if (lancamento) {
                linhas.push(lancamento);
                ultimoInternacional = lancamento.grupo === 'COMPRAS INTERNACIONAIS' ? lancamento : null;
            }
        });
    });
    fatura.cartoes_detectados = [...new Set(fatura.cartoes_detectados)].sort();
    return { origem: 'pdf', perfil_detectado: 'caixa_pdf', requer_mapeamento: false, fatura, linhas, total_linhas: linhas.length };
}

// Texto de uma pagina a partir dos trechos do PDF.js ({str, transform, width}), como extract_text(x_tolerance=1,
// y_tolerance=3): linhas de cima para baixo (mesma altura dentro de 3), trechos da esquerda para a direita, com espaco
// quando a distancia entre eles passa de 1.
export function linhasDaPagina(itens) {
    const trechos = itens.filter((i) => i && typeof i.str === 'string' && i.str !== '' && Array.isArray(i.transform))
        .map((i) => ({ texto: i.str, x: i.transform[4], y: i.transform[5], fim: i.transform[4] + (i.width || 0) }))
        .sort((a, b) => b.y - a.y || a.x - b.x);
    const linhas = [];
    for (const t of trechos) {
        const linha = linhas.find((l) => Math.abs(l.y - t.y) <= 3);
        if (linha) linha.trechos.push(t);
        else linhas.push({ y: t.y, trechos: [t] });
    }
    return linhas.sort((a, b) => b.y - a.y).map((l) => {
        const ordem = l.trechos.sort((a, b) => a.x - b.x);
        return ordem.reduce((texto, t, i) => {
            if (i === 0) return t.texto;
            const espaco = t.x - ordem[i - 1].fim > 1 && !texto.endsWith(' ') && !t.texto.startsWith(' ');
            return texto + (espaco ? ' ' : '') + t.texto;
        }, '');
    }).join('\n');
}

// Texto de cada pagina (pdfjs = modulo do PDF.js ja carregado). Erro claro para arquivo invalido ou sem texto.
export async function textoDoPdf(buffer, pdfjs) {
    const tarefa = pdfjs.getDocument({ data: new Uint8Array(buffer), isEvalSupported: false, disableFontFace: true,
        useSystemFonts: false, enableXfa: false, verbosity: 0 });
    let documento;
    try {
        documento = await tarefa.promise;
    } catch (_erro) {
        await tarefa.destroy();
        throw new Error('Arquivo PDF inválido ou protegido.');
    }
    try {
        const paginas = [];
        for (let n = 1; n <= documento.numPages; n += 1) {
            const pagina = await documento.getPage(n);
            paginas.push(linhasDaPagina((await pagina.getTextContent()).items));
        }
        if (!paginas.some((p) => p.trim())) {
            throw new Error('PDF sem texto extraivel. OCR e PDF escaneado estao fora do escopo deste MVP.');
        }
        return paginas;
    } finally {
        await tarefa.destroy();
    }
}
