// FIN-FIDELIDADE-RECORRENCIAS-1 — adaptador da tela original de Recorrencias: registra na ponte (ponte-api.js) o servico
// das Recorrencias (js/recorrencias-servico.js), que responde as rotas /api/... de js/original/recorrencias.js no formato
// do Flask. FIN-MVP-MOBILE-09: as regras sairam daqui sem mudanca para o servico, comum as Recorrencias mobile; aqui
// ficam a moldura, a permissao do perfil e o aviso da ultima operacao (#recorrencias-resultado).

import { supabase } from './cliente.js';
import { falha } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';
import { configurarRecorrencias, responderRecorrencias } from './recorrencias-servico.js';
import { TIPOS, abrirCadastroDespesa, destinosDesktop, prepararCadastro } from './cadastro-despesa.js';

function avisar(texto) {
    const aviso = document.getElementById('recorrencias-resultado');
    aviso.textContent = texto;
    aviso.hidden = false;
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    configurarRecorrencias(contexto.perfil.id, { avisar });
    // Quem so le o perfil ve as recorrencias, sem as acoes de escrita (o banco recusaria de qualquer forma).
    const { data: gere } = await supabase.rpc('pode_gerir_perfil', { p_perfil_id: contexto.perfil.id });
    document.body.classList.toggle('cf-somente-leitura', !gere);
    window.CF_REGISTRAR_ADAPTADOR(responderRecorrencias);
    // FIN-MVP-CADASTRO-UNIFICADO-01: "Nova recorrencia" abre o modal unico (js/cadastro-despesa.js). O formulario lateral
    // original fica so para a edicao: aparece ao editar e some ao salvar ou cancelar. O servico de Recorrencias ja esta
    // configurado acima (o aviso da ultima operacao continua em #recorrencias-resultado).
    prepararCadastro(contexto.perfil.id, { recorrencias: false });
    const secao = document.getElementById('secao-formulario');
    const preparar = window.prepararFormularioNovaRecorrencia;
    const editar = window.editarRecorrencia;
    window.prepararFormularioNovaRecorrencia = function (...args) {
        const r = preparar.apply(this, args);
        secao.hidden = true;
        return r;
    };
    window.editarRecorrencia = async function (...args) {
        const r = await editar.apply(this, args);
        secao.hidden = !document.getElementById('recorrencia-id').value;
        if (!secao.hidden) secao.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        return r;
    };
    window.abrirFormularioRecorrencia = () => abrirCadastroDespesa({ origem: 'recorrencias', tipoInicial: TIPOS.DESPESA_RECORRENTE,
        mes: document.getElementById('filtro-competencia').value, destinos: destinosDesktop('recorrencias'),
        aoSalvar: () => window.carregarRecorrencias() });
    secao.hidden = !document.getElementById('recorrencia-id').value;
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
