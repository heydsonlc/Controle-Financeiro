// FIN-MVP-MOBILE-09 — Recorrencias mobile. Consulta, cadastro, edicao, inativacao e reativacao das recorrencias do perfil
// pelo servico do desktop (js/recorrencias-servico.js, o mesmo da tela Recorrencias), sem regra nova:
//   - lista: recorrencias_do_perfil (ativas e inativas), separadas em contas a pagar e cartao de credito; resumo como os
//     indicadores do desktop (ativas, valor mensal estimado, proximo vencimento);
//   - cadastro e edicao: as validacoes e gravacoes do desktop (criar_despesa / editar_recorrencia; no cartao,
//     criar_recorrencia_cartao / editar_recorrencia_cartao), mensal, anual, semanal e a cada 2 semanas (estas fora do
//     cartao, como no desktop); trocar entre cartao e outro meio continua recusado (inativar e cadastrar de novo);
//   - inativar: a previa do desktop (P22, previa_interrupcao_recorrencia) e so entao interromper_recorrencia, com a versao e
//     a quantidade conferidas no banco; as ocorrencias pagas, com movimento, vencidas ou de cobranca real ficam;
//   - reativar: a previa da retomada (periodo inativo e restauracao opcional) e retomar_recorrencia.
// As contas e compras continuam geradas ao abrir a competencia em Despesas (nada e gerado aqui). Consorcios continuam no
// desktop. Quem so le o perfil consulta, sem acoes; o banco recusa de qualquer forma. Sem innerHTML (CSP).

import { hojeBrasilia } from './adaptador-comum.js';
import { centavos, dataCurta, el, reais } from './comum.js';
import { campoComErro, erroDoServico, mesAno, mostrarErros, par } from './mobile-formulario.js';
import {
    FALHA_GERAL, SETA, abrirFolha, botao, detalhes, entrada, fecharFolha, icone, limparAoEditar, mensagem, mostrarAviso,
    mostrarMensagem, prepararFolha, seletor, texto,
} from './mobile-ui.js';
import { ajustarCadastrosPelaPermissao, prepararMais, prepararModulos } from './mobile-comum.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { lerValor, valorParaCampo } from './receita-formulario.js';
import {
    atualizarRecorrencia, cartoesDaRecorrencia, categoriasDaRecorrencia, configurarRecorrencias, contasDaRecorrencia,
    criarRecorrencia, frequencia, interromperRecorrencia, podeGerirRecorrencias, previaInterrupcao, previaRetomada,
    recorrenciasDoPerfil, resolverCategoriaCartao, retomarRecorrencia,
} from './recorrencias-servico.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);

const estado = {
    itens: [],
    situacao: 'ativas',  // ativas | inativas | todas
    busca: '',
    fechados: {},
    somenteLeitura: true,
    apoio: null,  // categorias, cartoes e contas bancarias ativas (formulario)
    ultimoAviso: '',  // mensagem da ultima operacao do servico (a mesma que o desktop mostra)
};

// ---------------------------------------------------------------------------------------------------------------
// Textos (os do desktop: formatarFrequencia, meios do formulario, dia da semana)

const DIAS = ['Domingo', 'Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado'];
const FREQUENCIAS = [['mensal', 'Mensal'], ['semanal', 'Semanal'], ['quinzenal', 'A cada 2 semanas'], ['anual', 'Anual']];
const MEIOS = [['', 'Não especificado'], ['boleto', 'Boleto'], ['debito', 'Débito'], ['debito_automatico', 'Débito automático'],
    ['pix', 'PIX'], ['cartao', 'Cartão de crédito']];
const NOME_MEIO = Object.fromEntries(MEIOS.filter(([k]) => k));
const ehCartao = (r) => r.meio_pagamento === 'cartao';

function textoFrequencia(r) {
    const nome = (FREQUENCIAS.find(([k]) => k === r.frequencia) || [null, r.frequencia || 'Mensal'])[1];
    if (r.frequencia === 'semanal' || r.frequencia === 'quinzenal') {
        return r.dia_semana === null || r.dia_semana === undefined ? nome : `${nome} (${DIAS[r.dia_semana].toLowerCase()})`;
    }
    if (r.frequencia === 'anual' && r.data_vencimento) return `${nome} (${r.data_vencimento.slice(8, 10)}/${r.data_vencimento.slice(5, 7)})`;
    if (r.data_vencimento) return `${nome}, dia ${Number(r.data_vencimento.slice(8, 10))}`;
    return nome;
}

function textoMeio(r) {
    if (ehCartao(r)) return r.cartao_nome || 'Cartão de crédito';
    if (r.meio_pagamento === 'debito_automatico') return r.conta_bancaria_nome ? `Débito automático (${r.conta_bancaria_nome})` : 'Débito automático';
    return NOME_MEIO[r.meio_pagamento] || '';
}

// Valor mensal estimado e proximo vencimento: as regras dos indicadores do desktop (valorMensalEstimado, obterEventosAgenda).
function mensalEstimado(r) {
    const valor = centavos(r.valor);
    if (r.frequencia === 'semanal') return valor * 4;
    if (r.frequencia === 'quinzenal') return valor * 2;
    if (r.frequencia === 'anual') return Math.round(valor / 12);
    return valor;
}

// ---------------------------------------------------------------------------------------------------------------
// Lista

async function carregar() {
    const lista = $('mob-lista');
    lista.setAttribute('aria-busy', 'true');
    try {
        const linhas = await recorrenciasDoPerfil();
        estado.itens = linhas.map((r) => ({ ...r, ...frequencia(r.tipo_recorrencia), valor: Number(r.valor || 0) }));
    } catch (erro) {
        console.error('Recorrencias:', erro);
        estado.itens = [];
        mostrarAviso('Não foi possível carregar as recorrências.', 'erro');
    }
    desenhar();
    lista.setAttribute('aria-busy', 'false');
}

const normalizar = (t) => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

function filtrados() {
    const busca = normalizar(estado.busca.trim());
    return estado.itens.filter((r) => {
        if (estado.situacao === 'ativas' && !r.ativo) return false;
        if (estado.situacao === 'inativas' && r.ativo) return false;
        if (busca && !normalizar(`${r.nome} ${r.descricao || ''} ${r.categoria_nome || ''} ${r.cartao_nome || ''}`).includes(busca)) return false;
        return true;
    });
}

function linhaRecorrencia(r) {
    const linha = el('button', `mob-linha${r.ativo ? '' : ' inativa'}`);
    linha.type = 'button';
    linha.dataset.id = String(r.id);
    const t = el('span', 'mob-linha-texto');
    const sub = [r.ativo ? '' : 'Inativa', textoFrequencia(r)];
    if (r.ativo && r.proximo_vencimento) sub.push(`próx. ${dataCurta(r.proximo_vencimento)}`);
    sub.push(textoMeio(r));
    t.append(el('span', 'mob-linha-nome', r.nome), el('span', 'mob-linha-data', sub.filter(Boolean).join(' · ')));
    const valor = reais(centavos(r.valor));
    linha.append(t, el('span', 'mob-linha-valor', valor), icone(SETA, 'mob-seta'));
    linha.setAttribute('aria-label', `${r.nome}, ${valor}${r.ativo ? '' : ', inativa'}. Ver detalhes`);
    linha.addEventListener('click', () => abrirDetalhes(r.id));
    return linha;
}

function grupoEl(chave, rotulo, itens) {
    const secao = el('section', 'mob-grupo');
    secao.dataset.grupo = chave;
    const aberto = !estado.fechados[chave];
    const cabecalho = el('button', 'mob-grupo-cabecalho');
    cabecalho.type = 'button';
    cabecalho.setAttribute('aria-expanded', aberto ? 'true' : 'false');
    cabecalho.setAttribute('aria-controls', `mob-grupo-${chave}`);
    cabecalho.append(el('span', 'mob-grupo-nome', rotulo), el('span', 'mob-grupo-qtd', String(itens.length)), icone(SETA, 'mob-seta'));
    const corpo = el('div', 'mob-grupo-itens');
    corpo.id = `mob-grupo-${chave}`;
    corpo.hidden = !aberto;
    corpo.append(...itens.map(linhaRecorrencia));
    cabecalho.addEventListener('click', () => {
        const abrir = corpo.hidden;
        corpo.hidden = !abrir;
        cabecalho.setAttribute('aria-expanded', abrir ? 'true' : 'false');
        estado.fechados[chave] = !abrir;
    });
    secao.append(cabecalho, corpo);
    return secao;
}

const porNome = (a, b) => a.nome.localeCompare(b.nome, 'pt-BR') || a.id - b.id;

function desenhar() {
    const itens = filtrados();
    const contas = itens.filter((r) => !ehCartao(r)).sort(porNome);
    const cartao = itens.filter(ehCartao).sort(porNome);
    const grupos = [];
    if (contas.length) grupos.push(grupoEl('contas', 'CONTAS A PAGAR', contas));
    if (cartao.length) grupos.push(grupoEl('cartao', 'CARTÃO DE CRÉDITO', cartao));
    const lista = $('mob-lista');
    lista.replaceChildren(...grupos);
    if (!grupos.length) {
        const vazio = estado.itens.length ? 'Nenhuma recorrência com estes filtros.' : 'Nenhuma recorrência cadastrada.';
        lista.append(el('p', 'mob-vazio', vazio));
    }
    document.querySelectorAll('#mob-situacao button').forEach((b) => b.setAttribute('aria-pressed', b.dataset.situacao === estado.situacao ? 'true' : 'false'));
    desenharResumo();
}

function desenharResumo() {
    const ativas = estado.itens.filter((r) => r.ativo);
    const hoje = hojeBrasilia();
    const proxima = ativas.filter((r) => r.proximo_vencimento && r.proximo_vencimento >= hoje)
        .sort((a, b) => a.proximo_vencimento.localeCompare(b.proximo_vencimento))[0];
    $('mob-qtd-ativas').textContent = `${ativas.length} de ${estado.itens.length}`;
    $('mob-mensal').textContent = reais(ativas.reduce((s, r) => s + mensalEstimado(r), 0));
    $('mob-proximo').textContent = proxima ? dataCurta(proxima.proximo_vencimento).slice(0, 5) : '—';
    $('mob-proximo').title = proxima ? `${proxima.nome} em ${dataCurta(proxima.proximo_vencimento)}` : '';
    $('mob-resumo').hidden = false;
    $('mob-somente-leitura').hidden = !estado.somenteLeitura;
}

// ---------------------------------------------------------------------------------------------------------------
// Resultado de uma operacao: fecha o painel, mostra a mensagem do servico (a mesma do desktop) e rele a lista.

async function concluir(padrao) {
    const conteudo = estado.ultimoAviso || padrao;
    estado.ultimoAviso = '';
    fecharFolha();
    await carregar();
    mostrarAviso(conteudo, 'ok');
}

// ---------------------------------------------------------------------------------------------------------------
// Detalhes

function abrirDetalhes(id) {
    const r = estado.itens.find((x) => x.id === id);
    if (!r) return;
    const semanal = r.frequencia === 'semanal' || r.frequencia === 'quinzenal';
    const pares = [
        ['Situação', r.ativo ? 'Ativa' : 'Inativa'],
        ['Valor', reais(centavos(r.valor))],
        ['Frequência', (FREQUENCIAS.find(([k]) => k === r.frequencia) || [null, r.frequencia])[1]],
        ['Dia da semana', semanal && r.dia_semana !== null ? DIAS[r.dia_semana] : ''],
        ['Data inicial', r.data_vencimento ? dataCurta(r.data_vencimento) : ''],
        ['Próximo vencimento', r.ativo && r.proximo_vencimento ? dataCurta(r.proximo_vencimento) : ''],
        ['Categoria', r.categoria_nome || ''],
        ['Meio de pagamento', NOME_MEIO[r.meio_pagamento] || 'Não especificado'],
        [ehCartao(r) ? 'Cartão' : 'Conta bancária', ehCartao(r) ? (r.cartao_nome || '') : (r.conta_bancaria_nome || '')],
        ['Observações', r.descricao || ''],
    ];
    const conteudo = [detalhes(pares)];
    conteudo.push(texto(ehCartao(r)
        ? 'As compras entram na fatura do cartão quando a competência é aberta em Despesas.'
        : 'As contas são geradas automaticamente ao abrir a competência em Despesas.', 'discreto'));
    const acoes = el('div', 'mob-acoes mob-rec-acoes');
    const ver = el('a', 'mob-botao', ehCartao(r) ? 'Ver em Cartões' : 'Ver na Lista de Despesas');
    ver.href = ehCartao(r) ? 'cartoes-mobile.html' : 'despesas-mobile.html';
    acoes.append(ver);
    const gerenciavel = r.gerenciavel || ehCartao(r);
    if (estado.somenteLeitura) {
        conteudo.push(texto('Acesso somente de leitura a este perfil.', 'discreto'));
    } else if (!gerenciavel) {
        conteudo.push(texto('Recorrência de outro módulo: altere no módulo de origem.', 'discreto'));
    } else {
        const editar = botao('Editar');
        editar.id = 'mob-rec-editar';
        editar.addEventListener('click', () => abrirFormulario(r));
        acoes.append(editar);
        if (r.ativo) {
            const inativar = botao('Inativar', 'perigo');
            inativar.id = 'mob-rec-inativar';
            inativar.addEventListener('click', () => abrirInterrupcao(r));
            acoes.append(inativar);
        } else {
            const futuras = botao('Cancelar ocorrências futuras');
            futuras.id = 'mob-rec-cancelar-futuras';
            futuras.addEventListener('click', () => abrirInterrupcao(r));
            const reativar = botao('Reativar', 'primario');
            reativar.id = 'mob-rec-reativar';
            reativar.addEventListener('click', () => abrirRetomada(r));
            acoes.append(futuras, reativar);
        }
    }
    conteudo.push(acoes);
    abrirFolha(r.nome, ...conteudo);
}

// ---------------------------------------------------------------------------------------------------------------
// Cadastro e edicao (os campos do formulario do desktop, sem "Tipo": consorcios continuam no desktop)

async function apoio() {
    if (!estado.apoio) {
        const [categorias, cartoes, contas] = await Promise.all([categoriasDaRecorrencia(), cartoesDaRecorrencia(), contasDaRecorrencia()]);
        const lista = (r) => (r.corpo && r.corpo.success ? r.corpo.data || [] : []);
        estado.apoio = { categorias: lista(categorias), cartoes: lista(cartoes), contas: lista(contas) };
    }
    return estado.apoio;
}

async function abrirFormulario(r = null) {
    const { categorias, cartoes, contas } = await apoio();
    const editando = Boolean(r);
    const form = el('form', 'mob-form mob-rec-form');
    form.noValidate = true;
    const nome = entrada('text', r ? r.nome : '', { maxlength: '200', autocomplete: 'off', placeholder: 'Ex.: Aluguel, Diarista, Streaming' });
    const valor = entrada('text', r ? valorParaCampo(r.valor) : '', { inputmode: 'decimal', placeholder: '0,00' });
    const categoria = seletor([['', 'Selecione...'], ...categorias.map((c) => [c.id, c.nome])], r ? r.categoria_id : '');
    const inicio = entrada('date', r ? r.data_vencimento || '' : hojeBrasilia());
    const freq = seletor(FREQUENCIAS, r ? r.frequencia : 'mensal');
    const dia = seletor([['', 'Selecione...'], ...DIAS.map((d, i) => [i, d])], r && r.dia_semana !== null ? r.dia_semana : '');
    const meio = seletor(MEIOS, r ? r.meio_pagamento || '' : '');
    const cartao = seletor([['', 'Selecione...'], ...cartoes.map((c) => [c.id, c.nome])], r ? r.cartao_id || '' : '');
    const conta = seletor([['', 'Selecione...'], ...contas.map((c) => [c.id, c.instituicao ? `${c.nome} (${c.instituicao})` : c.nome])],
        r ? r.conta_bancaria_id || '' : '');
    const obs = el('textarea');
    obs.rows = 2;
    obs.value = r ? r.descricao || '' : '';

    const cNome = campoComErro('Nome', nome, { obrigatorio: true });
    const cValor = campoComErro('Valor', valor, { obrigatorio: true });
    const cCategoria = campoComErro('Categoria', categoria, { obrigatorio: true });
    const cInicio = campoComErro('Data inicial', inicio, { obrigatorio: true, ajuda: 'Primeiro vencimento: sem ela a recorrência não gera contas.' });
    const cFreq = campoComErro('Frequência', freq, { obrigatorio: true });
    const cDia = campoComErro('Dia da semana', dia, { obrigatorio: true });
    const cMeio = campoComErro('Meio de pagamento', meio);
    const cCartao = campoComErro('Cartão', cartao, { obrigatorio: true });
    const cConta = campoComErro('Conta bancária', conta, { obrigatorio: true });
    const ajudaMeio = el('span', 'mob-ajuda');
    cMeio.insertBefore(ajudaMeio, cMeio.lastChild);
    const ajudaCartao = el('span', 'mob-ajuda', 'Categoria do cartão: resolvida pela categoria da despesa.');
    cCartao.insertBefore(ajudaCartao, cCartao.lastChild);
    const linhaDia = par(cDia);
    linhaDia.classList.add('um');

    // Troca entre cartao e outro meio: como o desktop, recusada na edicao (inativar e cadastrar de novo).
    if (editando && ehCartao(r)) {
        meio.disabled = true;
        ajudaMeio.textContent = 'Para trocar o cartão por outro meio, inative esta recorrência e cadastre outra: as compras já geradas ficam no cartão.';
    } else if (editando) {
        meio.querySelector('option[value="cartao"]').disabled = true;
        ajudaMeio.textContent = 'Para passar ao cartão, inative esta recorrência e cadastre uma nova no cartão.';
    }
    ajudaMeio.hidden = !ajudaMeio.textContent;

    async function resolverCategoria() {
        if (meio.value !== 'cartao' || !cartao.value || !categoria.value) {
            ajudaCartao.textContent = 'Categoria do cartão: resolvida pela categoria da despesa.';
            return;
        }
        const resposta = await resolverCategoriaCartao(new URLSearchParams({ cartao_id: cartao.value, categoria_id: categoria.value }));
        const d = resposta.corpo && resposta.corpo.success ? resposta.corpo.data : null;
        const nomeCat = d && (d.categoria_cartao_nome || d.nome);
        ajudaCartao.textContent = nomeCat ? `Categoria do cartão: ${nomeCat}.` : 'Categoria do cartão: resolvida pela categoria da despesa.';
    }

    function ajustar() {
        const semanal = freq.value === 'semanal' || freq.value === 'quinzenal';
        linhaDia.hidden = !semanal;
        cCartao.hidden = meio.value !== 'cartao';
        cConta.hidden = meio.value !== 'debito_automatico';
        // Semanal e a cada 2 semanas nao valem no cartao (o desktop recusa com a mesma mensagem ao salvar).
        freq.querySelectorAll('option[value="semanal"], option[value="quinzenal"]').forEach((o) => { o.disabled = meio.value === 'cartao'; });
        resolverCategoria();
    }
    freq.addEventListener('change', ajustar);
    meio.addEventListener('change', ajustar);
    cartao.addEventListener('change', resolverCategoria);
    categoria.addEventListener('change', resolverCategoria);

    const m = mensagem();
    limparAoEditar(form, m);
    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', fecharFolha);
    const salvar = botao(editando ? 'Salvar alterações' : 'Cadastrar', 'primario');
    salvar.type = 'submit';
    salvar.id = 'mob-rec-salvar';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, salvar);
    const pValor = par(cValor, cCategoria);
    pValor.classList.add('empilha');
    const pInicio = par(cInicio, cFreq);
    pInicio.classList.add('empilha');
    form.append(cNome, pValor, pInicio, linhaDia, cMeio, cCartao, cConta, campoComErro('Observações', obs), m, acoes);
    ajustar();

    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        const semanal = freq.value === 'semanal' || freq.value === 'quinzenal';
        const erros = [];
        if (!nome.value.trim()) erros.push([cNome, 'Informe o nome.']);
        if (!(lerValor(valor.value) > 0)) erros.push([cValor, 'Informe um valor maior que zero.']);
        if (!categoria.value) erros.push([cCategoria, 'Selecione a categoria.']);
        if (!inicio.value) erros.push([cInicio, 'Informe a data do primeiro vencimento.']);
        if (semanal && dia.value === '') erros.push([cDia, 'Selecione o dia da semana.']);
        if (meio.value === 'cartao' && !cartao.value) erros.push([cCartao, 'Selecione o cartão.']);
        if (meio.value === 'debito_automatico' && !conta.value) erros.push([cConta, 'Selecione a conta do débito automático.']);
        if (mostrarErros(erros)) return;
        // O corpo do formulario do desktop (salvarRecorrenciaSimples), sem "ativo": a situacao muda por Inativar/Reativar.
        const corpo = {
            nome: nome.value.trim(),
            descricao: obs.value.trim(),
            valor: lerValor(valor.value),
            categoria_id: Number(categoria.value),
            data_vencimento: inicio.value,
            tipo_recorrencia: freq.value === 'quinzenal' ? 'semanal' : freq.value,
            frequencia_semanas: freq.value === 'quinzenal' ? 2 : 1,
            dia_semana: semanal ? dia.value : null,
            meio_pagamento: meio.value || null,
            cartao_id: meio.value === 'cartao' ? cartao.value : null,
            conta_bancaria_id: meio.value === 'debito_automatico' ? conta.value : null,
        };
        salvar.disabled = true;
        cancelar.disabled = true;
        mostrarMensagem(m, 'Salvando...');
        try {
            const resposta = editando ? await atualizarRecorrencia(r.id, corpo) : await criarRecorrencia(corpo);
            const c = resposta.corpo || {};
            if (!c.success) {
                erroDoServico(m, c.error || FALHA_GERAL, [[/dia da semana/i, cDia], [/cart[aã]o/i, cCartao], [/conta banc/i, cConta],
                    [/primeiro vencimento|data/i, cInicio], [/categoria/i, cCategoria], [/valor/i, cValor], [/nome/i, cNome]]);
                return;
            }
            await concluir(editando ? 'Recorrência atualizada.' : 'Recorrência criada.');
        } catch (erro) {
            console.error('Recorrencias:', erro);
            mostrarMensagem(m, FALHA_GERAL, 'erro');
        } finally {
            salvar.disabled = false;
            cancelar.disabled = false;
        }
    });
    abrirFolha(editando ? `Editar: ${r.nome}` : 'Nova recorrência', form);
}

// ---------------------------------------------------------------------------------------------------------------
// Inativar (P22): previa do que deixa de ser exigivel; a confirmacao leva a versao e a quantidade da previa.

function tabelaCompacta(linhas) {
    const lista = el('div', 'mob-rec-tabela');
    for (const valores of linhas) {
        const linha = el('div', 'mob-rec-tabela-linha');
        valores.forEach((v, i) => linha.append(el('span', i === valores.length - 1 ? 'direita' : '', v)));
        lista.append(linha);
    }
    return lista;
}

function abrirInterrupcao(r) {
    const corpo = el('div', 'mob-form mob-rec-previa');
    const m = mensagem();
    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', fecharFolha);
    const confirmar = botao(r.ativo ? 'Inativar' : 'Cancelar ocorrências', 'perigo');
    confirmar.id = 'mob-rec-confirmar';
    confirmar.disabled = true;
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, confirmar);
    let previa = null;

    function desenhar() {
        const p = previa;
        const itens = [detalhes([['Recorrência', p.nome], ['Data de efeito', `a partir de ${mesAno(p.efeito)}`]])];
        if (p.competencia_atual && p.efeito_padrao !== p.competencia_atual) {
            const caixa = el('label', 'mob-opcao');
            const marcar = entrada('checkbox');
            marcar.id = 'mob-rec-incluir-atual';
            marcar.checked = p.efeito === p.competencia_atual;
            marcar.addEventListener('change', () => carregarPrevia(marcar.checked ? p.competencia_atual : null));
            caixa.append(marcar, el('span', null, `Incluir a competência atual (${mesAno(p.competencia_atual)}); as vencidas ficam`));
            itens.push(caixa);
        }
        const resumo = texto(`${p.quantidade} ocorrência(s) deixam de ser exigíveis: ${reais(centavos(p.total))}`, 'mob-rec-resumo');
        resumo.id = 'mob-rec-quantidade';
        itens.push(resumo);
        if (p.afetadas.length) {
            itens.push(tabelaCompacta(p.afetadas.map((a) => [mesAno(a.competencia), dataCurta(a.data_vencimento), reais(centavos(a.valor))])));
        }
        if (p.preservadas.length) {
            itens.push(texto(`Permanecem (protegidas): ${p.preservadas.length} — ${reais(centavos(p.total_preservado))}`, 'discreto'));
            itens.push(tabelaCompacta(p.preservadas.map((a) => [mesAno(a.competencia), a.motivo, reais(centavos(a.valor))])));
        }
        corpo.replaceChildren(...itens);
        mostrarMensagem(m, p.pode_interromper ? '' : (p.motivo || 'Esta recorrência não pode ser alterada aqui.'), 'erro');
        confirmar.disabled = !p.pode_interromper || (!p.ativo && !p.quantidade);
    }

    async function carregarPrevia(efeito) {
        confirmar.disabled = true;
        const resposta = await previaInterrupcao(r.id, new URLSearchParams(efeito ? { efeito } : {}));
        const c = resposta.corpo || {};
        if (!c.success) {
            mostrarMensagem(m, c.error || FALHA_GERAL, 'erro');
            return;
        }
        previa = c.data;
        desenhar();
    }

    confirmar.addEventListener('click', async () => {
        if (!previa) return;
        confirmar.disabled = true;
        cancelar.disabled = true;
        const resposta = await interromperRecorrencia(r.id, { versao: previa.versao, efeito: previa.efeito, esperadas: previa.quantidade });
        const c = resposta.corpo || {};
        if (!c.success) {
            mostrarMensagem(m, c.error || FALHA_GERAL, 'erro');
            cancelar.disabled = false;
            confirmar.disabled = false;
            return;
        }
        await concluir('Recorrência inativada.');
    });
    abrirFolha(r.ativo ? 'Inativar recorrência' : 'Cancelar ocorrências futuras', corpo, m, acoes);
    carregarPrevia(null);
}

// ---------------------------------------------------------------------------------------------------------------
// Reativar (P22): periodo inativo que nao sera gerado e restauracao opcional das canceladas pela inativacao.

function abrirRetomada(r) {
    const corpo = el('div', 'mob-form mob-rec-previa');
    const m = mensagem();
    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', fecharFolha);
    const confirmar = botao('Reativar', 'primario');
    confirmar.id = 'mob-rec-confirmar';
    confirmar.disabled = true;
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, confirmar);
    let previa = null;
    let restaurar = false;

    function desenhar() {
        const p = previa;
        const mes = entrada('month', String(p.retomada).slice(0, 7));
        mes.id = 'mob-rec-retomada';
        mes.addEventListener('change', () => { if (/^\d{4}-\d{2}$/.test(mes.value)) carregarPrevia(`${mes.value}-01`); });
        const campoMes = el('label', 'mob-campo');
        campoMes.append(el('span', null, 'Retomar a partir de'), mes);
        const itens = [detalhes([['Recorrência', p.nome]]), campoMes];
        const meses = p.lacunas.map((l) => mesAno(l.competencia)).filter((v, i, a) => a.indexOf(v) === i).join(', ');
        const lacunas = texto(p.quantidade_lacunas
            ? `${p.quantidade_lacunas} ocorrência(s) do período inativo não serão geradas: ${meses}`
            : 'Nenhuma ocorrência do período inativo ficaria para trás.', 'mob-rec-resumo');
        lacunas.id = 'mob-rec-lacunas';
        itens.push(lacunas);
        if (p.quantidade_restauraveis) {
            const caixa = el('label', 'mob-opcao');
            const marcar = entrada('checkbox');
            marcar.id = 'mob-rec-restaurar';
            marcar.checked = restaurar;
            marcar.addEventListener('change', () => { restaurar = marcar.checked; });
            caixa.append(marcar, el('span', null, `Restaurar as ${p.quantidade_restauraveis} ocorrência(s) canceladas pela inativação `
                + `(${p.restauraveis.map((x) => mesAno(x.competencia)).join(', ')}; cerca de ${reais(centavos(p.total_restauravel))})`));
            itens.push(caixa);
        }
        if (p.dispensadas_mantidas) itens.push(texto(`${p.dispensadas_mantidas} ocorrência(s) excluída(s) uma a uma continuam excluídas.`, 'discreto'));
        corpo.replaceChildren(...itens);
        mostrarMensagem(m, p.pode_retomar ? '' : (p.motivo || 'Esta recorrência não pode ser alterada aqui.'), 'erro');
        confirmar.disabled = !p.pode_retomar;
    }

    async function carregarPrevia(retomada) {
        confirmar.disabled = true;
        const resposta = await previaRetomada(r.id, new URLSearchParams(retomada ? { retomada } : {}));
        const c = resposta.corpo || {};
        if (!c.success) {
            mostrarMensagem(m, c.error || FALHA_GERAL, 'erro');
            return;
        }
        previa = c.data;
        desenhar();
    }

    confirmar.addEventListener('click', async () => {
        if (!previa) return;
        confirmar.disabled = true;
        cancelar.disabled = true;
        const resposta = await retomarRecorrencia(r.id, { versao: previa.versao, retomada: previa.retomada, restaurar });
        const c = resposta.corpo || {};
        if (!c.success) {
            mostrarMensagem(m, c.error || FALHA_GERAL, 'erro');
            cancelar.disabled = false;
            confirmar.disabled = false;
            return;
        }
        await concluir('Recorrência reativada.');
    });
    abrirFolha('Reativar recorrência', corpo, m, acoes);
    carregarPrevia(null);
}

// ---------------------------------------------------------------------------------------------------------------
// Inicio

const usuario = await exigirUsuario();
if (usuario) {
    prepararModulos();
    ajustarCadastrosPelaPermissao(usuario.id);  // quem so le recebe o Lancar desabilitado (FIN-MVP-MOBILE-06)
    prepararMais();
    prepararFolha();
    document.querySelectorAll('#mob-situacao button').forEach((b) => b.addEventListener('click', () => {
        estado.situacao = b.dataset.situacao;
        mostrarAviso('');
        desenhar();
    }));
    $('mob-busca').addEventListener('input', () => {
        estado.busca = $('mob-busca').value;
        desenhar();
    });
    $('mob-nova').addEventListener('click', () => abrirFormulario(null));
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
        configurarRecorrencias(perfil.id, { avisar: (conteudo) => { estado.ultimoAviso = conteudo; } });
        // A permissao do perfil ativo (pode_gerir_perfil, a mesma do desktop): quem so le nao cadastra nem altera.
        estado.somenteLeitura = !(await podeGerirRecorrencias());
        $('mob-nova').hidden = estado.somenteLeitura;
        await carregar();
    } else {
        $('mob-lista').setAttribute('aria-busy', 'false');
        if ($('mob-aviso').hidden) mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
    }
}
