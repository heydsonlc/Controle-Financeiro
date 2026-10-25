// FIN-RECORRENCIA-1 — gerar contas recorrentes e faturas, com confirmacao, em tela de celular.
// Dados FICTICIOS de tests/supabase_local.py (semear_recorrencia_e2e). Este arquivo GRAVA no
// banco descartavel: usa so meses de 2027 e roda depois dos outros (workers: 1, ordem alfabetica).
import { expect, test } from '@playwright/test';

import {
    despesa, esperarMes, nomes, preencherDespesa, registrarDialogos, salvarDespesa,
} from './despesas.mjs';
import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const ID_PERFIL_B = process.env.CF_ID_PERFIL_B || '103';

// FIN-FIDELIDADE-DESPESAS-1: tela original de Despesas, em resolucao de computador (como o Flask).
test.use({ viewport: { width: 1366, height: 900 } });

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
    await esperarMes(page, mes);
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
    await expect(page.locator('#despesas-lista .empty-state')).toBeVisible();
    await expect(page.locator('#aviso-texto')).toHaveText('6 lançamentos recorrentes ou faturas a gerar até 04/2027.');
    await expect(page.locator('#geracao-confirmacao')).toBeHidden();

    await page.click('#gerar-contas');
    await expect(page.locator('#geracao-confirmacao')).toBeVisible();
    await page.locator('#geracao-confirmacao').getByRole('button', { name: 'Cancelar' }).click();
    await expect(page.locator('#geracao-confirmacao')).toBeHidden();
    await expect(page.locator('#gerar-contas')).toBeVisible();

    await abrirMes(page, '2027-03');
    await expect(page.locator('#despesas-lista .empty-state')).toBeVisible();
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
    await expect(despesa(page, 'Mensalidade B').locator('.despesa-cell-vencimento')).toHaveText('31/03/2027');
    await expect(despesa(page, 'Cartao B').locator('.despesa-cell-vencimento')).toHaveText('31/03/2027');
    expect(await nomes(page)).toHaveLength(2);  // a conta e a fatura do mes
    await expect(page.locator('#aviso-geracao')).toBeHidden();

    // Repetir nao duplica: a mesma consulta nao tem mais nada a gerar.
    await abrirMes(page, '2027-03');
    await expect(despesa(page, 'Mensalidade B')).toHaveCount(1);
    await expect(page.locator('#aviso-geracao')).toBeHidden();

    // Fevereiro: competencia dispensada nao aparece e nao volta a ser oferecida.
    await abrirMes(page, '2027-02');
    expect(await nomes(page)).toEqual([]);
    await expect(page.locator('#aviso-texto')).toHaveText('1 lançamento recorrente ou fatura a gerar até 03/2027.');
    await page.locator('#geracao-acoes summary').click();
    expect(await textos(page.locator('#geracao-acoes .geracao-lista li')))
        .toEqual(['Mensalidade B · 02/2027 — Dispensada pelo usuario']);

    // Abril: dia 31 vira 30, sem deslocar os meses seguintes.
    await abrirMes(page, '2027-04');
    await expect(despesa(page, 'Mensalidade B').locator('.despesa-cell-vencimento')).toHaveText('30/04/2027');
    await expect(despesa(page, 'Mensalidade B').locator('.status-badge')).toHaveText('Pendente');
});

test('quem so le o perfil ve o aviso, mas nao tem a acao de gerar', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2027-05');
    await trocarPerfil(page, 'Empresa');
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
            body: JSON.stringify({ p_perfil_id: Number(document.getElementById('perfil-financeiro-switcher').dataset.perfilAtivoId),
                p_mes: '2028-01-01', p_total_previsto: 2 }),
        });
        return [resposta.status, (await resposta.json()).message];
    });
    expect(status).toEqual([400, 'A geracao deste perfil ainda e feita pelo sistema atual (Flask)']);
    await abrirMes(page, '2028-01');
    expect(await nomes(page)).toEqual([]);  // nada foi gravado
});

test('gerar por fora da tela: perfil de outro usuario e perfil so de leitura recebem 403', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2027-05');
    await trocarPerfil(page, 'Empresa');
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
        const empresa = Number(document.getElementById('perfil-financeiro-switcher').dataset.perfilAtivoId);
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

// FIN-DESPESAS-1 — recorrencia cadastrada pela tela, gerada pelo FIN-RECORRENCIA-1 (sem outro gerador), conta
// editada, excluida so ela (competencia dispensada) e "esta e as futuras" (recorrencia inativada). Perfil B (novo
// gerador), em 2029; roda depois dos cenarios de 2027 deste arquivo. FIN-FIDELIDADE-DESPESAS-1: pelos modais originais.
const escolaB = (page) => despesa(page, 'Escola B');

async function abrirEdicaoEscola(page) {
    await escolaB(page).locator('[data-on-click^="editarDespesa"]').click();
    await expect(page.locator('#modal-despesa')).toBeVisible();
}

test('recorrencia pela tela original: cadastrar, gerar, editar a conta, excluir so esta e esta e as futuras', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirMes(page, '2029-03');
    await page.click('.btn-nova-despesa');
    await preencherDespesa(page, { nome: 'Escola B', valor: '500', categoria: 'Moradia', vencimento: '2029-03-31',
        recorrente: true, tipo: 'mensal' });
    await salvarDespesa(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Recorrência cadastrada. As contas são geradas pela ação "Gerar contas".');
    await expect(escolaB(page)).toHaveCount(0);  // nenhum segundo gerador: ainda nao ha conta

    await page.click('#gerar-contas');
    const painel = page.locator('#geracao-confirmacao');
    expect(await textos(painel.locator('.geracao-lista li', { hasText: 'Escola B' })))
        .toEqual(['03/2029 · Escola B · Conta · 31/03/2029 · R$ 500,00', '04/2029 · Escola B · Conta · 30/04/2029 · R$ 500,00']);
    await painel.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.locator('#geracao-resultado')).toContainText('Geração concluída');
    await expect(escolaB(page).locator('.despesa-cell-vencimento')).toHaveText('31/03/2029');
    await expect(escolaB(page).locator('.despesa-cell-detalhe')).toHaveText('Recorrencia');

    // Editar a conta (so esta): o valor muda; mudar a recorrencia pelo formulario fica para a tela Recorrencias.
    await abrirEdicaoEscola(page);
    await expect(page.locator('#recorrente')).toBeChecked();
    await page.fill('#valor', '550');
    await salvarDespesa(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Despesa atualizada com sucesso');
    await expect(escolaB(page).locator('.despesa-cell-valor')).toHaveText('R$ 550,00');
    await abrirEdicaoEscola(page);
    await page.selectOption('#tipo_recorrencia', 'anual');
    await salvarDespesa(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Erro: Para alterar a recorrência (frequência e próximas contas), use a tela Recorrências.');
    await page.locator('#modal-despesa [data-on-click="fecharModal()"]').first().click();

    // Excluir so esta: o modal de tipo de exclusao do original; a competencia fica dispensada.
    await abrirEdicaoEscola(page);
    await page.click('#btn-deletar-modal');
    await expect(page.locator('#modal-tipo-exclusao')).toBeVisible();
    await expect(page.locator('#modal-exclusao-titulo')).toHaveText('Excluir Despesa Recorrente');
    await page.locator('#modal-tipo-exclusao button', { hasText: 'apenas esta' }).click();
    await expect.poll(() => dialogos.at(-1)).toBe('Despesa excluída com sucesso!');
    await expect(escolaB(page)).toHaveCount(0);
    await abrirMes(page, '2029-03');
    await expect(escolaB(page)).toHaveCount(0);           // nao volta
    await expect(page.locator('#gerar-contas')).toHaveCount(0);  // e nao e oferecida de novo

    // Esta e as futuras (abril): a recorrencia e inativada e a conta excluida; nada novo e gerado.
    await abrirMes(page, '2029-04');
    await abrirEdicaoEscola(page);
    await page.click('#btn-deletar-modal');
    await page.locator('#modal-tipo-exclusao button', { hasText: 'futuras' }).click();
    await expect.poll(() => dialogos.at(-1)).toBe('Despesa e todas as futuras foram excluídas com sucesso!');
    await expect(escolaB(page)).toHaveCount(0);
    const plano = await page.evaluate(async () => {
        const token = JSON.parse(localStorage.getItem('cf-financeiro-auth')).access_token;
        const r = await fetch(`${window.CF_CONFIG.supabaseUrl}/rest/v1/rpc/previa_geracao`, {
            method: 'POST',
            headers: { apikey: window.CF_CONFIG.supabasePublishableKey, Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json', 'Content-Profile': 'financeiro' },
            body: JSON.stringify({ p_perfil_id: Number(document.getElementById('perfil-financeiro-switcher').dataset.perfilAtivoId),
                p_mes: '2029-06-01' }),
        });
        return (await r.json()).itens.map((i) => i.nome);
    });
    expect(plano).not.toContain('Escola B');  // recorrencia inativada
});
