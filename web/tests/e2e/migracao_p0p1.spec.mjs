// FIN-MIGRACAO-P0P1-01 (Etapa 1) — Empresa no novo aplicativo, envio de Documentos Fiscais e catalogo de categorias, pela
// tela. Usuario D (ficticio), titular de uma Empresa VAZIA ainda sem escritor NOVO, como a Empresa real antes da Etapa 2
// (tests/supabase_local.py, semear_empresa_vazia). As operacoes de administrador da Etapa 2 sao feitas pelo gancho so de
// teste /__e2e__/admin (run_e2e.py), que tambem devolve o retrato do perfil. Ordem fixa (serial): cada teste parte do
// estado do anterior; no fim o catalogo volta ao padrao (escritor FLASK, sem gestor) para os outros specs.
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

import { expect, test } from '@playwright/test';

import { gerarPdf } from '../pdf-ficticio.mjs';
import { abrirDespesas, cartoesDespesa, chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const D = { email: process.env.CF_EMAIL_D || 'usuario.d@teste.local', senha: process.env.CF_SENHA_D };
const PDF = gerarPdf([[[[50, 'Recibo P0P1 (ficticio)']], [[50, 'Valor R$ 123,45']]]]);  // 1 pagina, 2 linhas
const NAO_HABILITADO = 'Este perfil ainda não está habilitado para gravação no novo aplicativo. Nada foi gravado.';
const ENGANOSO = /Flask|sistema atual/i;
const CATEGORIA = 'TESTE MIGRACAO CATALOGO';

test.describe.configure({ mode: 'serial' });
test.skip(!process.env.CF_E2E_LOCAL, 'so no ambiente local descartavel (gancho de administrador)');
test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to|Ponte CSP/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (r) => { if (new URL(r.url()).pathname.startsWith('/api/')) problemas.push(`rede /api/: ${r.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamadas ao Flask').toEqual([]);
});

test.afterAll(async ({ request }) => {
    await admin(request, { acao: 'gestor', gestor: false });
    await admin(request, { acao: 'catalogo', escritor: 'FLASK' });
});

async function admin(request, pedido) {
    const r = await request.post('/__e2e__/admin', { data: pedido });
    expect(r.ok(), JSON.stringify(pedido)).toBe(true);
    return r.json();
}

async function entrar(page) {
    await page.goto('/index.html');
    await page.fill('#email', D.email);
    await page.fill('#senha', D.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-name')).toHaveText('Empresa D (vazia)');
}

async function enviarPelaTela(page) {
    await page.goto('/documentos-fiscais.html');
    await page.click('#ir-btn-importar');
    await page.setInputFiles('#ir-file-input', { name: 'nota-p0p1.pdf', mimeType: 'application/pdf', buffer: PDF });
    await expect(page.locator('#ir-upload-count')).toHaveText('1 arquivo(s) selecionado(s)');
    await page.click('#ir-upload-submit');
}

const mesDe = (deslocamento) => {
    const [ano, mes] = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date()).split('-').map(Number);
    const d = new Date(Date.UTC(ano, mes - 1 + deslocamento, 1));
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
};

test('Empresa sem escritor NOVO: envio pela tela recusado com o motivo, arquivo nao enviado, nada gravado', async ({ page, request }) => {
    const antes = await admin(request, { acao: 'retrato' });
    expect(Object.values(antes.linhas).reduce((a, b) => a + b, 0)).toBe(1);  // so o acesso do titular
    await entrar(page);
    await enviarPelaTela(page);

    const retorno = page.locator('#cf-upload-retorno');
    await expect(retorno).toHaveText(`Não foi possível enviar o documento. ${NAO_HABILITADO}`);
    await expect(retorno).toHaveAttribute('data-situacao', 'erro');
    await expect(retorno).toHaveAttribute('role', 'alert');
    const cartao = page.locator('#ir-upload-results .ir-upload-card', { hasText: 'nota-p0p1.pdf' });
    await expect(cartao).toContainText(NAO_HABILITADO);
    await expect(cartao.locator('.ir-status')).toHaveText('Não enviado');
    await expect(page.locator('#ir-import-erros')).toHaveText('1');
    expect(await page.locator('#ir-import-view').innerText()).not.toMatch(ENGANOSO);

    // A resposta da rota: 409, success:false e o motivo por arquivo (a tela nunca recebe lista vazia).
    const r = await page.evaluate(async (bytes) => {
        const form = new FormData();
        form.append('arquivos', new File([new Uint8Array(bytes)], 'nota-p0p1.pdf', { type: 'application/pdf' }));
        const resposta = await fetch('/api/ir/comprovantes/upload', { method: 'POST', body: form });
        return { status: resposta.status, corpo: await resposta.json() };
    }, [...PDF]);
    expect(r).toEqual({ status: 409, corpo: { success: false, error: NAO_HABILITADO, total: 1,
                                              data: [{ success: false, error: NAO_HABILITADO, arquivo: 'nota-p0p1.pdf' }] } });
    expect(await admin(request, { acao: 'retrato' })).toEqual(antes);
});

test('ativar o escritor NOVO nao gera nada: Despesas aberta em varias competencias', async ({ page, request }) => {
    // A ativacao so grava a linha do escritor e a do historico (tabelas administrativas); nenhum dado do perfil.
    const ADMINISTRATIVAS = ['financeiro.gerador_recorrencia', 'financeiro.gerador_recorrencia_historico'];
    const semAdministrativas = (r) => ({ ...r, linhas: Object.fromEntries(Object.entries(r.linhas).filter(([t]) => !ADMINISTRATIVAS.includes(t))) });
    const antes = await admin(request, { acao: 'retrato' });
    expect(ADMINISTRATIVAS.map((t) => antes.linhas[t])).toEqual([0, 0]);
    expect((await admin(request, { acao: 'escritor', gerador: 'NOVO' })).resultado).toBe('Perfil 120: FLASK (padrao) -> NOVO');
    const ativado = await admin(request, { acao: 'retrato' });
    expect(ADMINISTRATIVAS.map((t) => ativado.linhas[t])).toEqual([1, 1]);
    expect(semAdministrativas(ativado)).toEqual(semAdministrativas(antes));

    await entrar(page);
    const perfil = await perfilAtivoId(page);
    for (const mes of [mesDe(0), mesDe(1), mesDe(-3), '2027-06']) {
        await abrirDespesas(page, mes);
        await expect(cartoesDespesa(page)).toHaveCount(0);
        const previa = (await chamarRpc(page, 'previa_geracao', { p_perfil_id: perfil, p_mes: `${mes}-01` })).corpo;
        expect([previa.gerador, previa.pode_gerar, previa.a_gerar, previa.competencias], mes).toEqual(['NOVO', true, 0, []]);
    }
    expect(await admin(request, { acao: 'retrato' })).toEqual(ativado);
});

test('Empresa NOVO: envio pela tela grava, aparece na lista e abre o arquivo', async ({ page, request, context }) => {
    await entrar(page);
    await enviarPelaTela(page);
    const retorno = page.locator('#cf-upload-retorno');
    await expect(retorno).toHaveText('Documento enviado.');
    await expect(retorno).toHaveAttribute('data-situacao', 'sucesso');
    const cartao = page.locator('#ir-upload-results .ir-upload-card', { hasText: 'nota-p0p1' });
    await expect(cartao).toBeVisible();
    await expect(page.locator('#ir-import-erros')).toHaveText('0');

    const depois = await admin(request, { acao: 'retrato' });
    expect(depois.linhas['public.ir_comprovante']).toBe(1);
    // Bytes preservados (md5 do banco = md5 do arquivo enviado), nome, MIME, tamanho e perfil.
    expect(depois.arquivos).toEqual([{ nome: 'nota-p0p1.pdf', mime: 'application/pdf', tamanho: PDF.length,
                                       md5: createHash('md5').update(PDF).digest('hex'), perfil: 120 }]);

    // "Abrir arquivo": a nova aba recebe o blob do Supabase. O Chromium de teste nao tem visualizador de PDF e entrega o
    // PDF como download da propria aba; o conteudo entregue e byte a byte o enviado.
    const baixado = new Promise((resolver) => context.once('page', (aba) => aba.once('download', resolver)));
    await cartao.locator('a', { hasText: 'Abrir arquivo' }).click();
    const download = await baixado;
    expect(download.url()).toMatch(/^blob:/);
    const recebido = await readFile(await download.path());
    expect(Buffer.compare(recebido, PDF)).toBe(0);
    await download.page().close();

    await page.click('#ir-btn-voltar');
    const perfil = await perfilAtivoId(page);
    expect((await chamarRpc(page, 'ir_comprovantes_tela', { p_perfil_id: perfil, p_filtros: {}, p_id: null })).corpo.total).toBe(1);
    await expect(page.locator('#ir-comprovantes-tbody tr')).toHaveCount(1);
});

const despesa = (page, nome) => page.locator('#categorias-lista .despesa-list-item', { hasText: nome });

async function abrirCategorias(page) {
    await page.goto('/categorias.html');
    await expect(page.locator('#categorias-lista .despesa-list-item').first()).toBeVisible();
}

async function lerCategoria(page, nome) {
    const lista = (await chamarRpc(page, 'categorias_tela', { p_perfil_id: await perfilAtivoId(page), p_ativo: null })).corpo;
    return lista.find((c) => c.nome === nome);
}

test('catalogo no novo aplicativo: conta nao gestora nao ve as acoes e e recusada', async ({ page, request }) => {
    await admin(request, { acao: 'catalogo', escritor: 'NOVO' });
    await entrar(page);
    await abrirCategorias(page);
    await expect(page.locator('#cf-aviso-catalogo')).toHaveText(/^Esta conta não administra o catálogo de categorias de despesa/);
    await expect(page.locator('#btn-nova-categoria-despesa')).toBeHidden();
    await despesa(page, 'Moradia').first().click();
    await expect(page.locator('#form-palavra-chave')).toBeHidden();
    await expect(page.locator('[data-action="editar-despesa"]')).toBeHidden();
    const r = await page.evaluate(async () => {
        const resposta = await fetch('/api/categorias', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                          body: JSON.stringify({ nome: 'Nao grava D' }) });
        return { status: resposta.status, corpo: await resposta.json() };
    });
    expect(r).toEqual({ status: 403, corpo: { success: false, error: 'Esta conta não administra o catálogo de categorias. Nada foi gravado.' } });
    expect(await lerCategoria(page, 'Nao grava D')).toBeUndefined();
});

test('gestor do catalogo: criar, editar, palavras-chave, protecoes e excluir pela tela; sistemicas intactas', async ({ page, request }) => {
    await admin(request, { acao: 'gestor', gestor: true });
    const antes = (await admin(request, { acao: 'retrato' })).catalogo;
    expect(antes.n_sistemicas).toBe(10);
    const dialogos = registrarDialogos(page);
    await entrar(page);
    await abrirCategorias(page);
    await expect(page.locator('#cf-aviso-catalogo')).toHaveCount(0);
    await expect(page.locator('.categorias-aviso-fase')).toHaveCount(0);  // FIN-UX-SIMPLIFICACAO-CATEGORIAS-01: aviso de fase saiu

    // Criar: nome, descricao, cor, icone e ativa. O painel de logo fica desabilitado, com o aviso.
    await page.click('#btn-nova-categoria-despesa');
    await expect(page.locator('#logo-enviar')).toBeDisabled();
    await expect(page.locator('#logo-remover')).toBeDisabled();
    await expect(page.locator('#logo-upload-input')).toBeDisabled();
    await expect(page.locator('#logo-upload-status')).toHaveText('Upload de logo ainda não disponível nesta versão.');
    await page.fill('#nome', CATEGORIA);
    await page.fill('#descricao', 'Criada pelo E2E');
    await page.fill('#cor', '#123456');
    await page.locator('#icone-picker-grid button').first().click();
    const icone = await page.inputValue('#icone');
    expect(icone).not.toBe('');
    await page.locator('#form-categoria button[type=submit]').click();
    await expect(despesa(page, CATEGORIA)).toBeVisible();
    expect(await lerCategoria(page, CATEGORIA)).toMatchObject({ descricao: 'Criada pelo E2E', cor: '#123456', icone, ativo: true,
                                                                 sistemica: false });

    // Editar todos os campos (inclusive inativar); com o filtro "Todas" ela continua na lista.
    await despesa(page, CATEGORIA).click();
    await page.locator('[data-action="editar-despesa"]').click();
    await expect(page.locator('#logo-enviar')).toBeDisabled();
    await page.fill('#nome', `${CATEGORIA} (editada)`);
    await page.fill('#descricao', 'Editada pelo E2E');
    await page.fill('#cor', '#654321');
    await page.locator('#icone-picker-grid button').nth(1).click();
    const icone2 = await page.inputValue('#icone');
    await page.uncheck('#ativo');
    await page.locator('#form-categoria button[type=submit]').click();
    await page.selectOption('#categorias-status', 'todas');
    await expect(despesa(page, `${CATEGORIA} (editada)`)).toBeVisible();
    expect(await lerCategoria(page, `${CATEGORIA} (editada)`)).toMatchObject({ descricao: 'Editada pelo E2E', cor: '#654321',
                                                                               icone: icone2, ativo: false });

    // Palavras-chave: adicionar, listar, remover.
    await despesa(page, `${CATEGORIA} (editada)`).click();
    await page.fill('#nova-palavra-chave', 'Teste P0P1');
    await page.locator('#form-palavra-chave button[type=submit]').click();
    await expect(page.locator('#categoria-despesa-detalhe')).toContainText('teste p0p1');
    await page.locator('[data-action="remover-palavra-chave"]').first().click();
    await expect(page.locator('#categoria-despesa-detalhe')).not.toContainText('teste p0p1');

    // Protecoes: categoria em uso nao e excluida; sistemica nao e editada nem excluida.
    await despesa(page, 'Moradia').first().click();
    await page.locator('[data-action="excluir-despesa"]').click();
    await expect.poll(() => dialogos.some((m) => /registros vinculados/.test(m))).toBe(true);
    await expect(despesa(page, 'Moradia').first()).toBeVisible();
    const mob = (await chamarRpc(page, 'categorias_tela', { p_perfil_id: await perfilAtivoId(page), p_ativo: null })).corpo
        .find((c) => c.nome === 'Combustível');
    const tentativas = await page.evaluate(async (id) => Promise.all([
        fetch(`/api/categorias/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ descricao: 'x' }) }),
        fetch(`/api/categorias/${id}`, { method: 'DELETE' }),
    ].map(async (p) => (await p).json())), mob.id);
    expect(tentativas.map((t) => t.error)).toEqual(['Esta categoria e sistemica e nao pode ser editada.',
                                                    'Esta categoria e sistemica e nao pode ser excluida.']);

    // Excluir a categoria de teste pela tela: some da lista e do banco, com as palavras-chave dela.
    await despesa(page, `${CATEGORIA} (editada)`).click();
    await page.locator('[data-action="excluir-despesa"]').click();
    await expect(despesa(page, `${CATEGORIA} (editada)`)).toHaveCount(0);
    expect(await lerCategoria(page, `${CATEGORIA} (editada)`)).toBeUndefined();
    expect((await admin(request, { acao: 'retrato' })).catalogo).toEqual(antes);
    expect(dialogos.filter((m) => ENGANOSO.test(m))).toEqual([]);
});
