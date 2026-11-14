// FIN-MVP-MOBILE-06 — transferencia entre contas da tela Contas Bancarias do desktop (FIN-FIDELIDADE-MOVIMENTACOES-1):
// contas ativas do perfil e a gravacao por transferir_entre_contas (movimentos pareados de debito e credito, contas do
// perfil, ativas e diferentes, valor > 0, escritor unico de pagamentos, chave contra reenvio; o saldo e o dos movimentos).
// Extraido de js/contas-bancarias-adaptador.js para servir, sem duplicar regra, a tela Contas Bancarias e o Registrar
// Lancamento mobile. Nada novo no banco; nenhum saldo e alterado diretamente.
// FIN-MVP-MOBILE-07: o extrato (extrato_conta_bancaria: movimentos do periodo, mais recentes primeiro, com o saldo apos
// cada um calculado no banco; limite de 200 como a tela do desktop) e a conferencia de saldo (conferir_saldo_conta, so
// leitura) tambem ficam aqui, comuns a tela Contas Bancarias e as Contas mobile; e a origem de um movimento (a despesa, a
// fatura ou a outra conta da transferencia), so por leituras ja existentes.

import { supabase } from './cliente.js';
import { criarChaves, falha, mensagemDeErro, ok } from './adaptador-comum.js';

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

// Contas do perfil com o saldo pelos movimentos (status: ATIVO, INATIVO ou todas).
export const contasDoPerfil = (perfilId, status = null) => rpc((a) => supabase.rpc('contas_bancarias_tela', a),
    { p_perfil_id: perfilId, p_status: status });

const DATA = /^\d{4}-\d{2}-\d{2}$/;

// GET /api/contas/<id>/movimentos (inicio, fim, limit, incluir_saldo), com as validacoes do Flask.
export async function extratoDaConta(perfilId, id, parametros) {
    const inicio = parametros.get('inicio') || null;
    const fim = parametros.get('fim') || null;
    if ((inicio && !DATA.test(inicio.slice(0, 10))) || (fim && !DATA.test(fim.slice(0, 10)))) {
        return falha('Formato de data invalido. Use YYYY-MM-DD');
    }
    // Como o Flask (type=int): valor nao numerico = padrao.
    const limite = Number.parseInt(parametros.get('limit') ?? '', 10);
    const incluir = Number.parseInt(parametros.get('incluir_saldo') ?? '', 10);
    const movimentos = await rpc((a) => supabase.rpc('extrato_conta_bancaria', a), {
        p_perfil_id: perfilId, p_conta_bancaria_id: id, p_inicio: inicio && inicio.slice(0, 10),
        p_fim: fim && fim.slice(0, 10), p_limite: Number.isNaN(limite) ? 200 : limite,
        p_incluir_saldo: Number.isNaN(incluir) ? true : incluir !== 0,
    });
    return ok({ data: movimentos || [] });
}

// GET /api/contas/<id>/conferir-saldo: saldo registrado x saldo inicial + creditos - debitos (diagnostico, nao altera nada).
export async function conferirSaldo(perfilId, id) {
    return ok({ data: await rpc((a) => supabase.rpc('conferir_saldo_conta', a), { p_perfil_id: perfilId, p_conta_bancaria_id: id }) });
}

// Origem de um movimento, pelas leituras ja existentes: a despesa paga (despesa_para_edicao), a fatura paga
// (dados_pagamento_fatura) e a outra conta da transferencia (o extrato das demais contas na mesma data).
export async function origemDoMovimento(perfilId, parametros) {
    const numero = (nome) => Number(parametros.get(nome)) || null;
    const origem = {};
    // Cada leitura vale por si: a que falhar so deixa de aparecer (o detalhe do movimento continua).
    const lerOuNada = (funcao) => funcao().catch((erro) => { console.error('Origem do movimento:', erro); return null; });
    if (numero('fatura_id')) {
        // O pagamento da fatura tambem traz conta_id (a fatura e uma conta): vale a fatura.
        const f = await lerOuNada(() => rpc((a) => supabase.rpc('dados_pagamento_fatura', a), { p_perfil_id: perfilId, p_fatura_id: numero('fatura_id') }));
        if (f) origem.fatura = { id: f.fatura.id, cartao_id: f.fatura.cartao_id, cartao_nome: f.fatura.cartao_nome, competencia: f.fatura.competencia,
            paga: Boolean(f.fatura.paga) };
    } else if (numero('conta_id')) {
        const d = await lerOuNada(() => rpc((a) => supabase.rpc('despesa_para_edicao', a), { p_perfil_id: perfilId, p_conta_id: numero('conta_id') }));
        if (d) origem.despesa = { id: d.conta.id, nome: d.conta.nome, competencia: d.conta.competencia, situacao: d.conta.status_pagamento };
    }
    const transferencia = parametros.get('transferencia_id');
    const data = parametros.get('data');
    if (transferencia && data && DATA.test(data)) {
        for (const conta of (await contasDoPerfil(perfilId, 'ATIVO')).concat(await contasDoPerfil(perfilId, 'INATIVO'))) {
            if (conta.id === numero('conta_bancaria_id')) continue;
            const lidos = await rpc((a) => supabase.rpc('extrato_conta_bancaria', a), { p_perfil_id: perfilId, p_conta_bancaria_id: conta.id,
                p_inicio: data, p_fim: data, p_limite: 200, p_incluir_saldo: false });
            const par = (lidos || []).find((m) => String(m.transferencia_id) === String(transferencia));
            if (par) { origem.contrapartida = { conta_id: conta.id, conta_nome: conta.nome, tipo: par.tipo }; break; }
        }
    }
    return ok({ data: origem });
}

// A gravacao (a chave da operacao vem de quem chama: repetir nao duplica). Lanca o erro do banco.
export const gravarTransferencia = (perfilId, dados, chave) => rpc((a) => supabase.rpc('transferir_entre_contas', a),
    { p_perfil_id: perfilId, p_dados: dados, p_chave: chave });

// ---------------------------------------------------------------------------------------------------------------
// Rotas para as telas mobile (a tela Contas Bancarias do desktop usa as funcoes acima no seu adaptador)

const estado = { perfilId: null };
const chaves = criarChaves();

// O mesmo corpo da tela Contas Bancarias (salvarTransferencia): origem, destino, valor, data e descricao.
async function transferir(corpo) {
    const operacao = `transferir:${JSON.stringify(corpo)}`;
    const r = await gravarTransferencia(estado.perfilId, corpo, chaves.de(operacao));
    chaves.esquecer(operacao);
    return { status: 201, corpo: { success: true, message: 'Transferência realizada',
        data: { transferencia_id: r.transferencia_id, debito: r.debito, credito: r.credito } } };
}

const ROTAS = [
    ['GET', /^\/api\/contas\/?$/, async (m, c, p) => {
        const contas = (await contasDoPerfil(estado.perfilId, p.get('status'))) || [];
        return ok({ data: contas, total: contas.length });
    }],
    ['POST', /^\/api\/contas\/transferir$/, (m, corpo) => transferir(corpo || {})],
    ['GET', /^\/api\/contas\/(\d+)\/movimentos$/, (m, c, p) => extratoDaConta(estado.perfilId, Number(m[1]), p)],
    ['GET', /^\/api\/contas\/(\d+)\/conferir-saldo$/, (m) => conferirSaldo(estado.perfilId, Number(m[1]))],
    ['GET', /^\/api\/movimentos\/origem$/, (m, c, p) => origemDoMovimento(estado.perfilId, p)],  // FIN-MVP-MOBILE-07
];

// null quando a rota nao e de contas.
export async function responderContas({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                return falha(mensagemDeErro(erro), 400);
            }
        }
    }
    return null;
}

export function configurarContas(perfilId) {
    estado.perfilId = perfilId;
}
