// Guarda de sessao das paginas protegidas.
//
// Usa getUser(), que valida o token no Supabase Auth, e nao apenas getSession(),
// que so le o armazenamento local e aceitaria um token adulterado. Ainda assim
// isto e experiencia de uso: quem protege os dados e a RLS no banco.

import { supabase } from './cliente.js';

// MOBILE-CONTAS-1: a tela inicial e "Contas do mes"; categorias/contas bancarias segue acessivel.
const PAGINAS_PERMITIDAS = new Set(['contas.html', 'categorias.html']);
const PAGINA_INICIAL = 'contas.html';

export function destinoSeguro(next) {
    return PAGINAS_PERMITIDAS.has(next) ? next : PAGINA_INICIAL;
}

function irParaLogin() {
    const atual = window.location.pathname.split('/').pop();
    const next = PAGINAS_PERMITIDAS.has(atual) ? `?next=${encodeURIComponent(atual)}` : '';
    window.location.replace(`index.html${next}`);
}

export async function exigirUsuario() {
    const { data, error } = await supabase.auth.getUser();
    if (error || !data || !data.user) {
        await supabase.auth.signOut({ scope: 'local' });
        irParaLogin();
        return null;
    }
    document.body.hidden = false;
    return data.user;
}

export async function sair() {
    await supabase.auth.signOut();
    window.location.replace('index.html');
}
