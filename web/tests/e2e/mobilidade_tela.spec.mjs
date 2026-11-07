// FIN-FIDELIDADE-PATRIMONIO-1 (Mobilidade, fase 1) — tela original de Mobilidade do Flask (frontend/templates/veiculos.html)
// sobre o Supabase. Dados FICTICIOS do "Perfil B" (tests/supabase_local.py, semear_mobilidade_e2e): veiculo com projecoes,
// regra de manutencao, assinatura e caminho de transporte por app. FIN-MOBILIDADE-2: as acoes da tela gravam pelas
// funcoes do banco (Perfil B no novo aplicativo), pela mesma ponte /api/... que js/original/veiculos.js usa.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const C = { email: process.env.CF_EMAIL_C || 'usuario.c@teste.local', senha: process.env.CF_SENHA_C };
const VEICULO = 'Carro E2E (ficticio)';
// "Hoje" como o banco (financeiro.hoje_brasilia), e nao em UTC: das 21h a meia-noite de Brasilia a data UTC ja e o dia
// seguinte, e no ultimo dia do mes o veiculo nasceria no mes seguinte (11 projecoes na janela de 12 meses).
const HOJE_BRASILIA = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());

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

test('veiculo, assinatura e transporte por app como no Flask; cadastro, projecoes, ativacao e confirmacao gravam', async ({ page }) => {
    registrarDialogos(page);
    await entrar(page, B);
    await page.goto('/mobilidade.html');
    await expect(page.locator('.mobilidade-aviso-fase')).toContainText('gravados no Supabase');
    await expect(page.locator('#comp-cards')).toContainText(VEICULO);  // aba inicial: comparacao
    await page.locator('#tab-configuracao').click();
    await expect(page.locator('#conf-veiculos-lista')).toContainText(VEICULO);
    await expect(page.locator('#conf-assinaturas-lista')).toContainText('Assinatura E2E (ficticia)');
    await expect(page.locator('#conf-apps-lista')).toContainText('App E2E (ficticio)');

    const perfil = await perfilAtivoId(page);
    const antes = (await chamarRpc(page, 'veiculos_tela', { p_perfil_id: perfil, p_id: null })).corpo;
    expect(antes.map((v) => v.nome)).toEqual([VEICULO]);

    // Cadastro: o veiculo novo sai com as projecoes do MVP (categorias sistemicas, nunca criadas aqui).
    const novo = await api(page, 'POST', '/api/veiculos', {
        nome: 'Moto E2E (ficticia)', tipo: 'moto', combustivel: 'gasolina', autonomia_km_l: 30, status: 'ATIVO',
        data_inicio: HOJE_BRASILIA, combustivel_valor_mensal: 150, preco_medio_combustivel: 6,
    });
    expect(novo.status).toBe(201);
    expect(novo.corpo.data.nome).toBe('Moto E2E (ficticia)');
    const id = novo.corpo.data.id;
    const projecoes = (await chamarRpc(page, 'projecoes_mobilidade_tela', {
        p_perfil_id: perfil, p_origem_tipo: 'VEICULO', p_origem_id: id, p_meses: 12,
    })).corpo;
    expect(projecoes.length).toBe(12);
    expect(new Set(projecoes.map((p) => p.tipo_evento))).toEqual(new Set(['COMBUSTIVEL']));
    expect((await api(page, 'POST', `/api/veiculos/${id}/projecoes/gerar`, { meses_futuros: 12 })).corpo)
        .toMatchObject({ success: true, criadas: 12 });

    // Ativacao (exige confirmacao) e confirmacao de uma prevista, uma vez so. Sem recorrencia nem conta aqui: o banco do
    // E2E e compartilhado pelos specs de contas e recorrencias do Perfil B (a criacao delas esta nos testes Python).
    expect((await api(page, 'POST', '/api/veiculos/mobilidade/ativar', { tipo_modalidade: 'VEICULO', origem_id: id })).status).toBe(400);
    const ativada = await api(page, 'POST', '/api/veiculos/mobilidade/ativar', {
        tipo_modalidade: 'VEICULO', origem_id: id, meio_pagamento: 'pix', criar_recorrencia: false, confirmado: true,
    });
    expect(ativada.corpo.data.cenario).toMatchObject({ tipo_modalidade: 'VEICULO', origem_id: id, status: 'ATIVO' });
    expect(ativada.corpo.data.recorrencia).toBeNull();
    expect((await chamarRpc(page, 'mobilidade_ativa_tela', { p_perfil_id: perfil })).corpo.nome_origem).toBe('Moto E2E (ficticia)');
    const alvo = (await chamarRpc(page, 'projecoes_mobilidade_tela', {
        p_perfil_id: perfil, p_origem_tipo: 'VEICULO', p_origem_id: id, p_meses: 12,
    })).corpo[0];
    const confirmada = await api(page, 'POST', `/api/despesas-previstas/${alvo.id}/confirmar`, {});
    expect(confirmada.corpo.data).toEqual({ despesa_prevista: { id: alvo.id, status: 'CONFIRMADA' }, entidade_criada: null });
    expect((await api(page, 'POST', `/api/despesas-previstas/${alvo.id}/confirmar`, {})).status).toBe(400);

    // A tela recarregada mostra o veiculo novo.
    await page.reload();
    await page.locator('#tab-configuracao').click();
    await expect(page.locator('#conf-veiculos-lista')).toContainText('Moto E2E (ficticia)');
});

test('outro titular nao ve o veiculo', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/mobilidade.html');
    await expect(page.locator('.mobilidade-aviso-fase')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.locator('#tab-configuracao').click();
    await expect(page.locator('#conf-veiculos-lista')).not.toContainText('Carregando');
    await expect(page.locator('#conf-veiculos-lista')).not.toContainText(VEICULO);
});

// FIN-MVP-MOB-01: Flex pela tela: autonomia e preco por combustivel, custo calculado e custo manual. Veiculo excluido no fim.
test('veiculo flex: campos, custo calculado, referencia e custo manual', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await page.goto('/mobilidade.html');
    await expect(page.locator('#comp-cards')).toContainText(VEICULO);
    const perfil = await perfilAtivoId(page);
    const lido = async (nome) => (await chamarRpc(page, 'veiculos_tela', { p_perfil_id: perfil, p_id: null })).corpo.find((v) => v.nome === nome);
    const NOME = 'Flex E2E (ficticio)';

    await page.locator('#btn-novo-veiculo').click();
    await expect(page.locator('#autonomia_km_l')).toBeVisible();
    await expect(page.locator('#autonomia_gasolina_km_l')).toBeHidden();
    await page.fill('#nome', NOME);
    await page.selectOption('#combustivel', 'flex');
    await expect(page.locator('#autonomia_km_l')).toBeHidden();
    await expect(page.locator('#preco_medio_combustivel')).toBeHidden();
    await page.fill('#autonomia_gasolina_km_l', '10');
    await page.fill('#autonomia_etanol_km_l', '7');
    await page.fill('#preco_gasolina', '6');
    await page.fill('#preco_etanol', '4');
    await page.selectOption('#custo_combustivel_modo', 'CALCULADO');
    await expect(page.locator('#custo-calculado-aviso')).toContainText('Informe a quilometragem');
    await page.fill('#km_mensal_estimado', '1000');
    await expect(page.locator('#combustivel_valor_mensal')).toHaveValue('600.00');
    await page.selectOption('#combustivel_referencia', 'etanol');
    await expect(page.locator('#combustivel_valor_mensal')).toHaveValue('571.43');
    await page.selectOption('#combustivel_referencia', 'gasolina');
    await page.locator('#form-veiculo').evaluate((f) => f.requestSubmit());
    await expect.poll(async () => (await lido(NOME))?.autonomia_km_l).toBe(10);
    expect(await lido(NOME)).toMatchObject({ combustivel: 'flex', combustivel_referencia: 'gasolina', custo_combustivel_modo: 'CALCULADO',
        km_mensal_estimado: 1000, projecao_combustivel: { valor_mensal: 600 } });

    // Edicao pela tela: referencia etanol recalcula; depois, custo manual fica como informado.
    const id = (await lido(NOME)).id;
    await page.locator('#tab-configuracao').click();
    await page.locator(`#conf-veiculos-lista [data-on-click="abrirModalEditar(${id})"]`).click();
    await expect(page.locator('#autonomia_etanol_km_l')).toHaveValue('7');
    await page.selectOption('#combustivel_referencia', 'etanol');
    await page.locator('#form-veiculo').evaluate((f) => f.requestSubmit());
    await expect.poll(async () => (await lido(NOME))?.autonomia_km_l).toBe(7);
    expect((await lido(NOME)).projecao_combustivel.valor_mensal).toBe(571.43);
    await expect(page.locator('#conf-veiculos-lista')).toContainText('flex (etanol)');

    await page.locator(`#conf-veiculos-lista [data-on-click="abrirModalEditar(${id})"]`).click();
    await expect(page.locator('#combustivel_valor_mensal')).toHaveValue('571.43');
    await page.selectOption('#custo_combustivel_modo', 'MANUAL');
    await page.fill('#combustivel_valor_mensal', '480');
    await page.locator('#form-veiculo').evaluate((f) => f.requestSubmit());
    await expect.poll(async () => (await lido(NOME))?.custo_combustivel_modo).toBe('MANUAL');
    expect((await lido(NOME)).projecao_combustivel.valor_mensal).toBe(480);

    // Simulado: nao gera despesa real ao confirmar com pagamento; motivo na resposta.
    const alvo = (await chamarRpc(page, 'projecoes_mobilidade_tela', { p_perfil_id: perfil, p_origem_tipo: 'VEICULO', p_origem_id: id, p_meses: 12 })).corpo[0];
    const recusa = await api(page, 'POST', `/api/despesas-previstas/${alvo.id}/confirmar`, { meio_pagamento: 'pix' });
    expect(recusa.status).toBe(400);
    expect(recusa.corpo.error).toContain('Veículo simulado');
    expect(dialogos.length).toBeGreaterThan(0);
    expect((await api(page, 'DELETE', `/api/veiculos/${id}`)).status).toBe(200);
});

// FIN-MVP-MOB-01: abastecimento pela tela: veiculo obrigatorio, litros calculados, hodometro e correcao, sem criar despesa.
test('abastecimento: formulario compacto, litros, historico, regressao e correcao', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await page.goto('/mobilidade.html');
    await expect(page.locator('#comp-cards')).toContainText(VEICULO);
    const perfil = await perfilAtivoId(page);
    const veiculo = (await chamarRpc(page, 'veiculos_tela', { p_perfil_id: perfil, p_id: null })).corpo.find((v) => v.nome === VEICULO);
    const preencher = async (km, valor) => {
        await page.fill('#abast-hodometro', km);
        await page.fill('#abast-preco', '4.40');
        await page.fill('#abast-valor', valor);
    };

    // Pela acao geral, o veiculo nao vem escolhido.
    await page.locator('#btn-abastecer').click();
    await expect(page.locator('#modal-abastecimento')).toBeVisible();
    await expect(page.locator('#abast-veiculo')).toHaveValue('');
    await preencher('52300', '176');
    await expect(page.locator('#abast-litros')).toHaveText('40,000');
    await page.locator('#form-abastecimento button[type="submit"]').click();
    await expect(page.locator('#modal-abastecimento')).toBeVisible();  // veiculo obrigatorio: o navegador nao envia
    await page.selectOption('#abast-veiculo', String(veiculo.id));
    await expect(page.locator('#abast-combustivel')).toHaveValue(veiculo.combustivel.toLowerCase());
    await page.locator('#form-abastecimento button[type="submit"]').click();
    await expect(page.locator('#modal-abastecimento')).toBeHidden();

    // A partir do veiculo, ele vem selecionado; a regressao e recusada com o motivo.
    await page.locator('#tab-configuracao').click();
    await page.locator(`#conf-veiculos-lista [data-on-click="abrirModalAbastecimento(${veiculo.id})"]`).click();
    await expect(page.locator('#abast-veiculo')).toHaveValue(String(veiculo.id));
    await preencher('52000', '88');
    await page.fill('#abast-data', HOJE_BRASILIA);
    await page.locator('#abast-observacoes').fill('Leitura errada');
    const antes = await page.evaluate(() => document.querySelectorAll('#abast-veiculo option').length);
    expect(antes).toBeGreaterThan(1);
    await page.locator('#form-abastecimento').evaluate((f) => f.requestSubmit());
    await expect.poll(() => dialogos.length).toBeGreaterThan(0);
    await page.locator('#modal-abastecimento .close').click();

    // Historico, correcao com motivo e quilometragem real.
    await page.locator(`#conf-veiculos-lista [data-on-click="abrirHistoricoAbastecimentos(${veiculo.id})"]`).click();
    await expect(page.locator('#abast-historico-lista')).toContainText('40,000');
    await expect(page.locator('#abast-historico-lista')).toContainText('Aguardando');
    await expect(page.locator('#abast-km-resumo')).toContainText('52.300');
    await page.locator('#abast-historico-lista [title="Corrigir"]').click();
    await expect(page.locator('#abast-motivo')).toBeVisible();
    await page.fill('#abast-hodometro', '52400');
    await page.fill('#abast-motivo', 'Leitura conferida no painel');
    await page.locator('#form-abastecimento').evaluate((f) => f.requestSubmit());
    await expect(page.locator('#abast-km-resumo')).toContainText('52.400');
    await expect(page.locator('#abast-historico-lista')).toContainText('(corrigido)');
    await page.locator('#modal-abastecimentos .close').click();
    await expect(page.locator('#conf-veiculos-lista')).toContainText('52.400 km');
});

// FIN-MVP-MOB-01: troca de modalidade pela tela: a previa mostra as despesas futuras e a ativacao exige decidir cada uma. No
// usuario C: a recorrencia e as contas nao podem entrar no Perfil B, compartilhado com os specs de contas.
test('troca de modalidade: decide as despesas futuras e a substituida sai dos totais', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, C);
    await page.goto('/mobilidade.html');
    await page.waitForLoadState('networkidle');
    const perfil = await perfilAtivoId(page);
    const veiculo = (await api(page, 'POST', '/api/veiculos', {
        nome: 'Troca E2E (ficticio)', tipo: 'carro', combustivel: 'gasolina', autonomia_km_l: 10, status: 'ATIVO',
        data_inicio: HOJE_BRASILIA, combustivel_valor_mensal: 200, preco_medio_combustivel: 6,
    })).corpo.data;
    const ativada = await api(page, 'POST', '/api/veiculos/mobilidade/ativar', {
        tipo_modalidade: 'VEICULO', origem_id: veiculo.id, meio_pagamento: 'pix', confirmado: true,
    });
    expect(ativada.corpo.data.recorrencia.id).toBeGreaterThan(0);
    const assinatura = (await api(page, 'POST', '/api/veiculos/mobilidade/assinaturas', { nome: 'Assinatura troca E2E (ficticia)', valor_mensal: 900 })).corpo.data;

    // Despesas gera automaticamente o mes e o seguinte.
    await page.goto('/contas.html');
    await expect(page.locator('body')).toContainText('Combustivel - Troca E2E');
    await page.goto('/mobilidade.html');
    await page.waitForLoadState('networkidle');

    await page.evaluate((id) => window.abrirModalAtivacaoMobilidade('ASSINATURA', id), assinatura.id);
    await page.locator('#modal-ativar-mobilidade').getByText('Ver prévia').click();
    await expect(page.locator('#troca-conflitos')).toContainText('Combustivel - Troca E2E');
    await expect(page.locator('#ativar-mob-resultado')).toContainText('Não mudam nesta troca');
    await expect(page.locator('#troca-conflitos input:checked')).toHaveCount(0);

    // Sem decidir, nao ativa.
    await page.locator('#modal-ativar-mobilidade').getByText('Confirmar ativação').click();
    await expect.poll(() => dialogos.some((d) => /Escolha manter ou substituir/.test(d.message || d))).toBe(true);
    expect((await chamarRpc(page, 'mobilidade_ativa_tela', { p_perfil_id: perfil })).corpo.nome_origem).toBe('Troca E2E (ficticio)');

    const radio = page.locator('#troca-conflitos input[value="SUBSTITUIR"]').first();
    const contaId = Number(await radio.getAttribute('data-id'));
    await radio.check();
    await page.locator('#modal-ativar-mobilidade').getByText('Confirmar ativação').click();
    await expect(page.locator('#modal-ativar-mobilidade')).toBeHidden();
    expect((await chamarRpc(page, 'mobilidade_ativa_tela', { p_perfil_id: perfil })).corpo.nome_origem).toBe('Assinatura troca E2E (ficticia)');
    const despesas = (await chamarRpc(page, 'despesas_diretas_tela', { p_perfil_id: perfil })).corpo;
    expect(despesas.map((d) => d.id)).not.toContain(contaId);
});
