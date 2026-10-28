// FIN-FIDELIDADE-PATRIMONIO-1 (Mobilidade, fase 1) — adaptador da tela original de Mobilidade: responde as rotas
// /api/... que js/original/veiculos.js chama (ponte-api.js), no formato do Flask. Consulta (migration 20261115090000):
// veiculos, projecoes ja geradas, uso, regras e estimativas de manutencao por km, financiamento do veiculo, modalidade
// ativa, assinaturas, caminhos de transporte por app e categorias.
// FIN-MOBILIDADE-2 (migration 20261127090000): escrita pelas funcoes do banco, com o escritor unico do perfil (perfil
// ainda no Flask e recusado sem gravar): veiculos (criar, editar, converter, excluir com seguranca, gerar projecoes),
// regras e manutencao por km, financiamento projetivo do veiculo, previa e ativacao de modalidade (cenario ativo no
// banco, por perfil), assinaturas, caminhos de transporte por app e confirmar/adiar/ignorar despesas previstas.
// Categorias sistemicas MOB_* nunca sao criadas aqui. O arquivo global /api/veiculos/cenario-ativo do Flask nao e
// reproduzido (a tela le a modalidade ativa do banco).

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };
const chaves = criarChaves();
const NAO_REPRODUZIDO = 'Mobilidade: o cenário ativo fica no banco, por perfil (modalidade ativa). Esta ação do sistema antigo não é usada. Nada foi gravado.';

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
// funcao: arrow que chama supabase.rpc com o nome literal da funcao (build.test.mjs confere cada RPC usada).
const chamar = (funcao, args) => rpc(funcao, { ...perfil(), ...args });
const criado = (corpo) => ({ status: 201, corpo: { success: true, ...corpo } });
const veiculoLido = (id) => chamar((a) => supabase.rpc('veiculos_tela', a), { p_id: id });

// Cadastros com chave de repeticao (duplo clique ou reenvio nao duplicam); esquecida depois do sucesso.
async function comChave(operacao, funcao, args) {
    const r = await chamar(funcao, { ...args, p_chave: chaves.de(operacao) });
    chaves.esquecer(operacao);
    return r;
}

async function cartoes() {
    const dados = await chamar((a) => supabase.rpc('cartoes_do_perfil', a), {});
    return ok({ data: (dados || []).filter((c) => c.ativo).map((c) => ({ id: c.id, nome: c.nome, tipo: 'Agregador', ativo: true })) });
}

async function criarVeiculo(corpo) {
    const r = await comChave(`veiculo:${JSON.stringify(corpo)}`, (a) => supabase.rpc('criar_veiculo', a), { p_dados: corpo });
    return criado({ message: 'Veículo criado', data: await veiculoLido(r.veiculo_id) });
}

async function editarVeiculo(id, corpo) {
    await chamar((a) => supabase.rpc('editar_veiculo', a), { p_veiculo_id: id, p_dados: corpo });
    return ok({ message: 'Veículo atualizado', data: await veiculoLido(id) });
}

async function converterVeiculo(id, corpo) {
    await chamar((a) => supabase.rpc('converter_veiculo', a), { p_veiculo_id: id, p_dados: corpo });
    return ok({ message: 'Veículo convertido para ATIVO', data: await veiculoLido(id) });
}

async function gerarProjecoes(id, corpo) {
    const r = await chamar((a) => supabase.rpc('gerar_projecoes_veiculo', a), { p_veiculo_id: id, p_dados: corpo });
    return ok({ message: 'Projeções geradas', criadas: r.criadas });
}

async function criarRegra(id, corpo) {
    const r = await comChave(`regra:${id}:${JSON.stringify(corpo)}`, (a) => supabase.rpc('criar_regra_km_veiculo', a), { p_veiculo_id: id, p_dados: corpo });
    return criado({ message: 'Regra criada', data: r.data });
}

async function gerarManutencao(id, corpo) {
    const r = await chamar((a) => supabase.rpc('gerar_manutencao_km_veiculo', a), { p_veiculo_id: id, p_dados: corpo });
    return r.gerada ? criado({ message: 'Manutenção prevista gerada', data: r.data })
        : ok({ message: 'Nenhuma manutenção gerada (uso insuficiente ou já existe evento ativo)' });
}

async function excluirFinanciamento(id) {
    const r = await chamar((a) => supabase.rpc('excluir_financiamento_veiculo', a), { p_veiculo_id: id });
    return ok({ message: r.removidos ? 'Financiamento removido (simulação)' : 'Nenhum financiamento encontrado' });
}

async function ativar(corpo) {
    const r = await comChave(`ativar:${JSON.stringify(corpo)}`, (a) => supabase.rpc('ativar_mobilidade', a), { p_dados: corpo });
    const { repetida, ...dados } = r;
    return ok({ message: 'Modalidade ativada', data: dados });
}

async function criarAssinatura(corpo) {
    const r = await comChave(`assinatura:${JSON.stringify(corpo)}`, (a) => supabase.rpc('criar_assinatura_mobilidade', a), { p_dados: corpo });
    return criado({ data: r.data });
}

async function criarCaminho(corpo) {
    const r = await comChave(`caminho:${JSON.stringify(corpo)}`, (a) => supabase.rpc('criar_caminho_app', a), { p_dados: corpo });
    return criado({ message: 'Caminho criado', data: { id: r.id } });
}

const ROTAS = [
    ['GET', /^\/api\/categorias\/?$/, async () => lista(await chamar((a) => supabase.rpc('mobilidade_categorias_tela', a), {}))],
    ['GET', /^\/api\/cartoes\/?$/, () => cartoes()],
    ['GET', /^\/api\/veiculos\/mobilidade\/ativo$/, async () => ok({ data: await chamar((a) => supabase.rpc('mobilidade_ativa_tela', a), {}) })],
    ['GET', /^\/api\/veiculos\/mobilidade\/assinaturas$/, async (m, c, p) => ok({
        data: await chamar((a) => supabase.rpc('mobilidade_assinaturas_tela', a), {
            p_apenas_ativas: ['1', 'true', 'yes'].includes((p.get('apenas_ativas') || '').toLowerCase()),
        }),
    })],
    ['POST', /^\/api\/veiculos\/mobilidade\/assinaturas$/, (m, c) => criarAssinatura(c || {})],
    ['PUT', /^\/api\/veiculos\/mobilidade\/assinaturas\/(\d+)$/,
        async (m, c) => ok({ data: (await chamar((a) => supabase.rpc('editar_assinatura_mobilidade', a), { p_assinatura_id: Number(m[1]), p_dados: c || {} })).data })],
    ['PATCH', /^\/api\/veiculos\/mobilidade\/assinaturas\/(\d+)$/,
        async (m, c) => ok({ data: (await chamar((a) => supabase.rpc('editar_assinatura_mobilidade', a), { p_assinatura_id: Number(m[1]), p_dados: c || {} })).data })],
    ['POST', /^\/api\/veiculos\/mobilidade\/previsualizar$/,
        async (m, c) => ok({ data: await chamar((a) => supabase.rpc('previa_mobilidade', a), { p_dados: c || {} }) })],
    ['POST', /^\/api\/veiculos\/mobilidade\/ativar$/, (m, c) => ativar(c || {})],
    ['GET', /^\/api\/veiculos\/cenario-ativo$/, async () => ok({ data: {} })],
    ['POST', /^\/api\/veiculos\/cenario-ativo$/, async () => falha(NAO_REPRODUZIDO, 501)],
    ['GET', /^\/api\/veiculos\/?$/, async () => lista(await chamar((a) => supabase.rpc('veiculos_tela', a), { p_id: null }))],
    ['POST', /^\/api\/veiculos\/?$/, (m, c) => criarVeiculo(c || {})],
    ['GET', /^\/api\/veiculos\/(\d+)$/, async (m) => ok({ data: await veiculoLido(Number(m[1])) })],
    ['PUT', /^\/api\/veiculos\/(\d+)$/, (m, c) => editarVeiculo(Number(m[1]), c || {})],
    ['DELETE', /^\/api\/veiculos\/(\d+)$/, async (m) => {
        await chamar((a) => supabase.rpc('excluir_veiculo', a), { p_veiculo_id: Number(m[1]) });
        return ok({ message: 'Veículo deletado' });
    }],
    ['POST', /^\/api\/veiculos\/(\d+)\/converter$/, (m, c) => converterVeiculo(Number(m[1]), c || {})],
    ['GET', /^\/api\/veiculos\/(\d+)\/projecoes$/, async (m, c, p) => lista(await chamar((a) => supabase.rpc('projecoes_mobilidade_tela', a), {
        p_origem_tipo: 'VEICULO', p_origem_id: Number(m[1]), p_meses: inteiro(p, 'meses', 24),
    }))],
    ['POST', /^\/api\/veiculos\/(\d+)\/projecoes\/gerar$/, (m, c) => gerarProjecoes(Number(m[1]), c || {})],
    ['GET', /^\/api\/veiculos\/(\d+)\/uso$/, async (m, c, p) => ok({
        data: await chamar((a) => supabase.rpc('veiculo_uso_tela', a), { p_veiculo_id: Number(m[1]), p_janela: inteiro(p, 'janela_meses', 3) }),
    })],
    ['GET', /^\/api\/veiculos\/(\d+)\/regras-km$/, async (m) => lista(await chamar((a) => supabase.rpc('veiculo_regras_km_tela', a), { p_veiculo_id: Number(m[1]) }))],
    ['POST', /^\/api\/veiculos\/(\d+)\/regras-km$/, (m, c) => criarRegra(Number(m[1]), c || {})],
    ['DELETE', /^\/api\/veiculos\/(\d+)\/regras-km\/(\d+)$/, async (m) => {
        await chamar((a) => supabase.rpc('excluir_regra_km_veiculo', a), { p_veiculo_id: Number(m[1]), p_regra_id: Number(m[2]) });
        return ok({ message: 'Regra removida' });
    }],
    ['GET', /^\/api\/veiculos\/(\d+)\/manutencoes-km$/, async (m, c, p) => ok({
        data: await chamar((a) => supabase.rpc('veiculo_manutencoes_km_tela', a), { p_veiculo_id: Number(m[1]), p_janela: inteiro(p, 'janela_meses', 3) }),
    })],
    ['POST', /^\/api\/veiculos\/(\d+)\/manutencoes-km\/gerar$/, (m, c) => gerarManutencao(Number(m[1]), c || {})],
    ['GET', /^\/api\/veiculos\/(\d+)\/financiamento$/, async (m) => ok({
        data: await chamar((a) => supabase.rpc('veiculo_financiamento_tela', a), { p_veiculo_id: Number(m[1]) }),
    })],
    ['POST', /^\/api\/veiculos\/(\d+)\/financiamento$/, async (m, c) => ok({
        message: 'Financiamento simulado atualizado',
        ...(await chamar((a) => supabase.rpc('salvar_financiamento_veiculo', a), { p_veiculo_id: Number(m[1]), p_dados: c || {} })),
    })],
    ['DELETE', /^\/api\/veiculos\/(\d+)\/financiamento$/, (m) => excluirFinanciamento(Number(m[1]))],
    ['GET', /^\/api\/mobilidade-app\/?$/, async () => lista(await chamar((a) => supabase.rpc('transporte_app_tela', a), { p_id: null }))],
    ['POST', /^\/api\/mobilidade-app\/?$/, (m, c) => criarCaminho(c || {})],
    ['GET', /^\/api\/mobilidade-app\/(\d+)$/, async (m) => ok({ data: await chamar((a) => supabase.rpc('transporte_app_tela', a), { p_id: Number(m[1]) }) })],
    ['PUT', /^\/api\/mobilidade-app\/(\d+)$/, async (m, c) => {
        await chamar((a) => supabase.rpc('editar_caminho_app', a), { p_caminho_id: Number(m[1]), p_dados: c || {} });
        return ok({ message: 'Caminho atualizado', data: { id: Number(m[1]) } });
    }],
    ['DELETE', /^\/api\/mobilidade-app\/(\d+)$/, async (m) => {
        await chamar((a) => supabase.rpc('excluir_caminho_app', a), { p_caminho_id: Number(m[1]) });
        return ok({ message: 'Caminho removido' });
    }],
    ['GET', /^\/api\/mobilidade-app\/(\d+)\/projecoes$/, async (m, c, p) => lista(await chamar((a) => supabase.rpc('projecoes_mobilidade_tela', a), {
        p_origem_tipo: 'TRANSPORTE_APP', p_origem_id: Number(m[1]), p_meses: inteiro(p, 'meses', 24),
    }))],
    ['POST', /^\/api\/despesas-previstas\/(\d+)\/confirmar$/, async (m, c) => ok({
        message: 'Despesa prevista confirmada',
        data: await chamar((a) => supabase.rpc('confirmar_despesa_prevista', a), { p_id: Number(m[1]), p_dados: c || {} }),
    })],
    ['POST', /^\/api\/despesas-previstas\/(\d+)\/adiar$/, async (m, c) => ok({
        message: 'Despesa prevista adiada', ...(await chamar((a) => supabase.rpc('adiar_despesa_prevista', a), { p_id: Number(m[1]), p_dados: c || {} })),
    })],
    ['POST', /^\/api\/despesas-previstas\/(\d+)\/ignorar$/, async (m) => ok({
        message: 'Despesa prevista ignorada', ...(await chamar((a) => supabase.rpc('ignorar_despesa_prevista', a), { p_id: Number(m[1]) })),
    })],
];

// Erros do banco no formato do Flask: 409 escritor, 404 nao encontrado, 403 sem permissao, 400 o resto.
function falhaDoBanco(erro) {
    if (erro && erro.hint === 'SISTEMA_FLASK') {
        return falha('A mobilidade deste perfil ainda é administrada pelo sistema atual (Flask). Nada foi gravado.', 409);
    }
    if (erro && erro.hint === 'NAO_ENCONTRADA') return falha(mensagemDeErro(erro), 404);
    return falha(mensagemDeErro(erro), erro && erro.code === '42501' ? 403 : 400);
}

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                return falhaDoBanco(erro);
            }
        }
    }
    return falha('Mobilidade: rota não reconhecida pelo novo aplicativo. Nada foi gravado.', 501);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
