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
    alert: '<path d="M12 5 3.5 19h17z"/><path d="M12 10v4M12 17h.1"/>',
    car: '<path d="M5 16h14l-1.4-5A2 2 0 0 0 15.7 9H8.3a2 2 0 0 0-1.9 2L5 16Z"/><path d="M7 16v3M17 16v3M8 19h.1M16 19h.1"/>',
    import: '<path d="M12 4v10M8 10l4 4 4-4M5 18h14"/>',
    category: '<path d="M5 6h14M5 12h14M5 18h14"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    dots: '<path d="M12 5h.1M12 12h.1M12 19h.1"/>'
};

document.addEventListener('DOMContentLoaded', () => {
    preencherIcones();
    inicializarPeriodo();
    bindDashboardEvents();
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
    const filtros = document.getElementById('dashboard-filtros');
    const periodo = document.getElementById('dashboard-periodo');

    atualizar?.addEventListener('click', () => carregarDashboardOperacional());
    filtros?.addEventListener('click', () => periodo?.focus());
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

function renderCategoriasCartao(categorias) {
    const container = document.getElementById('categorias-cartao-lista');
    if (!container) return;

    if (!categorias.length) {
        container.innerHTML = estadoVazio('Configure Categorias do Cartao para acompanhar consumo.');
        return;
    }

    container.innerHTML = categorias.map((item) => `
        <div class="table-row category-row">
            <span class="category-cell">
                <i style="--item-color:${escapeAttr(item.cor || '#2563eb')}"></i>
                ${escapeHtml(item.nome)}
            </span>
            <span>${formatarMoeda(item.limite)}</span>
            <span>
                ${formatarMoeda(item.gasto)}
                <small>${item.percentual || 0}%</small>
                <b class="progress-line"><em style="width:${Math.min(item.percentual || 0, 100)}%"></em></b>
            </span>
            <span class="positive">${formatarMoeda(item.disponivel)}</span>
        </div>
    `).join('');
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
                <b>${escapeHtml(cartao.nome)}</b>
                <small>${cartao.final ? `**** ${escapeHtml(cartao.final)}` : 'Final nao informado'}</small>
            </span>
            <span>${formatarMoeda(cartao.limite_total)}</span>
            <span>
                ${formatarMoeda(cartao.utilizado)}
                <small>${cartao.percentual || 0}%</small>
                <b class="progress-line"><em style="width:${Math.min(cartao.percentual || 0, 100)}%"></em></b>
            </span>
            <span class="positive">${formatarMoeda(cartao.disponivel)}</span>
            <span><mark class="status-pill ${escapeHtml(cartao.status)}">${rotuloStatus(cartao.status)}</mark></span>
        </div>
    `).join('');
}

function renderMobilidade(mobilidade) {
    const container = document.getElementById('mobilidade-resumo');
    if (!container) return;

    const principal = `
        <article class="mobility-option active">
            <strong>${escapeHtml(mobilidade.nome || 'Sem modalidade ativa')}</strong>
            <span>Custo mensal</span>
            <b>${formatarMoeda(mobilidade.custo_mensal)}</b>
            <em>${mobilidade.status === 'ativa' ? 'Ativo' : 'Pendente'}</em>
        </article>
    `;

    const alternativas = (mobilidade.alternativas || []).slice(0, 2).map((item) => `
        <article class="mobility-option">
            <strong>${escapeHtml(item.nome)}</strong>
            <span>${escapeHtml(item.tipo || 'Alternativa')}</span>
            <b>${formatarMoeda(item.custo_mensal)}</b>
            <em>Alternativa</em>
        </article>
    `).join('');

    container.innerHTML = principal + (alternativas || '');
}

function renderAcoesRapidas(acoes) {
    const container = document.getElementById('acoes-rapidas');
    if (!container) return;

    const iconMap = ['check', 'import', 'category', 'refresh', 'dots'];
    container.innerHTML = (acoes || []).map((acao, index) => `
        <a href="${escapeAttr(acao.url || '#')}" class="quick-action-link tone-${index % 5}">
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[iconMap[index] || 'dots']}</svg>
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
        'acoes-rapidas',
    ];
    containers.forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = estadoVazio('Nao foi possivel carregar os dados agora.');
    });
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
