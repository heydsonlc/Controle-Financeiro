-- Reversao de 20261128090000_financeiro_documentos_escrita.sql (FIN-DOCUMENTOS-2): remove as funcoes de escrita de
-- Documentos e a tabela de idempotencia. Documentos, arquivos, vinculos e despesas gravados ficam (dados do Flask).
-- Ordem: reverter esta antes da 20261127 e das anteriores.

drop function financeiro.criar_financeiro_documento(integer, integer, jsonb, uuid);
drop function financeiro.remover_vinculo_documento(integer, integer, integer);
drop function financeiro.atualizar_vinculo_documento(integer, integer, integer, jsonb);
drop function financeiro.doc_vinculo(integer, integer, integer);
drop function financeiro.criar_vinculo_documento(integer, integer, jsonb);
drop function financeiro.doc_entidade(integer, text, integer);
drop function financeiro.doc_opcao(text, text[], text);
drop function financeiro.excluir_comprovante(integer, integer);
drop function financeiro.validar_comprovante(integer, integer);
drop function financeiro.atualizar_comprovante(integer, integer, jsonb);
drop function financeiro.enviar_comprovante(integer, jsonb, text, uuid);
drop function financeiro.doc_nome_seguro(text);
drop function financeiro.doc_evento(integer, text, text);
drop function financeiro.doc_comprovante(integer, integer);
drop function financeiro.registrar_operacao_documento(uuid, integer, text, jsonb);
drop function financeiro.repeticao_documento(uuid, integer, text);

drop table financeiro.operacao_documento;
