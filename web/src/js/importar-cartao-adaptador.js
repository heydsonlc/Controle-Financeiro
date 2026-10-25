// FIN-FIDELIDADE-CARTOES-1 — adaptador da tela original Importar Cartao: responde as rotas /api/importacao-cartao/...
// que js/original/importar_cartao.js chama (ponte-api.js), no formato do Flask.
// - O arquivo e lido aqui, no navegador (importacao-csv.js): nada do arquivo vai a servidor algum. O banco recebe so
//   as linhas lidas (analisar_importacao_cartao, so leitura) e, depois da confirmacao do usuario na tela,
//   importar_fatura_cartao grava tudo ou nada, com a analise refeita sob trava (duplicidade, conciliacao, fatura
//   paga ou consolidada).
// - XLSX (FIN-FIDELIDADE-CARTOES-2): lido aqui sem biblioteca nova (importacao-xlsx.js), como o openpyxl do Flask.
// - PDF: em migracao (no Flask, pdfplumber no servidor); depende de biblioteca a autorizar (I1).
// - Vincular uma linha a uma recorrencia escolhida: em migracao. Recorrencia no cartao com o mesmo nome e reconhecida
//   na importacao (como reconhecer_despesa_fixa do Flask) e o gerador nao a lanca de novo.

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { converterTabela, decodificar, detectarPerfilCsv, lerCsv, lerData, lerValor, normalizarClassificacao, normalizarDescricao,
    PERFIL_CAIXA, PERFIL_MANUAL, PERFIL_NUBANK } from './importacao-csv.js';
import { lerPlanilha } from './importacao-xlsx.js';
import { iniciarMoldura } from './moldura.js';

const estado = { perfilId: null };
const chaves = criarChaves();
const API = '/api/importacao-cartao';

// 'AAAA-MM', 'AAAA-MM-DD' ou 'MM/AAAA' -> 'AAAA-MM-01' (ou null).
function competencia(valor) {
    const texto = String(valor || '').trim();
    let m = /^(\d{4})-(0[1-9]|1[0-2])(-\d{2})?$/.exec(texto);
    if (m) return `${m[1]}-${m[2]}-01`;
    m = /^(0[1-9]|1[0-2])\/(\d{4})$/.exec(texto);
    return m ? `${m[2]}-${m[1]}-01` : null;
}

async function lerArquivo(formData, somenteCsv = false) {
    const arquivo = formData && formData.get('arquivo');
    if (!arquivo || !arquivo.name) return { erro: 'Nenhum arquivo enviado' };
    const nome = arquivo.name.toLowerCase();
    if (nome.endsWith('.xlsx')) {
        if (somenteCsv) return { erro: 'Apenas arquivos CSV são permitidos' };  // /upload do Flask (mapeamento manual)
        try {
            return { arquivo, origem: 'xlsx', tabela: await lerPlanilha(await arquivo.arrayBuffer()) };
        } catch (erro) {
            return { erro: /^XLSX|^Arquivo XLSX|^Compress/.test(erro.message) ? erro.message : 'Não foi possível ler o arquivo XLSX.' };
        }
    }
    if (!nome.endsWith('.csv')) {
        return { erro: 'Leitura de PDF: em migração para o novo aplicativo. Exporte a fatura em CSV ou XLSX, ou use o sistema atual.', status: 501 };
    }
    try {
        return { arquivo, origem: 'csv', tabela: lerCsv(decodificar(new Uint8Array(await arquivo.arrayBuffer()))) };
    } catch (erro) {
        return { erro: erro.message === 'CSV vazio' ? 'CSV vazio' : 'Não foi possível ler o arquivo CSV.' };
    }
}

// Linha enviada pela tela (formato do Flask) -> linha para o banco, com as regras de normalizacao do Flask.
function linhaParaBanco(l, indice) {
    const original = String(l.descricao_original || l.descricao || l.descricao_exibida || '').trim();
    let [normalizada, parcela, total] = normalizarDescricao(original);
    if (l.numero_parcela && l.total_parcelas) {
        parcela = Number(l.numero_parcela);
        total = Number(l.total_parcelas);
    }
    const valor = lerValor(l.valor);
    return {
        linha_id: l.linha_id || `linha-${indice + 1}`, linha_origem: l.linha_origem || indice + 1,
        data_compra: lerData(l.data_compra), descricao_original: original, descricao_normalizada: normalizada,
        descricao_exibida: String(l.descricao_exibida || '').trim() || normalizada, descricao_classificacao: normalizarClassificacao(normalizada),
        valor: valor === null ? null : valor.replace(/^-/, ''), parcela_atual: parcela, total_parcelas: total,
        // Valor negativo e credito (pagamento, estorno ou ajuste), nunca compra: o sinal nao e descartado.
        tipo_movimento: valor !== null && Number(valor) < 0 ? 'credito' : (l.tipo_movimento || 'debito'), categoria_id: l.categoria_id || l.categoria_despesa_id || null,
        categoria_origem: l.categoria_origem || null, ignorar: Boolean(l.ignorar),
        gerar_parcelas_futuras: Boolean(l.gerar_parcelas_futuras), origem_importacao: l.origem_importacao || 'csv',
    };
}

async function analisar(cartaoId, mes, linhas) {
    const { data, error } = await supabase.rpc('analisar_importacao_cartao', {
        p_perfil_id: estado.perfilId, p_cartao_id: Number(cartaoId), p_competencia: mes, p_linhas: linhas,
    });
    if (error) throw error;
    return data;
}

// Conciliacao do banco -> reconhecimento no formato do Flask (reconhecer_linhas_flexivel): a tela original retira da
// efetivacao a linha "duplicado_atual" com score >= 80 ("Ja existe na fatura").
function reconhecimento(r, indice) {
    const c = r.conciliacao;
    if (!c || typeof c !== 'object') return null;
    return {
        indice, tipo: 'duplicado_atual', score: 90, confianca: 'alta', referencia_id: c.lancamento_id,
        descricao_sugerida: c.descricao, categoria_id: c.categoria_id, valor_referencia: Number(c.valor),
        motivos: [`já lançada no cartão: ${c.descricao}`, 'mesmo valor, parcela e competência', c.recorrente ? 'gerada por recorrência' : 'data próxima'],
        tipo_sugerido: 'ignorar',
    };
}

function linhaParaTela(r, indice) {
    const rec = reconhecimento(r, indice);
    return {
        ...r,
        valor: Number(r.valor),
        motivo_duplicidade: r.duplicidade === 'lote' ? 'Repetida no próprio arquivo.' : (r.duplicidade === 'banco' ? 'Já importada nesta fatura.' : null),
        reconhecimento_match: rec,
        reconhecimento_status: rec ? 'alta' : 'sem_match',
        reconhecimento_score: rec ? rec.score : null,
        reconhecimento_tipo: rec ? rec.tipo : null,
        reconhecimento_acao_recomendada: rec ? 'ignorar' : 'despesa_avulsa',
    };
}

// POST /analisar (FormData): CSV lido aqui; perfil desconhecido pede o mapeamento manual da tela original.
async function analisarArquivo(formData) {
    const lido = await lerArquivo(formData);
    if (lido.erro) return falha(lido.erro, lido.status || 400);
    const cartaoId = formData.get('cartao_id');
    const mes = competencia(formData.get('competencia'));
    if (!cartaoId) return falha('cartao_id obrigatorio');
    if (!mes) return falha('competencia obrigatoria');
    const conv = converterTabela(lido.tabela, lido.origem);
    // XLSX sem cabecalho Nubank ou Caixa: o Flask recusa (nao ha mapeamento manual para XLSX).
    if (lido.origem === 'xlsx' && conv.requer_mapeamento) {
        return falha('XLSX sem cabecalhos reconheciveis. Use colunas equivalentes a CSV Nubank ou Caixa.');
    }
    const base = { origem: lido.origem, arquivo_nome: lido.arquivo.name, cartao_id: Number(cartaoId), competencia: mes.slice(0, 7),
        fatura: { emissor: null, vencimento: null, valor_total: null, cartoes_detectados: [], competencia: `${mes.slice(5, 7)}/${mes.slice(0, 4)}` },
        perfil_detectado: conv.perfil_detectado };
    if (conv.requer_mapeamento) {
        return ok({ data: { ...base, linhas: [], requer_mapeamento: true, validacoes: { total_linhas: conv.total_linhas },
            autodeteccao_confianca: conv.autodeteccao_confianca, mapeamento_sugerido: conv.mapeamento_sugerido, colunas: conv.colunas,
            linhas_dados: conv.linhas_dados, linhas_amostra: conv.linhas_amostra, total_linhas: conv.total_linhas, delimitador: conv.delimitador } });
    }
    if (!conv.linhas.length) return falha('Nenhuma linha de compra encontrada no arquivo.');
    const analise = await analisar(cartaoId, mes, conv.linhas);
    return ok({ data: { ...base, linhas: analise.linhas.map(linhaParaTela), requer_mapeamento: false, confronto_executado: true,
        situacao_fatura: analise.situacao_fatura,
        validacoes: { ...analise.validacoes, total_fatura: 0, diferenca: 0, revisar_totais: false } } });
}

// POST /upload (FormData): leitura e perfil, para o mapeamento manual (a tela mapeia as colunas).
async function upload(formData) {
    const lido = await lerArquivo(formData, true);
    if (lido.erro) return { status: lido.status || 400, corpo: { success: false, message: lido.erro } };
    const info = detectarPerfilCsv(lido.tabela.colunas);
    return ok({ ...lido.tabela, perfil_detectado: info.perfil, autodeteccao_confianca: info.confianca,
        mapeamento_sugerido: info.mapeamento_sugerido,
        perfis_suportados: [{ id: PERFIL_NUBANK, nome: 'Nubank CSV simples' }, { id: PERFIL_CAIXA, nome: 'Caixa (Credito/Debito)' },
            { id: PERFIL_MANUAL, nome: 'Manual generico' }] });
}

const mensagem = (texto, status = 400) => ({ status, corpo: { success: false, message: texto } });

function validarPedido(corpo) {
    const mes = competencia(corpo && corpo.competencia);
    if (!corpo || !corpo.cartao_id) return { erro: 'cartao_id obrigatorio' };
    if (!mes) return { erro: 'competencia obrigatoria' };
    if (!Array.isArray(corpo.linhas) || !corpo.linhas.length) return { erro: 'Nenhuma linha para processar' };
    return { mes, linhas: corpo.linhas.map(linhaParaBanco) };
}

// Resumo no formato de _executar_importacao do Flask, a partir da analise do banco.
function resumo(analise, modo, gravado) {
    const linhas = analise.linhas;
    const aGravar = linhas.filter((l) => !l.ignorar && l.status === 'valido' && l.categoria_id);
    const comErro = linhas.filter((l) => !l.ignorar && !(l.status === 'valido' && l.categoria_id));
    const duplicadas = linhas.filter((l) => ['duplicado', 'conciliado'].includes(l.status));
    const parcelas = (l) => (l.gerar_parcelas_futuras && l.total_parcelas > 1 ? l.total_parcelas - l.parcela_atual + 1 : 1);
    const avisos = linhas.flatMap((l, i) => (l.mensagens || []).map((aviso) => ({ linha: i + 1, aviso, avisos: [aviso] })));
    return {
        success: true, modo, total_recebidas: linhas.length, linhas_validas: aGravar.length, linhas_invalidas: comErro.length,
        inseridos: gravado ? gravado.inseridos : aGravar.reduce((s, l) => s + parcelas(l), 0), duplicados: duplicadas.length,
        erros: comErro.map((l) => ({ linha: l.linha_origem, erro: (l.mensagens || [])[0] || 'Linha precisa de revisão.' })),
        pendencias: { categoria_despesa: aGravar.length ? 0 : comErro.filter((l) => !l.categoria_id).length,
            categoria_cartao: aGravar.filter((l) => !l.categoria_cartao_id).length, avisos: avisos.length },
        avisos_linhas: avisos.slice(0, 50),
        amostra_duplicados: duplicadas.slice(0, 20).map((l) => ({ descricao: l.descricao_exibida, data_compra: l.data_compra,
            valor: Number(l.valor), numero_parcela: l.parcela_atual, total_parcelas: l.total_parcelas,
            origem: l.status === 'conciliado' ? 'conciliacao' : l.duplicidade })),
        amostra_erros: comErro.slice(0, 20).map((l) => ({ descricao: l.descricao_exibida, erro: (l.mensagens || [])[0] })),
        amostra_validos: aGravar.slice(0, 20).map((l) => ({ descricao: l.descricao_exibida, valor: Number(l.valor), data_compra: l.data_compra,
            numero_parcela: l.parcela_atual, total_parcelas: l.total_parcelas, categoria_id: l.categoria_id, categoria_cartao_id: l.categoria_cartao_id })),
    };
}

async function previsualizar(corpo) {
    const v = validarPedido(corpo);
    if (v.erro) return mensagem(v.erro);
    return ok(resumo(await analisar(corpo.cartao_id, v.mes, v.linhas), 'previsualizacao'));
}

async function gravar(cartaoId, mes, linhas) {
    const operacao = `importar:${cartaoId}:${mes}:${JSON.stringify(linhas)}`;
    const { data, error } = await supabase.rpc('importar_fatura_cartao', {
        p_perfil_id: estado.perfilId, p_cartao_id: Number(cartaoId), p_competencia: mes, p_linhas: linhas, p_chave: chaves.de(operacao),
    });
    if (error) return { erro: mensagemDeErro(error) };
    chaves.esquecer(operacao);
    return { gravado: data };
}

async function processar(corpo) {
    const v = validarPedido(corpo);
    if (v.erro) return mensagem(v.erro);
    const analise = await analisar(corpo.cartao_id, v.mes, v.linhas);
    const { erro, gravado } = await gravar(corpo.cartao_id, v.mes, v.linhas);
    if (erro) return mensagem(erro);
    return ok(resumo(analise, 'persistencia', gravado));
}

// POST /parcelamento: a parcela da linha e as futuras (gerar_apenas_atual_e_futuras do Flask).
async function parcelamento(corpo) {
    const linhas = corpo && (corpo.linhas || (corpo.linha ? [corpo.linha] : null));
    if (!Array.isArray(linhas) || linhas.length !== 1) return mensagem('Informe exatamente uma linha para parcelamento');
    const l = { ...linhas[0] };
    const atual = Number(l.numero_parcela || 1);
    const total = Number(l.total_parcelas || 1);
    if (!Number.isInteger(atual) || !Number.isInteger(total) || atual < 1 || total <= 1 || atual > total) return mensagem('Parcela fora do intervalo permitido');
    if (total > 60) return mensagem('Total de parcelas acima do limite permitido');
    return processar({ cartao_id: corpo.cartao_id, competencia: corpo.competencia,
        linhas: [{ ...l, numero_parcela: atual, total_parcelas: total, gerar_parcelas_futuras: true, ignorar: false }] });
}

async function reconhecer(corpo) {
    const v = validarPedido(corpo);
    if (v.erro) return mensagem(v.erro);
    const analise = await analisar(corpo.cartao_id, v.mes, v.linhas);
    return ok({ reconhecimentos: analise.linhas
        .map((r, i) => reconhecimento(r, corpo.linhas[i].indice ?? i)).filter(Boolean) });
}

async function categorias() {
    const { data, error } = await supabase.rpc('categorias_de_despesa');
    if (error) return falha(mensagemDeErro(error));
    return ok({ categorias: (data || []).map((c) => ({ id: c.id, nome: c.nome, cor: c.cor, ativo: true })) });
}

async function categoriasDoCartao(cartaoId) {
    const hoje = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
    const [limites, todas] = await Promise.all([
        supabase.rpc('limites_do_cartao', { p_perfil_id: estado.perfilId, p_cartao_id: cartaoId, p_mes: `${hoje.slice(0, 7)}-01` }),
        supabase.rpc('categorias_cartao_do_perfil', { p_perfil_id: estado.perfilId }),
    ]);
    if (limites.error || todas.error) return falha(mensagemDeErro(limites.error || todas.error));
    const porId = new Map((todas.data || []).map((c) => [c.id, c]));
    const lista = (limites.data || []).filter((l) => l.ativo && porId.get(l.categoria_cartao_id)?.ativo).map((l) => {
        const c = porId.get(l.categoria_cartao_id);
        return { id: c.id, nome: c.nome, cor: c.cor, icone: c.icone, ativo: true, limite_id: l.id,
            limite_mensal: Number(l.limite_mensal), categoria_cartao_id: c.id };
    });
    return ok({ categorias_cartao: lista, data: lista });
}

async function sugerir(corpo) {
    const descricoes = (corpo && corpo.descricoes) || [];
    if (!Array.isArray(descricoes)) return mensagem('descricoes deve ser uma lista');
    const itens = descricoes.filter((d) => d !== null && d !== undefined).map((d) => {
        const [normalizada] = normalizarDescricao(String(d));
        return { descricao: String(d), classificacao: normalizarClassificacao(normalizada), normalizada };
    });
    const { data, error } = await supabase.rpc('sugerir_categorias_importacao', { p_perfil_id: estado.perfilId, p_descricoes: itens });
    if (error) return mensagem(mensagemDeErro(error));
    const fallback = corpo.categoria_fallback_id || null;
    const sugestoes = {};
    for (const [d, s] of Object.entries(data || {})) {
        sugestoes[d] = s.origem === 'sem_sugestao' && fallback ? { ...s, categoria_id: fallback, origem: 'fallback', confianca: 'media' } : s;
    }
    return ok({ sugestoes });
}

async function resolver(parametros) {
    const { data, error } = await supabase.rpc('resolver_categoria_cartao_tela', {
        p_perfil_id: estado.perfilId, p_cartao_id: Number(parametros.get('cartao_id')), p_categoria_id: Number(parametros.get('categoria_id')),
    });
    if (error) return falha(mensagemDeErro(error));
    return ok({ data });
}

// GET /api/cartoes: lista de cartoes ativos (a tela original espera a lista pura, como o Flask devolve).
async function cartoes() {
    const { data, error } = await supabase.rpc('cartoes_do_perfil', { p_perfil_id: estado.perfilId });
    if (error) return falha(mensagemDeErro(error));
    return { status: 200, corpo: (data || []).filter((c) => c.ativo).map((c) => ({ id: c.id, nome: c.nome, tipo: 'Agregador', ativo: true })) };
}

const ROTAS = [
    ['GET', /^\/api\/cartoes\/?$/, () => cartoes()],
    ['POST', new RegExp(`^${API}/analisar$`), (m, corpo) => analisarArquivo(corpo)],
    ['POST', new RegExp(`^${API}/upload$`), (m, corpo) => upload(corpo)],
    ['POST', new RegExp(`^${API}/previsualizar$`), (m, corpo) => previsualizar(corpo)],
    ['POST', new RegExp(`^${API}/processar$`), (m, corpo) => processar(corpo)],
    ['POST', new RegExp(`^${API}/parcelamento$`), (m, corpo) => parcelamento(corpo)],
    ['POST', new RegExp(`^${API}/reconhecer$`), (m, corpo) => reconhecer(corpo)],
    ['POST', new RegExp(`^${API}/recorrencia$`), async () => mensagem('Vincular a linha a uma recorrência escolhida: em migração. '
        + 'Compra recorrente do cartão com o mesmo nome da recorrência já é reconhecida na importação.', 501)],
    ['GET', new RegExp(`^${API}/categorias$`), () => categorias()],
    ['GET', new RegExp(`^${API}/categorias-cartao/(\\d+)$`), (m) => categoriasDoCartao(Number(m[1]))],
    ['POST', new RegExp(`^${API}/sugerir-categorias$`), (m, corpo) => sugerir(corpo)],
    ['GET', /^\/api\/categorias-cartao\/resolver$/, (m, c, p) => resolver(p)],
];

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                return { status: 500, corpo: { success: false, error: mensagemDeErro(erro), message: mensagemDeErro(erro) } };
            }
        }
    }
    return falha(`${metodo} ${caminho}: em migração para o novo aplicativo. Até lá, continua no sistema atual.`, 501);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    // Quem so le o perfil analisa o arquivo, mas nao importa (o banco recusaria de qualquer forma).
    const { data: gere } = await supabase.rpc('pode_gerir_perfil', { p_perfil_id: estado.perfilId });
    document.body.classList.toggle('cf-somente-leitura', !gere);
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
