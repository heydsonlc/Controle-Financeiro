import { supabase } from './cliente.js';
import { destinoSeguro } from './sessao.js';

const form = document.getElementById('login-form');
const erro = document.getElementById('login-erro');
const enviar = document.getElementById('login-enviar');
const next = destinoSeguro(new URLSearchParams(window.location.search).get('next'));

// Mensagem sempre generica: nao revela se o e-mail existe.
const ERRO_GENERICO = 'E-mail ou senha inválidos.';

function mostrarErro(mensagem) {
    erro.textContent = mensagem;
    erro.hidden = false;
}

const { data: atual } = await supabase.auth.getUser();
if (atual && atual.user) {
    window.location.replace(next);
}

form.addEventListener('submit', async (evento) => {
    evento.preventDefault();
    erro.hidden = true;

    const email = form.email.value.trim().toLowerCase();
    const senha = form.senha.value;
    if (!email || !senha) {
        mostrarErro(ERRO_GENERICO);
        return;
    }

    enviar.disabled = true;
    try {
        const { error } = await supabase.auth.signInWithPassword({ email, password: senha });
        if (error) {
            mostrarErro(ERRO_GENERICO);
            return;
        }
        window.location.replace(next);
    } catch (_falha) {
        mostrarErro('Não foi possível entrar agora. Tente novamente.');
    } finally {
        enviar.disabled = false;
        form.senha.value = '';
    }
});
