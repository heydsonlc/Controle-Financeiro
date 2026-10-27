// FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 — adaptador da tela original de Categorias: responde as rotas /api/... que
// js/original/categorias.js chama (ponte-api.js), no formato do Flask (migration 20261119090000).
// - Leitura: categorias de despesa (globais), palavras-chave, Categorias do Cartao do perfil e vinculos. A tela original
//   pede palavras-chave e vinculos uma vez por categoria; aqui cada lista vem do banco uma vez por carga da tela.
// - Escrita so das Categorias do Cartao (por perfil): criar, editar, desativar/reativar, vincular e desvincular, pelo
//   escritor do perfil (o banco recusa perfil ainda no Flask).
// - Categorias de despesa e palavras-chave sao comuns a todos os perfis (inclusive os ainda no Flask). FIN-CATEGORIAS-
//   RECORRENCIAS-2 (migration 20261125090000): cadastro, edicao, exclusao segura e palavras-chave pelas funcoes do
//   catalogo, que so gravam com o catalogo passado ao novo aplicativo (escritor proprio, padrao Flask) e por conta
//   gestora; ate la o banco recusa e nada e gravado. Logos: os arquivos estao no servidor do Flask; aqui a tela mostra
//   o icone e o envio fica para o armazenamento de arquivos (FIN-DOCUMENTOS-2).

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null, palavras: null, vinculos: null };
const GLOBAIS = 'Categorias de despesa são comuns a todos os perfis, inclusive os ainda no sistema atual: cadastro, edição, '
    + 'exclusão e palavras-chave continuam no sistema atual (Flask) até o catálogo passar ao novo aplicativo. Nada foi gravado.';
const LOGOS = 'Logo de categoria: os arquivos ficam no servidor do sistema atual; o envio pelo novo aplicativo depende do '
    + 'armazenamento de arquivos (FIN-DOCUMENTOS-2). Nada foi gravado.';
const chaves = criarChaves();

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

// Catalogo global (sem perfil): respostas no formato do Flask; palavras-chave relidas na proxima consulta.
async function criarCategoria(corpo) {
    const operacao = `categoria:${JSON.stringify(corpo)}`;
    const r = await rpc((a) => supabase.rpc('criar_categoria', a), { p_dados: corpo, p_chave: chaves.de(operacao) });
    chaves.esquecer(operacao);
    const { corpo: lida } = await categoria(r.categoria_id);
    return { status: 201, corpo: { success: true, message: 'Categoria criada com sucesso', data: lida.data } };
}

async function editarCategoria(id, corpo) {
    await rpc((a) => supabase.rpc('editar_categoria', a), { p_categoria_id: id, p_dados: corpo });
    const { corpo: lida } = await categoria(id);
    return ok({ message: 'Categoria atualizada com sucesso', data: lida.data });
}

async function excluirCategoria(id) {
    await rpc((a) => supabase.rpc('excluir_categoria', a), { p_categoria_id: id });
    estado.palavras = null;
    return ok({ message: 'Categoria deletada com sucesso' });
}

async function criarPalavra(id, corpo) {
    const r = await rpc((a) => supabase.rpc('criar_palavra_chave', a), { p_categoria_id: id, p_palavra: (corpo || {}).palavra ?? '' });
    estado.palavras = null;
    return { status: r.created ? 201 : 200, corpo: { success: true, data: r, created: r.created } };
}

async function removerPalavra(id, palavraId) {
    const r = await rpc((a) => supabase.rpc('remover_palavra_chave', a), { p_categoria_id: id, p_palavra_id: palavraId });
    estado.palavras = null;
    return ok({ data: r });
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
    // Categorias de despesa (catalogo global): o banco grava so com o catalogo no novo aplicativo (FIN-CATEGORIAS-RECORRENCIAS-2).
    ['POST', /^\/api\/categorias\/?$/, (m, corpo) => criarCategoria(corpo || {})],
    ['PUT', /^\/api\/categorias\/(\d+)$/, (m, corpo) => editarCategoria(Number(m[1]), corpo || {})],
    ['DELETE', /^\/api\/categorias\/(\d+)$/, (m) => excluirCategoria(Number(m[1]))],
    ['POST', /^\/api\/categorias\/(\d+)\/palavras-chave$/, (m, corpo) => criarPalavra(Number(m[1]), corpo)],
    ['DELETE', /^\/api\/categorias\/(\d+)\/palavras-chave\/(\d+)$/, (m) => removerPalavra(Number(m[1]), Number(m[2]))],
    [null, /^\/api\/categorias\/\d+\/logo$/, async () => falha(LOGOS)],
];

function mensagem(erro) {
    if (erro && erro.hint === 'SISTEMA_FLASK') {
        return 'As Categorias do Cartão deste perfil ainda são administradas pelo sistema atual (Flask). Nada foi gravado.';
    }
    if (erro && erro.hint === 'CATALOGO_FLASK') return GLOBAIS;
    if (erro && erro.code === '42501' && /catalogo/i.test(erro.message || '')) {
        return 'Esta conta não administra o catálogo de categorias. Nada foi gravado.';
    }
    return mensagemDeErro(erro);
}

function statusDoErro(erro) {
    if (erro && erro.code === '42501') return 403;
    if (erro && erro.hint === 'NAO_ENCONTRADA') return 404;
    return 400;
}

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && (verbo === metodo || verbo === null)) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                return falha(mensagem(erro), statusDoErro(erro));
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
