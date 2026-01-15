const API_VEICULOS = '/api/veiculos';
const API_CATEGORIAS = '/api/categorias';
const API_DESPESAS_PREVISTAS = '/api/despesas-previstas';
const API_INDEXADORES_TIPOS = '/api/indexadores/tipos';
const API_MOBILIDADE_APP = '/api/mobilidade-app';

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

let caminhosVeiculos = null;
let caminhosApps = null;

document.addEventListener('DOMContentLoaded', async () => {
    preencherMeses();
    carregarCaminhosAtivosLocal();
    await carregarCategorias();
    await carregarCaminhosApp();
    await carregarVeiculos();
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
            <div class="card-actions"></div>
        </div>
    `;
}

async function renderCaminhosGrid() {
    const container = document.getElementById('caminhos-lista');
    if (!container) return;

    if (caminhosVeiculos === null || caminhosApps === null) {
        container.innerHTML = `<p class="loading">Carregando caminhos...</p>`;
        atualizarResumoMobilidadeAtiva();
        return;
    }

    const listaVeiculos = caminhosVeiculos || [];
    const listaApps = caminhosApps || [];

    if (!listaVeiculos.length && !listaApps.length) {
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

        await renderCaminhosGrid();
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
    } catch (e) {
        console.error(e);
        caminhosApps = [];
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

            <div class="card-actions">
                <button class="btn btn-edit" onclick="abrirModalAppEditar(${c.id})">Editar</button>
                <button class="btn btn-secondary" onclick="toggleProjecoesApp(${c.id})">Projeções</button>
                <button class="btn btn-danger" onclick="removerCaminhoApp(${c.id}, '${escapeAttr(c.nome || 'Transporte por App')}')">Excluir</button>
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
                <button type="button" class="btn btn-danger btn-sm" onclick="removerPerfilApp(${idx})">Remover</button>
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
                        <button class="btn btn-primary btn-sm" onclick="confirmarPrevista(${p.id})">Confirmar</button>
                        <button class="btn btn-secondary btn-sm" onclick="abrirModalAdiar(${p.id}, '${escapeAttr(p.data_atual_prevista || p.data_prevista)}')">Adiar</button>
                        <button class="btn btn-danger btn-sm" onclick="ignorarPrevista(${p.id})">Ignorar</button>
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
                            <button class="btn btn-primary btn-sm" onclick="confirmarPrevista(${p.id})">Confirmar</button>
                            <button class="btn btn-secondary btn-sm" onclick="abrirModalAdiar(${p.id}, '${escapeAttr(p.data_atual_prevista || p.data_prevista)}')">Adiar</button>
                            <button class="btn btn-danger btn-sm" onclick="ignorarPrevista(${p.id})">Ignorar</button>
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
            <button class="btn btn-secondary btn-sm" onclick="abrirModalFinanciamento(${v.id})">Financiamento</button>
            <button class="btn btn-secondary btn-sm" onclick="abrirModalManutencaoKm(${v.id})">Manuten&ccedil;&atilde;o por km</button>
            ${v.status === 'SIMULADO'
                ? `<button class="btn btn-primary btn-sm" onclick="converterVeiculo(${v.id})">Converter - ATIVO</button>`
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

            <div class="card-actions">
                <button class="btn btn-edit" onclick="abrirModalEditar(${v.id})">Editar</button>
                <button class="btn btn-secondary" onclick="toggleProjecoes(${v.id})">Proje&ccedil;&otilde;es</button>
                <button class="btn btn-danger" onclick="deletarVeiculo(${v.id}, '${escapeAttr(v.nome)}')">Excluir</button>
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

    const tiposRegras = new Set((respMan?.success ? (respMan.data?.tipos_evento_regras || []) : []).map(t => String(t || '').toUpperCase()));
    const custoBase = calcularCustoMensalEstimado(respProj.data || [], 12, tiposRegras);
    const impactoManut = respMan?.success ? Number(respMan.data?.impacto_mensal_total || 0) : 0;
    return custoBase + (Number.isFinite(impactoManut) ? impactoManut : 0);
}

async function atualizarCustosMensais(veiculoIds) {
    const ids = (veiculoIds || []).filter(Boolean);
    await Promise.all(ids.map(async (id) => {
        const el = document.getElementById(`custo-mensal-${id}`);
        if (!el) return;
        const valorEl = el.querySelector('.custo-valor');
        try {
            const custo = await obterCustoMensalVeiculo(id);
            const fmt = Number(custo || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
            if (valorEl) valorEl.textContent = `${fmt} / mês`;
        } catch (e) {
            console.error(e);
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
                    <button class="btn btn-primary btn-sm" onclick="confirmarPrevista(${p.id})">Confirmar</button>
                    <button class="btn btn-secondary btn-sm" onclick="abrirModalAdiar(${p.id}, '${escapeAttr(p.data_atual_prevista || p.data_prevista)}')">Adiar</button>
                    <button class="btn btn-danger btn-sm" onclick="ignorarPrevista(${p.id})">Ignorar</button>
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
                        <button class="btn btn-primary btn-sm" onclick="confirmarPrevista(${p.id})">Confirmar</button>
                        <button class="btn btn-secondary btn-sm" onclick="abrirModalAdiar(${p.id}, '${escapeAttr(p.data_atual_prevista || p.data_prevista)}')">Adiar</button>
                        <button class="btn btn-danger btn-sm" onclick="ignorarPrevista(${p.id})">Ignorar</button>
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
                            <button class="btn btn-danger btn-sm" onclick="removerRegraKm(${veiculoId}, ${r.id})">Remover</button>
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
                        : `<button class="btn btn-primary btn-sm" onclick="gerarManutencaoKm(${veiculoId}, ${e.regra_id})">Gerar despesa prevista</button>`;
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

async function confirmarPrevista(despesaId) {
    if (!confirm('Confirmar esta despesa prevista?\n\nIsso não cria lançamento real automaticamente.')) return;
    try {
        const resp = await fetch(`${API_DESPESAS_PREVISTAS}/${despesaId}/confirmar`, { method: 'POST' });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Falha ao confirmar');
        alert(data.message || 'Confirmada');
        await carregarVeiculos();
    } catch (e) {
        console.error(e);
        alert('Erro ao confirmar: ' + e.message);
    }
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
