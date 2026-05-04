const API_BASE = '/api/importacao-cartao';
const PERFIS = {
    NUBANK: 'nubank_csv_simples',
    CAIXA: 'caixa_credito_debito',
    MANUAL: 'manual_generico'
};

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
    filtroPrevia: 'todas',
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

function detectarParcelaDescricao(descricao) {
    const texto = String(descricao || '');
    let match = texto.match(/(\d{1,2})\s*[/\-]\s*(\d{1,2})/);
    if (match) {
        const numero = parseInt(match[1], 10);
        const total = parseInt(match[2], 10);
        if (numero >= 1 && total >= 1 && numero <= total) {
            return {
                numero_parcela: numero,
                total_parcelas: total,
                parcela: `${numero}/${total}`
            };
        }
    }

    match = texto.match(/parcela\s*(\d{1,2})\s*de\s*(\d{1,2})/i);
    if (match) {
        const numero = parseInt(match[1], 10);
        const total = parseInt(match[2], 10);
        if (numero >= 1 && total >= 1 && numero <= total) {
            return {
                numero_parcela: numero,
                total_parcelas: total,
                parcela: `${numero}/${total}`
            };
        }
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
        warning: '<path d="M12 8v5M12 17h.1"/><path d="M12 3 3.5 19h17L12 3Z"/>'
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
    chip.innerHTML = `
        <span class="file-icon ${tipo === 'pdf' ? '' : 'neutral'}">${iconSvg(tipo === 'pdf' ? 'pdf' : 'file')}</span>
        <span>
            <strong title="${escapeAttr(file.name)}">${escapeHtml(file.name)}</strong>
            <span>${formatarTamanho(file.size)}</span>
        </span>
        <button class="import-file-remove" type="button" onclick="removerArquivoSelecionado(event)" title="Remover arquivo" aria-label="Remover arquivo">${iconSvg('close')}</button>
    `;
}

function removerArquivoSelecionado(event) {
    if (event) event.stopPropagation();
    const input = document.getElementById('csvFile');
    const chip = document.getElementById('selectedFileInfo');

    if (input) input.value = '';
    if (chip) {
        chip.hidden = true;
        chip.innerHTML = '';
    }

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
    estado.perfilSelecionado = PERFIS.MANUAL;
    estado.filtroPrevia = 'todas';
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
    document.getElementById('resultadoContainer').innerHTML = '';
    renderizarClassificacao();
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
    estado.filtroPrevia = 'todas';
    estado.linhasSelecionadas = new Set();

    const origemLabel = (data?.origem || '').toUpperCase();
    setFeedback(
        'uploadResult',
        `${origemLabel} analisado com sucesso. <strong>${estado.linhasMapeadas.length}</strong> linhas normalizadas.`,
        'success'
    );

    document.getElementById('btnStep3').disabled = true;
    document.getElementById('btnStep4').disabled = false;
    document.getElementById('btnImportar').disabled = true;
    renderizarResumoAnalise(data);
    renderizarMapeamento();
    renderizarEditorPrePersistencia();
    atualizarResumoPainel();
}

function renderizarResumoAnalise(data) {
    const container = document.getElementById('resumoConfiguracaoImportacao');
    if (!container || !data) return;

    const fatura = data.fatura || {};
    const validacoes = data.validacoes || {};
    const cartoes = (fatura.cartoes_detectados || []).join(', ') || '-';
    const vencimento = fatura.vencimento || '-';
    const totalFatura = fatura.valor_total !== null && fatura.valor_total !== undefined
        ? formatarMoeda(fatura.valor_total)
        : '-';
    const diferenca = Number(validacoes.diferenca || 0);

    container.innerHTML = `
        <div class="import-feedback ${validacoes.revisar_totais ? 'warning' : 'success'}">
            <strong>Motor unificado:</strong> ${escapeHtml((data.origem || '').toUpperCase())}.
            Vencimento: <strong>${escapeHtml(vencimento)}</strong>.
            Total da fatura: <strong>${totalFatura}</strong>.
            Cartões detectados: <strong>${escapeHtml(cartoes)}</strong>.
            Total importável: <strong>${formatarMoeda(validacoes.total_importavel || 0)}</strong>.
            Diferença: <strong>${formatarMoeda(diferenca)}</strong>.
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
        estado.filtroPrevia = 'todas';
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
            alert('Analise o arquivo ou valide o perfil antes de gerar a prévia.');
            return false;
        }
        await previsualizarImportacao();
        rolarParaSecao('step3');
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

function invalidarPrevia() {
    estado.resumoPrevia = null;
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
        container.innerHTML = `
            <div class="import-feedback success">
                Arquivo normalizado pelo motor unificado. Revise as linhas, confirme Categoria da Despesa e Categoria do Cartão, e gere a prévia técnica.
            </div>
        `;
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

    const opcoesCategoriasCartao =
        `<option value="">Selecione linha a linha</option>${estado.categoriasCartao.map((categoria) => (
            `<option value="${categoria.id}">${escapeHtml(categoria.nome)}</option>`
        )).join('')}`;

    document.getElementById('modalCategoriaCartaoPadraoCaixa').innerHTML = opcoesCategoriasCartao;
    document.getElementById('modalCategoriaCartaoPadraoNubank').innerHTML = opcoesCategoriasCartao;
    document.getElementById('modalCategoriaCartaoPadraoManual').innerHTML = opcoesCategoriasCartao;

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
    const categoriaCartaoPadraoId = perfil === PERFIS.CAIXA
        ? 'modalCategoriaCartaoPadraoCaixa'
        : (perfil === PERFIS.NUBANK ? 'modalCategoriaCartaoPadraoNubank' : 'modalCategoriaCartaoPadraoManual');

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
        categoriaPadrao: toIntOrNull(document.getElementById('modalCategoriaPadrao').value),
        categoriaCartaoPadrao: toIntOrNull(document.getElementById(categoriaCartaoPadraoId).value)
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
            categoria_cartao_id: config.categoriaCartaoPadrao,
            categoria_cartao_origem: config.categoriaCartaoPadrao ? 'manual' : null,
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
                        <th>Parcela</th>
                    </tr>
                </thead>
                <tbody>
                    ${amostra.map((linha) => `
                        <tr>
                            <td>${escapeHtml(linha.data_compra)}</td>
                            <td>${escapeHtml(linha.descricao)}</td>
                            <td>${formatarMoeda(linha.valor)}</td>
                            <td>${escapeHtml(linha.parcela)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

async function confirmarValidacaoModal() {
    const config = obterConfiguracaoModal();
    if (!config.categoriaPadrao) {
        alert('Categoria da despesa padrão do lote é obrigatória.');
        return;
    }
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
            Linhas editáveis: <strong>${estado.linhasMapeadas.length}</strong>.
            Linhas inválidas no parse inicial: <strong>${resultado.invalidas.length}</strong>.
            Categoria da despesa sugerida por histórico/fallback pode ser ajustada antes de importar.
        </div>
    `;

    renderizarEditorPrePersistencia();
    fecharModalValidacao();
}

function nomeCategoriaDespesa(id) {
    const categoria = estado.categorias.find((item) => Number(item.id) === Number(id));
    return categoria ? categoria.nome : '';
}

function nomeCategoriaCartao(id) {
    const categoria = estado.categoriasCartao.find((item) => Number(item.id) === Number(id));
    return categoria ? categoria.nome : '';
}

function categoriaCartaoIdLinha(linha) {
    return toIntOrNull(linha.categoria_cartao_id);
}

function origemCategoriaCartaoLabel(linha) {
    const origem = linha.categoria_cartao_origem;
    if (origem === 'manual') return 'Origem: manual';
    if (origem === 'mapa_categoria_despesa') return 'Origem: resolvida por categoria de despesa';
    if (origem === 'categoria_cartao_nao_vinculada' || origem === 'nao_vinculada_ao_cartao') return 'Categoria sem limite neste cartao';
    if (origem === 'nao_configurada') return 'Categoria do Cartao nao configurada';
    return 'Categoria do Cartao nao configurada';
}

function opcoesCategoriaSelect(selecionado) {
    return `<option value="">Selecione uma categoria</option>${estado.categorias.map((categoria) => (
        `<option value="${categoria.id}" ${Number(selecionado) === Number(categoria.id) ? 'selected' : ''}>${escapeHtml(categoria.nome)}</option>`
    )).join('')}`;
}

function opcoesCategoriaCartaoSelect(selecionado) {
    return `<option value="">Selecione uma categoria</option>${estado.categoriasCartao.map((categoria) => (
        `<option value="${categoria.id}" ${Number(selecionado) === Number(categoria.id) ? 'selected' : ''}>${escapeHtml(categoria.nome)}</option>`
    )).join('')}`;
}

function statusLinha(linha) {
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
        return { texto: 'Categoria do cartao pendente', classe: 'missing' };
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
    if (!categoriaCartaoIdLinha(linha)) {
        return { texto: 'Sem categoria do cartão', classe: 'missing' };
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

function linhasPreviaFiltradas() {
    return estado.linhasMapeadas
        .map((linha, index) => ({ linha, index }))
        .filter(({ linha }) => {
            const status = statusLinha(linha);
            const origem = linha.categoria_origem || linha.categoria_sugerida_origem;
            const confianca = linha.categoria_confianca || linha.confianca_categoria;

            if (estado.filtroPrevia === 'prontas') return status.classe === 'valid' || linha.status_classificacao === 'classificada';
            if (estado.filtroPrevia === 'pendentes') return !linha.categoria_id || !categoriaCartaoIdLinha(linha);
            if (estado.filtroPrevia === 'ambiguas') return linha.status_classificacao === 'ambigua' || origem === 'ambigua';
            if (estado.filtroPrevia === 'duplicadas') return linha.status_classificacao === 'duplicada' || linha.status === 'duplicado';
            if (estado.filtroPrevia === 'baixa_confianca') return confianca === 'baixa' || status.classe === 'low-confidence';
            if (estado.filtroPrevia === 'sem_categoria_cartao') return !linha.ignorar && !categoriaCartaoIdLinha(linha);
            if (estado.filtroPrevia === 'revisar') return linhaPrecisaRevisao(linha);
            return true;
        });
}

function contarFiltroPrevia(filtro) {
    const anterior = estado.filtroPrevia;
    estado.filtroPrevia = filtro;
    const total = linhasPreviaFiltradas().length;
    estado.filtroPrevia = anterior;
    return total;
}

function alterarFiltroPrevia(filtro) {
    estado.filtroPrevia = filtro || 'todas';
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
        ['todas', 'Todas', estado.linhasMapeadas.length],
        ['prontas', 'Prontas', contarFiltroPrevia('prontas')],
        ['pendentes', 'Pendentes', contarFiltroPrevia('pendentes')],
        ['ambiguas', 'Ambiguas', contarFiltroPrevia('ambiguas')],
        ['duplicadas', 'Duplicadas', contarFiltroPrevia('duplicadas')],
        ['baixa_confianca', 'Baixa confianca', contarFiltroPrevia('baixa_confianca')],
        ['sem_categoria_cartao', 'Sem cartao', contarFiltroPrevia('sem_categoria_cartao')],
        ['revisar', 'Revisar', contarFiltroPrevia('revisar')]
    ].map(([id, label, total]) => `
        <button class="import-review-filter ${estado.filtroPrevia === id ? 'is-active' : ''}" type="button" onclick="alterarFiltroPrevia('${id}')">
            ${escapeHtml(label)} <span>${total}</span>
        </button>
    `).join('');

    return `
        <div class="import-review-toolbar">
            <div class="import-review-summary">
                <strong>Revisao em lote</strong>
                <span>${selecionadas} selecionada${selecionadas === 1 ? '' : 's'} de ${linhasFiltradas.length} visiveis</span>
            </div>
            <div class="import-review-filters">${filtros}</div>
            <div class="import-review-actions">
                <select id="bulkCategoriaDespesa" class="import-inline-select">${opcoesCategoriaSelect('')}</select>
                <button class="btn btn-secondary btn-sm" type="button" onclick="aplicarCategoriaDespesaLote()">Aplicar despesa</button>
                <select id="bulkCategoriaCartao" class="import-inline-select">${opcoesCategoriaCartaoSelect('')}</select>
                <button class="btn btn-secondary btn-sm" type="button" onclick="aplicarCategoriaCartaoLote()">Aplicar cartao</button>
                <button class="btn btn-secondary btn-sm" type="button" onclick="marcarLinhasSelecionadasRevisadas()">Marcar revisadas</button>
                <button class="btn btn-outline-danger btn-sm" type="button" onclick="ignorarLinhasSelecionadas()">Ignorar</button>
            </div>
        </div>
    `;
}

function renderizarEditorPrePersistencia() {
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
                            <th>Status</th>
                            <th>Data</th>
                            <th>Descrição</th>
                            <th>Parcela</th>
                            <th>Valor</th>
                            <th>Categoria da Despesa</th>
                            <th>Categoria do Cartão</th>
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${linhasFiltradas.length
                            ? linhasFiltradas.map(({ linha, index }) => renderizarLinhaPrevia(linha, index)).join('')
                            : '<tr><td colspan="9"><div class="import-empty-state compact">Nenhuma linha encontrada para este filtro.</div></td></tr>'}
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

function renderizarLinhaPrevia(linha, index) {
    const status = statusLinha(linha);
    const baixaConfianca = status.classe === 'low-confidence';
    const futurasDisabled = (!linha.parcelado || Number(linha.total_parcelas) <= 1) ? 'disabled' : '';
    const avisos = [...new Set([...(linha.avisos || []), ...(linha.mensagens || [])].filter(Boolean))];
    const detalheOrigem = [linha.cartao_final ? `Cartão ${linha.cartao_final}` : null, linha.grupo]
        .filter(Boolean)
        .join(' | ');
    const selecionada = estado.linhasSelecionadas.has(Number(index));

    return `
        <tr class="${linha.ignorar ? 'is-ignored' : ''}">
            <td class="import-row-check">
                <input type="checkbox" ${selecionada ? 'checked' : ''} onchange="alternarSelecaoLinha(${index}, this.checked)" aria-label="Selecionar linha ${index + 1}">
            </td>
            <td>
                <span class="import-status-pill ${status.classe}">${escapeHtml(status.texto)}</span>
                ${avisos.length ? `<span class="import-detected-note warning-note">${escapeHtml(avisos[0])}</span>` : ''}
            </td>
            <td>
                <input class="import-inline-input" type="text" value="${escapeAttr(linha.data_compra || '')}" onchange="atualizarLinhaEdicao(${index}, 'data_compra', this.value)">
            </td>
            <td class="import-description-cell">
                <input class="import-inline-input" type="text" value="${escapeAttr(linha.descricao_exibida || '')}" onchange="atualizarLinhaEdicao(${index}, 'descricao_exibida', this.value)">
                ${detalheOrigem ? `<span class="import-detected-note">${escapeHtml(detalheOrigem)}</span>` : ''}
            </td>
            <td>
                <input class="import-inline-input" type="text" value="${escapeAttr(linha.parcela || '1/1')}" onchange="atualizarParcelaTexto(${index}, this.value)">
                <label class="import-detected-note">
                    <input type="checkbox" ${linha.gerar_parcelas_futuras ? 'checked' : ''} ${futurasDisabled} onchange="atualizarLinhaEdicao(${index}, 'gerar_parcelas_futuras', this.checked)">
                    futuras
                </label>
            </td>
            <td>
                <input class="import-inline-input" type="number" step="0.01" value="${escapeAttr(formatarValor(linha.valor))}" onchange="atualizarLinhaEdicao(${index}, 'valor', this.value)">
            </td>
            <td class="import-category-cell">
                <select class="import-inline-select" onchange="atualizarLinhaEdicao(${index}, 'categoria_id', this.value)">
                    ${opcoesCategoriaSelect(linha.categoria_id)}
                </select>
                <span class="import-detected-note ${baixaConfianca ? 'low-confidence' : ''}">${escapeHtml(origemCategoriaLabel(linha))}</span>
                <div class="import-badge-row">${badgeConfianca(linha)}</div>
                ${palavrasChaveEncontradas(linha)}
                ${categoriasCandidatasHtml(linha)}
            </td>
            <td class="import-category-cell">
                <select class="import-inline-select import-card-category-select ${categoriaCartaoIdLinha(linha) ? '' : 'needs-review'}" onchange="atualizarLinhaEdicao(${index}, 'categoria_cartao_id', this.value)">
                    ${opcoesCategoriaCartaoSelect(categoriaCartaoIdLinha(linha))}
                </select>
                <span class="import-detected-note">${escapeHtml(origemCategoriaCartaoLabel(linha))}</span>
            </td>
            <td>
                <div class="row-actions">
                    <button class="row-action-button" type="button" onclick="detalharLinha(${index})" title="Detalhar" aria-label="Detalhar">${iconSvg('eye')}</button>
                    <button class="row-action-button ${linha.ignorar ? 'success' : 'danger'}" type="button" onclick="alternarIgnorarLinha(${index})" title="${linha.ignorar ? 'Incluir na importação' : 'Ignorar lançamento'}" aria-label="${linha.ignorar ? 'Incluir na importação' : 'Ignorar lançamento'}">${iconSvg(linha.ignorar ? 'undo' : 'trash')}</button>
                </div>
            </td>
        </tr>
    `;
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
            if (linha.categoria_cartao_origem !== 'manual') {
                linha.categoria_cartao_id = null;
                linha.categoria_cartao_origem = null;
                linha.categoria_cartao_nome = null;
                linha.categoria_cartao_vinculada_ao_cartao = false;
            }
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
        if (linha.categoria_cartao_origem !== 'manual') {
            linha.categoria_cartao_id = null;
            linha.categoria_cartao_origem = null;
            linha.categoria_cartao_nome = null;
            linha.categoria_cartao_vinculada_ao_cartao = false;
        }
    }

    estado.linhasSelecionadas = new Set();
    invalidarPrevia();
    renderizarEditorPrePersistencia();

    await Promise.all(selecionados.map((index) => resolverCategoriaCartaoLinha(index)));
}

function aplicarCategoriaCartaoLote() {
    const categoriaCartaoId = toIntOrNull(document.getElementById('bulkCategoriaCartao')?.value);
    const selecionados = indicesSelecionados();
    if (!selecionados.length) {
        alert('Selecione ao menos uma linha.');
        return;
    }
    if (!categoriaCartaoId) {
        alert('Selecione uma Categoria do Cartao para aplicar.');
        return;
    }

    selecionados.forEach((index) => {
        const linha = estado.linhasMapeadas[index];
        if (!linha) return;
        linha.categoria_cartao_id = categoriaCartaoId;
        linha.categoria_cartao_origem = 'manual';
        linha.categoria_cartao_vinculada_ao_cartao = true;
        if (linha.categoria_id) {
            linha.status = 'valido';
            linha.status_classificacao = 'classificada';
        }
    });

    estado.linhasSelecionadas = new Set();
    invalidarPrevia();
    renderizarEditorPrePersistencia();
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

async function resolverCategoriaCartaoLinha(index) {
    const linha = estado.linhasMapeadas[index];
    const cartaoId = parseInt(document.getElementById('cartaoSelect')?.value || '', 10);
    if (!linha || !linha.categoria_id || !cartaoId) return;
    try {
        estado.linhasMapeadas[index] = aplicarResolucaoCategoriaCartaoLinha(
            linha,
            await buscarResolucaoCategoriaCartao(linha.categoria_id, cartaoId)
        );
        invalidarPrevia();
        renderizarEditorPrePersistencia();
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
    linha.ignorar = !linha.ignorar;
    invalidarPrevia();
    renderizarEditorPrePersistencia();
}

function detalharLinha(index) {
    const linha = estado.linhasMapeadas[index];
    if (!linha) return;

    const categoriaDespesa = nomeCategoriaDespesa(linha.categoria_id) || 'Sem categoria da despesa';
    const categoriaCartao = nomeCategoriaCartao(categoriaCartaoIdLinha(linha)) || 'Sem categoria do cartão';
    alert(
        `Lançamento ${linha.linha_origem || index + 1}\n\n` +
        `Data: ${linha.data_compra}\n` +
        `Descrição: ${linha.descricao_exibida || linha.descricao}\n` +
        `Valor: ${formatarMoeda(linha.valor)}\n` +
        `Parcela: ${linha.parcela || '1/1'}\n` +
        `Categoria da Despesa: ${categoriaDespesa}\n` +
        `Categoria do Cartão: ${categoriaCartao}`
    );
}

function calcularResumoLocal() {
    const linhas = estado.linhasMapeadas;
    const ativas = linhas.filter((linha) => !linha.ignorar);
    const pendentesCartao = ativas.filter((linha) => !categoriaCartaoIdLinha(linha)).length;
    const pendentesDespesa = ativas.filter((linha) => !linha.categoria_id).length;
    const validas = ativas.filter((linha) => linha.categoria_id).length;
    const baixaConfianca = ativas.filter((linha) => statusLinha(linha).classe === 'low-confidence').length;
    const ignoradas = linhas.filter((linha) => linha.ignorar).length;
    const duplicadas = linhas.filter((linha) => linha.status === 'duplicado').length;
    const creditos = linhas.filter((linha) => linha.tipo_movimento === 'credito').length;
    const parceladas = linhas.filter((linha) => Number(linha.total_parcelas) > 1).length;
    const totalPrevisto = ativas.reduce((acc, linha) => acc + (parseValorNumerico(linha.valor) || 0), 0);
    const valorSemCategoriaCartao = ativas
        .filter((linha) => !categoriaCartaoIdLinha(linha))
        .reduce((acc, linha) => acc + (parseValorNumerico(linha.valor) || 0), 0);

    return {
        linhas,
        ativas,
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
    const novos = estado.resumoPrevia ? estado.resumoPrevia.inseridos : resumo.ativas.length;
    const confirmadasCartao = resumo.ativas.filter((linha) => categoriaCartaoIdLinha(linha)).length;

    setText('detectedCount', totalDetectado);
    setText('parceladoCount', resumo.parceladas);
    setText('duplicateCount', duplicados);
    setText('validCount', resumo.validas);
    setText('reviewCount', resumo.revisar);
    setText('missingCardCategoryCount', resumo.pendentesCartao);
    setText('validationDuplicateCount', duplicados);
    setText('plannedTotal', formatarMoeda(resumo.totalPrevisto));
    setText('uncategorizedCardValue', formatarMoeda(resumo.valorSemCategoriaCartao));
    setText('newCount', novos);
    setText('ignoredCount', resumo.ignoradas);
    setText('confirmedCardCategoryCount', `${confirmadasCartao}/${resumo.ativas.length}`);
    setText('pendingCardCategoryCount', `${resumo.pendentesCartao} pendentes`);

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
    const semLinhasAtivas = resumo.ativas.length === 0;
    const temPendenciasObrigatorias = resumo.pendentesDespesa > 0;

    if (btnPrevia) {
        btnPrevia.disabled = semLinhasAtivas || temPendenciasObrigatorias;
    }

    if (btnImportar) {
        btnImportar.disabled = !estado.resumoPrevia || estado.resumoPrevia.inseridos === 0 || temPendenciasObrigatorias;
    }
}

function renderizarClassificacao() {
    const container = document.getElementById('classificationList');
    if (!container) return;

    if (!estado.categoriasCartao.length) {
        container.innerHTML = '<div class="import-empty-state compact">As categorias do cartão aparecem após selecionar o cartão.</div>';
        return;
    }

    const contagens = new Map();
    estado.linhasMapeadas
        .filter((linha) => !linha.ignorar && categoriaCartaoIdLinha(linha))
        .forEach((linha) => {
            const categoriaCartaoId = Number(categoriaCartaoIdLinha(linha));
            contagens.set(categoriaCartaoId, (contagens.get(categoriaCartaoId) || 0) + 1);
        });

    container.innerHTML = estado.categoriasCartao.map((categoria) => {
        const count = contagens.get(Number(categoria.id)) || 0;
        return `
            <div class="import-category-row">
                <span class="import-category-name">
                    <span class="import-category-dot" aria-hidden="true"></span>
                    <span title="${escapeAttr(categoria.nome)}">${escapeHtml(categoria.nome)}</span>
                </span>
                <span class="import-category-count">${count} ${count === 1 ? 'item' : 'itens'}</span>
            </div>
        `;
    }).join('');
}

function montarPayloadImportacao() {
    const cartaoId = parseInt(document.getElementById('cartaoSelect').value, 10);
    const [mes, ano] = document.getElementById('competenciaInput').value.split('/');
    const competencia = `${ano}-${mes}-01`;
    const linhas = estado.linhasMapeadas
        .filter((linha) => !linha.ignorar && linha.tipo_movimento !== 'credito' && linha.status !== 'duplicado')
        .map((linha) => {
            const payload = {
                data_compra: linha.data_compra,
                descricao: linha.descricao || linha.descricao_exibida,
                descricao_exibida: linha.descricao_exibida || linha.descricao,
                valor: linha.valor,
                parcela: linha.parcela || `${linha.numero_parcela || 1}/${linha.total_parcelas || 1}`,
                numero_parcela: linha.numero_parcela || 1,
                total_parcelas: linha.total_parcelas || 1,
                gerar_parcelas_futuras: !!linha.gerar_parcelas_futuras,
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
    const importaveis = resumo.ativas.filter((linha) => linha.tipo_movimento !== 'credito' && linha.status !== 'duplicado');
    if (!importaveis.length) {
        alert('Nenhuma linha restante para importar.');
        return false;
    }
    if (importaveis.some((linha) => !linha.categoria_id)) {
        alert('Existem linhas sem Categoria da Despesa. Ajuste antes da prévia.');
        return false;
    }
    return true;
}

async function previsualizarImportacao() {
    if (!estado.linhasMapeadas.length) {
        alert('Valide perfil e mapeamento antes da prévia.');
        return;
    }
    if (!validarConfiguracaoBasica()) return;
    if (!validarPendenciasObrigatorias()) {
        atualizarResumoPainel();
        return;
    }

    try {
        const payload = montarPayloadImportacao();
        const resposta = await fetch(`${API_BASE}/previsualizar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const dados = await resposta.json();
        if (!resposta.ok || !dados.success) {
            throw new Error(dados.message || 'Falha na pré-visualização');
        }

        estado.resumoPrevia = dados;
        renderResumoPrevia(dados);
        atualizarResumoPainel();
    } catch (error) {
        alert(`Erro na pré-visualização: ${error.message}`);
    }
}

function renderResumoPrevia(dados) {
    const erros = (dados.erros || []).slice(0, 10);
    const duplicados = (dados.amostra_duplicados || []).slice(0, 10);
    const pendencias = dados.pendencias || {};
    const avisosLinhas = (dados.avisos_linhas || []).slice(0, 5);
    const resumo = calcularResumoLocal();
    const futuras = estado.linhasMapeadas.filter((linha) => !linha.ignorar && linha.gerar_parcelas_futuras && Number(linha.total_parcelas) > 1).length;

    document.getElementById('resumoPreviaTecnica').innerHTML = `
        <div class="import-feedback success">
            <strong>Pré-visualização concluída.</strong>
            Total recebido no backend: <strong>${dados.total_recebidas}</strong>.
            Potencial para inserir: <strong>${dados.inseridos}</strong>.
            Duplicados detectados: <strong>${dados.duplicados}</strong>.
            Linhas ignoradas: <strong>${resumo.ignoradas}</strong>.
            Linhas com criação de futuras: <strong>${futuras}</strong>.
            Pendentes de Categoria da Despesa: <strong>${pendencias.categoria_despesa || resumo.pendentesDespesa}</strong>.
            Pendentes de Categoria do Cartão: <strong>${pendencias.categoria_cartao || resumo.pendentesCartao}</strong>.
            Valor sem Categoria do Cartão: <strong>${formatarMoeda(resumo.valorSemCategoriaCartao)}</strong>.
        </div>
        ${avisosLinhas.length ? `
            <div class="import-feedback warning">
                <strong>Avisos de classificação</strong>
                ${avisosLinhas.map((item) => `<div>Linha ${escapeHtml(item.linha || '-')}: ${(item.avisos || []).map(escapeHtml).join(' | ')}</div>`).join('')}
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
    if (!estado.resumoPrevia) {
        alert('Gere a pré-visualização técnica antes de importar.');
        return;
    }
    if (!validarPendenciasObrigatorias()) {
        atualizarResumoPainel();
        return;
    }
    if (estado.resumoPrevia.inseridos === 0) {
        alert('Não há linhas novas para importar.');
        return;
    }

    const resumo = calcularResumoLocal();
    const futuras = estado.linhasMapeadas.filter((linha) => !linha.ignorar && linha.gerar_parcelas_futuras && Number(linha.total_parcelas) > 1).length;
    const confirmado = confirm(
        `Confirmar importação?\n\n` +
        `Inseridos esperados: ${estado.resumoPrevia.inseridos}\n` +
        `Duplicados esperados: ${estado.resumoPrevia.duplicados}\n` +
        `Linhas ignoradas: ${resumo.ignoradas}\n` +
        `Linhas com futuras: ${futuras}\n` +
        `Categorias do cartão pendentes: ${resumo.pendentesCartao}`
    );
    if (!confirmado) return;

    try {
        const payload = montarPayloadImportacao();
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
