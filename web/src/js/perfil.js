// Perfil financeiro ativo (PERFIS-1).
//
// A lista vem de financeiro.meus_perfis(), que so devolve perfis vinculados ao
// usuario logado. A escolha fica na sessao do navegador, por usuario, mas e so
// preferencia de tela: toda consulta passa o perfil ao banco, que revalida a
// autorizacao (financeiro.pode_acessar_perfil). Um id alterado manualmente aqui
// nao da acesso a nada.

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
        salvo = sessionStorage.getItem(chave(usuarioId));
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
        sessionStorage.setItem(chave(usuarioId), String(perfilId));
    } catch (_erro) {
        // Sem armazenamento: a escolha vale so ate recarregar a pagina.
    }
}
