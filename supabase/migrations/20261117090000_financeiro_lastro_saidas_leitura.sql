-- FIN-FIDELIDADE-DOCUMENTOS-1 (Documentos da Empresa) — leitura das "saidas sem documento" do Flask
-- (GET /api/ir/lastro/saidas-sem-documento e /resumo), so consulta e so no perfil Empresa.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261117090000).
-- Depende de 20261113090000 (financeiro.tipo_perfil_ir).
-- Validada em cluster local descartavel (tests/test_supabase_lastro_saidas_leitura.py, comparada com o Flask).
-- Docs: docs/FIN_FIDELIDADE_DOCUMENTOS_1.md.
--
-- Reproduz LastroFinanceiroService (listar_saidas_sem_documento / resumo_saidas_sem_documento): saidas do periodo (ano,
-- ou ano e mes) vindas de despesas previstas, contas (sem faturas), lancamentos no cartao e debitos avulsos (sem conta, sem
-- fatura e sem transferencia interna), com o vinculo de documento mais recente ou a pendencia ativa mais recente,
-- natureza sugerida, filtros (origem, natureza, busca sem acento, valor minimo, status) e o resumo por origem e natureza.
-- Nada e gravado: marcar status e vincular documento continuam no Flask. Nenhuma tabela nova.

-- _normalizar_texto (casefold + remove acentos). Interna.
create function financeiro.texto_sem_acento(p_texto text)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select translate(lower(coalesce(p_texto, '')), 'áàâãäåéèêëíìîïóòôõöúùûüçñýÿ', 'aaaaaaeeeeiiiiooooouuuucnyy')
$$;

-- sugerir_natureza. Interna.
create function financeiro.natureza_sugerida_lastro(p_categoria text, p_descricao text)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select case
        when t ~ '(patrimonio|moveis|equipamento|computador|notebook)' then 'PATRIMONIO_IMOBILIZADO'
        when t ~ '(imposto|taxa|guia)' then 'IMPOSTO_TAXA'
        when strpos(t, 'pro labore') > 0 or strpos(t, 'pro-labore') > 0 then 'PRO_LABORE'
        when strpos(t, 'lucro') > 0 or strpos(t, 'distribuicao') > 0 then 'DISTRIBUICAO_LUCROS'
        when strpos(t, 'reembolso') > 0 then 'REEMBOLSO'
        when strpos(t, 'software') > 0 or strpos(t, 'assinatura') > 0 then 'SOFTWARE_ASSINATURA'
        else 'DESPESA_OPERACIONAL' end
      from (select financeiro.texto_sem_acento(coalesce(p_categoria, '') || ' ' || coalesce(p_descricao, '')) t) x
$$;

-- _saidas_enriquecidas: saidas do periodo com vinculo/pendencia e os filtros basicos (sem o de status). Interna.
create function financeiro.saidas_lastro(p_perfil_id integer, p_f jsonb)
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

-- GET /api/ir/lastro/saidas-sem-documento (p_resumo false) e /resumo (true). So no perfil Empresa (403 no Flask).
create function financeiro.lastro_saidas_tela(p_perfil_id integer, p_filtros jsonb, p_resumo boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_f       jsonb := coalesce(p_filtros, '{}'::jsonb);
    v_saidas  jsonb;
    v_status  text := upper(btrim(coalesce(v_f ->> 'status', '')));
    v_perm    text[];
begin
    if financeiro.tipo_perfil_ir(p_perfil_id) <> 'EMPRESA' then
        raise exception 'Saidas sem documento estao disponiveis apenas no perfil Empresa' using errcode = '42501';
    end if;
    v_saidas := financeiro.saidas_lastro(p_perfil_id, v_f);
    if not coalesce(p_resumo, false) then
        v_perm := case when v_status in ('', 'PENDENTES') then array['SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR']
                       when v_status in ('TODOS', 'TODAS') then array['SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR', 'NAO_APLICAVEL']
                       else array[v_status] end;
        -- sorted(..., key=(data or '', tipo_entidade, entidade_id), reverse=True): ordem de codigo do Python.
        return coalesce((select jsonb_agg(s order by coalesce(s ->> 'data', '') collate "C" desc,
                                                     (s ->> 'tipo_entidade') collate "C" desc, (s ->> 'entidade_id')::integer desc)
                           from jsonb_array_elements(v_saidas) s
                          where not (s ->> 'possui_documento')::boolean and s ->> 'status_lastro' = any (v_perm)), '[]'::jsonb);
    end if;
    return (
        with s as (select x, coalesce(x ->> 'status_lastro', 'SEM_DOCUMENTO') st, (x ->> 'valor')::numeric valor,
                          (x ->> 'possui_documento')::boolean doc
                     from jsonb_array_elements(v_saidas) x),
             sem as (select * from s where not doc)
        select jsonb_build_object(
            'total_saidas', (select count(*) from s),
            'saidas_com_documento', (select count(*) from s where doc),
            'quantidade_sem_documento', (select count(*) from sem where st in ('SEM_DOCUMENTO', 'PENDENTE')),
            'valor_sem_documento', (select coalesce(sum(valor), 0) from sem where st in ('SEM_DOCUMENTO', 'PENDENTE')),
            'aguardando_contador', (select count(*) from sem where st = 'AGUARDANDO_CONTADOR'),
            'valor_aguardando_contador', (select coalesce(sum(valor), 0) from sem where st = 'AGUARDANDO_CONTADOR'),
            'nao_aplicavel', (select count(*) from sem where st = 'NAO_APLICAVEL'),
            'valor_nao_aplicavel', (select coalesce(sum(valor), 0) from sem where st = 'NAO_APLICAVEL'),
            'pendencias_total', (select count(*) from sem where st in ('SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR')),
            'valor_pendencias_total', (select coalesce(sum(valor), 0) from sem
                                        where st in ('SEM_DOCUMENTO', 'PENDENTE', 'AGUARDANDO_CONTADOR')),
            'por_origem', coalesce((select jsonb_agg(jsonb_build_object('nome', g.nome, 'quantidade', g.qtd, 'valor', g.valor)
                                                     order by g.valor desc, g.nome collate "C")
                                      from (select coalesce(nullif(x ->> 'origem', ''), 'Outros') nome, count(*) qtd, sum(valor) valor
                                              from sem group by 1) g), '[]'::jsonb),
            'por_natureza', coalesce((select jsonb_agg(jsonb_build_object('nome', g.nome, 'quantidade', g.qtd, 'valor', g.valor)
                                                       order by g.valor desc, g.nome collate "C")
                                        from (select coalesce(nullif(x ->> 'natureza_sugerida', ''), 'OUTRO') nome, count(*) qtd,
                                                     sum(valor) valor
                                                from sem group by 1) g), '[]'::jsonb)));
end
$$;

revoke execute on function financeiro.texto_sem_acento(text) from public, anon, authenticated;
revoke execute on function financeiro.natureza_sugerida_lastro(text, text) from public, anon, authenticated;
revoke execute on function financeiro.saidas_lastro(integer, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.lastro_saidas_tela(integer, jsonb, boolean) from public, anon;
grant execute on function financeiro.lastro_saidas_tela(integer, jsonb, boolean) to authenticated;
