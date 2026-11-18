// FIN-MVP-CADASTRO-UNIFICADO-02 — despesa direta cadastrada e paga na mesma operacao, pelo modal unico: Despesas e
// Lancamentos no desktop (Perfil B) e Nova Despesa no celular (Perfil G). Conferido na tela e no banco: opcao desmarcada
// por padrao; so na despesa direta; marcada, pede conta e data; uma despesa, um pagamento e um debito no saldo; toque duplo
// nao duplica; recusa do pagamento nao deixa despesa. No fim cada pagamento e estornado (os saldos voltam ao que eram
// para os outros arquivos). Datas em 2019, antes do inicio de qualquer recorrencia dos cenarios: abrir a competencia nao gera nada (um mes futuro geraria as recorrencias do perfil ate la e mudaria os outros specs). Dados FICTICIOS; so no banco descartavel.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import * as cad from './cadastro.mjs';
import { abrirDespesas, chamarRpc, despesa, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const PERFIL_G = 160;
const PENDENTE = 'Salvar despesa pendente';
const PAGAR = 'Salvar como paga';
const EVIDENCIAS = process.env.CF_CU2_EVIDENCIAS || '';  // capturas para a homologacao (opcional; dados ficticios)

async function evidencia(page, nome) {
    if (!EVIDENCIAS) return;
    mkdirSync(EVIDENCIAS, { recursive: true });
    await page.screenshot({ path: path.join(EVIDENCIAS, nome + '.png') });
}

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
    if (/contas/.test(destino)) await expect(page.locator('#perfil-financeiro-switcher')).toHaveAttribute('data-perfil-ativo-id', /^\d+$/);
}

async function rpc(page, funcao, corpo) {
    const r = await chamarRpc(page, funcao, corpo);
    expect(r.status, `${funcao}: ${JSON.stringify(r.corpo)}`).toBe(200);
    return r.corpo;
}

const centavos = (v) => Math.round(Number(v) * 100);
const saldos = async (page, perfil) => Object.fromEntries((await rpc(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' }))
    .map((c) => [c.id, centavos(c.saldo_atual)]));
const doMes = async (page, perfil, mes, nome) => (await rpc(page, 'contas_do_mes', { p_perfil_id: perfil, p_mes: `${mes}-01` })).filter((c) => c.nome === nome);

// Marca a opcao, espera as contas e escolhe a primeira (ou confere a unica ja escolhida). Devolve o id da conta.
async function marcarPagamento(page, data) {
    await expect(page.locator('#cad-paga')).not.toBeChecked();
    await expect(page.locator('#cad-salvar')).toHaveText(PENDENTE);
    await expect(page.locator('.cad-pagamento-campos')).toBeHidden();
    await page.check('#cad-paga');
    await expect(page.locator('#cad-salvar')).toHaveText(PAGAR);
    await expect(page.locator('.cad-pagamento-campos')).toHaveAttribute('data-contas', /^[1-9]\d*$/);
    const conta = page.locator('#cad-conta-pagamento');
    if (!(await conta.inputValue())) await conta.selectOption({ index: 1 });
    if (data) await page.fill('#cad-data-pagamento', data);
    return Number(await conta.inputValue());
}

// O que o banco gravou para a despesa: uma conta paga, um debito vigente na conta escolhida, saldo menor no valor exato.
async function conferirPaga(page, perfil, { nome, mes, valor, contaBancaria, data, antes }) {
    const linhas = await doMes(page, perfil, mes, nome);
    expect(linhas.length, 'uma despesa so').toBe(1);
    expect(linhas[0].status_pagamento).toBe('Pago');
    const pagamento = await rpc(page, 'dados_pagamento_despesa', { p_perfil_id: perfil, p_conta_id: linhas[0].id });
    expect(pagamento.despesa.paga).toBe(true);
    expect(String(pagamento.despesa.data_pagamento).slice(0, 10)).toBe(data);
    const depois = await saldos(page, perfil);
    for (const [id, saldo] of Object.entries(antes)) {
        expect(depois[id], `saldo da conta ${id}`).toBe(Number(id) === contaBancaria ? saldo - centavos(valor) : saldo);
    }
    return { conta: linhas[0], pagamento };
}

// Desfaz o pagamento pelo estorno oficial (o saldo volta); a despesa fica pendente em 2019.
async function estornar(page, perfil, { conta, pagamento }, antes) {
    const vigentes = pagamento.pagamentos.filter((p) => p.vigente);
    expect(vigentes.length, 'um pagamento vigente').toBe(1);
    const movimento = vigentes[0].movimento_id;
    await rpc(page, 'estornar_pagamento_despesa', { p_perfil_id: perfil, p_conta_id: conta.id, p_movimento_id: movimento,
        p_dados: { motivo: 'limpeza do teste', data_estorno: '2019-03-20' }, p_chave: crypto.randomUUID() });
    expect(await saldos(page, perfil)).toEqual(antes);
}

test.describe('desktop', () => {
    test.use({ viewport: { width: 1366, height: 900 } });

    test('Despesas: opcao desmarcada por padrao e so na despesa direta; marcada, cadastra e paga numa operacao', async ({ page }) => {
        test.setTimeout(90 * 1000);
        registrarDialogos(page);
        await entrar(page, B);
        const perfil = await perfilAtivoId(page);
        const antes = await saldos(page, perfil);
        await abrirDespesas(page, '2019-02');
        await page.click('.btn-nova-despesa');
        await cad.esperarModal(page, 'direta');
        await expect(page.locator('#cad-pagamento')).toContainText('Registrar esta despesa como paga');
        // So na despesa direta: os outros tipos nao tem a opcao e o botao volta a "Salvar".
        for (const tipo of ['compra', 'recorrente', 'consorcio']) {
            await cad.escolherTipo(page, tipo);
            await expect(page.locator('#cad-paga')).toHaveCount(0);
            await expect(page.locator('#cad-salvar')).toHaveText('Salvar');
        }
        await cad.escolherTipo(page, 'direta');
        await cad.preencherCadastro(page, { nome: 'Farmacia Pix CU2', valor: '87.40', vencimento: '2019-03-10' });
        await evidencia(page, 'desktop-1-opcao-desmarcada');
        const contaBancaria = await marcarPagamento(page, '2019-03-10');
        await evidencia(page, 'desktop-2-opcao-marcada');

        // Sem conta nem data: a tela recusa antes de enviar.
        await page.selectOption('#cad-conta-pagamento', '');
        await page.click('#cad-salvar');
        await expect(cad.erroDoCampo(page, 'cad-conta-pagamento')).toHaveText('Selecione a conta bancária do pagamento.');
        expect(await doMes(page, perfil, '2019-02', 'Farmacia Pix CU2')).toEqual([]);
        await page.selectOption('#cad-conta-pagamento', String(contaBancaria));

        await page.locator('#cad-salvar').dblclick();  // toque duplo: uma despesa e um pagamento
        await expect(cad.confirmacao(page)).toContainText('“Farmacia Pix CU2” cadastrada e paga');
        await expect(cad.confirmacao(page)).toContainText(/Despesa salva na competência 02\/2019 e paga: R\$\s*87,40 debitados de /);
        await expect(cad.confirmacao(page)).toContainText('Estornar');
        await evidencia(page, 'desktop-3-confirmacao');
        await page.click('#cad-concluir');
        await expect(cad.modal(page)).toHaveCount(0);
        // A lista ja mostra a despesa paga (sem entrar de novo nela).
        await expect(despesa(page, 'Farmacia Pix CU2')).toHaveCount(1);
        await expect(despesa(page, 'Farmacia Pix CU2').locator('.status-badge')).toContainText(/Pag[ao]/);
        const gravado = await conferirPaga(page, perfil, { nome: 'Farmacia Pix CU2', mes: '2019-02', valor: '87.40', contaBancaria, data: '2019-03-10', antes });

        // Desmarcada (padrao): pendente, sem movimento, como sempre.
        await page.click('.btn-nova-despesa');
        await cad.esperarModal(page, 'direta');
        await expect(page.locator('#cad-paga')).not.toBeChecked();
        await cad.preencherCadastro(page, { nome: 'Mercado pendente CU2', valor: '30', vencimento: '2019-03-12' });
        expect(await cad.salvarCadastro(page)).toContain('cadastrada como pendente');
        expect((await doMes(page, perfil, '2019-02', 'Mercado pendente CU2')).map((c) => c.status_pagamento)).toEqual(['Pendente']);
        const meio = await saldos(page, perfil);
        expect(meio[contaBancaria]).toBe(antes[contaBancaria] - 8740);

        // A edicao continua sem o campo de pagamento.
        await expect(page.locator('#modal-despesa #pago:visible')).toHaveCount(0);
        await estornar(page, perfil, gravado, antes);
    });

    test('Lancamentos: a mesma opcao no modal aberto pelo painel; a despesa paga aparece na lista', async ({ page }) => {
        test.setTimeout(90 * 1000);
        registrarDialogos(page);
        await entrar(page, B);
        const perfil = await perfilAtivoId(page);
        const antes = await saldos(page, perfil);
        await page.goto('/lancamentos.html');
        await expect(page.locator('#filtro-mes')).not.toHaveValue('');
        await page.click('#cf-lanc-despesa');
        await cad.esperarModal(page, 'direta');
        await expect(cad.modal(page)).toHaveAttribute('data-origem', 'lancamentos');
        await cad.preencherCadastro(page, { nome: 'Padaria debito CU2', valor: '12.50', vencimento: '2019-03-05' });
        const contaBancaria = await marcarPagamento(page, '2019-03-05');
        const cargas = Number(await page.locator('#lista-lancamentos').getAttribute('data-cargas')) || 0;
        await page.click('#cad-salvar');
        await expect(cad.confirmacao(page)).toContainText('“Padaria debito CU2” cadastrada e paga');
        await page.click('#cad-concluir');
        await expect.poll(async () => Number(await page.locator('#lista-lancamentos').getAttribute('data-cargas')) || 0, { timeout: 20000 }).toBeGreaterThan(cargas);
        await page.fill('#filtro-mes', '');
        await page.locator('#filtro-mes').dispatchEvent('change');
        await expect(page.locator('#lista-lancamentos .tbl-row', { hasText: 'Padaria debito CU2' })).toHaveCount(1);
        // Em Lancamentos a competencia e o mes da propria data.
        const gravado = await conferirPaga(page, perfil, { nome: 'Padaria debito CU2', mes: '2019-03', valor: '12.50', contaBancaria, data: '2019-03-05', antes });
        await estornar(page, perfil, gravado, antes);
    });
});

test.describe('celular', () => {
    test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

    test('Nova Despesa no celular: opcao, conta e data cabem na tela; cadastra e paga; recusa do banco nao deixa despesa', async ({ page }) => {
        test.setTimeout(90 * 1000);
        await entrar(page, G, '**/inicio.html**');
        const antes = await saldos(page, PERFIL_G);
        await page.goto('/despesa-nova-mobile.html?mes=2019-02');
        await cad.esperarModal(page, 'direta');
        await cad.preencherCadastro(page, { nome: 'Feira dinheiro CU2', valor: '45', vencimento: '2019-03-08' });
        const contaBancaria = await marcarPagamento(page, '2019-03-08');
        const medidas = await page.evaluate(() => ({
            rolagem: document.documentElement.scrollWidth > window.innerWidth,
            campos: [...document.querySelectorAll('.cad-pagamento-campos .mob-campo')].map((c) => Math.round(c.getBoundingClientRect().right)),
        }));
        expect(medidas.rolagem).toBe(false);
        // O rotulo do botao cabe inteiro, marcado e desmarcado.
        const cabe = () => page.locator('#cad-salvar').evaluate((b) => b.scrollWidth <= b.clientWidth);
        expect(await cabe(), PAGAR).toBe(true);
        await page.uncheck('#cad-paga');
        await expect(page.locator('#cad-salvar')).toHaveText(PENDENTE);
        expect(await cabe(), PENDENTE).toBe(true);
        await evidencia(page, 'celular-0-opcao-desmarcada');
        await page.check('#cad-paga');
        await page.locator('#cad-pagamento').scrollIntoViewIfNeeded();
        await evidencia(page, 'celular-1-opcao-marcada');
        for (const direita of medidas.campos) expect(direita).toBeLessThanOrEqual(390);

        // Recusa do banco no pagamento (conta que deixou de valer): nada e gravado, nem a despesa.
        await page.locator('#cad-conta-pagamento').evaluate((s) => { const o = s.options[s.selectedIndex]; o.value = '999999'; });
        await page.click('#cad-salvar');
        await expect(cad.mensagem(page)).toContainText('Nada foi gravado');
        expect(await doMes(page, PERFIL_G, '2019-02', 'Feira dinheiro CU2')).toEqual([]);
        expect(await saldos(page, PERFIL_G)).toEqual(antes);
        await page.locator('#cad-conta-pagamento').evaluate((s, id) => { s.options[s.selectedIndex].value = String(id); }, contaBancaria);

        await page.click('#cad-salvar');
        await expect(cad.confirmacao(page)).toContainText('“Feira dinheiro CU2” cadastrada e paga');
        const gravado = await conferirPaga(page, PERFIL_G, { nome: 'Feira dinheiro CU2', mes: '2019-02', valor: '45', contaBancaria, data: '2019-03-08', antes });
        await estornar(page, PERFIL_G, gravado, antes);
    });
});
