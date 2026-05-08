const API_BASE = '/api/importacao-cartao';
const PERFIS = {
    NUBANK: 'nubank_csv_simples',
    CAIXA: 'caixa_credito_debito',
    MANUAL: 'manual_generico'
};
const MAX_PARCELAS_IMPORTACAO = 60;

const estado = {
    cartoes: [],
    categorias: [],
    categoriasCartao: [],
    arquivoSelecionado: null,
    formatoSelecionado: 'auto',
    csvData: null,
    payloadUnificado: null,
    usaMapeamentoManual: false,
    linhasMapeadas: [],
    linhasInvalidasIniciais: [],
    resumoPrevia: null,
    analiseConfronto: null,
    faseImportacao: 'triagem',
    parcelamentoModal: null,
    perfilSelecionado: PERFIS.MANUAL,
    mapeamentoAtual: {
        data_compra: null,
        descricao: null,
        valor: null,
        parcela: null,
        credito: null,
        debito: null
    },
    regraNubank: 'absoluto',
    regraCaixa: 'debito',
    filtroPrevia: 'a_importar',
    filtroPrincipal: 'todos',
    filtroRetirados: 'todos',
    paginaPrincipal: 1,
    paginaRetirados: 1,
    linhasPorPagina: 10,
    linhasSelecionadas: new Set(),
};

document.addEventListener('DOMContentLoaded', async () => {
    await carregarCartoes();
    configurarUpload();
    configurarMascaraCompetencia();
    configurarFormatoArquivo();
    inicializarPainel();
});

function inicializarPainel() {
    const cartaoSelect = document.getElementById('cartaoSelect');
    if (cartaoSelect) {
        cartaoSelect.addEventListener('change', async () => {
            await carregarCategorias();
            if (estado.linhasMapeadas.length) {
                estado.linhasMapeadas.forEach((linha) => {
                    linha.categoria_cartao_id = null;
                    linha.categoria_cartao_origem = null;
                });
                invalidarPrevia();
                renderizarEditorPrePersistencia();
            }
            renderizarClassificacao();
            atualizarResumoPainel();
        });
    }

    renderizarClassificacao();
    atualizarResumoPainel();
}

function configurarMascaraCompetencia() {
    const input = document.getElementById('competenciaInput');
    if (!input) return;

    input.addEventListener('input', (event) => {
        let valor = event.target.value.replace(/\D/g, '');
        if (valor.length >= 2) {
            valor = `${valor.substring(0, 2)}/${valor.substring(2, 6)}`;
        }
        event.target.value = valor;
    });
}

function configurarFormatoArquivo() {
    document.querySelectorAll('.import-format-option').forEach((button) => {
        button.addEventListener('click', () => {
            estado.formatoSelecionado = button.dataset.format || 'auto';

            document.querySelectorAll('.import-format-option').forEach((item) => {
                const selecionado = item === button;
                item.classList.toggle('is-selected', selecionado);
                item.setAttribute('aria-pressed', selecionado ? 'true' : 'false');
            });

            if (estado.arquivoSelecionado) {
                selecionarArquivo(estado.arquivoSelecionado);
            } else {
                limparFeedback('uploadResult');
            }
        });
    });
}

const toIntOrNull = (valor) => {
    if (valor === '' || valor === null || valor === undefined) return null;
    const numero = parseInt(valor, 10);
    return Number.isNaN(numero) ? null : numero;
};

function escapeHtml(valor) {
    return String(valor ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[char]));
}

function escapeAttr(valor) {
    return escapeHtml(valor).replace(/`/g, '&#96;');
}

function parseValorNumerico(raw) {
    if (raw === null || raw === undefined) return null;
    let texto = String(raw).trim();
    if (!texto) return null;

    texto = texto.replace('R$', '').replace(/\s+/g, '');
    if (texto.includes(',') && texto.includes('.')) {
        texto = texto.replace(/\./g, '').replace(',', '.');
    } else if (texto.includes(',')) {
        texto = texto.replace(',', '.');
    }

    const numero = Number(texto);
    return Number.isFinite(numero) ? numero : null;
}

const formatarValor = (valor) => {
    const numero = Number(valor);
    return Number.isFinite(numero) ? numero.toFixed(2) : '';
};

function formatarMoeda(valor) {
    const numero = Number(valor || 0);
    return numero.toLocaleString('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    });
}

function validarNumerosParcelamento(numero, total) {
    return Number.isInteger(numero)
        && Number.isInteger(total)
        && numero >= 1
        && total > 1
        && numero <= total
        && total <= MAX_PARCELAS_IMPORTACAO;
}

function detectarParcelamentoTexto(descricao) {
    const texto = String(descricao || '').trim();
    if (!texto) return null;

    const padroes = [
        /\b(?:PARC(?:ELA)?\.?)\s*(\d{1,2})\s*(?:\/|DE)\s*(\d{1,2})\b/i,
        /\b(\d{1,2})\s*\/\s*(\d{1,2})\b/i,
        /\b(\d{1,2})\s+DE\s+(\d{1,2})\b/i
    ];

    for (const padrao of padroes) {
        const match = texto.match(padrao);
        if (!match) continue;
        const numero = parseInt(match[1], 10);
        const total = parseInt(match[2], 10);
        if (validarNumerosParcelamento(numero, total)) {
            const descricaoLimpa = `${texto.slice(0, match.index)} ${texto.slice(match.index + match[0].length)}`
                .replace(/\s+/g, ' ')
                .replace(/^[\s\-–|]+|[\s\-–|]+$/g, '')
                .trim();
            return {
                ehParcelamento: true,
                parcelaAtual: numero,
                totalParcelas: total,
                padraoDetectado: match[0],
                descricaoLimpa: descricaoLimpa || texto,
                rotulo: `${numero}/${total}`
            };
        }
    }

    return null;
}

function detectarParcelaDescricao(descricao) {
    const detectado = detectarParcelamentoTexto(descricao);
    if (detectado) {
        return {
            numero_parcela: detectado.parcelaAtual,
            total_parcelas: detectado.totalParcelas,
            parcela: detectado.rotulo
        };
    }

    return {
        numero_parcela: 1,
        total_parcelas: 1,
        parcela: '1/1'
    };
}

function nomePerfil(perfil) {
    if (perfil === PERFIS.NUBANK) return 'Nubank CSV simples';
    if (perfil === PERFIS.CAIXA) return 'Caixa (Crédito/Débito)';
    return 'Manual genérico';
}

function iconSvg(nome) {
    const icons = {
        file: '<path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6"/>',
        pdf: '<path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v5h5"/><path d="M8 16h8M8 12h3"/><path d="M12 12h1.5a1.5 1.5 0 0 1 0 3H12v-3Z"/>',
        close: '<path d="M6 6l12 12M18 6 6 18"/>',
        eye: '<path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/>',
        trash: '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>',
        undo: '<path d="M9 14 5 10l4-4"/><path d="M5 10h9a5 5 0 0 1 0 10h-3"/>',
        check: '<path d="M5 12.5l4 4L19 7"/>',
        warning: '<path d="M12 8v5M12 17h.1"/><path d="M12 3 3.5 19h17L12 3Z"/>',
        parcel: '<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="8" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/><path d="M13 17h8M17 13v8"/>',
        link: '<path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.2 1.2"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.2-1.2"/>',
        new: '<path d="M12 5v14M5 12h14"/>'
    };

    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${icons[nome] || icons.file}</svg>`;
}

function setFeedback(id, mensagem, tipo = 'success') {
    const elemento = document.getElementById(id);
    if (!elemento) return;
    elemento.innerHTML = `<div class="import-feedback ${tipo}">${mensagem}</div>`;
}

function limparFeedback(id) {
    const elemento = document.getElementById(id);
    if (elemento) elemento.innerHTML = '';
}

function competenciaApi() {
    const valor = document.getElementById('competenciaInput')?.value || '';
    if (!/^\d{2}\/\d{4}$/.test(valor)) return null;
    const [mes, ano] = valor.split('/');
    return `${ano}-${mes}`;
}

function validarConfiguracaoBasica(silencioso = false) {
    const cartaoId = document.getElementById('cartaoSelect')?.value;
    const competencia = document.getElementById('competenciaInput')?.value || '';

    if (!cartaoId || !competencia) {
        if (!silencioso) alert('Selecione cartão e competência antes de validar a importação.');
        return false;
    }

    if (!/^\d{2}\/\d{4}$/.test(competencia)) {
        if (!silencioso) alert('Formato de competência inválido. Use MM/AAAA.');
        return false;
    }

    return true;
}

async function carregarCartoes() {
    try {
        const resposta = await fetch('/api/cartoes');
        const cartoes = await resposta.json();
        if (!Array.isArray(cartoes)) throw new Error('Resposta de cartões inválida');

        estado.cartoes = cartoes;
        const select = document.getElementById('cartaoSelect');
        select.innerHTML = '<option value="">Selecione um cartão</option>';
        cartoes.forEach((cartao) => {
            const option = document.createElement('option');
            option.value = cartao.id;
            option.textContent = cartao.nome;
            select.appendChild(option);
        });
    } catch (error) {
        console.error(error);
        alert('Erro ao carregar cartões.');
    }
}

async function carregarCategorias() {
    try {
        const categoriasResp = await fetch(`${API_BASE}/categorias`);
        const categoriasJson = await categoriasResp.json();
        if (categoriasJson.success) {
            estado.categorias = categoriasJson.categorias || [];
        }

        const cartaoId = document.getElementById('cartaoSelect')?.value;
        estado.categoriasCartao = [];
        if (cartaoId) {
            const categoriasCartaoResp = await fetch(`${API_BASE}/categorias-cartao/${cartaoId}`);
            const categoriasCartaoJson = await categoriasCartaoResp.json();
            if (categoriasCartaoJson.success) {
                estado.categoriasCartao = categoriasCartaoJson.categorias_cartao || [];
            }
        }

        renderizarClassificacao();
        atualizarResumoPainel();
    } catch (error) {
        console.error(error);
    }
}

function configurarUpload() {
    const area = document.getElementById('uploadArea');
    const input = document.getElementById('csvFile');
    if (!area || !input) return;

    area.addEventListener('click', () => input.click());
    area.addEventListener('dragover', (event) => {
        event.preventDefault();
        area.classList.add('drag-over');
    });
    area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
    area.addEventListener('drop', (event) => {
        event.preventDefault();
        area.classList.remove('drag-over');
        const file = event.dataTransfer.files[0];
        if (file) selecionarArquivo(file);
    });
    input.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) selecionarArquivo(file);
    });
}

function extensaoArquivo(file) {
    const nome = (file?.name || '').toLowerCase();
    const partes = nome.split('.');
    return partes.length > 1 ? partes.pop() : '';
}

function formatoArquivo(file) {
    const extensao = extensaoArquivo(file);
    if (extensao === 'pdf') return 'pdf';
    if (extensao === 'xlsx' || extensao === 'xls') return 'xlsx';
    if (extensao === 'csv') return 'csv';
    return 'desconhecido';
}

function formatarTamanho(bytes) {
    if (!Number.isFinite(bytes)) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function mostrarArquivoSelecionado(file) {
    const chip = document.getElementById('selectedFileInfo');
    if (!chip) return;

    const tipo = formatoArquivo(file);
    chip.hidden = false;
    chip.className = 'import-file-inline import-file-inline--selected';
    chip.innerHTML = `
        <span class="file-icon ${tipo === 'pdf' ? '' : 'neutral'}">${iconSvg(tipo === 'pdf' ? 'pdf' : 'file')}</span>
        <span class="import-file-inline-text" title="${escapeAttr(file.name)}">${escapeHtml(file.name)}<small class="import-file-size">${formatarTamanho(file.size)}</small></span>
        <button class="import-file-remove" type="button" onclick="removerArquivoSelecionado(event)" title="Remover arquivo" aria-label="Remover arquivo">${iconSvg('close')}</button>
    `;
}

function renderizarArquivoPlaceholder() {
    const chip = document.getElementById('selectedFileInfo');
    if (!chip) return;
    chip.hidden = false;
    chip.className = 'import-file-inline';
    chip.innerHTML = `
        <span class="file-icon neutral" aria-hidden="true">${iconSvg('file')}</span>
        <span class="import-file-inline-text">Selecione Arquivo — pdf, csv ou xlsx</span>
    `;
}

function abrirSeletorArquivo() {
    document.getElementById('csvFile')?.click();
}

function removerArquivoSelecionado(event) {
    if (event) event.stopPropagation();
    const input = document.getElementById('csvFile');

    if (input) input.value = '';
    renderizarArquivoPlaceholder();

    estado.arquivoSelecionado = null;
    limparDadosImportacao();
    limparFeedback('uploadResult');
    atualizarResumoPainel();
}

function limparDadosImportacao() {
    estado.csvData = null;
    estado.payloadUnificado = null;
    estado.usaMapeamentoManual = false;
    estado.linhasMapeadas = [];
    estado.linhasInvalidasIniciais = [];
    estado.resumoPrevia = null;
    estado.analiseConfronto = null;
    estado.faseImportacao = 'triagem';
    estado.parcelamentoModal = null;
    estado.perfilSelecionado = PERFIS.MANUAL;
    estado.filtroPrevia = 'a_importar';
    estado.filtroPrincipal = 'todos';
    estado.filtroRetirados = 'todos';
    estado.paginaPrincipal = 1;
    estado.paginaRetirados = 1;
    estado.linhasSelecionadas = new Set();
    estado.mapeamentoAtual = {
        data_compra: null,
        descricao: null,
        valor: null,
        parcela: null,
        credito: null,
        debito: null
    };

    document.getElementById('btnStep3').disabled = true;
    document.getElementById('btnStep4').disabled = true;
    document.getElementById('btnImportar').disabled = true;
    document.getElementById('mapeamentoContainer').innerHTML = '';
    document.getElementById('resumoConfiguracaoImportacao').innerHTML = '';
    document.getElementById('previaContainer').innerHTML = '<div class="import-empty-state">Carregue um documento para validar o layout e revisar os lançamentos.</div>';
    document.getElementById('editorPrePersistencia').innerHTML = '';
    document.getElementById('resumoPreviaTecnica').innerHTML = '';
    const confronto = document.getElementById('confrontoContainer');
    if (confronto) confronto.innerHTML = '';
    const retirados = document.getElementById('retiradosContainer');
    if (retirados) retirados.innerHTML = '<div class="import-empty-state compact">Nenhum lançamento retirado da efetivação.</div>';
    document.getElementById('resultadoContainer').innerHTML = '';
    renderizarClassificacao();
    renderizarKpisImportacao();
}

function selecionarArquivo(file) {
    estado.arquivoSelecionado = file;
    mostrarArquivoSelecionado(file);
    limparDadosImportacao();

    const tipo = formatoArquivo(file);
    const formato = estado.formatoSelecionado;

    if (formato === 'pdf' && tipo !== 'pdf') {
        setFeedback('uploadResult', 'O formato selecionado é PDF. Escolha um arquivo PDF ou volte para Automático/CSV.', 'warning');
        return;
    }

    if (formato === 'csv' && tipo === 'pdf') {
        setFeedback('uploadResult', 'O formato selecionado é CSV/XLSX. Escolha um arquivo CSV ou XLSX, ou altere para PDF.', 'warning');
        return;
    }

    if (!['csv', 'xlsx', 'pdf'].includes(tipo)) {
        setFeedback('uploadResult', 'Formato não reconhecido. Use CSV, XLSX ou PDF.', 'error');
        return;
    }

    analisarArquivo(file);
}

function formatoBackend(file) {
    const tipo = formatoArquivo(file);
    if (estado.formatoSelecionado === 'pdf') return 'pdf';
    if (estado.formatoSelecionado === 'csv') return tipo === 'xlsx' ? 'xlsx' : 'csv';
    return 'automatico';
}

async function analisarArquivo(file) {
    const tipo = formatoArquivo(file);
    if (!validarConfiguracaoBasica(true)) {
        if (tipo === 'csv') {
            processarCSV(file);
            return;
        }
        setFeedback('uploadResult', 'Selecione cartão e competência antes de analisar PDF ou XLSX.', 'warning');
        return;
    }

    const formData = new FormData();
    formData.append('arquivo', file);
    formData.append('cartao_id', document.getElementById('cartaoSelect').value);
    formData.append('competencia', competenciaApi());
    formData.append('formato', formatoBackend(file));

    try {
        setFeedback('uploadResult', 'Analisando arquivo...', 'warning');
        await carregarCategorias();

        const resposta = await fetch(`${API_BASE}/analisar`, {
            method: 'POST',
            body: formData
        });
        const dados = await resposta.json();
        if (!resposta.ok || !dados.success) {
            throw new Error(dados.error || dados.message || 'Falha ao analisar arquivo');
        }

        if (dados.data?.requer_mapeamento && tipo === 'csv') {
            processarCSV(file);
            return;
        }

        aplicarPayloadUnificado(dados.data);
    } catch (error) {
        if (tipo === 'csv') {
            processarCSV(file);
            return;
        }
        setFeedback('uploadResult', `Erro ao analisar arquivo: ${escapeHtml(error.message)}`, 'error');
        atualizarResumoPainel();
    }
}

function converterLinhaIntermediaria(linha) {
    const parcelaAtual = linha.parcela_atual || linha.numero_parcela || 1;
    const totalParcelas = linha.total_parcelas || 1;
    return {
        linha_id: linha.linha_id,
        linha_origem: linha.linha_origem,
        status: linha.status,
        data_compra: linha.data_compra,
        descricao: linha.descricao_normalizada || linha.descricao_original || linha.descricao_exibida,
        descricao_original: linha.descricao_original,
        descricao_exibida: linha.descricao_exibida || linha.descricao_normalizada || linha.descricao_original,
        valor: formatarValor(linha.valor),
        categoria_id: toIntOrNull(linha.categoria_id || linha.categoria_despesa_id),
        categoria_despesa_id: toIntOrNull(linha.categoria_despesa_id || linha.categoria_id),
        categoria_nome: linha.categoria_nome,
        categoria_origem: linha.categoria_origem || linha.categoria_sugerida_origem,
        categoria_cartao_id: toIntOrNull(linha.categoria_cartao_id),
        categoria_cartao_nome: linha.categoria_cartao_nome,
        categoria_cartao_origem: linha.categoria_cartao_origem || linha.categoria_cartao_sugerida_origem,
        categoria_cartao_vinculada_ao_cartao: linha.categoria_cartao_vinculada_ao_cartao,
        status_classificacao: linha.status_classificacao,
        descricao_normalizada: linha.descricao_normalizada,
        categoria_confianca: linha.categoria_confianca || linha.confianca_categoria,
        confianca_categoria: linha.confianca_categoria || linha.categoria_confianca,
        palavras_chave_encontradas: linha.palavras_chave_encontradas || [],
        categorias_candidatas: linha.categorias_candidatas || [],
        categoria_sugerida_origem: linha.categoria_sugerida_origem,
        categoria_detectada_label: linha.categoria_detectada,
        cartao_final: linha.cartao_final,
        grupo: linha.grupo,
        tipo_movimento: linha.tipo_movimento || 'debito',
        duplicidade: linha.duplicidade,
        mensagens: linha.mensagens || [],
        avisos: linha.avisos || [],
        metadados: linha.metadados || {},
        origem_importacao: linha.origem_importacao || estado.payloadUnificado?.origem || 'csv',
        parcela: linha.parcela || `${parcelaAtual}/${totalParcelas}`,
        numero_parcela: parcelaAtual,
        parcela_atual: parcelaAtual,
        total_parcelas: totalParcelas,
        parcelado: Number(totalParcelas) > 1,
        gerar_parcelas_futuras: !!linha.gerar_parcelas_futuras,
        ignorar: !!linha.ignorar || ['ignorado', 'duplicado'].includes(linha.status)
    };
}

function aplicarPayloadUnificado(data) {
    estado.payloadUnificado = data;
    estado.usaMapeamentoManual = false;
    estado.csvData = {
        total_linhas: data?.validacoes?.total_linhas || data?.linhas?.length || 0,
        origem: data?.origem,
        fatura: data?.fatura || {}
    };
    estado.linhasMapeadas = (data?.linhas || []).map(converterLinhaIntermediaria);
    estado.linhasInvalidasIniciais = [];
    estado.resumoPrevia = null;
    estado.analiseConfronto = null;
    estado.faseImportacao = 'triagem';
    estado.filtroPrevia = 'a_importar';
    estado.filtroPrincipal = 'todos';
    estado.filtroRetirados = 'todos';
    estado.paginaPrincipal = 1;
    estado.paginaRetirados = 1;
    estado.linhasSelecionadas = new Set();

    limparFeedback('uploadResult');
    document.getElementById('mapeamentoContainer').innerHTML = '';

    document.getElementById('btnStep3').disabled = true;
    document.getElementById('btnStep4').disabled = false;
    document.getElementById('btnImportar').disabled = true;
    renderizarResumoAnalise(data, estado.linhasMapeadas.length);
    renderizarMapeamento();
    renderizarEditorPrePersistencia();
    atualizarResumoPainel();
}

function renderizarResumoAnalise(data, linhasNormalizadas) {
    const container = document.getElementById('resumoConfiguracaoImportacao');
    if (!container || !data) return;

    const fatura = data.fatura || {};
    const validacoes = data.validacoes || {};
    const cartoes = (fatura.cartoes_detectados || []).join(', ') || '-';
    const origemLabel = (data.origem || '').toUpperCase();
    const competencia = fatura.competencia || fatura.vencimento || '-';
    const totalFatura = fatura.valor_total !== null && fatura.valor_total !== undefined
        ? formatarMoeda(fatura.valor_total) : '-';
    const diferenca = Number(validacoes.diferenca || 0);
    const cls = validacoes.revisar_totais ? 'warning' : 'success';

    const itens = [
        `${origemLabel} analisado com sucesso. <strong>${linhasNormalizadas || 0}</strong> linhas normalizadas`,
        `Competência: <strong>${escapeHtml(competencia)}</strong>`,
        `Total da fatura: <strong>${totalFatura}</strong>`,
        `Cartões detectados: <strong>${escapeHtml(cartoes)}</strong>`,
        `Total importável: <strong>${formatarMoeda(validacoes.total_importavel || 0)}</strong>`,
        `Diferença: <strong>${formatarMoeda(diferenca)}</strong>`,
    ];

    container.innerHTML = `
        <div class="import-feedback import-feedback--faixa ${cls}">
            ${itens.join('<span class="import-faixa-sep" aria-hidden="true">|</span>')}
        </div>
    `;
}

async function processarCSV(file) {
    const formData = new FormData();
    formData.append('arquivo', file);

    try {
        const resposta = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
        });
        const dados = await resposta.json();
        if (!resposta.ok || !dados.success) {
            throw new Error(dados.message || 'Falha ao processar CSV');
        }

        estado.csvData = dados;
        estado.payloadUnificado = null;
        estado.usaMapeamentoManual = true;
        estado.linhasMapeadas = [];
        estado.linhasInvalidasIniciais = [];
        estado.resumoPrevia = null;
        estado.analiseConfronto = null;
        estado.faseImportacao = 'triagem';
        estado.filtroPrevia = 'a_importar';
        estado.filtroPrincipal = 'todos';
        estado.filtroRetirados = 'todos';
        estado.paginaPrincipal = 1;
        estado.paginaRetirados = 1;
        estado.linhasSelecionadas = new Set();
        estado.perfilSelecionado = dados.perfil_detectado || PERFIS.MANUAL;
        estado.mapeamentoAtual = {
            data_compra: dados.mapeamento_sugerido?.data_compra ?? null,
            descricao: dados.mapeamento_sugerido?.descricao ?? null,
            valor: dados.mapeamento_sugerido?.valor ?? null,
            parcela: dados.mapeamento_sugerido?.parcela ?? null,
            credito: dados.mapeamento_sugerido?.credito ?? null,
            debito: dados.mapeamento_sugerido?.debito ?? null
        };

        const mensagemPerfil = dados.autodeteccao_confianca === 'alta'
            ? `Perfil detectado automaticamente: <strong>${escapeHtml(nomePerfil(dados.perfil_detectado))}</strong>.`
            : 'Perfil não identificado com confiança. Valide o mapeamento manualmente.';

        setFeedback(
            'uploadResult',
            `CSV carregado com sucesso. <strong>${dados.total_linhas}</strong> linhas detectadas. Delimitador: <strong>${escapeHtml(dados.delimitador)}</strong>. ${mensagemPerfil}`,
            'success'
        );

        document.getElementById('btnStep3').disabled = false;
        document.getElementById('btnStep4').disabled = true;
        document.getElementById('btnImportar').disabled = true;
        renderizarMapeamento();
        atualizarResumoPainel();
    } catch (error) {
        setFeedback('uploadResult', `Erro ao processar CSV: ${escapeHtml(error.message)}`, 'error');
        atualizarResumoPainel();
    }
}

async function proximaEtapa(numero) {
    if (numero === 2) {
        return validarConfiguracaoBasica();
    }

    if (numero === 3) {
        if (!estado.csvData) {
            alert('Faça upload de um arquivo antes de validar o layout.');
            return false;
        }
        if (!validarConfiguracaoBasica()) return false;
        await carregarCategorias();
        if (estado.payloadUnificado && !estado.usaMapeamentoManual) {
            renderizarMapeamento();
            renderizarEditorPrePersistencia();
            rolarParaSecao('step3');
            return true;
        }
        renderizarMapeamento();
        abrirModalValidacao();
        rolarParaSecao('step3');
        return true;
    }

    if (numero === 4) {
        if (!estado.linhasMapeadas.length) {
            alert('Analise o arquivo ou valide o perfil antes de confrontar os lançamentos.');
            return false;
        }
        await previsualizarImportacao();
        rolarParaSecao('step5');
        return true;
    }

    if (numero === 5) {
        rolarParaSecao('step5');
        return true;
    }

    return true;
}

function voltarEtapa(numero) {
    rolarParaSecao(`step${numero}`);
}

function rolarParaSecao(id) {
    const elemento = document.getElementById(id);
    if (elemento) {
        elemento.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
    }
}

function invalidarPrevia(opcoes = {}) {
    estado.resumoPrevia = null;
    if (!opcoes.manterConfronto) {
        estado.analiseConfronto = null;
        estado.faseImportacao = 'triagem';
        estado.paginaPrincipal = 1;
        const confronto = document.getElementById('confrontoContainer');
        if (confronto) confronto.innerHTML = '';
    }
    estado.paginaRetirados = 1;
    const resumo = document.getElementById('resumoPreviaTecnica');
    if (resumo) resumo.innerHTML = '';
    const resultado = document.getElementById('resultadoContainer');
    if (resultado) resultado.innerHTML = '';
    atualizarResumoPainel();
}

function renderizarMapeamento() {
    const container = document.getElementById('mapeamentoContainer');
    if (!container) return;

    if (!estado.csvData) {
        container.innerHTML = '';
        return;
    }

    if (estado.payloadUnificado && !estado.usaMapeamentoManual) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <div class="import-feedback success">
            Perfil selecionado: <strong>${escapeHtml(nomePerfil(estado.perfilSelecionado))}</strong>.
            Use "Validar layout" para confirmar o mapeamento e liberar a prévia.
        </div>
    `;
}

function obterOpcoesColunas(selecionado) {
    const colunas = estado.csvData?.colunas || [];
    return `<option value="">-- Não mapear --</option>${colunas.map((coluna, index) => (
        `<option value="${index}" ${selecionado === index ? 'selected' : ''}>${escapeHtml(coluna)}</option>`
    )).join('')}`;
}

function abrirModalValidacao() {
    if (!estado.csvData) {
        alert('Carregue o CSV antes de validar.');
        return;
    }

    const perfis = estado.csvData.perfis_suportados || [
        { id: PERFIS.NUBANK, nome: nomePerfil(PERFIS.NUBANK) },
        { id: PERFIS.CAIXA, nome: nomePerfil(PERFIS.CAIXA) },
        { id: PERFIS.MANUAL, nome: nomePerfil(PERFIS.MANUAL) }
    ];

    document.getElementById('modalPerfil').innerHTML = perfis.map((perfil) => (
        `<option value="${escapeAttr(perfil.id)}" ${estado.perfilSelecionado === perfil.id ? 'selected' : ''}>${escapeHtml(perfil.nome)}</option>`
    )).join('');
    document.getElementById('modalMapData').innerHTML = obterOpcoesColunas(estado.mapeamentoAtual.data_compra);
    document.getElementById('modalMapDescricao').innerHTML = obterOpcoesColunas(estado.mapeamentoAtual.descricao);
    document.getElementById('modalMapValor').innerHTML = obterOpcoesColunas(estado.mapeamentoAtual.valor);
    document.getElementById('modalMapParcela').innerHTML = obterOpcoesColunas(estado.mapeamentoAtual.parcela);
    document.getElementById('modalMapCredito').innerHTML = obterOpcoesColunas(estado.mapeamentoAtual.credito);
    document.getElementById('modalMapDebito').innerHTML = obterOpcoesColunas(estado.mapeamentoAtual.debito);
    document.getElementById('modalRegraNubank').value = estado.regraNubank;
    document.getElementById('modalRegraCaixa').value = estado.regraCaixa;

    document.getElementById('modalCategoriaPadrao').innerHTML =
        `<option value="">Selecione</option>${estado.categorias.map((categoria) => (
            `<option value="${categoria.id}">${escapeHtml(categoria.nome)}</option>`
        )).join('')}`;

    atualizarCamposPerfilModal();
    renderizarAmostraModal();
    document.getElementById('perfilModal').style.display = 'flex';
}

function fecharModalValidacao() {
    document.getElementById('perfilModal').style.display = 'none';
}

function atualizarCamposPerfilModal() {
    const perfil = document.getElementById('modalPerfil').value;
    document.getElementById('boxCamposCaixa').hidden = perfil !== PERFIS.CAIXA;
    document.getElementById('boxCamposNubank').hidden = perfil !== PERFIS.NUBANK;
    document.getElementById('boxCamposManual').hidden = perfil === PERFIS.CAIXA || perfil === PERFIS.NUBANK;
    document.getElementById('boxCampoValor').hidden = perfil === PERFIS.CAIXA;
}

function obterConfiguracaoModal() {
    const perfil = document.getElementById('modalPerfil').value;
    return {
        perfil,
        mapeamento: {
            data_compra: toIntOrNull(document.getElementById('modalMapData').value),
            descricao: toIntOrNull(document.getElementById('modalMapDescricao').value),
            valor: toIntOrNull(document.getElementById('modalMapValor').value),
            parcela: toIntOrNull(document.getElementById('modalMapParcela').value),
            credito: toIntOrNull(document.getElementById('modalMapCredito').value),
            debito: toIntOrNull(document.getElementById('modalMapDebito').value)
        },
        regraNubank: document.getElementById('modalRegraNubank').value,
        regraCaixa: document.getElementById('modalRegraCaixa').value,
        categoriaPadrao: toIntOrNull(document.getElementById('modalCategoriaPadrao').value)
    };
}

function interpretarLinhaPorPerfil(linhaCsv, config) {
    const mapeamento = config.mapeamento;
    const data = mapeamento.data_compra !== null ? linhaCsv[mapeamento.data_compra] : null;
    const descricao = mapeamento.descricao !== null ? linhaCsv[mapeamento.descricao] : null;
    const parcelaCampo = mapeamento.parcela !== null ? linhaCsv[mapeamento.parcela] : null;

    if (!data || !descricao) {
        return { ok: false, erro: 'Data/descrição não mapeadas' };
    }

    let valor = null;
    if (config.perfil === PERFIS.CAIXA) {
        const credito = mapeamento.credito !== null ? parseValorNumerico(linhaCsv[mapeamento.credito]) : null;
        const debito = mapeamento.debito !== null ? parseValorNumerico(linhaCsv[mapeamento.debito]) : null;
        if (config.regraCaixa === 'debito') valor = debito;
        else if (config.regraCaixa === 'credito') valor = credito;
        else valor = (debito !== null && debito !== 0) ? debito : credito;
        if (valor === null || valor === 0) {
            return { ok: false, erro: 'Linha sem valor compatível com regra crédito/débito' };
        }
        valor = Math.abs(valor);
    } else {
        const valorBruto = mapeamento.valor !== null ? parseValorNumerico(linhaCsv[mapeamento.valor]) : null;
        if (valorBruto === null || valorBruto === 0) {
            return { ok: false, erro: 'Linha sem valor válido' };
        }
        if (config.perfil === PERFIS.NUBANK) {
            if (config.regraNubank === 'despesas_negativas') {
                if (valorBruto >= 0) return { ok: false, erro: 'Valor não negativo conforme regra Nubank' };
                valor = Math.abs(valorBruto);
            } else if (config.regraNubank === 'despesas_positivas') {
                if (valorBruto <= 0) return { ok: false, erro: 'Valor não positivo conforme regra Nubank' };
                valor = valorBruto;
            } else {
                valor = Math.abs(valorBruto);
            }
        } else {
            valor = Math.abs(valorBruto);
        }
    }

    const parcelaDescricao = detectarParcelaDescricao(descricao);
    const parcelaExplicita = detectarParcelaDescricao(parcelaCampo);
    const numeroParcela = parcelaExplicita.total_parcelas > 1 ? parcelaExplicita.numero_parcela : parcelaDescricao.numero_parcela;
    const totalParcelas = parcelaExplicita.total_parcelas > 1 ? parcelaExplicita.total_parcelas : parcelaDescricao.total_parcelas;

    return {
        ok: true,
        linha: {
            data_compra: String(data).trim(),
            descricao: String(descricao).trim(),
            descricao_exibida: String(descricao).trim(),
            valor: formatarValor(valor),
            categoria_id: config.categoriaPadrao,
            categoria_cartao_id: null,
            categoria_cartao_origem: null,
            categoria_sugerida_origem: 'fallback_lote',
            categoria_detectada_label: 'fallback do lote',
            parcela: `${numeroParcela}/${totalParcelas}`,
            numero_parcela: numeroParcela,
            total_parcelas: totalParcelas,
            parcelado: totalParcelas > 1,
            gerar_parcelas_futuras: false,
            ignorar: false
        }
    };
}

function construirLoteMapeado(config) {
    const linhas = estado.csvData?.linhas_dados || [];
    const mapeadas = [];
    const invalidas = [];

    linhas.forEach((linha, index) => {
        const interpretada = interpretarLinhaPorPerfil(linha, config);
        if (!interpretada.ok) {
            invalidas.push({
                linha: index + 1,
                erro: interpretada.erro
            });
            return;
        }
        mapeadas.push({
            linha_origem: index + 1,
            ...interpretada.linha
        });
    });

    return { mapeadas, invalidas };
}

async function aplicarSugestoesCategoria(linhas, fallback) {
    const descricoes = [...new Set(linhas.map((linha) => linha.descricao).filter(Boolean))];
    if (!descricoes.length) return linhas;

    try {
        const resposta = await fetch(`${API_BASE}/sugerir-categorias`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                descricoes,
                categoria_fallback_id: fallback
            })
        });
        const dados = await resposta.json();
        if (!resposta.ok || !dados.success) {
            throw new Error(dados.message || 'Falha na sugestão');
        }

        const sugestoes = dados.sugestoes || {};
        const linhasComCategoria = linhas.map((linha) => {
            const sugestao = sugestoes[linha.descricao];
            if (!sugestao) return linha;
            const origem = sugestao.origem || linha.categoria_sugerida_origem;
            return {
                ...linha,
                categoria_id: sugestao.categoria_id || linha.categoria_id,
                categoria_despesa_id: sugestao.categoria_id || linha.categoria_despesa_id || linha.categoria_id,
                categoria_origem: origem,
                categoria_sugerida_origem: origem,
                categoria_detectada_label: origem === 'historico' ? 'histórico' : 'fallback'
            };
        });
        return resolverCategoriasCartaoLote(linhasComCategoria);
    } catch (error) {
        console.warn(error);
        return resolverCategoriasCartaoLote(linhas);
    }
}

async function resolverCategoriasCartaoLote(linhas) {
    const cartaoId = parseInt(document.getElementById('cartaoSelect')?.value || '', 10);
    if (!cartaoId) return linhas;

    const cache = new Map();
    const resolvidas = [];

    for (const linha of linhas) {
        const categoriaId = toIntOrNull(linha.categoria_id || linha.categoria_despesa_id);
        if (!categoriaId || categoriaCartaoIdLinha(linha)) {
            resolvidas.push(linha);
            continue;
        }

        if (!cache.has(categoriaId)) {
            cache.set(categoriaId, buscarResolucaoCategoriaCartao(categoriaId, cartaoId));
        }

        try {
            const resolucao = await cache.get(categoriaId);
            resolvidas.push(aplicarResolucaoCategoriaCartaoLinha(linha, resolucao));
        } catch (error) {
            console.warn('Falha ao resolver Categoria do Cartao:', error);
            resolvidas.push(linha);
        }
    }

    return resolvidas;
}

async function buscarResolucaoCategoriaCartao(categoriaId, cartaoId) {
    const resp = await fetch(`/api/categorias-cartao/resolver?categoria_id=${encodeURIComponent(categoriaId)}&cartao_id=${encodeURIComponent(cartaoId)}`);
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
        throw new Error(payload.error || payload.message || 'Falha ao resolver Categoria do Cartao');
    }
    return payload.data || payload;
}

function aplicarResolucaoCategoriaCartaoLinha(linha, resolucao = {}) {
    const avisos = [...(linha.avisos || []), ...(linha.mensagens || [])];
    const categoriaCartaoId = toIntOrNull(resolucao.categoria_cartao_id);
    const vinculada = resolucao.vinculada_ao_cartao !== false;
    const proxima = {
        ...linha,
        avisos,
        mensagens: avisos,
        categoria_cartao_nome: resolucao.categoria_cartao_nome || linha.categoria_cartao_nome,
        categoria_cartao_vinculada_ao_cartao: categoriaCartaoId ? vinculada : false
    };

    if (categoriaCartaoId && vinculada) {
        proxima.categoria_cartao_id = categoriaCartaoId;
        proxima.categoria_cartao_origem = resolucao.origem || 'mapa_categoria_despesa';
        proxima.status_classificacao = proxima.categoria_id ? 'classificada' : proxima.status_classificacao;
        return proxima;
    }

    proxima.categoria_cartao_id = null;

    const temCategoriaResolvida = toIntOrNull(resolucao.categoria_cartao_resolvida_id || resolucao.categoria_cartao_id);
    if (temCategoriaResolvida && resolucao.vinculada_ao_cartao === false) {
        proxima.categoria_cartao_origem = 'nao_vinculada_ao_cartao';
        proxima.status_classificacao = 'categoria_cartao_nao_vinculada';
        const aviso = 'Esta Categoria do Cartao ainda nao esta vinculada ao cartao selecionado.';
        if (!proxima.avisos.includes(aviso)) proxima.avisos.push(aviso);
        proxima.mensagens = proxima.avisos;
        return proxima;
    }

    proxima.categoria_cartao_origem = 'nao_configurada';
    proxima.status_classificacao = 'categoria_cartao_pendente';
    const aviso = 'Categoria do Cartao ainda nao configurada para esta Categoria de Despesa.';
    if (!proxima.avisos.includes(aviso)) proxima.avisos.push(aviso);
    proxima.mensagens = proxima.avisos;
    return proxima;
}

function renderizarAmostraModal() {
    const config = obterConfiguracaoModal();
    const resultado = construirLoteMapeado(config);
    const amostra = resultado.mapeadas.slice(0, 8);

    document.getElementById('modalAmostraInterpretada').innerHTML = `
        <div class="import-feedback success">
            Linhas válidas estimadas: <strong>${resultado.mapeadas.length}</strong> |
            Inválidas estimadas: <strong>${resultado.invalidas.length}</strong>
        </div>
        <div class="import-preview-table-wrap">
            <table class="import-preview-table">
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>Descrição</th>
                        <th>Valor</th>
                    </tr>
                </thead>
                <tbody>
                    ${amostra.map((linha) => `
                        <tr>
                            <td>${escapeHtml(linha.data_compra)}</td>
                            <td>${escapeHtml(linha.descricao)}</td>
                            <td>${formatarMoeda(linha.valor)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

async function confirmarValidacaoModal() {
    const config = obterConfiguracaoModal();
    if (config.mapeamento.data_compra === null || config.mapeamento.descricao === null) {
        alert('Mapeie data e descrição.');
        return;
    }
    if (config.perfil === PERFIS.CAIXA) {
        if (config.mapeamento.credito === null && config.mapeamento.debito === null) {
            alert('No perfil Caixa, informe ao menos crédito ou débito.');
            return;
        }
    } else if (config.mapeamento.valor === null) {
        alert('Mapeie a coluna de valor.');
        return;
    }

    const resultado = construirLoteMapeado(config);
    if (!resultado.mapeadas.length) {
        alert('Nenhuma linha válida encontrada com a configuração atual.');
        return;
    }

    estado.perfilSelecionado = config.perfil;
    estado.mapeamentoAtual = config.mapeamento;
    estado.regraNubank = config.regraNubank;
    estado.regraCaixa = config.regraCaixa;
    estado.linhasInvalidasIniciais = resultado.invalidas;
    estado.linhasMapeadas = await aplicarSugestoesCategoria(resultado.mapeadas, config.categoriaPadrao);

    invalidarPrevia();
    document.getElementById('resumoConfiguracaoImportacao').innerHTML = `
        <div class="import-feedback success">
            Perfil validado: <strong>${escapeHtml(nomePerfil(config.perfil))}</strong>.
            Linhas na triagem: <strong>${estado.linhasMapeadas.length}</strong>.
            Linhas inválidas no parse inicial: <strong>${resultado.invalidas.length}</strong>.
            Revise quais lançamentos seguem na importação antes de confirmar.
        </div>
    `;

    renderizarEditorPrePersistencia();
    fecharModalValidacao();
}

function nomeCategoriaDespesa(id) {
    const categoria = estado.categorias.find((item) => Number(item.id) === Number(id));
    return categoria ? categoria.nome : '';
}

function categoriaCartaoIdLinha(linha) {
    return toIntOrNull(linha.categoria_cartao_id);
}

function avisoCategoriaCartaoMapeamentoLinha(linha) {
    if (!toIntOrNull(linha.categoria_id || linha.categoria_despesa_id)) return '';
    const origem = linha.categoria_cartao_origem;
    if (linha.status_classificacao === 'categoria_cartao_nao_vinculada'
        || origem === 'categoria_cartao_nao_vinculada'
        || origem === 'nao_vinculada_ao_cartao') {
        return 'Esta categoria da despesa ainda nao esta vinculada ao cartao selecionado.';
    }
    if (linha.status_classificacao === 'categoria_cartao_pendente' || origem === 'nao_configurada') {
        return 'Esta categoria da despesa nao possui mapeamento para o cartao. Ajuste em Categorias antes de importar.';
    }
    return '';
}

function opcoesCategoriaSelect(selecionado) {
    return `<option value="">Selecione uma categoria</option>${estado.categorias.map((categoria) => (
        `<option value="${categoria.id}" ${Number(selecionado) === Number(categoria.id) ? 'selected' : ''}>${escapeHtml(categoria.nome)}</option>`
    )).join('')}`;
}

function linhaDuplicada(linha) {
    return linha.status === 'duplicado' || linha.status_classificacao === 'duplicada' || linha.duplicada === true;
}

function linhaComErro(linha) {
    return linha.status === 'erro' || linha.status_classificacao === 'erro';
}

function linhaCredito(linha) {
    return linha.tipo_movimento === 'credito';
}

function linhaTratadaParcelamento(linha) {
    return Boolean(linha.tratada_como_parcelamento || linha.status === 'parcelamento_criado');
}

function linhaRecorrenciaVinculada(linha) {
    return Boolean(linha.recorrencia_vinculada || linha.status === 'recorrencia_vinculada');
}

function linhaBloqueadaTecnica(linha) {
    return linhaDuplicada(linha) || linhaComErro(linha) || linhaCredito(linha);
}

function linhaImportavel(linha) {
    return !linha.ignorar
        && !linhaTratadaParcelamento(linha)
        && !linhaRecorrenciaVinculada(linha)
        && !linhaBloqueadaTecnica(linha);
}

function descricaoOriginalLinha(linha) {
    return linha.descricao_original || linha.descricao_cartao || linha.descricao || linha.descricao_exibida || '';
}

function detectarParcelamentoLinha(linha) {
    const numeroExistente = toIntOrNull(linha.numero_parcela || linha.parcela_atual);
    const totalExistente = toIntOrNull(linha.total_parcelas);
    if (validarNumerosParcelamento(numeroExistente, totalExistente)) {
        return {
            numero: numeroExistente,
            total: totalExistente,
            rotulo: `${numeroExistente}/${totalExistente}`,
            origem: 'campo'
        };
    }

    const detectado = detectarParcelamentoTexto(descricaoOriginalLinha(linha)) || detectarParcelamentoTexto(linha.parcela);
    if (detectado) {
        return {
            numero: detectado.parcelaAtual,
            total: detectado.totalParcelas,
            rotulo: detectado.rotulo,
            origem: 'descricao',
            padraoDetectado: detectado.padraoDetectado,
            descricaoLimpa: detectado.descricaoLimpa
        };
    }

    return null;
}

function rotuloParcelamentoVisual(parcela) {
    const numero = toIntOrNull(parcela?.numero);
    const total = toIntOrNull(parcela?.total);
    if (!numero || !total) return parcela?.rotulo || '';
    return `${String(numero).padStart(2, '0')}/${String(total).padStart(2, '0')}`;
}

function sugestaoParcelamentoLinha(parcela) {
    const rotulo = rotuloParcelamentoVisual(parcela);
    return rotulo ? `${rotulo} detectado` : 'Parcelamento detectado';
}

function linhaPossivelParcelamento(linha) {
    return !!detectarParcelamentoLinha(linha);
}

function linhaPossivelRecorrencia(linha) {
    return Boolean(
        linha.is_recorrente
        || linha.recorrencia_id
        || linha.item_despesa_id
        || reconhecimentoEhRecorrencia(reconhecimentoLinha(linha))
    );
}

function reconhecimentoLinha(linha) {
    return linha.reconhecimento_match || null;
}

function reconhecimentoEhRecorrencia(reconhecimento) {
    if (!reconhecimento) return false;
    return reconhecimento.tipo_sugerido === 'recorrencia'
        || reconhecimento.tipo === 'recorrencia'
        || reconhecimento.origem === 'recorrencia'
        || Boolean(reconhecimento.item_despesa_id && reconhecimento.origem_alias === 'recorrencia');
}

function idRecorrenciaReconhecimento(linha) {
    const reconhecimento = reconhecimentoLinha(linha);
    if (!reconhecimentoEhRecorrencia(reconhecimento)) {
        return toIntOrNull(linha.recorrencia_id || linha.item_despesa_id);
    }
    return toIntOrNull(
        reconhecimento.item_despesa_id
        || reconhecimento.referencia_id
        || linha.recorrencia_id
        || linha.item_despesa_id
    );
}

function linhaDuplicadaPorReconhecimento(linha) {
    const reconhecimento = reconhecimentoLinha(linha);
    return reconhecimento?.tipo === 'duplicado_atual' && Number(reconhecimento.score || 0) >= 80;
}

function linhaReconhecimentoPendente(linha) {
    const reconhecimento = reconhecimentoLinha(linha);
    return Boolean(
        reconhecimento
        && Number(reconhecimento.score || 0) >= 60
        && !linha.tratar_como_novo
        && !linha.sugestao_reconhecimento_aplicada
        && !linhaRecorrenciaVinculada(linha)
        && !linha.ignorar
    );
}

function linhaReconhecimentoRecorrenciaPendente(linha) {
    return linhaReconhecimentoPendente(linha) && reconhecimentoEhRecorrencia(reconhecimentoLinha(linha));
}

function linhaNovaClassificavel(linha) {
    return linhaImportavel(linha)
        && !linhaPossivelParcelamento(linha)
        && !linhaPossivelRecorrencia(linha)
        && !linhaReconhecimentoPendente(linha);
}

function motivoConfrontoLinha(linha, tipo, parcela) {
    if (tipo === 'duplicado') {
        return linha.motivo_duplicidade || linha.duplicidade || 'Mesmo cartao, competencia, descricao e valor ja identificados.';
    }
    if (tipo === 'reconhecimento') {
        const reconhecimento = reconhecimentoLinha(linha);
        return `Score ${reconhecimento?.score || 0}: ${(reconhecimento?.motivos || []).join(', ') || 'valor/cartao/palavra-chave compativeis'}.`;
    }
    if (tipo === 'parcelamento') {
        return `Padrao de parcela ${parcela?.rotulo || ''} detectado na descricao original.`;
    }
    if (tipo === 'recorrencia') {
        const reconhecimento = reconhecimentoLinha(linha);
        if (reconhecimento) {
            return `Score ${reconhecimento.score || 0}: ${(reconhecimento.motivos || []).join(', ') || 'valor/cartao/fornecedor compativeis com recorrencia'}.`;
        }
        return 'Linha tem indicio de recorrencia nos dados disponiveis.';
    }
    if (tipo === 'erro') {
        return (linha.mensagens || linha.avisos || []).join(' | ') || 'Linha bloqueada pela validacao tecnica.';
    }
    return 'Sem alerta local. Classifique antes de importar.';
}

function montarAnaliseConfronto() {
    const grupos = {
        novos: [],
        duplicados: [],
        conhecidos: [],
        parcelamentos: [],
        recorrencias: [],
        erros: []
    };

    estado.linhasMapeadas.forEach((linha, index) => {
        const itemBase = { linha, index };
        if (linhaTratadaParcelamento(linha)) return;
        if (linhaRecorrenciaVinculada(linha)) return;
        if (linha.ignorar && !linhaDuplicada(linha) && !linhaComErro(linha)) return;

        if (linhaComErro(linha) || linhaCredito(linha)) {
            grupos.erros.push({
                ...itemBase,
                motivo: motivoConfrontoLinha(linha, 'erro')
            });
            return;
        }
        if (linhaDuplicada(linha)) {
            grupos.duplicados.push({
                ...itemBase,
                motivo: motivoConfrontoLinha(linha, 'duplicado')
            });
            return;
        }
        if (linhaDuplicadaPorReconhecimento(linha)) {
            grupos.duplicados.push({
                ...itemBase,
                reconhecimento: reconhecimentoLinha(linha),
                motivo: motivoConfrontoLinha(linha, 'reconhecimento')
            });
            return;
        }

        const parcela = detectarParcelamentoLinha(linha);
        if (parcela) {
            grupos.parcelamentos.push({
                ...itemBase,
                parcela,
                reconhecimento: reconhecimentoLinha(linha),
                motivo: motivoConfrontoLinha(linha, 'parcelamento', parcela)
            });
            return;
        }

        if (linhaReconhecimentoRecorrenciaPendente(linha)) {
            grupos.recorrencias.push({
                ...itemBase,
                reconhecimento: reconhecimentoLinha(linha),
                motivo: motivoConfrontoLinha(linha, 'recorrencia')
            });
            return;
        }

        if (linhaReconhecimentoPendente(linha)) {
            grupos.conhecidos.push({
                ...itemBase,
                reconhecimento: reconhecimentoLinha(linha),
                motivo: motivoConfrontoLinha(linha, 'reconhecimento')
            });
            return;
        }

        if (linhaPossivelRecorrencia(linha)) {
            grupos.recorrencias.push({
                ...itemBase,
                motivo: motivoConfrontoLinha(linha, 'recorrencia')
            });
            return;
        }

        if (linhaImportavel(linha)) {
            grupos.novos.push({
                ...itemBase,
                motivo: motivoConfrontoLinha(linha, 'novo')
            });
        }
    });

    return {
        ...grupos,
        totalSelecionados: estado.linhasMapeadas.filter(linhaImportavel).length,
        totalBloqueados: grupos.duplicados.length + grupos.conhecidos.length + grupos.parcelamentos.length + grupos.recorrencias.length + grupos.erros.length
    };
}

function linhasNovasConfirmaveis() {
    if (estado.analiseConfronto) {
        return estado.analiseConfronto.novos
            .map(({ linha }) => linha)
            .filter(linhaNovaClassificavel);
    }
    return estado.linhasMapeadas.filter(linhaNovaClassificavel);
}

function novasSemCategoriaDespesa() {
    return linhasNovasConfirmaveis().filter((linha) => !toIntOrNull(linha.categoria_id || linha.categoria_despesa_id));
}

function statusLinha(linha) {
    if (linhaComErro(linha)) {
        return { texto: 'Erro', classe: 'review' };
    }
    if (linhaDuplicada(linha)) {
        return { texto: 'Duplicado / já existente', classe: 'duplicate' };
    }
    if (linhaTratadaParcelamento(linha)) {
        return { texto: 'Parcelamento criado', classe: 'parcelment' };
    }
    if (linhaRecorrenciaVinculada(linha)) {
        return { texto: 'Recorrencia vinculada', classe: 'recurrence' };
    }
    if (linhaCredito(linha)) {
        return { texto: 'Ignorado', classe: 'ignored' };
    }
    if (linha.ignorar || linha.status_classificacao === 'ignorada' || linha.status === 'ignorado') {
        return { texto: 'Ignorado', classe: 'ignored' };
    }
    if (linhaImportavel(linha)) {
        return { texto: 'A importar', classe: 'valid' };
    }
    if (linha.status_classificacao === 'duplicada') {
        return { texto: 'Duplicado', classe: 'duplicate' };
    }
    if (linha.status_classificacao === 'ignorada') {
        return { texto: linha.tipo_movimento === 'credito' ? 'Crédito ignorado' : 'Ignorado', classe: 'ignored' };
    }
    if (linha.status_classificacao === 'erro') {
        return { texto: 'Erro', classe: 'review' };
    }
    if (linha.status_classificacao === 'ambigua' || linha.categoria_origem === 'ambigua') {
        return { texto: 'Ambigua', classe: 'review' };
    }
    if (linha.status_classificacao === 'categoria_despesa_pendente') {
        return { texto: 'Categoria da despesa pendente', classe: 'review' };
    }
    if (linha.status_classificacao === 'categoria_cartao_nao_vinculada') {
        return { texto: 'Sem limite no cartao', classe: 'missing' };
    }
    if (linha.status_classificacao === 'categoria_cartao_pendente') {
        return { texto: 'Mapeamento pendente', classe: 'missing' };
    }
    if (linha.status_classificacao === 'classificada') {
        return { texto: 'Classificada', classe: 'valid' };
    }
    if (linha.status === 'duplicado') {
        return { texto: 'Duplicado', classe: 'duplicate' };
    }
    if (linha.ignorar) {
        return { texto: linha.tipo_movimento === 'credito' ? 'Crédito ignorado' : 'Ignorado', classe: 'ignored' };
    }
    if (linha.status === 'revisar') {
        return { texto: 'Revisar', classe: 'review' };
    }
    if (!linha.categoria_id) {
        return { texto: 'Revisar', classe: 'review' };
    }
    if ((linha.categoria_confianca || linha.confianca_categoria) === 'baixa') {
        return { texto: 'Baixa confianca', classe: 'low-confidence' };
    }
    if (linha.categoria_sugerida_origem && !['historico', 'palavra_chave', 'manual'].includes(linha.categoria_sugerida_origem)) {
        return { texto: 'Baixa confiança', classe: 'low-confidence' };
    }
    return { texto: 'Válido', classe: 'valid' };
}

function origemCategoriaLabel(linha) {
    const origem = linha.categoria_origem || linha.categoria_sugerida_origem || '-';
    if (origem === 'manual') return 'Sugestão: manual';
    if (origem === 'historico') return 'Sugestão: histórico';
    if (origem === 'palavra_chave') return 'Sugestão: palavra-chave';
    if (origem === 'ambigua') return 'Ambígua: revise';
    if (origem === 'descricao') return 'Sugestão: descrição';
    if (origem === 'sem_sugestao') return 'Sem sugestão';
    if (origem === 'fallback' || origem === 'fallback_lote') return 'Sugestão: fallback do lote';
    return `Sugestão: ${origem}`;
}

function badgeConfianca(linha) {
    const confianca = linha.categoria_confianca || linha.confianca_categoria;
    const origem = linha.categoria_origem || linha.categoria_sugerida_origem;
    if (origem === 'manual') return '<span class="import-badge badge-manual">manual</span>';
    if (origem === 'historico') return '<span class="import-badge badge-alta">histórico</span>';
    if (origem === 'palavra_chave') {
        if (confianca === 'alta') return '<span class="import-badge badge-alta">alta</span>';
        return '<span class="import-badge badge-media">média</span>';
    }
    if (origem === 'ambigua') return '<span class="import-badge badge-revisar">revisar</span>';
    if (!confianca || confianca === 'baixa') return '<span class="import-badge badge-baixa">baixa</span>';
    return `<span class="import-badge badge-${confianca}">${escapeHtml(confianca)}</span>`;
}

function palavrasChaveEncontradas(linha) {
    const palavras = linha.palavras_chave_encontradas || [];
    if (!palavras.length) return '';
    return `<span class="import-detected-note kw-found">Palavras: ${escapeHtml(palavras.join(', '))}</span>`;
}

function categoriasCandidatasHtml(linha) {
    const origem = linha.categoria_origem || linha.categoria_sugerida_origem;
    const candidatas = linha.categorias_candidatas || [];
    if (origem !== 'ambigua' || !candidatas.length) return '';

    const labels = candidatas.slice(0, 3).map((item) => {
        const palavras = item.palavras_encontradas || [];
        return `${item.categoria_nome || item.nome || 'Categoria'}${palavras.length ? ` (${palavras.join(', ')})` : ''}`;
    });
    return `<span class="import-detected-note candidate-list">Candidatas: ${escapeHtml(labels.join(' | '))}</span>`;
}

function linhaPrecisaRevisao(linha) {
    const status = statusLinha(linha);
    return ['review', 'missing', 'low-confidence'].includes(status.classe)
        || linha.status_classificacao === 'ambigua'
        || linha.categoria_origem === 'ambigua'
        || linha.categoria_confianca === 'baixa';
}

function valorNumericoLinha(linha) {
    return parseValorNumerico(linha?.valor) || 0;
}

function formatarValorLinha(linha) {
    return formatarMoeda(valorNumericoLinha(linha));
}

function temConfrontoAtivo() {
    return Boolean(estado.analiseConfronto);
}

function linhaDuplicadaOperacional(linha) {
    return linhaDuplicada(linha) || linhaDuplicadaPorReconhecimento(linha);
}

function linhaRetiradaEfetivacao(linha) {
    return Boolean(
        linha.ignorar
        || linhaTratadaParcelamento(linha)
        || linhaRecorrenciaVinculada(linha)
        || linhaDuplicadaOperacional(linha)
        || linhaComErro(linha)
        || linhaCredito(linha)
    );
}

function motivoRetiradaCodigo(linha) {
    if (linhaRecorrenciaVinculada(linha)) return 'recorrencia_vinculada';
    if (linhaTratadaParcelamento(linha)) return 'parcelamento_tratado';
    if (linhaDuplicadaPorReconhecimento(linha)) return 'ja_existe_fatura';
    if (linhaDuplicada(linha)) return 'duplicado_fatura';
    if (linhaComErro(linha)) return 'erro_validacao';
    if (linhaCredito(linha)) return 'credito_estorno';
    if (linha.ignorar) return 'retirado_usuario';
    return 'outro_tecnico';
}

function motivoRetiradaLinha(linha) {
    const motivos = {
        retirado_usuario: 'Retirado pelo usuário',
        duplicado_fatura: 'Duplicado na fatura',
        ja_existe_fatura: 'Já existe na fatura',
        conhecida_alta_confianca: 'Conhecida com alta confiança',
        recorrencia_vinculada: 'Recorrencia vinculada',
        parcelamento_tratado: 'Parcelamento tratado',
        credito_estorno: 'Crédito/estorno',
        erro_validacao: 'Erro de validação',
        outro_tecnico: 'Outro motivo técnico'
    };
    return motivos[motivoRetiradaCodigo(linha)] || motivos.outro_tecnico;
}

function observacaoRetiradaLinha(linha) {
    const reconhecimento = reconhecimentoLinha(linha) || {};
    const parcelaCriada = linha.parcelamento_criado || {};
    const motivos = Array.isArray(reconhecimento.motivos) ? reconhecimento.motivos.join(', ') : '';

    if (linhaTratadaParcelamento(linha)) {
        const resumo = parcelaCriada.total_criados
            ? `${parcelaCriada.total_criados} parcela(s) gerada(s)`
            : 'Parcelamento criado';
        return `${resumo}${parcelaCriada.descricao ? ` · ${parcelaCriada.descricao}` : ''}`;
    }
    if (linhaRecorrenciaVinculada(linha)) {
        const recorrencia = linha.recorrencia_vinculada_info || {};
        const nome = recorrencia.nome || reconhecimento.descricao_sugerida || linha.descricao_exibida || 'recorrencia';
        return `Vinculada a ${nome} · ${formatarValorLinha(linha)}`;
    }
    if (linhaDuplicadaPorReconhecimento(linha)) {
        const score = reconhecimento.score ? `Score ${reconhecimento.score}` : 'Alta confiança';
        const sugestao = reconhecimento.descricao_sugerida || reconhecimento.descricao_match || 'match na fatura atual';
        return `${score}: ${sugestao}${motivos ? ` · ${motivos}` : ''}`;
    }
    if (linhaDuplicada(linha)) {
        return linha.motivo_duplicidade || linha.duplicidade || 'Duplicado exato ou já bloqueado pela prévia.';
    }
    if (linhaComErro(linha)) {
        return (linha.mensagens || linha.avisos || []).join(' | ') || 'Linha bloqueada pela validação técnica.';
    }
    if (linhaCredito(linha)) {
        return 'Crédito ou estorno não entra como nova despesa.';
    }
    if (linha.ignorar) {
        return 'Retirado manualmente antes da efetivação.';
    }
    return 'Linha fora da efetivação por regra técnica.';
}

function detalheRetiradaLinha(linha) {
    const reconhecimento = reconhecimentoLinha(linha) || {};
    return [
        `Motivo: ${motivoRetiradaLinha(linha)}`,
        `Descrição importada: ${descricaoOriginalLinha(linha) || '-'}`,
        `Valor importado: ${formatarValorLinha(linha)}`,
        linha.data_compra ? `Data: ${linha.data_compra}` : null,
        reconhecimento.descricao_sugerida ? `Match encontrado: ${reconhecimento.descricao_sugerida}` : null,
        reconhecimento.score ? `Score/confiança: ${reconhecimento.score} (${reconhecimento.confianca || 'sem confiança'})` : null,
        reconhecimento.competencia_referencia ? `Competência do match: ${reconhecimento.competencia_referencia}` : null,
        reconhecimento.valor_referencia ? `Valor do match: ${formatarMoeda(reconhecimento.valor_referencia)}` : null,
        `Observação: ${observacaoRetiradaLinha(linha)}`
    ].filter(Boolean).join('\n');
}

function linhaRestauravel(linha) {
    return Boolean(
        linha.ignorar
        && !linhaTratadaParcelamento(linha)
        && !linhaRecorrenciaVinculada(linha)
        && !linhaDuplicadaOperacional(linha)
        && !linhaComErro(linha)
        && !linhaCredito(linha)
    );
}

function obterInfoOperacional(linha, index) {
    const confronto = temConfrontoAtivo();
    const reconhecimento = reconhecimentoLinha(linha);
    const parcela = detectarParcelamentoLinha(linha);

    if (!confronto) {
        return {
            linha,
            index,
            status: 'A importar',
            classe: 'valid',
            tipo: parcela ? 'Parcelamento' : '—',
            filtro: 'pendentes',
            sugestao: parcela ? sugestaoParcelamentoLinha(parcela) : '—',
            descricaoEditavel: false,
            categoriaEditavel: false,
            parcela,
            reconhecimento
        };
    }

    if (parcela) {
        return {
            linha,
            index,
            status: 'Parcelado',
            classe: 'parcelment',
            tipo: 'Parcelamento',
            filtro: 'parcelados',
            sugestao: sugestaoParcelamentoLinha(parcela),
            descricaoEditavel: false,
            categoriaEditavel: false,
            parcela,
            reconhecimento
        };
    }

    if (linhaReconhecimentoRecorrenciaPendente(linha)) {
        const confiancaReconhecimento = reconhecimento?.confianca || 'media';
        return {
            linha,
            index,
            status: confiancaReconhecimento === 'alta' ? 'Recorrência' : 'Revisar',
            classe: confiancaReconhecimento === 'alta' ? 'recurrence' : 'review',
            tipo: 'Recorrência',
            filtro: 'recorrencias',
            sugestao: reconhecimento?.descricao_sugerida || 'Possível recorrência',
            descricaoEditavel: false,
            categoriaEditavel: false,
            parcela,
            reconhecimento
        };
    }

    if (linhaReconhecimentoPendente(linha)) {
        const confiancaReconhecimento = reconhecimento?.confianca || 'media';
        return {
            linha,
            index,
            status: confiancaReconhecimento === 'alta' ? 'Conhecida' : 'Revisar',
            classe: confiancaReconhecimento === 'alta' ? 'known' : 'review',
            tipo: reconhecimento?.tipo_sugerido === 'recorrencia'
                ? 'Recorrência'
                : (reconhecimento?.tipo_sugerido === 'parcelamento' ? 'Parcelamento conhecido' : 'Despesa conhecida'),
            filtro: 'conhecidas',
            sugestao: reconhecimento?.descricao_sugerida || 'Possível conhecida',
            descricaoEditavel: false,
            categoriaEditavel: false,
            parcela,
            reconhecimento
        };
    }

    if (linhaPossivelRecorrencia(linha)) {
        return {
            linha,
            index,
            status: 'Recorrência',
            classe: 'recurrence',
            tipo: 'Recorrência',
            filtro: 'recorrencias',
            sugestao: linha.descricao_exibida || linha.descricao || 'Possível recorrência',
            descricaoEditavel: false,
            categoriaEditavel: false,
            parcela,
            reconhecimento
        };
    }

    return {
        linha,
        index,
        status: 'Novo',
        classe: 'valid',
        tipo: 'Novo',
        filtro: 'novos',
        sugestao: '—',
        descricaoEditavel: true,
        categoriaEditavel: true,
        parcela,
        reconhecimento
    };
}

function linhasProcessamentoBase() {
    return estado.linhasMapeadas
        .map((linha, index) => ({ linha, index }))
        .filter(({ linha }) => !linhaRetiradaEfetivacao(linha))
        .map(({ linha, index }) => obterInfoOperacional(linha, index));
}

function linhasRetiradasBase() {
    return estado.linhasMapeadas
        .map((linha, index) => ({ linha, index }))
        .filter(({ linha }) => linhaRetiradaEfetivacao(linha));
}

function passaFiltroPrincipal(item, filtro = estado.filtroPrincipal) {
    if (filtro === 'todos') return true;
    if (filtro === 'conhecidas' || filtro === 'possiveis_conhecidas') return item.filtro === 'conhecidas';
    if (filtro === 'parcelados' || filtro === 'criar_parcelamento') return item.filtro === 'parcelados';
    if (filtro === 'novos' || filtro === 'criar_despesa') return item.filtro === 'novos';
    if (filtro === 'recorrencias') return item.filtro === 'recorrencias';
    if (filtro === 'duplicados') return linhaDuplicadaOperacional(item.linha);
    if (filtro === 'pendentes') return item.filtro !== 'novos' || !toIntOrNull(item.linha.categoria_id || item.linha.categoria_despesa_id);
    if (filtro === 'usar_sugestao') return item.filtro === 'conhecidas';
    return true;
}

function passaFiltroRetirados(item, filtro = estado.filtroRetirados) {
    const codigo = motivoRetiradaCodigo(item.linha);
    if (filtro === 'todos') return true;
    if (filtro === 'usuario') return codigo === 'retirado_usuario';
    if (filtro === 'existente') return codigo === 'ja_existe_fatura';
    if (filtro === 'duplicado') return codigo === 'duplicado_fatura';
    if (filtro === 'parcelamento') return codigo === 'parcelamento_tratado';
    if (filtro === 'recorrencia') return codigo === 'recorrencia_vinculada';
    if (filtro === 'bloqueado') return linhaComErro(item.linha) || linhaCredito(item.linha);
    if (filtro === 'credito') return linhaCredito(item.linha);
    if (filtro === 'erro') return linhaComErro(item.linha);
    return true;
}

function linhasProcessamentoFiltradas() {
    return linhasProcessamentoBase().filter((item) => passaFiltroPrincipal(item));
}

function linhasRetiradasFiltradas() {
    return linhasRetiradasBase().filter((item) => passaFiltroRetirados(item));
}

function contarFiltroPrincipal(filtro) {
    return linhasProcessamentoBase().filter((item) => passaFiltroPrincipal(item, filtro)).length;
}

function contarFiltroRetirados(filtro) {
    return linhasRetiradasBase().filter((item) => passaFiltroRetirados(item, filtro)).length;
}

function alterarFiltroPrincipal(filtro) {
    estado.filtroPrincipal = filtro || 'todos';
    estado.paginaPrincipal = 1;
    estado.linhasSelecionadas = new Set();
    renderizarEditorPrePersistencia();
}

function alterarFiltroRetirados(filtro) {
    estado.filtroRetirados = filtro || 'todos';
    estado.paginaRetirados = 1;
    renderizarTabelaRetirados();
    renderizarFiltroAvancado('retirados');
}

function alternarFiltroAvancado(tipo) {
    const id = tipo === 'retirados' ? 'retiradosFilterPanel' : 'principalFilterPanel';
    const painel = document.getElementById(id);
    if (!painel) return;
    renderizarFiltroAvancado(tipo);
    painel.hidden = !painel.hidden;
}

function renderizarFiltroAvancado(tipo) {
    const principal = tipo !== 'retirados';
    const painel = document.getElementById(principal ? 'principalFilterPanel' : 'retiradosFilterPanel');
    if (!painel) return;

    const filtros = principal
        ? [
            ['todos', 'Todos', contarFiltroPrincipal('todos')],
            ['conhecidas', 'Conhecidas', contarFiltroPrincipal('conhecidas')],
            ['possiveis_conhecidas', 'Possíveis conhecidas', contarFiltroPrincipal('possiveis_conhecidas')],
            ['parcelados', 'Parcelados', contarFiltroPrincipal('parcelados')],
            ['novos', 'Novos', contarFiltroPrincipal('novos')],
            ['recorrencias', 'Recorrências', contarFiltroPrincipal('recorrencias')],
            ['duplicados', 'Duplicados', contarFiltroPrincipal('duplicados')],
            ['pendentes', 'Pendentes de ação', contarFiltroPrincipal('pendentes')],
            ['criar_parcelamento', 'Criar parcelamento', contarFiltroPrincipal('criar_parcelamento')],
            ['criar_despesa', 'Criar despesa', contarFiltroPrincipal('criar_despesa')],
            ['usar_sugestao', 'Usar sugestão', contarFiltroPrincipal('usar_sugestao')]
        ]
        : [
            ['todos', 'Todos', contarFiltroRetirados('todos')],
            ['usuario', 'Retirado pelo usuário', contarFiltroRetirados('usuario')],
            ['existente', 'Já existe na fatura', contarFiltroRetirados('existente')],
            ['duplicado', 'Duplicado na fatura', contarFiltroRetirados('duplicado')],
            ['parcelamento', 'Parcelamento tratado', contarFiltroRetirados('parcelamento')],
            ['recorrencia', 'Recorrencia vinculada', contarFiltroRetirados('recorrencia')],
            ['bloqueado', 'Bloqueado', contarFiltroRetirados('bloqueado')],
            ['credito', 'Crédito/estorno', contarFiltroRetirados('credito')],
            ['erro', 'Erro', contarFiltroRetirados('erro')]
        ];

    const filtroAtivo = principal ? estado.filtroPrincipal : estado.filtroRetirados;
    const handler = principal ? 'alterarFiltroPrincipal' : 'alterarFiltroRetirados';
    painel.innerHTML = filtros.map(([id, label, total]) => `
        <button class="import-review-filter ${filtroAtivo === id ? 'is-active' : ''}" type="button" onclick="${handler}('${id}')">
            ${escapeHtml(label)} <span>${total}</span>
        </button>
    `).join('');
}

function paginaTabela(tipo) {
    return tipo === 'retirados' ? estado.paginaRetirados : estado.paginaPrincipal;
}

function definirPaginaTabela(tipo, pagina) {
    if (tipo === 'retirados') estado.paginaRetirados = pagina;
    else estado.paginaPrincipal = pagina;
}

function paginarItens(itens, tipo) {
    const porPagina = estado.linhasPorPagina;
    const totalPaginas = Math.max(1, Math.ceil(itens.length / porPagina));
    const pagina = Math.min(Math.max(1, paginaTabela(tipo)), totalPaginas);
    definirPaginaTabela(tipo, pagina);
    const inicio = (pagina - 1) * porPagina;
    return {
        itens: itens.slice(inicio, inicio + porPagina),
        pagina,
        totalPaginas,
        inicio,
        fim: Math.min(inicio + porPagina, itens.length),
        total: itens.length
    };
}

function alterarPaginaTabela(tipo, pagina) {
    definirPaginaTabela(tipo, Number(pagina) || 1);
    if (tipo === 'retirados') renderizarTabelaRetirados();
    else renderizarEditorPrePersistencia();
}

function renderizarPaginacaoTabela(tipo, paginaInfo) {
    const paginas = Array.from({ length: paginaInfo.totalPaginas }, (_, idx) => idx + 1)
        .filter((pagina) => paginaInfo.totalPaginas <= 5 || Math.abs(pagina - paginaInfo.pagina) <= 2 || pagina === 1 || pagina === paginaInfo.totalPaginas);
    const intervalo = paginaInfo.total
        ? `${paginaInfo.inicio + 1}-${paginaInfo.fim} de ${paginaInfo.total}`
        : '0-0 de 0';

    return `
        <div class="import-pagination">
            <span>${escapeHtml(intervalo)}</span>
            <div class="import-page-buttons">
                <button type="button" onclick="alterarPaginaTabela('${tipo}', 1)" ${paginaInfo.pagina === 1 ? 'disabled' : ''}>«</button>
                <button type="button" onclick="alterarPaginaTabela('${tipo}', ${paginaInfo.pagina - 1})" ${paginaInfo.pagina === 1 ? 'disabled' : ''}>‹</button>
                ${paginas.map((pagina) => `
                    <button type="button" class="${pagina === paginaInfo.pagina ? 'is-active' : ''}" onclick="alterarPaginaTabela('${tipo}', ${pagina})">${pagina}</button>
                `).join('')}
                <button type="button" onclick="alterarPaginaTabela('${tipo}', ${paginaInfo.pagina + 1})" ${paginaInfo.pagina === paginaInfo.totalPaginas ? 'disabled' : ''}>›</button>
                <button type="button" onclick="alterarPaginaTabela('${tipo}', ${paginaInfo.totalPaginas})" ${paginaInfo.pagina === paginaInfo.totalPaginas ? 'disabled' : ''}>»</button>
            </div>
            <span>10 por página</span>
        </div>
    `;
}

function linhasPreviaFiltradas() {
    return linhasProcessamentoFiltradas();
}

function contarFiltroPrevia(filtro) {
    const anterior = estado.filtroPrevia;
    estado.filtroPrevia = filtro;
    const total = linhasPreviaFiltradas().length;
    estado.filtroPrevia = anterior;
    return total;
}

function alterarFiltroPrevia(filtro) {
    estado.filtroPrevia = filtro || 'a_importar';
    estado.linhasSelecionadas = new Set();
    renderizarEditorPrePersistencia();
}

function alternarSelecaoLinha(index, marcado) {
    if (marcado) estado.linhasSelecionadas.add(Number(index));
    else estado.linhasSelecionadas.delete(Number(index));
    renderizarEditorPrePersistencia();
}

function alternarSelecaoTodasPrevia(marcado) {
    const visiveis = linhasPreviaFiltradas().map(({ index }) => Number(index));
    if (marcado) visiveis.forEach((index) => estado.linhasSelecionadas.add(index));
    else visiveis.forEach((index) => estado.linhasSelecionadas.delete(index));
    renderizarEditorPrePersistencia();
}

function indicesSelecionados() {
    return [...estado.linhasSelecionadas]
        .map((index) => Number(index))
        .filter((index) => estado.linhasMapeadas[index]);
}

function renderizarBarraRevisaoLote(linhasFiltradas) {
    const selecionadas = indicesSelecionados().length;
    const filtros = [
        ['a_importar', 'A importar', contarFiltroPrevia('a_importar')],
        ['ignorados', 'Ignorados', contarFiltroPrevia('ignorados')],
        ['todas', 'Todos', estado.linhasMapeadas.length],
        ['duplicadas', 'Duplicados', contarFiltroPrevia('duplicadas')]
    ].map(([id, label, total]) => `
        <button class="import-review-filter ${estado.filtroPrevia === id ? 'is-active' : ''}" type="button" onclick="alterarFiltroPrevia('${id}')">
            ${escapeHtml(label)} <span>${total}</span>
        </button>
    `).join('');

    return `
        <div class="import-review-toolbar">
            <div class="import-review-summary">
                <strong>Triagem</strong>
                <span>${selecionadas} selecionada${selecionadas === 1 ? '' : 's'} de ${linhasFiltradas.length} visiveis</span>
            </div>
            <div class="import-review-filters">${filtros}</div>
            <div class="import-review-actions">
                <button class="btn btn-outline-danger btn-sm" type="button" onclick="ignorarLinhasSelecionadas()">Ignorar lançamento</button>
                <button class="btn btn-secondary btn-sm" type="button" onclick="restaurarLinhasSelecionadas()">Restaurar</button>
            </div>
        </div>
    `;
}

function renderizarEditorPrePersistenciaLegado() {
    const container = document.getElementById('editorPrePersistencia');
    if (!container) return;

    const linhas = estado.linhasMapeadas;
    if (!linhas.length) {
        container.innerHTML = '';
        atualizarResumoPainel();
        return;
    }

    const previaContainer = document.getElementById('previaContainer');
    if (previaContainer) previaContainer.innerHTML = '';
    const linhasFiltradas = linhasPreviaFiltradas();
    const indicesVisiveis = linhasFiltradas.map(({ index }) => Number(index));
    const todasVisiveisSelecionadas = indicesVisiveis.length > 0
        && indicesVisiveis.every((index) => estado.linhasSelecionadas.has(index));
    container.innerHTML = `
        <div class="import-preview-shell">
            ${renderizarBarraRevisaoLote(linhasFiltradas)}
            <div class="import-preview-table-wrap">
                <table class="import-preview-table">
                    <thead>
                        <tr>
                            <th class="import-row-check">
                                <input type="checkbox" ${todasVisiveisSelecionadas ? 'checked' : ''} onchange="alternarSelecaoTodasPrevia(this.checked)" aria-label="Selecionar linhas visiveis">
                            </th>
                            <th>Data</th>
                            <th>Descrição original</th>
                            <th>Valor</th>
                            <th>Status</th>
                            <th>Ação</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${linhasFiltradas.length
                            ? linhasFiltradas.map(({ linha, index }) => renderizarLinhaPrevia(linha, index)).join('')
                            : '<tr><td colspan="6"><div class="import-empty-state compact">Nenhuma linha encontrada para este filtro.</div></td></tr>'}
                    </tbody>
                </table>
            </div>
            <div class="import-preview-footer">
                Mostrando ${linhasFiltradas.length} de ${estado.csvData?.total_linhas || linhas.length} lançamentos
            </div>
        </div>
    `;

    atualizarResumoPainel();
}

function renderizarEditorPrePersistencia() {
    const container = document.getElementById('editorPrePersistencia');
    if (!container) return;

    const previaContainer = document.getElementById('previaContainer');
    if (previaContainer) previaContainer.innerHTML = '';
    renderizarFiltroAvancado('principal');

    const linhasFiltradas = linhasProcessamentoFiltradas();
    const paginaInfo = paginarItens(linhasFiltradas, 'principal');
    const indicesVisiveis = paginaInfo.itens.map(({ index }) => Number(index));
    const todasVisiveisSelecionadas = indicesVisiveis.length > 0
        && indicesVisiveis.every((index) => estado.linhasSelecionadas.has(index));

    container.innerHTML = `
        <div class="import-preview-shell operational">
            <div class="import-preview-table-wrap operational">
                <table class="import-preview-table import-operational-table">
                    <thead>
                        <tr>
                            <th class="import-row-check">
                                <input type="checkbox" ${todasVisiveisSelecionadas ? 'checked' : ''} onchange="alternarSelecaoTodasPrevia(this.checked)" aria-label="Selecionar linhas visíveis">
                            </th>
                            <th>Status</th>
                            <th>Data</th>
                            <th>Descrição original</th>
                            <th>Valor</th>
                            <th>Tipo detectado</th>
                            <th>Sugestão</th>
                            <th>Descrição amigável</th>
                            <th>Categoria da despesa</th>
                            <th>Ação</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${paginaInfo.itens.length
                            ? paginaInfo.itens.map((item) => renderizarLinhaOperacional(item)).join('')
                            : '<tr><td colspan="10"><div class="import-empty-state compact">Nenhum lançamento em processamento para este filtro.</div></td></tr>'}
                    </tbody>
                </table>
            </div>
            ${renderizarPaginacaoTabela('principal', paginaInfo)}
        </div>
    `;

    renderizarTabelaRetirados();
    renderizarKpisImportacao();
    atualizarControlesImportacao();
}

function renderizarLinhaOperacional(item) {
    const { linha, index } = item;
    const descricaoOriginal = descricaoOriginalLinha(linha);
    const descricaoAmigavel = linha.descricao_exibida || linha.descricao || descricaoOriginal;
    const categoriaId = linha.categoria_id || linha.categoria_despesa_id;
    const avisoCategoriaCartao = avisoCategoriaCartaoMapeamentoLinha(linha);

    return `
        <tr>
            <td class="import-row-check">
                <input type="checkbox" ${estado.linhasSelecionadas.has(Number(index)) ? 'checked' : ''} onchange="alternarSelecaoLinha(${index}, this.checked)" aria-label="Selecionar linha ${index + 1}">
            </td>
            <td><span class="import-status-pill ${item.classe}">${escapeHtml(item.status)}</span></td>
            <td><span class="import-raw-text">${escapeHtml(linha.data_compra || '-')}</span></td>
            <td class="import-description-cell one-line">
                <span class="import-raw-description" title="${escapeAttr(descricaoOriginal)}">${escapeHtml(descricaoOriginal || '-')}</span>
            </td>
            <td><span class="import-raw-value">${formatarValorLinha(linha)}</span></td>
            <td>${escapeHtml(item.tipo || '—')}</td>
            <td class="import-description-cell one-line">
                <span title="${escapeAttr(item.sugestao || '—')}">${escapeHtml(item.sugestao || '—')}</span>
            </td>
            <td class="import-operational-edit-cell">
                ${item.descricaoEditavel ? `
                    <input class="form-control form-control-sm import-inline-input" type="text" value="${escapeAttr(descricaoAmigavel)}" onchange="atualizarLinhaClassificacao(${index}, 'descricao_exibida', this.value)">
                ` : '<span class="import-muted-cell">—</span>'}
            </td>
            <td class="import-category-cell">
                ${item.categoriaEditavel ? `
                    <select class="form-control form-control-sm import-inline-select" onchange="atualizarLinhaClassificacao(${index}, 'categoria_id', this.value)">
                        ${opcoesCategoriaSelect(categoriaId)}
                    </select>
                    ${avisoCategoriaCartao ? `<span class="import-detected-note">${escapeHtml(avisoCategoriaCartao)}</span>` : ''}
                ` : '<span class="import-muted-cell">—</span>'}
            </td>
            <td>${renderizarAcoesLinhaOperacional(item)}</td>
        </tr>
    `;
}

function renderizarAcoesLinhaOperacional(item) {
    const { linha, index } = item;
    const confronto = temConfrontoAtivo();
    const categoriaOk = toIntOrNull(linha.categoria_id || linha.categoria_despesa_id);

    // Sem confronto: triagem simples — apenas Retirar disponível
    if (!confronto) {
        return `<div class="row-actions operational">
            ${iconeBotaoAcao('success', 'check', 'Usar sugestão', null, true)}
            ${iconeBotaoAcao('parcel', 'parcel', 'Criar parcelamento', null, true)}
            ${iconeBotaoAcao('danger', 'trash', 'Retirar', `alternarIgnorarLinha(${index})`)}
        </div>`;
    }

    if (item.filtro === 'conhecidas') {
        return `<div class="row-actions operational">
            ${iconeBotaoAcao('success', 'check', 'Usar sugestão', `usarSugestaoReconhecimento(${index})`)}
            ${iconeBotaoAcao('neutral', 'new', 'Tratar como novo', `tratarReconhecimentoComoNovo(${index})`)}
            ${iconeBotaoAcao('danger', 'trash', 'Retirar', `ignorarReconhecimento(${index})`)}
        </div>`;
    }

    if (item.filtro === 'parcelados') {
        return `<div class="row-actions operational">
            ${iconeBotaoAcao('success', 'check', 'Usar sugestão', null, true)}
            ${iconeBotaoAcao('parcel', 'parcel', 'Criar parcelamento', `abrirModalParcelamento(${index})`)}
            ${iconeBotaoAcao('danger', 'trash', 'Retirar', `alternarIgnorarLinha(${index})`)}
        </div>`;
    }

    if (item.filtro === 'recorrencias') {
        const temSugestao = Boolean(item.reconhecimento);
        const recorrenciaId = idRecorrenciaReconhecimento(linha);
        return `<div class="row-actions operational">
            ${iconeBotaoAcao('success', 'check', 'Usar sugestão', temSugestao ? `usarSugestaoReconhecimento(${index})` : null, !temSugestao)}
            ${iconeBotaoAcao('success', 'link', 'Vincular recorrencia', recorrenciaId ? `vincularRecorrenciaImportada(${index})` : null, !recorrenciaId)}
            ${iconeBotaoAcao('neutral', 'new', 'Tratar como novo', `tratarReconhecimentoComoNovo(${index})`)}
            ${iconeBotaoAcao('danger', 'trash', 'Retirar', `alternarIgnorarLinha(${index})`)}
        </div>`;
    }

    // novos / default
    return `<div class="row-actions operational">
        ${iconeBotaoAcao('primary', 'check', 'Criar despesa', 'finalizarImportacao()', !categoriaOk)}
        ${iconeBotaoAcao('parcel', 'parcel', 'Criar parcelamento', null, true)}
        ${iconeBotaoAcao('danger', 'trash', 'Retirar', `alternarIgnorarLinha(${index})`)}
    </div>`;
}

function iconeBotaoAcao(classe, icone, titulo, acao, desabilitado = false) {
    const classeBotao = classe ? ` ${classe}` : '';
    const onclickAttr = acao && !desabilitado ? ` onclick="${acao}"` : '';
    const titleAttr = titulo ? ` title="${escapeAttr(titulo)}" aria-label="${escapeAttr(titulo)}"` : '';
    return `<button class="row-action-icon import-row-icon${classeBotao}" type="button"${onclickAttr}${titleAttr} ${desabilitado ? 'disabled' : ''}>${iconSvg(icone)}</button>`;
}

function botaoOperacional(classe, texto, icone, acao, desabilitado = false) {
    const classeBotao = classe ? ` ${classe}` : '';
    return `
        <button class="row-action-button import-row-action${classeBotao}" type="button" onclick="${acao}" ${desabilitado ? 'disabled' : ''}>
            ${icone ? iconSvg(icone) : ''}
            <span>${escapeHtml(texto)}</span>
        </button>
    `;
}

function renderizarLinhaPrevia(linha, index) {
    const status = statusLinha(linha);
    const tratadaParcelamento = linhaTratadaParcelamento(linha);
    const bloqueada = linhaBloqueadaTecnica(linha) || tratadaParcelamento;
    const detalheOrigem = [linha.cartao_final ? `Cartão ${linha.cartao_final}` : null, linha.grupo]
        .filter(Boolean)
        .join(' | ');
    const selecionada = estado.linhasSelecionadas.has(Number(index));
    const descricaoOriginal = linha.descricao_original || linha.descricao || linha.descricao_exibida || '';
    const textoAcao = tratadaParcelamento ? 'Tratado' : (linha.ignorar ? 'Restaurar' : 'Ignorar lançamento');
    const tituloAcao = bloqueada
        ? (tratadaParcelamento ? 'Linha ja transformada em parcelamento' : 'Linha protegida pela regra técnica da importação')
        : textoAcao;

    return `
        <tr class="${linha.ignorar ? 'is-ignored' : ''}">
            <td class="import-row-check">
                <input type="checkbox" ${selecionada ? 'checked' : ''} onchange="alternarSelecaoLinha(${index}, this.checked)" aria-label="Selecionar linha ${index + 1}">
            </td>
            <td>
                <span class="import-raw-text">${escapeHtml(linha.data_compra || '-')}</span>
            </td>
            <td class="import-description-cell">
                <span class="import-raw-description" title="${escapeAttr(descricaoOriginal)}">${escapeHtml(descricaoOriginal || '-')}</span>
                ${detalheOrigem ? `<span class="import-detected-note">${escapeHtml(detalheOrigem)}</span>` : ''}
            </td>
            <td>
                <span class="import-raw-value">${formatarMoeda(linha.valor)}</span>
            </td>
            <td>
                <span class="import-status-pill ${status.classe}">${escapeHtml(status.texto)}</span>
            </td>
            <td>
                <div class="row-actions">
                    <button class="row-action-button import-row-action ${linha.ignorar ? 'success' : 'danger'}" type="button" onclick="alternarIgnorarLinha(${index})" title="${escapeAttr(tituloAcao)}" aria-label="${escapeAttr(textoAcao)}" ${bloqueada ? 'disabled' : ''}>
                        ${iconSvg(linha.ignorar ? 'undo' : 'trash')}
                        <span>${escapeHtml(textoAcao)}</span>
                    </button>
                </div>
            </td>
        </tr>
    `;
}

function renderizarConfrontoClassificacaoLegado() {
    const container = document.getElementById('confrontoContainer');
    if (!container) return;

    const analise = estado.analiseConfronto;
    if (!analise) {
        container.innerHTML = '';
        return;
    }

    const totalAnalisado = analise.novos.length
        + analise.duplicados.length
        + analise.conhecidos.length
        + analise.parcelamentos.length
        + analise.recorrencias.length
        + analise.erros.length;
    const pendentesCategoria = novasSemCategoriaDespesa().length;

    container.innerHTML = `
        <div class="import-confront-shell">
            <div class="import-confront-header">
                <div>
                    <strong>Confronto pos-triagem</strong>
                    <span>${totalAnalisado} lancamento${totalAnalisado === 1 ? '' : 's'} analisado${totalAnalisado === 1 ? '' : 's'} antes da classificacao.</span>
                </div>
                <div class="import-confront-metrics" aria-label="Resumo do confronto">
                    <span>Novos <strong>${analise.novos.length}</strong></span>
                    <span>Duplicados <strong>${analise.duplicados.length}</strong></span>
                    <span>Conhecidos <strong>${analise.conhecidos.length}</strong></span>
                    <span>Parcelamentos <strong>${analise.parcelamentos.length}</strong></span>
                    <span>Recorrencias <strong>${analise.recorrencias.length}</strong></span>
                </div>
            </div>
            ${pendentesCategoria ? `
                <div class="import-feedback warning">
                    <strong>Classificacao pendente.</strong>
                    ${pendentesCategoria} lancamento${pendentesCategoria === 1 ? '' : 's'} novo${pendentesCategoria === 1 ? '' : 's'} precisa${pendentesCategoria === 1 ? '' : 'm'} de categoria da despesa antes da confirmacao.
                </div>
            ` : ''}
            ${!analise.novos.length ? `
                <div class="import-feedback warning">
                    Nenhum lancamento novo importavel apos o confronto. Duplicados, possiveis parcelamentos e recorrencias ficam fora da confirmacao deste MVP.
                </div>
            ` : ''}
            ${renderizarGrupoNovosConfronto(analise.novos)}
            ${renderizarGrupoAlertaConfronto('Possiveis duplicados / ja existentes', analise.duplicados, 'duplicate')}
            ${renderizarGrupoConhecidosConfronto(analise.conhecidos)}
            ${renderizarGrupoParcelamentosConfronto(analise.parcelamentos)}
            ${renderizarGrupoAlertaConfronto('Possiveis recorrencias', analise.recorrencias, 'recurrence')}
            ${renderizarGrupoAlertaConfronto('Bloqueados por validacao', analise.erros, 'review')}
        </div>
    `;

    atualizarResumoPainel();
}

function renderizarConfrontoClassificacao() {
    const confronto = document.getElementById('confrontoContainer');
    if (confronto) confronto.innerHTML = '';
    renderizarEditorPrePersistencia();
    renderizarTabelaRetirados();
    renderizarKpisImportacao();
    atualizarResumoPainel();
}

function renderizarGrupoNovosConfronto(itens) {
    if (!itens.length) return '';

    return `
        <section class="import-confront-group">
            <div class="import-confront-group-title">
                <strong>Lancamentos novos para classificar</strong>
                <span>Somente este grupo recebe categoria nesta etapa.</span>
            </div>
            <div class="import-preview-table-wrap">
                <table class="import-preview-table import-confront-table">
                    <thead>
                        <tr>
                            <th>Data</th>
                            <th>Descricao original</th>
                            <th>Descricao amigavel</th>
                            <th>Valor</th>
                            <th>Categoria da despesa</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${itens.map(({ linha, index }) => renderizarLinhaNovoConfronto(linha, index)).join('')}
                    </tbody>
                </table>
            </div>
        </section>
    `;
}

function renderizarLinhaNovoConfronto(linha, index) {
    const descricaoOriginal = descricaoOriginalLinha(linha);
    const descricaoAmigavel = linha.descricao_exibida || linha.descricao || descricaoOriginal;
    const avisoCategoriaCartao = avisoCategoriaCartaoMapeamentoLinha(linha);
    return `
        <tr>
            <td>${escapeHtml(linha.data_compra || '-')}</td>
            <td class="import-description-cell">
                <span class="import-raw-description" title="${escapeAttr(descricaoOriginal)}">${escapeHtml(descricaoOriginal || '-')}</span>
            </td>
            <td>
                <input class="form-control form-control-sm" type="text" value="${escapeAttr(descricaoAmigavel)}" onchange="atualizarLinhaClassificacao(${index}, 'descricao_exibida', this.value)">
            </td>
            <td>${formatarMoeda(linha.valor)}</td>
            <td class="import-category-cell">
                <select class="form-control form-control-sm" onchange="atualizarLinhaClassificacao(${index}, 'categoria_id', this.value)">
                    ${opcoesCategoriaSelect(linha.categoria_id || linha.categoria_despesa_id)}
                </select>
                ${avisoCategoriaCartao ? `<span class="import-detected-note">${escapeHtml(avisoCategoriaCartao)}</span>` : ''}
            </td>
        </tr>
    `;
}

function renderizarGrupoConhecidosConfronto(itens) {
    if (!itens.length) return '';

    return `
        <section class="import-confront-group is-alert">
            <div class="import-confront-group-title">
                <strong>Possiveis conhecidos / assinaturas</strong>
                <span>Revise antes de aplicar sugestao ou importar como novo.</span>
            </div>
            <div class="import-preview-table-wrap">
                <table class="import-preview-table import-confront-table">
                    <thead>
                        <tr>
                            <th>Data</th>
                            <th>Descricao original</th>
                            <th>Valor</th>
                            <th>Sugestao</th>
                            <th>Confianca</th>
                            <th>Acoes</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${itens.map(({ linha, index, reconhecimento, motivo }) => renderizarLinhaConhecidoConfronto(linha, index, reconhecimento, motivo)).join('')}
                    </tbody>
                </table>
            </div>
        </section>
    `;
}

function renderizarLinhaConhecidoConfronto(linha, index, reconhecimento, motivo) {
    const descricaoOriginal = descricaoOriginalLinha(linha);
    const sugestao = reconhecimento?.descricao_sugerida || 'Despesa conhecida';
    const keyword = [reconhecimento?.keyword_principal, reconhecimento?.keyword_secundaria]
        .filter(Boolean)
        .join(' / ');
    return `
        <tr>
            <td>${escapeHtml(linha.data_compra || '-')}</td>
            <td class="import-description-cell">
                <span class="import-raw-description">${escapeHtml(descricaoOriginal || '-')}</span>
                ${keyword ? `<span class="import-detected-note">Palavra-chave: ${escapeHtml(keyword)}</span>` : ''}
            </td>
            <td>${formatarMoeda(linha.valor)}</td>
            <td class="import-description-cell">
                <span class="import-raw-description">${escapeHtml(sugestao)}</span>
                <span class="import-detected-note">${escapeHtml(motivo || '')}</span>
            </td>
            <td>
                <span class="import-status-pill known">${escapeHtml((reconhecimento?.confianca || 'media').toUpperCase())} ${escapeHtml(reconhecimento?.score || '')}</span>
            </td>
            <td>
                <div class="row-actions">
                    <button class="row-action-button import-row-action success" type="button" onclick="usarSugestaoReconhecimento(${index})">
                        ${iconSvg('check')}
                        <span>Usar sugestao</span>
                    </button>
                    <button class="row-action-button import-row-action" type="button" onclick="tratarReconhecimentoComoNovo(${index})">
                        <span>Tratar como novo</span>
                    </button>
                    <button class="row-action-button import-row-action danger" type="button" onclick="ignorarReconhecimento(${index})">
                        ${iconSvg('trash')}
                        <span>Ignorar</span>
                    </button>
                </div>
            </td>
        </tr>
    `;
}

function renderizarGrupoParcelamentosConfronto(itens) {
    if (!itens.length) return '';

    return `
        <section class="import-confront-group is-alert">
            <div class="import-confront-group-title">
                <strong>Possiveis parcelamentos</strong>
                <span>Confirme explicitamente antes de gerar parcelas futuras.</span>
            </div>
            <div class="import-preview-table-wrap">
                <table class="import-preview-table import-confront-table">
                    <thead>
                        <tr>
                            <th>Data</th>
                            <th>Descricao original</th>
                            <th>Valor da parcela</th>
                            <th>Parcela</th>
                            <th>Status</th>
                            <th>Acao</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${itens.map(({ linha, index, parcela }) => `
                            <tr>
                                <td>${escapeHtml(linha.data_compra || '-')}</td>
                                <td class="import-description-cell">
                                    <span class="import-raw-description">${escapeHtml(descricaoOriginalLinha(linha) || '-')}</span>
                                    <span class="import-detected-note">Padrao detectado: ${escapeHtml(parcela?.padraoDetectado || parcela?.rotulo || '-')}</span>
                                </td>
                                <td>${formatarMoeda(linha.valor)}</td>
                                <td>${escapeHtml(parcela?.rotulo || '-')}</td>
                                <td><span class="import-status-pill parcelment">Possivel parcelamento</span></td>
                                <td>
                                    <button class="row-action-button import-row-action success" type="button" onclick="abrirModalParcelamento(${index})">
                                        ${iconSvg('check')}
                                        <span>Criar parcelamento</span>
                                    </button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </section>
    `;
}

function renderizarGrupoAlertaConfronto(titulo, itens, classe) {
    if (!itens.length) return '';

    return `
        <section class="import-confront-group is-alert">
            <div class="import-confront-group-title">
                <strong>${escapeHtml(titulo)}</strong>
                <span>Fora da criacao de nova despesa neste MVP.</span>
            </div>
            <div class="import-preview-table-wrap">
                <table class="import-preview-table import-confront-table">
                    <thead>
                        <tr>
                            <th>Data</th>
                            <th>Descricao original</th>
                            <th>Valor</th>
                            <th>Status</th>
                            <th>Motivo</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${itens.map(({ linha, motivo, parcela }) => `
                            <tr>
                                <td>${escapeHtml(linha.data_compra || '-')}</td>
                                <td class="import-description-cell">
                                    <span class="import-raw-description">${escapeHtml(descricaoOriginalLinha(linha) || '-')}</span>
                                    ${parcela ? `<span class="import-detected-note">Parcela detectada: ${escapeHtml(parcela.rotulo)}</span>` : ''}
                                </td>
                                <td>${formatarMoeda(linha.valor)}</td>
                                <td><span class="import-status-pill ${classe}">${escapeHtml(statusConfrontoLabel(classe))}</span></td>
                                <td>${escapeHtml(motivo || '-')}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </section>
    `;
}

function statusConfrontoLabel(classe) {
    if (classe === 'duplicate') return 'Possivel duplicado';
    if (classe === 'parcelment') return 'Possivel parcelamento';
    if (classe === 'known') return 'Possivel conhecido';
    if (classe === 'recurrence') return 'Possivel recorrencia';
    return 'Bloqueado';
}

function recalcularConfrontoAtual() {
    estado.analiseConfronto = montarAnaliseConfronto();
    renderizarEditorPrePersistencia();
    renderizarConfrontoClassificacao();
}

function usarSugestaoReconhecimento(index) {
    const linha = estado.linhasMapeadas[index];
    const reconhecimento = reconhecimentoLinha(linha || {});
    if (!linha || !reconhecimento) return;

    if (reconhecimento.descricao_sugerida) {
        linha.descricao_exibida = reconhecimento.descricao_sugerida;
        linha.descricao = reconhecimento.descricao_sugerida;
    }
    if (reconhecimento.categoria_id) {
        linha.categoria_id = toIntOrNull(reconhecimento.categoria_id);
        linha.categoria_despesa_id = linha.categoria_id;
        linha.categoria_origem = 'reconhecimento';
        linha.categoria_sugerida_origem = 'reconhecimento';
        linha.categoria_confianca = reconhecimento.confianca || 'media';
        linha.confianca_categoria = linha.categoria_confianca;
    }
    if (reconhecimento.categoria_cartao_id) {
        linha.categoria_cartao_id = toIntOrNull(reconhecimento.categoria_cartao_id);
        linha.categoria_cartao_origem = 'reconhecimento';
        linha.categoria_cartao_vinculada_ao_cartao = true;
    }
    linha.sugestao_reconhecimento_aplicada = true;
    linha.tratar_como_novo = false;
    linha.status = linha.categoria_id ? 'valido' : 'revisar';
    recalcularConfrontoAtual();
}

function tratarReconhecimentoComoNovo(index) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;
    linha.tratar_como_novo = true;
    linha.sugestao_reconhecimento_aplicada = false;
    recalcularConfrontoAtual();
}

function ignorarReconhecimento(index) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;
    linha.ignorar = true;
    recalcularConfrontoAtual();
}

async function vincularRecorrenciaImportada(index) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;
    if (!validarConfiguracaoBasica()) return;

    const reconhecimento = reconhecimentoLinha(linha) || {};
    const recorrenciaId = idRecorrenciaReconhecimento(linha);
    if (!recorrenciaId) {
        alert('Nao foi possivel identificar a recorrencia sugerida para este lancamento.');
        return;
    }

    const nomeRecorrencia = reconhecimento.descricao_sugerida || linha.descricao_exibida || linha.descricao || 'recorrencia sugerida';
    const mensagem = [
        'Este lancamento sera vinculado a recorrencia selecionada e nao sera criado como despesa avulsa.',
        '',
        `Recorrencia: ${nomeRecorrencia}`,
        `Descricao original: ${descricaoOriginalLinha(linha) || '-'}`,
        `Valor: ${formatarValorLinha(linha)}`,
        `Data: ${linha.data_compra || '-'}`,
        `Competencia: ${document.getElementById('competenciaInput')?.value || '-'}`
    ].join('\n');

    if (!confirm(mensagem)) return;

    const payload = {
        cartao_id: parseInt(document.getElementById('cartaoSelect').value, 10),
        competencia: competenciaCompletaApi(),
        item_despesa_id: recorrenciaId,
        linha: {
            data_compra: linha.data_compra,
            descricao: linha.descricao || descricaoOriginalLinha(linha),
            descricao_original: descricaoOriginalLinha(linha),
            descricao_exibida: linha.descricao_exibida || linha.descricao || nomeRecorrencia,
            valor: linha.valor,
            parcela: linha.parcela || `${linha.numero_parcela || 1}/${linha.total_parcelas || 1}`,
            numero_parcela: linha.numero_parcela || 1,
            total_parcelas: linha.total_parcelas || 1,
            item_despesa_id: recorrenciaId,
            origem_importacao: linha.origem_importacao || estado.payloadUnificado?.origem || 'csv',
            ignorar: false
        }
    };

    try {
        const resposta = await fetch(`${API_BASE}/recorrencia`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const resultado = await resposta.json();
        if (!resposta.ok || !resultado.success) {
            throw new Error(resultado.message || 'Falha ao vincular recorrencia.');
        }

        linha.recorrencia_vinculada = true;
        linha.status = 'recorrencia_vinculada';
        linha.ignorar = false;
        linha.is_recorrente = true;
        linha.item_despesa_id = recorrenciaId;
        linha.categoria_id = resultado.recorrencia?.categoria_id || reconhecimento.categoria_id || linha.categoria_id;
        linha.categoria_despesa_id = linha.categoria_id;
        linha.categoria_cartao_id = resultado.categoria_cartao_id || reconhecimento.categoria_cartao_id || linha.categoria_cartao_id;
        linha.recorrencia_vinculada_info = resultado.recorrencia || {
            id: recorrenciaId,
            nome: nomeRecorrencia
        };
        linha.lancamento_recorrente = resultado.lancamento || null;
        linha.sugestao_reconhecimento_aplicada = true;
        linha.tratar_como_novo = false;

        recalcularConfrontoAtual();
        document.getElementById('resultadoContainer').innerHTML = `
            <div class="import-feedback success">
                <strong>Recorrencia vinculada.</strong>
                A linha original nao sera importada como despesa avulsa.
                ${resultado.duplicado ? 'Lancamento equivalente ja existia na fatura.' : ''}
            </div>
        `;
    } catch (error) {
        document.getElementById('resultadoContainer').innerHTML = `
            <div class="import-feedback error">${escapeHtml(error.message)}</div>
        `;
    }
}

function competenciaCompletaApi() {
    const valor = document.getElementById('competenciaInput')?.value || '';
    if (!/^\d{2}\/\d{4}$/.test(valor)) return null;
    const [mes, ano] = valor.split('/');
    return `${ano}-${mes}-01`;
}

function cartaoSelecionadoNome() {
    const cartaoId = toIntOrNull(document.getElementById('cartaoSelect')?.value);
    const cartao = estado.cartoes.find((item) => Number(item.id) === Number(cartaoId));
    return cartao?.nome || 'Cartao selecionado';
}

function addMesesDataIso(dataIso, meses) {
    const data = new Date(`${dataIso}T00:00:00`);
    if (Number.isNaN(data.getTime())) return dataIso;
    data.setMonth(data.getMonth() + meses);
    return data.toISOString().slice(0, 10);
}

function addMesesCompetenciaIso(competenciaIso, meses) {
    const data = new Date(`${competenciaIso}T00:00:00`);
    if (Number.isNaN(data.getTime())) return competenciaIso;
    data.setMonth(data.getMonth() + meses);
    return data.toISOString().slice(0, 10);
}

function formatarCompetenciaCurta(dataIso) {
    const data = new Date(`${dataIso}T00:00:00`);
    if (Number.isNaN(data.getTime())) return dataIso;
    return data.toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' });
}

function preencherSelectValor(id, opcoesHtml, valor) {
    const elemento = document.getElementById(id);
    if (!elemento) return;
    elemento.innerHTML = opcoesHtml;
    elemento.value = valor || '';
}

async function abrirModalParcelamento(index) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;
    if (!estado.categorias.length) {
        await carregarCategorias();
    }

    const parcela = detectarParcelamentoLinha(linha);
    if (!parcela) {
        alert('Nao foi possivel detectar os dados de parcelamento desta linha.');
        return;
    }

    estado.parcelamentoModal = {
        index,
        linha,
        parcela,
        categoriaCartaoId: toIntOrNull(linha.categoria_cartao_id),
        categoriaCartaoAviso: ''
    };
    const descricaoOriginal = descricaoOriginalLinha(linha);
    const descricaoSugerida = parcela.descricaoLimpa || detectarParcelamentoTexto(descricaoOriginal)?.descricaoLimpa || descricaoOriginal;

    document.getElementById('parcelamentoDescricaoOriginal').value = descricaoOriginal;
    document.getElementById('parcelamentoDescricaoAmigavel').value = linha.descricao_exibida || descricaoSugerida;
    document.getElementById('parcelamentoDataCompra').value = linha.data_compra || '';
    document.getElementById('parcelamentoValor').value = formatarValor(parseValorNumerico(linha.valor));
    document.getElementById('parcelamentoParcelaAtual').value = parcela.numero;
    document.getElementById('parcelamentoTotalParcelas').value = parcela.total;
    document.getElementById('parcelamentoCartaoLabel').value = cartaoSelecionadoNome();
    document.getElementById('parcelamentoCompetenciaLabel').value = document.getElementById('competenciaInput')?.value || '';
    const categoriaInicial = linha.categoria_id || linha.categoria_despesa_id;
    preencherSelectValor('parcelamentoCategoriaDespesa', opcoesCategoriaSelect(categoriaInicial), categoriaInicial);

    const feedback = document.getElementById('parcelamentoFeedback');
    if (feedback) feedback.innerHTML = '';
    if (categoriaInicial) {
        await atualizarCategoriaDespesaParcelamento(categoriaInicial);
    }
    renderizarPreviewParcelamentoModal();
    document.getElementById('parcelamentoModal').hidden = false;
}

function fecharModalParcelamento() {
    estado.parcelamentoModal = null;
    const modal = document.getElementById('parcelamentoModal');
    if (modal) modal.hidden = true;
}

function obterDadosModalParcelamento() {
    const numero = parseInt(document.getElementById('parcelamentoParcelaAtual')?.value || '', 10);
    const total = parseInt(document.getElementById('parcelamentoTotalParcelas')?.value || '', 10);
    const valorNumerico = parseValorNumerico(document.getElementById('parcelamentoValor')?.value);
    return {
        descricaoOriginal: document.getElementById('parcelamentoDescricaoOriginal')?.value || '',
        descricaoAmigavel: document.getElementById('parcelamentoDescricaoAmigavel')?.value || '',
        dataCompra: document.getElementById('parcelamentoDataCompra')?.value || '',
        valor: valorNumerico === null ? '' : formatarValor(valorNumerico),
        numeroParcela: numero,
        totalParcelas: total,
        categoriaId: toIntOrNull(document.getElementById('parcelamentoCategoriaDespesa')?.value),
        categoriaCartaoId: toIntOrNull(estado.parcelamentoModal?.categoriaCartaoId)
    };
}

function renderizarPreviewParcelamentoModal() {
    const preview = document.getElementById('parcelamentoPreview');
    if (!preview || !estado.parcelamentoModal) return;

    const dados = obterDadosModalParcelamento();
    const competenciaBase = competenciaCompletaApi();
    if (!validarNumerosParcelamento(dados.numeroParcela, dados.totalParcelas) || !dados.dataCompra || !competenciaBase) {
        preview.innerHTML = '<div class="import-empty-state compact">Informe parcela atual, total, data e competencia para ver a previa.</div>';
        return;
    }

    const linhas = [];
    for (let numero = dados.numeroParcela; numero <= dados.totalParcelas; numero += 1) {
        const diff = numero - dados.numeroParcela;
        linhas.push({
            rotulo: `${numero}/${dados.totalParcelas}`,
            competencia: formatarCompetenciaCurta(addMesesCompetenciaIso(competenciaBase, diff)),
            data: addMesesDataIso(dados.dataCompra, diff),
            valor: formatarMoeda(dados.valor)
        });
    }

    preview.innerHTML = `
        <div class="import-parcel-preview-summary">
            Serao geradas ${linhas.length} parcela${linhas.length === 1 ? '' : 's'}, da ${linhas[0].rotulo} ate ${linhas[linhas.length - 1].rotulo}.
        </div>
        <div class="import-parcel-preview-list">
            ${linhas.map((item) => `
                <div class="import-parcel-preview-row">
                    <strong>${escapeHtml(item.rotulo)}</strong>
                    <span>${escapeHtml(item.competencia)}</span>
                    <span>${escapeHtml(item.data)}</span>
                    <span>${escapeHtml(item.valor)}</span>
                </div>
            `).join('')}
        </div>
    `;
}

async function atualizarCategoriaDespesaParcelamento(valor) {
    const categoriaId = toIntOrNull(valor);
    if (!estado.parcelamentoModal) return;
    estado.parcelamentoModal.categoriaCartaoId = null;
    estado.parcelamentoModal.categoriaCartaoAviso = '';

    if (!categoriaId) {
        const feedback = document.getElementById('parcelamentoFeedback');
        if (feedback) feedback.innerHTML = '';
        return;
    }

    try {
        const cartaoId = parseInt(document.getElementById('cartaoSelect')?.value || '', 10);
        const resolucao = await buscarResolucaoCategoriaCartao(categoriaId, cartaoId);
        const categoriaCartaoId = toIntOrNull(resolucao.categoria_cartao_id);
        if (categoriaCartaoId && resolucao.vinculada_ao_cartao !== false) {
            estado.parcelamentoModal.categoriaCartaoId = categoriaCartaoId;
        } else if (toIntOrNull(resolucao.categoria_cartao_resolvida_id || resolucao.categoria_cartao_id)) {
            estado.parcelamentoModal.categoriaCartaoAviso = 'Esta categoria da despesa ainda nao esta vinculada ao cartao selecionado.';
        } else {
            estado.parcelamentoModal.categoriaCartaoAviso = 'Esta categoria da despesa nao possui mapeamento para o cartao. Ajuste em Categorias antes de importar.';
        }
        const feedback = document.getElementById('parcelamentoFeedback');
        if (feedback) {
            feedback.innerHTML = estado.parcelamentoModal.categoriaCartaoAviso
                ? `<div class="import-feedback warning">${escapeHtml(estado.parcelamentoModal.categoriaCartaoAviso)}</div>`
                : '';
        }
    } catch (error) {
        console.warn('Falha ao resolver Categoria do Cartao para parcelamento:', error);
    }
}

async function confirmarParcelamentoImportado() {
    if (!estado.parcelamentoModal) return;
    if (!validarConfiguracaoBasica()) return;

    const { index, linha } = estado.parcelamentoModal;
    let dados = obterDadosModalParcelamento();
    const feedback = document.getElementById('parcelamentoFeedback');
    if (feedback) feedback.innerHTML = '';

    if (!validarNumerosParcelamento(dados.numeroParcela, dados.totalParcelas)) {
        if (feedback) feedback.innerHTML = '<div class="import-feedback error">Parcela atual e total de parcelas estao fora do intervalo permitido.</div>';
        return;
    }
    if (!dados.categoriaId) {
        if (feedback) feedback.innerHTML = '<div class="import-feedback error">Categoria da despesa e obrigatoria para criar parcelamento.</div>';
        return;
    }
    if (!dados.descricaoAmigavel || !dados.dataCompra || !dados.valor || parseValorNumerico(dados.valor) <= 0) {
        if (feedback) feedback.innerHTML = '<div class="import-feedback error">Preencha descricao, data e valor da parcela.</div>';
        return;
    }

    if (dados.categoriaId && !dados.categoriaCartaoId) {
        await atualizarCategoriaDespesaParcelamento(dados.categoriaId);
        dados = obterDadosModalParcelamento();
    }

    const payload = {
        cartao_id: parseInt(document.getElementById('cartaoSelect').value, 10),
        competencia: competenciaCompletaApi(),
        linhas: [{
            data_compra: dados.dataCompra,
            descricao: dados.descricaoOriginal,
            descricao_original: dados.descricaoOriginal,
            descricao_exibida: dados.descricaoAmigavel,
            valor: dados.valor,
            parcela: `${dados.numeroParcela}/${dados.totalParcelas}`,
            numero_parcela: dados.numeroParcela,
            total_parcelas: dados.totalParcelas,
            gerar_parcelas_futuras: true,
            gerar_apenas_atual_e_futuras: true,
            categoria_id: dados.categoriaId,
            categoria_cartao_id: dados.categoriaCartaoId,
            origem_importacao: linha.origem_importacao || estado.payloadUnificado?.origem || 'csv',
            ignorar: false
        }]
    };

    try {
        const resposta = await fetch(`${API_BASE}/parcelamento`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const resultado = await resposta.json();
        if (!resposta.ok || !resultado.success) {
            throw new Error(resultado.message || 'Falha ao criar parcelamento.');
        }
        if ((resultado.erros || []).length && !resultado.inseridos && !resultado.duplicados) {
            throw new Error((resultado.erros || []).map((item) => item.erro).join(' | ') || 'Parcelamento nao criado.');
        }

        linha.tratada_como_parcelamento = true;
        linha.ignorar = true;
        linha.status = 'parcelamento_criado';
        linha.parcelamento_criado = {
            inseridos: resultado.inseridos || 0,
            duplicados: resultado.duplicados || 0,
            numero_parcela: dados.numeroParcela,
            total_parcelas: dados.totalParcelas
        };

        estado.analiseConfronto = montarAnaliseConfronto();
        fecharModalParcelamento();
        renderizarEditorPrePersistencia();
        renderizarConfrontoClassificacao();
        document.getElementById('resultadoContainer').innerHTML = `
            <div class="import-feedback success">
                <strong>Parcelamento criado.</strong>
                Inseridos: <strong>${resultado.inseridos || 0}</strong>.
                Duplicados protegidos: <strong>${resultado.duplicados || 0}</strong>.
                A linha original nao sera importada como despesa avulsa.
            </div>
        `;
        rolarParaSecao('step5');
    } catch (error) {
        if (feedback) feedback.innerHTML = `<div class="import-feedback error">${escapeHtml(error.message)}</div>`;
    }
}

function atualizarParcelaTexto(index, valor) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;

    const parcela = detectarParcelaDescricao(valor);
    linha.numero_parcela = parcela.numero_parcela;
    linha.total_parcelas = parcela.total_parcelas;
    linha.parcela = parcela.parcela;
    linha.parcelado = parcela.total_parcelas > 1;
    if (!linha.parcelado) {
        linha.gerar_parcelas_futuras = false;
    }

    invalidarPrevia();
    renderizarEditorPrePersistencia();
}

function atualizarLinhaEdicao(index, campo, valor) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;

    if (campo === 'categoria_id' || campo === 'categoria_cartao_id') {
        linha[campo] = toIntOrNull(valor);
        if (campo === 'categoria_id') {
            linha.categoria_despesa_id = linha[campo];
            linha.categoria_origem = linha[campo] ? 'manual' : 'sem_sugestao';
            linha.categoria_sugerida_origem = linha.categoria_origem;
            linha.categoria_confianca = linha[campo] ? 'manual' : 'baixa';
            linha.confianca_categoria = linha.categoria_confianca;
            linha.palavras_chave_encontradas = [];
            linha.categorias_candidatas = [];
            linha.categoria_cartao_id = null;
            linha.categoria_cartao_origem = null;
            linha.categoria_cartao_nome = null;
            linha.categoria_cartao_vinculada_ao_cartao = false;
        }
        if (campo === 'categoria_cartao_id') {
            linha.categoria_cartao_origem = linha[campo] ? 'manual' : null;
            linha.categoria_cartao_vinculada_ao_cartao = !!linha[campo];
            if (linha[campo] && linha.categoria_id) linha.status_classificacao = 'classificada';
        }
    } else if (campo === 'numero_parcela' || campo === 'total_parcelas') {
        linha[campo] = Math.max(1, parseInt(valor || '1', 10));
        linha.parcelado = Number(linha.total_parcelas) > 1;
        linha.parcela = `${linha.numero_parcela || 1}/${linha.total_parcelas || 1}`;
        if (!linha.parcelado) linha.gerar_parcelas_futuras = false;
    } else if (campo === 'valor') {
        linha[campo] = formatarValor(valor);
    } else {
        linha[campo] = valor;
    }

    if (campo === 'descricao_exibida') {
        linha.descricao = valor;
    }
    if ((campo === 'categoria_id' || campo === 'categoria_cartao_id') && !['duplicado', 'ignorado'].includes(linha.status)) {
        if (!linha.categoria_id) linha.status = 'revisar';
        else linha.status = 'valido';
    }

    invalidarPrevia();
    renderizarEditorPrePersistencia();
    if (campo === 'categoria_id' && !categoriaCartaoIdLinha(linha)) {
        resolverCategoriaCartaoLinha(index);
    }
}

function atualizarLinhaClassificacao(index, campo, valor) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;

    if (campo === 'categoria_id' || campo === 'categoria_cartao_id') {
        linha[campo] = toIntOrNull(valor);
        if (campo === 'categoria_id') {
            linha.categoria_despesa_id = linha[campo];
            linha.categoria_origem = linha[campo] ? 'manual' : 'sem_sugestao';
            linha.categoria_sugerida_origem = linha.categoria_origem;
            linha.categoria_confianca = linha[campo] ? 'manual' : 'baixa';
            linha.confianca_categoria = linha.categoria_confianca;
            linha.palavras_chave_encontradas = [];
            linha.categorias_candidatas = [];
            linha.categoria_cartao_id = null;
            linha.categoria_cartao_origem = null;
            linha.categoria_cartao_nome = null;
            linha.categoria_cartao_vinculada_ao_cartao = false;
        }
        if (campo === 'categoria_cartao_id') {
            linha.categoria_cartao_origem = linha[campo] ? 'manual' : null;
            linha.categoria_cartao_vinculada_ao_cartao = !!linha[campo];
        }
    } else {
        linha[campo] = valor;
    }

    if (campo === 'descricao_exibida') {
        linha.descricao = valor;
    }
    if ((campo === 'categoria_id' || campo === 'categoria_cartao_id') && !['duplicado', 'ignorado'].includes(linha.status)) {
        linha.status = linha.categoria_id ? 'valido' : 'revisar';
        if (linha.categoria_id && linha.categoria_cartao_id) linha.status_classificacao = 'classificada';
    }

    estado.resumoPrevia = null;
    const resumo = document.getElementById('resumoPreviaTecnica');
    if (resumo) resumo.innerHTML = '';
    const resultado = document.getElementById('resultadoContainer');
    if (resultado) resultado.innerHTML = '';
    renderizarConfrontoClassificacao();

    if (campo === 'categoria_id' && !categoriaCartaoIdLinha(linha)) {
        resolverCategoriaCartaoLinha(index, { manterConfronto: true });
    }
}

async function aplicarCategoriaDespesaLote() {
    const categoriaId = toIntOrNull(document.getElementById('bulkCategoriaDespesa')?.value);
    const selecionados = indicesSelecionados();
    if (!selecionados.length) {
        alert('Selecione ao menos uma linha.');
        return;
    }
    if (!categoriaId) {
        alert('Selecione uma Categoria da Despesa para aplicar.');
        return;
    }

    for (const index of selecionados) {
        const linha = estado.linhasMapeadas[index];
        if (!linha) continue;
        linha.categoria_id = categoriaId;
        linha.categoria_despesa_id = categoriaId;
        linha.categoria_origem = 'manual';
        linha.categoria_sugerida_origem = 'manual';
        linha.categoria_confianca = 'manual';
        linha.confianca_categoria = 'manual';
        linha.palavras_chave_encontradas = [];
        linha.categorias_candidatas = [];
        linha.status = 'valido';
        linha.categoria_cartao_id = null;
        linha.categoria_cartao_origem = null;
        linha.categoria_cartao_nome = null;
        linha.categoria_cartao_vinculada_ao_cartao = false;
    }

    estado.linhasSelecionadas = new Set();
    invalidarPrevia();
    renderizarEditorPrePersistencia();

    await Promise.all(selecionados.map((index) => resolverCategoriaCartaoLinha(index)));
}

function ignorarLinhasSelecionadas() {
    const selecionados = indicesSelecionados();
    if (!selecionados.length) {
        alert('Selecione ao menos uma linha.');
        return;
    }

    selecionados.forEach((index) => {
        const linha = estado.linhasMapeadas[index];
        if (linha) linha.ignorar = true;
    });
    estado.linhasSelecionadas = new Set();
    invalidarPrevia();
    renderizarEditorPrePersistencia();
}

function restaurarLinhasSelecionadas() {
    const selecionados = indicesSelecionados();
    if (!selecionados.length) {
        alert('Selecione ao menos uma linha.');
        return;
    }

    selecionados.forEach((index) => {
        const linha = estado.linhasMapeadas[index];
        if (linha && !linhaBloqueadaTecnica(linha)) linha.ignorar = false;
    });
    estado.linhasSelecionadas = new Set();
    invalidarPrevia();
    renderizarEditorPrePersistencia();
}

function marcarLinhasSelecionadasRevisadas() {
    const selecionados = indicesSelecionados();
    if (!selecionados.length) {
        alert('Selecione ao menos uma linha.');
        return;
    }

    selecionados.forEach((index) => {
        const linha = estado.linhasMapeadas[index];
        if (!linha) return;
        if (linha.categoria_id) {
            linha.status = 'valido';
            linha.status_classificacao = categoriaCartaoIdLinha(linha) ? 'classificada' : 'categoria_cartao_pendente';
        }
        if (linha.categoria_origem === 'ambigua' && linha.categoria_id) {
            linha.categoria_origem = 'manual';
            linha.categoria_sugerida_origem = 'manual';
            linha.categoria_confianca = 'manual';
            linha.confianca_categoria = 'manual';
        }
    });

    estado.linhasSelecionadas = new Set();
    invalidarPrevia();
    renderizarEditorPrePersistencia();
}

async function resolverCategoriaCartaoLinha(index, opcoes = {}) {
    const linha = estado.linhasMapeadas[index];
    const cartaoId = parseInt(document.getElementById('cartaoSelect')?.value || '', 10);
    if (!linha || !linha.categoria_id || !cartaoId) return;
    try {
        estado.linhasMapeadas[index] = aplicarResolucaoCategoriaCartaoLinha(
            linha,
            await buscarResolucaoCategoriaCartao(linha.categoria_id, cartaoId)
        );
        invalidarPrevia({ manterConfronto: !!opcoes.manterConfronto });
        if (opcoes.manterConfronto) renderizarConfrontoClassificacao();
        else renderizarEditorPrePersistencia();
    } catch (error) {
        console.warn('Falha ao resolver Categoria do Cartao:', error);
    }
}

function alternarParcelado(index, marcado) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;
    linha.parcelado = marcado;
    if (!marcado) {
        linha.numero_parcela = 1;
        linha.total_parcelas = 1;
        linha.parcela = '1/1';
        linha.gerar_parcelas_futuras = false;
    } else if (Number(linha.total_parcelas) <= 1) {
        linha.numero_parcela = 1;
        linha.total_parcelas = 2;
        linha.parcela = '1/2';
    }
    invalidarPrevia();
    renderizarEditorPrePersistencia();
}

function alternarIgnorarLinha(index) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;
    if (linhaBloqueadaTecnica(linha)) return;
    linha.ignorar = !linha.ignorar;
    invalidarPrevia();
    renderizarEditorPrePersistencia();
}

function detalharLinha(index) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;

    alert(
        `Lançamento ${linha.linha_origem || index + 1}\n\n` +
        `Data: ${linha.data_compra}\n` +
        `Descrição original: ${linha.descricao_original || linha.descricao_exibida || linha.descricao}\n` +
        `Valor: ${formatarMoeda(linha.valor)}\n` +
        `Status: ${statusLinha(linha).texto}`
    );
}

function renderizarTabelaRetirados() {
    const container = document.getElementById('retiradosContainer');
    if (!container) return;
    renderizarFiltroAvancado('retirados');

    const retirados = linhasRetiradasFiltradas();
    const paginaInfo = paginarItens(retirados, 'retirados');

    container.innerHTML = `
        <div class="import-preview-table-wrap retired">
            <table class="import-preview-table import-retired-table">
                <thead>
                    <tr>
                        <th>Motivo</th>
                        <th>Data</th>
                        <th>Descrição original</th>
                        <th>Valor</th>
                        <th>Observação</th>
                        <th>Ação</th>
                    </tr>
                </thead>
                <tbody>
                    ${paginaInfo.itens.length
                        ? paginaInfo.itens.map(({ linha, index }) => renderizarLinhaRetirada(linha, index)).join('')
                        : '<tr><td colspan="6"><div class="import-empty-state compact">Nenhum lançamento retirado da efetivação para este filtro.</div></td></tr>'}
                </tbody>
            </table>
        </div>
        ${renderizarPaginacaoTabela('retirados', paginaInfo)}
    `;
}

function renderizarLinhaRetirada(linha, index) {
    const motivo = motivoRetiradaLinha(linha);
    const restauravel = linhaRestauravel(linha);
    const descricaoOriginal = descricaoOriginalLinha(linha);
    const observacao = observacaoRetiradaLinha(linha);
    return `
        <tr>
            <td><span class="import-retired-reason">${escapeHtml(motivo)}</span></td>
            <td>${escapeHtml(linha.data_compra || '-')}</td>
            <td class="import-description-cell one-line">
                <span class="import-raw-description" title="${escapeAttr(descricaoOriginal)}">${escapeHtml(descricaoOriginal || '-')}</span>
            </td>
            <td>${formatarValorLinha(linha)}</td>
            <td class="import-description-cell one-line">
                <span title="${escapeAttr(observacao)}">${escapeHtml(observacao || '-')}</span>
            </td>
            <td>
                <div class="row-actions operational">
                    ${iconeBotaoAcao('success', 'undo', 'Restaurar', restauravel ? `alternarIgnorarLinha(${index})` : null, !restauravel)}
                    ${iconeBotaoAcao('neutral', 'eye', 'Ver detalhes', `detalharLinhaRetirada(${index})`)}
                </div>
            </td>
        </tr>
    `;
}

function detalharLinhaRetirada(index) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;
    alert(detalheRetiradaLinha(linha));
}

function calcularKpisImportacao() {
    const encontrados = estado.csvData?.total_linhas || estado.linhasMapeadas.length || 0;
    const processamento = linhasProcessamentoBase();
    const retirados = linhasRetiradasBase();
    const conhecidas = processamento.filter((item) => item.filtro === 'conhecidas').length;
    const parcelamentos = processamento.filter((item) => item.filtro === 'parcelados').length;
    const novos = processamento.filter((item) => item.filtro === 'novos').length;
    const valorProcessamento = processamento.reduce((acc, item) => acc + valorNumericoLinha(item.linha), 0);
    const pendencias = processamento.filter((item) => {
        if (item.filtro === 'novos') return !toIntOrNull(item.linha.categoria_id || item.linha.categoria_despesa_id);
        return item.filtro !== 'novos';
    }).length + estado.linhasInvalidasIniciais.length;

    return {
        encontrados,
        processamento: processamento.length,
        retirados: retirados.length,
        conhecidas,
        parcelamentos,
        novos,
        valorProcessamento,
        pendencias
    };
}

function renderizarKpisImportacao() {
    const kpis = calcularKpisImportacao();
    setText('kpiEncontrados', kpis.encontrados);
    setText('kpiProcessamento', kpis.processamento);
    setText('kpiRetirados', kpis.retirados);
    setText('kpiConhecidas', kpis.conhecidas);
    setText('kpiParcelamentos', kpis.parcelamentos);
    setText('kpiNovos', kpis.novos);
    setText('kpiValorProcessamento', formatarMoeda(kpis.valorProcessamento));
    setText('kpiPendencias', kpis.pendencias);
}

function calcularResumoLocal() {
    const linhas = estado.linhasMapeadas;
    const ativas = linhas.filter(linhaImportavel);
    const pendentesCartao = 0;
    const pendentesDespesa = 0;
    const validas = ativas.length;
    const baixaConfianca = 0;
    const ignoradas = linhas.filter((linha) => linha.ignorar && !linhaDuplicada(linha) && !linhaTratadaParcelamento(linha)).length;
    const duplicadas = linhas.filter(linhaDuplicada).length;
    const creditos = linhas.filter(linhaCredito).length;
    const parceladas = linhas.filter((linha) => Number(linha.total_parcelas) > 1).length;
    const totalPrevisto = ativas.reduce((acc, linha) => acc + (parseValorNumerico(linha.valor) || 0), 0);
    const valorSemCategoriaCartao = 0;

    return {
        linhas,
        ativas,
        importaveis: ativas,
        pendentesCartao,
        pendentesDespesa,
        validas,
        revisar: pendentesCartao + pendentesDespesa + baixaConfianca + estado.linhasInvalidasIniciais.length,
        ignoradas,
        duplicadas,
        creditos,
        parceladas,
        totalPrevisto,
        valorSemCategoriaCartao
    };
}

function atualizarResumoPainel() {
    const resumo = calcularResumoLocal();
    const totalDetectado = estado.csvData?.total_linhas || resumo.linhas.length || 0;
    const duplicados = estado.resumoPrevia?.duplicados ?? resumo.duplicadas;
    const novosConfronto = estado.analiseConfronto ? linhasNovasConfirmaveis().length : resumo.importaveis.length;
    const novos = estado.resumoPrevia ? estado.resumoPrevia.inseridos : novosConfronto;
    const bloqueados = resumo.duplicadas + resumo.creditos + estado.linhasInvalidasIniciais.length;
    const valorPlanejado = estado.analiseConfronto
        ? linhasNovasConfirmaveis().reduce((acc, linha) => acc + (parseValorNumerico(linha.valor) || 0), 0)
        : resumo.totalPrevisto;

    setText('detectedCount', totalDetectado);
    setText('parceladoCount', resumo.importaveis.length);
    setText('duplicateCount', duplicados);
    setText('validCount', resumo.validas);
    setText('reviewCount', resumo.ignoradas);
    setText('missingCardCategoryCount', bloqueados);
    setText('validationDuplicateCount', duplicados);
    setText('plannedTotal', formatarMoeda(valorPlanejado));
    setText('uncategorizedCardValue', formatarMoeda(resumo.totalPrevisto));
    setText('newCount', novos);
    setText('ignoredCount', resumo.ignoradas);
    setText('confirmedCardCategoryCount', duplicados);
    setText('pendingCardCategoryCount', estado.analiseConfronto ? `${novosConfronto} novos` : `${resumo.importaveis.length} a importar`);
    renderizarKpisImportacao();

    atualizarControlesImportacao(resumo);
    renderizarClassificacao();
}

function setText(id, valor) {
    const elemento = document.getElementById(id);
    if (elemento) elemento.textContent = valor;
}

function atualizarControlesImportacao(resumo = calcularResumoLocal()) {
    const btnPrevia = document.getElementById('btnStep4');
    const btnImportar = document.getElementById('btnImportar');
    const semLinhasAtivas = resumo.importaveis.length === 0;

    if (btnPrevia) {
        btnPrevia.disabled = semLinhasAtivas;
    }

    if (btnImportar) {
        const quantidade = estado.analiseConfronto ? linhasNovasConfirmaveis().length : 0;
        btnImportar.disabled = !estado.analiseConfronto || quantidade === 0 || novasSemCategoriaDespesa().length > 0;
        btnImportar.innerHTML = `
            <span aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg></span>
            Criar despesas (${quantidade})
        `;
    }
}

function renderizarClassificacao() {
    const container = document.getElementById('classificationList');
    if (!container) return;

    const linhas = estado.linhasMapeadas;
    const resumo = [
        ['Total encontrados', estado.csvData?.total_linhas || linhas.length || 0],
        ['A importar', linhas.filter(linhaImportavel).length],
        ['Ignorados', linhas.filter((linha) => linha.ignorar && !linhaDuplicada(linha) && !linhaTratadaParcelamento(linha)).length],
        ['Duplicados', linhas.filter(linhaDuplicada).length],
    ];

    container.innerHTML = resumo.map(([label, count]) => `
        <div class="import-category-row">
            <span class="import-category-name">
                <span class="import-category-dot" aria-hidden="true"></span>
                <span>${escapeHtml(label)}</span>
            </span>
            <span class="import-category-count">${count}</span>
        </div>
    `).join('');
}

function montarPayloadImportacao() {
    const cartaoId = parseInt(document.getElementById('cartaoSelect').value, 10);
    const [mes, ano] = document.getElementById('competenciaInput').value.split('/');
    const competencia = `${ano}-${mes}-01`;
    const linhas = linhasNovasConfirmaveis()
        .map((linha) => {
            const payload = {
                data_compra: linha.data_compra,
                descricao_original: descricaoOriginalLinha(linha),
                descricao: linha.descricao_exibida || linha.descricao || descricaoOriginalLinha(linha),
                descricao_exibida: linha.descricao_exibida || linha.descricao || descricaoOriginalLinha(linha),
                valor: linha.valor,
                parcela: linha.parcela || `${linha.numero_parcela || 1}/${linha.total_parcelas || 1}`,
                numero_parcela: linha.numero_parcela || 1,
                total_parcelas: linha.total_parcelas || 1,
                gerar_parcelas_futuras: false,
                categoria_id: linha.categoria_id,
                categoria_origem: linha.categoria_origem,
                categoria_confianca: linha.categoria_confianca || linha.confianca_categoria,
                palavras_chave_encontradas: linha.palavras_chave_encontradas || [],
                origem_importacao: linha.origem_importacao || estado.payloadUnificado?.origem || 'csv',
                ignorar: false
            };

            if (linha.categoria_cartao_id) {
                payload.categoria_cartao_id = linha.categoria_cartao_id;
                payload.categoria_cartao_origem = linha.categoria_cartao_origem;
            }

            return payload;
        });

    return {
        cartao_id: cartaoId,
        competencia,
        linhas
    };
}

function validarPendenciasObrigatorias() {
    const resumo = calcularResumoLocal();
    const importaveis = resumo.importaveis;
    if (!importaveis.length) {
        alert('Nenhum lançamento selecionado para importação.');
        return false;
    }
    return true;
}

function validarNovosClassificados() {
    if (!estado.analiseConfronto) {
        alert('Avance para o confronto pos-triagem antes de confirmar.');
        return false;
    }

    const novos = linhasNovasConfirmaveis();
    if (!novos.length) {
        alert('Nenhum lancamento novo selecionado para importacao.');
        return false;
    }

    const pendentes = novasSemCategoriaDespesa();
    if (pendentes.length) {
        alert('Classifique a categoria da despesa dos lancamentos novos antes de confirmar.');
        return false;
    }

    return true;
}

function montarPayloadReconhecimento() {
    const cartaoId = parseInt(document.getElementById('cartaoSelect').value, 10);
    const competencia = competenciaCompletaApi();
    const linhas = estado.linhasMapeadas
        .map((linha, index) => ({ linha, index }))
        .filter(({ linha }) => !linha.ignorar && !linhaTratadaParcelamento(linha) && !linhaBloqueadaTecnica(linha))
        .map(({ linha, index }) => ({
            indice: index,
            data_compra: linha.data_compra,
            descricao_original: descricaoOriginalLinha(linha),
            descricao: linha.descricao || linha.descricao_exibida || descricaoOriginalLinha(linha),
            descricao_exibida: linha.descricao_exibida || linha.descricao || descricaoOriginalLinha(linha),
            valor: linha.valor,
            parcela: linha.parcela || `${linha.numero_parcela || 1}/${linha.total_parcelas || 1}`,
            numero_parcela: linha.numero_parcela || 1,
            total_parcelas: linha.total_parcelas || 1,
            categoria_id: linha.categoria_id || linha.categoria_despesa_id,
            categoria_cartao_id: linha.categoria_cartao_id
        }));

    return { cartao_id: cartaoId, competencia, linhas };
}

async function aplicarReconhecimentoFlexivel() {
    const payload = montarPayloadReconhecimento();
    if (!payload.linhas.length) return;

    estado.linhasMapeadas.forEach((linha) => {
        linha.reconhecimento_match = null;
        linha.tratar_como_novo = false;
        linha.sugestao_reconhecimento_aplicada = false;
    });

    try {
        const resposta = await fetch(`${API_BASE}/reconhecer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const dados = await resposta.json();
        if (!resposta.ok || !dados.success) {
            throw new Error(dados.message || 'Falha no reconhecimento flexivel');
        }

        (dados.reconhecimentos || []).forEach((reconhecimento) => {
            const index = Number(reconhecimento.indice);
            if (estado.linhasMapeadas[index]) {
                estado.linhasMapeadas[index].reconhecimento_match = reconhecimento;
            }
        });
    } catch (error) {
        console.warn('Reconhecimento flexivel indisponivel:', error);
    }
}

async function previsualizarImportacao() {
    if (!estado.linhasMapeadas.length) {
        alert('Valide perfil e mapeamento antes do confronto.');
        return;
    }
    if (!validarConfiguracaoBasica()) return;
    if (!validarPendenciasObrigatorias()) {
        atualizarResumoPainel();
        return;
    }

    await aplicarReconhecimentoFlexivel();
    estado.analiseConfronto = montarAnaliseConfronto();
    estado.faseImportacao = 'confronto';
    estado.resumoPrevia = null;
    const resumoTecnico = document.getElementById('resumoPreviaTecnica');
    if (resumoTecnico) resumoTecnico.innerHTML = '';
    const resultado = document.getElementById('resultadoContainer');
    if (resultado) resultado.innerHTML = '';
    renderizarConfrontoClassificacao();
    rolarParaSecao('step5');
}

function renderResumoPrevia(dados) {
    const erros = (dados.erros || []).slice(0, 10);
    const duplicados = (dados.amostra_duplicados || []).slice(0, 10);
    const pendencias = dados.pendencias || {};
    const avisosLinhas = (dados.avisos_linhas || []).slice(0, 5);
    const resumo = calcularResumoLocal();
    const pendentesEtapaPosterior = (pendencias.categoria_despesa || 0) + (pendencias.categoria_cartao || 0);

    document.getElementById('resumoPreviaTecnica').innerHTML = `
        <div class="import-feedback success">
            <strong>Pré-visualização concluída.</strong>
            Total recebido no backend: <strong>${dados.total_recebidas}</strong>.
            Potencial para inserir: <strong>${dados.inseridos}</strong>.
            Duplicados detectados: <strong>${dados.duplicados}</strong>.
            Linhas ignoradas: <strong>${resumo.ignoradas}</strong>.
            Dependem de etapa posterior: <strong>${pendentesEtapaPosterior}</strong>.
        </div>
        ${avisosLinhas.length ? `
            <div class="import-feedback warning">
                <strong>Avisos técnicos</strong>
                <div>${avisosLinhas.length} linha${avisosLinhas.length === 1 ? '' : 's'} dependem de etapa posterior.</div>
            </div>
        ` : ''}
        ${duplicados.length ? `
            <div class="import-feedback warning">
                <strong>Amostra de duplicados</strong>
                ${duplicados.map((item) => `<div>${escapeHtml(item.data_compra)} | ${escapeHtml(item.descricao)} | ${formatarMoeda(item.valor)} (${item.numero_parcela}/${item.total_parcelas})</div>`).join('')}
            </div>
        ` : ''}
        ${erros.length ? `
            <div class="import-feedback error">
                <strong>Amostra de erros</strong>
                ${erros.map((item) => `<div>Linha ${escapeHtml(item.linha || '-')}: ${escapeHtml(item.erro)}</div>`).join('')}
            </div>
        ` : ''}
    `;
}

async function finalizarImportacao() {
    if (!validarNovosClassificados()) {
        atualizarResumoPainel();
        return;
    }

    try {
        const payload = montarPayloadImportacao();
        const respostaPrevia = await fetch(`${API_BASE}/previsualizar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const previa = await respostaPrevia.json();
        if (!respostaPrevia.ok || !previa.success) {
            throw new Error(previa.message || 'Falha na pre-visualizacao');
        }

        estado.resumoPrevia = previa;
        renderResumoPrevia(previa);
        atualizarResumoPainel();

        if (previa.inseridos === 0) {
            alert('Nenhum lancamento novo selecionado para importacao.');
            return;
        }

        const resumo = calcularResumoLocal();
        const confirmado = confirm(
            `Confirmar importacao de ${previa.inseridos} lancamentos novos?\n\n` +
            `Ignorados: ${resumo.ignoradas}\n` +
            `Duplicados protegidos: ${previa.duplicados}\n` +
            `Possiveis parcelamentos fora deste MVP: ${estado.analiseConfronto?.parcelamentos.length || 0}`
        );
        if (!confirmado) return;

        const resposta = await fetch(`${API_BASE}/processar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const dados = await resposta.json();
        if (!resposta.ok || !dados.success) {
            throw new Error(dados.message || 'Falha na importação');
        }

        document.getElementById('resultadoContainer').innerHTML = `
            <div class="import-feedback success">
                <strong>Importação concluída.</strong>
                Total recebido: <strong>${dados.total_recebidas}</strong>.
                Linhas válidas: <strong>${dados.linhas_validas}</strong>.
                Linhas inválidas: <strong>${dados.linhas_invalidas}</strong>.
                Inseridos: <strong>${dados.inseridos}</strong>.
                Duplicados: <strong>${dados.duplicados}</strong>.
                Erros: <strong>${(dados.erros || []).length}</strong>.
            </div>
        `;
        rolarParaSecao('step5');
    } catch (error) {
        alert(`Erro na importação: ${error.message}`);
    }
}
