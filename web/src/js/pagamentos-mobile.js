// FIN-MVP-MOBILE-08 — Pagamentos mobile. Consulta as obrigacoes pendentes da competencia e registra a baixa pelos fluxos do
// desktop, sem regra financeira nova:
//   - leitura: GET /api/pagamentos (js/despesas-servico.js): as mesmas linhas da lista de Despesas, SEM gerar recorrencias
//     (consultar nao grava nada); grupos, agrupador semanal e valores pelas regras de js/despesas-grupos.js;
//   - uma obrigacao selecionada: o pagamento individual comum (js/mobile-pagamento.js -> pagar_despesa ou pagar_fatura),
//     com data, conta e valor diferente do previsto classificado e justificado;
//   - recorrencia semanal agrupada selecionada: o pagamento em lote existente (pagar_despesas_lote, P20/P21), que paga
//     todas as ocorrencias pendentes dela na competencia, numa so transacao.
// Decisao do titular (15/11/2026, opcao A): o banco so paga em lote as ocorrencias de uma mesma recorrencia; obrigacoes
// diferentes nao sao selecionadas juntas (a tela explica). Quem so le o perfil consulta, sem selecao nem pagamento; o banco
// recusa de qualquer forma. Sem innerHTML (CSP): tudo por createElement.

import { hojeBrasilia } from './adaptador-comum.js';
import { centavos, dataCurta, deslocarMes, el, reais } from './comum.js';
import {
    FORMAS_FILTRO, agruparDespesasSemanais, estaPaga, formatarCompetencia, formatarTipoRecorrencia, montarGrupos,
    obterFormaPagamentoDespesa, obterValorDespesa,
} from './despesas-grupos.js';
import { configurarDespesas, podeGerirPerfil, responderDespesas } from './despesas-servico.js';
import { abrirLote, abrirPagamento } from './mobile-pagamento.js';
import {
    FALHA_GERAL, SETA, abrirFolha, botao, detalhes, diaMes, fecharFolha, icone, mostrarAviso, prepararFolha, texto,
} from './mobile-ui.js';
import { ajustarCadastrosPelaPermissao, aplicarCompetencia, competenciaInicial, prepararMais, prepararModulos } from './mobile-comum.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);

const estado = {
    mes: null,
    obrigacoes: [],  // pendentes da competencia (nem pagas, nem com a obrigacao cancelada)
    fechados: {},  // grupos recolhidos pelo usuario (abertos por padrao: a tela e de execucao)
    selecao: null,  // uma unidade: { chave, tipo: 'despesa' | 'semanal', id | nome+competencia }
    somenteLeitura: true,
    contas: null,
    pedido: 0,
};

const AVISO_UMA_POR_VEZ = 'O pagamento em lote reúne só as ocorrências de uma mesma recorrência semanal. '
    + 'Para pagar outra obrigação, desmarque a selecionada.';

// ---------------------------------------------------------------------------------------------------------------
// Pedidos ao servico de Despesas: um de cada vez e em ordem (como a ponte-api.js do desktop e as outras paginas mobile).

let fila = Promise.resolve();
function api(metodo, caminho, corpo = null) {
    const endereco = new URL(caminho, window.location.origin);
    const tarefa = fila.then(async () => {
        try {
            const r = await responderDespesas({ metodo, caminho: endereco.pathname, parametros: endereco.searchParams,
                corpo: corpo === null ? null : JSON.parse(JSON.stringify(corpo)) });
            return r.corpo;
        } catch (erro) {
            console.error('Pagamentos:', metodo, endereco.pathname, erro);
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

// ---------------------------------------------------------------------------------------------------------------
// Regras de exibicao (as do desktop): pendente, pagavel e o valor que o pagamento sugere

// P23: a obrigacao cancelada fica com status 'Dispensada' e continua em contas_do_mes; o lote do banco a deixa de fora.
const pendente = (d) => !estaPaga(d) && d.status_pagamento !== 'Dispensada';
const ehFatura = (d) => d.is_fatura_cartao === true;
// Fatura: o executado consolidado e o valor sugerido (sem compras nao ha o que pagar); despesa: o valor da conta.
const valorAPagar = (d) => centavos(ehFatura(d) ? d.valor_executado : d.valor);
const pagavel = (d) => valorAPagar(d) > 0;
const vencida = (d) => Boolean(d.data_vencimento) && d.data_vencimento < hojeBrasilia();
const NOMES_FORMA = Object.fromEntries(FORMAS_FILTRO.filter(([k]) => k).concat([['nao_informado', 'Não informado'], ['outros', 'Outros']]));
const nomeForma = (d) => NOMES_FORMA[obterFormaPagamentoDespesa(d)] || 'Não informado';

function agrupadorAtual(nome, competencia) {
    return agruparDespesasSemanais(estado.obrigacoes)
        .find((a) => a.tipo === 'agrupador_semanal' && a.nome === nome && a.mes_competencia === competencia) || null;
}

// As ocorrencias pendentes de agora do agrupador (null se ele nao existe mais), para o painel do lote conferir.
function pendentesDoAgrupador(nome, competencia) {
    const agrupador = agrupadorAtual(nome, competencia);
    return agrupador ? agrupador.ocorrencias.filter(pendente) : null;
}

// Obrigacoes da unidade selecionada (uma despesa ou fatura; ou as ocorrencias pendentes do agrupador semanal).
function obrigacoesDaSelecao() {
    const s = estado.selecao;
    if (!s) return [];
    if (s.tipo === 'semanal') return pendentesDoAgrupador(s.nome, s.competencia) || [];
    const d = estado.obrigacoes.find((x) => x.id === s.id);
    return d ? [d] : [];
}

// ---------------------------------------------------------------------------------------------------------------
// Lista

async function carregar() {
    const mes = estado.mes;
    const pedido = ++estado.pedido;
    estado.contas = null;
    const lista = $('mob-lista');
    lista.setAttribute('aria-busy', 'true');
    const r = await api('GET', `/api/pagamentos?mes_referencia=${mes}`);
    if (pedido !== estado.pedido) return;  // ja trocaram de competencia
    estado.obrigacoes = r.success ? (r.data || []).filter(pendente) : [];
    if (!r.success) mostrarAviso(r.error || 'Não foi possível carregar os pagamentos.', 'erro');
    // A selecao so continua se a unidade ainda estiver pendente (depois de pagar ou de outra tela mudar a lista).
    if (estado.selecao && !obrigacoesDaSelecao().length) estado.selecao = null;
    desenhar();
    lista.dataset.competenciaCarregada = mes;
    lista.setAttribute('aria-busy', 'false');
}

function marcador(chave, rotulo, disponivel, motivo) {
    const caixa = el('label', 'mob-pag-marca');
    const entrada = document.createElement('input');
    entrada.type = 'checkbox';
    entrada.dataset.chave = chave;
    entrada.checked = Boolean(estado.selecao && estado.selecao.chave === chave);
    entrada.setAttribute('aria-label', `Selecionar ${rotulo}`);
    if (!disponivel) {
        entrada.disabled = true;
        caixa.title = motivo;
    }
    caixa.append(entrada);
    return { caixa, entrada };
}

function linhaObrigacao(d) {
    const linha = el('div', 'mob-pag-linha');
    linha.dataset.id = String(d.id);
    const chave = `d:${d.id}`;
    const abrir = el('button', 'mob-pag-abrir');
    abrir.type = 'button';
    const textoLinha = el('span', 'mob-linha-texto');
    textoLinha.append(el('span', 'mob-linha-nome', d.nome || 'Despesa'));
    const sub = [d.data_vencimento ? `Venc. ${diaMes(d.data_vencimento)}` : ''];
    if (ehFatura(d)) sub.push(pagavel(d) ? `executado ${reais(valorAPagar(d))}` : 'sem compras a pagar');
    textoLinha.append(el('span', 'mob-linha-data', sub.filter(Boolean).join(' · ')));
    const valor = reais(centavos(obterValorDespesa(d)));
    abrir.append(textoLinha, el('span', 'mob-linha-valor', valor), icone(SETA, 'mob-seta'));
    abrir.setAttribute('aria-label', `${d.nome}, ${valor}. Ver detalhes`);
    abrir.addEventListener('click', () => abrirDetalhes(d.id));
    if (!estado.somenteLeitura) {
        const { caixa, entrada } = marcador(chave, d.nome, pagavel(d), 'Fatura sem compras: nada a pagar.');
        entrada.addEventListener('change', () => alternar(entrada, { chave, tipo: 'despesa', id: d.id }));
        linha.append(caixa);
    }
    linha.append(abrir);
    return linha;
}

function linhaAgrupador(item) {
    const { agrupador, totais } = item;
    const linha = el('div', 'mob-pag-linha');
    linha.dataset.agrupador = agrupador.nome;
    const chave = `s:${agrupador.nome}|${agrupador.mes_competencia}`;
    const abrir = el('button', 'mob-pag-abrir');
    abrir.type = 'button';
    const textoLinha = el('span', 'mob-linha-texto');
    textoLinha.append(el('span', 'mob-linha-nome', agrupador.nome),
        el('span', 'mob-linha-data', `${totais.total_ocorrencias} ocorrência(s) pendente(s) · ${formatarTipoRecorrencia(agrupador.ocorrencias[0].tipo_recorrencia).toLowerCase()}`));
    abrir.append(textoLinha, el('span', 'mob-linha-valor', reais(totais.valor_centavos)), icone(SETA, 'mob-seta'));
    abrir.setAttribute('aria-label', `${agrupador.nome}, ${reais(totais.valor_centavos)}. Ver ocorrências`);
    abrir.addEventListener('click', () => abrirAgrupador(agrupador.nome, agrupador.mes_competencia));
    if (!estado.somenteLeitura) {
        const { caixa, entrada } = marcador(chave, `${agrupador.nome} (todas as pendentes)`, totais.valor_centavos > 0, '');
        entrada.addEventListener('change', () => alternar(entrada, { chave, tipo: 'semanal', nome: agrupador.nome,
            competencia: agrupador.mes_competencia }));
        linha.append(caixa);
    }
    linha.append(abrir);
    return linha;
}

function grupoEl(g) {
    const secao = el('section', 'mob-grupo');
    secao.dataset.grupo = g.chave;
    const aberto = !estado.fechados[g.chave];
    const cabecalho = el('button', 'mob-grupo-cabecalho');
    cabecalho.type = 'button';
    cabecalho.setAttribute('aria-expanded', aberto ? 'true' : 'false');
    cabecalho.setAttribute('aria-controls', `mob-grupo-${g.chave}`);
    cabecalho.append(el('span', 'mob-grupo-nome', g.rotulo), el('span', 'mob-grupo-total', reais(g.total_centavos)), icone(SETA, 'mob-seta'));
    const itens = el('div', 'mob-grupo-itens');
    itens.id = `mob-grupo-${g.chave}`;
    itens.hidden = !aberto;
    for (const item of g.itens) itens.append(item.tipo === 'semanal' ? linhaAgrupador(item) : linhaObrigacao(item.despesa));
    cabecalho.addEventListener('click', () => {
        const abrir = itens.hidden;
        itens.hidden = !abrir;
        cabecalho.setAttribute('aria-expanded', abrir ? 'true' : 'false');
        estado.fechados[g.chave] = !abrir;
    });
    secao.append(cabecalho, itens);
    return secao;
}

function desenhar() {
    const grupos = montarGrupos(estado.obrigacoes);
    const lista = $('mob-lista');
    lista.classList.toggle('somente-leitura', estado.somenteLeitura);
    lista.replaceChildren(...grupos.map(grupoEl));
    if (!grupos.length) lista.append(el('p', 'mob-vazio', 'Nenhuma obrigação pendente nesta competência.'));
    atualizarResumo();
}

// Resumo e barra da selecao: so os numeros mudam (sem reler a lista).
function atualizarResumo() {
    const pendenteTotal = estado.obrigacoes.reduce((s, d) => s + centavos(obterValorDespesa(d)), 0);
    const selecionadas = obrigacoesDaSelecao();
    const selecionado = selecionadas.reduce((s, d) => s + valorAPagar(d), 0);
    $('mob-total-pendente').textContent = reais(pendenteTotal);
    $('mob-qtd-selecionadas').textContent = String(selecionadas.length);
    $('mob-total-selecionado').textContent = reais(selecionado);
    $('mob-resumo').hidden = false;
    $('mob-somente-leitura').hidden = !estado.somenteLeitura;
    const barra = $('mob-selecao');
    barra.hidden = estado.somenteLeitura || !estado.obrigacoes.length;
    $('mob-selecao-valor').textContent = reais(selecionado);
    $('mob-limpar').disabled = !estado.selecao;
    const pagar = $('mob-pagar');
    pagar.disabled = !selecionadas.length;
    pagar.textContent = selecionadas.length > 1 ? `Pagar selecionadas (${selecionadas.length})` : 'Pagar selecionada';
    document.querySelectorAll('#mob-lista .mob-pag-marca input').forEach((c) => {
        c.checked = Boolean(estado.selecao && estado.selecao.chave === c.dataset.chave);
    });
}

// Uma unidade por vez (opcao A): marcar outra com uma ja marcada nao seleciona e explica o motivo.
function alternar(entrada, unidade) {
    if (entrada.checked) {
        if (estado.selecao && estado.selecao.chave !== unidade.chave) {
            entrada.checked = false;
            mostrarAviso(AVISO_UMA_POR_VEZ);
            return;
        }
        estado.selecao = unidade;
    } else if (estado.selecao && estado.selecao.chave === unidade.chave) {
        estado.selecao = null;
    }
    mostrarAviso('');
    atualizarResumo();
}

function limparSelecao() {
    estado.selecao = null;
    mostrarAviso('');
    atualizarResumo();
}

// ---------------------------------------------------------------------------------------------------------------
// Pagamento: o individual comum ou o lote da recorrencia semanal; ao concluir, o resultado com "Ver em Contas".

async function concluir(mensagemFinal, dados = {}) {
    estado.selecao = null;
    await carregar();
    const acoes = el('div', 'mob-acoes');
    const continuar = botao('Continuar', dados.conta_bancaria_id ? '' : 'primario');
    continuar.addEventListener('click', fecharFolha);
    acoes.append(continuar);
    if (dados.conta_bancaria_id) {
        // As Contas mobile (MOBILE-07) abrem no mes do pagamento e na conta debitada: o movimento ja gravado, sem outro.
        const mesPagamento = String(dados.data_pagamento || hojeBrasilia()).slice(0, 7);
        const ver = el('a', 'mob-botao primario', 'Ver em Contas');
        ver.id = 'mob-ver-contas';
        ver.href = `contas-mobile.html?mes=${mesPagamento}&conta=${dados.conta_bancaria_id}`;
        acoes.append(ver);
    }
    abrirFolha('Pagamento registrado', texto(mensagemFinal, 'quebras'), acoes);
}

const pagarObrigacao = (d) => abrirPagamento(d, { api, contasAtivas, concluir });
const pagarRecorrencia = (nome, competencia) => abrirLote(nome, competencia, {
    api, contasAtivas, concluir, recarregar: carregar, pendentesDoAgrupador, comData: true,
});

function pagarSelecao() {
    const s = estado.selecao;
    if (!s) return;
    if (s.tipo === 'semanal') {
        pagarRecorrencia(s.nome, s.competencia);
        return;
    }
    const d = estado.obrigacoes.find((x) => x.id === s.id);
    if (d) pagarObrigacao(d);
}

// ---------------------------------------------------------------------------------------------------------------
// Detalhes (dos registros existentes; edicao, exclusao e estorno continuam na Lista de Despesas)

async function abrirDetalhes(id) {
    const d = estado.obrigacoes.find((x) => x.id === id);
    if (!d) return;
    const fatura = ehFatura(d);
    const contas = d.conta_bancaria_id ? await contasAtivas() : [];
    const conta = contas.find((c) => c.id === d.conta_bancaria_id);
    const pares = [
        [fatura ? 'Valor da fatura' : 'Valor previsto', reais(centavos(obterValorDespesa(d)))],
        ['Vencimento', dataCurta(d.data_vencimento)],
        ['Competência', formatarCompetencia(d.mes_competencia)],
        ['Situação', vencida(d) ? 'Vencida' : 'Pendente'],
    ];
    if (fatura) pares.push(['Previsto', reais(centavos(d.valor_planejado))], ['Executado', reais(centavos(d.valor_executado))]);
    pares.push(
        ['Categoria', fatura ? '' : ((d.categoria && d.categoria.nome) || 'Sem categoria')],
        [fatura ? 'Cartão' : 'Conta bancária', fatura ? d.nome : (conta ? (conta.instituicao ? `${conta.nome} (${conta.instituicao})` : conta.nome) : '')],
        ['Forma de pagamento', nomeForma(d)],
        ['Recorrência', fatura ? '' : (d.recorrente ? formatarTipoRecorrencia(d.tipo_recorrencia) : 'Não')],
        ['Parcela', d.total_parcelas > 1 ? `${d.numero_parcela}/${d.total_parcelas}` : ''],
        ['Observações', d.descricao],
    );
    const conteudo = [detalhes(pares)];
    const acoes = el('div', 'mob-acoes');
    const lista = el('a', 'mob-botao', 'Ver na Lista de Despesas');
    lista.href = `despesas-mobile.html?mes=${d.mes_competencia}`;
    acoes.append(lista);
    if (estado.somenteLeitura) {
        conteudo.push(texto('Acesso somente de leitura a este perfil.', 'discreto'));
    } else if (pagavel(d)) {
        const pagar = botao(fatura ? 'Pagar fatura' : 'Pagar', 'primario');
        pagar.addEventListener('click', () => pagarObrigacao(d));
        acoes.append(pagar);
    } else {
        conteudo.push(texto('Fatura sem compras: nada a pagar.', 'discreto'));
    }
    conteudo.push(acoes);
    abrirFolha(d.nome || 'Obrigação', ...conteudo);
}

function abrirAgrupador(nome, competencia) {
    const pendentes = pendentesDoAgrupador(nome, competencia) || [];
    const lista = el('div', 'mob-lista mob-pag-ocorrencias');
    for (const o of pendentes) {
        const linha = el('button', 'mob-linha');
        linha.type = 'button';
        linha.dataset.id = String(o.id);
        const t = el('span', 'mob-linha-texto');
        t.append(el('span', 'mob-linha-nome', o.nome), el('span', 'mob-linha-data', `Venc. ${diaMes(o.data_vencimento)}`));
        linha.append(t, el('span', 'mob-linha-valor', reais(centavos(o.valor))), icone(SETA, 'mob-seta'));
        linha.addEventListener('click', () => abrirDetalhes(o.id));
        lista.append(linha);
    }
    const total = pendentes.reduce((s, o) => s + centavos(o.valor), 0);
    const conteudo = [texto(`${formatarCompetencia(competencia)} · ${pendentes.length} pendente(s) · ${reais(total)}`, 'discreto'), lista];
    if (!estado.somenteLeitura && pendentes.length) {
        const pagar = botao(`Pagar pendentes (${pendentes.length})`, 'primario');
        pagar.addEventListener('click', () => pagarRecorrencia(nome, competencia));
        const acoes = el('div', 'mob-acoes mob-acoes-espaco');
        acoes.append(pagar);
        conteudo.push(acoes);
    }
    abrirFolha(nome, ...conteudo);
}

// ---------------------------------------------------------------------------------------------------------------
// Inicio

function trocarMes(delta) {
    estado.mes = deslocarMes(estado.mes, delta);
    aplicarCompetencia(estado.mes);
    estado.selecao = null;  // outra competencia: nada selecionado (evita pagar obrigacoes de outro periodo)
    estado.fechados = {};
    mostrarAviso('');
    fecharFolha();
    carregar();
}

const usuario = await exigirUsuario();
if (usuario) {
    estado.mes = competenciaInicial();
    prepararModulos();
    ajustarCadastrosPelaPermissao(usuario.id);  // quem so le recebe o Lancar desabilitado (FIN-MVP-MOBILE-06)
    prepararMais();
    prepararFolha();
    aplicarCompetencia(estado.mes);
    $('mob-mes-anterior').addEventListener('click', () => trocarMes(-1));
    $('mob-mes-seguinte').addEventListener('click', () => trocarMes(1));
    $('mob-limpar').addEventListener('click', limparSelecao);
    $('mob-pagar').addEventListener('click', pagarSelecao);
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
        configurarDespesas(perfil.id);
        // A permissao do perfil ativo (pode_gerir_perfil, a mesma do desktop): quem so le nao seleciona nem paga.
        estado.somenteLeitura = !(await podeGerirPerfil());
        await carregar();
    } else {
        $('mob-lista').setAttribute('aria-busy', 'false');
        if ($('mob-aviso').hidden) mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
    }
}
