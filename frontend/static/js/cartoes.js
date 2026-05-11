/**
 * Tela Cartoes - limites por Categoria do Cartao global.
 */

const API_CARTOES = '/api/cartoes';
const API_CATEGORIAS = '/api/categorias';
const API_CATEGORIAS_CARTAO = '/api/categorias-cartao';

const estadoCartoes = {
    cartoes: [],
    categoriasDespesa: [],
    categoriasCartao: [],
    limitesPorCartao: new Map(),
    faturasPorCartao: new Map(),
    lancamentosFatura: new Map(),
    cartaoSelecionadoId: null,
    parcelamentoGestao: null,
    filtroLancamentosFatura: 'todos',
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
        layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5"/><path d="m3 16 9 5 9-5"/>',
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
        selecionarCartao(Number(item.dataset.cartaoId));
    });

    document.getElementById('cartao-detalhe')?.addEventListener('click', tratarCliqueDetalhe);
    document.getElementById('cartao-detalhe')?.addEventListener('change', tratarMudancaDetalhe);
    document.getElementById('form-cartao')?.addEventListener('submit', salvarCartao);
    document.getElementById('form-categoria-limite')?.addEventListener('submit', salvarCategoriaLimite);
    document.getElementById('form-revelar-cvv')?.addEventListener('submit', revelarCodigoSeguranca);
    document.getElementById('form-gerenciar-parcelamento')?.addEventListener('submit', salvarParcelasFuturas);
    document.getElementById('btn-cancelar-parcelas-futuras')?.addEventListener('click', cancelarParcelasFuturas);

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
        await carregarFaturaSelecionada();
        renderizarDetalheCartao();
    } catch (error) {
        console.error('Erro ao carregar tela de cartoes:', error);
        mostrarErro(`Erro ao carregar cart\u00f5es: ${error.message}`);
    }
}

async function carregarLimitesCartao(cartaoId) {
    const resp = await fetchJson(`${API_CARTOES}/${cartaoId}/categorias-limite?mes_referencia=${estadoCartoes.mesSelecionado}`);
    estadoCartoes.limitesPorCartao.set(Number(cartaoId), resp.data || []);
}

function chaveFatura(cartaoId, filtro = 'todos') {
    return `${Number(cartaoId)}:${estadoCartoes.mesSelecionado}:${filtro}`;
}

async function carregarResumoFaturaCartao(cartaoId) {
    const resp = await fetchJson(`${API_CARTOES}/${cartaoId}/fatura-categorias?mes_referencia=${estadoCartoes.mesSelecionado}`);
    estadoCartoes.faturasPorCartao.set(chaveFatura(cartaoId), resp.data || null);
}

async function carregarLancamentosFaturaCartao(cartaoId, filtro = estadoCartoes.filtroLancamentosFatura || 'todos') {
    const resp = await fetchJson(`${API_CARTOES}/${cartaoId}/fatura-lancamentos?mes_referencia=${estadoCartoes.mesSelecionado}&categoria_cartao_id=${encodeURIComponent(filtro)}`);
    estadoCartoes.lancamentosFatura.set(chaveFatura(cartaoId, filtro), resp.data?.lancamentos || []);
}

async function carregarFaturaCartao(cartaoId) {
    if (!cartaoId) return;
    await Promise.all([
        carregarResumoFaturaCartao(cartaoId),
        carregarLancamentosFaturaCartao(cartaoId, estadoCartoes.filtroLancamentosFatura || 'todos')
    ]);
}

async function carregarFaturaSelecionada() {
    if (!estadoCartoes.cartaoSelecionadoId) return;
    await carregarFaturaCartao(estadoCartoes.cartaoSelecionadoId);
}

async function selecionarCartao(cartaoId) {
    estadoCartoes.cartaoSelecionadoId = Number(cartaoId);
    estadoCartoes.filtroLancamentosFatura = 'todos';
    renderizarListaCartoes();
    renderizarDetalheCartao();
    try {
        await carregarFaturaSelecionada();
        renderizarDetalheCartao();
    } catch (error) {
        console.error('Erro ao carregar fatura do cartao:', error);
        mostrarErro(`Erro ao carregar fatura: ${error.message}`);
    }
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

function obterResumoFatura(cartaoId) {
    return estadoCartoes.faturasPorCartao.get(chaveFatura(cartaoId)) || null;
}

function obterLancamentosFatura(cartaoId, filtro = estadoCartoes.filtroLancamentosFatura || 'todos') {
    return estadoCartoes.lancamentosFatura.get(chaveFatura(cartaoId, filtro)) || [];
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
        const emissor = obterInstituicaoCartao(cartao);
        return `
            <button class="cartao-list-item ${selecionado ? 'selected' : ''}" type="button" data-cartao-id="${cartao.id}">
                <span class="cartao-brand">${renderizarMarcaCartao(cartao, 'sm')}</span>
                <span class="cartao-list-main">
                    <strong>${escapeHtml(cartao.nome)}</strong>
                    <small>${escapeHtml(emissor || 'Emissor nao informado')} &bull; **** ${escapeHtml(final)}</small>
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
    const resumoFatura = obterResumoFatura(cartao.id);
    const final = obterFinalCartao(cartao);

    detalhe.innerHTML = `
        <header class="cartao-detail-header">
            <div class="cartao-detail-identity">
                <span class="cartao-detail-brand">${renderizarMarcaCartao(cartao)}</span>
                <div>
                    <h2>${escapeHtml(cartao.nome)}</h2>
                    <p>${escapeHtml(obterInstituicaoCartao(cartao) || 'Emissor nao informado')} &bull; **** ${escapeHtml(final)} ${final !== '----' ? `(Final ${escapeHtml(final)})` : ''}</p>
                </div>
                <span class="compact-pill status-ativo">Ativo</span>
            </div>
            <div class="cartao-detail-actions">
                <button class="cf-button cf-button-secondary" type="button" data-action="editar-cartao">${cartoesIcon('edit')} <span>Editar cart&atilde;o</span></button>
                <button class="cf-button cf-button-primary" type="button" data-action="abrir-limite">Salvar limites</button>
            </div>
        </header>

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

        ${renderizarFaturaPorCategoria(cartao, resumoFatura)}

        <section class="operational-rule">
            <h3>Regra operacional</h3>
            <p>As despesas pagas neste cart&atilde;o s&atilde;o agrupadas automaticamente pela Categoria do Cart&atilde;o com base na Categoria de Despesa.</p>
        </section>
    `;
}

function renderizarFaturaPorCategoria(cartao, resumoFatura) {
    if (!resumoFatura) {
        return `
            <section class="detail-card fatura-categorias-card">
                <div class="fatura-card-header">
                    <div>
                        <h3>Fatura por Categoria do Cart&atilde;o</h3>
                        <p>Carregando consumo da fatura...</p>
                    </div>
                    ${renderizarSeletorMesFatura()}
                </div>
            </section>
        `;
    }

    return `
        <section class="detail-card fatura-categorias-card">
            <div class="fatura-card-header">
                <div>
                    <h3>Fatura por Categoria do Cart&atilde;o</h3>
                    <p>Consumo agrupado por Categoria do Cart&atilde;o em ${escapeHtml(resumoFatura.mes_referencia)}.</p>
                </div>
                ${renderizarSeletorMesFatura()}
            </div>

            <div class="fatura-metrics">
                <article>
                    <span>Total da fatura</span>
                    <strong>${formatarMoeda(resumoFatura.total_fatura)}</strong>
                </article>
                <article>
                    <span>Limite total</span>
                    <strong>${formatarMoeda(resumoFatura.limite_total)}</strong>
                </article>
                <article>
                    <span>Dispon&iacute;vel</span>
                    <strong class="${Number(resumoFatura.disponivel_total || 0) < 0 ? 'negative' : 'positive'}">${formatarMoeda(resumoFatura.disponivel_total)}</strong>
                </article>
                <article>
                    <span>Consumo</span>
                    <strong>${Math.round(Number(resumoFatura.percentual_total || 0))}%</strong>
                </article>
            </div>

            ${renderizarTabelaFaturaCategorias(resumoFatura.categorias || [])}
            ${renderizarLancamentosFatura(cartao)}
        </section>
    `;
}

function renderizarSeletorMesFatura() {
    return `
        <label class="fatura-mes-field">
            <span>M&ecirc;s da fatura</span>
            <input type="month" value="${escapeHtml(estadoCartoes.mesSelecionado)}" data-action="alterar-mes-fatura">
        </label>
    `;
}

function classeStatusFatura(status) {
    const normalizado = normalizarBusca(status);
    if (normalizado.includes('estourado')) return 'status-estourado';
    if (normalizado.includes('atencao')) return 'status-atencao';
    if (normalizado.includes('revisar')) return 'status-revisar';
    return 'status-normal';
}

function rotuloStatusFatura(status) {
    if (status === 'Atencao') return 'Aten&ccedil;&atilde;o';
    return escapeHtml(status || 'Normal');
}

function valorOuTraco(valor) {
    return valor === null || valor === undefined ? '&mdash;' : formatarMoeda(valor);
}

function percentualOuTraco(valor) {
    return valor === null || valor === undefined ? '&mdash;' : `${Math.round(Number(valor || 0))}%`;
}

function filtroCategoriaFatura(categoria) {
    if (categoria.sem_categoria) return 'sem_categoria';
    if (categoria.categoria_cartao_id) return String(categoria.categoria_cartao_id);
    return 'todos';
}

function renderizarTabelaFaturaCategorias(categorias) {
    if (!categorias.length) {
        return `
            <div class="table-empty">
                <h4>Nenhum lan&ccedil;amento na fatura</h4>
                <p>Configure as Categorias do Cart&atilde;o para acompanhar limites e consumo.</p>
            </div>
        `;
    }

    return `
        <div class="fatura-table">
            <div class="fatura-table-header">
                <div>Categoria do Cart&atilde;o</div>
                <div>Limite</div>
                <div>Gasto</div>
                <div>Dispon&iacute;vel</div>
                <div>Status</div>
                <div>A&ccedil;&otilde;es</div>
            </div>
            ${categorias.map((categoria) => {
                const filtro = filtroCategoriaFatura(categoria);
                const percentual = categoria.percentual;
                const cor = categoria.categoria_cartao_cor || (categoria.sem_categoria ? '#f97316' : '#2563eb');
                return `
                    <div class="fatura-table-row ${categoria.sem_categoria ? 'sem-categoria-row' : ''}">
                        <div class="table-category">
                            <span class="categoria-icon" style="color:${escapeHtml(cor)}">${renderizarIconeCategoriaCartao({
                                icone: categoria.categoria_cartao_icone,
                                cor
                            }, '18px')}</span>
                            <span>${escapeHtml(categoria.categoria_cartao_nome)}</span>
                        </div>
                        <div>${valorOuTraco(categoria.limite_mensal)}</div>
                        <div class="usage-cell">
                            <strong>${formatarMoeda(categoria.gasto_atual)}</strong>
                            <small>${percentualOuTraco(percentual)}</small>
                            <span class="progress-track"><span class="${classeStatusFatura(categoria.status)}" style="width:${Math.min(Number(percentual || 0), 100)}%"></span></span>
                        </div>
                        <div class="${Number(categoria.disponivel || 0) < 0 ? 'negative' : 'positive'}">${valorOuTraco(categoria.disponivel)}</div>
                        <div>
                            <span class="compact-pill ${classeStatusFatura(categoria.status)}">${rotuloStatusFatura(categoria.status)}</span>
                        </div>
                        <div>
                            <button class="cf-button cf-button-secondary fatura-action" type="button" data-action="ver-lancamentos-fatura" data-filtro-fatura="${escapeHtml(filtro)}">
                                Ver lan&ccedil;amentos
                            </button>
                        </div>
                        ${categoria.avisos?.length ? `<div class="fatura-row-warning">${escapeHtml(categoria.avisos[0])}</div>` : ''}
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

function renderizarLancamentosFatura(cartao) {
    const filtro = estadoCartoes.filtroLancamentosFatura || 'todos';
    const lancamentos = obterLancamentosFatura(cartao.id, filtro);
    const titulo = filtro === 'todos'
        ? 'Lan&ccedil;amentos da fatura'
        : (filtro === 'sem_categoria' ? 'Lan&ccedil;amentos sem Categoria do Cart&atilde;o' : 'Lan&ccedil;amentos da categoria selecionada');

    return `
        <section class="fatura-lancamentos">
            <div class="fatura-lancamentos-header">
                <div>
                    <h4>${titulo}</h4>
                    <p>Categoria de Despesa e Categoria do Cart&atilde;o aparecem separadas.</p>
                </div>
                <button class="cf-button cf-button-secondary" type="button" data-action="ver-lancamentos-fatura" data-filtro-fatura="todos">Todos</button>
            </div>
            ${lancamentos.length ? `
                <div class="fatura-lancamentos-table">
                    <div class="fatura-lancamentos-thead">
                        <span>Descri&ccedil;&atilde;o</span>
                        <span>Data</span>
                        <span>Cat. Despesa</span>
                        <span>Cat. Cart&atilde;o</span>
                        <span>Parcela</span>
                        <span>Valor</span>
                        <span>A&ccedil;&otilde;es</span>
                    </div>
                    ${lancamentos.map((lancamento) => `
                        <div class="fatura-lancamento-row ${lancamento.status_classificacao !== 'classificado' ? 'needs-review' : ''}">
                            <div class="fatura-lancamento-desc">
                                <strong>${escapeHtml(lancamento.descricao)}</strong>
                            </div>
                            <span class="fatura-lancamento-cell">${escapeHtml(lancamento.data || '-')}</span>
                            <span class="fatura-lancamento-cell">${escapeHtml(lancamento.categoria_nome || '—')}</span>
                            <span class="fatura-lancamento-cell ${!lancamento.categoria_cartao_nome ? 'fatura-cell--sem-cat' : ''}">${escapeHtml(lancamento.categoria_cartao_nome || 'Sem categoria')}</span>
                            <span class="fatura-lancamento-cell">${escapeHtml(String(lancamento.parcela_atual || 1))}/${escapeHtml(String(lancamento.parcelas_total || 1))}</span>
                            <span class="fatura-lancamento-cell fatura-lancamento-valor">${formatarMoeda(lancamento.valor)}</span>
                            <div class="lancamento-acoes">
                                <button class="lancamento-icon-btn" type="button" data-action="editar-lancamento" data-lancamento-id="${lancamento.id}" title="Editar lançamento" aria-label="Editar">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                                </button>
                                <button class="lancamento-icon-btn lancamento-icon-btn--parcelamento ${lancamentoTemParcelamentoGerenciavel(lancamento) ? '' : 'is-disabled'}" type="button" ${lancamentoTemParcelamentoGerenciavel(lancamento) ? `data-action="gerenciar-parcelamento" data-lancamento-id="${lancamento.id}"` : 'disabled'} title="Gerenciar parcelamento" aria-label="Gerenciar parcelamento">
                                    ${cartoesIcon('layers')}
                                </button>
                                <button class="lancamento-icon-btn lancamento-icon-btn--danger" type="button" data-action="excluir-lancamento" data-lancamento-id="${lancamento.id}" data-lancamento-desc="${escapeHtml(lancamento.descricao)}" title="Excluir lançamento" aria-label="Excluir">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/></svg>
                                </button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            ` : `
                <div class="table-empty">
                    <h4>Nenhum lan&ccedil;amento nesta sele&ccedil;&atilde;o</h4>
                    <p>Nenhum movimento foi encontrado para o filtro atual.</p>
                </div>
            `}
        </section>
    `;
}

function lancamentoTemParcelamentoGerenciavel(lancamento) {
    return Number(lancamento.parcelas_total || lancamento.total_parcelas || 1) > 1 && Boolean(lancamento.compra_id);
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
                    <button class="cf-button cf-button-secondary cf-button--icon" type="button" data-action="vincular-disponivel" data-categoria-cartao-id="${categoria.id}" title="Vincular" aria-label="Vincular ${escapeHtml(categoria.nome)}">
                        <span aria-hidden="true">+</span>
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
    } else if (action === 'ver-lancamentos-fatura') {
        const cartao = obterCartaoSelecionado();
        if (!cartao) return;
        estadoCartoes.filtroLancamentosFatura = button.dataset.filtroFatura || 'todos';
        await carregarLancamentosFaturaCartao(cartao.id, estadoCartoes.filtroLancamentosFatura);
        renderizarDetalheCartao();
    } else if (action === 'editar-lancamento') {
        abrirModalEditarLancamento(Number(button.dataset.lancamentoId));
    } else if (action === 'gerenciar-parcelamento') {
        await abrirModalGerenciarParcelamento(Number(button.dataset.lancamentoId));
    } else if (action === 'excluir-lancamento') {
        await confirmarExcluirLancamento(Number(button.dataset.lancamentoId), button.dataset.lancamentoDesc);
    }
}

async function tratarMudancaDetalhe(event) {
    const campo = event.target.closest('[data-action="alterar-mes-fatura"]');
    if (!campo) return;

    const cartao = obterCartaoSelecionado();
    if (!cartao || !campo.value) return;

    estadoCartoes.mesSelecionado = campo.value;
    estadoCartoes.filtroLancamentosFatura = 'todos';
    renderizarDetalheCartao();
    try {
        await carregarLimitesCartao(cartao.id);
        await carregarFaturaSelecionada();
        renderizarTelaCartoes();
    } catch (error) {
        console.error('Erro ao alterar mes da fatura:', error);
        mostrarErro(`Erro ao carregar fatura: ${error.message}`);
    }
}

function renderizarMarcaCartao(cartao, tamanho = 'md') {
    const nome = obterInstituicaoCartao(cartao) || cartao?.nome || 'Cartao';
    if (window.InstituicoesUI?.renderLogo) {
        return window.InstituicoesUI.renderLogo(nome, {
            tipo: 'cartao',
            tamanho
        });
    }

    const nomeFallback = String(nome || 'CC').trim();
    const partes = nomeFallback.split(/\s+/);
    const sigla = partes.length > 1
        ? `${partes[0][0] || ''}${partes[1][0] || ''}`
        : nomeFallback.slice(0, 2);
    return `<span>${escapeHtml(sigla.toUpperCase())}</span>`;
}

function obterInstituicaoCartao(cartao) {
    return String(cartao?.descricao || cartao?.emissor || cartao?.banco || cartao?.nome || '').trim();
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
        await carregarFaturaCartao(cartao.id);
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
        await carregarFaturaCartao(cartao.id);
        renderizarTelaCartoes();
        mostrarSucesso(limite.ativo ? 'V\u00ednculo desativado.' : 'V\u00ednculo reativado.');
    } catch (error) {
        console.error('Erro ao atualizar vinculo:', error);
        mostrarErro(`Erro ao atualizar vinculo: ${error.message}`);
    }
}

// ---------------------------------------------------------------------------
// Editar / Excluir lançamento de fatura
// ---------------------------------------------------------------------------

function _obterLancamentoPorId(id) {
    for (const lista of estadoCartoes.lancamentosFatura.values()) {
        const found = lista.find((l) => l.id === id);
        if (found) return found;
    }
    return null;
}

async function carregarCategoriasDespesaLancamento() {
    if (estadoCartoes.categoriasDespesa.length) return estadoCartoes.categoriasDespesa;

    const resp = await fetchJson(`${API_CATEGORIAS}?ativo=true`);
    const categorias = resp.data || resp || [];
    estadoCartoes.categoriasDespesa = categorias;
    return categorias;
}

async function preencherCategoriasDespesaLancamento(select, selecionadaId = null) {
    if (!select) return false;

    select.disabled = true;
    select.innerHTML = '<option value="">Carregando categorias...</option>';

    try {
        const categorias = await carregarCategoriasDespesaLancamento();
        select.innerHTML = '<option value="">Selecione uma categoria</option>' + categorias.map((categoria) => (
            `<option value="${categoria.id}" ${Number(selecionadaId) === Number(categoria.id) ? 'selected' : ''}>${escapeHtml(categoria.nome)}</option>`
        )).join('');
        select.disabled = false;
        return true;
    } catch (error) {
        select.innerHTML = '<option value="">Não foi possível carregar as categorias de despesa.</option>';
        select.disabled = true;
        mostrarErro('Não foi possível carregar as categorias de despesa.');
        return false;
    }
}

async function abrirModalEditarLancamento(lancamentoId) {
    const lanc = _obterLancamentoPorId(lancamentoId);
    if (!lanc) return;

    document.getElementById('lancamento-edit-id').value = lanc.id;
    document.getElementById('lancamento-edit-descricao').value = lanc.descricao || '';
    document.getElementById('lancamento-edit-valor').value = lanc.valor || '';
    document.getElementById('lancamento-edit-data').value = lanc.data_compra || lanc.data || '';
    document.getElementById('lancamento-edit-parcela').value = lanc.numero_parcela || lanc.parcela_atual || 1;
    document.getElementById('lancamento-edit-total-parcelas').value = lanc.total_parcelas || lanc.parcelas_total || 1;

    const selCat = document.getElementById('lancamento-edit-categoria');
    await preencherCategoriasDespesaLancamento(selCat, lanc.categoria_id);

    abrirModal('modal-editar-lancamento');
}

async function salvarEdicaoLancamento(event) {
    event.preventDefault();
    const id = Number(document.getElementById('lancamento-edit-id').value);
    const payload = {
        descricao: document.getElementById('lancamento-edit-descricao').value.trim(),
        valor: parseFloat(document.getElementById('lancamento-edit-valor').value),
        data_compra: document.getElementById('lancamento-edit-data').value,
        categoria_id: document.getElementById('lancamento-edit-categoria').value || null,
        numero_parcela: parseInt(document.getElementById('lancamento-edit-parcela').value, 10) || 1,
        total_parcelas: parseInt(document.getElementById('lancamento-edit-total-parcelas').value, 10) || 1,
    };
    try {
        await fetchJson(`/api/cartoes/lancamentos/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        fecharModal('modal-editar-lancamento');
        const cartao = obterCartaoSelecionado();
        if (cartao) {
            await carregarFaturaSelecionada();
            renderizarDetalheCartao();
        }
    } catch (err) {
        mostrarErro(`Erro ao salvar lançamento: ${err.message}`);
    }
}

async function confirmarExcluirLancamento(lancamentoId, descricao) {
    if (!confirm(`Excluir o lançamento "${descricao}"?\nEsta ação não pode ser desfeita.`)) return;
    try {
        await fetchJson(`/api/cartoes/lancamentos/${lancamentoId}`, { method: 'DELETE' });
        const cartao = obterCartaoSelecionado();
        if (cartao) {
            await carregarFaturaSelecionada();
            renderizarDetalheCartao();
        }
    } catch (err) {
        mostrarErro(`Erro ao excluir lançamento: ${err.message}`);
    }
}

function formatarCompetenciaParcelamento(competencia) {
    if (!competencia || !/^\d{4}-\d{2}/.test(competencia)) return competencia || '-';
    const [ano, mes] = competencia.split('-');
    return `${mes}/${ano}`;
}

function statusParcelaLabel(status) {
    const labels = {
        paga: 'Paga',
        fechada: 'Fechada',
        passada: 'Passada',
        atual: 'Atual',
        futura: 'Futura'
    };
    return labels[status] || 'Futura';
}

async function abrirModalGerenciarParcelamento(lancamentoId) {
    try {
        const resp = await fetchJson(`${API_CARTOES}/lancamentos/${lancamentoId}/parcelamento`);
        estadoCartoes.parcelamentoGestao = resp.data;
        await preencherCategoriasDespesaLancamento(
            document.getElementById('parcelamento-gestao-categoria'),
            resp.data?.base?.categoria_id
        );
        preencherModalGerenciarParcelamento(resp.data);
        abrirModal('modal-gerenciar-parcelamento');
    } catch (error) {
        mostrarErro(`Erro ao carregar parcelamento: ${error.message}`);
    }
}

function preencherModalGerenciarParcelamento(data) {
    const base = data?.base || {};
    const parcelas = data?.parcelas || [];
    const descricaoInput = document.getElementById('parcelamento-gestao-descricao');
    const valorInput = document.getElementById('parcelamento-gestao-valor');
    const resumo = document.getElementById('parcelamento-gestao-resumo');
    const tbody = document.getElementById('parcelamento-gestao-parcelas');
    const btnCancelarFuturas = document.getElementById('btn-cancelar-parcelas-futuras');

    if (descricaoInput) descricaoInput.value = base.descricao || '';
    if (valorInput) valorInput.value = base.valor || '';
    if (btnCancelarFuturas) btnCancelarFuturas.disabled = Number(base.futuras_editaveis || 0) === 0;

    if (resumo) {
        resumo.innerHTML = `
            <div><span>Descri&ccedil;&atilde;o</span><strong>${escapeHtml(base.descricao || '-')}</strong></div>
            <div><span>Cart&atilde;o</span><strong>${escapeHtml(base.cartao_nome || '-')}</strong></div>
            <div><span>Valor da parcela</span><strong>${formatarMoeda(base.valor)}</strong></div>
            <div><span>Parcela atual</span><strong>${escapeHtml(base.parcela_atual || '-')}/${escapeHtml(base.total_parcelas || '-')}</strong></div>
            <div><span>Primeira compet&ecirc;ncia</span><strong>${escapeHtml(formatarCompetenciaParcelamento(base.primeira_competencia))}</strong></div>
            <div><span>&Uacute;ltima compet&ecirc;ncia</span><strong>${escapeHtml(formatarCompetenciaParcelamento(base.ultima_competencia))}</strong></div>
            <div><span>Categoria da despesa</span><strong>${escapeHtml(base.categoria_nome || '-')}</strong></div>
            <div><span>Futuras edit&aacute;veis</span><strong>${escapeHtml(base.futuras_editaveis || 0)}</strong></div>
        `;
    }

    if (tbody) {
        tbody.innerHTML = parcelas.length ? parcelas.map((parcela) => `
            <tr>
                <td>${escapeHtml(parcela.parcela || '-')}</td>
                <td>${escapeHtml(formatarCompetenciaParcelamento(parcela.competencia))}</td>
                <td>${escapeHtml(parcela.data_compra || '-')}</td>
                <td>${formatarMoeda(parcela.valor)}</td>
                <td><span class="parcelamento-status ${escapeHtml(parcela.status || 'futura')}">${escapeHtml(statusParcelaLabel(parcela.status))}</span></td>
                <td>${parcela.editavel ? 'Edit&aacute;vel neste MVP' : 'Preservada'}</td>
            </tr>
        `).join('') : '<tr><td colspan="6">Nenhuma parcela relacionada encontrada.</td></tr>';
    }
}

async function salvarParcelasFuturas(event) {
    event.preventDefault();
    const baseId = estadoCartoes.parcelamentoGestao?.base?.id;
    if (!baseId) return;

    const payload = {
        descricao: document.getElementById('parcelamento-gestao-descricao')?.value.trim(),
        categoria_id: document.getElementById('parcelamento-gestao-categoria')?.value || null,
        valor: document.getElementById('parcelamento-gestao-valor')?.value || null
    };

    try {
        const resp = await fetchJson(`${API_CARTOES}/lancamentos/${baseId}/parcelamento/futuras`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        estadoCartoes.parcelamentoGestao = resp.data?.parcelamento || estadoCartoes.parcelamentoGestao;
        preencherModalGerenciarParcelamento(estadoCartoes.parcelamentoGestao);
        const cartao = obterCartaoSelecionado();
        if (cartao) {
            await carregarFaturaSelecionada();
            renderizarDetalheCartao();
        }
        mostrarSucesso(`${resp.data?.atualizadas || 0} parcela(s) futura(s) atualizada(s).`);
    } catch (error) {
        mostrarErro(`Erro ao atualizar parcelas futuras: ${error.message}`);
    }
}

async function cancelarParcelasFuturas() {
    const baseId = estadoCartoes.parcelamentoGestao?.base?.id;
    if (!baseId) return;
    if (!confirm('Esta aÃ§Ã£o afetarÃ¡ apenas as parcelas futuras deste parcelamento. As parcelas anteriores nÃ£o serÃ£o alteradas.')) return;

    try {
        const resp = await fetchJson(`${API_CARTOES}/lancamentos/${baseId}/parcelamento/cancelar-futuras`, {
            method: 'POST'
        });
        estadoCartoes.parcelamentoGestao = resp.data?.parcelamento || estadoCartoes.parcelamentoGestao;
        preencherModalGerenciarParcelamento(estadoCartoes.parcelamentoGestao);
        const cartao = obterCartaoSelecionado();
        if (cartao) {
            await carregarFaturaSelecionada();
            renderizarDetalheCartao();
        }
        mostrarSucesso(`${resp.data?.canceladas || 0} parcela(s) futura(s) cancelada(s).`);
    } catch (error) {
        mostrarErro(`Erro ao cancelar parcelas futuras: ${error.message}`);
    }
}

function abrirModal(modalId) {
    document.getElementById(modalId)?.classList.add('open');
}

function fecharModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.remove('open');
    if (modalId === 'modal-gerenciar-parcelamento') {
        estadoCartoes.parcelamentoGestao = null;
    }
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
