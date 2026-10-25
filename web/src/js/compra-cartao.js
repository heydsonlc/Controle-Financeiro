// FIN-FIDELIDADE-CARTOES-1 — formulario de compra nova no cartao (o de FIN-CARTOES-1 e FIN-CARTOES-FECHAMENTO-1),
// aberto no modal acrescentado a tela original de Cartoes. No Flask a compra e cadastrada em Lancamentos (tela ainda
// em migracao); aqui fica o mesmo formulario que o novo aplicativo ja tinha, sem mudar nenhuma regra:
// - parcelas, centavos, fatura de destino e bloqueios sao decididos no banco; a previa (previa_compra) mostra o que
//   sera gravado;
// - a fatura da 1a parcela e sugerida pelo fechamento (sugerir_competencia, so leitura) e pode ser trocada; a escolha
//   manual nunca e sobrescrita;
// - fatura consolidada so recebe compra com a confirmacao do total visto, uma caixa por fatura (reconferida sob trava).

import { supabase } from './cliente.js';
import { botao, campo, centavos, competenciaCurta, el, entrada, normalizarValor, reais, seletor } from './comum.js';
import { confirmacoes, consolidadaDoErro, mesSemSugestao, textoConsolidada, textoSugestao } from './fechamento.js';
import { hojeBrasilia, mensagemDeErro } from './adaptador-comum.js';

let categoriasCache = null;
async function categorias() {
    if (!categoriasCache) {
        const { data, error } = await supabase.rpc('categorias_de_despesa');
        categoriasCache = error ? [] : data || [];
    }
    return categoriasCache;
}

function formulario(painel, aoFechar) {
    painel.replaceChildren();
    const form = el('form', 'despesa-form');
    form.noValidate = true;
    const erro = el('p', 'login-error');
    erro.setAttribute('role', 'alert');
    erro.hidden = true;
    const salvar = botao('Salvar', 'botao-principal');
    salvar.type = 'submit';
    const cancelar = botao('Cancelar');
    const botoes = el('div', 'geracao-botoes');
    botoes.append(salvar, cancelar);
    const fechar = () => { painel.replaceChildren(); aoFechar(); };
    cancelar.addEventListener('click', fechar);
    const falhar = (texto) => {
        erro.textContent = texto;
        erro.hidden = false;
        salvar.disabled = false;
        cancelar.disabled = false;
    };
    const travar = () => { salvar.disabled = true; cancelar.disabled = true; };
    return { form, erro, botoes, fechar, falhar, travar };
}

// Caixa de confirmacao de uma fatura consolidada (marcada so pelo usuario).
function caixaConsolidada(consolidada) {
    const caixa = entrada('checkbox');
    caixa.id = `compra-consolidada-${consolidada.fatura_id}`;
    const linha = el('label', 'form-check');
    linha.htmlFor = caixa.id;
    linha.append(caixa, el('span', null, textoConsolidada(consolidada)));
    return { linha, caixa };
}

// Previa das parcelas: calculada no banco (mesma funcao do cadastro), so leitura. O conteudo so e trocado quando a
// resposta chega (limpar antes deslocaria o botao Salvar no meio do clique).
function montarPrevia(destino, perfilId, lerDados, estado) {
    let pedido = 0;
    return async () => {
        const dados = lerDados();
        const atual = ++pedido;
        if (!dados) {
            destino.replaceChildren();
            estado.consolidadas = [];
            return;
        }
        const { data, error } = await supabase.rpc('previa_compra', { p_perfil_id: perfilId, p_dados: dados });
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
            const { linha, caixa } = caixaConsolidada(consolidada);
            conteudo.push(linha);
            consolidadas.push({ ...consolidada, caixa });
        }
        destino.replaceChildren(...conteudo);
        estado.consolidadas = consolidadas;
    };
}

// o: { painel, perfilId, cartoes (ativos com vencimento), cartaoId (pre-selecionado), mes ('AAAA-MM'),
//      aoFechar(), aoGravar(mensagem) }
export function abrirNovaCompra(o) {
    const f = formulario(o.painel, o.aoFechar);
    const inicial = o.cartoes.some((c) => c.id === o.cartaoId) ? o.cartaoId : (o.cartoes[0] || {}).id;
    const cartao = seletor(o.cartoes.map((c) => [c.id, c.nome]), inicial || '');
    const descricao = entrada('text');
    descricao.maxLength = 200;
    const valor = entrada('text');
    valor.inputMode = 'decimal';
    valor.placeholder = '0,00';
    const parcelas = entrada('number', 1);
    parcelas.min = '1';
    parcelas.max = '60';
    const dataCompra = entrada('date', hojeBrasilia());
    const mesFatura = entrada('month', o.mes);
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
    const atualizarPrevia = montarPrevia(previa, o.perfilId, lerDados, estado);
    for (const controle of [descricao, valor, parcelas, mesFatura, categoria]) {
        controle.addEventListener('change', atualizarPrevia);
    }

    // Sugestao pelo fechamento: recalculada ao trocar cartao ou data; so preenche o mes enquanto o usuario nao o escolheu.
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
                p_perfil_id: o.perfilId, p_cartao_id: Number(cartao.value), p_data_compra: dataCompra.value,
            });
            if (atual !== pedidoSugestao) return;
            sugestao = error || !data ? { situacao: 'INDISPONIVEL' } : data;
            if (!manual) {
                mesFatura.value = sugestao.situacao === 'SUGERIDA' ? sugestao.competencia.slice(0, 7)
                    : mesSemSugestao(sugestao.situacao, o.mes);
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
    o.painel.append(f.form);
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
        const { data, error } = await supabase.rpc('criar_compra', { p_perfil_id: o.perfilId, p_dados: dados, p_chave: chave });
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
        await o.aoGravar(n > 1
            ? `Compra registrada em ${n} parcelas, a partir da fatura ${competenciaCurta(data.faturas[0])}.`
            : `Compra registrada na fatura ${competenciaCurta(data.faturas[0])}.`, data.faturas[0]);
    });
}
