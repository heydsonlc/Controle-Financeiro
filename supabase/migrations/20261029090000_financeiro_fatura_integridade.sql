-- FIN-FATURA-INTEGRIDADE-1 — fatura paga imutavel nas compras e ordem global de travas.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261029090000).
-- Validada em cluster local descartavel (tests/test_fatura_integridade.py). Docs: docs/FIN_FATURA_INTEGRIDADE_1.md.
--
-- 1. public.lancamento_agregado.mes_fatura_original (date, nula): competencia de origem quando a compra
--    foi desviada de uma fatura paga. Nula = nao desviada. Nada e preenchido retroativamente.
-- 2. gerar_mes_interno: a compra recorrente nao entra em fatura paga (vai para a proxima nao paga);
--    plano_recorrencia: o reconhecimento "pelo mes" vale so para compras antigas sem compra_id.
-- 3. Ordem global de travas, igual a do Flask: cartao (item_despesa, por id) -> faturas dele (por id) ->
--    compras -> conta bancaria -> movimento. Quem trava mais de uma fatura trava o cartao antes; o
--    pagamento trava uma so fatura e nunca espera outra. Sem ciclo de espera (nao depende da deteccao de
--    deadlock do PostgreSQL). criar_compra, travar_compra e gerar_mes_interno passam a travar o cartao.
-- Nenhum dado existente e alterado; as funcoes mantem assinatura e privilegios.

alter table public.lancamento_agregado add column if not exists mes_fatura_original date;
comment on column public.lancamento_agregado.mes_fatura_original is
    'FIN-FATURA-INTEGRIDADE-1: competencia de origem quando a compra foi desviada de fatura paga (nula = nao desviada).';

-- Primeiro mes sem fatura paga a partir da competencia (chamador ja travou o cartao). Interna.
create function financeiro.fatura_elegivel_existente(p_cartao_id integer, p_competencia date)
    returns date
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_mes date := date_trunc('month', p_competencia::timestamp)::date;
    v_fat integer;
begin
    for i in 0..24 loop
        v_fat := financeiro.fatura_do_mes(p_cartao_id, v_mes);
        if v_fat is null then
            return v_mes;
        end if;
        perform 1 from public.conta where id = v_fat for update;
        if not financeiro.fatura_esta_paga(v_fat) then
            return v_mes;
        end if;
        v_mes := (v_mes + interval '1 month')::date;
    end loop;
    raise exception 'Nao ha fatura aberta nos proximos 24 meses' using errcode = '22023';
end
$$;
revoke execute on function financeiro.fatura_elegivel_existente(integer, date) from public, anon, authenticated;

create or replace function financeiro.plano_recorrencia(p_perfil_id integer, p_mes date)
    returns setof financeiro.linha_plano
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes     date := date_trunc('month', p_mes::timestamp)::date;
    v_limite  date := (date_trunc('month', p_mes::timestamp) + interval '1 month')::date;
    v_ns      constant uuid := '7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c';  -- namespace do Flask
    v_pessoal boolean;
    v_item    record;
    v_cartao  record;
    v_reg     record;
    v_linha   financeiro.linha_plano;
    v_comp    date;
    v_passo   interval;
    v_dia     integer;
    v_motivo  text;
    v_ccs     integer[];
    v_qtd     integer;
    v_id      integer;
begin
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');

    -- 1) Recorrencias: conta (boleto, debito, pix...) ou compra no cartao.
    for v_item in
        select i.*
          from public.item_despesa i
         where (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))
           and coalesce(i.recorrente, false)
         order by i.id
    loop
        v_linha := null;
        v_linha.natureza := case when v_item.meio_pagamento = 'cartao' then 'LANCAMENTO_CARTAO' else 'CONTA' end;
        v_linha.item_despesa_id := v_item.id;
        v_linha.nome := v_item.nome;
        v_linha.valor := v_item.valor;
        v_linha.perfil_destino := v_item.perfil_financeiro_id;
        v_linha.observacoes := coalesce(v_item.descricao, '');
        v_motivo := null;

        if not coalesce(v_item.ativo, true) then
            v_linha.situacao := 'INATIVA';
            v_linha.motivo := 'Recorrencia inativa: nao gera novos lancamentos';
            return next v_linha;
            continue;
        end if;

        if v_item.tipo = 'Agregador' then
            v_motivo := 'Cartao marcado como recorrencia';
        elsif v_item.data_vencimento is null then
            v_motivo := 'Sem data de vencimento';
        elsif coalesce(v_item.tipo_recorrencia, 'mensal') not in ('mensal', 'anual') then
            v_motivo := 'Tipo de recorrencia fora do escopo: ' || v_item.tipo_recorrencia;
        elsif v_item.valor is null or v_item.valor < 0 then
            v_motivo := 'Sem valor valido';
        elsif v_linha.natureza = 'LANCAMENTO_CARTAO' then
            if v_item.cartao_id is null then
                v_motivo := 'Sem cartao';
            elsif v_item.categoria_id is null then
                v_motivo := 'Sem categoria';
            else
                select c.* into v_cartao
                  from public.item_despesa c
                 where c.id = v_item.cartao_id
                   and c.tipo = 'Agregador'
                   and coalesce(c.ativo, true)
                   and (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal));
                if not found then
                    v_motivo := 'Cartao inexistente, inativo ou de outro perfil';
                end if;
            end if;

            -- Categoria do cartao como CategoriaCartaoService.resolver_categoria_cartao_para_lancamento.
            if v_motivo is null then
                v_linha.cartao_id := v_item.cartao_id;
                v_linha.categoria_id := v_item.categoria_id;
                if v_item.categoria_cartao_id is not null then
                    if exists (select 1 from public.categoria_cartao cc
                                where cc.id = v_item.categoria_cartao_id
                                  and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal))) then
                        v_linha.categoria_cartao_id := v_item.categoria_cartao_id;
                    else
                        v_motivo := 'Categoria do cartao nao encontrada';
                    end if;
                else
                    select array_agg(v.categoria_cartao_id order by v.id) into v_ccs
                      from public.categoria_cartao_despesa v
                      join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
                     where v.categoria_id = v_item.categoria_id
                       and v.ativo and cc.ativo
                       and (v.perfil_financeiro_id = p_perfil_id or (v.perfil_financeiro_id is null and v_pessoal))
                       and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal));
                    if cardinality(v_ccs) > 1 then
                        v_motivo := 'Categoria de despesa com mais de uma categoria do cartao ativa';
                    elsif cardinality(v_ccs) = 1 and exists (
                        select 1 from public.cartao_categoria_limite lim
                          join public.categoria_cartao cc on cc.id = lim.categoria_cartao_id
                         where lim.cartao_id = v_item.cartao_id
                           and lim.categoria_cartao_id = v_ccs[1]
                           and lim.ativo and cc.ativo
                           and (lim.perfil_financeiro_id = p_perfil_id or (lim.perfil_financeiro_id is null and v_pessoal))
                           and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal))) then
                        v_linha.categoria_cartao_id := v_ccs[1];
                    end if;
                end if;
            end if;
        else
            v_linha.conta_bancaria_id := v_item.conta_bancaria_id;
            v_linha.debito_automatico := coalesce(v_item.meio_pagamento = 'debito_automatico', false);
        end if;

        if v_motivo is not null then
            v_linha.situacao := 'REJEITADA';
            v_linha.motivo := v_motivo;
            v_linha.cartao_id := null;
            v_linha.categoria_id := null;
            v_linha.categoria_cartao_id := null;
            return next v_linha;
            continue;
        end if;

        v_dia := extract(day from v_item.data_vencimento)::integer;
        v_passo := case when coalesce(v_item.tipo_recorrencia, 'mensal') = 'anual' then interval '1 year' else interval '1 month' end;
        v_comp := date_trunc('month', v_item.data_vencimento::timestamp)::date;
        while v_comp <= v_limite loop
            v_linha.competencia := v_comp;
            v_linha.data_vencimento := financeiro.dia_contratual(v_comp, v_dia);
            v_linha.registro_id := null;
            v_linha.motivo := null;
            v_linha.compra_id := case when v_linha.natureza = 'LANCAMENTO_CARTAO' then
                extensions.uuid_generate_v5(v_ns, format('%s-%s', v_item.id, to_char(v_comp, 'YYYY-MM-DD')))::text end;

            select r.* into v_reg
              from financeiro.recorrencia_competencia r
             where r.item_despesa_id = v_item.id and r.natureza = v_linha.natureza and r.competencia = v_comp;
            if found then
                if v_reg.situacao = 'GERADA' and (
                       exists (select 1 from public.conta c where c.id = v_reg.conta_id)
                    or exists (select 1 from public.lancamento_agregado l where l.id = v_reg.lancamento_id)) then
                    v_linha.situacao := 'EXISTENTE';
                    v_linha.registro_id := coalesce(v_reg.conta_id, v_reg.lancamento_id);
                else
                    v_linha.situacao := 'DISPENSADA';
                    v_linha.motivo := case when v_reg.situacao = 'DISPENSADA'
                                           then coalesce(v_reg.motivo, 'Competencia dispensada')
                                           else 'Registro gerado foi removido; nao sera recriado' end;
                end if;
            else
                -- Reconhece o que o Flask (ou outro caminho) ja gravou, sem depender da data.
                if v_linha.natureza = 'CONTA' then
                    select c.id into v_id
                      from public.conta c
                     where c.item_despesa_id = v_item.id
                       and coalesce(c.is_fatura_cartao, false) = false
                       and (date_trunc('month', c.mes_referencia) = v_comp or date_trunc('month', c.data_vencimento) = v_comp)
                     order by c.id
                     limit 1;
                else
                    select l.id into v_id
                      from public.lancamento_agregado l
                     where l.compra_id = v_linha.compra_id
                        -- FIN-FATURA-INTEGRIDADE-1: pelo mes so os antigos, sem compra_id (uma compra de outra
                        -- competencia desviada para este mes por fatura paga nao e a deste mes).
                        or (l.item_despesa_id = v_item.id and l.mes_fatura = v_comp and l.is_recorrente
                            and l.compra_id is null)
                     order by l.id
                     limit 1;
                end if;
                v_linha.situacao := case when v_id is null then 'A_GERAR' else 'EXISTENTE' end;
                v_linha.registro_id := v_id;
            end if;
            return next v_linha;
            v_comp := (v_comp + v_passo)::date;
        end loop;
    end loop;

    -- 2) Faturas do mes e do seguinte para cada cartao ativo do perfil.
    for v_cartao in
        select c.id, c.nome, c.perfil_financeiro_id, cfg.dia_vencimento
          from public.item_despesa c
          left join public.config_agregador cfg on cfg.item_despesa_id = c.id
         where (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal))
           and c.tipo = 'Agregador'
           and coalesce(c.ativo, true)
         order by c.id
    loop
        foreach v_comp in array array[v_mes, v_limite] loop
            v_linha := null;
            v_linha.natureza := 'FATURA';
            v_linha.item_despesa_id := v_cartao.id;
            v_linha.nome := v_cartao.nome;
            v_linha.competencia := v_comp;
            v_linha.perfil_destino := v_cartao.perfil_financeiro_id;
            v_linha.cartao_id := v_cartao.id;

            select c.id into v_id
              from public.conta c
             where c.item_despesa_id = v_cartao.id
               and c.is_fatura_cartao
               and date_trunc('month', c.cartao_competencia) = v_comp
             order by c.id
             limit 1;
            if v_id is not null then
                v_linha.situacao := 'EXISTENTE';
                v_linha.registro_id := v_id;
            elsif v_cartao.dia_vencimento is null or v_cartao.dia_vencimento not between 1 and 31 then
                v_linha.situacao := 'REJEITADA';
                v_linha.motivo := 'Cartao sem dia de vencimento configurado';
            else
                -- Planejado como CartaoService.calcular_planejado: limites ativos do cartao
                -- no perfil; sem limites, orcamento legado vigente por item agregado.
                select count(*), coalesce(sum(lim.limite_mensal), 0) into v_qtd, v_linha.valor
                  from public.cartao_categoria_limite lim
                 where lim.cartao_id = v_cartao.id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo;
                if v_qtd = 0 then
                    select coalesce(sum(o.valor_teto), 0) into v_linha.valor
                      from public.item_agregado ia
                      cross join lateral (
                          select oa.valor_teto
                            from public.orcamento_agregado oa
                           where oa.item_agregado_id = ia.id
                             and oa.ativo
                             and oa.vigencia_inicio <= v_comp
                             and (oa.vigencia_fim is null or oa.vigencia_fim >= v_comp)
                           order by oa.id
                           limit 1
                      ) o
                     where ia.item_despesa_id = v_cartao.id;
                end if;
                v_linha.situacao := 'A_GERAR';
                v_linha.data_vencimento := financeiro.dia_contratual(v_comp, v_cartao.dia_vencimento);
            end if;
            return next v_linha;
        end loop;
    end loop;
end
$$;

create or replace function financeiro.gerar_mes_interno(p_perfil_id integer, p_mes date, p_total_previsto integer,
                                                        p_dispensar jsonb default '[]'::jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_mes        date;
    v_linhas     financeiro.linha_plano[];
    v_linha      financeiro.linha_plano;
    v_disp       record;
    v_a_gerar    integer;
    v_exec       bigint;
    v_id         integer;
    v_contas     integer := 0;
    v_lancs      integer := 0;
    v_faturas    integer := 0;
    v_dispensas  integer := 0;
    v_destino    date;  -- FIN-FATURA-INTEGRIDADE-1: mes da compra recorrente (desvia de fatura paga)
    v_corrida    integer := 0;  -- faturas criadas ao mesmo tempo por outro caminho
    v_registros  jsonb := '[]'::jsonb;
    v_resumo     jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null or p_total_previsto is null or p_total_previsto < 0 then
        raise exception 'Mes e total previsto sao obrigatorios' using errcode = '22023';
    end if;
    p_dispensar := coalesce(p_dispensar, '[]'::jsonb);
    if jsonb_typeof(p_dispensar) <> 'array' then
        raise exception 'Dispensas devem ser uma lista' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes::timestamp)::date;

    -- Uma geracao por perfil de cada vez (abas ou cliques concorrentes).
    perform pg_advisory_xact_lock(20261023, p_perfil_id);

    select coalesce(array_agg(p order by p.competencia, p.natureza, p.item_despesa_id), '{}')
      into v_linhas
      from financeiro.plano_recorrencia(p_perfil_id, v_mes) p;
    select count(*) into v_a_gerar from unnest(v_linhas) l where l.situacao = 'A_GERAR';

    if v_a_gerar = 0 and jsonb_array_length(p_dispensar) = 0 then
        return jsonb_build_object('execucao_id', null, 'mes', v_mes,
            'criadas', jsonb_build_object('contas', 0, 'lancamentos', 0, 'faturas', 0, 'total', 0),
            'existentes', (select count(*) from unnest(v_linhas) l where l.situacao = 'EXISTENTE'),
            'dispensadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'DISPENSADA'),
            'dispensadas_agora', 0,
            'rejeitadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'REJEITADA'),
            'registros', '[]'::jsonb);
    end if;
    if v_a_gerar <> p_total_previsto then
        raise exception 'A previa mudou desde a confirmacao (previstos %, agora %). Revise e confirme de novo.',
            p_total_previsto, v_a_gerar;
    end if;
    if v_a_gerar > 500 then
        raise exception 'Geracao excede o limite de 500 registros (%).', v_a_gerar;
    end if;

    -- FIN-FATURA-INTEGRIDADE-1: ordem global de travas (cartao -> faturas): os cartoes das linhas a
    -- gerar ficam travados, em ordem de id, antes de qualquer fatura.
    perform 1 from public.item_despesa i
     where i.id in (select l.cartao_id from unnest(v_linhas) l where l.situacao = 'A_GERAR' and l.cartao_id is not null)
     order by i.id
       for update;

    insert into financeiro.geracao_execucao (perfil_financeiro_id, mes, user_id, resumo)
    values (p_perfil_id, v_mes, (select auth.uid()), '{}'::jsonb)
    returning id into v_exec;

    for v_disp in
        select d.natureza, d.item_id, date_trunc('month', d.competencia::timestamp)::date as competencia, d.motivo
          from jsonb_to_recordset(p_dispensar) as d(natureza text, item_id integer, competencia date, motivo text)
    loop
        if not exists (select 1 from unnest(v_linhas) l
                        where l.situacao = 'A_GERAR' and l.natureza in ('CONTA', 'LANCAMENTO_CARTAO')
                          and l.natureza = v_disp.natureza and l.item_despesa_id = v_disp.item_id
                          and l.competencia = v_disp.competencia) then
            raise exception 'Dispensa invalida: so competencias a gerar de recorrencias podem ser dispensadas'
                using errcode = '22023';
        end if;
        insert into financeiro.recorrencia_competencia
            (item_despesa_id, natureza, competencia, situacao, execucao_id, motivo, user_id)
        values (v_disp.item_id, v_disp.natureza, v_disp.competencia, 'DISPENSADA', v_exec,
                coalesce(left(nullif(btrim(v_disp.motivo), ''), 200), 'Dispensada pelo usuario'), (select auth.uid()));
        v_dispensas := v_dispensas + 1;
    end loop;

    foreach v_linha in array v_linhas loop
        continue when v_linha.situacao <> 'A_GERAR';
        continue when exists (select 1 from financeiro.recorrencia_competencia r
                               where r.item_despesa_id = v_linha.item_despesa_id and r.natureza = v_linha.natureza
                                 and r.competencia = v_linha.competencia and r.situacao = 'DISPENSADA');
        if v_linha.natureza = 'CONTA' then
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor,
                                      data_vencimento, status_pagamento, debito_automatico, conta_bancaria_id,
                                      observacoes, is_fatura_cartao, estouro_orcamento, status_fatura, criado_em)
            values (v_linha.perfil_destino, v_linha.item_despesa_id, v_linha.competencia, v_linha.nome, v_linha.valor,
                    v_linha.data_vencimento, 'Pendente', v_linha.debito_automatico, v_linha.conta_bancaria_id,
                    v_linha.observacoes, false, false, 'ABERTA', now() at time zone 'utc')
            returning id into v_id;
            insert into financeiro.recorrencia_competencia
                (item_despesa_id, natureza, competencia, situacao, conta_id, execucao_id, user_id)
            values (v_linha.item_despesa_id, 'CONTA', v_linha.competencia, 'GERADA', v_id, v_exec, (select auth.uid()));
            v_contas := v_contas + 1;
        elsif v_linha.natureza = 'LANCAMENTO_CARTAO' then
            -- FIN-FATURA-INTEGRIDADE-1: fatura paga nao recebe a compra recorrente; ela vai para a
            -- proxima fatura nao paga, com a competencia original registrada. A identidade continua a
            -- da competencia (recorrencia_competencia e compra_id), entao ela nao e gerada de novo.
            v_destino := financeiro.fatura_elegivel_existente(v_linha.cartao_id, v_linha.competencia);
            insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, item_agregado_id, categoria_cartao_id,
                                                    categoria_id, descricao, valor, data_compra, mes_fatura,
                                                    numero_parcela, total_parcelas, observacoes, is_recorrente,
                                                    item_despesa_id, compra_id, is_importado, criado_em,
                                                    mes_fatura_original)
            values (v_linha.perfil_destino, v_linha.cartao_id, null, v_linha.categoria_cartao_id,
                    v_linha.categoria_id, v_linha.nome, v_linha.valor, v_linha.data_vencimento, v_destino,
                    1, 1, v_linha.observacoes, true,
                    v_linha.item_despesa_id, v_linha.compra_id, false, now() at time zone 'utc',
                    nullif(v_linha.competencia, v_destino))
            returning id into v_id;
            insert into financeiro.recorrencia_competencia
                (item_despesa_id, natureza, competencia, situacao, lancamento_id, execucao_id, user_id)
            values (v_linha.item_despesa_id, 'LANCAMENTO_CARTAO', v_linha.competencia, 'GERADA', v_id, v_exec,
                    (select auth.uid()));
            v_lancs := v_lancs + 1;
        else
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor,
                                      valor_planejado, valor_executado, data_vencimento, status_pagamento,
                                      is_fatura_cartao, cartao_competencia, estouro_orcamento, debito_automatico,
                                      status_fatura, criado_em)
            values (v_linha.perfil_destino, v_linha.item_despesa_id, v_linha.competencia,
                    'Fatura ' || v_linha.nome || ' - ' || to_char(v_linha.competencia, 'MM/YYYY'),
                    v_linha.valor, v_linha.valor, 0, v_linha.data_vencimento, 'Pendente',
                    true, v_linha.competencia, false, false, 'ABERTA', now() at time zone 'utc')
            on conflict (item_despesa_id, cartao_competencia) where is_fatura_cartao do nothing
            returning id into v_id;
            -- FIN-FATURA-UNICA-1: outra transacao (ex.: compra no Flask) criou a mesma fatura
            -- depois do plano; o indice unico decidiu e a existente e reconhecida.
            if v_id is null then
                v_corrida := v_corrida + 1;
                continue;
            end if;
            v_faturas := v_faturas + 1;
        end if;
        v_registros := v_registros || jsonb_build_object('natureza', v_linha.natureza, 'item_id', v_linha.item_despesa_id,
                                                         'competencia', v_linha.competencia, 'registro_id', v_id);
    end loop;

    v_resumo := jsonb_build_object(
        'execucao_id', v_exec,
        'mes', v_mes,
        'criadas', jsonb_build_object('contas', v_contas, 'lancamentos', v_lancs, 'faturas', v_faturas,
                                      'total', v_contas + v_lancs + v_faturas),
        'existentes', (select count(*) from unnest(v_linhas) l where l.situacao = 'EXISTENTE') + v_corrida,
        'dispensadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'DISPENSADA') + v_dispensas,
        'dispensadas_agora', v_dispensas,
        'rejeitadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'REJEITADA'),
        'rejeicoes', coalesce((select jsonb_agg(jsonb_build_object('item_id', l.item_despesa_id, 'nome', l.nome,
                                                                    'natureza', l.natureza, 'competencia', l.competencia,
                                                                    'motivo', l.motivo))
                                 from unnest(v_linhas) l where l.situacao = 'REJEITADA'), '[]'::jsonb),
        'registros', v_registros);
    update financeiro.geracao_execucao set resumo = v_resumo where id = v_exec;
    return v_resumo;
end
$$;

create or replace function financeiro.criar_compra(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_cartao;
    v_linha     record;
    v_compra    text := gen_random_uuid()::text;
    v_ids       integer[] := '{}';
    v_meses     date[] := '{}';
    v_fatura    integer;
    v_id        integer;
    v_cartao    integer;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261028));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao (recorrencias do cartao)

    for v_linha in select * from financeiro.plano_compra(p_perfil_id, p_dados) order by numero loop
        if v_cartao is null then
            -- FIN-FATURA-INTEGRIDADE-1: ordem global de travas: o cartao antes das faturas.
            perform 1 from public.item_despesa where id = v_linha.cartao_id for update;
        end if;
        v_cartao := v_linha.cartao_id;
        v_fatura := financeiro.garantir_fatura(p_perfil_id, v_linha.cartao_id, v_linha.mes_fatura);
        perform 1 from public.conta where id = v_fatura for update;  -- o pagamento (se vier) espera
        if financeiro.fatura_esta_paga(v_fatura) then
            raise exception 'A fatura de % foi paga durante o cadastro. Revise e tente de novo.',
                to_char(v_linha.mes_fatura, 'MM/YYYY') using errcode = 'P0001';
        end if;
        insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, item_agregado_id, categoria_cartao_id,
                                                categoria_id, descricao, valor, data_compra, mes_fatura, numero_parcela,
                                                total_parcelas, observacoes, is_recorrente, compra_id, is_importado,
                                                criado_em, mes_fatura_original)
        values (coalesce((select c.perfil_financeiro_id from public.conta c where c.id = v_fatura), p_perfil_id),
                v_linha.cartao_id, null, v_linha.categoria_cartao_id, v_linha.categoria_id, v_linha.descricao,
                v_linha.valor, v_linha.data_compra, v_linha.mes_fatura, v_linha.numero, v_linha.total,
                v_linha.observacoes, false, v_compra, false, now() at time zone 'utc',
                -- desviada de fatura paga: guarda a competencia em que entraria
                case when v_linha.redirecionada
                     then (date_trunc('month', (p_dados ->> 'mes_fatura')::date::timestamp)
                           + make_interval(months => v_linha.numero - 1))::date end)
        returning id into v_id;
        v_ids := v_ids || v_id;
        if not v_linha.mes_fatura = any(v_meses) then
            v_meses := v_meses || v_linha.mes_fatura;
        end if;
    end loop;
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_cartao, v_meses[i]);
    end loop;
    v_resultado := jsonb_build_object('compra_id', v_compra, 'lancamentos', to_jsonb(v_ids), 'faturas', to_jsonb(v_meses));
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_compra', v_resultado);
    return v_resultado;
end
$$;

create or replace function financeiro.travar_compra(p_perfil_id integer, p_lancamento_id integer, p_versao text)
    returns integer[]
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_l      public.lancamento_agregado;
    v_abertas integer[];
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_l from public.lancamento_agregado where id = p_lancamento_id;
    if not found or not financeiro.pertence_ao_perfil(v_l.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Compra nao encontrada neste perfil' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao (recorrencias do cartao)
    -- FIN-FATURA-INTEGRIDADE-1: ordem global: cartao -> faturas (por id) -> parcelas.
    perform 1 from public.item_despesa where id = v_l.cartao_id for update;
    -- Faturas das parcelas primeiro (um pagamento simultaneo espera), depois as parcelas.
    perform 1 from public.conta c
     where c.is_fatura_cartao and c.item_despesa_id = v_l.cartao_id
       and c.cartao_competencia in (select p.mes_fatura from financeiro.parcelas_da_compra(p_lancamento_id) p)
     order by c.id for update;
    perform 1 from public.lancamento_agregado l
     where l.id in (select p.id from financeiro.parcelas_da_compra(p_lancamento_id) p) order by l.id for update;
    if p_versao is null or p_versao is distinct from financeiro.versao_compra(p_lancamento_id) then
        raise exception 'A compra foi alterada por outra operacao. Recarregue e tente de novo.'
            using errcode = 'P0001', hint = 'VERSAO';
    end if;
    select coalesce(array_agg(p.id order by p.numero_parcela), '{}') into v_abertas
      from financeiro.parcelas_da_compra(p_lancamento_id) p where financeiro.bloqueio_da_parcela(p.id) is null;
    if cardinality(v_abertas) = 0 then
        raise exception 'Operacao bloqueada: %', financeiro.bloqueio_da_parcela(p_lancamento_id)
            using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    return v_abertas;
end
$$;

-- create or replace preserva os privilegios (gerar_mes_interno e travar_compra: internas;
-- criar_compra: so authenticated). Reafirmado:
revoke execute on function financeiro.gerar_mes_interno(integer, date, integer, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.plano_recorrencia(integer, date) from public, anon, authenticated;
revoke execute on function financeiro.travar_compra(integer, integer, text) from public, anon, authenticated;
revoke execute on function financeiro.criar_compra(integer, jsonb, uuid) from public, anon;
grant execute on function financeiro.criar_compra(integer, jsonb, uuid) to authenticated;
