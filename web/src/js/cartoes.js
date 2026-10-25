// FIN-CARTOES-1 — Cartoes: faturas do mes, compras a vista e parceladas, cadastro de cartoes.
//
// Consulta: financeiro.faturas_do_mes (situacao, compras e previsto como a tela de contas),
// compras_da_fatura, cartoes_do_perfil (sem numero completo nem CVV), compra_para_edicao.
// Escrita so por RPC (criar_compra, editar_compra, excluir_compra, criar_cartao, editar_cartao,
// inativar_cartao). Parcelas, centavos, fatura de destino e bloqueios sao decididos no banco;
// a previa (previa_compra) mostra o que sera gravado.
// FIN-CARTOES-FECHAMENTO-1: a fatura da 1a parcela e sugerida pelo fechamento (sugerir_competencia, so
// leitura) e pode ser trocada; a escolha manual nunca e sobrescrita. Fatura consolidada so recebe compra
// com a confirmacao do total visto, uma caixa por fatura (o banco reconfere sob trava).
// FIN-CARTOES-PAGAMENTO-1: pagar e estornar a fatura (dados_pagamento_fatura, pagar_fatura,
// estornar_pagamento_fatura). Total, conta, saldo e pagamento vigente sao conferidos no banco; aqui so a escolha.

import { supabase } from './cliente.js';
import {
    MES_VALIDO, botao, campo, centavos, competenciaCurta, dataCurta, deslocarMes, el, entrada, formatarValor,
    linhaDetalhe, mesAtualBrasilia, normalizarValor, reais, seletor, tituloDoMes,
} from './comum.js';
import {
    REGRAS_DIA_FECHAMENTO, confirmacoes, consolidadaDoErro, mesSemSugestao, textoConsolidada, textoRegra, textoSugestao,
} from './fechamento.js';
import { iniciarMoldura } from './moldura.js';

const SITUACAO = { ABERTA: 'Aberta', FECHADA: 'Fechada', PAGA: 'Paga', SEM_FATURA: 'Sem compras' };
const BLOQUEIOS = {
    'Gerada por recorrencia: edite a recorrencia': 'Gerada por recorrência: altere a recorrência na tela de contas.',
    'Fatura paga: correcao so por estorno': 'Fatura paga: para corrigir, estorne o pagamento da fatura.',
    'Fatura fechada (consolidada)': 'Fatura fechada (consolidada).',
};
const textoBloqueio = (motivo) => BLOQUEIOS[motivo] || `${motivo}.`;

function mensagemDeErro(error) {
    const texto = (error && error.message) || '';
    if (/alterad[ao] por outra operacao/i.test(texto)) return 'O registro foi alterado por outra operação. Recarregue e tente de novo.';
    if (/nao autorizado|nao encontrad[ao] neste perfil/i.test(texto)) return 'Operação não autorizada para este perfil.';
    if (/Operacao bloqueada: /i.test(texto)) return `Operação bloqueada: ${textoBloqueio(texto.replace(/^.*Operacao bloqueada: /i, ''))}`;
    if (texto && error.code && /^(22023|P0001)$/.test(error.code)) return texto;
    return 'Não foi possível concluir a operação. Nada foi gravado.';
}

let categoriasCache = null;
async function categorias() {
    if (!categoriasCache) {
        const { data, error } = await supabase.rpc('categorias_de_despesa');
        categoriasCache = error ? [] : data || [];
    }
    return categoriasCache;
}

function formulario(titulo) {
    const painel = document.getElementById('cartao-painel');
    painel.replaceChildren();
    painel.hidden = false;
    const form = el('form', 'despesa-form');
    form.noValidate = true;
    form.append(el('h2', 'geracao-titulo', titulo));
    const erro = el('p', 'login-error');
    erro.setAttribute('role', 'alert');
    erro.hidden = true;
    const salvar = botao('Salvar', 'botao-principal');
    salvar.type = 'submit';
    const cancelar = botao('Cancelar');
    const botoes = el('div', 'geracao-botoes');
    botoes.append(salvar, cancelar);
    const fechar = () => { painel.replaceChildren(); painel.hidden = true; };
    cancelar.addEventListener('click', fechar);
    const falhar = (texto) => {
        erro.textContent = texto;
        erro.hidden = false;
        salvar.disabled = false;
        cancelar.disabled = false;
    };
    const travar = () => { salvar.disabled = true; cancelar.disabled = true; };
    painel.scrollIntoView({ block: 'nearest' });
    return { painel, form, erro, salvar, cancelar, botoes, fechar, falhar, travar };
}

function hojeBrasilia() {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
}

// Caixa de confirmacao de uma fatura consolidada (marcada so pelo usuario).
function caixaConsolidada(consolidada, prefixo) {
    const caixa = entrada('checkbox');
    caixa.id = `${prefixo}-consolidada-${consolidada.fatura_id}`;
    const linha = el('label', 'form-check');
    linha.htmlFor = caixa.id;
    linha.append(caixa, el('span', null, textoConsolidada(consolidada)));
    return { linha, caixa };
}

// Previa das parcelas: calculada no banco (mesma funcao do cadastro), so leitura. Destino em fatura
// consolidada: uma caixa por fatura em estado.consolidadas. O conteudo so e trocado quando a resposta chega:
// limpar antes deslocaria o botao Salvar no meio do clique (o `change` do campo sai no mousedown).
function montarPrevia(destino, contexto, lerDados, estado) {
    let pedido = 0;
    return async () => {
        const dados = lerDados();
        const atual = ++pedido;
        if (!dados) {
            destino.replaceChildren();
            estado.consolidadas = [];
            return;
        }
        const { data, error } = await supabase.rpc('previa_compra', { p_perfil_id: contexto.perfilId, p_dados: dados });
        if (atual !== pedido) return;
        if (error) {
            destino.replaceChildren(el('p', 'geracao-dica', mensagemDeErro(error)));
            estado.consolidadas = [];
            return;
        }
        const lista = el('ul', 'cartao-previa');
        for (const p of data.parcelas) {
            const texto = `${p.numero}/${p.total} · fatura ${competenciaCurta(p.mes_fatura)} · ${reais(centavos(p.valor))}`;
            lista.append(el('li', null, p.redirecionada ? `${texto} (fatura paga: vai para a próxima)`
                : p.situacao_fatura === 'FECHADA' ? `${texto} (fatura consolidada)` : texto));
        }
        const conteudo = [el('p', 'form-rotulo', `Parcelas (soma ${reais(centavos(data.soma))})`), lista];
        const consolidadas = [];
        for (const consolidada of data.consolidadas || []) {
            const { linha, caixa } = caixaConsolidada(consolidada, 'compra');
            conteudo.push(linha);
            consolidadas.push({ ...consolidada, caixa });
        }
        destino.replaceChildren(...conteudo);
        estado.consolidadas = consolidadas;
    };
}

function abrirNovaCompra(contexto) {
    const ativos = contexto.cartoes.filter((c) => c.ativo);
    const f = formulario('Nova compra no cartão');
    const cartao = seletor(ativos.map((c) => [c.id, c.nome]), ativos.length ? ativos[0].id : '');
    const descricao = entrada('text');
    descricao.maxLength = 200;
    const valor = entrada('text');
    valor.inputMode = 'decimal';
    valor.placeholder = '0,00';
    const parcelas = entrada('number', 1);
    parcelas.min = '1';
    parcelas.max = '60';
    const dataCompra = entrada('date', hojeBrasilia());
    const mesFatura = entrada('month', contexto.mes);
    const dicaMes = el('p', 'geracao-dica', 'Fatura da 1ª parcela; as seguintes vão para os meses seguintes.');
    const dicaSugestao = el('p', 'geracao-dica');
    dicaSugestao.id = 'compra-sugestao';
    dicaSugestao.setAttribute('role', 'status');
    dicaSugestao.hidden = true;
    const usarSugerida = botao('Usar a sugerida');
    usarSugerida.id = 'compra-usar-sugerida';
    usarSugerida.hidden = true;
    const categoria = seletor([['', 'Selecione']], '');
    categorias().then((lista) => { for (const c of lista) categoria.append(new Option(c.nome, String(c.id))); });
    const observacoes = el('textarea');
    observacoes.rows = 2;
    observacoes.maxLength = 1000;
    const previa = el('div', 'cartao-previa-caixa');
    previa.id = 'compra-previa';

    const lerDados = () => {
        const valorNormal = normalizarValor(valor.value);
        if (!cartao.value || !valorNormal || !dataCompra.value || !mesFatura.value || !categoria.value
            || !descricao.value.trim()) return null;
        return {
            cartao_id: Number(cartao.value), descricao: descricao.value.trim(), valor: valorNormal,
            total_parcelas: Number(parcelas.value || 1), data_compra: dataCompra.value, mes_fatura: `${mesFatura.value}-01`,
            categoria_id: Number(categoria.value), observacoes: observacoes.value.trim(),
        };
    };
    const estado = { consolidadas: [] };
    const atualizarPrevia = montarPrevia(previa, contexto, lerDados, estado);
    for (const controle of [descricao, valor, parcelas, mesFatura, categoria]) {
        controle.addEventListener('change', atualizarPrevia);
    }

    // Sugestao pelo fechamento: recalculada ao trocar cartao ou data; so preenche o mes enquanto o usuario
    // nao o escolheu.
    let manual = false;
    let sugestao = null;
    let pedidoSugestao = 0;
    const mostrarSugestao = () => {
        const { texto, alerta } = textoSugestao(sugestao, { manual, escolhido: mesFatura.value });
        dicaSugestao.textContent = texto;
        dicaSugestao.hidden = !texto;
        dicaSugestao.classList.toggle('dica-alerta', alerta);
        usarSugerida.hidden = !(sugestao && sugestao.situacao === 'SUGERIDA' && manual
            && mesFatura.value !== sugestao.competencia.slice(0, 7));
    };
    const sugerir = async () => {
        const atual = ++pedidoSugestao;
        sugestao = null;
        if (cartao.value && dataCompra.value) {
            const { data, error } = await supabase.rpc('sugerir_competencia', {
                p_perfil_id: contexto.perfilId, p_cartao_id: Number(cartao.value), p_data_compra: dataCompra.value,
            });
            if (atual !== pedidoSugestao) return;
            sugestao = error || !data ? { situacao: 'INDISPONIVEL' } : data;
            if (!manual) {
                mesFatura.value = sugestao.situacao === 'SUGERIDA' ? sugestao.competencia.slice(0, 7)
                    : mesSemSugestao(sugestao.situacao, contexto.mes);
            }
        }
        mostrarSugestao();
        await atualizarPrevia();
    };
    cartao.addEventListener('change', sugerir);
    dataCompra.addEventListener('change', sugerir);
    mesFatura.addEventListener('input', () => { manual = true; mostrarSugestao(); });
    usarSugerida.addEventListener('click', () => {
        manual = false;
        mesFatura.value = sugestao.competencia.slice(0, 7);
        mostrarSugestao();
        atualizarPrevia();
    });

    f.form.append(campo('Cartão', cartao, 'compra-cartao'), campo('Descrição', descricao, 'compra-descricao'),
        campo('Valor total (R$)', valor, 'compra-valor'), campo('Parcelas', parcelas, 'compra-parcelas'),
        campo('Data da compra', dataCompra, 'compra-data'), campo('Mês da fatura', mesFatura, 'compra-mes'), dicaMes,
        dicaSugestao, usarSugerida,
        campo('Categoria', categoria, 'compra-categoria'), campo('Observações', observacoes, 'compra-observacoes'),
        previa, f.erro, f.botoes);
    f.painel.append(f.form);
    sugerir();

    const chave = crypto.randomUUID();
    f.form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        f.erro.hidden = true;
        const dados = lerDados();
        if (!dados) {
            f.falhar('Verifique: cartão, descrição, valor, data, mês da fatura e categoria são obrigatórios.');
            return;
        }
        if (estado.consolidadas.some((c) => !c.caixa.checked)) {
            f.falhar('Confirme a inclusão na fatura consolidada ou escolha outro mês da fatura.');
            return;
        }
        if (estado.consolidadas.length) dados.confirmar_consolidadas = confirmacoes(estado.consolidadas);
        f.travar();
        const { data, error } = await supabase.rpc('criar_compra', { p_perfil_id: contexto.perfilId, p_dados: dados, p_chave: chave });
        if (error) {
            if (consolidadaDoErro(error)) {  // consolidada ou total mudou depois da previa: nada gravado
                await atualizarPrevia();
                f.falhar('A fatura de destino está consolidada e o total mudou ou não foi confirmado. Revise a prévia e confirme de novo.');
                return;
            }
            f.falhar(mensagemDeErro(error));
            return;
        }
        f.fechar();
        const n = data.lancamentos.length;
        await contexto.recarregar(n > 1
            ? `Compra registrada em ${n} parcelas, a partir da fatura ${competenciaCurta(data.faturas[0])}.`
            : `Compra registrada na fatura ${competenciaCurta(data.faturas[0])}.`);
    });
}

async function abrirEdicaoCompra(contexto, lancamentoId) {
    const { data, error } = await supabase.rpc('compra_para_edicao', { p_perfil_id: contexto.perfilId, p_lancamento_id: lancamentoId });
    if (error || !data) return;
    const aVista = data.compra.total_parcelas <= 1;
    const f = formulario(aVista ? 'Editar compra' : 'Editar compra parcelada');
    const descricao = entrada('text', data.compra.descricao);
    descricao.maxLength = 200;
    const categoria = seletor([], '');
    for (const c of await categorias()) categoria.append(new Option(c.nome, String(c.id)));
    categoria.value = String(data.compra.categoria_id);
    const observacoes = el('textarea');
    observacoes.rows = 2;
    observacoes.maxLength = 1000;
    observacoes.value = data.compra.observacoes || '';
    f.form.append(campo('Descrição', descricao, 'edicao-descricao'), campo('Categoria', categoria, 'edicao-categoria'));
    let valor;
    let dataCompra;
    let mesFatura;
    let pendente = null;  // fatura consolidada que o banco pediu para confirmar
    const confirmacao = el('div');
    if (aVista) {
        valor = entrada('text', formatarValor(data.compra.valor));
        valor.inputMode = 'decimal';
        dataCompra = entrada('date', data.compra.data_compra);
        mesFatura = entrada('month', data.compra.mes_fatura.slice(0, 7));
        // Na edicao o mes gravado e escolha do usuario: a sugestao da nova data so aparece como dica.
        const dicaSugestao = el('p', 'geracao-dica');
        dicaSugestao.id = 'edicao-sugestao';
        dicaSugestao.hidden = true;
        let pedidoSugestao = 0;
        dataCompra.addEventListener('change', async () => {
            const atual = ++pedidoSugestao;
            const resposta = dataCompra.value ? await supabase.rpc('sugerir_competencia', {
                p_perfil_id: contexto.perfilId, p_cartao_id: data.compra.cartao_id, p_data_compra: dataCompra.value,
            }) : { data: null };
            if (atual !== pedidoSugestao) return;
            const sugestao = resposta.error ? { situacao: 'INDISPONIVEL' } : resposta.data;
            const { texto, alerta } = textoSugestao(sugestao, { manual: true, escolhido: mesFatura.value });
            dicaSugestao.textContent = texto;
            dicaSugestao.hidden = !texto;
            dicaSugestao.classList.toggle('dica-alerta', alerta);
        });
        mesFatura.addEventListener('change', () => { pendente = null; confirmacao.replaceChildren(); });
        f.form.append(campo('Valor (R$)', valor, 'edicao-valor'), campo('Data da compra', dataCompra, 'edicao-data'),
            campo('Mês da fatura', mesFatura, 'edicao-mes'), dicaSugestao, confirmacao);
    } else {
        const preservadas = data.parcelas.length - data.abertas;
        f.form.append(el('p', 'geracao-dica', preservadas
            ? `Vale para as ${data.abertas} parcelas em fatura aberta; ${preservadas} em fatura paga ou fechada ficam como estão.`
            : `Vale para as ${data.abertas} parcelas. Valor e datas não mudam: exclua e lance de novo.`));
    }
    f.form.append(campo('Observações', observacoes, 'edicao-observacoes'), f.erro, f.botoes);
    f.painel.append(f.form);
    f.form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (!descricao.value.trim()) {
            f.falhar('Verifique: informe a descrição.');
            return;
        }
        const alteracao = { descricao: descricao.value.trim(), categoria_id: Number(categoria.value), observacoes: observacoes.value.trim() };
        if (aVista) {
            const valorNormal = normalizarValor(valor.value);
            if (!valorNormal || Number(valorNormal) <= 0 || !dataCompra.value || !mesFatura.value) {
                f.falhar('Verifique: valor, data da compra e mês da fatura.');
                return;
            }
            Object.assign(alteracao, { valor: valorNormal, data_compra: dataCompra.value, mes_fatura: `${mesFatura.value}-01` });
            if (pendente && !pendente.caixa.checked) {
                f.falhar('Confirme a inclusão na fatura consolidada ou escolha outro mês da fatura.');
                return;
            }
            if (pendente) alteracao.confirmar_consolidadas = confirmacoes([pendente.detalhe]);
        }
        f.travar();
        const resposta = await supabase.rpc('editar_compra', {
            p_perfil_id: contexto.perfilId, p_lancamento_id: lancamentoId, p_versao: data.versao, p_dados: alteracao,
        });
        if (resposta.error) {
            const detalhe = consolidadaDoErro(resposta.error);
            if (detalhe && aVista) {  // nada gravado: mostra o total atual para a confirmacao desta operacao
                const { linha, caixa } = caixaConsolidada(detalhe, 'edicao');
                pendente = { detalhe, caixa };
                confirmacao.replaceChildren(linha);
                f.falhar('A fatura escolhida está consolidada: confirme a inclusão para salvar.');
                return;
            }
            f.falhar(mensagemDeErro(resposta.error));
            return;
        }
        f.fechar();
        await contexto.recarregar('Compra atualizada.');
    });
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

async function pedirExclusao(area, contexto, lancamentoId) {
    const { data, error } = await supabase.rpc('compra_para_edicao', { p_perfil_id: contexto.perfilId, p_lancamento_id: lancamentoId });
    if (error || !data) return;
    const preservadas = data.parcelas.length - data.abertas;
    const pergunta = data.parcelas.length <= 1 ? 'Excluir esta compra?'
        : preservadas ? `Excluir as ${data.abertas} parcelas em fatura aberta? ${preservadas} em fatura paga ou fechada ficam (para corrigi-las é preciso estorno).`
            : `Excluir a compra inteira (${data.abertas} parcelas)?`;
    confirmarAcao(area, pergunta, 'Confirmar exclusão', async () => {
        const resposta = await supabase.rpc('excluir_compra', {
            p_perfil_id: contexto.perfilId, p_lancamento_id: lancamentoId, p_versao: data.versao,
        });
        if (!resposta.error) await contexto.recarregar(resposta.data.excluidas > 1 ? `${resposta.data.excluidas} parcelas excluídas.` : 'Compra excluída.');
        return resposta;
    });
}

function itemCompra(compra, contexto) {
    const item = el('li', 'cartao-compra');
    item.dataset.lancamentoId = String(compra.id);
    const linha = el('div', 'cartao-compra-linha');
    const parcela = compra.total_parcelas > 1 ? ` · ${compra.numero_parcela}/${compra.total_parcelas}` : '';
    const texto = el('span', 'conta-principal');
    texto.append(el('span', 'conta-nome', compra.descricao),
        el('span', 'conta-vencimento', `${dataCurta(compra.data_compra)}${parcela}${compra.categoria_nome ? ` · ${compra.categoria_nome}` : ''}`));
    linha.append(texto, el('span', 'conta-valor', reais(centavos(compra.valor))));
    item.append(linha);
    if (compra.pode_editar) {
        const acoes = el('div', 'despesa-acoes');
        const confirmacao = el('div', 'despesa-confirmacao');
        const editar = botao('Editar');
        editar.addEventListener('click', () => abrirEdicaoCompra(contexto, compra.id));
        const excluir = botao('Excluir');
        excluir.addEventListener('click', () => pedirExclusao(confirmacao, contexto, compra.id));
        acoes.append(editar, excluir);
        item.append(acoes, confirmacao);
    } else if (compra.bloqueio && contexto.podeGerir) {
        item.append(el('p', 'despesa-bloqueio', textoBloqueio(compra.bloqueio)));
    }
    return item;
}

const AJUSTES = { JUROS: 'Juros ou encargos', DESCONTO: 'Desconto', AJUSTE: 'Ajuste de quitação integral' };

// Pagamento integral (D2: sem saldo pendente). O total vem do banco; valor diferente dele pede classificacao e
// justificativa (D3), conferidas de novo no banco.
function abrirPagamento(contexto, dados) {
    const { fatura } = dados;
    const f = formulario('Pagar fatura');
    f.salvar.textContent = 'Confirmar pagamento';
    let executado = centavos(fatura.valor_executado);
    const resumo = el('dl', 'conta-detalhe');
    linhaDetalhe(resumo, 'Cartão', fatura.cartao_nome);
    linhaDetalhe(resumo, 'Fatura', competenciaCurta(fatura.competencia));
    const totalTexto = el('dd', null, reais(executado));
    resumo.append(el('dt', null, 'Total das compras'), totalTexto);
    const valor = entrada('text', formatarValor(executado / 100));
    valor.inputMode = 'decimal';
    const data = entrada('date', hojeBrasilia());
    const conta = seletor(dados.contas.map((c) => [c.id, `${c.nome} · saldo ${reais(centavos(c.saldo))}`]),
        dados.contas.length ? dados.contas[0].id : '');
    const tipo = seletor([['', 'Selecione']], '');
    const justificativa = el('textarea');
    justificativa.rows = 2;
    justificativa.maxLength = 500;
    const ajuste = el('div', 'pagamento-ajuste');
    ajuste.append(el('p', 'geracao-dica', 'O valor pago é diferente do total: classifique e justifique. A fatura fica quitada.'),
        campo('Diferença', tipo, 'pagamento-tipo'), campo('Justificativa', justificativa, 'pagamento-justificativa'));
    const atualizarAjuste = () => {
        const pago = normalizarValor(valor.value);
        const diferenca = pago === null ? 0 : centavos(pago) - executado;
        ajuste.hidden = diferenca === 0;
        const opcoes = diferenca > 0 ? ['JUROS', 'AJUSTE'] : ['DESCONTO', 'AJUSTE'];
        const atual = opcoes.includes(tipo.value) ? tipo.value : '';
        tipo.replaceChildren(new Option('Selecione', ''), ...opcoes.map((t) => new Option(AJUSTES[t], t)));
        tipo.value = atual;
    };
    valor.addEventListener('input', atualizarAjuste);
    atualizarAjuste();
    f.form.append(resumo, campo('Valor pago (R$)', valor, 'pagamento-valor'), campo('Data do pagamento', data, 'pagamento-data'),
        campo('Conta bancária', conta, 'pagamento-conta'), ajuste, f.erro, f.botoes);
    f.painel.append(f.form);
    if (!dados.contas.length) f.falhar('Nenhuma conta bancária ativa neste perfil para registrar o pagamento.');

    const chave = crypto.randomUUID();
    f.form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        f.erro.hidden = true;
        const pago = normalizarValor(valor.value);
        if (!pago || !data.value || !conta.value) {
            f.falhar('Informe o valor pago, a data e a conta bancária.');
            return;
        }
        const corpo = { conta_bancaria_id: Number(conta.value), data_pagamento: data.value, valor_pago: pago,
            valor_executado: (executado / 100).toFixed(2) };
        if (centavos(pago) !== executado) {
            if (!tipo.value || !justificativa.value.trim()) {
                f.falhar('Classifique a diferença e escreva a justificativa.');
                return;
            }
            corpo.tipo_ajuste = tipo.value;
            corpo.justificativa = justificativa.value.trim();
        }
        f.travar();
        const { data: r, error } = await supabase.rpc('pagar_fatura', {
            p_perfil_id: contexto.perfilId, p_fatura_id: fatura.id, p_dados: corpo, p_chave: chave,
        });
        if (error) {
            if (error.hint === 'EXECUTADO_MUDOU') {  // compra entrou ou saiu: mostra o total novo para conferir
                const novo = await supabase.rpc('dados_pagamento_fatura', { p_perfil_id: contexto.perfilId, p_fatura_id: fatura.id });
                if (!novo.error) {
                    executado = centavos(novo.data.fatura.valor_executado);
                    totalTexto.textContent = reais(executado);
                    atualizarAjuste();
                }
            }
            f.falhar(mensagemDeErro(error));
            return;
        }
        f.fechar();
        await contexto.recarregar(`Fatura paga: ${reais(centavos(r.valor_pago))} debitados de ${r.conta_nome}. `
            + `Saldo da conta: ${reais(centavos(r.saldo_conta))}.`);
    });
}

// Estorno do pagamento vigente (identificado pelo movimento de debito). O debito original fica no historico.
function abrirEstorno(contexto, dados, pagamento) {
    const f = formulario('Estornar pagamento');
    f.salvar.textContent = 'Confirmar estorno';
    f.salvar.className = 'botao botao-perigo';
    const resumo = el('dl', 'conta-detalhe');
    linhaDetalhe(resumo, 'Fatura', `${dados.fatura.cartao_nome} · ${competenciaCurta(dados.fatura.competencia)}`);
    linhaDetalhe(resumo, 'Valor pago', reais(centavos(pagamento.valor_pago)));
    linhaDetalhe(resumo, 'Conta bancária', pagamento.conta_nome);
    linhaDetalhe(resumo, 'Data do pagamento', dataCurta(pagamento.data_pagamento));
    const motivo = el('textarea');
    motivo.rows = 2;
    motivo.maxLength = 500;
    const data = entrada('date', hojeBrasilia());
    f.form.append(resumo, campo('Motivo do estorno', motivo, 'estorno-motivo'), campo('Data do estorno', data, 'estorno-data'),
        f.erro, f.botoes);
    f.painel.append(f.form);
    const chave = crypto.randomUUID();
    f.form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        f.erro.hidden = true;
        if (!motivo.value.trim() || !data.value) {
            f.falhar('Informe o motivo e a data do estorno.');
            return;
        }
        f.travar();
        const { data: r, error } = await supabase.rpc('estornar_pagamento_fatura', {
            p_perfil_id: contexto.perfilId, p_fatura_id: dados.fatura.id, p_movimento_id: pagamento.movimento_id,
            p_dados: { motivo: motivo.value.trim(), data_estorno: data.value }, p_chave: chave,
        });
        if (error) {
            f.falhar(mensagemDeErro(error));
            return;
        }
        f.fechar();
        await contexto.recarregar(`Pagamento estornado: ${reais(centavos(r.valor_estornado))} devolvidos a ${pagamento.conta_nome}. `
            + `Saldo da conta: ${reais(centavos(r.saldo_conta))}.`);
    });
}

// Situacao do pagamento na fatura aberta: pago (com estornos anteriores) e as acoes permitidas.
async function mostrarPagamento(area, fatura, contexto) {
    const { data, error } = await supabase.rpc('dados_pagamento_fatura', { p_perfil_id: contexto.perfilId, p_fatura_id: fatura.fatura_id });
    if (error || !data) return;
    const conteudo = [];
    for (const p of data.pagamentos) {
        const ajuste = p.tipo_ajuste ? ` · ${AJUSTES[p.tipo_ajuste]}: ${p.justificativa}` : '';
        const texto = `Pago em ${dataCurta(p.data_pagamento)} · ${reais(centavos(p.valor_pago))} · ${p.conta_nome || 'conta'}${ajuste}`;
        conteudo.push(el('p', p.vigente ? 'pagamento-linha' : 'pagamento-linha pagamento-estornado', p.estorno
            ? `${texto} · estornado em ${dataCurta(p.estorno.data)}${p.estorno.motivo ? ` (${p.estorno.motivo})` : ''}` : texto));
    }
    const vigente = data.pagamentos.find((p) => p.vigente);
    if (data.pode_pagar) {
        const pagar = botao('Pagar fatura', 'botao-principal');
        pagar.addEventListener('click', () => abrirPagamento(contexto, data));
        conteudo.push(pagar);
    } else if (data.pode_estornar && vigente) {
        const estornar = botao('Estornar pagamento');
        estornar.addEventListener('click', () => abrirEstorno(contexto, data, vigente));
        conteudo.push(estornar);
    } else if (contexto.podeGerir && data.sistema === 'FLASK' && !data.fatura.paga) {
        conteudo.push(el('p', 'geracao-dica', 'O pagamento das faturas deste perfil ainda é feito no sistema atual.'));
    }
    area.replaceChildren(...conteudo);
}

function itemFatura(fatura, contexto) {
    const item = el('li', 'conta');
    item.dataset.cartaoId = String(fatura.cartao_id);
    const detalhe = el('details');
    const resumo = el('summary', 'conta-resumo');
    const principal = el('span', 'conta-principal');
    principal.append(el('span', 'conta-nome', fatura.cartao_nome),
        el('span', 'conta-vencimento', fatura.data_vencimento ? `Vence ${dataCurta(fatura.data_vencimento)}` : 'Sem fatura neste mês'));
    const lado = el('span', 'conta-lado');
    lado.append(el('span', 'conta-valor', reais(centavos(fatura.valor_previsto))),
        el('span', `situacao situacao-fatura-${fatura.situacao.toLowerCase()}`, SITUACAO[fatura.situacao] || fatura.situacao));
    resumo.append(principal, lado);
    const lista = el('dl', 'conta-detalhe');
    linhaDetalhe(lista, 'Compras', reais(centavos(fatura.valor_executado)));
    linhaDetalhe(lista, fatura.situacao === 'PAGA' ? 'Valor' : 'Previsto', reais(centavos(fatura.valor_previsto)));
    const pagamento = el('div', 'fatura-pagamento');
    const compras = el('ul', 'cartao-compras');
    detalhe.append(resumo, lista, pagamento, compras);
    let carregadas = false;
    detalhe.addEventListener('toggle', async () => {
        if (!detalhe.open || carregadas) return;
        carregadas = true;
        if (fatura.fatura_id) mostrarPagamento(pagamento, fatura, contexto);
        const { data, error } = await supabase.rpc('compras_da_fatura', {
            p_perfil_id: contexto.perfilId, p_cartao_id: fatura.cartao_id, p_mes: `${contexto.mes}-01`,
        });
        if (error) return;
        if (!data.length) compras.append(el('li', 'geracao-dica', 'Nenhuma compra nesta fatura.'));
        for (const compra of data) compras.append(itemCompra(compra, contexto));
    });
    item.append(detalhe);
    return item;
}

function abrirCartao(contexto, cartao) {
    const f = formulario(cartao ? 'Editar cartão' : 'Novo cartão');
    const nome = entrada('text', cartao ? cartao.nome : '');
    nome.maxLength = 100;
    const fechamento = entrada('number', cartao ? cartao.dia_fechamento : '');
    const vencimento = entrada('number', cartao ? cartao.dia_vencimento : '');
    for (const dia of [fechamento, vencimento]) {
        dia.min = '1';
        dia.max = '31';
    }
    const regra = seletor(REGRAS_DIA_FECHAMENTO, cartao ? cartao.compra_no_fechamento || 'PROXIMO' : 'PROXIMO');
    // Confirmacao explicita: sem ela a fatura nao e sugerida. Mudar um dia ou a regra pede nova confirmacao.
    const confirmado = entrada('checkbox');
    confirmado.checked = Boolean(cartao && cartao.fechamento_confirmado);
    confirmado.id = 'cartao-confirmado';
    const linhaConfirmado = el('label', 'form-check');
    linhaConfirmado.htmlFor = confirmado.id;
    linhaConfirmado.append(confirmado, el('span', null, 'Confirmo os dias de fechamento e vencimento conforme a administradora'));
    for (const controle of [fechamento, vencimento, regra]) {
        controle.addEventListener('change', () => { confirmado.checked = false; });
    }
    const limite = entrada('text', cartao ? formatarValor(cartao.limite_credito) : '');
    limite.inputMode = 'decimal';
    const observacoes = el('textarea');
    observacoes.rows = 2;
    observacoes.maxLength = 1000;
    observacoes.value = cartao ? cartao.observacoes || '' : '';
    f.form.append(campo('Nome', nome, 'cartao-nome'), campo('Dia de fechamento', fechamento, 'cartao-fechamento'),
        campo('Dia de vencimento', vencimento, 'cartao-vencimento'),
        campo('Compra no dia do fechamento', regra, 'cartao-regra'), linhaConfirmado,
        el('p', 'geracao-dica', 'Sem a confirmação, a fatura de cada compra não é sugerida. Dias 29 a 31 usam o último dia nos meses curtos.'),
        campo('Limite de crédito (R$)', limite, 'cartao-limite'),
        el('p', 'geracao-dica', cartao ? 'Os novos dias valem para as próximas compras e faturas; as já criadas não mudam.'
            : 'Número e código de segurança não são registrados aqui.'),
        campo('Observações', observacoes, 'cartao-observacoes'), f.erro, f.botoes);
    f.painel.append(f.form);
    const chave = crypto.randomUUID();
    f.form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        const limiteNormal = limite.value.trim() ? normalizarValor(limite.value) : '';
        if (!nome.value.trim() || !fechamento.value || !vencimento.value || limiteNormal === null) {
            f.falhar('Verifique: nome, dias de fechamento e vencimento (1 a 31) e limite.');
            return;
        }
        const dados = {
            nome: nome.value.trim(), dia_fechamento: Number(fechamento.value), dia_vencimento: Number(vencimento.value),
            limite_credito: limiteNormal || null, observacoes: observacoes.value.trim(),
            compra_no_fechamento: regra.value, fechamento_confirmado: confirmado.checked,
        };
        f.travar();
        const { error } = cartao
            ? await supabase.rpc('editar_cartao', { p_perfil_id: contexto.perfilId, p_cartao_id: cartao.id, p_versao: cartao.versao, p_dados: dados })
            : await supabase.rpc('criar_cartao', { p_perfil_id: contexto.perfilId, p_dados: dados, p_chave: chave });
        if (error) {
            f.falhar(mensagemDeErro(error));
            return;
        }
        f.fechar();
        await contexto.recarregar(cartao ? 'Cartão atualizado.' : 'Cartão cadastrado.');
    });
}

function itemCadastro(cartao, contexto) {
    const item = el('li', 'conta');
    item.dataset.cadastroId = String(cartao.id);
    const detalhe = el('details');
    const resumo = el('summary', 'conta-resumo');
    const principal = el('span', 'conta-principal');
    const dias = cartao.dia_vencimento ? `Fecha dia ${cartao.dia_fechamento} · vence dia ${cartao.dia_vencimento}` : 'Sem configuração';
    principal.append(el('span', 'conta-nome', cartao.final_numero ? `${cartao.nome} •••• ${cartao.final_numero}` : cartao.nome),
        el('span', 'conta-vencimento', dias));
    const lado = el('span', 'conta-lado');
    lado.append(el('span', `situacao situacao-fatura-${cartao.ativo ? 'aberta' : 'sem_fatura'}`, cartao.ativo ? 'Ativo' : 'Inativo'));
    if (cartao.ativo && !cartao.fechamento_confirmado) lado.append(el('span', 'cartao-aviso', 'Fechamento a confirmar'));
    resumo.append(principal, lado);
    const lista = el('dl', 'conta-detalhe');
    if (cartao.dia_vencimento) linhaDetalhe(lista, 'Compra no dia do fechamento', textoRegra(cartao.compra_no_fechamento));
    if (cartao.limite_credito !== null) linhaDetalhe(lista, 'Limite', reais(centavos(cartao.limite_credito)));
    linhaDetalhe(lista, 'Observações', cartao.observacoes);
    detalhe.append(resumo, lista);
    if (contexto.podeGerir && cartao.ativo) {
        const acoes = el('div', 'despesa-acoes');
        const confirmacao = el('div', 'despesa-confirmacao');
        const editar = botao('Editar cartão');
        editar.addEventListener('click', () => abrirCartao(contexto, cartao));
        const inativar = botao('Inativar');
        inativar.addEventListener('click', () => confirmarAcao(confirmacao,
            'Inativar o cartão? Compras e faturas continuam registradas; ele deixa de receber compras novas.',
            'Confirmar inativação',
            async () => {
                const resposta = await supabase.rpc('inativar_cartao', {
                    p_perfil_id: contexto.perfilId, p_cartao_id: cartao.id, p_versao: cartao.versao,
                });
                if (!resposta.error) await contexto.recarregar('Cartão inativado.');
                return resposta;
            }));
        acoes.append(editar, inativar);
        detalhe.append(acoes, confirmacao);
    }
    item.append(detalhe);
    return item;
}

function limpar() {
    for (const id of ['totais', 'cartoes-nota', 'faturas-erro', 'faturas-vazio', 'secao-faturas', 'secao-cadastro']) {
        document.getElementById(id).hidden = true;
    }
    document.getElementById('lista-faturas').replaceChildren();
    document.getElementById('lista-cadastro').replaceChildren();
}

async function carregarMes(perfilId, mes) {
    limpar();
    const [faturas, lista, gestao] = await Promise.all([
        supabase.rpc('faturas_do_mes', { p_perfil_id: perfilId, p_mes: `${mes}-01` }),
        supabase.rpc('cartoes_do_perfil', { p_perfil_id: perfilId }),
        supabase.rpc('pode_gerir_perfil', { p_perfil_id: perfilId }),
    ]);
    const contexto = {
        perfilId,
        mes,
        cartoes: lista.data || [],
        podeGerir: !gestao.error && gestao.data === true,
        recarregar: async (mensagem) => {
            const aviso = document.getElementById('acao-resultado');
            aviso.textContent = mensagem;
            aviso.hidden = false;
            await carregarMes(perfilId, mes);
        },
    };
    const acoes = document.getElementById('acoes-mes');
    acoes.replaceChildren();
    document.getElementById('cartao-painel').hidden = true;
    document.getElementById('cartao-painel').replaceChildren();
    if (faturas.error || lista.error) {
        const erro = document.getElementById('faturas-erro');
        erro.textContent = 'Perfil não autorizado ou indisponível.';
        erro.hidden = false;
        return;
    }
    if (contexto.podeGerir) {
        if (contexto.cartoes.some((c) => c.ativo && c.dia_vencimento)) {
            const nova = botao('Nova compra', 'botao-principal');
            nova.id = 'nova-compra';
            nova.addEventListener('click', () => abrirNovaCompra({
                ...contexto, cartoes: contexto.cartoes.filter((c) => c.dia_vencimento),
            }));
            acoes.append(nova);
        }
        const novo = botao('Novo cartão');
        novo.id = 'novo-cartao';
        novo.addEventListener('click', () => abrirCartao(contexto, null));
        acoes.append(novo);
    }
    const dados = faturas.data || [];
    document.getElementById('total-executado').textContent = reais(dados.reduce((s, f) => s + centavos(f.valor_executado), 0));
    document.getElementById('total-previsto').textContent = reais(dados.reduce((s, f) => s + centavos(f.valor_previsto), 0));
    document.getElementById('totais').hidden = false;
    document.getElementById('cartoes-nota').hidden = false;
    if (!dados.length) {
        document.getElementById('faturas-vazio').hidden = false;
    } else {
        const destino = document.getElementById('lista-faturas');
        for (const fatura of dados) destino.append(itemFatura(fatura, contexto));
        document.getElementById('secao-faturas').hidden = false;
    }
    if (contexto.cartoes.length) {
        const destino = document.getElementById('lista-cadastro');
        for (const cartao of contexto.cartoes) destino.append(itemCadastro(cartao, contexto));
        document.getElementById('secao-cadastro').hidden = false;
    }
}

const parametro = new URLSearchParams(window.location.search).get('mes');
const mes = MES_VALIDO.test(parametro || '') ? parametro : mesAtualBrasilia();
document.getElementById('mes-titulo').textContent = tituloDoMes(mes);
document.getElementById('mes-anterior').href = `cartoes.html?mes=${deslocarMes(mes, -1)}`;
document.getElementById('mes-proximo').href = `cartoes.html?mes=${deslocarMes(mes, 1)}`;
// FIN-MIGRACAO-FIDELIDADE-FASE-1: sessao, menu e perfil ficam na moldura do Flask. Trocar de perfil
// recarrega a pagina (como no Flask): nada do perfil anterior permanece na tela.
const contexto = await iniciarMoldura();
if (contexto?.perfil) await carregarMes(contexto.perfil.id, mes);
