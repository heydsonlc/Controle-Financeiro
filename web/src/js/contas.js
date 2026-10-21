// MOBILE-CONTAS-1 — Contas do mes (somente leitura).
//
// Dados vem de financeiro.contas_do_mes / lancamentos_da_fatura /
// mes_pode_estar_incompleto, que revalidam o perfil no banco a cada chamada e
// nunca gravam (funcoes STABLE). Sem geracao de recorrencias e sem baixa de
// debito automatico: a tela mostra o que esta registrado.

import { supabase } from './cliente.js';
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

function itemDespesa(conta) {
    const item = el('li', 'conta');
    item.dataset.contaId = String(conta.id);
    const detalhe = el('details');
    const lista = el('dl', 'conta-detalhe');
    linhaDetalhe(lista, 'Categoria', conta.categoria_nome);
    if (conta.numero_parcela && conta.total_parcelas) linhaDetalhe(lista, 'Parcela', `${conta.numero_parcela} de ${conta.total_parcelas}`);
    linhaDetalhe(lista, 'Pago em', dataCurta(conta.data_pagamento));
    if (conta.debito_automatico) linhaDetalhe(lista, 'Débito automático', 'Sim');
    detalhe.append(resumoDaConta(conta, conta.nome), lista);
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

function limpar() {
    for (const id of ['totais', 'aviso-geracao', 'contas-erro', 'contas-vazio', 'secao-despesas', 'secao-cartoes']) {
        document.getElementById(id).hidden = true;
    }
    document.getElementById('lista-despesas').replaceChildren();
    document.getElementById('lista-cartoes').replaceChildren();
}

async function carregarMes(perfilId, mes) {
    limpar();
    const [contasResp, avisoResp] = await Promise.all([
        supabase.rpc('contas_do_mes', { p_perfil_id: perfilId, p_mes: `${mes}-01` }),
        supabase.rpc('mes_pode_estar_incompleto', { p_perfil_id: perfilId, p_mes: `${mes}-01` }),
    ]);
    if (contasResp.error) {
        const erro = document.getElementById('contas-erro');
        erro.textContent = 'Perfil não autorizado ou indisponível.';
        erro.hidden = false;
        return;
    }
    const contas = contasResp.data || [];
    document.getElementById('aviso-geracao').hidden = avisoResp.error ? true : !avisoResp.data;

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
        for (const conta of despesas) lista.append(itemDespesa(conta));
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
            await carregarMes(Number(seletor.value), mes);
        });
        await carregarMes(ativo.id, mes);
    }
}
