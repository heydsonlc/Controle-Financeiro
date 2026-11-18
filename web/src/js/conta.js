// FIN-MULTIUSUARIO-ACESSO-01 — situacao da conta de quem esta conectado.
//
// A identidade e a senha sao do Supabase Auth. O que o aplicativo acrescenta e a SITUACAO da conta: so quem foi convidado
// pelo administrador e ativou a conta usa o aplicativo. Isto aqui e experiencia de uso: quem recusa a conta sem acesso
// liberado e o banco, em toda funcao (financeiro.conta_ativa).

import { supabase } from './cliente.js';

export const PAGINA_PRIMEIRO_ACESSO = 'primeiro-acesso.html';

// { situacao: ATIVA | SUSPENSA | CONVIDADA | CONVITE_EXPIRADO | EMAIL_NAO_CONFIRMADO | SEM_CONVITE, administrador, perfis }
export async function situacaoDaConta() {
    const { data, error } = await supabase.rpc('situacao_da_minha_conta');
    if (error) throw error;
    return data;
}

// Sem perfil nenhum: ou a conta ainda nao foi ativada (primeiro acesso), ou nao tem acesso liberado. Nos dois casos a
// pagina de primeiro acesso explica; a conta ativa sem perfil (todos inativados) segue na tela, como antes.
export async function encaminharSemPerfil() {
    let conta;
    try {
        conta = await situacaoDaConta();
    } catch (_erro) {
        return false;
    }
    if (conta && conta.situacao === 'ATIVA') return false;
    window.location.replace(PAGINA_PRIMEIRO_ACESSO);
    return true;
}

// Atalho de administracao no menu: so para o administrador da plataforma. A resposta fica guardada na aba (por usuario)
// para nao repetir a consulta a cada pagina; a permissao de verdade e conferida no banco em cada operacao.
export async function souAdministrador(usuarioId) {
    const chave = `cf-admin:${usuarioId}`;
    try {
        const salvo = sessionStorage.getItem(chave);
        if (salvo === '1' || salvo === '0') return salvo === '1';
    } catch (_erro) { /* sem armazenamento: consulta sempre */ }
    const { data, error } = await supabase.rpc('sou_administrador_plataforma');
    if (error) return false;
    try {
        sessionStorage.setItem(chave, data === true ? '1' : '0');
    } catch (_erro) { /* idem */ }
    return data === true;
}
