// FIN-MOVIMENTACOES-1 — formularios de liquidacao (pagar despesa, receber receita) e de estorno, compartilhados
// pelas telas de Contas e Receitas. Nenhuma regra financeira aqui: valor devido/que falta, conta, saldo, ajuste e
// operacao vigente sao conferidos no banco (financeiro.pagar_despesa, receber_receita e estornos). A tela so
// preenche o que o banco informou e envia a escolha do usuario, com uma chave por formulario (reenvio sem duplicar).

import { botao, campo, centavos, dataCurta, el, entrada, formatarValor, linhaDetalhe, normalizarValor, reais, seletor } from './comum.js';

const AJUSTES = { JUROS: 'Juros ou multa', DESCONTO: 'Desconto', AJUSTE: 'Ajuste de quitação integral' };
export const textoAjuste = (tipo) => AJUSTES[tipo] || tipo;

function hojeBrasilia() {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
}

function painelFormulario(painel, titulo, rotuloConfirmar, perigo) {
    painel.replaceChildren();
    painel.hidden = false;
    const form = el('form', 'despesa-form');
    form.noValidate = true;
    form.append(el('h2', 'geracao-titulo', titulo));
    const erro = el('p', 'login-error');
    erro.setAttribute('role', 'alert');
    erro.hidden = true;
    const confirmar = botao(rotuloConfirmar, perigo ? 'botao-perigo' : 'botao-principal');
    confirmar.type = 'submit';
    const cancelar = botao('Cancelar');
    const botoes = el('div', 'geracao-botoes');
    botoes.append(confirmar, cancelar);
    const fechar = () => { painel.replaceChildren(); painel.hidden = true; };
    cancelar.addEventListener('click', fechar);
    const falhar = (texto) => {
        erro.textContent = texto;
        erro.hidden = false;
        confirmar.disabled = false;
        cancelar.disabled = false;
    };
    const travar = () => { confirmar.disabled = true; cancelar.disabled = true; };
    painel.scrollIntoView({ block: 'nearest' });
    return { form, erro, botoes, fechar, falhar, travar };
}

// Pagamento (modo 'pagar': diferenca exige classificacao + justificativa) ou recebimento (modo 'receber': valor
// menor e parcial; acima do que falta exige justificativa).
// opcoes: { painel, modo, titulo, resumo: [[rotulo, texto]], referencia (valor do banco), rotuloReferencia,
//           rotuloValor, rotuloData, contas, contaPadrao, enviar(corpo, chave), sucesso(data), mensagemDeErro, prefixo }
export function abrirLiquidacao(o) {
    const f = painelFormulario(o.painel, o.titulo, o.modo === 'pagar' ? 'Confirmar pagamento' : 'Confirmar recebimento');
    let referencia = centavos(o.referencia);
    const resumo = el('dl', 'conta-detalhe');
    for (const [rotulo, texto] of o.resumo) linhaDetalhe(resumo, rotulo, texto);
    const refTexto = el('dd', null, reais(referencia));
    resumo.append(el('dt', null, o.rotuloReferencia), refTexto);
    const valor = entrada('text', formatarValor(referencia / 100));
    valor.inputMode = 'decimal';
    const data = entrada('date', hojeBrasilia());
    const conta = seletor(o.contas.map((c) => [c.id, `${c.nome} · saldo ${reais(centavos(c.saldo))}`]),
        o.contas.some((c) => c.id === o.contaPadrao) ? o.contaPadrao : (o.contas[0] || {}).id);
    const tipo = seletor([['', 'Selecione']], '');
    const justificativa = el('textarea');
    justificativa.rows = 2;
    justificativa.maxLength = 500;
    const dica = el('p', 'geracao-dica');
    const ajuste = el('div', 'pagamento-ajuste');
    ajuste.append(dica);
    if (o.modo === 'pagar') ajuste.append(campo('Diferença', tipo, `${o.prefixo}-tipo`));
    ajuste.append(campo('Justificativa', justificativa, `${o.prefixo}-justificativa`));
    const parcial = el('p', 'geracao-dica', 'Valor menor que o que falta: recebimento parcial (a previsão fica Parcial).');
    const diferenca = () => {
        const v = normalizarValor(valor.value);
        return v === null ? 0 : centavos(v) - referencia;
    };
    const atualizar = () => {
        const dif = diferenca();
        if (o.modo === 'pagar') {
            ajuste.hidden = dif === 0;
            dica.textContent = 'O valor pago é diferente do devido: classifique e justifique. A despesa fica quitada.';
            const opcoes = dif > 0 ? ['JUROS', 'AJUSTE'] : ['DESCONTO', 'AJUSTE'];
            const atual = opcoes.includes(tipo.value) ? tipo.value : '';
            tipo.replaceChildren(new Option('Selecione', ''), ...opcoes.map((t) => new Option(AJUSTES[t], t)));
            tipo.value = atual;
        } else {
            ajuste.hidden = dif <= 0;
            dica.textContent = 'Valor acima do que falta receber: justifique.';
            parcial.hidden = !(dif < 0);
        }
    };
    valor.addEventListener('input', atualizar);
    atualizar();
    f.form.append(resumo, campo(o.rotuloValor, valor, `${o.prefixo}-valor`), campo(o.rotuloData, data, `${o.prefixo}-data`),
        campo('Conta bancária', conta, `${o.prefixo}-conta`), ajuste);
    if (o.modo === 'receber') f.form.append(parcial);
    f.form.append(f.erro, f.botoes);
    o.painel.append(f.form);
    if (!o.contas.length) f.falhar('Nenhuma conta bancária ativa neste perfil.');

    const chave = crypto.randomUUID();
    f.form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        f.erro.hidden = true;
        const v = normalizarValor(valor.value);
        if (!v || Number(v) <= 0 || !data.value || !conta.value) {
            f.falhar('Informe o valor, a data e a conta bancária.');
            return;
        }
        const dif = diferenca();
        const corpo = { conta_bancaria_id: Number(conta.value), valor: v, data: data.value, referencia: (referencia / 100).toFixed(2) };
        if ((o.modo === 'pagar' && dif !== 0) || (o.modo === 'receber' && dif > 0)) {
            if ((o.modo === 'pagar' && !tipo.value) || !justificativa.value.trim()) {
                f.falhar(o.modo === 'pagar' ? 'Classifique a diferença e escreva a justificativa.' : 'Escreva a justificativa.');
                return;
            }
            corpo.justificativa = justificativa.value.trim();
            if (o.modo === 'pagar') corpo.tipo_ajuste = tipo.value;
        }
        f.travar();
        const { data: r, error } = await o.enviar(corpo, chave);
        if (error) {
            if (error.hint === 'VALOR_MUDOU' && o.recarregarReferencia) {  // mudou no banco: mostra o valor novo
                const novo = await o.recarregarReferencia();
                if (novo !== null && novo !== undefined) {
                    referencia = centavos(novo);
                    refTexto.textContent = reais(referencia);
                    atualizar();
                }
            }
            f.falhar(o.mensagemDeErro(error));
            return;
        }
        f.fechar();
        await o.sucesso(r);
    });
}

// Estorno de uma operacao identificada (o banco recusa se ja foi estornada ou nao e a vigente).
// opcoes: { painel, titulo, resumo: [[rotulo, texto]], enviar(dados, chave), sucesso(data), mensagemDeErro, prefixo }
export function abrirEstorno(o) {
    const f = painelFormulario(o.painel, o.titulo, 'Confirmar estorno', true);
    const resumo = el('dl', 'conta-detalhe');
    for (const [rotulo, texto] of o.resumo) linhaDetalhe(resumo, rotulo, texto);
    const motivo = el('textarea');
    motivo.rows = 2;
    motivo.maxLength = 500;
    const data = entrada('date', hojeBrasilia());
    f.form.append(resumo, campo('Motivo do estorno', motivo, `${o.prefixo}-motivo`),
        campo('Data do estorno', data, `${o.prefixo}-data-estorno`), f.erro, f.botoes);
    o.painel.append(f.form);
    const chave = crypto.randomUUID();
    f.form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        f.erro.hidden = true;
        if (!motivo.value.trim() || !data.value) {
            f.falhar('Informe o motivo e a data do estorno.');
            return;
        }
        f.travar();
        const { data: r, error } = await o.enviar({ motivo: motivo.value.trim(), data_estorno: data.value }, chave);
        if (error) {
            f.falhar(o.mensagemDeErro(error));
            return;
        }
        f.fechar();
        await o.sucesso(r);
    });
}

export const linhaOperacao = (data, valor, conta) => `${dataCurta(data)} · ${reais(centavos(valor))} · ${conta || 'conta'}`;
