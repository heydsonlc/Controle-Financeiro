// FIN-MVP-MOBILE-05 — Nova Despesa mobile (atalho Despesa da pagina principal), homologada em 14/11/2026.
// FIN-MVP-MOBILE-06: o formulario (conta a pagar e compra no cartao) passou para js/despesa-formulario.js, comum a esta
// pagina e ao Registrar Lancamento; aqui ficam so a sessao, o perfil, a permissao e a moldura mobile.
// Nenhuma regra financeira nova. Sem innerHTML (CSP): tudo por createElement.

import { el } from './comum.js';
import { configurarCompras } from './compras-servico.js';
import { montarFormularioDespesa } from './despesa-formulario.js';
import { configurarDespesas, podeGerirPerfil, responderDespesas } from './despesas-servico.js';
import { MODULOS_ATIVOS, ajustarCadastrosPelaPermissao, competenciaInicial, prepararMais, prepararModulos } from './mobile-comum.js';
import { criarFila } from './mobile-formulario.js';
import { mostrarAviso, texto } from './mobile-ui.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);
const api = criarFila('Nova Despesa', responderDespesas);

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
        configurarDespesas(perfil.id);
        configurarCompras(perfil.id);
        if (!await podeGerirPerfil()) {
            // Somente leitura: sem formulario (o banco recusaria a gravacao de qualquer forma); Lancar desabilitado.
            await ajustarCadastrosPelaPermissao(usuario.id);
            const voltar = el('a', 'mob-botao', 'Voltar ao início');
            voltar.href = `inicio.html?mes=${mes}`;
            const acoes = el('div', 'mob-acoes');
            acoes.append(voltar);
            cadastro.replaceChildren(texto('Acesso somente de leitura a este perfil: não é possível cadastrar despesas.'), acoes);
        } else {
            const r = await api('GET', '/api/categorias');
            if (!r.success) mostrarAviso(r.error || 'Não foi possível carregar as categorias.', 'erro');
            montarFormularioDespesa(cadastro, { api, mes, categorias: r.success ? (r.data || []) : [] });
        }
    } else if ($('mob-aviso').hidden) {
        mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
    }
    cadastro.setAttribute('aria-busy', 'false');
}
