// FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 — tela original de Receitas do Flask (js/original/receitas.js) sobre o
// Supabase, pelo adaptador. Dados FICTICIOS: leitura do cenario de 11/2026 (tests/supabase_local.py:
// semear_receitas_e2e); toda escrita com o usuario B no "Perfil B" (atribuido ao novo aplicativo, "Conta Perfil B"),
// so em 03/2028, e todo recebimento e estornado no fim (a conta volta ao saldo de partida para os specs seguintes).
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';
import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (r) => { if (new URL(r.url()).pathname.startsWith('/api/')) problemas.push(`rede /api/: ${r.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamadas ao Flask').toEqual([]);
});

const normal = (texto) => (texto || '').replace(/\s+/g, ' ').trim();
const linha = (page, nome) => page.locator('#mes-lista .receita-row', { has: page.locator('.receita-source strong', { hasText: nome }) });
const toast = (page) => page.locator('.receitas-toast');

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
}

async function abrir(page, ano, mes) {
    await page.goto('/receitas.html');
    await expect(page.locator('#fontes-resumo .receitas-loading')).toHaveCount(0);
    await page.selectOption('#filtro-ano', String(ano));
    await page.selectOption('#filtro-mes', mes);
    await expect(page.locator('#mes-lista .receitas-loading')).toHaveCount(0);
}

// Conta pelo inicio do rotulo ("nome (instituicao)", como o JS do Flask monta a opcao).
async function escolherConta(page, seletor, nome) {
    const valor = await page.locator(`${seletor} option`).evaluateAll(
        (opcoes, n) => (opcoes.find((o) => o.textContent.startsWith(n)) || {}).value, nome);
    expect(valor, `conta ${nome}`).toBeTruthy();
    await page.selectOption(seletor, valor);
}

async function consolidar(page, nome, { valor, data, justificativa, conta = 'Conta Perfil B' }) {
    await linha(page, nome).locator('[title="Confirmar/realizar"]').click();
    await expect(page.locator('#modal-consolidar-conta')).toBeVisible();
    await escolherConta(page, '#consolidar-conta-bancaria', conta);
    if (valor) await page.fill('#consolidar-valor-recebido', valor);
    if (data) await page.fill('#consolidar-data-recebimento', data);
    if (justificativa) await page.fill('#consolidar-justificativa', justificativa);
    await page.locator('#form-consolidar-conta button[type=submit]').click();
}

async function estornarLinha(page, nome, motivo) {
    await linha(page, nome).locator('[title="Estornar recebimento"]').click();
    await page.fill('#estornar-receita-motivo', motivo);
    await page.locator('#form-estornar-receita button[type=submit]').click();
    await expect(toast(page)).toContainText('Recebimento estornado com sucesso');
}

test('tela original: previsto, realizado e diferenca de 11/2026 sem linha virtual e sem somar duas vezes', async ({ page }) => {
    await entrar(page, A);
    await abrir(page, 2026, '11');
    await expect(page.locator('.module-actionbar.receitas-toolbar')).toBeVisible();
    await expect(page.locator('.receitas-kpi-grid')).toBeVisible();
    const salario = linha(page, 'Salário (A)');
    await expect(salario.locator('.receita-status-badge')).toHaveText('Parcial');
    expect(normal(await salario.locator('.receita-value').allTextContents().then((v) => v.join(' | '))))
        .toBe('R$ 5.000,00 | R$ 2.000,00 | -R$ 3.000,00');
    await expect(linha(page, 'Freelas').locator('.receita-status-badge')).toHaveText('Prevista');
    // Previsto 5.800 (5.000 + 800), realizado 2.000: a previsao recebida nao conta de novo.
    await expect(page.locator('#total-previsto')).toHaveText(/R\$\s5\.800,00/);
    await expect(page.locator('#total-realizado')).toHaveText(/R\$\s2\.000,00/);
    await expect(page.locator('#diferenca')).toHaveText(/-R\$\s3\.800,00/);
    // Fonte recorrente sem previsao gravada no mes (12/2026): nenhuma linha "virtual" do valor base.
    await page.selectOption('#filtro-mes', '12');
    await expect(page.locator('#mes-lista .receitas-empty-state')).toBeVisible();
    await expect(page.locator('#mes-lista .receita-row')).toHaveCount(0);
});

test('Perfil B: fonte nova, recebimento parcial, acima do que falta com justificativa, estornos e inativar', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrir(page, 2028, '03');
    await page.click('#btn-nova-receita');
    await page.fill('#fonte-nome', 'Freela Tela E2E');
    await page.selectOption('#fonte-tipo', 'RENDA_EXTRA');
    await page.fill('#fonte-valor-base', '1.000,00');
    await page.locator('label.receitas-switch', { has: page.locator('#fonte-recorrente') }).click();  // interruptor do Flask
    await expect(page.locator('#fonte-recorrente')).not.toBeChecked();
    await escolherConta(page, '#fonte-conta-bancaria', 'Conta Perfil B');
    await page.locator('#form-fonte button[type=submit]').click();
    await expect(toast(page)).toContainText('Fonte de receita criada com sucesso');
    const item = () => linha(page, 'Freela Tela E2E');
    await expect(item().locator('.receita-status-badge')).toHaveText('Prevista');

    // FIN-CATEGORIAS-RECORRENCIAS-2: "Proximos recebimentos" mostra a data prevista gravada, mesmo em outro mes.
    const perfilB = await perfilAtivoId(page);
    const fonteNova = (await chamarRpc(page, 'receitas_fontes_tela', { p_perfil_id: perfilB })).corpo.find((f) => f.nome === 'Freela Tela E2E');
    const prevista = (await chamarRpc(page, 'receitas_orcamentos_tela', { p_perfil_id: perfilB, p_ano: 2028 })).corpo
        .find((o) => o.item_receita_id === fonteNova.id);
    expect((await chamarRpc(page, 'editar_receita', { p_perfil_id: perfilB, p_orcamento_id: prevista.id, p_versao: prevista.versao,
        p_dados: { data_prevista: '2028-04-05' } })).status).toBe(200);
    await abrir(page, 2028, '03');
    await expect(page.locator('#proximos-recebimentos .receitas-proximo-item', { hasText: 'Freela Tela E2E' }))
        .toContainText('Vencimento: 05/04/2028');

    await consolidar(page, 'Freela Tela E2E', { valor: '400,00', data: '2028-03-15' });
    await expect(toast(page)).toContainText('Receita registrada com sucesso');
    await expect(item().locator('.receita-status-badge')).toHaveText('Parcial');
    expect(normal((await item().locator('.receita-value').allTextContents()).join(' | '))).toBe('R$ 1.000,00 | R$ 400,00 | -R$ 600,00');

    // Acima do que falta (600) sem justificativa: o banco recusa e nada e gravado.
    await consolidar(page, 'Freela Tela E2E', { valor: '700,00', data: '2028-03-20' });
    await expect(toast(page)).toContainText(/justificativa/i);
    await page.locator('#modal-consolidar-conta [aria-label="Fechar"]').click();
    await expect(item().locator('.receita-status-badge')).toHaveText('Parcial');
    await consolidar(page, 'Freela Tela E2E', { valor: '700,00', data: '2028-03-20', justificativa: 'Bonus junto com o pagamento' });
    await expect(toast(page)).toContainText('Receita registrada com sucesso');
    await expect(item().locator('.receita-status-badge')).toHaveText('Realizada');
    expect(normal((await item().locator('.receita-value').allTextContents()).join(' | '))).toBe('R$ 1.000,00 | R$ 1.100,00 | R$ 100,00');

    // Recebimentos e saldo conferidos no banco (dois recebimentos, conta com 1.100).
    const perfil = await perfilAtivoId(page);
    const dados = (await chamarRpc(page, 'receitas_realizadas_tela', { p_perfil_id: perfil, p_inicio: '2028-03', p_fim: '2028-03' })).corpo;
    expect(dados.filter((r) => r.item_receita?.nome === 'Freela Tela E2E').map((r) => [r.valor_recebido, r.data_recebimento]).sort())
        .toEqual([[400, '2028-03-15'], [700, '2028-03-20']]);

    // Editar a fonte (nome e descricao) e o valor base (FIN-CATEGORIAS-RECORRENCIAS-2): a previsao gravada nao muda.
    await item().locator('[title="Editar"]').click();
    await page.fill('#fonte-descricao', 'Projetos avulsos');
    await page.locator('#form-fonte button[type=submit]').click();
    await expect(toast(page)).toContainText('Fonte de receita atualizada com sucesso');
    await item().locator('[title="Editar"]').click();
    await page.fill('#fonte-valor-base', '2.000,00');
    await page.locator('#form-fonte button[type=submit]').click();
    await expect(toast(page)).toContainText('Fonte de receita atualizada com sucesso');
    const fonteB = (await chamarRpc(page, 'receitas_fontes_tela', { p_perfil_id: perfil })).corpo.find((f) => f.nome === 'Freela Tela E2E');
    expect(Number(fonteB.valor_base_mensal)).toBe(2000);
    const previsaoB = (await chamarRpc(page, 'receitas_orcamentos_tela', { p_perfil_id: perfil, p_ano: 2028 })).corpo
        .filter((o) => o.item_receita_id === fonteB.id);
    expect(previsaoB.map((o) => [o.mes_referencia, Number(o.valor_esperado)])).toEqual([['2028-03-01', 1000]]);

    // "Cancelar/ignorar" de recebimento: o Flask recusa excluir recebimento com movimento; aqui tambem.
    // Estorno: dois recebimentos, um estorno por vez (a linha mostra o botao quando ha um so).
    const realizadas = dados.filter((r) => r.item_receita?.nome === 'Freela Tela E2E');
    for (const r of realizadas) {
        const resp = await chamarRpc(page, 'estornar_recebimento', {
            p_perfil_id: perfil, p_realizada_id: r.id, p_chave: crypto.randomUUID(),
            p_dados: { motivo: 'Limpeza do E2E', data_estorno: '2028-03-25' } });
        expect(resp.status).toBe(200);
    }
    await abrir(page, 2028, '03');
    await expect(item().locator('.receita-status-badge')).toHaveText('Prevista');  // estornados nao contam

    // Estorno pela tela: novo recebimento e estorno dele.
    await consolidar(page, 'Freela Tela E2E', { valor: '1.000,00', data: '2028-03-26' });
    await expect(item().locator('.receita-status-badge')).toHaveText('Realizada');
    await estornarLinha(page, 'Freela Tela E2E', 'Credito devolvido');
    await expect(item().locator('.receita-status-badge')).toHaveText('Prevista');

    // Inativar a fonte pelo modal original.
    await item().locator('[title="Editar"]').click();
    await page.click('#btn-inativar-fonte');
    await expect(toast(page)).toContainText('Fonte de receita inativada com sucesso');
    expect(dialogos).toContain('Inativar esta fonte de receita?');

    const conta = (await chamarRpc(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' })).corpo
        .find((c) => c.nome === 'Conta Perfil B');
    expect(conta.saldo_atual).toBe(0);  // todos os recebimentos estornados
});

test('perfil ainda no Flask (Pessoal): consolidar e recusado sem gravar', async ({ page }) => {
    await entrar(page, A);
    await abrir(page, 2026, '11');
    await linha(page, 'Freelas').locator('[title="Confirmar/realizar"]').click();
    await escolherConta(page, '#consolidar-conta-bancaria', 'Conta Pessoal (A)');
    await page.locator('#form-consolidar-conta button[type=submit]').click();
    await expect(toast(page)).toContainText('Os recebimentos deste perfil ainda são feitos pelo sistema atual (Flask)');
    await page.locator('#modal-consolidar-conta [aria-label="Fechar"]').click();
    await expect(linha(page, 'Freelas').locator('.receita-status-badge')).toHaveText('Prevista');
});

test('quem so le (Empresa) nao ve acoes de escrita; B nao ve as receitas de A', async ({ page }) => {
    await entrar(page, A);
    await trocarPerfil(page, 'Empresa');
    await abrir(page, 2026, '11');
    await expect(linha(page, 'Consultoria')).toBeVisible();
    await expect(page.locator('#btn-nova-receita')).toBeHidden();
    for (const acao of ['Editar', 'Confirmar/realizar', 'Cancelar/ignorar']) {
        await expect(linha(page, 'Consultoria').locator(`[title="${acao}"]`)).toBeHidden();
    }
    await expect(linha(page, 'Salário (A)')).toHaveCount(0);

    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await entrar(page, B);
    await abrir(page, 2026, '11');
    await expect(linha(page, 'Freela B')).toBeVisible();
    await expect(linha(page, 'Salário (A)')).toHaveCount(0);
    await expect(linha(page, 'Consultoria')).toHaveCount(0);
});
