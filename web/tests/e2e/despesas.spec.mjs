// FIN-DESPESAS-1 — cadastro, edicao e exclusao de despesas avulsas, bloqueios e autorizacao,
// em tela de celular. Dados FICTICIOS (tests/supabase_local.py). Grava no banco descartavel
// so em 2029 (perfil Pessoal do usuario A), longe dos meses dos outros cenarios.
// O fluxo de recorrencia (gerada pelo FIN-RECORRENCIA-1) esta no fim de recorrencia.spec.mjs.
import { expect, test } from '@playwright/test';

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

async function escolherCategoria(page, nome) {
    const valor = await page.locator('#despesa-categoria option', { hasText: nome }).first().getAttribute('value');
    await page.selectOption('#despesa-categoria', valor);
}

function despesa(page, nome) {
    return page.locator('#lista-despesas .conta', { has: page.locator('.conta-nome', { hasText: nome }) });
}

test('validacao no formulario: nada e enviado sem os campos obrigatorios', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2029-06');
    await page.click('#nova-despesa');
    await page.locator('#despesa-painel').getByRole('button', { name: 'Salvar' }).click();
    await expect(page.locator('#despesa-painel .login-error'))
        .toHaveText('Verifique: informe o nome, informe um valor válido, escolha a categoria, informe o vencimento.');
    await page.locator('#despesa-painel').getByRole('button', { name: 'Cancelar' }).click();
    await expect(page.locator('#despesa-painel')).toBeHidden();
    await expect(page.locator('#contas-vazio')).toBeVisible();
});

test('avulsa: cadastrar com competencia diferente do vencimento, editar e excluir', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2029-06');
    await page.click('#nova-despesa');
    await expect(page.locator('#despesa-tipo')).toHaveValue('avulsa');
    await page.fill('#despesa-nome', 'Conserto geladeira');
    await page.fill('#despesa-valor', '350,40');
    await escolherCategoria(page, 'Moradia');
    await page.fill('#despesa-vencimento', '2029-07-05');
    await page.locator('#despesa-vencimento').dispatchEvent('change');
    await expect(page.locator('#despesa-competencia')).toHaveValue('2029-07');  // padrao: mes do vencimento
    await page.fill('#despesa-competencia', '2029-06');
    await page.fill('#despesa-observacoes', 'Assistencia tecnica');
    await page.locator('#despesa-painel').getByRole('button', { name: 'Salvar' }).click();

    await expect(page.locator('#acao-resultado')).toHaveText('Despesa salva na competência 06/2029.');
    const item = despesa(page, 'Conserto geladeira');
    await expect(item.locator('.conta-vencimento')).toHaveText('Vence 05/07/2029');
    await expect(item.locator('.situacao')).toHaveText('Pendente');
    await expect(page.locator('#total-mes')).toHaveText(/350,40/);

    await abrirMes(page, '2029-07');  // vence em julho, mas pertence a junho
    await expect(page.locator('#lista-despesas .conta-nome', { hasText: 'Conserto geladeira' })).toHaveCount(0);

    await abrirMes(page, '2029-06');
    await despesa(page, 'Conserto geladeira').locator('summary').click();
    const acoes = despesa(page, 'Conserto geladeira').locator('.despesa-acoes button');
    await expect(acoes).toHaveText(['Editar', 'Excluir']);  // avulsa: sem acoes de recorrencia

    await acoes.filter({ hasText: 'Editar' }).click();
    await expect(page.locator('#despesa-valor')).toHaveValue('350,40');
    await expect(page.locator('#despesa-competencia')).toHaveValue('2029-06');
    await page.fill('#despesa-valor', '410,00');
    await page.locator('#despesa-painel').getByRole('button', { name: 'Salvar' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Despesa salva na competência 06/2029.');
    await expect(despesa(page, 'Conserto geladeira').locator('.conta-valor')).toHaveText(/410,00/);

    await despesa(page, 'Conserto geladeira').locator('summary').click();
    await despesa(page, 'Conserto geladeira').getByRole('button', { name: 'Excluir' }).click();
    await expect(despesa(page, 'Conserto geladeira').locator('.despesa-pergunta'))
        .toHaveText('Excluir esta despesa? Ela ainda não foi paga.');
    await despesa(page, 'Conserto geladeira').getByRole('button', { name: 'Confirmar exclusão' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Despesa excluída.');
    await expect(page.locator('#contas-vazio')).toBeVisible();
});

test('despesa paga e fatura nao oferecem edicao nem exclusao', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-11');
    const paga = despesa(page, 'Internet 11/2026');
    await paga.locator('summary').click();
    await expect(paga.locator('.despesa-bloqueio')).toHaveText('Despesa paga: correção só por estorno.');
    await expect(paga.locator('button')).toHaveCount(0);
    const fatura = page.locator('#lista-cartoes .conta').first();
    await fatura.locator('summary').click();
    await expect(fatura.locator('.despesa-acoes, .despesa-bloqueio')).toHaveCount(0);
});

test('perfil so de leitura: sem "Nova despesa" e sem acoes; escrita direta recebe 403', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-11');
    await expect(page.locator('#nova-despesa')).toBeVisible();  // Pessoal: A gerencia
    await page.selectOption('#perfil-ativo', { label: 'Empresa' });
    await expect(page.locator('#lista-despesas .conta-nome')).toHaveText(['Contador 11/2026']);
    await expect(page.locator('#nova-despesa')).toHaveCount(0);
    await despesa(page, 'Contador 11/2026').locator('summary').click();
    await expect(despesa(page, 'Contador 11/2026').locator('.despesa-caixa')).toBeEmpty();

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
        const empresa = Number(document.getElementById('perfil-ativo').value);
        const contaId = Number(document.querySelector('#lista-despesas .conta').dataset.contaId);
        const dados = { nome: 'Invasao', valor: '1.00', categoria_id: 1, data_vencimento: '2029-01-10' };
        return [
            await chamar('criar_despesa', { p_perfil_id: empresa, p_dados: dados, p_chave: crypto.randomUUID() }),
            await chamar('criar_despesa', { p_perfil_id: Number(idB), p_dados: dados, p_chave: crypto.randomUUID() }),
            await chamar('excluir_despesa', { p_perfil_id: empresa, p_conta_id: contaId, p_versao: 'x' }),
            await chamar('editar_despesa', { p_perfil_id: Number(idB), p_conta_id: contaId, p_versao: 'x', p_dados: {} }),
        ];
    }, ID_PERFIL_B);
    expect(status).toEqual([403, 403, 403, 403]);
    await abrirMes(page, '2026-11');
    await expect(page.locator('#lista-despesas .conta-nome')).toHaveText(['Contador 11/2026']);  // nada mudou
});

test('formulario aberto cabe na tela do celular, com campos tocaveis', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2029-06');
    await page.click('#nova-despesa');
    await page.check('#despesa-debito');
    await expect(page.locator('#despesa-conta-bancaria')).toBeVisible();
    const larguras = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    expect(larguras[0]).toBeLessThanOrEqual(larguras[1]);
    for (const campo of ['#despesa-nome', '#despesa-valor', '#despesa-categoria', '#despesa-vencimento']) {
        expect((await page.locator(campo).boundingBox()).height).toBeGreaterThanOrEqual(44);
    }
    expect((await page.locator('#despesa-tipo option').allTextContents()).map(normal))
        .toEqual(['Avulsa', 'Recorrente mensal', 'Recorrente anual']);
});
