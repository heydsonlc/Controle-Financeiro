-- FIN-FIDELIDADE-CARTOES-2 — R2: recorrencia no cartao pela tela de Recorrencias (POST/PUT /api/recorrencias do Flask com
-- meio_pagamento 'cartao').
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261106090000).
-- Validada em cluster local descartavel (tests/test_supabase_recorrencia_cartao.py). Docs: docs/FIN_FIDELIDADE_CARTOES_1.md.
--
-- Nenhuma tabela, coluna ou dado alterado; nenhuma funcao existente trocada (o gerador continua o mesmo: ele ja gera
-- a compra do cartao para item recorrente com meio 'cartao', natureza LANCAMENTO_CARTAO, identidade por competencia).
-- Como o Flask (routes/recorrencias.py): item 'Simples', recorrente, meio_pagamento 'cartao', cartao_id e a Categoria do
-- Cartao resolvida pela categoria de despesa (resolver_categoria_cartao_para_lancamento). Diferencas assumidas:
-- - salvar nao gera a primeira compra: a geracao e explicita em Despesas ("Gerar contas"), como nas demais recorrencias;
-- - so mensal e anual (R1); trocar entre cartao e outro meio nao e feito por edicao (inativar e cadastrar de novo),
--   para nao misturar compras ja geradas no cartao com contas;
-- - compras ja geradas (inclusive em fatura paga) nao mudam: a edicao vale para as proximas competencias.
-- - so no perfil atribuido ao novo aplicativo (financeiro.exigir_gerador_novo): perfil ainda no Flask = recusa, nada
--   gravado (a existencia da funcao nao libera a escrita; FIN-ESCRITOR-UNICO-CONTAS-1).

-- Dados validados de uma recorrencia no cartao. Interna.
create function financeiro.ler_dados_recorrencia_cartao(p_perfil_id integer, p_dados jsonb, p_parcial boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_saida jsonb := '{}'::jsonb;
    v_texto text;
    v_valor numeric;
    v_int   integer;
    v_data  date;
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da recorrencia invalidos' using errcode = '22023';
    end if;
    if p_dados ? 'nome' or not p_parcial then
        v_texto := btrim(coalesce(p_dados ->> 'nome', ''));
        if v_texto = '' or length(v_texto) > 200 then
            raise exception 'Nome e obrigatorio (ate 200 caracteres)' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('nome', v_texto);
    end if;
    if p_dados ? 'valor' or not p_parcial then
        begin
            v_valor := (p_dados ->> 'valor')::numeric;
        exception when others then
            v_valor := null;
        end;
        if v_valor is null or v_valor <= 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
            raise exception 'Valor deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('valor', v_valor);
    end if;
    if p_dados ? 'categoria_id' or not p_parcial then
        begin
            v_int := (p_dados ->> 'categoria_id')::integer;
        exception when others then
            v_int := null;
        end;
        if v_int is null or not exists (select 1 from public.categoria c where c.id = v_int and coalesce(c.ativo, true)) then
            raise exception 'Categoria inexistente ou inativa' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('categoria_id', v_int);
    end if;
    if p_dados ? 'data_vencimento' or not p_parcial then
        begin
            v_data := (p_dados ->> 'data_vencimento')::date;
        exception when others then
            v_data := null;
        end;
        if v_data is null then
            raise exception 'Informe a data do primeiro vencimento' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('data_vencimento', v_data);
    end if;
    if p_dados ? 'tipo_recorrencia' or not p_parcial then
        if coalesce(p_dados ->> 'tipo_recorrencia', 'mensal') not in ('mensal', 'anual') then
            raise exception 'Frequencia invalida: o novo aplicativo gera mensal e anual' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('tipo_recorrencia', coalesce(p_dados ->> 'tipo_recorrencia', 'mensal'));
    end if;
    if p_dados ? 'cartao_id' or not p_parcial then
        begin
            v_int := (p_dados ->> 'cartao_id')::integer;
        exception when others then
            v_int := null;
        end;
        if v_int is null then
            raise exception 'Informe o cartao da recorrencia' using errcode = '22023';
        end if;
        perform financeiro.cartao_do_perfil(p_perfil_id, v_int, true);
        if not exists (select 1 from public.config_agregador cfg where cfg.item_despesa_id = v_int
                        and cfg.dia_vencimento between 1 and 31) then
            raise exception 'Cartao sem dia de vencimento configurado' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('cartao_id', v_int);
    end if;
    if p_dados ? 'descricao' then
        v_saida := v_saida || jsonb_build_object('descricao', left(coalesce(p_dados ->> 'descricao', ''), 1000));
    end if;
    return v_saida;
end
$$;

create function financeiro.criar_recorrencia_cartao(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_despesa;
    v_d         jsonb;
    v_venc      date;
    v_id        integer;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.exigir_gerador_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO: perfil do Flask = recusa
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261026));  -- mesma chave de criar_despesa
    select * into v_anterior from financeiro.operacao_despesa o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    v_d := financeiro.ler_dados_recorrencia_cartao(p_perfil_id, p_dados, false);
    v_venc := (v_d ->> 'data_vencimento')::date;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- nao entra no meio de uma geracao
    insert into public.item_despesa (perfil_financeiro_id, nome, descricao, valor, data_vencimento, categoria_id, pago,
                                     recorrente, tipo_recorrencia, mes_competencia, tipo, meio_pagamento, cartao_id,
                                     categoria_cartao_id, ativo, criado_em)
    values (p_perfil_id, v_d ->> 'nome', v_d ->> 'descricao', (v_d ->> 'valor')::numeric, v_venc,
            (v_d ->> 'categoria_id')::integer, false, true, v_d ->> 'tipo_recorrencia',
            to_char(v_venc - interval '1 month', 'YYYY-MM'), 'Simples', 'cartao', (v_d ->> 'cartao_id')::integer,
            financeiro.resolver_categoria_cartao(p_perfil_id, (v_d ->> 'cartao_id')::integer, (v_d ->> 'categoria_id')::integer),
            true, now() at time zone 'utc')
    returning id into v_id;
    v_resultado := jsonb_build_object('item_id', v_id, 'recorrente', true, 'meio_pagamento', 'cartao',
                                      'competencia', date_trunc('month', v_venc::timestamp)::date);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_recorrencia_cartao', v_resultado);
    return v_resultado;
end
$$;

-- Trava a recorrencia no cartao do perfil e confere gestao, natureza e versao. Interna.
create function financeiro.travar_recorrencia_cartao(p_perfil_id integer, p_item_id integer, p_versao text)
    returns public.item_despesa
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item public.item_despesa;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.exigir_gerador_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO: perfil do Flask = recusa
    select * into v_item from public.item_despesa where id = p_item_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_item.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Recorrencia nao encontrada neste perfil' using errcode = '42501';
    end if;
    if not coalesce(v_item.recorrente, false) or v_item.tipo is distinct from 'Simples' or v_item.origem_tipo is not null
       or coalesce(v_item.meio_pagamento, '') <> 'cartao' then
        raise exception 'Operacao bloqueada: recorrencia gerenciada por outro modulo' using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    if p_versao is null or p_versao is distinct from financeiro.versao_recorrencia(p_item_id) then
        raise exception 'A recorrencia foi alterada por outra operacao. Recarregue e tente de novo.'
            using errcode = 'P0001', hint = 'VERSAO';
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    return v_item;
end
$$;

-- Edicao: vale para as proximas competencias; compras ja geradas ficam como estao (inclusive em fatura paga).
create function financeiro.editar_recorrencia_cartao(p_perfil_id integer, p_item_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item   public.item_despesa;
    v_d      jsonb;
    v_venc   date;
    v_tipo   text;
    v_cartao integer;
    v_cat    integer;
begin
    v_item := financeiro.travar_recorrencia_cartao(p_perfil_id, p_item_id, p_versao);
    v_d := financeiro.ler_dados_recorrencia_cartao(p_perfil_id, p_dados, true);
    v_venc := coalesce((v_d ->> 'data_vencimento')::date, v_item.data_vencimento);
    v_tipo := coalesce(v_d ->> 'tipo_recorrencia', v_item.tipo_recorrencia, 'mensal');
    -- Mesma regra de editar_recorrencia: no perfil gerado pelo Flask, dia e frequencia nao mudam por aqui.
    if (v_venc is distinct from v_item.data_vencimento or v_tipo is distinct from coalesce(v_item.tipo_recorrencia, 'mensal'))
       and financeiro.gerador_do_perfil(p_perfil_id) <> 'NOVO' then
        raise exception 'Dia e frequencia so mudam quando o novo aplicativo gera este perfil (o Flask duplicaria por data)'
            using errcode = 'P0001', hint = 'GERADOR_FLASK';
    end if;
    v_cartao := coalesce((v_d ->> 'cartao_id')::integer, v_item.cartao_id);
    v_cat := coalesce((v_d ->> 'categoria_id')::integer, v_item.categoria_id);
    update public.item_despesa i
       set nome = coalesce(v_d ->> 'nome', i.nome),
           valor = coalesce((v_d ->> 'valor')::numeric, i.valor),
           categoria_id = v_cat,
           data_vencimento = v_venc,
           mes_competencia = case when v_venc is distinct from i.data_vencimento
                                  then to_char(v_venc - interval '1 month', 'YYYY-MM') else i.mes_competencia end,
           tipo_recorrencia = v_tipo,
           descricao = case when v_d ? 'descricao' then v_d ->> 'descricao' else i.descricao end,
           cartao_id = v_cartao,
           categoria_cartao_id = financeiro.resolver_categoria_cartao(p_perfil_id, v_cartao, v_cat)
     where i.id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'versao', financeiro.versao_recorrencia(p_item_id));
end
$$;

-- Inativar (o "excluir" do Flask) ou reativar: nada ja gerado muda; inativa, nao gera novas compras.
create function financeiro.definir_situacao_recorrencia_cartao(p_perfil_id integer, p_item_id integer, p_versao text,
                                                               p_ativo boolean)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item public.item_despesa;
begin
    v_item := financeiro.travar_recorrencia_cartao(p_perfil_id, p_item_id, p_versao);
    if p_ativo is null then
        raise exception 'Situacao invalida' using errcode = '22023';
    end if;
    if p_ativo then
        perform financeiro.cartao_do_perfil(p_perfil_id, v_item.cartao_id, true);  -- cartao inativo nao recebe compra nova
    end if;
    update public.item_despesa set ativo = p_ativo where id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'ativo', p_ativo, 'versao', financeiro.versao_recorrencia(p_item_id));
end
$$;

revoke execute on function financeiro.ler_dados_recorrencia_cartao(integer, jsonb, boolean) from public, anon, authenticated;
revoke execute on function financeiro.travar_recorrencia_cartao(integer, integer, text) from public, anon, authenticated;
revoke execute on function financeiro.criar_recorrencia_cartao(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_recorrencia_cartao(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.definir_situacao_recorrencia_cartao(integer, integer, text, boolean) from public, anon;
grant execute on function financeiro.criar_recorrencia_cartao(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_recorrencia_cartao(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.definir_situacao_recorrencia_cartao(integer, integer, text, boolean) to authenticated;
