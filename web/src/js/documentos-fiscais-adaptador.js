// FIN-FIDELIDADE-DOCUMENTOS-1 (fase 1) — adaptador da tela original de Imposto de Renda: responde as rotas /api/ir/...
// que js/original/imposto_renda.js chama (ponte-api.js), no formato do Flask. So consulta, modos IRPF e Documentos da
// Empresa (migrations 20261113090000 e 20261117090000): contexto, categorias IR, vinculos de categoria, comprovantes com
// resumo e detalhe, taxonomia, metadados e resumo empresariais e as saidas sem documento.
// FIN-DOCUMENTOS-2 (migration 20261128090000): envio de arquivo (guardado no banco, privado do perfil, com as validacoes
// do Flask e duplicidade por hash), revisao, validacao, vinculos e despesa/lancamento a partir do documento, com o
// escritor unico do perfil. O texto de PDF textual e extraido aqui (pdf.js, sem servico externo); sem ele, revisao
// manual. Continuam no sistema atual: OCR de imagem, metadados empresariais, saidas sem documento, categorias IR e
// relatorios (Excel/PDF/ZIP).

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { textoDoPdf } from './importacao-pdf.js';
import { instalarAberturaDeArquivos, recusarNavegacao } from './arquivo-comprovante.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };
const chaves = criarChaves();
const NA_FASE_1 = 'Documentos fiscais: esta ação (OCR de imagem, metadados da empresa, saídas sem documento, categorias IR ou relatórios) continua no sistema atual. Nada foi gravado.';

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

// PDF.js carregado so quando um PDF e enviado (o worker tambem vem do proprio site).
let pdfjsCarregado = null;
async function pdfjs() {
    if (!pdfjsCarregado) {
        pdfjsCarregado = await import('../vendor/pdf.min.mjs');
        pdfjsCarregado.GlobalWorkerOptions.workerSrc = new URL('../vendor/pdf.worker.min.mjs', import.meta.url).href;
    }
    return pdfjsCarregado;
}

function base64(bytes) {
    let binario = '';
    for (let i = 0; i < bytes.length; i += 0x8000) binario += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(binario);
}

// Texto do PDF textual (complementar: PDF escaneado ou invalido fica para revisao manual).
async function textoExtraido(arquivo, bytes) {
    if (!/\.pdf$/i.test(arquivo.name || '')) return null;
    try {
        return (await textoDoPdf(bytes.buffer.slice(0), await pdfjs())).join('\n');
    } catch (_erro) {
        return null;
    }
}

const comprovanteLido = (id) => rpc((a) => supabase.rpc('ir_comprovantes_tela', a), {
    p_perfil_id: estado.perfilId, p_filtros: {}, p_id: id,
});

// POST /api/ir/comprovantes/upload: cada arquivo e uma chamada (o Flask devolve 207 se algum falha).
async function enviar(formData) {
    const arquivos = formData ? [...formData.getAll('arquivos'), ...formData.getAll('files'), ...formData.getAll('arquivo')]
        .filter((a) => a && a.name !== undefined) : [];
    if (!arquivos.length) return falha('Nenhum arquivo enviado', 400);
    const ano = formData.get('ano_calendario') || formData.get('ano') || null;
    const resultados = [];
    for (const arquivo of arquivos) {
        try {
            const bytes = new Uint8Array(await arquivo.arrayBuffer());
            const operacao = `upload:${arquivo.name}:${arquivo.size}:${arquivo.lastModified}`;
            const r = await rpc((a) => supabase.rpc('enviar_comprovante', a), {
                p_perfil_id: estado.perfilId, p_conteudo: base64(bytes), p_chave: chaves.de(operacao),
                p_dados: { nome_arquivo: arquivo.name, mime_type: arquivo.type || null, ano_calendario: ano,
                           texto_extraido: await textoExtraido(arquivo, bytes) },
            });
            chaves.esquecer(operacao);
            resultados.push({ success: true, data: { duplicado: r.duplicado, mensagem: r.mensagem,
                                                    comprovante: await comprovanteLido(r.comprovante_id) } });
        } catch (erro) {
            if (erro && erro.hint === 'SISTEMA_FLASK') throw erro;
            resultados.push({ success: false, error: mensagemDeErro(erro), arquivo: arquivo.name });
        }
    }
    const status = resultados.some((r) => !r.success) ? 207 : 200;
    return { status, corpo: { success: true, data: resultados, total: resultados.length } };
}

async function revisar(id, corpo) {
    await rpc((a) => supabase.rpc('atualizar_comprovante', a), { p_perfil_id: estado.perfilId, p_id: id, p_dados: corpo || {} });
    return ok({ data: await comprovanteLido(id) });
}

async function validar(id) {
    await rpc((a) => supabase.rpc('validar_comprovante', a), { p_perfil_id: estado.perfilId, p_id: id });
    return ok({ data: await comprovanteLido(id) });
}

async function excluir(id) {
    await rpc((a) => supabase.rpc('excluir_comprovante', a), { p_perfil_id: estado.perfilId, p_id: id });
    return ok({ message: 'Documento excluido' });
}

async function vincular(id, corpo) {
    const r = await rpc((a) => supabase.rpc('criar_vinculo_documento', a), { p_perfil_id: estado.perfilId, p_comprovante_id: id, p_dados: corpo || {} });
    return { status: 201, corpo: { success: true, data: { id: r.vinculo_id } } };
}

async function editarVinculo(id, vinculo, corpo) {
    await rpc((a) => supabase.rpc('atualizar_vinculo_documento', a), {
        p_perfil_id: estado.perfilId, p_comprovante_id: id, p_vinculo_id: vinculo, p_dados: corpo || {},
    });
    return ok({ data: { id: vinculo } });
}

async function removerVinculo(id, vinculo) {
    await rpc((a) => supabase.rpc('remover_vinculo_documento', a), { p_perfil_id: estado.perfilId, p_comprovante_id: id, p_vinculo_id: vinculo });
    return ok({ data: { id: vinculo, ativo: false } });
}

async function criarFinanceiro(id, corpo) {
    const operacao = `financeiro:${id}:${JSON.stringify(corpo || {})}`;
    const r = await rpc((a) => supabase.rpc('criar_financeiro_documento', a), {
        p_perfil_id: estado.perfilId, p_comprovante_id: id, p_dados: corpo || {}, p_chave: chaves.de(operacao),
    });
    chaves.esquecer(operacao);
    return { status: 201, corpo: { success: true, data: { ...r, comprovante: await comprovanteLido(id) } } };
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
    ['POST', /^\/api\/ir\/comprovantes\/upload$/, (m, c) => enviar(c)],
    ['PUT', /^\/api\/ir\/comprovantes\/(\d+)$/, (m, c) => revisar(Number(m[1]), c)],
    ['DELETE', /^\/api\/ir\/comprovantes\/(\d+)$/, (m) => excluir(Number(m[1]))],
    ['POST', /^\/api\/ir\/comprovantes\/(\d+)\/validar$/, (m) => validar(Number(m[1]))],
    ['POST', /^\/api\/ir\/comprovantes\/(\d+)\/vinculos$/, (m, c) => vincular(Number(m[1]), c)],
    ['PUT', /^\/api\/ir\/comprovantes\/(\d+)\/vinculos\/(\d+)$/, (m, c) => editarVinculo(Number(m[1]), Number(m[2]), c)],
    ['DELETE', /^\/api\/ir\/comprovantes\/(\d+)\/vinculos\/(\d+)$/, (m) => removerVinculo(Number(m[1]), Number(m[2]))],
    ['POST', /^\/api\/ir\/comprovantes\/(\d+)\/criar-financeiro$/, (m, c) => criarFinanceiro(Number(m[1]), c)],
];

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                if (erro && erro.hint === 'SISTEMA_FLASK') {
                    return falha('Os documentos deste perfil ainda são administrados pelo sistema atual (Flask). Nada foi gravado.', 409);
                }
                if (erro && erro.hint === 'NAO_ENCONTRADA') return falha(mensagemDeErro(erro), 404);
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
