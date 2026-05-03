const API_RECORRENCIAS = '/api/recorrencias';
const API_CONSORCIOS = '/api/consorcios/';
const API_CATEGORIAS = '/api/categorias';
const API_CARTOES = '/api/cartoes';

let estadoRecorrencias = {
    recorrencias: [],
    consorcios: [],
    categorias: [],
    cartoes: [],
    modoEdicao: null
};

document.addEventListener('DOMContentLoaded', async () => {
    await carregarDadosBase();
    await carregarRecorrencias();
    alternarTipoCadastro();
    alternarFrequencia();
});

async function carregarDadosBase() {
    const [categoriasResp, cartoesResp] = await Promise.all([
        fetch(`${API_CATEGORIAS}?ativo=true`).then(r => r.json()).catch(() => ({ success: false, data: [] })),
        fetch(API_CARTOES).then(r => r.json()).catch(() => ({ success: false, data: [] }))
    ]);

    estadoRecorrencias.categorias = categoriasResp.success ? (categoriasResp.data || []) : [];
    estadoRecorrencias.cartoes = cartoesResp.success ? (cartoesResp.data || []) : [];

    preencherSelectCategorias();
    preencherSelectCartoes();
}

function preencherSelectCategorias() {
    const selects = [
        document.getElementById('categoria-id'),
        document.getElementById('filtro-categoria')
    ].filter(Boolean);

    selects.forEach(select => {
        const primeiraOpcao = select.id === 'filtro-categoria' ? '<option value="">Todas</option>' : '<option value="">Selecione...</option>';
        select.innerHTML = primeiraOpcao + estadoRecorrencias.categorias
            .map(cat => `<option value="${cat.id}">${escapeHtml(cat.nome)}</option>`)
            .join('');
    });
}

function preencherSelectCartoes() {
    const select = document.getElementById('cartao-id');
    if (!select) return;

    select.innerHTML = '<option value="">Selecione...</option>' + estadoRecorrencias.cartoes
        .map(cartao => `<option value="${cartao.id}">${escapeHtml(cartao.nome)}</option>`)
        .join('');
}

async function carregarCategoriasCartaoSelecionado() {
    const cartaoId = document.getElementById('cartao-id').value;
    const select = document.getElementById('categoria-cartao-id');
    if (!select) return;

    select.innerHTML = '<option value="">Resolver automaticamente</option>';
    if (!cartaoId) return;

    const response = await fetch(`${API_CARTOES}/${cartaoId}/categorias-limite?ativo=true`).then(r => r.json()).catch(() => ({ success: false, data: [] }));
    if (!response.success) return;

    select.innerHTML += (response.data || [])
        .map(item => `<option value="${item.categoria_cartao_id || item.id}">${escapeHtml(item.categoria_cartao_nome || item.nome)}</option>`)
        .join('');
}

async function carregarRecorrencias() {
    const [recResp, consResp] = await Promise.all([
        fetch(`${API_RECORRENCIAS}?status=todas`).then(r => r.json()).catch(() => ({ success: false, data: [] })),
        fetch(API_CONSORCIOS).then(r => r.json()).catch(() => ({ success: false, data: [] }))
    ]);

    estadoRecorrencias.recorrencias = recResp.success ? (recResp.data || []) : [];
    estadoRecorrencias.consorcios = consResp.success ? (consResp.data || []) : [];

    renderizarLista();
}

function obterItensUnificados() {
    const recorrencias = estadoRecorrencias.recorrencias.map(item => {
        const categoria = estadoRecorrencias.categorias.find(cat => String(cat.id) === String(item.categoria_id)) || null;
        return {
            origem: 'recorrencia',
            id: item.id,
            nome: item.nome,
            descricao: item.descricao,
            tipo: 'recorrencia_simples',
            tipoLabel: 'Despesa recorrente',
            frequencia: item.frequencia || item.tipo_recorrencia || 'mensal',
            proximoVencimento: item.proximo_vencimento,
            valor: item.valor,
            categoriaId: item.categoria_id,
            categoriaNome: item.categoria_nome || categoria?.nome || '-',
            categoriaIcone: item.categoria_icone || categoria?.icone || null,
            categoriaLogoUrl: item.categoria_logo_url || categoria?.logo_url || null,
            meioPagamento: item.meio_pagamento || null,
            status: item.ativo ? 'ativa' : 'inativa',
            statusLabel: item.ativo ? 'Ativa' : 'Inativa',
            raw: item
        };
    });

    const consorcios = estadoRecorrencias.consorcios.map(item => ({
        origem: 'consorcio',
        id: item.id,
        nome: item.nome,
        descricao: item.observacoes,
        tipo: 'consorcio',
        tipoLabel: 'Consorcio',
        frequencia: 'parcelas',
        proximoVencimento: item.mes_inicio,
        valor: item.valor_inicial,
        categoriaId: '',
        categoriaNome: '-',
        status: item.ativo ? 'ativa' : 'inativa',
        statusLabel: item.ativo ? 'Ativo' : 'Inativo',
        detalhe: `${item.numero_parcelas || 0} parcelas`,
        raw: item
    }));

    return [...recorrencias, ...consorcios];
}

function aplicarFiltrosRecorrencias() {
    renderizarLista();
}

function renderizarLista() {
    const container = document.getElementById('recorrencias-lista');
    const totalEl = document.getElementById('recorrencias-total');
    if (!container) return;

    const filtroTipo = document.getElementById('filtro-tipo').value;
    const filtroStatus = document.getElementById('filtro-status').value;
    const filtroFrequencia = document.getElementById('filtro-frequencia').value;
    const filtroCategoria = document.getElementById('filtro-categoria').value;

    let itens = obterItensUnificados();
    itens = itens.filter(item => {
        if (filtroTipo && item.tipo !== filtroTipo) return false;
        if (filtroStatus && item.status !== filtroStatus) return false;
        if (filtroFrequencia && item.frequencia !== filtroFrequencia) return false;
        if (filtroCategoria && String(item.categoriaId || '') !== filtroCategoria) return false;
        return true;
    });

    if (totalEl) {
        totalEl.textContent = `${itens.length} cadastro(s)`;
    }

    if (itens.length === 0) {
        container.innerHTML = '<p class="recorrencias-empty">Nenhuma recorrencia cadastrada para os filtros selecionados.</p>';
        return;
    }

    container.innerHTML = `
        <div class="recorrencias-table">
            <div class="recorrencias-header">
                <span>Descricao</span>
                <span>Tipo</span>
                <span>Frequencia</span>
                <span>Proximo venc.</span>
                <span>Valor</span>
                <span>Categoria</span>
                <span>Status</span>
                <span>Acoes</span>
            </div>
            ${itens.map(renderizarLinha).join('')}
        </div>
    `;
}

function renderizarLinha(item) {
    const valor = formatarMoeda(item.valor);
    const vencimento = item.proximoVencimento ? formatarData(item.proximoVencimento) : '-';
    const detalhe = item.detalhe || formatarFrequencia(item.frequencia, item.raw);
    const categoriaVisual = {
        nome: item.categoriaNome,
        icone: item.categoriaIcone,
        logo_url: item.categoriaLogoUrl
    };
    const categoriaVisualHtml = (typeof renderCategoryVisual === 'function' && (item.categoriaLogoUrl || item.categoriaIcone))
        ? renderCategoryVisual(categoriaVisual, { size: '12px', alt: item.categoriaNome })
        : '';

    return `
        <div class="recorrencias-row">
            <div class="recorrencias-title">
                <strong>${escapeHtml(item.nome)}</strong>
                <small>${escapeHtml(item.descricao || detalhe || '')}</small>
            </div>
            <span><span class="compact-pill">${escapeHtml(item.tipoLabel)}</span>${(typeof renderPaymentIcon === 'function' && item.meioPagamento) ? `<span class="inline-icon" style="opacity:0.6;margin-left:4px" title="${item.meioPagamento}">${renderPaymentIcon(item.meioPagamento, { size: '12px' })}</span>` : ''}</span>
            <span>${escapeHtml(detalhe)}</span>
            <span>${vencimento}</span>
            <span class="recorrencias-value">${valor}</span>
            <span class="icon-chip">${categoriaVisualHtml}${escapeHtml(item.categoriaNome)}</span>
            <span><span class="compact-pill">${escapeHtml(item.statusLabel)}</span></span>
            <span class="row-actions recorrencias-actions">
                <button class="row-action-button" type="button" onclick="editarRecorrencia('${item.origem}', ${item.id})" title="Editar" aria-label="Editar">
                    <span class="action-icon" aria-hidden="true">${iconeEditar()}</span>
                </button>
                <button class="row-action-button danger" type="button" onclick="inativarRecorrencia('${item.origem}', ${item.id})" title="Inativar" aria-label="Inativar">
                    <span class="action-icon" aria-hidden="true">${iconeInativar()}</span>
                </button>
            </span>
        </div>
    `;
}

function abrirFormularioRecorrencia() {
    estadoRecorrencias.modoEdicao = null;
    document.getElementById('form-recorrencia').reset();
    document.getElementById('recorrencia-id').value = '';
    document.getElementById('recorrencia-origem').value = '';
    document.getElementById('form-titulo').textContent = 'Nova Recorrencia';
    document.getElementById('tipo-cadastro').disabled = false;
    document.getElementById('secao-formulario').hidden = false;
    alternarTipoCadastro();
    alternarFrequencia();
    document.getElementById('nome').focus();
}

function fecharFormularioRecorrencia() {
    document.getElementById('secao-formulario').hidden = true;
    document.getElementById('tipo-cadastro').disabled = false;
    estadoRecorrencias.modoEdicao = null;
}

function alternarTipoCadastro() {
    const tipo = document.getElementById('tipo-cadastro').value;
    const isConsorcio = tipo === 'consorcio';
    const editandoConsorcio = isConsorcio && document.getElementById('recorrencia-id').value;
    const categoria = document.getElementById('categoria-id');

    document.querySelectorAll('.recorrencia-campo').forEach(el => {
        el.hidden = isConsorcio;
    });
    document.querySelectorAll('.consorcio-campos').forEach(el => {
        el.hidden = !isConsorcio;
    });
    if (categoria) {
        categoria.required = !editandoConsorcio;
    }
    alternarFrequencia();
}

function alternarFrequencia() {
    const tipo = document.getElementById('tipo-cadastro').value;
    const frequencia = document.getElementById('frequencia').value;
    const mostrarSemanal = tipo !== 'consorcio' && (frequencia === 'semanal' || frequencia === 'quinzenal');

    document.querySelectorAll('.recorrencia-semanal').forEach(el => {
        el.hidden = !mostrarSemanal;
    });
}

function alternarMeioPagamento() {
    const meio = document.getElementById('meio-pagamento').value;
    document.querySelectorAll('.recorrencia-cartao').forEach(el => {
        el.hidden = meio !== 'cartao';
    });
}

async function salvarRecorrencia(event) {
    event.preventDefault();

    const tipo = document.getElementById('tipo-cadastro').value;
    if (tipo === 'consorcio') {
        await salvarConsorcio();
    } else {
        await salvarRecorrenciaSimples();
    }
}

async function salvarRecorrenciaSimples() {
    const id = document.getElementById('recorrencia-id').value;
    const frequencia = document.getElementById('frequencia').value;
    const dados = {
        nome: document.getElementById('nome').value.trim(),
        descricao: document.getElementById('observacoes').value.trim(),
        valor: Number(document.getElementById('valor').value),
        categoria_id: Number(document.getElementById('categoria-id').value),
        data_vencimento: document.getElementById('data-vencimento').value || null,
        tipo_recorrencia: frequencia === 'quinzenal' ? 'semanal' : frequencia,
        frequencia_semanas: frequencia === 'quinzenal' ? 2 : 1,
        dia_semana: document.getElementById('dia-semana').value || null,
        meio_pagamento: document.getElementById('meio-pagamento').value || null,
        cartao_id: document.getElementById('cartao-id').value || null,
        categoria_cartao_id: document.getElementById('categoria-cartao-id').value || null
    };

    const response = await fetch(id ? `${API_RECORRENCIAS}/${id}` : API_RECORRENCIAS, {
        method: id ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dados)
    });
    const result = await response.json();
    if (!result.success) {
        alert(result.error || 'Erro ao salvar recorrencia');
        return;
    }

    fecharFormularioRecorrencia();
    await carregarRecorrencias();
}

async function salvarConsorcio() {
    const id = document.getElementById('recorrencia-id').value;
    const dados = {
        nome: document.getElementById('nome').value.trim(),
        valor_inicial: Number(document.getElementById('valor').value),
        categoria_id: Number(document.getElementById('categoria-id').value),
        numero_parcelas: Number(document.getElementById('numero-parcelas').value),
        mes_inicio: converterMesParaData(document.getElementById('mes-inicio').value),
        tipo_reajuste: document.getElementById('tipo-reajuste').value,
        valor_reajuste: Number(document.getElementById('valor-reajuste').value || 0),
        mes_contemplacao: converterMesParaData(document.getElementById('mes-contemplacao').value),
        valor_premio: document.getElementById('valor-premio').value ? Number(document.getElementById('valor-premio').value) : null,
        observacoes: document.getElementById('observacoes').value.trim()
    };

    const response = await fetch(id ? `${API_CONSORCIOS}${id}` : API_CONSORCIOS, {
        method: id ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dados)
    });
    const result = await response.json();
    if (!result.success) {
        alert(result.error || 'Erro ao salvar consorcio');
        return;
    }

    fecharFormularioRecorrencia();
    await carregarRecorrencias();
}

async function editarRecorrencia(origem, id) {
    abrirFormularioRecorrencia();
    document.getElementById('recorrencia-id').value = id;
    document.getElementById('recorrencia-origem').value = origem;
    document.getElementById('tipo-cadastro').value = origem === 'consorcio' ? 'consorcio' : 'recorrencia_simples';
    document.getElementById('tipo-cadastro').disabled = true;
    document.getElementById('form-titulo').textContent = origem === 'consorcio' ? 'Editar Consorcio' : 'Editar Recorrencia';
    alternarTipoCadastro();

    if (origem === 'consorcio') {
        const item = estadoRecorrencias.consorcios.find(c => Number(c.id) === Number(id));
        if (!item) return;
        document.getElementById('nome').value = item.nome || '';
        document.getElementById('valor').value = item.valor_inicial || '';
        document.getElementById('numero-parcelas').value = item.numero_parcelas || '';
        document.getElementById('mes-inicio').value = normalizarMes(item.mes_inicio);
        document.getElementById('tipo-reajuste').value = item.tipo_reajuste || 'nenhum';
        document.getElementById('valor-reajuste').value = item.valor_reajuste || '';
        document.getElementById('mes-contemplacao').value = normalizarMes(item.mes_contemplacao);
        document.getElementById('valor-premio').value = item.valor_premio || '';
        document.getElementById('observacoes').value = item.observacoes || '';
        return;
    }

    const item = estadoRecorrencias.recorrencias.find(r => Number(r.id) === Number(id));
    if (!item) return;
    document.getElementById('nome').value = item.nome || '';
    document.getElementById('observacoes').value = item.descricao || '';
    document.getElementById('valor').value = item.valor || '';
    document.getElementById('categoria-id').value = item.categoria_id || '';
    document.getElementById('data-vencimento').value = item.data_vencimento || '';
    document.getElementById('frequencia').value = item.frequencia || 'mensal';
    document.getElementById('dia-semana').value = item.dia_semana ?? '';
    document.getElementById('meio-pagamento').value = item.meio_pagamento || '';
    document.getElementById('cartao-id').value = item.cartao_id || '';
    alternarFrequencia();
    alternarMeioPagamento();
    if (item.meio_pagamento === 'cartao' && item.cartao_id) {
        await carregarCategoriasCartaoSelecionado();
        document.getElementById('categoria-cartao-id').value = item.categoria_cartao_id || '';
    }
}

async function inativarRecorrencia(origem, id) {
    const label = origem === 'consorcio' ? 'consorcio' : 'recorrencia';
    if (!confirm(`Inativar ${label}?`)) return;

    const url = origem === 'consorcio' ? `${API_CONSORCIOS}${id}` : `${API_RECORRENCIAS}/${id}`;
    const response = await fetch(url, { method: 'DELETE' });
    const result = await response.json();
    if (!result.success) {
        alert(result.error || `Erro ao inativar ${label}`);
        return;
    }
    await carregarRecorrencias();
}

function formatarFrequencia(frequencia, item) {
    if (frequencia === 'mensal') return 'Mensal';
    if (frequencia === 'semanal') return 'Semanal';
    if (frequencia === 'quinzenal') return 'Quinzenal';
    if (frequencia === 'anual') return 'Anual';
    if (frequencia === 'parcelas') return `${item?.numero_parcelas || 0} parcelas`;
    return frequencia || '-';
}

function formatarMoeda(valor) {
    return Number(valor || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarData(valor) {
    if (!valor) return '-';
    const partes = String(valor).slice(0, 10).split('-');
    if (partes.length !== 3) return valor;
    return `${partes[2]}/${partes[1]}/${partes[0]}`;
}

function converterMesParaData(valor) {
    return valor ? `${valor}-01` : null;
}

function normalizarMes(valor) {
    return valor ? String(valor).slice(0, 7) : '';
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function iconeEditar() {
    return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z"/></svg>';
}

function iconeInativar() {
    return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>';
}
