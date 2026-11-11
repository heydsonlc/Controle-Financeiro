-- Reversao da 20261227090000 (P24): volta criar_consorcio ao texto publicado antes dela e remove as funcoes novas.
-- Os recebimentos de contemplacao realizados, as parcelas editadas e as parcelas anteriores registradas continuam como
-- estao (as anteriores tem a sua propria reversao: financeiro.reverter_regularizacao_historica, por lote).

CREATE OR REPLACE FUNCTION financeiro.criar_consorcio(p_perfil_id integer, p_dados jsonb, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_repetida  jsonb;
    v_d         jsonb;
    v_c         public.contrato_consorcio;
    v_categoria integer;
    v_parcelas  jsonb;
    v_receita   boolean;
    v_resultado jsonb;
    v_campo     text;
begin
    perform financeiro.exigir_escrita_consorcio(p_perfil_id);
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'criar_consorcio');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do consorcio invalidos' using errcode = '22023';
    end if;
    foreach v_campo in array array['nome', 'valor_inicial', 'numero_parcelas', 'categoria_id'] loop
        if nullif(btrim(coalesce(p_dados ->> v_campo, '')), '') is null or (p_dados ->> v_campo) in ('0', 'false') then
            raise exception 'Campo % é obrigatório', v_campo using errcode = '22023';
        end if;
    end loop;
    v_categoria := (p_dados ->> 'categoria_id')::integer;
    if not exists (select 1 from public.categoria c where c.id = v_categoria) then
        raise exception 'Categoria não encontrada' using errcode = '22023';
    end if;
    perform financeiro.exigir_nome_consorcio_livre(p_perfil_id, btrim(p_dados ->> 'nome'), null);
    v_d := financeiro.consorcio_normalizar(p_dados, null);
    insert into public.contrato_consorcio (perfil_financeiro_id, nome, valor_inicial, tipo_reajuste, valor_reajuste, numero_parcelas,
                                           mes_inicio, mes_contemplacao, valor_premio, item_receita_id, observacoes, ativo, criado_em)
    values (p_perfil_id, btrim(p_dados ->> 'nome'), (v_d ->> 'valor_inicial')::numeric, v_d ->> 'tipo_reajuste',
            (v_d ->> 'valor_reajuste')::numeric, (v_d ->> 'numero_parcelas')::integer, (v_d ->> 'mes_inicio')::date,
            (v_d ->> 'mes_contemplacao')::date, (v_d ->> 'valor_premio')::numeric,
            nullif(p_dados ->> 'item_receita_id', '')::integer, nullif(p_dados ->> 'observacoes', ''), true, now() at time zone 'utc')
    returning * into v_c;
    v_parcelas := financeiro.sincronizar_parcelas_consorcio(v_c, v_categoria, financeiro.consorcio_pagamento(p_dados), '{}');
    v_receita := financeiro.sincronizar_receita_contemplacao(v_c);
    v_resultado := jsonb_build_object('data', financeiro.consorcio_flask(v_c), 'parcelas_geradas', (v_parcelas ->> 'criadas')::integer,
                                      'receita_gerada', v_receita);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_consorcio', v_resultado);
    return v_resultado;
end
$function$;

drop function financeiro.editar_parcela_consorcio(integer, integer, text, jsonb, text);
drop function financeiro.realizar_contemplacao_consorcio(integer, integer, jsonb, uuid);
drop function financeiro.registrar_parcelas_anteriores_consorcio(integer, public.contrato_consorcio, integer);
drop function financeiro.consorcio_parcelas_anteriores(jsonb, integer, date);
