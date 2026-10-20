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
const CSS_COMPARTILHADO = ['style.css', 'theme-light.css'];
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

export async function construir({ url, chave, destino = path.join(WEB, 'dist'), permitirLocal = false }) {
    const origem = validarUrl(url, { permitirLocal });
    const chavePublica = validarChavePublica(chave);

    await rm(destino, { recursive: true, force: true });
    await cp(path.join(WEB, 'src'), destino, { recursive: true });

    await mkdir(path.join(destino, 'css', 'shared'), { recursive: true });
    for (const nome of CSS_COMPARTILHADO) {
        await cp(path.join(RAIZ, 'frontend', 'static', 'css', nome), path.join(destino, 'css', 'shared', nome));
    }

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
