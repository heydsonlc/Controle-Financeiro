// FIN-FIDELIDADE-DESPESAS-1 — geracao explicita das recorrencias e avisos de recorrencia rejeitada na tela Despesas.
//
// Extraido sem mudanca de regra de contas.js (FIN-RECORRENCIA-1, T1 e PENDENCIA-1): previa_geracao mostra o que falta
// gerar; gerar_mes so grava depois da confirmacao, com o total da previa e as competencias desmarcadas dispensadas.
// No Flask a geracao acontecia ao abrir a tela; no novo aplicativo ela e sempre explicita.
import { supabase } from './cliente.js';
import { botao, el, competenciaCurta, deslocarMes, dataCurta, reais, centavos } from './comum.js';
const plural = (n, um, varios) => n + ' ' + (n === 1 ? um : varios);
const NATUREZA = { CONTA: 'Conta', LANCAMENTO_CARTAO: 'Compra no cartão', FATURA: 'Fatura' };
const chavePendencia = (itemId, competencia) => `${itemId}|${String(competencia).slice(0, 10)}`;
const porConsolidacao = (item) => item.natureza === 'LANCAMENTO_CARTAO' && /consolidada/i.test(item.motivo || '');

function avisoDispensado(item, dispensadas) {
    return porConsolidacao(item) && dispensadas.has(chavePendencia(item.item_id, item.competencia));
}

function listaNaoGerados(previa, contexto) {
    const detalhe = el('details');
    detalhe.append(el('summary', null, 'Ver itens não gerados'));
    const lista = el('ul', 'geracao-lista');
    for (const item of [...previa.rejeitados, ...previa.dispensados]) {
        const quando = item.competencia ? ` · ${competenciaCurta(item.competencia)}` : '';
        const linha = el('li', null, `${item.nome}${quando} — ${item.motivo}`);
        if (previa.rejeitados.includes(item) && porConsolidacao(item)) {
            linha.classList.add('geracao-pendencia');
            if (avisoDispensado(item, contexto.dispensadas)) {
                linha.append(el('span', 'geracao-nota', ' · aviso dispensado'));
            } else if (previa.pode_gerir) {
                const dispensar = botao('Dispensar aviso');
                dispensar.title = 'A ocorrência continua registrada; a recorrência não é cancelada.';
                dispensar.addEventListener('click', async () => {
                    dispensar.disabled = true;
                    const { error } = await supabase.rpc('dispensar_aviso_recorrencia', {
                        p_perfil_id: contexto.perfilId, p_item_id: item.item_id, p_competencia: item.competencia,
                    });
                    if (error) {
                        dispensar.disabled = false;
                        linha.append(el('span', 'login-error', ' Não foi possível dispensar o aviso.'));
                        return;
                    }
                    await contexto.recarregar('Aviso dispensado. A ocorrência continua registrada.');
                });
                linha.append(' ', dispensar);
            }
        }
        lista.append(linha);
    }
    detalhe.append(lista);
    return detalhe;
}

export function mostrarGeracao(previa, perfilId, mes, contexto) {
    const aviso = document.getElementById('aviso-geracao');
    const acoes = document.getElementById('geracao-acoes');
    const painel = document.getElementById('geracao-confirmacao');
    acoes.replaceChildren();
    painel.replaceChildren();
    painel.hidden = true;
    // Avisos ja dispensados nao contam no aviso (continuam na lista, marcados, e registrados no banco).
    const rejeitadasAtivas = previa
        ? previa.rejeitados.filter((item) => !avisoDispensado(item, contexto.dispensadas)).length : 0;
    if (!previa || (!previa.a_gerar && !rejeitadasAtivas)) {
        aviso.hidden = true;
        return;
    }
    const partes = [];
    if (previa.a_gerar) partes.push(`${plural(previa.a_gerar, 'lançamento recorrente ou fatura', 'lançamentos recorrentes ou faturas')} a gerar até ${competenciaCurta(deslocarMes(mes, 1))}`);
    if (rejeitadasAtivas) partes.push(`${plural(rejeitadasAtivas, 'item não pode', 'itens não podem')} ser gerado${rejeitadasAtivas === 1 ? '' : 's'}`);
    document.getElementById('aviso-texto').textContent = `${partes.join(' · ')}.`;

    if (previa.a_gerar && previa.pode_gerar) {
        const gerarBotao = botao('Gerar contas', 'botao-principal');
        gerarBotao.id = 'gerar-contas';
        gerarBotao.addEventListener('click', () => {
            gerarBotao.hidden = true;
            abrirConfirmacao(previa, perfilId, mes, () => { gerarBotao.hidden = false; }, contexto);
        });
        acoes.append(gerarBotao);
    } else if (previa.a_gerar) {
        // FIN-RECORRENCIA-T1: um unico gerador por perfil; o padrao continua sendo o sistema atual.
        acoes.append(el('span', 'geracao-nota', previa.pode_gerir
            ? 'A geração deste perfil ainda é feita pelo sistema atual.'
            : 'Somente quem gerencia este perfil pode gerar.'));
    }
    if (previa.rejeitadas || previa.dispensadas) acoes.append(listaNaoGerados(previa, contexto));
    aviso.hidden = false;
}

function abrirConfirmacao(previa, perfilId, mes, aoCancelar, contexto) {
    const painel = document.getElementById('geracao-confirmacao');
    painel.replaceChildren();
    const competencias = previa.competencias.map(competenciaCurta);
    painel.append(
        el('h2', 'geracao-titulo', 'Confirmar geração'),
        el('p', null, `${plural(previa.a_gerar, 'registro', 'registros')} em ${plural(competencias.length, 'competência', 'competências')}: ${competencias.join(', ')}.`),
    );
    if (previa.extenso) {
        painel.append(el('p', 'geracao-alerta', previa.retroativo
            ? 'Inclui competências anteriores ao mês exibido (lacunas não geradas).'
            : 'Inclui mais de um mês.'));
    }
    painel.append(el('p', 'geracao-dica', 'Desmarque o que não deve ser cobrado: a competência fica registrada como dispensada e não é gerada de novo.'));

    const lista = el('ul', 'geracao-lista');
    const marcadores = [];
    for (const item of previa.itens) {
        const linha = el('li');
        const texto = `${competenciaCurta(item.competencia)} · ${item.nome} · ${NATUREZA[item.natureza]} · ${dataCurta(item.data_vencimento)} · ${reais(centavos(item.valor))}`;
        if (item.natureza === 'FATURA') {
            linha.append(el('span', null, texto));  // fatura sempre existe: nao e dispensavel
        } else {
            const rotulo = el('label');
            const caixa = el('input');
            caixa.type = 'checkbox';
            caixa.checked = true;
            marcadores.push({ caixa, item });
            rotulo.append(caixa, el('span', null, texto));
            linha.append(rotulo);
        }
        lista.append(linha);
    }
    painel.append(lista);

    const erro = el('p', 'login-error');
    erro.setAttribute('role', 'alert');
    erro.hidden = true;
    const confirmar = botao('Confirmar', 'botao-principal');
    const cancelar = botao('Cancelar');
    const botoes = el('div', 'geracao-botoes');
    botoes.append(confirmar, cancelar);
    painel.append(erro, botoes);
    painel.hidden = false;

    cancelar.addEventListener('click', () => {
        painel.replaceChildren();
        painel.hidden = true;
        aoCancelar();
    });
    confirmar.addEventListener('click', async () => {
        confirmar.disabled = true;
        cancelar.disabled = true;
        erro.hidden = true;
        const dispensar = marcadores.filter((m) => !m.caixa.checked)
            .map(({ item }) => ({ natureza: item.natureza, item_id: item.item_id, competencia: item.competencia }));
        const { data, error } = await supabase.rpc('gerar_mes', {
            p_perfil_id: perfilId, p_mes: `${mes}-01`, p_total_previsto: previa.a_gerar, p_dispensar: dispensar,
        });
        if (error) {
            erro.textContent = /previa mudou/i.test(error.message || '')
                ? 'As contas mudaram desde a prévia. Recarregue o mês e confirme de novo.'
                : 'Não foi possível gerar as contas. Nada foi gravado.';
            erro.hidden = false;
            confirmar.disabled = false;
            cancelar.disabled = false;
            return;
        }
        const resultado = document.getElementById('geracao-resultado');
        resultado.textContent = `Geração concluída: ${plural(data.criadas.total, 'criada', 'criadas')}, `
            + `${plural(data.existentes, 'já existente', 'já existentes')}, `
            + `${plural(data.dispensadas, 'dispensada', 'dispensadas')}, ${plural(data.rejeitadas, 'rejeitada', 'rejeitadas')}.`;
        resultado.hidden = false;
        await contexto.recarregar();
    });
}

