-- Reversao de 20261127090000_financeiro_mobilidade_escrita.sql (FIN-MOBILIDADE-2).
-- Remove as funcoes de escrita de Mobilidade e a tabela de idempotencia. Os dados gravados por elas (veiculos,
-- previstas, regras, financiamentos, assinaturas, cenarios, recorrencias, contas) ficam: sao dados do Flask.
-- Ordem: reverter esta antes das anteriores (docs/FIN_INTEGRACAO_1123_1126_1.md §3); nenhuma migration posterior
-- depende destas funcoes.
do $$
begin
    if exists (select 1 from financeiro.operacao_mobilidade) then
        raise notice 'financeiro.operacao_mobilidade tem registros de idempotencia; eles saem com a tabela';
    end if;
end
$$;

drop function financeiro.ignorar_despesa_prevista(integer, integer);
drop function financeiro.adiar_despesa_prevista(integer, integer, jsonb);
drop function financeiro.mob_ajustar_ciclo(integer, public.despesa_prevista);
drop function financeiro.confirmar_despesa_prevista(integer, integer, jsonb);
drop function financeiro.mob_registrar_combustivel(integer, public.despesa_prevista);
drop function financeiro.mob_rotulo_prevista(public.despesa_prevista);
drop function financeiro.mob_prevista(integer, integer);
drop function financeiro.excluir_caminho_app(integer, integer);
drop function financeiro.editar_caminho_app(integer, integer, jsonb);
drop function financeiro.criar_caminho_app(integer, jsonb, uuid);
drop function financeiro.mob_gerar_projecoes_app(integer, integer, jsonb, integer);
drop function financeiro.editar_assinatura_mobilidade(integer, integer, jsonb);
drop function financeiro.criar_assinatura_mobilidade(integer, jsonb, uuid);
drop function financeiro.ativar_mobilidade(integer, jsonb, uuid);
drop function financeiro.previa_mobilidade(integer, jsonb);
drop function financeiro.mob_cartao(integer, integer);
drop function financeiro.mob_origem(integer, text, integer);
drop function financeiro.mob_config_app(jsonb);
drop function financeiro.mob_cenario_flask(public.mobilidade_cenario_ativo);
drop function financeiro.mob_assinatura_flask(public.mobilidade_assinatura);
drop function financeiro.mob_resolver_cc(integer, integer, integer);
drop function financeiro.excluir_financiamento_veiculo(integer, integer);
drop function financeiro.salvar_financiamento_veiculo(integer, integer, jsonb);
drop function financeiro.mob_financiamento_flask(public.veiculo_financiamento);
drop function financeiro.mob_limpar_financiamento(integer, integer);
drop function financeiro.gerar_manutencao_km_veiculo(integer, integer, jsonb);
drop function financeiro.excluir_regra_km_veiculo(integer, integer, integer);
drop function financeiro.criar_regra_km_veiculo(integer, integer, jsonb, uuid);
drop function financeiro.excluir_veiculo(integer, integer);
drop function financeiro.gerar_projecoes_veiculo(integer, integer, jsonb);
drop function financeiro.converter_veiculo(integer, integer, jsonb);
drop function financeiro.editar_veiculo(integer, integer, jsonb);
drop function financeiro.criar_veiculo(integer, jsonb, uuid);
drop function financeiro.mob_dados_veiculo(public.veiculo, jsonb);
drop function financeiro.mob_gerar_projecoes(integer, integer, integer);
drop function financeiro.mob_tipo_evento(text);
drop function financeiro.mob_aplicar_categorias(integer);
drop function financeiro.mob_veiculo(integer, integer);
drop function financeiro.mob_agora();
drop function financeiro.mob_bool(jsonb, boolean);
drop function financeiro.mob_data(text);
drop function financeiro.mob_meses(jsonb, integer);
drop function financeiro.mob_inteiro(jsonb);
drop function financeiro.mob_categoria_evento(text);
drop function financeiro.mob_categoria(text);
drop function financeiro.repeticao_mobilidade(uuid, integer, text);
drop function financeiro.mob_inserir_prevista(integer, text, integer, integer, date, numeric, jsonb);
drop function financeiro.registrar_operacao_mobilidade(uuid, integer, text, jsonb);

drop table financeiro.operacao_mobilidade;
