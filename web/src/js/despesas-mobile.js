// FIN-MVP-MOB-01 — Lista de Despesas mobile. Le e altera os mesmos registros da tela Despesas do desktop, pelas mesmas
// rotas (js/despesas-servico.js: as mesmas funcoes do banco, validacoes, chaves de idempotencia e mensagens) e com as
// mesmas regras de leitura (js/despesas-grupos.js: grupos, ordem, valores, filtros e totais). Nenhuma regra financeira
// nova: pagamento, edicao, estorno, exclusao, cancelamento da obrigacao, interrupcao da recorrencia e pagamento em lote
// seguem os fluxos do desktop (js/original/despesas.js + js/despesas-adaptacoes.js), adaptados a um painel compacto.
// Sem innerHTML (CSP): tudo por createElement.

import { hojeBrasilia } from './adaptador-comum.js';
import { centavos, dataCurta, deslocarMes, el, reais } from './comum.js';
import {
    FORMAS_FILTRO, estaPaga, filtrarDespesas, filtrosAtivos, formatarCompetencia, formatarTipoRecorrencia, montarGrupos,
    obterFormaPagamentoDespesa, obterValorDespesa, totaisDaLista, agruparDespesasSemanais,
} from './despesas-grupos.js';
import { configurarDespesas, responderDespesas } from './despesas-servico.js';
import { aplicarCompetencia, competenciaInicial, prepararMais, prepararModulos } from './mobile-comum.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);
const SVG = 'http://www.w3.org/2000/svg';
const SETA = 'M9 5l7 7-7 7';
const FALHA_GERAL = 'Não foi possível concluir a operação. Nada foi gravado.';

const estado = {
    mes: null,
    despesas: [],
    abertos: {},  // grupos expandidos (varios ao mesmo tempo): chave do grupo -> true
    filtros: {},
    somenteLeitura: true,
    contas: null,
    categorias: null,
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
// Elementos

function icone(caminho, classe) {
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    if (classe) svg.setAttribute('class', classe);
    const p = document.createElementNS(SVG, 'path');
    p.setAttribute('d', caminho);
    svg.append(p);
    return svg;
}

function botao(texto, classe = '') {
    const b = el('button', `mob-botao${classe ? ` ${classe}` : ''}`, texto);
    b.type = 'button';
    return b;
}

function campo(rotulo, controle) {
    const caixa = el('label', 'mob-campo');
    caixa.append(el('span', null, rotulo), controle);
    return caixa;
}

function entrada(tipo, valor, atributos = {}) {
    const input = el('input');
    input.type = tipo;
    if (valor !== undefined && valor !== null) input.value = String(valor);
    Object.entries(atributos).forEach(([k, v]) => input.setAttribute(k, v));
    return input;
}

function seletor(opcoes, valor) {
    const select = el('select');
    for (const [chave, texto] of opcoes) {
        const opcao = el('option', null, texto);
        opcao.value = String(chave);
        select.append(opcao);
    }
    if (valor !== undefined && valor !== null) select.value = String(valor);
    return select;
}

function texto(conteudo, classe = '') {
    return el('p', `mob-texto${classe ? ` ${classe}` : ''}`, conteudo);
}

function mensagem() {
    const m = el('p', 'mob-mensagem');
    m.setAttribute('role', 'status');
    m.hidden = true;
    return m;
}

// O aviso de erro de um formulario some quando o usuario volta a preencher.
function limparAoEditar(form, m) {
    form.addEventListener('input', () => { if (m.classList.contains('erro')) mostrarMensagem(m, ''); });
    form.addEventListener('change', () => { if (m.classList.contains('erro')) mostrarMensagem(m, ''); });
}

function mostrarMensagem(m, conteudo, tipo = '') {
    m.textContent = conteudo || '';
    m.className = `mob-mensagem${tipo ? ` ${tipo}` : ''}`;
    m.hidden = !conteudo;
}

function detalhes(pares) {
    const dl = el('dl', 'mob-detalhes');
    for (const [rotulo, valor] of pares) {
        if (valor === undefined || valor === null || valor === '') continue;
        dl.append(el('dt', null, rotulo), el('dd', null, valor));
    }
    return dl;
}

const valorDe = (d) => reais(centavos(obterValorDespesa(d)));
const diaMes = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : '');
const NOMES_FORMA = Object.fromEntries(FORMAS_FILTRO.filter(([k]) => k).concat([['nao_informado', 'Não informado'], ['outros', 'Outros']]));
const nomeForma = (d) => NOMES_FORMA[obterFormaPagamentoDespesa(d)] || 'Não informado';

// ---------------------------------------------------------------------------------------------------------------
// Aviso da ultima operacao (acima da lista)

function mostrarAviso(conteudo, tipo = '') {
    const aviso = $('mob-aviso');
    aviso.textContent = conteudo || '';
    aviso.className = `mob-aviso${tipo === 'erro' ? ' erro' : ''}`;
    aviso.hidden = !conteudo;
}

// ---------------------------------------------------------------------------------------------------------------
// Painel inferior (um de cada vez)

function abrirFolha(titulo, ...conteudo) {
    $('mob-folha-titulo').textContent = titulo;
    $('mob-folha-corpo').replaceChildren(...conteudo);
    $('mob-folha-fundo').hidden = false;
    $('mob-folha-corpo').scrollTop = 0;
    $('mob-folha-fechar').focus();
}

function fecharFolha() {
    $('mob-folha-fundo').hidden = true;
    $('mob-folha-corpo').replaceChildren();
}

const folhaAberta = () => !$('mob-folha-fundo').hidden;

function prepararFolha() {
    $('mob-folha-fechar').addEventListener('click', fecharFolha);
    $('mob-folha-fundo').addEventListener('click', (evento) => { if (evento.target === $('mob-folha-fundo')) fecharFolha(); });
    document.addEventListener('keydown', (evento) => { if (evento.key === 'Escape' && folhaAberta()) fecharFolha(); });
}

// Resultado de uma operacao concluida: fecha o painel, mostra a mensagem e relê a competencia (lista e totais).
async function concluir(conteudo) {
    fecharFolha();
    mostrarAviso(conteudo, 'ok');
    await carregar();
}

// Recusa ou erro antes de abrir um formulario: painel so com a mensagem.
function folhaDeErro(titulo, conteudo) {
    const m = mensagem();
    mostrarMensagem(m, conteudo, 'erro');
    const fechar = botao('Fechar');
    fechar.addEventListener('click', fecharFolha);
    const acoes = el('div', 'mob-acoes');
    acoes.append(fechar);
    abrirFolha(titulo, m, acoes);
}

// ---------------------------------------------------------------------------------------------------------------
// Lista

async function carregar() {
    const mes = estado.mes;
    const pedido = ++estado.pedido;
    estado.contas = null;
    const lista = $('mob-lista');
    lista.setAttribute('aria-busy', 'true');
    const r = await api('GET', `/api/despesas?mes_referencia=${mes}`);
    if (pedido !== estado.pedido) return;  // ja trocaram de competencia
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
// Pagamento (individual): os campos do desktop (data, conta, valor total ou outro valor com a diferenca classificada e
// justificada). O banco paga pela mesma funcao, com a mesma chave de idempotencia.

const AJUSTES = { JUROS: 'Juros ou multa', DESCONTO: 'Desconto', AJUSTE: 'Ajuste de quitação integral' };

function opcoesDeConta(contas, sugerida) {
    const opcoes = [['', 'Selecione...'], ...contas.map((c) => [c.id, c.instituicao ? `${c.nome} (${c.instituicao})` : c.nome])];
    return seletor(opcoes, sugerida && contas.some((c) => c.id === sugerida) ? sugerida : '');
}

async function abrirPagamento(d) {
    const fatura = d.is_fatura_cartao === true;
    let devido = fatura ? Number(d.valor_executado || 0) : Number(d.valor || 0);
    let nota = '';
    if (fatura) {
        // FIN-CARTOES-EXECUTADO-01: o executado consolidado e o valor sugerido; o banco pode cobrar outro valor.
        const r = await api('GET', `/api/despesas/${d.id}/composicao-fatura`);
        if (r.success) {
            devido = Number(r.data.valor_executado || 0);
            nota = (r.data.previsto_sem_cobranca > 0
                ? `Inclui ${reais(centavos(r.data.previsto_sem_cobranca))} de despesas fixas previstas, ainda sem cobrança importada. ` : '')
                + 'Se o banco cobrou outro valor, escolha “Pagar outro valor”, informe o valor efetivamente cobrado e justifique a '
                + 'diferença. Nenhuma recorrência é marcada como não cobrada; a conciliação posterior continua possível.';
        }
    }
    const contas = await contasAtivas();
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const data = entrada('date', hojeBrasilia(), { required: '' });
    const conta = opcoesDeConta(contas, d.conta_bancaria_id);
    // Uma conta ja vinculada a despesa fixa a conta do pagamento (como no desktop).
    if (d.conta_bancaria_id && conta.value) conta.disabled = true;
    const opcoes = el('fieldset', 'mob-opcoes');
    const radio = (valor, rotulo, marcado) => {
        const caixa = el('label', 'mob-opcao');
        const r = entrada('radio', valor, { name: 'mob-tipo-pagamento' });
        r.checked = marcado;
        caixa.append(r, el('span', null, rotulo));
        return { caixa, r };
    };
    const total = radio('total', `${fatura ? 'Executado consolidado (valor sugerido)' : 'Valor total'}: ${reais(centavos(devido))}`, true);
    const outro = radio('parcial', 'Pagar outro valor', false);
    opcoes.append(total.caixa, outro.caixa);
    const valorPago = entrada('number', devido.toFixed(2), { step: '0.01', min: '0.01', inputmode: 'decimal' });
    const campoValor = campo('Valor pago', valorPago);
    campoValor.hidden = true;
    const tipoAjuste = seletor([['', 'Selecione...']]);
    const justificativa = el('textarea');
    const campoTipo = campo('Classificação da diferença', tipoAjuste);
    const campoJust = campo('Justificativa', justificativa);
    campoTipo.hidden = true;
    campoJust.hidden = true;
    const m = mensagem();

    const diferenca = () => {
        const pago = centavos(valorPago.value);
        return outro.r.checked && pago > 0 ? pago - centavos(devido) : 0;
    };
    const atualizar = () => {
        campoValor.hidden = !outro.r.checked;
        const dif = diferenca();
        campoTipo.hidden = dif === 0;
        campoJust.hidden = dif === 0;
        const tipos = dif > 0 ? ['JUROS', 'AJUSTE'] : ['DESCONTO', 'AJUSTE'];
        const atual = tipoAjuste.value;
        const rotulo = (t) => (fatura && t === 'AJUSTE' ? 'Valor cobrado pelo banco diferente do consolidado' : AJUSTES[t]);
        tipoAjuste.replaceChildren(new Option('Selecione...', ''), ...tipos.map((t) => new Option(rotulo(t), t)));
        if (tipos.includes(atual)) tipoAjuste.value = atual;
    };
    [total.r, outro.r].forEach((r) => r.addEventListener('change', atualizar));
    valorPago.addEventListener('input', atualizar);

    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', fecharFolha);
    const confirmar = botao('Confirmar pagamento', 'primario');
    confirmar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, confirmar);
    form.append(texto(`Vencimento ${dataCurta(d.data_vencimento) || '—'} · ${formatarCompetencia(d.mes_competencia)}`, 'discreto'));
    if (nota) form.append(texto(nota, 'discreto'));
    form.append(campo('Data do pagamento', data), campo('Conta bancária', conta), opcoes, campoValor, campoTipo, campoJust, m, acoes);
    limparAoEditar(form, m);

    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        const payload = { data_pagamento: data.value };
        if (outro.r.checked) {
            const v = parseFloat(valorPago.value);
            if (!v || v <= 0) { mostrarMensagem(m, 'Por favor, informe um valor válido.', 'erro'); return; }
            payload.valor_pago = v;
        }
        if (!data.value) { mostrarMensagem(m, 'Informe a data do pagamento.', 'erro'); return; }
        if (!conta.value) { mostrarMensagem(m, 'Selecione a conta bancária para executar o pagamento.', 'erro'); return; }
        payload.conta_bancaria_id = parseInt(conta.value, 10);
        if (diferenca() !== 0) {
            if (!tipoAjuste.value || !justificativa.value.trim()) {
                mostrarMensagem(m, 'Classifique a diferença e escreva a justificativa.', 'erro');
                return;
            }
            payload.tipo_ajuste = tipoAjuste.value;
            payload.justificativa = justificativa.value.trim();
        }
        confirmar.disabled = true;  // evita duplo envio (o banco tambem protege pela chave)
        mostrarMensagem(m, 'Pagando...');
        const r = await api('POST', `/api/despesas/${d.id}/pagar`, payload);
        if (!r.success) {
            mostrarMensagem(m, r.error || FALHA_GERAL, 'erro');
            confirmar.disabled = false;
            return;
        }
        await concluir(r.message || 'Despesa paga.');
    });
    abrirFolha(`${fatura ? 'Pagar fatura' : 'Pagar'}: ${d.nome}`, form);
}

// ---------------------------------------------------------------------------------------------------------------
// Estorno do pagamento (despesa ou fatura): movimento compensatorio; o pagamento original nao e apagado.

function abrirEstorno(d) {
    const fatura = d.is_fatura_cartao === true;
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const data = entrada('date', hojeBrasilia(), { required: '' });
    const motivo = el('textarea');
    motivo.required = true;
    const m = mensagem();
    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', fecharFolha);
    const confirmar = botao('Confirmar estorno', 'perigo');
    confirmar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, confirmar);
    form.append(
        texto(fatura
            ? 'O estorno não apaga o pagamento original. O sistema criará um crédito compensatório e reabrirá a fatura.'
            : 'O estorno não apaga o pagamento original. O sistema criará um movimento compensatório e reabrirá a despesa como pendente.'),
        campo('Data do estorno', data), campo('Motivo', motivo), m, acoes,
    );
    limparAoEditar(form, m);
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (!data.value) { mostrarMensagem(m, 'Informe a data do estorno.', 'erro'); return; }
        if (!motivo.value.trim()) { mostrarMensagem(m, 'Informe o motivo do estorno.', 'erro'); return; }
        confirmar.disabled = true;
        mostrarMensagem(m, 'Estornando...');
        const r = await api('POST', `/api/despesas/${d.id}/estornar-pagamento`, { data_estorno: data.value, motivo: motivo.value.trim() });
        if (!r.success) {
            mostrarMensagem(m, `Erro ao estornar: ${r.error || FALHA_GERAL}`, 'erro');
            confirmar.disabled = false;
            return;
        }
        await concluir(r.message || 'Pagamento estornado com sucesso.');
    });
    abrirFolha(fatura ? `Estornar pagamento da fatura: ${d.nome}` : `Estornar pagamento: ${d.nome}`, form);
}

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

function nomeDoMeio(meio) {
    const forma = meio && window.FormasPagamentoUI && window.FormasPagamentoUI.resolverFormaPagamento(meio);
    return (forma && forma.nome) || ({ pix: 'Pix', boleto: 'Boleto', debito: 'Débito', debito_automatico: 'Débito automático' }[meio]) || 'Não informado';
}

const idsDe = (ocorrencias) => ocorrencias.map((o) => o.id).sort((a, b) => a - b).join(',');
const CODIGOS_RECARREGAR = ['LOTE_DESATUALIZADO', 'LOTE_IDENTIDADE', 'VALOR_MUDOU', 'DESPESA_PAGA'];

async function abrirLote(nome, competencia) {
    const agrupador = agrupadorAtual(nome, competencia);
    const pendentes = agrupador ? agrupador.ocorrencias.filter((o) => !o.pago && !o.cancelada) : [];
    if (!pendentes.length) {
        folhaDeErro(nome, agrupador ? 'Todas as ocorrências já foram pagas!' : 'Agrupamento não encontrado. Atualize a lista e tente de novo.');
        return;
    }
    const total = pendentes.reduce((s, o) => s + centavos(o.valor), 0);
    const contas = await contasAtivas();
    const vinculadas = [...new Set(pendentes.map((o) => o.conta_bancaria_id).filter(Boolean))];
    const conta = opcoesDeConta(contas, vinculadas.length === 1 ? vinculadas[0] : null);
    const m = mensagem();
    const form = el('form', 'mob-form');
    form.noValidate = true;
    form.append(detalhes([
        ['Recorrência', nome], ['Competência', formatarCompetencia(competencia)], ['Forma de pagamento', nomeDoMeio(pendentes[0].meio_pagamento)],
        ['Ocorrências pendentes', String(pendentes.length)], ['Valor total', reais(total)],
    ]), campo('Conta bancária de débito', conta), m);
    const cancelar = botao('Cancelar');
    const confirmar = botao('Confirmar pagamento', 'primario');
    confirmar.type = 'submit';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, confirmar);
    form.append(acoes);
    let recarregar = false;  // no lote o aviso fica: ele diz se a lista mudou e precisa ser conferida
    const fechar = async () => { fecharFolha(); if (recarregar) await carregar(); };
    cancelar.addEventListener('click', fechar);
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (!conta.value) { mostrarMensagem(m, 'Selecione a conta bancária de débito.', 'erro'); return; }
        const agora = agrupadorAtual(nome, competencia);
        const aindaPendentes = agora ? agora.ocorrencias.filter((o) => !o.pago && !o.cancelada) : [];
        if (idsDe(aindaPendentes) !== idsDe(pendentes)) {
            recarregar = true;
            confirmar.disabled = true;
            mostrarMensagem(m, 'Nenhuma ocorrência foi paga.\nA lista mudou desde a abertura. Feche e confira a lista atualizada antes de pagar de novo.', 'erro');
            return;
        }
        confirmar.disabled = true;
        mostrarMensagem(m, 'Pagando...');
        const r = await api('POST', '/api/despesas/pagar-lote', {
            conta_bancaria_id: Number(conta.value),
            itens: pendentes.map((o) => ({ conta_id: o.id, valor_devido: Number(o.valor).toFixed(2) })),
            // o que o painel mostrou: o banco recusa se as ocorrencias nao forem desta recorrencia e competencia (P21)
            lote: { descricao: nome, competencia, recorrencias: [...new Set(pendentes.map((o) => o.item_despesa_id))].sort((a, b) => a - b),
                quantidade: pendentes.length, valor_total: (total / 100).toFixed(2) },
        });
        if (!r.success) {
            const deveRecarregar = CODIGOS_RECARREGAR.includes(r.codigo);
            mostrarMensagem(m, `Nenhuma ocorrência foi paga.\n${String(r.error || 'Não foi possível pagar.').replace(/^Nenhuma ocorrência foi paga\.\s*/, '')}`
                + (deveRecarregar ? '\nFeche e confira a lista atualizada antes de pagar de novo.' : ''), 'erro');
            if (deveRecarregar) recarregar = true;
            confirmar.disabled = deveRecarregar;
            return;
        }
        const resultado = r.data;
        await concluir(`Pagamento em lote concluído\n${resultado.pagas} ocorrência(s) paga(s)\nValor total: ${reais(centavos(resultado.valor_total))}\n`
            + `Conta de débito: ${resultado.conta_nome}\nSaldo da conta: ${reais(centavos(resultado.saldo_conta))}`);
    });
    abrirFolha(`Pagar ocorrências: ${nome}`, form);
}

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
