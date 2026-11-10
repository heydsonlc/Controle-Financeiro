-- FIN-RECORRENCIAS-INATIVACAO-01 (P22): inativar uma recorrencia passa a interromper os efeitos dela a partir de uma data.
-- Antes, inativar_recorrencia so gravava ativo = false: o gerador parava de criar ocorrencias novas, mas as ja geradas
-- (Despesas gera ate o mes seguinte, e a tela abre meses adiante) continuavam exigiveis em Despesas, Faturas e Dashboard.
-- E "Excluir esta e as futuras" em Despesas exigia a recorrencia ativa: numa recorrencia ja inativa a acao era sempre
-- recusada ("A recorrencia nao pode ser inativada por aqui").
--
-- Mesmo mecanismo da exclusao de uma ocorrencia (nenhuma tabela ou coluna nova):
-- - conta: a competencia fica DISPENSADA (recorrencia_competencia, ou recorrencia_ocorrencia na semanal) e a conta
--   pendente sai, como em excluir_despesa; o motivo guarda a conta, o valor e o vencimento cancelados;
-- - compra no cartao: a previsao da recorrencia sai da fatura (como em excluir_compra), a competencia fica DISPENSADA e
--   a fatura e recalculada.
-- So o que e elegivel: pendente, sem pagamento, sem movimento, sem outro bloqueio e nao vencido; no cartao, so a previsao
-- (sem cobranca real confirmada, fatura nao paga e nao consolidada, sem credito). O resto fica e aparece na previa.
-- Data de efeito: por padrao, o inicio da competencia seguinte; a tela pode incluir a competencia atual. Inativar e
-- cancelar acontecem na mesma transacao (falha = nada muda). Repetir nao muda mais nada.
-- Reativar (retomar) dispensa as competencias do periodo inativo que nunca foram geradas (o gerador as criaria como
-- contas atrasadas) e so restaura as ocorrencias canceladas pela inativacao se o usuario pedir.
-- Nenhum dado existente muda nesta migration.

-- 1. Dispensa de uma conta gerada por recorrencia: o que excluir_despesa ja fazia, agora compartilhado com a interrupcao.
create function financeiro.dispensar_conta_recorrente(p_item public.item_despesa, p_conta public.conta, p_motivo text)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_ocorrencia date;  -- FIN-CATEGORIAS-RECORRENCIAS-2
begin
    if financeiro.semanas_da_recorrencia(p_item.tipo_recorrencia) is not null then
        -- Na semanal, dispensa so a ocorrencia desta conta (a gravada na geracao ou a do ciclo).
        v_ocorrencia := coalesce(
            (select o.data_ocorrencia from financeiro.recorrencia_ocorrencia o
              where o.item_despesa_id = p_item.id and o.conta_id = p_conta.id),
            financeiro.ocorrencia_semanal(p_item.tipo_recorrencia, p_item.data_vencimento, p_conta.data_vencimento));
        if v_ocorrencia is not null then
            insert into financeiro.recorrencia_ocorrencia (item_despesa_id, data_ocorrencia, situacao, motivo, user_id)
            values (p_item.id, v_ocorrencia, 'DISPENSADA', p_motivo, (select auth.uid()))
            on conflict (item_despesa_id, data_ocorrencia) do update
               set situacao = 'DISPENSADA', conta_id = null, execucao_id = null,
                   motivo = excluded.motivo, user_id = excluded.user_id, registrado_em = now();
        end if;
    else
        insert into financeiro.recorrencia_competencia
            (item_despesa_id, natureza, competencia, situacao, motivo, user_id)
        values (p_item.id, 'CONTA', date_trunc('month', p_conta.mes_referencia::timestamp)::date, 'DISPENSADA',
                p_motivo, (select auth.uid()))
        on conflict (item_despesa_id, natureza, competencia) do update
           set situacao = 'DISPENSADA', conta_id = null, lancamento_id = null, execucao_id = null,
               motivo = excluded.motivo, user_id = excluded.user_id, registrado_em = now();
    end if;
    delete from public.conta where id = p_conta.id;
end
$$;

-- 2. Data de efeito: o inicio da competencia informada ou, sem ela, o da competencia seguinte (horario de Brasilia).
create function financeiro.efeito_interrupcao(p_efeito date)
    returns date
    language sql
    stable
    set search_path = ''
as $$
    select coalesce(date_trunc('month', p_efeito::timestamp)::date,
                    (date_trunc('month', now() at time zone 'America/Sao_Paulo') + interval '1 month')::date)
$$;

-- 3. Por que a recorrencia nao pode ser interrompida/retomada aqui (null = pode).
create function financeiro.motivo_sem_interrupcao(p_perfil_id integer, p_item public.item_despesa)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select case
               when not financeiro.pode_gerir_perfil(p_perfil_id) then 'Perfil somente para leitura'
               when financeiro.gerador_do_perfil(p_perfil_id) <> 'NOVO' then 'Perfil ainda gravado pelo sistema anterior'
               when not coalesce(p_item.recorrente, false) or p_item.tipo is distinct from 'Simples'
                    or p_item.origem_tipo is not null then 'Recorrencia gerenciada por outro modulo: altere no modulo de origem'
           end
$$;

-- 4. Ocorrencias ja geradas a partir do efeito, cada uma com a elegibilidade e, se ficar, o motivo. p_conta_id: a
--    ocorrencia escolhida em Despesas ("esta e as futuras"), que entra mesmo vencida (escolha explicita do usuario).
create function financeiro.ocorrencias_interrupcao(p_item_id integer, p_efeito date, p_conta_id integer)
    returns table (natureza text, registro_id integer, competencia date, data_vencimento date, valor numeric,
                   cartao_id integer, elegivel boolean, motivo text)
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with hoje as (select (now() at time zone 'America/Sao_Paulo')::date as d),
    contas as (
        select c.id, date_trunc('month', c.mes_referencia::timestamp)::date as comp, c.data_vencimento as venc, c.valor,
               financeiro.bloqueio_da_despesa(c.id) as bloqueio
          from public.conta c
         where c.item_despesa_id = p_item_id
           and not coalesce(c.is_fatura_cartao, false)
           and (date_trunc('month', c.mes_referencia::timestamp)::date >= p_efeito or c.id = p_conta_id)
    ),
    compras as (
        select l.id, coalesce(l.mes_fatura_original, l.mes_fatura) as comp, l.data_compra as venc, l.valor, l.cartao_id,
               case when coalesce(l.is_importado, false) then 'Cobranca importada: preservada'
                    when exists (select 1 from financeiro.credito_fatura cf where cf.lancamento_id = l.id)
                         then 'Compra com credito vinculado: preservada'
                    when exists (select 1 from public.conta f
                                  where f.id = financeiro.fatura_do_mes(l.cartao_id, l.mes_fatura) and f.status_fatura = 'FECHADA')
                         then 'Fatura fechada (consolidada): preservada'
                    else case financeiro.situacao_previsao(l.id, 'FIXA', l.is_importado, l.cartao_id, l.mes_fatura)
                             when 'PREVISTA' then null
                             when 'PAGA' then 'Fatura paga: preservada'
                             when 'NAO_COBRADA' then 'Ja registrada como nao cobrada'
                             else 'Cobranca real confirmada: preservada' end
               end as bloqueio
          from public.lancamento_agregado l
         where l.item_despesa_id = p_item_id
           and coalesce(l.is_recorrente, false)
           and coalesce(l.mes_fatura_original, l.mes_fatura) >= p_efeito
    )
    select 'CONTA'::text, c.id, c.comp, c.venc, c.valor, null::integer,
           c.bloqueio is null and (c.venc >= h.d or c.id = p_conta_id),
           coalesce(c.bloqueio, case when c.venc < h.d and c.id is distinct from p_conta_id
                                     then 'Vencida e pendente: preservada (exclua individualmente, se for o caso)' end)
      from contas c cross join hoje h
    union all
    select 'LANCAMENTO_CARTAO'::text, l.id, l.comp, l.venc, l.valor, l.cartao_id, l.bloqueio is null, l.bloqueio
      from compras l
    order by 3, 1, 2
$$;

-- 5. Previa da interrupcao (somente leitura): o que deixa de ser exigivel e o que fica.
create function financeiro.previa_interrupcao_recorrencia(p_perfil_id integer, p_item_id integer, p_efeito date,
                                                          p_conta_id integer default null)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_item   public.item_despesa;
    v_efeito date;
    v_r      jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_item from public.item_despesa where id = p_item_id;
    if not found or not financeiro.pertence_ao_perfil(v_item.perfil_financeiro_id, p_perfil_id)
       or not coalesce(v_item.recorrente, false) then
        raise exception 'Recorrencia nao encontrada neste perfil' using errcode = '42501';
    end if;
    v_efeito := financeiro.efeito_interrupcao(p_efeito);
    select jsonb_build_object(
               'afetadas', coalesce(jsonb_agg(to_jsonb(o) - 'elegivel' - 'motivo') filter (where o.elegivel), '[]'::jsonb),
               'quantidade', count(*) filter (where o.elegivel),
               'total', coalesce(sum(o.valor) filter (where o.elegivel), 0),
               'preservadas', coalesce(jsonb_agg(to_jsonb(o) - 'elegivel') filter (where not o.elegivel), '[]'::jsonb),
               'total_preservado', coalesce(sum(o.valor) filter (where not o.elegivel), 0))
      into v_r
      from financeiro.ocorrencias_interrupcao(p_item_id, v_efeito, p_conta_id) o;
    return v_r || jsonb_build_object(
        'item_id', v_item.id, 'nome', v_item.nome, 'ativo', coalesce(v_item.ativo, true),
        'meio_pagamento', v_item.meio_pagamento, 'tipo_recorrencia', coalesce(v_item.tipo_recorrencia, 'mensal'),
        'efeito', v_efeito, 'efeito_padrao', financeiro.efeito_interrupcao(null),
        'competencia_atual', date_trunc('month', now() at time zone 'America/Sao_Paulo')::date,
        'motivo', financeiro.motivo_sem_interrupcao(p_perfil_id, v_item),
        'pode_interromper', financeiro.motivo_sem_interrupcao(p_perfil_id, v_item) is null,
        'versao', financeiro.versao_recorrencia(p_item_id));
end
$$;

-- 6. Interrupcao: inativa (se ainda ativa) e cancela as ocorrencias elegiveis a partir do efeito, numa so transacao.
--    p_esperadas: quantidade que a previa mostrou (diferente = recusa, nada muda). Ordem de travas como travar_despesa
--    (conta -> recorrencia -> geracao) e, no cartao, como travar_compra (geracao -> cartao -> faturas -> compras).
create function financeiro.interromper_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text, p_efeito date,
                                                   p_esperadas integer default null, p_conta_id integer default null)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item        public.item_despesa;
    v_cartao      boolean;
    v_efeito      date;
    v_oc          record;
    v_conta       public.conta;
    v_lanc        public.lancamento_agregado;
    v_motivo      text;
    v_meses       date[] := '{}';
    v_qtd         integer;
    v_preservadas integer;
    v_total       numeric := 0;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_item from public.item_despesa where id = p_item_id;
    if not found or not financeiro.pertence_ao_perfil(v_item.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Recorrencia nao encontrada neste perfil' using errcode = '42501';
    end if;
    v_cartao := coalesce(v_item.meio_pagamento, '') = 'cartao';
    v_efeito := financeiro.efeito_interrupcao(p_efeito);
    if not v_cartao then
        perform 1 from public.conta c
         where c.item_despesa_id = p_item_id and not coalesce(c.is_fatura_cartao, false)
           and (date_trunc('month', c.mes_referencia::timestamp)::date >= v_efeito or c.id = p_conta_id)
         order by c.id
           for update;
        v_item := financeiro.travar_recorrencia(p_perfil_id, p_item_id, p_versao);
        perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao
    else
        v_item := financeiro.travar_recorrencia_cartao(p_perfil_id, p_item_id, p_versao);  -- ja com a trava da geracao
        perform 1 from public.item_despesa where id = v_item.cartao_id for update;
        perform 1 from public.conta f
         where f.is_fatura_cartao and f.item_despesa_id = v_item.cartao_id
           and f.cartao_competencia in (select l.mes_fatura from public.lancamento_agregado l
                                         where l.item_despesa_id = p_item_id and coalesce(l.is_recorrente, false)
                                           and coalesce(l.mes_fatura_original, l.mes_fatura) >= v_efeito)
         order by f.id
           for update;
        perform 1 from public.lancamento_agregado l
         where l.item_despesa_id = p_item_id and coalesce(l.is_recorrente, false)
           and coalesce(l.mes_fatura_original, l.mes_fatura) >= v_efeito
         order by l.id
           for update;
    end if;
    if p_conta_id is not null and (v_cartao or not exists (select 1 from public.conta c
                                                            where c.id = p_conta_id and c.item_despesa_id = p_item_id)) then
        raise exception 'A despesa escolhida nao e desta recorrencia' using errcode = '22023';
    end if;

    select count(*) filter (where o.elegivel), count(*) filter (where not o.elegivel) into v_qtd, v_preservadas
      from financeiro.ocorrencias_interrupcao(p_item_id, v_efeito, p_conta_id) o;
    if p_esperadas is not null and v_qtd <> p_esperadas then
        raise exception 'A previa mudou desde a confirmacao (previstas %, agora %). Revise e confirme de novo.', p_esperadas, v_qtd
            using errcode = 'P0001', hint = 'PREVIA';
    end if;

    for v_oc in select * from financeiro.ocorrencias_interrupcao(p_item_id, v_efeito, p_conta_id) o where o.elegivel loop
        if v_oc.natureza = 'CONTA' then
            select * into v_conta from public.conta where id = v_oc.registro_id for update;
            v_motivo := format('Interrompida pela inativacao da recorrencia: conta #%s de R$ %s, vencimento %s',
                               v_conta.id, v_conta.valor, to_char(v_conta.data_vencimento, 'DD/MM/YYYY'));
            perform financeiro.dispensar_conta_recorrente(v_item, v_conta, v_motivo);
        else
            select * into v_lanc from public.lancamento_agregado where id = v_oc.registro_id;
            v_motivo := format('Interrompida pela inativacao da recorrencia: compra #%s de R$ %s na fatura de %s',
                               v_lanc.id, v_lanc.valor, to_char(v_lanc.mes_fatura, 'MM/YYYY'));
            update financeiro.recorrencia_competencia r
               set situacao = 'DISPENSADA', conta_id = null, lancamento_id = null, execucao_id = null,
                   motivo = v_motivo, user_id = (select auth.uid()), registrado_em = now()
             where r.item_despesa_id = p_item_id and r.natureza = 'LANCAMENTO_CARTAO' and r.lancamento_id = v_lanc.id;
            if not found then
                insert into financeiro.recorrencia_competencia
                    (item_despesa_id, natureza, competencia, situacao, motivo, user_id)
                values (p_item_id, 'LANCAMENTO_CARTAO', v_oc.competencia, 'DISPENSADA', v_motivo, (select auth.uid()))
                on conflict (item_despesa_id, natureza, competencia) do update
                   set situacao = 'DISPENSADA', conta_id = null, lancamento_id = null, execucao_id = null,
                       motivo = excluded.motivo, user_id = excluded.user_id, registrado_em = now();
            end if;
            delete from public.lancamento_agregado where id = v_lanc.id;
            if not v_lanc.mes_fatura = any(v_meses) then
                v_meses := v_meses || v_lanc.mes_fatura;
            end if;
        end if;
        v_total := v_total + v_oc.valor;
    end loop;
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_item.cartao_id, v_meses[i]);
    end loop;
    if coalesce(v_item.ativo, true) then
        update public.item_despesa set ativo = false where id = p_item_id;
    end if;
    return jsonb_build_object('item_id', p_item_id, 'ativo', false, 'efeito', v_efeito, 'canceladas', v_qtd,
                              'valor_cancelado', v_total, 'preservadas', v_preservadas,
                              'versao', financeiro.versao_recorrencia(p_item_id));
end
$$;

-- 7. Competencias anteriores a p_ate que o gerador ainda criaria (sem registro e sem conta/compra reconhecida): na
--    retomada, sao o periodo inativo. Mesmo reconhecimento de plano_recorrencia (a semanal usa ocorrencias_semanais).
create function financeiro.lacunas_da_recorrencia(p_item_id integer, p_ate date)
    returns table (natureza text, competencia date, data_vencimento date)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
#variable_conflict use_column
declare
    v_item     public.item_despesa;
    v_natureza text;
    v_comp     date;
    v_passo    interval;
    v_dia      integer;
    v_base     financeiro.linha_plano;
    v_ns       constant uuid := '7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c';  -- namespace do Flask (compra_id)
begin
    select * into v_item from public.item_despesa where id = p_item_id;
    if not found or v_item.data_vencimento is null or p_ate is null then
        return;
    end if;
    v_natureza := case when v_item.meio_pagamento = 'cartao' then 'LANCAMENTO_CARTAO' else 'CONTA' end;
    if financeiro.semanas_da_recorrencia(v_item.tipo_recorrencia) is not null then
        if v_natureza <> 'CONTA' then
            return;  -- semanal no cartao nao e gerada
        end if;
        v_base.natureza := 'CONTA';
        v_base.item_despesa_id := v_item.id;
        v_base.nome := v_item.nome;
        return query
            select o.natureza, o.competencia, o.data_vencimento
              from financeiro.ocorrencias_semanais(v_base, v_item.tipo_recorrencia, v_item.data_vencimento,
                                                   (p_ate - interval '1 month')::date) o
             where o.situacao = 'A_GERAR' and o.data_vencimento < p_ate;
        return;
    end if;
    if coalesce(v_item.tipo_recorrencia, 'mensal') not in ('mensal', 'anual') then
        return;
    end if;
    v_dia := extract(day from v_item.data_vencimento)::integer;
    v_passo := case when v_item.tipo_recorrencia = 'anual' then interval '1 year' else interval '1 month' end;
    v_comp := date_trunc('month', v_item.data_vencimento::timestamp)::date;
    while v_comp < p_ate loop
        if not exists (select 1 from financeiro.recorrencia_competencia r
                        where r.item_despesa_id = v_item.id and r.natureza = v_natureza and r.competencia = v_comp)
           and (v_natureza <> 'CONTA' or not exists (
                   select 1 from public.conta c
                    where c.item_despesa_id = v_item.id and not coalesce(c.is_fatura_cartao, false)
                      and (date_trunc('month', c.mes_referencia) = v_comp or date_trunc('month', c.data_vencimento) = v_comp)))
           and (v_natureza <> 'LANCAMENTO_CARTAO' or not exists (
                   select 1 from public.lancamento_agregado l
                    where l.compra_id = extensions.uuid_generate_v5(v_ns, format('%s-%s', v_item.id, to_char(v_comp, 'YYYY-MM-DD')))::text
                       or (l.item_despesa_id = v_item.id and l.mes_fatura = v_comp and l.is_recorrente and l.compra_id is null))) then
            natureza := v_natureza;
            competencia := v_comp;
            data_vencimento := financeiro.dia_contratual(v_comp, v_dia);
            return next;
        end if;
        v_comp := (v_comp + v_passo)::date;
    end loop;
end
$$;

-- 8. Previa da retomada (somente leitura): periodo inativo que nao sera gerado, ocorrencias canceladas pela inativacao
--    que podem ser restauradas a partir da retomada e as excluidas uma a uma (ficam como estao).
create function financeiro.previa_retomada_recorrencia(p_perfil_id integer, p_item_id integer, p_retomada date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_item     public.item_despesa;
    v_retomada date;
    v_lacunas  jsonb;
    v_rest     jsonb;
    v_mantidas integer;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_item from public.item_despesa where id = p_item_id;
    if not found or not financeiro.pertence_ao_perfil(v_item.perfil_financeiro_id, p_perfil_id)
       or not coalesce(v_item.recorrente, false) then
        raise exception 'Recorrencia nao encontrada neste perfil' using errcode = '42501';
    end if;
    v_retomada := coalesce(date_trunc('month', p_retomada::timestamp)::date,
                           date_trunc('month', now() at time zone 'America/Sao_Paulo')::date);
    select coalesce(jsonb_agg(to_jsonb(l) order by l.data_vencimento), '[]'::jsonb) into v_lacunas
      from financeiro.lacunas_da_recorrencia(p_item_id, v_retomada) l;
    select coalesce(jsonb_agg(jsonb_build_object('competencia', x.competencia, 'motivo', x.motivo) order by x.competencia), '[]'::jsonb)
      into v_rest
      from (select r.competencia, r.motivo from financeiro.recorrencia_competencia r
             where r.item_despesa_id = p_item_id and r.situacao = 'DISPENSADA' and r.competencia >= v_retomada
               and r.motivo like 'Interrompida pela inativacao%'
            union all
            select o.data_ocorrencia, o.motivo from financeiro.recorrencia_ocorrencia o
             where o.item_despesa_id = p_item_id and o.situacao = 'DISPENSADA' and o.data_ocorrencia >= v_retomada
               and o.motivo like 'Interrompida pela inativacao%') x;
    select (select count(*) from financeiro.recorrencia_competencia r
             where r.item_despesa_id = p_item_id and r.situacao = 'DISPENSADA' and r.competencia >= v_retomada
               and r.motivo not like 'Interrompida pela inativacao%')
         + (select count(*) from financeiro.recorrencia_ocorrencia o
             where o.item_despesa_id = p_item_id and o.situacao = 'DISPENSADA' and o.data_ocorrencia >= v_retomada
               and o.motivo not like 'Interrompida pela inativacao%')
      into v_mantidas;
    return jsonb_build_object(
        'item_id', v_item.id, 'nome', v_item.nome, 'ativo', coalesce(v_item.ativo, true), 'valor', v_item.valor,
        'meio_pagamento', v_item.meio_pagamento, 'retomada', v_retomada,
        'lacunas', v_lacunas, 'quantidade_lacunas', jsonb_array_length(v_lacunas),
        'restauraveis', v_rest, 'quantidade_restauraveis', jsonb_array_length(v_rest),
        'total_restauravel', jsonb_array_length(v_rest) * coalesce(v_item.valor, 0),
        'dispensadas_mantidas', v_mantidas,
        'motivo', financeiro.motivo_sem_interrupcao(p_perfil_id, v_item),
        'pode_retomar', financeiro.motivo_sem_interrupcao(p_perfil_id, v_item) is null,
        'versao', financeiro.versao_recorrencia(p_item_id));
end
$$;

-- 9. Retomada: reativa a partir de p_retomada (padrao: competencia atual). O periodo inativo nunca gerado fica
--    DISPENSADO (o gerador nao cria contas atrasadas); as canceladas pela inativacao so voltam com p_restaurar.
--    Recorrencia ja ativa: nada muda.
create function financeiro.retomar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text, p_retomada date,
                                               p_restaurar boolean default false)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item       public.item_despesa;
    v_retomada   date;
    v_lacuna     record;
    v_motivo     text;
    v_lacunas    integer := 0;
    v_restauradas integer := 0;
    v_n          integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_item from public.item_despesa where id = p_item_id;
    if not found or not financeiro.pertence_ao_perfil(v_item.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Recorrencia nao encontrada neste perfil' using errcode = '42501';
    end if;
    if coalesce(v_item.meio_pagamento, '') = 'cartao' then
        v_item := financeiro.travar_recorrencia_cartao(p_perfil_id, p_item_id, p_versao);  -- ja com a trava da geracao
    else
        v_item := financeiro.travar_recorrencia(p_perfil_id, p_item_id, p_versao);
        perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- nao muda no meio de uma geracao
    end if;
    v_retomada := coalesce(date_trunc('month', p_retomada::timestamp)::date,
                           date_trunc('month', now() at time zone 'America/Sao_Paulo')::date);
    if coalesce(v_item.ativo, true) then
        return jsonb_build_object('item_id', p_item_id, 'ativo', true, 'retomada', null, 'lacunas_dispensadas', 0,
                                  'restauradas', 0, 'versao', financeiro.versao_recorrencia(p_item_id));
    end if;
    if coalesce(v_item.meio_pagamento, '') = 'cartao' then
        perform financeiro.cartao_do_perfil(p_perfil_id, v_item.cartao_id, true);  -- cartao inativo nao recebe compra nova
    end if;
    v_motivo := format('Periodo inativo: recorrencia retomada a partir de %s', to_char(v_retomada, 'MM/YYYY'));
    for v_lacuna in select * from financeiro.lacunas_da_recorrencia(p_item_id, v_retomada) loop
        if financeiro.semanas_da_recorrencia(v_item.tipo_recorrencia) is not null then
            insert into financeiro.recorrencia_ocorrencia (item_despesa_id, data_ocorrencia, situacao, motivo, user_id)
            values (p_item_id, v_lacuna.data_vencimento, 'DISPENSADA', v_motivo, (select auth.uid()));
        else
            insert into financeiro.recorrencia_competencia (item_despesa_id, natureza, competencia, situacao, motivo, user_id)
            values (p_item_id, v_lacuna.natureza, v_lacuna.competencia, 'DISPENSADA', v_motivo, (select auth.uid()));
        end if;
        v_lacunas := v_lacunas + 1;
    end loop;
    if coalesce(p_restaurar, false) then
        delete from financeiro.recorrencia_competencia r
         where r.item_despesa_id = p_item_id and r.situacao = 'DISPENSADA' and r.competencia >= v_retomada
           and r.motivo like 'Interrompida pela inativacao%';
        get diagnostics v_n = row_count;
        v_restauradas := v_n;
        delete from financeiro.recorrencia_ocorrencia o
         where o.item_despesa_id = p_item_id and o.situacao = 'DISPENSADA' and o.data_ocorrencia >= v_retomada
           and o.motivo like 'Interrompida pela inativacao%';
        get diagnostics v_n = row_count;
        v_restauradas := v_restauradas + v_n;
    end if;
    update public.item_despesa set ativo = true where id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'ativo', true, 'retomada', v_retomada, 'lacunas_dispensadas', v_lacunas,
                              'restauradas', v_restauradas, 'versao', financeiro.versao_recorrencia(p_item_id));
end
$$;

-- 10. Funcoes existentes (mesmas assinaturas e permissoes) passam pelo mesmo caminho.
-- As funcoes antigas continuam so para recorrencias fora do cartao (o cartao tem definir_situacao_recorrencia_cartao):
-- mesma ordem de recusa de travar_recorrencia (perfil, recorrencia do perfil, modulo), sem travar nada antes das contas.
create function financeiro.exigir_recorrencia_fora_do_cartao(p_perfil_id integer, p_item_id integer)
    returns void
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_item public.item_despesa;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_item from public.item_despesa where id = p_item_id;
    if not found or not financeiro.pertence_ao_perfil(v_item.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Recorrencia nao encontrada neste perfil' using errcode = '42501';
    end if;
    if coalesce(v_item.meio_pagamento, '') = 'cartao' then
        raise exception 'Operacao bloqueada: recorrencia gerenciada por outro modulo' using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
end
$$;

create or replace function financeiro.inativar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    -- P22: inativar interrompe a partir da competencia seguinte (as ocorrencias ja geradas e elegiveis saem).
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.exigir_recorrencia_fora_do_cartao(p_perfil_id, p_item_id);
    return financeiro.interromper_recorrencia(p_perfil_id, p_item_id, p_versao, null, null, null);
end
$$;

create or replace function financeiro.reativar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    -- P22: retoma na competencia atual, sem gerar o periodo inativo e sem restaurar o que a inativacao cancelou.
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.exigir_recorrencia_fora_do_cartao(p_perfil_id, p_item_id);
    return financeiro.retomar_recorrencia(p_perfil_id, p_item_id, p_versao, null, false);
end
$$;

create or replace function financeiro.definir_situacao_recorrencia_cartao(p_perfil_id integer, p_item_id integer,
                                                                          p_versao text, p_ativo boolean)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    -- Mesma ordem de recusa de travar_recorrencia_cartao (gestao, depois perfil do Flask).
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.exigir_gerador_novo(p_perfil_id);
    if p_ativo is null then
        raise exception 'Situacao invalida' using errcode = '22023';
    end if;
    -- P22: inativar tira as previsoes elegiveis das faturas a partir da competencia seguinte; reativar retoma sem
    -- lancar o periodo inativo.
    if p_ativo then
        return financeiro.retomar_recorrencia(p_perfil_id, p_item_id, p_versao, null, false);
    end if;
    return financeiro.interromper_recorrencia(p_perfil_id, p_item_id, p_versao, null, null, null);
end
$$;

create or replace function financeiro.excluir_despesa(p_perfil_id integer, p_conta_id integer, p_versao text)
    returns jsonb
    language plpgsql
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
        -- P22: a dispensa da competencia (ou da ocorrencia, na semanal) e a saida da conta ficam em dispensar_conta_recorrente.
        perform financeiro.dispensar_conta_recorrente(v_item, v_conta, 'Conta excluida pelo usuario');
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

revoke execute on function financeiro.dispensar_conta_recorrente(public.item_despesa, public.conta, text) from public, anon, authenticated;
revoke execute on function financeiro.efeito_interrupcao(date) from public, anon, authenticated;
revoke execute on function financeiro.motivo_sem_interrupcao(integer, public.item_despesa) from public, anon, authenticated;
revoke execute on function financeiro.ocorrencias_interrupcao(integer, date, integer) from public, anon, authenticated;
revoke execute on function financeiro.lacunas_da_recorrencia(integer, date) from public, anon, authenticated;
revoke execute on function financeiro.exigir_recorrencia_fora_do_cartao(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.previa_interrupcao_recorrencia(integer, integer, date, integer) from public, anon;
revoke execute on function financeiro.interromper_recorrencia(integer, integer, text, date, integer, integer) from public, anon;
revoke execute on function financeiro.previa_retomada_recorrencia(integer, integer, date) from public, anon;
revoke execute on function financeiro.retomar_recorrencia(integer, integer, text, date, boolean) from public, anon;
grant execute on function financeiro.previa_interrupcao_recorrencia(integer, integer, date, integer) to authenticated;
grant execute on function financeiro.interromper_recorrencia(integer, integer, text, date, integer, integer) to authenticated;
grant execute on function financeiro.previa_retomada_recorrencia(integer, integer, date) to authenticated;
grant execute on function financeiro.retomar_recorrencia(integer, integer, text, date, boolean) to authenticated;
