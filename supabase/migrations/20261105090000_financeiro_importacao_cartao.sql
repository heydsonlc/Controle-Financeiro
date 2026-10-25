-- FIN-FIDELIDADE-CARTOES-1 — Importar Cartao (tela original do Flask) sobre o Supabase.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261105090000).
-- Validada em cluster local descartavel (tests/test_supabase_importacao_cartao.py). Docs: docs/FIN_FIDELIDADE_CARTOES_1.md.
--
-- O arquivo e lido no navegador (nada do arquivo sai do aparelho); o banco recebe so as linhas ja lidas.
-- Nenhuma tabela nova, nenhuma coluna nova, nenhum dado existente alterado pela migration.
-- - analisar_importacao_cartao (so leitura): o pipeline do ImportacaoCartaoUnificadoService (validacao, sugestao de
--   categoria por palavra-chave e historico, Categoria do Cartao, duplicidade no lote e no banco) e, alem do Flask,
--   a conciliacao com compras ja lancadas no cartao (manual ou por recorrencia): a linha vem retirada da efetivacao,
--   com o lancamento encontrado, e so entra se o usuario mantiver explicitamente;
-- - importar_fatura_cartao: grava so com confirmacao do usuario, tudo ou nada (o Flask gravava as linhas boas e
--   listava erros), com idempotencia por chave, travas cartao -> faturas e a analise refeita sob a trava;
--   fatura paga nao recebe compra (vai para a proxima, competencia original registrada, como o Flask);
--   fatura consolidada recusa a importacao inteira (D6: nada entra sem confirmacao);
--   compra recorrente do cartao reconhecida pelo nome (reconhecer_despesa_fixa) entra com a identidade da
--   competencia (compra_id do gerador): o gerador a ve como EXISTENTE e nao gera de novo;
-- - sugerir_categorias_importacao e resolver_categoria_cartao_tela: leituras de apoio da tela.

-- Sugestao de Categoria de Despesa para uma descricao (CategoriaPalavraChaveService.classificar_por_palavras_chave e,
-- sem palavra-chave, o historico do perfil; sem historico, a categoria do cartao como "fallback", como o Flask). Interna.
create function financeiro.sugestao_categoria_importacao(p_perfil_id integer, p_classificacao text, p_normalizada text,
                                                         p_fallback integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_desc   text := btrim(coalesce(p_classificacao, ''));
    v_tokens text[] := regexp_split_to_array(btrim(coalesce(p_classificacao, '')), '\s+');
    v_cands  jsonb;
    v_n      integer;
    v_hist   integer;
begin
    if v_desc <> '' then
        select coalesce(jsonb_agg(jsonb_build_object('categoria_id', m.categoria_id, 'categoria_nome', m.nome,
                                                     'palavras_encontradas', m.palavras, 'score', m.score)
                                  order by m.score desc, m.categoria_id), '[]'::jsonb), count(*)
          into v_cands, v_n
          from (select pk.categoria_id, c.nome, to_jsonb(array_agg(lower(btrim(pk.palavra)) order by pk.id)) as palavras,
                       count(*) as score
                  from public.categoria_palavra_chave pk
                  join public.categoria c on c.id = pk.categoria_id and coalesce(c.ativo, true)
                 where pk.ativo and btrim(pk.palavra) <> ''
                   and case when position(' ' in btrim(pk.palavra)) > 0 then position(lower(btrim(pk.palavra)) in v_desc) > 0
                            else lower(btrim(pk.palavra)) = any(v_tokens) end
                 group by pk.categoria_id, c.nome) m;
        if v_n = 1 or (v_n > 1 and (v_cands -> 0 ->> 'score')::integer > (v_cands -> 1 ->> 'score')::integer) then
            return jsonb_build_object(
                'categoria_id', (v_cands -> 0 ->> 'categoria_id')::integer, 'origem', 'palavra_chave',
                'confianca', case when v_n = 1 or (v_cands -> 0 ->> 'score')::integer >= 2 then 'alta' else 'media' end,
                'ambigua', false, 'palavras_chave_encontradas', v_cands -> 0 -> 'palavras_encontradas',
                'categorias_candidatas', v_cands,
                'aviso', 'Categoria sugerida por palavra-chave. Palavras encontradas: '
                         || (select string_agg(p, ', ') from jsonb_array_elements_text(v_cands -> 0 -> 'palavras_encontradas') p) || '.');
        elsif v_n > 1 then
            return jsonb_build_object(
                'categoria_id', null, 'origem', 'ambigua', 'confianca', 'baixa', 'ambigua', true,
                'palavras_chave_encontradas', (select coalesce(jsonb_agg(distinct p), '[]'::jsonb)
                                                 from jsonb_array_elements(v_cands) c, jsonb_array_elements_text(c -> 'palavras_encontradas') p),
                'categorias_candidatas', v_cands,
                'aviso', 'Mais de uma categoria possivel. Revise antes de importar. Candidatas: '
                         || (select string_agg(c ->> 'categoria_nome', ', ') from (select c from jsonb_array_elements(v_cands) c limit 3) x) || '.');
        end if;
    end if;
    if btrim(coalesce(p_normalizada, '')) <> '' then
        select l.categoria_id into v_hist from public.lancamento_agregado l
         where lower(coalesce(l.descricao_original_normalizada, l.descricao)) = lower(btrim(p_normalizada))
           and l.categoria_id is not null and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
         order by l.id desc limit 1;
        if v_hist is not null then
            return jsonb_build_object('categoria_id', v_hist, 'origem', 'historico', 'confianca', 'alta', 'ambigua', false,
                                      'palavras_chave_encontradas', '[]'::jsonb, 'categorias_candidatas', '[]'::jsonb,
                                      'aviso', null);
        end if;
    end if;
    return jsonb_build_object('categoria_id', p_fallback, 'origem', case when p_fallback is null then 'sem_sugestao' else 'fallback' end,
                              'confianca', case when p_fallback is null then 'baixa' else 'media' end, 'ambigua', false,
                              'palavras_chave_encontradas', '[]'::jsonb, 'categorias_candidatas', '[]'::jsonb, 'aviso', null);
end
$$;

-- Analise da importacao (somente leitura). p_linhas: linhas lidas do arquivo, com as escolhas do usuario
-- (categoria_id, ignorar, manter_conciliada, gerar_parcelas_futuras). Devolve as linhas classificadas e as validacoes.
create function financeiro.analisar_importacao_cartao(p_perfil_id integer, p_cartao_id integer, p_competencia date,
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
                   and (abs(l.data_compra - v_data) <= 5 or coalesce(l.is_recorrente, false))
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

        -- Compra recorrente do cartao (reconhecer_despesa_fixa do Flask: nome igual, recorrente, no cartao).
        if v_status not in ('ignorado', 'duplicado', 'conciliado') and v_norm <> '' then
            select i.id into v_rec from public.item_despesa i
             where coalesce(i.recorrente, false) and coalesce(i.ativo, true) and i.tipo <> 'Agregador'
               and i.meio_pagamento = 'cartao' and i.cartao_id = p_cartao_id
               and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
               and lower(i.nome) = lower(v_norm)
             order by i.id limit 1;
            if v_rec is not null then
                v_msgs := v_msgs || '"Reconhecida como compra recorrente do cartao: o gerador nao a lanca de novo nesta competencia."'::jsonb;
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
            else
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
            'sem_categoria_cartao', count(*) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and l ->> 'status' not in ('duplicado', 'ignorado', 'conciliado')
                                                       and l ->> 'categoria_cartao_id' is null),
            'total_importavel', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and not (l ->> 'ignorar')::boolean), 0),
            'creditos', count(*) filter (where l ->> 'tipo_movimento' = 'credito'),
            'total_creditos', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'credito'), 0),
            'ignorados', count(*) filter (where l ->> 'status' = 'ignorado'))
            from jsonb_array_elements(v_saida) l));
end
$$;

-- Gravacao confirmada da importacao. Tudo ou nada; mesma chave = mesmo resultado (repetida).
create function financeiro.importar_fatura_cartao(p_perfil_id integer, p_cartao_id integer, p_competencia date,
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

-- Sugestoes por descricao (POST /api/importacao-cartao/sugerir-categorias).
create function financeiro.sugerir_categorias_importacao(p_perfil_id integer, p_descricoes jsonb)
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
    if p_descricoes is null or jsonb_typeof(p_descricoes) <> 'array' or jsonb_array_length(p_descricoes) > 2000 then
        raise exception 'descricoes deve ser uma lista' using errcode = '22023';
    end if;
    -- Cada item: {descricao, classificacao, normalizada}
    return coalesce((select jsonb_object_agg(d ->> 'descricao',
                            financeiro.sugestao_categoria_importacao(p_perfil_id, d ->> 'classificacao', d ->> 'normalizada', null))
                       from jsonb_array_elements(p_descricoes) d
                      where jsonb_typeof(d) = 'object' and d ->> 'descricao' is not null), '{}'::jsonb);
end
$$;

-- Categoria do Cartao de uma Categoria de Despesa neste cartao (GET /api/categorias-cartao/resolver).
create function financeiro.resolver_categoria_cartao_tela(p_perfil_id integer, p_cartao_id integer, p_categoria_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_cc  integer;
    v_res integer;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    v_cc := financeiro.resolver_categoria_cartao(p_perfil_id, p_cartao_id, p_categoria_id);
    if v_cc is null then
        select v.categoria_cartao_id into v_res
          from public.categoria_cartao_despesa v join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
         where v.categoria_id = p_categoria_id and v.ativo and cc.ativo
           and financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)
         order by v.id limit 1;
    end if;
    return jsonb_build_object(
        'categoria_cartao_id', v_cc, 'categoria_cartao_resolvida_id', v_res,
        'categoria_cartao_nome', (select cc.nome from public.categoria_cartao cc where cc.id = coalesce(v_cc, v_res)),
        'origem', case when v_cc is not null then 'mapa_categoria_despesa'
                       when v_res is not null then 'categoria_cartao_nao_vinculada' end,
        'vinculada_ao_cartao', v_cc is not null);
end
$$;

revoke execute on function financeiro.sugestao_categoria_importacao(integer, text, text, integer) from public, anon, authenticated;
revoke execute on function financeiro.analisar_importacao_cartao(integer, integer, date, jsonb) from public, anon;
revoke execute on function financeiro.importar_fatura_cartao(integer, integer, date, jsonb, uuid) from public, anon;
revoke execute on function financeiro.sugerir_categorias_importacao(integer, jsonb) from public, anon;
revoke execute on function financeiro.resolver_categoria_cartao_tela(integer, integer, integer) from public, anon;
grant execute on function financeiro.analisar_importacao_cartao(integer, integer, date, jsonb) to authenticated;
grant execute on function financeiro.importar_fatura_cartao(integer, integer, date, jsonb, uuid) to authenticated;
grant execute on function financeiro.sugerir_categorias_importacao(integer, jsonb) to authenticated;
grant execute on function financeiro.resolver_categoria_cartao_tela(integer, integer, integer) to authenticated;
