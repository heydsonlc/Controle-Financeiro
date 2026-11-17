// FIN-CATEGORIAS-REORGANIZACAO-01 — leituras da natureza gerencial (so leitura). As contas ficam em js/naturezas.js.
// Se a leitura falhar (funcao ainda nao publicada, rede), devolve null e a tela fica exatamente como era.

import { supabase } from './cliente.js';

let mapa = null;
// Mapa categoria -> natureza (uma leitura por pagina). null quando a leitura nao esta disponivel.
export async function carregarNaturezas() {
    if (mapa) return mapa;
    try {
        const { data, error } = await supabase.rpc('naturezas_das_categorias');
        if (error) throw error;
        mapa = new Map((data || []).map((c) => [Number(c.categoria_id), c.natureza]));
    } catch (erro) {
        console.warn('Naturezas das categorias indisponíveis:', erro && erro.message);
        return null;
    }
    return mapa;
}

export async function indicadoresDoMes(perfilId, mes) {
    try {
        const { data, error } = await supabase.rpc('indicadores_gerenciais', { p_perfil_id: perfilId, p_mes: mes });
        if (error) throw error;
        return data;
    } catch (erro) {
        console.warn('Indicadores gerenciais indisponíveis:', erro && erro.message);
        return null;
    }
}
