// FIN-FIDELIDADE-DESPESAS-1 — ponte entre as telas originais do Flask e a CSP do novo aplicativo.
//
// O build troca onclick="f(...)" por data-on-click e style="..." por data-estilo (scripts/build.mjs, adaptarParaCsp).
// Aqui:
// - eventos: delegacao no documento; cada data-on-<evento> e lido como chamadas simples "f(arg, ...); g()" com
//   argumentos literais (numero, texto entre aspas, this, this.value, event). Sem eval: so funcoes globais da lista
//   gerada no build (window.CF_PONTE_PERMITIDAS) sao chamadas, com this = elemento, como no atributo original;
// - estilos: data-estilo vira estilo pelo CSSOM (el.style.cssText), permitido pela CSP, inclusive no HTML que as telas
//   inserem depois (MutationObserver).
// Script classico (sem modulo): roda antes dos scripts originais, como o Flask carregava os seus.
(function () {
    'use strict';

    const permitidas = new Set(window.CF_PONTE_PERMITIDAS || []);
    const BORBULHAM = ['click', 'change', 'input', 'keyup', 'submit'];
    const NAO_BORBULHAM = ['error', 'load'];

    // Separa por um caractere fora de aspas.
    function separar(texto, separador) {
        const partes = [];
        let atual = '';
        let aspas = null;
        for (const c of texto) {
            if (aspas) {
                if (c === aspas) aspas = null;
                atual += c;
            } else if (c === '"' || c === "'") {
                aspas = c;
                atual += c;
            } else if (c === separador) {
                partes.push(atual);
                atual = '';
            } else {
                atual += c;
            }
        }
        partes.push(atual);
        return partes.map((p) => p.trim()).filter((p) => p !== '');
    }

    function argumento(texto, elemento, evento) {
        if (texto === 'this') return elemento;
        if (texto === 'this.value') return elemento.value;
        if (texto === 'event') return evento;
        if (/^-?\d+(\.\d+)?$/.test(texto)) return Number(texto);
        if (/^'[^']*'$/.test(texto) || /^"[^"]*"$/.test(texto)) return texto.slice(1, -1);
        if (texto === 'true' || texto === 'false') return texto === 'true';
        if (texto === 'null' || texto === 'undefined') return null;
        throw new Error(`argumento nao suportado: ${texto}`);
    }

    function executar(expressao, elemento, evento) {
        for (const chamada of separar(expressao, ';')) {
            const partes = /^([A-Za-z_$][\w$]*)\s*\(([\s\S]*)\)$/.exec(chamada);
            const funcao = partes && window[partes[1]];
            if (!partes || !permitidas.has(partes[1]) || typeof funcao !== 'function') {
                console.warn('Ponte CSP: chamada recusada:', chamada);
                continue;
            }
            try {
                const args = separar(partes[2], ',').map((a) => argumento(a, elemento, evento));
                funcao.apply(elemento, args);
            } catch (erro) {
                console.error('Ponte CSP:', chamada, erro);
            }
        }
    }

    function despachar(evento) {
        const atributo = `data-on-${evento.type}`;
        let elemento = evento.target instanceof Element ? evento.target : evento.target?.parentElement;
        while (elemento) {
            if (elemento.hasAttribute(atributo)) {
                executar(elemento.getAttribute(atributo), elemento, evento);
                if (evento.cancelBubble || !evento.bubbles) break;
            }
            if (!evento.bubbles) break;
            elemento = elemento.parentElement;
        }
    }

    for (const tipo of BORBULHAM) document.addEventListener(tipo, despachar);
    for (const tipo of NAO_BORBULHAM) document.addEventListener(tipo, despachar, true);

    function aplicarEstilo(elemento) {
        const estilo = elemento.getAttribute('data-estilo');
        if (estilo === null) return;
        elemento.style.cssText = estilo;
        elemento.removeAttribute('data-estilo');
    }

    function varrer(no) {
        if (no.nodeType !== 1) return;
        aplicarEstilo(no);
        for (const elemento of no.querySelectorAll('[data-estilo]')) aplicarEstilo(elemento);
    }

    new MutationObserver((mudancas) => {
        for (const mudanca of mudancas) {
            if (mudanca.type === 'attributes') aplicarEstilo(mudanca.target);
            else for (const no of mudanca.addedNodes) varrer(no);
        }
    }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-estilo'] });
    varrer(document.documentElement);
}());
