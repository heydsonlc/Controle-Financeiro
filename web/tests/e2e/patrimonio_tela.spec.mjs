// FIN-FIDELIDADE-PATRIMONIO-1 (fase 1) — tela original de Patrimonio do Flask (frontend/templates/patrimonio.html)
// sobre o Supabase, SO CONSULTA. Dados FICTICIOS (tests/supabase_local.py, semear_patrimonio_e2e): caixinhas e uma
// transferencia do "Perfil B" e bens do perfil Empresa. As acoes respondem que continuam no sistema atual, sem gravar.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';
import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to|Ponte CSP/i.test(msg.text())) problemas.push(msg.text());
        if (msg.type() === 'warning' && /Ponte CSP/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (pedido) => { if (/\/api\//.test(new URL(pedido.url()).pathname)) problemas.push(`rede /api/: ${pedido.url()}`); });
    testInfo.problemas = problemas;
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

test('caixinhas e transferencias como no Flask; acoes ficam no sistema atual sem gravar', async ({ page }) => {
    registrarDialogos(page);
    await entrar(page, B);
    await page.goto('/patrimonio.html');
    await expect(page.locator('.patrimonio-aviso-fase')).toContainText('continuam no sistema atual');
    await expect(page.locator('#patrimonio-pessoal')).toBeVisible();
    await expect(page.locator('#caixinhas-lista')).toContainText('Reserva E2E (ficticia)');
    await expect(page.locator('#caixinhas-lista')).toContainText('Viagem E2E (ficticia)');
    await expect(page.locator('#transferencias-lista')).toContainText('Reserva E2E (ficticia)');

    const perfil = await perfilAtivoId(page);
    const antes = (await chamarRpc(page, 'patrimonio_contas_tela', { p_perfil_id: perfil, p_ativo: null })).corpo;
    expect(antes.total).toBe(2);
    const r = await page.evaluate(async () => (await fetch('/api/patrimonio/contas', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nome: 'Nova', saldo_inicial: 1 }),
    })).json());
    expect(r).toEqual({ success: false, error: expect.stringContaining('continua no sistema atual') });
    expect((await chamarRpc(page, 'patrimonio_contas_tela', { p_perfil_id: perfil, p_ativo: null })).corpo).toEqual(antes);
});

test('perfil Empresa mostra os bens, o resumo e a imagem do sistema; outro titular nao ve as caixinhas', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/patrimonio.html');
    await expect(page.locator('#caixinhas-lista')).not.toContainText('Reserva E2E (ficticia)');
    await trocarPerfil(page, 'Empresa');
    await page.goto('/patrimonio.html');
    await expect(page.locator('#patrimonio-empresarial')).toBeVisible();
    await expect(page.locator('#bens-tabela-corpo')).toContainText('Notebook E2E (ficticio)');
    await expect(page.locator('#bens-tabela-corpo')).toContainText('Cadeira E2E (ficticia)');
    await expect(page.locator('#bens-pendencias')).toContainText('Notebook E2E (ficticio)');
    const imagem = page.locator('#bens-tabela-corpo img[src$="Patrimonio_notebook.jpg"]');
    if (await imagem.count()) expect(await imagem.first().evaluate((img) => img.complete && img.naturalWidth > 0)).toBe(true);
});
