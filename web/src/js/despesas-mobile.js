// FIN-MVP-MOB-01 — Lista de Despesas mobile. Le e altera os mesmos registros da tela Despesas do desktop, pelas mesmas
// rotas (js/despesas-servico.js: as mesmas funcoes do banco, validacoes, chaves de idempotencia e mensagens) e com as
// mesmas regras de leitura (js/despesas-grupos.js: grupos, ordem, valores, filtros e totais). Nenhuma regra financeira
// nova: pagamento, edicao, estorno, exclusao, cancelamento da obrigacao, interrupcao da recorrencia e pagamento em lote
// seguem os fluxos do desktop (js/original/despesas.js + js/despesas-adaptacoes.js), adaptados a um painel compacto.
// Sem innerHTML (CSP): tudo por createElement.

import { centavos, dataCurta, deslocarMes, el, reais } from './comum.js';
import {
    FORMAS_FILTRO, estaPaga, filtrarDespesas, filtrosAtivos, formatarCompetencia, formatarTipoRecorrencia, montarGrupos,
    obterFormaPagamentoDespesa, obterValorDespesa, totaisDaLista, agruparDespesasSemanais,
} from './despesas-grupos.js';
import { configurarDespesas, responderDespesas } from './despesas-servico.js';
import { abrirEstorno as estornoComum, abrirLote as loteComum, abrirPagamento as pagamentoComum } from './mobile-pagamento.js';
import {
    FALHA_GERAL, SETA, abrirFolha, botao, campo, detalhes, diaMes, entrada, fecharFolha, folhaDeErro, icone, limparAoEditar,
    mensagem, mostrarAviso, mostrarMensagem, prepararFolha, seletor, texto,
} from './mobile-ui.js';
import { ajustarCadastrosPelaPermissao, aplicarCompetencia, competenciaInicial, prepararMais, prepararModulos } from './mobile-comum.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';
import { repartirPorNatureza, textoDaReparticao } from './naturezas.js';
import { carregarNaturezas } from './naturezas-servico.js';

const $ = (id) => document.getElementById(id);

const estado = {
    mes: null,
    despesas: [],
    abertos: {},  // grupos expandidos (varios ao mesmo tempo): chave do grupo -> true
    filtros: {},
    somenteLeitura: true,
    contas: null,
    categorias: null,
    naturezas: null,  // FIN-CATEGORIAS-REORGANIZACAO-01: categoria -> natureza gerencial (so apresentacao)
    pedido: 0,
};

// ---------------------------------------------------------------------------------------------------------------
// Pedidos ao servico: um de cada vez e em ordem, como a ponte-api.js do desktop (a resposta de uma competencia antiga
// nunca chega depois da nova). O corpo passa por JSON, como o fetch do desktop.

let fila = Promise.resolve();
function api(metodo, caminho, corpo = null) {
    const endereco = new URL(caminho, window.location.origin);
    const tarefa = fila.then(async () => {
        try {
            const r = await responderDespesas({ metodo, caminho: endereco.pathname, parametros: endereco.searchParams,
                corpo: corpo === null ? null : JSON.parse(JSON.stringify(corpo)) });
            return r.corpo;
        } catch (erro) {
            console.error('Despesas:', metodo, endereco.pathname, erro);
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
        const r = await api('GET', '/api/categorias');
        estado.categorias = r.success ? (r.data || []) : [];
    }
    return estado.categorias;
}

// ---------------------------------------------------------------------------------------------------------------
// Elementos, painel inferior e aviso: js/mobile-ui.js (comuns as paginas mobile)

const valorDe = (d) => reais(centavos(obterValorDespesa(d)));
const NOMES_FORMA = Object.fromEntries(FORMAS_FILTRO.filter(([k]) => k).concat([['nao_informado', 'Não informado'], ['outros', 'Outros']]));
const nomeForma = (d) => NOMES_FORMA[obterFormaPagamentoDespesa(d)] || 'Não informado';

// Resultado de uma operacao concluida: fecha o painel, mostra a mensagem e relê a competencia (lista e totais).
async function concluir(conteudo) {
    fecharFolha();
    mostrarAviso(conteudo, 'ok');
    await carregar();
}

// ---------------------------------------------------------------------------------------------------------------
// Lista

async function carregar() {
    const mes = estado.mes;
    const pedido = ++estado.pedido;
    estado.contas = null;
    const lista = $('mob-lista');
    lista.setAttribute('aria-busy', 'true');
    const [r, naturezas] = await Promise.all([api('GET', `/api/despesas?mes_referencia=${mes}`), carregarNaturezas()]);
    if (pedido !== estado.pedido) return;  // ja trocaram de competencia
    estado.naturezas = naturezas;
    estado.despesas = r.success ? (r.data || []) : [];
    if (!r.success) mostrarAviso(r.error || 'Não foi possível carregar as despesas.', 'erro');
    desenhar();
    lista.dataset.competenciaCarregada = mes;
    lista.setAttribute('aria-busy', 'false');
}

function linhaDespesa(d) {
    const linha = el('button', `mob-linha${estaPaga(d) ? ' paga' : ''}`);
    linha.type = 'button';
    linha.dataset.id = String(d.id);
    const textoLinha = el('span', 'mob-linha-texto');
    textoLinha.append(el('span', 'mob-linha-nome', d.nome || d.descricao || 'Despesa'));
    if (d.data_vencimento) textoLinha.append(el('span', 'mob-linha-data', `Venc. ${diaMes(d.data_vencimento)}${estaPaga(d) ? ' · paga' : ''}`));
    linha.append(textoLinha, el('span', 'mob-linha-valor', valorDe(d)), icone(SETA, 'mob-seta'));
    linha.title = d.nome || '';
    linha.setAttribute('aria-label', `${d.nome}, ${valorDe(d)}${estaPaga(d) ? ', paga' : ''}. Ver detalhes`);
    linha.addEventListener('click', () => abrirDetalhes(d.id));
    return linha;
}

function linhaAgrupador(item) {
    const { agrupador, totais } = item;
    const linha = el('button', `mob-linha${totais.pagas === totais.total_ocorrencias && totais.total_ocorrencias > 0 ? ' paga' : ''}`);
    linha.type = 'button';
    linha.dataset.agrupador = agrupador.nome;
    const textoLinha = el('span', 'mob-linha-texto');
    textoLinha.append(el('span', 'mob-linha-nome', agrupador.nome),
        el('span', 'mob-linha-data', `${totais.pagas}/${totais.total_ocorrencias} pagas`));
    linha.append(textoLinha, el('span', 'mob-linha-valor', reais(totais.valor_centavos)), icone(SETA, 'mob-seta'));
    linha.setAttribute('aria-label', `${agrupador.nome}, ${reais(totais.valor_centavos)}. Ver ocorrências`);
    linha.addEventListener('click', () => abrirAgrupador(agrupador.nome, agrupador.mes_competencia));
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
    cabecalho.append(el('span', 'mob-grupo-nome', g.rotulo), el('span', 'mob-grupo-total', reais(g.total_centavos)), icone(SETA, 'mob-seta'));
    const itens = el('div', 'mob-grupo-itens');
    itens.id = `mob-grupo-${g.chave}`;
    itens.hidden = !aberto;
    for (const item of g.itens) itens.append(item.tipo === 'semanal' ? linhaAgrupador(item) : linhaDespesa(item.despesa));
    cabecalho.addEventListener('click', () => {
        const abrir = itens.hidden;
        itens.hidden = !abrir;
        cabecalho.setAttribute('aria-expanded', abrir ? 'true' : 'false');
        estado.abertos[g.chave] = abrir;
    });
    secao.append(cabecalho, itens);
    return secao;
}

function desenhar() {
    const visiveis = filtrarDespesas(estado.despesas, estado.filtros);
    const grupos = montarGrupos(visiveis);
    const lista = $('mob-lista');
    lista.replaceChildren(...grupos.map(grupoEl));
    if (!grupos.length) {
        lista.append(el('p', 'mob-vazio', filtrosAtivos(estado.filtros)
            ? 'Nenhuma despesa com os filtros escolhidos.' : 'Nenhuma despesa nesta competência.'));
    }
    const caixa = $('mob-total');
    caixa.replaceChildren();
    if (visiveis.length) {
        const t = totaisDaLista(visiveis);
        const linha = el('div', 'mob-total-linha');
        linha.append(el('span', 'mob-total-rotulo', 'Total'), el('span', 'mob-total-valor', reais(t.total)));
        caixa.append(linha, el('div', 'mob-total-detalhe', `Pendentes ${reais(t.pendentes)} · Pagas ${reais(t.pagas)}`));
        // Consumo e aportes: reparticao do mesmo total (as faturas contam como consumo); nada sai do total.
        if (estado.naturezas) {
            const partes = repartirPorNatureza(visiveis, estado.naturezas, obterValorDespesa);
            if (partes.consumo + partes.aportes + partes.outras === t.total) {
                const detalhe = el('div', 'mob-total-naturezas', textoDaReparticao(partes));
                detalhe.id = 'mob-total-naturezas';
                caixa.append(detalhe);
            }
        }
    }
    caixa.hidden = !visiveis.length;
    $('mob-filtro-marca').hidden = !filtrosAtivos(estado.filtros);
}

// ---------------------------------------------------------------------------------------------------------------
// Detalhes

async function abrirDetalhes(id) {
    const d = estado.despesas.find((x) => x.id === id);
    if (!d) return;
    const fatura = d.is_fatura_cartao === true;
    const paga = estaPaga(d);
    const contas = d.conta_bancaria_id ? await contasAtivas() : [];
    const conta = contas.find((c) => c.id === d.conta_bancaria_id);
    const situacao = paga ? `Paga${d.data_pagamento ? ` em ${dataCurta(d.data_pagamento)}` : ''}` : (d.status_pagamento || 'Pendente');
    const pares = [
        ['Vencimento', dataCurta(d.data_vencimento)],
        ['Competência', formatarCompetencia(d.mes_competencia)],
        ['Situação', situacao],
    ];
    if (fatura) {
        pares.push(['Previsto', reais(centavos(d.valor_planejado))], ['Executado', reais(centavos(d.valor_executado))]);
    }
    pares.push(
        ['Forma de pagamento', nomeForma(d)],
        ['Conta bancária', conta ? (conta.instituicao ? `${conta.nome} (${conta.instituicao})` : conta.nome) : ''],
        ['Categoria', fatura ? '' : ((d.categoria && d.categoria.nome) || 'Sem categoria')],
        ['Recorrência', fatura ? '' : (d.recorrente ? formatarTipoRecorrencia(d.tipo_recorrencia) : 'Não')],
        ['Parcela', d.total_parcelas > 1 ? `${d.numero_parcela}/${d.total_parcelas}` : ''],
        ['Observações', d.descricao],
    );
    const conteudo = [el('p', 'mob-folha-valor', valorDe(d)), detalhes(pares)];
    if (estado.somenteLeitura) {
        conteudo.push(texto('Acesso somente de leitura a este perfil.', 'discreto'));
    } else {
        // As acoes do desktop para a linha: fatura paga/estorna; despesa edita, paga, estorna e exclui. O banco confere tudo
        // de novo (situacao, permissao e versao); uma recusa aparece no painel.
        const acoes = el('div', 'mob-acoes');
        if (!paga) {
            const pagar = botao(fatura ? 'Pagar fatura' : 'Pagar', 'primario');
            pagar.addEventListener('click', () => abrirPagamento(d));
            acoes.append(pagar);
        } else {
            const estornar = botao('Estornar pagamento');
            estornar.addEventListener('click', () => abrirEstorno(d));
            acoes.append(estornar);
        }
        if (!fatura) {
            const editar = botao('Editar');
            editar.addEventListener('click', () => abrirEdicao(d));
            const excluir = botao('Excluir', 'perigo');
            excluir.addEventListener('click', () => abrirExclusao(d));
            acoes.append(editar, excluir);
        }
        conteudo.push(acoes);
    }
    abrirFolha(d.nome || 'Despesa', ...conteudo);
}

// ---------------------------------------------------------------------------------------------------------------
// Pagamento e estorno: o formulario comum (js/mobile-pagamento.js), pelas rotas da lista de Despesas.

const abrirPagamento = (d) => pagamentoComum(d, { api, contasAtivas, concluir });
const abrirEstorno = (d) => estornoComum(d, { api, concluir });

// ---------------------------------------------------------------------------------------------------------------
// Edicao: a mesma rota do desktop (o banco recusa o que nao pode mudar). Parcela de consorcio: so valor e vencimento,
// desta ou desta e das futuras (P24). Pagamento integralmente estornado: so consulta e "Cancelar obrigacao" (P23).

const AVISO_CANCELAMENTO = 'Esta despesa possui um pagamento anteriormente estornado: não pode ser editada. '
    + 'A obrigação pode ser cancelada, preservando o pagamento e o estorno no histórico.';

async function abrirEdicao(d) {
    const r = await api('GET', `/api/despesas/${d.id}`);
    if (!r.success) {
        folhaDeErro(`Editar: ${d.nome}`, `Esta despesa não pode ser editada. ${r.error || ''}`.trim());
        return;
    }
    const dados = r.data;
    if (dados.somente_cancelamento) {
        const cancelar = botao('Cancelar obrigação', 'perigo');
        cancelar.addEventListener('click', () => confirmarCancelamento(d));
        const fechar = botao('Fechar');
        fechar.addEventListener('click', fecharFolha);
        const acoes = el('div', 'mob-acoes');
        acoes.append(fechar, cancelar);
        abrirFolha(`Editar: ${d.nome}`, texto(AVISO_CANCELAMENTO), acoes);
        return;
    }
    if (dados.tipo === 'Consorcio') {
        const unica = botao('Somente esta parcela');
        unica.addEventListener('click', () => formularioConsorcio(dados, 'unica'));
        const futuras = botao('Esta e as futuras');
        futuras.addEventListener('click', () => formularioConsorcio(dados, 'futuras'));
        const acoes = el('div', 'mob-acoes');
        acoes.append(unica, futuras);
        abrirFolha('Editar parcela de consórcio', texto('Esta é uma parcela de consórcio. O que deseja editar?'), acoes);
        return;
    }
    await formularioEdicao(dados);
}

function rodapeFormulario(rotulo, form) {
    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', fecharFolha);
    const salvar = botao(rotulo, 'primario');
    salvar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, salvar);
    form.append(acoes);
    return salvar;
}

async function enviarEdicao(form, salvar, m, caminho, corpo) {
    salvar.disabled = true;
    mostrarMensagem(m, 'Salvando...');
    const r = await api('PUT', caminho, corpo);
    if (!r.success) {
        mostrarMensagem(m, `Erro: ${r.error || FALHA_GERAL}`, 'erro');
        salvar.disabled = false;
        return;
    }
    await concluir(r.message || 'Despesa atualizada com sucesso');
}

async function formularioEdicao(dados) {
    const lista = await categorias();
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const nome = entrada('text', dados.nome, { required: '', maxlength: '200' });
    const valor = entrada('number', Number(dados.valor).toFixed(2), { step: '0.01', min: '0.01', inputmode: 'decimal', required: '' });
    const vencimento = entrada('date', dados.data_vencimento || '', { required: '' });
    const competencia = entrada('month', dados.mes_competencia || '');
    const categoria = seletor([['', 'Selecione...'], ...lista.map((c) => [c.id, c.nome])], dados.categoria_id);
    const observacoes = el('textarea');
    observacoes.value = dados.descricao || '';
    // Recorrente: frequencia, categoria e proximas contas mudam na tela Recorrencias (o banco nao muda por aqui).
    if (dados.recorrente) {
        competencia.disabled = true;
        categoria.disabled = true;
    }
    const m = mensagem();
    form.append(campo('Nome', nome), campo('Valor', valor), campo('Vencimento', vencimento), campo('Competência', competencia),
        campo('Categoria', categoria), campo('Observações', observacoes));
    if (dados.recorrente) {
        form.append(texto(`Recorrência ${formatarTipoRecorrencia(dados.tipo_recorrencia).toLowerCase()}: frequência, categoria e `
            + 'próximas contas são alteradas na tela Recorrências.', 'discreto'));
    }
    form.append(m);
    limparAoEditar(form, m);
    const salvar = rodapeFormulario('Salvar', form);
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (!nome.value.trim()) { mostrarMensagem(m, 'Informe o nome da despesa.', 'erro'); return; }
        if (!(parseFloat(valor.value) > 0)) { mostrarMensagem(m, 'Informe um valor válido.', 'erro'); return; }
        if (!vencimento.value) { mostrarMensagem(m, 'Informe a data de vencimento.', 'erro'); return; }
        if (!dados.recorrente && !categoria.value) { mostrarMensagem(m, 'Selecione a categoria.', 'erro'); return; }
        // O mesmo corpo do formulario do desktop (salvarDespesa).
        await enviarEdicao(form, salvar, m, `/api/despesas/${dados.id}`, {
            nome: nome.value.trim(),
            descricao: observacoes.value.trim(),
            valor: parseFloat(valor.value),
            categoria_id: categoria.value ? parseInt(categoria.value, 10) : dados.categoria_id,
            data_vencimento: vencimento.value || null,
            data_pagamento: dados.data_pagamento || null,
            pago: Boolean(dados.pago),
            recorrente: Boolean(dados.recorrente),
            tipo_recorrencia: dados.tipo_recorrencia,
            mes_competencia: competencia.value || null,
        });
    });
    abrirFolha(`Editar: ${dados.nome}`, form);
}

function formularioConsorcio(dados, escopo) {
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const valor = entrada('number', Number(dados.valor).toFixed(2), { step: '0.01', min: '0.01', inputmode: 'decimal', required: '' });
    const vencimento = entrada('date', dados.data_vencimento || '', { required: '' });
    const m = mensagem();
    form.append(campo('Valor da parcela', valor), campo('Vencimento', vencimento), m);
    limparAoEditar(form, m);
    const salvar = rodapeFormulario('Salvar', form);
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (!(parseFloat(valor.value) > 0)) { mostrarMensagem(m, 'Informe um valor válido.', 'erro'); return; }
        await enviarEdicao(form, salvar, m, `/api/despesas/${dados.id}?tipo_edicao=${escopo}`, {
            nome: dados.nome, descricao: dados.descricao || '', valor: parseFloat(valor.value), categoria_id: dados.categoria_id,
            data_vencimento: vencimento.value || dados.data_vencimento, data_pagamento: null, pago: false, recorrente: false,
            tipo_recorrencia: 'mensal', mes_competencia: dados.mes_competencia || null,
        });
    });
    abrirFolha(escopo === 'unica' ? 'Editar esta parcela' : 'Editar esta e as parcelas futuras', form);
}

// ---------------------------------------------------------------------------------------------------------------
// Exclusao, cancelamento da obrigacao e interrupcao da recorrencia: distintos, como no desktop, e sempre com confirmacao.
// A previa do banco (previa-futuras) decide o que e possivel antes de oferecer a acao.

function confirmarCancelamento(d) {
    const voltar = botao('Voltar');
    voltar.addEventListener('click', fecharFolha);
    const confirmar = botao('Cancelar obrigação', 'perigo');
    const m = mensagem();
    confirmar.addEventListener('click', async () => {
        confirmar.disabled = true;
        const r = await api('DELETE', `/api/despesas/${d.id}?tipo_exclusao=cancelar`);
        if (!r.success) {
            mostrarMensagem(m, `Não foi possível cancelar a obrigação: ${r.error || FALHA_GERAL}`, 'erro');
            confirmar.disabled = false;
            return;
        }
        await concluir(r.message);
    });
    const acoes = el('div', 'mob-acoes');
    acoes.append(voltar, confirmar);
    abrirFolha('Cancelar obrigação', texto('Esta despesa possui um pagamento anteriormente estornado. '
        + 'O cancelamento encerrará a obrigação pendente, preservando o histórico financeiro.'), m, acoes);
}

async function excluirComo(d, caminho, confirmar, m) {
    confirmar.disabled = true;
    const r = await api('DELETE', caminho);
    if (!r.success) {
        mostrarMensagem(m, `Erro ao excluir: ${r.error || FALHA_GERAL}`, 'erro');
        confirmar.disabled = false;
        return;
    }
    await concluir(r.message || 'Despesa excluída com sucesso');
}

async function abrirExclusao(d) {
    const r = await api('GET', `/api/despesas/${d.id}/previa-futuras`);
    if (!r.success) {
        folhaDeErro(`Excluir: ${d.nome}`, r.error || 'Não foi possível conferir a despesa.');
        return;
    }
    const previa = r.data;
    if (previa.pode_cancelar) {
        confirmarCancelamento(d);
        return;
    }
    if (!previa.pode_excluir) {
        folhaDeErro(`Excluir: ${d.nome}`, `Esta despesa não pode ser excluída. ${previa.motivo || ''}`.trim());
        return;
    }
    const m = mensagem();
    const acoes = el('div', 'mob-acoes');
    const voltar = botao('Voltar');
    voltar.addEventListener('click', fecharFolha);
    if (d.tipo === 'Consorcio' || d.recorrente) {
        const unica = botao('Excluir somente esta', 'perigo');
        unica.addEventListener('click', () => excluirComo(d, `/api/despesas/${d.id}?tipo_exclusao=unica`, unica, m));
        const futuras = botao('Excluir esta e as futuras', 'perigo');
        const conteudo = [texto(d.tipo === 'Consorcio'
            ? 'Esta é uma parcela de consórcio. Como deseja excluir?' : 'Esta é uma despesa recorrente. Como deseja excluir?')];
        if (!previa.pode) {
            futuras.disabled = true;
            futuras.title = previa.motivo || '';
            conteudo.push(texto(`Esta e as futuras: ${previa.motivo || 'indisponível.'}`, 'discreto'));
        }
        // "Esta e as futuras" mostra antes o que deixa de ser exigivel e o que fica (o mesmo modal do desktop, P22).
        futuras.addEventListener('click', async () => {
            fecharFolha();
            const feito = await window.CFInterrupcao.interromper({
                titulo: 'Excluir esta e as futuras', rotulo: 'Excluir', previa, contaEscolhida: true,
                executar: (p) => api('DELETE', `/api/despesas/${d.id}?tipo_exclusao=futuras&esperadas=${p.quantidade}`),
            });
            if (feito) await concluir(feito.message);
        });
        acoes.append(voltar, unica, futuras);
        abrirFolha(d.tipo === 'Consorcio' ? 'Excluir parcela de consórcio' : 'Excluir despesa recorrente', ...conteudo, m, acoes);
        return;
    }
    const confirmar = botao('Excluir', 'perigo');
    confirmar.addEventListener('click', () => excluirComo(d, `/api/despesas/${d.id}`, confirmar, m));
    acoes.append(voltar, confirmar);
    abrirFolha(`Excluir: ${d.nome}`, texto(`Tem certeza que deseja excluir a despesa "${d.nome}"? Esta ação não pode ser desfeita.`), m, acoes);
}

// ---------------------------------------------------------------------------------------------------------------
// Recorrencia semanal agrupada: ocorrencias e pagamento das pendentes em lote (P20/P21), como no desktop.

function agrupadorAtual(nome, competencia) {
    return agruparDespesasSemanais(estado.despesas)
        .find((a) => a.tipo === 'agrupador_semanal' && a.nome === nome && a.mes_competencia === competencia) || null;
}

function abrirAgrupador(nome, competencia) {
    const agrupador = agrupadorAtual(nome, competencia);
    if (!agrupador) return;
    const visiveis = new Set(filtrarDespesas(estado.despesas, estado.filtros).map((d) => d.id));
    const ocorrencias = agrupador.ocorrencias.filter((o) => visiveis.has(o.id));
    const pendentes = agrupador.ocorrencias.filter((o) => !o.pago && !o.cancelada);
    const pagas = agrupador.ocorrencias.filter((o) => o.pago).length;
    const lista = el('div', 'mob-lista mob-linha-sub-itens');
    ocorrencias.forEach((o) => lista.append(linhaDespesa(o)));
    const conteudo = [texto(`${formatarCompetencia(competencia)} · ${pagas}/${agrupador.ocorrencias.length} pagas`, 'discreto'), lista];
    if (!estado.somenteLeitura && pendentes.length) {
        const pagar = botao(`Pagar pendentes (${pendentes.length})`, 'primario');
        pagar.addEventListener('click', () => abrirLote(nome, competencia));
        const acoes = el('div', 'mob-acoes mob-acoes-espaco');
        acoes.append(pagar);
        conteudo.push(acoes);
    }
    abrirFolha(nome, ...conteudo);
}

// O painel do lote e o comum (js/mobile-pagamento.js), o mesmo dos Pagamentos mobile (FIN-MVP-MOBILE-08).
const abrirLote = (nome, competencia) => loteComum(nome, competencia, {
    api, contasAtivas, concluir, recarregar: carregar,
    pendentesDoAgrupador: (n, c) => {
        const agrupador = agrupadorAtual(n, c);
        return agrupador ? agrupador.ocorrencias.filter((o) => !o.pago && !o.cancelada) : null;
    },
});

// ---------------------------------------------------------------------------------------------------------------
// Filtros do desktop num painel compacto (sem barra permanente)

function abrirFiltros() {
    const f = estado.filtros;
    const situacao = seletor([['', 'Todos os status'], ['pendente', 'Pendentes'], ['pago', 'Pagas']], f.situacao || '');
    const forma = seletor(FORMAS_FILTRO, f.forma || '');
    const vencimento = entrada('date', f.vencimentoAte || '');
    const busca = entrada('search', f.busca || '', { autocomplete: 'off', placeholder: 'Nome, observação ou categoria' });
    const form = el('form', 'mob-form');
    form.append(campo('Status', situacao), campo('Forma de pagamento', forma), campo('Vencimento até', vencimento), campo('Buscar', busca));
    const limpar = botao('Limpar');
    const aplicar = botao('Aplicar', 'primario');
    aplicar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(limpar, aplicar);
    form.append(acoes);
    limpar.addEventListener('click', () => { estado.filtros = {}; fecharFolha(); desenhar(); });
    form.addEventListener('submit', (evento) => {
        evento.preventDefault();
        estado.filtros = { situacao: situacao.value, forma: forma.value, vencimentoAte: vencimento.value, busca: busca.value.trim() };
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
    estado.abertos = {};  // nova competencia: grupos recolhidos
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
        configurarDespesas(perfil.id, {
            depoisDaGeracao: (_mes, preparo) => { estado.somenteLeitura = !(preparo.geracao.previa && preparo.geracao.previa.pode_gerir); },
        });
        await carregar();
    } else {
        $('mob-lista').setAttribute('aria-busy', 'false');
        if ($('mob-aviso').hidden) mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
    }
}
