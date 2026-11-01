-- Reversao de 20261210090000 (FIN-CARTAO-IMPORTACAO-FIXAS-01): volta a previa e a confirmacao da importacao ao texto anterior e remove as
-- funcoes internas novas. Os apelidos registrados e as conciliacoes feitas continuam (sao dados de 20261208090000 e se
-- desfazem pelas funcoes de la). So com autorizacao, retirando a versao de supabase_migrations.schema_migrations.

-- analisar_importacao_cartao: texto de 20261209090000.
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
             where coalesce(i.recorrente, false) and coalesce(i.ativo, true) and i.tipo <> 'Agregador'
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
            if v_chave = any(v_chaves) then
                v_dup := 'lote';
            elsif exists (select 1 from public.lancamento_agregado l
                           where l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
                             and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp
                             and l.data_compra = v_data and l.valor = v_valor
                             and l.numero_parcela = v_parc and l.total_parcelas = v_total
                             and lower(coalesce(l.descricao_original_normalizada, l.descricao)) = lower(v_norm)) then
                v_dup := 'banco';
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

        -- FIN-CARTAO-DESPESAS-FIXAS-01: ocorrencia da recorrencia reconhecida pela descricao (acima). Com a previsao do mes ainda sem
        -- cobranca, a linha a realiza: a compra prevista fica (identidade da recorrencia) com o valor real, e o
        -- previsto vai para financeiro.ocorrencia_recorrencia_cartao. Previsao ja realizada, ou em fatura paga ou
        -- consolidada: a linha sai da efetivacao, a compra existente fica como esta.
        if v_status in ('ignorado', 'duplicado', 'conciliado') or v_norm = '' then
            v_rec := null;
        elsif jsonb_array_length(v_cands) > 1 then
            v_status := 'revisar';
            v_msgs := v_msgs || to_jsonb(format('Mais de uma recorrencia do cartao combina com a descricao (%s): a linha nao foi vinculada; revise os nomes ou os apelidos de cobranca.',
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
                if coalesce(v_occ.is_recorrente, false) and coalesce(v_occ.total_parcelas, 1) = 1
                   and not coalesce(v_occ.is_importado, false)
                   and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                    where o.lancamento_id = v_occ.id and o.revertida_em is null)
                   and (v_fat_occ is null or not (financeiro.fatura_esta_paga(v_fat_occ)
                        or exists (select 1 from public.conta c where c.id = v_fat_occ and c.status_fatura = 'FECHADA'))) then
                    v_realiza := v_occ.id;
                    v_prev := v_occ.valor;
                    v_msgs := v_msgs || to_jsonb(format('Cobranca real da recorrencia "%s": confirma a previsao de R$ %s desta fatura (executado R$ %s%s).',
                        v_rec_nome, to_char(v_prev, 'FM999999990.00'), to_char(v_valor, 'FM999999990.00'),
                        case when v_valor <> v_prev then '; diferenca R$ ' || to_char(v_valor - v_prev, 'FM999999990.00') else '' end));
                else
                    v_conc := jsonb_build_object('lancamento_id', v_occ.id,
                                                 'descricao', coalesce(nullif(v_occ.descricao_exibida, ''), v_occ.descricao),
                                                 'data_compra', v_occ.data_compra, 'valor', v_occ.valor, 'categoria_id', v_occ.categoria_id,
                                                 'recorrente', true, 'mantida', false);
                    v_status := 'conciliado';
                    v_ignorar := true;
                    v_msgs := v_msgs || to_jsonb(format('Recorrencia ja lancada nesta fatura: %s (R$ %s); a compra existente fica como esta%s.',
                        v_conc ->> 'descricao', to_char((v_conc ->> 'valor')::numeric, 'FM999999990.00'),
                        case when (v_conc ->> 'valor')::numeric <> v_valor
                             then format(' (no arquivo, R$ %s: para corrigir, edite a compra)', to_char(v_valor, 'FM999999990.00'))
                             else '' end));
                    v_rec := null;
                end if;
            else
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

        v_saida := v_saida || jsonb_build_object(
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
            'mensagens', v_msgs, 'avisos', v_msgs);
    end loop;

    return jsonb_build_object(
        'cartao_id', p_cartao_id, 'competencia', to_char(v_comp, 'YYYY-MM'),
        'situacao_fatura', financeiro.situacao_fatura(financeiro.fatura_do_mes(p_cartao_id, v_comp)),
        'linhas', v_saida,
        'validacoes', (select jsonb_build_object(
            'total_linhas', count(*),
            'validas', count(*) filter (where l ->> 'status' = 'valido'),
            'revisar', count(*) filter (where l ->> 'status' = 'revisar'),
            'duplicadas', count(*) filter (where l ->> 'status' = 'duplicado'),
            'conciliadas', count(*) filter (where jsonb_typeof(l -> 'conciliacao') = 'object'),
            'realizacoes', count(*) filter (where l ->> 'realiza_lancamento_id' is not null and not (l ->> 'ignorar')::boolean),
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

-- importar_fatura_cartao: texto de 20261208090000.
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
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, p_cartao_id, v_meses[i]);
    end loop;

    select count(*) into v_dup from jsonb_array_elements(v_analise -> 'linhas') e
     where e ->> 'status' in ('duplicado', 'conciliado');
    v_res := jsonb_build_object(
        'inseridos', cardinality(v_ids), 'linhas_importadas', jsonb_array_length(v_a_gravar), 'duplicados', v_dup,
        'realizadas', v_realizadas,
        'lancamentos', to_jsonb(v_ids), 'faturas', to_jsonb(v_meses), 'cartao_id', p_cartao_id,
        'competencia', to_char(v_comp, 'YYYY-MM'));
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'importar_fatura', v_res);
    return v_res;
end
$$;

drop function financeiro.registrar_apelido_recorrencia(integer, integer, text);
drop function financeiro.conciliar_previsao_interna(integer, integer, integer);
