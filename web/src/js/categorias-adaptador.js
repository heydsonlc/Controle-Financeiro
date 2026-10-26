// FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 — adaptador da tela original de Categorias: responde as rotas /api/... que
// js/original/categorias.js chama (ponte-api.js), no formato do Flask (migration 20261119090000).
// - Leitura: categorias de despesa (globais), palavras-chave, Categorias do Cartao do perfil e vinculos. A tela original
//   pede palavras-chave e vinculos uma vez por categoria; aqui cada lista vem do banco uma vez por carga da tela.
// - Escrita so das Categorias do Cartao (por perfil): criar, editar, desativar/reativar, vincular e desvincular, pelo
//   escritor do perfil (o banco recusa perfil ainda no Flask).
// - Categorias de despesa, palavras-chave e logos sao comuns a todos os perfis (inclusive os ainda no Flask): ficam no
//   sistema atual. Logos: os arquivos estao no servidor do Flask; aqui a tela mostra o icone.

import { supabase } from './cliente.js';
import { falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null, palavras: null, vinculos: null };
const GLOBAIS = 'Categorias de despesa são comuns a todos os perfis, inclusive os ainda no sistema atual: cadastro, edição, '
    + 'exclusão, palavras-chave e logo continuam no sistema atual nesta fase. Nada foi gravado.';

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

const ativoDe = (parametros) => {
    const v = parametros.get('ativo');
    return v === null ? null : ['1', 'true', 'sim', 'yes'].includes(v.trim().toLowerCase());
};

const semLogo = (categoria) => ({ ...categoria, logo_url: null });

async function categorias(parametros) {
    estado.palavras = null;  // nova carga da tela: palavras-chave e vinculos relidos
    const lista = await rpc((a) => supabase.rpc('categorias_tela', a), { p_perfil_id: estado.perfilId, p_ativo: ativoDe(parametros) });
    return ok({ data: (lista || []).map(semLogo), total: (lista || []).length });
}

async function categoria(id) {
    const encontrada = ((await rpc((a) => supabase.rpc('categorias_tela', a), { p_perfil_id: estado.perfilId, p_ativo: null })) || [])
        .find((c) => c.id === id);
    return encontrada ? ok({ data: semLogo(encontrada) }) : falha('Categoria não encontrada', 404);
}

async function palavrasChave(id) {
    estado.palavras = estado.palavras || rpc((a) => supabase.rpc('palavras_chave_tela', a), { p_perfil_id: estado.perfilId });
    const lista = (await estado.palavras)[String(id)] || [];
    return ok({ data: lista, total: lista.length });
}

async function categoriasCartao(parametros) {
    estado.vinculos = null;
    const lista = await rpc((a) => supabase.rpc('categorias_cartao_tela', a), { p_perfil_id: estado.perfilId, p_ativo: ativoDe(parametros) });
    return ok({ data: (lista || []).map(semLogo), total: (lista || []).length });
}

async function vinculos(id, parametros) {
    const ativo = ativoDe(parametros);
    const chave = String(ativo);
    estado.vinculos = estado.vinculos || {};
    estado.vinculos[chave] = estado.vinculos[chave]
        || rpc((a) => supabase.rpc('categoria_cartao_despesas_tela', a), { p_perfil_id: estado.perfilId, p_ativo: ativo });
    const mapa = await estado.vinculos[chave];
    if (!(String(id) in mapa)) return falha('Categoria do Cartao nao encontrada');
    return ok({ data: mapa[String(id)], total: mapa[String(id)].length });
}

// Escritas (nome literal de cada RPC); os vinculos sao relidos na proxima carga.
async function escrever(chamada, args) {
    estado.vinculos = null;
    return ok({ data: await rpc(chamada, { p_perfil_id: estado.perfilId, ...args }) });
}

const ROTAS = [
    ['GET', /^\/api\/categorias\/?$/, (m, c, p) => categorias(p)],
    ['GET', /^\/api\/categorias\/(\d+)$/, (m) => categoria(Number(m[1]))],
    ['GET', /^\/api\/categorias\/(\d+)\/palavras-chave$/, (m) => palavrasChave(Number(m[1]))],
    ['GET', /^\/api\/categorias-cartao\/?$/, (m, c, p) => categoriasCartao(p)],
    ['GET', /^\/api\/categorias-cartao\/(\d+)\/despesas$/, (m, c, p) => vinculos(Number(m[1]), p)],
    ['POST', /^\/api\/categorias-cartao\/?$/, (m, corpo) => escrever((a) => supabase.rpc('criar_categoria_cartao', a), { p_dados: corpo || {} })],
    ['PUT', /^\/api\/categorias-cartao\/(\d+)$/, (m, corpo) => escrever((a) => supabase.rpc('editar_categoria_cartao', a), { p_id: Number(m[1]), p_dados: corpo || {} })],
    ['DELETE', /^\/api\/categorias-cartao\/(\d+)$/, (m) => escrever((a) => supabase.rpc('desativar_categoria_cartao', a), { p_id: Number(m[1]) })],
    ['POST', /^\/api\/categorias-cartao\/(\d+)\/despesas$/, (m, corpo) => escrever((a) => supabase.rpc('vincular_despesa_categoria_cartao', a), {
        p_categoria_cartao_id: Number(m[1]), p_categoria_id: Number((corpo || {}).categoria_id) || null,
        p_ativo: (corpo || {}).ativo ?? true,
    })],
    ['DELETE', /^\/api\/categorias-cartao\/(\d+)\/despesas\/(\d+)$/, (m) => escrever((a) => supabase.rpc('desvincular_despesa_categoria_cartao', a), {
        p_categoria_cartao_id: Number(m[1]), p_categoria_id: Number(m[2]),
    })],
    // Categorias de despesa (globais): cadastro, edicao, exclusao, palavras-chave e logo ficam no sistema atual.
    [null, /^\/api\/categorias(\/\d+(\/(palavras-chave(\/\d+)?|logo))?)?\/?$/, async () => falha(GLOBAIS)],
];

function mensagem(erro) {
    if (erro && erro.hint === 'SISTEMA_FLASK') {
        return 'As Categorias do Cartão deste perfil ainda são administradas pelo sistema atual (Flask). Nada foi gravado.';
    }
    return mensagemDeErro(erro);
}

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && (verbo === metodo || verbo === null)) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                return falha(mensagem(erro), erro && erro.code === '42501' ? 403 : 400);
            }
        }
    }
    return falha(`${metodo} ${caminho}: continua no sistema atual nesta fase. Nada foi gravado.`, 501);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
    const { data: gere } = await supabase.rpc('pode_gerir_perfil', { p_perfil_id: estado.perfilId });
    document.body.classList.toggle('cf-somente-leitura', gere !== true);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
