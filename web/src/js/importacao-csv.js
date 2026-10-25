// FIN-FIDELIDADE-CARTOES-1 — leitura do CSV da fatura no navegador (o arquivo nunca sai do aparelho). Mesmas regras do
// Flask (ImportacaoCartaoService.ler_csv / detectar_perfil_csv / normalizar_descricao e parsers/importacao_csv_parser):
// delimitador ; , ou tab; perfis Nubank (date/title/amount) e Caixa (data/descritivo/credito/debito); outro cabecalho
// pede o mapeamento manual. Diferenca assumida: no perfil de coluna unica de valor, valor negativo (pagamento ou
// estorno) e credito, e nao despesa (o Flask importava o valor absoluto como despesa).
// Funcoes puras (sem acesso a dados), testadas em tests/unit/importacao-csv.test.mjs.

export const PERFIL_NUBANK = 'nubank_csv_simples';
export const PERFIL_CAIXA = 'caixa_credito_debito';
export const PERFIL_MANUAL = 'manual_generico';
export const MAX_PARCELAS = 60;

// Bytes -> texto: UTF-8 (com ou sem BOM); se nao for UTF-8 valido, Windows-1252 (arquivos de banco brasileiros).
export function decodificar(bytes) {
    try {
        return new TextDecoder('utf-8', { fatal: true }).decode(bytes).replace(/^﻿/, '');
    } catch (_erro) {
        return new TextDecoder('windows-1252').decode(bytes);
    }
}

// Separa uma linha respeitando aspas ("" dentro de aspas e uma aspa).
function separarLinha(linha, delimitador) {
    const campos = [];
    let atual = '';
    let aspas = false;
    for (let i = 0; i < linha.length; i += 1) {
        const c = linha[i];
        if (aspas) {
            if (c === '"' && linha[i + 1] === '"') { atual += '"'; i += 1; } else if (c === '"') aspas = false;
            else atual += c;
        } else if (c === '"') aspas = true;
        else if (c === delimitador) { campos.push(atual); atual = ''; } else atual += c;
    }
    campos.push(atual);
    return campos;
}

function linhasDoTexto(texto) {
    // Quebras de linha dentro de aspas fazem parte do campo.
    const linhas = [];
    let atual = '';
    let aspas = false;
    for (const c of texto.replace(/\r\n?/g, '\n')) {
        if (c === '"') aspas = !aspas;
        if (c === '\n' && !aspas) { linhas.push(atual); atual = ''; } else atual += c;
    }
    if (atual) linhas.push(atual);
    return linhas;
}

// Como csv.Sniffer(delimiters=';,\t') nas 5 primeiras linhas: o delimitador presente com a mesma contagem em todas.
export function detectarDelimitador(texto) {
    const amostra = linhasDoTexto(texto).filter((l) => l.trim()).slice(0, 5);
    let melhor = null;
    for (const d of [';', ',', '\t']) {
        const contagens = amostra.map((l) => separarLinha(l, d).length - 1);
        if (contagens.length && contagens[0] > 0 && contagens.every((n) => n === contagens[0])) {
            if (!melhor || contagens[0] > melhor.n) melhor = { d, n: contagens[0] };
        }
    }
    return melhor ? melhor.d : ';';
}

export function lerCsv(texto) {
    const delimitador = detectarDelimitador(texto);
    const linhas = linhasDoTexto(texto).map((l) => separarLinha(l, delimitador));
    if (!linhas.length || !linhas[0].some((c) => c.trim())) throw new Error('CSV vazio');
    const colunas = linhas[0];
    const dados = linhas.slice(1).filter((l) => l.some((c) => String(c).trim()));
    return { delimitador, colunas, linhas_dados: dados, linhas_amostra: dados.slice(0, 5), total_linhas: dados.length };
}

const semAcento = (texto) => String(texto || '').normalize('NFKD').replace(/[̀-ͯ]/g, '');
const normalizarColuna = (c) => semAcento(String(c || '').replace(/﻿/g, '').trim().toLowerCase()).replace(/\s+/g, ' ').trim();

export function detectarPerfilCsv(colunas) {
    const norm = (colunas || []).map(normalizarColuna);
    const idx = (nomes) => { for (const n of nomes) { const i = norm.indexOf(n); if (i >= 0) return i; } return null; };
    const nubank = { data_compra: idx(['date']), descricao: idx(['title']), valor: idx(['amount']), parcela: null, credito: null, debito: null };
    if ([nubank.data_compra, nubank.descricao, nubank.valor].every((v) => v !== null)) {
        return { perfil: PERFIL_NUBANK, confianca: 'alta', mapeamento_sugerido: nubank };
    }
    const caixa = { data_compra: idx(['data']), descricao: idx(['descritivo']), valor: null, parcela: null,
        credito: idx(['credito']), debito: idx(['debito']) };
    if ([caixa.data_compra, caixa.descricao, caixa.credito, caixa.debito].every((v) => v !== null)) {
        return { perfil: PERFIL_CAIXA, confianca: 'alta', mapeamento_sugerido: caixa };
    }
    return { perfil: PERFIL_MANUAL, confianca: 'baixa',
        mapeamento_sugerido: { data_compra: null, descricao: null, valor: null, parcela: null, credito: null, debito: null } };
}

const PADROES_PARCELA = [
    /\b(?:PARC(?:ELA)?\.?)\s*(\d{1,2})\s*(?:\/|DE)\s*(\d{1,2})\b/i,
    /\b(\d{1,2})\s*\/\s*(\d{1,2})\b/,
    /\b(\d{1,2})\s+DE\s+(\d{1,2})\b/i,
];

export function detectarParcelamentoTexto(descricao) {
    const texto = String(descricao || '').trim();
    if (!texto) return null;
    for (const padrao of PADROES_PARCELA) {
        const m = padrao.exec(texto);
        if (!m) continue;
        const atual = Number(m[1]);
        const total = Number(m[2]);
        if (atual < 1 || total <= 1 || atual > total || total > MAX_PARCELAS) return null;
        const limpa = `${texto.slice(0, m.index)} ${texto.slice(m.index + m[0].length)}`.trim()
            .replace(/\s+/g, ' ').replace(/^[\s\-–|]+|[\s\-–|]+$/g, '');
        return { parcela_atual: atual, total_parcelas: total, descricao_limpa: limpa || texto };
    }
    return null;
}

export function normalizarDescricao(descricao) {
    const texto = String(descricao || '').trim();
    const p = detectarParcelamentoTexto(texto);
    return p ? [p.descricao_limpa, p.parcela_atual, p.total_parcelas] : [texto, 1, 1];
}

// Texto para as palavras-chave (CategoriaPalavraChaveService.normalizar_descricao_importacao).
export function normalizarClassificacao(descricao) {
    return semAcento(String(descricao || '').trim().toLowerCase()).replace(/[^\p{L}\p{N}_\s]/gu, ' ').replace(/\s+/g, ' ').trim();
}

// Valor monetario -> texto com 2 casas (com sinal) ou null.
export function lerValor(valor) {
    let texto = String(valor ?? '').trim().replace(/[DC]$/i, '').replace(/R\$/g, '').replace(/\s/g, '');
    if (!texto || texto === '-') return null;
    if (texto.includes(',') && texto.includes('.')) texto = texto.replace(/\./g, '').replace(',', '.');
    else if (texto.includes(',')) texto = texto.replace(',', '.');
    if (!/^[-+]?\d+(\.\d+)?$/.test(texto)) return null;
    return (Math.round(Number(texto) * 100) / 100).toFixed(2);
}

// Data -> AAAA-MM-DD (dia e mes conferidos) ou null. Nunca deixa a interpretacao (dia/mes) para o banco.
export function lerData(valor) {
    const texto = String(valor ?? '').trim();
    let a; let m; let d;
    let r = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(texto);
    if (r) [, a, m, d] = r;
    else if ((r = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$/.exec(texto))) {
        [, d, m, a] = r;
        if (a.length === 2) a = `20${a}`;
    } else return null;
    const data = new Date(Date.UTC(Number(a), Number(m) - 1, Number(d)));
    if (data.getUTCFullYear() !== Number(a) || data.getUTCMonth() !== Number(m) - 1 || data.getUTCDate() !== Number(d)) return null;
    return data.toISOString().slice(0, 10);
}

// Linha intermediaria (formato do parser do Flask), pronta para a analise no banco.
export function montarLinha(idx, data, descricao, valor, tipo, parcelaCampo = null, origem = 'csv') {
    const bruta = String(descricao || '').trim();
    let [normalizada, parcela, total] = normalizarDescricao(bruta);
    if (parcelaCampo) {
        const p = detectarParcelamentoTexto(String(parcelaCampo));
        if (p) { parcela = p.parcela_atual; total = p.total_parcelas; }
    }
    return {
        linha_id: `${origem}-${idx}`, linha_origem: idx, status: tipo === 'credito' ? 'ignorado' : 'revisar',
        data_compra: lerData(data), descricao_original: bruta, descricao_normalizada: normalizada || bruta,
        descricao_exibida: normalizada || bruta, descricao_classificacao: normalizarClassificacao(normalizada || bruta),
        parcela_atual: parcela, total_parcelas: total, parcela: `${parcela}/${total}`,
        valor: String(valor).replace(/^-/, ''), tipo_movimento: tipo, origem_importacao: origem,
        ignorar: tipo === 'credito', gerar_parcelas_futuras: false,
    };
}

// Tabela lida -> linhas (perfis conhecidos) ou pedido de mapeamento manual (converter_tabela_para_payload).
export function converterTabela(tabela, origem = 'csv') {
    const info = detectarPerfilCsv(tabela.colunas);
    const mapa = info.mapeamento_sugerido;
    const base = { ...tabela, perfil_detectado: info.perfil, autodeteccao_confianca: info.confianca,
        mapeamento_sugerido: mapa, requer_mapeamento: info.perfil === PERFIL_MANUAL, linhas: [] };
    if (base.requer_mapeamento) return base;
    const celula = (linha, i) => (i === null || i === undefined ? null : linha[i] ?? null);
    tabela.linhas_dados.forEach((linha, i) => {
        const data = celula(linha, mapa.data_compra);
        const descricao = celula(linha, mapa.descricao);
        let valor;
        let tipo;
        if (info.perfil === PERFIL_CAIXA) {
            const debito = lerValor(celula(linha, mapa.debito));
            const credito = lerValor(celula(linha, mapa.credito));
            if (debito !== null && Number(debito) !== 0) { valor = debito; tipo = 'debito'; } else if (credito !== null && Number(credito) !== 0) {
                valor = credito; tipo = 'credito';
            } else return;
        } else {
            valor = lerValor(celula(linha, mapa.valor));
            if (valor === null || Number(valor) === 0) return;
            tipo = Number(valor) < 0 ? 'credito' : 'debito';
        }
        if (!String(data || '').trim() || !String(descricao || '').trim()) return;
        base.linhas.push(montarLinha(i + 1, data, descricao, valor, tipo, celula(linha, mapa.parcela), origem));
    });
    base.total_linhas = base.linhas.length;
    return base;
}
