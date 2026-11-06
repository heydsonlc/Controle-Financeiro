-- Reversao de 20261215090000 (FIN-MVP-MOB-01): volta as funcoes ao texto anterior e remove as colunas novas. Recusada com veiculo Flex,
-- custo calculado ou vinculo gravado (a informacao se perderia). So com autorizacao, retirando a versao de
-- supabase_migrations.schema_migrations.
do $$
begin
    if exists (select 1 from public.veiculo v where v.combustivel = 'flex' or v.custo_combustivel_modo <> 'MANUAL' or v.km_mensal_estimado is not null) then
        raise exception 'Ha veiculo Flex ou com custo calculado: a reversao perderia esses dados';
    end if;
    if exists (select 1 from public.despesa_prevista d where d.conta_id is not null or d.lancamento_id is not null) then
        raise exception 'Ha previstas vinculadas a contas ou compras: a reversao perderia os vinculos';
    end if;
end
$$;

-- As previsoes de combustivel suprimidas por esta versao voltam a contar, como antes dela.
update public.despesa_prevista set status = 'PREVISTA'
 where status = 'SUPRIMIDA' and obrigacao = 'COMBUSTIVEL';

-- veiculo_flask: texto de 20261115090000.
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
      from (select round(coalesce((p_v).combustivel_valor_mensal, 0), 2) comb,
                   round(coalesce((p_v).seguro_valor, 0) / 12, 2) seg,
                   round(coalesce((p_v).ipva_valor, 0) / 12, 2) ipva,
                   round(coalesce((p_v).licenciamento_valor, 0) / 12, 2) lic) c
$$;

-- uso_do_veiculo: texto de 20261115090000.
create or replace function financeiro.uso_do_veiculo(p_v public.veiculo, p_janela integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_janela  integer := least(greatest(coalesce(p_janela, 3), 1), 12);
    v_fim     date := (date_trunc('month', financeiro.hoje_brasilia()) + interval '1 month')::date;
    v_inicio  date;
    v_por_mes jsonb := '{}'::jsonb;
    v_soma    numeric := 0;
    v_d       record;
begin
    v_inicio := (v_fim - make_interval(months => v_janela))::date;
    for v_d in
        select coalesce(d.data_atual_prevista, d.data_prevista) data_ref, md, d.valor_previsto
          from public.despesa_prevista d
          cross join lateral (select financeiro.json_seguro(d.metadata) md) j
         where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_v.perfil_financeiro_id)
           and d.origem_tipo = 'VEICULO' and d.origem_id = p_v.id and d.status = 'CONFIRMADA'
           and d.data_prevista >= v_inicio and d.data_prevista < v_fim
         order by d.id
    loop
        continue when jsonb_typeof(v_d.md) <> 'object' or v_d.md ->> 'tipo_evento' is distinct from 'COMBUSTIVEL';
        declare
            v_litros numeric := financeiro.numero_seguro(v_d.md -> 'litros_abastecidos');
            v_km     numeric;
            v_chave  text := to_char(v_d.data_ref, 'YYYY-MM');
        begin
            if v_litros is null or v_litros <= 0 then
                v_litros := case when coalesce(p_v.preco_medio_combustivel, 0) > 0 and coalesce(v_d.valor_previsto, 0) > 0
                                 then v_d.valor_previsto / p_v.preco_medio_combustivel end;
            end if;
            continue when coalesce(p_v.autonomia_km_l, 0) <= 0 or coalesce(v_litros, 0) <= 0;
            v_km := v_litros * p_v.autonomia_km_l;
            v_por_mes := v_por_mes || jsonb_build_object(v_chave, coalesce((v_por_mes ->> v_chave)::numeric, 0) + v_km);
            v_soma := v_soma + v_km;
        end;
    end loop;
    return jsonb_build_object(
        'veiculo_id', p_v.id, 'km_estimado_acumulado', coalesce(p_v.km_estimado_acumulado, 0),
        'km_estimado_ultimo_calculo_em', financeiro.iso_python(p_v.km_estimado_ultimo_calculo_em),
        'janela_meses', v_janela, 'km_por_mes', v_por_mes, 'media_movel_km_mes', v_soma / v_janela,
        'observacao', 'Estimativa baseada em consumo. Pode variar.',
        'preco_medio_combustivel', nullif(p_v.preco_medio_combustivel, 0), 'autonomia_km_l', nullif(p_v.autonomia_km_l, 0));
end
$$;

-- mob_inserir_prevista: texto de 20261127090000.
create or replace function financeiro.mob_inserir_prevista(p_perfil_id integer, p_origem_tipo text, p_origem_id integer,
                                                 p_categoria_id integer, p_data date, p_valor numeric, p_metadata jsonb)
    returns integer
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista,
                                         data_original_prevista, data_atual_prevista, valor_previsto, status, metadata,
                                         criado_em, atualizado_em)
    values (p_perfil_id, p_origem_tipo, p_origem_id, p_categoria_id, p_data, p_data, p_data, p_valor, 'PREVISTA',
            p_metadata::text, financeiro.mob_agora(), financeiro.mob_agora())
    returning id
$$;

-- mob_dados_veiculo: texto de 20261127090000.
create or replace function financeiro.mob_dados_veiculo(p_atual public.veiculo, p_dados jsonb)
    returns public.veiculo
    language plpgsql
    stable
    set search_path = ''
as $$
declare
    v public.veiculo := p_atual;
    v_novo boolean := p_atual.id is null;
    v_auton numeric;
begin
    if v_novo then
        v.nome := btrim(coalesce(p_dados ->> 'nome', ''));
        v.tipo := btrim(coalesce(p_dados ->> 'tipo', ''));
        v.combustivel := btrim(coalesce(p_dados ->> 'combustivel', ''));
        v.status := upper(btrim(coalesce(nullif(p_dados ->> 'status', ''), 'SIMULADO')));
        v.autonomia_km_l := financeiro.numero_seguro(p_dados -> 'autonomia_km_l');
        v.data_inicio := financeiro.mob_data(p_dados ->> 'data_inicio');
        if v.nome = '' then raise exception 'Nome é obrigatório' using errcode = '22023'; end if;
        if v.tipo = '' then raise exception 'Tipo é obrigatório' using errcode = '22023'; end if;
        if v.combustivel = '' then raise exception 'Combustível é obrigatório' using errcode = '22023'; end if;
        if v.autonomia_km_l is null or v.autonomia_km_l <= 0 then
            raise exception 'autonomia_km_l é obrigatório e deve ser > 0' using errcode = '22023';
        end if;
        if v.status not in ('SIMULADO', 'ATIVO') then
            raise exception 'Status inválido (SIMULADO|ATIVO)' using errcode = '22023';
        end if;
        if v.status = 'ATIVO' and v.data_inicio is null then
            raise exception 'data_inicio é obrigatório para veículo ATIVO' using errcode = '22023';
        end if;
        v.combustivel_valor_mensal := financeiro.numero_seguro(p_dados -> 'combustivel_valor_mensal');
        v.ipva_mes := financeiro.mob_inteiro(p_dados -> 'ipva_mes');
        v.ipva_valor := financeiro.numero_seguro(p_dados -> 'ipva_valor');
        v.seguro_mes := financeiro.mob_inteiro(p_dados -> 'seguro_mes');
        v.seguro_valor := financeiro.numero_seguro(p_dados -> 'seguro_valor');
        v.licenciamento_mes := financeiro.mob_inteiro(p_dados -> 'licenciamento_mes');
        v.licenciamento_valor := financeiro.numero_seguro(p_dados -> 'licenciamento_valor');
        v.preco_medio_combustivel := financeiro.numero_seguro(p_dados -> 'preco_medio_combustivel');
    else
        if p_dados ? 'nome' then v.nome := btrim(coalesce(p_dados ->> 'nome', '')); end if;
        if p_dados ? 'tipo' then v.tipo := btrim(coalesce(p_dados ->> 'tipo', '')); end if;
        if p_dados ? 'combustivel' then v.combustivel := btrim(coalesce(p_dados ->> 'combustivel', '')); end if;
        if p_dados ? 'autonomia_km_l' then
            v_auton := financeiro.numero_seguro(p_dados -> 'autonomia_km_l');
            if v_auton is null or v_auton <= 0 then
                raise exception 'autonomia_km_l deve ser > 0' using errcode = '22023';
            end if;
            v.autonomia_km_l := v_auton;
        end if;
        if p_dados ? 'status' then
            v.status := upper(btrim(coalesce(p_dados ->> 'status', '')));
            if v.status not in ('SIMULADO', 'ATIVO') then
                raise exception 'Status inválido (SIMULADO|ATIVO)' using errcode = '22023';
            end if;
        end if;
        if p_dados ? 'data_inicio' then v.data_inicio := financeiro.mob_data(p_dados ->> 'data_inicio'); end if;
        if v.status = 'ATIVO' and v.data_inicio is null then
            raise exception 'data_inicio é obrigatório para veículo ATIVO' using errcode = '22023';
        end if;
        if p_dados ? 'combustivel_valor_mensal' then
            v.combustivel_valor_mensal := financeiro.numero_seguro(p_dados -> 'combustivel_valor_mensal');
        end if;
        if p_dados ? 'ipva_mes' then v.ipva_mes := financeiro.mob_inteiro(p_dados -> 'ipva_mes'); end if;
        if p_dados ? 'ipva_valor' then v.ipva_valor := financeiro.numero_seguro(p_dados -> 'ipva_valor'); end if;
        if p_dados ? 'seguro_mes' then v.seguro_mes := financeiro.mob_inteiro(p_dados -> 'seguro_mes'); end if;
        if p_dados ? 'seguro_valor' then v.seguro_valor := financeiro.numero_seguro(p_dados -> 'seguro_valor'); end if;
        if p_dados ? 'licenciamento_mes' then v.licenciamento_mes := financeiro.mob_inteiro(p_dados -> 'licenciamento_mes'); end if;
        if p_dados ? 'licenciamento_valor' then
            v.licenciamento_valor := financeiro.numero_seguro(p_dados -> 'licenciamento_valor');
        end if;
        if p_dados ? 'preco_medio_combustivel' then
            v.preco_medio_combustivel := financeiro.numero_seguro(p_dados -> 'preco_medio_combustivel');
        end if;
    end if;
    if not (coalesce(v.ipva_mes, 1) between 1 and 12 and coalesce(v.seguro_mes, 1) between 1 and 12
            and coalesce(v.licenciamento_mes, 1) between 1 and 12) then
        raise exception 'Mês deve estar entre 1 e 12' using errcode = '22023';
    end if;
    return v;
end
$$;

-- criar_veiculo: texto de 20261127090000.
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
                                licenciamento_valor, preco_medio_combustivel, km_estimado_acumulado, criado_em, atualizado_em)
    values (p_perfil_id, v.nome, v.tipo, v.combustivel, v.autonomia_km_l, v.status, v.data_inicio,
            v.combustivel_valor_mensal, v.ipva_mes, v.ipva_valor, v.seguro_mes, v.seguro_valor, v.licenciamento_mes,
            v.licenciamento_valor, v.preco_medio_combustivel, 0, financeiro.mob_agora(), financeiro.mob_agora())
    returning id into v.id;
    perform financeiro.mob_aplicar_categorias(v.id);
    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'criar_veiculo',
        jsonb_build_object('veiculo_id', v.id));
end
$$;

-- editar_veiculo: texto de 20261127090000.
create or replace function financeiro.editar_veiculo(p_perfil_id integer, p_veiculo_id integer, p_dados jsonb)
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
    v := financeiro.mob_dados_veiculo(financeiro.mob_veiculo(p_perfil_id, p_veiculo_id), coalesce(p_dados, '{}'::jsonb));
    update public.veiculo
       set nome = v.nome, tipo = v.tipo, combustivel = v.combustivel, autonomia_km_l = v.autonomia_km_l,
           status = v.status, data_inicio = v.data_inicio, combustivel_valor_mensal = v.combustivel_valor_mensal,
           ipva_mes = v.ipva_mes, ipva_valor = v.ipva_valor, seguro_mes = v.seguro_mes, seguro_valor = v.seguro_valor,
           licenciamento_mes = v.licenciamento_mes, licenciamento_valor = v.licenciamento_valor,
           preco_medio_combustivel = v.preco_medio_combustivel, atualizado_em = financeiro.mob_agora()
     where id = v.id;
    perform financeiro.mob_aplicar_categorias(v.id);
    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    return jsonb_build_object('veiculo_id', v.id);
end
$$;

-- mob_gerar_projecoes: texto de 20261127090000.
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
    v_criadas   integer := 0;
    v_evento    record;
    v_ano       integer;
begin
    select * into v_v from public.veiculo where id = p_veiculo_id;
    v_inicio := date_trunc('month', greatest(coalesce(v_v.data_inicio, v_hoje), v_hoje))::date;
    v_fim := (v_inicio + make_interval(months => v_meses))::date;
    v_perfil := coalesce(v_v.perfil_financeiro_id, p_perfil_id);

    for v_d in select d.*, financeiro.mob_tipo_evento(d.metadata) tipo from public.despesa_prevista d
                where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                  and d.origem_tipo = 'VEICULO' and d.origem_id = v_v.id
                  and d.data_prevista >= v_inicio and d.data_prevista < v_fim
    loop
        continue when v_d.tipo is null or v_d.tipo not in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO');
        if v_d.status is not null and v_d.status <> 'PREVISTA' then
            if coalesce(v_d.data_original_prevista, v_d.data_prevista) >= v_inicio
               and coalesce(v_d.data_original_prevista, v_d.data_prevista) < v_fim then
                v_bloq := v_bloq || (v_d.tipo || '|' || coalesce(v_d.data_original_prevista, v_d.data_prevista));
            end if;
            if coalesce(v_d.data_atual_prevista, v_d.data_prevista) >= v_inicio
               and coalesce(v_d.data_atual_prevista, v_d.data_prevista) < v_fim then
                v_bloq := v_bloq || (v_d.tipo || '|' || coalesce(v_d.data_atual_prevista, v_d.data_prevista));
            end if;
        end if;
    end loop;
    delete from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.origem_tipo = 'VEICULO' and d.origem_id = v_v.id and d.status = 'PREVISTA'
       and d.data_prevista >= v_inicio and d.data_prevista < v_fim
       and financeiro.mob_tipo_evento(d.metadata) in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO');

    if coalesce(v_v.combustivel_valor_mensal, 0) > 0 then
        v_ref := v_inicio;
        while v_ref < v_fim loop
            if not (('COMBUSTIVEL|' || v_ref) = any (v_bloq)) then
                perform financeiro.mob_inserir_prevista(v_perfil, 'VEICULO', v_v.id, financeiro.mob_categoria_evento('COMBUSTIVEL'),
                    v_ref, v_v.combustivel_valor_mensal,
                    jsonb_build_object('tipo_evento', 'COMBUSTIVEL', 'ciclo_id', null, 'ordem_no_ciclo', null));
                v_criadas := v_criadas + 1;
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
            continue when v_ref < v_inicio or v_ref >= v_fim or ((v_evento.tipo || '|' || v_ref) = any (v_bloq));
            perform financeiro.mob_inserir_prevista(v_perfil, 'VEICULO', v_v.id, financeiro.mob_categoria_evento(v_evento.tipo),
                v_ref, v_evento.valor, jsonb_build_object('tipo_evento', v_evento.tipo, 'ciclo_id', null, 'ordem_no_ciclo', null));
            v_criadas := v_criadas + 1;
        end loop;
    end loop;
    return v_criadas;
end
$$;

-- ativar_mobilidade: texto de 20261127090000.
create or replace function financeiro.ativar_mobilidade(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep      jsonb;
    v_tipo     text := upper(coalesce(p_dados ->> 'tipo_modalidade', ''));
    v_origem   integer := financeiro.mob_inteiro(p_dados -> 'origem_id');
    v_meio     text := nullif(lower(coalesce(p_dados ->> 'meio_pagamento', '')), '');
    v_cartao   integer := financeiro.mob_inteiro(p_dados -> 'cartao_id');
    v_inicio   date := coalesce(financeiro.mob_data(p_dados ->> 'data_inicio'), date_trunc('month', financeiro.hoje_brasilia())::date);
    v_criar    boolean := financeiro.mob_bool(p_dados -> 'criar_recorrencia', true);
    v_anterior public.mobilidade_cenario_ativo;
    v_o        jsonb;
    v_cat      integer;
    v_cc       jsonb;
    v_avisos   jsonb := '[]'::jsonb;
    v_rec      public.item_despesa;
    v_c        public.mobilidade_cenario_ativo;
    v_sup      integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not financeiro.mob_bool(p_dados -> 'confirmado', false) then
        raise exception 'Envie confirmado=true para prosseguir com a ativacao.' using errcode = '22023';
    end if;
    v_rep := financeiro.repeticao_mobilidade(p_chave, p_perfil_id, 'ativar_mobilidade');
    if v_rep is not null then
        return v_rep;
    end if;
    if v_tipo not in ('VEICULO', 'TRANSPORTE_APP', 'ASSINATURA') then
        raise exception 'tipo_modalidade invalido: %', v_tipo using errcode = '22023';
    end if;
    if v_meio is not null and v_meio not in ('cartao', 'pix', 'boleto', 'dinheiro', 'debito') then
        raise exception 'meio_pagamento invalido: %', v_meio using errcode = '22023';
    end if;
    v_cartao := financeiro.mob_cartao(p_perfil_id, v_cartao);

    -- 1. Modalidade anterior e as recorrencias automaticas dela.
    select * into v_anterior from public.mobilidade_cenario_ativo c
     where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and c.status = 'ATIVO'
     order by c.id limit 1 for update;
    if found then
        update public.item_despesa i set ativo = false
         where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.origem_tipo = v_anterior.tipo_modalidade
           and i.origem_id = v_anterior.origem_id and i.recorrente and i.ativo;
        update public.mobilidade_cenario_ativo set status = 'INATIVO', updated_at = financeiro.mob_agora()
         where id = v_anterior.id;
    end if;

    -- 2. Recorrencia mensal.
    if v_origem is null or v_origem = 0 then
        raise exception 'origem_id (%) e obrigatorio',
            case v_tipo when 'VEICULO' then 'veiculo.id' when 'TRANSPORTE_APP' then 'caminho_id' else 'assinatura.id' end
            using errcode = '22023';
    end if;
    v_o := financeiro.mob_origem(p_perfil_id, v_tipo, v_origem);
    v_cat := financeiro.mob_categoria(v_o ->> 'codigo');
    v_cc := financeiro.mob_resolver_cc(p_perfil_id, v_cartao, v_cat);
    if v_cc ->> 'aviso' is not null then
        v_avisos := v_avisos || (v_cc -> 'aviso');
    end if;
    if v_criar and v_meio is not null and (v_tipo = 'ASSINATURA' or (v_o ->> 'valor')::numeric > 0) then
        select * into v_rec from public.item_despesa i
         where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.origem_tipo = v_tipo
           and i.origem_id = v_origem and i.origem_contexto = v_o ->> 'contexto' and i.recorrente and i.ativo
         order by i.id limit 1 for update;
        if v_rec.id is not null then
            update public.item_despesa
               set valor = (v_o ->> 'valor')::numeric, meio_pagamento = v_meio, cartao_id = v_cartao, categoria_id = v_cat,
                   categoria_cartao_id = (v_cc ->> 'id')::integer, ativo = true
             where id = v_rec.id
            returning * into v_rec;
        else
            insert into public.item_despesa (perfil_financeiro_id, nome, tipo, recorrente, tipo_recorrencia, valor, categoria_id,
                                             categoria_cartao_id, meio_pagamento, cartao_id, data_vencimento, mes_competencia,
                                             ativo, pago, origem_tipo, origem_id, origem_contexto, criado_em)
            values (p_perfil_id, v_o ->> 'rotulo', 'Simples', true, 'mensal', (v_o ->> 'valor')::numeric, v_cat,
                    (v_cc ->> 'id')::integer, v_meio, v_cartao, v_inicio, to_char(v_inicio, 'YYYY-MM'), true, false,
                    v_tipo, v_origem, v_o ->> 'contexto', financeiro.mob_agora())
            returning * into v_rec;
        end if;
        -- O Flask resolve de novo ao criar a recorrencia (criar_recorrencia_*): o aviso nao resolvido sai duas vezes.
        if v_cc ->> 'aviso' is not null then
            v_avisos := v_avisos || (v_cc -> 'aviso');
        end if;
        if v_tipo = 'TRANSPORTE_APP' then
            update public.despesa_prevista d set status = 'SUPRIMIDA', atualizado_em = financeiro.mob_agora()
             where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'TRANSPORTE_APP'
               and d.origem_id = v_origem and d.status = 'PREVISTA'
               and d.data_prevista >= date_trunc('month', financeiro.hoje_brasilia())::date
               and (coalesce(d.metadata, '') = '' or financeiro.mob_tipo_evento(d.metadata) = 'TRANSPORTE_APP');
            get diagnostics v_sup = row_count;
            if v_sup > 0 then
                v_avisos := v_avisos || to_jsonb(v_sup || ' DespesaPrevista(s) suprimida(s) por recorrencia ativa.');
            end if;
        end if;
    elsif v_criar and v_meio is null and (v_tipo = 'ASSINATURA' or (v_o ->> 'valor')::numeric > 0) then
        v_avisos := v_avisos || to_jsonb('meio_pagamento nao informado — recorrencia de ' || case v_tipo
            when 'VEICULO' then 'combustivel' when 'TRANSPORTE_APP' then 'transporte por app' else 'assinatura' end
            || ' nao foi criada.');
    elsif v_criar and v_tipo <> 'ASSINATURA' then
        v_avisos := v_avisos || to_jsonb(case v_tipo when 'VEICULO' then 'Veiculo sem valor de combustivel — recorrencia nao criada.'
                                                     else 'Caminho sem valor mensal — recorrencia nao criada.' end);
    end if;

    -- 3. Cenario ativo do perfil.
    insert into public.mobilidade_cenario_ativo (perfil_financeiro_id, tipo_modalidade, origem_id, ativo_desde, meio_pagamento,
                                                 cartao_id, categoria_id, categoria_cartao_id, recorrencia_id, status,
                                                 created_at, updated_at)
    values (p_perfil_id, v_tipo, coalesce(v_origem, 0), v_inicio, v_meio, v_cartao, v_cat, (v_cc ->> 'id')::integer, v_rec.id,
            'ATIVO', financeiro.mob_agora(), financeiro.mob_agora())
    returning * into v_c;
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'ativar_mobilidade', jsonb_build_object(
        'cenario', financeiro.mob_cenario_flask(v_c),
        'recorrencia', case when v_rec.id is not null then financeiro.item_despesa_flask(v_rec) end,
        'anterior_inativado', v_anterior.id, 'avisos', v_avisos));
end
$$;

-- mob_registrar_combustivel: texto de 20261127090000.
create or replace function financeiro.mob_registrar_combustivel(p_perfil_id integer, p_d public.despesa_prevista)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_v      public.veiculo;
    v_md     jsonb := financeiro.json_seguro(p_d.metadata);
    v_litros numeric;
begin
    if p_d.origem_tipo <> 'VEICULO' or p_d.status <> 'CONFIRMADA' or financeiro.mob_tipo_evento(p_d.metadata) is distinct from 'COMBUSTIVEL' then
        return;
    end if;
    select * into v_v from public.veiculo v where v.id = p_d.origem_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_v.perfil_financeiro_id, p_perfil_id) then
        return;
    end if;
    if v_v.km_estimado_ultimo_despesa_prevista_id is not null and p_d.id <= v_v.km_estimado_ultimo_despesa_prevista_id then
        return;
    end if;
    if coalesce(v_v.autonomia_km_l, 0) <= 0 then
        return;
    end if;
    v_litros := financeiro.numero_seguro(v_md -> 'litros_abastecidos');
    if v_litros is null or v_litros <= 0 then
        v_litros := case when coalesce(v_v.preco_medio_combustivel, 0) > 0 and coalesce(p_d.valor_previsto, 0) > 0
                         then p_d.valor_previsto / v_v.preco_medio_combustivel end;
    end if;
    if coalesce(v_litros, 0) <= 0 then
        return;
    end if;
    update public.veiculo
       set km_estimado_acumulado = coalesce(km_estimado_acumulado, 0) + v_litros * autonomia_km_l,
           km_estimado_ultimo_despesa_prevista_id = p_d.id, km_estimado_ultimo_calculo_em = financeiro.mob_agora()
     where id = v_v.id;
end
$$;

-- confirmar_despesa_prevista: texto de 20261127090000.
create or replace function financeiro.confirmar_despesa_prevista(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d       public.despesa_prevista;
    v_meio    text := nullif(lower(btrim(coalesce(p_dados ->> 'meio_pagamento', ''))), '');
    v_cat     integer;
    v_venc    date;
    v_obs     text := nullif(btrim(coalesce(p_dados ->> 'observacao', '')), '');
    v_nome    text;
    v_cartao  integer;
    v_item    integer;
    v_conta   integer;
    v_mes     date;
    v_compra  jsonb;
    v_criada  jsonb := null;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_d := financeiro.mob_prevista(p_perfil_id, p_id);
    if p_dados ? 'meio_pagamento' and v_meio is not null then
        if v_meio not in ('cartao', 'pix', 'boleto', 'dinheiro', 'debito') then
            raise exception 'meio_pagamento inválido: %. Use: cartao, pix, boleto, dinheiro, debito', v_meio using errcode = '22023';
        end if;
        v_cat := coalesce(nullif(financeiro.mob_inteiro(p_dados -> 'categoria_id'), 0), v_d.categoria_id);
        if coalesce(v_cat, 0) = 0 then
            raise exception 'categoria_id é obrigatório para conversão' using errcode = '22023';
        end if;
        v_venc := financeiro.mob_data(coalesce(nullif(p_dados ->> 'data_vencimento', ''),
                                               coalesce(v_d.data_atual_prevista, v_d.data_prevista)::text));
        if v_venc is null then
            raise exception 'data_vencimento inválida' using errcode = '22023';
        end if;
        v_nome := financeiro.mob_rotulo_prevista(v_d);
        if v_meio = 'cartao' then
            v_cartao := financeiro.mob_inteiro(p_dados -> 'cartao_id');
            if v_cartao is null or v_cartao = 0 then
                raise exception 'cartao_id é obrigatório quando meio_pagamento=cartao' using errcode = '22023';
            end if;
            v_compra := financeiro.criar_compra(p_perfil_id, jsonb_build_object(
                'cartao_id', v_cartao, 'categoria_id', v_cat, 'descricao', v_nome, 'valor', v_d.valor_previsto,
                'data_compra', v_venc, 'mes_fatura', to_char(v_venc, 'YYYY-MM-DD'), 'total_parcelas', 1, 'observacoes', v_obs),
                gen_random_uuid());
            v_criada := jsonb_build_object('tipo', 'lancamento_agregado', 'compra', v_compra, 'descricao', v_nome,
                                           'valor', v_d.valor_previsto::float8, 'data_vencimento', v_venc);
        else
            v_mes := date_trunc('month', v_venc)::date;
            insert into public.item_despesa (perfil_financeiro_id, nome, tipo, categoria_id, valor, recorrente, ativo, pago,
                                             tipo_recorrencia, meio_pagamento, data_vencimento, mes_competencia, criado_em)
            values (p_perfil_id, v_nome, 'Simples', v_cat, coalesce(v_d.valor_previsto, 0), false, true, false, 'mensal',
                    v_meio, v_venc, to_char(v_mes, 'YYYY-MM'), financeiro.mob_agora())
            returning id into v_item;
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento,
                                      status_pagamento, is_fatura_cartao, observacoes, debito_automatico, estouro_orcamento,
                                      status_fatura, criado_em)
            values (p_perfil_id, v_item, v_mes, v_nome || case when v_obs is not null then ' — ' || v_obs else '' end,
                    coalesce(v_d.valor_previsto, 0), v_venc, 'Pendente', false, v_obs, false, false, 'ABERTA', financeiro.mob_agora())
            returning id into v_conta;
            v_criada := jsonb_build_object('tipo', 'conta', 'id', v_conta,
                'descricao', v_nome || case when v_obs is not null then ' — ' || v_obs else '' end,
                'valor', coalesce(v_d.valor_previsto, 0)::float8, 'data_vencimento', v_venc);
        end if;
    end if;
    update public.despesa_prevista set status = 'CONFIRMADA', atualizado_em = financeiro.mob_agora() where id = v_d.id
    returning * into v_d;
    perform financeiro.mob_registrar_combustivel(p_perfil_id, v_d);
    return jsonb_build_object('despesa_prevista', jsonb_build_object('id', v_d.id, 'status', v_d.status),
                              'entidade_criada', v_criada);
end
$$;

-- dashboard_resumo_tela: texto de 20261209090000.
create or replace function financeiro.dashboard_resumo_tela(p_perfil_id integer, p_mes_referencia text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_hoje        date := (now() at time zone 'America/Sao_Paulo')::date;
    v_valor       text := btrim(coalesce(p_mes_referencia, ''));
    v_inicio      date;
    v_fim         date;
    v_dias        integer;
    v_saldo       numeric;
    v_receitas    numeric;
    v_recebidas   numeric;
    v_despesas    numeric;
    v_fat_total   numeric;
    v_fat_qtd     integer;
    v_rec_qtd     integer;
    v_rec_total   numeric;
    v_venc        jsonb;
    v_venc_total  numeric;
    v_categorias  jsonb;
    v_cartoes     jsonb;
    v_lim_total   numeric;
    v_uso_total   numeric;
    v_mobilidade  jsonb;
    v_alertas     jsonb := '[]'::jsonb;
    v_fluxo       jsonb;
    v_prev_mes    numeric;
    v_prev_pend   integer;
    v_prev_conf   integer;
    v_qtd         integer;
    v_venc_hoje   integer;
    v_percentual  numeric;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    -- _periodo_mes: YYYY-MM ou YYYY-MM-DD validos; senao, mes atual.
    if length(v_valor) = 7 then
        v_valor := v_valor || '-01';
    end if;
    begin
        if v_valor ~ '^\d{4}-\d{1,2}-\d{1,2}$' then
            v_inicio := date_trunc('month', v_valor::date)::date;
        end if;
    exception when others then
        v_inicio := null;
    end;
    v_inicio := coalesce(v_inicio, date_trunc('month', v_hoje)::date);
    v_fim := (v_inicio + interval '1 month' - interval '1 day')::date;
    v_dias := extract(day from v_fim)::integer;

    select coalesce(sum(cb.saldo_atual), 0) into v_saldo from public.conta_bancaria cb
     where financeiro.pertence_ao_perfil(cb.perfil_financeiro_id, p_perfil_id) and cb.status = 'ATIVO';
    -- D2: previsto = orcado + recebido sem previsao; o recebido de uma previsao nao soma de novo.
    v_receitas := coalesce((select sum(o.valor_esperado) from public.receita_orcamento o
                             where financeiro.pertence_ao_perfil(o.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', o.mes_referencia) = v_inicio), 0)
                + coalesce((select sum(r.valor_recebido) from public.receita_realizada r
                             where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', r.mes_referencia) = v_inicio and r.orcamento_id is null), 0);
    v_recebidas := coalesce((select sum(r.valor_recebido) from public.receita_realizada r
                              where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
                                and date_trunc('month', r.mes_referencia) = v_inicio), 0);
    v_despesas := coalesce((select sum(c.valor) from public.conta c
                             where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', c.mes_referencia) = v_inicio and c.is_fatura_cartao is not true), 0)
                + coalesce((select sum(d.valor_previsto) from public.despesa_prevista d
                             where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', d.data_atual_prevista) = v_inicio
                               and d.status in ('PREVISTA', 'ADIADA')), 0);

    -- _fluxo_caixa: 5 pontos lineares no mes.
    select jsonb_build_object(
               'labels', jsonb_agg(to_char(p.dia, 'FM00') || '/' || to_char(v_inicio, 'MM') order by p.ponto),
               'entradas', jsonb_agg(round(v_receitas * p.ponto / 5, 2) order by p.ponto),
               'saidas', jsonb_agg(round(v_despesas * p.ponto / 5, 2) order by p.ponto),
               'saldo_projetado', jsonb_agg(round(v_saldo + v_receitas * p.ponto / 5 - v_despesas * p.ponto / 5, 2) order by p.ponto),
               'resumo', jsonb_build_object('receitas_previstas', round(v_receitas, 2), 'despesas_previstas', round(v_despesas, 2),
                                            'saldo_final_projetado', round(v_saldo + v_receitas - v_despesas, 2),
                                            'receitas_recebidas', round(v_recebidas, 2),
                                            'diferenca_receitas', round(v_recebidas - v_receitas, 2)),
               'tipo', 'projecao_simplificada')
      into v_fluxo
      from (select g ponto, least(v_dias, 1 + (g - 1) * greatest(1, v_dias / 5)) dia from generate_series(1, 5) g) p;

    -- _total_faturas_periodo (FIN-CARTAO-PREVISTO-EXECUTADO-01: executado atual, sem previsoes pendentes)
    select coalesce(sum(coalesce(nullif(c.valor_consolidado, 0), nullif(financeiro.executado_fatura(c.id), 0), nullif(c.valor_planejado, 0), c.valor, 0)), 0),
           count(*)
      into v_fat_total, v_fat_qtd
      from public.conta c
     where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and c.is_fatura_cartao
       and date_trunc('month', c.mes_referencia) = v_inicio and c.status_pagamento is distinct from 'Pago'
       and c.status_pagamento is not null;

    -- _recorrencias_ativas
    select count(*), coalesce(sum(i.valor), 0) into v_rec_qtd, v_rec_total from public.item_despesa i
     where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.recorrente and i.ativo;

    -- _contas_a_vencer_7_dias (contas e faturas pendentes; 8 primeiras)
    select coalesce(jsonb_agg(jsonb_build_object(
               'id', x.id, 'data', x.data_vencimento, 'descricao', x.descricao,
               'origem', case when x.is_fatura_cartao then 'Fatura' else 'Conta' end, 'valor', round(coalesce(x.valor, 0), 2),
               'tipo', case when x.is_fatura_cartao then 'fatura' else 'despesa' end,
               'status_visual', case when x.data_vencimento = v_hoje then 'vence_hoje' else (x.data_vencimento - v_hoje) || ' dias' end)
           order by x.data_vencimento, x.id), '[]'::jsonb),
           coalesce(sum(coalesce(x.valor, 0)), 0),
           count(*) filter (where x.data_vencimento = v_hoje)
      into v_venc, v_venc_total, v_venc_hoje
      from (select c.* from public.conta c
             where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
               and c.data_vencimento between v_hoje and v_hoje + 7 and c.status_pagamento = 'Pendente'
             order by c.data_vencimento, c.id limit 8) x;

    -- _categorias_cartao: limites ativos + gastos do mes da fatura; 6 maiores gastos.
    with limites as (
        select l.categoria_cartao_id id, sum(coalesce(l.limite_mensal, 0)) limite, min(l.id) ordem
          from public.cartao_categoria_limite l join public.categoria_cartao cc on cc.id = l.categoria_cartao_id
         where financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id) and l.ativo
         group by 1),
    gastos as (
        select la.categoria_cartao_id id, sum(coalesce(la.valor, 0)) gasto
          from public.lancamento_agregado la join public.categoria_cartao cc on cc.id = la.categoria_cartao_id
         where financeiro.pertence_ao_perfil(la.perfil_financeiro_id, p_perfil_id)
           and financeiro.natureza_da_compra(la.total_parcelas, la.is_recorrente, la.item_despesa_id, la.categoria_cartao_id) = 'CATEGORIA'  -- FIN-CARTAO-DESPESAS-FIXAS-01
           and date_trunc('month', la.mes_fatura) = v_inicio
         group by 1),
    juntas as (
        select coalesce(l.id, g.id) id, coalesce(l.limite, 0) limite, coalesce(g.gasto, 0) gasto,
               case when l.id is not null then 0 else 1 end grupo, coalesce(l.ordem, g.id) ordem
          from limites l full join gastos g on g.id = l.id)
    select coalesce(jsonb_agg(jsonb_build_object(
               'categoria_cartao_id', j.id, 'nome', cc.nome, 'cor', cc.cor, 'icone', cc.icone,
               'limite', round(j.limite, 2), 'gasto', round(j.gasto, 2), 'disponivel', round(j.limite - j.gasto, 2),
               'percentual', financeiro.percentual_flask(j.gasto, j.limite),
               'status', financeiro.status_consumo_flask(financeiro.percentual_flask(j.gasto, j.limite)))
           order by j.gasto desc, j.grupo, j.ordem), '[]'::jsonb)
      into v_categorias
      from (select * from juntas order by gasto desc, grupo, ordem limit 6) j
      join public.categoria_cartao cc on cc.id = j.id;

    -- _cartoes_limites: cartoes (Agregador) ativos por nome.
    select coalesce(jsonb_agg(jsonb_build_object(
               'id', k.id, 'nome', k.nome, 'final', k.final, 'limite_total', round(k.limite, 2), 'utilizado', round(k.usado, 2),
               'disponivel', round(k.limite - k.usado, 2), 'percentual', financeiro.percentual_flask(k.usado, k.limite),
               'status', financeiro.status_consumo_flask(financeiro.percentual_flask(k.usado, k.limite)),
               'categorias_vinculadas', k.qtd)
           order by k.nome, k.id), '[]'::jsonb),
           coalesce(sum(k.limite), 0), coalesce(sum(k.usado), 0)
      into v_cartoes, v_lim_total, v_uso_total
      from (select i.id, i.nome,
                   coalesce(right((select cfg.numero_cartao::text from public.config_agregador cfg
                                    where cfg.item_despesa_id = i.id order by cfg.id limit 1), 4), '') final,
                   coalesce((select sum(coalesce(l.limite_mensal, 0)) from public.cartao_categoria_limite l
                              where l.cartao_id = i.id and l.ativo
                                and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)), 0) limite,
                   (select count(*) from public.cartao_categoria_limite l
                     where l.cartao_id = i.id and l.ativo and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)) qtd,
                   coalesce((select sum(la.valor) from public.lancamento_agregado la
                              where la.cartao_id = i.id and financeiro.pertence_ao_perfil(la.perfil_financeiro_id, p_perfil_id)
                                -- FIN-CARTAO-DESPESAS-FIXAS-01: uso dos limites sem as obrigacoes ja contratadas
                                and financeiro.natureza_da_compra(la.total_parcelas, la.is_recorrente, la.item_despesa_id, la.categoria_cartao_id) not in ('PARCELADA', 'FIXA')
                                and date_trunc('month', la.mes_fatura) = v_inicio), 0) usado
              from public.item_despesa i
             where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.tipo = 'Agregador' and i.ativo) k;

    -- _mobilidade_ativa
    select jsonb_build_object(
               'tipo', m.tipo_modalidade,
               'nome', case m.tipo_modalidade when 'VEICULO' then 'Veiculo proprio' when 'TRANSPORTE_APP' then 'Transporte por app'
                                               when 'ASSINATURA' then 'Assinatura' else coalesce(nullif(m.tipo_modalidade, ''), 'Mobilidade') end,
               'custo_mensal', round(coalesce(nullif((select r.valor from public.item_despesa r where r.id = m.recorrencia_id), 0), 0), 2),
               'status', 'ativa',
               'categoria_cartao', (select jsonb_build_object('id', cc.id, 'nome', cc.nome) from public.categoria_cartao cc
                                     where cc.id = m.categoria_cartao_id))
      into v_mobilidade
      from public.mobilidade_cenario_ativo m
     where financeiro.pertence_ao_perfil(m.perfil_financeiro_id, p_perfil_id) and m.status = 'ATIVO'
     order by m.updated_at desc nulls first, m.id desc limit 1;
    v_mobilidade := coalesce(v_mobilidade, jsonb_build_object('tipo', null, 'nome', 'Sem modalidade ativa', 'custo_mensal', 0,
                                                              'status', 'nao_configurada', 'categoria_cartao', null))
                    || jsonb_build_object('alternativas', coalesce((
                           select jsonb_agg(jsonb_build_object('tipo', 'ASSINATURA', 'nome', a.nome,
                                                               'custo_mensal', round(coalesce(a.valor_mensal, 0), 2),
                                                               'status', 'alternativa') order by a.id)
                             from (select * from public.mobilidade_assinatura a
                                    where financeiro.pertence_ao_perfil(a.perfil_financeiro_id, p_perfil_id) and a.status = 'ATIVO'
                                    order by a.id limit 3) a), '[]'::jsonb));

    -- _alertas_operacionais
    if v_venc_hoje > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'vencimento', 'nivel', 'critico',
                                                                      'mensagem', v_venc_hoje || ' vencimento(s) hoje'));
    end if;
    select count(*) into v_qtd from jsonb_array_elements(v_categorias) x where (x ->> 'percentual')::numeric > 80;
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'limite', 'nivel', 'atencao',
                                                                      'mensagem', v_qtd || ' limite(s) acima de 80%'));
    end if;
    select count(*) into v_qtd from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.data_atual_prevista < v_hoje
       and d.status in ('PREVISTA', 'ADIADA');
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'prevista', 'nivel', 'atencao',
                                                                      'mensagem', v_qtd || ' despesa(s) prevista(s) atrasada(s)'));
    end if;
    select count(*) into v_qtd from public.documento_empresarial_metadata dm
     where financeiro.pertence_ao_perfil(dm.perfil_financeiro_id, p_perfil_id) and dm.data_validade < v_hoje;
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'documento_empresarial', 'nivel', 'critico',
                         'mensagem', v_qtd || ' documento(s) empresarial(is) com validade vencida'));
    end if;
    select count(*) into v_qtd from public.documento_empresarial_metadata dm
     where financeiro.pertence_ao_perfil(dm.perfil_financeiro_id, p_perfil_id) and dm.data_validade between v_hoje and v_hoje + 30;
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'documento_empresarial', 'nivel', 'atencao',
                         'mensagem', v_qtd || ' documento(s) empresarial(is) com validade vencendo em 30 dias'));
    end if;

    -- Despesas previstas do mes (D1: so do perfil).
    select coalesce(sum(d.valor_previsto), 0), count(*) filter (where d.status in ('PREVISTA', 'ADIADA')),
           count(*) filter (where d.status = 'CONFIRMADA')
      into v_prev_mes, v_prev_pend, v_prev_conf
      from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.data_atual_prevista between v_inicio and v_fim;

    v_percentual := financeiro.percentual_flask(v_uso_total, v_lim_total);
    return jsonb_build_object(
        'periodo', jsonb_build_object('mes_referencia', to_char(v_inicio, 'YYYY-MM'), 'inicio', v_inicio, 'fim', v_fim,
                                      'rotulo', to_char(v_inicio, 'MM/YYYY')),
        'kpis', jsonb_build_object(
            'saldo_consolidado', jsonb_build_object('valor', round(v_saldo, 2), 'subtitulo', 'Disponivel em contas', 'tendencia', null),
            'fluxo_projetado_30_dias', jsonb_build_object('valor', v_fluxo -> 'resumo' -> 'saldo_final_projetado',
                                                          'subtitulo', 'Saldo projetado', 'tendencia', null),
            'faturas_em_aberto', jsonb_build_object('valor', round(v_fat_total, 2), 'quantidade_cartoes', v_fat_qtd,
                                                    'subtitulo', v_fat_qtd || ' cartao(s)'),
            'recorrencias_ativas', jsonb_build_object('quantidade', v_rec_qtd, 'valor_mensal', round(v_rec_total, 2),
                                                      'subtitulo', 'fixas e variaveis')),
        'operacional', jsonb_build_object(
            'despesas_previstas_mes', jsonb_build_object('valor', round(v_prev_mes, 2), 'pendentes', v_prev_pend,
                                                         'confirmadas', v_prev_conf,
                                                         'percentual_orcamento', case when v_receitas > 0
                                                             then financeiro.percentual_flask(v_prev_mes, v_receitas) else 0 end),
            'contas_a_vencer_7_dias', jsonb_build_object('valor', round(v_venc_total, 2), 'quantidade', jsonb_array_length(v_venc)),
            'alertas_operacionais', jsonb_build_object('quantidade', jsonb_array_length(v_alertas), 'itens', v_alertas),
            'modalidade_mobilidade_ativa', v_mobilidade),
        'fluxo_caixa', v_fluxo,
        'categorias_cartao', v_categorias,
        'proximos_vencimentos', v_venc,
        'cartoes_limites', jsonb_build_object('itens', v_cartoes, 'limite_total', round(v_lim_total, 2),
                                              'utilizado_total', round(v_uso_total, 2),
                                              'disponivel_total', round(v_lim_total - v_uso_total, 2),
                                              'percentual_total', v_percentual, 'status', financeiro.status_consumo_flask(v_percentual)),
        'mobilidade', v_mobilidade,
        'acoes_rapidas', jsonb_build_array(
            jsonb_build_object('label', 'Confirmar despesas previstas', 'url', '/despesas-previstas'),
            jsonb_build_object('label', 'Importar fatura', 'url', '/importar-cartao'),
            jsonb_build_object('label', 'Gerenciar categorias do cartao', 'url', '/categorias'),
            jsonb_build_object('label', 'Revisar recorrencias', 'url', '/recorrencias'),
            jsonb_build_object('label', 'Gerenciar mobilidade', 'url', '/veiculos')),
        'alertas', v_alertas);
end
$$;

-- saidas_lastro: texto de 20261117090000.
create or replace function financeiro.saidas_lastro(p_perfil_id integer, p_f jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_hoje   date := (now() at time zone 'America/Sao_Paulo')::date;
    v_ano    integer;
    v_mes    integer;
    v_ini    date;
    v_fim    date;
    v_origem text := upper(btrim(coalesce(p_f ->> 'origem', '')));
    v_nat    text := upper(btrim(coalesce(p_f ->> 'natureza', '')));
    v_busca  text := financeiro.texto_sem_acento(p_f ->> 'busca');
    v_minimo numeric := 0;
begin
    if btrim(coalesce(p_f ->> 'ano', '')) ~ '^[+-]?\d{1,9}$' then v_ano := nullif(btrim(p_f ->> 'ano')::integer, 0); end if;
    if btrim(coalesce(p_f ->> 'mes', '')) ~ '^[+-]?\d{1,9}$' then v_mes := btrim(p_f ->> 'mes')::integer; end if;
    v_ano := coalesce(v_ano, extract(year from v_hoje)::integer);
    if v_mes between 1 and 12 then
        v_ini := make_date(v_ano, v_mes, 1);
        v_fim := (v_ini + interval '1 month')::date;
    else
        v_ini := make_date(v_ano, 1, 1);
        v_fim := make_date(v_ano + 1, 1, 1);
    end if;
    begin
        v_minimo := coalesce(nullif(btrim(coalesce(nullif(p_f ->> 'valor_minimo', ''), p_f ->> 'valorMinimo', '')), ''), '0')::numeric;
    exception when others then
        v_minimo := 0;
    end;
    return coalesce((
        with saidas as (
            select 'DESPESA_PREVISTA'::text tipo, d.id, coalesce(d.data_atual_prevista, d.data_prevista) data_saida,
                   coalesce(cat.nome, 'Despesa') || ' - ' || coalesce(d.status, 'None') descricao, d.valor_previsto valor,
                   'Despesa prevista'::text origem, cat.nome categoria, d.status status_pagamento
              from public.despesa_prevista d left join public.categoria cat on cat.id = d.categoria_id
             where d.perfil_financeiro_id = p_perfil_id and d.valor_previsto > 0
               and d.data_atual_prevista >= v_ini and d.data_atual_prevista < v_fim
               and d.status not in ('IGNORADA', 'CANCELADA', 'SUPRIMIDA')
            union all
            select 'CONTA', c.id, coalesce(c.data_pagamento, c.data_vencimento),
                   case when nullif(c.descricao, '') is not null then c.descricao when i.id is not null then i.nome
                        else 'Conta #' || c.id end,
                   c.valor, 'Conta a pagar', cat.nome, c.status_pagamento
              from public.conta c
              left join public.item_despesa i on i.id = c.item_despesa_id
              left join public.categoria cat on cat.id = i.categoria_id
             where c.perfil_financeiro_id = p_perfil_id and c.valor > 0
               and c.data_vencimento >= v_ini and c.data_vencimento < v_fim and c.is_fatura_cartao is not true
            union all
            select 'LANCAMENTO', la.id, la.data_compra, la.descricao, la.valor, 'Lancamento no cartao', cat.nome, 'CARTAO'
              from public.lancamento_agregado la left join public.categoria cat on cat.id = la.categoria_id
             where la.perfil_financeiro_id = p_perfil_id and la.valor > 0 and la.data_compra >= v_ini and la.data_compra < v_fim
            union all
            select 'MOVIMENTO_FINANCEIRO', m.id, m.data_movimento, m.descricao, m.valor,
                   coalesce(nullif(m.origem, ''), 'Movimento financeiro'), null, m.tipo
              from public.movimento_financeiro m
             where m.perfil_financeiro_id = p_perfil_id and m.tipo = 'DEBITO' and m.valor > 0
               and m.data_movimento >= v_ini and m.data_movimento < v_fim
               and m.conta_id is null and m.fatura_id is null
               and not (upper(coalesce(m.origem, '')) = 'TRANSFERENCIA' and m.transferencia_id is not null
                        and exists (select 1 from public.movimento_financeiro t
                                     where t.perfil_financeiro_id = p_perfil_id and t.transferencia_id = m.transferencia_id
                                       and t.tipo = 'CREDITO' and t.id <> m.id))
        ),
        enriquecidas as (
            select s.*, financeiro.natureza_sugerida_lastro(s.categoria, s.descricao) sugerida, v.*, pe.*
              from saidas s
              left join lateral (
                  select vv.id vinculo_id, vv.comprovante_id documento_id, vv.status_lastro v_status, vv.natureza v_nat,
                         vv.observacoes v_obs
                    from public.ir_comprovante_vinculo vv join public.ir_comprovante cc on cc.id = vv.comprovante_id
                   where vv.perfil_financeiro_id = p_perfil_id and vv.ativo and cc.perfil_financeiro_id = p_perfil_id
                     and vv.tipo_entidade = s.tipo and vv.entidade_id = s.id
                   order by vv.created_at desc, vv.id desc limit 1) v on true
              left join lateral (
                  select pp.id pendencia_id, pp.status_lastro p_status, pp.natureza p_nat, pp.observacoes p_obs
                    from public.lastro_financeiro_pendencia pp
                   where pp.perfil_financeiro_id = p_perfil_id and pp.ativo and pp.tipo_entidade = s.tipo and pp.entidade_id = s.id
                   order by pp.updated_at desc, pp.id desc limit 1) pe on true
        ),
        finais as (
            select jsonb_build_object(
                       'tipo_entidade', e.tipo, 'entidade_id', e.id, 'data', e.data_saida, 'descricao', e.descricao,
                       'valor', coalesce(e.valor, 0), 'origem', e.origem, 'categoria', e.categoria,
                       'status_pagamento', e.status_pagamento,
                       'status_lastro', case when e.vinculo_id is not null then e.v_status
                                             when e.pendencia_id is not null then e.p_status else 'SEM_DOCUMENTO' end,
                       'natureza_sugerida', coalesce(nullif(case when e.vinculo_id is not null then e.v_nat
                                                                 when e.pendencia_id is not null then e.p_nat
                                                                 else e.sugerida end, ''), e.sugerida),
                       'possui_documento', e.vinculo_id is not null, 'documento_id', e.documento_id,
                       'vinculo_id', e.vinculo_id, 'pendencia_id', e.pendencia_id,
                       'observacoes', case when e.vinculo_id is not null then e.v_obs when e.pendencia_id is not null then e.p_obs end) j
              from enriquecidas e
        )
        select jsonb_agg(f.j order by f.j ->> 'tipo_entidade', (f.j ->> 'entidade_id')::integer)
          from finais f
         where (v_origem in ('', 'TODOS', 'TODAS')
                or v_origem in (upper(btrim(coalesce(f.j ->> 'origem', ''))), upper(btrim(coalesce(f.j ->> 'tipo_entidade', '')))))
           and (v_nat in ('', 'TODOS', 'TODAS') or upper(btrim(coalesce(f.j ->> 'natureza_sugerida', ''))) = v_nat)
           and (v_busca = '' or strpos(financeiro.texto_sem_acento(concat_ws(' ', coalesce(f.j ->> 'descricao', ''),
                       coalesce(f.j ->> 'categoria', ''), coalesce(f.j ->> 'origem', ''), coalesce(f.j ->> 'natureza_sugerida', ''))),
                       v_busca) > 0)
           and (f.j ->> 'valor')::numeric >= v_minimo), '[]'::jsonb);
end
$$;

drop function financeiro.mob_dados_flex(public.veiculo, jsonb);
drop function financeiro.mob_planejar_prevista(integer, integer, integer, text, date, numeric);
drop function financeiro.mob_sincronizar_combustivel(integer, integer, numeric);
drop function financeiro.mob_dispensar_cobertas(integer, integer, public.item_despesa);
drop function financeiro.mob_restaurar_combustivel(integer, integer);
drop function financeiro.mob_suprimir_combustivel(integer, integer);
drop function financeiro.mob_competencia_coberta(integer, integer, date);
drop function financeiro.mob_item_combustivel(integer, integer);
drop function financeiro.prevista_financeira(text, integer);

drop index public.ux_despesa_prevista_obrigacao_periodo;
drop function financeiro.mob_periodo(text, date);
alter table public.despesa_prevista
    drop column obrigacao, drop column periodo_referencia, drop column conta_id, drop column lancamento_id;
alter table public.veiculo
    drop constraint veiculo_combustivel_referencia_valida, drop constraint veiculo_custo_combustivel_modo_valido,
    drop column autonomia_gasolina_km_l, drop column autonomia_etanol_km_l, drop column preco_gasolina, drop column preco_etanol,
    drop column combustivel_referencia, drop column km_mensal_estimado, drop column custo_combustivel_modo;
comment on column public.veiculo.autonomia_km_l is null;
