// FIN-MVP-MOBILE-03 — pagamento e estorno no painel mobile, vindos de js/despesas-mobile.js (FIN-MVP-MOB-01) sem mudanca,
// para a Lista de Despesas e a fatura em Cartoes usarem o mesmo formulario: os campos do desktop (data, conta, valor total
// ou outro valor com a diferenca classificada e justificada) e as mesmas rotas do servico de Despesas.
//
// ctx = { api, contasAtivas, concluir, base }: pedidos da pagina, contas ativas, conclusao (fecha, avisa e rele) e a base
// das rotas de pagar e estornar ('/api/despesas', padrao, na lista; '/api/faturas' na fatura do cartao).

import { hojeBrasilia } from './adaptador-comum.js';
import { centavos, dataCurta, el, reais } from './comum.js';
import { formatarCompetencia } from './despesas-grupos.js';
import {
    FALHA_GERAL, abrirFolha, botao, campo, entrada, fecharFolha, limparAoEditar, mensagem, mostrarMensagem, seletor, texto,
} from './mobile-ui.js';

// Pagamento (individual): os campos do desktop (data, conta, valor total ou outro valor com a diferenca classificada e
// justificada). O banco paga pela mesma funcao, com a mesma chave de idempotencia.

const AJUSTES = { JUROS: 'Juros ou multa', DESCONTO: 'Desconto', AJUSTE: 'Ajuste de quitação integral' };

export function opcoesDeConta(contas, sugerida) {
    const opcoes = [['', 'Selecione...'], ...contas.map((c) => [c.id, c.instituicao ? `${c.nome} (${c.instituicao})` : c.nome])];
    return seletor(opcoes, sugerida && contas.some((c) => c.id === sugerida) ? sugerida : '');
}

export async function abrirPagamento(d, ctx) {
    const { api, contasAtivas, concluir, base = '/api/despesas' } = ctx;
    const fatura = d.is_fatura_cartao === true;
    let devido = fatura ? Number(d.valor_executado || 0) : Number(d.valor || 0);
    let nota = '';
    if (fatura) {
        // FIN-CARTOES-EXECUTADO-01: o executado consolidado e o valor sugerido; o banco pode cobrar outro valor.
        const r = await api('GET', `/api/despesas/${d.id}/composicao-fatura`);
        if (r.success) {
            devido = Number(r.data.valor_executado || 0);
            nota = (r.data.previsto_sem_cobranca > 0
                ? `Inclui ${reais(centavos(r.data.previsto_sem_cobranca))} de despesas fixas previstas, ainda sem cobrança importada. ` : '')
                + 'Se o banco cobrou outro valor, escolha “Pagar outro valor”, informe o valor efetivamente cobrado e justifique a '
                + 'diferença. Nenhuma recorrência é marcada como não cobrada; a conciliação posterior continua possível.';
        }
    }
    const contas = await contasAtivas();
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const data = entrada('date', hojeBrasilia(), { required: '' });
    const conta = opcoesDeConta(contas, d.conta_bancaria_id);
    // Uma conta ja vinculada a despesa fixa a conta do pagamento (como no desktop).
    if (d.conta_bancaria_id && conta.value) conta.disabled = true;
    const opcoes = el('fieldset', 'mob-opcoes');
    const radio = (valor, rotulo, marcado) => {
        const caixa = el('label', 'mob-opcao');
        const r = entrada('radio', valor, { name: 'mob-tipo-pagamento' });
        r.checked = marcado;
        caixa.append(r, el('span', null, rotulo));
        return { caixa, r };
    };
    const total = radio('total', `${fatura ? 'Executado consolidado (valor sugerido)' : 'Valor total'}: ${reais(centavos(devido))}`, true);
    const outro = radio('parcial', 'Pagar outro valor', false);
    opcoes.append(total.caixa, outro.caixa);
    const valorPago = entrada('number', devido.toFixed(2), { step: '0.01', min: '0.01', inputmode: 'decimal' });
    const campoValor = campo('Valor pago', valorPago);
    campoValor.hidden = true;
    const tipoAjuste = seletor([['', 'Selecione...']]);
    const justificativa = el('textarea');
    const campoTipo = campo('Classificação da diferença', tipoAjuste);
    const campoJust = campo('Justificativa', justificativa);
    campoTipo.hidden = true;
    campoJust.hidden = true;
    const m = mensagem();

    const diferenca = () => {
        const pago = centavos(valorPago.value);
        return outro.r.checked && pago > 0 ? pago - centavos(devido) : 0;
    };
    const atualizar = () => {
        campoValor.hidden = !outro.r.checked;
        const dif = diferenca();
        campoTipo.hidden = dif === 0;
        campoJust.hidden = dif === 0;
        const tipos = dif > 0 ? ['JUROS', 'AJUSTE'] : ['DESCONTO', 'AJUSTE'];
        const atual = tipoAjuste.value;
        const rotulo = (t) => (fatura && t === 'AJUSTE' ? 'Valor cobrado pelo banco diferente do consolidado' : AJUSTES[t]);
        tipoAjuste.replaceChildren(new Option('Selecione...', ''), ...tipos.map((t) => new Option(rotulo(t), t)));
        if (tipos.includes(atual)) tipoAjuste.value = atual;
    };
    [total.r, outro.r].forEach((r) => r.addEventListener('change', atualizar));
    valorPago.addEventListener('input', atualizar);

    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', fecharFolha);
    const confirmar = botao('Confirmar pagamento', 'primario');
    confirmar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, confirmar);
    form.append(texto(`Vencimento ${dataCurta(d.data_vencimento) || '—'} · ${formatarCompetencia(d.mes_competencia)}`, 'discreto'));
    if (nota) form.append(texto(nota, 'discreto'));
    form.append(campo('Data do pagamento', data), campo('Conta bancária', conta), opcoes, campoValor, campoTipo, campoJust, m, acoes);
    limparAoEditar(form, m);

    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        const payload = { data_pagamento: data.value };
        if (outro.r.checked) {
            const v = parseFloat(valorPago.value);
            if (!v || v <= 0) { mostrarMensagem(m, 'Por favor, informe um valor válido.', 'erro'); return; }
            payload.valor_pago = v;
        }
        if (!data.value) { mostrarMensagem(m, 'Informe a data do pagamento.', 'erro'); return; }
        if (!conta.value) { mostrarMensagem(m, 'Selecione a conta bancária para executar o pagamento.', 'erro'); return; }
        payload.conta_bancaria_id = parseInt(conta.value, 10);
        if (diferenca() !== 0) {
            if (!tipoAjuste.value || !justificativa.value.trim()) {
                mostrarMensagem(m, 'Classifique a diferença e escreva a justificativa.', 'erro');
                return;
            }
            payload.tipo_ajuste = tipoAjuste.value;
            payload.justificativa = justificativa.value.trim();
        }
        confirmar.disabled = true;  // evita duplo envio (o banco tambem protege pela chave)
        mostrarMensagem(m, 'Pagando...');
        const r = await api('POST', `${base}/${d.id}/pagar`, payload);
        if (!r.success) {
            mostrarMensagem(m, r.error || FALHA_GERAL, 'erro');
            confirmar.disabled = false;
            return;
        }
        await concluir(r.message || 'Despesa paga.');
    });
    abrirFolha(`${fatura ? 'Pagar fatura' : 'Pagar'}: ${d.nome}`, form);
}

// ---------------------------------------------------------------------------------------------------------------
// Estorno do pagamento (despesa ou fatura): movimento compensatorio; o pagamento original nao e apagado.

export function abrirEstorno(d, ctx) {
    const { api, concluir, base = '/api/despesas' } = ctx;
    const fatura = d.is_fatura_cartao === true;
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const data = entrada('date', hojeBrasilia(), { required: '' });
    const motivo = el('textarea');
    motivo.required = true;
    const m = mensagem();
    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', fecharFolha);
    const confirmar = botao('Confirmar estorno', 'perigo');
    confirmar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, confirmar);
    form.append(
        texto(fatura
            ? 'O estorno não apaga o pagamento original. O sistema criará um crédito compensatório e reabrirá a fatura.'
            : 'O estorno não apaga o pagamento original. O sistema criará um movimento compensatório e reabrirá a despesa como pendente.'),
        campo('Data do estorno', data), campo('Motivo', motivo), m, acoes,
    );
    limparAoEditar(form, m);
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (!data.value) { mostrarMensagem(m, 'Informe a data do estorno.', 'erro'); return; }
        if (!motivo.value.trim()) { mostrarMensagem(m, 'Informe o motivo do estorno.', 'erro'); return; }
        confirmar.disabled = true;
        mostrarMensagem(m, 'Estornando...');
        const r = await api('POST', `${base}/${d.id}/estornar-pagamento`, { data_estorno: data.value, motivo: motivo.value.trim() });
        if (!r.success) {
            mostrarMensagem(m, `Erro ao estornar: ${r.error || FALHA_GERAL}`, 'erro');
            confirmar.disabled = false;
            return;
        }
        await concluir(r.message || 'Pagamento estornado com sucesso.');
    });
    abrirFolha(fatura ? `Estornar pagamento da fatura: ${d.nome}` : `Estornar pagamento: ${d.nome}`, form);
}
