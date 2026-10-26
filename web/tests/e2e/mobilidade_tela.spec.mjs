// FIN-FIDELIDADE-PATRIMONIO-1 (Mobilidade, fase 1) — tela original de Mobilidade do Flask (frontend/templates/veiculos.html)
// sobre o Supabase, SO CONSULTA. Dados FICTICIOS do "Perfil B" (tests/supabase_local.py, semear_mobilidade_e2e): veiculo
// com projecoes, regra de manutencao, assinatura e caminho de transporte por app. Acoes respondem sem gravar.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const VEICULO = 'Carro E2E (ficticio)';

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

test('veiculo, assinatura e transporte por app como no Flask; acoes ficam no sistema atual sem gravar', async ({ page }) => {
    registrarDialogos(page);
    await entrar(page, B);
    await page.goto('/mobilidade.html');
    await expect(page.locator('.mobilidade-aviso-fase')).toContainText('continuam no sistema atual');
    await expect(page.locator('#comp-cards')).toContainText(VEICULO);  // aba inicial: comparacao
    await page.locator('#tab-configuracao').click();
    await expect(page.locator('#conf-veiculos-lista')).toContainText(VEICULO);
    await expect(page.locator('#conf-assinaturas-lista')).toContainText('Assinatura E2E (ficticia)');
    await expect(page.locator('#conf-apps-lista')).toContainText('App E2E (ficticio)');

    const perfil = await perfilAtivoId(page);
    const antes = (await chamarRpc(page, 'veiculos_tela', { p_perfil_id: perfil, p_id: null })).corpo;
    expect(antes.map((v) => v.nome)).toEqual([VEICULO]);
    const projecoes = (await chamarRpc(page, 'projecoes_mobilidade_tela', {
        p_perfil_id: perfil, p_origem_tipo: 'VEICULO', p_origem_id: antes[0].id, p_meses: 12,
    })).corpo;
    expect(projecoes.map((p) => p.tipo_evento)).toEqual(['COMBUSTIVEL', 'COMBUSTIVEL', 'IPVA']);

    const r = await page.evaluate(async (id) => (await fetch(`/api/veiculos/${id}/projecoes/gerar`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ meses_futuros: 12 }),
    })).json(), antes[0].id);
    expect(r).toEqual({ success: false, error: expect.stringContaining('continua no sistema atual') });
    expect((await chamarRpc(page, 'projecoes_mobilidade_tela', {
        p_perfil_id: perfil, p_origem_tipo: 'VEICULO', p_origem_id: antes[0].id, p_meses: 12,
    })).corpo).toEqual(projecoes);
});

test('outro titular nao ve o veiculo', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/mobilidade.html');
    await expect(page.locator('.mobilidade-aviso-fase')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.locator('#tab-configuracao').click();
    await expect(page.locator('#conf-veiculos-lista')).not.toContainText('Carregando');
    await expect(page.locator('#conf-veiculos-lista')).not.toContainText(VEICULO);
});
