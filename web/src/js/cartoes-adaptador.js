// FIN-FIDELIDADE-CARTOES-1 — adaptador da tela original de Cartoes: responde as rotas /api/... que
// js/original/cartoes.js chama (ponte-api.js), no formato do Flask, com as funcoes do Supabase (20261104090000 e
// FIN-CARTOES-1). Regras no banco: gestao do perfil, cartao e limite do perfil, versao contra edicao concorrente,
// travas cartao -> faturas -> parcelas, fatura paga/fechada e parcela de recorrencia protegidas.
// Diferencas assumidas em relacao ao Flask (docs/FIN_FIDELIDADE_CARTOES_1.md):
// - numero completo, validade e CVV: nunca enviados nem guardados (os campos ficam desativados);
// - editar um lancamento nao troca o numero nem o total de parcelas; excluir uma parcela exclui as parcelas abertas
//   da compra, depois de uma segunda confirmacao com as quantidades (as de fatura paga ou fechada ficam);
// - compra nova: o formulario do novo aplicativo (compra-cartao.js), no modal acrescentado; no Flask fica em Lancamentos.

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok, valorTexto } from './adaptador-comum.js';
import { abrirNovaCompra } from './compra-cartao.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null, cartoes: [], versoesCartao: {}, versoesLancamento: {}, versoesParcelamento: {} };
const chaves = criarChaves();
const MES = /^\d{4}-(0[1-9]|1[0-2])$/;
const SENSIVEIS = ['numero_cartao', 'data_validade', 'codigo_seguranca'];

const numero = (v) => (v === null || v === undefined ? null : Number(v));
const mesDe = (parametros) => {
    const mes = String(parametros.get('mes_referencia') || '').slice(0, 7);
    return MES.test(mes) ? `${mes}-01` : null;
};

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

// ---------------------------------------------------------------------------------------------------------------
// Cartoes
// ---------------------------------------------------------------------------------------------------------------

function cartaoDoFlask(c) {
    return {
        id: c.id,
        nome: c.nome,
        descricao: c.descricao,
        tipo: 'Agregador',
        ativo: c.ativo,
        // Cartao sem configuracao (dias nao cadastrados): sem config, como o Flask (to_dict sem config_agregador).
        config: c.dia_fechamento === null && c.dia_vencimento === null ? null : {
            dia_fechamento: c.dia_fechamento,
            dia_vencimento: c.dia_vencimento,
            limite_credito: numero(c.limite_credito),
            // So o final (os 4 ultimos digitos, quando houver): e o que a lista e o detalhe originais mostram.
            numero_cartao: c.final_numero || null,
            data_validade: null,
            tem_codigo: c.tem_codigo,
            possui_cvv: false,
            observacoes: c.observacoes,
            compra_no_fechamento: c.compra_no_fechamento,
            fechamento_confirmado: c.fechamento_confirmado,
            fechamento_configuravel: true,
        },
    };
}

async function listarCartoes() {
    const lista = await rpc((a) => supabase.rpc('cartoes_da_tela', a), { p_perfil_id: estado.perfilId });
    estado.cartoes = lista || [];
    estado.versoesCartao = Object.fromEntries(estado.cartoes.map((c) => [c.id, c.versao]));
    // Como GET /api/cartoes do Flask: so os ativos (o inativado sai da tela; compras e faturas continuam).
    return ok({ data: estado.cartoes.filter((c) => c.ativo).map(cartaoDoFlask) });
}

function dadosDoCartao(corpo) {
    if (SENSIVEIS.some((campo) => corpo[campo] !== null && corpo[campo] !== undefined && String(corpo[campo]).trim() !== '')) {
        return { recusa: 'Número completo, validade e código de segurança não são guardados no novo aplicativo.' };
    }
    const dados = {
        nome: String(corpo.nome || '').trim(),
        descricao: String(corpo.descricao || '').trim(),
        dia_fechamento: corpo.dia_fechamento,
        dia_vencimento: corpo.dia_vencimento,
        limite_credito: corpo.limite_credito === null || corpo.limite_credito === undefined || corpo.limite_credito === ''
            ? null : valorTexto(corpo.limite_credito),
        observacoes: String(corpo.observacoes || ''),
    };
    if (typeof corpo.tem_codigo === 'boolean') dados.tem_codigo = corpo.tem_codigo;
    if (corpo.compra_no_fechamento) dados.compra_no_fechamento = corpo.compra_no_fechamento;
    if (typeof corpo.fechamento_confirmado === 'boolean') dados.fechamento_confirmado = corpo.fechamento_confirmado;
    return { dados };
}

async function criarCartao(corpo) {
    const { recusa, dados } = dadosDoCartao(corpo);
    if (recusa) return falha(recusa);
    const operacao = `criar_cartao:${JSON.stringify(dados)}`;
    const { data, error } = await supabase.rpc('criar_cartao', { p_perfil_id: estado.perfilId, p_dados: dados, p_chave: chaves.de(operacao) });
    if (error) return falha(mensagemDeErro(error));
    chaves.esquecer(operacao);
    return { status: 201, corpo: { success: true, id: data.cartao_id } };
}

async function editarCartao(id, corpo) {
    const { recusa, dados } = dadosDoCartao(corpo);
    if (recusa) return falha(recusa);
    const { error } = await supabase.rpc('editar_cartao', {
        p_perfil_id: estado.perfilId, p_cartao_id: id, p_versao: estado.versoesCartao[id] || null, p_dados: dados,
    });
    if (error) return falha(mensagemDeErro(error));
    return ok({ id });
}

async function inativarCartao(id) {
    const { error } = await supabase.rpc('inativar_cartao', {
        p_perfil_id: estado.perfilId, p_cartao_id: id, p_versao: estado.versoesCartao[id] || null,
    });
    if (error) return falha(mensagemDeErro(error));
    return ok({ mensagem: 'Cartão inativado' });
}

// ---------------------------------------------------------------------------------------------------------------
// Categorias do Cartao e limites
// ---------------------------------------------------------------------------------------------------------------

async function categoriasCartao(parametros) {
    const lista = await rpc((a) => supabase.rpc('categorias_cartao_do_perfil', a), { p_perfil_id: estado.perfilId });
    const ativo = parametros.get('ativo');
    return ok({ data: (lista || []).filter((c) => ativo === null || String(c.ativo) === ativo)
        .map((c) => ({ id: c.id, nome: c.nome, descricao: c.descricao, cor: c.cor, icone: c.icone, ativo: c.ativo })) });
}

async function categoriasDespesa() {
    const { data, error } = await supabase.rpc('categorias_de_despesa');
    if (error) return falha(mensagemDeErro(error));
    return ok({ data: (data || []).map((c) => ({ id: c.id, nome: c.nome, cor: c.cor, ativo: true })) });
}

async function limites(cartaoId, parametros) {
    const mes = mesDe(parametros);
    if (!mes) return falha('mes_referencia invalido. Use YYYY-MM');
    const lista = await rpc((a) => supabase.rpc('limites_do_cartao', a), { p_perfil_id: estado.perfilId, p_cartao_id: cartaoId, p_mes: mes });
    return ok({ data: (lista || []).map((l) => ({
        id: l.id, cartao_id: l.cartao_id, categoria_cartao_id: l.categoria_cartao_id, categoria_cartao_nome: l.categoria_cartao_nome,
        limite_mensal: numero(l.limite_mensal), ativo: l.ativo, gasto_atual: numero(l.gasto_atual), disponivel: numero(l.disponivel),
        percentual_utilizado: numero(l.percentual_utilizado), mes_referencia: mes.slice(0, 7),
    })) });
}

const limiteTexto = (v) => (v === null || v === undefined || v === '' ? '' : String(v));

async function vincular(cartaoId, corpo) {
    const { data, error } = await supabase.rpc('vincular_limite_cartao', {
        p_perfil_id: estado.perfilId, p_cartao_id: cartaoId,
        p_dados: { categoria_cartao_id: corpo.categoria_cartao_id, limite_mensal: limiteTexto(corpo.limite_mensal), ativo: corpo.ativo !== false },
    });
    if (error) return falha(mensagemDeErro(error));
    return { status: data.criado ? 201 : 200, corpo: { success: true, data: { id: data.limite_id }, created: data.criado } };
}

async function atualizarLimite(cartaoId, limiteId, corpo) {
    const dados = {};
    if (corpo.limite_mensal !== undefined && corpo.limite_mensal !== null) dados.limite_mensal = limiteTexto(corpo.limite_mensal);
    if (typeof corpo.ativo === 'boolean') dados.ativo = corpo.ativo;
    const { error } = await supabase.rpc('atualizar_limite_cartao', {
        p_perfil_id: estado.perfilId, p_cartao_id: cartaoId, p_limite_id: limiteId, p_dados: dados,
    });
    if (error) return falha(mensagemDeErro(error));
    return ok({ data: { id: limiteId } });
}

async function desativarLimite(cartaoId, limiteId) {
    const { error } = await supabase.rpc('desativar_limite_cartao', { p_perfil_id: estado.perfilId, p_cartao_id: cartaoId, p_limite_id: limiteId });
    if (error) return falha(mensagemDeErro(error));
    return ok({ data: { id: limiteId, ativo: false } });
}

// ---------------------------------------------------------------------------------------------------------------
// Fatura por Categoria do Cartao e lancamentos
// ---------------------------------------------------------------------------------------------------------------

async function faturaCategorias(cartaoId, parametros) {
    const mes = mesDe(parametros);
    if (!mes) return falha('mes_referencia invalido. Use YYYY-MM');
    const data = await rpc((a) => supabase.rpc('fatura_por_categoria', a), { p_perfil_id: estado.perfilId, p_cartao_id: cartaoId, p_mes: mes });
    return ok({ data });
}

async function faturaLancamentos(cartaoId, parametros) {
    const mes = mesDe(parametros);
    if (!mes) return falha('mes_referencia invalido. Use YYYY-MM');
    const data = await rpc((a) => supabase.rpc('lancamentos_fatura_por_categoria', a), {
        p_perfil_id: estado.perfilId, p_cartao_id: cartaoId, p_mes: mes, p_filtro: parametros.get('categoria_cartao_id') || 'todos',
    });
    for (const l of data.lancamentos) estado.versoesLancamento[l.id] = l.versao;
    return ok({ data });
}

async function editarLancamento(id, corpo) {
    const dados = {
        descricao: String(corpo.descricao || '').trim(),
        valor: valorTexto(corpo.valor),
        data_compra: corpo.data_compra,
        numero_parcela: corpo.numero_parcela,
        total_parcelas: corpo.total_parcelas,
    };
    if (corpo.categoria_id) dados.categoria_id = Number(corpo.categoria_id);
    const { error } = await supabase.rpc('editar_lancamento_cartao', {
        p_perfil_id: estado.perfilId, p_lancamento_id: id, p_versao: estado.versoesLancamento[id] || null, p_dados: dados,
    });
    if (error) return falha(mensagemDeErro(error));
    return ok({ id });
}

// Excluir: a compra a vista sai; da parcelada saem as parcelas em fatura aberta (regra do FIN-CARTOES-1), com a
// segunda confirmacao dizendo quantas saem e quantas ficam. A versao e a da lista que o usuario viu.
async function excluirLancamento(id) {
    const { data, error } = await supabase.rpc('compra_para_edicao', { p_perfil_id: estado.perfilId, p_lancamento_id: id });
    if (error) return falha(mensagemDeErro(error));
    const versao = estado.versoesLancamento[id] || null;
    if (data.parcelas.length > 1) {
        const ficam = data.parcelas.length - data.abertas;
        const texto = `Esta compra é parcelada (${data.parcelas.length} parcelas). Serão excluídas as ${data.abertas} parcelas em fatura aberta`
            + (ficam ? `; ${ficam} em fatura paga ou fechada ficam (para corrigi-las é preciso estorno).` : '.')
            + '\nPara manter as parcelas atuais e remover só as próximas, use "Gerenciar parcelamento".';
        if (!window.confirm(texto)) return falha('Exclusão cancelada. Nada foi excluído.', 409);
    }
    const resposta = await supabase.rpc('excluir_compra', { p_perfil_id: estado.perfilId, p_lancamento_id: id, p_versao: versao });
    if (resposta.error) return falha(mensagemDeErro(resposta.error));
    return ok({ mensagem: 'Lançamento excluído com sucesso', excluidas: resposta.data.excluidas });
}

// ---------------------------------------------------------------------------------------------------------------
// Parcelamento
// ---------------------------------------------------------------------------------------------------------------

async function consultarParcelamento(id) {
    const data = await rpc((a) => supabase.rpc('parcelamento_da_compra', a), { p_perfil_id: estado.perfilId, p_lancamento_id: id });
    estado.versoesParcelamento[id] = data.versao;
    return data;
}

async function parcelamento(id) {
    try {
        return ok({ data: await consultarParcelamento(id) });
    } catch (erro) {
        return falha(mensagemDeErro(erro));
    }
}

async function parcelasFuturas(id, corpo) {
    const { data, error } = await supabase.rpc('editar_parcelas_futuras', {
        p_perfil_id: estado.perfilId, p_lancamento_id: id, p_versao: estado.versoesParcelamento[id] || null,
        p_dados: { descricao: corpo.descricao || '', categoria_id: corpo.categoria_id || '', valor: corpo.valor ? valorTexto(corpo.valor) : '' },
    });
    if (error) return falha(mensagemDeErro(error));
    return ok({ data: { ...data, parcelamento: await consultarParcelamento(id) }, message: 'Parcelas futuras atualizadas com sucesso' });
}

async function cancelarFuturas(id) {
    const { data, error } = await supabase.rpc('cancelar_parcelas_futuras', {
        p_perfil_id: estado.perfilId, p_lancamento_id: id, p_versao: estado.versoesParcelamento[id] || null,
    });
    if (error) return falha(mensagemDeErro(error));
    return ok({ data: { ...data, parcelamento: await consultarParcelamento(id) }, message: 'Parcelas futuras canceladas com sucesso' });
}

const ROTAS = [
    ['GET', /^\/api\/cartoes\/?$/, () => listarCartoes()],
    ['POST', /^\/api\/cartoes\/?$/, (m, corpo) => criarCartao(corpo || {})],
    ['PUT', /^\/api\/cartoes\/(\d+)$/, (m, corpo) => editarCartao(Number(m[1]), corpo || {})],
    ['DELETE', /^\/api\/cartoes\/(\d+)$/, (m) => inativarCartao(Number(m[1]))],
    [null, /^\/api\/cartoes\/\d+\/codigo-seguranca$/,
        async () => falha('O código de segurança não é guardado no novo aplicativo.', 410)],
    ['GET', /^\/api\/categorias-cartao\/?$/, (m, c, p) => categoriasCartao(p)],
    ['GET', /^\/api\/categorias\/?$/, () => categoriasDespesa()],
    ['GET', /^\/api\/cartoes\/(\d+)\/categorias-limite$/, (m, c, p) => limites(Number(m[1]), p)],
    ['POST', /^\/api\/cartoes\/(\d+)\/categorias-limite$/, (m, corpo) => vincular(Number(m[1]), corpo || {})],
    ['PUT', /^\/api\/cartoes\/(\d+)\/categorias-limite\/(\d+)$/, (m, corpo) => atualizarLimite(Number(m[1]), Number(m[2]), corpo || {})],
    ['DELETE', /^\/api\/cartoes\/(\d+)\/categorias-limite\/(\d+)$/, (m) => desativarLimite(Number(m[1]), Number(m[2]))],
    ['GET', /^\/api\/cartoes\/(\d+)\/fatura-categorias$/, (m, c, p) => faturaCategorias(Number(m[1]), p)],
    ['GET', /^\/api\/cartoes\/(\d+)\/fatura-lancamentos$/, (m, c, p) => faturaLancamentos(Number(m[1]), p)],
    ['PUT', /^\/api\/cartoes\/lancamentos\/(\d+)$/, (m, corpo) => editarLancamento(Number(m[1]), corpo || {})],
    ['DELETE', /^\/api\/cartoes\/lancamentos\/(\d+)$/, (m) => excluirLancamento(Number(m[1]))],
    ['GET', /^\/api\/cartoes\/lancamentos\/(\d+)\/parcelamento$/, (m) => parcelamento(Number(m[1]))],
    ['PUT', /^\/api\/cartoes\/lancamentos\/(\d+)\/parcelamento\/futuras$/, (m, corpo) => parcelasFuturas(Number(m[1]), corpo || {})],
    ['POST', /^\/api\/cartoes\/lancamentos\/(\d+)\/parcelamento\/cancelar-futuras$/, (m) => cancelarFuturas(Number(m[1]))],
];

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && (!verbo || verbo === metodo)) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                return falha(mensagemDeErro(erro), 500);
            }
        }
    }
    return falha(`${metodo} ${caminho}: em migração para o novo aplicativo. Até lá, continua no sistema atual.`, 501);
}

// Compra nova (acrescimo): o formulario do novo aplicativo no modal; ao gravar, a tela original recarrega.
function prepararNovaCompra(podeGerir) {
    const botao = document.getElementById('btn-nova-compra-cartao');
    botao.hidden = !podeGerir;
    botao.addEventListener('click', () => {
        const cartoes = estado.cartoes.filter((c) => c.ativo && c.dia_vencimento);
        if (!cartoes.length) {
            window.mostrarErro('Cadastre um cartão com dia de vencimento antes de lançar compras.');
            return;
        }
        const modal = document.getElementById('modal-nova-compra');
        modal.classList.add('open');
        abrirNovaCompra({
            painel: document.getElementById('cartao-painel'),
            perfilId: estado.perfilId,
            cartoes,
            cartaoId: window.CF_CARTOES.cartaoSelecionadoId(),
            mes: window.CF_CARTOES.mes(),
            aoFechar: () => modal.classList.remove('open'),
            aoGravar: async (mensagem) => {
                await window.carregarTelaCartoes();
                window.mostrarSucesso(mensagem);
            },
        });
    });
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    // Quem so le o perfil ve cartoes, limites e faturas, sem as acoes de escrita (o banco recusaria de qualquer forma).
    const { data: gere } = await supabase.rpc('pode_gerir_perfil', { p_perfil_id: estado.perfilId });
    document.body.classList.toggle('cf-somente-leitura', !gere);
    prepararNovaCompra(gere === true);
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
