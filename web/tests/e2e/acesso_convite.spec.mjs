// FIN-MULTIUSUARIO-ACESSO-01 — entrada por convite, primeiro acesso, recuperacao de senha, suspensao e administracao da
// plataforma, pelas telas. Usuarios FICTICIOS criados no auth simulado deste ambiente; NENHUM e-mail e enviado: o "link do
// e-mail" vem do gancho de teste /__e2e__/link, no mesmo formato do Supabase Auth. O usuario A e o administrador ficticio.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { chamarRpc } from './despesas.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const EVIDENCIAS = process.env.CF_ACESSO_EVIDENCIAS || '';  // capturas para a homologacao (opcional; dados ficticios)
const NOVA = { email: 'convidada.e2e@teste.local', senha: 'Senha-nova-E2E-2027', outra: 'Outra-senha-E2E-2028' };
const SEM_CONVITE = { email: 'semconvite.e2e@teste.local', senha: 'Senha-semconvite-2027' };
const VENCIDA = { email: 'vencida.e2e@teste.local', senha: 'Senha-vencida-2027' };
const REVOGADA = 'revogada.e2e@teste.local';
const SEM_ACESSO = 'Esta conta não tem acesso liberado ao aplicativo. Fale com o administrador.';

test.use({ viewport: { width: 1366, height: 900 } });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to|Ponte CSP/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS').toEqual([]);
});

async function evidencia(page, nome) {
    if (!EVIDENCIAS) return;
    mkdirSync(EVIDENCIAS, { recursive: true });
    await page.screenshot({ path: path.join(EVIDENCIAS, `${nome}.png`) });
}

async function admin(request, pedido) {
    const r = await request.post('/__e2e__/admin', { data: pedido });
    expect(r.ok(), JSON.stringify(pedido)).toBe(true);
    return r.json();
}

async function link(request, email, tipo, extra = {}) {
    const r = await request.post('/__e2e__/link', { data: { email, tipo, ...extra } });
    expect(r.ok()).toBe(true);
    return r.json();
}

async function entrar(page, conta, destino = '**/contas.html') {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL(destino);
}

async function abrirAdministracao(page) {
    await entrar(page, A);
    await expect(page.locator('#app-nav-plataforma')).toBeVisible();
    await page.click('#app-nav-plataforma a');
    await page.waitForURL('**/administracao.html');
    await expect(page.locator('#adm-pagina')).toBeVisible();
}

const convite = (page, email) => page.locator(`#adm-lista-convites .adm-item[data-convite="${email}"]`);
const usuario = (page, email) => page.locator(`#adm-lista-usuarios .adm-item[data-usuario="${email}"]`);

async function convidar(page, email, observacao = '') {
    await page.fill('#adm-convite-email', email);
    await page.fill('#adm-convite-observacao', observacao);
    await page.click('#adm-convite-enviar');
    await expect(page.locator('#adm-convite-enviar')).toBeEnabled();  // a operacao terminou (o formulario e limpo no sucesso)
}

// Cada link do e-mail e uma visita nova (trocar so o fragmento do endereco nao recarregaria a pagina).
async function abrirLink(page, fragmento) {
    await page.goto('about:blank');
    await page.goto(`/definir-senha.html#${fragmento}`);
}

async function definirSenha(page, senha, confirma = senha) {
    await page.fill('#ds-senha', senha);
    await page.fill('#ds-confirma', confirma);
    await page.click('#ds-enviar');
}

test('administrador registra convites; usuario comum nao ve a administracao nem consegue convidar', async ({ page, request }) => {
    const antes = await admin(request, { acao: 'retrato_acesso' });
    await abrirAdministracao(page);
    await expect(page.locator('#adm-lista-convites .adm-vazio')).toBeVisible();
    await convidar(page, 'nao-e-email');
    await expect(page.locator('#adm-alerta')).toHaveAttribute('data-tipo', 'erro');
    await convidar(page, `  ${NOVA.email.toUpperCase()} `, 'convite do teste');
    await expect(page.locator('#adm-alerta')).toContainText(`Convite registrado para ${NOVA.email}`);
    await expect(convite(page, NOVA.email).locator('.adm-selo')).toHaveText('Pendente');
    await expect(convite(page, NOVA.email)).toContainText('convite do teste');
    await convidar(page, NOVA.email);
    await expect(page.locator('#adm-alerta')).toHaveText('Já existe um convite pendente para este e-mail.');
    await convidar(page, B.email);
    await expect(page.locator('#adm-alerta')).toHaveText('Este e-mail já tem conta no aplicativo.');
    await convidar(page, VENCIDA.email);
    await convidar(page, REVOGADA);
    await expect(convite(page, REVOGADA).locator('.adm-selo')).toHaveText('Pendente');
    page.once('dialog', (d) => d.accept());
    await convite(page, REVOGADA).getByRole('button', { name: 'Revogar' }).click();
    await expect(convite(page, REVOGADA).locator('.adm-selo')).toHaveText('Revogado');
    await expect(convite(page, REVOGADA).getByRole('button')).toHaveCount(0);
    await evidencia(page, 'acesso-1-convites');
    const depois = await admin(request, { acao: 'retrato_acesso' });
    expect(depois).toEqual({ ...antes, convites: antes.convites + 3 });  // nenhum usuario, perfil ou dado criado por convidar

    // usuario comum: sem atalho no menu; a pagina direta mostra o aviso; o banco recusa
    await page.evaluate(() => sessionStorage.clear());
    await page.click('#app-logout-button');
    await page.waitForURL('**/index.html');
    await entrar(page, B);
    await expect(page.locator('#app-nav-plataforma')).toBeHidden();
    await page.goto('/administracao.html');
    await expect(page.locator('#adm-restrito')).toBeVisible();
    await expect(page.locator('#adm-pagina')).toBeHidden();
    for (const [funcao, parametros] of [['convites_tela', {}], ['usuarios_tela', {}], ['criar_convite', { p_dados: { email: 'amigo@teste.local' } }],
        ['suspender_usuario', { p_user_id: '00000000-0000-4000-8000-000000000000', p_motivo: 'x' }], ['auditoria_acesso_tela', { p_limite: 10 }]]) {
        const r = await chamarRpc(page, funcao, parametros);
        expect([r.status, r.corpo.code], funcao).toEqual([403, '42501']);
    }
    expect(await admin(request, { acao: 'retrato_acesso' })).toEqual(depois);
});

test('convidada: link do convite, senha, primeiro acesso e ativacao numa operacao; entra com a senha nova', async ({ page, request }) => {
    const antes = await admin(request, { acao: 'retrato_acesso' });
    // antes de definir a senha, nao ha como entrar
    await page.goto('/index.html');
    await page.fill('#email', NOVA.email);
    await page.fill('#senha', NOVA.senha);
    await page.click('#login-enviar');
    await expect(page.locator('#login-erro')).toHaveText('E-mail ou senha inválidos.');

    const { fragmento } = await link(request, NOVA.email, 'invite');
    await abrirLink(page, fragmento);
    await expect(page.locator('#ds-subtitulo')).toHaveText('Crie a senha da sua conta');
    expect(page.url()).not.toContain('access_token');  // o link sai do endereco
    await definirSenha(page, 'curta1');
    await expect(page.locator('#ds-erro')).toContainText('pelo menos 10 caracteres');
    await definirSenha(page, 'somenteletrasaqui');
    await expect(page.locator('#ds-erro')).toContainText('letras e números');
    await definirSenha(page, NOVA.senha, `${NOVA.senha}x`);
    await expect(page.locator('#ds-erro')).toHaveText('As duas senhas não são iguais.');
    await evidencia(page, 'acesso-2-definir-senha');
    await definirSenha(page, NOVA.senha);
    await page.waitForURL('**/primeiro-acesso.html');
    await expect(page.locator('#pa-form')).toBeVisible();
    await expect(page.locator('#pa-email')).toContainText(NOVA.email);
    await evidencia(page, 'acesso-3-primeiro-acesso');
    // ainda nao ativada: nada do aplicativo responde, e as paginas voltam para o primeiro acesso
    expect((await chamarRpc(page, 'meus_perfis', {})).corpo).toEqual([]);
    expect((await chamarRpc(page, 'criar_perfil', { p_dados: { nome: 'Atalho' } })).corpo.code).toBe('42501');
    expect(await admin(request, { acao: 'retrato_acesso' })).toEqual(antes);
    await page.fill('#pa-nome', '   ');
    await page.click('#pa-enviar');
    await expect(page.locator('#pa-erro')).toHaveText('Informe o nome do perfil.');
    await page.fill('#pa-nome', 'Minhas Finanças');
    await page.click('#pa-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-name')).toHaveText('Minhas Finanças');
    await expect(page.locator('#app-nav-plataforma')).toBeHidden();
    const depois = await admin(request, { acao: 'retrato_acesso' });
    // so a conta da plataforma e o perfil; nenhuma conta bancaria nem lancamento ficticio
    expect(depois).toEqual({ ...antes, contas_da_plataforma: antes.contas_da_plataforma + 1, perfis: antes.perfis + 1 });
    const perfis = (await chamarRpc(page, 'meus_perfis', {})).corpo;
    expect(perfis.map((p) => [p.nome, p.padrao, p.papel])).toEqual([['Minhas Finanças', true, 'TITULAR']]);
    // repetir a ativacao nao cria nada
    expect((await chamarRpc(page, 'ativar_minha_conta', { p_dados: { nome: 'De novo' } })).corpo).toMatchObject({ ativada: true, repetida: true, perfis: 1 });
    expect(await admin(request, { acao: 'retrato_acesso' })).toEqual(depois);
    // recebe o catalogo padrao; nao alcanca o perfil de mais ninguem
    await page.goto('/categorias.html');
    await expect(page.locator('#categorias-lista .despesa-list-item').first()).toBeVisible();
    await expect(page.locator('#categorias-lista .cf-selo-catalogo', { hasText: 'Minha' })).toHaveCount(0);
    for (const alheio of [1, 2, 101, 110, 120]) {
        const r = await chamarRpc(page, 'categorias_tela', { p_perfil_id: alheio, p_ativo: null });
        if (!perfis.some((p) => p.id === alheio)) expect(r.corpo.code, `perfil ${alheio}`).toBe('42501');
    }
    await page.click('#app-logout-button');
    await page.waitForURL('**/index.html');
    await entrar(page, NOVA);
    await expect(page.locator('#perfil-financeiro-name')).toHaveText('Minhas Finanças');
    // o mesmo link nao serve de novo como atalho de troca de senha sem nova visita valida: sem link, a pagina nao troca nada
    await page.goto('/definir-senha.html');
    await expect(page.locator('#ds-subtitulo')).toHaveText('Link inválido');
    await expect(page.locator('#ds-form')).toBeHidden();
});

test('link invalido ou expirado e conta sem convite: mensagens claras, nada criado', async ({ page, request }) => {
    const antes = await admin(request, { acao: 'retrato_acesso' });
    const vencido = await link(request, NOVA.email, 'recovery', { expirado: true });
    await abrirLink(page, vencido.fragmento);
    await expect(page.locator('#ds-subtitulo')).toHaveText('Link inválido');
    await expect(page.locator('#ds-aviso')).toContainText('não é mais válido');
    await expect(page.locator('#ds-links')).toBeVisible();
    await abrirLink(page, 'access_token=abc.def.ghi&refresh_token=x&type=recovery');
    await expect(page.locator('#ds-subtitulo')).toHaveText('Link inválido');

    // login criado no Supabase sem convite registrado no aplicativo: define a senha, mas nao ativa nem usa nada
    const { fragmento } = await link(request, SEM_CONVITE.email, 'invite');
    await abrirLink(page, fragmento);
    await definirSenha(page, SEM_CONVITE.senha);
    await page.waitForURL('**/primeiro-acesso.html');
    await expect(page.locator('#pa-subtitulo')).toHaveText('Acesso não liberado');
    await expect(page.locator('#pa-aviso')).toHaveText(SEM_ACESSO);
    await expect(page.locator('#pa-form')).toBeHidden();
    await evidencia(page, 'acesso-4-sem-acesso');
    const r = await chamarRpc(page, 'ativar_minha_conta', { p_dados: { nome: 'Forcado' } });
    expect([r.status, r.corpo.code]).toEqual([403, '42501']);
    for (const pagina of ['contas.html', 'dashboard.html', 'categorias.html', 'configuracoes.html', 'inicio.html']) {
        await page.goto(`/${pagina}`);
        await page.waitForURL('**/primeiro-acesso.html');
    }
    await page.click('#pa-sair');
    await page.waitForURL('**/index.html');
    expect(await admin(request, { acao: 'retrato_acesso' })).toEqual(antes);
});

test('convite expirado nao ativa; o reenvio registrado pelo administrador renova a validade', async ({ browser, page, request }) => {
    await admin(request, { acao: 'expirar_convite', email: VENCIDA.email });
    const { fragmento } = await link(request, VENCIDA.email, 'invite');
    await abrirLink(page, fragmento);
    await definirSenha(page, VENCIDA.senha);
    await page.waitForURL('**/primeiro-acesso.html');
    await expect(page.locator('#pa-aviso')).toHaveText('O seu convite expirou. Peça um novo convite ao administrador.');
    await expect(page.locator('#pa-form')).toBeHidden();

    const contexto = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    const adm = await contexto.newPage();
    await abrirAdministracao(adm);
    await expect(convite(adm, VENCIDA.email).locator('.adm-selo')).toHaveText('Expirado');
    await convite(adm, VENCIDA.email).getByRole('button', { name: 'Registrar reenvio' }).click();
    await expect(adm.locator('#adm-alerta')).toHaveText('Aguarde 10 minutos entre um envio e outro.');
    await admin(request, { acao: 'convite_antigo', email: VENCIDA.email });
    await convite(adm, VENCIDA.email).getByRole('button', { name: 'Registrar reenvio' }).click();
    await expect(convite(adm, VENCIDA.email).locator('.adm-selo')).toHaveText('Pendente');
    await expect(convite(adm, VENCIDA.email)).toContainText('2 envios');
    await contexto.close();

    await page.reload();
    await expect(page.locator('#pa-form')).toBeVisible();
    await page.fill('#pa-nome', 'Casa');
    await page.click('#pa-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-name')).toHaveText('Casa');
});

test('recuperacao de senha: resposta igual com ou sem conta; a senha nova vale e a antiga deixa de valer', async ({ page, request }) => {
    await page.goto('/index.html');
    await page.click('text=Esqueci minha senha');
    await page.waitForURL('**/recuperar-senha.html');
    const respostas = [];
    for (const email of ['ninguem.e2e@teste.local', NOVA.email]) {
        await page.goto('/recuperar-senha.html');
        await page.fill('#rs-email', email);
        await page.click('#rs-enviar');
        await expect(page.locator('#rs-aviso')).toBeVisible();
        respostas.push(await page.locator('#rs-aviso').textContent());
    }
    expect(respostas[0]).toBe(respostas[1]);  // nao revela se a conta existe
    await evidencia(page, 'acesso-5-recuperar-senha');
    const inexistente = await link(request, 'ninguem.e2e@teste.local', 'recovery');
    expect(inexistente.fragmento).toBeNull();
    expect(inexistente.pedidos_de_recuperacao).toEqual(expect.arrayContaining(['ninguem.e2e@teste.local', NOVA.email]));

    const { fragmento } = await link(request, NOVA.email, 'recovery');
    await abrirLink(page, fragmento);
    await expect(page.locator('#ds-subtitulo')).toHaveText('Crie uma nova senha');
    await definirSenha(page, NOVA.outra);
    await page.waitForURL('**/contas.html');  // conta ja ativa: o primeiro acesso segue direto para o aplicativo
    await page.click('#app-logout-button');
    await page.waitForURL('**/index.html');
    await page.fill('#email', NOVA.email);
    await page.fill('#senha', NOVA.senha);
    await page.click('#login-enviar');
    await expect(page.locator('#login-erro')).toHaveText('E-mail ou senha inválidos.');
    await entrar(page, { email: NOVA.email, senha: NOVA.outra });
});

test('suspensao: a conta deixa de receber qualquer resposta, os dados ficam, e a reativacao devolve o acesso', async ({ browser, page, request }) => {
    await entrar(page, { email: NOVA.email, senha: NOVA.outra });
    const perfil = (await chamarRpc(page, 'meus_perfis', {})).corpo[0].id;
    const antes = await admin(request, { acao: 'retrato_acesso' });

    const contexto = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    const adm = await contexto.newPage();
    await abrirAdministracao(adm);
    await adm.click('.adm-aba[data-aba="usuarios"]');
    await expect(usuario(adm, NOVA.email).locator('.adm-selo')).toHaveText('Ativa');
    await expect(usuario(adm, A.email).getByRole('button')).toHaveCount(0);  // o administrador nao suspende a propria conta
    await expect(usuario(adm, A.email)).toContainText('administrador');
    // a lista so informa situacao e quantidade de perfis
    await expect(usuario(adm, NOVA.email)).toContainText('1 perfil');
    adm.once('dialog', (d) => d.accept('teste de suspensao E2E'));
    await usuario(adm, NOVA.email).getByRole('button', { name: 'Suspender' }).click();
    await expect(usuario(adm, NOVA.email).locator('.adm-selo')).toHaveText('Suspensa');
    await expect(usuario(adm, NOVA.email)).toContainText('teste de suspensao E2E');
    await evidencia(adm, 'acesso-6-usuarios');

    // a sessao aberta da conta suspensa nao serve para mais nada
    for (const [funcao, parametros] of [['categorias_tela', { p_perfil_id: perfil, p_ativo: null }], ['criar_perfil', { p_dados: { nome: 'Outro' } }],
        ['contas_bancarias_do_perfil', { p_perfil_id: perfil }], ['ativar_minha_conta', { p_dados: { nome: 'Volta' } }]]) {
        expect((await chamarRpc(page, funcao, parametros)).corpo.code, funcao).toBe('42501');
    }
    expect((await chamarRpc(page, 'meus_perfis', {})).corpo).toEqual([]);
    await page.goto('/contas.html');
    await page.waitForURL('**/primeiro-acesso.html');
    await expect(page.locator('#pa-aviso')).toHaveText(SEM_ACESSO);  // mesma mensagem de quem nunca teve acesso
    expect(await admin(request, { acao: 'retrato_acesso' })).toEqual(antes);  // nada apagado

    await usuario(adm, NOVA.email).getByRole('button', { name: 'Reativar' }).click();
    await expect(usuario(adm, NOVA.email).locator('.adm-selo')).toHaveText('Ativa');
    await adm.click('.adm-aba[data-aba="auditoria"]');
    await expect(adm.locator('#adm-lista-auditoria .adm-item-titulo').first()).toHaveText('Conta reativada');  // a lista carregou
    const auditoria = await adm.locator('#adm-lista-auditoria .adm-item-titulo').allTextContents();
    expect(auditoria.slice(0, 2)).toEqual(['Conta reativada', 'Conta suspensa']);
    expect(auditoria).toEqual(expect.arrayContaining(['Convite registrado', 'Convite revogado', 'Reenvio registrado', 'Conta ativada']));
    await evidencia(adm, 'acesso-7-auditoria');
    await contexto.close();

    await page.reload();
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-name')).toHaveText('Minhas Finanças');
});
