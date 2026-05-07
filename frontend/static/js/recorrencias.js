const API_RECORRENCIAS = '/api/recorrencias';
const API_CONSORCIOS = '/api/consorcios/';
const API_CATEGORIAS = '/api/categorias';
const API_CARTOES = '/api/cartoes';
const API_CONTAS_BANCARIAS = '/api/contas?status=ATIVO';

let estadoRecorrencias = {
    recorrencias: [],
    consorcios: [],
    categorias: [],
    cartoes: [],
    contasBancarias: [],
    modoEdicao: null
};

document.addEventListener('DOMContentLoaded', async () => {
    await carregarDadosBase();
    await carregarRecorrencias();
    prepararFormularioNovaRecorrencia();
    configurarCalculoPremioConsorcio();
});

async function carregarDadosBase() {
    const [categoriasResp, cartoesResp, contasResp] = await Promise.all([
        fetch(`${API_CATEGORIAS}?ativo=true`).then(r => r.json()).catch(() => ({ success: false, data: [] })),
        fetch(API_CARTOES).then(r => r.json()).catch(() => ({ success: false, data: [] })),
        fetch(API_CONTAS_BANCARIAS).then(r => r.json()).catch(() => ({ success: false, data: [] }))
    ]);

    estadoRecorrencias.categorias = categoriasResp.success ? (categoriasResp.data || []) : [];
    estadoRecorrencias.cartoes = cartoesResp.success ? (cartoesResp.data || []) : [];
    estadoRecorrencias.contasBancarias = contasResp.success ? (contasResp.data || []) : [];

    preencherSelectCategorias();
    preencherSelectCartoes();
    preencherSelectContasBancarias();
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

function preencherSelectContasBancarias() {
    const select = document.getElementById('conta-bancaria-id');
    if (!select) return;

    select.innerHTML = '<option value="">Selecione...</option>' + estadoRecorrencias.contasBancarias
        .map(conta => `<option value="${conta.id}">${escapeHtml(`${conta.nome || 'Conta'}${conta.instituicao ? ` (${conta.instituicao})` : ''}`)}</option>`)
        .join('');
}

async function carregarCategoriasCartaoSelecionado() {
    const cartaoId = document.getElementById('cartao-id')?.value;
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

function atualizarAvisoCategoriaCartaoRecorrencia(mensagem, tipo = 'neutral') {
    const campo = document.getElementById('categoria-cartao-id');
    const info = document.getElementById('categoria-cartao-info');
    if (campo && tipo !== 'resolved') campo.value = '';
    if (!info) return;
    info.textContent = mensagem;
    info.classList.remove('is-resolved', 'is-warning');
    if (tipo === 'resolved') info.classList.add('is-resolved');
    if (tipo === 'warning') info.classList.add('is-warning');
}

async function carregarCategoriasCartaoSelecionado() {
    await resolverCategoriaCartaoRecorrencia();
}

async function resolverCategoriaCartaoRecorrencia() {
    const cartaoId = document.getElementById('cartao-id')?.value;
    const categoriaId = document.getElementById('categoria-id')?.value;
    const campo = document.getElementById('categoria-cartao-id');
    if (!campo) return;

    if (!cartaoId || !categoriaId) {
        atualizarAvisoCategoriaCartaoRecorrencia('Resolvida automaticamente pela Categoria de Despesa.', 'neutral');
        return;
    }

    try {
        const response = await fetch(`/api/categorias-cartao/resolver?categoria_id=${encodeURIComponent(categoriaId)}&cartao_id=${encodeURIComponent(cartaoId)}`);
        const data = await response.json();
        const resolucao = data.data || data;
        if (data.success && resolucao.categoria_cartao_id) {
            campo.value = String(resolucao.categoria_cartao_id);
            atualizarAvisoCategoriaCartaoRecorrencia(
                resolucao.aviso || `Categoria do Cartao resolvida automaticamente: ${resolucao.categoria_cartao_nome || ''}`,
                'resolved'
            );
        } else {
            atualizarAvisoCategoriaCartaoRecorrencia(
                resolucao.aviso || 'Categoria do Cartao nao configurada para esta Categoria de Despesa.',
                'warning'
            );
        }
    } catch (error) {
        console.warn('Erro ao resolver Categoria do Cartao:', error);
        atualizarAvisoCategoriaCartaoRecorrencia('Categoria do Cartao nao configurada para esta Categoria de Despesa.', 'warning');
    }
}

async function carregarRecorrencias() {
    const [recResp, consResp] = await Promise.all([
        fetch(`${API_RECORRENCIAS}?status=todas`).then(r => r.json()).catch(() => ({ success: false, data: [] })),
        fetch(API_CONSORCIOS).then(r => r.json()).catch(() => ({ success: false, data: [] }))
    ]);

    estadoRecorrencias.recorrencias = recResp.success ? (recResp.data || []) : [];
    estadoRecorrencias.consorcios = consResp.success ? (consResp.data || []) : [];

    renderizarTelaRecorrencias();
}

async function recarregarRecorrencias() {
    await carregarDadosBase();
    await carregarRecorrencias();
}

function renderizarTelaRecorrencias() {
    const itens = obterItensUnificados();
    const filtrados = obterItensFiltrados(itens);
    renderizarCardsResumo(itens);
    renderizarAgendaPeriodo(itens);
    renderizarLista(filtrados);
    renderizarComposicao(itens);
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
            tipoLabel: 'Despesa',
            frequencia: item.frequencia || item.tipo_recorrencia || 'mensal',
            proximoVencimento: item.proximo_vencimento,
            valor: Number(item.valor || 0),
            categoriaId: item.categoria_id,
            categoriaNome: item.categoria_nome || categoria?.nome || '-',
            categoriaIcone: item.categoria_icone || categoria?.icone || null,
            categoriaLogoUrl: item.categoria_logo_url || categoria?.logo_url || null,
            meioPagamento: item.meio_pagamento || null,
            categoriaCartaoId: item.categoria_cartao_id || null,
            categoriaCartaoNome: item.categoria_cartao_nome || null,
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
        valor: Number(item.valor_inicial || 0),
        categoriaId: item.categoria_id || '',
        categoriaNome: item.categoria_nome || '-',
        status: item.ativo ? 'ativa' : 'inativa',
        statusLabel: item.ativo ? 'Ativo' : 'Inativo',
        detalhe: `${item.numero_parcelas || 0} parcelas`,
        raw: item
    }));

    return [...recorrencias, ...consorcios];
}

function obterItensFiltrados(itens) {
    const filtroTipo = document.getElementById('filtro-tipo')?.value || '';
    const filtroStatus = document.getElementById('filtro-status')?.value || '';
    const filtroFrequencia = document.getElementById('filtro-frequencia')?.value || '';
    const filtroCategoria = document.getElementById('filtro-categoria')?.value || '';
    const busca = normalizarBusca(document.getElementById('filtro-busca')?.value || '');

    return itens.filter(item => {
        if (filtroTipo && item.tipo !== filtroTipo) return false;
        if (filtroStatus && item.status !== filtroStatus) return false;
        if (filtroFrequencia && item.frequencia !== filtroFrequencia) return false;
        if (filtroCategoria && String(item.categoriaId || '') !== filtroCategoria) return false;
        if (busca && !normalizarBusca(`${item.nome} ${item.descricao || ''} ${item.categoriaNome}`).includes(busca)) return false;
        return true;
    });
}

function aplicarFiltrosRecorrencias() {
    renderizarTelaRecorrencias();
}

function renderizarCardsResumo(itens) {
    const ativas = itens.filter(item => item.status === 'ativa');
    const totalMensal = ativas.reduce((total, item) => total + valorMensalEstimado(item), 0);
    const proximos = obterEventosAgenda(ativas);
    const proximo = proximos[0] || null;
    const categorias = new Set(ativas.map(item => item.categoriaNome).filter(nome => nome && nome !== '-'));
    const categoriaTop = obterCategoriaMaisUsada(ativas);

    setText('kpi-ativas', ativas.length);
    setText('kpi-ativas-sub', `de ${itens.length} cadastradas`);
    setText('kpi-valor-mensal', formatarMoeda(totalMensal));
    setText('kpi-proxima-geracao', proximo ? `${proximo.dias} ${proximo.dias === 1 ? 'dia' : 'dias'}` : '-');
    setText('kpi-proxima-data', proximo ? `${formatarData(proximo.data)} (${formatarDiaSemana(proximo.data)})` : 'Sem data prevista');
    setText('kpi-categorias', categorias.size);
    setText('kpi-categoria-top', categoriaTop ? `mais usada: ${categoriaTop}` : 'Sem categoria dominante');
}

function renderizarAgendaPeriodo(itens) {
    const container = document.getElementById('agenda-periodo');
    if (!container) return;

    const eventos = obterEventosAgenda(itens.filter(item => item.status === 'ativa')).slice(0, 3);
    if (!eventos.length) {
        container.innerHTML = `
            <div class="recorrencias-empty">
                <strong>Nenhuma recorrencia prevista no periodo.</strong>
                <span>Cadastre uma recorrencia para automatizar previsoes.</span>
            </div>
        `;
        return;
    }

    container.innerHTML = eventos.map(evento => `
        <article class="agenda-item">
            <span class="agenda-icon" style="color:${corCategoria(evento.item.categoriaId)}">${renderizarIconeCategoria(evento.item, '22px')}</span>
            <div>
                <strong>${escapeHtml(evento.item.nome)}</strong>
                <small>${formatarData(evento.data)} (${formatarDiaSemana(evento.data)})</small>
            </div>
            <strong class="agenda-value">${formatarMoeda(evento.item.valor)}</strong>
            <span class="agenda-badge">${evento.dias} ${evento.dias === 1 ? 'dia' : 'dias'}</span>
        </article>
    `).join('');
}

function renderizarLista(itens) {
    const container = document.getElementById('recorrencias-lista');
    const totalEl = document.getElementById('recorrencias-total');
    if (!container) return;

    if (totalEl) {
        totalEl.textContent = `${itens.length} ${itens.length === 1 ? 'cadastro' : 'cadastros'} no total`;
    }

    if (itens.length === 0) {
        container.innerHTML = `
            <div class="recorrencias-empty">
                <strong>Nenhuma recorrencia cadastrada.</strong>
                <span>Cadastre uma recorrencia para automatizar previsoes.</span>
            </div>
        `;
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
        <div class="recorrencias-table-footer">
            <span>Mostrando 1 a ${itens.length} de ${itens.length} recorrencias</span>
            <span>Itens por pagina <strong>10</strong></span>
        </div>
    `;
}

function renderizarLinha(item) {
    const vencimento = item.proximoVencimento ? formatarData(item.proximoVencimento) : '-';
    const dias = item.proximoVencimento ? diasAte(item.proximoVencimento) : null;
    const detalhe = item.detalhe || formatarFrequencia(item.frequencia, item.raw);
    const categoriaVisualHtml = renderizarIconeCategoria(item, '16px');
    const meioPagamentoHtml = (window.FormasPagamentoUI?.renderFormaPagamento && item.meioPagamento)
        ? `<span class="inline-icon" title="${escapeHtml(item.meioPagamento)}">${window.FormasPagamentoUI.renderFormaPagamento(item.meioPagamento, { size: '13px', showLabel: false, className: 'recorrencia-payment-method' })}</span>`
        : '';

    return `
        <div class="recorrencias-row">
            <div class="recorrencias-title">
                <span class="row-category-icon" style="color:${corCategoria(item.categoriaId)}">${categoriaVisualHtml}</span>
                <span>
                    <strong>${escapeHtml(item.nome)}</strong>
                    <small>${escapeHtml(item.descricao || detalhe || '')}</small>
                </span>
            </div>
            <span><span class="recorrencias-pill type">${escapeHtml(item.tipoLabel)}</span>${meioPagamentoHtml}</span>
            <span>${escapeHtml(detalhe)}</span>
            <span>${vencimento}${dias !== null ? `<small class="next-days">(${dias} ${dias === 1 ? 'dia' : 'dias'})</small>` : ''}</span>
            <span class="recorrencias-value">${formatarMoeda(item.valor)}</span>
            <span class="categoria-cell"><i style="background:${corCategoria(item.categoriaId)}"></i>${escapeHtml(item.categoriaNome)}</span>
            <span><span class="recorrencias-pill ${item.status === 'ativa' ? 'active' : 'inactive'}">${escapeHtml(item.statusLabel)}</span></span>
            <span class="row-actions recorrencias-actions">
                <button class="row-action-button" type="button" onclick="editarRecorrencia('${item.origem}', ${item.id})" title="Editar" aria-label="Editar">${iconeEditar()}</button>
                <button class="row-action-button danger" type="button" onclick="inativarRecorrencia('${item.origem}', ${item.id})" title="Inativar" aria-label="Inativar">${iconeInativar()}</button>
            </span>
        </div>
    `;
}

function renderizarComposicao(itens) {
    const container = document.getElementById('recorrencias-composicao');
    if (!container) return;

    const ativas = itens.filter(item => item.status === 'ativa');
    if (!ativas.length) {
        container.innerHTML = '<div class="recorrencias-empty"><strong>Sem dados suficientes para composicao.</strong></div>';
        return;
    }

    const total = ativas.length;
    const porFrequencia = ['mensal', 'semanal', 'quinzenal', 'anual', 'parcelas'].map(freq => ({
        freq,
        label: formatarFrequencia(freq),
        count: ativas.filter(item => item.frequencia === freq).length
    })).filter(item => item.count > 0);
    container.innerHTML = `
        <div class="composition-layout">
            <div class="composition-donut" style="${gerarDonut(porFrequencia, total)}">
                <strong>${total}</strong>
                <span>Total</span>
            </div>
            <div class="composition-list">
                ${porFrequencia.map((item, index) => `
                    <div class="composition-line">
                        <span><i class="dot color-${index}"></i>${escapeHtml(item.label)}</span>
                        <strong>${item.count} (${Math.round((item.count / total) * 100)}%)</strong>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function abrirFormularioRecorrencia() {
    prepararFormularioNovaRecorrencia();
    document.getElementById('secao-formulario')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    document.getElementById('nome')?.focus();
}

function prepararFormularioNovaRecorrencia() {
    estadoRecorrencias.modoEdicao = null;
    document.getElementById('form-recorrencia')?.reset();
    setValue('recorrencia-id', '');
    setValue('recorrencia-origem', '');
    setText('form-titulo', 'Nova recorrencia');
    const tipo = document.getElementById('tipo-cadastro');
    if (tipo) {
        tipo.disabled = false;
        tipo.value = 'recorrencia_simples';
    }
    const ativo = document.getElementById('recorrencia-ativa');
    if (ativo) ativo.checked = true;
    alternarTipoCadastro();
    alternarFrequencia();
    alternarMeioPagamento();
}

function fecharFormularioRecorrencia() {
    prepararFormularioNovaRecorrencia();
}

function alternarTipoCadastro() {
    const tipo = document.getElementById('tipo-cadastro')?.value || 'recorrencia_simples';
    const isConsorcio = tipo === 'consorcio';
    const editandoConsorcio = isConsorcio && document.getElementById('recorrencia-id')?.value;
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
    alternarMeioPagamento();
    calcularValorPremioConsorcio();
}

function alternarFrequencia() {
    const tipo = document.getElementById('tipo-cadastro')?.value || 'recorrencia_simples';
    const frequencia = document.getElementById('frequencia')?.value || 'mensal';
    const mostrarSemanal = tipo !== 'consorcio' && (frequencia === 'semanal' || frequencia === 'quinzenal');

    document.querySelectorAll('.recorrencia-semanal').forEach(el => {
        el.hidden = !mostrarSemanal;
    });
}

function alternarMeioPagamento() {
    const meio = document.getElementById('meio-pagamento')?.value || '';
    const contaBancaria = document.getElementById('conta-bancaria-id');
    document.querySelectorAll('.recorrencia-cartao').forEach(el => {
        el.hidden = meio !== 'cartao';
    });
    document.querySelectorAll('.recorrencia-conta-bancaria').forEach(el => {
        el.hidden = meio !== 'debito_automatico';
    });
    if (contaBancaria) {
        contaBancaria.required = meio === 'debito_automatico';
        if (meio !== 'debito_automatico') contaBancaria.value = '';
    }
    if (meio !== 'cartao') {
        setValue('cartao-id', '');
        setValue('categoria-cartao-id', '');
        atualizarAvisoCategoriaCartaoRecorrencia('Resolvida automaticamente pela Categoria de Despesa.', 'neutral');
    }
    if (meio === 'cartao') resolverCategoriaCartaoRecorrencia();
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
        conta_bancaria_id: document.getElementById('conta-bancaria-id')?.value || null,
        ativo: document.getElementById('recorrencia-ativa')?.checked ?? true
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

    prepararFormularioNovaRecorrencia();
    await carregarRecorrencias();
}

async function salvarConsorcio() {
    const id = document.getElementById('recorrencia-id').value;
    const mesContemplacaoValor = document.getElementById('mes-contemplacao').value;
    const mesContemplacao = converterMesParaData(mesContemplacaoValor);
    calcularValorPremioConsorcio();
    const dados = {
        nome: document.getElementById('nome').value.trim(),
        valor_inicial: Number(document.getElementById('valor').value),
        categoria_id: Number(document.getElementById('categoria-id').value),
        numero_parcelas: Number(document.getElementById('numero-parcelas').value),
        mes_inicio: converterMesParaData(document.getElementById('mes-inicio').value, mesContemplacao),
        tipo_reajuste: document.getElementById('tipo-reajuste').value,
        valor_reajuste: Number(document.getElementById('valor-reajuste').value || 0),
        mes_contemplacao: mesContemplacao,
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

    prepararFormularioNovaRecorrencia();
    await carregarRecorrencias();
}

async function editarRecorrencia(origem, id) {
    prepararFormularioNovaRecorrencia();
    setValue('recorrencia-id', id);
    setValue('recorrencia-origem', origem);
    setValue('tipo-cadastro', origem === 'consorcio' ? 'consorcio' : 'recorrencia_simples');
    document.getElementById('tipo-cadastro').disabled = true;
    setText('form-titulo', origem === 'consorcio' ? 'Editar consorcio' : 'Editar recorrencia');
    alternarTipoCadastro();

    if (origem === 'consorcio') {
        const item = estadoRecorrencias.consorcios.find(c => Number(c.id) === Number(id));
        if (!item) return;
        setValue('nome', item.nome || '');
        setValue('valor', item.valor_inicial || '');
        setValue('categoria-id', item.categoria_id || '');
        setValue('numero-parcelas', item.numero_parcelas || '');
        setValue('mes-inicio', normalizarMes(item.mes_inicio));
        setValue('tipo-reajuste', item.tipo_reajuste || 'nenhum');
        setValue('valor-reajuste', item.valor_reajuste || '');
        setValue('mes-contemplacao', normalizarMes(item.mes_contemplacao));
        setValue('valor-premio', item.valor_premio || '');
        setValue('observacoes', item.observacoes || '');
        document.getElementById('recorrencia-ativa').checked = item.ativo !== false;
        calcularValorPremioConsorcio();
        document.getElementById('nome')?.focus();
        return;
    }

    const item = estadoRecorrencias.recorrencias.find(r => Number(r.id) === Number(id));
    if (!item) return;
    setValue('nome', item.nome || '');
    setValue('observacoes', item.descricao || '');
    setValue('valor', item.valor || '');
    setValue('categoria-id', item.categoria_id || '');
    setValue('data-vencimento', item.data_vencimento || '');
    setValue('frequencia', item.frequencia || 'mensal');
    setValue('dia-semana', item.dia_semana ?? '');
    setValue('meio-pagamento', item.meio_pagamento || '');
    setValue('cartao-id', item.cartao_id || '');
    setValue('conta-bancaria-id', item.conta_bancaria_id || '');
    document.getElementById('recorrencia-ativa').checked = item.ativo !== false;
    alternarFrequencia();
    alternarMeioPagamento();
    if (item.meio_pagamento === 'cartao' && item.cartao_id) {
        await carregarCategoriasCartaoSelecionado();
        setValue('categoria-cartao-id', item.categoria_cartao_id || '');
        resolverCategoriaCartaoRecorrencia();
    }
    document.getElementById('nome')?.focus();
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

function obterEventosAgenda(itens) {
    return itens
        .map(item => ({ item, data: item.proximoVencimento, dias: diasAte(item.proximoVencimento) }))
        .filter(evento => evento.data && evento.dias !== null && evento.dias >= 0)
        .sort((a, b) => a.dias - b.dias);
}

function valorMensalEstimado(item) {
    const valor = Number(item.valor || 0);
    if (item.frequencia === 'semanal') return valor * 4;
    if (item.frequencia === 'quinzenal') return valor * 2;
    if (item.frequencia === 'anual') return valor / 12;
    return valor;
}

function obterCategoriaMaisUsada(itens) {
    const contagem = new Map();
    itens.forEach(item => {
        if (!item.categoriaNome || item.categoriaNome === '-') return;
        contagem.set(item.categoriaNome, (contagem.get(item.categoriaNome) || 0) + 1);
    });
    return [...contagem.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || null;
}

function gerarDonut(items, total) {
    const cores = ['#2563eb', '#7c3aed', '#22c55e', '#f59e0b', '#64748b'];
    let cursor = 0;
    const partes = items.map((item, index) => {
        const inicio = cursor;
        const fim = cursor + (item.count / total) * 100;
        cursor = fim;
        return `${cores[index % cores.length]} ${inicio}% ${fim}%`;
    });
    return `background: conic-gradient(${partes.join(', ')});`;
}

function corCategoria(categoriaId) {
    const categoria = estadoRecorrencias.categorias.find(cat => String(cat.id) === String(categoriaId));
    return categoria?.cor || '#2563eb';
}

function renderizarIconeCategoria(item, size) {
    const categoria = estadoRecorrencias.categorias.find(cat => String(cat.id) === String(item.categoriaId)) || {
        nome: item.categoriaNome,
        icone: item.categoriaIcone,
        logo_url: item.categoriaLogoUrl
    };
    if (typeof renderCategoryVisual === 'function') {
        return renderCategoryVisual(categoria, { size, alt: item.categoriaNome || item.nome });
    }
    return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20 12 12 20 4 12V4h8l8 8Z"/><path d="M8.5 8.5h.01"/></svg>';
}

function diasAte(valor) {
    if (!valor) return null;
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    const data = new Date(`${String(valor).slice(0, 10)}T00:00:00`);
    if (Number.isNaN(data.getTime())) return null;
    return Math.ceil((data - hoje) / 86400000);
}

function formatarFrequencia(frequencia, item) {
    if (frequencia === 'mensal') return 'Mensal';
    if (frequencia === 'semanal') return 'Semanal';
    if (frequencia === 'quinzenal') return 'A cada 2 semanas';
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

function formatarDiaSemana(valor) {
    const data = new Date(`${String(valor).slice(0, 10)}T00:00:00`);
    if (Number.isNaN(data.getTime())) return '';
    return data.toLocaleDateString('pt-BR', { weekday: 'short' }).replace('.', '');
}

function configurarCalculoPremioConsorcio() {
    ['valor', 'numero-parcelas', 'mes-inicio', 'mes-contemplacao', 'tipo-reajuste', 'valor-reajuste'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('input', calcularValorPremioConsorcio);
        el.addEventListener('change', calcularValorPremioConsorcio);
    });
}

function converterMesParaData(valor, dataBase = null) {
    if (valor === null || valor === undefined || String(valor).trim() === '') return null;

    const texto = String(valor).trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(texto)) return texto.slice(0, 10);
    if (/^\d{4}-\d{2}$/.test(texto)) return `${texto}-01`;
    if (/^\d{1,2}\/\d{4}$/.test(texto)) {
        const [mes, ano] = texto.split('/');
        const mesNumero = Number(mes);
        if (mesNumero < 1 || mesNumero > 12) return null;
        return `${ano}-${String(mesNumero).padStart(2, '0')}-01`;
    }
    if (/^\d{1,2}$/.test(texto)) {
        const mesNumero = Number(texto);
        if (mesNumero < 1 || mesNumero > 12) return null;
        const baseTexto = dataBase === null || dataBase === undefined ? '' : String(dataBase).trim();
        const base = baseTexto && !/^\d{1,2}$/.test(baseTexto)
            ? converterMesParaData(baseTexto)
            : new Date().toISOString().slice(0, 10);
        const ano = String(base).slice(0, 4);
        return `${ano}-${String(mesNumero).padStart(2, '0')}-01`;
    }

    return null;
}

function calcularPosicaoContemplacaoConsorcio(mesInicio, mesContemplacao) {
    const inicio = converterMesParaData(mesInicio, mesContemplacao);
    const contemplacao = converterMesParaData(mesContemplacao, inicio);
    if (!inicio || !contemplacao) return null;

    const [anoInicio, mesInicioNum] = inicio.split('-').map(Number);
    const [anoContemplacao, mesContemplacaoNum] = contemplacao.split('-').map(Number);
    return ((anoContemplacao - anoInicio) * 12) + (mesContemplacaoNum - mesInicioNum) + 1;
}

function calcularValorParcelaConsorcio(valorInicial, tipoReajuste, valorReajuste, posicao) {
    const base = Number(valorInicial || 0);
    const reajuste = Number(valorReajuste || 0);
    const passos = Math.max(Number(posicao || 1) - 1, 0);

    if (tipoReajuste === 'fixo' && reajuste > 0) {
        return base + (passos * reajuste);
    }
    if (tipoReajuste === 'percentual' && reajuste > 0) {
        return base * (1 + ((passos * reajuste) / 100));
    }
    return base;
}

function calcularValorPremioConsorcio() {
    const campoPremio = document.getElementById('valor-premio');
    if (!campoPremio) return null;

    const valorInicial = Number(document.getElementById('valor')?.value || 0);
    const numeroParcelas = Number(document.getElementById('numero-parcelas')?.value || 0);
    const mesInicio = document.getElementById('mes-inicio')?.value;
    const mesContemplacao = document.getElementById('mes-contemplacao')?.value;
    const tipoReajuste = document.getElementById('tipo-reajuste')?.value || 'nenhum';
    const valorReajuste = Number(document.getElementById('valor-reajuste')?.value || 0);
    const posicao = calcularPosicaoContemplacaoConsorcio(mesInicio, mesContemplacao);

    if (!valorInicial || !numeroParcelas || !posicao || posicao < 1 || posicao > numeroParcelas) {
        campoPremio.value = '';
        return null;
    }

    const parcela = calcularValorParcelaConsorcio(valorInicial, tipoReajuste, valorReajuste, posicao);
    const premio = Math.round((parcela * numeroParcelas + Number.EPSILON) * 100) / 100;
    campoPremio.value = premio.toFixed(2);
    return premio;
}

function normalizarMes(valor) {
    return valor ? String(valor).slice(0, 7) : '';
}

function normalizarBusca(value) {
    return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .trim();
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
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
