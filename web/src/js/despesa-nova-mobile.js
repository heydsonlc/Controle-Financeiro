// FIN-MVP-MOBILE-05 — Nova Despesa mobile (atalho Despesa da pagina principal), homologada em 14/11/2026.
// FIN-MVP-CADASTRO-UNIFICADO-01: o cadastro e o do modal unico (js/cadastro-despesa.js), o mesmo de Despesas, Lancamentos e
// Recorrencias no desktop e no celular; aqui ficam so a sessao, o perfil, a permissao e a moldura mobile. Ao fechar o
// modal (cancelar ou concluir) volta-se a pagina principal, na competencia de origem.
// Nenhuma regra financeira nova. Sem innerHTML (CSP): tudo por createElement.

import { el } from './comum.js';
import { TIPOS, abrirCadastroDespesa, destinosMobile, prepararCadastro } from './cadastro-despesa.js';
import { podeGerirPerfil } from './despesas-servico.js';
import { MODULOS_ATIVOS, ajustarCadastrosPelaPermissao, competenciaInicial, prepararMais, prepararModulos } from './mobile-comum.js';
import { mostrarAviso, texto } from './mobile-ui.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);

// Inicio, Voltar e os modulos ativos levam a competencia aberta (como aplicarCompetencia das outras paginas).
function ligarCompetencia(mes) {
    for (const inicio of document.querySelectorAll('[data-inicio]')) inicio.setAttribute('href', `inicio.html?mes=${mes}`);
    for (const item of document.querySelectorAll('[data-modulo][data-destino]')) {
        if (MODULOS_ATIVOS.has(item.dataset.modulo)) item.setAttribute('href', `${item.dataset.destino}?mes=${mes}`);
    }
}

const usuario = await exigirUsuario();
if (usuario) {
    const mes = competenciaInicial();
    prepararModulos();
    prepararMais();
    ligarCompetencia(mes);
    let perfil = null;
    try {
        const perfis = await carregarPerfis();
        perfil = escolherPerfilAtivo(perfis, usuario.id);
        if (perfil) salvarPerfilAtivo(usuario.id, perfil.id);
    } catch (_erro) {
        mostrarAviso('Não foi possível carregar os perfis financeiros.', 'erro');
    }
    const cadastro = $('mob-cadastro');
    if (perfil) {
        $('mob-perfil').textContent = perfil.nome || '';
        prepararCadastro(perfil.id);
        const voltar = el('a', 'mob-botao', 'Voltar ao início');
        voltar.href = `inicio.html?mes=${mes}`;
        const acoes = el('div', 'mob-acoes');
        acoes.append(voltar);
        if (!await podeGerirPerfil()) {
            // Somente leitura: sem cadastro (o banco recusaria a gravacao de qualquer forma); Lancar desabilitado.
            await ajustarCadastrosPelaPermissao(usuario.id);
            cadastro.replaceChildren(texto('Acesso somente de leitura a este perfil: não é possível cadastrar despesas.'), acoes);
        } else {
            cadastro.replaceChildren(acoes);
            abrirCadastroDespesa({ origem: 'despesas', mes, tipoInicial: TIPOS.DESPESA_DIRETA, destinos: destinosMobile(),
                aoFechar: () => { window.location.href = `inicio.html?mes=${mes}`; } });
        }
    } else if ($('mob-aviso').hidden) {
        mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
    }
    cadastro.setAttribute('aria-busy', 'false');
}
