// FIN-MVP-MOBILE-06 — bloco "Cartao de credito" dos formularios mobile, extraido da Nova Despesa (FIN-MVP-MOBILE-05,
// homologada) para servir a Nova Despesa, a Compra no cartao e o Abastecimento do Registrar Lancamento sem duplicar: a
// compra da tela Lancamentos do desktop (cartao ativo, data da compra, parcelas, fatura sugerida pelo fechamento e previa
// do parcelamento). Leituras so pelo servico comum (js/compras-servico.js); a gravacao fica com quem usa o bloco.
// Sem regra financeira; sem innerHTML (CSP).

import { el } from './comum.js';
import { hojeBrasilia } from './adaptador-comum.js';
import { responderCompras } from './compras-servico.js';
import { mesSemSugestao, textoSugestao } from './fechamento.js';
import { botao, entrada, seletor } from './mobile-ui.js';
import { campoComErro, mesAno, moeda, par } from './mobile-formulario.js';

let cartoesLidos = null;  // cartoes ativos do perfil, lidos uma vez por pagina

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

// opcoes: api (fila da tela), mesPadrao (competencia da pagina principal), valor/descricao/categoria (leitura dos campos
// da tela), ativo() (o bloco esta em uso), dataExterna (o campo de data da tela, quando a data da compra e a dela) e
// comParcelas (a vista quando false: compra com abastecimento).
// rotulos (FIN-MVP-CADASTRO-UNIFICADO-01): textos dos campos Cartao e Fatura, quando a tela usa outros (o resto nao muda).
export function blocoCartao({ api, mesPadrao, valor, descricao, categoria, ativo, dataExterna = null, comParcelas = true, aoTrocarCartao = null,
    rotulos = {} }) {
    const cartao = seletor([['', 'Selecione...']], '');
    const dataCompra = dataExterna || entrada('date', hojeBrasilia());
    const parcelas = entrada('number', '1', { min: '1', max: '48', step: '1', inputmode: 'numeric' });
    const fatura = entrada('month', '');
    const cCartao = campoComErro(rotulos.cartao || 'Cartão', cartao, { obrigatorio: true });
    const cDataCompra = dataExterna ? null : campoComErro('Data da compra', dataCompra, { obrigatorio: true });
    const cParcelas = comParcelas ? campoComErro('Parcelas', parcelas) : null;
    const cFatura = campoComErro(rotulos.fatura || 'Fatura', fatura, { obrigatorio: true });

    const elemento = el('div', 'mob-cartao');
    elemento.id = 'mob-cartao';
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
    elemento.append(cDataCompra ? par(cCartao, cDataCompra) : cCartao, cParcelas ? par(cParcelas, cFatura) : cFatura, linhaSugestao, previa);

    // Fatura sugerida pelo fechamento (como na tela Lancamentos): nunca sobrescreve o mes escolhido pelo usuario.
    const sug = { manual: false, sugerida: null, resposta: null, pedido: 0 };
    const mostrarSugestao = () => {
        const { texto: t, alerta } = textoSugestao(sug.resposta, { manual: sug.manual, escolhido: fatura.value });
        sugestao.textContent = t;
        sugestao.classList.toggle('alerta', alerta);
        linhaSugestao.hidden = !t;
        usarSugerida.hidden = !(sug.sugerida && sug.manual && fatura.value !== sug.sugerida);
    };
    let temporizador = null;
    let pedidoPrevia = 0;
    const agendarPrevia = () => {
        clearTimeout(temporizador);
        temporizador = setTimeout(async () => {
            const pedido = ++pedidoPrevia;
            const n = Number.parseInt(parcelas.value, 10);
            const v = valor();
            if (!comParcelas || !ativo() || !(n >= 2) || !(v > 0) || !cartao.value || !dataCompra.value || !/^\d{4}-\d{2}$/.test(fatura.value)) {
                previa.hidden = true;
                previa.replaceChildren();
                return;
            }
            const q = new URLSearchParams({ cartao_id: cartao.value, valor: v.toFixed(2), total_parcelas: String(n),
                data_compra: dataCompra.value, mes_fatura: `${fatura.value}-01`, descricao: descricao(), categoria_id: categoria() });
            const r = await api('GET', `/api/lancamentos/previa-parcelas?${q}`, null, responderCompras);
            if (pedido !== pedidoPrevia) return;
            if (r && r.success && r.data && Array.isArray(r.data.parcelas)) desenharPrevia(previa, r.data);
            else {
                previa.replaceChildren(el('span', 'mob-ajuda alerta', (r && r.error) || 'Não foi possível montar a prévia das parcelas.'));
                previa.hidden = false;
            }
        }, 300);
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
            fatura.value = mesSemSugestao(sug.resposta.situacao, mesPadrao);
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
    cartao.addEventListener('change', () => { atualizarSugestao(); if (aoTrocarCartao) aoTrocarCartao(cartao.value); });
    dataCompra.addEventListener('change', atualizarSugestao);
    for (const controle of [parcelas, fatura]) controle.addEventListener('input', agendarPrevia);

    // Primeira vez em uso: os cartoes ativos do perfil (um so ja vem escolhido).
    async function ativar() {
        if (!cartoesLidos) {
            const r = await api('GET', '/api/cartoes', null, responderCompras);
            if (!Array.isArray(r)) { cCartao.erro('Não foi possível carregar os cartões.'); return; }
            cartoesLidos = r;
        }
        if (cartao.options.length === 1) {
            for (const c of cartoesLidos) cartao.append(new Option(c.nome, String(c.id)));
            if (!cartoesLidos.length) cCartao.erro('Nenhum cartão ativo neste perfil: cadastre o cartão no desktop.');
            if (cartoesLidos.length === 1) {
                cartao.value = String(cartoesLidos[0].id);
                if (aoTrocarCartao) aoTrocarCartao(cartao.value);
            }
        }
        if (cartao.value && !sug.resposta) atualizarSugestao();
        agendarPrevia();
    }

    // Validacoes do formulario do desktop para a compra, junto ao campo (a data externa e validada pela tela).
    function validar() {
        const erros = [];
        const n = Number(parcelas.value);
        if (!cartao.value) erros.push([cCartao, 'Selecione o cartão.']);
        if (cDataCompra && !dataCompra.value) erros.push([cDataCompra, 'Informe a data da compra.']);
        if (cParcelas && !(Number.isInteger(n) && n >= 1 && n <= 48)) erros.push([cParcelas, 'Parcelas: de 1 a 48.']);
        if (!/^\d{4}-\d{2}$/.test(fatura.value)) erros.push([cFatura, 'Escolha o mês da fatura.']);
        return erros;
    }

    return {
        elemento, cartao, dataCompra, parcelas, fatura, cCartao, cDataCompra, cParcelas, cFatura, linhaSugestao, previa,
        ativar, validar, agendarPrevia, atualizarSugestao,
        totalParcelas: () => (comParcelas ? parseInt(parcelas.value, 10) || 1 : 1),
        nomeCartao: () => (cartao.selectedOptions[0] && cartao.value ? cartao.selectedOptions[0].textContent : ''),
        // Erro do servico de compra junto ao campo do cartao que ele cita.
        paresDeErro: () => [[/fatura/i, cFatura], ...(cParcelas ? [[/parcela/i, cParcelas]] : []), [/cart[aã]o/i, cCartao],
            ...(cDataCompra ? [[/data/i, cDataCompra]] : [])],
    };
}
