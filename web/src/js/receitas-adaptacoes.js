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

// FIN-RECEITAS-SALDO-01 — atualizar as previsoes ja gravadas pelo valor-base da fonte. Salvar a fonte continua como o
// Flask (so cria as previsoes que faltam); se ainda houver previsoes pendentes com outro valor, a tela mostra a previa
// (competencia inicial, o que muda e o que fica, com o motivo) e so atualiza com a confirmacao explicita. O banco confere
// a versao da fonte e a quantidade da previa e preserva recebidas, parciais e alteradas manualmente.
(function () {
    const moeda = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    const mesAno = (iso) => `${String(iso).slice(5, 7)}/${String(iso).slice(0, 4)}`;
    const atual = { id: null, previa: null };
    const MOTIVOS = {
        'Recebida (ha recebimento nesta competencia)': 'recebida (há recebimento nesta competência)',
        'Parcialmente recebida': 'parcialmente recebida',
        'Valor alterado manualmente': 'valor alterado manualmente',
        'Data prevista definida manualmente': 'data prevista definida manualmente',
        'Zerada ou removida manualmente': 'zerada ou removida manualmente',
        'Criada ou anotada manualmente': 'criada ou anotada manualmente',
    };

    function el(tag, props = {}, filhos = []) {
        const e = Object.assign(document.createElement(tag), props);
        e.append(...filhos);
        return e;
    }

    function modal() {
        let m = document.getElementById('modal-atualizar-previsoes');
        if (m) return m;
        const fechar = el('button', { type: 'button', textContent: '×' });
        fechar.setAttribute('aria-label', 'Fechar');
        const partir = el('input', { type: 'month', id: 'atualizar-previsoes-partir', required: true });
        const manter = el('button', { type: 'button', className: 'receitas-secondary-btn', id: 'atualizar-previsoes-manter',
            textContent: 'Manter as previsões' });
        const confirmar = el('button', { type: 'button', className: 'receitas-primary-btn', id: 'atualizar-previsoes-confirmar' });
        const caixa = el('div', { className: 'receitas-modal-box receitas-atualizar-box' }, [
            el('div', { className: 'receitas-modal-header' }, [
                el('div', {}, [el('h2', { id: 'atualizar-previsoes-titulo', textContent: 'Atualizar previsões pelo valor-base' }),
                    el('p', { id: 'atualizar-previsoes-subtitulo' })]),
                fechar]),
            el('div', { className: 'receitas-atualizar-corpo' }, [
                el('label', { className: 'receitas-field' }, [el('span', { textContent: 'A partir da competência' }), partir]),
                el('p', { id: 'atualizar-previsoes-resumo', className: 'receitas-atualizar-resumo' }),
                el('div', { id: 'atualizar-previsoes-lista' }),
                el('div', { id: 'atualizar-previsoes-preservadas', className: 'receitas-atualizar-preservadas' })]),
            el('div', { className: 'receitas-modal-footer' }, [manter, confirmar])]);
        caixa.setAttribute('role', 'dialog');
        caixa.setAttribute('aria-modal', 'true');
        caixa.setAttribute('aria-labelledby', 'atualizar-previsoes-titulo');
        m = el('div', { id: 'modal-atualizar-previsoes', className: 'receitas-modal' }, [caixa]);
        m.setAttribute('aria-hidden', 'true');
        document.body.appendChild(m);
        fechar.addEventListener('click', () => window.fecharModal('modal-atualizar-previsoes'));
        manter.addEventListener('click', () => window.fecharModal('modal-atualizar-previsoes'));
        partir.addEventListener('change', () => { if (partir.value) carregar(partir.value); });
        confirmar.addEventListener('click', confirmarAtualizacao);
        return m;
    }

    function desenhar(p) {
        const m = modal();
        atual.previa = p;
        m.querySelector('#atualizar-previsoes-subtitulo').textContent = `${p.nome}: valor-base ${moeda(p.valor_base)}.`;
        m.querySelector('#atualizar-previsoes-partir').value = String(p.a_partir).slice(0, 7);
        m.querySelector('#atualizar-previsoes-resumo').textContent = p.quantidade
            ? `${p.quantidade} previsão(ões) pendente(s) passam para ${moeda(p.valor_base)} (diferença ${moeda(p.diferenca_total)}). `
              + 'Nenhum recebimento ou saldo muda.'
            : 'Nenhuma previsão pendente a atualizar a partir desta competência.';
        const tabela = el('table', { className: 'receitas-atualizar-tabela' });
        tabela.createTHead().insertRow().append(...['Competência', 'Atual', 'Novo'].map((t) => el('th', { textContent: t })));
        const corpo = tabela.createTBody();
        p.afetadas.forEach((x) => corpo.insertRow().append(el('td', { textContent: mesAno(x.competencia) }),
            el('td', { textContent: moeda(x.valor_atual) }), el('td', { textContent: moeda(x.valor_novo) })));
        m.querySelector('#atualizar-previsoes-lista').replaceChildren(...(p.quantidade ? [tabela] : []));
        const ficam = p.preservadas.filter((x) => x.motivo !== 'Ja no valor-base');
        m.querySelector('#atualizar-previsoes-preservadas').replaceChildren(...(ficam.length ? [
            el('strong', { textContent: 'Ficam como estão:' }),
            el('ul', {}, ficam.map((x) => el('li', { textContent: `${mesAno(x.competencia)} — ${moeda(x.valor)}: ${MOTIVOS[x.motivo] || x.motivo}` })))] : []));
        const botao = m.querySelector('#atualizar-previsoes-confirmar');
        botao.textContent = `Atualizar ${p.quantidade} previsão(ões)`;
        botao.disabled = !p.quantidade || !p.pode_atualizar;
    }

    async function carregar(aPartir) {
        const consulta = aPartir ? `?a_partir=${aPartir}` : '';
        const r = await (await fetch(`/api/receitas/itens/${atual.id}/previa-atualizacao${consulta}`)).json();
        if (!r.success) {
            window.mostrarToast(r.error || 'Não foi possível conferir as previsões.', 'error');
            return null;
        }
        desenhar(r.data);
        return r.data;
    }

    async function confirmarAtualizacao() {
        const p = atual.previa;
        if (!p || !p.quantidade) return;
        document.getElementById('atualizar-previsoes-confirmar').disabled = true;
        const r = await (await fetch(`/api/receitas/itens/${atual.id}/atualizar-previsoes`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ a_partir: String(p.a_partir).slice(0, 7), esperadas: p.quantidade, versao: p.versao }),
        })).json();
        if (!r.success) {
            window.mostrarToast(r.error || 'Não foi possível atualizar as previsões.', 'error');
            await carregar(String(p.a_partir).slice(0, 7));  // previa de novo: algo mudou
            return;
        }
        window.fecharModal('modal-atualizar-previsoes');
        window.mostrarToast(r.message, 'success');
        await window.atualizarDados();
    }

    // Depois de salvar uma fonte existente: oferece a atualizacao se houver previsoes pendentes com outro valor.
    window.CFReceitasAtualizarPrevisoes = async function (id) {
        atual.id = id;
        const p = await carregar(null);
        if (p && p.pode_atualizar && p.quantidade > 0) window.abrirModal('modal-atualizar-previsoes');
    };
    const salvarFonteOriginal = window.salvarFonte;
    if (typeof salvarFonteOriginal === 'function') {
        window.salvarFonte = async function salvarFonte(event) {
            const id = Number(document.getElementById('fonte-id')?.value) || null;
            await salvarFonteOriginal(event);
            const salvo = document.getElementById('modal-fonte')?.getAttribute('aria-hidden') === 'true';
            if (id && salvo && !document.body.classList.contains('cf-somente-leitura')) {
                await window.CFReceitasAtualizarPrevisoes(id);
            }
        };
    }
}());
