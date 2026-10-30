// FIN-FIDELIDADE-DESPESAS-1 — geracao das recorrencias e avisos de recorrencia rejeitada na tela Despesas.
//
// FIN-RECORRENCIAS-AUTOMATICAS-1: como no Flask (lazy generation de GET /api/despesas?mes_referencia=...), a consulta
// do mes gera, sem confirmacao, o que falta ate o mes seguinte (lacunas incluidas) pelo mesmo motor do banco:
// previa_geracao diz o que falta e gerar_mes grava com o total dessa previa (se outra aba gerou no meio, o banco
// recusa a previa velha e a geracao refaz a previa). O banco continua decidindo permissao, gerador do perfil
// (Flask/novo), existentes, dispensadas e rejeitadas; nada e dispensado por aqui. Duas consultas na mesma aba nao
// geram ao mesmo tempo (ponte-api.js atende uma de cada vez, em ordem); entre abas, a trava do banco serializa.
import { supabase } from './cliente.js';
import { botao, el, competenciaCurta, deslocarMes } from './comum.js';
const plural = (n, um, varios) => n + ' ' + (n === 1 ? um : varios);
const chavePendencia = (itemId, competencia) => `${itemId}|${String(competencia).slice(0, 10)}`;
const porConsolidacao = (item) => item.natureza === 'LANCAMENTO_CARTAO' && /consolidada/i.test(item.motivo || '');
const TENTATIVAS = 3;

async function previaDe(perfilId, mes) {
    const { data, error } = await supabase.rpc('previa_geracao', { p_perfil_id: perfilId, p_mes: `${mes}-01` });
    return error ? null : data;
}

// Resultado: { previa (depois da geracao), criadas, falhou }. Nunca rejeita: a falha so vira aviso na tela.
export async function gerarRecorrencias(perfilId, mes) {
    let criadas = 0;
    for (let vez = 1; ; vez += 1) {
        const previa = await previaDe(perfilId, mes);
        if (!previa) return { previa: null, criadas, falhou: true };
        if (!previa.pode_gerar || !previa.a_gerar) return { previa, criadas, falhou: false };
        if (vez > TENTATIVAS) return { previa, criadas, falhou: true };
        const { data, error } = await supabase.rpc('gerar_mes', {
            p_perfil_id: perfilId, p_mes: `${mes}-01`, p_total_previsto: previa.a_gerar, p_dispensar: [],
        });
        if (error && !/previa mudou/i.test(error.message || '')) return { previa, criadas, falhou: true };
        if (!error) criadas += data.criadas.total;
    }
}

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

// geracao: resultado de gerarRecorrencias, com a previa ja sem os cartoes marcados como recorrencia.
export function mostrarGeracao(geracao, mes, contexto) {
    const { previa, criadas, falhou } = geracao;
    const aviso = document.getElementById('aviso-geracao');
    const acoes = document.getElementById('geracao-acoes');
    acoes.replaceChildren();
    if (criadas) {
        const resultado = document.getElementById('geracao-resultado');
        resultado.textContent = `${plural(criadas, 'lançamento recorrente ou fatura gerado', 'lançamentos recorrentes ou faturas gerados')} `
            + `automaticamente até ${competenciaCurta(deslocarMes(mes, 1))}.`;
        resultado.hidden = false;
    }
    // Avisos ja dispensados nao contam no aviso (continuam na lista, marcados, e registrados no banco).
    const rejeitadasAtivas = previa
        ? previa.rejeitados.filter((item) => !avisoDispensado(item, contexto.dispensadas)).length : 0;
    // So sobra "a gerar" quando este perfil nao gera aqui (Flask ou somente leitura) ou quando a geracao falhou.
    const pendentes = previa ? previa.a_gerar : 0;
    if (!falhou && !pendentes && !rejeitadasAtivas) {
        document.getElementById('aviso-texto').textContent = '';
        aviso.hidden = true;
        return;
    }
    const partes = [];
    if (falhou) partes.push('Não foi possível gerar as recorrências deste mês agora; as despesas já registradas estão na lista');
    else if (pendentes) partes.push(`${plural(pendentes, 'lançamento recorrente ou fatura', 'lançamentos recorrentes ou faturas')} a gerar até ${competenciaCurta(deslocarMes(mes, 1))}`);
    if (rejeitadasAtivas) partes.push(`${plural(rejeitadasAtivas, 'item não pode', 'itens não podem')} ser gerado${rejeitadasAtivas === 1 ? '' : 's'}`);
    document.getElementById('aviso-texto').textContent = `${partes.join(' · ')}.`;

    if (falhou) {
        acoes.append(el('span', 'geracao-nota', 'Recarregue a página para tentar de novo. Nada foi gravado pela tentativa que falhou.'));
    } else if (pendentes) {
        // FIN-RECORRENCIA-T1: um unico gerador por perfil (padrao: nenhum no novo aplicativo; FIN-MIGRACAO-P0P1-01).
        acoes.append(el('span', 'geracao-nota', previa.pode_gerir
            ? 'A geração de recorrências deste perfil ainda não está habilitada no novo aplicativo.'
            : 'Somente quem gerencia este perfil pode gerar.'));
    }
    if (previa && (previa.rejeitadas || previa.dispensadas)) acoes.append(listaNaoGerados(previa, contexto));
    aviso.hidden = false;
}
