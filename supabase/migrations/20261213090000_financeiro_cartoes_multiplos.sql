-- FIN-CARTOES-MULTIPLOS-01 — contratos de cartao com varios cartoes vinculados (fisico, virtual, adicional) e fatura unica.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261213090000). Depende de 20261212090000.
-- Validada em cluster local descartavel (tests/test_supabase_cartoes_multiplos.py) e ensaiada numa copia fiel da producao.
-- Doc: docs/FIN_CARTOES_MULTIPLOS_01.md. Gerada por scripts/gerar_migration_cartoes_multiplos.py.
-- Reversao: supabase/reversao/20261213090000_cartoes_multiplos_anterior.sql (recusada com cartao vinculado cadastrado).
--
-- Menor evolucao: o "cartao" de hoje (public.item_despesa Agregador + config_agregador) e o contrato, com fatura, pagamento
-- e limites unicos. financeiro.cartao_vinculado guarda os cartoes do contrato (4 ultimos digitos, tipo, portador, situacao,
-- substituto); a compra (public.lancamento_agregado.cartao_vinculado_id) e o credito guardam o cartao de origem, null =
-- sem cartao identificado. A importacao reconhece o cartao pelo final do arquivo ou pela escolha na previa (nunca por
-- presuncao) e nao confunde compras identicas de cartoes diferentes. Cartoes mostra a fatura por cartao. Limpeza seletiva
-- das despesas importadas (previa e execucao), so pelo que a importacao registrou como seu. Nenhum dado existente e
-- alterado pela migration (as colunas novas nascem vazias).
--
-- Funcoes existentes substituidas pelo texto vigente com os trechos marcados "FIN-CARTOES-MULTIPLOS-01": analisar_importacao_cartao, importar_fatura_cartao, fatura_por_categoria, lancamentos_fatura_por_categoria (texto de
-- 20261212090000).

-- =====================================================================================================================
-- 1. Cartoes vinculados ao contrato (o "cartao" atual: public.item_despesa tipo Agregador, com a fatura unica)
-- =====================================================================================================================
create table financeiro.cartao_vinculado (
    id                   integer     generated always as identity primary key,
    perfil_financeiro_id integer     not null,
    contrato_id          integer     not null references public.item_despesa (id),
    nome                 text        not null check (length(btrim(nome)) between 1 and 60),
    final                text        not null check (final ~ '^[0-9]{4}$'),
    tipo                 text        not null check (tipo in ('FISICO', 'VIRTUAL', 'ADICIONAL')),
    portador             text        check (portador is null or length(portador) <= 80),
    situacao             text        not null default 'ATIVO' check (situacao in ('ATIVO', 'CANCELADO', 'SUBSTITUIDO')),
    data_inicio          date,
    data_cancelamento    date,
    substituto_id        integer     references financeiro.cartao_vinculado (id),
    user_id              uuid        references auth.users (id) on delete set null,
    criado_em            timestamptz not null default now(),
    atualizado_em        timestamptz,
    unique (contrato_id, final),
    check (substituto_id is null or substituto_id <> id),
    check (situacao <> 'SUBSTITUIDO' or substituto_id is not null),
    check (data_cancelamento is null or data_inicio is null or data_cancelamento >= data_inicio)
);
comment on table financeiro.cartao_vinculado is
    'FIN-CARTOES-MULTIPLOS-01: cartao fisico, virtual ou adicional de um contrato de cartao (item_despesa Agregador), que continua com a fatura e o pagamento unicos. So os 4 ultimos digitos; nunca numero completo, validade ou CVV.';
alter table financeiro.cartao_vinculado enable row level security;
alter table financeiro.cartao_vinculado force row level security;
revoke all on financeiro.cartao_vinculado from public, anon, authenticated;

-- A compra e o credito guardam o cartao de origem (null = sem cartao identificado).
alter table public.lancamento_agregado add column cartao_vinculado_id integer references financeiro.cartao_vinculado (id);
create index lancamento_agregado_cartao_vinculado on public.lancamento_agregado (cartao_vinculado_id)
    where cartao_vinculado_id is not null;
alter table financeiro.credito_fatura add column cartao_vinculado_id integer references financeiro.cartao_vinculado (id);

-- Nenhuma referencia cruzada: o cartao vinculado e do perfil do contrato; o substituto, do mesmo contrato; a compra e o
-- credito, so de um cartao do proprio contrato.
create function financeiro.conferir_cartao_vinculado()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    if not exists (select 1 from public.item_despesa i where i.id = new.contrato_id and i.tipo = 'Agregador'
                      and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, new.perfil_financeiro_id)) then
        raise exception 'Contrato de cartao de outro perfil' using errcode = '23514';
    end if;
    if new.substituto_id is not null and not exists (select 1 from financeiro.cartao_vinculado v
                                                      where v.id = new.substituto_id and v.contrato_id = new.contrato_id) then
        raise exception 'O cartao substituto deve ser do mesmo contrato' using errcode = '23514';
    end if;
    return new;
end
$$;
create trigger cartao_vinculado_conferir before insert or update on financeiro.cartao_vinculado
    for each row execute function financeiro.conferir_cartao_vinculado();

create function financeiro.conferir_cartao_da_compra()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    if new.cartao_vinculado_id is not null and not exists (select 1 from financeiro.cartao_vinculado v
                                                            where v.id = new.cartao_vinculado_id and v.contrato_id = new.cartao_id) then
        raise exception 'O cartao de origem nao e deste contrato' using errcode = '23514';
    end if;
    return new;
end
$$;
create trigger lancamento_cartao_vinculado before insert or update of cartao_vinculado_id, cartao_id on public.lancamento_agregado
    for each row execute function financeiro.conferir_cartao_da_compra();
create trigger credito_cartao_vinculado before insert or update of cartao_vinculado_id, cartao_id on financeiro.credito_fatura
    for each row execute function financeiro.conferir_cartao_da_compra();
revoke execute on function financeiro.conferir_cartao_vinculado() from public, anon, authenticated;
revoke execute on function financeiro.conferir_cartao_da_compra() from public, anon, authenticated;

-- Cartoes vinculados de um contrato (com o uso: compras e creditos de origem), para a tela de Cartoes.
create function financeiro.cartoes_vinculados(p_perfil_id integer, p_contrato_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_contrato_id, false);
    return coalesce((
        select jsonb_agg(jsonb_build_object(
                   'id', v.id, 'nome', v.nome, 'final', v.final, 'tipo', v.tipo, 'portador', v.portador,
                   'situacao', v.situacao, 'data_inicio', v.data_inicio, 'data_cancelamento', v.data_cancelamento,
                   'substituto', (select jsonb_build_object('id', s.id, 'final', s.final, 'nome', s.nome)
                                    from financeiro.cartao_vinculado s where s.id = v.substituto_id),
                   'compras', (select count(*) from public.lancamento_agregado l where l.cartao_vinculado_id = v.id),
                   'creditos', (select count(*) from financeiro.credito_fatura cf where cf.cartao_vinculado_id = v.id),
                   'versao', md5(v::text))
               order by v.situacao <> 'ATIVO', v.tipo, v.final)
          from financeiro.cartao_vinculado v
         where v.contrato_id = p_contrato_id), '[]'::jsonb);
end
$$;

-- Cadastro (p_cartao_vinculado_id null) ou edicao (com a versao lida) de um cartao vinculado. O cartao nunca e excluido:
-- cancelado ou substituido, continua no historico (as compras de origem nao mudam). O final so muda sem compra de origem.
create function financeiro.salvar_cartao_vinculado(p_perfil_id integer, p_contrato_id integer, p_cartao_vinculado_id integer,
                                                   p_dados jsonb, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_atual   financeiro.cartao_vinculado;
    v_nome    text;
    v_final   text;
    v_tipo    text;
    v_port    text;
    v_sit     text;
    v_ini     date;
    v_canc    date;
    v_subst   integer;
    v_id      integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_contrato_id, false);
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do cartao invalidos' using errcode = '22023';
    end if;
    if p_dados ?| array['numero_cartao', 'numero', 'codigo_seguranca', 'cvv', 'data_validade', 'validade'] then
        raise exception 'Numero completo, validade e codigo de seguranca nao sao guardados: informe so os 4 ultimos digitos'
            using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava das compras e da importacao do perfil
    perform 1 from public.item_despesa where id = p_contrato_id for update;
    if p_cartao_vinculado_id is not null then
        select * into v_atual from financeiro.cartao_vinculado v where v.id = p_cartao_vinculado_id and v.contrato_id = p_contrato_id
           for update;
        if not found then
            raise exception 'Cartao vinculado nao encontrado neste contrato' using errcode = '42501';
        end if;
        if p_versao is distinct from md5(v_atual::text) then
            raise exception 'O cartao foi alterado por outra operacao: recarregue a tela' using errcode = '40001';
        end if;
    end if;
    v_nome := btrim(coalesce(p_dados ->> 'nome', v_atual.nome, ''));
    v_final := regexp_replace(coalesce(p_dados ->> 'final', v_atual.final, ''), '\s', '', 'g');
    v_tipo := upper(btrim(coalesce(p_dados ->> 'tipo', v_atual.tipo, '')));
    v_port := nullif(btrim(coalesce(p_dados ->> 'portador', v_atual.portador, '')), '');
    v_sit := upper(btrim(coalesce(p_dados ->> 'situacao', v_atual.situacao, 'ATIVO')));
    begin
        v_ini := case when p_dados ? 'data_inicio' then nullif(p_dados ->> 'data_inicio', '')::date else v_atual.data_inicio end;
        v_canc := case when p_dados ? 'data_cancelamento' then nullif(p_dados ->> 'data_cancelamento', '')::date else v_atual.data_cancelamento end;
        v_subst := case when p_dados ? 'substituto_id' then nullif(p_dados ->> 'substituto_id', '')::integer else v_atual.substituto_id end;
    exception when others then
        raise exception 'Data ou cartao substituto invalido' using errcode = '22023';
    end;
    if v_nome = '' or length(v_nome) > 60 then
        raise exception 'Nome do cartao obrigatorio (ate 60 caracteres)' using errcode = '22023';
    end if;
    if v_final !~ '^[0-9]{4}$' then
        raise exception 'Informe os 4 ultimos digitos do cartao' using errcode = '22023';
    end if;
    if v_tipo not in ('FISICO', 'VIRTUAL', 'ADICIONAL') then
        raise exception 'Tipo do cartao: fisico, virtual ou adicional' using errcode = '22023';
    end if;
    if v_sit not in ('ATIVO', 'CANCELADO', 'SUBSTITUIDO') then
        raise exception 'Situacao do cartao: ativo, cancelado ou substituido' using errcode = '22023';
    end if;
    if v_sit = 'SUBSTITUIDO' and v_subst is null then
        raise exception 'Informe o cartao substituto' using errcode = '22023';
    end if;
    if v_sit = 'ATIVO' then
        v_canc := null;
    end if;
    if v_atual.id is not null and v_final <> v_atual.final
       and (exists (select 1 from public.lancamento_agregado l where l.cartao_vinculado_id = v_atual.id)
            or exists (select 1 from financeiro.credito_fatura cf where cf.cartao_vinculado_id = v_atual.id)) then
        raise exception 'O final de um cartao com compras nao muda (o historico seria outro cartao): cadastre o novo cartao'
            using errcode = '22023';
    end if;
    if exists (select 1 from financeiro.cartao_vinculado v where v.contrato_id = p_contrato_id and v.final = v_final
                  and v.id is distinct from v_atual.id) then
        raise exception 'Ja ha um cartao final % neste contrato', v_final using errcode = '23505';
    end if;
    if v_atual.id is null then
        insert into financeiro.cartao_vinculado (perfil_financeiro_id, contrato_id, nome, final, tipo, portador, situacao,
                                                 data_inicio, data_cancelamento, substituto_id, user_id)
        values (p_perfil_id, p_contrato_id, v_nome, v_final, v_tipo, v_port, v_sit, v_ini, v_canc, v_subst, (select auth.uid()))
        returning id into v_id;
    else
        update financeiro.cartao_vinculado
           set nome = v_nome, final = v_final, tipo = v_tipo, portador = v_port, situacao = v_sit, data_inicio = v_ini,
               data_cancelamento = v_canc, substituto_id = v_subst, atualizado_em = now()
         where id = v_atual.id
        returning id into v_id;
    end if;
    return (select c from jsonb_array_elements(financeiro.cartoes_vinculados(p_perfil_id, p_contrato_id)) c
             where (c ->> 'id')::integer = v_id);
end
$$;

-- A fatura unica do contrato por cartao vinculado (executado das compras e creditos de cada um); o que nao tem cartao
-- identificado fica numa linha propria. A soma das linhas e o valor a pagar da fatura.
create function financeiro.fatura_por_cartao(p_perfil_id integer, p_contrato_id integer, p_mes date)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with compras as (
        select l.cartao_vinculado_id as cv,
               financeiro.valor_executado_compra(l.valor, financeiro.situacao_previsao(l.id,
                   financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id),
                   l.is_importado, l.cartao_id, l.mes_fatura)) as valor
          from public.lancamento_agregado l
         where l.cartao_id = p_contrato_id and l.mes_fatura = date_trunc('month', p_mes::timestamp)::date
           and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
    ),
    creditos as (
        select cf.cartao_vinculado_id as cv, cf.valor
          from financeiro.credito_fatura cf
         where cf.fatura_id = financeiro.fatura_do_mes(p_contrato_id, date_trunc('month', p_mes::timestamp)::date)
    ),
    linhas as (
        select v.id, v.nome, v.final, v.tipo, v.portador, v.situacao,
               coalesce((select sum(c.valor) from compras c where c.cv = v.id), 0) as compras,
               (select count(*) from compras c where c.cv = v.id and c.valor > 0) as quantidade,
               coalesce((select sum(c.valor) from creditos c where c.cv = v.id), 0) as creditos
          from financeiro.cartao_vinculado v where v.contrato_id = p_contrato_id
        union all
        select null, 'Sem cartao identificado', null, null, null, null,
               coalesce((select sum(c.valor) from compras c where c.cv is null), 0),
               (select count(*) from compras c where c.cv is null and c.valor > 0),
               coalesce((select sum(c.valor) from creditos c where c.cv is null), 0)
    )
    select coalesce(jsonb_agg(jsonb_build_object('cartao_vinculado_id', x.id, 'nome', x.nome, 'final', x.final, 'tipo', x.tipo,
                                                 'portador', x.portador, 'situacao', x.situacao, 'compras', x.compras,
                                                 'creditos', x.creditos, 'total', x.compras - x.creditos, 'quantidade', x.quantidade)
                              order by x.id is null, x.situacao <> 'ATIVO', x.final), '[]'::jsonb)
      from linhas x
     where x.id is not null or x.compras <> 0 or x.creditos <> 0
$$;
revoke execute on function financeiro.fatura_por_cartao(integer, integer, date) from public, anon, authenticated;

-- =====================================================================================================================
-- 2. Limpeza seletiva das despesas importadas (para a reconstrucao das faturas): previa e execucao
-- =====================================================================================================================
-- Elegivel: so o que a importacao registrou como seu (financeiro.operacao_cartao 'importar_fatura': as compras inseridas em
-- 'lancamentos' e os creditos em 'creditos_ids'), ainda marcado como importado. Compra importada sem essa evidencia (Flask,
-- versao anterior) e "origem nao comprovada": nunca entra. Protegidos (interrompem a execucao): fatura paga ou consolidada,
-- previsao de recorrencia realizada ou conciliada ainda vigente, credito de fora da selecao vinculado. Nada e alterado.
create function financeiro.previa_limpeza_importacoes(p_perfil_id integer, p_cartao_id integer, p_competencia date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes date := date_trunc('month', p_competencia::timestamp)::date;
    v_r   jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_cartao_id is not null then
        perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    end if;
    with ops as (
        select o.chave, o.criado_em, o.resultado from financeiro.operacao_cartao o
         where o.operacao = 'importar_fatura' and o.perfil_financeiro_id = p_perfil_id
    ),
    evid as (
        select distinct on (x.id) x.id, x.chave, x.criado_em from (
            select (e.v)::integer as id, o.chave, o.criado_em from ops o
             cross join lateral jsonb_array_elements_text(case when jsonb_typeof(o.resultado -> 'lancamentos') = 'array'
                                                               then o.resultado -> 'lancamentos' else '[]'::jsonb end) e(v)) x
         order by x.id, x.criado_em
    ),
    escopo as (
        select l.* from public.lancamento_agregado l
         where financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
           and (p_cartao_id is null or l.cartao_id = p_cartao_id)
           and (v_mes is null or coalesce(l.mes_fatura_original, l.mes_fatura) = v_mes)
    ),
    compras as (
        select l.id, l.cartao_id, l.mes_fatura, coalesce(l.descricao_exibida, l.descricao) as descricao, l.valor, l.data_compra,
               l.numero_parcela, l.total_parcelas, l.cartao_vinculado_id, e.chave,
               case
                   when not coalesce(l.is_importado, false) then 'Sem a marca de importacao'
                   when financeiro.fatura_esta_paga(financeiro.fatura_do_mes(l.cartao_id, l.mes_fatura)) then 'Fatura paga'
                   when exists (select 1 from public.conta c where c.id = financeiro.fatura_do_mes(l.cartao_id, l.mes_fatura)
                                   and c.status_fatura = 'FECHADA') then 'Fatura consolidada'
                   when exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                 where o.lancamento_id = l.id and o.revertida_em is null) then 'Ocorrencia de recorrencia vigente'
               end as protecao
          from escopo l join evid e on e.id = l.id
    ),
    ops_cred as (
        select (e.v)::bigint as id from ops o
         cross join lateral jsonb_array_elements_text(case when jsonb_typeof(o.resultado -> 'creditos_ids') = 'array'
                                                           then o.resultado -> 'creditos_ids' else '[]'::jsonb end) e(v)
    ),
    creditos as (
        select cf.id, cf.cartao_id, cf.mes_fatura, cf.descricao, cf.valor, cf.data_credito, cf.natureza, cf.lancamento_id,
               cf.cartao_vinculado_id,
               case when financeiro.fatura_esta_paga(cf.fatura_id) then 'Fatura paga'
                    when exists (select 1 from public.conta c where c.id = cf.fatura_id and c.status_fatura = 'FECHADA')
                        then 'Fatura consolidada' end as protecao
          from financeiro.credito_fatura cf
         where financeiro.pertence_ao_perfil(cf.perfil_financeiro_id, p_perfil_id)
           and (p_cartao_id is null or cf.cartao_id = p_cartao_id)
           and (v_mes is null or coalesce(cf.mes_fatura_original, cf.mes_fatura) = v_mes)
           and (cf.id in (select id from ops_cred) or cf.operacao_chave in (select chave from ops))
    ),
    -- credito de fora da selecao vinculado a uma compra da selecao: a compra fica protegida
    compras2 as (
        select c.*, coalesce(c.protecao, case when exists (select 1 from financeiro.credito_fatura cf
                                                            where cf.lancamento_id = c.id
                                                              and cf.id not in (select id from creditos)) then
                                                   'Credito de outra importacao vinculado' end) as protecao2
          from compras c
    ),
    nao_comprovadas as (
        select l.id, l.cartao_id, l.mes_fatura, coalesce(l.descricao_exibida, l.descricao) as descricao, l.valor,
               l.origem_importacao
          from escopo l where coalesce(l.is_importado, false) and l.id not in (select id from evid)
    )
    select jsonb_build_object(
        'filtro', jsonb_build_object('cartao_id', p_cartao_id, 'competencia', v_mes),
        'compras_elegiveis', coalesce((select jsonb_agg(jsonb_build_object('id', c.id, 'cartao_id', c.cartao_id,
                'mes_fatura', c.mes_fatura, 'descricao', c.descricao, 'valor', c.valor, 'data_compra', c.data_compra,
                'parcela', c.numero_parcela || '/' || c.total_parcelas, 'cartao_vinculado_id', c.cartao_vinculado_id,
                'operacao', c.chave) order by c.cartao_id, c.mes_fatura, c.id) from compras2 c where c.protecao2 is null), '[]'::jsonb),
        'creditos_elegiveis', coalesce((select jsonb_agg(jsonb_build_object('id', c.id, 'cartao_id', c.cartao_id,
                'mes_fatura', c.mes_fatura, 'descricao', c.descricao, 'valor', c.valor, 'natureza', c.natureza,
                'lancamento_id', c.lancamento_id) order by c.cartao_id, c.mes_fatura, c.id)
                from creditos c where c.protecao is null), '[]'::jsonb),
        'protegidos', coalesce((select jsonb_agg(x order by x ->> 'tipo', (x ->> 'id')::bigint) from (
                select jsonb_build_object('tipo', 'compra', 'id', c.id, 'cartao_id', c.cartao_id, 'mes_fatura', c.mes_fatura,
                                          'descricao', c.descricao, 'valor', c.valor, 'motivo', c.protecao2) x
                  from compras2 c where c.protecao2 is not null
                union all
                select jsonb_build_object('tipo', 'credito', 'id', c.id, 'cartao_id', c.cartao_id, 'mes_fatura', c.mes_fatura,
                                          'descricao', c.descricao, 'valor', c.valor, 'motivo', c.protecao)
                  from creditos c where c.protecao is not null) y), '[]'::jsonb),
        'nao_comprovadas', coalesce((select jsonb_agg(jsonb_build_object('id', n.id, 'cartao_id', n.cartao_id,
                'mes_fatura', n.mes_fatura, 'descricao', n.descricao, 'valor', n.valor, 'origem_importacao', n.origem_importacao,
                'motivo', 'Origem da importacao nao comprovada (sem registro da operacao): fora da limpeza')
                order by n.cartao_id, n.mes_fatura, n.id) from nao_comprovadas n), '[]'::jsonb),
        'por_fatura', coalesce((select jsonb_agg(jsonb_build_object(
                'cartao_id', f.cartao_id, 'mes_fatura', f.mes_fatura, 'compras', f.compras, 'total_compras', f.total_compras,
                'creditos', f.creditos, 'total_creditos', f.total_creditos,
                'valor_a_pagar_atual', financeiro.executado_fatura(financeiro.fatura_do_mes(f.cartao_id, f.mes_fatura)),
                'valor_a_pagar_depois', financeiro.executado_fatura(financeiro.fatura_do_mes(f.cartao_id, f.mes_fatura))
                                        - f.executado_compras + f.total_creditos,
                'previsoes_pendentes', (select count(*) from public.lancamento_agregado p
                                         where p.cartao_id = f.cartao_id and p.mes_fatura = f.mes_fatura
                                           and financeiro.situacao_previsao(p.id, financeiro.natureza_da_compra(p.total_parcelas,
                                               p.is_recorrente, p.item_despesa_id, p.categoria_cartao_id), p.is_importado,
                                               p.cartao_id, p.mes_fatura) = 'PREVISTA'))
                order by f.cartao_id, f.mes_fatura)
              from (select z.cartao_id, z.mes_fatura, sum(z.n_compra) as compras, sum(z.v_compra) as total_compras,
                           sum(z.e_compra) as executado_compras, sum(z.n_cred) as creditos, sum(z.v_cred) as total_creditos
                      from (select c.cartao_id, c.mes_fatura, 1 as n_compra, c.valor as v_compra,
                                   c.valor as e_compra, 0 as n_cred, 0 as v_cred
                              from compras2 c where c.protecao2 is null
                            union all
                            select c.cartao_id, c.mes_fatura, 0, 0, 0, 1, c.valor from creditos c where c.protecao is null) z
                     group by z.cartao_id, z.mes_fatura) f), '[]'::jsonb))
      into v_r;
    v_r := v_r || jsonb_build_object(
        'totais', jsonb_build_object(
            'compras_elegiveis', jsonb_array_length(v_r -> 'compras_elegiveis'),
            'valor_compras', coalesce((select sum((x ->> 'valor')::numeric) from jsonb_array_elements(v_r -> 'compras_elegiveis') x), 0),
            'creditos_elegiveis', jsonb_array_length(v_r -> 'creditos_elegiveis'),
            'valor_creditos', coalesce((select sum((x ->> 'valor')::numeric) from jsonb_array_elements(v_r -> 'creditos_elegiveis') x), 0),
            'protegidos', jsonb_array_length(v_r -> 'protegidos'),
            'nao_comprovadas', jsonb_array_length(v_r -> 'nao_comprovadas')),
        'executavel', jsonb_array_length(v_r -> 'protegidos') = 0
                      and (jsonb_array_length(v_r -> 'compras_elegiveis') + jsonb_array_length(v_r -> 'creditos_elegiveis')) > 0,
        'hash', md5(coalesce((select string_agg('c' || (x ->> 'id'), ',' order by (x ->> 'id')::integer)
                                from jsonb_array_elements(v_r -> 'compras_elegiveis') x), '') || '|'
                    || coalesce((select string_agg('k' || (x ->> 'id'), ',' order by (x ->> 'id')::bigint)
                                   from jsonb_array_elements(v_r -> 'creditos_elegiveis') x), '')));
    return v_r;
end
$$;

-- Execucao (so o perfil Pessoal, pelo titular): refaz a previa sob as travas, confere a impressao (hash) que o usuario
-- conferiu e recusa com protegido. Remove os creditos e as compras elegiveis numa transacao, recalcula as faturas e guarda
-- as linhas removidas inteiras na operacao (auditoria). Idempotente pela chave. Movimentos, saldos, pagamentos, faturas,
-- recorrencias e previsoes nao sao tocados.
create function financeiro.limpar_importacoes_cartao(p_perfil_id integer, p_cartao_id integer, p_competencia date,
                                                     p_hash text, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_cartao;
    v_previa   jsonb;
    v_compras  integer[];
    v_creditos bigint[];
    v_fotos_c  jsonb;
    v_fotos_k  jsonb;
    v_meses    record;
    v_res      jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if not exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal') then
        raise exception 'A limpeza das importacoes e so do perfil Pessoal' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261213));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return (v_anterior.resultado - 'fotos') || jsonb_build_object('repetida', true);
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava das compras e da importacao do perfil
    perform 1 from public.item_despesa i where i.tipo = 'Agregador' and (p_cartao_id is null or i.id = p_cartao_id)
                                           and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) for update;
    v_previa := financeiro.previa_limpeza_importacoes(p_perfil_id, p_cartao_id, p_competencia);
    if p_hash is distinct from v_previa ->> 'hash' then
        raise exception 'A previa da limpeza mudou desde a conferencia: confira de novo' using errcode = '40001';
    end if;
    if jsonb_array_length(v_previa -> 'protegidos') > 0 then
        raise exception 'Limpeza interrompida: % registro(s) importado(s) protegido(s) (fatura paga ou consolidada, ocorrencia de recorrencia, credito vinculado). Nada foi removido.',
            jsonb_array_length(v_previa -> 'protegidos') using errcode = 'P0001';
    end if;
    select coalesce(array_agg((x ->> 'id')::integer), '{}') into v_compras from jsonb_array_elements(v_previa -> 'compras_elegiveis') x;
    select coalesce(array_agg((x ->> 'id')::bigint), '{}') into v_creditos from jsonb_array_elements(v_previa -> 'creditos_elegiveis') x;
    if cardinality(v_compras) + cardinality(v_creditos) = 0 then
        raise exception 'Nada a limpar nesta selecao' using errcode = '22023';
    end if;
    select coalesce(jsonb_agg(to_jsonb(l) order by l.id), '[]'::jsonb) into v_fotos_c from public.lancamento_agregado l where l.id = any(v_compras);
    select coalesce(jsonb_agg(to_jsonb(cf) order by cf.id), '[]'::jsonb) into v_fotos_k from financeiro.credito_fatura cf where cf.id = any(v_creditos);
    delete from financeiro.credito_fatura where id = any(v_creditos);
    delete from public.lancamento_agregado where id = any(v_compras);
    for v_meses in
        select distinct (x ->> 'cartao_id')::integer as cartao, (x ->> 'mes_fatura')::date as mes
          from (select jsonb_array_elements(v_fotos_c) x union all select jsonb_array_elements(v_fotos_k)) y
    loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_meses.cartao, v_meses.mes);
    end loop;
    v_res := jsonb_build_object('compras_removidas', cardinality(v_compras), 'creditos_removidos', cardinality(v_creditos),
                                'valor_compras', v_previa -> 'totais' -> 'valor_compras',
                                'valor_creditos', v_previa -> 'totais' -> 'valor_creditos',
                                'por_fatura', v_previa -> 'por_fatura', 'filtro', v_previa -> 'filtro', 'hash', p_hash);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'limpar_importacoes',
            v_res || jsonb_build_object('fotos', jsonb_build_object('compras', v_fotos_c, 'creditos', v_fotos_k)));
    return v_res;
end
$$;

-- =====================================================================================================================
-- 3. Previa, confirmacao e leituras de Cartoes: texto vigente + os trechos marcados
-- =====================================================================================================================

-- analisar_importacao_cartao: texto de 20261212090000 + os trechos marcados.
create or replace function financeiro.analisar_importacao_cartao(p_perfil_id integer, p_cartao_id integer, p_competencia date,
                                                      p_linhas jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_cartao    public.item_despesa;
    v_comp      date := date_trunc('month', p_competencia::timestamp)::date;
    v_l         jsonb;
    v_idx       bigint;
    v_saida     jsonb := '[]'::jsonb;
    v_msgs      jsonb;
    v_status    text;
    v_ignorar   boolean;
    v_data      date;
    v_valor     numeric;
    v_parc      integer;
    v_total     integer;
    v_norm      text;
    v_chave     text;
    v_chaves    text[] := '{}';
    v_usados    integer[] := '{}';
    v_dup       text;
    v_cat       integer;
    v_sug       jsonb;
    v_cc        integer;
    v_cc_res    integer;
    v_vinc      boolean;
    v_cc_origem text;
    v_class     text;
    v_conc      jsonb;
    v_conc_id   integer;
    v_manter    boolean;
    v_rec       integer;
    v_tipo      text;
    v_cat_origem text;
    v_bruto     numeric;
    v_credito   text;
    v_cands     jsonb;    -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencias do cartao que combinam com a descricao
    v_desempate jsonb;
    v_texto     text;
    v_rec_cat   integer;
    v_rec_nome  text;
    v_realiza   integer;  -- compra prevista que esta linha realiza
    v_prev      numeric;
    v_occ       public.lancamento_agregado;
    v_fat_occ   integer;
    v_escolha   integer;            -- FIN-CARTAO-IMPORTACAO-FIXAS-01: recorrencia escolhida na previa (0 = compra comum)
    v_usadas    integer[] := '{}';  -- previsoes ja atribuidas a uma linha deste arquivo
    v_novas     integer[] := '{}';  -- recorrencias que ganham ocorrencia nova neste arquivo
    v_existente integer;            -- compra ja lancada que e esta linha (duplicada ou conciliada pelo valor)
    v_sug_conc  jsonb;
    v_fixa      jsonb;
    v_classe    text;
    v_apelido   text;
    v_prev_sug  public.lancamento_agregado;
    v_rev_nat   boolean;  -- FIN-CARTAO-NUBANK-PARCELADAS-01: revisao pela natureza da linha (nao so pela categoria pendente)
    v_amb       jsonb;    -- numero no texto que pode ser parcela, fora do padrao do arquivo
    v_amb_parc  integer;
    v_amb_total integer;
    v_amb_res   text;     -- decisao do usuario na previa: PARCELADA ou AVISTA
    v_cred      jsonb;            -- FIN-CARTAO-NUBANK-CREDITOS-01: credito da fatura (natureza, compra original, candidatas)
    v_cred_nat  text;
    v_alvo      text;             -- texto da compra no credito ("IOF de volta de Cloudflare" -> cloudflare)
    v_cred_cands jsonb;
    v_cred_esc  integer;
    v_cred_compra integer;
    v_cred_usados integer[] := '{}';  -- compras ja vinculadas a um credito deste arquivo
    v_cv        integer;  -- FIN-CARTOES-MULTIPLOS-01: cartao vinculado de origem (null = sem cartao identificado)
    v_cv_origem text;     -- ARQUIVO (final do arquivo) ou ESCOLHA (do usuario na previa)
    v_cv_esc    integer;
    v_final     text;     -- final do cartao informado no arquivo
    v_cv_lote   text;     -- o cartao na chave da duplicidade no proprio arquivo
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_cartao := financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, true);
    if p_competencia is null then
        raise exception 'competencia obrigatoria' using errcode = '22023';
    end if;
    if p_linhas is null or jsonb_typeof(p_linhas) <> 'array' then
        raise exception 'Linhas da importacao invalidas' using errcode = '22023';
    end if;
    if jsonb_array_length(p_linhas) > 2000 then
        raise exception 'Arquivo com mais de 2000 linhas: divida a importacao' using errcode = '22023';
    end if;

    for v_l, v_idx in select e, o from jsonb_array_elements(p_linhas) with ordinality as x(e, o) loop
        if jsonb_typeof(v_l) <> 'object' then
            raise exception 'Linha % invalida', v_idx using errcode = '22023';
        end if;
        v_msgs := '[]'::jsonb;
        v_status := 'valido';
        v_ignorar := coalesce((v_l ->> 'ignorar')::boolean, false);
        v_dup := null;
        v_rec := null;
        v_conc := null;
        v_conc_id := null;
        v_existente := null;
        v_sug_conc := null;
        v_fixa := null;
        v_apelido := null;
        v_escolha := null;
        v_rev_nat := false;
        v_amb := null;
        v_amb_res := null;
        v_cred := null;
        v_cred_compra := null;
        v_cred_cands := '[]'::jsonb;
        v_cv := null;
        v_cv_origem := null;
        v_cv_esc := null;
        v_manter := coalesce((v_l ->> 'manter_conciliada')::boolean, false);
        v_tipo := coalesce(nullif(v_l ->> 'tipo_movimento', ''), 'debito');
        begin
            v_data := nullif(v_l ->> 'data_compra', '')::date;
        exception when others then
            v_data := null;
        end;
        begin
            v_bruto := (v_l ->> 'valor')::numeric;
        exception when others then
            v_bruto := null;
        end;
        v_valor := round(abs(v_bruto), 2);
        -- Valor negativo nunca vira compra (o sinal nao e descartado): e credito, qualquer que seja o tipo informado.
        if v_bruto < 0 then
            v_tipo := 'credito';
        end if;
        -- Credito na fatura nao e despesa negativa: pagamento da fatura, estorno de compra e ajuste tem efeitos
        -- diferentes e nenhum entra como compra. FIN-CARTAO-NUBANK-CREDITOS-01: estorno, IOF devolvido e ajuste abatem o valor a pagar
        -- da fatura (credito_fatura); o pagamento recebido nao (e registrado em Despesas, pagar fatura).
        v_credito := case when v_tipo <> 'credito' then null
            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(pagamento|pgto|pag[ .]?fatura|obrigado pelo pag)' then 'pagamento_fatura'
            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(\miof\M.*(de volta|devolv|estorn|reembols)|(estorno|devolu[a-z]*|reembolso) d[eo] iof)' then 'iof_devolvido'
            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(estorno|estornad|devolu|reembolso|cancelamento|chargeback)' then 'estorno'
            else 'credito_ajuste' end;
        begin
            v_parc := coalesce(nullif(v_l ->> 'parcela_atual', '')::integer, 1);
            v_total := coalesce(nullif(v_l ->> 'total_parcelas', '')::integer, 1);
        exception when others then
            v_parc := 0;
            v_total := 0;
        end;
        v_norm := btrim(coalesce(nullif(v_l ->> 'descricao_normalizada', ''), v_l ->> 'descricao_original', ''));
        -- FIN-CARTAO-NUBANK-PARCELADAS-01: numero no texto que pode ser parcela, fora do padrao do arquivo ("MERCADO XYZ 03/10" no
        -- Nubank, que escreve "Loja - Parcela 3/10"): pede a decisao do usuario na previa (natureza_parcela PARCELADA,
        -- com esse numero, ou AVISTA). Nada e inventado: ate a decisao, a linha fica 1/1 e em revisao.
        if jsonb_typeof(v_l -> 'parcela_ambigua') = 'object' and v_tipo <> 'credito' and v_total = 1 then
            begin
                v_amb_parc := (v_l -> 'parcela_ambigua' ->> 'parcela_atual')::integer;
                v_amb_total := (v_l -> 'parcela_ambigua' ->> 'total_parcelas')::integer;
            exception when others then
                v_amb_parc := null;
                v_amb_total := null;
            end;
            if v_amb_parc >= 1 and v_amb_total between 2 and 60 and v_amb_parc <= v_amb_total then
                v_amb := jsonb_build_object('parcela_atual', v_amb_parc, 'total_parcelas', v_amb_total,
                                            'rotulo', lpad(v_amb_parc::text, 2, '0') || '/' || lpad(v_amb_total::text, 2, '0'));
                v_amb_res := upper(nullif(btrim(v_l ->> 'natureza_parcela'), ''));
                if v_amb_res = 'PARCELADA' then
                    v_parc := v_amb_parc;
                    v_total := v_amb_total;
                elsif v_amb_res is distinct from 'AVISTA' then
                    v_amb_res := null;
                end if;
            end if;
        end if;

        -- FIN-CARTOES-MULTIPLOS-01: cartao vinculado de origem (fisico, virtual ou adicional do mesmo contrato): pelo final que o
        -- arquivo informa (cartao_final, lido do PDF) ou pela escolha do usuario (cartao_vinculado_escolhido_id; 0 = sem
        -- cartao identificado). Final ausente ou nao cadastrado: sem cartao identificado, nunca um cartao presumido.
        v_final := right(nullif(regexp_replace(coalesce(v_l ->> 'cartao_final', ''), '[^0-9]', '', 'g'), ''), 4);
        if v_l ? 'cartao_vinculado_escolhido_id' then
            begin
                v_cv_esc := coalesce(nullif(v_l ->> 'cartao_vinculado_escolhido_id', '')::integer, 0);
            exception when others then
                v_cv_esc := -1;
            end;
            v_cv_origem := 'ESCOLHA';
            if v_cv_esc <> 0 then
                select v.id into v_cv from financeiro.cartao_vinculado v where v.id = v_cv_esc and v.contrato_id = p_cartao_id;
                if v_cv is null then
                    v_status := 'revisar';
                    v_rev_nat := true;
                    v_msgs := v_msgs || '"Cartao escolhido nao e deste contrato: escolha outro ou deixe sem cartao identificado."'::jsonb;
                end if;
            end if;
        elsif v_final is not null then
            select v.id into v_cv from financeiro.cartao_vinculado v where v.contrato_id = p_cartao_id and v.final = v_final;
            if v_cv is not null then
                v_cv_origem := 'ARQUIVO';
            else
                v_msgs := v_msgs || to_jsonb(format('Cartao final %s nao cadastrado neste contrato: a linha entra sem cartao identificado (cadastre o cartao em Cartoes ou escolha na previa).', v_final));
            end if;
        end if;
        v_cv_lote := coalesce('c' || v_cv::text, 'f' || v_final, '');

        -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencia do cartao pela descricao. O nome da recorrencia ou um apelido de cobranca
        -- (financeiro.recorrencia_apelido) aparece como palavras inteiras no texto normalizado da linha: mesmo
        -- cartao, recorrencia ativa paga no cartao. O valor nunca identifica; so desempata quando ha mais de uma.
        v_cands := '[]'::jsonb;
        v_rec_cat := null;
        v_rec_nome := null;
        v_realiza := null;
        v_prev := null;
        v_texto := ' ' || financeiro.texto_cobranca(v_norm) || ' ';
        if v_tipo <> 'credito' and btrim(v_texto) <> '' and v_total <= 1 then  -- FIN-CARTAO-NUBANK-PARCELADAS-01: parcela nao e despesa fixa
            select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'nome', i.nome, 'categoria_id', i.categoria_id,
                                                         'valor', i.valor,
                                                         'exato', financeiro.texto_cobranca(i.nome) = btrim(v_texto)
                                                                  or exists (select 1 from financeiro.recorrencia_apelido a
                                                                              where a.item_despesa_id = i.id and a.ativo
                                                                                and a.apelido = btrim(v_texto)))
                                      order by i.id), '[]'::jsonb)
              into v_cands
              from public.item_despesa i
             where coalesce(i.recorrente, false) and i.tipo <> 'Agregador'
               -- FIN-CARTAO-IMPORTACAO-FIXAS-01: inativada, mas com previsao pendente nesta competencia, ainda reconhece a cobranca
               and (coalesce(i.ativo, true) or exists (select 1 from public.lancamento_agregado p
                     where p.item_despesa_id = i.id and p.cartao_id = p_cartao_id and coalesce(p.is_recorrente, false)
                       and coalesce(p.mes_fatura_original, p.mes_fatura) = v_comp and not coalesce(p.is_importado, false)))
               and i.meio_pagamento = 'cartao' and i.cartao_id = p_cartao_id
               and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
               and ((financeiro.texto_cobranca(i.nome) <> ''
                     and position(' ' || financeiro.texto_cobranca(i.nome) || ' ' in v_texto) > 0)
                    or exists (select 1 from financeiro.recorrencia_apelido a
                                where a.item_despesa_id = i.id and a.ativo
                                  and position(' ' || a.apelido || ' ' in v_texto) > 0));
            -- Desempate: a que bate com o texto inteiro; depois, a de valor igual. Persistindo, nenhuma (revisar).
            if jsonb_array_length(v_cands) > 1 then
                select coalesce(jsonb_agg(c), '[]'::jsonb) into v_desempate
                  from jsonb_array_elements(v_cands) c where (c ->> 'exato')::boolean;
                if jsonb_array_length(v_desempate) = 1 then
                    v_cands := v_desempate;
                else
                    select coalesce(jsonb_agg(c), '[]'::jsonb) into v_desempate
                      from jsonb_array_elements(v_cands) c where (c ->> 'valor')::numeric = round(abs(v_bruto), 2);
                    if jsonb_array_length(v_desempate) = 1 then
                        v_cands := v_desempate;
                    end if;
                end if;
            end if;
        end if;
        v_rec := case when jsonb_array_length(v_cands) = 1 then (v_cands -> 0 ->> 'id')::integer end;
        v_rec_cat := (v_cands -> 0 ->> 'categoria_id')::integer;
        v_rec_nome := v_cands -> 0 ->> 'nome';
        -- FIN-CARTAO-IMPORTACAO-FIXAS-01: correcao do usuario na previa (recorrencia_escolhida_id): uma recorrencia deste cartao, ou 0 = compra
        -- comum (nenhuma recorrencia). Prevalece sobre o reconhecimento pela descricao.
        if v_l ? 'recorrencia_escolhida_id' and v_tipo <> 'credito' then
            begin
                v_escolha := coalesce(nullif(v_l ->> 'recorrencia_escolhida_id', '')::integer, 0);
            exception when others then
                v_escolha := -1;
            end;
            if v_escolha = 0 or v_total > 1 then
                v_cands := '[]'::jsonb;
                -- FIN-CARTAO-NUBANK-PARCELADAS-01: parcela de compra parcelada nao vira despesa fixa (Parcelada antes de Fixa)
                if v_escolha <> 0 then
                    v_status := 'revisar';
                    v_rev_nat := true;
                    v_msgs := v_msgs || '"Parcela de compra parcelada nao e despesa fixa: retire a recorrencia escolhida."'::jsonb;
                end if;
            else
                select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'nome', i.nome, 'categoria_id', i.categoria_id,
                                                             'valor', i.valor, 'exato', true)), '[]'::jsonb)
                  into v_cands
                  from public.item_despesa i
                 where i.id = v_escolha and coalesce(i.recorrente, false) and i.tipo <> 'Agregador'
                   and i.meio_pagamento = 'cartao' and i.cartao_id = p_cartao_id
                   and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
                   and (coalesce(i.ativo, true) or exists (select 1 from public.lancamento_agregado p
                         where p.item_despesa_id = i.id and p.cartao_id = p_cartao_id and coalesce(p.is_recorrente, false)
                           and coalesce(p.mes_fatura_original, p.mes_fatura) = v_comp and not coalesce(p.is_importado, false)));
                if jsonb_array_length(v_cands) = 0 then
                    v_status := 'revisar';
                    v_rev_nat := true;
                    v_msgs := v_msgs || '"Recorrencia escolhida nao e deste cartao (ou esta inativa): escolha outra ou trate como compra comum."'::jsonb;
                end if;
            end if;
            v_rec := case when jsonb_array_length(v_cands) = 1 then (v_cands -> 0 ->> 'id')::integer end;
            v_rec_cat := (v_cands -> 0 ->> 'categoria_id')::integer;
            v_rec_nome := v_cands -> 0 ->> 'nome';
        end if;

        -- Validacao (ImportacaoCartaoUnificadoService.validar_linhas)
        if v_tipo = 'credito' and v_credito = 'pagamento_fatura' then
            v_status := 'ignorado';
            v_ignorar := true;
            v_msgs := v_msgs || '"Pagamento da fatura: nao e compra nem credito desta fatura; o pagamento e registrado em Despesas (pagar fatura)."'::jsonb;
        -- FIN-CARTAO-NUBANK-CREDITOS-01: estorno, IOF devolvido e ajuste: credito da fatura (sem Categoria de Despesa), conferido abaixo
        elsif v_tipo = 'credito' and v_valor is not null and v_valor > 0 then
            if v_data is null then
                v_status := 'revisar';
                v_rev_nat := true;
                v_msgs := v_msgs || '"Data do credito ausente."'::jsonb;
            end if;
            if v_norm = '' then
                v_status := 'revisar';
                v_rev_nat := true;
                v_msgs := v_msgs || '"Descricao ausente."'::jsonb;
            end if;
        elsif v_valor is null or v_valor = 0 then
            v_status := 'ignorado';
            v_ignorar := true;
            v_msgs := v_msgs || '"Valor ausente ou zero."'::jsonb;
        else
            if v_data is null then
                v_status := 'revisar';
                v_rev_nat := true;
                v_msgs := v_msgs || '"Data de compra ausente."'::jsonb;
            end if;
            if v_norm = '' then
                v_status := 'revisar';
                v_rev_nat := true;
                v_msgs := v_msgs || '"Descricao ausente."'::jsonb;
            end if;
            if v_parc < 1 or v_total < 1 or v_parc > v_total or v_total > 60 then
                v_status := 'revisar';
                v_rev_nat := true;
                v_msgs := v_msgs || to_jsonb(format('Parcela fora do intervalo: %s/%s', v_parc, v_total));
            end if;
            -- FIN-CARTAO-NUBANK-PARCELADAS-01: parcela possivel no texto, sem a decisao do usuario
            if v_amb is not null and v_amb_res is null then
                v_status := 'revisar';
                v_rev_nat := true;
                v_msgs := v_msgs || to_jsonb(format('Possivel parcela %s no texto, fora do padrao do arquivo: confirme se e compra parcelada (%s) ou a vista.',
                    v_amb ->> 'rotulo', v_amb ->> 'rotulo'));
            end if;
            if v_valor >= 100000000 then
                v_status := 'revisar';
                v_rev_nat := true;
                v_msgs := v_msgs || '"Valor acima do permitido."'::jsonb;
            end if;
        end if;

        -- Categoria de Despesa: a do usuario prevalece; senao, sugestao (palavra-chave, historico, fallback do cartao)
        v_sug := null;
        v_cat := null;
        v_cat_origem := null;
        if v_tipo <> 'credito' then
            if nullif(v_l ->> 'categoria_id', '') is not null then
                begin
                    v_cat := (v_l ->> 'categoria_id')::integer;
                exception when others then
                    v_cat := null;
                end;
                if v_cat is null or not exists (select 1 from public.categoria c where c.id = v_cat and coalesce(c.ativo, true)) then
                    v_cat := null;
                    v_msgs := v_msgs || '"Categoria da despesa inexistente ou inativa."'::jsonb;
                else
                    v_cat_origem := coalesce(nullif(v_l ->> 'categoria_origem', ''), 'manual');
                end if;
            -- FIN-CARTAO-DESPESAS-FIXAS-01: linha reconhecida como a recorrencia usa a Categoria de Despesa dela
            elsif v_rec is not null and exists (select 1 from public.categoria c where c.id = v_rec_cat and coalesce(c.ativo, true)) then
                v_cat := v_rec_cat;
                v_cat_origem := 'recorrencia';
            else
                -- FIN-CARTOES-MULTIPLOS-01: reconstrucao da fatura: a mesma compra (cartao, data, valor e descricao) removida pela limpeza
                -- seletiva volta com a Categoria de Despesa que o usuario lhe deu (a foto da limpeza, em operacao_cartao)
                select (f ->> 'categoria_id')::integer into v_cat
                  from financeiro.operacao_cartao o
                 cross join lateral jsonb_array_elements(coalesce(o.resultado -> 'fotos' -> 'compras', '[]'::jsonb)) f
                 where o.operacao = 'limpar_importacoes' and o.perfil_financeiro_id = p_perfil_id
                   and (f ->> 'cartao_id')::integer = p_cartao_id and (f ->> 'valor')::numeric = v_valor
                   and (f ->> 'data_compra')::date = v_data
                   and lower(coalesce(f ->> 'descricao_original_normalizada', f ->> 'descricao')) = lower(v_norm)
                   and exists (select 1 from public.categoria c where c.id = (f ->> 'categoria_id')::integer and coalesce(c.ativo, true))
                 order by o.criado_em desc
                 limit 1;
                if v_cat is not null then
                    v_cat_origem := 'reconstrucao';
                else
                    v_sug := financeiro.sugestao_categoria_importacao(p_perfil_id, v_l ->> 'descricao_classificacao', v_norm,
                                                                      v_cartao.categoria_id);
                    v_cat := (v_sug ->> 'categoria_id')::integer;
                    v_cat_origem := v_sug ->> 'origem';
                    if v_sug ->> 'aviso' is not null then
                        v_msgs := v_msgs || to_jsonb(v_sug ->> 'aviso');
                    end if;
                end if;
            end if;
            if v_cat is null and v_status = 'valido' then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Informe a categoria da despesa."'::jsonb;
            end if;
        end if;

        -- Duplicidade (chave de negocio do Flask) no lote e no banco; depois, conciliacao com compra ja lancada.
        v_chave := null;
        -- FIN-CARTAO-NUBANK-CREDITOS-01: credito da fatura (estorno de compra, IOF devolvido ou ajuste da administradora). Nao e compra
        -- negativa nem receita: abate uma vez o valor a pagar da fatura; a compra original continua (vinculada quando
        -- identificada sem duvida pelo texto do credito, com valor estornavel suficiente; mais de uma candidata pede a
        -- escolha do usuario, credito_compra_id, ou 0 = sem compra vinculada). Duplicidade pela chave do credito.
        if v_tipo = 'credito' and v_status <> 'ignorado' and v_data is not null and v_norm <> '' and v_valor is not null then
            v_chave := concat_ws('|', p_cartao_id, v_comp, v_data, v_valor, lower(v_norm), 'credito');
            v_cred_nat := case v_credito when 'iof_devolvido' then 'IOF_DEVOLVIDO' when 'estorno' then 'ESTORNO' else 'AJUSTE' end;
            if v_chave || '|' || v_cv_lote = any(v_chaves) and not coalesce((v_l ->> 'manter_duplicada')::boolean, false) then
                v_dup := 'lote';
            elsif exists (select 1 from financeiro.credito_fatura cf
                           where cf.cartao_id = p_cartao_id and coalesce(cf.mes_fatura_original, cf.mes_fatura) = v_comp
                             and cf.chave = v_chave and financeiro.pertence_ao_perfil(cf.perfil_financeiro_id, p_perfil_id)
                             and (v_cv is null or cf.cartao_vinculado_id is null or cf.cartao_vinculado_id = v_cv)) then  -- FIN-CARTOES-MULTIPLOS-01
                v_dup := 'banco';
            end if;
            if v_dup is not null then
                v_status := 'duplicado';
                v_ignorar := true;
                v_msgs := v_msgs || '"Credito ja registrado nesta fatura (ou repetido no arquivo): nao e abatido de novo."'::jsonb;
                -- a natureza, para a tela manter o repetido legitimo como credito (manter_duplicada)
                v_cred := jsonb_build_object('natureza', v_cred_nat, 'rotulo', case v_cred_nat when 'ESTORNO' then 'Estorno de compra' when 'IOF_DEVOLVIDO' then 'Devolucao de IOF'
                                              else 'Credito ou ajuste da fatura' end,
                    'compra', null, 'candidatas', '[]'::jsonb, 'fatura_destino', to_char(v_comp, 'MM/YYYY'));
            else
                v_chaves := v_chaves || (v_chave || '|' || v_cv_lote);
                v_alvo := case v_cred_nat
                    when 'IOF_DEVOLVIDO' then btrim(regexp_replace(financeiro.texto_cobranca(v_l ->> 'descricao_original'),
                                                  '^.*\miof\M( de volta| devolvido| estornado| devolucao)?( de| do| da)?', ''))
                    when 'ESTORNO' then financeiro.texto_cobranca(coalesce(substring(v_l ->> 'descricao_original' from '"([^"]+)"'),
                        regexp_replace(v_l ->> 'descricao_original',
                                       '^\s*(estorno|estornado|devolucao|devolução|reembolso|cancelamento|chargeback)\s+(de|do|da)?\s*', '', 'i')))
                    end;
                select coalesce(jsonb_agg(jsonb_build_object('id', l.id, 'descricao', coalesce(nullif(l.descricao_exibida, ''), l.descricao),
                                                             'valor', l.valor, 'data_compra', l.data_compra,
                                                             'fatura', to_char(coalesce(l.mes_fatura_original, l.mes_fatura), 'MM/YYYY'),
                                                             'estornavel', l.valor - coalesce(cr.total, 0))
                                          order by l.data_compra desc, l.id), '[]'::jsonb)
                  into v_cred_cands
                  from public.lancamento_agregado l
                  left join lateral (select sum(cf.valor) as total from financeiro.credito_fatura cf
                                      where cf.lancamento_id = l.id) cr on true
                 where v_cred_nat in ('IOF_DEVOLVIDO', 'ESTORNO') and coalesce(v_alvo, '') <> ''
                   and l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
                   and coalesce(l.mes_fatura_original, l.mes_fatura) between (v_comp - interval '3 months')::date and v_comp
                   -- previsao de recorrencia ainda sem cobranca nao e compra a estornar
                   and (not coalesce(l.is_recorrente, false) or coalesce(l.is_importado, false)
                        or exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                    where o.lancamento_id = l.id and o.revertida_em is null))
                   and l.valor - coalesce(cr.total, 0) >= v_valor
                   and not l.id = any(v_cred_usados)
                   and (v_cv is null or l.cartao_vinculado_id is null or l.cartao_vinculado_id = v_cv)  -- FIN-CARTOES-MULTIPLOS-01: a compra do mesmo cartao
                   and position(' ' || v_alvo || ' ' in ' ' || financeiro.texto_cobranca(coalesce(l.descricao_original, l.descricao)) || ' ') > 0
                   and case v_cred_nat
                       when 'IOF_DEVOLVIDO' then l.valor = v_valor
                            and position(' iof ' in ' ' || financeiro.texto_cobranca(coalesce(l.descricao_original, l.descricao)) || ' ') > 0
                       else position(' iof ' in ' ' || financeiro.texto_cobranca(coalesce(l.descricao_original, l.descricao)) || ' ') = 0 end;
                if v_l ? 'credito_compra_id' then
                    begin
                        v_cred_esc := coalesce(nullif(v_l ->> 'credito_compra_id', '')::integer, 0);
                    exception when others then
                        v_cred_esc := -1;
                    end;
                    if v_cred_esc > 0 and exists (select 1 from jsonb_array_elements(v_cred_cands) c where (c ->> 'id')::integer = v_cred_esc) then
                        v_cred_compra := v_cred_esc;
                    elsif v_cred_esc <> 0 then
                        v_status := 'revisar';
                        v_rev_nat := true;
                        v_msgs := v_msgs || '"Compra escolhida nao e candidata a este credito (outro cartao, valor estornavel menor ou ja vinculada): escolha outra ou registre sem compra vinculada."'::jsonb;
                    end if;
                elsif jsonb_array_length(v_cred_cands) = 1 then
                    v_cred_compra := (v_cred_cands -> 0 ->> 'id')::integer;
                elsif jsonb_array_length(v_cred_cands) > 1 then
                    v_status := 'revisar';
                    v_rev_nat := true;
                    v_msgs := v_msgs || to_jsonb(format('%s compras podem ser a original deste credito: escolha a compra ou registre sem compra vinculada.',
                        jsonb_array_length(v_cred_cands)));
                end if;
                if v_cred_compra is not null then
                    v_cred_usados := v_cred_usados || v_cred_compra;
                end if;
                v_cred := jsonb_build_object(
                    'natureza', v_cred_nat,
                    'rotulo', case v_cred_nat when 'ESTORNO' then 'Estorno de compra' when 'IOF_DEVOLVIDO' then 'Devolucao de IOF'
                                              else 'Credito ou ajuste da fatura' end,
                    'compra', (select c from jsonb_array_elements(v_cred_cands) c where (c ->> 'id')::integer = v_cred_compra),
                    'candidatas', v_cred_cands,
                    'parcial', (select v_valor < (c ->> 'estornavel')::numeric from jsonb_array_elements(v_cred_cands) c
                                 where (c ->> 'id')::integer = v_cred_compra),
                    'escolhida', v_l ? 'credito_compra_id',
                    'fatura_destino', to_char(v_comp, 'MM/YYYY'));
                if v_status <> 'revisar' then
                    v_msgs := v_msgs || to_jsonb(format('%s: abate R$ %s do valor a pagar da fatura %s (nao e compra nem receita)%s.',
                        v_cred ->> 'rotulo', to_char(v_valor, 'FM999999990.00'), to_char(v_comp, 'MM/YYYY'),
                        case when v_cred_compra is not null
                             then format('; compra original preservada: %s (R$ %s)', v_cred -> 'compra' ->> 'descricao',
                                         to_char((v_cred -> 'compra' ->> 'valor')::numeric, 'FM999999990.00'))
                             else '; sem compra vinculada' end));
                end if;
            end if;
        end if;

        if v_status <> 'ignorado' and v_tipo <> 'credito' and v_data is not null and v_norm <> '' and v_valor is not null then
            v_chave := concat_ws('|', p_cartao_id, v_comp, v_data, v_valor, lower(v_norm), v_parc, v_total);
            -- FIN-CARTAO-IMPORTACAO-FIXAS-01: repetida no proprio arquivo, mas mantida pelo usuario (duas compras legitimas iguais)
            if v_chave || '|' || v_cv_lote = any(v_chaves) and not coalesce((v_l ->> 'manter_duplicada')::boolean, false) then
                v_dup := 'lote';
            else
                -- FIN-CARTAO-IMPORTACAO-FIXAS-01: a compra ja gravada (para sugerir a conciliacao com a previsao, abaixo)
                select l.id into v_existente from public.lancamento_agregado l
                 where l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
                   and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp
                   and l.data_compra = v_data and l.valor = v_valor
                   -- FIN-CARTOES-MULTIPLOS-01: de outro cartao vinculado nao e a mesma compra
                   and (v_cv is null or l.cartao_vinculado_id is null or l.cartao_vinculado_id = v_cv)
                   and ((l.numero_parcela = v_parc and l.total_parcelas = v_total)
                        -- FIN-CARTAO-NUBANK-PARCELADAS-01: ja gravada como a parcela do texto (decidida numa importacao anterior)
                        or (v_amb is not null and v_amb_res is null
                            and l.numero_parcela = v_amb_parc and l.total_parcelas = v_amb_total))
                   and lower(coalesce(l.descricao_original_normalizada, l.descricao)) = lower(v_norm)
                 order by l.id limit 1;
                if v_existente is not null then
                    v_dup := 'banco';
                    select l.numero_parcela, l.total_parcelas into v_parc, v_total
                      from public.lancamento_agregado l where l.id = v_existente;
                end if;
            end if;
            if v_dup is not null then
                v_status := 'duplicado';
                v_ignorar := true;
                v_msgs := v_msgs || '"Possivel duplicidade detectada."'::jsonb;
            else
                v_chaves := v_chaves || (v_chave || '|' || v_cv_lote);
                -- Compra ja lancada (manual, por recorrencia ou importacao com outra descricao): mesmo cartao,
                -- competencia, valor e parcela, data a ate 5 dias (ou gerada por recorrencia). Cada lancamento
                -- concilia uma linha so.
                select l.id, jsonb_build_object('lancamento_id', l.id,
                                                'descricao', coalesce(nullif(l.descricao_exibida, ''), l.descricao),
                                                'data_compra', l.data_compra, 'valor', l.valor, 'categoria_id', l.categoria_id,
                                                'recorrente', coalesce(l.is_recorrente, false), 'mantida', v_manter)
                  into v_conc_id, v_conc
                  from public.lancamento_agregado l
                 where l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
                   and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp and l.valor = v_valor
                   and coalesce(l.numero_parcela, 1) = v_parc and coalesce(l.total_parcelas, 1) = v_total
                   -- FIN-CARTAO-NUBANK-PARCELADAS-01: a parcela (da 2a em diante) nao traz a data da compra (o Nubank usa o inicio do
                   -- ciclo da fatura): a mesma parcela N/M, com o mesmo valor, na mesma fatura, e a parcela ja lancada
                   and (abs(l.data_compra - v_data) <= 5 or v_total > 1)
                   -- FIN-CARTAO-DESPESAS-FIXAS-01: compra de recorrencia (prevista ou realizada) nunca e conciliada so pelo valor
                   -- (ChatGPT de R$ 109,90 nao e o Claude); ela e encontrada pela descricao, abaixo.
                   and not (coalesce(l.is_recorrente, false) and l.item_despesa_id is not null)
                   and not l.id = any(v_usados)
                   and (v_cv is null or l.cartao_vinculado_id is null or l.cartao_vinculado_id = v_cv)  -- FIN-CARTOES-MULTIPLOS-01
                 order by (lower(coalesce(l.descricao_original_normalizada, l.descricao)) = lower(v_norm)) desc,
                          abs(l.data_compra - v_data), l.id
                 limit 1;
                if v_conc_id is not null then
                    v_usados := v_usados || v_conc_id;
                    if not v_manter then
                        v_status := 'conciliado';
                        v_ignorar := true;
                    end if;
                    v_msgs := v_msgs || to_jsonb(format('Ja lancada no cartao: %s (%s, R$ %s)%s.', v_conc ->> 'descricao',
                        to_char((v_conc ->> 'data_compra')::date, 'DD/MM/YYYY'), to_char((v_conc ->> 'valor')::numeric, 'FM999999990.00'),
                        case when v_manter then '; mantida pelo usuario como compra diferente' else '; retirada da efetivacao' end));
                end if;
            end if;
        end if;

        -- FIN-CARTAO-IMPORTACAO-FIXAS-01: ocorrencia da recorrencia reconhecida (descricao, apelido ou escolha do usuario).
        -- - previsao do mes sem cobranca: a linha a realiza (uma ocorrencia, previsto preservado);
        -- - cobranca ja lancada como compra comum (a mesma linha reimportada, ou a compra conciliada pelo valor): sugere
        --   conciliar com a previsao; a conciliacao so acontece na confirmacao, se pedida (conciliar_previsao);
        -- - nada e descartado em silencio: segunda cobranca do mes, previsao ja cobrada, em fatura paga ou consolidada
        --   pedem revisao (escolher outra recorrencia, tratar como compra comum ou retirar a linha).
        v_existente := coalesce(v_existente, case when v_status = 'conciliado' then v_conc_id end);
        if v_status in ('duplicado', 'conciliado') and v_existente is not null and v_rec is not null
           and jsonb_array_length(v_cands) = 1 then
            select l.* into v_occ from public.lancamento_agregado l where l.id = v_existente;
            if financeiro.natureza_da_compra(v_occ.total_parcelas, v_occ.is_recorrente, v_occ.item_despesa_id,
                                             v_occ.categoria_cartao_id) in ('CATEGORIA', 'OUTROS')
               and v_occ.item_despesa_id is null then
                select p.* into v_prev_sug from public.lancamento_agregado p
                 where p.item_despesa_id = v_rec and p.cartao_id = p_cartao_id and p.mes_fatura = v_occ.mes_fatura
                   and coalesce(p.is_recorrente, false) and coalesce(p.total_parcelas, 1) = 1
                   and not coalesce(p.is_importado, false)
                   and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                    where o.lancamento_id = p.id and o.revertida_em is null)
                   and not p.id = any(v_usadas)
                 order by p.id limit 1;
                if found then
                    v_fat_occ := financeiro.fatura_do_mes(p_cartao_id, v_prev_sug.mes_fatura);
                    if v_fat_occ is null or not (financeiro.fatura_esta_paga(v_fat_occ)
                       or exists (select 1 from public.conta c where c.id = v_fat_occ and c.status_fatura = 'FECHADA')) then
                        v_usadas := v_usadas || v_prev_sug.id;
                        v_sug_conc := jsonb_build_object('previsto_id', v_prev_sug.id, 'cobranca_id', v_occ.id,
                            'recorrencia_id', v_rec, 'recorrencia_nome', v_rec_nome, 'valor_previsto', v_prev_sug.valor,
                            'valor_cobrado', v_occ.valor, 'diferenca', v_occ.valor - v_prev_sug.valor,
                            'fatura', to_char(v_prev_sug.mes_fatura, 'MM/YYYY'));
                        v_msgs := v_msgs || to_jsonb(format('Ja lancada como compra comum e corresponde a previsao de "%s" (R$ %s): pode ser conciliada na confirmacao (cobrado R$ %s; diferenca R$ %s).',
                            v_rec_nome, to_char(v_prev_sug.valor, 'FM999999990.00'), to_char(v_occ.valor, 'FM999999990.00'),
                            to_char(v_occ.valor - v_prev_sug.valor, 'FM999999990.00')));
                    end if;
                end if;
            end if;
        end if;
        if v_status in ('ignorado', 'duplicado', 'conciliado') or v_norm = '' then
            v_rec := null;
        elsif jsonb_array_length(v_cands) > 1 then
            v_status := 'revisar';
            v_rev_nat := true;
            v_msgs := v_msgs || to_jsonb(format('Mais de uma recorrencia do cartao combina com a descricao (%s): a linha nao foi vinculada; escolha a recorrencia ou trate como compra comum.',
                (select string_agg(c ->> 'nome', ', ' order by (c ->> 'id')::integer) from jsonb_array_elements(v_cands) c)));
        elsif v_rec is not null then
            select l.* into v_occ
              from public.lancamento_agregado l
             where l.item_despesa_id = v_rec and l.cartao_id = p_cartao_id
               and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp
               -- FIN-CARTAO-PREVISTO-EXECUTADO-01: a previsao que a fatura paga deixou sem cobranca nao e a ocorrencia; a cobranca
               -- real que chega depois entra como compra da recorrencia (na proxima fatura aberta)
               and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                where o.lancamento_id = l.id and o.revertida_em is null and o.origem = 'NAO_COBRADA')
             order by l.id limit 1;
            if found then
                v_fat_occ := financeiro.fatura_do_mes(p_cartao_id, v_occ.mes_fatura);
                if v_occ.id = any(v_usadas) then
                    v_status := 'revisar';
                    v_rev_nat := true;
                    v_msgs := v_msgs || to_jsonb(format('Segunda cobranca de "%s" nesta fatura: a previsao ja ficou com outra linha do arquivo. Se esta e outra cobranca, trate como compra comum; se e a mesma, retire a linha.', v_rec_nome));
                elsif coalesce(v_occ.is_recorrente, false) and coalesce(v_occ.total_parcelas, 1) = 1
                   and not coalesce(v_occ.is_importado, false)
                   and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                    where o.lancamento_id = v_occ.id and o.revertida_em is null)
                   and (v_fat_occ is null or not (financeiro.fatura_esta_paga(v_fat_occ)
                        or exists (select 1 from public.conta c where c.id = v_fat_occ and c.status_fatura = 'FECHADA'))) then
                    v_realiza := v_occ.id;
                    v_prev := v_occ.valor;
                    v_usadas := v_usadas || v_occ.id;
                    v_msgs := v_msgs || to_jsonb(format('Cobranca real da recorrencia "%s": confirma a previsao de R$ %s desta fatura (executado R$ %s%s).',
                        v_rec_nome, to_char(v_prev, 'FM999999990.00'), to_char(v_valor, 'FM999999990.00'),
                        case when v_valor <> v_prev then '; diferenca R$ ' || to_char(v_valor - v_prev, 'FM999999990.00') else '' end));
                elsif coalesce(v_occ.is_importado, false) or not coalesce(v_occ.is_recorrente, false)
                      or coalesce(v_occ.total_parcelas, 1) <> 1
                      or exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                  where o.lancamento_id = v_occ.id and o.revertida_em is null) then
                    v_status := 'revisar';
                    v_rev_nat := true;
                    v_msgs := v_msgs || to_jsonb(format('"%s" ja tem cobranca nesta fatura (R$ %s em %s). Se esta e outra cobranca, trate como compra comum; se e a mesma, retire a linha.',
                        v_rec_nome, to_char(v_occ.valor, 'FM999999990.00'), to_char(v_occ.data_compra, 'DD/MM/YYYY')));
                elsif financeiro.fatura_esta_paga(v_fat_occ) then
                    v_status := 'revisar';
                    v_rev_nat := true;
                    v_msgs := v_msgs || to_jsonb(format('A previsao de "%s" esta em fatura paga (%s): se esta cobranca e outra, trate como compra comum (entra na proxima fatura aberta); se ja foi paga, retire a linha.',
                        v_rec_nome, to_char(v_occ.mes_fatura, 'MM/YYYY')));
                else
                    v_status := 'revisar';
                    v_rev_nat := true;
                    v_msgs := v_msgs || to_jsonb(format('A previsao de "%s" esta em fatura consolidada (%s): ela nao recebe cobranca por aqui; retire a linha ou trate como compra comum de outra competencia.',
                        v_rec_nome, to_char(v_occ.mes_fatura, 'MM/YYYY')));
                end if;
            elsif v_rec = any(v_novas) then
                v_status := 'revisar';
                v_rev_nat := true;
                v_msgs := v_msgs || to_jsonb(format('Segunda cobranca de "%s" nesta fatura: a ocorrencia do mes ja ficou com outra linha do arquivo. Se esta e outra cobranca, trate como compra comum; se e a mesma, retire a linha.', v_rec_nome));
            else
                v_novas := v_novas || v_rec;
                v_msgs := v_msgs || to_jsonb(format('Reconhecida como compra recorrente do cartao ("%s"): o gerador nao a lanca de novo nesta competencia.', v_rec_nome));
            end if;
        end if;

        -- Categoria do Cartao (resolver_categoria_cartao_para_lancamento)
        v_cc := null;
        v_cc_res := null;
        v_vinc := false;
        v_cc_origem := null;
        if v_cat is not null and v_tipo <> 'credito' then
            v_cc := financeiro.resolver_categoria_cartao(p_perfil_id, p_cartao_id, v_cat);
            if v_cc is not null then
                v_vinc := true;
                v_cc_origem := 'mapa_categoria_despesa';
            elsif v_rec is null and v_total <= 1 then  -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencia nao precisa de Categoria do Cartao
                                                      -- (nem a parcela: FIN-CARTAO-NUBANK-PARCELADAS-01)
                select v.categoria_cartao_id into v_cc_res
                  from public.categoria_cartao_despesa v join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
                 where v.categoria_id = v_cat and v.ativo and cc.ativo
                   and financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)
                 order by v.id limit 1;
                if v_cc_res is not null then
                    v_cc_origem := 'nao_vinculada_ao_cartao';
                    v_msgs := v_msgs || '"Esta Categoria do Cartao ainda nao esta vinculada ao cartao selecionado."'::jsonb;
                else
                    v_cc_origem := 'nao_configurada';
                    v_msgs := v_msgs || '"Categoria de despesa sem Categoria do Cartao configurada."'::jsonb;
                end if;
            end if;
        end if;

        v_class := case
            when v_status = 'duplicado' then 'duplicada'
            when v_status = 'conciliado' then 'conciliada'
            when v_ignorar or v_status = 'ignorado' then 'ignorada'
            -- FIN-CARTAO-NUBANK-CREDITOS-01: credito nao tem Categoria de Despesa
            when v_tipo = 'credito' then case when v_status = 'revisar' then 'revisar' else 'classificada' end
            when v_cat_origem = 'ambigua' then 'ambigua'
            when v_cat is null then 'categoria_despesa_pendente'
            when v_cc_origem = 'nao_vinculada_ao_cartao' then 'categoria_cartao_nao_vinculada'
            when v_rec is not null or v_total > 1 then 'classificada'
            when v_cc is null then 'categoria_cartao_pendente'
            else 'classificada' end;
        if v_class = 'classificada' then
            v_msgs := v_msgs || '"Linha pronta para importacao."'::jsonb;
        end if;
        -- FIN-CARTAO-IMPORTACAO-FIXAS-01: detalhe da despesa fixa e classificacao proposta na previa
        if v_rec is not null then
            v_fixa := jsonb_build_object('recorrencia_id', v_rec, 'nome', v_rec_nome,
                'valor_previsto', coalesce(v_prev, (v_cands -> 0 ->> 'valor')::numeric), 'valor_cobrado', v_valor,
                'diferenca', v_valor - coalesce(v_prev, (v_cands -> 0 ->> 'valor')::numeric),
                'competencia', to_char(v_comp, 'MM/YYYY'),
                'fatura_destino', to_char(case when v_realiza is not null then v_occ.mes_fatura else v_comp end, 'MM/YYYY'),
                'realiza_lancamento_id', v_realiza, 'escolhida', coalesce(v_escolha, 0) > 0);
            -- escolhida pelo usuario sem que a descricao a reconhecesse: o texto pode virar apelido na confirmacao
            if coalesce(v_escolha, 0) > 0 and length(btrim(v_texto)) between 3 and 80
               and position(' ' || financeiro.texto_cobranca(v_rec_nome) || ' ' in v_texto) = 0
               and not exists (select 1 from financeiro.recorrencia_apelido a where a.item_despesa_id = v_rec and a.ativo
                                  and position(' ' || a.apelido || ' ' in v_texto) > 0) then
                v_apelido := btrim(v_texto);
            end if;
        end if;
        v_classe := case
            when v_status = 'ignorado' then 'IGNORADA'
            when v_status in ('duplicado', 'conciliado') then case when v_total > 1 then 'PARCELA_EXISTENTE' else 'JA_EXISTENTE' end
            -- FIN-CARTAO-NUBANK-PARCELADAS-01: a categoria pendente nao esconde a natureza (Parcelada antes de Fixa)
            when v_status = 'revisar' and v_rev_nat then 'REVISAR'
            when v_tipo = 'credito' then 'CREDITO'  -- FIN-CARTAO-NUBANK-CREDITOS-01
            when v_total > 1 then 'PARCELADA'
            when v_rec is not null then 'DESPESA_FIXA'
            else 'COMPRA' end;

        v_saida := v_saida || (jsonb_build_object(
            'linha_id', coalesce(v_l ->> 'linha_id', 'linha-' || v_idx), 'tipo_credito', v_credito, 'linha_origem', coalesce((v_l ->> 'linha_origem')::integer, v_idx::integer),
            'status', v_status, 'ignorar', v_ignorar, 'tipo_movimento', v_tipo,
            'data_compra', v_data, 'valor', v_valor,
            'descricao_original', v_l ->> 'descricao_original', 'descricao_normalizada', v_norm,
            'descricao_exibida', coalesce(nullif(btrim(v_l ->> 'descricao_exibida'), ''), v_norm),
            'parcela_atual', v_parc, 'numero_parcela', v_parc, 'total_parcelas', v_total, 'parcela', v_parc || '/' || v_total,
            'categoria_id', v_cat, 'categoria_despesa_id', v_cat,
            'categoria_nome', (select c.nome from public.categoria c where c.id = v_cat),
            'categoria_origem', v_cat_origem, 'categoria_sugerida_origem', coalesce(v_sug ->> 'origem', v_cat_origem),
            'confianca_categoria', coalesce(v_sug ->> 'confianca', case when v_cat is not null then 'manual' else 'baixa' end),
            'palavras_chave_encontradas', coalesce(v_sug -> 'palavras_chave_encontradas', '[]'::jsonb),
            'categorias_candidatas', coalesce(v_sug -> 'categorias_candidatas', '[]'::jsonb),
            'categoria_cartao_id', v_cc, 'categoria_cartao_resolvida_id', v_cc_res,
            'categoria_cartao_nome', (select cc.nome from public.categoria_cartao cc where cc.id = coalesce(v_cc, v_cc_res)),
            'categoria_cartao_origem', v_cc_origem, 'categoria_cartao_vinculada_ao_cartao', v_vinc,
            'status_classificacao', v_class, 'duplicidade', v_dup, 'duplicada', v_status = 'duplicado',
            'ignorada', v_ignorar,
            'conciliacao', v_conc,
            'recorrencia_id', v_rec,
            'recorrencia_nome', case when v_rec is not null then v_rec_nome end,
            'recorrencias_candidatas', case when jsonb_array_length(v_cands) > 1 then v_cands end,
            'realiza_lancamento_id', v_realiza,
            'valor_previsto', v_prev,
            'gerar_parcelas_futuras', coalesce((v_l ->> 'gerar_parcelas_futuras')::boolean, false),
            'origem_importacao', coalesce(nullif(v_l ->> 'origem_importacao', ''), 'csv'),
            'hash_deduplicacao', v_chave,
            'mensagens', v_msgs, 'avisos', v_msgs)
            -- FIN-CARTAO-IMPORTACAO-FIXAS-01 (objeto a parte: jsonb_build_object aceita ate 100 argumentos)
            || jsonb_build_object(
            'classificacao_importacao', v_classe,
            'despesa_fixa', v_fixa,
            'conciliacao_sugerida', v_sug_conc,
            'conciliar_previsao', v_sug_conc is not null and coalesce((v_l ->> 'conciliar_previsao')::boolean, false),
            'recorrencia_escolhida_id', v_escolha,
            'apelido_sugerido', v_apelido,
            'salvar_apelido', v_apelido is not null and coalesce((v_l ->> 'salvar_apelido')::boolean, false),
            'manter_duplicada', coalesce((v_l ->> 'manter_duplicada')::boolean, false))
            -- FIN-CARTAO-NUBANK-PARCELADAS-01
            || jsonb_build_object(
            'parcela_ambigua', v_amb,
            'natureza_parcela', v_amb_res,
            'categoria_pendente', v_tipo <> 'credito' and v_cat is null,
            'credito', v_cred)  -- FIN-CARTAO-NUBANK-CREDITOS-01
            -- FIN-CARTOES-MULTIPLOS-01: cartao de origem
            || jsonb_build_object(
            'cartao_final', v_final,
            'cartao_vinculado_id', v_cv,
            'cartao_vinculado', (select jsonb_build_object('id', v.id, 'nome', v.nome, 'final', v.final, 'tipo', v.tipo, 'situacao', v.situacao)
                                    from financeiro.cartao_vinculado v where v.id = v_cv),
            'cartao_origem', v_cv_origem,
            'cartao_vinculado_escolhido_id', v_cv_esc));
    end loop;

    return jsonb_build_object(
        'cartao_id', p_cartao_id, 'competencia', to_char(v_comp, 'YYYY-MM'),
        'situacao_fatura', financeiro.situacao_fatura(financeiro.fatura_do_mes(p_cartao_id, v_comp)),
        -- FIN-CARTOES-MULTIPLOS-01: cartoes vinculados do contrato (a previa pode escolher o de origem)
        'cartoes_contrato', coalesce((select jsonb_agg(jsonb_build_object('id', v.id, 'nome', v.nome, 'final', v.final,
                                                                 'tipo', v.tipo, 'portador', v.portador, 'situacao', v.situacao)
                                              order by v.situacao <> 'ATIVO', v.final)
                                        from financeiro.cartao_vinculado v where v.contrato_id = p_cartao_id), '[]'::jsonb),
        -- os tipos de arquivo ja importados nesta fatura (PDF ou planilha): o outro so depois da limpeza seletiva
        'fontes_importadas', coalesce((select jsonb_agg(distinct case when l.origem_importacao in ('csv', 'xlsx') then 'planilha'
                                                                     else l.origem_importacao end)
                                         from public.lancamento_agregado l
                                        where l.cartao_id = p_cartao_id and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp
                                          and coalesce(l.is_importado, false)
                                          and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb),
        -- FIN-CARTAO-IMPORTACAO-FIXAS-01: recorrencias do cartao que a previa pode escolher (ativas, ou inativas com previsao pendente)
        'recorrencias_cartao', coalesce((select jsonb_agg(jsonb_build_object('id', i.id, 'nome', i.nome, 'valor', i.valor,
                                                                    'ativa', coalesce(i.ativo, true)) order by i.nome, i.id)
            from public.item_despesa i
           where coalesce(i.recorrente, false) and i.tipo <> 'Agregador' and i.meio_pagamento = 'cartao'
             and i.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
             and (coalesce(i.ativo, true) or exists (select 1 from public.lancamento_agregado p
                   where p.item_despesa_id = i.id and p.cartao_id = p_cartao_id and coalesce(p.is_recorrente, false)
                     and coalesce(p.mes_fatura_original, p.mes_fatura) = v_comp and not coalesce(p.is_importado, false)))), '[]'::jsonb),
        'linhas', v_saida,
        'validacoes', (select jsonb_build_object(
            'total_linhas', count(*),
            'validas', count(*) filter (where l ->> 'status' = 'valido'),
            'revisar', count(*) filter (where l ->> 'status' = 'revisar'),
            'duplicadas', count(*) filter (where l ->> 'status' = 'duplicado'),
            'conciliadas', count(*) filter (where jsonb_typeof(l -> 'conciliacao') = 'object'),
            'realizacoes', count(*) filter (where l ->> 'realiza_lancamento_id' is not null and not (l ->> 'ignorar')::boolean),
            'despesas_fixas', count(*) filter (where l ->> 'classificacao_importacao' = 'DESPESA_FIXA'),
            'parceladas', count(*) filter (where l ->> 'classificacao_importacao' = 'PARCELADA'),
            'parcelas_ambiguas', count(*) filter (where jsonb_typeof(l -> 'parcela_ambigua') = 'object'
                                                      and l ->> 'natureza_parcela' is null),
            'conciliacoes_sugeridas', count(*) filter (where jsonb_typeof(l -> 'conciliacao_sugerida') = 'object'),
            'sem_categoria_cartao', count(*) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and l ->> 'status' not in ('duplicado', 'ignorado', 'conciliado')
                                                       and l ->> 'categoria_cartao_id' is null
                                                       and l ->> 'recorrencia_id' is null and (l ->> 'total_parcelas')::integer <= 1),
            'total_importavel', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and not (l ->> 'ignorar')::boolean), 0),
            'creditos', count(*) filter (where l ->> 'tipo_movimento' = 'credito'),
            'total_creditos', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'credito'), 0),
            -- FIN-CARTAO-NUBANK-CREDITOS-01: creditos que a confirmacao abate da fatura
            'creditos_a_abater', count(*) filter (where l ->> 'classificacao_importacao' = 'CREDITO' and not (l ->> 'ignorar')::boolean),
            'total_creditos_a_abater', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'classificacao_importacao' = 'CREDITO'
                                                                                      and not (l ->> 'ignorar')::boolean), 0),
            'ignorados', count(*) filter (where l ->> 'status' = 'ignorado'),
            -- FIN-CARTOES-MULTIPLOS-01: finais do arquivo sem cartao cadastrado e linhas sem cartao identificado
            'cartoes_nao_cadastrados', coalesce(jsonb_agg(distinct l ->> 'cartao_final')
                filter (where l ->> 'cartao_final' is not null and l ->> 'cartao_vinculado_id' is null), '[]'::jsonb),
            'sem_cartao_identificado', count(*) filter (where l ->> 'cartao_vinculado_id' is null
                                                         and l ->> 'status' not in ('ignorado', 'duplicado', 'conciliado')))
            from jsonb_array_elements(v_saida) l));
end
$$;

-- importar_fatura_cartao: texto de 20261212090000 + os trechos marcados.
create or replace function financeiro.importar_fatura_cartao(p_perfil_id integer, p_cartao_id integer, p_competencia date,
                                                  p_linhas jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_cartao;
    v_comp      date := date_trunc('month', p_competencia::timestamp)::date;
    v_analise   jsonb;
    v_l         jsonb;
    v_pendentes text[] := '{}';
    v_a_gravar  jsonb := '[]'::jsonb;
    v_ids       integer[] := '{}';
    v_meses     date[] := '{}';
    v_n         integer;
    v_inicio    integer;
    v_alvo      date;
    v_orig      date;
    v_fat       integer;
    v_passos    integer;
    v_ant       date;
    v_compra    text;
    v_id        integer;
    v_ns        constant uuid := '7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c';  -- mesma identidade do gerador (namespace do Flask)
    v_res       jsonb;
    v_dup       integer;
    v_realizadas integer := 0;  -- FIN-CARTAO-DESPESAS-FIXAS-01
    v_conciliar  jsonb := '[]'::jsonb;  -- FIN-CARTAO-IMPORTACAO-FIXAS-01
    v_conciliadas integer := 0;
    v_apelidos   integer := 0;
    v_r          jsonb;
    v_creditos   jsonb := '[]'::jsonb;  -- FIN-CARTAO-NUBANK-CREDITOS-01
    v_cred_ids   bigint[] := '{}';
    v_cid        bigint;
    v_total_cred numeric := 0;
    v_lanc_cred  integer;  -- FIN-CARTOES-MULTIPLOS-01: compra original do credito
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
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
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, true);
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao e das compras do perfil
    perform 1 from public.item_despesa where id = p_cartao_id for update;  -- cartao antes das faturas

    -- Analise refeita sob a trava: duplicidade e conciliacao valem para o que esta gravado agora.
    v_analise := financeiro.analisar_importacao_cartao(p_perfil_id, p_cartao_id, v_comp, p_linhas);
    for v_l in select e from jsonb_array_elements(v_analise -> 'linhas') e loop
        -- FIN-CARTAO-IMPORTACAO-FIXAS-01: cobranca ja lancada que o usuario pediu para conciliar com a previsao (a linha nao e gravada)
        if coalesce((v_l ->> 'conciliar_previsao')::boolean, false) then
            v_conciliar := v_conciliar || v_l;
        end if;
        continue when (v_l ->> 'ignorar')::boolean;
        -- FIN-CARTAO-NUBANK-CREDITOS-01: credito da fatura (sem Categoria de Despesa): gravado a parte, abate o valor a pagar
        if v_l ->> 'tipo_movimento' = 'credito' then
            if v_l ->> 'status' <> 'valido' then
                v_pendentes := v_pendentes || format('linha %s (%s): %s', v_l ->> 'linha_origem',
                    coalesce(v_l ->> 'descricao_exibida', '-'), coalesce(v_l -> 'mensagens' ->> -1, v_l ->> 'status'));
            else
                v_creditos := v_creditos || v_l;
            end if;
            continue;
        end if;
        if v_l ->> 'status' <> 'valido' or v_l ->> 'categoria_id' is null then
            v_pendentes := v_pendentes || format('linha %s (%s): %s', v_l ->> 'linha_origem',
                coalesce(v_l ->> 'descricao_exibida', '-'), coalesce(v_l -> 'mensagens' ->> 0, v_l ->> 'status'));
        else
            v_a_gravar := v_a_gravar || v_l;
        end if;
    end loop;
    if cardinality(v_pendentes) > 0 then
        raise exception 'Importacao nao realizada: % linha(s) precisam de revisao ou devem ser retiradas: %',
            cardinality(v_pendentes), array_to_string(v_pendentes[1:5], '; ')
            using errcode = '22023', hint = 'REVISAR';
    end if;
    if jsonb_array_length(v_a_gravar) = 0 and jsonb_array_length(v_conciliar) = 0 and jsonb_array_length(v_creditos) = 0 then
        raise exception 'Nenhuma linha para importar' using errcode = '22023';
    end if;
    -- FIN-CARTOES-MULTIPLOS-01: o PDF e a planilha (CSV ou XLSX) sao a mesma fatura: o que ja foi importado de um tipo de arquivo nao
    -- recebe linhas novas do outro (valores arredondados de outro jeito viriam em dobro). Reconstruir pelo outro arquivo
    -- so depois da limpeza seletiva.
    if jsonb_array_length(v_a_gravar) > 0 and exists (
        select 1 from public.lancamento_agregado l
         where l.cartao_id = p_cartao_id and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp and coalesce(l.is_importado, false)
           and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
           and (case when l.origem_importacao in ('csv', 'xlsx') then 'planilha' else l.origem_importacao end)
               is distinct from (case when coalesce(v_a_gravar -> 0 ->> 'origem_importacao', 'csv') in ('csv', 'xlsx') then 'planilha'
                                      else v_a_gravar -> 0 ->> 'origem_importacao' end)) then
        raise exception 'Importacao nao realizada: a fatura de % ja foi importada de outro tipo de arquivo (PDF ou planilha). Importe o mesmo tipo de arquivo, ou faca a limpeza seletiva antes de reconstruir pelo outro.',
            to_char(v_comp, 'MM/YYYY') using errcode = 'P0001', hint = 'OUTRA_FONTE';
    end if;

    for v_l in select e from jsonb_array_elements(v_a_gravar) e loop
        -- FIN-CARTAO-DESPESAS-FIXAS-01: cobranca real da previsao da recorrencia: uma ocorrencia so, previsto preservado
        if (v_l ->> 'realiza_lancamento_id') is not null then
            v_id := financeiro.realizar_ocorrencia_recorrencia(p_perfil_id, (v_l ->> 'realiza_lancamento_id')::integer,
                jsonb_build_object('valor', v_l ->> 'valor', 'data_compra', v_l ->> 'data_compra',
                                   'descricao_original', v_l ->> 'descricao_original',
                                   'descricao_original_normalizada', v_l ->> 'descricao_normalizada',
                                   'is_importado', true, 'origem_importacao', coalesce(v_l ->> 'origem_importacao', 'csv')),
                'IMPORTACAO', null);
            v_realizadas := v_realizadas + 1;
            -- FIN-CARTOES-MULTIPLOS-01: o cartao de origem da cobranca real
            if (v_l ->> 'cartao_vinculado_id') is not null then
                update public.lancamento_agregado set cartao_vinculado_id = (v_l ->> 'cartao_vinculado_id')::integer where id = v_id;
            end if;
            v_alvo := (select l.mes_fatura from public.lancamento_agregado l where l.id = v_id);
            if not v_alvo = any(v_meses) then
                v_meses := v_meses || v_alvo;
            end if;
            continue;
        end if;
        v_n := (v_l ->> 'total_parcelas')::integer;
        -- Parcelamento pedido pelo usuario: a parcela do arquivo e as futuras (gerar_apenas_atual_e_futuras do Flask);
        -- sem ele, so a parcela da fatura importada (como o Flask).
        v_inicio := (v_l ->> 'parcela_atual')::integer;
        v_compra := case when (v_l ->> 'recorrencia_id') is not null
            then extensions.uuid_generate_v5(v_ns, format('%s-%s', v_l ->> 'recorrencia_id', to_char(v_comp, 'YYYY-MM-DD')))::text
            else gen_random_uuid()::text end;
        v_ant := null;
        for v_k in v_inicio .. case when (v_l ->> 'gerar_parcelas_futuras')::boolean and v_n > 1 then v_n else v_inicio end loop
            v_orig := (v_comp + make_interval(months => v_k - v_inicio))::date;
            v_alvo := v_orig;
            if v_ant is not null and v_alvo <= v_ant then
                v_alvo := (v_ant + interval '1 month')::date;
            end if;
            v_passos := 0;
            loop  -- fatura paga nao recebe compra: proxima nao paga (como o Flask e o novo aplicativo)
                v_fat := financeiro.fatura_do_mes(p_cartao_id, v_alvo);
                exit when v_fat is null or not financeiro.fatura_esta_paga(v_fat);
                v_alvo := (v_alvo + interval '1 month')::date;
                v_passos := v_passos + 1;
                if v_passos > 24 then
                    raise exception 'Nao ha fatura aberta nos proximos 24 meses' using errcode = '22023';
                end if;
            end loop;
            v_ant := v_alvo;
            v_fat := financeiro.garantir_fatura(p_perfil_id, p_cartao_id, v_alvo);
            perform 1 from public.conta where id = v_fat for update;
            if financeiro.fatura_esta_paga(v_fat) then
                raise exception 'A fatura de % foi paga durante a importacao. Revise e tente de novo.',
                    to_char(v_alvo, 'MM/YYYY') using errcode = 'P0001';
            end if;
            if exists (select 1 from public.conta c where c.id = v_fat and c.status_fatura = 'FECHADA') then
                raise exception 'Importacao nao realizada: a fatura de % esta consolidada e "%" cairia nela. Retire a linha ou importe em outra competencia.',
                    to_char(v_alvo, 'MM/YYYY'), v_l ->> 'descricao_exibida' using errcode = 'P0001', hint = 'CONSOLIDADA';
            end if;
            insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, item_agregado_id, categoria_cartao_id,
                                                    categoria_id, descricao, descricao_original, descricao_original_normalizada,
                                                    descricao_exibida, valor, data_compra, mes_fatura, numero_parcela,
                                                    total_parcelas, observacoes, is_recorrente, item_despesa_id, compra_id,
                                                    is_importado, origem_importacao, criado_em, mes_fatura_original,
                                                    cartao_vinculado_id)  -- FIN-CARTOES-MULTIPLOS-01
            values (coalesce((select c.perfil_financeiro_id from public.conta c where c.id = v_fat), p_perfil_id),
                    p_cartao_id, null, (v_l ->> 'categoria_cartao_id')::integer, (v_l ->> 'categoria_id')::integer,
                    left(v_l ->> 'descricao_normalizada', 200), v_l ->> 'descricao_original', v_l ->> 'descricao_normalizada',
                    case when v_n > 1 and (v_l ->> 'gerar_parcelas_futuras')::boolean
                         then format('%s (%s/%s)', v_l ->> 'descricao_exibida', v_k, v_n) else v_l ->> 'descricao_exibida' end,
                    (v_l ->> 'valor')::numeric, ((v_l ->> 'data_compra')::date + make_interval(months => v_k - v_inicio))::date,
                    v_alvo, v_k, v_n, '', (v_l ->> 'recorrencia_id') is not null, (v_l ->> 'recorrencia_id')::integer,
                    v_compra, true, left(coalesce(v_l ->> 'origem_importacao', 'csv'), 20), now() at time zone 'utc',
                    nullif(v_orig, v_alvo), (v_l ->> 'cartao_vinculado_id')::integer)
            returning id into v_id;
            v_ids := v_ids || v_id;
            if not v_alvo = any(v_meses) then
                v_meses := v_meses || v_alvo;
            end if;
        end loop;
    end loop;
    -- FIN-CARTAO-NUBANK-CREDITOS-01: creditos da fatura. Fatura paga nao recebe credito (vai para a proxima aberta, como as compras);
    -- consolidada recusa a importacao inteira.
    for v_l in select e from jsonb_array_elements(v_creditos) e loop
        v_alvo := v_comp;
        v_passos := 0;
        loop
            v_fat := financeiro.fatura_do_mes(p_cartao_id, v_alvo);
            exit when v_fat is null or not financeiro.fatura_esta_paga(v_fat);
            v_alvo := (v_alvo + interval '1 month')::date;
            v_passos := v_passos + 1;
            if v_passos > 24 then
                raise exception 'Nao ha fatura aberta nos proximos 24 meses' using errcode = '22023';
            end if;
        end loop;
        v_fat := financeiro.garantir_fatura(p_perfil_id, p_cartao_id, v_alvo);
        perform 1 from public.conta where id = v_fat for update;
        if financeiro.fatura_esta_paga(v_fat) then
            raise exception 'A fatura de % foi paga durante a importacao. Revise e tente de novo.',
                to_char(v_alvo, 'MM/YYYY') using errcode = 'P0001';
        end if;
        if exists (select 1 from public.conta c where c.id = v_fat and c.status_fatura = 'FECHADA') then
            raise exception 'Importacao nao realizada: a fatura de % esta consolidada e o credito "%" cairia nela. Retire a linha ou importe em outra competencia.',
                to_char(v_alvo, 'MM/YYYY'), v_l ->> 'descricao_exibida' using errcode = 'P0001', hint = 'CONSOLIDADA';
        end if;
        -- FIN-CARTOES-MULTIPLOS-01: na reconstrucao a compra original vem no mesmo arquivo e ja foi gravada acima: o credito sem compra
        -- (e sem escolha do usuario) procura de novo, pelas mesmas regras da previa; vincula so a candidata unica.
        v_lanc_cred := (v_l -> 'credito' -> 'compra' ->> 'id')::integer;
        if v_lanc_cred is null and v_l -> 'credito' ->> 'natureza' in ('IOF_DEVOLVIDO', 'ESTORNO')
           and not coalesce((v_l -> 'credito' ->> 'escolhida')::boolean, false) then
            select case when jsonb_array_length(x -> 'credito' -> 'candidatas') = 1
                        then (x -> 'credito' -> 'candidatas' -> 0 ->> 'id')::integer end
              into v_lanc_cred
              from jsonb_array_elements(financeiro.analisar_importacao_cartao(p_perfil_id, p_cartao_id, v_comp,
                       jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
                           'linha_id', v_l ->> 'linha_id', 'data_compra', v_l ->> 'data_compra', 'valor', v_l ->> 'valor',
                           'descricao_original', v_l ->> 'descricao_original', 'descricao_normalizada', v_l ->> 'descricao_normalizada',
                           'tipo_movimento', 'credito', 'cartao_final', v_l ->> 'cartao_final',
                           'cartao_vinculado_escolhido_id', v_l -> 'cartao_vinculado_escolhido_id')))) -> 'linhas') x;
        end if;
        insert into financeiro.credito_fatura (perfil_financeiro_id, cartao_id, fatura_id, mes_fatura, mes_fatura_original,
                                               natureza, descricao, descricao_original, data_credito, valor, lancamento_id,
                                               chave, origem_importacao, operacao_chave, user_id, cartao_vinculado_id)
        values (coalesce((select c.perfil_financeiro_id from public.conta c where c.id = v_fat), p_perfil_id), p_cartao_id,
                v_fat, v_alvo, nullif(v_comp, v_alvo), v_l -> 'credito' ->> 'natureza',
                left(coalesce(nullif(v_l ->> 'descricao_exibida', ''), v_l ->> 'descricao_normalizada'), 200),
                v_l ->> 'descricao_original', (v_l ->> 'data_compra')::date, (v_l ->> 'valor')::numeric,
                v_lanc_cred, v_l ->> 'hash_deduplicacao',
                left(coalesce(v_l ->> 'origem_importacao', 'csv'), 20), p_chave, (select auth.uid()),
                (v_l ->> 'cartao_vinculado_id')::integer)  -- FIN-CARTOES-MULTIPLOS-01
        returning id into v_cid;
        v_cred_ids := v_cred_ids || v_cid;
        v_total_cred := v_total_cred + (v_l ->> 'valor')::numeric;
        if not v_alvo = any(v_meses) then
            v_meses := v_meses || v_alvo;
        end if;
    end loop;
    -- FIN-CARTAO-IMPORTACAO-FIXAS-01: conciliacoes pedidas na previa (previsao + cobranca ja lancada), sob as mesmas travas
    for v_l in select e from jsonb_array_elements(v_conciliar) e loop
        v_r := financeiro.conciliar_previsao_interna(p_perfil_id, (v_l -> 'conciliacao_sugerida' ->> 'previsto_id')::integer,
                                                     (v_l -> 'conciliacao_sugerida' ->> 'cobranca_id')::integer);
        v_conciliadas := v_conciliadas + 1;
        v_alvo := (v_r ->> 'fatura')::date;
        if not v_alvo = any(v_meses) then
            v_meses := v_meses || v_alvo;
        end if;
    end loop;
    -- e os apelidos de cobranca que o usuario pediu para lembrar (escolheu a recorrencia que a descricao nao reconhecia)
    for v_l in select e from jsonb_array_elements(v_a_gravar) e where coalesce((e ->> 'salvar_apelido')::boolean, false) loop
        perform financeiro.registrar_apelido_recorrencia(p_perfil_id, (v_l ->> 'recorrencia_id')::integer, v_l ->> 'apelido_sugerido');
        v_apelidos := v_apelidos + 1;
    end loop;
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, p_cartao_id, v_meses[i]);
    end loop;

    select count(*) into v_dup from jsonb_array_elements(v_analise -> 'linhas') e
     where e ->> 'status' in ('duplicado', 'conciliado');
    v_res := jsonb_build_object(
        'inseridos', cardinality(v_ids), 'linhas_importadas', jsonb_array_length(v_a_gravar), 'duplicados', v_dup,
        'realizadas', v_realizadas,
        'conciliadas', v_conciliadas, 'apelidos', v_apelidos,
        'creditos', cardinality(v_cred_ids), 'total_creditos', v_total_cred, 'creditos_ids', to_jsonb(v_cred_ids),
        'lancamentos', to_jsonb(v_ids), 'faturas', to_jsonb(v_meses), 'cartao_id', p_cartao_id,
        'competencia', to_char(v_comp, 'YYYY-MM'));
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'importar_fatura', v_res);
    return v_res;
end
$$;

-- fatura_por_categoria: texto de 20261212090000 + os trechos marcados.
create or replace function financeiro.fatura_por_categoria(p_perfil_id integer, p_cartao_id integer, p_mes date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes        date := date_trunc('month', p_mes::timestamp)::date;
    v_grupos     jsonb;
    v_total      numeric;
    v_com        numeric;
    v_sem        numeric;
    v_limite     numeric;
    v_vinculadas numeric;
    v_fixas      numeric;  -- FIN-CARTAO-DESPESAS-FIXAS-01
    v_parceladas numeric;
    v_pendente   numeric;  -- FIN-CARTAO-PREVISTO-EXECUTADO-01
    v_fatura     integer;  -- FIN-CARTAO-NUBANK-CREDITOS-01
    v_creditos   numeric;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    v_fatura := financeiro.fatura_do_mes(p_cartao_id, v_mes);
    v_creditos := financeiro.creditos_fatura(v_fatura);
    with lanc as (
        -- FIN-CARTAO-PREVISTO-EXECUTADO-01: valor = executado (a previsao pendente nao entra no gasto nem no total da fatura)
        select financeiro.valor_executado_compra(l.valor, sit.s) as valor, l.categoria_cartao_id, nat.n as natureza,
               case when sit.s = 'PREVISTA' then l.valor else 0 end as pendente
          from public.lancamento_agregado l
         cross join lateral (select financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) as n) nat
         cross join lateral (select financeiro.situacao_previsao(l.id, nat.n, l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
         where l.cartao_id = p_cartao_id and l.mes_fatura = v_mes
           and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
    ),
    limites as (
        select lim.id, lim.categoria_cartao_id, lim.limite_mensal from public.cartao_categoria_limite lim
         where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo
    ),
    grupos as (
        -- 1. limites ativos (na ordem do vinculo)
        select 1 as ordem, lim.id as ordem2, lim.categoria_cartao_id, lim.limite_mensal,
               coalesce((select sum(x.valor) from lanc x where x.natureza = 'CATEGORIA' and x.categoria_cartao_id = lim.categoria_cartao_id), 0) as gasto,
               (select count(*) from lanc x where x.natureza = 'CATEGORIA' and x.categoria_cartao_id = lim.categoria_cartao_id) as qtd,
               'categoria_cartao' as tipo
          from limites lim
        union all
        -- 2. categorias com lancamento mas sem limite ativo neste cartao
        select 2, min(cc.id), x.categoria_cartao_id, 0, sum(x.valor), count(*), 'categoria_sem_limite'
          from lanc x join public.categoria_cartao cc on cc.id = x.categoria_cartao_id
         where x.categoria_cartao_id is not null and x.natureza = 'CATEGORIA'
           and x.categoria_cartao_id not in (select l2.categoria_cartao_id from limites l2)
         group by x.categoria_cartao_id
        union all
        -- 3 e 4. FIN-CARTAO-DESPESAS-FIXAS-01: obrigacoes ja contratadas, fora das Categorias do Cartao (nao consomem limite)
        select 3, 0, null, null, sum(x.valor), count(*), 'compras_parceladas'
          from lanc x where x.natureza = 'PARCELADA' having count(*) > 0
        union all
        select 4, 0, null, null, sum(x.valor), count(*), 'despesas_fixas'
          from lanc x where x.natureza = 'FIXA' having count(*) > 0
        union all
        -- 5. sem Categoria do Cartao (o que nao e parcelada nem fixa)
        select 5, 0, null, null, sum(x.valor), count(*), 'sem_categoria'
          from lanc x where x.natureza = 'OUTROS' having count(*) > 0
        union all
        -- 6. FIN-CARTAO-NUBANK-CREDITOS-01: creditos da fatura (estorno, IOF devolvido, ajuste), negativos: abatem o valor a pagar
        select 6, 0, null, null, -sum(cf.valor), count(*), 'creditos'
          from financeiro.credito_fatura cf where cf.fatura_id = v_fatura having count(*) > 0
    )
    select coalesce(jsonb_agg(jsonb_build_object(
               -- os grupos de parceladas e fixas levam o proprio filtro de "Ver lancamentos" (tela de Cartoes)
               'categoria_cartao_id', case when g.tipo in ('compras_parceladas', 'despesas_fixas', 'creditos') then to_jsonb(g.tipo)
                                           else to_jsonb(g.categoria_cartao_id) end,
               'categoria_cartao_nome', case g.tipo when 'sem_categoria' then 'Sem Categoria do Cartao'
                                                    when 'compras_parceladas' then 'Compras parceladas'
                                                    when 'despesas_fixas' then 'Despesas fixas'
                                                    when 'creditos' then 'Creditos e ajustes'
                                                    else coalesce(cc.nome, 'Categoria do Cartao') end,
               'natureza', case g.tipo when 'compras_parceladas' then 'PARCELADA' when 'despesas_fixas' then 'FIXA'
                                       when 'creditos' then 'CREDITO'
                                       when 'sem_categoria' then 'OUTROS' else 'CATEGORIA' end,
               'previsto_pendente', case when g.tipo = 'despesas_fixas' then (select coalesce(sum(x.pendente), 0) from lanc x) end,
               'categoria_cartao_cor', cc.cor,
               'categoria_cartao_icone', cc.icone,
               'limite_mensal', g.limite_mensal,
               'gasto_atual', g.gasto,
               'disponivel', case when g.tipo = 'categoria_cartao' then g.limite_mensal - g.gasto end,
               'percentual', case when g.tipo = 'categoria_cartao' then
                   case when g.limite_mensal > 0 then round(g.gasto / g.limite_mensal * 100, 2) else 0 end end,
               'percentual_utilizado', case when g.tipo = 'categoria_cartao' then
                   case when g.limite_mensal > 0 then round(g.gasto / g.limite_mensal * 100, 2) else 0 end end,
               'status', case when g.tipo = 'categoria_cartao' then financeiro.status_consumo(g.gasto, g.limite_mensal)
                              when g.tipo in ('compras_parceladas', 'despesas_fixas') then 'Contratada'
                              when g.tipo = 'creditos' then 'Abatido'
                              else 'Revisar' end,
               'quantidade_lancamentos', g.qtd,
               'vinculada_ao_cartao', g.tipo = 'categoria_cartao',
               'sem_categoria', g.tipo = 'sem_categoria',
               'categoria_sem_limite', g.tipo = 'categoria_sem_limite',
               'avisos', case g.tipo when 'sem_categoria' then '["Lancamentos sem Categoria do Cartao devem ser revisados."]'::jsonb
                                     when 'categoria_sem_limite' then '["Categoria sem limite neste cartao."]'::jsonb
                                     when 'compras_parceladas' then '["Parcelas ja contratadas: nao consomem limite de Categoria do Cartao."]'::jsonb
                                     when 'creditos' then '["Estornos, IOF devolvido e ajustes da administradora: abatem o valor a pagar; a compra original continua registrada."]'::jsonb
                                     when 'despesas_fixas' then case when (select coalesce(sum(x.pendente), 0) from lanc x) > 0
                                         then jsonb_build_array('R$ ' || to_char((select sum(x.pendente) from lanc x), 'FM999999990.00')
                                                                || ' previstos aguardando cobranca: fora do executado e do valor a pagar.')
                                         else '["Recorrencias do cartao: nao consomem limite de Categoria do Cartao."]'::jsonb end
                                     else '[]'::jsonb end,
               'tipo_grupo', g.tipo) order by g.ordem, g.ordem2), '[]'::jsonb)
      into v_grupos
      from grupos g left join public.categoria_cartao cc on cc.id = g.categoria_cartao_id;

    select coalesce(sum(ex.v), 0),
           coalesce(sum(ex.v) filter (where nat.n = 'CATEGORIA'), 0),
           coalesce(sum(ex.v) filter (where nat.n = 'OUTROS'), 0),
           coalesce(sum(ex.v) filter (where nat.n = 'FIXA'), 0),
           coalesce(sum(ex.v) filter (where nat.n = 'PARCELADA'), 0),
           coalesce(sum(ex.v) filter (where nat.n = 'CATEGORIA' and l.categoria_cartao_id in (
               select lim.categoria_cartao_id from public.cartao_categoria_limite lim
                where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo)), 0)
           , coalesce(sum(l.valor) filter (where sit.s = 'PREVISTA'), 0)
      into v_total, v_com, v_sem, v_fixas, v_parceladas, v_vinculadas, v_pendente
      from public.lancamento_agregado l
     cross join lateral (select financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) as n) nat  -- FIN-CARTAO-DESPESAS-FIXAS-01
     cross join lateral (select financeiro.situacao_previsao(l.id, nat.n, l.is_importado, l.cartao_id, l.mes_fatura) as s) sit  -- FIN-CARTAO-PREVISTO-EXECUTADO-01
     cross join lateral (select financeiro.valor_executado_compra(l.valor, sit.s) as v) ex
     where l.cartao_id = p_cartao_id and l.mes_fatura = v_mes
       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id);
    select coalesce(sum(lim.limite_mensal), 0) into v_limite from public.cartao_categoria_limite lim
     where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo;

    return jsonb_build_object(
        'cartao_id', p_cartao_id,
        'mes_referencia', to_char(v_mes, 'YYYY-MM'),
        -- FIN-CARTAO-NUBANK-CREDITOS-01: total da fatura = valor a pagar (compras executadas - creditos)
        'total_fatura', v_total - v_creditos,
        'total_compras', v_total,
        'total_creditos', v_creditos,
        -- FIN-CARTOES-MULTIPLOS-01: a fatura (unica do contrato) por cartao vinculado; o que nao tem cartao identificado, a parte
        'por_cartao', financeiro.fatura_por_cartao(p_perfil_id, p_cartao_id, v_mes),
        'total_com_categoria', v_com,
        'total_sem_categoria_cartao', v_sem,
        'total_despesas_fixas', v_fixas,
        'total_compras_parceladas', v_parceladas,
        'total_previsto_pendente', v_pendente,
        'limite_total', v_limite,
        'disponivel_total', v_limite - v_vinculadas,
        'percentual_total', case when v_limite > 0 then round(v_vinculadas / v_limite * 100, 2) else 0 end,
        'status_total', financeiro.status_consumo(v_vinculadas, v_limite),
        'situacao_fatura', financeiro.situacao_fatura(financeiro.fatura_do_mes(p_cartao_id, v_mes)),
        'categorias', v_grupos);
end
$$;

-- lancamentos_fatura_por_categoria: texto de 20261212090000 + os trechos marcados.
create or replace function financeiro.lancamentos_fatura_por_categoria(p_perfil_id integer, p_cartao_id integer, p_mes date,
                                                            p_filtro text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes    date := date_trunc('month', p_mes::timestamp)::date;
    v_filtro text := coalesce(nullif(btrim(p_filtro), ''), 'todos');
    v_cc     integer;
    v_gerir  boolean;
    v_cv     integer;  -- FIN-CARTOES-MULTIPLOS-01
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    if v_filtro ~ '^cartao-[0-9]{1,9}$' then  -- FIN-CARTOES-MULTIPLOS-01: compras e creditos de um cartao vinculado (0 = sem cartao)
        v_cv := substring(v_filtro from 8)::integer;
    elsif v_filtro not in ('todos', 'sem_categoria', 'despesas_fixas', 'compras_parceladas', 'creditos') then  -- FIN-CARTAO-DESPESAS-FIXAS-01, FIN-CARTAO-NUBANK-CREDITOS-01
        if v_filtro !~ '^[0-9]{1,9}$' then
            raise exception 'categoria_cartao_id invalido' using errcode = '22023';
        end if;
        v_cc := v_filtro::integer;
    end if;
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    return jsonb_build_object(
        'cartao_id', p_cartao_id,
        'mes_referencia', to_char(v_mes, 'YYYY-MM'),
        'categoria_cartao_id', v_filtro,
        'lancamentos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', l.id,
                       'data', l.data_compra,
                       'descricao', coalesce(nullif(l.descricao_exibida, ''), l.descricao),
                       'descricao_original', coalesce(l.descricao_original, l.descricao),
                       'valor', l.valor,
                       'categoria_id', l.categoria_id,
                       'categoria_nome', cat.nome,
                       'categoria_cartao_id', l.categoria_cartao_id,
                       'categoria_cartao_nome', cc.nome,
                       'origem', coalesce(l.origem_importacao, case when coalesce(l.is_recorrente, false) then 'recorrencia'
                                                                    else 'manual' end),
                       'parcela_atual', l.numero_parcela,
                       'parcelas_total', l.total_parcelas,
                       'compra_id', l.compra_id,
                       'cartao_vinculado', (select jsonb_build_object('id', v.id, 'nome', v.nome, 'final', v.final, 'tipo', v.tipo, 'situacao', v.situacao)
                                    from financeiro.cartao_vinculado v where v.id = l.cartao_vinculado_id),
                       'natureza', nat.n,
                       -- FIN-CARTAO-PREVISTO-EXECUTADO-01: situacao da previsao, previsto e executado da compra
                       'situacao_ocorrencia', sit.s,
                       'valor_previsto', case when nat.n = 'FIXA' then coalesce((select o.valor_previsto
                           from financeiro.ocorrencia_recorrencia_cartao o where o.lancamento_id = l.id and o.revertida_em is null), l.valor) end,
                       'valor_executado', financeiro.valor_executado_compra(l.valor, sit.s),
                       'status_classificacao', case
                           when nat.n in ('PARCELADA', 'FIXA') then 'classificado'  -- nao precisam de Categoria do Cartao
                           when l.categoria_cartao_id is null then 'sem_categoria_cartao'
                           when not exists (select 1 from public.cartao_categoria_limite lim
                                             where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id
                                               and lim.ativo and lim.categoria_cartao_id = l.categoria_cartao_id)
                               then 'categoria_sem_limite'
                           else 'classificado' end,
                       'bloqueio', financeiro.bloqueio_da_parcela(l.id),
                       'pode_editar', v_gerir and financeiro.bloqueio_da_parcela(l.id) is null,
                       'versao', financeiro.versao_compra(l.id))
                   order by l.data_compra, l.id)
              from public.lancamento_agregado l
              left join public.categoria cat on cat.id = l.categoria_id
              left join public.categoria_cartao cc on cc.id = l.categoria_cartao_id
             cross join lateral (select financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) as n) nat
             cross join lateral (select financeiro.situacao_previsao(l.id, nat.n, l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
             where l.cartao_id = p_cartao_id and l.mes_fatura = v_mes
               and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
               and (v_filtro = 'todos' or (v_cv is not null and coalesce(l.cartao_vinculado_id, 0) = v_cv)
                    or (v_filtro = 'sem_categoria' and nat.n = 'OUTROS')
                    or (v_filtro = 'despesas_fixas' and nat.n = 'FIXA')
                    or (v_filtro = 'compras_parceladas' and nat.n = 'PARCELADA')
                    or (nat.n = 'CATEGORIA' and l.categoria_cartao_id = v_cc))), '[]'::jsonb)
            -- FIN-CARTAO-NUBANK-CREDITOS-01: creditos da fatura, negativos e sem acoes de compra (identificador proprio)
            || coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', 'credito-' || cf.id,
                       'credito_id', cf.id,
                       'data', cf.data_credito,
                       'descricao', cf.descricao,
                       'descricao_original', coalesce(cf.descricao_original, cf.descricao),
                       'valor', -cf.valor,
                       'categoria_id', null,
                       'categoria_nome', case cf.natureza when 'ESTORNO' then 'Estorno de compra'
                                                         when 'IOF_DEVOLVIDO' then 'Devolucao de IOF'
                                                         else 'Credito ou ajuste da fatura' end,
                       'categoria_cartao_id', null,
                       'categoria_cartao_nome', null,
                       'origem', cf.origem_importacao,
                       'parcela_atual', null,
                       'parcelas_total', null,
                       'compra_id', null,
                       'cartao_vinculado', (select jsonb_build_object('id', v.id, 'nome', v.nome, 'final', v.final, 'tipo', v.tipo, 'situacao', v.situacao)
                                    from financeiro.cartao_vinculado v where v.id = cf.cartao_vinculado_id),
                       'natureza', 'CREDITO',
                       'natureza_credito', cf.natureza,
                       'compra_original', case when o.id is not null then jsonb_build_object(
                           'id', o.id, 'descricao', coalesce(nullif(o.descricao_exibida, ''), o.descricao), 'valor', o.valor,
                           'data_compra', o.data_compra) end,
                       'valor_executado', -cf.valor,
                       'status_classificacao', 'classificado',
                       'bloqueio', 'Credito da fatura',
                       'pode_editar', false,
                       'versao', null)
                   order by cf.data_credito, cf.id)
              from financeiro.credito_fatura cf
              left join public.lancamento_agregado o on o.id = cf.lancamento_id
             where (v_filtro in ('todos', 'creditos') or (v_cv is not null and coalesce(cf.cartao_vinculado_id, 0) = v_cv))
               and cf.fatura_id = financeiro.fatura_do_mes(p_cartao_id, v_mes)), '[]'::jsonb));
end
$$;

revoke execute on function financeiro.cartoes_vinculados(integer, integer) from public, anon;
revoke execute on function financeiro.salvar_cartao_vinculado(integer, integer, integer, jsonb, text) from public, anon;
revoke execute on function financeiro.previa_limpeza_importacoes(integer, integer, date) from public, anon;
revoke execute on function financeiro.limpar_importacoes_cartao(integer, integer, date, text, uuid) from public, anon;
grant execute on function financeiro.cartoes_vinculados(integer, integer) to authenticated;
grant execute on function financeiro.salvar_cartao_vinculado(integer, integer, integer, jsonb, text) to authenticated;
grant execute on function financeiro.previa_limpeza_importacoes(integer, integer, date) to authenticated;
grant execute on function financeiro.limpar_importacoes_cartao(integer, integer, date, text, uuid) to authenticated;
