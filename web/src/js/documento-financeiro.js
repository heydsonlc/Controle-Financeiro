// FIN-PRE-PRODUCAO-1 (2.2) — documento fiscal -> despesa/lancamento, comum as telas originais de Documentos Fiscais
// (imposto_renda.js: "Gerar financeiro"), Despesas e Lancamentos (despesas.js e lancamentos.js: "A partir de documento").
// Responde, no formato do Flask (routes/ir.py), as rotas que as tres telas chamam:
// - GET  /api/ir/comprovantes/documentos-para-financeiro (lista do perfil; ?sem_vinculo=true so os sem vinculo ativo);
// - GET  /api/ir/comprovantes/<id>/sugestao-financeira (migration 20261130090000);
// - POST /api/ir/comprovantes/<id>/criar-financeiro (migration 20261128090000: escritor unico do perfil, o mesmo documento
//   nao gera duas despesas, pagamento pela conta pelo motor de pagamento, no cartao pelo motor de compras).
// Devolve null quando a rota nao e uma destas (o adaptador da tela segue com as proprias).

import { supabase } from './cliente.js';
import { falha, mensagemDeErro, ok, PERFIL_NAO_HABILITADO } from './adaptador-comum.js';

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

export function erroDeDocumento(erro) {
    if (erro && erro.hint === 'SISTEMA_FLASK') {
        return falha(PERFIL_NAO_HABILITADO, 409);
    }
    if (erro && erro.hint === 'NAO_ENCONTRADA') return falha(mensagemDeErro(erro), 404);
    return falha(mensagemDeErro(erro), erro && erro.code === '42501' ? 403 : 400);
}

export const comprovanteDoPerfil = (perfilId, id) => rpc((a) => supabase.rpc('ir_comprovantes_tela', a), {
    p_perfil_id: perfilId, p_filtros: {}, p_id: id,
});

async function documentosParaFinanceiro(perfilId, parametros) {
    const r = await rpc((a) => supabase.rpc('ir_comprovantes_tela', a), {
        p_perfil_id: perfilId, p_filtros: Object.fromEntries(parametros.entries()), p_id: null,
    });
    const semVinculo = String(parametros.get('sem_vinculo') || 'false').trim().toLowerCase() === 'true';
    const dados = (r.data || []).filter((c) => !semVinculo || !c.vinculos_count).map((c) => ({
        id: c.id,
        prestador_nome: c.prestador_nome,
        prestador_cpf_cnpj: c.prestador_cpf_cnpj,
        data_documento: c.data_documento,
        valor: c.valor === null || c.valor === undefined ? null : Number(c.valor),
        status: c.status,
        categoria_nome: c.categoria_nome,
        arquivo_nome: c.arquivo ? c.arquivo.nome_arquivo : null,
        vinculos_count: c.vinculos_count,
    }));
    const destino = String(parametros.get('destino') || '').trim().toUpperCase();
    return ok({ data: dados, total: dados.length, destino: destino || null });
}

async function sugestao(perfilId, id) {
    return ok({ data: await rpc((a) => supabase.rpc('sugestao_financeira_documento_tela', a), { p_perfil_id: perfilId, p_comprovante_id: id }) });
}

async function criarFinanceiro(perfilId, chaves, id, corpo) {
    const operacao = `financeiro:${id}:${JSON.stringify(corpo || {})}`;
    const r = await rpc((a) => supabase.rpc('criar_financeiro_documento', a), {
        p_perfil_id: perfilId, p_comprovante_id: id, p_dados: corpo || {}, p_chave: chaves.de(operacao),
    });
    chaves.esquecer(operacao);
    return { status: 201, corpo: { success: true, data: { ...r, comprovante: await comprovanteDoPerfil(perfilId, id) } } };
}

const ROTAS = [
    ['GET', /^\/api\/ir\/comprovantes\/documentos-para-financeiro$/, (perfil, chaves, m, p) => documentosParaFinanceiro(perfil, p)],
    ['GET', /^\/api\/ir\/comprovantes\/(\d+)\/sugestao-financeira$/, (perfil, chaves, m) => sugestao(perfil, Number(m[1]))],
    ['POST', /^\/api\/ir\/comprovantes\/(\d+)\/criar-financeiro$/, (perfil, chaves, m, p, c) => criarFinanceiro(perfil, chaves, Number(m[1]), c)],
];

export async function responderDocumentoFinanceiro({ metodo, caminho, parametros, corpo }, perfilId, chaves) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(perfilId, chaves, m, parametros, corpo);
            } catch (erro) {
                return erroDeDocumento(erro);
            }
        }
    }
    return null;
}
