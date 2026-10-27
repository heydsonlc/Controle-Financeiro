// FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 — adaptacoes da tela original de Receitas (js/original/receitas.js nao muda):
// - sem linha "virtual": o Flask mostra a fonte recorrente sem previsao gravada no mes como prevista (valor base); aqui
//   so previsoes e recebimentos reais (FIN-RECEITAS-1), os mesmos numeros do Dashboard e da tela de Despesas;
// - "Consolidar Receita": o Flask registra so o que falta, com a data de hoje. Os campos acrescentados ao modal
//   (valor, data e justificativa) mantem o recebimento parcial, em outra data ou acima do previsto do novo aplicativo.
//   O valor visivel alimenta o campo oculto que o JS do Flask envia; data e justificativa sao lidas pelo adaptador.
// - FIN-CATEGORIAS-RECORRENCIAS-2: "Proximos recebimentos" usa a data prevista gravada na previsao (FIN-RECEITAS-DATA-
//   REAL-1: pode cair em outro mes, ex.: competencia 10 recebida em 05/11); sem ela, o dia previsto da fonte, como o
//   Flask. A linha leva a data inteira no lugar do dia, e montarDataPrevista a devolve como esta.
(function () {
    const original = window.montarReceitasMes;
    if (typeof original === 'function') {
        window.montarReceitasMes = function (...args) {
            const linhas = original.apply(this, args).filter((linha) => linha.origem !== 'fonte_base');
            // estado: global de js/original/receitas.js (script classico carregado antes deste)
            const orcamentos = (typeof estado !== 'undefined' && estado && estado.orcamentos) || [];
            const datas = new Map(orcamentos.filter((o) => o.data_prevista).map((o) => [o.id, o.data_prevista]));
            return linhas.map((l) => (datas.has(l.orcamento_id) ? { ...l, dia_previsto_pagamento: datas.get(l.orcamento_id) } : l));
        };
    }
    const montarData = window.montarDataPrevista;
    if (typeof montarData === 'function') {
        window.montarDataPrevista = function (anoMes, dia) {
            return /^\d{4}-\d{2}-\d{2}$/.test(String(dia || '')) ? dia : montarData(anoMes, dia);
        };
    }

    function hoje() {
        return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
    }

    document.addEventListener('DOMContentLoaded', () => {
        const modal = document.getElementById('modal-consolidar-conta');
        const oculto = document.getElementById('consolidar-valor-previsto');
        const valor = document.getElementById('consolidar-valor-recebido');
        const data = document.getElementById('consolidar-data-recebimento');
        const justificativa = document.getElementById('consolidar-justificativa');
        if (!modal || !oculto || !valor || !data || !justificativa) return;
        valor.addEventListener('input', () => { oculto.value = valor.value; });
        new MutationObserver(() => {
            if (modal.getAttribute('aria-hidden') !== 'false') return;
            const falta = Number(oculto.value) || 0;  // o Flask grava o numero do que falta
            valor.value = falta.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            oculto.value = valor.value;
            data.value = hoje();
            justificativa.value = '';
        }).observe(modal, { attributes: true, attributeFilter: ['aria-hidden'] });
    });
}());
