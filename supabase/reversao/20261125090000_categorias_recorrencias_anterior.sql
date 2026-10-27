-- Reversao de 20261125090000_financeiro_categorias_recorrencias.sql (FIN-CATEGORIAS-RECORRENCIAS-2).
-- Restaura as funcoes substituidas pelo texto anterior e remove as novas. Recusa se o novo motor ja gerou ou dispensou
-- ocorrencias semanais (a identidade delas se perderia) ou se o catalogo ja foi passado ao novo aplicativo.

do $$
begin
    if exists (select 1 from financeiro.recorrencia_ocorrencia) then
        raise exception 'Reversao recusada: ha ocorrencias semanais registradas (financeiro.recorrencia_ocorrencia)';
    end if;
    if exists (select 1 from financeiro.catalogo_categorias where escritor = 'NOVO') then
        raise exception 'Reversao recusada: o catalogo de categorias esta com o novo aplicativo';
    end if;
end
$$;

-- plano_recorrencia: texto de 20261108090000.
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
    v_consolidada date;  -- FIN-CARTOES-D6-INTEGRIDADE-1
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
           -- FIN-FIDELIDADE-CARTOES-2 (R4): o proprio cartao (Agregador) e gravado como recorrente (como no Flask), mas a
           -- fatura dele e gerada pela parte de cartoes; ele nao e uma recorrencia que produz despesa.
           and i.tipo is distinct from 'Agregador'
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
                -- FIN-CARTOES-D6-INTEGRIDADE-1: a geracao automatica nao e confirmacao do usuario (D6) e nao muda a
                -- competencia (D5): compra recorrente cujo destino e fatura consolidada nao e gerada (nem em silencio,
                -- nem em outro mes). Fica REJEITADA, com o motivo na previa, ate o usuario lancar pela compra, com a
                -- confirmacao. Nada e gravado; a proxima previa reavalia (idempotente).
                if v_linha.natureza = 'LANCAMENTO_CARTAO' and v_linha.situacao = 'A_GERAR' then
                    v_consolidada := financeiro.fatura_consolidada_no_destino(v_linha.cartao_id, v_comp);
                    if v_consolidada is not null then
                        v_linha.situacao := 'REJEITADA';
                        v_linha.motivo := 'Fatura de ' || to_char(v_consolidada, 'MM/YYYY')
                            || ' consolidada: a compra recorrente nao entra sem confirmacao (lance-a pela compra no cartao)';
                    end if;
                end if;
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

-- gerar_mes_interno: texto de 20261030090000.
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
    -- FIN-CARTOES-RECORRENCIA-PENDENCIA-1: a tentativa registra as compras recorrentes rejeitadas por fatura consolidada
    -- (uma ocorrencia por recorrencia + competencia; se a geracao falhar, o registro e desfeito junto).
    perform financeiro.registrar_rejeicoes_consolidadas(v_linhas, 'NOVO_APP');

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
            -- FIN-CARTOES-D6-INTEGRIDADE-1: a fatura de destino (travada acima) foi consolidada depois da previa:
            -- nada entra em silencio. Erro controlado; a geracao inteira e desfeita e a nova previa mostra o motivo.
            if exists (select 1 from public.conta c
                        where c.id = financeiro.fatura_do_mes(v_linha.cartao_id, v_destino) and c.status_fatura = 'FECHADA') then
                raise exception 'A fatura de % foi consolidada depois da previa: a compra recorrente "%" nao entra sem confirmacao. Revise e confirme de novo.',
                    to_char(v_destino, 'MM/YYYY'), v_linha.nome using errcode = 'P0001', hint = 'CONSOLIDADA';
            end if;
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

-- ler_dados_despesa: texto de 20261026090000.
create or replace function financeiro.ler_dados_despesa(p_dados jsonb, p_perfil_id integer, p_parcial boolean)
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
    v_data  date;
    v_int   integer;
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da despesa invalidos' using errcode = '22023';
    end if;
    if p_dados ->> 'meio_pagamento' = 'cartao' or p_dados ? 'cartao_id' then
        raise exception 'Despesas de cartao ficam no modulo de cartoes' using errcode = '22023';
    end if;

    if p_dados ? 'nome' or not p_parcial then
        v_texto := btrim(coalesce(p_dados ->> 'nome', ''));
        if v_texto = '' or length(v_texto) > 100 then
            raise exception 'Nome obrigatorio (ate 100 caracteres)' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('nome', v_texto);
    end if;

    if p_dados ? 'valor' or not p_parcial then
        begin
            v_valor := (p_dados ->> 'valor')::numeric;
        exception when others then
            raise exception 'Valor invalido' using errcode = '22023';
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
        if v_data is null or v_data < date '2000-01-01' or v_data > date '2100-12-31' then
            raise exception 'Data de vencimento invalida' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('data_vencimento', v_data);
    end if;

    if p_dados ? 'competencia' and nullif(p_dados ->> 'competencia', '') is not null then
        begin
            v_data := date_trunc('month', (p_dados ->> 'competencia')::date::timestamp)::date;
        exception when others then
            raise exception 'Competencia invalida' using errcode = '22023';
        end;
        v_saida := v_saida || jsonb_build_object('competencia', v_data);
    end if;

    if p_dados ? 'tipo_recorrencia' then
        if p_dados ->> 'tipo_recorrencia' not in ('mensal', 'anual') then
            raise exception 'Recorrencia deve ser mensal ou anual' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('tipo_recorrencia', p_dados ->> 'tipo_recorrencia');
    end if;

    if p_dados ? 'descricao' then
        v_texto := nullif(btrim(coalesce(p_dados ->> 'descricao', '')), '');
        if length(v_texto) > 1000 then
            raise exception 'Observacoes ate 1000 caracteres' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('descricao', v_texto);
    end if;

    if p_dados ? 'debito_automatico' or not p_parcial then
        if coalesce((p_dados ->> 'debito_automatico')::boolean, false) then
            begin
                v_int := (p_dados ->> 'conta_bancaria_id')::integer;
            exception when others then
                v_int := null;
            end;
            if v_int is null or not exists (
                select 1 from public.conta_bancaria b
                 where b.id = v_int and b.status = 'ATIVO'
                   and financeiro.pertence_ao_perfil(b.perfil_financeiro_id, p_perfil_id)) then
                raise exception 'Debito automatico exige uma conta bancaria ativa do perfil' using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object('debito_automatico', true, 'conta_bancaria_id', v_int);
        else
            v_saida := v_saida || jsonb_build_object('debito_automatico', false, 'conta_bancaria_id', null);
        end if;
    end if;
    return v_saida;
end
$$;

-- excluir_despesa: texto de 20261124090000.
create or replace function financeiro.excluir_despesa(p_perfil_id integer, p_conta_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_conta        public.conta;
    v_item         public.item_despesa;
    v_item_apagado boolean := false;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.travar_despesa(p_perfil_id, p_conta_id, p_versao);
    select * into v_conta from public.conta where id = p_conta_id;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id;

    if coalesce(v_item.recorrente, false) then
        if financeiro.gerador_do_perfil(p_perfil_id) <> 'NOVO' then
            raise exception 'Conta recorrente gerada pelo sistema atual: o Flask a recriaria. Exclua pelo sistema atual.'
                using errcode = 'P0001', hint = 'GERADOR_FLASK';
        end if;
        perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao
        insert into financeiro.recorrencia_competencia
            (item_despesa_id, natureza, competencia, situacao, motivo, user_id)
        values (v_item.id, 'CONTA', date_trunc('month', v_conta.mes_referencia::timestamp)::date, 'DISPENSADA',
                'Conta excluida pelo usuario', (select auth.uid()))
        on conflict (item_despesa_id, natureza, competencia) do update
           set situacao = 'DISPENSADA', conta_id = null, lancamento_id = null, execucao_id = null,
               motivo = excluded.motivo, user_id = excluded.user_id, registrado_em = now();
        delete from public.conta where id = p_conta_id;
    else
        delete from public.conta where id = p_conta_id;
        -- Item avulso sem outra referencia sai junto (o Flask o deixava orfao).
        if not exists (select 1 from public.conta c where c.item_despesa_id = v_item.id) then
            begin
                delete from public.item_despesa where id = v_item.id;
                v_item_apagado := true;
            exception when foreign_key_violation then
                v_item_apagado := false;
            end;
        end if;
    end if;
    return jsonb_build_object('conta_id', p_conta_id, 'item_excluido', v_item_apagado,
                              'competencia_dispensada', coalesce(v_item.recorrente, false));
end
$$;

-- recorrencias_do_perfil: texto de 20261103090000.
create or replace function financeiro.recorrencias_do_perfil(p_perfil_id integer)
    returns table (id integer, nome text, descricao text, valor numeric, categoria_id integer, categoria_nome text,
                   categoria_cor text, tipo_recorrencia text, data_vencimento date, proximo_vencimento date,
                   meio_pagamento text, cartao_id integer, cartao_nome text, conta_bancaria_id integer,
                   conta_bancaria_nome text, ativo boolean, gerenciavel boolean, versao text)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_pessoal boolean;
    v_hoje date := (now() at time zone 'America/Sao_Paulo')::date;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');
    return query
        select i.id, i.nome::text, i.descricao::text, i.valor, i.categoria_id, cat.nome::text, cat.cor::text,
               coalesce(i.tipo_recorrencia, 'mensal')::text, i.data_vencimento,
               -- Mesmo calculo do Flask (_proximo_vencimento) para mensal e anual, sem deslizar o dia contratual
               -- (soma a partir da data original, como o gerador). Outras frequencias: so a data se ainda vier.
               case
                   when i.data_vencimento is null then null
                   when i.data_vencimento >= v_hoje then i.data_vencimento
                   when coalesce(i.tipo_recorrencia, 'mensal') in ('mensal', 'anual') then (
                       select min(d)::date
                         from generate_series(0, 1200) k,
                              lateral (select case when coalesce(i.tipo_recorrencia, 'mensal') = 'anual'
                                                   then i.data_vencimento + make_interval(years => k)
                                                   else i.data_vencimento + make_interval(months => k) end as d) x
                        where x.d >= v_hoje)
               end,
               i.meio_pagamento::text, i.cartao_id, cartao.nome::text, i.conta_bancaria_id, cb.nome::text,
               coalesce(i.ativo, true),
               i.tipo = 'Simples' and i.origem_tipo is null and coalesce(i.meio_pagamento, '') <> 'cartao',
               financeiro.versao_recorrencia(i.id)
          from public.item_despesa i
          left join public.categoria cat on cat.id = i.categoria_id
          left join public.item_despesa cartao on cartao.id = i.cartao_id
          left join public.conta_bancaria cb on cb.id = i.conta_bancaria_id
         where (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))
           and coalesce(i.recorrente, false)
           and i.tipo is distinct from 'Consorcio'
           and i.tipo is distinct from 'Agregador'
         order by i.nome, i.id;
end
$$;

-- receita_orcamento_flask: texto de 20261119090000.
create or replace function financeiro.receita_orcamento_flask(p_o public.receita_orcamento)
    returns jsonb
    language sql
    stable
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_o.id, 'perfil_financeiro_id', p_o.perfil_financeiro_id, 'item_receita_id', p_o.item_receita_id,
        'mes_referencia', to_char(p_o.mes_referencia, 'YYYY-MM-DD'), 'valor_esperado', p_o.valor_esperado,
        'periodicidade', p_o.periodicidade, 'observacoes', p_o.observacoes)
$$;
drop function financeiro.redefinir_fonte_receita(integer, integer, text, jsonb);
drop function financeiro.receber_sem_previsao(integer, jsonb, uuid);
drop function financeiro.criar_categoria(jsonb, uuid);
drop function financeiro.editar_categoria(integer, jsonb);
drop function financeiro.excluir_categoria(integer);
drop function financeiro.criar_palavra_chave(integer, text);
drop function financeiro.remover_palavra_chave(integer, integer);
drop function financeiro.situacao_catalogo_categorias();
drop function financeiro.vinculos_da_categoria(integer);
drop function financeiro.validar_nome_categoria(text, integer);
drop function financeiro.ler_dados_categoria(jsonb, boolean);
drop function financeiro.exigir_escrita_catalogo();
drop function financeiro.definir_gestor_catalogo(uuid, boolean, text, text);
drop function financeiro.definir_escritor_catalogo(text, text, text);
drop function financeiro.categorias_sistemicas_mobilidade();
drop table financeiro.operacao_catalogo;
drop table financeiro.gestor_catalogo;
drop table financeiro.catalogo_categorias;
drop function financeiro.ocorrencias_semanais(financeiro.linha_plano, text, date, date);
drop function financeiro.semanas_do_item(integer);
drop function financeiro.proxima_ocorrencia_semanal(text, date, date);
drop function financeiro.ocorrencia_semanal(text, date, date);
drop function financeiro.ancora_semanal(text, date);
drop function financeiro.semanas_da_recorrencia(text);
drop table financeiro.recorrencia_ocorrencia;
