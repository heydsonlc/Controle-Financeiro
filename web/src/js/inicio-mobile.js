// FIN-MVP-MOB-08: pagina principal mobile. So sessao, competencia (estado local, no endereco) e atalhos.
// Nenhum dado financeiro e lido ou gravado aqui.
//
// Ativacao gradual: cada MVP mobile homologado entra em MODULOS_ATIVOS (pelo data-modulo do atalho). Atalho ativo
// ganha o link do seu destino com a competencia aberta; os demais ficam visiveis, desabilitados e sem navegar.

import { MES_VALIDO, deslocarMes, mesAtualBrasilia } from './comum.js';
import { exigirUsuario, sair } from './sessao.js';

export const MODULOS_ATIVOS = new Set([]);

const $ = (id) => document.getElementById(id);

const MESES_CURTOS = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

// Formato do mockup aprovado: "Nov/2026".
export function rotuloCompetencia(mes) {
    const [ano, m] = mes.split('-');
    return `${MESES_CURTOS[Number(m) - 1]}/${ano}`;
}

function competenciaInicial() {
    const mes = new URLSearchParams(window.location.search).get('mes');
    return MES_VALIDO.test(mes || '') ? mes : mesAtualBrasilia();
}

function aplicarCompetencia(mes) {
    $('mob-competencia').textContent = rotuloCompetencia(mes);
    $('mob-competencia').dataset.mes = mes;
    const endereco = new URL(window.location.href);
    if (endereco.searchParams.get('mes') !== mes) {
        endereco.searchParams.set('mes', mes);
        window.history.replaceState(null, '', endereco);
    }
    document.querySelector('.mob-barra-item.ativo').setAttribute('href', `inicio.html?mes=${mes}`);  // Inicio mantem o mes
    for (const atalho of document.querySelectorAll('[data-modulo][data-destino]')) {
        if (MODULOS_ATIVOS.has(atalho.dataset.modulo)) atalho.setAttribute('href', `${atalho.dataset.destino}?mes=${mes}`);
    }
}

function prepararAtalhos() {
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
function prepararMais() {
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

const usuario = await exigirUsuario();
if (usuario) {
    let mes = competenciaInicial();
    prepararAtalhos();
    prepararMais();
    aplicarCompetencia(mes);
    $('mob-mes-anterior').addEventListener('click', () => { mes = deslocarMes(mes, -1); aplicarCompetencia(mes); });
    $('mob-mes-seguinte').addEventListener('click', () => { mes = deslocarMes(mes, 1); aplicarCompetencia(mes); });
}
