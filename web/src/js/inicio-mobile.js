// FIN-MVP-MOB-08: pagina principal mobile. So sessao, competencia (estado local, no endereco) e atalhos.
// Nenhum dado financeiro e lido ou gravado aqui.
//
// FIN-MVP-MOB-01: competencia, modulos ativos (MODULOS_ATIVOS), barra e menu do "Mais" ficam em js/mobile-comum.js,
// comum as paginas mobile. O atalho Resumo abre a Lista de Despesas mobile; os demais seguem desabilitados.

//
// FIN-MVP-MOBILE-05: so a permissao do perfil ativo e consultada (perfil.js): quem so le o perfil ve o atalho Despesa
// (cadastro) desabilitado. A pagina Nova Despesa e o banco continuam recusando de qualquer forma.

import { deslocarMes } from './comum.js';
import { aplicarCompetencia, competenciaInicial, desabilitarModulo, prepararMais, prepararModulos } from './mobile-comum.js';
import { carregarPerfis, escolherPerfilAtivo, podeGerirPerfil } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);

// Atalhos de cadastro: so para quem gere o perfil ativo. Sem perfil ou com falha na consulta, o atalho fica como esta
// (a pagina de destino explica e bloqueia).
async function ajustarAtalhosDeCadastro(usuarioId) {
    try {
        const perfil = escolherPerfilAtivo(await carregarPerfis(), usuarioId);
        if (perfil && !await podeGerirPerfil(perfil.id)) desabilitarModulo('despesa', 'Somente leitura neste perfil');
    } catch (erro) {
        console.error('Pagina principal: permissao do perfil', erro);
    }
}

const usuario = await exigirUsuario();
if (usuario) {
    let mes = competenciaInicial();
    prepararModulos();
    prepararMais();
    aplicarCompetencia(mes);
    $('mob-mes-anterior').addEventListener('click', () => { mes = deslocarMes(mes, -1); aplicarCompetencia(mes); });
    $('mob-mes-seguinte').addEventListener('click', () => { mes = deslocarMes(mes, 1); aplicarCompetencia(mes); });
    await ajustarAtalhosDeCadastro(usuario.id);
}
