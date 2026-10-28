// FIN-PRE-PRODUCAO-1 (2.1) — tela original de Indexadores do Flask (frontend/templates/indexadores.html, secao TR para
// financiamentos SAC/TR) sobre o Supabase. TR FICTICIAS de 2037 (as de 2034-2035 sao do semear_financiamento_e2e).
// Cadastro, edicao (prompt do Flask), importacao, faltantes e a recusa de competencia repetida, tudo pela tela.
import { expect, test } from '@playwright/test';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };

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

async function carregarAno(page, ano) {
    await page.fill('#trFiltroAno', String(ano));
    await page.click('button:has-text("Carregar TR")');
}

test('TR mensal pela tela: atalho em Financiamentos, cadastro, edicao, importacao, faltantes e competencia repetida', async ({ page }) => {
    await entrar(page, B);
    await page.goto('/financiamentos.html');
    await page.click('.fin-atalho-indexadores a');
    await page.waitForURL('**/indexadores.html');
    await expect(page.locator('.app-nav-link.active')).toHaveAttribute('data-pagina', 'financiamentos');
    await expect(page.locator('#tituloTrFinanciamentos')).toHaveText('TR para financiamentos SAC/TR');

    // Lista existente (TR ficticia do semear_financiamento_e2e), como o Flask: percentual com 4 casas, decimal com 8.
    await carregarAno(page, 2035);
    await expect(page.locator('#tabelaTrOficial tr')).toHaveCount(12);
    await expect(page.locator('#tabelaTrOficial tr').first()).toContainText('2035-12');
    await expect(page.locator('#tabelaTrOficial tr').first()).toContainText('0,1000%');
    await expect(page.locator('#tabelaTrOficial tr').first()).toContainText('0,00100000');

    // Cadastro.
    await page.fill('#trCompetencia', '2037-01');
    await page.fill('#trValorPercentual', '0,16');
    await page.click('#formTrOficial button[type="submit"]');
    await expect(page.locator('#alertContainer')).toContainText('TR cadastrada com sucesso.');
    await carregarAno(page, 2037);
    const linha = page.locator('#tabelaTrOficial tr', { hasText: '2037-01' });
    await expect(linha).toContainText('0,1600%');
    await expect(linha).toContainText('0,00160000');
    await expect(linha).toContainText('BACEN');
    await expect(linha).toContainText('Não');

    // Competencia repetida: mensagem do Flask, nada gravado.
    await page.fill('#trCompetencia', '2037-01');
    await page.fill('#trValorPercentual', '0,5');
    await page.click('#formTrOficial button[type="submit"]');
    await expect(page.locator('#alertContainer')).toContainText('TR da competência 2037-01 já cadastrada');

    // Edicao pelo prompt do Flask.
    page.once('dialog', (dialogo) => dialogo.accept('0,2'));
    await linha.locator('button:has-text("Editar")').click();
    await expect(page.locator('#alertContainer')).toContainText('TR atualizada com sucesso.');
    await expect(page.locator('#tabelaTrOficial tr', { hasText: '2037-01' })).toContainText('0,2000%');

    // Importacao por texto (uma linha invalida nao impede as demais).
    await page.fill('#trImportTexto', '2037-02;0,15\n2037-03;0,17\nlinha invalida');
    await page.fill('#trImportFonte', 'BACEN');
    await page.click('button:has-text("Importar")');
    await expect(page.locator('#alertContainer')).toContainText('Importação concluída: 2 criadas, 0 atualizadas, 0 ignoradas. 1 linha(s) com erro.');
    await expect(page.locator('#tabelaTrOficial tr')).toHaveCount(3);

    // Faltantes.
    await page.fill('#trFaltanteInicio', '2037-01');
    await page.fill('#trFaltanteFim', '2037-05');
    await page.click('button:has-text("Verificar faltantes")');
    await expect(page.locator('#trFaltantesResultado')).toHaveText('Faltantes: 2037-04, 2037-05');
});
