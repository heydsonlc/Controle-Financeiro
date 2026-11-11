-- FIN-RECEITAS-SALDO-01: atualizacao das previsoes de receita pelo valor-base e regra unica do total de receitas.
--
-- 1. Valor-base de fonte recorrente: redefinir_fonte_receita (como o Flask) grava o valor na fonte e so cria as previsoes
--    que faltam nos 12 meses seguintes; as gravadas ficam com o valor antigo (ex.: Cargo em Comissao e Salario CBMGO de
--    12/2026 a 04/2027). Agora a tela oferece, com previa e confirmacao explicita, atualizar as previsoes existentes a
--    partir de uma competencia escolhida. Ficam preservadas: as com recebimento na competencia (realizadas ou parciais),
--    as alteradas manualmente (valor definido pelo usuario - nova marca valor_manual, gravada por editar_receita -, data
--    prevista propria, zerada/removida, ou criada/anotada fora da geracao automatica). Cada atualizacao fica registrada
--    em financeiro.operacao_receita (antes e depois de cada previsao). Nenhum recebimento ou movimento muda.
-- 2. Total de receitas do mes: receitas_totais_do_mes, a mesma regra para a tela de Despesas (saldo do mes) e o
--    Dashboard: recebimento estornado nao conta; previsao parcialmente recebida conta o previsto (o resto ainda e
--    esperado); recebido acima do previsto conta o recebido; recebimento sem previsao conta uma vez; previsao de consorcio
--    conta como prevista e nao como recebida.
-- Nenhum dado existente muda nesta migration (a coluna nova nasce false).

alter table public.receita_orcamento add column valor_manual boolean not null default false;
comment on column public.receita_orcamento.valor_manual is
    'FIN-RECEITAS-SALDO-01: valor definido pelo usuario nesta previsao; a atualizacao pelo valor-base nao a altera.';

-- 1. Previsoes da fonte a partir da competencia: o que a atualizacao pelo valor-base muda e o que preserva (motivo).
create function financeiro.previsoes_para_atualizar(p_item_id integer, p_a_partir date)
    returns table (orcamento_id integer, competencia date, valor_atual numeric, valor_novo numeric, atualizar boolean, motivo text)
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with fonte as (select i.id, i.valor_base_mensal as base from public.item_receita i where i.id = p_item_id),
    previsoes as (
        select o.*, financeiro.recebido_da_previsao(o.id) as recebido,
               exists (select 1 from public.receita_realizada r
                        where r.orcamento_id = o.id
                           or (r.item_receita_id = o.item_receita_id
                               and date_trunc('month', r.mes_referencia::timestamp) = date_trunc('month', o.mes_referencia::timestamp))) as com_recebimento
          from public.receita_orcamento o
         where o.item_receita_id = p_item_id
           and o.mes_referencia >= date_trunc('month', p_a_partir::timestamp)::date
    ),
    classificadas as (
        select p.id, date_trunc('month', p.mes_referencia::timestamp)::date as comp, p.valor_esperado, f.base,
               case when p.recebido > 0 and p.recebido < p.valor_esperado then 'Parcialmente recebida'
                    when p.com_recebimento then 'Recebida (ha recebimento nesta competencia)'
                    when p.valor_manual then 'Valor alterado manualmente'
                    when p.data_prevista is not null then 'Data prevista definida manualmente'
                    when p.valor_esperado = 0 then 'Zerada ou removida manualmente'
                    when coalesce(p.observacoes, '') not like 'Gerado automaticamente%' then 'Criada ou anotada manualmente'
                    when p.valor_esperado = f.base then 'Ja no valor-base'
               end as motivo
          from previsoes p cross join fonte f
    )
    select c.id, c.comp, c.valor_esperado, c.base, c.motivo is null, c.motivo
      from classificadas c
     order by c.comp, c.id
$$;

-- 2. Previa (somente leitura): a fonte, as previsoes que mudam e as preservadas, para a tela pedir a confirmacao.
create function financeiro.previa_atualizacao_previsoes(p_perfil_id integer, p_item_id integer, p_a_partir date default null)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_item    public.item_receita;
    v_padrao  date := date_trunc('month', now() at time zone 'America/Sao_Paulo')::date;
    v_partir  date := coalesce(date_trunc('month', p_a_partir::timestamp)::date, date_trunc('month', now() at time zone 'America/Sao_Paulo')::date);
    v_motivo  text;
    v_r       jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_item from public.item_receita where id = p_item_id;
    if not found or not financeiro.pertence_ao_perfil(v_item.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Fonte de receita nao encontrada neste perfil' using errcode = '42501';
    end if;
    v_motivo := case when not financeiro.pode_gerir_perfil(p_perfil_id) then 'Perfil somente para leitura'
                     when financeiro.fonte_de_outro_modulo(p_item_id) then 'Fonte gerada pelo modulo de consorcios'
                     when not coalesce(v_item.ativo, true) then 'Fonte inativa'
                     when not coalesce(v_item.recorrente, false) then 'Fonte nao recorrente'
                     when coalesce(v_item.valor_base_mensal, 0) <= 0 then 'Fonte sem valor-base' end;
    select jsonb_build_object(
               'afetadas', coalesce(jsonb_agg(jsonb_build_object('orcamento_id', p.orcamento_id, 'competencia', p.competencia,
                                                                 'valor_atual', p.valor_atual, 'valor_novo', p.valor_novo)
                                              order by p.competencia) filter (where p.atualizar and v_motivo is null), '[]'::jsonb),
               'quantidade', count(*) filter (where p.atualizar and v_motivo is null),
               'diferenca_total', coalesce(sum(p.valor_novo - p.valor_atual) filter (where p.atualizar and v_motivo is null), 0),
               'preservadas', coalesce(jsonb_agg(jsonb_build_object('orcamento_id', p.orcamento_id, 'competencia', p.competencia,
                                                                    'valor', p.valor_atual, 'motivo', p.motivo)
                                                 order by p.competencia) filter (where not p.atualizar), '[]'::jsonb))
      into v_r
      from financeiro.previsoes_para_atualizar(p_item_id, v_partir) p;
    return v_r || jsonb_build_object(
        'item_receita_id', v_item.id, 'nome', v_item.nome, 'valor_base', v_item.valor_base_mensal, 'a_partir', v_partir,
        'a_partir_padrao', v_padrao, 'pode_atualizar', v_motivo is null, 'motivo', v_motivo,
        'versao', financeiro.versao_fonte(p_item_id));
end
$$;

-- 3. Atualizacao: so com a confirmacao da previa (versao da fonte e quantidade conferidas), numa transacao, auditada.
create function financeiro.atualizar_previsoes_fonte(p_perfil_id integer, p_item_id integer, p_versao text, p_a_partir date,
                                                     p_esperadas integer, p_chave uuid)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_receita;
    v_item     public.item_receita;
    v_partir   date := date_trunc('month', p_a_partir::timestamp)::date;
    v_alt      jsonb := '[]'::jsonb;
    v_pres     jsonb;
    v_p        record;
    v_r        jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    if v_partir is null then
        raise exception 'Informe a competencia inicial' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261224));
    select * into v_anterior from financeiro.operacao_receita o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'atualizar_previsoes_fonte' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    perform financeiro.travar_fonte(p_perfil_id, p_item_id, p_versao);  -- gestao, perfil, versao e trava da fonte
    select * into v_item from public.item_receita where id = p_item_id;
    if financeiro.fonte_de_outro_modulo(p_item_id) or not coalesce(v_item.ativo, true) or not coalesce(v_item.recorrente, false)
       or coalesce(v_item.valor_base_mensal, 0) <= 0 then
        raise exception 'Esta fonte nao tem previsoes a atualizar pelo valor-base' using errcode = '22023';
    end if;
    -- As previsoes (e um recebimento concorrente, que trava a previsao) esperam esta transacao.
    perform 1 from public.receita_orcamento o where o.item_receita_id = p_item_id and o.mes_referencia >= v_partir
       order by o.id for update;
    for v_p in select * from financeiro.previsoes_para_atualizar(p_item_id, v_partir) p where p.atualizar loop
        update public.receita_orcamento set valor_esperado = v_p.valor_novo where id = v_p.orcamento_id;
        v_alt := v_alt || jsonb_build_object('orcamento_id', v_p.orcamento_id, 'competencia', v_p.competencia,
                                             'antes', v_p.valor_atual, 'depois', v_p.valor_novo);
    end loop;
    if jsonb_array_length(v_alt) is distinct from p_esperadas then
        raise exception 'As previsoes mudaram desde a previa (% agora, % na previa). Nada foi alterado.',
            jsonb_array_length(v_alt), p_esperadas using errcode = 'P0001', hint = 'PREVIA_DESATUALIZADA';
    end if;
    select coalesce(jsonb_agg(jsonb_build_object('orcamento_id', p.orcamento_id, 'competencia', p.competencia, 'motivo', p.motivo)
                              order by p.competencia), '[]'::jsonb)
      into v_pres
      from financeiro.previsoes_para_atualizar(p_item_id, v_partir) p
     where not p.atualizar and p.motivo <> 'Ja no valor-base';
    v_r := jsonb_build_object('item_receita_id', p_item_id, 'nome', v_item.nome, 'valor_base', v_item.valor_base_mensal,
                              'a_partir', v_partir, 'atualizadas', jsonb_array_length(v_alt), 'alteracoes', v_alt,
                              'preservadas', v_pres);
    insert into financeiro.operacao_receita (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'atualizar_previsoes_fonte', v_r);
    return v_r;
end
$$;

-- 4. Total de receitas do mes (somente leitura), sobre as mesmas linhas de Receitas do mes (receitas_do_mes).
create function financeiro.receitas_totais_do_mes(p_perfil_id integer, p_mes date)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'previstas', coalesce(sum(case
            when r.origem = 'PREVISAO' and r.situacao = 'REMOVIDA' then 0
            when r.origem = 'PREVISAO' then greatest(coalesce(r.valor_previsto, 0), coalesce(r.valor_recebido, 0))
            when r.situacao = 'ESTORNADA' then 0
            when r.situacao = 'PREVISTA_CONSORCIO' then coalesce(r.valor_previsto, 0)
            else coalesce(r.valor_recebido, 0) end), 0),
        'recebidas', coalesce(sum(case when r.situacao in ('ESTORNADA', 'PREVISTA_CONSORCIO') then 0
                                       else coalesce(r.valor_recebido, 0) end), 0),
        'estornadas', coalesce(sum(r.valor_recebido) filter (where r.situacao = 'ESTORNADA'), 0))
      from financeiro.receitas_do_mes(p_perfil_id, p_mes) r
$$;

-- 5. Funcoes existentes (texto publicado; so as trocas deste pacote).

CREATE OR REPLACE FUNCTION financeiro.editar_receita(p_perfil_id integer, p_orcamento_id integer, p_versao text, p_dados jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_orc  public.receita_orcamento;
    v_item public.item_receita;
    v_d    jsonb;
    v_comp date;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.travar_previsao(p_perfil_id, p_orcamento_id, p_versao);
    select * into v_orc from public.receita_orcamento where id = p_orcamento_id;
    select * into v_item from public.item_receita where id = v_orc.item_receita_id;
    v_d := financeiro.ler_dados_receita(p_dados - 'nome' - 'tipo' - 'dia_previsto' - 'conta_bancaria_id' - 'descricao',
                                        p_perfil_id, true);
    v_comp := coalesce((v_d ->> 'competencia')::date, v_orc.mes_referencia);
    if v_comp <> v_orc.mes_referencia then
        if coalesce(v_item.recorrente, true) then
            raise exception 'A competencia de uma previsao recorrente nao muda' using errcode = '22023';
        end if;
        if exists (select 1 from public.receita_orcamento o where o.item_receita_id = v_item.id and o.mes_referencia = v_comp) then
            raise exception 'Ja existe previsao desta fonte nesta competencia' using errcode = '22023';
        end if;
    end if;
    -- A data prevista e so desta previsao: uma excecao nao desloca as demais competencias.
    perform financeiro.validar_data_prevista(v_comp, case when v_d ? 'data_prevista' then (v_d ->> 'data_prevista')::date
                                                          else v_orc.data_prevista end);
    update public.receita_orcamento o
       set valor_esperado = coalesce((v_d ->> 'valor')::numeric, o.valor_esperado),
           -- FIN-RECEITAS-SALDO-01: valor definido pelo usuario nesta previsao
           valor_manual = o.valor_manual or coalesce((v_d ->> 'valor')::numeric, o.valor_esperado) is distinct from o.valor_esperado,
           observacoes = case when v_d ? 'observacoes' then v_d ->> 'observacoes' else o.observacoes end,
           data_prevista = case when v_d ? 'data_prevista' then (v_d ->> 'data_prevista')::date else o.data_prevista end,
           mes_referencia = v_comp
     where o.id = p_orcamento_id;
    return jsonb_build_object('orcamento_id', p_orcamento_id, 'competencia', v_comp,
                              'versao', financeiro.versao_previsao(p_orcamento_id));
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.dashboard_resumo_tela(p_perfil_id integer, p_mes_referencia text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
    -- FIN-RECEITAS-SALDO-01: previstas e recebidas pela regra unica de receitas_totais_do_mes (a mesma da tela de
    -- Despesas): estorno nao conta; previsao parcialmente recebida conta o previsto; recebido acima do previsto conta o
    -- recebido; recebimento sem previsao conta uma vez.
    select (t ->> 'previstas')::numeric, (t ->> 'recebidas')::numeric
      into v_receitas, v_recebidas
      from financeiro.receitas_totais_do_mes(p_perfil_id, v_inicio) t;
    v_despesas := coalesce((select sum(c.valor) from public.conta c
                             where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', c.mes_referencia) = v_inicio and c.is_fatura_cartao is not true
                               and c.status_pagamento is distinct from 'Substituida'), 0)  -- FIN-MVP-MOB-01
                + coalesce((select sum(d.valor_previsto) from public.despesa_prevista d
                             where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', d.data_atual_prevista) = v_inicio
                               and d.status in ('PREVISTA', 'ADIADA')
                               and financeiro.prevista_financeira(d.origem_tipo, d.origem_id)), 0);  -- FIN-MVP-MOB-01

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
       and d.status in ('PREVISTA', 'ADIADA')
       and financeiro.prevista_financeira(d.origem_tipo, d.origem_id);  -- FIN-MVP-MOB-01
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
       and d.data_atual_prevista between v_inicio and v_fim
       and d.status <> 'SUPRIMIDA'
       and financeiro.prevista_financeira(d.origem_tipo, d.origem_id);  -- FIN-MVP-MOB-01

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
$function$;

revoke execute on function financeiro.previsoes_para_atualizar(integer, date) from public, anon, authenticated;
revoke execute on function financeiro.previa_atualizacao_previsoes(integer, integer, date) from public, anon;
revoke execute on function financeiro.atualizar_previsoes_fonte(integer, integer, text, date, integer, uuid) from public, anon;
revoke execute on function financeiro.receitas_totais_do_mes(integer, date) from public, anon;
grant execute on function financeiro.previa_atualizacao_previsoes(integer, integer, date) to authenticated;
grant execute on function financeiro.atualizar_previsoes_fonte(integer, integer, text, date, integer, uuid) to authenticated;
grant execute on function financeiro.receitas_totais_do_mes(integer, date) to authenticated;
