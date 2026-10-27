// FIN-FIDELIDADE-CONTRATOS-1 (fase 1) — adaptador da tela original de Financiamentos: responde as rotas /api/... que
// js/original/financiamentos.js chama (ponte-api.js), no formato do Flask. Consulta (migration 20261110090000): lista e
// detalhe com parcelas. FIN-FINANCIAMENTOS-MOTOR-1 (migration 20261123090000): motor SAC/TR da Caixa, SAC, PRICE e
// SIMPLES - cadastro, edicao, vigencias de seguro, amortizacao extraordinaria, ajuste de saldo, regeneracao, exclusao e
// simulacao de quitacao. Documentos e conferencias da Caixa continuam no Flask (escritor unico) nesta fase.

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };
const chaves = criarChaves();
const PARCELA_EM_DESPESAS = 'Esta parcela possui despesa vinculada. Use o fluxo de Despesas para registrar o pagamento ou o '
    + 'estorno: a parcela e o saldo devedor são atualizados junto. (Parcela sem despesa, de contrato antigo: continua no '
    + 'sistema atual.) Nada foi gravado.';
const NA_FASE_1 = 'Financiamentos: documentos e conferências da Caixa ainda não estão no novo aplicativo; esta ação continua no sistema atual. Nada foi gravado.';

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

function falhaFinanciamento(error) {
    if (error.hint === 'SISTEMA_FLASK') return falha('Os financiamentos deste perfil ainda são administrados pelo sistema atual (Flask). Nada foi gravado.', 409);
    if (error.hint === 'NAO_ENCONTRADO') return falha('Financiamento não encontrado', 404);
    return falha(mensagemDeErro(error), error.code === '42501' ? 403 : 400);
}

async function criar(corpo) {
    const { data, error } = await supabase.rpc('criar_financiamento', { p_perfil_id: estado.perfilId, p_dados: corpo, p_chave: chaves.de('criar') });
    if (error) return falhaFinanciamento(error);
    chaves.esquecer('criar');
    return { status: 201, corpo: data };
}

async function amortizar(id, corpo) {
    const operacao = `amortizar-${id}`;
    const { data, error } = await supabase.rpc('registrar_amortizacao_extra', {
        p_perfil_id: estado.perfilId, p_id: id, p_dados: corpo, p_chave: chaves.de(operacao),
    });
    if (error) return falhaFinanciamento(error);
    chaves.esquecer(operacao);
    return { status: 201, corpo: data };
}

async function atualizar(id, corpo) {
    const operacao = `atualizar-${id}`;
    const { data, error } = await supabase.rpc('atualizar_financiamento', {
        p_perfil_id: estado.perfilId, p_id: id, p_dados: corpo, p_chave: chaves.de(operacao),
    });
    if (error) return falhaFinanciamento(error);
    chaves.esquecer(operacao);
    return ok(data);
}

async function novaVigencia(id, corpo) {
    const operacao = `vigencia-${id}`;
    const { data, error } = await supabase.rpc('adicionar_vigencia_seguro', {
        p_perfil_id: estado.perfilId, p_id: id, p_dados: corpo, p_chave: chaves.de(operacao),
    });
    if (error) return falhaFinanciamento(error);
    chaves.esquecer(operacao);
    return { status: 201, corpo: data };
}

async function ajustarSaldo(id, corpo) {
    const operacao = `ajuste-${id}`;
    const { data, error } = await supabase.rpc('ajustar_saldo_devedor', {
        p_perfil_id: estado.perfilId, p_id: id, p_dados: corpo, p_chave: chaves.de(operacao),
    });
    if (error) {
        const resposta = falhaFinanciamento(error);
        resposta.corpo.message = resposta.corpo.error;  // o Flask devolve message e error neste erro
        return resposta;
    }
    chaves.esquecer(operacao);
    return ok(data);
}

async function simularQuitacao(id, corpo) {
    const { data, error } = await supabase.rpc('simular_quitacao', { p_perfil_id: estado.perfilId, p_id: id, p_dados: corpo });
    if (error) return falhaFinanciamento(error);
    return ok(data);
}

async function regenerar(id) {
    const { data, error } = await supabase.rpc('regenerar_parcelas_financiamento', { p_perfil_id: estado.perfilId, p_id: id });
    if (error) return falhaFinanciamento(error);
    return ok(data);
}

async function excluir(id) {
    const { data, error } = await supabase.rpc('excluir_financiamento', { p_perfil_id: estado.perfilId, p_id: id });
    if (error) return falhaFinanciamento(error);
    return ok(data);
}

const ROTAS = [
    ['GET', /^\/api\/financiamentos\/?$/, (m, c, p) => listar(p)],
    ['GET', /^\/api\/financiamentos\/(\d+)$/, (m) => detalhe(Number(m[1]))],
    ['GET', /^\/api\/contas\/?$/, () => contasBancarias()],
    ['POST', /^\/api\/financiamentos\/?$/, (m, c) => criar(c)],
    ['POST', /^\/api\/financiamentos\/(\d+)\/amortizacao-extra$/, (m, c) => amortizar(Number(m[1]), c)],
    ['POST', /^\/api\/financiamentos\/(\d+)\/regenerar-parcelas$/, (m) => regenerar(Number(m[1]))],
    ['DELETE', /^\/api\/financiamentos\/(\d+)$/, (m) => excluir(Number(m[1]))],
    ['PUT', /^\/api\/financiamentos\/(\d+)$/, (m, c) => atualizar(Number(m[1]), c)],
    ['POST', /^\/api\/financiamentos\/(\d+)\/vigencias-seguro$/, (m, c) => novaVigencia(Number(m[1]), c)],
    ['POST', /^\/api\/financiamentos\/(\d+)\/ajustar-saldo$/, (m, c) => ajustarSaldo(Number(m[1]), c)],
    ['POST', /^\/api\/financiamentos\/(\d+)\/simular-quitacao$/, (m, c) => simularQuitacao(Number(m[1]), c)],
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
