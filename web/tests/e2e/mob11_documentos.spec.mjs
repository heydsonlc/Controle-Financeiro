// FIN-MOBILE-11 — Documentos Fiscais mobile (documentos-mobile.html), com dados FICTICIOS dos seeds de teste:
// perfil pessoal ("Perfil B", comprovantes do Imposto de Renda), Empresa ("Empresa C (ficticia)", documentos e saidas sem
// documento) e leitura ("Perfil G", leitor H). Tudo pelo servico comum a tela do desktop; cada gravacao e conferida pelas
// consultas do desktop. Grava so no banco descartavel. Ordem fixa (serial).
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

import { expect, test } from '@playwright/test';

import { gerarPdf } from '../pdf-ficticio.mjs';
import { chamarRpc } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const C = { email: process.env.CF_EMAIL_C || 'usuario.c@teste.local', senha: process.env.CF_SENHA_C };
const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const H = { email: process.env.CF_EMAIL_H || 'usuario.h@teste.local', senha: process.env.CF_SENHA_H };
const EVIDENCIAS = process.env.CF_EVIDENCIAS_DIR;
const PERFIL_G = 160;
const HOJE = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const ANO = Number(HOJE.slice(0, 4));
const MES = HOJE.slice(0, 7);
const CLINICA = 'Clinica E2E (ficticia)';
const SAIDA = 'Saida mobile 11 (ficticia)';
const SAIDA_JUSTIFICADA = 'Saida justificada mobile 11 (ficticia)';
const PDF_C = gerarPdf([[[[50, 'Documento mobile 11 (ficticio) da Empresa C']], [[50, 'Documento interno, sem palavras de classificacao.']]]]);
const DOCUMENTO_C = 'doc-mobile11-c.pdf';
const PDF_G = gerarPdf([[[[50, 'Recibo mobile 11 (ficticio) do Perfil G']], [[50, 'Valor R$ 88,00 - somente para o teste de leitura']]]]);

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

// O perfil da conta (B e C tem um so): pela mesma consulta de perfis do aplicativo.
async function perfilDaConta(page) {
    const perfis = await rpc(page, 'meus_perfis', {});
    expect(perfis.length).toBe(1);
    return perfis[0].id;
}

const carregada = (page) => expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
const folha = (page) => page.locator('#mob-folha');
const aviso = (page) => page.locator('#mob-aviso');
const linha = (page, nome) => page.locator('#mob-lista .mob-linha', { has: page.locator('.mob-linha-nome', { hasText: nome }) });
const situacao = (page, rotulo) => page.locator('#mob-situacao button', { hasText: new RegExp(`^${rotulo}$`) });
const documentos = async (page, perfil, filtros = {}) => (await rpc(page, 'ir_comprovantes_tela', { p_perfil_id: perfil, p_filtros: filtros, p_id: null })).data;

async function baixar(page, clicar) {
    const [download] = await Promise.all([page.waitForEvent('download'), clicar()]);
    const partes = [];
    for await (const parte of await download.createReadStream()) partes.push(parte);
    return { nome: download.suggestedFilename(), conteudo: Buffer.concat(partes) };
}

// Sem rolagem horizontal e nada cortado, nas larguras de celular do contrato.
async function semRolagemHorizontal(page, nome) {
    for (const [largura, altura] of [[320, 568], [375, 667], [390, 844], [430, 932]]) {
        await page.setViewportSize({ width: largura, height: altura });
        const medida = await page.evaluate(() => ({
            rolagem: document.documentElement.scrollWidth - window.innerWidth,
            fora: [...document.querySelectorAll('.mob-cabecalho, .mob-competencia, .mob-doc-segmento, .mob-resumo, .mob-linha, .mob-barra-item, .mob-folha:not([hidden]) .mob-botao')]
                .filter((e) => e.offsetParent !== null).filter((e) => { const r = e.getBoundingClientRect(); return r.left < -0.5 || r.right > window.innerWidth + 0.5; }).length,
            // o titulo do cabecalho nao encosta nos icones dos lados
            tituloLivre: (() => {
                const t = document.querySelector('.mob-titulo').getBoundingClientRect();
                return [...document.querySelectorAll('.mob-cabecalho .mob-icone-botao')].filter((b) => b.offsetParent !== null)
                    .every((b) => { const r = b.getBoundingClientRect(); return r.right <= t.left + 0.5 || r.left >= t.right - 0.5; });
            })(),
        }));
        expect(medida, `${nome} ${largura}x${altura}`).toEqual({ rolagem: 0, fora: 0, tituloLivre: true });
        if (largura === 320 || largura === 390) await evidencia(page, `mobile11-${nome}-${largura}`);
    }
    await page.setViewportSize({ width: 390, height: 844 });
}

test('perfil pessoal: lista do Imposto de Renda, situacao, busca, detalhe, baixar, revisar, validar e exportar', async ({ page }) => {
    await entrar(page, B);
    const perfil = await perfilDaConta(page);
    // Pagina principal: o atalho novo abre o modulo com a competencia.
    await page.locator('.mob-atalho[data-modulo="documentos"]').click();
    await page.waitForURL(`**/documentos-mobile.html?mes=${MES}`);
    await carregada(page);
    await expect(page.locator('.mob-titulo')).toHaveText('Documentos');
    await expect(page.locator('#mob-perfil')).toHaveText('Perfil B');
    await expect(page.locator('#mob-lista-titulo')).toHaveText('Comprovantes do Imposto de Renda');
    await expect(page.locator('#mob-competencia')).toHaveText(String(ANO));  // documentos: por ano
    await expect(page.locator('#mob-visoes')).toBeHidden();                  // saidas sem documento: so Empresa
    await expect(page.locator('#mob-somente-leitura')).toBeHidden();
    await expect(page.locator('#mob-situacao button')).toHaveText(['Todos', 'Pendentes', 'Validados']);
    const doBanco = await documentos(page, perfil, { ano: String(ANO) });
    await expect(page.locator('#mob-lista .mob-linha')).toHaveCount(doBanco.length);
    await expect(page.locator('#mob-resumo-total')).toHaveText(String(doBanco.length));
    await expect(linha(page, CLINICA)).toBeVisible();
    await semRolagemHorizontal(page, 'lista-pessoal');

    // Busca (no banco, como o desktop) e ano sem documentos.
    await page.fill('#mob-busca', 'nao-existe-mobile11');
    await expect(page.locator('#mob-lista .mob-vazio')).toContainText('Nenhum documento');
    await page.fill('#mob-busca', 'clinica');
    await expect(linha(page, CLINICA)).toBeVisible();
    await page.fill('#mob-busca', '');
    await expect(page.locator('#mob-lista .mob-linha')).toHaveCount(doBanco.length);
    await page.click('#mob-mes-anterior');
    await expect(page.locator('#mob-competencia')).toHaveText(String(ANO - 1));
    await carregada(page);
    await page.click('#mob-mes-seguinte');
    await expect(page.locator('#mob-competencia')).toHaveText(String(ANO));
    await expect(linha(page, CLINICA)).toBeVisible();

    // Detalhe: dados, arquivo, lastro e as acoes de quem gere.
    const clinica = doBanco.find((d) => d.prestador_nome === CLINICA);
    await linha(page, CLINICA).click();
    await expect(folha(page).locator('#mob-folha-titulo')).toHaveText('Documento');
    await expect(folha(page).locator('.mob-doc-arquivo')).toContainText(CLINICA);
    await expect(folha(page).locator('#mob-detalhe-documento')).toContainText('Prestador');
    await expect(folha(page).locator('#mob-detalhe-lastro')).toContainText(clinica.vinculos_count ? 'Lastro' : 'Nenhum vínculo');
    await expect(folha(page).locator('.mob-doc-acoes button')).toHaveText(['Baixar', 'Lastro', 'Vincular', 'Revisar']);
    await semRolagemHorizontal(page, 'detalhe-pessoal');
    const arquivo = await baixar(page, () => folha(page).locator('#mob-doc-baixar').click());
    expect(arquivo.nome).toBe(clinica.arquivo.nome_arquivo);
    expect(arquivo.conteudo.length).toBe(clinica.arquivo.tamanho_bytes);

    // Revisar (a mesma rota do desktop): observacao e valor; a categoria de despesa do documento fica como estava.
    await folha(page).locator('#mob-doc-revisar').click();
    await expect(folha(page).locator('#mob-folha-titulo')).toHaveText('Revisar documento');
    await expect(folha(page).locator('#mob-rev-prestador')).toHaveValue(CLINICA);
    await folha(page).locator('#mob-rev-observacoes').fill('revisado no celular (mobile 11)');
    await folha(page).locator('#mob-rev-valor').fill('321.45');
    await semRolagemHorizontal(page, 'revisao');
    await folha(page).locator('#mob-form-enviar').click();
    await expect(aviso(page)).toHaveText('Documento revisado.');
    await carregada(page);
    const revisado = (await documentos(page, perfil)).find((d) => d.id === clinica.id);
    expect([revisado.observacoes, Number(revisado.valor), revisado.prestador_nome, revisado.categoria_id]).toEqual(
        ['revisado no celular (mobile 11)', 321.45, CLINICA, clinica.categoria_id]);
    await expect(linha(page, CLINICA).locator('.mob-linha-valor')).toHaveText(/R\$\s321,45/);

    // Validar e a situacao "Validados".
    if (revisado.status !== 'VALIDADO') {
        await linha(page, CLINICA).click();
        await folha(page).locator('#mob-doc-revisar').click();
        await folha(page).locator('#mob-rev-validar').click();
        await expect(aviso(page)).toHaveText('Documento validado.');
        await carregada(page);
    }
    expect((await documentos(page, perfil)).find((d) => d.id === clinica.id).status).toBe('VALIDADO');
    await situacao(page, 'Validados').click();
    await carregada(page);
    await expect(linha(page, CLINICA).locator('.mob-doc-selo')).toHaveText('Validado');
    const validados = (await documentos(page, perfil, { ano: String(ANO), status: 'VALIDADO' })).length;
    await expect(page.locator('#mob-lista .mob-linha')).toHaveCount(validados);

    // Exportar: Excel e PDF do REG-03, com a situacao da tela; sem ZIP no perfil pessoal.
    await page.click('#mob-exportar');
    await expect(folha(page).locator('.mob-doc-exportar button')).toHaveText(['Excel', 'PDF']);
    const excel = await baixar(page, () => folha(page).locator('#mob-exportar-excel').click());
    expect(excel.nome).toBe(`IRPF_${ANO}_Perfil_B.xlsx`);
    expect(excel.conteudo.includes(Buffer.from(CLINICA))).toBe(true);
    const pdf = await baixar(page, () => folha(page).locator('#mob-exportar-pdf').click());
    expect(pdf.nome).toBe(`IRPF_${ANO}_Perfil_B.pdf`);
    expect(pdf.conteudo.toString('latin1')).toContain(`Total de comprovantes: ${validados}`);
    await folha(page).locator('#mob-folha-fechar').click();

    // Voltar: pagina principal, com a competencia.
    await page.click('#mob-voltar');
    await page.waitForURL(`**/inicio.html?mes=${MES}`);
});

test('Empresa: documentos, vinculo e lastro, saidas sem documento, situacao manual e exportacoes', async ({ page }) => {
    await entrar(page, C);
    const perfil = await perfilDaConta(page);
    // Saidas ficticias do mes (contas a pagar criadas aqui, pela funcao do desktop).
    const categoria = (await rpc(page, 'categorias_de_despesa', {})).find((c) => c.nome === 'Servicos C (ficticia)').id;
    for (const [nome, valor] of [[SAIDA, '150.00'], [SAIDA_JUSTIFICADA, '75.50']]) {
        await rpc(page, 'criar_despesa', { p_perfil_id: perfil, p_chave: crypto.randomUUID(),
            p_dados: { nome, valor, categoria_id: categoria, data_vencimento: `${MES}-10`, recorrente: false } });
    }
    // Um documento proprio deste teste, com arquivo e sem vinculo (outros testes deixam documentos e vinculos na Empresa C).
    const enviado = await rpc(page, 'enviar_comprovante', { p_perfil_id: perfil, p_conteudo: PDF_C.toString('base64'), p_chave: crypto.randomUUID(),
        p_dados: { nome_arquivo: DOCUMENTO_C, mime_type: 'application/pdf', ano_calendario: ANO, texto_extraido: null } });
    await page.goto(`/documentos-mobile.html?mes=${MES}`);
    await carregada(page);
    await expect(page.locator('#mob-lista-titulo')).toHaveText('Documentos da Empresa');
    await expect(page.locator('#mob-visoes button')).toHaveText(['Documentos', 'Saídas sem documento']);
    const doBanco = await documentos(page, perfil, { ano: String(ANO) });
    await expect(page.locator('#mob-lista .mob-linha')).toHaveCount(doBanco.length);
    const documento = doBanco.find((d) => d.id === enviado.comprovante_id);
    const nomeDoDocumento = DOCUMENTO_C;
    await semRolagemHorizontal(page, 'lista-empresa');

    // Saidas sem documento: resumo, lista do mes e detalhe.
    await page.locator('#mob-visoes button[data-visao="saidas"]').click();
    await carregada(page);
    await expect(page.locator('#mob-lista-titulo')).toHaveText('Saídas sem documento');
    await expect(page.locator('#mob-situacao button')).toHaveText(['Pendentes', 'Sem lastro', 'Todas']);
    const resumoAntes = await rpc(page, 'lastro_saidas_tela', { p_perfil_id: perfil, p_filtros: { ano: String(ANO), mes: String(Number(MES.slice(5))) }, p_resumo: true });
    await expect(page.locator('#mob-resumo-pendentes')).toHaveText(String(resumoAntes.pendencias_total));
    await expect(page.locator('#mob-resumo-com-documento')).toHaveText(String(resumoAntes.saidas_com_documento));
    await expect(page.locator('#mob-resumo-sem-documento')).toHaveText(String(resumoAntes.quantidade_sem_documento));
    await expect(linha(page, SAIDA).locator('.mob-doc-selo')).toHaveText('Sem lastro');
    await semRolagemHorizontal(page, 'saidas');

    // Situacao manual (justificativa): a saida deixa de ser "sem lastro".
    await linha(page, SAIDA_JUSTIFICADA).click();
    await expect(folha(page).locator('#mob-detalhe-saida')).toContainText('R$');
    await folha(page).locator('#mob-saida-situacao').click();
    await folha(page).locator('#mob-saida-situacao-valor').selectOption('NAO_APLICAVEL');
    await folha(page).locator('#mob-saida-situacao-observacoes').fill('sem nota: taxa interna (ficticia)');
    await folha(page).locator('#mob-form-enviar').click();
    await expect(aviso(page)).toHaveText('Situação da saída registrada.');
    await carregada(page);
    await expect(linha(page, SAIDA_JUSTIFICADA)).toHaveCount(0);  // "Pendentes" nao mostra a justificada
    await situacao(page, 'Todas').click();
    await carregada(page);
    await expect(linha(page, SAIDA_JUSTIFICADA).locator('.mob-doc-selo')).toHaveText('Justificado');

    // Vincular um documento a saida: ela passa a ter documento (sai da lista de pendencias).
    await linha(page, SAIDA).click();
    await folha(page).locator('#mob-saida-vincular').click();
    await expect(folha(page).locator('#mob-saida-documento')).toBeEnabled();
    await folha(page).locator('#mob-saida-documento').selectOption(String(documento.id));
    await folha(page).locator('#mob-form-enviar').click();
    await expect(aviso(page)).toHaveText('Saída vinculada ao documento.');
    await carregada(page);
    await expect(linha(page, SAIDA)).toHaveCount(0);
    await expect(page.locator('#mob-resumo-com-documento')).toHaveText(String(resumoAntes.saidas_com_documento + 1));

    // Exportacoes das saidas (REG-03).
    await page.click('#mob-exportar');
    await expect(folha(page).locator('.mob-doc-exportar button')).toHaveText(['Excel', 'PDF']);
    const saidasPdf = await baixar(page, () => folha(page).locator('#mob-exportar-pdf').click());
    expect(saidasPdf.nome).toMatch(new RegExp(`^Saidas_sem_documento_Empresa_C.*_${ANO}_${MES.slice(5)}\\.pdf$`));
    expect(saidasPdf.conteudo.toString('latin1')).toContain('Relatorio de Saidas sem Documento');
    await folha(page).locator('#mob-folha-fechar').click();

    // Documentos: o lastro do documento mostra o vinculo; vincular outro (sem entidade) e desvincular (dois toques).
    await page.locator('#mob-visoes button[data-visao="documentos"]').click();
    await carregada(page);
    await linha(page, nomeDoDocumento).first().click();
    const lastro = folha(page).locator('#mob-detalhe-lastro');
    await expect(lastro.locator('.mob-doc-vinculos li')).toHaveCount(1);
    await expect(lastro).toContainText(SAIDA);
    await expect(folha(page).locator('.mob-doc-acoes button')).toHaveText(['Baixar', 'Lastro', 'Vincular', 'Revisar']);
    await folha(page).locator('#mob-doc-vincular').click();
    await folha(page).locator('#mob-vinc-tipo').selectOption('OUTRO');
    await expect(folha(page).locator('#mob-vinc-entidade')).toBeDisabled();
    await folha(page).locator('#mob-vinc-observacoes').fill('vinculo sem entidade (mobile 11)');
    await semRolagemHorizontal(page, 'vinculo');
    await folha(page).locator('#mob-form-enviar').click();
    await expect(aviso(page)).toHaveText('Documento vinculado.');
    await carregada(page);
    let vinculos = await rpc(page, 'vinculos_documento_tela', { p_perfil_id: perfil, p_comprovante_id: documento.id });
    expect(vinculos.map((v) => v.tipo_entidade).sort()).toEqual(['CONTA', 'OUTRO']);
    await linha(page, nomeDoDocumento).first().click();
    await expect(lastro.locator('.mob-doc-vinculos li')).toHaveCount(2);
    const desvincular = lastro.locator(`.mob-doc-desvincular[data-vinculo="${vinculos.find((v) => v.tipo_entidade === 'OUTRO').id}"]`);
    await desvincular.click();
    await expect(desvincular).toHaveText('Confirmar');  // o primeiro toque so pede a confirmacao
    expect((await rpc(page, 'vinculos_documento_tela', { p_perfil_id: perfil, p_comprovante_id: documento.id })).length).toBe(2);
    await desvincular.click();
    await expect(lastro.locator('.mob-doc-vinculos li')).toHaveCount(1);
    vinculos = await rpc(page, 'vinculos_documento_tela', { p_perfil_id: perfil, p_comprovante_id: documento.id });
    expect(vinculos.map((v) => v.tipo_entidade)).toEqual(['CONTA']);
    await folha(page).locator('#mob-folha-fechar').click();

    // Exportacoes dos documentos: Excel, PDF e o pacote ZIP da Empresa (REG-04).
    await page.click('#mob-exportar');
    await expect(folha(page).locator('.mob-doc-exportar button')).toHaveText(['Excel', 'PDF', 'ZIP']);
    const excel = await baixar(page, () => folha(page).locator('#mob-exportar-excel').click());
    expect(excel.nome).toMatch(new RegExp(`^Documentos_Fiscais_${ANO}_Empresa_C.*\\.xlsx$`));
    const zip = await baixar(page, () => folha(page).locator('#mob-exportar-zip').click());
    expect(zip.nome).toBe(`Documentos_Empresa_${ANO}_Contador.zip`);
    expect(zip.conteudo.includes(Buffer.from('indice_documentos.xlsx'))).toBe(true);
    await semRolagemHorizontal(page, 'exportar');
    await folha(page).locator('#mob-folha-fechar').click();

    // Filtros: tipo documental (vale a classificacao gravada) e a marca de filtro ativo.
    await page.click('#mob-filtros');
    await folha(page).locator('#mob-filtro-tipo').selectOption('DOCUMENTO_SOCIETARIO');
    await folha(page).locator('#mob-filtros-aplicar').click();
    await carregada(page);
    await expect(page.locator('#mob-filtro-marca')).toBeVisible();
    await expect(page.locator('#mob-nota')).toContainText('classificação gravada');
    const societarios = await documentos(page, perfil, { ano: String(ANO), tipo_documental: 'DOCUMENTO_SOCIETARIO' });
    await expect(page.locator('#mob-lista .mob-linha')).toHaveCount(societarios.length);
    await page.click('#mob-filtros');
    await folha(page).locator('#mob-filtros-limpar').click();
    await carregada(page);
    await expect(page.locator('#mob-filtro-marca')).toBeHidden();

    // Limpeza: o vinculo criado sai (historico preservado) e a saida volta a ficar sem documento.
    await rpc(page, 'remover_vinculo_documento', { p_perfil_id: perfil, p_comprovante_id: documento.id, p_vinculo_id: vinculos[0].id });
    // O documento do teste continua guardado (com historico de vinculo, a exclusao e recusada, como no desktop): outros testes
    // da Empresa C contam os documentos pela consulta, nao por numero fixo.
});

test('somente leitura: consulta, baixa e exporta; sem revisar, vincular ou registrar situacao', async ({ page, browser }) => {
    // O titular (G) guarda um documento ficticio no Perfil G; o leitor (H) so consulta.
    const contexto = await browser.newContext();
    const paginaG = await contexto.newPage();
    await entrar(paginaG, G);
    const enviado = await rpc(paginaG, 'enviar_comprovante', { p_perfil_id: PERFIL_G, p_conteudo: PDF_G.toString('base64'), p_chave: crypto.randomUUID(),
        p_dados: { nome_arquivo: 'recibo-mobile11-g.pdf', mime_type: 'application/pdf', ano_calendario: ANO, texto_extraido: null } });
    await contexto.close();

    await entrar(page, H);
    await page.locator('.mob-atalho[data-modulo="documentos"]').click();
    await page.waitForURL('**/documentos-mobile.html**');
    await carregada(page);
    await expect(page.locator('#mob-somente-leitura')).toBeVisible();
    await expect(page.locator('#mob-visoes')).toBeHidden();
    const antes = await documentos(page, PERFIL_G);
    await linha(page, 'recibo-mobile11-g.pdf').click();
    await expect(folha(page).locator('.mob-doc-acoes button')).toHaveText(['Baixar', 'Lastro']);
    await expect(folha(page).locator('#mob-doc-revisar, #mob-doc-vincular, .mob-doc-desvincular')).toHaveCount(0);
    const arquivo = await baixar(page, () => folha(page).locator('#mob-doc-baixar').click());
    expect(Buffer.compare(arquivo.conteudo, PDF_G)).toBe(0);  // os bytes guardados, sem alteracao
    await folha(page).locator('#mob-folha-fechar').click();
    await page.click('#mob-exportar');
    const pdf = await baixar(page, () => folha(page).locator('#mob-exportar-pdf').click());
    expect(pdf.nome).toMatch(new RegExp(`^IRPF_${ANO}_Perfil_G.*\\.pdf$`));
    await folha(page).locator('#mob-folha-fechar').click();
    // O banco tambem recusa a escrita do leitor, e nada mudou.
    const recusa = await chamarRpc(page, 'atualizar_comprovante', { p_perfil_id: PERFIL_G, p_id: enviado.comprovante_id, p_dados: { observacoes: 'x' } });
    expect(recusa.status).toBeGreaterThanOrEqual(400);
    expect(await documentos(page, PERFIL_G)).toEqual(antes);
});

test('sem sessao: a pagina volta ao login', async ({ page }) => {
    await page.goto('/documentos-mobile.html');
    await page.waitForURL(/index\.html|\/\?next=|\/$/);
    await expect(page.locator('#email')).toBeVisible();
});
