// Comum aos adaptadores das telas originais do Flask (FIN-FIDELIDADE-*): respostas no formato do Flask, mensagens do
// banco como o usuario le e chaves de idempotencia. Sem acesso a dados (cada adaptador chama as suas funcoes).

export const ok = (corpo = {}) => ({ status: 200, corpo: { success: true, ...corpo } });
export const falha = (error, status = 400) => ({ status, corpo: { success: false, error } });
export const emMigracao = (funcao) => falha(`${funcao}: em migração para o novo aplicativo. Até lá, continua no sistema atual.`, 501);
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
    const texto = (error && error.message) || '';
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
