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

function financiamentosIcon(name) {
    const icons = {
        shield: '<path d="M12 4 5 7v5c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V7l-7-3Z"/>',
        trendDown: '<path d="M4 7h5l4 5 7 7"/><path d="M17 19h3v-3"/>',
        edit: '<path d="M5 19h4L19 9a2.1 2.1 0 0 0-3-3L6 16l-1 3Z"/><path d="M14 6l4 4"/>',
        eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.5"/>',
        file: '<path d="M7 4h7l4 4v12H7V4Z"/><path d="M14 4v4h4"/><path d="M9 13h6M9 17h6"/>',
        plus: '<path d="M12 5v14M5 12h14"/>',
        trash: '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>',
        loading: '<path d="M12 6v6l4 2"/><path d="M20 12a8 8 0 1 1-8-8"/>',
        warning: '<path d="M12 5 3.5 19h17L12 5Z"/><path d="M12 10v4M12 17h.1"/>',
        check: '<path d="M5 12.5l4 4L19 7"/>',
        error: '<path d="M6 6l12 12M18 6 6 18"/>',
        info: '<path d="M12 11v6"/><path d="M12 7h.1"/><path d="M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z"/>'
    };

    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" style="width:1em;height:1em;display:inline-block;vertical-align:-0.125em;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;">${icons[name] || icons.info}</svg>`;
}

// ============================================================================
// TOAST NOTIFICATIONS (Feedback Visual)
// ============================================================================

/**
 * Exibe notificação toast não bloqueante
 * @param {string} message - Mensagem a ser exibida (aceita HTML)
 * @param {string} type - Tipo: 'success', 'error', 'warning'
 * @param {number} duration - Duração em ms (padrão: 4000)
 */
function showToast(message, type = 'success', duration = 4000) {
    const toast = document.createElement('div');

    toast.className = `toast toast-${type}`;
    toast.innerHTML = message;

    document.body.appendChild(toast);

    // Trigger animation
    setTimeout(() => {
        toast.classList.add('show');
    }, 50);

    // Remove toast
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

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
                    <label>Saldo Devedor Atual</label>
                    <span>${formatarMoedaDisplay(fin.saldo_devedor_atual || fin.valor_financiado)}</span>
                </div>
                <div class="info-item">
                    <label>Parcelas</label>
                    <span>${fin.parcelas_pagas || 0} / ${fin.total_parcelas || fin.prazo_total_meses}</span>
                </div>
                <div class="info-item">
                    <label>Taxa de Juros Anual</label>
                    <span>${formatarPercentualDisplay(fin.taxa_juros_nominal_anual)}</span>
                </div>
            </div>

            <div class="row-actions financiamento-actions">
                <button class="row-action-button" onclick="verDetalhes(${fin.id})" title="Ver detalhes e parcelas" aria-label="Ver detalhes e parcelas">${financiamentosIcon('eye')}</button>
                ${fin.ativo ? `
                    <button class="row-action-button success" onclick="abrirModalAmortizacao(${fin.id})" title="Amortizacao extra" aria-label="Amortizacao extra">${financiamentosIcon('plus')}</button>
                ` : ''}
                <button class="row-action-button" onclick="abrirDemonstrativo(${fin.id})" title="Demonstrativo anual" aria-label="Demonstrativo anual">${financiamentosIcon('file')}</button>
                <button class="row-action-button" onclick="editarFinanciamento(${fin.id})" title="Editar" aria-label="Editar">${financiamentosIcon('edit')}</button>
                <button class="row-action-button danger" onclick="tentarExcluirFinanciamento(${fin.id}, '${fin.nome.replace(/'/g, "\\'")}')" title="Excluir" aria-label="Excluir">${financiamentosIcon('trash')}</button>
            </div>
        </div>
    `).join('');
}

function atualizarResumo(financiamentos) {
    const ativos = financiamentos.filter(f => f.ativo);

    const totalFinanciado = ativos.reduce((sum, f) => sum + parseFloat(f.valor_financiado), 0);
    const saldoDevedor = ativos.reduce((sum, f) => sum + parseFloat(f.saldo_devedor_atual || f.valor_financiado), 0);

    // Calcular total de parcelas pagas e total de parcelas
    const totalParcelasPagas = ativos.reduce((sum, f) => sum + (f.parcelas_pagas || 0), 0);
    const totalParcelas = ativos.reduce((sum, f) => sum + (f.total_parcelas || 0), 0);

    document.getElementById('total-financiado').textContent = formatarMoedaDisplay(totalFinanciado);
    document.getElementById('saldo-devedor').textContent = formatarMoedaDisplay(saldoDevedor);
    document.getElementById('parcelas-pagas').textContent = `${totalParcelasPagas} / ${totalParcelas}`;
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

    // MODO CRIAÇÃO: Mostrar seção de vigências (obrigatória)
    const secaoVigencias = document.getElementById('secao-vigencias-seguro');
    if (secaoVigencias) secaoVigencias.style.display = 'block';

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

    // Função para normalizar data de input type="month" para YYYY-MM-DD
    function normalizarDataMes(valorInput) {
        if (!valorInput) return null;

        console.log('DEBUG: normalizarDataMes - Input:', valorInput);

        // Se já está no formato YYYY-MM, adicionar -01
        if (/^\d{4}-\d{2}$/.test(valorInput)) {
            const resultado = valorInput + '-01';
            console.log('DEBUG: Formato YYYY-MM detectado, resultado:', resultado);
            return resultado;
        }

        // Se está no formato MM/YYYY, converter para YYYY-MM-01
        const matchMMYYYY = valorInput.match(/^(\d{2})\/(\d{4})$/);
        if (matchMMYYYY) {
            const resultado = `${matchMMYYYY[2]}-${matchMMYYYY[1]}-01`;
            console.log('DEBUG: Formato MM/YYYY detectado, resultado:', resultado);
            return resultado;
        }

        // Se está no formato MM/YYYY-DD (formato incorreto), converter para YYYY-MM-01
        const matchMMYYYYDD = valorInput.match(/^(\d{2})\/(\d{4})-(\d{2})$/);
        if (matchMMYYYYDD) {
            const resultado = `${matchMMYYYYDD[2]}-${matchMMYYYYDD[1]}-01`;
            console.log('DEBUG: Formato MM/YYYY-DD detectado, resultado:', resultado);
            return resultado;
        }

        // Se está no formato DD/MM/YYYY, converter para YYYY-MM-01 (usar apenas mês/ano)
        const matchDDMMYYYY = valorInput.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
        if (matchDDMMYYYY) {
            const dia = matchDDMMYYYY[1];
            const mes = matchDDMMYYYY[2];
            const ano = matchDDMMYYYY[3];
            const resultado = `${ano}-${mes}-01`;
            console.log('DEBUG: Formato DD/MM/YYYY detectado, resultado:', resultado);
            return resultado;
        }

        // Fallback: tentar adicionar -01 (YYYY-MM incompleto)
        console.log('DEBUG: Nenhum formato reconhecido, usando fallback');
        return valorInput + '-01';
    }

    // ========================================================================
    // VIGÊNCIAS DE SEGURO
    // ========================================================================
    // REGRA CRÍTICA:
    // - Ao CRIAR financiamento: vigências vão no payload (obrigatório)
    // - Ao EDITAR financiamento: vigências NÃO vão no payload (usa endpoint separado)
    // ========================================================================

    if (!isEditing) {
        // MODO CRIAÇÃO: Coletar vigências (mínimo 1 obrigatória)
        const vigencias = [];

        // Vigência 1 (obrigatória)
        const data1 = document.getElementById('seg-data-1').value;
        const valor1 = parseMoeda(document.getElementById('seg-valor-1').value);
        if (data1 && valor1 > 0) {
            vigencias.push({
                competencia_inicio: normalizarDataMes(data1),
                valor_mensal: valor1,
                observacoes: document.getElementById('seg-obs-1').value || null
            });
        }

        // Vigência 2 (opcional)
        const data2 = document.getElementById('seg-data-2').value;
        const valor2 = parseMoeda(document.getElementById('seg-valor-2').value);
        if (data2 && valor2 > 0) {
            vigencias.push({
                competencia_inicio: normalizarDataMes(data2),
                valor_mensal: valor2,
                observacoes: document.getElementById('seg-obs-2').value || null
            });
        }

        // Vigência 3 (opcional)
        const data3 = document.getElementById('seg-data-3').value;
        const valor3 = parseMoeda(document.getElementById('seg-valor-3').value);
        if (data3 && valor3 > 0) {
            vigencias.push({
                competencia_inicio: normalizarDataMes(data3),
                valor_mensal: valor3,
                observacoes: document.getElementById('seg-obs-3').value || null
            });
        }

        // Validar se tem pelo menos 1 vigência
        if (vigencias.length === 0) {
            mostrarErro('É obrigatório cadastrar pelo menos uma vigência de seguro (Vigência 1)');
            return;
        }

        // Adicionar vigências aos dados (SOMENTE ao criar)
        dados.vigencias_seguro = vigencias;
    }
    // MODO EDIÇÃO: NÃO envia vigências (usa POST /vigencias-seguro separadamente)

    // DEBUG: Log do payload antes de enviar
    console.log('DEBUG: Payload do financiamento:', JSON.stringify(dados, null, 2));

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

// Função atualizarCampoSeguro() removida - obsoleta após migração para vigências

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

/**
 * Recarrega detalhes do financiamento se o modal estiver aberto
 * Útil após operações que alteram o estado (pagar, amortizar, adicionar vigência)
 */
async function recarregarDetalhesSeAberto(financiamentoId) {
    const modal = document.getElementById('modal-detalhes');
    const isAberto = modal && modal.classList.contains('show');

    if (isAberto && financiamentoId) {
        try {
            const response = await fetch(`/api/financiamentos/${financiamentoId}`);
            const result = await response.json();

            if (result.success) {
                financiamentoAtual = result.data;
                renderizarDetalhes(result.data);
                // Não abre o modal novamente, apenas re-renderiza o conteúdo
            }
        } catch (error) {
            console.error('Erro ao recarregar detalhes:', error);
        }
    }
}

function renderizarDetalhes(dados) {
    document.getElementById('detalhes-titulo').textContent = dados.nome;

    const conteudo = document.getElementById('detalhes-conteudo');

    // Formatar informação de seguro - usar valor real calculado da primeira parcela
    let seguroInfo = 'R$ 0,00';
    if (dados.parcelas && dados.parcelas.length > 0) {
        // Pegar valor do seguro da primeira parcela (já calculado pelo backend)
        const valorSeguroParcela = dados.parcelas[0].valor_seguro;
        seguroInfo = formatarMoedaDisplay(valorSeguroParcela);
    } else if (dados.seguro_tipo === 'fixo') {
        // Fallback para seguro fixo se não houver parcelas
        seguroInfo = formatarMoedaDisplay(dados.valor_seguro_mensal);
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
                <label>Seguro Habitacional</label>
                <span>${seguroInfo}</span>
            </div>
            <div class="info-item">
                <label>Taxa Administrativa</label>
                <span>${formatarMoedaDisplay(dados.taxa_administracao_fixa || 0)}/mês</span>
            </div>
        </div>

        <div style="margin: 20px 0; padding: 15px; background: #f5f5f7; border-radius: 8px;">
            <button class="btn btn-info" onclick="abrirModalSeguro(${dados.id})" style="width: 100%;">
                ${financiamentosIcon('shield')} Gerenciar Seguro Habitacional (Vigências)
            </button>
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
                    <th class="${seguroClass}">Seguro ${seguroTipo === 'percentual_saldo' ? financiamentosIcon('trendDown') : ''}</th>
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
                                `<button class="row-action-button success" onclick="abrirModalPagamento(${p.id})" title="Pagar parcela" aria-label="Pagar parcela">${financiamentosIcon('check')}</button>` :
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

    // Usar valor_previsto_total que vem do backend
    const valorPrevisto = parcela.valor_previsto_total || 0;

    document.getElementById('pagar-parcela-id').value = parcelaId;
    document.getElementById('pagar-data').value = new Date().toISOString().split('T')[0];
    // Preencher com o valor previsto (usuário pode editar se for diferente)
    document.getElementById('pagar-valor').value = formatarMoedaDisplay(valorPrevisto);

    document.getElementById('pagar-info').innerHTML = `
        <p><strong>Parcela:</strong> ${parcela.numero_parcela} / ${financiamentoAtual.prazo_total_meses}</p>
        <p><strong>Vencimento:</strong> ${formatarData(parcela.data_vencimento)}</p>
        <p><strong>Valor Previsto:</strong> ${formatarMoedaDisplay(valorPrevisto)}</p>
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
            carregarFinanciamentos(); // Atualizar listagem e cards de resumo
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
            // Recarregar detalhes se modal estiver aberto (atualiza saldo exibido)
            await recarregarDetalhesSeAberto(financiamentoId);
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
// ADICIONAR VIGÊNCIA DE SEGURO (endpoint separado)
// ============================================================================

/**
 * Adiciona nova vigência de seguro usando endpoint específico
 * IMPORTANTE: Não usa PUT /financiamentos (evita recálculo estrutural)
 */
async function adicionarVigenciaSeguro(financiamentoId, dadosVigencia) {
    try {
        const response = await fetch(`/api/financiamentos/${financiamentoId}/vigencias-seguro`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dadosVigencia)
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso(`Vigência criada! ${result.data.parcelas_atualizadas} parcelas atualizadas.`);
            carregarFinanciamentos();
            // Recarregar detalhes se modal estiver aberto
            await recarregarDetalhesSeAberto(financiamentoId);
            return true;
        } else {
            mostrarErro('Erro ao adicionar vigência: ' + result.error);
            return false;
        }
    } catch (error) {
        mostrarErro('Erro ao adicionar vigência: ' + error.message);
        return false;
    }
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

    // Atualizar listagem se fechar modal de detalhes (pode ter havido alterações)
    if (modalId === 'modal-detalhes') {
        carregarFinanciamentos();
    }
}

// Fechar modal ao clicar fora
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        const modalId = event.target.id;
        event.target.style.display = 'none';

        // Atualizar listagem se fechar modal de detalhes
        if (modalId === 'modal-detalhes') {
            carregarFinanciamentos();
        }
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

            // Armazenar dados do financiamento para uso posterior (ex: saldo_devedor_atual ao salvar vigências)
            window.financiamentoAtual = fin;

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

            // MODO EDIÇÃO: Esconder seção de vigências (usa modal separado)
            const secaoVigencias = document.getElementById('secao-vigencias-seguro');
            if (secaoVigencias) secaoVigencias.style.display = 'none';

            // Preencher taxa de administração
            document.getElementById('fin-taxa-adm').value = formatarMoedaDisplay(fin.taxa_administracao_fixa || 0);

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

/**
 * Tenta excluir financiamento (hard delete)
 * Se não puder, oferece opção de inativar (soft delete)
 */
async function tentarExcluirFinanciamento(id, nome) {
    if (!confirm(`Tem certeza que deseja excluir o financiamento "${nome}"?\n\nAtenção: Esta ação é irreversível e só é permitida se não houver histórico financeiro.`)) {
        return;
    }

    mostrarLoading('Verificando se pode excluir...');

    try {
        const response = await fetch(`${API_BASE}/${id}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (response.ok && result.success) {
            // Exclusão bem-sucedida
            mostrarSucesso('Financiamento excluído com sucesso!');
            carregarFinanciamentos();
        } else if (response.status === 400) {
            // Não pode excluir - tem histórico
            esconderLoading();

            // Mostrar mensagem do backend
            const mensagem = result.message || result.error || 'Não foi possível excluir este financiamento.';

            // Perguntar se quer inativar
            const inativar = confirm(
                `EXCLUSÃO BLOQUEADA\n\n${mensagem}\n\n` +
                `Deseja INATIVAR este financiamento?\n` +
                `(Inativar mantém o histórico mas oculta o contrato da lista de ativos)`
            );

            if (inativar) {
                await inativarFinanciamento(id, nome);
            }
        } else {
            // Outro erro
            mostrarErro(result.message || result.error || 'Erro ao excluir financiamento');
        }
    } catch (error) {
        console.error('Erro:', error);
        mostrarErro('Erro ao comunicar com o servidor');
    }
}

/**
 * Inativa um financiamento (soft delete)
 */
async function inativarFinanciamento(id, nome) {
    mostrarLoading('Inativando financiamento...');

    try {
        // Como não temos endpoint de inativar direto, vamos usar o PUT para atualizar
        const response = await fetch(`${API_BASE}/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ativo: false })
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso(`Financiamento "${nome}" inativado com sucesso!`);
            carregarFinanciamentos();
        } else {
            mostrarErro('Erro ao inativar: ' + (result.message || result.error));
        }
    } catch (error) {
        console.error('Erro:', error);
        mostrarErro('Erro ao inativar financiamento');
    }
}

// ============================================================================
// GERENCIAMENTO DE SEGURO HABITACIONAL (MODAL SEPARADO)
// ============================================================================

/**
 * Abre modal de gerenciamento de seguro e carrega vigências
 * IMPORTANTE: Este modal NÃO chama PUT /financiamentos (evita recálculo estrutural)
 */
async function abrirModalSeguro(financiamentoId) {
    // Armazenar ID do financiamento
    document.getElementById('seguro-financiamento-id').value = financiamentoId;

    // Limpar campos editáveis (antes de preencher dados)
    document.getElementById('seguro-competencia').value = '';
    document.getElementById('seguro-valor').value = '';
    document.getElementById('seguro-observacoes').value = '';

    // Buscar dados do financiamento para preencher saldo devedor e identificar competência atual
    let competenciaAtual = null;
    try {
        const response = await fetch(`/api/financiamentos/${financiamentoId}`);
        const result = await response.json();

        if (result.success) {
            const saldoAtual = result.data.saldo_devedor_atual;
            document.getElementById('seguro-saldo-devedor').value = formatarMoedaDisplay(saldoAtual);

            // Identificar competência da próxima parcela não paga (ou primeira parcela se todas pagas)
            if (result.data.parcelas && result.data.parcelas.length > 0) {
                const proximaParcela = result.data.parcelas.find(p => p.status !== 'pago');

                if (proximaParcela && proximaParcela.data_vencimento) {
                    // Extrair YYYY-MM da data_vencimento
                    competenciaAtual = proximaParcela.data_vencimento.substring(0, 7); // "YYYY-MM-DD" -> "YYYY-MM"
                } else {
                    // Fallback: usar última parcela se todas estiverem pagas
                    const ultimaParcela = result.data.parcelas[result.data.parcelas.length - 1];
                    if (ultimaParcela && ultimaParcela.data_vencimento) {
                        competenciaAtual = ultimaParcela.data_vencimento.substring(0, 7);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Erro ao buscar financiamento:', error);
        document.getElementById('seguro-saldo-devedor').value = 'R$ 0,00';
    }

    // Carregar vigências (passando competência para lógica temporal)
    await carregarVigenciasSeguro(financiamentoId, competenciaAtual);

    // Abrir modal
    abrirModal('modal-seguro');
}

/**
 * Carrega todas as vigências do financiamento
 * @param {number} financiamentoId - ID do financiamento
 * @param {string} competenciaAtual - Competência da parcela atual (YYYY-MM) para lógica temporal
 */
async function carregarVigenciasSeguro(financiamentoId, competenciaAtual = null) {
    try {
        const response = await fetch(`/api/financiamentos/${financiamentoId}/seguros`);
        const result = await response.json();

        if (!result.success) {
            throw new Error(result.error || 'Erro ao carregar vigências');
        }

        const vigencias = result.data;

        // Renderizar vigência atual (usando lógica temporal)
        renderizarVigenciaAtualSeguro(vigencias, competenciaAtual);

        // Renderizar histórico
        renderizarHistoricoVigenciasSeguro(vigencias);

    } catch (error) {
        console.error('Erro ao carregar vigências:', error);
        mostrarErro('Erro ao carregar vigências: ' + error.message);
    }
}

/**
 * Renderiza a vigência aplicável no card de destaque
 * @param {Array} vigencias - Lista de vigências
 * @param {string} competenciaAtual - Competência da parcela atual (YYYY-MM) para lógica temporal
 */
function renderizarVigenciaAtualSeguro(vigencias, competenciaAtual = null) {
    const container = document.getElementById('seguro-vigencia-atual');

    // ========================================================================
    // LÓGICA TEMPORAL: Encontrar vigência aplicável para a competência atual
    // ========================================================================
    let vigenciaAplicavel = null;

    if (competenciaAtual && vigencias.length > 0) {
        console.log(`[Vigência] Usando lógica temporal para competência: ${competenciaAtual}`);

        // Filtrar vigências que iniciam antes ou na competência atual
        const vigenciasAplicaveis = vigencias.filter(v => {
            if (!v.competencia_inicio) return false;

            // Extrair YYYY-MM da competencia_inicio (pode vir como "YYYY-MM-DD")
            const competenciaVigencia = v.competencia_inicio.substring(0, 7);

            return competenciaVigencia <= competenciaAtual;
        });

        // Ordenar por competencia_inicio decrescente e pegar a primeira (mais recente)
        if (vigenciasAplicaveis.length > 0) {
            vigenciasAplicaveis.sort((a, b) => {
                const compA = a.competencia_inicio.substring(0, 7);
                const compB = b.competencia_inicio.substring(0, 7);
                return compB.localeCompare(compA); // Ordem decrescente
            });

            vigenciaAplicavel = vigenciasAplicaveis[0];
            console.log(`[Vigência] Vigência aplicável encontrada: ${vigenciaAplicavel.competencia_inicio.substring(0, 7)}`);
        } else {
            console.warn(`[Vigência] Nenhuma vigência encontrada para competência ${competenciaAtual}`);
        }
    } else {
        // Fallback: usar vigencia_ativa (compatibilidade com casos sem competência)
        console.log('[Vigência] Usando fallback: vigencia_ativa');
        vigenciaAplicavel = vigencias.find(v => v.vigencia_ativa);
    }

    // Se não encontrou vigência aplicável
    if (!vigenciaAplicavel) {
        container.innerHTML = `
            <div style="text-align: center; color: #999;">
                <p>${financiamentosIcon('warning')} Nenhuma vigência aplicável</p>
                <p style="font-size: 13px; margin-top: 5px;">Cadastre uma nova vigência abaixo</p>
            </div>
        `;
        return;
    }

    // Proteger contra campos ausentes
    if (!vigenciaAplicavel.competencia_inicio || !vigenciaAplicavel.valor_mensal) {
        console.error('Vigência aplicável com dados incompletos:', vigenciaAplicavel);
        container.innerHTML = `
            <div style="text-align: center; color: #ff3b30;">
                <p>${financiamentosIcon('warning')} Erro ao carregar vigência aplicável</p>
                <p style="font-size: 13px; margin-top: 5px;">Dados incompletos</p>
            </div>
        `;
        return;
    }

    // Formatar competência (YYYY-MM-DD -> MM/YYYY)
    const [ano, mes] = vigenciaAplicavel.competencia_inicio.split('-');
    const competenciaFormatada = `${mes}/${ano}`;

    // Formatar valor com proteção
    const valorMensal = parseFloat(vigenciaAplicavel.valor_mensal) || 0;

    container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <p style="margin: 0; font-size: 14px; color: #666;">Valor Mensal</p>
                <h2 style="margin: 5px 0; color: #007aff;">R$ ${valorMensal.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</h2>
            </div>
            <div style="text-align: right;">
                <p style="margin: 0; font-size: 14px; color: #666;">Vigente desde</p>
                <p style="margin: 5px 0; font-size: 18px; font-weight: 600;">${competenciaFormatada}</p>
            </div>
        </div>
        ${vigenciaAplicavel.observacoes ? `
        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #ddd;">
            <p style="margin: 0; font-size: 13px; color: #666;">Observações:</p>
            <p style="margin: 5px 0; font-size: 14px;">${vigenciaAplicavel.observacoes}</p>
        </div>
        ` : ''}
    `;
}

/**
 * Renderiza o histórico de vigências na tabela
 */
function renderizarHistoricoVigenciasSeguro(vigencias) {
    const tbody = document.getElementById('seguro-tbody-vigencias');

    if (vigencias.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; color: #999;">Nenhuma vigência cadastrada</td>
            </tr>
        `;
        return;
    }

    // Ordenar por competência (decrescente - mais recente primeiro)
    vigencias.sort((a, b) => new Date(b.competencia_inicio) - new Date(a.competencia_inicio));

    tbody.innerHTML = vigencias.map(v => {
        // Proteger contra dados ausentes
        if (!v.competencia_inicio || v.valor_mensal === undefined || v.valor_mensal === null) {
            console.warn('Vigência com dados incompletos:', v);
            return `
                <tr>
                    <td colspan="6" style="text-align: center; color: #ff3b30;">
                        Vigência #${v.id || '?'} com dados incompletos
                    </td>
                </tr>
            `;
        }

        const [anoInicio, mesInicio] = v.competencia_inicio.split('-');
        const dataInicio = `${mesInicio}/${anoInicio}`;

        let dataFim = '---';
        if (v.competencia_fim) {
            const [anoFim, mesFim] = v.competencia_fim.split('-');
            dataFim = `${mesFim}/${anoFim}`;
        }

        const status = v.vigencia_ativa ?
            '<span class="status-badge status-ativo" style="background: #34c759; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">Ativa</span>' :
            '<span class="status-badge status-encerrada" style="background: #999; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">Encerrada</span>';

        const valorMensal = parseFloat(v.valor_mensal) || 0;
        const valorFormatado = `R$ ${valorMensal.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

        return `
            <tr>
                <td>${dataInicio}</td>
                <td>${dataFim}</td>
                <td><strong>${valorFormatado}</strong></td>
                <td>${status}</td>
                <td>${v.observacoes || '<span style="color: #999;">---</span>'}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary"
                            onclick="editarVigenciaObservacoes(${v.id}, '${(v.observacoes || '').replace(/'/g, "\\'")}', ${v.vigencia_ativa})"
                            style="font-size: 12px; padding: 4px 8px;">
                        ${financiamentosIcon('edit')} Editar
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

/**
 * Salva nova vigência usando endpoint específico
 * IMPORTANTE: NÃO usa PUT /financiamentos (evita recálculo estrutural)
 */
async function salvarNovaVigencia(event) {
    event.preventDefault();

    const financiamentoId = document.getElementById('seguro-financiamento-id').value;
    const competenciaInput = document.getElementById('seguro-competencia').value; // YYYY-MM
    const valorInput = document.getElementById('seguro-valor').value;
    const saldoDevedorInput = document.getElementById('seguro-saldo-devedor').value;
    const observacoes = document.getElementById('seguro-observacoes').value;

    // Validar campos obrigatórios
    if (!competenciaInput) {
        mostrarErro('Competência de início é obrigatória');
        return;
    }

    if (!valorInput) {
        mostrarErro('Valor mensal é obrigatório');
        return;
    }

    const valorMensal = parseMoeda(valorInput);
    const saldoDevedor = parseMoeda(saldoDevedorInput);

    // Validar valores
    if (valorMensal <= 0) {
        mostrarErro('Valor mensal deve ser maior que zero');
        return;
    }

    // Converter competência para YYYY-MM-01
    const competenciaInicio = competenciaInput + '-01';

    try {
        const response = await fetch(`/api/financiamentos/${financiamentoId}/seguros`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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

        // Toast de feedback
        showToast(
            'Seguro atualizado com sucesso.<br>Parcelas futuras recalculadas automaticamente.',
            'success'
        );

        // Limpar formulário (exceto saldo devedor que é readonly)
        document.getElementById('seguro-competencia').value = '';
        document.getElementById('seguro-valor').value = '';
        document.getElementById('seguro-observacoes').value = '';
        // saldo_devedor permanece (readonly, informativo)

        // Recarregar vigências
        await carregarVigenciasSeguro(financiamentoId);

        // Recarregar detalhes do financiamento se modal estiver aberto
        await recarregarDetalhesSeAberto(financiamentoId);

    } catch (error) {
        console.error('Erro ao criar vigência:', error);
        mostrarErro('Erro ao criar vigência: ' + error.message);
    }
}

/**
 * Edita observações de uma vigência
 */
async function editarVigenciaObservacoes(vigenciaId, observacoesAtuais, vigenciaAtiva) {
    const novasObservacoes = prompt('Editar Observações:', observacoesAtuais);

    // Se cancelou ou não alterou, sair
    if (novasObservacoes === null || novasObservacoes === observacoesAtuais) {
        return;
    }

    try {
        const response = await fetch(`/api/financiamentos/seguros/${vigenciaId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                observacoes: novasObservacoes
            })
        });

        const result = await response.json();

        if (!result.success) {
            throw new Error(result.error || 'Erro ao atualizar observações');
        }

        // Sucesso
        mostrarSucesso('Observações atualizadas com sucesso!');

        // Toast de feedback
        showToast(
            'Vigência de seguro atualizada.<br>Parcelas futuras recalculadas automaticamente.',
            'success'
        );

        // Recarregar vigências
        const financiamentoId = document.getElementById('seguro-financiamento-id').value;
        await carregarVigenciasSeguro(financiamentoId);

        // Recarregar detalhes do financiamento se modal estiver aberto
        await recarregarDetalhesSeAberto(financiamentoId);

    } catch (error) {
        console.error('Erro ao atualizar observações:', error);
        mostrarErro('Erro ao atualizar observações: ' + error.message);
    }
}

// ============================================================================
// MENSAGENS DE FEEDBACK
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
        <div style="font-size: 32px; margin-bottom: 15px;">${financiamentosIcon('loading')}</div>
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
        'success': { bg: '#34c759', icone: financiamentosIcon('check') },
        'error': { bg: '#ff3b30', icone: financiamentosIcon('error') },
        'info': { bg: '#007aff', icone: financiamentosIcon('info') }
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
