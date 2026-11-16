// FIN-MVP-CADASTRO-UNIFICADO-01 — modal unico e responsivo de cadastro de despesas, para Despesas, Lancamentos e
// Recorrencias (desktop e mobile). Um so componente; o "Tipo de operacao" decide os campos visiveis e o servico que grava:
//   DESPESA_DIRETA     -> POST /api/despesas                (js/despesas-servico.js     -> criar_despesa)
//   COMPRA_CARTAO      -> POST /api/cartoes/:id/lancamentos (js/compras-servico.js      -> criar_compra)
//   DESPESA_RECORRENTE -> POST /api/recorrencias            (js/recorrencias-servico.js -> criar_despesa recorrente ou
//                                                            criar_recorrencia_cartao)
//   CONSORCIO          -> POST /api/consorcios              (js/recorrencias-servico.js -> criar_consorcio)
// Nenhuma regra financeira aqui: validacoes, competencia, fatura, parcelas, geracao e idempotencia sao as dos servicos.
// - Cadastro e pagamento separados: nao existe "Despesa ja foi paga"; nenhum corpo leva pago, data ou conta de pagamento.
// - Cada troca de tipo reconstroi os campos do tipo: nada de um tipo viaja no corpo de outro (so nome, valor, categoria e
//   observacoes passam adiante).
// - So cadastro: a edicao continua nas telas de cada modulo.
// Sem innerHTML e sem estilo inline (CSP): tudo por createElement; aparencia em css/cadastro-despesa.css.

import { deslocarMes, el, mesAtualBrasilia } from './comum.js';
import { hojeBrasilia } from './adaptador-comum.js';
import { configurarCompras, responderCompras } from './compras-servico.js';
import { configurarDespesas, podeGerirPerfil, responderDespesas } from './despesas-servico.js';
import { configurarRecorrencias, responderRecorrencias } from './recorrencias-servico.js';
import { blocoCartao } from './mobile-cartao.js';
import { campoComErro, criarFila, erroDoServico, mesAno, moeda, mostrarErros, perguntaConsolidada } from './mobile-formulario.js';
import { entrada, mensagem, mostrarMensagem, seletor } from './mobile-ui.js';

export const TIPOS = Object.freeze({
    DESPESA_DIRETA: 'DESPESA_DIRETA', COMPRA_CARTAO: 'COMPRA_CARTAO', DESPESA_RECORRENTE: 'DESPESA_RECORRENTE', CONSORCIO: 'CONSORCIO',
});
const ROTULOS = { DESPESA_DIRETA: 'Despesa direta', COMPRA_CARTAO: 'Compra no cartão', DESPESA_RECORRENTE: 'Despesa recorrente', CONSORCIO: 'Consórcio' };
const DIAS = ['Domingo', 'Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado'];
const LIMITE_OBSERVACOES = 500;
const FALHA = 'Falha ao salvar. Nada foi gravado.';

const api = criarFila('Cadastro de despesa', responderDespesas);
let avisoDaRecorrencia = '';  // texto do servico de Recorrencias sobre a ultima gravacao (quando o servico e configurado aqui)

// Perfil em uso nos tres servicos. A tela que ja configurou um servico (com os ganchos dela) passa false para ele.
export function prepararCadastro(perfilId, { despesas = true, compras = true, recorrencias = true } = {}) {
    if (despesas) configurarDespesas(perfilId);
    if (compras) configurarCompras(perfilId);
    if (recorrencias) configurarRecorrencias(perfilId, { avisar: (texto) => { avisoDaRecorrencia = texto; } });
}

const competenciaPorExtenso = (mes) => {
    const [ano, m] = mes.split('-').map(Number);
    return `${new Intl.DateTimeFormat('pt-BR', { month: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(ano, m - 1, 1)))}/${ano}`;
};
// Regra do formulario original (calcularCompetenciaAutomaticamente): o mes anterior ao do vencimento, por mes.
const competenciaDoVencimento = (vencimento) => deslocarMes(vencimento.slice(0, 7), -1);
const numero = (controle) => Number.parseFloat(controle.value);

// Botao do modal (classes do proprio componente, iguais no desktop e no mobile).
function botao(texto, classe) {
    const b = el('button', classe, texto);
    b.type = 'button';
    return b;
}

function inteiro(no) {
    no.classList.add('cad-inteiro');
    return no;
}
function meio(no) {
    no.classList.add('cad-meio');
    return no;
}

// Secao recolhida sob uma acao compacta ("+ Observacoes", "+ Opcoes adicionais"); aberta, mantem o conteudo.
function recolhida(rotulo, conteudo, { aberta = false, id } = {}) {
    const caixa = inteiro(el('div', 'cad-recolhida'));
    const acao = botao(`+ ${rotulo}`, 'cad-link');
    if (id) acao.id = id;
    acao.setAttribute('aria-expanded', String(aberta));
    conteudo.hidden = !aberta;
    acao.hidden = aberta;
    acao.addEventListener('click', () => {
        conteudo.hidden = false;
        acao.hidden = true;
        acao.setAttribute('aria-expanded', 'true');
        const primeiro = conteudo.querySelector('textarea, input, select');
        if (primeiro) primeiro.focus();
    });
    caixa.append(acao, conteudo);
    return caixa;
}

function campoObservacoes(comum) {
    const area = el('textarea');
    area.rows = 2;
    area.maxLength = LIMITE_OBSERVACOES;
    area.placeholder = 'Observações adicionais (opcional)';
    area.value = comum.observacoes;
    const contador = el('span', 'cad-contador', `${area.value.length}/${LIMITE_OBSERVACOES}`);
    area.addEventListener('input', () => {
        comum.observacoes = area.value;
        contador.textContent = `${area.value.length}/${LIMITE_OBSERVACOES}`;
    });
    const campo = campoComErro('Observações', area);
    campo.append(contador);
    return { area, no: recolhida('Observações', campo, { aberta: Boolean(comum.observacoes), id: 'cad-abrir-observacoes' }) };
}

// Nome, valor e categoria: existem em todos os tipos (o rotulo muda) e passam de um tipo para o outro.
function camposComuns(comum, categorias, { rotuloNome, exemplo, rotuloValor = 'Valor' }) {
    const nome = entrada('text', comum.nome, { maxlength: '200', autocomplete: 'off', placeholder: exemplo });
    nome.id = 'cad-nome';
    const valor = entrada('number', comum.valor, { step: '0.01', min: '0', inputmode: 'decimal', placeholder: '0,00' });
    valor.id = 'cad-valor';
    const categoria = seletor([['', 'Selecione uma categoria...'], ...categorias.map((c) => [c.id, c.nome])], comum.categoria);
    categoria.id = 'cad-categoria';
    nome.addEventListener('input', () => { comum.nome = nome.value; });
    valor.addEventListener('input', () => { comum.valor = valor.value; });
    categoria.addEventListener('change', () => { comum.categoria = categoria.value; });
    const cNome = campoComErro(rotuloNome, nome, { obrigatorio: true });
    const cValor = campoComErro(rotuloValor, valor, { obrigatorio: true });
    const cCategoria = campoComErro('Categoria', categoria, { obrigatorio: true });
    const erros = () => {
        const lista = [];
        if (!nome.value.trim()) lista.push([cNome, `Informe ${rotuloNome === 'Nome' ? 'o nome' : rotuloNome.toLowerCase().replace(/^(\S)/, 'a $1')}.`]);
        if (!(numero(valor) > 0)) lista.push([cValor, 'Informe um valor válido.']);
        if (!categoria.value) lista.push([cCategoria, 'Selecione a categoria.']);
        return lista;
    };
    return { nome, valor, categoria, cNome, cValor, cCategoria, erros };
}

const nota = (texto, classe = '') => inteiro(el('p', `cad-nota${classe ? ` cad-nota-${classe}` : ''}`, texto));

// ---------------------------------------------------------------------------------------------------------------
// 1. Despesa direta: obrigacao Pendente; o pagamento e depois, pela acao Pagar.

function despesaDireta(ctx) {
    const { comum, categorias, mes, dados } = ctx;
    const c = camposComuns(comum, categorias, { rotuloNome: 'Nome', exemplo: 'Ex.: Conta de luz, Aluguel, Mercado' });
    const vencimento = entrada('date', dados.data || '');
    vencimento.id = 'cad-vencimento';
    const cVencimento = campoComErro('Data de vencimento', vencimento, { obrigatorio: true });

    // Competencia: informacao compacta; a alteracao manual continua possivel, por uma acao discreta.
    const competencia = entrada('month', mes);
    competencia.id = 'cad-competencia';
    let manual = false;
    const textoCompetencia = el('span', 'cad-competencia-texto');
    textoCompetencia.id = 'cad-competencia-texto';
    const alterar = botao('Alterar competência', 'cad-link');
    alterar.id = 'cad-alterar-competencia';
    const resumo = el('div', 'cad-competencia');
    resumo.append(textoCompetencia, alterar);
    const cCompetencia = campoComErro('Competência', competencia, { ajuda: 'Mês do salário que pagará a despesa' });
    cCompetencia.hidden = true;
    const caixaCompetencia = meio(el('div', 'cad-competencia-caixa'));
    caixaCompetencia.append(resumo, cCompetencia);
    const mostrar = () => {
        textoCompetencia.textContent = /^\d{4}-\d{2}$/.test(competencia.value) ? `Competência: ${competenciaPorExtenso(competencia.value)}` : 'Competência: —';
    };
    alterar.addEventListener('click', () => {
        cCompetencia.hidden = false;
        alterar.hidden = true;
        competencia.focus();
    });
    competencia.addEventListener('input', () => { manual = true; mostrar(); });
    vencimento.addEventListener('change', () => {
        if (vencimento.value && !manual) competencia.value = competenciaDoVencimento(vencimento.value);
        mostrar();
    });
    if (vencimento.value) competencia.value = competenciaDoVencimento(vencimento.value);
    mostrar();

    const obs = campoObservacoes(comum);
    return {
        nos: [inteiro(c.cNome), c.cCategoria, c.cValor, meio(cVencimento), caixaCompetencia, obs.no,
            nota('O pagamento é registrado depois, pela ação Pagar: a despesa é cadastrada como pendente.', 'info')],
        foco: c.nome,
        preenchidos: () => [vencimento.value && 'Data de vencimento', manual && 'Competência'].filter(Boolean),
        validar() {
            const erros = c.erros();
            if (!vencimento.value) erros.push([cVencimento, 'Informe a data de vencimento.']);
            if (!/^\d{4}-\d{2}$/.test(competencia.value)) {
                cCompetencia.hidden = false;
                alterar.hidden = true;
                erros.push([cCompetencia, 'Informe a competência.']);
            }
            return erros;
        },
        async salvar() {
            // So os campos da despesa direta: sem pago, data de pagamento ou conta (a despesa nasce Pendente).
            const corpo = { nome: c.nome.value.trim(), descricao: obs.area.value.trim(), valor: numero(c.valor),
                categoria_id: Number(c.categoria.value), data_vencimento: vencimento.value, recorrente: false,
                mes_competencia: competencia.value };
            const r = await api('POST', '/api/despesas', corpo);
            if (!r.success) {
                if (/compet/i.test(r.error || '')) { cCompetencia.hidden = false; alterar.hidden = true; }
                return { erro: r.error || FALHA, pares: [[/compet/i, cCompetencia], [/valor/i, c.cValor], [/categoria/i, c.cCategoria],
                    [/nome/i, c.cNome], [/vencimento/i, cVencimento]] };
            }
            return { titulo: `“${corpo.nome}” cadastrada como pendente`, linhas: [r.message || 'Despesa salva.',
                'Para registrar o pagamento, use a ação Pagar na Lista de Despesas.'],
                destino: { modulo: 'despesas', mes: competencia.value, rotulo: 'Ver na Lista de Despesas' }, registro: { tipo: TIPOS.DESPESA_DIRETA, corpo } };
        },
    };
}

// ---------------------------------------------------------------------------------------------------------------
// 2. Compra no cartao: entra na fatura (nenhuma conta a pagar separada); o pagamento e o da fatura.

function compraCartao(ctx) {
    const { comum, categorias, mes, dados } = ctx;
    const c = camposComuns(comum, categorias, { rotuloNome: 'Descrição', exemplo: 'Ex.: Compras no supermercado' });
    const bloco = blocoCartao({ api, mesPadrao: mes, valor: () => numero(c.valor), descricao: () => c.nome.value,
        categoria: () => c.categoria.value, ativo: () => true, rotulos: { cartao: 'Cartão de crédito', fatura: 'Mês da fatura' } });
    bloco.cartao.id = 'cad-cartao';
    bloco.dataCompra.id = 'cad-data-compra';
    bloco.parcelas.id = 'cad-parcelas';
    bloco.fatura.id = 'cad-mes-fatura';
    if (dados.data) bloco.dataCompra.value = dados.data;
    const dataInicial = bloco.dataCompra.value;
    for (const controle of [c.valor, c.categoria]) controle.addEventListener('input', bloco.agendarPrevia);
    c.categoria.addEventListener('change', bloco.agendarPrevia);
    const obs = campoObservacoes(comum);
    const consolidada = inteiro(el('div', 'mob-consolidada'));
    consolidada.id = 'cad-consolidada';
    consolidada.hidden = true;

    async function gravar(confirmar) {
        const corpo = { cartao_id: Number(bloco.cartao.value), categoria_id: Number(c.categoria.value), descricao: c.nome.value.trim(),
            valor: numero(c.valor), data_compra: bloco.dataCompra.value, mes_fatura: bloco.fatura.value, numero_parcela: 1,
            total_parcelas: bloco.totalParcelas(), observacoes: obs.area.value.trim() };
        if (confirmar) corpo.confirmar_consolidadas = confirmar;
        const r = await api('POST', `/api/cartoes/${corpo.cartao_id}/lancamentos`, corpo, responderCompras);
        if (r && r.codigo === 'CONFIRMAR_FATURA_CONSOLIDADA') {
            // A mesma pergunta das telas atuais: a inclusao em fatura consolidada so com confirmacao explicita.
            return new Promise((resolver) => {
                perguntaConsolidada(consolidada, r.faturas, {
                    aoRecusar: () => {
                        consolidada.hidden = true;
                        resolver({ erro: 'Compra não salva: a inclusão na fatura consolidada não foi confirmada.', pares: [] });
                    },
                    aoConfirmar: (confirmacoes) => { consolidada.hidden = true; resolver(gravar(confirmacoes)); },
                });
                ctx.aguardando();
            });
        }
        if (!r || !r.success) {
            return { erro: (r && r.error) || FALHA, pares: [...bloco.paresDeErro(), [/valor/i, c.cValor], [/categoria/i, c.cCategoria], [/descri/i, c.cNome]] };
        }
        const meses = [...((r.data && r.data.faturas) || [`${corpo.mes_fatura}-01`])].map((f) => String(f).slice(0, 7)).sort();
        const onde = corpo.total_parcelas > 1
            ? `Compra lançada em ${corpo.total_parcelas} parcelas no cartão ${bloco.nomeCartao()}: faturas ${mesAno(`${meses[0]}-01`)} a ${mesAno(`${meses[meses.length - 1]}-01`)}.`
            : `Compra lançada na fatura ${mesAno(`${meses[0]}-01`)} do cartão ${bloco.nomeCartao()}.`;
        return { titulo: `“${corpo.descricao}” lançada no cartão`, linhas: [onde, 'A compra entra na fatura do cartão (sem conta a pagar separada). O pagamento é o da fatura.'],
            destino: { modulo: 'cartoes', mes: meses[0], cartaoId: corpo.cartao_id, rotulo: 'Ver no cartão' }, registro: { tipo: TIPOS.COMPRA_CARTAO, corpo } };
    }

    return {
        nos: [inteiro(bloco.cCartao), c.cCategoria, c.cNome, meio(c.cValor), meio(bloco.cDataCompra), meio(bloco.cParcelas), meio(bloco.cFatura),
            inteiro(bloco.linhaSugestao), inteiro(bloco.previa), obs.no, consolidada],
        foco: bloco.cartao,
        aoMontar: () => bloco.ativar(),
        preenchidos: () => [bloco.cartao.value && bloco.cartao.options.length > 2 && 'Cartão de crédito',
            bloco.dataCompra.value !== dataInicial && 'Data da compra', bloco.totalParcelas() > 1 && 'Parcelas'].filter(Boolean),
        validar: () => [...c.erros(), ...bloco.validar()],
        salvar: () => gravar(null),
    };
}

// ---------------------------------------------------------------------------------------------------------------
// 3. Despesa recorrente: grava a configuracao; as contas (ou compras) sao geradas depois, por competencia.

function despesaRecorrente(ctx) {
    const { comum, categorias, dados } = ctx;
    const c = camposComuns(comum, categorias, { rotuloNome: 'Nome', exemplo: 'Ex.: Aluguel, Academia, Assinatura' });
    const inicio = entrada('date', dados.data || hojeBrasilia());
    inicio.id = 'cad-data-inicial';
    const dataPadrao = inicio.value;
    const frequencia = seletor([['mensal', 'Mensal'], ['semanal', 'Semanal'], ['quinzenal', 'A cada 2 semanas'], ['anual', 'Anual']], 'mensal');
    frequencia.id = 'cad-frequencia';
    const dia = seletor([['', 'Selecione...'], ...DIAS.map((d, i) => [i, d])], '');
    dia.id = 'cad-dia-semana';

    // Meios efetivamente aceitos pelo servico de Recorrencias (o mesmo valor que ele grava).
    const pagamento = el('select');
    pagamento.id = 'cad-meio-pagamento';
    const grupo = el('optgroup');
    grupo.label = 'Conta a pagar';
    for (const [v, t] of [['', 'Conta a pagar (meio não informado)'], ['boleto', 'Conta a pagar — Boleto'], ['pix', 'Conta a pagar — PIX'],
        ['debito', 'Conta a pagar — Débito']]) grupo.append(new Option(t, v));
    pagamento.append(grupo, new Option('Débito automático', 'debito_automatico'), new Option('Cartão de crédito', 'cartao'));
    pagamento.value = '';
    const cartao = seletor([['', 'Selecione um cartão...']], '');
    cartao.id = 'cad-cartao-recorrencia';
    const conta = seletor([['', 'Selecione uma conta...']], '');
    conta.id = 'cad-conta-bancaria';
    const inativa = entrada('checkbox');
    inativa.id = 'cad-inativa';

    const cInicio = campoComErro('Data inicial', inicio, { obrigatorio: true, ajuda: 'Primeiro vencimento' });
    const cFrequencia = campoComErro('Frequência', frequencia, { obrigatorio: true });
    const cDia = campoComErro('Dia da semana', dia, { obrigatorio: true });
    const cPagamento = inteiro(campoComErro('Pagamento da conta', pagamento, { obrigatorio: true }));
    const ajudaPagamento = el('span', 'mob-ajuda');
    cPagamento.insertBefore(ajudaPagamento, cPagamento.lastChild);
    const cCartao = inteiro(campoComErro('Cartão de crédito', cartao, { obrigatorio: true }));
    const ajudaCartao = el('span', 'mob-ajuda');
    ajudaCartao.id = 'cad-categoria-cartao';
    cCartao.insertBefore(ajudaCartao, cCartao.lastChild);
    const cConta = inteiro(campoComErro('Conta bancária do débito automático', conta, { obrigatorio: true,
        ajuda: 'Nenhum pagamento é registrado no cadastro: o débito ocorre em cada vencimento.' }));
    const marcaInativa = el('label', 'cad-opcao');
    marcaInativa.append(inativa, el('span', null, 'Cadastrar inativa (não gera contas até ser reativada)'));
    const opcoes = recolhida('Opções adicionais', marcaInativa, { id: 'cad-abrir-opcoes' });
    const obs = campoObservacoes(comum);

    const semanal = () => frequencia.value === 'semanal' || frequencia.value === 'quinzenal';
    const SEM_CATEGORIA = 'Categoria do cartão: resolvida automaticamente pela categoria da despesa.';
    let pedido = 0;
    async function resolverCategoria() {
        const atual = ++pedido;
        ajudaCartao.textContent = SEM_CATEGORIA;
        if (pagamento.value !== 'cartao' || !cartao.value || !c.categoria.value) return;
        const r = await api('GET', `/api/categorias-cartao/resolver?cartao_id=${cartao.value}&categoria_id=${c.categoria.value}`, null, responderRecorrencias);
        if (atual !== pedido) return;
        const nomeCategoria = r && r.success && r.data && (r.data.categoria_cartao_nome || r.data.nome);
        if (nomeCategoria) ajudaCartao.textContent = `Categoria do cartão: ${nomeCategoria}.`;
    }
    const lidos = { cartoes: false, contas: false };
    async function carregar(qual, rota, controle, campo, vazio, rotulo) {
        if (lidos[qual]) return;
        lidos[qual] = true;
        const r = await api('GET', rota, null, responderRecorrencias);
        if (!r || !r.success) { lidos[qual] = false; campo.erro('Não foi possível carregar a lista.'); return; }
        for (const item of r.data || []) controle.append(new Option(rotulo(item), String(item.id)));
        if (!(r.data || []).length) campo.erro(vazio);
        if ((r.data || []).length === 1) controle.value = String(r.data[0].id);
        if (qual === 'cartoes' && dados.cartao_id) controle.value = String(dados.cartao_id);
        resolverCategoria();
    }
    function ajustar() {
        const noCartao = pagamento.value === 'cartao';
        cDia.hidden = !semanal();
        cCartao.hidden = !noCartao;
        cConta.hidden = pagamento.value !== 'debito_automatico';
        // O servico so lanca compra recorrente mensal ou anual: a combinacao invalida nao e oferecida.
        for (const o of frequencia.querySelectorAll('option[value="semanal"], option[value="quinzenal"]')) o.disabled = noCartao;
        pagamento.querySelector('option[value="cartao"]').disabled = semanal();
        ajudaPagamento.textContent = noCartao ? 'No cartão de crédito: frequência mensal ou anual. As compras entram na fatura.'
            : (semanal() ? 'Semanal e a cada 2 semanas: conta a pagar ou débito automático (no cartão, só mensal ou anual).' : '');
        ajudaPagamento.hidden = !ajudaPagamento.textContent;
        if (noCartao) carregar('cartoes', '/api/cartoes', cartao, cCartao, 'Nenhum cartão ativo neste perfil.', (x) => x.nome);
        if (pagamento.value === 'debito_automatico') {
            carregar('contas', '/api/contas', conta, cConta, 'Nenhuma conta bancária ativa neste perfil.', (x) => (x.instituicao ? `${x.nome} (${x.instituicao})` : x.nome));
        }
        resolverCategoria();
    }
    frequencia.addEventListener('change', ajustar);
    pagamento.addEventListener('change', ajustar);
    cartao.addEventListener('change', resolverCategoria);
    c.categoria.addEventListener('change', resolverCategoria);
    if (dados.meio_pagamento) pagamento.value = dados.meio_pagamento;
    if (dados.frequencia) frequencia.value = dados.frequencia;
    ajustar();

    return {
        nos: [inteiro(c.cNome), c.cCategoria, c.cValor, meio(cInicio), meio(cFrequencia), cDia, cPagamento, cCartao, cConta, opcoes, obs.no,
            nota('As contas são geradas automaticamente ao abrir cada competência; nada é pago no cadastro.', 'info')],
        foco: c.nome,
        preenchidos: () => [inicio.value !== dataPadrao && 'Data inicial', frequencia.value !== 'mensal' && 'Frequência', pagamento.value && 'Pagamento da conta',
            inativa.checked && 'Cadastrar inativa'].filter(Boolean),
        validar() {
            const erros = c.erros();
            if (!inicio.value) erros.push([cInicio, 'Informe a data do primeiro vencimento.']);
            if (semanal() && dia.value === '') erros.push([cDia, 'Selecione o dia da semana.']);
            if (pagamento.value === 'cartao' && !cartao.value) erros.push([cCartao, 'Selecione o cartão.']);
            if (pagamento.value === 'debito_automatico' && !conta.value) erros.push([cConta, 'Selecione a conta do débito automático.']);
            return erros;
        },
        async salvar() {
            // O corpo do formulario de Recorrencias (salvarRecorrenciaSimples): o servico grava semanal_N_D a partir dele.
            const corpo = { nome: c.nome.value.trim(), descricao: obs.area.value.trim(), valor: numero(c.valor), categoria_id: Number(c.categoria.value),
                data_vencimento: inicio.value, tipo_recorrencia: frequencia.value === 'quinzenal' ? 'semanal' : frequencia.value,
                frequencia_semanas: frequencia.value === 'quinzenal' ? 2 : 1, dia_semana: semanal() ? dia.value : null,
                meio_pagamento: pagamento.value || null, cartao_id: pagamento.value === 'cartao' ? cartao.value : null,
                conta_bancaria_id: pagamento.value === 'debito_automatico' ? conta.value : null, ativo: !inativa.checked };
            avisoDaRecorrencia = '';
            const r = await api('POST', '/api/recorrencias', corpo, responderRecorrencias);
            if (!r || !r.success) {
                return { erro: (r && r.error) || FALHA, pares: [[/dia da semana/i, cDia], [/cart[aã]o/i, cCartao], [/conta banc/i, cConta],
                    [/primeiro vencimento|data/i, cInicio], [/categoria/i, c.cCategoria], [/valor/i, c.cValor], [/nome/i, c.cNome]] };
            }
            return { titulo: `Recorrência “${corpo.nome}” cadastrada${corpo.ativo ? '' : ' (inativa)'}`,
                linhas: [avisoDaRecorrencia || 'Recorrência criada. As contas são geradas automaticamente ao abrir a competência em Despesas.'],
                destino: { modulo: 'recorrencias', rotulo: 'Ver em Recorrências' }, registro: { tipo: TIPOS.DESPESA_RECORRENTE, corpo } };
        },
    };
}

// ---------------------------------------------------------------------------------------------------------------
// 4. Consorcio: contrato com cronograma proprio (servico de consorcios), nunca uma recorrencia comum.

// A conta que a tela de Recorrencias ja mostra (calcularValorPremioConsorcio); o valor gravado e o que o banco calcula.
function premioEstimado({ valor, parcelas, inicio, contemplacao, tipo, reajuste }) {
    if (!(valor > 0) || !(parcelas >= 1) || !/^\d{4}-\d{2}$/.test(inicio) || !/^\d{4}-\d{2}$/.test(contemplacao)) return null;
    const [ai, mi] = inicio.split('-').map(Number);
    const [ac, mc] = contemplacao.split('-').map(Number);
    const posicao = (ac - ai) * 12 + (mc - mi) + 1;
    if (posicao < 1 || posicao > parcelas) return null;
    const passos = posicao - 1;
    let parcela = valor;
    if (tipo === 'fixo' && reajuste > 0) parcela = valor + passos * reajuste;
    if (tipo === 'percentual' && reajuste > 0) parcela = valor * (1 + (passos * reajuste) / 100);
    return Math.round((parcela * parcelas + Number.EPSILON) * 100) / 100;
}

function consorcio(ctx) {
    const { comum, categorias } = ctx;
    const c = camposComuns(comum, categorias, { rotuloNome: 'Nome do consórcio', exemplo: 'Ex.: Consórcio do carro', rotuloValor: 'Valor da parcela' });
    const mesAtual = mesAtualBrasilia();
    const parcelas = entrada('number', '', { min: '1', step: '1', inputmode: 'numeric', placeholder: 'Ex.: 60' });
    parcelas.id = 'cad-numero-parcelas';
    const inicio = entrada('month', mesAtual);
    inicio.id = 'cad-mes-inicio';
    const reajuste = seletor([['nenhum', 'Sem reajuste'], ['percentual', 'Percentual (%)'], ['fixo', 'Valor fixo (R$)']], 'nenhum');
    reajuste.id = 'cad-tipo-reajuste';
    const valorReajuste = entrada('number', '', { step: '0.01', min: '0', inputmode: 'decimal', placeholder: '0' });
    valorReajuste.id = 'cad-valor-reajuste';
    const contemplacao = entrada('month', '');
    contemplacao.id = 'cad-mes-contemplacao';
    const premio = el('output', 'cad-calculado', 'Calculado automaticamente');
    premio.id = 'cad-valor-premio';
    const anteriores = entrada('number', '', { min: '0', step: '1', inputmode: 'numeric', placeholder: '0' });
    anteriores.id = 'cad-parcelas-anteriores';

    const cParcelas = campoComErro('Número de parcelas', parcelas, { obrigatorio: true });
    const cInicio = campoComErro('Mês de início', inicio, { obrigatorio: true, ajuda: 'Mês da 1ª parcela do contrato' });
    const cReajuste = campoComErro('Tipo de reajuste', reajuste);
    const cValorReajuste = campoComErro('Valor do reajuste', valorReajuste, { obrigatorio: true });
    const cContemplacao = campoComErro('Mês de contemplação', contemplacao, { ajuda: 'Opcional: quando receberá o prêmio' });
    const cPremio = campoComErro('Valor do prêmio (calculado)', premio);
    const cAnteriores = inteiro(campoComErro('Parcelas já pagas antes do cadastro', anteriores, {
        ajuda: 'Contrato em andamento: as primeiras parcelas ficam no histórico como pagas, sem débito bancário.' }));
    const obs = campoObservacoes(comum);

    function ajustar() {
        cValorReajuste.hidden = reajuste.value === 'nenhum';
        cValorReajuste.firstChild.firstChild.textContent = reajuste.value === 'percentual' ? 'Reajuste por parcela (%)' : 'Reajuste por parcela (R$)';
        // So para contrato em andamento (inicio anterior ao mes corrente), como a regra do banco exige.
        const emAndamento = /^\d{4}-\d{2}$/.test(inicio.value) && inicio.value < mesAtual;
        cAnteriores.hidden = !emAndamento;
        if (!emAndamento) anteriores.value = '';
        const p = premioEstimado({ valor: numero(c.valor), parcelas: Number(parcelas.value), inicio: inicio.value, contemplacao: contemplacao.value,
            tipo: reajuste.value, reajuste: Number(valorReajuste.value) });
        premio.textContent = p === null ? 'Calculado automaticamente' : moeda(p);
        premio.classList.toggle('vazio', p === null);
    }
    for (const controle of [c.valor, parcelas, inicio, reajuste, valorReajuste, contemplacao]) {
        controle.addEventListener('input', ajustar);
        controle.addEventListener('change', ajustar);
    }
    ajustar();

    return {
        nos: [inteiro(c.cNome), c.cCategoria, c.cValor, meio(cParcelas), meio(cInicio), cReajuste, cValorReajuste, cContemplacao, cPremio, cAnteriores, obs.no,
            nota('O contrato gera o cronograma de parcelas pendentes; o pagamento de cada parcela é feito depois.', 'info')],
        foco: c.nome,
        preenchidos: () => [parcelas.value && 'Número de parcelas', inicio.value !== mesAtual && 'Mês de início', reajuste.value !== 'nenhum' && 'Tipo de reajuste',
            contemplacao.value && 'Mês de contemplação', anteriores.value && 'Parcelas já pagas'].filter(Boolean),
        validar() {
            const erros = c.erros();
            const n = Number(parcelas.value);
            if (!(Number.isInteger(n) && n >= 1)) erros.push([cParcelas, 'Informe o número de parcelas.']);
            if (!/^\d{4}-\d{2}$/.test(inicio.value)) erros.push([cInicio, 'Informe o mês de início.']);
            if (reajuste.value !== 'nenhum' && !(Number(valorReajuste.value) > 0)) erros.push([cValorReajuste, 'Informe o valor do reajuste.']);
            if (contemplacao.value && /^\d{4}-\d{2}$/.test(inicio.value) && n >= 1) {
                const fim = deslocarMes(inicio.value, n - 1);
                if (contemplacao.value < inicio.value || contemplacao.value > fim) erros.push([cContemplacao, 'A contemplação deve estar dentro do período do consórcio.']);
            }
            const pagas = anteriores.value === '' ? 0 : Number(anteriores.value);
            if (!cAnteriores.hidden && !(Number.isInteger(pagas) && pagas >= 0 && (pagas === 0 || pagas < n))) {
                erros.push([cAnteriores, 'Informe um número inteiro menor que o total de parcelas.']);
            }
            return erros;
        },
        async salvar() {
            // O corpo do cadastro de consorcio (salvarConsorcio), sem meio de pagamento: as parcelas nascem como contas a pagar.
            const corpo = { nome: c.nome.value.trim(), valor_inicial: numero(c.valor), categoria_id: Number(c.categoria.value),
                numero_parcelas: Number(parcelas.value), data_inicial: `${inicio.value}-01`, mes_inicio: `${inicio.value}-01`,
                tipo_reajuste: reajuste.value, valor_reajuste: reajuste.value === 'nenhum' ? 0 : Number(valorReajuste.value),
                mes_contemplacao: contemplacao.value ? `${contemplacao.value}-01` : null, observacoes: obs.area.value.trim() };
            const pagas = Number(anteriores.value);
            if (!cAnteriores.hidden && pagas > 0) corpo.parcelas_pagas_anteriores = pagas;
            const r = await api('POST', '/api/consorcios', corpo, responderRecorrencias);
            if (!r || !r.success) {
                return { erro: (r && r.error) || FALHA, pares: [[/parcelas ja pagas|parcelas já pagas/i, cAnteriores], [/contempla/i, cContemplacao],
                    [/in[ií]cio/i, cInicio], [/parcelas/i, cParcelas], [/categoria/i, c.cCategoria], [/valor/i, c.cValor], [/nome|consorcio|consórcio/i, c.cNome]] };
            }
            const linhas = [`${r.parcelas_geradas ?? corpo.numero_parcelas} parcelas geradas a partir de ${mesAno(corpo.mes_inicio)}.`];
            const historico = r.parcelas_anteriores;
            if (corpo.parcelas_pagas_anteriores) {
                linhas.push(`${(historico && (historico.quantidade ?? historico.registradas)) ?? corpo.parcelas_pagas_anteriores} parcela(s) anteriores registradas como pagas no histórico, sem débito bancário.`);
            }
            if (r.data && r.data.valor_premio) linhas.push(`Prêmio previsto na contemplação: ${moeda(r.data.valor_premio)}.`);
            return { titulo: `Consórcio “${corpo.nome}” cadastrado`, linhas,
                destino: { modulo: 'recorrencias', rotulo: 'Ver em Recorrências' }, registro: { tipo: TIPOS.CONSORCIO, corpo } };
        },
    };
}

const MONTADORES = { DESPESA_DIRETA: despesaDireta, COMPRA_CARTAO: compraCartao, DESPESA_RECORRENTE: despesaRecorrente, CONSORCIO: consorcio };

// ---------------------------------------------------------------------------------------------------------------
// O modal

let aberto = null;  // um cadastro por vez

// opcoes:
//   origem         'despesas' | 'lancamentos' | 'recorrencias' (so identifica quem abriu: volta-se sempre a ela)
//   mes            competencia aberta na origem (AAAA-MM); padrao: mes atual
//   tipoInicial    um de TIPOS; tipos: lista dos tipos oferecidos (padrao: os quatro)
//   dados          pre-preenchimento: nome, valor, categoria_id, observacoes, data, cartao_id, meio_pagamento, frequencia
//   destinos       { despesas(mes), cartoes(mes, cartaoId), recorrencias() } -> endereco do registro no modulo (opcional)
//   aoSalvar(registro)  depois de cada gravacao confirmada (a tela atualiza a lista); aoFechar() ao sair
// O perfil e o dos servicos (prepararCadastro). Devolve uma Promise que termina quando o modal fecha.
export function abrirCadastroDespesa(opcoes = {}) {
    if (aberto) return aberto;
    const mes = /^\d{4}-\d{2}$/.test(opcoes.mes || '') ? opcoes.mes : mesAtualBrasilia();
    const tipos = (opcoes.tipos || Object.keys(TIPOS)).filter((t) => MONTADORES[t]);
    const dados = opcoes.dados || {};
    const comum = { nome: dados.nome || '', valor: dados.valor ? String(dados.valor) : '', categoria: dados.categoria_id ? String(dados.categoria_id) : '',
        observacoes: dados.observacoes || '' };
    let tipoAtual = tipos.includes(opcoes.tipoInicial) ? opcoes.tipoInicial : tipos[0];
    let secao = null;
    let enviando = false;
    let categorias = [];
    let salvou = false;

    const fundo = el('div', 'cad-fundo');
    fundo.id = 'cad-fundo';
    const modal = el('section', 'cad-modal');
    modal.id = 'cad-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'cad-titulo');
    modal.dataset.origem = opcoes.origem || '';
    const titulo = el('h2', 'cad-titulo', 'Nova despesa');
    titulo.id = 'cad-titulo';
    const fechar = botao('×', 'cad-fechar');
    fechar.id = 'cad-fechar';
    fechar.setAttribute('aria-label', 'Fechar');
    const cabecalho = el('header', 'cad-cabecalho');
    cabecalho.append(titulo, fechar);

    const form = el('form', 'cad-form');
    form.noValidate = true;
    const corpo = el('div', 'cad-corpo');
    const seletorTipo = seletor(tipos.map((t) => [t, ROTULOS[t]]), tipoAtual);
    seletorTipo.id = 'cad-tipo';
    const cTipo = inteiro(campoComErro('Tipo de operação', seletorTipo, { obrigatorio: true }));
    const troca = inteiro(el('div', 'cad-troca'));
    troca.id = 'cad-troca';
    troca.hidden = true;
    troca.setAttribute('role', 'alertdialog');
    const grade = el('div', 'cad-grade');
    grade.id = 'cad-campos';
    const m = mensagem();
    m.id = 'cad-mensagem';
    corpo.append(cTipo, troca, grade, m);
    const cancelar = botao('Cancelar', 'cad-botao');
    cancelar.id = 'cad-cancelar';
    const salvar = botao('Salvar', 'cad-botao primario');
    salvar.type = 'submit';
    salvar.id = 'cad-salvar';
    const rodape = el('footer', 'cad-rodape');
    rodape.append(cancelar, salvar);
    form.append(corpo, rodape);
    modal.append(cabecalho, form);
    fundo.append(modal);

    // Teclado virtual: a altura util acompanha a area visivel (o rodape nao fica sob o teclado).
    const viewport = window.visualViewport;
    const medir = () => fundo.style.setProperty('--cad-altura', `${Math.round(viewport.height)}px`);
    if (viewport) {
        viewport.addEventListener('resize', medir);
        medir();
    }

    let terminar;
    const fim = new Promise((resolver) => { terminar = resolver; });
    function encerrar() {
        if (enviando) return;
        document.removeEventListener('keydown', tecla, true);
        if (viewport) viewport.removeEventListener('resize', medir);
        fundo.remove();
        document.documentElement.classList.remove('cad-aberto');
        aberto = null;
        if (opcoes.aoFechar) opcoes.aoFechar({ salvou });
        terminar({ salvou });
    }
    function tecla(evento) {
        if (evento.key === 'Escape') { evento.stopPropagation(); encerrar(); }
    }

    function montar(tipo) {
        tipoAtual = tipo;
        seletorTipo.value = tipo;
        modal.dataset.tipo = tipo;
        mostrarMensagem(m, '');
        troca.hidden = true;
        secao = MONTADORES[tipo]({ comum, categorias, mes, dados, aguardando: () => { enviando = false; mostrarMensagem(m, ''); } });
        grade.replaceChildren(...secao.nos);
        if (secao.aoMontar) secao.aoMontar();
        corpo.scrollTop = 0;
    }

    // Troca de tipo: nome, valor, categoria e observacoes seguem; o que so existe no tipo atual e descartado, com
    // confirmacao quando ja havia algo preenchido.
    seletorTipo.addEventListener('change', () => {
        const novo = seletorTipo.value;
        const perdidos = secao ? secao.preenchidos() : [];
        if (!perdidos.length) { montar(novo); return; }
        seletorTipo.value = tipoAtual;
        const manter = botao('Manter', 'cad-botao');
        manter.id = 'cad-troca-manter';
        const trocar = botao(`Trocar para ${ROTULOS[novo]}`, 'cad-botao primario');
        trocar.id = 'cad-troca-confirmar';
        const acoes = el('div', 'cad-troca-acoes');
        acoes.append(manter, trocar);
        troca.replaceChildren(el('p', null, `Trocar para “${ROTULOS[novo]}” descarta o que só existe em “${ROTULOS[tipoAtual]}”: ${perdidos.join(', ')}. `
            + 'Nome, valor, categoria e observações são mantidos.'), acoes);
        troca.hidden = false;
        manter.addEventListener('click', () => { troca.hidden = true; seletorTipo.focus(); });
        trocar.addEventListener('click', () => { montar(novo); seletorTipo.focus(); });
        trocar.focus();
    });

    function confirmar(resultado) {
        salvou = true;
        modal.classList.add('cad-concluido');
        titulo.textContent = 'Cadastro concluído';
        const caixa = el('div', 'cad-confirmacao');
        caixa.id = 'cad-confirmacao';
        caixa.setAttribute('role', 'status');
        caixa.append(el('p', 'cad-confirmacao-titulo', resultado.titulo), ...resultado.linhas.map((t) => el('p', 'cad-confirmacao-linha', t)));
        corpo.replaceChildren(caixa);
        const novo = botao('Novo cadastro', 'cad-botao');
        novo.id = 'cad-novo';
        const concluir = botao('Concluir', 'cad-botao primario');
        concluir.id = 'cad-concluir';
        const nos = [novo];
        const destino = resultado.destino;
        const endereco = destino && opcoes.destinos && opcoes.destinos[destino.modulo] && opcoes.destinos[destino.modulo](destino.mes, destino.cartaoId);
        if (endereco) {
            const ver = el('a', 'cad-botao', destino.rotulo);
            ver.id = 'cad-ver-registro';
            ver.href = endereco;
            nos.push(ver);
        }
        nos.push(concluir);
        rodape.replaceChildren(...nos);
        novo.addEventListener('click', () => {
            // Novo cadastro do mesmo tipo, em branco (o registro anterior ja esta confirmado pelo servidor).
            Object.assign(comum, { nome: '', valor: '', categoria: '', observacoes: '' });
            salvar.disabled = false;
            modal.classList.remove('cad-concluido');
            titulo.textContent = 'Nova despesa';
            corpo.replaceChildren(cTipo, troca, grade, m);
            rodape.replaceChildren(cancelar, salvar);
            montar(tipoAtual);
            if (secao.foco) secao.foco.focus();
        });
        concluir.addEventListener('click', encerrar);
        concluir.focus();
        if (opcoes.aoSalvar) opcoes.aoSalvar(resultado.registro);
    }

    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (enviando || !secao || !troca.hidden || modal.classList.contains('cad-concluido')) return;
        for (const campo of grade.querySelectorAll('.mob-campo')) if (campo.erro) campo.erro('');
        mostrarMensagem(m, '');
        if (mostrarErros(secao.validar())) return;
        enviando = true;
        salvar.disabled = true;
        cancelar.disabled = true;
        mostrarMensagem(m, 'Salvando...');
        let resultado;
        try {
            resultado = await secao.salvar();
        } catch (erro) {
            console.error('Cadastro de despesa:', erro);
            resultado = { erro: FALHA, pares: [] };
        }
        enviando = false;
        cancelar.disabled = false;
        if (resultado.erro) {
            salvar.disabled = false;
            erroDoServico(m, resultado.erro, resultado.pares || []);
            return;
        }
        confirmar(resultado);
    });
    // Editar depois de um erro apaga o aviso do rodape (o do campo some pelo proprio campo).
    form.addEventListener('input', () => { if (m.classList.contains('erro')) mostrarMensagem(m, ''); });
    cancelar.addEventListener('click', encerrar);
    fechar.addEventListener('click', encerrar);
    document.addEventListener('keydown', tecla, true);

    document.body.append(fundo);
    document.documentElement.classList.add('cad-aberto');
    aberto = fim;

    // Carregamento inicial: permissao e categorias (o perfil somente leitura nao recebe o formulario).
    grade.replaceChildren(nota('Carregando...', 'carregando'));
    salvar.disabled = true;
    seletorTipo.disabled = true;
    (async () => {
        const pode = await podeGerirPerfil().catch(() => false);
        if (!pode) {
            modal.classList.add('cad-leitura');
            cTipo.hidden = true;
            grade.replaceChildren(nota('Acesso somente de leitura a este perfil: não é possível cadastrar despesas.', 'leitura'));
            cancelar.textContent = 'Fechar';
            salvar.hidden = true;
            cancelar.focus();
            return;
        }
        const r = await api('GET', '/api/categorias');
        categorias = r && r.success ? (r.data || []) : [];
        seletorTipo.disabled = false;
        salvar.disabled = false;
        montar(tipoAtual);
        if (!r || !r.success) mostrarMensagem(m, (r && r.error) || 'Não foi possível carregar as categorias.', 'erro');
        if (secao.foco) secao.foco.focus();
    })();
    return fim;
}
