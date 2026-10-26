// FIN-FIDELIDADE-CONSOLIDACAO-1 — Dashboard Financeiro original do Flask (frontend/templates/index.html) sobre o Supabase,
// so leitura (dashboard_resumo_tela). KPIs, grafico (Chart.js do proprio Flask) e acoes rapidas apontando para as
// paginas deste aplicativo. Dados FICTICIOS do cluster local.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId } from './despesas.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };

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

test('KPIs do resumo, grafico e acoes rapidas para as paginas daqui', async ({ page }) => {
    await page.goto('/index.html');
    await page.fill('#email', A.email);
    await page.fill('#senha', A.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await page.goto('/dashboard.html');

    const perfil = await perfilAtivoId(page);
    const mes = await page.locator('#dashboard-periodo').inputValue();
    const resumo = (await chamarRpc(page, 'dashboard_resumo_tela', { p_perfil_id: perfil, p_mes_referencia: mes })).corpo;
    const saldo = resumo.kpis.saldo_consolidado.valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    await expect(page.locator('#kpi-saldo')).toContainText(saldo);
    await expect(page.locator('#kpi-recorrencias')).toContainText(String(resumo.kpis.recorrencias_ativas.quantidade));
    // D2: previsto, recebido e diferenca da execucao, sem somar a previsao recebida de novo.
    const real = (v) => v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const fluxo = resumo.fluxo_caixa.resumo;
    await expect(page.locator('#flow-receitas')).toContainText(real(fluxo.receitas_previstas));
    await expect(page.locator('#flow-receitas-recebidas')).toContainText(real(fluxo.receitas_recebidas));
    await expect(page.locator('#flow-receitas-diferenca')).toContainText(real(Math.abs(fluxo.diferenca_receitas)));
    expect(await page.locator('#fluxo-caixa-chart').evaluate((c) => c.width > 0)).toBe(true);
    expect(await page.evaluate(() => typeof window.Chart)).toBe('function');

    const links = await page.locator('#acoes-rapidas a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
    expect(links.length).toBe(5);
    for (const href of links) expect(href).toMatch(/^[a-z-]+\.html$/);
    // Como no Flask, em 1366px as primeiras acoes rolam por baixo dos controles: clica-se numa visivel.
    await page.locator('#acoes-rapidas a', { hasText: 'Revisar recorr' }).click();
    await page.waitForURL('**/recorrencias.html');
});
