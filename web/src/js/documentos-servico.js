// FIN-MOBILE-11 — servico dos Documentos Fiscais: responde as rotas /api/ir/... (e as de apoio) no formato do Flask, pelas
// funcoes do banco. Veio de js/documentos-fiscais-adaptador.js SEM mudanca de regra (FIN-FIDELIDADE-DOCUMENTOS-1,
// FIN-DOCUMENTOS-2, FIN-MIGRACAO-LASTRO-EMPRESA-01, FIN-PRE-PRODUCAO-1, FIN-REG-03 e FIN-REG-04), para a tela original do
// desktop (pela ponte-api) e os Documentos mobile usarem as mesmas consultas, gravacoes, relatorios e pacote ZIP.
// O que e da tela (moldura, avisos e botoes acrescentados) ficou no adaptador; o aviso do envio chega por gancho.

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, NAO_DISPONIVEL, ok } from './adaptador-comum.js';
import { textoDoPdf } from './importacao-pdf.js';
import { comprovanteDoPerfil, erroDeDocumento, responderDocumentoFinanceiro } from './documento-financeiro.js';
import { MIME_XLSX } from './exportacao-xlsx.js';
import { divergencia, ERRO_PERFIL_ZIP, ERRO_SEM_DOCUMENTOS, montarPacote, normalizarFiltros, recusaPorVolume } from './zip-documentos.js';
import { ERRO_PERFIL_LASTRO, excelIr, excelSaidas, filtrarComprovantes, pdfIr, pdfSaidas, resumoIr, validarFiltrosSaidas } from './relatorio-fiscal.js';

const estado = { perfilId: null, perfil: null, filtrosDaLista: null, aoEnviar: null };
const chaves = criarChaves();
const NA_FASE_1 = `Documentos fiscais: esta ação (OCR de imagem ou categorias IR) ${NAO_DISPONIVEL}`;

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
    if (id === null) estado.filtrosDaLista = new URLSearchParams(parametros);  // os relatorios usam os filtros da lista em tela
    const r = await rpc((a) => supabase.rpc('ir_comprovantes_tela', a), {
        p_perfil_id: estado.perfilId, p_filtros: Object.fromEntries(parametros.entries()), p_id: id,
    });
    // FIN-MIGRACAO-LASTRO-EMPRESA-01: no modo Empresa, "Pendencias de lastro" ("N documentos sem vinculo de lastro") usa o
    // mesmo criterio do cartao "Sem lastro" (so documento que comprova operacao financeira): contrato social, procuracao e
    // certidao existem sem vinculo e nao sao pendencia.
    if (id === null && r && r.resumo && r.resumo.documentos_empresa && r.resumo.lastro) {
        r.resumo.lastro = { ...r.resumo.lastro, documentos_sem_vinculo: r.resumo.documentos_empresa.sem_lastro };
    }
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

const comprovanteLido = (id) => comprovanteDoPerfil(estado.perfilId, id);

// POST /api/ir/comprovantes/upload: cada arquivo e uma chamada (o Flask devolve 207 se algum falha).
// FIN-MIGRACAO-P0P1-01: a tela original so le `data` (renderResultadoUpload(json.data || [])) e apagava a lista sem aviso
// quando o perfil era recusado (409 sem `data`). Agora toda falha volta por arquivo, com o motivo; recusa do perfil inteiro
// (escritor ou permissao) interrompe o envio e vale para todos os arquivos. O painel mostra o retorno (retornoDoEnvio).
const RECUSA_DO_PERFIL = (erro) => erro && (erro.hint === 'SISTEMA_FLASK' || erro.code === '42501');

async function enviar(formData) {
    const arquivos = formData ? [...formData.getAll('arquivos'), ...formData.getAll('files'), ...formData.getAll('arquivo')]
        .filter((a) => a && a.name !== undefined) : [];
    if (!arquivos.length) return falha('Nenhum arquivo enviado', 400);
    const ano = formData.get('ano_calendario') || formData.get('ano') || null;
    const resultados = [];
    let recusa = null;
    for (const arquivo of arquivos) {
        if (recusa) {
            resultados.push({ success: false, error: recusa, arquivo: arquivo.name });
            continue;
        }
        try {
            const bytes = new Uint8Array(await arquivo.arrayBuffer());
            const operacao = `upload:${arquivo.name}:${arquivo.size}:${arquivo.lastModified}`;
            const r = await rpc((a) => supabase.rpc('enviar_comprovante', a), {
                p_perfil_id: estado.perfilId, p_conteudo: base64(bytes), p_chave: chaves.de(operacao),
                p_dados: { nome_arquivo: arquivo.name, mime_type: arquivo.type || null, ano_calendario: ano,
                           texto_extraido: await textoExtraido(arquivo, bytes) },
            });
            chaves.esquecer(operacao);
            // Gravado: uma falha so na releitura nao vira "nao enviado" (a lista do perfil, recarregada, mostra o documento).
            const comprovante = await comprovanteLido(r.comprovante_id).catch(() => ({ id: r.comprovante_id }));
            resultados.push({ success: true, data: { duplicado: r.duplicado, mensagem: r.mensagem, comprovante } });
        } catch (erro) {
            const motivo = erro && erro.code === '42501' ? 'Esta conta não pode gravar documentos neste perfil. Nada foi gravado.'
                : mensagemDeErro(erro);
            if (RECUSA_DO_PERFIL(erro)) recusa = motivo;
            resultados.push({ success: false, error: motivo, arquivo: arquivo.name });
        }
    }
    const enviados = resultados.filter((r) => r.success).length;
    if (estado.aoEnviar) estado.aoEnviar(enviados, resultados);  // aviso da tela (desktop)
    if (!enviados) {
        return { status: recusa ? 409 : 400,
                 corpo: { success: false, error: resultados[0].error, data: resultados, total: resultados.length } };
    }
    const status = enviados < resultados.length ? 207 : 200;
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

// PUT /api/ir/comprovantes/<id>/metadata-empresarial: a revisao (modo Empresa) grava os metadados depois do comprovante.
async function salvarMetadata(id, corpo) {
    const operacao = `metadata:${id}:${JSON.stringify(corpo || {})}`;
    const r = await rpc((a) => supabase.rpc('salvar_metadata_empresarial', a), {
        p_perfil_id: estado.perfilId, p_id: id, p_dados: corpo || {}, p_chave: chaves.de(operacao),
    });
    chaves.esquecer(operacao);
    return ok({ data: r });
}

// POST /api/ir/lastro/saidas-sem-documento/vincular e /status (LastroFinanceiroService do Flask).
async function vincularSaida(corpo) {
    const r = await rpc((a) => supabase.rpc('vincular_saida_documento', a), { p_perfil_id: estado.perfilId, p_dados: corpo || {} });
    return { status: 201, corpo: { success: true, data: r } };
}

async function marcarStatusSaida(corpo) {
    return ok({ data: await rpc((a) => supabase.rpc('marcar_status_saida', a), { p_perfil_id: estado.perfilId, p_dados: corpo || {} }) });
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

async function entidadesVinculaveis(parametros) {
    return lista(await rpc((a) => supabase.rpc('entidades_vinculaveis_tela', a), {
        p_perfil_id: estado.perfilId, p_tipo: parametros.get('tipo'), p_busca: parametros.get('busca'),
    }));
}

export const vinculosAtivos = (id) => rpc((a) => supabase.rpc('vinculos_documento_tela', a), { p_perfil_id: estado.perfilId, p_comprovante_id: id });

// Cartoes e contas do perfil para o modal "Sugestao financeira" (carregarRecursosFinanceirosSugestao), como Lancamentos.
async function cartoes() {
    const todos = await rpc((a) => supabase.rpc('cartoes_do_perfil', a), { p_perfil_id: estado.perfilId });
    return { status: 200, corpo: (todos || []).filter((c) => c.ativo).map((c) => ({ id: c.id, nome: c.nome, tipo: 'Agregador', ativo: true })) };
}

async function contasBancarias() {
    const contas = await rpc((a) => supabase.rpc('contas_bancarias_tela', a), { p_perfil_id: estado.perfilId, p_status: 'ATIVO' });
    return lista(contas || []);
}

async function resumoLastro(parametros) {
    return ok({ data: await rpc((a) => supabase.rpc('lastro_resumo_tela', a), { p_perfil_id: estado.perfilId, p_ano: parametros.get('ano') }) });
}

async function saidas(parametros, resumo) {
    const r = await rpc((a) => supabase.rpc('lastro_saidas_tela', a), {
        p_perfil_id: estado.perfilId, p_filtros: Object.fromEntries(parametros.entries()), p_resumo: resumo,
    });
    return resumo ? ok({ data: r }) : lista(r);
}

// ---- FIN-REG-03: relatorios (so leitura) -----------------------------------------------------------------------------
function momento() {
    const d = new Date();
    const dois = (n) => String(n).padStart(2, '0');
    return { anoAtual: d.getFullYear(),
             agora: `${dois(d.getDate())}/${dois(d.getMonth() + 1)}/${d.getFullYear()} ${dois(d.getHours())}:${dois(d.getMinutes())}` };
}

const arquivo = (r, pdf) => ({ status: 200, arquivo: { conteudo: r.conteudo, nome: r.nome, mime: pdf ? 'application/pdf' : MIME_XLSX } });

// Falha na montagem do arquivo: mensagem clara, sem detalhe interno (o detalhe fica so no console).
function gerar(montar, descricao) {
    try {
        return montar();
    } catch (erro) {
        console.error('Relatorio:', descricao, erro);
        return falha(`Não foi possível gerar ${descricao}. Nada foi alterado.`, 500);
    }
}

// Lista completa do filtro (ir_comprovantes_tela nao pagina) com os vinculos ATIVOS de cada documento, o MAIS RECENTE
// primeiro (a ordem de vinculos_documento_tela, a mesma da lista da tela); so quem tem vinculo e consultado, em grupos
// pequenos. O primeiro e o vinculo que o relatorio mostra como natureza e situacao do lastro do documento.
async function comprovantesDoRelatorio(filtros) {
    const r = await rpc((a) => supabase.rpc('ir_comprovantes_tela', a), { p_perfil_id: estado.perfilId, p_filtros: filtros, p_id: null });
    const documentos = (r && r.data) || [];
    const comVinculo = documentos.filter((c) => Number(c.vinculos_count) > 0);
    for (let i = 0; i < comVinculo.length; i += 8) {
        await Promise.all(comVinculo.slice(i, i + 8).map(async (c) => {
            c.vinculos = await vinculosAtivos(c.id) || [];
        }));
    }
    return documentos;
}

// GET /api/ir/relatorios/excel|pdf|resumo (IrRelatorioService).
async function relatorioIr(tipo, parametros) {
    const filtros = Object.fromEntries(parametros.entries());
    if (filtros.ano && !/^\s*[+-]?\d+\s*$/.test(filtros.ano)) return falha('Ano do relatorio invalido', 400);
    const documentos = filtrarComprovantes(await comprovantesDoRelatorio(filtros), filtros);
    if (tipo === 'resumo') return ok({ data: resumoIr(documentos) });
    const entrada = { perfilNome: estado.perfil.nome, empresa: estado.perfil.tipo === 'EMPRESA', comprovantes: documentos, filtros, ...momento() };
    return gerar(() => arquivo(tipo === 'pdf' ? pdfIr(entrada) : excelIr(entrada), tipo === 'pdf'), 'o relatório');
}

// GET /api/ir/lastro/saidas-sem-documento/relatorio-excel|pdf (LastroRelatorioService): so no perfil Empresa.
async function relatorioSaidas(tipo, parametros) {
    if (estado.perfil.tipo !== 'EMPRESA') return falha(ERRO_PERFIL_LASTRO, 403);
    const filtros = Object.fromEntries(parametros.entries());
    try {
        validarFiltrosSaidas(filtros);
    } catch (erro) {
        return falha(erro.message, 400);
    }
    const lidas = await rpc((a) => supabase.rpc('lastro_saidas_tela', a), { p_perfil_id: estado.perfilId, p_filtros: filtros, p_resumo: false });
    const entrada = { perfilNome: estado.perfil.nome, saidas: lidas || [], filtros, ...momento() };
    return gerar(() => arquivo(tipo === 'pdf' ? pdfSaidas(entrada) : excelSaidas(entrada), tipo === 'pdf'), 'o relatório');
}

// ---- FIN-REG-04: pacote ZIP dos documentos da Empresa (so leitura) ----------------------------------------------------
function bytesDoArquivo(dados) {
    const binario = atob((dados && dados.conteudo_base64) || '');
    const bytes = new Uint8Array(binario.length);
    for (let i = 0; i < binario.length; i += 1) bytes[i] = binario.charCodeAt(i);
    return bytes;
}

// GET /api/ir/documentos-empresa/exportar-zip (DocumentoZipService): so no perfil Empresa, com os filtros da tela. Qualquer
// falha (consulta, arquivo ausente, divergencia de integridade, volume) devolve erro e NENHUM pacote, nem parcial.
async function pacoteZip(parametros) {
    if (estado.perfil.tipo !== 'EMPRESA') return falha(ERRO_PERFIL_ZIP, 403);
    const filtros = normalizarFiltros(Object.fromEntries(parametros.entries()));
    const r = await rpc((a) => supabase.rpc('ir_comprovantes_tela', a), { p_perfil_id: estado.perfilId, p_filtros: filtros, p_id: null });
    const documentos = (r && r.data) || [];
    if (!documentos.length) return falha(ERRO_SEM_DOCUMENTOS, 400);
    const recusa = recusaPorVolume(documentos);
    if (recusa) return falha(recusa, 413);
    try {
        const comVinculo = documentos.filter((c) => Number(c.vinculos_count) > 0);
        for (let i = 0; i < comVinculo.length; i += 8) {
            await Promise.all(comVinculo.slice(i, i + 8).map(async (c) => { c.vinculos = await vinculosAtivos(c.id) || []; }));
        }
        const comArquivo = documentos.filter((c) => c.arquivo);
        for (let i = 0; i < comArquivo.length; i += 3) {  // poucos por vez: cada arquivo chega inteiro na memoria
            const problemas = await Promise.all(comArquivo.slice(i, i + 3).map(async (c) => {
                const dados = await rpc((a) => supabase.rpc('arquivo_comprovante_tela', a), { p_perfil_id: estado.perfilId, p_comprovante_id: c.id });
                c.conteudo = bytesDoArquivo(dados);
                const diferenca = await divergencia(c, c.conteudo);
                return diferenca ? `O arquivo "${c.arquivo.nome_arquivo}" tem ${diferenca}. O pacote não foi gerado.` : null;
            }));
            const problema = problemas.find(Boolean);
            if (problema) return falha(problema, 409);
        }
        const pacote = montarPacote({ perfilNome: estado.perfil.nome, documentos, filtros, ...momento(), quando: new Date() });
        return { status: 200, arquivo: { conteudo: pacote.conteudo, nome: pacote.nome, mime: 'application/zip' } };
    } catch (erro) {
        if (erro instanceof RangeError) {
            return falha('O pacote é grande demais para a memória deste navegador. Refine os filtros (ano, tipo ou categoria) e gere em partes.', 413);
        }
        if (erro && (erro.code || erro.hint)) throw erro;  // erro do banco: tratado como nas demais rotas (perfil, nao encontrado)
        console.error('Pacote ZIP:', erro);
        return falha(erro instanceof Error && /pacote não foi gerado/.test(erro.message) ? erro.message
            : 'Não foi possível gerar o pacote ZIP. Nenhum arquivo foi gerado.', 500);
    } finally {
        for (const c of documentos) delete c.conteudo;  // libera a memoria dos arquivos
    }
}

const ROTAS = [
    ['GET', /^\/api\/ir\/documentos-empresa\/exportar-zip$/, (m, c, p) => pacoteZip(p)],
    ['GET', /^\/api\/ir\/relatorios\/(excel|pdf|resumo)$/, (m, c, p) => relatorioIr(m[1], p)],
    ['GET', /^\/api\/ir\/lastro\/saidas-sem-documento\/relatorio-(excel|pdf)$/, (m, c, p) => relatorioSaidas(m[1], p)],
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
    ['PUT', /^\/api\/ir\/comprovantes\/(\d+)\/metadata-empresarial$/, (m, c) => salvarMetadata(Number(m[1]), c)],
    ['POST', /^\/api\/ir\/lastro\/saidas-sem-documento\/vincular$/, (m, c) => vincularSaida(c)],
    ['POST', /^\/api\/ir\/lastro\/saidas-sem-documento\/status$/, (m, c) => marcarStatusSaida(c)],
    ['PUT', /^\/api\/ir\/comprovantes\/(\d+)$/, (m, c) => revisar(Number(m[1]), c)],
    ['DELETE', /^\/api\/ir\/comprovantes\/(\d+)$/, (m) => excluir(Number(m[1]))],
    ['POST', /^\/api\/ir\/comprovantes\/(\d+)\/validar$/, (m) => validar(Number(m[1]))],
    ['POST', /^\/api\/ir\/comprovantes\/(\d+)\/vinculos$/, (m, c) => vincular(Number(m[1]), c)],
    ['PUT', /^\/api\/ir\/comprovantes\/(\d+)\/vinculos\/(\d+)$/, (m, c) => editarVinculo(Number(m[1]), Number(m[2]), c)],
    ['DELETE', /^\/api\/ir\/comprovantes\/(\d+)\/vinculos\/(\d+)$/, (m) => removerVinculo(Number(m[1]), Number(m[2]))],
    ['GET', /^\/api\/ir\/entidades-vinculaveis$/, (m, c, p) => entidadesVinculaveis(p)],
    ['GET', /^\/api\/ir\/comprovantes\/(\d+)\/vinculos$/, async (m) => lista(await vinculosAtivos(Number(m[1])))],
    ['GET', /^\/api\/ir\/lastro\/resumo$/, (m, c, p) => resumoLastro(p)],
    ['GET', /^\/api\/cartoes\/?$/, () => cartoes()],
    ['GET', /^\/api\/contas\/?$/, () => contasBancarias()],
];

export async function responderDocumentos({ metodo, caminho, parametros, corpo }) {
    const documentoFinanceiro = await responderDocumentoFinanceiro({ metodo, caminho, parametros, corpo }, estado.perfilId, chaves);
    if (documentoFinanceiro) return documentoFinanceiro;
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                return erroDeDocumento(erro);
            }
        }
    }
    return falha(NA_FASE_1, 501);
}

// perfil: { id, nome, tipo } do perfil ativo. aoEnviar(enviados, resultados): aviso da tela depois de um envio (opcional).
export function configurarDocumentos(perfil, { aoEnviar = null } = {}) {
    estado.perfilId = perfil.id;
    estado.perfil = perfil;
    estado.aoEnviar = aoEnviar;
    estado.filtrosDaLista = null;
}

// Filtros da ultima lista pedida (os relatorios do desktop usam os filtros da lista em tela).
export const filtrosDaLista = () => estado.filtrosDaLista;
