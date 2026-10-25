// FIN-FIDELIDADE-RECORRENCIAS-1 — adaptador da tela original de Recorrencias: responde as rotas /api/... que
// js/original/recorrencias.js chama (ponte-api.js), no formato do Flask (_item_to_dict), com as funcoes do Supabase.
//
// Regras no banco (FIN-DESPESAS-1 + 20261103090000): criar_despesa (recorrente), editar_recorrencia,
// inativar_recorrencia, reativar_recorrencia, definir_meio_pagamento_recorrencia e recorrencias_do_perfil, com gestao
// do perfil, versao contra edicao concorrente e trava de geracao. Diferencas assumidas em relacao ao Flask:
// - salvar nao gera conta: a geracao e explicita, em Despesas ("Gerar contas"), como no FIN-RECORRENCIA-1;
// - semanal / a cada 2 semanas: o gerador do novo aplicativo so gera mensal e anual (pendencia);
// - recorrencia no cartao: cadastrada no modulo de cartoes (pendencia); aqui aparece, mas nao e alterada;
// - consorcios: modulo em migracao (a lista avisa).

import { supabase } from './cliente.js';
import { criarChaves, emMigracao, falha, mensagemDeErro, ok, valorTexto } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null, itens: new Map() };
const chaves = criarChaves();
const MEIOS_INFORMATIVOS = ['boleto', 'pix', 'debito'];
const TIPO_FREQUENCIA = /^semanal_(\d+)_(\d)$/;

// tipo_recorrencia do banco -> frequencia/dia da semana como o Flask (_detalhes_frequencia).
function frequencia(tipo) {
    const semanal = TIPO_FREQUENCIA.exec(tipo || '');
    if (semanal) return { frequencia: semanal[1] === '2' ? 'quinzenal' : 'semanal', dia_semana: Number(semanal[2]), frequencia_semanas: Number(semanal[1]) };
    if (tipo === 'a_cada_2_semanas') return { frequencia: 'quinzenal', dia_semana: null, frequencia_semanas: 2 };
    return { frequencia: tipo || 'mensal', dia_semana: null, frequencia_semanas: null };
}

function itemDoFlask(r) {
    return {
        id: r.id,
        tipo: 'recorrencia_simples',
        tipo_visual: 'Recorrencia',
        nome: r.nome,
        descricao: r.descricao,
        valor: r.valor === null ? null : Number(r.valor),
        categoria_id: r.categoria_id,
        categoria_nome: r.categoria_nome,
        recorrente: true,
        tipo_recorrencia: r.tipo_recorrencia,
        ...frequencia(r.tipo_recorrencia),
        meio_pagamento: r.meio_pagamento,
        cartao_id: r.cartao_id,
        conta_bancaria_id: r.conta_bancaria_id,
        conta_bancaria_nome: r.conta_bancaria_nome,
        categoria_cartao_id: null,
        ativo: r.ativo,
        status: r.ativo ? 'Ativa' : 'Inativa',
        data_vencimento: r.data_vencimento,
        proximo_vencimento: r.proximo_vencimento,
    };
}

async function recorrencias() {
    const { data, error } = await supabase.rpc('recorrencias_do_perfil', { p_perfil_id: estado.perfilId });
    if (error) throw error;
    estado.itens = new Map((data || []).map((r) => [r.id, r]));
    return data || [];
}

async function atual(id) {
    await recorrencias();
    return estado.itens.get(id) || null;
}

function avisar(texto) {
    const aviso = document.getElementById('recorrencias-resultado');
    aviso.textContent = texto;
    aviso.hidden = false;
}

// Pedidos do formulario que o novo aplicativo ainda nao atende (sem gravar registro incompleto).
function recusa(corpo, tipoAtual) {
    if (corpo.tipo_recorrencia === 'semanal') {
        if (!tipoAtual || !TIPO_FREQUENCIA.test(tipoAtual)) {
            return 'Semanal e a cada 2 semanas: o novo aplicativo ainda não gera essa frequência (pendência). Use mensal ou anual.';
        }
    } else if (!['mensal', 'anual'].includes(corpo.tipo_recorrencia)) {
        return 'Frequência inválida.';
    }
    if (corpo.meio_pagamento === 'cartao') {
        return 'Recorrência no cartão de crédito: em migração para o novo aplicativo (módulo de cartões).';
    }
    if (corpo.meio_pagamento === 'debito_automatico' && !corpo.conta_bancaria_id) {
        return 'Conta bancária é obrigatória para recorrência em débito automático.';
    }
    if (!String(corpo.nome || '').trim()) return 'Nome e obrigatorio';
    if (!(Number(corpo.valor) > 0)) return 'Valor e obrigatorio';
    if (!corpo.categoria_id) return 'Categoria e obrigatoria';
    if (!corpo.data_vencimento) return 'Informe a data do primeiro vencimento: sem ela a recorrência não gera contas.';
    return null;
}

const MENSAGEM_GERACAO = 'As contas são geradas em Despesas, pela ação "Gerar contas" (com confirmação).';

async function definirMeio(id, meio) {
    const item = await atual(id);
    if ((item.meio_pagamento || null) === (meio || null)) return null;
    const { error } = await supabase.rpc('definir_meio_pagamento_recorrencia', {
        p_perfil_id: estado.perfilId, p_item_id: id, p_versao: item.versao, p_meio: meio || null,
    });
    return error;
}

async function definirAtivo(id, ativo) {
    const item = await atual(id);
    if (item.ativo === ativo) return null;
    const args = { p_perfil_id: estado.perfilId, p_item_id: id, p_versao: item.versao };
    const { error } = ativo
        ? await supabase.rpc('reativar_recorrencia', args)
        : await supabase.rpc('inativar_recorrencia', args);
    return error;
}

async function criar(corpo) {
    const motivo = recusa(corpo, null);
    if (motivo) return falha(motivo);
    const debito = corpo.meio_pagamento === 'debito_automatico';
    const dados = {
        nome: String(corpo.nome).trim(),
        valor: valorTexto(corpo.valor),
        categoria_id: Number(corpo.categoria_id),
        data_vencimento: corpo.data_vencimento,
        descricao: String(corpo.descricao || '').trim(),
        recorrente: true,
        tipo_recorrencia: corpo.tipo_recorrencia,
        debito_automatico: debito,
        conta_bancaria_id: debito ? Number(corpo.conta_bancaria_id) : null,
    };
    const operacao = `criar:${JSON.stringify(dados)}`;
    const { data, error } = await supabase.rpc('criar_despesa', { p_perfil_id: estado.perfilId, p_dados: dados, p_chave: chaves.de(operacao) });
    if (error) return falha(mensagemDeErro(error));
    chaves.esquecer(operacao);
    // Passos complementares (informativos): a recorrencia ja existe; se falharem, o aviso diz o que faltou.
    const pendentes = [];
    if (MEIOS_INFORMATIVOS.includes(corpo.meio_pagamento) && await definirMeio(data.item_id, corpo.meio_pagamento)) pendentes.push('o meio de pagamento');
    if (corpo.ativo === false && await definirAtivo(data.item_id, false)) pendentes.push('a inativação');
    avisar(`Recorrência criada. ${MENSAGEM_GERACAO}${pendentes.length ? ` Não foi possível gravar ${pendentes.join(' e ')}; edite a recorrência.` : ''}`);
    return { status: 201, corpo: { success: true, message: 'Recorrencia criada com sucesso' } };
}

async function atualizar(id, corpo) {
    const item = await atual(id);
    if (!item) return falha('Recorrencia nao encontrada', 404);
    if (!item.gerenciavel) return falha('Recorrência de cartão ou de outro módulo: altere no módulo de origem.', 409);
    const motivo = recusa(corpo, item.tipo_recorrencia);
    if (motivo) return falha(motivo);
    const debito = corpo.meio_pagamento === 'debito_automatico';
    const dados = {
        nome: String(corpo.nome).trim(),
        valor: valorTexto(corpo.valor),
        categoria_id: Number(corpo.categoria_id),
        data_vencimento: corpo.data_vencimento,
        descricao: String(corpo.descricao || '').trim(),
    };
    // Semanal existente: a frequencia fica como esta (o formulario manda "semanal"; o banco guarda semanal_N_D).
    if (corpo.tipo_recorrencia !== 'semanal') dados.tipo_recorrencia = corpo.tipo_recorrencia;
    if (debito) Object.assign(dados, { debito_automatico: true, conta_bancaria_id: Number(corpo.conta_bancaria_id) });
    else if (item.meio_pagamento === 'debito_automatico') Object.assign(dados, { debito_automatico: false, conta_bancaria_id: null });
    const { error } = await supabase.rpc('editar_recorrencia', {
        p_perfil_id: estado.perfilId, p_item_id: id, p_versao: item.versao, p_dados: dados,
    });
    if (error) {
        if (error.hint === 'GERADOR_FLASK') return falha('Vencimento e frequência só mudam quando o novo aplicativo gera este perfil.');
        return falha(mensagemDeErro(error));
    }
    if (!debito) {
        const meio = MEIOS_INFORMATIVOS.includes(corpo.meio_pagamento) ? corpo.meio_pagamento : null;
        const erroMeio = await definirMeio(id, meio);
        if (erroMeio) return falha(`Recorrência salva, mas o meio de pagamento não: ${mensagemDeErro(erroMeio)}`);
    }
    if (typeof corpo.ativo === 'boolean') {
        const erroAtivo = await definirAtivo(id, corpo.ativo);
        if (erroAtivo) return falha(`Recorrência salva, mas a situação não: ${mensagemDeErro(erroAtivo)}`);
    }
    avisar(`Recorrência atualizada. Vale para as próximas contas; as já geradas não mudam. ${MENSAGEM_GERACAO}`);
    return ok({ message: 'Recorrencia atualizada com sucesso' });
}

async function inativar(id) {
    const item = await atual(id);
    if (!item) return falha('Recorrencia nao encontrada', 404);
    if (!item.gerenciavel) return falha('Recorrência de cartão ou de outro módulo: altere no módulo de origem.', 409);
    const erro = await definirAtivo(id, false);
    if (erro) return falha(mensagemDeErro(erro));
    avisar('Recorrência inativada: nenhuma conta nova será gerada; as já geradas continuam.');
    return ok({ message: 'Recorrencia inativada com sucesso' });
}

async function listar() {
    const lista = await recorrencias();
    return ok({ data: lista.map(itemDoFlask), total: lista.length });
}

async function categorias() {
    const { data, error } = await supabase.rpc('categorias_de_despesa');
    if (error) return falha(mensagemDeErro(error));
    return ok({ data: (data || []).map((c) => ({ id: c.id, nome: c.nome, cor: c.cor, ativo: true })) });
}

async function cartoes() {
    const { data, error } = await supabase.rpc('cartoes_do_perfil', { p_perfil_id: estado.perfilId });
    if (error) return falha(mensagemDeErro(error));
    return ok({ data: (data || []).filter((c) => c.ativo).map((c) => ({ id: c.id, nome: c.nome })) });
}

async function contasBancarias() {
    const { data, error } = await supabase.rpc('contas_bancarias_do_perfil', { p_perfil_id: estado.perfilId });
    if (error) return falha(mensagemDeErro(error));
    return ok({ data: (data || []).filter((c) => String(c.status || '').toUpperCase() === 'ATIVO')
        .map((c) => ({ id: c.id, nome: c.nome, instituicao: c.instituicao })) });
}

const ROTAS = [
    ['GET', /^\/api\/recorrencias\/?$/, () => listar()],
    ['POST', /^\/api\/recorrencias\/?$/, (m, corpo) => criar(corpo || {})],
    ['PUT', /^\/api\/recorrencias\/(\d+)$/, (m, corpo) => atualizar(Number(m[1]), corpo || {})],
    ['DELETE', /^\/api\/recorrencias\/(\d+)$/, (m) => inativar(Number(m[1]))],
    ['GET', /^\/api\/categorias\/?$/, () => categorias()],
    ['GET', /^\/api\/cartoes\/?$/, () => cartoes()],
    ['GET', /^\/api\/contas\/?$/, () => contasBancarias()],
    // Consorcios: modulo em migracao; a lista avisa (recorrencias-aviso-consorcios) e nao mostra nenhum.
    ['GET', /^\/api\/consorcios\/?$/, async () => ok({ data: [] })],
    [null, /^\/api\/consorcios(\/|$)/, async () => emMigracao('Consórcios')],
    ['GET', /^\/api\/cartoes\/\d+\/categorias-limite$/, async () => emMigracao('Categoria do cartão')],
    ['GET', /^\/api\/categorias-cartao\/resolver$/, async () => emMigracao('Categoria do cartão')],
];

async function adaptador({ metodo, caminho, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && (!verbo || verbo === metodo)) {
            try {
                return await executar(m, corpo);
            } catch (erro) {
                return falha(mensagemDeErro(erro), 500);
            }
        }
    }
    return emMigracao(`${metodo} ${caminho}`);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    // Quem so le o perfil ve as recorrencias, sem as acoes de escrita (o banco recusaria de qualquer forma).
    const { data: gere } = await supabase.rpc('pode_gerir_perfil', { p_perfil_id: estado.perfilId });
    document.body.classList.toggle('cf-somente-leitura', !gere);
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
