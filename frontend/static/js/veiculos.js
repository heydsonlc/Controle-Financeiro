const API_VEICULOS = '/api/veiculos';
const API_CATEGORIAS = '/api/categorias';
const API_DESPESAS_PREVISTAS = '/api/despesas-previstas';
const API_INDEXADORES_TIPOS = '/api/indexadores/tipos';
const API_MOBILIDADE_APP = '/api/mobilidade-app';
const API_ASSINATURAS = `${API_VEICULOS}/mobilidade/assinaturas`;

const STORAGE_MOBILIDADE_ATIVA = 'mobilidade_caminhos_ativos_v1';

let mobilidadeAtiva = {
    VEICULO: new Set(),
    TRANSPORTE_APP: new Set(),
};

let custoMensalConsolidado = {
    VEICULO: {},
    TRANSPORTE_APP: {},
};

let categorias = [];
let veiculoEditando = null;
let projecoesIndex = {};
let finVeiculoCache = {};
let appEditando = null;
let appPerfis = [];
let assinaturaEditando = null;

let caminhosVeiculos = null;
let caminhosApps = null;
let caminhosAssinaturas = null;

const MOBILIDADE_IMAGENS = {
    veiculoCompacto: '/static/img/Veiculo_pessoal_1.png',
    veiculoMedio: '/static/img/Veiculo_pessoal_2.png',
    veiculoSuv: '/static/img/Veiculo_pessoal_3.png',
    assinatura: '/static/img/transporte_por_assinatura.png',
    app: '/static/img/Transporte_por_App.png',
};

function veiculosIcon(name) {
    const icons = {
        edit: '<path d="M5 19h4L19 9a2.1 2.1 0 0 0-3-3L6 16l-1 3Z"/><path d="M14 6l4 4"/>',
        eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.5"/>',
        file: '<path d="M7 4h7l4 4v12H7V4Z"/><path d="M14 4v4h4"/><path d="M9 13h6M9 17h6"/>',
        trash: '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>',
        check: '<path d="M5 12.5l4 4L19 7"/>',
        clock: '<path d="M12 6v6l4 2"/><path d="M20 12a8 8 0 1 1-8-8"/>',
        remove: '<path d="M6 6l12 12M18 6 6 18"/>'
    };
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" style="width:1em;height:1em;display:inline-block;vertical-align:-0.125em;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;">${icons[name] || icons.eye}</svg>`;
}

function _textoModalidadeImagem(cenario) {
    const raw = cenario?.raw || cenario || {};
    return `${raw.nome || cenario?.nome || ''} ${raw.tipo || ''} ${raw.combustivel || ''}`.toLowerCase();
}

function imagemModalidade(cenario) {
    const tipo = String(cenario?.tipo || cenario?.tipo_modalidade || '').toUpperCase();
    const texto = _textoModalidadeImagem(cenario);
    if (tipo === 'ASSINATURA') return MOBILIDADE_IMAGENS.assinatura;
    if (tipo === 'TRANSPORTE_APP') return MOBILIDADE_IMAGENS.app;
    if (texto.includes('suv') || texto.includes('assinatura')) return MOBILIDADE_IMAGENS.veiculoSuv;
    if (texto.includes('city') || texto.includes('civic') || texto.includes('corolla') || texto.includes('sedan medio') || texto.includes('sedan médio')) {
        return MOBILIDADE_IMAGENS.veiculoMedio;
    }
    return MOBILIDADE_IMAGENS.veiculoCompacto;
}

function fallbackImagemModalidade(tipo) {
    const tipoNorm = String(tipo || '').toUpperCase();
    if (tipoNorm === 'TRANSPORTE_APP') {
        return `<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="14" y="6" width="20" height="36" rx="4"/><path d="M20 38h8"/><circle cx="24" cy="34" r="1.5" fill="currentColor" stroke="none"/></svg>`;
    }
    return `<svg viewBox="0 0 56 32" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 22h48M8 22l4-12h28l4 12"/><path d="M14 10l3-8h18l3 8"/><rect x="16" y="12" width="8" height="6" rx="1"/><rect x="32" y="12" width="8" height="6" rx="1"/><circle cx="12" cy="25" r="3"/><circle cx="44" cy="25" r="3"/></svg>`;
}

function renderImagemModalidade(cenario, classe = 'comp-card-image') {
    const tipo = String(cenario?.tipo || cenario?.tipo_modalidade || '').toUpperCase();
    const src = imagemModalidade(cenario);
    const alt = cenario?.tipo === 'ASSINATURA' ? 'Carro por assinatura' :
        cenario?.tipo === 'TRANSPORTE_APP' ? 'Transporte por app ou taxi' : 'Veiculo proprio';
    return `
        <img class="${classe}" src="${escapeAttr(src)}" alt="${escapeAttr(alt)}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">
        <div class="mobility-image-fallback" aria-hidden="true" style="display:none;">${fallbackImagemModalidade(tipo)}</div>
    `;
}

function extrairListaApi(payload) {
    if (Array.isArray(payload)) return payload;
    if (payload?.success === true) return payload.data || [];
    return Array.isArray(payload?.data) ? payload.data : [];
}

document.addEventListener('DOMContentLoaded', async () => {
    preencherMeses();
    carregarCaminhosAtivosLocal();
    await carregarCategorias();
    await carregarCaminhosApp();
    await carregarAssinaturas();
    await carregarVeiculos();
    await carregarCenarioAtivo();
    await renderizarComparacao();
    toggleDataInicio();
});

function preencherMeses() {
    const selects = ['ipva_mes', 'seguro_mes', 'licenciamento_mes'];
    selects.forEach(id => {
        const sel = document.getElementById(id);
        if (!sel) return;
        sel.innerHTML = '<option value="">Mês</option>' + Array.from({ length: 12 }, (_, i) => {
            const n = i + 1;
            return `<option value="${n}">${String(n).padStart(2, '0')}</option>`;
        }).join('');
    });
}

async function carregarCategorias() {
    try {
        const resp = await fetch(API_CATEGORIAS);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao carregar categorias');
        categorias = data.data || [];

        // Mantido para outras telas futuras; o formulário de veículo não expõe categorias.
    } catch (e) {
        console.error(e);
        alert('Erro ao carregar categorias: ' + e.message);
    }
}


function renderEmptyCard() {
    return `
        <div class="card card-empty">
            <div class="card-header"></div>
            <div class="card-body"></div>
            <div class="card-cost"></div>
            <div class="row-actions card-actions"></div>
        </div>
    `;
}

async function renderCaminhosGrid() {
    const container = document.getElementById('caminhos-lista');
    if (!container) return;

    if (caminhosVeiculos === null || caminhosApps === null || caminhosAssinaturas === null) {
        container.innerHTML = `<p class="loading">Carregando caminhos...</p>`;
        atualizarResumoMobilidadeAtiva();
        return;
    }

    const listaVeiculos = caminhosVeiculos || [];
    const listaApps = caminhosApps || [];
    const listaAssinaturas = caminhosAssinaturas || [];

    if (!listaVeiculos.length && !listaApps.length && !listaAssinaturas.length) {
        container.innerHTML = `
            <div class="empty-state">
                <h3>Nenhum caminho cadastrado</h3>
                <p class="small-note">Crie um veÃ­culo ou um caminho de app para comparar cenÃ¡rios.</p>
            </div>
        `;
        atualizarResumoMobilidadeAtiva();
        return;
    }

    const cards = [];
    listaVeiculos.forEach(v => cards.push(renderVeiculoCard(v)));
    listaAssinaturas.forEach(a => cards.push(renderAssinaturaCard(a)));
    listaApps.forEach(c => cards.push(renderAppCard(c)));

    const total = cards.length;
    const resto = total % 4;
    const vazios = resto === 0 ? 0 : (4 - resto);
    for (let i = 0; i < vazios; i++) {
        cards.push(renderEmptyCard());
    }

    container.innerHTML = cards.join('');
    atualizarResumoMobilidadeAtiva();

    await atualizarCustosMensais(listaVeiculos.map(v => v.id));
}

function carregarCaminhosAtivosLocal() {
    try {
        const raw = localStorage.getItem(STORAGE_MOBILIDADE_ATIVA);
        if (!raw) return;
        const obj = JSON.parse(raw);
        if (obj && Array.isArray(obj.VEICULO)) {
            mobilidadeAtiva.VEICULO = new Set(obj.VEICULO.map(Number).filter(Number.isFinite));
        }
        if (obj && Array.isArray(obj.TRANSPORTE_APP)) {
            mobilidadeAtiva.TRANSPORTE_APP = new Set(obj.TRANSPORTE_APP.map(Number).filter(Number.isFinite));
        }
    } catch (e) {
        console.warn('Falha ao carregar caminhos ativos:', e);
    }
}

function salvarCaminhosAtivosLocal() {
    const payload = {
        VEICULO: Array.from(mobilidadeAtiva.VEICULO || []),
        TRANSPORTE_APP: Array.from(mobilidadeAtiva.TRANSPORTE_APP || []),
    };
    try {
        localStorage.setItem(STORAGE_MOBILIDADE_ATIVA, JSON.stringify(payload));
    } catch (e) {
        console.warn('Falha ao salvar caminhos ativos:', e);
    }
}

function isCaminhoAtivo(tipo, id) {
    const set = mobilidadeAtiva?.[tipo];
    return !!(set && set.has(Number(id)));
}

function toggleCaminhoAtivo(tipo, id, ativo) {
    const set = mobilidadeAtiva?.[tipo];
    if (!set) return;
    const nid = Number(id);
    if (!Number.isFinite(nid)) return;
    if (ativo) set.add(nid);
    else set.delete(nid);
    salvarCaminhosAtivosLocal();
    atualizarResumoMobilidadeAtiva();
}

function atualizarResumoMobilidadeAtiva() {
    const el = document.getElementById('mobilidade-ativa-resumo');
    if (!el) return;

    const ativosVeiculo = Array.from(mobilidadeAtiva?.VEICULO || []);
    const ativosApp = Array.from(mobilidadeAtiva?.TRANSPORTE_APP || []);

    let total = 0;
    ativosVeiculo.forEach((id) => {
        total += Number(custoMensalConsolidado?.VEICULO?.[id] || 0);
    });
    ativosApp.forEach((id) => {
        total += Number(custoMensalConsolidado?.TRANSPORTE_APP?.[id] || 0);
    });

    const n = ativosVeiculo.length + ativosApp.length;
    const fmt = Number(total || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

    const valorEl = el.querySelector('.mobilidade-resumo-valor');
    const subEl = el.querySelector('.mobilidade-resumo-sub');
    if (valorEl) valorEl.textContent = `${fmt} / mês`;
    if (subEl) subEl.textContent = `(${n} ${n === 1 ? 'caminho ativo' : 'caminhos ativos'})`;
}

async function carregarVeiculos() {
    try {
        const resp = await fetch(API_VEICULOS);
        const data = await resp.json();

        if (!data.success) {
            console.error('Erro ao carregar veículos:', data.error);
            caminhosVeiculos = [];
            await renderCaminhosGrid();
            return;
        }

        const itens = data.data || [];
        caminhosVeiculos = itens;

        const ids = new Set(itens.map(v => Number(v.id)).filter(Number.isFinite));
        Array.from(mobilidadeAtiva.VEICULO || []).forEach((id) => {
            if (!ids.has(Number(id))) mobilidadeAtiva.VEICULO.delete(Number(id));
        });

        // reset cache (será preenchido ao carregar projeções para custo mensal)
        custoMensalConsolidado.VEICULO = {};

        await atualizarCustosMensais(Array.from(ids));
        await renderCaminhosGrid();
        if (abaAtiva === 'comparacao') await renderizarComparacao();
        if (abaAtiva === 'configuracao') await renderizarConfiguracao();
    } catch (e) {
        console.error(e);
        caminhosVeiculos = [];
        await renderCaminhosGrid();
    }
}

async function carregarCaminhosApp() {
    try {
        const resp = await fetch(API_MOBILIDADE_APP);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao carregar caminhos');

        const itens = data.data || [];
        caminhosApps = itens;

        const ids = new Set(itens.map(c => Number(c.id)).filter(Number.isFinite));
        // limpar ativos que nÃ£o existem mais
        Array.from(mobilidadeAtiva.TRANSPORTE_APP || []).forEach((id) => {
            if (!ids.has(Number(id))) mobilidadeAtiva.TRANSPORTE_APP.delete(Number(id));
        });

        // cache de custo mensal consolidado (j? vem da API)
        custoMensalConsolidado.TRANSPORTE_APP = {};
        itens.forEach((c) => {
            const cid = Number(c.id);
            if (!Number.isFinite(cid)) return;
            custoMensalConsolidado.TRANSPORTE_APP[cid] = Number(c.valor_mensal || 0);
        });

        await renderCaminhosGrid();
        if (abaAtiva === 'comparacao') await renderizarComparacao();
        if (abaAtiva === 'configuracao') await renderizarConfiguracao();
    } catch (e) {
        console.error(e);
        caminhosApps = [];
        await renderCaminhosGrid();
    }
}

async function carregarAssinaturas() {
    try {
        const resp = await fetch(API_ASSINATURAS);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao carregar assinaturas');
        caminhosAssinaturas = data.data || [];
        await renderCaminhosGrid();
        if (abaAtiva === 'comparacao') await renderizarComparacao();
        if (abaAtiva === 'configuracao') await renderizarConfiguracao();
    } catch (e) {
        console.error(e);
        caminhosAssinaturas = [];
        await renderCaminhosGrid();
    }
}

function renderAppCard(c) {
    const projId = `app-projecoes-${c.id}`;
    const valor = formatarMoeda(c.valor_mensal || 0);
    const ativo = isCaminhoAtivo('TRANSPORTE_APP', c.id);

    return `
        <div class="card">
            <div class="card-header">
                <div class="card-title">${escapeHtml(c.nome || 'Transporte por App')}</div>
                <div class="card-right">
                    <label class="caminho-toggle">
                        <input type="checkbox" ${ativo ? 'checked' : ''} onchange="toggleCaminhoAtivo('TRANSPORTE_APP', ${c.id}, this.checked)">
                        <span>Ativo</span>
                    </label>
                    <span class="card-badge">APP</span>
                </div>
            </div>

            <div class="card-body">
                <div class="veiculo-sub">${Number(c.km_mensal_estimado || 0).toLocaleString('pt-BR')} km/mês · ${formatarMoeda(c.preco_medio_por_km || 0)} / km</div>
            </div>

            <div class="card-cost">
                <div class="custo-label">Custo mensal estimado</div>
                <div class="custo-valor">${valor} / mês</div>
                <div class="custo-hint">Leitura projetiva (não cria despesas reais).</div>
            </div>

            <div class="row-actions card-actions">
                <button class="row-action-button" onclick="abrirModalAppEditar(${c.id})" title="Editar" aria-label="Editar">${veiculosIcon('edit')}</button>
                <button class="row-action-button" onclick="toggleProjecoesApp(${c.id})" title="Projecoes" aria-label="Projecoes">${veiculosIcon('eye')}</button>
                <button class="row-action-button danger" onclick="removerCaminhoApp(${c.id}, '${escapeAttr(c.nome || 'Transporte por App')}')" title="Excluir" aria-label="Excluir">${veiculosIcon('trash')}</button>
            </div>

            <div class="projecoes-wrap" id="${projId}" style="display:none;">
                <div class="projecoes-header">
                    <strong>Despesas previstas</strong>
                    <span class="small-note">Não são lançamentos reais.</span>
                </div>
                <div class="projecoes-body">
                    <p class="loading">Carregando projeções...</p>
                </div>
            </div>
        </div>
    `;
}

function renderAssinaturaCard(a) {
    const valor = formatarMoeda(a.valor_mensal || 0);
    const ativo = isCenarioAtivo('ASSINATURA', a.id);

    return `
        <div class="card">
            <div class="card-header">
                <div class="card-title">${escapeHtml(a.nome || 'Carro por Assinatura')}</div>
                <div class="card-right">
                    <span class="card-badge ${a.status === 'ATIVO' ? 'status-ativo' : 'status-simulado'}">${escapeHtml(a.status || 'ATIVO')}</span>
                    ${ativo ? '<span class="card-badge status-ativo">Selecionada</span>' : ''}
                </div>
            </div>

            <div class="card-body">
                <div class="veiculo-sub">Contrato mensal de mobilidade</div>
                <div class="veiculo-sub">Manutenção, seguro e depreciação normalmente diluídos no contrato.</div>
            </div>

            <div class="card-cost">
                <div class="custo-label">Assinatura mensal</div>
                <div class="custo-valor">${valor} / mês</div>
                <div class="custo-hint">Recorrência mensal ao ativar.</div>
            </div>

            <div class="row-actions card-actions">
                <button class="row-action-button" onclick="abrirModalAssinaturaEditar(${a.id})" title="Editar" aria-label="Editar">${veiculosIcon('edit')}</button>
                <button class="row-action-button success" onclick="abrirModalAtivacaoMobilidade('ASSINATURA', ${a.id})" title="Selecionar" aria-label="Selecionar">${veiculosIcon('check')}</button>
            </div>
        </div>
    `;
}

function abrirModalAppNovo() {
    appEditando = null;
    appPerfis = [];
    document.getElementById('modal-app-titulo').textContent = 'Transporte por App';
    document.getElementById('app-id').value = '';
    document.getElementById('app-nome').value = 'Transporte por App';
    document.getElementById('app-km-mensal').value = '';
    document.getElementById('app-preco-km').value = '';
    document.getElementById('app-corridas-mes').value = '';
    document.getElementById('app-km-corrida').value = '';
    renderPerfisApp();
    document.getElementById('modal-app').style.display = 'block';
}

function fecharModalApp() {
    document.getElementById('modal-app').style.display = 'none';
    appEditando = null;
}

function preencherCategoriasAssinatura() {
    const sel = document.getElementById('assinatura-categoria-id');
    if (!sel) return;
    sel.innerHTML = '<option value="">— Padrão (Mobilidade) —</option>' +
        (categorias || []).map(c => `<option value="${c.id}">${escapeHtml(c.nome)}</option>`).join('');
}

function abrirModalAssinaturaNovo() {
    assinaturaEditando = null;
    preencherCategoriasAssinatura();
    document.getElementById('modal-assinatura-titulo').textContent = 'Carro por Assinatura';
    document.getElementById('assinatura-id').value = '';
    document.getElementById('assinatura-nome').value = '';
    document.getElementById('assinatura-valor-mensal').value = '';
    document.getElementById('assinatura-status').value = 'ATIVO';
    document.getElementById('assinatura-categoria-id').value = '';
    document.getElementById('modal-assinatura').style.display = 'block';
}

function abrirModalAssinaturaEditar(id) {
    const ass = (caminhosAssinaturas || []).find(a => Number(a.id) === Number(id));
    if (!ass) {
        alert('Assinatura não encontrada.');
        return;
    }
    assinaturaEditando = id;
    preencherCategoriasAssinatura();
    document.getElementById('modal-assinatura-titulo').textContent = 'Carro por Assinatura (editar)';
    document.getElementById('assinatura-id').value = id;
    document.getElementById('assinatura-nome').value = ass.nome || '';
    document.getElementById('assinatura-valor-mensal').value = ass.valor_mensal ?? '';
    document.getElementById('assinatura-status').value = ass.status || 'ATIVO';
    document.getElementById('assinatura-categoria-id').value = ass.categoria_id || '';
    document.getElementById('modal-assinatura').style.display = 'block';
}

function fecharModalAssinatura() {
    document.getElementById('modal-assinatura').style.display = 'none';
    assinaturaEditando = null;
}

async function salvarAssinatura(event) {
    event.preventDefault();
    const id = document.getElementById('assinatura-id')?.value;
    const payload = {
        nome: document.getElementById('assinatura-nome')?.value,
        valor_mensal: document.getElementById('assinatura-valor-mensal')?.value,
        status: document.getElementById('assinatura-status')?.value || 'ATIVO',
        categoria_id: document.getElementById('assinatura-categoria-id')?.value || null,
    };

    try {
        const resp = await fetch(id ? `${API_ASSINATURAS}/${id}` : API_ASSINATURAS, {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao salvar assinatura');
        fecharModalAssinatura();
        await carregarAssinaturas();
    } catch (e) {
        console.error(e);
        alert('Erro ao salvar assinatura: ' + e.message);
    }
}

function adicionarPerfilApp(prefill = null) {
    appPerfis.push({
        nome: prefill?.nome || '',
        km_mensal: prefill?.km_mensal ?? '',
        preco_medio_por_km: prefill?.preco_medio_por_km ?? '',
    });
    renderPerfisApp();
}

function removerPerfilApp(idx) {
    appPerfis = (appPerfis || []).filter((_, i) => i !== idx);
    renderPerfisApp();
}

function renderPerfisApp() {
    const wrap = document.getElementById('app-perfis');
    if (!wrap) return;
    if (!appPerfis || appPerfis.length === 0) {
        wrap.innerHTML = `<div class="empty-state"><p class="small-note">Nenhum perfil configurado.</p></div>`;
        return;
    }

    wrap.innerHTML = appPerfis.map((p, idx) => `
        <div class="manut-regra-item app-perfil-row" data-idx="${idx}">
            <div class="linha" style="flex: 1 1 auto; min-width:0;">
                <div class="inline" style="flex-wrap:wrap; gap:10px;">
                    <div style="flex: 1 1 200px; min-width:160px;">
                        <label class="small-note">Nome</label>
                        <input type="text" class="app-perfil-nome" value="${escapeAttr(p.nome)}" placeholder="Ex: Trabalho">
                    </div>
                    <div style="flex: 0 0 160px;">
                        <label class="small-note">Km/mês</label>
                        <input type="number" step="0.01" class="app-perfil-km" value="${escapeAttr(p.km_mensal)}" placeholder="Ex: 120">
                    </div>
                    <div style="flex: 0 0 180px;">
                        <label class="small-note">R$/km</label>
                        <input type="number" step="0.01" class="app-perfil-preco" value="${escapeAttr(p.preco_medio_por_km)}" placeholder="Ex: 3.10">
                    </div>
                </div>
            </div>
            <div class="row-actions">
                <button type="button" class="row-action-button danger" onclick="removerPerfilApp(${idx})" title="Remover" aria-label="Remover">${veiculosIcon('trash')}</button>
            </div>
        </div>
    `).join('');
}

function coletarPerfisAppDoDOM() {
    const wrap = document.getElementById('app-perfis');
    if (!wrap) return [];
    const rows = Array.from(wrap.querySelectorAll('.app-perfil-row'));
    return rows.map(row => {
        const nome = row.querySelector('.app-perfil-nome')?.value?.trim() || 'Perfil';
        const km = row.querySelector('.app-perfil-km')?.value;
        const preco = row.querySelector('.app-perfil-preco')?.value;
        return { nome, km_mensal: km, preco_medio_por_km: preco };
    });
}

function _toNumberOrNull(value) {
    if (value === null || value === undefined) return null;
    const s = String(value).trim();
    if (!s) return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
}

function _validarESanitizarPerfisApp(perfisRaw, kmTotal) {
    const perfis = (perfisRaw || []).map(p => ({
        nome: String(p?.nome || '').trim() || 'Perfil',
        km_mensal: _toNumberOrNull(p?.km_mensal),
        preco_medio_por_km: _toNumberOrNull(p?.preco_medio_por_km),
    }));

    // Remover linhas vazias/incompletas (perfil é opcional; km é o critério)
    const perfisComKm = perfis.filter(p => p.km_mensal !== null);

    for (const p of perfisComKm) {
        if (p.km_mensal <= 0) {
            throw new Error('Km/mês do perfil deve ser > 0.');
        }
        if (p.preco_medio_por_km !== null && p.preco_medio_por_km <= 0) {
            throw new Error('R$/km do perfil deve ser > 0 (quando informado).');
        }
    }

    const somaKm = perfisComKm.reduce((acc, p) => acc + (p.km_mensal || 0), 0);
    if (Number.isFinite(kmTotal) && somaKm > kmTotal + 1e-9) {
        throw new Error('A soma de km/mês dos perfis deve ser menor ou igual ao km mensal total.');
    }

    return perfisComKm.map(p => ({
        nome: p.nome,
        km_mensal: p.km_mensal,
        preco_medio_por_km: p.preco_medio_por_km,
    }));
}

async function abrirModalAppEditar(id) {
    try {
        const resp = await fetch(`${API_MOBILIDADE_APP}/${id}`);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao carregar caminho');

        const c = data.data || {};
        appEditando = id;
        document.getElementById('modal-app-titulo').textContent = 'Transporte por App (editar)';
        document.getElementById('app-id').value = id;
        document.getElementById('app-nome').value = c.nome || 'Transporte por App';
        document.getElementById('app-km-mensal').value = c.km_mensal_estimado ?? '';
        document.getElementById('app-preco-km').value = c.preco_medio_por_km ?? '';
        document.getElementById('app-corridas-mes').value = c.corridas_mes ?? '';
        document.getElementById('app-km-corrida').value = c.km_medio_por_corrida ?? '';

        appPerfis = Array.isArray(c.perfis) ? c.perfis.map(p => ({
            nome: p.nome || '',
            km_mensal: p.km_mensal ?? '',
            preco_medio_por_km: p.preco_medio_por_km ?? '',
        })) : [];
        renderPerfisApp();

        document.getElementById('modal-app').style.display = 'block';
    } catch (e) {
        console.error(e);
        alert('Erro: ' + e.message);
    }
}

async function salvarCaminhoApp(event) {
    event.preventDefault();
    const id = document.getElementById('app-id').value;

    const kmTotal = _toNumberOrNull(document.getElementById('app-km-mensal').value);
    const precoBase = _toNumberOrNull(document.getElementById('app-preco-km').value);
    if (kmTotal === null || kmTotal <= 0) {
        alert('Informe Km mensal estimado (> 0).');
        return;
    }
    if (precoBase === null || precoBase <= 0) {
        alert('Informe Preço médio por km (> 0).');
        return;
    }

    let perfis = [];
    try {
        perfis = _validarESanitizarPerfisApp(coletarPerfisAppDoDOM(), kmTotal);
    } catch (e) {
        alert(e.message || 'Perfis inválidos.');
        return;
    }

    const payload = {
        nome: document.getElementById('app-nome').value,
        km_mensal_estimado: kmTotal,
        preco_medio_por_km: precoBase,
        perfis,
        corridas_mes: document.getElementById('app-corridas-mes').value,
        km_medio_por_corrida: document.getElementById('app-km-corrida').value,
        meses_futuros: 12,
    };

    try {
        const url = id ? `${API_MOBILIDADE_APP}/${id}` : API_MOBILIDADE_APP;
        const method = id ? 'PUT' : 'POST';
        const resp = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao salvar');
        alert(data.message || 'OK');
        fecharModalApp();
        await carregarCaminhosApp();
    } catch (e) {
        console.error(e);
        alert('Erro: ' + e.message);
    }
}

async function removerCaminhoApp(id = null, nome = null) {
    const caminhoId = id || document.getElementById('app-id')?.value;
    if (!caminhoId) return;
    const nm = nome || document.getElementById('app-nome')?.value || `#${caminhoId}`;
    if (!confirm(`Excluir "${nm}"?\n\nIsto remove apenas as despesas previstas deste caminho.`)) return;
    try {
        const resp = await fetch(`${API_MOBILIDADE_APP}/${caminhoId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao remover');
        alert(data.message || 'Removido');
        fecharModalApp();
        await carregarCaminhosApp();
    } catch (e) {
        console.error(e);
        alert('Erro: ' + e.message);
    }
}

async function toggleProjecoesApp(id) {
    const wrap = document.getElementById(`app-projecoes-${id}`);
    if (!wrap) return;

    const mostrando = wrap.style.display !== 'none';
    wrap.style.display = mostrando ? 'none' : 'block';
    if (mostrando) return;

    const body = wrap.querySelector('.projecoes-body');
    body.innerHTML = '<p class="loading">Carregando projeções...</p>';

    try {
        const resp = await fetch(`${API_MOBILIDADE_APP}/${id}/projecoes?meses=24`);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao carregar projeções');

        const proj = data.data || [];
        if (!proj.length) {
            body.innerHTML = '<p class="empty-state">Nenhuma projeção configurada para o período.</p>';
            return;
        }

        projecoesIndex = {};
        proj.forEach(p => {
            projecoesIndex[p.id] = { tipo_evento: _normalizarTipoEvento(p) || null };
        });

        const grupos = _consolidarProjecoes(proj, 12, new Set());

        const md0 = proj[0]?.metadata?.caminho || null;
        const perfis0 = Array.isArray(md0?.perfis) ? md0.perfis : [];
        const resumoCalculo = md0 ? `
            <div class="uso-resumo">
                <div><strong>Km mensal:</strong> ${Number(md0.km_mensal_estimado || 0).toLocaleString('pt-BR')} km/mês</div>
                <div><strong>Preço médio:</strong> ${formatarMoeda(md0.preco_medio_por_km || 0)} / km</div>
                ${perfis0.length ? `<div class="small-note">Perfis: ${perfis0.map(p => `${escapeHtml(p.nome)} (${Number(p.km_mensal || 0).toLocaleString('pt-BR')} km/mês)`).join(' • ')}</div>` : ''}
            </div>
        ` : '';

        const gruposHtml = (grupos || []).map(g => {
            const rowsGrupo = (g.itens || []).map(p => {
                const mes = formatarMesAno(p.data_atual_prevista || p.data_prevista);
                const categoria = p.categoria?.nome || `Categoria #${p.categoria_id}`;
                const tipo = _rotuloDetalheTipo(p);
                const valor = formatarMoeda(p.valor_previsto);
                const isPrevista = String(p.status || '').toUpperCase() === 'PREVISTA';
                const actions = isPrevista ? `
                    <div class="row-actions">
                        <button class="row-action-button success" onclick="confirmarPrevista(${p.id})" title="Confirmar" aria-label="Confirmar">${veiculosIcon('check')}</button>
                        <button class="row-action-button" onclick="abrirModalAdiar(${p.id}, '${escapeAttr(p.data_atual_prevista || p.data_prevista)}')" title="Adiar" aria-label="Adiar">${veiculosIcon('clock')}</button>
                        <button class="row-action-button danger" onclick="ignorarPrevista(${p.id})" title="Ignorar" aria-label="Ignorar">${veiculosIcon('remove')}</button>
                    </div>
                ` : `<span class="small-note">—</span>`;
                return `<tr>
                    <td>${mes}</td>
                    <td>${escapeHtml(tipo)}</td>
                    <td>${escapeHtml(categoria)}</td>
                    <td class="right">${valor}</td>
                    <td><span class="badge-prevista">${escapeHtml(p.status)}</span></td>
                    <td>${actions}</td>
                </tr>`;
            }).join('');

            return `
                <details class="prev-consolidada">
                    <summary>
                        <div class="prev-sum-left">
                            <div class="prev-titulo">${escapeHtml(g.label)}</div>
                            <div class="prev-info">${escapeHtml(g.infoResumo)}</div>
                        </div>
                        <div class="prev-sum-right">
                            <div class="prev-valor">${escapeHtml(g.valorResumo)}</div>
                        </div>
                    </summary>
                    <div class="prev-detalhe">
                        <table class="table-projecoes">
                            <thead>
                                <tr>
                                    <th>Mês</th>
                                    <th>Tipo</th>
                                    <th>Categoria</th>
                                    <th class="right">Valor</th>
                                    <th>Status</th>
                                    <th>Ações</th>
                                </tr>
                            </thead>
                            <tbody>${rowsGrupo || ''}</tbody>
                        </table>
                    </div>
                </details>
            `;
        }).join('');

        body.innerHTML = `
            ${resumoCalculo}
            <div class="prev-consolidadas">
                <div class="small-note">Visão consolidada por tipo (leitura). Expanda para detalhes.</div>
                ${gruposHtml || ''}
            </div>
            <details class="prev-auditoria">
                <summary>Ver lista completa por mês (auditoria)</summary>
                <table class="table-projecoes">
                <thead>
                    <tr>
                        <th>Mês</th>
                        <th>Tipo</th>
                        <th>Categoria</th>
                        <th class="right">Valor</th>
                        <th>Status</th>
                        <th>Ações</th>
                    </tr>
                </thead>
                <tbody>${(proj || []).map(p => {
                    const mes = formatarMesAno(p.data_atual_prevista || p.data_prevista);
                    const categoria = p.categoria?.nome || `Categoria #${p.categoria_id}`;
                    const tipo = _rotuloDetalheTipo(p);
                    const valor = formatarMoeda(p.valor_previsto);
                    const isPrevista = String(p.status || '').toUpperCase() === 'PREVISTA';
                    const actions = isPrevista ? `
                        <div class="row-actions">
                            <button class="row-action-button success" onclick="confirmarPrevista(${p.id})" title="Confirmar" aria-label="Confirmar">${veiculosIcon('check')}</button>
                            <button class="row-action-button" onclick="abrirModalAdiar(${p.id}, '${escapeAttr(p.data_atual_prevista || p.data_prevista)}')" title="Adiar" aria-label="Adiar">${veiculosIcon('clock')}</button>
                            <button class="row-action-button danger" onclick="ignorarPrevista(${p.id})" title="Ignorar" aria-label="Ignorar">${veiculosIcon('remove')}</button>
                        </div>
                    ` : `<span class="small-note">—</span>`;
                    return `<tr>
                        <td>${mes}</td>
                        <td>${escapeHtml(tipo)}</td>
                        <td>${escapeHtml(categoria)}</td>
                        <td class="right">${valor}</td>
                        <td><span class="badge-prevista">${escapeHtml(p.status)}</span></td>
                        <td>${actions}</td>
                    </tr>`;
                }).join('')}</tbody>
                </table>
            </details>
        `;
    } catch (e) {
        console.error(e);
        body.innerHTML = `<p class="empty-state">Erro ao carregar projeções: ${escapeHtml(e.message)}</p>`;
    }
}

function renderVeiculoCard(v) {
    const statusClass = v.status === 'ATIVO' ? 'status-ativo' : 'status-simulado';
    const statusLabel = v.status;
    const inicio = v.data_inicio ? `In&iacute;cio: ${formatarData(v.data_inicio)}` : 'In&iacute;cio: (n&atilde;o definido)';
    const projId = `projecoes-${v.id}`;
    const kmTotal = v.uso_estimado?.km_estimado_acumulado ?? 0;
    const ativo = isCaminhoAtivo('VEICULO', v.id);

    const acoesDetalhe = `
        <div class="projecoes-actions">
            <button class="row-action-button" onclick="abrirModalFinanciamento(${v.id})" title="Financiamento" aria-label="Financiamento">${veiculosIcon('file')}</button>
            <button class="row-action-button" onclick="abrirModalManutencaoKm(${v.id})" title="Manutencao por km" aria-label="Manutencao por km">${veiculosIcon('clock')}</button>
            ${v.status === 'SIMULADO'
                ? `<button class="row-action-button success" onclick="converterVeiculo(${v.id})" title="Converter para ativo" aria-label="Converter para ativo">${veiculosIcon('check')}</button>`
                : ''}
        </div>
    `;

    return `
        <div class="card">
            <div class="card-header">
                <div class="card-title">${escapeHtml(v.nome)}</div>
                <div class="card-right">
                    <label class="caminho-toggle">
                        <input type="checkbox" ${ativo ? 'checked' : ''} onchange="toggleCaminhoAtivo('VEICULO', ${v.id}, this.checked)">
                        <span>Ativo</span>
                    </label>
                    <span class="card-badge ${statusClass}">${escapeHtml(statusLabel)}</span>
                </div>
            </div>

            <div class="card-body">
                <div class="veiculo-sub">${escapeHtml(v.tipo)} - ${escapeHtml(v.combustivel)} - Autonomia: ${v.autonomia_km_l} km/L</div>
                <div class="veiculo-sub">${inicio}</div>
                <div class="veiculo-sub">Km estimado total: ${Number(kmTotal).toLocaleString('pt-BR')} <span class="small-note">(estimativa)</span></div>
            </div>

            <div class="card-cost" id="custo-mensal-${v.id}">
                <div class="custo-label">Custo mensal estimado</div>
                <div class="custo-valor">?</div>
                <div class="custo-hint">Leitura projetiva (n&atilde;o cria despesas reais).</div>
            </div>

            <div class="row-actions card-actions">
                <button class="row-action-button" onclick="abrirModalEditar(${v.id})" title="Editar" aria-label="Editar">${veiculosIcon('edit')}</button>
                <button class="row-action-button" onclick="toggleProjecoes(${v.id})" title="Projecoes" aria-label="Projecoes">${veiculosIcon('eye')}</button>
                <button class="row-action-button danger" onclick="deletarVeiculo(${v.id}, '${escapeAttr(v.nome)}')" title="Excluir" aria-label="Excluir">${veiculosIcon('trash')}</button>
            </div>

            <div class="projecoes-wrap" id="${projId}" style="display:none;">
                <div class="projecoes-header">
                    <strong>Despesas previstas</strong>
                    <span class="small-note">N&atilde;o s&atilde;o lan&ccedil;amentos reais.</span>
                </div>
                ${acoesDetalhe}
                <div class="projecoes-body">
                    <p class="loading">Carregando proje&ccedil;&otilde;es...</p>
                </div>
            </div>
        </div>
    `;
}

function _primeiroDiaMes(d) {
    return new Date(d.getFullYear(), d.getMonth(), 1);
}

function _addMeses(d, meses) {
    return new Date(d.getFullYear(), d.getMonth() + meses, 1);
}

function _parseIsoDate(iso) {
    if (!iso) return null;
    const parts = String(iso).split('-');
    if (parts.length < 2) return null;
    const y = Number(parts[0]);
    const m = Number(parts[1]) - 1;
    if (!Number.isFinite(y) || !Number.isFinite(m)) return null;
    return new Date(y, m, 1);
}

function calcularCustoMensalEstimado(despesas, mesesJanela = 12, tiposExcluir = new Set()) {
    const inicio = _primeiroDiaMes(new Date());
    const fim = _addMeses(inicio, mesesJanela);

    const statusValidos = new Set(['PREVISTA', 'CONFIRMADA', 'ADIADA']);
    const tiposMensais = new Set(['COMBUSTIVEL', 'PARCELA_FINANCIAMENTO']);

    const totalMensalPorMes = new Array(mesesJanela).fill(0);
    let somaNaoMensaisNaJanela = 0;

    (despesas || []).forEach(d => {
        if (!statusValidos.has(String(d.status || '').toUpperCase())) return;
        const tipo = String(d.tipo_evento || d.metadata?.tipo_evento || '').toUpperCase();
        if (tiposExcluir && tiposExcluir.has(tipo)) return;
        const iso = d.data_atual_prevista || d.data_prevista;
        const dt = _parseIsoDate(iso);
        if (!dt) return;
        if (dt < inicio || dt >= fim) return;

        const idxMes = (dt.getFullYear() - inicio.getFullYear()) * 12 + (dt.getMonth() - inicio.getMonth());
        if (idxMes < 0 || idxMes >= mesesJanela) return;

        const valor = Number(d.valor_previsto || 0);
        if (!Number.isFinite(valor)) return;

        if (tiposMensais.has(tipo)) {
            totalMensalPorMes[idxMes] += valor;
        } else {
            somaNaoMensaisNaJanela += valor;
        }
    });

    const somaMensal = totalMensalPorMes.reduce((a, b) => a + b, 0);
    const mediaMensal = mesesJanela ? (somaMensal / mesesJanela) : 0;
    const anualizado = somaNaoMensaisNaJanela / 12;
    return mediaMensal + anualizado;
}

function _normalizarTipoEvento(p) {
    return String(p?.tipo_evento || p?.metadata?.tipo_evento || '').trim().toUpperCase();
}

function _grupoPrevisaoPorTipoEvento(tipoEvento) {
    const tipo = String(tipoEvento || '').toUpperCase();
    if (!tipo) return 'OUTROS';
    if (tipo === 'COMBUSTIVEL') return 'COMBUSTIVEL';
    if (tipo === 'IPVA') return 'IPVA';
    if (tipo === 'SEGURO') return 'SEGURO';
    if (tipo === 'LICENCIAMENTO') return 'LICENCIAMENTO';
    if (tipo === 'PARCELA_FINANCIAMENTO' || tipo === 'IOF_FINANCIAMENTO') return 'FINANCIAMENTO';
    if (tipo === 'TRANSPORTE_APP') return 'APP';
    return 'OUTROS';
}

function _rotuloGrupoPrevisao(grupo) {
    switch (grupo) {
        case 'COMBUSTIVEL': return 'Combustível';
        case 'FINANCIAMENTO': return 'Financiamento';
        case 'APP': return 'Transporte por App';
        case 'MANUTENCAO': return 'Manutenção';
        case 'SEGURO': return 'Seguro';
        case 'IPVA': return 'IPVA';
        case 'LICENCIAMENTO': return 'Licenciamento';
        default: return 'Outros';
    }
}

function _ehEventoManutencao(p, tiposRegras) {
    const tipo = _normalizarTipoEvento(p);
    if (!tipo) return false;
    if (['COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO', 'PARCELA_FINANCIAMENTO', 'IOF_FINANCIAMENTO'].includes(tipo)) {
        return false;
    }

    if (tiposRegras && tiposRegras.size && tiposRegras.has(tipo)) {
        return true;
    }

    const md = p?.metadata || {};
    if (md?.ciclo_id) return true;
    if (md?.intervalo_km) return true;
    return false;
}

function _grupoPrevisaoParaItem(p, tiposRegras) {
    const tipo = _normalizarTipoEvento(p);
    const grupoBase = _grupoPrevisaoPorTipoEvento(tipo);
    if (grupoBase !== 'OUTROS') return grupoBase;
    if (_ehEventoManutencao(p, tiposRegras)) return 'MANUTENCAO';
    return 'OUTROS';
}

function _ordemGrupoPrevisao(grupo) {
    switch (grupo) {
        case 'COMBUSTIVEL': return 10;
        case 'FINANCIAMENTO': return 20;
        case 'APP': return 25;
        case 'MANUTENCAO': return 30;
        case 'SEGURO': return 40;
        case 'IPVA': return 50;
        case 'LICENCIAMENTO': return 60;
        default: return 99;
    }
}

function _resumoStatus(itens) {
    const acc = { PREVISTA: 0, CONFIRMADA: 0, ADIADA: 0, IGNORADA: 0 };
    (itens || []).forEach(i => {
        const st = String(i?.status || '').toUpperCase();
        if (acc[st] !== undefined) acc[st] += 1;
    });
    const parts = [];
    if (acc.PREVISTA) parts.push(`${acc.PREVISTA} prevista(s)`);
    if (acc.ADIADA) parts.push(`${acc.ADIADA} adiada(s)`);
    if (acc.CONFIRMADA) parts.push(`${acc.CONFIRMADA} confirmada(s)`);
    if (acc.IGNORADA) parts.push(`${acc.IGNORADA} ignorada(s)`);
    return parts.join(' • ') || '—';
}

function _keyMes(iso) {
    const dt = _parseIsoDate(iso);
    if (!dt) return null;
    const m = String(dt.getMonth() + 1).padStart(2, '0');
    return `${dt.getFullYear()}-${m}`;
}

function _rotuloDetalheTipo(p) {
    const tipo = _normalizarTipoEvento(p);
    if (tipo === 'TRANSPORTE_APP') return 'Transporte por App';
    if (tipo === 'PARCELA_FINANCIAMENTO') {
        const n = p?.metadata?.numero_parcela;
        const total = p?.metadata?.total_parcelas;
        if (n && total) return `Parcela ${n}/${total}`;
        if (n) return `Parcela ${n}`;
        return 'Parcela';
    }
    if (tipo === 'IOF_FINANCIAMENTO') return 'IOF';

    const cicloId = p?.metadata?.ciclo_id;
    const ordem = p?.metadata?.ordem_no_ciclo;
    if (cicloId && ordem) return `${tipo} (ciclo ${cicloId} • #${ordem})`;
    if (cicloId) return `${tipo} (ciclo ${cicloId})`;
    return tipo;
}

function _consolidarProjecoes(projecoes, mesesResumo = 12, tiposRegras = new Set()) {
    const statusValidos = new Set(['PREVISTA', 'CONFIRMADA', 'ADIADA']);
    const inicio = _primeiroDiaMes(new Date());
    const fim = _addMeses(inicio, mesesResumo);

    const porGrupo = new Map();
    (projecoes || []).forEach(p => {
        const grupo = _grupoPrevisaoParaItem(p, tiposRegras);
        if (!porGrupo.has(grupo)) porGrupo.set(grupo, []);
        porGrupo.get(grupo).push(p);
    });

    const grupos = [];
    for (const [grupo, itens] of porGrupo.entries()) {
        const itensOrdenados = [...itens].sort((a, b) => {
            const da = _parseIsoDate(a?.data_atual_prevista || a?.data_prevista) || new Date(0, 0, 1);
            const db = _parseIsoDate(b?.data_atual_prevista || b?.data_prevista) || new Date(0, 0, 1);
            if (da.getTime() !== db.getTime()) return da - db;
            return Number(a?.id || 0) - Number(b?.id || 0);
        });

        const janela = itensOrdenados.filter(p => {
            const st = String(p?.status || '').toUpperCase();
            if (!statusValidos.has(st)) return false;
            const dt = _parseIsoDate(p?.data_atual_prevista || p?.data_prevista);
            if (!dt) return false;
            return dt >= inicio && dt < fim;
        });

        const mesesComOcorrencia = new Set();
        let totalJanela = 0;
        janela.forEach(p => {
            const v = Number(p?.valor_previsto || 0);
            if (Number.isFinite(v)) totalJanela += v;
            const k = _keyMes(p?.data_atual_prevista || p?.data_prevista);
            if (k) mesesComOcorrencia.add(k);
        });

        const mediaMes = mesesResumo ? (totalJanela / mesesResumo) : 0;
        const statusResumo = _resumoStatus(itensOrdenados);

        let valorResumo = '—';
        let infoResumo = statusResumo;

        if (grupo === 'COMBUSTIVEL') {
            valorResumo = `${formatarMoeda(mediaMes)} / mês`;
            const rec = mesesComOcorrencia.size >= Math.max(1, mesesResumo - 1)
                ? 'recorrência: mensal'
                : `ocorrências: ${mesesComOcorrencia.size}/${mesesResumo}m`;
            infoResumo = `${rec} • ${statusResumo}`;
        } else if (grupo === 'APP') {
            valorResumo = `${formatarMoeda(mediaMes)} / mês`;
            const caminho = itensOrdenados?.[0]?.metadata?.caminho || null;
            const km = caminho ? Number(caminho.km_mensal_estimado || 0) : null;
            const preco = caminho ? Number(caminho.preco_medio_por_km || 0) : null;
            const base = (km !== null && preco !== null)
                ? `${Number(km).toLocaleString('pt-BR')} km/mês • ${formatarMoeda(preco)} / km`
                : 'recorrência: mensal';
            infoResumo = `${base} • ${statusResumo}`;
        } else if (grupo === 'FINANCIAMENTO') {
            const parcelas = janela.filter(p => _normalizarTipoEvento(p) === 'PARCELA_FINANCIAMENTO');
            let mediaParcela = 0;
            if (parcelas.length) {
                const soma = parcelas.reduce((acc, p) => acc + Number(p?.valor_previsto || 0), 0);
                mediaParcela = soma / parcelas.length;
            }
            valorResumo = `${formatarMoeda(mediaParcela)} / mês`;

            const proxima = itensOrdenados.find(p => {
                const st = String(p?.status || '').toUpperCase();
                if (!statusValidos.has(st)) return false;
                const dt = _parseIsoDate(p?.data_atual_prevista || p?.data_prevista);
                return dt && dt >= inicio;
            });
            const proxTipo = proxima ? _normalizarTipoEvento(proxima) : null;
            const n = proxima?.metadata?.numero_parcela;
            const total = proxima?.metadata?.total_parcelas;
            const proxTxt = (proxTipo === 'PARCELA_FINANCIAMENTO' && n && total) ? `próxima: ${n}/${total}` : null;
            const restTxt = (proxTipo === 'PARCELA_FINANCIAMENTO' && n && total)
                ? `restantes: ${Math.max(0, Number(total) - Number(n) + 1)}`
                : `parcelas na janela: ${parcelas.length}`;
            infoResumo = `${[proxTxt, restTxt, statusResumo].filter(Boolean).join(' • ')}`;
        } else if (grupo === 'IPVA' || grupo === 'SEGURO' || grupo === 'LICENCIAMENTO') {
            valorResumo = `${formatarMoeda(mediaMes)} / mês (diluído)`;
            const prox = itensOrdenados.find(p => {
                const st = String(p?.status || '').toUpperCase();
                if (!statusValidos.has(st)) return false;
                const dt = _parseIsoDate(p?.data_atual_prevista || p?.data_prevista);
                return dt && dt >= inicio;
            });
            const cobranca = prox ? `cobrança: ${formatarMesAno(prox.data_atual_prevista || prox.data_prevista)}` : 'cobrança: —';
            infoResumo = `${cobranca} • ${statusResumo}`;
        } else if (grupo === 'MANUTENCAO') {
            const prox = itensOrdenados.find(p => {
                const st = String(p?.status || '').toUpperCase();
                if (!statusValidos.has(st)) return false;
                const dt = _parseIsoDate(p?.data_atual_prevista || p?.data_prevista);
                return dt && dt >= inicio;
            });
            if (prox) {
                valorResumo = formatarMoeda(prox.valor_previsto);
                infoResumo = `próximo: ${_rotuloDetalheTipo(prox)} • ${formatarMesAno(prox.data_atual_prevista || prox.data_prevista)} • ${statusResumo}`;
            } else {
                valorResumo = '—';
                infoResumo = `nenhum evento previsto • ${statusResumo}`;
            }
        } else {
            valorResumo = `${formatarMoeda(mediaMes)} / mês (diluído)`;
            infoResumo = statusResumo;
        }

        grupos.push({
            grupo,
            label: _rotuloGrupoPrevisao(grupo),
            ordem: _ordemGrupoPrevisao(grupo),
            itens: itensOrdenados,
            valorResumo,
            infoResumo,
        });
    }

    return grupos.sort((a, b) => a.ordem - b.ordem);
}

async function obterCustoMensalVeiculo(veiculoId) {
    const [respProj, respMan] = await Promise.all([
        fetch(`${API_VEICULOS}/${veiculoId}/projecoes?meses=12`).then(r => r.json()),
        fetch(`${API_VEICULOS}/${veiculoId}/manutencoes-km?janela_meses=3`).then(r => r.json()).catch(() => null),
    ]);

    if (!respProj.success) throw new Error(respProj.error || 'Falha ao carregar projeções');

    const veiculo = (caminhosVeiculos || []).find(v => Number(v.id) === Number(veiculoId));
    const custoCadastral = veiculo ? calcularCustoMensalVeiculoLocal(veiculo, false) : 0;
    const tiposRegras = new Set((respMan?.success ? (respMan.data?.tipos_evento_regras || []) : []).map(t => String(t || '').toUpperCase()));
    const tiposDiretos = new Set(['COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO', ...Array.from(tiposRegras)]);
    const custoProjetivoComplementar = calcularCustoMensalEstimado(respProj.data || [], 12, tiposDiretos);
    const impactoManut = respMan?.success ? Number(respMan.data?.impacto_mensal_total || 0) : 0;
    return custoCadastral + custoProjetivoComplementar + (Number.isFinite(impactoManut) ? impactoManut : 0);
}

async function atualizarCustosMensais(veiculoIds) {
    const ids = (veiculoIds || []).filter(Boolean);
    await Promise.all(ids.map(async (id) => {
        const el = document.getElementById(`custo-mensal-${id}`);
        const valorEl = el?.querySelector('.custo-valor');
        try {
            const custo = await obterCustoMensalVeiculo(id);
            custoMensalConsolidado.VEICULO[id] = Number(custo || 0);
            const fmt = Number(custo || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
            if (valorEl) valorEl.textContent = `${fmt} / mês`;
        } catch (e) {
            console.error(e);
            const veiculo = (caminhosVeiculos || []).find(v => Number(v.id) === Number(id));
            const fallback = veiculo ? calcularCustoMensalVeiculoLocal(veiculo, false) : 0;
            custoMensalConsolidado.VEICULO[id] = Number(fallback || 0);
            if (valorEl) valorEl.textContent = '—';
        }
    }));
}

function abrirModalNovo() {
    veiculoEditando = null;
    document.getElementById('modal-titulo').textContent = 'Novo Veículo';
    document.getElementById('form-veiculo').reset();
    document.getElementById('veiculo-id').value = '';
    document.getElementById('status').value = 'SIMULADO';
    document.getElementById('data_inicio').value = new Date().toISOString().slice(0, 10);
    toggleDataInicio();
    document.getElementById('modal-veiculo').style.display = 'block';
}

function fecharModal() {
    document.getElementById('modal-veiculo').style.display = 'none';
    veiculoEditando = null;
}

function toggleDataInicio() {
    const status = document.getElementById('status')?.value;
    const wrap = document.getElementById('wrap-data-inicio');
    const statusGroup = document.getElementById('status-group');
    if (!wrap) return;
    const ativo = status === 'ATIVO';
    wrap.style.display = ativo ? 'block' : 'none';
    if (statusGroup) {
        if (ativo) {
            statusGroup.classList.remove('span-2');
        } else {
            statusGroup.classList.add('span-2');
        }
    }
}

async function abrirModalEditar(id) {
    try {
        const resp = await fetch(`${API_VEICULOS}/${id}`);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao carregar veículo');

        const v = data.data;
        veiculoEditando = id;
        document.getElementById('modal-titulo').textContent = 'Editar Veículo';
        document.getElementById('veiculo-id').value = v.id;

        document.getElementById('nome').value = v.nome || '';
        document.getElementById('tipo').value = v.tipo || 'carro';
        document.getElementById('combustivel').value = v.combustivel || 'gasolina';
        document.getElementById('autonomia_km_l').value = v.autonomia_km_l ?? '';
        document.getElementById('status').value = v.status || 'SIMULADO';
        document.getElementById('data_inicio').value = v.data_inicio ? v.data_inicio.slice(0, 10) : new Date().toISOString().slice(0, 10);

        document.getElementById('combustivel_valor_mensal').value = v.projecao_combustivel?.valor_mensal ?? '';
        document.getElementById('preco_medio_combustivel').value = v.preco_medio_combustivel ?? '';

        document.getElementById('ipva_mes').value = v.ipva?.mes ?? '';
        document.getElementById('ipva_valor').value = v.ipva?.valor ?? '';

        document.getElementById('seguro_mes').value = v.seguro?.mes ?? '';
        document.getElementById('seguro_valor').value = v.seguro?.valor ?? '';

        document.getElementById('licenciamento_mes').value = v.licenciamento?.mes ?? '';
        document.getElementById('licenciamento_valor').value = v.licenciamento?.valor ?? '';

        toggleDataInicio();
        document.getElementById('modal-veiculo').style.display = 'block';
    } catch (e) {
        console.error(e);
        alert('Erro: ' + e.message);
    }
}

async function salvarVeiculo(event) {
    event.preventDefault();

    const status = document.getElementById('status').value;
    const payload = {
        nome: document.getElementById('nome').value.trim(),
        tipo: document.getElementById('tipo').value,
        combustivel: document.getElementById('combustivel').value,
        autonomia_km_l: document.getElementById('autonomia_km_l').value,
        status: status,
        data_inicio: status === 'ATIVO' ? document.getElementById('data_inicio').value : null,

        combustivel_valor_mensal: document.getElementById('combustivel_valor_mensal').value || null,
        preco_medio_combustivel: document.getElementById('preco_medio_combustivel').value || null,

        ipva_mes: document.getElementById('ipva_mes').value || null,
        ipva_valor: document.getElementById('ipva_valor').value || null,

        seguro_mes: document.getElementById('seguro_mes').value || null,
        seguro_valor: document.getElementById('seguro_valor').value || null,

        licenciamento_mes: document.getElementById('licenciamento_mes').value || null,
        licenciamento_valor: document.getElementById('licenciamento_valor').value || null,
    };

    const id = document.getElementById('veiculo-id').value;
    const url = id ? `${API_VEICULOS}/${id}` : API_VEICULOS;
    const method = id ? 'PUT' : 'POST';

    try {
        const resp = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao salvar');
        alert(data.message || 'Salvo');
        fecharModal();
        await carregarVeiculos();
    } catch (e) {
        console.error(e);
        alert('Erro ao salvar: ' + e.message);
    }
}

async function deletarVeiculo(id, nome) {
    if (!confirm(`Deseja realmente excluir "${nome}"?\n\nAs projeções previstas desse veículo também serão removidas.`)) return;
    try {
        const resp = await fetch(`${API_VEICULOS}/${id}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao excluir');
        alert(data.message || 'Excluído');
        await carregarVeiculos();
    } catch (e) {
        console.error(e);
        alert('Erro ao excluir: ' + e.message);
    }
}

async function converterVeiculo(id) {
    if (!confirm('Converter SIMULADO → ATIVO?\n\nIsso não cria lançamentos reais; apenas torna as projeções reais daqui pra frente.')) return;
    const hoje = new Date().toISOString().slice(0, 10);
    const data_inicio = prompt('Data de início (YYYY-MM-DD):', hoje);
    if (!data_inicio) return;

    try {
        const resp = await fetch(`${API_VEICULOS}/${id}/converter`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ data_inicio })
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao converter');
        alert(data.message || 'Convertido');
        await carregarVeiculos();
    } catch (e) {
        console.error(e);
        alert('Erro ao converter: ' + e.message);
    }
}

async function toggleProjecoes(id) {
    const wrap = document.getElementById(`projecoes-${id}`);
    if (!wrap) return;

    const mostrando = wrap.style.display !== 'none';
    wrap.style.display = mostrando ? 'none' : 'block';
    if (mostrando) return;

    const body = wrap.querySelector('.projecoes-body');
    body.innerHTML = '<p class="loading">Carregando projeções...</p>';

    try {
        const resp = await fetch(`${API_VEICULOS}/${id}/projecoes?meses=24`);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao carregar projeções');

        if (!data.data || data.data.length === 0) {
            body.innerHTML = '<p class="empty-state">Nenhuma projeção configurada para o período.</p>';
            return;
        }

        projecoesIndex = {};
        const rows = data.data.map(p => {
            projecoesIndex[p.id] = { tipo_evento: p.tipo_evento || (p.metadata?.tipo_evento ?? null) };
            const mes = formatarMesAno(p.data_atual_prevista || p.data_prevista);
            const categoria = p.categoria?.nome || `Categoria #${p.categoria_id}`;
            const tipo = p.tipo_evento || (p.metadata?.tipo_evento ?? '');
            const valor = formatarMoeda(p.valor_previsto);
            const isPrevista = p.status === 'PREVISTA';
            const actions = isPrevista ? `
                <div class="row-actions">
                    <button class="row-action-button success" onclick="confirmarPrevista(${p.id})" title="Confirmar" aria-label="Confirmar">${veiculosIcon('check')}</button>
                    <button class="row-action-button" onclick="abrirModalAdiar(${p.id}, '${escapeAttr(p.data_atual_prevista || p.data_prevista)}')" title="Adiar" aria-label="Adiar">${veiculosIcon('clock')}</button>
                    <button class="row-action-button danger" onclick="ignorarPrevista(${p.id})" title="Ignorar" aria-label="Ignorar">${veiculosIcon('remove')}</button>
                </div>
            ` : `<span class="small-note">—</span>`;
            return `<tr>
                <td>${mes}</td>
                <td>${escapeHtml(tipo)}</td>
                <td>${escapeHtml(categoria)}</td>
                <td class="right">${valor}</td>
                <td><span class="badge-prevista">${p.status}</span></td>
                <td>${actions}</td>
            </tr>`;
        }).join('');

        const [usoResumo, manutResp] = await Promise.all([
            carregarUsoResumo(id),
            fetch(`${API_VEICULOS}/${id}/manutencoes-km?janela_meses=3`).then(r => r.json()).catch(() => null),
        ]);

        const manutResumo = manutResp?.success ? (manutResp.data || {}) : null;
        const manutImpacto = manutResumo ? Number(manutResumo.impacto_mensal_total || 0) : 0;
        const manutFonteImpacto = String(manutResumo?.fonte_impacto || '').toUpperCase();
        const manutObsImpacto = manutResumo?.observacao_impacto || manutResumo?.observacao || null;
        const tiposRegras = new Set((manutResumo?.regras || []).map(r => String(r?.tipo_evento || '').toUpperCase()).filter(Boolean));
        const grupos = _consolidarProjecoes(data.data || [], 12, tiposRegras);

        if (Number.isFinite(manutImpacto) && manutImpacto > 0) {
            const g = grupos.find(x => x && x.grupo === 'MANUTENCAO');
            const base = manutFonteImpacto === 'TEMPO'
                ? 'Baseado no intervalo informado (meses).'
                : (manutFonteImpacto === 'KM'
                    ? `Baseado em uso estimado (~ ${Number(manutResumo?.km_mes_estimado || 0).toLocaleString('pt-BR')} km/mês).`
                    : null);
            const info = base || manutObsImpacto || 'Impacto mensal estimado. Pode variar.';

            if (g) {
                g.valorResumo = `${formatarMoeda(manutImpacto)} / mês (estimado)`;
                g.infoResumo = info;
            } else {
                grupos.push({
                    grupo: 'MANUTENCAO',
                    label: 'Manutenção',
                    ordem: _ordemGrupoPrevisao('MANUTENCAO'),
                    itens: [],
                    valorResumo: `${formatarMoeda(manutImpacto)} / mês (estimado)`,
                    infoResumo: info,
                });
                grupos.sort((a, b) => a.ordem - b.ordem);
            }
        }

        const gruposHtml = (grupos || []).map(g => {
            const itensDetalhe = g.grupo === 'MANUTENCAO'
                ? (g.itens || []).filter(p => _ehEventoManutencao(p, tiposRegras))
                : (g.itens || []);

            const rowsGrupo = itensDetalhe.map(p => {
                const mes = formatarMesAno(p.data_atual_prevista || p.data_prevista);
                const categoria = p.categoria?.nome || `Categoria #${p.categoria_id}`;
                const tipo = _rotuloDetalheTipo(p);
                const valor = formatarMoeda(p.valor_previsto);
                const isPrevista = String(p.status || '').toUpperCase() === 'PREVISTA';
                const actions = isPrevista ? `
                    <div class="row-actions">
                        <button class="row-action-button success" onclick="confirmarPrevista(${p.id})" title="Confirmar" aria-label="Confirmar">${veiculosIcon('check')}</button>
                        <button class="row-action-button" onclick="abrirModalAdiar(${p.id}, '${escapeAttr(p.data_atual_prevista || p.data_prevista)}')" title="Adiar" aria-label="Adiar">${veiculosIcon('clock')}</button>
                        <button class="row-action-button danger" onclick="ignorarPrevista(${p.id})" title="Ignorar" aria-label="Ignorar">${veiculosIcon('remove')}</button>
                    </div>
                ` : `<span class="small-note">—</span>`;
                return `<tr>
                    <td>${mes}</td>
                    <td>${escapeHtml(tipo)}</td>
                    <td>${escapeHtml(categoria)}</td>
                    <td class="right">${valor}</td>
                    <td><span class="badge-prevista">${escapeHtml(p.status)}</span></td>
                    <td>${actions}</td>
                </tr>`;
            }).join('');

            const detalheVazio = (g.grupo === 'MANUTENCAO' && (!itensDetalhe || itensDetalhe.length === 0))
                ? `<div class="small-note">Nenhuma manutenção prevista ainda. Configure regras ou gere uma previsão em Manutenção por km.</div>`
                : '';

            return `
                <details class="prev-consolidada">
                    <summary>
                        <div class="prev-sum-left">
                            <div class="prev-titulo">${escapeHtml(g.label)}</div>
                            <div class="prev-info">${escapeHtml(g.infoResumo)}</div>
                        </div>
                        <div class="prev-sum-right">
                            <div class="prev-valor">${escapeHtml(g.valorResumo)}</div>
                        </div>
                    </summary>
                    <div class="prev-detalhe">
                        ${detalheVazio}
                        <table class="table-projecoes">
                            <thead>
                                <tr>
                                    <th>Mês</th>
                                    <th>Tipo</th>
                                    <th>Categoria</th>
                                    <th class="right">Valor</th>
                                    <th>Status</th>
                                    <th>Ações</th>
                                </tr>
                            </thead>
                            <tbody>${rowsGrupo || ''}</tbody>
                        </table>
                    </div>
                </details>
            `;
        }).join('');

        body.innerHTML = `
            <div class="uso-resumo">
                <div><strong>Uso estimado:</strong> ${Number(usoResumo.km_estimado_acumulado || 0).toLocaleString('pt-BR')} km</div>
                <div><strong>Média móvel:</strong> ${Number(usoResumo.media_movel_km_mes || 0).toLocaleString('pt-BR')} km/mês (${usoResumo.janela_meses || 3}m)</div>
                <div class="small-note">${escapeHtml(usoResumo.observacao || 'Estimativa baseada em consumo. Pode variar.')}</div>
            </div>
            <div class="prev-consolidadas">
                <div class="small-note">Visão consolidada por tipo (leitura). Expanda para ver ciclos/mês e aplicar ações da FASE 2.</div>
                ${gruposHtml || ''}
            </div>

            <details class="prev-auditoria">
                <summary>Ver lista completa por mês (auditoria)</summary>
                <table class="table-projecoes">
                <thead>
                    <tr>
                        <th>Mês</th>
                        <th>Tipo</th>
                        <th>Categoria</th>
                        <th class="right">Valor</th>
                        <th>Status</th>
                        <th>Ações</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
                </table>
            </details>
        `;
    } catch (e) {
        console.error(e);
        body.innerHTML = `<p class="empty-state">Erro ao carregar projeções: ${escapeHtml(e.message)}</p>`;
    }
}

function formatarData(iso) {
    try {
        const [y, m, d] = iso.split('-');
        return `${d}/${m}/${y}`;
    } catch {
        return iso;
    }
}

function formatarMesAno(iso) {
    try {
        const [y, m] = iso.split('-');
        return `${m}/${y}`;
    } catch {
        return iso;
    }
}

function formatarMoeda(valor) {
    const n = Number(valor || 0);
    return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function escapeHtml(str) {
    return String(str ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function escapeAttr(str) {
    return escapeHtml(str).replaceAll('`', '&#096;');
}

function renderFormaPagamentoMobilidade(valor, options = {}) {
    if (!valor) return '';
    if (window.FormasPagamentoUI?.renderFormaPagamento) {
        return window.FormasPagamentoUI.renderFormaPagamento(valor, {
            size: 'sm',
            showLabel: true,
            className: 'mobilidade-payment-method',
            ...options
        });
    }
    return `<span class="payment-method payment-method--sm payment-method--default mobilidade-payment-method"><span class="payment-method__label">${escapeHtml(valor)}</span></span>`;
}

// Fechar modal ao clicar fora
window.onclick = function(event) {
    const modal = document.getElementById('modal-veiculo');
    if (event.target === modal) {
        fecharModal();
    }
};

// Fechar modal Transporte por App ao clicar fora
window.addEventListener('click', function(event) {
    const modalApp = document.getElementById('modal-app');
    if (event.target === modalApp) {
        fecharModalApp();
    }
});

let manutModalVeiculoId = null;

function toggleManutencoes(id) {
    abrirModalManutencaoKm(id);
}

// Fechar modal de manutenção ao clicar fora
window.addEventListener('click', function(event) {
    const modal = document.getElementById('modal-manutencao-km');
    if (event.target === modal) {
        fecharModalManutencaoKm();
    }
});

async function abrirModalManutencaoKm(veiculoId) {
    manutModalVeiculoId = veiculoId;

    // garantir categorias para o select do formulário
    if (!categorias || categorias.length === 0) {
        await carregarCategorias();
    }
    popularCategoriasSelectRegraKm();

    toggleFormNovaRegraKm(false);

    document.getElementById('modal-manutencao-km').style.display = 'block';
    await carregarManutencaoKmModal(veiculoId);
}

function fecharModalManutencaoKm() {
    document.getElementById('modal-manutencao-km').style.display = 'none';
    manutModalVeiculoId = null;
    toggleFormNovaRegraKm(false);
}

function popularCategoriasSelectRegraKm() {
    const sel = document.getElementById('regra-categoria');
    if (!sel) return;
    sel.innerHTML = '';

    (categorias || []).forEach(c => {
        if (c && c.ativo === false) return;
        sel.innerHTML += `<option value="${c.id}">${escapeHtml(c.nome)}</option>`;
    });
}

function toggleTipoCustomRegraKm() {
    const sel = document.getElementById('regra-tipo-evento');
    const custom = document.getElementById('regra-tipo-custom');
    if (!sel || !custom) return;
    const show = sel.value === 'OUTRO';
    custom.style.display = show ? 'block' : 'none';
    if (!show) custom.value = '';
}

function toggleFormNovaRegraKm(mostrar) {
    const form = document.getElementById('form-regra-km');
    if (!form) return;
    form.style.display = mostrar ? 'block' : 'none';
    if (!mostrar) {
        form.reset?.();
        toggleTipoCustomRegraKm();
    }
}

function _labelTipoEvento(tipo) {
    const t = String(tipo || '').toUpperCase();
    const mapa = {
        'TROCA_OLEO': 'Troca de óleo',
        'REVISAO_GERAL': 'Revisão geral',
        'TROCA_PNEUS': 'Troca de pneus',
        'ALINHAMENTO_BALANCEAMENTO': 'Alinhamento / Balanceamento',
    };
    return mapa[t] || tipo || 'Manutenção';
}

async function carregarManutencaoKmModal(veiculoId) {
    const usoEl = document.getElementById('manut-uso');
    const estimEl = document.getElementById('manut-estimativas');
    const estimVazioEl = document.getElementById('manut-estimativas-vazio');
    const regrasEl = document.getElementById('manut-regras');
    const impactoEl = document.getElementById('manut-impacto');

    if (usoEl) usoEl.innerHTML = '<p class="loading">Carregando uso...</p>';
    if (estimEl) estimEl.innerHTML = '';
    if (estimVazioEl) estimVazioEl.style.display = 'none';
    if (regrasEl) regrasEl.innerHTML = '<p class="loading">Carregando regras...</p>';
    if (impactoEl) impactoEl.innerHTML = '<p class="loading">Calculando impacto...</p>';

    try {
        const [usoResumo, resp] = await Promise.all([
            carregarUsoResumo(veiculoId),
            fetch(`${API_VEICULOS}/${veiculoId}/manutencoes-km?janela_meses=3`).then(r => r.json()),
        ]);
        if (!resp.success) throw new Error(resp.error || 'Falha ao carregar manutenção');

        const regras = resp.data?.regras || [];
        const estimativas = resp.data?.estimativas || [];
        const obs = resp.data?.observacao || 'Baseado no uso estimado. Pode variar.';
        const fonteUso = String(resp.data?.fonte_uso || '').toUpperCase();
        const kmMesEstimado = Number(resp.data?.km_mes_estimado || 0);
        const impactoMensal = Number(resp.data?.impacto_mensal_total || 0);
        const fonteImpacto = String(resp.data?.fonte_impacto || '').toUpperCase();
        const obsImpacto = resp.data?.observacao_impacto || null;

        if (usoEl) {
            const notaFonte =
                fonteUso === 'PROJETADO'
                    ? 'Estimativa com base em uso projetado (simulação).'
                    : (fonteUso === 'HISTORICO' ? 'Estimativa com base no uso histórico.' : 'Estimativa indisponível.');
            usoEl.innerHTML = `
                <div><strong>Km acumulado estimado:</strong> ${Number(usoResumo.km_estimado_acumulado || 0).toLocaleString('pt-BR')} km</div>
                <div><strong>Média móvel:</strong> ${Number(usoResumo.media_movel_km_mes || 0).toLocaleString('pt-BR')} km/mês (últimos ${usoResumo.janela_meses || 3} meses)</div>
                <div><strong>Uso mensal estimado:</strong> ${kmMesEstimado > 0 ? `${kmMesEstimado.toLocaleString('pt-BR')} km/mês` : '—'} <span class="small-note">(${escapeHtml(notaFonte)})</span></div>
                <div class="small-note">${escapeHtml(obsImpacto || obs)}</div>
            `;
        }

        if (regrasEl) {
            if (!regras.length) {
                regrasEl.innerHTML = `<div class="empty-state"><p>Nenhuma regra cadastrada.</p></div>`;
            } else {
                regrasEl.innerHTML = regras.map(r => `
                    <div class="manut-regra-item">
                        <div class="linha">
                            <div class="titulo">${escapeHtml(_labelTipoEvento(r.tipo_evento))}</div>
                            <div class="small-note">A cada ${Number(r.intervalo_km || 0).toLocaleString('pt-BR')} km • ${formatarMoeda(r.custo_estimado)} • ${escapeHtml(r.categoria?.nome || 'Categoria')}</div>
                        </div>
                        <div class="row-actions">
                            <button class="row-action-button danger" onclick="removerRegraKm(${veiculoId}, ${r.id})" title="Remover" aria-label="Remover">${veiculosIcon('trash')}</button>
                        </div>
                    </div>
                `).join('');
            }
        }

        if (estimEl) {
            if (!estimativas.length) {
                if (estimVazioEl) estimVazioEl.style.display = 'block';
            } else {
                estimEl.innerHTML = estimativas.map(e => {
                    const dataEst = e.data_prevista_estimada ? formatarMesAno(e.data_prevista_estimada) : '(uso insuficiente)';
                    const btn = e.existe_evento
                        ? `<span class="small-note">Já existe uma despesa prevista/adiada/confirmada.</span>`
                        : `<button class="row-action-button success" onclick="gerarManutencaoKm(${veiculoId}, ${e.regra_id})" title="Gerar despesa prevista" aria-label="Gerar despesa prevista">${veiculosIcon('check')}</button>`;
                    return `
                        <div class="manut-card">
                            <div><strong>${escapeHtml(_labelTipoEvento(e.tipo_evento))}</strong></div>
                            <div class="small-note">Intervalo: a cada ${Number(e.intervalo_km || 0).toLocaleString('pt-BR')} km</div>
                            <div class="small-note">Próxima estimativa: ~ ${escapeHtml(dataEst)}</div>
                            <div class="small-note">Custo estimado: ${formatarMoeda(e.custo_estimado)}</div>
                            <div class="small-note">Km restante: ${Math.round(e.km_restante || 0).toLocaleString('pt-BR')} km</div>
                            <div class="row-actions" style="margin-top:8px;">${btn}</div>
                        </div>
                    `;
                }).join('');
            }
        }

        if (impactoEl) {
            if (!regras.length) {
                impactoEl.innerHTML = `<div><strong>Manutenção:</strong> —</div><div class="small-note">Cadastre regras para estimar impacto.</div>`;
            } else if (!Number.isFinite(impactoMensal) || impactoMensal <= 0) {
                impactoEl.innerHTML = `
                    <div><strong>Manutenção:</strong> —</div>
                    <div class="small-note">Sem dados suficientes para estimar uso projetado. Informe combustível mensal e preço médio no veículo.</div>
                `;
            } else {
                impactoEl.innerHTML = `
                    <div><strong>Manutenção adiciona:</strong> ~ ${formatarMoeda(impactoMensal)} / mês</div>
                    <div class="small-note">${escapeHtml(obsImpacto || obs)}</div>
                `;
            }
        }
    } catch (e) {
        console.error(e);
        if (usoEl) usoEl.innerHTML = `<p class="empty-state">Erro ao carregar uso: ${escapeHtml(e.message)}</p>`;
        if (regrasEl) regrasEl.innerHTML = `<p class="empty-state">Erro ao carregar regras: ${escapeHtml(e.message)}</p>`;
        if (impactoEl) impactoEl.innerHTML = `<p class="empty-state">Erro: ${escapeHtml(e.message)}</p>`;
    }
}

async function gerarManutencaoKm(veiculoId, regraId) {
    if (!confirm('Gerar despesa prevista de manutenção por km?\n\nEsta ação cria apenas este evento. Não ajusta futuros.')) return;
    try {
        const resp = await fetch(`${API_VEICULOS}/${veiculoId}/manutencoes-km/gerar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ regra_id: regraId, janela_meses: 3 })
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao gerar manutenção');
        alert(data.message || 'OK');
        await carregarVeiculos();
        if (manutModalVeiculoId && Number(manutModalVeiculoId) === Number(veiculoId)) {
            await carregarManutencaoKmModal(veiculoId);
        }
    } catch (e) {
        console.error(e);
        alert('Erro: ' + e.message);
    }
}

async function criarRegraKm(event) {
    event.preventDefault();
    if (!manutModalVeiculoId) return;

    const tipoSel = document.getElementById('regra-tipo-evento').value;
    const tipoCustom = document.getElementById('regra-tipo-custom').value.trim();
    const tipo_evento = (tipoSel === 'OUTRO' ? tipoCustom : tipoSel).trim().toUpperCase();

    if (!tipo_evento) {
        alert('Informe o tipo da regra.');
        return;
    }

    const payload = {
        tipo_evento,
        intervalo_km: document.getElementById('regra-intervalo-km').value,
        meses_intervalo: document.getElementById('regra-intervalo-meses')?.value,
        custo_estimado: document.getElementById('regra-custo').value,
        categoria_id: document.getElementById('regra-categoria').value,
        ativo: true,
    };

    try {
        const resp = await fetch(`${API_VEICULOS}/${manutModalVeiculoId}/regras-km`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao criar regra');
        toggleFormNovaRegraKm(false);
        await carregarManutencaoKmModal(manutModalVeiculoId);
    } catch (e) {
        console.error(e);
        alert('Erro ao criar regra: ' + e.message);
    }
}

async function removerRegraKm(veiculoId, regraId) {
    if (!confirm('Remover esta regra de manutenção?\n\nIsso não remove despesas previstas já criadas.')) return;
    try {
        const resp = await fetch(`${API_VEICULOS}/${veiculoId}/regras-km/${regraId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao remover regra');
        await carregarManutencaoKmModal(veiculoId);
    } catch (e) {
        console.error(e);
        alert('Erro ao remover regra: ' + e.message);
    }
}

// confirmarPrevista: abre modal de confirmação com escolha de meio de pagamento
function confirmarPrevista(despesaId, dadosPrevista) {
    abrirModalConfirmar(despesaId, dadosPrevista || null);
}

function abrirModalAdiar(despesaId, dataAtualIso) {
    document.getElementById('adiar-despesa-id').value = despesaId;
    const input = document.getElementById('adiar-nova-data');
    if (dataAtualIso) {
        input.value = (dataAtualIso || '').slice(0, 7); // YYYY-MM
    } else {
        input.value = new Date().toISOString().slice(0, 7);
    }
    document.getElementById('modal-adiar').style.display = 'block';
}

function fecharModalAdiar() {
    document.getElementById('modal-adiar').style.display = 'none';
}

async function confirmarAdiar(event) {
    event.preventDefault();
    const despesaId = document.getElementById('adiar-despesa-id').value;
    const ym = document.getElementById('adiar-nova-data').value; // YYYY-MM
    if (!ym) return;
    const nova_data = `${ym}-01`;

    if (!confirm('Adiar esta despesa?\n\nEsta ação afeta apenas esta despesa. Outras projeções não serão alteradas.')) return;

    let ajustar_ciclo = false;
    const tipo = projecoesIndex[Number(despesaId)]?.tipo_evento;
    const ehPossivelCiclo = tipo && !['COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO', 'PARCELA_FINANCIAMENTO', 'IOF_FINANCIAMENTO', 'TRANSPORTE_APP'].includes(String(tipo).toUpperCase());
    if (ehPossivelCiclo) {
        ajustar_ciclo = confirm(
            'Esta manutenção faz parte de um ciclo por km.\n' +
            'Deseja ajustar o ciclo a partir desta nova data?\n' +
            'Isso irá apenas gerar a próxima ocorrência estimada.'
        );
    }

    try {
        const resp = await fetch(`${API_DESPESAS_PREVISTAS}/${despesaId}/adiar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nova_data, ajustar_ciclo })
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao adiar');
        alert(data.message || 'Adiada');
        fecharModalAdiar();
        await carregarVeiculos();
    } catch (e) {
        console.error(e);
        alert('Erro ao adiar: ' + e.message);
    }
}

async function ignorarPrevista(despesaId) {
    if (!confirm('Ignorar esta despesa prevista?\n\nO registro permanecerá no histórico como IGNORADA.')) return;
    try {
        const resp = await fetch(`${API_DESPESAS_PREVISTAS}/${despesaId}/ignorar`, { method: 'POST' });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao ignorar');
        alert(data.message || 'Ignorada');
        await carregarVeiculos();
    } catch (e) {
        console.error(e);
        alert('Erro ao ignorar: ' + e.message);
    }
}

// Fechar modal adiar ao clicar fora
window.addEventListener('click', function(event) {
    const modalAdiar = document.getElementById('modal-adiar');
    if (event.target === modalAdiar) {
        fecharModalAdiar();
    }
});

async function carregarUsoResumo(veiculoId) {
    try {
        const resp = await fetch(`${API_VEICULOS}/${veiculoId}/uso?janela_meses=3`);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao carregar uso');
        return data.data || {};
    } catch (e) {
        console.error(e);
        return { km_estimado_acumulado: 0, media_movel_km_mes: 0, janela_meses: 3, observacao: 'Estimativa baseada em consumo. Pode variar.' };
    }
}

async function abrirModalFinanciamento(veiculoId) {
    document.getElementById('fin-veiculo-id').value = veiculoId;
    await carregarIndexadoresSelect();

    const resumoEl = document.getElementById('fin-resumo');
    resumoEl.style.display = 'none';
    resumoEl.innerHTML = '';

    try {
        const respV = await fetch(`${API_VEICULOS}/${veiculoId}`);
        const dataV = await respV.json();
        if (dataV.success) finVeiculoCache[veiculoId] = dataV.data;

        const resp = await fetch(`${API_VEICULOS}/${veiculoId}/financiamento`);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao carregar financiamento');

        const fin = data.data;
        if (fin) {
            document.getElementById('fin-valor-bem').value = fin.valor_bem ?? '';
            document.getElementById('fin-entrada').value = fin.entrada ?? 0;
            document.getElementById('fin-numero-parcelas').value = fin.numero_parcelas ?? 48;
            document.getElementById('fin-taxa-juros').value = fin.taxa_juros_mensal ?? 2.02;
            document.getElementById('fin-indexador').value = fin.indexador_tipo ?? '';
            document.getElementById('fin-iof').value = fin.iof_percentual ?? 0.38;
        } else {
            document.getElementById('fin-valor-bem').value = '';
            document.getElementById('fin-entrada').value = 0;
            document.getElementById('fin-numero-parcelas').value = 48;
            document.getElementById('fin-taxa-juros').value = 2.02;
            document.getElementById('fin-indexador').value = 'TR';
            document.getElementById('fin-iof').value = 0.38;
        }

        document.getElementById('modal-financiamento').style.display = 'block';
    } catch (e) {
        console.error(e);
        alert('Erro ao abrir financiamento: ' + e.message);
    }
}

function fecharModalFinanciamento() {
    document.getElementById('modal-financiamento').style.display = 'none';
}

async function carregarIndexadoresSelect() {
    const sel = document.getElementById('fin-indexador');
    if (!sel) return;
    sel.innerHTML = '<option value="">(sem indexador)</option>';
    try {
        const resp = await fetch(API_INDEXADORES_TIPOS);
        const tipos = await resp.json();
        (tipos || []).forEach(t => {
            sel.innerHTML += `<option value="${t.nome}">${t.nome}</option>`;
        });
    } catch (e) {
        // fallback
        ['TR', 'IPCA', 'IGP-M', 'CDI', 'SELIC'].forEach(n => {
            sel.innerHTML += `<option value="${n}">${n}</option>`;
        });
    }
}

async function salvarFinanciamento(event) {
    event.preventDefault();
    const veiculoId = document.getElementById('fin-veiculo-id').value;
    const payload = {
        valor_bem: document.getElementById('fin-valor-bem').value,
        entrada: document.getElementById('fin-entrada').value,
        numero_parcelas: document.getElementById('fin-numero-parcelas').value,
        taxa_juros_mensal: document.getElementById('fin-taxa-juros').value,
        indexador_tipo: document.getElementById('fin-indexador').value || null,
        iof_percentual: document.getElementById('fin-iof').value,
    };

    try {
        const resp = await fetch(`${API_VEICULOS}/${veiculoId}/financiamento`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao salvar financiamento');

        const fin = data.financiamento || {};
        const res = data.resumo || {};
        const valorFinanciado = Number(fin.valor_financiado || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        const iofValor = Number(res.iof_valor || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        const mediaParcela = Number(res.valor_medio_parcela || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        const custoTotal = Number(res.custo_total_financiamento || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

        const veiculo = finVeiculoCache[Number(veiculoId)];
        const usoComb = Number(veiculo?.projecao_combustivel?.valor_mensal || 0) * 12;
        const usoAnual = Number(veiculo?.ipva?.valor || 0) + Number(veiculo?.seguro?.valor || 0) + Number(veiculo?.licenciamento?.valor || 0);
        const custoUso = usoComb + usoAnual;
        const custoUsoFmt = custoUso.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        const custoTotalVeiculoFmt = (custoUso + Number(res.custo_total_financiamento || 0)).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

        const resumoEl = document.getElementById('fin-resumo');
        resumoEl.style.display = 'block';
        resumoEl.innerHTML = `
            <div><strong>Valor financiado:</strong> ${valorFinanciado}</div>
            <div><strong>IOF:</strong> ${iofValor} (${res.iof_percentual || 0}% )</div>
            <div><strong>Parcela média (estimada):</strong> ${mediaParcela}</div>
            <div><strong>Custo total do financiamento:</strong> ${custoTotal}</div>
            <div><strong>Custo total estimado do veículo (uso + financiamento):</strong> ${custoTotalVeiculoFmt}</div>
            <div class="small-note">Uso estimado (12m): ${custoUsoFmt} (combustível + anuais configurados)</div>
            <div class="small-note">Não cria lançamentos reais automaticamente. Parcelas são despesas previstas.</div>
        `;

        alert(data.message || 'Financiamento salvo');
        await carregarVeiculos();
    } catch (e) {
        console.error(e);
        alert('Erro ao salvar financiamento: ' + e.message);
    }
}

async function removerFinanciamento() {
    const veiculoId = document.getElementById('fin-veiculo-id').value;
    if (!confirm('Remover financiamento (simulação)?\n\nIsto removerá apenas parcelas PREVISTAS; não tocará em confirmadas/adiadas/ignoradas.')) return;
    try {
        const resp = await fetch(`${API_VEICULOS}/${veiculoId}/financiamento`, { method: 'DELETE' });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao remover');
        alert(data.message || 'Removido');
        fecharModalFinanciamento();
        await carregarVeiculos();
    } catch (e) {
        console.error(e);
        alert('Erro ao remover financiamento: ' + e.message);
    }
}

// Fechar modal financiamento ao clicar fora
window.addEventListener('click', function(event) {
    const modal = document.getElementById('modal-financiamento');
    if (event.target === modal) {
        fecharModalFinanciamento();
    }
});

// ================================================================
// VEIC-2 — SISTEMA DE ABAS
// ================================================================

const API_CARTOES = '/api/cartoes';
const API_CENARIO_ATIVO = `${API_VEICULOS}/cenario-ativo`;

let abaAtiva = 'comparacao';
let cenarioAtivoState = {}; // { tipo: 'VEICULO'|'TRANSPORTE_APP', id: N }
let cartoesCacheGlobal = null;

function ativarAba(nome) {
    abaAtiva = nome;
    const abas = ['comparacao', 'configuracao', 'efetivacao'];
    abas.forEach(a => {
        const tab = document.getElementById(`tab-${a}`);
        const bloco = document.getElementById(`bloco-${a}`);
        if (tab) {
            tab.classList.toggle('active', a === nome);
            tab.setAttribute('aria-selected', a === nome ? 'true' : 'false');
        }
        if (bloco) bloco.style.display = a === nome ? '' : 'none';
    });

    if (nome === 'comparacao') renderizarComparacao();
    if (nome === 'configuracao') renderizarConfiguracao();
    if (nome === 'efetivacao') iniciarEfetivacao();
}

// ================================================================
// CENÁRIO ATIVO (persistência backend + localStorage fallback)
// ================================================================

async function carregarCenarioAtivo() {
    // Fonte primária: banco via /api/veiculos/mobilidade/ativo
    try {
        const resp = await fetch(`${API_VEICULOS}/mobilidade/ativo`);
        const data = await resp.json();
        if (data.success && data.data) {
            const c = data.data;
            cenarioAtivoState = {
                tipo: c.tipo_modalidade,
                id: c.origem_id,
                nome_origem: c.nome_origem,
                recorrencia: c.recorrencia || null,
                meio_pagamento: c.meio_pagamento || null,
                cartao_id: c.cartao_id || null,
                categoria_cartao_id: c.categoria_cartao_id || null,
            };
            _sincronizarMobilidadeAtivaLocal(c.tipo_modalidade, c.origem_id);
            return;
        }
    } catch (e) {
        console.warn('Falha ao carregar cenário ativo do banco:', e);
    }
    // Fallback: localStorage legado (leitura apenas — não grava mais)
    try {
        const raw = localStorage.getItem(STORAGE_MOBILIDADE_ATIVA);
        if (raw) {
            const obj = JSON.parse(raw);
            const vIds = (obj.VEICULO || []).map(Number).filter(Number.isFinite);
            const aIds = (obj.TRANSPORTE_APP || []).map(Number).filter(Number.isFinite);
            if (vIds.length) cenarioAtivoState = { tipo: 'VEICULO', id: vIds[0] };
            else if (aIds.length) cenarioAtivoState = { tipo: 'TRANSPORTE_APP', id: aIds[0] };
        }
    } catch (e) { /* sem fallback */ }
}

function _sincronizarMobilidadeAtivaLocal(tipo, id) {
    if (tipo === 'VEICULO') {
        mobilidadeAtiva.VEICULO = new Set([id]);
        mobilidadeAtiva.TRANSPORTE_APP = new Set();
    } else if (tipo === 'TRANSPORTE_APP') {
        mobilidadeAtiva.VEICULO = new Set();
        mobilidadeAtiva.TRANSPORTE_APP = new Set([id]);
    } else if (tipo === 'ASSINATURA') {
        mobilidadeAtiva.VEICULO = new Set();
        mobilidadeAtiva.TRANSPORTE_APP = new Set();
    } else {
        mobilidadeAtiva.VEICULO = new Set();
        mobilidadeAtiva.TRANSPORTE_APP = new Set();
    }
}

async function salvarCenarioAtivo(tipo, id) {
    // Chamado apenas para tipos sem modal de ativação (TRANSPORTE_APP legado, etc.)
    // Para VEICULO e ASSINATURA: o fluxo passa pelo modal que chama /mobilidade/ativar.
    cenarioAtivoState = { tipo, id };
    _sincronizarMobilidadeAtivaLocal(tipo, id);
}

function isCenarioAtivo(tipo, id) {
    return cenarioAtivoState.tipo === tipo && Number(cenarioAtivoState.id) === Number(id);
}

// ================================================================
// BLOCO 1 — COMPARAÇÃO
// ================================================================

let cenariosSelecionados = new Set(); // Set de chaves "TIPO_ID"
let todosOsCenarios = []; // [{tipo, id, nome, subLabel, custoMensal, custoAnual, itens}]

function _chaveCenario(tipo, id) { return `${tipo}_${id}`; }

// Calcula custo mensal de veículo diretamente dos campos do objeto,
// sem depender do cache assíncrono custoMensalConsolidado.
// Usa cache como enriquecimento se já estiver disponível.
function calcularCustoMensalVeiculoLocal(v, usarCache = true) {
    const cached = Number(custoMensalConsolidado?.VEICULO?.[v.id] || 0);
    if (usarCache && cached > 0) return cached;
    const totalApi = Number(v.total_mensal_estimado || 0);
    let soma = 0;
    if (v.projecao_combustivel?.valor_mensal) soma += Number(v.projecao_combustivel.valor_mensal);
    if (v.ipva?.valor) soma += Number(v.ipva.valor) / 12;
    if (v.seguro?.valor) soma += Number(v.seguro.valor) / 12;
    if (v.licenciamento?.valor) soma += Number(v.licenciamento.valor) / 12;
    if (totalApi > 0 || soma === 0) return totalApi;
    return soma;
}

async function construirTodosOsCenarios(veiculos, apps) {
    const todos = [];

    for (const v of (veiculos || [])) {
        const custo = calcularCustoMensalVeiculoLocal(v);
        const itens = [];
        if (v.projecao_combustivel?.valor_mensal) itens.push({ nome: 'Combustível/mês', valor: Number(v.projecao_combustivel.valor_mensal) });
        if (v.ipva?.valor) itens.push({ nome: 'IPVA (diluído)', valor: Number(v.ipva.valor) / 12 });
        if (v.seguro?.valor) itens.push({ nome: 'Seguro (diluído)', valor: Number(v.seguro.valor) / 12 });
        if (v.licenciamento?.valor) itens.push({ nome: 'Licenciamento (diluído)', valor: Number(v.licenciamento.valor) / 12 });

        todos.push({
            tipo: 'VEICULO',
            id: v.id,
            nome: v.nome,
            subLabel: `${v.tipo} · ${v.combustivel} · ${v.autonomia_km_l} km/L`,
            statusLabel: v.status,
            custoMensal: custo,
            custoAnual: custo * 12,
            itens,
            raw: v,
        });
    }

    for (const a of (caminhosAssinaturas || [])) {
        const custo = Number(a.valor_mensal || 0);
        todos.push({
            tipo: 'ASSINATURA',
            id: a.id,
            nome: a.nome || 'Carro por Assinatura',
            subLabel: 'Contrato mensal de mobilidade',
            statusLabel: a.status || 'ATIVO',
            custoMensal: custo,
            custoAnual: custo * 12,
            itens: [{ nome: 'Assinatura mensal', valor: custo }],
            raw: a,
        });
    }

    for (const c of (apps || [])) {
        const custo = Number(c.valor_mensal || 0);
        todos.push({
            tipo: 'TRANSPORTE_APP',
            id: c.id,
            nome: c.nome || 'Transporte por App',
            subLabel: `${Number(c.km_mensal_estimado || 0).toLocaleString('pt-BR')} km/mês · ${formatarMoeda(c.preco_medio_por_km || 0)} /km`,
            statusLabel: 'APP',
            custoMensal: custo,
            custoAnual: custo * 12,
            itens: [{ nome: 'Custo mensal', valor: custo }],
            raw: c,
        });
    }

    const filtro = document.getElementById('comp-tipo')?.value || 'todos';
    let filtrados = todos;
    if (filtro === 'proprio_assinatura') {
        filtrados = todos.filter(c => c.tipo === 'VEICULO' || c.tipo === 'ASSINATURA');
    } else if (filtro === 'proprio_app') {
        filtrados = todos.filter(c => c.tipo === 'VEICULO' || c.tipo === 'TRANSPORTE_APP');
    }

    todosOsCenarios = filtrados;

    // Selecionar os primeiros 3 automaticamente se nenhum selecionado ainda
    if (cenariosSelecionados.size === 0) {
        filtrados.slice(0, 3).forEach(c => cenariosSelecionados.add(_chaveCenario(c.tipo, c.id)));
    }
    Array.from(cenariosSelecionados).forEach(chave => {
        if (!filtrados.some(c => _chaveCenario(c.tipo, c.id) === chave)) cenariosSelecionados.delete(chave);
    });
    if (cenariosSelecionados.size === 0) {
        filtrados.slice(0, 3).forEach(c => cenariosSelecionados.add(_chaveCenario(c.tipo, c.id)));
    }
}

async function renderizarComparacao() {
    if (!caminhosVeiculos || !caminhosApps || !caminhosAssinaturas) return;
    await construirTodosOsCenarios(caminhosVeiculos, caminhosApps);

    const seletorWrap = document.getElementById('comp-seletor-wrap');

    if (!todosOsCenarios.length) {
        if (seletorWrap) seletorWrap.style.display = 'none';
        _renderComparacaoVazio();
        return;
    }

    if (seletorWrap) seletorWrap.style.display = '';
    renderSeletorCenarios();
    renderResumoSuperior();
    renderCardsComparacao();
    renderTabelaComparativa();
}

function _renderComparacaoVazio() {
    const seletor = document.getElementById('comp-seletor-lista');
    const resumo = document.getElementById('comp-resumo-superior');
    const cards = document.getElementById('comp-cards');
    const tabelaWrap = document.getElementById('comp-tabela-wrap');

    if (resumo) resumo.style.display = 'none';
    if (tabelaWrap) tabelaWrap.style.display = 'none';

    if (seletor) seletor.innerHTML = '';

    if (cards) cards.innerHTML = `
        <div class="veic-empty-state">
            <div class="veic-empty-icon" aria-hidden="true">
                <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M10 46h44M14 46l5-16h10L32 46M32 30l3-16h10l5 16M20 38h8M36 38h8"/>
                    <circle cx="18" cy="49" r="2"/><circle cx="28" cy="49" r="2"/>
                    <circle cx="36" cy="49" r="2"/><circle cx="46" cy="49" r="2"/>
                </svg>
            </div>
            <h3 class="veic-empty-titulo">Nenhum cenário cadastrado ainda</h3>
            <p class="veic-empty-sub">Cadastre veículos, assinaturas ou transporte por app para comparar custos lado a lado.</p>
            <div class="veic-empty-acoes">
                <button class="btn btn-primary" onclick="ativarAba('configuracao')">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="width:14px;height:14px;margin-right:6px;"><path d="M12 5v14M5 12h14"/></svg>
                    Ir para Configuração
                </button>
            </div>
            <div class="veic-empty-cards-placeholder">
                <div class="veic-placeholder-card">
                    <div class="veic-placeholder-tipo">Veículo próprio</div>
                    <div class="veic-placeholder-nome"></div>
                    <div class="veic-placeholder-custo"></div>
                    <div class="veic-placeholder-linhas"><div></div><div></div><div></div></div>
                </div>
                <div class="veic-placeholder-card">
                    <div class="veic-placeholder-tipo">Carro por assinatura</div>
                    <div class="veic-placeholder-nome"></div>
                    <div class="veic-placeholder-custo"></div>
                    <div class="veic-placeholder-linhas"><div></div><div></div><div></div></div>
                </div>
                <div class="veic-placeholder-card">
                    <div class="veic-placeholder-tipo">Transporte por App</div>
                    <div class="veic-placeholder-nome"></div>
                    <div class="veic-placeholder-custo"></div>
                    <div class="veic-placeholder-linhas"><div></div><div></div><div></div></div>
                </div>
            </div>
        </div>
    `;
}

function renderSeletorCenarios() {
    const el = document.getElementById('comp-seletor-lista');
    if (!el) return;

    if (!todosOsCenarios.length) {
        return; // estado vazio já tratado por _renderComparacaoVazio()
    }

    el.innerHTML = todosOsCenarios.map(c => {
        const chave = _chaveCenario(c.tipo, c.id);
        const selecionado = cenariosSelecionados.has(chave);
        return `
            <label class="comp-seletor-item${selecionado ? ' selecionado' : ''}" onclick="toggleSelecaoCenario('${chave}', this)">
                <input type="checkbox" ${selecionado ? 'checked' : ''} style="pointer-events:none;">
                <span>${escapeHtml(c.nome)}</span>
                <span class="small-note" style="margin-left:4px;">${formatarMoeda(c.custoMensal)}/mês</span>
            </label>
        `;
    }).join('');
}

function toggleSelecaoCenario(chave, labelEl) {
    if (cenariosSelecionados.has(chave)) {
        cenariosSelecionados.delete(chave);
        labelEl.classList.remove('selecionado');
        labelEl.querySelector('input').checked = false;
    } else {
        if (cenariosSelecionados.size >= 3) {
            alert('Selecione no máximo 3 cenários para comparar.');
            return;
        }
        cenariosSelecionados.add(chave);
        labelEl.classList.add('selecionado');
        labelEl.querySelector('input').checked = true;
    }
    renderResumoSuperior();
    renderCardsComparacao();
    renderTabelaComparativa();
}

function getCenariosSelecionados() {
    return todosOsCenarios.filter(c => cenariosSelecionados.has(_chaveCenario(c.tipo, c.id)));
}

function labelTipoCenario(c) {
    if (c?.tipo === 'VEICULO') return 'Veículo próprio';
    if (c?.tipo === 'ASSINATURA') return 'Assinatura';
    if (c?.tipo === 'TRANSPORTE_APP') return 'App/Táxi';
    return 'Mobilidade';
}

function calcularCustoPorKmCenario(c) {
    if (!c) return null;
    if (c.tipo === 'TRANSPORTE_APP') {
        const km = Number(c.raw?.km_mensal_estimado || 0);
        return km > 0 ? c.custoMensal / km : null;
    }
    if (c.tipo === 'VEICULO') {
        const preco = Number(c.raw?.preco_medio_combustivel || 0);
        const autonomia = Number(c.raw?.autonomia_km_l || 0);
        const comb = Number(c.raw?.projecao_combustivel?.valor_mensal || 0);
        if (preco > 0 && autonomia > 0 && comb > 0) {
            const kmMes = (comb / preco) * autonomia;
            return kmMes > 0 ? c.custoMensal / kmMes : null;
        }
        const usoManual = Number(document.getElementById('comp-uso-mensal')?.value || 0);
        return usoManual > 0 ? c.custoMensal / usoManual : null;
    }
    const usoManual = Number(document.getElementById('comp-uso-mensal')?.value || 0);
    return usoManual > 0 ? c.custoMensal / usoManual : null;
}

function statusCenarioComparacao(c, selecionados) {
    const maisEconomico = selecionados.reduce((a, b) => a.custoMensal < b.custoMensal ? a : b, selecionados[0]);
    if (maisEconomico && c.tipo === maisEconomico.tipo && Number(c.id) === Number(maisEconomico.id)) return 'Mais econômico';
    if (c.tipo === 'TRANSPORTE_APP') return 'Conveniência total';
    return 'Boa relação custo-benefício';
}

function renderResumoSuperior() {
    const el = document.getElementById('comp-resumo-superior');
    if (!el) return;
    const sel = getCenariosSelecionados();
    if (!sel.length) {
        // Mostrar 4 KPIs em skeleton quando há cenários mas nenhum está selecionado
        el.style.display = 'grid';
        el.innerHTML = `
            <div class="comp-resumo-card"><div class="comp-resumo-label">Mais econômico</div><div class="comp-resumo-valor" style="color:#9ca3af;">—</div><div class="comp-resumo-sub">Selecione cenários acima</div></div>
            <div class="comp-resumo-card"><div class="comp-resumo-label">Custo mensal médio</div><div class="comp-resumo-valor" style="color:#9ca3af;">—</div><div class="comp-resumo-sub">Entre as opções</div></div>
            <div class="comp-resumo-card"><div class="comp-resumo-label">Custo anual estimado</div><div class="comp-resumo-valor" style="color:#9ca3af;">—</div><div class="comp-resumo-sub">Selecione para calcular</div></div>
            <div class="comp-resumo-card"><div class="comp-resumo-label">Melhor custo por km</div><div class="comp-resumo-valor" style="color:#9ca3af;">—</div><div class="comp-resumo-sub">Uso mensal informado</div></div>
        `;
        return;
    }

    const horizonte = Number(document.getElementById('comp-horizonte')?.value || 24);
    const mensal = sel.map(c => c.custoMensal);
    const mediaGeral = mensal.reduce((a, b) => a + b, 0) / mensal.length;
    const maisEconomico = sel.reduce((a, b) => a.custoMensal < b.custoMensal ? a : b);
    const custosKmValidos = sel
        .map(c => ({ c, custoKm: calcularCustoPorKmCenario(c) }))
        .filter(item => Number.isFinite(item.custoKm) && item.custoKm > 0);
    const melhorKm = custosKmValidos.length
        ? custosKmValidos.reduce((a, b) => a.custoKm <= b.custoKm ? a : b)
        : null;

    el.style.display = 'grid';
    el.innerHTML = `
        <div class="comp-resumo-card destaque">
            <div class="comp-resumo-label">Mais econômico</div>
            <div class="comp-resumo-valor destaque">${escapeHtml(maisEconomico.nome)}</div>
            <div class="comp-resumo-sub">${formatarMoeda(maisEconomico.custoMensal)} / mês</div>
        </div>
        <div class="comp-resumo-card">
            <div class="comp-resumo-label">Custo mensal médio</div>
            <div class="comp-resumo-valor">${formatarMoeda(mediaGeral)} / mês</div>
            <div class="comp-resumo-sub">Entre as ${sel.length} opções</div>
        </div>
        <div class="comp-resumo-card">
            <div class="comp-resumo-label">Custo anual estimado</div>
            <div class="comp-resumo-valor">${formatarMoeda(mediaGeral * 12)}</div>
            <div class="comp-resumo-sub">Horizonte ${horizonte}m: ${formatarMoeda(mediaGeral * horizonte)}</div>
        </div>
        <div class="comp-resumo-card">
            <div class="comp-resumo-label">Melhor custo por km</div>
            <div class="comp-resumo-valor">${melhorKm ? escapeHtml(melhorKm.c.nome) : '—'}</div>
            <div class="comp-resumo-sub">${melhorKm ? `${formatarMoeda(melhorKm.custoKm)} / km` : 'Sem km suficiente'}</div>
        </div>
    `;
}

function renderCardsComparacao() {
    const el = document.getElementById('comp-cards');
    if (!el) return;
    const sel = getCenariosSelecionados();

    if (!sel.length) {
        el.innerHTML = `<div class="veic-empty-state veic-empty-state--inline" style="grid-column:1/-1"><p class="veic-empty-sub">Selecione cenários acima para comparar lado a lado.</p></div>`;
        renderDetalheOpcaoSelecionada();
        return;
    }

    el.innerHTML = sel.map(c => {
        const ativoGlobal = isCenarioAtivo(c.tipo, c.id);
        const statusComparacao = statusCenarioComparacao(c, sel);
        const custoKm = calcularCustoPorKmCenario(c);
        const itensHtml = c.itens.slice(0, 4).map(i => `
            <div class="comp-card-item-linha">
                <span class="comp-card-item-nome">${escapeHtml(i.nome)}</span>
                <span class="comp-card-item-valor">${formatarMoeda(i.valor)}</span>
            </div>
        `).join('');

        const editAction = c.tipo === 'VEICULO'
            ? `onclick="abrirModalEditar(${c.id})"`
            : c.tipo === 'ASSINATURA'
                ? `onclick="abrirModalAssinaturaEditar(${c.id})"`
                : `onclick="abrirModalAppEditar(${c.id})"`;

        const tipoRaw = c.tipo === 'VEICULO'
            ? (c.raw?.tipo || 'carro')
            : c.tipo === 'TRANSPORTE_APP'
                ? 'app'
                : 'assinatura';

        return `
            <div class="comp-card${ativoGlobal ? ' ativo-global' : ''}">
                ${ativoGlobal ? '<span class="comp-card-badge-ativo">Opção selecionada</span>' : ''}
                <div class="comp-card-visual comp-card-visual--${tipoRaw}">
                    ${renderImagemModalidade(c)}
                </div>
                <div class="comp-card-body">
                    <div class="comp-card-tipo">${escapeHtml(labelTipoCenario(c))}</div>
                    <div class="comp-card-nome">${escapeHtml(c.nome)}</div>
                    <div class="comp-card-sub">${escapeHtml(c.subLabel)}</div>
                    <div class="comp-card-status">${escapeHtml(statusComparacao)}</div>
                </div>
                <div class="comp-card-kpi">
                    <div class="comp-card-custo-label">Custo mensal estimado</div>
                    <div class="comp-card-custo-valor">${formatarMoeda(c.custoMensal)}</div>
                    <div class="comp-card-custo-anual">Anual: ${formatarMoeda(c.custoAnual)}</div>
                    <div class="comp-card-custo-km">${custoKm ? `${formatarMoeda(custoKm)} / km` : 'Custo/km indisponível'}</div>
                </div>
                <div class="comp-card-itens">${itensHtml || '<span class="small-note">Sem detalhamento configurado.</span>'}</div>
                <div class="comp-card-acoes">
                    <button class="btn btn-secondary btn-sm" ${editAction}>Editar</button>
                    ${!ativoGlobal ? `<button class="btn btn-primary btn-sm" onclick="definirCenarioAtivo('${c.tipo}', ${c.id})">Selecionar esta opção</button>` : `<button class="btn btn-secondary btn-sm" disabled>Opção selecionada</button>`}
                    <button class="btn btn-secondary btn-sm" onclick="ativarAba('efetivacao'); selecionarCenarioEfetivacao('${c.tipo}', ${c.id})">Efetivar</button>
                </div>
            </div>
        `;
    }).join('');
    renderDetalheOpcaoSelecionada();
}

function renderDetalheOpcaoSelecionada() {
    const el = document.getElementById('comp-detalhe-selecionado');
    if (!el) return;
    const sel = getCenariosSelecionados();
    const ativoSelecionado = sel.find(c => isCenarioAtivo(c.tipo, c.id));
    const ativoGeral = cenarioAtivoState.tipo
        ? todosOsCenarios.find(c => c.tipo === cenarioAtivoState.tipo && Number(c.id) === Number(cenarioAtivoState.id))
        : null;
    const c = ativoSelecionado || ativoGeral || sel[0];

    if (!c) {
        el.style.display = 'none';
        el.innerHTML = '';
        return;
    }

    const recorrentes = c.itens.filter(i => /combust|assinatura|app|transporte|mensal/i.test(i.nome));
    const periodicas = c.itens.filter(i => /ipva|seguro|licenciamento|manuten|revis|pneu|oleo|óleo/i.test(i.nome));
    const rec = isCenarioAtivo(c.tipo, c.id) ? (cenarioAtivoState.recorrencia || null) : null;
    const meio = rec?.meio_pagamento || cenarioAtivoState.meio_pagamento || null;
    const cartaoTexto = rec?.cartao_id
        ? `Cartão #${rec.cartao_id}${rec.categoria_cartao_id ? ` · Categoria do Cartão #${rec.categoria_cartao_id}` : ''}`
        : 'Nenhum lançamento no cartão configurado';
    const pagamentoHtml = meio && meio !== 'cartao'
        ? `<span class="comp-payment-line">${renderFormaPagamentoMobilidade(meio, { size: 'sm', showLabel: true })}<span class="comp-payment-note">recorrencia ${rec ? 'configurada' : 'nao criada'}</span></span>`
        : escapeHtml('Nenhum pagamento PIX/boleto/conta configurado');

    const lista = (itens, vazio) => itens.length
        ? itens.map(i => `<div class="comp-detalhe-linha"><span>${escapeHtml(i.nome)}</span><strong>${formatarMoeda(i.valor)}</strong></div>`).join('')
        : `<div class="comp-detalhe-vazio">${escapeHtml(vazio)}</div>`;

    el.style.display = '';
    el.innerHTML = `
        <div class="comp-detalhe-header">
            <div>
                <h3>Detalhamento da opção selecionada</h3>
                <p>${escapeHtml(labelTipoCenario(c))} · ${escapeHtml(c.nome)}</p>
            </div>
            <div class="comp-detalhe-total">
                <span>Total mensal</span>
                <strong>${formatarMoeda(c.custoMensal)}</strong>
            </div>
        </div>
        <div class="comp-detalhe-grid">
            <section class="comp-detalhe-card">
                <h4>Despesas recorrentes mensais</h4>
                ${lista(recorrentes, 'Sem recorrências mensais configuradas.')}
            </section>
            <section class="comp-detalhe-card">
                <h4>Despesas periódicas</h4>
                ${lista(periodicas, 'Sem despesas periódicas configuradas.')}
            </section>
            <section class="comp-detalhe-card">
                <h4>Lançamentos no cartão</h4>
                <div class="comp-detalhe-vazio">${escapeHtml(cartaoTexto)}</div>
            </section>
            <section class="comp-detalhe-card">
                <h4>Pagamentos PIX/boleto/conta</h4>
                <div class="comp-detalhe-vazio">${pagamentoHtml}</div>
            </section>
        </div>
    `;
}

function renderTabelaComparativa() {
    const wrap = document.getElementById('comp-tabela-wrap');
    const tabela = document.getElementById('comp-tabela');
    if (!wrap || !tabela) return;

    const sel = getCenariosSelecionados();
    if (sel.length < 2) { wrap.style.display = 'none'; return; }

    wrap.style.display = '';
    const menores = {};
    const atributos = ['custoMensal', 'custoAnual'];
    atributos.forEach(k => {
        const vals = sel.map(c => c[k]);
        menores[k] = Math.min(...vals);
    });

    const custoKm = sel.map(c => calcularCustoPorKmCenario(c));
    const menoresCustoKm = custoKm.filter(v => v !== null);
    const menorKm = menoresCustoKm.length ? Math.min(...menoresCustoKm) : null;

    const cabecalho = `<thead><tr>
        <th>Atributo</th>
        ${sel.map(c => `<th>${escapeHtml(c.nome)}</th>`).join('')}
    </tr></thead>`;

    const linhas = [
        { label: 'Custo mensal', key: 'custoMensal', fmt: formatarMoeda },
        { label: 'Custo anual', key: 'custoAnual', fmt: formatarMoeda },
    ];

    const linhaKm = `<tr>
        <td>Custo/km</td>
        ${custoKm.map(v => {
            if (v === null) return `<td class="small-note">—</td>`;
            const melhor = menorKm !== null && Math.abs(v - menorKm) < 0.001;
            return `<td class="${melhor ? 'melhor' : ''}">${v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2 })}/km</td>`;
        }).join('')}
    </tr>`;

    const corpo = `<tbody>
        ${linhas.map(({ label, key, fmt }) => `<tr>
            <td>${label}</td>
            ${sel.map(c => {
                const val = c[key];
                const melhor = val === menores[key];
                return `<td class="${melhor ? 'melhor' : ''}">${fmt(val)}</td>`;
            }).join('')}
        </tr>`).join('')}
        ${linhaKm}
        <tr>
            <td>Tipo</td>
            ${sel.map(c => `<td>${escapeHtml(labelTipoCenario(c))}</td>`).join('')}
        </tr>
    </tbody>`;

    tabela.innerHTML = cabecalho + corpo;
}

async function definirCenarioAtivo(tipo, id) {
    // VEIC-2B: todos os tipos passam pelo modal de ativação (banco).
    await abrirModalAtivacaoMobilidade(tipo, id);
}

// ================================================================
// VEIC-2: Modal de ativação de modalidade de mobilidade
// ================================================================

let _ativacaoPrevia = null;

async function abrirModalAtivacaoMobilidade(tipo, origemId) {
    const modal = document.getElementById('modal-ativar-mobilidade');
    if (!modal) {
        // Fallback: fluxo legado se o modal ainda não estiver no template
        await salvarCenarioAtivo(tipo, origemId);
        renderCardsComparacao();
        renderResumoSuperior();
        return;
    }

    // Popular cartões
    const selCartao = document.getElementById('ativar-mob-cartao-id');
    if (selCartao && !cartoesCacheGlobal) {
        try {
            const r = await fetch(API_CARTOES);
            const d = await r.json();
            cartoesCacheGlobal = extrairListaApi(d).filter(c => c.tipo === 'Agregador' || c.ativo !== false);
        } catch (e) { cartoesCacheGlobal = []; }
    }
    if (selCartao) {
        selCartao.innerHTML = '<option value="">— Nenhum —</option>' +
            (cartoesCacheGlobal || []).map(c => `<option value="${c.id}">${escapeHtml(c.nome)}</option>`).join('');
    }

    // Popular categorias de despesa
    const selCat = document.getElementById('ativar-mob-categoria-id');
    if (selCat && selCat.options.length <= 1) {
        try {
            const r = await fetch(API_CATEGORIAS);
            const d = await r.json();
            const cats = d.success ? (d.data || []) : [];
            selCat.innerHTML = '<option value="">— Padrão (Mobilidade) —</option>' +
                cats.map(c => `<option value="${c.id}">${escapeHtml(c.nome)}</option>`).join('');
        } catch (e) { /* mantém opções existentes */ }
    }

    document.getElementById('ativar-mob-tipo').value = tipo;
    document.getElementById('ativar-mob-origem-id').value = origemId;
    document.getElementById('ativar-mob-resultado').innerHTML = '';
    _ativacaoPrevia = null;

    // Ajustar rótulos conforme tipo
    const tituloEl = document.getElementById('ativar-mob-titulo');
    const meioLabel = document.getElementById('ativar-mob-meio-label');
    const recLabel = document.getElementById('ativar-mob-criar-recorrencia-label');
    if (tipo === 'VEICULO') {
        if (tituloEl) tituloEl.textContent = 'Ativar veículo próprio';
        if (meioLabel) meioLabel.textContent = 'Meio de pagamento do combustível';
        if (recLabel) recLabel.textContent = 'Criar recorrência mensal de combustível';
    } else if (tipo === 'TRANSPORTE_APP') {
        if (tituloEl) tituloEl.textContent = 'Ativar transporte por app';
        if (meioLabel) meioLabel.textContent = 'Meio de pagamento do app';
        if (recLabel) recLabel.textContent = 'Criar recorrência mensal de transporte por app';
    } else if (tipo === 'ASSINATURA') {
        if (tituloEl) tituloEl.textContent = 'Ativar assinatura de mobilidade';
        if (meioLabel) meioLabel.textContent = 'Meio de pagamento da assinatura';
        if (recLabel) recLabel.textContent = 'Criar recorrência mensal de assinatura';
    }

    modal.style.display = 'flex';
}

function fecharModalAtivacaoMobilidade() {
    const modal = document.getElementById('modal-ativar-mobilidade');
    if (modal) modal.style.display = 'none';
}

async function previsualizarAtivacaoMobilidade() {
    const tipo = document.getElementById('ativar-mob-tipo')?.value;
    const origemId = document.getElementById('ativar-mob-origem-id')?.value;
    const meio = document.getElementById('ativar-mob-meio')?.value || '';
    const cartaoId = document.getElementById('ativar-mob-cartao-id')?.value || '';
    const categoriaId = document.getElementById('ativar-mob-categoria-id')?.value || '';
    const dataInicio = document.getElementById('ativar-mob-data-inicio')?.value || '';
    const criarRec = document.getElementById('ativar-mob-criar-recorrencia')?.checked !== false;

    const divResultado = document.getElementById('ativar-mob-resultado');
    if (divResultado) divResultado.innerHTML = '<span style="color:#6b7280;font-size:0.85rem;">Calculando prévia…</span>';

    try {
        const resp = await fetch(`${API_VEICULOS}/mobilidade/previsualizar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tipo_modalidade: tipo,
                origem_id: origemId ? Number(origemId) : null,
                meio_pagamento: meio || null,
                cartao_id: cartaoId ? Number(cartaoId) : null,
                categoria_id: categoriaId ? Number(categoriaId) : null,
                data_inicio: dataInicio || null,
                criar_recorrencia: criarRec,
            }),
        });
        const data = await resp.json();
        if (!data.success) {
            if (divResultado) divResultado.innerHTML = `<span style="color:#ef4444;">${escapeHtml(data.error)}</span>`;
            return;
        }
        _ativacaoPrevia = { ...data.data, meio_pagamento: meio, cartao_id: cartaoId, categoria_id: categoriaId, data_inicio: dataInicio, criar_recorrencia: criarRec };
        _renderizarPreviaAtivacao(data.data, divResultado);
    } catch (e) {
        if (divResultado) divResultado.innerHTML = `<span style="color:#ef4444;">Erro: ${escapeHtml(String(e))}</span>`;
    }
}

function _renderizarPreviaAtivacao(previa, container) {
    if (!container) return;
    const rec = previa.recorrencia;
    const avisos = previa.avisos || [];
    const categoriaCartaoSelect = document.getElementById('ativar-mob-categoria-cartao-id');
    const categoriaCartaoNome = categoriaCartaoSelect?.selectedOptions?.[0]?.textContent?.trim();
    const fmtBrl = v => v != null ? 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2 }) : '—';

    let html = `<div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px;font-size:0.85rem;">`;
    html += `<div style="font-weight:600;margin-bottom:8px;">Prévia da ativação — ${escapeHtml(previa.nome_origem || '')}</div>`;

    if (rec) {
        html += `<div style="background:#f0fdf4;border-radius:6px;padding:8px;margin-bottom:8px;">`;
        html += `<div style="font-weight:500;color:#16a34a;">Recorrência mensal que será criada</div>`;
        html += `<div>${escapeHtml(rec.nome)}</div>`;
        html += `<div>Valor: <strong>${fmtBrl(rec.valor)}</strong></div>`;
        html += `<div>Categoria do Cartão: ${rec.categoria_cartao_id ? `<strong>${escapeHtml(categoriaCartaoNome || rec.categoria_cartao_nome || String(rec.categoria_cartao_id))}</strong>` : '<span style="color:#9ca3af;">não configurada</span>'}</div>`;
        html += `</div>`;
    } else {
        html += `<div style="color:#6b7280;margin-bottom:8px;">Nenhuma recorrência mensal será criada.</div>`;
    }

    if (previa.despesas_previstas?.length) {
        html += `<div style="font-weight:500;margin-bottom:4px;">Continuam como Despesa Prevista:</div>`;
        html += `<ul style="margin:0 0 8px 16px;padding:0;">${previa.despesas_previstas.map(d => `<li>${escapeHtml(d)}</li>`).join('')}</ul>`;
    }

    avisos.forEach(a => {
        html += `<div style="color:#d97706;background:#fffbeb;border-radius:4px;padding:4px 8px;margin-bottom:4px;">⚠ ${escapeHtml(a)}</div>`;
    });

    html += `</div>`;
    container.innerHTML = html;
}

async function confirmarAtivacaoMobilidade() {
    if (!_ativacaoPrevia) {
        await previsualizarAtivacaoMobilidade();
        if (!_ativacaoPrevia) return;
    }

    const tipo = document.getElementById('ativar-mob-tipo')?.value;
    const origemId = document.getElementById('ativar-mob-origem-id')?.value;
    const meio = document.getElementById('ativar-mob-meio')?.value || '';
    const cartaoId = document.getElementById('ativar-mob-cartao-id')?.value || '';
    const categoriaId = document.getElementById('ativar-mob-categoria-id')?.value || '';
    const dataInicio = document.getElementById('ativar-mob-data-inicio')?.value || '';
    const criarRec = document.getElementById('ativar-mob-criar-recorrencia')?.checked !== false;

    try {
        const resp = await fetch(`${API_VEICULOS}/mobilidade/ativar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tipo_modalidade: tipo,
                origem_id: origemId ? Number(origemId) : null,
                meio_pagamento: meio || null,
                cartao_id: cartaoId ? Number(cartaoId) : null,
                categoria_id: categoriaId ? Number(categoriaId) : null,
                data_inicio: dataInicio || null,
                criar_recorrencia: criarRec,
                confirmado: true,
            }),
        });
        const data = await resp.json();
        if (!data.success) {
            alert('Erro ao ativar: ' + data.error);
            return;
        }
        cenarioAtivoState = {
            tipo,
            id: Number(origemId),
            recorrencia: data.data?.recorrencia || null,
            meio_pagamento: data.data?.cenario?.meio_pagamento || meio || null,
            cartao_id: data.data?.cenario?.cartao_id || null,
            categoria_cartao_id: data.data?.cenario?.categoria_cartao_id || null,
        };
        _sincronizarMobilidadeAtivaLocal(tipo, Number(origemId));
        salvarCaminhosAtivosLocal();
        fecharModalAtivacaoMobilidade();
        renderCardsComparacao();
        renderResumoSuperior();
        await renderizarConfiguracao();
    } catch (e) {
        alert('Erro: ' + String(e));
    }
}

async function carregarCategoriaCartaoParaMobilidade() {
    const selCartao = document.getElementById('ativar-mob-cartao-id');
    const cartaoId = selCartao?.value;
    const categoriaId = document.getElementById('ativar-mob-categoria-id')?.value;
    const selCC = document.getElementById('ativar-mob-categoria-cartao-id');
    if (!selCC) return;
    if (!cartaoId) { selCC.innerHTML = '<option value="">—</option>'; return; }
    try {
        const r = await fetch(`/api/cartoes/${cartaoId}/categorias-limite?ativo=true`);
        const d = await r.json();
        const itens = d.success ? (d.data || []).filter(l => l.ativo !== false) : [];
        selCC.innerHTML = '<option value="">— Nenhuma —</option>' +
            itens.map(l => `<option value="${l.categoria_cartao_id}">${escapeHtml(l.categoria_cartao_nome || String(l.categoria_cartao_id))}</option>`).join('');
    } catch (e) { selCC.innerHTML = '<option value="">—</option>'; }
}

function atualizarAvisoCategoriaCartaoMobilidade(mensagem, tipo = 'neutral', prefixo = 'ativar-mob') {
    const campo = document.getElementById(`${prefixo}-categoria-cartao-id`);
    const info = document.getElementById(`${prefixo}-categoria-cartao-info`);
    if (campo && tipo !== 'resolved') campo.value = '';
    if (!info) return;
    info.textContent = mensagem;
    info.classList.remove('is-resolved', 'is-warning');
    if (tipo === 'resolved') info.classList.add('is-resolved');
    if (tipo === 'warning') info.classList.add('is-warning');
}

async function carregarCategoriaCartaoParaMobilidade() {
    const cartaoId = document.getElementById('ativar-mob-cartao-id')?.value;
    const categoriaId = document.getElementById('ativar-mob-categoria-id')?.value;
    const campo = document.getElementById('ativar-mob-categoria-cartao-id');
    if (!campo) return;

    if (!cartaoId || !categoriaId) {
        atualizarAvisoCategoriaCartaoMobilidade('Resolvida automaticamente pela Categoria de Despesa.', 'neutral', 'ativar-mob');
        return;
    }

    try {
        const r = await fetch(`/api/categorias-cartao/resolver?categoria_id=${encodeURIComponent(categoriaId)}&cartao_id=${encodeURIComponent(cartaoId)}`);
        const data = await r.json();
        const resolucao = data.data || data;
        if (data.success && resolucao.categoria_cartao_id) {
            campo.value = String(resolucao.categoria_cartao_id);
            atualizarAvisoCategoriaCartaoMobilidade(
                resolucao.aviso || `Categoria do Cartao resolvida automaticamente: ${resolucao.categoria_cartao_nome || ''}`,
                'resolved',
                'ativar-mob'
            );
        } else {
            atualizarAvisoCategoriaCartaoMobilidade(
                resolucao.aviso || 'Categoria do Cartao nao configurada para esta Categoria de Despesa.',
                'warning',
                'ativar-mob'
            );
        }
    } catch (e) {
        console.warn('Categoria do Cartao nao carregada:', e.message);
        atualizarAvisoCategoriaCartaoMobilidade('Categoria do Cartao nao configurada para esta Categoria de Despesa.', 'warning', 'ativar-mob');
    }
}

// ================================================================
// BLOCO 2 — CONFIGURAÇÃO
// ================================================================

let confSubtabAtiva = 'veiculo';

function ativarConfSubtab(nome) {
    confSubtabAtiva = nome;
    ['veiculo', 'assinatura', 'app'].forEach(t => {
        const btn = document.getElementById(`conf-subtab-${t}`);
        const painel = document.getElementById(`conf-painel-${t}`);
        if (btn) btn.classList.toggle('active', t === nome);
        if (painel) painel.style.display = t === nome ? '' : 'none';
    });
}

async function renderizarConfiguracao() {
    await construirTodosOsCenarios(caminhosVeiculos || [], caminhosApps || []);
    renderConfVeiculos();
    renderConfAssinaturas();
    renderConfApps();
    renderConfResumoLateral();
}

function renderConfResumoLateral() {
    const el = document.getElementById('conf-resumo-mensal');
    if (!el) return;

    // Encontra o cenário ativo para mostrar resumo
    const c = todosOsCenarios.find(c => isCenarioAtivo(c.tipo, c.id));
    if (!c) {
        el.innerHTML = `<div class="conf-vazio-card" style="padding:20px 12px;"><p class="conf-vazio-sub">Selecione um cenário ativo para ver o resumo de custos.</p></div>`;
        return;
    }

    const itens = c.itens.length ? c.itens : [{ nome: 'Custo mensal', valor: c.custoMensal }];
    const total = c.custoMensal;

    el.innerHTML = `
        <div class="conf-resumo-linha" style="padding:2px 0 6px;font-size:0.78rem;color:#6b7280;">${escapeHtml(c.nome)}</div>
        ${itens.map(i => `
            <div class="conf-resumo-linha">
                <span class="conf-resumo-linha-label">${escapeHtml(i.nome)}</span>
                <span class="conf-resumo-linha-valor">${formatarMoeda(i.valor)}</span>
            </div>
        `).join('')}
        <div class="conf-resumo-total">
            <span>Total mensal</span>
            <span class="valor">${formatarMoeda(total)}</span>
        </div>
    `;
}

function renderConfVeiculos() {
    const el = document.getElementById('conf-veiculos-lista');
    if (!el) return;
    const lista = caminhosVeiculos || [];
    if (!lista.length) {
        el.innerHTML = `
            <div class="conf-vazio-card">
                <div class="conf-vazio-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 17h14M7 17l2.5-8h5L17 17M9 13h6"/><circle cx="8" cy="19" r="1"/><circle cx="16" cy="19" r="1"/></svg>
                </div>
                <h4 class="conf-vazio-titulo">Nenhum veículo cadastrado</h4>
                <p class="conf-vazio-sub">Cadastre pelo menos um veículo para iniciar a comparação de custos.</p>
                <button class="btn btn-primary btn-sm" style="margin-top:8px;" onclick="abrirModalNovo()">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="width:13px;height:13px;margin-right:4px;"><path d="M12 5v14M5 12h14"/></svg>
                    Novo veículo
                </button>
            </div>
        `;
        return;
    }
    el.innerHTML = lista.map(v => {
        const ativo = isCenarioAtivo('VEICULO', v.id);
        const custo = custoMensalConsolidado?.VEICULO?.[v.id] || calcularCustoMensalVeiculoLocal(v, false);
        return `
            <div class="conf-item${ativo ? ' cenario-ativo-global' : ''}">
                <div class="conf-item-thumb">${renderImagemModalidade({ tipo: 'VEICULO', raw: v, nome: v.nome }, 'conf-item-image')}</div>
                <div class="conf-item-info">
                    <div class="conf-item-nome">${escapeHtml(v.nome)} <span class="card-badge ${v.status === 'ATIVO' ? 'status-ativo' : 'status-simulado'}">${escapeHtml(v.status)}</span></div>
                    <div class="conf-item-sub">${escapeHtml(v.tipo)} · ${escapeHtml(v.combustivel)} · ${v.autonomia_km_l} km/L</div>
                </div>
                <div class="conf-item-custo">${formatarMoeda(custo)}/mês</div>
                <div class="conf-item-acoes">
                    <button class="row-action-button" onclick="abrirModalEditar(${v.id})" title="Editar" aria-label="Editar">${veiculosIcon('edit')}</button>
                    <button class="row-action-button" onclick="toggleProjecoes(${v.id})" title="Projeções" aria-label="Projeções">${veiculosIcon('eye')}</button>
                    <button class="row-action-button" onclick="abrirModalFinanciamento(${v.id})" title="Financiamento" aria-label="Financiamento">${veiculosIcon('file')}</button>
                    <button class="row-action-button" onclick="abrirModalManutencaoKm(${v.id})" title="Manutenção" aria-label="Manutenção">${veiculosIcon('clock')}</button>
                    <button class="row-action-button danger" onclick="deletarVeiculo(${v.id}, '${escapeAttr(v.nome)}')" title="Excluir" aria-label="Excluir">${veiculosIcon('trash')}</button>
                </div>
            </div>
            <div id="projecoes-${v.id}" class="projecoes-wrap" style="display:none;">
                <div class="projecoes-header">
                    <strong>Despesas previstas</strong>
                    <span class="small-note">Não são lançamentos reais.</span>
                </div>
                <div class="projecoes-actions">
                    <button class="row-action-button" onclick="abrirModalFinanciamento(${v.id})" title="Financiamento" aria-label="Financiamento">${veiculosIcon('file')}</button>
                    <button class="row-action-button" onclick="abrirModalManutencaoKm(${v.id})" title="Manutencao por km" aria-label="Manutencao por km">${veiculosIcon('clock')}</button>
                    ${v.status === 'SIMULADO' ? `<button class="row-action-button success" onclick="converterVeiculo(${v.id})" title="Converter para ativo" aria-label="Converter para ativo">${veiculosIcon('check')}</button>` : ''}
                </div>
                <div class="projecoes-body"><p class="loading">Carregando projeções...</p></div>
            </div>
        `;
    }).join('');
}

function renderConfAssinaturas() {
    const el = document.getElementById('conf-assinaturas-lista');
    if (!el) return;
    const lista = caminhosAssinaturas || [];
    if (!lista.length) {
        el.innerHTML = `
            <div class="conf-vazio-card">
                <div class="conf-vazio-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 16h16M6 16l2-7h8l2 7M9 9V6h6v3"/><circle cx="8" cy="19" r="1"/><circle cx="16" cy="19" r="1"/></svg>
                </div>
                <h4 class="conf-vazio-titulo">Nenhuma assinatura cadastrada</h4>
                <p class="conf-vazio-sub">Cadastre um carro por assinatura para comparar contrato mensal com veículo próprio e app/táxi.</p>
                <button class="btn btn-primary btn-sm" style="margin-top:8px;" onclick="abrirModalAssinaturaNovo()">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="width:13px;height:13px;margin-right:4px;"><path d="M12 5v14M5 12h14"/></svg>
                    Nova assinatura
                </button>
            </div>
        `;
        return;
    }
    el.innerHTML = lista.map(a => {
        const ativo = isCenarioAtivo('ASSINATURA', a.id);
        return `
            <div class="conf-item${ativo ? ' cenario-ativo-global' : ''}">
                <div class="conf-item-thumb">${renderImagemModalidade({ tipo: 'ASSINATURA', raw: a, nome: a.nome }, 'conf-item-image')}</div>
                <div class="conf-item-info">
                    <div class="conf-item-nome">${escapeHtml(a.nome || 'Carro por Assinatura')} <span class="card-badge ${a.status === 'ATIVO' ? 'status-ativo' : 'status-simulado'}">${escapeHtml(a.status || 'ATIVO')}</span></div>
                    <div class="conf-item-sub">Contrato mensal · recorrência ao ativar</div>
                </div>
                <div class="conf-item-custo">${formatarMoeda(a.valor_mensal || 0)}/mês</div>
                <div class="conf-item-acoes">
                    <button class="row-action-button" onclick="abrirModalAssinaturaEditar(${a.id})" title="Editar" aria-label="Editar">${veiculosIcon('edit')}</button>
                    <button class="row-action-button success" onclick="abrirModalAtivacaoMobilidade('ASSINATURA', ${a.id})" title="Selecionar" aria-label="Selecionar">${veiculosIcon('check')}</button>
                </div>
            </div>
        `;
    }).join('');
}

function renderConfApps() {
    const el = document.getElementById('conf-apps-lista');
    if (!el) return;
    const lista = caminhosApps || [];
    if (!lista.length) {
        el.innerHTML = `
            <div class="conf-vazio-card">
                <div class="conf-vazio-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="20" rx="2"/><path d="M12 18h.01"/></svg>
                </div>
                <h4 class="conf-vazio-titulo">Nenhum cenário de app cadastrado</h4>
                <p class="conf-vazio-sub">Cadastre um cenário de transporte por app (Uber, 99, etc.) para comparar com veículo próprio.</p>
                <button class="btn btn-primary btn-sm" style="margin-top:8px;" onclick="abrirModalAppNovo()">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="width:13px;height:13px;margin-right:4px;"><path d="M12 5v14M5 12h14"/></svg>
                    Novo cenário de app
                </button>
            </div>
        `;
        return;
    }
    el.innerHTML = lista.map(c => {
        const ativo = isCenarioAtivo('TRANSPORTE_APP', c.id);
        return `
            <div class="conf-item${ativo ? ' cenario-ativo-global' : ''}">
                <div class="conf-item-thumb">${renderImagemModalidade({ tipo: 'TRANSPORTE_APP', raw: c, nome: c.nome }, 'conf-item-image')}</div>
                <div class="conf-item-info">
                    <div class="conf-item-nome">${escapeHtml(c.nome || 'Transporte por App')}</div>
                    <div class="conf-item-sub">${Number(c.km_mensal_estimado || 0).toLocaleString('pt-BR')} km/mês · ${formatarMoeda(c.preco_medio_por_km || 0)} /km</div>
                </div>
                <div class="conf-item-custo">${formatarMoeda(c.valor_mensal || 0)}/mês</div>
                <div class="conf-item-acoes">
                    <button class="row-action-button" onclick="abrirModalAppEditar(${c.id})" title="Editar" aria-label="Editar">${veiculosIcon('edit')}</button>
                    <button class="row-action-button" onclick="toggleProjecoesApp(${c.id})" title="Projeções" aria-label="Projeções">${veiculosIcon('eye')}</button>
                    <button class="row-action-button danger" onclick="removerCaminhoApp(${c.id}, '${escapeAttr(c.nome || 'App')}')" title="Excluir" aria-label="Excluir">${veiculosIcon('trash')}</button>
                </div>
            </div>
            <div class="projecoes-wrap" id="app-projecoes-${c.id}" style="display:none;">
                <div class="projecoes-header">
                    <strong>Despesas previstas</strong>
                    <span class="small-note">Não são lançamentos reais.</span>
                </div>
                <div class="projecoes-body"><p class="loading">Carregando projeções...</p></div>
            </div>
        `;
    }).join('');
}

// ================================================================
// BLOCO 3 — EFETIVAÇÃO
// ================================================================

let efetCenarioTipo = null;
let efetCenarioId = null;
let efetProjecoes = [];

async function iniciarEfetivacao() {
    // Popular select de cenários
    const sel = document.getElementById('efet-cenario-select');
    if (!sel) return;

    const tipoLabel = (c) => labelTipoCenario(c);
    const opcoes = todosOsCenarios.map(c => {
        const label = `[${tipoLabel(c)}] ${c.nome} — ${formatarMoeda(c.custoMensal)}/mes`;
        const selected = (efetCenarioTipo === c.tipo && Number(efetCenarioId) === Number(c.id));
        return `<option value="${c.tipo}|${c.id}" ${selected ? 'selected' : ''}>${label}</option>`;
    });
    sel.innerHTML = `<option value="">Selecione um cenario...</option>` + opcoes.join('');

    if (efetCenarioTipo && efetCenarioId) {
        await carregarEfetivacao();
    } else {
        _renderEfetivacaoBannerVazio();
        _renderEfetivacaoGradeVazia();
        document.getElementById('efet-resumo').style.display = 'none';
    }
}

function selecionarCenarioEfetivacao(tipo, id) {
    efetCenarioTipo = tipo;
    efetCenarioId = id;
    const sel = document.getElementById('efet-cenario-select');
    if (sel) sel.value = `${tipo}|${id}`;
    carregarEfetivacao();
}

function _renderEfetivacaoBannerVazio() {
    const banner = document.getElementById('efet-banner');
    if (banner) banner.innerHTML = `
        <div class="efet-banner efet-banner--vazio">
            <div class="efet-banner-icone">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 17h14M7 17l2.5-8h5L17 17M9 13h6"/><circle cx="8" cy="19" r="1"/><circle cx="16" cy="19" r="1"/></svg>
            </div>
            <div class="efet-banner-info">
                <h3 class="efet-banner-titulo">Nenhuma modalidade selecionada</h3>
                <p class="efet-banner-sub">Selecione um cenário no menu acima para revisar as despesas que serão geradas.</p>
            </div>
        </div>
    `;
}

function _renderEfetivacaoBanner(cenario) {
    const banner = document.getElementById('efet-banner');
    if (!banner || !cenario) return;
    const tipoLabel = labelTipoCenario(cenario);
    banner.innerHTML = `
        <div class="efet-banner">
            <div class="efet-banner-icone efet-banner-icone-img">${renderImagemModalidade(cenario, 'efet-banner-image')}</div>
            <div class="efet-banner-info">
                <h3 class="efet-banner-titulo">Modalidade ativa: ${escapeHtml(tipoLabel)} — ${escapeHtml(cenario.nome)}</h3>
                <p class="efet-banner-sub">Todas as despesas listadas abaixo serão criadas conforme a configuração escolhida.</p>
            </div>
            <div class="efet-banner-meta">
                <div class="efet-banner-meta-item">
                    <span class="efet-banner-meta-label">Custo mensal</span>
                    <span class="efet-banner-meta-valor">${formatarMoeda(cenario.custoMensal)}</span>
                </div>
            </div>
        </div>
    `;
}

function _renderEfetivacaoGradeVazia() {
    const secTitulo = document.getElementById('efet-secao-titulo');
    const nota = document.getElementById('efet-nota');
    const rodape = document.getElementById('efet-rodape');
    if (secTitulo) secTitulo.style.display = 'none';
    if (nota) nota.style.display = 'none';
    if (rodape) rodape.style.display = 'none';

    const el = document.getElementById('efet-grade');
    if (!el) return;
    el.innerHTML = `
        <div class="efet-grade-vazio">
            <table>
                <thead>
                    <tr>
                        <th>Tipo de custo</th>
                        <th>Descricao</th>
                        <th>Frequencia</th>
                        <th>Proximo lancamento</th>
                        <th>Destino financeiro</th>
                        <th>Forma de pagamento</th>
                        <th>Cartao / Conta</th>
                        <th style="text-align:right;">Valor estimado</th>
                        <th>Status</th>
                    </tr>
                </thead>
            </table>
            <div class="efet-grade-vazio-msg">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01M16 18h.01"/></svg>
                <p style="font-size:0.9rem;font-weight:600;color:#374151;margin:0;">Nenhum cenario selecionado para efetivacao</p>
                <p style="font-size:0.83rem;color:#6b7280;margin:0;">Selecione um cenario na aba Comparacao para revisar as despesas que serao criadas.</p>
                <button class="btn btn-secondary btn-sm" style="margin-top:8px;" onclick="ativarAba('comparacao')">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="width:13px;height:13px;margin-right:4px;"><path d="M19 12H5M12 5l-7 7 7 7"/></svg>
                    Voltar para Comparacao
                </button>
            </div>
        </div>
    `;
}

async function carregarEfetivacao() {
    const sel = document.getElementById('efet-cenario-select');
    const val = sel?.value || '';

    if (!val) {
        document.getElementById('efet-resumo').style.display = 'none';
        _renderEfetivacaoBannerVazio();
        _renderEfetivacaoGradeVazia();
        return;
    }

    const [tipo, idStr] = val.split('|');
    efetCenarioTipo = tipo;
    efetCenarioId = Number(idStr);

    // Mostrar banner com dados do cenário
    const cenario = todosOsCenarios.find(c => c.tipo === tipo && Number(c.id) === Number(idStr));
    _renderEfetivacaoBanner(cenario);

    document.getElementById('efet-grade').innerHTML = `<p class="loading" style="padding:16px;">Carregando projecoes...</p>`;

    try {
        let url;
        if (tipo === 'VEICULO') {
            url = `${API_VEICULOS}/${efetCenarioId}/projecoes?meses=24`;
        } else if (tipo === 'TRANSPORTE_APP') {
            url = `${API_MOBILIDADE_APP}/${efetCenarioId}/projecoes?meses=24`;
        } else {
            efetProjecoes = [];
            renderEfetivacaoResumo();
            renderEfetivacaoGrade();
            const nota = document.getElementById('efet-nota');
            const rodape = document.getElementById('efet-rodape');
            if (nota) nota.style.display = 'none';
            if (rodape) rodape.style.display = 'none';
            return;
        }
        const resp = await fetch(url);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao carregar projecoes');

        efetProjecoes = data.data || [];
        projecoesIndex = {};
        efetProjecoes.forEach(p => {
            projecoesIndex[p.id] = { tipo_evento: _normalizarTipoEvento(p) || null };
        });

        renderEfetivacaoResumo();
        renderEfetivacaoGrade();

        const nota = document.getElementById('efet-nota');
        const rodape = document.getElementById('efet-rodape');
        if (nota) nota.style.display = efetProjecoes.length ? 'flex' : 'none';
        if (rodape) rodape.style.display = efetProjecoes.length ? 'flex' : 'none';
    } catch (e) {
        console.error(e);
        document.getElementById('efet-grade').innerHTML = `<div class="efet-grade-vazio"><div class="efet-grade-vazio-msg"><p>Erro ao carregar: ${escapeHtml(e.message)}</p></div></div>`;
    }
}

function renderEfetivacaoResumo() {
    const el = document.getElementById('efet-resumo');
    if (!el) return;

    const previstas = efetProjecoes.filter(p => p.status === 'PREVISTA');
    const confirmadas = efetProjecoes.filter(p => p.status === 'CONFIRMADA');
    const adiadas = efetProjecoes.filter(p => p.status === 'ADIADA');
    const ignoradas = efetProjecoes.filter(p => p.status === 'IGNORADA');

    const totalPrevisto = previstas.reduce((a, p) => a + Number(p.valor_previsto || 0), 0);

    el.style.display = 'grid';
    el.innerHTML = `
        <div class="efet-resumo-card">
            <div class="efet-resumo-label">Total previsto</div>
            <div class="efet-resumo-valor">${formatarMoeda(totalPrevisto)}</div>
            <div class="efet-resumo-sub">${previstas.length} despesa(s) PREVISTA</div>
        </div>
        <div class="efet-resumo-card">
            <div class="efet-resumo-label">Confirmadas</div>
            <div class="efet-resumo-valor">${confirmadas.length}</div>
            <div class="efet-resumo-sub">Já convertidas em lançamento</div>
        </div>
        <div class="efet-resumo-card">
            <div class="efet-resumo-label">Adiadas</div>
            <div class="efet-resumo-valor">${adiadas.length}</div>
            <div class="efet-resumo-sub">Aguardando nova data</div>
        </div>
        <div class="efet-resumo-card">
            <div class="efet-resumo-label">Ignoradas</div>
            <div class="efet-resumo-valor">${ignoradas.length}</div>
            <div class="efet-resumo-sub">Descartadas manualmente</div>
        </div>
    `;
}

function renderEfetivacaoGrade() {
    const el = document.getElementById('efet-grade');
    const secTitulo = document.getElementById('efet-secao-titulo');
    if (!el) return;

    if (!efetProjecoes.length) {
        if (secTitulo) secTitulo.style.display = 'none';
        el.innerHTML = `
            <div class="efet-grade-vazio">
                <table><thead><tr>
                    <th>Tipo de custo</th><th>Descricao</th><th>Frequencia</th>
                    <th>Proximo lancamento</th><th>Destino financeiro</th>
                    <th>Forma de pagamento</th><th>Cartao / Conta</th>
                    <th style="text-align:right;">Valor estimado</th><th>Status</th>
                </tr></thead></table>
                <div class="efet-grade-vazio-msg">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
                    <p style="font-size:0.9rem;font-weight:600;color:#374151;margin:0;">Nenhuma despesa prevista para este cenario.</p>
                    <p style="font-size:0.83rem;color:#6b7280;margin:0;">Configure custos no cadastro do cenario para gerar projecoes.</p>
                </div>
            </div>
        `;
        return;
    }

    if (secTitulo) secTitulo.style.display = '';

    const _frequencia = (p) => {
        const t = _normalizarTipoEvento(p);
        if (['COMBUSTIVEL', 'TRANSPORTE_APP'].includes(t)) return 'Recorrência';
        if (t.includes('PARCELA')) return 'Parcela mensal';
        if (['IPVA', 'SEGURO', 'LICENCIAMENTO'].includes(t)) return 'Anual';
        return 'Despesa prevista';
    };

    const _destinoFinanceiro = (p) => {
        const t = _normalizarTipoEvento(p);
        if (['COMBUSTIVEL', 'TRANSPORTE_APP'].includes(t)) return 'Recorrência';
        if (t.includes('PARCELA')) return 'Lançamento no cartão';
        return 'Despesa Prevista';
    };

    const linhas = efetProjecoes.map(p => {
        const data = p.data_atual_prevista || p.data_prevista;
        const mes = formatarMesAno(data);
        const tipo = _rotuloDetalheTipo(p);
        const catNome = p.categoria?.nome || `Cat. #${p.categoria_id}`;
        const valor = formatarMoeda(p.valor_previsto);
        const status = String(p.status || '').toLowerCase();
        const badgeClass = { prevista: 'prevista', confirmada: 'confirmada', adiada: 'adiada', ignorada: 'ignorada' }[status] || 'prevista';
        const freq = _frequencia(p);
        const destino = _destinoFinanceiro(p);
        const formaPagamento = p.meio_pagamento || p.forma_pagamento || p.meio || null;
        const formaPagamentoHtml = formaPagamento
            ? renderFormaPagamentoMobilidade(formaPagamento, { size: 'sm', showLabel: true })
            : '<span class="small-note">—</span>';

        let acoes = `<span class="small-note">—</span>`;
        if (p.status === 'PREVISTA') {
            acoes = `
                <div class="row-actions">
                    <button class="row-action-button success" onclick="confirmarPrevista(${p.id}, ${JSON.stringify({ id: p.id, descricao: tipo, valor: p.valor_previsto, data: data, categoria: catNome, categoria_id: p.categoria_id, origem: 'Mobilidade', origem_tipo: p.origem_tipo, tipo_evento: _normalizarTipoEvento(p) }).replace(/"/g, '&quot;')})" title="Confirmar e gerar lancamento" aria-label="Confirmar">${veiculosIcon('check')}</button>
                    <button class="row-action-button" onclick="abrirModalAdiar(${p.id}, '${escapeAttr(data)}')" title="Adiar" aria-label="Adiar">${veiculosIcon('clock')}</button>
                    <button class="row-action-button danger" onclick="ignorarPrevista(${p.id})" title="Ignorar" aria-label="Ignorar">${veiculosIcon('remove')}</button>
                </div>
            `;
        }

        return `<tr>
            <td>${escapeHtml(tipo)}</td>
            <td>${escapeHtml(catNome)}</td>
            <td><span class="small-note">${escapeHtml(freq)}</span></td>
            <td>${mes}</td>
            <td><span class="small-note">${escapeHtml(destino)}</span></td>
            <td>${formaPagamentoHtml}</td>
            <td>—</td>
            <td style="text-align:right;font-weight:700;">${valor}</td>
            <td>
                <span class="efet-status-badge ${badgeClass}">${escapeHtml(p.status)}</span>
                ${p.status === 'PREVISTA' ? acoes : ''}
            </td>
        </tr>`;
    }).join('');

    el.innerHTML = `
        <div class="efet-grade">
            <table>
                <thead>
                    <tr>
                        <th>Tipo de custo</th>
                        <th>Descricao</th>
                        <th>Frequencia</th>
                        <th>Proximo lancamento</th>
                        <th>Destino financeiro</th>
                        <th>Forma de pagamento</th>
                        <th>Cartao / Conta</th>
                        <th style="text-align:right;">Valor estimado</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>${linhas}</tbody>
            </table>
        </div>
    `;
}

// ================================================================
// MODAL DE CONFIRMAÇÃO COM MEIO DE PAGAMENTO
// ================================================================

let _confirmarDadosPrevista = null;

async function abrirModalConfirmar(despesaId, dadosPrevista) {
    _confirmarDadosPrevista = dadosPrevista || null;
    document.getElementById('confirmar-despesa-id').value = despesaId;

    // Preview
    const preview = document.getElementById('confirmar-preview');
    if (dadosPrevista) {
        const origem = [dadosPrevista.origem || 'Mobilidade', dadosPrevista.origem_tipo, dadosPrevista.tipo_evento]
            .filter(Boolean)
            .join(' · ');
        preview.innerHTML = `
            <div class="confirmar-preview-top">
                <span class="confirmar-preview-pill">Mobilidade</span>
                <strong>${escapeHtml(dadosPrevista.descricao || 'Despesa prevista')}</strong>
            </div>
            <div class="confirmar-preview-grid">
                <div><span>Valor</span><strong>${formatarMoeda(dadosPrevista.valor || 0)}</strong></div>
                <div><span>Data prevista</span><strong>${formatarMesAno(dadosPrevista.data || '')}</strong></div>
                <div><span>Categoria de despesa</span><strong>${escapeHtml(dadosPrevista.categoria || '—')}</strong></div>
                <div><span>Origem</span><strong>${escapeHtml(origem || 'Mobilidade')}</strong></div>
            </div>
        `;
        // Pré-preenche data de vencimento
        const dataInput = document.getElementById('confirmar-data-vencimento');
        if (dataInput && dadosPrevista.data) {
            dataInput.value = String(dadosPrevista.data).slice(0, 10);
        }
    } else {
        preview.innerHTML = `<div class="confirmar-preview-top"><span class="confirmar-preview-pill">Mobilidade</span><strong>Despesa prevista #${despesaId}</strong></div>`;
        const dataInput = document.getElementById('confirmar-data-vencimento');
        if (dataInput) dataInput.value = new Date().toISOString().slice(0, 10);
    }

    // Reset meio de pagamento
    const meiSel = document.getElementById('confirmar-meio');
    if (meiSel) meiSel.value = '';
    toggleConfirmarCartao();

    // Habilitar botão
    const btn = document.getElementById('btn-confirmar-submit');
    if (btn) btn.disabled = false;

    document.getElementById('modal-confirmar-prevista').style.display = 'block';
}

function fecharModalConfirmar() {
    document.getElementById('modal-confirmar-prevista').style.display = 'none';
    _confirmarDadosPrevista = null;
}

function toggleConfirmarCartao() {
    const meio = document.getElementById('confirmar-meio')?.value;
    const wrap = document.getElementById('wrap-confirmar-cartao');
    const wrapItem = document.getElementById('wrap-confirmar-categoria-cartao');
    if (!wrap) return;
    if (meio === 'cartao') {
        wrap.style.display = '';
        carregarCartoesSelect();
    } else {
        wrap.style.display = 'none';
        if (wrapItem) wrapItem.style.display = 'none';
        const selItem = document.getElementById('confirmar-categoria-cartao-id');
        if (selItem) selItem.innerHTML = '<option value="">— Nenhuma —</option>';
    }
}

async function carregarCartoesSelect() {
    if (cartoesCacheGlobal) {
        preencherSelectCartoes(cartoesCacheGlobal);
        return;
    }
    try {
        const resp = await fetch(API_CARTOES);
        const data = await resp.json();
        cartoesCacheGlobal = extrairListaApi(data).filter(c => c.ativo !== false);
        preencherSelectCartoes(cartoesCacheGlobal);
    } catch (e) {
        console.error(e);
        const sel = document.getElementById('confirmar-cartao-id');
        if (sel) sel.innerHTML = `<option value="">Erro ao carregar cartões</option>`;
    }
}

function preencherSelectCartoes(cartoes) {
    const sel = document.getElementById('confirmar-cartao-id');
    if (!sel) return;
    sel.innerHTML = `<option value="">Selecione o cartão...</option>` +
        (cartoes || []).map(c => `<option value="${c.id}">${escapeHtml(c.nome)}</option>`).join('');
}

async function carregarCategoriasCartaoConfirmacao(cartaoId) {
    const wrap = document.getElementById('wrap-confirmar-categoria-cartao');
    const sel = document.getElementById('confirmar-categoria-cartao-id');
    if (!wrap || !sel) return;

    if (!cartaoId) {
        wrap.style.display = 'none';
        sel.innerHTML = '<option value="">— Nenhuma —</option>';
        return;
    }

    try {
        const resp = await fetch(`${API_CARTOES}/${cartaoId}/categorias-limite?ativo=true`);
        const data = await resp.json();
        const itens = (data.success ? (data.data || []) : []).filter(i => i.ativo !== false);

        if (!itens.length) {
            wrap.style.display = '';
            sel.innerHTML = '<option value="">— Nenhuma categoria configurada —</option>';
            return;
        }

        sel.innerHTML = '<option value="">— Nenhuma —</option>' +
            itens.map(i => `<option value="${i.categoria_cartao_id || i.id}">${escapeHtml(i.categoria_cartao_nome || i.nome)}</option>`).join('');

        // Pré-selecionar "Mobilidade" se existir neste cartão
        const mob = itens.find(i => (i.categoria_cartao_nome || i.nome || '').toLowerCase() === 'mobilidade');
        if (mob) sel.value = String(mob.categoria_cartao_id || mob.id);

        wrap.style.display = '';
    } catch (e) {
        console.warn('Categorias do Cartao nao carregadas:', e.message);
        wrap.style.display = '';
        sel.innerHTML = '<option value="">— Nenhuma —</option>';
    }
}

async function carregarCategoriasCartaoConfirmacao(cartaoId) {
    const wrap = document.getElementById('wrap-confirmar-categoria-cartao');
    const campo = document.getElementById('confirmar-categoria-cartao-id');
    if (!wrap || !campo) return;
    wrap.style.display = cartaoId ? '' : 'none';

    const categoriaId = _confirmarDadosPrevista?.categoria_id;
    if (!cartaoId || !categoriaId) {
        atualizarAvisoCategoriaCartaoMobilidade('Resolvida automaticamente pela Categoria de Despesa.', 'neutral', 'confirmar');
        return;
    }

    try {
        const resp = await fetch(`/api/categorias-cartao/resolver?categoria_id=${encodeURIComponent(categoriaId)}&cartao_id=${encodeURIComponent(cartaoId)}`);
        const data = await resp.json();
        const resolucao = data.data || data;
        if (data.success && resolucao.categoria_cartao_id) {
            campo.value = String(resolucao.categoria_cartao_id);
            atualizarAvisoCategoriaCartaoMobilidade(
                resolucao.aviso || `Categoria do Cartao resolvida automaticamente: ${resolucao.categoria_cartao_nome || ''}`,
                'resolved',
                'confirmar'
            );
        } else {
            atualizarAvisoCategoriaCartaoMobilidade(
                resolucao.aviso || 'Categoria do Cartao nao configurada para esta Categoria de Despesa.',
                'warning',
                'confirmar'
            );
        }
    } catch (e) {
        console.warn('Categorias do Cartao nao carregadas:', e.message);
        atualizarAvisoCategoriaCartaoMobilidade('Categoria do Cartao nao configurada para esta Categoria de Despesa.', 'warning', 'confirmar');
    }
}

async function submitConfirmarPrevista() {
    const despesaId = document.getElementById('confirmar-despesa-id')?.value;
    const meio = document.getElementById('confirmar-meio')?.value;
    const cartaoId = document.getElementById('confirmar-cartao-id')?.value;
    const dataVenc = document.getElementById('confirmar-data-vencimento')?.value;
    const obs = document.getElementById('confirmar-observacao')?.value?.trim();

    if (!meio) { alert('Selecione o meio de pagamento.'); return; }
    if (meio === 'cartao' && !cartaoId) { alert('Selecione o cartão.'); return; }

    const btn = document.getElementById('btn-confirmar-submit');
    if (btn) btn.disabled = true;

    const payload = { meio_pagamento: meio };
    if (meio === 'cartao' && cartaoId) payload.cartao_id = Number(cartaoId);
    if (dataVenc) payload.data_vencimento = dataVenc;
    if (obs) payload.observacao = obs;
    if (_confirmarDadosPrevista?.categoria_id) payload.categoria_id = Number(_confirmarDadosPrevista.categoria_id);

    try {
        const resp = await fetch(`${API_DESPESAS_PREVISTAS}/${despesaId}/confirmar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao confirmar');

        const criada = data.data?.entidade_criada;
        let msg = 'Despesa prevista confirmada.';
        if (criada) {
            msg += criada.tipo === 'lancamento_agregado'
                ? `\n\nLançamento no cartão criado: ${criada.descricao} — ${formatarMoeda(criada.valor)}`
                : `\nConta gerada: ${criada.descricao} — ${formatarMoeda(criada.valor)} (venc. ${criada.data_vencimento})`;
        }
        alert(msg);
        fecharModalConfirmar();

        // Recarregar conforme aba ativa
        if (abaAtiva === 'efetivacao') {
            await carregarEfetivacao();
        } else {
            await carregarVeiculos();
            await carregarCaminhosApp();
        }
    } catch (e) {
        console.error(e);
        alert('Erro ao confirmar: ' + e.message);
        if (btn) btn.disabled = false;
    }
}

// Fechar modal confirmar ao clicar fora
window.addEventListener('click', function(event) {
    if (event.target === document.getElementById('modal-confirmar-prevista')) fecharModalConfirmar();
});

// ================================================================
// OVERRIDE DO DOMContentLoaded para carregar cenário ativo e aba inicial
// ================================================================

// O DOMContentLoaded original já existe e carrega veículos/apps.
// Estendemos ao final para inicializar abas após os dados carregarem.

const _originalInit = document.addEventListener;
(function _veic2Init() {
    // Aguarda carregamento dos dados (que ocorre no DOMContentLoaded original)
    // e então inicializa as abas e cenário ativo.
    document.addEventListener('DOMContentLoaded', async () => {
        await carregarCenarioAtivo();
        // Renderiza a aba ativa (comparação por padrão, já ativada pelo HTML)
        // Os dados de veículos/apps já são carregados pelo DOMContentLoaded original
        // Aqui apenas garantimos que as abas respondem após o carregamento inicial.
        // A função ativarAba('comparacao') será chamada após carregarVeiculos/carregarCaminhosApp terminarem.
    });
})();
