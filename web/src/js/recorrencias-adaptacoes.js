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
