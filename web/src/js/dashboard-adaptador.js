// FIN-FIDELIDADE-CONSOLIDACAO-1 — adaptador do Dashboard Financeiro original (frontend/templates/index.html +
// js/original/dashboard.js): responde GET /api/dashboard/resumo (ponte-api.js) no formato do Flask, pela migration
// 20261114090000. O Dashboard so le. (Os links das "acoes rapidas" sao montados pelo JS do Flask com rotas do Flask:
// js/dashboard-adaptacoes.js os aponta para as paginas daqui.)

import { supabase } from './cliente.js';
import { falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };

async function resumo(parametros) {
    const { data, error } = await supabase.rpc('dashboard_resumo_tela', {
        p_perfil_id: estado.perfilId, p_mes_referencia: parametros.get('mes_referencia') || parametros.get('periodo') || '',
    });
    if (error) throw error;
    return ok({ data });
}

async function adaptador({ metodo, caminho, parametros }) {
    if (metodo === 'GET' && /^\/api\/dashboard\/resumo$/.test(caminho)) {
        try {
            return await resumo(parametros);
        } catch (erro) {
            return falha(mensagemDeErro(erro), erro && erro.code === '42501' ? 403 : 400);
        }
    }
    return falha('Dashboard: esta consulta ainda não foi migrada. Continua no sistema atual.', 501);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
