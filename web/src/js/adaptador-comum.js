// Comum aos adaptadores das telas originais do Flask (FIN-FIDELIDADE-*): respostas no formato do Flask, mensagens do
// banco como o usuario le e chaves de idempotencia. Sem acesso a dados (cada adaptador chama as suas funcoes).

export const ok = (corpo = {}) => ({ status: 200, corpo: { success: true, ...corpo } });
export const falha = (error, status = 400) => ({ status, corpo: { success: false, error } });

// FIN-MIGRACAO-P0P1-01: o Flask grava num banco local, fora da producao. Nenhuma mensagem manda o usuario "continuar no
// sistema atual": o que o novo aplicativo nao faz ainda nao esta disponivel, e perfil sem escritor NOVO nao esta habilitado.
export const NAO_DISPONIVEL = 'ainda não está disponível nesta versão do aplicativo. Nada foi gravado.';
export const PERFIL_NAO_HABILITADO = 'Este perfil ainda não está habilitado para gravação no novo aplicativo. Nada foi gravado.';
export const CATALOGO_NAO_HABILITADO = 'O catálogo de categorias de despesa ainda não está habilitado para gravação no novo aplicativo. Nada foi gravado.';
export const emMigracao = (funcao) => falha(`${funcao}: ${NAO_DISPONIVEL}`, 501);

// Recusas do escritor unico (hint do banco), com o mesmo sentido para qualquer tela.
const POR_DICA = {
    SISTEMA_FLASK: PERFIL_NAO_HABILITADO,
    GERADOR_FLASK: 'A geração de recorrências deste perfil ainda não está habilitada no novo aplicativo. Nada foi gravado.',
    CATALOGO_FLASK: CATALOGO_NAO_HABILITADO,
    COM_DOCUMENTOS: 'Este financiamento tem documentos ou conferências da Caixa; a exclusão dele ainda não está disponível nesta versão do aplicativo. Nada foi gravado.',
};
// Textos do banco que ainda citam o sistema atual sem hint proprio.
const TEXTOS_DO_BANCO = [
    [/^Esta categoria ja tem um vinculo legado \(sem perfil\) neste cartao: ajuste-o no sistema atual$/,
        () => 'Esta categoria já tem um vínculo antigo (sem perfil) neste cartão; o ajuste dele ainda não está disponível nesta versão do aplicativo. Nada foi gravado.'],
    [/^(A categoria sistêmica .*) Ela é criada pelo sistema atual; nada foi gravado\.$/, (m) => `${m[1]} Nada foi gravado.`],
];
export const valorTexto = (valor) => (Number(valor) || 0).toFixed(2);

// Motivos de bloqueio do banco (sem acento) como o usuario le (mesmos textos do FIN-DESPESAS-1).
const BLOQUEIOS = {
    'Despesa paga: correcao so por estorno': 'Despesa paga: para corrigir, estorne o pagamento.',
    'Possui movimento financeiro vinculado': 'Possui movimento financeiro vinculado.',
    'Fatura ou compra de cartao: fica no modulo de cartoes': 'Fatura ou compra de cartão: fica no módulo de cartões.',
    'Parcela de consorcio: fica no modulo de consorcios': 'Parcela de consórcio: fica no módulo de consórcios (em migração).',
    'Parcela de financiamento: fica no modulo de financiamentos': 'Parcela de financiamento: fica no módulo de financiamentos (em migração).',
    'Gerada por outro modulo (veiculos, mobilidade ou assinaturas)': 'Gerada por outro módulo (veículos, mobilidade ou assinaturas).',
    'recorrencia gerenciada por outro modulo': 'recorrência de cartão ou de outro módulo: altere no módulo de origem.',
    // FIN-CARTOES-1 (parcela de cartao), mesmos textos da tela de Cartoes anterior.
    'Gerada por recorrencia: edite a recorrencia': 'Gerada por recorrência: altere a recorrência.',
    'Fatura paga: correcao so por estorno': 'Fatura paga: para corrigir, estorne o pagamento da fatura.',
    'Fatura fechada (consolidada)': 'Fatura fechada (consolidada).',
};
export const textoBloqueio = (motivo) => BLOQUEIOS[motivo] || `${motivo}.`;

export function mensagemDeErro(error) {
    if (error && POR_DICA[error.hint]) return POR_DICA[error.hint];
    const texto = (error && error.message) || '';
    for (const [padrao, reescrever] of TEXTOS_DO_BANCO) {
        const m = padrao.exec(texto);
        if (m) return reescrever(m);
    }
    if (/alterad[ao] por outra operacao/i.test(texto)) return 'O registro foi alterado por outra operação. Recarregue e tente de novo.';
    if (/nao autorizado|nao encontrad[ao] neste perfil/i.test(texto)) return 'Operação não autorizada para este perfil.';
    if (/Operacao bloqueada: /i.test(texto)) return `Operação bloqueada: ${textoBloqueio(texto.replace(/^.*Operacao bloqueada: /i, ''))}`;
    if (texto && error.code && /^(22023|P0001|42501)$/.test(error.code)) return texto;
    return 'Não foi possível concluir a operação. Nada foi gravado.';
}

export function hojeBrasilia() {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
}

// Mesma chave em reenvios da mesma operacao (o banco nao duplica); esquecida depois do sucesso.
export function criarChaves() {
    const chaves = {};
    return {
        de: (operacao) => {
            if (!chaves[operacao]) chaves[operacao] = crypto.randomUUID();
            return chaves[operacao];
        },
        esquecer: (operacao) => { delete chaves[operacao]; },
    };
}
