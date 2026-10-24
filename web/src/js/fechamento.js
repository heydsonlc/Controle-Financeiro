// FIN-CARTOES-FECHAMENTO-1 — textos e decisoes de tela da fatura sugerida pelo fechamento do cartao.
// Puro (sem DOM nem Supabase): a competencia e calculada no banco (financeiro.sugerir_competencia e
// previa_compra); aqui so se decide o que mostrar e o que enviar. Testado em tests/unit/fechamento.test.mjs.

const curta = (iso) => (iso ? `${iso.slice(5, 7)}/${iso.slice(0, 4)}` : '');
const diaMes = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : '');
const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const moeda = (valor) => brl.format(Number(valor || 0));

export const REGRAS_DIA_FECHAMENTO = [
    ['PROXIMO', 'Vai para a próxima fatura'],
    ['ATUAL', 'Entra na fatura que está fechando'],
];

export function textoRegra(regra) {
    return regra === 'ATUAL' ? 'Entra na fatura que está fechando' : 'Vai para a próxima fatura';
}

// Mes do campo quando nao ha sugestao e o usuario nao escolheu: ciclo ambiguo exige escolha (vazio);
// cartao nao confirmado ou sem dias volta ao mes padrao da tela (com aviso), nunca ao que outro cartao sugeriu.
export function mesSemSugestao(situacao, padrao) {
    return situacao === 'CICLO_AMBIGUO' ? '' : padrao;
}

// Texto da dica abaixo do mes da fatura. `escolhido` e o mes do campo (AAAA-MM); `manual` diz se foi o usuario.
export function textoSugestao(sugestao, { manual = false, escolhido = '' } = {}) {
    if (!sugestao) return { texto: '', alerta: false };
    switch (sugestao.situacao) {
    case 'NAO_CONFIRMADO':
        return { texto: 'Fechamento deste cartão ainda não confirmado: confira o mês da fatura.', alerta: true };
    case 'CICLO_AMBIGUO':
        return { texto: 'Os dias de fechamento e vencimento não definem a fatura desta data: escolha o mês.', alerta: true };
    case 'SEM_CONFIGURACAO':
        return { texto: 'Cartão sem dias de fechamento e vencimento: confira o mês da fatura.', alerta: true };
    case 'INDISPONIVEL':  // a consulta falhou: nada e sugerido
        return { texto: 'Não foi possível sugerir a fatura: confira o mês.', alerta: true };
    case 'SUGERIDA':
        break;
    default:
        return { texto: '', alerta: false };
    }
    const partes = [`Sugerida pelo fechamento: fatura ${curta(sugestao.competencia)} `
        + `(fecha ${diaMes(sugestao.fechamento)}, vence ${diaMes(sugestao.vencimento)}).`];
    const diferente = manual && escolhido && escolhido !== sugestao.competencia.slice(0, 7);
    if (diferente) partes.push(`Mês escolhido: ${curta(`${escolhido}-01`)}.`);
    else if (sugestao.fatura_situacao === 'FECHADA') partes.push('Essa fatura está consolidada: a inclusão pede confirmação.');
    else if (sugestao.fatura_situacao === 'PAGA') partes.push('Essa fatura já está paga: a compra vai para a próxima em aberto.');
    return { texto: partes.join(' '), alerta: !diferente && sugestao.fatura_situacao === 'FECHADA' };
}

export function textoConsolidada(c) {
    return `Incluir na fatura consolidada ${curta(c.competencia)}: total ${moeda(c.total_consolidado)} `
        + `passa a ${moeda(c.total_novo)} (inclusão de ${moeda(c.valor_incluido)}).`;
}

// Confirmacao da operacao especifica: cada fatura com o total que o usuario viu (o banco confere sob trava).
export function confirmacoes(consolidadas) {
    return (consolidadas || []).map((c) => ({ fatura_id: c.fatura_id, total_consolidado: String(c.total_consolidado) }));
}

// Erro do banco que pede confirmacao (HINT CONSOLIDADA, DETAIL em JSON); null para qualquer outro erro.
export function consolidadaDoErro(error) {
    if (!error || error.hint !== 'CONSOLIDADA') return null;
    try {
        const detalhe = JSON.parse(error.details || '');
        return detalhe && detalhe.fatura_id ? detalhe : null;
    } catch {
        return null;
    }
}
