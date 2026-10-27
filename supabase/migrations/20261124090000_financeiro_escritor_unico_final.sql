-- FIN-ESCRITOR-UNICO-FINAL-1 — escritor unico nas escritas antigas do novo aplicativo: cadastros e edicoes de despesas,
-- recorrencias, receitas (previsoes e fontes), cartoes, limites, compras, lancamentos, parcelas futuras, importacao de
-- fatura e gestao de perfil passam a exigir o perfil atribuido ao novo aplicativo (financeiro.gerador_recorrencia = NOVO).
-- Perfil no Flask: recusado (hint SISTEMA_FLASK), nada gravado. Do outro lado, o Flask recusa essas escritas em perfil
-- NOVO (backend/services/gerador_recorrencia_service.py, registrar_guarda_escritor_unico).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261124090000).
-- Validada em cluster local descartavel (tests/test_supabase_escritor_unico_final.py). Docs: docs/FIN_ESCRITOR_UNICO_FINAL_1.md.
-- Cada funcao e o texto da sua ultima definicao com UMA linha marcada FIN-ESCRITOR-UNICO-FINAL-1 (mesma assinatura e
-- privilegios). Reversao: supabase/reversao/20261124090000_escritas_sem_escritor_anterior.sql. Nenhuma tabela nem dado.
-- Fora: criar_perfil (perfil novo ja nasce no novo aplicativo) e o catalogo global de categorias (continua no Flask).

-- Guarda das escritas: quem gere o perfil ativo (pode_gerir_perfil; inativo so na gestao do proprio perfil) e perfil no novo
-- aplicativo; mesma trava do Flask (20261023). As verificacoes proprias de cada funcao continuam. Interna.
create function financeiro.exigir_escrita_novo(p_perfil_id integer, p_inativo_ok boolean default false)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_sistema text;
begin
    if not (financeiro.pode_gerir_perfil(p_perfil_id)
            or p_inativo_ok and exists (select 1 from financeiro.perfil_acesso a
                                         where a.user_id = (select auth.uid()) and a.perfil_financeiro_id = p_perfil_id and a.pode_gerir)) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    select g.gerador into v_sistema from financeiro.gerador_recorrencia g where g.perfil_financeiro_id = p_perfil_id for share;
    if v_sistema is distinct from 'NOVO' then
        raise exception 'Este perfil ainda é administrado pelo sistema atual (Flask). Nada foi gravado.'
            using errcode = 'P0001', hint = 'SISTEMA_FLASK';
    end if;
end
$$;

revoke execute on function financeiro.exigir_escrita_novo(integer, boolean) from public, anon, authenticated;

-- atualizar_limite_cartao: texto de 20261104090000 + a linha marcada.
create or replace function financeiro.atualizar_limite_cartao(p_perfil_id integer, p_cartao_id integer, p_limite_id integer,
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
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
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

-- atualizar_perfil: texto de 20261102090000 + a linha marcada.
create or replace function financeiro.atualizar_perfil(p_perfil_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_perfil public.perfil_financeiro%rowtype;
    v jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id, true);  -- FIN-ESCRITOR-UNICO-FINAL-1
    if not financeiro.gere_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do perfil invalidos' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtext('financeiro.perfil_financeiro.gestao'));
    select * into v_perfil from public.perfil_financeiro p where p.id = p_perfil_id for update;
    v := financeiro.normalizar_dados_perfil(p_dados - 'ativo' - 'padrao' - 'id', v_perfil.nome);

    if v ? 'nome' and v ->> 'nome' <> v_perfil.nome then
        if v_perfil.nome = 'Pessoal' then
            raise exception 'O perfil Pessoal nao pode ser renomeado: ele guarda os registros sem perfil' using errcode = '22023';
        end if;
        if v ->> 'nome' = 'Pessoal' then
            raise exception 'O nome Pessoal e reservado ao perfil que guarda os registros sem perfil' using errcode = '22023';
        end if;
        if exists (select 1 from public.perfil_financeiro p where p.nome = v ->> 'nome' and p.id <> p_perfil_id) then
            raise exception 'Ja existe perfil financeiro com este nome' using errcode = '23505';
        end if;
    end if;

    update public.perfil_financeiro p
       set nome = coalesce(v ->> 'nome', p.nome),
           tipo = coalesce(v ->> 'tipo', p.tipo),
           documento = case when v ? 'documento' then v ->> 'documento' else p.documento end,
           logo_url = case when v ? 'logo_url' then v ->> 'logo_url' else p.logo_url end,
           avatar = coalesce(v ->> 'avatar', p.avatar),
           cor = coalesce(v ->> 'cor', p.cor),
           updated_at = (now() at time zone 'utc')
     where p.id = p_perfil_id;
    return financeiro.perfil_em_json(p_perfil_id);
exception
    when unique_violation then
        raise exception 'Ja existe perfil financeiro com este nome' using errcode = '23505';
end
$$;

-- cancelar_parcelas_futuras: texto de 20261104090000 + a linha marcada.
create or replace function financeiro.cancelar_parcelas_futuras(p_perfil_id integer, p_lancamento_id integer, p_versao text)
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
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
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

-- criar_cartao: texto de 20261104090000 + a linha marcada.
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

-- criar_compra: texto de 20261030090000 + a linha marcada.
create or replace function financeiro.criar_compra(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_cartao;
    v_linhas    record;
    v_linha     record;
    v_compra    text := gen_random_uuid()::text;
    v_ids       integer[] := '{}';
    v_meses     date[] := '{}';
    v_fatura    integer;
    v_id        integer;
    v_cartao    integer;
    v_resultado jsonb;
    v_conf      jsonb;
    v_incluir   jsonb := '{}'::jsonb;  -- fatura consolidada -> {incluido, primeiro lancamento, competencia}
    v_fechadas  jsonb := '[]'::jsonb;
    v_total     numeric;
    v_chave     text;
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
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao (recorrencias do cartao)
    v_conf := p_dados -> 'confirmar_consolidadas';

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
                                                criado_em, mes_fatura_original, mes_fatura_sugerido)
        values (coalesce((select c.perfil_financeiro_id from public.conta c where c.id = v_fatura), p_perfil_id),
                v_linha.cartao_id, null, v_linha.categoria_cartao_id, v_linha.categoria_id, v_linha.descricao,
                v_linha.valor, v_linha.data_compra, v_linha.mes_fatura, v_linha.numero, v_linha.total,
                v_linha.observacoes, false, v_compra, false, now() at time zone 'utc',
                -- desviada de fatura paga: guarda a competencia em que entraria
                case when v_linha.redirecionada
                     then (date_trunc('month', coalesce(nullif(p_dados ->> 'mes_fatura', '')::date,
                                                        v_linha.mes_fatura_sugerido - make_interval(months => v_linha.numero - 1))
                                       ::timestamp)
                           + make_interval(months => v_linha.numero - 1))::date end,
                v_linha.mes_fatura_sugerido)
        returning id into v_id;
        v_ids := v_ids || v_id;
        if not v_linha.mes_fatura = any(v_meses) then
            v_meses := v_meses || v_linha.mes_fatura;
        end if;
        -- D6: fatura consolidada (relida com a trava) so com a confirmacao desta operacao.
        if exists (select 1 from public.conta c where c.id = v_fatura and c.status_fatura = 'FECHADA') then
            v_chave := v_fatura::text;
            v_incluir := jsonb_set(v_incluir, array[v_chave], jsonb_build_object(
                'incluido', coalesce((v_incluir #>> array[v_chave, 'incluido'])::numeric, 0) + v_linha.valor,
                'lancamento', coalesce((v_incluir #>> array[v_chave, 'lancamento'])::integer, v_id),
                'competencia', v_linha.mes_fatura));
        end if;
    end loop;

    for v_linhas in select key::integer as fatura, value from jsonb_each(v_incluir) order by key::integer loop
        v_total := financeiro.exigir_confirmacao_consolidada(v_linhas.fatura, v_conf, (v_linhas.value ->> 'incluido')::numeric);
        update public.conta set valor_consolidado = v_total + (v_linhas.value ->> 'incluido')::numeric
         where id = v_linhas.fatura;
        insert into public.fatura_consolidada_inclusao (fatura_id, cartao_id, perfil_financeiro_id, competencia, compra_id,
                                                        lancamento_id, valor_incluido, total_consolidado_anterior,
                                                        total_consolidado_novo, operacao, origem, user_id, criado_em)
        values (v_linhas.fatura, v_cartao, p_perfil_id, (v_linhas.value ->> 'competencia')::date, v_compra,
                (v_linhas.value ->> 'lancamento')::integer, (v_linhas.value ->> 'incluido')::numeric, v_total,
                v_total + (v_linhas.value ->> 'incluido')::numeric, 'COMPRA', 'NOVO_APP', (select auth.uid())::text,
                now() at time zone 'utc');
        v_fechadas := v_fechadas || jsonb_build_object('fatura_id', v_linhas.fatura,
                                                       'total_consolidado', v_total + (v_linhas.value ->> 'incluido')::numeric);
    end loop;
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_cartao, v_meses[i]);
    end loop;
    v_resultado := jsonb_build_object('compra_id', v_compra, 'lancamentos', to_jsonb(v_ids), 'faturas', to_jsonb(v_meses),
                                      'consolidadas', v_fechadas);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_compra', v_resultado);
    return v_resultado;
end
$$;

-- criar_despesa: texto de 20261026090000 + a linha marcada.
create or replace function financeiro.criar_despesa(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_despesa;
    v_d         jsonb;
    v_rec       boolean;
    v_venc      date;
    v_comp      date;
    v_item_id   integer;
    v_conta_id  integer;
    v_resultado jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    -- Repeticao (duplo clique, reenvio): a mesma chave devolve o mesmo resultado.
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261026));
    select * into v_anterior from financeiro.operacao_despesa o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;

    v_d := financeiro.ler_dados_despesa(p_dados, p_perfil_id, false);
    v_rec := coalesce((p_dados ->> 'recorrente')::boolean, false);
    v_venc := (v_d ->> 'data_vencimento')::date;
    if v_rec then
        if v_d ? 'competencia' and (v_d ->> 'competencia')::date <> date_trunc('month', v_venc::timestamp)::date then
            raise exception 'Na recorrencia a competencia e o mes de cada vencimento' using errcode = '22023';
        end if;
    else
        v_comp := coalesce((v_d ->> 'competencia')::date, date_trunc('month', v_venc::timestamp)::date);
        if v_comp < (date_trunc('month', v_venc::timestamp) - interval '12 months')::date
           or v_comp > (date_trunc('month', v_venc::timestamp) + interval '12 months')::date then
            raise exception 'Competencia deve ficar a ate 12 meses do vencimento' using errcode = '22023';
        end if;
    end if;

    -- Mesmos campos que o Flask grava (POST /api/despesas e /api/recorrencias).
    insert into public.item_despesa (perfil_financeiro_id, nome, descricao, valor, data_vencimento, categoria_id,
                                     pago, recorrente, tipo_recorrencia, mes_competencia, tipo, meio_pagamento,
                                     conta_bancaria_id, ativo, criado_em)
    values (p_perfil_id, v_d ->> 'nome', v_d ->> 'descricao', (v_d ->> 'valor')::numeric, v_venc,
            (v_d ->> 'categoria_id')::integer, false, v_rec, coalesce(v_d ->> 'tipo_recorrencia', 'mensal'),
            to_char(v_venc - interval '1 month', 'YYYY-MM'), 'Simples',
            case when (v_d ->> 'debito_automatico')::boolean then 'debito_automatico' end,
            (v_d ->> 'conta_bancaria_id')::integer, true, now() at time zone 'utc')
    returning id into v_item_id;

    if not v_rec then
        insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor,
                                  data_vencimento, status_pagamento, debito_automatico, conta_bancaria_id,
                                  numero_parcela, total_parcelas, observacoes, is_fatura_cartao, estouro_orcamento,
                                  status_fatura, criado_em)
        values (p_perfil_id, v_item_id, v_comp, v_d ->> 'nome', (v_d ->> 'valor')::numeric, v_venc, 'Pendente',
                (v_d ->> 'debito_automatico')::boolean, (v_d ->> 'conta_bancaria_id')::integer, 1, 1,
                v_d ->> 'descricao', false, false, 'ABERTA', now() at time zone 'utc')
        returning id into v_conta_id;
    end if;

    v_resultado := jsonb_build_object('item_id', v_item_id, 'conta_id', v_conta_id, 'recorrente', v_rec,
                                      'competencia', coalesce(v_comp, date_trunc('month', v_venc::timestamp)::date));
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_despesa', v_resultado);
    return v_resultado;
end
$$;

-- criar_receita: texto de 20261027090000 + a linha marcada.
create or replace function financeiro.criar_receita(p_perfil_id integer, p_dados jsonb, p_chave uuid)
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
    v_data      date;
    v_desloc    integer;
    v_dia       integer;
    v_resultado jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
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
    -- Data prevista da (primeira) competencia; na recorrencia ela define a regra: dia contratual e
    -- deslocamento em meses (ex.: competencia 10, prevista 05/11 -> todo dia 5 do mes seguinte).
    v_data := (v_d ->> 'data_prevista')::date;
    perform financeiro.validar_data_prevista(v_comp, v_data);
    if v_data is not null then
        v_dia := extract(day from v_data)::integer;
        v_desloc := (extract(year from v_data)::integer * 12 + extract(month from v_data)::integer)
                    - (extract(year from v_comp)::integer * 12 + extract(month from v_comp)::integer);
    end if;

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
                case when v_rec then (v_d ->> 'valor')::numeric end, coalesce((v_d ->> 'dia_previsto')::integer, v_dia),
                (v_d ->> 'conta_bancaria_id')::integer, v_rec, now() at time zone 'utc')
        returning id into v_item_id;
        select * into v_item from public.item_receita where id = v_item_id;
    end if;

    if v_rec then
        for i in 0..11 loop
            v_mes := (v_comp + make_interval(months => i))::date;
            continue when exists (select 1 from public.receita_orcamento o
                                   where o.item_receita_id = v_item_id and o.mes_referencia = v_mes);
            -- Cada competencia calcula a sua data a partir do dia contratual: sem deriva (31 -> 28 -> 31).
            insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, valor_esperado,
                                                  periodicidade, observacoes, data_prevista, criado_em)
            values (p_perfil_id, v_item_id, v_mes, (v_d ->> 'valor')::numeric, 'MENSAL_FIXA',
                    'Gerado automaticamente - ' || v_item.nome,
                    case when v_data is not null
                         then financeiro.dia_contratual((v_mes + make_interval(months => v_desloc))::date, v_dia) end,
                    now() at time zone 'utc')
            returning id into v_id;
            v_ids := v_ids || v_id;
        end loop;
    else
        if exists (select 1 from public.receita_orcamento o where o.item_receita_id = v_item_id and o.mes_referencia = v_comp) then
            raise exception 'Ja existe previsao desta fonte nesta competencia: edite a existente' using errcode = '22023';
        end if;
        insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, valor_esperado,
                                              periodicidade, observacoes, data_prevista, criado_em)
        values (p_perfil_id, v_item_id, v_comp, (v_d ->> 'valor')::numeric,
                case when coalesce(v_item.recorrente, false) then 'MENSAL_FIXA' else 'UNICA' end,
                v_d ->> 'observacoes', v_data, now() at time zone 'utc')
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

-- definir_meio_pagamento_recorrencia: texto de 20261103090000 + a linha marcada.
create or replace function financeiro.definir_meio_pagamento_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text,
                                                              p_meio text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item public.item_despesa;
    v_meio text := nullif(lower(btrim(coalesce(p_meio, ''))), '');
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    if v_meio is not null and v_meio not in ('boleto', 'pix', 'debito') then
        raise exception 'Meio de pagamento invalido: use boleto, pix, debito ou nenhum (cartao e debito automatico tem fluxo proprio)'
            using errcode = '22023';
    end if;
    v_item := financeiro.travar_recorrencia(p_perfil_id, p_item_id, p_versao);
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    -- Sair do debito automatico solta tambem a conta do debito (como editar_recorrencia com debito_automatico=false).
    update public.item_despesa
       set meio_pagamento = v_meio,
           conta_bancaria_id = case when v_item.meio_pagamento = 'debito_automatico' then null else conta_bancaria_id end
     where id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'meio_pagamento', v_meio, 'versao', financeiro.versao_recorrencia(p_item_id));
end
$$;

-- desativar_limite_cartao: texto de 20261104090000 + a linha marcada.
create or replace function financeiro.desativar_limite_cartao(p_perfil_id integer, p_cartao_id integer, p_limite_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.travar_limite_cartao(p_perfil_id, p_cartao_id, p_limite_id);
    update public.cartao_categoria_limite set ativo = false, updated_at = now() at time zone 'utc' where id = p_limite_id;
    return jsonb_build_object('limite_id', p_limite_id, 'ativo', false);
end
$$;

-- dispensar_aviso_recorrencia: texto de 20261030090000 + a linha marcada.
create or replace function financeiro.dispensar_aviso_recorrencia(p_perfil_id integer, p_item_id integer, p_competencia date)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_comp   date;
    v_reg    public.recorrencia_rejeicao;
    v_linhas financeiro.linha_plano[];
    v_ja     boolean;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_item_id is null or p_competencia is null then
        raise exception 'Recorrencia e competencia sao obrigatorias' using errcode = '22023';
    end if;
    if not exists (select 1 from public.item_despesa i where i.id = p_item_id
                    and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)) then
        raise exception 'Recorrencia nao encontrada neste perfil' using errcode = '42501';
    end if;
    v_comp := date_trunc('month', p_competencia::timestamp)::date;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- em serie com a geracao do perfil
    select * into v_reg from public.recorrencia_rejeicao r
     where r.item_despesa_id = p_item_id and r.competencia = v_comp for update;
    if not found then
        select coalesce(array_agg(p), '{}') into v_linhas from financeiro.plano_recorrencia(p_perfil_id, v_comp) p
         where p.item_despesa_id = p_item_id and p.competencia = v_comp;
        perform financeiro.registrar_rejeicoes_consolidadas(v_linhas, 'NOVO_APP');
        select * into v_reg from public.recorrencia_rejeicao r
         where r.item_despesa_id = p_item_id and r.competencia = v_comp for update;
        if not found then
            raise exception 'Nao ha aviso de recorrencia rejeitada para esta competencia' using errcode = '22023';
        end if;
    end if;
    v_ja := v_reg.aviso_dispensado_em is not null;
    if not v_ja then
        update public.recorrencia_rejeicao
           set aviso_dispensado_em = now() at time zone 'utc', aviso_dispensado_user_id = (select auth.uid())::text
         where id = v_reg.id
        returning * into v_reg;
    end if;
    return jsonb_build_object('id', v_reg.id, 'item_id', v_reg.item_despesa_id, 'competencia', v_reg.competencia,
                              'situacao', v_reg.situacao, 'aviso_dispensado_em', v_reg.aviso_dispensado_em,
                              'ja_dispensado', v_ja);
end
$$;

-- editar_cartao: texto de 20261104090000 + a linha marcada.
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
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
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

-- editar_compra: texto de 20261030090000 + a linha marcada.
create or replace function financeiro.editar_compra(p_perfil_id integer, p_lancamento_id integer, p_versao text, p_dados jsonb)
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
    v_mes     date;
    v_meses   date[];
    v_fatura  integer;
    v_total   numeric;
    v_sugerido date;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    v_abertas := financeiro.travar_compra(p_perfil_id, p_lancamento_id, p_versao);
    select * into v_l from public.lancamento_agregado where id = p_lancamento_id;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da compra invalidos' using errcode = '22023';
    end if;
    if p_dados ? 'descricao' then
        v_desc := btrim(coalesce(p_dados ->> 'descricao', ''));
        if v_desc = '' or length(v_desc) > 200 then
            raise exception 'Descricao obrigatoria (ate 200 caracteres)' using errcode = '22023';
        end if;
    end if;
    if p_dados ? 'categoria_id' then
        v_cat := (p_dados ->> 'categoria_id')::integer;
        if not exists (select 1 from public.categoria c where c.id = v_cat and coalesce(c.ativo, true)) then
            raise exception 'Categoria inexistente ou inativa' using errcode = '22023';
        end if;
        v_cc := financeiro.resolver_categoria_cartao(p_perfil_id, v_l.cartao_id, v_cat);
    end if;
    if p_dados ?| array['valor', 'data_compra', 'mes_fatura'] then
        if coalesce(v_l.total_parcelas, 1) > 1 then
            raise exception 'Compra parcelada: valor e datas nao mudam aqui (exclua as parcelas abertas e lance de novo)'
                using errcode = '22023';
        end if;
        v_valor := coalesce((p_dados ->> 'valor')::numeric, v_l.valor);
        if v_valor <= 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
            raise exception 'Valor deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
        end if;
        v_data := coalesce((p_dados ->> 'data_compra')::date, v_l.data_compra);
        v_mes := coalesce(date_trunc('month', (p_dados ->> 'mes_fatura')::date::timestamp)::date, v_l.mes_fatura);
        if v_mes <> v_l.mes_fatura then
            v_fatura := financeiro.garantir_fatura(p_perfil_id, v_l.cartao_id, v_mes);
            perform 1 from public.conta where id = v_fatura for update;
            if financeiro.fatura_esta_paga(v_fatura) then
                raise exception 'A fatura de destino ja esta paga' using errcode = '22023';
            end if;
            if exists (select 1 from public.conta c where c.id = v_fatura and c.status_fatura = 'FECHADA') then
                v_total := financeiro.exigir_confirmacao_consolidada(v_fatura, p_dados -> 'confirmar_consolidadas', v_valor);
            end if;
        end if;
        if v_data is distinct from v_l.data_compra then
            v_sugerido := (financeiro.sugestao_competencia(v_l.cartao_id, v_data) ->> 'competencia')::date;
        end if;
    end if;
    select array_agg(distinct l.mes_fatura) into v_meses from public.lancamento_agregado l where l.id = any(v_abertas);
    update public.lancamento_agregado l
       set descricao = coalesce(v_desc, l.descricao),
           categoria_id = coalesce(v_cat, l.categoria_id),
           categoria_cartao_id = case when p_dados ? 'categoria_id' then v_cc else l.categoria_cartao_id end,
           observacoes = case when p_dados ? 'observacoes' then coalesce(p_dados ->> 'observacoes', '') else l.observacoes end,
           valor = coalesce(v_valor, l.valor),
           data_compra = coalesce(v_data, l.data_compra),
           mes_fatura = coalesce(v_mes, l.mes_fatura),
           mes_fatura_sugerido = case when v_data is distinct from l.data_compra and v_data is not null
                                      then v_sugerido else l.mes_fatura_sugerido end
     where l.id = any(v_abertas);
    if v_total is not null then
        update public.conta set valor_consolidado = v_total + v_valor where id = v_fatura;
        insert into public.fatura_consolidada_inclusao (fatura_id, cartao_id, perfil_financeiro_id, competencia, compra_id,
                                                        lancamento_id, valor_incluido, total_consolidado_anterior,
                                                        total_consolidado_novo, operacao, origem, user_id, criado_em)
        values (v_fatura, v_l.cartao_id, p_perfil_id, v_mes, v_l.compra_id, p_lancamento_id, v_valor, v_total,
                v_total + v_valor, 'EDICAO', 'NOVO_APP', (select auth.uid())::text, now() at time zone 'utc');
    end if;
    if v_mes is not null and not v_mes = any(v_meses) then
        v_meses := v_meses || v_mes;
    end if;
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_l.cartao_id, v_meses[i]);
    end loop;
    return jsonb_build_object('lancamentos', to_jsonb(v_abertas), 'versao', financeiro.versao_compra(p_lancamento_id));
end
$$;

-- editar_despesa: texto de 20261026090000 + a linha marcada.
create or replace function financeiro.editar_despesa(p_perfil_id integer, p_conta_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta;
    v_item  public.item_despesa;
    v_d     jsonb;
    v_venc  date;
    v_comp  date;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.travar_despesa(p_perfil_id, p_conta_id, p_versao);
    select * into v_conta from public.conta where id = p_conta_id;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id;
    v_d := financeiro.ler_dados_despesa(p_dados, p_perfil_id, true);
    v_venc := coalesce((v_d ->> 'data_vencimento')::date, v_conta.data_vencimento);

    if coalesce(v_item.recorrente, false) then
        if v_d ? 'competencia' and (v_d ->> 'competencia')::date <> v_conta.mes_referencia then
            raise exception 'A competencia de uma conta recorrente nao muda' using errcode = '22023';
        end if;
        if v_d ? 'categoria_id' and (v_d ->> 'categoria_id')::integer is distinct from v_item.categoria_id then
            raise exception 'A categoria e da recorrencia: edite a recorrencia' using errcode = '22023';
        end if;
        if v_venc <> v_conta.data_vencimento and financeiro.gerador_do_perfil(p_perfil_id) <> 'NOVO' then
            raise exception 'Vencimento de conta recorrente gerada pelo sistema atual nao pode mudar aqui'
                using errcode = 'P0001', hint = 'GERADOR_FLASK';
        end if;
        v_comp := v_conta.mes_referencia;
    else
        v_comp := coalesce((v_d ->> 'competencia')::date, v_conta.mes_referencia);
        if v_comp < (date_trunc('month', v_venc::timestamp) - interval '12 months')::date
           or v_comp > (date_trunc('month', v_venc::timestamp) + interval '12 months')::date then
            raise exception 'Competencia deve ficar a ate 12 meses do vencimento' using errcode = '22023';
        end if;
    end if;

    update public.conta c
       set descricao = coalesce(v_d ->> 'nome', c.descricao),
           valor = coalesce((v_d ->> 'valor')::numeric, c.valor),
           data_vencimento = v_venc,
           mes_referencia = v_comp,
           observacoes = case when v_d ? 'descricao' then v_d ->> 'descricao' else c.observacoes end,
           debito_automatico = case when v_d ? 'debito_automatico' then (v_d ->> 'debito_automatico')::boolean
                                    else c.debito_automatico end,
           conta_bancaria_id = case when v_d ? 'debito_automatico' then (v_d ->> 'conta_bancaria_id')::integer
                                    else c.conta_bancaria_id end
     where c.id = p_conta_id;

    if not coalesce(v_item.recorrente, false) then
        -- Avulsa: o item espelha a sua unica conta (como o Flask cria).
        update public.item_despesa i
           set nome = coalesce(v_d ->> 'nome', i.nome),
               valor = coalesce((v_d ->> 'valor')::numeric, i.valor),
               data_vencimento = v_venc,
               mes_competencia = to_char(v_venc - interval '1 month', 'YYYY-MM'),
               categoria_id = coalesce((v_d ->> 'categoria_id')::integer, i.categoria_id),
               descricao = case when v_d ? 'descricao' then v_d ->> 'descricao' else i.descricao end,
               meio_pagamento = case when v_d ? 'debito_automatico'
                                     then case when (v_d ->> 'debito_automatico')::boolean then 'debito_automatico' end
                                     else i.meio_pagamento end,
               conta_bancaria_id = case when v_d ? 'debito_automatico' then (v_d ->> 'conta_bancaria_id')::integer
                                        else i.conta_bancaria_id end
         where i.id = v_item.id;
    end if;
    return jsonb_build_object('conta_id', p_conta_id, 'competencia', v_comp,
                              'versao', financeiro.versao_despesa(p_conta_id));
end
$$;

-- editar_fonte_receita: texto de 20261027090000 + a linha marcada.
create or replace function financeiro.editar_fonte_receita(p_perfil_id integer, p_item_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.travar_fonte(p_perfil_id, p_item_id, p_versao);
    v_d := financeiro.ler_dados_receita(p_dados - 'valor' - 'competencia' - 'observacoes' - 'data_prevista', p_perfil_id, true);
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

-- editar_lancamento_cartao: texto de 20261104090000 + a linha marcada.
create or replace function financeiro.editar_lancamento_cartao(p_perfil_id integer, p_lancamento_id integer, p_versao text,
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
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
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

-- editar_parcelas_futuras: texto de 20261104090000 + a linha marcada.
create or replace function financeiro.editar_parcelas_futuras(p_perfil_id integer, p_lancamento_id integer, p_versao text,
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
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
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

-- editar_receita: texto de 20261027090000 + a linha marcada.
create or replace function financeiro.editar_receita(p_perfil_id integer, p_orcamento_id integer, p_versao text, p_dados jsonb)
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
           observacoes = case when v_d ? 'observacoes' then v_d ->> 'observacoes' else o.observacoes end,
           data_prevista = case when v_d ? 'data_prevista' then (v_d ->> 'data_prevista')::date else o.data_prevista end,
           mes_referencia = v_comp
     where o.id = p_orcamento_id;
    return jsonb_build_object('orcamento_id', p_orcamento_id, 'competencia', v_comp,
                              'versao', financeiro.versao_previsao(p_orcamento_id));
end
$$;

-- editar_recorrencia: texto de 20261026090000 + a linha marcada.
create or replace function financeiro.editar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item public.item_despesa;
    v_d    jsonb;
    v_venc date;
    v_tipo text;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    v_item := financeiro.travar_recorrencia(p_perfil_id, p_item_id, p_versao);
    v_d := financeiro.ler_dados_despesa(p_dados, p_perfil_id, true);
    if v_d ? 'competencia' then
        raise exception 'Na recorrencia a competencia e o mes de cada vencimento' using errcode = '22023';
    end if;
    v_venc := coalesce((v_d ->> 'data_vencimento')::date, v_item.data_vencimento);
    v_tipo := coalesce(v_d ->> 'tipo_recorrencia', v_item.tipo_recorrencia, 'mensal');
    if (v_venc is distinct from v_item.data_vencimento or v_tipo is distinct from coalesce(v_item.tipo_recorrencia, 'mensal'))
       and financeiro.gerador_do_perfil(p_perfil_id) <> 'NOVO' then
        raise exception 'Dia e frequencia so mudam quando o novo aplicativo gera este perfil (o Flask duplicaria por data)'
            using errcode = 'P0001', hint = 'GERADOR_FLASK';
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- nao muda no meio de uma geracao
    update public.item_despesa i
       set nome = coalesce(v_d ->> 'nome', i.nome),
           valor = coalesce((v_d ->> 'valor')::numeric, i.valor),
           categoria_id = coalesce((v_d ->> 'categoria_id')::integer, i.categoria_id),
           data_vencimento = v_venc,
           mes_competencia = case when v_venc is distinct from i.data_vencimento
                                  then to_char(v_venc - interval '1 month', 'YYYY-MM') else i.mes_competencia end,
           tipo_recorrencia = v_tipo,
           descricao = case when v_d ? 'descricao' then v_d ->> 'descricao' else i.descricao end,
           meio_pagamento = case when v_d ? 'debito_automatico'
                                 then case when (v_d ->> 'debito_automatico')::boolean then 'debito_automatico' end
                                 else i.meio_pagamento end,
           conta_bancaria_id = case when v_d ? 'debito_automatico' then (v_d ->> 'conta_bancaria_id')::integer
                                    else i.conta_bancaria_id end
     where i.id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'versao', financeiro.versao_recorrencia(p_item_id));
end
$$;

-- excluir_compra: texto de 20261028090000 + a linha marcada.
create or replace function financeiro.excluir_compra(p_perfil_id integer, p_lancamento_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_abertas integer[];
    v_l       public.lancamento_agregado;
    v_meses   date[];
    v_total   integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    v_abertas := financeiro.travar_compra(p_perfil_id, p_lancamento_id, p_versao);
    select * into v_l from public.lancamento_agregado where id = p_lancamento_id;
    select count(*) into v_total from financeiro.parcelas_da_compra(p_lancamento_id);
    select array_agg(distinct l.mes_fatura) into v_meses from public.lancamento_agregado l where l.id = any(v_abertas);
    delete from public.lancamento_agregado where id = any(v_abertas);
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_l.cartao_id, v_meses[i]);
    end loop;
    return jsonb_build_object('excluidas', cardinality(v_abertas), 'preservadas', v_total - cardinality(v_abertas));
end
$$;

-- excluir_despesa: texto de 20261026090000 + a linha marcada.
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

-- excluir_receita: texto de 20261027090000 + a linha marcada.
create or replace function financeiro.excluir_receita(p_perfil_id integer, p_orcamento_id integer, p_versao text)
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
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
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

-- importar_fatura_cartao: texto de 20261105090000 + a linha marcada.
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
        continue when (v_l ->> 'ignorar')::boolean;
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
    if jsonb_array_length(v_a_gravar) = 0 then
        raise exception 'Nenhuma linha para importar' using errcode = '22023';
    end if;

    for v_l in select e from jsonb_array_elements(v_a_gravar) e loop
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
                                                    is_importado, origem_importacao, criado_em, mes_fatura_original)
            values (coalesce((select c.perfil_financeiro_id from public.conta c where c.id = v_fat), p_perfil_id),
                    p_cartao_id, null, (v_l ->> 'categoria_cartao_id')::integer, (v_l ->> 'categoria_id')::integer,
                    left(v_l ->> 'descricao_normalizada', 200), v_l ->> 'descricao_original', v_l ->> 'descricao_normalizada',
                    case when v_n > 1 and (v_l ->> 'gerar_parcelas_futuras')::boolean
                         then format('%s (%s/%s)', v_l ->> 'descricao_exibida', v_k, v_n) else v_l ->> 'descricao_exibida' end,
                    (v_l ->> 'valor')::numeric, ((v_l ->> 'data_compra')::date + make_interval(months => v_k - v_inicio))::date,
                    v_alvo, v_k, v_n, '', (v_l ->> 'recorrencia_id') is not null, (v_l ->> 'recorrencia_id')::integer,
                    v_compra, true, left(coalesce(v_l ->> 'origem_importacao', 'csv'), 20), now() at time zone 'utc',
                    nullif(v_orig, v_alvo))
            returning id into v_id;
            v_ids := v_ids || v_id;
            if not v_alvo = any(v_meses) then
                v_meses := v_meses || v_alvo;
            end if;
        end loop;
    end loop;
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, p_cartao_id, v_meses[i]);
    end loop;

    select count(*) into v_dup from jsonb_array_elements(v_analise -> 'linhas') e
     where e ->> 'status' in ('duplicado', 'conciliado');
    v_res := jsonb_build_object(
        'inseridos', cardinality(v_ids), 'linhas_importadas', jsonb_array_length(v_a_gravar), 'duplicados', v_dup,
        'lancamentos', to_jsonb(v_ids), 'faturas', to_jsonb(v_meses), 'cartao_id', p_cartao_id,
        'competencia', to_char(v_comp, 'YYYY-MM'));
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'importar_fatura', v_res);
    return v_res;
end
$$;

-- inativar_cartao: texto de 20261028090000 + a linha marcada.
create or replace function financeiro.inativar_cartao(p_perfil_id integer, p_cartao_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    perform 1 from public.item_despesa where id = p_cartao_id for update;
    if p_versao is distinct from (select c.versao from financeiro.cartoes_do_perfil(p_perfil_id) c where c.id = p_cartao_id) then
        raise exception 'O cartao foi alterado por outra operacao. Recarregue e tente de novo.' using errcode = 'P0001';
    end if;
    update public.item_despesa set ativo = false where id = p_cartao_id;  -- nunca exclusao fisica
    return jsonb_build_object('cartao_id', p_cartao_id, 'ativo', false);
end
$$;

-- inativar_fonte_receita: texto de 20261027090000 + a linha marcada.
create or replace function financeiro.inativar_fonte_receita(p_perfil_id integer, p_item_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.travar_fonte(p_perfil_id, p_item_id, p_versao);
    update public.item_receita set ativo = false where id = p_item_id;
    return jsonb_build_object('item_receita_id', p_item_id, 'ativo', false);
end
$$;

-- inativar_perfil: texto de 20261102090000 + a linha marcada.
create or replace function financeiro.inativar_perfil(p_perfil_id integer)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_perfil public.perfil_financeiro%rowtype;
    v_novo_padrao integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id, true);  -- FIN-ESCRITOR-UNICO-FINAL-1
    if not financeiro.gere_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(hashtext('financeiro.perfil_financeiro.gestao'));
    select * into v_perfil from public.perfil_financeiro p where p.id = p_perfil_id for update;
    if not v_perfil.ativo then
        return financeiro.perfil_em_json(p_perfil_id);
    end if;
    if (select count(*) from financeiro.perfil_acesso a
          join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
         where a.user_id = (select auth.uid()) and p.ativo) <= 1 then
        raise exception 'Nao e possivel inativar o unico perfil ativo' using errcode = '22023';
    end if;
    if v_perfil.padrao then
        select p.id into v_novo_padrao
          from public.perfil_financeiro p
         where p.ativo and p.id <> p_perfil_id and financeiro.gere_perfil(p.id)
         order by p.id
         limit 1;
        if v_novo_padrao is null then
            raise exception 'Defina outro perfil padrao antes de inativar este' using errcode = '22023';
        end if;
    end if;

    update public.perfil_financeiro
       set ativo = false, padrao = false, updated_at = (now() at time zone 'utc')
     where id = p_perfil_id;
    if v_novo_padrao is not null then
        perform financeiro.aplicar_perfil_padrao(v_novo_padrao);
    end if;
    return financeiro.perfil_em_json(p_perfil_id);
end
$$;

-- inativar_recorrencia: texto de 20261026090000 + a linha marcada.
create or replace function financeiro.inativar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.travar_recorrencia(p_perfil_id, p_item_id, p_versao);
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    update public.item_despesa set ativo = false where id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'ativo', false);
end
$$;

-- reativar_perfil: texto de 20261102090000 + a linha marcada.
create or replace function financeiro.reativar_perfil(p_perfil_id integer)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id, true);  -- FIN-ESCRITOR-UNICO-FINAL-1
    if not financeiro.gere_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(hashtext('financeiro.perfil_financeiro.gestao'));
    update public.perfil_financeiro
       set ativo = true, updated_at = (now() at time zone 'utc')
     where id = p_perfil_id and not ativo;
    if not exists (select 1 from public.perfil_financeiro p where p.padrao and p.ativo) then
        perform financeiro.aplicar_perfil_padrao(p_perfil_id);
    end if;
    return financeiro.perfil_em_json(p_perfil_id);
end
$$;

-- reativar_recorrencia: texto de 20261103090000 + a linha marcada.
create or replace function financeiro.reativar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.travar_recorrencia(p_perfil_id, p_item_id, p_versao);
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- nao muda no meio de uma geracao
    update public.item_despesa set ativo = true where id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'ativo', true, 'versao', financeiro.versao_recorrencia(p_item_id));
end
$$;

-- vincular_limite_cartao: texto de 20261104090000 + a linha marcada.
create or replace function financeiro.vincular_limite_cartao(p_perfil_id integer, p_cartao_id integer, p_dados jsonb)
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
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
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
