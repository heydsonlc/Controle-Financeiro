// FIN-FIDELIDADE-DESPESAS-1 — o minimo que a tela original de Despesas (js/original/despesas.js, sem alteracao)
// precisa para as regras do novo aplicativo. Script classico, carregado depois do original: substitui so as
// funcoes abaixo, cada uma com o motivo.
(function () {
    'use strict';

    const MES = /^\d{4}-(0[1-9]|1[0-2])$/;

    // 1. Competencia. O Flask devolvia todos os meses e a tela filtrava; o Supabase devolve o mes pedido (contas_do_mes).
    //    Trocar a competencia recarrega o mes. Ao abrir, vale o ?mes= do menu (competencia mantida na navegacao).
    document.addEventListener('DOMContentLoaded', () => {
        const filtro = document.getElementById('filtro-competencia');
        const pedido = new URLSearchParams(window.location.search).get('mes');
        if (MES.test(pedido || '')) {
            filtro.value = `${pedido.slice(5, 7)}/${pedido.slice(0, 4)}`;
            window.carregarDespesas();
        }
        filtro.addEventListener('change', () => {
            if (/^(0[1-9]|1[0-2])\/\d{4}$/.test(filtro.value)) window.carregarDespesas();
        });
        const valorPago = document.getElementById('pagar-valor-pago');
        if (valorPago) valorPago.addEventListener('input', atualizarAjuste);
    });

    // Marca o mes cuja listagem terminou de carregar (a tela pode pedir dois meses seguidos ao abrir).
    const carregarOriginal = window.carregarDespesas;
    window.carregarDespesas = async function carregarDespesas() {
        const competencia = document.getElementById('filtro-competencia').value;  // a do pedido, nao a do fim
        await carregarOriginal();
        document.getElementById('despesas-lista').dataset.competenciaCarregada = competencia;
    };

    // 3. "A partir de documento" depende de Documentos Fiscais (OCR), ainda em migracao: o seletor original abre e
    //    informa, em vez de mostrar uma lista vazia.
    window.abrirSeletorDocumentoDespesa = function abrirSeletorDocumentoDespesa() {
        const modal = document.getElementById('doc-desp-seletor-modal');
        if (!modal) return;
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
        const aviso = document.createElement('p');
        aviso.className = 'doc-atalho-vazio';
        aviso.textContent = 'Documentos fiscais: em migração para o novo aplicativo. Até lá, o lançamento a partir de '
            + 'documento continua no sistema atual.';
        document.getElementById('doc-desp-lista').replaceChildren(aviso);
    };

    // 2. Pagamento (FIN-MOVIMENTACOES-1): o pagamento da despesa e integral. "Pagar outro Valor" continua, mas a
    //    diferenca para o devido exige classificacao (juros, desconto ou ajuste de quitacao) e justificativa.
    const AJUSTES = { JUROS: 'Juros ou multa', DESCONTO: 'Desconto', AJUSTE: 'Ajuste de quitação integral' };

    function diferencaDoDevido() {
        const outro = document.querySelector('input[name="tipo-pagamento"]:checked')?.value === 'parcial';
        const previsto = Math.round(Number(document.getElementById('pagar-valor-previsto').value || 0) * 100);
        const pago = Math.round(Number(document.getElementById('pagar-valor-pago').value || 0) * 100);
        return outro && pago > 0 ? pago - previsto : 0;
    }

    function atualizarAjuste() {
        const caixa = document.getElementById('pagar-ajuste');
        const tipo = document.getElementById('pagar-ajuste-tipo');
        const diferenca = diferencaDoDevido();
        caixa.hidden = diferenca === 0;
        const opcoes = diferenca > 0 ? ['JUROS', 'AJUSTE'] : ['DESCONTO', 'AJUSTE'];
        const atual = tipo.value;
        tipo.replaceChildren(new Option('Selecione...', ''), ...opcoes.map((t) => new Option(AJUSTES[t], t)));
        if (opcoes.includes(atual)) tipo.value = atual;
    }

    const alternarOriginal = window.alternarCampoValor;
    window.alternarCampoValor = function alternarCampoValor() {
        alternarOriginal();
        atualizarAjuste();
    };

    const fecharPagarOriginal = window.fecharModalPagar;
    window.fecharModalPagar = function fecharModalPagar() {
        fecharPagarOriginal();
        document.getElementById('pagar-ajuste').hidden = true;
        document.getElementById('pagar-ajuste-justificativa').value = '';
    };

    // Copia de confirmarPagamento do original; acrescimos marcados com "Ajuste".
    window.confirmarPagamento = async function confirmarPagamento(event) {
        event.preventDefault();
        const id = document.getElementById('pagar-despesa-id').value;
        const tipoPagamento = document.querySelector('input[name="tipo-pagamento"]:checked').value;
        const dataPagamento = document.getElementById('pagar-data').value;
        const contaBancariaId = document.getElementById('pagar-conta-bancaria')?.value;
        let valorPago;
        if (tipoPagamento === 'total') {
            valorPago = null;
        } else {
            valorPago = parseFloat(document.getElementById('pagar-valor-pago').value);
            if (!valorPago || valorPago <= 0) {
                alert('Por favor, informe um valor válido');
                return;
            }
        }
        const payload = { data_pagamento: dataPagamento };
        if (!contaBancariaId) {
            alert('Selecione a conta bancária para executar o pagamento.');
            return;
        }
        payload.conta_bancaria_id = parseInt(contaBancariaId, 10);
        if (valorPago !== null) payload.valor_pago = valorPago;
        // Ajuste: diferenca classificada e justificada.
        if (diferencaDoDevido() !== 0) {
            const tipoAjuste = document.getElementById('pagar-ajuste-tipo').value;
            const justificativa = document.getElementById('pagar-ajuste-justificativa').value.trim();
            if (!tipoAjuste || !justificativa) {
                alert('Classifique a diferença e escreva a justificativa.');
                return;
            }
            payload.tipo_ajuste = tipoAjuste;
            payload.justificativa = justificativa;
        }
        const botao = document.querySelector('#form-pagar button[type="submit"]');
        if (botao) botao.disabled = true;  // Ajuste: evita duplo envio (o banco tambem protege pela chave)
        try {
            const response = await fetch(`${API_URL}/${id}/pagar`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!data.success) {
                alert('Erro ao marcar como pago: ' + data.error);
                return;
            }
            alert(data.message || 'Despesa marcada como paga!');  // Ajuste: a mensagem informa a conta e o saldo
            window.fecharModalPagar();
            window.carregarDespesas();
        } catch (error) {
            console.error('Erro ao marcar despesa como paga:', error);
            alert('Erro ao marcar despesa como paga. Por favor, tente novamente.');
        } finally {
            if (botao) botao.disabled = false;
        }
    };
}());
