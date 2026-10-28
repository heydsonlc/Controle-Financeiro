// FIN-PRE-PRODUCAO-1 (2.1) — adaptador da tela original de Indexadores (secao TR para financiamentos SAC/TR): responde
// as rotas /api/indexadores/tr... que js/original/indexadores.js chama (ponte-api.js), no formato do Flask
// (routes/indexadores.py), com as funcoes da migration 20261129090000.
//
// A TR e uma so para todos os perfis, como no Flask: consultar exige um perfil autorizado e gravar exige gerir um perfil
// ativo; a TR ja usada em parcela de financiamento SAC/TR nao muda (regra do Flask). Cadastro e importacao levam chave
// de idempotencia (reenvio nao duplica).

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';

const chaves = criarChaves();

function erroDoFlask(erro) {
    return falha(mensagemDeErro(erro), erro && erro.code === '42501' ? 403 : 400);
}

async function chamar(funcao) {
    const { data, error } = await funcao();
    if (error) throw error;
    return data;
}

async function listar(parametros) {
    const ano = Number.parseInt(parametros.get('ano'), 10);
    const items = await chamar(() => supabase.rpc('tr_oficial_tela', {
        p_ano: Number.isFinite(ano) ? ano : null, p_inicio: parametros.get('inicio'), p_fim: parametros.get('fim'),
    }));
    return ok({ items });
}

async function faltantes(parametros) {
    const lista = await chamar(() => supabase.rpc('tr_faltantes', { p_inicio: parametros.get('inicio'), p_fim: parametros.get('fim') }));
    return ok({ faltantes: lista });
}

async function criar(corpo) {
    const r = await chamar(() => supabase.rpc('criar_tr', { p_dados: corpo || {}, p_chave: chaves.de('criar_tr') }));
    chaves.esquecer('criar_tr');
    return { status: 201, corpo: { success: true, message: 'TR cadastrada com sucesso.', data: r.data } };
}

async function editar(competencia, corpo) {
    const r = await chamar(() => supabase.rpc('editar_tr', { p_competencia: decodeURIComponent(competencia), p_dados: corpo || {} }));
    return ok({ message: 'TR atualizada com sucesso.', data: r.data });
}

async function importar(corpo) {
    const r = await chamar(() => supabase.rpc('importar_tr', { p_dados: corpo || {}, p_chave: chaves.de('importar_tr') }));
    chaves.esquecer('importar_tr');
    return ok({ criados: r.criados, atualizados: r.atualizados, ignorados: r.ignorados, erros: r.erros });
}

const ROTAS = [
    ['GET', /^\/api\/indexadores\/tr$/, (m, c, p) => listar(p)],
    ['GET', /^\/api\/indexadores\/tr\/faltantes$/, (m, c, p) => faltantes(p)],
    ['POST', /^\/api\/indexadores\/tr$/, (m, c) => criar(c)],
    ['POST', /^\/api\/indexadores\/tr\/importar$/, (m, c) => importar(c)],
    ['PUT', /^\/api\/indexadores\/tr\/([^/]+)$/, (m, c) => editar(m[1], c)],
];

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                return erroDoFlask(erro);
            }
        }
    }
    return falha('Indexadores: só a TR para financiamentos SAC/TR está disponível no novo aplicativo. Nada foi gravado.', 501);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
