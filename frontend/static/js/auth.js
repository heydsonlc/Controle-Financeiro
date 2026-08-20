/**
 * SEG-1: sessão de autenticação global.
 * - Redireciona para /login quando uma chamada a /api/* retorna 401
 *   (sessão expirada/ausente), sem quebrar chamadas que já tratam 401 sozinhas.
 * - Liga o botão de logout do topbar (POST /logout).
 */
(function () {
    const originalFetch = window.fetch.bind(window);

    window.fetch = function (input, init) {
        return originalFetch(input, init).then((response) => {
            const url = typeof input === 'string' ? input : (input && input.url) || '';
            if (response.status === 401 && url.includes('/api/')) {
                window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
            }
            return response;
        });
    };

    document.addEventListener('DOMContentLoaded', () => {
        const botaoLogout = document.getElementById('app-logout-button');
        if (!botaoLogout) return;

        botaoLogout.addEventListener('click', () => {
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/logout';
            document.body.appendChild(form);
            form.submit();
        });
    });
})();
