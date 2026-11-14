// FIN-MVP-MOB-01 — Lista de Despesas mobile. Usuario F, titular do "Perfil F (ficticio)" (so deste cenario; gerador NOVO;
// "Diarista F" semanal as tercas, "Aluguel F" e "Internet F" mensais, a partir de 04/2031; duas contas bancarias). As despesas
// avulsas sao criadas pela funcao oficial. Somente leitura: usuario A no perfil Empresa (leitor), sem escrita.
// A lista mobile e comparada com a tela do desktop no mesmo banco (mesmos grupos, linhas, valores e totais); situacao,
// pagamentos e movimentos sao conferidos no banco. Dados FICTICIOS; grava so no banco descartavel.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { chamarRpc, normal } from './despesas.mjs';

const F = { email: process.env.CF_EMAIL_F || 'usuario.f@teste.local', senha: process.env.CF_SENHA_F };
const A = { email: 'usuario.a@teste.local', senha: process.env.CF_SENHA_A, id: 'aaaaaaaa-0000-4000-8000-00000000000a' };
const PERFIL_F = 150;
const MES = '2031-04';
const CELULAR = { width: 390, height: 844 };
const DESKTOP = { width: 1366, height: 900 };
const EVIDENCIAS = process.env.CF_MOB01_EVIDENCIAS || '';  // capturas da homologacao (opcional)

test.use({ viewport: CELULAR, isMobile: true, hasTouch: true });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    // A pagina mobile nao tem servidor /api/: as rotas de Despesas sao atendidas no navegador pelo servico comum.
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

async function esperarLista(page, mes) {
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-competencia-carregada', mes);
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
}

async function abrirLista(page, mes = MES) {
    await page.goto(`/despesas-mobile.html?mes=${mes}`);
    await esperarLista(page, mes);
}

const cabecalho = (page, rotulo) => page.locator('.mob-grupo-cabecalho', { has: page.locator('.mob-grupo-nome', { hasText: rotulo }) });
const linha = (page, nome) => page.locator('#mob-lista .mob-linha', { has: page.locator('.mob-linha-nome', { hasText: nome }) }).first();
const folha = (page) => page.locator('#mob-folha');
const botaoFolha = (page, texto) => folha(page).locator('.mob-botao', { hasText: texto });
const aviso = (page) => page.locator('#mob-aviso');

async function expandir(page, rotulo) {
    const c = cabecalho(page, rotulo);
    if ((await c.getAttribute('aria-expanded')) !== 'true') await c.click();
    await expect(c).toHaveAttribute('aria-expanded', 'true');
}

async function expandirTodos(page) {
    const fechados = page.locator('.mob-grupo-cabecalho[aria-expanded="false"]');
    while (await fechados.count()) await fechados.first().click();
}

async function abrirDetalhes(page, grupo, nome) {
    await expandir(page, grupo);
    await linha(page, nome).click();
    await expect(folha(page)).toBeVisible();
    await expect(page.locator('#mob-folha-titulo')).toContainText(nome);
}

// Sequencia mostrada: G:<grupo> e L:<nome>=<valor>, na ordem da tela.
async function sequenciaMobile(page) {
    await expandirTodos(page);
    return page.$$eval('.mob-grupo-nome, .mob-grupo-itens > .mob-linha', (els) => els.map((e) => (e.classList.contains('mob-grupo-nome')
        ? `G:${e.textContent.trim()}`
        : `L:${e.querySelector('.mob-linha-nome').textContent.trim()}=${e.querySelector('.mob-linha-valor').textContent.replace(/\s+/g, ' ').trim()}`)));
}

async function sequenciaDesktop(page, mes) {
    await page.setViewportSize(DESKTOP);
    await page.goto(`/contas.html?mes=${mes}`);
    await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', `${mes.slice(5, 7)}/${mes.slice(0, 4)}`);
    const seq = await page.$$eval('#despesas-lista .despesas-grupo-titulo, #despesas-lista .despesa-card:not(.despesa-row-child)', (els) => els.map((e) => (e.classList.contains('despesas-grupo-titulo')
        ? `G:${e.textContent.trim()}`
        : `L:${e.querySelector('.despesa-cell-nome').textContent.trim()}=${e.querySelector('.despesa-cell-valor').textContent.replace(/\s+/g, ' ').trim()}`)));
    const total = normal(await page.locator('#total-geral').textContent());
    const pendentes = normal(await page.locator('#total-pendentes').textContent());
    const pagas = normal(await page.locator('#total-pagas').textContent());
    await page.setViewportSize(CELULAR);
    return { seq, total, pendentes, pagas };
}

async function totaisMobile(page) {
    return {
        total: normal(await page.locator('#mob-total .mob-total-valor').textContent()),
        detalhe: normal(await page.locator('#mob-total .mob-total-detalhe').textContent()),
    };
}

async function conferirIgualAoDesktop(page, mes) {
    const mobile = await sequenciaMobile(page);
    const t = await totaisMobile(page);
    const desktop = await sequenciaDesktop(page, mes);
    expect(mobile).toEqual(desktop.seq);
    expect(t.total).toBe(desktop.total);
    expect(t.detalhe).toBe(`Pendentes ${desktop.pendentes} · Pagas ${desktop.pagas}`);
    await abrirLista(page, mes);
    return mobile;
}

const contasDoMes = async (page, mes = MES) => (await chamarRpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_F, p_mes: `${mes}-01` })).corpo;
const contaDoMes = async (page, padrao, mes = MES) => (await contasDoMes(page, mes)).filter((c) => padrao.test(c.nome));

async function criarAvulsa(page, nome, valor, vencimento, descricao = '') {
    const r = await chamarRpc(page, 'criar_despesa', { p_perfil_id: PERFIL_F, p_chave: crypto.randomUUID(), p_dados: {
        nome, valor, descricao, categoria_id: 201, data_vencimento: vencimento, competencia: `${MES}-01`, debito_automatico: false,
        conta_bancaria_id: null } });
    expect(r.status, JSON.stringify(r.corpo)).toBe(200);
}

test('Resumo abre a lista com a competencia da pagina principal; setas, voltar e Inicio mantem o mes', async ({ page }) => {
    await entrar(page, F);
    await page.goto(`/inicio.html?mes=${MES}`);
    const resumo = page.locator('.mob-atalho[data-modulo="resumo"]');
    await expect(resumo).toHaveAttribute('href', `despesas-mobile.html?mes=${MES}`);
    await expect(resumo).not.toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('.mob-atalho[aria-disabled="true"]')).toHaveCount(2);  // Resumo, Cartoes (MOBILE-03), Receita (MOBILE-04), Despesa (MOBILE-05), Lancamento (MOBILE-06) e Contas (MOBILE-07) habilitados
    await expect(page.locator('.mob-barra-item[data-modulo="resumo"]')).toHaveAttribute('href', `despesas-mobile.html?mes=${MES}`);
    await expect(page.locator('.mob-barra-item[data-modulo="lancar"]')).toHaveAttribute('href', `lancamento-mobile.html?mes=${MES}`);  // FIN-MVP-MOBILE-06

    await resumo.click();
    await page.waitForURL(`**/despesas-mobile.html?mes=${MES}`);
    await esperarLista(page, MES);
    await expect(page.locator('#mob-competencia')).toHaveText('Abr/2031');
    await expect(page.locator('#mob-perfil')).toHaveText('Perfil F (ficticio)');
    await expect(page.locator('.mob-barra-item.ativo')).toHaveText('Resumo');
    // grupos recolhidos ao abrir
    expect(await page.locator('.mob-grupo-cabecalho').count()).toBeGreaterThan(0);
    await expect(page.locator('.mob-grupo-cabecalho[aria-expanded="true"]')).toHaveCount(0);
    for (const itens of await page.locator('.mob-grupo-itens').all()) await expect(itens).toBeHidden();

    await page.click('#mob-mes-seguinte');
    await esperarLista(page, '2031-05');
    await expect(page.locator('#mob-competencia')).toHaveText('Mai/2031');
    expect(page.url()).toContain('mes=2031-05');
    await page.reload();
    await esperarLista(page, '2031-05');
    await expect(page.locator('#mob-voltar')).toHaveAttribute('href', 'inicio.html?mes=2031-05');
    await page.click('#mob-voltar');
    await page.waitForURL('**/inicio.html?mes=2031-05');
    await expect(page.locator('#mob-competencia')).toHaveText('Mai/2031');

    await page.click('#mob-mes-anterior');
    await page.locator('.mob-barra-item[data-modulo="resumo"]').click();
    await page.waitForURL(`**/despesas-mobile.html?mes=${MES}`);
    await esperarLista(page, MES);
    await page.locator('.mob-barra-item', { hasText: 'Início' }).click();
    await page.waitForURL(`**/inicio.html?mes=${MES}`);
});

test('mesmos grupos, linhas, valores e totais do desktop; accordion; sem Categoria, Status nem primeira Data', async ({ page }) => {
    await entrar(page, F);
    await abrirLista(page);
    await criarAvulsa(page, 'Conserto F', '420.33', '2031-04-15', 'Peça trocada (ficticio)');
    await criarAvulsa(page, 'Presente F', '75.50', '2031-04-08');
    await criarAvulsa(page, 'Mercado F com uma descricao bem longa para conferir o corte', '310.00', '2031-04-20');
    await abrirLista(page);

    await evidencia(page, 'lista-recolhida-390x844');
    const seq = await conferirIgualAoDesktop(page, MES);
    expect(seq.filter((s) => s.startsWith('G:'))).toEqual(['G:DESPESAS RECORRENTES', 'G:DESPESAS AVULSAS']);
    expect(seq).toContain('L:Diarista F=R$ 1.000,00');  // 5 tercas de abril, agrupadas como no desktop

    // accordion: varios abertos ao mesmo tempo; fechar um nao fecha o outro
    await expandir(page, 'DESPESAS RECORRENTES');
    await expandir(page, 'DESPESAS AVULSAS');
    await expect(page.locator('.mob-grupo-cabecalho[aria-expanded="true"]')).toHaveCount(2);
    await evidencia(page, 'grupos-abertos-390x844');
    await cabecalho(page, 'DESPESAS RECORRENTES').click();
    await expect(cabecalho(page, 'DESPESAS RECORRENTES')).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator('#mob-grupo-DESPESAS_RECORRENTES')).toBeHidden();
    await expect(page.locator('#mob-grupo-DESPESAS_AVULSAS')).toBeVisible();

    // linha: descricao (vencimento discreto) | valor | seta; sem categoria, status nem segunda data
    const conserto = linha(page, 'Conserto F');
    await expect(conserto.locator('.mob-linha-data')).toHaveText('Venc. 15/04');
    expect(await conserto.evaluate((e) => e.children.length)).toBe(3);
    await expect(conserto).not.toContainText(/Moradia|Pendente|Pago|Abr\/2031/);
    await expect(page.locator('#mob-lista')).not.toContainText(/Moradia|Pendente/);
    // valores alinhados a direita, na mesma coluna
    const direitas = await page.locator('#mob-grupo-DESPESAS_AVULSAS .mob-linha-valor').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().right)));
    expect(new Set(direitas).size).toBe(1);

    // sem rolagem horizontal; descricao longa cortada sem empurrar o valor
    await expandirTodos(page);
    for (const largura of [320, 360, 375, 390, 412, 430]) {
        await page.setViewportSize({ width: largura, height: 800 });
        const medida = await page.evaluate(() => ({ rolagem: document.documentElement.scrollWidth, largura: window.innerWidth,
            valores: [...document.querySelectorAll('.mob-linha-valor, .mob-grupo-total')].map((e) => e.getBoundingClientRect().right) }));
        expect(medida.rolagem, `largura ${largura}`).toBeLessThanOrEqual(medida.largura);
        if (largura === 320) await evidencia(page, 'grupos-abertos-320');
        for (const direita of medida.valores) expect(direita, `largura ${largura}`).toBeLessThanOrEqual(largura);
    }
    await page.setViewportSize(CELULAR);
});

test('detalhes e pagamento pelo fluxo do desktop; lista e totais atualizados, sem duplicar', async ({ page }) => {
    await entrar(page, F);
    await abrirLista(page);
    await abrirDetalhes(page, 'DESPESAS AVULSAS', 'Conserto F');
    const corpo = page.locator('#mob-folha-corpo');
    await expect(corpo.locator('.mob-folha-valor')).toHaveText(/R\$\s420,33/);
    const pares = await corpo.locator('.mob-detalhes').evaluate((dl) => Object.fromEntries([...dl.querySelectorAll('dt')].map((dt) => [dt.textContent, dt.nextElementSibling.textContent])));
    expect(pares).toMatchObject({ Vencimento: '15/04/2031', 'Competência': 'Abr/2031', 'Situação': 'Pendente', Categoria: 'Moradia',
        'Recorrência': 'Não', 'Observações': 'Peça trocada (ficticio)' });
    expect(await folha(page).locator('.mob-botao').allTextContents()).toEqual(['Pagar', 'Editar', 'Excluir']);
    await evidencia(page, 'detalhes', false);

    await botaoFolha(page, 'Pagar').click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Pagar: Conserto F');
    const conta = folha(page).locator('select').first();
    expect(await conta.locator('option').allTextContents()).toEqual(['Selecione...', 'Conta F (ficticia) (Banco ficticio)', 'Conta F2 (ficticia) (Banco ficticio)']);
    await botaoFolha(page, 'Confirmar pagamento').click();
    await expect(folha(page).locator('.mob-mensagem')).toHaveText('Selecione a conta bancária para executar o pagamento.');
    // outro valor: a diferenca exige classificacao e justificativa (FIN-MOVIMENTACOES-1)
    await folha(page).locator('input[value="parcial"]').check();
    await folha(page).locator('input[type="number"]').fill('430.33');
    await conta.selectOption({ label: 'Conta F (ficticia) (Banco ficticio)' });
    await botaoFolha(page, 'Confirmar pagamento').click();
    await expect(folha(page).locator('.mob-mensagem')).toHaveText('Classifique a diferença e escreva a justificativa.');
    expect((await contaDoMes(page, /^Conserto F/))[0].status_pagamento).toBe('Pendente');
    await folha(page).locator('.mob-campo', { hasText: 'Classificação da diferença' }).locator('select').selectOption('JUROS');
    await folha(page).locator('.mob-campo', { hasText: 'Justificativa' }).locator('textarea').fill('Multa por atraso (ficticio)');
    await evidencia(page, 'pagamento-outro-valor', false);
    await botaoFolha(page, 'Confirmar pagamento').click();
    await expect(folha(page)).toBeHidden();
    await expect(aviso(page)).toContainText(/Despesa paga: R\$\s430,33 debitados de Conta F \(ficticia\)/);
    await esperarLista(page, MES);
    // o grupo aberto continua aberto; a linha mostra a despesa paga
    await expect(cabecalho(page, 'DESPESAS AVULSAS')).toHaveAttribute('aria-expanded', 'true');
    await expect(linha(page, 'Conserto F')).toHaveClass(/paga/);
    await expect(linha(page, 'Conserto F').locator('.mob-linha-data')).toHaveText('Venc. 15/04 · paga');
    await evidencia(page, 'apos-pagamento');

    const [conserto] = await contaDoMes(page, /^Conserto F/);
    expect(conserto.status_pagamento).toBe('Pago');
    // um pagamento so (sem duplicar), com o valor pago, a conta escolhida e a diferenca classificada
    const pagamento = (await chamarRpc(page, 'dados_pagamento_despesa', { p_perfil_id: PERFIL_F, p_conta_id: conserto.id })).corpo;
    expect(pagamento.pagamentos).toHaveLength(1);
    expect(pagamento.pagamentos[0]).toMatchObject({ vigente: true, conta_nome: 'Conta F (ficticia)', valor_pago: 430.33, valor_devido: 420.33,
        tipo_ajuste: 'JUROS', justificativa: 'Multa por atraso (ficticio)' });
    await conferirIgualAoDesktop(page, MES);  // totais atualizados como no desktop
});

test('estorno, edicao bloqueada, cancelamento da obrigacao, exclusao e edicao respeitam as regras', async ({ page }) => {
    await entrar(page, F);
    await abrirLista(page);
    // paga: sem Pagar; edicao e exclusao recusadas pelo banco, com o motivo
    await abrirDetalhes(page, 'DESPESAS AVULSAS', 'Conserto F');
    expect(await folha(page).locator('.mob-botao').allTextContents()).toEqual(['Estornar pagamento', 'Editar', 'Excluir']);
    await botaoFolha(page, 'Editar').click();
    await expect(folha(page).locator('.mob-mensagem.erro')).toContainText('não pode ser editada');
    await botaoFolha(page, 'Fechar').click();
    await abrirDetalhes(page, 'DESPESAS AVULSAS', 'Conserto F');
    await botaoFolha(page, 'Excluir').click();
    await expect(folha(page).locator('.mob-mensagem.erro')).toContainText('não pode ser excluída');
    await botaoFolha(page, 'Fechar').click();

    // estorno: motivo obrigatorio; a despesa volta a pendente
    await abrirDetalhes(page, 'DESPESAS AVULSAS', 'Conserto F');
    await botaoFolha(page, 'Estornar pagamento').click();
    await botaoFolha(page, 'Confirmar estorno').click();
    await expect(folha(page).locator('.mob-mensagem')).toHaveText('Informe o motivo do estorno.');
    await folha(page).locator('textarea').fill('Pagamento em duplicidade (ficticio)');
    await botaoFolha(page, 'Confirmar estorno').click();
    await expect(aviso(page)).toContainText(/Pagamento estornado: R\$\s430,33 devolvidos a Conta F \(ficticia\)/);
    await esperarLista(page, MES);
    await expect(linha(page, 'Conserto F')).not.toHaveClass(/paga/);
    expect((await contaDoMes(page, /^Conserto F/))[0].status_pagamento).toBe('Pendente');

    // pagamento integralmente estornado: excluir vira "Cancelar obrigacao" (P23), distinto da exclusao
    await abrirDetalhes(page, 'DESPESAS AVULSAS', 'Conserto F');
    await botaoFolha(page, 'Excluir').click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Cancelar obrigação');
    await botaoFolha(page, 'Cancelar obrigação').click();
    await expect(aviso(page)).toContainText('Obrigação cancelada');
    await esperarLista(page, MES);
    expect((await contaDoMes(page, /^Conserto F/)).every((c) => c.status_pagamento !== 'Pendente')).toBe(true);

    // exclusao simples, com confirmacao
    await abrirDetalhes(page, 'DESPESAS AVULSAS', 'Presente F');
    await botaoFolha(page, 'Excluir').click();
    await expect(folha(page)).toContainText('Tem certeza que deseja excluir a despesa');
    await botaoFolha(page, 'Excluir').click();
    await expect(aviso(page)).toContainText('Despesa excluída com sucesso');
    await esperarLista(page, MES);
    await expect(linha(page, 'Presente F')).toHaveCount(0);
    expect(await contaDoMes(page, /^Presente F/)).toEqual([]);

    // edicao pela mesma rota do desktop
    await abrirDetalhes(page, 'DESPESAS AVULSAS', 'Mercado F');
    await botaoFolha(page, 'Editar').click();
    await folha(page).locator('.mob-campo', { hasText: 'Nome' }).locator('input').fill('Mercado F editado');
    await folha(page).locator('.mob-campo', { hasText: 'Valor' }).locator('input').fill('315.40');
    await botaoFolha(page, 'Salvar').click();
    await expect(aviso(page)).toContainText('Despesa atualizada com sucesso');
    await esperarLista(page, MES);
    await expect(linha(page, 'Mercado F editado').locator('.mob-linha-valor')).toHaveText(/R\$\s315,40/);
    const [mercado] = await contaDoMes(page, /^Mercado F editado/);
    expect(Number(mercado.valor)).toBe(315.4);

    // recorrente: categoria e competencia mudam na tela Recorrencias
    await abrirDetalhes(page, 'DESPESAS RECORRENTES', 'Internet F');
    await botaoFolha(page, 'Editar').click();
    await expect(folha(page).locator('.mob-campo', { hasText: 'Categoria' }).locator('select')).toBeDisabled();
    await expect(folha(page).locator('.mob-campo', { hasText: 'Competência' }).locator('input')).toBeDisabled();
    await expect(folha(page)).toContainText('tela Recorrências');
    await botaoFolha(page, 'Cancelar').click();

    // recorrente: "esta e as futuras" mostra antes a previa (o mesmo modal do desktop) e interrompe a recorrencia
    await abrirDetalhes(page, 'DESPESAS RECORRENTES', 'Aluguel F');
    await botaoFolha(page, 'Excluir').click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Excluir despesa recorrente');
    await botaoFolha(page, 'Excluir esta e as futuras').click();
    const previa = page.locator('.cf-int-fundo');
    await expect(previa).toBeVisible();
    await expect(previa).toContainText('Excluir esta e as futuras');
    await previa.locator('.cf-int-botao', { hasText: 'Excluir' }).click();
    await expect(aviso(page)).toContainText('Recorrência interrompida');
    await esperarLista(page, MES);
    expect((await contaDoMes(page, /^Aluguel F/)).filter((c) => c.status_pagamento === 'Pendente')).toEqual([]);
    await conferirIgualAoDesktop(page, MES);
});

test('recorrencia semanal agrupada: ocorrencias e pagamento das pendentes em lote', async ({ page }) => {
    await entrar(page, F);
    await abrirLista(page);
    await expandir(page, 'DESPESAS RECORRENTES');
    const diarista = page.locator('#mob-lista .mob-linha[data-agrupador="Diarista F"]');
    await expect(diarista.locator('.mob-linha-data')).toHaveText('0/5 pagas');
    await diarista.click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Diarista F');
    await expect(folha(page).locator('.mob-linha')).toHaveCount(5);
    await evidencia(page, 'semanal-ocorrencias', false);
    // cada ocorrencia abre os proprios detalhes
    await folha(page).locator('.mob-linha').first().click();
    await expect(page.locator('#mob-folha-titulo')).toContainText('Diarista F - ');
    await page.click('#mob-folha-fechar');
    await diarista.click();
    await botaoFolha(page, 'Pagar pendentes (5)').click();
    const pares = await folha(page).locator('.mob-detalhes').evaluate((dl) => Object.fromEntries([...dl.querySelectorAll('dt')].map((dt) => [dt.textContent, dt.nextElementSibling.textContent])));
    expect(pares).toMatchObject({ 'Recorrência': 'Diarista F', 'Forma de pagamento': 'Pix', 'Ocorrências pendentes': '5' });
    expect(pares['Valor total'].replace(/\s/g, ' ')).toBe('R$ 1.000,00');
    await evidencia(page, 'pagamento-lote', false);
    await botaoFolha(page, 'Confirmar pagamento').click();
    await expect(folha(page).locator('.mob-mensagem')).toHaveText('Selecione a conta bancária de débito.');
    await folha(page).locator('select').selectOption({ label: 'Conta F2 (ficticia) (Banco ficticio)' });
    await botaoFolha(page, 'Confirmar pagamento').click();
    await expect(aviso(page)).toContainText('Pagamento em lote concluído');
    await expect(aviso(page)).toContainText('5 ocorrência(s) paga(s)');
    await esperarLista(page, MES);
    await expect(diarista.locator('.mob-linha-data')).toHaveText('5/5 pagas');
    const diaristas = await contaDoMes(page, /^Diarista F - /);
    expect(diaristas).toHaveLength(5);
    expect(diaristas.every((c) => c.status_pagamento === 'Pago')).toBe(true);
    await conferirIgualAoDesktop(page, MES);
});

test('filtros num painel compacto: status, forma de pagamento e busca', async ({ page }) => {
    await entrar(page, F);
    await abrirLista(page);
    await expect(page.locator('#mob-filtro-marca')).toBeHidden();
    await page.click('#mob-filtros');
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Filtros');
    await evidencia(page, 'filtros', false);
    await folha(page).locator('.mob-campo', { hasText: 'Status' }).locator('select').selectOption('pendente');
    await botaoFolha(page, 'Aplicar').click();
    await expect(page.locator('#mob-filtro-marca')).toBeVisible();
    await expandirTodos(page);
    await expect(page.locator('#mob-lista .mob-linha.paga')).toHaveCount(0);
    await expect(page.locator('#mob-total .mob-total-detalhe')).toContainText(/Pagas R\$\s0,00/);

    await page.click('#mob-filtros');
    await folha(page).locator('.mob-campo', { hasText: 'Status' }).locator('select').selectOption('');
    await folha(page).locator('.mob-campo', { hasText: 'Buscar' }).locator('input').fill('internet');
    await botaoFolha(page, 'Aplicar').click();
    await expandirTodos(page);
    expect(await page.locator('#mob-lista .mob-linha-nome').allTextContents()).toEqual([expect.stringMatching(/^Internet F/)]);

    await page.click('#mob-filtros');
    await botaoFolha(page, 'Limpar').click();
    await expect(page.locator('#mob-filtro-marca')).toBeHidden();
    expect(await page.locator('.mob-grupo-cabecalho').count()).toBe(2);
});

test('perfil somente leitura: mesmos grupos do desktop e nenhuma acao de escrita', async ({ page }) => {
    await entrar(page, A);
    await page.evaluate((id) => localStorage.setItem(`cf-perfil-ativo:${id}`, '102'), A.id);  // Empresa: A e leitor
    await abrirLista(page, '2026-11');
    await expect(page.locator('#mob-perfil')).toHaveText('Empresa');
    const seq = await conferirIgualAoDesktop(page, '2026-11');
    expect(seq.some((s) => s.startsWith('L:Contador'))).toBe(true);
    await abrirDetalhes(page, 'DESPESAS AVULSAS', 'Contador');
    await expect(folha(page)).toContainText('Acesso somente de leitura a este perfil.');
    await expect(folha(page).locator('.mob-botao')).toHaveCount(0);
    await evidencia(page, 'somente-leitura', false);
});
