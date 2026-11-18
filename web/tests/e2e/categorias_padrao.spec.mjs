// FIN-CADASTROS-PADRAO-01 — catalogo padrao e personalizacao na tela de Categorias, com o usuario B (usuario comum) no
// "Perfil B". Conferido na tela e no banco: selos Padrao e Minha; categoria particular criada com natureza, visivel so para o
// dono; palavra-chave propria; palavra padrao desligada so para o usuario e restaurada; categoria de cartao padrao protegida.
// O usuario A confere, no fim, que nada disso chegou a ele. Tudo o que o teste cria e removido. Dados FICTICIOS.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const EVIDENCIAS = process.env.CF_CP_EVIDENCIAS || '';  // capturas para a homologacao (opcional; dados ficticios)
const PARTICULAR = 'Pets E2E';

test.use({ viewport: { width: 1366, height: 900 } });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to|Ponte CSP/i.test(msg.text())) problemas.push(msg.text());
        if (msg.type() === 'warning' && /Ponte CSP/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS').toEqual([]);
});

// O cenario do E2E nasce com o catalogo no sistema anterior, e enquanto ele estiver la nada do catalogo e gravado pelo novo
// aplicativo (nem o que e do usuario). Estes testes sao do catalogo ja no novo aplicativo, como em producao; no fim volta.
async function admin(request, pedido) {
    const r = await request.post('/__e2e__/admin', { data: pedido });
    expect(r.ok(), JSON.stringify(pedido)).toBe(true);
    return r.json();
}

test.beforeAll(async ({ request }) => {
    await admin(request, { acao: 'catalogo', escritor: 'NOVO' });
});

test.afterAll(async ({ request }) => {
    await admin(request, { acao: 'catalogo', escritor: 'FLASK' });
});

async function evidencia(page, nome) {
    if (!EVIDENCIAS) return;
    mkdirSync(EVIDENCIAS, { recursive: true });
    await page.screenshot({ path: path.join(EVIDENCIAS, `${nome}.png`) });
}

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await page.goto('/categorias.html');
    await expect(page.locator('#categorias-lista .despesa-list-item').first()).toBeVisible();
}

const despesa = (page, nome) => page.locator('#categorias-lista .despesa-list-item', { hasText: nome });
const chip = (page, palavra) => page.locator('#categoria-despesa-detalhe .keyword-chip', { hasText: palavra });
const categorias = async (page) => (await chamarRpc(page, 'categorias_tela', { p_perfil_id: await perfilAtivoId(page), p_ativo: null })).corpo;
const palavrasDe = async (page, id) => ((await chamarRpc(page, 'palavras_chave_tela', { p_perfil_id: await perfilAtivoId(page) })).corpo[String(id)] || []);

test('usuario comum: categoria particular com natureza, palavra propria, palavra padrao desligada e restaurada', async ({ page }) => {
    test.setTimeout(90 * 1000);
    registrarDialogos(page);
    await entrar(page, B);
    const catalogo = await page.evaluate(async () => (await (await fetch('/api/categorias')).json()).data.map((c) => c.nome));
    await evidencia(page, 'categorias-1-catalogo-padrao');

    // Categoria particular: o formulario diz o que ela e e pede a natureza gerencial.
    await page.click('#btn-nova-categoria-despesa');
    await expect(page.locator('#modal-titulo')).toHaveText('Nova Categoria de Despesa (particular)');
    await page.fill('#nome', PARTICULAR);
    await page.fill('#descricao', 'Criada pelo E2E');
    await expect(page.locator('#cf-natureza')).toHaveValue('CONSUMO');
    await page.selectOption('#cf-natureza', 'APORTE');
    await evidencia(page, 'categorias-2-formulario-particular');
    await page.locator('#form-categoria button[type=submit]').click();
    await expect(despesa(page, PARTICULAR).locator('.cf-selo-catalogo')).toHaveText('Minha');
    const criada = (await categorias(page)).find((c) => c.nome === PARTICULAR);
    expect(criada).toMatchObject({ padrao: false, natureza: 'APORTE', ativo: true });
    await despesa(page, PARTICULAR).click();
    await expect(page.locator('#categoria-despesa-detalhe .cf-natureza strong')).toHaveText('Aporte');
    await expect(page.locator('[data-action="editar-despesa"]')).toBeVisible();   // a particular e editavel
    // nome de categoria padrao nao e aceito
    const repetida = await chamarRpc(page, 'criar_categoria', { p_dados: { nome: 'moradia' }, p_chave: crypto.randomUUID() });
    expect(repetida.corpo.message).toBe('Ja existe uma categoria com este nome');

    // Palavra-chave propria na particular.
    await page.fill('#nova-palavra-chave', 'Petshop E2E');
    await page.locator('#form-palavra-chave button[type=submit]').click();
    await expect(chip(page, 'petshop e2e')).toHaveAttribute('data-origem', 'PROPRIA');
    await evidencia(page, 'categorias-3-particular-com-palavra-propria');

    // Palavra PADRAO desligada so para este usuario: fica riscada, com o botao de restaurar; o catalogo nao muda.
    await despesa(page, 'Moradia').first().click();
    await expect(page.locator('#categoria-despesa-detalhe .keywords-card .card-title-inline p')).toContainText('vale só para a sua conta');
    const moradia = (await categorias(page)).find((c) => c.nome === 'Moradia');
    const padrao = (await palavrasDe(page, moradia.id)).find((p) => p.palavra === 'padaria');
    expect(padrao).toMatchObject({ origem: 'PADRAO', ativo: true });
    await chip(page, 'padaria').locator('button').click();
    await expect(chip(page, 'padaria')).toHaveAttribute('data-origem', 'DESLIGADA');
    expect((await palavrasDe(page, moradia.id)).find((p) => p.palavra === 'padaria')).toMatchObject({ origem: 'DESLIGADA', ativo: false });
    await evidencia(page, 'categorias-4-palavra-padrao-desligada');
    await chip(page, 'padaria').locator('button').click();  // restaurar
    await expect(chip(page, 'padaria')).toHaveAttribute('data-origem', 'PADRAO');
    expect((await palavrasDe(page, moradia.id)).find((p) => p.palavra === 'padaria')).toMatchObject({ id: padrao.id, origem: 'PADRAO', ativo: true });

    // Palavra propria numa categoria padrao, e de novo desligando a padrao (para o usuario A conferir que nao o alcanca).
    await page.fill('#nova-palavra-chave', 'Condominio do B');
    await page.locator('#form-palavra-chave button[type=submit]').click();
    await expect(chip(page, 'condominio do b')).toHaveAttribute('data-origem', 'PROPRIA');
    await chip(page, 'padaria').locator('button').click();
    await expect(chip(page, 'padaria')).toHaveAttribute('data-origem', 'DESLIGADA');
    expect(catalogo).not.toContain(PARTICULAR);
});

test('o outro usuario nao ve a categoria particular, nem as palavras, nem a palavra desligada', async ({ page }) => {
    await entrar(page, A);
    expect((await categorias(page)).map((c) => c.nome)).not.toContain(PARTICULAR);
    await expect(despesa(page, PARTICULAR)).toHaveCount(0);
    const moradia = (await categorias(page)).find((c) => c.nome === 'Moradia');
    const palavras = await palavrasDe(page, moradia.id);
    expect(palavras.find((p) => p.palavra === 'padaria')).toMatchObject({ origem: 'PADRAO', ativo: true });
    expect(palavras.map((p) => p.palavra)).not.toContain('condominio do b');
});

test('limpeza: B restaura a palavra padrao, remove as proprias e exclui a categoria particular', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await despesa(page, 'Moradia').first().click();
    await chip(page, 'padaria').locator('button').click();
    await expect(chip(page, 'padaria')).toHaveAttribute('data-origem', 'PADRAO');
    await chip(page, 'condominio do b').locator('button').click();
    await expect(chip(page, 'condominio do b')).toHaveCount(0);
    await despesa(page, PARTICULAR).click();
    await chip(page, 'petshop e2e').locator('button').click();
    await expect(chip(page, 'petshop e2e')).toHaveCount(0);
    await page.locator('[data-action="excluir-despesa"]').click();
    await expect(despesa(page, PARTICULAR)).toHaveCount(0);
    expect((await categorias(page)).map((c) => c.nome)).not.toContain(PARTICULAR);
    expect((await chamarRpc(page, 'palavras_chave_tela', { p_perfil_id: await perfilAtivoId(page) })).status).toBe(200);
    expect(dialogos.filter((m) => /Erro/.test(m))).toEqual([]);
});
