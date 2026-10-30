// FIN-FIDELIDADE-PATRIMONIO-1 / FIN-PATRIMONIO-2 — tela original de Patrimonio do Flask (frontend/templates/patrimonio.html)
// sobre o Supabase. Dados FICTICIOS (tests/supabase_local.py, semear_patrimonio_e2e): caixinhas e uma transferencia do
// "Perfil B" (novo aplicativo) e bens do perfil Empresa (ainda no Flask). No Perfil B a escrita e feita pela tela original
// (caixinha, transferencia, exclusao que desfaz os saldos, inativacao); no fim o cenario volta ao total de partida.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';
import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
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

test('caixinhas e transferencias pela tela original no Perfil B: criar, transferir, desfazer e inativar', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await page.goto('/patrimonio.html');
    await expect(page.locator('.patrimonio-aviso-fase')).toContainText('gravados pelo novo aplicativo');
    await expect(page.locator('#patrimonio-pessoal')).toBeVisible();
    await expect(page.locator('#caixinhas-lista')).toContainText('Reserva E2E (ficticia)');
    await expect(page.locator('#caixinhas-lista')).toContainText('Viagem E2E (ficticia)');
    await expect(page.locator('#transferencias-lista')).toContainText('Reserva E2E (ficticia)');
    const perfil = await perfilAtivoId(page);
    const contas = async () => (await chamarRpc(page, 'patrimonio_contas_tela', { p_perfil_id: perfil, p_ativo: null })).corpo;
    const saldo = async (nome) => (await contas()).data.find((c) => c.nome === nome)?.saldo_atual;
    expect((await contas()).total).toBe(2);
    const reserva = await saldo('Reserva E2E (ficticia)');

    // Nova caixinha pelo modal original.
    await page.click('#btn-nova-caixinha');
    await page.fill('#conta-nome', 'Nova E2E (ficticia)');
    await page.fill('#conta-saldo-inicial', '100,00');
    await page.locator('#form-conta button[type=submit]').click();
    await expect.poll(() => dialogos.at(-1)).toBe('Conta criada com sucesso');
    await expect(page.locator('#caixinhas-lista')).toContainText('Nova E2E (ficticia)');
    expect(await saldo('Nova E2E (ficticia)')).toBe(100);

    // Transferencia: sai da Reserva e entra na nova.
    await page.click('#btn-nova-transferencia');
    const idDe = async (nome) => String((await contas()).data.find((c) => c.nome === nome).id);
    await page.selectOption('#transf-origem', await idDe('Reserva E2E (ficticia)'));
    await page.selectOption('#transf-destino', await idDe('Nova E2E (ficticia)'));
    await page.fill('#transf-valor', '50,00');
    await page.locator('#form-transferencia button[type=submit]').click();
    await expect.poll(() => dialogos.at(-1)).toBe('Transferência criada com sucesso');
    expect([await saldo('Reserva E2E (ficticia)'), await saldo('Nova E2E (ficticia)')]).toEqual([reserva - 50, 150]);

    // Saldo insuficiente: recusado, nada muda.
    const r = await page.evaluate(async () => (await fetch('/api/patrimonio/transferencias', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conta_origem_id: 0, conta_destino_id: 1, valor: 1, data_transferencia: '2033-02-01' }),
    })).json());
    expect(r.success).toBe(false);

    // Excluir a transferencia desfaz os saldos; inativar a caixinha a tira do total.
    const lista = (await chamarRpc(page, 'patrimonio_transferencias_tela', { p_perfil_id: perfil, p_data_inicio: null,
        p_data_fim: null, p_conta_id: null, p_id: null })).corpo;
    const nova = lista.find((t) => t.conta_destino_nome === 'Nova E2E (ficticia)');
    await page.getByRole('button', { name: 'Transferências', exact: true }).click();  // aba da lista
    await page.locator(`[data-on-click="deletarTransferencia(${nova.id})"]`).click();
    await expect.poll(() => dialogos.at(-1)).toBe('Transferência deletada e saldos revertidos');
    expect([await saldo('Reserva E2E (ficticia)'), await saldo('Nova E2E (ficticia)')]).toEqual([reserva, 100]);
    const id = (await contas()).data.find((c) => c.nome === 'Nova E2E (ficticia)').id;
    await page.getByRole('button', { name: 'Caixinhas', exact: true }).click();
    await page.locator(`[data-on-click="inativarConta(${id})"]`).click();
    await expect.poll(() => dialogos.at(-1)).toBe('Caixinha inativada');
    expect((await contas()).total).toBe(2);
});

test('perfil Empresa mostra os bens, o resumo e a imagem do sistema; outro titular nao ve as caixinhas', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/patrimonio.html');
    await expect(page.locator('#caixinhas-lista')).not.toContainText('Reserva E2E (ficticia)');
    // Pessoal ainda no Flask: a escrita e recusada sem gravar (escritor unico).
    const r = await page.evaluate(async () => (await fetch('/api/patrimonio/contas', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nome: 'Nao grava', saldo_inicial: 1 }),
    })).json());
    expect(r).toEqual({ success: false, error: expect.stringContaining('ainda não está habilitado para gravação') });
    await trocarPerfil(page, 'Empresa');
    await page.goto('/patrimonio.html');
    await expect(page.locator('#patrimonio-empresarial')).toBeVisible();
    await expect(page.locator('#bens-tabela-corpo')).toContainText('Notebook E2E (ficticio)');
    await expect(page.locator('#bens-tabela-corpo')).toContainText('Cadeira E2E (ficticia)');
    await expect(page.locator('#bens-pendencias')).toContainText('Notebook E2E (ficticio)');
    const imagem = page.locator('#bens-tabela-corpo img[src$="Patrimonio_notebook.jpg"]');
    if (await imagem.count()) expect(await imagem.first().evaluate((img) => img.complete && img.naturalWidth > 0)).toBe(true);

    // FIN-RELATORIOS-CONFIG-1: Excel e PDF dos bens gerados no navegador (conteudo conferido com o Flask nos testes Python).
    for (const [botao, extensao, assinatura] of [['#btn-exportar-bens-excel', 'xlsx', 'PK'], ['#btn-exportar-bens-pdf', 'pdf', '%PDF']]) {
        const [download] = await Promise.all([page.waitForEvent('download'), page.click(botao)]);
        expect(download.suggestedFilename()).toBe(`Bens_Patrimoniais_Empresa_${new Date().getFullYear()}.${extensao}`);
        const fluxo = await download.createReadStream();
        const partes = [];
        for await (const parte of fluxo) partes.push(parte);
        expect(Buffer.concat(partes).subarray(0, assinatura.length).toString('latin1')).toBe(assinatura);
    }
});
