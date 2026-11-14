// FIN-MVP-MOBILE-06 — abastecimento com a despesa (tela Lancamentos do desktop, FIN-MOB-ABAST-LANCAMENTOS-01): leituras do
// formulario e a gravacao por salvar_lancamento_abastecimento (uma transacao: a despesa, conta a pagar por criar_despesa ou
// compra a vista no cartao por criar_compra, e o abastecimento vinculado, validado pelas mesmas regras da Mobilidade;
// chave contra reenvio; abastecimento ja registrado na Mobilidade, sem despesa, e reaproveitado). Extraido de
// js/lancamentos-adaptador.js para servir, sem duplicar regra, a tela Lancamentos e o Registrar Lancamento mobile.
// Os litros sao calculados no banco (valor total / preco por litro). Nada novo no banco.

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok, valorTexto } from './adaptador-comum.js';
import { montarCompra, respostaDaCompra } from './compras-servico.js';
import { confirmacoes } from './fechamento.js';

const MES = /^\d{4}-(0[1-9]|1[0-2])/;

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

// Categoria Combustivel (pelo codigo MOB_COMBUSTIVEL, nunca pelo nome) e veiculos com o ultimo hodometro (sem eletricos).
export const formularioAbastecimento = (perfilId) => rpc((a) => supabase.rpc('formulario_abastecimento_lancamento', a), { p_perfil_id: perfilId });

// Cartoes fisicos do contrato (so o final de 4 digitos).
export const cartoesVinculados = (perfilId, contratoId) => rpc((a) => supabase.rpc('cartoes_vinculados', a),
    { p_perfil_id: perfilId, p_contrato_id: contratoId });

// Despesa direta (conta a pagar) como a tela Lancamentos a grava: pendente, sem conta bancaria (pagar fica em Despesas);
// competencia do formulario quando vier.
export function dadosDaDespesaDireta(corpo) {
    const dados = {
        nome: String(corpo.nome || '').trim(), valor: valorTexto(corpo.valor), descricao: String(corpo.descricao || '').trim(),
        categoria_id: corpo.categoria_id, data_vencimento: corpo.data_vencimento, debito_automatico: false, conta_bancaria_id: null,
    };
    if (MES.test(corpo.mes_competencia || '')) dados.competencia = `${String(corpo.mes_competencia).slice(0, 7)}-01`;
    return dados;
}

// A gravacao (a chave da operacao vem de quem chama: repetir nao duplica). Devolve {data} ou {error}.
export function gravarLancamentoAbastecimento(perfilId, dados, chave) {
    return supabase.rpc('salvar_lancamento_abastecimento', { p_perfil_id: perfilId, p_dados: dados, p_chave: chave });
}

// ---------------------------------------------------------------------------------------------------------------
// Rotas para as telas mobile (a tela Lancamentos do desktop usa as funcoes acima no seu adaptador)

const estado = { perfilId: null };
const chaves = criarChaves();

// corpo: {tipo: 'despesa' | 'compra', lancamento: o corpo da tela Lancamentos (despesa direta ou compra no cartao),
// abastecimento: {veiculo_id, combustivel, hodometro_km, preco_litro, cartao_vinculado_id?}}.
async function salvar(corpo) {
    const lancamento = corpo.lancamento || {};
    const abastecimento = corpo.abastecimento || {};
    if (!(Number(lancamento.valor) > 0)) return falha('Informe um valor válido.');
    if (corpo.tipo === 'compra') {
        const montada = montarCompra(Number(lancamento.cartao_id), { ...lancamento, total_parcelas: 1 });
        if (montada.erro) return falha(montada.erro);
        const { dados } = montada;
        const operacao = `compra-abastecimento:${JSON.stringify({ dados, abastecimento })}`;
        if (Array.isArray(lancamento.confirmar_consolidadas)) dados.confirmar_consolidadas = confirmacoes(lancamento.confirmar_consolidadas);
        const resultado = await gravarLancamentoAbastecimento(estado.perfilId, { lancamento: { tipo: 'compra', dados }, abastecimento },
            chaves.de(operacao));
        return respostaDaCompra(estado.perfilId, dados, resultado, () => chaves.esquecer(operacao));
    }
    if (corpo.tipo !== 'despesa') return falha('Tipo de lançamento inválido.');
    if (!lancamento.data_vencimento) return falha('Informe a data.');
    const dados = dadosDaDespesaDireta(lancamento);
    const operacao = `despesa-abastecimento:${JSON.stringify({ dados, abastecimento })}`;
    const { data, error } = await gravarLancamentoAbastecimento(estado.perfilId, { lancamento: { tipo: 'despesa', dados }, abastecimento },
        chaves.de(operacao));
    if (error) return falha(mensagemDeErro(error));
    chaves.esquecer(operacao);
    return { status: 201, corpo: { success: true, message: 'Despesa e abastecimento salvos com sucesso', data } };
}

const ROTAS = [
    ['GET', /^\/api\/lancamentos\/abastecimento\/formulario$/, async () => ok({ data: await formularioAbastecimento(estado.perfilId) })],
    ['GET', /^\/api\/cartoes\/(\d+)\/vinculados$/, async (m) => ok({ data: await cartoesVinculados(estado.perfilId, Number(m[1])) })],
    ['POST', /^\/api\/lancamentos\/abastecimento$/, (m, corpo) => salvar(corpo || {})],
];

// null quando a rota nao e do abastecimento.
export async function responderAbastecimento({ metodo, caminho, parametros, corpo }) {
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

export function configurarAbastecimento(perfilId) {
    estado.perfilId = perfilId;
}
