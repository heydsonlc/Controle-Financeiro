// FIN-MIGRACAO-FIDELIDADE-FASE-1 — gestao de perfis em Configuracoes (tela original do Flask) sobre o banco.
// Dados FICTICIOS (tests/supabase_local.py). Grava perfis: so no banco descartavel (CF_E2E_LOCAL). O fluxo
// devolve A ao estado inicial (Pessoal padrao; o perfil criado termina inativo) para os specs seguintes.
import { expect, test } from '@playwright/test';

import { nomesDosPerfis, perfilAtivo, trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const ID_PESSOAL = process.env.CF_ID_PERFIL_PESSOAL || '101';
const NOVO = 'Trabalho (e2e)';
const EDITADO = 'Consultoria (e2e)';

test.describe.configure({ mode: 'serial' });
test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    test.skip(!process.env.CF_E2E_LOCAL, 'grava perfis: so no banco descartavel');
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas || [], 'CSP/erros de JS').toEqual([]);
});

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await page.goto('/configuracoes.html#perfis-financeiros');
    await expect(page.locator('#config-profiles-list .config-profile-card').first()).toBeVisible();
}

const cartao = (page, nome) => page.locator('#config-profiles-list .config-profile-card')
    .filter({ has: page.locator('strong', { hasText: new RegExp(`^${nome.replace(/[()]/g, '\\$&')}$`) }) });
const selos = (page, nome) => cartao(page, nome).locator('.config-profile-badge');
const alerta = (page) => page.locator('#config-profile-alert');

async function salvar(page, mensagem = 'Configurações do perfil salvas.') {
    await page.click('#config-profile-save');
    await expect(alerta(page)).toHaveText(mensagem);
}

test('Configuracoes lista os perfis do usuario com estado, padrao, uso e permissao', async ({ page }) => {
    await entrar(page, A);
    await expect(page.locator('.app-nav-link.active')).toHaveText(/Configurações e Preferências/);
    await expect(page.locator('#config-profiles-list .config-profile-card strong'))
        .toHaveText(['Empresa', 'Pessoal', 'Perfil inativo (A)']);
    await expect(selos(page, 'Pessoal')).toHaveText(['Ativo', 'Padrão', 'Perfil em uso']);
    await expect(selos(page, 'Empresa')).toHaveText(['Disponível', 'Somente leitura']);
    await expect(selos(page, 'Perfil inativo (A)')).toHaveText(['Inativo']);
    await expect(page.locator('#config-profile-nome')).toHaveValue('Pessoal');  // perfil em uso selecionado

    await cartao(page, 'Empresa').click();
    await expect(page.locator('#config-profile-nome')).toHaveValue('Empresa');
    await expect(page.locator('#config-profile-nome')).toBeDisabled();
    await expect(page.locator('#config-profile-save')).toBeDisabled();
    await expect(alerta(page)).toContainText('somente de leitura');

    // Secoes ainda nao migradas: titulo original e aviso.
    await page.click('[data-config-section-target="backup"]');
    await expect(page.locator('#config-section-backup')).toContainText('Em migração');
    await expect(page.locator('#config-help-title')).toHaveText('Backup');
    await page.click('#config-export-settings');
    await expect(page.locator('#config-aviso-geral')).toContainText('Exportar configurações: em migração');
});

test('criar, editar, tornar padrao, usar, inativar e reativar; isolamento dos dados', async ({ page }) => {
    await entrar(page, A);
    // Criar
    await page.click('#config-profile-new');
    await expect(alerta(page)).toHaveText('Novo perfil em edição. Preencha os dados e salve para criar.');
    await page.fill('#config-profile-nome', NOVO);
    await page.selectOption('#config-profile-tipo', 'EMPRESA');
    await page.fill('#config-profile-documento', '12.345.678/0001-90');
    await page.fill('#config-profile-cor', '#0f766e');
    await salvar(page);
    await expect(selos(page, NOVO)).toHaveText(['Disponível']);
    await expect(cartao(page, NOVO).locator('.config-profile-avatar')).toHaveText('T(');
    await expect(cartao(page, NOVO).locator('small')).toHaveText('Empresa · 12.345.678/0001-90');
    await page.click('#perfil-financeiro-trigger');
    await expect(nomesDosPerfis(page)).toHaveText(['Pessoal', 'Empresa', NOVO]);
    await page.keyboard.press('Escape');

    // Nome duplicado e nome reservado: mensagens do banco, nada muda.
    await page.fill('#config-profile-nome', 'Empresa');
    await salvar(page, 'Ja existe perfil financeiro com este nome');
    await cartao(page, 'Pessoal').click();
    await page.fill('#config-profile-nome', 'Minhas contas');
    await salvar(page, 'O perfil Pessoal nao pode ser renomeado: ele guarda os registros sem perfil');
    await expect(page.locator('#config-profile-nome')).toHaveValue('Pessoal');

    // Editar nome, tipo, apelido e tornar padrao
    await cartao(page, NOVO).click();
    await page.fill('#config-profile-nome', EDITADO);
    await page.selectOption('#config-profile-tipo', 'OUTRO');
    await page.fill('#config-profile-avatar', 'ce');
    await page.check('#config-profile-padrao');
    await salvar(page);
    await expect(selos(page, EDITADO)).toHaveText(['Disponível', 'Padrão']);
    await expect(selos(page, 'Pessoal')).toHaveText(['Ativo', 'Perfil em uso']);
    await expect(cartao(page, EDITADO).locator('.config-profile-avatar')).toHaveText('CE');

    // Usar este perfil: o topo muda e a escolha vale nas outras paginas; o perfil novo nao ve dados de outro.
    await page.click('#config-profile-use');
    await expect(alerta(page)).toHaveText(`Perfil em uso alterado para ${EDITADO}.`);
    await expect(perfilAtivo(page)).toHaveText(EDITADO);
    await expect(page.locator('#perfil-financeiro-type')).toHaveText('Perfil financeiro');
    await page.goto('/contas.html?mes=2026-11');
    await expect(perfilAtivo(page)).toHaveText(EDITADO);
    await expect(page.locator('#despesas-lista .empty-state')).toBeVisible();  // tela original de Despesas
    for (const nome of ['Aluguel 11/2026', 'Internet 11/2026', 'Contador 11/2026']) {
        await expect(page.getByText(nome)).toHaveCount(0);
    }
    await page.goto('/categorias.html');
    await expect(page.locator('#contas-vazio')).toBeVisible();  // nem a "Carteira legado sem perfil" do Pessoal

    // Nao inativa o perfil em uso
    await page.goto('/configuracoes.html');
    await cartao(page, EDITADO).click();
    await page.uncheck('#config-profile-ativo');
    await salvar(page, 'Selecione outro perfil antes de inativar o perfil ativo');

    // Volta ao Pessoal, devolve o padrao e inativa o perfil criado
    await trocarPerfil(page, 'Pessoal');
    await cartao(page, 'Pessoal').click();
    await page.check('#config-profile-padrao');
    await salvar(page);
    await expect(selos(page, 'Pessoal')).toHaveText(['Ativo', 'Padrão', 'Perfil em uso']);
    await cartao(page, EDITADO).click();
    await page.uncheck('#config-profile-ativo');
    await salvar(page);
    await expect(selos(page, EDITADO)).toHaveText(['Inativo']);
    await page.click('#perfil-financeiro-trigger');
    await expect(nomesDosPerfis(page)).toHaveText(['Pessoal', 'Empresa']);
    await page.keyboard.press('Escape');

    // Reativar e inativar de novo (estado final igual ao inicial, com o perfil criado inativo)
    await cartao(page, EDITADO).click();
    await page.check('#config-profile-ativo');
    await salvar(page);
    await expect(selos(page, EDITADO)).toHaveText(['Disponível']);
    await page.uncheck('#config-profile-ativo');
    await salvar(page);
    await page.reload();
    await expect(page.locator('#config-profiles-list .config-profile-card strong'))
        .toHaveText(['Empresa', 'Pessoal', EDITADO, 'Perfil inativo (A)']);
    await expect(selos(page, 'Pessoal')).toHaveText(['Ativo', 'Padrão', 'Perfil em uso']);
});

test('outro usuario nao ve nem altera perfis de A, nem o padrao de A', async ({ page }) => {
    await entrar(page, B);
    await expect(page.locator('#config-profiles-list .config-profile-card strong')).toHaveText(['Perfil B']);
    await page.click('#config-profile-new');
    await page.fill('#config-profile-nome', 'B quer ser padrao');
    await page.check('#config-profile-padrao');
    await salvar(page, 'O perfil padrao atual e gerido por outro titular');
    await expect(page.locator('#config-profiles-list .config-profile-card strong')).toHaveText(['Perfil B']);  // nada criado

    const status = await page.evaluate(async (idPessoal) => {
        const token = JSON.parse(localStorage.getItem('cf-financeiro-auth')).access_token;
        const chamar = (funcao, corpo) => fetch(`${window.CF_CONFIG.supabaseUrl}/rest/v1/rpc/${funcao}`, {
            method: 'POST',
            headers: {
                apikey: window.CF_CONFIG.supabasePublishableKey,
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
                'Content-Profile': 'financeiro',
            },
            body: JSON.stringify(corpo),
        }).then((r) => r.status);
        const id = Number(idPessoal);
        return [
            await chamar('atualizar_perfil', { p_perfil_id: id, p_dados: { nome: 'Tomado' } }),
            await chamar('inativar_perfil', { p_perfil_id: id }),
            await chamar('definir_perfil_padrao', { p_perfil_id: id }),
        ];
    }, ID_PESSOAL);
    expect(status).toEqual([403, 403, 403]);
});
