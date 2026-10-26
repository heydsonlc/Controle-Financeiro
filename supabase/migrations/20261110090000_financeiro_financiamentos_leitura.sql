-- FIN-FIDELIDADE-CONTRATOS-1 (fase 1) — tela original de Financiamentos do Flask sobre o Supabase, SO LEITURA.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261110090000).
-- Validada em cluster local descartavel (tests/test_supabase_financiamentos_leitura.py).
-- Docs: docs/FIN_FIDELIDADE_CONTRATOS_1.md.
--
-- Lista e detalhe no formato do Flask (routes/financiamentos.py: listar_financiamentos, buscar_financiamento;
-- Financiamento/FinanciamentoParcela.to_dict; _obter_info_vigencia_para_edicao). O calculo (SAC, PRICE, SAC/TR da
-- Caixa, seguros MIP/DFI, indexadores), as amortizacoes, os ajustes de saldo e os pagamentos de parcela continuam no
-- Flask (escritor unico): nada aqui grava. Nenhuma tabela nova; nenhum dado existente e alterado.

-- Financiamento no formato do Flask (to_dict): colunas gravadas, os padroes do to_dict e o saldo devedor atual
-- ("estado soberano" gravado; sem ele, o saldo apos a parcela anterior a primeira pendente). Interna.
create function financeiro.financiamento_flask(p_fin public.financiamento)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select to_jsonb(p_fin) - 'saldo_devedor_atual' || jsonb_build_object(
        'saldo_devedor_atual', coalesce(p_fin.saldo_devedor_atual, (
            select case when pend.numero_parcela > 1
                        then coalesce((select ant.saldo_devedor_apos_pagamento from public.financiamento_parcela ant
                                        where ant.financiamento_id = p_fin.id and ant.numero_parcela = pend.numero_parcela - 1
                                        limit 1), p_fin.valor_financiado)
                        else p_fin.valor_financiado end
              from (select min(p.numero_parcela) as numero_parcela from public.financiamento_parcela p
                     where p.financiamento_id = p_fin.id and p.status = 'pendente') pend)),
        -- 'float(x) if x else None' do to_dict: zero vira null.
        'taxa_juros_efetiva_anual', nullif(p_fin.taxa_juros_efetiva_anual, 0),
        'taxa_juros_efetiva_relacionamento_anual', nullif(p_fin.taxa_juros_efetiva_relacionamento_anual, 0),
        'modo_calculo_financiamento', coalesce(p_fin.modo_calculo_financiamento, 'padrao'),
        'modo_taxa_mensal', coalesce(p_fin.modo_taxa_mensal, 'efetiva_equivalente'),
        'seguro_percentual', coalesce(nullif(p_fin.seguro_percentual, 0), 0.0006),
        'valor_seguro_mensal', coalesce(p_fin.valor_seguro_mensal, 0),
        'seguro_modo', coalesce(p_fin.seguro_modo, 'fixo'),
        'taxa_administracao_fixa', coalesce(p_fin.taxa_administracao_fixa, 0),
        'faixas_mip', coalesce((select jsonb_agg(to_jsonb(fx) order by fx.id) from public.financiamento_seguro_faixa_mip fx
                                 where fx.financiamento_id = p_fin.id), '[]'::jsonb),
        'ultimo_ajuste_saldo', (select to_jsonb(a) from public.financiamento_ajuste_saldo a
                                 where a.financiamento_id = p_fin.id order by a.criado_em desc nulls last, a.id desc limit 1),
        'parcelas_pagas', (select count(*) from public.financiamento_parcela p where p.financiamento_id = p_fin.id and p.status = 'pago'),
        'total_parcelas', (select count(*) from public.financiamento_parcela p where p.financiamento_id = p_fin.id))
$$;

-- vigencia_seguro_info (como _obter_info_vigencia_para_edicao): ultima vigencia ativa e ultima amortizacao. Interna.
create function financeiro.vigencia_seguro_info(p_financiamento_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_vig  public.financiamento_seguro_vigencia;
    v_amor date;
    v_data date;
begin
    select * into v_vig from public.financiamento_seguro_vigencia v
     where v.financiamento_id = p_financiamento_id and v.vigencia_ativa order by v.competencia_inicio desc limit 1;
    select a.data into v_amor from public.financiamento_amortizacao_extra a
     where a.financiamento_id = p_financiamento_id order by a.data desc limit 1;
    if v_vig.id is null then
        return jsonb_build_object('data_sugerida', null, 'valor_sugerido', null, 'observacoes_sugeridas', null,
                                  'mensagem_orientativa', 'Nenhuma vigência de seguro cadastrada. Cadastre a primeira vigência.');
    end if;
    if v_amor is null or v_amor < v_vig.competencia_inicio then
        return jsonb_build_object('data_sugerida', v_vig.competencia_inicio, 'valor_sugerido', v_vig.valor_mensal,
                                  'observacoes_sugeridas', v_vig.observacoes, 'mensagem_orientativa', null);
    end if;
    v_data := (date_trunc('month', v_amor::timestamp) + interval '1 month')::date;
    return jsonb_build_object('data_sugerida', v_data, 'valor_sugerido', null, 'observacoes_sugeridas', null,
                              'mensagem_orientativa', 'Após amortização extraordinária, informe o novo valor do seguro a partir de '
                                                      || to_char(v_data, 'MM/YYYY') || '.');
end
$$;

-- GET /api/financiamentos[?ativo=]: financiamentos do perfil (todos, ou so ativos / inativos).
create function financeiro.financiamentos_tela(p_perfil_id integer, p_ativo boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    -- Ordem do Flask (data do contrato, mais recente primeiro); empate pelo id, do mais novo.
    return coalesce((select jsonb_agg(financeiro.financiamento_flask(f) order by f.data_contrato desc, f.id desc)
                       from public.financiamento f
                      where financeiro.pertence_ao_perfil(f.perfil_financeiro_id, p_perfil_id)
                        and (p_ativo is null or f.ativo = p_ativo)), '[]'::jsonb);
end
$$;

-- GET /api/financiamentos/<id>: financiamento, parcelas em ordem e vigencia_seguro_info.
create function financeiro.financiamento_tela(p_perfil_id integer, p_financiamento_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_fin public.financiamento;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_fin from public.financiamento f where f.id = p_financiamento_id;
    if not found or not financeiro.pertence_ao_perfil(v_fin.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Financiamento nao encontrado neste perfil' using errcode = '22023';
    end if;
    return financeiro.financiamento_flask(v_fin) || jsonb_build_object(
        -- FinanciamentoParcela.to_dict: saldo apos o pagamento zero vira null ('float(x) if x else None').
        'parcelas', coalesce((select jsonb_agg(to_jsonb(p) || jsonb_build_object('saldo_devedor_apos_pagamento',
                                                                                 nullif(p.saldo_devedor_apos_pagamento, 0))
                                               order by p.numero_parcela, p.id) from public.financiamento_parcela p
                               where p.financiamento_id = v_fin.id), '[]'::jsonb),
        'vigencia_seguro_info', financeiro.vigencia_seguro_info(v_fin.id));
end
$$;

revoke execute on function financeiro.financiamento_flask(public.financiamento) from public, anon, authenticated;
revoke execute on function financeiro.vigencia_seguro_info(integer) from public, anon, authenticated;
revoke execute on function financeiro.financiamentos_tela(integer, boolean) from public, anon;
revoke execute on function financeiro.financiamento_tela(integer, integer) from public, anon;
grant execute on function financeiro.financiamentos_tela(integer, boolean) to authenticated;
grant execute on function financeiro.financiamento_tela(integer, integer) to authenticated;
