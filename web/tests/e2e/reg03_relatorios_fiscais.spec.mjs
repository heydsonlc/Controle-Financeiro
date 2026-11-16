// FIN-REG-03 — relatorios fiscais pela tela de Documentos Fiscais (dados FICTICIOS dos seeds de teste):
// Imposto de Renda no perfil pessoal ("Perfil B") e Documentos Fiscais + Saidas sem documento na "Empresa C (ficticia)".
// Os botoes ja existentes da tela geram o arquivo no navegador (nenhuma chamada a servidor /api/), com nome, extensao e
// formato validos; o conteudo e conferido com o Flask em tests/test_relatorios_fiscais.py.
import { expect, test } from '@playwright/test';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const C = { email: process.env.CF_EMAIL_C || 'usuario.c@teste.local', senha: process.env.CF_SENHA_C };
const ANO = new Date().getFullYear();

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
    page.on('dialog', async (dialogo) => { avisos.push(dialogo.message()); await dialogo.dismiss(); });
    testInfo.problemas = problemas;
    testInfo.avisos = avisos;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamada ao Flask').toEqual([]);
});

async function abrirDocumentos(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await page.goto('/documentos-fiscais.html');
    await expect(page.locator('#ir-filtro-ano')).toBeVisible();
    await expect(page.locator('#perfil-financeiro-switcher')).toHaveAttribute('data-perfil-ativo-id', /^\d+$/);
}

async function baixar(page, seletor) {
    const [download] = await Promise.all([page.waitForEvent('download'), page.click(seletor)]);
    const partes = [];
    for await (const parte of await download.createReadStream()) partes.push(parte);
    return { nome: download.suggestedFilename(), conteudo: Buffer.concat(partes) };
}

const ehXlsx = (conteudo) => conteudo.subarray(0, 2).toString('latin1') === 'PK' && conteudo.includes(Buffer.from('xl/workbook.xml'));
const ehPdf = (conteudo) => conteudo.subarray(0, 8).toString('latin1') === '%PDF-1.4' && conteudo.subarray(-5).toString('latin1') === '%%EOF';
async function pedirArquivo(page, rota) {
    const r = await page.evaluate(async (endereco) => {
        const resposta = await fetch(endereco);
        const bytes = new Uint8Array(await resposta.arrayBuffer());
        return { status: resposta.status, tipo: resposta.headers.get('Content-Type'), nome: resposta.headers.get('Content-Disposition'),
                 bytes: Array.from(bytes) };
    }, rota);
    return { ...r, conteudo: Buffer.from(r.bytes) };
}

const pedir = (page, rota) => page.evaluate(async (r) => {
    const resposta = await fetch(r);
    return { status: resposta.status, tipo: resposta.headers.get('Content-Type'), corpo: resposta.ok ? null : await resposta.json() };
}, rota);

test('Imposto de Renda (perfil pessoal): Exportar, Excel e PDF geram o relatorio da lista em tela, sem sair da pagina', async ({ page }, testInfo) => {
    await abrirDocumentos(page, B);
    await expect(page.locator('#ir-comprovantes-tbody tr', { hasText: 'Clinica E2E (ficticia)' })).toBeVisible();
    const antes = page.url();
    const linhas = await page.locator('#ir-comprovantes-tbody tr').count();

    const exportar = await baixar(page, '#ir-btn-exportar');  // "Exportar" da barra de acoes: Excel, como no Flask
    expect(exportar.nome).toBe(`IRPF_${ANO}_Perfil_B.xlsx`);
    expect(ehXlsx(exportar.conteudo)).toBe(true);
    for (const texto of ['Clinica E2E (ficticia)', 'Total de comprovantes', 'Categoria IR', 'Comprovantes']) {
        expect(exportar.conteudo.includes(Buffer.from(texto)), texto).toBe(true);
    }
    // No perfil pessoal a tela original so mostra "Exportar" (os botoes Excel/PDF/ZIP do painel sao do modo Empresa): o PDF
    // do IRPF e gerado pela mesma rota da tela.
    for (const botao of ['#ir-btn-excel', '#ir-btn-pdf', '#ir-doc-btn-zip']) await expect(page.locator(botao)).toBeHidden();
    const pdf = await pedirArquivo(page, `/api/ir/relatorios/pdf?ano=${ANO}`);
    expect(pdf.nome).toContain(`IRPF_${ANO}_Perfil_B.pdf`);
    expect(pdf.tipo).toBe('application/pdf');
    expect(ehPdf(pdf.conteudo)).toBe(true);
    const texto = pdf.conteudo.toString('latin1');
    expect(texto).toContain('Relatorio de Comprovantes - Imposto de Renda');
    expect(texto).toContain('Perfil financeiro: Perfil B');
    expect(texto).toContain('Clinica E2E \\(ficticia\\)');
    expect(texto).toContain('Relatorio informativo. A dedutibilidade deve ser validada');

    // Filtro da tela vale para o relatorio: busca sem resultado gera o relatorio vazio (como no Flask), sem erro.
    await page.fill('#ir-filtro-busca', 'nao-existe-reg03');
    await expect(page.locator('#ir-comprovantes-tbody tr', { hasText: 'Clinica E2E (ficticia)' })).toHaveCount(0);
    const vazio = await baixar(page, '#ir-btn-exportar');
    expect(ehXlsx(vazio.conteudo)).toBe(true);
    expect(vazio.conteudo.includes(Buffer.from('Clinica E2E'))).toBe(false);
    expect(vazio.conteudo.includes(Buffer.from('Total de comprovantes'))).toBe(true);
    await page.fill('#ir-filtro-busca', '');
    await expect(page.locator('#ir-comprovantes-tbody tr')).toHaveCount(linhas);  // a lista segue como estava

    expect(page.url()).toBe(antes);
    expect(testInfo.avisos).toEqual([]);
    await expect(page.locator('#ir-btn-exportar')).toBeEnabled();
    // Saidas sem documento: so no perfil Empresa (painel oculto e rota recusada com a mensagem do Flask).
    await expect(page.locator('#ir-saidas-sem-documento-panel')).toBeHidden();
    for (const formato of ['excel', 'pdf']) {
        expect(await pedir(page, `/api/ir/lastro/saidas-sem-documento/relatorio-${formato}?ano=${ANO}`)).toEqual({
            status: 403, tipo: 'application/json',
            corpo: { success: false, error: 'Relatorio de lastro empresarial disponivel apenas no perfil Empresa.' } });
    }
    // Filtro invalido: recusa clara, sem arquivo.
    expect((await pedir(page, '/api/ir/relatorios/excel?ano=abc')).corpo.error).toBe('Ano do relatorio invalido');
    // OCR continua indisponivel (aviso preservado).
    const ocr = await pedir(page, '/api/ir/comprovantes/1/reprocessar-ocr');
    expect(ocr.status).toBe(501);
    expect(ocr.corpo.error).toContain('OCR de imagem');
});

test('Empresa: relatorio de Documentos Fiscais e de Saidas sem documento em Excel e PDF', async ({ page }, testInfo) => {
    await abrirDocumentos(page, C);
    await expect(page.locator('#ir-saidas-sem-documento-panel')).toBeVisible();
    const antes = page.url();

    const excel = await baixar(page, '#ir-btn-excel');
    expect(excel.nome).toMatch(new RegExp(`^Documentos_Fiscais_${ANO}_Empresa_C.*\\.xlsx$`));
    expect(ehXlsx(excel.conteudo)).toBe(true);
    for (const texto of ['Documentos Fiscais e Lastro', 'Categoria Fiscal', 'Lastros', 'Status do lastro']) {
        expect(excel.conteudo.includes(Buffer.from(texto)), texto).toBe(true);
    }
    const pdf = await baixar(page, '#ir-btn-pdf');
    expect(pdf.nome).toMatch(new RegExp(`^Documentos_Fiscais_${ANO}_Empresa_C.*\\.pdf$`));
    expect(ehPdf(pdf.conteudo)).toBe(true);
    expect(pdf.conteudo.toString('latin1')).toContain('Relatorio de Documentos Fiscais e Lastro');

    const saidasExcel = await baixar(page, '#ir-saidas-btn-excel');
    expect(saidasExcel.nome).toMatch(new RegExp(`^Saidas_sem_documento_Empresa_C.*_${ANO}\\.xlsx$`));
    expect(ehXlsx(saidasExcel.conteudo)).toBe(true);
    for (const texto of ['Saidas_sem_documento', 'Pendencias_contador', 'Total por origem', 'Valor total sem documento']) {
        expect(saidasExcel.conteudo.includes(Buffer.from(texto)), texto).toBe(true);
    }
    const saidasPdf = await baixar(page, '#ir-saidas-btn-pdf');
    expect(saidasPdf.nome).toMatch(new RegExp(`^Saidas_sem_documento_Empresa_C.*_${ANO}\\.pdf$`));
    expect(ehPdf(saidasPdf.conteudo)).toBe(true);
    const texto = saidasPdf.conteudo.toString('latin1');
    expect(texto).toContain('Relatorio de Saidas sem Documento');
    expect(texto).toContain(`Periodo: ${ANO}`);

    // Mes invalido: a mesma recusa do Flask, sem arquivo.
    expect(await pedir(page, `/api/ir/lastro/saidas-sem-documento/relatorio-pdf?ano=${ANO}&mes=13`)).toEqual({
        status: 400, tipo: 'application/json', corpo: { success: false, error: 'Mes do relatorio invalido' } });
    expect(page.url()).toBe(antes);
    expect(testInfo.avisos).toEqual([]);
    for (const botao of ['#ir-btn-excel', '#ir-btn-pdf', '#ir-saidas-btn-excel', '#ir-saidas-btn-pdf']) await expect(page.locator(botao)).toBeEnabled();
    // O ZIP das saidas continua desabilitado, como na tela original.
    await expect(page.locator('#ir-saidas-btn-zip')).toBeDisabled();
});
