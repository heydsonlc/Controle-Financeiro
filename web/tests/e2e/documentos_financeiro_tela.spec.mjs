// FIN-PRE-PRODUCAO-1 (2.2) — botoes de Documentos pela tela, com o usuario C (titular da "Empresa C (ficticia)", ja no
// novo aplicativo; tests/supabase_local.py, semear_empresa_c_e2e): vincular o mesmo documento a dois bens e desvincular
// (Documentos Fiscais), "Gerar financeiro" (Documentos Fiscais) e "A partir de documento" (Despesas e Lancamentos), sem
// gerar duas vezes a partir do mesmo documento. Tudo com dados FICTICIOS.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId } from './despesas.mjs';

const C = { email: process.env.CF_EMAIL_C || 'usuario.c@teste.local', senha: process.env.CF_SENHA_C };

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    const avisos = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to|Ponte CSP/i.test(msg.text())) problemas.push(msg.text());
        if (msg.type() === 'warning' && /Ponte CSP/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (pedido) => { if (/\/api\//.test(new URL(pedido.url()).pathname)) problemas.push(`rede /api/: ${pedido.url()}`); });
    page.on('dialog', async (dialogo) => {
        avisos.push(dialogo.message());
        await (dialogo.type() === 'confirm' ? dialogo.accept() : dialogo.dismiss());
    });
    testInfo.problemas = problemas;
    testInfo.avisos = avisos;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamada ao Flask').toEqual([]);
});

async function entrar(page) {
    await page.goto('/index.html');
    await page.fill('#email', C.email);
    await page.fill('#senha', C.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-switcher')).toHaveAttribute('data-perfil-ativo-id', /^\d+$/);
}

async function idDoDocumento(page, nome) {
    const perfil = await perfilAtivoId(page);
    const lista = (await chamarRpc(page, 'ir_comprovantes_tela', { p_perfil_id: perfil, p_filtros: {}, p_id: null })).corpo;
    return { perfil, id: lista.data.find((d) => d.prestador_nome === nome).id };
}

const vinculos = async (page, perfil, id) => (await chamarRpc(page, 'vinculos_documento_tela', { p_perfil_id: perfil, p_comprovante_id: id })).corpo;

async function vincularAoBem(page, linha, bem) {
    await linha.locator('button[title="Vincular"]').click();
    await expect(page.locator('#ir-link-modal')).toHaveClass(/open/);
    await page.selectOption('#ir-link-tipo-entidade', 'PATRIMONIO');
    const opcao = page.locator('#ir-link-entidade option', { hasText: bem });
    await expect(opcao).toHaveCount(1);
    await page.selectOption('#ir-link-entidade', await opcao.getAttribute('value'));
    await page.selectOption('#ir-link-natureza', 'PATRIMONIO_IMOBILIZADO');
    await page.click('#ir-link-save');
    await expect(page.locator('#ir-link-modal')).not.toHaveClass(/open/);
}

test('documento em dois bens pela tela (vincular duas vezes) e desvincular um deles', async ({ page }) => {
    await entrar(page);
    await page.goto('/documentos-fiscais.html');
    const linha = page.locator('#ir-comprovantes-tbody tr', { hasText: 'Nota de itens C (ficticia)' });
    await expect(linha).toBeVisible();
    const { perfil, id } = await idDoDocumento(page, 'Nota de itens C (ficticia)');

    await vincularAoBem(page, linha, 'Notebook C (ficticio)');
    await vincularAoBem(page, linha, 'Monitor C (ficticio)');
    expect((await vinculos(page, perfil, id)).map((v) => v.resumo_entidade).sort())
        .toEqual(['Monitor C (ficticio)', 'Notebook C (ficticio)']);

    // Vinculos ativos no modal, com "Desvincular" (acrescimo ao Flask): o vinculo fica inativo.
    await linha.locator('button[title="Vincular"]').click();
    const ativos = page.locator('.cf-vinculos-ativos li');
    await expect(ativos).toHaveCount(2);
    await ativos.filter({ hasText: 'Monitor C (ficticio)' }).locator('button.cf-desvincular').click();
    await expect(ativos).toHaveCount(1);
    await expect(ativos.first()).toContainText('PATRIMONIO - Notebook C (ficticio)');
    expect((await vinculos(page, perfil, id)).map((v) => v.resumo_entidade)).toEqual(['Notebook C (ficticio)']);
});

test('Gerar financeiro na tela de Documentos: despesa criada uma vez so', async ({ page }, testInfo) => {
    await entrar(page);
    await page.goto('/documentos-fiscais.html');
    const linha = page.locator('#ir-comprovantes-tbody tr', { hasText: 'Servico C (ficticio)' });
    await linha.locator('button[title="Revisar"]').click();
    await page.click('#ir-review-financeiro');
    await expect(page.locator('#ir-sugestao-financeira-modal')).toHaveClass(/open/);
    await expect(page.locator('#ir-sugestao-descricao')).toHaveValue(/^Servico C \(ficticio\)/);
    await expect(page.locator('#ir-sugestao-valor')).toHaveValue('300');
    await page.selectOption('#ir-sugestao-categoria', { index: 1 });
    await page.click('#ir-sugestao-confirmar');
    await expect(page.locator('#ir-sugestao-financeira-modal')).not.toHaveClass(/open/);
    const { perfil, id } = await idDoDocumento(page, 'Servico C (ficticio)');
    expect((await vinculos(page, perfil, id)).map((v) => v.tipo_entidade)).toEqual(['CONTA']);

    // De novo: recusado (o mesmo documento nao gera duas despesas).
    await linha.locator('button[title="Revisar"]').click();
    await page.click('#ir-review-financeiro');
    await page.selectOption('#ir-sugestao-categoria', { index: 1 });
    await page.click('#ir-sugestao-confirmar');
    await expect.poll(() => testInfo.avisos.join(' | ')).toContain('ja gerou uma despesa ou lancamento');
    expect((await vinculos(page, perfil, id)).length).toBe(1);
});

test('A partir de documento em Despesas e em Lancamentos', async ({ page }) => {
    await entrar(page);
    await page.click('.btn-doc-atalho-despesa');
    await page.locator('#doc-desp-lista .doc-atalho-item', { hasText: 'Despesa C (ficticia)' }).click();
    await expect(page.locator('#doc-desp-descricao')).toHaveValue(/^Despesa C \(ficticia\)/);
    await page.selectOption('#doc-desp-categoria', { index: 1 });
    await page.click('#doc-desp-confirmar');
    await expect(page.locator('#doc-desp-sugestao-modal')).toBeHidden();
    let doc = await idDoDocumento(page, 'Despesa C (ficticia)');
    expect((await vinculos(page, doc.perfil, doc.id)).map((v) => v.tipo_entidade)).toEqual(['CONTA']);

    await page.goto('/lancamentos.html');
    await page.click('#btn-lanc-a-partir-doc');
    await page.locator('#doc-atalho-lista .doc-atalho-item', { hasText: 'Lancamento C (ficticio)' }).click();
    await expect(page.locator('#doc-atalho-valor')).toHaveValue('45');
    await page.selectOption('#doc-atalho-forma-pagamento', 'pix');
    await page.selectOption('#doc-atalho-categoria', { index: 1 });
    await page.click('#doc-atalho-confirmar');
    await expect(page.locator('#doc-atalho-sugestao-modal')).toBeHidden();
    doc = await idDoDocumento(page, 'Lancamento C (ficticio)');
    expect((await vinculos(page, doc.perfil, doc.id)).map((v) => v.tipo_entidade)).toEqual(['CONTA']);
});
