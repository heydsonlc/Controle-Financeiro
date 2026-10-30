// FIN-FIDELIDADE-DESPESAS-1 — cadastro, edicao e exclusao pela tela original de Despesas (modal do Flask), com as
// regras do banco (FIN-DESPESAS-1). Dados FICTICIOS (tests/supabase_local.py). Grava no banco descartavel.
import { expect, test } from '@playwright/test';

import {
    abrirDespesas, chamarRpc, despesa, nomes, perfilAtivoId, preencherDespesa, registrarDialogos, resumo, salvarDespesa,
    trocarCompetencia,
} from './despesas.mjs';
import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const ID_PERFIL_B = process.env.CF_ID_PERFIL_B || '103';

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
        if (msg.type() === 'warning' && /Ponte CSP/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS').toEqual([]);
});

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
}

test('validacao do formulario original: nada e enviado sem os campos obrigatorios', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, A);
    await abrirDespesas(page, '2029-06');
    await page.click('.btn-nova-despesa');
    await expect(page.locator('#modal-despesa')).toBeVisible();
    await expect(page.locator('#modal-titulo')).toHaveText('Nova Despesa');
    await salvarDespesa(page);
    await expect(page.locator('#modal-despesa')).toBeVisible();  // required do HTML original
    expect(dialogos).toEqual([]);
    await page.locator('#modal-despesa [data-on-click="fecharModal()"]').first().click();
    await expect(page.locator('#modal-despesa')).toBeHidden();
});

// FIN-ESCRITOR-UNICO-FINAL-1: o Pessoal segue no Flask; o cadastro pelo novo aplicativo e recusado, sem gravar.
test('perfil ainda no Flask: cadastro pelo modal original recusado sem gravar', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, A);
    await abrirDespesas(page, '2029-06');
    await page.click('.btn-nova-despesa');
    await preencherDespesa(page, { nome: 'Conserto recusado', valor: '10', categoria: 'Moradia', vencimento: '2029-07-05' });
    await salvarDespesa(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Erro: Este perfil ainda é administrado pelo sistema atual (Flask). Nada foi gravado.');
    await abrirDespesas(page, '2029-06');
    await expect(despesa(page, 'Conserto recusado')).toHaveCount(0);
});

// FIN-ESCRITOR-UNICO-FINAL-1: o cadastro completo e no Perfil B (novo aplicativo).
test('avulsa: cadastrar pelo modal original (competencia do Flask), editar e excluir', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirDespesas(page, '2029-06');
    // FIN-RECORRENCIAS-AUTOMATICAS-1: o mes ja abre com as recorrencias do Perfil B geradas; a avulsa soma a elas.
    const totalGeral = async () => Number((await page.locator('#total-geral').textContent()).replace(/[^\d,]/g, '').replace(',', '.'));
    const antes = await totalGeral();
    await page.click('.btn-nova-despesa');
    await preencherDespesa(page, { nome: 'Conserto geladeira', valor: '350.40', categoria: 'Moradia', vencimento: '2029-07-05',
        observacoes: 'Assistencia tecnica' });
    await expect(page.locator('#mes_competencia')).toHaveValue('2029-06');  // regra do Flask: mes anterior ao vencimento
    await salvarDespesa(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Despesa salva na competência 06/2029.');
    await expect(despesa(page, 'Conserto geladeira')).toBeVisible();
    await expect(despesa(page, 'Conserto geladeira').locator('.despesa-cell-detalhe')).toHaveText('Assistencia tecnica');
    await expect.poll(totalGeral).toBeCloseTo(antes + 350.40, 2);

    await trocarCompetencia(page, '2029-07');  // vence em julho, mas pertence a junho
    await expect(despesa(page, 'Conserto geladeira')).toHaveCount(0);
    await trocarCompetencia(page, '2029-06');

    await despesa(page, 'Conserto geladeira').locator('[data-on-click^="editarDespesa"]').click();
    await expect(page.locator('#modal-titulo')).toHaveText('Editar Despesa');
    await expect(page.locator('#valor')).toHaveValue('350.4');
    await expect(page.locator('#mes_competencia')).toHaveValue('2029-06');
    await expect(page.locator('#descricao')).toHaveValue('Assistencia tecnica');
    await page.fill('#valor', '410');
    await salvarDespesa(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Despesa atualizada com sucesso');
    await expect(despesa(page, 'Conserto geladeira').locator('.despesa-cell-valor')).toHaveText('R$ 410,00');
    await expect(despesa(page, 'Conserto geladeira').locator('.despesa-cell-nome')).toHaveText('Conserto geladeira');

    await despesa(page, 'Conserto geladeira').locator('[data-on-click^="editarDespesa"]').click();
    await page.click('#btn-deletar-modal');
    await expect.poll(() => dialogos.at(-1)).toBe('Despesa excluída com sucesso');
    expect(dialogos.at(-2)).toMatch(/^Tem certeza que deseja deletar a despesa "Conserto geladeira"\?/);
    await expect(despesa(page, 'Conserto geladeira')).toHaveCount(0);
    await expect.poll(totalGeral).toBeCloseTo(antes, 2);
});

test('despesa paga nao abre edicao e fatura nao tem edicao', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, A);
    await abrirDespesas(page, '2026-11');
    await despesa(page, 'Internet 11/2026').locator('[data-on-click^="editarDespesa"]').click();
    await expect.poll(() => dialogos.at(-1))
        .toBe('Erro ao carregar despesa: Esta despesa não pode ser editada. Despesa paga: para corrigir, estorne o pagamento.');
    await expect(page.locator('#modal-despesa')).toBeHidden();
    await expect(despesa(page, 'Fatura Cartao Azul').locator('[data-on-click^="editarDespesa"]')).toHaveCount(0);
});

test('pedidos do formulario que o novo aplicativo ainda nao atende: recusados com aviso, sem gravar nada', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, A);
    await abrirDespesas(page, '2029-08');
    await page.click('.btn-nova-despesa');
    await preencherDespesa(page, { nome: 'Faxina', valor: '120', categoria: 'Moradia', vencimento: '2029-08-10' });
    await page.check('#pago');
    await salvarDespesa(page);
    await expect.poll(() => dialogos.at(-1))
        .toBe('Erro: Use a ação de pagamento para marcar a despesa como paga: ela escolhe a conta bancária e registra o movimento.');
    // Semanal e a cada 2 semanas deixaram de ser recusadas (FIN-CATEGORIAS-RECORRENCIAS-2; ver recorrencias_tela.spec).
    await page.locator('#modal-despesa [data-on-click="fecharModal()"]').first().click();
    // FIN-PRE-PRODUCAO-1: "A partir de documento" lista os documentos do perfil (o Pessoal de A nao tem nenhum).
    await page.click('.btn-doc-atalho-despesa');
    await expect(page.locator('#doc-desp-lista')).toHaveText('Nenhum documento encontrado.');
    await abrirDespesas(page, '2029-08');
    expect(await nomes(page)).toEqual([]);
    expect(await resumo(page)).toEqual({ total: 'R$ 0,00', pendentes: 'R$ 0,00', pagas: 'R$ 0,00' });
});

test('perfil so de leitura: sem acoes na tela; escrita direta recebe 403', async ({ page }) => {
    registrarDialogos(page);
    await entrar(page, A);
    await abrirDespesas(page, '2026-11');
    await expect(page.locator('.btn-nova-despesa')).toBeVisible();  // Pessoal: A gerencia
    await trocarPerfil(page, 'Empresa');
    await expect(page.locator('.btn-nova-despesa')).toBeHidden();
    const empresa = await perfilAtivoId(page);
    const contaId = Number(await page.locator('#despesas-lista .despesa-card', { hasText: 'Contador 11/2026' }).getAttribute('data-despesa-id'));
    const dados = { nome: 'Invasao', valor: '1.00', categoria_id: 1, data_vencimento: '2029-01-10' };
    const status = [
        (await chamarRpc(page, 'criar_despesa', { p_perfil_id: empresa, p_dados: dados, p_chave: crypto.randomUUID() })).status,
        (await chamarRpc(page, 'criar_despesa', { p_perfil_id: Number(ID_PERFIL_B), p_dados: dados, p_chave: crypto.randomUUID() })).status,
        (await chamarRpc(page, 'excluir_despesa', { p_perfil_id: empresa, p_conta_id: contaId, p_versao: 'x' })).status,
        (await chamarRpc(page, 'pagar_despesa', { p_perfil_id: empresa, p_conta_id: contaId, p_chave: crypto.randomUUID(), p_dados: {} })).status,
    ];
    expect(status).toEqual([403, 403, 403, 403]);
    await abrirDespesas(page, '2026-11');
    expect(await nomes(page)).toEqual(['Fatura Cartao Empresa - 11/2026', 'Contador 11/2026']);  // nada mudou
});
