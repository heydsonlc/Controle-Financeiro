-- FIN-FATURA-UNICA-1 — uma unica fatura por cartao e competencia, garantida pelo banco.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261025090000).
-- Validada em cluster local descartavel, com concorrencia real Flask x novo motor
-- (tests/test_supabase_fatura_unica.py).
--
-- Causa: o Flask (CartaoService.get_or_create_fatura) e o novo motor (gerar_mes)
-- consultam a fatura e depois inserem; duas transacoes simultaneas podiam inserir a
-- mesma fatura. Identidade real (conferida no modelo): o cartao (item_despesa tipo
-- 'Agregador', que tem um unico perfil) + cartao_competencia (sempre dia 1), so nas
-- linhas is_fatura_cartao. O perfil nao entra na chave: a fatura sempre nasce no
-- perfil do cartao, e inclui-lo permitiria duplicar a fatura de um mesmo cartao.
--
-- - Verifica duplicidades historicas ANTES; havendo, aborta sem alterar nada.
-- - Indice unico parcial com o MESMO nome/predicado do model do Flask e da migration
--   Alembic d81f5a2b9c3e (IF NOT EXISTS: quem rodar primeiro cria).
-- - gerar_mes_interno: a fatura usa ON CONFLICT DO NOTHING e a conflitante e contada
--   como existente (idempotente). Nada mais muda na funcao.
-- Nenhum dado, valor, pagamento ou compra e alterado.

do $$
declare
    v_duplicados integer;
begin
    select count(*) into v_duplicados
      from (select 1 from public.conta
             where is_fatura_cartao and cartao_competencia is not null
             group by item_despesa_id, cartao_competencia having count(*) > 1) d;
    if v_duplicados > 0 then
        raise exception 'FIN-FATURA-UNICA-1: % fatura(s) duplicada(s) (cartao + competencia). Nada foi alterado: '
                        'rode scripts/diagnostico_faturas_duplicadas.py e decida o tratamento.', v_duplicados;
    end if;
end
$$;

create unique index if not exists ux_conta_fatura_cartao_competencia
    on public.conta (item_despesa_id, cartao_competencia)
    where is_fatura_cartao;

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
            insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, item_agregado_id, categoria_cartao_id,
                                                    categoria_id, descricao, valor, data_compra, mes_fatura,
                                                    numero_parcela, total_parcelas, observacoes, is_recorrente,
                                                    item_despesa_id, compra_id, is_importado, criado_em)
            values (v_linha.perfil_destino, v_linha.cartao_id, null, v_linha.categoria_cartao_id,
                    v_linha.categoria_id, v_linha.nome, v_linha.valor, v_linha.data_vencimento, v_linha.competencia,
                    1, 1, v_linha.observacoes, true,
                    v_linha.item_despesa_id, v_linha.compra_id, false, now() at time zone 'utc')
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

-- create or replace preserva os privilegios (interna: sem EXECUTE para o navegador).
revoke execute on function financeiro.gerar_mes_interno(integer, date, integer, jsonb) from public, anon, authenticated;
