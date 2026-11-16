// FIN-REG-04 — pacote ZIP dos documentos da Empresa pelo botao "ZIP" ja existente na tela, com a "Empresa C (ficticia)" e
// arquivos FICTICIOS enviados aqui. O pacote e montado no navegador (nenhuma chamada a servidor /api/): indice, pastas pelo
// tipo documental, bytes originais, filtros da tela, recusas (sem documentos, perfil pessoal, divergencia de integridade).
// A comparacao com o Flask esta em tests/test_zip_documentos_empresa.py. Ordem fixa (serial).
import crypto from 'node:crypto';

import { expect, test } from '@playwright/test';

import { gerarPdf } from '../pdf-ficticio.mjs';
import { chamarRpc, perfilAtivoId } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const C = { email: process.env.CF_EMAIL_C || 'usuario.c@teste.local', senha: process.env.CF_SENHA_C };
const ANO = new Date().getFullYear();
const pdf = (...linhas) => gerarPdf([linhas.map((texto) => [[50, texto]])]);
const PIX = ['pix-zip-e2e.pdf', pdf('Comprovante de transferencia Pix', 'ID da transacao ZIP0001 - Valor R$ 77,00 - Empresa C')];
const NEUTRO = ['neutro-zip-e2e.pdf', pdf('Documento interno ficticio do pacote ZIP', 'sem nenhuma palavra reconhecida pela regra.')];
const NOME_ZIP = `Documentos_Empresa_${ANO}_Contador.zip`;
const empresaC = { perfil: null, documento: null };  // preenchido no primeiro teste (serial)

test.describe.configure({ mode: 'serial' });
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

const linha = (page, nome) => page.locator('#ir-comprovantes-tbody tr', { hasText: nome });

async function enviar(page, [nome, conteudo]) {
    await page.click('#ir-btn-importar');
    await page.setInputFiles('#ir-file-input', { name: nome, mimeType: 'application/pdf', buffer: conteudo });
    await page.click('#ir-upload-submit');
    await expect(page.locator('#cf-upload-retorno')).toHaveText('Documento enviado.');
    await page.click('#ir-btn-voltar');
    await expect(linha(page, nome)).toBeVisible();
}

// Clica em "ZIP" e devolve o pacote. Um aviso no lugar do download e falha, com a mensagem do aviso.
async function baixarZip(page) {
    let download = null;
    let recusa = null;
    const aoBaixar = (d) => { download = d; };
    const aoAvisar = (d) => { recusa = d.message(); };
    page.on('download', aoBaixar);
    page.on('dialog', aoAvisar);
    try {
        await page.click('#ir-doc-btn-zip');
        await expect.poll(() => download !== null || recusa !== null, { timeout: 20000 }).toBe(true);
    } finally {
        page.off('download', aoBaixar);
        page.off('dialog', aoAvisar);
    }
    if (!download) throw new Error(`aviso em vez do pacote: ${recusa}`);
    const partes = [];
    for await (const parte of await download.createReadStream()) partes.push(parte);
    return { nome: download.suggestedFilename(), conteudo: Buffer.concat(partes) };
}

// Nomes das entradas pelo diretorio central do pacote, localizado pelo registro final (o indice .xlsx e outro ZIP, guardado
// sem compressao dentro do pacote: procurar a assinatura no arquivo todo acharia o diretorio dele).
function entradas(zip) {
    const fim = zip.length - 22;
    expect(zip.readUInt32LE(fim)).toBe(0x06054b50);
    const nomes = [];
    let i = zip.readUInt32LE(fim + 16);
    for (let n = zip.readUInt16LE(fim + 10); n > 0; n -= 1) {
        expect(zip.readUInt32LE(i)).toBe(0x02014b50);
        const tamanho = zip.readUInt16LE(i + 28);
        nomes.push(zip.subarray(i + 46, i + 46 + tamanho).toString('utf8'));
        i += 46 + tamanho + zip.readUInt16LE(i + 30) + zip.readUInt16LE(i + 32);
    }
    return nomes;
}

const documentos = async (page) => (await chamarRpc(page, 'ir_comprovantes_tela', { p_perfil_id: await perfilAtivoId(page), p_filtros: {}, p_id: null })).corpo.data;

test('ZIP da Empresa: indice, pastas pelo tipo, bytes originais e filtros da tela', async ({ page }, testInfo) => {
    await abrirDocumentos(page, C);
    await enviar(page, PIX);
    await enviar(page, NEUTRO);
    const antes = page.url();
    const todos = await documentos(page);
    empresaC.perfil = await perfilAtivoId(page);
    empresaC.documento = todos.find((d) => d.arquivo && d.arquivo.nome_arquivo === PIX[0]).id;

    const pacote = await baixarZip(page);
    expect(pacote.nome).toBe(NOME_ZIP);
    const nomes = entradas(pacote.conteudo);
    expect(nomes[0]).toBe('indice_documentos.xlsx');
    // uma entrada por documento com arquivo; os documentos sem arquivo (seeds) ficam so no indice
    expect(nomes.length - 1).toBe(todos.filter((d) => d.arquivo).length);
    expect(nomes.filter((n) => /^pagamentos_realizados\/\d{3}_PAGAMENTO_.*\.pdf$/.test(n)).length).toBeGreaterThanOrEqual(1);
    expect(nomes.filter((n) => /^outros\/\d{3}_DOC_.*\.pdf$/.test(n)).length).toBeGreaterThanOrEqual(1);
    expect(new Set(nomes).size).toBe(nomes.length);
    expect(nomes.every((n) => /^[\x21-\x7e]+$/.test(n))).toBe(true);
    // bytes originais, sem conversao nem recompressao: o PDF enviado esta inteiro dentro do pacote
    expect(pacote.conteudo.includes(PIX[1])).toBe(true);
    expect(pacote.conteudo.includes(NEUTRO[1])).toBe(true);
    for (const texto of ['Nome no ZIP', 'Arquivo nao incluido', 'Total por tipo documental', 'Pacote gerencial para apoio ao contador', PIX[0]]) {
        expect(pacote.conteudo.includes(Buffer.from(texto)), texto).toBe(true);
    }

    // Filtro da tela (aba "Pagamentos realizados"): o pacote so traz o que a lista mostra. O filtro por tipo vale sobre a
    // classificacao GRAVADA (como no Flask); a do comprovante de Pix e gravada aqui, como a revisao da tela faria.
    const gravado = await chamarRpc(page, 'salvar_metadata_empresarial', { p_perfil_id: empresaC.perfil, p_id: empresaC.documento,
        p_dados: { tipo_documental: 'PAGAMENTO_REALIZADO', categoria_documental: 'PIX_PAGO' }, p_chave: crypto.randomUUID() });
    expect(gravado.status).toBeLessThan(300);
    await page.click('#ir-doc-tabs button[data-tipo="PAGAMENTO_REALIZADO"]');
    await expect(linha(page, PIX[0])).toBeVisible();
    await expect(linha(page, NEUTRO[0])).toHaveCount(0);
    const filtrado = await baixarZip(page);
    expect(filtrado.conteudo.includes(PIX[1])).toBe(true);
    expect(filtrado.conteudo.includes(NEUTRO[1])).toBe(false);
    expect(entradas(filtrado.conteudo).slice(1).every((n) => n.startsWith('pagamentos_realizados/'))).toBe(true);

    // Sem documentos para o filtro: aviso claro e nenhum arquivo.
    await page.fill('#ir-filtro-busca', 'nao-existe-reg04');
    await expect(page.locator('#ir-comprovantes-tbody tr', { hasText: PIX[0] })).toHaveCount(0);
    let baixou = false;
    page.once('download', () => { baixou = true; });
    await page.click('#ir-doc-btn-zip');
    await expect.poll(() => testInfo.avisos.join(' | ')).toContain('Nenhum documento encontrado para os filtros selecionados.');
    await expect(page.locator('#ir-doc-btn-zip')).toBeEnabled();
    expect(baixou).toBe(false);
    expect(page.url()).toBe(antes);
    // O ZIP das saidas sem documento continua desabilitado, como na tela original.
    await expect(page.locator('#ir-saidas-btn-zip')).toBeDisabled();
});

test('divergencia de integridade ou falha na leitura de um arquivo nao gera pacote, nem parcial', async ({ page }, testInfo) => {
    await abrirDocumentos(page, C);
    await expect(linha(page, PIX[0])).toBeVisible();
    let baixou = false;
    page.on('download', () => { baixou = true; });

    // O arquivo chega com um byte diferente do registrado (resposta da consulta adulterada so neste teste).
    await page.route('**/rest/v1/rpc/arquivo_comprovante_tela', async (rota) => {
        const resposta = await rota.fetch();
        const dados = await resposta.json();
        const bytes = Buffer.from(dados.conteudo_base64, 'base64');
        bytes[bytes.length - 1] ^= 0xff;
        await rota.fulfill({ response: resposta, json: { ...dados, conteudo_base64: bytes.toString('base64') } });
    });
    await page.click('#ir-doc-btn-zip');
    await expect.poll(() => testInfo.avisos.join(' | ')).toContain('conteúdo diferente do registrado (SHA-256). O pacote não foi gerado.');
    await expect(page.locator('#ir-doc-btn-zip')).toBeEnabled();
    await page.unroute('**/rest/v1/rpc/arquivo_comprovante_tela');

    // A consulta do arquivo falha: mensagem clara, sem detalhe interno, e nenhum pacote.
    testInfo.avisos.length = 0;
    await page.route('**/rest/v1/rpc/arquivo_comprovante_tela', (rota) => rota.fulfill({ status: 500, json: { message: 'falha simulada', code: 'XX000' } }));
    await page.click('#ir-doc-btn-zip');
    await expect.poll(() => testInfo.avisos.length).toBe(1);
    expect(testInfo.avisos[0]).not.toContain('XX000');
    await expect(page.locator('#ir-doc-btn-zip')).toBeEnabled();
    await page.unroute('**/rest/v1/rpc/arquivo_comprovante_tela');
    expect(baixou).toBe(false);

    // Sem a interferencia, o pacote volta a ser gerado.
    const pacote = await baixarZip(page);
    expect(pacote.nome).toBe(NOME_ZIP);
    expect(pacote.conteudo.includes(PIX[1])).toBe(true);
});

test('perfil pessoal nao gera nem consulta o pacote; os documentos de teste sao removidos', async ({ page, browser }) => {
    await abrirDocumentos(page, B);
    await expect(page.locator('#ir-doc-btn-zip')).toBeHidden();
    const recusa = await page.evaluate(async () => {
        const r = await fetch('/api/ir/documentos-empresa/exportar-zip');
        return { status: r.status, corpo: await r.json() };
    });
    expect(recusa).toEqual({ status: 403, corpo: { success: false, error: 'Pacote de documentos empresariais disponivel apenas no perfil Empresa.' } });
    // A conta do Perfil B nao le os documentos nem os arquivos da Empresa C.
    for (const [funcao, corpo] of [['ir_comprovantes_tela', { p_perfil_id: empresaC.perfil, p_filtros: {}, p_id: null }],
                                   ['arquivo_comprovante_tela', { p_perfil_id: empresaC.perfil, p_comprovante_id: empresaC.documento }]]) {
        const r = await chamarRpc(page, funcao, corpo);
        expect(r.status, funcao).toBeGreaterThanOrEqual(400);
        expect(r.corpo.code, funcao).toBe('42501');
    }
    // Com o proprio perfil, o arquivo da Empresa C continua inacessivel ("nao encontrado", sem revelar que existe).
    const alheio = await chamarRpc(page, 'arquivo_comprovante_tela', { p_perfil_id: await perfilAtivoId(page), p_comprovante_id: empresaC.documento });
    expect(alheio.status).toBeGreaterThanOrEqual(400);
    expect(alheio.corpo.message).toBe('Comprovante nao encontrado');

    // Limpeza: os dois documentos ficticios enviados neste arquivo saem da Empresa C (sessao propria da conta C).
    const contexto = await browser.newContext({ viewport: { width: 1600, height: 900 } });
    const paginaC = await contexto.newPage();
    await abrirDocumentos(paginaC, C);
    const enviados = (lista) => lista.filter((x) => x.arquivo && [PIX[0], NEUTRO[0]].includes(x.arquivo.nome_arquivo));
    for (const d of enviados(await documentos(paginaC))) {
        // o documento classificado na tela so sai sem o registro de classificacao: a exclusao cuida disso (FIN-MIGRACAO-LASTRO-EMPRESA-01)
        expect((await chamarRpc(paginaC, 'excluir_comprovante', { p_perfil_id: empresaC.perfil, p_id: d.id })).status).toBeLessThan(300);
    }
    expect(enviados(await documentos(paginaC))).toEqual([]);
    await contexto.close();
});
