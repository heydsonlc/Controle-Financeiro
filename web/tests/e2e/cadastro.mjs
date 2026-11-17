// FIN-MVP-CADASTRO-UNIFICADO-01 — apoio dos specs para o modal unico de cadastro de despesas (js/cadastro-despesa.js),
// aberto por Despesas, Lancamentos e Recorrencias, no desktop e no celular.
import { expect } from '@playwright/test';

export const TIPOS = { direta: 'DESPESA_DIRETA', compra: 'COMPRA_CARTAO', recorrente: 'DESPESA_RECORRENTE', consorcio: 'CONSORCIO' };
export const modal = (page) => page.locator('#cad-modal');
export const confirmacao = (page) => page.locator('#cad-confirmacao');
export const erroDoCampo = (page, id) => page.locator('#cad-modal .mob-campo', { has: page.locator(`#${id}`) }).locator('.mob-campo-erro');
export const mensagem = (page) => page.locator('#cad-mensagem');

// O modal aberto e pronto (permissao e categorias carregadas), no tipo esperado.
export async function esperarModal(page, tipo) {
    await expect(modal(page)).toBeVisible();
    await expect(page.locator('#cad-tipo')).toBeEnabled();
    if (tipo) await expect(modal(page)).toHaveAttribute('data-tipo', TIPOS[tipo] || tipo);
}

// Troca o tipo de operacao; se o modal perguntar (havia algo preenchido so do tipo anterior), confirma a troca.
export async function escolherTipo(page, tipo) {
    const valor = TIPOS[tipo] || tipo;
    if ((await page.inputValue('#cad-tipo')) !== valor) {
        await page.selectOption('#cad-tipo', valor);
        if (await page.locator('#cad-troca').isVisible()) await page.click('#cad-troca-confirmar');
    }
    await expect(modal(page)).toHaveAttribute('data-tipo', valor);
}

async function selecionar(page, seletor, texto) {
    const controle = page.locator(seletor);
    if (texto === undefined || texto === null) {
        if (!(await controle.inputValue())) await controle.selectOption({ index: 1 });
        return;
    }
    const valor = await controle.locator('option', { hasText: texto }).first().getAttribute('value');
    await controle.selectOption(valor);
}

async function data(page, seletor, valor) {
    await page.fill(seletor, valor);
    await page.locator(seletor).dispatchEvent('change');
}

// Preenche o modal aberto. d.tipo: direta | compra | recorrente | consorcio (padrao: o tipo ja aberto).
//   comuns: nome, valor, categoria (texto da opcao; sem ela, a primeira), observacoes
//   direta: vencimento, competencia (AAAA-MM, pela acao "Alterar competencia")
//   compra: cartao (texto), data, parcelas, fatura (AAAA-MM)
//   recorrente: inicio, frequencia (mensal|semanal|quinzenal|anual), dia (0-6), meio ('', boleto, pix, debito,
//               debito_automatico, cartao), cartao (texto), conta (texto), inativa
//   consorcio: parcelas, inicio (AAAA-MM), reajuste (nenhum|percentual|fixo), valorReajuste, contemplacao, anteriores
export async function preencherCadastro(page, d) {
    await esperarModal(page);
    if (d.tipo) await escolherTipo(page, d.tipo);
    const tipo = await page.inputValue('#cad-tipo');
    if (tipo === TIPOS.compra) {
        await expect.poll(() => page.locator('#cad-cartao option').count()).toBeGreaterThan(1);
        if (d.cartao !== undefined || !(await page.inputValue('#cad-cartao'))) await selecionar(page, '#cad-cartao', d.cartao);
    }
    if (d.nome !== undefined) await page.fill('#cad-nome', d.nome);
    if (d.valor !== undefined) await page.fill('#cad-valor', String(d.valor));
    if (d.categoria !== false) await selecionar(page, '#cad-categoria', d.categoria);
    if (tipo === TIPOS.direta) {
        if (d.vencimento) await data(page, '#cad-vencimento', d.vencimento);
        if (d.competencia) {
            if (await page.locator('#cad-alterar-competencia').isVisible()) await page.click('#cad-alterar-competencia');
            await page.fill('#cad-competencia', d.competencia);
        }
    } else if (tipo === TIPOS.compra) {
        if (d.data) await data(page, '#cad-data-compra', d.data);
        if (d.parcelas !== undefined) await page.fill('#cad-parcelas', String(d.parcelas));
        if (d.fatura) await page.fill('#cad-mes-fatura', d.fatura);
    } else if (tipo === TIPOS.recorrente) {
        if (d.inicio) await data(page, '#cad-data-inicial', d.inicio);
        if (d.meio !== undefined && d.meio !== 'cartao') await page.selectOption('#cad-meio-pagamento', d.meio);
        if (d.frequencia) await page.selectOption('#cad-frequencia', d.frequencia);
        if (d.meio === 'cartao') {
            await page.selectOption('#cad-meio-pagamento', 'cartao');
            await expect.poll(() => page.locator('#cad-cartao-recorrencia option').count()).toBeGreaterThan(1);
            await selecionar(page, '#cad-cartao-recorrencia', d.cartao);
        }
        if (d.dia !== undefined) await page.selectOption('#cad-dia-semana', String(d.dia));
        if (d.meio === 'debito_automatico') {
            await expect.poll(() => page.locator('#cad-conta-bancaria option').count()).toBeGreaterThan(1);
            await selecionar(page, '#cad-conta-bancaria', d.conta);
        }
        if (d.inativa) {
            if (await page.locator('#cad-abrir-opcoes').isVisible()) await page.click('#cad-abrir-opcoes');
            await page.check('#cad-inativa');
        }
    } else if (tipo === TIPOS.consorcio) {
        if (d.parcelas !== undefined) await page.fill('#cad-numero-parcelas', String(d.parcelas));
        if (d.inicio) await page.fill('#cad-mes-inicio', d.inicio);
        if (d.reajuste) await page.selectOption('#cad-tipo-reajuste', d.reajuste);
        if (d.valorReajuste !== undefined) await page.fill('#cad-valor-reajuste', String(d.valorReajuste));
        if (d.contemplacao) await page.fill('#cad-mes-contemplacao', d.contemplacao);
        if (d.anteriores !== undefined) await page.fill('#cad-parcelas-anteriores', String(d.anteriores));
    }
    if (d.observacoes !== undefined) {
        if (await page.locator('#cad-abrir-observacoes').isVisible()) await page.click('#cad-abrir-observacoes');
        await page.fill('#cad-campos textarea', d.observacoes);
    }
}

// Salvar e esperar a confirmacao do servidor; devolve o texto dela. confirmarConsolidada: responde a pergunta da fatura.
export async function salvarCadastro(page, { concluir = true, confirmarConsolidada = true } = {}) {
    await page.click('#cad-salvar');
    if (confirmarConsolidada) {
        await expect(page.locator('#cad-confirmacao, #cad-consolidada:not([hidden])')).toBeVisible();
        if (await page.locator('#cad-consolidada').isVisible()) await page.click('#mob-confirmar-inclusao');
    }
    await expect(confirmacao(page)).toBeVisible();
    const texto = (await confirmacao(page).innerText()).replace(/\s+/g, ' ').trim();
    if (concluir) {
        await page.click('#cad-concluir');
        await expect(modal(page)).toHaveCount(0);
    }
    return texto;
}

// Salvar esperando recusa (validacao da tela ou do servico): devolve a mensagem do rodape, ou a do primeiro campo.
export async function salvarComErro(page) {
    await page.click('#cad-salvar');
    await expect(page.locator('#cad-mensagem.erro, #cad-modal .mob-campo-erro:not([hidden])').first()).toBeVisible();
    await expect(confirmacao(page)).toHaveCount(0);
    if (await page.locator('#cad-mensagem.erro').isVisible()) return (await mensagem(page).innerText()).trim();
    return (await page.locator('#cad-modal .mob-campo-erro:not([hidden])').first().innerText()).trim();
}

export async function fecharCadastro(page) {
    await page.click('#cad-cancelar');
    await expect(modal(page)).toHaveCount(0);
}

// Cadastro inteiro a partir do modal ja aberto: preenche, salva e conclui.
export async function cadastrar(page, d, opcoes) {
    await preencherCadastro(page, d);
    return salvarCadastro(page, opcoes);
}
