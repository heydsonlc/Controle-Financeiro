// FIN-MOBILE-11 — Documentos Fiscais mobile (atalho Documentos da pagina principal). Tudo pelo servico comum a tela do
// desktop (js/documentos-servico.js, as mesmas rotas /api/ir/... e as mesmas funcoes do banco); nenhuma regra nova:
// - lista do ano (Imposto de Renda no perfil pessoal, Documentos da Empresa no perfil Empresa), com situacao, busca e
//   filtros; detalhe com os vinculos (lastro); baixar o arquivo;
// - quem gere o perfil: revisar (dados basicos), validar, vincular e desvincular; quem so le, consulta;
// - Empresa: saidas sem documento do mes (resumo, lista, vincular documento e situacao manual);
// - exportacoes do FIN-REG-03/04 (Excel, PDF e, na Empresa, o pacote ZIP), geradas no aparelho.
// FIN-REG-08: incluir documento (fotografar ou selecionar, ler no aparelho, conferir e enviar) em js/documentos-mobile-envio.js.
// So no desktop: classificacao documental da Empresa, exclusao, "gerar financeiro" e patrimonio.
// Sem innerHTML (CSP): tudo por createElement.

import { arquivoDoComprovante } from './arquivo-comprovante.js';
import { dataCurta, deslocarMes, el } from './comum.js';
import { configurarDocumentos, responderDocumentos } from './documentos-servico.js';
import { criarEnvio } from './documentos-mobile-envio.js';
import {
    ajustarCadastrosPelaPermissao, aplicarCompetencia, competenciaInicial, prepararMais, prepararModulos,
} from './mobile-comum.js';
import { criarFila, moeda } from './mobile-formulario.js';
import {
    FALHA_GERAL, SETA, abrirFolha, botao, campo, detalhes, entrada, fecharFolha, icone, mensagem, mostrarAviso, mostrarMensagem,
    prepararFolha, seletor, texto,
} from './mobile-ui.js';
import { carregarPerfis, escolherPerfilAtivo, podeGerirPerfil, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);
const api = criarFila('Documentos', responderDocumentos);
const estado = {
    mes: null,               // 'AAAA-MM' (documentos: vale o ano; saidas: o mes)
    visao: 'documentos',     // 'documentos' | 'saidas' (saidas: so Empresa)
    situacao: { documentos: '', saidas: '' },
    busca: '',
    filtros: { categoria: '', tipo: '', origem: '', valorMinimo: '' },
    perfil: null,
    empresa: false,
    somenteLeitura: true,
    categorias: [],          // categorias de IR / fiscais do contexto
    tipos: [],               // tipos documentais (Empresa)
    documentos: [],
    saidas: [],
    pedido: 0,
};

const SITUACOES = {
    documentos: [['', 'Todos'], ['PENDENTE_REVISAO', 'Pendentes'], ['VALIDADO', 'Validados']],
    saidas: [['', 'Pendentes'], ['SEM_DOCUMENTO', 'Sem lastro'], ['TODOS', 'Todas']],
};
const STATUS = { IMPORTADO: 'Importado', PENDENTE_REVISAO: 'Pendente', CLASSIFICADO: 'Classificado', VALIDADO: 'Validado', ERRO_LEITURA: 'Erro de leitura' };
const LASTRO = { SEM_DOCUMENTO: 'Sem lastro', PENDENTE: 'Sem lastro', COM_DOCUMENTO: 'Com documento', VALIDADO: 'Com documento',
                 AGUARDANDO_CONTADOR: 'Aguardando contador', NAO_APLICAVEL: 'Justificado', DIVERGENTE: 'Divergente' };
const ENTIDADES = [['DESPESA_PREVISTA', 'Despesa prevista'], ['LANCAMENTO', 'Lançamento de cartão'], ['MOVIMENTO_FINANCEIRO', 'Movimento financeiro'],
                   ['PATRIMONIO', 'Patrimônio'], ['FINANCIAMENTO', 'Financiamento'], ['CONTA', 'Conta bancária'], ['OUTRO', 'Outro']];
const NATUREZAS = [['DESPESA_OPERACIONAL', 'Despesa operacional'], ['PATRIMONIO_IMOBILIZADO', 'Patrimônio / Imobilizado'],
                   ['SOFTWARE_ASSINATURA', 'Software / Assinatura'], ['IMPOSTO_TAXA', 'Imposto / taxa'], ['PRO_LABORE', 'Pró-labore'],
                   ['DISTRIBUICAO_LUCROS', 'Distribuição de lucros'], ['REEMBOLSO', 'Reembolso'], ['EMPRESTIMO', 'Empréstimo'],
                   ['ADIANTAMENTO', 'Adiantamento'], ['OUTRO', 'Outro']];
const STATUS_VINCULO = [['PENDENTE', 'Pendente'], ['COM_DOCUMENTO', 'Com documento'], ['VALIDADO', 'Validado'],
                        ['AGUARDANDO_CONTADOR', 'Aguardando contador'], ['DIVERGENTE', 'Divergente'], ['NAO_APLICAVEL', 'Não aplicável']];
const ORIGENS = [['', 'Todas'], ['DESPESA_PREVISTA', 'Despesa prevista'], ['CONTA', 'Conta a pagar'], ['LANCAMENTO', 'Lançamento no cartão'],
                 ['MOVIMENTO_FINANCEIRO', 'Movimento financeiro']];

const ano = () => estado.mes.slice(0, 4);
const nomeDoDocumento = (d) => d.prestador_nome || (d.arquivo && d.arquivo.nome_arquivo) || `Documento #${d.id}`;
const classificacao = (d) => (estado.empresa ? (d.categoria_documental_label || d.tipo_documental_label) : d.categoria_ir_nome) || 'Sem categoria';
const rotuloDe = (pares, chave) => (pares.find(([c]) => c === chave) || [null, chave || '—'])[1];

// ---------------------------------------------------------------------------------------------------------------
// Consultas (os mesmos filtros da tela do desktop)

function filtrosDosDocumentos() {
    const q = new URLSearchParams({ ano: ano() });
    if (estado.situacao.documentos) q.set('status', estado.situacao.documentos);
    if (estado.filtros.categoria) q.set('categoria_ir_id', estado.filtros.categoria);
    if (estado.empresa && estado.filtros.tipo) q.set('tipo_documental', estado.filtros.tipo);
    if (estado.busca) q.set('busca', estado.busca);
    return q;
}

function filtrosDasSaidas() {
    const q = new URLSearchParams({ ano: ano(), mes: String(Number(estado.mes.slice(5, 7))) });
    if (estado.situacao.saidas) q.set('status', estado.situacao.saidas);
    if (estado.filtros.origem) q.set('origem', estado.filtros.origem);
    if (estado.filtros.valorMinimo) q.set('valor_minimo', estado.filtros.valorMinimo);
    if (estado.busca) q.set('busca', estado.busca);
    return q;
}

// ---------------------------------------------------------------------------------------------------------------
// Cabecalho da lista: visao, periodo, situacao e resumo

function desenharControles() {
    aplicarCompetencia(estado.mes);
    const saidas = estado.visao === 'saidas';
    if (!saidas) $('mob-competencia').textContent = ano();  // documentos: por ano, como a tela do desktop
    $('mob-mes-anterior').setAttribute('aria-label', saidas ? 'Mês anterior' : 'Ano anterior');
    $('mob-mes-seguinte').setAttribute('aria-label', saidas ? 'Mês seguinte' : 'Ano seguinte');
    for (const b of $('mob-visoes').querySelectorAll('button')) b.setAttribute('aria-pressed', b.dataset.visao === estado.visao ? 'true' : 'false');
    const atual = estado.situacao[estado.visao];
    $('mob-situacao').replaceChildren(...SITUACOES[estado.visao].map(([chave, rotulo]) => {
        const b = el('button', null, rotulo);
        b.type = 'button';
        b.dataset.situacao = chave;
        b.setAttribute('aria-pressed', chave === atual ? 'true' : 'false');
        b.addEventListener('click', () => { estado.situacao[estado.visao] = chave; carregar(); });
        return b;
    }));
    $('mob-busca').placeholder = saidas ? 'Buscar descrição, categoria ou origem' : 'Buscar prestador, CPF/CNPJ ou observação';
    $('mob-lista-titulo').textContent = saidas ? 'Saídas sem documento' : (estado.empresa ? 'Documentos da Empresa' : 'Comprovantes do Imposto de Renda');
    $('mob-incluir').hidden = saidas || estado.somenteLeitura;  // FIN-REG-08
    const f = estado.filtros;
    $('mob-filtro-marca').hidden = !(saidas ? (f.origem || f.valorMinimo) : (f.categoria || f.tipo));
}

function desenharResumo(pares) {
    const caixa = $('mob-resumo');
    caixa.hidden = !pares;
    if (!pares) return;
    $('mob-resumo-valores').replaceChildren(...pares.map(([rotulo, valor, id]) => {
        const d = el('div');
        const dd = el('dd', null, valor);
        dd.id = id;
        d.append(el('dt', null, rotulo), dd);
        return d;
    }));
}

function vazio(titulo, detalhe) {
    const caixa = el('div', 'mob-vazio');
    caixa.append(el('strong', null, titulo), el('span', null, detalhe));
    return caixa;
}

function linha({ id, tipo, nome, sub, valor, selo, classeSelo, aoAbrir }) {
    const b = el('button', 'mob-linha mob-doc-linha');
    b.type = 'button';
    b.dataset.id = id;
    b.dataset.tipo = tipo;
    const textoLinha = el('span', 'mob-linha-texto');
    textoLinha.append(el('span', 'mob-linha-nome', nome), el('span', 'mob-linha-data', sub));
    const lado = el('span', 'mob-doc-lado');
    lado.append(el('span', 'mob-linha-valor', valor), el('span', `mob-doc-selo ${classeSelo}`, selo));
    b.append(textoLinha, lado, icone(SETA, 'mob-seta'));
    b.title = nome;
    b.setAttribute('aria-label', `${nome}, ${sub}, ${valor}, ${selo}. Ver detalhes`);
    b.addEventListener('click', aoAbrir);
    return b;
}

const classeDoStatus = (status) => (status === 'VALIDADO' ? 'ok' : status === 'ERRO_LEITURA' ? 'erro' : 'pendente');
const classeDoLastro = (status) => (['COM_DOCUMENTO', 'VALIDADO'].includes(status) ? 'ok' : ['NAO_APLICAVEL', 'AGUARDANDO_CONTADOR'].includes(status) ? 'neutro' : 'pendente');

function desenharDocumentos(resumo) {
    const r = resumo || {};
    desenharResumo(estado.empresa && r.documentos_empresa ? [
        ['Documentos', String(r.documentos_empresa.documentos_cadastrados ?? estado.documentos.length), 'mob-resumo-total'],
        ['Sem lastro', String(r.documentos_empresa.sem_lastro ?? 0), 'mob-resumo-sem-lastro'],
        ['Pendentes', String(r.pendentes_revisao ?? 0), 'mob-resumo-pendentes'],
    ] : [
        ['Comprovantes', String(r.total_comprovantes ?? estado.documentos.length), 'mob-resumo-total'],
        ['Dedutível (potencial)', moeda(r.valor_potencialmente_dedutivel), 'mob-resumo-valor'],
        ['Pendentes', String(r.pendentes_revisao ?? 0), 'mob-resumo-pendentes'],
    ]);
    $('mob-lista').replaceChildren(...(estado.documentos.length ? estado.documentos.map((d) => linha({
        id: d.id, tipo: 'documento', nome: nomeDoDocumento(d),
        sub: `${d.data_documento ? dataCurta(d.data_documento) : 'Sem data'} · ${classificacao(d)}`,
        valor: d.valor === null || d.valor === undefined ? '—' : moeda(d.valor),
        selo: STATUS[d.status] || d.status, classeSelo: classeDoStatus(d.status), aoAbrir: () => abrirDocumento(d),
    })) : [vazio('Nenhum documento', 'Nenhum documento neste ano com a situação e os filtros escolhidos.')]));
    const nota = $('mob-nota');
    nota.hidden = !(estado.empresa && estado.filtros.tipo);
    nota.textContent = 'O filtro por tipo considera a classificação gravada na revisão (feita no desktop).';
}

function desenharSaidas(resumo) {
    const r = resumo || {};
    desenharResumo([
        ['Pendentes', String(r.pendencias_total ?? 0), 'mob-resumo-pendentes'],
        ['Com documento', String(r.saidas_com_documento ?? 0), 'mob-resumo-com-documento'],
        ['Sem documento', String(r.quantidade_sem_documento ?? 0), 'mob-resumo-sem-documento'],
    ]);
    $('mob-lista').replaceChildren(...(estado.saidas.length ? estado.saidas.map((s) => linha({
        id: `${s.tipo_entidade}:${s.entidade_id}`, tipo: 'saida', nome: s.descricao || s.origem || 'Saída',
        sub: `${s.data ? dataCurta(s.data) : 'Sem data'} · ${s.origem || '—'}`, valor: moeda(s.valor),
        selo: LASTRO[s.status_lastro] || s.status_lastro, classeSelo: classeDoLastro(s.status_lastro), aoAbrir: () => abrirSaida(s),
    })) : [vazio('Nenhuma saída sem documento', 'Nenhuma saída neste mês com a situação e os filtros escolhidos.')]));
    $('mob-nota').hidden = true;
}

// Nada e gravado nem gerado ao listar.
async function carregar() {
    const pedido = ++estado.pedido;
    const lista = $('mob-lista');
    lista.setAttribute('aria-busy', 'true');
    desenharControles();
    if (estado.visao === 'saidas') {
        const q = filtrosDasSaidas();
        const [saidas, resumo] = await Promise.all([api('GET', `/api/ir/lastro/saidas-sem-documento?${q}`),
                                                    api('GET', `/api/ir/lastro/saidas-sem-documento/resumo?${q}`)]);
        if (pedido !== estado.pedido) return;
        estado.saidas = saidas.success ? (saidas.data || []) : [];
        if (!saidas.success) mostrarAviso(saidas.error || 'Não foi possível carregar as saídas.', 'erro');
        desenharSaidas(resumo.success ? resumo.data : null);
        lista.dataset.carregado = `saidas:${q}`;
    } else {
        const q = filtrosDosDocumentos();
        const r = await api('GET', `/api/ir/comprovantes?${q}`);
        if (pedido !== estado.pedido) return;
        estado.documentos = r.success ? (r.data || []) : [];
        if (!r.success) mostrarAviso(r.error || 'Não foi possível carregar os documentos.', 'erro');
        desenharDocumentos(r.success ? r.resumo : null);
        lista.dataset.carregado = `documentos:${q}`;
    }
    lista.setAttribute('aria-busy', 'false');
}

// ---------------------------------------------------------------------------------------------------------------
// Arquivos: baixar o documento e as exportacoes (geradas no aparelho; nada e enviado a outro lugar)

function salvarArquivo(blob, nome) {
    const url = URL.createObjectURL(blob);
    const link = el('a');
    link.href = url;
    link.download = nome;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 60000);
}

async function comEspera(b, m, tarefa) {
    const rotulo = b.textContent;
    b.disabled = true;
    b.textContent = 'Aguarde...';
    mostrarMensagem(m, '');
    try {
        const erro = await tarefa();
        if (erro) mostrarMensagem(m, erro, 'erro');
        return !erro;
    } catch (erro) {
        console.error('Documentos:', erro);
        mostrarMensagem(m, FALHA_GERAL, 'erro');
        return false;
    } finally {
        b.disabled = false;
        b.textContent = rotulo;
    }
}

// Rota de arquivo do servico (relatorios e ZIP): devolve a mensagem de erro, ou null depois de entregar o arquivo.
async function exportar(caminho) {
    const endereco = new URL(caminho, window.location.origin);
    const r = await responderDocumentos({ metodo: 'GET', caminho: endereco.pathname, parametros: endereco.searchParams, corpo: null });
    if (!r.arquivo) return (r.corpo && r.corpo.error) || 'Não foi possível gerar o arquivo.';
    salvarArquivo(new Blob([r.arquivo.conteudo], { type: r.arquivo.mime }), r.arquivo.nome);
    return null;
}

function abrirExportacao() {
    const saidas = estado.visao === 'saidas';
    const m = mensagem();
    const lista = el('div', 'mob-doc-exportar');
    const opcao = (id, rotulo, caminho) => {
        const b = botao(rotulo);
        b.id = id;
        b.addEventListener('click', () => comEspera(b, m, () => exportar(caminho)));
        lista.append(b);
    };
    if (saidas) {
        const q = filtrosDasSaidas();
        opcao('mob-exportar-excel', 'Excel', `/api/ir/lastro/saidas-sem-documento/relatorio-excel?${q}`);
        opcao('mob-exportar-pdf', 'PDF', `/api/ir/lastro/saidas-sem-documento/relatorio-pdf?${q}`);
    } else {
        const q = filtrosDosDocumentos();
        opcao('mob-exportar-excel', 'Excel', `/api/ir/relatorios/excel?${q}`);
        opcao('mob-exportar-pdf', 'PDF', `/api/ir/relatorios/pdf?${q}`);
        if (estado.empresa) opcao('mob-exportar-zip', 'ZIP', `/api/ir/documentos-empresa/exportar-zip?${q}`);
    }
    const explicacao = saidas ? 'Relatório das saídas sem documento do mês, com a situação e os filtros da tela.'
        : `Relatório dos documentos de ${ano()}, com a situação e os filtros da tela.${estado.empresa ? ' O ZIP traz os arquivos e o índice para o contador.' : ''}`;
    abrirFolha('Exportar', texto(explicacao, 'discreto'), lista, m);
}

// ---------------------------------------------------------------------------------------------------------------
// Documento: detalhe, lastro (vinculos), baixar, revisar, validar e vincular

function cartaoDoArquivo(d) {
    const caixa = el('div', 'mob-doc-arquivo');
    const selo = el('span', 'mob-doc-arquivo-tipo', d.arquivo ? ((/\.([A-Za-z0-9]{1,5})$/.exec(d.arquivo.nome_arquivo || '') || [null, 'DOC'])[1]).toUpperCase() : '—');
    const textoArquivo = el('span', 'mob-doc-arquivo-texto');
    const kb = d.arquivo && d.arquivo.tamanho_bytes ? `${Math.max(1, Math.round(d.arquivo.tamanho_bytes / 1024))} KB` : '';
    textoArquivo.append(el('strong', null, nomeDoDocumento(d)), el('span', null, d.arquivo ? [d.arquivo.nome_arquivo, kb].filter(Boolean).join(' · ') : 'Sem arquivo guardado'));
    caixa.append(selo, textoArquivo);
    return caixa;
}

async function abrirDocumento(d) {
    const corpo = detalhes([
        [estado.empresa ? 'Fornecedor / emissor' : 'Prestador', d.prestador_nome || '—'],
        ['CPF/CNPJ', d.prestador_cpf_cnpj],
        ['Data', d.data_documento ? dataCurta(d.data_documento) : '—'],
        ['Valor', d.valor === null || d.valor === undefined ? '—' : moeda(d.valor)],
        [estado.empresa ? 'Classificação' : 'Categoria IR', classificacao(d)],
        [estado.empresa ? 'Categoria fiscal' : '', estado.empresa ? d.categoria_ir_nome : ''],
        ['Dedutível', estado.empresa || d.dedutivel === null || d.dedutivel === undefined ? '' : (d.dedutivel ? 'Sim' : 'Não')],
        ['Situação', STATUS[d.status] || d.status],
        ['Validade', estado.empresa && d.data_validade ? dataCurta(d.data_validade) : ''],
        ['Observações', d.observacoes],
    ]);
    corpo.id = 'mob-detalhe-documento';
    const lastro = el('section', 'mob-doc-lastro');
    lastro.id = 'mob-detalhe-lastro';
    lastro.append(el('h3', 'mob-doc-subtitulo', 'Lastro (vínculos)'), texto('Carregando...', 'discreto'));
    const m = mensagem();
    const acoes = el('div', 'mob-acoes mob-doc-acoes');
    const acao = (id, rotulo, classe, aoClicar) => {
        const b = botao(rotulo, classe);
        b.id = id;
        b.addEventListener('click', () => aoClicar(b));
        acoes.append(b);
        return b;
    };
    if (d.arquivo) {
        acao('mob-doc-baixar', 'Baixar', '', (b) => comEspera(b, m, async () => {
            const arquivo = await arquivoDoComprovante(estado.perfil.id, d.id);
            salvarArquivo(arquivo.blob, arquivo.nome);
            return null;
        }));
    }
    acao('mob-doc-lastro', 'Lastro', '', () => lastro.scrollIntoView({ block: 'nearest' }));
    if (!estado.somenteLeitura) {
        acao('mob-doc-vincular', 'Vincular', '', () => abrirVinculo(d));
        acao('mob-doc-revisar', 'Revisar', 'primario', () => abrirRevisao(d));
    }
    abrirFolha('Documento', cartaoDoArquivo(d), corpo, acoes, m, lastro);
    desenharLastro(d, lastro, m);
}

async function desenharLastro(d, lastro, m) {
    const r = await api('GET', `/api/ir/comprovantes/${d.id}/vinculos`);
    if (!lastro.isConnected) return;  // o painel ja foi fechado
    const titulo = el('h3', 'mob-doc-subtitulo', 'Lastro (vínculos)');
    if (!r.success) { lastro.replaceChildren(titulo, texto(r.error || 'Não foi possível ler os vínculos.', 'discreto')); return; }
    const vinculos = r.data || [];
    if (!vinculos.length) {
        lastro.replaceChildren(titulo, texto('Nenhum vínculo: este documento ainda não comprova nenhuma saída ou bem.', 'discreto'));
        return;
    }
    const lista = el('ul', 'mob-doc-vinculos');
    for (const v of vinculos) {
        const item = el('li');
        const descricao = el('span', 'mob-doc-vinculo-texto');
        descricao.append(el('strong', null, v.resumo_entidade || `${rotuloDe(ENTIDADES, v.tipo_entidade)}${v.entidade_id ? ` #${v.entidade_id}` : ''}`),
            el('span', null, [rotuloDe(ENTIDADES, v.tipo_entidade), rotuloDe(NATUREZAS, v.natureza), rotuloDe(STATUS_VINCULO, v.status_lastro)].filter(Boolean).join(' · ')));
        item.append(descricao);
        if (!estado.somenteLeitura) {
            const desvincular = botao('Desvincular', 'mob-doc-desvincular');
            desvincular.dataset.vinculo = v.id;
            let confirmando = false;
            desvincular.addEventListener('click', async () => {
                if (!confirmando) {  // segundo toque confirma (o vinculo fica inativo; o historico e preservado)
                    confirmando = true;
                    desvincular.textContent = 'Confirmar';
                    return;
                }
                const ok = await comEspera(desvincular, m, async () => {
                    const resposta = await api('DELETE', `/api/ir/comprovantes/${d.id}/vinculos/${v.id}`);
                    return resposta.success ? null : (resposta.error || 'Não foi possível desvincular.');
                });
                if (ok) { await desenharLastro(d, lastro, m); carregar(); }
            });
            item.append(desvincular);
        }
        lista.append(item);
    }
    lastro.replaceChildren(titulo, lista);
}

function formulario(titulo, campos, rotuloEnviar, aoEnviar, nota = '') {
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const m = mensagem();
    const cancelar = botao('Cancelar');
    cancelar.addEventListener('click', fecharFolha);
    const enviar = botao(rotuloEnviar, 'primario');
    enviar.type = 'submit';
    enviar.id = 'mob-form-enviar';
    const acoes = el('div', 'mob-acoes');
    acoes.append(cancelar, enviar);
    form.append(...campos, ...(nota ? [texto(nota, 'discreto')] : []), m, acoes);
    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (enviar.disabled) return;
        const concluido = await comEspera(enviar, m, aoEnviar);
        if (concluido) { fecharFolha(); await carregar(); }
    });
    abrirFolha(titulo, form);
    return { form, m };
}

// Revisao: os dados basicos do documento, pela mesma rota da tela do desktop (PUT /api/ir/comprovantes/<id>). A categoria de
// despesa e a classificacao documental da Empresa nao sao alteradas aqui (ficam como estao; a edicao delas e no desktop).
function abrirRevisao(d) {
    const data = entrada('date', d.data_documento ? String(d.data_documento).slice(0, 10) : '');
    const prestador = entrada('text', d.prestador_nome || '', { maxlength: '255', autocomplete: 'off' });
    const documento = entrada('text', d.prestador_cpf_cnpj || '', { maxlength: '20', autocomplete: 'off', inputmode: 'numeric' });
    const valor = entrada('number', d.valor ?? '', { step: '0.01', min: '0', inputmode: 'decimal' });
    const anoCalendario = entrada('number', d.ano_calendario ?? ano(), { step: '1', min: '2000', max: '2100', inputmode: 'numeric' });
    const categoria = seletor([['', 'Sem categoria'], ...estado.categorias.map((c) => [c.id, c.nome])], d.categoria_ir_id ?? '');
    const observacoes = el('textarea');
    observacoes.rows = 3;
    observacoes.maxLength = 1000;
    observacoes.value = d.observacoes || '';
    for (const [campoDoForm, id] of [[data, 'mob-rev-data'], [prestador, 'mob-rev-prestador'], [documento, 'mob-rev-documento'], [valor, 'mob-rev-valor'],
        [anoCalendario, 'mob-rev-ano'], [categoria, 'mob-rev-categoria'], [observacoes, 'mob-rev-observacoes']]) campoDoForm.id = id;
    const { form, m } = formulario('Revisar documento', [
        campo(estado.empresa ? 'Fornecedor / emissor' : 'Prestador', prestador), campo('CPF/CNPJ', documento), campo('Data do documento', data),
        campo('Valor', valor), campo('Ano-calendário', anoCalendario), campo(estado.empresa ? 'Categoria fiscal' : 'Categoria IR', categoria),
        campo('Observações', observacoes),
    ], 'Salvar', async () => {
        const r = await api('PUT', `/api/ir/comprovantes/${d.id}`, {
            data_documento: data.value, prestador_nome: prestador.value, prestador_cpf_cnpj: documento.value, valor: valor.value,
            ano_calendario: anoCalendario.value, categoria_id: d.categoria_id ?? null, categoria_ir_id: categoria.value || null,
            observacoes: observacoes.value,
        });
        if (!r.success) return r.error || 'Não foi possível salvar a revisão.';
        mostrarAviso('Documento revisado.');
        return null;
    }, estado.empresa ? 'Tipo, categoria documental, validade e demais dados da Empresa são revisados no desktop.' : '');
    if (d.status !== 'VALIDADO') {
        // Validar: a mesma rota do desktop (o banco confere o que falta); o documento validado sai dos pendentes.
        const validar = botao('Validar');
        validar.id = 'mob-rev-validar';
        validar.addEventListener('click', async () => {
            const ok = await comEspera(validar, m, async () => {
                const r = await api('POST', `/api/ir/comprovantes/${d.id}/validar`);
                if (!r.success) return r.error || 'Não foi possível validar o documento.';
                mostrarAviso('Documento validado.');
                return null;
            });
            if (ok) { fecharFolha(); await carregar(); }
        });
        form.querySelector('.mob-acoes').prepend(validar);
    }
}

// Vinculo: a mesma rota e os mesmos campos da tela do desktop (POST /api/ir/comprovantes/<id>/vinculos).
function abrirVinculo(d) {
    const tipo = seletor(ENTIDADES, 'DESPESA_PREVISTA');
    const entidade = seletor([['', 'Carregando...']], '');
    const natureza = seletor(NATUREZAS, 'DESPESA_OPERACIONAL');
    const status = seletor(STATUS_VINCULO, 'COM_DOCUMENTO');
    const observacoes = el('textarea');
    observacoes.rows = 2;
    observacoes.maxLength = 500;
    for (const [campoDoForm, id] of [[tipo, 'mob-vinc-tipo'], [entidade, 'mob-vinc-entidade'], [natureza, 'mob-vinc-natureza'], [status, 'mob-vinc-status'],
        [observacoes, 'mob-vinc-observacoes']]) campoDoForm.id = id;
    let pedido = 0;
    async function carregarEntidades() {
        const meu = ++pedido;
        if (tipo.value === 'OUTRO') {
            entidade.replaceChildren(new Option('Sem entidade específica', ''));
            entidade.disabled = true;
            return;
        }
        entidade.disabled = true;
        entidade.replaceChildren(new Option('Carregando...', ''));
        const r = await api('GET', `/api/ir/entidades-vinculaveis?tipo=${encodeURIComponent(tipo.value)}`);
        if (meu !== pedido || !entidade.isConnected) return;
        const itens = r.success ? (r.data || []) : [];
        entidade.replaceChildren(new Option(itens.length ? 'Selecione...' : 'Nenhuma entidade encontrada neste perfil', ''),
            ...itens.map((i) => new Option(`${i.label}${i.valor !== null && i.valor !== undefined ? ` - ${moeda(i.valor)}` : ''}`, String(i.id))));
        entidade.disabled = false;
    }
    tipo.addEventListener('change', carregarEntidades);
    formulario('Vincular documento', [
        campo('Tipo de entidade', tipo), campo('Entidade', entidade), campo('Natureza', natureza), campo('Situação do lastro', status),
        campo('Observações', observacoes),
    ], 'Vincular', async () => {
        if (tipo.value !== 'OUTRO' && !entidade.value) return 'Escolha a entidade a vincular.';
        const r = await api('POST', `/api/ir/comprovantes/${d.id}/vinculos`, {
            tipo_entidade: tipo.value, entidade_id: entidade.value || null, natureza: natureza.value, status_lastro: status.value,
            tipo_vinculo: 'COMPROVANTE', observacoes: observacoes.value,
        });
        if (!r.success) return r.error || 'Não foi possível vincular o documento.';
        mostrarAviso('Documento vinculado.');
        return null;
    }, nomeDoDocumento(d));
    carregarEntidades();
}

// ---------------------------------------------------------------------------------------------------------------
// Saida sem documento (Empresa): detalhe, vincular um documento e registrar a situacao (as rotas do desktop)

function abrirSaida(s) {
    const corpo = detalhes([
        ['Data', s.data ? dataCurta(s.data) : '—'],
        ['Descrição', s.descricao || '—'],
        ['Valor', moeda(s.valor)],
        ['Origem', s.origem],
        ['Categoria', s.categoria],
        ['Natureza sugerida', rotuloDe(NATUREZAS, s.natureza_sugerida)],
        ['Situação', LASTRO[s.status_lastro] || s.status_lastro],
        ['Pagamento', s.status_pagamento],
        ['Observações', s.observacoes],
    ]);
    corpo.id = 'mob-detalhe-saida';
    const acoes = el('div', 'mob-acoes mob-doc-acoes');
    if (!estado.somenteLeitura) {
        const situacao = botao('Situação');
        situacao.id = 'mob-saida-situacao';
        situacao.addEventListener('click', () => abrirSituacaoDaSaida(s));
        const vincular = botao('Vincular documento', 'primario');
        vincular.id = 'mob-saida-vincular';
        vincular.addEventListener('click', () => abrirVinculoDaSaida(s));
        acoes.append(situacao, vincular);
    } else {
        const fechar = botao('Fechar');
        fechar.addEventListener('click', fecharFolha);
        acoes.append(fechar);
    }
    abrirFolha('Saída sem documento', corpo, acoes);
}

async function abrirVinculoDaSaida(s) {
    const documento = seletor([['', 'Carregando...']], '');
    documento.id = 'mob-saida-documento';
    documento.disabled = true;
    const status = seletor([['VALIDADO', 'Validado'], ['COM_DOCUMENTO', 'Com documento'], ['PENDENTE', 'Pendente'],
                            ['AGUARDANDO_CONTADOR', 'Aguardando contador'], ['DIVERGENTE', 'Divergente']], 'VALIDADO');
    status.id = 'mob-saida-status';
    const observacoes = el('textarea');
    observacoes.rows = 2;
    observacoes.maxLength = 500;
    observacoes.value = s.observacoes || '';
    formulario('Vincular documento', [campo('Documento', documento), campo('Situação do lastro', status), campo('Observações', observacoes)], 'Vincular', async () => {
        if (!documento.value) return 'Escolha o documento.';
        const r = await api('POST', '/api/ir/lastro/saidas-sem-documento/vincular', {
            tipo_entidade: s.tipo_entidade, entidade_id: s.entidade_id, comprovante_id: documento.value, tipo_vinculo: 'COMPROVANTE',
            natureza: s.natureza_sugerida || 'DESPESA_OPERACIONAL', status_lastro: status.value, observacoes: observacoes.value,
        });
        if (!r.success) return r.error || 'Não foi possível vincular o documento.';
        mostrarAviso('Saída vinculada ao documento.');
        return null;
    }, `${s.descricao || 'Saída'} · ${moeda(s.valor)}`);
    const r = await api('GET', `/api/ir/comprovantes?ano=${ano()}`);
    if (!documento.isConnected) return;
    const itens = r.success ? (r.data || []) : [];
    documento.replaceChildren(new Option(itens.length ? 'Selecione...' : `Nenhum documento em ${ano()}`, ''),
        ...itens.map((d) => new Option(`${nomeDoDocumento(d)}${d.valor !== null && d.valor !== undefined ? ` - ${moeda(d.valor)}` : ''}`, String(d.id))));
    documento.disabled = false;
}

function abrirSituacaoDaSaida(s) {
    const status = seletor([['AGUARDANDO_CONTADOR', 'Aguardando contador'], ['NAO_APLICAVEL', 'Não aplicável (justificado)'], ['PENDENTE', 'Pendente']],
        ['AGUARDANDO_CONTADOR', 'NAO_APLICAVEL', 'PENDENTE'].includes(s.status_lastro) ? s.status_lastro : 'AGUARDANDO_CONTADOR');
    status.id = 'mob-saida-situacao-valor';
    const natureza = seletor(NATUREZAS, s.natureza_sugerida || 'DESPESA_OPERACIONAL');
    const observacoes = el('textarea');
    observacoes.id = 'mob-saida-situacao-observacoes';
    observacoes.rows = 2;
    observacoes.maxLength = 500;
    observacoes.value = s.observacoes || '';
    formulario('Situação da saída', [campo('Situação', status), campo('Natureza', natureza), campo('Justificativa / observações', observacoes)], 'Salvar', async () => {
        const r = await api('POST', '/api/ir/lastro/saidas-sem-documento/status', {
            tipo_entidade: s.tipo_entidade, entidade_id: String(s.entidade_id), status_lastro: status.value, natureza: natureza.value,
            observacoes: observacoes.value,
        });
        if (!r.success) return r.error || 'Não foi possível registrar a situação.';
        mostrarAviso('Situação da saída registrada.');
        return null;
    }, `${s.descricao || 'Saída'} · ${moeda(s.valor)}`);
}

// ---------------------------------------------------------------------------------------------------------------
// Filtros

function abrirFiltros() {
    const saidas = estado.visao === 'saidas';
    const f = estado.filtros;
    const categoria = seletor([['', 'Todas'], ...estado.categorias.map((c) => [c.id, c.nome])], f.categoria);
    categoria.id = 'mob-filtro-categoria';
    const tipo = seletor([['', 'Todos'], ...estado.tipos.map((t) => [t.codigo, t.rotulo])], f.tipo);
    tipo.id = 'mob-filtro-tipo';
    const origem = seletor(ORIGENS, f.origem);
    origem.id = 'mob-filtro-origem';
    const valorMinimo = entrada('number', f.valorMinimo, { step: '0.01', min: '0', inputmode: 'decimal', placeholder: '0,00' });
    valorMinimo.id = 'mob-filtro-valor';
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const limpar = botao('Limpar');
    limpar.id = 'mob-filtros-limpar';
    const aplicar = botao('Aplicar', 'primario');
    aplicar.type = 'submit';
    aplicar.id = 'mob-filtros-aplicar';
    const acoes = el('div', 'mob-acoes');
    acoes.append(limpar, aplicar);
    form.append(...(saidas ? [campo('Origem', origem), campo('Valor mínimo', valorMinimo)]
        : [campo(estado.empresa ? 'Categoria fiscal' : 'Categoria IR', categoria), ...(estado.empresa ? [campo('Tipo documental', tipo)] : [])]), acoes);
    limpar.addEventListener('click', () => {
        Object.assign(estado.filtros, saidas ? { origem: '', valorMinimo: '' } : { categoria: '', tipo: '' });
        fecharFolha();
        carregar();
    });
    form.addEventListener('submit', (evento) => {
        evento.preventDefault();
        Object.assign(estado.filtros, saidas ? { origem: origem.value, valorMinimo: valorMinimo.value } : { categoria: categoria.value, tipo: tipo.value });
        fecharFolha();
        carregar();
    });
    abrirFolha('Filtros', form);
}

// Documentos: seta muda o ano; saidas: o mes.
function trocarPeriodo(delta) {
    estado.mes = estado.visao === 'saidas' ? deslocarMes(estado.mes, delta) : `${Number(ano()) + delta}-${estado.mes.slice(5, 7)}`;
    carregar();
}

// ---------------------------------------------------------------------------------------------------------------
// Inicio

const usuario = await exigirUsuario();
if (usuario) {
    estado.mes = competenciaInicial();
    prepararModulos();
    prepararMais();
    prepararFolha();
    aplicarCompetencia(estado.mes);
    let perfil = null;
    try {
        perfil = escolherPerfilAtivo(await carregarPerfis(), usuario.id);
        if (perfil) salvarPerfilAtivo(usuario.id, perfil.id);
    } catch (_erro) {
        mostrarAviso('Não foi possível carregar os perfis financeiros.', 'erro');
    }
    if (perfil) {
        estado.perfil = perfil;
        estado.empresa = perfil.tipo === 'EMPRESA';
        $('mob-perfil').textContent = perfil.nome || '';
        configurarDocumentos(perfil);
        estado.somenteLeitura = !(await podeGerirPerfil(perfil.id).catch(() => false));
        $('mob-somente-leitura').hidden = !estado.somenteLeitura;
        if (estado.somenteLeitura) ajustarCadastrosPelaPermissao(usuario.id);
        const contexto = await api('GET', '/api/ir/contexto');
        if (contexto.success && contexto.data) {
            estado.categorias = contexto.data.categorias || [];
            estado.tipos = (contexto.data.taxonomia_documental && contexto.data.taxonomia_documental.tipos_documentais) || [];
        }
        // Saidas sem documento: so no perfil Empresa (a visao nem aparece nos demais).
        $('mob-visoes').hidden = !estado.empresa;
        const pedida = new URLSearchParams(window.location.search).get('visao');
        if (estado.empresa && pedida === 'saidas') estado.visao = 'saidas';
        for (const b of $('mob-visoes').querySelectorAll('button')) {
            b.addEventListener('click', () => {
                if (estado.visao === b.dataset.visao) return;
                estado.visao = b.dataset.visao;
                estado.busca = '';
                $('mob-busca').value = '';
                carregar();
            });
        }
        let espera = null;
        $('mob-busca').addEventListener('input', () => {
            window.clearTimeout(espera);
            espera = window.setTimeout(() => { estado.busca = $('mob-busca').value.trim(); carregar(); }, 300);
        });
        // FIN-REG-08: incluir documento. Depois do envio, a lista e recarregada no ano do documento (e o detalhe, se pedido).
        const envio = criarEnvio({
            perfil,
            ano: () => ano(),
            aoEnviado: async (id, abrirDetalhe) => {
                const doc = (await api('GET', `/api/ir/comprovantes/${id}`)).data;
                if (doc && doc.ano_calendario && String(doc.ano_calendario) !== ano()) estado.mes = `${doc.ano_calendario}-${estado.mes.slice(5, 7)}`;
                await carregar();
                const daLista = estado.documentos.find((d) => d.id === id);
                if (abrirDetalhe && daLista) abrirDocumento(daLista);
            },
        });
        $('mob-incluir').addEventListener('click', envio.abrir);
        $('mob-filtros').addEventListener('click', abrirFiltros);
        $('mob-exportar').addEventListener('click', abrirExportacao);
        $('mob-mes-anterior').addEventListener('click', () => trocarPeriodo(-1));
        $('mob-mes-seguinte').addEventListener('click', () => trocarPeriodo(1));
        await carregar();
    } else {
        if ($('mob-aviso').hidden) mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
        $('mob-lista').setAttribute('aria-busy', 'false');
    }
}
