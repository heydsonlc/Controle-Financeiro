// FIN-FIDELIDADE-CARTOES-1 — adaptador da tela original de Cartoes: registra na ponte-api.js o servico que responde as
// rotas /api/... que js/original/cartoes.js chama. FIN-MVP-MOBILE-03: as rotas e regras foram para js/cartoes-servico.js
// (sem mudanca), compartilhado com a tela mobile; aqui ficam a moldura e o modo somente leitura da tela do desktop.

import { falha } from './adaptador-comum.js';
import { configurarCartoes, podeGerirPerfil, responderCartoes } from './cartoes-servico.js';
import { iniciarMoldura } from './moldura.js';

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    configurarCartoes(contexto.perfil.id);
    // Quem so le o perfil ve cartoes, limites e faturas, sem as acoes de escrita (o banco recusaria de qualquer forma).
    document.body.classList.toggle('cf-somente-leitura', !await podeGerirPerfil());
    window.CF_REGISTRAR_ADAPTADOR(responderCartoes);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
