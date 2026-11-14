// FIN-MVP-MOBILE-05 — Nova Despesa mobile (atalho Despesa da pagina principal). O formulario "Nova Despesa" do desktop
// (js/original/despesas.js + a recusa do servico), em versao compacta e progressiva, pelo mesmo servico e rota:
// POST /api/despesas em js/despesas-servico.js -> criar_despesa (chave de idempotencia: toques repetidos nao duplicam).
// - Campos gravados: nome ("Descricao" aqui), valor, categoria, vencimento, competencia (despesa simples), recorrencia
//   (mensal, anual ou semanal com dia e frequencia 1 ou 2) e o meio de pagamento informativo da recorrencia; a
//   "Descricao" opcional do desktop vai em "Observacoes".
// - Competencia: a do mes aberto na pagina principal; ao escolher o vencimento, a regra do desktop (mes anterior ao
//   vencimento) enquanto o usuario nao mudar a competencia. Na recorrencia, a competencia e a de cada vencimento (banco).
// - O que o servico do desktop recusa nao aparece (nao ha caminho que funcione): despesa ja paga (o pagamento e pela
//   acao Pagar da lista), recorrencia no cartao, consorcio e parcelamento (sem parcelas neste formulario).
// Nenhuma regra financeira nova. Sem innerHTML (CSP): tudo por createElement.

import { deslocarMes, el } from './comum.js';
import { configurarDespesas, podeGerirPerfil, responderDespesas } from './despesas-servico.js';
import { formatarCompetencia } from './despesas-grupos.js';
import { MODULOS_ATIVOS, competenciaInicial, prepararMais, prepararModulos } from './mobile-comum.js';
import { FALHA_GERAL, botao, entrada, mostrarAviso, mostrarMensagem, mensagem, seletor, texto } from './mobile-ui.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);
const estado = { mes: null, categorias: [], enviando: false };

// Pedidos ao servico: um de cada vez (como a ponte-api.js do desktop); o corpo passa por JSON, como o fetch.
let fila = Promise.resolve();
function api(metodo, caminho, corpo = null) {
    const endereco = new URL(caminho, window.location.origin);
    const tarefa = fila.then(async () => {
        try {
            const r = await responderDespesas({ metodo, caminho: endereco.pathname, parametros: endereco.searchParams,
                corpo: corpo === null ? null : JSON.parse(JSON.stringify(corpo)) });
            return r.corpo;
        } catch (erro) {
            console.error('Nova Despesa:', metodo, endereco.pathname, erro);
            return { success: false, error: FALHA_GERAL };
        }
    });
    fila = tarefa.catch(() => {});
    return tarefa;
}

// Inicio, Voltar e os modulos ativos levam a competencia aberta (como aplicarCompetencia das outras paginas).
function ligarCompetencia(mes) {
    for (const inicio of document.querySelectorAll('[data-inicio]')) inicio.setAttribute('href', `inicio.html?mes=${mes}`);
    for (const item of document.querySelectorAll('[data-modulo][data-destino]')) {
        if (MODULOS_ATIVOS.has(item.dataset.modulo)) item.setAttribute('href', `${item.dataset.destino}?mes=${mes}`);
    }
}

// Regra do desktop (calcularCompetenciaAutomaticamente): o mes anterior ao do vencimento. Por mes, nao por data: no
// desktop, vencimento em 29 a 31 cujo mes anterior e mais curto caia no proprio mes (Date.setMonth; 31/03 -> 03/03).
const competenciaDoVencimento = (vencimento) => deslocarMes(vencimento.slice(0, 7), -1);

// ---------------------------------------------------------------------------------------------------------------
// Campos com o erro logo abaixo

function campo(rotulo, controle, { obrigatorio = false, ajuda = '' } = {}) {
    const caixa = el('label', 'mob-campo');
    const titulo = el('span', null, rotulo);
    if (obrigatorio) titulo.append(el('span', 'mob-obrigatorio', ' *'));
    const erro = el('span', 'mob-campo-erro');
    erro.hidden = true;
    erro.setAttribute('role', 'alert');
    caixa.append(titulo, controle);
    if (ajuda) caixa.append(el('span', 'mob-ajuda', ajuda));
    caixa.append(erro);
    caixa.erro = (conteudo) => {
        erro.textContent = conteudo || '';
        erro.hidden = !conteudo;
        if (conteudo) controle.setAttribute('aria-invalid', 'true');
        else controle.removeAttribute('aria-invalid');
    };
    return caixa;
}

const par = (...filhos) => {
    const linha = el('div', 'mob-par');
    linha.append(...filhos);
    return linha;
};

const DIAS = [['', 'Selecione...'], ['0', 'Domingo'], ['1', 'Segunda-feira'], ['2', 'Terça-feira'], ['3', 'Quarta-feira'],
    ['4', 'Quinta-feira'], ['5', 'Sexta-feira'], ['6', 'Sábado']];

// ---------------------------------------------------------------------------------------------------------------
// Formulario

function desenharFormulario() {
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const nome = entrada('text', '', { maxlength: '200', placeholder: 'Ex.: Conta de luz, Aluguel, Mercado', autocomplete: 'off' });
    const valor = entrada('number', '', { step: '0.01', min: '0', inputmode: 'decimal', placeholder: '0,00' });
    const categoria = seletor([['', 'Selecione...'], ...estado.categorias.map((c) => [c.id, c.nome])], '');
    const vencimento = entrada('date', '');
    const competencia = entrada('month', estado.mes);
    let competenciaManual = false;
    const recorrente = entrada('checkbox');
    const tipo = seletor([['mensal', 'Mensal'], ['anual', 'Anual'], ['semanal', 'Semanal (por dia da semana)']], 'mensal');
    const dia = seletor(DIAS, '');
    const frequencia = seletor([['1', 'Toda semana'], ['2', 'A cada 2 semanas']], '1');
    const meio = seletor([['', 'Não informado'], ['boleto', 'Boleto'], ['debito', 'Débito'], ['pix', 'PIX']], '');
    const observacoes = el('textarea');
    observacoes.rows = 2;
    observacoes.maxLength = 500;
    observacoes.placeholder = 'Opcional';

    const cNome = campo('Descrição', nome, { obrigatorio: true });
    const cValor = campo('Valor', valor, { obrigatorio: true });
    const cCategoria = campo('Categoria', categoria, { obrigatorio: true });
    const cVencimento = campo('Vencimento', vencimento, { obrigatorio: true });
    const cCompetencia = campo('Competência', competencia, { ajuda: 'Mês do salário que pagará a despesa' });
    const cDia = campo('Dia da semana', dia, { obrigatorio: true });
    const cFrequencia = campo('Frequência', frequencia);
    const marcaRecorrente = el('label', 'mob-opcao');
    marcaRecorrente.append(recorrente, el('span', null, 'Despesa recorrente'));

    const secaoRecorrencia = el('div', 'mob-condicional');
    secaoRecorrencia.id = 'mob-recorrencia';
    const parSemanal = par(cDia, cFrequencia);
    parSemanal.classList.add('empilha');
    const parVencimento = par(cVencimento, cCompetencia);
    secaoRecorrencia.append(campo('Periodicidade', tipo), parSemanal,
        campo('Meio de pagamento', meio, { ajuda: 'Informativo; o pagamento é feito depois, pela lista' }),
        el('span', 'mob-ajuda', 'As contas são geradas ao abrir cada competência na Lista de Despesas; a competência de cada uma é o mês do vencimento.'));

    const ajustarRecorrencia = () => {
        secaoRecorrencia.hidden = !recorrente.checked;
        parSemanal.hidden = tipo.value !== 'semanal';
        cCompetencia.hidden = recorrente.checked;  // na recorrencia o banco usa o mes de cada vencimento
        parVencimento.classList.toggle('um', recorrente.checked);
    };
    recorrente.addEventListener('change', ajustarRecorrencia);
    tipo.addEventListener('change', ajustarRecorrencia);
    competencia.addEventListener('input', () => { competenciaManual = true; });
    vencimento.addEventListener('change', () => {
        if (vencimento.value && !competenciaManual) competencia.value = competenciaDoVencimento(vencimento.value);
    });
    ajustarRecorrencia();

    const m = mensagem();
    const campos = [cNome, cValor, cCategoria, cVencimento, cCompetencia, cDia];
    const limparErros = () => { campos.forEach((c) => c.erro('')); mostrarMensagem(m, ''); };
    for (const [c, controle] of [[cNome, nome], [cValor, valor], [cCategoria, categoria], [cVencimento, vencimento],
        [cCompetencia, competencia], [cDia, dia]]) {
        controle.addEventListener('input', () => c.erro(''));
        controle.addEventListener('change', () => c.erro(''));
    }

    const cancelar = el('a', 'mob-botao', 'Cancelar');
    cancelar.id = 'mob-cancelar';
    cancelar.href = `inicio.html?mes=${estado.mes}`;
    const salvar = botao('Salvar', 'primario');
    salvar.type = 'submit';
    salvar.id = 'mob-salvar';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, salvar);

    form.append(cNome, par(cValor, cCategoria), parVencimento, marcaRecorrente, secaoRecorrencia,
        campo('Observações', observacoes), m, acoes);

    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (estado.enviando) return;
        limparErros();
        // As validacoes do formulario do desktop (campos obrigatorios e dia da semana) e as do servico, junto ao campo.
        const erros = [];
        if (!nome.value.trim()) erros.push([cNome, 'Informe a descrição.']);
        if (!(parseFloat(valor.value) > 0)) erros.push([cValor, 'Informe um valor válido.']);
        if (!categoria.value) erros.push([cCategoria, 'Selecione a categoria.']);
        if (!vencimento.value) erros.push([cVencimento, 'Informe a data de vencimento.']);
        if (!recorrente.checked && !/^\d{4}-\d{2}$/.test(competencia.value)) erros.push([cCompetencia, 'Informe a competência.']);
        if (recorrente.checked && tipo.value === 'semanal' && !dia.value) erros.push([cDia, 'Selecione o dia da semana.']);
        if (erros.length) {
            erros.forEach(([c, t]) => c.erro(t));
            erros[0][0].querySelector('input, select, textarea').focus();
            return;
        }
        estado.enviando = true;
        salvar.disabled = true;
        mostrarMensagem(m, 'Salvando...');
        // O mesmo corpo do desktop (salvarDespesa); despesa ja paga nao e cadastrada por aqui (pago: false).
        const tipoRecorrencia = recorrente.checked && tipo.value === 'semanal' ? `semanal_${frequencia.value}_${dia.value}` : tipo.value;
        const corpo = {
            nome: nome.value.trim(), descricao: observacoes.value.trim(), valor: parseFloat(valor.value),
            categoria_id: parseInt(categoria.value, 10), data_vencimento: vencimento.value, data_pagamento: null, pago: false,
            recorrente: recorrente.checked, tipo_recorrencia: tipoRecorrencia,
            mes_competencia: recorrente.checked ? null : competencia.value,
        };
        if (recorrente.checked && meio.value) corpo.meio_pagamento = meio.value;
        const r = await api('POST', '/api/despesas', corpo);
        if (!r.success) {
            estado.enviando = false;
            salvar.disabled = false;
            const erro = r.error || 'Falha ao salvar. Nada foi gravado.';
            // Mensagem do banco junto ao campo que ela cita (competencia antes: "a ate 12 meses do vencimento").
            const doCampo = [[/compet/i, cCompetencia], [/valor/i, cValor], [/categoria/i, cCategoria], [/nome/i, cNome],
                [/vencimento/i, cVencimento]].find(([padrao]) => padrao.test(erro));
            if (doCampo) doCampo[1].erro(erro);
            mostrarMensagem(m, erro, 'erro');
            return;
        }
        const mesDaLista = recorrente.checked ? vencimento.value.slice(0, 7) : competencia.value;
        desenharConfirmacao(r.message || 'Despesa salva.', mesDaLista, corpo.nome);
    });
    $('mob-cadastro').replaceChildren(form);
    nome.focus();
}

// Depois de salvar: confirmacao discreta e os caminhos (nada de redirecionar sozinho).
function desenharConfirmacao(mensagemDoServico, mes, nome) {
    estado.enviando = false;
    const caixa = el('div', 'mob-confirmacao');
    caixa.id = 'mob-confirmacao';
    const lista = el('a', 'mob-botao primario', 'Ver na Lista de Despesas');
    lista.id = 'mob-ver-lista';
    lista.href = `despesas-mobile.html?mes=${mes}`;
    const outra = botao('Nova despesa');
    outra.id = 'mob-outra';
    outra.addEventListener('click', () => { mostrarAviso(''); desenharFormulario(); });
    const inicio = el('a', 'mob-botao', 'Início');
    inicio.href = `inicio.html?mes=${estado.mes}`;
    const acoes = el('div', 'mob-acoes');
    acoes.append(lista, outra, inicio);
    caixa.append(el('p', 'mob-confirmacao-titulo', `“${nome}” cadastrada`), texto(mensagemDoServico),
        texto(`Lista de Despesas: ${formatarCompetencia(mes)}.`, 'discreto'), acoes);
    $('mob-cadastro').replaceChildren(caixa);
}

// ---------------------------------------------------------------------------------------------------------------
// Inicio

const usuario = await exigirUsuario();
if (usuario) {
    estado.mes = competenciaInicial();
    prepararModulos();
    prepararMais();
    ligarCompetencia(estado.mes);
    let perfil = null;
    try {
        const perfis = await carregarPerfis();
        perfil = escolherPerfilAtivo(perfis, usuario.id);
        if (perfil) salvarPerfilAtivo(usuario.id, perfil.id);
    } catch (_erro) {
        mostrarAviso('Não foi possível carregar os perfis financeiros.', 'erro');
    }
    const cadastro = $('mob-cadastro');
    if (perfil) {
        $('mob-perfil').textContent = perfil.nome || '';
        configurarDespesas(perfil.id);
        if (!await podeGerirPerfil()) {
            // Somente leitura: sem formulario (o banco recusaria a gravacao de qualquer forma).
            const voltar = el('a', 'mob-botao', 'Voltar ao início');
            voltar.href = `inicio.html?mes=${estado.mes}`;
            const acoes = el('div', 'mob-acoes');
            acoes.append(voltar);
            cadastro.replaceChildren(texto('Acesso somente de leitura a este perfil: não é possível cadastrar despesas.'), acoes);
        } else {
            const r = await api('GET', '/api/categorias');
            estado.categorias = r.success ? (r.data || []) : [];
            if (!r.success) mostrarAviso(r.error || 'Não foi possível carregar as categorias.', 'erro');
            desenharFormulario();
        }
    } else if ($('mob-aviso').hidden) {
        mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
    }
    cadastro.setAttribute('aria-busy', 'false');
}
