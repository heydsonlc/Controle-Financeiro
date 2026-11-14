// FIN-MVP-MOBILE-04 — regras de leitura da tela de Receitas do desktop, sem DOM, para as Receitas mobile mostrarem a
// mesma lista, na mesma ordem e com os mesmos totais:
// - montarReceitasMes: a montagem de js/original/receitas.js (frontend/static/js/receitas.js, que nao muda) com as
//   adaptacoes do novo aplicativo (js/receitas-adaptacoes.js): sem a linha "virtual" da fonte sem previsao, data
//   prevista gravada na previsao e previsao removida (zerada e sem recebimento) fora da lista;
// - separarReceitas: "Receitas do mes" (com os filtros Tipo e Busca) e "Receitas atrasadas" (competencias anteriores do
//   mesmo ano ainda nao realizadas), como aplicarFiltrosLocais;
// - totaisDaLista: Previsto e Realizado dos cartoes do desktop (soma das linhas filtradas) e Pendente, o que falta das
//   linhas previstas ou parciais (a conta do painel "Recebimentos pendentes" do desktop).
// A equivalencia com o arquivo original e conferida no teste unitario (receitas-lista.test.mjs, que roda o original).

export const TIPOS_RECEITA = {
    SALARIO_FIXO: 'Salário Fixo',
    GRATIFICACAO: 'Gratificação',
    RENDA_EXTRA: 'Renda Extra',
    ALUGUEL: 'Aluguel',
    RENDIMENTO_FINANCEIRO: 'Rendimento',
    OUTROS: 'Outros',
    PONTUAL: 'Pontual',
};
// Opcoes do formulario da fonte no desktop (o rotulo de RENDIMENTO_FINANCEIRO no formulario e o completo).
export const TIPOS_DA_FONTE = [['SALARIO_FIXO', 'Salário Fixo'], ['GRATIFICACAO', 'Gratificação'], ['RENDA_EXTRA', 'Renda Extra'],
    ['ALUGUEL', 'Aluguel'], ['RENDIMENTO_FINANCEIRO', 'Rendimento Financeiro'], ['OUTROS', 'Outros']];
// Filtro "Tipo" do desktop
export const TIPOS_DO_FILTRO = [['', 'Todos os tipos'], ...TIPOS_DA_FONTE, ['PONTUAL', 'Pontual']];

export const formatarTipo = (tipo) => TIPOS_RECEITA[tipo] || TIPOS_RECEITA.OUTROS;
const normalizarDataMes = (data) => (data ? `${String(data).slice(0, 7)}-01` : '');
const chaveReceita = (itemId, competencia) => `${itemId || 'sem-fonte'}|${normalizarDataMes(competencia)}`;
const soma = (lista, campo) => (lista || []).reduce((total, item) => total + Number(item[campo] || 0), 0);
const centavos = (valor) => Math.round(Number(valor || 0) * 100);

// Recebimento previsto pelo modulo de consorcios (contemplacao) ainda sem conta: aguarda confirmacao.
export function receitaPendenteConfirmacao(receita) {
    const observacoes = String((receita && receita.observacoes) || '');
    return /\bconsorcio_id=\d+\b/.test(observacoes) && !(receita && receita.conta_bancaria_id);
}

export function obterStatusReceita(previsto, realizado) {
    if (realizado > 0 && (previsto <= 0 || realizado >= previsto)) return 'REALIZADA';
    if (realizado > 0) return 'PARCIAL';
    return 'PREVISTA';
}

function obterContaLinha(fonte, realizada, contas) {
    const contaId = (realizada && realizada.conta_bancaria_id) || (fonte && fonte.conta_bancaria_id);
    if (!contaId) return null;
    return (contas || []).find((conta) => Number(conta.id) === Number(contaId)) || {
        id: contaId,
        nome: (realizada && realizada.conta_bancaria && realizada.conta_bancaria.nome)
            || (fonte && fonte.conta_bancaria && fonte.conta_bancaria.nome) || 'Conta bancária',
        instituicao: (realizada && realizada.conta_bancaria && realizada.conta_bancaria.instituicao)
            || (fonte && fonte.conta_bancaria && fonte.conta_bancaria.instituicao) || '',
    };
}

// Dia previsto (numero) ou data prevista inteira (adaptacao do novo aplicativo), como montarDataPrevista.
export function montarDataPrevista(anoMes, dia) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(String(dia || ''))) return dia;
    const ano = Number(anoMes.slice(0, 4));
    const mes = Number(anoMes.slice(5, 7));
    const ultimoDia = new Date(ano, mes, 0).getDate();
    const diaSeguro = Math.min(Math.max(Number(dia || 1), 1), ultimoDia);
    return `${anoMes.slice(0, 8)}${String(diaSeguro).padStart(2, '0')}`;
}

// montarReceitasMes do desktop (mesmas linhas, campos e ordem), ja com as adaptacoes do novo aplicativo.
export function montarReceitasMes({ orcamentos, realizadas, anoMes, fontes, contas }) {
    const buscarFonte = (id) => (fontes || []).find((fonte) => Number(fonte.id) === Number(id));
    const realizadasEfetivas = (realizadas || []).filter((receita) => !receitaPendenteConfirmacao(receita));
    const realizadasPendentes = (realizadas || []).filter(receitaPendenteConfirmacao);
    const realizadasSelecionadas = realizadasEfetivas.filter((receita) => normalizarDataMes(receita.competencia || receita.mes_referencia) === anoMes);
    const realizadasPorFonteCompetencia = new Map();
    realizadasEfetivas.forEach((receita) => {
        if (!receita.item_receita_id) return;
        const chave = chaveReceita(receita.item_receita_id, receita.competencia || receita.mes_referencia);
        if (!realizadasPorFonteCompetencia.has(chave)) realizadasPorFonteCompetencia.set(chave, []);
        realizadasPorFonteCompetencia.get(chave).push(receita);
    });

    const idsPlanejadosNoMesSelecionado = new Set();
    const chavesPlanejadas = new Set();
    const lista = [];

    (orcamentos || [])
        .filter((orcamento) => normalizarDataMes(orcamento.ano_mes || orcamento.mes_referencia) <= anoMes)
        .forEach((orcamento) => {
            const itemId = orcamento.item_receita_id;
            const competencia = normalizarDataMes(orcamento.ano_mes || orcamento.mes_referencia);
            const chave = chaveReceita(itemId, competencia);
            const fonte = buscarFonte(itemId);
            const realizadasFonte = realizadasPorFonteCompetencia.get(chave) || [];
            const valorPrevisto = Number(orcamento.valor_previsto ?? orcamento.valor_esperado ?? 0);
            const valorRealizado = soma(realizadasFonte, 'valor_recebido');
            const status = obterStatusReceita(valorPrevisto, valorRealizado);
            if (competencia === anoMes) idsPlanejadosNoMesSelecionado.add(itemId);
            if (competencia !== anoMes && status === 'REALIZADA') return;
            chavesPlanejadas.add(chave);
            lista.push({
                uid: `orc-${orcamento.id || itemId}`,
                origem: 'orcamento',
                orcamento_id: orcamento.id,
                item_receita_id: itemId,
                fonte,
                nome: (fonte && fonte.nome) || (orcamento.item_receita && orcamento.item_receita.nome) || 'Receita',
                descricao: (fonte && fonte.descricao) || orcamento.observacoes || '',
                competencia,
                tipo: (fonte && fonte.tipo) || (orcamento.item_receita && orcamento.item_receita.tipo) || 'OUTROS',
                status,
                conta: obterContaLinha(fonte, realizadasFonte[0], contas),
                valor_previsto: valorPrevisto,
                valor_realizado: valorRealizado,
                diferenca: valorRealizado - valorPrevisto,
                realizada_id: realizadasFonte.length === 1 ? realizadasFonte[0].id : null,
                realizadas_count: realizadasFonte.length,
                // Adaptacao: a data prevista gravada na previsao no lugar do dia da fonte.
                dia_previsto_pagamento: orcamento.data_prevista || (fonte && fonte.dia_previsto_pagamento) || null,
            });
        });

    realizadasPendentes
        .filter((receita) => normalizarDataMes(receita.competencia || receita.mes_referencia) <= anoMes)
        .filter((receita) => !receita.item_receita_id
            || !chavesPlanejadas.has(chaveReceita(receita.item_receita_id, receita.competencia || receita.mes_referencia)))
        .forEach((receita) => {
            const fonte = buscarFonte(receita.item_receita_id);
            const valorPrevisto = Number(receita.valor_recebido || 0);
            lista.push({
                uid: `pend-real-${receita.id}`,
                origem: 'realizada_pendente',
                id: receita.id,
                item_receita_id: receita.item_receita_id,
                fonte,
                nome: receita.descricao || (fonte && fonte.nome) || 'Receita prevista',
                descricao: (fonte && fonte.descricao) || receita.observacoes || '',
                competencia: normalizarDataMes(receita.competencia || receita.mes_referencia) || anoMes,
                tipo: (fonte && fonte.tipo) || (receita.item_receita && receita.item_receita.tipo) || 'OUTROS',
                status: 'PREVISTA',
                conta: obterContaLinha(fonte, null, contas),
                valor_previsto: valorPrevisto,
                valor_realizado: 0,
                diferenca: -valorPrevisto,
                realizada_id: receita.id,
                realizadas_count: 0,
                dia_previsto_pagamento: Number(String(receita.data_recebimento || '').slice(8, 10)) || (fonte && fonte.dia_previsto_pagamento) || null,
            });
        });

    // (A linha "virtual" da fonte recorrente sem previsao no mes nao existe no novo aplicativo: receitas-adaptacoes.js.)

    realizadasSelecionadas
        .filter((receita) => receita.item_receita_id && !idsPlanejadosNoMesSelecionado.has(receita.item_receita_id))
        .filter((receita) => !(buscarFonte(receita.item_receita_id) || {}).recorrente)
        .forEach((receita) => lista.push(linhaRealizadaPontual(receita, buscarFonte(receita.item_receita_id), anoMes, contas)));
    realizadasSelecionadas.filter((receita) => !receita.item_receita_id)
        .forEach((receita) => lista.push(linhaRealizadaPontual(receita, null, anoMes, contas)));

    const ORDEM = { PREVISTA: 0, PARCIAL: 1, REALIZADA: 2, CANCELADA: 3 };
    return lista
        // Adaptacao (FIN-MVP-SANEAMENTO-FINAL-01): previsao removida (zerada) e sem recebimento nao e receita pendente.
        .filter((r) => !(r.origem === 'orcamento' && Number(r.valor_previsto || 0) === 0 && Number(r.valor_realizado || 0) === 0))
        .sort((a, b) => (ORDEM[a.status] ?? 9) - (ORDEM[b.status] ?? 9)
            || a.competencia.localeCompare(b.competencia)
            || a.nome.localeCompare(b.nome));
}

function linhaRealizadaPontual(receita, fonte, anoMes, contas) {
    const valorRealizado = Number(receita.valor_recebido || 0);
    return {
        uid: `real-${receita.id}`,
        origem: 'realizada',
        id: receita.id,
        item_receita_id: receita.item_receita_id,
        fonte,
        nome: receita.descricao || (fonte && fonte.nome) || 'Receita pontual',
        descricao: (fonte && fonte.descricao) || receita.observacoes || '',
        competencia: normalizarDataMes(receita.competencia || receita.mes_referencia) || anoMes,
        tipo: (fonte && fonte.tipo) || (receita.item_receita && receita.item_receita.tipo) || 'PONTUAL',
        status: 'REALIZADA',
        conta: obterContaLinha(fonte, receita, contas),
        valor_previsto: 0,
        valor_realizado: valorRealizado,
        diferenca: valorRealizado,
        realizada_id: receita.id,
        realizadas_count: 1,
        dia_previsto_pagamento: null,
    };
}

const normalizarTexto = (texto) => String(texto || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

// aplicarFiltrosLocais do desktop: as do mes (Tipo e Busca) e as atrasadas (sem filtro, como o desktop).
export function separarReceitas(linhas, anoMes, { tipo = '', busca = '' } = {}) {
    const termo = normalizarTexto(String(busca || '').trim());
    const doMes = (linhas || [])
        .filter((r) => r.competencia === anoMes)
        .filter((r) => {
            const tipoOk = !tipo || r.tipo === tipo;
            const texto = normalizarTexto([r.nome, r.descricao, formatarTipo(r.tipo), r.conta && r.conta.nome,
                r.conta && r.conta.instituicao].filter(Boolean).join(' '));
            return tipoOk && (!termo || texto.includes(termo));
        });
    const atrasadas = (linhas || []).filter((r) => r.competencia < anoMes && r.status !== 'REALIZADA');
    return { doMes, atrasadas };
}

export const faltaReceber = (r) => (['PREVISTA', 'PARCIAL'].includes(r.status) ? Math.max(centavos(r.valor_previsto) - centavos(r.valor_realizado), 0) : 0);

// Em centavos. Previsto e Realizado = os cartoes do desktop (renderizarKpis); Pendente = o que falta das previstas e parciais.
export function totaisDaLista(linhas) {
    return {
        previsto: (linhas || []).reduce((t, r) => t + centavos(r.valor_previsto), 0),
        recebido: (linhas || []).reduce((t, r) => t + centavos(r.valor_realizado), 0),
        pendente: (linhas || []).reduce((t, r) => t + faltaReceber(r), 0),
    };
}

// Situacao em texto do mobile (o desktop: Prevista, Parcial, Realizada).
export const SITUACOES = { PREVISTA: 'Prevista', PARCIAL: 'Parcialmente recebida', REALIZADA: 'Recebida', CANCELADA: 'Cancelada' };

// Recebimentos (nao estornados) da linha: os da fonte na competencia, ou o proprio registro (pontual ou pendente).
export function recebimentosDaLinha(linha, realizadas) {
    if (linha.origem !== 'orcamento') return (realizadas || []).filter((r) => r.id === linha.realizada_id && linha.origem === 'realizada');
    return (realizadas || []).filter((r) => !receitaPendenteConfirmacao(r) && r.item_receita_id === linha.item_receita_id
        && normalizarDataMes(r.competencia || r.mes_referencia) === linha.competencia)
        .sort((a, b) => String(a.data_recebimento).localeCompare(String(b.data_recebimento)) || a.id - b.id);
}

const diaMes = (iso) => (iso ? `${String(iso).slice(8, 10)}/${String(iso).slice(5, 7)}` : '');

// Linha discreta abaixo da descricao: data prevista (pendente) ou do recebimento (recebida), e a situacao.
export function legendaDaReceita(linha, recebimentos) {
    const ultimo = (recebimentos || [])[recebimentos.length - 1];
    if (linha.status === 'REALIZADA') return ultimo ? `Receb. ${diaMes(ultimo.data_recebimento)} · recebida` : 'recebida';
    const prevista = linha.dia_previsto_pagamento ? `Prev. ${diaMes(montarDataPrevista(linha.competencia, linha.dia_previsto_pagamento))}` : 'Sem data prevista';
    if (linha.status === 'PARCIAL') return `${prevista} · parcial`;
    if (linha.origem === 'realizada_pendente') return `${prevista} · aguardando confirmação`;
    return prevista;
}

// Valor da linha: o recebido quando recebida; senao o previsto (o que se espera receber).
export const valorDaLinha = (linha) => (linha.status === 'REALIZADA' ? centavos(linha.valor_realizado) : centavos(linha.valor_previsto));

// Operacoes que o desktop permite para a linha e que o banco aceita (as que ele sempre recusaria nao aparecem):
// - receber: "Confirmar/realizar" (desabilitado na realizada); fonte do modulo de consorcios so na contemplacao;
// - editar: a fonte da receita ("Editar" do desktop abre a fonte), menos a de outro modulo;
// - estornar: so a realizada com um recebimento (o botao do desktop);
// - cancelar: "Cancelar/ignorar" = remover a previsao, so sem recebimento (o banco recusa a que ja tem recebimento) e
//   fora do modulo de consorcios. Excluir recebimento nao existe no novo aplicativo (corrigir = estornar).
export function acoesDaReceita(linha) {
    const deOutroModulo = Boolean(linha.fonte && linha.fonte.de_outro_modulo);
    return {
        receber: linha.status !== 'REALIZADA' && (linha.origem === 'realizada_pendente'
            || (linha.origem === 'orcamento' && Boolean(linha.item_receita_id) && !deOutroModulo)),
        editar: Boolean(linha.item_receita_id && linha.fonte) && !deOutroModulo,
        estornar: linha.status === 'REALIZADA' && Boolean(linha.realizada_id) && linha.origem !== 'realizada_pendente',
        cancelar: linha.origem === 'orcamento' && linha.status === 'PREVISTA' && centavos(linha.valor_realizado) === 0 && !deOutroModulo,
    };
}
