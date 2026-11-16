// FIN-CACHE-01 — versao por conteudo nos enderecos de JS/CSS (scripts/versionar.mjs).
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { versionarRecursos } from '../../scripts/versionar.mjs';

const ARQUIVOS = {
    'index.html': '<link rel="stylesheet" href="css/app.css"><script src="config.js"></script>'
        + '<script type="module" src="js/pagina.js"></script><link rel="icon" href="icones/a.png?v=2"><a href="https://x.test/a.js">x</a>',
    'outra.html': '<script type="module" src="./js/comum.js"></script>',
    'config.js': 'window.CF_CONFIG = {};\n',
    'css/app.css': 'body { color: #000; }\n',
    'js/pagina.js': "import { a } from './comum.js';\nimport {\n    b,\n} from \"./sub/b.js\";\nexport * from './sub/b.js';\n"
        + "const pdf = () => import('../vendor/pdf.min.mjs');\nconst w = new URL('../vendor/pdf.worker.min.mjs', import.meta.url);\n"
        + "const pasta = new URL('../vendor/ocr-1.0/', import.meta.url);\n",
    'js/comum.js': "export const a = 1;\n",
    'js/sub/b.js': "import { c } from '../ciclo-c.js';\nexport const b = c;\n",
    'js/ciclo-c.js': "import { d } from './ciclo-d.js';\nexport const c = 1; export const e = () => d;\n",
    'js/ciclo-d.js': "import { c } from './ciclo-c.js';\nexport const d = () => c;\n",
    'vendor/pdf.min.mjs': "export default 1; import('./nao-existe.js');\n",  // vendor nao e lido por dentro
    'vendor/pdf.worker.min.mjs': 'self.x = 1;\n',
    'vendor/ocr-1.0/worker.min.js': 'self.y = 1;\n',
};

async function montar(alteracoes = {}) {
    const raiz = await mkdtemp(path.join(os.tmpdir(), 'cf-versionar-'));
    for (const [nome, texto] of Object.entries({ ...ARQUIVOS, ...alteracoes })) {
        await mkdir(path.dirname(path.join(raiz, nome)), { recursive: true });
        await writeFile(path.join(raiz, nome), texto);
    }
    return raiz;
}

const ler = (raiz, nome) => readFile(path.join(raiz, nome), 'utf8');

test('toda referencia a JS/CSS do site recebe a versao; o mesmo arquivo tem o mesmo endereco em todo lugar', async () => {
    const raiz = await montar();
    try {
        const { versoes } = await versionarRecursos(raiz);
        const v = (nome) => versoes.get(nome);
        for (const nome of ['config.js', 'css/app.css', 'js/pagina.js', 'js/comum.js', 'js/sub/b.js', 'vendor/pdf.min.mjs']) assert.match(v(nome), /^[0-9a-f]{12}$/, nome);
        const index = await ler(raiz, 'index.html');
        assert.ok(index.includes(`href="css/app.css?v=${v('css/app.css')}"`));
        assert.ok(index.includes(`src="config.js?v=${v('config.js')}"`));
        assert.ok(index.includes(`src="js/pagina.js?v=${v('js/pagina.js')}"`));
        assert.ok(index.includes('href="icones/a.png?v=2"'), 'referencia com consulta propria fica como estava');
        assert.ok(index.includes('href="https://x.test/a.js"'), 'endereco externo nao muda');
        assert.ok((await ler(raiz, 'outra.html')).includes(`src="./js/comum.js?v=${v('js/comum.js')}"`));
        const pagina = await ler(raiz, 'js/pagina.js');
        assert.ok(pagina.includes(`from './comum.js?v=${v('js/comum.js')}'`));
        assert.ok(pagina.includes(`} from "./sub/b.js?v=${v('js/sub/b.js')}"`), 'import em varias linhas e aspas duplas');
        assert.ok(pagina.includes(`export * from './sub/b.js?v=${v('js/sub/b.js')}'`));
        assert.ok(pagina.includes(`import('../vendor/pdf.min.mjs?v=${v('vendor/pdf.min.mjs')}')`));
        assert.ok(pagina.includes(`new URL('../vendor/pdf.worker.min.mjs?v=${v('vendor/pdf.worker.min.mjs')}', import.meta.url)`));
        assert.ok(pagina.includes("new URL('../vendor/ocr-1.0/', import.meta.url)"), 'pasta (versao no nome) fica como estava');
        // ciclo: hash comum, e cada membro aponta para o outro com ele
        assert.equal(v('js/ciclo-c.js'), v('js/ciclo-d.js'));
        assert.ok((await ler(raiz, 'js/ciclo-c.js')).includes(`'./ciclo-d.js?v=${v('js/ciclo-d.js')}'`));
        assert.ok((await ler(raiz, 'js/ciclo-d.js')).includes(`'./ciclo-c.js?v=${v('js/ciclo-c.js')}'`));
        assert.equal(await ler(raiz, 'vendor/pdf.min.mjs'), ARQUIVOS['vendor/pdf.min.mjs'], 'vendor nao e reescrito');
    } finally {
        await rm(raiz, { recursive: true, force: true });
    }
});

test('mudar um modulo interno muda o endereco de quem o importa ate o HTML; o resto mantem o endereco (e o cache)', async () => {
    const a = await montar();
    const b = await montar({ 'js/ciclo-d.js': "import { c } from './ciclo-c.js';\nexport const d = () => c + 1;\n" });
    const c = await montar();
    try {
        const va = (await versionarRecursos(a)).versoes;
        const vb = (await versionarRecursos(b)).versoes;
        const vc = (await versionarRecursos(c)).versoes;
        assert.deepEqual([...va], [...vc], 'mesmo conteudo, mesmas versoes (build deterministico)');
        for (const nome of ['js/ciclo-c.js', 'js/ciclo-d.js', 'js/sub/b.js', 'js/pagina.js']) assert.notEqual(va.get(nome), vb.get(nome), nome);
        for (const nome of ['js/comum.js', 'css/app.css', 'config.js', 'vendor/pdf.min.mjs', 'vendor/pdf.worker.min.mjs']) assert.equal(va.get(nome), vb.get(nome), nome);
        assert.notEqual(await ler(a, 'index.html'), await ler(b, 'index.html'));
        assert.equal(await ler(a, 'outra.html'), await ler(b, 'outra.html'));
    } finally {
        for (const raiz of [a, b, c]) await rm(raiz, { recursive: true, force: true });
    }
});

test('importacao ou referencia a arquivo inexistente interrompe o build', async () => {
    const raiz = await montar({ 'js/comum.js': "import './sumiu.js';\nexport const a = 1;\n" });
    const html = await montar({ 'outra.html': '<script src="js/sumiu.js"></script>' });
    try {
        await assert.rejects(versionarRecursos(raiz), /js\/comum\.js: importa \.\/sumiu\.js, que nao existe no dist/);
        await assert.rejects(versionarRecursos(html), /outra\.html: referencia js\/sumiu\.js, que nao existe no dist/);
    } finally {
        await rm(raiz, { recursive: true, force: true });
        await rm(html, { recursive: true, force: true });
    }
});
