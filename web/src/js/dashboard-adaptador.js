// FIN-FIDELIDADE-CONSOLIDACAO-1 — adaptador do Dashboard Financeiro original (frontend/templates/index.html +
// js/original/dashboard.js): responde GET /api/dashboard/resumo (ponte-api.js) no formato do Flask, pela migration
// 20261114090000. O Dashboard so le. (Os links das "acoes rapidas" sao montados pelo JS do Flask com rotas do Flask:
// js/dashboard-adaptacoes.js os aponta para as paginas daqui.)
// D2 (FIN-AUDITORIA-GERAL-1): "Receitas previstas" e a previsao do mes, sem somar de novo o que dela ja foi recebido; o
// recebido e a diferenca da execucao aparecem logo abaixo (#flow-receitas-execucao), so leitura.
// FIN-CATEGORIAS-REORGANIZACAO-01: sob o total de saidas (o mesmo valor de "despesas previstas" do resumo, sem mudanca),
// uma linha compacta reparte esse total em consumo e aportes (#flow-saidas-naturezas). E so apresentacao: o total, o
// grafico e o saldo projetado continuam vindo de dashboard_resumo_tela. Se a reparticao nao estiver disponivel ou nao
// fechar com o total, a linha nao aparece.

import { supabase } from './cliente.js';
import { emMigracao, falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';
import { reparticaoDosIndicadores, textoDaReparticao } from './naturezas.js';
import { indicadoresDoMes } from './naturezas-servico.js';

const estado = { perfilId: null };

async function resumo(parametros) {
    const { data, error } = await supabase.rpc('dashboard_resumo_tela', {
        p_perfil_id: estado.perfilId, p_mes_referencia: parametros.get('mes_referencia') || parametros.get('periodo') || '',
    });
    if (error) throw error;
    const resumoFluxo = data && data.fluxo_caixa && data.fluxo_caixa.resumo;
    mostrarExecucao(resumoFluxo);
    mostrarNaturezas(data && data.periodo && data.periodo.mes_referencia, resumoFluxo);  // nao segura o resumo
    return ok({ data });
}

let pedidoNaturezas = 0;
async function mostrarNaturezas(mes, resumoFluxo) {
    const linha = document.getElementById('flow-saidas-naturezas');
    if (!linha) return;
    const pedido = ++pedidoNaturezas;
    linha.hidden = true;
    if (!mes || !resumoFluxo) return;
    const partes = reparticaoDosIndicadores(await indicadoresDoMes(estado.perfilId, mes), resumoFluxo.despesas_previstas);
    if (pedido !== pedidoNaturezas || !partes) return;  // trocaram de mes, ou a reparticao nao fecha com o total
    linha.textContent = textoDaReparticao(partes);
    linha.dataset.mes = mes;
    linha.hidden = false;
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
