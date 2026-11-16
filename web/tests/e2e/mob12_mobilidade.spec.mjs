// FIN-MOBILE-12 — Mobilidade mobile (mobilidade-mobile.html), com dados FICTICIOS: usuario G (titular do "Perfil G", com o
// veiculo "Flex G") e o leitor H. Veiculos, Abastecer (o formulario homologado do Registrar Lancamento, com o veiculo ja
// escolhido), Historico e Resumo. Os abastecimentos deste arquivo sao de 03/2024 e tem descricao propria, para nao tocar
// nas competencias nem nos nomes que os outros testes conferem. Cada efeito e conferido pelas consultas do desktop.
// Grava so no banco descartavel. Ordem fixa (serial).
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import crypto from 'node:crypto';

import { expect, test } from '@playwright/test';

import { chamarRpc } from './despesas.mjs';

const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const H = { email: process.env.CF_EMAIL_H || 'usuario.h@teste.local', senha: process.env.CF_SENHA_H };
const C = { email: process.env.CF_EMAIL_C || 'usuario.c@teste.local', senha: process.env.CF_SENHA_C };
const EVIDENCIAS = process.env.CF_EVIDENCIAS_DIR;
const PERFIL_G = 160;
const VEICULO = 'Flex G (ficticio)';
const MES = '2024-03';
const HOJE = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());

test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (req) => { if (new URL(req.url()).pathname.startsWith('/api/')) problemas.push(`pedido a /api/: ${req.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP, erros de JS ou pedidos a /api/').toEqual([]);
});

async function evidencia(page, nome) {
    if (!EVIDENCIAS) return;
    mkdirSync(EVIDENCIAS, { recursive: true });
    await page.screenshot({ path: path.join(EVIDENCIAS, `${nome}.png`), fullPage: true });
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

const carregada = (page) => expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
const folha = (page) => page.locator('#mob-folha');
const cartao = (page, nome) => page.locator('.mob-veiculo', { has: page.locator('.mob-veiculo-nome', { hasText: nome }) });
const campo = (page, rotulo) => page.locator('#mob-cadastro .mob-campo', { has: page.locator('xpath=./span[1]', { hasText: new RegExp(`^${rotulo}`) }) });
const controle = (page, rotulo) => campo(page, rotulo).locator('input, select, textarea, output').first();
const veiculoG = async (page) => (await rpc(page, 'veiculos_tela', { p_perfil_id: PERFIL_G, p_id: null })).find((v) => v.nome === VEICULO);
const historicoG = async (page, id) => rpc(page, 'abastecimentos_veiculo_tela', { p_perfil_id: PERFIL_G, p_veiculo_id: id });

async function semRolagemHorizontal(page, nome) {
    for (const [largura, altura] of [[320, 568], [375, 667], [390, 844], [430, 932]]) {
        await page.setViewportSize({ width: largura, height: altura });
        const medida = await page.evaluate(() => ({
            rolagem: document.documentElement.scrollWidth - window.innerWidth,
            fora: [...document.querySelectorAll('.mob-cabecalho, .mob-competencia, .mob-veiculo, .mob-veiculo-acoes .mob-botao, .mob-barra-item, .mob-abastecimento, .mob-grafico')]
                .filter((e) => e.offsetParent !== null).filter((e) => { const r = e.getBoundingClientRect(); return r.left < -0.5 || r.right > window.innerWidth + 0.5; }).length,
            // os botoes do veiculo na mesma linha, com a altura do botao compacto ja homologado (38 px)
            acoes: [...document.querySelectorAll('.mob-veiculo')].every((v) => {
                const caixas = [...v.querySelectorAll('.mob-veiculo-acoes .mob-botao')].map((b) => b.getBoundingClientRect());
                return new Set(caixas.map((r) => Math.round(r.top))).size === 1 && caixas.every((r) => Math.round(r.height) === 38);
            }),
        }));
        expect(medida, `${nome} ${largura}x${altura}`).toEqual({ rolagem: 0, fora: 0, acoes: true });
        if (largura === 320 || largura === 390) await evidencia(page, `mobile12-${nome}-${largura}`);
    }
    await page.setViewportSize({ width: 390, height: 844 });
}

// Abastecer pelo cartao do veiculo: o formulario homologado, com o veiculo ja escolhido e a despesa como conta a pagar.
async function abastecer(page, { data, hodometro, valor, preco, descricao }) {
    const veiculo = await veiculoG(page);
    await cartao(page, VEICULO).locator('[data-acao="abastecer"]').click();
    await page.waitForURL(`**/lancamento-mobile.html?mes=*&tipo=abastecimento&veiculo=${veiculo.id}`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
    await expect(controle(page, 'Veículo')).toHaveValue(String(veiculo.id));
    await controle(page, 'Data').fill(data);
    await controle(page, 'Hodômetro').fill(String(hodometro));
    await controle(page, 'Combustível').selectOption('gasolina');
    await controle(page, 'Preço por litro').fill(preco);
    await controle(page, 'Valor total').fill(valor);
    await controle(page, 'Descrição').fill(descricao);
    await expect(controle(page, 'Meio de pagamento').locator('option')).toHaveText(['Conta a pagar', 'Cartão de crédito']);
    await page.click('#mob-salvar');
    await expect(page.locator('#mob-confirmacao')).toContainText(`“${descricao}” registrado`);
}

test('veiculos, abastecer pelo formulario homologado, historico e resumo do veiculo', async ({ page }) => {
    await entrar(page, G);
    const veiculo = await veiculoG(page);
    const antes = (await historicoG(page, veiculo.id)).abastecimentos.length;
    // Pagina principal: o atalho novo abre o modulo com a competencia.
    await page.locator('.mob-atalho[data-modulo="mobilidade"]').click();
    await page.waitForURL(`**/mobilidade-mobile.html?mes=${HOJE.slice(0, 7)}`);
    await carregada(page);
    await expect(page.locator('.mob-titulo')).toHaveText('Mobilidade');
    await expect(page.locator('#mob-perfil')).toContainText('Perfil G');
    await expect(page.locator('#mob-somente-leitura')).toBeHidden();
    await expect(page.locator('#mob-abastecer')).toBeVisible();
    const total = (await rpc(page, 'veiculos_tela', { p_perfil_id: PERFIL_G, p_id: null })).length;
    await expect(page.locator('.mob-veiculo')).toHaveCount(total);
    await expect(cartao(page, VEICULO).locator('.mob-veiculo-acoes .mob-botao')).toHaveText(['Abastecer', 'Histórico', 'Resumo']);
    await expect(cartao(page, VEICULO).locator('.mob-veiculo-combustivel dd')).toHaveText('Flex');
    await semRolagemHorizontal(page, 'veiculos');

    // Dois abastecimentos de 03/2024 (40 L cada, 400 km entre eles), pelo formulario homologado.
    await page.goto(`/mobilidade-mobile.html?mes=${MES}`);
    await carregada(page);
    await expect(page.locator('#mob-competencia')).toHaveText('Mar/2024');
    await abastecer(page, { data: '2024-03-10', hodometro: 1000, valor: '200', preco: '5.000', descricao: 'Abast mobile 12 A (ficticio)' });
    await page.goto(`/mobilidade-mobile.html?mes=${MES}`);
    await carregada(page);
    await abastecer(page, { data: '2024-03-20', hodometro: 1400, valor: '220', preco: '5.500', descricao: 'Abast mobile 12 B (ficticio)' });
    // No banco: os dois abastecimentos vinculados a contas a pagar da competencia 03/2024, pela regra do Financeiro.
    const h = await historicoG(page, veiculo.id);
    expect(h.abastecimentos.length).toBe(antes + 2);
    const novos = h.abastecimentos.filter((a) => String(a.data_abastecimento).startsWith(MES));
    expect(novos.map((a) => [a.data_abastecimento, Number(a.hodometro_km), Number(a.valor_total), Number(a.litros), a.situacao_vinculo, Number(a.km_rodados || 0)]))
        .toEqual([['2024-03-20', 1400, 220, 40, 'VINCULADO', 400], ['2024-03-10', 1000, 200, 40, 'VINCULADO', 0]]);
    const contas = (await rpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_G, p_mes: `${MES}-01` })).filter((c) => /^Abast mobile 12/.test(c.nome));
    expect(contas.map((c) => [c.nome, Number(c.valor), c.categoria_nome]).sort()).toEqual([
        ['Abast mobile 12 A (ficticio)', 200, 'Combustível'], ['Abast mobile 12 B (ficticio)', 220, 'Combustível']]);

    // Cartao do veiculo na competencia: o abastecido do mes.
    await page.goto(`/mobilidade-mobile.html?mes=${MES}`);
    await carregada(page);
    const doCartao = cartao(page, VEICULO);
    await expect(doCartao.locator('.mob-veiculo-mes dt')).toHaveText('Abastecido em Mar/2024');
    await expect(doCartao.locator('.mob-veiculo-mes dd')).toHaveText(/R\$\s420,00/);
    await expect(doCartao.locator('.mob-veiculo-mes .mob-veiculo-nota')).toHaveText('2 abastecimentos');
    await expect(doCartao.locator('.mob-veiculo-km dd')).toHaveText(/km$/);

    // Historico: como o banco devolve (mais recentes primeiro) e o filtro do mes.
    await doCartao.locator('[data-acao="historico"]').click();
    await expect(folha(page).locator('#mob-folha-titulo')).toHaveText(`Histórico · ${VEICULO}`);
    await expect(folha(page).locator('.mob-abastecimento')).toHaveCount(h.abastecimentos.length);
    await folha(page).locator('.mob-mob-segmento button[data-periodo="mes"]').click();
    await expect(folha(page).locator('.mob-abastecimento')).toHaveCount(2);
    await expect(folha(page).locator('.mob-abastecimento').first()).toContainText('20/03/2024');
    await expect(folha(page).locator('.mob-abastecimento').first()).toContainText('1.400 km · Gasolina · 40,000 L · R$ 5,500/L · 400 km rodados');
    await expect(folha(page).locator('.mob-abastecimento').first().locator('.mob-linha-valor')).toHaveText(/R\$\s220,00/);
    await semRolagemHorizontal(page, 'historico');
    await folha(page).locator('#mob-folha-fechar').click();

    // Resumo: gasto do mes, consumo medio, custo por km, ultimos abastecimentos e o grafico dos ultimos meses.
    await doCartao.locator('[data-acao="resumo"]').click();
    await expect(folha(page).locator('#mob-folha-titulo')).toHaveText(`Resumo · ${VEICULO}`);
    const resumo = folha(page).locator('#mob-resumo-veiculo');
    await expect(resumo).toContainText('Gasto em Mar/2024');
    await expect(resumo).toContainText('R$ 420,00 (2 abastecimentos, 80,000 L)');
    await expect(resumo).toContainText('10,0 km/L');     // 400 km com os 40 L do segundo abastecimento
    await expect(resumo).toContainText('R$ 0,55/km');    // R$ 220 nos 400 km
    await expect(resumo).toContainText('20/03/2024 · R$ 220,00 · 40,000 L');
    await expect(folha(page).locator('#mob-resumo-ultimos .mob-abastecimento')).toHaveCount(2);
    await expect(folha(page).locator('.mob-grafico rect')).toHaveCount(6);
    await expect(folha(page).locator('.mob-grafico')).toHaveAttribute('aria-label', /Mar\/2024 R\$\s420,00/);
    await semRolagemHorizontal(page, 'resumo');
    await folha(page).locator('#mob-folha-fechar').click();

    // Competencia: outro mes sem abastecimentos; e o "+" do cabecalho abre o formulario sem veiculo escolhido na rota.
    await page.click('#mob-mes-anterior');
    await expect(page.locator('#mob-competencia')).toHaveText('Fev/2024');
    await carregada(page);
    await expect(cartao(page, VEICULO).locator('.mob-veiculo-mes .mob-veiculo-nota')).toHaveText('0 abastecimentos');
    await page.click('#mob-abastecer');
    await page.waitForURL('**/lancamento-mobile.html?mes=2024-02&tipo=abastecimento');
    await page.goBack();
    await carregada(page);
    await page.click('#mob-voltar');
    await page.waitForURL('**/inicio.html?mes=2024-02');
});

test('somente leitura: consulta veiculos, historico e resumo; sem abastecer', async ({ page }) => {
    await entrar(page, H);
    await page.locator('.mob-atalho[data-modulo="mobilidade"]').click();
    await page.waitForURL('**/mobilidade-mobile.html**');
    await carregada(page);
    await expect(page.locator('#mob-somente-leitura')).toBeVisible();
    await expect(page.locator('#mob-abastecer')).toBeHidden();
    await expect(cartao(page, VEICULO).locator('.mob-veiculo-acoes .mob-botao')).toHaveText(['Histórico', 'Resumo']);
    await expect(page.locator('[data-acao="abastecer"]')).toHaveCount(0);
    const veiculo = await veiculoG(page);
    const antes = await historicoG(page, veiculo.id);
    await cartao(page, VEICULO).locator('[data-acao="historico"]').click();
    await expect(folha(page).locator('.mob-abastecimento')).toHaveCount(antes.abastecimentos.length);
    await folha(page).locator('#mob-folha-fechar').click();
    await cartao(page, VEICULO).locator('[data-acao="resumo"]').click();
    await expect(folha(page).locator('#mob-resumo-veiculo')).toContainText('Consumo médio');
    await folha(page).locator('#mob-folha-fechar').click();
    // O banco tambem recusa a gravacao do leitor, e nada mudou.
    const recusa = await chamarRpc(page, 'registrar_abastecimento', { p_perfil_id: PERFIL_G, p_chave: crypto.randomUUID(),
        p_dados: { veiculo_id: veiculo.id, data_abastecimento: '2024-03-25', hodometro_km: 1500, combustivel: 'gasolina', preco_litro: 5, valor_total: 50 } });
    expect(recusa.status).toBeGreaterThanOrEqual(400);
    expect(await historicoG(page, veiculo.id)).toEqual(antes);
});

test('perfil sem veiculos mostra a orientacao; sem sessao a pagina volta ao login', async ({ page, browser }) => {
    await entrar(page, C);
    await page.goto('/mobilidade-mobile.html');
    await carregada(page);
    const perfil = (await rpc(page, 'meus_perfis', {}))[0].id;
    const veiculos = await rpc(page, 'veiculos_tela', { p_perfil_id: perfil, p_id: null });
    if (veiculos.length) {
        await expect(page.locator('.mob-veiculo')).toHaveCount(veiculos.length);
    } else {
        await expect(page.locator('#mob-lista .mob-vazio')).toContainText('Nenhum veículo neste perfil');
        await expect(page.locator('#mob-abastecer')).toBeHidden();
    }
    const contexto = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const anonima = await contexto.newPage();
    await anonima.goto('/mobilidade-mobile.html');
    await anonima.waitForURL(/index\.html|\/\?next=|\/$/);
    await expect(anonima.locator('#email')).toBeVisible();
    await contexto.close();
});
