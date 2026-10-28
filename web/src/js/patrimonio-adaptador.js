// FIN-FIDELIDADE-PATRIMONIO-1 (fase 1) — adaptador da tela original de Patrimonio: responde as rotas /api/... que
// js/original/patrimonio.js chama (ponte-api.js), no formato do Flask. Consulta (migration 20261112090000): caixinhas,
// transferencias, bens do perfil Empresa (com documento e imagem) e o resumo.
// FIN-PATRIMONIO-2 (migration 20261126090000): escrita pelas funcoes do banco, com o escritor unico do perfil (perfil
// ainda no Flask e recusado sem gravar): caixinhas (criar, editar, inativar), transferencias (criar, excluir desfazendo
// os saldos), bens (criar, editar, criar a partir de documento, vincular documento, excluir sem lastro), documentos
// vinculaveis e a sugestao a partir de documento (heuristica do Flask em patrimonio-sugestao.js).
// FIN-RELATORIOS-CONFIG-1: exportacao dos bens em Excel e PDF gerada no navegador, igual a do Flask
// (relatorio-patrimonio.js, sem biblioteca; conferida com o Flask em tests/test_relatorios_patrimonio.py).

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { instalarAberturaDeArquivos } from './arquivo-comprovante.js';
import { iniciarMoldura } from './moldura.js';
import { gerarSugestao } from './patrimonio-sugestao.js';
import { excelDeBens, pdfDeBens } from './relatorio-patrimonio.js';
import { MIME_XLSX } from './exportacao-xlsx.js';

const estado = { perfil: null };
const chaves = criarChaves();
const NO_SISTEMA_ATUAL = 'Patrimônio: esta ação continua no sistema atual. Nada foi gravado.';

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

const contaLida = (id) => rpc((a) => supabase.rpc('patrimonio_conta_tela', a), { p_perfil_id: estado.perfil.id, p_conta_id: id });

async function conta(id) {
    return ok({ data: await contaLida(id) });
}

async function transferencias(parametros, id = null) {
    const lista = await rpc((a) => supabase.rpc('patrimonio_transferencias_tela', a), {
        p_perfil_id: estado.perfil.id, p_data_inicio: texto(parametros, 'data_inicio'), p_data_fim: texto(parametros, 'data_fim'),
        p_conta_id: texto(parametros, 'conta_id'), p_id: id,
    });
    return id === null ? ok({ data: lista || [], total: (lista || []).length }) : ok({ data: lista[0] });
}

const bemLido = (id) => rpc((a) => supabase.rpc('patrimonio_bens_tela', a), { p_perfil_id: estado.perfil.id, p_filtros: {}, p_bem_id: id });

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

async function documentosVinculaveis(parametros) {
    const lista = await rpc((a) => supabase.rpc('patrimonio_documentos_vinculaveis_tela', a), {
        p_perfil_id: estado.perfil.id, p_busca: texto(parametros, 'busca'),
    });
    return ok({ data: lista || [], total: (lista || []).length });
}

async function sugestao(comprovanteId) {
    const dados = await rpc((a) => supabase.rpc('patrimonio_documento_sugestao_tela', a), {
        p_perfil_id: estado.perfil.id, p_comprovante_id: comprovanteId,
    });
    return ok({ data: gerarSugestao(dados) });
}

// Cadastros com chave de repeticao (duplo clique ou reenvio nao duplicam); esquecida depois do sucesso.
async function comChave(operacao, funcao, args) {
    const r = await rpc(funcao, { ...args, p_chave: chaves.de(operacao) });
    chaves.esquecer(operacao);
    return r;
}

async function criarConta(corpo) {
    const r = await comChave(`conta:${JSON.stringify(corpo)}`, (a) => supabase.rpc('criar_caixinha', a),
        { p_perfil_id: estado.perfil.id, p_dados: corpo });
    return { status: 201, corpo: { success: true, message: 'Conta criada com sucesso', data: await contaLida(r.conta_id) } };
}

async function editarConta(id, corpo) {
    await rpc((a) => supabase.rpc('editar_caixinha', a), { p_perfil_id: estado.perfil.id, p_conta_id: id, p_dados: corpo });
    return ok({ message: 'Conta atualizada com sucesso', data: await contaLida(id) });
}

async function inativarConta(id) {
    await rpc((a) => supabase.rpc('inativar_caixinha', a), { p_perfil_id: estado.perfil.id, p_conta_id: id });
    return ok({ message: 'Conta inativada com sucesso' });
}

async function criarTransferencia(corpo) {
    const r = await comChave(`transferencia:${JSON.stringify(corpo)}`, (a) => supabase.rpc('criar_transferencia_patrimonio', a),
        { p_perfil_id: estado.perfil.id, p_dados: corpo });
    const { corpo: lida } = await transferencias(new URLSearchParams(), r.transferencia_id);
    return { status: 201, corpo: { success: true, message: 'Transferência criada com sucesso', data: lida.data } };
}

async function excluirTransferencia(id) {
    await rpc((a) => supabase.rpc('excluir_transferencia_patrimonio', a), { p_perfil_id: estado.perfil.id, p_transferencia_id: id });
    return ok({ message: 'Transferência deletada e saldos revertidos' });
}

async function criarBem(corpo) {
    const r = await comChave(`bem:${JSON.stringify(corpo)}`, (a) => supabase.rpc('criar_bem_patrimonial', a),
        { p_perfil_id: estado.perfil.id, p_dados: corpo });
    return { status: 201, corpo: { success: true, message: 'Bem patrimonial criado com sucesso', data: await bemLido(r.bem_id) } };
}

async function criarBemDeDocumento(corpo) {
    const r = await comChave(`bem-doc:${JSON.stringify(corpo)}`, (a) => supabase.rpc('criar_bem_de_documento', a),
        { p_perfil_id: estado.perfil.id, p_dados: corpo });
    return { status: 201, corpo: { success: true, message: 'Bem criado a partir do documento fiscal', data: await bemLido(r.bem_id) } };
}

async function editarBem(id, corpo) {
    await rpc((a) => supabase.rpc('editar_bem_patrimonial', a), { p_perfil_id: estado.perfil.id, p_bem_id: id, p_dados: corpo });
    return ok({ message: 'Bem patrimonial atualizado com sucesso', data: await bemLido(id) });
}

async function vincularDocumento(id, corpo) {
    await rpc((a) => supabase.rpc('vincular_documento_bem', a), { p_perfil_id: estado.perfil.id, p_bem_id: id, p_dados: corpo });
    return ok({ message: 'Documento fiscal vinculado ao bem', data: await bemLido(id) });
}

async function excluirBem(id) {
    await rpc((a) => supabase.rpc('excluir_bem_patrimonial', a), { p_perfil_id: estado.perfil.id, p_bem_id: id });
    return ok({ message: 'Bem patrimonial excluido' });
}

// GET /api/patrimonio/bens/exportar-excel|pdf: so no perfil Empresa (PermissionError 403 do Flask).
async function exportarBens(tipo, parametros) {
    if (estado.perfil.tipo !== 'EMPRESA') return falha('Relatorio patrimonial disponivel apenas no perfil Empresa.', 403);
    const filtros = Object.fromEntries(parametros.entries());
    const bensLidos = await rpc((a) => supabase.rpc('patrimonio_bens_tela', a), { p_perfil_id: estado.perfil.id, p_filtros: filtros, p_bem_id: null });
    const d = new Date();
    const dois = (n) => String(n).padStart(2, '0');
    const entrada = { perfilNome: estado.perfil.nome, bens: bensLidos || [], filtros, anoAtual: d.getFullYear(),
                      agora: `${dois(d.getDate())}/${dois(d.getMonth() + 1)}/${d.getFullYear()} ${dois(d.getHours())}:${dois(d.getMinutes())}` };
    const r = tipo === 'pdf' ? pdfDeBens(entrada) : excelDeBens(entrada);
    return { status: 200, arquivo: { conteudo: r.conteudo, nome: r.nome, mime: tipo === 'pdf' ? 'application/pdf' : MIME_XLSX } };
}

const ROTAS = [
    ['GET', /^\/api\/perfis-financeiros\/ativo$/, () => ok({ perfil_ativo: estado.perfil })],
    ['GET', /^\/api\/patrimonio\/contas\/?$/, (m, c, p) => contas(p)],
    ['GET', /^\/api\/patrimonio\/contas\/(\d+)$/, (m) => conta(Number(m[1]))],
    ['POST', /^\/api\/patrimonio\/contas\/?$/, (m, c) => criarConta(c || {})],
    ['PUT', /^\/api\/patrimonio\/contas\/(\d+)$/, (m, c) => editarConta(Number(m[1]), c || {})],
    ['DELETE', /^\/api\/patrimonio\/contas\/(\d+)$/, (m) => inativarConta(Number(m[1]))],
    ['GET', /^\/api\/patrimonio\/transferencias\/?$/, (m, c, p) => transferencias(p)],
    ['GET', /^\/api\/patrimonio\/transferencias\/(\d+)$/, (m, c, p) => transferencias(p, Number(m[1]))],
    ['POST', /^\/api\/patrimonio\/transferencias\/?$/, (m, c) => criarTransferencia(c || {})],
    ['DELETE', /^\/api\/patrimonio\/transferencias\/(\d+)$/, (m) => excluirTransferencia(Number(m[1]))],
    ['GET', /^\/api\/patrimonio\/bens\/?$/, (m, c, p) => bens(p)],
    ['POST', /^\/api\/patrimonio\/bens\/?$/, (m, c) => criarBem(c || {})],
    ['GET', /^\/api\/patrimonio\/bens\/resumo$/, () => resumo()],
    ['GET', /^\/api\/patrimonio\/bens\/imagens$/, () => imagens()],
    ['GET', /^\/api\/patrimonio\/bens\/exportar-excel$/, (m, c, p) => exportarBens('excel', p)],
    ['GET', /^\/api\/patrimonio\/bens\/exportar-pdf$/, (m, c, p) => exportarBens('pdf', p)],
    ['POST', /^\/api\/patrimonio\/bens\/criar-a-partir-documento$/, (m, c) => criarBemDeDocumento(c || {})],
    ['GET', /^\/api\/patrimonio\/bens\/sugestao-a-partir-documento\/(\d+)$/, (m) => sugestao(Number(m[1]))],
    ['GET', /^\/api\/patrimonio\/bens\/(\d+)$/, (m) => bens(new URLSearchParams(), Number(m[1]))],
    ['PUT', /^\/api\/patrimonio\/bens\/(\d+)$/, (m, c) => editarBem(Number(m[1]), c || {})],
    ['DELETE', /^\/api\/patrimonio\/bens\/(\d+)$/, (m) => excluirBem(Number(m[1]))],
    ['POST', /^\/api\/patrimonio\/bens\/(\d+)\/vincular-documento$/, (m, c) => vincularDocumento(Number(m[1]), c || {})],
    ['GET', /^\/api\/patrimonio\/documentos-vinculaveis$/, (m, c, p) => documentosVinculaveis(p)],
];

// Erros do banco no formato do Flask: 403 fora do perfil Empresa ou sem permissao, 404 nao encontrado, 409 escritor.
function falhaDoBanco(erro) {
    if (erro && erro.hint === 'SISTEMA_FLASK') {
        return falha('O patrimônio deste perfil ainda é administrado pelo sistema atual (Flask). Nada foi gravado.', 409);
    }
    if (erro && erro.hint === 'SO_EMPRESA') return falha(erro.message, 403);
    if (erro && erro.hint === 'NAO_ENCONTRADA') return falha(erro.message, 404);
    return falha(mensagemDeErro(erro), erro && erro.code === '42501' ? 403 : 400);
}

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                return falhaDoBanco(erro);
            }
        }
    }
    return falha(NO_SISTEMA_ATUAL, 501);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfil = contexto.perfil;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
    instalarAberturaDeArquivos(estado.perfil.id);  // documento fiscal do bem (window.open('/api/ir/comprovantes/<id>/arquivo'))
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
