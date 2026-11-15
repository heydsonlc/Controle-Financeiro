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
    'cartoes_vinculados',  // FIN-CARTOES-MULTIPLOS-01 (so leitura)
    'formulario_abastecimento_lancamento', 'abastecimento_do_lancamento',  // FIN-MOB-ABAST-LANCAMENTOS-01 (so leitura)
    'abastecimentos_da_importacao', 'candidatas_abastecimento',  // FIN-MVP-LANCAMENTOS-03 (so leem: sugestao e candidatas)
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
    'registrar_abastecimento', 'corrigir_abastecimento', 'anular_abastecimento', 'abastecimentos_veiculo_tela', 'custos_veiculos_tela',
    'veiculo_manutencoes_km_tela', 'veiculo_financiamento_tela', 'mobilidade_ativa_tela', 'mobilidade_assinaturas_tela',
    'transporte_app_tela', 'previa_mobilidade',  // FIN-MOBILIDADE-2: previa da ativacao (so le)
    'projecoes_veiculo_tela',  // FIN-MVP-MOB-02: lista de Projecoes do veiculo (so le)
    'previa_interrupcao_recorrencia', 'previa_retomada_recorrencia',  // FIN-RECORRENCIAS-INATIVACAO-01 (P22, so leem)
    'receitas_totais_do_mes', 'previa_atualizacao_previsoes',  // FIN-RECEITAS-SALDO-01 (so leem)
    'previa_cancelamento_despesa',  // FIN-DESPESAS-CANCELAMENTO-01 (P23, so le)
    'consorcios_tela',  // FIN-FIDELIDADE-CONTRATOS-1 (Consorcios, so leitura)
    // FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 (so leitura)
    'receitas_fontes_tela', 'receitas_orcamentos_tela', 'receitas_realizadas_tela', 'categorias_tela', 'palavras_chave_tela',
    'categorias_cartao_tela', 'categoria_cartao_despesas_tela',
    'situacao_catalogo_categorias',  // FIN-MIGRACAO-P0P1-01: escritor do catalogo e se a conta e gestora (so leitura)
    'tr_oficial_tela', 'tr_faltantes',  // FIN-PRE-PRODUCAO-1: Indexadores (so leitura)
    // FIN-PRE-PRODUCAO-1: Documentos (so leitura): vincular, desvincular, lastro e sugestao financeira
    'entidades_vinculaveis_tela', 'vinculos_documento_tela', 'lastro_resumo_tela', 'sugestao_financeira_documento_tela',
    'preferencias_tela']);  // FIN-PRE-PRODUCAO-1: Preferencias (so leitura)
// Escrita so por RPC transacional autorizada no banco, revisada uma a uma, e so na tela que a usa.
const RPCS_DE_ESCRITA = new Map([
    ['gerar_mes', 'despesas-recorrencias.js'],  // FIN-FIDELIDADE-DESPESAS-1: extraido de contas.js
    // FIN-DESPESAS-1
    // FIN-FIDELIDADE-DESPESAS-1: a tela original de Despesas chama pelo adaptador; FIN-MVP-MOB-01: as chamadas ficam no servico
    // comum ao desktop e a Lista de Despesas mobile (despesas-servico.js), sem funcao nova
    ['criar_despesa', ['despesas-servico.js', 'recorrencias-adaptador.js', 'lancamentos-adaptador.js']],
    ['editar_despesa', ['despesas-servico.js', 'lancamentos-adaptador.js']],
    ['excluir_despesa', ['despesas-servico.js', 'lancamentos-adaptador.js']],
    ['inativar_recorrencia', 'recorrencias-adaptador.js'],
    // FIN-RECORRENCIAS-INATIVACAO-01 (P22): interromper (Recorrencias e "esta e as futuras" de Despesas) e retomar
    ['interromper_recorrencia', ['despesas-servico.js', 'recorrencias-adaptador.js']],
    ['retomar_recorrencia', 'recorrencias-adaptador.js'],
    // P24 (FIN-CONSORCIOS-INTEGRACAO-01): realizar a contemplacao prevista e editar parcela de consorcio pendente
    ['realizar_contemplacao_consorcio', 'receitas-servico.js'],
    ['editar_parcela_consorcio', 'despesas-servico.js'],
    // FIN-RECEITAS-SALDO-01: previsoes pendentes pelo valor-base, so com a confirmacao da previa (auditado no banco)
    ['atualizar_previsoes_fonte', 'receitas-servico.js'],
    // FIN-DESPESAS-CANCELAMENTO-01 (P23): cancelar a obrigacao com pagamento estornado (elegibilidade e historico no banco)
    ['cancelar_despesa', 'despesas-servico.js'],
    // FIN-FIDELIDADE-RECORRENCIAS-1 (tela de Recorrencias; o banco exige gestao do perfil e a versao)
    ['editar_recorrencia', 'recorrencias-adaptador.js'],
    ['reativar_recorrencia', 'recorrencias-adaptador.js'],
    ['definir_meio_pagamento_recorrencia', ['recorrencias-adaptador.js', 'despesas-servico.js']],
    // FIN-FIDELIDADE-CARTOES-2 (R2: recorrencia no cartao; gestao, perfil, cartao e versao conferidos no banco)
    ['criar_recorrencia_cartao', 'recorrencias-adaptador.js'],
    ['editar_recorrencia_cartao', 'recorrencias-adaptador.js'],
    ['definir_situacao_recorrencia_cartao', 'recorrencias-adaptador.js'],
    // FIN-RECEITAS-1 (so previsoes; nenhum recebimento). FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1: tela original de Receitas
    // pelo adaptador. FIN-MVP-MOBILE-04: as chamadas ficam no servico comum ao desktop e as Receitas mobile
    // (receitas-servico.js), sem funcao nova
    ['criar_receita', 'receitas-servico.js'],
    ['editar_receita', 'receitas-servico.js'],
    ['excluir_receita', 'receitas-servico.js'],
    ['editar_fonte_receita', 'receitas-servico.js'],
    ['inativar_fonte_receita', 'receitas-servico.js'],
    // FIN-CARTOES-1 (compras e cartoes). FIN-FIDELIDADE-CARTOES-1: tela original de Cartoes pelo adaptador (FIN-MVP-MOBILE-03:
    // rotas no servico cartoes-servico.js, comum ao desktop e aos Cartoes mobile, sem funcao nova); a compra
    // nova fica em Lancamentos (MVP-FIN-AJUSTES-01); editar_compra fica sem tela (a do Flask edita um lancamento por
    // editar_lancamento_cartao).
    // FIN-FIDELIDADE-MOVIMENTACOES-1: Lancamentos. FIN-MVP-MOBILE-05: a chamada fica no servico comum a tela Lancamentos e a
    // Nova Despesa mobile (compras-servico.js), sem funcao nova
    ['criar_compra', ['compras-servico.js']],
    // FIN-MOB-ABAST-LANCAMENTOS-01: despesa e abastecimento numa transacao; desvincular so com a decisao do usuario
    ['salvar_lancamento_abastecimento', 'abastecimento-servico.js'],  // FIN-MVP-MOBILE-06: servico comum a Lancamentos e ao Registrar Lancamento
    ['desvincular_abastecimento', ['lancamentos-adaptador.js', 'cartoes-servico.js', 'mobilidade-adaptador.js']],
    // FIN-MVP-LANCAMENTOS-03: vincular a compra ao abastecimento pela Mobilidade (as regras e o historico no banco)
    ['vincular_abastecimento', 'mobilidade-adaptador.js'],
    ['excluir_compra', ['cartoes-servico.js', 'lancamentos-adaptador.js']],
    ['criar_cartao', 'cartoes-servico.js'],
    ['editar_cartao', 'cartoes-servico.js'],
    ['inativar_cartao', 'cartoes-servico.js'],
    // FIN-FIDELIDADE-CARTOES-1 (limites, um lancamento e parcelas futuras; gestao, perfil, versao e bloqueios no banco)
    ['vincular_limite_cartao', 'cartoes-servico.js'],
    ['atualizar_limite_cartao', 'cartoes-servico.js'],
    ['desativar_limite_cartao', 'cartoes-servico.js'],
    ['editar_lancamento_cartao', 'cartoes-servico.js'],
    ['editar_parcelas_futuras', 'cartoes-servico.js'],
    ['cancelar_parcelas_futuras', 'cartoes-servico.js'],
    // FIN-CARTOES-MULTIPLOS-01 (cartao vinculado ao contrato: so os 4 ultimos digitos; versao, perfil e contrato no banco)
    ['salvar_cartao_vinculado', 'cartoes-servico.js'],
    // FIN-FIDELIDADE-CARTOES-1 (Importar Cartao: so depois da confirmacao na tela; tudo ou nada, analise refeita no banco)
    ['importar_fatura_cartao', 'importar-cartao-adaptador.js'],
    // FIN-CARTOES-RECORRENCIA-PENDENCIA-1 (so dispensa o aviso; nao muda recorrencia, compra nem fatura)
    ['dispensar_aviso_recorrencia', 'despesas-recorrencias.js'],
    // FIN-CARTOES-PAGAMENTO-1 (pagamento integral e estorno de fatura; debito/credito e saldo decididos no banco)
    // FIN-FIDELIDADE-CARTOES-1: so em Despesas, como no Flask (a tela original de Cartoes nao paga fatura).
    ['pagar_fatura', 'despesas-servico.js'],
    // FIN-DESPESAS-PAGAMENTO-LOTE-01 (P20): ocorrencias pendentes com a conta escolhida; tudo ou nada, revalidado no banco
    ['pagar_despesas_lote', 'despesas-servico.js'],
    ['estornar_pagamento_fatura', 'despesas-servico.js'],
    // FIN-FIDELIDADE-MOVIMENTACOES-1 (Contas Bancarias: cadastro com versao; ajuste e transferencia pelo escritor unico,
    // com chave; so AJUSTE editavel; saldo pelos movimentos, decidido no banco)
    ['criar_conta_bancaria', 'contas-bancarias-adaptador.js'],
    ['editar_conta_bancaria', 'contas-bancarias-adaptador.js'],
    ['ajustar_saldo_conta', 'contas-bancarias-adaptador.js'],
    ['editar_ajuste_conta', 'contas-bancarias-adaptador.js'],
    ['excluir_ajuste_conta', 'contas-bancarias-adaptador.js'],
    ['transferir_entre_contas', 'contas-servico.js'],  // FIN-MVP-MOBILE-06: servico comum a Contas Bancarias e ao Registrar Lancamento
    // FIN-MOVIMENTACOES-1 (pagamento/estorno de despesa comum, recebimento/estorno de receita; saldo no banco)
    ['pagar_despesa', 'despesas-servico.js'],
    ['estornar_pagamento_despesa', 'despesas-servico.js'],
    ['receber_receita', 'receitas-servico.js'],
    ['estornar_recebimento', 'receitas-servico.js'],
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
    ['redefinir_fonte_receita', 'receitas-servico.js'],
    ['receber_sem_previsao', 'receitas-servico.js'],
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
    // FIN-MVP-MOB-02 (itens da lista de Projecoes do veiculo; escritor unico)
    ['salvar_projecao_veiculo', 'mobilidade-adaptador.js'],
    ['alternar_projecao_veiculo', 'mobilidade-adaptador.js'],
    ['excluir_projecao_veiculo', 'mobilidade-adaptador.js'],
    // FIN-DOCUMENTOS-2 (envio e guarda do arquivo no banco, revisao, vinculos e despesa a partir do documento)
    ['enviar_comprovante', 'documentos-fiscais-adaptador.js'],
    ['atualizar_comprovante', 'documentos-fiscais-adaptador.js'],
    ['validar_comprovante', 'documentos-fiscais-adaptador.js'],
    ['excluir_comprovante', 'documentos-fiscais-adaptador.js'],
    ['criar_vinculo_documento', 'documentos-fiscais-adaptador.js'],
    ['atualizar_vinculo_documento', 'documentos-fiscais-adaptador.js'],
    ['remover_vinculo_documento', 'documentos-fiscais-adaptador.js'],
    // FIN-MIGRACAO-LASTRO-EMPRESA-01 (metadados empresariais e saidas sem documento; escritor unico e perfil Empresa no banco)
    ['salvar_metadata_empresarial', 'documentos-fiscais-adaptador.js'],
    ['vincular_saida_documento', 'documentos-fiscais-adaptador.js'],
    ['marcar_status_saida', 'documentos-fiscais-adaptador.js'],
    // FIN-PRE-PRODUCAO-1: modulo comum a Documentos, Despesas e Lancamentos ("Gerar financeiro" / "A partir de documento")
    ['criar_financeiro_documento', 'documento-financeiro.js'],
    // FIN-PRE-PRODUCAO-1: TR mensal (indice unico; gravar exige gerir um perfil ativo; TR usada nao muda)
    ['criar_tr', 'indexadores-adaptador.js'],
    ['editar_tr', 'indexadores-adaptador.js'],
    ['importar_tr', 'indexadores-adaptador.js'],
    // FIN-PRE-PRODUCAO-1: preferencias (interface do usuario; as do perfil exigem gerir o perfil)
    ['salvar_preferencias', 'configuracoes.js'],
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
        // index.html (login), inicio.html (pagina principal mobile, FIN-MVP-MOB-08), despesas-mobile.html (Lista de
        // Despesas mobile, FIN-MVP-MOB-01), cartoes-mobile.html (FIN-MVP-MOBILE-03) e receitas-mobile.html (FIN-MVP-MOBILE-04)
        // ficam fora da moldura do desktop.
        const paginas = arquivos.filter((a) => a.endsWith('.html') && !['index.html', 'inicio.html', 'despesas-mobile.html',
            'cartoes-mobile.html', 'receitas-mobile.html', 'despesa-nova-mobile.html',  // + FIN-MVP-MOBILE-05
            'lancamento-mobile.html',  // + FIN-MVP-MOBILE-06
            'contas-mobile.html',  // + FIN-MVP-MOBILE-07
            'pagamentos-mobile.html'].includes(a));  // + FIN-MVP-MOBILE-08
        assert.equal(paginas.length, 16);  // + indexadores.html (FIN-PRE-PRODUCAO-1)
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

// FIN-MVP-MOB-08: pagina principal mobile, fora da moldura; atalhos visiveis e desabilitados.
// FIN-MVP-MOB-01: o atalho Resumo (e o Resumo da barra) navega, para a Lista de Despesas mobile.
// FIN-MVP-MOBILE-03: o atalho Cartoes navega, para os Cartoes mobile (a barra nao ganha item).
// FIN-MVP-MOBILE-04: o atalho Receita navega, para as Receitas mobile (a barra nao ganha item).
// FIN-MVP-MOBILE-05: o atalho Despesa navega, para a Nova Despesa mobile.
// FIN-MVP-MOBILE-06: o atalho Lancamento e o Lancar da barra navegam, para o Registrar Lancamento (a mesma pagina).
// FIN-MVP-MOBILE-07: o atalho Contas navega, para as Contas mobile.
// FIN-MVP-MOBILE-08: o atalho Pagamentos navega, para os Pagamentos mobile.
test('pagina principal mobile: protegida, sem moldura, so Recorrencias desabilitado entre os 8 atalhos', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-mob08-'));
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const html = await readFile(path.join(destino, 'inicio.html'), 'utf8');
        assert.ok(!(await readdir(destino)).some((n) => /previa/i.test(n)), 'pre-visualizacao local fora do dist');
        assert.match(html, /<body class="mob mob-inicio" data-protegido hidden>/);
        assert.doesNotMatch(html, /\{\{|<script>|\sstyle=|\son[a-z]+=/i, 'sem marcador, script ou estilo inline');
        assert.doesNotMatch(html, /app-sidebar|app-shell-body|css\/shared\//, 'sem moldura nem CSS do desktop');
        assert.match(html, /<link rel="stylesheet" href="css\/mobile-base.css">\s*<link rel="stylesheet" href="css\/inicio-mobile.css">/);
        // No HTML todos comecam desabilitados e sem link; js/mobile-comum.js habilita os de MODULOS_ATIVOS.
        const atalhos = [...html.matchAll(/<a class="mob-atalho" data-modulo="(\w+)" data-destino="([\w.-]+)" aria-disabled="true">[\s\S]*?<span class="mob-atalho-nome">([^<]+)<\/span>/g)]
            .map((m) => [m[3], m[1], m[2]]);
        assert.deepEqual(atalhos.map((a) => a[0]), ['Receita', 'Despesa', 'Lançamento', 'Resumo', 'Pagamentos', 'Recorrências', 'Cartões', 'Contas']);
        assert.deepEqual(atalhos.find((a) => a[0] === 'Resumo'), ['Resumo', 'resumo', 'despesas-mobile.html']);
        assert.deepEqual(atalhos.find((a) => a[0] === 'Cartões'), ['Cartões', 'cartoes', 'cartoes-mobile.html']);
        assert.deepEqual(atalhos.find((a) => a[0] === 'Receita'), ['Receita', 'receita', 'receitas-mobile.html']);
        assert.deepEqual(atalhos.find((a) => a[0] === 'Despesa'), ['Despesa', 'despesa', 'despesa-nova-mobile.html']);
        assert.deepEqual(atalhos.find((a) => a[0] === 'Lançamento'), ['Lançamento', 'lancamento', 'lancamento-mobile.html']);
        assert.deepEqual(atalhos.find((a) => a[0] === 'Contas'), ['Contas', 'contas', 'contas-mobile.html']);
        assert.deepEqual(atalhos.find((a) => a[0] === 'Pagamentos'), ['Pagamentos', 'pagamentos', 'pagamentos-mobile.html']);
        assert.doesNotMatch(html.slice(html.indexOf('mob-grade'), html.indexOf('class="mob-barra"')), /href=/, 'atalhos sem link no HTML');
        const barra = [...html.matchAll(/<(a|button) (?:type="button" )?class="mob-barra-item([^"]*)"([^>]*)>[\s\S]*?<span>([^<]+)<\/span>/g)]
            .map((m) => [m[4], /href=/.test(m[3]) ? 'link' : (m[1] === 'button' ? 'botao' : 'desabilitado')]);
        // "Mais" abre o menu com Sair (homologacao de 13/11/2026); Resumo ganha o link no script (MODULOS_ATIVOS).
        assert.deepEqual(barra, [['Início', 'link'], ['Lançar', 'desabilitado'], ['Resumo', 'desabilitado'], ['Mais', 'botao']]);
        assert.match(html, /<a class="mob-barra-item" data-modulo="resumo" data-destino="despesas-mobile.html" aria-disabled="true">/);
        assert.match(html, /<a class="mob-barra-item" data-modulo="lancar" data-destino="lancamento-mobile.html" aria-disabled="true">/);
        assert.match(html, /<div class="mob-menu-mais" id="mob-menu-mais" role="menu"[^>]*hidden>[\s\S]*?id="mob-sair"[\s\S]*?<span>Sair<\/span>/);
        const css = await readFile(path.join(destino, 'css', 'inicio-mobile.css'), 'utf8');
        for (const regra of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/(^|\})\s*([^{}@]+)\{/g)) {
            for (const seletor of regra[2].split(',')) assert.match(seletor.trim(), /^body\.mob-inicio(\[|\s|$)/, `regra restrita: ${seletor.trim()}`);
        }
        const script = await readFile(path.join(destino, 'js', 'inicio-mobile.js'), 'utf8');
        assert.doesNotMatch(script, /\.rpc\s*\(|\.from\s*\(|despesas-servico/, 'a pagina principal nao le nem grava dados');
        const comum = await readFile(path.join(destino, 'js', 'mobile-comum.js'), 'utf8');
        assert.match(comum, /export const MODULOS_ATIVOS = new Set\(\['resumo', 'cartoes', 'receita', 'despesa', 'lancamento', 'lancar', 'contas', 'pagamentos'\]\);/,
            'Resumo, Cartoes, Receita, Despesa, Lancamento, Lancar (FIN-MVP-MOBILE-06), Contas (FIN-MVP-MOBILE-07) e Pagamentos (FIN-MVP-MOBILE-08) ativos');
        assert.doesNotMatch(comum, /\.rpc\s*\(|\.from\s*\(/);
        // FIN-MVP-MOBILE-05/06: so a permissao do perfil ativo (perfil.js): quem so le recebe Despesa, Lancamento e Lancar desabilitados.
        assert.ok(script.includes('ajustarCadastrosPelaPermissao(usuario.id)'));
        assert.match(comum, /MODULOS_DE_CADASTRO = \['despesa', 'lancamento', 'lancar'\]/);
        assert.ok(comum.includes("from './perfil.js'"), 'a permissao pela funcao do banco (pode_gerir_perfil), sem outro controle');
        assert.match(comum, /export function desabilitarModulo\(modulo, motivo\)/);
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

// FIN-MVP-MOB-01: Lista de Despesas mobile, fora da moldura; CSS restrito as paginas mobile; dados so pelo servico comum
// ao desktop (nenhuma consulta propria ao banco).
test('lista de despesas mobile: protegida, sem moldura, CSS restrito e dados so pelo servico do desktop', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-mob01-'));
    const regrasRestritas = (css, padrao, nome) => {
        for (const regra of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/(^|\})\s*([^{}@]+)\{/g)) {
            for (const seletor of regra[2].split(',')) assert.match(seletor.trim(), padrao, `${nome}: regra restrita: ${seletor.trim()}`);
        }
    };
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const html = await readFile(path.join(destino, 'despesas-mobile.html'), 'utf8');
        assert.match(html, /<body class="mob mob-modulo mob-despesas" data-protegido hidden>/);
        assert.doesNotMatch(html, /\{\{|<script>|\sstyle=|\son[a-z]+=/i, 'sem marcador, script ou estilo inline');
        assert.doesNotMatch(html, /app-sidebar|app-shell-body|css\/shared\//, 'sem moldura nem CSS do desktop');
        assert.match(html, /<h1 class="mob-titulo">Despesas<\/h1>/);
        assert.match(html, /id="mob-voltar" href="inicio.html" data-inicio/, 'voltar a pagina principal');
        assert.match(html, /id="mob-filtros"/, 'filtros num painel (sem barra permanente)');
        for (const id of ['mob-mes-anterior', 'mob-competencia', 'mob-mes-seguinte', 'mob-lista', 'mob-total', 'mob-folha', 'mob-sair']) {
            assert.match(html, new RegExp(`id="${id}"`), id);
        }
        const barra = [...html.matchAll(/<(a|button) (?:type="button" )?class="mob-barra-item([^"]*)"([^>]*)>[\s\S]*?<span>([^<]+)<\/span>/g)]
            .map((m) => [m[4], m[2].includes('ativo') ? 'ativo' : (/href=/.test(m[3]) ? 'link' : (m[1] === 'button' ? 'botao' : 'desabilitado'))]);
        assert.deepEqual(barra, [['Início', 'link'], ['Lançar', 'desabilitado'], ['Resumo', 'ativo'], ['Mais', 'botao']]);
        for (const arquivo of ['css/mobile-base.css', 'css/mobile-modulo.css', 'css/interrupcao-recorrencia.css',
            'js/original/formas_pagamento.js', 'js/interrupcao-recorrencia.js', 'js/despesas-mobile.js']) {
            assert.match(html, new RegExp(`(href|src)="${arquivo.replace(/[.]/g, '\.')}"`), arquivo);
        }
        regrasRestritas(await readFile(path.join(destino, 'css', 'mobile-base.css'), 'utf8'), /^body\.mob(\[|\s|$)/, 'mobile-base.css');
        // FIN-MVP-MOBILE-03: o CSS da lista (era despesas-mobile.css) e comum aos modulos mobile, restrito a body.mob-modulo.
        regrasRestritas(await readFile(path.join(destino, 'css', 'mobile-modulo.css'), 'utf8'), /^body\.mob-modulo(\[|\s|$)/, 'mobile-modulo.css');
        const script = await readFile(path.join(destino, 'js', 'despesas-mobile.js'), 'utf8');
        assert.doesNotMatch(script, /\.rpc\s*\(|\.from\s*\(|supabase/, 'nenhuma consulta propria: so o servico comum');
        assert.match(script, /from '\.\/despesas-servico\.js'/);
        assert.match(script, /from '\.\/despesas-grupos\.js'/);
        // O desktop usa o mesmo servico (as mesmas rotas e funcoes do banco).
        const adaptador = await readFile(path.join(destino, 'js', 'despesas-adaptador.js'), 'utf8');
        assert.match(adaptador, /import \{ configurarDespesas, responderDespesas \} from '\.\/despesas-servico\.js';/);
        const servico = await readFile(path.join(destino, 'js', 'despesas-servico.js'), 'utf8');
        assert.doesNotMatch(servico, /document\.|window\./, 'servico sem DOM');
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

// FIN-MVP-MOBILE-03: Cartoes mobile, fora da moldura; CSS restrito; dados so pelos servicos do desktop (Cartoes e a fatura em
// Despesas), sem consulta propria ao banco nem botao de compra nova.
test('cartoes mobile: protegida, sem moldura, CSS restrito e dados so pelos servicos do desktop', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-mobile03-'));
    const regrasRestritas = (css, padrao, nome) => {
        for (const regra of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/(^|\})\s*([^{}@]+)\{/g)) {
            for (const seletor of regra[2].split(',')) assert.match(seletor.trim(), padrao, `${nome}: regra restrita: ${seletor.trim()}`);
        }
    };
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const html = await readFile(path.join(destino, 'cartoes-mobile.html'), 'utf8');
        assert.match(html, /<body class="mob mob-modulo mob-cartoes" data-protegido hidden>/);
        assert.doesNotMatch(html, /\{\{|<script>|\sstyle=|\son[a-z]+=/i, 'sem marcador, script ou estilo inline');
        assert.doesNotMatch(html, /app-sidebar|app-shell-body|css\/shared\//, 'sem moldura nem CSS do desktop');
        assert.match(html, /<h1 class="mob-titulo">Cartões<\/h1>/);
        assert.match(html, /id="mob-voltar" href="inicio.html" data-inicio/, 'voltar a pagina principal');
        assert.doesNotMatch(html, /Nova compra|Novo lan/i, 'sem botao de compra nova (FIN-MVP-MOBILE-06)');
        for (const id of ['mob-mes-anterior', 'mob-competencia', 'mob-mes-seguinte', 'mob-cartao', 'mob-fatura', 'mob-lista',
            'mob-filtros', 'mob-folha', 'mob-sair']) {
            assert.match(html, new RegExp(`id="${id}"`), id);
        }
        // A barra segue o padrao aprovado: nenhum item novo (Cartoes nao e item da barra).
        const barra = [...html.matchAll(/<(a|button) (?:type="button" )?class="mob-barra-item([^"]*)"([^>]*)>[\s\S]*?<span>([^<]+)<\/span>/g)]
            .map((m) => [m[4], m[2].includes('ativo') ? 'ativo' : (/href=/.test(m[3]) ? 'link' : (m[1] === 'button' ? 'botao' : 'desabilitado'))]);
        assert.deepEqual(barra, [['Início', 'link'], ['Lançar', 'desabilitado'], ['Resumo', 'desabilitado'], ['Mais', 'botao']]);
        for (const arquivo of ['css/mobile-base.css', 'css/mobile-modulo.css', 'css/cartoes-mobile.css', 'js/cartoes-mobile.js']) {
            assert.match(html, new RegExp(`(href|src)="${arquivo.replace(/[.]/g, '\\.')}"`), arquivo);
        }
        regrasRestritas(await readFile(path.join(destino, 'css', 'cartoes-mobile.css'), 'utf8'), /^body\.mob-cartoes(\[|\s|$)/, 'cartoes-mobile.css');
        const script = await readFile(path.join(destino, 'js', 'cartoes-mobile.js'), 'utf8');
        assert.doesNotMatch(script, /\.rpc\s*\(|\.from\s*\(|supabase/, 'nenhuma consulta propria: so os servicos do desktop');
        for (const modulo of ['cartoes-servico', 'despesas-servico', 'cartoes-grupos', 'mobile-pagamento']) {
            assert.ok(script.includes(`from './${modulo}.js'`), modulo);
        }
        // O desktop usa o mesmo servico de Cartoes (as mesmas rotas e funcoes do banco); servicos e regras sem DOM.
        const adaptador = await readFile(path.join(destino, 'js', 'cartoes-adaptador.js'), 'utf8');
        assert.ok(adaptador.includes("import { configurarCartoes, podeGerirPerfil, responderCartoes } from './cartoes-servico.js';"));
        assert.doesNotMatch(adaptador, /\.rpc\s*\(/, 'o adaptador do desktop so registra o servico');
        const servico = await readFile(path.join(destino, 'js', 'cartoes-servico.js'), 'utf8');
        assert.doesNotMatch(servico, /document\./, 'servico sem DOM');
        assert.ok(servico.includes('window.confirm(texto)'), 'desktop: as mesmas confirmacoes (window.confirm)');
        const grupos = await readFile(path.join(destino, 'js', 'cartoes-grupos.js'), 'utf8');
        assert.doesNotMatch(grupos, /document\.|window\.|\.rpc\s*\(/, 'regras de leitura puras');
        // A pagina principal leva o atalho Cartoes a esta pagina (MODULOS_ATIVOS) e a sessao a aceita como destino.
        assert.ok((await readFile(path.join(destino, 'js', 'sessao.js'), 'utf8')).includes("'cartoes-mobile.html'"));
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

// FIN-MVP-MOBILE-04: Receitas mobile, fora da moldura; CSS restrito; dados so pelo servico do desktop (o mesmo da tela de
// Receitas), sem consulta propria ao banco; "+" para nova receita no cabecalho (sem item novo na barra).
test('receitas mobile: protegida, sem moldura, CSS restrito e dados so pelo servico do desktop', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-mobile04-'));
    const regrasRestritas = (css, padrao, nome) => {
        for (const regra of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/(^|\})\s*([^{}@]+)\{/g)) {
            for (const seletor of regra[2].split(',')) assert.match(seletor.trim(), padrao, `${nome}: regra restrita: ${seletor.trim()}`);
        }
    };
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const html = await readFile(path.join(destino, 'receitas-mobile.html'), 'utf8');
        assert.match(html, /<body class="mob mob-modulo mob-receitas" data-protegido hidden>/);
        assert.doesNotMatch(html, /\{\{|<script>|\sstyle=|\son[a-z]+=/i, 'sem marcador, script ou estilo inline');
        assert.doesNotMatch(html, /app-sidebar|app-shell-body|css\/shared\//, 'sem moldura nem CSS do desktop');
        assert.match(html, /<h1 class="mob-titulo">Receitas<\/h1>/);
        assert.match(html, /id="mob-voltar" href="inicio.html" data-inicio/, 'voltar a pagina principal');
        assert.match(html, /id="mob-nova" aria-label="Nova receita" aria-haspopup="dialog" hidden/, '"+" compacto, escondido ate saber se pode gravar');
        for (const id of ['mob-mes-anterior', 'mob-competencia', 'mob-mes-seguinte', 'mob-resumo', 'mob-lista', 'mob-atrasadas',
            'mob-filtros', 'mob-folha', 'mob-sair']) {
            assert.match(html, new RegExp(`id="${id}"`), id);
        }
        // A barra segue o padrao aprovado: nenhum item novo (Receita nao e item da barra).
        const barra = [...html.matchAll(/<(a|button) (?:type="button" )?class="mob-barra-item([^"]*)"([^>]*)>[\s\S]*?<span>([^<]+)<\/span>/g)]
            .map((m) => [m[4], m[2].includes('ativo') ? 'ativo' : (/href=/.test(m[3]) ? 'link' : (m[1] === 'button' ? 'botao' : 'desabilitado'))]);
        assert.deepEqual(barra, [['Início', 'link'], ['Lançar', 'desabilitado'], ['Resumo', 'desabilitado'], ['Mais', 'botao']]);
        for (const arquivo of ['css/mobile-base.css', 'css/mobile-modulo.css', 'css/receitas-mobile.css', 'js/receitas-mobile.js']) {
            assert.match(html, new RegExp(`(href|src)="${arquivo.replace(/[.]/g, '\\.')}"`), arquivo);
        }
        regrasRestritas(await readFile(path.join(destino, 'css', 'receitas-mobile.css'), 'utf8'), /^body\.mob-receitas(\[|\s|$)/, 'receitas-mobile.css');
        const script = await readFile(path.join(destino, 'js', 'receitas-mobile.js'), 'utf8');
        assert.doesNotMatch(script, /\.rpc\s*\(|\.from\s*\(|supabase/, 'nenhuma consulta propria: so o servico do desktop');
        for (const modulo of ['receitas-servico', 'receitas-lista', 'mobile-ui', 'mobile-comum']) {
            assert.ok(script.includes(`from './${modulo}.js'`), modulo);
        }
        // O desktop usa o mesmo servico (as mesmas rotas e funcoes do banco); servico sem DOM fora do modal do desktop.
        const adaptador = await readFile(path.join(destino, 'js', 'receitas-adaptador.js'), 'utf8');
        assert.ok(adaptador.includes("import { configurarReceitas, podeGerirPerfil, responderReceitas } from './receitas-servico.js';"));
        assert.doesNotMatch(adaptador, /\.rpc\s*\(/, 'o adaptador do desktop so registra o servico');
        const lista = await readFile(path.join(destino, 'js', 'receitas-lista.js'), 'utf8');
        assert.doesNotMatch(lista, /document\.|window\.|\.rpc\s*\(/, 'regras de leitura puras');
        // A pagina principal leva o atalho Receita a esta pagina (MODULOS_ATIVOS) e a sessao a aceita como destino.
        assert.ok((await readFile(path.join(destino, 'js', 'sessao.js'), 'utf8')).includes("'receitas-mobile.html'"));
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

// FIN-MVP-MOBILE-05: Nova Despesa mobile, fora da moldura; CSS restrito; grava so pelo servico de Despesas do desktop
// (POST /api/despesas -> criar_despesa), sem consulta propria ao banco; sem campos que o servico recusa.
test('nova despesa mobile: protegida, sem moldura, CSS restrito e cadastro so pelo servico do desktop', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-mobile05-'));
    const regrasRestritas = (css, padrao, nome) => {
        for (const regra of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/(^|\})\s*([^{}@]+)\{/g)) {
            for (const seletor of regra[2].split(',')) assert.match(seletor.trim(), padrao, `${nome}: regra restrita: ${seletor.trim()}`);
        }
    };
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const html = await readFile(path.join(destino, 'despesa-nova-mobile.html'), 'utf8');
        assert.match(html, /<body class="mob mob-modulo mob-despesa-nova" data-protegido hidden>/);
        assert.doesNotMatch(html, /\{\{|<script>|\sstyle=|\son[a-z]+=/i, 'sem marcador, script ou estilo inline');
        assert.doesNotMatch(html, /app-sidebar|app-shell-body|css\/shared\//, 'sem moldura nem CSS do desktop');
        assert.match(html, /<h1 class="mob-titulo">Nova Despesa<\/h1>/);
        assert.match(html, /id="mob-voltar" href="inicio.html" data-inicio/, 'voltar a pagina principal');
        for (const id of ['mob-perfil', 'mob-aviso', 'mob-cadastro', 'mob-sair']) assert.match(html, new RegExp(`id="${id}"`), id);
        // A barra segue o padrao aprovado; o Lancar ganha o link no script (FIN-MVP-MOBILE-06).
        assert.match(html, /data-modulo="lancar" data-destino="lancamento-mobile.html"/);
        const barra = [...html.matchAll(/<(a|button) (?:type="button" )?class="mob-barra-item([^"]*)"([^>]*)>[\s\S]*?<span>([^<]+)<\/span>/g)]
            .map((m) => [m[4], /href=/.test(m[3]) ? 'link' : (m[1] === 'button' ? 'botao' : 'desabilitado')]);
        assert.deepEqual(barra, [['Início', 'link'], ['Lançar', 'desabilitado'], ['Resumo', 'desabilitado'], ['Mais', 'botao']]);
        for (const arquivo of ['css/mobile-base.css', 'css/mobile-modulo.css', 'css/despesa-nova-mobile.css', 'js/despesa-nova-mobile.js']) {
            assert.match(html, new RegExp(`(href|src)="${arquivo.replace(/[.]/g, '\\.')}"`), arquivo);
        }
        regrasRestritas(await readFile(path.join(destino, 'css', 'despesa-nova-mobile.css'), 'utf8'), /^body\.mob-despesa-nova(\[|\s|$)/,
            'despesa-nova-mobile.css');
        const pagina = await readFile(path.join(destino, 'js', 'despesa-nova-mobile.js'), 'utf8');
        assert.doesNotMatch(pagina, /\.rpc\s*\(|\.from\s*\(|supabase/, 'nenhuma consulta propria: so o servico do desktop');
        assert.ok(pagina.includes("from './despesas-servico.js'"), 'servico de Despesas do desktop');
        // FIN-MVP-MOBILE-06: o formulario e o comum (Nova Despesa e Registrar Lancamento), sem segunda copia.
        assert.ok(pagina.includes("from './despesa-formulario.js'") && pagina.includes('montarFormularioDespesa(cadastro'));
        const script = await readFile(path.join(destino, 'js', 'despesa-formulario.js'), 'utf8');
        assert.doesNotMatch(script, /\.rpc\s*\(|\.from\s*\(|supabase/, 'formulario sem consulta propria');
        assert.match(script, /api\('POST', '\/api\/despesas', corpo\)/, 'a mesma rota do formulario do desktop');
        // O que o servico do desktop recusa nao e oferecido: despesa ja paga e consorcio; o cartao nunca vai a /api/despesas.
        assert.match(script, /pago: false/);
        assert.doesNotMatch(script, /e_consorcio|meio_pagamento = 'cartao'|meio_pagamento: 'cartao'/, 'sem consorcio nem conta a pagar no cartao');
        // Ajuste final (Proposta A): "Cartao de credito" grava so pela compra da tela Lancamentos (criar_compra no servico comum).
        assert.ok(script.includes("from './compras-servico.js'"), 'compra no cartao pelo servico comum a tela Lancamentos');
        assert.match(script, /api\('POST', `\/api\/cartoes\/\$\{corpo\.cartao_id\}\/lancamentos`, corpo, responderCompras\)/);
        assert.ok(script.includes('O cadastro de despesas recorrentes no cartão de crédito será disponibilizado em uma etapa posterior.'));
        const compras = await readFile(path.join(destino, 'js', 'compras-servico.js'), 'utf8');
        assert.match(compras, /supabase\.rpc\('criar_compra'/);
        const lancamentos = await readFile(path.join(destino, 'js', 'lancamentos-adaptador.js'), 'utf8');
        assert.ok(lancamentos.includes("from './compras-servico.js'") && !/rpc\('criar_compra'/.test(lancamentos),
            'a tela Lancamentos grava a compra pelo mesmo servico');
        assert.ok((await readFile(path.join(destino, 'js', 'sessao.js'), 'utf8')).includes("'despesa-nova-mobile.html'"));
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

// FIN-MVP-MOBILE-06: Registrar Lancamento mobile, fora da moldura; CSS restrito; um seletor de operacoes e, abaixo, os
// formularios ja existentes (um so de cada), pelos servicos do desktop: nenhuma consulta propria nem gravacao nova.
test('registrar lancamento mobile: protegido, sem moldura, CSS restrito, operacoes pelos formularios e servicos existentes', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-mobile06-'));
    const regrasRestritas = (css, padrao, nome) => {
        for (const regra of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/(^|\})\s*([^{}@]+)\{/g)) {
            for (const seletor of regra[2].split(',')) assert.match(seletor.trim(), padrao, `${nome}: regra restrita: ${seletor.trim()}`);
        }
    };
    const ler = (arquivo) => readFile(path.join(destino, 'js', arquivo), 'utf8');
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const html = await readFile(path.join(destino, 'lancamento-mobile.html'), 'utf8');
        assert.match(html, /<body class="mob mob-modulo mob-despesa-nova mob-lancamento" data-protegido hidden>/);
        assert.doesNotMatch(html, /\{\{|<script>|\sstyle=|\son[a-z]+=/i, 'sem marcador, script ou estilo inline');
        assert.doesNotMatch(html, /app-sidebar|app-shell-body|css\/shared\//, 'sem moldura nem CSS do desktop');
        assert.match(html, /<h1 class="mob-titulo">Registrar Lançamento<\/h1>/);
        assert.match(html, /id="mob-voltar" href="inicio.html" data-inicio/, 'voltar a pagina principal');
        for (const id of ['mob-perfil', 'mob-aviso', 'mob-tipos', 'mob-cadastro', 'mob-sair']) assert.match(html, new RegExp(`id="${id}"`), id);
        // Seletor compacto: as operacoes que o desktop tem (Receita, Despesa, Compra no cartao, Transferencia, Abastecimento).
        const tipos = [...html.matchAll(/<button type="button" class="mob-tipo" data-tipo="(\w+)" aria-pressed="false">[\s\S]*?<span>([^<]+)<\/span>/g)]
            .map((m) => [m[1], m[2]]);
        assert.deepEqual(tipos, [['receita', 'Receita'], ['despesa', 'Despesa'], ['cartao', 'Compra no cartão'],
            ['transferencia', 'Transferência'], ['abastecimento', 'Abastecimento']]);
        assert.match(html, /<a class="mob-barra-item ativo" data-modulo="lancar" data-destino="lancamento-mobile.html" aria-current="page">/);
        for (const arquivo of ['css/mobile-base.css', 'css/mobile-modulo.css', 'css/despesa-nova-mobile.css', 'css/lancamento-mobile.css',
            'js/lancamento-mobile.js']) {
            assert.match(html, new RegExp(`(href|src)="${arquivo.replace(/[.]/g, '\\.')}"`), arquivo);
        }
        regrasRestritas(await readFile(path.join(destino, 'css', 'lancamento-mobile.css'), 'utf8'), /^body\.mob-lancamento(\[|\s|$)/,
            'lancamento-mobile.css');
        // Pagina e formularios: nenhuma consulta propria (so os servicos do desktop).
        for (const arquivo of ['lancamento-mobile.js', 'despesa-formulario.js', 'receita-formulario.js', 'transferencia-formulario.js',
            'abastecimento-formulario.js', 'mobile-cartao.js', 'mobile-formulario.js']) {
            assert.doesNotMatch(await ler(arquivo), /\.rpc\s*\(|\.from\s*\(|supabase/, `${arquivo}: so os servicos do desktop`);
        }
        const pagina = await ler('lancamento-mobile.js');
        for (const modulo of ['despesa-formulario.js', 'receita-formulario.js', 'transferencia-formulario.js', 'abastecimento-formulario.js']) {
            assert.ok(pagina.includes(`from './${modulo}'`), `formulario existente: ${modulo}`);
        }
        // Um formulario de cada: a Nova Despesa e as Receitas mobile usam os mesmos modulos.
        assert.ok((await ler('receitas-mobile.js')).includes("from './receita-formulario.js'"));
        assert.ok((await ler('despesa-nova-mobile.js')).includes("from './despesa-formulario.js'"));
        // Gravacoes so nos servicos comuns ao desktop (a tela do desktop chama o mesmo servico).
        assert.match(await ler('abastecimento-servico.js'), /supabase\.rpc\('salvar_lancamento_abastecimento'/);
        assert.ok(!/rpc\('salvar_lancamento_abastecimento'/.test(await ler('lancamentos-adaptador.js'))
            && (await ler('lancamentos-adaptador.js')).includes("from './abastecimento-servico.js'"));
        assert.match(await ler('contas-servico.js'), /supabase\.rpc\('transferir_entre_contas'/);
        assert.ok(!/rpc\('transferir_entre_contas'/.test(await ler('contas-bancarias-adaptador.js'))
            && (await ler('contas-bancarias-adaptador.js')).includes("from './contas-servico.js'"));
        // Abastecimento: compra so a vista; litros so exibidos (o banco calcula).
        assert.match(await ler('abastecimento-formulario.js'), /comParcelas: false/);
        assert.ok((await ler('sessao.js')).includes("'lancamento-mobile.html'"));
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

// FIN-MVP-MOBILE-07: Contas e Movimentacoes mobile, fora da moldura; CSS restrito; so consulta pelo servico comum a tela
// Contas Bancarias (contas, saldo do banco, extrato e conferencia); a transferencia e a do Registrar Lancamento.
test('contas mobile: protegida, sem moldura, CSS restrito, consulta pelo servico do desktop e sem escrita propria', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-mobile07-'));
    const ler = (arquivo) => readFile(path.join(destino, 'js', arquivo), 'utf8');
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const html = await readFile(path.join(destino, 'contas-mobile.html'), 'utf8');
        assert.match(html, /<body class="mob mob-modulo mob-contas" data-protegido hidden>/);
        assert.doesNotMatch(html, /\{\{|<script>|\sstyle=|\son[a-z]+=/i, 'sem marcador, script ou estilo inline');
        assert.doesNotMatch(html, /app-sidebar|app-shell-body|css\/shared\//, 'sem moldura nem CSS do desktop');
        assert.match(html, /<h1 class="mob-titulo">Contas<\/h1>/);
        assert.match(html, /id="mob-voltar" href="inicio.html" data-inicio/, 'voltar a pagina principal');
        for (const id of ['mob-perfil', 'mob-filtros', 'mob-transferir', 'mob-conta', 'mob-saldo', 'mob-competencia', 'mob-lista', 'mob-folha', 'mob-sair']) {
            assert.match(html, new RegExp(`id="${id}"`), id);
        }
        assert.doesNotMatch(html, /Nova conta|mob-nova/, 'sem criar conta');
        // A barra nao ganha item: os mesmos quatro das paginas homologadas.
        const barra = [...html.matchAll(/<(a|button) (?:type="button" )?class="mob-barra-item([^"]*)"([^>]*)>[\s\S]*?<span>([^<]+)<\/span>/g)].map((m) => m[4]);
        assert.deepEqual(barra, ['Início', 'Lançar', 'Resumo', 'Mais']);
        for (const arquivo of ['css/mobile-base.css', 'css/mobile-modulo.css', 'css/contas-mobile.css', 'js/contas-mobile.js']) {
            assert.match(html, new RegExp(`(href|src)="${arquivo.replace(/[.]/g, '\\.')}"`), arquivo);
        }
        const css = await readFile(path.join(destino, 'css', 'contas-mobile.css'), 'utf8');
        for (const regra of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/(^|\})\s*([^{}@]+)\{/g)) {
            for (const seletor of regra[2].split(',')) assert.match(seletor.trim(), /^body\.mob-contas(\[|\s|$)/, `regra restrita: ${seletor.trim()}`);
        }
        const pagina = await ler('contas-mobile.js');
        assert.doesNotMatch(pagina, /\.rpc\s*\(|\.from\s*\(|supabase/, 'so o servico comum');
        assert.ok(pagina.includes("from './contas-servico.js'"));
        assert.doesNotMatch(pagina, /'(POST|PUT|DELETE)'/, 'nenhuma gravacao: so consulta');
        assert.match(pagina, /lancamento-mobile\.html\?mes=\$\{estado\.mes\}&tipo=transferencia&origem=/, 'transferencia pelo MOBILE-06');
        assert.doesNotMatch(await ler('contas-movimentos.js'), /\.rpc\s*\(|supabase|document\./, 'regras de exibicao puras');
        const servico = await ler('contas-servico.js');
        for (const funcao of ['contas_bancarias_tela', 'extrato_conta_bancaria', 'conferir_saldo_conta']) assert.ok(servico.includes(`supabase.rpc('${funcao}'`), funcao);
        assert.doesNotMatch(servico, /ajustar_saldo_conta|editar_ajuste_conta|excluir_ajuste_conta|criar_conta_bancaria/, 'sem ajuste nem cadastro');
        const adaptador = await ler('contas-bancarias-adaptador.js');
        assert.ok(adaptador.includes('extratoDaConta(estado.perfilId') && !/rpc\('extrato_conta_bancaria'/.test(adaptador),
            'a tela Contas Bancarias le o extrato pelo mesmo servico');
        assert.ok((await ler('sessao.js')).includes("'contas-mobile.html'"));
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

// FIN-MVP-MOBILE-08: Pagamentos mobile, fora da moldura; CSS restrito; obrigacoes pelo servico de Despesas do desktop SEM gerar
// recorrencias; pagamento so pelos fluxos existentes (individual e lote da recorrencia semanal, P20/P21), sem funcao nova.
test('pagamentos mobile: protegida, sem moldura, CSS restrito, leitura sem geracao e pagamento pelos fluxos do desktop', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-mobile08-'));
    const ler = (arquivo) => readFile(path.join(destino, 'js', arquivo), 'utf8');
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const html = await readFile(path.join(destino, 'pagamentos-mobile.html'), 'utf8');
        assert.match(html, /<body class="mob mob-modulo mob-pagamentos" data-protegido hidden>/);
        assert.doesNotMatch(html, /\{\{|<script>|\sstyle=|\son[a-z]+=/i, 'sem marcador, script ou estilo inline');
        assert.doesNotMatch(html, /app-sidebar|app-shell-body|css\/shared\//, 'sem moldura nem CSS do desktop');
        assert.match(html, /<h1 class="mob-titulo">Pagamentos<\/h1>/);
        assert.match(html, /id="mob-voltar" href="inicio.html" data-inicio/, 'voltar a pagina principal');
        for (const id of ['mob-perfil', 'mob-mes-anterior', 'mob-competencia', 'mob-mes-seguinte', 'mob-resumo', 'mob-total-pendente',
            'mob-qtd-selecionadas', 'mob-total-selecionado', 'mob-lista', 'mob-selecao', 'mob-limpar', 'mob-pagar', 'mob-folha', 'mob-sair']) {
            assert.match(html, new RegExp(`id="${id}"`), id);
        }
        // A barra nao ganha item: os mesmos quatro das paginas homologadas.
        const barra = [...html.matchAll(/<(a|button) (?:type="button" )?class="mob-barra-item([^"]*)"([^>]*)>[\s\S]*?<span>([^<]+)<\/span>/g)].map((m) => m[4]);
        assert.deepEqual(barra, ['Início', 'Lançar', 'Resumo', 'Mais']);
        for (const arquivo of ['css/mobile-base.css', 'css/mobile-modulo.css', 'css/pagamentos-mobile.css', 'js/original/formas_pagamento.js',
            'js/pagamentos-mobile.js']) {
            assert.match(html, new RegExp(`(href|src)="${arquivo.replace(/[.]/g, '\\.')}"`), arquivo);
        }
        const css = await readFile(path.join(destino, 'css', 'pagamentos-mobile.css'), 'utf8');
        for (const regra of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/(^|\})\s*([^{}@]+)\{/g)) {
            for (const seletor of regra[2].split(',')) assert.match(seletor.trim(), /^body\.mob-pagamentos(\[|\s|$)/, `regra restrita: ${seletor.trim()}`);
        }
        const pagina = await ler('pagamentos-mobile.js');
        assert.doesNotMatch(pagina, /\.rpc\s*\(|\.from\s*\(|supabase/, 'nenhuma consulta propria: so o servico do desktop');
        for (const modulo of ['despesas-servico', 'despesas-grupos', 'mobile-pagamento', 'mobile-ui', 'mobile-comum']) {
            assert.ok(pagina.includes(`from './${modulo}.js'`), modulo);
        }
        assert.ok(pagina.includes("api('GET', `/api/pagamentos?mes_referencia=${mes}`)"), 'leitura pela rota sem geracao');
        assert.doesNotMatch(pagina, /\/api\/despesas\?mes|gerar_mes|gerarRecorrencias/, 'a consulta nao gera recorrencias');
        assert.doesNotMatch(pagina, /'(PUT|DELETE)'/, 'sem edicao nem exclusao: ficam na Lista de Despesas');
        assert.ok(pagina.includes('abrirPagamento(d, { api, contasAtivas, concluir })'), 'pagamento individual comum');
        assert.ok(pagina.includes('abrirLote(nome, competencia, {'), 'lote da recorrencia semanal comum');
        assert.ok(pagina.includes("status_pagamento !== 'Dispensada'"), 'obrigacao cancelada (P23) fora das pendentes');
        assert.ok(pagina.includes('podeGerirPerfil()'), 'permissao pela funcao do banco');
        // O servico: rota de leitura sem a geracao; o lote e o individual sao as funcoes de sempre (nenhuma nova).
        const servico = await ler('despesas-servico.js');
        const leitura = servico.slice(servico.indexOf('async function obrigacoesDoMes'), servico.indexOf('// Detalhe da fatura'));
        assert.ok(leitura.includes("supabase.rpc('contas_do_mes'") && !/gerarRecorrencias|prepararGeracao|gerar_mes/.test(leitura),
            'obrigacoes do mes sem gerar');
        assert.ok(servico.includes("['GET', /^\\/api\\/pagamentos\\/?$/, (m, p) => obrigacoesDoMes(p)]"), 'rota de leitura');
        // Um painel de lote so: a Lista de Despesas mobile usa o mesmo de js/mobile-pagamento.js.
        const comum = await ler('mobile-pagamento.js');
        assert.ok(comum.includes('export async function abrirLote(nome, competencia, ctx)'));
        assert.ok(comum.includes("api('POST', '/api/despesas/pagar-lote'"));
        const lista = await ler('despesas-mobile.js');
        assert.ok(lista.includes('abrirLote as loteComum') && !lista.includes("'/api/despesas/pagar-lote'"), 'lista usa o painel comum');
        assert.ok((await ler('sessao.js')).includes("'pagamentos-mobile.html'"));
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});

// FIN-MVP-MOBILE-FINAL-01: aplicativo na tela de inicio (PWA/iOS). Manifesto valido (nome, inicio na pagina principal mobile,
// standalone, cores), icones PNG nos tamanhos declarados, metadados iOS nas paginas mobile e no login; telas do desktop sem
// manifesto; nenhum service worker nem cache (Cache API, IndexedDB); CSP inalterada (manifesto e icones do proprio site).
test('pwa: manifesto, icones e metadados iOS so nas paginas mobile e no login; sem service worker nem cache de dados', async () => {
    const destino = await mkdtemp(path.join(os.tmpdir(), 'cf-web-pwa-'));
    const dimensoes = (png) => [png.readUInt32BE(16), png.readUInt32BE(20)];  // cabecalho IHDR
    try {
        await construir({ url: URL_OK, chave: 'sb_publishable_abc123', destino });
        const manifesto = JSON.parse(await readFile(path.join(destino, 'manifest.webmanifest'), 'utf8'));
        assert.equal(manifesto.name, 'Controle Financeiro');
        assert.equal(manifesto.short_name, 'Financeiro');
        assert.equal(manifesto.start_url, 'inicio.html', 'abre na pagina principal mobile (que exige a sessao)');
        assert.equal(manifesto.scope, './');
        assert.equal(manifesto.display, 'standalone');
        assert.equal(manifesto.orientation, 'portrait');
        assert.equal(manifesto.theme_color, '#1d1d1f', 'preto da identidade');
        assert.equal(manifesto.background_color, '#ffffff');
        assert.ok(manifesto.icons.some((i) => i.purpose === 'maskable'));
        // FIN-MVP-MOBILE-ICON-01: icones da carteira do portal, com versao no endereco (as imagens ficam 4 h no cache do navegador).
        for (const icone of manifesto.icons) {
            assert.match(icone.src, /^icones\/[\w-]+\.png\?v=2$/, icone.src);
            const png = await readFile(path.join(destino, icone.src.split('?')[0]));
            assert.equal(png.subarray(1, 4).toString('latin1'), 'PNG', icone.src);
            assert.deepEqual(dimensoes(png), icone.sizes.split('x').map(Number), icone.src);
        }
        assert.deepEqual(dimensoes(await readFile(path.join(destino, 'icones', 'apple-touch-icon.png'))), [180, 180]);
        assert.deepEqual(dimensoes(await readFile(path.join(destino, 'icones', 'icone-32.png'))), [32, 32]);
        const mobile = ['inicio.html', 'despesas-mobile.html', 'cartoes-mobile.html', 'receitas-mobile.html', 'despesa-nova-mobile.html',
            'lancamento-mobile.html', 'contas-mobile.html', 'pagamentos-mobile.html'];
        for (const pagina of [...mobile, 'index.html']) {
            const html = await readFile(path.join(destino, pagina), 'utf8');
            for (const marca of ['<link rel="manifest" href="manifest.webmanifest">', '<link rel="apple-touch-icon" href="icones/apple-touch-icon.png?v=2">',
                '<meta name="apple-mobile-web-app-capable" content="yes">', '<meta name="apple-mobile-web-app-title" content="Financeiro">']) {
                assert.ok(html.includes(marca), `${pagina}: ${marca}`);
            }
        }
        for (const pagina of mobile) {
            const html = await readFile(path.join(destino, pagina), 'utf8');
            assert.match(html, /<meta name="viewport" content="width=device-width, initial-scale=1\.0, viewport-fit=cover">/, `${pagina}: areas seguras`);
            assert.match(html, /<meta name="theme-color" content="#ffffff">/, `${pagina}: barra do navegador como a homologada`);
            assert.ok(html.includes('<link rel="icon" type="image/png" sizes="32x32" href="icones/icone-32.png?v=2">'), `${pagina}: icone da aba`);
        }
        // Telas do desktop: sem manifesto nem metadados do aplicativo (o desktop nao muda).
        for (const pagina of ['contas.html', 'cartoes.html', 'receitas.html', 'lancamentos.html', 'contas-bancarias.html', 'dashboard.html']) {
            assert.doesNotMatch(await readFile(path.join(destino, pagina), 'utf8'), /manifest\.webmanifest|apple-mobile-web-app/, pagina);
        }
        // Nada de service worker, Cache API ou IndexedDB: nenhum dado financeiro fica no aparelho (so a sessao e o perfil ativo).
        for (const arquivo of await readdir(path.join(destino, 'js'))) {
            if (!arquivo.endsWith('.js')) continue;
            assert.doesNotMatch(await readFile(path.join(destino, 'js', arquivo), 'utf8'), /serviceWorker|caches\.|indexedDB/, arquivo);
        }
        assert.ok(!(await readdir(destino)).some((n) => /^(sw|service-worker)\.js$/.test(n)), 'sem service worker');
        const cabecalhos = await readFile(path.join(destino, '_headers'), 'utf8');
        assert.match(cabecalhos, /default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:/, 'CSP inalterada');
    } finally {
        await rm(destino, { recursive: true, force: true });
    }
});
