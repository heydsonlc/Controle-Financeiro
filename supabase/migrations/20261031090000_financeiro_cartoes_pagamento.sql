-- FIN-CARTOES-PAGAMENTO-1 — pagamento e estorno de fatura de cartao no novo aplicativo.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261031090000).
-- Validada em cluster local descartavel (tests/test_cartoes_pagamento.py). Docs: docs/FIN_CARTOES_PAGAMENTO_1.md.
--
-- Regras do Flask (CartaoService.pagar_fatura e despesas.estornar_pagamento) reaproveitadas, nas mesmas tabelas:
-- - pagamento: fatura travada, executado recalculado pelas compras, conta bancaria do perfil e ativa, movimento
--   DEBITO origem FATURA (conta_id = fatura_id = fatura), saldo_atual = saldo_inicial + creditos - debitos,
--   fatura 'Pago' com valor = valor pago. status_fatura (fechamento/consolidacao) nao muda;
-- - estorno: movimento CREDITO origem ESTORNO_FATURA com movimento_original_id; o original fica no historico.
-- Correcoes em relacao ao Flask:
-- - a identidade do pagamento e o movimento de debito (nunca "a fatura ja teve um estorno"): pagar, estornar, pagar
--   e estornar de novo funciona;
-- - o estorno devolve a fatura ao estado aberto recalculado (valor = planejado), em vez de manter o valor pago;
-- - valor pago diferente do executado so com classificacao (JUROS, DESCONTO ou AJUSTE de quitacao integral) e
--   justificativa; nao existe saldo pendente (pagamento parcial fica para outra etapa).
-- Escritor unico (D5): so paga/estorna perfil atribuido ao novo aplicativo (financeiro.gerador_recorrencia = NOVO,
-- a mesma atribuicao do FIN-RECORRENCIA-T1); o Flask recusa pagar/estornar fatura desses perfis.
-- Ordem de travas (FIN-FATURA-INTEGRIDADE-1): chave -> perfil (20261023) -> fatura -> conta bancaria -> movimento.
-- Nenhum dado existente e alterado.

-- 1. Dados do pagamento que o movimento nao guarda. Valor, conta e data ficam so no movimento (sem duplicar).
create table financeiro.pagamento_fatura (
    id                    bigint      generated always as identity primary key,
    fatura_id             integer     not null references public.conta (id) on delete cascade,
    perfil_financeiro_id  integer     not null,
    movimento_id          integer     not null references public.movimento_financeiro (id) on delete cascade,
    origem                text        not null,
    valor_executado       numeric(15, 2),
    tipo_ajuste           text,
    justificativa         text,
    user_id               uuid,
    criado_em             timestamptz not null default now(),
    estorno_movimento_id  integer     references public.movimento_financeiro (id) on delete set null,
    estorno_motivo        text,
    estorno_user_id       uuid,
    estornado_em          timestamptz,
    constraint ux_pagamento_fatura_movimento unique (movimento_id),
    constraint ux_pagamento_fatura_estorno unique (estorno_movimento_id),
    constraint ck_pagamento_fatura_origem check (origem in ('NOVO_APP', 'FLASK')),
    constraint ck_pagamento_fatura_ajuste check (tipo_ajuste in ('JUROS', 'DESCONTO', 'AJUSTE')),
    constraint ck_pagamento_fatura_justificativa check (tipo_ajuste is null or length(btrim(justificativa)) > 0),
    constraint ck_pagamento_fatura_estorno check ((estornado_em is null) = (estorno_motivo is null))
);
comment on table financeiro.pagamento_fatura is
    'FIN-CARTOES-PAGAMENTO-1: executado no pagamento, ajuste justificado, responsavel e estorno de cada pagamento de '
    'fatura (identidade = movimento de debito). Origem FLASK: pagamento do Flask estornado pelo novo aplicativo.';
-- No maximo um pagamento vigente (nao estornado) por fatura.
create unique index ux_pagamento_fatura_vigente on financeiro.pagamento_fatura (fatura_id) where estornado_em is null;
alter table financeiro.pagamento_fatura enable row level security;
alter table financeiro.pagamento_fatura force row level security;
revoke all on financeiro.pagamento_fatura from public, anon, authenticated;

-- 2. Executado da fatura pelas compras (mesma soma de recalcular_fatura). Interna.
create function financeiro.executado_fatura(p_fatura_id integer)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce(sum(l.valor), 0)
      from public.conta c
      join public.lancamento_agregado l on l.cartao_id = c.item_despesa_id and l.mes_fatura = c.cartao_competencia
     where c.id = p_fatura_id
       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, coalesce(c.perfil_financeiro_id,
               (select p.id from public.perfil_financeiro p where p.nome = 'Pessoal' order by p.id limit 1)))
$$;
revoke execute on function financeiro.executado_fatura(integer) from public, anon, authenticated;

-- 3. Saldo pelos movimentos (como ContaBancariaService.recalcular_saldo_conta). Internas.
create function financeiro.saldo_da_conta(p_conta_bancaria_id integer)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce(cb.saldo_inicial, 0)
           + coalesce((select sum(case when m.tipo = 'CREDITO' then m.valor when m.tipo = 'DEBITO' then -m.valor else 0 end)
                         from public.movimento_financeiro m where m.conta_bancaria_id = cb.id), 0)
      from public.conta_bancaria cb where cb.id = p_conta_bancaria_id
$$;
revoke execute on function financeiro.saldo_da_conta(integer) from public, anon, authenticated;

-- saldo_atual e o mesmo valor que o Flask grava (cache recalculado), nunca um segundo saldo independente.
create function financeiro.atualizar_saldo_conta(p_conta_bancaria_id integer)
    returns numeric
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_saldo numeric := financeiro.saldo_da_conta(p_conta_bancaria_id);
begin
    update public.conta_bancaria set saldo_atual = v_saldo, data_atualizacao = now() at time zone 'utc'
     where id = p_conta_bancaria_id;
    return v_saldo;
end
$$;
revoke execute on function financeiro.atualizar_saldo_conta(integer) from public, anon, authenticated;

-- 4. Escritor unico (D5): so o perfil atribuido ao novo aplicativo. Mesma trava de criar_compra e da geracao
-- (a troca de atribuicao espera). Interna.
create function financeiro.exigir_pagamento_novo(p_perfil_id integer)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_sistema text;
begin
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    select g.gerador into v_sistema from financeiro.gerador_recorrencia g
     where g.perfil_financeiro_id = p_perfil_id for share;
    if v_sistema is distinct from 'NOVO' then
        raise exception 'Os pagamentos deste perfil ainda sao feitos pelo sistema atual (Flask)'
            using errcode = 'P0001', hint = 'SISTEMA_FLASK';
    end if;
end
$$;
revoke execute on function financeiro.exigir_pagamento_novo(integer) from public, anon, authenticated;

-- Fatura do perfil, travada (FOR UPDATE). Interna.
create function financeiro.travar_fatura_do_perfil(p_perfil_id integer, p_fatura_id integer)
    returns public.conta
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_fatura public.conta;
begin
    select * into v_fatura from public.conta c where c.id = p_fatura_id and c.is_fatura_cartao for update;
    if not found or not financeiro.pertence_ao_perfil(v_fatura.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Fatura nao encontrada neste perfil' using errcode = '42501';
    end if;
    return v_fatura;
end
$$;
revoke execute on function financeiro.travar_fatura_do_perfil(integer, integer) from public, anon, authenticated;

-- Pagamento vigente: o debito mais recente da fatura, sem estorno que o referencie. Interna.
create function financeiro.pagamento_vigente(p_fatura_id integer)
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select m.id from public.movimento_financeiro m
     where (m.conta_id = p_fatura_id or m.fatura_id = p_fatura_id) and m.tipo = 'DEBITO' and m.origem = 'FATURA'
       and not exists (select 1 from public.movimento_financeiro e
                        where e.movimento_original_id = m.id and e.tipo = 'CREDITO')
     order by m.id desc limit 1
$$;
revoke execute on function financeiro.pagamento_vigente(integer) from public, anon, authenticated;

-- 5. Leitura para a tela: fatura (executado recalculado), contas ativas com saldo, historico de pagamentos e
-- estornos e o que o usuario pode fazer. Quem acessa o perfil le; pagar/estornar exige gestao e o novo aplicativo.
create function financeiro.dados_pagamento_fatura(p_perfil_id integer, p_fatura_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_fatura    public.conta;
    v_paga      boolean;
    v_executado numeric;
    v_gerir     boolean;
    v_novo      boolean;
    v_vigente   integer;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_fatura from public.conta c where c.id = p_fatura_id and c.is_fatura_cartao;
    if not found or not financeiro.pertence_ao_perfil(v_fatura.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Fatura nao encontrada neste perfil' using errcode = '42501';
    end if;
    v_paga := financeiro.fatura_esta_paga(v_fatura.id);
    v_executado := case when v_paga then coalesce(v_fatura.valor_executado, 0) else financeiro.executado_fatura(v_fatura.id) end;
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    v_novo := financeiro.gerador_do_perfil(p_perfil_id) = 'NOVO';
    v_vigente := financeiro.pagamento_vigente(v_fatura.id);
    return jsonb_build_object(
        'fatura', jsonb_build_object(
            'id', v_fatura.id, 'cartao_id', v_fatura.item_despesa_id,
            'cartao_nome', (select i.nome from public.item_despesa i where i.id = v_fatura.item_despesa_id),
            'competencia', v_fatura.cartao_competencia, 'data_vencimento', v_fatura.data_vencimento,
            'valor_executado', v_executado, 'paga', v_paga, 'status_fatura', v_fatura.status_fatura),
        'contas', coalesce((select jsonb_agg(jsonb_build_object('id', cb.id, 'nome', cb.nome, 'instituicao', cb.instituicao,
                                                                'saldo', financeiro.saldo_da_conta(cb.id)) order by cb.nome, cb.id)
                              from public.conta_bancaria cb
                             where cb.status = 'ATIVO' and financeiro.pertence_ao_perfil(cb.perfil_financeiro_id, p_perfil_id)),
                           '[]'::jsonb),
        'pagamentos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'movimento_id', m.id, 'data_pagamento', m.data_movimento, 'valor_pago', m.valor,
                       'conta_bancaria_id', m.conta_bancaria_id, 'conta_nome', cb.nome,
                       'valor_executado', p.valor_executado, 'tipo_ajuste', p.tipo_ajuste,
                       'justificativa', p.justificativa, 'origem', coalesce(p.origem, 'FLASK'),
                       'vigente', coalesce(m.id = v_vigente, false) and v_paga,
                       'estorno', case when e.id is null then null else jsonb_build_object(
                           'movimento_id', e.id, 'data', e.data_movimento, 'valor', e.valor,
                           'motivo', p.estorno_motivo) end) order by m.id)
              from public.movimento_financeiro m
              left join public.conta_bancaria cb on cb.id = m.conta_bancaria_id
              left join financeiro.pagamento_fatura p on p.movimento_id = m.id
              left join lateral (select x.id, x.data_movimento, x.valor from public.movimento_financeiro x
                                  where x.movimento_original_id = m.id and x.tipo = 'CREDITO'
                                  order by x.id limit 1) e on true
             where (m.conta_id = v_fatura.id or m.fatura_id = v_fatura.id) and m.tipo = 'DEBITO' and m.origem = 'FATURA'),
            '[]'::jsonb),
        'sistema', case when v_novo then 'NOVO' else 'FLASK' end,
        'pode_pagar', v_gerir and v_novo and not v_paga and v_executado > 0,
        'pode_estornar', v_gerir and v_novo and v_paga and v_vigente is not null);
end
$$;

-- 6. Pagamento integral. p_dados: conta_bancaria_id, data_pagamento, valor_pago, valor_executado (o total que o
-- usuario viu: se o banco recalcular outro, recusa para nova conferencia) e, se o valor pago for diferente do
-- executado, tipo_ajuste (JUROS se maior, DESCONTO se menor, AJUSTE em ambos) com justificativa.
-- Idempotente pela chave: a mesma solicitacao devolve o mesmo resultado, sem novo debito.
create function financeiro.pagar_fatura(p_perfil_id integer, p_fatura_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_cartao;
    v_fatura    public.conta;
    v_conta     public.conta_bancaria;
    v_conta_id  integer;
    v_data      date;
    v_valor     numeric;
    v_visto     numeric;
    v_executado numeric;
    v_tipo      text;
    v_just      text;
    v_mov       integer;
    v_pag       bigint;
    v_saldo     numeric;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261031));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'pagar_fatura' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do pagamento invalidos' using errcode = '22023';
    end if;
    begin
        v_conta_id := (p_dados ->> 'conta_bancaria_id')::integer;
        v_data := (p_dados ->> 'data_pagamento')::date;
        v_valor := (p_dados ->> 'valor_pago')::numeric;
        v_visto := (p_dados ->> 'valor_executado')::numeric;
    exception when invalid_text_representation or datetime_field_overflow or invalid_datetime_format
                   or numeric_value_out_of_range then
        raise exception 'Dados do pagamento invalidos' using errcode = '22023';
    end;
    if v_conta_id is null then
        raise exception 'Selecione a conta bancaria do pagamento' using errcode = '22023';
    end if;
    if v_data is null then
        raise exception 'Informe a data do pagamento' using errcode = '22023';
    end if;
    if v_valor is null or v_valor <= 0 or v_valor <> round(v_valor, 2) then
        raise exception 'Valor pago deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
    end if;

    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    v_fatura := financeiro.travar_fatura_do_perfil(p_perfil_id, p_fatura_id);
    if financeiro.fatura_esta_paga(v_fatura.id) then
        raise exception 'Esta fatura ja foi paga' using errcode = '22023', hint = 'FATURA_PAGA';
    end if;
    -- Com a fatura travada nenhuma compra entra nela (criar_compra trava a mesma linha): a soma e a definitiva.
    v_executado := financeiro.executado_fatura(v_fatura.id);
    if v_executado <= 0 then
        raise exception 'Fatura sem compras: nada a pagar' using errcode = '22023';
    end if;
    if v_visto is distinct from v_executado then
        raise exception 'O total da fatura mudou para R$ %. Confira e confirme de novo.',
            replace(to_char(v_executado, 'FM999999990.00'), '.', ',') using errcode = '22023', hint = 'EXECUTADO_MUDOU';
    end if;
    if v_valor <> v_executado then
        v_tipo := upper(btrim(coalesce(p_dados ->> 'tipo_ajuste', '')));
        v_just := btrim(coalesce(p_dados ->> 'justificativa', ''));
        if v_tipo not in ('JUROS', 'DESCONTO', 'AJUSTE') or (v_tipo = 'JUROS' and v_valor < v_executado)
           or (v_tipo = 'DESCONTO' and v_valor > v_executado) then
            raise exception 'Valor diferente do total: classifique a diferenca (juros, desconto ou ajuste de quitacao integral)'
                using errcode = '22023', hint = 'AJUSTE_OBRIGATORIO';
        end if;
        if v_just = '' or length(v_just) > 500 then
            raise exception 'Valor diferente do total: a justificativa e obrigatoria (ate 500 caracteres)'
                using errcode = '22023', hint = 'AJUSTE_OBRIGATORIO';
        end if;
    end if;
    select * into v_conta from public.conta_bancaria cb where cb.id = v_conta_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Conta bancaria nao encontrada neste perfil' using errcode = '22023';
    end if;
    if v_conta.status is distinct from 'ATIVO' then
        raise exception 'Conta bancaria inativa' using errcode = '22023';
    end if;

    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             fatura_id, conta_id, origem, ajustavel, criado_em)
    values (p_perfil_id, v_conta.id, 'DEBITO', v_valor, left('Pagamento fatura cartao - ' || v_fatura.descricao, 200), v_data,
            v_fatura.id, v_fatura.id, 'FATURA', false, now() at time zone 'utc')
    returning id into v_mov;
    v_saldo := financeiro.atualizar_saldo_conta(v_conta.id);
    update public.conta set valor_executado = v_executado, valor = v_valor, data_pagamento = v_data,
                            status_pagamento = 'Pago', conta_bancaria_id = v_conta.id
     where id = v_fatura.id;
    insert into financeiro.pagamento_fatura (fatura_id, perfil_financeiro_id, movimento_id, origem, valor_executado,
                                            tipo_ajuste, justificativa, user_id)
    values (v_fatura.id, p_perfil_id, v_mov, 'NOVO_APP', v_executado, v_tipo, nullif(v_just, ''), (select auth.uid()))
    returning id into v_pag;
    v_resultado := jsonb_build_object('fatura_id', v_fatura.id, 'movimento_id', v_mov, 'pagamento_id', v_pag,
                                      'valor_pago', v_valor, 'valor_executado', v_executado, 'diferenca', v_valor - v_executado,
                                      'tipo_ajuste', v_tipo, 'data_pagamento', v_data, 'conta_bancaria_id', v_conta.id,
                                      'conta_nome', v_conta.nome, 'saldo_conta', v_saldo);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'pagar_fatura', v_resultado);
    return v_resultado;
end
$$;

-- 7. Estorno do pagamento vigente (p_movimento_id: o debito do pagamento, visto na tela). p_dados: motivo e
-- data_estorno. Credito compensatorio na mesma conta; o debito original fica. A fatura volta a aberta recalculada
-- (status_fatura preservado). Idempotente pela chave.
create function financeiro.estornar_pagamento_fatura(p_perfil_id integer, p_fatura_id integer, p_movimento_id integer,
                                                     p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_cartao;
    v_fatura    public.conta;
    v_original  public.movimento_financeiro;
    v_motivo    text;
    v_data      date;
    v_estorno   integer;
    v_saldo     numeric;
    v_perfil    integer;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261031));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'estornar_pagamento_fatura' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    v_motivo := btrim(coalesce(p_dados ->> 'motivo', ''));
    if v_motivo = '' or length(v_motivo) > 500 then
        raise exception 'Informe o motivo do estorno (ate 500 caracteres)' using errcode = '22023';
    end if;
    begin
        v_data := (p_dados ->> 'data_estorno')::date;
    exception when invalid_datetime_format or datetime_field_overflow then
        raise exception 'Data do estorno invalida' using errcode = '22023';
    end;
    if v_data is null then
        raise exception 'Informe a data do estorno' using errcode = '22023';
    end if;
    if p_movimento_id is null then
        raise exception 'Pagamento a estornar nao identificado' using errcode = '22023';
    end if;

    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    v_fatura := financeiro.travar_fatura_do_perfil(p_perfil_id, p_fatura_id);
    if v_fatura.status_pagamento is distinct from 'Pago' then
        raise exception 'Esta fatura nao esta paga: nada a estornar' using errcode = '22023', hint = 'NAO_PAGA';
    end if;
    select * into v_original from public.movimento_financeiro m where m.id = p_movimento_id;
    if not found or v_original.tipo <> 'DEBITO' or v_original.origem <> 'FATURA'
       or not (v_original.conta_id = v_fatura.id or v_original.fatura_id = v_fatura.id) then
        raise exception 'Pagamento nao encontrado nesta fatura' using errcode = '22023';
    end if;
    -- Ordem global: conta bancaria antes do movimento.
    perform 1 from public.conta_bancaria cb where cb.id = v_original.conta_bancaria_id for update;
    perform 1 from public.movimento_financeiro m where m.id = v_original.id for update;
    if p_movimento_id is distinct from financeiro.pagamento_vigente(v_fatura.id) then
        raise exception 'Este pagamento ja foi estornado ou nao e o pagamento atual da fatura'
            using errcode = '22023', hint = 'JA_ESTORNADO';
    end if;

    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             fatura_id, conta_id, origem, ajustavel, movimento_original_id, criado_em)
    values (coalesce(v_original.perfil_financeiro_id, p_perfil_id), v_original.conta_bancaria_id, 'CREDITO',
            v_original.valor, left('Estorno de pagamento da fatura: ' || coalesce(v_fatura.descricao, v_fatura.id::text), 200),
            v_data, v_fatura.id, v_fatura.id, 'ESTORNO_FATURA', false, v_original.id, now() at time zone 'utc')
    returning id into v_estorno;
    v_saldo := financeiro.atualizar_saldo_conta(v_original.conta_bancaria_id);
    update public.conta
       set status_pagamento = 'Pendente', data_pagamento = null,
           observacoes = concat_ws(E'\n', nullif(observacoes, ''), '[ESTORNO] ' || v_data::text || ' — ' || v_motivo)
     where id = v_fatura.id;
    -- Volta a aberta com os valores atuais das compras (planejado/executado), como qualquer fatura nao paga.
    v_perfil := coalesce(v_fatura.perfil_financeiro_id,
                         (select p.id from public.perfil_financeiro p where p.nome = 'Pessoal' order by p.id limit 1));
    perform financeiro.recalcular_fatura(v_perfil, v_fatura.item_despesa_id, v_fatura.cartao_competencia);
    update financeiro.pagamento_fatura
       set estorno_movimento_id = v_estorno, estorno_motivo = v_motivo, estorno_user_id = (select auth.uid()),
           estornado_em = now()
     where movimento_id = v_original.id;
    if not found then  -- pagamento feito pelo Flask: registra so o estorno
        insert into financeiro.pagamento_fatura (fatura_id, perfil_financeiro_id, movimento_id, origem, estorno_movimento_id,
                                                estorno_motivo, estorno_user_id, estornado_em)
        values (v_fatura.id, p_perfil_id, v_original.id, 'FLASK', v_estorno, v_motivo, (select auth.uid()), now());
    end if;
    v_resultado := jsonb_build_object('fatura_id', v_fatura.id, 'movimento_estorno_id', v_estorno,
                                      'movimento_original_id', v_original.id, 'valor_estornado', v_original.valor,
                                      'data_estorno', v_data, 'conta_bancaria_id', v_original.conta_bancaria_id,
                                      'saldo_conta', v_saldo);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'estornar_pagamento_fatura', v_resultado);
    return v_resultado;
end
$$;

revoke execute on function financeiro.dados_pagamento_fatura(integer, integer) from public, anon;
revoke execute on function financeiro.pagar_fatura(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.estornar_pagamento_fatura(integer, integer, integer, jsonb, uuid) from public, anon;
grant execute on function financeiro.dados_pagamento_fatura(integer, integer) to authenticated;
grant execute on function financeiro.pagar_fatura(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.estornar_pagamento_fatura(integer, integer, integer, jsonb, uuid) to authenticated;
