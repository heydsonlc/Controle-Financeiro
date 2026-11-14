// FIN-MVP-MOBILE-03 — Cartoes de Credito mobile. Usuario G, titular do "Perfil G (ficticio)" (so deste cenario; gerador NOVO):
// "Itau Visa G" (final 1234) com a fatura de 04/2031 montada pelas funcoes oficiais (limites de "Mercado G" e "Viagem G", compras a
// vista, uma parcelada em 6x, uma sem Categoria do Cartao, a despesa fixa "Streaming G" prevista, cartoes do contrato fisico
// 1234 e virtual 9876, e um estorno parcial da padaria) e "Nubank Master G" (final 5678) sem compras (o Visa tambem tem compras no mes atual, so para a homologacao). Somente leitura: usuario H, leitor
// do Perfil G. A fatura mobile e comparada com as telas do desktop no mesmo banco (Cartoes: grupos e executado; Despesas:
// previsto) e com as funcoes do banco; pagamentos, estornos e compras sao conferidos no banco. Dados FICTICIOS; grava so no
// banco descartavel.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { chamarRpc, despesa, normal } from './despesas.mjs';

const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const H = { email: process.env.CF_EMAIL_H || 'usuario.h@teste.local', senha: process.env.CF_SENHA_H };
const PERFIL_G = 160;
const MES = '2031-04';
const CELULAR = { width: 390, height: 844 };
const DESKTOP = { width: 1366, height: 900 };
const EVIDENCIAS = process.env.CF_MOBILE03_EVIDENCIAS || '';  // capturas da homologacao (opcional)
const VISA = 'Itau Visa G (ficticio)';
const MASTER = 'Nubank Master G (ficticio)';

test.use({ viewport: CELULAR, isMobile: true, hasTouch: true });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    // A pagina mobile nao tem servidor /api/: as rotas sao atendidas no navegador pelos servicos do desktop.
    page.on('request', (req) => { if (new URL(req.url()).pathname.startsWith('/api/')) problemas.push(`pedido a /api/: ${req.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP, erros de JS ou pedidos a /api/').toEqual([]);
});

async function evidencia(page, nome, inteira = true) {
    if (!EVIDENCIAS) return;
    mkdirSync(EVIDENCIAS, { recursive: true });
    await page.screenshot({ path: path.join(EVIDENCIAS, `${nome}.png`), fullPage: inteira });
}

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/inicio.html**');
}

async function rpc(page, funcao, corpo) {
    const r = await chamarRpc(page, funcao, corpo);
    expect(r.status, `${funcao}: ${JSON.stringify(r.corpo)}`).toBe(200);
    return r.corpo;
}

const idDoCartao = async (page, nome) => (await rpc(page, 'cartoes_da_tela', { p_perfil_id: PERFIL_G })).find((c) => c.nome === nome).id;

async function esperarFatura(page, mes, cartaoId) {
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-carregado', `${mes}:${cartaoId}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
}

async function abrirCartoes(page, cartaoId, mes = MES) {
    await page.goto(`/cartoes-mobile.html?mes=${mes}&cartao=${cartaoId}`);
    await esperarFatura(page, mes, cartaoId);
}

const cabecalho = (page, chave) => page.locator(`.mob-grupo[data-grupo="${chave}"] .mob-grupo-cabecalho`);
const linha = (page, nome) => page.locator('#mob-lista .mob-linha', { has: page.locator('.mob-linha-nome', { hasText: nome }) }).first();
const folha = (page) => page.locator('#mob-folha');
const botaoFolha = (page, texto) => folha(page).locator('.mob-botao', { hasText: texto });
const aviso = (page) => page.locator('#mob-aviso');
const valorFatura = (page, rotulo) => page.locator('.mob-fatura-valores div', { has: page.locator('dt', { hasText: rotulo }) }).locator('dd');
const reais = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }).replace(/\s/g, ' ');
const semAcento = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

async function expandirTodos(page) {
    const fechados = page.locator('.mob-grupo-cabecalho[aria-expanded="false"]');
    while (await fechados.count()) await fechados.first().click();
}

async function abrirDetalhes(page, chave, nome) {
    if ((await cabecalho(page, chave).getAttribute('aria-expanded')) !== 'true') await cabecalho(page, chave).click();
    await linha(page, nome).click();
    await expect(folha(page)).toBeVisible();
    await expect(page.locator('#mob-folha-titulo')).toContainText(nome);
}

const detalhe = (page, rotulo) => folha(page).locator('.mob-detalhes dt', { hasText: new RegExp(`^${rotulo}$`) }).locator('xpath=following-sibling::dd[1]');

// Grupos mostrados: [chave, rotulo, quantidade, total]
const gruposMobile = (page) => page.$$eval('.mob-grupo', (els) => els.map((g) => {
    const rotulo = g.querySelector('.mob-grupo-rotulo');
    return [g.dataset.grupo, rotulo.firstChild.textContent.trim(), Number(rotulo.querySelector('.mob-grupo-qtd').textContent.replace(/\D/g, '')),
        g.querySelector('.mob-grupo-total').textContent.replace(/\s+/g, ' ').trim()];
}));

const comprasDoGrupo = (page, chave) => page.$$eval(`.mob-grupo[data-grupo="${chave}"] .mob-linha`, (els) => els.map((e) => [
    e.querySelector('.mob-linha-nome').textContent.trim(), e.querySelector('.mob-linha-valor').textContent.replace(/\s+/g, ' ').trim()]));

// Linha da fatura em Despesas (contas_do_mes): os mesmos previsto, executado e vencimento da tela Despesas.
async function faturaNoBanco(page, cartaoId, mes = MES) {
    const contas = await rpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_G, p_mes: `${mes}-01` });
    return contas.find((c) => c.grupo === 'FATURA' && c.cartao_id === cartaoId) || null;
}

async function conferirCabecalhoComBanco(page, cartaoId) {
    const f = await faturaNoBanco(page, cartaoId);
    await expect(valorFatura(page, 'Previsto')).toHaveText(reais(f.valor_previsto));
    await expect(valorFatura(page, 'Executado')).toHaveText(reais(f.valor_executado));
    await expect(valorFatura(page, 'Vencimento')).toHaveText(`${f.data_vencimento.slice(8, 10)}/${f.data_vencimento.slice(5, 7)}`);
    return f;
}

test('atalho Cartoes da pagina principal abre a fatura na competencia; seletor de cartao so com o final; sem rolagem lateral', async ({ page }) => {
    await entrar(page, G);
    await page.goto(`/inicio.html?mes=${MES}`);
    const atalho = page.locator('.mob-atalho[data-modulo="cartoes"]');
    await expect(atalho).toHaveAttribute('href', `cartoes-mobile.html?mes=${MES}`);
    await expect(atalho).not.toHaveAttribute('aria-disabled', 'true');
    await atalho.click();
    await page.waitForURL(`**/cartoes-mobile.html?mes=${MES}**`);
    const visa = await idDoCartao(page, VISA);
    const master = await idDoCartao(page, MASTER);
    // Os cartoes ativos do perfil, na ordem da tela do desktop; o primeiro vem selecionado, como no desktop.
    await esperarFatura(page, MES, visa);
    await expect(page.locator('#mob-cartao option')).toHaveText([`${VISA} · final 1234`, `${MASTER} · final 5678`]);
    await expect(page.locator('h1.mob-titulo')).toHaveText('Cartões');
    await expect(page.locator('#mob-competencia')).toHaveText('Abr/2031');
    await page.selectOption('#mob-cartao', String(master));
    await esperarFatura(page, MES, master);
    await page.selectOption('#mob-cartao', String(visa));
    await esperarFatura(page, MES, visa);
    expect(new URL(page.url()).searchParams.get('cartao')).toBe(String(visa));
    // Inicio e voltar mantem a competencia; nenhum item novo na barra.
    await expect(page.locator('#mob-voltar')).toHaveAttribute('href', `inicio.html?mes=${MES}`);
    await expect(page.locator('.mob-barra-item[data-inicio]')).toHaveAttribute('href', `inicio.html?mes=${MES}`);
    await expect(page.locator('.mob-barra-item')).toHaveText(['Início', 'Lançar', 'Resumo', 'Mais']);
    await expect(page.locator('#mob-lista-titulo')).toHaveText('Compras da fatura');
    await expect(page.locator('.mob-grupo-cabecalho[aria-expanded="true"]')).toHaveCount(0);  // grupos recolhidos
    await evidencia(page, 'fatura-recolhida-390x844');
    // Nunca o numero completo, validade ou CVV: so o final de 4 digitos.
    expect(await page.locator('body').textContent()).not.toMatch(/\d{4}[\s.-]?\d{4}[\s.-]?\d{4}|CVV|validade/i);
    for (const largura of [320, 360, 390, 412]) {
        await page.setViewportSize({ width: largura, height: 800 });
        await expandirTodos(page);
        const { rolagem, largo } = await page.evaluate(() => ({ rolagem: document.documentElement.scrollWidth,
            largo: document.documentElement.clientWidth }));
        expect(rolagem, `sem rolagem horizontal em ${largura}px`).toBeLessThanOrEqual(largo);
        if (largura === 320) await evidencia(page, 'grupos-abertos-320');
    }
    await page.setViewportSize(CELULAR);
    await evidencia(page, 'grupos-abertos-390x844');
    await page.click('#mob-voltar');
    await page.waitForURL(`**/inicio.html?mes=${MES}`);
});

test('fatura igual ao desktop: previsto, executado e vencimento de Despesas; grupos, totais e compras da tela Cartoes', async ({ page }) => {
    await entrar(page, G);
    const visa = await idDoCartao(page, VISA);
    await abrirCartoes(page, visa);
    // Cabecalho: os valores da fatura em Despesas (contas_do_mes), sem soma propria.
    const f = await conferirCabecalhoComBanco(page, visa);
    expect([Number(f.valor_executado), Number(f.valor_previsto)]).toEqual([565.8, 1090.3]);
    await expect(page.locator('.mob-fatura-titulo')).toHaveText('Fatura Abr/2031');
    await expect(page.locator('.mob-fatura-nota')).toHaveText(`Compras ${reais(571.3)} · créditos −${reais(5.5)}`);

    // Grupos: os do banco (fatura_por_categoria), na mesma ordem, com o executado de cada um.
    const resumo = await rpc(page, 'fatura_por_categoria', { p_perfil_id: PERFIL_G, p_cartao_id: visa, p_mes: `${MES}-01` });
    const grupos = await gruposMobile(page);
    expect(grupos.map((g) => [semAcento(g[1]), g[2], g[3]])).toEqual(resumo.categorias.map((c) => [
        semAcento(c.categoria_cartao_nome), Number(c.quantidade_lancamentos), reais(c.gasto_atual)]));
    expect(grupos.map((g) => [g[0], g[1], g[3]])).toEqual([
        ['360', 'Mercado G', reais(275.5)], ['362', 'Viagem G', reais(0)], ['361', 'Restaurantes G', reais(120)],
        ['compras_parceladas', 'Compras parceladas', reais(90)], ['despesas_fixas', 'Despesas fixas', reais(39.9)],
        ['sem_categoria', 'Sem Categoria do Cartão', reais(45.9)], ['creditos', 'Créditos e ajustes', reais(-5.5)]]);
    await expect(cabecalho(page, '360').locator('.mob-grupo-limite')).toHaveText(`Limite ${reais(500)} · disponível ${reais(224.5)}`);
    await expect(cabecalho(page, '361').locator('.mob-grupo-limite')).toHaveCount(0);

    // Compras de cada grupo: as mesmas do filtro "Ver lancamentos" do desktop (lancamentos_fatura_por_categoria).
    await expandirTodos(page);
    for (const [chave] of grupos) {
        const doBanco = (await rpc(page, 'lancamentos_fatura_por_categoria', { p_perfil_id: PERFIL_G, p_cartao_id: visa,
            p_mes: `${MES}-01`, p_filtro: chave })).lancamentos;
        expect(await comprasDoGrupo(page, chave), chave).toEqual(doBanco.map((l) => [l.descricao, reais(l.valor)]));
    }
    await expect(cabecalho(page, '362').locator('xpath=following-sibling::div')).toHaveText('Nenhuma compra nesta categoria.');
    await expect(linha(page, 'Loja Eletronicos G').locator('.mob-linha-data')).toHaveText('03/04 · 1/6 · •••• 1234');
    await expect(linha(page, 'Streaming G').locator('.mob-linha-data')).toContainText('prevista');

    // Tela Cartoes do desktop: os mesmos grupos e valores, e o total da fatura igual ao executado.
    await page.setViewportSize(DESKTOP);
    await page.goto('/cartoes.html');
    await page.locator('#lista-cartoes .cartao-list-item', { hasText: VISA }).click();
    const campo = page.locator('[data-action="alterar-mes-fatura"]');
    await campo.fill(MES);
    await campo.dispatchEvent('change');
    await expect(page.locator('.fatura-card-header p')).toHaveText(`Consumo agrupado por Categoria do Cartão em ${MES}.`);
    const desktop = await page.$$eval('.fatura-categorias-card > .fatura-table:not(.fatura-por-cartao) > .fatura-table-row', (els) => els.map((e) => [
        e.querySelector('.table-category span:last-child').textContent.trim(), e.querySelector('.usage-cell strong').textContent.replace(/\s+/g, ' ').trim()]));
    expect(desktop.map(([n, v]) => [semAcento(n), v])).toEqual(grupos.map((g) => [semAcento(g[1]), g[3]]));
    expect(normal(await page.locator('.fatura-metrics article', { hasText: 'Total da fatura' }).locator('strong').textContent()))
        .toBe(normal(reais(f.valor_executado)));
    // Tela Despesas do desktop: a linha da fatura mostra o mesmo previsto (fatura em aberto).
    await page.goto(`/contas.html?mes=${MES}`);
    await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', '04/2031');
    expect(normal(await despesa(page, `Fatura ${VISA} - 04/2031`).locator('.despesa-cell-valor').textContent())).toBe(normal(reais(f.valor_previsto)));
});

test('detalhe da compra: parcela, despesa fixa e credito; filtros por cartao do contrato e situacao', async ({ page }) => {
    await entrar(page, G);
    const visa = await idDoCartao(page, VISA);
    await abrirCartoes(page, visa);

    await abrirDetalhes(page, 'compras_parceladas', 'Loja Eletronicos G');
    await expect(folha(page).locator('.mob-folha-valor')).toHaveText(reais(90));
    await expect(detalhe(page, 'Parcela')).toHaveText('1 de 6');
    await expect(detalhe(page, 'Cartão')).toHaveText(`${VISA} · •••• 1234`);
    await expect(detalhe(page, 'Competência')).toHaveText('Abr/2031');
    await expect(detalhe(page, 'Data')).toHaveText('03/04/2031');
    await expect(detalhe(page, 'Situação da cobrança')).toHaveText('Lançada');
    await expect(folha(page).locator('.mob-botao')).toHaveText(['Editar', 'Parcelamento', 'Excluir']);
    await evidencia(page, 'detalhe-parcelada', false);
    await page.click('#mob-folha-fechar');

    await abrirDetalhes(page, 'despesas_fixas', 'Streaming G');
    await expect(detalhe(page, 'Recorrência')).toHaveText('Despesa fixa do cartão');
    await expect(detalhe(page, 'Previsto')).toHaveText(reais(39.9));
    await expect(detalhe(page, 'Executado')).toHaveText(reais(39.9));
    await expect(detalhe(page, 'Situação da cobrança')).toHaveText('Prevista · aguardando cobrança');
    await expect(detalhe(page, 'Alteração')).toHaveText('Gerada por recorrencia: edite a recorrencia');
    await expect(folha(page).locator('.mob-botao')).toHaveText(['Excluir']);  // sem Editar: o banco bloqueia
    await page.click('#mob-folha-fechar');

    await abrirDetalhes(page, 'creditos', 'Estorno parcial Padaria G');
    await expect(folha(page).locator('.mob-folha-valor')).toHaveText(reais(-5.5));
    await expect(detalhe(page, 'Tipo')).toHaveText('Estorno de compra');
    await expect(detalhe(page, 'Compra original')).toHaveText(`Padaria G (${reais(35.5)})`);
    await expect(folha(page).locator('.mob-botao')).toHaveCount(0);  // credito sem acoes, como no desktop
    await page.click('#mob-folha-fechar');

    // Filtros: cartao do contrato (o "Ver lancamentos" por cartao do desktop) e situacao, num painel.
    await page.click('#mob-filtros');
    await expect(folha(page).locator('select').first().locator('option')).toHaveText(['Todos os cartões', '•••• 1234 · Físico',
        '•••• 9876 · Virtual', 'Sem cartão identificado']);
    await folha(page).locator('select').first().selectOption({ label: '•••• 9876 · Virtual' });
    await evidencia(page, 'filtros', false);
    await botaoFolha(page, 'Aplicar').click();
    await expect(page.locator('#mob-filtro-marca')).toBeVisible();
    expect((await gruposMobile(page)).map((g) => [g[0], g[2], g[3]])).toEqual([['361', 1, reais(120)]]);
    await page.click('#mob-filtros');
    await folha(page).locator('select').first().selectOption('');
    await folha(page).locator('select').nth(1).selectOption('prevista');
    await botaoFolha(page, 'Aplicar').click();
    expect((await gruposMobile(page)).map((g) => g[0])).toEqual(['despesas_fixas']);
    await page.click('#mob-filtros');
    await botaoFolha(page, 'Limpar').click();
    await expect(page.locator('#mob-filtro-marca')).toBeHidden();
    expect((await gruposMobile(page)).length).toBe(7);
});

test('pagamento da fatura pelo fluxo do desktop, sem duplicidade; estorno reabre a fatura', async ({ page }) => {
    await entrar(page, G);
    const visa = await idDoCartao(page, VISA);
    await abrirCartoes(page, visa);
    const f = await faturaNoBanco(page, visa);

    await page.click('#mob-pagar-fatura');
    await expect(page.locator('#mob-folha-titulo')).toHaveText(`Pagar fatura: Fatura ${VISA} - 04/2031`);
    // O executado consolidado e o valor sugerido, com a parte de despesas fixas previstas identificada (como no desktop).
    await expect(folha(page).locator('.mob-opcao').first()).toContainText(`Executado consolidado (valor sugerido): ${reais(565.8)}`);
    await expect(folha(page)).toContainText(`Inclui ${reais(39.9)} de despesas fixas previstas, ainda sem cobrança importada.`);
    await folha(page).locator('.mob-campo', { hasText: 'Conta bancária' }).locator('select').selectOption({ label: 'Conta G (ficticia) (Banco ficticio)' });
    await evidencia(page, 'pagar-fatura', false);
    await botaoFolha(page, 'Confirmar pagamento').dblclick();  // duplo toque: um pagamento so
    await expect(aviso(page)).toContainText(`Fatura paga: ${reais(565.8)} debitados de Conta G (ficticia).`);
    await esperarFatura(page, MES, visa);
    await expect(page.locator('.mob-fatura-situacao')).toHaveText(/^Paga em \d{2}\/\d{2}$/);
    await expect(page.locator('#mob-pagar-fatura')).toHaveCount(0);
    await expect(page.locator('#mob-estornar-fatura')).toBeVisible();
    await conferirCabecalhoComBanco(page, visa);
    await evidencia(page, 'apos-pagamento');
    // No banco: um pagamento vigente, pelo valor sugerido; um segundo pagamento e recusado.
    const pagamento = await rpc(page, 'dados_pagamento_fatura', { p_perfil_id: PERFIL_G, p_fatura_id: f.id });
    expect(pagamento.pagamentos.filter((p) => p.vigente).map((p) => Number(p.valor_pago))).toEqual([565.8]);
    expect(pagamento.pode_pagar).toBe(false);
    const contaG = (await rpc(page, 'contas_bancarias_do_perfil', { p_perfil_id: PERFIL_G }))[0].id;
    const repetido = await chamarRpc(page, 'pagar_fatura', { p_perfil_id: PERFIL_G, p_fatura_id: f.id, p_chave: crypto.randomUUID(),
        p_dados: { conta_bancaria_id: contaG, data_pagamento: '2026-11-14', valor_pago: '565.80', valor_executado: '565.80' } });
    expect(repetido.status, 'segundo pagamento recusado').not.toBe(200);

    // Estorno: movimento compensatorio, fatura reaberta (o pagamento original fica no historico).
    await page.click('#mob-estornar-fatura');
    await folha(page).locator('textarea').fill('Teste E2E (ficticio): estorno do pagamento');
    await botaoFolha(page, 'Confirmar estorno').click();
    await expect(aviso(page)).toContainText(`Pagamento estornado: ${reais(565.8)} devolvidos a Conta G (ficticia).`);
    await esperarFatura(page, MES, visa);
    await expect(page.locator('#mob-pagar-fatura')).toBeVisible();
    await expect(page.locator('.mob-fatura-situacao')).not.toHaveText(/Paga/);
    const depois = await rpc(page, 'dados_pagamento_fatura', { p_perfil_id: PERFIL_G, p_fatura_id: f.id });
    expect([depois.pode_pagar, depois.pagamentos.length, depois.pagamentos.filter((p) => p.vigente).length]).toEqual([true, 1, 0]);
});

test('edicao e exclusao de compras e parcelas futuras pelas regras do desktop; totais atualizados', async ({ page }) => {
    await entrar(page, G);
    const visa = await idDoCartao(page, VISA);
    await abrirCartoes(page, visa);

    // Edicao: o mesmo corpo do desktop; grupo e cabecalho relidos.
    // (Editar regrava a classificacao pela regra do banco: por isso a compra de categoria com limite ativo.)
    await abrirDetalhes(page, '360', 'Mercado Online G');
    await botaoFolha(page, 'Editar').click();
    await folha(page).locator('.mob-campo', { hasText: 'Valor' }).locator('input').fill('250.00');
    await evidencia(page, 'editar-compra', false);
    await botaoFolha(page, 'Salvar').click();
    await expect(aviso(page)).toHaveText('Lançamento atualizado.');
    await esperarFatura(page, MES, visa);
    await expect(cabecalho(page, '360').locator('.mob-grupo-total')).toHaveText(reais(285.5));
    await expect(cabecalho(page, '360').locator('.mob-grupo-limite')).toHaveText(`Limite ${reais(500)} · disponível ${reais(214.5)}`);
    expect(Number((await conferirCabecalhoComBanco(page, visa)).valor_executado)).toBe(575.8);

    // Exclusao a vista: confirmacao; o grupo sem compras some (como no desktop).
    await abrirDetalhes(page, 'sem_categoria', 'Farmacia G');
    await botaoFolha(page, 'Excluir').click();
    await expect(folha(page)).toContainText('Excluir o lançamento "Farmacia G"?');
    await botaoFolha(page, 'Excluir').click();
    await expect(aviso(page)).toHaveText('Lançamento excluído.');
    await esperarFatura(page, MES, visa);
    await expect(page.locator('.mob-grupo[data-grupo="sem_categoria"]')).toHaveCount(0);
    expect(Number((await conferirCabecalhoComBanco(page, visa)).valor_executado)).toBe(529.9);

    // Exclusao da parcelada: a segunda confirmacao do desktop, com as quantidades; cancelar nao exclui nada.
    await abrirDetalhes(page, 'compras_parceladas', 'Loja Eletronicos G');
    await botaoFolha(page, 'Excluir').click();
    await botaoFolha(page, 'Excluir').click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Confirmar');
    await expect(folha(page)).toContainText('Esta compra é parcelada (6 parcelas). Serão excluídas as 6 parcelas em fatura aberta.');
    await evidencia(page, 'excluir-parcelada', false);
    await botaoFolha(page, 'Cancelar').click();
    await expect(aviso(page)).toHaveText('Exclusão cancelada. Nada foi excluído.');
    await expect(folha(page)).toBeHidden();
    await expect(linha(page, 'Loja Eletronicos G')).toBeVisible();

    // Parcelamento: as 6 parcelas; cancelar so as futuras (a de 04/2031 fica).
    await linha(page, 'Loja Eletronicos G').click();
    await botaoFolha(page, 'Parcelamento').click();
    await expect(folha(page).locator('.mob-parcela')).toHaveCount(6);
    await expect(detalhe(page, 'Futuras editáveis')).toHaveText('5');
    await evidencia(page, 'parcelamento', false);
    await botaoFolha(page, 'Cancelar parcelas futuras').click();
    await expect(folha(page)).toContainText('Esta ação afetará apenas as parcelas futuras deste parcelamento.');
    await botaoFolha(page, 'Cancelar parcelas futuras').click();
    await expect(aviso(page)).toHaveText('5 parcela(s) futura(s) cancelada(s).');
    await esperarFatura(page, MES, visa);
    await expect(cabecalho(page, 'compras_parceladas').locator('.mob-grupo-total')).toHaveText(reais(90));
    const id = Number(await linha(page, 'Loja Eletronicos G').getAttribute('data-id'));
    const parcelamento = await rpc(page, 'parcelamento_da_compra', { p_perfil_id: PERFIL_G, p_lancamento_id: id });
    expect(Number(parcelamento.base.futuras_editaveis)).toBe(0);
});

test('outro cartao sem compras e troca de competencia mantendo o cartao', async ({ page }) => {
    await entrar(page, G);
    const visa = await idDoCartao(page, VISA);
    const master = await idDoCartao(page, MASTER);
    await abrirCartoes(page, master);
    await expect(page.locator('#mob-lista .mob-vazio')).toHaveText('Nenhuma compra nesta competênciaEste cartão não possui compras registradas em Abr/2031.');
    // A fatura vazia do mes existe (gerada com o mes): vencimento do cartao, previsto e executado zerados, sem pagamento.
    await conferirCabecalhoComBanco(page, master);
    await expect(valorFatura(page, 'Vencimento')).toHaveText('25/04');
    await expect(valorFatura(page, 'Executado')).toHaveText(reais(0));
    await expect(page.locator('.mob-fatura-situacao')).toHaveText('Aberta');
    await expect(page.locator('#mob-pagar-fatura')).toHaveCount(0);
    await evidencia(page, 'cartao-sem-compras');
    await page.selectOption('#mob-cartao', String(visa));
    await esperarFatura(page, MES, visa);
    await cabecalho(page, '360').click();
    await page.click('#mob-mes-seguinte');
    await esperarFatura(page, '2031-05', visa);  // o cartao escolhido fica
    await expect(page.locator('#mob-competencia')).toHaveText('Mai/2031');
    await expect(page.locator('#mob-cartao')).toHaveValue(String(visa));
    await expect(page.locator('.mob-grupo-cabecalho[aria-expanded="true"]')).toHaveCount(0);
    await page.click('#mob-mes-anterior');
    await esperarFatura(page, MES, visa);
    await expect(page.locator('.mob-barra-item[data-inicio]')).toHaveAttribute('href', `inicio.html?mes=${MES}`);
});

test('perfil somente leitura: mesma fatura e nenhuma acao de escrita', async ({ page }) => {
    await entrar(page, H);
    const visa = await idDoCartao(page, VISA);
    await abrirCartoes(page, visa);
    await conferirCabecalhoComBanco(page, visa);
    await expect(page.locator('.mob-fatura-acoes')).toHaveCount(0);
    expect((await gruposMobile(page)).length).toBeGreaterThan(0);
    await abrirDetalhes(page, '360', 'Mercado Online G');
    await expect(folha(page)).toContainText('Acesso somente de leitura a este perfil.');
    await expect(folha(page).locator('.mob-botao')).toHaveCount(0);
    await evidencia(page, 'somente-leitura', false);
});
