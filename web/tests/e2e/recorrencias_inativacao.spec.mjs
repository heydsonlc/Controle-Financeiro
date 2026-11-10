// FIN-RECORRENCIAS-INATIVACAO-01 (P22) — inativar interrompe a recorrencia: previa (data de efeito, ocorrencias que
// deixam de ser exigiveis, valor e protegidas) e confirmacao; "Excluir esta e as futuras" em Despesas, inclusive numa
// recorrencia ja inativa (antes recusado com "A recorrencia nao pode ser inativada por aqui"); reativar pelo formulario
// sem restaurar em silencio. Dados FICTICIOS no "Perfil B" (novo gerador), em 2037, longe dos outros cenarios.
import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const EVIDENCIAS = process.env.CF_EVIDENCIAS_DIR;

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
    await page.fill('#email', B.email);
    await page.fill('#senha', B.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', /\d{2}\/\d{4}/);
    await page.waitForLoadState('networkidle');
}

async function abrirRecorrencias(page) {
    await page.goto('/recorrencias.html');
    await expect(page.locator('#recorrencias-total')).toHaveText(/cadastros? no total/);
    await page.selectOption('#filtro-status', '');
    await page.fill('#filtro-competencia', '');
}

const linha = (page, nome) => page.locator('#recorrencias-lista .recorrencias-row', { has: page.locator('strong', { hasText: nome }) });
const modal = (page) => page.locator('.cf-int-caixa');

async function criar(page, nome, vencimento, valor) {
    const perfil = await perfilAtivoId(page);
    const categorias = await chamarRpc(page, 'categorias_de_despesa', {});
    const r = await chamarRpc(page, 'criar_despesa', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
        nome, valor, categoria_id: categorias.corpo[0].id, data_vencimento: vencimento, recorrente: true, tipo_recorrencia: 'mensal' } });
    expect(r.status).toBe(200);
    return r.corpo.item_id;
}

async function recorrencia(page, id) {
    const lista = await chamarRpc(page, 'recorrencias_do_perfil', { p_perfil_id: await perfilAtivoId(page) });
    return lista.corpo.find((r) => r.id === id);
}

async function excluirFuturas(page, nome) {
    await despesa(page, nome).locator('[title="Editar"]').click();
    await page.locator('#btn-deletar-modal').click();
    const escolha = page.locator('#modal-tipo-exclusao');
    await expect(escolha).toBeVisible();
    const futuras = escolha.locator('[data-on-click="confirmarTipoExclusao(\'futuras\')"]');
    await expect(futuras).toBeEnabled();
    await futuras.click();
}

async function caberNaTela(page) {
    const caixa = await modal(page).boundingBox();
    const tela = page.viewportSize();
    expect(caixa.x).toBeGreaterThanOrEqual(0);
    expect(caixa.y).toBeGreaterThanOrEqual(0);
    expect(caixa.x + caixa.width).toBeLessThanOrEqual(tela.width);
    expect(caixa.y + caixa.height).toBeLessThanOrEqual(tela.height);
    const alturas = await modal(page).locator('.cf-int-rodape .cf-int-botao').evaluateAll((b) => b.map((x) => x.getBoundingClientRect().height));
    expect(new Set(alturas).size).toBe(1);  // botoes padronizados
}

for (const largura of [1366, 1920]) {
    test(`Recorrencias: inativar mostra o impacto e interrompe as futuras (${largura})`, async ({ page }) => {
        await page.setViewportSize({ width: largura, height: largura === 1366 ? 768 : 1080 });
        const nome = `Telefonia P22 ${largura}`;
        const ano = largura === 1366 ? 2037 : 2038;
        await entrar(page);
        const id = await criar(page, nome, `${ano}-03-10`, '55.00');
        await abrirDespesas(page, `${ano}-03`);  // gera 03 e 04
        await abrirDespesas(page, `${ano}-05`);  // gera 05 e 06
        await expect(despesa(page, nome)).toHaveCount(1);

        await abrirRecorrencias(page);
        await linha(page, nome).locator('[data-on-click^="inativarRecorrencia"]').click();
        await expect(modal(page).locator('h3')).toHaveText('Inativar recorrência');
        await expect(modal(page)).toContainText(nome);
        await expect(modal(page).locator('.cf-int-resumo')).toHaveText(/^4 ocorrência\(s\) deixam de ser exigíveis: R\$\s220,00$/);
        await expect(modal(page).locator('.cf-int-tabela tbody tr')).toHaveCount(4);
        await expect(modal(page).locator('.cf-int-opcao')).toContainText('Incluir a competência atual');
        await caberNaTela(page);
        if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/p22_inativar_${largura}.png` });
        // Cancelar nao grava nada
        await modal(page).locator('.cf-int-botao.secundario').click();
        await expect(page.locator('.cf-int-fundo')).toHaveCount(0);
        expect((await recorrencia(page, id)).ativo).toBe(true);

        await linha(page, nome).locator('[data-on-click^="inativarRecorrencia"]').click();
        await modal(page).locator('.cf-int-botao.perigo').click();
        await expect(page.locator('.cf-int-fundo')).toHaveCount(0);
        await expect(linha(page, nome)).toContainText('Inativa');
        await expect(page.locator('#recorrencias-resultado')).toContainText('4 ocorrência(s) deixaram de ser exigíveis');
        for (const m of ['03', '04', '05', '06']) {
            await abrirDespesas(page, `${ano}-${m}`);
            await expect(despesa(page, nome)).toHaveCount(0);
        }

        // Reativar pelo formulario: previa da retomada; as canceladas so voltam se pedido (aqui, nao).
        await abrirRecorrencias(page);
        await linha(page, nome).locator('[data-on-click^="editarRecorrencia"]').click();
        await page.check('#recorrencia-ativa');
        await page.click('button[type="submit"][form="form-recorrencia"]');
        await expect(modal(page).locator('h3')).toHaveText('Reativar recorrência');
        await expect(modal(page).locator('.cf-int-opcao')).toContainText('Restaurar as 4 ocorrência(s) canceladas pela inativação');
        await expect(modal(page).locator('.cf-int-opcao input')).not.toBeChecked();
        await caberNaTela(page);
        if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/p22_reativar_${largura}.png` });
        await modal(page).locator('.cf-int-botao.primario').click();
        await expect(page.locator('.cf-int-fundo')).toHaveCount(0);
        await expect(linha(page, nome)).toContainText('Ativa');
        await abrirDespesas(page, `${ano}-04`);
        await expect(despesa(page, nome)).toHaveCount(0);  // nao restaurada em silencio

        // Limpeza: inativa de novo (nada pendente fica para os outros specs).
        const r = await recorrencia(page, id);
        expect((await chamarRpc(page, 'interromper_recorrencia', { p_perfil_id: await perfilAtivoId(page), p_item_id: id,
            p_versao: r.versao, p_efeito: null, p_esperadas: null, p_conta_id: null })).status).toBe(200);
    });
}

test('Despesas: esta e as futuras numa recorrencia ativa e numa ja inativa', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await page.setViewportSize({ width: 1366, height: 768 });
    await entrar(page);
    const perfil = await perfilAtivoId(page);

    // Ativa: 07 e 08/2037 geradas; a partir de 07 tudo sai e a recorrencia fica inativa.
    const ativa = 'Academia P22';
    const idAtiva = await criar(page, ativa, '2037-07-12', '90.00');
    await abrirDespesas(page, '2037-07');
    await excluirFuturas(page, ativa);
    await expect(modal(page).locator('h3')).toHaveText('Excluir esta e as futuras');
    await expect(modal(page).locator('.cf-int-resumo')).toHaveText(/^2 ocorrência\(s\) deixam de ser exigíveis: R\$\s180,00$/);
    await caberNaTela(page);
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/p22_despesas_futuras_1366.png` });
    await modal(page).locator('.cf-int-botao.perigo').click();
    await expect.poll(() => dialogos.at(-1)).toBe('Recorrência interrompida: 2 ocorrência(s) deixaram de ser exigíveis.');
    await expect(despesa(page, ativa)).toHaveCount(0);
    await abrirDespesas(page, '2037-08');
    await expect(despesa(page, ativa)).toHaveCount(0);
    expect((await recorrencia(page, idAtiva)).ativo).toBe(false);

    // Ja inativa com uma futura pendente (o caso de Telefonia e USP): antes, "esta e as futuras" era sempre recusada.
    const inativa = 'USP P22';
    const idInativa = await criar(page, inativa, '2037-09-05', '508.10');
    await abrirDespesas(page, '2037-09');  // gera 09 e 10
    const r = await recorrencia(page, idInativa);
    expect((await chamarRpc(page, 'interromper_recorrencia', { p_perfil_id: perfil, p_item_id: idInativa, p_versao: r.versao,
        p_efeito: '2037-10-01', p_esperadas: 1, p_conta_id: null })).status).toBe(200);  // inativa; 09 fica pendente
    await abrirDespesas(page, '2037-09');
    await expect(despesa(page, inativa)).toHaveCount(1);
    await excluirFuturas(page, inativa);
    await expect(modal(page).locator('.cf-int-resumo')).toHaveText(/^1 ocorrência\(s\) deixam de ser exigíveis: R\$\s508,10$/);
    await modal(page).locator('.cf-int-botao.perigo').click();
    await expect.poll(() => dialogos.at(-1)).toBe('Recorrência interrompida: 1 ocorrência(s) deixaram de ser exigíveis.');
    await expect(despesa(page, inativa)).toHaveCount(0);
    expect(dialogos.some((m) => /não pode ser inativada por aqui/.test(m))).toBe(false);
});
