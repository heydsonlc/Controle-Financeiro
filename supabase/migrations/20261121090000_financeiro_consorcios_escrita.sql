-- FIN-CONTRATOS-3 (fase A) — cadastro, edicao, regeneracao segura e exclusao de consorcios no novo aplicativo.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261121090000).
-- Validada em cluster local descartavel, comparada com o PROPRIO Flask (tests/test_supabase_consorcios_escrita.py).
-- Docs: docs/FIN_CONTRATOS_3.md.
--
-- Regras do Flask (routes/consorcios.py, services/consorcio_receita_service.py), nas mesmas tabelas:
-- - contrato em public.contrato_consorcio; cada parcela = item_despesa tipo 'Consorcio' "<nome> - Parcela i/n" + a sua
--   despesa (public.conta, vencimento dia 5, numero/total da parcela); valor = inicial com reajuste fixo ou percentual
--   por passo (normalizar_dados_consorcio, calcular_valor_parcela_consorcio, arredondamento meio para cima);
-- - premio = parcela da posicao de contemplacao x numero de parcelas; receita de contemplacao = recebimento sem conta
--   (marcador consorcio_id=N), na fonte "Contemplação de Consórcio" do perfil;
-- - edicao nao regenera parcelas (como o Flask); meio de pagamento vale para as parcelas.
-- Correcoes em relacao ao Flask (defeitos que NAO sao reproduzidos):
-- - REGENERAR: o Flask apaga todas as despesas do contrato, inclusive pagas. Aqui parcela paga ou com qualquer
--   movimento (inclusive estornado) fica intacta; so as pendentes sem movimento sao atualizadas, criadas ou removidas,
--   tudo numa transacao, com o contrato travado;
-- - EXCLUIR: so remove despesa pendente SEM movimento (o Flask apaga pendente mesmo com pagamento estornado);
-- - meio de pagamento: so muda despesas pendentes (o Flask regrava a conta bancaria de despesas ja pagas);
-- - receita de contemplacao ja confirmada (com movimento) nao e reescrita (o Flask muda valor e data dela);
-- - renomear o contrato renomeia as parcelas (o Flask perde o vinculo, que e pelo nome) e nome repetido entre
--   consorcios ativos do perfil e recusado (dois contratos com o mesmo nome misturariam parcelas).
-- Escrita: gestao do perfil + escritor unico (financeiro.exigir_pagamento_novo: perfil ainda no Flask = recusa) +
-- cadastros de consorcio do perfil em serie; criacao idempotente pela chave. Nenhuma tabela nova.

-- 1. Calculo (Flask) -------------------------------------------------------------------------------------------------

-- calcular_valor_parcela_consorcio. Interna.
create function financeiro.consorcio_valor_parcela(p_inicial numeric, p_tipo text, p_reajuste numeric, p_posicao integer)
    returns numeric
    language sql
    immutable
    set search_path = ''
as $$
    select round(case
        when p_tipo = 'fixo' and coalesce(p_reajuste, 0) > 0 then p_inicial + (p_posicao - 1) * p_reajuste
        when p_tipo = 'percentual' and coalesce(p_reajuste, 0) > 0 then p_inicial * (1 + ((p_posicao - 1) * p_reajuste) / 100)
        else p_inicial end, 2)
$$;

-- Mes de referencia (normalizar_mes_referencia): YYYY-MM-DD, YYYY-MM, M/YYYY ou so o mes (com a base). Interna.
create function financeiro.consorcio_mes(p_valor text, p_base date, p_campo text)
    returns date
    language plpgsql
    stable
    set search_path = ''
as $$
declare
    v_texto text := btrim(coalesce(p_valor, ''));
    v_rotulo text := case when p_campo = 'mes_inicio' then 'inicio' else 'contemplacao' end;
    v_mes integer;
    v_base date := coalesce(p_base, financeiro.hoje_brasilia());
    v_ano integer;
begin
    if v_texto = '' then
        return null;
    end if;
    begin
        if v_texto ~ '^\d{4}-\d{2}-\d{2}$' then
            return date_trunc('month', to_date(v_texto, 'YYYY-MM-DD')::timestamp)::date;
        elsif v_texto ~ '^\d{4}-\d{2}$' then
            return to_date(v_texto || '-01', 'YYYY-MM-DD');
        elsif v_texto ~ '^\d{1,2}/\d{4}$' then
            v_mes := split_part(v_texto, '/', 1)::integer;
            if v_mes not between 1 and 12 then
                raise exception 'mes';
            end if;
            return make_date(split_part(v_texto, '/', 2)::integer, v_mes, 1);
        elsif v_texto ~ '^\d{1,2}$' then
            v_mes := v_texto::integer;
            if v_mes not between 1 and 12 then
                raise exception 'mes';
            end if;
            v_ano := extract(year from v_base)::integer;
            if p_campo = 'mes_contemplacao' and v_mes < extract(month from v_base) then
                v_ano := v_ano + 1;
            end if;
            return make_date(v_ano, v_mes, 1);
        end if;
    exception when others then
        raise exception 'Mes de % invalido. Informe um mes entre 1 e 12.', v_rotulo using errcode = '22023';
    end;
    raise exception 'Mes de % invalido. Informe uma data no formato YYYY-MM, YYYY-MM-DD ou mes entre 1 e 12.', v_rotulo
        using errcode = '22023';
end
$$;

-- normalizar_dados_consorcio (com o contrato atual na edicao). Interna.
create function financeiro.consorcio_normalizar(p_dados jsonb, p_atual public.contrato_consorcio)
    returns jsonb
    language plpgsql
    stable
    set search_path = ''
as $$
declare
    v_n        integer;
    v_inicial  numeric;
    v_tipo     text;
    v_reajuste numeric;
    v_ini_txt  text;
    v_cont_txt text;
    v_base_ini date;
    v_base_ct  date;
    v_mes_num  integer;
    v_base     date;
    v_inicio   date;
    v_contemp  date;
    v_posicao  integer;
    v_premio   numeric;

    function_data constant text := '^\d{4}-\d{2}(-\d{2})?$';
begin
    begin
        v_n := coalesce(nullif(p_dados ->> 'numero_parcelas', '')::numeric::integer, p_atual.numero_parcelas, 0);
        v_inicial := round(coalesce(nullif(p_dados ->> 'valor_inicial', '')::numeric, p_atual.valor_inicial, 0), 2);
        v_reajuste := round(coalesce(nullif(p_dados ->> 'valor_reajuste', '')::numeric, p_atual.valor_reajuste, 0), 2);
    exception when others then
        raise exception 'Valores do consorcio invalidos' using errcode = '22023';
    end;
    if v_n < 1 then
        raise exception 'Numero de parcelas deve ser maior que zero.' using errcode = '22023';
    end if;
    v_tipo := coalesce(case when p_dados ? 'tipo_reajuste' then p_dados ->> 'tipo_reajuste' end, p_atual.tipo_reajuste, 'nenhum');
    v_ini_txt := coalesce(case when p_dados ? 'mes_inicio' then p_dados ->> 'mes_inicio' end, p_atual.mes_inicio::text);
    v_cont_txt := case when p_dados ? 'mes_contemplacao' then p_dados ->> 'mes_contemplacao' else p_atual.mes_contemplacao::text end;
    -- _data_base_de_valor de data_inicial / data_vencimento e do mes de contemplacao (so formatos de data)
    v_base_ini := coalesce(
        case when coalesce(p_dados ->> 'data_inicial', '') ~ function_data then date_trunc('month', (p_dados ->> 'data_inicial' || case when length(p_dados ->> 'data_inicial') = 7 then '-01' else '' end)::date::timestamp)::date end,
        case when coalesce(p_dados ->> 'data_vencimento', '') ~ function_data then date_trunc('month', (p_dados ->> 'data_vencimento' || case when length(p_dados ->> 'data_vencimento') = 7 then '-01' else '' end)::date::timestamp)::date end);
    v_base_ct := case when coalesce(v_cont_txt, '') ~ function_data
                      then date_trunc('month', (v_cont_txt || case when length(v_cont_txt) = 7 then '-01' else '' end)::date::timestamp)::date end;
    v_mes_num := case when coalesce(v_ini_txt, '') ~ '^\d{1,2}$' and v_ini_txt::integer between 1 and 12 then v_ini_txt::integer end;
    v_base := coalesce(v_base_ini, p_atual.mes_inicio);
    if v_base is null and v_base_ct is not null then
        v_base := case when v_mes_num is not null and v_mes_num > extract(month from v_base_ct)
                       then make_date(extract(year from v_base_ct)::integer - 1, v_mes_num, 1) else v_base_ct end;
    end if;
    v_base := coalesce(v_base, financeiro.hoje_brasilia());
    if nullif(btrim(coalesce(v_ini_txt, '')), '') is null and v_base_ini is not null then
        v_ini_txt := v_base_ini::text;
    end if;
    v_inicio := financeiro.consorcio_mes(v_ini_txt, v_base, 'mes_inicio');
    if v_inicio is null then
        raise exception 'Mes de inicio e obrigatorio.' using errcode = '22023';
    end if;
    v_contemp := financeiro.consorcio_mes(v_cont_txt, v_inicio, 'mes_contemplacao');
    if v_contemp is not null then
        v_posicao := (extract(year from v_contemp) - extract(year from v_inicio)) * 12
                     + (extract(month from v_contemp) - extract(month from v_inicio)) + 1;
        if v_posicao < 1 or v_posicao > v_n then
            raise exception 'Mes de contemplacao deve estar dentro do periodo do consorcio.' using errcode = '22023';
        end if;
        v_premio := round(financeiro.consorcio_valor_parcela(v_inicial, v_tipo, v_reajuste, v_posicao) * v_n, 2);
    end if;
    return jsonb_build_object('valor_inicial', v_inicial, 'tipo_reajuste', v_tipo, 'valor_reajuste', v_reajuste,
                              'numero_parcelas', v_n, 'mes_inicio', v_inicio, 'mes_contemplacao', v_contemp,
                              'posicao_contemplacao', v_posicao, 'valor_premio', v_premio);
end
$$;

-- normalizar_pagamento_consorcio. Interna.
create function financeiro.consorcio_pagamento(p_dados jsonb)
    returns jsonb
    language sql
    immutable
    set search_path = ''
as $$
    select jsonb_build_object(
        'meio_pagamento', m.meio,
        'cartao_id', case when m.meio = 'cartao' then nullif(p_dados ->> 'cartao_id', '')::integer end,
        'categoria_cartao_id', case when m.meio = 'cartao' then nullif(p_dados ->> 'categoria_cartao_id', '')::integer end,
        'conta_bancaria_id', case when m.meio = 'debito_automatico' then nullif(p_dados ->> 'conta_bancaria_id', '')::integer end)
      from (select nullif(lower(btrim(coalesce(p_dados ->> 'meio_pagamento', ''))), '') meio) m
$$;

-- Posicao da parcela pelo nome "<prefixo> - Parcela i/n" (um dos prefixos do contrato), ou nulo. Interna.
create function financeiro.posicao_parcela_consorcio(p_nome text, p_prefixos text[])
    returns integer
    language sql
    immutable
    set search_path = ''
as $$
    select min(substring(substr(p_nome, length(p) + 12) from '^(\d+)/\d+$')::integer)
      from unnest(p_prefixos) p
     where left(p_nome, length(p) + 11) = p || ' - Parcela '
$$;

-- Despesa efetivada: paga ou com qualquer movimento (inclusive estornado). Interna.
create function financeiro.despesa_efetivada(p_conta_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from public.conta c where c.id = p_conta_id and c.status_pagamento = 'Pago')
        or exists (select 1 from public.movimento_financeiro m where m.conta_id = p_conta_id)
$$;

-- 2. Parcelas (geracao e regeneracao seguras) ----------------------------------------------------------------------

-- Gera ou ajusta as parcelas do contrato: posicao 1..n com o valor e o vencimento do contrato; parcela efetivada fica
-- intacta; pendente sem movimento e atualizada; faltante e criada; acima de n, pendente sem movimento e removida.
-- p_prefixos: nomes do contrato (o atual e, na renomeacao, o anterior). Interna.
create function financeiro.sincronizar_parcelas_consorcio(p_c public.contrato_consorcio, p_categoria integer, p_pag jsonb,
                                                          p_prefixos text[])
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_perfil integer := financeiro.perfil_do_consorcio(p_c);
    v_prefixos text[] := array_append(coalesce(p_prefixos, '{}'), p_c.nome);
    v_meio   text := p_pag ->> 'meio_pagamento';
    v_item   public.item_despesa;
    v_conta  public.conta;
    v_mes    date;
    v_venc   date;
    v_valor  numeric;
    v_nome   text;
    v_cont   jsonb := jsonb_build_object('criadas', 0, 'atualizadas', 0, 'preservadas', 0, 'removidas', 0);
    v_id     integer;
begin
    for i in 1..p_c.numero_parcelas loop
        v_mes := (p_c.mes_inicio + make_interval(months => i - 1))::date;
        v_venc := v_mes + 4;
        v_valor := financeiro.consorcio_valor_parcela(p_c.valor_inicial, p_c.tipo_reajuste, p_c.valor_reajuste, i);
        v_nome := p_c.nome || ' - Parcela ' || i || '/' || p_c.numero_parcelas;
        select * into v_item from public.item_despesa d
         where d.tipo = 'Consorcio' and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
           and financeiro.posicao_parcela_consorcio(d.nome, v_prefixos) = i
         order by d.id limit 1 for update;
        if not found then
            insert into public.item_despesa (perfil_financeiro_id, nome, descricao, valor, data_vencimento, categoria_id, pago,
                                             recorrente, tipo, mes_competencia, meio_pagamento, cartao_id, categoria_cartao_id,
                                             conta_bancaria_id, ativo, criado_em)
            values (v_perfil, v_nome, 'Parcela ' || i || ' do consórcio ' || p_c.nome, v_valor, v_venc, p_categoria, false, false,
                    'Consorcio', to_char(v_mes, 'YYYY-MM'), v_meio, (p_pag ->> 'cartao_id')::integer,
                    (p_pag ->> 'categoria_cartao_id')::integer, (p_pag ->> 'conta_bancaria_id')::integer, true,
                    now() at time zone 'utc')
            returning id into v_id;
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento,
                                      status_pagamento, debito_automatico, conta_bancaria_id, numero_parcela, total_parcelas,
                                      is_fatura_cartao, estouro_orcamento, status_fatura)
            values (v_perfil, v_id, v_mes, v_nome, v_valor, v_venc, 'Pendente', coalesce(v_meio, '') = 'debito_automatico',
                    (p_pag ->> 'conta_bancaria_id')::integer, i, p_c.numero_parcelas, false, false, 'ABERTA');
            v_cont := jsonb_set(v_cont, '{criadas}', to_jsonb((v_cont ->> 'criadas')::integer + 1));
            continue;
        end if;
        select * into v_conta from public.conta c where c.item_despesa_id = v_item.id order by c.id limit 1 for update;
        if v_conta.id is not null and financeiro.despesa_efetivada(v_conta.id) then
            v_cont := jsonb_set(v_cont, '{preservadas}', to_jsonb((v_cont ->> 'preservadas')::integer + 1));
            continue;
        end if;
        update public.item_despesa
           set nome = v_nome, descricao = 'Parcela ' || i || ' do consórcio ' || p_c.nome, valor = v_valor, data_vencimento = v_venc,
               categoria_id = p_categoria, mes_competencia = to_char(v_mes, 'YYYY-MM'), meio_pagamento = v_meio,
               cartao_id = (p_pag ->> 'cartao_id')::integer, categoria_cartao_id = (p_pag ->> 'categoria_cartao_id')::integer,
               conta_bancaria_id = (p_pag ->> 'conta_bancaria_id')::integer, ativo = true
         where id = v_item.id;
        if v_conta.id is null then
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento,
                                      status_pagamento, debito_automatico, conta_bancaria_id, numero_parcela, total_parcelas,
                                      is_fatura_cartao, estouro_orcamento, status_fatura)
            values (v_perfil, v_item.id, v_mes, v_nome, v_valor, v_venc, 'Pendente', coalesce(v_meio, '') = 'debito_automatico',
                    (p_pag ->> 'conta_bancaria_id')::integer, i, p_c.numero_parcelas, false, false, 'ABERTA');
        else
            update public.conta
               set mes_referencia = v_mes, descricao = v_nome, valor = v_valor, data_vencimento = v_venc,
                   debito_automatico = coalesce(v_meio, '') = 'debito_automatico', conta_bancaria_id = (p_pag ->> 'conta_bancaria_id')::integer,
                   numero_parcela = i, total_parcelas = p_c.numero_parcelas
             where id = v_conta.id;
        end if;
        v_cont := jsonb_set(v_cont, '{atualizadas}', to_jsonb((v_cont ->> 'atualizadas')::integer + 1));
    end loop;
    -- Acima do novo numero de parcelas: pendente sem movimento sai; efetivada fica (historico).
    for v_item in select d.* from public.item_despesa d
                   where d.tipo = 'Consorcio' and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
                     and financeiro.posicao_parcela_consorcio(d.nome, v_prefixos) > p_c.numero_parcelas
                   order by d.id for update loop
        if exists (select 1 from public.conta c where c.item_despesa_id = v_item.id and financeiro.despesa_efetivada(c.id)) then
            v_cont := jsonb_set(v_cont, '{preservadas}', to_jsonb((v_cont ->> 'preservadas')::integer + 1));
        else
            delete from public.conta c where c.item_despesa_id = v_item.id;
            delete from public.item_despesa d where d.id = v_item.id;
            v_cont := jsonb_set(v_cont, '{removidas}', to_jsonb((v_cont ->> 'removidas')::integer + 1));
        end if;
    end loop;
    return v_cont;
end
$$;

-- 3. Receita de contemplacao ---------------------------------------------------------------------------------------

-- gerar_ou_atualizar_receita_contemplacao, sem reescrever recebimento ja confirmado (com movimento). Interna.
create function financeiro.sincronizar_receita_contemplacao(p_c public.contrato_consorcio)
    returns boolean
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_perfil   integer := financeiro.perfil_do_consorcio(p_c);
    v_marcador text := 'consorcio_id=' || p_c.id;
    v_fonte    integer;
    v_canonica public.receita_realizada;
    v_dup      public.receita_realizada;
    v_existe   boolean;
begin
    if p_c.mes_contemplacao is null or p_c.valor_premio is null or p_c.valor_premio = 0 then
        return false;
    end if;
    v_existe := exists (select 1 from public.receita_realizada r where r.observacoes ilike '%' || v_marcador || '%');
    if not coalesce(p_c.ativo, true) and not v_existe then
        return false;
    end if;
    select i.id into v_fonte from public.item_receita i
     where i.perfil_financeiro_id = v_perfil and i.nome in ('Contemplação de Consórcio', 'ContemplaÃ§Ã£o de ConsÃ³rcio')
     order by (i.nome = 'Contemplação de Consórcio') desc, (coalesce(i.ativo, true)) desc, i.id limit 1;
    if v_fonte is null then
        insert into public.item_receita (perfil_financeiro_id, nome, tipo, descricao, ativo, recorrente)
        values (v_perfil, 'Contemplação de Consórcio', 'OUTROS', 'Receita pontual gerada automaticamente por consórcio contemplado.',
                true, false)
        returning id into v_fonte;
    else
        update public.item_receita set nome = 'Contemplação de Consórcio', tipo = 'OUTROS', ativo = true, recorrente = false,
               descricao = coalesce(nullif(descricao, ''), 'Receita pontual gerada automaticamente por consórcio contemplado.')
         where id = v_fonte;
    end if;
    if v_existe then
        select r.* into v_canonica from public.receita_realizada r where r.observacoes ilike '%' || v_marcador || '%'
         order by (r.perfil_financeiro_id = v_perfil) desc, (r.item_receita_id = v_fonte) desc, (r.perfil_financeiro_id is not null) desc, r.id
         limit 1 for update;
        if not exists (select 1 from public.movimento_financeiro m where m.receita_realizada_id = v_canonica.id) then
            update public.receita_realizada
               set perfil_financeiro_id = v_perfil, item_receita_id = v_fonte, data_recebimento = p_c.mes_contemplacao,
                   valor_recebido = p_c.valor_premio, mes_referencia = date_trunc('month', p_c.mes_contemplacao::timestamp)::date,
                   descricao = 'Consórcio ' || p_c.nome || ' - contemplação (ID ' || p_c.id || ')', orcamento_id = null
             where id = v_canonica.id;
        end if;
        for v_dup in select r.* from public.receita_realizada r
                      where r.observacoes ilike '%' || v_marcador || '%' and r.id <> v_canonica.id for update loop
            if exists (select 1 from public.movimento_financeiro m where m.receita_realizada_id = v_dup.id) then
                update public.receita_realizada
                   set observacoes = concat_ws(E'\n', nullif(replace(observacoes, v_marcador, ''), ''),
                                               'duplicada_preservada_consorcio_id=' || p_c.id)
                 where id = v_dup.id;
            else
                delete from public.receita_realizada where id = v_dup.id;
            end if;
        end loop;
        return true;
    end if;
    if not coalesce(p_c.ativo, true) then
        return false;
    end if;
    insert into public.receita_realizada (perfil_financeiro_id, item_receita_id, data_recebimento, valor_recebido,
                                          mes_referencia, descricao, observacoes)
    values (v_perfil, v_fonte, p_c.mes_contemplacao, p_c.valor_premio, date_trunc('month', p_c.mes_contemplacao::timestamp)::date,
            'Consórcio ' || p_c.nome || ' - contemplação (ID ' || p_c.id || ')', v_marcador);
    return true;
end
$$;

-- 4. Operacoes ----------------------------------------------------------------------------------------------------

-- Gestao + escritor unico + cadastros de consorcio do perfil em serie. Interna.
create function financeiro.exigir_escrita_consorcio(p_perfil_id integer)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    perform pg_advisory_xact_lock(20261121, p_perfil_id);
end
$$;

-- Contrato do perfil, travado. Interna.
create function financeiro.travar_consorcio(p_perfil_id integer, p_id integer)
    returns public.contrato_consorcio
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c public.contrato_consorcio;
begin
    select * into v_c from public.contrato_consorcio c where c.id = p_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_c.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Consórcio não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADO';
    end if;
    return v_c;
end
$$;

-- Nome livre entre os consorcios ativos do perfil (as parcelas sao ligadas pelo nome). Interna.
create function financeiro.exigir_nome_consorcio_livre(p_perfil_id integer, p_nome text, p_ignorar integer)
    returns void
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if exists (select 1 from public.contrato_consorcio c
                where lower(c.nome) = lower(p_nome) and c.id is distinct from p_ignorar and coalesce(c.ativo, true)
                  and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)) then
        raise exception 'Ja existe um consorcio ativo com este nome neste perfil' using errcode = '22023';
    end if;
end
$$;

-- POST /api/consorcios/: contrato, parcelas e receita de contemplacao. Idempotente pela chave.
create function financeiro.criar_consorcio(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida  jsonb;
    v_d         jsonb;
    v_c         public.contrato_consorcio;
    v_categoria integer;
    v_parcelas  jsonb;
    v_receita   boolean;
    v_resultado jsonb;
    v_campo     text;
begin
    perform financeiro.exigir_escrita_consorcio(p_perfil_id);
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'criar_consorcio');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do consorcio invalidos' using errcode = '22023';
    end if;
    foreach v_campo in array array['nome', 'valor_inicial', 'numero_parcelas', 'categoria_id'] loop
        if nullif(btrim(coalesce(p_dados ->> v_campo, '')), '') is null or (p_dados ->> v_campo) in ('0', 'false') then
            raise exception 'Campo % é obrigatório', v_campo using errcode = '22023';
        end if;
    end loop;
    v_categoria := (p_dados ->> 'categoria_id')::integer;
    if not exists (select 1 from public.categoria c where c.id = v_categoria) then
        raise exception 'Categoria não encontrada' using errcode = '22023';
    end if;
    perform financeiro.exigir_nome_consorcio_livre(p_perfil_id, btrim(p_dados ->> 'nome'), null);
    v_d := financeiro.consorcio_normalizar(p_dados, null);
    insert into public.contrato_consorcio (perfil_financeiro_id, nome, valor_inicial, tipo_reajuste, valor_reajuste, numero_parcelas,
                                           mes_inicio, mes_contemplacao, valor_premio, item_receita_id, observacoes, ativo, criado_em)
    values (p_perfil_id, btrim(p_dados ->> 'nome'), (v_d ->> 'valor_inicial')::numeric, v_d ->> 'tipo_reajuste',
            (v_d ->> 'valor_reajuste')::numeric, (v_d ->> 'numero_parcelas')::integer, (v_d ->> 'mes_inicio')::date,
            (v_d ->> 'mes_contemplacao')::date, (v_d ->> 'valor_premio')::numeric,
            nullif(p_dados ->> 'item_receita_id', '')::integer, nullif(p_dados ->> 'observacoes', ''), true, now() at time zone 'utc')
    returning * into v_c;
    v_parcelas := financeiro.sincronizar_parcelas_consorcio(v_c, v_categoria, financeiro.consorcio_pagamento(p_dados), '{}');
    v_receita := financeiro.sincronizar_receita_contemplacao(v_c);
    v_resultado := jsonb_build_object('data', financeiro.consorcio_flask(v_c), 'parcelas_geradas', (v_parcelas ->> 'criadas')::integer,
                                      'receita_gerada', v_receita);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_consorcio', v_resultado);
    return v_resultado;
end
$$;

-- PUT /api/consorcios/<id>: como o Flask (nao regenera parcelas); renomeia as parcelas; meio de pagamento so nas
-- despesas pendentes; receita de contemplacao sincronizada.
create function financeiro.editar_consorcio(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c        public.contrato_consorcio;
    v_anterior text;
    v_d        jsonb;
    v_pag      jsonb;
    v_perfil   integer;
    v_receita  boolean;
begin
    perform financeiro.exigir_escrita_consorcio(p_perfil_id);
    v_c := financeiro.travar_consorcio(p_perfil_id, p_id);
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do consorcio invalidos' using errcode = '22023';
    end if;
    v_anterior := v_c.nome;
    v_perfil := financeiro.perfil_do_consorcio(v_c);
    if p_dados ? 'nome' and btrim(coalesce(p_dados ->> 'nome', '')) <> '' and btrim(p_dados ->> 'nome') <> v_c.nome then
        perform financeiro.exigir_nome_consorcio_livre(p_perfil_id, btrim(p_dados ->> 'nome'), v_c.id);
        update public.item_despesa d
           set nome = btrim(p_dados ->> 'nome') || substr(d.nome, length(v_anterior) + 1)
         where d.tipo = 'Consorcio' and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
           and financeiro.posicao_parcela_consorcio(d.nome, array[v_anterior]) is not null;
        update public.contrato_consorcio set nome = btrim(p_dados ->> 'nome') where id = v_c.id;
    end if;
    if p_dados ? 'observacoes' then
        update public.contrato_consorcio set observacoes = p_dados ->> 'observacoes' where id = v_c.id;
    end if;
    if p_dados ?| array['valor_inicial', 'numero_parcelas', 'mes_inicio', 'mes_contemplacao', 'tipo_reajuste', 'valor_reajuste'] then
        v_d := financeiro.consorcio_normalizar(p_dados, v_c);
        update public.contrato_consorcio
           set valor_inicial = (v_d ->> 'valor_inicial')::numeric, tipo_reajuste = v_d ->> 'tipo_reajuste',
               valor_reajuste = (v_d ->> 'valor_reajuste')::numeric, numero_parcelas = (v_d ->> 'numero_parcelas')::integer,
               mes_inicio = (v_d ->> 'mes_inicio')::date, mes_contemplacao = (v_d ->> 'mes_contemplacao')::date,
               valor_premio = (v_d ->> 'valor_premio')::numeric
         where id = v_c.id;
    end if;
    if p_dados ? 'ativo' and jsonb_typeof(p_dados -> 'ativo') = 'boolean' then
        update public.contrato_consorcio set ativo = (p_dados ->> 'ativo')::boolean where id = v_c.id;
    end if;
    select * into v_c from public.contrato_consorcio where id = v_c.id;
    if p_dados ?| array['meio_pagamento', 'cartao_id', 'conta_bancaria_id', 'categoria_cartao_id'] then
        v_pag := financeiro.consorcio_pagamento(p_dados);
        update public.item_despesa d
           set meio_pagamento = v_pag ->> 'meio_pagamento', cartao_id = (v_pag ->> 'cartao_id')::integer,
               categoria_cartao_id = (v_pag ->> 'categoria_cartao_id')::integer,
               conta_bancaria_id = (v_pag ->> 'conta_bancaria_id')::integer
         where d.tipo = 'Consorcio' and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
           and financeiro.posicao_parcela_consorcio(d.nome, array[v_c.nome]) is not null;
        update public.conta c
           set debito_automatico = coalesce(v_pag ->> 'meio_pagamento', '') = 'debito_automatico',
               conta_bancaria_id = (v_pag ->> 'conta_bancaria_id')::integer
          from public.item_despesa d
         where c.item_despesa_id = d.id and d.tipo = 'Consorcio'
           and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
           and financeiro.posicao_parcela_consorcio(d.nome, array[v_c.nome]) is not null
           and not financeiro.despesa_efetivada(c.id);
    end if;
    v_receita := financeiro.sincronizar_receita_contemplacao(v_c);
    return jsonb_build_object('data', financeiro.consorcio_flask(v_c), 'receita_gerada', v_receita);
end
$$;

-- POST /api/consorcios/<id>/regenerar-parcelas: regeneracao SEGURA (parcelas efetivadas intactas).
create function financeiro.regenerar_parcelas_consorcio(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c         public.contrato_consorcio;
    v_perfil    integer;
    v_categoria integer;
    v_primeira  public.item_despesa;
    v_res       jsonb;
begin
    perform financeiro.exigir_escrita_consorcio(p_perfil_id);
    v_c := financeiro.travar_consorcio(p_perfil_id, p_id);
    v_perfil := financeiro.perfil_do_consorcio(v_c);
    select d.* into v_primeira from public.item_despesa d
     where d.tipo = 'Consorcio' and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
       and financeiro.posicao_parcela_consorcio(d.nome, array[v_c.nome]) is not null
     order by d.id limit 1;
    v_categoria := coalesce(nullif(coalesce(p_dados, '{}') ->> 'categoria_id', '')::integer, v_primeira.categoria_id);
    if v_categoria is null then
        raise exception 'categoria_id é obrigatório (nenhuma parcela anterior encontrada)' using errcode = '22023';
    end if;
    v_res := financeiro.sincronizar_parcelas_consorcio(
        v_c, v_categoria,
        jsonb_build_object('meio_pagamento', v_primeira.meio_pagamento, 'cartao_id', v_primeira.cartao_id,
                           'categoria_cartao_id', v_primeira.categoria_cartao_id, 'conta_bancaria_id', v_primeira.conta_bancaria_id),
        '{}');
    return v_res || jsonb_build_object('parcelas_geradas', (v_res ->> 'criadas')::integer + (v_res ->> 'atualizadas')::integer,
                                       'message', 'Parcelas regeneradas com sucesso');
end
$$;

-- DELETE /api/consorcios/<id>: inativa o contrato e as parcelas; remove so despesa pendente SEM movimento; receita de
-- contemplacao sem movimento sai, com movimento so perde o marcador (historico preservado).
create function financeiro.excluir_consorcio(p_perfil_id integer, p_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c        public.contrato_consorcio;
    v_perfil   integer;
    v_marcador text;
    v_rem      integer;
begin
    perform financeiro.exigir_escrita_consorcio(p_perfil_id);
    v_c := financeiro.travar_consorcio(p_perfil_id, p_id);
    v_perfil := financeiro.perfil_do_consorcio(v_c);
    v_marcador := 'consorcio_id=' || v_c.id;
    update public.contrato_consorcio set ativo = false where id = v_c.id;
    update public.item_despesa d set ativo = false
     where d.tipo = 'Consorcio' and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
       and financeiro.posicao_parcela_consorcio(d.nome, array[v_c.nome]) is not null;
    delete from public.conta c using public.item_despesa d
     where c.item_despesa_id = d.id and d.tipo = 'Consorcio'
       and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
       and financeiro.posicao_parcela_consorcio(d.nome, array[v_c.nome]) is not null
       and not financeiro.despesa_efetivada(c.id);
    get diagnostics v_rem = row_count;
    update public.receita_realizada r
       set observacoes = nullif(btrim(replace(r.observacoes, v_marcador, ''), E'\n '), '')
     where r.observacoes ilike '%' || v_marcador || '%'
       and exists (select 1 from public.movimento_financeiro m where m.receita_realizada_id = r.id);
    delete from public.receita_realizada r
     where r.observacoes ilike '%' || v_marcador || '%'
       and not exists (select 1 from public.movimento_financeiro m where m.receita_realizada_id = r.id);
    return jsonb_build_object('message', 'Consórcio desativado com sucesso', 'despesas_pendentes_removidas', v_rem);
end
$$;

-- 5. Privilegios --------------------------------------------------------------------------------------------------

revoke execute on function financeiro.consorcio_valor_parcela(numeric, text, numeric, integer) from public, anon, authenticated;
revoke execute on function financeiro.consorcio_mes(text, date, text) from public, anon, authenticated;
revoke execute on function financeiro.consorcio_normalizar(jsonb, public.contrato_consorcio) from public, anon, authenticated;
revoke execute on function financeiro.consorcio_pagamento(jsonb) from public, anon, authenticated;
revoke execute on function financeiro.posicao_parcela_consorcio(text, text[]) from public, anon, authenticated;
revoke execute on function financeiro.despesa_efetivada(integer) from public, anon, authenticated;
revoke execute on function financeiro.sincronizar_parcelas_consorcio(public.contrato_consorcio, integer, jsonb, text[]) from public, anon, authenticated;
revoke execute on function financeiro.sincronizar_receita_contemplacao(public.contrato_consorcio) from public, anon, authenticated;
revoke execute on function financeiro.exigir_escrita_consorcio(integer) from public, anon, authenticated;
revoke execute on function financeiro.travar_consorcio(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.exigir_nome_consorcio_livre(integer, text, integer) from public, anon, authenticated;
revoke execute on function financeiro.criar_consorcio(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_consorcio(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.regenerar_parcelas_consorcio(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.excluir_consorcio(integer, integer) from public, anon;
grant execute on function financeiro.criar_consorcio(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_consorcio(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.regenerar_parcelas_consorcio(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.excluir_consorcio(integer, integer) to authenticated;
