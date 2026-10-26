// FIN-FIDELIDADE-DOCUMENTOS-1 (fase 1) — adaptador da tela original de Imposto de Renda: responde as rotas /api/ir/...
// que js/original/imposto_renda.js chama (ponte-api.js), no formato do Flask. So consulta, modos IRPF e Documentos da
// Empresa (migrations 20261113090000 e 20261117090000): contexto, categorias IR, vinculos de categoria, comprovantes com
// resumo e detalhe, taxonomia, metadados e resumo empresariais e as saidas sem documento. Arquivos (envio, OCR, download,
// ZIP), edicao, validacao, vinculos, marcacao de status e relatorios continuam no Flask nesta fase.

import { supabase } from './cliente.js';
import { falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { instalarAberturaDeArquivos, recusarNavegacao } from './arquivo-comprovante.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };
const NA_FASE_1 = 'Documentos fiscais: nesta fase o novo aplicativo só consulta documentos, categorias e resumos. Esta ação continua no sistema atual. Nada foi gravado.';

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

const lista = (dados) => ok({ data: dados || [], total: (dados || []).length });

async function contexto() {
    return ok({ data: await rpc((a) => supabase.rpc('ir_contexto_tela', a), { p_perfil_id: estado.perfilId }) });
}

async function categorias() {
    return lista(await rpc((a) => supabase.rpc('ir_categorias_tela', a), { p_perfil_id: estado.perfilId }));
}

async function categoriasDespesa(disponiveis) {
    return lista(await rpc((a) => supabase.rpc('ir_categorias_despesa_tela', a), { p_perfil_id: estado.perfilId, p_disponiveis: disponiveis }));
}

async function comprovantes(parametros, id = null) {
    const r = await rpc((a) => supabase.rpc('ir_comprovantes_tela', a), {
        p_perfil_id: estado.perfilId, p_filtros: Object.fromEntries(parametros.entries()), p_id: id,
    });
    return id === null ? ok(r) : ok({ data: r });
}

async function empresa(recurso, parametros = null, id = null) {
    return ok({ data: await rpc((a) => supabase.rpc('ir_documentos_empresa_tela', a), {
        p_perfil_id: estado.perfilId, p_recurso: recurso, p_filtros: parametros ? Object.fromEntries(parametros.entries()) : {}, p_id: id,
    }) });
}

async function saidas(parametros, resumo) {
    const r = await rpc((a) => supabase.rpc('lastro_saidas_tela', a), {
        p_perfil_id: estado.perfilId, p_filtros: Object.fromEntries(parametros.entries()), p_resumo: resumo,
    });
    return resumo ? ok({ data: r }) : lista(r);
}

const ROTAS = [
    ['GET', /^\/api\/ir\/contexto$/, () => contexto()],
    ['GET', /^\/api\/ir\/categorias$/, () => categorias()],
    ['GET', /^\/api\/ir\/categorias-despesa$/, () => categoriasDespesa(false)],
    ['GET', /^\/api\/ir\/categorias-despesa-disponiveis$/, () => categoriasDespesa(true)],
    ['GET', /^\/api\/ir\/comprovantes$/, (m, c, p) => comprovantes(p)],
    ['GET', /^\/api\/ir\/comprovantes\/(\d+)$/, (m, c, p) => comprovantes(p, Number(m[1]))],
    ['GET', /^\/api\/ir\/documentos-empresa\/taxonomia$/, () => empresa('taxonomia')],
    ['GET', /^\/api\/ir\/documentos-empresa\/resumo$/, (m, c, p) => empresa('resumo', p)],
    ['GET', /^\/api\/ir\/comprovantes\/(\d+)\/metadata-empresarial$/, (m) => empresa('metadata', null, Number(m[1]))],
    ['GET', /^\/api\/ir\/lastro\/saidas-sem-documento$/, (m, c, p) => saidas(p, false)],
    ['GET', /^\/api\/ir\/lastro\/saidas-sem-documento\/resumo$/, (m, c, p) => saidas(p, true)],
];

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                return falha(mensagemDeErro(erro), erro && erro.code === '42501' ? 403 : 400);
            }
        }
    }
    return falha(NA_FASE_1, 501);
}

const contextoMoldura = await iniciarMoldura();
if (contextoMoldura && contextoMoldura.perfil) {
    estado.perfilId = contextoMoldura.perfil.id;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
    instalarAberturaDeArquivos(estado.perfilId);  // "Abrir arquivo" (link /api/ir/comprovantes/<id>/arquivo)
    recusarNavegacao(['#ir-btn-exportar', '#ir-btn-excel', '#ir-btn-pdf'],
        'Relatório de documentos fiscais (Excel/PDF): continua no sistema atual nesta fase. Nada foi gravado.');
} else if (contextoMoldura) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
