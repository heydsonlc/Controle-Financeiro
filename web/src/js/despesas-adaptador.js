// FIN-FIDELIDADE-DESPESAS-1 — adaptador da tela original de Despesas: responde as rotas /api/... que
// js/original/despesas.js chama (ponte-api.js), no formato do Flask, com as funcoes do Supabase ja validadas.
//
// Regras financeiras, autorizacao, versao contra edicao concorrente, idempotencia e saldos ficam no banco
// (contas_do_mes, despesa_para_edicao, criar/editar/excluir_despesa, dados_pagamento_*, pagar_*, estornar_*).
// Aqui so ha traducao de formato e as somas de apresentacao da barra lateral (o Flask tambem as fazia na rota).
// O que a tela original oferece e o banco ainda nao atende responde "em migracao" (consorcios, documentos fiscais,
// recorrencia semanal ou no cartao, consolidacao de fatura).

import { supabase } from './cliente.js';
import {
    criarChaves, emMigracao, falha, hojeBrasilia, mensagemDeErro, ok, textoBloqueio, valorTexto,
} from './adaptador-comum.js';
import { centavos, deslocarMes, mesAtualBrasilia, reais } from './comum.js';
import { mostrarGeracao } from './despesas-recorrencias.js';
import { definirCompetencia, iniciarMoldura } from './moldura.js';

const MES = /^\d{4}-(0[1-9]|1[0-2])$/;
const estado = { perfilId: null, mes: null, linhas: new Map(), categorias: null, contasAtivas: [] };
const chaves = criarChaves();

function somarDias(iso, dias) {
    const data = new Date(`${iso}T00:00:00Z`);
    data.setUTCDate(data.getUTCDate() + dias);
    return data.toISOString().slice(0, 10);
}

async function categoriasDeDespesa() {
    if (!estado.categorias) {
        const { data, error } = await supabase.rpc('categorias_de_despesa');
        if (error) throw error;
        estado.categorias = (data || []).map((c) => ({ id: c.id, nome: c.nome, cor: c.cor, ativo: true }));
    }
    return estado.categorias;
}

async function contasBancariasAtivas() {
    const { data, error } = await supabase.rpc('contas_bancarias_do_perfil', { p_perfil_id: estado.perfilId });
    if (error) throw error;
    estado.contasAtivas = (data || []).filter((c) => String(c.status || '').toUpperCase() === 'ATIVO');
    return estado.contasAtivas;
}

// Linha de contas_do_mes (+ despesa_para_edicao, so nas despesas do mes) no formato de GET /api/despesas do Flask.
function linhaDoFlask(c, mes, edicao, categoriasPorNome, meios = new Map()) {
    const fatura = c.grupo === 'FATURA';
    const categoria = c.categoria_nome
        ? { ...(categoriasPorNome.get(c.categoria_nome) || {}), nome: c.categoria_nome, cor: c.categoria_cor || '#6e6e73' }
        : null;
    const item = edicao && edicao.item;
    const contaBancaria = edicao && edicao.conta && edicao.conta.conta_bancaria_id;
    const linha = {
        id: c.id,
        nome: c.nome,
        descricao: (edicao && edicao.conta && edicao.conta.descricao) || '',
        tipo: fatura ? 'cartao' : (edicao && /consorcio/i.test(edicao.bloqueio || '') ? 'Consorcio' : 'Simples'),
        valor: Number(c.valor || 0),
        // So uma conta ativa do perfil fixa a conta do pagamento (como no Flask); senao a tela pede a conta.
        conta_bancaria_id: estado.contasAtivas.some((cb) => cb.id === contaBancaria) ? contaBancaria : null,
        financiamento_parcela_id: edicao && /financiamento/i.test(edicao.bloqueio || '') ? c.id : null,
        categoria_id: categoria && categoria.id ? categoria.id : null,
        categoria,
        data_vencimento: c.data_vencimento,
        data_pagamento: c.data_pagamento,
        pago: c.status_pagamento === 'Pago',
        status_pagamento: c.status_pagamento,
        mes_competencia: mes,
        recorrente: !fatura && Boolean(item && item.recorrente),
        tipo_recorrencia: !fatura && item && item.recorrente ? item.tipo_recorrencia : null,
        meio_pagamento: fatura ? 'cartao' : (c.debito_automatico ? 'debito_automatico' : (item && meios.get(item.id)) || null),
        debito_automatico: Boolean(c.debito_automatico),
        numero_parcela: c.numero_parcela,
        total_parcelas: c.total_parcelas,
        agrupado: fatura,
        ativo: true,
        is_fatura_cartao: fatura,
    };
    if (fatura) {
        Object.assign(linha, {
            valor_fatura: linha.valor,
            valor_planejado: Number(c.valor_previsto || 0),
            valor_executado: Number(c.valor_executado || 0),
            estouro_orcamento: false,
            cartao_id: c.cartao_id,
        });
    }
    return linha;
}

// Barra lateral e cartoes de resumo: as mesmas somas que a rota do Flask fazia sobre a listagem.
function barraLateral(doMes, todas, receitasMes) {
    const soma = (lista) => lista.reduce((s, d) => s + centavos(d.valor), 0) / 100;
    const hoje = hojeBrasilia();
    const seteDias = somarDias(hoje, 7);
    const vencendo = todas.filter((d) => !d.pago && d.data_vencimento && d.data_vencimento >= hoje && d.data_vencimento <= seteDias);
    const recorrentes = doMes.filter((d) => d.recorrente && !d.is_fatura_cartao);
    const faturas = doMes.filter((d) => d.is_fatura_cartao);
    const composicao = new Map();
    for (const d of doMes.filter((x) => !x.is_fatura_cartao)) {
        const nome = (d.categoria && d.categoria.nome) || 'Sem categoria';
        const atual = composicao.get(nome) || { nome, valor: 0, cor: (d.categoria && d.categoria.cor) || '#6e6e73' };
        atual.valor = (centavos(atual.valor) + centavos(d.valor)) / 100;
        composicao.set(nome, atual);
    }
    const proximos = todas
        .filter((d) => !d.pago && d.data_vencimento && d.data_vencimento >= hoje && !d.is_fatura_cartao)
        .sort((a, b) => a.data_vencimento.localeCompare(b.data_vencimento))
        .slice(0, 5)
        .map((d) => ({ id: d.id, nome: d.nome, valor: d.valor, data_vencimento: d.data_vencimento,
            status_pagamento: d.status_pagamento || 'Pendente', categoria: (d.categoria && d.categoria.nome) || '', tipo: d.tipo }));
    const totalMes = soma(doMes);
    return {
        total_mes: totalMes,
        total_pendentes: soma(doMes.filter((d) => !d.pago)),
        total_pagas: soma(doMes.filter((d) => d.pago)),
        vencendo_7d_count: vencendo.length,
        vencendo_7d_valor: soma(vencendo),
        recorrentes_count: recorrentes.length,
        recorrentes_valor: soma(recorrentes),
        cartoes_count: faturas.length,
        cartoes_valor: soma(faturas),
        composicao_categoria: [...composicao.values()].sort((a, b) => b.valor - a.valor),
        proximos_vencimentos: proximos,
        receitas_mes: receitasMes,
        saldo_mes: (centavos(receitasMes) - centavos(totalMes)) / 100,
    };
}

// FIN-FIDELIDADE-RECORRENCIAS-1: o cadastro de cartao (Flask e novo aplicativo) marca o proprio cartao (item
// "Agregador") como recorrente; o gerador o lista como "nao pode ser gerado", mas a fatura e gerada pela parte de
// cartoes e o cartao em si nunca vira conta. O aviso ignora so essa rejeicao (pelo motivo exato do banco); as demais
// continuam. A correcao no gerador (pular o cartao) fica pendente: troca uma funcao grande do banco.
const MOTIVO_CARTAO_COMO_RECORRENCIA = 'Cartao marcado como recorrencia';
function semCartoesComoRecorrencia(previa) {
    if (!previa) return previa;
    const rejeitados = (previa.rejeitados || []).filter((item) => item.motivo !== MOTIVO_CARTAO_COMO_RECORRENCIA);
    return { ...previa, rejeitados, rejeitadas: rejeitados.length };
}

async function atualizarGeracao(mes) {
    const [previaResp, pendenciasResp] = await Promise.all([
        supabase.rpc('previa_geracao', { p_perfil_id: estado.perfilId, p_mes: `${mes}-01` }),
        supabase.rpc('recorrencias_rejeitadas', { p_perfil_id: estado.perfilId, p_incluir_dispensadas: true }),
    ]);
    const previa = semCartoesComoRecorrencia(previaResp.error ? null : previaResp.data);
    // Quem so le o perfil nao ve as acoes de escrita da tela original (o banco recusaria de qualquer forma).
    document.body.classList.toggle('cf-somente-leitura', !(previa && previa.pode_gerir));
    const dispensadas = new Set((pendenciasResp.error ? [] : pendenciasResp.data || [])
        .filter((p) => p.aviso_dispensado_em).map((p) => `${p.item_id}|${String(p.competencia).slice(0, 10)}`));
    mostrarGeracao(previa, estado.perfilId, mes, {
        perfilId: estado.perfilId,
        mes,
        dispensadas,
        recarregar: async (mensagem) => {
            if (mensagem) {
                const aviso = document.getElementById('geracao-resultado');
                aviso.textContent = mensagem;
                aviso.hidden = false;
            }
            window.carregarDespesas();
        },
    });
}

async function listar(parametros) {
    const mes = parametros.get('mes_referencia') || parametros.get('mes') || mesAtualBrasilia();
    if (!MES.test(mes)) return falha('Competência inválida. Use MM/AAAA.');
    if (mes !== estado.mes) document.getElementById('geracao-resultado').hidden = true;
    estado.mes = mes;
    definirCompetencia(mes);
    const doMes = (m) => supabase.rpc('contas_do_mes', { p_perfil_id: estado.perfilId, p_mes: `${m}-01` });
    const [atual, anterior, seguinte, receitas, categorias, , , recorrentes] = await Promise.all([
        doMes(mes), doMes(deslocarMes(mes, -1)), doMes(deslocarMes(mes, 1)),
        supabase.rpc('receitas_do_mes', { p_perfil_id: estado.perfilId, p_mes: `${mes}-01` }),
        categoriasDeDespesa(), contasBancariasAtivas(), atualizarGeracao(mes),
        supabase.rpc('recorrencias_do_perfil', { p_perfil_id: estado.perfilId }),
    ]);
    if (atual.error) return falha(mensagemDeErro(atual.error), 403);
    const categoriasPorNome = new Map(categorias.map((c) => [c.nome, c]));
    // Dados do item (recorrencia, categoria, observacoes, conta) que contas_do_mes nao traz: um por despesa do mes.
    const edicoes = new Map(await Promise.all((atual.data || []).filter((c) => c.grupo === 'DESPESA').map(async (c) => {
        const { data, error } = await supabase.rpc('despesa_para_edicao', { p_perfil_id: estado.perfilId, p_conta_id: c.id });
        return [c.id, error ? null : data];
    })));
    const meios = new Map((recorrentes.error ? [] : recorrentes.data || []).map((r) => [r.id, r.meio_pagamento]));
    const linhas = (atual.data || []).map((c) => linhaDoFlask(c, mes, edicoes.get(c.id), categoriasPorNome, meios));
    // Como o Flask: vencimento mais recente primeiro (a tela agrupa por origem e tipo).
    linhas.sort((x, y) => String(y.data_vencimento || '').localeCompare(String(x.data_vencimento || '')));
    const vizinhas = [[anterior, deslocarMes(mes, -1)], [seguinte, deslocarMes(mes, 1)]]
        .flatMap(([r, m]) => (r.error ? [] : r.data || []).map((c) => linhaDoFlask(c, m, null, categoriasPorNome)));
    estado.linhas = new Map(linhas.map((l) => [l.id, l]));
    const receitasMes = (receitas.error ? [] : receitas.data || []).reduce((s, r) => {
        const recebido = centavos(r.valor_recebido);
        return s + (recebido > 0 ? recebido : centavos(r.valor_previsto));
    }, 0) / 100;
    return ok({ data: linhas, sidebar: barraLateral(linhas, [...linhas, ...vizinhas], receitasMes) });
}

async function edicaoAtual(id) {
    const { data, error } = await supabase.rpc('despesa_para_edicao', { p_perfil_id: estado.perfilId, p_conta_id: id });
    if (error) throw error;
    return data;
}

async function obter(id) {
    let edicao;
    try {
        edicao = await edicaoAtual(id);
    } catch (erro) {
        return falha(mensagemDeErro(erro), 404);
    }
    if (!edicao.pode_gerir) return falha('Você tem acesso somente de leitura a este perfil.', 403);
    if (edicao.bloqueio && /consorcio/i.test(edicao.bloqueio)) return emMigracao('Parcelas de consórcio');
    if (edicao.bloqueio && !edicao.pode_editar) return falha(`Esta despesa não pode ser editada. ${textoBloqueio(edicao.bloqueio)}`, 409);
    const linha = estado.linhas.get(id);
    return ok({ data: {
        id,
        nome: edicao.conta.nome,
        descricao: edicao.conta.descricao || '',
        valor: Number(edicao.conta.valor),
        categoria_id: edicao.item.categoria_id,
        data_vencimento: edicao.conta.data_vencimento,
        data_pagamento: (linha && linha.data_pagamento) || null,
        pago: edicao.conta.status_pagamento === 'Pago',
        recorrente: Boolean(edicao.item.recorrente),
        tipo_recorrencia: edicao.item.recorrente ? edicao.item.tipo_recorrencia : 'mensal',
        mes_competencia: String(edicao.conta.competencia || '').slice(0, 7),
        meio_pagamento: edicao.conta.debito_automatico ? 'debito' : '',
        tipo: 'Simples',
    } });
}

// Pedidos do formulario original que o novo aplicativo ainda nao atende (sem registro incompleto).
function recusaDoFormulario(corpo) {
    if (corpo.pago) {
        return 'Use a ação de pagamento para marcar a despesa como paga: ela escolhe a conta bancária e registra o movimento.';
    }
    if (corpo.recorrente && /^semanal/.test(String(corpo.tipo_recorrencia || ''))) {
        return 'Semanal e a cada 2 semanas: o novo aplicativo ainda não gera essa frequência (pendência). Use mensal ou anual.';
    }
    if (corpo.recorrente && !['mensal', 'anual'].includes(corpo.tipo_recorrencia)) return 'Tipo de recorrência inválido.';
    if (corpo.meio_pagamento === 'cartao') return 'Recorrência no cartão de crédito: em migração para o novo aplicativo (módulo de cartões).';
    if (!corpo.data_vencimento) return 'Informe a data de vencimento.';
    if (!(Number(corpo.valor) > 0)) return 'Informe um valor válido.';
    return null;
}

async function criar(corpo) {
    const recusa = recusaDoFormulario(corpo || {});
    if (recusa) return falha(recusa);
    const dados = {
        nome: String(corpo.nome || '').trim(),
        valor: valorTexto(corpo.valor),
        descricao: String(corpo.descricao || '').trim(),
        categoria_id: corpo.categoria_id,
        data_vencimento: corpo.data_vencimento,
        debito_automatico: false,
        conta_bancaria_id: null,
    };
    if (corpo.recorrente) Object.assign(dados, { recorrente: true, tipo_recorrencia: corpo.tipo_recorrencia });
    else if (MES.test(corpo.mes_competencia || '')) dados.competencia = `${corpo.mes_competencia}-01`;
    const operacao = `criar:${JSON.stringify(dados)}`;
    const { data, error } = await supabase.rpc('criar_despesa', { p_perfil_id: estado.perfilId, p_dados: dados, p_chave: chaves.de(operacao) });
    if (error) return falha(mensagemDeErro(error));
    chaves.esquecer(operacao);
    let message = data.recorrente
        ? 'Recorrência cadastrada. As contas são geradas pela ação "Gerar contas".'
        : `Despesa salva na competência ${String(data.competencia).slice(5, 7)}/${String(data.competencia).slice(0, 4)}.`;
    // FIN-FIDELIDADE-RECORRENCIAS-1: o meio de pagamento (boleto, PIX ou debito) da recorrencia e gravado, so informativo.
    if (data.recorrente && ['boleto', 'pix', 'debito'].includes(corpo.meio_pagamento)) {
        const lista = await supabase.rpc('recorrencias_do_perfil', { p_perfil_id: estado.perfilId });
        const item = !lista.error && (lista.data || []).find((r) => r.id === data.item_id);
        const meio = item && await supabase.rpc('definir_meio_pagamento_recorrencia', {
            p_perfil_id: estado.perfilId, p_item_id: data.item_id, p_versao: item.versao, p_meio: corpo.meio_pagamento,
        });
        if (!meio || meio.error) message += ' O meio de pagamento não foi gravado: ajuste na tela Recorrências.';
    }
    return ok({ message });
}

async function atualizar(id, corpo) {
    let edicao;
    try {
        edicao = await edicaoAtual(id);
    } catch (erro) {
        return falha(mensagemDeErro(erro), 404);
    }
    if (!edicao.pode_editar) return falha(edicao.bloqueio ? textoBloqueio(edicao.bloqueio) : 'Operação não autorizada para este perfil.', 409);
    if (corpo.pago && edicao.conta.status_pagamento !== 'Pago') {
        return falha('Use a ação de pagamento para marcar a despesa como paga. Edição comum não pode registrar pagamentos.');
    }
    const recorrente = Boolean(edicao.item.recorrente);
    if (Boolean(corpo.recorrente) !== recorrente || (recorrente && corpo.tipo_recorrencia !== edicao.item.tipo_recorrencia)) {
        return falha('Para alterar a recorrência (frequência e próximas contas), use a tela Recorrências.');
    }
    if (!(Number(corpo.valor) > 0)) return falha('Informe um valor válido.');
    const dados = {
        nome: String(corpo.nome || '').trim(),
        valor: valorTexto(corpo.valor),
        descricao: String(corpo.descricao || '').trim(),
        debito_automatico: Boolean(edicao.conta.debito_automatico),
        conta_bancaria_id: edicao.conta.conta_bancaria_id,
    };
    if (corpo.data_vencimento && corpo.data_vencimento !== edicao.conta.data_vencimento) {
        if (!edicao.pode_mudar_vencimento) return falha('O vencimento desta conta não pode ser alterado aqui.');
        dados.data_vencimento = corpo.data_vencimento;
    } else {
        dados.data_vencimento = edicao.conta.data_vencimento;
    }
    if (!recorrente) {
        dados.categoria_id = corpo.categoria_id;
        if (MES.test(corpo.mes_competencia || '')) dados.competencia = `${corpo.mes_competencia}-01`;
    }
    const { error } = await supabase.rpc('editar_despesa', {
        p_perfil_id: estado.perfilId, p_conta_id: id, p_versao: edicao.versao, p_dados: dados,
    });
    if (error) return falha(mensagemDeErro(error));
    return ok({ message: 'Despesa atualizada com sucesso' });
}

async function excluir(id, parametros) {
    let edicao;
    try {
        edicao = await edicaoAtual(id);
    } catch (erro) {
        return falha(mensagemDeErro(erro), 404);
    }
    if (!edicao.pode_excluir) return falha(edicao.bloqueio ? textoBloqueio(edicao.bloqueio) : 'Esta despesa não pode ser excluída.', 409);
    // "Esta e as futuras" de uma recorrencia: inativa a recorrencia (nenhuma conta nova) e exclui esta conta.
    if (parametros.get('tipo_exclusao') === 'futuras' && edicao.item.recorrente) {
        if (!edicao.pode_inativar_recorrencia) return falha('A recorrência não pode ser inativada por aqui.');
        const inativada = await supabase.rpc('inativar_recorrencia', {
            p_perfil_id: estado.perfilId, p_item_id: edicao.item.id, p_versao: edicao.versao_recorrencia,
        });
        if (inativada.error) return falha(mensagemDeErro(inativada.error));
        edicao = await edicaoAtual(id);
    }
    const { error } = await supabase.rpc('excluir_despesa', { p_perfil_id: estado.perfilId, p_conta_id: id, p_versao: edicao.versao });
    if (error) return falha(mensagemDeErro(error));
    return ok({ message: 'Despesa excluída com sucesso' });
}

function motivoSemPagamento(dados, bloqueio) {
    if (bloqueio) return textoBloqueio(bloqueio);
    if (dados.sistema === 'FLASK') return 'O pagamento das despesas deste perfil ainda é feito no sistema atual.';
    return 'Operação não autorizada para este perfil.';
}

async function pagar(id, corpo) {
    const linha = estado.linhas.get(id);
    if (linha && linha.is_fatura_cartao) return pagarFatura(id, corpo);
    const { data, error } = await supabase.rpc('dados_pagamento_despesa', { p_perfil_id: estado.perfilId, p_conta_id: id });
    if (error) return falha(mensagemDeErro(error));
    if (!data.pode_pagar) return falha(data.despesa.paga ? 'Esta despesa já está paga.' : motivoSemPagamento(data, data.despesa.bloqueio));
    const devido = Number(data.despesa.valor);
    const pago = corpo.valor_pago === undefined || corpo.valor_pago === null ? devido : Number(corpo.valor_pago);
    if (centavos(pago) !== centavos(devido) && (!corpo.tipo_ajuste || !corpo.justificativa)) {
        return falha('Classifique a diferença e escreva a justificativa.');
    }
    const operacao = `pagar:${id}`;
    const { data: r, error: erro } = await supabase.rpc('pagar_despesa', {
        p_perfil_id: estado.perfilId, p_conta_id: id, p_chave: chaves.de(operacao), p_dados: {
            conta_bancaria_id: corpo.conta_bancaria_id, data_pagamento: corpo.data_pagamento, valor_pago: valorTexto(pago),
            valor_devido: valorTexto(devido), tipo_ajuste: corpo.tipo_ajuste || null, justificativa: corpo.justificativa || null } });
    if (erro) return falha(mensagemDeErro(erro));
    chaves.esquecer(operacao);
    return ok({ message: `Despesa paga: ${reais(centavos(r.valor_pago))} debitados de ${r.conta_nome}. `
        + `Saldo da conta: ${reais(centavos(r.saldo_conta))}.` });
}

async function pagarFatura(id, corpo) {
    const { data, error } = await supabase.rpc('dados_pagamento_fatura', { p_perfil_id: estado.perfilId, p_fatura_id: id });
    if (error) return falha(mensagemDeErro(error));
    if (!data.pode_pagar) {
        return falha(data.fatura.paga ? 'Esta fatura já está paga.'
            : (data.sistema === 'FLASK' ? 'O pagamento das faturas deste perfil ainda é feito no sistema atual.'
                : 'A fatura não pode ser paga agora (sem compras ou sem permissão).'));
    }
    const executado = Number(data.fatura.valor_executado);
    const pago = corpo.valor_pago === undefined || corpo.valor_pago === null ? executado : Number(corpo.valor_pago);
    if (centavos(pago) !== centavos(executado) && (!corpo.tipo_ajuste || !corpo.justificativa)) {
        return falha('Classifique a diferença e escreva a justificativa.');
    }
    const dados = { conta_bancaria_id: corpo.conta_bancaria_id, data_pagamento: corpo.data_pagamento,
        valor_pago: valorTexto(pago), valor_executado: valorTexto(executado) };
    if (centavos(pago) !== centavos(executado)) Object.assign(dados, { tipo_ajuste: corpo.tipo_ajuste, justificativa: corpo.justificativa });
    const operacao = `pagar-fatura:${id}`;
    const { data: r, error: erro } = await supabase.rpc('pagar_fatura', {
        p_perfil_id: estado.perfilId, p_fatura_id: id, p_dados: dados, p_chave: chaves.de(operacao) });
    if (erro) {
        if (erro.hint === 'EXECUTADO_MUDOU') return falha('As compras da fatura mudaram. Recarregue a lista e confira o novo total.');
        return falha(mensagemDeErro(erro));
    }
    chaves.esquecer(operacao);
    return ok({ message: `Fatura paga: ${reais(centavos(r.valor_pago))} debitados de ${r.conta_nome}. `
        + `Saldo da conta: ${reais(centavos(r.saldo_conta))}.` });
}

async function estornar(id, corpo) {
    const linha = estado.linhas.get(id);
    const fatura = Boolean(linha && linha.is_fatura_cartao);
    const consulta = fatura
        ? await supabase.rpc('dados_pagamento_fatura', { p_perfil_id: estado.perfilId, p_fatura_id: id })
        : await supabase.rpc('dados_pagamento_despesa', { p_perfil_id: estado.perfilId, p_conta_id: id });
    if (consulta.error) return falha(mensagemDeErro(consulta.error));
    const vigente = (consulta.data.pagamentos || []).find((p) => p.vigente);
    if (!consulta.data.pode_estornar || !vigente) {
        return falha(consulta.data.sistema === 'FLASK'
            ? 'O estorno deste perfil ainda é feito no sistema atual.' : 'Não há pagamento vigente para estornar.');
    }
    const dados = { motivo: String(corpo.motivo || '').trim(), data_estorno: corpo.data_estorno };
    const operacao = `estornar:${id}:${vigente.movimento_id}`;
    const resposta = fatura
        ? await supabase.rpc('estornar_pagamento_fatura', { p_perfil_id: estado.perfilId, p_fatura_id: id,
            p_movimento_id: vigente.movimento_id, p_dados: dados, p_chave: chaves.de(operacao) })
        : await supabase.rpc('estornar_pagamento_despesa', { p_perfil_id: estado.perfilId, p_conta_id: id,
            p_movimento_id: vigente.movimento_id, p_dados: dados, p_chave: chaves.de(operacao) });
    if (resposta.error) return falha(mensagemDeErro(resposta.error));
    chaves.esquecer(operacao);
    return ok({ message: `Pagamento estornado: ${reais(centavos(resposta.data.valor_estornado))} devolvidos a `
        + `${vigente.conta_nome}. Saldo da conta: ${reais(centavos(resposta.data.saldo_conta))}.` });
}

// Detalhe da fatura (lancamentos do cartao na competencia), so leitura.
async function comprasDaFatura(cartaoId, parametros) {
    const mes = String(parametros.get('mes_fatura') || '').slice(0, 7);
    if (!MES.test(mes)) return falha('Competência inválida.');
    const { data, error } = await supabase.rpc('compras_da_fatura', { p_perfil_id: estado.perfilId, p_cartao_id: cartaoId, p_mes: `${mes}-01` });
    if (error) return falha(mensagemDeErro(error), 403);
    return ok({ data: (data || []).map((c) => ({
        id: c.id, descricao: c.descricao, valor: Number(c.valor), data_compra: c.data_compra,
        numero_parcela: c.numero_parcela, total_parcelas: c.total_parcelas, categoria_cartao_id: null,
        categoria_cartao_nome: c.categoria_nome, is_recorrente: Boolean(c.recorrente),
    })) });
}

const ROTAS = [
    ['GET', /^\/api\/despesas\/?$/, (m, p) => listar(p)],
    ['POST', /^\/api\/despesas\/?$/, (m, p, corpo) => criar(corpo)],
    ['GET', /^\/api\/despesas\/(\d+)$/, (m) => obter(Number(m[1]))],
    ['PUT', /^\/api\/despesas\/(\d+)$/, (m, p, corpo) => atualizar(Number(m[1]), corpo || {})],
    ['DELETE', /^\/api\/despesas\/(\d+)$/, (m, p) => excluir(Number(m[1]), p)],
    ['POST', /^\/api\/despesas\/(\d+)\/pagar$/, (m, p, corpo) => pagar(Number(m[1]), corpo || {})],
    ['POST', /^\/api\/despesas\/(\d+)\/estornar-pagamento$/, (m, p, corpo) => estornar(Number(m[1]), corpo || {})],
    ['GET', /^\/api\/categorias\/?$/, async () => ok({ data: await categoriasDeDespesa() })],
    ['GET', /^\/api\/contas\/?$/, async () => ok({ data: (await contasBancariasAtivas()).map((c) => ({ id: c.id, nome: c.nome, instituicao: c.instituicao })) })],
    ['GET', /^\/api\/cartoes\/(\d+)\/lancamentos$/, (m, p) => comprasDaFatura(Number(m[1]), p)],
    // Limites por categoria do cartao: sem funcao de leitura no Supabase ainda; o detalhe mostra as compras.
    ['GET', /^\/api\/cartoes\/(\d+)\/fatura-categorias$/, async () => ok({ categorias: [] })],
    // Avisos de recorrencia rejeitada: mostrados no bloco de geracao (despesas-recorrencias.js).
    ['GET', /^\/api\/recorrencias\/pendencias$/, async () => ok({ data: [] })],
    ['GET', /^\/api\/cartoes\/?$/, async () => emMigracao('Recorrência paga no cartão de crédito')],
    ['GET', /^\/api\/cartoes\/\d+\/categorias-limite$/, async () => emMigracao('Categoria do cartão')],
    ['GET', /^\/api\/categorias-cartao\/resolver$/, async () => emMigracao('Categoria do cartão')],
    ['POST', /^\/api\/cartoes\/\d+\/faturas\/[^/]+\/consolidar$/, async () => emMigracao('Consolidação de fatura')],
    [null, /^\/api\/consorcios(\/|$)/, async () => emMigracao('Consórcios')],
    [null, /^\/api\/ir\//, async () => emMigracao('Documentos fiscais')],
];

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && (!verbo || verbo === metodo)) return executar(m, parametros, corpo);
    }
    return emMigracao(`${metodo} ${caminho}`);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
} else if (contexto) {
    // Sem perfil autorizado (o aviso da moldura ja aparece): a tela nao consulta nada.
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
