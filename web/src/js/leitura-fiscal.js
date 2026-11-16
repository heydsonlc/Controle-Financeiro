// FIN-REG-08 — interpretacao fiscal do texto de um documento (lido no navegador: PDF digital ou OCR) e sugestao de
// categoria. Funcoes puras, sem rede nem tela, para o desktop e o celular usarem as mesmas regras.
//
// Os leitores reproduzem os do Flask (comparados em tests/test_leitura_fiscal.py sobre os mesmos textos ficticios):
//   backend/services/ir_nfse_goiania_parser.py   NFS-e de Goiania;
//   backend/services/cupom_fiscal_parser.py      cupom fiscal, NFC-e, CF-e/SAT;
//   IrDocumentoService._extrair_dados_simples    demais documentos;
//   OcrService.normalizar_texto_ocr              limpeza do texto;
//   CategoriaPalavraChaveService                 categoria por palavras-chave.
// Diferencas deliberadas (decisao do titular, 15/11/2026): o resultado e SEMPRE sugestao e cada campo diz se foi
// identificado, se precisa de conferencia ou se nao foi reconhecido; valor ambiguo nao e escolhido (o Flask escolhia o
// maior valor do documento generico e nao conferia o total do cupom com subtotal, desconto e troco); CPF/CNPJ com digito
// verificador invalido pede conferencia. Nada aqui grava ou valida documento.

// ---------------------------------------------------------------------------------------------------------------
// Utilitarios (equivalentes aos do Python)

const semAcento = (texto) => String(texto ?? '').normalize('NFKD').replace(/\p{M}/gu, '');

// _normalizar dos parsers: minusculas, sem acento, espacos colapsados.
export function normalizar(texto) {
    return semAcento(String(texto ?? '').toLowerCase()).replace(/\s+/g, ' ').trim();
}

const linhasDe = (texto) => String(texto ?? '').split(/\r\n|\r|\n/).map((l) => l.trim()).filter(Boolean);

// OcrService.normalizar_texto_ocr
export function normalizarTextoOcr(texto) {
    const linhas = String(texto ?? '').replace(/\x00/g, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
        .map((l) => l.replace(/[ \t]+/g, ' ').trim()).filter(Boolean);
    return linhas.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

// Decimal(str) do Python para texto so de digitos, ponto e virgula: devolve o texto canonico ou null.
function decimal(texto) {
    const t = String(texto ?? '').trim();
    return /^[+-]?(\d+(\.\d*)?|\.\d+)$/.test(t) ? t : null;
}

const numero = (texto) => (texto === null || texto === undefined ? null : Number(texto));
const emCentavos = (valor) => Math.round(Number(valor) * 100);

// '1.234,56' -> '1234.56' (valores do documento)
function valorBr(texto) {
    return decimal(String(texto ?? '').replace(/\./g, '').replace(',', '.'));
}

// dd/mm/aaaa -> aaaa-mm-dd, so data que existe
export function dataIso(texto) {
    const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(String(texto ?? '').trim());
    if (!m) return null;
    const [dia, mes, ano] = [Number(m[1]), Number(m[2]), Number(m[3])];
    const d = new Date(Date.UTC(ano, mes - 1, dia));
    return d.getUTCFullYear() === ano && d.getUTCMonth() === mes - 1 && d.getUTCDate() === dia ? `${m[3]}-${m[2]}-${m[1]}` : null;
}

// Digitos verificadores de CPF e CNPJ (so para pedir conferencia; o valor lido e mantido).
export function documentoValido(texto) {
    const d = String(texto ?? '').replace(/\D/g, '');
    if (d.length === 11) {
        if (/^(\d)\1{10}$/.test(d)) return false;
        const dv = (n) => { let s = 0; for (let i = 0; i < n; i += 1) s += Number(d[i]) * (n + 1 - i); const r = (s * 10) % 11; return r === 10 ? 0 : r; };
        return dv(9) === Number(d[9]) && dv(10) === Number(d[10]);
    }
    if (d.length === 14) {
        if (/^(\d)\1{13}$/.test(d)) return false;
        const dv = (n) => { const pesos = n === 12 ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
            let s = 0; for (let i = 0; i < n; i += 1) s += Number(d[i]) * pesos[i]; const r = s % 11; return r < 2 ? 0 : 11 - r; };
        return dv(12) === Number(d[12]) && dv(13) === Number(d[13]);
    }
    return null;  // nem CPF nem CNPJ
}

// ---------------------------------------------------------------------------------------------------------------
// NFS-e de Goiania (ir_nfse_goiania_parser.py)

export function ehNfseGoiania(texto) {
    const n = normalizar(texto);
    return (n.includes('prefeitura municipal de goiania')
        && (n.includes('nota fiscal de servico eletronica') || n.includes('nfs-e'))
        && n.includes('dados do prestador de servico')) || n.includes('issnetonline.com.br/goiania');
}

function proximoValor(texto, rotulo, padrao) {
    const linhas = linhasDe(texto);
    const rotuloNorm = normalizar(rotulo);
    for (let i = 0; i < linhas.length; i += 1) {
        if (!normalizar(linhas[i]).includes(rotuloNorm)) continue;
        const janela = linhas.slice(i, i + 8);
        for (const candidata of janela) {
            const m = new RegExp(padrao).exec(candidata);
            if (m && !normalizar(candidata).includes(rotuloNorm)) return m[0];
        }
        const m = new RegExp(padrao).exec(janela.join('\n'));
        if (m) return m[0];
    }
    return null;
}

function regexGrupo(texto, padrao) {
    const m = new RegExp(padrao, 'i').exec(String(texto ?? ''));
    return m ? m[1].trim().split(/\s+/).join(' ') : null;
}

function prestadorNfse(texto) {
    const linhas = linhasDe(texto);
    const bloqueios = ['data de geracao', 'data de competencia', 'serie do documento', 'numero da nota fiscal', 'inscricao municipal',
        'cpf/cnpj', 'identificacao da nota', 'natureza da operacao', 'local dos servicos', 'municipio incidencia', 'cod. de autenticidade',
        'responsavel pela retencao', 'prefeitura municipal', 'secretaria municipal'];
    for (let i = 0; i < linhas.length; i += 1) {
        if (!normalizar(linhas[i]).includes('dados do prestador de servico')) continue;
        for (const candidata of linhas.slice(i + 1, i + 16)) {
            const n = normalizar(candidata);
            if (bloqueios.some((b) => n.includes(b))) continue;
            if (/\d{2}\/\d{2}\/\d{4}/.test(candidata)) continue;
            if (/^\d{5,}$|^\d{2}:\d{2}/.test(candidata)) continue;
            if (/(rua|avenida|cep|fone|email|@|goiania\/go)/.test(n)) continue;
            if (/[A-Za-z]/.test(candidata)) return candidata.slice(0, 255);
        }
    }
    return null;
}

function descricaoNfse(texto) {
    const m = /Descri[cç][aã]o dos Servi[cç]os\s*([\s\S]+?)\s*Detalhamento dos Tributos/i.exec(String(texto ?? ''));
    if (!m) return null;
    const d = m[1].split(/\|?\s*Cond\.?Pagto/i)[0].replace(/\|/g, ' ').replace(/\s+/g, ' ').trim();
    return d ? d.slice(0, 500) : null;
}

// _valor_apos_rotulo: a posicao e achada no texto normalizado e aplicada ao original (como no Flask).
function valorAposRotulo(texto, rotulo) {
    const pos = normalizar(texto).indexOf(normalizar(rotulo));
    if (pos < 0) return null;
    const m = /R\$\s*([\d.]+,\d{2})/.exec(String(texto).slice(pos, pos + 500));
    return m ? valorBr(m[1]) : null;
}

function valorNfse(texto) {
    const total = valorAposRotulo(texto, 'Vl. Total dos Servicos');
    if (total !== null) return total;
    const liquido = valorAposRotulo(texto, 'Vl. Liquido da Nota Fiscal');
    if (liquido !== null) return liquido;
    const m = /Cond\.?Pagto[\s\S]*?R\$\s*([\d.]+,\d{2})/i.exec(String(texto ?? ''));
    return m ? valorBr(m[1]) : null;
}

export function dadosNfseGoiania(texto) {
    const t = String(texto ?? '');
    const data = proximoValor(t, 'Data de Competencia', '\\b\\d{2}/\\d{2}/\\d{4}\\b')
        || proximoValor(t, 'Data de Geracao da NFS-e', '\\b\\d{2}/\\d{2}/\\d{4}\\b')
        || proximoValor(t, 'Data de Emissao do RPS', '\\b\\d{2}/\\d{2}/\\d{4}\\b');
    const dados = {
        numero_nota: proximoValor(t, 'Numero da Nota Fiscal', '\\b\\d+\\b'),
        data_documento: data,
        prestador_nome: prestadorNfse(t),
        prestador_cpf_cnpj: regexGrupo(t, 'CPF/CNPJ\\s+(\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2})'),
        tomador_nome: regexGrupo(t, 'Raz[aã]o Social\\s*:\\s*(.+?)(?:\\n|$)'),
        tomador_cpf: regexGrupo(t, 'CNPJ/CPF\\s*:\\s*(\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}|\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2})'),
        descricao_servico: descricaoNfse(t),
        valor: valorNfse(t),
    };
    dados.texto_classificacao = [dados.descricao_servico, dados.prestador_nome, t].filter(Boolean).join(' ').trim();
    return dados;
}

// ---------------------------------------------------------------------------------------------------------------
// Cupom fiscal / NFC-e / CF-e / SAT (cupom_fiscal_parser.py)

const TERMOS_CUPOM = ['cupom fiscal', 'nfc-e', 'nfce', 'nota fiscal de consumidor eletronica', 'nota fiscal de consumidor eletronico',
    'extrato no.', 'extrato no', 'extrato n.', 'extrato nº', 'documento auxiliar da nota fiscal de consumidor eletronica', 'danfe nfc-e',
    'danfe nfce', 'sat', 'cf-e', 'cfe', 'cupom fiscal eletronico'];
const PISTAS_CUPOM = ['chave de acesso', 'qrcode', 'qr code', 'sefaz', 'valor total', 'valor a pagar', 'total r$', 'total da nota', 'valor pago'];
const BLOQUEIOS_ESTABELECIMENTO = /(cupom|fiscal|nfc|nfce|danfe|sat\b|cf-e|cfe|cnpj|cpf|inscri|endere|cep|fone|telefone|email|data|hora|emissao|emitido|total|valor|troco|desconto|subtotal|sefaz|qr\s*code|chave|acesso|serie|numero|documento auxiliar|nota fiscal|consumidor|eletronica|eletronico)/i;

export function ehCupomFiscal(texto) {
    const n = normalizar(texto);
    if (TERMOS_CUPOM.some((t) => n.includes(t))) return true;
    if (PISTAS_CUPOM.filter((t) => n.includes(t)).length >= 2) return true;
    return /\b\d{44}\b/.test(String(texto ?? ''));
}

function tipoCupom(n) {
    if (n.includes('nfc-e') || n.includes('nfce') || n.includes('nota fiscal de consumidor') || n.includes('danfe nfc')) return 'NFCE';
    if (n.includes('cf-e') || n.includes('cfe') || n.includes('cupom fiscal eletronico')) return 'SAT';
    if (n.includes('cupom fiscal')) return 'CUPOM_FISCAL';
    if (n.includes('sat')) return 'SAT';
    return 'CUPOM_FISCAL';
}

function cnpjCupom(texto) {
    const t = String(texto ?? '');
    const formatados = [...t.matchAll(/\b\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}\b/g)];
    if (formatados.length) {
        const minusculo = t.toLowerCase();
        let consumidor = minusculo.indexOf('cpf do consumidor');
        if (consumidor < 0) consumidor = minusculo.indexOf('cpf consumidor');
        if (consumidor < 0) consumidor = minusculo.length;
        const antes = formatados.find((m) => m.index < consumidor);
        return (antes || formatados[0])[0];
    }
    const bruto = /\b(\d{14})\b/.exec(t);
    return bruto ? bruto[1] : null;
}

function normalizarDataCupom(d) {
    if (!d) return null;
    let m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(d);
    if (m) return `${m[3]}/${m[2]}/${m[1]}`;
    m = /^(\d{2})-(\d{2})-(\d{4})$/.exec(d);
    if (m) return `${m[1]}/${m[2]}/${m[3]}`;
    m = /^(\d{2})\/(\d{2})\/(\d{2})$/.exec(d);
    if (m) return `${m[1]}/${m[2]}/20${m[3]}`;
    return d;
}

function dataCupom(texto) {
    const padroes = [/\b(\d{2}\/\d{2}\/\d{4})\b/, /\b(\d{2}-\d{2}-\d{4})\b/, /\b(\d{4}-\d{2}-\d{2})\b/, /\b(\d{2}\/\d{2}\/\d{2})\b/];
    const termos = ['emissao', 'emitido', 'emitida', 'data', 'competencia', 'nfc-e', 'cupom'];
    for (const linha of linhasDe(texto)) {
        const n = normalizar(linha);
        if (!termos.some((t) => n.includes(t))) continue;
        for (const p of padroes) {
            const m = p.exec(linha);
            if (m) return normalizarDataCupom(m[1]);
        }
    }
    for (const p of padroes) {
        const m = p.exec(String(texto ?? ''));
        if (m) return normalizarDataCupom(m[1]);
    }
    return null;
}

function valorCupomBruto(texto) {
    if (!texto) return null;
    let limpo = String(texto).trim().replace(/R\$/g, '').replace(/ /g, '');
    if (limpo.includes(',')) limpo = limpo.replace(/\./g, '').replace(/,/g, '.');
    return decimal(limpo);
}

const ROTULOS_TOTAL = ['valor total', 'total da nota', 'total r$', 'valor a pagar', 'valor pago', 'total'];
const ROTULOS_EVITAR = /(troco|desconto|subtotal|parcela|taxa|tribut|ipi|icms|pis|cofins|frete)/i;

function totalCupom(texto) {
    const linhas = linhasDe(texto);
    const normais = linhas.map(normalizar);
    for (const rotulo of ROTULOS_TOTAL) {
        for (const n of normais) {
            if (!n.includes(rotulo) || ROTULOS_EVITAR.test(n)) continue;
            const i = normais.indexOf(n);  // primeira linha igual (como o Flask)
            const janela = i + 1 < linhas.length ? `${linhas[i]} ${linhas[i + 1]}` : linhas[i];
            const m = /R?\$?\s*([\d.,]+)/.exec(janela);
            if (m) {
                const v = valorCupomBruto(m[1]);
                if (v !== null && Number(v) > 0) return v;
            }
        }
    }
    return null;
}

function chaveAcesso(texto) {
    const t = String(texto ?? '');
    const m = /\b(\d{44})\b/.exec(t);
    if (m) return m[1];
    const g = /(\d{4}[\s-]){10}\d{4}/.exec(t);
    return g ? g[0].replace(/[\s-]/g, '') : null;
}

function numeroCupom(texto) {
    for (const p of [/(?:COO|Cupom)\s*[:-]?\s*(\d+)/i, /(?:N[uú]mero|N[oº]\.?)\s*[:-]?\s*(\d{3,})/i, /(?:NFC-e|NFCE)\s*[:-]?\s*(\d+)/i,
        /(?:Extrato\s*N[oº]\.?)\s*[:-]?\s*(\d+)/i]) {
        const m = p.exec(String(texto ?? ''));
        if (m) return m[1];
    }
    return null;
}

function estabelecimentoCupom(texto) {
    const linhas = linhasDe(texto);
    let posCnpj = linhas.length;
    for (let i = 0; i < linhas.length; i += 1) {
        if (/\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}/.test(linhas[i]) || /\b\d{14}\b/.test(linhas[i])) { posCnpj = i; break; }
    }
    const candidatos = [];
    for (const linha of linhas.slice(0, Math.max(posCnpj, 8))) {
        const n = normalizar(linha);
        if (n.length < 3 || BLOQUEIOS_ESTABELECIMENTO.test(n)) continue;
        if (/^\d+$|^\d{2}\/\d{2}|\d{2}:\d{2}/.test(linha)) continue;
        if (/[A-Za-zÀ-ɏ]/.test(linha)) candidatos.push(linha.slice(0, 255));
        if (candidatos.length >= 2) break;
    }
    return candidatos[0] || null;
}

export function dadosCupomFiscal(texto) {
    const t = String(texto ?? '');
    const n = normalizar(t);
    const estabelecimento = estabelecimentoCupom(t);
    const data = dataCupom(t);
    return {
        tipo_detectado: tipoCupom(n),
        estabelecimento,
        cnpj: cnpjCupom(t),
        data_emissao: data,
        valor_total: totalCupom(t),
        numero_documento: numeroCupom(t),
        chave_acesso: chaveAcesso(t),
        descricao_resumida: `Cupom fiscal — ${estabelecimento || 'Estabelecimento nao identificado'}`,
        texto_classificacao: t,
    };
}

// FIN-REG-08: o total lido confere com o resto do cupom? Subtotal - desconto + acrescimo e dinheiro - troco, quando o
// cupom traz esses valores. Devolve os valores alternativos encontrados (vazio = nada contradiz o total).
const VALOR_BR = /\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}/g;
function ultimoValorDaLinha(texto, rotulo, evitar = null) {
    for (const linha of linhasDe(texto)) {
        const n = normalizar(linha);
        if (!rotulo.test(n) || (evitar && evitar.test(n))) continue;
        const valores = linha.match(VALOR_BR);
        if (valores) return emCentavos(valorBr(valores[valores.length - 1]));
    }
    return null;
}

export function conferenciaDoTotal(texto, total) {
    if (total === null || total === undefined) return [];
    const lido = emCentavos(total);
    const alternativas = [];
    const subtotal = ultimoValorDaLinha(texto, /\bsub ?total\b/);
    const desconto = ultimoValorDaLinha(texto, /\bdesconto/) || 0;
    const acrescimo = ultimoValorDaLinha(texto, /\bacrescimo/) || 0;
    if (subtotal !== null) {
        const esperado = subtotal - desconto + acrescimo;
        if (esperado > 0 && esperado !== lido) alternativas.push(esperado);
    }
    const dinheiro = ultimoValorDaLinha(texto, /\bdinheiro\b/);
    const troco = ultimoValorDaLinha(texto, /\btroco\b/);
    if (dinheiro !== null && troco !== null) {
        const esperado = dinheiro - troco;
        if (esperado > 0 && esperado !== lido) alternativas.push(esperado);
    }
    return [...new Set(alternativas)].map((c) => (c / 100).toFixed(2));
}

// ---------------------------------------------------------------------------------------------------------------
// Demais documentos (IrDocumentoService._extrair_dados_simples e _extrair_prestador)

function prestadorGenerico(texto) {
    const linhas = linhasDe(texto);
    const inicios = ['dados do prestador de serviço', 'dados do prestador de servico', 'prestador de serviços', 'prestador de servicos',
        'prestador dos serviços', 'prestador dos servicos'];
    const bloqueios = /(data|cnpj|cpf|inscri|endere|cep|fone|telefone|email|nota|numero|série|serie|cód|cod|responsavel|identifica|natureza|local|município|municipio)/i;
    const dataOuNumero = /^\d{1,2}\/\d{1,2}\/\d{4}|^\d{2}\/\d{2}\/\d{4}|\d{2}:\d{2}|\d{5,}$/;
    for (let i = 0; i < linhas.length; i += 1) {
        if (!inicios.some((p) => linhas[i].toLowerCase().includes(p))) continue;
        for (const candidata of linhas.slice(i + 1, i + 10)) {
            if (candidata.length < 4 || bloqueios.test(candidata) || dataOuNumero.test(candidata)) continue;
            if (/[A-Za-zÀ-ÿ]/.test(candidata)) return candidata.slice(0, 255);
        }
    }
    return null;
}

export function dadosGenericos(texto) {
    const t = String(texto ?? '');
    const data = /\b(\d{2}\/\d{2}\/\d{4})\b/.exec(t);
    const valores = [...t.matchAll(/(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2})/g)].map((m) => valorBr(m[1])).filter((v) => v !== null);
    const doc = /\b(\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b/.exec(t);
    let prestador = prestadorGenerico(t);
    if (!prestador) {
        for (const linha of t.split(/\r\n|\r|\n/)) {
            const limpa = linha.trim();
            if (!limpa || limpa.length < 4) continue;
            if (/(nota|cpf|cnpj|valor|data|total|recibo|serie|prefeitura|secretaria)/i.test(limpa)) continue;
            prestador = limpa.slice(0, 255);
            break;
        }
    }
    const maior = valores.length ? valores.reduce((a, b) => (Number(b) > Number(a) ? b : a)) : null;
    return { data_documento: data ? data[1] : null, valores, maior_valor: maior, prestador_cpf_cnpj: doc ? doc[1] : null,
             prestador_nome: prestador || null };
}

// ---------------------------------------------------------------------------------------------------------------
// Leitura do documento: modelo, campos e a situacao de cada campo (o que a tela mostra para conferencia)

export const TIPOS = { NFSE_GOIANIA: 'NFS-e de Goiânia', CUPOM_FISCAL: 'Cupom fiscal', GENERICO: 'Documento', SEM_TEXTO: 'Sem texto legível' };
export const SITUACOES = { identificado: 'Informação identificada', conferir: 'Conferir informação', nao_reconhecido: 'Informação não reconhecida' };
const TEXTO_MINIMO = 50;  // o mesmo minimo do banco para guardar o texto

const textoSuficiente = (texto) => String(texto ?? '').replace(/\s+/g, '').length >= TEXTO_MINIMO;

// origem: 'TEXTO_PDF' (texto do proprio PDF) ou 'OCR_IMAGEM' / 'OCR_PDF' (reconhecimento de caracteres).
export function lerDocumento(textoBruto, { origem = 'TEXTO_PDF' } = {}) {
    const texto = origem === 'TEXTO_PDF' ? String(textoBruto ?? '') : normalizarTextoOcr(textoBruto);
    const vazio = { valor: null, situacao: 'nao_reconhecido' };
    const resultado = {
        tipo: 'SEM_TEXTO', origem, texto, avisos: [], valoresCandidatos: [], textoClassificacao: '',
        campos: { data_documento: vazio, prestador_nome: vazio, prestador_cpf_cnpj: vazio, tomador_nome: vazio, tomador_cpf: vazio,
                  valor: vazio, numero_documento: vazio, descricao: vazio, chave_acesso: vazio },
    };
    if (!textoSuficiente(texto)) {
        resultado.avisos.push(origem === 'TEXTO_PDF' ? 'O PDF não tem texto legível suficiente; preencha os dados.'
            : 'O reconhecimento não obteve texto suficiente; preencha os dados.');
        return resultado;
    }
    const ocr = origem !== 'TEXTO_PDF';
    // Lido por OCR: tudo para conferencia. Texto do PDF: modelo conhecido = identificado; generico = conferir.
    const situacaoBase = (modeloConhecido) => (ocr || !modeloConhecido ? 'conferir' : 'identificado');
    const campo = (valor, modeloConhecido) => (valor === null || valor === undefined || valor === ''
        ? vazio : { valor, situacao: situacaoBase(modeloConhecido) });
    let bruto;
    if (ehNfseGoiania(texto)) {
        resultado.tipo = 'NFSE_GOIANIA';
        bruto = dadosNfseGoiania(texto);
        Object.assign(resultado.campos, {
            data_documento: campo(dataIso(bruto.data_documento), true), prestador_nome: campo(bruto.prestador_nome, true),
            prestador_cpf_cnpj: campo(bruto.prestador_cpf_cnpj, true), tomador_nome: campo(bruto.tomador_nome, true),
            tomador_cpf: campo(bruto.tomador_cpf, true), valor: campo(bruto.valor === null ? null : Number(bruto.valor).toFixed(2), true),
            numero_documento: campo(bruto.numero_nota, true), descricao: campo(bruto.descricao_servico, true),
        });
        resultado.textoClassificacao = bruto.texto_classificacao;
    } else if (ehCupomFiscal(texto)) {
        resultado.tipo = 'CUPOM_FISCAL';
        bruto = dadosCupomFiscal(texto);
        Object.assign(resultado.campos, {
            data_documento: campo(dataIso(bruto.data_emissao), true), prestador_nome: campo(bruto.estabelecimento, true),
            prestador_cpf_cnpj: campo(bruto.cnpj, true), numero_documento: campo(bruto.numero_documento, true),
            chave_acesso: campo(bruto.chave_acesso, true), descricao: campo(bruto.descricao_resumida, true),
        });
        const alternativas = conferenciaDoTotal(texto, bruto.valor_total);
        if (bruto.valor_total !== null && alternativas.length) {
            // Total contraditorio: nenhum valor e escolhido; o usuario confere no documento.
            resultado.valoresCandidatos = [Number(bruto.valor_total).toFixed(2), ...alternativas];
            resultado.campos.valor = { valor: null, situacao: 'conferir' };
            resultado.avisos.push('O total lido não confere com subtotal, desconto ou troco do cupom. Confira o valor no documento.');
        } else {
            resultado.campos.valor = campo(bruto.valor_total === null ? null : Number(bruto.valor_total).toFixed(2), true);
        }
        resultado.textoClassificacao = bruto.texto_classificacao;
    } else {
        resultado.tipo = 'GENERICO';
        bruto = dadosGenericos(texto);
        Object.assign(resultado.campos, {
            data_documento: campo(dataIso(bruto.data_documento), false), prestador_nome: campo(bruto.prestador_nome, false),
            prestador_cpf_cnpj: campo(bruto.prestador_cpf_cnpj, false),
        });
        const distintos = [...new Set(bruto.valores.map((v) => Number(v).toFixed(2)))];
        if (distintos.length === 1) {
            resultado.campos.valor = { valor: distintos[0], situacao: 'conferir' };
        } else if (distintos.length > 1) {
            // Varios valores no documento: nenhum e escolhido (o Flask escolhia o maior).
            resultado.valoresCandidatos = distintos.sort((a, b) => Number(b) - Number(a)).slice(0, 5);
            resultado.campos.valor = { valor: null, situacao: 'conferir' };
            resultado.avisos.push('O documento tem mais de um valor. Escolha ou informe o valor correto.');
        }
        resultado.textoClassificacao = texto;
    }
    for (const chave of ['prestador_cpf_cnpj', 'tomador_cpf']) {
        const c = resultado.campos[chave];
        if (c.valor && documentoValido(c.valor) === false) {
            resultado.campos[chave] = { valor: c.valor, situacao: 'conferir' };
            resultado.avisos.push(`${chave === 'tomador_cpf' ? 'CPF/CNPJ do tomador' : 'CPF/CNPJ'} com dígito verificador inválido: confira.`);
        }
    }
    if (ocr) resultado.avisos.push('Texto lido por reconhecimento de caracteres (OCR): confira valor, data e CPF/CNPJ.');
    return resultado;
}

// ---------------------------------------------------------------------------------------------------------------
// Sugestao de categoria (CategoriaPalavraChaveService.classificar_por_palavras_chave + historico do emitente)

// normalizar_descricao_importacao: sem acento, so letras, digitos, _ e espacos.
export function normalizarDescricao(texto) {
    return semAcento(String(texto ?? '').trim().toLowerCase()).replace(/[^\p{L}\p{N}_\s]/gu, ' ').replace(/\s+/g, ' ').trim();
}

// palavras: [{ categoria_id, palavra }] ativas; categorias: Map(id -> nome) das categorias que o perfil pode usar.
export function categoriaPorPalavrasChave(texto, palavras, categorias) {
    const descricao = normalizarDescricao(texto);
    if (!descricao) return { categoria_id: null, origem: 'sem_sugestao', candidatas: [], palavras: [] };
    const tokens = new Set(descricao.split(' '));
    const porCategoria = new Map();
    for (const p of palavras) {
        if (!categorias.has(p.categoria_id)) continue;  // so categorias do perfil
        const palavra = String(p.palavra ?? '').trim();
        if (!palavra) continue;
        const achou = palavra.includes(' ') ? descricao.includes(palavra) : tokens.has(palavra);
        if (achou) porCategoria.set(p.categoria_id, [...(porCategoria.get(p.categoria_id) || []), palavra]);
    }
    if (!porCategoria.size) return { categoria_id: null, origem: 'sem_sugestao', candidatas: [], palavras: [] };
    const candidatas = [...porCategoria].map(([id, ps]) => ({ categoria_id: id, categoria_nome: categorias.get(id), palavras: ps, score: ps.length }))
        .sort((a, b) => b.score - a.score);
    if (candidatas.length === 1 || candidatas[0].score > candidatas[1].score) {
        const c = candidatas[0];
        return { categoria_id: c.categoria_id, categoria_nome: c.categoria_nome, origem: 'palavra_chave', candidatas, palavras: c.palavras };
    }
    return { categoria_id: null, origem: 'ambigua', candidatas, palavras: [...new Set(candidatas.flatMap((c) => c.palavras))].sort() };
}

// Documentos anteriores do mesmo emitente (CPF/CNPJ) no perfil, todos com a mesma categoria: sugestao segura.
export function categoriaPorEmitente(documento, historico) {
    const alvo = String(documento ?? '').replace(/\D/g, '');
    if (alvo.length !== 11 && alvo.length !== 14) return null;
    const usadas = new Set(historico.filter((d) => String(d.prestador_cpf_cnpj ?? '').replace(/\D/g, '') === alvo && d.categoria_id)
        .map((d) => d.categoria_id));
    return usadas.size === 1 ? [...usadas][0] : null;
}

// contexto: { palavras, categorias: [{ id, nome, categoria_ir_id }], historico: [{ prestador_cpf_cnpj, categoria_id }] }
export function sugerirCategoria(leitura, contexto) {
    const categorias = new Map((contexto.categorias || []).map((c) => [c.id, c.nome]));
    const irDe = new Map((contexto.categorias || []).map((c) => [c.id, c.categoria_ir_id ?? null]));
    const vazio = { categoria_id: null, categoria_nome: null, categoria_ir_id: null, fonte: null, aviso: 'Sem sugestão segura de categoria.', candidatas: [] };
    if (!leitura || leitura.tipo === 'SEM_TEXTO') return vazio;
    const porPalavra = categoriaPorPalavrasChave(leitura.textoClassificacao, contexto.palavras || [], categorias);
    if (porPalavra.categoria_id) {
        return { categoria_id: porPalavra.categoria_id, categoria_nome: porPalavra.categoria_nome, categoria_ir_id: irDe.get(porPalavra.categoria_id),
                 fonte: 'palavra_chave', candidatas: porPalavra.candidatas,
                 aviso: `Categoria sugerida por palavra-chave: ${porPalavra.palavras.join(', ')}.` };
    }
    if (porPalavra.origem === 'ambigua') {
        return { ...vazio, candidatas: porPalavra.candidatas,
                 aviso: `Mais de uma categoria possível (${porPalavra.candidatas.slice(0, 3).map((c) => c.categoria_nome).join(', ')}): escolha.` };
    }
    const doc = leitura.campos.prestador_cpf_cnpj.valor;
    const doEmitente = categoriaPorEmitente(doc, contexto.historico || []);
    if (doEmitente && categorias.has(doEmitente)) {
        return { categoria_id: doEmitente, categoria_nome: categorias.get(doEmitente), categoria_ir_id: irDe.get(doEmitente), fonte: 'emitente',
                 candidatas: [], aviso: 'Categoria usada nos documentos anteriores deste emitente.' };
    }
    return vazio;
}

export { numero, textoSuficiente };
