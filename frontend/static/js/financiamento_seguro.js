/**
 * Gestão de Vigências de Seguro Habitacional
 *
 * REGRAS:
 * - Seguro é valor absoluto (não percentual)
 * - Histórico é imutável
 * - Apenas observações podem ser editadas
 * - Nova vigência encerra a anterior automaticamente
 */

let financiamentoId = null;

// Inicializar ao carregar página
document.addEventListener('DOMContentLoaded', function() {
    // Pegar financiamento_id da URL
    const urlParams = new URLSearchParams(window.location.search);
    financiamentoId = urlParams.get('id');

    if (!financiamentoId) {
        alert('ID do financiamento não informado');
        window.location.href = '/financiamentos';
        return;
    }

    // NÃO definir data mínima - permitir cadastro retroativo
    // (para financiamentos em andamento que começaram no passado)

    // Carregar dados
    carregarVigencias();

    // Event listeners
    document.getElementById('form-nova-vigencia').addEventListener('submit', criarVigencia);
    document.getElementById('btn-salvar-obs').addEventListener('click', salvarObservacoes);
});

/**
 * Carregar todas as vigências do financiamento
 */
async function carregarVigencias() {
    try {
        const response = await fetch(`/api/financiamentos/${financiamentoId}/seguros`);
        const result = await response.json();

        if (!result.success) {
            throw new Error(result.error || 'Erro ao carregar vigências');
        }

        const vigencias = result.data;

        // Renderizar vigência atual
        renderizarVigenciaAtual(vigencias);

        // Renderizar histórico
        renderizarHistorico(vigencias);

    } catch (error) {
        console.error('Erro ao carregar vigências:', error);
        mostrarErro('Erro ao carregar vigências: ' + error.message);
    }
}

/**
 * Renderizar vigência atual (card destaque)
 */
function renderizarVigenciaAtual(vigencias) {
    const container = document.getElementById('vigencia-atual');

    // Encontrar vigência ativa
    const vigenciaAtiva = vigencias.find(v => v.vigencia_ativa);

    if (!vigenciaAtiva) {
        container.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i>
                Nenhuma vigência ativa. Cadastre uma nova vigência abaixo.
            </div>
        `;
        return;
    }

    // Formatar data
    const dataInicio = formatarCompetencia(vigenciaAtiva.competencia_inicio);

    container.innerHTML = `
        <div class="row">
            <div class="col-md-4">
                <h6 class="text-muted mb-2">Valor Mensal</h6>
                <h2 class="text-primary mb-0">R$ ${parseFloat(vigenciaAtiva.valor_mensal).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</h2>
            </div>
            <div class="col-md-4">
                <h6 class="text-muted mb-2">Vigente desde</h6>
                <h4 class="mb-0">${dataInicio}</h4>
            </div>
            <div class="col-md-4">
                <h6 class="text-muted mb-2">Status</h6>
                <h4 class="mb-0">
                    <span class="badge badge-success">ATIVO</span>
                </h4>
            </div>
        </div>
        ${vigenciaAtiva.observacoes ? `
        <div class="row mt-3">
            <div class="col-12">
                <h6 class="text-muted mb-2">Observações</h6>
                <p class="mb-0">${vigenciaAtiva.observacoes}</p>
            </div>
        </div>
        ` : ''}
    `;
}

/**
 * Renderizar histórico de vigências
 */
function renderizarHistorico(vigencias) {
    const tbody = document.getElementById('tbody-vigencias');

    if (vigencias.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-muted">
                    Nenhuma vigência cadastrada
                </td>
            </tr>
        `;
        return;
    }

    // Ordenar por competência (decrescente - mais recente primeiro)
    vigencias.sort((a, b) => new Date(b.competencia_inicio) - new Date(a.competencia_inicio));

    tbody.innerHTML = vigencias.map(v => {
        const dataInicio = formatarCompetencia(v.competencia_inicio);
        const dataFim = v.competencia_fim ? formatarCompetencia(v.competencia_fim) : '---';
        const status = v.vigencia_ativa ?
            '<span class="badge badge-success">Ativa</span>' :
            '<span class="badge badge-secondary">Encerrada</span>';
        const valorFormatado = `R$ ${parseFloat(v.valor_mensal).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

        return `
            <tr>
                <td>${dataInicio}</td>
                <td>${dataFim}</td>
                <td><strong>${valorFormatado}</strong></td>
                <td>${status}</td>
                <td>${v.observacoes || '<span class="text-muted">---</span>'}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="abrirModalEdicao(${v.id}, '${(v.observacoes || '').replace(/'/g, "\\'")}')">
                        <i class="fas fa-edit"></i> Editar
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

/**
 * Criar nova vigência
 */
async function criarVigencia(event) {
    event.preventDefault();

    // Pegar valores do formulário
    const competenciaInput = document.getElementById('competencia_inicio').value; // YYYY-MM
    const valorMensal = parseFloat(document.getElementById('valor_mensal').value);
    const saldoDevedor = parseFloat(document.getElementById('saldo_devedor').value);
    const observacoes = document.getElementById('observacoes').value;

    // Converter competência para primeiro dia do mês
    const [ano, mes] = competenciaInput.split('-');
    const competenciaInicio = `${ano}-${mes}-01`;

    // Não validar data retroativa - permitir cadastro de vigências passadas
    // (necessário para financiamentos em andamento)

    // Validar valores
    if (valorMensal <= 0) {
        alert('Valor mensal deve ser maior que zero');
        return;
    }

    if (saldoDevedor <= 0) {
        alert('Saldo devedor deve ser maior que zero');
        return;
    }

    try {
        const response = await fetch(`/api/financiamentos/${financiamentoId}/seguros`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                competencia_inicio: competenciaInicio,
                valor_mensal: valorMensal,
                saldo_devedor_vigencia: saldoDevedor,
                observacoes: observacoes || null
            })
        });

        const result = await response.json();

        if (!result.success) {
            throw new Error(result.error || 'Erro ao criar vigência');
        }

        // Sucesso
        mostrarSucesso('Vigência criada com sucesso!');

        // Limpar formulário
        document.getElementById('form-nova-vigencia').reset();

        // Recarregar lista
        carregarVigencias();

    } catch (error) {
        console.error('Erro ao criar vigência:', error);
        mostrarErro('Erro ao criar vigência: ' + error.message);
    }
}

/**
 * Abrir modal de edição de observações
 */
function abrirModalEdicao(vigenciaId, observacoes) {
    document.getElementById('edit-vigencia-id').value = vigenciaId;
    document.getElementById('edit-observacoes').value = observacoes;
    $('#modalEditarObservacoes').modal('show');
}

/**
 * Salvar observações editadas
 */
async function salvarObservacoes() {
    const vigenciaId = document.getElementById('edit-vigencia-id').value;
    const observacoes = document.getElementById('edit-observacoes').value;

    try {
        const response = await fetch(`/api/financiamentos/seguros/${vigenciaId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                observacoes: observacoes
            })
        });

        const result = await response.json();

        if (!result.success) {
            throw new Error(result.error || 'Erro ao salvar observações');
        }

        // Sucesso
        mostrarSucesso('Observações atualizadas com sucesso!');

        // Fechar modal
        $('#modalEditarObservacoes').modal('hide');

        // Recarregar lista
        carregarVigencias();

    } catch (error) {
        console.error('Erro ao salvar observações:', error);
        mostrarErro('Erro ao salvar observações: ' + error.message);
    }
}

/**
 * Formatar competência (YYYY-MM-DD -> MM/YYYY)
 */
function formatarCompetencia(dataStr) {
    const [ano, mes] = dataStr.split('-');
    return `${mes}/${ano}`;
}

/**
 * Mostrar mensagem de sucesso
 */
function mostrarSucesso(mensagem) {
    // Criar e mostrar toast/alert
    const alertHtml = `
        <div class="alert alert-success alert-dismissible fade show" role="alert" style="position: fixed; top: 20px; right: 20px; z-index: 9999; min-width: 300px;">
            <i class="fas fa-check-circle"></i> ${mensagem}
            <button type="button" class="close" data-dismiss="alert">
                <span>&times;</span>
            </button>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', alertHtml);

    // Auto-remover após 3 segundos
    setTimeout(() => {
        const alert = document.querySelector('.alert-success');
        if (alert) alert.remove();
    }, 3000);
}

/**
 * Mostrar mensagem de erro
 */
function mostrarErro(mensagem) {
    // Criar e mostrar toast/alert
    const alertHtml = `
        <div class="alert alert-danger alert-dismissible fade show" role="alert" style="position: fixed; top: 20px; right: 20px; z-index: 9999; min-width: 300px;">
            <i class="fas fa-exclamation-circle"></i> ${mensagem}
            <button type="button" class="close" data-dismiss="alert">
                <span>&times;</span>
            </button>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', alertHtml);

    // Auto-remover após 5 segundos
    setTimeout(() => {
        const alert = document.querySelector('.alert-danger');
        if (alert) alert.remove();
    }, 5000);
}
