-- Reversao de 20261126090000_financeiro_patrimonio_escrita.sql (FIN-PATRIMONIO-2).
-- Remove as funcoes de escrita e leitura novas e a tabela de controle (operacao_patrimonio). Caixinhas,
-- transferencias, bens e vinculos gravados ficam nas tabelas do Flask, consistentes (saldos e vinculos sao os
-- mesmos que o Flask gravaria); a escrita volta a ser so do Flask.

drop function financeiro.patrimonio_documento_sugestao_tela(integer, integer);
drop function financeiro.patrimonio_documentos_vinculaveis_tela(integer, text);
drop function financeiro.excluir_bem_patrimonial(integer, integer);
drop function financeiro.vincular_documento_bem(integer, integer, jsonb);
drop function financeiro.editar_bem_patrimonial(integer, integer, jsonb);
drop function financeiro.criar_bem_de_documento(integer, jsonb, uuid);
drop function financeiro.criar_bem_patrimonial(integer, jsonb, uuid);
drop function financeiro.excluir_transferencia_patrimonio(integer, integer);
drop function financeiro.criar_transferencia_patrimonio(integer, jsonb, uuid);
drop function financeiro.inativar_caixinha(integer, integer);
drop function financeiro.editar_caixinha(integer, integer, jsonb);
drop function financeiro.criar_caixinha(integer, jsonb, uuid);
drop function financeiro.documento_patrimonio_flask(public.ir_comprovante);
drop function financeiro.inserir_bem(integer, jsonb);
drop function financeiro.vincular_documento_ao_bem(integer, integer, integer, jsonb);
drop function financeiro.travar_documento_patrimonio(integer, integer);
drop function financeiro.travar_bem(integer, integer);
drop function financeiro.depreciacao_bem(numeric, integer);
drop function financeiro.aplicar_dados_bem(public.bem_patrimonial, jsonb, boolean);
drop function financeiro.imagem_bem(text);
drop function financeiro.opcao_bem(text, text[], text);
drop function financeiro.data_bem(text);
drop function financeiro.inteiro_bem(jsonb);
drop function financeiro.decimal_bem(text);
drop function financeiro.texto_bem(text, integer);
drop function financeiro.exigir_perfil_empresa(integer);
drop function financeiro.travar_contas_transferencia(integer, integer);
drop function financeiro.ler_dados_caixinha(integer, integer, jsonb, boolean);
drop function financeiro.travar_caixinha(integer, integer);
drop function financeiro.valor_patrimonio(jsonb, text);
drop function financeiro.registrar_operacao_patrimonio(uuid, integer, text, jsonb);
drop function financeiro.repeticao_patrimonio(uuid, integer, text);
drop table financeiro.operacao_patrimonio;
