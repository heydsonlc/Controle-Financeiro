/**
 * JavaScript para gerenciamento de Despesas
 */

const API_URL = '/api/despesas';
const API_CONTAS_URL = '/api/despesas/contas';  // Endpoint para contas a pagar (execução)
const CATEGORIAS_URL = '/api/categorias';
let despesaEditando = null;
let despesas = [];
let categorias = [];
let contasBancariasAtivas = [];

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
    carregarContasBancariasAtivas();

    // Event listeners para filtros
    document.getElementById('filtro-categoria').addEventListener('change', aplicarFiltros);
    document.getElementById('filtro-status').addEventListener('change', aplicarFiltros);
    document.getElementById('filtro-vencimento-ate').addEventListener('change', aplicarFiltros);
    document.getElementById('filtro-competencia').addEventListener('change', aplicarFiltros);

    // Event listener para calcular competência automaticamente quando data de vencimento mudar
    document.getElementById('data_vencimento').addEventListener('change', calcularCompetenciaAutomaticamente);

    // Event listener para carregar categorias quando cartão for selecionado
    document.getElementById('cartao_id').addEventListener('change', function() {
        const cartaoId = this.value;
        if (cartaoId) {
            carregarCategoriasCartao(cartaoId);
        } else {
            const selectCategoria = document.getElementById('item_agregado_id');
            selectCategoria.innerHTML = '<option value="">Sem categoria</option>';
        }
    });
});

async function carregarContasBancariasAtivas() {
    try {
        const resp = await fetch('/api/contas?status=ATIVO');
        const json = await resp.json();
        if (!json.success) return;
        contasBancariasAtivas = json.data || [];
        atualizarSelectContaBancariaPagamento(contasBancariasAtivas);
    } catch (e) {
        console.error('Erro ao carregar contas bancárias:', e);
    }
}

function atualizarSelectContaBancariaPagamento(contas, selecionado = '') {
    const select = document.getElementById('pagar-conta-bancaria');
    if (!select) return;

    const valorAtual = selecionado || select.value || '';
    select.innerHTML = '<option value=\"\">Selecione...</option>';

    (contas || []).forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `${c.nome} (${c.instituicao})`;
        select.appendChild(opt);
    });

    if (valorAtual) {
        select.value = String(valorAtual);
    }
}

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
 * Carrega lista de cartões de crédito para seleção em despesas recorrentes
 */
async function carregarCartoes() {
    console.log('DEBUG: Iniciando carregamento de cartões...');
    try {
        const response = await fetch('/api/cartoes');
        console.log('DEBUG: Response status:', response.status);

        const data = await response.json();
        console.log('DEBUG: Dados recebidos:', data);

        // Aceitar tanto Array direto quanto objeto {success, data}
        let cartoesList = [];
        if (Array.isArray(data)) {
            // API retorna array diretamente
            cartoesList = data;
        } else if (data.success && data.data) {
            // API retorna {success: true, data: [...]}
            cartoesList = data.data;
        } else {
            console.error('DEBUG: Formato de resposta não reconhecido:', data);
            return;
        }

        const selectCartao = document.getElementById('cartao_id');
        selectCartao.innerHTML = '<option value="">Selecione o cartão...</option>';

        // Filtrar apenas itens do tipo 'Agregador' (cartões)
        const cartoes = cartoesList.filter(item => item.tipo === 'Agregador');
        console.log('DEBUG: Cartões filtrados:', cartoes);

        cartoes.forEach(cartao => {
            if (cartao.ativo) {
                selectCartao.innerHTML += `<option value="${cartao.id}">${cartao.nome}</option>`;
            }
        });

        console.log('DEBUG: Select HTML final:', selectCartao.innerHTML);
    } catch (error) {
        console.error('Erro ao carregar cartões:', error);
    }
}

/**
 * Carrega categorias (ItemAgregado) de um cartão específico
 */
async function carregarCategoriasCartao(cartaoId) {
    try {
        const response = await fetch(`/api/cartoes/${cartaoId}/itens`);
        const data = await response.json();

        // Aceitar tanto Array direto quanto objeto {success, data}
        let categoriasList = [];
        if (Array.isArray(data)) {
            categoriasList = data;
        } else if (data.success && data.data) {
            categoriasList = data.data;
        }

        const selectCategoria = document.getElementById('item_agregado_id');
        selectCategoria.innerHTML = '<option value="">Sem categoria</option>';

        categoriasList.forEach(categoria => {
            if (categoria.ativo) {
                selectCategoria.innerHTML += `<option value="${categoria.id}">${categoria.nome}</option>`;
            }
        });
    } catch (error) {
        console.error('Erro ao carregar categorias do cartão:', error);
    }
}

/**
 * Carrega todas as despesas da API
 */
async function carregarDespesas() {
    try {
        // Pegar mês selecionado no filtro de competência (formato: MM/YYYY)
        const filtroCompetencia = document.getElementById('filtro-competencia').value;
        let url = API_URL;

        if (filtroCompetencia) {
            // Converter MM/YYYY para YYYY-MM
            const [mes, ano] = filtroCompetencia.split('/');
            const mesFormatado = `${ano}-${mes}`;
            url = `${API_URL}?mes_referencia=${mesFormatado}`;
            console.log(`[DEBUG] Carregando despesas para: ${mesFormatado}`);
        }

        const response = await fetch(url);
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
    const vencimentoAteFiltro = document.getElementById('filtro-vencimento-ate').value; // Formato YYYY-MM-DD
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

    // NOVO: Filtrar por competência PRIMEIRO (eixo soberano)
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

    // NOVO: Filtrar por vencimento até (data completa) DENTRO da competência
    // Regra: mostrar apenas despesas onde data_vencimento <= data_selecionada
    if (vencimentoAteFiltro) {
        despesasFiltradas = despesasFiltradas.filter(d => {
            if (!d.data_vencimento) return false;
            // Comparar datas no formato ISO (YYYY-MM-DD)
            return d.data_vencimento <= vencimentoAteFiltro;
        });
    }

    renderizarDespesas(despesasFiltradas);
    atualizarResumo(despesasFiltradas);
}

/**
 * Agrupa despesas recorrentes semanais por (item_despesa_id + competência)
 * REGRA: Agrupamento APENAS VISUAL (runtime) - sem persistência
 * Seção conforme script: apenas despesas com recorrente=true e tipo_recorrencia='semanal'
 */
function agruparDespesasSemanais(despesas) {
    const agrupamentos = {};
    const despesasNaoAgrupadas = [];

    despesas.forEach(despesa => {
        // Critério de agrupamento: recorrente=true E tipo_recorrencia COMEÇA com 'semanal'
        // Aceita: 'semanal', 'semanal_1_2', etc
        const ehSemanal = despesa.tipo_recorrencia && despesa.tipo_recorrencia.startsWith('semanal');

        if (despesa.recorrente === true && ehSemanal) {
            // Extrair nome base (remover " - DD/MM" do final)
            // Ex: "Diarista - 31/12" → "Diarista"
            const nomeBase = despesa.nome.replace(/\s*-\s*\d{2}\/\d{2}$/, '').trim();

            // Chave de agrupamento: nome base + competência
            // Isso agrupa todas as ocorrências semanais do mesmo item no mesmo mês
            const chave = `${nomeBase}_${despesa.mes_competencia}`;

            if (!agrupamentos[chave]) {
                agrupamentos[chave] = {
                    tipo: 'agrupador_semanal',
                    nome: nomeBase,  // Nome sem a data
                    mes_competencia: despesa.mes_competencia,
                    categoria_id: despesa.categoria_id,
                    categoria: despesa.categoria,
                    ocorrencias: [],
                    _agrupado: true  // Flag interna para identificação
                };
            }

            agrupamentos[chave].ocorrencias.push(despesa);
        } else {
            // Não agrupa: mensal, anual, ou não recorrente
            despesasNaoAgrupadas.push(despesa);
        }
    });

    // Converter agrupamentos em array e retornar com não agrupados
    const agrupados = Object.values(agrupamentos);
    return [...agrupados, ...despesasNaoAgrupadas];
}

/**
 * Calcula totais de um agrupamento semanal (runtime)
 * Considera apenas ocorrências não canceladas
 */
function calcularTotaisAgrupamento(ocorrencias) {
    const nao_canceladas = ocorrencias.filter(o => !o.cancelada);

    return {
        total_ocorrencias: nao_canceladas.length,
        pagas: nao_canceladas.filter(o => o.pago).length,
        valor_total: nao_canceladas.reduce((sum, o) => sum + (parseFloat(o.valor) || 0), 0)
    };
}

/**
 * Renderiza um agrupador de despesas semanais
 * Usa o MESMO layout visual de uma despesa comum
 * Formato: <Nome> — <MM/YYYY> — <pagas>/<total> — R$ <valor_total>
 */
function renderizarAgrupadorSemanal(agrupador, index) {
    const totais = calcularTotaisAgrupamento(agrupador.ocorrencias);
    const categoria = agrupador.categoria || (agrupador.categoria_id ? categorias.find(c => c.id === agrupador.categoria_id) : null);
    const categoriaNome = categoria ? categoria.nome : 'Sem categoria';
    const competencia = agrupador.mes_competencia ? formatarCompetencia(agrupador.mes_competencia) : '';

    // Status: se TODAS pagas = Pago, senão Pendente
    const todasPagas = totais.pagas === totais.total_ocorrencias && totais.total_ocorrencias > 0;
    const statusClass = todasPagas ? 'pago' : 'pendente';
    const statusTexto = todasPagas ? 'Pago' : 'Pendente';

    // Descrição agregada: Nome — MM/YYYY — pagas/total — R$ valor
    const descricaoAgrupada = `${agrupador.nome} — ${competencia} — ${totais.pagas}/${totais.total_ocorrencias}`;

    return `
        <div class="despesa-card despesa-card-padrao ${statusClass} tipo-recorrente agrupador-semanal" data-agrupador-index="${index}">
            <div class="despesa-linha-principal">
                <div class="despesa-status">
                    <span class="status-badge status-badge-${statusClass}">${statusTexto}</span>
                </div>

                <div class="despesa-descricao">
                    ${descricaoAgrupada}
                </div>

                <div class="despesa-meta">
                    <span class="meta-tipo tipo-recorrente">Recorrente</span>
                    ${categoria ? `<span class="meta-categoria">${categoriaNome}</span>` : ''}
                </div>

                <div class="despesa-valor-principal">
                    R$ ${totais.valor_total.toFixed(2).replace('.', ',')}
                </div>

                <div class="despesa-actions">
                    <button class="btn-icon btn-pagar" onclick="pagarTodasOcorrencias(${index})" title="${todasPagas ? 'Todas ocorrências já pagas' : 'Pagar todas as ocorrências pendentes'}" ${todasPagas ? 'disabled style="opacity: 0.3; cursor: not-allowed;"' : ''}>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    </button>
                    <button class="btn-icon btn-expandir" onclick="toggleAgrupadorSemanal(${index})" title="Expandir ocorrências">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                    </button>
                </div>
            </div>

            <div class="agrupador-detalhes" id="agrupador-detalhes-${index}" style="display: none;">
                ${agrupador.ocorrencias.map(ocorrencia => renderizarOcorrenciaIndividual(ocorrencia)).join('')}
            </div>
        </div>
    `;
}

/**
 * Renderiza uma ocorrência individual dentro de um agrupamento
 * Mantém botões funcionais (Pagar e Editar apenas)
 */
function renderizarOcorrenciaIndividual(despesa) {
    const pagoFlag = despesa.status ? despesa.status.toLowerCase() === 'pago' : despesa.pago;
    const statusClass = pagoFlag ? 'pago' : 'pendente';
    const statusTexto = pagoFlag ? 'Pago' : 'Pendente';
    const cancelada = despesa.cancelada || false;

    return `
        <div class="ocorrencia-item ${cancelada ? 'cancelada' : ''}" style="padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span class="status-badge status-badge-${statusClass}" style="font-size: 0.8em;">${cancelada ? 'Cancelado' : statusTexto}</span>
                    <span style="color: rgba(255, 255, 255, 0.9);">
                        ${despesa.data_vencimento ? new Date(despesa.data_vencimento + 'T00:00:00').toLocaleDateString('pt-BR') : 'Sem data'}
                    </span>
                    ${despesa.descricao ? `<span style="color: rgba(255, 255, 255, 0.6); font-size: 0.9em;">${despesa.descricao}</span>` : ''}
                </div>
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="font-weight: 600; color: white;">R$ ${parseFloat(despesa.valor).toFixed(2).replace('.', ',')}</span>
                    <button class="btn-icon btn-pagar" onclick="marcarComoPago(${despesa.id})" title="${pagoFlag ? 'Já pago' : 'Marcar como pago'}" ${pagoFlag ? 'disabled style="opacity: 0.3; cursor: not-allowed;"' : ''}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    </button>
                    <button class="btn-icon" onclick="editarDespesa(${despesa.id})" title="Editar">✏️</button>
                </div>
            </div>
        </div>
    `;
}

/**
 * Toggle de expansão do agrupador semanal
 */
function toggleAgrupadorSemanal(index) {
    const detalhes = document.getElementById(`agrupador-detalhes-${index}`);
    if (detalhes) {
        detalhes.style.display = detalhes.style.display === 'none' ? 'block' : 'none';
    }
}

/**
 * Paga todas as ocorrências pendentes de um agrupamento semanal
 */
async function pagarTodasOcorrencias(index) {
    // Obter o agrupamento da lista processada
    const despesasProcessadas = agruparDespesasSemanais(despesas);
    const agrupador = despesasProcessadas[index];

    if (!agrupador || agrupador.tipo !== 'agrupador_semanal') {
        alert('Erro: Agrupamento não encontrado');
        return;
    }

    // Filtrar apenas ocorrências pendentes (não pagas e não canceladas)
    const ocorrenciasPendentes = agrupador.ocorrencias.filter(o => !o.pago && !o.cancelada);

    if (ocorrenciasPendentes.length === 0) {
        alert('Todas as ocorrências já foram pagas!');
        return;
    }

    // Confirmar ação
    const nomeAgrupador = agrupador.nome;
    const totalPendente = ocorrenciasPendentes.reduce((sum, o) => sum + parseFloat(o.valor), 0);
    const competencia = agrupador.mes_competencia ? formatarCompetencia(agrupador.mes_competencia) : '';

    const confirmar = confirm(
        `Pagar ${ocorrenciasPendentes.length} ocorrência(s) de "${nomeAgrupador}" (${competencia})?\n\n` +
        `Valor total: R$ ${totalPendente.toFixed(2).replace('.', ',')}`
    );

    if (!confirmar) return;

    // Pagar cada ocorrência pendente
    const dataHoje = new Date().toISOString().split('T')[0];
    let sucessos = 0;
    let erros = 0;

    for (const ocorrencia of ocorrenciasPendentes) {
        try {
            // ItemDespesa usa endpoint PUT /<id> com campo pago=true
            const response = await fetch(`${API_URL}/${ocorrencia.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    pago: true,
                    data_pagamento: dataHoje,
                    valor_pago: ocorrencia.valor
                })
            });

            const data = await response.json();
            if (data.success) {
                sucessos++;
            } else {
                erros++;
                console.error(`Erro ao pagar ocorrência ${ocorrencia.id}:`, data.error);
            }
        } catch (error) {
            erros++;
            console.error(`Erro ao pagar ocorrência ${ocorrencia.id}:`, error);
        }
    }

    // Mostrar resultado
    if (erros === 0) {
        alert(`✓ ${sucessos} ocorrência(s) paga(s) com sucesso!`);
    } else {
        alert(`Pagamento concluído com avisos:\n✓ ${sucessos} paga(s)\n✗ ${erros} com erro`);
    }

    // Recarregar lista
    await carregarDespesas();
}

/**
 * Renderiza a lista de despesas
 */
/**
 * Renderiza a lista de despesas seguindo o padrão FATURA MENSAL CONSOLIDADA
 * Conforme contrato seção 2: Despesas como Fatura Mensal Consolidada
 *
 * Estrutura padronizada: [Status] Descrição | Competência | Tipo | Valor
 * Regra definitiva do cartão: Previsto OU Executado (NUNCA ambos)
 *
 * NOVO: Agrupa visualmente despesas recorrentes semanais
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

    // Agrupar despesas semanais ANTES de renderizar (apenas organização visual)
    // IMPORTANTE: manter o índice original do agrupador semanal, pois pagarTodasOcorrencias(index)
    // recalcula com agruparDespesasSemanais(despesas) e usa o mesmo índice.
    const despesasProcessadas = agruparDespesasSemanais(despesasParaRenderizar);

    const ORDEM_GRUPOS = [
        'FINANCIAMENTOS',
        'FATURAS_CARTAO',
        'DESPESAS_RECORRENTES',
        'DESPESAS_AVULSAS',
        'INVESTIMENTOS',
    ];

    const rotulosGrupo = {
        FINANCIAMENTOS: 'FINANCIAMENTOS',
        FATURAS_CARTAO: 'FATURAS DE CARTÃO DE CRÉDITO',
        DESPESAS_RECORRENTES: 'DESPESAS RECORRENTES',
        DESPESAS_AVULSAS: 'DESPESAS AVULSAS',
        INVESTIMENTOS: 'INVESTIMENTOS',
    };

    function grupoLeitura(d) {
        if (d?.tipo === 'agrupador_semanal') return 'DESPESAS_RECORRENTES';
        if (d && d.financiamento_parcela_id != null) return 'FINANCIAMENTOS';
        if (d && d.is_fatura_cartao === true) return 'FATURAS_CARTAO';
        if (d && d.recorrente === true && String(d.tipo || '').trim().toLowerCase() === 'simples') return 'DESPESAS_RECORRENTES';
        if (String(d?.tipo || '').trim().toLowerCase() === 'consorcio') return 'INVESTIMENTOS';
        return 'DESPESAS_AVULSAS';
    }

    function renderizarCardDespesa(despesa) {

        // Renderização normal para despesas não agrupadas
        // Determinar tipo de despesa para identificação visual
        const isFaturaCartao = despesa.is_fatura_cartao === true || despesa.tipo === 'cartao';
        const isAgrupado = despesa.agrupado === true || isFaturaCartao;
        const isRecorrente = despesa.recorrente === true;
        const isParcela = despesa.total_parcelas > 1;
        const valorDespesa = obterValorDespesa(despesa);

        // Status: Pago ou Pendente (backend já decide)
        const pagoFlag = despesa.status ? despesa.status.toLowerCase() === 'pago' : despesa.pago;
        const statusClass = pagoFlag ? 'pago' : 'pendente';
        const statusTexto = pagoFlag ? 'Pago' : 'Pendente';

        // Determinar TIPO conforme regras do contrato
        let tipoTexto = '';
        let tipoClass = '';

        if (isFaturaCartao || despesa.tipo === 'cartao') {
            tipoTexto = 'Cartão';
            tipoClass = 'tipo-cartao';
        } else if (isParcela) {
            tipoTexto = 'Parcela';
            tipoClass = 'tipo-parcela';
        } else if (isRecorrente) {
            tipoTexto = 'Recorrente';
            tipoClass = 'tipo-recorrente';
        } else {
            tipoTexto = 'Direto';
            tipoClass = 'tipo-direto';
        }

        // Categoria (opcional, metadado)
        const categoria = despesa.categoria || (despesa.categoria_id ? categorias.find(c => c.id === despesa.categoria_id) : null);
        const categoriaNome = categoria ? categoria.nome : 'Sem categoria';

        // Competência formatada
        const competencia = despesa.mes_competencia ? formatarCompetencia(despesa.mes_competencia) : '';

        // Ações disponíveis
        const acoesHTML = isFaturaCartao ? `
            <div class="despesa-actions">
                <button class="btn-icon btn-detalhes" onclick="toggleDetalhesFatura(${despesa.id}, '${despesa.cartao_id || ''}', '${despesa.mes_competencia || ''}')" title="Ver detalhes da fatura">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="6 9 12 15 18 9"></polyline>
                    </svg>
                </button>
                ${despesa.status_fatura === 'ABERTA' ? `
                    <button class="btn-icon btn-consolidar" onclick="consolidarFatura(${despesa.cartao_id || despesa.id}, '${despesa.competencia || despesa.mes_competencia || ''}')" title="Consolidar fatura" style="color: #ff9500;">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M9 11l3 3L22 4"></path>
                            <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"></path>
                        </svg>
                    </button>
                ` : ''}
                <button class="btn-icon btn-pagar" onclick="marcarComoPago(${despesa.id})" title="${despesa.pago ? 'Fatura já paga' : 'Pagar fatura'}" ${despesa.pago ? 'disabled style="opacity: 0.3; cursor: not-allowed;"' : ''}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                </button>
            </div>
        ` : (isAgrupado ? '' : `
            <div class="despesa-actions">
                <button class="btn-icon" onclick="editarDespesa(${despesa.id})" title="Editar">
                    ✏️
                </button>
                <button class="btn-icon btn-pagar" onclick="marcarComoPago(${despesa.id})" title="${despesa.pago ? 'Já pago' : 'Marcar como pago'}" ${despesa.pago ? 'disabled style="opacity: 0.3; cursor: not-allowed;"' : ''}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                </button>
            </div>
        `);

        // Layout padronizado para TODAS as despesas
        // Estrutura: [Status] Descrição | Competência | Tipo | Valor
        return `
            <div class="despesa-card despesa-card-padrao ${statusClass} ${tipoClass}" data-despesa-id="${despesa.id}">
                <div class="despesa-linha-principal">
                    <div class="despesa-status">
                        <span class="status-badge status-badge-${statusClass}">${statusTexto}</span>
                    </div>

                    <div class="despesa-descricao">
                        ${despesa.nome}
                    </div>

                    <div class="despesa-meta">
                        ${competencia ? `<span class="meta-competencia">${competencia}</span>` : ''}
                        <span class="meta-tipo ${tipoClass}">${tipoTexto}</span>
                        ${isFaturaCartao && despesa.status_fatura ? `<span class="meta-status-fatura" style="background: ${despesa.status_fatura === 'FECHADA' ? '#ff9500' : despesa.status_fatura === 'PAGA' ? '#34c759' : '#007aff'}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 600;">${despesa.status_fatura}</span>` : ''}
                        ${categoria ? `<span class="meta-categoria">${categoriaNome}</span>` : ''}
                    </div>

                    <div class="despesa-valor-principal">
                        R$ ${valorDespesa.toFixed(2).replace('.', ',')}
                    </div>

                    ${acoesHTML}
                </div>

                ${isFaturaCartao ? `
                    <div class="fatura-detalhes" id="fatura-detalhes-${despesa.id}" style="display: none;">
                        <div class="loading-detalhes">Carregando detalhes...</div>
                    </div>
                ` : ''}

                ${despesa.descricao && !isFaturaCartao && despesa.financiamento_parcela_id == null ? `
                    <div class="despesa-linha-detalhes">
                        <span class="despesa-obs">${despesa.descricao}</span>
                    </div>
                ` : ''}
            </div>
        `;
    }

    const grupos = {
        FINANCIAMENTOS: [],
        FATURAS_CARTAO: [],
        DESPESAS_RECORRENTES: [],
        DESPESAS_AVULSAS: [],
        INVESTIMENTOS: [],
    };

    despesasProcessadas.forEach((despesa, indexOriginal) => {
        const g = grupoLeitura(despesa);
        grupos[g].push({ despesa, indexOriginal });
    });

    const partesHTML = [];
    ORDEM_GRUPOS.forEach(g => {
        const itens = grupos[g] || [];
        if (!itens.length) return;

        partesHTML.push(`<div class="despesas-grupo-titulo">${rotulosGrupo[g] || g}</div>`);
        itens.forEach(({ despesa, indexOriginal }) => {
            if (despesa.tipo === 'agrupador_semanal') {
                partesHTML.push(renderizarAgrupadorSemanal(despesa, indexOriginal));
                return;
            }
            partesHTML.push(renderizarCardDespesa(despesa));
        });
    });

    lista.innerHTML = partesHTML.join('');
}

/**
 * Atualiza os cards de resumo
 */
function atualizarResumo(despesasParaResumir) {
    const total = despesasParaResumir.reduce((sum, d) => sum + obterValorDespesa(d), 0);
    const totalPendentes = despesasParaResumir
        .filter(d => {
            const pagoFlag = d.status ? d.status.toLowerCase() === 'pago' : d.pago;
            return !pagoFlag;
        })
        .reduce((sum, d) => sum + obterValorDespesa(d), 0);
    const totalPagas = despesasParaResumir
        .filter(d => {
            const pagoFlag = d.status ? d.status.toLowerCase() === 'pago' : d.pago;
            return pagoFlag;
        })
        .reduce((sum, d) => sum + obterValorDespesa(d), 0);

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
    document.getElementById('meio-pagamento-group').style.display = 'none';
    document.getElementById('campos-cartao').style.display = 'none';
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

        // Mostrar campo de meio de pagamento se recorrente
        document.getElementById('meio-pagamento-group').style.display = despesa.recorrente ? 'block' : 'none';

        // Preencher meio de pagamento e campos de cartão se existirem
        if (despesa.recorrente && despesa.meio_pagamento) {
            document.getElementById('meio_pagamento').value = despesa.meio_pagamento;

            if (despesa.meio_pagamento === 'cartao') {
                // Mostrar campos de cartão
                document.getElementById('campos-cartao').style.display = 'block';

                // Carregar cartões primeiro
                await carregarCartoes();

                // Selecionar o cartão se existir
                if (despesa.cartao_id) {
                    document.getElementById('cartao_id').value = despesa.cartao_id;

                    // Carregar categorias do cartão
                    await carregarCategoriasCartao(despesa.cartao_id);

                    // Selecionar a categoria se existir
                    if (despesa.item_agregado_id) {
                        document.getElementById('item_agregado_id').value = despesa.item_agregado_id;
                    }
                }
            } else {
                document.getElementById('campos-cartao').style.display = 'none';
            }
        } else {
            document.getElementById('meio_pagamento').value = '';
            document.getElementById('campos-cartao').style.display = 'none';
        }

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

    // Adicionar campos de recorrência paga via cartão (se preenchidos)
    if (recorrente) {
        const meioPagamento = document.getElementById('meio_pagamento').value;
        if (meioPagamento) {
            dados.meio_pagamento = meioPagamento;
        }

        if (meioPagamento === 'cartao') {
            const cartaoId = document.getElementById('cartao_id').value;
            const itemAgregadoId = document.getElementById('item_agregado_id').value;

            const cartaoIdNumber = Number(cartaoId);
            if (!Number.isInteger(cartaoIdNumber) || cartaoIdNumber <= 0) {
                alert('Selecione um cartão válido.');
                return;
            }
            dados.cartao_id = cartaoIdNumber;

            if (itemAgregadoId) {
                const itemAgregadoIdNumber = Number(itemAgregadoId);
                if (Number.isInteger(itemAgregadoIdNumber) && itemAgregadoIdNumber > 0) {
                    dados.item_agregado_id = itemAgregadoIdNumber;
                }
            }
        }
    }

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
    const categoriaId = parseInt(document.getElementById('categoria_id')?.value) || null;
    if (!categoriaId) {
        alert('Selecione uma categoria para o consórcio.');
        return;
    }

    const dados = {
        nome: document.getElementById('nome').value.trim(),
        valor_inicial: parseFloat(document.getElementById('valor').value),
        numero_parcelas: parseInt(numeroParcelas),
        mes_inicio: mesInicioISO,
        tipo_reajuste: document.getElementById('tipo_reajuste').value,
        valor_reajuste: parseFloat(document.getElementById('valor_reajuste').value) || 0,
        mes_contemplacao: null,
        valor_premio: null,
        categoria_id: categoriaId,
        item_despesa_id: null, // legacy: não usar para categoria
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
        const url = id ? `/api/consorcios/${id}` : '/api/consorcios/';
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
    const contaBancariaId = despesa.conta_bancaria_id || '';

    // Guardar no modal se é fatura de cartão
    document.getElementById('pagar-despesa-id').value = id;
    document.getElementById('pagar-despesa-id').dataset.isFaturaCartao = isFaturaCartao;

    // Preencher dados básicos
    document.getElementById('pagar-nome-despesa').textContent = despesa.nome;
    document.getElementById('pagar-data').value = new Date().toISOString().split('T')[0];

    const groupConta = document.getElementById('pagar-conta-bancaria-group');
    const selectConta = document.getElementById('pagar-conta-bancaria');
    if (selectConta) {
        if (!contasBancariasAtivas || contasBancariasAtivas.length === 0) {
            carregarContasBancariasAtivas();
        }
        atualizarSelectContaBancariaPagamento(contasBancariasAtivas, contaBancariaId);

        const temContaDefinida = Boolean(contaBancariaId);
        selectConta.disabled = temContaDefinida;
        selectConta.required = !temContaDefinida;
        if (groupConta) groupConta.style.display = temContaDefinida ? 'none' : 'block';
    }

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
        const valorPrevistoInput = document.getElementById('pagar-valor-previsto');
        const valorPrevistoDisplay = document.getElementById('pagar-valor-previsto-display');
        const valorPagoInput = document.getElementById('pagar-valor-pago');

        if (valorPrevistoInput) valorPrevistoInput.value = valorExecutado;
        if (valorPrevistoDisplay) valorPrevistoDisplay.textContent = `R$ ${valorExecutado.toFixed(2).replace('.', ',')}`;
        if (valorPagoInput) valorPagoInput.value = valorExecutado;

        // Trocar texto para "Valor Executado"
        const labelTotal = document.querySelector('input[name="tipo-pagamento"][value="total"]');
        if (labelTotal) {
            const spanElement = labelTotal.closest('label')?.querySelector('span');
            if (spanElement) {
                spanElement.innerHTML = `Valor Executado (Gasto Real): <strong>R$ ${valorExecutado.toFixed(2).replace('.', ',')}</strong>`;
            }
        }
    } else {
        // Remover aviso se existir
        const avisoExistente = document.querySelector('.aviso-fatura-cartao');
        if (avisoExistente) {
            avisoExistente.remove();
        }

        // Despesa normal
        const valorFormatado = `R$ ${parseFloat(despesa.valor).toFixed(2).replace('.', ',')}`;
        const valorPrevistoInput = document.getElementById('pagar-valor-previsto');
        const valorPrevistoDisplay = document.getElementById('pagar-valor-previsto-display');
        const valorPagoInput = document.getElementById('pagar-valor-pago');

        if (valorPrevistoInput) valorPrevistoInput.value = despesa.valor;
        if (valorPrevistoDisplay) valorPrevistoDisplay.textContent = valorFormatado;
        if (valorPagoInput) valorPagoInput.value = despesa.valor;

        // Texto padrão
        const labelTotal = document.querySelector('input[name="tipo-pagamento"][value="total"]');
        if (labelTotal) {
            const spanElement = labelTotal.closest('label')?.querySelector('span');
            if (spanElement) {
                spanElement.innerHTML = `Valor Total: <strong>${valorFormatado}</strong>`;
            }
        }
    }

    // Resetar para o estado inicial
    const radioTotal = document.querySelector('input[name="tipo-pagamento"][value="total"]');
    if (radioTotal) radioTotal.checked = true;

    const campoCustom = document.getElementById('campo-valor-custom');
    if (campoCustom) campoCustom.style.display = 'none';

    // Abrir modal
    const modal = document.getElementById('modal-pagar');
    if (modal) modal.style.display = 'block';
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
    const contaBancariaId = document.getElementById('pagar-conta-bancaria')?.value;

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

        if (!contaBancariaId) {
            alert('Selecione a conta bancária para executar o pagamento.');
            return;
        }
        payload.conta_bancaria_id = parseInt(contaBancariaId, 10);

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

    const groupConta = document.getElementById('pagar-conta-bancaria-group');
    const selectConta = document.getElementById('pagar-conta-bancaria');
    if (groupConta) groupConta.style.display = 'block';
    if (selectConta) {
        selectConta.disabled = false;
        selectConta.required = true;
        selectConta.value = '';
    }
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
 * Retorna o valor soberano da despesa.
 * Para cartão, usa valor_fatura vindo do backend; demais usam valor.
 */
function obterValorDespesa(despesa) {
    if (!despesa) return 0;
    if (despesa.tipo === 'cartao' || despesa.is_fatura_cartao === true) {
        return parseFloat(despesa.valor_fatura || 0);
    }
    return parseFloat(despesa.valor || 0);
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

/**
 * Expande/contrai os detalhes da fatura do cartão
 * Conforme script de fechamento da fatura
 */
async function toggleDetalhesFatura(despesaId, cartaoId, competencia) {
    const container = document.getElementById(`fatura-detalhes-${despesaId}`);
    const botao = event.target.closest('.btn-detalhes');

    if (!container) return;

    // Toggle visibilidade
    if (container.style.display === 'none' || container.style.display === '') {
        // Expandir
        container.style.display = 'block';

        // Rotacionar ícone do botão
        if (botao) {
            const svg = botao.querySelector('svg');
            if (svg) svg.style.transform = 'rotate(180deg)';
        }

        // Verificar se já carregou os dados
        if (!container.dataset.loaded) {
            await carregarDetalhesFatura(despesaId, cartaoId, competencia);
            container.dataset.loaded = 'true';
        }
    } else {
        // Recolher
        container.style.display = 'none';

        // Rotacionar ícone de volta
        if (botao) {
            const svg = botao.querySelector('svg');
            if (svg) svg.style.transform = 'rotate(0deg)';
        }
    }
}

/**
 * Carrega e renderiza os detalhes completos da fatura do cartão
 * Estrutura em 4 blocos conforme script:
 * 1. Compras Parceladas
 * 2. Despesas Fixas
 * 3. Despesas por Categoria (com previsão)
 * 4. Outros Lançamentos
 */
async function carregarDetalhesFatura(despesaId, cartaoId, competencia) {
    const container = document.getElementById(`fatura-detalhes-${despesaId}`);
    if (!container) return;

    const competenciaNormalizada = normalizarCompetencia(competencia);
    container.innerHTML = '<div class="loading-detalhes">Carregando detalhes...</div>';

    try {
        // Buscar lançamentos do cartão na competência
        const response = await fetch(`/api/cartoes/${cartaoId}/lancamentos?mes_fatura=${competenciaNormalizada}`);
        const json = await response.json();
        const lancamentos = extrairArray(json);

        // Buscar resumo do cartão para obter previsões das categorias
        const resumoResponse = await fetch(`/api/cartoes/${cartaoId}/resumo?mes_referencia=${competenciaNormalizada}`);
        const resumoJson = await resumoResponse.json();
        if (!resumoResponse.ok) {
            throw new Error(resumoJson?.erro || 'Erro ao carregar resumo do cartão');
        }

        // Organizar lançamentos nos 4 blocos
        const blocos = organizarLancamentosEmBlocos(lancamentos, resumoJson);

        // Calcular totais
        const totais = calcularTotaisFatura(blocos, lancamentos);

        // Renderizar visualização completa
        container.innerHTML = renderizarFaturaCompleta(blocos, totais, competenciaNormalizada);

    } catch (error) {
        console.error('Erro ao carregar detalhes da fatura:', error);
        container.innerHTML = `
            <div class="erro-detalhes">
                <p>Erro ao carregar detalhes da fatura.</p>
                <button onclick="toggleDetalhesFatura(${despesaId}, '${cartaoId}', '${competencia}')" class="btn btn-secondary">
                    Fechar
                </button>
            </div>
        `;
    }
}

/**
 * Organiza lançamentos nos 4 blocos conforme regras do script
 */
function organizarLancamentosEmBlocos(lancamentos, resumoCartao) {
    const blocos = {
        parceladas: [],      // Parte 1: total_parcelas > 1
        fixas: [],           // Parte 2: recorrentes mensais (quando vierem marcadas)
        porCategoria: {},    // Parte 3: com categoria que tem previs?es
        outros: []           // Parte 4: resto
    };

    // Mapear categorias com previsão (valor_orcado no resumo)
    (resumoCartao?.itens || []).forEach(item => {
        const previsto = parseFloat(item.valor_orcado || 0);
        if (previsto > 0) {
            blocos.porCategoria[item.id] = {
                id: item.id,
                nome: item.nome,
                previsto,
                lancamentos: []
            };
        }
    });

    lancamentos.forEach(lanc => {
        const valorLanc = parseFloat(lanc.valor || 0);
        const totalParcelas = parseInt(lanc.total_parcelas || 0);
        const numeroParcela = parseInt(lanc.numero_parcela || 0);
        const categoriaPrevista = blocos.porCategoria[lanc.item_agregado_id];
        const isRecorrenteCartao = lanc.is_recorrente === true;  // Lançamento gerado por despesa recorrente

        // PARTE 1: Compras Parceladas
        if (totalParcelas > 1) {
            blocos.parceladas.push({
                descricao: lanc.descricao,
                valor: valorLanc,
                numero_parcela: numeroParcela,
                total_parcelas: totalParcelas
            });
        }
        // PARTE 2: Despesas Fixas (recorrentes no cartão)
        else if (isRecorrenteCartao && totalParcelas <= 1) {
            blocos.fixas.push({
                descricao: lanc.descricao,
                valor: valorLanc
            });
        }
        // PARTE 3: Despesas por Categoria (com previsão)
        else if (categoriaPrevista) {
            categoriaPrevista.lancamentos.push({
                descricao: lanc.descricao,
                valor: valorLanc,
                data_compra: lanc.data_compra,
                observacoes: lanc.observacoes
            });
        }
        // PARTE 4: Outros Lançamentos
        else {
            blocos.outros.push({
                descricao: lanc.descricao,
                valor: valorLanc,
                data_compra: lanc.data_compra
            });
        }
    });

    return blocos;
}

/**
 * Calcula totais da fatura
 *
 * REGRA IMUTÁVEL: A fatura mostra SEMPRE valores PREVISTOS
 * - totalFatura = soma dos PREVISTOS de todos os blocos
 * - totalExecutado = soma dos EXECUTADOS (apenas para referência interna)
 */
function calcularTotaisFatura(blocos, lancamentos) {
    // === PREVISTO: Soma dos orçamentos/tetos de cada bloco ===

    // Bloco 1: Compras Parceladas (valor executado = previsto)
    const previstoParceladas = blocos.parceladas.reduce((sum, p) => sum + parseFloat(p.valor || 0), 0);

    // Bloco 2: Despesas Fixas (valor executado = previsto)
    const previstoFixas = blocos.fixas.reduce((sum, f) => sum + parseFloat(f.valor || 0), 0);

    // Bloco 3: Despesas por Categoria (usa valor_previsto do orçamento)
    const previstoCategorias = Object.values(blocos.porCategoria).reduce((sum, cat) => {
        return sum + parseFloat(cat.previsto || 0);
    }, 0);

    // Bloco 4: Outros Lançamentos (valor executado = previsto)
    const previstoOutros = blocos.outros.reduce((sum, o) => sum + parseFloat(o.valor || 0), 0);

    // TOTAL DA FATURA = SOMA DOS PREVISTOS
    const totalFatura = previstoParceladas + previstoFixas + previstoCategorias + previstoOutros;

    // === EXECUTADO: Soma real dos lançamentos (para referência) ===
    const totalExecutado = lancamentos.reduce((sum, l) => sum + parseFloat(l.valor || 0), 0);

    return {
        totalFatura,      // ← PREVISTO (usado no cabeçalho da fatura)
        totalExecutado    // ← EXECUTADO (referência interna, não exibido)
    };
}

/**
 * Renderiza a visualização completa da fatura
 *
 * CABEÇALHO: Exibe SEMPRE valores PREVISTOS
 * - Total da Fatura = soma dos PREVISTOS (quanto vou pagar)
 * - Total Executado = soma dos EXECUTADOS (quanto já gastei, para transparência)
 */
function renderizarFaturaCompleta(blocos, totais, competencia) {
    const competenciaFormatada = formatarCompetenciaCompleta(competencia);

    return `
        <div class="fatura-container">
            <div class="fatura-header">
                <h3>Fatura do Cartão - ${competenciaFormatada}</h3>
                <div class="fatura-totais">
                    <div class="total-item destaque">
                        <span class="total-label">Total da Fatura (Previsto):</span>
                        <span class="total-valor">R$ ${totais.totalFatura.toFixed(2).replace('.', ',')}</span>
                    </div>
                    <div class="total-item">
                        <span class="total-label">Total Executado:</span>
                        <span class="total-valor">R$ ${totais.totalExecutado.toFixed(2).replace('.', ',')}</span>
                    </div>
                </div>
            </div>

            <div class="fatura-blocos">
                ${renderizarBlocoParceladas(blocos.parceladas)}
                ${renderizarBlocoFixas(blocos.fixas)}
                ${renderizarBlocoPorCategoria(blocos.porCategoria)}
                ${renderizarBlocoOutros(blocos.outros)}
            </div>

            ${renderizarRodapeFatura(blocos)}
        </div>
    `;
}

function renderizarBlocoParceladas(parceladas) {
    const total = parceladas.reduce((sum, p) => sum + (p.valor || 0), 0);
    const linhas = parceladas.length > 0
        ? parceladas.map(p => `
            <div class="linha-simples">
                <div>
                    <div class="linha-titulo">${p.descricao}</div>
                    <div class="linha-legenda">${formatarParcelaAtual(p.numero_parcela, p.total_parcelas)}</div>
                </div>
                <div class="linha-valor">R$ ${formatarValorBR(p.valor)}</div>
            </div>
        `).join('')
        : '<div class="linha-vazia">Nenhuma compra parcelada neste mês.</div>';

    return `
        <div class="fatura-bloco">
            <div class="bloco-header">
                <span class="bloco-titulo">Compras Parceladas</span>
                <span class="bloco-subtotal">R$ ${formatarValorBR(total)}</span>
            </div>
            <div class="bloco-lista">${linhas}</div>
        </div>
    `;
}

function renderizarBlocoFixas(fixas) {
    const total = fixas.reduce((sum, f) => sum + (f.valor || 0), 0);
    const linhas = fixas.length > 0
        ? fixas.map(f => `
            <div class="linha-simples">
                <div class="linha-titulo">${f.descricao}</div>
                <div class="linha-valor">R$ ${formatarValorBR(f.valor)}</div>
            </div>
        `).join('')
        : '<div class="linha-vazia">Nenhuma despesa fixa no cartão neste mês.</div>';

    return `
        <div class="fatura-bloco">
            <div class="bloco-header">
                <span class="bloco-titulo">Despesas Fixas</span>
                <span class="bloco-subtotal">R$ ${formatarValorBR(total)}</span>
            </div>
            <div class="bloco-lista">${linhas}</div>
        </div>
    `;
}

/**
 * Renderiza bloco "Despesas por Categoria"
 *
 * LINHA PRINCIPAL: Mostra PREVISTO (orçamento da categoria)
 * DETALHAMENTO INTERNO: Mostra EXECUTADO (lançamentos reais)
 */
function renderizarBlocoPorCategoria(porCategoria) {
    const categorias = Object.values(porCategoria || {});
    const conteudo = categorias.length > 0
        ? categorias.map(cat => {
            const previsto = parseFloat(cat.previsto || 0);
            const executado = cat.lancamentos.reduce((sum, l) => sum + (l.valor || 0), 0);
            const indicador = executado < previsto ? '↑' : executado > previsto ? '↓' : '=';
            const corIndicador = executado < previsto ? '#10b981' : executado > previsto ? '#ef4444' : '#6e6e73';

            // ← DETALHAMENTO: Valores EXECUTADOS (lançamentos reais)
            const detalhes = cat.lancamentos.length > 0
                ? cat.lancamentos.map(l => `
                    <div class="linha-simples">
                        <div>
                            <div class="linha-titulo">${l.descricao}</div>
                            ${l.data_compra ? `<div class="linha-legenda">${formatarDataCurta(l.data_compra)} • executado</div>` : `<div class="linha-legenda">executado</div>`}
                            ${l.observacoes ? `<div class="linha-legenda">${l.observacoes}</div>` : ''}
                        </div>
                        <div class="linha-valor">R$ ${formatarValorBR(l.valor)}</div>
                    </div>
                `).join('')
                : '<div class="linha-vazia">Nenhum lançamento executado.</div>';

            return `
                <div class="categoria-bloco">
                    <button type="button" class="categoria-linha" onclick="toggleCategoriaDetalhe('${cat.id}')">
                        <div class="categoria-info">
                            <span class="categoria-valor">
                                R$ ${formatarValorBR(previsto)}
                                <span style="margin-left: 6px; font-weight: 700; color: ${corIndicador};" title="Comparação: executado vs previsto">${indicador}</span>
                            </span>
                            <span class="categoria-nome">${cat.nome}</span>
                        </div>
                        <div class="categoria-indicador" style="color: #6e6e73; font-size: 13px;" title="Total executado desta categoria">
                            R$ ${formatarValorBR(executado)}
                        </div>
                    </button>
                    <div class="categoria-detalhes" id="categoria-detalhe-${cat.id}" style="display: none;">
                        ${detalhes}
                    </div>
                </div>
            `;
        }).join('')
        : '<div class="linha-vazia">Nenhuma categoria com previsão neste mês.</div>';

    return `
        <div class="fatura-bloco">
            <div class="bloco-header">
                <span class="bloco-titulo">Despesas por Categoria</span>
                <span class="bloco-subtotal">Previsto</span>
            </div>
            <div class="bloco-lista">${conteudo}</div>
        </div>
    `;
}

function renderizarBlocoOutros(outros) {
    const total = outros.reduce((sum, o) => sum + (o.valor || 0), 0);
    const linhas = outros.length > 0
        ? outros.map(o => `
            <div class="linha-simples">
                <div>
                    <div class="linha-titulo">${o.descricao}</div>
                    ${o.data_compra ? `<div class="linha-legenda">${formatarDataCurta(o.data_compra)}</div>` : ''}
                </div>
                <div class="linha-valor">R$ ${formatarValorBR(o.valor)}</div>
            </div>
        `).join('')
        : '<div class="linha-vazia">Sem outros lançamentos no cartão.</div>';

    return `
        <div class="fatura-bloco">
            <div class="bloco-header">
                <span class="bloco-titulo">Outros Lançamentos</span>
                <span class="bloco-subtotal">R$ ${formatarValorBR(total)}</span>
            </div>
            <div class="bloco-lista">${linhas}</div>
        </div>
    `;
}

function renderizarRodapeFatura(blocos) {
    const totalParceladas = blocos.parceladas.reduce((sum, p) => sum + (p.valor || 0), 0);
    const totalFixas = blocos.fixas.reduce((sum, f) => sum + (f.valor || 0), 0);
    const totalOutros = blocos.outros.reduce((sum, o) => sum + (o.valor || 0), 0);
    const linhasCategorias = Object.values(blocos.porCategoria || {}).map(cat => {
        const previsto = parseFloat(cat.previsto || 0);
        const executado = (cat.lancamentos || []).reduce((s, l) => s + parseFloat(l.valor || 0), 0);
        const valorRodape = Math.max(previsto, executado);
        return `
        <div class="rodape-linha">
            <span class="rodape-valor">R$ ${formatarValorBR(valorRodape)}</span>
            <span class="rodape-label">${cat.nome}</span>
        </div>
    `;
    }).join('');

    return `
        <div class="rodape-fatura">
            <div class="rodape-linha">
                <span class="rodape-valor">R$ ${formatarValorBR(totalParceladas)}</span>
                <span class="rodape-label">Compras Parceladas do mês</span>
            </div>
            <div class="rodape-linha">
                <span class="rodape-valor">R$ ${formatarValorBR(totalFixas)}</span>
                <span class="rodape-label">Despesas Fixas</span>
            </div>
            ${linhasCategorias}
            <div class="rodape-linha">
                <span class="rodape-valor">R$ ${formatarValorBR(totalOutros)}</span>
                <span class="rodape-label">Outros Lançamentos</span>
            </div>
        </div>
    `;
}

function toggleCategoriaDetalhe(categoriaId) {
    const detalhe = document.getElementById(`categoria-detalhe-${categoriaId}`);
    if (!detalhe) return;

    detalhe.style.display = detalhe.style.display === 'none' || detalhe.style.display === ''
        ? 'block'
        : 'none';
}

function formatarValorBR(valor) {
    const numero = parseFloat(valor || 0);
    return numero.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatarParcelaAtual(numero, total) {
    if (!total || total <= 1) return '';
    const atual = String(numero || 1).padStart(2, '0');
    const totalFormatado = String(total).padStart(2, '0');
    return `${atual}/${totalFormatado}`;
}

function formatarDataCurta(dataISO) {
    if (!dataISO) return '';
    const data = new Date(`${dataISO}T00:00:00`);
    return data.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

function normalizarCompetencia(competencia) {
    if (!competencia) return '';
    return competencia.substring(0, 7);
}

function formatarCompetenciaCompleta(competencia) {
    const comp = normalizarCompetencia(competencia);
    if (!comp || comp.length < 7) return comp || '';

    const [ano, mes] = comp.split('-');
    const meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
    const nomeMes = meses[parseInt(mes, 10) - 1] || mes;
    return `${nomeMes}/${ano}`;
}

/**
 * Consolida (fecha) uma fatura de cartão de crédito
 * Apenas faturas com status='ABERTA' podem ser consolidadas
 */
async function consolidarFatura(cartaoId, competencia) {
    // Extrair apenas YYYY-MM da competencia
    const mesCompetencia = competencia.substring(0, 7);

    if (!confirm(`Deseja consolidar a fatura de ${mesCompetencia}?\n\nApós a consolidação, a fatura ficará marcada como FECHADA.\nAinda será possível adicionar lançamentos, mas o valor consolidado será mantido como referência.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/cartoes/${cartaoId}/faturas/${mesCompetencia}/consolidar`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.erro || 'Erro ao consolidar fatura');
        }

        // Sucesso
        alert(`Fatura consolidada com sucesso!\n\nValor consolidado: R$ ${data.fatura.valor_consolidado.toFixed(2).replace('.', ',')}\nStatus: ${data.fatura.status_fatura}`);

        // Recarregar lista de despesas
        carregarDespesas();

    } catch (error) {
        console.error('Erro ao consolidar fatura:', error);
        alert(`Erro ao consolidar fatura: ${error.message}`);
    }
}

// Fechar modal ao clicar fora dele
window.onclick = function(event) {
    const modal = document.getElementById('modal-despesa');
    if (event.target === modal) {
        fecharModal();
    }
}
