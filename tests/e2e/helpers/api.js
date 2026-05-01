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
  const body = await getHealth(request, 'TEST-2A');

  if (body.environment !== 'testing') {
    throw new Error(
      `[TEST-2A] Servidor está em ambiente '${body.environment}', não 'testing'. ` +
      `Abortando para evitar criação de dados em ambiente real.`
    );
  }
}

async function skipUnlessTestingEnvironment(testApi, request, label = 'TEST-2B') {
  const body = await getHealth(request, label);

  testApi.skip(
    body.environment !== 'testing',
    `[${label}] Testes funcionais de criaÃ§Ã£o exigem FLASK_ENV=testing. Ambiente atual: ${body.environment}.`
  );

  return body;
}

async function getHealth(request, label) {
  const response = await request.get(`${BASE_URL}/health`);
  if (!response.ok()) {
    throw new Error(`[${label}] /health retornou status ${response.status()}`);
  }

  return response.json();
}

module.exports = { ensureTestingEnvironment, skipUnlessTestingEnvironment, BASE_URL };
