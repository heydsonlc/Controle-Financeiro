// FIN-MVP-MOB-01 — partes comuns das paginas mobile (padrao do FIN-MVP-MOB-08): competencia no endereco (?mes=),
// modulos ativos, links da barra inferior e menu do "Mais" (Sair). Veio de js/inicio-mobile.js, sem mudar o comportamento.
//
// Ativacao gradual: cada MVP mobile homologado entra em MODULOS_ATIVOS (pelo data-modulo do atalho ou do item da barra).
// O item ativo ganha o link do seu data-destino com a competencia aberta; os demais ficam visiveis, desabilitados
// (aria-disabled, "Em breve" no titulo) e sem navegar.

import { MES_VALIDO, mesAtualBrasilia } from './comum.js';
import { sair } from './sessao.js';

// FIN-MVP-MOB-01: Resumo (atalho da pagina principal e item da barra) abre a Lista de Despesas mobile.
export const MODULOS_ATIVOS = new Set(['resumo']);

const $ = (id) => document.getElementById(id);

const MESES_CURTOS = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

// Formato do mockup aprovado: "Nov/2026".
export function rotuloCompetencia(mes) {
    const [ano, m] = mes.split('-');
    return `${MESES_CURTOS[Number(m) - 1]}/${ano}`;
}

export function competenciaInicial() {
    const mes = new URLSearchParams(window.location.search).get('mes');
    return MES_VALIDO.test(mes || '') ? mes : mesAtualBrasilia();
}

// Mostra a competencia, guarda no endereco (atualizar a pagina a mantem) e leva aos links: Inicio e modulos ativos
// abrem com o mesmo mes (competencia sincronizada entre as paginas).
export function aplicarCompetencia(mes) {
    $('mob-competencia').textContent = rotuloCompetencia(mes);
    $('mob-competencia').dataset.mes = mes;
    const endereco = new URL(window.location.href);
    if (endereco.searchParams.get('mes') !== mes) {
        endereco.searchParams.set('mes', mes);
        window.history.replaceState(null, '', endereco);
    }
    for (const inicio of document.querySelectorAll('[data-inicio]')) inicio.setAttribute('href', `inicio.html?mes=${mes}`);
    for (const item of document.querySelectorAll('[data-modulo][data-destino]')) {
        if (MODULOS_ATIVOS.has(item.dataset.modulo)) item.setAttribute('href', `${item.dataset.destino}?mes=${mes}`);
    }
}

export function prepararModulos() {
    for (const item of document.querySelectorAll('[data-modulo]')) {
        if (MODULOS_ATIVOS.has(item.dataset.modulo) && item.dataset.destino) {
            item.removeAttribute('aria-disabled');
            continue;
        }
        item.removeAttribute('href');
        item.setAttribute('aria-disabled', 'true');
        item.title = 'Em breve';
        item.addEventListener('click', (evento) => evento.preventDefault());
    }
}

// "Mais": menu com Sair (aprovado na homologacao de 13/11/2026); fecha com Esc, toque fora ou escolha.
export function prepararMais() {
    const botao = $('mob-mais');
    const menu = $('mob-menu-mais');
    const abrir = (aberto) => {
        menu.hidden = !aberto;
        botao.setAttribute('aria-expanded', aberto ? 'true' : 'false');
        if (aberto) $('mob-sair').focus();
    };
    botao.addEventListener('click', (evento) => { evento.stopPropagation(); abrir(menu.hidden); });
    document.addEventListener('click', (evento) => { if (!menu.hidden && !menu.contains(evento.target)) abrir(false); });
    document.addEventListener('keydown', (evento) => { if (evento.key === 'Escape' && !menu.hidden) { abrir(false); botao.focus(); } });
    $('mob-sair').addEventListener('click', async () => {
        $('mob-sair').disabled = true;
        await sair();
    });
}
