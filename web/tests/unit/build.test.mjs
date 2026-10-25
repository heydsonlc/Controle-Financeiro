// Testes do build: o navegador so pode receber valores publicos do projeto certo.
import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { construir, montarPagina, validarChavePublica, validarUrl, verificarDist } from '../../scripts/build.mjs';

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
    'despesa_para_edicao', 'receitas_do_mes', 'fontes_de_receita', 'receita_para_edicao', 'pode_gerir_perfil',
    'cartoes_do_perfil', 'faturas_do_mes', 'compras_da_fatura', 'compra_para_edicao', 'previa_compra',
    'recorrencias_rejeitadas',
    'sugerir_competencia',  // FIN-CARTOES-FECHAMENTO-1 (so leitura)
    'dados_pagamento_fatura',  // FIN-CARTOES-PAGAMENTO-1 (so leitura)
    'dados_pagamento_despesa', 'dados_recebimento_receita', 'movimentos_do_mes',  // FIN-MOVIMENTACOES-1 (so leitura)
    'perfis_para_configuracao']);  // FIN-MIGRACAO-FIDELIDADE-FASE-1 (so leitura)
// Escrita so por RPC transacional autorizada no banco, revisada uma a uma, e so na tela que a usa.
const RPCS_DE_ESCRITA = new Map([
    ['gerar_mes', 'despesas-recorrencias.js'],  // FIN-FIDELIDADE-DESPESAS-1: extraido de contas.js
    // FIN-DESPESAS-1
    // FIN-FIDELIDADE-DESPESAS-1: a tela original de Despesas chama pelo adaptador (despesas-adaptador.js)
    ['criar_despesa', 'despesas-adaptador.js'],
    ['editar_despesa', 'despesas-adaptador.js'],
    ['excluir_despesa', 'despesas-adaptador.js'],
    ['inativar_recorrencia', 'despesas-adaptador.js'],
    // FIN-RECEITAS-1 (so previsoes; nenhum recebimento)
    ['criar_receita', 'receitas.js'],
    ['editar_receita', 'receitas.js'],
    ['excluir_receita', 'receitas.js'],
    ['editar_fonte_receita', 'receitas.js'],
    ['inativar_fonte_receita', 'receitas.js'],
    // FIN-CARTOES-1 (compras e cartoes)
    ['criar_compra', 'cartoes.js'],
    ['editar_compra', 'cartoes.js'],
    ['excluir_compra', 'cartoes.js'],
    ['criar_cartao', 'cartoes.js'],
    ['editar_cartao', 'cartoes.js'],
    ['inativar_cartao', 'cartoes.js'],
    // FIN-CARTOES-RECORRENCIA-PENDENCIA-1 (so dispensa o aviso; nao muda recorrencia, compra nem fatura)
    ['dispensar_aviso_recorrencia', 'despesas-recorrencias.js'],
    // FIN-CARTOES-PAGAMENTO-1 (pagamento integral e estorno de fatura; debito/credito e saldo decididos no banco)
    ['pagar_fatura', ['cartoes.js', 'despesas-adaptador.js']],  // FIN-FIDELIDADE-DESPESAS-1: fatura tambem em Despesas
    ['estornar_pagamento_fatura', ['cartoes.js', 'despesas-adaptador.js']],
    // FIN-MOVIMENTACOES-1 (pagamento/estorno de despesa comum, recebimento/estorno de receita; saldo no banco)
    ['pagar_despesa', 'despesas-adaptador.js'],
    ['estornar_pagamento_despesa', 'despesas-adaptador.js'],
    ['receber_receita', 'receitas.js'],
    ['estornar_recebimento', 'receitas.js'],
    // FIN-MIGRACAO-FIDELIDADE-FASE-1 (gestao de perfis; o banco exige pode_gerir do perfil). Camada unica: perfil.js
    ['criar_perfil', 'perfil.js'],
    ['atualizar_perfil', 'perfil.js'],
    ['inativar_perfil', 'perfil.js'],
    ['reativar_perfil', 'perfil.js'],
    ['definir_perfil_padrao', 'perfil.js'],
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
            assert.ok(RPCS_DE_LEITURA.has(funcao) || [RPCS_DE_ESCRITA.get(funcao)].flat().includes(nome),
                `${nome} chama RPC nao liberada: ${funcao}`);
        }
        assert.doesNotMatch(fonte.replace(/\.rpc\s*\(\s*['"`][^'"`]+['"`]/g, ''), /\.rpc\s*\(/, `${nome} chama RPC com nome dinamico`);
        assert.doesNotMatch(fonte, /innerHTML|outerHTML|insertAdjacentHTML|document\.write/, `${nome} injeta HTML`);
    }
});

// FIN-MIGRACAO-FIDELIDADE-FASE-1: moldura do Flask montada no build.
const MENU_DO_FLASK = [
    ['Dashboard', ['Dashboard']],
    ['Operação', ['Lançamentos', 'Despesas', 'Recorrencias']],
    ['Gestão Financeira', ['Receitas', 'Cartões', 'Contas Bancárias', 'Financiamentos', 'Patrimônio', 'Documentos Fiscais']],
    ['Cadastros', ['Categorias', 'Mobilidade']],
    ['Ferramentas', ['Importar Cartão']],
    ['Sistema', ['Configurações e Preferências', 'Ajuda e Manual']],
];
const MIGRADAS = { 'contas.html': 'Despesas', 'receitas.html': 'Receitas', 'cartoes.html': 'Cartões',
    'categorias.html': 'Categorias', 'configuracoes.html': 'Configurações e Preferências', 'ajuda.html': 'Ajuda e Manual' };

function menuDe(html) {
    return [...html.matchAll(/<div class="app-nav-section-title">([^<]+)<\/div>([\s\S]*?)<\/div>\s*(?=<div class="app-nav-section">|<\/nav>)/g)]
        .map(([, secao, corpo]) => [secao, [...corpo.matchAll(/<span class="app-nav-text">([^<]+)<\/span>/g)].map((m) => m[1])]);
}

test('todas as paginas usam a moldura do Flask com o mesmo menu, sem pagina quebrada', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-moldura-'));
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const arquivos = (await readdir(destino, { recursive: true })).map((a) => a.split(path.sep).join('/'));
        assert.ok(!arquivos.some((a) => /^(moldura|paginas)(\/|$)/.test(a)), 'fontes da moldura fora do dist');
        assert.ok(arquivos.includes('css/shared/layout.css') && arquivos.includes('js/original/ajuda.js'));
        const paginas = arquivos.filter((a) => a.endsWith('.html') && a !== 'index.html');
        assert.equal(paginas.length, 15);
        for (const pagina of paginas) {
            const html = await readFile(path.join(destino, pagina), 'utf8');
            assert.doesNotMatch(html, /\{\{|\{%|url_for|<script>|\sstyle=|\son[a-z]+=/i, `${pagina}: marcador, script ou estilo inline`);
            assert.deepEqual(menuDe(html), MENU_DO_FLASK, `${pagina}: menu igual ao do Flask`);
            assert.match(html, /<body class="app-shell-body" data-protegido hidden>/);
            for (const id of ['perfil-financeiro-trigger', 'perfil-financeiro-options', 'app-logout-button', 'app-alertas-button']) {
                assert.match(html, new RegExp(`id="${id}"`), `${pagina}: ${id}`);
            }
            const ativos = [...html.matchAll(/class="app-nav-link active"/g)];
            assert.equal(ativos.length, 1, `${pagina}: um item ativo`);
            for (const [, href] of html.matchAll(/<a href="([^"#?]+)[^"]*" class="app-nav-link/g)) {
                assert.ok(arquivos.includes(href), `${pagina}: link ${href} existe`);
            }
            const emMigracao = [...html.matchAll(/data-em-migracao[^>]*>[\s\S]*?<span class="app-nav-text">([^<]+)<\/span>\s*<span class="app-nav-status">Em migração<\/span>/g)].map((m) => m[1]);
            assert.deepEqual(emMigracao.sort(), MENU_DO_FLASK.flatMap(([, itens]) => itens)
                .filter((item) => !Object.values(MIGRADAS).includes(item)).sort(), `${pagina}: itens em migracao`);
        }
        const despesas = await readFile(path.join(destino, 'contas.html'), 'utf8');
        assert.match(despesas, /<a href="contas.html" class="app-nav-link active" data-pagina="despesas" aria-current="page">/);
        assert.match(despesas, /<span>Gerenciamento de Despesas<\/span>/);
        const dashboard = await readFile(path.join(destino, 'dashboard.html'), 'utf8');
        assert.match(dashboard, /class="modulo-em-migracao"/);
        assert.match(dashboard, /<script type="module" src="js\/pagina.js"><\/script>/);
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

test('montagem escapa titulos e falha com marcador nao resolvido', () => {
    const base = '<title>{{documento}}</title><span>{{titulo}}</span>{{css}}{{acao}}{{conteudo}}{{scripts}}';
    const html = montarPagina(base, { arquivo: 'x.html', titulo: '<b>', conteudo: 'c', acao: '' }, new Set());
    assert.match(html, /<span>&lt;b&gt;<\/span>/);
    assert.throws(() => montarPagina(`${base}{{outro}}`, { arquivo: 'x.html', titulo: 't', conteudo: '' }, new Set()),
        /nao resolvido/);
});
