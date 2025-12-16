/**
 * JavaScript para gerenciamento de Cartões de Crédito
 */

// ============================================================================
// ESTADO GLOBAL
// ============================================================================

const state = {
    cartoes: [],
    categorias: [],
    cartaoAtual: null,
    itensAgregados: [],
    mesSelecionado: new Date().toISOString().slice(0, 7) // YYYY-MM
};

// ============================================================================
// INICIALIZAÇÃO
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    inicializar();
});

async function inicializar() {
    // Definir mês atual (converter de ISO para formato brasileiro)
    const mesInput = document.getElementById('filtro-mes');
    mesInput.value = converterISOparaMesAnoBR(state.mesSelecionado);

    // Event listeners
    document.getElementById('filtro-mes').addEventListener('change', (e) => {
        // Converter de MM/AAAA para ISO YYYY-MM
        const mesBR = e.target.value;
        const mesISO = converterMesAnoBRparaISO(mesBR);
        if (mesISO) {
            state.mesSelecionado = mesISO.substring(0, 7); // YYYY-MM
            if (state.cartaoAtual) {
                carregarResumoCartao(state.cartaoAtual.id);
            }
        }
    });

    document.getElementById('filtro-cartao').addEventListener('change', (e) => {
        if (e.target.value) {
            const cartao = state.cartoes.find(c => c.id == e.target.value);
            if (cartao) {
                visualizarCartao(cartao);
            }
        }
    });

    // Carregar dados iniciais
    await carregarCategorias();
    await carregarCartoes();
}

// ============================================================================
// CARREGAR CATEGORIAS
// ============================================================================

async function carregarCategorias() {
    try {
        const response = await fetch('/api/categorias');
        if (!response.ok) throw new Error('Erro ao carregar categorias');

        const data = await response.json();
        state.categorias = Array.isArray(data) ? data : [];

        // Preencher selects de categoria
        const selects = [
            document.getElementById('cartao-categoria')
        ];

        selects.forEach(select => {
            if (select) {
                select.innerHTML = '<option value="">Selecione...</option>';
                state.categorias.forEach(cat => {
                    if (cat.ativo) {
                        select.innerHTML += `<option value="${cat.id}">${cat.nome}</option>`;
                    }
                });
            }
        });
    } catch (error) {
        console.error('Erro ao carregar categorias:', error);
        state.categorias = [];
        mostrarErro('Erro ao carregar categorias');
    }
}

// ============================================================================
// CRUD DE CARTÕES
// ============================================================================

async function carregarCartoes() {
    try {
        const response = await fetch('/api/cartoes');
        if (!response.ok) throw new Error('Erro ao carregar cartões');

        state.cartoes = await response.json();
        renderizarCartoes();
        atualizarFiltroCartoes();
    } catch (error) {
        console.error('Erro ao carregar cartões:', error);
        mostrarErro('Erro ao carregar cartões');
    }
}

function renderizarCartoes() {
    const container = document.getElementById('lista-cartoes');

    if (state.cartoes.length === 0) {
        container.innerHTML = '<p class="empty-state">Nenhum cartão cadastrado. Clique em "Novo Cartão" para começar.</p>';
        return;
    }

    container.innerHTML = state.cartoes.map(cartao => `
        <div class="cartao-card" onclick="visualizarCartao(${JSON.stringify(cartao).replace(/"/g, '&quot;')})">
            <div class="cartao-card-header">
                <h3>${cartao.nome}</h3>
                ${cartao.config?.tem_codigo ? `
                    <button class="btn-cvv" onclick="event.stopPropagation(); abrirModalRevelarCVV(${cartao.id})" title="Ver código de segurança">
                        CVV 🔒
                    </button>
                ` : ''}
            </div>
            <div class="cartao-card-body">
                ${cartao.descricao ? `<p class="cartao-descricao">${cartao.descricao}</p>` : ''}
                ${cartao.config?.numero_cartao ? `
                    <div class="cartao-numero-display">
                        <span class="numero-cartao">${cartao.config.numero_cartao}</span>
                    </div>
                ` : ''}
                <div class="cartao-info-grid">
                    ${cartao.config?.data_validade ? `
                        <div class="info-item">
                            <span class="label">Validade:</span>
                            <span class="value">${cartao.config.data_validade}</span>
                        </div>
                    ` : ''}
                    <div class="info-item">
                        <span class="label">Vencimento:</span>
                        <span class="value">Dia ${cartao.config?.dia_vencimento || '-'}</span>
                    </div>
                    <div class="info-item">
                        <span class="label">Limite:</span>
                        <span class="value">R$ ${formatarMoeda(cartao.config?.limite_credito || 0)}</span>
                    </div>
                </div>
            </div>
        </div>
    `).join('');
}

function atualizarFiltroCartoes() {
    const select = document.getElementById('filtro-cartao');
    select.innerHTML = '<option value="">Selecione um cartão...</option>';
    state.cartoes.forEach(cartao => {
        select.innerHTML += `<option value="${cartao.id}">${cartao.nome}</option>`;
    });
}

function abrirModalCartao() {
    document.getElementById('modal-cartao-titulo').textContent = 'Novo Cartão de Crédito';
    document.getElementById('form-cartao').reset();
    document.getElementById('cartao-id').value = '';
    abrirModal('modal-cartao');
}

function abrirModalEditarCartao() {
    if (!state.cartaoAtual) return;

    const cartao = state.cartaoAtual;
    document.getElementById('modal-cartao-titulo').textContent = 'Editar Cartão de Crédito';
    document.getElementById('cartao-id').value = cartao.id;
    document.getElementById('cartao-nome').value = cartao.nome;
    document.getElementById('cartao-descricao').value = cartao.descricao || '';
    document.getElementById('cartao-dia-vencimento').value = cartao.config?.dia_vencimento || '';
    document.getElementById('cartao-limite').value = cartao.config?.limite_credito || '';
    document.getElementById('cartao-numero').value = cartao.config?.numero_cartao || '';
    document.getElementById('cartao-data-validade').value = cartao.config?.data_validade || '';
    document.getElementById('cartao-cvv').value = '';  // Não mostra o CVV por segurança
    document.getElementById('cartao-tem-codigo').checked = cartao.config?.tem_codigo || false;
    document.getElementById('cartao-observacoes').value = cartao.config?.observacoes || '';

    abrirModal('modal-cartao');
}

async function salvarCartao(event) {
    event.preventDefault();

    const id = document.getElementById('cartao-id').value;
    const diaVencimento = parseInt(document.getElementById('cartao-dia-vencimento').value);

    const dados = {
        nome: document.getElementById('cartao-nome').value,
        descricao: document.getElementById('cartao-descricao').value,
        dia_fechamento: diaVencimento, // Mesmo dia do vencimento
        dia_vencimento: diaVencimento,
        limite_credito: parseFloat(document.getElementById('cartao-limite').value) || null,
        numero_cartao: document.getElementById('cartao-numero').value || null,
        data_validade: document.getElementById('cartao-data-validade').value || null,
        codigo_seguranca: document.getElementById('cartao-cvv').value || null,
        tem_codigo: document.getElementById('cartao-tem-codigo').checked,
        observacoes: document.getElementById('cartao-observacoes').value
    };

    try {
        const url = id ? `/api/cartoes/${id}` : '/api/cartoes';
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        if (!response.ok) throw new Error('Erro ao salvar cartão');

        fecharModal('modal-cartao');
        await carregarCartoes();
        mostrarSucesso(id ? 'Cartão atualizado com sucesso!' : 'Cartão criado com sucesso!');

        // Se estava editando, atualizar a visualização
        if (id && state.cartaoAtual && state.cartaoAtual.id == id) {
            const cartao = state.cartoes.find(c => c.id == id);
            if (cartao) {
                visualizarCartao(cartao);
            }
        }
    } catch (error) {
        console.error('Erro ao salvar cartão:', error);
        mostrarErro('Erro ao salvar cartão');
    }
}

async function excluirCartao(id) {
    if (!confirm('Tem certeza que deseja excluir este cartão?')) return;

    try {
        const response = await fetch(`/api/cartoes/${id}`, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error('Erro ao excluir cartão');

        voltarListaCartoes();
        await carregarCartoes();
        mostrarSucesso('Cartão excluído com sucesso!');
    } catch (error) {
        console.error('Erro ao excluir cartão:', error);
        mostrarErro('Erro ao excluir cartão');
    }
}

// ============================================================================
// VISUALIZAÇÃO DO CARTÃO
// ============================================================================

function visualizarCartao(cartao) {
    state.cartaoAtual = cartao;

    // Atualizar informações do header
    document.getElementById('cartao-nome-detalhe').textContent = cartao.nome;
    document.getElementById('cartao-descricao-detalhe').textContent = cartao.descricao || '';

    // Atualizar seletor
    document.getElementById('filtro-cartao').value = cartao.id;

    // Mostrar view de detalhes
    document.getElementById('view-lista-cartoes').style.display = 'none';
    document.getElementById('view-detalhes-cartao').style.display = 'block';

    // Carregar dados
    carregarItensAgregados(cartao.id);
    carregarResumoCartao(cartao.id);
}

function voltarListaCartoes() {
    state.cartaoAtual = null;
    document.getElementById('filtro-cartao').value = '';
    document.getElementById('view-lista-cartoes').style.display = 'block';
    document.getElementById('view-detalhes-cartao').style.display = 'none';
}

async function carregarResumoCartao(cartaoId) {
    try {
        const response = await fetch(`/api/cartoes/${cartaoId}/resumo?mes_referencia=${state.mesSelecionado}`);
        if (!response.ok) throw new Error('Erro ao carregar resumo');

        const resumo = await response.json();

        // Atualizar cards de resumo
        document.getElementById('total-orcado').textContent = `R$ ${formatarMoeda(resumo.total_orcado)}`;
        document.getElementById('total-gasto').textContent = `R$ ${formatarMoeda(resumo.total_gasto)}`;
        document.getElementById('saldo-disponivel').textContent = `R$ ${formatarMoeda(resumo.saldo_disponivel)}`;
        document.getElementById('limite-credito').textContent = resumo.limite_credito
            ? `R$ ${formatarMoeda(resumo.limite_credito)}`
            : '-';

        // Renderizar orçamentos com os dados do resumo
        renderizarOrcamentos(resumo.itens);

    } catch (error) {
        console.error('Erro ao carregar resumo:', error);
        mostrarErro('Erro ao carregar resumo do cartão');
    }
}

// ============================================================================
// CRUD DE ITENS AGREGADOS (Categorias do cartão)
// ============================================================================

async function carregarItensAgregados(cartaoId) {
    try {
        const response = await fetch(`/api/cartoes/${cartaoId}/itens`);
        if (!response.ok) throw new Error('Erro ao carregar itens');

        state.itensAgregados = await response.json();
        renderizarItensAgregados();
        atualizarSelectsItensAgregados();
    } catch (error) {
        console.error('Erro ao carregar itens agregados:', error);
        mostrarErro('Erro ao carregar categorias do cartão');
    }
}

function renderizarItensAgregados() {
    const container = document.getElementById('lista-itens-agregados');

    if (state.itensAgregados.length === 0) {
        container.innerHTML = '<p class="empty-state">Nenhuma categoria cadastrada. Adicione categorias para organizar seus gastos.</p>';
        return;
    }

    container.innerHTML = state.itensAgregados.map(item => `
        <div class="item-card">
            <div class="item-header">
                <h4>${item.nome}</h4>
                <div class="item-actions">
                    <button class="btn-icon" onclick="editarItemAgregado(${item.id})" title="Editar">✎</button>
                    <button class="btn-icon btn-danger" onclick="excluirItemAgregado(${item.id})" title="Excluir">×</button>
                </div>
            </div>
            ${item.descricao ? `<p class="item-descricao">${item.descricao}</p>` : ''}
        </div>
    `).join('');
}

function atualizarSelectsItensAgregados() {
    const selects = [
        document.getElementById('orcamento-categoria'),
        document.getElementById('lancamento-categoria')
    ];

    selects.forEach(select => {
        select.innerHTML = '<option value="">Selecione...</option>';
        state.itensAgregados.forEach(item => {
            select.innerHTML += `<option value="${item.id}">${item.nome}</option>`;
        });
    });
}

function abrirModalItemAgregado() {
    document.getElementById('modal-item-titulo').textContent = 'Nova Categoria';
    document.getElementById('form-item-agregado').reset();
    document.getElementById('item-id').value = '';
    abrirModal('modal-item-agregado');
}

async function editarItemAgregado(id) {
    const item = state.itensAgregados.find(i => i.id === id);
    if (!item) return;

    document.getElementById('modal-item-titulo').textContent = 'Editar Categoria';
    document.getElementById('item-id').value = item.id;
    document.getElementById('item-nome').value = item.nome;
    document.getElementById('item-descricao').value = item.descricao || '';

    abrirModal('modal-item-agregado');
}

async function salvarItemAgregado(event) {
    event.preventDefault();

    const id = document.getElementById('item-id').value;
    const dados = {
        nome: document.getElementById('item-nome').value,
        descricao: document.getElementById('item-descricao').value
    };

    try {
        const url = id
            ? `/api/cartoes/itens/${id}`
            : `/api/cartoes/${state.cartaoAtual.id}/itens`;
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        if (!response.ok) throw new Error('Erro ao salvar categoria');

        fecharModal('modal-item-agregado');
        await carregarItensAgregados(state.cartaoAtual.id);
        await carregarResumoCartao(state.cartaoAtual.id);
        mostrarSucesso(id ? 'Categoria atualizada!' : 'Categoria criada!');
    } catch (error) {
        console.error('Erro ao salvar item:', error);
        mostrarErro('Erro ao salvar categoria');
    }
}

async function excluirItemAgregado(id) {
    if (!confirm('Tem certeza que deseja excluir esta categoria?')) return;

    try {
        const response = await fetch(`/api/cartoes/itens/${id}`, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error('Erro ao excluir categoria');

        await carregarItensAgregados(state.cartaoAtual.id);
        await carregarResumoCartao(state.cartaoAtual.id);
        mostrarSucesso('Categoria excluída!');
    } catch (error) {
        console.error('Erro ao excluir item:', error);
        mostrarErro('Erro ao excluir categoria');
    }
}

// ============================================================================
// CRUD DE ORÇAMENTOS
// ============================================================================

function renderizarOrcamentos(itens) {
    const container = document.getElementById('lista-orcamentos');

    if (!itens || itens.length === 0) {
        container.innerHTML = '<p class="empty-state">Nenhuma categoria definida para este mês. Clique em "Nova Categoria" para começar.</p>';
        return;
    }

    container.innerHTML = itens.map(item => {
        const percentual = item.percentual_utilizado || 0;
        const cor = percentual > 100 ? '#ef4444' : percentual > 80 ? '#f59e0b' : '#10b981';

        return `
            <div class="orcamento-card">
                <div class="orcamento-header">
                    <h4>${item.nome}</h4>
                    <span class="percentual" style="color: ${cor}">${percentual.toFixed(0)}%</span>
                </div>
                <div class="orcamento-valores">
                    <div class="valor-item">
                        <span class="label">Limite Mensal:</span>
                        <span class="value">R$ ${formatarMoeda(item.valor_orcado)}</span>
                    </div>
                    <div class="valor-item">
                        <span class="label">Utilizado:</span>
                        <span class="value">R$ ${formatarMoeda(item.valor_gasto)}</span>
                    </div>
                    <div class="valor-item">
                        <span class="label">Disponível:</span>
                        <span class="value" style="color: ${item.saldo >= 0 ? '#10b981' : '#ef4444'}">
                            R$ ${formatarMoeda(item.saldo)}
                        </span>
                    </div>
                </div>
                <div class="orcamento-barra">
                    <div class="barra-progresso" style="width: ${Math.min(percentual, 100)}%; background: ${cor}"></div>
                </div>
                ${item.orcamento_id ? `
                    <div class="orcamento-actions">
                        <button class="btn-sm btn-secondary" onclick="editarOrcamento(${item.id}, ${item.orcamento_id})">Editar</button>
                        <button class="btn-sm btn-danger" onclick="excluirOrcamento(${item.orcamento_id})">Excluir</button>
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

function abrirModalOrcamento() {
    document.getElementById('modal-orcamento-titulo').textContent = 'Definir Limite da Categoria';
    document.getElementById('form-orcamento').reset();
    document.getElementById('orcamento-id').value = '';
    // Converter ISO YYYY-MM para MM/AAAA
    document.getElementById('orcamento-mes').value = converterISOparaMesAnoBR(state.mesSelecionado);
    abrirModal('modal-orcamento');
}

async function editarOrcamento(itemId, orcamentoId) {
    try {
        // Buscar detalhes do orçamento
        const item = state.itensAgregados.find(i => i.id === itemId);
        const response = await fetch(`/api/cartoes/itens/${itemId}/orcamentos?mes_referencia=${state.mesSelecionado}`);
        const orcamentos = await response.json();
        const orcamento = orcamentos.find(o => o.id === orcamentoId);

        if (!orcamento) throw new Error('Orçamento não encontrado');

        document.getElementById('modal-orcamento-titulo').textContent = 'Editar Limite da Categoria';
        document.getElementById('orcamento-id').value = orcamento.id;
        document.getElementById('orcamento-item-id').value = itemId;
        document.getElementById('orcamento-categoria').value = itemId;
        // Converter ISO YYYY-MM para MM/AAAA
        document.getElementById('orcamento-mes').value = converterISOparaMesAnoBR(orcamento.mes_referencia);
        document.getElementById('orcamento-valor').value = orcamento.valor_teto;
        document.getElementById('orcamento-observacoes').value = orcamento.observacoes || '';

        abrirModal('modal-orcamento');
    } catch (error) {
        console.error('Erro ao carregar orçamento:', error);
        mostrarErro('Erro ao carregar orçamento');
    }
}

async function salvarOrcamento(event) {
    event.preventDefault();

    const id = document.getElementById('orcamento-id').value;
    const itemId = id
        ? document.getElementById('orcamento-item-id').value
        : document.getElementById('orcamento-categoria').value;

    // Converter mês de MM/AAAA para ISO YYYY-MM
    const mesBR = document.getElementById('orcamento-mes').value;
    const mesISO = converterMesAnoBRparaISO(mesBR);

    if (!mesISO) {
        mostrarErro('Formato de data inválido. Use MM/AAAA');
        return;
    }

    const dados = {
        mes_referencia: mesISO.substring(0, 7), // YYYY-MM
        valor_teto: parseFloat(document.getElementById('orcamento-valor').value),
        observacoes: document.getElementById('orcamento-observacoes').value
    };

    try {
        const url = id
            ? `/api/cartoes/orcamentos/${id}`
            : `/api/cartoes/itens/${itemId}/orcamentos`;
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.erro || 'Erro ao salvar orçamento');
        }

        fecharModal('modal-orcamento');
        await carregarResumoCartao(state.cartaoAtual.id);
        mostrarSucesso(id ? 'Limite atualizado!' : 'Categoria criada!');
    } catch (error) {
        console.error('Erro ao salvar orçamento:', error);
        mostrarErro(error.message);
    }
}

async function excluirOrcamento(id) {
    if (!confirm('Tem certeza que deseja excluir o limite desta categoria?')) return;

    try {
        const response = await fetch(`/api/cartoes/orcamentos/${id}`, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error('Erro ao excluir orçamento');

        await carregarResumoCartao(state.cartaoAtual.id);
        mostrarSucesso('Limite excluído!');
    } catch (error) {
        console.error('Erro ao excluir orçamento:', error);
        mostrarErro('Erro ao excluir orçamento');
    }
}

// ============================================================================
// CRUD DE LANÇAMENTOS (Gastos)
// ============================================================================

async function carregarLancamentos() {
    const container = document.getElementById('lista-lancamentos');

    if (!state.cartaoAtual) return;

    try {
        // Carregar lançamentos de todos os itens do cartão
        const promises = state.itensAgregados.map(item =>
            fetch(`/api/cartoes/itens/${item.id}/lancamentos?mes_fatura=${state.mesSelecionado}`)
                .then(r => r.json())
                .then(lancamentos => lancamentos.map(l => ({ ...l, item_nome: item.nome })))
        );

        const resultados = await Promise.all(promises);
        const todosLancamentos = resultados.flat();

        renderizarLancamentos(todosLancamentos);
    } catch (error) {
        console.error('Erro ao carregar lançamentos:', error);
        container.innerHTML = '<p class="error">Erro ao carregar lançamentos</p>';
    }
}

function renderizarLancamentos(lancamentos) {
    const container = document.getElementById('lista-lancamentos');

    if (lancamentos.length === 0) {
        container.innerHTML = '<p class="empty-state">Nenhum gasto registrado para este mês.</p>';
        return;
    }

    // Agrupar por categoria
    const porCategoria = {};
    lancamentos.forEach(lanc => {
        if (!porCategoria[lanc.item_nome]) {
            porCategoria[lanc.item_nome] = [];
        }
        porCategoria[lanc.item_nome].push(lanc);
    });

    container.innerHTML = Object.keys(porCategoria).map(categoria => {
        const itens = porCategoria[categoria];
        const total = itens.reduce((sum, i) => sum + parseFloat(i.valor), 0);

        return `
            <div class="lancamento-grupo">
                <div class="grupo-header">
                    <h4>${categoria}</h4>
                    <span class="grupo-total">R$ ${formatarMoeda(total)}</span>
                </div>
                <div class="lancamentos-items">
                    ${itens.map(lanc => `
                        <div class="lancamento-item">
                            <div class="lancamento-info">
                                <span class="lancamento-descricao">${lanc.descricao}</span>
                                <span class="lancamento-data">${formatarData(lanc.data_compra)}</span>
                                ${lanc.total_parcelas > 1 ? `
                                    <span class="lancamento-parcela">${lanc.numero_parcela}/${lanc.total_parcelas}</span>
                                ` : ''}
                            </div>
                            <div class="lancamento-actions">
                                <span class="lancamento-valor">R$ ${formatarMoeda(lanc.valor)}</span>
                                <button class="btn-icon" onclick="editarLancamento(${lanc.id})" title="Editar">✎</button>
                                <button class="btn-icon btn-danger" onclick="excluirLancamento(${lanc.id})" title="Excluir">×</button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }).join('');
}

function abrirModalLancamento() {
    document.getElementById('modal-lancamento-titulo').textContent = 'Novo Gasto';
    document.getElementById('form-lancamento').reset();
    document.getElementById('lancamento-id').value = '';
    // Converter ISO YYYY-MM para MM/AAAA
    document.getElementById('lancamento-fatura').value = converterISOparaMesAnoBR(state.mesSelecionado);
    document.getElementById('lancamento-data').value = new Date().toISOString().slice(0, 10);
    abrirModal('modal-lancamento');
}

async function editarLancamento(id) {
    try {
        // Buscar o lançamento nos itens
        let lancamento = null;
        let itemId = null;

        for (const item of state.itensAgregados) {
            const response = await fetch(`/api/cartoes/itens/${item.id}/lancamentos?mes_fatura=${state.mesSelecionado}`);
            const lancamentos = await response.json();
            lancamento = lancamentos.find(l => l.id === id);
            if (lancamento) {
                itemId = item.id;
                break;
            }
        }

        if (!lancamento) throw new Error('Lançamento não encontrado');

        document.getElementById('modal-lancamento-titulo').textContent = 'Editar Gasto';
        document.getElementById('lancamento-id').value = lancamento.id;
        document.getElementById('lancamento-item-id').value = itemId;
        document.getElementById('lancamento-categoria').value = itemId;
        document.getElementById('lancamento-descricao').value = lancamento.descricao;
        document.getElementById('lancamento-valor').value = lancamento.valor;
        document.getElementById('lancamento-data').value = lancamento.data_compra;
        // Converter ISO YYYY-MM para MM/AAAA
        document.getElementById('lancamento-fatura').value = converterISOparaMesAnoBR(lancamento.mes_fatura);
        document.getElementById('lancamento-parcela').value = lancamento.numero_parcela;
        document.getElementById('lancamento-total-parcelas').value = lancamento.total_parcelas;
        document.getElementById('lancamento-observacoes').value = lancamento.observacoes || '';

        abrirModal('modal-lancamento');
    } catch (error) {
        console.error('Erro ao carregar lançamento:', error);
        mostrarErro('Erro ao carregar lançamento');
    }
}

async function salvarLancamento(event) {
    event.preventDefault();

    const id = document.getElementById('lancamento-id').value;
    const itemId = id
        ? document.getElementById('lancamento-item-id').value
        : document.getElementById('lancamento-categoria').value;

    // Converter mês da fatura de MM/AAAA para ISO YYYY-MM
    const faturaBR = document.getElementById('lancamento-fatura').value;
    const faturaISO = converterMesAnoBRparaISO(faturaBR);

    if (!faturaISO) {
        mostrarErro('Formato de data inválido. Use MM/AAAA');
        return;
    }

    const dados = {
        descricao: document.getElementById('lancamento-descricao').value,
        valor: parseFloat(document.getElementById('lancamento-valor').value),
        data_compra: document.getElementById('lancamento-data').value,
        mes_fatura: faturaISO.substring(0, 7), // YYYY-MM
        numero_parcela: parseInt(document.getElementById('lancamento-parcela').value) || 1,
        total_parcelas: parseInt(document.getElementById('lancamento-total-parcelas').value) || 1,
        observacoes: document.getElementById('lancamento-observacoes').value
    };

    try {
        const url = id
            ? `/api/cartoes/lancamentos/${id}`
            : `/api/cartoes/itens/${itemId}/lancamentos`;
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        if (!response.ok) throw new Error('Erro ao salvar lançamento');

        fecharModal('modal-lancamento');
        await carregarLancamentos();
        await carregarResumoCartao(state.cartaoAtual.id);
        mostrarSucesso(id ? 'Gasto atualizado!' : 'Gasto registrado!');
    } catch (error) {
        console.error('Erro ao salvar lançamento:', error);
        mostrarErro('Erro ao salvar gasto');
    }
}

async function excluirLancamento(id) {
    if (!confirm('Tem certeza que deseja excluir este lançamento?')) return;

    try {
        const response = await fetch(`/api/cartoes/lancamentos/${id}`, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error('Erro ao excluir lançamento');

        await carregarLancamentos();
        await carregarResumoCartao(state.cartaoAtual.id);
        mostrarSucesso('Lançamento excluído!');
    } catch (error) {
        console.error('Erro ao excluir lançamento:', error);
        mostrarErro('Erro ao excluir lançamento');
    }
}

// ============================================================================
// CRUD DE FATURAS
// ============================================================================

/**
 * Carrega faturas do cartão
 * Frontend não decide - apenas busca e exibe
 */
async function carregarFaturas(cartaoId) {
    const container = document.getElementById('lista-faturas');

    if (!cartaoId) {
        container.innerHTML = '<p class="empty-state">Selecione um cartão para ver as faturas.</p>';
        return;
    }

    mostrarLoading('Carregando faturas...');

    try {
        const response = await fetch(`/api/cartoes/${cartaoId}/faturas`);

        if (!response.ok) {
            throw new Error('Erro ao carregar faturas');
        }

        const faturas = await response.json();
        renderizarFaturas(faturas);

    } catch (error) {
        console.error('Erro ao carregar faturas:', error);
        container.innerHTML = '<p class="error">Erro ao carregar faturas</p>';
        mostrarErro('Erro ao carregar faturas');
    } finally {
        esconderLoading();
    }
}

/**
 * Renderiza lista de faturas
 * Não calcula nada - apenas exibe o que veio do backend
 */
function renderizarFaturas(faturas) {
    const container = document.getElementById('lista-faturas');

    if (!faturas || faturas.length === 0) {
        container.innerHTML = '<p class="empty-state">Nenhuma fatura encontrada.</p>';
        return;
    }

    // Criar tabela simples
    container.innerHTML = `
        <table class="tabela-faturas" style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr style="background: #f5f5f7; text-align: left;">
                    <th style="padding: 12px; border-bottom: 2px solid #e8e8ea;">Competência</th>
                    <th style="padding: 12px; border-bottom: 2px solid #e8e8ea;">Valor</th>
                    <th style="padding: 12px; border-bottom: 2px solid #e8e8ea;">Status</th>
                    <th style="padding: 12px; border-bottom: 2px solid #e8e8ea; text-align: center;">Ação</th>
                </tr>
            </thead>
            <tbody>
                ${faturas.map(fatura => {
                    const isPendente = fatura.status === 'PENDENTE';
                    const statusCor = isPendente ? '#ff9500' : '#34c759';
                    const statusTexto = isPendente ? 'Pendente' : 'Paga';

                    return `
                        <tr style="border-bottom: 1px solid #e8e8ea;">
                            <td style="padding: 12px; color: #1d1d1f;">${fatura.competencia || '-'}</td>
                            <td style="padding: 12px; color: #1d1d1f; font-weight: 600;">R$ ${formatarMoeda(fatura.valor_total || 0)}</td>
                            <td style="padding: 12px;">
                                <span style="
                                    display: inline-block;
                                    padding: 4px 12px;
                                    background: ${statusCor}15;
                                    color: ${statusCor};
                                    border-radius: 12px;
                                    font-size: 13px;
                                    font-weight: 600;
                                ">${statusTexto}</span>
                            </td>
                            <td style="padding: 12px; text-align: center;">
                                ${isPendente ? `
                                    <button
                                        class="btn btn-sm btn-primary"
                                        onclick="abrirModalPagarFatura(${fatura.despesa_id}, '${fatura.competencia}', ${fatura.valor_total})"
                                        style="padding: 6px 16px; font-size: 14px;">
                                        Pagar
                                    </button>
                                ` : `
                                    <span style="color: #6e6e73; font-size: 13px;">
                                        ${fatura.data_pagamento ? `Paga em ${formatarData(fatura.data_pagamento)}` : '-'}
                                    </span>
                                `}
                            </td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
}

/**
 * Abre modal para pagar fatura
 */
function abrirModalPagarFatura(despesaId, competencia, valor) {
    document.getElementById('fatura-despesa-id').value = despesaId;
    document.getElementById('fatura-data-pagamento').value = new Date().toISOString().slice(0, 10);

    // Preencher info da fatura
    document.getElementById('fatura-info').innerHTML = `
        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <span style="color: #6e6e73;">Competência:</span>
            <strong style="color: #1d1d1f;">${competencia}</strong>
        </div>
        <div style="display: flex; justify-content: space-between;">
            <span style="color: #6e6e73;">Valor:</span>
            <strong style="color: #1d1d1f; font-size: 18px;">R$ ${formatarMoeda(valor)}</strong>
        </div>
    `;

    abrirModal('modal-pagar-fatura');
}

/**
 * Confirma pagamento da fatura
 * Chama endpoint de despesas já existente
 */
async function pagarFatura(event) {
    event.preventDefault();

    const despesaId = document.getElementById('fatura-despesa-id').value;
    const dataPagamento = document.getElementById('fatura-data-pagamento').value;
    const contaBancariaId = document.getElementById('fatura-conta-bancaria').value;

    const dados = {
        data_pagamento: dataPagamento
    };

    // Conta bancária é opcional
    if (contaBancariaId) {
        dados.conta_bancaria_id = parseInt(contaBancariaId);
    }

    mostrarLoading('Processando pagamento...');

    try {
        const response = await fetch(`/api/despesas/${despesaId}/pagar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.erro || result.message || 'Erro ao pagar fatura');
        }

        fecharModal('modal-pagar-fatura');

        // Recarregar faturas e resumo
        if (state.cartaoAtual) {
            await carregarFaturas(state.cartaoAtual.id);
            await carregarResumoCartao(state.cartaoAtual.id);
        }

        mostrarSucesso('Fatura paga com sucesso!');

    } catch (error) {
        console.error('Erro ao pagar fatura:', error);
        mostrarErro(error.message);
    }
}

// ============================================================================
// CONTROLE DE TABS
// ============================================================================

window.trocarTab = function(tabName) {
    // Remover active de todos
    document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    // Adicionar active no selecionado
    event.target.classList.add('active');
    document.getElementById('tab-' + tabName).classList.add('active');

    // Carregar dados específicos da tab
    if (tabName === 'lancamentos') {
        carregarLancamentos();
    } else if (tabName === 'faturas') {
        if (state.cartaoAtual) {
            carregarFaturas(state.cartaoAtual.id);
        }
    }
};

// ============================================================================
// UTILITÁRIOS
// ============================================================================

function abrirModal(modalId) {
    document.getElementById(modalId).style.display = 'flex';
}

function fecharModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

function formatarMoeda(valor) {
    return parseFloat(valor || 0).toLocaleString('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatarData(data) {
    if (!data) return '';
    const d = new Date(data + 'T00:00:00');
    return d.toLocaleDateString('pt-BR');
}

// ============================================================================
// MENSAGENS DE FEEDBACK (copiado de financiamentos.js)
// ============================================================================

function mostrarLoading(mensagem = 'Carregando...') {
    // Remover loading anterior se existir
    esconderLoading();

    const overlay = document.createElement('div');
    overlay.id = 'loading-overlay';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10000;
    `;

    const box = document.createElement('div');
    box.style.cssText = `
        background: white;
        padding: 30px 40px;
        border-radius: 8px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    `;

    box.innerHTML = `
        <div style="font-size: 32px; margin-bottom: 15px;">⏳</div>
        <div style="font-size: 16px; color: #1d1d1f;">${mensagem}</div>
    `;

    overlay.appendChild(box);
    document.body.appendChild(overlay);
}

function esconderLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.remove();
    }
}

function mostrarSucesso(mensagem) {
    esconderLoading();
    mostrarNotificacao(mensagem, 'success');
}

function mostrarErro(mensagem) {
    esconderLoading();
    mostrarNotificacao(mensagem, 'error');
}

function mostrarNotificacao(mensagem, tipo = 'info') {
    // Remover notificações anteriores
    const existente = document.getElementById('notificacao-toast');
    if (existente) existente.remove();

    const cores = {
        'success': { bg: '#34c759', icone: '✓' },
        'error': { bg: '#ff3b30', icone: '✕' },
        'info': { bg: '#007aff', icone: 'ℹ' },
        'warning': { bg: '#ff9500', icone: '⚠' }
    };

    const config = cores[tipo] || cores['info'];

    const toast = document.createElement('div');
    toast.id = 'notificacao-toast';
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${config.bg};
        color: white;
        padding: 16px 24px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        z-index: 10001;
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 15px;
        max-width: 400px;
        animation: slideIn 0.3s ease-out;
    `;

    toast.innerHTML = `
        <span style="font-size: 20px; font-weight: bold;">${config.icone}</span>
        <span>${mensagem}</span>
    `;

    document.body.appendChild(toast);

    // Auto-remover após 4 segundos
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Adicionar CSS das animações
if (!document.getElementById('toast-animations')) {
    const style = document.createElement('style');
    style.id = 'toast-animations';
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(400px);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        @keyframes slideOut {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(400px);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
}

// Fechar modal ao clicar fora
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
};

// ============================================================================
// NÚMERO DO CARTÃO E CÓDIGO DE SEGURANÇA
// ============================================================================

// Formatar número do cartão automaticamente (adicionar espaços)
document.addEventListener('DOMContentLoaded', () => {
    const inputNumeroCartao = document.getElementById('cartao-numero');
    if (inputNumeroCartao) {
        inputNumeroCartao.addEventListener('input', (e) => {
            let valor = e.target.value.replace(/\s/g, '');  // Remove espaços
            let formatado = valor.match(/.{1,4}/g)?.join(' ') || valor;  // Adiciona espaço a cada 4 dígitos
            e.target.value = formatado;
        });
    }
});

// Função para revelar código de segurança
async function revelarCodigoSeguranca(event) {
    event.preventDefault();

    const cartaoId = document.getElementById('cvv-cartao-id').value;
    const senha = document.getElementById('cvv-senha').value;

    try {
        const response = await fetch(`/api/cartoes/${cartaoId}/codigo-seguranca`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ senha: senha })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.erro || 'Erro ao revelar código');
        }

        const data = await response.json();

        // Mostrar código
        document.getElementById('cvv-codigo').textContent = data.codigo_seguranca || '***';
        document.getElementById('cvv-resultado').style.display = 'block';
        document.getElementById('btn-revelar').style.display = 'none';

    } catch (error) {
        mostrarErro(error.message);
        document.getElementById('cvv-senha').value = '';
    }
}

// Abrir modal para revelar CVV
window.abrirModalRevelarCVV = function(cartaoId) {
    document.getElementById('cvv-cartao-id').value = cartaoId;
    document.getElementById('cvv-senha').value = '';
    document.getElementById('cvv-resultado').style.display = 'none';
    document.getElementById('btn-revelar').style.display = 'inline-block';
    abrirModal('modal-revelar-cvv');
};

/**
 * Aplica máscara MM/AAAA em campos de mês/ano
 */
function mascaraMesAno(input) {
    let valor = input.value.replace(/\D/g, ''); // Remove tudo que não é dígito

    if (valor.length >= 2) {
        valor = valor.substring(0, 2) + '/' + valor.substring(2, 6);
    }

    input.value = valor;
}

/**
 * Converte data brasileira MM/AAAA para formato ISO YYYY-MM-DD
 */
function converterMesAnoBRparaISO(mesAnoBR) {
    if (!mesAnoBR || mesAnoBR.length !== 7) return null;

    const partes = mesAnoBR.split('/');
    if (partes.length !== 2) return null;

    const mes = partes[0];
    const ano = partes[1];

    // Validar mês
    const mesNum = parseInt(mes);
    if (mesNum < 1 || mesNum > 12) return null;

    return `${ano}-${mes}-01`;
}

/**
 * Converte data ISO YYYY-MM para formato brasileiro MM/AAAA
 */
function converterISOparaMesAnoBR(dataISO) {
    if (!dataISO) return '';

    const partes = dataISO.split('-');
    if (partes.length < 2) return '';

    return `${partes[1]}/${partes[0]}`;
}

