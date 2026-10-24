// FIN-MOVIMENTACOES-1 — movimentos do mes nas contas bancarias do perfil (so leitura: financeiro.movimentos_do_mes).
// Saldo de cada conta pelos movimentos; cada movimento com data, descricao, tipo, origem, valor, conta e o que o
// originou (despesa, fatura ou receita). Sem conciliacao nem importacao de extrato.

import { supabase } from './cliente.js';
import { centavos, dataCurta, el, reais } from './comum.js';

const ORIGENS = {
    DESPESA: 'Pagamento de despesa', ESTORNO_DESPESA: 'Estorno de despesa', FATURA: 'Pagamento de fatura',
    ESTORNO_FATURA: 'Estorno de fatura', RECEITA: 'Recebimento', ESTORNO_RECEITA: 'Estorno de recebimento',
    TRANSFERENCIA: 'Transferência', AJUSTE: 'Ajuste', MANUAL: 'Manual', FINANCIAMENTO: 'Financiamento',
};

export async function mostrarMovimentos(perfilId, mes) {
    const secao = document.getElementById('secao-movimentos');
    const saldos = document.getElementById('saldos-contas');
    const lista = document.getElementById('lista-movimentos');
    secao.hidden = true;
    saldos.replaceChildren();
    lista.replaceChildren();
    const { data, error } = await supabase.rpc('movimentos_do_mes', { p_perfil_id: perfilId, p_mes: `${mes}-01` });
    if (error || !data || !data.contas.length) return;
    for (const c of data.contas.filter((x) => x.status === 'ATIVO')) {
        const linha = el('p', 'saldo-conta');
        linha.append(el('span', null, c.nome), el('strong', null, reais(centavos(c.saldo))));
        saldos.append(linha);
    }
    if (!data.movimentos.length) lista.append(el('li', 'geracao-dica', 'Nenhum movimento neste mês.'));
    for (const m of data.movimentos) {
        const item = el('li', 'conta movimento');
        item.dataset.movimentoId = String(m.id);
        const principal = el('span', 'conta-principal');
        const origem = ORIGENS[m.origem] || m.origem;
        principal.append(el('span', 'conta-nome', m.referencia || m.descricao),
            el('span', 'conta-vencimento', `${dataCurta(m.data)} · ${origem} · ${m.conta_nome}`));
        const sinal = m.tipo === 'CREDITO' ? '+' : '−';
        const valor = el('span', `conta-valor movimento-${m.tipo.toLowerCase()}`, `${sinal} ${reais(centavos(m.valor))}`);
        const linha = el('div', 'conta-resumo');
        linha.append(principal, valor);
        item.append(linha);
        lista.append(item);
    }
    secao.hidden = false;
}
