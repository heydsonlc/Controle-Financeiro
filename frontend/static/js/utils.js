/**
 * Utilitários gerais do sistema
 * Conforme contrato de API em /docs/api-contract.md
 */

/**
 * Extrai array de uma resposta de API
 * Garante compatibilidade com diferentes formatos de resposta
 *
 * @param {*} response - Resposta da API
 * @returns {Array} Array de dados ou array vazio
 */
function extrairArray(response) {
    // Se já é array, retorna direto
    if (Array.isArray(response)) return response;

    // Se tem propriedade 'data' com array, retorna
    if (response?.data && Array.isArray(response.data)) return response.data;

    // Se tem propriedade 'categorias' com array, retorna
    if (response?.categorias && Array.isArray(response.categorias)) return response.categorias;

    // Se tem propriedade 'itens' com array, retorna
    if (response?.itens && Array.isArray(response.itens)) return response.itens;

    // Fallback: retorna array vazio para evitar erros
    console.warn('⚠️ extrairArray: formato inesperado', response);
    return [];
}
