// FIN-MVP-MOB-01 — partes comuns das paginas mobile (padrao do FIN-MVP-MOB-08): competencia no endereco (?mes=),
// modulos ativos, links da barra inferior e menu do "Mais" (Sair). Veio de js/inicio-mobile.js, sem mudar o comportamento.
//
// Ativacao gradual: cada MVP mobile homologado entra em MODULOS_ATIVOS (pelo data-modulo do atalho ou do item da barra).
// O item ativo ganha o link do seu data-destino com a competencia aberta; os demais ficam visiveis, desabilitados
// (aria-disabled, "Em breve" no titulo) e sem navegar.

import { MES_VALIDO, mesAtualBrasilia } from './comum.js';
import { carregarPerfis, escolherPerfilAtivo, podeGerirPerfil } from './perfil.js';
import { sair } from './sessao.js';

// FIN-MVP-MOB-01: Resumo (atalho da pagina principal e item da barra) abre a Lista de Despesas mobile.
// FIN-MVP-MOBILE-03: o atalho Cartoes abre os Cartoes mobile (sem item novo na barra).
// FIN-MVP-MOBILE-04: o atalho Receita abre as Receitas mobile (sem item novo na barra).
// FIN-MVP-MOBILE-05: o atalho Despesa abre a Nova Despesa mobile (cadastro rapido).
// FIN-MVP-MOBILE-06: o atalho Lancamento e o Lancar da barra abrem a mesma pagina, Registrar Lancamento.
// FIN-MVP-MOBILE-07: o atalho Contas abre as Contas mobile (sem item novo na barra).
// FIN-MVP-MOBILE-08: o atalho Pagamentos abre os Pagamentos mobile (sem item novo na barra; quem so le consulta).
// FIN-MVP-MOBILE-09: o atalho Recorrencias abre as Recorrencias mobile (sem item novo na barra; quem so le consulta).
export const MODULOS_ATIVOS = new Set(['resumo', 'cartoes', 'receita', 'despesa', 'lancamento', 'lancar', 'contas', 'pagamentos',
    'recorrencias']);

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

// FIN-MVP-MOBILE-05: modulo ativo que o perfil nao permite (cadastro em perfil somente leitura): visivel, desabilitado,
// sem destino (aplicarCompetencia nao lhe devolve o link) e com o motivo no titulo.
export function desabilitarModulo(modulo, motivo) {
    for (const item of document.querySelectorAll(`[data-modulo="${modulo}"]`)) {
        item.removeAttribute('href');
        item.removeAttribute('data-destino');
        item.setAttribute('aria-disabled', 'true');
        item.title = motivo;
        item.addEventListener('click', (evento) => evento.preventDefault());
    }
}

// FIN-MVP-MOBILE-06: atalhos e itens de cadastro (Despesa, Lancamento e o Lancar da barra) so para quem gere o perfil
// ativo (a permissao do banco, pela mesma pode_gerir_perfil). E so apresentacao: as paginas de cadastro e o banco recusam.
// Devolve true (gere), false (so le) ou null (sem perfil ou falha na consulta: os itens ficam como estao).
export const MODULOS_DE_CADASTRO = ['despesa', 'lancamento', 'lancar'];
export async function ajustarCadastrosPelaPermissao(usuarioId) {
    try {
        const perfil = escolherPerfilAtivo(await carregarPerfis(), usuarioId);
        if (!perfil) return null;
        if (await podeGerirPerfil(perfil.id)) return true;
        for (const modulo of MODULOS_DE_CADASTRO) desabilitarModulo(modulo, 'Somente leitura neste perfil');
        return false;
    } catch (erro) {
        console.error('Mobile: permissao do perfil', erro);
        return null;
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
