/**
 * JavaScript para a página de Receitas
 *
 * Funcionalidades:
 * - Gerenciamento de fontes de receita
 * - Planejamento de orçamento
 * - Registro de receitas realizadas
 * - Relatórios e análises
 */

// ============================================================================
// ESTADO DA APLICAÇÃO
// ============================================================================

let estado = {
    anoAtual: new Date().getFullYear(),
    mesAtual: null,
    tipoFiltro: '',
    abaAtiva: 'fontes',
    fontes: [],
    orcamentos: [],
    realizadas: []
};

// ============================================================================
// INICIALIZAÇÃO
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    inicializar();
});

function inicializar() {
    // Preencher seletor de anos (últimos 5 anos + próximos 2)
    const anoInicio = new Date().getFullYear() - 5;
    const anoFim = new Date().getFullYear() + 2;
    const selectAno = document.getElementById('filtro-ano');

    for (let ano = anoInicio; ano <= anoFim; ano++) {
        const option = document.createElement('option');
        option.value = ano;
        option.textContent = ano;
        if (ano === estado.anoAtual) {
            option.selected = true;
        }
        selectAno.appendChild(option);
    }

    // Carregar dados iniciais
    carregarFontesReceita();
    atualizarDados();
}

// ============================================================================
// GERENCIAMENTO DE ABAS
// ============================================================================

function mudarAba(aba) {
    // Atualizar botões
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // Atualizar conteúdo
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`aba-${aba}`).classList.add('active');

    // Atualizar estado
    estado.abaAtiva = aba;

    // Carregar dados da aba
    if (aba === 'fontes') {
        carregarFontesReceita();
    } else if (aba === 'orcamento') {
        carregarOrcamentos();
    } else if (aba === 'realizadas') {
        carregarRealizadas();
    }
}

// ============================================================================
// ATUALIZAÇÃO DE DADOS
// ============================================================================

function atualizarDados() {
    const ano = document.getElementById('filtro-ano').value;
    const mes = document.getElementById('filtro-mes').value;

    estado.anoAtual = parseInt(ano);
    estado.mesAtual = mes || null;

    // Atualizar resumo
    atualizarResumo();

    // Recarregar aba ativa
    if (estado.abaAtiva === 'orcamento') {
        carregarOrcamentos();
    } else if (estado.abaAtiva === 'realizadas') {
        carregarRealizadas();
    }
}

async function atualizarResumo() {
    try {
        const response = await fetch(`/api/receitas/resumo-mensal?ano=${estado.anoAtual}`);
        const result = await response.json();

        if (result.success) {
            // Se mês específico selecionado
            if (estado.mesAtual) {
                const mesNum = parseInt(estado.mesAtual);
                const dados = result.data[mesNum];

                document.getElementById('total-previsto').textContent =
                    formatarMoeda(dados.total_previsto);
                document.getElementById('total-realizado').textContent =
                    formatarMoeda(dados.total_realizado);

                const diferenca = dados.total_realizado - dados.total_previsto;
                document.getElementById('diferenca').textContent =
                    formatarMoeda(diferenca);
                document.getElementById('diferenca').className =
                    `valor ${diferenca >= 0 ? 'positivo' : 'negativo'}`;

                const conf = dados.total_previsto > 0 ?
                    ((dados.total_realizado / dados.total_previsto) * 100).toFixed(1) : 0;
                document.getElementById('confiabilidade').textContent = `${conf}%`;
            }
        }
    } catch (error) {
        console.error('Erro ao atualizar resumo:', error);
    }
}

// ============================================================================
// FONTES DE RECEITA
// ============================================================================

async function carregarFontesReceita() {
    const lista = document.getElementById('fontes-lista');
    lista.innerHTML = '<p class="loading">Carregando...</p>';

    try {
        const tipo = document.getElementById('filtro-tipo').value;
        const url = tipo ? `/api/receitas/itens?tipo=${tipo}` : '/api/receitas/itens';

        const response = await fetch(url);
        const result = await response.json();

        if (result.success) {
            estado.fontes = result.data;
            renderizarFontes(result.data);

            // Atualizar selects de fontes nos modais
            atualizarSelectsFontes(result.data);
        } else {
            lista.innerHTML = `<p class="error">${result.error}</p>`;
        }
    } catch (error) {
        console.error('Erro ao carregar fontes:', error);
        lista.innerHTML = '<p class="error">Erro ao carregar fontes de receita</p>';
    }
}

function renderizarFontes(fontes) {
    const lista = document.getElementById('fontes-lista');

    if (fontes.length === 0) {
        lista.innerHTML = '<p class="empty">Nenhuma fonte de receita cadastrada</p>';
        return;
    }

    lista.innerHTML = fontes.map(fonte => `
        <div class="card-item ${fonte.ativo ? '' : 'inativo'}">
            <div class="item-header">
                <h3>${fonte.nome}</h3>
                <span class="badge ${getTipoBadgeClass(fonte.tipo)}">${formatarTipo(fonte.tipo)}</span>
            </div>
            <div class="item-body">
                ${fonte.descricao ? `<p>${fonte.descricao}</p>` : ''}
                ${fonte.valor_base_mensal ? `<p><strong>Valor Base:</strong> ${formatarMoeda(fonte.valor_base_mensal)}</p>` : ''}
                ${fonte.dia_previsto_pagamento ? `<p><strong>Dia de Pagamento:</strong> ${fonte.dia_previsto_pagamento}</p>` : ''}
            </div>
            <div class="item-actions">
                <button class="btn-icon" onclick="editarFonte(${fonte.id})" title="Editar">✏️</button>
                <button class="btn-icon" onclick="deletarFonte(${fonte.id})" title="Deletar">🗑️</button>
            </div>
        </div>
    `).join('');
}

function atualizarSelectsFontes(fontes) {
    const selects = ['orc-fonte', 'rec-fonte', 'real-fonte'];

    selects.forEach(selectId => {
        const select = document.getElementById(selectId);
        select.innerHTML = '<option value="">Selecione...</option>';

        fontes.filter(f => f.ativo).forEach(fonte => {
            const option = document.createElement('option');
            option.value = fonte.id;
            option.textContent = `${fonte.nome} (${formatarTipo(fonte.tipo)})`;
            select.appendChild(option);
        });
    });
}

// ============================================================================
// MODAIS
// ============================================================================

function abrirModalFonte(id = null) {
    const modal = document.getElementById('modal-fonte');
    const form = document.getElementById('form-fonte');
    form.reset();

    if (id) {
        // Modo edição - carregar dados
        const fonte = estado.fontes.find(f => f.id === id);
        if (fonte) {
            document.getElementById('fonte-id').value = fonte.id;
            document.getElementById('fonte-nome').value = fonte.nome;
            document.getElementById('fonte-tipo').value = fonte.tipo;
            document.getElementById('fonte-descricao').value = fonte.descricao || '';
            document.getElementById('fonte-valor-base').value = fonte.valor_base_mensal || '';
            document.getElementById('fonte-dia-pagamento').value = fonte.dia_previsto_pagamento || '';
            document.getElementById('fonte-ativo').checked = fonte.ativo;
            document.getElementById('modal-fonte-titulo').textContent = 'Editar Fonte de Receita';
        }
    } else {
        // Modo criação
        document.getElementById('modal-fonte-titulo').textContent = 'Nova Fonte de Receita';
    }

    modal.style.display = 'block';
}

function abrirModalOrcamento() {
    const modal = document.getElementById('modal-orcamento');
    modal.style.display = 'block';
}

function abrirModalRecorrente() {
    const modal = document.getElementById('modal-recorrente');
    modal.style.display = 'block';
}

function abrirModalRealizada() {
    const modal = document.getElementById('modal-realizada');
    const hoje = new Date().toISOString().split('T')[0];
    document.getElementById('real-data-recebimento').value = hoje;
    modal.style.display = 'block';
}

function fecharModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// ============================================================================
// SALVAMENTOS
// ============================================================================

async function salvarFonte(event) {
    event.preventDefault();

    const form = document.getElementById('form-fonte');
    const id = document.getElementById('fonte-id').value;

    const dados = {
        nome: document.getElementById('fonte-nome').value,
        tipo: document.getElementById('fonte-tipo').value,
        descricao: document.getElementById('fonte-descricao').value,
        valor_base_mensal: document.getElementById('fonte-valor-base').value || null,
        dia_previsto_pagamento: document.getElementById('fonte-dia-pagamento').value || null,
        ativo: document.getElementById('fonte-ativo').checked
    };

    try {
        const url = id ? `/api/receitas/itens/${id}` : '/api/receitas/itens';
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            fecharModal('modal-fonte');
            carregarFontesReceita();
        } else {
            alert('Erro: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao salvar fonte:', error);
        alert('Erro ao salvar fonte de receita');
    }
}

async function salvarOrcamento(event) {
    event.preventDefault();

    const dados = {
        item_receita_id: parseInt(document.getElementById('orc-fonte').value),
        ano_mes: document.getElementById('orc-ano-mes').value + '-01',
        valor_previsto: parseFloat(document.getElementById('orc-valor').value),
        periodicidade: document.getElementById('orc-periodicidade').value,
        observacoes: document.getElementById('orc-observacoes').value
    };

    try {
        const response = await fetch('/api/receitas/orcamento', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            fecharModal('modal-orcamento');
            carregarOrcamentos();
        } else {
            alert('Erro: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao salvar orçamento:', error);
        alert('Erro ao salvar orçamento');
    }
}

async function gerarRecorrente(event) {
    event.preventDefault();

    const dados = {
        item_receita_id: parseInt(document.getElementById('rec-fonte').value),
        data_inicio: document.getElementById('rec-inicio').value + '-01',
        data_fim: document.getElementById('rec-fim').value + '-01',
        valor_mensal: parseFloat(document.getElementById('rec-valor').value),
        periodicidade: 'MENSAL_FIXA'
    };

    try {
        const response = await fetch('/api/receitas/orcamento/gerar-recorrente', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            fecharModal('modal-recorrente');
            carregarOrcamentos();
        } else {
            alert('Erro: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao gerar projeções:', error);
        alert('Erro ao gerar projeções recorrentes');
    }
}

async function salvarRealizada(event) {
    event.preventDefault();

    const dados = {
        item_receita_id: parseInt(document.getElementById('real-fonte').value),
        data_recebimento: document.getElementById('real-data-recebimento').value,
        valor_recebido: parseFloat(document.getElementById('real-valor').value),
        competencia: document.getElementById('real-competencia').value + '-01',
        descricao: document.getElementById('real-descricao').value,
        observacoes: document.getElementById('real-observacoes').value
    };

    try {
        const response = await fetch('/api/receitas/realizadas', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            fecharModal('modal-realizada');
            carregarRealizadas();
            atualizarResumo();
        } else {
            alert('Erro: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao salvar receita:', error);
        alert('Erro ao salvar receita realizada');
    }
}

// ============================================================================
// UTILITÁRIOS
// ============================================================================

function formatarMoeda(valor) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(valor || 0);
}

function formatarTipo(tipo) {
    const tipos = {
        'SALARIO_FIXO': 'Salário',
        'GRATIFICACAO': 'Gratificação',
        'RENDA_EXTRA': 'Renda Extra',
        'ALUGUEL': 'Aluguel',
        'RENDIMENTO_FINANCEIRO': 'Rendimentos',
        'OUTROS': 'Outros'
    };
    return tipos[tipo] || tipo;
}

function getTipoBadgeClass(tipo) {
    const classes = {
        'SALARIO_FIXO': 'badge-success',
        'GRATIFICACAO': 'badge-primary',
        'RENDA_EXTRA': 'badge-warning',
        'ALUGUEL': 'badge-info',
        'RENDIMENTO_FINANCEIRO': 'badge-secondary',
        'OUTROS': 'badge-default'
    };
    return classes[tipo] || 'badge-default';
}

async function carregarOrcamentos() {
    const lista = document.getElementById('orcamento-lista');
    lista.innerHTML = '<p class="loading">Carregando...</p>';

    try {
        const response = await fetch(`/api/receitas/orcamento?ano=${estado.anoAtual}`);
        const result = await response.json();

        if (result.success) {
            estado.orcamentos = result.data;
            renderizarOrcamentos(result.data);
        } else {
            lista.innerHTML = `<p class="error">${result.error}</p>`;
        }
    } catch (error) {
        console.error('Erro ao carregar orçamentos:', error);
        lista.innerHTML = '<p class="error">Erro ao carregar orçamentos</p>';
    }
}

function renderizarOrcamentos(orcamentos) {
    const lista = document.getElementById('orcamento-lista');

    if (orcamentos.length === 0) {
        lista.innerHTML = '<p class="empty">Nenhum orçamento cadastrado</p>';
        return;
    }

    // Agrupar por item_receita_id
    const grouped = {};
    orcamentos.forEach(orc => {
        if (!grouped[orc.item_receita_id]) {
            grouped[orc.item_receita_id] = [];
        }
        grouped[orc.item_receita_id].push(orc);
    });

    // Renderizar
    lista.innerHTML = Object.values(grouped).map(grupo => {
        const fonte = estado.fontes.find(f => f.id === grupo[0].item_receita_id);
        const totalPrevisto = grupo.reduce((sum, o) => sum + o.valor_previsto, 0);

        return `
            <div class="card-item">
                <div class="item-header">
                    <h3>${fonte ? fonte.nome : 'Fonte desconhecida'}</h3>
                    <span class="badge badge-info">${grupo.length} meses</span>
                </div>
                <div class="item-body">
                    <p><strong>Total previsto:</strong> ${formatarMoeda(totalPrevisto)}</p>
                    <p><strong>Meses:</strong> ${grupo.map(o => {
                        const data = new Date(o.ano_mes);
                        return (data.getMonth() + 1).toString().padStart(2, '0');
                    }).join(', ')}</p>
                </div>
            </div>
        `;
    }).join('');
}

async function carregarRealizadas() {
    const lista = document.getElementById('realizadas-lista');
    lista.innerHTML = '<p class="loading">Carregando...</p>';

    try {
        let url = '/api/receitas/realizadas';
        if (estado.mesAtual) {
            url += `?ano_mes=${estado.anoAtual}-${estado.mesAtual}-01`;
        }

        const response = await fetch(url);
        const result = await response.json();

        if (result.success) {
            estado.realizadas = result.data;
            renderizarRealizadas(result.data);
        } else {
            lista.innerHTML = `<p class="error">${result.error}</p>`;
        }
    } catch (error) {
        console.error('Erro ao carregar realizadas:', error);
        lista.innerHTML = '<p class="error">Erro ao carregar receitas realizadas</p>';
    }
}

function renderizarRealizadas(receitas) {
    const lista = document.getElementById('realizadas-lista');

    if (receitas.length === 0) {
        lista.innerHTML = '<p class="empty">Nenhuma receita recebida</p>';
        return;
    }

    lista.innerHTML = receitas.map(rec => `
        <div class="card-item">
            <div class="item-header">
                <h3>${rec.descricao || 'Receita'}</h3>
                <span class="badge badge-success">${formatarMoeda(rec.valor_recebido)}</span>
            </div>
            <div class="item-body">
                <p><strong>Data:</strong> ${new Date(rec.data_recebimento).toLocaleDateString('pt-BR')}</p>
                <p><strong>Competência:</strong> ${new Date(rec.competencia).toLocaleDateString('pt-BR', {month: 'long', year: 'numeric'})}</p>
                ${rec.observacoes ? `<p><strong>Obs:</strong> ${rec.observacoes}</p>` : ''}
            </div>
            <div class="item-actions">
                <button class="btn-icon" onclick="deletarRealizada(${rec.id})" title="Deletar">🗑️</button>
            </div>
        </div>
    `).join('');
}

async function deletarRealizada(id) {
    if (!confirm('Tem certeza que deseja deletar esta receita?')) {
        return;
    }

    try {
        const response = await fetch(`/api/receitas/realizadas/${id}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            carregarRealizadas();
            atualizarResumo();
        } else {
            alert('Erro: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao deletar receita:', error);
        alert('Erro ao deletar receita');
    }
}

function editarFonte(id) {
    abrirModalFonte(id);
}

async function deletarFonte(id) {
    if (!confirm('Tem certeza que deseja inativar esta fonte de receita?')) {
        return;
    }

    try {
        const response = await fetch(`/api/receitas/itens/${id}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            carregarFontesReceita();
        } else {
            alert('Erro: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao inativar fonte:', error);
        alert('Erro ao inativar fonte de receita');
    }
}

// ============================================================================
// FECHAR MODAL AO CLICAR FORA
// ============================================================================

window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
};
