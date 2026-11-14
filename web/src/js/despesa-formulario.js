// FIN-MVP-MOBILE-05 — formulario "Nova Despesa" mobile (homologado em 14/11/2026). FIN-MVP-MOBILE-06: extraido de
// js/despesa-nova-mobile.js, sem mudar o comportamento, para servir a Nova Despesa e o Registrar Lancamento (opcoes
// Despesa e Compra no cartao) com um so formulario.
// O formulario "Nova Despesa" do desktop (js/original/despesas.js + a recusa do servico), em versao compacta e progressiva,
// pelo mesmo servico e rota: POST /api/despesas em js/despesas-servico.js -> criar_despesa (chave de idempotencia).
// - Campos gravados: nome ("Descricao" aqui), valor, categoria, vencimento, competencia (despesa simples), recorrencia
//   (mensal, anual ou semanal com dia e frequencia 1 ou 2) e o meio de pagamento informativo da recorrencia; a
//   "Descricao" opcional do desktop vai em "Observacoes".
// - Competencia: a do mes aberto na pagina principal; ao escolher o vencimento, a regra do desktop (mes anterior ao
//   vencimento) enquanto o usuario nao mudar a competencia. Na recorrencia, a competencia e a de cada vencimento (banco).
// - O que o servico do desktop recusa nao aparece: despesa ja paga (o pagamento e pela acao Pagar da lista) e consorcio.
// - "Meio de pagamento" logo apos descricao, valor e categoria: "Conta a pagar" (o fluxo acima) ou "Cartao de credito": a
//   compra da tela Lancamentos do desktop (js/mobile-cartao.js), gravada so por criar_compra (js/compras-servico.js,
//   POST /api/cartoes/:id/lancamentos), com a confirmacao de fatura consolidada. E uma coisa ou outra: a compra entra na
//   fatura e nenhuma conta a pagar e criada. No cartao a recorrencia fica desabilitada (etapa posterior).
// Nenhuma regra financeira nova. Sem innerHTML (CSP): tudo por createElement.

import { deslocarMes, el } from './comum.js';
import { responderCompras } from './compras-servico.js';
import { formatarCompetencia } from './despesas-grupos.js';
import { botao, entrada, mensagem, mostrarAviso, mostrarMensagem, seletor, texto } from './mobile-ui.js';
import { blocoCartao } from './mobile-cartao.js';
import { campoComErro, erroDoServico, mesAno, mostrarErros, par, perguntaConsolidada } from './mobile-formulario.js';

export const RECORRENCIA_NO_CARTAO = 'O cadastro de despesas recorrentes no cartão de crédito será disponibilizado em uma etapa posterior.';

const DIAS = [['', 'Selecione...'], ['0', 'Domingo'], ['1', 'Segunda-feira'], ['2', 'Terça-feira'], ['3', 'Quarta-feira'],
    ['4', 'Quinta-feira'], ['5', 'Sexta-feira'], ['6', 'Sábado']];

// Regra do desktop (calcularCompetenciaAutomaticamente): o mes anterior ao do vencimento. Por mes, nao por data: no
// desktop, vencimento em 29 a 31 cujo mes anterior e mais curto caia no proprio mes (Date.setMonth; 31/03 -> 03/03).
const competenciaDoVencimento = (vencimento) => deslocarMes(vencimento.slice(0, 7), -1);

// opcoes: api (fila da tela: servico de Despesas por padrao), mes (competencia da pagina principal), categorias,
// meio ('conta' | 'cartao', o inicial), rotuloNovo (botao da confirmacao que recomeca o formulario).
export function montarFormularioDespesa(container, opcoes) {
    const { api, mes, categorias, meio: meioInicial = 'conta' } = opcoes;
    let enviando = false;
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const nome = entrada('text', '', { maxlength: '200', placeholder: 'Ex.: Conta de luz, Aluguel, Mercado', autocomplete: 'off' });
    const valor = entrada('number', '', { step: '0.01', min: '0', inputmode: 'decimal', placeholder: '0,00' });
    const categoria = seletor([['', 'Selecione...'], ...categorias.map((c) => [c.id, c.nome])], '');
    const meioPagamento = seletor([['conta', 'Conta a pagar'], ['cartao', 'Cartão de crédito']], meioInicial);
    const vencimento = entrada('date', '');
    const competencia = entrada('month', mes);
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

    const cNome = campoComErro('Descrição', nome, { obrigatorio: true });
    const cValor = campoComErro('Valor', valor, { obrigatorio: true });
    const cCategoria = campoComErro('Categoria', categoria, { obrigatorio: true });
    const cMeioPagamento = campoComErro('Meio de pagamento', meioPagamento);
    const cVencimento = campoComErro('Vencimento', vencimento, { obrigatorio: true });
    const cCompetencia = campoComErro('Competência', competencia, { ajuda: 'Mês do salário que pagará a despesa' });
    const cDia = campoComErro('Dia da semana', dia, { obrigatorio: true });
    const cFrequencia = campoComErro('Frequência', frequencia);
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
    secaoRecorrencia.append(campoComErro('Periodicidade', tipo), parSemanal,
        campoComErro('Pagamento da conta', meio, { ajuda: 'Informativo; o pagamento é feito depois, pela lista' }),
        el('span', 'mob-ajuda', 'As contas são geradas ao abrir cada competência na Lista de Despesas; a competência de cada uma é o mês do vencimento.'));

    const ehCartao = () => meioPagamento.value === 'cartao';
    // Cartao de credito: a compra da tela Lancamentos do desktop (cartao, data, parcelas, fatura sugerida e previa).
    const bloco = blocoCartao({ api, mesPadrao: mes, valor: () => parseFloat(valor.value), descricao: () => nome.value,
        categoria: () => categoria.value, ativo: ehCartao });
    for (const controle of [valor, categoria]) controle.addEventListener('input', bloco.agendarPrevia);
    categoria.addEventListener('change', bloco.agendarPrevia);

    const ajustar = () => {
        const noCartao = ehCartao();
        parVencimento.hidden = noCartao;
        bloco.elemento.hidden = !noCartao;
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
    meioPagamento.addEventListener('change', () => {
        ajustar();
        if (ehCartao()) bloco.ativar();
    });
    ajustar();
    if (ehCartao()) bloco.ativar();

    const m = mensagem();
    const consolidada = el('div', 'mob-consolidada');
    consolidada.id = 'mob-consolidada';
    consolidada.hidden = true;

    const cancelar = el('a', 'mob-botao', 'Cancelar');
    cancelar.id = 'mob-cancelar';
    cancelar.href = `inicio.html?mes=${mes}`;
    const salvar = botao('Salvar', 'primario');
    salvar.type = 'submit';
    salvar.id = 'mob-salvar';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, salvar);

    form.append(cNome, par(cValor, cCategoria), cMeioPagamento, parVencimento, bloco.elemento, marcaRecorrente, avisoRecorrencia,
        secaoRecorrencia, campoComErro('Observações', observacoes), m, consolidada, acoes);

    // Mudou algo com a pergunta da fatura consolidada aberta: a pergunta (e o total visto) deixa de valer.
    form.addEventListener('input', () => {
        if (consolidada.hidden || enviando) return;
        consolidada.hidden = true;
        salvar.disabled = false;
    });

    const liberar = () => { enviando = false; salvar.disabled = false; };

    // Compra no cartao: POST /api/cartoes/:id/lancamentos -> criar_compra (o corpo da tela Lancamentos do desktop).
    async function salvarCompra(confirmar = null) {
        const corpo = {
            cartao_id: parseInt(bloco.cartao.value, 10), categoria_id: parseInt(categoria.value, 10), descricao: nome.value.trim(),
            valor: parseFloat(valor.value), data_compra: bloco.dataCompra.value, mes_fatura: bloco.fatura.value, numero_parcela: 1,
            total_parcelas: bloco.totalParcelas(), observacoes: observacoes.value.trim(),
        };
        if (confirmar) corpo.confirmar_consolidadas = confirmar;
        enviando = true;
        salvar.disabled = true;
        consolidada.hidden = true;
        mostrarMensagem(m, 'Salvando...');
        const r = await api('POST', `/api/cartoes/${corpo.cartao_id}/lancamentos`, corpo, responderCompras);
        if (r && r.codigo === 'CONFIRMAR_FATURA_CONSOLIDADA') {
            enviando = false;
            mostrarMensagem(m, '');
            perguntaConsolidada(consolidada, r.faturas, {
                aoRecusar: () => {
                    consolidada.hidden = true;
                    liberar();
                    mostrarMensagem(m, 'Compra não salva: a inclusão na fatura consolidada não foi confirmada.', 'erro');
                },
                aoConfirmar: (confirmacoes) => { if (!enviando) salvarCompra(confirmacoes); },
            });
            return;
        }
        if (!r || !r.success) {
            liberar();
            erroDoServico(m, (r && r.error) || 'Falha ao salvar. Nada foi gravado.', [[/fatura/i, bloco.cFatura], [/parcela/i, bloco.cParcelas],
                [/valor/i, cValor], [/categoria/i, cCategoria], [/cart[aã]o/i, bloco.cCartao], [/data/i, bloco.cDataCompra], [/descri/i, cNome]]);
            return;
        }
        desenharConfirmacaoCompra(container, opcoes, corpo, bloco.nomeCartao(), (r.data && r.data.faturas) || [`${corpo.mes_fatura}-01`]);
    }

    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (enviando || !consolidada.hidden) return;
        for (const c of form.querySelectorAll('.mob-campo')) if (c.erro) c.erro('');
        mostrarMensagem(m, '');
        // As validacoes do formulario do desktop (campos obrigatorios) e as do servico, junto ao campo.
        const erros = [];
        if (!nome.value.trim()) erros.push([cNome, 'Informe a descrição.']);
        if (!(parseFloat(valor.value) > 0)) erros.push([cValor, 'Informe um valor válido.']);
        if (!categoria.value) erros.push([cCategoria, 'Selecione a categoria.']);
        if (ehCartao()) {
            erros.push(...bloco.validar());
        } else {
            if (!vencimento.value) erros.push([cVencimento, 'Informe a data de vencimento.']);
            if (!recorrente.checked && !/^\d{4}-\d{2}$/.test(competencia.value)) erros.push([cCompetencia, 'Informe a competência.']);
            if (recorrente.checked && tipo.value === 'semanal' && !dia.value) erros.push([cDia, 'Selecione o dia da semana.']);
        }
        if (mostrarErros(erros)) return;
        if (ehCartao()) { await salvarCompra(); return; }
        enviando = true;
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
            erroDoServico(m, r.error || 'Falha ao salvar. Nada foi gravado.', [[/compet/i, cCompetencia], [/valor/i, cValor],
                [/categoria/i, cCategoria], [/nome/i, cNome], [/vencimento/i, cVencimento]]);
            return;
        }
        const mesDaLista = recorrente.checked ? vencimento.value.slice(0, 7) : competencia.value;
        desenharConfirmacao(container, opcoes, r.message || 'Despesa salva.', mesDaLista, corpo.nome);
    });
    container.replaceChildren(form);
    nome.focus();
    return form;
}

function acoesDaConfirmacao(container, opcoes, principal) {
    const outra = botao(opcoes.rotuloNovo || 'Nova despesa');
    outra.id = 'mob-outra';
    outra.addEventListener('click', () => {
        mostrarAviso('');
        if (opcoes.aoRecomecar) opcoes.aoRecomecar();
        else montarFormularioDespesa(container, opcoes);
    });
    const inicio = el('a', 'mob-botao', 'Início');
    inicio.href = `inicio.html?mes=${opcoes.mes}`;
    const acoes = el('div', 'mob-acoes');
    acoes.append(principal, outra, inicio);
    return acoes;
}

// Depois de salvar: confirmacao discreta e os caminhos (nada de redirecionar sozinho).
function desenharConfirmacao(container, opcoes, mensagemDoServico, mes, nome) {
    const caixa = el('div', 'mob-confirmacao');
    caixa.id = 'mob-confirmacao';
    const lista = el('a', 'mob-botao primario', 'Ver na Lista de Despesas');
    lista.id = 'mob-ver-lista';
    lista.href = `despesas-mobile.html?mes=${mes}`;
    caixa.append(el('p', 'mob-confirmacao-titulo', `“${nome}” cadastrada`), texto(mensagemDoServico),
        texto(`Lista de Despesas: ${formatarCompetencia(mes)}.`, 'discreto'), acoesDaConfirmacao(container, opcoes, lista));
    container.replaceChildren(caixa);
    if (opcoes.aoConcluir) opcoes.aoConcluir();
}

// Compra no cartao: a fatura (ou as faturas, no parcelamento) em que entrou e o caminho para o cartao.
export function desenharConfirmacaoCompra(container, opcoes, corpo, nomeCartao, faturas, nota = 'A compra entra na fatura do cartão (sem conta a pagar separada).') {
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
        texto(nota, 'discreto'), acoesDaConfirmacao(container, opcoes, ver));
    container.replaceChildren(caixa);
    if (opcoes.aoConcluir) opcoes.aoConcluir();
}

export { acoesDaConfirmacao };
