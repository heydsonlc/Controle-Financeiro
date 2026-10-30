// FIN-RECORRENCIA-1 — contas recorrentes e faturas geradas ao abrir Despesas (FIN-RECORRENCIAS-AUTOMATICAS-1).
// Dados FICTICIOS de tests/supabase_local.py (semear_recorrencia_e2e). Este arquivo GRAVA no
// banco descartavel: usa so meses de 2027 e roda depois dos outros (workers: 1, ordem alfabetica).
import { expect, test } from '@playwright/test';

import {
    chamarRpc, despesa, esperarMes, estornar, nomes, pagar, perfilAtivoId, preencherDespesa, registrarDialogos, salvarDespesa,
    trocarCompetencia,
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

// FIN-RECORRENCIAS-AUTOMATICAS-1: como no Flask, abrir a competencia gera, sem confirmacao, o que falta ate o mes
// seguinte (lacunas incluidas), pelo motor do banco. Como abrir um mes distante completa todas as lacunas, o cenario
// usa a propria recorrencia (Perfil B, gerador novo), em 2040, meses que nenhum outro spec abre.
const AUTO = 'Academia Auto';  // nome que nenhum filtro dos outros specs alcanca
const contasDoMes = async (page, mes) => (await chamarRpc(page, 'contas_do_mes', {
    p_perfil_id: await perfilAtivoId(page), p_mes: `${mes}-01` })).corpo;
const previaDoMes = async (page, mes) => (await chamarRpc(page, 'previa_geracao', {
    p_perfil_id: await perfilAtivoId(page), p_mes: `${mes}-01` })).corpo;
const resultado = (page) => page.locator('#geracao-resultado');
const doItem = async (page, mes) => (await contasDoMes(page, mes)).filter((c) => c.nome.startsWith(AUTO));
const faturasB = async (page, mes) => (await contasDoMes(page, mes)).filter((c) => c.grupo === 'FATURA' && c.cartao_nome === 'Cartao B');
const brl = (v) => `R$ ${v.toFixed(2).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, '.')}`;

test('abrir Despesas gera ate o mes seguinte, sem botao; reabrir, recarregar e trocar a competencia nao duplicam', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirMes(page, '2040-03');  // as faturas de 03 e 04/2040 ja sao geradas aqui
    await page.click('.btn-nova-despesa');
    await preencherDespesa(page, { nome: AUTO, valor: '120', categoria: 'Moradia', vencimento: '2040-01-31',
        recorrente: true, tipo: 'mensal' });
    await salvarDespesa(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Recorrência cadastrada. As contas são geradas automaticamente ao abrir a competência.');
    // A lista recarregada gera 01 a 04/2040 (lacunas ate o mes seguinte), sem confirmacao.
    await expect(resultado(page)).toHaveText('4 lançamentos recorrentes ou faturas gerados automaticamente até 04/2040.');
    await expect(page.locator('#gerar-contas')).toHaveCount(0);
    await expect(page.locator('#aviso-geracao')).toBeHidden();
    await expect(despesa(page, AUTO).locator('.despesa-cell-vencimento')).toHaveText('31/03/2040');
    await expect(despesa(page, 'Cartao B').locator('.despesa-cell-vencimento')).toHaveText('31/03/2040');
    for (const mes of ['2040-01', '2040-02', '2040-03', '2040-04']) expect(await doItem(page, mes), mes).toHaveLength(1);
    for (const mes of ['2040-03', '2040-04']) expect(await faturasB(page, mes), mes).toHaveLength(1);
    expect(await faturasB(page, '2040-02')).toHaveLength(0);  // fatura: so o mes e o seguinte, como no Flask
    expect(await doItem(page, '2040-05')).toHaveLength(0);    // nada alem do mes seguinte
    expect((await previaDoMes(page, '2040-03')).a_gerar).toBe(0);
    // Cards ja com o que foi gerado.
    const total = (await contasDoMes(page, '2040-03')).reduce((s, c) => s + Number(c.valor), 0);
    await expect(page.locator('#total-geral')).toHaveText(brl(total));

    // Recarregar a pagina: tudo reconhecido como existente.
    await page.reload();
    await esperarMes(page, '2040-03');
    await expect(resultado(page)).toBeHidden();
    await expect(despesa(page, AUTO)).toHaveCount(1);
    await expect(despesa(page, 'Cartao B')).toHaveCount(1);

    // Abril (dia 31 vira 30): completa maio.
    await abrirMes(page, '2040-04');
    await expect(resultado(page)).toHaveText(/gerados automaticamente até 05\/2040\.$/);
    await expect(despesa(page, AUTO).locator('.despesa-cell-vencimento')).toHaveText('30/04/2040');
    await expect(despesa(page, AUTO).locator('.status-badge')).toHaveText('Pendente');

    // Troca pelo filtro da propria tela (sem recarregar): maio completa junho.
    await trocarCompetencia(page, '2040-05');
    await expect(resultado(page)).toHaveText(/gerados automaticamente até 06\/2040\.$/);
    await expect(despesa(page, AUTO).locator('.despesa-cell-vencimento')).toHaveText('31/05/2040');

    // De volta a marco: nada novo, nada duplicado.
    await trocarCompetencia(page, '2040-03');
    await expect(resultado(page)).toBeHidden();
    for (const mes of ['2040-01', '2040-02', '2040-03', '2040-04', '2040-05', '2040-06']) {
        expect(await doItem(page, mes), mes).toHaveLength(1);
    }
    for (const mes of ['2040-03', '2040-04', '2040-05', '2040-06']) expect(await faturasB(page, mes), mes).toHaveLength(1);
});

test('conta paga continua paga e conta excluida nao volta ao reabrir', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirMes(page, '2040-02');
    await pagar(page, AUTO, { data: '2040-02-28' });
    await expect.poll(() => dialogos.at(-1)).toMatch(/^Despesa paga: R\$\s120,00 debitados de Conta Perfil B\./);
    await abrirMes(page, '2040-03');  // o plano de marco cobre fevereiro
    await abrirMes(page, '2040-02');
    await expect(despesa(page, AUTO)).toHaveCount(1);
    await expect(despesa(page, AUTO).locator('.status-badge')).toHaveText('Pago');
    await expect(despesa(page, AUTO).locator('.despesa-cell-valor')).toHaveText('R$ 120,00');
    // Devolve a "Conta Perfil B" ao saldo de partida (os specs compartilham o banco descartavel).
    await estornar(page, AUTO, 'Estorno do teste de geracao automatica', '2040-02-29');
    await expect.poll(() => dialogos.at(-1)).toBe('Pagamento estornado com sucesso.');

    // Excluir so a de janeiro: a competencia fica dispensada e nenhuma abertura a recria.
    await abrirMes(page, '2040-01');
    await despesa(page, AUTO).locator('[data-on-click^="editarDespesa"]').click();
    await page.click('#btn-deletar-modal');
    await page.locator('#modal-tipo-exclusao button', { hasText: 'apenas esta' }).click();
    await expect.poll(() => dialogos.at(-1)).toBe('Despesa excluída com sucesso!');
    for (const mes of ['2040-01', '2040-02', '2040-01']) await abrirMes(page, mes);
    await expect(despesa(page, AUTO)).toHaveCount(0);
    await expect(resultado(page)).toBeHidden();
    expect(await doItem(page, '2040-01')).toHaveLength(0);
    expect((await previaDoMes(page, '2040-01')).dispensados.filter((d) => d.nome === AUTO)
        .map((d) => [d.competencia, d.motivo])).toEqual([['2040-01-01', 'Conta excluida pelo usuario']]);
});

test('falha na geracao: aviso objetivo, lista existente mantida; recarregar gera', async ({ page }) => {
    await entrar(page, B);
    await page.route('**/rest/v1/rpc/gerar_mes', (rota) => rota.abort('failed'));
    await abrirMes(page, '2040-06');  // a conta e a fatura de 06 ja existem; faltam as de 07/2040
    await expect(page.locator('#aviso-texto')).toHaveText(/^Não foi possível gerar as recorrências deste mês agora/);
    await expect(page.locator('#geracao-acoes')).toContainText('Recarregue a página para tentar de novo.');
    await expect(despesa(page, AUTO).locator('.despesa-cell-vencimento')).toHaveText('30/06/2040');
    await expect(despesa(page, 'Cartao B')).toHaveCount(1);
    expect((await previaDoMes(page, '2040-06')).a_gerar).toBeGreaterThan(0);  // nada gravado
    expect(await doItem(page, '2040-07')).toHaveLength(0);

    await page.unroute('**/rest/v1/rpc/gerar_mes');
    await page.reload();
    await esperarMes(page, '2040-06');
    await expect(resultado(page)).toHaveText(/gerados automaticamente até 07\/2040\.$/);
    await expect(page.locator('#aviso-geracao')).toBeHidden();
    expect(await doItem(page, '2040-07')).toHaveLength(1);
});

test('duas abas abrindo a mesma competencia ao mesmo tempo: uma geracao so', async ({ page }) => {
    await entrar(page, B);
    const outra = await page.context().newPage();
    await Promise.all([abrirMes(page, '2040-10'), abrirMes(outra, '2040-10')]);
    for (const mes of ['2040-08', '2040-09', '2040-10', '2040-11']) expect(await doItem(page, mes), mes).toHaveLength(1);
    for (const mes of ['2040-10', '2040-11']) expect(await faturasB(page, mes), mes).toHaveLength(1);
    expect((await previaDoMes(page, '2040-10')).a_gerar).toBe(0);
    await outra.close();
});

test('resposta atrasada de outra competencia nao substitui a selecionada', async ({ page }) => {
    await entrar(page, B);
    await abrirMes(page, '2040-03');
    // A leitura de abril demora; o usuario ja escolheu maio.
    await page.route('**/rest/v1/rpc/contas_do_mes', async (rota) => {
        if ((rota.request().postData() || '').includes('2040-04-01')) await new Promise((r) => setTimeout(r, 1500));
        await rota.continue();
    });
    await page.fill('#filtro-competencia', '04/2040');
    await page.locator('#filtro-competencia').dispatchEvent('change');
    await page.fill('#filtro-competencia', '05/2040');
    await page.locator('#filtro-competencia').dispatchEvent('change');
    await esperarMes(page, '2040-05');
    await page.waitForTimeout(2000);
    await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', '05/2040');
    await expect(despesa(page, AUTO).locator('.despesa-cell-vencimento')).toHaveText('31/05/2040');
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
    await expect(page.locator('#geracao-acoes')).toContainText('A geração de recorrências deste perfil ainda não está habilitada no novo aplicativo.');
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
    await expect.poll(() => dialogos.at(-1)).toBe('Recorrência cadastrada. As contas são geradas automaticamente ao abrir a competência.');
    // A tela recarrega a lista depois de salvar: a geracao automatica (o mesmo motor) cria marco e abril.
    await expect(page.locator('#geracao-resultado')).toContainText('gerados automaticamente até 04/2029');
    for (const mes of ['2029-03', '2029-04']) {
        expect((await contasDoMes(page, mes)).filter((c) => c.nome.startsWith('Escola B')), mes).toHaveLength(1);
    }
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
    await expect(page.locator('#gerar-contas')).toHaveCount(0);

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
