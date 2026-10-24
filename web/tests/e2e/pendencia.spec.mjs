// FIN-CARTOES-RECORRENCIA-PENDENCIA-1 — compra recorrente nao lancada porque a fatura de destino esta consolidada,
// em tela de celular. Usuario B no "Perfil B" temporario (gerador novo), recorrencia ficticia "Streaming B" no
// Cartao B a partir de 2033 (tests/supabase_local.py: PENDENCIA_E2E). A consolidacao usa o gancho do harness local,
// por isso o cenario so roda no banco descartavel (CF_E2E_LOCAL).
import { expect, test } from '@playwright/test';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };

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

function linhaStreaming(page) {
    return page.locator('#geracao-acoes .geracao-lista li', { hasText: 'Streaming B · 02/2033' });
}

async function ocorrencias(page) {
    return page.evaluate(async () => {
        const perfil = Number(document.getElementById('perfil-ativo').value);
        const token = JSON.parse(localStorage.getItem('cf-financeiro-auth')).access_token;
        const resposta = await fetch(`${window.CF_CONFIG.supabaseUrl}/rest/v1/rpc/recorrencias_rejeitadas`, {
            method: 'POST',
            headers: {
                apikey: window.CF_CONFIG.supabasePublishableKey,
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
                'Content-Profile': 'financeiro',
            },
            body: JSON.stringify({ p_perfil_id: perfil, p_incluir_dispensadas: true }),
        });
        return resposta.json();
    });
}

test('recorrencia com destino consolidado: aviso, dispensa auditavel e ocorrencia preservada', async ({ page }) => {
    test.skip(!process.env.CF_E2E_LOCAL, 'a consolidacao usa o gancho do harness local');
    await entrar(page, B);
    const consolidacao = await page.request.post('/__e2e__/consolidar', {
        data: { cartao: 'Cartao B', competencia: '2033-02-01', criar_se_faltar: true },
    });
    expect(consolidacao.status()).toBe(200);

    await abrirMes(page, '2033-02');
    await expect(page.locator('#aviso-texto')).toContainText('1 item não pode ser gerado');
    await page.locator('#geracao-acoes details summary').click();
    const linha = linhaStreaming(page);
    await expect(linha).toContainText('Fatura de 02/2033 consolidada');
    await expect(linha.getByRole('button', { name: 'Dispensar aviso' })).toBeVisible();
    expect(await ocorrencias(page)).toEqual([]);  // a previa nao grava

    await linha.getByRole('button', { name: 'Dispensar aviso' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Aviso dispensado. A ocorrência continua registrada.');
    await expect(page.locator('#aviso-texto')).not.toContainText('não pode ser gerado');

    // Persistencia depois de recarregar: aviso dispensado, ocorrencia pendente, nada lancado.
    await page.reload();
    await expect(page.locator('#totais')).toBeVisible();
    await page.locator('#geracao-acoes details summary').click();
    await expect(linhaStreaming(page)).toContainText('aviso dispensado');
    await expect(linhaStreaming(page).getByRole('button', { name: 'Dispensar aviso' })).toHaveCount(0);
    const [ocorrencia] = await ocorrencias(page);
    expect([ocorrencia.nome, ocorrencia.competencia, ocorrencia.situacao, ocorrencia.origem, Boolean(ocorrencia.aviso_dispensado_em)])
        .toEqual(['Streaming B', '2033-02-01', 'PENDENTE', 'NOVO_APP', true]);
    expect(normal(ocorrencia.motivo)).toContain('Fatura de 02/2033 consolidada');
});
