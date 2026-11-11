// FIN-RECEITAS-SALDO-01 — (1) atualizar as previsoes ja gravadas pelo valor-base da fonte, com previa e confirmacao,
// preservando a recebida e a alterada manualmente; (2) o saldo do mes negativo em Despesas aparece com o sinal.
// Usuario E (perfil proprio), dados FICTICIOS em 2028 (receitas) e 02/2030 (despesas do P20, sem receitas).
import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, perfilAtivoId } from './despesas.mjs';

const E = { email: process.env.CF_EMAIL_E || 'usuario.e@teste.local', senha: process.env.CF_SENHA_E };
const EVIDENCIAS = process.env.CF_EVIDENCIAS_DIR;
const NOME = 'Subsidio E2E';

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
    // o perfil ativo so e conhecido depois de a moldura carregar (como em recorrencias_inativacao.spec.mjs)
    await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', /\d{2}\/\d{4}/);
    await page.waitForLoadState('networkidle');
}

async function rpcOk(page, funcao, corpo) {
    const r = await chamarRpc(page, funcao, corpo);
    expect(r.status, `${funcao}: ${JSON.stringify(r.corpo)}`).toBe(200);
    return r.corpo;
}

async function abrirReceitas(page, ano, mes) {
    await page.goto('/receitas.html');
    await expect(page.locator('#fontes-resumo .receitas-loading')).toHaveCount(0);
    await page.selectOption('#filtro-ano', String(ano));
    await page.selectOption('#filtro-mes', mes);
    await expect(page.locator('#mes-lista .receitas-loading')).toHaveCount(0);
}

const linha = (page) => page.locator('#mes-lista .receita-row', { has: page.locator('.receita-source strong', { hasText: NOME }) });
const modal = (page) => page.locator('#modal-atualizar-previsoes');
const toast = (page) => page.locator('.receitas-toast');

async function valores(page, perfil, item) {
    const lista = await rpcOk(page, 'receitas_orcamentos_tela', { p_perfil_id: perfil, p_ano: 2028 });
    return Object.fromEntries(lista.filter((o) => o.item_receita_id === item).map((o) => [o.mes_referencia.slice(5, 7), Number(o.valor_esperado)]));
}

async function salvarValorBase(page, valor) {
    await linha(page).locator('[title="Editar"]').click();
    await page.fill('#fonte-valor-base', valor);
    await page.locator('#form-fonte button[type=submit]').click();
    await expect(toast(page)).toContainText('Fonte de receita atualizada com sucesso');
}

test('valor-base novo: previa, competencia inicial e confirmacao; recebida e manual preservadas', async ({ page }) => {
    await entrar(page);
    const perfil = await perfilAtivoId(page);
    const contaE = (await rpcOk(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' })).find((c) => c.nome === 'Conta E (ficticia)');
    const criada = await rpcOk(page, 'criar_receita', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
        nome: NOME, tipo: 'SALARIO_FIXO', valor: '1000.00', competencia: '2028-01-01', dia_previsto: 5, recorrente: true,
        conta_bancaria_id: contaE.id } });
    const item = criada.item_receita_id;
    const lista = await rpcOk(page, 'receitas_orcamentos_tela', { p_perfil_id: perfil, p_ano: 2028 });
    const prev = (mes) => lista.find((o) => o.item_receita_id === item && o.mes_referencia === `2028-${mes}-01`);
    await rpcOk(page, 'receber_receita', { p_perfil_id: perfil, p_orcamento_id: prev('01').id, p_chave: crypto.randomUUID(),
        p_dados: { conta_bancaria_id: contaE.id, data_recebimento: '2028-01-05', valor_recebido: '1000.00', falta: 1000 } });
    const edicao = await rpcOk(page, 'receita_para_edicao', { p_perfil_id: perfil, p_orcamento_id: prev('03').id });
    await rpcOk(page, 'editar_receita', { p_perfil_id: perfil, p_orcamento_id: prev('03').id, p_versao: edicao.versao, p_dados: { valor: '900.00' } });

    await abrirReceitas(page, 2028, '01');
    await salvarValorBase(page, '1.200,00');
    await expect(modal(page)).toBeVisible();
    await expect(page.locator('#atualizar-previsoes-subtitulo')).toHaveText(/Subsidio E2E: valor-base R\$\s1\.200,00\./);
    await expect(page.locator('#atualizar-previsoes-lista tbody tr')).toHaveCount(10);  // 02 e 04 a 12
    await expect(page.locator('#atualizar-previsoes-resumo')).toContainText('10 previsão(ões) pendente(s) passam para');
    await expect(page.locator('#atualizar-previsoes-preservadas li')).toHaveText([
        /^01\/2028 — R\$\s1\.000,00: recebida/, /^03\/2028 — R\$\s900,00: valor alterado manualmente$/]);
    await expect(page.locator('#atualizar-previsoes-confirmar')).toHaveText('Atualizar 10 previsão(ões)');
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/receitas_atualizar_previsoes_1366.png` });

    // So a partir de 06/2028
    await page.fill('#atualizar-previsoes-partir', '2028-06');
    await page.locator('#atualizar-previsoes-partir').dispatchEvent('change');
    await expect(page.locator('#atualizar-previsoes-lista tbody tr')).toHaveCount(7);
    await page.click('#atualizar-previsoes-confirmar');
    await expect(toast(page)).toContainText('7 previsão(ões) atualizada(s) para o valor-base.');
    await expect(modal(page)).toBeHidden();
    expect(await valores(page, perfil, item)).toEqual({ '01': 1000, '02': 1000, '03': 900, '04': 1000, '05': 1000, '06': 1200,
        '07': 1200, '08': 1200, '09': 1200, '10': 1200, '11': 1200, '12': 1200 });
});

test('manter as previsoes nao muda nada; limpeza', async ({ page }) => {
    await entrar(page);
    const perfil = await perfilAtivoId(page);
    const fonte = (await rpcOk(page, 'receitas_fontes_tela', { p_perfil_id: perfil })).find((f) => f.nome === NOME);
    const antes = await valores(page, perfil, fonte.id);
    await abrirReceitas(page, 2028, '02');
    await salvarValorBase(page, '1.200,00');
    await expect(modal(page)).toBeVisible();
    await expect(page.locator('#atualizar-previsoes-lista tbody tr')).toHaveCount(3);  // 02, 04 e 05
    await page.click('#atualizar-previsoes-manter');
    await expect(modal(page)).toBeHidden();
    expect(await valores(page, perfil, fonte.id)).toEqual(antes);

    // Limpeza: estorna o recebimento de 01/2028 (a conta volta ao saldo de partida) e inativa a fonte.
    const realizadas = await rpcOk(page, 'receitas_realizadas_tela', { p_perfil_id: perfil, p_inicio: '2028-01', p_fim: '2028-01' });
    for (const r of realizadas.filter((x) => x.item_receita?.nome === NOME)) {
        await rpcOk(page, 'estornar_recebimento', { p_perfil_id: perfil, p_realizada_id: r.id, p_chave: crypto.randomUUID(),
            p_dados: { motivo: 'Limpeza do E2E', data_estorno: '2028-01-06' } });
    }
    const atual = (await rpcOk(page, 'receitas_fontes_tela', { p_perfil_id: perfil })).find((f) => f.nome === NOME);
    await rpcOk(page, 'inativar_fonte_receita', { p_perfil_id: perfil, p_item_id: atual.id, p_versao: atual.versao });
});

test('Despesas: saldo do mes negativo com o sinal', async ({ page }) => {
    await entrar(page);
    await abrirDespesas(page, '2030-02');
    const saldo = page.locator('#saldo-mes');
    await expect(saldo).toHaveText(/^-R\$\s[\d.]+,\d{2}$/);
    await expect(saldo).toHaveCSS('color', 'rgb(255, 59, 48)');
    await expect(saldo).toHaveAttribute('title', /^Receitas do mês R\$\s[\d.]+,\d{2} − despesas do mês R\$\s[\d.]+,\d{2}$/);
});
