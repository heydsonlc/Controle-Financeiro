// FIN-MULTIUSUARIO-ACESSO-01 — definicao de senha pelo link de convite ou de recuperacao.
//
// O Supabase Auth valida o link (uso unico, com validade) e devolve a sessao no fragmento do endereco (#access_token=...).
// O fragmento e lido uma vez e retirado do endereco e do historico antes de qualquer outra coisa; nada dele e guardado
// pelo aplicativo alem da sessao do proprio Supabase. A senha e gravada pelo Supabase Auth (o aplicativo nao guarda senha).
// Depois de salvar, as outras sessoes da conta sao encerradas e o usuario segue para o primeiro acesso (que decide se a
// conta precisa ser ativada ou se vai direto para o aplicativo).

import { supabase } from './cliente.js';
import { PAGINA_PRIMEIRO_ACESSO } from './conta.js';

const $ = (id) => document.getElementById(id);
const LINK_INVALIDO = 'Este link não é mais válido: ele pode ter expirado ou já ter sido usado. Peça um novo.';

function mostrarErro(texto) {
    $('ds-erro').textContent = texto;
    $('ds-erro').hidden = false;
}

function linkInvalido() {
    $('ds-subtitulo').textContent = 'Link inválido';
    $('ds-aviso').textContent = LINK_INVALIDO;
    $('ds-aviso').hidden = false;
    $('ds-links').hidden = false;
}

// regra minima da tela (a politica do Supabase Auth continua valendo e pode ser mais exigente)
export function senhaAceita(senha) {
    return typeof senha === 'string' && senha.length >= 10 && senha.length <= 72 && /[A-Za-zÀ-ÿ]/.test(senha) && /\d/.test(senha);
}

const fragmento = new URLSearchParams(window.location.hash.replace(/^#/, ''));
window.history.replaceState(null, '', window.location.pathname);  // o link nao fica no endereco nem no historico

let pronto = false;
const tipo = fragmento.get('type');
if (fragmento.get('error') || fragmento.get('error_code')) {
    linkInvalido();
} else if (fragmento.get('access_token') && fragmento.get('refresh_token') && (tipo === 'invite' || tipo === 'recovery')) {
    try {  // um link adulterado ou cortado pode fazer a biblioteca lancar em vez de devolver o erro
        const { data, error } = await supabase.auth.setSession({ access_token: fragmento.get('access_token'), refresh_token: fragmento.get('refresh_token') });
        pronto = !error && Boolean(data && data.session);
    } catch (_falha) {
        pronto = false;
    }
    if (!pronto) linkInvalido();
} else {
    linkInvalido();  // sem link valido nesta visita, a pagina nao troca a senha de uma sessao ja aberta
}

if (pronto) {
    $('ds-subtitulo').textContent = tipo === 'invite' ? 'Crie a senha da sua conta' : 'Crie uma nova senha';
    $('ds-form').hidden = false;
    $('ds-senha').focus();
    $('ds-form').addEventListener('submit', async (evento) => {
        evento.preventDefault();
        $('ds-erro').hidden = true;
        const senha = $('ds-senha').value;
        if (!senhaAceita(senha)) {
            mostrarErro('A senha precisa ter pelo menos 10 caracteres, com letras e números.');
            return;
        }
        if (senha !== $('ds-confirma').value) {
            mostrarErro('As duas senhas não são iguais.');
            return;
        }
        $('ds-enviar').disabled = true;
        try {
            const { error } = await supabase.auth.updateUser({ password: senha });
            if (error) {
                mostrarErro(/session|jwt|expired/i.test(error.message || '') ? LINK_INVALIDO : 'Não foi possível salvar a senha. Verifique se ela atende às regras e tente de novo.');
                return;
            }
            await supabase.auth.signOut({ scope: 'others' }).catch(() => {});  // encerra as outras sessoes da conta
            window.location.replace(PAGINA_PRIMEIRO_ACESSO);
        } catch (_falha) {
            mostrarErro('Não foi possível salvar a senha agora. Tente novamente.');
        } finally {
            $('ds-enviar').disabled = false;
            $('ds-senha').value = '';
            $('ds-confirma').value = '';
        }
    });
}
