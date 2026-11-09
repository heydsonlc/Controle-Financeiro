// FIN-MVP-MOB-02 (P13) — lista de Projecoes do veiculo na tela de Mobilidade, com dados FICTICIOS do "Perfil B"
// (tests/supabase_local.py). Mobilidade -> Veiculo -> Projecoes -> + Adicionar projecao -> tipo, valor e periodicidade ->
// Salvar; editar, desativar, reativar e excluir; campos conforme a frequencia; combustivel pelo cadastro do veiculo; regra
// de manutencao por km na mesma lista; tabela compacta em 1366 e 1920 px. O veiculo do teste e excluido no fim.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const VEICULO = 'Projecoes E2E (ficticio)';
const HOJE_BRASILIA = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const EVIDENCIAS = process.env.CF_EVIDENCIAS_DIR || '';

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

async function api(page, metodo, url, corpo) {
    return page.evaluate(async ({ metodo, url, corpo }) => {
        const r = await fetch(url, { method: metodo, headers: { 'Content-Type': 'application/json' },
                                     body: corpo === undefined ? undefined : JSON.stringify(corpo) });
        return { status: r.status, corpo: await r.json() };
    }, { metodo, url, corpo });
}

function proximoMes(n) {
    const [a, m] = HOJE_BRASILIA.split('-').map(Number);
    const d = new Date(Date.UTC(a, m - 1 + n, 1));
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

function mesAno(aaaaMm) {
    const [a, m] = aaaaMm.split('-');
    return `${m}/${a}`;
}

async function evidencia(page, nome) {
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/${nome}.png`, fullPage: false });
}

// Tabela compacta: uma linha por item, sem crescer na vertical, botoes do mesmo tamanho e sem rolagem horizontal da pagina.
async function conferirLayout(page, tabela) {
    const medidas = await tabela.evaluate((t) => ({
        linhas: [...t.querySelectorAll('tbody tr')].map((tr) => tr.getBoundingClientRect().height),
        botoes: [...t.querySelectorAll('.row-action-button')].map((b) => {
            const r = b.getBoundingClientRect();
            return [Math.round(r.width), Math.round(r.height)];
        }),
        acoes: [...t.querySelectorAll('.projecao-acoes')].map((a) => a.scrollWidth <= a.clientWidth + 1),
        quebra: [...t.querySelectorAll('td')].some((td) => td.getBoundingClientRect().height > 40),
        pagina: document.documentElement.scrollWidth <= window.innerWidth,
        envoltorio: (() => { const w = t.closest('.projecoes-itens-tabela'); return w.scrollWidth <= w.clientWidth + 1; })(),
    }));
    expect(medidas.linhas.every((h) => h <= 40), `alturas ${medidas.linhas}`).toBe(true);
    expect(new Set(medidas.botoes.map((b) => b.join('x'))).size, `botoes ${JSON.stringify(medidas.botoes)}`).toBe(1);
    expect(medidas.acoes.every(Boolean)).toBe(true);
    expect(medidas.quebra).toBe(false);
    expect(medidas.pagina).toBe(true);
    expect(medidas.envoltorio).toBe(true);
}

test('lista de projecoes: adicionar, campos por frequencia, editar, desativar, reativar, excluir e combustivel', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await page.goto('/mobilidade.html');
    const perfil = await perfilAtivoId(page);
    const novo = await api(page, 'POST', '/api/veiculos', {
        nome: VEICULO, tipo: 'carro', combustivel: 'gasolina', autonomia_km_l: 11, status: 'ATIVO', data_inicio: HOJE_BRASILIA,
        combustivel_valor_mensal: 300, preco_medio_combustivel: 6,
    });
    expect(novo.status).toBe(201);
    const id = novo.corpo.data.id;
    try {
        await roteiro(page, perfil, id, dialogos);
    } finally {
        // o veiculo do teste sai mesmo se algo falhar (o banco do E2E e compartilhado pelos specs de Mobilidade)
        for (const r of (await api(page, 'GET', `/api/veiculos/${id}/regras-km`)).corpo.data || []) {
            await api(page, 'DELETE', `/api/veiculos/${id}/regras-km/${r.id}`);
        }
        for (const i of (await api(page, 'GET', `/api/veiculos/${id}/projecoes-itens`)).corpo.data?.itens || []) {
            if (i.pode_excluir) await api(page, 'DELETE', `/api/veiculos/projecoes-itens/${i.id}`);
        }
        expect((await api(page, 'DELETE', `/api/veiculos/${id}`)).status).toBe(200);
    }
});

async function roteiro(page, perfil, id, dialogos) {
    await page.reload();
    await page.locator('#tab-configuracao').click();
    const linhaVeiculo = page.locator('.conf-item', { hasText: VEICULO });
    await linhaVeiculo.locator('button[title="Projeções"]').click();
    const area = page.locator(`#projecoes-itens-${id}`);
    const tabela = area.locator('.tabela-projecoes-itens');
    await expect(tabela.locator('thead')).toContainText('Despesa');
    await expect(tabela.locator('thead th')).toHaveText(['Despesa', 'Valor', 'Periodicidade', 'Próxima ocorrência', 'Situação', 'Ações']);
    const combustivel = tabela.locator('tbody tr', { hasText: 'Combustível' });
    await expect(combustivel).toContainText('R$ 300,00');
    await expect(combustivel).toContainText('Mensal');
    await expect(combustivel.locator('button[aria-label*="desative"]')).toBeDisabled();  // excluir: indisponivel, mas visivel

    // Modal compacto: so os campos da frequencia escolhida
    await area.getByRole('button', { name: '+ Adicionar projeção' }).click();
    const modal = page.locator('#modal-projecao');
    await expect(modal).toBeVisible();
    await expect(page.locator('#projecao-titulo')).toHaveText('Adicionar projeção');
    await expect(page.locator('#projecao-inicio')).toHaveAttribute('type', 'month');
    await expect(page.locator('#projecao-fim-grupo')).toBeVisible();
    await page.selectOption('#projecao-frequencia', 'DATA');
    await expect(page.locator('#projecao-inicio')).toHaveAttribute('type', 'date');
    await expect(page.locator('#projecao-inicio-rotulo')).toHaveText('Data programada *');
    await expect(page.locator('#projecao-fim-grupo')).toBeHidden();
    await page.selectOption('#projecao-frequencia', 'SEMANAL');
    await expect(page.locator('#projecao-inicio')).toHaveAttribute('type', 'date');
    await expect(page.locator('#projecao-fim-grupo')).toBeVisible();
    await page.selectOption('#projecao-frequencia', 'ANUAL');
    await expect(page.locator('#projecao-inicio-rotulo')).toHaveText('Mês de cobrança *');
    await expect(page.locator('#projecao-aviso')).toContainText('valor integral');
    await page.selectOption('#projecao-tipo', 'IPVA');
    await expect(page.locator('#projecao-frequencia')).toBeDisabled();
    await expect(page.locator('#projecao-frequencia')).toHaveValue('ANUAL');
    await evidencia(page, '02-modal-adicionar');

    // Salvar: pneus semestrais a partir do proximo mes
    await page.selectOption('#projecao-tipo', 'PNEUS');
    await page.selectOption('#projecao-frequencia', 'SEMESTRAL');
    await expect(page.locator('#projecao-inicio-rotulo')).toHaveText('Primeira competência *');
    await page.fill('#projecao-nome', 'Pneus dianteiros (E2E)');
    await page.fill('#projecao-valor', '1200');
    await page.fill('#projecao-inicio', proximoMes(1));
    await page.click('#projecao-salvar');
    await expect(modal).toBeHidden();
    const pneus = tabela.locator('tbody tr', { hasText: 'Pneus dianteiros (E2E)' });
    await expect(pneus).toContainText('R$ 1.200,00');
    await expect(pneus).toContainText('Semestral');
    await expect(pneus).toContainText(mesAno(proximoMes(1)));
    await expect(pneus).toContainText('Ativa');
    await expect(page.locator(`#conf-custo-${id}`)).toHaveText('R$ 500,00/mês');  // 300 de combustivel + 1.200 / 6
    await expect(area.locator('.projecoes-itens-cabecalho')).toContainText('Média mensal R$ 500,00');
    const ocorrencias = async () => (await chamarRpc(page, 'projecoes_mobilidade_tela', {
        p_perfil_id: perfil, p_origem_tipo: 'VEICULO', p_origem_id: id, p_meses: 12,
    })).corpo.filter((o) => o.metadata?.nome === 'Pneus dianteiros (E2E)' || o.metadata?.nome === 'Pneus (E2E)');
    expect((await ocorrencias()).map((o) => [o.data_prevista.slice(0, 7), o.valor_previsto, o.status]))
        .toEqual([[proximoMes(1), 1200, 'PREVISTA'], [proximoMes(7), 1200, 'PREVISTA']]);
    // as despesas previstas abaixo mostram o item pelo nome
    await expect(page.locator(`#projecoes-${id} .projecoes-body`)).toContainText('Pneus dianteiros (E2E)');
    await conferirLayout(page, tabela);
    await evidencia(page, '03-lista-1366');

    // Editar: o tipo fica fixo
    await pneus.locator('button[aria-label="Editar"]').click();
    await expect(page.locator('#projecao-titulo')).toHaveText('Editar projeção — Pneus dianteiros (E2E)');
    await expect(page.locator('#projecao-tipo')).toBeDisabled();
    await page.fill('#projecao-valor', '1350');
    await page.fill('#projecao-nome', 'Pneus (E2E)');
    const ids = (await ocorrencias()).map((o) => o.id);
    await page.click('#projecao-salvar');
    const editado = tabela.locator('tbody tr', { hasText: 'Pneus (E2E)' });
    await expect(editado).toContainText('R$ 1.350,00');
    expect((await ocorrencias()).map((o) => [o.id, o.valor_previsto])).toEqual(ids.map((i) => [i, 1350]));  // mesmos ids

    // Desativar e reativar
    await editado.locator('button[aria-label="Desativar"]').click();
    await expect(editado).toHaveClass(/projecao-inativa/);
    await expect(editado).toContainText('Inativa');
    expect(await ocorrencias()).toEqual([]);
    expect(dialogos.some((d) => /Desativar esta projeção/.test(d))).toBe(true);
    await editado.locator('button[aria-label="Ativar"]').click();
    await expect(editado).toContainText('Ativa');
    expect((await ocorrencias()).length).toBe(2);

    // Regra de manutencao por km na mesma lista; o mesmo servico pede confirmacao (aceita) para manter as duas
    const regra = await api(page, 'POST', `/api/veiculos/${id}/regras-km`, { tipo_evento: 'TROCA_OLEO', intervalo_km: 10000, custo_estimado: 300 });
    expect(regra.status).toBe(201);
    await area.getByRole('button', { name: '+ Adicionar projeção' }).click();
    await expect(page.locator('#projecao-tipo')).toBeEnabled();
    await page.selectOption('#projecao-tipo', 'MANUTENCAO_PREVENTIVA');
    await page.selectOption('#projecao-frequencia', 'TRIMESTRAL');
    await page.fill('#projecao-valor', '250');
    await page.fill('#projecao-inicio', proximoMes(2));
    await page.click('#projecao-salvar');
    await expect(tabela.locator('tbody tr', { hasText: 'Manutenção preventiva' })).toContainText('Trimestral');
    expect(dialogos.some((d) => /quilometragem para este serviço/.test(d))).toBe(true);
    await expect(tabela.locator('tbody tr', { hasText: 'A cada 10.000 km' })).toContainText('Por km');
    await conferirLayout(page, tabela);

    // Combustivel: so o valor, pelo cadastro do veiculo
    await combustivel.locator('button[aria-label="Editar"]').click();
    await expect(page.locator('#projecao-tipo-grupo')).toBeHidden();
    await expect(page.locator('#projecao-frequencia-grupo')).toBeHidden();
    await expect(page.locator('#projecao-aviso')).toContainText('segue o cadastro do veículo');
    await page.fill('#projecao-valor', '320');
    await page.click('#projecao-salvar');
    await expect(combustivel).toContainText('R$ 320,00');
    expect((await chamarRpc(page, 'veiculos_tela', { p_perfil_id: perfil, p_id: id })).corpo.projecao_combustivel.valor_mensal).toBe(320);

    // 1920 px: a mesma tabela, sem sobreposicao nem crescimento
    await page.setViewportSize({ width: 1920, height: 1000 });
    await conferirLayout(page, tabela);
    await evidencia(page, '04-lista-1920');
    await page.setViewportSize({ width: 1366, height: 900 });

    // Excluir (sem historico) e limpeza do veiculo do teste
    const manut = tabela.locator('tbody tr', { hasText: 'Manutenção preventiva' });
    await manut.locator('button[aria-label="Excluir"]').click();
    await expect(manut).toHaveCount(0);
    await editado.locator('button[aria-label="Excluir"]').click();
    await expect(tabela.locator('tbody tr', { hasText: 'Pneus (E2E)' })).toHaveCount(0);
    expect(await ocorrencias()).toEqual([]);
}

test('modal do veiculo sem os campos fixos de IPVA, seguro e licenciamento', async ({ page }) => {
    await entrar(page, B);
    await page.goto('/mobilidade.html');
    await page.locator('#tab-configuracao').click();
    await page.locator('#conf-veiculos-lista button', { hasText: 'Novo veículo' }).or(page.locator('#btn-novo-veiculo')).first().click();
    await expect(page.locator('#modal-veiculo')).toBeVisible();
    await expect(page.locator('#modal-veiculo')).toContainText('lista de Projeções do veículo');
    for (const campo of ['#ipva_mes', '#ipva_valor', '#seguro_mes', '#seguro_valor', '#licenciamento_mes', '#licenciamento_valor']) {
        await expect(page.locator(campo)).toHaveCount(0);
    }
    await expect(page.locator('#combustivel_valor_mensal')).toBeVisible();
    await evidencia(page, '01-modal-veiculo');
});
