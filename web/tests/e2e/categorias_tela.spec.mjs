// FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 — tela original de Categorias do Flask (js/original/categorias.js) sobre o
// Supabase, pelo adaptador. Dados FICTICIOS (tests/supabase_local.py): categorias de despesa globais (Moradia 201,
// Saude 202...), palavra-chave "padaria" (201) e as Categorias do Cartao "Mercado B" (vinculada a 201) e "Viagem B" do
// "Perfil B" (atribuido ao novo aplicativo). Escrita so com o usuario B no Perfil B, numa Categoria do Cartao criada
// aqui e desativada no fim. Categorias de despesa (globais): nenhuma escrita aqui (catalogo no padrao, nao habilitado).
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';
import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (r) => { if (new URL(r.url()).pathname.startsWith('/api/')) problemas.push(`rede /api/: ${r.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamadas ao Flask').toEqual([]);
});

const despesa = (page, nome) => page.locator('#categorias-lista .despesa-list-item', { hasText: nome });
const cartao = (page, nome) => page.locator('#categorias-cartao-lista .cartao-list-item', { hasText: nome });

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
}

async function abrir(page) {
    await page.goto('/categorias.html');
    await expect(page.locator('#categorias-lista .despesa-list-item').first()).toBeVisible();
}

test('tela original: categorias de despesa, palavras-chave, Categorias do Cartao e vinculos do perfil', async ({ page }) => {
    await entrar(page, B);
    await abrir(page);
    await expect(page.locator('.module-actionbar.categorias-toolbar')).toBeVisible();
    await expect(page.locator('.categorias-aviso-fase')).toContainText('Categorias do Cartão');
    await despesa(page, 'Moradia').first().click();
    await expect(page.locator('#categoria-despesa-detalhe')).toContainText('padaria');
    await page.click('#tab-cartao');
    await expect(cartao(page, 'Mercado B')).toBeVisible();
    await expect(cartao(page, 'Viagem B')).toBeVisible();
    await cartao(page, 'Mercado B').click();
    await expect(page.locator('#categoria-cartao-detalhe .linked-chip', { hasText: 'Moradia' })).toBeVisible();
    // Isolamento: as Categorias do Cartao do Pessoal (usuario A) nao aparecem para B.
    await expect(cartao(page, 'Mercado RC')).toHaveCount(0);
});

test('Perfil B: criar, editar, vincular, desvincular, desativar e reativar Categoria do Cartao', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrir(page);
    await page.click('#btn-nova-categoria-cartao');
    await page.fill('#cartao-nome', 'Farmacia Tela E2E');
    await page.fill('#cartao-descricao', 'Remedios e saude');
    await page.locator('#categoria-cartao-detalhe button[type=submit][form="form-categoria-cartao"]').click();
    await expect(cartao(page, 'Farmacia Tela E2E')).toBeVisible();
    const perfil = await perfilAtivoId(page);
    const lida = async () => (await chamarRpc(page, 'categorias_cartao_tela', { p_perfil_id: perfil, p_ativo: null })).corpo
        .find((c) => c.nome.startsWith('Farmacia Tela E2E'));
    expect((await lida()).descricao).toBe('Remedios e saude');

    await cartao(page, 'Farmacia Tela E2E').click();
    await page.fill('#cartao-nome', 'Farmacia Tela E2E (editada)');
    await page.locator('#categoria-cartao-detalhe button[type=submit][form="form-categoria-cartao"]').click();
    await expect(cartao(page, 'Farmacia Tela E2E (editada)')).toBeVisible();

    await cartao(page, 'Farmacia Tela E2E (editada)').click();
    await page.locator('#categorias-disponiveis-lista .available-chip', { hasText: 'Saude' }).first().click();
    await expect(page.locator('#categoria-cartao-detalhe .linked-chip', { hasText: 'Saude' })).toBeVisible();
    const id = (await lida()).id;
    const vinculos = async () => (await chamarRpc(page, 'categoria_cartao_despesas_tela', { p_perfil_id: perfil, p_ativo: true })).corpo[String(id)];
    expect((await vinculos()).map((v) => v.categoria_nome)).toEqual(['Saude']);
    // A mesma categoria de despesa nao vai para outra Categoria do Cartao ativa (Mercado B ja tem Moradia).
    await cartao(page, 'Mercado B').click();
    await expect(page.locator('#categorias-disponiveis-lista .available-chip', { hasText: 'Saude' })).toHaveCount(0);

    await cartao(page, 'Farmacia Tela E2E (editada)').click();
    await page.locator('#categoria-cartao-detalhe .linked-chip', { hasText: 'Saude' }).click();
    await expect(page.locator('#categoria-cartao-detalhe .linked-chip', { hasText: 'Saude' })).toHaveCount(0);
    expect(await vinculos()).toEqual([]);

    // Desativar: como no Flask, com o filtro "Ativas" ela sai da lista; em "Todas", reativar.
    await cartao(page, 'Farmacia Tela E2E (editada)').click();
    await page.locator('#categoria-cartao-detalhe [data-action="toggle-status"]').click();
    await expect(cartao(page, 'Farmacia Tela E2E (editada)')).toHaveCount(0);
    expect((await lida()).ativo).toBe(false);
    await page.selectOption('#categorias-status', 'todas');
    await cartao(page, 'Farmacia Tela E2E (editada)').click();
    await expect(page.locator('#categoria-cartao-detalhe [data-action="toggle-status"]')).toContainText('Reativar');
    await page.locator('#categoria-cartao-detalhe [data-action="toggle-status"]').click();
    await expect(page.locator('#categoria-cartao-detalhe [data-action="toggle-status"]')).toContainText('Desativar');
    expect((await lida()).ativo).toBe(true);
    expect(dialogos.filter((m) => /Deseja (desativar|reativar) a Categoria do Cartao/.test(m))).toHaveLength(2);

    // Fim: desativada de novo (nada e apagado; os specs seguintes nao a veem como ativa).
    await page.locator('#categoria-cartao-detalhe [data-action="toggle-status"]').click();
    await expect(page.locator('#categoria-cartao-detalhe [data-action="toggle-status"]')).toContainText('Reativar');
    expect((await lida()).ativo).toBe(false);
});

// FIN-MIGRACAO-P0P1-01: com o catalogo ainda nao habilitado (padrao, sem escritor), as acoes das categorias de despesa nem
// aparecem e o aviso diz o motivo (antes o formulario era preenchido e so o salvar recusava, citando o Flask). Uma chamada
// direta continua recusada pelo banco, sem gravar. O caminho do gestor esta em migracao_p0p1.spec.mjs.
test('catalogo ainda nao habilitado: acoes das categorias de despesa escondidas, com o motivo, e nada gravado', async ({ page }) => {
    await entrar(page, B);
    await abrir(page);
    await expect(page.locator('#cf-aviso-catalogo'))
        .toHaveText(/^O catálogo de categorias de despesa ainda não está habilitado para gravação nesta versão/);
    await expect(page.locator('#btn-nova-categoria-despesa')).toBeHidden();
    await despesa(page, 'Moradia').first().click();
    await expect(page.locator('#categoria-despesa-detalhe')).toContainText('padaria');
    await expect(page.locator('#form-palavra-chave')).toBeHidden();
    await expect(page.locator('[data-action="editar-despesa"]')).toBeHidden();
    await expect(page.locator('[data-action="excluir-despesa"]')).toBeHidden();
    await expect(page.locator('[data-action="remover-palavra-chave"]').first()).toBeHidden();
    for (const aviso of ['.categorias-aviso-fase', '#cf-aviso-catalogo']) {
        expect(await page.locator(aviso).innerText()).not.toMatch(/Flask|sistema atual/i);
    }

    const antes = (await chamarRpc(page, 'categorias_tela', { p_perfil_id: await perfilAtivoId(page), p_ativo: null })).corpo;
    const r = await page.evaluate(async () => {
        const resposta = await fetch('/api/categorias', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                          body: JSON.stringify({ nome: 'Categoria Global E2E' }) });
        return { status: resposta.status, corpo: await resposta.json() };
    });
    expect(r).toEqual({ status: 400, corpo: { success: false,
        error: 'O catálogo de categorias de despesa ainda não está habilitado para gravação no novo aplicativo. Nada foi gravado.' } });
    const depois = (await chamarRpc(page, 'categorias_tela', { p_perfil_id: await perfilAtivoId(page), p_ativo: null })).corpo;
    expect(depois).toEqual(antes);
});

test('perfil ainda no Flask (Pessoal) nao grava Categoria do Cartao; quem so le (Empresa) nao ve acoes', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, A);
    await abrir(page);
    await page.click('#btn-nova-categoria-cartao');
    await page.fill('#cartao-nome', 'Nao Grava Pessoal E2E');
    await page.locator('#categoria-cartao-detalhe button[type=submit][form="form-categoria-cartao"]').click();
    await expect.poll(() => dialogos.some((m) => m.includes('Este perfil ainda não está habilitado para gravação no novo aplicativo.'))).toBe(true);
    await expect(cartao(page, 'Nao Grava Pessoal E2E')).toHaveCount(0);

    await trocarPerfil(page, 'Empresa');
    await abrir(page);
    await expect(page.locator('#btn-nova-categoria-cartao')).toBeHidden();
});
