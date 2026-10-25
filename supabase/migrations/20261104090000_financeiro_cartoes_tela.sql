-- FIN-FIDELIDADE-CARTOES-1 — funcoes da tela original de Cartoes do Flask (frontend/templates/cartoes.html).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261104090000).
-- Validada em cluster local descartavel (tests/test_supabase_cartoes_tela.py). Docs: docs/FIN_FIDELIDADE_CARTOES_1.md.
--
-- Nenhuma tabela nova, nenhuma coluna nova, nenhum dado existente alterado pela migration.
-- Funcoes novas (como as rotas do Flask, com as regras do novo aplicativo):
-- - categorias_cartao_do_perfil: GET /api/categorias-cartao;
-- - cartoes_da_tela: GET /api/cartoes (com o emissor; nunca numero completo, validade nem CVV);
-- - limites_do_cartao, vincular_limite_cartao, atualizar_limite_cartao, desativar_limite_cartao:
--   /api/cartoes/<id>/categorias-limite (CategoriaCartaoService);
-- - fatura_por_categoria, lancamentos_fatura_por_categoria: /api/cartoes/<id>/fatura-categorias e fatura-lancamentos
--   (CartaoService.obter_resumo_fatura_por_categoria_cartao e listar_lancamentos_fatura_por_categoria_cartao);
-- - editar_lancamento_cartao: PUT /api/cartoes/lancamentos/<id> (so este lancamento), sem trocar numero nem total
--   de parcelas (no Flask isso desmonta o parcelamento) e sem tocar fatura paga, fechada ou de recorrencia;
-- - parcelamento_da_compra, editar_parcelas_futuras, cancelar_parcelas_futuras: /api/cartoes/lancamentos/<id>/parcelamento
--   (so parcelas futuras em fatura aberta, como CartaoService; travas e versao de travar_compra).
-- Funcoes trocadas (create or replace, mesma assinatura e privilegios): ler_dados_cartao, criar_cartao e editar_cartao
-- passam a gravar o emissor ("Banco / Emissor", item_despesa.descricao) e "Possui codigo de seguranca"
-- (config_agregador.tem_codigo, so a marcacao). Numero, validade e CVV continuam recusados.

-- ===========================================================================================================
-- Cadastro do cartao: emissor e "possui codigo" (o resto identico a 20261030090000)
-- ===========================================================================================================

create or replace function financeiro.ler_dados_cartao(p_dados jsonb, p_parcial boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_saida jsonb := '{}'::jsonb;
    v_texto text;
    v_int   integer;
    v_valor numeric;
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do cartao invalidos' using errcode = '22023';
    end if;
    if p_dados ?| array['numero_cartao', 'codigo_seguranca', 'data_validade'] then
        raise exception 'Numero, validade e codigo de seguranca nao sao tratados no novo aplicativo' using errcode = '22023';
    end if;
    if p_dados ? 'nome' or not p_parcial then
        v_texto := btrim(coalesce(p_dados ->> 'nome', ''));
        if v_texto = '' or length(v_texto) > 100 then
            raise exception 'Nome do cartao obrigatorio (ate 100 caracteres)' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('nome', v_texto);
    end if;
    foreach v_texto in array array['dia_fechamento', 'dia_vencimento'] loop
        if p_dados ? v_texto or not p_parcial then
            begin
                v_int := (p_dados ->> v_texto)::integer;
            exception when others then
                v_int := null;
            end;
            if v_int is null or v_int not between 1 and 31 then
                raise exception 'Dias de fechamento e vencimento devem ficar entre 1 e 31' using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object(v_texto, v_int);
        end if;
    end loop;
    if p_dados ? 'compra_no_fechamento' then
        if coalesce(p_dados ->> 'compra_no_fechamento', '') not in ('ATUAL', 'PROXIMO') then
            raise exception 'Regra da compra no dia do fechamento invalida (ATUAL ou PROXIMO)' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('compra_no_fechamento', p_dados ->> 'compra_no_fechamento');
    end if;
    if p_dados ? 'fechamento_confirmado' then
        if jsonb_typeof(p_dados -> 'fechamento_confirmado') <> 'boolean' then
            raise exception 'Confirmacao do fechamento invalida' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('fechamento_confirmado', (p_dados ->> 'fechamento_confirmado')::boolean);
    end if;
    if p_dados ? 'limite_credito' then
        if nullif(p_dados ->> 'limite_credito', '') is null then
            v_saida := v_saida || jsonb_build_object('limite_credito', null);
        else
            begin
                v_valor := (p_dados ->> 'limite_credito')::numeric;
            exception when others then
                v_valor := null;
            end;
            if v_valor is null or v_valor < 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
                raise exception 'Limite de credito invalido' using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object('limite_credito', v_valor);
        end if;
    end if;
    if p_dados ? 'observacoes' then
        v_saida := v_saida || jsonb_build_object('observacoes', left(coalesce(p_dados ->> 'observacoes', ''), 1000));
    end if;
    -- FIN-FIDELIDADE-CARTOES-1: emissor (texto livre do Flask) e a marcacao "possui codigo" (nunca o codigo).
    if p_dados ? 'descricao' then
        v_saida := v_saida || jsonb_build_object('descricao', left(btrim(coalesce(p_dados ->> 'descricao', '')), 500));
    end if;
    if p_dados ? 'tem_codigo' then
        if jsonb_typeof(p_dados -> 'tem_codigo') <> 'boolean' then
            raise exception 'Marcacao do codigo de seguranca invalida' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('tem_codigo', (p_dados ->> 'tem_codigo')::boolean);
    end if;
    return v_saida;
end
$$;

create or replace function financeiro.criar_cartao(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_cartao;
    v_d        jsonb;
    v_cat      integer;
    v_id       integer;
    v_res      jsonb;
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
    v_d := financeiro.ler_dados_cartao(p_dados, false);
    select c.id into v_cat from public.categoria c where c.nome = 'Cartoes de Credito' order by c.id limit 1;  -- como o Flask
    insert into public.item_despesa (perfil_financeiro_id, categoria_id, nome, tipo, descricao, ativo, recorrente,
                                     tipo_recorrencia, pago, criado_em)
    values (p_perfil_id, v_cat, v_d ->> 'nome', 'Agregador', coalesce(v_d ->> 'descricao', ''), true, true, 'mensal', false,
            now() at time zone 'utc')
    returning id into v_id;
    insert into public.config_agregador (item_despesa_id, dia_fechamento, dia_vencimento, limite_credito, tem_codigo,
                                         observacoes, criado_em, compra_no_fechamento, fechamento_confirmado)
    values (v_id, (v_d ->> 'dia_fechamento')::integer, (v_d ->> 'dia_vencimento')::integer,
            (v_d ->> 'limite_credito')::numeric, coalesce((v_d ->> 'tem_codigo')::boolean, true),
            coalesce(v_d ->> 'observacoes', ''), now() at time zone 'utc',
            coalesce(v_d ->> 'compra_no_fechamento', 'PROXIMO'), coalesce((v_d ->> 'fechamento_confirmado')::boolean, false));
    v_res := jsonb_build_object('cartao_id', v_id);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_cartao', v_res);
    return v_res;
end
$$;

create or replace function financeiro.editar_cartao(p_perfil_id integer, p_cartao_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    perform 1 from public.item_despesa where id = p_cartao_id for update;
    perform 1 from public.config_agregador where item_despesa_id = p_cartao_id for update;
    if p_versao is distinct from (select c.versao from financeiro.cartoes_do_perfil(p_perfil_id) c where c.id = p_cartao_id) then
        raise exception 'O cartao foi alterado por outra operacao. Recarregue e tente de novo.' using errcode = 'P0001';
    end if;
    v_d := financeiro.ler_dados_cartao(p_dados, true);
    update public.item_despesa
       set nome = coalesce(v_d ->> 'nome', nome),
           descricao = case when v_d ? 'descricao' then v_d ->> 'descricao' else descricao end
     where id = p_cartao_id;
    -- Faturas ja criadas mantem o vencimento gravado; o novo dia vale para as proximas. Compras ja lancadas
    -- nao mudam de fatura por causa da nova configuracao.
    update public.config_agregador cfg
       set dia_fechamento = coalesce((v_d ->> 'dia_fechamento')::integer, cfg.dia_fechamento),
           dia_vencimento = coalesce((v_d ->> 'dia_vencimento')::integer, cfg.dia_vencimento),
           limite_credito = case when v_d ? 'limite_credito' then (v_d ->> 'limite_credito')::numeric else cfg.limite_credito end,
           observacoes = case when v_d ? 'observacoes' then v_d ->> 'observacoes' else cfg.observacoes end,
           tem_codigo = coalesce((v_d ->> 'tem_codigo')::boolean, cfg.tem_codigo),
           compra_no_fechamento = coalesce(v_d ->> 'compra_no_fechamento', cfg.compra_no_fechamento),
           fechamento_confirmado = case
               when v_d ? 'fechamento_confirmado' then (v_d ->> 'fechamento_confirmado')::boolean
               when (v_d ? 'dia_fechamento' and (v_d ->> 'dia_fechamento')::integer <> cfg.dia_fechamento)
                    or (v_d ? 'dia_vencimento' and (v_d ->> 'dia_vencimento')::integer <> cfg.dia_vencimento)
                    or (v_d ? 'compra_no_fechamento' and v_d ->> 'compra_no_fechamento' <> cfg.compra_no_fechamento)
                    then false
               else cfg.fechamento_confirmado end
     where cfg.item_despesa_id = p_cartao_id;
    return jsonb_build_object('cartao_id', p_cartao_id);
end
$$;

-- ===========================================================================================================
-- Leituras da tela
-- ===========================================================================================================

-- Cartoes do perfil para a tela original: cartoes_do_perfil (versao inclusive) + emissor e "possui codigo".
create function financeiro.cartoes_da_tela(p_perfil_id integer)
    returns table (id integer, nome text, descricao text, ativo boolean, dia_fechamento integer, dia_vencimento integer,
                   limite_credito numeric, final_numero text, observacoes text, versao text,
                   compra_no_fechamento text, fechamento_confirmado boolean, tem_codigo boolean)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    return query  -- cartoes_do_perfil confere o acesso ao perfil
        select c.id, c.nome, coalesce(i.descricao, '')::text, c.ativo, c.dia_fechamento, c.dia_vencimento,
               c.limite_credito, c.final_numero, c.observacoes, c.versao, c.compra_no_fechamento,
               c.fechamento_confirmado, coalesce(cfg.tem_codigo, true)
          from financeiro.cartoes_do_perfil(p_perfil_id) c
          join public.item_despesa i on i.id = c.id
          left join public.config_agregador cfg on cfg.item_despesa_id = c.id;
end
$$;

-- Categorias do Cartao do perfil (NULL conta como Pessoal), como CategoriaCartaoService.listar_categorias.
create function financeiro.categorias_cartao_do_perfil(p_perfil_id integer)
    returns table (id integer, nome text, descricao text, cor text, icone text, ativo boolean)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return query
        select cc.id, cc.nome::text, cc.descricao::text, cc.cor::text, cc.icone::text, cc.ativo
          from public.categoria_cartao cc
         where financeiro.pertence_ao_perfil(cc.perfil_financeiro_id, p_perfil_id)
         order by cc.nome, cc.id;
end
$$;

-- Gasto de uma Categoria do Cartao na fatura do mes (lancamentos do perfil; NULL conta como Pessoal). Interna.
create function financeiro.gasto_categoria_fatura(p_perfil_id integer, p_cartao_id integer, p_categoria_cartao_id integer,
                                                  p_mes date)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce(sum(l.valor), 0) from public.lancamento_agregado l
     where l.cartao_id = p_cartao_id and l.categoria_cartao_id = p_categoria_cartao_id and l.mes_fatura = p_mes
       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
$$;

-- Status do consumo como CartaoService._status_consumo (Normal, Atencao acima de 80%, Estourado acima de 100%). Interna.
create function financeiro.status_consumo(p_gasto numeric, p_limite numeric)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select case when coalesce(p_limite, 0) <= 0 then case when coalesce(p_gasto, 0) > 0 then 'Estourado' else 'Normal' end
                when p_gasto / p_limite * 100 > 100 then 'Estourado'
                when p_gasto / p_limite * 100 > 80 then 'Atencao'
                else 'Normal' end
$$;

-- Limites do cartao (vinculos com Categorias do Cartao) e o gasto no mes, como GET /categorias-limite.
create function financeiro.limites_do_cartao(p_perfil_id integer, p_cartao_id integer, p_mes date)
    returns table (id integer, cartao_id integer, categoria_cartao_id integer, categoria_cartao_nome text,
                   limite_mensal numeric, ativo boolean, gasto_atual numeric, disponivel numeric,
                   percentual_utilizado numeric)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes date := date_trunc('month', p_mes::timestamp)::date;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    return query
        select lim.id, lim.cartao_id, lim.categoria_cartao_id, cc.nome::text, lim.limite_mensal, lim.ativo, g.gasto,
               lim.limite_mensal - g.gasto,
               case when lim.limite_mensal > 0 then round(g.gasto / lim.limite_mensal * 100, 2) else 0 end
          from public.cartao_categoria_limite lim
          join public.categoria_cartao cc on cc.id = lim.categoria_cartao_id
          cross join lateral (select financeiro.gasto_categoria_fatura(p_perfil_id, p_cartao_id, lim.categoria_cartao_id,
                                                                       v_mes) as gasto) g
         where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id  -- como listar_limites_cartao
         order by lim.id;
end
$$;

-- Fatura do mes por Categoria do Cartao (CartaoService.obter_resumo_fatura_por_categoria_cartao): grupos dos limites
-- ativos, categorias sem limite neste cartao e "sem categoria"; totais e status como o Flask.
create function financeiro.fatura_por_categoria(p_perfil_id integer, p_cartao_id integer, p_mes date)
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
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    with lanc as (
        select l.valor, l.categoria_cartao_id from public.lancamento_agregado l
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
               coalesce((select sum(x.valor) from lanc x where x.categoria_cartao_id = lim.categoria_cartao_id), 0) as gasto,
               (select count(*) from lanc x where x.categoria_cartao_id = lim.categoria_cartao_id) as qtd,
               'categoria_cartao' as tipo
          from limites lim
        union all
        -- 2. categorias com lancamento mas sem limite ativo neste cartao
        select 2, min(cc.id), x.categoria_cartao_id, 0, sum(x.valor), count(*), 'categoria_sem_limite'
          from lanc x join public.categoria_cartao cc on cc.id = x.categoria_cartao_id
         where x.categoria_cartao_id is not null
           and x.categoria_cartao_id not in (select l2.categoria_cartao_id from limites l2)
         group by x.categoria_cartao_id
        union all
        -- 3. sem Categoria do Cartao
        select 3, 0, null, null, sum(x.valor), count(*), 'sem_categoria'
          from lanc x where x.categoria_cartao_id is null having count(*) > 0
    )
    select coalesce(jsonb_agg(jsonb_build_object(
               'categoria_cartao_id', g.categoria_cartao_id,
               'categoria_cartao_nome', case when g.tipo = 'sem_categoria' then 'Sem Categoria do Cartao'
                                             else coalesce(cc.nome, 'Categoria do Cartao') end,
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
                              else 'Revisar' end,
               'quantidade_lancamentos', g.qtd,
               'vinculada_ao_cartao', g.tipo = 'categoria_cartao',
               'sem_categoria', g.tipo = 'sem_categoria',
               'categoria_sem_limite', g.tipo = 'categoria_sem_limite',
               'avisos', case g.tipo when 'sem_categoria' then '["Lancamentos sem Categoria do Cartao devem ser revisados."]'::jsonb
                                     when 'categoria_sem_limite' then '["Categoria sem limite neste cartao."]'::jsonb
                                     else '[]'::jsonb end,
               'tipo_grupo', g.tipo) order by g.ordem, g.ordem2), '[]'::jsonb)
      into v_grupos
      from grupos g left join public.categoria_cartao cc on cc.id = g.categoria_cartao_id;

    select coalesce(sum(l.valor), 0),
           coalesce(sum(l.valor) filter (where l.categoria_cartao_id is not null), 0),
           coalesce(sum(l.valor) filter (where l.categoria_cartao_id is null), 0),
           coalesce(sum(l.valor) filter (where l.categoria_cartao_id in (
               select lim.categoria_cartao_id from public.cartao_categoria_limite lim
                where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo)), 0)
      into v_total, v_com, v_sem, v_vinculadas
      from public.lancamento_agregado l
     where l.cartao_id = p_cartao_id and l.mes_fatura = v_mes
       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id);
    select coalesce(sum(lim.limite_mensal), 0) into v_limite from public.cartao_categoria_limite lim
     where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo;

    return jsonb_build_object(
        'cartao_id', p_cartao_id,
        'mes_referencia', to_char(v_mes, 'YYYY-MM'),
        'total_fatura', v_total,
        'total_com_categoria', v_com,
        'total_sem_categoria_cartao', v_sem,
        'limite_total', v_limite,
        'disponivel_total', v_limite - v_vinculadas,
        'percentual_total', case when v_limite > 0 then round(v_vinculadas / v_limite * 100, 2) else 0 end,
        'status_total', financeiro.status_consumo(v_vinculadas, v_limite),
        'situacao_fatura', financeiro.situacao_fatura(financeiro.fatura_do_mes(p_cartao_id, v_mes)),
        'categorias', v_grupos);
end
$$;

-- Lancamentos da fatura (CartaoService.listar_lancamentos_fatura_por_categoria_cartao), filtro 'todos',
-- 'sem_categoria' ou o id da Categoria do Cartao; com o bloqueio de cada um (regra do novo aplicativo).
create function financeiro.lancamentos_fatura_por_categoria(p_perfil_id integer, p_cartao_id integer, p_mes date,
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
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    if v_filtro not in ('todos', 'sem_categoria') then
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
                       'status_classificacao', case
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
             where l.cartao_id = p_cartao_id and l.mes_fatura = v_mes
               and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
               and (v_filtro = 'todos' or (v_filtro = 'sem_categoria' and l.categoria_cartao_id is null)
                    or l.categoria_cartao_id = v_cc)), '[]'::jsonb));
end
$$;

-- ===========================================================================================================
-- Limites por Categoria do Cartao (CategoriaCartaoService)
-- ===========================================================================================================

-- Valor do limite mensal: zero ou positivo, 2 casas (vazio = 0, como _parse_decimal). Interna.
create function financeiro.ler_limite_mensal(p_valor text)
    returns numeric
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_valor numeric;
begin
    if nullif(btrim(coalesce(p_valor, '')), '') is null then
        return 0;
    end if;
    begin
        v_valor := p_valor::numeric;
    exception when others then
        v_valor := null;
    end;
    if v_valor is null or v_valor < 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
        raise exception 'Limite mensal invalido (zero ou positivo, ate 2 casas decimais)' using errcode = '22023';
    end if;
    return v_valor;
end
$$;

-- Vincula (ou atualiza o vinculo existente, como vincular_categoria_cartao_ao_cartao) uma Categoria do Cartao
-- ativa do perfil ao cartao do perfil, com o limite mensal. Unico por cartao + categoria.
create function financeiro.vincular_limite_cartao(p_perfil_id integer, p_cartao_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_cc     integer;
    v_limite numeric;
    v_ativo  boolean;
    v_id     integer;
    v_criado boolean;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' or coalesce(p_dados ->> 'categoria_cartao_id', '') !~ '^[0-9]{1,9}$' then
        raise exception 'categoria_cartao_id invalido' using errcode = '22023';
    end if;
    v_cc := (p_dados ->> 'categoria_cartao_id')::integer;
    if not exists (select 1 from public.categoria_cartao cc where cc.id = v_cc and cc.ativo
                    and financeiro.pertence_ao_perfil(cc.perfil_financeiro_id, p_perfil_id)) then
        raise exception 'Categoria do Cartao nao encontrada neste perfil (ou inativa)' using errcode = '22023';
    end if;
    v_limite := financeiro.ler_limite_mensal(p_dados ->> 'limite_mensal');
    if p_dados ? 'ativo' and jsonb_typeof(p_dados -> 'ativo') <> 'boolean' then
        raise exception 'Situacao do vinculo invalida' using errcode = '22023';
    end if;
    v_ativo := coalesce((p_dados ->> 'ativo')::boolean, true);
    perform 1 from public.item_despesa where id = p_cartao_id for update;  -- serializa os vinculos do cartao
    select lim.id into v_id from public.cartao_categoria_limite lim
     where lim.cartao_id = p_cartao_id and lim.categoria_cartao_id = v_cc for update;
    v_criado := v_id is null;
    if v_criado then
        insert into public.cartao_categoria_limite (perfil_financeiro_id, cartao_id, categoria_cartao_id, limite_mensal,
                                                    ativo, created_at, updated_at)
        values (p_perfil_id, p_cartao_id, v_cc, v_limite, v_ativo, now() at time zone 'utc', now() at time zone 'utc')
        returning id into v_id;
    else
        if not exists (select 1 from public.cartao_categoria_limite lim where lim.id = v_id
                        and lim.perfil_financeiro_id = p_perfil_id) then
            raise exception 'Esta categoria ja tem um vinculo legado (sem perfil) neste cartao: ajuste-o no sistema atual'
                using errcode = '22023';
        end if;
        update public.cartao_categoria_limite
           set limite_mensal = v_limite, ativo = v_ativo, vigencia_inicio = null, vigencia_fim = null,
               updated_at = now() at time zone 'utc'
         where id = v_id;
    end if;
    return jsonb_build_object('limite_id', v_id, 'criado', v_criado);
end
$$;

-- Trava o vinculo do cartao e do perfil ou erro. Interna.
create function financeiro.travar_limite_cartao(p_perfil_id integer, p_cartao_id integer, p_limite_id integer)
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
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    perform 1 from public.item_despesa where id = p_cartao_id for update;
    perform 1 from public.cartao_categoria_limite lim
     where lim.id = p_limite_id and lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id for update;
    if not found then
        raise exception 'Limite nao encontrado neste cartao' using errcode = '42501';
    end if;
end
$$;

-- Atualiza limite mensal e/ou situacao (atualizar_limite); campo ausente fica como esta.
create function financeiro.atualizar_limite_cartao(p_perfil_id integer, p_cartao_id integer, p_limite_id integer,
                                                   p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_limite numeric;
begin
    perform financeiro.travar_limite_cartao(p_perfil_id, p_cartao_id, p_limite_id);
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do limite invalidos' using errcode = '22023';
    end if;
    if p_dados ? 'limite_mensal' and jsonb_typeof(p_dados -> 'limite_mensal') <> 'null' then
        v_limite := financeiro.ler_limite_mensal(p_dados ->> 'limite_mensal');
    end if;
    if p_dados ? 'ativo' and jsonb_typeof(p_dados -> 'ativo') not in ('boolean', 'null') then
        raise exception 'Situacao do vinculo invalida' using errcode = '22023';
    end if;
    -- Reativar exige a Categoria do Cartao ativa (senao o vinculo nao classificaria nenhuma compra).
    if (p_dados ->> 'ativo')::boolean and not exists (
        select 1 from public.cartao_categoria_limite lim join public.categoria_cartao cc on cc.id = lim.categoria_cartao_id
         where lim.id = p_limite_id and cc.ativo) then
        raise exception 'Categoria do Cartao inativa: reative-a em Categorias antes do vinculo' using errcode = '22023';
    end if;
    update public.cartao_categoria_limite
       set limite_mensal = coalesce(v_limite, limite_mensal),
           ativo = coalesce((p_dados ->> 'ativo')::boolean, ativo),
           updated_at = now() at time zone 'utc'
     where id = p_limite_id;
    return jsonb_build_object('limite_id', p_limite_id);
end
$$;

create function financeiro.desativar_limite_cartao(p_perfil_id integer, p_cartao_id integer, p_limite_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.travar_limite_cartao(p_perfil_id, p_cartao_id, p_limite_id);
    update public.cartao_categoria_limite set ativo = false, updated_at = now() at time zone 'utc' where id = p_limite_id;
    return jsonb_build_object('limite_id', p_limite_id, 'ativo', false);
end
$$;

-- ===========================================================================================================
-- Lancamento da fatura: edicao so deste lancamento
-- ===========================================================================================================

-- Como PUT /api/cartoes/lancamentos/<id>, sem os defeitos do Flask: numero e total de parcelas nao mudam;
-- data da compra so na compra a vista; descricao, categoria e valor so deste lancamento. Fatura paga,
-- fechada ou parcela de recorrencia: bloqueado (bloqueio_da_parcela). Recalcula a fatura.
create function financeiro.editar_lancamento_cartao(p_perfil_id integer, p_lancamento_id integer, p_versao text,
                                                    p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_abertas integer[];
    v_l       public.lancamento_agregado;
    v_desc    text;
    v_cat     integer;
    v_cc      integer;
    v_valor   numeric;
    v_data    date;
    v_sugerido date;
begin
    v_abertas := financeiro.travar_compra(p_perfil_id, p_lancamento_id, p_versao);
    if not p_lancamento_id = any(v_abertas) then
        raise exception 'Operacao bloqueada: %', financeiro.bloqueio_da_parcela(p_lancamento_id)
            using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    select * into v_l from public.lancamento_agregado where id = p_lancamento_id;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do lancamento invalidos' using errcode = '22023';
    end if;
    if (p_dados ? 'numero_parcela' and (p_dados ->> 'numero_parcela') is distinct from coalesce(v_l.numero_parcela, 1)::text)
       or (p_dados ? 'total_parcelas' and (p_dados ->> 'total_parcelas') is distinct from coalesce(v_l.total_parcelas, 1)::text) then
        raise exception 'Parcela e total de parcelas nao mudam por aqui: use Gerenciar parcelamento para as parcelas futuras'
            using errcode = '22023';
    end if;
    if p_dados ? 'descricao' then
        v_desc := btrim(coalesce(p_dados ->> 'descricao', ''));
        if v_desc = '' or length(v_desc) > 200 then
            raise exception 'Descricao obrigatoria (ate 200 caracteres)' using errcode = '22023';
        end if;
    end if;
    if nullif(p_dados ->> 'categoria_id', '') is not null then
        begin
            v_cat := (p_dados ->> 'categoria_id')::integer;
        exception when others then
            v_cat := null;
        end;
        if v_cat is null or not exists (select 1 from public.categoria c where c.id = v_cat and coalesce(c.ativo, true)) then
            raise exception 'Categoria inexistente ou inativa' using errcode = '22023';
        end if;
        v_cc := financeiro.resolver_categoria_cartao(p_perfil_id, v_l.cartao_id, v_cat);
    end if;
    if p_dados ? 'valor' then
        begin
            v_valor := (p_dados ->> 'valor')::numeric;
        exception when others then
            v_valor := null;
        end;
        if v_valor is null or v_valor <= 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
            raise exception 'Valor deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
        end if;
    end if;
    if p_dados ? 'data_compra' then
        begin
            v_data := (p_dados ->> 'data_compra')::date;
        exception when others then
            v_data := null;
        end;
        if v_data is null then
            raise exception 'Data da compra invalida' using errcode = '22023';
        end if;
        if v_data <> v_l.data_compra then
            if coalesce(v_l.total_parcelas, 1) > 1 then
                raise exception 'Compra parcelada: a data da compra nao muda por parcela' using errcode = '22023';
            end if;
            v_sugerido := (financeiro.sugestao_competencia(v_l.cartao_id, v_data) ->> 'competencia')::date;
        end if;
    end if;
    update public.lancamento_agregado l
       set descricao = coalesce(v_desc, l.descricao),
           descricao_exibida = case when v_desc is not null then v_desc else l.descricao_exibida end,
           categoria_id = coalesce(v_cat, l.categoria_id),
           categoria_cartao_id = case when v_cat is not null then v_cc else l.categoria_cartao_id end,
           valor = coalesce(v_valor, l.valor),
           data_compra = coalesce(v_data, l.data_compra),
           mes_fatura_sugerido = case when v_data is distinct from l.data_compra and v_data is not null
                                      then v_sugerido else l.mes_fatura_sugerido end
     where l.id = p_lancamento_id;
    perform financeiro.recalcular_fatura(p_perfil_id, v_l.cartao_id, v_l.mes_fatura);
    return jsonb_build_object('lancamento_id', p_lancamento_id, 'versao', financeiro.versao_compra(p_lancamento_id));
end
$$;

-- ===========================================================================================================
-- Parcelamento (CartaoService.consultar_parcelamento_lancamento / atualizar / cancelar parcelas futuras)
-- ===========================================================================================================

-- Situacao de uma parcela em relacao a base: paga, fechada, passada, atual ou futura (como o Flask). Interna.
create function financeiro.situacao_parcela(p_lancamento_id integer, p_base_mes date)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select case financeiro.situacao_fatura(financeiro.fatura_do_mes(l.cartao_id, l.mes_fatura))
               when 'PAGA' then 'paga'
               when 'FECHADA' then 'fechada'
               else case when l.mes_fatura < p_base_mes then 'passada'
                         when l.mes_fatura = p_base_mes then 'atual' else 'futura' end end
      from public.lancamento_agregado l where l.id = p_lancamento_id
$$;

-- Parcela futura editavel: depois da base, em fatura aberta e sem outro bloqueio (recorrencia). Interna.
create function financeiro.parcela_futura_editavel(p_lancamento_id integer, p_base_mes date)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select l.mes_fatura > p_base_mes and financeiro.situacao_parcela(l.id, p_base_mes) = 'futura'
           and financeiro.bloqueio_da_parcela(l.id) is null
      from public.lancamento_agregado l where l.id = p_lancamento_id
$$;

-- Base do parcelamento (lancamento do perfil, parcelado e com compra_id) ou erro. Interna.
create function financeiro.base_do_parcelamento(p_perfil_id integer, p_lancamento_id integer)
    returns public.lancamento_agregado
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_l public.lancamento_agregado;
begin
    select * into v_l from public.lancamento_agregado where id = p_lancamento_id;
    if not found or not financeiro.pertence_ao_perfil(v_l.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Lancamento nao encontrado neste perfil' using errcode = '42501';
    end if;
    if coalesce(v_l.total_parcelas, 1) <= 1 then
        raise exception 'Lancamento nao pertence a parcelamento' using errcode = '22023';
    end if;
    if v_l.compra_id is null then
        raise exception 'Parcelamento sem identificador de compra' using errcode = '22023';
    end if;
    return v_l;
end
$$;

create function financeiro.parcelamento_da_compra(p_perfil_id integer, p_lancamento_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_b public.lancamento_agregado;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_b := financeiro.base_do_parcelamento(p_perfil_id, p_lancamento_id);
    return jsonb_build_object(
        'base', (select jsonb_build_object(
                    'id', v_b.id, 'compra_id', v_b.compra_id, 'cartao_id', v_b.cartao_id,
                    'cartao_nome', (select i.nome from public.item_despesa i where i.id = v_b.cartao_id),
                    'descricao', coalesce(nullif(v_b.descricao_exibida, ''), v_b.descricao), 'valor', v_b.valor,
                    'parcela_atual', v_b.numero_parcela, 'total_parcelas', v_b.total_parcelas,
                    'categoria_id', v_b.categoria_id,
                    'categoria_nome', (select c.nome from public.categoria c where c.id = v_b.categoria_id),
                    'primeira_competencia', to_char(min(p.mes_fatura), 'YYYY-MM'),
                    'ultima_competencia', to_char(max(p.mes_fatura), 'YYYY-MM'),
                    'futuras_editaveis', count(*) filter (where financeiro.parcela_futura_editavel(p.id, v_b.mes_fatura)),
                    'futuras_bloqueadas', count(*) filter (where p.mes_fatura > v_b.mes_fatura
                                                             and not financeiro.parcela_futura_editavel(p.id, v_b.mes_fatura)))
                   from financeiro.parcelas_da_compra(p_lancamento_id) p),
        'parcelas', (select jsonb_agg(jsonb_build_object(
                         'id', p.id, 'parcela', p.numero_parcela || '/' || p.total_parcelas,
                         'numero_parcela', p.numero_parcela, 'total_parcelas', p.total_parcelas,
                         'competencia', to_char(p.mes_fatura, 'YYYY-MM'), 'data_compra', p.data_compra, 'valor', p.valor,
                         'descricao', coalesce(nullif(p.descricao_exibida, ''), p.descricao),
                         'categoria_id', p.categoria_id, 'categoria_cartao_id', p.categoria_cartao_id,
                         'status', financeiro.situacao_parcela(p.id, v_b.mes_fatura),
                         'editavel', financeiro.parcela_futura_editavel(p.id, v_b.mes_fatura))
                         order by p.numero_parcela, p.mes_fatura, p.id)
                       from financeiro.parcelas_da_compra(p_lancamento_id) p),
        'pode_gerir', financeiro.pode_gerir_perfil(p_perfil_id),
        'versao', financeiro.versao_compra(p_lancamento_id));
end
$$;

-- Trava a compra (travar_compra: gestao, perfil, cartao -> faturas -> parcelas, versao) e devolve as parcelas
-- futuras editaveis, relidas sob a trava. Sem parcela aberta, travar_compra ja recusa. Interna.
create function financeiro.travar_parcelas_futuras(p_perfil_id integer, p_lancamento_id integer, p_versao text)
    returns integer[]
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_b       public.lancamento_agregado;
    v_futuras integer[];
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_b := financeiro.base_do_parcelamento(p_perfil_id, p_lancamento_id);
    perform financeiro.travar_compra(p_perfil_id, p_lancamento_id, p_versao);
    select coalesce(array_agg(p.id order by p.numero_parcela), '{}') into v_futuras
      from financeiro.parcelas_da_compra(p_lancamento_id) p
     where financeiro.parcela_futura_editavel(p.id, v_b.mes_fatura);
    return v_futuras;
end
$$;

create function financeiro.editar_parcelas_futuras(p_perfil_id integer, p_lancamento_id integer, p_versao text,
                                                   p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_futuras integer[];
    v_b       public.lancamento_agregado;
    v_desc    text;
    v_cat     integer;
    v_cc      integer;
    v_valor   numeric;
    v_meses   date[];
begin
    v_futuras := financeiro.travar_parcelas_futuras(p_perfil_id, p_lancamento_id, p_versao);
    select * into v_b from public.lancamento_agregado where id = p_lancamento_id;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do parcelamento invalidos' using errcode = '22023';
    end if;
    -- Campo vazio fica como esta (como o Flask).
    v_desc := nullif(btrim(coalesce(p_dados ->> 'descricao', '')), '');
    if length(v_desc) > 200 then
        raise exception 'Descricao ate 200 caracteres' using errcode = '22023';
    end if;
    if nullif(p_dados ->> 'categoria_id', '') is not null then
        begin
            v_cat := (p_dados ->> 'categoria_id')::integer;
        exception when others then
            v_cat := null;
        end;
        if v_cat is null or not exists (select 1 from public.categoria c where c.id = v_cat and coalesce(c.ativo, true)) then
            raise exception 'Categoria inexistente ou inativa' using errcode = '22023';
        end if;
        v_cc := financeiro.resolver_categoria_cartao(p_perfil_id, v_b.cartao_id, v_cat);
    end if;
    if nullif(p_dados ->> 'valor', '') is not null then
        begin
            v_valor := (p_dados ->> 'valor')::numeric;
        exception when others then
            v_valor := null;
        end;
        if v_valor is null or v_valor <= 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
            raise exception 'Valor deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
        end if;
    end if;
    if cardinality(v_futuras) = 0 then
        return jsonb_build_object('atualizadas', 0, 'faturas_afetadas', '[]'::jsonb);
    end if;
    select array_agg(distinct l.mes_fatura order by l.mes_fatura) into v_meses
      from public.lancamento_agregado l where l.id = any(v_futuras);
    update public.lancamento_agregado l
       set descricao = coalesce(v_desc, l.descricao),
           descricao_exibida = case when v_desc is not null then v_desc else l.descricao_exibida end,
           categoria_id = coalesce(v_cat, l.categoria_id),
           categoria_cartao_id = case when v_cat is not null then v_cc else l.categoria_cartao_id end,
           valor = coalesce(v_valor, l.valor)
     where l.id = any(v_futuras);
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_b.cartao_id, v_meses[i]);
    end loop;
    return jsonb_build_object('atualizadas', cardinality(v_futuras),
                              'faturas_afetadas', (select jsonb_agg(to_char(m, 'YYYY-MM')) from unnest(v_meses) m));
end
$$;

-- Cancela (exclui) so as parcelas futuras em fatura aberta; as anteriores, pagas ou fechadas ficam (historico).
create function financeiro.cancelar_parcelas_futuras(p_perfil_id integer, p_lancamento_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_futuras integer[];
    v_b       public.lancamento_agregado;
    v_meses   date[];
begin
    v_futuras := financeiro.travar_parcelas_futuras(p_perfil_id, p_lancamento_id, p_versao);
    select * into v_b from public.lancamento_agregado where id = p_lancamento_id;
    if cardinality(v_futuras) = 0 then
        return jsonb_build_object('canceladas', 0, 'faturas_afetadas', '[]'::jsonb);
    end if;
    select array_agg(distinct l.mes_fatura order by l.mes_fatura) into v_meses
      from public.lancamento_agregado l where l.id = any(v_futuras);
    delete from public.lancamento_agregado where id = any(v_futuras);
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_b.cartao_id, v_meses[i]);
    end loop;
    return jsonb_build_object('canceladas', cardinality(v_futuras),
                              'faturas_afetadas', (select jsonb_agg(to_char(m, 'YYYY-MM')) from unnest(v_meses) m));
end
$$;

-- ===========================================================================================================
-- Privilegios: internas sem execucao para ninguem; as da tela so para authenticated.
-- ===========================================================================================================

revoke execute on function financeiro.ler_dados_cartao(jsonb, boolean) from public, anon, authenticated;
revoke execute on function financeiro.gasto_categoria_fatura(integer, integer, integer, date) from public, anon, authenticated;
revoke execute on function financeiro.status_consumo(numeric, numeric) from public, anon, authenticated;
revoke execute on function financeiro.ler_limite_mensal(text) from public, anon, authenticated;
revoke execute on function financeiro.travar_limite_cartao(integer, integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.situacao_parcela(integer, date) from public, anon, authenticated;
revoke execute on function financeiro.parcela_futura_editavel(integer, date) from public, anon, authenticated;
revoke execute on function financeiro.base_do_parcelamento(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.travar_parcelas_futuras(integer, integer, text) from public, anon, authenticated;

revoke execute on function financeiro.criar_cartao(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_cartao(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.cartoes_da_tela(integer) from public, anon;
revoke execute on function financeiro.categorias_cartao_do_perfil(integer) from public, anon;
revoke execute on function financeiro.limites_do_cartao(integer, integer, date) from public, anon;
revoke execute on function financeiro.fatura_por_categoria(integer, integer, date) from public, anon;
revoke execute on function financeiro.lancamentos_fatura_por_categoria(integer, integer, date, text) from public, anon;
revoke execute on function financeiro.vincular_limite_cartao(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.atualizar_limite_cartao(integer, integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.desativar_limite_cartao(integer, integer, integer) from public, anon;
revoke execute on function financeiro.editar_lancamento_cartao(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.parcelamento_da_compra(integer, integer) from public, anon;
revoke execute on function financeiro.editar_parcelas_futuras(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.cancelar_parcelas_futuras(integer, integer, text) from public, anon;
grant execute on function financeiro.criar_cartao(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_cartao(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.cartoes_da_tela(integer) to authenticated;
grant execute on function financeiro.categorias_cartao_do_perfil(integer) to authenticated;
grant execute on function financeiro.limites_do_cartao(integer, integer, date) to authenticated;
grant execute on function financeiro.fatura_por_categoria(integer, integer, date) to authenticated;
grant execute on function financeiro.lancamentos_fatura_por_categoria(integer, integer, date, text) to authenticated;
grant execute on function financeiro.vincular_limite_cartao(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.atualizar_limite_cartao(integer, integer, integer, jsonb) to authenticated;
grant execute on function financeiro.desativar_limite_cartao(integer, integer, integer) to authenticated;
grant execute on function financeiro.editar_lancamento_cartao(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.parcelamento_da_compra(integer, integer) to authenticated;
grant execute on function financeiro.editar_parcelas_futuras(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.cancelar_parcelas_futuras(integer, integer, text) to authenticated;
