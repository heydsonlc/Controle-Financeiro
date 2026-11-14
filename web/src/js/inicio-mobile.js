// FIN-MVP-MOB-08: pagina principal mobile. So sessao, competencia (estado local, no endereco) e atalhos.
// Nenhum dado financeiro e lido ou gravado aqui.
//
// FIN-MVP-MOB-01: competencia, modulos ativos (MODULOS_ATIVOS), barra e menu do "Mais" ficam em js/mobile-comum.js,
// comum as paginas mobile. O atalho Resumo abre a Lista de Despesas mobile; os demais seguem desabilitados.
//
// FIN-MVP-MOBILE-05/06: so a permissao do perfil ativo e consultada (mobile-comum.js -> perfil.js): quem so le o perfil ve
// os atalhos de cadastro (Despesa, Lancamento e o Lancar da barra) desabilitados. As paginas e o banco recusam de qualquer forma.

import { deslocarMes } from './comum.js';
import { ajustarCadastrosPelaPermissao, aplicarCompetencia, competenciaInicial, prepararMais, prepararModulos } from './mobile-comum.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);

const usuario = await exigirUsuario();
if (usuario) {
    let mes = competenciaInicial();
    prepararModulos();
    prepararMais();
    aplicarCompetencia(mes);
    $('mob-mes-anterior').addEventListener('click', () => { mes = deslocarMes(mes, -1); aplicarCompetencia(mes); });
    $('mob-mes-seguinte').addEventListener('click', () => { mes = deslocarMes(mes, 1); aplicarCompetencia(mes); });
    await ajustarCadastrosPelaPermissao(usuario.id);
}
