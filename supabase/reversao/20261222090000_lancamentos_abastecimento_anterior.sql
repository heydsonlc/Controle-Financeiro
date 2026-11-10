-- Reversao de 20261222090000 (FIN-MVP-LANCAMENTOS-03, parte A): volta importar_fatura_cartao e abastecimentos_veiculo_tela ao
-- texto publicado antes dela (lido da producao em 09/11/2026, na 20261221090000; sem CR) e remove as funcoes novas. Nenhuma
-- tabela muda: os vinculos de abastecimento ja gravados continuam (sao os mesmos de vincular_abastecimento). So com
-- autorizacao, retirando a versao de supabase_migrations.schema_migrations.
CREATE OR REPLACE FUNCTION financeiro.importar_fatura_cartao(p_perfil_id integer, p_cartao_id integer, p_competencia date, p_linhas jsonb, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
    -- FIN-CARTAO-CREDITOS-02: a marca interna que dispensa a duplicidade so vale na consulta da compra original, abaixo
    v_analise := financeiro.analisar_importacao_cartao(p_perfil_id, p_cartao_id, v_comp,
        case when jsonb_typeof(p_linhas) = 'array'
             then (select coalesce(jsonb_agg(case when jsonb_typeof(e) = 'object' then e - '_interna_sem_duplicidade' else e end order by o),
                                   '[]'::jsonb)
                     from jsonb_array_elements(p_linhas) with ordinality as x(e, o))
             else p_linhas end);
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
                           '_interna_sem_duplicidade', true,  -- FIN-CARTAO-CREDITOS-02: decidida acima; aqui so a compra original
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
$function$;

CREATE OR REPLACE FUNCTION financeiro.abastecimentos_veiculo_tela(p_perfil_id integer, p_veiculo_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_v public.veiculo;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_v := financeiro.veiculo_do_perfil(p_perfil_id, p_veiculo_id);
    if v_v.id is null then
        raise exception 'Veículo não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return jsonb_build_object(
        'quilometragem', financeiro.mob_km_veiculo(v_v, (financeiro.uso_do_veiculo(v_v, 3) ->> 'media_movel_km_mes')::numeric),
        'abastecimentos', coalesce((
            select jsonb_agg(financeiro.mob_abastecimento_flask(x.a) || jsonb_build_object('km_rodados', x.km_rodados)
                             order by (x.a).anulado_em is not null, (x.a).data_abastecimento desc, (x.a).hodometro_km desc, (x.a).id desc)
              from (select t as a,
                           case when t.anulado_em is null
                                then t.hodometro_km - lag(t.hodometro_km) over (partition by t.anulado_em is null
                                                                                order by t.data_abastecimento, t.hodometro_km, t.id) end as km_rodados
                      from financeiro.abastecimento t where t.veiculo_id = v_v.id) x), '[]'::jsonb));
end
$function$;

drop function financeiro.abastecimentos_da_importacao(integer, integer, jsonb);
drop function financeiro.mob_vincular_importacao(integer, integer, integer);
drop function financeiro.mob_despesa_do_abastecimento(integer, integer);
