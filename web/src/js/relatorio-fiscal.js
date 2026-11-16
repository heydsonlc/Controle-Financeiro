// FIN-REG-03 — relatorios fiscais gerados no navegador, iguais aos do Flask:
//   IrRelatorioService      Imposto de Renda (perfil Pessoal) e Documentos Fiscais e Lastro (perfil Empresa), Excel e PDF;
//   LastroRelatorioService  Saidas sem documento (so perfil Empresa), Excel e PDF.
// So leitura e sem acesso a rede: as funcoes recebem o que as consultas ja publicadas devolvem (ir_comprovantes_tela,
// vinculos_documento_tela, lastro_saidas_tela) e devolvem { nome, conteudo }. Nada e gravado.
//
// Entrada dos comprovantes: os dicionarios de ir_comprovantes_tela, cada um com `vinculos` = vinculos ATIVOS do documento
// em ordem de id (a ordem em que o Flask os le em `comprovante.vinculos.filter_by(ativo=True)`; o primeiro e o "vinculo
// principal" do relatorio).

import { gerarXlsx } from './exportacao-xlsx.js';
import { pdfSimples } from './exportacao-pdf.js';

// ---- valores --------------------------------------------------------------------------------------------------------
// Numeric(12, 2) do banco: a soma e feita em centavos (inteiros), como o Decimal do Python, e volta como float.
const centavos = (valor) => Math.round(Number(valor || 0) * 100);
const flutuante = (c) => ({ numero: c / 100 });  // celula float: recebe o formato monetario, como no openpyxl
const valorOuVazio = (valor) => (valor === null || valor === undefined ? null : flutuante(centavos(valor)));

// IrRelatorioService._moeda: f"R$ {Decimal:,.2f}" com ponto de milhar e virgula decimal.
export function moeda(valorEmCentavos) {
    const negativo = valorEmCentavos < 0;
    const absoluto = Math.abs(valorEmCentavos);
    const inteiro = String(Math.trunc(absoluto / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return `R$ ${negativo ? '-' : ''}${inteiro},${String(absoluto % 100).padStart(2, '0')}`;
}

function data(valor) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(valor || ''));
    return m ? `${m[3]}/${m[2]}/${m[1]}` : (valor ? String(valor) : null);
}

const verdadeiro = (valor) => ['true', '1', 'sim'].includes(String(valor || '').trim().toLowerCase());
const falso = (valor) => ['false', '0', 'nao'].includes(String(valor || '').trim().toLowerCase());
const maiusculas = (valor) => String(valor || '').trim().toUpperCase();
const comparar = (a, b) => (a < b ? -1 : a > b ? 1 : 0);  // ordem de codigo, como o sorted() do Python
const nomeSeguro = (nome, padrao) => String(nome || padrao).replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '');

function validarAno(filtros) {
    const ano = filtros.ano;
    if (ano !== null && ano !== undefined && ano !== '' && !/^\s*[+-]?\d+\s*$/.test(String(ano))) {
        throw new Error('Ano do relatorio invalido');
    }
}

// ---- Imposto de Renda / Documentos Fiscais ---------------------------------------------------------------------------
const vinculos = (c) => c.vinculos || [];
const principal = (c, campo, padrao = null) => (vinculos(c).length ? (vinculos(c)[0][campo] ?? null) : padrao);
const nomeDoArquivo = (c) => (c.arquivo && c.arquivo.nome_arquivo) || null;

// IrRelatorioService._coletar_comprovantes: filtros do relatorio aplicados sobre a lista ja filtrada pela consulta.
export function filtrarComprovantes(comprovantes, filtros = {}) {
    validarAno(filtros);
    let lista = comprovantes;
    if (verdadeiro(filtros.dedutivel)) lista = lista.filter((c) => c.dedutivel === true);
    else if (falso(filtros.dedutivel)) lista = lista.filter((c) => c.dedutivel === false);
    if (verdadeiro(filtros.somente_validados)) lista = lista.filter((c) => c.status === 'VALIDADO');
    const statusLastro = maiusculas(filtros.status_lastro);
    if (statusLastro && statusLastro !== 'TODOS') lista = lista.filter((c) => principal(c, 'status_lastro', 'SEM_DOCUMENTO') === statusLastro);
    const natureza = maiusculas(filtros.natureza);
    if (natureza) lista = lista.filter((c) => principal(c, 'natureza') === natureza);
    const tipoEntidade = maiusculas(filtros.tipo_entidade);
    if (tipoEntidade) lista = lista.filter((c) => principal(c, 'tipo_entidade') === tipoEntidade);
    if (verdadeiro(filtros.somente_pendentes)) {
        lista = lista.filter((c) => ['SEM_DOCUMENTO', 'PENDENTE', 'DIVERGENTE', 'AGUARDANDO_CONTADOR'].includes(principal(c, 'status_lastro', 'SEM_DOCUMENTO'))
            || ['PENDENTE_REVISAO', 'ERRO_LEITURA', 'IMPORTADO'].includes(c.status));
    }
    return lista;
}

export function resumoIr(comprovantes) {
    return {
        total: comprovantes.length,
        valor_total: comprovantes.reduce((s, c) => s + centavos(c.valor), 0) / 100,
        validados: comprovantes.filter((c) => c.status === 'VALIDADO').length,
        pendentes: comprovantes.filter((c) => ['PENDENTE_REVISAO', 'IMPORTADO'].includes(c.status)).length,
        erros: comprovantes.filter((c) => c.status === 'ERRO_LEITURA').length,
        vinculados: comprovantes.filter((c) => vinculos(c).length > 0).length,
        aguardando_contador: comprovantes.filter((c) => principal(c, 'status_lastro') === 'AGUARDANDO_CONTADOR').length,
    };
}

const valorDedutivel = (comprovantes) => comprovantes.filter((c) => c.dedutivel !== false).reduce((s, c) => s + centavos(c.valor), 0);

function totaisPorCategoria(comprovantes) {
    const grupos = new Map();
    for (const c of comprovantes) {
        const chave = c.categoria_ir_nome || 'Sem categoria IR';
        const g = grupos.get(chave) || { qtd: 0, valor: 0, validados: 0, pendentes: 0 };
        g.qtd += 1;
        g.valor += centavos(c.valor);
        g.validados += c.status === 'VALIDADO' ? 1 : 0;
        g.pendentes += ['PENDENTE_REVISAO', 'IMPORTADO'].includes(c.status) ? 1 : 0;
        grupos.set(chave, g);
    }
    return [...grupos].sort((a, b) => comparar(a[0], b[0])).map(([nome, g]) => ({ nome, ...g }));
}

function totaisPorCategoriaNatureza(comprovantes) {
    const grupos = new Map();
    for (const c of comprovantes) {
        const categoria = c.categoria_ir_nome || 'Sem categoria fiscal';
        const natureza = principal(c, 'natureza') || 'SEM_NATUREZA';
        const chave = JSON.stringify([categoria, natureza]);
        const g = grupos.get(chave) || { categoria, natureza, qtd: 0, valor: 0, lastro: 0, sem: 0 };
        g.qtd += 1;
        g.valor += centavos(c.valor);
        if (vinculos(c).length) g.lastro += 1; else g.sem += 1;
        grupos.set(chave, g);
    }
    return [...grupos.values()].sort((a, b) => comparar(a.categoria, b.categoria) || comparar(a.natureza, b.natureza));
}

const ROTULOS_IR = new Set(['Categoria IR', 'Categoria Fiscal', 'Ano-calendario', 'Ano', 'Documento']);
const abaIr = (nome, linhas) => ({ nome, linhas, estilo: 'relatorio', rotulos: ROTULOS_IR, larguraMaxima: 42 });

function nomeIr({ perfilNome, empresa, filtros, anoAtual }, extensao) {
    return `${empresa ? 'Documentos_Fiscais' : 'IRPF'}_${filtros.ano || anoAtual}_${nomeSeguro(perfilNome, 'Perfil')}.${extensao}`;
}

// entrada: { perfilNome, empresa, comprovantes (ja filtrados), filtros, agora ('dd/mm/aaaa hh:mm'), anoAtual }
export function excelIr(entrada) {
    const { perfilNome, empresa, comprovantes, filtros, agora } = entrada;
    const r = resumoIr(comprovantes);
    let abas;
    if (empresa) {
        const linhasResumo = [
            ['Perfil financeiro', perfilNome ?? null],
            ['Modo', 'Documentos Fiscais e Lastro'],
            ['Ano/periodo', filtros.ano || 'Todos'],
            ['Total de documentos', r.total],
            ['Valor total documentado', flutuante(centavos(r.valor_total))],
            ['Documentos vinculados', r.vinculados],
            ['Documentos sem vinculo', Math.max(r.total - r.vinculados, 0)],
            ['Aguardando contador', r.aguardando_contador],
            ['Data/hora de geracao', agora],
            [],
            ['Categoria Fiscal', 'Natureza', 'Quantidade', 'Valor total', 'Com lastro', 'Sem lastro'],
            ...totaisPorCategoriaNatureza(comprovantes).map((g) => [g.categoria, g.natureza, g.qtd, flutuante(g.valor), g.lastro, g.sem]),
        ];
        const linhasDocumentos = [
            ['Ano', 'Data', 'Prestador/Emissor', 'CPF/CNPJ', 'Valor', 'Categoria Fiscal', 'Categoria de Despesa', 'Natureza',
             'Status do documento', 'Status do lastro', 'Nome do arquivo', 'Observacoes'],
            ...comprovantes.map((c) => [c.ano_calendario ?? null, data(c.data_documento), c.prestador_nome ?? null, c.prestador_cpf_cnpj ?? null,
                valorOuVazio(c.valor), c.categoria_ir_nome ?? null, c.categoria_nome ?? null, principal(c, 'natureza'), c.status ?? null,
                principal(c, 'status_lastro', 'SEM_DOCUMENTO'), nomeDoArquivo(c), c.observacoes ?? null]),
        ];
        const linhasLastros = [['Documento', 'Data', 'Valor', 'Tipo de entidade vinculada', 'ID/Descricao da entidade', 'Tipo de vinculo',
                                'Natureza', 'Status do lastro', 'Observacoes']];
        for (const c of comprovantes) {
            for (const v of vinculos(c)) {
                linhasLastros.push([nomeDoArquivo(c) || `Comprovante ${c.id}`, data(c.data_documento), valorOuVazio(c.valor), v.tipo_entidade ?? null,
                    v.resumo_entidade || (v.entidade_id ?? null), v.tipo_vinculo ?? null, v.natureza ?? null, v.status_lastro ?? null,
                    v.observacoes ?? null]);
            }
        }
        if (linhasLastros.length === 1) linhasLastros.push(['Nenhum vinculo de lastro cadastrado para os filtros selecionados.']);
        abas = [abaIr('Resumo', linhasResumo), abaIr('Documentos', linhasDocumentos), abaIr('Lastros', linhasLastros)];
    } else {
        const linhasResumo = [
            ['Perfil financeiro', perfilNome ?? null],
            ['Modo', 'Imposto de Renda'],
            ['Ano-calendario', filtros.ano || 'Todos'],
            ['Total de comprovantes', r.total],
            ['Valor total potencialmente dedutivel', flutuante(valorDedutivel(comprovantes))],
            ['Quantidade validada', r.validados],
            ['Quantidade pendente', r.pendentes],
            ['Quantidade com erro de leitura', r.erros],
            ['Data/hora de geracao', agora],
            [],
            ['Categoria IR', 'Quantidade', 'Valor total', 'Validados', 'Pendentes'],
            ...totaisPorCategoria(comprovantes).map((g) => [g.nome, g.qtd, flutuante(g.valor), g.validados, g.pendentes]),
        ];
        const linhasComprovantes = [
            ['Ano-calendario', 'Data do documento', 'Prestador', 'CPF/CNPJ', 'Tomador', 'Valor', 'Categoria IR', 'Categoria de Despesa',
             'Dedutivel', 'Status', 'Confianca', 'Origem da classificacao', 'Nome do arquivo', 'Observacoes'],
            ...comprovantes.map((c) => [c.ano_calendario ?? null, data(c.data_documento), c.prestador_nome ?? null, c.prestador_cpf_cnpj ?? null,
                c.tomador_nome ?? null, valorOuVazio(c.valor), c.categoria_ir_nome ?? null, c.categoria_nome ?? null,
                c.dedutivel === true ? 'Sim' : c.dedutivel === false ? 'Nao' : '', c.status ?? null, c.confianca ?? null,
                c.origem_classificacao ?? null, nomeDoArquivo(c), c.observacoes ?? null]),
        ];
        abas = [abaIr('Resumo', linhasResumo), abaIr('Comprovantes', linhasComprovantes)];
    }
    return { nome: nomeIr(entrada, 'xlsx'), conteudo: gerarXlsx(abas) };
}

function linhasDeDocumentos(comprovantes, empresa) {
    return comprovantes.slice(0, 80).map((c) => {
        const partes = [data(c.data_documento) || '-', c.prestador_nome || nomeDoArquivo(c) || 'Sem prestador', c.categoria_ir_nome || '-',
                        moeda(centavos(c.valor)), c.status];
        if (empresa) partes.push(principal(c, 'natureza') || '-', principal(c, 'status_lastro', 'SEM_DOCUMENTO'));
        return partes.map((p) => (p === null || p === undefined ? 'None' : String(p))).join(' | ');
    });
}

export function linhasPdfIr({ perfilNome, empresa, comprovantes, filtros, agora }) {
    const r = resumoIr(comprovantes);
    if (!empresa) {
        return [
            'Relatorio de Comprovantes - Imposto de Renda',
            `Perfil financeiro: ${perfilNome || ''}`,
            `Ano-calendario: ${filtros.ano || 'Todos'}`,
            `Gerado em: ${agora}`,
            '',
            `Total de comprovantes: ${r.total}`,
            `Valor potencialmente dedutivel: ${moeda(valorDedutivel(comprovantes))}`,
            `Pendentes de revisao: ${r.pendentes}`,
            `Validados: ${r.validados}`,
            '',
            'Totais por Categoria IR:',
            ...totaisPorCategoria(comprovantes).map((g) => `- ${g.nome}: ${g.qtd} doc(s), ${moeda(g.valor)}`),
            '', 'Comprovantes:',
            ...linhasDeDocumentos(comprovantes, false),
            '', 'Relatorio informativo. A dedutibilidade deve ser validada pelo contador/responsavel fiscal.',
        ];
    }
    const pendentes = comprovantes.filter((c) => ['SEM_DOCUMENTO', 'DIVERGENTE', 'AGUARDANDO_CONTADOR', 'PENDENTE']
        .includes(principal(c, 'status_lastro', 'SEM_DOCUMENTO')));
    const linhasPendentes = linhasDeDocumentos(pendentes, true);
    return [
        'Relatorio de Documentos Fiscais e Lastro',
        `Perfil financeiro: ${perfilNome || ''}`,
        `Ano/periodo: ${filtros.ano || 'Todos'}`,
        `Gerado em: ${agora}`,
        '',
        `Documentos fiscais: ${r.total}`,
        `Valor documentado: ${moeda(centavos(r.valor_total))}`,
        `Documentos com lastro: ${r.vinculados}`,
        `Documentos sem lastro: ${Math.max(r.total - r.vinculados, 0)}`,
        `Aguardando contador: ${r.aguardando_contador}`,
        '',
        'Totais por Categoria Fiscal/Natureza:',
        ...totaisPorCategoriaNatureza(comprovantes).map((g) => `- ${g.categoria} / ${g.natureza}: ${g.qtd} doc(s), ${moeda(g.valor)}, lastro ${g.lastro}, sem ${g.sem}`),
        '', 'Documentos:',
        ...linhasDeDocumentos(comprovantes, true),
        '', 'Pendencias:',
        ...(linhasPendentes.length ? linhasPendentes : ['Nenhuma pendencia encontrada.']),
        '', 'Relatorio gerencial. A classificacao fiscal/contabil deve ser validada pelo contador.',
    ];
}

export function pdfIr(entrada) {
    return { nome: nomeIr(entrada, 'pdf'), conteudo: pdfSimples(linhasPdfIr(entrada)) };
}

// ---- Saidas sem documento (Lastro, perfil Empresa) -------------------------------------------------------------------
export const ERRO_PERFIL_LASTRO = 'Relatorio de lastro empresarial disponivel apenas no perfil Empresa.';

// LastroRelatorioService._validar_filtros
export function validarFiltrosSaidas(filtros = {}) {
    validarAno(filtros);
    const mes = filtros.mes;
    if (mes !== null && mes !== undefined && mes !== '') {
        if (!/^\s*[+-]?\d+\s*$/.test(String(mes)) || Number(mes) < 1 || Number(mes) > 12) throw new Error('Mes do relatorio invalido');
    }
    return filtros;
}

export function resumoSaidas(saidas) {
    const grupos = { origem: new Map(), natureza: new Map(), status: new Map() };
    const somar = (mapa, chave, valor) => {
        const g = mapa.get(chave) || { quantidade: 0, valor: 0 };
        mapa.set(chave, { quantidade: g.quantidade + 1, valor: g.valor + valor });
    };
    let total = 0;
    for (const s of saidas) {
        const valor = centavos(s.valor);
        total += valor;
        somar(grupos.origem, s.origem || 'Outros', valor);
        somar(grupos.natureza, maiusculas(s.natureza_sugerida || 'OUTRO'), valor);
        somar(grupos.status, maiusculas(s.status_lastro || 'SEM_DOCUMENTO'), valor);
    }
    const ordenar = (mapa) => [...mapa].map(([nome, g]) => ({ nome, ...g })).sort((a, b) => b.valor - a.valor || comparar(a.nome, b.nome));
    const contagem = (status) => (grupos.status.get(status) || { quantidade: 0 }).quantidade;
    return {
        quantidade: saidas.length, valor_total: total, aguardando_contador: contagem('AGUARDANDO_CONTADOR'),
        nao_aplicavel: contagem('NAO_APLICAVEL'), pendente: contagem('PENDENTE') + contagem('SEM_DOCUMENTO'),
        por_origem: ordenar(grupos.origem), por_natureza: ordenar(grupos.natureza), por_status: ordenar(grupos.status),
    };
}

const ROTULOS_LASTRO = new Set(['Data', 'Perfil financeiro', 'Nome', 'Total por origem', 'Total por natureza', 'Total por status']);
const abaLastro = (nome, linhas) => ({ nome, linhas, estilo: 'relatorio', rotulos: ROTULOS_LASTRO, larguraMaxima: 48 });

function nomeSaidas({ perfilNome, filtros, anoAtual }, extensao) {
    const ano = filtros.ano || anoAtual;
    const periodo = filtros.mes ? `${ano}_${String(Number(filtros.mes)).padStart(2, '0')}` : String(ano);
    return `Saidas_sem_documento_${nomeSeguro(perfilNome, 'Empresa')}_${periodo}.${extensao}`;
}

// entrada: { perfilNome, saidas (lastro_saidas_tela, lista), filtros, agora, anoAtual }
export function excelSaidas(entrada) {
    const { perfilNome, saidas, filtros, agora } = entrada;
    const r = resumoSaidas(saidas);
    const grupo = (titulo, dados) => [[titulo], ['Nome', 'Quantidade', 'Valor total'],
        ...(dados.length ? dados.map((g) => [g.nome, g.quantidade, flutuante(g.valor)]) : [['Nenhum registro encontrado', 0, flutuante(0)]]), []];
    const linhasResumo = [
        ['Perfil financeiro', perfilNome ?? null],
        ['Modo', 'Documentos Fiscais e Lastro'],
        ['Ano', filtros.ano || 'Todos'],
        ['Mes', filtros.mes || 'Todos'],
        ['Data/hora de geracao', agora],
        ['Total de saidas sem documento', r.quantidade],
        ['Valor total sem documento', flutuante(r.valor_total)],
        ['Quantidade aguardando contador', r.aguardando_contador],
        ['Quantidade nao aplicavel', r.nao_aplicavel],
        ['Quantidade pendente', r.pendente],
        [],
        ...grupo('Total por origem', r.por_origem), ...grupo('Total por natureza', r.por_natureza), ...grupo('Total por status', r.por_status),
    ];
    while (linhasResumo.length && linhasResumo[linhasResumo.length - 1].length === 0) linhasResumo.pop();  // linha vazia final nao conta
    const linhasSaidas = [
        ['Data', 'Origem', 'Descricao', 'Categoria', 'Valor', 'Natureza sugerida', 'Status do lastro', 'Status financeiro',
         'Tipo da entidade', 'ID da entidade', 'Observacoes'],
        ...saidas.map((s) => [data(s.data), s.origem ?? null, s.descricao ?? null, s.categoria ?? null, flutuante(centavos(s.valor)),
            s.natureza_sugerida ?? null, s.status_lastro ?? null, s.status_pagamento ?? null, s.tipo_entidade ?? null, s.entidade_id ?? null,
            s.observacoes ?? null]),
    ];
    if (!saidas.length) linhasSaidas.push(['Nenhuma saida sem documento encontrada para os filtros selecionados.']);
    const pendencias = saidas.filter((s) => ['AGUARDANDO_CONTADOR', 'PENDENTE', 'DIVERGENTE'].includes(maiusculas(s.status_lastro)));
    const linhasPendencias = [
        ['Data', 'Descricao', 'Valor', 'Natureza', 'Status', 'Observacoes', 'Origem'],
        ...pendencias.map((s) => [data(s.data), s.descricao ?? null, flutuante(centavos(s.valor)), s.natureza_sugerida ?? null,
            s.status_lastro ?? null, s.observacoes ?? null, s.origem ?? null]),
    ];
    if (!pendencias.length) linhasPendencias.push(['Nenhuma pendencia para contador encontrada para os filtros selecionados.']);
    return { nome: nomeSaidas(entrada, 'xlsx'),
             conteudo: gerarXlsx([abaLastro('Resumo', linhasResumo), abaLastro('Saidas_sem_documento', linhasSaidas),
                                  abaLastro('Pendencias_contador', linhasPendencias)]) };
}

const textoCurto = (valor, limite) => {
    const texto = String(valor || '').trim();
    return texto ? Array.from(texto).slice(0, limite).join('') : '-';
};

export function linhasPdfSaidas({ perfilNome, saidas, filtros, agora }) {
    const r = resumoSaidas(saidas);
    const grupo = (dados) => (dados.length ? dados.map((g) => `- ${g.nome}: ${g.quantidade} item(ns), ${moeda(g.valor)}`)
        : ['- Nenhum registro encontrado.']);
    const ano = filtros.ano || 'Todos';
    return [
        'Relatorio de Saidas sem Documento',
        `Perfil financeiro: ${perfilNome}`,
        `Periodo: ${filtros.mes ? `${filtros.mes}/${ano}` : String(ano)}`,
        `Gerado em: ${agora}`,
        '',
        'Resumo executivo',
        `Saidas sem documento: ${r.quantidade}`,
        `Valor total sem lastro: ${moeda(r.valor_total)}`,
        `Aguardando contador: ${r.aguardando_contador}`,
        `Nao aplicavel: ${r.nao_aplicavel}`,
        `Pendente: ${r.pendente}`,
        '',
        'Totais por origem:', ...grupo(r.por_origem),
        '', 'Totais por natureza:', ...grupo(r.por_natureza),
        '', 'Totais por status:', ...grupo(r.por_status),
        '', 'Saidas:',
        ...(saidas.length ? saidas.slice(0, 90).map((s) => [data(s.data) || '-', String(s.origem || '-'), textoCurto(s.descricao, 34),
            moeda(centavos(s.valor)), String(s.natureza_sugerida || '-'), String(s.status_lastro || '-')].join(' | '))
            : ['Nenhuma saida sem documento encontrada para os filtros selecionados.']),
        '',
        'Relatorio gerencial. A classificacao fiscal/contabil deve ser validada pelo contador responsavel.',
    ];
}

export function pdfSaidas(entrada) {
    return { nome: nomeSaidas(entrada, 'pdf'), conteudo: pdfSimples(linhasPdfSaidas(entrada)) };
}
