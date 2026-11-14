// FIN-MVP-MOBILE-04 — formulario "Nova receita" / "Editar" das Receitas mobile (homologado em 14/11/2026): o formulario da
// fonte do desktop ("Nova Fonte de Receita" / "Editar Fonte de Receita"), com os mesmos campos gravados, pelas rotas do
// servico comum (js/receitas-servico.js: POST /api/receitas/itens -> criar_receita; PUT -> editar_fonte_receita).
// A fonte nova nasce com a sua previsao na competencia aberta (recorrente: 12 meses a partir dela); nada e recebido aqui
// (o recebimento e a acao Receber das Receitas, com conta e movimento).
// FIN-MVP-MOBILE-06: extraido de js/receitas-mobile.js, sem mudar o comportamento, para servir as Receitas mobile e o
// Registrar Lancamento (opcao Receita) com um so formulario. Sem innerHTML (CSP).

import { el } from './comum.js';
import { formatarCompetencia } from './despesas-grupos.js';
import { botao, campo, entrada, limparAoEditar, mensagem, mostrarMensagem, seletor, texto } from './mobile-ui.js';
import { TIPOS_DA_FONTE } from './receitas-lista.js';

export const OPCOES_DIA = [['', 'Selecione o dia'], ...[...Array(31).keys()].map((i) => [i + 1, String(i + 1)])];
export const opcoesDaConta = (contas) => [['', 'Selecione...'], ...contas.map((c) => [c.id, `${c.nome} (${c.instituicao || 'Instituição'})`])];

// Valor digitado ("1.234,56" ou "1234.56") como o parseMoeda do desktop.
export function lerValor(textoValor) {
    const limpo = String(textoValor || '').replace(/[^\d,.-]/g, '').trim();
    if (!limpo) return 0;
    const normalizado = limpo.includes(',') ? limpo.replace(/\./g, '').replace(',', '.') : limpo;
    return Number.parseFloat(normalizado) || 0;
}
export const valorParaCampo = (valor) => Number(valor || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function caixaDeMarcar(rotulo, marcado) {
    const caixa = el('label', 'mob-opcao');
    const input = entrada('checkbox');
    input.checked = Boolean(marcado);
    caixa.append(input, el('span', null, rotulo));
    return { caixa, input };
}

// opcoes: api (fila com o servico de Receitas), mes (competencia aberta), contas (ativas do perfil), fonte (edicao; null na
// nova), aoCancelar() e aoSalvo(resposta) (a tela decide: fechar o painel, a confirmacao ou a previa da atualizacao).
export function formularioFonte({ api, mes, contas, fonte = null, aoCancelar, aoSalvo }) {
    const nova = !fonte;
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const nome = entrada('text', fonte ? fonte.nome : '', { maxlength: '100', placeholder: 'Ex: Salário, Gratificação' });
    const tipo = seletor([['', 'Selecione...'], ...TIPOS_DA_FONTE], fonte ? fonte.tipo : '');
    const descricao = el('textarea');
    descricao.maxLength = 200;
    descricao.rows = 2;
    descricao.value = (fonte && fonte.descricao) || '';
    const valor = entrada('text', fonte && fonte.valor_base_mensal ? valorParaCampo(fonte.valor_base_mensal) : '',
        { inputmode: 'decimal', autocomplete: 'off', placeholder: '0,00' });
    const recorrente = caixaDeMarcar('Receita recorrente (mensal)', fonte ? fonte.recorrente : true);
    const dia = seletor(OPCOES_DIA, (fonte && fonte.dia_previsto_pagamento) || '');
    const conta = seletor(opcoesDaConta(contas), (fonte && fonte.conta_bancaria_id) || '');
    const ativa = caixaDeMarcar('Fonte ativa', fonte ? fonte.ativo : true);
    const campoDia = campo('Dia previsto do recebimento', dia);
    const ajustarDia = () => { dia.disabled = !recorrente.input.checked; };
    recorrente.input.addEventListener('change', ajustarDia);
    ajustarDia();
    const m = mensagem();
    form.append(campo('Nome', nome), campo('Tipo', tipo), campo('Descrição', descricao), campo('Valor base mensal', valor),
        recorrente.caixa, campoDia, campo('Conta bancária', conta));
    if (!nova) form.append(ativa.caixa);
    form.append(texto(nova
        ? `Competência ${formatarCompetencia(mes)}: a receita nasce prevista neste mês; recorrente, nos 12 meses a partir dele.`
        : 'As previsões já gravadas não mudam ao salvar; havendo previsões pendentes com outro valor, você poderá atualizá-las.', 'discreto'), m);
    limparAoEditar(form, m);
    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', aoCancelar);
    const salvar = botao('Salvar', 'primario');
    salvar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, salvar);
    form.append(acoes);
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (salvar.disabled) return;
        // O mesmo corpo do desktop (salvarFonte).
        const corpo = {
            nome: nome.value.trim(), tipo: tipo.value, descricao: descricao.value.trim() || '',
            valor_base_mensal: lerValor(valor.value),
            dia_previsto_pagamento: recorrente.input.checked ? (parseInt(dia.value || '0', 10) || null) : null,
            conta_bancaria_id: conta.value ? parseInt(conta.value, 10) : null,
            recorrente: recorrente.input.checked, ativo: nova ? true : ativa.input.checked,
        };
        if (!corpo.nome || !corpo.tipo) { mostrarMensagem(m, 'Informe nome e tipo da fonte.', 'erro'); return; }
        salvar.disabled = true;
        mostrarMensagem(m, 'Salvando...');
        const r = await api(nova ? 'POST' : 'PUT', nova ? '/api/receitas/itens' : `/api/receitas/itens/${fonte.id}`, corpo);
        if (!r.success) {
            mostrarMensagem(m, r.error || 'Erro ao salvar fonte.', 'erro');
            salvar.disabled = false;
            return;
        }
        await aoSalvo(r, corpo);
    });
    return form;
}
