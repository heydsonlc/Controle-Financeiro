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
    await expect(page.locator('#recorrencias-aviso-consorcios')).toContainText('Consórcios: só consulta');
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

    // Pedidos que o novo aplicativo ainda nao atende: recusados, nada e gravado.
    await preencher(page, { nome: NOME, valor: '99.90', vencimento: '2031-01-10', frequencia: 'semanal', dia: 1 });
    await salvar(page);
    await expect.poll(() => dialogos.at(-1)).toMatch(/^Semanal e a cada 2 semanas: o novo aplicativo ainda não gera/);
    await page.selectOption('#frequencia', 'mensal');
    await page.selectOption('#meio-pagamento', 'cartao');
    await salvar(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Selecione o cartão da recorrência.');  // FIN-FIDELIDADE-CARTOES-2: cartao obrigatorio
    await expect(page.locator('#recorrencias-lista .recorrencias-row')).toHaveCount(total);

    await preencher(page, { categoria: false, meio: 'boleto', observacoes: 'Fibra' });
    await salvar(page);
    await expect(page.locator('#recorrencias-resultado')).toContainText('Recorrência criada.');
    await expect(page.locator('#recorrencias-resultado')).toContainText('Gerar contas');
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

    // Integracao: a geracao e explicita, em Despesas.
    await abrirDespesas(page, '2031-01');
    await expect(page.locator('#aviso-geracao')).not.toContainText('Cartao marcado como recorrencia');
    if (await page.locator('#geracao-acoes summary').count()) {
        await page.locator('#geracao-acoes summary').click();
        await expect(page.locator('#geracao-acoes .geracao-lista')).not.toContainText('Cartao Rec (tela)');
    }
    await expect(despesa(page, NOME)).toHaveCount(0);
    await page.click('#gerar-contas');
    const painel = page.locator('#geracao-confirmacao');
    await expect(painel.locator('.geracao-lista li', { hasText: NOME }).first()).toContainText('01/2031 · Internet B (tela) · Conta · 10/01/2031 · R$ 109,90');
    await painel.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.locator('#geracao-resultado')).toContainText('Geração concluída');
    const gerada = despesa(page, NOME);
    await expect(gerada.locator('.despesa-cell-valor')).toHaveText('R$ 109,90');
    await expect(gerada.locator('.despesa-cell-vencimento')).toHaveText('10/01/2031');
    await expect(gerada.locator('.despesa-cell-detalhe')).toHaveText('Fibra');  // observacoes da recorrencia
    await expect(gerada.locator('.despesa-cell-forma-pagamento')).toContainText(/pix/i);
    expect(await page.locator('.despesas-grupo-titulo').allTextContents()).toContain('DESPESAS RECORRENTES');
    // Sem duplicidade: reabrir o mes nao oferece de novo a mesma conta.
    await abrirDespesas(page, '2031-01');
    await expect(despesa(page, NOME)).toHaveCount(1);
    if (await page.locator('#gerar-contas').count()) {
        await page.click('#gerar-contas');
        await expect(page.locator('#geracao-confirmacao .geracao-lista li', { hasText: '01/2031 · Internet B (tela)' })).toHaveCount(0);
    }
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
    await expect.poll(() => dialogos.at(-1)).toBe('Vencimento e frequência só mudam quando o novo aplicativo gera este perfil.');
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

    await abrirDespesas(page, '2032-03');
    await page.click('#gerar-contas');
    const painel = page.locator('#geracao-confirmacao');
    await expect(painel.locator('.geracao-lista li', { hasText: 'Musica no cartao (tela)' }).first()).toContainText('03/2032');
    await painel.getByRole('button', { name: 'Confirmar' }).click();
    await expect(page.locator('#geracao-resultado')).toContainText('Geração concluída');
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

    // Limpeza do cenario: inativa a recorrencia e o cartao (compras e faturas continuam registradas).
    const recs = await chamarRpc(page, 'recorrencias_do_perfil', { p_perfil_id: perfil });
    const rec = recs.corpo.find((r) => r.nome === 'Musica no cartao (tela)');
    expect((await chamarRpc(page, 'definir_situacao_recorrencia_cartao', { p_perfil_id: perfil, p_item_id: rec.id, p_versao: rec.versao,
        p_ativo: false })).status).toBe(200);
    const cartoes = await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil });
    const cartao = cartoes.corpo.find((c) => c.id === criado.corpo.cartao_id);
    expect((await chamarRpc(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: cartao.id, p_versao: cartao.versao })).status).toBe(200);
});
