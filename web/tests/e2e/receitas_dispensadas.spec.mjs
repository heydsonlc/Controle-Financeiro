// FIN-MVP-SANEAMENTO-FINAL-01 — previsao removida ("Remover previsao" de fonte recorrente: valor 0, "Removido pelo usuario",
// sem recebimento) nao e receita pendente: sai das atrasadas e da lista do mes, e o valor-base da fonte nao volta a aparecer
// naquele mes. Usuario E (perfil proprio), dados FICTICIOS no ano seguinte; limpeza inativa a fonte.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId } from './despesas.mjs';

const E = { email: process.env.CF_EMAIL_E || 'usuario.e@teste.local', senha: process.env.CF_SENHA_E };
const NOME = 'Previsao Dispensada E2E';
const ANO = new Date().getFullYear() + 1;

test.use({ viewport: { width: 1366, height: 900 } });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
        if (/Ponte CSP|Adaptador:/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (r) => { if (new URL(r.url()).pathname.startsWith('/api/')) problemas.push(`rede /api/: ${r.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamadas ao Flask').toEqual([]);
});

async function entrar(page) {
    await page.goto('/index.html');
    await page.fill('#email', E.email);
    await page.fill('#senha', E.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', /\d{2}\/\d{4}/);
    await page.waitForLoadState('networkidle');
}

async function rpcOk(page, funcao, corpo) {
    const r = await chamarRpc(page, funcao, corpo);
    expect(r.status, `${funcao}: ${JSON.stringify(r.corpo)}`).toBe(200);
    return r.corpo;
}

async function abrirReceitas(page, mes) {
    await page.goto('/receitas.html');
    await expect(page.locator('#fontes-resumo .receitas-loading')).toHaveCount(0);
    await page.selectOption('#filtro-ano', String(ANO));
    await page.selectOption('#filtro-mes', mes);
    await expect(page.locator('#mes-lista .receitas-loading')).toHaveCount(0);
}

const daFonte = (page, lista) => page.locator(`${lista} .receita-row`, { has: page.locator('.receita-source strong', { hasText: NOME }) });

test('previsao removida sai das atrasadas e da lista do mes; as outras continuam', async ({ page }) => {
    await entrar(page);
    const perfil = await perfilAtivoId(page);
    const contaE = (await rpcOk(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' })).find((c) => c.nome === 'Conta E (ficticia)');
    const criada = await rpcOk(page, 'criar_receita', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
        nome: NOME, tipo: 'SALARIO_FIXO', valor: '1000.00', competencia: `${ANO}-01-01`, dia_previsto: 5, recorrente: true,
        conta_bancaria_id: contaE.id } });
    const item = criada.item_receita_id;

    await abrirReceitas(page, '04');
    await expect(daFonte(page, '#atrasadas-lista')).toHaveCount(3);  // 01, 02 e 03 pendentes

    const fev = (await rpcOk(page, 'receitas_orcamentos_tela', { p_perfil_id: perfil, p_ano: ANO }))
        .find((o) => o.item_receita_id === item && o.mes_referencia === `${ANO}-02-01`);
    const r = await rpcOk(page, 'excluir_receita', { p_perfil_id: perfil, p_orcamento_id: fev.id, p_versao: fev.versao });
    expect(r.modo).toBe('ZERADA');

    await abrirReceitas(page, '04');
    await expect(daFonte(page, '#atrasadas-lista')).toHaveCount(2);
    await expect(daFonte(page, '#atrasadas-lista')).not.toContainText([`/02/${ANO}`]);
    await abrirReceitas(page, '02');
    await expect(daFonte(page, '#mes-lista')).toHaveCount(0);  // nem a linha de R$ 0,00 nem o valor-base da fonte
    await abrirReceitas(page, '03');
    await expect(daFonte(page, '#mes-lista')).toHaveCount(1);  // a de 03 continua

    // Limpeza: inativa a fonte.
    const fonte = (await rpcOk(page, 'receitas_fontes_tela', { p_perfil_id: perfil })).find((f) => f.id === item);
    await rpcOk(page, 'inativar_fonte_receita', { p_perfil_id: perfil, p_item_id: fonte.id, p_versao: fonte.versao });
});
