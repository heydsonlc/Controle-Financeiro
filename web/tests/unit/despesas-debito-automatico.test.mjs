// FIN-DESPESAS-DEBITO-AUTOMATICO-01 (P19) — conta bancaria enviada na edicao de uma despesa em debito automatico e a
// mensagem da recusa do banco. Dados FICTICIOS.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { contaDoDebito, mensagemDeErro } from '../../src/js/adaptador-comum.js';

const edicao = (conta, item) => ({ conta, item });

test('despesa gerada antes do vinculo usa a conta da recorrencia', () => {
    assert.equal(contaDoDebito(edicao({ debito_automatico: true, conta_bancaria_id: null }, { conta_bancaria_id: 96 })), 96);
});

test('a conta propria da despesa prevalece sobre a da recorrencia', () => {
    assert.equal(contaDoDebito(edicao({ debito_automatico: true, conta_bancaria_id: 97 }, { conta_bancaria_id: 96 })), 97);
});

test('sem conta em lugar nenhum: segue vazia e o banco recusa', () => {
    assert.equal(contaDoDebito(edicao({ debito_automatico: true, conta_bancaria_id: null }, { conta_bancaria_id: null })), null);
    assert.equal(contaDoDebito(edicao({ debito_automatico: true }, {})), null);
});

test('sem debito automatico a conta da recorrencia nao entra', () => {
    assert.equal(contaDoDebito(edicao({ debito_automatico: false, conta_bancaria_id: null }, { conta_bancaria_id: 96 })), null);
});

test('recusa do banco diz onde vincular a conta', () => {
    const texto = mensagemDeErro({ code: '22023', message: 'Debito automatico exige uma conta bancaria ativa do perfil' });
    assert.match(texto, /^Débito automático exige uma conta bancária ativa do perfil\. Vincule a conta na recorrência/);
    assert.match(texto, /Nada foi gravado\.$/);
});
