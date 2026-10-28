// Testes do build: o navegador so pode receber valores publicos do projeto certo.
import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { construir, montarPagina, validarChavePublica, validarUrl, verificarDist } from '../../scripts/build.mjs';

const URL_OK = 'https://abcdefghijklmnopqrst.supabase.co';
const jwt = (payload) => [
    Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url'),
    Buffer.from(JSON.stringify(payload)).toString('base64url'),
    'assinatura',
].join('.');

test('aceita a chave publicavel e a chave anon legada', () => {
    assert.equal(validarChavePublica('sb_publishable_abc123'), 'sb_publishable_abc123');
    assert.ok(validarChavePublica(jwt({ role: 'anon' })));
});

test('recusa chave secreta e JWT privilegiado', () => {
    assert.throws(() => validarChavePublica('sb_secret_abc123'), /secreta/);
    assert.throws(() => validarChavePublica(jwt({ role: 'service_role' })), /apenas "anon"/);
    assert.throws(() => validarChavePublica(jwt({ role: 'authenticated' })), /apenas "anon"/);
    assert.throws(() => validarChavePublica(''), /ausente/);
    assert.throws(() => validarChavePublica('qualquer-coisa'), /nao reconhecido/);
});

test('recusa o projeto Supabase da Calculadora Judicial', () => {
    assert.throws(() => validarUrl('https://dshqjhyymtpxpxuntzbz.supabase.co'), /Calculadora Judicial/);
});

test('exige https em supabase.co; local so com --local', () => {
    assert.equal(validarUrl(URL_OK), URL_OK);
    assert.throws(() => validarUrl('http://abcdefghijklmnopqrst.supabase.co'), /https/);
    assert.throws(() => validarUrl('https://exemplo.com'), /supabase\.co/);
    assert.throws(() => validarUrl('http://127.0.0.1:54321'), /--local/);
    assert.equal(validarUrl('http://127.0.0.1:54321', { permitirLocal: true }), 'http://127.0.0.1:54321');
});

test('dist gerado contem so valores publicos e CSP restrita', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-build-'));
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const config = await readFile(path.join(destino, 'config.js'), 'utf8');
        assert.match(config, /"supabaseUrl":"https:\/\/abcdefghijklmnopqrst\.supabase\.co"/);
        assert.match(config, /"supabasePublishableKey":"sb_publishable_abc123"/);
        assert.doesNotMatch(config, /secret|service|password|senha/i);

        const headers = await readFile(path.join(destino, '_headers'), 'utf8');
        assert.match(headers, /script-src 'self';/);
        assert.match(headers, new RegExp(`connect-src 'self' ${URL_OK.replace(/\./g, '\\.')}`));
        assert.match(headers, /frame-ancestors 'none'/);

        const arquivos = await readdir(destino, { recursive: true });
        assert.ok(arquivos.some((a) => a.replaceAll('\\', '/') === 'css/shared/theme-light.css'), 'tema reaproveitado');
        assert.ok(arquivos.some((a) => a.replaceAll('\\', '/') === 'vendor/supabase.js'));
        assert.ok(!arquivos.some((a) => /\.env|\.py$|\.sql$/.test(a)), 'nada de backend no dist');
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

test('verificacao de dist detecta segredo injetado', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-scan-'));
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        await writeFile(path.join(destino, 'js', 'vazamento.js'), 'const k = "sb_secret_vazada123";');
        await assert.rejects(verificarDist(destino), /sb_secret_/);
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

const RPCS_DE_LEITURA = new Set(['meus_perfis', 'contas_bancarias_do_perfil', 'contas_do_mes',
    'lancamentos_da_fatura', 'mes_pode_estar_incompleto', 'previa_geracao', 'categorias_de_despesa',
    'despesa_para_edicao', 'receitas_do_mes', 'fontes_de_receita', 'receita_para_edicao', 'pode_gerir_perfil',
    'cartoes_do_perfil', 'faturas_do_mes', 'compras_da_fatura', 'compra_para_edicao', 'previa_compra',
    'recorrencias_rejeitadas',
    'sugerir_competencia',  // FIN-CARTOES-FECHAMENTO-1 (so leitura)
    'dados_pagamento_fatura',  // FIN-CARTOES-PAGAMENTO-1 (so leitura)
    'dados_pagamento_despesa', 'dados_recebimento_receita', 'movimentos_do_mes',  // FIN-MOVIMENTACOES-1 (so leitura)
    'perfis_para_configuracao',  // FIN-MIGRACAO-FIDELIDADE-FASE-1 (so leitura)
    'recorrencias_do_perfil',  // FIN-FIDELIDADE-RECORRENCIAS-1 (so leitura)
    // FIN-FIDELIDADE-CARTOES-1 (so leitura)
    'cartoes_da_tela', 'categorias_cartao_do_perfil', 'limites_do_cartao', 'fatura_por_categoria',
    'lancamentos_fatura_por_categoria', 'parcelamento_da_compra',
    'analisar_importacao_cartao', 'sugerir_categorias_importacao', 'resolver_categoria_cartao_tela',
    // FIN-FIDELIDADE-MOVIMENTACOES-1 (so leitura; a conferencia de saldo nao altera nada)
    'contas_bancarias_tela', 'conta_bancaria_tela', 'extrato_conta_bancaria', 'conferir_saldo_conta',
    'compras_do_cartao_tela', 'despesas_diretas_tela', 'receitas_lancamentos_tela',
    'financiamentos_tela', 'financiamento_tela',  // FIN-FIDELIDADE-CONTRATOS-1 (fase 1, so leitura)
    'simular_quitacao',  // FIN-FINANCIAMENTOS-MOTOR-1 (so calcula, como a rota do Flask fora da guarda)
    // FIN-FIDELIDADE-PATRIMONIO-1 (fase 1, so leitura)
    'patrimonio_contas_tela', 'patrimonio_conta_tela', 'patrimonio_transferencias_tela', 'patrimonio_bens_tela',
    'patrimonio_resumo_tela', 'imagens_patrimonio',
    // FIN-PATRIMONIO-2: documentos vinculaveis e dados para a sugestao de bem a partir de documento
    'patrimonio_documentos_vinculaveis_tela', 'patrimonio_documento_sugestao_tela',
    // FIN-FIDELIDADE-DOCUMENTOS-1 (fase 1, so leitura, modo IRPF)
    'ir_contexto_tela', 'ir_categorias_tela', 'ir_categorias_despesa_tela', 'ir_comprovantes_tela',
    'ir_documentos_empresa_tela', 'lastro_saidas_tela',  // Documentos da Empresa (so leitura)
    'arquivo_comprovante_tela',  // "Abrir arquivo" (so leitura)
    'dashboard_resumo_tela',  // FIN-FIDELIDADE-CONSOLIDACAO-1 (so leitura)
    // FIN-FIDELIDADE-PATRIMONIO-1 (Mobilidade, fase 1, so leitura)
    'mobilidade_categorias_tela', 'veiculos_tela', 'projecoes_mobilidade_tela', 'veiculo_uso_tela', 'veiculo_regras_km_tela',
    'veiculo_manutencoes_km_tela', 'veiculo_financiamento_tela', 'mobilidade_ativa_tela', 'mobilidade_assinaturas_tela',
    'transporte_app_tela', 'previa_mobilidade',  // FIN-MOBILIDADE-2: previa da ativacao (so le)
    'consorcios_tela',  // FIN-FIDELIDADE-CONTRATOS-1 (Consorcios, so leitura)
    // FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 (so leitura)
    'receitas_fontes_tela', 'receitas_orcamentos_tela', 'receitas_realizadas_tela', 'categorias_tela', 'palavras_chave_tela',
    'categorias_cartao_tela', 'categoria_cartao_despesas_tela']);
// Escrita so por RPC transacional autorizada no banco, revisada uma a uma, e so na tela que a usa.
const RPCS_DE_ESCRITA = new Map([
    ['gerar_mes', 'despesas-recorrencias.js'],  // FIN-FIDELIDADE-DESPESAS-1: extraido de contas.js
    // FIN-DESPESAS-1
    // FIN-FIDELIDADE-DESPESAS-1: a tela original de Despesas chama pelo adaptador (despesas-adaptador.js)
    ['criar_despesa', ['despesas-adaptador.js', 'recorrencias-adaptador.js', 'lancamentos-adaptador.js']],
    ['editar_despesa', ['despesas-adaptador.js', 'lancamentos-adaptador.js']],
    ['excluir_despesa', ['despesas-adaptador.js', 'lancamentos-adaptador.js']],
    ['inativar_recorrencia', ['despesas-adaptador.js', 'recorrencias-adaptador.js']],
    // FIN-FIDELIDADE-RECORRENCIAS-1 (tela de Recorrencias; o banco exige gestao do perfil e a versao)
    ['editar_recorrencia', 'recorrencias-adaptador.js'],
    ['reativar_recorrencia', 'recorrencias-adaptador.js'],
    ['definir_meio_pagamento_recorrencia', ['recorrencias-adaptador.js', 'despesas-adaptador.js']],
    // FIN-FIDELIDADE-CARTOES-2 (R2: recorrencia no cartao; gestao, perfil, cartao e versao conferidos no banco)
    ['criar_recorrencia_cartao', 'recorrencias-adaptador.js'],
    ['editar_recorrencia_cartao', 'recorrencias-adaptador.js'],
    ['definir_situacao_recorrencia_cartao', 'recorrencias-adaptador.js'],
    // FIN-RECEITAS-1 (so previsoes; nenhum recebimento). FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1: tela original de Receitas
    // pelo adaptador (receitas-adaptador.js)
    ['criar_receita', 'receitas-adaptador.js'],
    ['editar_receita', 'receitas-adaptador.js'],
    ['excluir_receita', 'receitas-adaptador.js'],
    ['editar_fonte_receita', 'receitas-adaptador.js'],
    ['inativar_fonte_receita', 'receitas-adaptador.js'],
    // FIN-CARTOES-1 (compras e cartoes). FIN-FIDELIDADE-CARTOES-1: tela original de Cartoes pelo adaptador; a compra
    // nova continua com o formulario do novo aplicativo (compra-cartao.js); editar_compra fica sem tela (a do Flask edita
    // um lancamento por editar_lancamento_cartao).
    ['criar_compra', ['compra-cartao.js', 'lancamentos-adaptador.js']],  // FIN-FIDELIDADE-MOVIMENTACOES-1: Lancamentos
    ['excluir_compra', ['cartoes-adaptador.js', 'lancamentos-adaptador.js']],
    ['criar_cartao', 'cartoes-adaptador.js'],
    ['editar_cartao', 'cartoes-adaptador.js'],
    ['inativar_cartao', 'cartoes-adaptador.js'],
    // FIN-FIDELIDADE-CARTOES-1 (limites, um lancamento e parcelas futuras; gestao, perfil, versao e bloqueios no banco)
    ['vincular_limite_cartao', 'cartoes-adaptador.js'],
    ['atualizar_limite_cartao', 'cartoes-adaptador.js'],
    ['desativar_limite_cartao', 'cartoes-adaptador.js'],
    ['editar_lancamento_cartao', 'cartoes-adaptador.js'],
    ['editar_parcelas_futuras', 'cartoes-adaptador.js'],
    ['cancelar_parcelas_futuras', 'cartoes-adaptador.js'],
    // FIN-FIDELIDADE-CARTOES-1 (Importar Cartao: so depois da confirmacao na tela; tudo ou nada, analise refeita no banco)
    ['importar_fatura_cartao', 'importar-cartao-adaptador.js'],
    // FIN-CARTOES-RECORRENCIA-PENDENCIA-1 (so dispensa o aviso; nao muda recorrencia, compra nem fatura)
    ['dispensar_aviso_recorrencia', 'despesas-recorrencias.js'],
    // FIN-CARTOES-PAGAMENTO-1 (pagamento integral e estorno de fatura; debito/credito e saldo decididos no banco)
    // FIN-FIDELIDADE-CARTOES-1: so em Despesas, como no Flask (a tela original de Cartoes nao paga fatura).
    ['pagar_fatura', 'despesas-adaptador.js'],
    ['estornar_pagamento_fatura', 'despesas-adaptador.js'],
    // FIN-FIDELIDADE-MOVIMENTACOES-1 (Contas Bancarias: cadastro com versao; ajuste e transferencia pelo escritor unico,
    // com chave; so AJUSTE editavel; saldo pelos movimentos, decidido no banco)
    ['criar_conta_bancaria', 'contas-bancarias-adaptador.js'],
    ['editar_conta_bancaria', 'contas-bancarias-adaptador.js'],
    ['ajustar_saldo_conta', 'contas-bancarias-adaptador.js'],
    ['editar_ajuste_conta', 'contas-bancarias-adaptador.js'],
    ['excluir_ajuste_conta', 'contas-bancarias-adaptador.js'],
    ['transferir_entre_contas', 'contas-bancarias-adaptador.js'],
    // FIN-MOVIMENTACOES-1 (pagamento/estorno de despesa comum, recebimento/estorno de receita; saldo no banco)
    ['pagar_despesa', 'despesas-adaptador.js'],
    ['estornar_pagamento_despesa', 'despesas-adaptador.js'],
    ['receber_receita', 'receitas-adaptador.js'],
    ['estornar_recebimento', 'receitas-adaptador.js'],
    // FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 (Categorias do Cartao, por perfil: gestao e escritor unico no banco; as
    // categorias de despesa, globais, nao tem escrita no novo aplicativo)
    ['criar_categoria_cartao', 'categorias-adaptador.js'],
    ['editar_categoria_cartao', 'categorias-adaptador.js'],
    ['desativar_categoria_cartao', 'categorias-adaptador.js'],
    ['vincular_despesa_categoria_cartao', 'categorias-adaptador.js'],
    ['desvincular_despesa_categoria_cartao', 'categorias-adaptador.js'],
    // FIN-CONTRATOS-3 (consorcios: gestao, escritor unico, contrato travado; regeneracao e exclusao seguras no banco)
    ['criar_consorcio', 'recorrencias-adaptador.js'],
    ['editar_consorcio', 'recorrencias-adaptador.js'],
    ['excluir_consorcio', 'recorrencias-adaptador.js'],
    ['regenerar_parcelas_consorcio', 'recorrencias-adaptador.js'],
    // FIN-FINANCIAMENTOS-MOTOR-1 (motor SAC/TR: escritor unico, contrato travado, parcelas efetivadas e historicas intactas)
    ['criar_financiamento', 'financiamentos-adaptador.js'],
    ['registrar_amortizacao_extra', 'financiamentos-adaptador.js'],
    ['regenerar_parcelas_financiamento', 'financiamentos-adaptador.js'],
    ['excluir_financiamento', 'financiamentos-adaptador.js'],
    ['atualizar_financiamento', 'financiamentos-adaptador.js'],
    ['adicionar_vigencia_seguro', 'financiamentos-adaptador.js'],
    ['ajustar_saldo_devedor', 'financiamentos-adaptador.js'],
    // FIN-CATEGORIAS-RECORRENCIAS-2 (fonte: valor base, recorrencia e reativacao; recebimento sem previsao; catalogo
    // global de categorias, gravado so com escritor NOVO do catalogo e conta gestora)
    ['redefinir_fonte_receita', 'receitas-adaptador.js'],
    ['receber_sem_previsao', 'receitas-adaptador.js'],
    ['criar_categoria', 'categorias-adaptador.js'],
    ['editar_categoria', 'categorias-adaptador.js'],
    ['excluir_categoria', 'categorias-adaptador.js'],
    ['criar_palavra_chave', 'categorias-adaptador.js'],
    ['remover_palavra_chave', 'categorias-adaptador.js'],
    // FIN-PATRIMONIO-2 (caixinhas, transferencias e bens da Empresa; escritor unico do perfil no banco)
    ['criar_caixinha', 'patrimonio-adaptador.js'],
    ['editar_caixinha', 'patrimonio-adaptador.js'],
    ['inativar_caixinha', 'patrimonio-adaptador.js'],
    ['criar_transferencia_patrimonio', 'patrimonio-adaptador.js'],
    ['excluir_transferencia_patrimonio', 'patrimonio-adaptador.js'],
    ['criar_bem_patrimonial', 'patrimonio-adaptador.js'],
    ['criar_bem_de_documento', 'patrimonio-adaptador.js'],
    ['editar_bem_patrimonial', 'patrimonio-adaptador.js'],
    ['vincular_documento_bem', 'patrimonio-adaptador.js'],
    ['excluir_bem_patrimonial', 'patrimonio-adaptador.js'],
    // FIN-MOBILIDADE-2 (veiculos, modalidade ativa, assinaturas, transporte por app e despesas previstas; escritor unico)
    ['criar_veiculo', 'mobilidade-adaptador.js'],
    ['editar_veiculo', 'mobilidade-adaptador.js'],
    ['converter_veiculo', 'mobilidade-adaptador.js'],
    ['gerar_projecoes_veiculo', 'mobilidade-adaptador.js'],
    ['excluir_veiculo', 'mobilidade-adaptador.js'],
    ['criar_regra_km_veiculo', 'mobilidade-adaptador.js'],
    ['excluir_regra_km_veiculo', 'mobilidade-adaptador.js'],
    ['gerar_manutencao_km_veiculo', 'mobilidade-adaptador.js'],
    ['salvar_financiamento_veiculo', 'mobilidade-adaptador.js'],
    ['excluir_financiamento_veiculo', 'mobilidade-adaptador.js'],
    ['ativar_mobilidade', 'mobilidade-adaptador.js'],
    ['criar_assinatura_mobilidade', 'mobilidade-adaptador.js'],
    ['editar_assinatura_mobilidade', 'mobilidade-adaptador.js'],
    ['criar_caminho_app', 'mobilidade-adaptador.js'],
    ['editar_caminho_app', 'mobilidade-adaptador.js'],
    ['excluir_caminho_app', 'mobilidade-adaptador.js'],
    ['confirmar_despesa_prevista', 'mobilidade-adaptador.js'],
    ['adiar_despesa_prevista', 'mobilidade-adaptador.js'],
    ['ignorar_despesa_prevista', 'mobilidade-adaptador.js'],
    // FIN-DOCUMENTOS-2 (envio e guarda do arquivo no banco, revisao, vinculos e despesa a partir do documento)
    ['enviar_comprovante', 'documentos-fiscais-adaptador.js'],
    ['atualizar_comprovante', 'documentos-fiscais-adaptador.js'],
    ['validar_comprovante', 'documentos-fiscais-adaptador.js'],
    ['excluir_comprovante', 'documentos-fiscais-adaptador.js'],
    ['criar_vinculo_documento', 'documentos-fiscais-adaptador.js'],
    ['atualizar_vinculo_documento', 'documentos-fiscais-adaptador.js'],
    ['remover_vinculo_documento', 'documentos-fiscais-adaptador.js'],
    ['criar_financeiro_documento', 'documentos-fiscais-adaptador.js'],
    // FIN-MIGRACAO-FIDELIDADE-FASE-1 (gestao de perfis; o banco exige pode_gerir do perfil). Camada unica: perfil.js
    ['criar_perfil', 'perfil.js'],
    ['atualizar_perfil', 'perfil.js'],
    ['inativar_perfil', 'perfil.js'],
    ['reativar_perfil', 'perfil.js'],
    ['definir_perfil_padrao', 'perfil.js'],
]);

test('codigo-fonte do frontend nao escreve em tabelas nem usa innerHTML', async () => {
    const dir = new URL('../../src/js/', import.meta.url);
    for (const nome of await readdir(dir)) {
        // Comentarios fora: o que importa e o codigo executado.
        const fonte = (await readFile(new URL(nome, dir), 'utf8'))
            .replace(/\/\*[\s\S]*?\*\//g, '')
            .replace(/^\s*\/\/.*$/gm, '')
            .replace(/\s\/\/.*$/gm, '');
        assert.doesNotMatch(fonte, /\.(insert|update|upsert|delete)\s*\(/, `${nome} faz escrita direta`);
        // So RPCs liberadas (PERFIS-1); escrita exige revisao explicita (FIN-RECORRENCIA-1: gerar_mes).
        for (const [, funcao] of fonte.matchAll(/\.rpc\s*\(\s*['"`]([^'"`]+)['"`]/g)) {
            assert.ok(RPCS_DE_LEITURA.has(funcao) || [RPCS_DE_ESCRITA.get(funcao)].flat().includes(nome),
                `${nome} chama RPC nao liberada: ${funcao}`);
        }
        assert.doesNotMatch(fonte.replace(/\.rpc\s*\(\s*['"`][^'"`]+['"`]/g, ''), /\.rpc\s*\(/, `${nome} chama RPC com nome dinamico`);
        assert.doesNotMatch(fonte, /innerHTML|outerHTML|insertAdjacentHTML|document\.write/, `${nome} injeta HTML`);
    }
});

// FIN-MIGRACAO-FIDELIDADE-FASE-1: moldura do Flask montada no build.
const MENU_DO_FLASK = [
    ['Dashboard', ['Dashboard']],
    ['Operação', ['Lançamentos', 'Despesas', 'Recorrencias']],
    ['Gestão Financeira', ['Receitas', 'Cartões', 'Contas Bancárias', 'Financiamentos', 'Patrimônio', 'Documentos Fiscais']],
    ['Cadastros', ['Categorias', 'Mobilidade']],
    ['Ferramentas', ['Importar Cartão']],
    ['Sistema', ['Configurações e Preferências', 'Ajuda e Manual']],
];
const MIGRADAS = { 'contas.html': 'Despesas', 'recorrencias.html': 'Recorrencias', 'receitas.html': 'Receitas', 'cartoes.html': 'Cartões',
    'categorias.html': 'Categorias', 'configuracoes.html': 'Configurações e Preferências', 'ajuda.html': 'Ajuda e Manual',
    'importar-cartao.html': 'Importar Cartão', 'contas-bancarias.html': 'Contas Bancárias',
    'lancamentos.html': 'Lançamentos', 'financiamentos.html': 'Financiamentos', 'patrimonio.html': 'Patrimônio',
    'documentos-fiscais.html': 'Documentos Fiscais', 'dashboard.html': 'Dashboard',
    'mobilidade.html': 'Mobilidade' };

function menuDe(html) {
    return [...html.matchAll(/<div class="app-nav-section-title">([^<]+)<\/div>([\s\S]*?)<\/div>\s*(?=<div class="app-nav-section">|<\/nav>)/g)]
        .map(([, secao, corpo]) => [secao, [...corpo.matchAll(/<span class="app-nav-text">([^<]+)<\/span>/g)].map((m) => m[1])]);
}

test('todas as paginas usam a moldura do Flask com o mesmo menu, sem pagina quebrada', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-moldura-'));
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const arquivos = (await readdir(destino, { recursive: true })).map((a) => a.split(path.sep).join('/'));
        assert.ok(!arquivos.some((a) => /^(moldura|paginas)(\/|$)/.test(a)), 'fontes da moldura fora do dist');
        assert.ok(arquivos.includes('css/shared/layout.css') && arquivos.includes('js/original/ajuda.js'));
        const paginas = arquivos.filter((a) => a.endsWith('.html') && a !== 'index.html');
        assert.equal(paginas.length, 15);
        for (const pagina of paginas) {
            const html = await readFile(path.join(destino, pagina), 'utf8');
            assert.doesNotMatch(html, /\{\{|\{%|url_for|<script>|\sstyle=|\son[a-z]+=/i, `${pagina}: marcador, script ou estilo inline`);
            assert.deepEqual(menuDe(html), MENU_DO_FLASK, `${pagina}: menu igual ao do Flask`);
            assert.match(html, /<body class="app-shell-body" data-protegido hidden>/);
            for (const id of ['perfil-financeiro-trigger', 'perfil-financeiro-options', 'app-logout-button', 'app-alertas-button']) {
                assert.match(html, new RegExp(`id="${id}"`), `${pagina}: ${id}`);
            }
            const ativos = [...html.matchAll(/class="app-nav-link active"/g)];
            assert.equal(ativos.length, 1, `${pagina}: um item ativo`);
            for (const [, href] of html.matchAll(/<a href="([^"#?]+)[^"]*" class="app-nav-link/g)) {
                assert.ok(arquivos.includes(href), `${pagina}: link ${href} existe`);
            }
            const emMigracao = [...html.matchAll(/data-em-migracao[^>]*>[\s\S]*?<span class="app-nav-text">([^<]+)<\/span>\s*<span class="app-nav-status">Em migração<\/span>/g)].map((m) => m[1]);
            assert.deepEqual(emMigracao.sort(), MENU_DO_FLASK.flatMap(([, itens]) => itens)
                .filter((item) => !Object.values(MIGRADAS).includes(item)).sort(), `${pagina}: itens em migracao`);
        }
        const despesas = await readFile(path.join(destino, 'contas.html'), 'utf8');
        assert.match(despesas, /<a href="contas.html" class="app-nav-link active" data-pagina="despesas" aria-current="page">/);
        assert.match(despesas, /<span>Gerenciamento de Despesas<\/span>/);
        // Todos os modulos do menu migrados (Mobilidade foi o ultimo): nenhuma pagina "em migracao" no build.
        const mobilidade = await readFile(path.join(destino, 'mobilidade.html'), 'utf8');
        assert.doesNotMatch(mobilidade, /class="modulo-em-migracao"/);
        assert.match(mobilidade, /class="mobilidade-aviso-fase"/);
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

test('montagem escapa titulos e falha com marcador nao resolvido', () => {
    const base = '<title>{{documento}}</title><span>{{titulo}}</span>{{css}}{{acao}}{{conteudo}}{{scripts}}';
    const html = montarPagina(base, { arquivo: 'x.html', titulo: '<b>', conteudo: 'c', acao: '' }, new Set());
    assert.match(html, /<span>&lt;b&gt;<\/span>/);
    assert.throws(() => montarPagina(`${base}{{outro}}`, { arquivo: 'x.html', titulo: 't', conteudo: '' }, new Set()),
        /nao resolvido/);
});
