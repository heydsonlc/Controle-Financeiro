// FIN-DESPESAS-CANCELAMENTO-01 (P23) — cancelar a obrigacao de uma ocorrencia com pagamento estornado. Usuario E (perfil
// proprio): "Sessao P23", semanal de R$ 250 (tercas de 05/2030), 4 sessoes pagas e estornadas e a de 14/05 paga de novo,
// como a Psicologa de 11/2026. A sessao de 07/05 foi desmarcada: o modal de exclusao oferece so "Cancelar obrigacao"; depois
// o agrupamento das pendentes passa de R$ 750,00 para R$ 500,00 e a recorrencia continua ativa. Dados FICTICIOS.
import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const E = { email: process.env.CF_EMAIL_E || 'usuario.e@teste.local', senha: process.env.CF_SENHA_E };
const EVIDENCIAS = process.env.CF_EVIDENCIAS_DIR;
const MES = '2030-05';
const NOME = 'Sessao P23';

test.use({ viewport: { width: 1366, height: 900 } });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
        if (/Ponte CSP|Adaptador:/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (req) => { if (new URL(req.url()).pathname.startsWith('/api/')) problemas.push(`chamada ao Flask: ${req.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/Flask').toEqual([]);
});

async function entrar(page) {
    await page.goto('/index.html');
    await page.fill('#email', E.email);
    await page.fill('#senha', E.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', /\d{2}\/\d{4}/);
    await page.waitForLoadState('networkidle');
}

async function sessoes(page, perfil, mes = MES) {
    const r = await chamarRpc(page, 'contas_do_mes', { p_perfil_id: perfil, p_mes: `${mes}-01` });
    return r.corpo.filter((c) => c.nome.startsWith(`${NOME} - `))
        .sort((a, b) => String(a.data_vencimento).localeCompare(String(b.data_vencimento)));
}

async function rpcOk(page, funcao, corpo) {
    const r = await chamarRpc(page, funcao, corpo);
    expect(r.status, `${funcao}: ${JSON.stringify(r.corpo)}`).toBe(200);
    return r.corpo;
}

const sessao = (page, dia) => page.locator('#despesas-lista .despesa-row-child', { hasText: `${NOME} - ${dia}` });
const escolha = (page) => page.locator('#modal-tipo-exclusao');
const botao = (page, tipo) => escolha(page).locator(`[data-on-click="confirmarTipoExclusao('${tipo}')"]`);

async function pendentesDoAgrupamento(page) {
    await page.selectOption('#filtro-status', 'pendente');
    const grupo = despesa(page, NOME);
    await expect(grupo).toHaveCount(1);
    return grupo;
}

async function editarSessao(page, dia) {
    const grupo = await pendentesDoAgrupamento(page);
    if (!(await grupo.locator('.agrupador-detalhes').isVisible())) await grupo.locator('[data-on-click^="toggleAgrupadorSemanal"]').click();
    await sessao(page, dia).locator('[title="Editar"]').click();
    await expect(page.locator('#modal-despesa')).toBeVisible();
}

// Sessao com pagamento estornado: o lapis abre o formulario so para consulta, com "Cancelar obrigacao" (antes recusava:
// "Esta despesa nao pode ser editada. Possui movimento financeiro vinculado.").
async function cancelarSessao(page, dia) {
    await editarSessao(page, dia);
    await expect(page.locator('#form-despesa .cf-aviso-cancelamento')).toContainText('pagamento anteriormente estornado');
    await expect(page.locator('#nome')).toBeDisabled();
    await expect(page.locator('#form-despesa button[type="submit"]')).toBeDisabled();
    await expect(page.locator('#btn-deletar-modal')).toBeHidden();
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/p23_formulario_1366.png` });
    await page.locator('#btn-cancelar-obrigacao').click();
    await expect(escolha(page)).toBeVisible();
}

async function excluirSessao(page, dia) {
    await editarSessao(page, dia);
    await expect(page.locator('#form-despesa .cf-aviso-cancelamento')).toHaveCount(0);
    await expect(page.locator('#nome')).toBeEnabled();
    await page.locator('#btn-deletar-modal').click();
    await expect(escolha(page)).toBeVisible();
}

test('sessao com pagamento estornado: Cancelar obrigacao tira so ela das pendentes e preserva o historico', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page);
    const perfil = await perfilAtivoId(page);
    const categorias = await rpcOk(page, 'categorias_de_despesa', {});
    const criada = await rpcOk(page, 'criar_despesa', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
        nome: NOME, valor: '250.00', categoria_id: categorias[0].id, data_vencimento: `${MES}-07`, recorrente: true, tipo_recorrencia: 'semanal_1_2' } });
    await abrirDespesas(page, MES);  // gera as 4 tercas
    const todas = await sessoes(page, perfil);
    expect(todas.map((c) => String(c.data_vencimento).slice(8, 10))).toEqual(['07', '14', '21', '28']);
    const contaE = (await rpcOk(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' })).find((c) => c.nome === 'Conta E (ficticia)');
    const pagar = (c) => rpcOk(page, 'pagar_despesa', { p_perfil_id: perfil, p_conta_id: c.id, p_chave: crypto.randomUUID(),
        p_dados: { conta_bancaria_id: contaE.id, data_pagamento: `${MES}-06`, valor_pago: '250.00', valor_devido: '250.00' } });
    for (const c of todas) {
        const p = await pagar(c);
        await rpcOk(page, 'estornar_pagamento_despesa', { p_perfil_id: perfil, p_conta_id: c.id, p_movimento_id: p.movimento_id,
            p_chave: crypto.randomUUID(), p_dados: { motivo: 'Pago por engano', data_estorno: `${MES}-06` } });
    }
    await pagar(todas[1]);  // 14/05 paga de novo
    const saldoAntes = (await rpcOk(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' })).find((c) => c.id === contaE.id).saldo_atual;

    await abrirDespesas(page, MES);
    const grupo = await pendentesDoAgrupamento(page);
    await expect(grupo.locator('> .despesa-linha-principal .despesa-cell-valor')).toHaveText(/R\$\s750,00/);

    // O modal oferece so "Cancelar obrigacao", com a mensagem; "esta e as futuras" fica fora deste caso.
    await cancelarSessao(page, '07/05');
    await expect(page.locator('#modal-exclusao-titulo')).toHaveText('Cancelar obrigação');
    await expect(page.locator('#modal-exclusao-texto')).toHaveText('Esta despesa possui um pagamento anteriormente estornado. '
        + 'O cancelamento encerrará a obrigação pendente, preservando o histórico financeiro.');
    await expect(botao(page, 'unica')).toHaveText('Cancelar obrigação');
    await expect(botao(page, 'unica')).toBeEnabled();
    await expect(botao(page, 'futuras')).toBeHidden();
    const alturas = await escolha(page).locator('button').evaluateAll((b) => b.filter((x) => x.offsetParent).map((x) => Math.round(x.getBoundingClientRect().height)));
    expect(new Set(alturas).size).toBe(1);  // botoes do modal no mesmo padrao
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/p23_cancelar_obrigacao_1366.png` });

    // Desistir nao grava nada
    await escolha(page).getByRole('button', { name: 'Cancelar', exact: true }).click();
    await expect(escolha(page)).toBeHidden();
    expect((await sessoes(page, perfil))[0].status_pagamento).toBe('Pendente');

    // Confirmar: so a sessao de 07/05 sai; o total das pendentes vai a R$ 500,00
    await cancelarSessao(page, '07/05');
    await botao(page, 'unica').click();
    await expect.poll(() => dialogos.at(-1)).toBe('Obrigação cancelada. A despesa deixou de ser exigível; o pagamento e o estorno continuam no histórico.');
    const depois = await pendentesDoAgrupamento(page);
    await expect(depois.locator('> .despesa-linha-principal .despesa-cell-valor')).toHaveText(/R\$\s500,00/);
    await depois.locator('[data-on-click^="toggleAgrupadorSemanal"]').click();
    await expect(page.locator('#despesas-lista .despesa-row-child', { hasText: `${NOME} - ` })).toHaveCount(2);
    await expect(sessao(page, '07/05')).toHaveCount(0);
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/p23_depois_1366.png` });
    const restantes = await sessoes(page, perfil);
    expect(restantes.map((c) => [String(c.data_vencimento).slice(8, 10), c.status_pagamento])).toEqual([['14', 'Pago'], ['21', 'Pendente'], ['28', 'Pendente']]);
    // recorrencia ativa e saldo igual (nenhum pagamento ou estorno novo)
    const rec = (await rpcOk(page, 'recorrencias_do_perfil', { p_perfil_id: perfil })).find((r) => r.id === criada.item_id);
    expect(rec.ativo).toBe(true);
    expect((await rpcOk(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' })).find((c) => c.id === contaE.id).saldo_atual).toBe(saldoAntes);
    // o lote das pendentes so tem as duas restantes
    await page.selectOption('#filtro-status', '');
    await despesa(page, NOME).locator('[data-on-click^="pagarTodasOcorrencias"]').click();
    await expect(page.locator('#pagar-lote-quantidade')).toHaveText('2');
    await expect(page.locator('#pagar-lote-total')).toHaveText('R$ 500,00');
    await page.click('#pagar-lote-cancelar');
});

test('sem pagamento estornado o modal de exclusao continua o mesmo', async ({ page }) => {
    await entrar(page);
    await abrirDespesas(page, '2030-06');  // sessoes de 06/2030: nunca pagas
    await excluirSessao(page, '04/06');
    await expect(page.locator('#modal-exclusao-titulo')).toHaveText('Excluir Despesa Recorrente');
    await expect(botao(page, 'unica')).toContainText('Excluir apenas esta parcela');
    await expect(botao(page, 'futuras')).toBeVisible();
    await expect(botao(page, 'unica')).toBeEnabled();
    await escolha(page).getByRole('button', { name: 'Cancelar', exact: true }).click();
    await expect(escolha(page)).toBeHidden();
    // Limpeza: a recorrencia de teste fica inativa (nada pendente para os outros specs).
    const perfil = await perfilAtivoId(page);
    const rec = (await rpcOk(page, 'recorrencias_do_perfil', { p_perfil_id: perfil })).find((r) => r.nome === NOME);
    await rpcOk(page, 'interromper_recorrencia', { p_perfil_id: perfil, p_item_id: rec.id, p_versao: rec.versao, p_efeito: '2030-06-01',
        p_esperadas: null, p_conta_id: null });
});
