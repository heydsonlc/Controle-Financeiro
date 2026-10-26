// FIN-FIDELIDADE-MOVIMENTACOES-1 — correcao de um defeito da tela original de Lancamentos (js/original/lancamentos.js
// fica igual ao Flask). Na abertura, carregarCartoes() e carregarLancamentos() rodam juntos: a lista percorre
// state.cartoes antes de os cartoes chegarem e sai sem as compras de cartao (no Flask elas so aparecem depois de salvar
// algo). Aqui a lista espera a carga de cartoes em andamento; a ordem e o restante ficam como no Flask.
// Script classico, depois de lancamentos.js e antes do DOMContentLoaded.
(function () {
    'use strict';
    const carregarCartoes = window.carregarCartoes;
    const carregarLancamentos = window.carregarLancamentos;
    if (typeof carregarCartoes !== 'function' || typeof carregarLancamentos !== 'function') return;
    let cartoes = Promise.resolve();
    window.carregarCartoes = function (...args) {
        cartoes = Promise.resolve(carregarCartoes.apply(this, args)).catch(() => {});
        return cartoes;
    };
    window.carregarLancamentos = async function (...args) {
        await cartoes;
        return carregarLancamentos.apply(this, args);
    };
}());
