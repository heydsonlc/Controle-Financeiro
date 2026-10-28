// FIN-FIDELIDADE-PATRIMONIO-1 (Mobilidade, fase 1) — tela original de Mobilidade do Flask (frontend/templates/veiculos.html)
// sobre o Supabase. Dados FICTICIOS do "Perfil B" (tests/supabase_local.py, semear_mobilidade_e2e): veiculo com projecoes,
// regra de manutencao, assinatura e caminho de transporte por app. FIN-MOBILIDADE-2: as acoes da tela gravam pelas
// funcoes do banco (Perfil B no novo aplicativo), pela mesma ponte /api/... que js/original/veiculos.js usa.
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

async function api(page, metodo, url, corpo) {
    return page.evaluate(async ({ metodo, url, corpo }) => {
        const r = await fetch(url, { method: metodo, headers: { 'Content-Type': 'application/json' },
                                     body: corpo === undefined ? undefined : JSON.stringify(corpo) });
        return { status: r.status, corpo: await r.json() };
    }, { metodo, url, corpo });
}

test('veiculo, assinatura e transporte por app como no Flask; cadastro, projecoes, ativacao e confirmacao gravam', async ({ page }) => {
    registrarDialogos(page);
    await entrar(page, B);
    await page.goto('/mobilidade.html');
    await expect(page.locator('.mobilidade-aviso-fase')).toContainText('gravados no Supabase');
    await expect(page.locator('#comp-cards')).toContainText(VEICULO);  // aba inicial: comparacao
    await page.locator('#tab-configuracao').click();
    await expect(page.locator('#conf-veiculos-lista')).toContainText(VEICULO);
    await expect(page.locator('#conf-assinaturas-lista')).toContainText('Assinatura E2E (ficticia)');
    await expect(page.locator('#conf-apps-lista')).toContainText('App E2E (ficticio)');

    const perfil = await perfilAtivoId(page);
    const antes = (await chamarRpc(page, 'veiculos_tela', { p_perfil_id: perfil, p_id: null })).corpo;
    expect(antes.map((v) => v.nome)).toEqual([VEICULO]);

    // Cadastro: o veiculo novo sai com as projecoes do MVP (categorias sistemicas, nunca criadas aqui).
    const novo = await api(page, 'POST', '/api/veiculos', {
        nome: 'Moto E2E (ficticia)', tipo: 'moto', combustivel: 'gasolina', autonomia_km_l: 30, status: 'ATIVO',
        data_inicio: new Date().toISOString().slice(0, 10), combustivel_valor_mensal: 150, preco_medio_combustivel: 6,
    });
    expect(novo.status).toBe(201);
    expect(novo.corpo.data.nome).toBe('Moto E2E (ficticia)');
    const id = novo.corpo.data.id;
    const projecoes = (await chamarRpc(page, 'projecoes_mobilidade_tela', {
        p_perfil_id: perfil, p_origem_tipo: 'VEICULO', p_origem_id: id, p_meses: 12,
    })).corpo;
    expect(projecoes.length).toBe(12);
    expect(new Set(projecoes.map((p) => p.tipo_evento))).toEqual(new Set(['COMBUSTIVEL']));
    expect((await api(page, 'POST', `/api/veiculos/${id}/projecoes/gerar`, { meses_futuros: 12 })).corpo)
        .toMatchObject({ success: true, criadas: 12 });

    // Ativacao (exige confirmacao) e confirmacao de uma prevista, uma vez so. Sem recorrencia nem conta aqui: o banco do
    // E2E e compartilhado pelos specs de contas e recorrencias do Perfil B (a criacao delas esta nos testes Python).
    expect((await api(page, 'POST', '/api/veiculos/mobilidade/ativar', { tipo_modalidade: 'VEICULO', origem_id: id })).status).toBe(400);
    const ativada = await api(page, 'POST', '/api/veiculos/mobilidade/ativar', {
        tipo_modalidade: 'VEICULO', origem_id: id, meio_pagamento: 'pix', criar_recorrencia: false, confirmado: true,
    });
    expect(ativada.corpo.data.cenario).toMatchObject({ tipo_modalidade: 'VEICULO', origem_id: id, status: 'ATIVO' });
    expect(ativada.corpo.data.recorrencia).toBeNull();
    expect((await chamarRpc(page, 'mobilidade_ativa_tela', { p_perfil_id: perfil })).corpo.nome_origem).toBe('Moto E2E (ficticia)');
    const alvo = (await chamarRpc(page, 'projecoes_mobilidade_tela', {
        p_perfil_id: perfil, p_origem_tipo: 'VEICULO', p_origem_id: id, p_meses: 12,
    })).corpo[0];
    const confirmada = await api(page, 'POST', `/api/despesas-previstas/${alvo.id}/confirmar`, {});
    expect(confirmada.corpo.data).toEqual({ despesa_prevista: { id: alvo.id, status: 'CONFIRMADA' }, entidade_criada: null });
    expect((await api(page, 'POST', `/api/despesas-previstas/${alvo.id}/confirmar`, {})).status).toBe(400);

    // A tela recarregada mostra o veiculo novo.
    await page.reload();
    await page.locator('#tab-configuracao').click();
    await expect(page.locator('#conf-veiculos-lista')).toContainText('Moto E2E (ficticia)');
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
