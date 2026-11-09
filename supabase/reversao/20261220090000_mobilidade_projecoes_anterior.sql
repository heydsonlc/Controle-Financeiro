-- Reversao de 20261220090000 (FIN-MVP-MOB-02): volta as funcoes ao texto anterior e remove os itens de projecao e o historico.
-- As colunas do veiculo ja espelham os itens anuais, entao o gerador antigo volta a produzir as mesmas ocorrencias. Recusada com
-- item que o formulario antigo nao representa (tipo novo, outra frequencia, termino, combustivel desativado) ou com ocorrencia
-- de item novo (a informacao se perderia). So com autorizacao, retirando a versao de supabase_migrations.schema_migrations.
do $$
begin
    if exists (select 1 from financeiro.veiculo_projecao p
                where p.tipo not in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO')
                   or (p.tipo = 'COMBUSTIVEL' and not p.ativo)
                   or (p.tipo <> 'COMBUSTIVEL' and (p.frequencia <> 'ANUAL' or p.data_fim is not null))) then
        raise exception 'Ha projecoes que o formulario antigo nao representa: a reversao perderia esses itens';
    end if;
    if exists (select 1 from public.despesa_prevista d where d.obrigacao like 'PROJ:%') then
        raise exception 'Ha ocorrencias de itens novos de projecao: a reversao perderia a identidade delas';
    end if;
end
$$;

-- mob_gerar_projecoes: texto de 20261215090000.
create or replace function financeiro.mob_gerar_projecoes(p_perfil_id integer, p_veiculo_id integer, p_meses integer)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_v         public.veiculo;
    v_hoje      date := financeiro.hoje_brasilia();
    v_meses     integer := greatest(coalesce(p_meses, 12), 1);
    v_inicio    date;
    v_fim       date;
    v_perfil    integer;
    v_bloq      text[] := '{}';
    v_d         record;
    v_ref       date;
    v_mantidas  integer[] := '{}';
    v_evento    record;
    v_ano       integer;
begin
    select * into v_v from public.veiculo where id = p_veiculo_id;
    v_inicio := date_trunc('month', greatest(coalesce(v_v.data_inicio, v_hoje), v_hoje))::date;
    v_fim := (v_inicio + make_interval(months => v_meses))::date;
    v_perfil := coalesce(v_v.perfil_financeiro_id, p_perfil_id);

    -- FIN-MVP-MOB-01: competencia em que o usuario ja agiu nao volta. A identidade e a obrigacao + o periodo (mes do combustivel,
    -- ano das anuais), em qualquer data, para mudar o mes do vencimento nao recriar o que ja foi confirmado.
    for v_d in select d.*, financeiro.mob_tipo_evento(d.metadata) tipo from public.despesa_prevista d
                where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                  and d.origem_tipo = 'VEICULO' and d.origem_id = v_v.id
                  and d.status is not null and d.status <> 'PREVISTA'
    loop
        continue when v_d.tipo is null or v_d.tipo not in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO');
        v_bloq := v_bloq || (v_d.tipo || '|' || financeiro.mob_periodo(v_d.tipo, coalesce(v_d.data_original_prevista, v_d.data_prevista)));
        v_bloq := v_bloq || (v_d.tipo || '@' || coalesce(v_d.data_atual_prevista, v_d.data_prevista));
    end loop;

    if coalesce(v_v.combustivel_valor_mensal, 0) > 0 then
        v_ref := v_inicio;
        while v_ref < v_fim loop
            if not (('COMBUSTIVEL|' || v_ref) = any (v_bloq) or ('COMBUSTIVEL@' || v_ref) = any (v_bloq)) then
                v_mantidas := v_mantidas || financeiro.mob_planejar_prevista(v_perfil, p_perfil_id, v_v.id, 'COMBUSTIVEL', v_ref, v_v.combustivel_valor_mensal);
            end if;
            v_ref := (v_ref + interval '1 month')::date;
        end loop;
    end if;

    for v_evento in select * from (values ('IPVA', v_v.ipva_mes, v_v.ipva_valor, 1),
                                          ('SEGURO', v_v.seguro_mes, v_v.seguro_valor, 2),
                                          ('LICENCIAMENTO', v_v.licenciamento_mes, v_v.licenciamento_valor, 3)) e(tipo, mes, valor, ordem)
                     order by ordem
    loop
        continue when not (coalesce(v_evento.mes, 0) between 1 and 12 and coalesce(v_evento.valor, 0) > 0);
        for v_ano in extract(year from v_inicio)::integer .. extract(year from (v_fim - 1))::integer loop
            v_ref := make_date(v_ano, v_evento.mes, 1);
            continue when v_ref < v_inicio or v_ref >= v_fim
                or ((v_evento.tipo || '|' || financeiro.mob_periodo(v_evento.tipo, v_ref)) = any (v_bloq))
                or ((v_evento.tipo || '@' || v_ref) = any (v_bloq));
            v_mantidas := v_mantidas || financeiro.mob_planejar_prevista(v_perfil, p_perfil_id, v_v.id, v_evento.tipo, v_ref, v_evento.valor);
        end loop;
    end loop;

    -- O que deixou de ser projetado na janela sai; o resto fica com o mesmo id.
    delete from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.origem_tipo = 'VEICULO' and d.origem_id = v_v.id and d.status = 'PREVISTA'
       and d.data_prevista >= v_inicio and d.data_prevista < v_fim
       and financeiro.mob_tipo_evento(d.metadata) in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO')
       and not (d.id = any (v_mantidas));
    perform financeiro.mob_suprimir_combustivel(p_perfil_id, v_v.id);
    return cardinality(v_mantidas);
end
$$;

-- veiculo_flask: texto de 20261215090000.
create or replace function financeiro.veiculo_flask(p_v public.veiculo)
    returns jsonb
    language sql
    stable
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_v.id, 'perfil_financeiro_id', p_v.perfil_financeiro_id, 'nome', p_v.nome, 'tipo', p_v.tipo,
        'combustivel', p_v.combustivel, 'autonomia_km_l', p_v.autonomia_km_l, 'status', p_v.status,
        'data_inicio', p_v.data_inicio,
        'projecao_combustivel', jsonb_build_object('categoria_id', p_v.categoria_combustivel_id,
                                                   'valor_mensal', nullif(p_v.combustivel_valor_mensal, 0)),
        'preco_medio_combustivel', nullif(p_v.preco_medio_combustivel, 0),
        'uso_estimado', jsonb_build_object('km_estimado_acumulado', coalesce(p_v.km_estimado_acumulado, 0),
                                           'km_estimado_ultimo_calculo_em', financeiro.iso_python(p_v.km_estimado_ultimo_calculo_em)),
        'ipva', jsonb_build_object('categoria_id', p_v.ipva_categoria_id, 'mes', p_v.ipva_mes, 'valor', nullif(p_v.ipva_valor, 0)),
        'seguro', jsonb_build_object('categoria_id', p_v.seguro_categoria_id, 'mes', p_v.seguro_mes, 'valor', nullif(p_v.seguro_valor, 0)),
        'licenciamento', jsonb_build_object('categoria_id', p_v.licenciamento_categoria_id, 'mes', p_v.licenciamento_mes,
                                            'valor', nullif(p_v.licenciamento_valor, 0)),
        'criado_em', financeiro.iso_python(p_v.criado_em), 'atualizado_em', financeiro.iso_python(p_v.atualizado_em),
        'resumo_mensal_estimado', jsonb_build_object(
            'combustivel_mensal', c.comb, 'seguro_mensal_diluido', c.seg, 'ipva_mensal_diluido', c.ipva,
            'licenciamento_mensal_diluido', c.lic, 'manutencao_mensal_media', 0, 'assinatura_mensal', 0,
            'transporte_app_mensal', 0, 'outros_custos_mensais', 0),
        'total_mensal_estimado', c.comb + c.seg + c.ipva + c.lic)
        -- FIN-MVP-MOB-01: so nos veiculos que usam os campos novos (os demais respondem como antes)
        || case when (p_v).combustivel = 'flex' or (p_v).custo_combustivel_modo <> 'MANUAL' or (p_v).km_mensal_estimado is not null
                then jsonb_build_object('autonomia_gasolina_km_l', (p_v).autonomia_gasolina_km_l,
                                        'autonomia_etanol_km_l', (p_v).autonomia_etanol_km_l,
                                        'preco_gasolina', (p_v).preco_gasolina, 'preco_etanol', (p_v).preco_etanol,
                                        'combustivel_referencia', (p_v).combustivel_referencia,
                                        'km_mensal_estimado', (p_v).km_mensal_estimado,
                                        'custo_combustivel_modo', (p_v).custo_combustivel_modo)
                else '{}'::jsonb end
        -- FIN-MVP-MOB-01: ultima leitura real do hodometro, quando ha
        || coalesce((select jsonb_build_object('km_real', a.hodometro_km, 'km_real_data', a.data_abastecimento)
                       from financeiro.abastecimento a where a.veiculo_id = (p_v).id and a.anulado_em is null
                      order by a.data_abastecimento desc, a.hodometro_km desc, a.id desc limit 1), '{}'::jsonb)
        || case when (p_v).em_uso_paralelo then jsonb_build_object('em_uso_paralelo', true) else '{}'::jsonb end
      from (select round(coalesce((p_v).combustivel_valor_mensal, 0), 2) comb,
                   round(coalesce((p_v).seguro_valor, 0) / 12, 2) seg,
                   round(coalesce((p_v).ipva_valor, 0) / 12, 2) ipva,
                   round(coalesce((p_v).licenciamento_valor, 0) / 12, 2) lic) c
$$;

-- criar_veiculo: texto de 20261215090000.
create or replace function financeiro.criar_veiculo(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep jsonb;
    v     public.veiculo;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_rep := financeiro.repeticao_mobilidade(p_chave, p_perfil_id, 'criar_veiculo');
    if v_rep is not null then
        return v_rep;
    end if;
    v := financeiro.mob_dados_veiculo(null::public.veiculo, coalesce(p_dados, '{}'::jsonb));
    insert into public.veiculo (perfil_financeiro_id, nome, tipo, combustivel, autonomia_km_l, status, data_inicio,
                                combustivel_valor_mensal, ipva_mes, ipva_valor, seguro_mes, seguro_valor, licenciamento_mes,
                                licenciamento_valor, preco_medio_combustivel, km_estimado_acumulado, criado_em, atualizado_em,
                                autonomia_gasolina_km_l, autonomia_etanol_km_l, preco_gasolina, preco_etanol,
                                combustivel_referencia, km_mensal_estimado, custo_combustivel_modo, em_uso_paralelo)
    values (p_perfil_id, v.nome, v.tipo, v.combustivel, v.autonomia_km_l, v.status, v.data_inicio,
            v.combustivel_valor_mensal, v.ipva_mes, v.ipva_valor, v.seguro_mes, v.seguro_valor, v.licenciamento_mes,
            v.licenciamento_valor, v.preco_medio_combustivel, 0, financeiro.mob_agora(), financeiro.mob_agora(),
            v.autonomia_gasolina_km_l, v.autonomia_etanol_km_l, v.preco_gasolina, v.preco_etanol,
            v.combustivel_referencia, v.km_mensal_estimado, v.custo_combustivel_modo, v.em_uso_paralelo)
    returning id into v.id;
    perform financeiro.mob_aplicar_categorias(v.id);
    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'criar_veiculo',
        jsonb_build_object('veiculo_id', v.id));
end
$$;

-- editar_veiculo: texto de 20261215090000.
create or replace function financeiro.editar_veiculo(p_perfil_id integer, p_veiculo_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v       public.veiculo;
    v_antes public.veiculo;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_antes := financeiro.mob_veiculo(p_perfil_id, p_veiculo_id);
    v := financeiro.mob_dados_veiculo(v_antes, coalesce(p_dados, '{}'::jsonb));
    update public.veiculo
       set nome = v.nome, tipo = v.tipo, combustivel = v.combustivel, autonomia_km_l = v.autonomia_km_l,
           status = v.status, data_inicio = v.data_inicio, combustivel_valor_mensal = v.combustivel_valor_mensal,
           ipva_mes = v.ipva_mes, ipva_valor = v.ipva_valor, seguro_mes = v.seguro_mes, seguro_valor = v.seguro_valor,
           licenciamento_mes = v.licenciamento_mes, licenciamento_valor = v.licenciamento_valor,
           preco_medio_combustivel = v.preco_medio_combustivel, atualizado_em = financeiro.mob_agora(),
           autonomia_gasolina_km_l = v.autonomia_gasolina_km_l, autonomia_etanol_km_l = v.autonomia_etanol_km_l,
           preco_gasolina = v.preco_gasolina, preco_etanol = v.preco_etanol, combustivel_referencia = v.combustivel_referencia,
           km_mensal_estimado = v.km_mensal_estimado, custo_combustivel_modo = v.custo_combustivel_modo,
           em_uso_paralelo = v.em_uso_paralelo
     where id = v.id;
    perform financeiro.mob_aplicar_categorias(v.id);
    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    -- FIN-MVP-MOB-01: o custo novo vale para a recorrencia e so para as ocorrencias futuras elegiveis
    if v.combustivel_valor_mensal is distinct from v_antes.combustivel_valor_mensal and coalesce(v.combustivel_valor_mensal, 0) > 0 then
        perform financeiro.mob_sincronizar_combustivel(p_perfil_id, v.id, v.combustivel_valor_mensal);
    end if;
    -- FIN-MVP-MOB-01: deixou de estar em uso sem ser o cenario: a recorrencia se encerra, como na troca. As contas ja lancadas ficam.
    if v_antes.em_uso_paralelo and not v.em_uso_paralelo and financeiro.mob_situacao_uso(v) <> 'CENARIO' then
        update public.item_despesa i set ativo = false
         where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.origem_tipo = 'VEICULO' and i.origem_id = v.id
           and i.recorrente and i.ativo;
        perform financeiro.mob_restaurar_combustivel(p_perfil_id, v.id);
    end if;
    return jsonb_build_object('veiculo_id', v.id);
end
$$;

-- excluir_veiculo: texto de 20261215090000.
create or replace function financeiro.excluir_veiculo(p_perfil_id integer, p_veiculo_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v public.veiculo;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v := financeiro.mob_veiculo(p_perfil_id, p_veiculo_id);
    if exists (select 1 from public.mobilidade_cenario_ativo c
                where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                  and c.status = 'ATIVO' and c.tipo_modalidade = 'VEICULO' and c.origem_id = v.id) then
        raise exception 'Este veículo é a modalidade de mobilidade ativa. Ative outra modalidade antes de excluir. Nada foi excluído.'
            using errcode = '22023', hint = 'EM_USO';
    end if;
    if exists (select 1 from public.despesa_prevista d
                where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                  and d.origem_tipo = 'VEICULO' and d.origem_id = v.id
                  and (d.status in ('CONFIRMADA', 'ADIADA')
                       or exists (select 1 from public.despesa_prevista_acao_log l
                                   where l.despesa_prevista_id = d.id or l.despesa_prevista_criada_id = d.id))) then
        raise exception 'O veículo tem despesas previstas já confirmadas ou adiadas (histórico). Nada foi excluído.'
            using errcode = '22023', hint = 'COM_HISTORICO';
    end if;
    if exists (select 1 from financeiro.abastecimento a where a.veiculo_id = v.id) then  -- FIN-MVP-MOB-01
        raise exception 'O veículo tem abastecimentos registrados (histórico). Nada foi excluído.'
            using errcode = '22023', hint = 'COM_HISTORICO';
    end if;
    if (financeiro.mob_item_combustivel(p_perfil_id, v.id)).id is not null then
        raise exception 'O veículo tem recorrência de combustível ativa. Tire o uso paralelo antes de excluir. Nada foi excluído.'
            using errcode = '22023', hint = 'EM_USO';
    end if;
    if exists (select 1 from public.veiculo_financiamento f where f.veiculo_id = v.id)
       or exists (select 1 from public.veiculo_regra_manutencao_km r where r.veiculo_id = v.id)
       or exists (select 1 from public.veiculo_ciclo_manutencao c where c.veiculo_id = v.id) then
        raise exception 'Remova antes o financiamento e as regras de manutenção do veículo. Nada foi excluído.'
            using errcode = '22023', hint = 'COM_VINCULOS';
    end if;
    delete from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
       and d.origem_id = v.id;
    delete from public.veiculo where id = v.id;
    return jsonb_build_object('veiculo_id', v.id, 'excluido', true);
end
$$;

-- mob_rotulo_prevista: texto de 20261127090000.
create or replace function financeiro.mob_rotulo_prevista(p_d public.despesa_prevista)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select coalesce(case upper(coalesce(financeiro.mob_tipo_evento(p_d.metadata), p_d.origem_tipo, ''))
        when 'COMBUSTIVEL' then 'Combustível' when 'IPVA' then 'IPVA' when 'SEGURO' then 'Seguro'
        when 'LICENCIAMENTO' then 'Licenciamento' when 'PARCELA_FINANCIAMENTO' then 'Parcela de financiamento'
        when 'IOF_FINANCIAMENTO' then 'IOF de financiamento' when 'TRANSPORTE_APP' then 'Transporte por app'
        when 'TROCA_OLEO' then 'Troca de óleo' when 'TROCA_PNEUS' then 'Troca de pneus' when 'REVISAO_GERAL' then 'Revisão geral'
        when 'ALINHAMENTO_BALANCEAMENTO' then 'Alinhamento / Balanceamento' end,
        nullif(coalesce(financeiro.mob_tipo_evento(p_d.metadata), p_d.origem_tipo, ''), ''), 'Despesa prevista')
$$;

-- mob_ajustar_ciclo: texto de 20261127090000.
create or replace function financeiro.mob_ajustar_ciclo(p_perfil_id integer, p_d public.despesa_prevista)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_tipo   text := financeiro.mob_tipo_evento(p_d.metadata);
    v_r      public.veiculo_regra_manutencao_km;
    v_v      public.veiculo;
    v_ciclo  public.veiculo_ciclo_manutencao;
    v_md     jsonb := financeiro.json_seguro(p_d.metadata);
    v_ordem  integer;
    v_media  numeric;
    v_meses  integer;
    v_prox   date;
    v_id     integer;
begin
    if p_d.origem_tipo <> 'VEICULO' or v_tipo is null or v_tipo in ('IPVA', 'SEGURO', 'LICENCIAMENTO', 'COMBUSTIVEL') then
        return jsonb_build_object('ciclo_id', null, 'criada', null);
    end if;
    select * into v_r from public.veiculo_regra_manutencao_km r
     where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id) and r.veiculo_id = p_d.origem_id
       and r.tipo_evento = v_tipo and r.ativo order by r.id limit 1;
    if not found then
        return jsonb_build_object('ciclo_id', null, 'criada', null);
    end if;
    v_v := financeiro.veiculo_do_perfil(p_perfil_id, p_d.origem_id);
    if v_v.id is null then
        return jsonb_build_object('ciclo_id', null, 'criada', null);
    end if;
    select * into v_ciclo from public.veiculo_ciclo_manutencao c
     where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and c.veiculo_id = v_v.id and c.tipo_evento = v_tipo
     order by c.id limit 1;
    if not found then
        insert into public.veiculo_ciclo_manutencao (perfil_financeiro_id, veiculo_id, tipo_evento, regra_id, intervalo_km, criado_em)
        values (coalesce(v_r.perfil_financeiro_id, p_perfil_id), v_v.id, v_tipo, v_r.id, v_r.intervalo_km, financeiro.mob_agora())
        returning * into v_ciclo;
    end if;
    if jsonb_typeof(v_md) <> 'object' then
        v_md := '{}'::jsonb;
    end if;
    if coalesce((v_md ->> 'ciclo_id'), '') in ('', '0') then
        v_md := v_md || jsonb_build_object('ciclo_id', v_ciclo.id);
    end if;
    if coalesce((v_md ->> 'ordem_no_ciclo'), '') in ('', '0') then
        select coalesce(max(financeiro.mob_inteiro(financeiro.json_seguro(d.metadata) -> 'ordem_no_ciclo')), 0) into v_ordem
          from public.despesa_prevista d
         where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
           and d.status in ('PREVISTA', 'ADIADA', 'CONFIRMADA', 'IGNORADA')
           and financeiro.mob_inteiro(financeiro.json_seguro(d.metadata) -> 'ciclo_id') = v_ciclo.id;
        v_md := v_md || jsonb_build_object('ordem_no_ciclo', case when v_ordem > 0 then v_ordem + 1 else 1 end);
    end if;
    update public.despesa_prevista set metadata = v_md::text where id = p_d.id;

    v_media := (financeiro.uso_do_veiculo(v_v, 3) ->> 'media_movel_km_mes')::numeric;
    if coalesce(v_media, 0) <= 0 or coalesce(v_r.intervalo_km, 0) = 0 then
        return jsonb_build_object('ciclo_id', v_ciclo.id, 'criada', null);
    end if;
    v_meses := ceil(v_r.intervalo_km / v_media)::integer;
    v_prox := date_trunc('month', coalesce(p_d.data_atual_prevista, p_d.data_prevista) + make_interval(months => v_meses))::date;
    if exists (select 1 from public.despesa_prevista d
                where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
                  and d.origem_id = v_v.id and d.status in ('PREVISTA', 'ADIADA', 'CONFIRMADA') and d.data_prevista >= v_prox
                  and d.id <> p_d.id and financeiro.mob_tipo_evento(d.metadata) = v_tipo) then
        return jsonb_build_object('ciclo_id', v_ciclo.id, 'criada', null);
    end if;
    v_id := financeiro.mob_inserir_prevista(coalesce(v_v.perfil_financeiro_id, p_perfil_id), 'VEICULO', v_v.id,
        financeiro.mob_categoria_evento(v_tipo), v_prox, v_r.custo_estimado,
        jsonb_build_object('tipo_evento', v_tipo, 'ciclo_id', v_ciclo.id,
                           'ordem_no_ciclo', (v_md ->> 'ordem_no_ciclo')::integer + 1, 'intervalo_km', v_r.intervalo_km));
    return jsonb_build_object('ciclo_id', v_ciclo.id, 'criada', v_id);
end
$$;

drop function financeiro.excluir_projecao_veiculo(integer, integer);
drop function financeiro.alternar_projecao_veiculo(integer, integer, boolean);
drop function financeiro.salvar_projecao_veiculo(integer, integer, jsonb, uuid);
drop function financeiro.projecoes_veiculo_tela(integer, integer);
drop function financeiro.mob_dados_projecao(financeiro.veiculo_projecao, public.veiculo, jsonb);
drop function financeiro.mob_projecao_tela(financeiro.veiculo_projecao, public.veiculo);
drop function financeiro.mob_protegidas_projecao(financeiro.veiculo_projecao);
drop function financeiro.mob_projecao(integer, integer);
drop function financeiro.mob_projecoes_dinamicas(integer);
drop function financeiro.mob_projecao_legada(integer, public.veiculo, text, integer, numeric);
drop function financeiro.mob_espelhar_legado(integer);
drop function financeiro.mob_converter_legado(integer, integer);
drop function financeiro.mob_inserir_projecao(financeiro.veiculo_projecao);
drop function financeiro.mob_inicio_anual(public.veiculo, integer);
drop function financeiro.mob_historico_projecao(text, financeiro.veiculo_projecao, financeiro.veiculo_projecao);
drop function financeiro.mob_planejar_projecao(integer, integer, financeiro.veiculo_projecao, date, numeric);
drop function financeiro.mob_datas_projecao(financeiro.veiculo_projecao, date, date);
drop function financeiro.mob_media_mensal_projecao(financeiro.veiculo_projecao, public.veiculo);
drop function financeiro.mob_valor_projecao(financeiro.veiculo_projecao, public.veiculo);
drop function financeiro.mob_rotulo_tipo_projecao(text);
drop function financeiro.mob_periodo_frequencia(text, date);
drop table financeiro.veiculo_projecao_historico;
drop table financeiro.veiculo_projecao;
