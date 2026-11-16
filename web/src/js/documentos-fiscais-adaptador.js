// FIN-FIDELIDADE-DOCUMENTOS-1 (fase 1) — adaptador da tela original de Imposto de Renda: responde as rotas /api/ir/...
// que js/original/imposto_renda.js chama (ponte-api.js), no formato do Flask. So consulta, modos IRPF e Documentos da
// Empresa (migrations 20261113090000 e 20261117090000): contexto, categorias IR, vinculos de categoria, comprovantes com
// resumo e detalhe, taxonomia, metadados e resumo empresariais e as saidas sem documento.
// FIN-DOCUMENTOS-2 (migration 20261128090000): envio de arquivo (guardado no banco, privado do perfil, com as validacoes
// do Flask e duplicidade por hash), revisao, validacao, vinculos e despesa/lancamento a partir do documento, com o
// escritor unico do perfil. O texto de PDF textual e extraido aqui (pdf.js, sem servico externo); sem ele, revisao
// manual. Ainda nao disponiveis nesta versao: OCR de imagem e categorias IR.
// FIN-REG-03: relatorios de Imposto de Renda / Documentos Fiscais e de Saidas sem documento (Excel e PDF), gerados no
// navegador (js/relatorio-fiscal.js) com as consultas ja publicadas; so leitura, sem migration.
// FIN-REG-04: pacote ZIP dos documentos da Empresa para o contador (js/zip-documentos.js), com indice e os arquivos
// originais conferidos pelo SHA-256 gravado; so leitura, sem migration, nada sai do navegador.
// FIN-MIGRACAO-LASTRO-EMPRESA-01 (migration 20261202090000): metadados empresariais (a revisao da tela original grava
// tipo, categoria, numero, orgao, datas, situacao...), saidas sem documento (vincular documento e situacao manual) e
// exclusao de documento pela lista (botao acrescentado; a tela original nao tinha), pelas funcoes do banco.
// FIN-PRE-PRODUCAO-1 (migration 20261130090000): entidades vinculaveis, vinculos ativos e resumo de lastro, e "Gerar
// financeiro" (sugestao + criacao, js/documento-financeiro.js, comum com Despesas e Lancamentos). Um documento pode ser
// vinculado a varios bens (regra do titular). Acrescimo ao Flask (que nao tinha "desvincular" na tela): o modal
// "Vincular documento" lista os vinculos ativos com "Desvincular" (o vinculo fica inativo, historico preservado).

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, NAO_DISPONIVEL, ok } from './adaptador-comum.js';
import { textoDoPdf } from './importacao-pdf.js';
import { instalarAberturaDeArquivos } from './arquivo-comprovante.js';
import { comprovanteDoPerfil, erroDeDocumento, responderDocumentoFinanceiro } from './documento-financeiro.js';
import { iniciarMoldura } from './moldura.js';
import { MIME_XLSX } from './exportacao-xlsx.js';
import { divergencia, ERRO_PERFIL_ZIP, ERRO_SEM_DOCUMENTOS, montarPacote, normalizarFiltros, recusaPorVolume } from './zip-documentos.js';
import { ERRO_PERFIL_LASTRO, excelIr, excelSaidas, filtrarComprovantes, pdfIr, pdfSaidas, resumoIr, validarFiltrosSaidas } from './relatorio-fiscal.js';

const estado = { perfilId: null, perfil: null, filtrosDaLista: null };
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
    retornoDoEnvio(enviados, resultados);
    if (!enviados) {
        return { status: recusa ? 409 : 400,
                 corpo: { success: false, error: resultados[0].error, data: resultados, total: resultados.length } };
    }
    const status = enviados < resultados.length ? 207 : 200;
    return { status, corpo: { success: true, data: resultados, total: resultados.length } };
}

// Retorno do envio no painel "Arquivos importados" (acima da lista, que a tela original redesenha a cada envio).
function retornoDoEnvio(enviados, resultados) {
    const aviso = document.getElementById('cf-upload-retorno');
    if (!aviso) return;
    const falhas = resultados.filter((r) => !r.success);
    let texto;
    if (!falhas.length) {
        texto = enviados === 1 ? 'Documento enviado.' : `${enviados} documentos enviados.`;
    } else if (!enviados) {
        const motivos = [...new Set(falhas.map((r) => r.error))];
        texto = `Não foi possível enviar ${falhas.length === 1 ? 'o documento' : 'os documentos'}. `
            + (motivos.length === 1 ? motivos[0] : 'Veja o motivo de cada arquivo abaixo.');
    } else {
        texto = `${enviados} de ${resultados.length} documentos enviados. Os demais não foram enviados; veja o motivo abaixo.`;
    }
    aviso.textContent = texto;
    aviso.dataset.situacao = !falhas.length ? 'sucesso' : (enviados ? 'parcial' : 'erro');
    aviso.setAttribute('role', falhas.length ? 'alert' : 'status');
    aviso.hidden = false;
}

// A tela original marca o arquivo que falhou como "Erro de leitura"; aqui ele aparece como "Não enviado" (o motivo segue
// embaixo do nome). So o cartao de falha tem o selo como neto do cartao (no de documento gravado ele fica em
// .ir-upload-badges, e "Erro de leitura" ali e o status real do documento). Nova selecao esconde o retorno anterior.
function instalarRetornoDoEnvio() {
    const lista = document.getElementById('ir-upload-results');
    if (!lista) return;
    const aviso = document.createElement('p');
    aviso.id = 'cf-upload-retorno';
    aviso.className = 'cf-upload-retorno';
    aviso.hidden = true;
    lista.before(aviso);
    new MutationObserver(() => {
        for (const selo of lista.querySelectorAll('.ir-upload-card > div > .ir-status.erro')) {
            if (selo.textContent !== 'Não enviado') selo.textContent = 'Não enviado';  // sem laco: so muda uma vez
        }
    }).observe(lista, { childList: true, subtree: true });
    const esconder = () => { aviso.hidden = true; };
    document.getElementById('ir-file-input')?.addEventListener('change', esconder);
    document.getElementById('ir-dropzone')?.addEventListener('drop', esconder);
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

const vinculosAtivos = (id) => rpc((a) => supabase.rpc('vinculos_documento_tela', a), { p_perfil_id: estado.perfilId, p_comprovante_id: id });

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

// Lista completa do filtro (ir_comprovantes_tela nao pagina) com os vinculos ATIVOS de cada documento em ordem de id, como
// o Flask os le; so quem tem vinculo e consultado, em grupos pequenos.
async function comprovantesDoRelatorio(filtros) {
    const r = await rpc((a) => supabase.rpc('ir_comprovantes_tela', a), { p_perfil_id: estado.perfilId, p_filtros: filtros, p_id: null });
    const documentos = (r && r.data) || [];
    const comVinculo = documentos.filter((c) => Number(c.vinculos_count) > 0);
    for (let i = 0; i < comVinculo.length; i += 8) {
        await Promise.all(comVinculo.slice(i, i + 8).map(async (c) => {
            c.vinculos = [...(await vinculosAtivos(c.id) || [])].sort((x, y) => x.id - y.id);
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

async function adaptador({ metodo, caminho, parametros, corpo }) {
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

// Acrescimo FIN-PRE-PRODUCAO-1: vinculos ativos com "Desvincular" no modal "Vincular documento" (a tela do Flask so
// criava). Desvincular passa pela mesma rota DELETE (ponte-api): o vinculo fica inativo e a lista e recarregada.
function instalarDesvinculo() {
    const modal = document.getElementById('ir-link-modal');
    const form = document.getElementById('ir-link-form');
    if (!modal || !form) return;
    const secao = document.createElement('section');
    secao.className = 'cf-vinculos-ativos';
    secao.setAttribute('aria-label', 'Vínculos ativos do documento');
    const titulo = document.createElement('h3');
    titulo.textContent = 'Vínculos ativos';
    const listaVinculos = document.createElement('ul');
    secao.append(titulo, listaVinculos);
    form.after(secao);

    async function desvincular(comprovante, vinculo) {
        if (!window.confirm('Desvincular este documento? O vínculo fica inativo e o histórico é preservado.')) return;
        const r = await (await fetch(`/api/ir/comprovantes/${comprovante}/vinculos/${vinculo}`, { method: 'DELETE' })).json();
        if (!r.success) {
            window.alert(r.error || 'Não foi possível desvincular o documento.');
            return;
        }
        await mostrar();
        document.getElementById('ir-btn-atualizar')?.click();
    }

    async function mostrar() {
        const comprovante = Number(document.getElementById('ir-link-comprovante-id')?.value);
        listaVinculos.replaceChildren();
        if (!comprovante) return;
        let vinculos = [];
        try {
            vinculos = await vinculosAtivos(comprovante);
        } catch (_erro) {
            vinculos = [];
        }
        if (!vinculos.length) {
            const vazio = document.createElement('li');
            vazio.className = 'cf-vinculos-vazio';
            vazio.textContent = 'Nenhum vínculo ativo.';
            listaVinculos.append(vazio);
            return;
        }
        for (const v of vinculos) {
            const item = document.createElement('li');
            const texto = document.createElement('span');
            texto.textContent = `${v.tipo_entidade}${v.resumo_entidade ? ` - ${v.resumo_entidade}` : ''} (${v.status_lastro})`;
            const botao = document.createElement('button');
            botao.type = 'button';
            botao.className = 'ir-secondary-btn cf-desvincular';
            botao.textContent = 'Desvincular';
            botao.addEventListener('click', () => desvincular(comprovante, v.id));
            item.append(texto, botao);
            listaVinculos.append(item);
        }
    }

    new MutationObserver(() => {
        if (modal.classList.contains('open')) mostrar();
    }).observe(modal, { attributes: true, attributeFilter: ['class'] });
}

// FIN-MIGRACAO-LASTRO-EMPRESA-01: "Excluir documento" nas acoes de cada linha da lista (a tela original nao tinha), so para
// quem gere o perfil. Usa a rota DELETE (excluir_comprovante confere perfil, escritor, vinculos e documento validado) e
// mostra o motivo da recusa; depois da exclusao a lista e os contadores sao recarregados pela propria tela.
const SVG = 'http://www.w3.org/2000/svg';

function iconeLixeira() {
    const svg = document.createElementNS(SVG, 'svg');
    const atributos = { viewBox: '0 0 24 24', 'aria-hidden': 'true', focusable: 'false', fill: 'none', stroke: 'currentColor',
                        'stroke-width': '1.8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', class: 'cf-icone-lixeira' };
    for (const [nome, valor] of Object.entries(atributos)) svg.setAttribute(nome, valor);
    for (const d of ['M4 7h16', 'M10 11v6M14 11v6', 'M6 7l1 13h10l1-13', 'M9 7V4h6v3']) {
        const caminho = document.createElementNS(SVG, 'path');
        caminho.setAttribute('d', d);
        svg.append(caminho);
    }
    return svg;
}

async function excluirDocumento(id, nome) {
    if (!window.confirm(`Excluir o documento "${nome}"?\nO arquivo e os dados dele saem do sistema. Esta ação não pode ser desfeita.`)) return false;
    const r = await (await fetch(`/api/ir/comprovantes/${id}`, { method: 'DELETE' })).json();
    if (!r.success) {
        window.alert(r.error || 'Não foi possível excluir o documento. Nada foi excluído.');
        return false;
    }
    await window.IRDoc?.carregarComprovantes?.();
    return true;
}

// Correcao autorizada (30/10/2026): "Excluir documento" tambem no rodape da revisao, onde o titular ja trabalha com o
// documento. Mesma rota e mesma confirmacao da lixeira da lista; fecha a revisao so quando a exclusao acontece.
function instalarExclusaoNaRevisao() {
    const rodape = document.querySelector('#ir-review-modal .ir-modal-footer');
    if (!rodape || rodape.querySelector('.cf-revisao-excluir')) return;
    const botao = document.createElement('button');
    botao.type = 'button';
    botao.id = 'cf-review-excluir';
    botao.className = 'ir-secondary-btn cf-revisao-excluir';
    const rotulo = document.createElement('span');
    rotulo.textContent = 'Excluir documento';
    botao.append(iconeLixeira(), rotulo);
    botao.addEventListener('click', async () => {
        const id = Number(document.getElementById('ir-review-id')?.value);
        if (!id) return;
        const nome = (document.getElementById('ir-review-file-name')?.textContent || `Documento #${id}`).trim();
        botao.disabled = true;
        try {
            if (await excluirDocumento(id, nome)) document.getElementById('ir-review-close')?.click();
        } finally {
            botao.disabled = false;
        }
    });
    rodape.prepend(botao);
}

async function instalarExclusao() {
    const corpo = document.getElementById('ir-comprovantes-tbody');
    if (!corpo) return;
    const { data: gere } = await supabase.rpc('pode_gerir_perfil', { p_perfil_id: estado.perfilId });
    if (gere !== true) return;
    instalarExclusaoNaRevisao();

    function acrescentar() {
        for (const revisar of corpo.querySelectorAll('[data-on-click^="window.IRDoc.abrirRevisao("]')) {
            const acoes = revisar.parentElement;
            if (!acoes || acoes.querySelector('.cf-excluir-documento')) continue;  // sem laco: so acrescenta uma vez
            const id = Number(/abrirRevisao\((\d+)\)/.exec(revisar.getAttribute('data-on-click'))?.[1]);
            if (!id) continue;
            const nome = (revisar.closest('tr')?.querySelector('strong')?.textContent || `Documento #${id}`).trim();
            const botao = document.createElement('button');
            botao.type = 'button';
            botao.className = 'ir-icon-btn ir-icon-only cf-excluir-documento';
            botao.title = 'Excluir documento';
            botao.setAttribute('aria-label', 'Excluir documento');
            const rotulo = document.createElement('span');
            rotulo.className = 'sr-only';
            rotulo.textContent = 'Excluir documento';
            botao.append(iconeLixeira(), rotulo);
            botao.addEventListener('click', () => excluirDocumento(id, nome));
            acoes.append(botao);
        }
    }
    new MutationObserver(acrescentar).observe(corpo, { childList: true, subtree: true });
    acrescentar();
}

// FIN-REG-03: "Exportar", "Excel" e "PDF" do relatorio de Imposto de Renda. A tela original navega para a rota do servidor
// (window.location.href); aqui o clique gera o arquivo pela mesma rota (ponte-api) e o entrega como download, com os
// filtros da lista em tela (toda mudanca de filtro recarrega a lista). Os demais botoes ja usam fetch na tela original.
function nomeDoAnexo(resposta, padrao) {
    const m = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(resposta.headers.get('Content-Disposition') || '');
    return m ? m[1].replace(/"/g, '') : padrao;
}

async function baixarRelatorioIr(tipo, botao) {
    const parametros = estado.filtrosDaLista || new URLSearchParams({ ano: String(new Date().getFullYear()) });
    const original = botao.innerHTML;
    botao.disabled = true;
    botao.textContent = 'Gerando...';
    try {
        const resposta = await fetch(`/api/ir/relatorios/${tipo}?${parametros.toString()}`);
        if (!resposta.ok) {
            const erro = await resposta.json().catch(() => ({}));
            throw new Error(erro.error || 'Não foi possível gerar o relatório.');
        }
        const url = URL.createObjectURL(await resposta.blob());
        const link = document.createElement('a');
        link.href = url;
        link.download = nomeDoAnexo(resposta, tipo === 'pdf' ? 'Relatorio_fiscal.pdf' : 'Relatorio_fiscal.xlsx');
        document.body.append(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (erro) {
        window.alert(erro.message || 'Não foi possível gerar o relatório.');
    } finally {
        botao.disabled = false;
        botao.innerHTML = original;
    }
}

function instalarRelatorioIr() {
    const BOTOES = { 'ir-btn-exportar': 'excel', 'ir-btn-excel': 'excel', 'ir-btn-pdf': 'pdf' };
    document.addEventListener('click', (evento) => {
        const botao = evento.target.closest && evento.target.closest('#ir-btn-exportar, #ir-btn-excel, #ir-btn-pdf');
        if (!botao) return;
        evento.preventDefault();
        evento.stopImmediatePropagation();  // a tela original navegaria para /api/ir/relatorios/...
        if (!botao.disabled) baixarRelatorioIr(BOTOES[botao.id], botao);
    }, true);
}

const contextoMoldura = await iniciarMoldura();
if (contextoMoldura && contextoMoldura.perfil) {
    estado.perfilId = contextoMoldura.perfil.id;
    estado.perfil = contextoMoldura.perfil;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
    instalarAberturaDeArquivos(estado.perfilId);  // "Abrir arquivo" (link /api/ir/comprovantes/<id>/arquivo)
    instalarDesvinculo();
    instalarRetornoDoEnvio();
    instalarExclusao();
    instalarRelatorioIr();
} else if (contextoMoldura) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
