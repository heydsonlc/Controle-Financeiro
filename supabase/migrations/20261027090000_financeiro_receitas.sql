-- FIN-RECEITAS-1 — consulta e gestao de receitas PREVISTAS, por perfil.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261027090000).
-- Validada em cluster local descartavel, com comparacao contra o Flask
-- (tests/test_supabase_receitas.py). Diagnostico e decisoes: docs/FIN_RECEITAS_1.md.
--
-- Reutiliza o modelo do Flask, sem tabela paralela de receitas:
-- - public.item_receita      = fonte (nome unico por perfil; `tipo` faz o papel de categoria);
-- - public.receita_orcamento = previsao mensal (valor esperado por competencia);
-- - public.receita_realizada = recebimento efetivo (com movimento de credito) — SO LIDO aqui.
-- Regra central: receita prevista nao e dinheiro recebido. Nenhuma funcao desta migration
-- cria, altera ou remove recebimento, movimento financeiro ou saldo.
-- Situacao (como a tela de receitas do Flask, a partir dos registros reais):
-- - RECEBIDA: soma recebida (sem estornos e sem previsao de consorcio) >= prevista;
-- - PARCIAL: recebido > 0 e < previsto; PREVISTA: nada recebido; INATIVA: fonte inativa e
--   nada recebido; REMOVIDA: previsao zerada pelo usuario (o "excluir" do Flask);
-- - recebimentos sem previsao: RECEBIDA; com movimento de estorno: ESTORNADA;
--   contemplacao de consorcio sem conta (marcador consorcio_id=): PREVISTA_CONSORCIO (outro modulo).
-- Escrita: so com gestao explicita (pode_gerir); previsao com recebimento (mesmo estornado)
-- nao muda; fontes do modulo de consorcios ficam bloqueadas; versao (md5) + FOR UPDATE; a
-- tabela de recebimentos e travada em modo SHARE durante a alteracao de uma previsao, para
-- que um recebimento simultaneo no Flask espere (ou seja visto) — nunca se cruzam;
-- criacao idempotente por chave (financeiro.operacao_receita).

create table financeiro.operacao_receita (
    chave                uuid        primary key,
    user_id              uuid        not null references auth.users (id) on delete cascade,
    perfil_financeiro_id integer     not null,
    operacao             text        not null,
    resultado            jsonb       not null,
    criado_em            timestamptz not null default now()
);

comment on table financeiro.operacao_receita is
    'FIN-RECEITAS-1: resultado de cada cadastro por chave do cliente (repeticao devolve o mesmo resultado).';

alter table financeiro.operacao_receita enable row level security;
alter table financeiro.operacao_receita force row level security;
revoke all on financeiro.operacao_receita from public, anon, authenticated;

-- Recebimento estornado: existe movimento compensatorio (CORE-ESTORNO-2 do Flask). Interna.
create function financeiro.receita_estornada(p_realizada_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from public.movimento_financeiro m
                    where m.receita_realizada_id = p_realizada_id and m.origem = 'ESTORNO_RECEITA')
$$;

-- Fonte criada pelo modulo de consorcios (contemplacao): so o modulo a altera. Interna.
create function financeiro.fonte_de_outro_modulo(p_item_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from public.item_receita i
                    where i.id = p_item_id
                      and i.nome in ('Contemplação de Consórcio', 'ContemplaÃ§Ã£o de ConsÃ³rcio'))
        or exists (select 1 from public.receita_realizada r
                    where r.item_receita_id = p_item_id and r.observacoes ~ 'consorcio_id=[0-9]+')
$$;

-- Motivo que impede alterar/remover a previsao (NULL = permitido). Interna.
create function financeiro.bloqueio_da_previsao(p_orcamento_id integer)
    returns text
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_orc public.receita_orcamento;
begin
    select * into v_orc from public.receita_orcamento where id = p_orcamento_id;
    if not found then
        return 'Previsao inexistente';
    end if;
    if financeiro.fonte_de_outro_modulo(v_orc.item_receita_id) then
        return 'Gerada pelo modulo de consorcios';
    end if;
    if exists (select 1 from public.receita_realizada r
                where r.orcamento_id = v_orc.id
                   or (r.item_receita_id = v_orc.item_receita_id
                       and date_trunc('month', r.mes_referencia::timestamp) = date_trunc('month', v_orc.mes_referencia::timestamp))) then
        return 'Ha recebimento registrado nesta competencia';
    end if;
    return null;
end
$$;

create function financeiro.versao_previsao(p_orcamento_id integer)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select md5(o::text || '|' || i::text)
      from public.receita_orcamento o join public.item_receita i on i.id = o.item_receita_id
     where o.id = p_orcamento_id
$$;

create function financeiro.versao_fonte(p_item_id integer)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select md5(i::text) from public.item_receita i where i.id = p_item_id
$$;

-- Receitas da competencia (somente leitura): previsoes e recebimentos, com a situacao derivada.
create function financeiro.receitas_do_mes(p_perfil_id integer, p_mes date)
    returns table (
        origem text, id integer, item_receita_id integer, nome text, tipo text, competencia date,
        data_prevista date, valor_previsto numeric, valor_recebido numeric, situacao text,
        conta_bancaria_nome text, recorrente boolean, fonte_ativa boolean, observacoes text
    )
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes     date;
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null then
        raise exception 'Mes de competencia obrigatorio' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes::timestamp)::date;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');

    return query
    with realizadas as (
        select r.*, financeiro.receita_estornada(r.id) as estornada,
               (coalesce(r.observacoes, '') ~ 'consorcio_id=[0-9]+' and r.conta_bancaria_id is null) as consorcio
          from public.receita_realizada r
         where (r.perfil_financeiro_id = p_perfil_id or (r.perfil_financeiro_id is null and v_pessoal))
           and date_trunc('month', r.mes_referencia::timestamp)::date = v_mes
    ),
    previsoes as (
        select o.id, o.item_receita_id, i.nome, i.tipo, o.mes_referencia, o.valor_esperado, o.observacoes,
               i.dia_previsto_pagamento, i.conta_bancaria_id, coalesce(i.recorrente, true) as recorrente,
               coalesce(i.ativo, true) as ativo,
               coalesce((select sum(r.valor_recebido) from realizadas r
                          where r.item_receita_id = o.item_receita_id and not r.estornada and not r.consorcio), 0) as recebido
          from public.receita_orcamento o
          join public.item_receita i on i.id = o.item_receita_id
         where (o.perfil_financeiro_id = p_perfil_id or (o.perfil_financeiro_id is null and v_pessoal))
           and date_trunc('month', o.mes_referencia::timestamp)::date = v_mes
    ),
    linhas as (
    select 'PREVISAO'::text as origem, p.id, p.item_receita_id, p.nome::text as nome, p.tipo::text as tipo,
           v_mes as competencia,
           case when p.dia_previsto_pagamento between 1 and 31
                then financeiro.dia_contratual(v_mes, p.dia_previsto_pagamento) end as data_prevista,
           p.valor_esperado as valor_previsto, p.recebido as valor_recebido,
           case when p.valor_esperado = 0 and coalesce(p.observacoes, '') ilike 'Removid%' then 'REMOVIDA'
                when p.recebido > 0 and (p.valor_esperado <= 0 or p.recebido >= p.valor_esperado) then 'RECEBIDA'
                when p.recebido > 0 then 'PARCIAL'
                when not p.ativo then 'INATIVA'
                else 'PREVISTA' end as situacao,
           (select b.nome::text from public.conta_bancaria b where b.id = p.conta_bancaria_id) as conta_bancaria_nome,
           p.recorrente, p.ativo as fonte_ativa, p.observacoes
      from previsoes p
    union all
    -- Recebimentos sem previsao na competencia, estornos e previsoes de consorcio: linhas proprias.
    select 'RECEBIMENTO'::text, r.id, r.item_receita_id, coalesce(i.nome, r.descricao, 'Receita')::text,
           coalesce(i.tipo, 'PONTUAL')::text, v_mes, r.data_recebimento,
           case when r.consorcio then r.valor_recebido end,
           case when r.consorcio then 0 else r.valor_recebido end,
           case when r.estornada then 'ESTORNADA' when r.consorcio then 'PREVISTA_CONSORCIO' else 'RECEBIDA' end,
           (select b.nome::text from public.conta_bancaria b where b.id = r.conta_bancaria_id),
           coalesce(i.recorrente, false), coalesce(i.ativo, true), r.observacoes
      from realizadas r
      left join public.item_receita i on i.id = r.item_receita_id
     where r.estornada or r.consorcio
        or not exists (select 1 from previsoes p where p.item_receita_id = r.item_receita_id)
    )
    -- Mesma ordem da tela de receitas do Flask: prevista, parcial, recebida; depois as demais.
    select l.origem, l.id, l.item_receita_id, l.nome, l.tipo, l.competencia, l.data_prevista, l.valor_previsto,
           l.valor_recebido, l.situacao, l.conta_bancaria_nome, l.recorrente, l.fonte_ativa, l.observacoes
      from linhas l
     order by case l.situacao when 'PREVISTA' then 0 when 'PREVISTA_CONSORCIO' then 0 when 'PARCIAL' then 1
                               when 'RECEBIDA' then 2 else 3 end,
              l.data_prevista nulls last, l.nome;
end
$$;

-- Fontes do perfil (para escolher no cadastro).
create function financeiro.fontes_de_receita(p_perfil_id integer)
    returns table (id integer, nome text, tipo text, recorrente boolean, ativo boolean, dia_previsto integer,
                   conta_bancaria_id integer, valor_base_mensal numeric, de_outro_modulo boolean)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');
    return query
        select i.id, i.nome::text, i.tipo::text, coalesce(i.recorrente, true), coalesce(i.ativo, true),
               i.dia_previsto_pagamento, i.conta_bancaria_id, i.valor_base_mensal, financeiro.fonte_de_outro_modulo(i.id)
          from public.item_receita i
         where i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal)
         order by i.nome;
end
$$;

-- Validacao dos dados vindos do navegador. Interna. p_parcial: so as chaves presentes.
create function financeiro.ler_dados_receita(p_dados jsonb, p_perfil_id integer, p_parcial boolean)
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
        raise exception 'Dados da receita invalidos' using errcode = '22023';
    end if;
    if p_dados ?| array['valor_recebido', 'data_recebimento', 'recebido'] then
        raise exception 'Recebimento nao e registrado aqui (modulo de recebimentos)' using errcode = '22023';
    end if;
    if p_dados ? 'nome' or (not p_parcial and not p_dados ? 'item_receita_id') then
        v_texto := btrim(coalesce(p_dados ->> 'nome', ''));
        if v_texto = '' or length(v_texto) > 100 then
            raise exception 'Nome da fonte obrigatorio (ate 100 caracteres)' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('nome', v_texto);
    end if;
    if p_dados ? 'tipo' or (not p_parcial and not p_dados ? 'item_receita_id') then
        if coalesce(p_dados ->> 'tipo', '') not in
           ('SALARIO_FIXO', 'GRATIFICACAO', 'RENDA_EXTRA', 'ALUGUEL', 'RENDIMENTO_FINANCEIRO', 'OUTROS') then
            raise exception 'Categoria (tipo) de receita invalida' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('tipo', p_dados ->> 'tipo');
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
    if p_dados ? 'competencia' or not p_parcial then
        begin
            v_data := date_trunc('month', (p_dados ->> 'competencia')::date::timestamp)::date;
        exception when others then
            v_data := null;
        end;
        if v_data is null or v_data < date '2000-01-01' or v_data > date '2100-12-01' then
            raise exception 'Competencia invalida' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('competencia', v_data);
    end if;
    if p_dados ? 'dia_previsto' then
        if nullif(p_dados ->> 'dia_previsto', '') is null then
            v_saida := v_saida || jsonb_build_object('dia_previsto', null);
        else
            begin
                v_int := (p_dados ->> 'dia_previsto')::integer;
            exception when others then
                v_int := null;
            end;
            if v_int is null or v_int not between 1 and 31 then
                raise exception 'Dia previsto deve ficar entre 1 e 31' using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object('dia_previsto', v_int);
        end if;
    end if;
    if p_dados ? 'conta_bancaria_id' then
        if nullif(p_dados ->> 'conta_bancaria_id', '') is null then
            v_saida := v_saida || jsonb_build_object('conta_bancaria_id', null);
        else
            begin
                v_int := (p_dados ->> 'conta_bancaria_id')::integer;
            exception when others then
                v_int := null;
            end;
            if v_int is null or not exists (
                select 1 from public.conta_bancaria b
                 where b.id = v_int and b.status = 'ATIVO'
                   and financeiro.pertence_ao_perfil(b.perfil_financeiro_id, p_perfil_id)) then
                raise exception 'Conta bancaria de destino deve ser ativa e do perfil' using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object('conta_bancaria_id', v_int);
        end if;
    end if;
    foreach v_texto in array array['descricao', 'observacoes'] loop
        if p_dados ? v_texto then
            if length(p_dados ->> v_texto) > 1000 then
                raise exception 'Texto ate 1000 caracteres' using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object(v_texto, nullif(btrim(coalesce(p_dados ->> v_texto, '')), ''));
        end if;
    end loop;
    return v_saida;
end
$$;

-- Dados e permissoes de uma previsao para a tela (somente leitura).
create function financeiro.receita_para_edicao(p_perfil_id integer, p_orcamento_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_orc      public.receita_orcamento;
    v_item     public.item_receita;
    v_bloqueio text;
    v_modulo   boolean;
    v_gerir    boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_orc from public.receita_orcamento where id = p_orcamento_id;
    if not found or not financeiro.pertence_ao_perfil(v_orc.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Receita nao encontrada neste perfil' using errcode = '42501';
    end if;
    select * into v_item from public.item_receita where id = v_orc.item_receita_id;
    v_bloqueio := financeiro.bloqueio_da_previsao(p_orcamento_id);
    v_modulo := financeiro.fonte_de_outro_modulo(v_item.id);
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    return jsonb_build_object(
        'previsao', jsonb_build_object('id', v_orc.id, 'competencia', v_orc.mes_referencia, 'valor', v_orc.valor_esperado,
                                       'observacoes', v_orc.observacoes, 'periodicidade', v_orc.periodicidade),
        'fonte', jsonb_build_object('id', v_item.id, 'nome', v_item.nome, 'tipo', v_item.tipo,
                                    'recorrente', coalesce(v_item.recorrente, true), 'ativo', coalesce(v_item.ativo, true),
                                    'dia_previsto', v_item.dia_previsto_pagamento, 'conta_bancaria_id', v_item.conta_bancaria_id,
                                    'descricao', v_item.descricao, 'valor_base_mensal', v_item.valor_base_mensal),
        'bloqueio', v_bloqueio,
        'bloqueio_fonte', case when v_modulo then 'Gerada pelo modulo de consorcios' end,
        'pode_gerir', v_gerir,
        'pode_editar', v_gerir and v_bloqueio is null,
        'pode_mudar_competencia', v_gerir and v_bloqueio is null and not coalesce(v_item.recorrente, true),
        'pode_excluir', v_gerir and v_bloqueio is null,
        'pode_editar_fonte', v_gerir and not v_modulo,
        'pode_inativar_fonte', v_gerir and not v_modulo and coalesce(v_item.ativo, true),
        'versao', financeiro.versao_previsao(p_orcamento_id),
        'versao_fonte', financeiro.versao_fonte(v_item.id));
end
$$;

-- Cadastro de receita PREVISTA: fonte nova (avulsa ou recorrente) ou previsao de uma fonte existente.
-- Recorrente: 12 previsoes mensais a partir da competencia (o Flask gera 12 meses a partir do mes
-- atual ao criar a fonte), com o mesmo texto de observacao do Flask.
create function financeiro.criar_receita(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_receita;
    v_d         jsonb;
    v_rec       boolean;
    v_item      public.item_receita;
    v_item_id   integer;
    v_comp      date;
    v_ids       integer[] := '{}';
    v_id        integer;
    v_mes       date;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261027));
    select * into v_anterior from financeiro.operacao_receita o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    perform pg_advisory_xact_lock(20261027, p_perfil_id);  -- cadastros de receita do perfil em serie

    v_d := financeiro.ler_dados_receita(p_dados, p_perfil_id, false);
    v_rec := coalesce((p_dados ->> 'recorrente')::boolean, false);
    v_comp := (v_d ->> 'competencia')::date;

    if p_dados ? 'item_receita_id' then
        select * into v_item from public.item_receita i
         where i.id = (p_dados ->> 'item_receita_id')::integer
           and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
         for update;
        if not found then
            raise exception 'Fonte de receita nao encontrada neste perfil' using errcode = '42501';
        end if;
        if not coalesce(v_item.ativo, true) or financeiro.fonte_de_outro_modulo(v_item.id) then
            raise exception 'Fonte inativa ou de outro modulo' using errcode = '22023';
        end if;
        if v_rec then
            raise exception 'Recorrencia e definida ao criar a fonte' using errcode = '22023';
        end if;
        v_item_id := v_item.id;
    else
        if exists (select 1 from public.item_receita i
                    where i.nome = v_d ->> 'nome' and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)) then
            raise exception 'Ja existe uma fonte de receita com este nome' using errcode = '22023';
        end if;
        insert into public.item_receita (perfil_financeiro_id, nome, tipo, descricao, ativo, valor_base_mensal,
                                         dia_previsto_pagamento, conta_bancaria_id, recorrente, criado_em)
        values (p_perfil_id, v_d ->> 'nome', v_d ->> 'tipo', coalesce(v_d ->> 'descricao', ''), true,
                case when v_rec then (v_d ->> 'valor')::numeric end, (v_d ->> 'dia_previsto')::integer,
                (v_d ->> 'conta_bancaria_id')::integer, v_rec, now() at time zone 'utc')
        returning id into v_item_id;
        select * into v_item from public.item_receita where id = v_item_id;
    end if;

    if v_rec then
        for i in 0..11 loop
            v_mes := (v_comp + make_interval(months => i))::date;
            continue when exists (select 1 from public.receita_orcamento o
                                   where o.item_receita_id = v_item_id and o.mes_referencia = v_mes);
            insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, valor_esperado,
                                                  periodicidade, observacoes, criado_em)
            values (p_perfil_id, v_item_id, v_mes, (v_d ->> 'valor')::numeric, 'MENSAL_FIXA',
                    'Gerado automaticamente - ' || v_item.nome, now() at time zone 'utc')
            returning id into v_id;
            v_ids := v_ids || v_id;
        end loop;
    else
        if exists (select 1 from public.receita_orcamento o where o.item_receita_id = v_item_id and o.mes_referencia = v_comp) then
            raise exception 'Ja existe previsao desta fonte nesta competencia: edite a existente' using errcode = '22023';
        end if;
        insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, valor_esperado,
                                              periodicidade, observacoes, criado_em)
        values (p_perfil_id, v_item_id, v_comp, (v_d ->> 'valor')::numeric,
                case when coalesce(v_item.recorrente, false) then 'MENSAL_FIXA' else 'UNICA' end,
                v_d ->> 'observacoes', now() at time zone 'utc')
        returning id into v_id;
        v_ids := v_ids || v_id;
    end if;

    v_resultado := jsonb_build_object('item_receita_id', v_item_id, 'previsoes', to_jsonb(v_ids),
                                      'competencia', v_comp, 'recorrente', v_rec);
    insert into financeiro.operacao_receita (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_receita', v_resultado);
    return v_resultado;
end
$$;

-- Trava a previsao (e a tabela de recebimentos em modo SHARE) e confere perfil, bloqueio e versao. Interna.
create function financeiro.travar_previsao(p_perfil_id integer, p_orcamento_id integer, p_versao text)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_orc      public.receita_orcamento;
    v_bloqueio text;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    -- Um recebimento do Flask em andamento termina antes (e passa a bloquear); um novo espera.
    lock table public.receita_realizada in share mode;
    perform pg_advisory_xact_lock(20261027, p_perfil_id);
    select * into v_orc from public.receita_orcamento where id = p_orcamento_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_orc.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Receita nao encontrada neste perfil' using errcode = '42501';
    end if;
    perform 1 from public.item_receita where id = v_orc.item_receita_id for update;
    v_bloqueio := financeiro.bloqueio_da_previsao(p_orcamento_id);
    if v_bloqueio is not null then
        raise exception 'Operacao bloqueada: %', v_bloqueio using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    if p_versao is null or p_versao is distinct from financeiro.versao_previsao(p_orcamento_id) then
        raise exception 'A receita foi alterada por outra operacao. Recarregue e tente de novo.'
            using errcode = 'P0001', hint = 'VERSAO';
    end if;
end
$$;

-- Edicao de uma previsao sem recebimento: valor, observacoes e (fonte avulsa) competencia.
create function financeiro.editar_receita(p_perfil_id integer, p_orcamento_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_orc  public.receita_orcamento;
    v_item public.item_receita;
    v_d    jsonb;
    v_comp date;
begin
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
    update public.receita_orcamento o
       set valor_esperado = coalesce((v_d ->> 'valor')::numeric, o.valor_esperado),
           observacoes = case when v_d ? 'observacoes' then v_d ->> 'observacoes' else o.observacoes end,
           mes_referencia = v_comp
     where o.id = p_orcamento_id;
    return jsonb_build_object('orcamento_id', p_orcamento_id, 'competencia', v_comp,
                              'versao', financeiro.versao_previsao(p_orcamento_id));
end
$$;

-- Exclusao segura de uma previsao sem recebimento. Fonte recorrente: zera a previsao com a mesma
-- marca do Flask ("Removido pelo usuario"), para a tela do Flask nao reexibi-la pelo valor base da
-- fonte. Fonte avulsa: apaga a previsao e, sem outras referencias, a propria fonte (sem orfaos).
create function financeiro.excluir_receita(p_perfil_id integer, p_orcamento_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_orc          public.receita_orcamento;
    v_item         public.item_receita;
    v_fonte_apagada boolean := false;
begin
    perform financeiro.travar_previsao(p_perfil_id, p_orcamento_id, p_versao);
    select * into v_orc from public.receita_orcamento where id = p_orcamento_id;
    select * into v_item from public.item_receita where id = v_orc.item_receita_id;
    if coalesce(v_item.recorrente, true) then
        update public.receita_orcamento set valor_esperado = 0, observacoes = 'Removido pelo usuário' where id = p_orcamento_id;
        return jsonb_build_object('orcamento_id', p_orcamento_id, 'modo', 'ZERADA', 'fonte_excluida', false);
    end if;
    delete from public.receita_orcamento where id = p_orcamento_id;
    if not exists (select 1 from public.receita_orcamento o where o.item_receita_id = v_item.id)
       and not exists (select 1 from public.receita_realizada r where r.item_receita_id = v_item.id) then
        begin
            delete from public.item_receita where id = v_item.id;
            v_fonte_apagada := true;
        exception when foreign_key_violation then
            v_fonte_apagada := false;
        end;
    end if;
    return jsonb_build_object('orcamento_id', p_orcamento_id, 'modo', 'EXCLUIDA', 'fonte_excluida', v_fonte_apagada);
end
$$;

-- Trava a fonte e confere perfil, modulo e versao. Interna.
create function financeiro.travar_fonte(p_perfil_id integer, p_item_id integer, p_versao text)
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
    perform pg_advisory_xact_lock(20261027, p_perfil_id);
    perform 1 from public.item_receita i
      where i.id = p_item_id and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) for update;
    if not found then
        raise exception 'Fonte de receita nao encontrada neste perfil' using errcode = '42501';
    end if;
    if financeiro.fonte_de_outro_modulo(p_item_id) then
        raise exception 'Operacao bloqueada: Gerada pelo modulo de consorcios' using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    if p_versao is null or p_versao is distinct from financeiro.versao_fonte(p_item_id) then
        raise exception 'A fonte foi alterada por outra operacao. Recarregue e tente de novo.'
            using errcode = 'P0001', hint = 'VERSAO';
    end if;
end
$$;

-- Edicao da fonte: nome, categoria (tipo), dia previsto, conta de destino e descricao.
-- Nao altera previsoes nem recebimentos ja registrados.
create function financeiro.editar_fonte_receita(p_perfil_id integer, p_item_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d jsonb;
begin
    perform financeiro.travar_fonte(p_perfil_id, p_item_id, p_versao);
    v_d := financeiro.ler_dados_receita(p_dados - 'valor' - 'competencia' - 'observacoes', p_perfil_id, true);
    if v_d ? 'nome' and exists (select 1 from public.item_receita i
                                 where i.nome = v_d ->> 'nome' and i.id <> p_item_id
                                   and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)) then
        raise exception 'Ja existe outra fonte com este nome' using errcode = '22023';
    end if;
    update public.item_receita i
       set nome = coalesce(v_d ->> 'nome', i.nome),
           tipo = coalesce(v_d ->> 'tipo', i.tipo),
           dia_previsto_pagamento = case when v_d ? 'dia_previsto' then (v_d ->> 'dia_previsto')::integer
                                         else i.dia_previsto_pagamento end,
           conta_bancaria_id = case when v_d ? 'conta_bancaria_id' then (v_d ->> 'conta_bancaria_id')::integer
                                    else i.conta_bancaria_id end,
           descricao = case when v_d ? 'descricao' then coalesce(v_d ->> 'descricao', '') else i.descricao end
     where i.id = p_item_id;
    return jsonb_build_object('item_receita_id', p_item_id, 'versao', financeiro.versao_fonte(p_item_id));
end
$$;

-- Inativacao da fonte (o "excluir fonte" do Flask): historico e previsoes ficam; a previsao sem
-- recebimento passa a aparecer como INATIVA.
create function financeiro.inativar_fonte_receita(p_perfil_id integer, p_item_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.travar_fonte(p_perfil_id, p_item_id, p_versao);
    update public.item_receita set ativo = false where id = p_item_id;
    return jsonb_build_object('item_receita_id', p_item_id, 'ativo', false);
end
$$;

revoke execute on function financeiro.receita_estornada(integer) from public, anon, authenticated;
revoke execute on function financeiro.fonte_de_outro_modulo(integer) from public, anon, authenticated;
revoke execute on function financeiro.bloqueio_da_previsao(integer) from public, anon, authenticated;
revoke execute on function financeiro.versao_previsao(integer) from public, anon, authenticated;
revoke execute on function financeiro.versao_fonte(integer) from public, anon, authenticated;
revoke execute on function financeiro.ler_dados_receita(jsonb, integer, boolean) from public, anon, authenticated;
revoke execute on function financeiro.travar_previsao(integer, integer, text) from public, anon, authenticated;
revoke execute on function financeiro.travar_fonte(integer, integer, text) from public, anon, authenticated;
revoke execute on function financeiro.receitas_do_mes(integer, date) from public, anon;
revoke execute on function financeiro.fontes_de_receita(integer) from public, anon;
revoke execute on function financeiro.receita_para_edicao(integer, integer) from public, anon;
revoke execute on function financeiro.criar_receita(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_receita(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.excluir_receita(integer, integer, text) from public, anon;
revoke execute on function financeiro.editar_fonte_receita(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.inativar_fonte_receita(integer, integer, text) from public, anon;
grant execute on function financeiro.receitas_do_mes(integer, date) to authenticated;
grant execute on function financeiro.fontes_de_receita(integer) to authenticated;
grant execute on function financeiro.receita_para_edicao(integer, integer) to authenticated;
grant execute on function financeiro.criar_receita(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_receita(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.excluir_receita(integer, integer, text) to authenticated;
grant execute on function financeiro.editar_fonte_receita(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.inativar_fonte_receita(integer, integer, text) to authenticated;
