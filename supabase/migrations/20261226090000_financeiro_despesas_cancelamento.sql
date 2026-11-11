-- FIN-DESPESAS-CANCELAMENTO-01 (P23): cancelar uma ocorrencia de despesa cujo pagamento foi integralmente estornado.
-- Antes, a exclusao individual recusava a conta ("Possui movimento financeiro vinculado"): o pagamento e o estorno ficam
-- como movimentos da conta (e em pagamento_fatura), e apagar a conta romperia esse historico (movimento_financeiro.conta_id
-- sem cascata; pagamento_fatura com cascata). A obrigacao que deixou de existir (sessao desmarcada, por exemplo) ficava
-- pendente para sempre.
--
-- Cancelamento logico, pelo mecanismo que ja existe para conta preservada fora dos indicadores (a 'Substituida' da
-- Mobilidade, FIN-MVP-MOB-01): a conta fica com status_pagamento = 'Dispensada' e os vinculos de pagamento e estorno
-- continuam intactos. As leituras que ja deixam de fora a 'Substituida' (Despesas, Dashboard, despesas diretas, lastro de
-- saidas, lote, candidatas e vinculo de abastecimento) deixam de fora tambem a 'Dispensada'; o pagamento a recusa.
-- Na recorrencia, a competencia (ou a ocorrencia, na semanal) fica DISPENSADA como na exclusao (P22), agora com a conta
-- no registro: o gerador nao recria a ocorrencia. A recorrencia continua ativa; as outras ocorrencias nao mudam.
-- Elegivel so quando nao ha pagamento liquido ativo: cada pagamento (DEBITO 'DESPESA') tem o seu estorno integral
-- (CREDITO 'ESTORNO_DESPESA' com movimento_original_id), nenhum outro movimento e nenhum outro vinculo protegido.
-- Cada cancelamento fica tambem em financeiro.operacao_despesa (operacao 'cancelar_despesa': conta antes, pagamentos,
-- estornos e motivo). Retomada sobre a 20261224090000 e a 20261225090000 (contas_do_mes e dashboard_resumo_tela partem
-- do texto publicado por elas).
-- Nenhuma tabela ou coluna nova; nenhum dado existente muda nesta migration.

-- 1. Registro da dispensa de uma ocorrencia de recorrencia (o que dispensar_conta_recorrente ja gravava). p_manter_conta:
--    a conta continua existindo (cancelamento logico) e fica no registro.
create function financeiro.registrar_dispensa_recorrente(p_item public.item_despesa, p_conta public.conta, p_motivo text,
                                                         p_manter_conta boolean)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_ocorrencia date;  -- FIN-CATEGORIAS-RECORRENCIAS-2
    v_conta_id   integer := case when p_manter_conta then p_conta.id end;
begin
    if financeiro.semanas_da_recorrencia(p_item.tipo_recorrencia) is not null then
        -- Na semanal, dispensa so a ocorrencia desta conta (a gravada na geracao ou a do ciclo).
        v_ocorrencia := coalesce(
            (select o.data_ocorrencia from financeiro.recorrencia_ocorrencia o
              where o.item_despesa_id = p_item.id and o.conta_id = p_conta.id),
            financeiro.ocorrencia_semanal(p_item.tipo_recorrencia, p_item.data_vencimento, p_conta.data_vencimento));
        if v_ocorrencia is not null then
            insert into financeiro.recorrencia_ocorrencia (item_despesa_id, data_ocorrencia, situacao, conta_id, motivo, user_id)
            values (p_item.id, v_ocorrencia, 'DISPENSADA', v_conta_id, p_motivo, (select auth.uid()))
            on conflict (item_despesa_id, data_ocorrencia) do update
               set situacao = 'DISPENSADA', conta_id = excluded.conta_id, execucao_id = null,
                   motivo = excluded.motivo, user_id = excluded.user_id, registrado_em = now();
        end if;
    else
        insert into financeiro.recorrencia_competencia
            (item_despesa_id, natureza, competencia, situacao, conta_id, motivo, user_id)
        values (p_item.id, 'CONTA', date_trunc('month', p_conta.mes_referencia::timestamp)::date, 'DISPENSADA',
                v_conta_id, p_motivo, (select auth.uid()))
        on conflict (item_despesa_id, natureza, competencia) do update
           set situacao = 'DISPENSADA', conta_id = excluded.conta_id, lancamento_id = null, execucao_id = null,
               motivo = excluded.motivo, user_id = excluded.user_id, registrado_em = now();
    end if;
end
$$;

-- 2. Se a despesa pode ter a obrigacao cancelada (somente leitura). Matriz do contrato:
--    nunca paga -> exclusao comum (nao e este caminho); estornada integralmente -> elegivel; paga ou com valor pago
--    residual -> bloqueada; movimento fora do par pagamento/estorno -> bloqueada; ja cancelada -> idempotente;
--    outro vinculo financeiro (abastecimento, despesa prevista, regularizacao, parcela historica, troca de Mobilidade) ->
--    bloqueada com o motivo.
create function financeiro.situacao_cancelamento_despesa(p_conta_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_conta     public.conta;
    v_bloqueio  text;
    v_pago      numeric;
    v_estornado numeric;
    v_pags      jsonb;
    v_ests      jsonb;
    v_vinculo   text;
begin
    select * into v_conta from public.conta where id = p_conta_id;
    if not found then
        return jsonb_build_object('elegivel', false, 'motivo', 'Despesa inexistente');
    end if;
    if v_conta.status_pagamento = 'Dispensada' then
        return jsonb_build_object('elegivel', false, 'cancelada', true, 'motivo', 'Obrigacao ja cancelada');
    end if;
    -- Os bloqueios de modulo (cartao, consorcio, financiamento, outro modulo) vem antes dos de pagamento e movimento.
    v_bloqueio := financeiro.bloqueio_da_despesa(p_conta_id);
    if v_bloqueio is null then
        return jsonb_build_object('elegivel', false, 'exclusao', true, 'motivo', 'Sem pagamento estornado: use Excluir');
    end if;
    if v_bloqueio not in ('Despesa paga: correcao so por estorno', 'Possui movimento financeiro vinculado') then
        return jsonb_build_object('elegivel', false, 'motivo', v_bloqueio);
    end if;
    if v_conta.status_pagamento = 'Pago' or v_conta.data_pagamento is not null then
        return jsonb_build_object('elegivel', false, 'motivo', 'Pagamento ainda valido: estorne antes de cancelar');
    end if;
    v_vinculo := case
        when exists (select 1 from financeiro.abastecimento a where a.conta_id = p_conta_id) then 'abastecimento'
        when exists (select 1 from public.despesa_prevista d where d.conta_id = p_conta_id) then 'despesa prevista'
        when exists (select 1 from financeiro.regularizacao_historica r where r.conta_id = p_conta_id) then 'regularizacao historica'
        when exists (select 1 from financeiro.parcela_historica h where h.conta_id = p_conta_id) then 'parcela historica'
        when exists (select 1 from financeiro.mobilidade_troca_decisao t where t.conta_id = p_conta_id) then 'troca de Mobilidade'
    end;
    if v_vinculo is not null then
        return jsonb_build_object('elegivel', false, 'motivo', 'Protegida por outro vinculo financeiro: ' || v_vinculo);
    end if;
    -- Pagamento liquido: cada DEBITO 'DESPESA' menos o CREDITO 'ESTORNO_DESPESA' que o estorna.
    select coalesce(sum(m.valor) filter (where m.tipo = 'DEBITO' and m.origem = 'DESPESA'), 0),
           coalesce(sum(m.valor) filter (where m.tipo = 'CREDITO' and m.origem = 'ESTORNO_DESPESA'), 0),
           coalesce(jsonb_agg(m.id order by m.id) filter (where m.tipo = 'DEBITO' and m.origem = 'DESPESA'), '[]'::jsonb),
           coalesce(jsonb_agg(m.id order by m.id) filter (where m.tipo = 'CREDITO' and m.origem = 'ESTORNO_DESPESA'), '[]'::jsonb)
      into v_pago, v_estornado, v_pags, v_ests
      from public.movimento_financeiro m
     where m.conta_id = p_conta_id;
    if v_pago > v_estornado then
        return jsonb_build_object('elegivel', false, 'motivo', 'Pagamento parcialmente estornado: ha valor pago residual',
                                  'valor_residual', v_pago - v_estornado);
    end if;
    -- Conciliado: so o par pagamento/estorno, cada estorno integral, do mesmo banco, ligado ao seu pagamento (e o
    -- registro do pagamento com o estorno gravado); nenhum movimento como fatura desta conta.
    if exists (select 1 from public.movimento_financeiro m where m.fatura_id = p_conta_id)
       or exists (select 1 from public.movimento_financeiro m
                   where m.conta_id = p_conta_id
                     and not (m.tipo = 'DEBITO' and m.origem = 'DESPESA')
                     and not (m.tipo = 'CREDITO' and m.origem = 'ESTORNO_DESPESA'))
       or exists (select 1 from public.movimento_financeiro d
                   where d.conta_id = p_conta_id and d.tipo = 'DEBITO' and d.origem = 'DESPESA'
                     and (select count(*) from public.movimento_financeiro e
                           where e.movimento_original_id = d.id and e.conta_id = p_conta_id and e.tipo = 'CREDITO'
                             and e.origem = 'ESTORNO_DESPESA' and e.valor = d.valor
                             and e.conta_bancaria_id is not distinct from d.conta_bancaria_id) <> 1)
       or exists (select 1 from public.movimento_financeiro e
                   where e.conta_id = p_conta_id and e.tipo = 'CREDITO' and e.origem = 'ESTORNO_DESPESA'
                     and not exists (select 1 from public.movimento_financeiro d
                                      where d.id = e.movimento_original_id and d.conta_id = p_conta_id
                                        and d.tipo = 'DEBITO' and d.origem = 'DESPESA'))
       or exists (select 1 from financeiro.pagamento_fatura p
                   where p.fatura_id = p_conta_id
                     and (p.estorno_movimento_id is null
                          or not exists (select 1 from public.movimento_financeiro e
                                          where e.id = p.estorno_movimento_id and e.movimento_original_id = p.movimento_id))) then
        return jsonb_build_object('elegivel', false, 'motivo', 'Movimento financeiro nao conciliado com o pagamento e o estorno');
    end if;
    return jsonb_build_object('elegivel', true, 'pagamentos', v_pags, 'estornos', v_ests,
                              'valor_pago', v_pago, 'valor_estornado', v_estornado);
end
$$;

-- 3. Previa do cancelamento (somente leitura): o que a tela mostra antes de oferecer "Cancelar obrigacao".
create function financeiro.previa_cancelamento_despesa(p_perfil_id integer, p_conta_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta;
    v_item  public.item_despesa;
    v_r     jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_conta from public.conta where id = p_conta_id;
    if not found or coalesce(v_conta.is_fatura_cartao, false)
       or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Despesa nao encontrada neste perfil' using errcode = '42501';
    end if;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id;
    v_r := financeiro.situacao_cancelamento_despesa(p_conta_id);
    if (v_r ->> 'elegivel')::boolean then
        if not financeiro.pode_gerir_perfil(p_perfil_id) then
            v_r := jsonb_build_object('elegivel', false, 'motivo', 'Perfil somente para leitura');
        elsif financeiro.gerador_do_perfil(p_perfil_id) <> 'NOVO' then
            v_r := jsonb_build_object('elegivel', false, 'motivo', 'Perfil ainda gravado pelo sistema anterior');
        end if;
    end if;
    return v_r || jsonb_build_object(
        'conta_id', v_conta.id, 'descricao', v_conta.descricao, 'valor', v_conta.valor,
        'competencia', date_trunc('month', v_conta.mes_referencia::timestamp)::date, 'data_vencimento', v_conta.data_vencimento,
        'recorrente', coalesce(v_item.recorrente, false), 'versao', financeiro.versao_despesa(p_conta_id));
end
$$;

-- 4. Cancelamento: a conta fica 'Dispensada' (fora das pendencias), o historico fica; na recorrencia, a ocorrencia fica
--    DISPENSADA com a conta no registro. Mesma ordem de travas da exclusao (conta, recorrencia, trava da geracao): um
--    pagamento ou estorno concorrente espera a conta e, depois, encontra a obrigacao cancelada. Repetir nao muda nada.
create function financeiro.cancelar_despesa(p_perfil_id integer, p_conta_id integer, p_versao text)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_conta    public.conta;
    v_item     public.item_despesa;
    v_situacao jsonb;
    v_motivo   text;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_conta from public.conta where id = p_conta_id for update;
    if not found or coalesce(v_conta.is_fatura_cartao, false)
       or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Despesa nao encontrada neste perfil' using errcode = '42501';
    end if;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id for update;
    if v_conta.status_pagamento = 'Dispensada' then
        return jsonb_build_object('conta_id', p_conta_id, 'cancelada', true, 'repetida', true);
    end if;
    if p_versao is null or p_versao is distinct from financeiro.versao_despesa(p_conta_id) then
        raise exception 'A despesa foi alterada por outra operacao. Recarregue e tente de novo.'
            using errcode = 'P0001', hint = 'VERSAO';
    end if;
    if coalesce(v_item.recorrente, false) then
        if financeiro.gerador_do_perfil(p_perfil_id) <> 'NOVO' then
            raise exception 'Conta recorrente gerada pelo sistema atual: o Flask a recriaria. Exclua pelo sistema atual.'
                using errcode = 'P0001', hint = 'GERADOR_FLASK';
        end if;
        perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao
    end if;
    v_situacao := financeiro.situacao_cancelamento_despesa(p_conta_id);
    if not coalesce((v_situacao ->> 'elegivel')::boolean, false) then
        raise exception 'Operacao bloqueada: %', v_situacao ->> 'motivo' using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    v_motivo := format('Obrigacao cancelada pelo usuario: conta %s, R$ %s, vencimento %s; pagamento estornado (movimentos %s, estornos %s)',
                       v_conta.id, to_char(v_conta.valor, 'FM999999990.00'), to_char(v_conta.data_vencimento, 'DD/MM/YYYY'),
                       v_situacao -> 'pagamentos', v_situacao -> 'estornos');
    update public.conta set status_pagamento = 'Dispensada' where id = p_conta_id;
    if coalesce(v_item.recorrente, false) then
        perform financeiro.registrar_dispensa_recorrente(v_item, v_conta, v_motivo, true);
    end if;
    -- Trilha de auditoria: o estado anterior da conta, os pagamentos e estornos preservados e o motivo.
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (gen_random_uuid(), (select auth.uid()), p_perfil_id, 'cancelar_despesa',
            jsonb_build_object('conta_id', p_conta_id, 'conta_antes', to_jsonb(v_conta), 'item_despesa_id', v_item.id,
                               'recorrente', coalesce(v_item.recorrente, false), 'pagamentos', v_situacao -> 'pagamentos',
                               'estornos', v_situacao -> 'estornos', 'motivo', v_motivo));
    return jsonb_build_object('conta_id', p_conta_id, 'cancelada', true, 'valor', v_conta.valor,
                              'competencia', date_trunc('month', v_conta.mes_referencia::timestamp)::date,
                              'data_vencimento', v_conta.data_vencimento, 'pagamentos', v_situacao -> 'pagamentos',
                              'estornos', v_situacao -> 'estornos', 'competencia_dispensada', coalesce(v_item.recorrente, false));
end
$$;

-- 5. Funcoes existentes (texto publicado; so as trocas da P23).

CREATE OR REPLACE FUNCTION financeiro.dispensar_conta_recorrente(p_item item_despesa, p_conta conta, p_motivo text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    -- FIN-DESPESAS-CANCELAMENTO-01 (P23): o registro da dispensa fica em registrar_dispensa_recorrente (igual ao anterior).
    perform financeiro.registrar_dispensa_recorrente(p_item, p_conta, p_motivo, false);
    delete from public.conta where id = p_conta.id;
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.bloqueio_do_pagamento(p_conta_id integer)
 RETURNS text
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_conta public.conta;
    v_item  public.item_despesa;
begin
    select * into v_conta from public.conta where id = p_conta_id;
    if not found then
        return 'Despesa inexistente';
    end if;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id;
    if coalesce(v_conta.is_fatura_cartao, false) then
        return 'Fatura de cartao: pague na tela de cartoes';
    end if;
    if v_conta.status_pagamento = 'Substituida' then  -- FIN-MVP-MOB-01
        return 'Despesa substituida na troca de modalidade de Mobilidade';
    end if;
    if v_conta.status_pagamento = 'Dispensada' then  -- FIN-DESPESAS-CANCELAMENTO-01 (P23)
        return 'Obrigacao cancelada: nada a pagar';
    end if;
    -- FIN-CONTRATOS-2: parcelas de consorcio (despesa comum do item 'Consorcio') e de financiamento (sincronizada pela
    -- financeiro.sincronizar_parcela_paga) sao pagas aqui, pelo escritor unico do perfil.
    return null;
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.contas_do_mes(p_perfil_id integer, p_mes date)
 RETURNS TABLE(id integer, grupo text, nome text, valor numeric, valor_previsto numeric, valor_executado numeric, data_vencimento date, data_pagamento date, situacao text, status_pagamento text, categoria_nome text, categoria_cor text, cartao_id integer, cartao_nome text, numero_parcela integer, total_parcelas integer, debito_automatico boolean)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_mes date;
    v_hoje date := (now() at time zone 'America/Sao_Paulo')::date;
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null then
        raise exception 'Mes de competencia obrigatorio' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes)::date;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');

    return query
    with contas as (
        select c.*
          from public.conta c
         where (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal))
           and c.status_pagamento is distinct from 'Substituida' and c.status_pagamento is distinct from 'Dispensada'  -- FIN-MVP-MOB-01: preservada, fora das despesas do mes
           and (
                (coalesce(c.is_fatura_cartao, false) = false and date_trunc('month', c.mes_referencia) = v_mes)
             or (c.is_fatura_cartao = true and date_trunc('month', c.cartao_competencia) = v_mes)
           )
    ),
    gastos as (
        -- gasto do mes por cartao e categoria de cartao, no perfil (mes_fatura = 1o dia, como no Flask)
        -- FIN-CARTOES-EXECUTADO-01: total = executado (a previsao fixa sem cobranca ja entra pelo valor previsto)
        select l.cartao_id, l.categoria_cartao_id, sum(financeiro.valor_executado_compra(l.valor, sit.s)) as total,
               sum(l.valor) filter (where sit.s = 'PREVISTA') as pendente,
               -- FIN-CARTAO-DESPESAS-FIXAS-01: parceladas e fixas nao consomem o limite da Categoria do Cartao
               sum(l.valor) filter (where financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) = 'CATEGORIA') as total_categoria
          from public.lancamento_agregado l
         cross join lateral (select financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id), l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
         where (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
           and l.mes_fatura = v_mes
         group by l.cartao_id, l.categoria_cartao_id
    ),
    faturas as (
        select c.id,
               -- FIN-CARTAO-NUBANK-CREDITOS-01: executado das compras menos os creditos da fatura (valor a pagar)
               coalesce((select sum(g.total) from gastos g where g.cartao_id = c.item_despesa_id), 0)
                   - financeiro.creditos_fatura(c.id) as executado,
               coalesce((select sum(g.pendente) from gastos g where g.cartao_id = c.item_despesa_id), 0) as pendente,
               coalesce((select sum(greatest(lim.limite_mensal - coalesce(g.total_categoria, 0), 0))
                           from public.cartao_categoria_limite lim
                           left join gastos g
                             on g.cartao_id = lim.cartao_id and g.categoria_cartao_id = lim.categoria_cartao_id
                          where lim.cartao_id = c.item_despesa_id and lim.ativo), 0) as complemento
          from contas c
         where c.is_fatura_cartao = true
    )
    select c.id,
           case when c.is_fatura_cartao then 'FATURA' else 'DESPESA' end,
           c.descricao::text,
           case
               when not coalesce(c.is_fatura_cartao, false) then c.valor
               when c.status_pagamento = 'Pago' then f.executado
               else f.executado + f.complemento
           end,
           case when c.is_fatura_cartao then f.executado + f.complemento end,
           case when c.is_fatura_cartao then f.executado end,
           c.data_vencimento,
           c.data_pagamento,
           case
               when c.status_pagamento = 'Pago' then 'PAGA'
               when c.status_pagamento = 'Atrasado' or c.data_vencimento < v_hoje then 'VENCIDA'
               else 'PENDENTE'
           end,
           coalesce(c.status_pagamento, 'Pendente')::text,
           cat.nome::text,
           cat.cor::text,
           case when c.is_fatura_cartao then c.item_despesa_id end,
           case when c.is_fatura_cartao then item.nome::text end,
           c.numero_parcela,
           c.total_parcelas,
           coalesce(c.debito_automatico, false)
      from contas c
      left join faturas f on f.id = c.id
      left join public.item_despesa item on item.id = c.item_despesa_id
      left join public.categoria cat on cat.id = item.categoria_id
     order by 2, c.data_vencimento, c.descricao, c.id;
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
                               and c.status_pagamento is distinct from 'Substituida' and c.status_pagamento is distinct from 'Dispensada'), 0)  -- FIN-MVP-MOB-01
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

    -- _total_faturas_periodo (FIN-CARTOES-EXECUTADO-01: o mesmo valor da fatura em Despesas, previsto_fatura)
    select coalesce(sum(financeiro.previsto_fatura(c.id)), 0),
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
               'origem', case when x.is_fatura_cartao then 'Fatura' else 'Conta' end, 'valor', round(coalesce(x.valor, 0), 2),  -- FIN-CARTOES-EXECUTADO-01
               'tipo', case when x.is_fatura_cartao then 'fatura' else 'despesa' end,
               'status_visual', case when x.data_vencimento = v_hoje then 'vence_hoje' else (x.data_vencimento - v_hoje) || ' dias' end)
           order by x.data_vencimento, x.id), '[]'::jsonb),
           coalesce(sum(coalesce(x.valor, 0)), 0),
           count(*) filter (where x.data_vencimento = v_hoje)
      into v_venc, v_venc_total, v_venc_hoje
      from (select c.id, c.data_vencimento, c.descricao, c.is_fatura_cartao,
                   case when c.is_fatura_cartao then financeiro.previsto_fatura(c.id) else c.valor end as valor  -- fatura: como em Despesas
              from public.conta c
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

CREATE OR REPLACE FUNCTION financeiro.despesas_diretas_tela(p_perfil_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return coalesce((
        select jsonb_agg(jsonb_build_object(
                   'id', c.id, 'nome', c.descricao, 'descricao', coalesce(c.observacoes, ''),
                   'tipo', coalesce(i.tipo, 'Simples'), 'valor', c.valor, 'conta_bancaria_id', c.conta_bancaria_id,
                   'financiamento_parcela_id', c.financiamento_parcela_id, 'categoria_id', cat.id,
                   'categoria', case when cat.id is null then null else jsonb_build_object(
                       'id', cat.id, 'nome', cat.nome, 'cor', to_jsonb(cat) -> 'cor', 'icone', to_jsonb(cat) -> 'icone',
                       'logo_url', to_jsonb(cat) -> 'logo_url') end,
                   'data_vencimento', c.data_vencimento, 'data_pagamento', c.data_pagamento,
                   'pago', c.status_pagamento = 'Pago', 'status_pagamento', c.status_pagamento,
                   'mes_competencia', to_char(c.mes_referencia, 'YYYY-MM'), 'recorrente', coalesce(i.recorrente, false),
                   'tipo_recorrencia', i.tipo_recorrencia,
                   'meio_pagamento', case when i.id is not null then i.meio_pagamento
                                          when c.debito_automatico then 'debito' end,
                   'debito_automatico', c.debito_automatico, 'numero_parcela', c.numero_parcela,
                   'total_parcelas', c.total_parcelas, 'agrupado', false, 'ativo', true, 'is_fatura_cartao', false)
                 order by c.data_vencimento desc, c.id desc)
          from public.conta c
          left join public.item_despesa i on i.id = c.item_despesa_id
          left join public.categoria cat on cat.id = i.categoria_id
         where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
           and not coalesce(c.is_fatura_cartao, false)
           and c.status_pagamento is distinct from 'Substituida' and c.status_pagamento is distinct from 'Dispensada'), '[]'::jsonb);  -- FIN-MVP-MOB-01
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.saidas_lastro(p_perfil_id integer, p_f jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
               and financeiro.prevista_financeira(d.origem_tipo, d.origem_id)  -- FIN-MVP-MOB-01
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
               and c.status_pagamento is distinct from 'Substituida' and c.status_pagamento is distinct from 'Dispensada'  -- FIN-MVP-MOB-01
            union all
            select 'LANCAMENTO', la.id, la.data_compra, la.descricao, la.valor, 'Lancamento no cartao', cat.nome, 'CARTAO'
              from public.lancamento_agregado la left join public.categoria cat on cat.id = la.categoria_id
             where la.perfil_financeiro_id = p_perfil_id and la.valor > 0 and la.data_compra >= v_ini and la.data_compra < v_fim
               and not financeiro.mob_compra_substituida(la.id)  -- FIN-MVP-MOB-01
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
$function$;

CREATE OR REPLACE FUNCTION financeiro.pagar_despesas_lote(p_perfil_id integer, p_dados jsonb, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_anterior  financeiro.operacao_despesa;
    v_itens     jsonb;
    v_banco     integer;
    v_data      date;
    v_ids       integer[];
    v_achadas   integer;
    v_recs      integer[];
    v_comps     date[];
    v_pendentes integer[];
    v_item      jsonb;
    v_conta     public.conta;
    v_r         jsonb;
    v_pagas     jsonb := '[]'::jsonb;
    v_total     numeric := 0;
    v_estado    text;
    v_msg       text;
    v_hint      text;
    v_resultado jsonb;
    v_ident     jsonb;
    v_ident_recs integer[];
    v_soma      numeric;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- quem gere o perfil e perfil no novo aplicativo (escritor unico)
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261101));
    select * into v_anterior from financeiro.operacao_despesa o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'pagar_despesas_lote' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;

    -- Dados: as ocorrencias com o valor que a tela mostrou, a conta e a data
    v_itens := case when jsonb_typeof(p_dados -> 'itens') = 'array' then p_dados -> 'itens' end;
    if v_itens is null or jsonb_array_length(v_itens) = 0 then
        raise exception 'Nenhuma ocorrência pendente para pagar' using errcode = '22023';
    end if;
    if jsonb_array_length(v_itens) > 60 then
        raise exception 'Lote com mais de 60 ocorrências' using errcode = '22023';
    end if;
    if exists (select 1 from jsonb_array_elements(v_itens) e
                where jsonb_typeof(e) <> 'object' or coalesce(e ->> 'conta_id', '') !~ '^\d+$'
                   or coalesce(e ->> 'valor_devido', '') !~ '^\d+(\.\d{1,2})?$') then
        raise exception 'Dados do lote inválidos' using errcode = '22023';
    end if;
    v_ids := array(select distinct (e ->> 'conta_id')::integer from jsonb_array_elements(v_itens) e order by 1);
    if cardinality(v_ids) <> jsonb_array_length(v_itens) then
        raise exception 'Ocorrência repetida no lote' using errcode = '22023';
    end if;
    -- Identidade do lote que o modal mostrou (P21): obrigatoria
    v_ident := p_dados -> 'lote';
    if jsonb_typeof(v_ident) is distinct from 'object' or btrim(coalesce(v_ident ->> 'descricao', '')) = ''
       or coalesce(v_ident ->> 'competencia', '') !~ '^\d{4}-(0[1-9]|1[0-2])$'
       or jsonb_typeof(v_ident -> 'recorrencias') is distinct from 'array' or (v_ident -> 'recorrencias') = '[]'::jsonb
       or exists (select 1 from jsonb_array_elements(case when jsonb_typeof(v_ident -> 'recorrencias') = 'array'
                                                          then v_ident -> 'recorrencias' else '[]'::jsonb end) e
                   where jsonb_typeof(e) <> 'number' or e::text !~ '^\d{1,9}$')
       or coalesce(v_ident ->> 'quantidade', '') !~ '^\d{1,9}$' or coalesce(v_ident ->> 'valor_total', '') !~ '^\d+(\.\d{1,2})?$' then
        raise exception 'O pedido não identifica o lote mostrado na tela. Atualize a página e abra o lote de novo. Nada foi pago.'
            using errcode = '22023', hint = 'LOTE_IDENTIDADE';
    end if;
    begin
        v_data := (p_dados ->> 'data_pagamento')::date;
    exception when others then
        v_data := null;
    end;
    if v_data is null then
        raise exception 'Informe a data do pagamento' using errcode = '22023';
    end if;
    if coalesce(p_dados ->> 'conta_bancaria_id', '') !~ '^\d+$' then
        raise exception 'Selecione a conta bancária de débito' using errcode = '22023', hint = 'CONTA_OBRIGATORIA';
    end if;
    v_banco := (p_dados ->> 'conta_bancaria_id')::integer;
    -- a conta e conferida antes de qualquer pagamento (ativa e do perfil)
    perform financeiro.travar_conta_bancaria(p_perfil_id, v_banco);

    -- O lote que a tela mostrou tem de ser o de agora: mesmas recorrencias e competencia, mesmas ocorrencias pendentes
    select count(*), array_agg(distinct c.item_despesa_id), array_agg(distinct date_trunc('month', c.mes_referencia)::date)
      into v_achadas, v_recs, v_comps
      from public.conta c
     where c.id = any(v_ids) and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
       and not coalesce(c.is_fatura_cartao, false) and c.item_despesa_id is not null;
    if v_achadas <> cardinality(v_ids) then
        raise exception 'Ocorrência não encontrada neste perfil' using errcode = '42501';
    end if;
    if cardinality(v_comps) <> 1 then
        raise exception 'O pagamento em lote é de uma competência por vez' using errcode = '22023';
    end if;
    -- As ocorrencias tem de ser exatamente o lote mostrado: mesma recorrencia (nome e itens), competencia, quantidade e total
    v_ident_recs := array(select distinct e::text::integer from jsonb_array_elements(v_ident -> 'recorrencias') e order by 1);
    v_soma := (select sum((e ->> 'valor_devido')::numeric) from jsonb_array_elements(v_itens) e);
    if v_ident_recs is distinct from array(select x from unnest(v_recs) x order by 1)
       or (v_ident ->> 'competencia' || '-01')::date <> v_comps[1]
       or (v_ident ->> 'quantidade')::integer <> cardinality(v_ids)
       or (v_ident ->> 'valor_total')::numeric <> v_soma
       or exists (select 1 from public.conta c where c.id = any(v_ids)
                   and btrim(regexp_replace(c.descricao, '\s*-\s*\d{2}/\d{2}$', '')) <> btrim(v_ident ->> 'descricao')) then
        raise exception 'As ocorrências enviadas não são as do lote mostrado (%, %). Nada foi pago.',
            btrim(v_ident ->> 'descricao'), to_char((v_ident ->> 'competencia' || '-01')::date, 'MM/YYYY')
            using errcode = '22023', hint = 'LOTE_IDENTIDADE';
    end if;
    v_pendentes := array(select c.id from public.conta c
                          where c.item_despesa_id = any(v_recs) and date_trunc('month', c.mes_referencia)::date = v_comps[1]
                            and not coalesce(c.is_fatura_cartao, false)
                            and c.status_pagamento is distinct from 'Pago' and c.status_pagamento is distinct from 'Substituida' and c.status_pagamento is distinct from 'Dispensada'
                            and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                          order by c.id);
    if v_pendentes is distinct from v_ids then
        raise exception 'As ocorrências pendentes mudaram desde a abertura (agora são %). Confira de novo. Nada foi pago.',
            cardinality(v_pendentes) using errcode = '22023', hint = 'LOTE_DESATUALIZADO';
    end if;

    -- Cada ocorrencia pelo pagamento individual, com a mesma conta; qualquer recusa desfaz o lote inteiro
    for v_item in select e from jsonb_array_elements(v_itens) e order by (e ->> 'conta_id')::integer loop
        select * into v_conta from public.conta c where c.id = (v_item ->> 'conta_id')::integer;
        begin
            v_r := financeiro.pagar_despesa(p_perfil_id, v_conta.id,
                jsonb_build_object('conta_bancaria_id', v_banco, 'data_pagamento', v_data,
                                   'valor_pago', v_item ->> 'valor_devido', 'valor_devido', v_item ->> 'valor_devido'),
                extensions.uuid_generate_v5(p_chave, v_conta.id::text));
        exception when others then
            get stacked diagnostics v_estado = returned_sqlstate, v_msg = message_text, v_hint = pg_exception_hint;
            raise exception 'Nenhuma ocorrência foi paga. "%" (vencimento %): %', v_conta.descricao,
                to_char(v_conta.data_vencimento, 'DD/MM/YYYY'), v_msg
                using errcode = v_estado, hint = coalesce(nullif(v_hint, ''), 'LOTE_RECUSADO');
        end;
        v_pagas := v_pagas || jsonb_build_object('conta_id', v_conta.id, 'descricao', v_conta.descricao,
                                                 'data_vencimento', v_conta.data_vencimento, 'valor_pago', (v_r ->> 'valor_pago')::numeric,
                                                 'movimento_id', (v_r ->> 'movimento_id')::integer);
        v_total := v_total + (v_r ->> 'valor_pago')::numeric;
    end loop;

    v_resultado := jsonb_build_object('pagas', jsonb_array_length(v_pagas), 'valor_total', v_total, 'data_pagamento', v_data,
                                      'conta_bancaria_id', v_banco, 'conta_nome', v_r ->> 'conta_nome',
                                      'saldo_conta', (v_r ->> 'saldo_conta')::numeric, 'ocorrencias', v_pagas);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'pagar_despesas_lote', v_resultado);
    return v_resultado;
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.candidatas_abastecimento(p_perfil_id integer, p_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    a       financeiro.abastecimento;
    v_lista jsonb;
    v_nome  text;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into a from financeiro.abastecimento x where x.id = p_id;
    if not found or not financeiro.pertence_ao_perfil(a.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Abastecimento não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    v_nome := nullif(upper(btrim(coalesce(a.estabelecimento, ''))), '');
    select coalesce(jsonb_agg(y.c order by (y.c ->> 'mesmo_cartao_fisico')::boolean desc, (y.c ->> 'estabelecimento_confere')::boolean desc,
                              abs((y.c ->> 'dias')::integer), y.c ->> 'natureza', (y.c ->> 'id')::integer), '[]'::jsonb)
      into v_lista
      from (select jsonb_build_object('natureza', 'COMPRA', 'id', l.id, 'descricao', l.descricao, 'data', l.data_compra, 'valor', l.valor,
                       'cartao_id', l.cartao_id, 'dias', l.data_compra - a.data_abastecimento,
                       'mesmo_cartao_fisico', a.cartao_vinculado_id is not null and l.cartao_vinculado_id is not distinct from a.cartao_vinculado_id,
                       'estabelecimento_confere', v_nome is not null and position(v_nome in upper(coalesce(l.descricao, ''))) > 0) as c
              from public.lancamento_agregado l
             where financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id) and l.valor = a.valor_total
               and l.data_compra between a.data_abastecimento - 3 and a.data_abastecimento + 10
               and coalesce(a.meio_pagamento, 'cartao') = 'cartao'
               and (a.cartao_id is null or l.cartao_id = a.cartao_id)
               and (a.cartao_vinculado_id is null or l.cartao_vinculado_id is null or l.cartao_vinculado_id = a.cartao_vinculado_id)
               and not exists (select 1 from financeiro.abastecimento x where x.lancamento_id = l.id and x.id <> a.id)
            union all
            select jsonb_build_object('natureza', 'CONTA', 'id', k.id, 'descricao', k.descricao, 'data', k.data_vencimento, 'valor', k.valor,
                       'cartao_id', null, 'dias', k.data_vencimento - a.data_abastecimento, 'mesmo_cartao_fisico', false,
                       'estabelecimento_confere', v_nome is not null and position(v_nome in upper(coalesce(k.descricao, ''))) > 0)
              from public.conta k
             where financeiro.pertence_ao_perfil(k.perfil_financeiro_id, p_perfil_id) and k.valor = a.valor_total
               and not coalesce(k.is_fatura_cartao, false) and k.status_pagamento is distinct from 'Substituida' and k.status_pagamento is distinct from 'Dispensada'
               and k.data_vencimento between a.data_abastecimento - 3 and a.data_abastecimento + 10
               and coalesce(a.meio_pagamento, '') <> 'cartao'
               and not exists (select 1 from financeiro.abastecimento x where x.conta_id = k.id and x.id <> a.id)) y;
    return jsonb_build_object('candidatas', v_lista, 'ambigua', jsonb_array_length(v_lista) > 1);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.vincular_abastecimento(p_perfil_id integer, p_id integer, p_dados jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    a       financeiro.abastecimento;
    n       financeiro.abastecimento;
    v_lanc  integer := nullif(financeiro.mob_inteiro(p_dados -> 'lancamento_id'), 0);
    v_conta integer := nullif(financeiro.mob_inteiro(p_dados -> 'conta_id'), 0);
    v_l     public.lancamento_agregado;
    v_c     public.conta;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    a := financeiro.mob_abastecimento(p_perfil_id, p_id);
    if a.anulado_em is not null then
        raise exception 'Abastecimento anulado não pode ser vinculado' using errcode = '22023';
    end if;
    if (v_lanc is null) = (v_conta is null) then
        raise exception 'Informe a compra ou a conta correspondente' using errcode = '22023';
    end if;
    if a.lancamento_id is not null or a.conta_id is not null then
        raise exception 'Abastecimento já vinculado. Desvincule antes de trocar.' using errcode = '22023', hint = 'ABASTECIMENTO_VINCULADO';
    end if;
    if v_lanc is not null then
        select * into v_l from public.lancamento_agregado l
         where l.id = v_lanc and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id) for share;
        if not found then
            raise exception 'Compra não encontrada neste perfil' using errcode = '22023';
        end if;
        if v_l.valor <> a.valor_total then
            raise exception 'O valor da compra é diferente do abastecimento. Nada foi gravado.' using errcode = '22023', hint = 'VALOR_DIVERGENTE';
        end if;
        if a.cartao_id is not null and v_l.cartao_id is distinct from a.cartao_id then
            raise exception 'A compra é de outro cartão. Nada foi gravado.' using errcode = '22023', hint = 'CARTAO_DIVERGENTE';
        end if;
        if a.cartao_vinculado_id is not null and v_l.cartao_vinculado_id is not null and v_l.cartao_vinculado_id <> a.cartao_vinculado_id then
            raise exception 'A compra é de outro cartão físico. Nada foi gravado.' using errcode = '22023', hint = 'CARTAO_DIVERGENTE';
        end if;
        if exists (select 1 from financeiro.abastecimento x where x.lancamento_id = v_lanc) then
            raise exception 'Esta compra já pertence a outro abastecimento. Nada foi gravado.' using errcode = '22023', hint = 'DESPESA_JA_VINCULADA';
        end if;
    else
        select * into v_c from public.conta c
         where c.id = v_conta and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and not coalesce(c.is_fatura_cartao, false)
           and c.status_pagamento is distinct from 'Substituida' and c.status_pagamento is distinct from 'Dispensada' for share;
        if not found then
            raise exception 'Conta não encontrada neste perfil' using errcode = '22023';
        end if;
        if v_c.valor <> a.valor_total then
            raise exception 'O valor da conta é diferente do abastecimento. Nada foi gravado.' using errcode = '22023', hint = 'VALOR_DIVERGENTE';
        end if;
        if exists (select 1 from financeiro.abastecimento x where x.conta_id = v_conta) then
            raise exception 'Esta conta já pertence a outro abastecimento. Nada foi gravado.' using errcode = '22023', hint = 'DESPESA_JA_VINCULADA';
        end if;
    end if;
    update financeiro.abastecimento x set lancamento_id = v_lanc, conta_id = v_conta, atualizado_em = now()
     where x.id = a.id
    returning * into n;
    insert into financeiro.abastecimento_historico (abastecimento_id, acao, antes, depois, user_id)
    values (a.id, 'VINCULO', to_jsonb(a), to_jsonb(n), (select auth.uid()));
    return jsonb_build_object('abastecimento', financeiro.mob_abastecimento_flask(n));
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.salvar_lancamento_abastecimento(p_perfil_id integer, p_dados jsonb, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_rep    jsonb;
    v_l      jsonb := case when jsonb_typeof(p_dados -> 'lancamento') = 'object' then p_dados -> 'lancamento' end;
    v_a      jsonb := case when jsonb_typeof(p_dados -> 'abastecimento') = 'object' then p_dados -> 'abastecimento' else '{}'::jsonb end;
    v_tipo   text;
    v_d      jsonb;
    v_ab_id  integer;
    v_fis    integer;
    v_lanc   integer;
    v_conta  integer;
    v_valor  numeric;
    v_data   date;
    v_cart   integer;
    v_meio   text;
    v_desc   text;
    v_ab     jsonb;
    v_r      jsonb;
    v_compra jsonb;
    v_reuso  boolean := false;
    v_atual  financeiro.abastecimento;
    v_comp   public.lancamento_agregado;
    v_ct     public.conta;
    v_novo   financeiro.abastecimento;
    v_vinc   jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_rep := financeiro.repeticao_mobilidade(p_chave, p_perfil_id, 'salvar_lancamento_abastecimento');
    if v_rep is not null then
        return v_rep;
    end if;
    v_tipo := v_l ->> 'tipo';
    if v_tipo is null or v_tipo not in ('compra', 'despesa', 'compra_existente', 'despesa_existente') then
        raise exception 'Dados do lançamento inválidos' using errcode = '22023';
    end if;
    v_d := case when jsonb_typeof(v_l -> 'dados') = 'object' then v_l -> 'dados' end;
    v_ab_id := nullif(financeiro.mob_inteiro(v_a -> 'id'), 0);
    v_fis := nullif(financeiro.mob_inteiro(v_a -> 'cartao_vinculado_id'), 0);

    -- 1. O que o abastecimento herda da despesa (valor, data, cartao, estabelecimento)
    if v_tipo in ('compra', 'despesa') and v_d is null then
        raise exception 'Dados do lançamento inválidos' using errcode = '22023';
    end if;
    if v_tipo = 'compra' then
        if coalesce(financeiro.mob_inteiro(v_d -> 'total_parcelas'), 1) <> 1 then
            raise exception 'Abastecimento é registrado com compra à vista (1 parcela). Lance a compra parcelada sem os dados do abastecimento. Nada foi gravado.'
                using errcode = '22023', hint = 'ABASTECIMENTO_PARCELADO';
        end if;
        v_valor := financeiro.numero_seguro(v_d -> 'valor');
        v_data := financeiro.mob_data(v_d ->> 'data_compra');
        v_cart := financeiro.mob_inteiro(v_d -> 'cartao_id');
        v_meio := 'cartao';
        v_desc := v_d ->> 'descricao';
    elsif v_tipo = 'despesa' then
        v_valor := financeiro.numero_seguro(v_d -> 'valor');
        v_data := financeiro.mob_data(v_d ->> 'data_vencimento');
        v_desc := v_d ->> 'nome';
    elsif v_tipo = 'compra_existente' then
        select * into v_comp from public.lancamento_agregado l
         where l.id = financeiro.mob_inteiro(v_l -> 'id') and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id) for update;
        if not found then
            raise exception 'Compra não encontrada neste perfil' using errcode = '22023', hint = 'NAO_ENCONTRADA';
        end if;
        if coalesce(v_comp.total_parcelas, 1) <> 1 then
            raise exception 'Abastecimento é registrado com compra à vista (1 parcela). Nada foi gravado.' using errcode = '22023', hint = 'ABASTECIMENTO_PARCELADO';
        end if;
        v_lanc := v_comp.id;
        v_valor := v_comp.valor;
        v_data := v_comp.data_compra;
        v_cart := v_comp.cartao_id;
        v_meio := 'cartao';
        v_desc := coalesce(nullif(v_comp.descricao_exibida, ''), v_comp.descricao);
        v_fis := coalesce(v_fis, v_comp.cartao_vinculado_id);
    else
        select * into v_ct from public.conta c
         where c.id = financeiro.mob_inteiro(v_l -> 'id') and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
           and not coalesce(c.is_fatura_cartao, false) and c.status_pagamento is distinct from 'Substituida' and c.status_pagamento is distinct from 'Dispensada' for update;
        if not found then
            raise exception 'Despesa não encontrada neste perfil' using errcode = '22023', hint = 'NAO_ENCONTRADA';
        end if;
        v_conta := v_ct.id;
        v_valor := coalesce(financeiro.numero_seguro(v_d -> 'valor'), v_ct.valor);
        v_data := coalesce(financeiro.mob_data(v_d ->> 'data_vencimento'), v_ct.data_vencimento);
        v_desc := coalesce(nullif(v_d ->> 'nome', ''), v_ct.descricao);
    end if;
    if v_meio is null then
        v_meio := nullif(lower(btrim(coalesce(v_a ->> 'meio_pagamento', ''))), '');
        if v_meio = 'cartao' then
            raise exception 'Despesa direta não é compra no cartão: lance pelo tipo Cartão de crédito' using errcode = '22023';
        end if;
    end if;
    v_ab := (v_a - 'id' - 'valor_total' - 'data_abastecimento' - 'cartao_id' - 'cartao_vinculado_id' - 'meio_pagamento' - 'lancamento_id' - 'conta_id')
            || jsonb_strip_nulls(jsonb_build_object('valor_total', v_valor, 'data_abastecimento', v_data, 'cartao_id', v_cart,
                                                    'cartao_vinculado_id', v_fis, 'meio_pagamento', v_meio,
                                                    'estabelecimento', coalesce(nullif(btrim(coalesce(v_a ->> 'estabelecimento', '')), ''), left(v_desc, 120))));

    -- 2. Antes de qualquer despesa, os dados do abastecimento com as regras de sempre (hodometro, combustivel, cartao)
    if v_ab_id is null then
        perform financeiro.mob_dados_abastecimento(p_perfil_id, v_ab);
    end if;

    -- 3. A despesa
    if v_tipo = 'compra' then
        v_compra := financeiro.criar_compra(p_perfil_id, v_d, extensions.uuid_generate_v5(p_chave, 'compra'));
        v_lanc := (v_compra -> 'lancamentos' ->> 0)::integer;
        if v_fis is not null then
            -- o cartao fisico da compra (o mesmo do abastecimento); o gatilho confere que e do mesmo contrato
            update public.lancamento_agregado set cartao_vinculado_id = v_fis where id = v_lanc;
        end if;
    elsif v_tipo = 'despesa' then
        v_r := financeiro.criar_despesa(p_perfil_id, v_d, extensions.uuid_generate_v5(p_chave, 'despesa'));
        v_conta := (v_r ->> 'conta_id')::integer;
    end if;

    -- 4. O abastecimento, vinculado
    v_vinc := case when v_lanc is not null then jsonb_build_object('lancamento_id', v_lanc) else jsonb_build_object('conta_id', v_conta) end;
    select * into v_atual from financeiro.abastecimento x
     where (v_lanc is not null and x.lancamento_id = v_lanc) or (v_conta is not null and x.conta_id = v_conta);
    if found then
        -- edicao: o mesmo abastecimento acompanha a despesa (valor, data e dados operacionais), com o historico
        if v_ab_id is distinct from v_atual.id then
            raise exception 'Esta despesa já tem um abastecimento vinculado. Nada foi gravado.' using errcode = '22023', hint = 'DESPESA_JA_VINCULADA';
        end if;
        perform financeiro.desvincular_abastecimento(p_perfil_id, v_atual.id);
        if v_tipo = 'despesa_existente' and v_d is not null then
            perform financeiro.editar_despesa(p_perfil_id, v_conta, v_l ->> 'versao', v_d);
        end if;
        perform financeiro.corrigir_abastecimento(p_perfil_id, v_atual.id,
            v_ab || jsonb_build_object('motivo', 'Ajuste pelo formulário de Lançamentos'));
        perform financeiro.vincular_abastecimento(p_perfil_id, v_atual.id, v_vinc);
    else
        if v_tipo = 'despesa_existente' and v_d is not null then
            perform financeiro.editar_despesa(p_perfil_id, v_conta, v_l ->> 'versao', v_d);
        end if;
        if v_ab_id is null then
            -- o mesmo abastecimento ja registrado em Mobilidade, ainda sem despesa, e reaproveitado (nao ha dois registros)
            select x.id into v_ab_id from financeiro.abastecimento x
             where x.veiculo_id = financeiro.mob_inteiro(v_ab -> 'veiculo_id') and x.anulado_em is null
               and x.lancamento_id is null and x.conta_id is null
               and x.data_abastecimento = v_data and x.valor_total = v_valor
               and x.hodometro_km = round(financeiro.numero_seguro(v_ab -> 'hodometro_km'), 1)
             order by x.id limit 1;
            v_reuso := v_ab_id is not null;
        else
            v_reuso := true;
        end if;
        if v_ab_id is null then
            v_r := financeiro.registrar_abastecimento(p_perfil_id, v_ab, extensions.uuid_generate_v5(p_chave, 'abastecimento'));
            v_ab_id := (v_r -> 'abastecimento' ->> 'id')::integer;
        end if;
        perform financeiro.vincular_abastecimento(p_perfil_id, v_ab_id, v_vinc);
    end if;
    select * into v_novo from financeiro.abastecimento x where x.id = v_ab_id;
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'salvar_lancamento_abastecimento', jsonb_build_object(
        'lancamento_id', v_lanc, 'conta_id', v_conta, 'reaproveitado', v_reuso,
        'abastecimento', financeiro.mob_abastecimento_flask(v_novo), 'compra', v_compra));
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.ocorrencias_interrupcao(p_item_id integer, p_efeito date, p_conta_id integer)
 RETURNS TABLE(natureza text, registro_id integer, competencia date, data_vencimento date, valor numeric, cartao_id integer, elegivel boolean, motivo text)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    with hoje as (select (now() at time zone 'America/Sao_Paulo')::date as d),
    contas as (
        select c.id, date_trunc('month', c.mes_referencia::timestamp)::date as comp, c.data_vencimento as venc, c.valor,
               financeiro.bloqueio_da_despesa(c.id) as bloqueio
          from public.conta c
         where c.item_despesa_id = p_item_id
           and not coalesce(c.is_fatura_cartao, false)
           and c.status_pagamento is distinct from 'Dispensada'  -- FIN-DESPESAS-CANCELAMENTO-01 (P23)
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
$function$;

revoke execute on function financeiro.registrar_dispensa_recorrente(public.item_despesa, public.conta, text, boolean) from public, anon, authenticated;
revoke execute on function financeiro.situacao_cancelamento_despesa(integer) from public, anon, authenticated;
revoke execute on function financeiro.previa_cancelamento_despesa(integer, integer) from public, anon;
revoke execute on function financeiro.cancelar_despesa(integer, integer, text) from public, anon;
grant execute on function financeiro.previa_cancelamento_despesa(integer, integer) to authenticated;
grant execute on function financeiro.cancelar_despesa(integer, integer, text) to authenticated;
