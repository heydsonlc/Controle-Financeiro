// ============================================
// DASHBOARD - JAVASCRIPT PRINCIPAL
// ============================================

const API_BASE = '/api/dashboard';

function obterMensagemErro(payload, fallback = 'Erro ao processar requisição') {
    return payload?.error || payload?.erro || payload?.message || fallback;
}

// Instâncias dos gráficos (para poder destruir ao atualizar)
let graficoCategorias = null;
let graficoEvolucao = null;
let graficoSaldo = null;
let filtroPeriodoAtual = '';
let preferenciasDashboard = null;
const PALETA_CATEGORIAS_FALLBACK = [
    '#2563eb', '#ef4444', '#16a34a', '#f59e0b', '#7c3aed',
    '#0891b2', '#e11d48', '#65a30d', '#d97706', '#4f46e5'
];

function dashboardIcon(name) {
    const icons = {
        activity: '<path d="M4 13h4l2-6 4 10 2-4h4"/>',
        warning: '<path d="M12 5 3.5 19h17L12 5Z"/><path d="M12 10v4M12 17h.1"/>',
        card: '<path d="M4 7h16v10H4V7Z"/><path d="M4 10h16"/>',
        money: '<path d="M12 4v16"/><path d="M8 8.5h6a2.5 2.5 0 0 1 0 5h-4a2.5 2.5 0 0 0 0 5h6"/>',
        bolt: '<path d="M13 3 5 14h6l-1 7 8-11h-6l1-7Z"/>',
        gift: '<path d="M4 10h16v10H4V10Z"/><path d="M12 10v10M4 14h16"/><path d="M8 10a2 2 0 1 1 4 0M16 10a2 2 0 1 0-4 0"/>',
        calendar: '<path d="M7 4v3M17 4v3M5 9h14"/><path d="M5 6h14v14H5V6Z"/>'
    };

    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" style="width:1em;height:1em;display:inline-block;vertical-align:-0.125em;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;">${icons[name] || icons.activity}</svg>`;
}

// ============================================
// INICIALIZAÇÃO
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    inicializarFiltroPeriodo();
    carregarDashboard();
});

function buildApiUrl(path, extraParams = {}) {
    const params = new URLSearchParams();
    if (filtroPeriodoAtual) {
        params.set('periodo', filtroPeriodoAtual);
    }

    Object.entries(extraParams).forEach(([chave, valor]) => {
        if (valor !== undefined && valor !== null && `${valor}` !== '') {
            params.set(chave, valor);
        }
    });

    const query = params.toString();
    return `${API_BASE}${path}${query ? `?${query}` : ''}`;
}

function inicializarFiltroPeriodo() {
    const input = document.getElementById('filtro-periodo-input');
    const btnAplicar = document.getElementById('filtro-periodo-aplicar');
    const btnLimpar = document.getElementById('filtro-periodo-limpar');

    if (!input || !btnAplicar || !btnLimpar) return;

    const agora = new Date();
    const mes = String(agora.getMonth() + 1).padStart(2, '0');
    input.value = `${agora.getFullYear()}-${mes}`;
    filtroPeriodoAtual = input.value;

    btnAplicar.addEventListener('click', async () => {
        filtroPeriodoAtual = input.value || '';
        await carregarDashboard();
    });

    btnLimpar.addEventListener('click', async () => {
        const atual = new Date();
        const mesAtual = String(atual.getMonth() + 1).padStart(2, '0');
        input.value = `${atual.getFullYear()}-${mesAtual}`;
        filtroPeriodoAtual = input.value;
        await carregarDashboard();
    });
}

async function carregarDashboard() {
    try {
        await carregarPreferenciasDashboard();
        aplicarPreferenciasDashboard();

        // Carregar todos os dados em paralelo
        await Promise.all([
            carregarResumoMes(),
            carregarIndicadores(),
            carregarGraficoCategorias(),
            carregarGraficoEvolucao(),
            carregarGraficoSaldo(),
            carregarAlertas(),
            carregarFluxoCaixaProjetado()
        ]);

        // Gerar leitura do mês após carregar dados
        await gerarLeituraDoMes();
    } catch (error) {
        console.error('Erro ao carregar dashboard:', error);
        mostrarErro('Erro ao carregar dados do dashboard');
    }
}

async function carregarPreferenciasDashboard() {
    try {
        const response = await fetch('/api/preferencias');
        const data = await response.json();
        if (response.ok && data?.success) {
            preferenciasDashboard = data.data || null;
        }
    } catch (error) {
        console.error('Erro ao carregar preferências do dashboard:', error);
    }
}

function aplicarPreferenciasDashboard() {
    if (!preferenciasDashboard) return;

    const secaoIndicadores = document.getElementById('secao-indicadores');
    const cardCategorias = document.getElementById('card-grafico-categorias');
    const cardEvolucao = document.getElementById('card-grafico-evolucao');
    const cardSaldo = document.getElementById('card-grafico-saldo');
    const cardSaldoContas = document.getElementById('card-saldo-contas');

    const graficos = (preferenciasDashboard.graficos_visiveis || '')
        .split(',')
        .map(v => v.trim())
        .filter(Boolean);

    const mostrarCategorias = graficos.length === 0 || graficos.includes('categorias');
    const mostrarEvolucaoPref = graficos.length === 0 || graficos.includes('evolucao');
    const mostrarSaldoPref = graficos.length === 0 || graficos.includes('saldo');

    if (cardCategorias) cardCategorias.style.display = mostrarCategorias ? '' : 'none';
    if (cardEvolucao) {
        const habilitado = mostrarEvolucaoPref && preferenciasDashboard.mostrar_evolucao_historica !== false;
        cardEvolucao.style.display = habilitado ? '' : 'none';
    }
    if (cardSaldo) cardSaldo.style.display = mostrarSaldoPref ? '' : 'none';
    if (cardSaldoContas) {
        cardSaldoContas.style.display = preferenciasDashboard.mostrar_saldo_consolidado === false ? 'none' : '';
    }
    if (secaoIndicadores) {
        secaoIndicadores.style.display = preferenciasDashboard.insights_inteligentes_ativo === false ? 'none' : '';
    }
}

// ============================================
// BLOCO 1: RESUMO FINANCEIRO DO MÊS
// ============================================
async function carregarResumoMes() {
    try {
        const response = await fetch(buildApiUrl('/resumo-mes'));
        const data = await response.json();
        if (!response.ok || data?.success === false) {
            throw new Error(obterMensagemErro(data, 'Erro ao carregar resumo do mês'));
        }

        if (data.success) {
            const resumo = data.data;

            // Atualizar mês atual no header
            document.getElementById('mes-atual').textContent =
                `Visão Geral - ${resumo.mes_nome}`;

            // Atualizar cards de resumo
            document.getElementById('receitas-mes').textContent =
                formatarMoeda(resumo.receitas_mes);

            document.getElementById('despesas-mes').textContent =
                formatarMoeda(resumo.despesas_mes);

            const saldoLiquidoEl = document.getElementById('saldo-liquido');
            saldoLiquidoEl.textContent = formatarMoeda(resumo.saldo_liquido);

            // Colorir saldo líquido baseado no valor
            const cardSaldoLiquido = saldoLiquidoEl.closest('.resumo-card');
            if (resumo.saldo_liquido > 0) {
                cardSaldoLiquido.style.background = 'linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(34, 197, 94, 0.1))';
                cardSaldoLiquido.style.borderColor = 'rgba(34, 197, 94, 0.3)';
            } else if (resumo.saldo_liquido < 0) {
                cardSaldoLiquido.style.background = 'linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(239, 68, 68, 0.1))';
                cardSaldoLiquido.style.borderColor = 'rgba(239, 68, 68, 0.3)';
            }

            document.getElementById('saldo-contas').textContent =
                formatarMoeda(resumo.saldo_contas_bancarias);
        }
    } catch (error) {
        console.error('Erro ao carregar resumo do mês:', error);
    }
}

// ============================================
// BLOCO 2: INDICADORES INTELIGENTES
// ============================================
async function carregarIndicadores() {
    try {
        const response = await fetch(buildApiUrl('/indicadores'));
        const data = await response.json();
        if (!response.ok || data?.success === false) {
            throw new Error(obterMensagemErro(data, 'Erro ao carregar indicadores'));
        }

        if (data.success) {
            const indicadores = data.data;
            const container = document.getElementById('indicadores-container');
            container.innerHTML = '';

            // 1. Despesas acima da média
            if (indicadores.despesas_acima_media) {
                container.appendChild(criarIndicadorChip(
                    dashboardIcon('activity'),
                    'Despesas acima da média',
                    `${formatarMoeda(indicadores.despesas_mes_atual)} vs ${formatarMoeda(indicadores.media_historica)}`,
                    'vermelho'
                ));
            }

            // 2. Gastos pendentes próximos
            if (indicadores.gastos_pendentes_proximos > 0) {
                container.appendChild(criarIndicadorChip(
                    dashboardIcon('warning'),
                    'Contas a vencer (7 dias)',
                    `${indicadores.gastos_pendentes_proximos} conta(s)`,
                    'amarelo'
                ));
            }

            // 3. Faturas de cartão próximas
            if (indicadores.faturas_cartao_proximas > 0) {
                container.appendChild(criarIndicadorChip(
                    dashboardIcon('card'),
                    'Faturas próximas',
                    `${indicadores.faturas_cartao_proximas} cartão(ões)`,
                    'azul'
                ));
            }

            // 4. Percentual poupado
            if (indicadores.percentual_poupado > 0) {
                container.appendChild(criarIndicadorChip(
                    dashboardIcon('money'),
                    'Você poupou',
                    `${indicadores.percentual_poupado}% da sua renda`,
                    'verde'
                ));
            } else if (indicadores.percentual_poupado < 0) {
                container.appendChild(criarIndicadorChip(
                    dashboardIcon('bolt'),
                    'Gastos acima da receita',
                    `${Math.abs(indicadores.percentual_poupado)}% a mais`,
                    'vermelho'
                ));
            }

            // 5. Receitas extras
            if (indicadores.receitas_extras > 0) {
                container.appendChild(criarIndicadorChip(
                    dashboardIcon('gift'),
                    'Receitas extras',
                    formatarMoeda(indicadores.receitas_extras),
                    'roxo'
                ));
            }

            // Se não há indicadores
            if (container.children.length === 0) {
                container.innerHTML = '<p class="loading-indicator">Nenhum indicador disponível no momento</p>';
            }
        }
    } catch (error) {
        console.error('Erro ao carregar indicadores:', error);
    }
}

function criarIndicadorChip(icone, label, value, cor) {
    const chip = document.createElement('div');
    chip.className = `indicador-chip ${cor}`;
    chip.innerHTML = `
        <div class="indicador-icon">${icone}</div>
        <div class="indicador-info">
            <p class="label">${label}</p>
            <p class="value">${value}</p>
        </div>
    `;
    return chip;
}

// ============================================
// BLOCO 3: GRÁFICOS
// ============================================

// Gráfico de Pizza: Despesas por Categoria
async function carregarGraficoCategorias() {
    try {
        const response = await fetch(buildApiUrl('/grafico-categorias'));
        const data = await response.json();
        if (!response.ok || data?.success === false) {
            throw new Error(obterMensagemErro(data, 'Erro ao carregar gráfico de categorias'));
        }

        if (data.success && data.data.labels.length > 0) {
            const ctx = document.getElementById('grafico-categorias').getContext('2d');
            const labels = data.data.labels || [];
            const valores = data.data.valores || [];
            const cores = resolverCoresGraficoCategorias(data.data.cores || [], labels.length);
            const corTextoLegenda = obterCorTextoDashboard();

            // Destruir gráfico anterior se existir
            if (graficoCategorias) {
                graficoCategorias.destroy();
            }

            graficoCategorias = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels,
                    datasets: [{
                        data: valores,
                        backgroundColor: cores,
                        borderWidth: 2,
                        borderColor: 'rgba(255, 255, 255, 0.65)'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            align: 'start',
                            labels: {
                                color: corTextoLegenda,
                                font: {
                                    size: 12
                                },
                                padding: 12,
                                boxWidth: 12,
                                boxHeight: 12,
                                usePointStyle: true,
                                pointStyle: 'circle'
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.label || '';
                                    const value = formatarMoeda(context.parsed);
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentual = ((context.parsed / total) * 100).toFixed(1);
                                    return `${label}: ${value} (${percentual}%)`;
                                }
                            }
                        }
                    }
                }
            });
        } else {
            document.getElementById('grafico-categorias').parentElement.innerHTML =
                '<p style="color: rgba(255,255,255,0.6); text-align:center; padding: 40px;">Sem dados para exibir</p>';
        }
    } catch (error) {
        console.error('Erro ao carregar gráfico de categorias:', error);
    }
}

// Gráfico de Barras: Evolução de Gastos
async function carregarGraficoEvolucao() {
    try {
        const response = await fetch(buildApiUrl('/grafico-evolucao'));
        const data = await response.json();
        if (!response.ok || data?.success === false) {
            throw new Error(obterMensagemErro(data, 'Erro ao carregar gráfico de evolução'));
        }

        if (data.success && data.data.labels.length > 0) {
            const ctx = document.getElementById('grafico-evolucao').getContext('2d');

            if (graficoEvolucao) {
                graficoEvolucao.destroy();
            }

            graficoEvolucao = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.data.labels,
                    datasets: [{
                        label: 'Despesas',
                        data: data.data.valores,
                        backgroundColor: 'rgba(239, 68, 68, 0.6)',
                        borderColor: 'rgba(239, 68, 68, 1)',
                        borderWidth: 2,
                        borderRadius: 8
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return 'Despesas: ' + formatarMoeda(context.parsed.y);
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                color: 'white',
                                callback: function(value) {
                                    return 'R$ ' + value.toLocaleString('pt-BR');
                                }
                            },
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)'
                            }
                        },
                        x: {
                            ticks: {
                                color: 'white'
                            },
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)'
                            }
                        }
                    }
                }
            });
        } else {
            document.getElementById('grafico-evolucao').parentElement.innerHTML =
                '<p style="color: rgba(255,255,255,0.6); text-align:center; padding: 40px;">Sem dados para exibir</p>';
        }
    } catch (error) {
        console.error('Erro ao carregar gráfico de evolução:', error);
    }
}

// Gráfico de Linha: Evolução do Saldo
async function carregarGraficoSaldo() {
    try {
        const response = await fetch(buildApiUrl('/grafico-saldo'));
        const data = await response.json();
        if (!response.ok || data?.success === false) {
            throw new Error(obterMensagemErro(data, 'Erro ao carregar gráfico de saldo'));
        }

        if (data.success && data.data.labels.length > 0) {
            const ctx = document.getElementById('grafico-saldo').getContext('2d');

            if (graficoSaldo) {
                graficoSaldo.destroy();
            }

            graficoSaldo = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.data.labels,
                    datasets: [{
                        label: 'Saldo Bancário',
                        data: data.data.valores,
                        backgroundColor: 'rgba(59, 130, 246, 0.2)',
                        borderColor: 'rgba(59, 130, 246, 1)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 5,
                        pointBackgroundColor: 'rgba(59, 130, 246, 1)',
                        pointBorderColor: 'white',
                        pointBorderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return 'Saldo: ' + formatarMoeda(context.parsed.y);
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: false,
                            ticks: {
                                color: 'white',
                                callback: function(value) {
                                    return 'R$ ' + value.toLocaleString('pt-BR');
                                }
                            },
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)'
                            }
                        },
                        x: {
                            ticks: {
                                color: 'white'
                            },
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)'
                            }
                        }
                    }
                }
            });
        } else {
            document.getElementById('grafico-saldo').parentElement.innerHTML =
                '<p style="color: rgba(255,255,255,0.6); text-align:center; padding: 40px;">Sem dados para exibir</p>';
        }
    } catch (error) {
        console.error('Erro ao carregar gráfico de saldo:', error);
    }
}

// ============================================
// BLOCO 4: ALERTAS E AGENDA FINANCEIRA
// ============================================
async function carregarAlertas() {
    try {
        const response = await fetch(buildApiUrl('/alertas'));
        const data = await response.json();
        if (!response.ok || data?.success === false) {
            throw new Error(obterMensagemErro(data, 'Erro ao carregar alertas'));
        }

        if (data.success) {
            const alertas = data.data;

            // Contas a vencer
            exibirAlertasContas(alertas.contas_vencer);

            // Faturas de cartão
            exibirAlertasCartoes(alertas.cartoes_vencer);

            // Financiamentos
            exibirAlertasFinanciamentos(alertas.financiamentos_mes);

            // Receitas previstas
            exibirAlertasReceitas(alertas.receitas_previstas);
        }
    } catch (error) {
        console.error('Erro ao carregar alertas:', error);
    }
}

function exibirAlertasContas(contas) {
    const container = document.getElementById('contas-vencer');

    if (contas.length === 0) {
        container.innerHTML = '<p class="empty">Nenhuma conta a vencer nos próximos 7 dias</p>';
        return;
    }

    container.innerHTML = contas.map(conta => `
        <div class="alerta-item lancamento">
            <p class="item-titulo">${conta.descricao}</p>
            <div class="item-detalhes">
                <span>${dashboardIcon('calendar')} ${conta.data_vencimento} | ${conta.categoria}</span>
                <span class="item-valor">${formatarMoeda(conta.valor)}</span>
            </div>
        </div>
    `).join('');
}

function exibirAlertasCartoes(cartoes) {
    const container = document.getElementById('cartoes-vencer');

    if (cartoes.length === 0) {
        container.innerHTML = '<p class="empty">Nenhuma fatura próxima</p>';
        return;
    }

    container.innerHTML = cartoes.map(cartao => `
        <div class="alerta-item cartao">
            <p class="item-titulo">${cartao.nome}</p>
            <div class="item-detalhes">
                <span>${dashboardIcon('calendar')} ${cartao.data_vencimento} | ${cartao.status}</span>
                <span class="item-valor">${formatarMoeda(cartao.valor)}</span>
            </div>
        </div>
    `).join('');
}

function exibirAlertasFinanciamentos(financiamentos) {
    const container = document.getElementById('financiamentos-mes');

    if (financiamentos.length === 0) {
        container.innerHTML = '<p class="empty">Nenhum financiamento ativo</p>';
        return;
    }

    container.innerHTML = financiamentos.map(fin => `
        <div class="alerta-item financiamento">
            <p class="item-titulo">${fin.descricao}</p>
            <div class="item-detalhes">
                <span>Parcela ${fin.parcela_atual}/${fin.total_parcelas}</span>
                <span class="item-valor">${formatarMoeda(fin.valor_parcela)}</span>
            </div>
        </div>
    `).join('');
}

function exibirAlertasReceitas(receitas) {
    const container = document.getElementById('receitas-previstas');

    if (receitas.length === 0) {
        container.innerHTML = '<p class="empty">Nenhuma receita prevista</p>';
        return;
    }

    container.innerHTML = receitas.map(receita => `
        <div class="alerta-item receita">
            <p class="item-titulo">${receita.descricao}</p>
            <div class="item-detalhes">
                <span>${dashboardIcon('calendar')} ${receita.data_recebimento} | ${receita.fonte}</span>
                <span class="item-valor">${formatarMoeda(receita.valor)}</span>
            </div>
        </div>
    `).join('');
}

// ============================================
// FASE 5.2 — LEITURA DO MÊS
// Bloco interpretativo.
// NÃO cria regras.
// NÃO sugere ações.
// NÃO altera cálculos financeiros.
// ============================================

async function gerarLeituraDoMes() {
    try {
        // Buscar dados do resumo e indicadores
        const [resumoResponse, indicadoresResponse, categoriasResponse] = await Promise.all([
            fetch(buildApiUrl('/resumo-mes')),
            fetch(buildApiUrl('/indicadores')),
            fetch(buildApiUrl('/grafico-categorias'))
        ]);

        const resumo = await resumoResponse.json();
        const indicadores = await indicadoresResponse.json();
        const categorias = await categoriasResponse.json();

        if (
            !resumoResponse.ok || !indicadoresResponse.ok || !categoriasResponse.ok ||
            !resumo.success || !indicadores.success || !categorias.success
        ) {
            throw new Error('Dados incompletos');
        }

        const frases = [];
        const dados = resumo.data;
        const inds = indicadores.data;
        const cats = categorias.data;

        // Leitura 1: Saldo do Mês
        if (dados.saldo_liquido !== undefined) {
            if (dados.saldo_liquido > 0) {
                frases.push(`O saldo líquido do mês está positivo em ${formatarMoeda(dados.saldo_liquido)}.`);
            } else if (dados.saldo_liquido < 0) {
                frases.push(`O saldo líquido do mês está negativo em ${formatarMoeda(Math.abs(dados.saldo_liquido))}.`);
            } else {
                frases.push(`O saldo líquido do mês está equilibrado.`);
            }
        }

        // Leitura 2: Execução do Orçamento (se disponível)
        if (dados.despesas_mes > 0 && inds.despesas_mes_atual > 0) {
            const percentual = Math.round((inds.despesas_mes_atual / dados.despesas_mes) * 100);
            if (percentual > 0 && percentual <= 100) {
                frases.push(`Até agora, ${percentual}% das despesas previstas já foram executadas.`);
            }
        }

        // Leitura 3: Principal Origem de Despesa
        if (cats.labels && cats.labels.length > 0 && cats.valores && cats.valores.length > 0) {
            const indiceMaior = cats.valores.indexOf(Math.max(...cats.valores));
            const categoriaPrincipal = cats.labels[indiceMaior];
            frases.push(`A maior parte das despesas do mês está concentrada em ${categoriaPrincipal}.`);
        }

        // Leitura 4: Cartões (condicional)
        if (inds.faturas_cartao_proximas > 0) {
            frases.push(`As faturas de cartão representam uma parcela relevante das despesas do mês.`);
        }

        // Leitura 5: Situação Geral (neutra)
        if (dados.saldo_liquido >= 0 && inds.percentual_poupado >= 0) {
            frases.push(`O mês apresenta um comportamento financeiro consistente até o momento.`);
        } else {
            frases.push(`O comportamento financeiro do mês exige acompanhamento.`);
        }

        // Renderizar leitura (máximo 5 frases)
        const container = document.getElementById('leitura-container');
        container.innerHTML = frases.slice(0, 5).map(frase =>
            `<p style="margin: 8px 0; font-size: 14px;">${frase}</p>`
        ).join('');

    } catch (error) {
        console.error('Erro ao gerar leitura do mês:', error);
        const container = document.getElementById('leitura-container');
        container.innerHTML = '<p style="color: rgba(255,255,255,0.5);">Dados insuficientes para gerar leitura.</p>';
    }
}

// ============================================
// FUNÇÕES AUXILIARES
// ============================================
function formatarMoeda(valor) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(valor);
}

function mostrarErro(mensagem) {
    alert(mensagem);
}

// ============================================
// UTILITARIOS DO GRAFICO DE CATEGORIAS
// ============================================

function obterCorTextoDashboard() {
    try {
        const cor = window.getComputedStyle(document.body).color;
        return cor || '#1d1d1f';
    } catch (_) {
        return '#1d1d1f';
    }
}
function resolverCoresGraficoCategorias(coresOriginais, quantidade) {
    if (quantidade <= 0) return [];
    const coresLimpas = (coresOriginais || [])
        .map(cor => typeof cor === 'string' ? cor.trim() : '')
        .filter(Boolean);
    const coresUnicas = [...new Set(coresLimpas.map(cor => cor.toLowerCase()))];
    const precisaFallback = coresLimpas.length !== quantidade || coresUnicas.length <= 1;
    if (!precisaFallback) {
        return coresLimpas.slice(0, quantidade);
    }
    const paleta = [];
    for (let i = 0; i < quantidade; i += 1) {
        paleta.push(PALETA_CATEGORIAS_FALLBACK[i % PALETA_CATEGORIAS_FALLBACK.length]);
    }
    return paleta;
}

async function carregarFluxoCaixaProjetado() {
    try {
        const response = await fetch(buildApiUrl('/fluxo-caixa-projetado', { meses: 4 }));
        const data = await response.json();
        if (!response.ok || data?.success === false) {
            throw new Error(obterMensagemErro(data, 'Erro ao carregar fluxo projetado'));
        }

        const container = document.getElementById('fluxo-projetado-lista');
        const subtitle = document.getElementById('fluxo-projetado-subtitle');
        if (!container || !subtitle || !data?.data) return;

        const bloco = data.data;
        subtitle.textContent = `${bloco.horizonte_meses} mes(es) a partir de ${bloco.periodo_inicio}`;

        if (!bloco.labels || bloco.labels.length === 0) {
            container.innerHTML = '<p class="empty">Sem dados para projecao.</p>';
            return;
        }

        container.innerHTML = bloco.labels.map((label, index) => `
            <div class="fluxo-item">
                <div><strong>${label}</strong></div>
                <div>Entradas: ${formatarMoeda(bloco.entradas[index] || 0)}</div>
                <div>Saidas: ${formatarMoeda(bloco.saidas[index] || 0)}</div>
                <div class="saldo">Saldo proj.: ${formatarMoeda(bloco.saldo_projetado[index] || 0)}</div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Erro ao carregar fluxo projetado:', error);
        const container = document.getElementById('fluxo-projetado-lista');
        const subtitle = document.getElementById('fluxo-projetado-subtitle');
        if (container) {
            container.innerHTML = '<p class="empty">Erro ao carregar projecao.</p>';
        }
        if (subtitle) {
            subtitle.textContent = 'Erro ao carregar projecao';
        }
    }
}

// Atualizar dashboard a cada 5 minutos
setInterval(() => {
    carregarDashboard();
}, 5 * 60 * 1000);
