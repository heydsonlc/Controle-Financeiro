// FIN-MVP-MOBILE-FINAL-01 — cenarios integrados dos sete modulos mobile (contrato, secao 6), encadeados como o usuario faria:
// cadastro (Nova Despesa / Registrar Lancamento), consulta no modulo (Lista de Despesas, Receitas, Cartoes), pagamento ou
// recebimento, reflexo na conta (Contas) e estorno pelo modulo de origem. Usuario G, titular do "Perfil G (ficticio)"; leitor H.
// Cadastros em 05/2033 (competencia sem outro dado); pagamentos e recebimentos com a data de hoje (Contas, mes atual). Cada
// efeito e conferido pelas funcoes de leitura do desktop (saldo, extrato, conferencia), nunca por valores fixos de saldo.
// Dados FICTICIOS; grava so no banco descartavel.
import { expect, test } from '@playwright/test';

import { chamarRpc } from './despesas.mjs';

const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const H = { email: process.env.CF_EMAIL_H || 'usuario.h@teste.local', senha: process.env.CF_SENHA_H };
const PERFIL_G = 160;
const MES = '2033-05';
const HOJE = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const MES_HOJE = HOJE.slice(0, 7);
const CONTA_G = 'Conta G (ficticia)';
const ROTULO_CONTA_G = 'Conta G (ficticia) (Banco ficticio)';
const RESERVA_G = 'Reserva G (ficticia)';
const MASTER = 'Nubank Master G (ficticio)';

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

const reais = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }).replace(/\s/g, ' ');
const centavos = (v) => Math.round(Number(v) * 100);
const folha = (page) => page.locator('#mob-folha');
const botaoFolha = (page, texto) => folha(page).locator('.mob-botao', { hasText: texto });
const aviso = (page) => page.locator('#mob-aviso');
const campoCadastro = (page, rotulo) => page.locator('#mob-cadastro .mob-campo', { has: page.locator('xpath=./span[1]', { hasText: new RegExp(`^${rotulo}`) }) })
    .locator('input, select, textarea').first();
const contaDoBanco = async (page, nome) => (await rpc(page, 'contas_bancarias_tela', { p_perfil_id: PERFIL_G, p_status: 'ATIVO' })).find((c) => c.nome === nome);
const contasDoMes = (page, mes, nome) => rpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_G, p_mes: `${mes}-01` }).then((l) => l.filter((c) => c.nome === nome));
const idDoCartao = async (page, nome) => (await rpc(page, 'cartoes_do_perfil', { p_perfil_id: PERFIL_G })).find((c) => c.nome === nome).id;
const consistente = async (page, contaId) => (await rpc(page, 'conferir_saldo_conta', { p_perfil_id: PERFIL_G, p_conta_bancaria_id: contaId })).consistente;

// Lista de Despesas mobile: competencia carregada, grupos abertos e a linha pelo nome.
async function abrirLista(page, mes) {
    await page.goto(`/despesas-mobile.html?mes=${mes}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-competencia-carregada', mes);
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    const fechados = page.locator('.mob-grupo-cabecalho[aria-expanded="false"]');
    while (await fechados.count()) await fechados.first().click();
}
const linhaLista = (page, nome) => page.locator('#mob-lista .mob-linha', { has: page.locator('.mob-linha-nome', { hasText: nome }) });

// Contas mobile: a conta e o mes atual (os pagamentos sao de hoje); o movimento pela natureza e pelo valor.
async function abrirContas(page, contaId) {
    await page.goto(`/contas-mobile.html?mes=${MES_HOJE}&conta=${contaId}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
}
const movimento = (page, natureza, valor) => page.locator(`#mob-lista .mob-movimento[data-natureza="${natureza}"]`, {
    has: page.locator('.mob-linha-valor', { hasText: valor }) });

async function conferirConta(page, contaId, saldoEsperado) {
    const conta = (await rpc(page, 'contas_bancarias_tela', { p_perfil_id: PERFIL_G, p_status: 'ATIVO' })).find((c) => c.id === contaId);
    expect(centavos(conta.saldo_atual)).toBe(saldoEsperado);
    await expect(page.locator('#mob-saldo-valor')).toHaveText(reais(saldoEsperado / 100));
    expect(await consistente(page, contaId)).toBe(true);
}

// ---------------------------------------------------------------------------------------------------------------

test('cenario 1 (despesa): cadastrar, consultar na Lista, pagar, ver o movimento e o saldo em Contas', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    const saldo = centavos(contaG.saldo_atual);
    // Cadastro pela Nova Despesa (atalho Despesa).
    await page.goto(`/despesa-nova-mobile.html?mes=${MES}`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
    await campoCadastro(page, 'Descrição').fill('Integrada Luz G');
    await campoCadastro(page, 'Valor').fill('271.37');
    await campoCadastro(page, 'Categoria').selectOption({ label: 'Moradia' });
    await campoCadastro(page, 'Vencimento').fill(`${MES}-20`);
    await campoCadastro(page, 'Competência').fill(MES);
    await page.locator('#mob-salvar').dblclick();
    await expect(page.locator('#mob-confirmacao')).toContainText('“Integrada Luz G” cadastrada');
    expect((await contasDoMes(page, MES, 'Integrada Luz G')).map((c) => [centavos(c.valor), c.status_pagamento])).toEqual([[27137, 'Pendente']]);
    // Consulta e pagamento pela Lista de Despesas mobile.
    await page.click('#mob-ver-lista');
    await abrirLista(page, MES);
    await expect(linhaLista(page, 'Integrada Luz G')).toHaveCount(1);
    await linhaLista(page, 'Integrada Luz G').click();
    await botaoFolha(page, 'Pagar').click();
    await folha(page).locator('select').first().selectOption({ label: ROTULO_CONTA_G });
    await botaoFolha(page, 'Confirmar pagamento').dblclick();  // toque duplo: um pagamento so
    await expect(aviso(page)).toContainText(`Despesa paga: ${reais(271.37)} debitados de ${CONTA_G}`);
    const [luz] = await contasDoMes(page, MES, 'Integrada Luz G');
    expect(luz.status_pagamento).toBe('Pago');
    expect((await rpc(page, 'dados_pagamento_despesa', { p_perfil_id: PERFIL_G, p_conta_id: luz.id })).pagamentos.length).toBe(1);
    // Movimento e saldo em Contas.
    await abrirContas(page, contaG.id);
    await expect(movimento(page, 'despesa', reais(271.37))).toHaveCount(1);
    await conferirConta(page, contaG.id, saldo - 27137);
    await movimento(page, 'despesa', reais(271.37)).click();
    await expect(folha(page)).toContainText('Integrada Luz G');
});

test('cenario 2 (receita): cadastrar prevista, localizar em Receitas, receber, ver o credito e o saldo em Contas', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    const saldo = centavos(contaG.saldo_atual);
    // Cadastro pela opcao Receita do Registrar Lancamento: nasce prevista.
    await page.goto(`/lancamento-mobile.html?mes=${MES}&tipo=receita`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
    await page.locator('#mob-cadastro .mob-campo', { hasText: 'Nome' }).locator('input').fill('Integrada Bonus G');
    await page.locator('#mob-cadastro .mob-campo', { hasText: 'Tipo' }).locator('select').selectOption({ index: 1 });
    await page.locator('#mob-cadastro .mob-campo', { hasText: 'Valor base mensal' }).locator('input').fill('432,10');
    await page.locator('#mob-cadastro .mob-opcao', { hasText: 'Receita recorrente' }).locator('input').uncheck();
    await page.locator('#mob-cadastro .mob-campo', { hasText: 'Conta bancária' }).locator('select').selectOption({ label: ROTULO_CONTA_G });
    await page.locator('#mob-cadastro button[type="submit"]').click();
    await expect(page.locator('#mob-confirmacao')).toContainText('“Integrada Bonus G” cadastrada');
    expect(centavos((await contaDoBanco(page, CONTA_G)).saldo_atual)).toBe(saldo);  // prevista: nada recebido
    // Receitas mobile: a receita a receber; Receber (a data de hoje).
    await page.click('#mob-ver-receitas');
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-carregado', MES);
    const linha = page.locator('#mob-lista .mob-linha', { has: page.locator('.mob-linha-nome', { hasText: 'Integrada Bonus G' }) });
    await linha.click();
    await botaoFolha(page, 'Receber').click();
    await botaoFolha(page, 'Receber').dblclick();
    await expect(aviso(page)).toHaveText(`Receita registrada com sucesso: ${reais(432.1)} em ${CONTA_G}.`);
    await expect(linha).toHaveClass(/recebida/);
    // Credito e saldo em Contas.
    await abrirContas(page, contaG.id);
    await expect(movimento(page, 'receita', reais(432.1))).toHaveCount(1);
    await conferirConta(page, contaG.id, saldo + 43210);
});

test('cenario 3 (cartao): compra no cartao, na fatura certa; pagar a fatura; debito na conta; sem duplicidade na Lista', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    const master = await idDoCartao(page, MASTER);
    const saldo = centavos(contaG.saldo_atual);
    await page.goto(`/lancamento-mobile.html?mes=${MES}&tipo=cartao`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
    await campoCadastro(page, 'Descrição').fill('Integrada Fone G');
    await campoCadastro(page, 'Valor').fill('345.60');
    await campoCadastro(page, 'Categoria').selectOption({ label: 'Moradia' });
    await campoCadastro(page, 'Cartão').selectOption({ label: MASTER });
    await campoCadastro(page, 'Data da compra').fill(`${MES}-05`);
    await campoCadastro(page, 'Data da compra').dispatchEvent('change');
    await expect(campoCadastro(page, 'Fatura')).toHaveValue(MES);  // fecha dia 15: a fatura de 05/2033
    await page.locator('#mob-salvar').dblclick();
    await expect(page.locator('#mob-confirmacao')).toContainText(`Compra lançada na fatura 05/2033 do cartão ${MASTER}.`);
    // A fatura nos Cartoes mobile; pagamento pela conta.
    await page.click('#mob-ver-cartao');
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-carregado', `${MES}:${master}`);
    await expect(page.locator('#mob-lista')).toContainText('Integrada Fone G');
    await page.click('#mob-pagar-fatura');
    await folha(page).locator('.mob-campo', { hasText: 'Conta bancária' }).locator('select').selectOption({ label: ROTULO_CONTA_G });
    await botaoFolha(page, 'Confirmar pagamento').dblclick();
    await expect(aviso(page)).toContainText(`Fatura paga: ${reais(345.6)} debitados de ${CONTA_G}.`);
    // Lista de Despesas: so a fatura (com o valor), nenhuma conta a pagar com o nome da compra.
    await abrirLista(page, MES);
    await expect(linhaLista(page, 'Integrada Fone G')).toHaveCount(0);
    await expect(linhaLista(page, 'Nubank Master G').locator('.mob-linha-valor')).toHaveText(reais(345.6));
    expect(await contasDoMes(page, MES, 'Integrada Fone G')).toEqual([]);
    // Debito na conta.
    await abrirContas(page, contaG.id);
    await expect(movimento(page, 'fatura', reais(345.6))).toHaveCount(1);
    await conferirConta(page, contaG.id, saldo - 34560);
});

test('cenario 4 (transferencia): debito na origem, credito no destino, saldos e o vinculo entre os dois movimentos', async ({ page }) => {
    await entrar(page, G);
    const origem = await contaDoBanco(page, CONTA_G);
    const destino = await contaDoBanco(page, RESERVA_G);
    await abrirContas(page, origem.id);
    await page.click('#mob-transferir');
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
    await campoCadastro(page, 'Conta de destino').selectOption(String(destino.id));
    await campoCadastro(page, 'Valor').fill('55.55');
    await page.locator('#mob-salvar').dblclick();
    await page.click('#mob-ver-contas');
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    await conferirConta(page, origem.id, centavos(origem.saldo_atual) - 5555);
    await expect(movimento(page, 'transferencia', reais(55.55))).toHaveCount(1);
    await movimento(page, 'transferencia', reais(55.55)).click();
    await expect(folha(page).locator('.mob-detalhes dt', { hasText: /^Conta de destino$/ }).locator('xpath=following-sibling::dd[1]')).toHaveText(RESERVA_G);
    await page.click('#mob-ver-origem');
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    await conferirConta(page, destino.id, centavos(destino.saldo_atual) + 5555);
    // Os dois movimentos tem o mesmo transferencia_id (debito na origem, credito no destino).
    const lerMes = (id) => rpc(page, 'extrato_conta_bancaria', { p_perfil_id: PERFIL_G, p_conta_bancaria_id: id, p_inicio: `${MES_HOJE}-01`,
        p_fim: HOJE, p_limite: 200, p_incluir_saldo: false });
    const debito = (await lerMes(origem.id)).filter((m) => m.transferencia_id && centavos(m.valor) === 5555);
    const credito = (await lerMes(destino.id)).filter((m) => m.transferencia_id && centavos(m.valor) === 5555);
    expect(debito.map((m) => m.tipo)).toEqual(['DEBITO']);
    expect(credito.map((m) => m.tipo)).toEqual(['CREDITO']);
    expect(debito[0].transferencia_id).toBe(credito[0].transferencia_id);
});

test('cenario 5 (abastecimento): vinculo com o veiculo, dados do abastecimento e uma despesa so, paga pela Lista', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    const veiculo = (await rpc(page, 'formulario_abastecimento_lancamento', { p_perfil_id: PERFIL_G })).veiculos.find((v) => v.nome === 'Flex G (ficticio)');
    await page.goto(`/lancamento-mobile.html?mes=${MES_HOJE}&tipo=abastecimento`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
    const km = Number(veiculo.ultimo_hodometro || 0) + 500;  // a partir da ultima leitura (outro spec pode ter abastecido)
    await campoCadastro(page, 'Hodômetro').fill(String(km));
    await campoCadastro(page, 'Combustível').selectOption('gasolina');
    await campoCadastro(page, 'Preço por litro').fill('6.25');
    await campoCadastro(page, 'Valor total').fill('125');
    await campoCadastro(page, 'Descrição').fill('Integrada Abastecimento G');
    await page.locator('#mob-salvar').dblclick();
    await expect(page.locator('#mob-confirmacao')).toContainText('20,000 L de Gasolina');
    const abastecimentos = (await rpc(page, 'abastecimentos_veiculo_tela', { p_perfil_id: PERFIL_G, p_veiculo_id: veiculo.id })).abastecimentos
        .filter((a) => Number(a.hodometro_km) === km);
    expect(abastecimentos.map((a) => [centavos(a.valor_total), a.combustivel, Number(a.litros), Boolean(a.conta_id)])).toEqual([[12500, 'gasolina', 20, true]]);
    const contas = await contasDoMes(page, MES_HOJE, 'Integrada Abastecimento G');
    expect(contas.map((c) => [centavos(c.valor), c.categoria_nome, c.id === abastecimentos[0].conta_id])).toEqual([[12500, 'Combustível', true]]);
    // A despesa do abastecimento e paga pela Lista (uma obrigacao so).
    await abrirLista(page, MES_HOJE);
    await expect(linhaLista(page, 'Integrada Abastecimento G')).toHaveCount(1);
    await linhaLista(page, 'Integrada Abastecimento G').click();
    await botaoFolha(page, 'Pagar').click();
    await folha(page).locator('select').first().selectOption({ label: ROTULO_CONTA_G });
    await botaoFolha(page, 'Confirmar pagamento').click();
    await expect(aviso(page)).toContainText(`Despesa paga: ${reais(125)}`);
    await abrirContas(page, contaG.id);
    await conferirConta(page, contaG.id, centavos(contaG.saldo_atual) - 12500);
});

test('cenario 6 (estornos): despesa, recebimento e fatura estornados nos modulos de origem; situacao, movimentos e saldos', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    const master = await idDoCartao(page, MASTER);
    let saldo = centavos(contaG.saldo_atual);
    // Despesa (Lista de Despesas): volta a pendente; credito do estorno.
    await abrirLista(page, MES);
    await linhaLista(page, 'Integrada Luz G').click();
    await botaoFolha(page, 'Estornar pagamento').click();
    await folha(page).locator('textarea').fill('Teste integrado (ficticio)');
    await botaoFolha(page, 'Confirmar estorno').click();
    await expect(aviso(page)).toContainText(`Pagamento estornado: ${reais(271.37)} devolvidos a ${CONTA_G}`);
    expect((await contasDoMes(page, MES, 'Integrada Luz G'))[0].status_pagamento).toBe('Pendente');
    saldo += 27137;
    // Recebimento (Receitas): volta a prevista; debito do estorno.
    await page.goto(`/receitas-mobile.html?mes=${MES}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-carregado', MES);
    const receita = page.locator('#mob-lista .mob-linha', { has: page.locator('.mob-linha-nome', { hasText: 'Integrada Bonus G' }) });
    await receita.click();
    await botaoFolha(page, 'Estornar').click();
    await folha(page).locator('.mob-campo', { hasText: 'Motivo do estorno' }).locator('textarea, input').first().fill('Teste integrado (ficticio)');
    await botaoFolha(page, 'Estornar').click();
    await expect(aviso(page)).toHaveText('Recebimento estornado com sucesso.');
    await expect(receita).not.toHaveClass(/recebida/);
    saldo -= 43210;
    // Fatura (Cartoes): reaberta; credito do estorno; a compra continua na fatura.
    await page.goto(`/cartoes-mobile.html?mes=${MES}&cartao=${master}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-carregado', `${MES}:${master}`);
    await page.click('#mob-estornar-fatura');
    await folha(page).locator('textarea').fill('Teste integrado (ficticio)');
    await botaoFolha(page, 'Confirmar estorno').click();
    await expect(aviso(page)).toContainText(`Pagamento estornado: ${reais(345.6)} devolvidos a ${CONTA_G}.`);
    await expect(page.locator('#mob-pagar-fatura')).toBeVisible();
    saldo += 34560;
    // Contas: os tres estornos (com o movimento original de cada um) e o saldo pelos movimentos.
    await abrirContas(page, contaG.id);
    for (const valor of [271.37, 432.1, 345.6]) await expect(movimento(page, 'estorno', reais(valor))).toHaveCount(1);
    await conferirConta(page, contaG.id, saldo);
    // O estorno da fatura: o movimento original e a fatura (reaberta).
    await movimento(page, 'estorno', reais(345.6)).click();
    await expect(folha(page)).toContainText('Estorno dePagamento fatura cartao');
    await expect(folha(page)).toContainText('Nubank Master G (ficticio) · Mai/2033');
    await expect(folha(page)).toContainText('Em aberto');
});

test('cenario 7 (permissoes): leitor sem escrita em nenhum modulo; sessao encerrada; endereco direto; competencia e atualizacao', async ({ page }) => {
    await entrar(page, H);
    const contaG = await contaDoBanco(page, CONTA_G);
    await page.goto(`/inicio.html?mes=${MES}`);
    for (const modulo of ['despesa', 'lancamento']) {
        await expect(page.locator(`.mob-atalho[data-modulo="${modulo}"]`)).toHaveAttribute('title', 'Somente leitura neste perfil');
    }
    await expect(page.locator('.mob-barra-item[data-modulo="lancar"]')).toHaveAttribute('aria-disabled', 'true');
    // Lista: a despesa sem Pagar nem Estornar; Receitas sem "+"; Cartoes sem pagar; Contas sem transferir.
    await abrirLista(page, MES);
    await linhaLista(page, 'Integrada Luz G').click();
    await expect(folha(page).locator('.mob-botao', { hasText: /Pagar|Estornar|Editar|Excluir/ })).toHaveCount(0);
    await page.goto(`/receitas-mobile.html?mes=${MES}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-carregado', MES);
    await expect(page.locator('#mob-nova')).toBeHidden();
    await page.goto(`/cartoes-mobile.html?mes=${MES}&cartao=${await idDoCartao(page, MASTER)}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('#mob-pagar-fatura')).toHaveCount(0);
    await abrirContas(page, contaG.id);
    await expect(page.locator('#mob-transferir')).toBeHidden();
    // O banco recusa a escrita do leitor, qualquer que seja o estado dos botoes.
    const [luz] = await contasDoMes(page, MES, 'Integrada Luz G');
    const pagar = await chamarRpc(page, 'pagar_despesa', { p_perfil_id: PERFIL_G, p_conta_id: luz.id, p_chave: crypto.randomUUID(),
        p_dados: { conta_bancaria_id: contaG.id, data_pagamento: HOJE, valor_pago: '271.37', valor_devido: '271.37' } });
    expect(pagar.status).not.toBe(200);
    // Atualizar a pagina mantem a conta e a competencia; trocar o mes tambem.
    await page.reload();
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    await expect(page).toHaveURL(new RegExp(`mes=${MES_HOJE}&conta=${contaG.id}`));
    await page.click('#mob-mes-anterior');
    await expect(page).toHaveURL(/mes=\d{4}-\d{2}/);
    await expect(page.locator('.mob-barra-item[data-inicio]')).toHaveAttribute('href', /inicio\.html\?mes=\d{4}-\d{2}/);
    // Sessao encerrada (Mais -> Sair): as paginas mobile voltam ao login, inclusive pelo endereco direto.
    await page.click('#mob-mais');
    await page.click('#mob-sair');
    await page.waitForURL('**/index.html**');
    for (const pagina of ['inicio.html', 'contas-mobile.html', 'lancamento-mobile.html?tipo=transferencia', 'despesas-mobile.html']) {
        await page.goto(`/${pagina}`);
        await page.waitForURL('**/index.html**');
        await expect(page.locator('#login-form')).toBeVisible();
    }
});
