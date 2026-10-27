// FIN-PATRIMONIO-2 — sugestao de bem a partir de documento fiscal: a heuristica de
// backend/services/patrimonio_sugestao_service.py (gerar_sugestao), sobre os dados que o banco devolve
// (patrimonio_documento_sugestao_tela). Mesmas regras, ordem dos avisos e formato da resposta do Flask.

const VIDA_UTIL = { Informatica: 36, Moveis: 120, Equipamentos: 60, Estrutura: 120, Veiculos: 60, Ferramentas: 60, Outros: 60 };
const REGRAS = [
    ['Informatica', [['notebook', 'Notebook'], ['laptop', 'Notebook'], ['computador', 'Computador'], ['monitor', 'Monitor'],
        ['teclado', 'Teclado'], ['mouse', 'Mouse'], ['impressora', 'Impressora']]],
    ['Moveis', [['cadeira ergonomica', 'Cadeira ergonomica'], ['cadeira', 'Cadeira'], ['mesa de reuniao', 'Mesa de reuniao'],
        ['mesa', 'Mesa'], ['armario', 'Armario'], ['gaveteiro', 'Gaveteiro'], ['estante', 'Estante']]],
    ['Estrutura', [['ar-condicionado', 'Ar-condicionado'], ['ar condicionado', 'Ar-condicionado'], ['climatizador', 'Climatizador'],
        ['instalacao', 'Estrutura'], ['split', 'Ar-condicionado']]],
    ['Equipamentos', [['camera', 'Camera'], ['roteador', 'Roteador'], ['nobreak', 'Nobreak'], ['telefone', 'Telefone']]],
    ['Ferramentas', [['furadeira', 'Furadeira'], ['ferramenta', 'Ferramenta'], ['serra', 'Serra'], ['parafusadeira', 'Parafusadeira']]],
    ['Veiculos', [['veiculo', 'Veiculo'], ['carro', 'Veiculo'], ['moto', 'Moto']]],
];
const PREFERENCIAS = {
    Informatica: ['notebook', 'impressora', 'monitor', 'webcam'], Moveis: ['cadeira', 'mesa', 'moveis'],
    Estrutura: ['ar_condicionado', 'ar condicionado'], Equipamentos: ['impressora', 'webcam', 'monitor'],
    Ferramentas: ['ferramenta'], Veiculos: ['veiculo'], Outros: [],
};
const CAMPOS_EDITAVEIS = ['nome', 'categoria', 'descricao', 'fornecedor', 'documento_numero', 'data_aquisicao', 'valor_aquisicao',
    'vida_util_meses', 'centro_custo', 'localizacao', 'responsavel', 'imagem_arquivo', 'observacoes'];

// _normalizar: minusculas, sem acentos, so letras, digitos, espaco e hifen.
export function normalizar(valor) {
    return String(valor ?? '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '')
        .replace(/[^a-z0-9\s-]+/g, ' ').replace(/\s+/g, ' ').trim();
}

// str.title() do Python sobre texto ja normalizado (ASCII).
const titulo = (texto) => texto.replace(/[a-z]+/gi, (p) => p[0].toUpperCase() + p.slice(1).toLowerCase());

// Centavos com meio para cima (Decimal.quantize ROUND_HALF_UP).
const centavos = (valor) => {
    const n = Number(valor);
    return Number.isFinite(n) ? Math.sign(n) * Math.floor(Math.abs(n) * 100 + 0.5 + 1e-9) : 0;
};

function inferir(texto) {
    const normal = normalizar(texto);
    let melhor = null;
    for (const [categoria, regras] of REGRAS) {
        for (const [termo, nome] of regras) {
            const posicao = normal.indexOf(termo);
            if (posicao >= 0 && (melhor === null || posicao < melhor[0])) melhor = [posicao, categoria, nome, termo];
        }
    }
    return melhor ? melhor.slice(1) : ['Outros', 'Bem patrimonial', null];
}

function montarNome(nomeBase, texto) {
    const normal = normalizar(texto);
    const padroes = { Notebook: /\bnotebook\s+([a-z0-9][a-z0-9\s-]{1,40})/, Impressora: /\bimpressora\s+([a-z0-9][a-z0-9\s-]{1,32})/ };
    const m = padroes[nomeBase] && padroes[nomeBase].exec(normal);
    if (m) return titulo(`${nomeBase} ${m[1].trim()}`).slice(0, 160);
    return nomeBase.slice(0, 160);
}

function numeroDocumento(texto) {
    const normal = normalizar(texto);
    for (const padrao of [/(?:nf|nfs-e|nota fiscal|nota|numero|nro|no)\D{0,16}(\d{3,})/, /\b(\d{5,})\b/]) {
        const m = padrao.exec(normal);
        if (m) return m[1].slice(0, 80);
    }
    return null;
}

function imagem(categoria, nomeBase, texto, imagens) {
    if (!imagens || !imagens.length) return null;
    const alvo = normalizar([categoria, nomeBase, texto].join(' '));
    const chaves = [];
    if (alvo.includes('impressora')) chaves.push('impressora');
    if (alvo.includes('monitor')) chaves.push('monitor');
    if (alvo.includes('cadeira')) chaves.push('cadeira');
    if (alvo.includes('ar condicionado') || alvo.includes('ar-condicionado')) chaves.push('ar_condicionado');
    chaves.push(...(PREFERENCIAS[categoria] || []));
    for (const chave of chaves) {
        const alvoChave = normalizar(chave).replaceAll(' ', '_');
        const achada = imagens.find((i) => normalizar(i.arquivo).replaceAll(' ', '_').includes(alvoChave));
        if (achada) return achada.arquivo;
    }
    return null;
}

// d = financeiro.patrimonio_documento_sugestao_tela(perfil, comprovante).
export function gerarSugestao(d) {
    const avisos = [];
    if (d.vinculo_existente) avisos.push('Este documento fiscal ja esta vinculado a um bem patrimonial.');
    const texto = [d.texto_extraido, d.observacoes, d.prestador_nome, d.categoria_nome, d.categoria_ir_nome, d.arquivo_nome]
        .map((p) => (p === null || p === undefined ? '' : String(p))).join(' ');
    const [categoria, nomeBase, termo] = inferir(texto);
    const valorCentavos = centavos(d.valor);
    const vida = VIDA_UTIL[categoria] || VIDA_UTIL.Outros;
    const depreciacao = Math.floor(valorCentavos / vida + 0.5 + 1e-9) / 100;
    if (!texto.trim()) avisos.push('Texto extraido indisponivel. Revise os campos manualmente.');
    if (categoria === 'Outros') avisos.push('Categoria patrimonial nao identificada com seguranca.');
    if (valorCentavos <= 0) avisos.push('Valor de aquisicao nao identificado automaticamente.');
    const observacoes = [
        'Sugestao gerada a partir de documento fiscal importado.',
        'Vida util sugerida apenas para controle gerencial. Validacao contabil deve ser feita pelo contador.',
    ];
    if (termo) observacoes.push(`Termo usado na heuristica: ${termo}.`);
    if (d.origem_classificacao && String(d.origem_classificacao).toUpperCase().includes('OCR')) {
        avisos.push('Sugestao baseada em texto extraido por OCR. Revise os dados antes de confirmar.');
    }
    let descricao = `${nomeBase} sugerido a partir de documento fiscal de ${d.prestador_nome || 'fornecedor nao identificado'}.`;
    if (d.arquivo_nome) descricao += ` Arquivo: ${d.arquivo_nome}.`;
    return {
        comprovante_id: d.comprovante_id,
        documento: d.documento,
        bloqueado: Boolean(d.vinculo_existente),
        vinculo_existente: d.vinculo_existente || null,
        nome: montarNome(nomeBase, texto),
        categoria,
        descricao: descricao.slice(0, 2000),
        fornecedor: d.prestador_nome || '',
        documento_numero: numeroDocumento(texto) || `DOC-${d.comprovante_id}`,
        data_aquisicao: d.data_documento || null,
        valor_aquisicao: valorCentavos / 100,
        vida_util_meses: vida,
        depreciacao_mensal: depreciacao,
        centro_custo: '',
        localizacao: '',
        responsavel: '',
        imagem_arquivo: imagem(categoria, nomeBase, texto, d.imagens),
        status_documental: 'COM_LASTRO',
        natureza: 'PATRIMONIO_IMOBILIZADO',
        observacoes: observacoes.join('\n'),
        avisos,
        origem: d.texto_extraido ? 'texto_extraido' : 'dados_revisados',
        campos_editaveis: CAMPOS_EDITAVEIS,
    };
}
