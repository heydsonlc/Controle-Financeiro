// FIN-FIDELIDADE-DESPESAS-1 — apoio dos specs da tela original de Despesas (frontend/templates/despesas.html).
import { expect } from '@playwright/test';

export const normal = (texto) => (texto || '').replace(/\s+/g, ' ').trim();
const competenciaBr = (mes) => `${mes.slice(5, 7)}/${mes.slice(0, 4)}`;

// A tela original usa alert()/confirm(): aceita e guarda as mensagens para conferir.
export function registrarDialogos(page) {
    const mensagens = [];
    page.on('dialog', async (dialogo) => {
        mensagens.push(dialogo.message());
        await dialogo.accept();
    });
    return mensagens;
}

export async function esperarMes(page, mes) {
    await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', competenciaBr(mes));
}

export async function abrirDespesas(page, mes) {
    await page.goto(`/contas.html?mes=${mes}`);
    await esperarMes(page, mes);
}

// Troca a competencia como o usuario (campo MM/AAAA do filtro) e espera o mes carregar.
export async function trocarCompetencia(page, mes) {
    await page.fill('#filtro-competencia', competenciaBr(mes));
    await page.locator('#filtro-competencia').dispatchEvent('change');
    await esperarMes(page, mes);
}

export const cartoesDespesa = (page) => page.locator('#despesas-lista .despesa-card:not(.despesa-row-child)');
export const despesa = (page, nome) => page.locator('#despesas-lista .despesa-card:not(.despesa-row-child)',
    { has: page.locator('.despesa-cell-nome', { hasText: nome }) });
export const textos = async (locator) => (await locator.allTextContents()).map(normal);
export const nomes = (page) => textos(cartoesDespesa(page).locator('.despesa-cell-nome'));
export const situacoes = (page) => textos(cartoesDespesa(page).locator('.status-badge'));
export const valores = (page) => textos(cartoesDespesa(page).locator('.despesa-cell-valor'));

export async function resumo(page) {
    return {
        total: normal(await page.locator('#total-geral').textContent()),
        pendentes: normal(await page.locator('#total-pendentes').textContent()),
        pagas: normal(await page.locator('#total-pagas').textContent()),
    };
}

export async function primeiraCategoria(page, nome) {
    const opcao = nome
        ? page.locator('#categoria_id option', { hasText: nome }).first()
        : page.locator('#categoria_id option:not([value=""])').first();
    return opcao.getAttribute('value');
}

// Modal "Nova Despesa" do original. d: { nome, valor, categoria, vencimento, competencia, observacoes, recorrente, tipo }
export async function preencherDespesa(page, d) {
    await page.fill('#nome', d.nome);
    if (d.observacoes !== undefined) await page.fill('#descricao', d.observacoes);
    await page.fill('#valor', String(d.valor));
    await page.selectOption('#categoria_id', await primeiraCategoria(page, d.categoria));
    if (d.vencimento) {
        await page.fill('#data_vencimento', d.vencimento);
        await page.locator('#data_vencimento').dispatchEvent('change');
    }
    if (d.recorrente) {
        await page.check('#recorrente');
        if (d.tipo) await page.selectOption('#tipo_recorrencia', d.tipo);
    }
    if (d.competencia) await page.fill('#mes_competencia', d.competencia);
}

export async function salvarDespesa(page) {
    await page.click('#form-despesa button[type=submit]');
}

export async function abrirPagamento(page, nome) {
    await despesa(page, nome).locator('[data-on-click^="marcarComoPago"]').click();
    await expect(page.locator('#modal-pagar')).toBeVisible();
}

// Modal "Pagar" do original; outro valor exige classificacao e justificativa (FIN-MOVIMENTACOES-1).
export async function pagar(page, nome, p = {}) {
    await abrirPagamento(page, nome);
    if (p.data) await page.fill('#pagar-data', p.data);
    if (p.valor !== undefined) {
        await page.check('input[name="tipo-pagamento"][value="parcial"]');
        await page.fill('#pagar-valor-pago', String(p.valor));
        await page.locator('#pagar-valor-pago').dispatchEvent('input');
    }
    if (p.tipo) await page.selectOption('#pagar-ajuste-tipo', p.tipo);
    if (p.justificativa) await page.fill('#pagar-ajuste-justificativa', p.justificativa);
    const conta = page.locator('#pagar-conta-bancaria');
    if (await conta.isEnabled()) await conta.selectOption(p.conta ? { label: p.conta } : { index: 1 });
    await page.click('#form-pagar button[type=submit]');
}

export async function estornar(page, nome, motivo, data) {
    await despesa(page, nome).locator('[data-on-click^="abrirModalEstorno"]').click();
    await expect(page.locator('#modal-estorno')).toBeVisible();
    if (data) await page.fill('#estorno-data', data);
    await page.fill('#estorno-motivo', motivo);
    await page.click('#form-estorno button[type=submit]');
}

// Chamada direta a uma funcao do Supabase com o token da sessao (testes de autorizacao).
export async function chamarRpc(page, funcao, corpo) {
    return page.evaluate(async ({ funcao, corpo }) => {
        const token = JSON.parse(localStorage.getItem('cf-financeiro-auth')).access_token;
        const r = await fetch(`${window.CF_CONFIG.supabaseUrl}/rest/v1/rpc/${funcao}`, {
            method: 'POST',
            headers: {
                apikey: window.CF_CONFIG.supabasePublishableKey,
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
                'Content-Profile': 'financeiro',
            },
            body: JSON.stringify(corpo),
        });
        return { status: r.status, corpo: await r.json().catch(() => null) };
    }, { funcao, corpo });
}

export const perfilAtivoId = (page) => page.evaluate(() => Number(document.getElementById('perfil-financeiro-switcher').dataset.perfilAtivoId));
