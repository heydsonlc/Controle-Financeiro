#!/usr/bin/env node
// CF-SUPABASE-REFACTOR-1 — build estatico para Cloudflare Pages.
//
// Monta web/dist a partir de web/src, reaproveita o tema do frontend atual
// (frontend/static/css) e gera config.js SOMENTE com valores publicos.
//
// Uso:
//   SUPABASE_URL=https://<ref>.supabase.co SUPABASE_PUBLISHABLE_KEY=sb_publishable_... node scripts/build.mjs
//   node scripts/build.mjs --local   (aceita http://127.0.0.1 — somente testes locais)
//
// Falha fechado se a chave parecer privilegiada, se o projeto for o da
// Calculadora Judicial ou se algo sensivel aparecer em dist/.

import { cp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const RAIZ = path.resolve(WEB, '..');

// Projeto Supabase da Calculadora Judicial / Portal Kortex: nunca compartilhar.
export const PROJETOS_PROIBIDOS = new Set(['dshqjhyymtpxpxuntzbz']);
// FIN-MIGRACAO-FIDELIDADE-FASE-1: CSS da moldura e das telas do Flask, sem alteracao.
const CSS_COMPARTILHADO = ['style.css', 'theme-light.css', 'layout.css', 'instituicoes.css', 'formas_pagamento.css',
    'configuracoes.css', 'ajuda.css', 'despesas.css', 'recorrencias.css'];
// JS do Flask reaproveitado: vai para js/original/ so com a conversao de adaptarParaCsp (o arquivo do Flask nao muda).
const JS_ORIGINAL = ['ajuda.js', 'utils.js', 'icons.js', 'instituicoes.js', 'formas_pagamento.js', 'despesas.js', 'recorrencias.js'];
// Imagens que os componentes do Flask (formas_pagamento.js, instituicoes.js) pedem em /static/...: so as que eles
// citam pelo nome (versionadas), nunca a pasta inteira (frontend/static/img tem arquivos pessoais fora do Git).
const IMAGENS_ORIGINAIS = {
    'static/img': ['logo_pix.png', 'icone_dinheiro.jpg', 'logo_bandeira_cartao_visa.png', 'icone_boleto.jpg', 'trasnferencia_icone.jpg'],
};
const ORIGEM_IMAGENS_INSTITUICOES = 'static/assets/instituicoes';
// Fontes da montagem: nao vao para o dist.
const SO_FONTE = ['moldura', 'paginas'];
const PADROES_PROIBIDOS = [
    /sb_secret_[A-Za-z0-9_-]+/,
    /service_role/i,
    /DATABASE_URL/,
    /postgres(ql)?:\/\//i,
    /SUPABASE_SERVICE/i,
];

export function validarUrl(url, { permitirLocal = false } = {}) {
    let alvo;
    try {
        alvo = new URL(url);
    } catch {
        throw new Error('SUPABASE_URL invalida.');
    }
    const local = alvo.protocol === 'http:' && alvo.hostname === '127.0.0.1';
    if (local) {
        if (!permitirLocal) throw new Error('SUPABASE_URL local so e aceita com --local.');
        return alvo.origin;
    }
    if (alvo.protocol !== 'https:') throw new Error('SUPABASE_URL deve usar https.');
    const ref = alvo.hostname.endsWith('.supabase.co') ? alvo.hostname.split('.')[0] : null;
    if (!ref) throw new Error('SUPABASE_URL deve ser https://<ref>.supabase.co.');
    if (PROJETOS_PROIBIDOS.has(ref)) {
        throw new Error('Projeto Supabase da Calculadora Judicial: proibido no Controle Financeiro.');
    }
    return alvo.origin;
}

function payloadJwt(chave) {
    const partes = chave.split('.');
    if (partes.length !== 3) return null;
    try {
        return JSON.parse(Buffer.from(partes[1], 'base64url').toString('utf8'));
    } catch {
        return null;
    }
}

export function validarChavePublica(chave) {
    const valor = String(chave || '').trim();
    if (!valor) throw new Error('SUPABASE_PUBLISHABLE_KEY ausente.');
    if (valor.startsWith('sb_secret_')) throw new Error('Chave secreta (sb_secret_) nunca vai para o navegador.');
    if (valor.startsWith('sb_publishable_')) return valor;
    const payload = payloadJwt(valor);
    if (payload && payload.role === 'anon') return valor;
    if (payload) throw new Error(`Chave JWT com role "${payload.role}": apenas "anon" e permitida.`);
    throw new Error('Formato de chave nao reconhecido: use a chave publicavel (sb_publishable_...).');
}

export function cabecalhosSeguranca(origemSupabase) {
    const csp = [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        `connect-src 'self' ${origemSupabase}`,
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "object-src 'none'",
    ].join('; ');
    return [
        '/*',
        `  Content-Security-Policy: ${csp}`,
        '  X-Content-Type-Options: nosniff',
        '  X-Frame-Options: DENY',
        '  Referrer-Policy: same-origin',
        '  Permissions-Policy: camera=(), microphone=(), geolocation=()',
        '',
    ].join('\n');
}

async function listarArquivos(dir) {
    const saida = [];
    for (const item of await readdir(dir, { withFileTypes: true })) {
        const caminho = path.join(dir, item.name);
        if (item.isDirectory()) saida.push(...await listarArquivos(caminho));
        else saida.push(caminho);
    }
    return saida;
}

export async function verificarDist(destino) {
    const problemas = [];
    for (const arquivo of await listarArquivos(destino)) {
        const relativo = path.relative(destino, arquivo).split(path.sep).join('/');
        const conteudo = await readFile(arquivo, 'utf8');
        // A biblioteca de terceiros e verificada so contra chaves reais embutidas.
        const padroes = relativo.startsWith('vendor/') ? PADROES_PROIBIDOS.slice(0, 1) : PADROES_PROIBIDOS;
        for (const padrao of padroes) {
            if (padrao.test(conteudo)) problemas.push(`${relativo}: ${padrao}`);
        }
    }
    if (problemas.length) throw new Error(`Conteudo sensivel em dist/: ${problemas.join(', ')}`);
}

// FIN-FIDELIDADE-DESPESAS-1: as telas do Flask usam onclick="f(...)" e style="..." no HTML e no JS. A CSP do novo
// aplicativo (script-src e style-src 'self') bloqueia os dois. Sem afrouxar a CSP, o build troca os atributos por
// data-on-<evento> e data-estilo, que js/ponte-csp.js aplica (chamada so de funcoes da lista gerada aqui, sem eval;
// estilo por CSSOM). E a unica mudanca nas copias do HTML e do JS originais.
const ATRIBUTO_EVENTO = /(\s)on(click|change|input|keyup|submit|error|load)=/g;
const ATRIBUTO_ESTILO = /(\s)style=/g;
export function adaptarParaCsp(texto) {
    return texto.replace(ATRIBUTO_EVENTO, '$1data-on-$2=').replace(ATRIBUTO_ESTILO, '$1data-estilo=');
}

// Funcoes chamadas pelos data-on-* (as unicas que a ponte executa).
export function funcoesDosEventos(texto) {
    const nomes = new Set();
    for (const [, duplas, simples] of texto.matchAll(/data-on-[a-z]+=(?:"([^"]*)"|'([^']*)')/g)) {
        for (const [, nome] of String(duplas ?? simples).matchAll(/(?:^|;)\s*([A-Za-z_$][\w$]*)\s*\(/g)) nomes.add(nome);
    }
    return nomes;
}

const escapar = (texto) => String(texto).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// Pagina de src/paginas: comentario inicial com os metadados em JSON, depois "<!-- acao -->" (opcional,
// barra de acoes do Flask) e "<!-- conteudo -->".
export function lerPagina(nome, fonte) {
    const meta = /^<!-- moldura (\{[\s\S]*?\}) -->\s*/.exec(fonte);
    if (!meta) throw new Error(`${nome}: metadados da moldura ausentes.`);
    const dados = JSON.parse(meta[1]);
    const resto = fonte.slice(meta[0].length);
    const corte = resto.indexOf('<!-- conteudo -->');
    if (corte < 0) throw new Error(`${nome}: marcador <!-- conteudo --> ausente.`);
    const antes = resto.slice(0, corte);
    const marcaAcao = antes.indexOf('<!-- acao -->');
    const acao = marcaAcao < 0 ? '' : antes.slice(marcaAcao + '<!-- acao -->'.length).trim();
    return { ...dados, arquivo: nome, acao, conteudo: resto.slice(corte + '<!-- conteudo -->'.length).trim() };
}

export function paginaEmMigracao(modulo) {
    return {
        ...modulo,
        css: [],
        scripts: ['js/pagina.js'],
        acao: '',
        conteudo: `<section class="modulo-em-migracao" aria-labelledby="modulo-titulo">
                        <span class="modulo-em-migracao-selo">Em migração</span>
                        <h1 class="modulo-em-migracao-titulo" id="modulo-titulo">${escapar(modulo.titulo)}</h1>
                        <p>${escapar(modulo.descricao)}</p>
                        <p>Este módulo faz parte do plano de substituição e ainda está sendo migrado para o novo aplicativo. Nada foi removido: até a migração, ele continua no sistema atual.</p>
                        <p class="modulo-em-migracao-disponiveis">Já disponíveis aqui: <a href="contas.html">Despesas</a>, <a href="receitas.html">Receitas</a>, <a href="cartoes.html">Cartões</a>, <a href="categorias.html">Categorias</a> e <a href="configuracoes.html">Configurações</a> (perfis financeiros).</p>
                    </section>`,
    };
}

// Moldura do Flask + pagina. Item ativo e itens "Em migracao" marcados aqui, como o active_page do Jinja.
export function montarPagina(base, pagina, emMigracao) {
    let html = base.replace(/<a href="([^"]+)" class="app-nav-link" data-pagina="(\w+)">([\s\S]*?)<\/a>/g,
        (_todo, href, chave, miolo) => {
            const ativo = chave === pagina.ativo;
            const selo = emMigracao.has(chave)
                ? '\n                        <span class="app-nav-status">Em migração</span>\n                    ' : '';
            return `<a href="${href}" class="app-nav-link${ativo ? ' active' : ''}" data-pagina="${chave}"`
                + `${emMigracao.has(chave) ? ' data-em-migracao' : ''}${ativo ? ' aria-current="page"' : ''}>`
                + `${miolo.replace(/\s*$/, '')}${selo || '\n                    '}</a>`;
        });
    const trocas = {
        documento: escapar(pagina.documento || `${pagina.titulo} - Controle Financeiro`),
        titulo: escapar(pagina.titulo),
        css: (pagina.css || []).map((c) => `    <link rel="stylesheet" href="${c}">`).join('\n'),
        acao: adaptarParaCsp(pagina.acao || ''),
        conteudo: adaptarParaCsp(pagina.conteudo || ''),
        // Classicos (na ordem do template do Flask) antes dos modulos do novo aplicativo.
        scripts: [
            ...(pagina.classicos || []).map((s) => `    <script src="${s}"></script>`),
            ...(pagina.scripts || []).map((s) => (s.startsWith('js/original/')
                ? `    <script src="${s}"></script>` : `    <script type="module" src="${s}"></script>`)),
        ].join('\n'),
    };
    html = html.replace(/\{\{(documento|titulo|css|acao|conteudo|scripts)\}\}/g, (_t, chave) => trocas[chave]);
    if (/\{\{|\{%/.test(html)) throw new Error(`${pagina.arquivo}: marcador da moldura nao resolvido.`);
    return html;
}

async function montarPaginas(destino) {
    const fonte = path.join(WEB, 'src');
    const base = await readFile(path.join(fonte, 'moldura', 'base.html'), 'utf8');
    const modulos = JSON.parse(await readFile(path.join(fonte, 'moldura', 'em-migracao.json'), 'utf8'));
    const paginas = [];
    for (const nome of (await readdir(path.join(fonte, 'paginas'))).filter((n) => n.endsWith('.html'))) {
        paginas.push(lerPagina(nome, await readFile(path.join(fonte, 'paginas', nome), 'utf8')));
    }
    paginas.push(...modulos.map(paginaEmMigracao));
    // Todo item do menu leva a uma pagina que existe (nunca a uma pagina quebrada).
    const doMenu = [...base.matchAll(/href="([^"#]+)(?:#[^"]*)?" class="app-nav-link" data-pagina="(\w+)"/g)];
    for (const [, href, chave] of doMenu) {
        if (!paginas.some((p) => p.arquivo === href && p.ativo === chave)) {
            throw new Error(`Item do menu sem pagina: ${chave} -> ${href}`);
        }
    }
    const emMigracao = new Set(modulos.map((m) => m.ativo));
    const montadas = [];
    for (const pagina of paginas) {
        const html = montarPagina(base, pagina, emMigracao);
        montadas.push(html);
        await writeFile(path.join(destino, pagina.arquivo), html);
    }
    return montadas;
}

export async function construir({ url, chave, destino = path.join(WEB, 'dist'), permitirLocal = false }) {
    const origem = validarUrl(url, { permitirLocal });
    const chavePublica = validarChavePublica(chave);

    await rm(destino, { recursive: true, force: true });
    await cp(path.join(WEB, 'src'), destino, { recursive: true });
    for (const pasta of SO_FONTE) await rm(path.join(destino, pasta), { recursive: true, force: true });
    const montadas = await montarPaginas(destino);

    await mkdir(path.join(destino, 'css', 'shared'), { recursive: true });
    for (const nome of CSS_COMPARTILHADO) {
        await cp(path.join(RAIZ, 'frontend', 'static', 'css', nome), path.join(destino, 'css', 'shared', nome));
    }
    await mkdir(path.join(destino, 'js', 'original'), { recursive: true });
    const permitidas = new Set();
    for (const html of montadas) for (const nome of funcoesDosEventos(html)) permitidas.add(nome);
    for (const nome of JS_ORIGINAL) {
        const adaptado = adaptarParaCsp(await readFile(path.join(RAIZ, 'frontend', 'static', 'js', nome), 'utf8'));
        for (const funcao of funcoesDosEventos(adaptado)) permitidas.add(funcao);
        await writeFile(path.join(destino, 'js', 'original', nome), adaptado);
    }
    const imagens = { ...IMAGENS_ORIGINAIS };
    const instituicoes = await readFile(path.join(RAIZ, 'frontend', 'static', 'js', 'instituicoes.js'), 'utf8');
    imagens[ORIGEM_IMAGENS_INSTITUICOES] = [...new Set([...instituicoes.matchAll(/'([\w-]+\.(?:png|svg))'/g)].map((m) => m[1]))];
    for (const [pasta, nomes] of Object.entries(imagens)) {
        await mkdir(path.join(destino, ...pasta.split('/')), { recursive: true });
        for (const nome of nomes) {
            const origem = path.join(RAIZ, 'frontend', ...pasta.split('/'), nome);
            await cp(origem, path.join(destino, ...pasta.split('/'), nome)).catch(() => {});  // logo ausente: o componente usa o padrao
        }
    }
    await writeFile(path.join(destino, 'js', 'original', 'ponte-permitidas.js'),
        '// Gerado por scripts/build.mjs: funcoes que os atributos data-on-* das telas originais podem chamar.\n'
        + `window.CF_PONTE_PERMITIDAS = Object.freeze(${JSON.stringify([...permitidas].sort())});\n`);

    await mkdir(path.join(destino, 'vendor'), { recursive: true });
    await cp(
        path.join(WEB, 'node_modules', '@supabase', 'supabase-js', 'dist', 'umd', 'supabase.js'),
        path.join(destino, 'vendor', 'supabase.js'),
    );

    const config = { supabaseUrl: origem, supabasePublishableKey: chavePublica };
    await writeFile(
        path.join(destino, 'config.js'),
        `// Gerado por scripts/build.mjs. Somente valores publicos.\nwindow.CF_CONFIG = Object.freeze(${JSON.stringify(config)});\n`,
    );
    await writeFile(path.join(destino, '_headers'), cabecalhosSeguranca(origem));

    await verificarDist(destino);
    return { destino, origem };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    try {
        const resultado = await construir({
            url: process.env.SUPABASE_URL,
            chave: process.env.SUPABASE_PUBLISHABLE_KEY,
            permitirLocal: process.argv.includes('--local'),
        });
        console.log(`BUILD_OK ${path.relative(RAIZ, resultado.destino)} -> ${resultado.origem}`);
    } catch (falha) {
        console.error(`BUILD_FALHOU: ${falha.message}`);
        process.exit(1);
    }
}
