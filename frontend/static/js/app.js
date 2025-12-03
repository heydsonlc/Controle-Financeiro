/**
 * JavaScript principal do sistema de controle financeiro
 */

// Configuração base da API
const API_BASE_URL = 'http://localhost:5000/api';

/**
 * Faz requisições para a API
 */
async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;

    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('Erro na requisição:', error);
        throw error;
    }
}

/**
 * Carrega dados iniciais do dashboard
 */
async function loadDashboard() {
    console.log('Sistema de Controle Financeiro - Inicializado');

    // Verificar se estamos na página do dashboard
    if (!document.getElementById('receitas-mes')) {
        return; // Não é a página do dashboard
    }

    try {
        // Carregar resumo do mês
        await carregarResumoMes();

        // Carregar gráficos
        await carregarGraficoCategorias();
        await carregarGraficoEvolucao();

    } catch (error) {
        console.error('Erro ao carregar dashboard:', error);
    }
}

/**
 * Carrega o resumo financeiro do mês
 */
async function carregarResumoMes() {
    try {
        const response = await apiRequest('/dashboard/resumo-mes');

        if (response.success) {
            const data = response.data;

            // Atualizar cards de resumo
            document.getElementById('receitas-mes').textContent =
                `R$ ${data.receitas_mes.toFixed(2).replace('.', ',')}`;

            document.getElementById('despesas-mes').textContent =
                `R$ ${data.despesas_mes.toFixed(2).replace('.', ',')}`;

            document.getElementById('saldo-liquido').textContent =
                `R$ ${data.saldo_liquido.toFixed(2).replace('.', ',')}`;

            document.getElementById('saldo-contas').textContent =
                `R$ ${data.saldo_contas_bancarias.toFixed(2).replace('.', ',')}`;
        }
    } catch (error) {
        console.error('Erro ao carregar resumo do mês:', error);
    }
}

/**
 * Carrega dados do gráfico de categorias
 */
async function carregarGraficoCategorias() {
    try {
        const response = await apiRequest('/dashboard/grafico-categorias');

        if (response.success && response.data.length > 0) {
            renderizarGraficoPizza(response.data);
        } else {
            mostrarMensagemSemDados('grafico-categorias');
        }
    } catch (error) {
        console.error('Erro ao carregar gráfico de categorias:', error);
        mostrarMensagemSemDados('grafico-categorias');
    }
}

/**
 * Carrega dados do gráfico de evolução
 */
async function carregarGraficoEvolucao() {
    try {
        const response = await apiRequest('/dashboard/grafico-evolucao');

        if (response.success && response.data.length > 0) {
            renderizarGraficoEvolucao(response.data);
        } else {
            mostrarMensagemSemDados('grafico-evolucao');
        }
    } catch (error) {
        console.error('Erro ao carregar gráfico de evolução:', error);
        mostrarMensagemSemDados('grafico-evolucao');
    }
}

/**
 * Renderiza gráfico de pizza (categorias)
 */
function renderizarGraficoPizza(dados) {
    // TODO: Implementar com biblioteca de gráficos (Chart.js, ApexCharts, etc)
    console.log('Dados do gráfico de pizza:', dados);
}

/**
 * Renderiza gráfico de evolução
 */
function renderizarGraficoEvolucao(dados) {
    // TODO: Implementar com biblioteca de gráficos
    console.log('Dados do gráfico de evolução:', dados);
}

/**
 * Mostra mensagem quando não há dados
 */
function mostrarMensagemSemDados(containerId) {
    const container = document.getElementById(containerId);
    if (container) {
        container.innerHTML = '<p style="text-align: center; color: #6e6e73;">Sem dados para exibir</p>';
    }
}

// Inicializar quando o DOM estiver carregado
document.addEventListener('DOMContentLoaded', loadDashboard);
