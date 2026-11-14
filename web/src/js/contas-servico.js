// FIN-MVP-MOBILE-06 — transferencia entre contas da tela Contas Bancarias do desktop (FIN-FIDELIDADE-MOVIMENTACOES-1):
// contas ativas do perfil e a gravacao por transferir_entre_contas (movimentos pareados de debito e credito, contas do
// perfil, ativas e diferentes, valor > 0, escritor unico de pagamentos, chave contra reenvio; o saldo e o dos movimentos).
// Extraido de js/contas-bancarias-adaptador.js para servir, sem duplicar regra, a tela Contas Bancarias e o Registrar
// Lancamento mobile. Nada novo no banco; nenhum saldo e alterado diretamente.

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok } from './adaptador-comum.js';

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

// Contas do perfil com o saldo pelos movimentos (status: ATIVO, INATIVO ou todas).
export const contasDoPerfil = (perfilId, status = null) => rpc((a) => supabase.rpc('contas_bancarias_tela', a),
    { p_perfil_id: perfilId, p_status: status });

// A gravacao (a chave da operacao vem de quem chama: repetir nao duplica). Lanca o erro do banco.
export const gravarTransferencia = (perfilId, dados, chave) => rpc((a) => supabase.rpc('transferir_entre_contas', a),
    { p_perfil_id: perfilId, p_dados: dados, p_chave: chave });

// ---------------------------------------------------------------------------------------------------------------
// Rotas para as telas mobile (a tela Contas Bancarias do desktop usa as funcoes acima no seu adaptador)

const estado = { perfilId: null };
const chaves = criarChaves();

// O mesmo corpo da tela Contas Bancarias (salvarTransferencia): origem, destino, valor, data e descricao.
async function transferir(corpo) {
    const operacao = `transferir:${JSON.stringify(corpo)}`;
    const r = await gravarTransferencia(estado.perfilId, corpo, chaves.de(operacao));
    chaves.esquecer(operacao);
    return { status: 201, corpo: { success: true, message: 'Transferência realizada',
        data: { transferencia_id: r.transferencia_id, debito: r.debito, credito: r.credito } } };
}

const ROTAS = [
    ['GET', /^\/api\/contas\/?$/, async (m, c, p) => {
        const contas = (await contasDoPerfil(estado.perfilId, p.get('status'))) || [];
        return ok({ data: contas, total: contas.length });
    }],
    ['POST', /^\/api\/contas\/transferir$/, (m, corpo) => transferir(corpo || {})],
];

// null quando a rota nao e de contas.
export async function responderContas({ metodo, caminho, parametros, corpo }) {
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

export function configurarContas(perfilId) {
    estado.perfilId = perfilId;
}
