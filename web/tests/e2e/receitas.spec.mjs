// FIN-RECEITAS-1 — receitas PREVISTAS do mes, em tela de celular. Dados FICTICIOS
// (tests/supabase_local.py: semear_receitas_e2e). Grava so em 2029/2030 (Pessoal do usuario A).
// Regra conferida: previsao nao e recebimento — nenhuma acao de receber existe na tela.
import { expect, test } from '@playwright/test';

import { esperarMes } from './despesas.mjs';

import { irPeloMenu, itemDoMenu, trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const ID_PERFIL_B = process.env.CF_ID_PERFIL_B || '103';

test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

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

const normal = (texto) => (texto || '').replace(/\s+/g, ' ').trim();
const textos = async (locator) => (await locator.allTextContents()).map(normal);

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
}

async function abrirMes(page, mes) {
    await page.goto(`/receitas.html?mes=${mes}`);
    await expect(page.locator('#totais')).toBeVisible();
}

function receita(page, nome) {
    return page.locator('#lista-receitas .conta', { has: page.locator('.conta-nome', { hasText: nome }) });
}

async function totais(page) {
    return {
        previsto: normal(await page.locator('#total-previsto').textContent()),
        recebido: normal(await page.locator('#total-recebido').textContent()),
        aReceber: normal(await page.locator('#total-a-receber').textContent()),
    };
}

test('aba Receitas a partir de Contas do mes, no mesmo mes', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/contas.html?mes=2026-11');
    await esperarMes(page, '2026-11');  // FIN-FIDELIDADE-DESPESAS-1: tela original de Despesas
    await irPeloMenu(page, 'receitas');
    await page.waitForURL(/receitas\.html\?mes=2026-11$/);
    await expect(page.locator('#mes-titulo')).toHaveText('Novembro de 2026');
    await expect(itemDoMenu(page, 'receitas')).toHaveAttribute('aria-current', 'page');
});

test('situacoes reais, totais e nenhuma acao de recebimento', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-11');
    expect(await textos(page.locator('#lista-receitas .conta-nome'))).toEqual(['Freelas', 'Salário (A)']);
    await expect(receita(page, 'Salário (A)').locator('.situacao')).toHaveText('Parcial');
    await expect(receita(page, 'Freelas').locator('.situacao')).toHaveText('Prevista');
    await expect(receita(page, 'Freelas').locator('.conta-vencimento')).toHaveText('Prevista para 20/11/2026');
    expect(await totais(page)).toEqual({ previsto: 'R$ 5.800,00', recebido: 'R$ 2.000,00', aReceber: 'R$ 3.800,00' });
    await expect(page.locator('#receitas-nota')).toHaveText(/Previsão não altera saldo/);
    await expect(page.getByRole('button', { name: /receber|recebimento|estornar|conciliar/i })).toHaveCount(0);

    const salario = receita(page, 'Salário (A)');
    await salario.locator('summary').click();
    await expect(salario.locator('.despesa-bloqueio'))
        .toHaveText('Há recebimento registrado nesta competência: a previsão fica preservada.');
    await expect(salario.locator('.despesa-acoes button')).toHaveText(['Editar fonte', 'Inativar fonte']);
});

test('avulsa: cadastrar prevista, editar e excluir sem tocar no recebido', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2029-05');
    await page.click('#nova-receita');
    await expect(page.locator('#receita-fonte')).toHaveValue('nova');
    await expect(page.locator('#receita-competencia')).toHaveValue('2029-05');
    await page.fill('#receita-nome', 'Plantão');
    await page.selectOption('#receita-tipo', 'RENDA_EXTRA');
    await page.fill('#receita-data', '2029-05-15');
    await page.fill('#receita-valor', '1.500,00');
    await page.locator('#receita-painel').getByRole('button', { name: 'Salvar' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Receita prevista cadastrada na competência 05/2029.');
    await expect(receita(page, 'Plantão').locator('.conta-vencimento')).toHaveText('Prevista para 15/05/2029');
    await expect(receita(page, 'Plantão').locator('.situacao')).toHaveText('Prevista');
    expect(await totais(page)).toEqual({ previsto: 'R$ 1.500,00', recebido: 'R$ 0,00', aReceber: 'R$ 1.500,00' });

    await receita(page, 'Plantão').locator('summary').click();
    await expect(receita(page, 'Plantão').locator('.despesa-acoes button'))
        .toHaveText(['Editar', 'Excluir', 'Editar fonte', 'Inativar fonte']);
    await receita(page, 'Plantão').getByRole('button', { name: 'Editar', exact: true }).click();
    await page.fill('#receita-valor', '1.600,00');
    await page.locator('#receita-painel').getByRole('button', { name: 'Salvar' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Receita prevista salva na competência 05/2029.');
    await expect(receita(page, 'Plantão').locator('.conta-valor')).toHaveText(/1\.600,00/);

    await receita(page, 'Plantão').locator('summary').click();
    await receita(page, 'Plantão').getByRole('button', { name: 'Excluir' }).click();
    await expect(receita(page, 'Plantão').locator('.despesa-pergunta')).toHaveText('Excluir esta receita prevista? Nada foi recebido.');
    await receita(page, 'Plantão').getByRole('button', { name: 'Confirmar exclusão' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Receita prevista excluída.');
    await expect(page.locator('#receitas-vazio')).toBeVisible();
});

test('competencia de outubro com recebimento previsto em novembro: total fica em outubro', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2029-10');
    await page.click('#nova-receita');
    await page.fill('#receita-nome', 'Salário outubro');
    await page.selectOption('#receita-tipo', 'SALARIO_FIXO');
    await page.fill('#receita-valor', '5.000,00');
    await expect(page.locator('#receita-competencia')).toHaveValue('2029-10');
    await page.fill('#receita-data', '2029-11-05');
    await page.locator('#receita-painel').getByRole('button', { name: 'Salvar' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Receita prevista cadastrada na competência 10/2029.');
    await expect(receita(page, 'Salário outubro').locator('.conta-vencimento'))
        .toHaveText('Prevista para 05/11/2029 · competência 10/2029');
    expect(await totais(page)).toEqual({ previsto: 'R$ 5.000,00', recebido: 'R$ 0,00', aReceber: 'R$ 5.000,00' });
    await abrirMes(page, '2029-11');
    await expect(receita(page, 'Salário outubro')).toHaveCount(0);  // o orcamento e de outubro

    await abrirMes(page, '2029-10');
    await receita(page, 'Salário outubro').locator('summary').click();
    await receita(page, 'Salário outubro').getByRole('button', { name: 'Editar', exact: true }).click();
    await expect(page.locator('#receita-data')).toHaveValue('2029-11-05');
    await page.fill('#receita-data', '2029-11-06');
    await page.locator('#receita-painel').getByRole('button', { name: 'Salvar' }).click();
    await expect(receita(page, 'Salário outubro').locator('.conta-vencimento'))
        .toHaveText('Prevista para 06/11/2029 · competência 10/2029');
});

test('recorrente: 12 competencias a partir da escolhida', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2029-06');
    await page.click('#nova-receita');
    await page.fill('#receita-nome', 'Aluguel sala recebido');
    await page.selectOption('#receita-tipo', 'ALUGUEL');
    await page.selectOption('#receita-recorrencia', 'mensal');
    await page.fill('#receita-valor', '2000');
    await page.fill('#receita-data', '2029-07-10');  // regra: dia 10 do mes seguinte a cada competencia
    await page.locator('#receita-painel').getByRole('button', { name: 'Salvar' }).click();
    await expect(page.locator('#acao-resultado'))
        .toHaveText('Receita prevista cadastrada: 12 competências a partir de 06/2029.');
    await abrirMes(page, '2030-05');
    await expect(receita(page, 'Aluguel sala recebido').locator('.conta-vencimento'))
        .toHaveText('Prevista para 10/06/2030 · competência 05/2030');
    await abrirMes(page, '2030-06');
    await expect(receita(page, 'Aluguel sala recebido')).toHaveCount(0);
});

test('perfil so de leitura: sem "Nova receita" e sem acoes; escrita direta recebe 403', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-11');
    await trocarPerfil(page, 'Empresa');
    await expect(page.locator('#lista-receitas .conta-nome')).toHaveText(['Consultoria']);
    await expect(page.locator('#nova-receita')).toHaveCount(0);
    await receita(page, 'Consultoria').locator('summary').click();
    await expect(receita(page, 'Consultoria').locator('.despesa-caixa')).toBeEmpty();
    const status = await page.evaluate(async (idB) => {
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
        const empresa = Number(document.getElementById('perfil-financeiro-switcher').dataset.perfilAtivoId);
        const dados = { nome: 'Invasao', tipo: 'OUTROS', valor: '1.00', competencia: '2029-01-01' };
        return [
            await chamar('criar_receita', { p_perfil_id: empresa, p_dados: dados, p_chave: crypto.randomUUID() }),
            await chamar('criar_receita', { p_perfil_id: Number(idB), p_dados: dados, p_chave: crypto.randomUUID() }),
            await chamar('receitas_do_mes', { p_perfil_id: Number(idB), p_mes: '2026-11-01' }),
        ];
    }, ID_PERFIL_B);
    expect(status).toEqual([403, 403, 403]);
});

test('formulario de receita cabe na tela do celular', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2029-07');
    await page.click('#nova-receita');
    const larguras = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    expect(larguras[0]).toBeLessThanOrEqual(larguras[1]);
    for (const campo of ['#receita-fonte', '#receita-nome', '#receita-valor', '#receita-competencia', '#receita-data']) {
        expect((await page.locator(campo).boundingBox()).height).toBeGreaterThanOrEqual(44);
    }
    await page.selectOption('#receita-fonte', { label: 'Freelas' });
    await expect(page.locator('#receita-nome')).toBeHidden();  // fonte existente: so valor, competencia e observacoes
});
