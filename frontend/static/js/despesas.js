/**
 * JavaScript para gerenciamento de Despesas
 */

const API_URL = '/api/despesas';
const API_CONTAS_URL = '/api/despesas/contas';  // Endpoint para contas a pagar (execução)
const CATEGORIAS_URL = '/api/categorias';
let despesaEditando = null;
let despesas = [];
let categorias = [];

// Carregar dados ao iniciar a página
document.addEventListener('DOMContentLoaded', () => {
    // Definir mês atual no filtro de competência
    const hoje = new Date();
    const mes = String(hoje.getMonth() + 1).padStart(2, '0');
    const ano = hoje.getFullYear();
    const mesAtual = `${mes}/${ano}`;
    document.getElementById('filtro-competencia').value = mesAtual;

    carregarCategorias();
    carregarDespesas();

    // Event listeners para filtros
    document.getElementById('filtro-categoria').addEventListener('change', aplicarFiltros);
    document.getElementById('filtro-status').addEventListener('change', aplicarFiltros);
    document.getElementById('filtro-mes').addEventListener('change', aplicarFiltros);
    document.getElementById('filtro-competencia').addEventListener('change', aplicarFiltros);

    // Event listener para calcular competência automaticamente quando data de vencimento mudar
    document.getElementById('data_vencimento').addEventListener('change', calcularCompetenciaAutomaticamente);
});

/**
 * Carrega categorias para os selects
 */
async function carregarCategorias() {
    try {
        const response = await fetch(CATEGORIAS_URL);
        const data = await response.json();

        if (data.success) {
            categorias = data.data;

            // Preencher select de categoria no formulário
            const selectForm = document.getElementById('categoria_id');
            selectForm.innerHTML = '<option value="">Selecione...</option>';
            categorias.forEach(cat => {
                if (cat.ativo) {
                    selectForm.innerHTML += `<option value="${cat.id}">${cat.nome}</option>`;
                }
            });

            // Preencher select de filtro
            const selectFiltro = document.getElementById('filtro-categoria');
            selectFiltro.innerHTML = '<option value="">Todas as categorias</option>';
            categorias.forEach(cat => {
                if (cat.ativo) {
                    selectFiltro.innerHTML += `<option value="${cat.id}">${cat.nome}</option>`;
                }
            });
        }
    } catch (error) {
        console.error('Erro ao carregar categorias:', error);
    }
}

/**
 * Carrega todas as despesas da API
 */
async function carregarDespesas() {
    try {
        const response = await fetch(API_URL);
        const data = await response.json();

        if (!data.success) {
            mostrarErro('Erro ao carregar despesas: ' + data.error);
            return;
        }

        despesas = data.data;
        aplicarFiltros();

    } catch (error) {
        console.error('Erro ao carregar despesas:', error);
        mostrarErro('Erro ao carregar despesas. Por favor, tente novamente.');
    }
}

/**
 * Calcula competência automaticamente quando data de vencimento é alterada
 */
function calcularCompetenciaAutomaticamente() {
    const dataVencimento = document.getElementById('data_vencimento').value;

    if (dataVencimento) {
        // Criar data e subtrair 1 mês
        const data = new Date(dataVencimento + 'T00:00:00');
        data.setMonth(data.getMonth() - 1);

        // Formatar como YYYY-MM
        const ano = data.getFullYear();
        const mes = String(data.getMonth() + 1).padStart(2, '0');
        const competencia = `${ano}-${mes}`;

        // Preencher campo se estiver vazio
        const campoCompetencia = document.getElementById('mes_competencia');
        if (!campoCompetencia.value) {
            campoCompetencia.value = competencia;
        }
    }
}

/**
 * Aplica filtros e atualiza a lista
 */
function aplicarFiltros() {
    const categoriaFiltro = document.getElementById('filtro-categoria').value;
    const statusFiltro = document.getElementById('filtro-status').value;
    const mesFiltro = document.getElementById('filtro-mes').value;
    const competenciaFiltro = document.getElementById('filtro-competencia').value;

    let despesasFiltradas = [...despesas];

    // Filtrar por categoria
    if (categoriaFiltro) {
        despesasFiltradas = despesasFiltradas.filter(d => d.categoria_id == categoriaFiltro);
    }

    // Filtrar por status
    if (statusFiltro) {
        if (statusFiltro === 'pago') {
            despesasFiltradas = despesasFiltradas.filter(d => d.pago);
        } else if (statusFiltro === 'pendente') {
            despesasFiltradas = despesasFiltradas.filter(d => !d.pago);
        }
    }

    // Filtrar por mês de vencimento (formato brasileiro MM/AAAA -> YYYY-MM)
    if (mesFiltro && mesFiltro.length === 7) {
        const mesISO = converterMesAnoBRparaISO(mesFiltro);
        if (mesISO) {
            const anoMes = mesISO.substring(0, 7); // Pega apenas YYYY-MM
            despesasFiltradas = despesasFiltradas.filter(d => {
                if (!d.data_vencimento) return false;
                return d.data_vencimento.startsWith(anoMes);
            });
        }
    }

    // Filtrar por mês de competência (formato brasileiro MM/AAAA -> YYYY-MM)
    if (competenciaFiltro && competenciaFiltro.length === 7) {
        const competenciaISO = converterMesAnoBRparaISO(competenciaFiltro);
        if (competenciaISO) {
            const anoMes = competenciaISO.substring(0, 7); // Pega apenas YYYY-MM
            despesasFiltradas = despesasFiltradas.filter(d => {
                if (!d.mes_competencia) return false;
                return d.mes_competencia === anoMes;
            });
        }
    }

    renderizarDespesas(despesasFiltradas);
    atualizarResumo(despesasFiltradas);
}

/**
 * Renderiza a lista de despesas
 */
function renderizarDespesas(despesasParaRenderizar) {
    const lista = document.getElementById('despesas-lista');

    if (despesasParaRenderizar.length === 0) {
        lista.innerHTML = `
            <div class="empty-state">
                <h3>Nenhuma despesa encontrada</h3>
                <p>Clique em "Nova Despesa" para começar</p>
            </div>
        `;
        return;
    }

    lista.innerHTML = despesasParaRenderizar.map(despesa => {
        // Verificar se é fatura de cartão (nova lógica)
        const isFaturaCartao = despesa.is_fatura_cartao === true;
        const isAgrupado = despesa.agrupado === true || isFaturaCartao;

        // Usar a categoria que vem do backend (já completa) ou buscar no array local
        const categoria = despesa.categoria || (despesa.categoria_id ? categorias.find(c => c.id === despesa.categoria_id) : null);
        const statusClass = despesa.pago ? 'pago' : 'pendente';
        const statusTexto = despesa.pago ? 'Paga' : 'Pendente';

        let dataVencimento = '';
        if (despesa.data_vencimento) {
            const data = new Date(despesa.data_vencimento + 'T00:00:00');
            dataVencimento = data.toLocaleDateString('pt-BR');
        }

        let dataPagamento = '';
        if (despesa.data_pagamento) {
            const data = new Date(despesa.data_pagamento + 'T00:00:00');
            dataPagamento = data.toLocaleDateString('pt-BR');
        }

        // Informações específicas de fatura de cartão
        let infoFaturaCartao = '';
        if (isFaturaCartao) {
            const valorPlanejado = parseFloat(despesa.valor_planejado || 0);
            const valorExecutado = parseFloat(despesa.valor_executado || 0);
            const estouro = despesa.estouro_orcamento === true;

            infoFaturaCartao = `
                <div class="fatura-cartao-info">
                    <div class="valores-comparacao">
                        <div class="valor-item ${!despesa.pago ? 'valor-destaque' : ''}">
                            <span class="valor-label">💰 Planejado:</span>
                            <span class="valor-numero">R$ ${valorPlanejado.toFixed(2).replace('.', ',')}</span>
                        </div>
                        <div class="valor-item ${despesa.pago ? 'valor-destaque' : ''}">
                            <span class="valor-label">💳 Executado:</span>
                            <span class="valor-numero">R$ ${valorExecutado.toFixed(2).replace('.', ',')}</span>
                        </div>
                    </div>
                    ${estouro ? `
                        <div class="alerta-estouro">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                                <line x1="12" y1="9" x2="12" y2="13"></line>
                                <line x1="12" y1="17" x2="12.01" y2="17"></line>
                            </svg>
                            <span>Orçamento ultrapassado em R$ ${(valorExecutado - valorPlanejado).toFixed(2).replace('.', ',')}</span>
                        </div>
                    ` : ''}
                </div>
            `;
        }

        // Para faturas de cartão, mostrar apenas botão de pagar (se pendente)
        const acoesHTML = isFaturaCartao ? `
            <div class="despesa-actions">
                ${!despesa.pago ? `
                    <button class="btn-icon btn-pagar" onclick="marcarComoPago(${despesa.id})" title="Pagar fatura">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    </button>
                ` : ''}
            </div>
        ` : (isAgrupado ? '' : `
            <div class="despesa-actions">
                <button class="btn-icon" onclick="editarDespesa(${despesa.id})" title="Editar">
                    ✏️
                </button>
                ${!despesa.pago ? `
                    <button class="btn-icon btn-pagar" onclick="marcarComoPago(${despesa.id})" title="Marcar como pago">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    </button>
                ` : ''}
            </div>
        `);

        return `
            <div class="despesa-card ${statusClass} ${isFaturaCartao ? 'fatura-cartao' : ''} ${isAgrupado ? 'agrupado' : ''} ${despesa.estouro_orcamento ? 'com-estouro' : ''}">
                <div class="despesa-info">
                    <div class="despesa-header">
                        <div class="despesa-nome">
                            <span class="status-indicador status-indicador-${statusClass}"></span>
                            ${despesa.nome}
                            ${isFaturaCartao ? '<span class="badge-fatura">Fatura Virtual</span>' : ''}
                        </div>
                        <div class="despesa-valor ${isFaturaCartao ? 'valor-fatura' : ''}">
                            R$ ${parseFloat(despesa.valor).toFixed(2).replace('.', ',')}
                            ${isFaturaCartao && !despesa.pago ? '<span class="valor-tipo">(Planejado)</span>' : ''}
                            ${isFaturaCartao && despesa.pago ? '<span class="valor-tipo">(Executado)</span>' : ''}
                        </div>
                        ${categoria ? `
                            <div class="despesa-categoria">
                                <span class="categoria-cor" style="background-color: ${categoria.cor}"></span>
                                ${categoria.nome}
                            </div>
                        ` : ''}
                    </div>

                    ${infoFaturaCartao}

                    ${despesa.descricao && !isFaturaCartao ? `<div style="color: rgba(255,255,255,0.8); font-size: 0.9em;">${despesa.descricao}</div>` : ''}

                    <div class="despesa-detalhes">
                        ${dataVencimento ? `<span>📅 Venc: ${dataVencimento}</span>` : ''}
                        ${dataPagamento ? `<span>✓ Pago: ${dataPagamento}</span>` : ''}
                        ${despesa.mes_competencia ? `<span>💼 Competência: ${formatarCompetencia(despesa.mes_competencia)}</span>` : ''}
                        ${despesa.recorrente && !isAgrupado ? `<span>🔄 ${formatarTipoRecorrencia(despesa.tipo_recorrencia)}</span>` : ''}
                    </div>
                </div>

                ${acoesHTML}
            </div>
        `;
    }).join('');
}

/**
 * Atualiza os cards de resumo
 */
function atualizarResumo(despesasParaResumir) {
    const total = despesasParaResumir.reduce((sum, d) => sum + parseFloat(d.valor), 0);
    const totalPendentes = despesasParaResumir.filter(d => !d.pago).reduce((sum, d) => sum + parseFloat(d.valor), 0);
    const totalPagas = despesasParaResumir.filter(d => d.pago).reduce((sum, d) => sum + parseFloat(d.valor), 0);

    document.getElementById('total-geral').textContent = `R$ ${total.toFixed(2).replace('.', ',')}`;
    document.getElementById('total-pendentes').textContent = `R$ ${totalPendentes.toFixed(2).replace('.', ',')}`;
    document.getElementById('total-pagas').textContent = `R$ ${totalPagas.toFixed(2).replace('.', ',')}`;
}

/**
 * Abre o modal para criar nova despesa
 */
function abrirModal() {
    despesaEditando = null;
    document.getElementById('modal-titulo').textContent = 'Nova Despesa';
    document.getElementById('form-despesa').reset();
    document.getElementById('despesa-id').value = '';
    document.getElementById('tipo-recorrencia-group').style.display = 'none';
    document.getElementById('campos-semanal').style.display = 'none';
    document.getElementById('campos-consorcio').style.display = 'none';
    document.getElementById('campo-valor-reajuste').style.display = 'none';
    document.getElementById('btn-deletar-modal').style.display = 'none';
    document.getElementById('e_consorcio').checked = false;
    document.getElementById('modal-despesa').style.display = 'block';
}

/**
 * Fecha o modal
 */
function fecharModal() {
    document.getElementById('modal-despesa').style.display = 'none';
    document.getElementById('campos-consorcio').style.display = 'none';
    document.getElementById('campo-valor-reajuste').style.display = 'none';
    document.getElementById('e_consorcio').checked = false;
    despesaEditando = null;
}

/**
 * Edita uma despesa existente
 */
async function editarDespesa(id) {
    try {
        const response = await fetch(`${API_URL}/${id}`);
        const data = await response.json();

        if (!data.success) {
            alert('Erro ao carregar despesa: ' + data.error);
            return;
        }

        const despesa = data.data;

        // Se for parcela de consórcio, perguntar tipo de edição primeiro
        if (despesa.tipo === 'Consorcio') {
            // Guardar ID temporariamente
            window.despesaConsorcioEditando = id;
            // Mostrar modal de escolha
            document.getElementById('modal-tipo-edicao').style.display = 'block';
            return;
        }

        despesaEditando = id;

        // Preencher formulário
        document.getElementById('modal-titulo').textContent = 'Editar Despesa';
        document.getElementById('despesa-id').value = despesa.id;
        document.getElementById('nome').value = despesa.nome;
        document.getElementById('descricao').value = despesa.descricao || '';
        document.getElementById('valor').value = despesa.valor;
        document.getElementById('categoria_id').value = despesa.categoria_id;
        document.getElementById('data_vencimento').value = despesa.data_vencimento || '';
        document.getElementById('data_pagamento').value = despesa.data_pagamento || '';
        document.getElementById('pago').checked = despesa.pago;
        document.getElementById('recorrente').checked = despesa.recorrente;
        document.getElementById('mes_competencia').value = despesa.mes_competencia || '';

        // Processar tipo de recorrência
        let tipoRecorrencia = despesa.tipo_recorrencia || 'mensal';
        if (tipoRecorrencia.startsWith('semanal_')) {
            // Parse do formato semanal_freq_dia
            const partes = tipoRecorrencia.split('_');
            if (partes.length === 3) {
                document.getElementById('tipo_recorrencia').value = 'semanal';
                document.getElementById('frequencia_semanas').value = partes[1];
                document.getElementById('dia_semana').value = partes[2];
            } else {
                document.getElementById('tipo_recorrencia').value = tipoRecorrencia;
            }
        } else {
            document.getElementById('tipo_recorrencia').value = tipoRecorrencia;
        }

        // Mostrar campo de recorrência se necessário
        document.getElementById('tipo-recorrencia-group').style.display = despesa.recorrente ? 'block' : 'none';

        // Mostrar campos semanais se for semanal
        if (despesa.recorrente && despesa.tipo_recorrencia && despesa.tipo_recorrencia.startsWith('semanal')) {
            document.getElementById('campos-semanal').style.display = 'block';
        } else {
            document.getElementById('campos-semanal').style.display = 'none';
        }

        // Mostrar botão deletar no modal
        document.getElementById('btn-deletar-modal').style.display = 'block';

        // Abrir modal
        document.getElementById('modal-despesa').style.display = 'block';

    } catch (error) {
        console.error('Erro ao carregar despesa:', error);
        alert('Erro ao carregar despesa. Por favor, tente novamente.');
    }
}

/**
 * Salva despesa (criar ou atualizar)
 */
async function salvarDespesa(event) {
    event.preventDefault();

    const id = document.getElementById('despesa-id').value;
    const eConsorcio = document.getElementById('e_consorcio').checked;

    // Se for consórcio, usar API de consórcios
    if (eConsorcio) {
        await salvarConsorcio(id);
        return;
    }

    // Lógica normal de despesa
    const recorrente = document.getElementById('recorrente').checked;
    let tipoRecorrencia = document.getElementById('tipo_recorrencia').value;

    // Se for recorrência semanal, criar string codificada com dia e frequência
    if (recorrente && tipoRecorrencia === 'semanal') {
        const diaSemana = document.getElementById('dia_semana').value;
        const freqSemanas = document.getElementById('frequencia_semanas').value || '1';

        if (!diaSemana) {
            alert('Por favor, selecione o dia da semana para a recorrência semanal.');
            return;
        }

        // Formato: semanal_frequencia_dia (ex: semanal_1_1 = toda semana, segunda-feira)
        tipoRecorrencia = `semanal_${freqSemanas}_${diaSemana}`;
    }

    const dados = {
        nome: document.getElementById('nome').value.trim(),
        descricao: document.getElementById('descricao').value.trim(),
        valor: parseFloat(document.getElementById('valor').value),
        categoria_id: parseInt(document.getElementById('categoria_id').value),
        data_vencimento: document.getElementById('data_vencimento').value || null,
        data_pagamento: document.getElementById('data_pagamento').value || null,
        pago: document.getElementById('pago').checked,
        recorrente: recorrente,
        tipo_recorrencia: tipoRecorrencia,
        mes_competencia: document.getElementById('mes_competencia').value || null
    };

    try {
        // Se estiver editando parcela de consórcio, adicionar tipo de edição na URL
        let url = id ? `${API_URL}/${id}` : API_URL;
        if (id && window.tipoEdicaoConsorcio) {
            url += `?tipo_edicao=${window.tipoEdicaoConsorcio}`;
        }
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const data = await response.json();

        if (!data.success) {
            alert('Erro: ' + data.error);
            return;
        }

        alert(data.message);
        fecharModal();
        carregarDespesas();

    } catch (error) {
        console.error('Erro ao salvar despesa:', error);
        alert('Erro ao salvar despesa. Por favor, tente novamente.');
    }
}

/**
 * Salva consórcio (criar ou atualizar)
 */
async function salvarConsorcio(id) {
    // Validar campos obrigatórios do consórcio
    const numeroParcelas = document.getElementById('numero_parcelas_consorcio').value;
    const mesInicioBR = document.getElementById('mes_inicio_consorcio').value;

    if (!numeroParcelas || !mesInicioBR) {
        alert('Por favor, preencha o número de parcelas e o mês de início do consórcio.');
        return;
    }

    // Converter data brasileira MM/AAAA para ISO YYYY-MM-DD
    const mesInicioISO = converterMesAnoBRparaISO(mesInicioBR);
    if (!mesInicioISO) {
        alert('Formato de data inválido no mês de início. Use MM/AAAA (exemplo: 05/2025)');
        return;
    }

    // Preparar dados do consórcio
    const dados = {
        nome: document.getElementById('nome').value.trim(),
        valor_inicial: parseFloat(document.getElementById('valor').value),
        numero_parcelas: parseInt(numeroParcelas),
        mes_inicio: mesInicioISO,
        tipo_reajuste: document.getElementById('tipo_reajuste').value,
        valor_reajuste: parseFloat(document.getElementById('valor_reajuste').value) || 0,
        mes_contemplacao: null,
        valor_premio: null,
        item_despesa_id: parseInt(document.getElementById('categoria_id').value) || null,
        item_receita_id: null
    };

    // Adicionar contemplação se informado
    const mesContemplacaoBR = document.getElementById('mes_contemplacao').value;
    const valorPremio = document.getElementById('valor_premio').value;

    if (mesContemplacaoBR) {
        const mesContemplacaoISO = converterMesAnoBRparaISO(mesContemplacaoBR);
        if (!mesContemplacaoISO) {
            alert('Formato de data inválido no mês de contemplação. Use MM/AAAA (exemplo: 06/2027)');
            return;
        }
        dados.mes_contemplacao = mesContemplacaoISO;
    }

    if (valorPremio) {
        dados.valor_premio = parseFloat(valorPremio);
    }

    try {
        const url = id ? `/api/consorcios/${id}` : '/api/consorcios';
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const data = await response.json();

        if (!data.success) {
            alert('Erro ao salvar consórcio: ' + data.error);
            return;
        }

        // Mostrar informações sobre o que foi gerado
        let mensagem = 'Consórcio salvo com sucesso!\n\n';

        if (data.parcelas_geradas) {
            mensagem += `✓ ${data.parcelas_geradas} parcelas geradas automaticamente\n`;
        }

        if (data.receita_gerada) {
            mensagem += `✓ Receita de contemplação criada\n`;
        }

        alert(mensagem);
        fecharModal();
        carregarDespesas();

    } catch (error) {
        console.error('Erro ao salvar consórcio:', error);
        alert('Erro ao salvar consórcio. Por favor, tente novamente.');
    }
}

/**
 * Marca uma despesa como paga
 */
/**
 * Abre modal para marcar despesa como paga
 */
function marcarComoPago(id) {
    // Buscar despesa na lista
    const despesa = despesas.find(d => d.id === id);
    if (!despesa) {
        alert('Despesa não encontrada');
        return;
    }

    const isFaturaCartao = despesa.is_fatura_cartao === true;

    // Guardar no modal se é fatura de cartão
    document.getElementById('pagar-despesa-id').value = id;
    document.getElementById('pagar-despesa-id').dataset.isFaturaCartao = isFaturaCartao;

    // Preencher dados básicos
    document.getElementById('pagar-nome-despesa').textContent = despesa.nome;
    document.getElementById('pagar-data').value = new Date().toISOString().split('T')[0];

    // Se for fatura de cartão, criar interface especial
    if (isFaturaCartao) {
        const valorPlanejado = parseFloat(despesa.valor_planejado || 0);
        const valorExecutado = parseFloat(despesa.valor_executado || 0);
        const estouro = despesa.estouro_orcamento === true;

        const form = document.getElementById('form-pagar');

        // Adicionar aviso especial ANTES das opções de pagamento
        const avisoExistente = form.querySelector('.aviso-fatura-cartao');
        if (!avisoExistente) {
            const avisoHTML = `
                <div class="aviso-fatura-cartao" style="background: linear-gradient(135deg, rgba(0, 122, 255, 0.1) 0%, rgba(0, 122, 255, 0.05) 100%); padding: 16px; border-radius: 10px; margin-bottom: 20px; border-left: 3px solid #007aff;">
                    <h4 style="margin: 0 0 12px 0; color: #1d1d1f; font-size: 0.95em; font-weight: 600;">💳 Fatura de Cartão de Crédito</h4>

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">
                        <div style="background: #ffffff; padding: 12px; border-radius: 8px; border: 1px solid rgba(0, 0, 0, 0.06);">
                            <div style="font-size: 0.75em; color: #6e6e73; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;">💰 Planejado (Orçamento)</div>
                            <div style="font-size: 1.2em; font-weight: 600; color: #1d1d1f;">R$ ${valorPlanejado.toFixed(2).replace('.', ',')}</div>
                        </div>
                        <div style="background: #ffffff; padding: 12px; border-radius: 8px; border: 1px solid rgba(0, 0, 0, 0.06);">
                            <div style="font-size: 0.75em; color: #6e6e73; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;">💳 Executado (Gasto Real)</div>
                            <div style="font-size: 1.2em; font-weight: 600; color: ${estouro ? '#ff3b30' : '#34c759'};">R$ ${valorExecutado.toFixed(2).replace('.', ',')}</div>
                        </div>
                    </div>

                    ${estouro ? `
                        <div style="background: rgba(255, 59, 48, 0.1); padding: 10px; border-radius: 6px; margin-bottom: 12px; border: 1px solid rgba(255, 59, 48, 0.2);">
                            <span style="color: #ff3b30; font-size: 0.85em; font-weight: 500;">⚠️ Orçamento ultrapassado em R$ ${(valorExecutado - valorPlanejado).toFixed(2).replace('.', ',')}</span>
                        </div>
                    ` : ''}

                    <div style="background: rgba(0, 122, 255, 0.08); padding: 10px; border-radius: 6px; font-size: 0.85em; color: #1d1d1f; line-height: 1.5;">
                        <strong>O que acontece ao pagar:</strong><br>
                        O valor da fatura mudará de <strong>Planejado</strong> (R$ ${valorPlanejado.toFixed(2).replace('.', ',')}) para <strong>Executado</strong> (R$ ${valorExecutado.toFixed(2).replace('.', ',')})
                    </div>
                </div>
            `;

            // Inserir no início do formulário
            const primeiroElemento = form.querySelector('.form-group');
            primeiroElemento.insertAdjacentHTML('beforebegin', avisoHTML);
        }

        // Configurar valor para executado
        document.getElementById('pagar-valor-previsto').value = valorExecutado;
        document.getElementById('pagar-valor-previsto-display').textContent = `R$ ${valorExecutado.toFixed(2).replace('.', ',')}`;
        document.getElementById('pagar-valor-pago').value = valorExecutado;

        // Trocar texto para "Valor Executado"
        const labelTotal = document.querySelector('input[name="tipo-pagamento"][value="total"]').closest('label').querySelector('span');
        labelTotal.innerHTML = `Valor Executado (Gasto Real): <strong>R$ ${valorExecutado.toFixed(2).replace('.', ',')}</strong>`;
    } else {
        // Remover aviso se existir
        const avisoExistente = document.querySelector('.aviso-fatura-cartao');
        if (avisoExistente) {
            avisoExistente.remove();
        }

        // Despesa normal
        const valorFormatado = `R$ ${parseFloat(despesa.valor).toFixed(2).replace('.', ',')}`;
        document.getElementById('pagar-valor-previsto').value = despesa.valor;
        document.getElementById('pagar-valor-previsto-display').textContent = valorFormatado;
        document.getElementById('pagar-valor-pago').value = despesa.valor;

        // Texto padrão
        const labelTotal = document.querySelector('input[name="tipo-pagamento"][value="total"]').closest('label').querySelector('span');
        labelTotal.innerHTML = `Valor Total: <strong>${valorFormatado}</strong>`;
    }

    // Resetar para o estado inicial
    document.querySelector('input[name="tipo-pagamento"][value="total"]').checked = true;
    document.getElementById('campo-valor-custom').style.display = 'none';

    // Abrir modal
    document.getElementById('modal-pagar').style.display = 'block';
}

/**
 * Alterna visibilidade do campo de valor customizado
 */
function alternarCampoValor() {
    const tipoPagamento = document.querySelector('input[name="tipo-pagamento"]:checked').value;
    const campoValor = document.getElementById('campo-valor-custom');
    const inputValor = document.getElementById('pagar-valor-pago');

    if (tipoPagamento === 'parcial') {
        campoValor.style.display = 'block';
        inputValor.required = true;
        inputValor.focus();
    } else {
        campoValor.style.display = 'none';
        inputValor.required = false;
    }
}

/**
 * Confirma o pagamento (único botão)
 */
async function confirmarPagamento(event) {
    event.preventDefault();

    const id = document.getElementById('pagar-despesa-id').value;
    const tipoPagamento = document.querySelector('input[name="tipo-pagamento"]:checked').value;
    const valorPrevisto = parseFloat(document.getElementById('pagar-valor-previsto').value);
    const dataPagamento = document.getElementById('pagar-data').value;

    // Determinar o valor a ser pago
    let valorPago;
    if (tipoPagamento === 'total') {
        // Pagar valor total - não envia valor_pago, backend usará o valor previsto
        valorPago = null;
    } else {
        // Pagar valor customizado
        valorPago = parseFloat(document.getElementById('pagar-valor-pago').value);

        if (!valorPago || valorPago <= 0) {
            alert('Por favor, informe um valor válido');
            return;
        }
    }

    try {
        const payload = {
            data_pagamento: dataPagamento
        };

        // Adicionar valor_pago apenas se for diferente do total
        if (valorPago !== null) {
            payload.valor_pago = valorPago;
        }

        const response = await fetch(`${API_URL}/${id}/pagar`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (!data.success) {
            alert('Erro ao marcar como pago: ' + data.error);
            return;
        }

        alert('Despesa marcada como paga!');
        fecharModalPagar();
        carregarDespesas();

    } catch (error) {
        console.error('Erro ao marcar despesa como paga:', error);
        alert('Erro ao marcar despesa como paga. Por favor, tente novamente.');
    }
}

/**
 * Fecha modal de pagamento e reseta estado
 */
function fecharModalPagar() {
    document.getElementById('modal-pagar').style.display = 'none';

    // Resetar formulário
    document.getElementById('form-pagar').reset();
    document.querySelector('input[name="tipo-pagamento"][value="total"]').checked = true;
    document.getElementById('campo-valor-custom').style.display = 'none';
}

/**
 * Deleta despesa a partir do modal de edição
 */
function deletarDespesaModal() {
    const id = parseInt(document.getElementById('despesa-id').value);
    const nome = document.getElementById('nome').value;

    // Verificar se é parcela de consórcio ou despesa recorrente
    const despesa = despesas.find(d => d.id === id);
    if (despesa && (despesa.tipo === 'Consorcio' || despesa.recorrente)) {
        // Guardar ID e fechar modal de edição
        window.despesaExcluindo = id;
        window.tipoDespesaExcluindo = despesa.tipo === 'Consorcio' ? 'consorcio' : 'recorrente';
        fecharModal();

        // Atualizar textos do modal
        if (despesa.tipo === 'Consorcio') {
            document.getElementById('modal-exclusao-titulo').textContent = 'Excluir Parcela de Consórcio';
            document.getElementById('modal-exclusao-texto').textContent = 'Esta é uma parcela de consórcio. Como deseja excluir?';
        } else {
            document.getElementById('modal-exclusao-titulo').textContent = 'Excluir Despesa Recorrente';
            document.getElementById('modal-exclusao-texto').textContent = 'Esta é uma despesa recorrente. Como deseja excluir?';
        }

        // Mostrar modal de tipo de exclusão
        document.getElementById('modal-tipo-exclusao').style.display = 'block';
        return;
    }

    // Exclusão normal
    if (confirm(`Tem certeza que deseja deletar a despesa "${nome}"?\n\nEsta ação não pode ser desfeita.`)) {
        deletarDespesa(id);
        fecharModal();
    }
}

/**
 * Confirma e deleta uma despesa
 */
function confirmarDeletar(id, nome) {
    if (confirm(`Tem certeza que deseja deletar a despesa "${nome}"?\n\nEsta ação não pode ser desfeita.`)) {
        deletarDespesa(id);
    }
}

/**
 * Deleta uma despesa
 */
async function deletarDespesa(id) {
    try {
        const response = await fetch(`${API_URL}/${id}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (!data.success) {
            alert('Erro ao deletar: ' + data.error);
            return;
        }

        alert(data.message);
        carregarDespesas();

    } catch (error) {
        console.error('Erro ao deletar despesa:', error);
        alert('Erro ao deletar despesa. Por favor, tente novamente.');
    }
}

/**
 * Formata mês de competência (YYYY-MM para formato legível)
 */
function formatarCompetencia(competencia) {
    if (!competencia) return '';

    const [ano, mes] = competencia.split('-');
    const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    return `${meses[parseInt(mes) - 1]}/${ano}`;
}

/**
 * Formata tipo de recorrência para exibição
 */
function formatarTipoRecorrencia(tipo) {
    // Se não tem tipo, retornar texto padrão
    if (!tipo) {
        return 'Recorrente';
    }

    // Formato antigo (compatibilidade)
    const tiposAntigos = {
        'a_cada_2_semanas': 'A cada 2 semanas',
        'mensal': 'Mensal',
        'semanal': 'Semanal',
        'anual': 'Anual'
    };

    if (tiposAntigos[tipo]) {
        return tiposAntigos[tipo];
    }

    // Novo formato semanal: "semanal_freq_dia" (ex: "semanal_1_1" = toda semana, segunda-feira)
    if (tipo.startsWith('semanal_')) {
        const partes = tipo.split('_');
        if (partes.length === 3) {
            const freq = parseInt(partes[1]);
            const dia = parseInt(partes[2]);

            const diasSemana = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'];
            const diaNome = diasSemana[dia] || 'dia';

            if (freq === 1) {
                return `Toda ${diaNome.toLowerCase()}`;
            } else {
                return `A cada ${freq} semanas (${diaNome.toLowerCase()})`;
            }
        }
    }

    // Se não reconheceu o formato, retornar o próprio tipo ou "Recorrente"
    return tipo || 'Recorrente';
}

/**
 * Mostra mensagem de erro
 */
function mostrarErro(mensagem) {
    const lista = document.getElementById('despesas-lista');
    lista.innerHTML = `<p class="empty-state">${mensagem}</p>`;
}

/**
 * Alterna visibilidade dos campos específicos de consórcio
 */
function alternarCamposConsorcio() {
    const checkbox = document.getElementById('e_consorcio');
    const camposConsorcio = document.getElementById('campos-consorcio');

    if (checkbox.checked) {
        camposConsorcio.style.display = 'block';
    } else {
        camposConsorcio.style.display = 'none';
        // Limpar campos ao desmarcar
        document.getElementById('numero_parcelas_consorcio').value = '';
        document.getElementById('mes_inicio_consorcio').value = '';
        document.getElementById('tipo_reajuste').value = 'nenhum';
        document.getElementById('valor_reajuste').value = '';
        document.getElementById('mes_contemplacao').value = '';
        document.getElementById('valor_premio').value = '';
        document.getElementById('campo-valor-reajuste').style.display = 'none';
    }
}

/**
 * Alterna visibilidade e label do campo de valor de reajuste
 */
function alternarCamposReajuste() {
    const tipoReajuste = document.getElementById('tipo_reajuste').value;
    const campoValor = document.getElementById('campo-valor-reajuste');
    const labelValor = document.getElementById('label-valor-reajuste');
    const inputValor = document.getElementById('valor_reajuste');

    if (tipoReajuste === 'nenhum') {
        campoValor.style.display = 'none';
        inputValor.value = '';
    } else {
        campoValor.style.display = 'block';

        if (tipoReajuste === 'percentual') {
            labelValor.textContent = 'Percentual de Reajuste (%)';
            inputValor.placeholder = 'Ex: 0.5 (para 0,5%)';
            inputValor.step = '0.01';
        } else if (tipoReajuste === 'fixo') {
            labelValor.textContent = 'Valor Fixo de Reajuste (R$)';
            inputValor.placeholder = 'Ex: 10.00';
            inputValor.step = '0.01';
        }
    }
}

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
 * Calcula automaticamente o valor do prêmio do consórcio
 * Prêmio = Número de parcelas (participantes) × Valor da parcela no mês de contemplação
 */
function calcularValorPremio() {
    // Verificar se é um consórcio
    const eConsorcio = document.getElementById('e_consorcio');
    if (!eConsorcio || !eConsorcio.checked) {
        return;
    }

    // Obter valores dos campos
    const valorInicial = parseFloat(document.getElementById('valor').value);
    const numeroParcelas = parseInt(document.getElementById('numero_parcelas_consorcio').value);
    const mesInicioBR = document.getElementById('mes_inicio_consorcio').value;
    const mesContemplacaoBR = document.getElementById('mes_contemplacao').value;
    const tipoReajuste = document.getElementById('tipo_reajuste').value;
    const valorReajuste = parseFloat(document.getElementById('valor_reajuste').value) || 0;

    // Validar campos obrigatórios
    if (!valorInicial || !numeroParcelas || !mesInicioBR || !mesContemplacaoBR) {
        document.getElementById('valor_premio').value = '';
        return;
    }

    // Converter datas brasileiras para ISO
    const mesInicioISO = converterMesAnoBRparaISO(mesInicioBR);
    const mesContemplacaoISO = converterMesAnoBRparaISO(mesContemplacaoBR);

    if (!mesInicioISO || !mesContemplacaoISO) {
        document.getElementById('valor_premio').value = '';
        return;
    }

    // Calcular número de meses entre início e contemplação
    const dataInicio = new Date(mesInicioISO);
    const dataContemplacao = new Date(mesContemplacaoISO);
    const mesesAteContemplacao = Math.round((dataContemplacao - dataInicio) / (1000 * 60 * 60 * 24 * 30));

    if (mesesAteContemplacao < 0 || mesesAteContemplacao >= numeroParcelas) {
        document.getElementById('valor_premio').value = '';
        return;
    }

    // Calcular o valor da parcela no mês de contemplação
    let valorParcelaContemplacao = valorInicial;

    if (tipoReajuste === 'percentual' && valorReajuste > 0) {
        // Reajuste percentual: valor_inicial * (1 + taxa%)^meses
        const fatorReajuste = Math.pow(1 + (valorReajuste / 100), mesesAteContemplacao);
        valorParcelaContemplacao = valorInicial * fatorReajuste;
    } else if (tipoReajuste === 'fixo' && valorReajuste > 0) {
        // Reajuste fixo: valor_inicial + (valor_fixo * meses)
        valorParcelaContemplacao = valorInicial + (valorReajuste * mesesAteContemplacao);
    }

    // Valor do prêmio = Número de participantes × Valor da parcela na contemplação
    // (Número de parcelas = Número de participantes no grupo do consórcio)
    const valorPremio = numeroParcelas * valorParcelaContemplacao;

    // Atualizar campo
    document.getElementById('valor_premio').value = valorPremio.toFixed(2);
}

/**
 * Fecha o modal de tipo de edição de consórcio
 */
function fecharModalTipoEdicao() {
    document.getElementById('modal-tipo-edicao').style.display = 'none';
    window.despesaConsorcioEditando = null;
}

/**
 * Fecha o modal de tipo de exclusão
 */
function fecharModalTipoExclusao() {
    document.getElementById('modal-tipo-exclusao').style.display = 'none';
    window.despesaExcluindo = null;
    window.tipoDespesaExcluindo = null;
}

/**
 * Confirma o tipo de exclusão (consórcio ou recorrente)
 */
async function confirmarTipoExclusao(tipo) {
    const id = window.despesaExcluindo;
    if (!id) return;

    // Fechar modal de tipo de exclusão
    fecharModalTipoExclusao();

    // Fazer exclusão com o tipo especificado
    await deletarDespesaEspecial(id, tipo);
}

/**
 * Deleta despesa especial (consórcio ou recorrente) - única ou futuras
 */
async function deletarDespesaEspecial(id, tipoExclusao) {
    try {
        const url = `${API_URL}/${id}?tipo_exclusao=${tipoExclusao}`;
        const response = await fetch(url, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (!data.success) {
            alert('Erro ao deletar: ' + data.error);
            return;
        }

        const tipoDespesa = window.tipoDespesaExcluindo === 'consorcio' ? 'Parcela' : 'Despesa';
        const mensagem = tipoExclusao === 'futuras'
            ? `${tipoDespesa} e todas as futuras foram excluídas com sucesso!`
            : `${tipoDespesa} excluída com sucesso!`;

        alert(mensagem);
        carregarDespesas();

    } catch (error) {
        console.error('Erro ao deletar:', error);
        alert('Erro ao deletar. Por favor, tente novamente.');
    }
}

/**
 * Confirma o tipo de edição de parcela de consórcio
 */
async function confirmarTipoEdicao(tipo) {
    const id = window.despesaConsorcioEditando;
    if (!id) return;

    // Fechar modal de tipo de edição
    fecharModalTipoEdicao();

    // Agora sim, carregar a despesa para edição
    await editarParcelaConsorcio(id, tipo);
}

/**
 * Edita parcela de consórcio (única ou futuras)
 */
async function editarParcelaConsorcio(id, tipoEdicao) {
    try {
        const response = await fetch(`${API_URL}/${id}`);
        const data = await response.json();

        if (!data.success) {
            alert('Erro ao carregar despesa: ' + data.error);
            return;
        }

        const despesa = data.data;
        despesaEditando = id;

        // Guardar o tipo de edição para uso no salvamento
        window.tipoEdicaoConsorcio = tipoEdicao;

        // Preencher formulário
        document.getElementById('modal-titulo').textContent =
            tipoEdicao === 'unica'
                ? 'Editar Esta Parcela'
                : 'Editar Esta e Parcelas Futuras';

        document.getElementById('despesa-id').value = despesa.id;
        document.getElementById('nome').value = despesa.nome;
        document.getElementById('descricao').value = despesa.descricao || '';
        document.getElementById('valor').value = despesa.valor;
        document.getElementById('categoria_id').value = despesa.categoria_id;
        document.getElementById('data_vencimento').value = despesa.data_vencimento || '';
        document.getElementById('data_pagamento').value = despesa.data_pagamento || '';
        document.getElementById('pago').checked = despesa.pago;
        document.getElementById('recorrente').checked = despesa.recorrente;
        document.getElementById('mes_competencia').value = despesa.mes_competencia || '';

        // Mostrar botão deletar no modal
        document.getElementById('btn-deletar-modal').style.display = 'block';

        // Abrir modal de edição
        document.getElementById('modal-despesa').style.display = 'block';

    } catch (error) {
        console.error('Erro ao carregar despesa:', error);
        alert('Erro ao carregar despesa. Por favor, tente novamente.');
    }
}

// Fechar modal ao clicar fora dele
window.onclick = function(event) {
    const modal = document.getElementById('modal-despesa');
    if (event.target === modal) {
        fecharModal();
    }
}
