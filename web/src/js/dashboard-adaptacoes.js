// FIN-FIDELIDADE-CONSOLIDACAO-1 — unica adaptacao de apresentacao do Dashboard original: js/original/dashboard.js monta
// as "acoes rapidas" com rotas do Flask (/despesas, /lancamentos...), que aqui nao existem. Depois de cada montagem, os
// enderecos passam a apontar para as paginas deste aplicativo (o JS do Flask nao e alterado).
(function () {
    // Despesas previstas e veiculos ficam na Mobilidade (ainda em migracao: a pagina informa).
    const PAGINAS = { '/despesas': 'contas.html', '/importar-cartao': 'importar-cartao.html', '/lancamentos': 'lancamentos.html',
        '/recorrencias': 'recorrencias.html', '/veiculos': 'mobilidade.html', '/cartoes': 'cartoes.html', '/categorias': 'categorias.html' };

    function ajustar(raiz) {
        raiz.querySelectorAll('a[href^="/"]').forEach((link) => {
            const pagina = PAGINAS[link.getAttribute('href')];
            if (pagina) link.setAttribute('href', pagina);
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        const container = document.getElementById('acoes-rapidas');
        if (!container) return;
        ajustar(container);
        new MutationObserver(() => ajustar(container)).observe(container, { childList: true, subtree: true });
    });
}());
