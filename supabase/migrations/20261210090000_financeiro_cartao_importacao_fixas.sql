-- FIN-CARTAO-IMPORTACAO-FIXAS-01 — reconhecimento, classificacao e conciliacao das despesas fixas durante a importacao da fatura.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261210090000). Depende de 20261208090000 e 20261209090000.
-- Validada em cluster local descartavel (tests/test_supabase_cartao_importacao_fixas.py) e ensaiada numa copia fiel da
-- producao. Doc: docs/FIN_CARTAO_IMPORTACAO_FIXAS_01.md. Gerada por scripts/gerar_migration_cartao_importacao_fixas.py.
-- Reversao: supabase/reversao/20261210090000_cartao_importacao_fixas_anterior.sql.
--
-- Na previa (analisar_importacao_cartao, so leitura), cada linha traz a classificacao proposta:
-- JA_EXISTENTE / PARCELA_EXISTENTE (nao grava de novo), DESPESA_FIXA (recorrencia, previsto, cobrado, diferenca,
-- competencia e fatura de destino), PARCELADA, COMPRA (Categoria do Cartao ou Outros), REVISAR ou IGNORADA. A previa aceita
-- a correcao do usuario: recorrencia_escolhida_id (outra recorrencia do cartao, ou 0 = compra comum), salvar_apelido,
-- conciliar_previsao (compra ja lancada + previsao) e manter_duplicada (duas compras iguais legitimas no arquivo).
-- Nada e descartado em silencio: segunda cobranca do mes, previsao ja cobrada, em fatura paga ou consolidada pedem revisao.
-- Recorrencia inativada com previsao pendente na competencia ainda reconhece a cobranca.
-- Na confirmacao (importar_fatura_cartao), tudo numa transacao, com a analise refeita sob as travas: realiza as
-- previsoes, grava as compras, concilia as pedidas e registra os apelidos pedidos. Nenhum dado existente e alterado
-- pela migration.
--
-- Funcoes existentes substituidas pelo texto vigente com os trechos marcados "FIN-CARTAO-IMPORTACAO-FIXAS-01": analisar_importacao_cartao
-- (texto de 20261209090000) e importar_fatura_cartao (texto de 20261208090000).

-- =====================================================================================================================
-- 1. Conciliacao e apelido dentro da importacao (internas; a importacao ja autorizou e travou o perfil)
-- =====================================================================================================================
-- Previsao da recorrencia + compra comum ja lancada (a cobranca real), mesmo cartao e mesma fatura aberta: a previsao fica
-- (identidade da recorrencia) com os dados da cobranca; a compra da cobranca sai, inteira na auditoria
-- (ocorrencia_recorrencia_cartao.lancamento_absorvido). Reversivel por reverter_ocorrencia_recorrencia.
create function financeiro.conciliar_previsao_interna(p_perfil_id integer, p_previsto_id integer, p_cobranca_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_prev public.lancamento_agregado;
    v_cob  public.lancamento_agregado;
begin
    select * into v_prev from public.lancamento_agregado where id = p_previsto_id for update;
    select * into v_cob from public.lancamento_agregado where id = p_cobranca_id for update;
    if v_prev.id is null or v_cob.id is null or p_previsto_id = p_cobranca_id
       or not financeiro.pertence_ao_perfil(v_prev.perfil_financeiro_id, p_perfil_id)
       or not financeiro.pertence_ao_perfil(v_cob.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Compra nao encontrada neste perfil' using errcode = '42501';
    end if;
    if v_cob.cartao_id <> v_prev.cartao_id or v_cob.mes_fatura <> v_prev.mes_fatura then
        raise exception 'A previsao e a cobranca devem estar no mesmo cartao e na mesma fatura' using errcode = '22023';
    end if;
    if financeiro.natureza_da_compra(v_cob.total_parcelas, v_cob.is_recorrente, v_cob.item_despesa_id, v_cob.categoria_cartao_id)
       not in ('CATEGORIA', 'OUTROS') or v_cob.item_despesa_id is not null then
        raise exception 'A cobranca deve ser uma compra comum (nem parcelada, nem de recorrencia)' using errcode = '22023';
    end if;
    if exists (select 1 from public.fatura_consolidada_inclusao i where i.lancamento_id = v_cob.id) then
        raise exception 'A cobranca foi incluida numa fatura consolidada: concilie pela propria fatura' using errcode = 'P0001';
    end if;
    perform financeiro.realizar_ocorrencia_recorrencia(p_perfil_id, v_prev.id,
        jsonb_build_object('valor', v_cob.valor, 'data_compra', v_cob.data_compra,
                           'descricao_original', coalesce(v_cob.descricao_original, v_cob.descricao),
                           'descricao_original_normalizada', coalesce(v_cob.descricao_original_normalizada, v_cob.descricao),
                           'is_importado', coalesce(v_cob.is_importado, false), 'origem_importacao', v_cob.origem_importacao),
        'CONCILIACAO', to_jsonb(v_cob));
    delete from public.lancamento_agregado where id = v_cob.id;  -- inteira em ocorrencia_recorrencia_cartao.lancamento_absorvido
    return jsonb_build_object('previsto_id', v_prev.id, 'cobranca_id', v_cob.id, 'fatura', v_prev.mes_fatura,
                              'valor_previsto', v_prev.valor, 'valor_executado', v_cob.valor);
end
$$;

-- Apelido de cobranca confirmado na importacao: as mesmas regras de criar_apelido_recorrencia (texto normalizado de 3 a 80
-- letras ou numeros; recusado se reconheceria outra recorrencia do cartao).
create function financeiro.registrar_apelido_recorrencia(p_perfil_id integer, p_item_id integer, p_apelido text)
    returns bigint
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item  public.item_despesa;
    v_texto text := financeiro.texto_cobranca(p_apelido);
    v_outra text;
    v_id    bigint;
begin
    v_item := financeiro.recorrencia_cartao_do_perfil(p_perfil_id, p_item_id);
    if length(v_texto) < 3 or length(v_texto) > 80 then
        raise exception 'Apelido deve ter de 3 a 80 letras ou numeros' using errcode = '22023';
    end if;
    select i.nome into v_outra
      from financeiro.recorrencia_apelido a join public.item_despesa i on i.id = a.item_despesa_id
     where a.apelido = v_texto and a.ativo and a.item_despesa_id <> p_item_id and i.cartao_id = v_item.cartao_id
     limit 1;
    if v_outra is null then
        select i.nome into v_outra from public.item_despesa i
         where i.id <> p_item_id and i.cartao_id = v_item.cartao_id and coalesce(i.recorrente, false) and coalesce(i.ativo, true)
           and i.meio_pagamento = 'cartao' and financeiro.texto_cobranca(i.nome) = v_texto
         limit 1;
    end if;
    if v_outra is not null then
        raise exception 'Apelido "%" ja reconhece outra recorrencia deste cartao: %', v_texto, v_outra using errcode = '22023';
    end if;
    insert into financeiro.recorrencia_apelido (perfil_financeiro_id, item_despesa_id, apelido, user_id)
    values (p_perfil_id, p_item_id, v_texto, (select auth.uid()))
    on conflict (item_despesa_id, apelido) do update set ativo = true
    returning id into v_id;
    return v_id;
end
$$;

-- =====================================================================================================================
-- 2. Previa e confirmacao da importacao: texto vigente + os trechos marcados
-- =====================================================================================================================

-- analisar_importacao_cartao: texto de 20261209090000 + os trechos marcados.
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
        -- diferentes e nenhum entra como compra nem reduz a fatura por aqui (como o Flask, que nao importa credito).
        v_credito := case when v_tipo <> 'credito' then null
            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(pagamento|pgto|pag[ .]?fatura|obrigado pelo pag)' then 'pagamento_fatura'
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

        -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencia do cartao pela descricao. O nome da recorrencia ou um apelido de cobranca
        -- (financeiro.recorrencia_apelido) aparece como palavras inteiras no texto normalizado da linha: mesmo
        -- cartao, recorrencia ativa paga no cartao. O valor nunca identifica; so desempata quando ha mais de uma.
        v_cands := '[]'::jsonb;
        v_rec_cat := null;
        v_rec_nome := null;
        v_realiza := null;
        v_prev := null;
        v_texto := ' ' || financeiro.texto_cobranca(v_norm) || ' ';
        if v_tipo <> 'credito' and btrim(v_texto) <> '' then
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
            if v_escolha = 0 then
                v_cands := '[]'::jsonb;
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
                    v_msgs := v_msgs || '"Recorrencia escolhida nao e deste cartao (ou esta inativa): escolha outra ou trate como compra comum."'::jsonb;
                end if;
            end if;
            v_rec := case when jsonb_array_length(v_cands) = 1 then (v_cands -> 0 ->> 'id')::integer end;
            v_rec_cat := (v_cands -> 0 ->> 'categoria_id')::integer;
            v_rec_nome := v_cands -> 0 ->> 'nome';
        end if;

        -- Validacao (ImportacaoCartaoUnificadoService.validar_linhas)
        if v_tipo = 'credito' then
            v_status := 'ignorado';
            v_ignorar := true;
            v_msgs := v_msgs || case v_credito
                when 'pagamento_fatura' then '"Pagamento da fatura: nao e compra nem desconto; o pagamento e registrado em Despesas (pagar fatura)."'::jsonb
                when 'estorno' then '"Estorno de compra: nao importado; a compra original continua na fatura. Se ela deve sair, corrija pela propria compra."'::jsonb
                else '"Credito ou ajuste da administradora: nao importado como despesa."'::jsonb end;
        elsif v_valor is null or v_valor = 0 then
            v_status := 'ignorado';
            v_ignorar := true;
            v_msgs := v_msgs || '"Valor ausente ou zero."'::jsonb;
        else
            if v_data is null then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Data de compra ausente."'::jsonb;
            end if;
            if v_norm = '' then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Descricao ausente."'::jsonb;
            end if;
            if v_parc < 1 or v_total < 1 or v_parc > v_total or v_total > 60 then
                v_status := 'revisar';
                v_msgs := v_msgs || to_jsonb(format('Parcela fora do intervalo: %s/%s', v_parc, v_total));
            end if;
            if v_valor >= 100000000 then
                v_status := 'revisar';
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
                v_sug := financeiro.sugestao_categoria_importacao(p_perfil_id, v_l ->> 'descricao_classificacao', v_norm,
                                                                  v_cartao.categoria_id);
                v_cat := (v_sug ->> 'categoria_id')::integer;
                v_cat_origem := v_sug ->> 'origem';
                if v_sug ->> 'aviso' is not null then
                    v_msgs := v_msgs || to_jsonb(v_sug ->> 'aviso');
                end if;
            end if;
            if v_cat is null and v_status = 'valido' then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Informe a categoria da despesa."'::jsonb;
            end if;
        end if;

        -- Duplicidade (chave de negocio do Flask) no lote e no banco; depois, conciliacao com compra ja lancada.
        v_chave := null;
        if v_status <> 'ignorado' and v_data is not null and v_norm <> '' and v_valor is not null then
            v_chave := concat_ws('|', p_cartao_id, v_comp, v_data, v_valor, lower(v_norm), v_parc, v_total);
            -- FIN-CARTAO-IMPORTACAO-FIXAS-01: repetida no proprio arquivo, mas mantida pelo usuario (duas compras legitimas iguais)
            if v_chave = any(v_chaves) and not coalesce((v_l ->> 'manter_duplicada')::boolean, false) then
                v_dup := 'lote';
            else
                -- FIN-CARTAO-IMPORTACAO-FIXAS-01: a compra ja gravada (para sugerir a conciliacao com a previsao, abaixo)
                select l.id into v_existente from public.lancamento_agregado l
                 where l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
                   and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp
                   and l.data_compra = v_data and l.valor = v_valor
                   and l.numero_parcela = v_parc and l.total_parcelas = v_total
                   and lower(coalesce(l.descricao_original_normalizada, l.descricao)) = lower(v_norm)
                 order by l.id limit 1;
                if v_existente is not null then
                    v_dup := 'banco';
                end if;
            end if;
            if v_dup is not null then
                v_status := 'duplicado';
                v_ignorar := true;
                v_msgs := v_msgs || '"Possivel duplicidade detectada."'::jsonb;
            else
                v_chaves := v_chaves || v_chave;
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
                   and abs(l.data_compra - v_data) <= 5
                   -- FIN-CARTAO-DESPESAS-FIXAS-01: compra de recorrencia (prevista ou realizada) nunca e conciliada so pelo valor
                   -- (ChatGPT de R$ 109,90 nao e o Claude); ela e encontrada pela descricao, abaixo.
                   and not (coalesce(l.is_recorrente, false) and l.item_despesa_id is not null)
                   and not l.id = any(v_usados)
                 order by abs(l.data_compra - v_data), l.id
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
                    v_msgs := v_msgs || to_jsonb(format('"%s" ja tem cobranca nesta fatura (R$ %s em %s). Se esta e outra cobranca, trate como compra comum; se e a mesma, retire a linha.',
                        v_rec_nome, to_char(v_occ.valor, 'FM999999990.00'), to_char(v_occ.data_compra, 'DD/MM/YYYY')));
                elsif financeiro.fatura_esta_paga(v_fat_occ) then
                    v_status := 'revisar';
                    v_msgs := v_msgs || to_jsonb(format('A previsao de "%s" esta em fatura paga (%s): se esta cobranca e outra, trate como compra comum (entra na proxima fatura aberta); se ja foi paga, retire a linha.',
                        v_rec_nome, to_char(v_occ.mes_fatura, 'MM/YYYY')));
                else
                    v_status := 'revisar';
                    v_msgs := v_msgs || to_jsonb(format('A previsao de "%s" esta em fatura consolidada (%s): ela nao recebe cobranca por aqui; retire a linha ou trate como compra comum de outra competencia.',
                        v_rec_nome, to_char(v_occ.mes_fatura, 'MM/YYYY')));
                end if;
            elsif v_rec = any(v_novas) then
                v_status := 'revisar';
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
            elsif v_rec is null then  -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencia nao precisa de Categoria do Cartao
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
            when v_cat_origem = 'ambigua' then 'ambigua'
            when v_cat is null then 'categoria_despesa_pendente'
            when v_cc_origem = 'nao_vinculada_ao_cartao' then 'categoria_cartao_nao_vinculada'
            when v_rec is not null then 'classificada'
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
            when v_tipo = 'credito' or v_status = 'ignorado' then 'IGNORADA'
            when v_status in ('duplicado', 'conciliado') then case when v_total > 1 then 'PARCELA_EXISTENTE' else 'JA_EXISTENTE' end
            when v_status = 'revisar' then 'REVISAR'
            when v_rec is not null then 'DESPESA_FIXA'
            when v_total > 1 then 'PARCELADA'
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
            'manter_duplicada', coalesce((v_l ->> 'manter_duplicada')::boolean, false)));
    end loop;

    return jsonb_build_object(
        'cartao_id', p_cartao_id, 'competencia', to_char(v_comp, 'YYYY-MM'),
        'situacao_fatura', financeiro.situacao_fatura(financeiro.fatura_do_mes(p_cartao_id, v_comp)),
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
            'conciliacoes_sugeridas', count(*) filter (where jsonb_typeof(l -> 'conciliacao_sugerida') = 'object'),
            'sem_categoria_cartao', count(*) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and l ->> 'status' not in ('duplicado', 'ignorado', 'conciliado')
                                                       and l ->> 'categoria_cartao_id' is null
                                                       and l ->> 'recorrencia_id' is null and (l ->> 'total_parcelas')::integer <= 1),
            'total_importavel', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and not (l ->> 'ignorar')::boolean), 0),
            'creditos', count(*) filter (where l ->> 'tipo_movimento' = 'credito'),
            'total_creditos', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'credito'), 0),
            'ignorados', count(*) filter (where l ->> 'status' = 'ignorado'))
            from jsonb_array_elements(v_saida) l));
end
$$;

-- importar_fatura_cartao: texto de 20261208090000 + os trechos marcados.
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
    if jsonb_array_length(v_a_gravar) = 0 and jsonb_array_length(v_conciliar) = 0 then
        raise exception 'Nenhuma linha para importar' using errcode = '22023';
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
        'lancamentos', to_jsonb(v_ids), 'faturas', to_jsonb(v_meses), 'cartao_id', p_cartao_id,
        'competencia', to_char(v_comp, 'YYYY-MM'));
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'importar_fatura', v_res);
    return v_res;
end
$$;

-- Internas: sem EXECUTE para o navegador.
revoke execute on function financeiro.conciliar_previsao_interna(integer, integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.registrar_apelido_recorrencia(integer, integer, text) from public, anon, authenticated;
