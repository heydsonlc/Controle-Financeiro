// FIN-PRE-PRODUCAO-1 (2.4) — Preferencias em Configuracoes (formularios do Flask): as financeiras e operacionais sao do
// perfil em uso (so quem o gere altera), as de interface sao da conta do usuario (valem em todos os perfis). Usuario A:
// titular do Pessoal e LEITOR da Empresa (tests/supabase_local.py). Valores FICTICIOS.
import { expect, test } from '@playwright/test';

import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to|Ponte CSP/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS').toEqual([]);
});

async function entrar(page) {
    await page.goto('/index.html');
    await page.fill('#email', A.email);
    await page.fill('#senha', A.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
}

const secao = (page, nome) => page.locator(`[data-config-section="${nome}"]`);

test('preferencias do perfil e da conta: salvar, recarregar e trocar de perfil', async ({ page }) => {
    await entrar(page);
    await page.goto('/configuracoes.html#preferencias-gerais');
    await expect(page.locator('#nome_usuario')).toHaveValue('Usuário');  // padrao do Flask
    await page.fill('#nome_usuario', 'Usuario A (ficticio)');
    await page.fill('#renda_principal', '4321.50');
    await page.selectOption('#mes_inicio_planejamento', '3');
    await page.fill('#dia_fechamento_mes', '10');
    await page.click('[data-preferences-save="gerais"]');
    await expect(secao(page, 'preferencias-gerais').locator('[data-pref-aviso]')).toHaveText('Preferências salvas.');

    await page.click('[data-config-section-target="aparencia"]');
    await page.check('input[name="tema_sistema"][value="claro"]');
    await page.click('[data-preferences-save="aparencia"]');
    await expect(secao(page, 'aparencia').locator('[data-pref-aviso]')).toHaveText('Preferências salvas.');

    await page.reload();
    await page.click('[data-config-section-target="preferencias-gerais"]');
    await expect(page.locator('#nome_usuario')).toHaveValue('Usuario A (ficticio)');
    await expect(page.locator('#renda_principal')).toHaveValue('4321.5');
    await expect(page.locator('#mes_inicio_planejamento')).toHaveValue('3');
    await expect(page.locator('input[name="tema_sistema"][value="claro"]')).toBeChecked();

    // Empresa: A so le o perfil. As do perfil ficam bloqueadas (e com os valores da Empresa); as da conta seguem.
    await trocarPerfil(page, 'Empresa');
    await page.goto('/configuracoes.html#preferencias-gerais');
    await expect(page.locator('#renda_principal')).toBeDisabled();
    await expect(page.locator('#renda_principal')).toHaveValue('0');
    await expect(page.locator('#nome_usuario')).toBeEnabled();
    await expect(page.locator('#nome_usuario')).toHaveValue('Usuario A (ficticio)');
    await expect(secao(page, 'preferencias-gerais').locator('[data-pref-aviso]')).toContainText('Você só lê este perfil');
    await page.fill('#nome_usuario', 'Usuario A renomeado (ficticio)');
    await page.click('[data-preferences-save="gerais"]');
    await expect(secao(page, 'preferencias-gerais').locator('[data-pref-aviso]')).toHaveText('Preferências salvas.');

    await trocarPerfil(page, 'Pessoal');
    await page.goto('/configuracoes.html#preferencias-gerais');
    await expect(page.locator('#nome_usuario')).toHaveValue('Usuario A renomeado (ficticio)');
    await expect(page.locator('#renda_principal')).toHaveValue('4321.5');
});
