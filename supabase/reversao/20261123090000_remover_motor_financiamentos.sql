-- REVERSAO da migration 20261123090000 (FIN-FINANCIAMENTOS-MOTOR-1): remove as funcoes do motor, o registro de
-- parcelas historicas e os dois indices unicos. Nao e migration (fora de supabase/migrations). Aplicar so com
-- autorizacao, numa transacao, e SO se financeiro.parcela_historica estiver vazia (senao o registro das parcelas
-- historicas se perde: conferir antes).
begin;

do $$
begin
    if exists (select 1 from financeiro.parcela_historica) then
        raise exception 'financeiro.parcela_historica tem registros: reversao interrompida';
    end if;
end
$$;

drop function financeiro.simular_quitacao(integer, integer, jsonb);
drop function financeiro.ajustar_saldo_devedor(integer, integer, jsonb, uuid);
drop function financeiro.atualizar_financiamento(integer, integer, jsonb, uuid);
drop function financeiro.adicionar_vigencia_seguro(integer, integer, jsonb, uuid);
drop function financeiro.fin_criar_vigencia(public.financiamento, date, numeric, text);
drop function financeiro.fin_recalcular_seguro(integer, date);
drop function financeiro.fin_campo_alterado(text, jsonb, jsonb);
drop function financeiro.excluir_financiamento(integer, integer);
drop function financeiro.registrar_amortizacao_extra(integer, integer, jsonb, uuid);
drop function financeiro.registrar_parcelas_historicas(integer, integer, jsonb, uuid);
drop function financeiro.regenerar_parcelas_financiamento(integer, integer);
drop function financeiro.criar_financiamento(integer, jsonb, uuid);
drop function financeiro.fin_data(text, text);
drop function financeiro.fin_numero(text, text);
drop function financeiro.fin_competencia(text);
drop function financeiro.fin_possui_execucao(integer);
drop function financeiro.travar_financiamento(integer, integer);
drop function financeiro.exigir_escrita_financiamento(integer);
drop function financeiro.fin_atualizar_sac_tr(public.financiamento, integer[], numeric, numeric);
drop function financeiro.fin_ajustar_padrao(public.financiamento, integer[], numeric);
drop function financeiro.fin_amortizar_padrao(public.financiamento, integer[], numeric, text);
drop function financeiro.fin_gerar(public.financiamento, jsonb);
drop function financeiro.fin_gerar_padrao(public.financiamento, jsonb);
drop function financeiro.fin_indexador(text, date);
drop function financeiro.fin_taxa_mensal(numeric, text);
drop function financeiro.fin_pow_int(numeric, integer);
drop function financeiro.fin_gerar_sac_tr(public.financiamento, jsonb);
drop function financeiro.fin_gravar_despesa(public.financiamento, integer);
drop function financeiro.fin_parcela_elegivel(integer);
drop function financeiro.fin_conta_da_parcela(integer);
drop function financeiro.fin_seguro(jsonb, date, numeric, numeric);
drop function financeiro.fin_config(public.financiamento);
drop function financeiro.fin_tr(date);
drop function financeiro.fin_usa_sac_tr(text, text, text);
drop function financeiro.fin_div(numeric, numeric);
drop function financeiro.fin_r(numeric);
drop table financeiro.parcela_historica;
drop function financeiro.proteger_parcela_historica();

-- saldo_devedor_pelas_parcelas volta a definicao de 20261120090000.
create or replace function financeiro.saldo_devedor_pelas_parcelas(p_financiamento_id integer)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce((select p.saldo_devedor_apos_pagamento from public.financiamento_parcela p
                      where p.financiamento_id = p_financiamento_id and p.status = 'pago'
                      order by p.numero_parcela desc, p.id desc limit 1),
                    (select f.valor_financiado from public.financiamento f where f.id = p_financiamento_id))
$$;
drop index public.conta_financiamento_parcela_unica;
drop index public.financiamento_parcela_numero_unico;

commit;
