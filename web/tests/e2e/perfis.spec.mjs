// PERFIS-1 — perfis financeiros autorizados, troca de perfil e acesso cruzado.
// Dados FICTICIOS semeados por tests/supabase_local.py (ids fixos, sobrescreviveis por ambiente).
import { expect, test } from '@playwright/test';

import { nomesDosPerfis, perfilAtivo, trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const ID_PERFIL_B = process.env.CF_ID_PERFIL_B || '103';
const CONTAS = {
    PESSOAL: ['Carteira legado sem perfil', 'Conta Pessoal (A)'],
    EMPRESA: ['Conta Empresa (A)'],
    PERFIL_B: ['Conta Perfil B'],
};
const TODAS = [...CONTAS.PESSOAL, ...CONTAS.EMPRESA, ...CONTAS.PERFIL_B, 'Conta do perfil inativo'];

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS').toEqual([]);
});

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await page.goto('/categorias.html');
}

const contas = (page) => page.locator('#contas-corpo tr td:nth-child(2)');
const opcoes = nomesDosPerfis;

test('usuario A ve so os proprios perfis ativos, com o padrao selecionado', async ({ page }) => {
    await entrar(page, A);
    await expect(opcoes(page)).toHaveText(['Pessoal', 'Empresa']);
    await expect(perfilAtivo(page)).toHaveText('Pessoal');
    // Regra do Flask: o Pessoal inclui registros legados sem perfil.
    await expect(contas(page)).toHaveText(CONTAS.PESSOAL);
});

test('usuario A alterna entre os proprios perfis e a escolha persiste ao recarregar e em outra aba', async ({ page }) => {
    await entrar(page, A);
    await expect(contas(page)).toHaveText(CONTAS.PESSOAL);
    await trocarPerfil(page, 'Empresa');
    await expect(contas(page)).toHaveText(CONTAS.EMPRESA);
    await page.reload();
    await expect(perfilAtivo(page)).toHaveText('Empresa');
    await expect(contas(page)).toHaveText(CONTAS.EMPRESA);
    // FIN-MIGRACAO-FIDELIDADE-FASE-1: como a sessao do Flask, vale tambem numa nova aba e nas outras paginas.
    const outraAba = await page.context().newPage();
    await outraAba.goto('/contas.html?mes=2026-11');
    await expect(perfilAtivo(outraAba)).toHaveText('Empresa');
    await expect(outraAba.locator('#lista-despesas .conta-nome')).toHaveText(['Contador 11/2026']);
    await outraAba.close();
});

test('usuario B nao ve perfis nem contas de A', async ({ page }) => {
    await entrar(page, B);
    await expect(opcoes(page)).toHaveText(['Perfil B']);
    await expect(contas(page)).toHaveText(CONTAS.PERFIL_B);
    for (const nome of TODAS.filter((n) => !CONTAS.PERFIL_B.includes(n))) {
        await expect(page.getByText(nome, { exact: true })).toHaveCount(0);
    }
});

test('perfil alterado manualmente no navegador nao da acesso ao perfil de outro usuario', async ({ page }) => {
    await entrar(page, A);
    await expect(contas(page)).toHaveText(CONTAS.PESSOAL);

    // 1) Adultera a escolha salva: a tela volta para um perfil autorizado.
    const chaveAdulterada = await page.evaluate((idB) => {
        const usuarioId = JSON.parse(localStorage.getItem('cf-financeiro-auth')).user.id;
        const chave = `cf-perfil-ativo:${usuarioId}`;
        localStorage.setItem(chave, idB);
        return chave;
    }, ID_PERFIL_B);
    expect(await page.evaluate((k) => localStorage.getItem(k), chaveAdulterada)).toBe(ID_PERFIL_B);
    await page.reload();
    await expect(perfilAtivo(page)).toHaveText('Pessoal');
    await expect(page.getByText('Conta Perfil B', { exact: true })).toHaveCount(0);

    // 2) Chamada direta a funcao com o id do perfil de B: o banco recusa.
    const resposta = await page.evaluate(async (idB) => {
        const chaveSessao = Object.keys(localStorage).find((k) => k === 'cf-financeiro-auth');
        const token = JSON.parse(localStorage.getItem(chaveSessao)).access_token;
        const r = await fetch(`${window.CF_CONFIG.supabaseUrl}/rest/v1/rpc/contas_bancarias_do_perfil`, {
            method: 'POST',
            headers: {
                apikey: window.CF_CONFIG.supabasePublishableKey,
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
                'Content-Profile': 'financeiro',
            },
            body: JSON.stringify({ p_perfil_id: Number(idB) }),
        });
        return { status: r.status, corpo: await r.text() };
    }, ID_PERFIL_B);
    expect(resposta.status).toBe(403);
    expect(resposta.corpo).not.toContain('Conta Perfil B');
});

test('perfil inativo nao aparece nem tem contas exibidas', async ({ page }) => {
    await entrar(page, A);
    await expect(opcoes(page)).not.toContainText(['Perfil inativo (A)']);
    await expect(page.getByText('Conta do perfil inativo', { exact: true })).toHaveCount(0);
});
