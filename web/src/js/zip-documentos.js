// FIN-REG-04 — pacote ZIP dos documentos da Empresa para o contador, montado no navegador, como o DocumentoZipService do
// Flask: indice_documentos.xlsx (abas "Indice" e "Resumo") + os arquivos em pastas pelo tipo documental, com o nome
// "NNN_TIPO_nome.ext". So leitura e sem acesso a rede: recebe os documentos que ir_comprovantes_tela devolve (com
// metadata_empresarial), os vinculos ativos de cada um (o mais recente primeiro, como vinculos_documento_tela) e os bytes
// de cada arquivo; devolve { nome, conteudo }. Os bytes dos arquivos vao para o ZIP sem compressao e sem alteracao.
//
// Diferencas justificadas em relacao ao Flask: o ZIP e "armazenado" (o Flask comprime; o conteudo dos arquivos e o mesmo);
// cada arquivo e conferido com o SHA-256 e o tamanho gravados no banco antes de entrar (o Flask nao confere) e uma
// divergencia interrompe o pacote inteiro.

import { empacotarZip, gerarXlsx } from './exportacao-xlsx.js';

export const ERRO_PERFIL_ZIP = 'Pacote de documentos empresariais disponivel apenas no perfil Empresa.';
export const ERRO_SEM_DOCUMENTOS = 'Nenhum documento encontrado para os filtros selecionados.';
// Limites do pacote montado em memoria no navegador (o conteudo chega em base64 e e copiado para o ZIP).
export const LIMITES = { documentos: 1000, bytesPorArquivo: 40 * 1024 * 1024, bytesNoTotal: 250 * 1024 * 1024 };

const PASTAS_POR_TIPO = {
    PAGAMENTO_REALIZADO: 'pagamentos_realizados', NOTA_FISCAL_RECEBIDA: 'notas_fiscais_recebidas', NOTA_FISCAL_EMITIDA: 'notas_fiscais_emitidas',
    DOCUMENTO_OBRIGATORIO: 'documentos_obrigatorios', DOCUMENTO_SOCIETARIO: 'societarios', PROCURACAO_REPRESENTACAO: 'procuracoes_representacoes',
    CONTRATO_INSTRUMENTO: 'contratos_instrumentos', CERTIDAO_LICENCA: 'certidoes_licencas', PATRIMONIO_IMOBILIZADO: 'patrimonio',
    CONTABIL_FISCAL: 'contabil_fiscal', OUTRO: 'outros',
};
const TIPOS_CURTOS = {
    PAGAMENTO_REALIZADO: 'PAGAMENTO', NOTA_FISCAL_RECEBIDA: 'NF_RECEBIDA', NOTA_FISCAL_EMITIDA: 'NF_EMITIDA', DOCUMENTO_OBRIGATORIO: 'DOC_OBRIGATORIO',
    DOCUMENTO_SOCIETARIO: 'SOC', PROCURACAO_REPRESENTACAO: 'PROCURACAO', CONTRATO_INSTRUMENTO: 'CONTRATO', CERTIDAO_LICENCA: 'CERTIDAO',
    PATRIMONIO_IMOBILIZADO: 'PATRIMONIO', CONTABIL_FISCAL: 'CONTABIL', OUTRO: 'DOC',
};
const STATUS_DOCUMENTAIS = new Set(['ATIVO', 'VALIDO', 'VENCENDO', 'VENCIDO', 'PENDENTE', 'EM_REVISAO', 'AGUARDANDO_CONTADOR', 'SEM_LASTRO',
                                    'COM_LASTRO', 'NAO_APLICAVEL', 'ARQUIVADO']);
const EXTENSOES = { 'application/pdf': '.pdf', 'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif',
                    'text/plain': '.txt', 'text/xml': '.xml', 'application/xml': '.xml', 'application/zip': '.zip' };
const AVISO = 'Pacote gerencial para apoio ao contador. Conferir com a contabilidade antes de entregar obrigacoes fiscais.';

const centavos = (valor) => Math.round(Number(valor || 0) * 100);
const comparar = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

// DocumentoZipService._normalizar_filtros
export function normalizarFiltros(filtros = {}) {
    const dados = { ...filtros };
    if (dados.categoria_fiscal && !dados.categoria_ir_id) dados.categoria_ir_id = dados.categoria_fiscal;
    const status = String(dados.status || '').trim().toUpperCase();
    if (status && !['TODOS', 'TODAS'].includes(status) && !dados.status_documental && STATUS_DOCUMENTAIS.has(status)) {
        dados.status_documental = status;
        delete dados.status;
    }
    return dados;
}

// DocumentoZipService._sanitize_filename
export function nomeLimpo(valor, limite = 80) {
    let texto = String(valor || 'Documento').normalize('NFKD');
    texto = Array.from(texto).filter((c) => c.codePointAt(0) < 128).join('');
    texto = texto.replace(/[/\\:*?"<>|]+/g, ' ').replace(/\s+/g, '_').replace(/^[._ ]+|[._ ]+$/g, '').replace(/[^A-Za-z0-9._-]+/g, '');
    return (texto || 'Documento').slice(0, limite);
}

function extensao(arquivo) {
    if (!arquivo) return '.bin';
    const m = /(\.[A-Za-z0-9]{1,8})$/.exec(arquivo.nome_arquivo || '');
    return m ? m[1].toLowerCase() : (EXTENSOES[String(arquivo.mime_type || '').toLowerCase()] || '.bin');
}

function data(valor) {
    if (!valor) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(valor));
    return m ? `${m[3]}/${m[2]}/${m[1]}` : String(valor);
}

function entidadeVinculada(vinculo) {
    if (!vinculo) return '';
    if (vinculo.resumo_entidade) return vinculo.resumo_entidade;
    if (vinculo.entidade_id) return `${vinculo.tipo_entidade} #${vinculo.entidade_id}`;
    return vinculo.tipo_entidade || '';
}

// DocumentoZipService._montar_entradas: uma entrada por documento, na ordem da consulta. `conteudo` (Uint8Array) e o arquivo
// lido do banco; documento sem arquivo entra so no indice ("Arquivo nao incluido").
export function montarEntradas(documentos) {
    return documentos.map((d, i) => {
        const numero = i + 1;
        const md = d.metadata_empresarial || {};
        const tipo = String(md.tipo_documental || 'OUTRO').toUpperCase();
        const temArquivo = Boolean(d.arquivo);
        const base = md.documento_label || d.prestador_nome || (temArquivo ? d.arquivo.nome_arquivo : null) || `Documento ${d.id}`;
        const nomeArquivo = `${String(numero).padStart(3, '0')}_${TIPOS_CURTOS[tipo] || 'DOC'}_${nomeLimpo(base)}${extensao(d.arquivo)}`;
        const vinculo = (d.vinculos || [])[0] || null;
        const observacoes = [temArquivo ? null : 'Arquivo nao encontrado ou indisponivel', md.observacoes ? String(md.observacoes) : null,
                             d.observacoes ? String(d.observacoes) : null].filter(Boolean).join('; ');
        return {
            numero, id: d.id, conteudo: temArquivo ? (d.conteudo || null) : null,
            nome_zip: temArquivo ? `${PASTAS_POR_TIPO[tipo] || 'outros'}/${nomeArquivo}` : 'Arquivo nao incluido',
            nome_original: temArquivo ? (d.arquivo.nome_arquivo || '') : '',
            documento_label: md.documento_label || d.prestador_nome || `Documento #${d.id}`,
            tipo: md.tipo_documental || 'OUTRO', tipo_label: md.tipo_documental_label || 'Outro',
            categoria_documental: md.categoria_documental_label || 'Sem categoria', categoria_fiscal: d.categoria_ir_nome || '',
            data_emissao: data(md.data_emissao || d.data_documento), data_validade: data(md.data_validade),
            prestador_emissor: d.prestador_nome || md.orgao_emissor || '', cpf_cnpj: d.prestador_cpf_cnpj || '',
            valor: d.valor === null || d.valor === undefined ? null : centavos(d.valor),
            status_documental: md.status_documental || 'ATIVO', status_documental_label: md.status_documental_label || 'Ativo',
            status_lastro: vinculo ? vinculo.status_lastro : 'SEM_DOCUMENTO', entidade_vinculada: entidadeVinculada(vinculo), observacoes,
        };
    });
}

function contagem(entradas, campo) {
    const mapa = new Map();
    for (const e of entradas) mapa.set(e[campo], (mapa.get(e[campo]) || 0) + 1);
    return [...mapa].sort((a, b) => comparar(a[0], b[0]));
}

function descricaoDosFiltros(filtros) {
    const pares = Object.keys(filtros).sort().filter((k) => filtros[k] !== null && filtros[k] !== undefined && filtros[k] !== '')
        .map((k) => `${k}=${filtros[k]}`);
    return pares.length ? pares.join(', ') : 'Sem filtros adicionais';
}

// DocumentoZipService.montar_indice_documentos
export function indiceDocumentos({ entradas, filtros, perfilNome, agora }) {
    const moeda = (c) => ({ numero: c / 100 });
    const linhasIndice = [
        ['Nº', 'Nome original', 'Nome no ZIP', 'Documento', 'Tipo documental', 'Categoria documental', 'Categoria fiscal', 'Data de emissao',
         'Data de validade', 'Prestador / emissor', 'CPF/CNPJ', 'Valor', 'Status documental', 'Status fiscal/lastro', 'Entidade vinculada',
         'Observacoes'],
        ...entradas.map((e) => [e.numero, e.nome_original, e.nome_zip, e.documento_label, e.tipo_label, e.categoria_documental, e.categoria_fiscal,
            e.data_emissao, e.data_validade, e.prestador_emissor, e.cpf_cnpj, e.valor === null ? null : moeda(e.valor), e.status_documental_label,
            e.status_lastro, e.entidade_vinculada, e.observacoes]),
    ];
    const comLastro = entradas.filter((e) => ['COM_DOCUMENTO', 'VALIDADO', 'COM_LASTRO'].includes(e.status_lastro)).length;
    const grupo = (titulo, dados) => [[titulo], ['Nome', 'Quantidade'], ...(dados.length ? dados : [['Nenhum registro', 0]]), []];
    const linhasResumo = [
        ['Perfil financeiro', perfilNome ?? null],
        ['Data/hora de geracao', agora],
        ['Ano-calendario', filtros.ano || 'Todos'],
        ['Filtros aplicados', descricaoDosFiltros(filtros)],
        ['Total de documentos', entradas.length],
        ['Total de valor documentado', moeda(entradas.reduce((s, e) => s + (e.valor || 0), 0))],
        ['Total com lastro', comLastro],
        ['Total sem lastro', Math.max(entradas.length - comLastro, 0)],
        ['Aviso', AVISO],
        [],
        ...grupo('Total por tipo documental', contagem(entradas, 'tipo_label')),
        ...grupo('Total por status', contagem(entradas, 'status_documental_label')),
    ];
    linhasResumo.pop();  // a linha vazia final nao existe na planilha
    const aba = (nome, linhas) => ({ nome, linhas, estilo: 'indice', larguraMinima: 0, larguraMaxima: 48 });
    return gerarXlsx([aba('Indice', linhasIndice), aba('Resumo', linhasResumo)]);
}

// DocumentoZipService._nome_pacote
export function nomeDoPacote(filtros, anoAtual) {
    const ano = nomeLimpo(String(filtros.ano || anoAtual));
    const mes = String(filtros.mes || '').trim();
    if (!mes) return `Documentos_Empresa_${ano}_Contador.zip`;
    return `Documentos_Empresa_${ano}_${/^[+-]?\d+$/.test(mes) ? String(Number(mes)).padStart(2, '0') : nomeLimpo(mes)}_Contador.zip`;
}

// Antes de ler qualquer arquivo: o volume cabe no navegador? Devolve a mensagem de recusa ou null.
export function recusaPorVolume(documentos) {
    const comArquivo = documentos.filter((d) => d.arquivo);
    const mb = (bytes) => `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} MB`;
    if (documentos.length > LIMITES.documentos) {
        return `O pacote teria ${documentos.length} documentos (limite: ${LIMITES.documentos}). Refine os filtros (ano, tipo ou categoria) e gere em partes.`;
    }
    const maior = comArquivo.reduce((m, d) => Math.max(m, Number(d.arquivo.tamanho_bytes) || 0), 0);
    if (maior > LIMITES.bytesPorArquivo) {
        return `Há um arquivo de ${mb(maior)} (limite por arquivo: ${mb(LIMITES.bytesPorArquivo)}). O pacote não foi gerado.`;
    }
    const total = comArquivo.reduce((s, d) => s + (Number(d.arquivo.tamanho_bytes) || 0), 0);
    if (total > LIMITES.bytesNoTotal) {
        return `Os arquivos somam ${mb(total)} (limite do pacote: ${mb(LIMITES.bytesNoTotal)}). Refine os filtros (ano, tipo ou categoria) e gere em partes.`;
    }
    return null;
}

async function sha256(bytes) {
    const resumo = new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', bytes));
    return Array.from(resumo, (b) => b.toString(16).padStart(2, '0')).join('');
}

// O arquivo lido e o que o banco registrou? Tamanho e SHA-256 gravados no envio. Devolve a descricao da divergencia ou null.
export async function divergencia(documento, bytes) {
    const esperado = documento.arquivo || {};
    if (esperado.tamanho_bytes !== null && esperado.tamanho_bytes !== undefined && Number(esperado.tamanho_bytes) !== bytes.length) {
        return 'tamanho diferente do registrado';
    }
    const hash = esperado.hash_arquivo || documento.hash_arquivo;
    if (hash && /^[0-9a-f]{64}$/i.test(hash) && (await sha256(bytes)) !== hash.toLowerCase()) return 'conteúdo diferente do registrado (SHA-256)';
    return null;
}

// entrada: { perfilNome, documentos (cada um com `vinculos` e, se tem arquivo, `conteudo` ja conferido), filtros (ja
// normalizados), agora ('dd/mm/aaaa hh:mm'), anoAtual, quando (Date, opcional: data das entradas do ZIP) }
export function montarPacote({ perfilNome, documentos, filtros, agora, anoAtual, quando = null }) {
    if (!documentos.length) throw new Error(ERRO_SEM_DOCUMENTOS);
    const entradas = montarEntradas(documentos);
    const semConteudo = entradas.filter((e) => e.nome_zip !== 'Arquivo nao incluido' && !(e.conteudo instanceof Uint8Array));
    if (semConteudo.length) throw new Error(`Arquivo do documento nº ${semConteudo[0].numero} não foi lido: o pacote não foi gerado.`);
    const nomes = entradas.filter((e) => e.conteudo).map((e) => e.nome_zip);
    if (new Set(nomes).size !== nomes.length) throw new Error('Nomes de arquivo repetidos no pacote: o pacote não foi gerado.');
    const arquivos = [{ nome: 'indice_documentos.xlsx', conteudo: indiceDocumentos({ entradas, filtros, perfilNome, agora }) },
                      ...entradas.filter((e) => e.conteudo).map((e) => ({ nome: e.nome_zip, conteudo: e.conteudo }))];
    return { nome: nomeDoPacote(filtros, anoAtual), conteudo: empacotarZip(arquivos, quando), entradas };
}
