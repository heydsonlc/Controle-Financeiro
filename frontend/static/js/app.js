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
    console.log('Aguardando implementação das rotas da API...');
}

// Inicializar quando o DOM estiver carregado
document.addEventListener('DOMContentLoaded', loadDashboard);
