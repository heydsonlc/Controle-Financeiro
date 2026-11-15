// FIN-MVP-MOB-08: pagina principal mobile. So sessao, competencia (estado local, no endereco) e atalhos.
// Nenhum dado financeiro e lido ou gravado aqui.
//
// FIN-MVP-MOB-01: competencia, modulos ativos (MODULOS_ATIVOS), barra e menu do "Mais" ficam em js/mobile-comum.js,
// comum as paginas mobile. O atalho Resumo abre a Lista de Despesas mobile; os demais seguem desabilitados.
//
// FIN-MVP-MOBILE-05/06: so a permissao do perfil ativo e consultada (mobile-comum.js -> perfil.js): quem so le o perfil ve
// os atalhos de cadastro (Despesa, Lancamento e o Lancar da barra) desabilitados. As paginas e o banco recusam de qualquer forma.

//
// FIN-MVP-MOBILE-10: alternancia de perfis pelo icone de usuario ao lado do sino. A lista e a de meus_perfis (perfis
// ativos vinculados ao usuario) e a escolha e a mesma do seletor do desktop (perfil.js -> salvarPerfilAtivo): fica no
// navegador, vale para todas as paginas e a pagina recarrega, como no desktop, para nada do perfil anterior ficar na tela.
// E so preferencia de tela: o banco revalida o acesso a cada consulta.

import { deslocarMes, el } from './comum.js';
import { ajustarCadastrosPelaPermissao, aplicarCompetencia, competenciaInicial, prepararMais, prepararModulos } from './mobile-comum.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);
const SVG = 'http://www.w3.org/2000/svg';

function marcaDeEscolha() {
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const p = document.createElementNS(SVG, 'path');
    p.setAttribute('d', 'M5 12.5l4.5 4.5L19 7.5');
    svg.append(p);
    return svg;
}

async function prepararPerfis(usuario) {
    const botao = $('mob-perfis');
    const menu = $('mob-menu-perfis');
    let perfis = [];
    try {
        perfis = await carregarPerfis();
    } catch (erro) {
        console.error('Mobile: perfis', erro);
    }
    const ativo = escolherPerfilAtivo(perfis, usuario.id);
    botao.setAttribute('aria-label', ativo ? `Perfil financeiro: ${ativo.nome}. Trocar perfil` : 'Perfil financeiro');
    botao.title = ativo ? ativo.nome : 'Perfil financeiro';
    menu.replaceChildren(el('p', 'mob-menu-perfis-titulo', 'Perfil financeiro'));
    for (const perfil of perfis) {
        const item = el('button', 'mob-menu-item');
        item.type = 'button';
        item.setAttribute('role', 'menuitemradio');
        item.dataset.perfilId = String(perfil.id);
        const escolhido = Boolean(ativo && String(ativo.id) === String(perfil.id));
        item.setAttribute('aria-checked', escolhido ? 'true' : 'false');
        item.append(el('span', null, perfil.nome), marcaDeEscolha());
        item.addEventListener('click', () => {
            if (escolhido) {
                abrir(false);
                botao.focus();
                return;
            }
            salvarPerfilAtivo(usuario.id, perfil.id);
            window.location.reload();  // mantem a competencia (?mes=) e recarrega tudo no perfil novo
        });
        menu.append(item);
    }
    if (!perfis.length) menu.append(el('p', 'mob-menu-perfis-titulo', 'Nenhum perfil financeiro autorizado.'));
    function abrir(aberto) {
        menu.hidden = !aberto;
        botao.setAttribute('aria-expanded', aberto ? 'true' : 'false');
        if (aberto) (menu.querySelector('[aria-checked="true"]') || menu.querySelector('.mob-menu-item'))?.focus();
    }
    botao.addEventListener('click', (evento) => { evento.stopPropagation(); abrir(menu.hidden); });
    document.addEventListener('click', (evento) => { if (!menu.hidden && !menu.contains(evento.target)) abrir(false); });
    document.addEventListener('keydown', (evento) => { if (evento.key === 'Escape' && !menu.hidden) { abrir(false); botao.focus(); } });
}

const usuario = await exigirUsuario();
if (usuario) {
    let mes = competenciaInicial();
    prepararModulos();
    prepararMais();
    aplicarCompetencia(mes);
    $('mob-mes-anterior').addEventListener('click', () => { mes = deslocarMes(mes, -1); aplicarCompetencia(mes); });
    $('mob-mes-seguinte').addEventListener('click', () => { mes = deslocarMes(mes, 1); aplicarCompetencia(mes); });
    await Promise.all([prepararPerfis(usuario), ajustarCadastrosPelaPermissao(usuario.id)]);
}
