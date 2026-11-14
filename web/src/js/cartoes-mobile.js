// FIN-MVP-MOBILE-03 — Cartoes de Credito mobile. Le e altera os mesmos registros das telas do desktop, pelas mesmas rotas:
// - js/cartoes-servico.js (tela Cartoes): cartoes ativos do perfil, fatura por Categoria do Cartao, compras da fatura,
//   edicao, exclusao e parcelamento, com as mesmas funcoes do banco, versoes e confirmacoes;
// - js/despesas-servico.js (tela Despesas): a linha da fatura (vencimento, previsto e executado), pagamento e estorno.
// Grupos e totais: js/cartoes-grupos.js (os grupos do desktop, vindos do banco). Nenhuma regra financeira nova; nenhuma
// compra nova por aqui (sera o FIN-MVP-MOBILE-06). Sem innerHTML (CSP): tudo por createElement.

import { centavos, dataCurta, deslocarMes, el, reais } from './comum.js';
import { hojeBrasilia } from './adaptador-comum.js';
import {
    cartoesDaFatura, executadoDaCompra, filtrosAtivos, legendaDaCompra, montarGruposFatura, rotuloCartaoDoContrato,
    situacaoDaCobranca, situacaoDaFatura,
} from './cartoes-grupos.js';
import { configurarCartoes, podeGerirPerfil, responderCartoes } from './cartoes-servico.js';
import { formatarCompetencia } from './despesas-grupos.js';
import { configurarDespesas, responderDespesas } from './despesas-servico.js';
import { aplicarCompetencia, competenciaInicial, prepararMais, prepararModulos, rotuloCompetencia } from './mobile-comum.js';
import { abrirEstorno, abrirPagamento } from './mobile-pagamento.js';
import {
    FALHA_GERAL, SETA, abrirFolha, botao, campo, detalhes, diaMes, entrada, fecharFolha, folhaDeErro, icone, limparAoEditar,
    mensagem, mostrarAviso, mostrarMensagem, prepararFolha, quandoFechar, seletor, texto,
} from './mobile-ui.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);

const estado = {
    mes: null,
    cartaoId: null,
    cartoes: [],
    fatura: null,       // linha da fatura em Despesas (contas_do_mes): vencimento, previsto, executado, situacao
    resumo: null,       // fatura por Categoria do Cartao (tela Cartoes): grupos, creditos, cartoes do contrato
    lancamentos: [],    // compras e creditos da fatura (filtro "todos" do desktop)
    abertos: {},        // grupos expandidos (varios ao mesmo tempo): chave -> true
    filtros: {},
    somenteLeitura: true,
    contas: null,
    categorias: null,
    pedido: 0,
};

// ---------------------------------------------------------------------------------------------------------------
// Pedidos aos servicos: um de cada vez e em ordem (como a ponte-api.js do desktop). A fatura em Despesas e as contas
// bancarias vao ao servico de Despesas; o resto, ao de Cartoes. O corpo passa por JSON, como o fetch do desktop.

const DO_SERVICO_DE_DESPESAS = /^\/api\/(despesas|faturas|contas)(\/|$)/;
let fila = Promise.resolve();
function api(metodo, caminho, corpo = null) {
    const endereco = new URL(caminho, window.location.origin);
    const responder = DO_SERVICO_DE_DESPESAS.test(endereco.pathname) ? responderDespesas : responderCartoes;
    const tarefa = fila.then(async () => {
        try {
            const r = await responder({ metodo, caminho: endereco.pathname, parametros: endereco.searchParams,
                corpo: corpo === null ? null : JSON.parse(JSON.stringify(corpo)) });
            return r.corpo;
        } catch (erro) {
            console.error('Cartões:', metodo, endereco.pathname, erro);
            return { success: false, error: FALHA_GERAL };
        }
    });
    fila = tarefa.catch(() => {});
    return tarefa;
}

async function contasAtivas() {
    if (!estado.contas) {
        const r = await api('GET', '/api/contas?status=ATIVO');
        estado.contas = r.success ? (r.data || []) : [];
    }
    return estado.contas;
}

async function categorias() {
    if (!estado.categorias) {
        const r = await api('GET', '/api/categorias?ativo=true');
        estado.categorias = r.success ? (r.data || []) : [];
    }
    return estado.categorias;
}

// Confirmacao pedida pelo servico (as mesmas perguntas do desktop: abastecimento vinculado, parcelas da compra), no painel.
// Fechar o painel sem escolher conta como Cancelar (o servico nunca fica esperando).
function confirmarNoPainel(pergunta) {
    return new Promise((resolve) => {
        const cancelar = botao('Cancelar');
        const ok = botao('OK', 'primario');
        const decidir = (resposta) => {
            quandoFechar(null);
            cancelar.disabled = true;
            ok.disabled = true;
            resolve(resposta);
        };
        cancelar.addEventListener('click', () => decidir(false));
        ok.addEventListener('click', () => decidir(true));
        const acoes = el('div', 'mob-acoes');
        acoes.append(cancelar, ok);
        abrirFolha('Confirmar', texto(pergunta, 'quebras'), acoes);
        quandoFechar(() => resolve(false));
    });
}

// ---------------------------------------------------------------------------------------------------------------
// Utilitarios da tela

const cartaoAtual = () => estado.cartoes.find((c) => c.id === estado.cartaoId) || null;
const finalDo = (c) => (c && c.config && c.config.numero_cartao) || '';
const nomeDoCartao = (c) => (c ? `${c.nome}${finalDo(c) ? ` · final ${finalDo(c)}` : ''}` : '');
const valorDa = (l) => reais(centavos(l.valor));

// Resultado de uma operacao concluida: fecha o painel, mostra a mensagem e rele a fatura (resumo, grupos e compras).
async function concluir(conteudo) {
    fecharFolha();
    mostrarAviso(conteudo, 'ok');
    await carregar();
}

// Erro de uma operacao: no formulario, se ele ainda esta aberto; senao (o servico abriu uma confirmacao), num painel.
function mostrarErro(form, m, titulo, conteudo) {
    if (form.isConnected) mostrarMensagem(m, conteudo, 'erro');
    else folhaDeErro(titulo, conteudo);
}

function guardarCartaoNoEndereco() {
    const endereco = new URL(window.location.href);
    if (endereco.searchParams.get('cartao') !== String(estado.cartaoId)) {
        endereco.searchParams.set('cartao', String(estado.cartaoId));
        window.history.replaceState(null, '', endereco);
    }
}

// ---------------------------------------------------------------------------------------------------------------
// Cartoes do perfil (os ativos, como a tela do desktop) e fatura da competencia

async function carregarCartoes() {
    const r = await api('GET', '/api/cartoes');
    estado.cartoes = r.success ? (r.data || []) : [];
    if (!r.success) mostrarAviso(r.error || 'Não foi possível carregar os cartões.', 'erro');
    const pedido = Number(new URLSearchParams(window.location.search).get('cartao'));
    estado.cartaoId = (estado.cartoes.find((c) => c.id === pedido) || estado.cartoes[0] || {}).id || null;
    const select = $('mob-cartao');
    select.replaceChildren(...estado.cartoes.map((c) => {
        const opcao = el('option', null, nomeDoCartao(c));
        opcao.value = String(c.id);
        return opcao;
    }));
    if (estado.cartaoId) {
        select.value = String(estado.cartaoId);
        guardarCartaoNoEndereco();
    }
    $('mob-cartao-caixa').hidden = !estado.cartoes.length;
}

async function carregar() {
    const { mes, cartaoId } = estado;
    const pedido = ++estado.pedido;
    estado.contas = null;
    const lista = $('mob-lista');
    lista.setAttribute('aria-busy', 'true');
    if (!cartaoId) {
        estado.fatura = null;
        estado.resumo = null;
        estado.lancamentos = [];
        desenhar();
        lista.dataset.carregado = `${mes}:`;
        lista.setAttribute('aria-busy', 'false');
        return;
    }
    const [faturas, resumo, compras] = await Promise.all([
        api('GET', `/api/faturas?mes_referencia=${mes}`),
        api('GET', `/api/cartoes/${cartaoId}/fatura-categorias?mes_referencia=${mes}`),
        api('GET', `/api/cartoes/${cartaoId}/fatura-lancamentos?mes_referencia=${mes}&categoria_cartao_id=todos`),
    ]);
    if (pedido !== estado.pedido) return;  // ja trocaram de competencia ou de cartao
    estado.fatura = faturas.success ? ((faturas.data || []).find((f) => f.cartao_id === cartaoId) || null) : null;
    estado.resumo = resumo.success ? resumo.data : null;
    estado.lancamentos = compras.success ? ((compras.data && compras.data.lancamentos) || []) : [];
    const erro = [faturas, resumo, compras].find((r) => !r.success);
    if (erro) mostrarAviso(erro.error || 'Não foi possível carregar a fatura.', 'erro');
    desenhar();
    lista.dataset.carregado = `${mes}:${cartaoId}`;
    lista.setAttribute('aria-busy', 'false');
}

// ---------------------------------------------------------------------------------------------------------------
// Resumo da fatura: Vencimento | Previsto | Executado, os da fatura em Despesas (nada somado aqui)

function desenharFatura() {
    const caixa = $('mob-fatura');
    const cartao = cartaoAtual();
    caixa.replaceChildren();
    caixa.hidden = !cartao;
    if (!cartao) return;
    const f = estado.fatura;
    const r = estado.resumo;
    const situacao = situacaoDaFatura(f, r, hojeBrasilia());
    const topo = el('div', 'mob-fatura-topo');
    topo.append(el('span', 'mob-fatura-titulo', `Fatura ${formatarCompetencia(estado.mes)}`),
        el('span', `mob-fatura-situacao${situacao === 'Vencida' ? ' vencida' : ''}`, situacao));
    const valores = el('dl', 'mob-fatura-valores');
    const dia = cartao.config && cartao.config.dia_vencimento;
    for (const [rotulo, valor] of [
        ['Vencimento', f ? diaMes(f.data_vencimento) : (dia ? `Dia ${dia}` : '—')],
        ['Previsto', f ? reais(centavos(f.valor_planejado)) : '—'],
        ['Executado', f ? reais(centavos(f.valor_executado)) : '—'],
    ]) {
        const item = el('div');
        item.append(el('dt', null, rotulo), el('dd', null, valor));
        valores.append(item);
    }
    caixa.append(topo, valores);
    if (r && Number(r.total_creditos || 0) > 0) {
        caixa.append(el('p', 'mob-fatura-nota',
            `Compras ${reais(centavos(r.total_compras))} · créditos −${reais(centavos(r.total_creditos))}`));
    }
    // Pagar so a fatura com compras (sem compras o banco nao paga: dados_pagamento_fatura.pode_pagar); estornar a paga.
    if (f && !estado.somenteLeitura && (f.pago || estado.lancamentos.length)) {
        const acoes = el('div', 'mob-fatura-acoes');
        if (f.pago) {
            const estornar = botao('Estornar pagamento');
            estornar.id = 'mob-estornar-fatura';
            estornar.addEventListener('click', () => abrirEstorno(f, { api, concluir, base: '/api/faturas' }));
            acoes.append(estornar);
        } else {
            const pagar = botao('Pagar fatura', 'primario');
            pagar.id = 'mob-pagar-fatura';
            pagar.addEventListener('click', () => abrirPagamento(f, { api, contasAtivas, concluir, base: '/api/faturas' }));
            acoes.append(pagar);
        }
        caixa.append(acoes);
    }
}

// ---------------------------------------------------------------------------------------------------------------
// Compras da fatura nos grupos do desktop

function linhaCompra(l) {
    const credito = l.natureza === 'CREDITO';
    const linha = el('button', `mob-linha${credito ? ' credito' : ''}`);
    linha.type = 'button';
    linha.dataset.id = String(l.id);
    const textoLinha = el('span', 'mob-linha-texto');
    textoLinha.append(el('span', 'mob-linha-nome', l.descricao || 'Compra'));
    const legenda = legendaDaCompra(l);
    if (legenda) textoLinha.append(el('span', 'mob-linha-data', legenda));
    linha.append(textoLinha, el('span', 'mob-linha-valor', valorDa(l)), icone(SETA, 'mob-seta'));
    linha.title = l.descricao || '';
    linha.setAttribute('aria-label', `${l.descricao}, ${valorDa(l)}${legenda ? `, ${legenda}` : ''}. Ver detalhes`);
    linha.addEventListener('click', () => abrirDetalhes(l.id));
    return linha;
}

function grupoEl(g) {
    const secao = el('section', 'mob-grupo');
    secao.dataset.grupo = g.chave;
    const aberto = Boolean(estado.abertos[g.chave]);
    const cabecalho = el('button', 'mob-grupo-cabecalho');
    cabecalho.type = 'button';
    cabecalho.setAttribute('aria-expanded', aberto ? 'true' : 'false');
    cabecalho.setAttribute('aria-controls', `mob-grupo-${g.chave}`);
    const nome = el('span', 'mob-grupo-nome');
    const titulo = el('span', 'mob-grupo-rotulo', g.rotulo);
    titulo.append(el('span', 'mob-grupo-qtd', ` (${g.quantidade})`));
    nome.append(titulo);
    if (g.limite_centavos !== null) {
        nome.append(el('span', `mob-grupo-limite${g.disponivel_centavos < 0 ? ' negativo' : ''}`,
            `Limite ${reais(g.limite_centavos)} · disponível ${reais(g.disponivel_centavos)}`));
    }
    cabecalho.append(nome, el('span', 'mob-grupo-total', reais(g.total_centavos)), icone(SETA, 'mob-seta'));
    const itens = el('div', 'mob-grupo-itens');
    itens.id = `mob-grupo-${g.chave}`;
    itens.hidden = !aberto;
    if (g.itens.length) g.itens.forEach((l) => itens.append(linhaCompra(l)));
    else itens.append(el('p', 'mob-grupo-vazio', 'Nenhuma compra nesta categoria.'));
    cabecalho.addEventListener('click', () => {
        const abrir = itens.hidden;
        itens.hidden = !abrir;
        cabecalho.setAttribute('aria-expanded', abrir ? 'true' : 'false');
        estado.abertos[g.chave] = abrir;
    });
    secao.append(cabecalho, itens);
    return secao;
}

function desenharLista() {
    const lista = $('mob-lista');
    const cartao = cartaoAtual();
    $('mob-lista-titulo').hidden = !cartao;
    if (!cartao) {
        lista.replaceChildren(el('p', 'mob-vazio', estado.cartoes.length ? '' : 'Nenhum cartão ativo neste perfil.'));
        return;
    }
    if (!estado.lancamentos.length) {
        const vazio = el('div', 'mob-vazio');
        vazio.append(el('strong', null, 'Nenhuma compra nesta competência'), el('br'),
            `Este cartão não possui compras registradas em ${rotuloCompetencia(estado.mes)}.`);
        lista.replaceChildren(vazio);
        return;
    }
    const grupos = montarGruposFatura(estado.resumo, estado.lancamentos, estado.filtros);
    lista.replaceChildren(...grupos.map(grupoEl));
    if (!grupos.length) lista.append(el('p', 'mob-vazio', 'Nenhuma compra com os filtros escolhidos.'));
}

function desenhar() {
    desenharFatura();
    desenharLista();
    $('mob-filtro-marca').hidden = !filtrosAtivos(estado.filtros);
}

// ---------------------------------------------------------------------------------------------------------------
// Detalhe da compra (painel inferior) e operacoes que o desktop ja permite para ela

const TIPOS_CREDITO = { ESTORNO: 'Estorno de compra', IOF_DEVOLVIDO: 'Devolução de IOF', AJUSTE: 'Crédito ou ajuste da fatura' };

function abrirDetalhes(id) {
    const l = estado.lancamentos.find((x) => x.id === id);
    if (!l) return;
    const cartao = cartaoAtual();
    const credito = l.natureza === 'CREDITO';
    const vinculado = l.cartao_vinculado && l.cartao_vinculado.final ? ` · •••• ${l.cartao_vinculado.final}` : '';
    const pares = [
        ['Data', dataCurta(l.data)],
        ['Cartão', `${cartao ? cartao.nome : ''}${vinculado}`],
        ['Competência', formatarCompetencia(estado.mes)],
    ];
    if (credito) {
        pares.push(['Tipo', TIPOS_CREDITO[l.natureza_credito] || l.categoria_nome || 'Crédito da fatura'],
            ['Compra original', l.compra_original ? `${l.compra_original.descricao} (${reais(centavos(l.compra_original.valor))})` : 'Sem compra vinculada']);
    } else {
        pares.push(
            ['Parcela', Number(l.parcelas_total || 1) > 1 ? `${l.parcela_atual || 1} de ${l.parcelas_total}` : ''],
            ['Recorrência', l.natureza === 'FIXA' ? 'Despesa fixa do cartão' : ''],
            ['Previsto', l.natureza === 'FIXA' && l.valor_previsto !== null && l.valor_previsto !== undefined ? reais(centavos(l.valor_previsto)) : ''],
            ['Executado', l.natureza === 'FIXA' ? reais(centavos(executadoDaCompra(l))) : ''],
            ['Categoria', l.categoria_nome || 'Sem categoria'],
            ['Categoria do Cartão', l.categoria_cartao_nome || (l.natureza === 'CATEGORIA' || l.natureza === 'OUTROS' ? 'Sem Categoria do Cartão' : '')],
        );
    }
    pares.push(['Situação da cobrança', situacaoDaCobranca(l)]);
    if (!credito && l.bloqueio) pares.push(['Alteração', l.bloqueio]);
    const conteudo = [el('p', 'mob-folha-valor', valorDa(l)), detalhes(pares)];
    if (estado.somenteLeitura) {
        conteudo.push(texto('Acesso somente de leitura a este perfil.', 'discreto'));
    } else if (!credito) {
        // As acoes do desktop para a compra (o credito nao tem acoes). O banco confere tudo de novo (bloqueio, permissao e
        // versao lida); uma recusa aparece no painel.
        const acoes = el('div', 'mob-acoes');
        if (l.pode_editar) {
            const editar = botao('Editar');
            editar.addEventListener('click', () => abrirEdicao(l));
            acoes.append(editar);
        }
        if (Number(l.parcelas_total || 1) > 1 && l.compra_id) {
            const parcelas = botao('Parcelamento');
            parcelas.addEventListener('click', () => abrirParcelamento(l));
            acoes.append(parcelas);
        }
        const excluir = botao('Excluir', 'perigo');
        excluir.addEventListener('click', () => abrirExclusao(l));
        acoes.append(excluir);
        conteudo.push(acoes);
    }
    abrirFolha(l.descricao || 'Compra', ...conteudo);
}

// Edicao: os campos do desktop (descricao, valor, data e Categoria de Despesa); numero e total de parcelas nao mudam por
// aqui (regra do banco), so aparecem. A mesma rota: o servico pergunta pelo abastecimento vinculado quando houver.
async function abrirEdicao(l) {
    const lista = await categorias();
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const descricao = entrada('text', l.descricao, { required: '', maxlength: '200' });
    const valor = entrada('number', Number(l.valor).toFixed(2), { step: '0.01', min: '0', inputmode: 'decimal', required: '' });
    const data = entrada('date', l.data || '', { required: '' });
    const categoria = seletor([['', 'Selecione uma categoria'], ...lista.map((c) => [c.id, c.nome])], l.categoria_id);
    const m = mensagem();
    form.append(campo('Descrição', descricao), campo('Valor', valor), campo('Data da compra', data), campo('Categoria de Despesa', categoria));
    if (Number(l.parcelas_total || 1) > 1) {
        form.append(texto(`Parcela ${l.parcela_atual || 1} de ${l.parcelas_total}. Para mudar as próximas parcelas, use “Parcelamento”.`, 'discreto'));
    }
    form.append(m);
    limparAoEditar(form, m);
    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', fecharFolha);
    const salvar = botao('Salvar', 'primario');
    salvar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, salvar);
    form.append(acoes);
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (!descricao.value.trim()) { mostrarMensagem(m, 'Informe a descrição.', 'erro'); return; }
        if (!(parseFloat(valor.value) >= 0) || valor.value === '') { mostrarMensagem(m, 'Informe um valor válido.', 'erro'); return; }
        if (!data.value) { mostrarMensagem(m, 'Informe a data da compra.', 'erro'); return; }
        salvar.disabled = true;
        mostrarMensagem(m, 'Salvando...');
        // O mesmo corpo do formulario do desktop (salvarEdicaoLancamento).
        const r = await api('PUT', `/api/cartoes/lancamentos/${l.id}`, {
            descricao: descricao.value.trim(),
            valor: parseFloat(valor.value),
            data_compra: data.value,
            categoria_id: categoria.value || null,
            numero_parcela: Number(l.parcela_atual) || 1,
            total_parcelas: Number(l.parcelas_total) || 1,
        });
        if (!r.success && String(r.error || '').startsWith('Alteração cancelada')) {  // desistiu na confirmacao do abastecimento
            fecharFolha();
            mostrarAviso(r.error);
            return;
        }
        if (!r.success) {
            mostrarErro(form, m, `Editar: ${l.descricao}`, `Erro ao salvar lançamento: ${r.error || FALHA_GERAL}`);
            salvar.disabled = false;
            return;
        }
        await concluir('Lançamento atualizado.');
    });
    abrirFolha(`Editar: ${l.descricao}`, form);
}

// Exclusao: a confirmacao do desktop; na compra parcelada o servico pergunta de novo, com quantas parcelas saem e quantas
// ficam (as de fatura paga ou fechada nunca saem).
function abrirExclusao(l) {
    const m = mensagem();
    const voltar = botao('Voltar');
    voltar.addEventListener('click', fecharFolha);
    const confirmar = botao('Excluir', 'perigo');
    const caixa = el('div');
    confirmar.addEventListener('click', async () => {
        confirmar.disabled = true;
        const r = await api('DELETE', `/api/cartoes/lancamentos/${l.id}`);
        if (!r.success) {
            if (String(r.error || '').startsWith('Exclusão cancelada')) {  // desistiu na segunda confirmacao: nada foi excluido
                fecharFolha();
                mostrarAviso(r.error);
                return;
            }
            mostrarErro(caixa, m, `Excluir: ${l.descricao}`, `Erro ao excluir lançamento: ${r.error || FALHA_GERAL}`);
            confirmar.disabled = false;
            return;
        }
        const n = Number(r.excluidas || 0);
        await concluir(n > 1 ? `Lançamento excluído (${n} parcelas).` : 'Lançamento excluído.');
    });
    const acoes = el('div', 'mob-acoes');
    acoes.append(voltar, confirmar);
    caixa.append(texto(`Excluir o lançamento "${l.descricao}"?\nEsta ação não pode ser desfeita.`, 'quebras'), m, acoes);
    abrirFolha('Excluir lançamento', caixa);
}

// Parcelamento: o conjunto de parcelas e a alteracao ou o cancelamento so das futuras (as anteriores nao mudam), como o
// "Gerenciar parcelamento" do desktop.
const SITUACOES_PARCELA = { paga: 'Paga', fechada: 'Fechada', passada: 'Passada', atual: 'Atual', futura: 'Futura' };
const competenciaCurta = (c) => (c && /^\d{4}-\d{2}/.test(c) ? `${c.slice(5, 7)}/${c.slice(0, 4)}` : (c || '—'));

async function abrirParcelamento(l) {
    const r = await api('GET', `/api/cartoes/lancamentos/${l.id}/parcelamento`);
    if (!r.success) {
        folhaDeErro('Parcelamento', `Erro ao carregar parcelamento: ${r.error || FALHA_GERAL}`);
        return;
    }
    const base = r.data.base || {};
    const parcelas = r.data.parcelas || [];
    const lista = await categorias();
    const editaveis = Number(base.futuras_editaveis || 0);
    const resumo = detalhes([
        ['Cartão', base.cartao_nome], ['Valor da parcela', reais(centavos(base.valor))],
        ['Parcela atual', `${base.parcela_atual || '-'}/${base.total_parcelas || '-'}`],
        ['Primeira competência', competenciaCurta(base.primeira_competencia)], ['Última competência', competenciaCurta(base.ultima_competencia)],
        ['Categoria da despesa', base.categoria_nome || '-'], ['Futuras editáveis', String(editaveis)],
    ]);
    const tabela = el('div', 'mob-parcelas');
    for (const p of parcelas) {
        const linha = el('div', 'mob-parcela');
        const meio = el('span');
        meio.append(el('span', null, competenciaCurta(p.competencia)), el('br'),
            el('span', 'mob-parcela-situacao', `${SITUACOES_PARCELA[p.status] || 'Futura'} · ${p.editavel ? 'editável' : 'preservada'}`));
        linha.append(el('span', null, String(p.parcela || '-')), meio, el('span', 'mob-parcela-valor', reais(centavos(p.valor))));
        tabela.append(linha);
    }
    if (!parcelas.length) tabela.append(el('p', 'mob-grupo-vazio', 'Nenhuma parcela relacionada encontrada.'));
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const descricao = entrada('text', base.descricao || '', { maxlength: '200' });
    const categoria = seletor([['', 'Selecione uma categoria'], ...lista.map((c) => [c.id, c.nome])], base.categoria_id);
    const valor = entrada('number', base.valor || '', { step: '0.01', min: '0', inputmode: 'decimal' });
    const m = mensagem();
    form.append(campo('Descrição para parcelas futuras', descricao), campo('Categoria da Despesa', categoria),
        campo('Valor das parcelas futuras', valor));
    if (!editaveis) form.append(texto('Nenhuma parcela futura editável: as parcelas atuais e as anteriores não mudam por aqui.', 'discreto'));
    form.append(m);
    limparAoEditar(form, m);
    const cancelarFuturas = botao('Cancelar parcelas futuras', 'perigo');
    const salvar = botao('Salvar alterações futuras', 'primario');
    salvar.type = 'submit';
    cancelarFuturas.disabled = !editaveis;
    salvar.disabled = !editaveis;
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelarFuturas, salvar);
    form.append(acoes);
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        salvar.disabled = true;
        mostrarMensagem(m, 'Salvando...');
        const resposta = await api('PUT', `/api/cartoes/lancamentos/${base.id}/parcelamento/futuras`, {
            descricao: descricao.value.trim(), categoria_id: categoria.value || null, valor: valor.value || null });
        if (!resposta.success) {
            mostrarMensagem(m, `Erro ao atualizar parcelas futuras: ${resposta.error || FALHA_GERAL}`, 'erro');
            salvar.disabled = false;
            return;
        }
        await concluir(`${(resposta.data && resposta.data.atualizadas) || 0} parcela(s) futura(s) atualizada(s).`);
    });
    cancelarFuturas.addEventListener('click', () => confirmarCancelarFuturas(base));
    abrirFolha(`Parcelamento: ${base.descricao || l.descricao}`, resumo, tabela, form);
}

function confirmarCancelarFuturas(base) {
    const m = mensagem();
    const voltar = botao('Voltar');
    voltar.addEventListener('click', fecharFolha);
    const confirmar = botao('Cancelar parcelas futuras', 'perigo');
    confirmar.addEventListener('click', async () => {
        confirmar.disabled = true;
        const r = await api('POST', `/api/cartoes/lancamentos/${base.id}/parcelamento/cancelar-futuras`);
        if (!r.success) {
            mostrarMensagem(m, `Erro ao cancelar parcelas futuras: ${r.error || FALHA_GERAL}`, 'erro');
            confirmar.disabled = false;
            return;
        }
        await concluir(`${(r.data && r.data.canceladas) || 0} parcela(s) futura(s) cancelada(s).`);
    });
    const acoes = el('div', 'mob-acoes');
    acoes.append(voltar, confirmar);
    abrirFolha('Cancelar parcelas futuras', texto('Esta ação afetará apenas as parcelas futuras deste parcelamento. '
        + 'As parcelas anteriores não serão alteradas.'), m, acoes);
}

// ---------------------------------------------------------------------------------------------------------------
// Filtros num painel compacto: cartao do contrato (o "Ver lancamentos" por cartao do desktop) e situacao

function abrirFiltros() {
    const f = estado.filtros;
    const form = el('form', 'mob-form');
    const doContrato = cartoesDaFatura(estado.resumo);
    let vinculado = null;
    if (doContrato.length) {
        vinculado = seletor([['', 'Todos os cartões'], ...doContrato.map((c) => [c.id, rotuloCartaoDoContrato(c)])], f.vinculado || '');
        form.append(campo('Cartão do contrato', vinculado));
    }
    const situacao = seletor([['', 'Todas'], ['revisar', 'A revisar (sem Categoria do Cartão ou sem limite)'],
        ['prevista', 'Previstas aguardando cobrança']], f.situacao || '');
    form.append(campo('Situação', situacao));
    const limpar = botao('Limpar');
    const aplicar = botao('Aplicar', 'primario');
    aplicar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(limpar, aplicar);
    form.append(acoes);
    limpar.addEventListener('click', () => { estado.filtros = {}; fecharFolha(); desenhar(); });
    form.addEventListener('submit', (evento) => {
        evento.preventDefault();
        estado.filtros = { vinculado: vinculado ? vinculado.value : '', situacao: situacao.value };
        fecharFolha();
        desenhar();
    });
    abrirFolha('Filtros', form);
}

// ---------------------------------------------------------------------------------------------------------------
// Inicio

function trocarMes(delta) {
    estado.mes = deslocarMes(estado.mes, delta);
    aplicarCompetencia(estado.mes);
    mostrarAviso('');
    fecharFolha();
    estado.abertos = {};  // nova competencia: grupos recolhidos (o cartao escolhido fica)
    carregar();
}

function trocarCartao() {
    estado.cartaoId = Number($('mob-cartao').value) || null;
    guardarCartaoNoEndereco();
    mostrarAviso('');
    estado.abertos = {};
    estado.filtros = {};  // os cartoes do contrato sao de cada cartao
    carregar();
}

const usuario = await exigirUsuario();
if (usuario) {
    estado.mes = competenciaInicial();
    prepararModulos();
    prepararMais();
    prepararFolha();
    aplicarCompetencia(estado.mes);
    $('mob-mes-anterior').addEventListener('click', () => trocarMes(-1));
    $('mob-mes-seguinte').addEventListener('click', () => trocarMes(1));
    $('mob-filtros').addEventListener('click', abrirFiltros);
    $('mob-cartao').addEventListener('change', trocarCartao);
    let perfil = null;
    try {
        const perfis = await carregarPerfis();
        perfil = escolherPerfilAtivo(perfis, usuario.id);
        if (perfil) salvarPerfilAtivo(usuario.id, perfil.id);
    } catch (_erro) {
        mostrarAviso('Não foi possível carregar os perfis financeiros.', 'erro');
    }
    if (perfil) {
        $('mob-perfil').textContent = perfil.nome || '';
        // O mesmo perfil em uso no desktop. Quem so le o perfil nao ve as acoes de escrita (o banco recusaria de qualquer
        // forma), como a tela do desktop (cf-somente-leitura).
        configurarCartoes(perfil.id, { confirmar: confirmarNoPainel });
        configurarDespesas(perfil.id);
        estado.somenteLeitura = !await podeGerirPerfil();
        await carregarCartoes();
        await carregar();
    } else {
        $('mob-lista').setAttribute('aria-busy', 'false');
        if ($('mob-aviso').hidden) mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
    }
}
