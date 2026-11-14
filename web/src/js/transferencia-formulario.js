// FIN-MVP-MOBILE-06 — Transferencia entre contas do Registrar Lancamento: o modal "Transferencia" da tela Contas Bancarias do
// desktop (js/original/contas_bancarias.js), com os mesmos campos (origem, destino, valor, data e descricao) e a mesma
// gravacao (js/contas-servico.js -> transferir_entre_contas: movimentos pareados, saldo pelos movimentos, auditoria e chave
// contra reenvio). Contas ativas do perfil; destino diferente da origem (regra do banco, conferida tambem na tela).
// Nenhum saldo e alterado diretamente; sem innerHTML (CSP).

import { el } from './comum.js';
import { hojeBrasilia } from './adaptador-comum.js';
import { responderContas } from './contas-servico.js';
import { acoesDaConfirmacao } from './despesa-formulario.js';
import { botao, entrada, mensagem, mostrarMensagem, seletor, texto } from './mobile-ui.js';
import { campoComErro, erroDoServico, moeda, mostrarErros, par } from './mobile-formulario.js';

const dataBr = (iso) => String(iso).slice(0, 10).split('-').reverse().join('/');
const rotuloConta = (c) => `${c.nome} · ${moeda(c.saldo_atual)}`;

// opcoes: api (fila da tela), mes (competencia da pagina principal), contas (ativas do perfil, com o saldo), rotuloNovo e
// aoRecomecar/aoConcluir (como os outros formularios).
export function montarFormularioTransferencia(container, opcoes) {
    const { api, mes, contas } = opcoes;
    if (contas.length < 2) {
        const voltar = el('a', 'mob-botao', 'Cancelar');
        voltar.id = 'mob-cancelar';
        voltar.href = `inicio.html?mes=${mes}`;
        const acoes = el('div', 'mob-acoes');
        acoes.append(voltar);
        // A mesma orientacao da tela Contas Bancarias do desktop.
        container.replaceChildren(texto('Cadastre outra conta ativa para transferir.'), acoes);
        return null;
    }
    let enviando = false;
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const origem = seletor([['', 'Selecione...'], ...contas.map((c) => [c.id, rotuloConta(c)])], '');
    const destino = seletor([['', 'Selecione...']], '');
    const valor = entrada('number', '', { step: '0.01', min: '0', inputmode: 'decimal', placeholder: '0,00' });
    const data = entrada('date', hojeBrasilia());
    const descricao = entrada('text', 'Transferência entre contas', { maxlength: '200', autocomplete: 'off' });
    const cOrigem = campoComErro('Conta de origem', origem, { obrigatorio: true });
    const cDestino = campoComErro('Conta de destino', destino, { obrigatorio: true });
    const cValor = campoComErro('Valor', valor, { obrigatorio: true });
    const cData = campoComErro('Data', data, { obrigatorio: true });
    const cDescricao = campoComErro('Descrição', descricao);

    // Destino: as demais contas ativas (como a tela Contas Bancarias), mantendo a escolha quando ainda valer.
    const atualizarDestinos = () => {
        const atual = destino.value;
        destino.replaceChildren(new Option('Selecione...', ''),
            ...contas.filter((c) => String(c.id) !== origem.value).map((c) => new Option(rotuloConta(c), String(c.id))));
        if ([...destino.options].some((o) => o.value === atual)) destino.value = atual;
    };
    origem.addEventListener('change', atualizarDestinos);
    atualizarDestinos();

    const m = mensagem();
    const cancelar = el('a', 'mob-botao', 'Cancelar');
    cancelar.id = 'mob-cancelar';
    cancelar.href = `inicio.html?mes=${mes}`;
    const salvar = botao('Transferir', 'primario');
    salvar.type = 'submit';
    salvar.id = 'mob-salvar';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, salvar);
    const parValor = par(cValor, cData);
    parValor.classList.add('empilha');  // < 360 px: a data inteira, sem corte
    form.append(cOrigem, cDestino, parValor, cDescricao,
        el('span', 'mob-ajuda', 'A transferência registra a saída na origem e a entrada no destino; os saldos vêm dos movimentos.'), m, acoes);

    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (enviando) return;
        for (const c of form.querySelectorAll('.mob-campo')) if (c.erro) c.erro('');
        mostrarMensagem(m, '');
        const erros = [];
        if (!origem.value) erros.push([cOrigem, 'Selecione a conta de origem.']);
        if (!destino.value) erros.push([cDestino, 'Selecione a conta de destino.']);
        else if (destino.value === origem.value) erros.push([cDestino, 'Conta de origem e destino devem ser diferentes.']);
        if (!(parseFloat(valor.value) > 0)) erros.push([cValor, 'Informe um valor maior que zero.']);
        if (!data.value) erros.push([cData, 'Informe a data.']);
        if (mostrarErros(erros)) return;
        enviando = true;
        salvar.disabled = true;
        mostrarMensagem(m, 'Salvando...');
        // O mesmo corpo da tela Contas Bancarias (salvarTransferencia).
        const corpo = { conta_origem_id: Number(origem.value), conta_destino_id: Number(destino.value), valor: parseFloat(valor.value),
            data_movimento: data.value, descricao: descricao.value.trim() || 'Transferência' };
        const r = await api('POST', '/api/contas/transferir', corpo, responderContas);
        if (!r || !r.success) {
            enviando = false;
            salvar.disabled = false;
            erroDoServico(m, (r && r.error) || 'Falha ao transferir. Nada foi gravado.', [[/valor/i, cValor], [/diferentes|destino/i, cDestino],
                [/origem|conta/i, cOrigem], [/data/i, cData]]);
            return;
        }
        // Saldos relidos depois da gravacao (os do banco, pelos movimentos).
        const lidas = await api('GET', '/api/contas?status=ATIVO', null, responderContas);
        const atuais = lidas && lidas.success ? lidas.data || [] : [];
        const nomeDe = (id) => (contas.find((c) => c.id === id) || {}).nome || '';
        const saldoDe = (id) => { const c = atuais.find((x) => x.id === id); return c ? moeda(c.saldo_atual) : '—'; };
        const caixa = el('div', 'mob-confirmacao');
        caixa.id = 'mob-confirmacao';
        const principal = el('a', 'mob-botao primario', 'Início');
        principal.href = `inicio.html?mes=${mes}`;
        const acoesFim = acoesDaConfirmacao(container, opcoes, principal);
        acoesFim.lastChild.remove();  // "Inicio" ja e o principal
        caixa.append(el('p', 'mob-confirmacao-titulo', 'Transferência realizada'),
            texto(`${moeda(corpo.valor)} de ${nomeDe(corpo.conta_origem_id)} para ${nomeDe(corpo.conta_destino_id)} em ${dataBr(corpo.data_movimento)}.`),
            texto(`Saldos: ${nomeDe(corpo.conta_origem_id)} ${saldoDe(corpo.conta_origem_id)} · ${nomeDe(corpo.conta_destino_id)} ${saldoDe(corpo.conta_destino_id)}.`, 'discreto'),
            acoesFim);
        container.replaceChildren(caixa);
        if (opcoes.aoConcluir) opcoes.aoConcluir();
    });
    container.replaceChildren(form);
    origem.focus();
    return form;
}
