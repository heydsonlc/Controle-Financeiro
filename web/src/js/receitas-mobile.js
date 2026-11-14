// FIN-MVP-MOBILE-04 — Receitas mobile. Le e altera os mesmos registros da tela de Receitas do desktop, pelas mesmas rotas
// do servico comum (js/receitas-servico.js): fontes, previsoes do ano e recebimentos; recebimento (receber_receita, ou
// receber_sem_previsao, ou a contemplacao do consorcio), estorno, remover previsao, nova receita (fonte) e edicao da fonte
// com a atualizacao das previsoes pelo valor-base. A lista, a ordem e os totais sao os do desktop (js/receitas-lista.js).
// Nenhuma regra financeira nova. Sem innerHTML (CSP): tudo por createElement.

import { centavos, dataCurta, deslocarMes, el, reais } from './comum.js';
import { hojeBrasilia } from './adaptador-comum.js';
import { formatarCompetencia } from './despesas-grupos.js';
import { ajustarCadastrosPelaPermissao, aplicarCompetencia, competenciaInicial, prepararMais, prepararModulos } from './mobile-comum.js';
import {
    FALHA_GERAL, SETA, abrirFolha, botao, campo, detalhes, entrada, fecharFolha, folhaDeErro, icone, limparAoEditar,
    mensagem, mostrarAviso, mostrarMensagem, prepararFolha, seletor, texto,
} from './mobile-ui.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import {
    SITUACOES, TIPOS_DO_FILTRO, acoesDaReceita, faltaReceber, formatarTipo, legendaDaReceita,
    montarDataPrevista, montarReceitasMes, recebimentosDaLinha, separarReceitas, totaisDaLista, valorDaLinha,
} from './receitas-lista.js';
import { formularioFonte, lerValor, opcoesDaConta, valorParaCampo } from './receita-formulario.js';
import { configurarReceitas, podeGerirPerfil, responderReceitas } from './receitas-servico.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);

const estado = {
    mes: null,           // 'AAAA-MM'
    fontes: [],
    contas: [],
    orcamentos: [],      // previsoes do ano da competencia (como o desktop)
    realizadas: [],      // recebimentos de janeiro ate a competencia, sem os estornados (como o desktop)
    linhas: [],          // montarReceitasMes
    atrasadasAbertas: false,
    filtros: {},
    somenteLeitura: true,
    pedido: 0,
};

// ---------------------------------------------------------------------------------------------------------------
// Pedidos ao servico: um de cada vez e em ordem (como a ponte-api.js do desktop); o corpo passa por JSON, como o fetch.

let fila = Promise.resolve();
function api(metodo, caminho, corpo = null) {
    const endereco = new URL(caminho, window.location.origin);
    const tarefa = fila.then(async () => {
        try {
            const r = await responderReceitas({ metodo, caminho: endereco.pathname, parametros: endereco.searchParams,
                corpo: corpo === null ? null : JSON.parse(JSON.stringify(corpo)) });
            return r.corpo;
        } catch (erro) {
            console.error('Receitas:', metodo, endereco.pathname, erro);
            return { success: false, error: FALHA_GERAL };
        }
    });
    fila = tarefa.catch(() => {});
    return tarefa;
}

// ---------------------------------------------------------------------------------------------------------------
// Utilitarios da tela

const anoMes = () => `${estado.mes}-01`;
const reaisDe = (valor) => reais(centavos(valor));
const opcoesDeConta = () => opcoesDaConta(estado.contas);

// Resultado de uma operacao concluida: fecha o painel, mostra a mensagem e rele a competencia (lista e totais).
async function concluir(conteudo) {
    fecharFolha();
    mostrarAviso(conteudo, 'ok');
    await carregar();
}

function acoesDoFormulario(form, rotuloSalvar, classe = 'primario') {
    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', fecharFolha);
    const salvar = botao(rotuloSalvar, classe);
    salvar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, salvar);
    form.append(acoes);
    return salvar;
}

// ---------------------------------------------------------------------------------------------------------------
// Carga da competencia: as mesmas leituras da tela do desktop (contas e fontes; previsoes do ano; recebimentos de
// janeiro ate a competencia). Nada e gerado nem gravado ao abrir ou atualizar a pagina.

async function carregar() {
    const pedido = ++estado.pedido;
    const mes = estado.mes;
    const ano = mes.slice(0, 4);
    const lista = $('mob-lista');
    lista.setAttribute('aria-busy', 'true');
    const [contas, fontes, orcamentos, realizadas] = await Promise.all([
        api('GET', '/api/contas?status=ATIVO'),
        api('GET', '/api/receitas/itens'),
        api('GET', `/api/receitas/orcamento?ano=${ano}`),
        api('GET', `/api/receitas/realizadas?ano_mes_inicio=${ano}-01-01&ano_mes_fim=${mes}-01`),
    ]);
    if (pedido !== estado.pedido) return;  // ja trocaram de competencia
    estado.contas = contas.success ? (contas.data || []) : [];
    estado.fontes = fontes.success ? (fontes.data || []) : [];
    estado.orcamentos = orcamentos.success ? (orcamentos.data || []) : [];
    estado.realizadas = realizadas.success ? (realizadas.data || []) : [];
    const erro = [contas, fontes, orcamentos, realizadas].find((r) => !r.success);
    if (erro) mostrarAviso(erro.error || 'Não foi possível carregar as receitas.', 'erro');
    estado.linhas = montarReceitasMes({ orcamentos: estado.orcamentos, realizadas: estado.realizadas, anoMes: anoMes(),
        fontes: estado.fontes, contas: estado.contas });
    desenhar();
    lista.dataset.carregado = mes;
    lista.setAttribute('aria-busy', 'false');
}

// ---------------------------------------------------------------------------------------------------------------
// Resumo, lista do mes e atrasadas

function desenharResumo(doMes) {
    const t = totaisDaLista(doMes);
    const resumo = $('mob-resumo');
    const valores = el('dl', 'mob-resumo-valores');
    for (const [rotulo, valor, chave] of [['Previsto', t.previsto, 'previsto'], ['Recebido', t.recebido, 'recebido'],
        ['Pendente', t.pendente, 'pendente']]) {
        const item = el('div');
        item.dataset.total = chave;
        item.append(el('dt', null, rotulo), el('dd', null, reais(valor)));
        valores.append(item);
    }
    resumo.replaceChildren(valores);
    resumo.hidden = false;
}

function linhaReceita(linha, atrasada = false) {
    const recebimentos = recebimentosDaLinha(linha, estado.realizadas);
    const recebida = linha.status === 'REALIZADA';
    const b = el('button', `mob-linha${recebida ? ' recebida' : ''}`);
    b.type = 'button';
    b.dataset.uid = linha.uid;
    const textoLinha = el('span', 'mob-linha-texto');
    textoLinha.append(el('span', 'mob-linha-nome', linha.nome));
    const legenda = `${atrasada ? `${formatarCompetencia(linha.competencia.slice(0, 7))} · ` : ''}${legendaDaReceita(linha, recebimentos)}`;
    textoLinha.append(el('span', 'mob-linha-data', legenda));
    const valor = reais(valorDaLinha(linha));
    b.append(textoLinha, el('span', 'mob-linha-valor', valor), icone(SETA, 'mob-seta'));
    b.title = linha.nome;
    b.setAttribute('aria-label', `${linha.nome}, ${valor}, ${legenda}. Ver detalhes`);
    b.addEventListener('click', () => abrirDetalhes(linha.uid));
    return b;
}

// "Receitas atrasadas" do desktop: competencias anteriores (do mesmo ano) ainda nao realizadas. Bloco recolhido ao abrir,
// com a quantidade e o que falta receber.
function desenharAtrasadas(atrasadas) {
    const caixa = $('mob-atrasadas');
    caixa.hidden = !atrasadas.length;
    if (!atrasadas.length) {
        caixa.replaceChildren();
        return;
    }
    const falta = atrasadas.reduce((t, r) => t + faltaReceber(r), 0);
    const secao = el('section', 'mob-grupo');
    secao.dataset.grupo = 'atrasadas';
    const cabecalho = el('button', 'mob-grupo-cabecalho');
    cabecalho.type = 'button';
    cabecalho.setAttribute('aria-expanded', estado.atrasadasAbertas ? 'true' : 'false');
    cabecalho.setAttribute('aria-controls', 'mob-grupo-atrasadas');
    const nome = el('span', 'mob-grupo-nome');
    const titulo = el('span', 'mob-grupo-rotulo', 'Receitas atrasadas');
    titulo.append(el('span', 'mob-grupo-qtd', ` (${atrasadas.length})`));
    nome.append(titulo, el('span', 'mob-grupo-detalhe', 'Meses anteriores · a receber'));
    cabecalho.append(nome, el('span', 'mob-grupo-total', reais(falta)), icone(SETA, 'mob-seta'));
    const itens = el('div', 'mob-grupo-itens');
    itens.id = 'mob-grupo-atrasadas';
    itens.hidden = !estado.atrasadasAbertas;
    atrasadas.forEach((r) => itens.append(linhaReceita(r, true)));
    cabecalho.addEventListener('click', () => {
        const abrir = itens.hidden;
        itens.hidden = !abrir;
        cabecalho.setAttribute('aria-expanded', abrir ? 'true' : 'false');
        estado.atrasadasAbertas = abrir;
    });
    secao.append(cabecalho, itens);
    caixa.replaceChildren(secao);
}

function desenhar() {
    const { doMes, atrasadas } = separarReceitas(estado.linhas, anoMes(), estado.filtros);
    desenharResumo(doMes);
    $('mob-lista-titulo').hidden = false;
    const lista = $('mob-lista');
    if (doMes.length) {
        lista.replaceChildren(...doMes.map((r) => linhaReceita(r)));
    } else if (estado.filtros.tipo || estado.filtros.busca) {
        lista.replaceChildren(el('p', 'mob-vazio', 'Nenhuma receita com os filtros escolhidos.'));
    } else {
        const vazio = el('div', 'mob-vazio');
        vazio.append(el('strong', null, 'Nenhuma receita encontrada para o período.'), el('br'),
            estado.somenteLeitura ? '' : 'Use + para cadastrar uma receita.');
        lista.replaceChildren(vazio);
    }
    desenharAtrasadas(atrasadas);
    $('mob-filtro-marca').hidden = !(estado.filtros.tipo || estado.filtros.busca);
}

// ---------------------------------------------------------------------------------------------------------------
// Detalhe da receita (painel inferior) e as operacoes que o desktop permite para ela

const orcamentoDa = (linha) => estado.orcamentos.find((o) => o.id === linha.orcamento_id) || null;

function recorrenciaDa(linha) {
    if (!linha.fonte) return 'Pontual (sem fonte)';
    return linha.fonte.recorrente ? 'Mensal (recorrente)' : 'Não recorrente';
}

function abrirDetalhes(uid) {
    const linha = estado.linhas.find((l) => l.uid === uid);
    if (!linha) return;
    const recebimentos = recebimentosDaLinha(linha, estado.realizadas);
    const orcamento = orcamentoDa(linha);
    const pendente = ['PREVISTA', 'PARCIAL'].includes(linha.status);
    const observacoes = [orcamento && orcamento.observacoes && !/^Gerado automaticamente/.test(orcamento.observacoes) ? orcamento.observacoes : '',
        ...recebimentos.map((r) => r.observacoes)].filter(Boolean).join('\n');
    const pares = [
        ['Descrição', linha.descricao || ''],
        ['Tipo', formatarTipo(linha.tipo)],
        ['Competência', formatarCompetencia(linha.competencia.slice(0, 7))],
        ['Data prevista', linha.dia_previsto_pagamento ? dataCurta(montarDataPrevista(linha.competencia, linha.dia_previsto_pagamento)) : ''],
        ['Valor previsto', linha.origem === 'realizada' ? '' : reaisDe(linha.valor_previsto)],
        ['Valor recebido', reaisDe(linha.valor_realizado)],
        ['Falta receber', pendente ? reais(faltaReceber(linha)) : ''],
        ['Recebimento', recebimentos.length === 1 ? dataCurta(recebimentos[0].data_recebimento) : ''],
        ['Conta bancária', linha.conta ? linha.conta.nome : 'Sem conta padrão'],
        ['Recorrência', recorrenciaDa(linha)],
        ['Situação', linha.origem === 'realizada_pendente' ? 'Prevista · aguardando confirmação' : SITUACOES[linha.status]],
    ];
    const conteudo = [el('p', 'mob-folha-valor', reais(valorDaLinha(linha))), detalhes(pares)];
    if (recebimentos.length > 1) {
        const tabela = el('div', 'mob-tabela');
        for (const r of recebimentos) {
            const item = el('div', 'mob-tabela-linha');
            const conta = estado.contas.find((c) => Number(c.id) === Number(r.conta_bancaria_id));
            const meio = el('span', null, dataCurta(r.data_recebimento));
            meio.append(el('span', 'mob-tabela-sub', conta ? conta.nome : 'Sem conta'));
            item.append(meio, el('span', 'mob-tabela-valor', reaisDe(r.valor_recebido)));
            tabela.append(item);
        }
        conteudo.push(el('p', 'mob-texto discreto', 'Recebimentos'), tabela);
    }
    if (observacoes) conteudo.push(detalhes([['Observações', observacoes]]));
    if (estado.somenteLeitura) {
        conteudo.push(texto('Acesso somente de leitura a este perfil.', 'discreto'));
    } else {
        const pode = acoesDaReceita(linha);
        const acoes = el('div', 'mob-acoes');
        if (pode.receber) {
            const receber = botao('Receber', 'primario');
            receber.addEventListener('click', () => abrirRecebimento(linha));
            acoes.append(receber);
        }
        if (pode.editar) {
            const editar = botao('Editar');
            editar.addEventListener('click', () => abrirFonte(linha.fonte));
            acoes.append(editar);
        }
        if (pode.estornar) {
            const estornar = botao('Estornar', 'perigo');
            estornar.addEventListener('click', () => abrirEstorno(linha));
            acoes.append(estornar);
        }
        if (pode.cancelar) {
            const cancelar = botao('Cancelar previsão', 'perigo');
            cancelar.addEventListener('click', () => abrirCancelamento(linha));
            acoes.append(cancelar);
        }
        if (acoes.childElementCount) conteudo.push(acoes);
        if (linha.status === 'PARCIAL') {
            conteudo.push(texto('Recebimento parcial: o estorno fica para quando a receita estiver totalmente recebida, como no desktop.', 'discreto'));
        }
    }
    abrirFolha(linha.nome, ...conteudo);
}

// Receber ("Consolidar Receita" do desktop): conta, valor (o que falta), data e justificativa. Com previsao na
// competencia, receber_receita (parcial, outra data ou acima do previsto com justificativa; o banco confere o que falta e
// nao duplica); contemplacao do consorcio, a rota propria. A chave da operacao fica a mesma nos reenvios.
function abrirRecebimento(linha) {
    const falta = Math.max(Number(linha.valor_previsto || 0) - Number(linha.valor_realizado || 0), 0);
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const conta = seletor(opcoesDeConta(), (linha.fonte && linha.fonte.conta_bancaria_id) || (linha.conta && linha.conta.id) || '');
    const valor = entrada('text', valorParaCampo(falta), { inputmode: 'decimal', autocomplete: 'off' });
    const data = entrada('date', hojeBrasilia());
    const justificativa = el('textarea');
    justificativa.maxLength = 500;
    justificativa.rows = 2;
    const m = mensagem();
    form.append(texto(`${linha.nome} · ${formatarCompetencia(linha.competencia.slice(0, 7))} · falta ${reaisDe(falta)}`, 'discreto'),
        campo('Conta bancária', conta), campo('Valor recebido', valor), campo('Data do recebimento', data),
        campo('Justificativa (obrigatória acima do que falta)', justificativa),
        texto('Cria um crédito no extrato da conta. Abaixo do que falta, o recebimento é parcial.', 'discreto'), m);
    limparAoEditar(form, m);
    const salvar = acoesDoFormulario(form, 'Receber');
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        const recebido = lerValor(valor.value);
        if (!conta.value || !recebido) { mostrarMensagem(m, 'Selecione a conta bancária e informe o valor recebido.', 'erro'); return; }
        if (!data.value) { mostrarMensagem(m, 'Informe a data do recebimento.', 'erro'); return; }
        salvar.disabled = true;
        mostrarMensagem(m, 'Registrando...');
        const pendenteConsorcio = linha.origem === 'realizada_pendente';
        // O mesmo corpo do desktop (confirmarConsolidacaoComConta); data e justificativa vao no corpo (fora do modal do desktop).
        const corpo = {
            item_receita_id: linha.item_receita_id || undefined, data_recebimento: data.value, valor_recebido: recebido,
            competencia: linha.competencia, conta_bancaria_id: Number(conta.value), descricao: linha.nome || 'Receita',
            justificativa: justificativa.value.trim(),
        };
        if (!pendenteConsorcio) corpo.observacoes = 'Consolidado pelo gerenciamento de receitas';
        const r = await api(pendenteConsorcio ? 'PUT' : 'POST',
            pendenteConsorcio ? `/api/receitas/realizadas/${linha.realizada_id}` : '/api/receitas/realizadas', corpo);
        if (!r.success) {
            mostrarMensagem(m, r.error || 'Erro ao consolidar receita.', 'erro');
            salvar.disabled = false;
            return;
        }
        const contaNome = (estado.contas.find((c) => String(c.id) === conta.value) || {}).nome;
        await concluir(`${r.message || 'Receita registrada com sucesso'}: ${reaisDe(recebido)} em ${contaNome || 'conta'}.`);
    });
    abrirFolha(`Receber: ${linha.nome}`, form);
}

// Estorno do recebimento: o mecanismo do desktop (debito compensatorio; o recebimento original fica no historico).
function abrirEstorno(linha) {
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const data = entrada('date', hojeBrasilia());
    const motivo = el('textarea');
    motivo.rows = 3;
    motivo.maxLength = 500;
    motivo.placeholder = 'Ex: Recebimento lançado por engano';
    const m = mensagem();
    form.append(texto('O estorno não apaga o recebimento original: cria um débito compensatório e preserva o histórico.', 'discreto'),
        detalhes([['Receita', linha.nome], ['Valor recebido', reaisDe(linha.valor_realizado)]]),
        campo('Data do estorno', data), campo('Motivo do estorno', motivo), m);
    limparAoEditar(form, m);
    const salvar = acoesDoFormulario(form, 'Estornar', 'perigo');
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (!data.value) { mostrarMensagem(m, 'Informe a data do estorno.', 'erro'); return; }
        if (!motivo.value.trim()) { mostrarMensagem(m, 'Informe o motivo do estorno.', 'erro'); return; }
        salvar.disabled = true;
        mostrarMensagem(m, 'Estornando...');
        const r = await api('POST', `/api/receitas/realizadas/${linha.realizada_id}/estornar`,
            { data_estorno: data.value, motivo: motivo.value.trim() });
        if (!r.success) {
            mostrarMensagem(m, r.error || 'Erro ao estornar recebimento.', 'erro');
            salvar.disabled = false;
            return;
        }
        await concluir(r.message || 'Recebimento estornado com sucesso.');
    });
    abrirFolha('Estornar recebimento', form);
}

// "Cancelar/ignorar" do desktop: remover a previsao desta competencia (excluir_receita; na fonte recorrente ela fica com
// valor 0, para o valor-base nao voltar neste mes).
function abrirCancelamento(linha) {
    const m = mensagem();
    const voltar = botao('Voltar');
    voltar.addEventListener('click', fecharFolha);
    const confirmar = botao('Cancelar previsão', 'perigo');
    confirmar.addEventListener('click', async () => {
        confirmar.disabled = true;
        const r = await api('POST', '/api/receitas/orcamento', {
            item_receita_id: linha.item_receita_id, ano_mes: linha.competencia, valor_previsto: 0,
            periodicidade: 'MENSAL_FIXA', observacoes: 'Removido pelo usuário',
        });
        if (!r.success) {
            mostrarMensagem(m, r.error || 'Erro ao remover previsão.', 'erro');
            confirmar.disabled = false;
            return;
        }
        await concluir('Previsão removida.');
    });
    const acoes = el('div', 'mob-acoes');
    acoes.append(voltar, confirmar);
    abrirFolha('Cancelar previsão', texto(`Remover a previsão de "${linha.nome}" na competência ${formatarCompetencia(linha.competencia.slice(0, 7))}?\n`
        + `Valor previsto: ${reaisDe(linha.valor_previsto)}. Nenhum saldo muda.`, 'quebras'), m, acoes);
}

// ---------------------------------------------------------------------------------------------------------------
// Nova receita e edicao: o formulario da fonte do desktop ("Nova Fonte de Receita" / "Editar Fonte de Receita"), com os
// mesmos campos gravados. A fonte nova nasce com a sua previsao na competencia aberta (recorrente: 12 meses a partir
// dela). Na edicao, as previsoes gravadas nao mudam; havendo pendentes com outro valor, a previa da atualizacao.

function abrirFonte(fonte = null) {
    const nova = !fonte;
    // FIN-MVP-MOBILE-06: o formulario e o de js/receita-formulario.js (comum ao Registrar Lancamento), sem mudanca.
    const form = formularioFonte({ api, mes: estado.mes, contas: estado.contas, fonte, aoCancelar: fecharFolha,
        aoSalvo: async (r) => {
            if (nova) {
                await concluir(r.message || 'Fonte salva com sucesso.');
                return;
            }
            await oferecerAtualizacao(fonte.id, r.message || 'Fonte salva com sucesso.');
        } });
    abrirFolha(nova ? 'Nova receita' : `Editar: ${fonte.nome}`, form);
}

// Depois de salvar a fonte (como o desktop): previa das previsoes pendentes com outro valor; so atualiza com a
// confirmacao, conferindo a versao da fonte e a quantidade da previa (o banco preserva recebidas, parciais e manuais).
const MOTIVOS = {
    'Recebida (ha recebimento nesta competencia)': 'recebida (há recebimento nesta competência)',
    'Parcialmente recebida': 'parcialmente recebida',
    'Valor alterado manualmente': 'valor alterado manualmente',
    'Data prevista definida manualmente': 'data prevista definida manualmente',
    'Zerada ou removida manualmente': 'zerada ou removida manualmente',
    'Criada ou anotada manualmente': 'criada ou anotada manualmente',
};
const mesAno = (iso) => `${String(iso).slice(5, 7)}/${String(iso).slice(0, 4)}`;

async function oferecerAtualizacao(id, mensagemSalvo, aPartir = null) {
    const r = await api('GET', `/api/receitas/itens/${id}/previa-atualizacao${aPartir ? `?a_partir=${aPartir}` : ''}`);
    if (!r.success) {
        if (aPartir) { folhaDeErro('Atualizar previsões', r.error || 'Não foi possível conferir as previsões.'); return; }
        await concluir(mensagemSalvo);
        return;
    }
    const p = r.data;
    if (!aPartir && !(p.pode_atualizar && p.quantidade > 0)) {
        await concluir(mensagemSalvo);
        return;
    }
    const partir = entrada('month', String(p.a_partir).slice(0, 7));
    partir.addEventListener('change', () => { if (partir.value) oferecerAtualizacao(id, mensagemSalvo, partir.value); });
    const conteudo = [texto(`${mensagemSalvo}\n${p.nome}: valor-base ${reaisDe(p.valor_base)}.`, 'quebras'),
        campo('A partir da competência', partir),
        texto(p.quantidade
            ? `${p.quantidade} previsão(ões) pendente(s) passam para ${reaisDe(p.valor_base)} (diferença ${reaisDe(p.diferenca_total)}). Nenhum recebimento ou saldo muda.`
            : 'Nenhuma previsão pendente a atualizar a partir desta competência.', 'discreto')];
    if (p.quantidade) {
        const tabela = el('div', 'mob-tabela');
        for (const x of p.afetadas) {
            const item = el('div', 'mob-tabela-linha');
            const meio = el('span', null, mesAno(x.competencia));
            meio.append(el('span', 'mob-tabela-sub', `atual ${reaisDe(x.valor_atual)}`));
            item.append(meio, el('span', 'mob-tabela-valor', reaisDe(x.valor_novo)));
            tabela.append(item);
        }
        conteudo.push(tabela);
    }
    const ficam = (p.preservadas || []).filter((x) => x.motivo !== 'Ja no valor-base');
    if (ficam.length) {
        conteudo.push(texto(`Ficam como estão:\n${ficam.map((x) => `${mesAno(x.competencia)} — ${reaisDe(x.valor)}: ${MOTIVOS[x.motivo] || x.motivo}`).join('\n')}`, 'quebras discreto'));
    }
    const m = mensagem();
    const manter = botao('Manter as previsões');
    manter.addEventListener('click', () => concluir(mensagemSalvo));
    const confirmar = botao(`Atualizar ${p.quantidade} previsão(ões)`, 'primario');
    confirmar.disabled = !p.quantidade || !p.pode_atualizar;
    confirmar.addEventListener('click', async () => {
        confirmar.disabled = true;
        const resposta = await api('POST', `/api/receitas/itens/${id}/atualizar-previsoes`,
            { a_partir: String(p.a_partir).slice(0, 7), esperadas: p.quantidade, versao: p.versao });
        if (!resposta.success) {
            mostrarMensagem(m, resposta.error || 'Não foi possível atualizar as previsões.', 'erro');
            await oferecerAtualizacao(id, mensagemSalvo, String(p.a_partir).slice(0, 7));  // previa de novo: algo mudou
            return;
        }
        await concluir(resposta.message);
    });
    const acoes = el('div', 'mob-acoes');
    acoes.append(manter, confirmar);
    conteudo.push(m, acoes);
    abrirFolha('Atualizar previsões pelo valor-base', ...conteudo);
}

// ---------------------------------------------------------------------------------------------------------------
// Filtros num painel compacto: Tipo e Busca, os da tela do desktop (valem para a lista do mes e para o resumo)

function abrirFiltros() {
    const f = estado.filtros;
    const form = el('form', 'mob-form');
    const tipo = seletor(TIPOS_DO_FILTRO, f.tipo || '');
    const busca = entrada('search', f.busca || '', { placeholder: 'Receita, fonte, descrição ou conta' });
    form.append(campo('Tipo', tipo), campo('Buscar', busca));
    const limpar = botao('Limpar');
    const aplicar = botao('Aplicar', 'primario');
    aplicar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(limpar, aplicar);
    form.append(acoes);
    limpar.addEventListener('click', () => { estado.filtros = {}; fecharFolha(); desenhar(); });
    form.addEventListener('submit', (evento) => {
        evento.preventDefault();
        estado.filtros = { tipo: tipo.value, busca: busca.value.trim() };
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
    estado.atrasadasAbertas = false;
    carregar();
}

const usuario = await exigirUsuario();
if (usuario) {
    estado.mes = competenciaInicial();
    prepararModulos();
    ajustarCadastrosPelaPermissao(usuario.id);  // FIN-MVP-MOBILE-06: quem so le recebe o Lancar desabilitado
    prepararMais();
    prepararFolha();
    aplicarCompetencia(estado.mes);
    $('mob-mes-anterior').addEventListener('click', () => trocarMes(-1));
    $('mob-mes-seguinte').addEventListener('click', () => trocarMes(1));
    $('mob-filtros').addEventListener('click', abrirFiltros);
    $('mob-nova').addEventListener('click', () => abrirFonte(null));
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
        // O mesmo perfil em uso no desktop; a fonte nova nasce na competencia aberta aqui. Quem so le o perfil nao ve as
        // acoes de escrita (o banco recusaria de qualquer forma), como a tela do desktop (cf-somente-leitura).
        configurarReceitas(perfil.id, { competencia: () => estado.mes });
        estado.somenteLeitura = !await podeGerirPerfil();
        $('mob-nova').hidden = estado.somenteLeitura;
        await carregar();
    } else {
        $('mob-lista').setAttribute('aria-busy', 'false');
        if ($('mob-aviso').hidden) mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
    }
}
