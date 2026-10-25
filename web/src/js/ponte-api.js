// FIN-FIDELIDADE-DESPESAS-1 — as telas originais chamam fetch('/api/...') do Flask. Aqui essas chamadas (so as do
// proprio site com caminho /api/) sao entregues ao adaptador da tela (modulo que usa as funcoes do Supabase) e
// respondidas no formato do Flask. Nada vai ao Flask: nao existe servidor /api/ no novo aplicativo.
// Fila unica e em ordem: a resposta de uma chamada mais antiga nunca chega depois da de uma mais nova (a tela original
// usa a ultima listagem que recebe). As chamadas feitas antes de o adaptador ficar pronto esperam por ele.
(function () {
    'use strict';

    const fetchOriginal = window.fetch.bind(window);
    let registrar;
    const adaptadorPronto = new Promise((resolver) => { registrar = resolver; });
    let fila = Promise.resolve();

    window.CF_REGISTRAR_ADAPTADOR = (adaptador) => registrar(adaptador);

    function resposta(status, corpo) {
        return new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } });
    }

    window.fetch = function (entrada, opcoes) {
        const endereco = new URL(typeof entrada === 'string' ? entrada : entrada.url, window.location.href);
        if (endereco.origin !== window.location.origin || !endereco.pathname.startsWith('/api/')) {
            return fetchOriginal(entrada, opcoes);
        }
        const metodo = String((opcoes && opcoes.method) || 'GET').toUpperCase();
        let corpo = null;
        if (opcoes && typeof opcoes.body === 'string' && opcoes.body) {
            try { corpo = JSON.parse(opcoes.body); } catch (_erro) { corpo = null; }
        }
        const tarefa = fila.then(async () => {
            const adaptador = await adaptadorPronto;
            try {
                const r = await adaptador({ metodo, caminho: endereco.pathname, parametros: endereco.searchParams, corpo });
                return resposta(r.status || 200, r.corpo);
            } catch (erro) {
                console.error('Adaptador:', metodo, endereco.pathname, erro);
                return resposta(500, { success: false, error: 'Não foi possível concluir a operação. Nada foi gravado.' });
            }
        });
        fila = tarefa.catch(() => {});
        return tarefa;
    };
}());
