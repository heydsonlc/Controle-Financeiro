// FIN-MVP-CADASTRO-UNIFICADO-01 — integracao do modal unico de cadastro de despesas nos tres modulos (Etapa 4).
// O que cada modulo ja confere no seu spec (despesa direta, compra, recorrencias, consorcio em andamento, somente leitura no
// celular) fica la; aqui: os pontos de entrada e o tipo inicial de cada um, os tipos que passaram a existir em cada origem
// (consorcio e recorrencia no cartao por Despesas e pelo celular), o retorno a origem, o painel de Lancamentos (escolha do
// tipo, abastecimento e entrada/credito no formulario original) e a ausencia de movimento bancario no cadastro.
// Perfil B (desktop) e Perfil G (celular), com datas a partir de 2045, longe dos meses que os outros specs abrem: nada
// daqui gera conta nas competencias deles. Dados FICTICIOS; grava so no banco descartavel.
import { expect, test } from '@playwright/test';

import * as cad from './cadastro.mjs';
import { abrirDespesas, chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';
import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const PERFIL_G = 160;

test.describe.configure({ mode: 'serial' });

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

async function entrar(page, conta, destino = '**/contas.html') {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL(destino);
    // Desktop: a moldura ja escolheu o perfil ativo (perfilAtivoId le o seletor).
    if (/contas/.test(destino)) await expect(page.locator('#perfil-financeiro-switcher')).toHaveAttribute('data-perfil-ativo-id', /^\d+$/);
}

async function rpc(page, funcao, corpo) {
    const r = await chamarRpc(page, funcao, corpo);
    expect(r.status, `${funcao}: ${JSON.stringify(r.corpo)}`).toBe(200);
    return r.corpo;
}

const recorrencia = async (page, perfil, nome) => (await rpc(page, 'recorrencias_do_perfil', { p_perfil_id: perfil })).filter((r) => r.nome === nome);
const consorcio = async (page, perfil, nome) => (await rpc(page, 'consorcios_tela', { p_perfil_id: perfil, p_id: null })).filter((c) => c.nome === nome);
const saldos = async (page, perfil) => (await rpc(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' }))
    .map((c) => [c.id, Number(c.saldo_atual)]);
const TIPOS = ['Despesa direta', 'Compra no cartão', 'Despesa recorrente', 'Consórcio'];

test.describe('desktop', () => {
    test.use({ viewport: { width: 1366, height: 900 } });

    test('Despesas: "Nova despesa" abre o modal em Despesa direta; os quatro tipos; recorrencia e consorcio pelo servico de cada um', async ({ page }) => {
        const dialogos = registrarDialogos(page);
        await entrar(page, B);
        const perfil = await perfilAtivoId(page);
        const antes = await saldos(page, perfil);
        await abrirDespesas(page, '2026-11');
        await page.click('.btn-nova-despesa');
        await cad.esperarModal(page, 'direta');
        await expect(cad.modal(page)).toHaveAttribute('data-origem', 'despesas');
        await expect(page.locator('#cad-tipo option')).toHaveText(TIPOS);
        await expect(page.locator('#modal-despesa')).toBeHidden();  // o modal original fica para a edicao
        const caixa = await cad.modal(page).boundingBox();
        expect(Math.round(caixa.width)).toBe(640);

        // Recorrencia anual em debito automatico, cadastrada inativa (antes: so pela tela Recorrencias).
        await cad.preencherCadastro(page, { tipo: 'recorrente', nome: 'Seguro anual CU', valor: '1200', inicio: '2045-06-10', frequencia: 'anual',
            meio: 'debito_automatico', inativa: true });
        await expect(page.locator('#cad-dia-semana')).toBeHidden();
        const anual = await cad.salvarCadastro(page, { concluir: false });
        expect(anual).toContain('Recorrência “Seguro anual CU” cadastrada (inativa)');
        const gravada = await recorrencia(page, perfil, 'Seguro anual CU');
        expect(gravada.map((r) => [r.tipo_recorrencia, r.meio_pagamento, r.ativo, Boolean(r.conta_bancaria_id), Number(r.valor)]))
            .toEqual([['anual', 'debito_automatico', false, true, 1200]]);

        // "Novo cadastro" no mesmo modal; recorrencia anual no cartao (antes: "em migracao" nesta tela).
        await page.click('#cad-novo');
        await cad.esperarModal(page, 'recorrente');
        await cad.preencherCadastro(page, { nome: 'Anuidade CU', valor: '480', inicio: '2045-08-15', meio: 'cartao', frequencia: 'anual' });
        expect(await cad.salvarCadastro(page, { concluir: false })).toContain('Recorrência no cartão criada.');
        expect((await recorrencia(page, perfil, 'Anuidade CU')).map((r) => [r.tipo_recorrencia, r.meio_pagamento, Boolean(r.cartao_id)]))
            .toEqual([['anual', 'cartao', true]]);

        // Consorcio a partir de Despesas: o servico de consorcios (contrato e cronograma), nunca uma recorrencia comum.
        await page.click('#cad-novo');
        await cad.preencherCadastro(page, { tipo: 'consorcio', nome: 'Consorcio CU Desktop', valor: '300', parcelas: 4, inicio: '2045-03',
            reajuste: 'percentual', valorReajuste: 10, contemplacao: '2045-05' });
        await expect(page.locator('#cad-valor-premio')).toHaveText(/1\.440,00/);  // 300 x 1,20 x 4
        await expect(page.locator('#cad-parcelas-anteriores')).toBeHidden();
        const texto = await cad.salvarCadastro(page, { concluir: false });
        expect(texto).toContain('4 parcelas geradas a partir de 03/2045.');
        await expect(page.locator('#cad-ver-registro')).toHaveAttribute('href', 'recorrencias.html');
        const contrato = await consorcio(page, perfil, 'Consorcio CU Desktop');
        expect(contrato.map((c) => [c.numero_parcelas, c.mes_inicio, c.tipo_reajuste, Number(c.valor_reajuste), c.mes_contemplacao, Number(c.valor_premio)]))
            .toEqual([[4, '2045-03-01', 'percentual', 10, '2045-05-01', 1440]]);
        expect(await recorrencia(page, perfil, 'Consorcio CU Desktop')).toEqual([]);
        const parcelas = [];
        for (const mes of ['2045-03', '2045-04', '2045-05', '2045-06']) {
            parcelas.push(...(await rpc(page, 'contas_do_mes', { p_perfil_id: perfil, p_mes: `${mes}-01` }))
                .filter((c) => c.nome.startsWith('Consorcio CU Desktop - Parcela')).map((c) => [c.nome.slice(-3), Number(c.valor), c.status_pagamento]));
        }
        expect(parcelas).toEqual([['1/4', 300, 'Pendente'], ['2/4', 330, 'Pendente'], ['3/4', 360, 'Pendente'], ['4/4', 390, 'Pendente']]);
        // Nome repetido: o servico recusa e nada e duplicado.
        await page.click('#cad-novo');
        await cad.preencherCadastro(page, { tipo: 'consorcio', nome: 'Consorcio CU Desktop', valor: '300', parcelas: 4, inicio: '2045-03' });
        await cad.salvarComErro(page);
        expect((await consorcio(page, perfil, 'Consorcio CU Desktop')).length).toBe(1);

        // Fechar volta a Despesas, na competencia de origem; nenhum cadastro mexeu em saldo.
        await cad.fecharCadastro(page);
        await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', '11/2026');
        expect(await saldos(page, perfil)).toEqual(antes);
        expect(dialogos).toEqual([]);
    });

    test('Recorrencias: "Nova recorrencia" abre o modal em Despesa recorrente; o formulario lateral so aparece na edicao', async ({ page }) => {
        registrarDialogos(page);
        await entrar(page, B);
        await page.goto('/recorrencias.html');
        await expect(page.locator('#recorrencias-total')).toHaveText(/cadastros? no total/);
        await expect(page.locator('#secao-formulario')).toBeHidden();
        await page.click('#btn-nova-recorrencia');
        await cad.esperarModal(page, 'recorrente');
        await expect(cad.modal(page)).toHaveAttribute('data-origem', 'recorrencias');
        await expect(page.locator('#cad-tipo option')).toHaveText(TIPOS);
        await cad.fecharCadastro(page);
        await expect(page).toHaveURL(/recorrencias\.html/);
        // Edicao: o formulario original, com os dados do registro; cancelar o esconde de novo.
        await page.selectOption('#filtro-status', '');
        await page.fill('#filtro-competencia', '');  // todas as competencias (a recorrencia comeca em 2045)
        await page.locator('#filtro-competencia').dispatchEvent('change');
        const linha = page.locator('#recorrencias-lista .recorrencias-row', { hasText: 'Seguro anual CU' });
        await linha.locator('[data-on-click^="editarRecorrencia"]').click();
        await expect(page.locator('#secao-formulario')).toBeVisible();
        await expect(page.locator('#form-titulo')).toHaveText('Editar recorrencia');
        await expect(page.locator('#nome')).toHaveValue('Seguro anual CU');
        await expect(cad.modal(page)).toHaveCount(0);
        await page.locator('#secao-formulario [data-on-click="fecharFormularioRecorrencia()"]').click();
        await expect(page.locator('#secao-formulario')).toBeHidden();
    });

    test('Lancamentos: escolha do tipo no painel; modal para despesa e compra; formulario original so para abastecimento e entrada/credito', async ({ page }) => {
        registrarDialogos(page);
        await entrar(page, B);
        await page.goto('/lancamentos.html');
        await expect(page.locator('#filtro-mes')).not.toHaveValue('');
        const painel = page.locator('#painel-novo-lancamento');
        await expect(painel).toHaveAttribute('data-modo', 'escolha');
        await expect(page.locator('#cf-lanc-escolha button')).toHaveText(['Despesa direta', 'Compra no cartão', 'Abastecimento', 'Entrada / crédito']);
        await expect(page.locator('#form-lancamento')).toBeHidden();
        // Tipo escolhido na tela: o modal ja abre nele; fechar volta a tela, na escolha.
        await page.click('#cf-lanc-cartao');
        await cad.esperarModal(page, 'compra');
        await expect(cad.modal(page)).toHaveAttribute('data-origem', 'lancamentos');
        await cad.fecharCadastro(page);
        await page.click('#cf-lanc-despesa');
        await cad.esperarModal(page, 'direta');
        await expect(page.locator('#cad-competencia-texto')).toHaveText(/^Competência: \S+\/\d{4}$/);  // a do mes da data (hoje)
        await expect(page.locator('#cad-alterar-competencia')).toBeHidden();
        await cad.fecharCadastro(page);
        await expect(page).toHaveURL(/lancamentos\.html/);
        await expect(painel).toHaveAttribute('data-modo', 'escolha');

        // Entrada / credito: o formulario original, preso ao tipo (as opcoes de despesa ficam indisponiveis).
        await page.click('#cf-lanc-credito');
        await expect(painel).toHaveAttribute('data-modo', 'credito');
        await expect(page.locator('#form-lancamento')).toBeVisible();
        await expect(page.locator('#lancamento-tipo')).toHaveValue('credito');
        await expect(page.locator('#campos-credito')).toBeVisible();
        await expect(page.locator('#lancamento-tipo option[value="direto"]')).toHaveJSProperty('disabled', true);
        await expect(page.locator('#lancamento-tipo option[value="cartao"]')).toHaveJSProperty('disabled', true);
        await page.click('.lanc-panel-action[title="Limpar formulario"]');
        await expect(painel).toHaveAttribute('data-modo', 'escolha');

        // "+" da barra de acoes: a mesma escolha.
        await page.click('#btn-novo-lancamento');
        await expect(page.locator('#cf-lanc-escolha')).toBeVisible();
        // Abastecimento: o formulario original (despesa ou compra e abastecimento numa transacao; o fluxo completo esta em
        // lancamentos_abastecimento.spec). Entrada/credito fica indisponivel neste modo, e a despesa comum nao e gravada por aqui.
        await expect(page.locator('#cf-lanc-abastecimento')).toBeEnabled();
        await page.click('#cf-lanc-abastecimento');
        await expect(painel).toHaveAttribute('data-modo', 'abastecimento');
        await expect(page.locator('#form-lancamento')).toBeVisible();
        await expect(page.locator('#cf-lanc-modo-dica')).toContainText('Tudo é gravado junto.');
        await expect(page.locator('#lancamento-tipo option[value="credito"]')).toHaveJSProperty('disabled', true);
        await page.selectOption('#lancamento-tipo', 'direto');
        await expect(page.locator('#bloco-abastecimento')).toBeVisible();  // a categoria Combustivel ja vem escolhida
        await page.click('.lanc-panel-action[title="Limpar formulario"]');
        await expect(painel).toHaveAttribute('data-modo', 'escolha');
    });

    test('perfil somente leitura: sem cadastro em Despesas, Recorrencias e Lancamentos', async ({ page }) => {
        registrarDialogos(page);
        await entrar(page, A);
        await trocarPerfil(page, 'Empresa');
        await expect(page.locator('.btn-nova-despesa')).toBeHidden();
        await page.goto('/recorrencias.html');
        await expect(page.locator('#recorrencias-total')).toHaveText(/cadastros? no total/);
        await expect(page.locator('#btn-nova-recorrencia')).toBeHidden();
        await expect(page.locator('#secao-formulario')).toBeHidden();
        await page.goto('/lancamentos.html');
        await expect(page.locator('#filtro-mes')).not.toHaveValue('');
        await expect(page.locator('#btn-novo-lancamento')).toBeHidden();
        await expect(page.locator('#painel-novo-lancamento')).toBeHidden();
        await expect(cad.modal(page)).toHaveCount(0);
    });
});

test.describe('celular', () => {
    test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

    test('consorcio pelo celular (Nova Despesa): contrato e cronograma pelo servico de consorcios, sem movimento bancario', async ({ page }) => {
        await entrar(page, G, '**/inicio.html**');
        const antes = await saldos(page, PERFIL_G);
        await page.goto('/despesa-nova-mobile.html?mes=2031-06');
        await cad.esperarModal(page, 'direta');
        await cad.preencherCadastro(page, { tipo: 'consorcio', nome: 'Consorcio CU Celular', valor: '250', parcelas: 3, inicio: '2046-02', categoria: 'Moradia',
            reajuste: 'fixo', valorReajuste: 5, contemplacao: '2046-04' });
        await expect(page.locator('#cad-valor-premio')).toHaveText(/780,00/);  // (250 + 2 x 5) x 3
        // Tela cheia no celular: cabecalho e rodape fixos, sem rolagem horizontal.
        const medidas = await page.evaluate(() => {
            const m = document.querySelector('.cad-modal').getBoundingClientRect();
            const r = document.querySelector('.cad-rodape').getBoundingClientRect();
            return { largura: Math.round(m.width), rodape: r.bottom <= window.innerHeight + 0.5, rolagem: document.documentElement.scrollWidth > window.innerWidth };
        });
        expect(medidas).toEqual({ largura: 390, rodape: true, rolagem: false });
        await page.locator('#cad-salvar').dblclick();
        await expect(cad.confirmacao(page)).toContainText('Consórcio “Consorcio CU Celular” cadastrado');
        await expect(cad.confirmacao(page)).toContainText('3 parcelas geradas a partir de 02/2046.');
        await expect(page.locator('#cad-ver-registro')).toHaveAttribute('href', 'recorrencias-mobile.html');
        const contrato = await consorcio(page, PERFIL_G, 'Consorcio CU Celular');
        expect(contrato.map((c) => [c.numero_parcelas, c.mes_inicio, Number(c.valor_premio)])).toEqual([[3, '2046-02-01', 780]]);  // toque duplo: um contrato
        const parcelas = (await rpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_G, p_mes: '2046-03-01' }))
            .filter((c) => c.nome.startsWith('Consorcio CU Celular')).map((c) => [Number(c.valor), c.status_pagamento]);
        expect(parcelas).toEqual([[255, 'Pendente']]);
        expect(await saldos(page, PERFIL_G)).toEqual(antes);
        // Concluir volta a pagina principal, na competencia de origem.
        await page.click('#cad-concluir');
        await page.waitForURL('**/inicio.html?mes=2031-06');
    });

    test('Recorrencias no celular: "+" abre o modal em Despesa recorrente; cancelar volta a lista sem gravar', async ({ page }) => {
        await entrar(page, G, '**/inicio.html**');
        await page.goto('/recorrencias-mobile.html');
        await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
        const antes = (await rpc(page, 'recorrencias_do_perfil', { p_perfil_id: PERFIL_G })).length;
        await page.click('#mob-nova');
        await cad.esperarModal(page, 'recorrente');
        await expect(cad.modal(page)).toHaveAttribute('data-origem', 'recorrencias');
        await expect(page.locator('#cad-tipo option')).toHaveText(TIPOS);
        await cad.preencherCadastro(page, { nome: 'Rascunho CU', valor: '10', inicio: '2046-01-10' });
        await cad.fecharCadastro(page);
        await expect(page).toHaveURL(/recorrencias-mobile\.html/);
        expect((await rpc(page, 'recorrencias_do_perfil', { p_perfil_id: PERFIL_G })).length).toBe(antes);
    });
});
