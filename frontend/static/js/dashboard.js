// ============================================
// DASHBOARD - JAVASCRIPT PRINCIPAL
// ============================================

const API_BASE = 'http://localhost:5000/api/dashboard';

// Instâncias dos gráficos (para poder destruir ao atualizar)
let graficoCategorias = null;
let graficoEvolucao = null;
let graficoSaldo = null;

// ============================================
// INICIALIZAÇÃO
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    carregarDashboard();
});

async function carregarDashboard() {
    try {
        // Carregar todos os dados em paralelo
        await Promise.all([
            carregarResumoMes(),
            carregarIndicadores(),
            carregarGraficoCategorias(),
            carregarGraficoEvolucao(),
            carregarGraficoSaldo(),
            carregarAlertas(),
            carregarAgendaFinanceira()
        ]);

        // Gerar leitura do mês após carregar dados
        await gerarLeituraDoMes();
    } catch (error) {
        console.error('Erro ao carregar dashboard:', error);
        mostrarErro('Erro ao carregar dados do dashboard');
    }
}

// ============================================
// BLOCO 1: RESUMO FINANCEIRO DO MÊS
// ============================================
async function carregarResumoMes() {
    try {
        const response = await fetch(`${API_BASE}/resumo-mes`);
        const data = await response.json();

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
        const response = await fetch(`${API_BASE}/indicadores`);
        const data = await response.json();

        if (data.success) {
            const indicadores = data.data;
            const container = document.getElementById('indicadores-container');
            container.innerHTML = '';

            // 1. Despesas acima da média
            if (indicadores.despesas_acima_media) {
                container.appendChild(criarIndicadorChip(
                    '🔥',
                    'Despesas acima da média',
                    `${formatarMoeda(indicadores.despesas_mes_atual)} vs ${formatarMoeda(indicadores.media_historica)}`,
                    'vermelho'
                ));
            }

            // 2. Gastos pendentes próximos
            if (indicadores.gastos_pendentes_proximos > 0) {
                container.appendChild(criarIndicadorChip(
                    '⚠️',
                    'Contas a vencer (7 dias)',
                    `${indicadores.gastos_pendentes_proximos} conta(s)`,
                    'amarelo'
                ));
            }

            // 3. Faturas de cartão próximas
            if (indicadores.faturas_cartao_proximas > 0) {
                container.appendChild(criarIndicadorChip(
                    '💳',
                    'Faturas próximas',
                    `${indicadores.faturas_cartao_proximas} cartão(ões)`,
                    'azul'
                ));
            }

            // 4. Percentual poupado
            if (indicadores.percentual_poupado > 0) {
                container.appendChild(criarIndicadorChip(
                    '💰',
                    'Você poupou',
                    `${indicadores.percentual_poupado}% da sua renda`,
                    'verde'
                ));
            } else if (indicadores.percentual_poupado < 0) {
                container.appendChild(criarIndicadorChip(
                    '⚡',
                    'Gastos acima da receita',
                    `${Math.abs(indicadores.percentual_poupado)}% a mais`,
                    'vermelho'
                ));
            }

            // 5. Receitas extras
            if (indicadores.receitas_extras > 0) {
                container.appendChild(criarIndicadorChip(
                    '🎁',
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
        const response = await fetch(`${API_BASE}/grafico-categorias`);
        const data = await response.json();

        if (data.success && data.data.labels.length > 0) {
            const ctx = document.getElementById('grafico-categorias').getContext('2d');

            // Destruir gráfico anterior se existir
            if (graficoCategorias) {
                graficoCategorias.destroy();
            }

            graficoCategorias = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: data.data.labels,
                    datasets: [{
                        data: data.data.valores,
                        backgroundColor: data.data.cores,
                        borderWidth: 2,
                        borderColor: 'rgba(255, 255, 255, 0.8)'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: {
                                color: 'white',
                                font: {
                                    size: 12
                                },
                                padding: 10
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
        const response = await fetch(`${API_BASE}/grafico-evolucao`);
        const data = await response.json();

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
        const response = await fetch(`${API_BASE}/grafico-saldo`);
        const data = await response.json();

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
        const response = await fetch(`${API_BASE}/alertas`);
        const data = await response.json();

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
                <span>📅 ${conta.data_vencimento} | ${conta.categoria}</span>
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
                <span>📅 ${cartao.data_vencimento} | ${cartao.status}</span>
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
                <span>📅 ${receita.data_recebimento} | ${receita.fonte}</span>
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
            fetch(`${API_BASE}/resumo-mes`),
            fetch(`${API_BASE}/indicadores`),
            fetch(`${API_BASE}/grafico-categorias`)
        ]);

        const resumo = await resumoResponse.json();
        const indicadores = await indicadoresResponse.json();
        const categorias = await categoriasResponse.json();

        if (!resumo.success || !indicadores.success || !categorias.success) {
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
// FASE 6.1: AGENDA FINANCEIRA + INSIGHTS TEMPORAIS
// ============================================

async function carregarAgendaFinanceira() {
    try {
        const response = await fetch(`${API_BASE}/alertas`);
        const data = await response.json();

        if (data.success) {
            const alertas = data.data;

            // Consolidar todos os itens em uma única timeline
            const todosItens = consolidarTimeline(alertas);

            // Renderizar timeline
            renderizarTimeline(todosItens);

            // Gerar insights temporais
            gerarInsightsTemporais(todosItens);
        }
    } catch (error) {
        console.error('Erro ao carregar agenda financeira:', error);
        document.getElementById('timeline-agenda').innerHTML =
            '<p style="color: rgba(255,255,255,0.5);">Erro ao carregar agenda.</p>';
        document.getElementById('insights-temporais').innerHTML =
            '<p style="color: rgba(255,255,255,0.5);">Erro ao gerar insights.</p>';
    }
}

function consolidarTimeline(alertas) {
    const itens = [];
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);

    // Adicionar contas comuns
    if (alertas.contas_vencer) {
        alertas.contas_vencer.forEach(conta => {
            itens.push({
                data: parseDataBR(conta.data_vencimento),
                dataStr: conta.data_vencimento,
                tipo: 'Conta',
                descricao: conta.descricao,
                valor: conta.valor,
                status: 'Pendente',
                categoria: conta.categoria
            });
        });
    }

    // Adicionar faturas de cartão
    if (alertas.faturas_cartao) {
        alertas.faturas_cartao.forEach(cartao => {
            if (cartao.data_vencimento && cartao.data_vencimento !== 'N/A') {
                itens.push({
                    data: parseDataBR(cartao.data_vencimento),
                    dataStr: cartao.data_vencimento,
                    tipo: 'Cartão',
                    descricao: cartao.nome,
                    valor: cartao.valor,
                    status: cartao.status,
                    categoria: 'Fatura de Cartão'
                });
            }
        });
    }

    // Adicionar financiamentos
    if (alertas.financiamentos) {
        alertas.financiamentos.forEach(fin => {
            // Financiamentos não têm data_vencimento específica, usar primeiro dia do mês
            const primeiroDiaMes = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
            itens.push({
                data: primeiroDiaMes,
                dataStr: primeiroDiaMes.toLocaleDateString('pt-BR'),
                tipo: 'Financiamento',
                descricao: `${fin.descricao} (${fin.parcela_atual}/${fin.total_parcelas})`,
                valor: fin.valor_parcela,
                status: 'Pendente',
                categoria: 'Financiamento'
            });
        });
    }

    // Ordenar por data (ascendente)
    itens.sort((a, b) => a.data - b.data);

    return itens;
}

function parseDataBR(dataStr) {
    // Converte DD/MM/YYYY para Date
    const [dia, mes, ano] = dataStr.split('/');
    return new Date(ano, mes - 1, dia);
}

function renderizarTimeline(itens) {
    const container = document.getElementById('timeline-agenda');

    if (itens.length === 0) {
        container.innerHTML = '<p style="color: rgba(255,255,255,0.5);">Nenhum evento financeiro no período.</p>';
        return;
    }

    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);

    let html = '<div style="display: flex; flex-direction: column; gap: 12px;">';

    itens.forEach(item => {
        const isHoje = item.data.getTime() === hoje.getTime();
        const isPassado = item.data < hoje;

        const bgColor = isHoje ? 'rgba(0, 122, 255, 0.15)' : 'rgba(255,255,255,0.05)';
        const borderColor = isHoje ? '#007aff' : 'rgba(255,255,255,0.1)';
        const textOpacity = isPassado ? '0.5' : '0.9';

        html += `
            <div style="
                background: ${bgColor};
                border-left: 3px solid ${borderColor};
                border-radius: 6px;
                padding: 12px 16px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                opacity: ${textOpacity};
            ">
                <div style="flex: 1;">
                    <div style="font-size: 0.85em; color: rgba(255,255,255,0.6); margin-bottom: 4px;">
                        ${item.dataStr} ${isHoje ? '• HOJE' : ''}
                    </div>
                    <div style="font-weight: 500; color: white; margin-bottom: 2px;">
                        ${item.descricao}
                    </div>
                    <div style="font-size: 0.85em; color: rgba(255,255,255,0.6);">
                        ${item.tipo} ${item.categoria ? `• ${item.categoria}` : ''}
                    </div>
                </div>
                <div style="font-weight: 600; color: white; white-space: nowrap; margin-left: 16px;">
                    ${formatarMoeda(item.valor)}
                </div>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

function gerarInsightsTemporais(itens) {
    const container = document.getElementById('insights-temporais');

    if (itens.length === 0) {
        container.innerHTML = '<p style="color: rgba(255,255,255,0.5);">Dados insuficientes para gerar insights.</p>';
        return;
    }

    const frases = [];
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);

    // Insight 1: Percentual já vencido
    const itensPassados = itens.filter(item => item.data <= hoje);
    const percentualVencido = Math.round((itensPassados.length / itens.length) * 100);

    if (percentualVencido > 0) {
        frases.push(`Até hoje, ${percentualVencido}% das despesas do mês já venceram.`);
    }

    // Insight 2: Concentração temporal
    const primeiraDezena = itens.filter(item => item.data.getDate() <= 10).length;
    const segundaDezena = itens.filter(item => item.data.getDate() > 10 && item.data.getDate() <= 20).length;
    const terceiraDezena = itens.filter(item => item.data.getDate() > 20).length;

    const maiorConcentracao = Math.max(primeiraDezena, segundaDezena, terceiraDezena);
    if (maiorConcentracao === terceiraDezena && terceiraDezena > 0) {
        frases.push('O maior volume de vencimentos ocorre na terceira dezena do mês.');
    } else if (maiorConcentracao === segundaDezena && segundaDezena > 0) {
        frases.push('O maior volume de vencimentos concentra-se entre os dias 11 e 20.');
    } else if (primeiraDezena > 0) {
        frases.push('O maior volume de vencimentos ocorre nos primeiros 10 dias do mês.');
    }

    // Insight 3: Cartões
    const itensCartao = itens.filter(item => item.tipo === 'Cartão');
    if (itensCartao.length > 0) {
        const mediaDataCartao = itensCartao.reduce((acc, item) => acc + item.data.getDate(), 0) / itensCartao.length;
        if (mediaDataCartao > 20) {
            frases.push('As despesas de cartão concentram-se após o dia 20.');
        }
    }

    // Renderizar insights (máximo 3)
    container.innerHTML = frases.slice(0, 3).map(frase =>
        `<p style="margin: 8px 0; font-size: 14px;">${frase}</p>`
    ).join('');
}

// Atualizar dashboard a cada 5 minutos
setInterval(() => {
    carregarDashboard();
}, 5 * 60 * 1000);
