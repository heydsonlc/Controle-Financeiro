// FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 — adaptador da tela original de Receitas: responde as rotas /api/... que
// js/original/receitas.js chama (ponte-api.js), no formato do Flask.
// - Leitura (migration 20261119090000): fontes, previsoes do ano e recebimentos; os recebimentos estornados saem da
//   lista (melhoria do FIN-RECEITAS-1: estorno nao conta como recebido e a previsao volta a pendente).
// - Escrita pelas funcoes ja existentes (FIN-RECEITAS-1 e FIN-MOVIMENTACOES-1), sem regra duplicada aqui:
//   fonte nova = criar_receita (recorrente: 12 previsoes a partir da competencia escolhida), editar/inativar fonte,
//   "remover previsao" = excluir_receita (recorrente zera como o Flask), consolidar = receber_receita (valor, data e
//   justificativa dos campos acrescentados ao modal) e estornar = estornar_recebimento.
// - FIN-CATEGORIAS-RECORRENCIAS-2 (migration 20261125090000): valor base, recorrencia e reativacao da fonte
//   (redefinir_fonte_receita: como o Flask, cria so as previsoes que faltam nos 12 meses a partir do mes atual; as
//   gravadas nao mudam) e recebimento sem previsao (receber_sem_previsao: credito no extrato, sem duplicar a receita).
//   A data prevista de cada previsao aparece em "Proximos recebimentos" (receitas-adaptacoes.js).
// - Edicao de recebimento ainda nao esta disponivel (corrigir = estornar e receber de novo).

import { supabase } from './cliente.js';
import { criarChaves, falha, hojeBrasilia, mensagemDeErro, NAO_DISPONIVEL, ok, PERFIL_NAO_HABILITADO } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };
const chaves = criarChaves();

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

const fontes = () => rpc((a) => supabase.rpc('receitas_fontes_tela', a), { p_perfil_id: estado.perfilId });
const orcamentos = (ano) => rpc((a) => supabase.rpc('receitas_orcamentos_tela', a), { p_perfil_id: estado.perfilId, p_ano: ano });

async function realizadas(parametros) {
    const lista = await rpc((a) => supabase.rpc('receitas_realizadas_tela', a), {
        p_perfil_id: estado.perfilId, p_inicio: parametros.get('ano_mes_inicio') || parametros.get('ano_mes'),
        p_fim: parametros.get('ano_mes_fim') || parametros.get('ano_mes'),
    });
    return lista || [];
}

async function contasAtivas() {
    const lista = await rpc((a) => supabase.rpc('contas_bancarias_tela', a), { p_perfil_id: estado.perfilId, p_status: 'ATIVO' });
    return ok({ data: lista || [], total: (lista || []).length });
}

// Competencia escolhida nos filtros da tela (mes "Todos" = mes atual), como getAnoMesSelecionado do Flask.
function competenciaDaTela() {
    const hoje = hojeBrasilia();
    const ano = document.getElementById('filtro-ano')?.value || hoje.slice(0, 4);
    const mes = document.getElementById('filtro-mes')?.value || hoje.slice(5, 7);
    return `${ano}-${mes}-01`;
}

async function fonte(id) {
    const encontrada = (await fontes()).find((f) => f.id === id);
    if (!encontrada) throw Object.assign(new Error('Fonte de receita não encontrada'), { status: 404 });
    return encontrada;
}

async function criarFonte(corpo) {
    const valor = Number(corpo.valor_base_mensal) || 0;
    if (valor <= 0) {
        return falha('Informe o valor base: no novo aplicativo a fonte nasce com a sua previsão. Nada foi gravado.');
    }
    if (corpo.ativo === false) return falha('Uma fonte nova nasce ativa. Nada foi gravado.');
    const r = await rpc((a) => supabase.rpc('criar_receita', a), {
        p_perfil_id: estado.perfilId, p_chave: chaves.de('fonte'), p_dados: {
            nome: corpo.nome, tipo: corpo.tipo, valor: valor.toFixed(2), competencia: competenciaDaTela(),
            recorrente: corpo.recorrente !== false, dia_previsto: corpo.dia_previsto_pagamento || null,
            conta_bancaria_id: corpo.conta_bancaria_id || null, descricao: corpo.descricao || null,
        },
    });
    chaves.esquecer('fonte');
    return ok({ message: 'Fonte de receita criada com sucesso', data: await fonte(r.item_receita_id) });
}

// PUT da fonte como o Flask: dados da fonte; inativar quando pedido; depois valor base, recorrencia e reativacao, que
// completam as previsoes que faltam (fonte ativa e recorrente com valor base) sem mudar as gravadas.
async function editarFonte(id, corpo) {
    const atual = await fonte(id);
    let { versao } = await rpc((a) => supabase.rpc('editar_fonte_receita', a), {
        p_perfil_id: estado.perfilId, p_item_id: id, p_versao: atual.versao, p_dados: {
            nome: corpo.nome, tipo: corpo.tipo, descricao: corpo.descricao ?? null,
            dia_previsto: corpo.dia_previsto_pagamento || null, conta_bancaria_id: corpo.conta_bancaria_id || null,
        },
    });
    if (corpo.ativo === false && atual.ativo) {
        await rpc((a) => supabase.rpc('inativar_fonte_receita', a), { p_perfil_id: estado.perfilId, p_item_id: id, p_versao: versao });
        ({ versao } = await fonte(id));
    }
    const dados = { recorrente: corpo.recorrente ?? atual.recorrente };
    if ('valor_base_mensal' in corpo) {
        const base = corpo.valor_base_mensal === null || corpo.valor_base_mensal === '' ? null : Number(corpo.valor_base_mensal);
        dados.valor_base_mensal = base === null || Number.isNaN(base) ? null : base.toFixed(2);
    }
    if (corpo.ativo === true && !atual.ativo) dados.ativo = true;
    const r = await rpc((a) => supabase.rpc('redefinir_fonte_receita', a), {
        p_perfil_id: estado.perfilId, p_item_id: id, p_versao: versao, p_dados: dados,
    });
    const criadas = (r.previsoes_criadas || []).length;
    const extra = criadas ? ` ${criadas === 1 ? '1 previsão criada' : `${criadas} previsões criadas`} nos próximos meses; as já gravadas não mudam.` : '';
    return ok({ message: `Fonte de receita atualizada com sucesso.${extra}`, data: await fonte(id) });
}

async function inativarFonte(id) {
    const atual = await fonte(id);
    await rpc((a) => supabase.rpc('inativar_fonte_receita', a), { p_perfil_id: estado.perfilId, p_item_id: id, p_versao: atual.versao });
    return ok({ message: 'Fonte de receita inativada com sucesso', data: await fonte(id) });
}

// Previsao gravada da fonte na competencia (o Flask manda fonte + competencia, nao o id da previsao).
async function previsaoDe(itemId, competencia) {
    const mes = String(competencia || '').slice(0, 7);
    return (await orcamentos(Number(mes.slice(0, 4)))).find((o) => o.item_receita_id === itemId && o.mes_referencia.slice(0, 7) === mes);
}

// POST /api/receitas/orcamento: valor zero = "remover previsao" (excluir_receita: recorrente zera como o Flask);
// valor positivo = editar a previsao existente ou prever a fonte nesta competencia.
async function salvarPrevisao(corpo) {
    const itemId = Number(corpo.item_receita_id);
    const previsao = await previsaoDe(itemId, corpo.ano_mes);
    const valor = Number(corpo.valor_previsto) || 0;
    if (valor === 0) {
        if (!previsao) return falha('Não há previsão gravada desta fonte nesta competência. Nada foi gravado.');
        await rpc((a) => supabase.rpc('excluir_receita', a), { p_perfil_id: estado.perfilId, p_orcamento_id: previsao.id, p_versao: previsao.versao });
        return ok({ message: 'Previsão removida.' });
    }
    if (previsao) {
        await rpc((a) => supabase.rpc('editar_receita', a), {
            p_perfil_id: estado.perfilId, p_orcamento_id: previsao.id, p_versao: previsao.versao,
            p_dados: { valor: valor.toFixed(2), observacoes: corpo.observacoes || null },
        });
    } else {
        await rpc((a) => supabase.rpc('criar_receita', a), {
            p_perfil_id: estado.perfilId, p_chave: chaves.de('previsao'), p_dados: {
                item_receita_id: itemId, valor: valor.toFixed(2), competencia: corpo.ano_mes, observacoes: corpo.observacoes || null,
            },
        });
        chaves.esquecer('previsao');
    }
    return ok({ message: 'Orçamento criado/atualizado com sucesso' });
}

// Sem previsao gravada na competencia (Flask: POST /api/receitas/realizadas sem orcamento): recebimento da fonte com
// credito no extrato. Havendo previsao, o banco recusa e o recebimento vai pela previsao (nao conta duas vezes).
async function receberSemPrevisao(corpo, data) {
    const dados = {
        item_receita_id: Number(corpo.item_receita_id), data_recebimento: data,
        valor_recebido: (Number(corpo.valor_recebido) || 0).toFixed(2), competencia: corpo.competencia || null,
        conta_bancaria_id: corpo.conta_bancaria_id || null, descricao: corpo.descricao || '', observacoes: corpo.observacoes || '',
    };
    const operacao = `sem-previsao:${JSON.stringify(dados)}`;
    const r = await rpc((a) => supabase.rpc('receber_sem_previsao', a), {
        p_perfil_id: estado.perfilId, p_dados: dados, p_chave: chaves.de(operacao),
    });
    chaves.esquecer(operacao);
    return { status: 201, corpo: { success: true, message: 'Receita registrada com sucesso', data: r } };
}

// POST /api/receitas/realizadas: "Consolidar" (modal com valor, data e justificativa acrescentados) ou "Registrar
// recebimento". Com previsao na competencia, recebimento dela pelo motor do novo aplicativo (escritor unico do perfil).
async function receber(corpo) {
    if (!corpo.item_receita_id) return falha(`Recebimento sem fonte ${NAO_DISPONIVEL}`);
    const consolidando = document.getElementById('modal-consolidar-conta')?.getAttribute('aria-hidden') === 'false';
    const data = (consolidando && document.getElementById('consolidar-data-recebimento')?.value) || corpo.data_recebimento;
    const justificativa = (consolidando && document.getElementById('consolidar-justificativa')?.value.trim()) || null;
    const previsao = await previsaoDe(Number(corpo.item_receita_id), corpo.competencia || corpo.data_recebimento);
    if (!previsao) return receberSemPrevisao(corpo, data);
    const dados = await rpc((a) => supabase.rpc('dados_recebimento_receita', a), { p_perfil_id: estado.perfilId, p_orcamento_id: previsao.id });
    const r = await rpc((a) => supabase.rpc('receber_receita', a), {
        p_perfil_id: estado.perfilId, p_orcamento_id: previsao.id, p_chave: chaves.de(`receber-${previsao.id}`), p_dados: {
            conta_bancaria_id: corpo.conta_bancaria_id, data_recebimento: data,
            valor_recebido: (Number(corpo.valor_recebido) || 0).toFixed(2), falta: dados.receita.falta, justificativa,
        },
    });
    chaves.esquecer(`receber-${previsao.id}`);
    return ok({ message: 'Receita registrada com sucesso', data: r });
}

async function estornar(id, corpo) {
    if (!corpo.motivo) return falha('Motivo do estorno e obrigatorio.');
    if (!corpo.data_estorno) return falha('Data do estorno e obrigatoria.');
    const r = await rpc((a) => supabase.rpc('estornar_recebimento', a), {
        p_perfil_id: estado.perfilId, p_realizada_id: id, p_chave: chaves.de(`estorno-${id}`),
        p_dados: { motivo: corpo.motivo, data_estorno: corpo.data_estorno },
    });
    chaves.esquecer(`estorno-${id}`);
    return ok({ message: 'Recebimento estornado com sucesso.', data: r });
}

async function excluirRecebimento(id) {
    const recebimento = (await realizadas(new URLSearchParams())).find((r) => r.id === id);
    if (recebimento && recebimento.conta_bancaria_id) {
        return falha('Receita realizada ou com movimento financeiro nao pode ser excluida.', 409);
    }
    return falha(`Excluir este registro ${NAO_DISPONIVEL}`);
}

const ROTAS = [
    ['GET', /^\/api\/contas\/?$/, () => contasAtivas()],
    ['GET', /^\/api\/receitas\/itens\/?$/, async () => { const l = await fontes(); return ok({ data: l || [], total: (l || []).length }); }],
    ['GET', /^\/api\/receitas\/itens\/(\d+)$/, async (m) => ok({ data: await fonte(Number(m[1])) })],
    ['POST', /^\/api\/receitas\/itens\/?$/, (m, corpo) => criarFonte(corpo || {})],
    ['PUT', /^\/api\/receitas\/itens\/(\d+)$/, (m, corpo) => editarFonte(Number(m[1]), corpo || {})],
    ['DELETE', /^\/api\/receitas\/itens\/(\d+)$/, (m) => inativarFonte(Number(m[1]))],
    ['GET', /^\/api\/receitas\/orcamento\/?$/, async (m, c, p) => {
        const ano = Number(p.get('ano'));
        if (!ano) return falha('Parâmetro ano é obrigatório');
        const l = await orcamentos(ano);
        return ok({ data: l || [], total: (l || []).length });
    }],
    ['POST', /^\/api\/receitas\/orcamento\/?$/, (m, corpo) => salvarPrevisao(corpo || {})],
    // Estornados saem da lista: nao contam como recebidos e a previsao volta a pendente (melhoria do FIN-RECEITAS-1).
    ['GET', /^\/api\/receitas\/realizadas\/?$/, async (m, c, p) => {
        const l = (await realizadas(p)).filter((r) => !r.estornada);
        return ok({ data: l, total: l.length });
    }],
    ['POST', /^\/api\/receitas\/realizadas\/?$/, (m, corpo) => receber(corpo || {})],
    ['POST', /^\/api\/receitas\/realizadas\/(\d+)\/estornar$/, (m, corpo) => estornar(Number(m[1]), corpo || {})],
    ['PUT', /^\/api\/receitas\/realizadas\/(\d+)$/, async () => falha('Editar um recebimento ainda não está disponível nesta versão do aplicativo. '
        + 'Para corrigir, estorne e registre de novo. Nada foi gravado.')],
    ['DELETE', /^\/api\/receitas\/realizadas\/(\d+)$/, (m) => excluirRecebimento(Number(m[1]))],
];

function mensagem(erro) {
    if (erro && erro.hint === 'SISTEMA_FLASK') {
        return PERFIL_NAO_HABILITADO;
    }
    return mensagemDeErro(erro);
}

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                if (erro && erro.status === 404) return falha(erro.message, 404);
                return falha(mensagem(erro), erro && erro.code === '42501' ? 403 : 400);
            }
        }
    }
    return falha(`${metodo} ${caminho}: ${NAO_DISPONIVEL}`, 501);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
    const { data: gere } = await supabase.rpc('pode_gerir_perfil', { p_perfil_id: estado.perfilId });
    document.body.classList.toggle('cf-somente-leitura', gere !== true);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
