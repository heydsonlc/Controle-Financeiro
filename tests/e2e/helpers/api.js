/**
 * Utilitários de API para testes E2E.
 * Verifica ambiente antes de criar dados para evitar contaminação em desenvolvimento.
 */

const BASE_URL = 'http://localhost:5000';

/**
 * Garante que o servidor em execução está em modo 'testing'.
 * Deve ser chamado antes de qualquer criação de dado nos testes funcionais.
 * Lança erro se o ambiente for diferente de 'testing'.
 */
async function ensureTestingEnvironment(request) {
  const response = await request.get(`${BASE_URL}/health`);
  const body = await response.json();

  if (body.environment !== 'testing') {
    throw new Error(
      `[TEST-2A] Servidor está em ambiente '${body.environment}', não 'testing'. ` +
      `Abortando para evitar criação de dados em ambiente real.`
    );
  }
}

module.exports = { ensureTestingEnvironment, BASE_URL };
