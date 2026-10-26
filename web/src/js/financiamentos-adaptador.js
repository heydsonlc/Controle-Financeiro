// FIN-FIDELIDADE-CONTRATOS-1 (fase 1) — adaptador da tela original de Financiamentos: responde as rotas /api/... que
// js/original/financiamentos.js chama (ponte-api.js), no formato do Flask. So consulta (migration 20261110090000): lista e
// detalhe com parcelas. Calculo (SAC, PRICE, SAC/TR, seguros, indexadores), cadastro, pagamento e estorno de parcelas,
// amortizacao, ajuste de saldo, simulacoes, documentos e conferencias continuam no Flask (escritor unico) nesta fase.

import { supabase } from './cliente.js';
import { falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };
const PARCELA_EM_DESPESAS = 'Esta parcela possui despesa vinculada. Use o fluxo de Despesas para registrar o pagamento ou o '
    + 'estorno: a parcela e o saldo devedor são atualizados junto. (Parcela sem despesa, de contrato antigo: continua no '
    + 'sistema atual.) Nada foi gravado.';
const NA_FASE_1 = 'Financiamentos: nesta fase o novo aplicativo só consulta contratos, parcelas e saldos. Esta ação continua no sistema atual. Nada foi gravado.';

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

async function listar(parametros) {
    const ativo = parametros.get('ativo');
    const lista = await rpc((a) => supabase.rpc('financiamentos_tela', a), {
        p_perfil_id: estado.perfilId, p_ativo: ativo === null ? null : String(ativo).toLowerCase() === 'true',
    });
    return ok({ data: lista || [], total: (lista || []).length });
}

async function detalhe(id) {
    return ok({ data: await rpc((a) => supabase.rpc('financiamento_tela', a), { p_perfil_id: estado.perfilId, p_financiamento_id: id }) });
}

async function contasBancarias() {
    const lista = await rpc((a) => supabase.rpc('contas_bancarias_tela', a), { p_perfil_id: estado.perfilId, p_status: 'ATIVO' });
    return ok({ data: lista || [], total: (lista || []).length });
}

const ROTAS = [
    ['GET', /^\/api\/financiamentos\/?$/, (m, c, p) => listar(p)],
    ['GET', /^\/api\/financiamentos\/(\d+)$/, (m) => detalhe(Number(m[1]))],
    ['GET', /^\/api\/contas\/?$/, () => contasBancarias()],
    // FIN-CONTRATOS-2: como no Flask (CORE-SALDO-1C), a parcela com despesa e paga e estornada em Despesas, onde o novo
    // aplicativo atualiza a parcela e o saldo devedor na mesma operacao. Parcela sem despesa (contrato antigo): pendente.
    ['POST', /^\/api\/financiamentos\/parcelas\/(\d+)\/(pagar|estornar-pagamento)$/, async () => falha(PARCELA_EM_DESPESAS, 409)],
];

async function adaptador({ metodo, caminho, parametros, corpo }) {
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
    return falha(NA_FASE_1, 501);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
