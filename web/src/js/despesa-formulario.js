// FIN-MVP-MOBILE-06 — confirmacoes dos formularios mobile de cadastro (Abastecimento e Transferencia).
// FIN-MVP-CADASTRO-UNIFICADO-01: o formulario "Nova Despesa" que ficava aqui (conta a pagar, compra no cartao e recorrencia)
// foi substituido pelo modal unico (js/cadastro-despesa.js); restam as pecas de confirmacao usadas pelos outros formularios.
// Sem innerHTML (CSP): tudo por createElement.

import { el } from './comum.js';
import { botao, mostrarAviso, texto } from './mobile-ui.js';
import { mesAno } from './mobile-formulario.js';

function acoesDaConfirmacao(container, opcoes, principal) {
    const outra = botao(opcoes.rotuloNovo || 'Nova despesa');
    outra.id = 'mob-outra';
    outra.addEventListener('click', () => {
        mostrarAviso('');
        if (opcoes.aoRecomecar) opcoes.aoRecomecar();
    });
    const inicio = el('a', 'mob-botao', 'Início');
    inicio.href = `inicio.html?mes=${opcoes.mes}`;
    const acoes = el('div', 'mob-acoes');
    acoes.append(principal, outra, inicio);
    return acoes;
}

// Compra no cartao: a fatura (ou as faturas, no parcelamento) em que entrou e o caminho para o cartao.
export function desenharConfirmacaoCompra(container, opcoes, corpo, nomeCartao, faturas, nota = 'A compra entra na fatura do cartão (sem conta a pagar separada).') {
    const meses = [...faturas].map((f) => String(f).slice(0, 7)).sort();
    const primeira = meses[0];
    const caixa = el('div', 'mob-confirmacao');
    caixa.id = 'mob-confirmacao';
    const ver = el('a', 'mob-botao primario', 'Ver no cartão');
    ver.id = 'mob-ver-cartao';
    ver.href = `cartoes-mobile.html?mes=${primeira}&cartao=${corpo.cartao_id}`;
    const onde = corpo.total_parcelas > 1
        ? `Compra lançada em ${corpo.total_parcelas} parcelas no cartão ${nomeCartao}: faturas ${mesAno(`${primeira}-01`)} a ${mesAno(`${meses[meses.length - 1]}-01`)}.`
        : `Compra lançada na fatura ${mesAno(`${primeira}-01`)} do cartão ${nomeCartao}.`;
    caixa.append(el('p', 'mob-confirmacao-titulo', `“${corpo.descricao}” lançada no cartão`), texto(onde),
        texto(nota, 'discreto'), acoesDaConfirmacao(container, opcoes, ver));
    container.replaceChildren(caixa);
    if (opcoes.aoConcluir) opcoes.aoConcluir();
}

export { acoesDaConfirmacao };
