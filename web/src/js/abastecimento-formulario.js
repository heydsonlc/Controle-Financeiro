// FIN-MVP-MOBILE-06 — Abastecimento do Registrar Lancamento: o bloco "Dados do Abastecimento" da tela Lancamentos do desktop
// (js/lancamentos-abastecimento.js, FIN-MOB-ABAST-LANCAMENTOS-01) em versao mobile. A despesa e a do lancamento, com a
// categoria Combustivel (pelo codigo MOB_COMBUSTIVEL que o banco informa): conta a pagar (despesa direta, competencia do
// mes da data, como a tela Lancamentos) ou compra a vista no cartao (js/mobile-cartao.js; fatura sugerida e cartao
// fisico). Gravacao so por salvar_lancamento_abastecimento (js/abastecimento-servico.js): despesa e abastecimento numa
// transacao, validados pelas regras da Mobilidade (hodometro, combustivel do veiculo, data nao futura, repeticao).
// Litros: o banco calcula (valor total / preco por litro); a tela mostra a mesma conta antes de salvar, como o desktop, e
// depois o valor gravado. Sem regra nova; sem innerHTML (CSP).

import { el } from './comum.js';
import { hojeBrasilia } from './adaptador-comum.js';
import { responderAbastecimento } from './abastecimento-servico.js';
import { desenharConfirmacaoCompra, acoesDaConfirmacao } from './despesa-formulario.js';
import { formatarCompetencia } from './despesas-grupos.js';
import { botao, entrada, mensagem, mostrarMensagem, seletor, texto } from './mobile-ui.js';
import { blocoCartao } from './mobile-cartao.js';
import { campoComErro, erroDoServico, mostrarErros, par, perguntaConsolidada } from './mobile-formulario.js';

// Os mesmos do desktop (lancamentos-abastecimento.js): combustiveis aceitos pelo cadastro do veiculo.
const COMBUSTIVEIS = { flex: ['gasolina', 'etanol'], gasolina: ['gasolina'], etanol: ['etanol'], diesel: ['diesel'], gnv: ['gnv'] };
const ROTULOS = { gasolina: 'Gasolina', etanol: 'Etanol', diesel: 'Diesel', gnv: 'GNV', outro: 'Outro' };
const SITUACOES = { SIMULADO: 'simulado', FORA_DE_USO: 'fora de uso' };

// Exibicao dos litros como no desktop: valor total / preco por litro, tres casas, sem arredondar o que e gravado.
const litrosDe = (valor, preco) => (Number(valor) > 0 && Number(preco) > 0 ? Number(valor) / Number(preco) : null);
const formatarLitros = (litros) => (litros === null || litros === undefined ? '—'
    : `${Number(litros).toLocaleString('pt-BR', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} L`);
const km = (v) => `${Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} km`;

// opcoes: api (fila da tela), mes (competencia da pagina principal), formulario ({categoria_combustivel_id, veiculos}),
// rotuloNovo e aoRecomecar/aoConcluir (como os outros formularios). FIN-MOBILE-12: veiculoId (opcional) abre o formulario
// com o veiculo ja escolhido, quando ele esta na lista (atalho Abastecer da Mobilidade mobile); nada mais muda.
export function montarFormularioAbastecimento(container, opcoes) {
    const { api, mes, formulario } = opcoes;
    const veiculos = (formulario && formulario.veiculos) || [];
    const categoriaId = formulario && formulario.categoria_combustivel_id;
    if (!categoriaId || !veiculos.length) {
        const voltar = el('a', 'mob-botao', 'Cancelar');
        voltar.id = 'mob-cancelar';
        voltar.href = `inicio.html?mes=${mes}`;
        const acoes = el('div', 'mob-acoes');
        acoes.append(voltar);
        container.replaceChildren(texto(!categoriaId
            ? 'A categoria Combustível não foi encontrada no catálogo: o abastecimento não pode ser lançado.'
            : 'Nenhum veículo neste perfil (exceto elétricos): cadastre o veículo na Mobilidade, no desktop.'), acoes);
        return null;
    }
    let enviando = false;
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const veiculo = seletor([['', 'Selecione...'], ...veiculos.map((v) => [v.id,
        SITUACOES[v.situacao_uso] ? `${v.nome} (${SITUACOES[v.situacao_uso]})` : v.nome])],
        veiculos.some((v) => v.id === opcoes.veiculoId) ? opcoes.veiculoId : (veiculos.length === 1 ? veiculos[0].id : ''));
    const data = entrada('date', hojeBrasilia(), { max: hojeBrasilia() });
    const hodometro = entrada('number', '', { step: '0.1', min: '0', inputmode: 'decimal', placeholder: 'km' });
    const combustivel = seletor([], '');
    const preco = entrada('number', '', { step: '0.001', min: '0', inputmode: 'decimal', placeholder: '0,000' });
    const valor = entrada('number', '', { step: '0.01', min: '0', inputmode: 'decimal', placeholder: '0,00' });
    const litros = el('output', 'mob-litros', '—');
    litros.id = 'mob-litros';
    const descricao = entrada('text', '', { maxlength: '200', autocomplete: 'off' });
    let descricaoManual = false;
    const meioPagamento = seletor([['conta', 'Conta a pagar'], ['cartao', 'Cartão de crédito']], 'conta');
    const fisico = seletor([['', 'Não identificado']], '');
    const observacoes = el('textarea');
    observacoes.rows = 2;
    observacoes.maxLength = 500;
    observacoes.placeholder = 'Opcional';

    const cVeiculo = campoComErro('Veículo', veiculo, { obrigatorio: true });
    const cData = campoComErro('Data', data, { obrigatorio: true });
    const cHodometro = campoComErro('Hodômetro (km)', hodometro, { obrigatorio: true });
    const cCombustivel = campoComErro('Combustível', combustivel, { obrigatorio: true });
    const cPreco = campoComErro('Preço por litro', preco, { obrigatorio: true });
    const cValor = campoComErro('Valor total', valor, { obrigatorio: true });
    const cLitros = el('div', 'mob-campo');
    cLitros.append(el('span', null, 'Litros'), litros);
    const cDescricao = campoComErro('Descrição', descricao, { obrigatorio: true });
    const cMeio = campoComErro('Meio de pagamento', meioPagamento);
    const cFisico = campoComErro('Cartão físico', fisico);
    cFisico.hidden = true;
    const notaConta = el('span', 'mob-ajuda');
    notaConta.id = 'mob-nota-conta';

    const ehCartao = () => meioPagamento.value === 'cartao';
    const veiculoEscolhido = () => veiculos.find((v) => String(v.id) === veiculo.value) || null;

    // Cartao fisico do contrato (so o final), quando o cartao tem algum ativo; "Nao identificado" e aceito.
    let pedidoFisico = 0;
    async function carregarFisicos(cartaoId) {
        const pedido = ++pedidoFisico;
        fisico.replaceChildren(new Option('Não identificado', ''));
        cFisico.hidden = true;
        if (!cartaoId) return;
        const r = await api('GET', `/api/cartoes/${cartaoId}/vinculados`, null, responderAbastecimento);
        if (pedido !== pedidoFisico) return;
        const ativos = (r && r.success ? r.data || [] : []).filter((c) => c.situacao === 'ATIVO');
        for (const c of ativos) fisico.append(new Option(`${c.nome} •••• ${c.final}`, String(c.id)));
        cFisico.hidden = ativos.length === 0;
    }
    const bloco = blocoCartao({ api, mesPadrao: mes, valor: () => parseFloat(valor.value), descricao: () => descricao.value,
        categoria: () => String(categoriaId), ativo: ehCartao, dataExterna: data, comParcelas: false, aoTrocarCartao: carregarFisicos });

    const atualizarVeiculo = () => {
        const v = veiculoEscolhido();
        const lista = v ? (COMBUSTIVEIS[v.combustivel] || ['outro']) : [];
        const atual = combustivel.value;
        combustivel.replaceChildren(...lista.map((c) => new Option(ROTULOS[c] || c, c)));
        if (lista.includes(atual)) combustivel.value = atual;
        hodometro.placeholder = v && v.ultimo_hodometro !== null && v.ultimo_hodometro !== undefined ? `último: ${km(v.ultimo_hodometro)}` : 'km';
        if (!descricaoManual) descricao.value = v ? `Abastecimento ${v.nome}` : '';
    };
    const atualizarLitros = () => { litros.textContent = formatarLitros(litrosDe(valor.value, preco.value)); };
    const atualizarNota = () => {
        notaConta.textContent = data.value
            ? `Conta a pagar pendente na competência ${formatarCompetencia(data.value.slice(0, 7))} (mês da data), paga depois pela Lista de Despesas.`
            : '';
    };
    const ajustar = () => {
        const noCartao = ehCartao();
        bloco.elemento.hidden = !noCartao;
        notaConta.hidden = noCartao;
        if (!noCartao) cFisico.hidden = true;
    };
    veiculo.addEventListener('change', atualizarVeiculo);
    descricao.addEventListener('input', () => { descricaoManual = true; });
    for (const controle of [valor, preco]) controle.addEventListener('input', atualizarLitros);
    data.addEventListener('change', atualizarNota);
    meioPagamento.addEventListener('change', async () => {
        ajustar();
        if (ehCartao()) {
            await bloco.ativar();
            carregarFisicos(bloco.cartao.value);
        }
    });
    atualizarVeiculo();
    atualizarNota();
    ajustar();

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
    const parData = par(cData, cHodometro);
    parData.classList.add('empilha');  // < 360 px: a data inteira, sem corte
    form.append(cVeiculo, parData, par(cCombustivel, cPreco), par(cValor, cLitros), cDescricao, cMeio, notaConta,
        bloco.elemento, cFisico, campoComErro('Observações', observacoes), m, consolidada, acoes);
    form.addEventListener('input', () => {
        if (consolidada.hidden || enviando) return;
        consolidada.hidden = true;
        salvar.disabled = false;
    });
    const liberar = () => { enviando = false; salvar.disabled = false; };

    async function gravar(confirmar = null) {
        const dadosAbastecimento = { veiculo_id: Number(veiculo.value), combustivel: combustivel.value, hodometro_km: Number(hodometro.value),
            preco_litro: Number(preco.value) };
        let corpo;
        if (ehCartao()) {
            if (!cFisico.hidden && fisico.value) dadosAbastecimento.cartao_vinculado_id = Number(fisico.value);
            corpo = { tipo: 'compra', abastecimento: dadosAbastecimento, lancamento: {
                cartao_id: parseInt(bloco.cartao.value, 10), categoria_id: categoriaId, descricao: descricao.value.trim(),
                valor: parseFloat(valor.value), data_compra: data.value, mes_fatura: bloco.fatura.value, total_parcelas: 1,
                observacoes: observacoes.value.trim() } };
            if (confirmar) corpo.lancamento.confirmar_consolidadas = confirmar;
        } else {
            // Despesa direta como a tela Lancamentos: vencimento na data e competencia do mes da data.
            corpo = { tipo: 'despesa', abastecimento: dadosAbastecimento, lancamento: {
                nome: descricao.value.trim(), valor: parseFloat(valor.value), descricao: observacoes.value.trim(), categoria_id: categoriaId,
                data_vencimento: data.value, mes_competencia: data.value.slice(0, 7) } };
        }
        enviando = true;
        salvar.disabled = true;
        consolidada.hidden = true;
        mostrarMensagem(m, 'Salvando...');
        const r = await api('POST', '/api/lancamentos/abastecimento', corpo, responderAbastecimento);
        if (r && r.codigo === 'CONFIRMAR_FATURA_CONSOLIDADA') {
            enviando = false;
            mostrarMensagem(m, '');
            perguntaConsolidada(consolidada, r.faturas, {
                aoRecusar: () => {
                    consolidada.hidden = true;
                    liberar();
                    mostrarMensagem(m, 'Abastecimento não salvo: a inclusão na fatura consolidada não foi confirmada.', 'erro');
                },
                aoConfirmar: (confirmacoes) => { if (!enviando) gravar(confirmacoes); },
            });
            return;
        }
        if (!r || !r.success) {
            liberar();
            erroDoServico(m, (r && r.error) || 'Falha ao salvar. Nada foi gravado.', [[/hod[oô]metro/i, cHodometro], [/combust/i, cCombustivel],
                [/pre[cç]o/i, cPreco], [/fatura/i, bloco.cFatura], [/cart[aã]o/i, bloco.cCartao], [/valor/i, cValor], [/data/i, cData],
                [/ve[ií]culo/i, cVeiculo], [/descri|nome/i, cDescricao]]);
            return;
        }
        desenharConfirmacao(container, opcoes, corpo, r.data || {}, veiculoEscolhido(), bloco.nomeCartao());
    }

    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (enviando || !consolidada.hidden) return;
        for (const c of form.querySelectorAll('.mob-campo')) if (c.erro) c.erro('');
        mostrarMensagem(m, '');
        // As validacoes do bloco do desktop (veiculo, combustivel, hodometro e preco) e as da despesa, junto ao campo;
        // hodometro, combustivel do veiculo, data e repeticao sao conferidos de novo no banco.
        const erros = [];
        if (!veiculo.value) erros.push([cVeiculo, 'Selecione o veículo.']);
        if (!data.value) erros.push([cData, 'Informe a data do abastecimento.']);
        if (hodometro.value === '' || !(Number(hodometro.value) >= 0)) erros.push([cHodometro, 'Informe o hodômetro.']);
        if (!combustivel.value) erros.push([cCombustivel, 'Selecione o combustível.']);
        if (!(Number(preco.value) > 0)) erros.push([cPreco, 'Informe o preço por litro.']);
        if (!(parseFloat(valor.value) > 0)) erros.push([cValor, 'Informe o valor total.']);
        if (!descricao.value.trim()) erros.push([cDescricao, 'Informe a descrição.']);
        if (ehCartao()) erros.push(...bloco.validar());
        if (mostrarErros(erros)) return;
        await gravar();
    });
    container.replaceChildren(form);
    veiculo.focus();
    return form;
}

// Depois de salvar: o abastecimento gravado (litros do banco) e onde a despesa ficou.
function desenharConfirmacao(container, opcoes, corpo, data, v, nomeCartao) {
    const a = data.abastecimento || {};
    const resumo = `${v ? v.nome : 'Veículo'} · ${km(a.hodometro_km ?? corpo.abastecimento.hodometro_km)} · ${formatarLitros(a.litros)} de `
        + `${ROTULOS[a.combustivel || corpo.abastecimento.combustivel] || ''} a ${Number(a.preco_litro ?? corpo.abastecimento.preco_litro)
            .toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 3 })}/L`;
    if (corpo.tipo === 'compra') {
        desenharConfirmacaoCompra(container, opcoes, { ...corpo.lancamento, total_parcelas: 1 }, nomeCartao,
            (data.compra && data.compra.faturas) || [`${corpo.lancamento.mes_fatura}-01`],
            `Abastecimento registrado no veículo: ${resumo}. A compra entra na fatura do cartão (sem conta a pagar separada).`);
        container.querySelector('.mob-confirmacao-titulo').textContent = `“${corpo.lancamento.descricao}” registrado`;
        return;
    }
    const mes = corpo.lancamento.mes_competencia;
    const caixa = el('div', 'mob-confirmacao');
    caixa.id = 'mob-confirmacao';
    const lista = el('a', 'mob-botao primario', 'Ver na Lista de Despesas');
    lista.id = 'mob-ver-lista';
    lista.href = `despesas-mobile.html?mes=${mes}`;
    caixa.append(el('p', 'mob-confirmacao-titulo', `“${corpo.lancamento.nome}” registrado`),
        texto(`Abastecimento registrado no veículo: ${resumo}.`),
        texto(`Conta a pagar de ${Number(corpo.lancamento.valor).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })} na competência `
            + `${formatarCompetencia(mes)}, paga depois pela Lista de Despesas.`, 'discreto'),
        acoesDaConfirmacao(container, opcoes, lista));
    container.replaceChildren(caixa);
    if (opcoes.aoConcluir) opcoes.aoConcluir();
}
