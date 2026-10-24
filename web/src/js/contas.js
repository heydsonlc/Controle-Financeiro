// MOBILE-CONTAS-1 — Contas do mes.
//
// Consulta: financeiro.contas_do_mes / lancamentos_da_fatura / previa_geracao,
// que revalidam o perfil no banco a cada chamada e nunca gravam (STABLE).
// FIN-RECORRENCIA-1: a unica escrita e financeiro.gerar_mes, acionada pelo botao
// "Gerar contas" e so depois da confirmacao (com o total da previa confirmada e
// as competencias desmarcadas como dispensadas). Sem baixa de debito automatico.
// FIN-DESPESAS-1: cadastro/edicao/exclusao em despesas.js, tambem so por RPC.

import { supabase } from './cliente.js';
import { carregarAcoes, mostrarAcoesDoMes } from './despesas.js';
import { mostrarMovimentos } from './movimentos.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario, sair } from './sessao.js';

const MES_VALIDO = /^\d{4}-(0[1-9]|1[0-2])$/;
const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const SITUACAO = { PAGA: 'Paga', PENDENTE: 'Pendente', VENCIDA: 'Vencida' };

function mesAtualBrasilia() {
    const partes = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit' })
        .formatToParts(new Date());
    const valor = (tipo) => partes.find((p) => p.type === tipo).value;
    return `${valor('year')}-${valor('month')}`;
}

function deslocarMes(mes, delta) {
    const [ano, m] = mes.split('-').map(Number);
    const data = new Date(Date.UTC(ano, m - 1 + delta, 1));
    return `${data.getUTCFullYear()}-${String(data.getUTCMonth() + 1).padStart(2, '0')}`;
}

function tituloDoMes(mes) {
    const [ano, m] = mes.split('-').map(Number);
    const texto = new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric', timeZone: 'UTC' })
        .format(new Date(Date.UTC(ano, m - 1, 1)));
    return texto.charAt(0).toUpperCase() + texto.slice(1);
}

function dataCurta(iso) {
    if (!iso) return '';
    const [ano, m, d] = iso.split('-');
    return `${d}/${m}/${ano}`;
}

// Soma em centavos: evita erro de ponto flutuante nos totais.
const centavos = (valor) => Math.round(Number(valor || 0) * 100);
const reais = (c) => moeda.format(c / 100);

function el(tag, classe, texto) {
    const elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto !== undefined && texto !== null) elemento.textContent = String(texto);
    return elemento;
}

function linhaDetalhe(lista, rotulo, valor) {
    if (valor === undefined || valor === null || valor === '') return;
    lista.append(el('dt', null, rotulo), el('dd', null, valor));
}

function resumoDaConta(conta, nome) {
    const resumo = el('summary', 'conta-resumo');
    const principal = el('span', 'conta-principal');
    principal.append(el('span', 'conta-nome', nome), el('span', 'conta-vencimento', `Vence ${dataCurta(conta.data_vencimento)}`));
    const lado = el('span', 'conta-lado');
    lado.append(el('span', 'conta-valor', reais(centavos(conta.valor))),
        el('span', `situacao situacao-${conta.situacao.toLowerCase()}`, SITUACAO[conta.situacao] || conta.situacao));
    resumo.append(principal, lado);
    return resumo;
}

function itemDespesa(conta, contexto) {
    const item = el('li', 'conta');
    item.dataset.contaId = String(conta.id);
    const detalhe = el('details');
    const lista = el('dl', 'conta-detalhe');
    linhaDetalhe(lista, 'Categoria', conta.categoria_nome);
    if (conta.numero_parcela && conta.total_parcelas) linhaDetalhe(lista, 'Parcela', `${conta.numero_parcela} de ${conta.total_parcelas}`);
    linhaDetalhe(lista, 'Pago em', dataCurta(conta.data_pagamento));
    if (conta.debito_automatico) linhaDetalhe(lista, 'Débito automático', 'Sim');
    const acoes = el('div', 'despesa-caixa');
    detalhe.append(resumoDaConta(conta, conta.nome), lista, acoes);
    // Acoes (editar, excluir, recorrencia) so ao abrir: o banco informa o que e permitido.
    let carregadas = false;
    detalhe.addEventListener('toggle', () => {
        if (!detalhe.open || carregadas) return;
        carregadas = true;
        carregarAcoes(acoes, conta.id, contexto);
    });
    item.append(detalhe);
    return item;
}

function itemFatura(conta, perfilId, mes) {
    const item = el('li', 'conta');
    item.dataset.contaId = String(conta.id);
    const detalhe = el('details');
    const corpo = el('div', 'conta-detalhe');
    const valores = el('dl');
    linhaDetalhe(valores, 'Previsto', reais(centavos(conta.valor_previsto)));
    linhaDetalhe(valores, 'Executado', reais(centavos(conta.valor_executado)));
    linhaDetalhe(valores, 'Pago em', dataCurta(conta.data_pagamento));
    const compras = el('ul', 'compras');
    corpo.append(valores, compras);
    // Ja agrupada sob o nome do cartao: so "Fatura mm/aaaa" da competencia (o mes exibido), nao do vencimento.
    const [ano, m] = mes.split('-');
    detalhe.append(resumoDaConta(conta, `Fatura ${m}/${ano}`), corpo);

    let carregada = false;
    detalhe.addEventListener('toggle', async () => {
        if (!detalhe.open || carregada) return;
        carregada = true;
        const { data, error } = await supabase.rpc('lancamentos_da_fatura', { p_perfil_id: perfilId, p_conta_id: conta.id });
        if (error) {
            compras.append(el('li', 'compra-erro', 'Não foi possível carregar as compras desta fatura.'));
            return;
        }
        if (!data.length) compras.append(el('li', 'compra-vazia', 'Nenhuma compra nesta fatura.'));
        for (const compra of data) {
            const linha = el('li', 'compra');
            const parcela = compra.total_parcelas > 1 ? ` (${compra.numero_parcela}/${compra.total_parcelas})` : '';
            linha.append(el('span', 'compra-descricao', `${compra.descricao}${parcela}`),
                el('span', 'compra-valor', reais(centavos(compra.valor))));
            compras.append(linha);
        }
    });
    item.append(detalhe);
    return item;
}

const competenciaCurta = (iso) => `${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
const NATUREZA = { CONTA: 'Conta', LANCAMENTO_CARTAO: 'Compra no cartão', FATURA: 'Fatura' };
const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

function botao(texto, classe) {
    const elemento = el('button', classe ? `botao ${classe}` : 'botao', texto);
    elemento.type = 'button';
    return elemento;
}

// FIN-CARTOES-RECORRENCIA-PENDENCIA-1: compra recorrente rejeitada porque a fatura de destino esta consolidada. O
// banco registra a ocorrencia; "Dispensar aviso" so reconhece o aviso (a ocorrencia continua pendente e consultavel;
// recorrencia, compras e faturas nao mudam). A identidade e recorrencia + competencia.
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

function mostrarGeracao(previa, perfilId, mes, contexto) {
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
            abrirConfirmacao(previa, perfilId, mes, () => { gerarBotao.hidden = false; });
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

function abrirConfirmacao(previa, perfilId, mes, aoCancelar) {
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
        await carregarMes(perfilId, mes);
    });
}

function limpar() {
    for (const id of ['totais', 'aviso-geracao', 'contas-erro', 'contas-vazio', 'secao-despesas', 'secao-cartoes']) {
        document.getElementById(id).hidden = true;
    }
    document.getElementById('lista-despesas').replaceChildren();
    document.getElementById('lista-cartoes').replaceChildren();
}

async function carregarMes(perfilId, mes) {
    limpar();
    const [contasResp, previaResp, pendenciasResp] = await Promise.all([
        supabase.rpc('contas_do_mes', { p_perfil_id: perfilId, p_mes: `${mes}-01` }),
        supabase.rpc('previa_geracao', { p_perfil_id: perfilId, p_mes: `${mes}-01` }),
        // FIN-CARTOES-RECORRENCIA-PENDENCIA-1 (so leitura; antes da migration a funcao nao existe: sem avisos)
        supabase.rpc('recorrencias_rejeitadas', { p_perfil_id: perfilId, p_incluir_dispensadas: true }),
    ]);
    if (contasResp.error) {
        const erro = document.getElementById('contas-erro');
        erro.textContent = 'Perfil não autorizado ou indisponível.';
        erro.hidden = false;
        return;
    }
    const contas = contasResp.data || [];
    const previa = previaResp.error ? null : previaResp.data;
    const dispensadas = new Set((pendenciasResp.error ? [] : pendenciasResp.data || [])
        .filter((p) => p.aviso_dispensado_em).map((p) => chavePendencia(p.item_id, p.competencia)));
    const contexto = {
        perfilId,
        mes,
        dispensadas,
        recarregar: async (mensagem) => {
            const aviso = document.getElementById('acao-resultado');
            aviso.textContent = mensagem;
            aviso.hidden = false;
            await carregarMes(perfilId, mes);
        },
    };
    mostrarAcoesDoMes(contexto, Boolean(previa && previa.pode_gerir));
    mostrarGeracao(previa, perfilId, mes, contexto);
    mostrarMovimentos(perfilId, mes);  // FIN-MOVIMENTACOES-1 (so leitura)

    // Cada conta (despesa ou fatura) entra uma unica vez; compras nunca sao somadas aqui.
    const total = contas.reduce((soma, c) => soma + centavos(c.valor), 0);
    const pago = contas.filter((c) => c.situacao === 'PAGA').reduce((soma, c) => soma + centavos(c.valor), 0);
    document.getElementById('total-mes').textContent = reais(total);
    document.getElementById('total-pago').textContent = reais(pago);
    document.getElementById('total-a-pagar').textContent = reais(total - pago);
    document.getElementById('totais').hidden = false;

    if (!contas.length) {
        document.getElementById('contas-vazio').hidden = false;
        return;
    }

    const despesas = contas.filter((c) => c.grupo === 'DESPESA');
    if (despesas.length) {
        const lista = document.getElementById('lista-despesas');
        for (const conta of despesas) lista.append(itemDespesa(conta, contexto));
        document.getElementById('secao-despesas').hidden = false;
    }

    const faturas = contas.filter((c) => c.grupo === 'FATURA');
    if (faturas.length) {
        const porCartao = new Map();
        for (const fatura of faturas) {
            const chave = String(fatura.cartao_id);
            if (!porCartao.has(chave)) porCartao.set(chave, { nome: fatura.cartao_nome || 'Cartão', faturas: [] });
            porCartao.get(chave).faturas.push(fatura);
        }
        const destino = document.getElementById('lista-cartoes');
        for (const [cartaoId, grupo] of porCartao) {
            const bloco = el('div', 'cartao-grupo');
            bloco.dataset.cartaoId = cartaoId;
            const lista = el('ul', 'lista-contas');
            for (const fatura of grupo.faturas) lista.append(itemFatura(fatura, perfilId, mes));
            bloco.append(el('h3', 'cartao-nome', grupo.nome), lista);
            destino.append(bloco);
        }
        document.getElementById('secao-cartoes').hidden = false;
    }
}

const parametro = new URLSearchParams(window.location.search).get('mes');
const mes = MES_VALIDO.test(parametro || '') ? parametro : mesAtualBrasilia();
document.getElementById('mes-titulo').textContent = tituloDoMes(mes);
document.getElementById('mes-anterior').href = `contas.html?mes=${deslocarMes(mes, -1)}`;
document.getElementById('mes-proximo').href = `contas.html?mes=${deslocarMes(mes, 1)}`;
document.getElementById('aba-contas').href = `contas.html?mes=${mes}`;
document.getElementById('aba-receitas').href = `receitas.html?mes=${mes}`;  // FIN-RECEITAS-1
document.getElementById('aba-cartoes').href = `cartoes.html?mes=${mes}`;  // FIN-CARTOES-1

const usuario = await exigirUsuario();
if (usuario) {
    document.getElementById('usuario-email').textContent = usuario.email || '';
    document.getElementById('sair').addEventListener('click', sair);

    let perfis = [];
    try {
        perfis = await carregarPerfis();
    } catch (_erro) {
        const erro = document.getElementById('perfis-erro');
        erro.textContent = 'Não foi possível carregar os perfis financeiros.';
        erro.hidden = false;
    }
    if (!perfis.length) {
        document.getElementById('perfis-vazio').hidden = !document.getElementById('perfis-erro').hidden;
    } else {
        const seletor = document.getElementById('perfil-ativo');
        for (const perfil of perfis) {
            const opcao = el('option', null, perfil.nome);
            opcao.value = String(perfil.id);
            seletor.append(opcao);
        }
        const ativo = escolherPerfilAtivo(perfis, usuario.id);
        seletor.value = String(ativo.id);
        document.getElementById('perfil-rotulo').hidden = false;
        seletor.addEventListener('change', async () => {
            salvarPerfilAtivo(usuario.id, seletor.value);
            document.getElementById('geracao-resultado').hidden = true;
            document.getElementById('acao-resultado').hidden = true;
            await carregarMes(Number(seletor.value), mes);
        });
        await carregarMes(ativo.id, mes);
    }
}
