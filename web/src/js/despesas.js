// FIN-DESPESAS-1 — cadastro e edicao de despesas na tela Contas do mes.
//
// Toda regra fica no banco (financeiro.criar_despesa / editar_despesa / excluir_despesa /
// editar_recorrencia / inativar_recorrencia): gestao do perfil, bloqueio de conta paga ou
// com movimento, versao contra edicoes concorrentes, competencia dispensada ao excluir
// conta recorrente. A tela so mostra as acoes que o banco informa como permitidas
// (financeiro.despesa_para_edicao) e nunca grava direto em tabela.
// FIN-MOVIMENTACOES-1: pagar e estornar despesa comum (dados_pagamento_despesa, pagar_despesa,
// estornar_pagamento_despesa); valor devido, conta, saldo e pagamento vigente sao conferidos no banco.

import { supabase } from './cliente.js';
import { centavos, dataCurta, reais } from './comum.js';
import { abrirEstorno, abrirLiquidacao, linhaOperacao, textoAjuste } from './liquidacao.js';

const cache = new Map();  // perfil -> { categorias, contasBancarias }

function el(tag, classe, texto) {
    const elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto !== undefined && texto !== null) elemento.textContent = String(texto);
    return elemento;
}

function botao(texto, classe) {
    const elemento = el('button', classe ? `botao ${classe}` : 'botao', texto);
    elemento.type = 'button';
    return elemento;
}

const competenciaCurta = (iso) => `${iso.slice(5, 7)}/${iso.slice(0, 4)}`;

// "1.234,56" ou "1234.56" -> "1234.56"; o banco valida de novo.
function normalizarValor(texto) {
    const limpo = String(texto || '').trim().replace(/\s|R\$/g, '');
    const numero = limpo.includes(',') ? limpo.replace(/\./g, '').replace(',', '.') : limpo;
    return /^\d+(\.\d{1,2})?$/.test(numero) ? numero : null;
}

// Motivos de bloqueio do banco (sem acento) como o usuario le.
const BLOQUEIOS = {
    'Despesa paga: correcao so por estorno': 'Despesa paga: para corrigir, estorne o pagamento.',
    'Possui movimento financeiro vinculado': 'Possui movimento financeiro vinculado.',
    'Fatura ou compra de cartao: fica no modulo de cartoes': 'Fatura ou compra de cartão: fica no módulo de cartões.',
    'Parcela de consorcio: fica no modulo de consorcios': 'Parcela de consórcio: fica no módulo de consórcios.',
    'Parcela de financiamento: fica no modulo de financiamentos': 'Parcela de financiamento: fica no módulo de financiamentos.',
    'Gerada por outro modulo (veiculos, mobilidade ou assinaturas)': 'Gerada por outro módulo (veículos, mobilidade ou assinaturas).',
};
const textoBloqueio = (motivo) => BLOQUEIOS[motivo] || `${motivo}.`;

const formatarValor = (valor) => (valor === null || valor === undefined ? ''
    : Number(valor).toFixed(2).replace('.', ','));

// Mensagens do banco (sem acento) para o usuario.
function mensagemDeErro(error) {
    const texto = (error && error.message) || '';
    if (/alterad[ao] por outra operacao/i.test(texto)) return 'A despesa foi alterada por outra operação. Recarregue e tente de novo.';
    if (/nao autorizado|nao encontrada neste perfil/i.test(texto)) return 'Operação não autorizada para este perfil.';
    if (/Operacao bloqueada: /i.test(texto)) return `Operação bloqueada: ${textoBloqueio(texto.replace(/^.*Operacao bloqueada: /i, ''))}`;
    if (texto && error.code && /^(22023|P0001)$/.test(error.code)) return texto;
    return 'Não foi possível concluir a operação. Nada foi gravado.';
}

async function opcoesDoPerfil(perfilId) {
    if (!cache.has(perfilId)) {
        const [categorias, contas] = await Promise.all([
            supabase.rpc('categorias_de_despesa'),
            supabase.rpc('contas_bancarias_do_perfil', { p_perfil_id: perfilId }),
        ]);
        cache.set(perfilId, {
            categorias: categorias.error ? [] : categorias.data || [],
            contasBancarias: contas.error ? [] : (contas.data || []).filter((c) => c.status === 'ATIVO'),
        });
    }
    return cache.get(perfilId);
}

function campo(rotulo, controle, id) {
    const linha = el('label', 'form-campo');
    linha.htmlFor = id;
    controle.id = id;
    linha.append(el('span', 'form-rotulo', rotulo), controle);
    return linha;
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

function entrada(tipo, valor) {
    const input = el('input');
    input.type = tipo;
    if (valor !== undefined && valor !== null) input.value = String(valor);
    return input;
}

// Formulario unico para os tres modos: 'criar', 'conta' (uma conta pendente) e 'recorrencia'.
async function abrirFormulario(contexto, modo, edicao) {
    const painel = document.getElementById('despesa-painel');
    painel.replaceChildren();
    painel.hidden = false;
    const { categorias, contasBancarias } = await opcoesDoPerfil(contexto.perfilId);
    const conta = edicao ? edicao.conta : null;
    const itemAtual = edicao ? edicao.item : null;
    const recorrenteConta = modo === 'conta' && itemAtual.recorrente;
    const base = modo === 'recorrencia' ? itemAtual : conta;
    const titulos = { criar: 'Nova despesa', conta: 'Editar despesa', recorrencia: 'Editar recorrência' };

    const formulario = el('form', 'despesa-form');
    formulario.noValidate = true;
    formulario.append(el('h2', 'geracao-titulo', titulos[modo]));

    const tipo = seletor([['avulsa', 'Avulsa'], ['mensal', 'Recorrente mensal'], ['anual', 'Recorrente anual']],
        modo === 'recorrencia' ? itemAtual.tipo_recorrencia : 'avulsa');
    if (modo === 'criar') formulario.append(campo('Tipo', tipo, 'despesa-tipo'));
    if (modo === 'recorrencia') {
        tipo.querySelector('option[value="avulsa"]').remove();
        tipo.disabled = !edicao.pode_mudar_calendario;
        formulario.append(campo('Frequência', tipo, 'despesa-tipo'));
    }

    const nome = entrada('text', base ? base.nome : '');
    nome.maxLength = 100;
    nome.required = true;
    const valor = entrada('text', base ? formatarValor(base.valor) : '');
    valor.inputMode = 'decimal';
    valor.placeholder = '0,00';
    formulario.append(campo('Nome', nome, 'despesa-nome'), campo('Valor (R$)', valor, 'despesa-valor'));

    const categoria = seletor([['', 'Selecione'], ...categorias.map((c) => [c.id, c.nome])],
        modo === 'criar' ? '' : itemAtual.categoria_id);
    if (!recorrenteConta) formulario.append(campo('Categoria', categoria, 'despesa-categoria'));

    const vencimento = entrada('date', base ? base.data_vencimento : '');
    if (modo === 'conta') vencimento.disabled = !edicao.pode_mudar_vencimento;
    if (modo === 'recorrencia') vencimento.disabled = !edicao.pode_mudar_calendario;
    formulario.append(campo(modo === 'recorrencia' ? 'Primeiro vencimento (define o dia)' : 'Vencimento',
        vencimento, 'despesa-vencimento'));

    // Competencia: so na avulsa (na recorrencia e o mes de cada vencimento).
    const competencia = entrada('month', conta ? conta.competencia.slice(0, 7) : '');
    const linhaCompetencia = campo('Competência', competencia, 'despesa-competencia');
    let competenciaManual = modo === 'conta';
    competencia.addEventListener('input', () => { competenciaManual = true; });
    vencimento.addEventListener('change', () => {
        if (!competenciaManual && vencimento.value) competencia.value = vencimento.value.slice(0, 7);
    });
    if (modo !== 'recorrencia' && !recorrenteConta) formulario.append(linhaCompetencia);
    if (modo === 'criar') {
        tipo.addEventListener('change', () => { linhaCompetencia.hidden = tipo.value !== 'avulsa'; });
    }

    const debito = entrada('checkbox');
    debito.checked = Boolean(base && base.debito_automatico);
    const contaBancaria = seletor([['', 'Selecione'], ...contasBancarias.map((c) => [c.id, c.nome])],
        base ? base.conta_bancaria_id : '');
    const linhaDebito = el('label', 'form-check');
    linhaDebito.htmlFor = 'despesa-debito';
    debito.id = 'despesa-debito';
    linhaDebito.append(debito, el('span', null, 'Débito automático'));
    const linhaConta = campo('Conta bancária', contaBancaria, 'despesa-conta-bancaria');
    linhaConta.hidden = !debito.checked;
    debito.addEventListener('change', () => { linhaConta.hidden = !debito.checked; });
    formulario.append(linhaDebito, linhaConta);

    const observacoes = el('textarea');
    observacoes.rows = 2;
    observacoes.maxLength = 1000;
    observacoes.value = (base && base.descricao) || '';
    formulario.append(campo('Observações', observacoes, 'despesa-observacoes'));

    const erro = el('p', 'login-error');
    erro.setAttribute('role', 'alert');
    erro.hidden = true;
    const salvar = botao('Salvar', 'botao-principal');
    salvar.type = 'submit';
    const cancelar = botao('Cancelar');
    const botoes = el('div', 'geracao-botoes');
    botoes.append(salvar, cancelar);
    formulario.append(erro, botoes);
    painel.append(formulario);
    nome.focus();

    const chave = crypto.randomUUID();  // mesma chave em reenvios deste formulario: sem duplicar
    cancelar.addEventListener('click', () => { painel.replaceChildren(); painel.hidden = true; });
    formulario.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        erro.hidden = true;
        const valorNormal = normalizarValor(valor.value);
        const problemas = [];
        if (!nome.value.trim()) problemas.push('informe o nome');
        if (!valorNormal || Number(valorNormal) <= 0) problemas.push('informe um valor válido');
        if (!recorrenteConta && !categoria.value) problemas.push('escolha a categoria');
        if (!vencimento.value) problemas.push('informe o vencimento');
        if (debito.checked && !contaBancaria.value) problemas.push('escolha a conta bancária do débito');
        if (problemas.length) {
            erro.textContent = `Verifique: ${problemas.join(', ')}.`;
            erro.hidden = false;
            return;
        }
        const dados = {
            nome: nome.value.trim(),
            valor: valorNormal,
            descricao: observacoes.value.trim(),
            debito_automatico: debito.checked,
            conta_bancaria_id: debito.checked ? Number(contaBancaria.value) : null,
        };
        if (!vencimento.disabled) dados.data_vencimento = vencimento.value;
        if (!recorrenteConta) dados.categoria_id = Number(categoria.value);
        salvar.disabled = true;
        cancelar.disabled = true;
        let resposta;
        if (modo === 'criar') {
            const recorrente = tipo.value !== 'avulsa';
            if (recorrente) Object.assign(dados, { recorrente: true, tipo_recorrencia: tipo.value });
            else if (competencia.value) dados.competencia = `${competencia.value}-01`;
            resposta = await supabase.rpc('criar_despesa', { p_perfil_id: contexto.perfilId, p_dados: dados, p_chave: chave });
        } else if (modo === 'conta') {
            if (!itemAtual.recorrente && competencia.value) dados.competencia = `${competencia.value}-01`;
            resposta = await supabase.rpc('editar_despesa', {
                p_perfil_id: contexto.perfilId, p_conta_id: conta.id, p_versao: edicao.versao, p_dados: dados,
            });
        } else {
            if (!tipo.disabled) dados.tipo_recorrencia = tipo.value;
            resposta = await supabase.rpc('editar_recorrencia', {
                p_perfil_id: contexto.perfilId, p_item_id: itemAtual.id, p_versao: edicao.versao_recorrencia, p_dados: dados,
            });
        }
        if (resposta.error) {
            erro.textContent = mensagemDeErro(resposta.error);
            erro.hidden = false;
            salvar.disabled = false;
            cancelar.disabled = false;
            return;
        }
        painel.replaceChildren();
        painel.hidden = true;
        let mensagem = 'Despesa salva.';
        if (modo === 'criar' && resposta.data.recorrente) {
            mensagem = 'Recorrência cadastrada. As contas são geradas pela ação "Gerar contas".';
        } else if (modo === 'criar' || (modo === 'conta' && !itemAtual.recorrente)) {
            mensagem = `Despesa salva na competência ${competenciaCurta(resposta.data.competencia)}.`;
        } else if (modo === 'recorrencia') {
            mensagem = 'Recorrência atualizada. Vale para as próximas contas; as já existentes não mudam.';
        }
        await contexto.recarregar(mensagem);
    });
}

// Botao "Nova despesa": so para quem gerencia o perfil.
export function mostrarAcoesDoMes(contexto, podeGerir) {
    const destino = document.getElementById('acoes-mes');
    destino.replaceChildren();
    document.getElementById('despesa-painel').hidden = true;
    document.getElementById('despesa-painel').replaceChildren();
    if (!podeGerir) return;
    const nova = botao('Nova despesa', 'botao-principal');
    nova.id = 'nova-despesa';
    nova.addEventListener('click', () => abrirFormulario(contexto, 'criar'));
    destino.append(nova);
}

function confirmarAcao(area, pergunta, rotulo, executar) {
    area.replaceChildren();
    const confirmar = botao(rotulo, 'botao-perigo');
    const cancelar = botao('Cancelar');
    const erro = el('p', 'login-error');
    erro.setAttribute('role', 'alert');
    erro.hidden = true;
    const botoes = el('div', 'geracao-botoes');
    botoes.append(confirmar, cancelar);
    area.append(el('p', 'despesa-pergunta', pergunta), erro, botoes);
    cancelar.addEventListener('click', () => area.replaceChildren());
    confirmar.addEventListener('click', async () => {
        confirmar.disabled = true;
        cancelar.disabled = true;
        const { error } = await executar();
        if (error) {
            erro.textContent = mensagemDeErro(error);
            erro.hidden = false;
            cancelar.disabled = false;
        }
    });
}

// Pagamento da despesa: historico (pagamentos e estornos) e a acao permitida agora (Pagar ou Estornar).
async function mostrarPagamento(caixa, contaId, contexto) {
    const dados = () => supabase.rpc('dados_pagamento_despesa', { p_perfil_id: contexto.perfilId, p_conta_id: contaId });
    const { data, error } = await dados();
    if (error || !data) return;
    const area = el('div', 'fatura-pagamento');
    for (const p of data.pagamentos) {
        let texto = `Pago em ${linhaOperacao(p.data_pagamento, p.valor_pago, p.conta_nome)}`;
        if (p.tipo_ajuste) texto += ` · ${textoAjuste(p.tipo_ajuste)}: ${p.justificativa}`;
        if (p.estorno) texto += ` · estornado em ${dataCurta(p.estorno.data)}${p.estorno.motivo ? ` (${p.estorno.motivo})` : ''}`;
        area.append(el('p', p.vigente ? 'pagamento-linha' : 'pagamento-linha pagamento-estornado', texto));
    }
    const painel = document.getElementById('despesa-painel');
    const vigente = data.pagamentos.find((p) => p.vigente);
    const despesa = data.despesa;
    if (data.pode_pagar) {
        const pagar = botao('Pagar', 'botao-principal');
        pagar.addEventListener('click', () => abrirLiquidacao({
            painel, modo: 'pagar', prefixo: 'pagamento', titulo: 'Pagar despesa', mensagemDeErro,
            resumo: [['Despesa', despesa.descricao], ['Vencimento', dataCurta(despesa.data_vencimento)]],
            referencia: despesa.valor, rotuloReferencia: 'Valor devido', rotuloValor: 'Valor pago (R$)',
            rotuloData: 'Data do pagamento', contas: data.contas,
            enviar: (c, chave) => supabase.rpc('pagar_despesa', {
                p_perfil_id: contexto.perfilId, p_conta_id: contaId, p_chave: chave, p_dados: {
                    conta_bancaria_id: c.conta_bancaria_id, data_pagamento: c.data, valor_pago: c.valor,
                    valor_devido: c.referencia, tipo_ajuste: c.tipo_ajuste, justificativa: c.justificativa } }),
            recarregarReferencia: async () => { const r = await dados(); return r.error ? null : r.data.despesa.valor; },
            sucesso: (r) => contexto.recarregar(`Despesa paga: ${reais(centavos(r.valor_pago))} debitados de ${r.conta_nome}. `
                + `Saldo da conta: ${reais(centavos(r.saldo_conta))}.`),
        }));
        area.append(pagar);
    } else if (data.pode_estornar && vigente) {
        const estornar = botao('Estornar pagamento');
        estornar.addEventListener('click', () => abrirEstorno({
            painel, prefixo: 'estorno', titulo: 'Estornar pagamento', mensagemDeErro,
            resumo: [['Despesa', despesa.descricao], ['Valor pago', reais(centavos(vigente.valor_pago))],
                ['Conta bancária', vigente.conta_nome], ['Data do pagamento', dataCurta(vigente.data_pagamento)]],
            enviar: (d, chave) => supabase.rpc('estornar_pagamento_despesa', {
                p_perfil_id: contexto.perfilId, p_conta_id: contaId, p_movimento_id: vigente.movimento_id, p_dados: d, p_chave: chave }),
            sucesso: (r) => contexto.recarregar(`Pagamento estornado: ${reais(centavos(r.valor_estornado))} devolvidos a `
                + `${vigente.conta_nome}. Saldo da conta: ${reais(centavos(r.saldo_conta))}.`),
        }));
        area.append(estornar);
    } else if (data.sistema === 'FLASK' && !despesa.paga && !despesa.bloqueio) {
        area.append(el('p', 'geracao-dica', 'O pagamento das despesas deste perfil ainda é feito no sistema atual.'));
    }
    if (area.childElementCount) caixa.prepend(area);
}

// Acoes de uma despesa, carregadas ao abrir o detalhe (o banco diz o que e permitido).
export async function carregarAcoes(caixa, contaId, contexto) {
    mostrarPagamento(caixa, contaId, contexto);
    const { data, error } = await supabase.rpc('despesa_para_edicao', { p_perfil_id: contexto.perfilId, p_conta_id: contaId });
    if (error || !data || !data.pode_gerir) return;
    if (data.bloqueio) {
        caixa.append(el('p', 'despesa-bloqueio', textoBloqueio(data.bloqueio)));
        if (!data.pode_editar_recorrencia) return;
    }
    const acoes = el('div', 'despesa-acoes');
    const confirmacao = el('div', 'despesa-confirmacao');
    if (data.pode_editar) {
        const editar = botao('Editar');
        editar.addEventListener('click', () => abrirFormulario(contexto, 'conta', data));
        acoes.append(editar);
    }
    if (data.pode_excluir) {
        const excluir = botao('Excluir');
        excluir.addEventListener('click', () => confirmarAcao(confirmacao,
            data.item.recorrente
                ? 'Excluir esta conta? A competência fica dispensada e não volta a ser gerada.'
                : 'Excluir esta despesa? Ela ainda não foi paga.',
            'Confirmar exclusão',
            async () => {
                const resposta = await supabase.rpc('excluir_despesa', {
                    p_perfil_id: contexto.perfilId, p_conta_id: contaId, p_versao: data.versao,
                });
                if (!resposta.error) await contexto.recarregar('Despesa excluída.');
                return resposta;
            }));
        acoes.append(excluir);
    }
    if (data.pode_editar_recorrencia) {
        const editarRec = botao('Editar recorrência');
        editarRec.addEventListener('click', () => abrirFormulario(contexto, 'recorrencia', data));
        acoes.append(editarRec);
    }
    if (data.pode_inativar_recorrencia) {
        const inativar = botao('Inativar recorrência');
        inativar.addEventListener('click', () => confirmarAcao(confirmacao,
            'Inativar a recorrência? Nenhuma conta nova será gerada; as existentes continuam.',
            'Confirmar inativação',
            async () => {
                const resposta = await supabase.rpc('inativar_recorrencia', {
                    p_perfil_id: contexto.perfilId, p_item_id: data.item.id, p_versao: data.versao_recorrencia,
                });
                if (!resposta.error) await contexto.recarregar('Recorrência inativada.');
                return resposta;
            }));
        acoes.append(inativar);
    }
    if (acoes.childElementCount) caixa.append(acoes, confirmacao);
}
