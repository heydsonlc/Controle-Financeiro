// FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 — adaptador da tela original de Receitas: responde as rotas /api/... que
// js/original/receitas.js chama (ponte-api.js), no formato do Flask.
// FIN-MVP-MOBILE-04: as rotas e as chamadas ao banco passaram para js/receitas-servico.js, comum as Receitas mobile, sem
// mudar as regras (leitura, fonte nova e edicao, previsoes, recebimento, estorno, contemplacao e atualizacao pelo
// valor-base). Aqui ficam so o perfil da moldura e a marca de somente leitura.

import { falha } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';
import { configurarReceitas, podeGerirPerfil, responderReceitas } from './receitas-servico.js';

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    configurarReceitas(contexto.perfil.id);
    window.CF_REGISTRAR_ADAPTADOR(responderReceitas);
    document.body.classList.toggle('cf-somente-leitura', !await podeGerirPerfil());
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
