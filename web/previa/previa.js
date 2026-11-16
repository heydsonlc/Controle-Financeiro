// FIN-MVP-MOB-08 — pagina de pre-visualizacao (so ambiente local). Mesma pagina em varios tamanhos, lado a lado.
// Os quadros sao da mesma origem: a sessao (localStorage) vale para todos; cada quadro tem a sua largura, entao o
// destino do login e o layout respondem como num aparelho daquele tamanho. Preferencias so no navegador.
(function () {
    'use strict';

    const APARELHOS = [
        { id: 'p320', nome: 'Celular pequeno', w: 320, h: 568 },
        { id: 'p360', nome: 'Android', w: 360, h: 740 },
        { id: 'p375', nome: 'iPhone SE', w: 375, h: 667 },
        { id: 'p390', nome: 'iPhone 14', w: 390, h: 844 },
        { id: 'p412', nome: 'Pixel', w: 412, h: 915 },
        { id: 'p430', nome: 'iPhone Pro Max', w: 430, h: 932 },
        { id: 't820', nome: 'Tablet', w: 820, h: 1180 },
        { id: 'd1366', nome: 'Desktop', w: 1366, h: 900, desktop: true },
    ];
    const PADRAO = ['p360', 'p390', 'p430', 'd1366'];
    const CHAVE = 'cf-previa-mobile';
    const $ = (id) => document.getElementById(id);

    function ler() {
        try { return JSON.parse(localStorage.getItem(CHAVE)) || {}; } catch (_e) { return {}; }
    }
    function gravar(estado) {
        try { localStorage.setItem(CHAVE, JSON.stringify(estado)); } catch (_e) { /* sem preferencias */ }
    }

    // index.html = pagina inicial de cada aparelho: celular -> inicio.html, tablet e desktop -> contas.html (como no login)
    const estado = { rota: 'index.html', zoom: '0.75', aparelhos: PADRAO, ...ler() };

    function rotaSegura(texto) {
        const rota = String(texto || '').trim().replace(/^\/+/, '');
        // FIN-MVP-CADASTRO-UNIFICADO-01: aceita tambem as paginas de demonstracao desta pasta (__previa__/cadastro.html?cenario=1).
        return /^(__previa__\/)?[\w.-]+\.html(\?[\w=&%.-]*)?$/.test(rota) ? rota : 'index.html';
    }

    function montarOpcoes() {
        const caixa = $('pv-opcoes');
        for (const ap of APARELHOS) {
            const rotulo = document.createElement('label');
            const marca = document.createElement('input');
            marca.type = 'checkbox';
            marca.value = ap.id;
            marca.checked = estado.aparelhos.includes(ap.id);
            marca.addEventListener('change', () => {
                estado.aparelhos = [...caixa.querySelectorAll('input:checked')].map((m) => m.value);
                gravar(estado);
                montarQuadros();
            });
            rotulo.append(marca, ` ${ap.nome} ${ap.w}×${ap.h}`);
            caixa.append(rotulo);
        }
    }

    function montarQuadros() {
        const area = $('pv-quadros');
        area.replaceChildren();
        const zoom = Number(estado.zoom) || 0.75;
        for (const ap of APARELHOS.filter((a) => estado.aparelhos.includes(a.id))) {
            const escala = ap.desktop ? zoom * 0.55 : (ap.w > 700 ? zoom * 0.6 : zoom);
            const quadro = document.createElement('div');
            quadro.className = 'pv-quadro';
            const nome = document.createElement('div');
            nome.className = 'pv-quadro-nome';
            const medida = document.createElement('span');
            medida.textContent = ` ${ap.w}×${ap.h} · ${Math.round(escala * 100)}%`;
            nome.append(ap.nome, medida);
            const moldura = document.createElement('div');
            moldura.className = `pv-moldura${ap.desktop ? ' pv-desktop' : ''}`;
            moldura.style.width = `${Math.round(ap.w * escala)}px`;
            moldura.style.height = `${Math.round(ap.h * escala)}px`;
            const iframe = document.createElement('iframe');
            iframe.title = `${ap.nome} ${ap.w}×${ap.h}`;
            iframe.style.width = `${ap.w}px`;
            iframe.style.height = `${ap.h}px`;
            iframe.style.transform = `scale(${escala})`;
            iframe.src = `/${estado.rota}`;
            moldura.append(iframe);
            quadro.append(nome, moldura);
            area.append(quadro);
        }
    }

    function recarregar() {
        for (const iframe of document.querySelectorAll('.pv-quadros iframe')) {
            try { iframe.contentWindow.location.reload(); } catch (_e) { iframe.src = iframe.src; }
        }
    }

    async function reconstruir() {
        const botao = $('pv-reconstruir');
        botao.disabled = true;
        $('pv-status').textContent = 'Recompilando…';
        try {
            const r = await fetch('/__previa__/reconstruir', { method: 'POST' });
            const corpo = await r.json();
            $('pv-status').textContent = corpo.ok ? `Recompilado às ${new Date().toLocaleTimeString('pt-BR')}` : `Falhou: ${corpo.erro}`;
            if (corpo.ok) recarregar();
        } catch (falha) {
            $('pv-status').textContent = `Falhou: ${falha.message}`;
        } finally {
            botao.disabled = false;
        }
    }

    $('pv-rota').value = estado.rota;
    $('pv-zoom').value = estado.zoom;
    $('pv-rota').addEventListener('change', () => {
        estado.rota = rotaSegura($('pv-rota').value);
        $('pv-rota').value = estado.rota;
        gravar(estado);
        montarQuadros();
    });
    $('pv-zoom').addEventListener('change', () => { estado.zoom = $('pv-zoom').value; gravar(estado); montarQuadros(); });
    $('pv-recarregar').addEventListener('click', recarregar);
    $('pv-reconstruir').addEventListener('click', reconstruir);
    montarOpcoes();
    montarQuadros();
}());
