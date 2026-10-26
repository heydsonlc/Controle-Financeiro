-- FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 — telas originais de Receitas e Categorias do Flask sobre o Supabase.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261119090000).
-- Validada em cluster local descartavel, comparada com o PROPRIO Flask (tests/test_supabase_receitas_categorias_tela.py).
-- Docs: docs/FIN_FIDELIDADE_RECEITAS_CATEGORIAS_1.md.
--
-- Leituras no formato do Flask (o JS original monta a tela a partir delas):
-- - receitas_fontes_tela, receitas_orcamentos_tela, receitas_realizadas_tela: GET /api/receitas/itens,
--   /orcamento?ano= e /realizadas?ano_mes_inicio=&ano_mes_fim= (to_dict de ItemReceita, ReceitaOrcamento e
--   ReceitaRealizada), mais campos extras que o Flask ignora: versao (edicao com controle de concorrencia), de_outro_modulo
--   e estornada. Sem o backfill de contemplacao de consorcio que o GET do Flask grava (leitura nao grava aqui).
-- - categorias_tela, palavras_chave_tela, categorias_cartao_tela, categoria_cartao_despesas_tela: GET /api/categorias
--   (com palavras_chave_count), /api/categorias/<id>/palavras-chave, /api/categorias-cartao e
--   /api/categorias-cartao/<id>/despesas, de uma vez (a tela original faz uma chamada por categoria).
-- Escrita, so Categorias do Cartao (por perfil), como CategoriaCartaoService do Flask:
--   criar, editar, desativar, vincular e desvincular categoria de despesa. So por quem gere o perfil e SO no perfil
--   atribuido ao novo aplicativo (financeiro.exigir_pagamento_novo: perfil ainda no Flask = recusa, nada gravado).
--   Vinculos e desativacoes nao reclassificam compras ja lancadas (o Flask tambem nao).
-- Categorias de despesa, palavras-chave e logos sao GLOBAIS (comuns a todos os perfis, inclusive os ainda no Flask):
-- nenhuma escrita aqui (docs §5).
-- Correcao em relacao ao Flask: a cor da Categoria do Cartao precisa ser #RRGGBB (o Flask grava qualquer texto).
-- Nenhuma tabela nova; nenhum dado existente e alterado.

-- 1. Receitas -----------------------------------------------------------------------------------------------------

-- ItemReceita.to_dict. Interna.
create function financeiro.item_receita_flask(p_i public.item_receita)
    returns jsonb
    language sql
    stable
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_i.id, 'perfil_financeiro_id', p_i.perfil_financeiro_id, 'nome', p_i.nome, 'tipo', p_i.tipo,
        'descricao', p_i.descricao, 'ativo', p_i.ativo,
        'valor_base_mensal', case when coalesce(p_i.valor_base_mensal, 0) <> 0 then p_i.valor_base_mensal end,
        'dia_previsto_pagamento', p_i.dia_previsto_pagamento, 'conta_origem_id', p_i.conta_origem_id,
        'conta_bancaria_id', p_i.conta_bancaria_id, 'recorrente', p_i.recorrente)
$$;

-- ReceitaOrcamento.to_dict. Interna.
create function financeiro.receita_orcamento_flask(p_o public.receita_orcamento)
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

-- ReceitaRealizada.to_dict (com item_receita quando houver fonte). Interna.
create function financeiro.receita_realizada_flask(p_r public.receita_realizada)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_r.id, 'perfil_financeiro_id', p_r.perfil_financeiro_id, 'item_receita_id', p_r.item_receita_id,
        'data_recebimento', to_char(p_r.data_recebimento, 'YYYY-MM-DD'), 'valor_recebido', p_r.valor_recebido,
        'mes_referencia', to_char(p_r.mes_referencia, 'YYYY-MM-DD'), 'competencia', to_char(p_r.mes_referencia, 'YYYY-MM-DD'),
        'conta_origem_id', p_r.conta_origem_id, 'conta_bancaria_id', p_r.conta_bancaria_id, 'descricao', p_r.descricao,
        'orcamento_id', p_r.orcamento_id, 'observacoes', p_r.observacoes)
        || coalesce((select jsonb_build_object('item_receita', jsonb_build_object('id', i.id, 'nome', i.nome, 'tipo', i.tipo))
                       from public.item_receita i where i.id = p_r.item_receita_id), '{}'::jsonb)
$$;

-- GET /api/receitas/itens: fontes do perfil (NULL = Pessoal), por nome.
create function financeiro.receitas_fontes_tela(p_perfil_id integer)
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
    return coalesce((
        select jsonb_agg(financeiro.item_receita_flask(i)
                         || jsonb_build_object('versao', financeiro.versao_fonte(i.id),
                                               'de_outro_modulo', financeiro.fonte_de_outro_modulo(i.id))
                         order by i.nome, i.id)
          from public.item_receita i
         where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb);
end
$$;

-- GET /api/receitas/orcamento?ano=: previsoes do ano, por competencia e fonte.
create function financeiro.receitas_orcamentos_tela(p_perfil_id integer, p_ano integer)
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
    if p_ano is null or p_ano not between 2000 and 2100 then
        raise exception 'Parametro ano e obrigatorio' using errcode = '22023';
    end if;
    return coalesce((
        select jsonb_agg(financeiro.receita_orcamento_flask(o) || jsonb_build_object('versao', financeiro.versao_previsao(o.id))
                         order by o.mes_referencia, o.item_receita_id, o.id)
          from public.receita_orcamento o
         where financeiro.pertence_ao_perfil(o.perfil_financeiro_id, p_perfil_id)
           and o.mes_referencia between make_date(p_ano, 1, 1) and make_date(p_ano, 12, 31)), '[]'::jsonb);
end
$$;

-- Competencia do filtro do Flask: 'YYYY-MM' ou 'YYYY-MM-DD', sempre o dia 1. Interna.
create function financeiro.competencia_flask(p_texto text)
    returns date
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_texto text := btrim(coalesce(p_texto, ''));
begin
    if v_texto = '' then
        return null;
    end if;
    if length(v_texto) = 7 then
        v_texto := v_texto || '-01';
    end if;
    return date_trunc('month', to_date(left(v_texto, 10), 'YYYY-MM-DD')::timestamp)::date;
exception when others then
    raise exception 'Competencia invalida' using errcode = '22023';
end
$$;

-- GET /api/receitas/realizadas?ano_mes_inicio=&ano_mes_fim=: recebimentos por competencia (mais recente primeiro no mes).
create function financeiro.receitas_realizadas_tela(p_perfil_id integer, p_inicio text, p_fim text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_inicio date := financeiro.competencia_flask(p_inicio);
    v_fim    date := financeiro.competencia_flask(p_fim);
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return coalesce((
        select jsonb_agg(financeiro.receita_realizada_flask(r) || jsonb_build_object('estornada', financeiro.receita_estornada(r.id))
                         order by r.mes_referencia, r.data_recebimento desc, r.id)
          from public.receita_realizada r
         where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
           and (v_inicio is null or r.mes_referencia >= v_inicio)
           and (v_fim is null or r.mes_referencia <= v_fim)), '[]'::jsonb);
end
$$;

-- 2. Categorias (leitura) -----------------------------------------------------------------------------------------

-- CategoriaCartao.to_dict. Interna.
create function financeiro.categoria_cartao_flask(p_c public.categoria_cartao)
    returns jsonb
    language sql
    stable
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_c.id, 'perfil_financeiro_id', p_c.perfil_financeiro_id, 'nome', p_c.nome, 'descricao', p_c.descricao,
        'cor', p_c.cor, 'icone', p_c.icone, 'logo_arquivo', p_c.logo_arquivo, 'logo_mime', p_c.logo_mime,
        'logo_tamanho', p_c.logo_tamanho, 'logo_original_nome', p_c.logo_original_nome,
        'logo_criado_em', financeiro.iso_python(p_c.logo_criado_em),
        'logo_url', case when nullif(p_c.logo_arquivo, '') is not null then '/api/categorias-cartao/' || p_c.id || '/logo' end,
        'ativo', coalesce(p_c.ativo, false), 'created_at', financeiro.iso_python(p_c.created_at),
        'updated_at', financeiro.iso_python(p_c.updated_at))
$$;

-- CategoriaCartaoDespesa.to_dict (com os nomes). Interna.
create function financeiro.categoria_cartao_despesa_flask(p_v public.categoria_cartao_despesa)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_v.id, 'perfil_financeiro_id', p_v.perfil_financeiro_id, 'categoria_cartao_id', p_v.categoria_cartao_id,
        'categoria_cartao_nome', (select cc.nome from public.categoria_cartao cc where cc.id = p_v.categoria_cartao_id),
        'categoria_id', p_v.categoria_id,
        'categoria_nome', (select c.nome from public.categoria c where c.id = p_v.categoria_id),
        'ativo', coalesce(p_v.ativo, false), 'created_at', financeiro.iso_python(p_v.created_at),
        'updated_at', financeiro.iso_python(p_v.updated_at))
$$;

-- GET /api/categorias (globais): _categoria_to_dict, com palavras_chave_count (ativas). p_ativo nulo = todas.
create function financeiro.categorias_tela(p_perfil_id integer, p_ativo boolean)
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
    return coalesce((
        select jsonb_agg(financeiro.categoria_flask(c)
                         || jsonb_build_object('palavras_chave_count',
                                               (select count(*) from public.categoria_palavra_chave p
                                                 where p.categoria_id = c.id and p.ativo))
                         order by c.id)
          from public.categoria c
         where p_ativo is null or c.ativo is not distinct from p_ativo), '[]'::jsonb);
end
$$;

-- GET /api/categorias/<id>/palavras-chave, de todas as categorias: {categoria_id: [ativas, por palavra]}.
create function financeiro.palavras_chave_tela(p_perfil_id integer)
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
    return coalesce((
        select jsonb_object_agg(x.categoria_id::text, x.palavras)
          from (select p.categoria_id,
                       jsonb_agg(jsonb_build_object('id', p.id, 'categoria_id', p.categoria_id, 'palavra', p.palavra,
                                                    'ativo', coalesce(p.ativo, false),
                                                    'created_at', financeiro.iso_python(p.created_at),
                                                    'updated_at', financeiro.iso_python(p.updated_at))
                                 order by p.palavra, p.id) palavras
                  from public.categoria_palavra_chave p
                 where p.ativo
                 group by p.categoria_id) x), '{}'::jsonb);
end
$$;

-- GET /api/categorias-cartao: Categorias do Cartao do perfil (NULL = Pessoal), por nome. p_ativo nulo = todas.
create function financeiro.categorias_cartao_tela(p_perfil_id integer, p_ativo boolean)
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
    return coalesce((
        select jsonb_agg(financeiro.categoria_cartao_flask(cc) order by cc.nome, cc.id)
          from public.categoria_cartao cc
         where financeiro.pertence_ao_perfil(cc.perfil_financeiro_id, p_perfil_id)
           and (p_ativo is null or coalesce(cc.ativo, false) = p_ativo)), '[]'::jsonb);
end
$$;

-- GET /api/categorias-cartao/<id>/despesas, de todas as Categorias do Cartao do perfil: {id: [vinculos por id]}.
-- Como o Flask: os vinculos sao os gravados com o id do perfil (filtro exato, sem o NULL do Pessoal).
create function financeiro.categoria_cartao_despesas_tela(p_perfil_id integer, p_ativo boolean)
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
    return coalesce((
        select jsonb_object_agg(cc.id::text, coalesce((
                   select jsonb_agg(financeiro.categoria_cartao_despesa_flask(v) order by v.id)
                     from public.categoria_cartao_despesa v
                    where v.categoria_cartao_id = cc.id and v.perfil_financeiro_id = p_perfil_id
                      and (p_ativo is null or coalesce(v.ativo, false) = p_ativo)), '[]'::jsonb))
          from public.categoria_cartao cc
         where financeiro.pertence_ao_perfil(cc.perfil_financeiro_id, p_perfil_id)), '{}'::jsonb);
end
$$;

-- 3. Categorias do Cartao (escrita, escritor unico do perfil) -----------------------------------------------------

-- Gestao + escritor do perfil + cadastros de Categoria do Cartao do perfil em serie (nome unico). Interna.
create function financeiro.exigir_escrita_categoria_cartao(p_perfil_id integer)
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
    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    perform pg_advisory_xact_lock(20261119, p_perfil_id);
end
$$;

-- A Categoria do Cartao do perfil, travada. Interna.
create function financeiro.travar_categoria_cartao(p_perfil_id integer, p_id integer)
    returns public.categoria_cartao
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c public.categoria_cartao;
begin
    select * into v_c from public.categoria_cartao cc where cc.id = p_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_c.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Categoria do Cartao nao encontrada' using errcode = '22023';
    end if;
    return v_c;
end
$$;

-- Validacoes do cadastro (CategoriaCartaoService): nome obrigatorio e unico no perfil (sem caixa), cor #RRGGBB,
-- icone ate 50. Devolve so as chaves presentes (p_parcial) ou todas. Interna.
create function financeiro.ler_dados_categoria_cartao(p_perfil_id integer, p_dados jsonb, p_parcial boolean, p_ignorar integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_saida jsonb := '{}'::jsonb;
    v_nome  text;
    v_cor   text;
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados invalidos' using errcode = '22023';
    end if;
    if not p_parcial or (p_dados ? 'nome' and jsonb_typeof(p_dados -> 'nome') <> 'null') then
        v_nome := btrim(coalesce(p_dados ->> 'nome', ''));
        if v_nome = '' then
            raise exception 'Nome e obrigatorio' using errcode = '22023';
        end if;
        if length(v_nome) > 100 then
            raise exception 'Nome ate 100 caracteres' using errcode = '22023';
        end if;
        if exists (select 1 from public.categoria_cartao cc
                    where lower(cc.nome) = lower(v_nome) and cc.id is distinct from p_ignorar
                      and financeiro.pertence_ao_perfil(cc.perfil_financeiro_id, p_perfil_id)) then
            raise exception 'Ja existe uma Categoria do Cartao com este nome' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('nome', v_nome);
    end if;
    if not p_parcial or p_dados ? 'descricao' then
        v_saida := v_saida || jsonb_build_object('descricao', nullif(btrim(coalesce(p_dados ->> 'descricao', '')), ''));
    end if;
    if not p_parcial or nullif(p_dados ->> 'cor', '') is not null then
        v_cor := coalesce(nullif(p_dados ->> 'cor', ''), '#6c757d');
        if v_cor !~ '^#[0-9A-Fa-f]{6}$' then
            raise exception 'Cor invalida (use #RRGGBB)' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('cor', v_cor);
    end if;
    if not p_parcial or p_dados ? 'icone' then
        v_saida := v_saida || jsonb_build_object('icone', nullif(left(btrim(coalesce(p_dados ->> 'icone', '')), 50), ''));
    end if;
    if not p_parcial or (p_dados ? 'ativo' and jsonb_typeof(p_dados -> 'ativo') <> 'null') then
        v_saida := v_saida || jsonb_build_object('ativo', coalesce((p_dados ->> 'ativo')::boolean, true));
    end if;
    return v_saida;
exception when invalid_text_representation then
    raise exception 'Dados invalidos' using errcode = '22023';
end
$$;

-- POST /api/categorias-cartao.
create function financeiro.criar_categoria_cartao(p_perfil_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d jsonb;
    v_c public.categoria_cartao;
begin
    perform financeiro.exigir_escrita_categoria_cartao(p_perfil_id);
    v_d := financeiro.ler_dados_categoria_cartao(p_perfil_id, p_dados, false, null);
    insert into public.categoria_cartao (perfil_financeiro_id, nome, descricao, cor, icone, ativo, created_at, updated_at)
    values (p_perfil_id, v_d ->> 'nome', v_d ->> 'descricao', v_d ->> 'cor', v_d ->> 'icone', (v_d ->> 'ativo')::boolean,
            now() at time zone 'utc', now() at time zone 'utc')
    returning * into v_c;
    return financeiro.categoria_cartao_flask(v_c);
end
$$;

-- PUT /api/categorias-cartao/<id>: so os campos enviados.
create function financeiro.editar_categoria_cartao(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d jsonb;
    v_c public.categoria_cartao;
begin
    perform financeiro.exigir_escrita_categoria_cartao(p_perfil_id);
    v_c := financeiro.travar_categoria_cartao(p_perfil_id, p_id);
    v_d := financeiro.ler_dados_categoria_cartao(p_perfil_id, p_dados, true, v_c.id);
    update public.categoria_cartao cc set
        nome = coalesce(v_d ->> 'nome', cc.nome),
        descricao = case when v_d ? 'descricao' then v_d ->> 'descricao' else cc.descricao end,
        cor = coalesce(v_d ->> 'cor', cc.cor),
        icone = case when v_d ? 'icone' then v_d ->> 'icone' else cc.icone end,
        ativo = coalesce((v_d ->> 'ativo')::boolean, cc.ativo),
        updated_at = now() at time zone 'utc'
     where cc.id = v_c.id
    returning * into v_c;
    return financeiro.categoria_cartao_flask(v_c);
end
$$;

-- DELETE /api/categorias-cartao/<id>: desativa (nada e apagado; compras e limites ficam como estao).
create function financeiro.desativar_categoria_cartao(p_perfil_id integer, p_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c public.categoria_cartao;
begin
    perform financeiro.exigir_escrita_categoria_cartao(p_perfil_id);
    v_c := financeiro.travar_categoria_cartao(p_perfil_id, p_id);
    update public.categoria_cartao cc set ativo = false, updated_at = now() at time zone 'utc'
     where cc.id = v_c.id
    returning * into v_c;
    return financeiro.categoria_cartao_flask(v_c);
end
$$;

-- POST /api/categorias-cartao/<id>/despesas: vincula (ou reativa) uma categoria de despesa. Ativo: a categoria de
-- despesa nao pode ter vinculo ativo com OUTRA Categoria do Cartao do perfil. Devolve o vinculo e 'created'.
create function financeiro.vincular_despesa_categoria_cartao(p_perfil_id integer, p_categoria_cartao_id integer,
                                                             p_categoria_id integer, p_ativo boolean)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c      public.categoria_cartao;
    v_ativo  boolean := coalesce(p_ativo, true);
    v_v      public.categoria_cartao_despesa;
    v_criado boolean := false;
begin
    perform financeiro.exigir_escrita_categoria_cartao(p_perfil_id);
    v_c := financeiro.travar_categoria_cartao(p_perfil_id, p_categoria_cartao_id);
    if p_categoria_id is null or not exists (select 1 from public.categoria c where c.id = p_categoria_id) then
        raise exception 'Categoria de despesa nao encontrada' using errcode = '22023';
    end if;
    if v_ativo and exists (select 1 from public.categoria_cartao_despesa v
                            where v.categoria_id = p_categoria_id and v.ativo and v.categoria_cartao_id <> v_c.id
                              and financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)) then
        raise exception 'Categoria de despesa ja vinculada a outra Categoria do Cartao ativa' using errcode = '22023';
    end if;
    select * into v_v from public.categoria_cartao_despesa v
     where v.categoria_cartao_id = v_c.id and v.categoria_id = p_categoria_id and v.perfil_financeiro_id = p_perfil_id
       for update;
    if found then
        update public.categoria_cartao_despesa v set ativo = v_ativo, updated_at = now() at time zone 'utc'
         where v.id = v_v.id
        returning * into v_v;
    else
        insert into public.categoria_cartao_despesa (perfil_financeiro_id, categoria_cartao_id, categoria_id, ativo,
                                                     created_at, updated_at)
        values (p_perfil_id, v_c.id, p_categoria_id, v_ativo, now() at time zone 'utc', now() at time zone 'utc')
        returning * into v_v;
        v_criado := true;
    end if;
    return financeiro.categoria_cartao_despesa_flask(v_v) || jsonb_build_object('created', v_criado);
end
$$;

-- DELETE /api/categorias-cartao/<id>/despesas/<categoria_id>: desativa o vinculo (nada e apagado).
create function financeiro.desvincular_despesa_categoria_cartao(p_perfil_id integer, p_categoria_cartao_id integer,
                                                                p_categoria_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_v public.categoria_cartao_despesa;
begin
    perform financeiro.exigir_escrita_categoria_cartao(p_perfil_id);
    select * into v_v from public.categoria_cartao_despesa v
     where v.categoria_cartao_id = p_categoria_cartao_id and v.categoria_id = p_categoria_id
       and v.perfil_financeiro_id = p_perfil_id
       for update;
    if not found then
        raise exception 'Vinculo nao encontrado' using errcode = '22023';
    end if;
    update public.categoria_cartao_despesa v set ativo = false, updated_at = now() at time zone 'utc'
     where v.id = v_v.id
    returning * into v_v;
    return financeiro.categoria_cartao_despesa_flask(v_v);
end
$$;

-- 4. Privilegios --------------------------------------------------------------------------------------------------

revoke execute on function financeiro.item_receita_flask(public.item_receita) from public, anon, authenticated;
revoke execute on function financeiro.receita_orcamento_flask(public.receita_orcamento) from public, anon, authenticated;
revoke execute on function financeiro.receita_realizada_flask(public.receita_realizada) from public, anon, authenticated;
revoke execute on function financeiro.competencia_flask(text) from public, anon, authenticated;
revoke execute on function financeiro.categoria_cartao_flask(public.categoria_cartao) from public, anon, authenticated;
revoke execute on function financeiro.categoria_cartao_despesa_flask(public.categoria_cartao_despesa) from public, anon, authenticated;
revoke execute on function financeiro.exigir_escrita_categoria_cartao(integer) from public, anon, authenticated;
revoke execute on function financeiro.travar_categoria_cartao(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.ler_dados_categoria_cartao(integer, jsonb, boolean, integer) from public, anon, authenticated;
revoke execute on function financeiro.receitas_fontes_tela(integer) from public, anon;
revoke execute on function financeiro.receitas_orcamentos_tela(integer, integer) from public, anon;
revoke execute on function financeiro.receitas_realizadas_tela(integer, text, text) from public, anon;
revoke execute on function financeiro.categorias_tela(integer, boolean) from public, anon;
revoke execute on function financeiro.palavras_chave_tela(integer) from public, anon;
revoke execute on function financeiro.categorias_cartao_tela(integer, boolean) from public, anon;
revoke execute on function financeiro.categoria_cartao_despesas_tela(integer, boolean) from public, anon;
revoke execute on function financeiro.criar_categoria_cartao(integer, jsonb) from public, anon;
revoke execute on function financeiro.editar_categoria_cartao(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.desativar_categoria_cartao(integer, integer) from public, anon;
revoke execute on function financeiro.vincular_despesa_categoria_cartao(integer, integer, integer, boolean) from public, anon;
revoke execute on function financeiro.desvincular_despesa_categoria_cartao(integer, integer, integer) from public, anon;
grant execute on function financeiro.receitas_fontes_tela(integer) to authenticated;
grant execute on function financeiro.receitas_orcamentos_tela(integer, integer) to authenticated;
grant execute on function financeiro.receitas_realizadas_tela(integer, text, text) to authenticated;
grant execute on function financeiro.categorias_tela(integer, boolean) to authenticated;
grant execute on function financeiro.palavras_chave_tela(integer) to authenticated;
grant execute on function financeiro.categorias_cartao_tela(integer, boolean) to authenticated;
grant execute on function financeiro.categoria_cartao_despesas_tela(integer, boolean) to authenticated;
grant execute on function financeiro.criar_categoria_cartao(integer, jsonb) to authenticated;
grant execute on function financeiro.editar_categoria_cartao(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.desativar_categoria_cartao(integer, integer) to authenticated;
grant execute on function financeiro.vincular_despesa_categoria_cartao(integer, integer, integer, boolean) to authenticated;
grant execute on function financeiro.desvincular_despesa_categoria_cartao(integer, integer, integer) to authenticated;
