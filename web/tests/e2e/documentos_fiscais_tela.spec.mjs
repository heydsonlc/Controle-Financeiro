// FIN-FIDELIDADE-DOCUMENTOS-1 (fase 1) — tela original de Imposto de Renda do Flask (frontend/templates/imposto_renda.html)
// sobre o Supabase, SO CONSULTA, modo IRPF. Dados FICTICIOS do "Perfil B" (tests/supabase_local.py,
// semear_documentos_fiscais_e2e). As acoes respondem que continuam no sistema atual, sem gravar.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId } from './despesas.mjs';
import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };

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
    page.on('dialog', async (dialogo) => { avisos.push(dialogo.message()); await dialogo.dismiss(); });
    testInfo.problemas = problemas;
    testInfo.avisos = avisos;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamada ao Flask').toEqual([]);
});

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-switcher')).toHaveAttribute('data-perfil-ativo-id', /^\d+$/);
}

test('comprovantes e categorias como no Flask; acoes ficam no sistema atual sem gravar', async ({ page }, testInfo) => {
    await entrar(page, B);
    await page.goto('/documentos-fiscais.html');
    await expect(page.locator('.ir-aviso-fase')).toContainText('continuam no sistema atual');
    await expect(page.locator('#ir-comprovantes-tbody')).toContainText('Clinica E2E (ficticia)');
    await expect(page.locator('#ir-comprovantes-tbody')).toContainText('Escola E2E (ficticia)');
    expect(testInfo.avisos).toEqual([]);  // no modo IRPF o Flask nao pede as saidas sem documento

    const perfil = await perfilAtivoId(page);
    const antes = (await chamarRpc(page, 'ir_comprovantes_tela', { p_perfil_id: perfil, p_filtros: {}, p_id: null })).corpo;
    expect(antes.total).toBe(2);
    const r = await page.evaluate(async (id) => (await fetch(`/api/ir/comprovantes/${id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ valor: 1 }),
    })).json(), antes.data[0].id);
    expect(r).toEqual({ success: false, error: expect.stringContaining('continua no sistema atual') });
    expect((await chamarRpc(page, 'ir_comprovantes_tela', { p_perfil_id: perfil, p_filtros: {}, p_id: null })).corpo).toEqual(antes);
});

test('outro titular nao ve os comprovantes', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/documentos-fiscais.html');
    await expect(page.locator('#ir-lista-subtitulo')).toBeVisible();
    await expect(page.locator('#ir-comprovantes-tbody')).not.toContainText('Clinica E2E (ficticia)');
});

test('perfil Empresa: documentos da empresa, resumo e saidas sem documento, sem avisos', async ({ page }, testInfo) => {
    await entrar(page, A);
    await trocarPerfil(page, 'Empresa');
    await page.goto('/documentos-fiscais.html');
    await expect(page.locator('#ir-comprovantes-tbody')).toContainText('Junta Comercial E2E (ficticia)');
    await expect(page.locator('#ir-comprovantes-tbody')).toContainText('Contrato Social');
    const perfil = await perfilAtivoId(page);
    const resumo = (await chamarRpc(page, 'ir_documentos_empresa_tela', { p_perfil_id: perfil, p_recurso: 'resumo', p_filtros: {}, p_id: null })).corpo;
    expect(resumo.checklist_empresarial[0]).toEqual({ label: 'Contrato Social', status: 'ok' });
    await page.waitForLoadState('networkidle');
    expect(testInfo.avisos).toEqual([]);  // saidas sem documento carregaram (antes: "em migracao")
});

test('abrir arquivo do comprovante (nova aba com o arquivo do Supabase) e relatorio recusado sem navegar', async ({ page, context }, testInfo) => {
    await entrar(page, B);
    await page.goto('/documentos-fiscais.html');
    const linha = page.locator('#ir-comprovantes-tbody tr', { hasText: 'Clinica E2E (ficticia)' });
    await expect(linha).toBeVisible();
    const [aba] = await Promise.all([context.waitForEvent('page'), linha.locator('a[title="Abrir arquivo"]').click()]);
    await expect.poll(() => aba.url()).toMatch(/^blob:/);
    await expect(aba.locator('body')).toContainText('Recibo E2E (ficticio) - conteudo de teste');
    await aba.close();

    const antes = page.url();
    await page.locator('#ir-btn-exportar').click();  // "Exportar" da barra de acoes (Excel no Flask)
    await expect.poll(() => testInfo.avisos.join(' | ')).toContain('continua no sistema atual');
    expect(page.url()).toBe(antes);
});
