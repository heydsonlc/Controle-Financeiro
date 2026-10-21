// FIN-RECORRENCIA-1 — gerar contas recorrentes e faturas, com confirmacao, em tela de celular.
// Dados FICTICIOS de tests/supabase_local.py (semear_recorrencia_e2e). Este arquivo GRAVA no
// banco descartavel: usa so meses de 2027 e roda depois dos outros (workers: 1, ordem alfabetica).
import { expect, test } from '@playwright/test';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
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

const LINHAS_MARCO = [
    '01/2027 · Mensalidade B · Conta · 31/01/2027 · R$ 120,00',
    '02/2027 · Mensalidade B · Conta · 28/02/2027 · R$ 120,00',
    '03/2027 · Mensalidade B · Conta · 31/03/2027 · R$ 120,00',
    '03/2027 · Cartao B · Fatura · 31/03/2027 · R$ 0,00',
    '04/2027 · Mensalidade B · Conta · 30/04/2027 · R$ 120,00',
    '04/2027 · Cartao B · Fatura · 30/04/2027 · R$ 0,00',
];

test('consulta do mes nao grava: aviso discreto e acao "Gerar contas"; cancelar nao grava', async ({ page }) => {
    await entrar(page, B);
    await abrirMes(page, '2027-03');
    await expect(page.locator('#contas-vazio')).toBeVisible();
    await expect(page.locator('#aviso-texto')).toHaveText('6 lançamentos recorrentes ou faturas a gerar até 04/2027.');
    await expect(page.locator('#geracao-confirmacao')).toBeHidden();

    await page.click('#gerar-contas');
    await expect(page.locator('#geracao-confirmacao')).toBeVisible();
    await page.locator('#geracao-confirmacao').getByRole('button', { name: 'Cancelar' }).click();
    await expect(page.locator('#geracao-confirmacao')).toBeHidden();
    await expect(page.locator('#gerar-contas')).toBeVisible();

    await abrirMes(page, '2027-03');
    await expect(page.locator('#contas-vazio')).toBeVisible();
    await expect(page.locator('#aviso-texto')).toHaveText('6 lançamentos recorrentes ou faturas a gerar até 04/2027.');
});

test('confirmacao mostra competencias e registros; dispensa fica registrada; dia contratual preservado', async ({ page }) => {
    await entrar(page, B);
    await abrirMes(page, '2027-03');
    await page.click('#gerar-contas');
    const painel = page.locator('#geracao-confirmacao');
    await expect(painel.locator('p').first()).toHaveText('6 registros em 4 competências: 01/2027, 02/2027, 03/2027, 04/2027.');
    await expect(painel.locator('.geracao-alerta')).toHaveText(/anteriores ao mês exibido/);
    const linhas = painel.locator('.geracao-lista li');
    expect(await textos(linhas)).toEqual(LINHAS_MARCO);
    await expect(painel.locator('input[type=checkbox]')).toHaveCount(4);  // fatura nao e dispensavel

    await linhas.filter({ hasText: '02/2027 · Mensalidade B' }).locator('input').uncheck();
    await painel.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.locator('#geracao-resultado'))
        .toHaveText('Geração concluída: 5 criadas, 0 já existentes, 1 dispensada, 0 rejeitadas.');

    // Lista recarregada: conta e fatura do mes, aviso some.
    await expect(page.locator('#lista-despesas .conta-nome')).toHaveText(['Mensalidade B']);
    await expect(page.locator('#lista-despesas .conta-vencimento')).toHaveText(['Vence 31/03/2027']);
    await expect(page.locator('#lista-cartoes .cartao-nome')).toHaveText(['Cartao B']);
    await expect(page.locator('#lista-cartoes .conta-vencimento')).toHaveText(['Vence 31/03/2027']);
    await expect(page.locator('#aviso-geracao')).toBeHidden();

    // Repetir nao duplica: a mesma consulta nao tem mais nada a gerar.
    await abrirMes(page, '2027-03');
    await expect(page.locator('#lista-despesas .conta')).toHaveCount(1);
    await expect(page.locator('#aviso-geracao')).toBeHidden();

    // Fevereiro: competencia dispensada nao aparece e nao volta a ser oferecida.
    await abrirMes(page, '2027-02');
    await expect(page.locator('#lista-despesas .conta')).toHaveCount(0);
    await expect(page.locator('#aviso-texto')).toHaveText('1 lançamento recorrente ou fatura a gerar até 03/2027.');
    await page.locator('#geracao-acoes summary').click();
    expect(await textos(page.locator('#geracao-acoes .geracao-lista li')))
        .toEqual(['Mensalidade B · 02/2027 — Dispensada pelo usuario']);

    // Abril: dia 31 vira 30, sem deslocar os meses seguintes.
    await abrirMes(page, '2027-04');
    await expect(page.locator('#lista-despesas .conta-vencimento')).toHaveText(['Vence 30/04/2027']);
    await expect(page.locator('#lista-despesas .situacao')).toHaveText(['Pendente']);
});

test('quem so le o perfil ve o aviso, mas nao tem a acao de gerar', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2027-05');
    await page.selectOption('#perfil-ativo', { label: 'Empresa' });
    await expect(page.locator('#aviso-texto')).toHaveText(/^2 lançamentos recorrentes ou faturas a gerar até 06\/2027/);
    await expect(page.locator('#geracao-acoes')).toContainText('Somente quem gerencia este perfil pode gerar.');
    await expect(page.locator('#gerar-contas')).toHaveCount(0);
});

test('perfil ainda gerado pelo sistema atual: aviso sem a acao de gerar (FIN-RECORRENCIA-T1)', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2028-01');
    await expect(page.locator('#aviso-texto')).toHaveText(/^2 lançamentos recorrentes ou faturas a gerar até 02\/2028/);
    await expect(page.locator('#geracao-acoes')).toContainText('A geração deste perfil ainda é feita pelo sistema atual.');
    await expect(page.locator('#gerar-contas')).toHaveCount(0);
    const status = await page.evaluate(async () => {
        const token = JSON.parse(localStorage.getItem('cf-financeiro-auth')).access_token;
        const resposta = await fetch(`${window.CF_CONFIG.supabaseUrl}/rest/v1/rpc/gerar_mes`, {
            method: 'POST',
            headers: {
                apikey: window.CF_CONFIG.supabasePublishableKey,
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
                'Content-Profile': 'financeiro',
            },
            body: JSON.stringify({ p_perfil_id: Number(document.getElementById('perfil-ativo').value),
                p_mes: '2028-01-01', p_total_previsto: 2 }),
        });
        return [resposta.status, (await resposta.json()).message];
    });
    expect(status).toEqual([400, 'A geracao deste perfil ainda e feita pelo sistema atual (Flask)']);
    await abrirMes(page, '2028-01');
    await expect(page.locator('#lista-despesas .conta')).toHaveCount(0);  // nada foi gravado
});

test('gerar por fora da tela: perfil de outro usuario e perfil so de leitura recebem 403', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2027-05');
    await page.selectOption('#perfil-ativo', { label: 'Empresa' });
    await expect(page.locator('#aviso-texto')).toBeVisible();
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
        return [
            await chamar('gerar_mes', { p_perfil_id: Number(idB), p_mes: '2027-03-01', p_total_previsto: 0 }),
            await chamar('previa_geracao', { p_perfil_id: Number(idB), p_mes: '2027-03-01' }),
            await chamar('gerar_mes', { p_perfil_id: empresa, p_mes: '2027-05-01', p_total_previsto: 2 }),
            await chamar('plano_recorrencia', { p_perfil_id: empresa, p_mes: '2027-05-01' }),
        ];
    }, ID_PERFIL_B);
    expect(status.slice(0, 3)).toEqual([403, 403, 403]);
    expect([401, 403, 404]).toContain(status[3]);  // funcao interna: sem EXECUTE para o navegador
});

// FIN-DESPESAS-1 — recorrencia cadastrada pela tela, gerada pelo FIN-RECORRENCIA-1 (sem outro
// gerador), editada, conta excluida (competencia dispensada) e inativada. Perfil B (novo gerador),
// em 2029; roda depois dos cenarios de 2027 deste arquivo.
async function escolherCategoria(page, nome) {
    const valor = await page.locator('#despesa-categoria option', { hasText: nome }).first().getAttribute('value');
    await page.selectOption('#despesa-categoria', valor);
}

const escolaB = (page) => page.locator('#lista-despesas .conta', { has: page.locator('.conta-nome', { hasText: 'Escola B' }) });

test('recorrencia pela tela: cadastrar, gerar, editar, excluir conta (dispensada) e inativar', async ({ page }) => {
    await entrar(page, B);
    await abrirMes(page, '2029-03');
    await page.click('#nova-despesa');
    await page.selectOption('#despesa-tipo', 'mensal');
    await expect(page.locator('#despesa-competencia')).toBeHidden();  // na recorrencia, o mes de cada vencimento
    await page.fill('#despesa-nome', 'Escola B');
    await page.fill('#despesa-valor', '500,00');
    await escolherCategoria(page, 'Moradia');
    await page.fill('#despesa-vencimento', '2029-03-31');
    await page.locator('#despesa-painel').getByRole('button', { name: 'Salvar' }).click();
    await expect(page.locator('#acao-resultado'))
        .toHaveText('Recorrência cadastrada. As contas são geradas pela ação "Gerar contas".');
    await expect(escolaB(page)).toHaveCount(0);  // nenhum segundo gerador: ainda nao ha conta

    await page.click('#gerar-contas');
    const painel = page.locator('#geracao-confirmacao');
    expect(await textos(painel.locator('.geracao-lista li', { hasText: 'Escola B' })))
        .toEqual(['03/2029 · Escola B · Conta · 31/03/2029 · R$ 500,00', '04/2029 · Escola B · Conta · 30/04/2029 · R$ 500,00']);
    await painel.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.locator('#geracao-resultado')).toContainText('Geração concluída');
    await expect(escolaB(page).locator('.conta-vencimento')).toHaveText('Vence 31/03/2029');

    await escolaB(page).locator('summary').click();
    await expect(escolaB(page).locator('.despesa-acoes button'))
        .toHaveText(['Editar', 'Excluir', 'Editar recorrência', 'Inativar recorrência']);
    await escolaB(page).getByRole('button', { name: 'Editar recorrência' }).click();
    await page.fill('#despesa-valor', '550,00');
    await page.locator('#despesa-painel').getByRole('button', { name: 'Salvar' }).click();
    await expect(page.locator('#acao-resultado'))
        .toHaveText('Recorrência atualizada. Vale para as próximas contas; as já existentes não mudam.');
    await expect(escolaB(page).locator('.conta-valor')).toHaveText(/500,00/);  // conta existente nao muda

    await escolaB(page).locator('summary').click();
    await escolaB(page).getByRole('button', { name: 'Excluir' }).click();
    await expect(escolaB(page).locator('.despesa-pergunta'))
        .toHaveText('Excluir esta conta? A competência fica dispensada e não volta a ser gerada.');
    await escolaB(page).getByRole('button', { name: 'Confirmar exclusão' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Despesa excluída.');
    await expect(escolaB(page)).toHaveCount(0);
    await abrirMes(page, '2029-03');
    await expect(escolaB(page)).toHaveCount(0);           // nao volta
    await expect(page.locator('#gerar-contas')).toHaveCount(0);  // e nao e oferecida de novo

    await abrirMes(page, '2029-04');
    await escolaB(page).locator('summary').click();
    await escolaB(page).getByRole('button', { name: 'Inativar recorrência' }).click();
    await escolaB(page).getByRole('button', { name: 'Confirmar inativação' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Recorrência inativada.');
    await expect(escolaB(page).locator('.conta-valor')).toHaveText(/500,00/);  // historico fica
    await escolaB(page).locator('summary').click();
    await expect(escolaB(page).getByRole('button', { name: 'Inativar recorrência' })).toHaveCount(0);

    await abrirMes(page, '2029-06');
    await page.click('#gerar-contas');
    await expect(page.locator('#geracao-confirmacao .geracao-lista li', { hasText: 'Escola B' })).toHaveCount(0);
});
