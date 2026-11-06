// FIN-FIDELIDADE-CARTOES-1 — tela original de Cartoes do Flask (frontend/templates/cartoes.html) sobre o Supabase.
// Substitui cartoes.spec, fechamento.spec e pagamento.spec (tela anterior do novo aplicativo). Dados FICTICIOS
// (tests/supabase_local.py: semear_contas e semear_cartoes_e2e). Leituras com o usuario A (gestor do Pessoal, LEITOR
// da Empresa); toda escrita com o usuario B no "Perfil B": cria o proprio cartao, grava em 2031-2034 e o inativa no fim.
import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, esperarMes, estornar, pagar, perfilAtivoId, registrarDialogos } from './despesas.mjs';
import { irPeloMenu, itemDoMenu, trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };

test.use({ viewport: { width: 1366, height: 900 } });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
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
}

async function abrirCartoes(page) {
    await page.goto('/cartoes.html');
    await expect(page.locator('#lista-cartoes .loading')).toHaveCount(0);
}

const itemCartao = (page, nome) => page.locator('#lista-cartoes .cartao-list-item', { hasText: nome });
const detalhe = (page) => page.locator('#cartao-detalhe');
const toast = (page) => page.locator('#notificacao-toast');
const lancamento = (page, nome) => page.locator('.fatura-lancamento-row', { hasText: nome });
const grupo = (page, nome) => page.locator('.fatura-table-row', { hasText: nome });
const metrica = (page, rotulo) => page.locator('.fatura-metrics article', { hasText: rotulo }).locator('strong');

async function selecionar(page, nome) {
    await itemCartao(page, nome).click();
    await expect(itemCartao(page, nome)).toHaveClass(/selected/);
    await expect(detalhe(page).locator('.cartao-detail-header h2')).toHaveText(nome);
}

// Mes da fatura pelo campo original (input month + change) e espera o resumo do mes chegar.
async function mesDaFatura(page, mes) {
    const campo = page.locator('[data-action="alterar-mes-fatura"]');
    await campo.fill(mes);
    await campo.dispatchEvent('change');
    await expect(page.locator('.fatura-card-header p')).toHaveText(`Consumo agrupado por Categoria do Cartão em ${mes}.`);
}

async function novoCartao(page, c) {
    await page.click('#btn-novo-cartao');
    await expect(page.locator('#modal-cartao')).toHaveClass(/open/);
    await expect(page.locator('#modal-cartao-titulo')).toHaveText('Novo Cartão');
    await page.fill('#cartao-nome', c.nome);
    if (c.emissor) await page.fill('#cartao-descricao', c.emissor);
    await page.fill('#cartao-dia-fechamento', String(c.fechamento));
    await page.fill('#cartao-dia-vencimento', String(c.vencimento));
    if (c.limite) await page.fill('#cartao-limite', c.limite);
    if (c.confirmado) await page.check('#cartao-fechamento-confirmado');
    await page.click('#form-cartao button[type=submit]');
    await expect(toast(page)).toHaveText('Cartão criado.');
    await expect(itemCartao(page, c.nome)).toBeVisible();
}

async function inativarCartao(page, nome) {
    await selecionar(page, nome);
    await detalhe(page).locator('[data-action="editar-cartao"]').click();
    await page.click('#btn-inativar-cartao');
    await expect(toast(page)).toHaveText('Cartão inativado.');
    await expect(itemCartao(page, nome)).toHaveCount(0);
}

// Compra pela funcao do banco (a tela de compra nova e Lancamentos: cenario do fechamento abaixo e lancamentos_tela.spec).
// c: { cartao, descricao, valor, parcelas, data, mes }
async function novaCompra(page, c) {
    const perfil = await perfilAtivoId(page);
    const cartao = (await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil })).corpo.find((x) => x.nome === c.cartao);
    const categoria = (await chamarRpc(page, 'categorias_de_despesa', {})).corpo.find((x) => x.nome.startsWith('Moradia'));
    const r = await chamarRpc(page, 'criar_compra', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
        cartao_id: cartao.id, descricao: c.descricao, valor: c.valor, total_parcelas: c.parcelas || 1, data_compra: c.data,
        mes_fatura: `${c.mes}-01`, categoria_id: categoria.id } });
    expect(r.status, c.descricao).toBe(200);
}

test('tela original pelo menu: cartoes, fatura por Categoria do Cartao e lancamentos (Pessoal)', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/contas.html?mes=2026-11');
    await esperarMes(page, '2026-11');
    await irPeloMenu(page, 'cartoes');
    await page.waitForURL(/cartoes\.html/);
    await expect(itemDoMenu(page, 'cartoes')).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('.cartoes-toolbar #btn-novo-cartao')).toBeVisible();
    await expect(page.locator('#lista-cartoes .cartao-list-main strong')).toHaveText(['Cartao Azul', 'Cartao Verde']);
    await expect(page.locator('#summary-cartoes-ativos')).toHaveText('2');
    // Limites de exemplo sem perfil (legado): o Flask lista so os do perfil, como aqui.
    await expect(page.locator('#summary-categorias-vinculadas')).toHaveText('0');
    await expect(detalhe(page).locator('.categorias-vinculadas-card')).toHaveCount(0);  // MVP-FIN-AJUSTES-01 (P10)
    await expect(detalhe(page).locator('[data-action="revelar-cvv"]')).toHaveCount(0);  // CVV nao e guardado

    await selecionar(page, 'Cartao Azul');
    await mesDaFatura(page, '2026-11');
    await expect(metrica(page, 'Total da fatura')).toHaveText('R$ 1.220,00');
    await expect(metrica(page, 'Limite total')).toHaveText('R$ 0,00');
    // FIN-CARTAO-DESPESAS-FIXAS-01: a parcela (sem Categoria do Cartao) fica no grupo proprio, fora das categorias.
    await expect(page.locator('.fatura-table-row .table-category')).toHaveText(['Mercado', 'Restaurantes', 'Combustivel', 'Compras parceladas']);
    await expect(grupo(page, 'Mercado').locator('.usage-cell strong')).toHaveText('R$ 500,00');
    await expect(grupo(page, 'Compras parceladas').locator('.fatura-row-warning')).toHaveText('Parcelas ja contratadas: nao consomem limite de Categoria do Cartao.');
    await expect(grupo(page, 'Compras parceladas').locator('.usage-cell strong')).toHaveText('R$ 200,00');
    await expect(page.locator('.fatura-lancamento-row')).toHaveCount(6);
    await expect(lancamento(page, 'Compra parcelada')).toContainText('2/3');
    await grupo(page, 'Restaurantes').locator('[data-action="ver-lancamentos-fatura"]').click();
    await expect(page.locator('.fatura-lancamento-row')).toHaveCount(1);
    await expect(page.locator('.fatura-lancamentos-header h4')).toHaveText('Lançamentos da categoria selecionada');

    // Pessoal segue no Flask (FIN-ESCRITOR-UNICO-FINAL-1): a exclusao e recusada pelo escritor unico, antes da regra da
    // fatura paga (que continua testada no Perfil B, na integracao com Despesas); a tela original mostra o erro.
    const dialogos = registrarDialogos(page);
    await selecionar(page, 'Cartao Verde');
    await mesDaFatura(page, '2026-11');
    await lancamento(page, 'Livraria').locator('[data-action="excluir-lancamento"]').click();
    await expect(toast(page)).toHaveText('Erro ao excluir lançamento: Este perfil ainda não está habilitado para gravação no novo aplicativo. Nada foi gravado.');
    expect(dialogos.at(-1)).toMatch(/^Excluir o lançamento "Livraria"\?/);
    await expect(page.locator('.fatura-lancamento-row')).toHaveCount(2);
});

test('cadastro, limites, compra, edicao de um lancamento, parcelas futuras, exclusao e inativacao', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirCartoes(page);
    await expect(itemCartao(page, 'Cartao Antigo')).toHaveCount(0);  // inativo: fora da tela (como o Flask)
    expect(await page.content()).not.toMatch(/5555|Cartao Antigo/);

    // Numero, validade e CVV: desativados (nunca digitados nem enviados).
    await page.click('#btn-novo-cartao');
    for (const id of ['#cartao-numero', '#cartao-data-validade', '#cartao-cvv']) await expect(page.locator(id)).toBeDisabled();
    await expect(page.locator('#btn-inativar-cartao')).toBeHidden();
    await page.locator('#modal-cartao [data-close-modal="modal-cartao"]').first().click();
    await novoCartao(page, { nome: 'Cartao Roxo', emissor: 'Banco Roxo S.A.', fechamento: 3, vencimento: 12, limite: '2500', confirmado: true });
    await expect(itemCartao(page, 'Cartao Roxo').locator('small').first()).toHaveText('Banco Roxo S.A. • **** ----');
    await selecionar(page, 'Cartao Roxo');
    await expect(detalhe(page).locator('.cartao-detail-identity p').nth(1)).toHaveText('Fecha dia 3 • vence dia 12 • compra no dia do fechamento vai para a próxima fatura');
    await expect(detalhe(page).locator('.status-atencao')).toHaveCount(0);

    // Editar: mudar um dia desfaz a confirmacao (o original desmarca; o banco tambem).
    await detalhe(page).locator('[data-action="editar-cartao"]').click();
    await expect(page.locator('#cartao-fechamento-confirmado')).toBeChecked();
    await expect(page.locator('#btn-inativar-cartao')).toBeVisible();
    await page.fill('#cartao-dia-vencimento', '10');
    await page.locator('#cartao-dia-vencimento').dispatchEvent('change');
    await expect(page.locator('#cartao-fechamento-confirmado')).not.toBeChecked();
    await page.click('#form-cartao button[type=submit]');
    await expect(toast(page)).toHaveText('Cartão atualizado.');
    await expect(detalhe(page).locator('.status-atencao')).toHaveText('Fechamento a confirmar');

    // Limite por Categoria do Cartao.
    await expect(detalhe(page).locator('.available-category strong')).toHaveText(['Mercado B', 'Viagem B']);
    await detalhe(page).locator('.available-category', { hasText: 'Mercado B' }).locator('[data-action="vincular-disponivel"]').click();
    await expect(page.locator('#limite-categoria-cartao option:checked')).toHaveText('Mercado B');
    await page.fill('#limite-valor', '500');
    await page.click('#form-categoria-limite button[type=submit]');
    await expect(toast(page)).toHaveText('Limite salvo.');
    await expect(page.locator('#summary-categorias-vinculadas')).toHaveText('1');
    await expect(page.locator('#summary-limite-total')).toHaveText('R$ 500,00');
    await expect(detalhe(page).locator('.available-category strong')).toHaveText(['Viagem B']);

    // MVP-FIN-AJUSTES-01 (P10/P11): a tabela da fatura edita, desvincula e mostra os lancamentos; compra nova nao fica aqui.
    await expect(page.locator('#btn-nova-compra-cartao')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Nova compra' })).toHaveCount(0);
    await expect(detalhe(page).locator('.fatura-table-header > div').last()).toHaveText('Ações');
    await grupo(page, 'Mercado B').locator('[data-action="editar-limite"]').click();
    await expect(page.locator('#limite-categoria-cartao option:checked')).toHaveText('Mercado B');
    await page.fill('#limite-valor', '600');
    await page.click('#form-categoria-limite button[type=submit]');
    await expect(toast(page)).toHaveText('Limite salvo.');
    await expect(grupo(page, 'Mercado B').locator('> div').nth(1)).toHaveText('R$ 600,00');
    await grupo(page, 'Mercado B').locator('[data-action="toggle-limite"]').click();
    await expect(toast(page)).toHaveText('Vínculo desativado.');
    await expect(grupo(page, 'Mercado B')).toHaveCount(0);
    await expect(detalhe(page).locator('.available-category strong')).toHaveText(['Mercado B', 'Viagem B']);
    // Vincular de novo reaproveita o vinculo desativado e a tabela consolidada se atualiza.
    await detalhe(page).locator('.available-category', { hasText: 'Mercado B' }).locator('[data-action="vincular-disponivel"]').click();
    await page.fill('#limite-valor', '500');
    await page.click('#form-categoria-limite button[type=submit]');
    await expect(toast(page)).toHaveText('Limite salvo.');
    await expect(grupo(page, 'Mercado B').locator('> div').nth(1)).toHaveText('R$ 500,00');
    await expect(detalhe(page).locator('.available-category strong')).toHaveText(['Viagem B']);

    // Compra nova: 3 parcelas a partir de 05/2031.
    await novaCompra(page, { cartao: 'Cartao Roxo', descricao: 'Geladeira E2E', valor: '100.00', parcelas: 3, data: '2031-05-12', mes: '2031-05' });

    await mesDaFatura(page, '2031-05');
    await expect(metrica(page, 'Total da fatura')).toHaveText('R$ 33,34');
    // FIN-CARTAO-DESPESAS-FIXAS-01: a parcela (Categoria do Cartao Mercado B gravada) nao consome o limite da categoria
    await expect(metrica(page, 'Disponível')).toHaveText('R$ 500,00');
    await expect(grupo(page, 'Mercado B').locator('.compact-pill')).toHaveText('Normal');
    await expect(grupo(page, 'Compras parceladas').locator('.usage-cell strong')).toHaveText('R$ 33,34');
    // Desvincular nao apaga lancamentos: a fatura continua igual; so o limite sai.
    await grupo(page, 'Mercado B').locator('[data-action="toggle-limite"]').click();
    await expect(toast(page)).toHaveText('Vínculo desativado.');
    await expect(metrica(page, 'Total da fatura')).toHaveText('R$ 33,34');
    await expect(grupo(page, 'Compras parceladas').locator('.usage-cell strong')).toHaveText('R$ 33,34');
    await expect(lancamento(page, 'Geladeira E2E')).toHaveCount(1);
    await grupo(page, 'Compras parceladas').locator('[data-action="ver-lancamentos-fatura"]').click();
    await expect(lancamento(page, 'Geladeira E2E')).toHaveCount(1);
    await expect(grupo(page, 'Compras parceladas').locator('[data-action="editar-limite"]')).toBeDisabled();
    await expect(grupo(page, 'Compras parceladas').locator('[data-action="toggle-limite"]')).toBeDisabled();
    await detalhe(page).locator('.available-category', { hasText: 'Mercado B' }).locator('[data-action="vincular-disponivel"]').click();
    await page.fill('#limite-valor', '500');
    await page.click('#form-categoria-limite button[type=submit]');
    await expect(toast(page)).toHaveText('Limite salvo.');
    await expect(grupo(page, 'Mercado B').locator('.compact-pill')).toHaveText('Normal');
    await expect(lancamento(page, 'Geladeira E2E')).toContainText('Mercado B');
    await expect(lancamento(page, 'Geladeira E2E')).toContainText('1/3');

    // Editar so este lancamento: total de parcelas nao muda (defeito do Flask); o valor desta parcela muda.
    await lancamento(page, 'Geladeira E2E').locator('[data-action="editar-lancamento"]').click();
    await expect(page.locator('#lancamento-edit-total-parcelas')).toHaveValue('3');
    await page.fill('#lancamento-edit-total-parcelas', '4');
    await page.click('#form-editar-lancamento button[type=submit]');
    await expect(toast(page)).toHaveText(/^Erro ao salvar lançamento: Parcela e total de parcelas nao mudam por aqui/);
    await page.fill('#lancamento-edit-total-parcelas', '3');
    await page.fill('#lancamento-edit-valor', '40');
    await page.click('#form-editar-lancamento button[type=submit]');
    await expect(page.locator('#modal-editar-lancamento')).not.toHaveClass(/open/);
    await expect(lancamento(page, 'Geladeira E2E').locator('.fatura-lancamento-valor')).toHaveText('R$ 40,00');
    await expect(metrica(page, 'Total da fatura')).toHaveText('R$ 40,00');

    // Gerenciar parcelamento: so as futuras em fatura aberta.
    await lancamento(page, 'Geladeira E2E').locator('[data-action="gerenciar-parcelamento"]').click();
    await expect(page.locator('#modal-gerenciar-parcelamento')).toHaveClass(/open/);
    await expect(page.locator('#parcelamento-gestao-resumo div', { hasText: 'Futuras editáveis' }).locator('strong')).toHaveText('2');
    await expect(page.locator('#parcelamento-gestao-parcelas .parcelamento-status')).toHaveText(['Atual', 'Futura', 'Futura']);
    await page.fill('#parcelamento-gestao-valor', '30');
    await page.click('#form-gerenciar-parcelamento button[type=submit]');
    await expect(toast(page)).toHaveText('2 parcela(s) futura(s) atualizada(s).');
    await expect(page.locator('#parcelamento-gestao-parcelas tr td:nth-child(4)')).toHaveText(['R$ 40,00', 'R$ 30,00', 'R$ 30,00']);
    await page.click('#btn-cancelar-parcelas-futuras');
    await expect(toast(page)).toHaveText('2 parcela(s) futura(s) cancelada(s).');
    expect(dialogos.at(-1)).toBe('Esta ação afetará apenas as parcelas futuras deste parcelamento. As parcelas anteriores não serão alteradas.');
    await expect(page.locator('#parcelamento-gestao-parcelas tr')).toHaveCount(1);
    await page.locator('#modal-gerenciar-parcelamento [data-close-modal]').first().click();
    await mesDaFatura(page, '2031-06');
    await expect(page.locator('.fatura-lancamento-row')).toHaveCount(0);

    // Excluir parcelada: segunda confirmacao com as quantidades; a vista: so a do original.
    await novaCompra(page, { cartao: 'Cartao Roxo', descricao: 'Sofa E2E', valor: '50.00', parcelas: 2, data: '2031-06-02', mes: '2031-06' });
    await mesDaFatura(page, '2031-06');
    await lancamento(page, 'Sofa E2E').locator('[data-action="excluir-lancamento"]').click();
    await expect(lancamento(page, 'Sofa E2E')).toHaveCount(0);
    expect(dialogos.slice(-2)).toEqual([
        'Excluir o lançamento "Sofa E2E"?\nEsta ação não pode ser desfeita.',
        'Esta compra é parcelada (2 parcelas). Serão excluídas as 2 parcelas em fatura aberta.\nPara manter as parcelas atuais e remover só as próximas, use "Gerenciar parcelamento".',
    ]);
    await mesDaFatura(page, '2031-07');
    await expect(page.locator('.fatura-lancamento-row')).toHaveCount(0);
    await mesDaFatura(page, '2031-05');
    await lancamento(page, 'Geladeira E2E').locator('[data-action="excluir-lancamento"]').click();
    await expect(lancamento(page, 'Geladeira E2E')).toHaveCount(0);
    await expect(metrica(page, 'Total da fatura')).toHaveText('R$ 0,00');

    await inativarCartao(page, 'Cartao Roxo');
});

test('fechamento confirmado sugere a fatura; manual prevalece; consolidada so com confirmacao e protegida', async ({ page }) => {
    test.skip(!process.env.CF_E2E_LOCAL, 'a consolidacao usa o gancho do harness local');
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirCartoes(page);
    await novoCartao(page, { nome: 'Cartao Lilas', fechamento: 25, vencimento: 5, confirmado: true });
    await expect(page.locator('#cartao-compra-no-fechamento')).toHaveValue('PROXIMO');

    // MVP-FIN-AJUSTES-01 (P11): a compra nova fica em Lancamentos, com a mesma sugestao pelo fechamento.
    const abrirCompra = async () => {
        await page.goto('/lancamentos.html');
        await expect(page.locator('#filtro-mes')).not.toHaveValue('');
        await page.click('#btn-novo-lancamento');
        await page.selectOption('#lancamento-tipo', 'cartao');
        await page.selectOption('#lancamento-cartao', { label: 'Cartao Lilas' });
    };
    const data = async (valor) => { await page.fill('#lancamento-data', valor); await page.locator('#lancamento-data').dispatchEvent('change'); };
    const sugestao = page.locator('#lancamento-fatura-sugestao');
    const preencher = async (descricao, valor) => {
        await page.fill('#lancamento-descricao', descricao);
        await page.fill('#lancamento-valor', valor);
        await page.selectOption('#lancamento-categoria-despesa-cartao', { label: 'Moradia' });
        await page.locator('#form-lancamento').evaluate((f) => f.requestSubmit());
    };
    await abrirCompra();
    await data('2031-11-24');
    await expect(page.locator('#lancamento-mes-fatura')).toHaveValue('2031-12');
    await expect(sugestao).toHaveText('Sugerida pelo fechamento: fatura de 12/2031 (fecha 25/11, vence 05/12).');
    await data('2031-11-25');
    await expect(page.locator('#lancamento-mes-fatura')).toHaveValue('2032-01');
    await page.fill('#lancamento-mes-fatura', '2032-02');
    await data('2031-11-24');
    await expect(page.locator('#lancamento-mes-fatura')).toHaveValue('2032-02');
    await expect(sugestao).toContainText('Mês escolhido manualmente: 02/2032.');
    await data('2031-11-26');
    await page.click('#lancamento-usar-sugerida');
    await expect(page.locator('#lancamento-mes-fatura')).toHaveValue('2032-01');
    await preencher('Mesa E2E', '100');
    await expect.poll(() => dialogos.join('|')).toContain('Lançamento em cartão salvo com sucesso!');

    const consolidacao = await page.request.post('/__e2e__/consolidar', { data: { cartao: 'Cartao Lilas', competencia: '2032-01-01' } });
    expect(consolidacao.status()).toBe(200);
    await abrirCompra();
    await data('2031-11-27');
    await expect(sugestao).toContainText('Essa fatura está consolidada: a inclusão pedirá confirmação.');
    await preencher('Cadeira E2E', '10');
    await expect.poll(() => dialogos.join('|')).toContain('Esta compra entra em fatura já consolidada');
    await expect.poll(() => dialogos.filter((m) => m.includes('salvo com sucesso')).length).toBe(2);
    await abrirCartoes(page);

    // Na fatura consolidada nada muda por aqui (D6): edicao e exclusao recusadas.
    await selecionar(page, 'Cartao Lilas');
    await mesDaFatura(page, '2032-01');
    await expect(page.locator('.fatura-lancamento-row')).toHaveCount(2);
    await expect(metrica(page, 'Total da fatura')).toHaveText('R$ 110,00');
    await lancamento(page, 'Mesa E2E').locator('[data-action="editar-lancamento"]').click();
    await page.click('#form-editar-lancamento button[type=submit]');
    await expect(toast(page)).toHaveText('Erro ao salvar lançamento: Operação bloqueada: Fatura fechada (consolidada).');
    await page.locator('#modal-editar-lancamento [data-close-modal]').first().click();
    await inativarCartao(page, 'Cartao Lilas');
});

test('integracao com Despesas: fatura paga protege os lancamentos; estornada, volta a editar', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirCartoes(page);
    await novoCartao(page, { nome: 'Cartao Pagamento', fechamento: 3, vencimento: 12 });
    await novaCompra(page, { cartao: 'Cartao Pagamento', descricao: 'Compra a pagar E2E', valor: '150.00', data: '2034-05-02', mes: '2034-05' });

    // Despesas (como no Flask): a fatura do mes com o valor das compras; pagar e estornar.
    await abrirDespesas(page, '2034-05');
    const fatura = 'Fatura Cartao Pagamento - 05/2034';
    await expect(despesa(page, fatura).locator('.despesa-cell-valor')).toHaveText('R$ 150,00');
    await pagar(page, fatura, { conta: 'Conta Perfil B (Banco ficticio)' });
    await expect.poll(() => dialogos.at(-1)).toMatch(/^Fatura paga: R\$\s150,00 debitados de Conta Perfil B\./);
    await expect(despesa(page, fatura).locator('.status-badge')).toHaveText('Pago');

    await abrirCartoes(page);
    await selecionar(page, 'Cartao Pagamento');
    await mesDaFatura(page, '2034-05');
    await lancamento(page, 'Compra a pagar E2E').locator('[data-action="editar-lancamento"]').click();
    await page.fill('#lancamento-edit-valor', '1');
    await page.click('#form-editar-lancamento button[type=submit]');
    await expect(toast(page)).toHaveText('Erro ao salvar lançamento: Operação bloqueada: Fatura paga: para corrigir, estorne o pagamento da fatura.');
    await page.locator('#modal-editar-lancamento [data-close-modal]').first().click();
    await expect(lancamento(page, 'Compra a pagar E2E').locator('.fatura-lancamento-valor')).toHaveText('R$ 150,00');

    await abrirDespesas(page, '2034-05');
    await estornar(page, fatura, 'Debito em duplicidade');
    await expect.poll(() => dialogos.at(-1)).toBe('Pagamento da fatura estornado com sucesso.');
    await abrirCartoes(page);
    await selecionar(page, 'Cartao Pagamento');
    await mesDaFatura(page, '2034-05');
    await lancamento(page, 'Compra a pagar E2E').locator('[data-action="excluir-lancamento"]').click();
    await expect(lancamento(page, 'Compra a pagar E2E')).toHaveCount(0);
    await abrirDespesas(page, '2034-05');
    await expect(despesa(page, fatura).locator('.despesa-cell-valor')).toHaveText('R$ 0,00');  // sem dupla contagem
    await abrirCartoes(page);
    await inativarCartao(page, 'Cartao Pagamento');
});

test('LEITOR ve sem acoes; escrita direta e outro perfil recusados', async ({ page }) => {
    await entrar(page, A);
    await abrirCartoes(page);
    await trocarPerfil(page, 'Empresa');
    await expect(page.locator('#lista-cartoes .loading')).toHaveCount(0);
    await selecionar(page, 'Cartao Empresa');
    await mesDaFatura(page, '2026-11');
    await expect(metrica(page, 'Total da fatura')).toHaveText('R$ 250,00');
    for (const seletor of ['#btn-novo-cartao', '#btn-vincular-categoria', '[data-action="editar-cartao"]',
        '[data-action="abrir-limite"]', '.lancamento-acoes', '[data-action="editar-limite"]', '[data-action="toggle-limite"]']) {
        await expect(page.locator(seletor).first()).toBeHidden();
    }
    await expect(page.locator('.fatura-table-row [data-action="ver-lancamentos-fatura"]').first()).toBeVisible();
    const empresa = await perfilAtivoId(page);
    const cartao = Number(await itemCartao(page, 'Cartao Empresa').getAttribute('data-cartao-id'));
    const status = [
        (await chamarRpc(page, 'vincular_limite_cartao', { p_perfil_id: empresa, p_cartao_id: cartao, p_dados: { categoria_cartao_id: 301 } })).status,
        (await chamarRpc(page, 'criar_cartao', { p_perfil_id: empresa, p_dados: { nome: 'X', dia_fechamento: 1, dia_vencimento: 9 }, p_chave: crypto.randomUUID() })).status,
        (await chamarRpc(page, 'limites_do_cartao', { p_perfil_id: Number(process.env.CF_ID_PERFIL_B || '103'), p_cartao_id: cartao, p_mes: '2026-11-01' })).status,
    ];
    expect(status).toEqual([403, 403, 403]);
});
