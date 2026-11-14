// FIN-MVP-MOBILE-03 — regras de leitura da fatura do cartao para a tela mobile, sem DOM e sem regra nova. Os grupos sao os da
// tela Cartoes do desktop ("Fatura por Categoria do Cartao"): vem prontos do banco (fatura_por_categoria), na mesma ordem
// (Categorias do Cartao com limite, categorias sem limite, Compras parceladas, Despesas fixas, Sem Categoria do Cartao e
// Creditos e ajustes), com o executado de cada um (gasto_atual). Cada compra entra no grupo pelo mesmo criterio do filtro
// "Ver lancamentos" do desktop (lancamentos_fatura_por_categoria): a natureza que o banco informa e, nas compras de
// categoria, a Categoria do Cartao gravada na compra.

import { centavos } from './comum.js';

// Natureza da compra (banco) -> chave do grupo; as compras de categoria usam a Categoria do Cartao.
const CHAVE_POR_NATUREZA = { CREDITO: 'creditos', FIXA: 'despesas_fixas', PARCELADA: 'compras_parceladas', OUTROS: 'sem_categoria' };

// Os nomes fixos que o banco grava sem acento ganham a grafia correta; os demais (Categorias do Cartao) ficam como estao.
const ROTULOS_FIXOS = { sem_categoria: 'Sem Categoria do Cartão', creditos: 'Créditos e ajustes' };

export function chaveDoLancamento(l) {
    return CHAVE_POR_NATUREZA[l.natureza] || String(l.categoria_cartao_id);
}

// Mesma chave do filtro "Ver lancamentos" do desktop (filtroCategoriaFatura): sem_categoria ou o categoria_cartao_id do
// grupo, que nos grupos de parceladas, fixas e creditos ja e o nome do filtro.
export function chaveDoGrupo(g) {
    if (g.sem_categoria) return 'sem_categoria';
    return String(g.categoria_cartao_id);
}

export function rotuloDoGrupo(g) {
    return ROTULOS_FIXOS[g.tipo_grupo] || g.categoria_cartao_nome || 'Categoria do Cartão';
}

// Executado da compra: o que o banco informa (a previsao nao cobrada vale 0; o credito e negativo).
export function executadoDaCompra(l) {
    return l.valor_executado === null || l.valor_executado === undefined ? Number(l.valor || 0) : Number(l.valor_executado);
}

export const totalDosItens = (itens) => itens.reduce((s, l) => s + centavos(executadoDaCompra(l)), 0);

// Filtros do painel: cartao do contrato (id do cartao vinculado; '0' = sem cartao identificado, como o filtro cartao-0 do
// desktop) e situacao (a revisar: sem Categoria do Cartao ou categoria sem limite, como o destaque da linha no desktop;
// prevista: despesa fixa aguardando cobranca).
export function filtrarLancamentos(lista, filtros = {}) {
    return lista.filter((l) => {
        if (filtros.vinculado) {
            const id = l.cartao_vinculado ? String(l.cartao_vinculado.id) : '0';
            if (id !== String(filtros.vinculado)) return false;
        }
        if (filtros.situacao === 'revisar' && (l.natureza === 'CREDITO' || l.status_classificacao === 'classificado')) return false;
        if (filtros.situacao === 'prevista' && l.situacao_ocorrencia !== 'PREVISTA') return false;
        return true;
    });
}

export const filtrosAtivos = (filtros = {}) => Boolean(filtros.vinculado || filtros.situacao);

// Grupos da fatura na ordem do desktop. Sem filtro, todos os grupos que o desktop mostra (inclusive a categoria com limite
// ainda sem compra) com o executado do banco; com filtro, so os grupos com compras visiveis e o total delas.
export function montarGruposFatura(resumo, lancamentos, filtros = {}) {
    const visiveis = filtrarLancamentos(lancamentos || [], filtros);
    const filtrado = filtrosAtivos(filtros);
    const grupos = [];
    const usadas = new Set();
    for (const g of (resumo && resumo.categorias) || []) {
        const chave = chaveDoGrupo(g);
        usadas.add(chave);
        const itens = visiveis.filter((l) => chaveDoLancamento(l) === chave);
        if (filtrado && !itens.length) continue;
        grupos.push({
            chave,
            rotulo: rotuloDoGrupo(g),
            natureza: g.natureza,
            itens,
            quantidade: filtrado ? itens.length : Number(g.quantidade_lancamentos || 0),
            total_centavos: filtrado ? totalDosItens(itens) : centavos(g.gasto_atual),
            limite_centavos: g.vinculada_ao_cartao && g.limite_mensal !== null && g.limite_mensal !== undefined ? centavos(g.limite_mensal) : null,
            disponivel_centavos: g.vinculada_ao_cartao && g.disponivel !== null && g.disponivel !== undefined ? centavos(g.disponivel) : null,
        });
    }
    // Nenhuma compra fica de fora: o que nao casou com um grupo do resumo (nao deveria acontecer) aparece num grupo proprio.
    const sobra = visiveis.filter((l) => !usadas.has(chaveDoLancamento(l)));
    if (sobra.length) {
        grupos.push({ chave: 'outros', rotulo: 'Outros lançamentos', natureza: null, itens: sobra, quantidade: sobra.length,
            total_centavos: totalDosItens(sobra), limite_centavos: null, disponivel_centavos: null });
    }
    return grupos;
}

// Cartoes do contrato que aparecem na fatura (como a tabela "por cartao" do desktop, so quando ha cartao identificado).
export function cartoesDaFatura(resumo) {
    const linhas = (resumo && resumo.por_cartao) || [];
    if (!linhas.some((l) => l.cartao_vinculado_id)) return [];
    return linhas.map((l) => ({ id: String(l.cartao_vinculado_id || 0), final: l.final || null, tipo: l.tipo || null }));
}

const TIPOS_CARTAO = { FISICO: 'Físico', VIRTUAL: 'Virtual', ADICIONAL: 'Adicional' };
export const rotuloCartaoDoContrato = (c) => (c.id === '0' ? 'Sem cartão identificado'
    : `•••• ${c.final}${c.tipo && TIPOS_CARTAO[c.tipo] ? ` · ${TIPOS_CARTAO[c.tipo]}` : ''}`);

// Situacao da cobranca da compra, com os textos do desktop (situacaoPrevisaoLancamento) para as previsoes.
export function situacaoDaCobranca(l) {
    if (l.natureza === 'CREDITO') return 'Crédito da fatura';
    if (l.situacao_ocorrencia === 'PREVISTA') return 'Prevista · aguardando cobrança';
    if (l.situacao_ocorrencia === 'NAO_COBRADA') return 'Prevista · não cobrada nesta fatura';
    if (l.situacao_ocorrencia === 'CONFIRMADA' || l.situacao_ocorrencia === 'PAGA') return 'Cobrada';
    return l.origem && l.origem !== 'manual' && l.origem !== 'recorrencia' ? 'Importada' : 'Lançada';
}

// Linha discreta abaixo da descricao: data, parcela ou previsao, e o cartao do contrato.
export function legendaDaCompra(l) {
    const partes = [];
    if (l.data) partes.push(`${l.data.slice(8, 10)}/${l.data.slice(5, 7)}`);
    if (l.natureza === 'CREDITO') partes.push('crédito');
    else if (Number(l.parcelas_total || 1) > 1) partes.push(`${l.parcela_atual || 1}/${l.parcelas_total}`);
    else if (l.situacao_ocorrencia === 'PREVISTA') partes.push('prevista');
    else if (l.situacao_ocorrencia === 'NAO_COBRADA') partes.push('não cobrada');
    else if (l.natureza !== 'FIXA') partes.push('à vista');
    if (l.cartao_vinculado && l.cartao_vinculado.final) partes.push(`•••• ${l.cartao_vinculado.final}`);
    return partes.join(' · ');
}

// Situacao da fatura (cabecalho): paga, fechada, vencida ou aberta, pela linha da fatura (Despesas) e pelo resumo.
export function situacaoDaFatura(fatura, resumo, hoje) {
    if (!fatura) return 'Sem fatura';
    if (fatura.pago) return `Paga${fatura.data_pagamento ? ` em ${fatura.data_pagamento.slice(8, 10)}/${fatura.data_pagamento.slice(5, 7)}` : ''}`;
    if (fatura.data_vencimento && hoje && fatura.data_vencimento < hoje) return 'Vencida';
    if (resumo && resumo.situacao_fatura === 'FECHADA') return 'Fechada';
    return 'Aberta';
}
