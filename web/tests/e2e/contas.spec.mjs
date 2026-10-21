// MOBILE-CONTAS-1 — tela "Contas do mes" (somente leitura), em tela de celular.
// Dados FICTICIOS de tests/supabase_local.py (semear_contas). Valores esperados calculados a mao.
import { expect, test } from '@playwright/test';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const ID_PERFIL_B = process.env.CF_ID_PERFIL_B || '103';
const ID_FATURA_EMPRESA = process.env.CF_ID_FATURA_EMPRESA || '511';

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
    await page.goto(`/contas.html?mes=${mes}`);
    await expect(page.locator('#totais')).toBeVisible();
}

async function totais(page) {
    return {
        total: normal(await page.locator('#total-mes').textContent()),
        pago: normal(await page.locator('#total-pago').textContent()),
        aPagar: normal(await page.locator('#total-a-pagar').textContent()),
    };
}

test('login abre Contas do mes no mes atual de Brasilia', async ({ page }) => {
    await entrar(page, A);
    const esperado = new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric', timeZone: 'America/Sao_Paulo' })
        .format(new Date());
    await expect(page.locator('#mes-titulo')).toHaveText(esperado.charAt(0).toUpperCase() + esperado.slice(1));
    await expect(page.locator('#totais')).toBeVisible();
});

test('novembro (Pessoal): despesas por vencimento, faturas por cartao e totais corretos', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-11');
    await expect(page.locator('#mes-titulo')).toHaveText('Novembro de 2026');
    expect(await totais(page)).toEqual({ total: 'R$ 4.390,50', pago: 'R$ 270,50', aPagar: 'R$ 4.120,00' });

    const despesas = page.locator('#lista-despesas .conta');
    expect(await textos(despesas.locator('.conta-nome'))).toEqual(['Plano de saude 11/2026', 'Internet 11/2026', 'Aluguel 11/2026']);
    expect(await textos(despesas.locator('.situacao'))).toEqual(['Pendente', 'Paga', 'Pendente']);
    expect(await textos(despesas.locator('.conta-valor'))).toEqual(['R$ 800,00', 'R$ 150,50', 'R$ 2.000,00']);

    expect(await textos(page.locator('#lista-cartoes .cartao-nome'))).toEqual(['Cartao Verde', 'Cartao Azul']);
    const faturas = page.locator('#lista-cartoes .conta');
    expect(await textos(faturas.locator('.conta-valor'))).toEqual(['R$ 120,00', 'R$ 1.320,00']);
    expect(await textos(faturas.locator('.situacao'))).toEqual(['Paga', 'Pendente']);
    // FIN-RECORRENCIA-1: nada a gerar, mas itens que o motor recusa ficam visiveis (sem acao de gerar).
    await expect(page.locator('#aviso-texto')).toHaveText('3 itens não podem ser gerados.');
    await expect(page.locator('#gerar-contas')).toHaveCount(0);
    await page.locator('#geracao-acoes summary').click();
    expect(await textos(page.locator('#geracao-acoes .geracao-lista li'))).toEqual([
        'Aluguel — Sem valor valido',
        'Cartao Azul · 12/2026 — Cartao sem dia de vencimento configurado',
        'Cartao Verde · 12/2026 — Cartao sem dia de vencimento configurado',
    ]);
});

test('detalhe da fatura mostra as compras do mes, sem compras de outro mes', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-11');
    const azul = page.locator('#lista-cartoes .cartao-grupo', { has: page.locator('.cartao-nome', { hasText: 'Cartao Azul' }) });
    await azul.locator('summary').click();
    const compras = azul.locator('.compra-descricao');
    await expect(compras).toHaveCount(6);
    expect(await textos(compras)).toContain('Compra parcelada (2/3)');
    expect(await textos(compras)).not.toContain('Supermercado dezembro');
    await expect(azul.locator('.conta-detalhe dd').first()).toHaveText(/1\.320,00/);  // previsto
});

test('janeiro: vencida por data, atrasada e paga apesar da data passada', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-01');
    expect(await textos(page.locator('#lista-despesas .situacao'))).toEqual(['Vencida', 'Vencida', 'Paga']);
    expect(await textos(page.locator('#lista-cartoes .situacao'))).toEqual(['Paga']);
    expect(await totais(page)).toEqual({ total: 'R$ 3.330,50', pago: 'R$ 650,50', aPagar: 'R$ 2.680,00' });
});

test('navegacao entre meses pelas setas, inclusive virada de ano', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-01');
    await page.click('#mes-anterior');
    await page.waitForURL(/mes=2025-12$/);
    await expect(page.locator('#mes-titulo')).toHaveText('Dezembro de 2025');
    await page.click('#mes-proximo');
    await page.waitForURL(/mes=2026-01$/);
    await expect(page.locator('#mes-titulo')).toHaveText('Janeiro de 2026');
});

test('mes sem contas mostra vazio e o aviso discreto quando ha indicio', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-06');
    await expect(page.locator('#contas-vazio')).toBeVisible();
    await expect(page.locator('#aviso-geracao')).toBeVisible();
    expect(await totais(page)).toEqual({ total: 'R$ 0,00', pago: 'R$ 0,00', aPagar: 'R$ 0,00' });
});

test('perfil Empresa mostra so as contas da Empresa', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-11');
    await page.selectOption('#perfil-ativo', { label: 'Empresa' });
    await expect(page.locator('#lista-despesas .conta-nome')).toHaveText(['Contador 11/2026']);
    await expect(page.locator('#lista-cartoes .cartao-nome')).toHaveText(['Cartao Empresa']);
    expect(await totais(page)).toEqual({ total: 'R$ 1.450,00', pago: 'R$ 0,00', aPagar: 'R$ 1.450,00' });
    await expect(page.getByText('Internet 11/2026')).toHaveCount(0);  // legado sem perfil e do Pessoal
});

test('usuario B ve so as proprias contas', async ({ page }) => {
    await entrar(page, B);
    await abrirMes(page, '2026-11');
    await expect(page.locator('#lista-despesas .conta-nome')).toHaveText(['Aluguel B 11/2026']);
    await expect(page.locator('#secao-cartoes')).toBeHidden();
    for (const nome of ['Aluguel 11/2026', 'Internet 11/2026', 'Contador 11/2026', 'Cartao Azul']) {
        await expect(page.getByText(nome)).toHaveCount(0);
    }
});

test('perfil ou fatura alterados no navegador nao dao acesso a contas de outro perfil', async ({ page }) => {
    await entrar(page, A);
    await page.evaluate((idB) => {
        const usuarioId = JSON.parse(localStorage.getItem('cf-financeiro-auth')).user.id;
        sessionStorage.setItem(`cf-perfil-ativo:${usuarioId}`, idB);
    }, ID_PERFIL_B);
    await abrirMes(page, '2026-11');
    await expect(page.locator('#perfil-ativo option:checked')).toHaveText('Pessoal');
    await expect(page.getByText('Aluguel B 11/2026')).toHaveCount(0);

    const status = await page.evaluate(async ({ idB, idFatura }) => {
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
        const pessoal = Number(document.getElementById('perfil-ativo').value);
        return [
            await chamar('contas_do_mes', { p_perfil_id: Number(idB), p_mes: '2026-11-01' }),
            await chamar('lancamentos_da_fatura', { p_perfil_id: pessoal, p_conta_id: Number(idFatura) }),
        ];
    }, { idB: ID_PERFIL_B, idFatura: ID_FATURA_EMPRESA });
    expect(status).toEqual([403, 403]);
});

test('tela de celular: sem rolagem horizontal, setas tocaveis e nenhuma acao de escrita', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-11');
    const larguras = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    expect(larguras[0]).toBeLessThanOrEqual(larguras[1]);
    for (const seta of ['#mes-anterior', '#mes-proximo']) {
        const caixa = await page.locator(seta).boundingBox();
        expect(caixa.width).toBeGreaterThanOrEqual(44);
        expect(caixa.height).toBeGreaterThanOrEqual(44);
    }
    await expect(page.locator('form, input, textarea, select:not(#perfil-ativo)')).toHaveCount(0);
    await expect(page.locator('button')).toHaveText(['Sair']);
});

test('parametro de mes invalido volta para o mes atual', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/contas.html?mes=2026-13');
    await expect(page.locator('#mes-titulo')).not.toHaveText(/13/);
    await expect(page.locator('#totais')).toBeVisible();
});
