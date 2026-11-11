// P24 (FIN-CONSORCIOS-INTEGRACAO-01) — consorcio em moeda ja em andamento: (C) cadastro pelo modal original de
// Recorrencias com o contrato inteiro (10 parcelas, inicio 4 meses atras) e as 4 primeiras pagas antes do cadastro (pagas
// no historico, sem debito bancario; a do mes corrente e a 5/10; premio integral = 570 x 10); (B) edicao de parcela
// em Despesas ("esta" e "esta e as futuras"); (A) "Confirmar/realizar" da contemplacao em Receitas, com o credito.
// Usuario E (perfil proprio), dados FICTICIOS; no fim, o recebimento e estornado e o contrato excluido.
import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const E = { email: process.env.CF_EMAIL_E || 'usuario.e@teste.local', senha: process.env.CF_SENHA_E };
const EVIDENCIAS = process.env.CF_EVIDENCIAS_DIR;
const NOME = 'Consorcio P24 E2E';

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

// Mes corrente (Brasilia) deslocado, como YYYY-MM.
function mes(deslocamento) {
    const [a, m] = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date()).split('-').map(Number);
    const d = new Date(Date.UTC(a, m - 1 + deslocamento, 1));
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}
const mmaa = (ym) => `${ym.slice(5, 7)}/${ym.slice(0, 4)}`;

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

async function parcelas(page, perfil) {
    const meses = Array.from({ length: 10 }, (_, i) => mes(i - 4));
    const todas = [];
    for (const m of meses) {
        const doMes = await rpcOk(page, 'contas_do_mes', { p_perfil_id: perfil, p_mes: `${m}-01` });
        todas.push(...doMes.filter((c) => c.nome.startsWith(`${NOME} - Parcela`)));
    }
    return todas.sort((a, b) => String(a.data_vencimento).localeCompare(String(b.data_vencimento)));
}

const saldos = async (page, perfil) => (await rpcOk(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' }))
    .map((c) => [c.id, Number(c.saldo_atual)]);

test('C: cadastro de consorcio em andamento com 4 parcelas pagas antes do cadastro', async ({ page }) => {
    await entrar(page);
    const perfil = await perfilAtivoId(page);
    const antes = await saldos(page, perfil);
    await page.goto('/recorrencias.html');
    await expect(page.locator('#recorrencias-total')).toHaveText(/cadastros? no total/);
    await page.click('#btn-nova-recorrencia');
    await page.selectOption('#tipo-cadastro', 'consorcio');
    await expect(page.locator('#parcelas-pagas-anteriores')).toBeVisible();
    await page.fill('#nome', NOME);
    await page.fill('#valor', '500');
    const categoria = await page.locator('#categoria-id option:not([value=""])').first().getAttribute('value');
    await page.selectOption('#categoria-id', categoria);
    await page.fill('#data-vencimento', `${mes(-4)}-05`);
    await page.fill('#numero-parcelas', '10');
    await page.selectOption('#tipo-reajuste', 'fixo');
    await page.fill('#valor-reajuste', '10');
    await page.fill('#mes-contemplacao', mes(3));
    await page.fill('#parcelas-pagas-anteriores', '4');
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/p24_cadastro_retroativo_1366.png` });
    await page.click('button[type="submit"][form="form-recorrencia"]');
    await expect(page.locator('#recorrencias-lista .recorrencias-row', { hasText: NOME })).toBeVisible();

    const contrato = (await rpcOk(page, 'consorcios_tela', { p_perfil_id: perfil, p_id: null })).find((c) => c.nome === NOME);
    expect([contrato.numero_parcelas, contrato.mes_inicio, Number(contrato.valor_premio)]).toEqual([10, `${mes(-4)}-01`, 5700]);
    const p = await parcelas(page, perfil);
    expect(p.map((x) => x.nome)).toEqual(Array.from({ length: 10 }, (_, i) => `${NOME} - Parcela ${i + 1}/10`));
    expect(p.map((x) => x.status_pagamento)).toEqual([...Array(4).fill('Pago'), ...Array(6).fill('Pendente')]);
    expect(String(p[4].data_vencimento).slice(0, 7)).toBe(mes(0));  // a do mes corrente e a 5/10
    expect(await saldos(page, perfil)).toEqual(antes);                // nenhum debito ficticio
});

test('B: editar esta parcela e esta e as futuras', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page);
    const perfil = await perfilAtivoId(page);
    await abrirDespesas(page, mes(0));
    await despesa(page, `${NOME} - Parcela 5/10`).locator('[title="Editar"]').click();
    await expect(page.locator('#modal-tipo-edicao')).toBeVisible();
    await page.locator('#modal-tipo-edicao [data-on-click="confirmarTipoEdicao(\'unica\')"]').click();
    await expect(page.locator('#modal-despesa')).toBeVisible();
    await page.fill('#valor', '555.55');
    await page.click('#form-despesa button[type="submit"]');
    await expect.poll(() => dialogos.join('|')).toMatch(/Parcela atualizada com sucesso|sucesso/);

    await abrirDespesas(page, mes(1));
    await despesa(page, `${NOME} - Parcela 6/10`).locator('[title="Editar"]').click();
    await page.locator('#modal-tipo-edicao [data-on-click="confirmarTipoEdicao(\'futuras\')"]').click();
    await expect(page.locator('#modal-despesa')).toBeVisible();
    await page.fill('#valor', '600');
    await page.click('#form-despesa button[type="submit"]');
    await expect.poll(() => dialogos.at(-1) || '').toMatch(/parcela\(s\) futura\(s\) atualizadas|sucesso/);

    const p = await parcelas(page, perfil);
    expect(p.map((x) => Number(x.valor))).toEqual([500, 510, 520, 530, 555.55, 600, 600, 600, 600, 600]);
    expect(p.slice(0, 4).every((x) => x.status_pagamento === 'Pago')).toBe(true);
});

test('A: Confirmar/realizar a contemplacao em Receitas; limpeza', async ({ page }) => {
    await entrar(page);
    const perfil = await perfilAtivoId(page);
    const contaE = (await rpcOk(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' })).find((c) => c.nome === 'Conta E (ficticia)');
    const saldoAntes = Number(contaE.saldo_atual);
    const alvo = mes(3);
    await page.goto('/receitas.html');
    await expect(page.locator('#fontes-resumo .receitas-loading')).toHaveCount(0);
    await page.selectOption('#filtro-ano', alvo.slice(0, 4));
    await page.selectOption('#filtro-mes', alvo.slice(5, 7));
    await expect(page.locator('#mes-lista .receitas-loading')).toHaveCount(0);
    const linha = page.locator('#mes-lista .receita-row', { hasText: `${NOME} - contemplação` });
    await expect(linha).toHaveCount(1);
    await expect(linha).toContainText('Prevista');
    await expect(linha).toContainText(/R\$\s5\.700,00/);
    await linha.locator('[title="Confirmar/realizar"]').click();
    await expect(page.locator('#modal-consolidar-conta')).toBeVisible();
    await page.selectOption('#consolidar-conta-bancaria', String(contaE.id));
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/p24_contemplacao_1366.png` });
    await page.locator('#form-consolidar-conta button[type="submit"]').click();
    await expect(page.locator('.receitas-toast')).toContainText('Contemplação do consórcio recebida com sucesso.');
    await expect(page.locator('#mes-lista .receita-row', { hasText: `${NOME} - contemplação` })).toContainText(/Realizada|Recebida/);
    const depois = (await rpcOk(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' })).find((c) => c.id === contaE.id);
    expect(Number(depois.saldo_atual)).toBeCloseTo(saldoAntes + 5700, 2);

    // Limpeza: estorna o recebimento (a conta volta ao saldo) e exclui o contrato (as historicas pagas ficam no historico).
    const realizadas = await rpcOk(page, 'receitas_realizadas_tela', { p_perfil_id: perfil, p_inicio: alvo, p_fim: alvo });
    const rec = realizadas.find((r) => String(r.descricao || '').includes(NOME));
    await rpcOk(page, 'estornar_recebimento', { p_perfil_id: perfil, p_realizada_id: rec.id, p_chave: crypto.randomUUID(),
        p_dados: { motivo: 'Limpeza do E2E', data_estorno: `${alvo}-10` } });
    const contrato = (await rpcOk(page, 'consorcios_tela', { p_perfil_id: perfil, p_id: null })).find((c) => c.nome === NOME);
    await rpcOk(page, 'excluir_consorcio', { p_perfil_id: perfil, p_id: contrato.id });
    expect(mmaa(alvo)).toMatch(/^\d{2}\/\d{4}$/);
});
