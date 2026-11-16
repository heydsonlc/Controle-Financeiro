// FIN-CACHE-01 — versao por conteudo nos enderecos de JS e CSS do dist.
//
// Diagnostico (15/11/2026, producao): o HTML sai com "max-age=0, must-revalidate" (sempre revalidado), mas JS e CSS saem com
// "max-age=14400" (o "Browser Cache TTL" de 4 h da zona do dominio). Depois de uma publicacao, o navegador podia juntar o HTML
// novo com JS antigo ainda no cache: botoes novos sem acao ate o cache vencer (ou ate limpar os dados do site).
//
// Correcao, sem depender da configuracao da zona: cada referencia a um JS/CSS do proprio site recebe "?v=<hash do conteudo>"
// (no HTML: src/href; nos modulos: import estatico, export ... from, import() literal e new URL('...', import.meta.url)).
// Arquivo alterado = endereco novo, que o navegador ainda nao tem; arquivo igual = mesmo endereco, cache mantido.
// O hash de um modulo inclui o hash do que ele importa (a mudanca num modulo interno muda o endereco de quem o importa, ate o
// HTML). Ciclos de importacao recebem um hash comum. Todas as referencias a um arquivo usam o mesmo endereco: cada modulo
// continua sendo carregado uma unica vez (o estado compartilhado entre modulos nao se divide).
// Fora daqui: arquivos de vendor nao sao lidos por dentro (so recebem a versao); a pasta do OCR leva a versao no nome
// (vendor/tesseract-7.0.0/) e os caminhos internos do Tesseract ficam como estao.

import { createHash } from 'node:crypto';
import { readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const RECURSO = /\.(?:m?js|css)$/;
// Especificadores relativos (./ ou ../) terminados em .js/.mjs, sem consulta.
const IMPORTACOES = [
    /(\bfrom\s*|\bimport\s*)(['"])(\.{1,2}\/[^'"?#\s]+?\.m?js)\2/g,                      // import/export ... from '...'; import '...'
    /(\bimport\(\s*)(['"])(\.{1,2}\/[^'"?#\s]+?\.m?js)\2(?=\s*\))/g,                      // import('...')
    /(\bnew URL\(\s*)(['"])(\.{1,2}\/[^'"?#\s]+?\.m?js)\2(?=\s*,\s*import\.meta\.url\s*\))/g, // new URL('...', import.meta.url)
];
// src/href do HTML para JS/CSS do proprio site (relativo ou a partir da raiz), sem consulta.
const NO_HTML = /(\s(?:src|href)=)(["'])((?!https?:|\/\/|data:|blob:)[^"'?#\s]+?\.(?:m?js|css))\2/g;

const rel = (raiz, arquivo) => path.relative(raiz, arquivo).split(path.sep).join('/');

async function listar(dir) {
    const saida = [];
    for (const item of await readdir(dir, { withFileTypes: true })) {
        const caminho = path.join(dir, item.name);
        if (item.isDirectory()) saida.push(...await listar(caminho));
        else saida.push(caminho);
    }
    return saida;
}

function alvo(raiz, deOnde, especificador) {
    const base = especificador.startsWith('/') ? raiz : path.dirname(deOnde);
    return path.resolve(base, especificador.replace(/^\//, ''));
}

const hash = (...partes) => {
    const h = createHash('sha256');
    for (const p of partes) h.update(p).update('\0');
    return h.digest('hex').slice(0, 12);
};

// Componentes fortemente conexos (Tarjan, iterativo), em ordem de dependencia: um componente so aparece depois de todos os
// componentes de que ele depende.
function componentes(nos, arestas) {
    let indice = 0;
    const idx = new Map();
    const baixo = new Map();
    const pilha = [];
    const naPilha = new Set();
    const saida = [];
    for (const inicio of nos) {
        if (idx.has(inicio)) continue;
        const trabalho = [[inicio, 0]];
        idx.set(inicio, indice); baixo.set(inicio, indice); indice += 1;
        pilha.push(inicio); naPilha.add(inicio);
        while (trabalho.length) {
            const topo = trabalho[trabalho.length - 1];
            const [no, i] = topo;
            const vizinhos = [...(arestas.get(no) || [])];
            if (i < vizinhos.length) {
                topo[1] += 1;
                const w = vizinhos[i];
                if (!idx.has(w)) {
                    idx.set(w, indice); baixo.set(w, indice); indice += 1;
                    pilha.push(w); naPilha.add(w);
                    trabalho.push([w, 0]);
                } else if (naPilha.has(w)) {
                    baixo.set(no, Math.min(baixo.get(no), idx.get(w)));
                }
                continue;
            }
            trabalho.pop();
            if (trabalho.length) {
                const pai = trabalho[trabalho.length - 1][0];
                baixo.set(pai, Math.min(baixo.get(pai), baixo.get(no)));
            }
            if (baixo.get(no) === idx.get(no)) {
                const comp = [];
                let w;
                do { w = pilha.pop(); naPilha.delete(w); comp.push(w); } while (w !== no);
                saida.push(comp.sort());
            }
        }
    }
    return saida;
}

// Reescreve o dist no lugar. Devolve { versoes: Map(caminho relativo -> hash), html: [paginas reescritas] }.
export async function versionarRecursos(raiz) {
    const arquivos = await listar(raiz);
    const recursos = new Set(arquivos.filter((a) => RECURSO.test(a)));
    const ehVendor = (a) => rel(raiz, a).startsWith('vendor/');
    const conteudo = new Map();
    const arestas = new Map();
    for (const arquivo of recursos) {
        const texto = await readFile(arquivo, 'utf8');
        conteudo.set(arquivo, texto);
        const deps = new Set();
        if (/\.m?js$/.test(arquivo) && !ehVendor(arquivo)) {
            for (const padrao of IMPORTACOES) {
                for (const m of texto.matchAll(padrao)) {
                    const destino = alvo(raiz, arquivo, m[3]);
                    if (!recursos.has(destino)) throw new Error(`${rel(raiz, arquivo)}: importa ${m[3]}, que nao existe no dist`);
                    deps.add(destino);
                }
            }
        }
        arestas.set(arquivo, deps);
    }

    const versoes = new Map();
    const reescrever = (arquivo, texto) => {
        if (!/\.m?js$/.test(arquivo) || ehVendor(arquivo)) return texto;
        let saida = texto;
        for (const padrao of IMPORTACOES) {
            saida = saida.replace(padrao, (_t, antes, aspas, esp) => `${antes}${aspas}${esp}?v=${versoes.get(alvo(raiz, arquivo, esp))}${aspas}`);
        }
        return saida;
    };
    for (const comp of componentes([...recursos].sort(), arestas)) {
        const ciclo = comp.length > 1 || arestas.get(comp[0]).has(comp[0]);
        if (!ciclo) {
            const [arquivo] = comp;
            const novo = reescrever(arquivo, conteudo.get(arquivo));
            versoes.set(arquivo, hash(novo));
            conteudo.set(arquivo, novo);
            continue;
        }
        // Ciclo: hash comum, do conteudo original dos membros e das versoes do que esta fora do ciclo.
        const membros = new Set(comp);
        const externas = comp.flatMap((a) => [...arestas.get(a)].filter((d) => !membros.has(d)).map((d) => `${rel(raiz, d)}=${versoes.get(d)}`));
        const comum = hash(...comp.map((a) => `${rel(raiz, a)}\n${conteudo.get(a)}`), ...[...new Set(externas)].sort());
        for (const a of comp) versoes.set(a, comum);
        for (const a of comp) conteudo.set(a, reescrever(a, conteudo.get(a)));
    }
    for (const arquivo of recursos) {
        if (!/\.m?js$/.test(arquivo) || ehVendor(arquivo)) continue;
        await writeFile(arquivo, conteudo.get(arquivo));
    }

    const html = [];
    for (const pagina of arquivos.filter((a) => a.endsWith('.html'))) {
        const texto = await readFile(pagina, 'utf8');
        const novo = texto.replace(NO_HTML, (t, antes, aspas, esp) => {
            const destino = alvo(raiz, pagina, esp);
            if (!recursos.has(destino)) throw new Error(`${rel(raiz, pagina)}: referencia ${esp}, que nao existe no dist`);
            return `${antes}${aspas}${esp}?v=${versoes.get(destino)}${aspas}`;
        });
        if (novo !== texto) {
            await writeFile(pagina, novo);
            html.push(rel(raiz, pagina));
        }
    }
    return { versoes: new Map([...versoes].map(([a, v]) => [rel(raiz, a), v])), html };
}
