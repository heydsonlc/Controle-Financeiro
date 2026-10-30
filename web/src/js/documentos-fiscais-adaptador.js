// FIN-FIDELIDADE-DOCUMENTOS-1 (fase 1) — adaptador da tela original de Imposto de Renda: responde as rotas /api/ir/...
// que js/original/imposto_renda.js chama (ponte-api.js), no formato do Flask. So consulta, modos IRPF e Documentos da
// Empresa (migrations 20261113090000 e 20261117090000): contexto, categorias IR, vinculos de categoria, comprovantes com
// resumo e detalhe, taxonomia, metadados e resumo empresariais e as saidas sem documento.
// FIN-DOCUMENTOS-2 (migration 20261128090000): envio de arquivo (guardado no banco, privado do perfil, com as validacoes
// do Flask e duplicidade por hash), revisao, validacao, vinculos e despesa/lancamento a partir do documento, com o
// escritor unico do perfil. O texto de PDF textual e extraido aqui (pdf.js, sem servico externo); sem ele, revisao
// manual. Ainda nao disponiveis nesta versao: OCR de imagem, categorias IR e relatorios (Excel/PDF/ZIP).
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
import { instalarAberturaDeArquivos, recusarNavegacao } from './arquivo-comprovante.js';
import { comprovanteDoPerfil, erroDeDocumento, responderDocumentoFinanceiro } from './documento-financeiro.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };
const chaves = criarChaves();
const NA_FASE_1 = `Documentos fiscais: esta ação (OCR de imagem, categorias IR ou relatórios) ${NAO_DISPONIVEL}`;

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

async function instalarExclusao() {
    const corpo = document.getElementById('ir-comprovantes-tbody');
    if (!corpo) return;
    const { data: gere } = await supabase.rpc('pode_gerir_perfil', { p_perfil_id: estado.perfilId });
    if (gere !== true) return;

    async function excluirDocumento(id, nome) {
        if (!window.confirm(`Excluir o documento "${nome}"?\nO arquivo e os dados dele saem do sistema. Esta ação não pode ser desfeita.`)) return;
        const r = await (await fetch(`/api/ir/comprovantes/${id}`, { method: 'DELETE' })).json();
        if (!r.success) {
            window.alert(r.error || 'Não foi possível excluir o documento. Nada foi excluído.');
            return;
        }
        await window.IRDoc?.carregarComprovantes?.();
    }

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

const contextoMoldura = await iniciarMoldura();
if (contextoMoldura && contextoMoldura.perfil) {
    estado.perfilId = contextoMoldura.perfil.id;
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
    instalarAberturaDeArquivos(estado.perfilId);  // "Abrir arquivo" (link /api/ir/comprovantes/<id>/arquivo)
    instalarDesvinculo();
    instalarRetornoDoEnvio();
    instalarExclusao();
    recusarNavegacao(['#ir-btn-exportar', '#ir-btn-excel', '#ir-btn-pdf'], `Relatório de documentos fiscais (Excel/PDF): ${NAO_DISPONIVEL}`);
} else if (contextoMoldura) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
