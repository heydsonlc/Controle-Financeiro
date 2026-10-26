-- FIN-FIDELIDADE-PATRIMONIO-1 (Mobilidade, fase 1) — leitura da tela original de Mobilidade do Flask (so consulta).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261115090000).
-- Depende de 20261112090000 (financeiro.iso_python).
-- Validada em cluster local descartavel (tests/test_supabase_mobilidade_leitura.py, comparada com o Flask).
-- Docs: docs/FIN_FIDELIDADE_PATRIMONIO_1.md.
--
-- Reproduz as rotas GET de routes/veiculos.py e routes/mobilidade_app.py no formato do Flask: veiculos (com o resumo
-- mensal estimado), projecoes (despesas previstas ja geradas), uso estimado por consumo, regras e estimativas de
-- manutencao por km, financiamento do veiculo, modalidade ativa, assinaturas, caminhos de transporte por app e a lista
-- de categorias (globais, como no Flask).
-- Nada e gravado: gerar projecoes, cadastrar/editar/excluir, ativar modalidade, confirmar/adiar/ignorar previstas e
-- financiamento continuam no Flask (escritor unico) nesta fase. A pre-visualizacao de ativacao tambem fica no Flask:
-- ela chama obter_categoria_sistemica_id, que CRIA categorias MOB_* quando faltam (leitura que grava).
-- Nenhuma tabela nova. Nenhum dado existente e alterado.

-- json.loads(...) do Flask com o "except: {}" (texto invalido ou vazio = objeto vazio). Interna.
create function financeiro.json_seguro(p_texto text)
    returns jsonb
    language plpgsql
    immutable
    set search_path = ''
as $$
begin
    if p_texto is null or btrim(p_texto) = '' then
        return '{}'::jsonb;
    end if;
    return p_texto::jsonb;
exception when others then
    return '{}'::jsonb;
end
$$;

-- Decimal(str(x)) / float(x) do Flask sobre um valor do JSON (numero ou texto); invalido = NULL. Interna.
create function financeiro.numero_seguro(p_valor jsonb)
    returns numeric
    language plpgsql
    immutable
    set search_path = ''
as $$
begin
    if p_valor is null or jsonb_typeof(p_valor) not in ('number', 'string') or btrim(p_valor #>> '{}') = '' then
        return null;
    end if;
    return btrim(p_valor #>> '{}')::numeric;
exception when others then
    return null;
end
$$;

-- Categoria.to_dict. Interna.
create function financeiro.categoria_flask(p_c public.categoria)
    returns jsonb
    language sql
    stable
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_c.id, 'perfil_financeiro_id', p_c.perfil_financeiro_id, 'nome', p_c.nome, 'descricao', p_c.descricao,
        'cor', p_c.cor, 'icone', p_c.icone, 'logo_arquivo', p_c.logo_arquivo, 'logo_mime', p_c.logo_mime,
        'logo_tamanho', p_c.logo_tamanho, 'logo_original_nome', p_c.logo_original_nome,
        'logo_criado_em', financeiro.iso_python(p_c.logo_criado_em),
        'logo_url', case when nullif(p_c.logo_arquivo, '') is not null then '/api/categorias/' || p_c.id || '/logo' end,
        'ativo', p_c.ativo, 'sistemica', coalesce(p_c.sistemica, false), 'codigo_sistema', p_c.codigo_sistema,
        'modulo_origem', p_c.modulo_origem, 'bloquear_edicao', coalesce(p_c.bloquear_edicao, false),
        'bloquear_exclusao', coalesce(p_c.bloquear_exclusao, false), 'criado_em', financeiro.iso_python(p_c.criado_em))
$$;

-- DespesaPrevista.to_dict. Interna.
create function financeiro.despesa_prevista_flask(p_d public.despesa_prevista)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_d.id, 'perfil_financeiro_id', p_d.perfil_financeiro_id, 'origem_tipo', p_d.origem_tipo,
        'origem_id', p_d.origem_id, 'categoria_id', p_d.categoria_id,
        'categoria', (select financeiro.categoria_flask(c) from public.categoria c where c.id = p_d.categoria_id),
        'data_original_prevista', p_d.data_original_prevista, 'data_atual_prevista', p_d.data_atual_prevista,
        'data_prevista', p_d.data_prevista, 'valor_previsto', p_d.valor_previsto, 'status', p_d.status,
        'metadata', jsonb_build_object('ciclo_id', null, 'ordem_no_ciclo', null) || md,
        'tipo_evento', md -> 'tipo_evento')
      from (select case when jsonb_typeof(financeiro.json_seguro((p_d).metadata)) = 'object'
                        then financeiro.json_seguro((p_d).metadata) else '{}'::jsonb end md) x
$$;

-- Hoje em Brasilia (o Flask usa date.today() da maquina). Interna.
create function financeiro.hoje_brasilia()
    returns date
    language sql
    stable
    set search_path = ''
as $$
    select (now() at time zone 'America/Sao_Paulo')::date
$$;

-- Veiculo do perfil (NULL se nao existe ou e de outro perfil). Interna.
create function financeiro.veiculo_do_perfil(p_perfil_id integer, p_veiculo_id integer)
    returns public.veiculo
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select v from public.veiculo v
     where v.id = p_veiculo_id and financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)
$$;

-- serializar_veiculo_mobilidade: Veiculo.to_dict + resumo mensal estimado (anuais diluidos por 12, ROUND_HALF_UP).
create function financeiro.veiculo_flask(p_v public.veiculo)
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

-- calcular_resumo_uso (veiculo_uso_service): km por mes inferido das despesas de combustivel CONFIRMADAS. Interna.
create function financeiro.uso_do_veiculo(p_v public.veiculo, p_janela integer)
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

-- VeiculoRegraManutencaoKm.to_dict. Interna.
create function financeiro.regra_km_flask(p_r public.veiculo_regra_manutencao_km)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_r.id, 'perfil_financeiro_id', p_r.perfil_financeiro_id, 'veiculo_id', p_r.veiculo_id,
        'tipo_evento', p_r.tipo_evento, 'intervalo_km', p_r.intervalo_km, 'meses_intervalo', p_r.meses_intervalo,
        'custo_estimado', p_r.custo_estimado, 'categoria_id', p_r.categoria_id,
        'categoria', (select financeiro.categoria_flask(c) from public.categoria c where c.id = p_r.categoria_id),
        'ativo', coalesce(p_r.ativo, false), 'criado_em', financeiro.iso_python(p_r.criado_em),
        'atualizado_em', financeiro.iso_python(p_r.atualizado_em))
$$;

-- ItemDespesa.to_dict (recorrencia da modalidade ativa). Interna.
create function financeiro.item_despesa_flask(p_i public.item_despesa)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_i.id, 'perfil_financeiro_id', p_i.perfil_financeiro_id, 'categoria_id', p_i.categoria_id, 'nome', p_i.nome,
        'tipo', p_i.tipo, 'descricao', p_i.descricao, 'ativo', p_i.ativo, 'valor', nullif(p_i.valor, 0),
        'valor_pago', nullif(p_i.valor_pago, 0), 'data_vencimento', p_i.data_vencimento, 'data_pagamento', p_i.data_pagamento,
        'pago', p_i.pago, 'recorrente', p_i.recorrente, 'tipo_recorrencia', p_i.tipo_recorrencia,
        'mes_competencia', p_i.mes_competencia, 'meio_pagamento', p_i.meio_pagamento, 'cartao_id', p_i.cartao_id,
        'conta_bancaria_id', p_i.conta_bancaria_id, 'item_agregado_id', p_i.item_agregado_id, 'origem_tipo', p_i.origem_tipo,
        'origem_id', p_i.origem_id, 'origem_contexto', p_i.origem_contexto, 'categoria_cartao_id', p_i.categoria_cartao_id)
        || coalesce((select jsonb_build_object('categoria', jsonb_build_object(
                         'id', c.id, 'nome', c.nome, 'icone', c.icone,
                         'logo_url', case when nullif(c.logo_arquivo, '') is not null then '/api/categorias/' || c.id || '/logo' end))
                       from public.categoria c where c.id = p_i.categoria_id), '{}'::jsonb)
        || coalesce((select jsonb_build_object('cartao', jsonb_build_object('id', k.id, 'nome', k.nome))
                       from public.item_despesa k where k.id = p_i.cartao_id), '{}'::jsonb)
        || coalesce((select jsonb_build_object('item_agregado', jsonb_build_object('id', a.id, 'nome', a.nome))
                       from public.item_agregado a where a.id = p_i.item_agregado_id), '{}'::jsonb)
$$;

-- Configuracao do caminho de transporte por app: metadata.caminho da ultima prevista da origem. Interna.
create function financeiro.caminho_app_md(p_perfil_id integer, p_origem_id integer)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select financeiro.json_seguro(d.metadata)
      from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.origem_tipo = 'TRANSPORTE_APP' and d.origem_id = p_origem_id
     order by d.id desc limit 1
$$;

-- GET /api/categorias (Categoria de Despesa e global no Flask; contagem de palavras-chave ativas).
create function financeiro.mobilidade_categorias_tela(p_perfil_id integer)
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
    return coalesce((select jsonb_agg(financeiro.categoria_flask(c) || jsonb_build_object(
                                          'palavras_chave_count', (select count(*) from public.categoria_palavra_chave k
                                                                    where k.categoria_id = c.id and k.ativo))
                                      order by c.id)
                       from public.categoria c), '[]'::jsonb);
end
$$;

-- GET /api/veiculos e /api/veiculos/<id> (p_id), mais recentes primeiro.
create function financeiro.veiculos_tela(p_perfil_id integer, p_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_v public.veiculo;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_id is not null then
        v_v := financeiro.veiculo_do_perfil(p_perfil_id, p_id);
        if v_v.id is null then
            raise exception 'Veículo não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
        end if;
        return financeiro.veiculo_flask(v_v);
    end if;
    return coalesce((select jsonb_agg(financeiro.veiculo_flask(v) order by v.id desc) from public.veiculo v
                      where financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb);
end
$$;

-- GET /api/veiculos/<id>/projecoes?meses= e /api/mobilidade-app/<id>/projecoes?meses= (p_origem_tipo VEICULO ou
-- TRANSPORTE_APP): previstas ja geradas das proximas N competencias. O veiculo precisa existir; o caminho, nao.
create function financeiro.projecoes_mobilidade_tela(p_perfil_id integer, p_origem_tipo text, p_origem_id integer, p_meses integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_inicio date := date_trunc('month', financeiro.hoje_brasilia())::date;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_origem_tipo not in ('VEICULO', 'TRANSPORTE_APP') then
        raise exception 'Origem invalida' using errcode = '22023';
    end if;
    if p_origem_tipo = 'VEICULO' and (financeiro.veiculo_do_perfil(p_perfil_id, p_origem_id)).id is null then
        raise exception 'Veículo não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return coalesce((select jsonb_agg(financeiro.despesa_prevista_flask(d) order by d.data_prevista, d.id)
                       from public.despesa_prevista d
                      where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                        and d.origem_tipo = p_origem_tipo and d.origem_id = p_origem_id
                        and d.data_prevista >= v_inicio
                        and d.data_prevista < (v_inicio + make_interval(months => greatest(coalesce(p_meses, 24), 1)))::date),
                    '[]'::jsonb);
end
$$;

-- GET /api/veiculos/<id>/uso?janela_meses=
create function financeiro.veiculo_uso_tela(p_perfil_id integer, p_veiculo_id integer, p_janela integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_v public.veiculo;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_v := financeiro.veiculo_do_perfil(p_perfil_id, p_veiculo_id);
    if v_v.id is null then
        raise exception 'Veículo não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return financeiro.uso_do_veiculo(v_v, p_janela);
end
$$;

-- GET /api/veiculos/<id>/regras-km
create function financeiro.veiculo_regras_km_tela(p_perfil_id integer, p_veiculo_id integer)
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
    if (financeiro.veiculo_do_perfil(p_perfil_id, p_veiculo_id)).id is null then
        raise exception 'Veículo não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return coalesce((select jsonb_agg(financeiro.regra_km_flask(r) order by r.id) from public.veiculo_regra_manutencao_km r
                      where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id) and r.veiculo_id = p_veiculo_id),
                    '[]'::jsonb);
end
$$;

-- GET /api/veiculos/<id>/manutencoes-km?janela_meses= (listar_estimativas + calcular_impacto_mensal_manutencao).
create function financeiro.veiculo_manutencoes_km_tela(p_perfil_id integer, p_veiculo_id integer, p_janela integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_v        public.veiculo;
    v_janela   integer := coalesce(p_janela, 3);
    v_hoje     date := financeiro.hoje_brasilia();
    v_km_atual numeric;
    v_km_mes   numeric;
    v_fonte    text;
    v_obs      text;
    v_itens    jsonb := '[]'::jsonb;
    v_total    numeric := 0;
    v_fonte_i  text := 'INDISPONIVEL';
    v_r        public.veiculo_regra_manutencao_km;
    v_rest     numeric;
    v_meses    integer;
    v_data     date;
    v_exist    public.despesa_prevista;
    v_mod      numeric;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_v := financeiro.veiculo_do_perfil(p_perfil_id, p_veiculo_id);
    if v_v.id is null then
        raise exception 'Veículo não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    v_km_atual := coalesce(v_v.km_estimado_acumulado, 0);
    -- _calcular_km_mes_estimado: historico (media movel) > projetado (combustivel mensal / preco * autonomia).
    v_km_mes := ((financeiro.uso_do_veiculo(v_v, v_janela)) ->> 'media_movel_km_mes')::numeric;
    if v_km_mes > 0 then
        v_fonte := 'HISTORICO';
        v_obs := 'Baseado no uso estimado (histórico via consumo). Pode variar.';
    elsif coalesce(v_v.combustivel_valor_mensal, 0) > 0 and coalesce(v_v.preco_medio_combustivel, 0) > 0
          and coalesce(v_v.autonomia_km_l, 0) > 0 then
        v_km_mes := v_v.combustivel_valor_mensal / v_v.preco_medio_combustivel * v_v.autonomia_km_l;
        v_fonte := 'PROJETADO';
        v_obs := 'Baseado em uso projetado (combustível mensal, preço médio e autonomia). Pode variar.';
    else
        v_km_mes := 0;
        v_fonte := 'INDISPONIVEL';
        v_obs := 'Sem dados suficientes para estimar uso mensal. Informe combustível mensal e preço médio, ou gere histórico.';
    end if;

    for v_r in select * from public.veiculo_regra_manutencao_km r
                where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id) and r.veiculo_id = v_v.id and r.ativo
                order by r.id
    loop
        select d.* into v_exist from public.despesa_prevista d
         where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
           and d.origem_tipo = 'VEICULO' and d.origem_id = v_v.id and d.status in ('PREVISTA', 'ADIADA', 'CONFIRMADA')
           and financeiro.json_seguro(d.metadata) ->> 'tipo_evento' = v_r.tipo_evento
         order by d.id limit 1;
        -- _calcular_km_restante
        if coalesce(v_r.intervalo_km, 0) <= 0 then
            v_rest := 0;
        elsif v_km_atual <= 0 then
            v_rest := v_r.intervalo_km;
        else
            v_mod := mod(v_km_atual, v_r.intervalo_km::numeric);
            v_rest := case when v_mod = 0 then 0 else v_r.intervalo_km - v_mod end;
        end if;
        v_meses := null;
        v_data := null;
        if v_km_mes > 0 and v_rest > 0 then
            v_meses := ceil(v_rest / v_km_mes)::integer;
            v_data := date_trunc('month', v_hoje + make_interval(months => v_meses))::date;
        elsif v_km_mes > 0 and v_rest = 0 then
            v_meses := 0;
            v_data := date_trunc('month', v_hoje)::date;
        end if;
        v_itens := v_itens || jsonb_build_array(jsonb_build_object(
            'regra_id', v_r.id, 'tipo_evento', v_r.tipo_evento, 'intervalo_km', v_r.intervalo_km,
            'meses_intervalo', v_r.meses_intervalo, 'custo_estimado', v_r.custo_estimado, 'categoria_id', v_r.categoria_id,
            'km_atual_estimado', v_km_atual, 'km_restante', v_rest, 'media_movel_km_mes', v_km_mes,
            'meses_estimados', v_meses, 'data_prevista_estimada', v_data,
            'existe_evento', v_exist.id is not null, 'evento_existente_id', v_exist.id,
            'evento_existente_status', v_exist.status));
        -- calcular_impacto_mensal_manutencao
        if coalesce(v_r.custo_estimado, 0) > 0 then
            if v_km_mes > 0 and coalesce(v_r.intervalo_km, 0) > 0 then
                v_total := v_total + v_r.custo_estimado * (v_km_mes / v_r.intervalo_km);
                v_fonte_i := 'KM';
            elsif coalesce(v_r.meses_intervalo, 0) > 0 then
                v_total := v_total + v_r.custo_estimado / v_r.meses_intervalo;
                if v_fonte_i <> 'KM' then
                    v_fonte_i := 'TEMPO';
                end if;
            end if;
        end if;
    end loop;

    return jsonb_build_object(
        'veiculo_id', v_v.id, 'janela_meses', v_janela, 'observacao', v_obs, 'fonte_uso', v_fonte, 'km_mes_estimado', v_km_mes,
        'regras', coalesce((select jsonb_agg(financeiro.regra_km_flask(r) order by r.id) from public.veiculo_regra_manutencao_km r
                             where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
                               and r.veiculo_id = v_v.id and r.ativo), '[]'::jsonb),
        'estimativas', v_itens, 'impacto_mensal_total', v_total, 'fonte_impacto', v_fonte_i,
        'observacao_impacto', case v_fonte_i when 'KM' then 'Impacto mensal estimado via km (uso estimado/projetado). Pode variar.'
                                             when 'TEMPO' then 'Impacto mensal estimado via intervalo informado (meses). Pode variar.' end,
        'tipos_evento_regras', coalesce((select jsonb_agg(r.tipo_evento order by r.id) from public.veiculo_regra_manutencao_km r
                                          where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
                                            and r.veiculo_id = v_v.id and r.ativo), '[]'::jsonb));
end
$$;

-- GET /api/veiculos/<id>/financiamento (null se nao ha).
create function financeiro.veiculo_financiamento_tela(p_perfil_id integer, p_veiculo_id integer)
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
    return (select jsonb_build_object(
                'id', f.id, 'veiculo_id', f.veiculo_id, 'valor_bem', f.valor_bem, 'entrada', coalesce(f.entrada, 0),
                'valor_financiado', f.valor_financiado, 'numero_parcelas', f.numero_parcelas,
                'taxa_juros_mensal', f.taxa_juros_mensal, 'indexador_tipo', f.indexador_tipo,
                'iof_percentual', coalesce(f.iof_percentual, 0), 'iof_valor', coalesce(f.iof_valor, 0),
                'categoria_id', f.categoria_id, 'custo_total_financiamento', coalesce(f.custo_total_financiamento, 0),
                'criado_em', financeiro.iso_python(f.criado_em), 'atualizado_em', financeiro.iso_python(f.atualizado_em))
              from public.veiculo_financiamento f
             where financeiro.pertence_ao_perfil(f.perfil_financeiro_id, p_perfil_id) and f.veiculo_id = p_veiculo_id
             order by f.id limit 1);
end
$$;

-- GET /api/veiculos/mobilidade/ativo (obter_modalidade_ativa; null se nao ha).
create function financeiro.mobilidade_ativa_tela(p_perfil_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_c     public.mobilidade_cenario_ativo;
    v_dados jsonb;
    v_md    jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_c from public.mobilidade_cenario_ativo c
     where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and c.status = 'ATIVO'
     order by c.id limit 1;
    if not found then
        return null;
    end if;
    v_dados := jsonb_build_object(
        'id', v_c.id, 'perfil_financeiro_id', v_c.perfil_financeiro_id, 'tipo_modalidade', v_c.tipo_modalidade,
        'origem_id', v_c.origem_id, 'ativo_desde', v_c.ativo_desde, 'meio_pagamento', v_c.meio_pagamento,
        'cartao_id', v_c.cartao_id, 'categoria_id', v_c.categoria_id, 'categoria_cartao_id', v_c.categoria_cartao_id,
        'recorrencia_id', v_c.recorrencia_id, 'status', v_c.status,
        'created_at', financeiro.iso_python(v_c.created_at), 'updated_at', financeiro.iso_python(v_c.updated_at));
    if coalesce(v_c.origem_id, 0) <> 0 then
        if v_c.tipo_modalidade = 'VEICULO' then
            v_dados := v_dados || jsonb_build_object('nome_origem', (financeiro.veiculo_do_perfil(p_perfil_id, v_c.origem_id)).nome);
        elsif v_c.tipo_modalidade = 'TRANSPORTE_APP' then
            v_md := financeiro.caminho_app_md(p_perfil_id, v_c.origem_id);
            v_dados := v_dados || jsonb_build_object('nome_origem',
                coalesce(nullif(case when jsonb_typeof(v_md -> 'caminho') = 'object' then v_md -> 'caminho' ->> 'nome' end, ''),
                         'Caminho ' || v_c.origem_id));
        elsif v_c.tipo_modalidade = 'ASSINATURA' then
            v_dados := v_dados || jsonb_build_object('nome_origem', (select a.nome from public.mobilidade_assinatura a
                                                                    where a.id = v_c.origem_id
                                                                      and financeiro.pertence_ao_perfil(a.perfil_financeiro_id, p_perfil_id)));
        end if;
    end if;
    if v_c.recorrencia_id is not null then
        v_dados := v_dados || jsonb_build_object('recorrencia', (select financeiro.item_despesa_flask(i) from public.item_despesa i
                                                                 where i.id = v_c.recorrencia_id
                                                                   and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)));
    end if;
    return v_dados;
end
$$;

-- GET /api/veiculos/mobilidade/assinaturas[?apenas_ativas=] (por nome).
create function financeiro.mobilidade_assinaturas_tela(p_perfil_id integer, p_apenas_ativas boolean)
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
    return coalesce((select jsonb_agg(jsonb_build_object(
                                'id', a.id, 'perfil_financeiro_id', a.perfil_financeiro_id, 'nome', a.nome,
                                'valor_mensal', a.valor_mensal, 'categoria_id', a.categoria_id, 'status', a.status,
                                'created_at', financeiro.iso_python(a.created_at), 'updated_at', financeiro.iso_python(a.updated_at))
                            order by a.nome, a.id)
                       from public.mobilidade_assinatura a
                      where financeiro.pertence_ao_perfil(a.perfil_financeiro_id, p_perfil_id)
                        and (not coalesce(p_apenas_ativas, false) or a.status = 'ATIVO')), '[]'::jsonb);
end
$$;

-- GET /api/mobilidade-app (caminhos, id desc) e /api/mobilidade-app/<id> (p_id): configuracao na ultima prevista.
create function financeiro.transporte_app_tela(p_perfil_id integer, p_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_md jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_id is not null then
        v_md := financeiro.caminho_app_md(p_perfil_id, p_id);
        if v_md is null then
            raise exception 'Caminho não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
        end if;
        return jsonb_build_object('id', p_id)
               || case when jsonb_typeof(v_md -> 'caminho') = 'object' then v_md -> 'caminho' else '{}'::jsonb end;
    end if;
    return coalesce((
        select jsonb_agg(jsonb_build_object(
                   'id', o.origem_id,
                   'nome', btrim(coalesce(nullif(c ->> 'nome', ''), 'Caminho ' || o.origem_id)),
                   'km_mensal_estimado', coalesce(nullif(financeiro.numero_seguro(c -> 'km_mensal_estimado'), 0), 0),
                   'preco_medio_por_km', coalesce(nullif(financeiro.numero_seguro(c -> 'preco_medio_por_km'), 0), 0),
                   'valor_mensal', coalesce(nullif(financeiro.numero_seguro(md -> 'calculo' -> 'valor_mensal'), 0),
                                            nullif(ultimo.valor_previsto, 0), 0))
               order by o.origem_id desc)
          from (select distinct d.origem_id from public.despesa_prevista d
                 where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                   and d.origem_tipo = 'TRANSPORTE_APP' and d.origem_id is not null) o
          cross join lateral (select d.* from public.despesa_prevista d
                               where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                                 and d.origem_tipo = 'TRANSPORTE_APP' and d.origem_id = o.origem_id
                               order by d.id desc limit 1) ultimo
          cross join lateral (select financeiro.json_seguro(ultimo.metadata) md) m
          cross join lateral (select case when jsonb_typeof(m.md -> 'caminho') = 'object' then m.md -> 'caminho'
                                          else '{}'::jsonb end c) cc), '[]'::jsonb);
end
$$;

revoke execute on function financeiro.json_seguro(text) from public, anon, authenticated;
revoke execute on function financeiro.numero_seguro(jsonb) from public, anon, authenticated;
revoke execute on function financeiro.categoria_flask(public.categoria) from public, anon, authenticated;
revoke execute on function financeiro.despesa_prevista_flask(public.despesa_prevista) from public, anon, authenticated;
revoke execute on function financeiro.hoje_brasilia() from public, anon, authenticated;
revoke execute on function financeiro.veiculo_do_perfil(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.veiculo_flask(public.veiculo) from public, anon, authenticated;
revoke execute on function financeiro.uso_do_veiculo(public.veiculo, integer) from public, anon, authenticated;
revoke execute on function financeiro.regra_km_flask(public.veiculo_regra_manutencao_km) from public, anon, authenticated;
revoke execute on function financeiro.item_despesa_flask(public.item_despesa) from public, anon, authenticated;
revoke execute on function financeiro.caminho_app_md(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mobilidade_categorias_tela(integer) from public, anon;
revoke execute on function financeiro.veiculos_tela(integer, integer) from public, anon;
revoke execute on function financeiro.projecoes_mobilidade_tela(integer, text, integer, integer) from public, anon;
revoke execute on function financeiro.veiculo_uso_tela(integer, integer, integer) from public, anon;
revoke execute on function financeiro.veiculo_regras_km_tela(integer, integer) from public, anon;
revoke execute on function financeiro.veiculo_manutencoes_km_tela(integer, integer, integer) from public, anon;
revoke execute on function financeiro.veiculo_financiamento_tela(integer, integer) from public, anon;
revoke execute on function financeiro.mobilidade_ativa_tela(integer) from public, anon;
revoke execute on function financeiro.mobilidade_assinaturas_tela(integer, boolean) from public, anon;
revoke execute on function financeiro.transporte_app_tela(integer, integer) from public, anon;
grant execute on function financeiro.mobilidade_categorias_tela(integer) to authenticated;
grant execute on function financeiro.veiculos_tela(integer, integer) to authenticated;
grant execute on function financeiro.projecoes_mobilidade_tela(integer, text, integer, integer) to authenticated;
grant execute on function financeiro.veiculo_uso_tela(integer, integer, integer) to authenticated;
grant execute on function financeiro.veiculo_regras_km_tela(integer, integer) to authenticated;
grant execute on function financeiro.veiculo_manutencoes_km_tela(integer, integer, integer) to authenticated;
grant execute on function financeiro.veiculo_financiamento_tela(integer, integer) to authenticated;
grant execute on function financeiro.mobilidade_ativa_tela(integer) to authenticated;
grant execute on function financeiro.mobilidade_assinaturas_tela(integer, boolean) to authenticated;
grant execute on function financeiro.transporte_app_tela(integer, integer) to authenticated;
