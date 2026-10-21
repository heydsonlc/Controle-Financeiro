// Testes do build: o navegador so pode receber valores publicos do projeto certo.
import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { construir, validarChavePublica, validarUrl, verificarDist } from '../../scripts/build.mjs';

const URL_OK = 'https://abcdefghijklmnopqrst.supabase.co';
const jwt = (payload) => [
    Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url'),
    Buffer.from(JSON.stringify(payload)).toString('base64url'),
    'assinatura',
].join('.');

test('aceita a chave publicavel e a chave anon legada', () => {
    assert.equal(validarChavePublica('sb_publishable_abc123'), 'sb_publishable_abc123');
    assert.ok(validarChavePublica(jwt({ role: 'anon' })));
});

test('recusa chave secreta e JWT privilegiado', () => {
    assert.throws(() => validarChavePublica('sb_secret_abc123'), /secreta/);
    assert.throws(() => validarChavePublica(jwt({ role: 'service_role' })), /apenas "anon"/);
    assert.throws(() => validarChavePublica(jwt({ role: 'authenticated' })), /apenas "anon"/);
    assert.throws(() => validarChavePublica(''), /ausente/);
    assert.throws(() => validarChavePublica('qualquer-coisa'), /nao reconhecido/);
});

test('recusa o projeto Supabase da Calculadora Judicial', () => {
    assert.throws(() => validarUrl('https://dshqjhyymtpxpxuntzbz.supabase.co'), /Calculadora Judicial/);
});

test('exige https em supabase.co; local so com --local', () => {
    assert.equal(validarUrl(URL_OK), URL_OK);
    assert.throws(() => validarUrl('http://abcdefghijklmnopqrst.supabase.co'), /https/);
    assert.throws(() => validarUrl('https://exemplo.com'), /supabase\.co/);
    assert.throws(() => validarUrl('http://127.0.0.1:54321'), /--local/);
    assert.equal(validarUrl('http://127.0.0.1:54321', { permitirLocal: true }), 'http://127.0.0.1:54321');
});

test('dist gerado contem so valores publicos e CSP restrita', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-build-'));
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const config = await readFile(path.join(destino, 'config.js'), 'utf8');
        assert.match(config, /"supabaseUrl":"https:\/\/abcdefghijklmnopqrst\.supabase\.co"/);
        assert.match(config, /"supabasePublishableKey":"sb_publishable_abc123"/);
        assert.doesNotMatch(config, /secret|service|password|senha/i);

        const headers = await readFile(path.join(destino, '_headers'), 'utf8');
        assert.match(headers, /script-src 'self';/);
        assert.match(headers, new RegExp(`connect-src 'self' ${URL_OK.replace(/\./g, '\\.')}`));
        assert.match(headers, /frame-ancestors 'none'/);

        const arquivos = await readdir(destino, { recursive: true });
        assert.ok(arquivos.some((a) => a.replaceAll('\\', '/') === 'css/shared/theme-light.css'), 'tema reaproveitado');
        assert.ok(arquivos.some((a) => a.replaceAll('\\', '/') === 'vendor/supabase.js'));
        assert.ok(!arquivos.some((a) => /\.env|\.py$|\.sql$/.test(a)), 'nada de backend no dist');
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

test('verificacao de dist detecta segredo injetado', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-scan-'));
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        await writeFile(path.join(destino, 'js', 'vazamento.js'), 'const k = "sb_secret_vazada123";');
        await assert.rejects(verificarDist(destino), /sb_secret_/);
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

const RPCS_DE_LEITURA = new Set(['meus_perfis', 'contas_bancarias_do_perfil', 'contas_do_mes',
    'lancamentos_da_fatura', 'mes_pode_estar_incompleto', 'previa_geracao', 'categorias_de_despesa',
    'despesa_para_edicao']);
// Escrita so por RPC transacional autorizada no banco, revisada uma a uma, e so na tela que a usa.
const RPCS_DE_ESCRITA = new Map([
    ['gerar_mes', 'contas.js'],
    // FIN-DESPESAS-1
    ['criar_despesa', 'despesas.js'],
    ['editar_despesa', 'despesas.js'],
    ['excluir_despesa', 'despesas.js'],
    ['editar_recorrencia', 'despesas.js'],
    ['inativar_recorrencia', 'despesas.js'],
]);

test('codigo-fonte do frontend nao escreve em tabelas nem usa innerHTML', async () => {
    const dir = new URL('../../src/js/', import.meta.url);
    for (const nome of await readdir(dir)) {
        // Comentarios fora: o que importa e o codigo executado.
        const fonte = (await readFile(new URL(nome, dir), 'utf8'))
            .replace(/\/\*[\s\S]*?\*\//g, '')
            .replace(/^\s*\/\/.*$/gm, '')
            .replace(/\s\/\/.*$/gm, '');
        assert.doesNotMatch(fonte, /\.(insert|update|upsert|delete)\s*\(/, `${nome} faz escrita direta`);
        // So RPCs liberadas (PERFIS-1); escrita exige revisao explicita (FIN-RECORRENCIA-1: gerar_mes).
        for (const [, funcao] of fonte.matchAll(/\.rpc\s*\(\s*['"`]([^'"`]+)['"`]/g)) {
            assert.ok(RPCS_DE_LEITURA.has(funcao) || RPCS_DE_ESCRITA.get(funcao) === nome,
                `${nome} chama RPC nao liberada: ${funcao}`);
        }
        assert.doesNotMatch(fonte.replace(/\.rpc\s*\(\s*['"`][^'"`]+['"`]/g, ''), /\.rpc\s*\(/, `${nome} chama RPC com nome dinamico`);
        assert.doesNotMatch(fonte, /innerHTML|outerHTML|insertAdjacentHTML|document\.write/, `${nome} injeta HTML`);
    }
});
