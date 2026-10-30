// FIN-FIDELIDADE-MOVIMENTACOES-1 — adaptador da tela original de Lancamentos: responde as rotas /api/... que
// js/original/lancamentos.js chama (ponte-api.js), no formato do Flask. Leituras da migration 20261109090000 (secao 6);
// escrita so pelas funcoes ja existentes (criar_compra, criar/editar/excluir_despesa, excluir_compra), com as mesmas
// regras das telas de Cartoes e Despesas. Diferencas assumidas em relacao ao Flask (docs/FIN_FIDELIDADE_MOVIMENTACOES_1.md):
// - despesa direta "paga" na criacao e recusada: o pagamento escolhe a conta bancaria e registra o movimento (Despesas);
// - confirmar recebimento e entrada pontual sem conta bancaria: recusados (a receita e recebida em Receitas, com conta);
// - editar compra de cartao aqui gravaria uma compra nova (o Flask duplica): recusado, a correcao fica na tela de Cartoes;
// - "A partir de documento" (FIN-PRE-PRODUCAO-1): lista, sugestao e criacao do lancamento por js/documento-financeiro.js.

import { supabase } from './cliente.js';
import { criarChaves, emMigracao, falha, mensagemDeErro, ok, textoBloqueio, valorTexto } from './adaptador-comum.js';
import { confirmacoes, consolidadaDoErro } from './fechamento.js';
import { responderDocumentoFinanceiro } from './documento-financeiro.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };
const chaves = criarChaves();
const MES = /^\d{4}-(0[1-9]|1[0-2])/;

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

// As rotas de despesa direta e de exclusao mostram so "Erro ao salvar/excluir" (o Flask ignora a mensagem): o motivo
// aparece antes, no mesmo aviso da tela (mostrarErro).
function avisar(mensagem, status = 400) {
    if (typeof window.mostrarErro === 'function') window.mostrarErro(mensagem);
    return falha(mensagem, status);
}

const hojeMes = () => `${new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date()).slice(0, 7)}-01`;

// ---------------------------------------------------------------------------------------------------------------
// Leituras
// ---------------------------------------------------------------------------------------------------------------

async function cartoes() {
    const lista = await rpc((a) => supabase.rpc('cartoes_do_perfil', a), { p_perfil_id: estado.perfilId });
    return { status: 200, corpo: (lista || []).filter((c) => c.ativo).map((c) => ({ id: c.id, nome: c.nome, tipo: 'Agregador', ativo: true })) };
}

async function categorias() {
    const lista = await rpc((a) => supabase.rpc('categorias_de_despesa', a), {});
    return ok({ data: (lista || []).map((c) => ({ id: c.id, nome: c.nome, cor: c.cor, ativo: true })) });
}

async function contasBancarias() {
    const lista = await rpc((a) => supabase.rpc('contas_bancarias_tela', a), { p_perfil_id: estado.perfilId, p_status: 'ATIVO' });
    return ok({ data: lista || [], total: (lista || []).length });
}

async function limites(cartaoId) {
    const lista = await rpc((a) => supabase.rpc('limites_do_cartao', a), { p_perfil_id: estado.perfilId, p_cartao_id: cartaoId, p_mes: hojeMes() });
    return ok({ data: (lista || []).filter((l) => l.ativo).map((l) => ({ id: l.id, categoria_cartao_id: l.categoria_cartao_id,
        categoria_cartao_nome: l.categoria_cartao_nome, limite_mensal: Number(l.limite_mensal), ativo: true })) });
}

async function resolver(parametros) {
    const data = await rpc((a) => supabase.rpc('resolver_categoria_cartao_tela', a), { p_perfil_id: estado.perfilId,
        p_cartao_id: Number(parametros.get('cartao_id')), p_categoria_id: Number(parametros.get('categoria_id')) });
    return ok({ data });
}

async function competenciaSugerida(cartaoId, parametros) {
    const data = await rpc((a) => supabase.rpc('sugerir_competencia', a), {
        p_perfil_id: estado.perfilId, p_cartao_id: cartaoId, p_data_compra: parametros.get('data'),
    });
    return { status: 200, corpo: data };
}

async function comprasDoCartao(cartaoId) {
    const lista = await rpc((a) => supabase.rpc('compras_do_cartao_tela', a), { p_perfil_id: estado.perfilId, p_cartao_id: cartaoId });
    return { status: 200, corpo: lista || [] };
}

async function despesas() {
    const lista = await rpc((a) => supabase.rpc('despesas_diretas_tela', a), { p_perfil_id: estado.perfilId });
    return ok({ data: lista || [] });
}

async function receitas(parte, parametros) {
    const mes = parametros.get('ano_mes');
    const ano = Number.parseInt(parametros.get('ano') ?? '', 10);
    const r = await rpc((a) => supabase.rpc('receitas_lancamentos_tela', a), {
        p_perfil_id: estado.perfilId, p_mes: mes && MES.test(mes) ? `${mes.slice(0, 7)}-01` : null, p_ano: Number.isNaN(ano) ? null : ano,
    });
    return ok({ data: r[parte] || [] });
}

// ---------------------------------------------------------------------------------------------------------------
// Compra no cartao (criar_compra; fatura consolidada so com a confirmacao do total visto, como no Flask)
// ---------------------------------------------------------------------------------------------------------------

async function criarCompra(cartaoId, corpo) {
    const campoId = document.getElementById('lancamento-id');
    if (campoId && campoId.value && campoId.dataset.tipo === 'cartao') {
        return falha('Para corrigir uma compra no cartão, use a tela Cartões (editar lançamento). Salvar aqui criaria uma compra nova. Nada foi gravado.');
    }
    const valor = Number(corpo.valor);
    if (!(valor > 0)) return falha('Informe um valor válido.');
    if (!MES.test(String(corpo.mes_fatura || ''))) return falha('Escolha o mês da fatura');
    const dados = {
        cartao_id: cartaoId, descricao: String(corpo.descricao || '').trim(), valor: valorTexto(valor),
        total_parcelas: Number(corpo.total_parcelas) || 1, data_compra: corpo.data_compra,
        mes_fatura: `${String(corpo.mes_fatura).slice(0, 7)}-01`, categoria_id: Number(corpo.categoria_id),
        observacoes: String(corpo.observacoes || '').trim(),
    };
    const operacao = `compra:${JSON.stringify(dados)}`;
    if (Array.isArray(corpo.confirmar_consolidadas)) dados.confirmar_consolidadas = confirmacoes(corpo.confirmar_consolidadas);
    const { data, error } = await supabase.rpc('criar_compra', { p_perfil_id: estado.perfilId, p_dados: dados, p_chave: chaves.de(operacao) });
    if (error) {
        if (consolidadaDoErro(error)) {
            // Mesma pergunta do Flask (409 CONFIRMAR_FATURA_CONSOLIDADA), com os totais da previa do banco.
            const previa = await supabase.rpc('previa_compra', { p_perfil_id: estado.perfilId, p_dados: { ...dados, confirmar_consolidadas: undefined } });
            if (previa.error) return falha(mensagemDeErro(previa.error));
            return { status: 409, corpo: { success: false, codigo: 'CONFIRMAR_FATURA_CONSOLIDADA', faturas: previa.data.consolidadas || [],
                error: 'A compra entra em fatura já consolidada: confirme a inclusão.' } };
        }
        return falha(mensagemDeErro(error));
    }
    chaves.esquecer(operacao);
    return { status: 201, corpo: { success: true, data } };
}

// Excluir compra: as parcelas em fatura aberta saem (regra do FIN-CARTOES-1), com a confirmacao das quantidades.
async function excluirCompra(id) {
    const { data, error } = await supabase.rpc('compra_para_edicao', { p_perfil_id: estado.perfilId, p_lancamento_id: id });
    if (error) return avisar(mensagemDeErro(error));
    if (data.parcelas.length > 1) {
        const ficam = data.parcelas.length - data.abertas;
        const texto = `Esta compra é parcelada (${data.parcelas.length} parcelas). Serão excluídas as ${data.abertas} parcelas em fatura aberta`
            + (ficam ? `; ${ficam} em fatura paga ou fechada ficam (para corrigi-las é preciso estorno).` : '.');
        if (!window.confirm(texto)) return avisar('Exclusão cancelada. Nada foi excluído.', 409);
    }
    const resposta = await supabase.rpc('excluir_compra', { p_perfil_id: estado.perfilId, p_lancamento_id: id, p_versao: data.versao });
    if (resposta.error) return avisar(mensagemDeErro(resposta.error));
    return ok({ message: 'Lançamento excluído com sucesso' });
}

// ---------------------------------------------------------------------------------------------------------------
// Despesa direta (as mesmas funcoes e recusas da tela de Despesas)
// ---------------------------------------------------------------------------------------------------------------

const PAGAR = 'Use a ação de pagamento em Despesas para marcar a despesa como paga: ela escolhe a conta bancária e registra o movimento. Nada foi gravado.';

async function criarDespesa(corpo) {
    if (corpo.pago) return avisar(PAGAR);
    if (!(Number(corpo.valor) > 0)) return avisar('Informe um valor válido.');
    if (!corpo.data_vencimento) return avisar('Informe a data.');
    const dados = {
        nome: String(corpo.nome || '').trim(), valor: valorTexto(corpo.valor), descricao: String(corpo.descricao || '').trim(),
        categoria_id: corpo.categoria_id, data_vencimento: corpo.data_vencimento, debito_automatico: false, conta_bancaria_id: null,
    };
    if (MES.test(corpo.mes_competencia || '')) dados.competencia = `${String(corpo.mes_competencia).slice(0, 7)}-01`;
    const operacao = `despesa:${JSON.stringify(dados)}`;
    const { error } = await supabase.rpc('criar_despesa', { p_perfil_id: estado.perfilId, p_dados: dados, p_chave: chaves.de(operacao) });
    if (error) return avisar(mensagemDeErro(error));
    chaves.esquecer(operacao);
    return { status: 201, corpo: { success: true, message: 'Despesa criada com sucesso' } };
}

async function edicaoDespesa(id) {
    const { data, error } = await supabase.rpc('despesa_para_edicao', { p_perfil_id: estado.perfilId, p_conta_id: id });
    if (error) throw error;
    return data;
}

async function atualizarDespesa(id, corpo) {
    const edicao = await edicaoDespesa(id);
    if (!edicao.pode_editar) return avisar(edicao.bloqueio ? textoBloqueio(edicao.bloqueio) : 'Operação não autorizada para este perfil.', 409);
    if (corpo.pago && edicao.conta.status_pagamento !== 'Pago') return avisar(PAGAR);
    if (edicao.item.recorrente) return avisar('Despesa de recorrência: altere em Despesas ou em Recorrências.');
    if (!(Number(corpo.valor) > 0)) return avisar('Informe um valor válido.');
    const dados = {
        nome: String(corpo.nome || '').trim(), valor: valorTexto(corpo.valor), descricao: String(corpo.descricao || '').trim(),
        debito_automatico: Boolean(edicao.conta.debito_automatico), conta_bancaria_id: edicao.conta.conta_bancaria_id,
        categoria_id: corpo.categoria_id, data_vencimento: edicao.conta.data_vencimento,
    };
    if (corpo.data_vencimento && corpo.data_vencimento !== edicao.conta.data_vencimento) {
        if (!edicao.pode_mudar_vencimento) return avisar('A data desta despesa não pode ser alterada aqui.');
        dados.data_vencimento = corpo.data_vencimento;
    }
    if (MES.test(corpo.mes_competencia || '')) dados.competencia = `${String(corpo.mes_competencia).slice(0, 7)}-01`;
    const { error } = await supabase.rpc('editar_despesa', { p_perfil_id: estado.perfilId, p_conta_id: id, p_versao: edicao.versao, p_dados: dados });
    if (error) return avisar(mensagemDeErro(error));
    return ok({ message: 'Despesa atualizada com sucesso' });
}

async function excluirDespesa(id) {
    const edicao = await edicaoDespesa(id);
    if (!edicao.pode_excluir) return avisar(edicao.bloqueio ? textoBloqueio(edicao.bloqueio) : 'Esta despesa não pode ser excluída.', 409);
    const { error } = await supabase.rpc('excluir_despesa', { p_perfil_id: estado.perfilId, p_conta_id: id, p_versao: edicao.versao });
    if (error) return avisar(mensagemDeErro(error));
    return ok({ message: 'Despesa excluída com sucesso' });
}

// ---------------------------------------------------------------------------------------------------------------
// Rotas
// ---------------------------------------------------------------------------------------------------------------

const RECEBER = 'Recebimento sem conta bancária não é registrado no novo aplicativo: use Receitas → Receber, que escolhe a conta e registra o movimento. Nada foi gravado.';

const ROTAS = [
    ['GET', /^\/api\/cartoes\/?$/, () => cartoes()],
    ['GET', /^\/api\/categorias\/?$/, () => categorias()],
    ['GET', /^\/api\/contas\/?$/, () => contasBancarias()],
    ['GET', /^\/api\/cartoes\/(\d+)\/categorias-limite$/, (m) => limites(Number(m[1]))],
    ['GET', /^\/api\/categorias-cartao\/resolver$/, (m, c, p) => resolver(p)],
    ['GET', /^\/api\/cartoes\/(\d+)\/competencia-sugerida$/, (m, c, p) => competenciaSugerida(Number(m[1]), p)],
    ['GET', /^\/api\/cartoes\/(\d+)\/lancamentos$/, (m) => comprasDoCartao(Number(m[1]))],
    ['POST', /^\/api\/cartoes\/(\d+)\/lancamentos$/, (m, corpo) => criarCompra(Number(m[1]), corpo || {})],
    ['DELETE', /^\/api\/cartoes\/lancamentos\/(\d+)$/, (m) => excluirCompra(Number(m[1]))],
    ['GET', /^\/api\/despesas\/?$/, () => despesas()],
    ['POST', /^\/api\/despesas\/?$/, (m, corpo) => criarDespesa(corpo || {})],
    ['PUT', /^\/api\/despesas\/(\d+)$/, (m, corpo) => atualizarDespesa(Number(m[1]), corpo || {})],
    ['DELETE', /^\/api\/despesas\/(\d+)$/, (m) => excluirDespesa(Number(m[1]))],
    ['GET', /^\/api\/receitas\/realizadas\/?$/, (m, c, p) => receitas('realizadas', p)],
    ['GET', /^\/api\/receitas\/orcamento\/?$/, (m, c, p) => receitas('orcamentos', p)],
    ['GET', /^\/api\/receitas\/itens\/?$/, (m, c, p) => receitas('itens', p)],
    ['POST', /^\/api\/receitas\/realizadas(\/pontual)?\/?$/, async () => falha(RECEBER)],
    ['DELETE', /^\/api\/receitas\/realizadas\/(\d+)$/, async () => avisar('Recebimento: o estorno fica em Receitas, que registra o movimento de volta. Nada foi excluído.')],
    ['GET', /^\/api\/ir\//, async () => emMigracao('Documentos fiscais (A partir de documento)')],
    ['POST', /^\/api\/ir\//, async () => emMigracao('Documentos fiscais (A partir de documento)')],
];

async function adaptador({ metodo, caminho, parametros, corpo }) {
    const documento = await responderDocumentoFinanceiro({ metodo, caminho, parametros, corpo }, estado.perfilId, chaves);
    if (documento) return documento;
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                return falha(mensagemDeErro(erro), 400);
            }
        }
    }
    return emMigracao(`${metodo} ${caminho}`);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    // Quem so le o perfil ve os lancamentos, sem as acoes de escrita (o banco recusaria de qualquer forma).
    const { data: gere } = await supabase.rpc('pode_gerir_perfil', { p_perfil_id: estado.perfilId });
    document.body.classList.toggle('cf-somente-leitura', gere !== true);
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
