// FIN-MVP-MOBILE-07 — leitura dos movimentos do extrato (extrato_conta_bancaria) para as Contas mobile. Puro (sem DOM nem
// Supabase), testado em tests/unit/contas-movimentos.test.mjs. Nenhum saldo e calculado aqui: o saldo da conta e o do banco
// (contas_bancarias_tela) e o saldo apos cada movimento vem do extrato. Aqui so se decide como mostrar cada movimento:
// a natureza (pelos vinculos que o banco grava), o sinal (CREDITO entra, DEBITO sai) e o filtro por tipo.

// Natureza pelos vinculos do movimento (movimento_flask): transferencia (par de debito e credito, transferencia_id),
// estorno (movimento_original_id), ajuste de saldo (AJUSTE, o unico editavel no desktop), pagamento de fatura (fatura_id),
// pagamento de despesa (conta_id), recebimento (receita_realizada_id), parcela de financiamento; os demais, pelo tipo.
export function naturezaDoMovimento(m) {
    const origem = String(m.origem || '').toUpperCase();
    const credito = m.tipo === 'CREDITO';
    if (m.transferencia_id || origem === 'TRANSFERENCIA') {
        return { chave: 'transferencia', rotulo: credito ? 'Transferência recebida' : 'Transferência enviada' };
    }
    if (m.movimento_original_id || origem.startsWith('ESTORNO')) return { chave: 'estorno', rotulo: 'Estorno' };
    if (origem === 'AJUSTE' || m.ajustavel) return { chave: 'ajuste', rotulo: 'Ajuste de saldo' };
    if (m.fatura_id || origem === 'FATURA') return { chave: 'fatura', rotulo: 'Pagamento de fatura' };
    if (m.conta_id || origem === 'DESPESA') return { chave: 'despesa', rotulo: 'Pagamento de despesa' };
    if (m.receita_realizada_id || origem === 'RECEITA') return { chave: 'receita', rotulo: 'Recebimento' };
    if (m.financiamento_parcela_id || origem === 'FINANCIAMENTO') return { chave: 'financiamento', rotulo: 'Parcela de financiamento' };
    return { chave: 'outro', rotulo: credito ? 'Entrada' : 'Saída' };
}

// Sinal pela natureza financeira do movimento (como o extrato do desktop: debito com "-", credito com "+").
export const ehEntrada = (m) => m.tipo === 'CREDITO';
export const sinalDoMovimento = (m) => (ehEntrada(m) ? '+' : '−');

export const TIPOS_DO_FILTRO = [
    ['', 'Todos'], ['entradas', 'Entradas'], ['saidas', 'Saídas'], ['transferencia', 'Transferências'], ['estorno', 'Estornos'],
    ['despesa', 'Pagamentos de despesa'], ['receita', 'Recebimentos'], ['fatura', 'Pagamentos de fatura'], ['ajuste', 'Ajustes de saldo'],
];

// Filtro por tipo sobre o extrato do periodo (a consulta ao banco e sempre a do desktop: conta, inicio, fim e limite).
export function filtrarMovimentos(movimentos, tipo) {
    if (!tipo) return movimentos;
    if (tipo === 'entradas') return movimentos.filter(ehEntrada);
    if (tipo === 'saidas') return movimentos.filter((m) => !ehEntrada(m));
    return movimentos.filter((m) => naturezaDoMovimento(m).chave === tipo);
}

// Periodo do mes 'AAAA-MM': do dia 1 ao ultimo dia (datas civis, sem fuso).
export function periodoDoMes(mes) {
    const [ano, m] = mes.split('-').map(Number);
    const ultimo = new Date(Date.UTC(ano, m, 0)).getUTCDate();
    return { inicio: `${mes}-01`, fim: `${mes}-${String(ultimo).padStart(2, '0')}` };
}

// Identificacao da conta no seletor: o nome do desktop; so quando outra conta tem o mesmo nome, o tipo e a instituicao para
// diferenciar (nunca agencia nem numero). Inativa, marcada.
export function rotuloDaConta(conta, contas = []) {
    const mesmoNome = contas.filter((c) => String(c.nome).trim().toLowerCase() === String(conta.nome).trim().toLowerCase()).length > 1;
    const extra = mesmoNome ? [conta.tipo, conta.instituicao].filter(Boolean).join(' · ') : '';
    return `${conta.nome}${extra ? ` (${extra})` : ''}${conta.status === 'INATIVO' ? ' · inativa' : ''}`;
}

export const LIMITE_EXTRATO = 200;  // o mesmo da tela Contas Bancarias do desktop
