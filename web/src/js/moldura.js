// Moldura do Flask (FIN-MIGRACAO-FIDELIDADE-FASE-1): barra lateral, barra superior e seletor de perfil.
//
// Porta o comportamento de frontend/static/js/contexto_financeiro.js sobre financeiro.meus_perfis():
// mesmo gatilho, mesmas opcoes e, ao trocar de perfil, a pagina recarrega (como no Flask), entao
// nada do perfil anterior fica na tela. Diferencas do original:
// - o botao de menu abre e fecha a barra lateral no celular (no Flask ele nao fazia nada);
// - Alertas mostra que a funcao esta em migracao, em vez de nao responder;
// - o menu de perfis mostra a conta conectada e marca os perfis "somente leitura" (usuario,
//   perfil e permissao sao conceitos distintos);
// - links das telas por competencia (Despesas, Receitas, Cartoes) mantem o mes aberto.
// Elementos criados por DOM (sem innerHTML) e cor so por CSSOM: a CSP usa style-src 'self'.

import { MES_VALIDO } from './comum.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario, sair } from './sessao.js';

const CELULAR = '(max-width: 768px)';
const COR_VALIDA = /^#[0-9A-Fa-f]{6}$/;
const PAGINAS_POR_COMPETENCIA = new Set(['contas.html', 'receitas.html', 'cartoes.html']);

const estado = { usuario: null, perfis: [], ativo: null };
const $ = (id) => document.getElementById(id);

export function tipoLabel(tipo) {
    const valor = String(tipo || '').toUpperCase();
    if (valor === 'PESSOAL') return 'Pessoal';
    if (valor === 'EMPRESA') return 'Empresa';
    return 'Perfil financeiro';
}

export function iniciais(perfil) {
    if (perfil?.avatar) return String(perfil.avatar).slice(0, 3).toUpperCase();
    const partes = String(perfil?.nome || 'PF').trim().split(/\s+/).filter(Boolean);
    if (!partes.length) return 'PF';
    if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
    return `${partes[0][0]}${partes[1][0]}`.toUpperCase();
}

export function definirCor(elemento, propriedade, cor) {
    elemento.style.setProperty(propriedade, COR_VALIDA.test(cor || '') ? cor : '#2563eb');
}

function abrirMenu(aberto) {
    document.body.classList.toggle('app-menu-aberto', aberto);
    document.querySelector('.app-menu-button').setAttribute('aria-expanded', aberto ? 'true' : 'false');
    if (aberto) document.querySelector('.app-sidebar .app-nav-link.active, .app-sidebar .app-nav-link')?.focus();
}

function ligarMenu() {
    const botao = document.querySelector('.app-menu-button');
    botao.addEventListener('click', () => {
        if (window.matchMedia(CELULAR).matches) abrirMenu(!document.body.classList.contains('app-menu-aberto'));
    });
    $('app-menu-fundo').addEventListener('click', () => abrirMenu(false));
    for (const link of document.querySelectorAll('.app-sidebar a')) link.addEventListener('click', () => abrirMenu(false));
    window.matchMedia(CELULAR).addEventListener('change', (evento) => { if (!evento.matches) abrirMenu(false); });
}

function manterCompetencia() {
    const mes = new URLSearchParams(window.location.search).get('mes');
    if (!MES_VALIDO.test(mes || '')) return;
    for (const link of document.querySelectorAll('.app-sidebar a.app-nav-link')) {
        const destino = link.getAttribute('href');
        if (PAGINAS_POR_COMPETENCIA.has(destino)) link.setAttribute('href', `${destino}?mes=${mes}`);
    }
}

function abrirAlertas(aberto) {
    $('app-alertas-aviso').hidden = !aberto;
    $('app-alertas-button').setAttribute('aria-expanded', aberto ? 'true' : 'false');
}

function abrirSeletor(aberto) {
    $('perfil-financeiro-switcher').classList.toggle('open', aberto);
    $('perfil-financeiro-trigger').setAttribute('aria-expanded', aberto ? 'true' : 'false');
}

function ligarTopbar() {
    $('app-logout-button').addEventListener('click', sair);
    $('app-alertas-button').addEventListener('click', (evento) => {
        evento.stopPropagation();
        abrirSeletor(false);
        abrirAlertas($('app-alertas-aviso').hidden);
    });
    $('perfil-financeiro-trigger').addEventListener('click', (evento) => {
        evento.stopPropagation();
        abrirAlertas(false);
        abrirSeletor(!$('perfil-financeiro-switcher').classList.contains('open'));
    });
    $('perfil-financeiro-options').addEventListener('click', (evento) => {
        const opcao = evento.target.closest('.perfil-financeiro-option');
        if (!opcao) return;
        evento.stopPropagation();
        if (String(estado.ativo?.id) === opcao.dataset.perfilId) {
            abrirSeletor(false);
            return;
        }
        opcao.disabled = true;
        salvarPerfilAtivo(estado.usuario.id, opcao.dataset.perfilId);
        window.location.reload();
    });
    document.addEventListener('click', (evento) => {
        if (!evento.target.closest('#perfil-financeiro-menu')) abrirSeletor(false);
        abrirAlertas(false);
    });
    document.addEventListener('keydown', (evento) => {
        if (evento.key !== 'Escape') return;
        abrirSeletor(false);
        abrirAlertas(false);
        abrirMenu(false);
    });
}

function opcaoDePerfil(perfil, ativo) {
    const opcao = document.createElement('button');
    opcao.type = 'button';
    opcao.className = `perfil-financeiro-option${ativo ? ' active' : ''}`;
    opcao.dataset.perfilId = String(perfil.id);
    opcao.setAttribute('role', 'menuitem');
    const avatar = document.createElement('span');
    avatar.className = 'perfil-financeiro-option-avatar';
    avatar.textContent = iniciais(perfil);
    definirCor(avatar, '--perfil-color', perfil.cor);
    const texto = document.createElement('span');
    texto.className = 'perfil-financeiro-option-text';
    const nome = document.createElement('strong');
    nome.textContent = perfil.nome || 'Perfil';
    const tipo = document.createElement('small');
    tipo.textContent = `${tipoLabel(perfil.tipo)}${perfil.papel === 'LEITOR' ? ' · somente leitura' : ''}${ativo ? ' atual' : ''}`;
    texto.append(nome, tipo);
    opcao.append(avatar, texto);
    if (ativo) {
        const marca = document.createElement('span');
        marca.className = 'perfil-financeiro-option-check';
        marca.setAttribute('aria-hidden', 'true');
        marca.textContent = '✓';
        opcao.append(marca);
    }
    return opcao;
}

function renderizarPerfis() {
    const ativo = estado.ativo;
    $('perfil-financeiro-name').textContent = ativo ? (ativo.nome || 'Perfil') : 'Sem perfil';
    $('perfil-financeiro-type').textContent = ativo ? tipoLabel(ativo.tipo) : 'Perfil financeiro';
    $('perfil-financeiro-avatar').textContent = ativo ? iniciais(ativo) : 'PF';
    definirCor($('perfil-financeiro-avatar'), '--perfil-color', ativo?.cor);
    const switcher = $('perfil-financeiro-switcher');
    switcher.dataset.perfilAtivoId = ativo ? String(ativo.id) : '';
    switcher.dataset.loading = 'false';
    $('perfil-financeiro-options').replaceChildren(
        ...estado.perfis.map((perfil) => opcaoDePerfil(perfil, String(perfil.id) === String(ativo?.id))));
}

// Recarrega a lista (usado tambem por Configuracoes depois de criar ou editar um perfil).
export async function atualizarPerfis() {
    estado.perfis = await carregarPerfis();
    estado.ativo = escolherPerfilAtivo(estado.perfis, estado.usuario.id);
    if (estado.ativo) salvarPerfilAtivo(estado.usuario.id, estado.ativo.id);
    renderizarPerfis();
    return estado.ativo;
}

// "Usar este perfil" em Configuracoes: troca o perfil em uso sem sair da tela.
export function usarPerfil(perfilId) {
    salvarPerfilAtivo(estado.usuario.id, perfilId);
    estado.ativo = estado.perfis.find((p) => String(p.id) === String(perfilId)) || estado.ativo;
    renderizarPerfis();
    return estado.ativo;
}

function mostrar(id) {
    const elemento = $(id);
    if (elemento) elemento.hidden = false;
}

// Devolve { usuario, perfil, perfis } (perfil null quando nao ha perfil autorizado) ou null sem sessao.
export async function iniciarMoldura() {
    ligarMenu();
    ligarTopbar();
    manterCompetencia();
    const usuario = await exigirUsuario();
    if (!usuario) return null;
    estado.usuario = usuario;
    $('usuario-email').textContent = usuario.email ? `Conectado como ${usuario.email}` : '';
    try {
        await atualizarPerfis();
    } catch (_erro) {
        $('perfil-financeiro-switcher').dataset.loading = 'error';
        const erro = $('perfis-erro');
        if (erro) {
            erro.textContent = 'Não foi possível carregar os perfis financeiros.';
            erro.hidden = false;
        }
        return { usuario, perfil: null, perfis: [] };
    }
    if (!estado.perfis.length) mostrar('perfis-vazio');
    return { usuario, perfil: estado.ativo, perfis: estado.perfis };
}
