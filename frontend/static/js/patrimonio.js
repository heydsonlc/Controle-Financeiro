const API_BASE = '/api/patrimonio';

const estadoPatrimonio = {
    contas: [],
    transferencias: [],
    bens: [],
    documentos: [],
    imagens: [],
    resumoBens: null,
    busca: '',
    aba: 'contas',
    modoEmpresa: false,
    bemSelecionadoId: null,
};

let contaAtual = null;

document.addEventListener('DOMContentLoaded', () => {
    inicializarPreviewCaixinha();
    inicializarPatrimonioContextual();
});

function patrimonioIcon(name) {
    const icons = {
        edit: '<path d="M5 19h4L19 9a2.1 2.1 0 0 0-3-3L6 16l-1 3Z"/><path d="M14 6l4 4"/>',
        inactive: '<path d="M6 6l12 12"/><path d="M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z"/>',
        calendar: '<path d="M7 4v3M17 4v3M5 9h14"/><path d="M5 6h14v14H5V6Z"/>',
        note: '<path d="M6 4h9l3 3v13H6V4Z"/><path d="M15 4v4h4"/><path d="M9 13h6M9 17h4"/>',
        trash: '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>',
        arrow: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
        transfer: '<path d="M7 7h10"/><path d="m14 4 3 3-3 3"/><path d="M17 17H7"/><path d="m10 14-3 3 3 3"/>',
        view: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z"/><circle cx="12" cy="12" r="3"/>',
        wallet: '<path d="M5 8h14v11H5z"/><path d="M8 8V6h8v2"/><path d="M16 13h2"/>',
        home: '<path d="m4 11 8-7 8 7"/><path d="M6 10v10h12V10"/><path d="M10 20v-6h4v6"/>',
        plane: '<path d="M10 21 12 13 3 8l2-2 10 4 4-7 2 2-4 7 4 10-2 2-5-9-8 2-2 2Z"/>',
        shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-5"/>',
        chart: '<path d="M4 19h16"/><path d="m7 16 4-4 3 3 5-7"/><path d="M17 8h2v2"/>',
        box: '<path d="M4 7h16v12H4z"/><path d="M8 7V5h8v2"/><path d="M8 13h8"/>',
    };
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${icons[name] || icons.wallet}</svg>`;
}

function inicializarPreviewCaixinha() {
    ['conta-nome', 'conta-tipo', 'conta-cor', 'conta-saldo-inicial', 'conta-meta'].forEach((id) => {
        document.getElementById(id)?.addEventListener('input', atualizarPreviewCaixinha);
        document.getElementById(id)?.addEventListener('change', atualizarPreviewCaixinha);
    });
}

async function inicializarPatrimonioContextual() {
    configurarEventosEmpresa();
    const perfil = await obterPerfilAtivo();
    if (perfil?.tipo === 'EMPRESA') {
        ativarModoEmpresa();
        await carregarPatrimonioEmpresarial();
    } else {
        ativarModoPessoal();
    }
}

async function obterPerfilAtivo() {
    try {
        const response = await fetch('/api/perfis-financeiros/ativo');
        if (!response.ok) return null;
        const result = await response.json();
        return result.perfil_ativo || null;
    } catch (error) {
        return null;
    }
}

function ativarModoPessoal() {
    estadoPatrimonio.modoEmpresa = false;
    document.body.classList.remove('patrimonio-empresa-mode');
    document.getElementById('patrimonio-empresarial')?.setAttribute('hidden', '');
    document.getElementById('patrimonio-pessoal')?.removeAttribute('hidden');
    carregarContas();
    carregarTransferencias();
}

function ativarModoEmpresa() {
    estadoPatrimonio.modoEmpresa = true;
    document.body.classList.add('patrimonio-empresa-mode');
    document.getElementById('patrimonio-pessoal')?.setAttribute('hidden', '');
    document.getElementById('patrimonio-empresarial')?.removeAttribute('hidden');
    const pageTitle = document.querySelector('.app-topbar-title span');
    if (pageTitle) pageTitle.textContent = 'Patrimonio Empresarial';
}

function configurarEventosEmpresa() {
    if (document.body.dataset.patrimonioEmpresaBound === 'true') return;
    document.body.dataset.patrimonioEmpresaBound = 'true';

    ['bem-filtro-categoria', 'bem-filtro-status', 'bem-filtro-documento'].forEach((id) => {
        document.getElementById(id)?.addEventListener('change', carregarPatrimonioEmpresarial);
    });
    document.getElementById('bem-busca')?.addEventListener('input', debounce(carregarPatrimonioEmpresarial, 260));
    document.getElementById('btn-atualizar-bens')?.addEventListener('click', carregarPatrimonioEmpresarial);
    document.getElementById('btn-novo-bem')?.addEventListener('click', abrirModalNovoBem);
    document.getElementById('btn-importar-nota')?.addEventListener('click', () => { window.location.href = '/imposto-renda'; });
    document.getElementById('btn-vincular-documento')?.addEventListener('click', () => abrirModalVincularBem());
    document.getElementById('form-bem')?.addEventListener('submit', salvarBemEmpresarial);
    document.getElementById('form-vincular-bem')?.addEventListener('submit', salvarVinculoBem);
    document.getElementById('btn-criar-bem-documento')?.addEventListener('click', criarBemAPartirDocumento);
}

async function carregarPatrimonioEmpresarial() {
    try {
        const params = montarParamsBens();
        const [resumo, bens, documentos, imagens] = await Promise.all([
            fetchJson(`${API_BASE}/bens/resumo`),
            fetchJson(`${API_BASE}/bens?${params.toString()}`),
            fetchJson(`${API_BASE}/documentos-vinculaveis`),
            fetchJson(`${API_BASE}/bens/imagens`),
        ]);

        estadoPatrimonio.resumoBens = resumo.data || {};
        estadoPatrimonio.bens = bens.data || [];
        estadoPatrimonio.documentos = documentos.data || [];
        estadoPatrimonio.imagens = imagens.data || [];

        renderizarFiltrosCategoriaBens();
        renderizarResumoBens();
        renderizarTabelaBens();
        renderizarComposicaoBens();
        renderizarPendenciasBens();
        renderizarOpcoesDocumentos();
        if (!estadoPatrimonio.bemSelecionadoId && estadoPatrimonio.bens.length) {
            estadoPatrimonio.bemSelecionadoId = estadoPatrimonio.bens[0].id;
        }
        renderizarDetalheBem();
    } catch (error) {
        mostrarErro('Erro ao carregar patrimonio empresarial');
    }
}

function montarParamsBens() {
    const params = new URLSearchParams();
    const categoria = document.getElementById('bem-filtro-categoria')?.value;
    const status = document.getElementById('bem-filtro-status')?.value;
    const documento = document.getElementById('bem-filtro-documento')?.value;
    const busca = document.getElementById('bem-busca')?.value;
    if (categoria) params.set('categoria', categoria);
    if (status) params.set('status', status);
    if (documento) params.set('documento', documento);
    if (busca) params.set('busca', busca);
    return params;
}

function renderizarFiltrosCategoriaBens() {
    const select = document.getElementById('bem-filtro-categoria');
    if (!select) return;
    const valorAtual = select.value;
    const categorias = [...new Set(estadoPatrimonio.bens.map((bem) => bem.categoria).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
    select.innerHTML = '<option value="">Todas</option>' + categorias.map((categoria) => `<option value="${escapeHtml(categoria)}">${escapeHtml(categoria)}</option>`).join('');
    select.value = categorias.includes(valorAtual) ? valorAtual : '';
}

function renderizarResumoBens() {
    const resumo = estadoPatrimonio.resumoBens || {};
    setText('bem-kpi-total', formatarMoedaDisplay(resumo.patrimonio_total || 0));
    setText('bem-kpi-total-legenda', `${resumo.bens_cadastrados || 0} bens cadastrados`);
    setText('bem-kpi-lastro', resumo.bens_com_lastro || 0);
    setText('bem-kpi-lastro-legenda', `${Number(resumo.percentual_com_lastro || 0).toFixed(1)}% do total`);
    setText('bem-kpi-pendencias', resumo.pendencias_documentais || 0);
    setText('bem-kpi-aquisicoes', formatarMoedaDisplay(resumo.aquisicoes_ano?.valor || 0));
    setText('bem-kpi-aquisicoes-legenda', `${resumo.aquisicoes_ano?.quantidade || 0} novos bens`);
    setText('bens-pendencias-count', resumo.pendencias_documentais || 0);
}

function renderizarTabelaBens() {
    const tbody = document.getElementById('bens-tabela-corpo');
    if (!tbody) return;
    setText('bens-lista-meta', `${estadoPatrimonio.bens.length} ${estadoPatrimonio.bens.length === 1 ? 'bem exibido' : 'bens exibidos'}`);
    if (!estadoPatrimonio.bens.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7">
                    <div class="empty-state">
                        <strong>Nenhum bem patrimonial cadastrado.</strong>
                        <span>Crie um bem ou selecione uma nota fiscal ja importada para iniciar o lastro.</span>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = estadoPatrimonio.bens.map((bem) => `
        <tr class="${bem.id === estadoPatrimonio.bemSelecionadoId ? 'selected' : ''}" onclick="selecionarBemEmpresarial(${bem.id})">
            <td>
                <div class="bem-cell">
                    ${miniaturaBem(bem)}
                    <div>
                        <strong>${escapeHtml(bem.nome)}</strong>
                        <small>${escapeHtml(bem.codigo || 'Sem tag')}</small>
                    </div>
                </div>
            </td>
            <td>${escapeHtml(bem.categoria || '-')}</td>
            <td>${formatarData(bem.data_aquisicao)}</td>
            <td><strong>${formatarMoedaDisplay(bem.valor_aquisicao || 0)}</strong></td>
            <td>${escapeHtml(bem.documento_label || 'Sem documento')}</td>
            <td><span class="bem-status ${classeStatusDocumento(bem.status_documental)}">${escapeHtml(bem.status_documental_label || '-')}</span></td>
            <td>
                <div class="bem-row-actions">
                    <button class="row-action-button" type="button" onclick="event.stopPropagation(); abrirModalEditarBem(${bem.id})" title="Editar" aria-label="Editar">${patrimonioIcon('edit')}</button>
                    <button class="row-action-button" type="button" onclick="event.stopPropagation(); abrirModalVincularBem(${bem.id})" title="Vincular documento" aria-label="Vincular documento">${patrimonioIcon('view')}</button>
                </div>
            </td>
        </tr>
    `).join('');
}

function renderizarComposicaoBens() {
    const container = document.getElementById('bens-composicao');
    if (!container) return;
    const composicao = estadoPatrimonio.resumoBens?.composicao || [];
    const total = estadoPatrimonio.resumoBens?.patrimonio_total || 0;
    if (!composicao.length) {
        container.innerHTML = '<div class="empty-state"><strong>Sem imobilizado.</strong><span>Cadastre bens com valor para visualizar a composicao.</span></div>';
        return;
    }
    const cores = ['#2563eb', '#10b981', '#f59e0b', '#8b5cf6', '#0ea5e9', '#ef4444'];
    let cursor = 0;
    const gradiente = composicao.map((item, index) => {
        const inicio = cursor;
        const fim = cursor + Number(item.percentual || 0);
        cursor = fim;
        return `${cores[index % cores.length]} ${inicio}% ${fim}%`;
    }).join(', ');
    container.innerHTML = `
        <div class="patrimonio-donut" style="background: conic-gradient(${gradiente});">
            <span>Total</span>
            <strong>${formatarMoedaDisplay(total)}</strong>
        </div>
        <div class="patrimonio-composition-list">
            ${composicao.map((item, index) => `
                <div class="patrimonio-composition-line">
                    <span class="patrimonio-composition-name"><i style="--cor-conta:${cores[index % cores.length]}"></i>${escapeHtml(item.categoria)}</span>
                    <strong>${Number(item.percentual || 0).toFixed(1)}%</strong>
                    <span>${formatarMoedaDisplay(item.valor || 0)}</span>
                </div>
            `).join('')}
        </div>
    `;
}

function renderizarPendenciasBens() {
    const container = document.getElementById('bens-pendencias');
    if (!container) return;
    const pendencias = estadoPatrimonio.resumoBens?.pendencias_prioritarias || [];
    if (!pendencias.length) {
        container.innerHTML = '<div class="empty-state"><strong>Nenhuma pendencia documental.</strong><span>Todos os bens cadastrados estao com lastro ou excecao tratada.</span></div>';
        return;
    }
    container.innerHTML = pendencias.map((bem) => `
        <button type="button" class="pendencia-bem-item" onclick="selecionarBemEmpresarial(${bem.id})">
            <span>${patrimonioIcon('note')}</span>
            <strong>${escapeHtml(bem.nome)}</strong>
            <small>${escapeHtml(bem.status_documental_label || 'Pendente')}</small>
        </button>
    `).join('');
}

function renderizarDetalheBem() {
    const container = document.getElementById('bem-detalhe');
    if (!container) return;
    const bem = estadoPatrimonio.bens.find((item) => item.id === estadoPatrimonio.bemSelecionadoId);
    if (!bem) {
        container.innerHTML = '<div class="empty-state"><strong>Selecione um bem.</strong><span>O detalhe exibe documento fiscal, fornecedor, valor, local e status documental.</span></div>';
        return;
    }
    container.innerHTML = `
        <div class="patrimonio-panel-header">
            <div>
                <h2>Detalhe do bem selecionado</h2>
                <small>${escapeHtml(bem.status_documental_label || '-')}</small>
            </div>
            <div class="bem-detail-actions">
                <button type="button" class="patrimonio-secondary-btn" onclick="verDocumentoBem(${bem.id})">Ver documento</button>
                <button type="button" class="patrimonio-primary-btn" onclick="abrirModalEditarBem(${bem.id})">Editar bem</button>
            </div>
        </div>
        <div class="bem-detail-card">
            ${miniaturaBem(bem, true)}
            <div class="bem-detail-main">
                <h3>${escapeHtml(bem.nome)}</h3>
                <p>${escapeHtml(bem.codigo || 'Sem tag')} &middot; ${escapeHtml(bem.categoria || 'Sem categoria')}</p>
                <small>${escapeHtml(bem.descricao || 'Sem descricao cadastrada.')}</small>
            </div>
            <span class="bem-status ${classeStatusDocumento(bem.status_documental)}">${escapeHtml(bem.status_documental_label || '-')}</span>
            <dl class="bem-detail-grid">
                <div><dt>Fornecedor</dt><dd>${escapeHtml(bem.fornecedor || '-')}</dd></div>
                <div><dt>Numero da nota</dt><dd>${escapeHtml(bem.documento_numero || '-')}</dd></div>
                <div><dt>Data da compra</dt><dd>${formatarData(bem.data_aquisicao)}</dd></div>
                <div><dt>Valor de aquisicao</dt><dd>${formatarMoedaDisplay(bem.valor_aquisicao || 0)}</dd></div>
                <div><dt>Vida util estimada</dt><dd>${bem.vida_util_meses ? `${bem.vida_util_meses} meses` : '-'}</dd></div>
                <div><dt>Depreciacao mensal</dt><dd>${bem.depreciacao_mensal ? formatarMoedaDisplay(bem.depreciacao_mensal) : '-'}</dd></div>
                <div><dt>Centro de custo</dt><dd>${escapeHtml(bem.centro_custo || '-')}</dd></div>
                <div><dt>Localizacao</dt><dd>${escapeHtml(bem.localizacao || '-')}</dd></div>
                <div><dt>Responsavel</dt><dd>${escapeHtml(bem.responsavel || '-')}</dd></div>
                <div><dt>Documento fiscal</dt><dd>${escapeHtml(bem.documento_label || 'Sem documento')}</dd></div>
            </dl>
        </div>
    `;
}

function selecionarBemEmpresarial(id) {
    estadoPatrimonio.bemSelecionadoId = id;
    renderizarTabelaBens();
    renderizarDetalheBem();
}

function renderizarOpcoesDocumentos() {
    const options = '<option value="">Sem documento vinculado</option>' + estadoPatrimonio.documentos.map((doc) => (
        `<option value="${doc.id}">${escapeHtml(doc.label)}</option>`
    )).join('');
    const vinculoOptions = '<option value="">Selecione um documento...</option>' + estadoPatrimonio.documentos.map((doc) => (
        `<option value="${doc.id}">${escapeHtml(doc.label)}</option>`
    )).join('');
    const bemSelect = document.getElementById('bem-comprovante');
    const vinculoSelect = document.getElementById('vinculo-comprovante');
    if (bemSelect) bemSelect.innerHTML = options;
    if (vinculoSelect) vinculoSelect.innerHTML = vinculoOptions;
}

function renderizarImagensBens() {
    const grid = document.getElementById('bem-imagens-grid');
    if (!grid) return;
    const selecionada = document.getElementById('bem-imagem-arquivo')?.value || '';
    if (!estadoPatrimonio.imagens.length) {
        grid.innerHTML = '<div class="empty-state"><strong>Sem imagens locais.</strong><span>O cadastro usara o icone padrao.</span></div>';
        return;
    }
    grid.innerHTML = estadoPatrimonio.imagens.map((imagem) => `
        <button type="button" class="bem-image-option ${imagem.arquivo === selecionada ? 'selected' : ''}" data-bem-imagem="${escapeHtml(imagem.arquivo)}">
            <img src="${escapeHtml(imagem.url)}" alt="${escapeHtml(imagem.label)}">
            <span>${escapeHtml(imagem.label)}</span>
        </button>
    `).join('');
    grid.querySelectorAll('[data-bem-imagem]').forEach((button) => {
        button.addEventListener('click', () => selecionarImagemBem(button.dataset.bemImagem));
    });
}

function selecionarImagemBem(arquivo) {
    setValue('bem-imagem-arquivo', arquivo || '');
    renderizarImagensBens();
}

async function abrirModalNovoBem() {
    document.getElementById('form-bem')?.reset();
    setValue('bem-id', '');
    setValue('bem-imagem-arquivo', '');
    setValue('bem-status-documental', 'SEM_DOCUMENTO');
    await garantirDadosAuxiliaresBens();
    renderizarOpcoesDocumentos();
    renderizarImagensBens();
    abrirModal('modal-bem');
}

async function abrirModalEditarBem(id) {
    const bem = estadoPatrimonio.bens.find((item) => item.id === id);
    if (!bem) return;
    await garantirDadosAuxiliaresBens();
    preencherFormBem(bem);
    renderizarOpcoesDocumentos();
    renderizarImagensBens();
    abrirModal('modal-bem');
}

function preencherFormBem(bem) {
    setValue('bem-id', bem.id);
    setValue('bem-nome', bem.nome || '');
    setValue('bem-codigo', bem.codigo || '');
    setValue('bem-categoria', bem.categoria || 'Equipamentos');
    setValue('bem-status-documental', bem.status_documental || 'SEM_DOCUMENTO');
    setValue('bem-descricao', bem.descricao || '');
    setValue('bem-imagem-arquivo', bem.imagem_arquivo || '');
    setValue('bem-valor', bem.valor_aquisicao ? formatarMoedaDisplay(bem.valor_aquisicao) : '');
    setValue('bem-data', bem.data_aquisicao || '');
    setValue('bem-fornecedor', bem.fornecedor || '');
    setValue('bem-documento-numero', bem.documento_numero || '');
    setValue('bem-comprovante', '');
    setValue('bem-vida-util', bem.vida_util_meses || '');
    setValue('bem-centro-custo', bem.centro_custo || '');
    setValue('bem-localizacao', bem.localizacao || '');
    setValue('bem-responsavel', bem.responsavel || '');
    setValue('bem-observacoes', bem.observacoes || '');
}

async function salvarBemEmpresarial(event) {
    event.preventDefault();
    const id = document.getElementById('bem-id')?.value;
    const dados = dadosFormBem();
    try {
        const response = await fetch(id ? `${API_BASE}/bens/${id}` : `${API_BASE}/bens`, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados),
        });
        const result = await response.json();
        if (!result.success) {
            mostrarErro(result.error);
            return;
        }
        mostrarSucesso(result.message || 'Bem salvo');
        fecharModal('modal-bem');
        estadoPatrimonio.bemSelecionadoId = result.data?.id || estadoPatrimonio.bemSelecionadoId;
        await carregarPatrimonioEmpresarial();
    } catch (error) {
        mostrarErro('Erro ao salvar bem');
    }
}

async function criarBemAPartirDocumento() {
    const dados = dadosFormBem();
    if (!dados.comprovante_id) {
        mostrarErro('Selecione um documento fiscal para criar o bem.');
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/bens/criar-a-partir-documento`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados),
        });
        const result = await response.json();
        if (!result.success) {
            mostrarErro(result.error);
            return;
        }
        mostrarSucesso(result.message || 'Bem criado a partir do documento');
        fecharModal('modal-bem');
        estadoPatrimonio.bemSelecionadoId = result.data?.id;
        await carregarPatrimonioEmpresarial();
    } catch (error) {
        mostrarErro('Erro ao criar bem a partir do documento');
    }
}

function dadosFormBem() {
    return {
        nome: document.getElementById('bem-nome')?.value,
        codigo: document.getElementById('bem-codigo')?.value,
        categoria: document.getElementById('bem-categoria')?.value,
        status_documental: document.getElementById('bem-status-documental')?.value,
        descricao: document.getElementById('bem-descricao')?.value,
        imagem_arquivo: document.getElementById('bem-imagem-arquivo')?.value,
        valor_aquisicao: parseMoeda(document.getElementById('bem-valor')?.value),
        data_aquisicao: document.getElementById('bem-data')?.value,
        fornecedor: document.getElementById('bem-fornecedor')?.value,
        documento_numero: document.getElementById('bem-documento-numero')?.value,
        comprovante_id: Number(document.getElementById('bem-comprovante')?.value) || null,
        vida_util_meses: Number(document.getElementById('bem-vida-util')?.value) || null,
        centro_custo: document.getElementById('bem-centro-custo')?.value,
        localizacao: document.getElementById('bem-localizacao')?.value,
        responsavel: document.getElementById('bem-responsavel')?.value,
        observacoes: document.getElementById('bem-observacoes')?.value,
    };
}

async function abrirModalVincularBem(id) {
    const bemId = id || estadoPatrimonio.bemSelecionadoId;
    if (!bemId) {
        mostrarErro('Selecione um bem para vincular documento.');
        return;
    }
    await garantirDadosAuxiliaresBens();
    renderizarOpcoesDocumentos();
    setValue('vinculo-bem-id', bemId);
    setValue('vinculo-comprovante', '');
    setValue('vinculo-tipo', 'NOTA_FISCAL');
    setValue('vinculo-natureza', 'PATRIMONIO_IMOBILIZADO');
    setValue('vinculo-observacoes', '');
    abrirModal('modal-vincular-bem');
}

async function salvarVinculoBem(event) {
    event.preventDefault();
    const bemId = document.getElementById('vinculo-bem-id')?.value;
    const dados = {
        comprovante_id: Number(document.getElementById('vinculo-comprovante')?.value),
        tipo_vinculo: document.getElementById('vinculo-tipo')?.value,
        natureza: document.getElementById('vinculo-natureza')?.value,
        observacoes: document.getElementById('vinculo-observacoes')?.value,
    };
    try {
        const response = await fetch(`${API_BASE}/bens/${bemId}/vincular-documento`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados),
        });
        const result = await response.json();
        if (!result.success) {
            mostrarErro(result.error);
            return;
        }
        mostrarSucesso(result.message || 'Documento vinculado');
        fecharModal('modal-vincular-bem');
        estadoPatrimonio.bemSelecionadoId = result.data?.id || Number(bemId);
        await carregarPatrimonioEmpresarial();
    } catch (error) {
        mostrarErro('Erro ao vincular documento');
    }
}

async function garantirDadosAuxiliaresBens() {
    if (estadoPatrimonio.documentos.length && estadoPatrimonio.imagens.length) return;
    const [documentos, imagens] = await Promise.all([
        fetchJson(`${API_BASE}/documentos-vinculaveis`),
        fetchJson(`${API_BASE}/bens/imagens`),
    ]);
    estadoPatrimonio.documentos = documentos.data || [];
    estadoPatrimonio.imagens = imagens.data || [];
}

function verDocumentoBem(id) {
    const bem = estadoPatrimonio.bens.find((item) => item.id === id);
    const documentoId = bem?.documento?.id;
    if (!documentoId) {
        mostrarErro('Este bem ainda nao possui documento vinculado.');
        return;
    }
    window.open(`/api/ir/comprovantes/${documentoId}/arquivo`, '_blank', 'noopener');
}

function miniaturaBem(bem, grande = false) {
    const url = bem.imagem_url || imagemUrlPorChave(bem.imagem_chave);
    const classe = grande ? 'bem-thumb large' : 'bem-thumb';
    if (url) {
        return `<span class="${classe}"><img src="${escapeHtml(url)}" alt="${escapeHtml(bem.nome || 'Bem patrimonial')}"></span>`;
    }
    return `<span class="${classe} fallback">${patrimonioIcon('box')}</span>`;
}

function imagemUrlPorChave(chave) {
    if (!chave || !estadoPatrimonio.imagens.length) return null;
    const aliases = {
        notebook: ['notebook', 'laptop'],
        cadeira: ['cadeira'],
        moveis: ['mesa', 'movel', 'moveis', 'móveis'],
        impressora: ['impressora'],
        ar_condicionado: ['ar condicionado', 'ar_condicionado', 'condicionado'],
        monitor: ['monitor'],
        webcam: ['webcam'],
        placa_video: ['placa video', 'placa_de_video', 'gpu'],
        equipamento: ['equipamento'],
    };
    const termos = aliases[chave] || [chave];
    const imagem = estadoPatrimonio.imagens.find((item) => {
        const arquivo = normalizarBusca(item.arquivo).replace(/_/g, ' ');
        return termos.some((termo) => arquivo.includes(normalizarBusca(termo).replace(/_/g, ' ')));
    });
    return imagem?.url || null;
}

function classeStatusDocumento(status) {
    if (status === 'COM_LASTRO') return 'ok';
    if (status === 'NAO_APLICAVEL') return 'neutral';
    if (status === 'AGUARDANDO_CONTADOR') return 'info';
    if (status === 'DIVERGENTE') return 'danger';
    return 'warn';
}

async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok || result.success === false) {
        throw new Error(result.error || 'Erro de API');
    }
    return result;
}

function debounce(fn, delay) {
    let timeoutId;
    return (...args) => {
        window.clearTimeout(timeoutId);
        timeoutId = window.setTimeout(() => fn(...args), delay);
    };
}

function mostrarAba(aba, button) {
    estadoPatrimonio.aba = aba;
    document.querySelectorAll('.patrimonio-view-tab').forEach((item) => item.classList.remove('active'));
    if (button) {
        button.classList.add('active');
    } else {
        document.querySelector(`.patrimonio-view-tab[onclick*="${aba}"]`)?.classList.add('active');
    }

    document.querySelectorAll('.tab-content').forEach((content) => content.classList.remove('active'));
    document.getElementById(`aba-${aba}`)?.classList.add('active');

    if (aba === 'transferencias') {
        carregarTransferencias();
    }
}

function filtrarPatrimonio() {
    estadoPatrimonio.busca = normalizarBusca(document.getElementById('patrimonio-busca')?.value);
    renderizarCaixinhas();
    renderizarTransferencias();
}

async function carregarContas() {
    try {
        const response = await fetch(`${API_BASE}/contas`);
        const result = await response.json();
        if (result.success) {
            estadoPatrimonio.contas = result.data || [];
            atualizarResumo(estadoPatrimonio.contas, result.total_patrimonio || 0);
            renderizarCaixinhas();
            renderizarComposicao();
            renderizarMetas();
            atualizarInsight();
        }
    } catch (error) {
        mostrarErro('Erro ao carregar contas');
    }
}

function renderizarCaixinhas() {
    const lista = document.getElementById('caixinhas-lista');
    if (!lista) return;

    let contas = filtrarContas(estadoPatrimonio.contas);
    const ordenacao = document.getElementById('patrimonio-ordenacao')?.value || 'nome';
    contas = ordenarContas(contas, ordenacao);

    document.getElementById('patrimonio-lista-meta').textContent = `${contas.length} ${contas.length === 1 ? 'caixinha exibida' : 'caixinhas exibidas'}`;
    document.getElementById('patrimonio-total-exibido').textContent = `Exibindo ${contas.length} de ${estadoPatrimonio.contas.length} caixinhas`;

    if (!contas.length) {
        lista.innerHTML = `
            <div class="empty-state">
                <strong>Nenhuma caixinha cadastrada.</strong>
                <span>Crie uma caixinha para organizar reservas, metas e investimentos.</span>
                <button type="button" class="patrimonio-primary-btn" onclick="abrirModalNovaConta()">Nova caixinha</button>
            </div>
        `;
        return;
    }

    lista.innerHTML = contas.map((conta) => criarCardConta(conta)).join('');
}

function filtrarContas(contas) {
    if (!estadoPatrimonio.busca) return contas;
    return contas.filter((conta) => {
        const texto = normalizarBusca(`${conta.nome} ${conta.tipo || ''} ${conta.observacoes || ''}`);
        return texto.includes(estadoPatrimonio.busca);
    });
}

function ordenarContas(contas, ordenacao) {
    return [...contas].sort((a, b) => {
        if (ordenacao === 'saldo') return Number(b.saldo_atual || 0) - Number(a.saldo_atual || 0);
        if (ordenacao === 'meta') return progressoMeta(b) - progressoMeta(a);
        return String(a.nome || '').localeCompare(String(b.nome || ''), 'pt-BR');
    });
}

function criarCardConta(conta) {
    const progresso = progressoMeta(conta);
    const saldo = Number(conta.saldo_atual || 0);
    const meta = Number(conta.meta || 0);
    const restante = Math.max(meta - saldo, 0);
    const tipo = conta.tipo || 'Caixinha';

    return `
        <article class="caixinha-card" style="--cor-conta:${escapeHtml(conta.cor || '#2563eb')}">
            <div class="caixinha-main">
                <span class="caixinha-icon" aria-hidden="true">${iconePorTipo(tipo)}</span>
                <div class="caixinha-info">
                    <h3>${escapeHtml(conta.nome)}</h3>
                    <small><i class="tipo-dot"></i>Tipo: ${escapeHtml(tipo)}</small>
                </div>
            </div>
            <div class="caixinha-metric">
                <span>Saldo atual</span>
                <strong class="money">${formatarMoedaDisplay(saldo)}</strong>
            </div>
            <div class="caixinha-metric">
                <span>Meta</span>
                <strong>${meta ? formatarMoedaDisplay(meta) : '-'}</strong>
            </div>
            <div class="caixinha-progress">
                <strong>${meta ? `${progresso.toFixed(1)}%` : '-'}</strong>
                <div class="progress-track"><span style="width:${Math.min(progresso, 100)}%"></span></div>
                <small>${meta ? `${formatarMoedaDisplay(restante)} restantes` : 'Sem meta definida'}</small>
            </div>
            <span class="caixinha-badge ${conta.ativo ? '' : 'inativo'}">${conta.ativo ? 'Ativa' : 'Inativa'}</span>
            <div class="caixinha-actions">
                <button class="row-action-button" type="button" onclick="editarConta(${conta.id})" title="Editar" aria-label="Editar">${patrimonioIcon('edit')}</button>
                <button class="row-action-button" type="button" onclick="abrirModalNovaTransferencia(${conta.id})" title="Transferir" aria-label="Transferir">${patrimonioIcon('transfer')}</button>
                <button class="row-action-button danger" type="button" onclick="inativarConta(${conta.id})" title="${conta.ativo ? 'Inativar' : 'Ativar'}" aria-label="${conta.ativo ? 'Inativar' : 'Ativar'}">${patrimonioIcon('inactive')}</button>
            </div>
        </article>
    `;
}

function atualizarResumo(contas, total) {
    const ativas = contas.filter((conta) => conta.ativo);
    const inativas = contas.length - ativas.length;
    const metaTotal = ativas.reduce((sum, conta) => sum + Number(conta.meta || 0), 0);
    const progresso = metaTotal ? (Number(total || 0) / metaTotal) * 100 : 0;
    const maior = ativas.reduce((acc, conta) => (Number(conta.saldo_atual || 0) > Number(acc?.saldo_atual || -1) ? conta : acc), null);

    setText('patrimonio-total', formatarMoedaDisplay(total || 0));
    setText('total-caixinhas', ativas.length);
    setText('patrimonio-inativas', `${inativas} ${inativas === 1 ? 'inativa' : 'inativas'}`);
    setText('patrimonio-meta-total', formatarMoedaDisplay(metaTotal));
    setText('patrimonio-meta-progresso', `${progresso.toFixed(1)}% da meta atingida`);
    setText('patrimonio-maior-saldo', formatarMoedaDisplay(maior?.saldo_atual || 0));
    setText('patrimonio-maior-caixinha', maior?.nome || 'Nenhuma caixinha');
}

function renderizarComposicao() {
    const container = document.getElementById('patrimonio-composicao');
    if (!container) return;

    const contas = estadoPatrimonio.contas.filter((conta) => conta.ativo && Number(conta.saldo_atual || 0) > 0);
    const total = contas.reduce((sum, conta) => sum + Number(conta.saldo_atual || 0), 0);
    if (!contas.length || total <= 0) {
        container.innerHTML = '<div class="empty-state"><strong>Sem saldo para compor.</strong><span>Cadastre caixinhas com saldo para visualizar a distribui&ccedil;&atilde;o.</span></div>';
        return;
    }

    container.innerHTML = `
        <div class="patrimonio-donut" style="${gerarDonut(contas, total)}">
            <span>Total</span>
            <strong>${formatarMoedaDisplay(total)}</strong>
        </div>
        <div class="patrimonio-composition-list">
            ${contas.map((conta) => {
                const percentual = (Number(conta.saldo_atual || 0) / total) * 100;
                return `
                    <div class="patrimonio-composition-line">
                        <span class="patrimonio-composition-name"><i style="--cor-conta:${escapeHtml(conta.cor || '#2563eb')}"></i>${escapeHtml(conta.nome)}</span>
                        <strong>${percentual.toFixed(1)}%</strong>
                        <span>${formatarMoedaDisplay(conta.saldo_atual)}</span>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

function renderizarMetas() {
    const container = document.getElementById('patrimonio-metas');
    if (!container) return;

    const metas = estadoPatrimonio.contas
        .filter((conta) => conta.ativo && Number(conta.meta || 0) > 0)
        .sort((a, b) => progressoMeta(b) - progressoMeta(a))
        .slice(0, 3);

    if (!metas.length) {
        container.innerHTML = '<div class="empty-state"><strong>Nenhuma meta definida.</strong><span>Inclua uma meta em uma caixinha para acompanhar o progresso.</span></div>';
        return;
    }

    container.innerHTML = metas.map((conta) => `
        <article class="patrimonio-goal-item" style="--cor-conta:${escapeHtml(conta.cor || '#2563eb')}">
            <span class="patrimonio-goal-icon" aria-hidden="true">${iconePorTipo(conta.tipo)}</span>
            <div>
                <strong>${escapeHtml(conta.nome)}</strong>
                <small>${progressoMeta(conta).toFixed(1)}% da meta atingida</small>
            </div>
            <strong>${formatarMoedaDisplay(conta.meta)}</strong>
        </article>
    `).join('');
}

function atualizarInsight() {
    const ativas = estadoPatrimonio.contas.filter((conta) => conta.ativo);
    const total = ativas.reduce((sum, conta) => sum + Number(conta.saldo_atual || 0), 0);
    const meta = ativas.reduce((sum, conta) => sum + Number(conta.meta || 0), 0);
    const progresso = meta ? (total / meta) * 100 : 0;
    const texto = meta
        ? `Voce atingiu ${progresso.toFixed(1)}% das suas metas. Continue mantendo a consistencia nos aportes.`
        : 'Defina metas nas caixinhas para acompanhar a evolucao do patrimonio.';
    setText('patrimonio-insight', texto);
}

async function carregarTransferencias() {
    try {
        const response = await fetch(`${API_BASE}/transferencias`);
        const result = await response.json();
        if (result.success) {
            estadoPatrimonio.transferencias = result.data || [];
            renderizarTransferencias();
        }
    } catch (error) {
        mostrarErro('Erro ao carregar transferencias');
    }
}

function renderizarTransferencias() {
    const lista = document.getElementById('transferencias-lista');
    if (!lista) return;

    const transferencias = estadoPatrimonio.transferencias.filter((transferencia) => {
        if (!estadoPatrimonio.busca) return true;
        const texto = normalizarBusca(`${transferencia.conta_origem_nome || ''} ${transferencia.conta_destino_nome || ''} ${transferencia.descricao || ''}`);
        return texto.includes(estadoPatrimonio.busca);
    });

    if (!transferencias.length) {
        lista.innerHTML = '<div class="empty-state"><strong>Nenhuma transferencia registrada.</strong><span>Use Transferir para movimentar valores entre caixinhas.</span></div>';
        return;
    }

    lista.innerHTML = transferencias.map((transferencia) => `
        <article class="transf-card">
            <div class="transf-info">
                <div class="transf-contas">
                    <span>${escapeHtml(transferencia.conta_origem_nome || '-')}</span>
                    <span class="transf-seta">${patrimonioIcon('arrow')}</span>
                    <span>${escapeHtml(transferencia.conta_destino_nome || '-')}</span>
                </div>
                <div class="transf-detalhes">
                    <span>${patrimonioIcon('calendar')} ${formatarData(transferencia.data_transferencia)}</span>
                    ${transferencia.descricao ? `<span>${patrimonioIcon('note')} ${escapeHtml(transferencia.descricao)}</span>` : ''}
                </div>
            </div>
            <strong class="transf-valor">${formatarMoedaDisplay(transferencia.valor)}</strong>
            <div class="transf-actions">
                <button class="row-action-button danger" type="button" onclick="deletarTransferencia(${transferencia.id})" title="Excluir transferencia" aria-label="Excluir transferencia">${patrimonioIcon('trash')}</button>
            </div>
        </article>
    `).join('');
}

function abrirModalNovaConta() {
    contaAtual = null;
    setText('modal-conta-titulo', 'Nova Caixinha');
    document.getElementById('form-conta')?.reset();
    setValue('conta-id', '');
    setValue('conta-cor', '#28a745');
    atualizarPreviewCaixinha();
    abrirModal('modal-conta');
}

async function editarConta(id) {
    try {
        const response = await fetch(`${API_BASE}/contas/${id}`);
        const result = await response.json();
        if (result.success) {
            contaAtual = result.data;
            preencherFormConta(result.data);
            setText('modal-conta-titulo', 'Editar Caixinha');
            abrirModal('modal-conta');
        }
    } catch (error) {
        mostrarErro('Erro ao carregar conta');
    }
}

function preencherFormConta(conta) {
    setValue('conta-id', conta.id);
    setValue('conta-nome', conta.nome);
    setValue('conta-tipo', conta.tipo || 'Corrente');
    setValue('conta-cor', conta.cor || '#28a745');
    setValue('conta-saldo-inicial', formatarMoedaDisplay(conta.saldo_inicial));
    setValue('conta-meta', conta.meta ? formatarMoedaDisplay(conta.meta) : '');
    setValue('conta-obs', conta.observacoes || '');
    atualizarPreviewCaixinha();
}

async function salvarConta(event) {
    event.preventDefault();
    const id = document.getElementById('conta-id')?.value;
    const dados = {
        nome: document.getElementById('conta-nome')?.value,
        tipo: document.getElementById('conta-tipo')?.value,
        saldo_inicial: parseMoeda(document.getElementById('conta-saldo-inicial')?.value),
        meta: parseMoeda(document.getElementById('conta-meta')?.value) || null,
        cor: document.getElementById('conta-cor')?.value,
        observacoes: document.getElementById('conta-obs')?.value,
    };

    try {
        const response = await fetch(id ? `${API_BASE}/contas/${id}` : `${API_BASE}/contas`, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados),
        });
        const result = await response.json();
        if (result.success) {
            mostrarSucesso(result.message || 'Caixinha salva');
            fecharModal('modal-conta');
            carregarContas();
        } else {
            mostrarErro(result.error);
        }
    } catch (error) {
        mostrarErro('Erro ao salvar');
    }
}

async function inativarConta(id) {
    if (!confirm('Deseja realmente inativar esta caixinha?')) return;
    try {
        const response = await fetch(`${API_BASE}/contas/${id}`, { method: 'DELETE' });
        const result = await response.json();
        if (result.success) {
            mostrarSucesso('Caixinha inativada');
            carregarContas();
        } else {
            mostrarErro(result.error);
        }
    } catch (error) {
        mostrarErro('Erro ao inativar');
    }
}

async function abrirModalNovaTransferencia(origemId) {
    try {
        const response = await fetch(`${API_BASE}/contas`);
        const result = await response.json();
        if (result.success) {
            estadoPatrimonio.contas = result.data || estadoPatrimonio.contas;
            const contas = result.data.filter((conta) => conta.ativo);
            const options = contas.map((conta) => `<option value="${conta.id}">${escapeHtml(conta.nome)} - ${formatarMoedaDisplay(conta.saldo_atual)}</option>`).join('');
            document.getElementById('transf-origem').innerHTML = '<option value="">Selecione...</option>' + options;
            document.getElementById('transf-destino').innerHTML = '<option value="">Selecione...</option>' + options;
            document.getElementById('form-transferencia')?.reset();
            if (origemId) setValue('transf-origem', origemId);
            document.getElementById('transf-data').valueAsDate = new Date();
            atualizarPreviewTransferencia();
            abrirModal('modal-transferencia');
        }
    } catch (error) {
        mostrarErro('Erro ao carregar contas');
    }
}

async function salvarTransferencia(event) {
    event.preventDefault();
    const dados = {
        conta_origem_id: Number(document.getElementById('transf-origem')?.value),
        conta_destino_id: Number(document.getElementById('transf-destino')?.value),
        valor: parseMoeda(document.getElementById('transf-valor')?.value),
        data_transferencia: document.getElementById('transf-data')?.value,
        descricao: document.getElementById('transf-descricao')?.value,
    };

    try {
        const response = await fetch(`${API_BASE}/transferencias`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados),
        });
        const result = await response.json();
        if (result.success) {
            mostrarSucesso(result.message || 'Transferencia criada');
            fecharModal('modal-transferencia');
            carregarTransferencias();
            carregarContas();
        } else {
            mostrarErro(result.error);
        }
    } catch (error) {
        mostrarErro('Erro ao criar transferencia');
    }
}

async function deletarTransferencia(id) {
    if (!confirm('Deletar esta transferencia? Os saldos serao revertidos.')) return;
    try {
        const response = await fetch(`${API_BASE}/transferencias/${id}`, { method: 'DELETE' });
        const result = await response.json();
        if (result.success) {
            mostrarSucesso(result.message || 'Transferencia removida');
            carregarTransferencias();
            carregarContas();
        } else {
            mostrarErro(result.error);
        }
    } catch (error) {
        mostrarErro('Erro ao deletar');
    }
}

function atualizarPreviewCaixinha() {
    const nome = document.getElementById('conta-nome')?.value || 'Nome da caixinha';
    const tipo = document.getElementById('conta-tipo')?.value || 'Corrente';
    const cor = document.getElementById('conta-cor')?.value || '#28a745';
    const saldo = parseMoeda(document.getElementById('conta-saldo-inicial')?.value);
    const meta = parseMoeda(document.getElementById('conta-meta')?.value);
    const progresso = meta ? Math.min((saldo / meta) * 100, 100) : 0;

    document.documentElement.style.setProperty('--preview-color', cor);
    setText('preview-conta-nome', nome);
    setText('preview-conta-tipo', `Tipo: ${tipo}`);
    setText('preview-conta-saldo', formatarMoedaDisplay(saldo));
    setText('preview-conta-meta', formatarMoedaDisplay(meta));
    document.getElementById('preview-conta-progress').style.width = `${progresso}%`;
    document.getElementById('preview-conta-icon').innerHTML = iconePorTipo(tipo);
}

function atualizarPreviewTransferencia() {
    const valor = parseMoeda(document.getElementById('transf-valor')?.value);
    setText('preview-transfer-saida', formatarMoedaDisplay(valor));
    setText('preview-transfer-entrada', formatarMoedaDisplay(valor));
}

function abrirModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
}

function fecharModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
}

window.addEventListener('click', (event) => {
    if (event.target.classList.contains('patrimonio-modal')) {
        fecharModal(event.target.id);
    }
});

function gerarDonut(contas, total) {
    let cursor = 0;
    const partes = contas.map((conta) => {
        const inicio = cursor;
        const fim = cursor + (Number(conta.saldo_atual || 0) / total) * 100;
        cursor = fim;
        return `${conta.cor || '#2563eb'} ${inicio}% ${fim}%`;
    });
    return `background: conic-gradient(${partes.join(', ')});`;
}

function progressoMeta(conta) {
    const meta = Number(conta.meta || 0);
    if (!meta) return 0;
    return (Number(conta.saldo_atual || 0) / meta) * 100;
}

function iconePorTipo(tipo = '') {
    const texto = normalizarBusca(tipo);
    if (texto.includes('reserva')) return patrimonioIcon('shield');
    if (texto.includes('invest')) return patrimonioIcon('chart');
    if (texto.includes('poup')) return patrimonioIcon('home');
    if (texto.includes('prazo') || texto.includes('viagem')) return patrimonioIcon('plane');
    if (texto.includes('corrente')) return patrimonioIcon('box');
    return patrimonioIcon('wallet');
}

function formatarMoeda(input) {
    if (!input) return;
    let value = String(input.value || '').replace(/\D/g, '');
    if (!value) {
        input.value = '';
        return;
    }
    value = (Number.parseInt(value, 10) / 100).toFixed(2);
    input.value = `R$ ${value.replace('.', ',').replace(/(\d)(?=(\d{3})+,)/g, '$1.')}`;
}

function parseMoeda(value) {
    if (!value) return 0;
    if (typeof value === 'number') return value;
    return Number.parseFloat(String(value).replace('R$', '').replace(/\./g, '').replace(',', '.').trim()) || 0;
}

function formatarMoedaDisplay(value) {
    return Number(value || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarData(value) {
    if (!value) return '-';
    return new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString('pt-BR');
}

function normalizarBusca(value) {
    return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .trim();
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

function setValue(id, value) {
    const element = document.getElementById(id);
    if (element) element.value = value;
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function mostrarSucesso(message) {
    alert(message);
}

function mostrarErro(message) {
    alert(message || 'Erro inesperado');
}
