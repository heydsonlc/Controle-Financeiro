// Guarda de sessao das paginas protegidas.
//
// Usa getUser(), que valida o token no Supabase Auth, e nao apenas getSession(),
// que so le o armazenamento local e aceitaria um token adulterado. Ainda assim
// isto e experiencia de uso: quem protege os dados e a RLS no banco.

import { supabase } from './cliente.js';

// MOBILE-CONTAS-1: a tela inicial e "Contas do mes"; categorias/contas bancarias segue acessivel.
// FIN-MIGRACAO-FIDELIDADE-FASE-1: todas as paginas do menu da moldura (inclusive "Em migracao").
const PAGINAS_PERMITIDAS = new Set(['contas.html', 'categorias.html', 'receitas.html', 'cartoes.html',
    'configuracoes.html', 'ajuda.html', 'dashboard.html', 'lancamentos.html', 'recorrencias.html',
    'contas-bancarias.html', 'financiamentos.html', 'patrimonio.html', 'documentos-fiscais.html',
    'mobilidade.html', 'importar-cartao.html', 'inicio.html', 'despesas-mobile.html',  // FIN-MVP-MOB-01: Lista de Despesas mobile
    'cartoes-mobile.html',  // FIN-MVP-MOBILE-03: Cartoes mobile
    'receitas-mobile.html',  // FIN-MVP-MOBILE-04: Receitas mobile
    'despesa-nova-mobile.html']);  // FIN-MVP-MOBILE-05: Nova Despesa mobile
const PAGINA_INICIAL = 'contas.html';
// FIN-MVP-MOB-08: no celular a pagina inicial e a pagina principal mobile (inicio.html); tablet e desktop seguem em
// contas.html. Um destino pedido (?next=, acesso direto a uma URL interna) continua valendo em qualquer largura.
export const CELULAR_INICIO = '(max-width: 767px)';
const PAGINA_INICIAL_CELULAR = 'inicio.html';

export function ehCelular() {
    return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(CELULAR_INICIO).matches;
}

export function destinoSeguro(next, celular = ehCelular()) {
    if (PAGINAS_PERMITIDAS.has(next)) return next;
    return celular ? PAGINA_INICIAL_CELULAR : PAGINA_INICIAL;
}

// O Cloudflare Pages tambem serve /contas (sem .html): o destino depois do login e o mesmo.
export function paginaAtual(caminho) {
    const nome = caminho.split('/').pop();
    return nome && !nome.includes('.') ? `${nome}.html` : nome;
}

function irParaLogin() {
    const atual = paginaAtual(window.location.pathname);
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
