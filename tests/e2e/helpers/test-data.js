/**
 * Geradores de nomes únicos para dados de teste E2E.
 * Prefixo TESTE_E2E_ + timestamp garante isolamento e facilita limpeza manual.
 */

function timestamp() {
  return Date.now();
}

function makeCategoriaNome() {
  return `TESTE_E2E_Cat_${timestamp()}`;
}

function makeContaNome() {
  return `TESTE_E2E_Conta_${timestamp()}`;
}

function makeFonteNome() {
  return `TESTE_E2E_Fonte_${timestamp()}`;
}

module.exports = { makeCategoriaNome, makeContaNome, makeFonteNome };
