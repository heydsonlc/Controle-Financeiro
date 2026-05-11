const DASHBOARD_API = '/api/dashboard/resumo';

let dashboardChart = null;
let dashboardState = null;

const ICONS = {
    wallet: '<path d="M5 7h14v11H5z"/><path d="M16 12h3v4h-3a2 2 0 0 1 0-4Z"/><path d="M7 7V5h9v2"/>',
    trend: '<path d="M4 16 9 11l4 4 7-8"/><path d="M15 7h5v5"/>',
    card: '<path d="M4 7h16v10H4z"/><path d="M4 10h16"/>',
    refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v5h-5"/>',
    calendar: '<path d="M7 4v3M17 4v3M5 9h14"/><path d="M5 6h14v14H5z"/>',
    clock: '<path d="M12 6v6l4 2"/><path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/>',
    entry: '<path d="M5 6h14M5 12h14M5 18h9"/><path d="m17 16 2 2 3-4"/>',
    alert: '<path d="M12 5 3.5 19h17z"/><path d="M12 10v4M12 17h.1"/>',
    car: '<path d="M5 16h14l-1.4-5A2 2 0 0 0 15.7 9H8.3a2 2 0 0 0-1.9 2L5 16Z"/><path d="M7 16v3M17 16v3M8 19h.1M16 19h.1"/>',
    phone: '<path d="M8 3h8a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"/><path d="M11 18h2"/>',
    import: '<path d="M12 4v10M8 10l4 4 4-4M5 18h14"/>',
    category: '<path d="M5 6h14M5 12h14M5 18h14"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    dots: '<path d="M12 5h.1M12 12h.1M12 19h.1"/>'
};

document.addEventListener('DOMContentLoaded', () => {
    preencherIcones();
    inicializarPeriodo();
    bindDashboardEvents();
    renderAcoesRapidas();
    carregarDashboardOperacional();
});

function preencherIcones() {
    document.querySelectorAll('[data-icon]').forEach((element) => {
        const icon = ICONS[element.dataset.icon] || ICONS.wallet;
        element.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${icon}</svg>`;
    });
}

function bindDashboardEvents() {
    const atualizar = document.getElementById('dashboard-atualizar');
    const periodo = document.getElementById('dashboard-periodo');

    atualizar?.addEventListener('click', () => carregarDashboardOperacional());
    periodo?.addEventListener('change', () => carregarDashboardOperacional());
}

function inicializarPeriodo() {
    const input = document.getElementById('dashboard-periodo');
    if (!input) return;
    const hoje = new Date();
    const mes = String(hoje.getMonth() + 1).padStart(2, '0');
    input.value = `${hoje.getFullYear()}-${mes}`;
}

async function carregarDashboardOperacional() {
    const periodo = document.getElementById('dashboard-periodo')?.value || '';
    const params = new URLSearchParams();
    if (periodo) params.set('mes_referencia', periodo);

    try {
        aplicarEstadoCarregando();
        const response = await fetch(`${DASHBOARD_API}?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok || payload?.success === false) {
            throw new Error(payload?.error || 'Erro ao carregar dashboard');
        }
        dashboardState = payload.data;
        renderDashboard(payload.data);
    } catch (error) {
        console.error('Erro ao carregar dashboard operacional:', error);
        renderErroDashboard();
    }
}

function aplicarEstadoCarregando() {
    document.querySelectorAll('.dashboard-panel, .dashboard-kpi-card, .dashboard-op-card').forEach((el) => {
        el.classList.add('is-loading');
    });
}

function limparEstadoCarregando() {
    document.querySelectorAll('.is-loading').forEach((el) => el.classList.remove('is-loading'));
}

function renderDashboard(data) {
    limparEstadoCarregando();
    renderKpis(data.kpis || {});
    renderOperacional(data.operacional || {});
    renderFluxoCaixa(data.fluxo_caixa || {});
    renderCategoriasCartao(data.categorias_cartao || []);
    renderProximosVencimentos(data.proximos_vencimentos || []);
    renderCartoesLimites(data.cartoes_limites || {});
    renderMobilidade(data.mobilidade || {});
    renderAcoesRapidas(data.acoes_rapidas || []);
}

function renderKpis(kpis) {
    const saldo = kpis.saldo_consolidado || {};
    const fluxo = kpis.fluxo_projetado_30_dias || {};
    const faturas = kpis.faturas_em_aberto || {};
    const recorrencias = kpis.recorrencias_ativas || {};

    setText('kpi-saldo', formatarMoeda(saldo.valor));
    setText('kpi-saldo-sub', saldo.subtitulo || 'Disponivel em contas');
    setText('kpi-fluxo', formatarMoeda(fluxo.valor));
    setText('kpi-faturas', formatarMoeda(faturas.valor));
    setText('kpi-faturas-sub', `${faturas.quantidade_cartoes || 0} cartao(s)`);
    setText('kpi-recorrencias', recorrencias.quantidade || 0);
    setText('kpi-recorrencias-sub', `${formatarMoeda(recorrencias.valor_mensal)} / mes`);
}

function renderOperacional(operacional) {
    const previstas = operacional.despesas_previstas_mes || {};
    const vencer = operacional.contas_a_vencer_7_dias || {};
    const alertas = operacional.alertas_operacionais || {};
    const mobilidade = operacional.modalidade_mobilidade_ativa || {};

    setText('op-previstas', formatarMoeda(previstas.valor));
    setText('op-previstas-sub', `${previstas.pendentes || 0} pendentes | ${previstas.confirmadas || 0} confirmadas`);
    const bar = document.getElementById('op-previstas-bar');
    if (bar) bar.style.width = `${Math.min(previstas.percentual_orcamento || 0, 100)}%`;

    setText('op-vencer', formatarMoeda(vencer.valor));
    setText('op-vencer-sub', `${vencer.quantidade || 0} conta(s)`);

    const alertasContainer = document.getElementById('op-alertas');
    if (alertasContainer) {
        const itens = alertas.itens || [];
        alertasContainer.innerHTML = itens.length
            ? itens.slice(0, 3).map((item) => `
                <span class="alert-line ${escapeHtml(item.nivel || 'info')}">
                    <span></span>${escapeHtml(item.mensagem)}
                </span>
            `).join('')
            : '<span class="empty-inline">Sem alertas no periodo</span>';
    }

    setText('op-mobilidade', mobilidade.nome || 'Sem modalidade ativa');
    setText('op-mobilidade-sub', mobilidade.custo_mensal
        ? `Custo mensal estimado ${formatarMoeda(mobilidade.custo_mensal)}`
        : 'Configure a mobilidade');
}

function renderFluxoCaixa(fluxo) {
    const resumo = fluxo.resumo || {};
    setText('flow-receitas', formatarMoeda(resumo.receitas_previstas));
    setText('flow-despesas', formatarMoeda(resumo.despesas_previstas));
    setText('flow-saldo', formatarMoeda(resumo.saldo_final_projetado));

    const canvas = document.getElementById('fluxo-caixa-chart');
    if (!canvas || typeof Chart === 'undefined') return;

    if (dashboardChart) {
        dashboardChart.destroy();
    }

    dashboardChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: fluxo.labels || [],
            datasets: [
                datasetLinha('Entradas', fluxo.entradas || [], '#16a34a', false),
                datasetLinha('Saidas', fluxo.saidas || [], '#ef4444', false),
                datasetLinha('Saldo projetado', fluxo.saldo_projetado || [], '#2563eb', true),
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => `${context.dataset.label}: ${formatarMoeda(context.parsed.y)}`,
                    },
                },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(15, 23, 42, 0.08)' },
                    ticks: { color: '#64748b' },
                },
                y: {
                    grid: { color: 'rgba(15, 23, 42, 0.08)' },
                    ticks: {
                        color: '#64748b',
                        callback: (value) => formatarMoeda(value).replace(',00', ''),
                    },
                },
            },
        },
    });
}

function datasetLinha(label, data, color, fill) {
    return {
        label,
        data,
        borderColor: color,
        backgroundColor: fill ? 'rgba(37, 99, 235, 0.12)' : color,
        borderWidth: fill ? 3 : 2,
        pointRadius: 2,
        pointHoverRadius: 4,
        tension: 0.35,
        fill,
    };
}

const CATEGORIAS_POR_PAGINA = 5;
let _categoriasCartaoTodas = [];
let _categoriasPaginaAtual = 0;

function renderCategoriasCartao(categorias) {
    _categoriasCartaoTodas = categorias || [];
    _categoriasPaginaAtual = 0;
    _renderPaginaCategoria();
}

function mudarPaginaCategoria(delta) {
    const totalPaginas = Math.ceil(_categoriasCartaoTodas.length / CATEGORIAS_POR_PAGINA);
    _categoriasPaginaAtual = Math.max(0, Math.min(_categoriasPaginaAtual + delta, totalPaginas - 1));
    _renderPaginaCategoria();
}

function _renderPaginaCategoria() {
    const container = document.getElementById('categorias-cartao-lista');
    const paginacao = document.getElementById('categorias-cartao-paginacao');
    const infoEl = document.getElementById('categorias-pag-info');
    const btnPrev = document.getElementById('categorias-pag-prev');
    const btnNext = document.getElementById('categorias-pag-next');
    if (!container) return;

    const categorias = _categoriasCartaoTodas;

    if (!categorias.length) {
        container.innerHTML = estadoVazio('Configure Categorias do Cartao para acompanhar consumo.');
        if (paginacao) paginacao.hidden = true;
        return;
    }

    const totalPaginas = Math.ceil(categorias.length / CATEGORIAS_POR_PAGINA);
    const inicio = _categoriasPaginaAtual * CATEGORIAS_POR_PAGINA;
    const pagina = categorias.slice(inicio, inicio + CATEGORIAS_POR_PAGINA);

    const total = categorias.reduce((acc, item) => {
        acc.limite += Number(item.limite || 0);
        acc.gasto += Number(item.gasto || 0);
        acc.disponivel += Number(item.disponivel || 0);
        return acc;
    }, { limite: 0, gasto: 0, disponivel: 0 });

    const _linhaCategoria = (item) => {
        const percentual = Math.max(0, Math.min(item.percentual || 0, 100));
        const iconeCategoria = window.CategoriaCartaoIconesUI?.renderIconeCategoriaCartao
            ? window.CategoriaCartaoIconesUI.renderIconeCategoriaCartao(item, {
                size: 'sm',
                className: 'dashboard-categoria-cartao-icon',
                label: item.nome
            })
            : `<i style="--item-color:${escapeAttr(item.cor || '#2563eb')}"></i>`;
        return `<div class="table-row category-row">
            <span class="category-cell">
                ${iconeCategoria}
                <span>${escapeHtml(item.nome)}</span>
            </span>
            <span class="category-progress-cell">
                <b class="progress-line" aria-label="Consumo ${percentual}%">
                    <em style="width:${percentual}%"></em>
                </b>
            </span>
            <span>${formatarMoeda(item.limite)}</span>
            <span>${formatarMoeda(item.gasto)}</span>
            <span class="positive">${formatarMoeda(item.disponivel)}</span>
        </div>`;
    };

    // 5 linhas sempre: dados + placeholders vazios
    let html = pagina.map(_linhaCategoria).join('');
    const vazias = CATEGORIAS_POR_PAGINA - pagina.length;
    for (let i = 0; i < vazias; i++) {
        html += `<div class="table-row category-row category-row--empty" aria-hidden="true"></div>`;
    }

    // Linha total separada
    html += `<div class="table-row category-row category-total-row">
        <strong>Total</strong>
        <span class="category-progress-cell"></span>
        <strong>${formatarMoeda(total.limite)}</strong>
        <strong>${formatarMoeda(total.gasto)}</strong>
        <strong class="positive">${formatarMoeda(total.disponivel)}</strong>
    </div>`;

    container.innerHTML = html;

    // Paginação
    if (paginacao) {
        paginacao.hidden = totalPaginas <= 1;
        if (infoEl) infoEl.textContent = `${_categoriasPaginaAtual + 1} / ${totalPaginas}`;
        if (btnPrev) btnPrev.disabled = _categoriasPaginaAtual === 0;
        if (btnNext) btnNext.disabled = _categoriasPaginaAtual >= totalPaginas - 1;
    }
}

function renderProximosVencimentos(vencimentos) {
    const container = document.getElementById('proximos-vencimentos');
    if (!container) return;

    if (!vencimentos.length) {
        container.innerHTML = estadoVazio('Nenhum vencimento nos proximos 7 dias.');
        return;
    }

    container.innerHTML = vencimentos.map((item) => `
        <div class="due-item">
            <span class="due-date">${formatarDataCurta(item.data)}</span>
            <strong>${escapeHtml(item.descricao)}</strong>
            <span>${escapeHtml(item.origem || item.tipo || '-')}</span>
            <b>${formatarMoeda(item.valor)}</b>
            <em class="${item.status_visual === 'vence_hoje' ? 'danger' : ''}">
                ${item.status_visual === 'vence_hoje' ? 'Vence hoje' : escapeHtml(item.status_visual)}
            </em>
        </div>
    `).join('');
}

function renderCartoesLimites(bloco) {
    const container = document.getElementById('cartoes-limites-lista');
    if (!container) return;
    const cartoes = bloco.itens || [];

    if (!cartoes.length) {
        container.innerHTML = estadoVazio('Nenhum cartao ativo no periodo.');
        return;
    }

    container.innerHTML = cartoes.map((cartao) => `
        <div class="table-row card-row">
            <span class="card-name-cell">
                ${renderBandeiraCartao(cartao)}
                <span class="card-name-main">
                    <b>${escapeHtml(cartao.nome)}</b>${cartao.final ? `<small class="card-final-inline">**** ${escapeHtml(cartao.final)}</small>` : ''}
                </span>
            </span>
            <span>${formatarMoeda(cartao.limite_total)}</span>
            <span class="card-bar-cell"><b class="progress-line"><em style="width:${Math.min(cartao.percentual || 0, 100)}%"></em></b></span>
            <span class="card-utilizado-valor">${formatarMoeda(cartao.utilizado)}</span>
            <span class="card-pct-cell"><small class="card-pct">${cartao.percentual || 0}%</small></span>
            <span class="positive">${formatarMoeda(cartao.disponivel)}</span>
            <span><mark class="status-pill ${escapeHtml(cartao.status)}">${rotuloStatus(cartao.status)}</mark></span>
        </div>
    `).join('');
}

const BANDEIRAS_CARTAO_DASHBOARD = {
    visa: {
        nome: 'Visa',
        asset: '/static/img/logo_bandeira_cartao_visa.png',
        aliases: ['visa']
    },
    mastercard: {
        nome: 'Mastercard',
        asset: '/static/img/logo_marterCard.png',
        aliases: ['mastercard', 'master card', 'master']
    },
    elo: {
        nome: 'Elo',
        asset: '/static/img/elo.png',
        aliases: ['elo']
    }
};

function normalizarBandeiraCartao(valor) {
    return String(valor || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function resolverBandeiraCartao(cartao) {
    const texto = normalizarBandeiraCartao([
        cartao?.bandeira,
        cartao?.bandeira_key,
        cartao?.nome,
        cartao?.descricao,
        cartao?.emissor
    ].filter(Boolean).join(' '));

    const encontrada = Object.entries(BANDEIRAS_CARTAO_DASHBOARD).find(([, bandeira]) => (
        bandeira.aliases.some((alias) => {
            const alvo = normalizarBandeiraCartao(alias);
            return alvo && new RegExp(`(^| )${alvo}( |$)`).test(texto);
        })
    ));

    if (!encontrada) {
        return {
            key: 'desconhecida',
            nome: 'Bandeira nao identificada',
            asset: null
        };
    }

    return {
        key: encontrada[0],
        ...encontrada[1]
    };
}

function renderBandeiraCartao(cartao) {
    const bandeira = resolverBandeiraCartao(cartao);
    const fallback = `<span class="card-brand-fallback" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false">${ICONS.card}</svg></span>`;
    if (!bandeira.asset) {
        return `<span class="card-brand card-brand--fallback" title="${escapeAttr(bandeira.nome)}" aria-label="${escapeAttr(bandeira.nome)}">${fallback}</span>`;
    }

    return `
        <span class="card-brand card-brand--${escapeAttr(bandeira.key)}" title="${escapeAttr(bandeira.nome)}" aria-label="${escapeAttr(bandeira.nome)}">
            <img src="${escapeAttr(bandeira.asset)}" alt="" loading="lazy" onerror="this.hidden=true;this.nextElementSibling.hidden=false;">
            <span class="card-brand-fallback" hidden>${fallback}</span>
        </span>
    `;
}

function renderMobilidade(mobilidade) {
    const container = document.getElementById('mobilidade-resumo');
    if (!container) return;

    const cenarios = montarCenariosMobilidade(mobilidade);

    const cards = cenarios.map(({ modalidade, item, status }) => {
        const valor = item && item.custo_mensal !== undefined && item.custo_mensal !== null
            ? formatarMoeda(item.custo_mensal)
            : '&mdash;';

        return `
            <article class="mobility-option ${status.classe}">
                <div class="mobility-option-header">
                    <span class="mobility-option-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" focusable="false">${ICONS[modalidade.icon]}</svg>
                    </span>
                    <strong>${escapeHtml(modalidade.nome)}</strong>
                </div>
                <span>Custo mensal</span>
                <b>${valor}</b>
                <em>${status.rotulo}</em>
            </article>
        `;
    }).join('');

    container.innerHTML = `
        <div class="mobility-options-grid">
            ${cards}
        </div>
    `;
}

function definicoesMobilidade() {
    return [
        { tipo: 'VEICULO', nome: 'Ve\u00edculo pr\u00f3prio', icon: 'car' },
        { tipo: 'ASSINATURA', nome: 'Assinatura', icon: 'card' },
        { tipo: 'TRANSPORTE_APP', nome: 'Transporte por app', icon: 'phone' },
    ];
}

function montarCenariosMobilidade(mobilidade) {
    const modalidades = definicoesMobilidade();
    const tipoAtivo = mobilidade.status === 'ativa' ? normalizarTipoMobilidade(mobilidade.tipo) : '';
    const alternativas = new Map();

    (mobilidade.alternativas || []).forEach((item) => {
        const tipo = normalizarTipoMobilidade(item.tipo);
        if (tipo && !alternativas.has(tipo)) alternativas.set(tipo, item);
    });

    if (!tipoAtivo) {
        return modalidades.slice(0, 2).map((modalidade) => ({
            modalidade,
            item: null,
            status: definirStatusMobilidade(modalidade.tipo, tipoAtivo, null)
        }));
    }

    const cenarios = [];
    const modalidadeAtiva = modalidades.find((modalidade) => modalidade.tipo === tipoAtivo) || {
        tipo: tipoAtivo,
        nome: mobilidade.nome || 'Mobilidade',
        icon: 'car'
    };

    cenarios.push({
        modalidade: modalidadeAtiva,
        item: mobilidade,
        status: definirStatusMobilidade(modalidadeAtiva.tipo, tipoAtivo, alternativas.get(modalidadeAtiva.tipo))
    });

    const alternativa = modalidades
        .filter((modalidade) => modalidade.tipo !== tipoAtivo)
        .map((modalidade) => ({
            modalidade,
            item: alternativas.get(modalidade.tipo) || null,
            status: definirStatusMobilidade(modalidade.tipo, tipoAtivo, alternativas.get(modalidade.tipo))
        }))
        .sort((a, b) => {
            const peso = (cenario) => cenario.item ? 0 : 1;
            return peso(a) - peso(b);
        })[0];

    if (alternativa) {
        cenarios.push(alternativa);
    }

    return cenarios.slice(0, 2);
}

function normalizarTipoMobilidade(tipo) {
    return String(tipo || '').toUpperCase();
}

function definirStatusMobilidade(tipo, tipoAtivo, itemAlternativo) {
    if (tipoAtivo === tipo) {
        return { rotulo: 'Ativo', classe: 'active' };
    }

    if (itemAlternativo) {
        return { rotulo: 'Alternativa', classe: 'alternative' };
    }

    if (!tipoAtivo) {
        return { rotulo: 'Pendente', classe: 'pending' };
    }

    return { rotulo: 'N\u00e3o configurado', classe: 'not-configured' };
}

function renderAcoesRapidas() {
    const container = document.getElementById('acoes-rapidas');
    if (!container) return;

    const acoes = [
        { label: 'Confirmar despesas previstas', url: '/despesas', icon: 'check' },
        { label: 'Importar fatura', url: '/importar-cartao', icon: 'import' },
        { label: 'Lan\u00e7amentos', url: '/lancamentos', icon: 'entry' },
        { label: 'Revisar recorr\u00eancias', url: '/recorrencias', icon: 'refresh' },
        { label: 'Gerenciar mobilidade', url: '/veiculos', icon: 'car' },
    ];

    container.innerHTML = acoes.map((acao, index) => `
        <a href="${escapeAttr(acao.url || '#')}" class="quick-action-link tone-${index % 5}">
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[acao.icon] || ICONS.dots}</svg>
            ${escapeHtml(acao.label)}
        </a>
    `).join('');
}

function renderErroDashboard() {
    limparEstadoCarregando();
    const containers = [
        'categorias-cartao-lista',
        'proximos-vencimentos',
        'cartoes-limites-lista',
        'mobilidade-resumo',
    ];
    containers.forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = estadoVazio('Nao foi possivel carregar os dados agora.');
    });
    renderAcoesRapidas();
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function formatarMoeda(valor) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL',
    }).format(Number(valor || 0));
}

function formatarDataCurta(data) {
    if (!data) return '-';
    const partes = String(data).split('-');
    if (partes.length !== 3) return data;
    return `${partes[2]}/${partes[1]}`;
}

function rotuloStatus(status) {
    const mapa = {
        normal: 'Normal',
        atencao: 'Atencao',
        estourado: 'Estourado',
        revisar: 'Revisar',
    };
    return mapa[status] || 'Normal';
}

function estadoVazio(texto) {
    return `<div class="dashboard-empty">${escapeHtml(texto)}</div>`;
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, '&#096;');
}
