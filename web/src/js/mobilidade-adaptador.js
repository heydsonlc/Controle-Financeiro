// FIN-FIDELIDADE-PATRIMONIO-1 (Mobilidade, fase 1) — adaptador da tela original de Mobilidade: responde as rotas
// /api/... que js/original/veiculos.js chama (ponte-api.js), no formato do Flask. So consulta (migration 20261115090000):
// veiculos, projecoes ja geradas, uso, regras e estimativas de manutencao por km, financiamento do veiculo, modalidade
// ativa, assinaturas, caminhos de transporte por app e categorias. Cadastro, edicao, geracao de projecoes, ativacao de
// modalidade (inclusive a pre-visualizacao, que no Flask cria categorias), financiamento e confirmacao/adiamento de
// despesas previstas continuam no Flask (escritor unico) nesta fase.

import { supabase } from './cliente.js';
import { falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };
const NA_FASE_1 = 'Mobilidade: nesta fase o novo aplicativo só consulta veículos, projeções, uso e manutenções. Esta ação continua no sistema atual. Nada foi gravado.';

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

// request.args.get(nome, default, type=int) do Flask: valor invalido vale o padrao.
function inteiro(parametros, nome, padrao) {
    const valor = (parametros.get(nome) || '').trim();
    return /^[+-]?\d+$/.test(valor) ? Number(valor) : padrao;
}

const lista = (dados) => ok({ data: dados || [], total: (dados || []).length });
const perfil = () => ({ p_perfil_id: estado.perfilId });

const ROTAS = [
    ['GET', /^\/api\/categorias\/?$/, async () => lista(await rpc((a) => supabase.rpc('mobilidade_categorias_tela', a), perfil()))],
    ['GET', /^\/api\/veiculos\/mobilidade\/ativo$/,
        async () => ok({ data: await rpc((a) => supabase.rpc('mobilidade_ativa_tela', a), perfil()) })],
    ['GET', /^\/api\/veiculos\/mobilidade\/assinaturas$/, async (m, c, p) => ok({
        data: await rpc((a) => supabase.rpc('mobilidade_assinaturas_tela', a), {
            ...perfil(), p_apenas_ativas: ['1', 'true', 'yes'].includes((p.get('apenas_ativas') || '').toLowerCase()),
        }),
    })],
    ['GET', /^\/api\/veiculos\/?$/, async () => lista(await rpc((a) => supabase.rpc('veiculos_tela', a), { ...perfil(), p_id: null }))],
    ['GET', /^\/api\/veiculos\/(\d+)$/,
        async (m) => ok({ data: await rpc((a) => supabase.rpc('veiculos_tela', a), { ...perfil(), p_id: Number(m[1]) }) })],
    ['GET', /^\/api\/veiculos\/(\d+)\/projecoes$/, async (m, c, p) => lista(await rpc((a) => supabase.rpc('projecoes_mobilidade_tela', a), {
        ...perfil(), p_origem_tipo: 'VEICULO', p_origem_id: Number(m[1]), p_meses: inteiro(p, 'meses', 24),
    }))],
    ['GET', /^\/api\/veiculos\/(\d+)\/uso$/, async (m, c, p) => ok({
        data: await rpc((a) => supabase.rpc('veiculo_uso_tela', a), { ...perfil(), p_veiculo_id: Number(m[1]), p_janela: inteiro(p, 'janela_meses', 3) }),
    })],
    ['GET', /^\/api\/veiculos\/(\d+)\/regras-km$/,
        async (m) => lista(await rpc((a) => supabase.rpc('veiculo_regras_km_tela', a), { ...perfil(), p_veiculo_id: Number(m[1]) }))],
    ['GET', /^\/api\/veiculos\/(\d+)\/manutencoes-km$/, async (m, c, p) => ok({
        data: await rpc((a) => supabase.rpc('veiculo_manutencoes_km_tela', a), {
            ...perfil(), p_veiculo_id: Number(m[1]), p_janela: inteiro(p, 'janela_meses', 3),
        }),
    })],
    ['GET', /^\/api\/veiculos\/(\d+)\/financiamento$/, async (m) => ok({
        data: await rpc((a) => supabase.rpc('veiculo_financiamento_tela', a), { ...perfil(), p_veiculo_id: Number(m[1]) }),
    })],
    ['GET', /^\/api\/mobilidade-app\/?$/, async () => lista(await rpc((a) => supabase.rpc('transporte_app_tela', a), { ...perfil(), p_id: null }))],
    ['GET', /^\/api\/mobilidade-app\/(\d+)$/,
        async (m) => ok({ data: await rpc((a) => supabase.rpc('transporte_app_tela', a), { ...perfil(), p_id: Number(m[1]) }) })],
    ['GET', /^\/api\/mobilidade-app\/(\d+)\/projecoes$/, async (m, c, p) => lista(await rpc((a) => supabase.rpc('projecoes_mobilidade_tela', a), {
        ...perfil(), p_origem_tipo: 'TRANSPORTE_APP', p_origem_id: Number(m[1]), p_meses: inteiro(p, 'meses', 24),
    }))],
];

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                const status = erro && erro.code === '42501' ? 403 : erro && erro.hint === 'NAO_ENCONTRADA' ? 404 : 400;
                return falha(mensagemDeErro(erro), status);
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
