// FIN-MVP-MOBILE-05 — Nova Despesa mobile (atalho Despesa da pagina principal). O formulario "Nova Despesa" do desktop
// (js/original/despesas.js + a recusa do servico), em versao compacta e progressiva, pelo mesmo servico e rota:
// POST /api/despesas em js/despesas-servico.js -> criar_despesa (chave de idempotencia: toques repetidos nao duplicam).
// - Campos gravados: nome ("Descricao" aqui), valor, categoria, vencimento, competencia (despesa simples), recorrencia
//   (mensal, anual ou semanal com dia e frequencia 1 ou 2) e o meio de pagamento informativo da recorrencia; a
//   "Descricao" opcional do desktop vai em "Observacoes".
// - Competencia: a do mes aberto na pagina principal; ao escolher o vencimento, a regra do desktop (mes anterior ao
//   vencimento) enquanto o usuario nao mudar a competencia. Na recorrencia, a competencia e a de cada vencimento (banco).
// - O que o servico do desktop recusa nao aparece (nao ha caminho que funcione): despesa ja paga (o pagamento e pela
//   acao Pagar da lista) e consorcio.
// - Ajuste final (decisao de 14/11/2026, Proposta A): "Meio de pagamento" logo apos descricao, valor e categoria:
//   "Conta a pagar" (o fluxo acima, POST /api/despesas) ou "Cartao de credito": a compra da tela Lancamentos do desktop
//   (cartao ativo, data da compra, parcelas, fatura sugerida pelo fechamento, previa do parcelamento e a confirmacao de
//   fatura consolidada), gravada so por criar_compra (js/compras-servico.js, POST /api/cartoes/:id/lancamentos). E uma
//   coisa ou outra: a compra entra na fatura e nenhuma conta a pagar e criada. No cartao a recorrencia fica desabilitada
//   (etapa posterior). O futuro Registrar Lancamento (FIN-MVP-MOBILE-06) reaproveita este fluxo.
// Nenhuma regra financeira nova. Sem innerHTML (CSP): tudo por createElement.

import { deslocarMes, el } from './comum.js';
import { configurarCompras, responderCompras } from './compras-servico.js';
import { configurarDespesas, podeGerirPerfil, responderDespesas } from './despesas-servico.js';
import { formatarCompetencia } from './despesas-grupos.js';
import { mesSemSugestao, textoConsolidada, textoSugestao } from './fechamento.js';
import { MODULOS_ATIVOS, competenciaInicial, prepararMais, prepararModulos } from './mobile-comum.js';
import { FALHA_GERAL, botao, entrada, mostrarAviso, mostrarMensagem, mensagem, seletor, texto } from './mobile-ui.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);
const estado = { mes: null, categorias: [], cartoes: null, enviando: false };

// Pedidos aos servicos do desktop (Despesas; compra no cartao de Lancamentos): um de cada vez (como a ponte-api.js do
// desktop); o corpo passa por JSON, como o fetch.
let fila = Promise.resolve();
function api(metodo, caminho, corpo = null, servico = responderDespesas) {
    const endereco = new URL(caminho, window.location.origin);
    const tarefa = fila.then(async () => {
        try {
            const r = await servico({ metodo, caminho: endereco.pathname, parametros: endereco.searchParams,
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

const RECORRENCIA_NO_CARTAO = 'O cadastro de despesas recorrentes no cartão de crédito será disponibilizado em uma etapa posterior.';

const hojeBrasilia = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const mesAno = (iso) => `${String(iso).slice(5, 7)}/${String(iso).slice(0, 4)}`;
const moeda = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

// Cartoes ativos do perfil: lidos na primeira escolha de "Cartao de credito".
async function carregarCartoes() {
    if (estado.cartoes) return estado.cartoes;
    const r = await api('GET', '/api/cartoes', null, responderCompras);
    if (!Array.isArray(r)) return null;
    estado.cartoes = r;
    return r;
}

// Previa do parcelamento (2 ou mais parcelas): os numeros vem de previa_compra (o mesmo plano que criar_compra grava,
// como a previa da tela Lancamentos do desktop): parcela, fatura e valor, com o total.
function desenharPrevia(caixa, p) {
    const tabela = el('table', 'mob-previa-tabela');
    const cab = tabela.createTHead().insertRow();
    for (const [t, c] of [['Parcela'], ['Fatura'], ['Valor', 'direita']]) cab.append(el('th', c || null, t));
    const corpo = tabela.createTBody();
    for (const x of p.parcelas) {
        const tr = corpo.insertRow();
        tr.append(el('td', null, `${x.numero}/${x.total}`), el('td', null, `${mesAno(x.mes_fatura)}${x.redirecionada ? ' *' : ''}`),
            el('td', 'direita', moeda(x.valor)));
    }
    const total = tabela.createTFoot().insertRow();
    total.append(el('td', null, 'Total'), el('td'), el('td', 'direita', moeda(p.soma)));
    caixa.replaceChildren(el('span', 'mob-previa-titulo', 'Prévia do parcelamento'), tabela);
    const notas = [];
    if (p.parcelas.some((x) => x.redirecionada)) notas.push('* fatura paga: a parcela vai para a próxima em aberto.');
    if ((p.consolidadas || []).length) notas.push(`Fatura consolidada: ${p.consolidadas.map((f) => mesAno(f.competencia)).join(', ')} (pedirá confirmação ao salvar).`);
    if (notas.length) caixa.append(el('span', 'mob-ajuda', notas.join(' ')));
    caixa.hidden = false;
}

function desenharFormulario() {
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const nome = entrada('text', '', { maxlength: '200', placeholder: 'Ex.: Conta de luz, Aluguel, Mercado', autocomplete: 'off' });
    const valor = entrada('number', '', { step: '0.01', min: '0', inputmode: 'decimal', placeholder: '0,00' });
    const categoria = seletor([['', 'Selecione...'], ...estado.categorias.map((c) => [c.id, c.nome])], '');
    const meioPagamento = seletor([['conta', 'Conta a pagar'], ['cartao', 'Cartão de crédito']], 'conta');
    const vencimento = entrada('date', '');
    const competencia = entrada('month', estado.mes);
    let competenciaManual = false;
    const cartao = seletor([['', 'Selecione...']], '');
    const dataCompra = entrada('date', hojeBrasilia());
    const parcelas = entrada('number', '1', { min: '1', max: '48', step: '1', inputmode: 'numeric' });
    const fatura = entrada('month', '');
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
    const cMeioPagamento = campo('Meio de pagamento', meioPagamento);
    const cVencimento = campo('Vencimento', vencimento, { obrigatorio: true });
    const cCompetencia = campo('Competência', competencia, { ajuda: 'Mês do salário que pagará a despesa' });
    const cCartao = campo('Cartão', cartao, { obrigatorio: true });
    const cDataCompra = campo('Data da compra', dataCompra, { obrigatorio: true });
    const cParcelas = campo('Parcelas', parcelas);
    const cFatura = campo('Fatura', fatura, { obrigatorio: true });
    const cDia = campo('Dia da semana', dia, { obrigatorio: true });
    const cFrequencia = campo('Frequência', frequencia);
    const marcaRecorrente = el('label', 'mob-opcao');
    marcaRecorrente.append(recorrente, el('span', null, 'Despesa recorrente'));
    const avisoRecorrencia = el('span', 'mob-ajuda', RECORRENCIA_NO_CARTAO);
    avisoRecorrencia.id = 'mob-recorrencia-cartao';

    // Conta a pagar (o fluxo de antes): vencimento e competencia; a recorrencia abre ao marcar.
    const parVencimento = par(cVencimento, cCompetencia);
    const secaoRecorrencia = el('div', 'mob-condicional');
    secaoRecorrencia.id = 'mob-recorrencia';
    const parSemanal = par(cDia, cFrequencia);
    parSemanal.classList.add('empilha');
    secaoRecorrencia.append(campo('Periodicidade', tipo), parSemanal,
        campo('Pagamento da conta', meio, { ajuda: 'Informativo; o pagamento é feito depois, pela lista' }),
        el('span', 'mob-ajuda', 'As contas são geradas ao abrir cada competência na Lista de Despesas; a competência de cada uma é o mês do vencimento.'));

    // Cartao de credito: a compra da tela Lancamentos do desktop (cartao, data, parcelas, fatura sugerida e previa).
    const secaoCartao = el('div', 'mob-cartao');
    secaoCartao.id = 'mob-cartao';
    const sugestao = el('span', 'mob-ajuda');
    sugestao.id = 'mob-fatura-sugestao';
    const usarSugerida = botao('Usar a fatura sugerida', 'mob-botao-discreto');
    usarSugerida.id = 'mob-usar-sugerida';
    const linhaSugestao = el('div', 'mob-sugestao');
    linhaSugestao.append(sugestao, usarSugerida);
    const previa = el('div', 'mob-previa');
    previa.id = 'mob-previa-parcelas';
    previa.setAttribute('aria-live', 'polite');
    previa.hidden = true;
    secaoCartao.append(par(cCartao, cDataCompra), par(cParcelas, cFatura), linhaSugestao, previa);

    const ehCartao = () => meioPagamento.value === 'cartao';
    const ajustar = () => {
        const noCartao = ehCartao();
        parVencimento.hidden = noCartao;
        secaoCartao.hidden = !noCartao;
        // Recorrencia no cartao: etapa posterior (sem cadastro aqui); a recorrencia de conta segue como antes.
        if (noCartao) recorrente.checked = false;
        recorrente.disabled = noCartao;
        marcaRecorrente.classList.toggle('desabilitada', noCartao);
        avisoRecorrencia.hidden = !noCartao;
        secaoRecorrencia.hidden = noCartao || !recorrente.checked;
        parSemanal.hidden = tipo.value !== 'semanal';
        cCompetencia.hidden = recorrente.checked;  // na recorrencia o banco usa o mes de cada vencimento
        parVencimento.classList.toggle('um', recorrente.checked);
    };
    recorrente.addEventListener('change', ajustar);
    tipo.addEventListener('change', ajustar);
    competencia.addEventListener('input', () => { competenciaManual = true; });
    vencimento.addEventListener('change', () => {
        if (vencimento.value && !competenciaManual) competencia.value = competenciaDoVencimento(vencimento.value);
    });

    // Fatura sugerida pelo fechamento (como na tela Lancamentos): nunca sobrescreve o mes escolhido pelo usuario.
    const sug = { manual: false, sugerida: null, resposta: null, pedido: 0 };
    const mostrarSugestao = () => {
        const { texto: t, alerta } = textoSugestao(sug.resposta, { manual: sug.manual, escolhido: fatura.value });
        sugestao.textContent = t;
        sugestao.classList.toggle('alerta', alerta);
        linhaSugestao.hidden = !t;
        usarSugerida.hidden = !(sug.sugerida && sug.manual && fatura.value !== sug.sugerida);
    };
    const atualizarSugestao = async () => {
        const pedido = ++sug.pedido;
        sug.sugerida = null;
        sug.resposta = null;
        if (!cartao.value || !dataCompra.value) { mostrarSugestao(); return; }
        const r = await api('GET', `/api/cartoes/${cartao.value}/competencia-sugerida?data=${encodeURIComponent(dataCompra.value)}`,
            null, responderCompras);
        if (pedido !== sug.pedido) return;  // cartao ou data mudaram durante a consulta
        sug.resposta = r && r.situacao ? r : { situacao: 'INDISPONIVEL' };
        if (sug.resposta.situacao === 'SUGERIDA') {
            sug.sugerida = sug.resposta.competencia.slice(0, 7);
            if (!sug.manual) fatura.value = sug.sugerida;
        } else if (!sug.manual) {
            fatura.value = mesSemSugestao(sug.resposta.situacao, estado.mes);
        }
        mostrarSugestao();
        agendarPrevia();
    };
    fatura.addEventListener('input', () => { sug.manual = true; mostrarSugestao(); });
    usarSugerida.addEventListener('click', () => {
        if (!sug.sugerida) return;
        sug.manual = false;
        fatura.value = sug.sugerida;
        mostrarSugestao();
        agendarPrevia();
    });

    let temporizador = null;
    let pedidoPrevia = 0;
    const agendarPrevia = () => {
        clearTimeout(temporizador);
        temporizador = setTimeout(async () => {
            const pedido = ++pedidoPrevia;
            const n = Number.parseInt(parcelas.value, 10);
            if (!ehCartao() || !(n >= 2) || !(parseFloat(valor.value) > 0) || !cartao.value || !dataCompra.value || !/^\d{4}-\d{2}$/.test(fatura.value)) {
                previa.hidden = true;
                previa.replaceChildren();
                return;
            }
            const q = new URLSearchParams({ cartao_id: cartao.value, valor: parseFloat(valor.value).toFixed(2), total_parcelas: String(n),
                data_compra: dataCompra.value, mes_fatura: `${fatura.value}-01`, descricao: nome.value, categoria_id: categoria.value });
            const r = await api('GET', `/api/lancamentos/previa-parcelas?${q}`, null, responderCompras);
            if (pedido !== pedidoPrevia) return;
            if (r && r.success && r.data && Array.isArray(r.data.parcelas)) desenharPrevia(previa, r.data);
            else {
                previa.replaceChildren(el('span', 'mob-ajuda alerta', (r && r.error) || 'Não foi possível montar a prévia das parcelas.'));
                previa.hidden = false;
            }
        }, 300);
    };
    cartao.addEventListener('change', atualizarSugestao);
    dataCompra.addEventListener('change', atualizarSugestao);
    for (const controle of [valor, parcelas, fatura, categoria]) controle.addEventListener('input', agendarPrevia);
    categoria.addEventListener('change', agendarPrevia);

    meioPagamento.addEventListener('change', async () => {
        ajustar();
        if (!ehCartao()) return;
        const lista = await carregarCartoes();
        if (!lista) { cCartao.erro('Não foi possível carregar os cartões.'); return; }
        if (cartao.options.length === 1) {
            for (const c of lista) cartao.append(new Option(c.nome, String(c.id)));
            if (!lista.length) cCartao.erro('Nenhum cartão ativo neste perfil: cadastre o cartão no desktop.');
            if (lista.length === 1) cartao.value = String(lista[0].id);
        }
        if (cartao.value && !sug.resposta) atualizarSugestao();
        agendarPrevia();
    });
    ajustar();

    const m = mensagem();
    // Fatura consolidada: a mesma pergunta do desktop, aqui no proprio formulario (totais da previa do banco).
    const consolidada = el('div', 'mob-consolidada');
    consolidada.id = 'mob-consolidada';
    consolidada.hidden = true;

    const campos = [cNome, cValor, cCategoria, cVencimento, cCompetencia, cDia, cCartao, cDataCompra, cParcelas, cFatura];
    const limparErros = () => { campos.forEach((c) => c.erro('')); mostrarMensagem(m, ''); };
    for (const [c, controle] of [[cNome, nome], [cValor, valor], [cCategoria, categoria], [cVencimento, vencimento],
        [cCompetencia, competencia], [cDia, dia], [cCartao, cartao], [cDataCompra, dataCompra], [cParcelas, parcelas], [cFatura, fatura]]) {
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

    form.append(cNome, par(cValor, cCategoria), cMeioPagamento, parVencimento, secaoCartao, marcaRecorrente, avisoRecorrencia,
        secaoRecorrencia, campo('Observações', observacoes), m, consolidada, acoes);

    // Mudou algo com a pergunta da fatura consolidada aberta: a pergunta (e o total visto) deixa de valer.
    form.addEventListener('input', () => {
        if (consolidada.hidden || estado.enviando) return;
        consolidada.hidden = true;
        salvar.disabled = false;
    });

    const liberar = () => { estado.enviando = false; salvar.disabled = false; };
    const erroDoServico = (erro, pares) => {
        const doCampo = pares.find(([padrao]) => padrao.test(erro));
        if (doCampo) doCampo[1].erro(erro);
        mostrarMensagem(m, erro, 'erro');
    };

    // Compra no cartao: POST /api/cartoes/:id/lancamentos -> criar_compra (o corpo da tela Lancamentos do desktop).
    async function salvarCompra(confirmar = null) {
        const corpo = {
            cartao_id: parseInt(cartao.value, 10), categoria_id: parseInt(categoria.value, 10), descricao: nome.value.trim(),
            valor: parseFloat(valor.value), data_compra: dataCompra.value, mes_fatura: fatura.value, numero_parcela: 1,
            total_parcelas: parseInt(parcelas.value, 10) || 1, observacoes: observacoes.value.trim(),
        };
        if (confirmar) corpo.confirmar_consolidadas = confirmar;
        estado.enviando = true;
        salvar.disabled = true;
        consolidada.hidden = true;
        mostrarMensagem(m, 'Salvando...');
        const r = await api('POST', `/api/cartoes/${corpo.cartao_id}/lancamentos`, corpo, responderCompras);
        if (r && r.codigo === 'CONFIRMAR_FATURA_CONSOLIDADA') {
            estado.enviando = false;
            mostrarMensagem(m, '');
            const sim = botao('Confirmar inclusão', 'primario');
            sim.id = 'mob-confirmar-inclusao';
            const nao = botao('Não incluir');
            nao.id = 'mob-nao-incluir';
            const botoes = el('div', 'mob-acoes');
            botoes.append(nao, sim);
            consolidada.replaceChildren(el('p', 'mob-confirmacao-titulo', 'Fatura já consolidada'),
                ...(r.faturas || []).map((f) => texto(textoConsolidada(f))),
                texto('Confirmar a inclusão? O total consolidado será atualizado e a inclusão ficará registrada.', 'discreto'), botoes);
            consolidada.hidden = false;
            nao.addEventListener('click', () => {
                consolidada.hidden = true;
                liberar();
                mostrarMensagem(m, 'Compra não salva: a inclusão na fatura consolidada não foi confirmada.', 'erro');
            });
            sim.addEventListener('click', () => {
                if (estado.enviando) return;
                salvarCompra((r.faturas || []).map((f) => ({ fatura_id: f.fatura_id, total_consolidado: f.total_consolidado })));
            });
            sim.focus();
            return;
        }
        if (!r || !r.success) {
            liberar();
            erroDoServico((r && r.error) || 'Falha ao salvar. Nada foi gravado.', [[/fatura/i, cFatura], [/parcela/i, cParcelas],
                [/valor/i, cValor], [/categoria/i, cCategoria], [/cart[aã]o/i, cCartao], [/data/i, cDataCompra], [/descri/i, cNome]]);
            return;
        }
        const nomeCartao = cartao.selectedOptions[0] ? cartao.selectedOptions[0].textContent : '';
        desenharConfirmacaoCompra(corpo, nomeCartao, (r.data && r.data.faturas) || [`${corpo.mes_fatura}-01`]);
    }

    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (estado.enviando || !consolidada.hidden) return;
        limparErros();
        // As validacoes do formulario do desktop (campos obrigatorios) e as do servico, junto ao campo.
        const erros = [];
        if (!nome.value.trim()) erros.push([cNome, 'Informe a descrição.']);
        if (!(parseFloat(valor.value) > 0)) erros.push([cValor, 'Informe um valor válido.']);
        if (!categoria.value) erros.push([cCategoria, 'Selecione a categoria.']);
        if (ehCartao()) {
            const n = Number(parcelas.value);
            if (!cartao.value) erros.push([cCartao, 'Selecione o cartão.']);
            if (!dataCompra.value) erros.push([cDataCompra, 'Informe a data da compra.']);
            if (!(Number.isInteger(n) && n >= 1 && n <= 48)) erros.push([cParcelas, 'Parcelas: de 1 a 48.']);
            if (!/^\d{4}-\d{2}$/.test(fatura.value)) erros.push([cFatura, 'Escolha o mês da fatura.']);
        } else {
            if (!vencimento.value) erros.push([cVencimento, 'Informe a data de vencimento.']);
            if (!recorrente.checked && !/^\d{4}-\d{2}$/.test(competencia.value)) erros.push([cCompetencia, 'Informe a competência.']);
            if (recorrente.checked && tipo.value === 'semanal' && !dia.value) erros.push([cDia, 'Selecione o dia da semana.']);
        }
        if (erros.length) {
            erros.forEach(([c, t]) => c.erro(t));
            erros[0][0].querySelector('input, select, textarea').focus();
            return;
        }
        if (ehCartao()) { await salvarCompra(); return; }
        estado.enviando = true;
        salvar.disabled = true;
        mostrarMensagem(m, 'Salvando...');
        // Conta a pagar: o mesmo corpo do desktop (salvarDespesa); despesa ja paga nao e cadastrada por aqui (pago: false).
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
            liberar();
            // Mensagem do banco junto ao campo que ela cita (competencia antes: "a ate 12 meses do vencimento").
            erroDoServico(r.error || 'Falha ao salvar. Nada foi gravado.', [[/compet/i, cCompetencia], [/valor/i, cValor],
                [/categoria/i, cCategoria], [/nome/i, cNome], [/vencimento/i, cVencimento]]);
            return;
        }
        const mesDaLista = recorrente.checked ? vencimento.value.slice(0, 7) : competencia.value;
        desenharConfirmacao(r.message || 'Despesa salva.', mesDaLista, corpo.nome);
    });
    $('mob-cadastro').replaceChildren(form);
    nome.focus();
}

function acoesDaConfirmacao(principal) {
    const outra = botao('Nova despesa');
    outra.id = 'mob-outra';
    outra.addEventListener('click', () => { mostrarAviso(''); desenharFormulario(); });
    const inicio = el('a', 'mob-botao', 'Início');
    inicio.href = `inicio.html?mes=${estado.mes}`;
    const acoes = el('div', 'mob-acoes');
    acoes.append(principal, outra, inicio);
    return acoes;
}

// Depois de salvar: confirmacao discreta e os caminhos (nada de redirecionar sozinho).
function desenharConfirmacao(mensagemDoServico, mes, nome) {
    estado.enviando = false;
    const caixa = el('div', 'mob-confirmacao');
    caixa.id = 'mob-confirmacao';
    const lista = el('a', 'mob-botao primario', 'Ver na Lista de Despesas');
    lista.id = 'mob-ver-lista';
    lista.href = `despesas-mobile.html?mes=${mes}`;
    caixa.append(el('p', 'mob-confirmacao-titulo', `“${nome}” cadastrada`), texto(mensagemDoServico),
        texto(`Lista de Despesas: ${formatarCompetencia(mes)}.`, 'discreto'), acoesDaConfirmacao(lista));
    $('mob-cadastro').replaceChildren(caixa);
}

// Compra no cartao: a fatura (ou as faturas, no parcelamento) em que entrou e o caminho para o cartao.
function desenharConfirmacaoCompra(corpo, nomeCartao, faturas) {
    estado.enviando = false;
    const meses = [...faturas].map((f) => String(f).slice(0, 7)).sort();
    const primeira = meses[0];
    const caixa = el('div', 'mob-confirmacao');
    caixa.id = 'mob-confirmacao';
    const ver = el('a', 'mob-botao primario', 'Ver no cartão');
    ver.id = 'mob-ver-cartao';
    ver.href = `cartoes-mobile.html?mes=${primeira}&cartao=${corpo.cartao_id}`;
    const onde = corpo.total_parcelas > 1
        ? `Compra lançada em ${corpo.total_parcelas} parcelas no cartão ${nomeCartao}: faturas ${mesAno(`${primeira}-01`)} a ${mesAno(`${meses[meses.length - 1]}-01`)}.`
        : `Compra lançada na fatura ${mesAno(`${primeira}-01`)} do cartão ${nomeCartao}.`;
    caixa.append(el('p', 'mob-confirmacao-titulo', `“${corpo.descricao}” lançada no cartão`), texto(onde),
        texto('A compra entra na fatura do cartão (sem conta a pagar separada).', 'discreto'), acoesDaConfirmacao(ver));
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
        configurarCompras(perfil.id);
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
