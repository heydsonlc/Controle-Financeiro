-- Reversao de 20261129090000_financeiro_indexadores.sql (FIN-PRE-PRODUCAO-1). As TR cadastradas pelo novo aplicativo
-- ficam em public.indice_tr_mensal (tabela do Flask, que continua lendo); so as funcoes e as tabelas de idempotencia e
-- auditoria sao removidas.
drop function if exists financeiro.importar_tr(jsonb, uuid);
drop function if exists financeiro.editar_tr(text, jsonb);
drop function if exists financeiro.criar_tr(jsonb, uuid);
drop function if exists financeiro.tr_faltantes(text, text);
drop function if exists financeiro.tr_oficial_tela(integer, text, text);
drop function if exists financeiro.idx_travar();
drop function if exists financeiro.idx_repeticao(uuid, text);
drop function if exists financeiro.idx_auditar(text, text, numeric, numeric, text, text);
drop function if exists financeiro.idx_tr_json(public.indice_tr_mensal);
drop function if exists financeiro.idx_tr_usada(text);
drop function if exists financeiro.idx_decimal(text);
drop function if exists financeiro.idx_competencia(text);
drop function if exists financeiro.idx_exigir_acesso(boolean);
drop table if exists financeiro.indice_tr_historico;
drop table if exists financeiro.operacao_indexador;
