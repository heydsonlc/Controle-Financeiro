/**
 * JavaScript para Gerenciamento de Financiamentos
 * Funções para manipular CRUD, parcelas, amortizações e demonstrativos
 */

// ============================================================================
// VARIÁVEIS GLOBAIS
// ============================================================================

const API_BASE = '/api/financiamentos';

let financiamentoAtual = null;
let parcelaAtualPagamento = null;

// ============================================================================
// INICIALIZAÇÃO
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    carregarFinanciamentos();
    configurarDataAtual();
});

function configurarDataAtual() {
    const hoje = new Date().toISOString().split('T')[0];
    const dataContrato = document.getElementById('fin-data-contrato');
    const dataPrimeira = document.getElementById('fin-data-primeira');

    if (dataContrato) dataContrato.value = hoje;
    if (dataPrimeira) {
        // Primeira parcela: próximo mês
        const proximoMes = new Date();
        proximoMes.setMonth(proximoMes.getMonth() + 1);
        dataPrimeira.value = proximoMes.toISOString().split('T')[0];
    }
}

// ============================================================================
// CRUD DE FINANCIAMENTOS
// ============================================================================

async function carregarFinanciamentos() {
    try {
        const status = document.getElementById('filtro-status').value;
        const sistema = document.getElementById('filtro-sistema').value;

        let url = '/api/financiamentos?';
        if (status) url += `ativo=${status}&`;

        const response = await fetch(url);
        const result = await response.json();

        if (result.success) {
            let financiamentos = result.data;

            // Filtrar por sistema se necessário
            if (sistema) {
                financiamentos = financiamentos.filter(f => f.sistema_amortizacao === sistema);
            }

            renderizarFinanciamentos(financiamentos);
            atualizarResumo(financiamentos);
        } else {
            mostrarErro('Erro ao carregar financiamentos: ' + result.error);
        }
    } catch (error) {
        mostrarErro('Erro ao carregar financiamentos: ' + error.message);
    }
}

function renderizarFinanciamentos(financiamentos) {
    const lista = document.getElementById('financiamentos-lista');

    if (financiamentos.length === 0) {
        lista.innerHTML = '<p class="loading">Nenhum financiamento encontrado.</p>';
        return;
    }

    lista.innerHTML = financiamentos.map(fin => `
        <div class="financiamento-card">
            <div class="financiamento-header">
                <div class="financiamento-titulo">
                    <h3>${fin.nome}</h3>
                    <p>${fin.produto || 'Sem produto especificado'}</p>
                </div>
                <span class="financiamento-badge badge-${fin.sistema_amortizacao.toLowerCase()}">
                    ${fin.sistema_amortizacao}
                </span>
            </div>

            <div class="financiamento-info">
                <div class="info-item">
                    <label>Valor Financiado</label>
                    <span>${formatarMoedaDisplay(fin.valor_financiado)}</span>
                </div>
                <div class="info-item">
                    <label>Prazo Total</label>
                    <span>${fin.prazo_total_meses} meses</span>
                </div>
                <div class="info-item">
                    <label>Taxa Anual</label>
                    <span>${formatarPercentualDisplay(fin.taxa_juros_nominal_anual)}</span>
                </div>
                <div class="info-item">
                    <label>Data Contrato</label>
                    <span>${formatarData(fin.data_contrato)}</span>
                </div>
            </div>

            <div class="financiamento-actions">
                <button class="btn btn-primary" onclick="verDetalhes(${fin.id})">
                    Ver Detalhes e Parcelas
                </button>
                <button class="btn btn-success" onclick="abrirModalAmortizacao(${fin.id})">
                    Amortização Extra
                </button>
                <button class="btn btn-info" onclick="abrirDemonstrativo(${fin.id})">
                    Demonstrativo Anual
                </button>
                <button class="btn btn-secondary" onclick="editarFinanciamento(${fin.id})">
                    Editar
                </button>
                <button class="btn btn-danger" onclick="excluirFinanciamento(${fin.id}, '${fin.nome.replace(/'/g, "\\'")}')">
                    Excluir
                </button>
            </div>
        </div>
    `).join('');
}

function atualizarResumo(financiamentos) {
    const ativos = financiamentos.filter(f => f.ativo);

    const totalFinanciado = ativos.reduce((sum, f) => sum + parseFloat(f.valor_financiado), 0);
    const saldoDevedor = ativos.reduce((sum, f) => sum + parseFloat(f.saldo_devedor_atual || f.valor_financiado), 0);

    document.getElementById('total-financiado').textContent = formatarMoedaDisplay(totalFinanciado);
    document.getElementById('saldo-devedor').textContent = formatarMoedaDisplay(saldoDevedor);
    document.getElementById('contratos-ativos').textContent = ativos.length;
}

// ============================================================================
// MODAL NOVO FINANCIAMENTO
// ============================================================================

function abrirModalNovoFinanciamento() {
    const form = document.getElementById('form-financiamento');
    form.reset();
    form.removeAttribute('data-editing-id');
    document.querySelector('#modal-financiamento h2').textContent = 'Novo Financiamento';
    configurarDataAtual();
    abrirModal('modal-financiamento');
}

async function salvarFinanciamento(event) {
    event.preventDefault();

    const form = document.getElementById('form-financiamento');
    const editingId = form.getAttribute('data-editing-id');
    const isEditing = !!editingId;

    // Coletar dados básicos
    const dados = {
        nome: document.getElementById('fin-nome').value,
        produto: document.getElementById('fin-produto').value,
        sistema_amortizacao: document.getElementById('fin-sistema').value,
        valor_financiado: parseMoeda(document.getElementById('fin-valor').value),
        prazo_total_meses: parseInt(document.getElementById('fin-prazo').value),
        taxa_juros_nominal_anual: parsePercentual(document.getElementById('fin-taxa').value),
        indexador_saldo: document.getElementById('fin-indexador').value || null,
        data_contrato: document.getElementById('fin-data-contrato').value,
        data_primeira_parcela: document.getElementById('fin-data-primeira').value,
        taxa_administracao_fixa: parseMoeda(document.getElementById('fin-taxa-adm').value) || 0
    };

    // Adicionar dados de seguro baseado no tipo
    const seguroTipo = document.getElementById('fin-seguro-tipo').value;
    dados.seguro_tipo = seguroTipo;

    if (seguroTipo === 'fixo') {
        dados.valor_seguro_mensal = parseMoeda(document.getElementById('fin-seguro-valor').value) || 0;
        dados.seguro_percentual = 0.0006; // valor padrão
    } else { // percentual_saldo
        dados.seguro_percentual = parseFloat(document.getElementById('fin-seguro-percentual').value) || 0.0006;
        dados.valor_seguro_mensal = 0;
    }

    try {
        const url = isEditing ? `/api/financiamentos/${editingId}` : '/api/financiamentos';
        const method = isEditing ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso(isEditing ? 'Financiamento atualizado com sucesso!' : 'Financiamento criado e parcelas geradas com sucesso!');
            fecharModal('modal-financiamento');
            form.removeAttribute('data-editing-id');
            carregarFinanciamentos();
        } else {
            mostrarErro('Erro ao salvar financiamento: ' + result.error);
        }
    } catch (error) {
        mostrarErro('Erro ao salvar financiamento: ' + error.message);
    }
}

function atualizarInfoSistema() {
    const sistema = document.getElementById('fin-sistema').value;
    const infoDiv = document.getElementById('info-sistema');

    const infos = {
        'SAC': 'Amortização constante, juros decrescentes. Parcelas começam mais altas e diminuem.',
        'PRICE': 'Parcelas fixas (PMT constante). Amortização cresce e juros decrescem.',
        'SIMPLES': 'Juros simples fixos sobre o principal. Amortização constante.'
    };

    infoDiv.textContent = infos[sistema] || '';
}

function atualizarCampoSeguro() {
    const tipo = document.getElementById('fin-seguro-tipo').value;
    const campoFixo = document.getElementById('campo-seguro-fixo');
    const campoPercentual = document.getElementById('campo-seguro-percentual');

    if (tipo === 'fixo') {
        campoFixo.style.display = 'block';
        campoPercentual.style.display = 'none';
        // Tornar campo fixo obrigatório
        document.getElementById('fin-seguro-valor').setAttribute('required', 'required');
        document.getElementById('fin-seguro-percentual').removeAttribute('required');
    } else { // percentual_saldo
        campoFixo.style.display = 'none';
        campoPercentual.style.display = 'block';
        // Tornar campo percentual obrigatório
        document.getElementById('fin-seguro-percentual').setAttribute('required', 'required');
        document.getElementById('fin-seguro-valor').removeAttribute('required');
    }
}

// ============================================================================
// DETALHES DO FINANCIAMENTO
// ============================================================================

async function verDetalhes(id) {
    try {
        const response = await fetch(`/api/financiamentos/${id}`);
        const result = await response.json();

        if (result.success) {
            financiamentoAtual = result.data;
            renderizarDetalhes(result.data);
            abrirModal('modal-detalhes');
        } else {
            mostrarErro('Erro ao carregar detalhes: ' + result.error);
        }
    } catch (error) {
        mostrarErro('Erro ao carregar detalhes: ' + error.message);
    }
}

function renderizarDetalhes(dados) {
    document.getElementById('detalhes-titulo').textContent = dados.nome;

    const conteudo = document.getElementById('detalhes-conteudo');

    // Formatar informação de seguro
    let seguroInfo = '';
    if (dados.seguro_tipo === 'percentual_saldo') {
        const percentual = (dados.seguro_percentual * 100).toFixed(2);
        seguroInfo = `${percentual}% sobre saldo (variável)`;
    } else {
        seguroInfo = `${formatarMoedaDisplay(dados.valor_seguro_mensal)} (fixo)`;
    }

    conteudo.innerHTML = `
        <div class="detalhes-header">
            <div class="info-item">
                <label>Sistema</label>
                <span>${dados.sistema_amortizacao}</span>
            </div>
            <div class="info-item">
                <label>Valor Financiado</label>
                <span>${formatarMoedaDisplay(dados.valor_financiado)}</span>
            </div>
            <div class="info-item">
                <label>Saldo Devedor Atual</label>
                <span>${formatarMoedaDisplay(dados.saldo_devedor_atual)}</span>
            </div>
            <div class="info-item">
                <label>Taxa Anual</label>
                <span>${formatarPercentualDisplay(dados.taxa_juros_nominal_anual)}</span>
            </div>
            <div class="info-item">
                <label>Prazo</label>
                <span>${dados.prazo_total_meses} meses</span>
            </div>
            <div class="info-item">
                <label>Indexador</label>
                <span>${dados.indexador_saldo || 'Nenhum'}</span>
            </div>
            <div class="info-item">
                <label>Seguro</label>
                <span class="${dados.seguro_tipo === 'percentual_saldo' ? 'seguro-variavel' : ''}">${seguroInfo}</span>
            </div>
            <div class="info-item">
                <label>Taxa Administrativa</label>
                <span>${formatarMoedaDisplay(dados.taxa_administracao_fixa || 0)}/mês</span>
            </div>
        </div>

        <div class="detalhes-section">
            <h3>Cronograma de Parcelas (${dados.total_parcelas} parcelas)</h3>
            ${renderizarTabelaParcelas(dados.parcelas, dados.seguro_tipo)}
        </div>
    `;
}

function renderizarTabelaParcelas(parcelas, seguroTipo) {
    if (!parcelas || parcelas.length === 0) {
        return '<p>Nenhuma parcela encontrada.</p>';
    }

    const seguroClass = seguroTipo === 'percentual_saldo' ? 'seguro-variavel' : '';

    return `
        <table class="parcelas-tabela">
            <thead>
                <tr>
                    <th>Nº</th>
                    <th>Vencimento</th>
                    <th>Amortização</th>
                    <th>Juros</th>
                    <th class="${seguroClass}">Seguro ${seguroTipo === 'percentual_saldo' ? '📉' : ''}</th>
                    <th>Taxa Adm</th>
                    <th>Total</th>
                    <th>Saldo Após</th>
                    <th>Status</th>
                    <th>Ações</th>
                </tr>
            </thead>
            <tbody>
                ${parcelas.map(p => `
                    <tr>
                        <td>${p.numero_parcela}</td>
                        <td>${formatarData(p.data_vencimento)}</td>
                        <td>${formatarMoedaDisplay(p.valor_amortizacao || p.amortizacao)}</td>
                        <td>${formatarMoedaDisplay(p.valor_juros || p.juros)}</td>
                        <td class="${seguroClass}">${formatarMoedaDisplay(p.valor_seguro || p.seguro || 0)}</td>
                        <td>${formatarMoedaDisplay(p.valor_taxa_adm || p.taxa_administrativa || 0)}</td>
                        <td><strong>${formatarMoedaDisplay(p.valor_previsto_total || p.encargo_total)}</strong></td>
                        <td>${formatarMoedaDisplay(p.saldo_devedor_apos_pagamento || 0)}</td>
                        <td><span class="status-badge status-${p.status}">${p.status}</span></td>
                        <td>
                            ${p.status === 'pendente' ?
                                `<button class="btn btn-sm btn-success" onclick="abrirModalPagamento(${p.id})">Pagar</button>` :
                                `<small>Pago em ${formatarData(p.data_pagamento)}</small>`
                            }
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

// ============================================================================
// PAGAMENTO DE PARCELA
// ============================================================================

function abrirModalPagamento(parcelaId) {
    const parcela = financiamentoAtual.parcelas.find(p => p.id === parcelaId);

    if (!parcela) {
        mostrarErro('Parcela não encontrada');
        return;
    }

    parcelaAtualPagamento = parcela;

    document.getElementById('pagar-parcela-id').value = parcelaId;
    document.getElementById('pagar-data').value = new Date().toISOString().split('T')[0];
    document.getElementById('pagar-valor').value = formatarMoedaDisplay(parcela.encargo_total);

    document.getElementById('pagar-info').innerHTML = `
        <p><strong>Parcela:</strong> ${parcela.numero_parcela} / ${financiamentoAtual.prazo_total_meses}</p>
        <p><strong>Vencimento:</strong> ${formatarData(parcela.data_vencimento)}</p>
        <p><strong>Valor Previsto:</strong> ${formatarMoedaDisplay(parcela.encargo_total)}</p>
    `;

    abrirModal('modal-pagar');
}

async function salvarPagamento(event) {
    event.preventDefault();

    const parcelaId = document.getElementById('pagar-parcela-id').value;
    const dados = {
        valor_pago: parseMoeda(document.getElementById('pagar-valor').value),
        data_pagamento: document.getElementById('pagar-data').value
    };

    try {
        const response = await fetch(`/api/financiamentos/parcelas/${parcelaId}/pagar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso('Pagamento registrado com sucesso!');
            fecharModal('modal-pagar');
            verDetalhes(financiamentoAtual.id); // Recarregar detalhes
        } else {
            mostrarErro('Erro ao registrar pagamento: ' + result.error);
        }
    } catch (error) {
        mostrarErro('Erro ao registrar pagamento: ' + error.message);
    }
}

// ============================================================================
// AMORTIZAÇÃO EXTRAORDINÁRIA
// ============================================================================

function abrirModalAmortizacao(financiamentoId) {
    document.getElementById('form-amortizacao').reset();
    document.getElementById('amort-financiamento-id').value = financiamentoId;
    document.getElementById('amort-data').value = new Date().toISOString().split('T')[0];
    abrirModal('modal-amortizacao');
}

async function salvarAmortizacao(event) {
    event.preventDefault();

    const financiamentoId = document.getElementById('amort-financiamento-id').value;
    const dados = {
        data: document.getElementById('amort-data').value,
        valor: parseMoeda(document.getElementById('amort-valor').value),
        tipo: document.getElementById('amort-tipo').value,
        observacoes: document.getElementById('amort-obs').value
    };

    try {
        const response = await fetch(`/api/financiamentos/${financiamentoId}/amortizacao-extra`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso('Amortização extraordinária registrada! Parcelas recalculadas.');
            fecharModal('modal-amortizacao');
            carregarFinanciamentos();
        } else {
            mostrarErro('Erro ao registrar amortização: ' + result.error);
        }
    } catch (error) {
        mostrarErro('Erro ao registrar amortização: ' + error.message);
    }
}

function atualizarInfoAmortizacao() {
    const tipo = document.getElementById('amort-tipo').value;
    const infoDiv = document.getElementById('info-amortizacao');

    const infos = {
        'reduzir_parcela': 'O valor das próximas parcelas será reduzido. O prazo total permanece o mesmo.',
        'reduzir_prazo': 'O número de parcelas restantes será reduzido. O valor das parcelas permanece o mesmo.'
    };

    infoDiv.textContent = infos[tipo] || '';
}

// ============================================================================
// DEMONSTRATIVO ANUAL
// ============================================================================

function abrirDemonstrativo(financiamentoId) {
    financiamentoAtual = { id: financiamentoId };

    // Preencher anos (ano do contrato até ano atual + 2)
    const selectAno = document.getElementById('demo-ano');
    const anoAtual = new Date().getFullYear();
    selectAno.innerHTML = '';

    for (let ano = anoAtual - 5; ano <= anoAtual + 5; ano++) {
        const option = document.createElement('option');
        option.value = ano;
        option.textContent = ano;
        if (ano === anoAtual) option.selected = true;
        selectAno.appendChild(option);
    }

    abrirModal('modal-demonstrativo');
    carregarDemonstrativo();
}

async function carregarDemonstrativo() {
    const ano = document.getElementById('demo-ano').value;
    const conteudo = document.getElementById('demonstrativo-conteudo');

    conteudo.innerHTML = '<p class="loading">Carregando demonstrativo...</p>';

    try {
        const response = await fetch(`/api/financiamentos/${financiamentoAtual.id}/demonstrativo-anual?ano=${ano}`);
        const result = await response.json();

        if (result.success) {
            renderizarDemonstrativo(result.data);
        } else {
            conteudo.innerHTML = `<p class="loading">Erro: ${result.error}</p>`;
        }
    } catch (error) {
        conteudo.innerHTML = `<p class="loading">Erro: ${error.message}</p>`;
    }
}

function renderizarDemonstrativo(dados) {
    const conteudo = document.getElementById('demonstrativo-conteudo');

    if (dados.meses.length === 0) {
        conteudo.innerHTML = '<p class="loading">Nenhum dado para este ano.</p>';
        return;
    }

    conteudo.innerHTML = `
        <table class="demonstrativo-tabela">
            <thead>
                <tr>
                    <th>Mês</th>
                    <th>Amortização</th>
                    <th>Juros</th>
                    <th>Seguro</th>
                    <th>Taxa Adm</th>
                    <th>Total</th>
                    <th>Saldo Final</th>
                </tr>
            </thead>
            <tbody>
                ${dados.meses.map(m => `
                    <tr>
                        <td>${m.mes_ano}</td>
                        <td>${formatarMoedaDisplay(m.amortizacao)}</td>
                        <td>${formatarMoedaDisplay(m.juros)}</td>
                        <td>${formatarMoedaDisplay(m.seguro)}</td>
                        <td>${formatarMoedaDisplay(m.taxa_administrativa)}</td>
                        <td><strong>${formatarMoedaDisplay(m.total)}</strong></td>
                        <td>${formatarMoedaDisplay(m.saldo_final)}</td>
                    </tr>
                `).join('')}
            </tbody>
            <tfoot>
                <tr>
                    <td>TOTAL ${dados.ano}</td>
                    <td>${formatarMoedaDisplay(dados.totais.amortizacao)}</td>
                    <td>${formatarMoedaDisplay(dados.totais.juros)}</td>
                    <td>${formatarMoedaDisplay(dados.totais.seguro)}</td>
                    <td>${formatarMoedaDisplay(dados.totais.taxa_administrativa)}</td>
                    <td><strong>${formatarMoedaDisplay(dados.totais.total)}</strong></td>
                    <td>-</td>
                </tr>
            </tfoot>
        </table>
    `;
}

// ============================================================================
// FUNÇÕES AUXILIARES DE FORMATAÇÃO
// ============================================================================

function formatarMoeda(input) {
    let valor = input.value.replace(/\D/g, '');
    valor = (valor / 100).toFixed(2);
    input.value = 'R$ ' + valor.replace('.', ',').replace(/(\d)(?=(\d{3})+(?!\d))/g, '$1.');
}

function formatarMoedaDisplay(valor) {
    if (!valor) return 'R$ 0,00';
    const num = parseFloat(valor);
    return 'R$ ' + num.toFixed(2).replace('.', ',').replace(/(\d)(?=(\d{3})+(?!\d))/g, '$1.');
}

function parseMoeda(valor) {
    if (!valor) return 0;
    return parseFloat(valor.replace(/[^\d,]/g, '').replace(',', '.'));
}

function formatarPercentual(input) {
    let valor = input.value.replace(/[^\d,]/g, '');
    input.value = valor;
}

function formatarPercentualDisplay(valor) {
    if (!valor) return '0%';
    return parseFloat(valor).toFixed(2) + '%';
}

function parsePercentual(valor) {
    if (!valor) return 0;
    return parseFloat(valor.replace(',', '.'));
}

function formatarData(data) {
    if (!data) return '-';
    const d = new Date(data + 'T00:00:00');
    return d.toLocaleDateString('pt-BR');
}

// ============================================================================
// FUNÇÕES DE MODAL
// ============================================================================

function abrirModal(modalId) {
    document.getElementById(modalId).style.display = 'block';
}

function fecharModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// Fechar modal ao clicar fora
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
};

// ============================================================================
// EDITAR E EXCLUIR FINANCIAMENTO
// ============================================================================

async function editarFinanciamento(id) {
    try {
        // Buscar dados do financiamento
        const response = await fetch(`${API_BASE}/${id}`);
        const result = await response.json();

        if (result.success) {
            const fin = result.data;

            // Preencher formulário (reutilizar o modal de novo financiamento)
            document.getElementById('fin-nome').value = fin.nome;
            document.getElementById('fin-produto').value = fin.produto || '';
            document.getElementById('fin-sistema').value = fin.sistema_amortizacao;
            document.getElementById('fin-valor').value = formatarMoedaDisplay(fin.valor_financiado);
            document.getElementById('fin-prazo').value = fin.prazo_total_meses;
            document.getElementById('fin-taxa').value = formatarPercentualDisplay(fin.taxa_juros_nominal_anual);
            document.getElementById('fin-indexador').value = fin.indexador_saldo || '';
            document.getElementById('fin-data-contrato').value = fin.data_contrato;
            document.getElementById('fin-data-primeira').value = fin.data_primeira_parcela;

            // Preencher campos de seguro
            const seguroTipo = fin.seguro_tipo || 'fixo';
            document.getElementById('fin-seguro-tipo').value = seguroTipo;

            if (seguroTipo === 'fixo') {
                document.getElementById('fin-seguro-valor').value = formatarMoedaDisplay(fin.valor_seguro_mensal || 0);
            } else {
                document.getElementById('fin-seguro-percentual').value = fin.seguro_percentual || 0.0006;
            }

            // Preencher taxa de administração
            document.getElementById('fin-taxa-adm').value = formatarMoedaDisplay(fin.taxa_administracao_fixa || 0);

            // Atualizar visualização dos campos de seguro
            atualizarCampoSeguro();

            // Alterar título do modal e adicionar ID para update
            document.querySelector('#modal-financiamento h2').textContent = 'Editar Financiamento';
            document.getElementById('form-financiamento').setAttribute('data-editing-id', id);

            abrirModal('modal-financiamento');
        } else {
            mostrarErro('Erro ao carregar financiamento: ' + result.error);
        }
    } catch (error) {
        console.error('Erro:', error);
        mostrarErro('Erro ao carregar financiamento para edição');
    }
}

async function excluirFinanciamento(id, nome) {
    if (!confirm(`Tem certeza que deseja excluir o financiamento "${nome}"?\n\nEsta ação irá inativar o contrato.`)) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/${id}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso('Financiamento inativado com sucesso!');
            carregarFinanciamentos();
        } else {
            mostrarErro('Erro ao excluir: ' + result.error);
        }
    } catch (error) {
        console.error('Erro:', error);
        mostrarErro('Erro ao excluir financiamento');
    }
}

// ============================================================================
// MENSAGENS DE FEEDBACK
// ============================================================================

function mostrarSucesso(mensagem) {
    alert('OK ' + mensagem);
}

function mostrarErro(mensagem) {
    alert('ERRO ' + mensagem);
}
