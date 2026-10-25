// FIN-FIDELIDADE-CARTOES-1 — o minimo que a tela original de Cartoes (js/original/cartoes.js, sem alteracao) precisa
// para as regras do novo aplicativo. Script classico, carregado depois do original: substitui so o que esta abaixo,
// cada item com o motivo.
(function () {
    'use strict';

    // Estado da tela original (const global do script classico) para o modulo do adaptador (compra nova).
    window.CF_CARTOES = Object.freeze({
        mes: () => estadoCartoes.mesSelecionado,  // eslint-disable-line no-undef
        cartaoSelecionadoId: () => estadoCartoes.cartaoSelecionadoId,  // eslint-disable-line no-undef
    });

    // 1. Numero, validade e CVV nao sao guardados no novo aplicativo (decisao de seguranca do FIN-CARTOES-1): os
    //    campos ficam desativados e vazios, para que nada seja digitado, mantido no formulario ou enviado.
    const SENSIVEIS = ['cartao-numero', 'cartao-data-validade', 'cartao-cvv'];
    function bloquearSensiveis() {
        for (const id of SENSIVEIS) {
            const campo = document.getElementById(id);
            if (!campo) continue;
            campo.value = '';
            campo.disabled = true;
            campo.placeholder = 'Não guardado no novo aplicativo';
            campo.setAttribute('aria-describedby', 'cartao-dados-sensiveis');
        }
    }
    document.addEventListener('DOMContentLoaded', bloquearSensiveis);

    // 2. Inativar o cartao em edicao: a rota DELETE de cartoes do Flask existe, mas a tela nao tinha o botao;
    //    o novo aplicativo ja inativava pela tela de Cartoes (FIN-CARTOES-1). Nunca exclusao fisica.
    const abrirNovoOriginal = window.abrirModalCartao;
    window.abrirModalCartao = function abrirModalCartao() {
        abrirNovoOriginal();
        bloquearSensiveis();
        document.getElementById('btn-inativar-cartao').hidden = true;
    };
    const abrirEdicaoOriginal = window.abrirModalEditarCartao;
    window.abrirModalEditarCartao = function abrirModalEditarCartao() {
        abrirEdicaoOriginal();
        bloquearSensiveis();
        document.getElementById('btn-inativar-cartao').hidden = !document.getElementById('cartao-id').value;
    };
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('btn-inativar-cartao').addEventListener('click', async () => {
            const id = document.getElementById('cartao-id').value;
            const nome = document.getElementById('cartao-nome').value;
            if (!id || !confirm(`Inativar o cartão "${nome}"?\nCompras e faturas continuam registradas; ele deixa de aparecer e de receber compras novas.`)) return;
            try {
                await fetchJson(`${API_CARTOES}/${id}`, { method: 'DELETE' });  // eslint-disable-line no-undef
                fecharModal('modal-cartao');
                await carregarTelaCartoes();  // eslint-disable-line no-undef
                mostrarSucesso('Cartão inativado.');  // eslint-disable-line no-undef
            } catch (erro) {
                mostrarErro(`Erro ao inativar cartão: ${erro.message}`);  // eslint-disable-line no-undef
            }
        });
    });

    // 3. "Cancelar parcelas futuras": a mensagem de confirmacao do Flask esta com acentos corrompidos (defeito de
    //    codificacao no arquivo original). Mesma funcao, com o texto correto.
    window.cancelarParcelasFuturas = async function cancelarParcelasFuturas() {
        const baseId = estadoCartoes.parcelamentoGestao?.base?.id;  // eslint-disable-line no-undef
        if (!baseId) return;
        if (!confirm('Esta ação afetará apenas as parcelas futuras deste parcelamento. As parcelas anteriores não serão alteradas.')) return;
        try {
            const resp = await fetchJson(`${API_CARTOES}/lancamentos/${baseId}/parcelamento/cancelar-futuras`, { method: 'POST' });  // eslint-disable-line no-undef
            estadoCartoes.parcelamentoGestao = resp.data?.parcelamento || estadoCartoes.parcelamentoGestao;  // eslint-disable-line no-undef
            preencherModalGerenciarParcelamento(estadoCartoes.parcelamentoGestao);  // eslint-disable-line no-undef
            if (obterCartaoSelecionado()) {  // eslint-disable-line no-undef
                await carregarFaturaSelecionada();  // eslint-disable-line no-undef
                renderizarDetalheCartao();  // eslint-disable-line no-undef
            }
            mostrarSucesso(`${resp.data?.canceladas || 0} parcela(s) futura(s) cancelada(s).`);  // eslint-disable-line no-undef
        } catch (erro) {
            mostrarErro(`Erro ao cancelar parcelas futuras: ${erro.message}`);  // eslint-disable-line no-undef
        }
    };
}());
