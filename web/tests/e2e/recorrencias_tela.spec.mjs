// FIN-FIDELIDADE-RECORRENCIAS-1 — tela original de Recorrencias do Flask sobre o Supabase, e a integracao com Despesas.
// Dados FICTICIOS (tests/supabase_local.py). Escrita so no "Perfil B" (novo gerador), em 2031; o pagamento feito
// para conferir a preservacao e estornado no fim (a "Conta Perfil B" volta ao saldo de partida).
import { expect, test } from '@playwright/test';

import {
    abrirDespesas, chamarRpc, despesa, estornar, pagar, perfilAtivoId, registrarDialogos,
} from './despesas.mjs';
import { itemDoMenu, trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const NOME = 'Internet B (tela)';

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

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', /\d{2}\/\d{4}/);
    await page.waitForLoadState('networkidle');
}

async function abrirRecorrencias(page) {
    await page.goto('/recorrencias.html');
    await expect(page.locator('#recorrencias-total')).toHaveText(/cadastros? no total/);
}

const linha = (page, nome) => page.locator('#recorrencias-lista .recorrencias-row', { has: page.locator('strong', { hasText: nome }) });

async function preencher(page, d) {
    if (d.nome !== undefined) await page.fill('#nome', d.nome);
    if (d.valor !== undefined) await page.fill('#valor', String(d.valor));
    if (d.categoria !== false) {
        const categoria = await page.locator('#categoria-id option:not([value=""])').first().getAttribute('value');
        await page.selectOption('#categoria-id', categoria);
    }
    if (d.vencimento !== undefined) await page.fill('#data-vencimento', d.vencimento);
    if (d.frequencia) await page.selectOption('#frequencia', d.frequencia);
    if (d.dia !== undefined) await page.selectOption('#dia-semana', String(d.dia));
    if (d.meio !== undefined) await page.selectOption('#meio-pagamento', d.meio);
    if (d.observacoes !== undefined) await page.fill('#observacoes', d.observacoes);
}

const salvar = (page) => page.click('button[type="submit"][form="form-recorrencia"]');

test('tela original: menu, indicadores, lista, filtros e aviso de consorcios', async ({ page }) => {
    await entrar(page, B);
    await itemDoMenu(page, 'recorrencias').click();
    await page.waitForURL('**/recorrencias.html');
    await expect(page.locator('#recorrencias-total')).toHaveText(/cadastros? no total/);
    await expect(page.locator('.app-topbar-title')).toHaveText('Recorrencias');
    await expect(itemDoMenu(page, 'recorrencias')).toHaveClass(/active/);
    await expect(itemDoMenu(page, 'recorrencias').locator('.app-nav-status')).toHaveCount(0);  // ja migrada
    await expect(page.locator('.recorrencias-kpi-card')).toHaveCount(4);
    await expect(linha(page, 'Mensalidade B')).toContainText('Mensal');
    await expect(linha(page, 'Mensalidade B')).toContainText('R$ 120,00');
    await expect(page.locator('#recorrencias-aviso-consorcios')).toContainText('Parcelas pagas nunca são apagadas');
    await page.selectOption('#filtro-status', 'inativa');
    await expect(linha(page, 'Mensalidade B')).toHaveCount(0);
    await page.selectOption('#filtro-status', '');
    await page.fill('#filtro-busca', 'mensalidade');
    await expect(page.locator('#recorrencias-lista .recorrencias-row')).toHaveCount(1);
});

test('cadastrar, recusas sem gravar, editar e gerar em Despesas com nome, valor, vencimento e meio', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirRecorrencias(page);
    const total = await page.locator('#recorrencias-lista .recorrencias-row').count();

    // Pedidos que o novo aplicativo nao atende: recusados, nada e gravado. Semanal no cartao: o Flask so lanca compra
    // recorrente mensal ou anual (FIN-CATEGORIAS-RECORRENCIAS-2).
    await preencher(page, { nome: NOME, valor: '99.90', vencimento: '2031-01-10', frequencia: 'semanal', dia: 1, meio: 'cartao' });
    await salvar(page);
    await expect.poll(() => dialogos.at(-1)).toMatch(/^Semanal e a cada 2 semanas não valem no cartão/);
    await page.selectOption('#frequencia', 'mensal');
    await salvar(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Selecione o cartão da recorrência.');  // FIN-FIDELIDADE-CARTOES-2: cartao obrigatorio
    await expect(page.locator('#recorrencias-lista .recorrencias-row')).toHaveCount(total);

    await preencher(page, { categoria: false, meio: 'boleto', observacoes: 'Fibra' });
    await salvar(page);
    await expect(page.locator('#recorrencias-resultado')).toContainText('Recorrência criada.');
    await expect(page.locator('#recorrencias-resultado')).toContainText('geradas automaticamente ao abrir a competência em Despesas');
    await expect(linha(page, NOME)).toContainText('R$ 99,90');
    await expect(linha(page, NOME)).toContainText('10/01/2031');
    await expect(linha(page, NOME)).toContainText('Ativa');
    await expect(linha(page, NOME).locator('[title="boleto"]')).toHaveCount(1);

    await linha(page, NOME).locator('[data-on-click^="editarRecorrencia"]').click();
    await expect(page.locator('#form-titulo')).toHaveText('Editar recorrencia');
    await expect(page.locator('#valor')).toHaveValue('99.9');
    await expect(page.locator('#meio-pagamento')).toHaveValue('boleto');
    await expect(page.locator('#observacoes')).toHaveValue('Fibra');
    await page.fill('#valor', '109.90');
    await page.selectOption('#meio-pagamento', 'pix');
    await salvar(page);
    await expect(page.locator('#recorrencias-resultado')).toContainText('Recorrência atualizada.');
    await expect(linha(page, NOME)).toContainText('R$ 109,90');
    await expect(linha(page, NOME).locator('[title="pix"]')).toHaveCount(1);

    // O cadastro de cartao marca o proprio cartao como recorrente (como no Flask). FIN-FIDELIDADE-CARTOES-2 (R4): o
    // gerador nao o le mais como recorrencia (nem rejeitada); a fatura e gerada pela parte de cartoes.
    await page.goto('/cartoes.html');  // FIN-FIDELIDADE-CARTOES-1: tela original de Cartoes
    await page.click('#btn-novo-cartao');
    await page.fill('#cartao-nome', 'Cartao Rec (tela)');
    await page.fill('#cartao-dia-fechamento', '3');
    await page.fill('#cartao-dia-vencimento', '12');
    await page.click('#form-cartao button[type=submit]');
    await expect(page.locator('#lista-cartoes .cartao-list-item', { hasText: 'Cartao Rec (tela)' })).toBeVisible();
    const bruta = await chamarRpc(page, 'previa_geracao', { p_perfil_id: await perfilAtivoId(page), p_mes: '2031-01-01' });
    expect(bruta.corpo.rejeitados.filter((r) => r.nome === 'Cartao Rec (tela)')).toEqual([]);
    // So a fatura do cartao (parte de cartoes); o cartao nunca como recorrencia que gera conta.
    expect(bruta.corpo.itens.filter((r) => r.nome === 'Cartao Rec (tela)' && r.natureza !== 'FATURA')).toEqual([]);

    // Integracao: Despesas gera ao abrir a competencia, sem confirmacao (FIN-RECORRENCIAS-AUTOMATICAS-1).
    await abrirDespesas(page, '2031-01');
    await expect(page.locator('#gerar-contas')).toHaveCount(0);
    await expect(page.locator('#aviso-geracao')).not.toContainText('Cartao marcado como recorrencia');
    if (await page.locator('#geracao-acoes summary').count()) {
        await page.locator('#geracao-acoes summary').click();
        await expect(page.locator('#geracao-acoes .geracao-lista')).not.toContainText('Cartao Rec (tela)');
    }
    await expect(page.locator('#geracao-resultado')).toContainText('gerados automaticamente até 02/2031');
    const gerada = despesa(page, NOME);
    await expect(gerada.locator('.despesa-cell-valor')).toHaveText('R$ 109,90');
    await expect(gerada.locator('.despesa-cell-vencimento')).toHaveText('10/01/2031');
    await expect(gerada.locator('.despesa-cell-detalhe')).toHaveText('Fibra');  // observacoes da recorrencia
    await expect(gerada.locator('.despesa-cell-forma-pagamento')).toContainText(/pix/i);
    expect(await page.locator('.despesas-grupo-titulo').allTextContents()).toContain('DESPESAS RECORRENTES');
    // Sem duplicidade: reabrir o mes nao gera de novo a mesma conta (o plano a ve como existente).
    await abrirDespesas(page, '2031-01');
    await expect(despesa(page, NOME)).toHaveCount(1);
    const depois = await chamarRpc(page, 'previa_geracao', { p_perfil_id: await perfilAtivoId(page), p_mes: '2031-01-01' });
    expect(depois.corpo.itens.filter((i) => i.nome === NOME)).toEqual([]);
});

test('conta paga preservada quando a recorrencia muda; inativar e reativar', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirDespesas(page, '2031-01');
    await pagar(page, NOME, { data: '2031-01-10' });
    await expect.poll(() => dialogos.at(-1)).toMatch(/^Despesa paga: R\$\s109,90 debitados de Conta Perfil B\./);

    await abrirRecorrencias(page);
    await linha(page, NOME).locator('[data-on-click^="editarRecorrencia"]').click();
    await page.fill('#valor', '150');
    await salvar(page);
    await expect(linha(page, NOME)).toContainText('R$ 150,00');
    await abrirDespesas(page, '2031-01');
    await expect(despesa(page, NOME).locator('.status-badge')).toHaveText('Pago');
    await expect(despesa(page, NOME).locator('.despesa-cell-valor')).toHaveText('R$ 109,90');  // a conta paga nao muda

    await abrirRecorrencias(page);
    await linha(page, NOME).locator('[data-on-click^="inativarRecorrencia"]').click();
    await expect.poll(() => dialogos.at(-1)).toBe('Inativar recorrencia?');
    await expect(linha(page, NOME)).toContainText('Inativa');
    await expect(page.locator('#recorrencias-resultado')).toContainText('nenhuma conta nova será gerada');
    const previa = await chamarRpc(page, 'previa_geracao', { p_perfil_id: await perfilAtivoId(page), p_mes: '2031-03-01' });
    expect(previa.corpo.itens.map((i) => i.nome)).not.toContain(NOME);

    await linha(page, NOME).locator('[data-on-click^="editarRecorrencia"]').click();
    await expect(page.locator('#recorrencia-ativa')).not.toBeChecked();
    await page.check('#recorrencia-ativa');
    await salvar(page);
    await expect(linha(page, NOME)).toContainText('Ativa');
    const depois = await chamarRpc(page, 'previa_geracao', { p_perfil_id: await perfilAtivoId(page), p_mes: '2031-03-01' });
    expect(depois.corpo.itens.map((i) => i.nome)).toContain(NOME);

    // Devolve a "Conta Perfil B" ao saldo de partida (os specs compartilham o banco descartavel).
    await abrirDespesas(page, '2031-01');
    await estornar(page, NOME, 'Estorno do teste de recorrencias', '2031-01-11');
    await expect.poll(() => dialogos.at(-1)).toBe('Pagamento estornado com sucesso.');
});

test('perfil so de leitura: lista sem acoes; isolamento e escrita direta recusada', async ({ page }) => {
    registrarDialogos(page);
    await entrar(page, A);
    await abrirRecorrencias(page);
    await trocarPerfil(page, 'Empresa');
    await expect(page.locator('#recorrencias-total')).toHaveText(/cadastros? no total/);
    await expect(linha(page, 'Aluguel sala')).toBeVisible();
    await expect(page.locator('#btn-nova-recorrencia')).toBeHidden();
    await expect(page.locator('#secao-formulario')).toBeHidden();
    await expect(page.locator('.recorrencias-actions').first()).toBeHidden();
    await expect(page.getByText(NOME)).toHaveCount(0);  // recorrencia do Perfil B
    const empresa = await perfilAtivoId(page);
    const sala = (await chamarRpc(page, 'recorrencias_do_perfil', { p_perfil_id: empresa })).corpo.find((r) => r.nome === 'Aluguel sala');
    expect((await chamarRpc(page, 'inativar_recorrencia', { p_perfil_id: empresa, p_item_id: sala.id, p_versao: sala.versao })).status).toBe(403);
    expect((await chamarRpc(page, 'reativar_recorrencia', { p_perfil_id: empresa, p_item_id: sala.id, p_versao: sala.versao })).status).toBe(403);
    expect((await chamarRpc(page, 'recorrencias_do_perfil', { p_perfil_id: Number(process.env.CF_ID_PERFIL_B || '103') })).status).toBe(403);
});

test('perfil gerado pelo sistema atual: vencimento e frequencia nao mudam por aqui', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, A);
    await abrirRecorrencias(page);
    await linha(page, 'Seguro 2028').locator('[data-on-click^="editarRecorrencia"]').click();
    await page.fill('#data-vencimento', '2028-01-20');
    await salvar(page);
    // FIN-ESCRITOR-UNICO-FINAL-1: perfil no Flask nao muda nada por aqui (antes: so vencimento e frequencia).
    await expect.poll(() => dialogos.at(-1)).toBe('Este perfil ainda é administrado pelo sistema atual (Flask). Nada foi gravado.');
    await abrirRecorrencias(page);
    await expect(linha(page, 'Seguro 2028')).toContainText('10/01/2028');
});

// FIN-FIDELIDADE-CARTOES-2 (R2) — recorrencia no cartao pela tela original: cadastrar, gerar a compra em Despesas (na
// fatura do cartao), editar (vale para as proximas) e inativar. Perfil B, cartao criado aqui, em 2032; inativado no fim.
test('recorrencia no cartao: cadastrar, gerar a compra na fatura, editar e inativar', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    const perfil = await perfilAtivoId(page);
    const criado = await chamarRpc(page, 'criar_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(),
        p_dados: { nome: 'Cartao Recorrente (tela)', dia_fechamento: 3, dia_vencimento: 12 } });
    expect(criado.status).toBe(200);
    await abrirRecorrencias(page);
    await preencher(page, { nome: 'Musica no cartao (tela)', valor: '21.90', vencimento: '2032-03-12', meio: 'cartao' });
    await page.selectOption('#cartao-id', { label: 'Cartao Recorrente (tela)' });
    await salvar(page);
    await expect(page.locator('#recorrencias-resultado')).toContainText('Recorrência no cartão criada.');
    await expect(linha(page, 'Musica no cartao (tela)')).toContainText('R$ 21,90');

    // A compra recorrente entra na fatura ao abrir a competencia (FIN-RECORRENCIAS-AUTOMATICAS-1).
    await abrirDespesas(page, '2032-03');
    await expect(page.locator('#geracao-resultado')).toContainText('gerados automaticamente até 04/2032');
    await expect(despesa(page, 'Fatura Cartao Recorrente (tela) - 03/2032')).toBeVisible();
    await expect(despesa(page, 'Musica no cartao (tela)')).toHaveCount(0);  // compra na fatura, nao conta avulsa

    await abrirRecorrencias(page);
    await linha(page, 'Musica no cartao (tela)').locator('[data-on-click^="editarRecorrencia"]').click();
    await page.fill('#valor', '24.90');
    await salvar(page);
    await expect(page.locator('#recorrencias-resultado')).toContainText('Recorrência no cartão atualizada.');
    await linha(page, 'Musica no cartao (tela)').locator('[data-on-click^="editarRecorrencia"]').click();
    await page.selectOption('#meio-pagamento', 'boleto');
    await salvar(page);
    await expect.poll(() => dialogos.at(-1)).toMatch(/^Para trocar o cartão por outro meio de pagamento, inative/);
    const lista = await chamarRpc(page, 'compras_da_fatura', { p_perfil_id: perfil, p_cartao_id: criado.corpo.cartao_id, p_mes: '2032-03-01' });
    expect(lista.corpo.map((c) => [c.descricao, Number(c.valor), c.recorrente])).toEqual([['Musica no cartao (tela)', 21.9, true]]);
    // Reabrir o mes nao duplica a compra, e a ja gerada nao muda com o novo valor da recorrencia.
    await abrirDespesas(page, '2032-03');
    const reaberta = await chamarRpc(page, 'compras_da_fatura', { p_perfil_id: perfil, p_cartao_id: criado.corpo.cartao_id, p_mes: '2032-03-01' });
    expect(reaberta.corpo.map((c) => [c.descricao, Number(c.valor)])).toEqual([['Musica no cartao (tela)', 21.9]]);
    await expect(despesa(page, 'Fatura Cartao Recorrente (tela) - 03/2032')).toHaveCount(1);

    // Limpeza do cenario: inativa a recorrencia e o cartao (compras e faturas continuam registradas).
    const recs = await chamarRpc(page, 'recorrencias_do_perfil', { p_perfil_id: perfil });
    const rec = recs.corpo.find((r) => r.nome === 'Musica no cartao (tela)');
    expect((await chamarRpc(page, 'definir_situacao_recorrencia_cartao', { p_perfil_id: perfil, p_item_id: rec.id, p_versao: rec.versao,
        p_ativo: false })).status).toBe(200);
    const cartoes = await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil });
    const cartao = cartoes.corpo.find((c) => c.id === criado.corpo.cartao_id);
    expect((await chamarRpc(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: cartao.id, p_versao: cartao.versao })).status).toBe(200);
});

// FIN-CATEGORIAS-RECORRENCIAS-2 (R1): a cada 2 semanas pela tela original (Perfil B, 04/2032, depois do cenario do
// cartao): uma conta por ocorrencia, na segunda-feira, com a descricao do Flask; sem duplicar ao reabrir; inativada no fim.
test('a cada 2 semanas: cadastrar, gerar uma conta por ocorrencia em Despesas e inativar', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    const nome = 'Diarista B (tela)';
    await entrar(page, B);
    await abrirRecorrencias(page);
    await preencher(page, { nome, valor: '80', vencimento: '2032-04-01', frequencia: 'quinzenal', dia: 1, meio: 'pix' });
    await salvar(page);
    await expect(page.locator('#recorrencias-resultado')).toContainText('Recorrência criada.');
    await expect(linha(page, nome)).toContainText('A cada 2 semanas');
    await expect(linha(page, nome)).toContainText('05/04/2032');  // primeira segunda-feira a partir de 01/04
    await linha(page, nome).locator('[data-on-click^="editarRecorrencia"]').click();
    await expect(page.locator('#frequencia')).toHaveValue('quinzenal');
    await expect(page.locator('#dia-semana')).toHaveValue('1');

    // Ao abrir a competencia: uma conta por ocorrencia ate o mes seguinte (FIN-RECORRENCIAS-AUTOMATICAS-1).
    await abrirDespesas(page, '2032-04');
    await expect(page.locator('#geracao-resultado')).toContainText('gerados automaticamente até 05/2032');
    // Como no Flask, as semanais aparecem agrupadas (um cartao com as ocorrencias do mes).
    await expect(despesa(page, `${nome} - 05/04`)).toHaveCount(1);
    const grupo = despesa(page, `${nome} - 19/04`);
    await expect(grupo.locator('.despesa-cell-vencimento', { hasText: '19/04/2032' })).toHaveCount(1);
    await expect(grupo.locator('.despesa-cell-vencimento', { hasText: '05/04/2032' })).toHaveCount(1);
    await expect(grupo.locator('.despesa-cell-vencimento', { hasText: '12/04/2032' })).toHaveCount(0);
    // Maio (gerado junto, mes seguinte): 03, 17 e 31/05.
    await abrirDespesas(page, '2032-05');
    const maio = despesa(page, `${nome} - 31/05`);
    for (const dia of ['03/05/2032', '17/05/2032', '31/05/2032']) {
        await expect(maio.locator('.despesa-cell-vencimento', { hasText: dia })).toHaveCount(1);
    }
    // Reabrir o mes nao gera de novo as mesmas ocorrencias.
    await abrirDespesas(page, '2032-04');
    await expect(despesa(page, `${nome} - 05/04`)).toHaveCount(1);
    await expect(despesa(page, `${nome} - 19/04`).locator('.despesa-cell-vencimento', { hasText: '05/04/2032' })).toHaveCount(1);

    await abrirRecorrencias(page);
    await linha(page, nome).locator('[data-on-click^="inativarRecorrencia"]').click();
    await expect.poll(() => dialogos.at(-1)).toBe('Inativar recorrencia?');
    await expect(linha(page, nome)).toContainText('Inativa');
});

// FIN-CONTRATOS-3: consorcio cadastrado pelo modal original (Perfil B, novo aplicativo), parcelas em Despesas e
// inativacao (as despesas pendentes saem; nada pago e apagado). Em 2034, longe dos outros cenarios.
test('consorcio: cadastrar pelo modal original, parcelas em Despesas e inativar', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirRecorrencias(page);
    await page.click('#btn-nova-recorrencia');
    await page.selectOption('#tipo-cadastro', 'consorcio');
    await expect(page.locator('#data-vencimento')).toBeVisible();  // Data inicial visivel no modo consorcio (defeito do Flask corrigido)
    await preencher(page, { nome: 'Consorcio Tela E2E', valor: 200, vencimento: '2034-05-05' });
    await page.fill('#numero-parcelas', '3');
    await salvar(page);
    await expect(linha(page, 'Consorcio Tela E2E')).toBeVisible();
    const perfil = await perfilAtivoId(page);
    const lista = (await chamarRpc(page, 'consorcios_tela', { p_perfil_id: perfil, p_id: null })).corpo;
    const contrato = lista.find((c) => c.nome === 'Consorcio Tela E2E');
    expect([contrato.numero_parcelas, contrato.valor_inicial, contrato.mes_inicio]).toEqual([3, 200, '2034-05-01']);

    await abrirDespesas(page, '2034-06');
    await expect(despesa(page, 'Consorcio Tela E2E - Parcela 2/3')).toBeVisible();

    await abrirRecorrencias(page);
    await linha(page, 'Consorcio Tela E2E').locator('[data-on-click^="inativarRecorrencia(\'consorcio\'"]').click();
    await expect.poll(() => dialogos.some((m) => /Inativar consorcio\?/.test(m))).toBe(true);
    await expect(linha(page, 'Consorcio Tela E2E')).toHaveCount(0);
    await abrirDespesas(page, '2034-06');
    await expect(despesa(page, 'Consorcio Tela E2E - Parcela 2/3')).toHaveCount(0);
});

// FIN-RECORRENCIAS-AUTOMATICAS-1: semanal (toda quarta-feira) gerada ao abrir Despesas, uma conta por ocorrencia ate o mes
// seguinte, sem duplicar ao reabrir. Perfil B, em 2036 (depois de todos os meses que os cenarios anteriores abrem).
test('semanal: abrir Despesas gera uma conta por ocorrencia ate o mes seguinte, sem duplicar', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    const nome = 'Feira B (tela)';
    await entrar(page, B);
    await abrirRecorrencias(page);
    await preencher(page, { nome, valor: '45', vencimento: '2036-03-01', frequencia: 'semanal', dia: 3, meio: 'pix' });
    await salvar(page);
    await expect(page.locator('#recorrencias-resultado')).toContainText('geradas automaticamente ao abrir a competência em Despesas');
    const perfil = await perfilAtivoId(page);
    const vencimentos = async (mes) => (await chamarRpc(page, 'contas_do_mes', { p_perfil_id: perfil, p_mes: `${mes}-01` }))
        .corpo.filter((c) => c.nome.startsWith(nome)).map((c) => c.data_vencimento).sort();
    expect(await vencimentos('2036-03')).toEqual([]);  // salvar nao gera conta

    await abrirDespesas(page, '2036-03');
    await expect(page.locator('#geracao-resultado')).toContainText('gerados automaticamente até 04/2036');
    expect(await vencimentos('2036-03')).toEqual(['2036-03-05', '2036-03-12', '2036-03-19', '2036-03-26']);
    expect(await vencimentos('2036-04')).toEqual(['2036-04-02', '2036-04-09', '2036-04-16', '2036-04-23', '2036-04-30']);
    expect(await vencimentos('2036-05')).toEqual([]);
    await expect(despesa(page, `${nome} - 26/03`).locator('.despesa-cell-vencimento', { hasText: '05/03/2036' })).toHaveCount(1);

    await abrirDespesas(page, '2036-03');  // reabrir: nada novo
    expect(await vencimentos('2036-03')).toHaveLength(4);
    await abrirDespesas(page, '2036-04');
    expect(await vencimentos('2036-03')).toHaveLength(4);
    expect(await vencimentos('2036-04')).toHaveLength(5);
    expect(await vencimentos('2036-05')).toEqual(['2036-05-07', '2036-05-14', '2036-05-21', '2036-05-28']);

    await abrirRecorrencias(page);
    await linha(page, nome).locator('[data-on-click^="inativarRecorrencia"]').click();
    await expect.poll(() => dialogos.at(-1)).toBe('Inativar recorrencia?');
    await expect(linha(page, nome)).toContainText('Inativa');
});
