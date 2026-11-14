// FIN-MVP-MOBILE-05 — compra no cartao do desktop (tela Lancamentos, "Compra no cartao"): leituras do formulario e
// gravacao por criar_compra, extraidas de js/lancamentos-adaptador.js para servir, sem duplicar regra, a tela
// Lancamentos do desktop, a Nova Despesa mobile e o futuro Registrar Lancamento (FIN-MVP-MOBILE-06). Nada novo no banco:
// as mesmas funcoes (cartoes_do_perfil, sugerir_competencia, previa_compra, criar_compra), as mesmas validacoes e a mesma
// confirmacao de fatura consolidada (409 CONFIRMAR_FATURA_CONSOLIDADA, como no Flask). A compra entra na fatura do cartao
// (garantir_fatura no banco); nenhuma conta a pagar e criada: a fatura e a unica conta na Lista de Despesas.

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok, valorTexto } from './adaptador-comum.js';
import { confirmacoes, consolidadaDoErro } from './fechamento.js';

const MES = /^\d{4}-(0[1-9]|1[0-2])/;

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

// Cartoes ativos do perfil, no formato do Flask (GET /api/cartoes).
export async function cartoesAtivos(perfilId) {
    const lista = await rpc((a) => supabase.rpc('cartoes_do_perfil', a), { p_perfil_id: perfilId });
    return (lista || []).filter((c) => c.ativo).map((c) => ({ id: c.id, nome: c.nome, tipo: 'Agregador', ativo: true }));
}

// Fatura sugerida pelo fechamento do cartao (calculada no banco).
export function competenciaSugerida(perfilId, cartaoId, dataCompra) {
    return rpc((a) => supabase.rpc('sugerir_competencia', a), { p_perfil_id: perfilId, p_cartao_id: cartaoId, p_data_compra: dataCompra });
}

// FIN-MVP-LANCAMENTOS-03 (P14): previa das parcelas pelo mesmo plano que criar_compra grava.
// Descricao e categoria nao mudam as parcelas (valores e faturas), so a validacao: ainda vazias no formulario, a previa usa
// um texto provisorio e a primeira categoria ativa; ao salvar valem as do formulario, como sempre.
export async function previaParcelas(perfilId, p) {
    let categoria = Number(p.get('categoria_id')) || null;
    if (!categoria) categoria = ((await rpc((a) => supabase.rpc('categorias_de_despesa', a), {})) || [])[0]?.id || null;
    const dados = { cartao_id: Number(p.get('cartao_id')), valor: valorTexto(Number(p.get('valor'))), total_parcelas: Number(p.get('total_parcelas')) || 1,
        data_compra: p.get('data_compra'), mes_fatura: p.get('mes_fatura'), categoria_id: categoria,
        descricao: String(p.get('descricao') || '').trim().slice(0, 200) || 'Prévia das parcelas' };
    if (!(dados.cartao_id > 0) || !MES.test(String(dados.mes_fatura || ''))) return falha('Escolha o cartão e o mês da fatura.');
    const { data, error } = await supabase.rpc('previa_compra', { p_perfil_id: perfilId, p_dados: dados });
    if (error) return falha(mensagemDeErro(error));
    return ok({ data });
}

// Dados da compra a partir do corpo do formulario (POST /api/cartoes/:id/lancamentos), com as validacoes de antes.
export function montarCompra(cartaoId, corpo) {
    const valor = Number(corpo.valor);
    if (!(valor > 0)) return { erro: 'Informe um valor válido.' };
    if (!MES.test(String(corpo.mes_fatura || ''))) return { erro: 'Escolha o mês da fatura' };
    return { dados: {
        cartao_id: cartaoId, descricao: String(corpo.descricao || '').trim(), valor: valorTexto(valor),
        total_parcelas: Number(corpo.total_parcelas) || 1, data_compra: corpo.data_compra,
        mes_fatura: `${String(corpo.mes_fatura).slice(0, 7)}-01`, categoria_id: Number(corpo.categoria_id),
        observacoes: String(corpo.observacoes || '').trim(),
    } };
}

// A gravacao da compra (a chave da operacao vem de quem chama: repetir nao duplica).
export function gravarCompra(perfilId, dados, chave) {
    return supabase.rpc('criar_compra', { p_perfil_id: perfilId, p_dados: dados, p_chave: chave });
}

// Resposta no formato do Flask; fatura consolidada: a mesma pergunta (409), com os totais da previa do banco.
// `esquecer` libera a chave da operacao so depois do sucesso.
export async function respostaDaCompra(perfilId, dados, { data, error }, esquecer) {
    if (error) {
        if (consolidadaDoErro(error)) {
            const previa = await supabase.rpc('previa_compra', { p_perfil_id: perfilId, p_dados: { ...dados, confirmar_consolidadas: undefined } });
            if (previa.error) return falha(mensagemDeErro(previa.error));
            return { status: 409, corpo: { success: false, codigo: 'CONFIRMAR_FATURA_CONSOLIDADA', faturas: previa.data.consolidadas || [],
                error: 'A compra entra em fatura já consolidada: confirme a inclusão.' } };
        }
        return falha(mensagemDeErro(error));
    }
    esquecer();
    return { status: 201, corpo: { success: true, data } };
}

// ---------------------------------------------------------------------------------------------------------------
// Rotas para as telas mobile (a tela Lancamentos do desktop usa as funcoes acima no seu adaptador)

const estado = { perfilId: null };
const chaves = criarChaves();

async function criarCompra(cartaoId, corpo) {
    const montada = montarCompra(cartaoId, corpo);
    if (montada.erro) return falha(montada.erro);
    const { dados } = montada;
    const operacao = `compra:${JSON.stringify(dados)}`;
    if (Array.isArray(corpo.confirmar_consolidadas)) dados.confirmar_consolidadas = confirmacoes(corpo.confirmar_consolidadas);
    const resultado = await gravarCompra(estado.perfilId, dados, chaves.de(operacao));
    return respostaDaCompra(estado.perfilId, dados, resultado, () => chaves.esquecer(operacao));
}

const ROTAS = [
    ['GET', /^\/api\/cartoes\/?$/, async () => ({ status: 200, corpo: await cartoesAtivos(estado.perfilId) })],
    ['GET', /^\/api\/cartoes\/(\d+)\/competencia-sugerida$/, async (m, c, p) => ({ status: 200,
        corpo: await competenciaSugerida(estado.perfilId, Number(m[1]), p.get('data')) })],
    ['GET', /^\/api\/lancamentos\/previa-parcelas$/, (m, c, p) => previaParcelas(estado.perfilId, p)],
    ['POST', /^\/api\/cartoes\/(\d+)\/lancamentos$/, (m, corpo) => criarCompra(Number(m[1]), corpo || {})],
];

// null quando a rota nao e de compra no cartao.
export async function responderCompras({ metodo, caminho, parametros, corpo }) {
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
    return null;
}

export function configurarCompras(perfilId) {
    estado.perfilId = perfilId;
}
