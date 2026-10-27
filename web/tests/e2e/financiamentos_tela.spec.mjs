// FIN-FIDELIDADE-CONTRATOS-1 (fase 1) — tela original de Financiamentos do Flask (frontend/templates/financiamentos.html)
// sobre o Supabase, SO CONSULTA. Financiamento FICTICIO do "Perfil B" (tests/supabase_local.py, semear_financiamento_e2e):
// 3 parcelas, 1 paga. As acoes fora da fase (documentos, conferencias da Caixa) respondem que continuam no sistema atual, sem gravar.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const NOME = 'Financiamento E2E (ficticio)';

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

test('lista, detalhe e parcelas como no Flask; acoes ficam no sistema atual sem gravar', async ({ page }) => {
    registrarDialogos(page);
    await entrar(page, B);
    await page.goto('/financiamentos.html');
    await expect(page.locator('.fin-aviso-fase')).toContainText('continuam no sistema atual');
    const linha = page.locator('#financiamentos-lista .fin-contract-row', { hasText: NOME });
    await expect(linha).toBeVisible();
    await expect(linha).toContainText('SAC');

    await linha.locator('[title="Visualizar"]').click();
    await expect(page.locator('#detalhe-parcelas-pagas')).toHaveText(/1\s*\/\s*3/);
    await expect(page.locator('#detalhe-parcelas-body tr')).toHaveCount(3);

    // Acao fora da fase 1: mensagem clara e nada gravado.
    const perfil = await perfilAtivoId(page);
    const antes = (await chamarRpc(page, 'financiamentos_tela', { p_perfil_id: perfil, p_ativo: null })).corpo;
    const r = await page.evaluate(async () => (await fetch('/api/financiamentos/1/conferencias-caixa', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tipo: 'mensal' }),
    })).json());
    expect(r).toEqual({ success: false, error: expect.stringContaining('continua no sistema atual') });
    expect((await chamarRpc(page, 'financiamentos_tela', { p_perfil_id: perfil, p_ativo: null })).corpo).toEqual(antes);
});

test('outro titular nao ve o financiamento', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/financiamentos.html');
    await expect(page.locator('#financiamentos-lista')).not.toContainText('Carregando');
    await expect(page.locator('#financiamentos-lista')).not.toContainText(NOME);
});
