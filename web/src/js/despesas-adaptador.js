// FIN-FIDELIDADE-DESPESAS-1 — adaptador da tela original de Despesas: responde as rotas /api/... que
// js/original/despesas.js chama (ponte-api.js), no formato do Flask, com as funcoes do Supabase ja validadas.
//
// FIN-MVP-MOB-01: as rotas e as regras ficam em js/despesas-servico.js (comum ao desktop e a Lista de Despesas mobile);
// aqui ficam so a moldura, a competencia do menu e o aviso da geracao de recorrencias, como antes.

import { definirCompetencia, iniciarMoldura } from './moldura.js';
import { falha } from './adaptador-comum.js';
import { mostrarGeracao } from './despesas-recorrencias.js';
import { configurarDespesas, responderDespesas } from './despesas-servico.js';
import { TIPOS, abrirCadastroDespesa, destinosDesktop, prepararCadastro } from './cadastro-despesa.js';

const estado = { perfilId: null, mes: null };

function exibirGeracao(mes, { geracao, dispensadas }) {
    // Quem so le o perfil nao ve as acoes de escrita da tela original (o banco recusaria de qualquer forma).
    document.body.classList.toggle('cf-somente-leitura', !(geracao.previa && geracao.previa.pode_gerir));
    mostrarGeracao(geracao, mes, {
        perfilId: estado.perfilId,
        dispensadas,
        recarregar: async (mensagem) => {
            if (mensagem) {
                const aviso = document.getElementById('geracao-resultado');
                aviso.textContent = mensagem;
                aviso.hidden = false;
            }
            window.carregarDespesas();
        },
    });
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    configurarDespesas(estado.perfilId, {
        antesDeListar: (mes, trocou) => {
            if (trocou) document.getElementById('geracao-resultado').hidden = true;
            estado.mes = mes;
            definirCompetencia(mes);
        },
        depoisDaGeracao: exibirGeracao,
    });
    window.CF_REGISTRAR_ADAPTADOR(responderDespesas);
    // FIN-MVP-CADASTRO-UNIFICADO-01: "Nova despesa" abre o modal unico (js/cadastro-despesa.js). O modal original
    // (#modal-despesa) continua para a edicao, que nao passa por abrirModal(). O servico de Despesas ja esta configurado
    // acima, com os ganchos desta tela.
    prepararCadastro(estado.perfilId, { despesas: false });
    const novo = (tipoInicial) => () => abrirCadastroDespesa({ origem: 'despesas', mes: estado.mes, tipoInicial,
        destinos: destinosDesktop('despesas'), aoSalvar: () => window.carregarDespesas() });
    window.abrirModal = novo(TIPOS.DESPESA_DIRETA);
    window.abrirModalRecorrencia = novo(TIPOS.DESPESA_RECORRENTE);
    window.abrirModalConsorcio = novo(TIPOS.CONSORCIO);
} else if (contexto) {
    // Sem perfil autorizado (o aviso da moldura ja aparece): a tela nao consulta nada.
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
