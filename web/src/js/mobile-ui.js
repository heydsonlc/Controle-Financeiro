// FIN-MVP-MOBILE-03 — elementos e painel inferior das paginas mobile, vindos de js/despesas-mobile.js (FIN-MVP-MOB-01)
// sem mudanca, para a Lista de Despesas e Cartoes usarem os mesmos. Sem innerHTML (CSP): tudo por createElement.

import { el } from './comum.js';

const $ = (id) => document.getElementById(id);
const SVG = 'http://www.w3.org/2000/svg';
export const SETA = 'M9 5l7 7-7 7';
export const FALHA_GERAL = 'Não foi possível concluir a operação. Nada foi gravado.';

// ---------------------------------------------------------------------------------------------------------------
// Elementos

export function icone(caminho, classe) {
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    if (classe) svg.setAttribute('class', classe);
    const p = document.createElementNS(SVG, 'path');
    p.setAttribute('d', caminho);
    svg.append(p);
    return svg;
}

export function botao(texto, classe = '') {
    const b = el('button', `mob-botao${classe ? ` ${classe}` : ''}`, texto);
    b.type = 'button';
    return b;
}

export function campo(rotulo, controle) {
    const caixa = el('label', 'mob-campo');
    caixa.append(el('span', null, rotulo), controle);
    return caixa;
}

export function entrada(tipo, valor, atributos = {}) {
    const input = el('input');
    input.type = tipo;
    if (valor !== undefined && valor !== null) input.value = String(valor);
    Object.entries(atributos).forEach(([k, v]) => input.setAttribute(k, v));
    return input;
}

export function seletor(opcoes, valor) {
    const select = el('select');
    for (const [chave, texto] of opcoes) {
        const opcao = el('option', null, texto);
        opcao.value = String(chave);
        select.append(opcao);
    }
    if (valor !== undefined && valor !== null) select.value = String(valor);
    return select;
}

export function texto(conteudo, classe = '') {
    return el('p', `mob-texto${classe ? ` ${classe}` : ''}`, conteudo);
}

export function mensagem() {
    const m = el('p', 'mob-mensagem');
    m.setAttribute('role', 'status');
    m.hidden = true;
    return m;
}

// O aviso de erro de um formulario some quando o usuario volta a preencher.
export function limparAoEditar(form, m) {
    form.addEventListener('input', () => { if (m.classList.contains('erro')) mostrarMensagem(m, ''); });
    form.addEventListener('change', () => { if (m.classList.contains('erro')) mostrarMensagem(m, ''); });
}

export function mostrarMensagem(m, conteudo, tipo = '') {
    m.textContent = conteudo || '';
    m.className = `mob-mensagem${tipo ? ` ${tipo}` : ''}`;
    m.hidden = !conteudo;
}

export function detalhes(pares) {
    const dl = el('dl', 'mob-detalhes');
    for (const [rotulo, valor] of pares) {
        if (valor === undefined || valor === null || valor === '') continue;
        dl.append(el('dt', null, rotulo), el('dd', null, valor));
    }
    return dl;
}

export const diaMes = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : '');

// ---------------------------------------------------------------------------------------------------------------
// Aviso da ultima operacao (acima da lista)

export function mostrarAviso(conteudo, tipo = '') {
    const aviso = $('mob-aviso');
    aviso.textContent = conteudo || '';
    aviso.className = `mob-aviso${tipo === 'erro' ? ' erro' : ''}`;
    aviso.hidden = !conteudo;
}

// ---------------------------------------------------------------------------------------------------------------
// Painel inferior (um de cada vez)

export function abrirFolha(titulo, ...conteudo) {
    $('mob-folha-titulo').textContent = titulo;
    $('mob-folha-corpo').replaceChildren(...conteudo);
    $('mob-folha-fundo').hidden = false;
    $('mob-folha-corpo').scrollTop = 0;
    $('mob-folha-fechar').focus();
}

// FIN-MVP-MOBILE-03: painel que espera uma resposta (confirmacao pedida pelo servico) registra o que fazer se for fechado
// pelo X, pelo fundo ou pelo Esc (conta como cancelar). Sem registro, fechar e como antes.
let aoFechar = null;
export function quandoFechar(funcao) {
    aoFechar = funcao;
}

export function fecharFolha() {
    $('mob-folha-fundo').hidden = true;
    $('mob-folha-corpo').replaceChildren();
    const funcao = aoFechar;
    aoFechar = null;
    if (funcao) funcao();
}

export const folhaAberta = () => !$('mob-folha-fundo').hidden;

export function prepararFolha() {
    $('mob-folha-fechar').addEventListener('click', fecharFolha);
    $('mob-folha-fundo').addEventListener('click', (evento) => { if (evento.target === $('mob-folha-fundo')) fecharFolha(); });
    document.addEventListener('keydown', (evento) => { if (evento.key === 'Escape' && folhaAberta()) fecharFolha(); });
}

// Recusa ou erro antes de abrir um formulario: painel so com a mensagem.
export function folhaDeErro(titulo, conteudo) {
    const m = mensagem();
    mostrarMensagem(m, conteudo, 'erro');
    const fechar = botao('Fechar');
    fechar.addEventListener('click', fecharFolha);
    const acoes = el('div', 'mob-acoes');
    acoes.append(fechar);
    abrirFolha(titulo, m, acoes);
}
