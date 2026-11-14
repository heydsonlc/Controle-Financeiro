// FIN-FIDELIDADE-MOVIMENTACOES-1 — adaptador da tela original de Contas Bancarias: responde as rotas /api/contas que
// js/original/contas_bancarias.js chama (ponte-api.js), no formato do Flask, com as funcoes do Supabase (20261109090000).
// Regras no banco: gestao do perfil, conta do perfil, saldo pelos movimentos, saldo inicial so sem movimentos, so AJUSTE
// editavel, transferencia pareada, escritor unico do perfil para movimentos, chave contra reenvio, versao do cadastro.
// FIN-MVP-MOBILE-06: a gravacao da transferencia (transferir_entre_contas) fica em js/contas-servico.js, comum a esta tela e
// ao Registrar Lancamento mobile; o comportamento desta tela nao muda.
// FIN-MVP-MOBILE-07: o extrato e a conferencia de saldo tambem (comuns as Contas mobile), sem mudanca.

import { supabase } from './cliente.js';
import { criarChaves, emMigracao, falha, mensagemDeErro, ok } from './adaptador-comum.js';
import { iniciarMoldura } from './moldura.js';
import { conferirSaldo, extratoDaConta, gravarTransferencia } from './contas-servico.js';

const estado = { perfilId: null, versoes: {} };
const chaves = criarChaves();

async function rpc(funcao, args) {
    const { data, error } = await funcao(args);
    if (error) throw error;
    return data;
}

const lembrar = (conta) => {
    if (conta && conta.id) estado.versoes[conta.id] = conta.versao;
    return conta;
};

// Mesma chave enquanto o pedido for o mesmo (reenvio nao duplica); esquecida depois do sucesso.
async function comChave(operacao, executar) {
    const resultado = await executar(chaves.de(operacao));
    chaves.esquecer(operacao);
    return resultado;
}

// ---------------------------------------------------------------------------------------------------------------
// Cadastro
// ---------------------------------------------------------------------------------------------------------------

async function listar(parametros) {
    const contas = (await rpc((a) => supabase.rpc('contas_bancarias_tela', a), { p_perfil_id: estado.perfilId, p_status: parametros.get('status') })) || [];
    contas.forEach(lembrar);
    return ok({ data: contas, total: contas.length });
}

async function buscar(id) {
    return ok({ data: lembrar(await rpc((a) => supabase.rpc('conta_bancaria_tela', a), { p_perfil_id: estado.perfilId, p_conta_bancaria_id: id })) });
}

async function criar(corpo) {
    const conta = await comChave(`criar:${JSON.stringify(corpo)}`, (chave) => rpc((a) => supabase.rpc('criar_conta_bancaria', a),
        { p_perfil_id: estado.perfilId, p_dados: corpo, p_chave: chave }));
    return { status: 201, corpo: { success: true, message: 'Conta criada com sucesso', data: lembrar(conta) } };
}

async function editar(id, dados, mensagem) {
    const conta = await rpc((a) => supabase.rpc('editar_conta_bancaria', a), {
        p_perfil_id: estado.perfilId, p_conta_bancaria_id: id, p_versao: estado.versoes[id] ?? null, p_dados: dados,
    });
    return ok({ message: mensagem, data: lembrar(conta) });
}

// ---------------------------------------------------------------------------------------------------------------
// Extrato, conferencia e movimentos
// ---------------------------------------------------------------------------------------------------------------

// FIN-MVP-MOBILE-07: extrato e conferencia pelo servico comum (js/contas-servico.js), com as mesmas validacoes de antes.
const extrato = (id, parametros) => extratoDaConta(estado.perfilId, id, parametros);
const conferir = (id) => conferirSaldo(estado.perfilId, id);

async function ajustar(id, corpo) {
    const r = await comChave(`ajuste:${id}:${JSON.stringify(corpo)}`, (chave) => rpc((a) => supabase.rpc('ajustar_saldo_conta', a),
        { p_perfil_id: estado.perfilId, p_conta_bancaria_id: id, p_dados: corpo, p_chave: chave }));
    if (r.sem_alteracao) return ok({ message: 'Saldo já está no valor desejado', data: r.conta });
    return { status: 201, corpo: { success: true, message: 'Ajuste criado com sucesso', data: { conta: r.conta, movimento: r.movimento } } };
}

async function editarAjuste(id, movimento, corpo) {
    const data = await rpc((a) => supabase.rpc('editar_ajuste_conta', a), {
        p_perfil_id: estado.perfilId, p_conta_bancaria_id: id, p_movimento_id: movimento, p_dados: corpo,
    });
    return ok({ message: 'Movimento atualizado', data });
}

async function excluirAjuste(id, movimento) {
    await rpc((a) => supabase.rpc('excluir_ajuste_conta', a), { p_perfil_id: estado.perfilId, p_conta_bancaria_id: id, p_movimento_id: movimento });
    return ok({ message: 'Movimento excluído' });
}

async function transferir(corpo) {
    const r = await comChave(`transferir:${JSON.stringify(corpo)}`, (chave) => gravarTransferencia(estado.perfilId, corpo, chave));
    return {
        status: 201,
        corpo: { success: true, message: 'Transferência realizada', data: { transferencia_id: r.transferencia_id, debito: r.debito, credito: r.credito } },
    };
}

// ---------------------------------------------------------------------------------------------------------------
// Rotas
// ---------------------------------------------------------------------------------------------------------------

const ROTAS = [
    ['GET', /^\/api\/contas\/?$/, (m, c, p) => listar(p)],
    ['POST', /^\/api\/contas\/?$/, (m, corpo) => criar(corpo || {})],
    ['POST', /^\/api\/contas\/transferir$/, (m, corpo) => transferir(corpo || {})],
    ['GET', /^\/api\/contas\/(\d+)$/, (m) => buscar(Number(m[1]))],
    ['PUT', /^\/api\/contas\/(\d+)$/, (m, corpo) => editar(Number(m[1]), corpo || {}, 'Conta atualizada com sucesso')],
    ['DELETE', /^\/api\/contas\/(\d+)$/, (m) => editar(Number(m[1]), { status: 'INATIVO' }, 'Conta inativada com sucesso')],
    ['PUT', /^\/api\/contas\/(\d+)\/ativar$/, (m) => editar(Number(m[1]), { status: 'ATIVO' }, 'Conta reativada com sucesso')],
    ['GET', /^\/api\/contas\/(\d+)\/movimentos$/, (m, c, p) => extrato(Number(m[1]), p)],
    ['GET', /^\/api\/contas\/(\d+)\/conferir-saldo$/, (m) => conferir(Number(m[1]))],
    ['POST', /^\/api\/contas\/(\d+)\/ajuste-saldo$/, (m, corpo) => ajustar(Number(m[1]), corpo || {})],
    ['PUT', /^\/api\/contas\/(\d+)\/movimentos\/(\d+)$/, (m, corpo) => editarAjuste(Number(m[1]), Number(m[2]), corpo || {})],
    ['DELETE', /^\/api\/contas\/(\d+)\/movimentos\/(\d+)$/, (m) => excluirAjuste(Number(m[1]), Number(m[2]))],
];

async function adaptador({ metodo, caminho, parametros, corpo }) {
    for (const [verbo, padrao, executar] of ROTAS) {
        const m = padrao.exec(caminho);
        if (m && verbo === metodo) {
            try {
                return await executar(m, corpo, parametros);
            } catch (erro) {
                // Escritor unico (D5; FIN-ESCRITOR-UNICO-CONTAS-1): perfil nao habilitado vem do hint (mensagemDeErro).
                return falha(mensagemDeErro(erro), 400);
            }
        }
    }
    return emMigracao(`${metodo} ${caminho}`);
}

const contexto = await iniciarMoldura();
if (contexto && contexto.perfil) {
    estado.perfilId = contexto.perfil.id;
    // Quem so le o perfil ve contas, extratos e conferencias, sem as acoes de escrita (o banco recusaria de qualquer forma).
    const { data: gere } = await supabase.rpc('pode_gerir_perfil', { p_perfil_id: estado.perfilId });
    document.body.classList.toggle('cf-somente-leitura', gere !== true);
    window.CF_REGISTRAR_ADAPTADOR(adaptador);
} else if (contexto) {
    window.CF_REGISTRAR_ADAPTADOR(async () => falha('Nenhum perfil financeiro autorizado para esta conta.', 403));
}
