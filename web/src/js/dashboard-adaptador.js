// FIN-FIDELIDADE-CONSOLIDACAO-1 — adaptador do Dashboard Financeiro original (frontend/templates/index.html +
// js/original/dashboard.js): responde GET /api/dashboard/resumo (ponte-api.js) no formato do Flask, pela migration
// 20261114090000. O Dashboard so le. (Os links das "acoes rapidas" sao montados pelo JS do Flask com rotas do Flask:
// js/dashboard-adaptacoes.js os aponta para as paginas daqui.)
// D2 (FIN-AUDITORIA-GERAL-1): "Receitas previstas" e a previsao do mes, sem somar de novo o que dela ja foi recebido; o
// recebido e a diferenca da execucao aparecem logo abaixo (#flow-receitas-execucao), so leitura.

import { supabase } from './cliente.js';
import { emMigracao, falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };

async function resumo(parametros) {
    const { data, error } = await supabase.rpc('dashboard_resumo_tela', {
        p_perfil_id: estado.perfilId, p_mes_referencia: parametros.get('mes_referencia') || parametros.get('periodo') || '',
    });
    if (error) throw error;
    mostrarExecucao(data && data.fluxo_caixa && data.fluxo_caixa.resumo);
    return ok({ data });
}

const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

function mostrarExecucao(resumoFluxo) {
    const linha = document.getElementById('flow-receitas-execucao');
    if (!linha || !resumoFluxo || resumoFluxo.receitas_recebidas === undefined) return;
    const diferenca = Number(resumoFluxo.diferenca_receitas) || 0;
    document.getElementById('flow-receitas-recebidas').textContent = moeda.format(Number(resumoFluxo.receitas_recebidas) || 0);
    const campo = document.getElementById('flow-receitas-diferenca');
    campo.textContent = moeda.format(diferenca);
    campo.classList.toggle('negativa', diferenca < 0);
    linha.hidden = false;
}

async function adaptador({ metodo, caminho, parametros }) {
    if (metodo === 'GET' && /^\/api\/dashboard\/resumo$/.test(caminho)) {
        try {
            return await resumo(parametros);
        } catch (erro) {
            return falha(mensagemDeErro(erro), erro && erro.code === '42501' ? 403 : 400);
        }
    }
    return emMigracao('Dashboard: esta consulta');
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
