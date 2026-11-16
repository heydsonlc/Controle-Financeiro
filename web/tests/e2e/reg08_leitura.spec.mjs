// FIN-REG-08 — leitura e classificacao sugerida de documentos fiscais, com dados FICTICIOS (banco descartavel):
//   * desktop (documentos-fiscais.html): imagem enviada e lida por OCR no navegador; a revisao recebe as sugestoes so nos
//     campos vazios e nunca troca uma correcao manual;
//   * celular (documentos-mobile.html): Fotografar/Selecionar -> pre-visualizacao -> leitura -> conferencia -> ajustar
//     categoria -> confirmar envio; cancelar sem gravar; arquivo repetido nao altera o existente; leitor sem o botao;
//   * preparo do arquivo (foto acima de 10 MB reduzida, HEIC e formato invalido recusados) e a CSP por caminho
//     ('wasm-unsafe-eval' so nas paginas de documentos e nos arquivos do OCR).
// Nenhum pedido sai para outro endereco (OCR, modelo e worker sao do proprio site). Ordem fixa (serial).
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { gerarPdf } from '../pdf-ficticio.mjs';
import { chamarRpc } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const C = { email: process.env.CF_EMAIL_C || 'usuario.c@teste.local', senha: process.env.CF_SENHA_C };
const H = { email: process.env.CF_EMAIL_H || 'usuario.h@teste.local', senha: process.env.CF_SENHA_H };
const EVIDENCIAS = process.env.CF_EVIDENCIAS_DIR;
const HOJE = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const ANO = HOJE.slice(0, 4);
const DATA_BR = `${HOJE.slice(8, 10)}/${HOJE.slice(5, 7)}/${ANO}`;

// NFS-e de Goiania FICTICIA (mesmo leiaute do exemplo do Flask; nomes, CNPJ e CPF de teste).
const LABORATORIO = 'Laboratorio Ficticio E2E SA';
const CNPJ_LABORATORIO = '11.222.333/0001-81';
// marca: o projeto do Playwright (cada motor envia o seu arquivo; o mesmo arquivo seria "ja enviado").
const nfse = (marca) => gerarPdf([[
    'Serie do Documento', 'Prefeitura Municipal de Goiania - GO Nota Fiscal de', 'Servico Eletronica -', 'Secretaria Municipal da Fazenda',
    'NFS-e', 'Numero da Nota Fiscal', '90817', 'Dados do Prestador de Servico', 'Data de Geracao da NFS-e', `${DATA_BR} 10:20:08`,
    LABORATORIO, 'Data de Competencia', 'Laboratorio Ficticio', DATA_BR, 'Rua Ficticia, 100 - Setor Teste',
    `Inscricao Municipal 99999 - CPF/CNPJ ${CNPJ_LABORATORIO}`, 'Identificacao da Nota Fiscal Eletronica',
    'Dados do Tomador de Servicos', 'CNPJ/CPF : 529.982.247-25 IM :', 'Razao Social : TITULAR FICTICIO E2E',
    'Descricao dos Servicos', 'SERVICOS PRESTADOS EXAMES LABORATORIAIS (ficticio)', 'Detalhamento dos Tributos',
    'Vl. Total dos Servicos Desconto Incondicionado Deducoes Base Calculo', 'R$ 130,80 R$ 0,00 R$ 0,00 R$ 130,80',
    'PIS COFINS INSS IRRF CSLL Outras Retencoes Vl. ISSQN Retido Vl. Liquido da Nota Fiscal',
    'R$ 0,00 R$ 0,00 R$ 0,00 R$ 0,00 R$ 0,00 R$ 0,00 R$ 0,00 R$ 130,80', `Ensaio: ${marca}`,
].map((t) => [[40, t]])]);
// Recibo generico com varios valores distintos: valor ambiguo (nenhum e escolhido sozinho).
const recibo = (marca) => gerarPdf([[
    'RECIBO (ficticio) - documento de teste da leitura', 'Recebi de Titular Ficticio E2E a importancia abaixo.',
    `Data: ${DATA_BR}`, 'Servico de manutencao: R$ 80,00', 'Material: R$ 45,50', 'Deslocamento: R$ 12,00', `Ensaio: ${marca}`,
].map((t) => [[40, t]])]);
// Cupom FICTICIO desenhado em texto grande e fotografado (captura de tela): lido por OCR.
const CUPOM_HTML = `<!doctype html><html><body style="margin:0;background:#fff">
<pre style="font:600 34px/1.45 'Courier New',monospace;color:#000;padding:48px 56px;margin:0">PADARIA FICTICIA E2E LTDA
CNPJ 11.222.333/0001-81
CUPOM FISCAL ELETRONICO - SAT
${DATA_BR} 10:15
PAO FRANCES          10,00
CAFE COADO           15,00
TOTAL R$             25,00
DINHEIRO             30,00
TROCO                 5,00</pre></body></html>`;

test.describe.configure({ mode: 'serial' });
test.setTimeout(180000);

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => {
        // Ensaio WebKit: pedido interrompido pela troca de pagina vira erro "access control checks" (comportamento do motor,
        // nao do aplicativo). So nesse projeto e so essa mensagem; o resto continua contando.
        if (testInfo.project.name === 'webkit-aproximado' && /\/rest\/v1\/rpc\/\w+ due to access control checks\.$/.test(erro.message)) return;
        problemas.push(`pageerror: ${erro.message}`);
    });
    page.on('request', (req) => {
        const url = new URL(req.url());
        if (url.protocol === 'blob:' || url.protocol === 'data:') return;
        if (!['127.0.0.1', 'localhost'].includes(url.hostname)) problemas.push(`pedido externo: ${req.url()}`);
        if (url.pathname.startsWith('/api/')) problemas.push(`pedido a /api/: ${req.url()}`);
    });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP, erros de JS, pedidos externos ou a /api/').toEqual([]);
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
    await page.waitForURL(/\/(inicio|contas)\.html/);  // celular: inicio; desktop: contas
    await page.waitForLoadState('networkidle');
}

async function rpc(page, funcao, corpo) {
    const r = await chamarRpc(page, funcao, corpo);
    expect(r.status, `${funcao}: ${JSON.stringify(r.corpo)}`).toBe(200);
    return r.corpo;
}

async function perfilDaConta(page) {
    const perfis = await rpc(page, 'meus_perfis', {});
    expect(perfis.length).toBe(1);
    return perfis[0].id;
}

const documentos = async (page, perfil) => (await rpc(page, 'ir_comprovantes_tela', { p_perfil_id: perfil, p_filtros: {}, p_id: null })).data;
const documento = async (page, perfil, id) => (await rpc(page, 'ir_comprovantes_tela', { p_perfil_id: perfil, p_filtros: {}, p_id: id }));
const porArquivo = (lista, nome) => lista.filter((d) => d.arquivo && d.arquivo.nome_arquivo === nome).sort((a, b) => b.id - a.id);  // o mais recente primeiro
const revisar = (page, id) => page.locator(`#ir-comprovantes-tbody [data-on-click="window.IRDoc.abrirRevisao(${id})"]`);

// A "foto" do cupom: o texto desenhado numa pagina em branco, capturado como PNG (sem documento real).
async function fotoDoCupom(browser) {
    const contexto = await browser.newContext({ viewport: { width: 900, height: 620 }, deviceScaleFactor: 1 });
    const p = await contexto.newPage();
    await p.setContent(CUPOM_HTML);
    const png = await p.screenshot({ type: 'png', fullPage: true });
    await contexto.close();
    return png;
}

test.describe('desktop', () => {
    test.use({ viewport: { width: 1366, height: 900 } });

    test('imagem lida por OCR no navegador; revisao com sugestoes so nos campos vazios, sem trocar a correcao manual', async ({ page, browser }) => {
        const png = await fotoDoCupom(browser);
        await entrar(page, B);
        const perfil = await perfilDaConta(page);
        await page.goto('/documentos-fiscais.html');
        await page.click('#ir-btn-importar');
        await page.setInputFiles('#ir-file-input', { name: 'cupom-reg08-desktop.png', mimeType: 'image/png', buffer: png });
        await page.click('#ir-upload-submit');
        await expect(page.locator('#cf-upload-retorno')).toHaveText('Documento enviado.', { timeout: 150000 });
        await expect(page.locator('#cf-upload-leitura')).toContainText('Texto lido automaticamente em 1 documento');
        await evidencia(page, 'reg08-desktop-envio');

        // No banco: o texto lido e a origem (OCR da imagem); o documento fica pendente, sem dados preenchidos sozinhos.
        const [enviado] = porArquivo(await documentos(page, perfil), 'cupom-reg08-desktop.png');
        const completo = await documento(page, perfil, enviado.id);
        expect(completo.texto_extraido).toMatch(/PADARIA/i);
        expect(completo.origem_classificacao).toBe('OCR_IMAGEM');
        expect([completo.status, completo.prestador_nome || null, completo.valor ?? null]).toEqual(['PENDENTE_REVISAO', null, null]);

        // Revisao: tudo marcado para conferir (OCR); o valor coerente com o troco e sugerido.
        await page.click('#ir-btn-voltar');
        await revisar(page, enviado.id).click();
        await expect(page.locator('#ir-review-modal')).toHaveClass(/open/);
        await expect(page.locator('#cf-leitura-resumo')).toContainText('Leitura automática (OCR da imagem): Cupom fiscal.');
        await expect(page.locator('#ir-review-prestador')).toHaveValue(/PADARIA FICTICIA E2E/i);
        await expect(page.locator('#ir-review-prestador')).toHaveClass(/cf-sugerido/);
        await expect(page.locator('#ir-review-doc')).toHaveValue('11.222.333/0001-81');
        await expect(page.locator('#ir-review-valor')).toHaveValue(/^25(\.00?)?$/);
        await expect(page.locator('#ir-review-valor').locator('xpath=ancestor::label').locator('.cf-leitura-nota')).toHaveText('Conferir informação');
        await expect(page.locator('#ir-review-data')).toHaveValue(HOJE);
        await evidencia(page, 'reg08-desktop-revisao');

        // Correcao manual gravada pelo "Salvar revisao".
        await page.fill('#ir-review-prestador', 'Padaria corrigida manualmente (ficticia)');
        await page.click('#ir-review-save');
        await expect(page.locator('#ir-review-modal')).not.toHaveClass(/open/);
        const revisado = await documento(page, perfil, enviado.id);
        expect([revisado.prestador_nome, Number(revisado.valor), revisado.status]).toEqual(['Padaria corrigida manualmente (ficticia)', 25, 'PENDENTE_REVISAO']);

        // Reaberta: a correcao fica; a leitura aparece so como nota. Fechar sem salvar nao grava nada.
        await revisar(page, enviado.id).click();
        await expect(page.locator('#ir-review-modal')).toHaveClass(/open/);
        await expect(page.locator('#cf-leitura-resumo')).toBeVisible();
        await expect(page.locator('#ir-review-prestador')).toHaveValue('Padaria corrigida manualmente (ficticia)');
        await expect(page.locator('#ir-review-prestador')).not.toHaveClass(/cf-sugerido/);
        await expect(page.locator('#ir-review-prestador').locator('xpath=ancestor::label').locator('.cf-leitura-nota'))
            .toContainText('(o valor atual foi mantido)');
        await page.click('#ir-review-close');
        expect(await documento(page, perfil, enviado.id)).toEqual(revisado);
    });

    test('documento generico: nada preenchido sozinho; "Usar" aplica so a sugestao escolhida', async ({ page }, testInfo) => {
        const generico = gerarPdf([[`Recibo de servico (ficticio) - ${testInfo.project.name}`, `Data: ${DATA_BR}`,
            'Emitente CNPJ 11.222.333/0001-81', 'Valor recebido: R$ 77,00'].map((t) => [[40, t]])]);
        await entrar(page, B);
        const perfil = await perfilDaConta(page);
        await page.goto('/documentos-fiscais.html');
        await page.click('#ir-btn-importar');
        await page.setInputFiles('#ir-file-input', { name: 'recibo-generico-reg08.pdf', mimeType: 'application/pdf', buffer: generico });
        await page.click('#ir-upload-submit');
        await expect(page.locator('#cf-upload-retorno')).toHaveText('Documento enviado.', { timeout: 60000 });
        const [enviado] = porArquivo(await documentos(page, perfil), 'recibo-generico-reg08.pdf');
        await page.click('#ir-btn-voltar');
        await revisar(page, enviado.id).click();
        await expect(page.locator('#ir-review-modal')).toHaveClass(/open/);
        await expect(page.locator('#cf-leitura-resumo')).toContainText('Documento sem modelo reconhecido: nada foi preenchido.');
        for (const campo of ['#ir-review-valor', '#ir-review-doc', '#ir-review-data']) await expect(page.locator(campo)).toHaveValue('');
        const notaValor = page.locator('#ir-review-valor').locator('xpath=ancestor::label').locator('.cf-leitura-nota');
        await expect(notaValor).toContainText('A leitura sugere: R$ 77,00.');
        await evidencia(page, 'reg08-desktop-generico');
        await notaValor.locator('.cf-leitura-usar').click();
        await expect(page.locator('#ir-review-valor')).toHaveValue(/^77(\.00?)?$/);
        await expect(page.locator('#ir-review-valor')).toHaveClass(/cf-sugerido/);
        await page.click('#ir-review-save');
        await expect(page.locator('#ir-review-modal')).not.toHaveClass(/open/);
        const salvo = await documento(page, perfil, enviado.id);
        expect([Number(salvo.valor), salvo.prestador_cpf_cnpj || null, salvo.data_documento || null, salvo.status])
            .toEqual([77, null, null, 'PENDENTE_REVISAO']);  // so o que o usuario escolheu usar
    });
});

test.describe('celular', () => {
    test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

    const folha = (page) => page.locator('#mob-folha');
    const titulo = (page) => page.locator('#mob-folha-titulo');
    const carregada = (page) => expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');

    async function semRolagemHorizontal(page, nome) {
        for (const [largura, altura] of [[320, 568], [375, 667], [390, 844], [430, 932]]) {
            await page.setViewportSize({ width: largura, height: altura });
            const medida = await page.evaluate(() => ({
                rolagem: document.documentElement.scrollWidth - window.innerWidth,
                fora: [...document.querySelectorAll('.mob-cabecalho, .mob-doc-titulo-linha, #mob-incluir, .mob-folha:not([hidden]) :is(.mob-botao, input, select, textarea, .mob-envio-previa)')]
                    .filter((e) => e.offsetParent !== null).filter((e) => { const r = e.getBoundingClientRect(); return r.left < -0.5 || r.right > window.innerWidth + 0.5; }).length,
            }));
            expect(medida, `${nome} ${largura}x${altura}`).toEqual({ rolagem: 0, fora: 0 });
            if (largura === 320 || largura === 390) await evidencia(page, `reg08-${nome}-${largura}`);
        }
        await page.setViewportSize({ width: 390, height: 844 });
    }

    // Empresa C: tem Categoria de Despesa propria (o Perfil B do cenario nao tem; as categorias sem perfil sao do Pessoal).
    test('selecionar NFS-e -> reconhecer -> conferir -> ajustar categoria -> confirmar; cancelar nao grava; repetido nao altera', async ({ page }, testInfo) => {
        const NFSE = nfse(testInfo.project.name);
        await entrar(page, C);
        const perfil = await perfilDaConta(page);
        await page.goto('/documentos-mobile.html');
        await carregada(page);
        const antes = (await documentos(page, perfil)).length;
        await expect(page.locator('#mob-incluir')).toBeVisible();
        await expect(page.locator('#mob-foto')).toHaveAttribute('capture', 'environment');
        await expect(page.locator('#mob-foto')).toHaveAttribute('accept', 'image/jpeg,image/png,image/webp');
        await semRolagemHorizontal(page, 'lista');

        // Escolha e pre-visualizacao; Cancelar fecha sem gravar.
        await page.click('#mob-incluir');
        await expect(titulo(page)).toHaveText('Incluir documento');
        await expect(folha(page).locator('.mob-acoes button')).toHaveText(['Fotografar', 'Selecionar arquivo']);
        await semRolagemHorizontal(page, 'escolha');
        await page.setInputFiles('#mob-arquivo', { name: 'nfse-reg08.pdf', mimeType: 'application/pdf', buffer: NFSE });
        await expect(folha(page).locator('#mob-envio-previa')).toContainText('nfse-reg08.pdf');
        await expect(folha(page).locator('#mob-envio-previa')).toContainText('PDF ·');
        await semRolagemHorizontal(page, 'previa');
        await folha(page).locator('#mob-envio-cancelar').click();
        await expect(page.locator('#mob-folha-fundo')).toBeHidden();
        expect((await documentos(page, perfil)).length).toBe(antes);

        // Reconhecer: texto do PDF, NFS-e de Goiania identificada.
        await page.click('#mob-incluir');
        await page.setInputFiles('#mob-arquivo', { name: 'nfse-reg08.pdf', mimeType: 'application/pdf', buffer: NFSE });
        await folha(page).locator('#mob-envio-continuar').click();
        await expect(titulo(page)).toHaveText('Conferir documento', { timeout: 60000 });
        await expect(folha(page).locator('#mob-envio-resumo')).toHaveText('NFS-e de Goiânia · lido por texto do PDF. Confira antes de enviar.');
        await expect(folha(page).locator('#mob-envio-data')).toHaveValue(HOJE);
        await expect(folha(page).locator('#mob-envio-prestador')).toHaveValue(LABORATORIO);
        await expect(folha(page).locator('#mob-envio-documento')).toHaveValue(CNPJ_LABORATORIO);
        await expect(folha(page).locator('#mob-envio-valor')).toHaveValue(/^130\.80?$/);
        await expect(folha(page).locator('#mob-envio-ano')).toHaveValue(ANO);
        await expect(folha(page).locator('.mob-envio-situacao.identificado')).toHaveCount(4);
        await semRolagemHorizontal(page, 'conferencia');

        // Cancelar na conferencia tambem nao grava.
        await folha(page).locator('#mob-envio-cancelar').click();
        await expect(page.locator('#mob-folha-fundo')).toBeHidden();
        expect((await documentos(page, perfil)).length).toBe(antes);

        // Ajustar categoria e confirmar: um documento pendente, com os dados conferidos.
        await page.click('#mob-incluir');
        await page.setInputFiles('#mob-arquivo', { name: 'nfse-reg08.pdf', mimeType: 'application/pdf', buffer: NFSE });
        await folha(page).locator('#mob-envio-continuar').click();
        await expect(titulo(page)).toHaveText('Conferir documento', { timeout: 60000 });
        const servicos = (await rpc(page, 'categorias_de_despesa', {})).find((x) => x.nome === 'Servicos C (ficticia)').id;
        // Sem historico do emitente (primeira vez neste banco): nenhuma categoria escolhida sozinha. Se outro motor ja enviou
        // a nota deste emitente com a categoria, o historico unanime a sugere (e continua editavel).
        const comHistorico = (await documentos(page, perfil)).some((d) => d.prestador_cpf_cnpj === CNPJ_LABORATORIO && d.categoria_id);
        await expect(folha(page).locator('#mob-envio-categoria')).toHaveValue(comHistorico ? String(servicos) : '');
        await expect(folha(page).locator('#mob-envio-categoria-nota')).toHaveText(comHistorico
            ? 'Categoria usada nos documentos anteriores deste emitente.' : 'Sem sugestão segura de categoria.');
        await folha(page).locator('#mob-envio-categoria').selectOption(String(servicos));
        const opcoes = [String(servicos)];
        await folha(page).locator('#mob-envio-observacoes').fill('conferido no celular (reg08)');
        await folha(page).locator('#mob-envio-confirmar').click();
        await expect(titulo(page)).toHaveText('Documento enviado');
        await expect(page.locator('#mob-aviso')).toHaveText('Documento enviado.');
        await evidencia(page, 'reg08-celular-enviado');
        const [enviado] = porArquivo(await documentos(page, perfil), 'nfse-reg08.pdf');
        const completo = await documento(page, perfil, enviado.id);
        expect([completo.status, completo.prestador_nome, completo.prestador_cpf_cnpj, Number(completo.valor), completo.data_documento,
            String(completo.ano_calendario), String(completo.categoria_id), completo.observacoes, completo.origem_classificacao]).toEqual(
            ['PENDENTE_REVISAO', LABORATORIO, CNPJ_LABORATORIO, 130.8, HOJE, ANO, opcoes[0], 'conferido no celular (reg08)', 'TEXTO_PDF']);
        expect(completo.texto_extraido).toContain('Prefeitura Municipal de Goiania');

        // Abrir documento: a lista e recarregada e o detalhe abre.
        await folha(page).locator('#mob-envio-abrir').click();
        await expect(titulo(page)).toHaveText('Documento');
        await expect(folha(page).locator('#mob-detalhe-documento')).toContainText(LABORATORIO);
        await page.locator('#mob-folha-fechar').click();
        await expect(page.locator('#mob-lista .mob-linha', { hasText: LABORATORIO }).first()).toBeVisible();

        // O mesmo arquivo de novo, com dados diferentes na conferencia: o documento existente fica como estava.
        await page.click('#mob-incluir');
        await page.setInputFiles('#mob-arquivo', { name: 'nfse-reg08.pdf', mimeType: 'application/pdf', buffer: NFSE });
        await folha(page).locator('#mob-envio-continuar').click();
        await expect(titulo(page)).toHaveText('Conferir documento', { timeout: 60000 });
        // agora ha historico do emitente: a categoria confirmada antes e sugerida
        await expect(folha(page).locator('#mob-envio-categoria')).toHaveValue(String(servicos));
        await expect(folha(page).locator('#mob-envio-categoria-nota')).toHaveText('Categoria usada nos documentos anteriores deste emitente.');
        await folha(page).locator('#mob-envio-prestador').fill('Nome que nao pode entrar');
        await folha(page).locator('#mob-envio-confirmar').click();
        await expect(titulo(page)).toHaveText('Documento já enviado');
        await page.locator('#mob-envio-fechar').click();
        expect(await documento(page, perfil, enviado.id)).toEqual(completo);
        expect((await documentos(page, perfil)).length).toBe(antes + 1);
    });

    test('valor ambiguo vira opcoes (nenhuma escolhida sozinha); preenchimento manual continua possivel', async ({ page }, testInfo) => {
        const RECIBO = recibo(testInfo.project.name);
        await entrar(page, B);
        const perfil = await perfilDaConta(page);
        await page.goto('/documentos-mobile.html');
        await carregada(page);
        await page.click('#mob-incluir');
        await page.setInputFiles('#mob-arquivo', { name: 'recibo-reg08.pdf', mimeType: 'application/pdf', buffer: RECIBO });
        await folha(page).locator('#mob-envio-continuar').click();
        await expect(titulo(page)).toHaveText('Conferir documento', { timeout: 60000 });
        await expect(folha(page).locator('#mob-envio-valor')).toHaveValue('');
        const chips = folha(page).locator('#mob-envio-opcoes button');
        await expect(chips).toHaveCount(3);
        await expect(chips).toHaveText([/80,00/, /45,50/, /12,00/]);
        await semRolagemHorizontal(page, 'ambiguo');
        await chips.nth(0).click();
        await expect(folha(page).locator('#mob-envio-valor')).toHaveValue('80.00');
        await folha(page).locator('#mob-envio-prestador').fill('Oficina digitada a mao (ficticia)');
        await folha(page).locator('#mob-envio-confirmar').click();
        await expect(titulo(page)).toHaveText('Documento enviado');
        await page.locator('#mob-envio-fechar').click();
        const [enviado] = porArquivo(await documentos(page, perfil), 'recibo-reg08.pdf');
        expect([enviado.prestador_nome, Number(enviado.valor), enviado.status]).toEqual(['Oficina digitada a mao (ficticia)', 80, 'PENDENTE_REVISAO']);
        await expect(page.locator('#mob-lista .mob-linha', { hasText: 'Oficina digitada a mao' }).first()).toBeVisible();
    });

    test('fotografar: imagem lida por OCR, tudo para conferir; fechar durante a conferencia nao grava', async ({ page, browser }) => {
        const png = await fotoDoCupom(browser);
        await entrar(page, B);
        const perfil = await perfilDaConta(page);
        await page.goto('/documentos-mobile.html');
        await carregada(page);
        const antes = (await documentos(page, perfil)).length;
        await page.click('#mob-incluir');
        await page.setInputFiles('#mob-foto', { name: 'foto-cupom-reg08.png', mimeType: 'image/png', buffer: png });
        await expect(folha(page).locator('#mob-envio-previa img')).toHaveAttribute('src', /^data:image\/jpeg;base64,/);  // miniatura (CSP sem blob:)
        await expect(folha(page).locator('#mob-envio-previa img')).toBeVisible();
        await folha(page).locator('#mob-envio-continuar').click();
        await expect(titulo(page)).toHaveText('Lendo o documento');
        await expect(folha(page).locator('#mob-envio-andamento')).toBeVisible();
        await expect(titulo(page)).toHaveText('Conferir documento', { timeout: 150000 });
        await expect(folha(page).locator('#mob-envio-resumo')).toHaveText('Cupom fiscal · lido por reconhecimento da imagem (OCR). Confira antes de enviar.');
        await expect(folha(page).locator('.mob-envio-situacao.identificado')).toHaveCount(0);  // OCR: nada "identificado"
        await expect(folha(page).locator('#mob-envio-prestador')).toHaveValue(/PADARIA FICTICIA E2E/i);
        await expect(folha(page).locator('#mob-envio-valor')).toHaveValue(/^25(\.00?)?$/);
        await evidencia(page, 'reg08-celular-ocr');
        await page.locator('#mob-folha-fechar').click();
        await expect(page.locator('#mob-folha-fundo')).toBeHidden();
        expect((await documentos(page, perfil)).length).toBe(antes);
    });

    test('preparo do arquivo: foto acima de 10 MB reduzida e informada; HEIC, formato invalido e PDF grande recusados', async ({ page }) => {
        await entrar(page, B);
        await page.goto('/documentos-mobile.html');
        await carregada(page);
        const r = await page.evaluate(async () => {
            const { prepararArquivo, LIMITE_BYTES } = await import('/js/leitura-ocr.js');
            // ruido aleatorio: PNG praticamente sem compressao, acima de 10 MB
            const canvas = document.createElement('canvas');
            canvas.width = 2200;
            canvas.height = 1700;
            const ctx = canvas.getContext('2d');
            const img = ctx.createImageData(canvas.width, canvas.height);
            const bloco = new Uint8Array(65536);
            for (let i = 0; i < img.data.length; i += 65536) {
                crypto.getRandomValues(bloco);
                img.data.set(bloco.subarray(0, Math.min(65536, img.data.length - i)), i);
            }
            for (let i = 3; i < img.data.length; i += 4) img.data[i] = 255;
            ctx.putImageData(img, 0, 0);
            const png = await new Promise((ok) => canvas.toBlob(ok, 'image/png'));
            const grande = await prepararArquivo(new File([png], 'foto-grande.png', { type: 'image/png' }));
            const heic = await prepararArquivo(new File([new Uint8Array([0, 0, 0, 24, 102, 116, 121, 112, 104, 101, 105, 99])], 'foto.heic', { type: 'image/heic' }));
            const texto = await prepararArquivo(new File(['texto ficticio'], 'nota.txt', { type: 'text/plain' }));
            const pdf = await prepararArquivo(new File([new Uint8Array(LIMITE_BYTES + 1)], 'grande.pdf', { type: 'application/pdf' }));
            return {
                original: png.size, limite: LIMITE_BYTES,
                grande: { tamanho: grande.arquivo.size, tipo: grande.arquivo.type, nome: grande.arquivo.name, tratamentos: grande.tratamentos, erro: grande.erro,
                          originalMantido: grande.original.size === png.size },
                heic: heic.erro, texto: texto.erro, pdf: pdf.erro,
            };
        });
        expect(r.original).toBeGreaterThan(r.limite);
        expect(r.grande.erro).toBeNull();
        expect(r.grande.tamanho).toBeLessThanOrEqual(r.limite);
        expect([r.grande.tipo, r.grande.nome, r.grande.originalMantido]).toEqual(['image/jpeg', 'foto-grande.jpg', true]);
        expect(r.grande.tratamentos).toHaveLength(1);
        expect(r.grande.tratamentos[0]).toMatch(/cópia JPEG reduzida .* \(limite de 10 MB\)\.$/);
        expect(r.heic).toBe('Este navegador não abre fotos HEIC. Use a câmera pelo botão Fotografar ou envie a foto em JPEG.');
        expect(r.texto).toBe('Formato não aceito. Envie PDF, PNG, JPEG ou WebP.');
        expect(r.pdf).toMatch(/^O PDF tem .*; o limite é 10 MB\.$/);

        // Pela tela: formato invalido mostra o erro e nada vai ao banco.
        await page.click('#mob-incluir');
        await page.setInputFiles('#mob-arquivo', { name: 'nota.txt', mimeType: 'text/plain', buffer: Buffer.from('texto ficticio') });
        await expect(folha(page).locator('.mob-mensagem')).toHaveText('Formato não aceito. Envie PDF, PNG, JPEG ou WebP.');
        await expect(folha(page).locator('#mob-envio-continuar')).toHaveCount(0);
        await folha(page).locator('#mob-envio-cancelar').click();
        await expect(page.locator('#mob-folha-fundo')).toBeHidden();
        await page.waitForLoadState('networkidle');  // nenhum pedido pendente ao fechar a pagina (o WebKit acusa pedido interrompido)
    });

    test('somente leitura: sem o botao de incluir', async ({ page }) => {
        await entrar(page, H);
        await page.goto('/documentos-mobile.html');
        await carregada(page);
        await expect(page.locator('#mob-somente-leitura')).toBeVisible();
        await expect(page.locator('#mob-incluir')).toBeHidden();
    });
});

test('CSP por caminho: wasm-unsafe-eval so nas paginas de documentos e nos arquivos do OCR; arquivos do OCR locais', async ({ page }) => {
    const csp = async (caminho) => {
        const r = await page.request.get(caminho);
        expect(r.status(), caminho).toBe(200);
        return r.headers()['content-security-policy'] || '';
    };
    const scriptSrc = (politica) => (/(?:^|;)\s*script-src([^;]*)/.exec(politica) || [null, ''])[1].trim();
    for (const caminho of ['/documentos-mobile.html', '/documentos-fiscais.html', '/vendor/tesseract-7.0.0/worker.min.js',
        '/vendor/tesseract-7.0.0/tesseract.esm.min.js']) {
        const politica = await csp(caminho);
        expect(scriptSrc(politica), caminho).toBe("'self' 'wasm-unsafe-eval'");
        expect(politica, caminho).toContain("default-src 'self'");
    }
    for (const caminho of ['/inicio.html', '/contas-mobile.html', '/index.html', '/js/leitura-ocr.js']) {
        expect(scriptSrc(await csp(caminho)), caminho).toBe("'self'");
    }
    for (const arquivo of ['tesseract-core-lstm.wasm.js', 'tesseract-core-simd-lstm.wasm.js', 'tesseract-core-relaxedsimd-lstm.wasm.js',
        'por.traineddata.gz']) {
        const r = await page.request.get(`/vendor/tesseract-7.0.0/${arquivo}`);
        expect(r.status(), arquivo).toBe(200);
    }
});
