/**
 * Tela Cartoes - limites por Categoria do Cartao global.
 */

const API_CARTOES = '/api/cartoes';
const API_CATEGORIAS_CARTAO = '/api/categorias-cartao';

const estadoCartoes = {
    cartoes: [],
    categoriasCartao: [],
    limitesPorCartao: new Map(),
    cartaoSelecionadoId: null,
    buscaGeral: '',
    buscaLateral: '',
    status: 'ativos',
    mesSelecionado: new Date().toISOString().slice(0, 7)
};

function cartoesIcon(name) {
    const icons = {
        card: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M3 10h18"/>',
        edit: '<path d="M5 19h4L19 9a2.1 2.1 0 0 0-3-3L6 16l-1 3Z"/><path d="M14 6l4 4"/>',
        link: '<path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.1 0l-2 2a5 5 0 0 0 7.1 7.1l1.1-1.1"/>',
        lock: '<path d="M7 11V8a5 5 0 0 1 10 0v3"/><path d="M6 11h12v9H6v-9Z"/><path d="M12 15v2"/>',
        remove: '<path d="M6 6l12 12M18 6 6 18"/>',
        check: '<path d="M5 12.5l4 4L19 7"/>',
        more: '<path d="M12 5h.1M12 12h.1M12 19h.1"/>',
        info: '<path d="M12 11v6"/><path d="M12 7h.1"/><path d="M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z"/>',
        alert: '<path d="M12 5 3.5 19h17L12 5Z"/><path d="M12 10v4M12 17h.1"/>',
        default: '<rect x="4" y="4" width="16" height="16" rx="3"/>'
    };
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${icons[name] || icons.default}</svg>`;
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[char]));
}

function normalizarBusca(value) {
    return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .trim();
}

function formatarMoeda(valor) {
    const numero = Number(valor || 0);
    return numero.toLocaleString('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    });
}

function formatarMoedaCompacta(valor) {
    const numero = Number(valor || 0);
    return numero.toLocaleString('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function obterFinalCartao(cartao) {
    const numero = String(cartao?.config?.numero_cartao || '').replace(/\D/g, '');
    return numero.length >= 4 ? numero.slice(-4) : '----';
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => null);
    if (!response.ok || data?.success === false) {
        throw new Error(data?.error || data?.erro || data?.message || `Erro HTTP ${response.status}`);
    }
    return data;
}

document.addEventListener('DOMContentLoaded', () => {
    inicializarTelaCartoes();
});

function inicializarTelaCartoes() {
    configurarEventosCartoes();
    carregarTelaCartoes();
}

function configurarEventosCartoes() {
    document.getElementById('btn-novo-cartao')?.addEventListener('click', abrirModalCartao);
    document.getElementById('btn-vincular-categoria')?.addEventListener('click', () => abrirModalLimite());

    document.getElementById('cartoes-pesquisa')?.addEventListener('input', (event) => {
        estadoCartoes.buscaGeral = event.target.value;
        ajustarSelecaoCartao();
        renderizarTelaCartoes();
    });

    document.getElementById('cartoes-busca-lateral')?.addEventListener('input', (event) => {
        estadoCartoes.buscaLateral = event.target.value;
        ajustarSelecaoCartao();
        renderizarListaCartoes();
        renderizarDetalheCartao();
    });

    document.getElementById('cartoes-status')?.addEventListener('change', (event) => {
        estadoCartoes.status = event.target.value;
        ajustarSelecaoCartao();
        renderizarTelaCartoes();
    });

    document.getElementById('lista-cartoes')?.addEventListener('click', (event) => {
        const item = event.target.closest('[data-cartao-id]');
        if (!item) return;
        estadoCartoes.cartaoSelecionadoId = Number(item.dataset.cartaoId);
        renderizarListaCartoes();
        renderizarDetalheCartao();
    });

    document.getElementById('cartao-detalhe')?.addEventListener('click', tratarCliqueDetalhe);
    document.getElementById('form-cartao')?.addEventListener('submit', salvarCartao);
    document.getElementById('form-categoria-limite')?.addEventListener('submit', salvarCategoriaLimite);
    document.getElementById('form-revelar-cvv')?.addEventListener('submit', revelarCodigoSeguranca);

    document.querySelectorAll('[data-close-modal]').forEach((button) => {
        button.addEventListener('click', () => fecharModal(button.dataset.closeModal));
    });

    document.querySelectorAll('.modal').forEach((modal) => {
        modal.addEventListener('click', (event) => {
            if (event.target === modal) fecharModal(modal.id);
        });
    });

    document.getElementById('cartao-numero')?.addEventListener('input', (event) => {
        const valor = event.target.value.replace(/\D/g, '');
        event.target.value = valor.match(/.{1,4}/g)?.join(' ') || valor;
    });

    document.getElementById('cartao-data-validade')?.addEventListener('input', (event) => mascaraMesAno(event.target));
}

async function carregarTelaCartoes() {
    try {
        const [cartoesResp, categoriasResp] = await Promise.all([
            fetchJson(API_CARTOES),
            fetchJson(`${API_CATEGORIAS_CARTAO}?ativo=true`)
        ]);

        estadoCartoes.cartoes = Array.isArray(cartoesResp) ? cartoesResp : (cartoesResp.data || []);
        estadoCartoes.categoriasCartao = categoriasResp.data || [];

        await Promise.all(estadoCartoes.cartoes.map((cartao) => carregarLimitesCartao(cartao.id)));
        ajustarSelecaoCartao();
        renderizarTelaCartoes();
    } catch (error) {
        console.error('Erro ao carregar tela de cartoes:', error);
        mostrarErro(`Erro ao carregar cart\u00f5es: ${error.message}`);
    }
}

async function carregarLimitesCartao(cartaoId) {
    const resp = await fetchJson(`${API_CARTOES}/${cartaoId}/categorias-limite?mes_referencia=${estadoCartoes.mesSelecionado}`);
    estadoCartoes.limitesPorCartao.set(Number(cartaoId), resp.data || []);
}

function renderizarTelaCartoes() {
    renderizarResumo();
    renderizarListaCartoes();
    renderizarDetalheCartao();
}

function renderizarResumo() {
    const cartoesAtivos = estadoCartoes.cartoes.filter((cartao) => cartao.ativo !== false);
    let categoriasVinculadas = 0;
    let limiteTotal = 0;

    estadoCartoes.limitesPorCartao.forEach((limites) => {
        limites.filter((limite) => limite.ativo).forEach((limite) => {
            categoriasVinculadas += 1;
            limiteTotal += Number(limite.limite_mensal || 0);
        });
    });

    setText('summary-cartoes-ativos', cartoesAtivos.length);
    setText('summary-categorias-vinculadas', categoriasVinculadas);
    setText('summary-limite-total', formatarMoeda(limiteTotal));
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function filtrarCartoes() {
    const busca = normalizarBusca(`${estadoCartoes.buscaGeral} ${estadoCartoes.buscaLateral}`);
    return estadoCartoes.cartoes.filter((cartao) => {
        if (estadoCartoes.status === 'ativos' && cartao.ativo === false) return false;
        if (estadoCartoes.status === 'inativos' && cartao.ativo !== false) return false;
        if (!busca) return true;
        return normalizarBusca(`${cartao.nome} ${cartao.descricao || ''} ${obterFinalCartao(cartao)}`).includes(busca);
    });
}

function ajustarSelecaoCartao() {
    const cartoes = filtrarCartoes();
    const selecionadoExiste = cartoes.some((cartao) => cartao.id === estadoCartoes.cartaoSelecionadoId);
    estadoCartoes.cartaoSelecionadoId = selecionadoExiste
        ? estadoCartoes.cartaoSelecionadoId
        : (cartoes[0]?.id || null);
}

function obterCartaoSelecionado() {
    return estadoCartoes.cartoes.find((cartao) => cartao.id === estadoCartoes.cartaoSelecionadoId) || null;
}

function obterLimitesCartao(cartaoId) {
    return estadoCartoes.limitesPorCartao.get(Number(cartaoId)) || [];
}

function obterCategoriaCartao(categoriaCartaoId) {
    return estadoCartoes.categoriasCartao.find((categoria) => categoria.id === Number(categoriaCartaoId)) || null;
}

function obterLimitesAtivos(cartaoId) {
    return obterLimitesCartao(cartaoId).filter((limite) => limite.ativo);
}

function obterCategoriasDisponiveis(cartaoId) {
    const vinculadasAtivas = new Set(obterLimitesAtivos(cartaoId).map((limite) => limite.categoria_cartao_id));
    return estadoCartoes.categoriasCartao
        .filter((categoria) => categoria.ativo && !vinculadasAtivas.has(categoria.id))
        .sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
}

function renderizarListaCartoes() {
    const lista = document.getElementById('lista-cartoes');
    if (!lista) return;

    const cartoes = filtrarCartoes();
    if (!cartoes.length) {
        lista.innerHTML = `
            <div class="empty-inline">
                <h3>Nenhum cart&atilde;o encontrado</h3>
                <p>Ajuste a busca ou cadastre um novo cart&atilde;o.</p>
            </div>
        `;
        return;
    }

    lista.innerHTML = cartoes.map((cartao) => {
        const selecionado = cartao.id === estadoCartoes.cartaoSelecionadoId;
        const limitesAtivos = obterLimitesAtivos(cartao.id);
        const final = obterFinalCartao(cartao);
        return `
            <button class="cartao-list-item ${selecionado ? 'selected' : ''}" type="button" data-cartao-id="${cartao.id}">
                <span class="cartao-brand">${renderizarMarcaCartao(cartao)}</span>
                <span class="cartao-list-main">
                    <strong>${escapeHtml(cartao.nome)}</strong>
                    <small>**** ${escapeHtml(final)}</small>
                </span>
                <span class="cartao-list-meta">
                    <span class="status-dot active"></span>
                    <small>Ativo</small>
                    <small>${limitesAtivos.length} ${limitesAtivos.length === 1 ? 'categoria vinculada' : 'categorias vinculadas'}</small>
                </span>
                <span class="cartao-list-check" aria-hidden="true">${selecionado ? cartoesIcon('check') : ''}</span>
            </button>
        `;
    }).join('');
}

function renderizarDetalheCartao() {
    const detalhe = document.getElementById('cartao-detalhe');
    if (!detalhe) return;

    const cartao = obterCartaoSelecionado();
    if (!cartao) {
        detalhe.innerHTML = `
            <div class="detail-empty">
                <h2>Selecione um cart&atilde;o</h2>
                <p>Escolha um cart&atilde;o para vincular Categorias do Cart&atilde;o globais e definir limites mensais.</p>
            </div>
        `;
        return;
    }

    const limites = filtrarLimitesPorStatus(obterLimitesCartao(cartao.id));
    const limitesAtivos = obterLimitesAtivos(cartao.id);
    const disponiveis = obterCategoriasDisponiveis(cartao.id);
    const totalLimite = limitesAtivos.reduce((sum, limite) => sum + Number(limite.limite_mensal || 0), 0);
    const totalGasto = limitesAtivos.reduce((sum, limite) => sum + Number(limite.gasto_atual || 0), 0);
    const final = obterFinalCartao(cartao);

    detalhe.innerHTML = `
        <header class="cartao-detail-header">
            <div class="cartao-detail-identity">
                <span class="cartao-detail-brand">${renderizarMarcaCartao(cartao)}</span>
                <div>
                    <h2>${escapeHtml(cartao.nome)}</h2>
                    <p>**** ${escapeHtml(final)} ${final !== '----' ? `(Final ${escapeHtml(final)})` : ''}</p>
                </div>
                <span class="compact-pill status-ativo">Ativo</span>
            </div>
            <div class="cartao-detail-actions">
                <button class="cf-button cf-button-secondary" type="button" data-action="editar-cartao">${cartoesIcon('edit')} <span>Editar cart&atilde;o</span></button>
                <button class="cf-button cf-button-primary" type="button" data-action="abrir-limite">Salvar limites</button>
            </div>
        </header>

        <section class="detail-card cartao-resumo-card">
            <h3>Resumo do Cart&atilde;o</h3>
            <div class="resumo-grid">
                <div>
                    <span>Nome do cart&atilde;o</span>
                    <strong>${escapeHtml(cartao.nome)}</strong>
                </div>
                <div>
                    <span>Banco / Emissor</span>
                    <strong>${escapeHtml(cartao.descricao || '-')}</strong>
                </div>
                <div>
                    <span>Final do cart&atilde;o</span>
                    <strong>**** ${escapeHtml(final)}</strong>
                </div>
                <div>
                    <span>Vencimento da fatura</span>
                    <strong>Dia ${escapeHtml(cartao.config?.dia_vencimento || '-')}</strong>
                </div>
            </div>
        </section>

        <section class="detail-card categorias-vinculadas-card">
            <h3>Categorias do Cart&atilde;o Vinculadas</h3>
            ${renderizarTabelaLimites(limites)}
            <div class="limite-total-row">
                <strong>Total</strong>
                <strong>${formatarMoeda(totalLimite)}</strong>
                <span>${formatarMoeda(totalGasto)}</span>
                <span>${formatarMoeda(totalLimite - totalGasto)}</span>
                <span>${totalLimite > 0 ? Math.round((totalGasto / totalLimite) * 100) : 0}%</span>
            </div>
        </section>

        <section class="detail-card categorias-disponiveis-card">
            <h3>Categorias dispon&iacute;veis para vincular</h3>
            ${renderizarCategoriasDisponiveis(disponiveis)}
        </section>

        <section class="operational-rule">
            <h3>Regra operacional</h3>
            <p>As despesas pagas neste cart&atilde;o s&atilde;o agrupadas automaticamente pela Categoria do Cart&atilde;o com base na Categoria de Despesa.</p>
        </section>
    `;
}

function filtrarLimitesPorStatus(limites) {
    if (estadoCartoes.status === 'ativos') return limites.filter((limite) => limite.ativo);
    if (estadoCartoes.status === 'inativos') return limites.filter((limite) => !limite.ativo);
    return limites;
}

function renderizarTabelaLimites(limites) {
    if (!limites.length) {
        return `
            <div class="table-empty">
                <h4>Nenhuma Categoria do Cart&atilde;o vinculada</h4>
                <p>Use Vincular categoria para associar uma categoria global e definir o limite mensal.</p>
            </div>
        `;
    }

    const linhas = limites.map((limite) => {
        const categoria = obterCategoriaCartao(limite.categoria_cartao_id);
        const limiteMensal = Number(limite.limite_mensal || 0);
        const gastoAtual = Number(limite.gasto_atual || 0);
        const disponivel = Number(limite.disponivel ?? (limiteMensal - gastoAtual));
        const percentual = Math.min(Number(limite.percentual_utilizado || 0), 999);
        return `
            <div class="limites-table-row">
                <div class="table-category">
                    <span class="categoria-icon" style="color:${escapeHtml(categoria?.cor || '#2563eb')}">${renderizarIconeCategoriaCartao(categoria, '18px')}</span>
                    <span>${escapeHtml(categoria?.nome || limite.categoria_cartao_nome || 'Categoria')}</span>
                </div>
                <div>${formatarMoeda(limiteMensal)}</div>
                <div class="usage-cell">
                    <strong>${formatarMoeda(gastoAtual)}</strong>
                    <small>${Math.round(percentual)}%</small>
                    <span class="progress-track"><span style="width:${Math.min(percentual, 100)}%"></span></span>
                </div>
                <div class="${disponivel < 0 ? 'negative' : 'positive'}">${formatarMoeda(disponivel)}</div>
                <div>
                    <span class="compact-pill ${limite.ativo ? 'status-ativo' : 'status-inativo'}">${limite.ativo ? 'Ativa' : 'Inativa'}</span>
                </div>
                <div class="row-actions">
                    <button class="row-action-button" type="button" data-action="editar-limite" data-limite-id="${limite.id}" title="Editar limite" aria-label="Editar limite">${cartoesIcon('edit')}</button>
                    <button class="row-action-button danger" type="button" data-action="toggle-limite" data-limite-id="${limite.id}" title="${limite.ativo ? 'Desativar' : 'Reativar'}" aria-label="${limite.ativo ? 'Desativar' : 'Reativar'}">${limite.ativo ? cartoesIcon('remove') : cartoesIcon('check')}</button>
                </div>
            </div>
        `;
    }).join('');

    return `
        <div class="limites-table">
            <div class="limites-table-header">
                <div>Categoria do Cart&atilde;o</div>
                <div>Limite mensal</div>
                <div>Gasto atual</div>
                <div>Dispon&iacute;vel</div>
                <div>Status</div>
                <div>A&ccedil;&otilde;es</div>
            </div>
            ${linhas}
        </div>
    `;
}

function renderizarCategoriasDisponiveis(disponiveis) {
    if (!disponiveis.length) {
        return '<div class="empty-inline">Todas as Categorias do Cart&atilde;o ativas j&aacute; est&atilde;o vinculadas a este cart&atilde;o.</div>';
    }

    return `
        <div class="available-grid">
            ${disponiveis.map((categoria) => `
                <article class="available-category">
                    <span class="categoria-icon" style="color:${escapeHtml(categoria.cor || '#2563eb')}">${renderizarIconeCategoriaCartao(categoria, '20px')}</span>
                    <strong>${escapeHtml(categoria.nome)}</strong>
                    <button class="cf-button cf-button-secondary" type="button" data-action="vincular-disponivel" data-categoria-cartao-id="${categoria.id}">
                        <span aria-hidden="true">+</span>
                        <span>Vincular</span>
                    </button>
                </article>
            `).join('')}
        </div>
    `;
}

async function tratarCliqueDetalhe(event) {
    const button = event.target.closest('[data-action]');
    if (!button) return;

    const action = button.dataset.action;
    if (action === 'editar-cartao') {
        abrirModalEditarCartao();
    } else if (action === 'abrir-limite') {
        abrirModalLimite();
    } else if (action === 'editar-limite') {
        abrirModalLimite(Number(button.dataset.limiteId));
    } else if (action === 'toggle-limite') {
        await alternarLimite(Number(button.dataset.limiteId));
    } else if (action === 'vincular-disponivel') {
        abrirModalLimite(null, Number(button.dataset.categoriaCartaoId));
    }
}

function renderizarMarcaCartao(cartao) {
    const nome = String(cartao?.nome || 'CC').trim();
    const partes = nome.split(/\s+/);
    const sigla = partes.length > 1
        ? `${partes[0][0] || ''}${partes[1][0] || ''}`
        : nome.slice(0, 2);
    return `<span>${escapeHtml(sigla.toUpperCase())}</span>`;
}

function renderizarIconeCategoriaCartao(categoria, size = '18px') {
    if (typeof renderIcon === 'function') {
        return renderIcon(categoria?.icone || 'credit-card', { size });
    }
    return cartoesIcon('card');
}

function abrirModalCartao() {
    document.getElementById('modal-cartao-titulo').textContent = 'Novo Cart\u00e3o';
    document.getElementById('form-cartao').reset();
    document.getElementById('cartao-id').value = '';
    document.getElementById('cartao-tem-codigo').checked = true;
    abrirModal('modal-cartao');
}

function abrirModalEditarCartao() {
    const cartao = obterCartaoSelecionado();
    if (!cartao) return;

    document.getElementById('modal-cartao-titulo').textContent = 'Editar Cart\u00e3o';
    document.getElementById('cartao-id').value = cartao.id;
    document.getElementById('cartao-nome').value = cartao.nome || '';
    document.getElementById('cartao-descricao').value = cartao.descricao || '';
    document.getElementById('cartao-dia-vencimento').value = cartao.config?.dia_vencimento || '';
    document.getElementById('cartao-limite').value = cartao.config?.limite_credito || '';
    document.getElementById('cartao-numero').value = cartao.config?.numero_cartao || '';
    document.getElementById('cartao-data-validade').value = cartao.config?.data_validade || '';
    document.getElementById('cartao-cvv').value = '';
    document.getElementById('cartao-tem-codigo').checked = cartao.config?.tem_codigo !== false;
    document.getElementById('cartao-observacoes').value = cartao.config?.observacoes || '';
    abrirModal('modal-cartao');
}

async function salvarCartao(event) {
    event.preventDefault();

    const id = document.getElementById('cartao-id').value;
    const diaVencimento = Number(document.getElementById('cartao-dia-vencimento').value);
    const dados = {
        nome: document.getElementById('cartao-nome').value.trim(),
        descricao: document.getElementById('cartao-descricao').value.trim(),
        dia_fechamento: diaVencimento,
        dia_vencimento: diaVencimento,
        limite_credito: parseFloat(document.getElementById('cartao-limite').value) || null,
        numero_cartao: document.getElementById('cartao-numero').value || null,
        data_validade: document.getElementById('cartao-data-validade').value || null,
        codigo_seguranca: document.getElementById('cartao-cvv').value || null,
        tem_codigo: document.getElementById('cartao-tem-codigo').checked,
        observacoes: document.getElementById('cartao-observacoes').value
    };

    if (!dados.nome || !diaVencimento) {
        mostrarErro('Informe nome e vencimento do cart\u00e3o.');
        return;
    }

    try {
        const response = await fetchJson(id ? `${API_CARTOES}/${id}` : API_CARTOES, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        fecharModal('modal-cartao');
        await carregarTelaCartoes();
        estadoCartoes.cartaoSelecionadoId = Number(response.id || id || estadoCartoes.cartaoSelecionadoId);
        ajustarSelecaoCartao();
        renderizarTelaCartoes();
        mostrarSucesso(id ? 'Cart\u00e3o atualizado.' : 'Cart\u00e3o criado.');
    } catch (error) {
        console.error('Erro ao salvar cartao:', error);
        mostrarErro(`Erro ao salvar cart\u00e3o: ${error.message}`);
    }
}

function abrirModalLimite(limiteId = null, categoriaPreSelecionadaId = null) {
    const cartao = obterCartaoSelecionado();
    if (!cartao) {
        mostrarErro('Selecione um cart\u00e3o primeiro.');
        return;
    }

    const limite = limiteId
        ? obterLimitesCartao(cartao.id).find((item) => item.id === Number(limiteId))
        : null;
    const select = document.getElementById('limite-categoria-cartao');
    const categoriasDisponiveis = obterCategoriasDisponiveis(cartao.id);
    const categoriaAtual = limite ? obterCategoriaCartao(limite.categoria_cartao_id) : null;
    const opcoes = limite && categoriaAtual
        ? [categoriaAtual]
        : categoriasDisponiveis;

    if (!limite && !opcoes.length) {
        mostrarErro('N\u00e3o h\u00e1 Categorias do Cart\u00e3o dispon\u00edveis para vincular.');
        return;
    }

    document.getElementById('modal-limite-titulo').textContent = limite ? 'Editar limite' : 'Vincular Categoria';
    document.getElementById('limite-id').value = limite?.id || '';
    select.innerHTML = opcoes.map((categoria) => `
        <option value="${categoria.id}" ${(categoria.id === (categoriaPreSelecionadaId || limite?.categoria_cartao_id)) ? 'selected' : ''}>${escapeHtml(categoria.nome)}</option>
    `).join('');
    select.disabled = Boolean(limite);
    document.getElementById('limite-valor').value = limite?.limite_mensal || '';
    document.getElementById('limite-ativo').checked = limite?.ativo !== false;
    abrirModal('modal-categoria-limite');
}

async function salvarCategoriaLimite(event) {
    event.preventDefault();

    const cartao = obterCartaoSelecionado();
    if (!cartao) return;

    const limiteId = document.getElementById('limite-id').value;
    const dados = {
        categoria_cartao_id: Number(document.getElementById('limite-categoria-cartao').value),
        limite_mensal: document.getElementById('limite-valor').value || 0,
        ativo: document.getElementById('limite-ativo').checked
    };

    try {
        await fetchJson(
            limiteId ? `${API_CARTOES}/${cartao.id}/categorias-limite/${limiteId}` : `${API_CARTOES}/${cartao.id}/categorias-limite`,
            {
                method: limiteId ? 'PUT' : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(dados)
            }
        );
        fecharModal('modal-categoria-limite');
        await carregarLimitesCartao(cartao.id);
        renderizarTelaCartoes();
        mostrarSucesso('Limite salvo.');
    } catch (error) {
        console.error('Erro ao salvar limite:', error);
        mostrarErro(`Erro ao salvar limite: ${error.message}`);
    }
}

async function alternarLimite(limiteId) {
    const cartao = obterCartaoSelecionado();
    if (!cartao) return;

    const limite = obterLimitesCartao(cartao.id).find((item) => item.id === Number(limiteId));
    if (!limite) return;

    try {
        if (limite.ativo) {
            await fetchJson(`${API_CARTOES}/${cartao.id}/categorias-limite/${limite.id}`, { method: 'DELETE' });
        } else {
            await fetchJson(`${API_CARTOES}/${cartao.id}/categorias-limite/${limite.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ativo: true })
            });
        }
        await carregarLimitesCartao(cartao.id);
        renderizarTelaCartoes();
        mostrarSucesso(limite.ativo ? 'V\u00ednculo desativado.' : 'V\u00ednculo reativado.');
    } catch (error) {
        console.error('Erro ao atualizar vinculo:', error);
        mostrarErro(`Erro ao atualizar vinculo: ${error.message}`);
    }
}

function abrirModal(modalId) {
    document.getElementById(modalId)?.classList.add('open');
}

function fecharModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.remove('open');
    if (modalId === 'modal-categoria-limite') {
        document.getElementById('limite-categoria-cartao').disabled = false;
    }
}

async function revelarCodigoSeguranca(event) {
    event.preventDefault();

    const cartaoId = document.getElementById('cvv-cartao-id').value;
    const senha = document.getElementById('cvv-senha').value;
    try {
        const resp = await fetchJson(`${API_CARTOES}/${cartaoId}/codigo-seguranca`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ senha })
        });
        document.getElementById('cvv-codigo').textContent = resp.data?.codigo_seguranca || '***';
        document.getElementById('cvv-resultado').hidden = false;
        document.getElementById('btn-revelar').hidden = true;
    } catch (error) {
        mostrarErro(error.message);
    }
}

function mascaraMesAno(input) {
    let valor = input.value.replace(/\D/g, '');
    if (valor.length >= 2) {
        valor = `${valor.substring(0, 2)}/${valor.substring(2, 6)}`;
    }
    input.value = valor;
}

function mostrarSucesso(mensagem) {
    mostrarNotificacao(mensagem, 'success');
}

function mostrarErro(mensagem) {
    mostrarNotificacao(mensagem, 'error');
}

function mostrarNotificacao(mensagem, tipo = 'info') {
    const existente = document.getElementById('notificacao-toast');
    if (existente) existente.remove();

    const cores = {
        success: '#16a34a',
        error: '#dc2626',
        info: '#2563eb'
    };
    const toast = document.createElement('div');
    toast.id = 'notificacao-toast';
    toast.className = 'notificacao-toast';
    toast.style.background = cores[tipo] || cores.info;
    toast.textContent = mensagem;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3600);
}

window.abrirModalCartao = abrirModalCartao;
window.abrirModalEditarCartao = abrirModalEditarCartao;
window.fecharModal = fecharModal;
window.mascaraMesAno = mascaraMesAno;
