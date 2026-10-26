// FIN-FIDELIDADE-PATRIMONIO-1 (fase 1) — adaptador da tela original de Patrimonio: responde as rotas /api/... que
// js/original/patrimonio.js chama (ponte-api.js), no formato do Flask. So consulta (migration 20261112090000): caixinhas,
// transferencias, bens do perfil Empresa (com documento e imagem) e o resumo. Cadastro, edicao, inativacao,
// transferencias, exportacoes (Excel/PDF) e vinculos de documentos continuam no Flask (escritor unico) nesta fase.

import { supabase } from './cliente.js';
import { falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { instalarAberturaDeArquivos } from './arquivo-comprovante.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfil: null };
const NA_FASE_1 = 'Patrimônio: nesta fase o novo aplicativo só consulta caixinhas, transferências e bens. Esta ação continua no sistema atual. Nada foi gravado.';

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

const texto = (parametros, nome) => {
    const valor = parametros.get(nome);
    return valor === null || valor === '' ? null : valor;
};

async function contas(parametros) {
    const ativo = parametros.get('ativo');
    const r = await rpc((a) => supabase.rpc('patrimonio_contas_tela', a), {
        p_perfil_id: estado.perfil.id, p_ativo: ativo === null ? null : ativo.toLowerCase() === 'true',
    });
    return ok(r);
}

async function conta(id) {
    return ok({ data: await rpc((a) => supabase.rpc('patrimonio_conta_tela', a), { p_perfil_id: estado.perfil.id, p_conta_id: id }) });
}

async function transferencias(parametros, id = null) {
    const lista = await rpc((a) => supabase.rpc('patrimonio_transferencias_tela', a), {
        p_perfil_id: estado.perfil.id, p_data_inicio: texto(parametros, 'data_inicio'), p_data_fim: texto(parametros, 'data_fim'),
        p_conta_id: texto(parametros, 'conta_id'), p_id: id,
    });
    return id === null ? ok({ data: lista || [], total: (lista || []).length }) : ok({ data: lista[0] });
}

async function bens(parametros, id = null) {
    const filtros = Object.fromEntries(parametros.entries());
    const r = await rpc((a) => supabase.rpc('patrimonio_bens_tela', a), { p_perfil_id: estado.perfil.id, p_filtros: filtros, p_bem_id: id });
    return id === null ? ok({ data: r || [], total: (r || []).length }) : ok({ data: r });
}

async function resumo() {
    return ok({ data: await rpc((a) => supabase.rpc('patrimonio_resumo_tela', a), { p_perfil_id: estado.perfil.id }) });
}

async function imagens() {
    const lista = await rpc((a) => supabase.rpc('imagens_patrimonio', a), {});
    return ok({ data: lista || [], total: (lista || []).length });
}

const ROTAS = [
    ['GET', /^\/api\/perfis-financeiros\/ativo$/, () => ok({ perfil_ativo: estado.perfil })],
    ['GET', /^\/api\/patrimonio\/contas\/?$/, (m, c, p) => contas(p)],
    ['GET', /^\/api\/patrimonio\/contas\/(\d+)$/, (m) => conta(Number(m[1]))],
    ['GET', /^\/api\/patrimonio\/transferencias\/?$/, (m, c, p) => transferencias(p)],
    ['GET', /^\/api\/patrimonio\/transferencias\/(\d+)$/, (m, c, p) => transferencias(p, Number(m[1]))],
    ['GET', /^\/api\/patrimonio\/bens\/?$/, (m, c, p) => bens(p)],
    ['GET', /^\/api\/patrimonio\/bens\/resumo$/, () => resumo()],
    ['GET', /^\/api\/patrimonio\/bens\/imagens$/, () => imagens()],
    ['GET', /^\/api\/patrimonio\/bens\/(\d+)$/, (m) => bens(new URLSearchParams(), Number(m[1]))],
    // So alimenta o seletor de "vincular documento", acao que continua no sistema atual nesta fase: lista vazia.
    ['GET', /^\/api\/patrimonio\/documentos-vinculaveis$/, () => ok({ data: [], total: 0 })],
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

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfil = contexto.perfil;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
    instalarAberturaDeArquivos(estado.perfil.id);  // documento fiscal do bem (window.open('/api/ir/comprovantes/<id>/arquivo'))
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
