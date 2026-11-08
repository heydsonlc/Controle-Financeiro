-- FIN-MOB-ABAST-LANCAMENTOS-01: abastecimento no formulario de Novo Lancamento. So funcoes novas: nenhuma tabela, coluna
-- ou valor muda. Reaproveitam as do MVP-MOB-01 e do escritor unico, sem repetir regra de hodometro, combustivel ou litros:
--
-- - formulario_abastecimento_lancamento: a categoria Combustivel pelo codigo estavel (MOB_COMBUSTIVEL, a mesma que a
--   Mobilidade usa) e os veiculos do perfil.
-- - abastecimento_do_lancamento: o abastecimento vinculado a uma compra ou conta e os ja registrados que podem ser ela.
-- - salvar_lancamento_abastecimento: numa so transacao, a despesa (compra a vista ou despesa direta, nova ou ja lancada) e o
--   seu registro operacional, vinculados. Uma despesa, um abastecimento: o abastecimento nunca e outra despesa. Se qualquer
--   parte falha, nada e gravado; repetir com a mesma chave devolve o resultado gravado.

-- =====================================================================================================================
-- 1. Leituras do formulario
-- =====================================================================================================================
create function financeiro.formulario_abastecimento_lancamento(p_perfil_id integer)
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
    return jsonb_build_object(
        'categoria_combustivel_id', financeiro.mob_categoria_evento('COMBUSTIVEL'),
        'veiculos', coalesce((
            select jsonb_agg(jsonb_build_object('id', v.id, 'nome', v.nome, 'combustivel', lower(btrim(coalesce(v.combustivel, ''))),
                                                'situacao_uso', financeiro.mob_situacao_uso(v), 'ultimo_hodometro', u.hodometro_km)
                             order by v.nome, v.id)
              from public.veiculo v
              left join lateral (select a.hodometro_km from financeiro.abastecimento a
                                  where a.veiculo_id = v.id and a.anulado_em is null
                                  order by a.data_abastecimento desc, a.hodometro_km desc, a.id desc limit 1) u on true
             where financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)
               and lower(btrim(coalesce(v.combustivel, ''))) <> 'eletrico'), '[]'::jsonb));
end
$$;

create function financeiro.abastecimento_do_lancamento(p_perfil_id integer, p_lancamento_id integer, p_conta_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    a       financeiro.abastecimento;
    v_valor numeric;
    v_data  date;
    v_cart  integer;
    v_cat   integer;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if (p_lancamento_id is null) = (p_conta_id is null) then
        raise exception 'Informe a compra ou a conta' using errcode = '22023';
    end if;
    if p_lancamento_id is not null then
        select l.valor, l.data_compra, l.cartao_id, l.categoria_id into v_valor, v_data, v_cart, v_cat from public.lancamento_agregado l
         where l.id = p_lancamento_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id);
    else
        select c.valor, c.data_vencimento, (select i.categoria_id from public.item_despesa i where i.id = c.item_despesa_id)
          into v_valor, v_data, v_cat from public.conta c
         where c.id = p_conta_id and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and not coalesce(c.is_fatura_cartao, false);
    end if;
    if v_valor is null then
        raise exception 'Despesa não encontrada neste perfil' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    select * into a from financeiro.abastecimento x
     where (p_lancamento_id is not null and x.lancamento_id = p_lancamento_id) or (p_conta_id is not null and x.conta_id = p_conta_id);
    return jsonb_build_object(
        'categoria_id', v_cat,  -- a lista de compras da tela nao traz a categoria (a edicao a completa)
        'abastecimento', case when a.id is not null then financeiro.mob_abastecimento_flask(a)
                                  || jsonb_build_object('veiculo_nome', (select v.nome from public.veiculo v where v.id = a.veiculo_id)) end,
        -- registros de Mobilidade ainda sem despesa que podem ser esta (mesmo valor, de 3 dias antes a 10 depois)
        'candidatos', case when a.id is null then coalesce((
            select jsonb_agg(financeiro.mob_abastecimento_flask(x) || jsonb_build_object('veiculo_nome', v.nome)
                             order by abs(x.data_abastecimento - v_data), x.id)
              from financeiro.abastecimento x join public.veiculo v on v.id = x.veiculo_id
             where financeiro.pertence_ao_perfil(x.perfil_financeiro_id, p_perfil_id) and x.anulado_em is null
               and x.lancamento_id is null and x.conta_id is null and x.valor_total = v_valor
               and v_data between x.data_abastecimento - 3 and x.data_abastecimento + 10
               and (p_lancamento_id is null or coalesce(x.meio_pagamento, 'cartao') = 'cartao')
               and (p_lancamento_id is null or x.cartao_id is null or x.cartao_id = v_cart)
               and (p_conta_id is null or coalesce(x.meio_pagamento, '') <> 'cartao')), '[]'::jsonb) else '[]'::jsonb end);
end
$$;

-- =====================================================================================================================
-- 2. Despesa e abastecimento numa so operacao
-- =====================================================================================================================
-- p_dados: {lancamento: {tipo, dados, id, versao}, abastecimento: {id | veiculo_id, combustivel, hodometro_km, preco_litro,
-- cartao_vinculado_id, meio_pagamento, observacoes}}. tipo: compra (criar_compra, a vista), despesa (criar_despesa),
-- compra_existente (id) ou despesa_existente (id; dados e versao opcionais: editar_despesa). Valor, data, cartao e
-- estabelecimento do abastecimento vem da despesa. abastecimento.id reaproveita um registro de Mobilidade.
create function financeiro.salvar_lancamento_abastecimento(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep    jsonb;
    v_l      jsonb := case when jsonb_typeof(p_dados -> 'lancamento') = 'object' then p_dados -> 'lancamento' end;
    v_a      jsonb := case when jsonb_typeof(p_dados -> 'abastecimento') = 'object' then p_dados -> 'abastecimento' else '{}'::jsonb end;
    v_tipo   text;
    v_d      jsonb;
    v_ab_id  integer;
    v_fis    integer;
    v_lanc   integer;
    v_conta  integer;
    v_valor  numeric;
    v_data   date;
    v_cart   integer;
    v_meio   text;
    v_desc   text;
    v_ab     jsonb;
    v_r      jsonb;
    v_compra jsonb;
    v_reuso  boolean := false;
    v_atual  financeiro.abastecimento;
    v_comp   public.lancamento_agregado;
    v_ct     public.conta;
    v_novo   financeiro.abastecimento;
    v_vinc   jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_rep := financeiro.repeticao_mobilidade(p_chave, p_perfil_id, 'salvar_lancamento_abastecimento');
    if v_rep is not null then
        return v_rep;
    end if;
    v_tipo := v_l ->> 'tipo';
    if v_tipo is null or v_tipo not in ('compra', 'despesa', 'compra_existente', 'despesa_existente') then
        raise exception 'Dados do lançamento inválidos' using errcode = '22023';
    end if;
    v_d := case when jsonb_typeof(v_l -> 'dados') = 'object' then v_l -> 'dados' end;
    v_ab_id := nullif(financeiro.mob_inteiro(v_a -> 'id'), 0);
    v_fis := nullif(financeiro.mob_inteiro(v_a -> 'cartao_vinculado_id'), 0);

    -- 1. O que o abastecimento herda da despesa (valor, data, cartao, estabelecimento)
    if v_tipo in ('compra', 'despesa') and v_d is null then
        raise exception 'Dados do lançamento inválidos' using errcode = '22023';
    end if;
    if v_tipo = 'compra' then
        if coalesce(financeiro.mob_inteiro(v_d -> 'total_parcelas'), 1) <> 1 then
            raise exception 'Abastecimento é registrado com compra à vista (1 parcela). Lance a compra parcelada sem os dados do abastecimento. Nada foi gravado.'
                using errcode = '22023', hint = 'ABASTECIMENTO_PARCELADO';
        end if;
        v_valor := financeiro.numero_seguro(v_d -> 'valor');
        v_data := financeiro.mob_data(v_d ->> 'data_compra');
        v_cart := financeiro.mob_inteiro(v_d -> 'cartao_id');
        v_meio := 'cartao';
        v_desc := v_d ->> 'descricao';
    elsif v_tipo = 'despesa' then
        v_valor := financeiro.numero_seguro(v_d -> 'valor');
        v_data := financeiro.mob_data(v_d ->> 'data_vencimento');
        v_desc := v_d ->> 'nome';
    elsif v_tipo = 'compra_existente' then
        select * into v_comp from public.lancamento_agregado l
         where l.id = financeiro.mob_inteiro(v_l -> 'id') and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id) for update;
        if not found then
            raise exception 'Compra não encontrada neste perfil' using errcode = '22023', hint = 'NAO_ENCONTRADA';
        end if;
        if coalesce(v_comp.total_parcelas, 1) <> 1 then
            raise exception 'Abastecimento é registrado com compra à vista (1 parcela). Nada foi gravado.' using errcode = '22023', hint = 'ABASTECIMENTO_PARCELADO';
        end if;
        v_lanc := v_comp.id;
        v_valor := v_comp.valor;
        v_data := v_comp.data_compra;
        v_cart := v_comp.cartao_id;
        v_meio := 'cartao';
        v_desc := coalesce(nullif(v_comp.descricao_exibida, ''), v_comp.descricao);
        v_fis := coalesce(v_fis, v_comp.cartao_vinculado_id);
    else
        select * into v_ct from public.conta c
         where c.id = financeiro.mob_inteiro(v_l -> 'id') and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
           and not coalesce(c.is_fatura_cartao, false) and c.status_pagamento is distinct from 'Substituida' for update;
        if not found then
            raise exception 'Despesa não encontrada neste perfil' using errcode = '22023', hint = 'NAO_ENCONTRADA';
        end if;
        v_conta := v_ct.id;
        v_valor := coalesce(financeiro.numero_seguro(v_d -> 'valor'), v_ct.valor);
        v_data := coalesce(financeiro.mob_data(v_d ->> 'data_vencimento'), v_ct.data_vencimento);
        v_desc := coalesce(nullif(v_d ->> 'nome', ''), v_ct.descricao);
    end if;
    if v_meio is null then
        v_meio := nullif(lower(btrim(coalesce(v_a ->> 'meio_pagamento', ''))), '');
        if v_meio = 'cartao' then
            raise exception 'Despesa direta não é compra no cartão: lance pelo tipo Cartão de crédito' using errcode = '22023';
        end if;
    end if;
    v_ab := (v_a - 'id' - 'valor_total' - 'data_abastecimento' - 'cartao_id' - 'cartao_vinculado_id' - 'meio_pagamento' - 'lancamento_id' - 'conta_id')
            || jsonb_strip_nulls(jsonb_build_object('valor_total', v_valor, 'data_abastecimento', v_data, 'cartao_id', v_cart,
                                                    'cartao_vinculado_id', v_fis, 'meio_pagamento', v_meio,
                                                    'estabelecimento', coalesce(nullif(btrim(coalesce(v_a ->> 'estabelecimento', '')), ''), left(v_desc, 120))));

    -- 2. Antes de qualquer despesa, os dados do abastecimento com as regras de sempre (hodometro, combustivel, cartao)
    if v_ab_id is null then
        perform financeiro.mob_dados_abastecimento(p_perfil_id, v_ab);
    end if;

    -- 3. A despesa
    if v_tipo = 'compra' then
        v_compra := financeiro.criar_compra(p_perfil_id, v_d, extensions.uuid_generate_v5(p_chave, 'compra'));
        v_lanc := (v_compra -> 'lancamentos' ->> 0)::integer;
        if v_fis is not null then
            -- o cartao fisico da compra (o mesmo do abastecimento); o gatilho confere que e do mesmo contrato
            update public.lancamento_agregado set cartao_vinculado_id = v_fis where id = v_lanc;
        end if;
    elsif v_tipo = 'despesa' then
        v_r := financeiro.criar_despesa(p_perfil_id, v_d, extensions.uuid_generate_v5(p_chave, 'despesa'));
        v_conta := (v_r ->> 'conta_id')::integer;
    end if;

    -- 4. O abastecimento, vinculado
    v_vinc := case when v_lanc is not null then jsonb_build_object('lancamento_id', v_lanc) else jsonb_build_object('conta_id', v_conta) end;
    select * into v_atual from financeiro.abastecimento x
     where (v_lanc is not null and x.lancamento_id = v_lanc) or (v_conta is not null and x.conta_id = v_conta);
    if found then
        -- edicao: o mesmo abastecimento acompanha a despesa (valor, data e dados operacionais), com o historico
        if v_ab_id is distinct from v_atual.id then
            raise exception 'Esta despesa já tem um abastecimento vinculado. Nada foi gravado.' using errcode = '22023', hint = 'DESPESA_JA_VINCULADA';
        end if;
        perform financeiro.desvincular_abastecimento(p_perfil_id, v_atual.id);
        if v_tipo = 'despesa_existente' and v_d is not null then
            perform financeiro.editar_despesa(p_perfil_id, v_conta, v_l ->> 'versao', v_d);
        end if;
        perform financeiro.corrigir_abastecimento(p_perfil_id, v_atual.id,
            v_ab || jsonb_build_object('motivo', 'Ajuste pelo formulário de Lançamentos'));
        perform financeiro.vincular_abastecimento(p_perfil_id, v_atual.id, v_vinc);
    else
        if v_tipo = 'despesa_existente' and v_d is not null then
            perform financeiro.editar_despesa(p_perfil_id, v_conta, v_l ->> 'versao', v_d);
        end if;
        if v_ab_id is null then
            -- o mesmo abastecimento ja registrado em Mobilidade, ainda sem despesa, e reaproveitado (nao ha dois registros)
            select x.id into v_ab_id from financeiro.abastecimento x
             where x.veiculo_id = financeiro.mob_inteiro(v_ab -> 'veiculo_id') and x.anulado_em is null
               and x.lancamento_id is null and x.conta_id is null
               and x.data_abastecimento = v_data and x.valor_total = v_valor
               and x.hodometro_km = round(financeiro.numero_seguro(v_ab -> 'hodometro_km'), 1)
             order by x.id limit 1;
            v_reuso := v_ab_id is not null;
        else
            v_reuso := true;
        end if;
        if v_ab_id is null then
            v_r := financeiro.registrar_abastecimento(p_perfil_id, v_ab, extensions.uuid_generate_v5(p_chave, 'abastecimento'));
            v_ab_id := (v_r -> 'abastecimento' ->> 'id')::integer;
        end if;
        perform financeiro.vincular_abastecimento(p_perfil_id, v_ab_id, v_vinc);
    end if;
    select * into v_novo from financeiro.abastecimento x where x.id = v_ab_id;
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'salvar_lancamento_abastecimento', jsonb_build_object(
        'lancamento_id', v_lanc, 'conta_id', v_conta, 'reaproveitado', v_reuso,
        'abastecimento', financeiro.mob_abastecimento_flask(v_novo), 'compra', v_compra));
end
$$;

revoke execute on function financeiro.formulario_abastecimento_lancamento(integer) from public, anon;
grant execute on function financeiro.formulario_abastecimento_lancamento(integer) to authenticated;
revoke execute on function financeiro.abastecimento_do_lancamento(integer, integer, integer) from public, anon;
grant execute on function financeiro.abastecimento_do_lancamento(integer, integer, integer) to authenticated;
revoke execute on function financeiro.salvar_lancamento_abastecimento(integer, jsonb, uuid) from public, anon;
grant execute on function financeiro.salvar_lancamento_abastecimento(integer, jsonb, uuid) to authenticated;
