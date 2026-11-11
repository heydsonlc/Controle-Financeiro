// FIN-RECORRENCIAS-INATIVACAO-01 (P22) — o minimo que a tela original de Recorrencias (js/original/recorrencias.js, sem
// alteracao) precisa: "Inativar" passa a mostrar antes o impacto (data de efeito, ocorrencias que deixam de ser exigiveis,
// valor e as que ficam protegidas) e so entao interrompe; numa recorrencia ja inativa, a mesma acao cancela as
// ocorrencias futuras que ficaram. Reativar pelo formulario mostra a retomada (periodo inativo e restauracao opcional).
// Script classico, carregado depois do original; consorcios seguem o caminho original.
(function () {
    'use strict';

    const API = '/api/recorrencias';

    async function json(url, opcoes) {
        const resposta = await fetch(url, opcoes);
        return resposta.json();
    }

    const enviar = (url, corpo) => json(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) });

    // Promise: resultado da operacao confirmada, ou null se o usuario cancelou.
    function situacao(id, ativo) {
        if (ativo) {
            return window.CFInterrupcao.retomar({
                buscar: (retomada) => json(`${API}/${id}/previa-retomada${retomada ? `?retomada=${retomada}` : ''}`),
                executar: (p, restaurar) => enviar(`${API}/${id}/retomar`, { versao: p.versao, retomada: p.retomada, restaurar }),
            });
        }
        return window.CFInterrupcao.interromper({
            incluirAtual: true,
            buscar: (efeito) => json(`${API}/${id}/previa-interrupcao${efeito ? `?efeito=${efeito}` : ''}`),
            executar: (p) => enviar(`${API}/${id}/interromper`, { versao: p.versao, efeito: p.efeito, esperadas: p.quantidade }),
        });
    }

    window.CF_SITUACAO_RECORRENCIA = situacao;

    const inativarOriginal = window.inativarRecorrencia;
    window.inativarRecorrencia = async function inativarRecorrencia(origem, id) {
        if (origem === 'consorcio') return inativarOriginal(origem, id);
        if (await situacao(id, false)) await window.carregarRecorrencias();
        return undefined;
    };
})();

// P24 (FIN-CONSORCIOS-INTEGRACAO-01): consorcio ja em andamento. No cadastro (nao na edicao), o contrato e informado
// inteiro (Data inicial = mes da 1a parcela, numero total de parcelas) e o campo abaixo diz quantas das primeiras ja foram
// pagas antes do cadastro: elas ficam pagas no historico, sem debito bancario, e a numeracao segue a do contrato (5/10).
(function () {
    function campo() {
        const grupo = document.getElementById('campos-consorcio');
        if (!grupo || document.getElementById('parcelas-pagas-anteriores')) return;
        const caixa = document.createElement('div');
        caixa.className = 'form-group';
        caixa.id = 'grupo-parcelas-pagas-anteriores';
        const rotulo = Object.assign(document.createElement('label'), { textContent: 'Parcelas já pagas antes do cadastro' });
        rotulo.htmlFor = 'parcelas-pagas-anteriores';
        const entrada = Object.assign(document.createElement('input'), { type: 'number', id: 'parcelas-pagas-anteriores', min: '0', step: '1',
            placeholder: '0' });
        const ajuda = Object.assign(document.createElement('small'), { id: 'parcelas-pagas-anteriores-ajuda',
            textContent: 'Contrato em andamento: informe o mês da 1ª parcela e o total do contrato. As primeiras parcelas pagas '
                + 'ficam no histórico como pagas, sem débito bancário.' });
        entrada.setAttribute('aria-describedby', ajuda.id);
        caixa.append(rotulo, entrada, ajuda);
        grupo.appendChild(caixa);
    }
    function ajustar() {
        campo();
        const caixa = document.getElementById('grupo-parcelas-pagas-anteriores');
        if (!caixa) return;
        const editando = Boolean(document.getElementById('recorrencia-id')?.value);
        caixa.hidden = editando;  // so no cadastro
        if (editando) document.getElementById('parcelas-pagas-anteriores').value = '';
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ajustar);
    else ajustar();
    ['prepararFormularioNovaRecorrencia', 'editarRecorrencia', 'alternarTipoCadastro'].forEach((nome) => {
        const original = window[nome];
        if (typeof original !== 'function') return;
        window[nome] = function (...args) {
            const r = original.apply(this, args);
            Promise.resolve(r).then(ajustar);
            ajustar();
            return r;
        };
    });
}());
