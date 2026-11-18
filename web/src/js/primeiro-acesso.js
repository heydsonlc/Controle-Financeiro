// FIN-MULTIUSUARIO-ACESSO-01 — primeiro acesso.
//
// Quem chega aqui ja entrou (convite aceito e senha definida, ou login). A pagina pergunta ao banco a situacao da PROPRIA
// conta e: (a) convidada -> pede o nome do primeiro perfil e ativa, numa unica operacao no banco (repetir nao duplica);
// (b) ativa -> segue para o aplicativo; (c) sem acesso liberado -> explica e oferece sair. As mensagens nao dizem nada
// sobre outras contas.

import { supabase } from './cliente.js';
import { situacaoDaConta } from './conta.js';
import { destinoSeguro } from './sessao.js';

const $ = (id) => document.getElementById(id);
const AVISOS = {
    SEM_CONVITE: 'Esta conta não tem acesso liberado ao aplicativo. Fale com o administrador.',
    SUSPENSA: 'Esta conta não tem acesso liberado ao aplicativo. Fale com o administrador.',
    CONVITE_EXPIRADO: 'O seu convite expirou. Peça um novo convite ao administrador.',
    EMAIL_NAO_CONFIRMADO: 'Confirme o seu e-mail pelo link recebido e entre de novo.',
};

function mostrarErro(texto) {
    $('pa-erro').textContent = texto;
    $('pa-erro').hidden = false;
}

function seguir() {
    window.location.replace(destinoSeguro(null));
}

async function carregar() {
    $('pa-erro').hidden = true;
    let conta;
    try {
        conta = await situacaoDaConta();
    } catch (_erro) {
        $('pa-subtitulo').textContent = 'Primeiro acesso';
        mostrarErro('Não foi possível verificar a sua conta agora. Tente novamente.');
        return;
    }
    if (conta.situacao === 'ATIVA') {
        // ativa e sem perfil: Configuracoes e onde se cria ou reativa um perfil
        window.location.replace(conta.perfis > 0 ? destinoSeguro(null) : 'configuracoes.html');
        return;
    }
    if (conta.situacao === 'CONVIDADA') {
        $('pa-subtitulo').textContent = 'Bem-vindo. Vamos ativar a sua conta.';
        $('pa-form').hidden = false;
        $('pa-nome').focus();
        return;
    }
    $('pa-subtitulo').textContent = 'Acesso não liberado';
    $('pa-aviso').textContent = AVISOS[conta.situacao] || AVISOS.SEM_CONVITE;
    $('pa-aviso').hidden = false;
}

const { data: sessao } = await supabase.auth.getUser();
if (!sessao || !sessao.user) {
    window.location.replace('index.html');
} else {
    document.body.hidden = false;
    $('pa-email').textContent = sessao.user.email ? `Conectado como ${sessao.user.email}.` : '';
    $('pa-sair').addEventListener('click', async () => {
        await supabase.auth.signOut();
        window.location.replace('index.html');
    });
    $('pa-form').addEventListener('submit', async (evento) => {
        evento.preventDefault();
        $('pa-erro').hidden = true;
        const nome = $('pa-nome').value.trim();
        if (!nome) {
            mostrarErro('Informe o nome do perfil.');
            return;
        }
        $('pa-enviar').disabled = true;
        try {
            const { error } = await supabase.rpc('ativar_minha_conta', { p_dados: { nome, tipo: $('pa-tipo').value } });
            if (error) {
                if (error.hint === 'CONVITE_EXPIRADO' || error.hint === 'SEM_CONVITE' || error.hint === 'CONTA_INATIVA' || error.hint === 'EMAIL_NAO_CONFIRMADO') {
                    $('pa-form').hidden = true;
                    await carregar();
                } else {
                    mostrarErro(error.code === '23505' ? 'Já existe um perfil com este nome.' : (error.code === '22023' && error.message) || 'Não foi possível ativar a conta. Nada foi gravado.');
                }
                return;
            }
            seguir();
        } catch (_falha) {
            mostrarErro('Não foi possível ativar a conta agora. Tente novamente.');
        } finally {
            $('pa-enviar').disabled = false;
        }
    });
    await carregar();
}
