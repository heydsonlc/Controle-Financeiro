// FIN-MVP-MOB-01 — regras de leitura da lista de Despesas do desktop, em funcoes puras para a Lista de Despesas mobile.
// A tela do desktop usa o arquivo do Flask (frontend/static/js/despesas.js -> js/original/despesas.js), que nao muda;
// as funcoes abaixo reproduzem as dele (mesmo nome, mesma regra): grupos e ordem (renderizarDespesas/grupoLeitura),
// agrupador semanal (agruparDespesasSemanais, calcularTotaisAgrupamento), valor (obterValorDespesa), forma de pagamento
// (obterFormaPagamentoDespesa), filtros (aplicarFiltros, filtrarBusca), totais (atualizarResumo) e textos
// (formatarCompetencia, formatarTipoRecorrencia). O teste unitario roda o arquivo original numa VM com os mesmos dados e
// confere grupos, ordem, valores e filtros. Nenhum grupo novo: so os do desktop.
// Somas em centavos (o desktop soma em reais e formata com 2 casas: o resultado mostrado e o mesmo).

import { centavos } from './comum.js';

export const ORDEM_GRUPOS = ['FINANCIAMENTOS', 'FATURAS_CARTAO', 'DESPESAS_RECORRENTES', 'DESPESAS_AVULSAS', 'INVESTIMENTOS'];

export const ROTULOS_GRUPO = {
    FINANCIAMENTOS: 'FINANCIAMENTOS',
    FATURAS_CARTAO: 'FATURAS DE CARTÃO DE CRÉDITO',
    DESPESAS_RECORRENTES: 'DESPESAS RECORRENTES',
    DESPESAS_AVULSAS: 'DESPESAS AVULSAS',
    INVESTIMENTOS: 'INVESTIMENTOS',
};

export function grupoLeitura(d) {
    if (d?.tipo === 'agrupador_semanal') return 'DESPESAS_RECORRENTES';
    if (d && d.financiamento_parcela_id != null) return 'FINANCIAMENTOS';
    if (d && d.is_fatura_cartao === true) return 'FATURAS_CARTAO';
    if (d && d.recorrente === true && String(d.tipo || '').trim().toLowerCase() === 'simples') return 'DESPESAS_RECORRENTES';
    if (String(d?.tipo || '').trim().toLowerCase() === 'consorcio') return 'INVESTIMENTOS';
    return 'DESPESAS_AVULSAS';
}

// Recorrencias semanais do mesmo item na competencia viram uma linha (agrupamento so visual, como no desktop).
export function agruparDespesasSemanais(despesas) {
    const agrupamentos = {};
    const despesasNaoAgrupadas = [];
    despesas.forEach((despesa) => {
        const ehSemanal = despesa.tipo_recorrencia && despesa.tipo_recorrencia.startsWith('semanal');
        if (despesa.recorrente === true && ehSemanal) {
            const nomeBase = despesa.nome.replace(/\s*-\s*\d{2}\/\d{2}$/, '').trim();
            const chave = `${nomeBase}_${despesa.mes_competencia}`;
            if (!agrupamentos[chave]) {
                agrupamentos[chave] = {
                    tipo: 'agrupador_semanal',
                    nome: nomeBase,
                    mes_competencia: despesa.mes_competencia,
                    categoria_id: despesa.categoria_id,
                    categoria: despesa.categoria,
                    ocorrencias: [],
                    _agrupado: true,
                };
            }
            agrupamentos[chave].ocorrencias.push(despesa);
        } else {
            despesasNaoAgrupadas.push(despesa);
        }
    });
    return [...Object.values(agrupamentos), ...despesasNaoAgrupadas];
}

// Valor mostrado na linha do agrupador: ocorrencias nao canceladas.
export function calcularTotaisAgrupamento(ocorrencias) {
    const naoCanceladas = ocorrencias.filter((o) => !o.cancelada);
    return {
        total_ocorrencias: naoCanceladas.length,
        pagas: naoCanceladas.filter((o) => o.pago).length,
        valor_centavos: naoCanceladas.reduce((soma, o) => soma + centavos(parseFloat(o.valor) || 0), 0),
    };
}

// Valor soberano: fatura de cartao usa valor_fatura; as demais, valor.
export function obterValorDespesa(despesa) {
    if (!despesa) return 0;
    if (despesa.tipo === 'cartao' || despesa.is_fatura_cartao === true) return parseFloat(despesa.valor_fatura || 0);
    return parseFloat(despesa.valor || 0);
}

export const estaPaga = (d) => (d.status ? d.status.toLowerCase() === 'pago' : Boolean(d.pago));

function normalizarFormaPagamento(valor, formas) {
    if (formas?.normalizarFormaPagamento) return formas.normalizarFormaPagamento(valor);
    return String(valor || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
        .replace(/[^\w\s]/g, ' ').replace(/\s+/g, ' ').trim();
}

// formas: window.FormasPagamentoUI (js/original/formas_pagamento.js, o mesmo componente do desktop).
export function obterFormaPagamentoDespesa(despesa, formas = globalThis.FormasPagamentoUI) {
    if (!despesa) return 'nao_informado';
    if (despesa.is_fatura_cartao === true || despesa.tipo === 'cartao') return 'cartao';
    const normalizada = normalizarFormaPagamento(despesa.meio_pagamento || despesa.forma_pagamento || despesa.pagamento, formas);
    if (!normalizada) return 'nao_informado';
    if (normalizada === 'debito' || normalizada.includes('debito automatico') || normalizada.includes('debito em conta')) {
        return 'debito_automatico';
    }
    const resolvida = formas?.resolverFormaPagamento ? formas.resolverFormaPagamento(normalizada) : null;
    if (resolvida?.key && resolvida.key !== 'default') return resolvida.key;
    if (normalizada.includes('transferencia') || normalizada === 'ted' || normalizada === 'doc') return 'transferencia';
    return 'outros';
}

// Opcoes do filtro "Forma de pagamento" do desktop (contas.html), na mesma ordem.
export const FORMAS_FILTRO = [
    ['', 'Todas'], ['pix', 'Pix'], ['dinheiro', 'Dinheiro'], ['cartao', 'Cartão'], ['boleto', 'Boleto'],
    ['transferencia', 'Transferência'], ['debito_automatico', 'Débito automático'], ['outros', 'Outros / Não informado'],
];

// Filtros do desktop: forma de pagamento, status e "vencimento ate" (aplicarFiltros) e a busca por nome, descricao ou
// categoria (filtrarBusca). No desktop a busca substitui os demais filtros; aqui valem juntos.
export function filtrarDespesas(despesas, filtros = {}, formas = globalThis.FormasPagamentoUI) {
    let lista = [...despesas];
    const { forma, situacao, vencimentoAte, busca } = filtros;
    if (forma) {
        lista = lista.filter((d) => {
            const f = obterFormaPagamentoDespesa(d, formas);
            return forma === 'outros' ? (f === 'outros' || f === 'nao_informado') : f === forma;
        });
    }
    if (situacao === 'pago') lista = lista.filter((d) => d.pago);
    else if (situacao === 'pendente') lista = lista.filter((d) => !d.pago);
    if (vencimentoAte) lista = lista.filter((d) => d.data_vencimento && d.data_vencimento <= vencimentoAte);
    const texto = String(busca || '').toLowerCase().trim();
    if (texto) {
        lista = lista.filter((d) => (d.nome || '').toLowerCase().includes(texto)
            || (d.descricao || '').toLowerCase().includes(texto)
            || (d.categoria && d.categoria.nome ? d.categoria.nome.toLowerCase() : '').includes(texto));
    }
    return lista;
}

export const filtrosAtivos = (filtros = {}) => Boolean(filtros.forma || filtros.situacao || filtros.vencimentoAte
    || String(filtros.busca || '').trim());

// Grupos na ordem do desktop, so os que tem linhas. Cada item e uma despesa ou um agrupador semanal; o total do grupo e
// a soma dos valores das suas linhas.
export function montarGrupos(despesas) {
    const grupos = Object.fromEntries(ORDEM_GRUPOS.map((g) => [g, []]));
    agruparDespesasSemanais(despesas).forEach((d) => {
        if (d.tipo === 'agrupador_semanal') {
            const totais = calcularTotaisAgrupamento(d.ocorrencias);
            grupos[grupoLeitura(d)].push({ tipo: 'semanal', agrupador: d, totais, valor_centavos: totais.valor_centavos });
        } else {
            grupos[grupoLeitura(d)].push({ tipo: 'despesa', despesa: d, valor_centavos: centavos(obterValorDespesa(d)) });
        }
    });
    return ORDEM_GRUPOS.filter((g) => grupos[g].length).map((g) => ({
        chave: g,
        rotulo: ROTULOS_GRUPO[g],
        itens: grupos[g],
        total_centavos: grupos[g].reduce((soma, item) => soma + item.valor_centavos, 0),
    }));
}

// Cartoes de resumo do desktop (atualizarResumo): total, pendentes e pagas da lista mostrada.
export function totaisDaLista(despesas) {
    const soma = (lista) => lista.reduce((s, d) => s + centavos(obterValorDespesa(d)), 0);
    return {
        total: soma(despesas),
        pendentes: soma(despesas.filter((d) => !estaPaga(d))),
        pagas: soma(despesas.filter((d) => estaPaga(d))),
    };
}

export function formatarCompetencia(competencia) {
    if (!competencia) return '';
    const [ano, mes] = competencia.split('-');
    const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    return `${meses[parseInt(mes, 10) - 1]}/${ano}`;
}

export function formatarTipoRecorrencia(tipo) {
    if (!tipo) return 'Recorrente';
    const tiposAntigos = { a_cada_2_semanas: 'A cada 2 semanas', mensal: 'Mensal', semanal: 'Semanal', anual: 'Anual' };
    if (tiposAntigos[tipo]) return tiposAntigos[tipo];
    if (tipo.startsWith('semanal_')) {
        const partes = tipo.split('_');
        if (partes.length === 3) {
            const freq = parseInt(partes[1], 10);
            const diaNome = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'][parseInt(partes[2], 10)] || 'dia';
            return freq === 1 ? `Toda ${diaNome.toLowerCase()}` : `A cada ${freq} semanas (${diaNome.toLowerCase()})`;
        }
    }
    return tipo || 'Recorrente';
}
