// FIN-MIGRACAO-LASTRO-EMPRESA-01 — Documentos da Empresa pela tela, com o usuario C (titular da "Empresa C (ficticia)", ja
// no novo aplicativo; tests/supabase_local.py, semear_empresa_c_e2e). Tudo com dados FICTICIOS, enviados aqui:
// classificacao automatica segura (contrato social que cita Pix nao vira pagamento; sem evidencia = "Nao classificado"),
// "Sem lastro" so para documento financeiro, reclassificacao e metadados pela revisao, saidas sem documento (vincular,
// situacao "aguardando contador", desvincular), exclusao pela lista (com confirmacao e recusa com motivo) e arquivo recusado
// com mensagem. Ordem fixa (serial): cada teste parte do estado do anterior.
import { expect, test } from '@playwright/test';

import { gerarPdf } from '../pdf-ficticio.mjs';
import { chamarRpc, perfilAtivoId } from './despesas.mjs';

const C = { email: process.env.CF_EMAIL_C || 'usuario.c@teste.local', senha: process.env.CF_SENHA_C };
const pdf = (...linhas) => gerarPdf([linhas.map((texto) => [[50, texto]])]);
const ARQUIVOS = {
    contrato: ['contrato-lastro-e2e.pdf', pdf('CONTRATO SOCIAL DA EMPRESA C FICTICIA LTDA', 'Os socios podem pagar fornecedores via PIX.')],
    pix: ['pix-lastro-e2e.pdf', pdf('Comprovante de transferencia Pix', 'ID da transacao E2E0001 - Valor R$ 45,00 - Empresa C')],
    neutro: ['neutro-lastro-e2e.pdf', pdf('Documento interno ficticio da Empresa C', 'sem nenhuma palavra reconhecida pela regra.')],
    revisao: ['revisao-lastro-e2e.pdf', pdf('TESTE LASTRO EMPRESA - documento ficticio da Empresa C', 'para excluir pela revisao.')],
};
const SAIDA = 'Saida lastro E2E (ficticia)';
const SAIDA_CONTADOR = 'Saida contador E2E (ficticia)';

test.describe.configure({ mode: 'serial' });
// 1600 px: em 1366 px a coluna "Natureza sugerida" da tabela de saidas (tela original) cobre os botoes de acao da linha
// (pendencia cosmetica registrada em docs/FIN_MIGRACAO_LASTRO_EMPRESA_01.md).
test.use({ viewport: { width: 1600, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    const avisos = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to|Ponte CSP/i.test(msg.text())) problemas.push(msg.text());
        if (msg.type() === 'warning' && /Ponte CSP/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (pedido) => { if (/\/api\//.test(new URL(pedido.url()).pathname)) problemas.push(`rede /api/: ${pedido.url()}`); });
    page.on('dialog', async (dialogo) => {
        avisos.push(dialogo.message());
        await (dialogo.type() === 'confirm' ? dialogo.accept() : dialogo.dismiss());
    });
    testInfo.problemas = problemas;
    testInfo.avisos = avisos;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamada ao Flask').toEqual([]);
});

async function abrirDocumentos(page) {
    await page.goto('/index.html');
    await page.fill('#email', C.email);
    await page.fill('#senha', C.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await page.goto('/documentos-fiscais.html');
    await expect(page.locator('#ir-comprovantes-tbody tr').first()).toBeVisible();
}

const linha = (page, nome) => page.locator('#ir-comprovantes-tbody tr', { hasText: nome });
const saida = (page, descricao) => page.locator('#ir-saidas-tbody tr', { hasText: descricao });

async function documento(page, nome) {
    const perfil = await perfilAtivoId(page);
    const lista = (await chamarRpc(page, 'ir_comprovantes_tela', { p_perfil_id: perfil, p_filtros: {}, p_id: null })).corpo;
    return lista.data.find((d) => (d.arquivo && d.arquivo.nome_arquivo) === nome);
}

// Contadores do resumo pela consulta, depois conferidos na tela (a tela os preenche depois da lista).
async function contadores(page) {
    const lista = (await chamarRpc(page, 'ir_comprovantes_tela', { p_perfil_id: await perfilAtivoId(page), p_filtros: {}, p_id: null })).corpo;
    const r = lista.resumo.documentos_empresa;
    await expect(page.locator('#ir-kpi-total')).toHaveText(String(r.documentos_cadastrados));
    await expect(page.locator('#ir-kpi-categorias')).toHaveText(String(r.sem_lastro));
    return { total: r.documentos_cadastrados, semLastro: r.sem_lastro };
}

async function enviar(page, chave) {
    const [nome, conteudo] = ARQUIVOS[chave];
    await page.click('#ir-btn-importar');
    await page.setInputFiles('#ir-file-input', { name: nome, mimeType: 'application/pdf', buffer: conteudo });
    await page.click('#ir-upload-submit');
    await expect(page.locator('#cf-upload-retorno')).toHaveText('Documento enviado.');
    await page.click('#ir-btn-voltar');
    await expect(linha(page, nome)).toBeVisible();
}

test('classificacao automatica segura e "Sem lastro" so para documento financeiro', async ({ page }) => {
    await abrirDocumentos(page);
    const { semLastro: semLastroAntes } = await contadores(page);
    for (const chave of ['contrato', 'pix', 'neutro']) await enviar(page, chave);

    // Contrato social que cita Pix: documento societario, nao pagamento.
    await expect(linha(page, ARQUIVOS.contrato[0])).toContainText('Contrato Social');
    await expect(linha(page, ARQUIVOS.contrato[0])).toContainText('Documento societario/cadastral');
    await expect(linha(page, ARQUIVOS.contrato[0])).not.toContainText('Pix pago');
    // Comprovante de Pix de verdade: pagamento.
    await expect(linha(page, ARQUIVOS.pix[0])).toContainText('Pix pago');
    // Sem evidencia: "Nao classificado", nunca um palpite.
    await expect(linha(page, ARQUIVOS.neutro[0])).toContainText('Não classificado');
    // So o comprovante de Pix entra em "Sem lastro" (e nas pendencias de lastro).
    await expect(page.locator('#ir-kpi-categorias')).toHaveText(String(semLastroAntes + 1));
    await expect(page.locator('#ir-pendencias')).toContainText(`${semLastroAntes + 1} documentos sem vinculo de lastro`);
});

test('reclassificar e editar metadados pela revisao', async ({ page }) => {
    await abrirDocumentos(page);
    await linha(page, ARQUIVOS.neutro[0]).locator('button[title="Revisar"]').click();
    await expect(page.locator('#ir-review-modal')).toHaveClass(/open/);
    await page.selectOption('#ir-review-categoria-documental', 'CERTIDAO_FEDERAL');
    await page.fill('#ir-review-numero-documento', 'CND-E2E-001');
    await page.fill('#ir-review-orgao-emissor', 'Receita Federal (ficticia)');
    const validade = new Date(Date.now() + 120 * 864e5).toISOString().slice(0, 10);
    await page.fill('#ir-review-data-validade', validade);
    await page.click('#ir-review-save');
    await expect(page.locator('#ir-review-modal')).not.toHaveClass(/open/);
    await expect(linha(page, ARQUIVOS.neutro[0])).toContainText('Certidao Federal');
    await expect(linha(page, ARQUIVOS.neutro[0])).toContainText('Certidao / licenca');

    const doc = await documento(page, ARQUIVOS.neutro[0]);
    expect(doc.metadata_empresarial).toMatchObject({ tipo_documental: 'CERTIDAO_LICENCA', categoria_documental: 'CERTIDAO_FEDERAL',
                                                      numero_documento: 'CND-E2E-001', data_validade: validade,
                                                      status_documental: 'VALIDO', origem_documental: 'USUARIO' });
    const detalhe = (await chamarRpc(page, 'ir_comprovantes_tela', { p_perfil_id: await perfilAtivoId(page), p_filtros: {}, p_id: doc.id })).corpo;
    expect(detalhe.eventos.map((e) => e.descricao)).toContain(
        'Metadados empresariais revisados pelo usuario: Não classificado / Não classificado (inferido) -> Certidao / licenca / Certidao Federal.');
});

test('saidas sem documento: vincular, aguardando contador e desvincular', async ({ page }, testInfo) => {
    await abrirDocumentos(page);
    const perfil = await perfilAtivoId(page);
    const categoria = (await chamarRpc(page, 'categorias_tela', { p_perfil_id: perfil, p_ativo: null })).corpo
        .find((c) => c.nome === 'Servicos C (ficticia)');
    const vencimento = `${new Date().toISOString().slice(0, 7)}-10`;
    for (const [nome, valor] of [[SAIDA, '45.00'], [SAIDA_CONTADOR, '19.90']]) {
        const r = await chamarRpc(page, 'criar_despesa', { p_perfil_id: perfil, p_chave: crypto.randomUUID(),
                                                           p_dados: { nome, valor, categoria_id: categoria.id, data_vencimento: vencimento } });
        expect(r.status, JSON.stringify(r.corpo)).toBe(200);
    }
    await page.reload();
    await expect(saida(page, SAIDA)).toBeVisible();
    const { semLastro: semLastroAntes } = await contadores(page);

    // Vincular o comprovante de Pix a saida: ela sai da lista e o comprovante deixa de ser "sem lastro".
    await saida(page, SAIDA).locator('button[title="Vincular documento"]').click();
    await expect(page.locator('#ir-saida-link-modal')).toHaveClass(/open/);
    const pix = await documento(page, ARQUIVOS.pix[0]);
    await page.selectOption('#ir-saida-link-comprovante', String(pix.id));
    await page.click('#ir-saida-link-save');
    await expect(page.locator('#ir-saida-link-modal')).not.toHaveClass(/open/);
    await expect(saida(page, SAIDA)).toHaveCount(0);
    await expect(page.locator('#ir-kpi-categorias')).toHaveText(String(semLastroAntes - 1));
    const vinculos = (await chamarRpc(page, 'vinculos_documento_tela', { p_perfil_id: perfil, p_comprovante_id: pix.id })).corpo;
    expect(vinculos).toEqual([expect.objectContaining({ tipo_entidade: 'CONTA', resumo_entidade: SAIDA, status_lastro: 'VALIDADO' })]);

    // Situacao manual: aguardando contador.
    await saida(page, SAIDA_CONTADOR).locator('button[title="Aguardando contador"]').click();
    await expect(page.locator('#ir-saida-status-modal')).toHaveClass(/open/);
    await page.fill('#ir-saida-status-observacoes', 'conferir com o contador');
    await page.click('#ir-saida-status-save');
    await expect(page.locator('#ir-saida-status-modal')).not.toHaveClass(/open/);
    await expect(saida(page, SAIDA_CONTADOR)).toContainText(/Aguardando contador/i);

    // Desvincular pelo modal "Vincular" do documento: a saida volta para a lista, sem documento.
    await linha(page, ARQUIVOS.pix[0]).locator('button[title="Vincular"]').click();
    await expect(page.locator('#ir-link-modal')).toHaveClass(/open/);
    await page.locator('.cf-vinculos-ativos .cf-desvincular').click();
    await expect(page.locator('.cf-vinculos-ativos')).toContainText('Nenhum vínculo ativo.');
    await page.locator('#ir-link-modal .ir-modal-close, #ir-link-close').first().click();
    await page.reload();
    await expect(saida(page, SAIDA)).toBeVisible();
    expect(testInfo.avisos.filter((m) => /Desvincular este documento/.test(m))).toHaveLength(1);
});

test('excluir pela lista: confirmacao, contadores e recusa com motivo', async ({ page }, testInfo) => {
    await abrirDocumentos(page);
    const { total } = await contadores(page);
    const botao = linha(page, ARQUIVOS.neutro[0]).locator('button.cf-excluir-documento');
    await expect(botao).toHaveAttribute('title', 'Excluir documento');
    await expect(botao).toHaveAttribute('aria-label', 'Excluir documento');
    await botao.click();
    await expect(linha(page, ARQUIVOS.neutro[0])).toHaveCount(0);
    await expect(page.locator('#ir-kpi-total')).toHaveText(String(total - 1));
    expect(testInfo.avisos[0]).toBe(`Excluir o documento "${ARQUIVOS.neutro[0]}"?\nO arquivo e os dados dele saem do sistema. Esta ação não pode ser desfeita.`);
    expect(await documento(page, ARQUIVOS.neutro[0])).toBeUndefined();

    // O comprovante de Pix tem historico de vinculo (desvinculado no teste anterior): fica preservado, com o motivo.
    await linha(page, ARQUIVOS.pix[0]).locator('button.cf-excluir-documento').click();
    await expect.poll(() => testInfo.avisos.at(-1)).toMatch(/^O documento tem vinculos/);
    await expect(linha(page, ARQUIVOS.pix[0])).toBeVisible();
    await expect(page.locator('#ir-kpi-total')).toHaveText(String(total - 1));
});

// Correcao autorizada (30/10/2026): "Excluir documento" tambem dentro da revisao, com a mesma rota e confirmacao. Cancelar
// nao exclui nem fecha; a recusa mostra o motivo e mantem a revisao aberta; a exclusao fecha a revisao e atualiza a lista.
test('excluir pela revisao: cancelar, recusa com motivo e exclusao', async ({ page }, testInfo) => {
    await abrirDocumentos(page);
    await enviar(page, 'revisao');
    const { total } = await contadores(page);
    const botao = page.locator('#ir-review-modal #cf-review-excluir');

    // Recusa: o comprovante de Pix tem historico de vinculo.
    await linha(page, ARQUIVOS.pix[0]).locator('button[title="Revisar"]').click();
    await expect(page.locator('#ir-review-modal')).toHaveClass(/open/);
    await expect(botao).toHaveText('Excluir documento');
    await botao.click();
    await expect.poll(() => testInfo.avisos.at(-1)).toMatch(/^O documento tem vinculos/);
    await expect(page.locator('#ir-review-modal')).toHaveClass(/open/);
    await page.click('#ir-review-close');

    // Cancelar a confirmacao: nada muda.
    page.removeAllListeners('dialog');
    page.once('dialog', async (dialogo) => { testInfo.avisos.push(dialogo.message()); await dialogo.dismiss(); });
    await linha(page, ARQUIVOS.revisao[0]).locator('button[title="Revisar"]').click();
    await expect(page.locator('#ir-review-modal')).toHaveClass(/open/);
    await botao.click();
    await expect.poll(() => testInfo.avisos.at(-1)).toBe(
        `Excluir o documento "${ARQUIVOS.revisao[0]}"?\nO arquivo e os dados dele saem do sistema. Esta ação não pode ser desfeita.`);
    await expect(page.locator('#ir-review-modal')).toHaveClass(/open/);
    expect(await documento(page, ARQUIVOS.revisao[0])).toBeDefined();

    // Confirmar: exclui, fecha a revisao e atualiza lista e contadores.
    page.once('dialog', async (dialogo) => { testInfo.avisos.push(dialogo.message()); await dialogo.accept(); });
    await botao.click();
    await expect(page.locator('#ir-review-modal')).not.toHaveClass(/open/);
    await expect(linha(page, ARQUIVOS.revisao[0])).toHaveCount(0);
    await expect(page.locator('#ir-kpi-total')).toHaveText(String(total - 1));
    expect(await documento(page, ARQUIVOS.revisao[0])).toBeUndefined();
});

test('arquivo recusado continua com mensagem clara (nada gravado)', async ({ page }) => {
    await abrirDocumentos(page);
    const { total } = await contadores(page);
    await page.click('#ir-btn-importar');
    await page.setInputFiles('#ir-file-input', { name: 'nota.txt', mimeType: 'text/plain', buffer: Buffer.from('texto ficticio') });
    await page.click('#ir-upload-submit');
    await expect(page.locator('#cf-upload-retorno')).toHaveText('Não foi possível enviar o documento. Tipo de arquivo nao permitido');
    await expect(page.locator('#ir-upload-results .ir-upload-card', { hasText: 'nota.txt' }).locator('.ir-status')).toHaveText('Não enviado');
    await page.click('#ir-btn-voltar');
    await expect(page.locator('#ir-kpi-total')).toHaveText(String(total));
});
