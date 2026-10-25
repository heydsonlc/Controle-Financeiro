// Perfil financeiro ativo (PERFIS-1) e gestao de perfis (FIN-MIGRACAO-FIDELIDADE-FASE-1).
//
// A lista vem de financeiro.meus_perfis(), que so devolve perfis ativos vinculados ao
// usuario logado. A escolha fica no navegador, por usuario, e vale para todas as abas
// (como a sessao do Flask), mas e so preferencia de tela: toda consulta passa o perfil
// ao banco, que revalida a autorizacao (financeiro.pode_acessar_perfil). Um id alterado
// manualmente aqui nao da acesso a nada.
//
// Gestao (tela Configuracoes): funcoes do banco que exigem gestao explicita do perfil
// (perfil_acesso.pode_gerir) e devolvem o perfil no formato do Flask (to_dict).

import { supabase } from './cliente.js';

const chave = (usuarioId) => `cf-perfil-ativo:${usuarioId}`;

export async function carregarPerfis() {
    const { data, error } = await supabase.rpc('meus_perfis');
    if (error) throw error;
    return data || [];
}

export function escolherPerfilAtivo(perfis, usuarioId) {
    let salvo = null;
    try {
        salvo = localStorage.getItem(chave(usuarioId));
    } catch (_erro) {
        salvo = null;
    }
    return perfis.find((p) => String(p.id) === salvo)
        || perfis.find((p) => p.padrao)
        || perfis[0]
        || null;
}

export function salvarPerfilAtivo(usuarioId, perfilId) {
    try {
        localStorage.setItem(chave(usuarioId), String(perfilId));
    } catch (_erro) {
        // Sem armazenamento: a escolha vale so ate recarregar a pagina.
    }
}

// Todos os perfis vinculados ao usuario, inclusive inativos, com papel e permissao de gestao.
export async function perfisParaConfiguracao() {
    const { data, error } = await supabase.rpc('perfis_para_configuracao');
    if (error) throw error;
    return data || [];
}

// dados: { nome, tipo, documento, avatar, cor, ativo, padrao }; o banco normaliza como o Flask.
export async function criarPerfil(dados) {
    const { data, error } = await supabase.rpc('criar_perfil', { p_dados: dados });
    if (error) throw error;
    return data;
}

// So nome, tipo, documento, avatar e cor; ativo e padrao tem chamadas proprias.
export async function atualizarPerfil(perfilId, dados) {
    const { data, error } = await supabase.rpc('atualizar_perfil', { p_perfil_id: perfilId, p_dados: dados });
    if (error) throw error;
    return data;
}

export async function inativarPerfil(perfilId) {
    const { data, error } = await supabase.rpc('inativar_perfil', { p_perfil_id: perfilId });
    if (error) throw error;
    return data;
}

export async function reativarPerfil(perfilId) {
    const { data, error } = await supabase.rpc('reativar_perfil', { p_perfil_id: perfilId });
    if (error) throw error;
    return data;
}

export async function definirPerfilPadrao(perfilId) {
    const { data, error } = await supabase.rpc('definir_perfil_padrao', { p_perfil_id: perfilId });
    if (error) throw error;
    return data;
}
