-- FIN-DESPESAS-PAGAMENTO-LOTE-02 (P21): o pagamento em lote confere a identidade do lote que a tela mostrou e o usuario
-- confirmou. A tela abria o modal de outra recorrencia (Diarista abria Psicologa: a posicao do botao era procurada numa
-- lista com outra ordem); o banco aceitava, porque as ocorrencias enviadas eram todas as pendentes de uma recorrencia,
-- so que da outra. Agora o pedido traz o que o modal mostrou (nome, competencia, recorrencias, quantidade e total) e o
-- banco recusa (LOTE_IDENTIDADE) se as ocorrencias nao forem exatamente esse lote. Pedido sem identidade (tela antiga)
-- tambem e recusado. So a funcao muda (mesma assinatura e permissoes); nenhuma tabela, coluna ou valor.

create or replace function financeiro.pagar_despesas_lote(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_despesa;
    v_itens     jsonb;
    v_banco     integer;
    v_data      date;
    v_ids       integer[];
    v_achadas   integer;
    v_recs      integer[];
    v_comps     date[];
    v_pendentes integer[];
    v_item      jsonb;
    v_conta     public.conta;
    v_r         jsonb;
    v_pagas     jsonb := '[]'::jsonb;
    v_total     numeric := 0;
    v_estado    text;
    v_msg       text;
    v_hint      text;
    v_resultado jsonb;
    v_ident     jsonb;
    v_ident_recs integer[];
    v_soma      numeric;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- quem gere o perfil e perfil no novo aplicativo (escritor unico)
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261101));
    select * into v_anterior from financeiro.operacao_despesa o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'pagar_despesas_lote' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;

    -- Dados: as ocorrencias com o valor que a tela mostrou, a conta e a data
    v_itens := case when jsonb_typeof(p_dados -> 'itens') = 'array' then p_dados -> 'itens' end;
    if v_itens is null or jsonb_array_length(v_itens) = 0 then
        raise exception 'Nenhuma ocorrência pendente para pagar' using errcode = '22023';
    end if;
    if jsonb_array_length(v_itens) > 60 then
        raise exception 'Lote com mais de 60 ocorrências' using errcode = '22023';
    end if;
    if exists (select 1 from jsonb_array_elements(v_itens) e
                where jsonb_typeof(e) <> 'object' or coalesce(e ->> 'conta_id', '') !~ '^\d+$'
                   or coalesce(e ->> 'valor_devido', '') !~ '^\d+(\.\d{1,2})?$') then
        raise exception 'Dados do lote inválidos' using errcode = '22023';
    end if;
    v_ids := array(select distinct (e ->> 'conta_id')::integer from jsonb_array_elements(v_itens) e order by 1);
    if cardinality(v_ids) <> jsonb_array_length(v_itens) then
        raise exception 'Ocorrência repetida no lote' using errcode = '22023';
    end if;
    -- Identidade do lote que o modal mostrou (P21): obrigatoria
    v_ident := p_dados -> 'lote';
    if jsonb_typeof(v_ident) is distinct from 'object' or btrim(coalesce(v_ident ->> 'descricao', '')) = ''
       or coalesce(v_ident ->> 'competencia', '') !~ '^\d{4}-(0[1-9]|1[0-2])$'
       or jsonb_typeof(v_ident -> 'recorrencias') is distinct from 'array' or (v_ident -> 'recorrencias') = '[]'::jsonb
       or exists (select 1 from jsonb_array_elements(case when jsonb_typeof(v_ident -> 'recorrencias') = 'array'
                                                          then v_ident -> 'recorrencias' else '[]'::jsonb end) e
                   where jsonb_typeof(e) <> 'number' or e::text !~ '^\d{1,9}$')
       or coalesce(v_ident ->> 'quantidade', '') !~ '^\d{1,9}$' or coalesce(v_ident ->> 'valor_total', '') !~ '^\d+(\.\d{1,2})?$' then
        raise exception 'O pedido não identifica o lote mostrado na tela. Atualize a página e abra o lote de novo. Nada foi pago.'
            using errcode = '22023', hint = 'LOTE_IDENTIDADE';
    end if;
    begin
        v_data := (p_dados ->> 'data_pagamento')::date;
    exception when others then
        v_data := null;
    end;
    if v_data is null then
        raise exception 'Informe a data do pagamento' using errcode = '22023';
    end if;
    if coalesce(p_dados ->> 'conta_bancaria_id', '') !~ '^\d+$' then
        raise exception 'Selecione a conta bancária de débito' using errcode = '22023', hint = 'CONTA_OBRIGATORIA';
    end if;
    v_banco := (p_dados ->> 'conta_bancaria_id')::integer;
    -- a conta e conferida antes de qualquer pagamento (ativa e do perfil)
    perform financeiro.travar_conta_bancaria(p_perfil_id, v_banco);

    -- O lote que a tela mostrou tem de ser o de agora: mesmas recorrencias e competencia, mesmas ocorrencias pendentes
    select count(*), array_agg(distinct c.item_despesa_id), array_agg(distinct date_trunc('month', c.mes_referencia)::date)
      into v_achadas, v_recs, v_comps
      from public.conta c
     where c.id = any(v_ids) and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
       and not coalesce(c.is_fatura_cartao, false) and c.item_despesa_id is not null;
    if v_achadas <> cardinality(v_ids) then
        raise exception 'Ocorrência não encontrada neste perfil' using errcode = '42501';
    end if;
    if cardinality(v_comps) <> 1 then
        raise exception 'O pagamento em lote é de uma competência por vez' using errcode = '22023';
    end if;
    -- As ocorrencias tem de ser exatamente o lote mostrado: mesma recorrencia (nome e itens), competencia, quantidade e total
    v_ident_recs := array(select distinct e::text::integer from jsonb_array_elements(v_ident -> 'recorrencias') e order by 1);
    v_soma := (select sum((e ->> 'valor_devido')::numeric) from jsonb_array_elements(v_itens) e);
    if v_ident_recs is distinct from array(select x from unnest(v_recs) x order by 1)
       or (v_ident ->> 'competencia' || '-01')::date <> v_comps[1]
       or (v_ident ->> 'quantidade')::integer <> cardinality(v_ids)
       or (v_ident ->> 'valor_total')::numeric <> v_soma
       or exists (select 1 from public.conta c where c.id = any(v_ids)
                   and btrim(regexp_replace(c.descricao, '\s*-\s*\d{2}/\d{2}$', '')) <> btrim(v_ident ->> 'descricao')) then
        raise exception 'As ocorrências enviadas não são as do lote mostrado (%, %). Nada foi pago.',
            btrim(v_ident ->> 'descricao'), to_char((v_ident ->> 'competencia' || '-01')::date, 'MM/YYYY')
            using errcode = '22023', hint = 'LOTE_IDENTIDADE';
    end if;
    v_pendentes := array(select c.id from public.conta c
                          where c.item_despesa_id = any(v_recs) and date_trunc('month', c.mes_referencia)::date = v_comps[1]
                            and not coalesce(c.is_fatura_cartao, false)
                            and c.status_pagamento is distinct from 'Pago' and c.status_pagamento is distinct from 'Substituida'
                            and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                          order by c.id);
    if v_pendentes is distinct from v_ids then
        raise exception 'As ocorrências pendentes mudaram desde a abertura (agora são %). Confira de novo. Nada foi pago.',
            cardinality(v_pendentes) using errcode = '22023', hint = 'LOTE_DESATUALIZADO';
    end if;

    -- Cada ocorrencia pelo pagamento individual, com a mesma conta; qualquer recusa desfaz o lote inteiro
    for v_item in select e from jsonb_array_elements(v_itens) e order by (e ->> 'conta_id')::integer loop
        select * into v_conta from public.conta c where c.id = (v_item ->> 'conta_id')::integer;
        begin
            v_r := financeiro.pagar_despesa(p_perfil_id, v_conta.id,
                jsonb_build_object('conta_bancaria_id', v_banco, 'data_pagamento', v_data,
                                   'valor_pago', v_item ->> 'valor_devido', 'valor_devido', v_item ->> 'valor_devido'),
                extensions.uuid_generate_v5(p_chave, v_conta.id::text));
        exception when others then
            get stacked diagnostics v_estado = returned_sqlstate, v_msg = message_text, v_hint = pg_exception_hint;
            raise exception 'Nenhuma ocorrência foi paga. "%" (vencimento %): %', v_conta.descricao,
                to_char(v_conta.data_vencimento, 'DD/MM/YYYY'), v_msg
                using errcode = v_estado, hint = coalesce(nullif(v_hint, ''), 'LOTE_RECUSADO');
        end;
        v_pagas := v_pagas || jsonb_build_object('conta_id', v_conta.id, 'descricao', v_conta.descricao,
                                                 'data_vencimento', v_conta.data_vencimento, 'valor_pago', (v_r ->> 'valor_pago')::numeric,
                                                 'movimento_id', (v_r ->> 'movimento_id')::integer);
        v_total := v_total + (v_r ->> 'valor_pago')::numeric;
    end loop;

    v_resultado := jsonb_build_object('pagas', jsonb_array_length(v_pagas), 'valor_total', v_total, 'data_pagamento', v_data,
                                      'conta_bancaria_id', v_banco, 'conta_nome', v_r ->> 'conta_nome',
                                      'saldo_conta', (v_r ->> 'saldo_conta')::numeric, 'ocorrencias', v_pagas);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'pagar_despesas_lote', v_resultado);
    return v_resultado;
end
$$;

revoke execute on function financeiro.pagar_despesas_lote(integer, jsonb, uuid) from public, anon;
grant execute on function financeiro.pagar_despesas_lote(integer, jsonb, uuid) to authenticated;
