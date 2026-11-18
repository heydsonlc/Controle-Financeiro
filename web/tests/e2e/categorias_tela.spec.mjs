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
    // FIN-CADASTROS-PADRAO-01: sem avisos de bloqueio. O que e do aplicativo aparece com o selo "Padrao"; o modo de edicao do
    // catalogo padrao so existe para quem o administra (B e usuario comum).
    await expect(page.locator('.categorias-aviso-fase')).toHaveCount(0);
    await expect(page.locator('#cf-aviso-catalogo')).toHaveCount(0);
    await expect(page.locator('#cf-modo-catalogo')).toHaveCount(0);
    await expect(despesa(page, 'Moradia').first().locator('.cf-selo-catalogo')).toHaveText('Padrão');
    await despesa(page, 'Moradia').first().click();
    await expect(page.locator('#categoria-despesa-detalhe')).toContainText('padaria');
    await page.click('#tab-cartao');
    await expect(cartao(page, 'Mercado B')).toBeVisible();
    await expect(cartao(page, 'Viagem B')).toBeVisible();
    await cartao(page, 'Mercado B').click();
    await expect(page.locator('#categoria-cartao-detalhe .linked-chip', { hasText: 'Moradia' })).toBeVisible();
    // Isolamento: as Categorias do Cartao do Pessoal (usuario A) nao aparecem para B.
    await expect(cartao(page, 'Mercado RC')).toHaveCount(0);

    // FIN-MIGRACAO-LASTRO-EMPRESA-01: categoria sem descricao mostra o texto, nao os codigos HTML (defeito do original).
    await page.click('#tab-despesas');
    const semDescricao = (await chamarRpc(page, 'categorias_tela', { p_perfil_id: await perfilAtivoId(page), p_ativo: true })).corpo
        .find((c) => !c.descricao);
    await despesa(page, semDescricao.nome).first().click();
    await expect(page.locator('#categoria-despesa-detalhe')).toContainText('Sem descrição cadastrada.');
    await expect(page.locator('#categoria-despesa-detalhe')).not.toContainText('&ccedil;');
});

// FIN-UX-SIMPLIFICACAO-CATEGORIAS-01: sem os cards-resumo da direita, lista mais larga (mesma largura nas duas abas),
// itens mais baixos e Categoria do Cartao em duas linhas (dados em cima, vinculos embaixo, na largura do painel).
test('layout: sem cards-resumo, lista larga e estavel, itens compactos, Cartao em duas linhas', async ({ page }) => {
    await entrar(page, B);
    await abrir(page);
    await expect(page.locator('.categorias-summary-sidebar, .categorias-summary, [id^="summary-"]')).toHaveCount(0);
    const larguraLista = (seletor) => page.locator(seletor).evaluate((el) => el.closest('aside').getBoundingClientRect().width);
    const despesas = await larguraLista('#categorias-lista');
    expect(despesas).toBeGreaterThanOrEqual(320);
    expect(despesas).toBeLessThanOrEqual(380);
    expect((await despesa(page, 'Moradia').first().boundingBox()).height).toBeLessThan(66);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

    await page.click('#tab-cartao');
    await cartao(page, 'Mercado B').click();
    expect(await larguraLista('#categorias-cartao-lista')).toBe(despesas);
    const dados = await page.locator('#form-categoria-cartao').boundingBox();
    const vinculos = await page.locator('#categoria-cartao-detalhe .vinculos-card').boundingBox();
    expect(vinculos.y).toBeGreaterThanOrEqual(dados.y + dados.height);
    expect(Math.abs(vinculos.width - dados.width)).toBeLessThanOrEqual(1);
    expect(Math.abs(vinculos.x - dados.x)).toBeLessThanOrEqual(1);
    await expect(page.locator('#categoria-cartao-detalhe .linked-chip', { hasText: 'Moradia' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
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

// FIN-CADASTROS-PADRAO-01: a categoria PADRAO e do aplicativo. O usuario comum nao a edita nem exclui (as acoes nem
// aparecem) e nao cria categoria padrao (o banco recusa); o cadastro dele e de categorias PARTICULARES, que nao dependem de o
// catalogo padrao estar habilitado para gravacao. O caminho de quem administra o catalogo esta em migracao_p0p1.spec.mjs.
test('usuario comum: categoria padrao sem editar nem excluir; criar categoria padrao e recusado e nada e gravado', async ({ page }) => {
    await entrar(page, B);
    await abrir(page);
    await despesa(page, 'Moradia').first().click();
    await expect(page.locator('#categoria-despesa-detalhe')).toContainText('padaria');
    await expect(page.locator('#categoria-despesa-detalhe .detail-identity .cf-selo-catalogo')).toHaveText('Padrão');
    await expect(page.locator('[data-action="editar-despesa"]')).toBeHidden();
    await expect(page.locator('[data-action="excluir-despesa"]')).toBeHidden();
    await expect(page.locator('#btn-nova-categoria-despesa')).toBeVisible();   // categoria particular
    await expect(page.locator('#form-palavra-chave')).toBeVisible();           // palavra-chave propria

    const perfil = await perfilAtivoId(page);
    const antes = (await chamarRpc(page, 'categorias_tela', { p_perfil_id: perfil, p_ativo: null })).corpo;
    const moradia = antes.find((c) => c.nome === 'Moradia');
    const tentativas = [
        await chamarRpc(page, 'criar_categoria', { p_dados: { nome: 'Categoria Global E2E', padrao: true }, p_chave: crypto.randomUUID() }),
        await chamarRpc(page, 'editar_categoria', { p_categoria_id: moradia.id, p_dados: { nome: 'Tomada' } }),
        await chamarRpc(page, 'excluir_categoria', { p_categoria_id: moradia.id }),
        await chamarRpc(page, 'definir_natureza_categoria', { p_categoria_id: moradia.id, p_natureza: 'APORTE', p_chave: crypto.randomUUID() }),
        await chamarRpc(page, 'criar_palavra_chave', { p_categoria_id: moradia.id, p_palavra: 'global e2e' }),
    ];
    expect(tentativas.map((t) => t.status)).toEqual([400, 400, 400, 400, 400]);  // catalogo padrao nao habilitado para gravacao neste cenario
    for (const t of tentativas) expect(t.corpo.message).toMatch(/catalogo de categorias/i);
    expect((await chamarRpc(page, 'categorias_tela', { p_perfil_id: perfil, p_ativo: null })).corpo).toEqual(antes);
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
