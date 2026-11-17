// FIN-CATEGORIAS-REORGANIZACAO-01 — Consumo e Aportes nas telas (so apresentacao): linha compacta sob o total de saidas do
// Dashboard e sob o total da Lista de Despesas mobile. A natureza da categoria e gravada pelo gancho de teste
// /__e2e__/admin (run_e2e.py), direto no banco descartavel, e desfeita no fim. Conferido: o total, o saldo projetado e os
// demais numeros nao mudam; consumo + aportes (+ outras saidas) = total exibido. Dados FICTICIOS.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId } from './despesas.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const F = { email: process.env.CF_EMAIL_F || 'usuario.f@teste.local', senha: process.env.CF_SENHA_F };
const PERFIL_F = 150;
const MES_F = '2031-04';
const EVIDENCIAS = process.env.CF_NAT_EVIDENCIAS || '';  // capturas para a homologacao (opcional; dados ficticios)

async function evidencia(alvo, nome) {
    if (!EVIDENCIAS) return;
    mkdirSync(EVIDENCIAS, { recursive: true });
    await alvo.screenshot({ path: path.join(EVIDENCIAS, `${nome}.png`) });
}

test.describe.configure({ mode: 'serial' });

const marcadas = [];  // categorias com natureza gravada por este arquivo (desfeitas no fim, mesmo com falha)

async function admin(request, pedido) {
    const r = await request.post('/__e2e__/admin', { data: pedido });
    expect(r.status(), JSON.stringify(pedido)).toBe(200);
    return r.json();
}

async function marcar(request, categoriaId, natureza) {
    if (natureza) marcadas.push(categoriaId);
    await admin(request, { acao: 'natureza', categoria_id: categoriaId, natureza });
}

test.afterAll(async ({ request }) => {
    for (const id of marcadas) await admin(request, { acao: 'natureza', categoria_id: id, natureza: null });
});

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to|Ponte CSP/i.test(msg.text())) problemas.push(msg.text());
        // "Failed to fetch" = leitura interrompida pela troca de pagina do proprio teste (nao e indisponibilidade).
        if (msg.type() === 'warning' && /Ponte CSP|indispon/i.test(msg.text()) && !/Failed to fetch/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP, erros de JS ou leitura de natureza indisponivel').toEqual([]);
});

// "R$ 1.234,56" -> centavos
const centavos = (texto) => Math.round(Number(texto.replace(/[^\d,-]/g, '').replace(',', '.')) * 100);
function partes(bruto) {
    const texto = bruto.replace(/ /g, ' ');
    const ler = (rotulo) => {
        const m = texto.match(new RegExp(`${rotulo}\\s+(-?R\\$\\s*[\\d.,]+)`));
        return m ? centavos(m[1]) : 0;
    };
    return { consumo: ler('Consumo'), aportes: ler('Aportes'), outras: ler('Outras saídas') };
}

async function entrar(page, conta, destino) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL(destino);
}

async function abrirDashboard(page, mes) {
    await page.goto('/dashboard.html');
    await page.locator('#dashboard-periodo').fill(mes);
    await page.locator('#dashboard-periodo').dispatchEvent('change');
    await expect(page.locator('#flow-saidas-naturezas')).toHaveAttribute('data-mes', mes);
    await expect(page.locator('#flow-saidas-naturezas')).toBeVisible();
}

const numerosDoDashboard = (page) => page.evaluate(() => Object.fromEntries(
    ['kpi-saldo', 'kpi-fluxo', 'flow-receitas', 'flow-despesas', 'flow-saldo', 'flow-receitas-recebidas', 'flow-receitas-diferenca']
        .map((id) => [id, document.getElementById(id).textContent.trim()])));

test('Dashboard: consumo e aportes repartem o total de saidas, sem mudar total, saldo nem fluxo', async ({ page, request }) => {
    test.setTimeout(90 * 1000);
    await page.setViewportSize({ width: 1366, height: 900 });
    await entrar(page, A, '**/contas.html');
    await page.goto('/dashboard.html');
    const perfil = await perfilAtivoId(page);
    const exemplo = await admin(request, { acao: 'natureza_exemplo', perfil });

    // Antes: nenhuma categoria de aporte -> tudo e consumo (ou outras saidas), e a soma e o total exibido.
    await abrirDashboard(page, exemplo.mes);
    await expect(page.locator('.flow-summary')).toContainText('Total de saídas');
    const antes = await numerosDoDashboard(page);
    const total = centavos(antes['flow-despesas']);
    expect(total).toBeGreaterThan(0);
    const p0 = partes(await page.locator('#flow-saidas-naturezas').innerText());
    expect(p0.aportes).toBe(0);
    expect(p0.consumo + p0.outras).toBe(total);
    const altura = (await page.locator('.dashboard-flow-panel').boundingBox()).height;

    // Depois: a categoria vira aporte. So a reparticao muda.
    await marcar(request, exemplo.categoria_id, 'APORTE');
    await abrirDashboard(page, exemplo.mes);
    await expect(page.locator('#flow-saidas-naturezas')).not.toContainText('Aportes R$ 0,00');
    expect(await numerosDoDashboard(page)).toEqual(antes);
    await evidencia(page.locator('.dashboard-flow-panel'), 'dashboard-desktop-fluxo');
    const p1 = partes(await page.locator('#flow-saidas-naturezas').innerText());
    expect(p1.aportes).toBeGreaterThanOrEqual(Math.round(Number(exemplo.valor) * 100));
    expect(p1.consumo + p1.aportes + p1.outras).toBe(total);
    expect(p1.consumo).toBe(p0.consumo - p1.aportes);
    const indicadores = (await chamarRpc(page, 'indicadores_gerenciais', { p_perfil_id: perfil, p_mes: exemplo.mes })).corpo;
    expect(Math.round(indicadores.aportes * 100)).toBe(p1.aportes);
    expect(Math.round(indicadores.fluxo_total * 100)).toBe(total);
    // Linha compacta: o painel do fluxo nao cresce.
    expect((await page.locator('.dashboard-flow-panel').boundingBox()).height).toBeLessThanOrEqual(altura + 1);

    // Tela estreita (celular no Dashboard): a linha cabe, sem rolagem horizontal da pagina.
    await page.setViewportSize({ width: 390, height: 844 });
    await abrirDashboard(page, exemplo.mes);
    expect(partes(await page.locator('#flow-saidas-naturezas').innerText())).toEqual(p1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.locator('.flow-summary').scrollIntoViewIfNeeded();
    await evidencia(page, 'dashboard-celular-fluxo');
    const caixa = await page.locator('#flow-saidas-naturezas').boundingBox();
    expect(caixa.x + caixa.width).toBeLessThanOrEqual(390);

    // Natureza nao definida aparece como "Outras saídas", ainda dentro do total.
    await marcar(request, exemplo.categoria_id, 'NAO_DEFINIDO');
    await abrirDashboard(page, exemplo.mes);
    const p2 = partes(await page.locator('#flow-saidas-naturezas').innerText());
    expect(p2.aportes).toBe(0);
    expect(p2.outras).toBe(p0.outras + p1.aportes);
    expect(p2.consumo + p2.outras).toBe(total);
    expect(await numerosDoDashboard(page)).toEqual(antes);

    await marcar(request, exemplo.categoria_id, null);
    await abrirDashboard(page, exemplo.mes);
    expect(partes(await page.locator('#flow-saidas-naturezas').innerText())).toEqual(p0);
});

test.describe('Lista de Despesas mobile', () => {
    test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

    async function abrirLista(page) {
        await page.goto(`/despesas-mobile.html?mes=${MES_F}`);
        await expect(page.locator('#mob-lista')).toHaveAttribute('data-competencia-carregada', MES_F);
        await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
        await expect(page.locator('#mob-total-naturezas')).toBeVisible();
    }
    const totais = async (page) => ({
        total: await page.locator('#mob-total .mob-total-valor').innerText(),
        detalhe: await page.locator('#mob-total .mob-total-detalhe').first().innerText(),
    });

    test('consumo e aportes sob o total, com o total e as parcelas pagas/pendentes iguais', async ({ page, request }) => {
        test.setTimeout(90 * 1000);
        await entrar(page, F, '**/inicio.html**');
        await abrirLista(page);  // abrir a competencia gera as recorrencias do mes (o teste nao depende de outro arquivo)
        const exemplo = await admin(request, { acao: 'natureza_exemplo', perfil: PERFIL_F, mes: MES_F });
        const antes = await totais(page);
        const total = centavos(antes.total);
        const p0 = partes(await page.locator('#mob-total-naturezas').innerText());
        expect(p0.aportes).toBe(0);
        expect(p0.consumo + p0.outras).toBe(total);

        await marcar(request, exemplo.categoria_id, 'APORTE');
        await abrirLista(page);
        expect(await totais(page)).toEqual(antes);
        const p1 = partes(await page.locator('#mob-total-naturezas').innerText());
        expect(p1.aportes).toBe(Math.round(Number(exemplo.valor) * 100));
        expect(p1.consumo + p1.aportes + p1.outras).toBe(total);
        // As parcelas de aporte continuam na lista (nenhuma despesa some).
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await page.locator('#mob-total').scrollIntoViewIfNeeded();
        await evidencia(page, 'lista-mobile-total');
        const caixa = await page.locator('#mob-total-naturezas').boundingBox();
        expect(caixa.height).toBeLessThanOrEqual(40);  // uma linha (duas, no maximo, em valores longos)

        await marcar(request, exemplo.categoria_id, null);
        await abrirLista(page);
        expect(partes(await page.locator('#mob-total-naturezas').innerText())).toEqual(p0);
        expect(await totais(page)).toEqual(antes);
    });
});
