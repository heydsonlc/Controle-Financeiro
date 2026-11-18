// FIN-MULTIUSUARIO-ACESSO-01 — pedido de recuperacao de senha.
//
// O link e enviado pelo Supabase Auth e leva a definir-senha.html. A resposta e SEMPRE a mesma, exista ou nao conta com o
// e-mail informado: a tela nao revela quem tem conta. O limite de pedidos e o do Supabase Auth.

import { supabase } from './cliente.js';

const $ = (id) => document.getElementById(id);
const RESPOSTA = 'Se houver uma conta com este e-mail, enviaremos um link para definir uma nova senha. Confira também a caixa de spam.';

$('rs-form').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    $('rs-erro').hidden = true;
    const email = $('rs-email').value.trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
        $('rs-erro').textContent = 'Informe um e-mail válido.';
        $('rs-erro').hidden = false;
        return;
    }
    $('rs-enviar').disabled = true;
    try {
        await supabase.auth.resetPasswordForEmail(email, { redirectTo: new URL('definir-senha.html', window.location.href).href });
    } catch (_falha) {
        // mesma resposta: nem a falha diz se a conta existe
    }
    $('rs-form').hidden = true;
    $('rs-aviso').textContent = RESPOSTA;
    $('rs-aviso').hidden = false;
});
