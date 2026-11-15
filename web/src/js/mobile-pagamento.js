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
    FALHA_GERAL, abrirFolha, botao, campo, detalhes, entrada, fecharFolha, folhaDeErro, limparAoEditar, mensagem, mostrarMensagem,
    seletor, texto,
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
        // FIN-MVP-MOBILE-08: a conta e a data seguem para quem quiser oferecer "Ver em Contas" (as outras telas ignoram).
        await concluir(r.message || 'Despesa paga.', { conta_bancaria_id: payload.conta_bancaria_id, data_pagamento: payload.data_pagamento });
    });
    abrirFolha(`${fatura ? 'Pagar fatura' : 'Pagar'}: ${d.nome}`, form);
}

// ---------------------------------------------------------------------------------------------------------------
// Pagamento em lote das ocorrencias pendentes de uma recorrencia semanal agrupada (P20/P21), como no desktop. Veio de
// js/despesas-mobile.js (FIN-MVP-MOB-01) sem mudanca de texto nem de regra, para a Lista de Despesas e os Pagamentos
// mobile usarem o mesmo painel. O banco paga todas as pendentes da recorrencia na competencia, numa so transacao (tudo
// ou nada), e confere de novo as ocorrencias, os valores e a identidade do lote.
//
// ctx = { api, contasAtivas, concluir, recarregar, pendentesDoAgrupador, comData }: pendentesDoAgrupador(nome, competencia)
// devolve as ocorrencias pendentes de agora (null se o agrupador nao existe mais); recarregar rele a lista ao fechar
// quando ela mudou; comData mostra a data do pagamento (a de hoje, a que o servico usa no lote) no painel.

function nomeDoMeio(meio) {
    const forma = meio && window.FormasPagamentoUI && window.FormasPagamentoUI.resolverFormaPagamento(meio);
    return (forma && forma.nome) || ({ pix: 'Pix', boleto: 'Boleto', debito: 'Débito', debito_automatico: 'Débito automático' }[meio]) || 'Não informado';
}

const idsDe = (ocorrencias) => ocorrencias.map((o) => o.id).sort((a, b) => a - b).join(',');
const CODIGOS_RECARREGAR = ['LOTE_DESATUALIZADO', 'LOTE_IDENTIDADE', 'VALOR_MUDOU', 'DESPESA_PAGA'];

export async function abrirLote(nome, competencia, ctx) {
    const { api, contasAtivas, concluir, recarregar: reler, pendentesDoAgrupador, comData = false } = ctx;
    const encontradas = pendentesDoAgrupador(nome, competencia);
    const pendentes = encontradas || [];
    if (!pendentes.length) {
        folhaDeErro(nome, encontradas ? 'Todas as ocorrências já foram pagas!' : 'Agrupamento não encontrado. Atualize a lista e tente de novo.');
        return;
    }
    const total = pendentes.reduce((s, o) => s + centavos(o.valor), 0);
    const contas = await contasAtivas();
    const vinculadas = [...new Set(pendentes.map((o) => o.conta_bancaria_id).filter(Boolean))];
    const conta = opcoesDeConta(contas, vinculadas.length === 1 ? vinculadas[0] : null);
    const m = mensagem();
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const pares = [
        ['Recorrência', nome], ['Competência', formatarCompetencia(competencia)], ['Forma de pagamento', nomeDoMeio(pendentes[0].meio_pagamento)],
        ['Ocorrências pendentes', String(pendentes.length)], ['Valor total', reais(total)],
    ];
    if (comData) pares.push(['Data do pagamento', dataCurta(hojeBrasilia())]);
    form.append(detalhes(pares), campo('Conta bancária de débito', conta), m);
    const cancelar = botao('Cancelar');
    const confirmar = botao('Confirmar pagamento', 'primario');
    confirmar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, confirmar);
    form.append(acoes);
    let recarregar = false;  // no lote o aviso fica: ele diz se a lista mudou e precisa ser conferida
    const fechar = async () => { fecharFolha(); if (recarregar) await reler(); };
    cancelar.addEventListener('click', fechar);
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (!conta.value) { mostrarMensagem(m, 'Selecione a conta bancária de débito.', 'erro'); return; }
        const aindaPendentes = pendentesDoAgrupador(nome, competencia) || [];
        if (idsDe(aindaPendentes) !== idsDe(pendentes)) {
            recarregar = true;
            confirmar.disabled = true;
            mostrarMensagem(m, 'Nenhuma ocorrência foi paga.\nA lista mudou desde a abertura. Feche e confira a lista atualizada antes de pagar de novo.', 'erro');
            return;
        }
        confirmar.disabled = true;
        mostrarMensagem(m, 'Pagando...');
        const r = await api('POST', '/api/despesas/pagar-lote', {
            conta_bancaria_id: Number(conta.value),
            itens: pendentes.map((o) => ({ conta_id: o.id, valor_devido: Number(o.valor).toFixed(2) })),
            // o que o painel mostrou: o banco recusa se as ocorrencias nao forem desta recorrencia e competencia (P21)
            lote: { descricao: nome, competencia, recorrencias: [...new Set(pendentes.map((o) => o.item_despesa_id))].sort((a, b) => a - b),
                quantidade: pendentes.length, valor_total: (total / 100).toFixed(2) },
        });
        if (!r.success) {
            const deveRecarregar = CODIGOS_RECARREGAR.includes(r.codigo);
            mostrarMensagem(m, `Nenhuma ocorrência foi paga.\n${String(r.error || 'Não foi possível pagar.').replace(/^Nenhuma ocorrência foi paga\.\s*/, '')}`
                + (deveRecarregar ? '\nFeche e confira a lista atualizada antes de pagar de novo.' : ''), 'erro');
            if (deveRecarregar) recarregar = true;
            confirmar.disabled = deveRecarregar;
            return;
        }
        const resultado = r.data;
        await concluir(`Pagamento em lote concluído\n${resultado.pagas} ocorrência(s) paga(s)\nValor total: ${reais(centavos(resultado.valor_total))}\n`
            + `Conta de débito: ${resultado.conta_nome}\nSaldo da conta: ${reais(centavos(resultado.saldo_conta))}`,
        { conta_bancaria_id: resultado.conta_bancaria_id, data_pagamento: resultado.data_pagamento });
    });
    abrirFolha(`Pagar ocorrências: ${nome}`, form);
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
