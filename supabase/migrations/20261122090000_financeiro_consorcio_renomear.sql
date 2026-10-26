-- FIN-CONTRATOS-3 — renomear o consorcio tambem renomeia a descricao das despesas pendentes (a lista de Despesas mostra
-- a descricao da despesa; antes ela so acompanhava na proxima regeneracao). Despesa paga ou com movimento guarda a
-- descricao original (historico).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261122090000).
-- Validada em cluster local descartavel (tests/test_supabase_consorcios_escrita.py). Docs: docs/FIN_CONTRATOS_3.md.
-- Substitui so financeiro.editar_consorcio: o texto de 20261121090000 com as linhas marcadas (mesma assinatura e
-- privilegios). Reversao: supabase/reversao/20261122090000_editar_consorcio_anterior.sql. Nenhuma tabela nem dado.

create or replace function financeiro.editar_consorcio(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_c        public.contrato_consorcio;
    v_anterior text;
    v_d        jsonb;
    v_pag      jsonb;
    v_perfil   integer;
    v_receita  boolean;
begin
    perform financeiro.exigir_escrita_consorcio(p_perfil_id);
    v_c := financeiro.travar_consorcio(p_perfil_id, p_id);
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do consorcio invalidos' using errcode = '22023';
    end if;
    v_anterior := v_c.nome;
    v_perfil := financeiro.perfil_do_consorcio(v_c);
    if p_dados ? 'nome' and btrim(coalesce(p_dados ->> 'nome', '')) <> '' and btrim(p_dados ->> 'nome') <> v_c.nome then
        perform financeiro.exigir_nome_consorcio_livre(p_perfil_id, btrim(p_dados ->> 'nome'), v_c.id);
        update public.item_despesa d
           set nome = btrim(p_dados ->> 'nome') || substr(d.nome, length(v_anterior) + 1)
         where d.tipo = 'Consorcio' and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
           and financeiro.posicao_parcela_consorcio(d.nome, array[v_anterior]) is not null;
        update public.contrato_consorcio set nome = btrim(p_dados ->> 'nome') where id = v_c.id;
        -- FIN-CONTRATOS-3: a descricao das despesas pendentes (sem movimento) acompanha; as efetivadas guardam o historico.
        update public.conta c
           set descricao = btrim(p_dados ->> 'nome') || substr(c.descricao, length(v_anterior) + 1)
          from public.item_despesa d
         where c.item_despesa_id = d.id and d.tipo = 'Consorcio'
           and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
           and financeiro.posicao_parcela_consorcio(d.nome, array[btrim(p_dados ->> 'nome')]) is not null
           and left(c.descricao, length(v_anterior) + 11) = v_anterior || ' - Parcela '
           and not financeiro.despesa_efetivada(c.id);
    end if;
    if p_dados ? 'observacoes' then
        update public.contrato_consorcio set observacoes = p_dados ->> 'observacoes' where id = v_c.id;
    end if;
    if p_dados ?| array['valor_inicial', 'numero_parcelas', 'mes_inicio', 'mes_contemplacao', 'tipo_reajuste', 'valor_reajuste'] then
        v_d := financeiro.consorcio_normalizar(p_dados, v_c);
        update public.contrato_consorcio
           set valor_inicial = (v_d ->> 'valor_inicial')::numeric, tipo_reajuste = v_d ->> 'tipo_reajuste',
               valor_reajuste = (v_d ->> 'valor_reajuste')::numeric, numero_parcelas = (v_d ->> 'numero_parcelas')::integer,
               mes_inicio = (v_d ->> 'mes_inicio')::date, mes_contemplacao = (v_d ->> 'mes_contemplacao')::date,
               valor_premio = (v_d ->> 'valor_premio')::numeric
         where id = v_c.id;
    end if;
    if p_dados ? 'ativo' and jsonb_typeof(p_dados -> 'ativo') = 'boolean' then
        update public.contrato_consorcio set ativo = (p_dados ->> 'ativo')::boolean where id = v_c.id;
    end if;
    select * into v_c from public.contrato_consorcio where id = v_c.id;
    if p_dados ?| array['meio_pagamento', 'cartao_id', 'conta_bancaria_id', 'categoria_cartao_id'] then
        v_pag := financeiro.consorcio_pagamento(p_dados);
        update public.item_despesa d
           set meio_pagamento = v_pag ->> 'meio_pagamento', cartao_id = (v_pag ->> 'cartao_id')::integer,
               categoria_cartao_id = (v_pag ->> 'categoria_cartao_id')::integer,
               conta_bancaria_id = (v_pag ->> 'conta_bancaria_id')::integer
         where d.tipo = 'Consorcio' and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
           and financeiro.posicao_parcela_consorcio(d.nome, array[v_c.nome]) is not null;
        update public.conta c
           set debito_automatico = coalesce(v_pag ->> 'meio_pagamento', '') = 'debito_automatico',
               conta_bancaria_id = (v_pag ->> 'conta_bancaria_id')::integer
          from public.item_despesa d
         where c.item_despesa_id = d.id and d.tipo = 'Consorcio'
           and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, v_perfil)
           and financeiro.posicao_parcela_consorcio(d.nome, array[v_c.nome]) is not null
           and not financeiro.despesa_efetivada(c.id);
    end if;
    v_receita := financeiro.sincronizar_receita_contemplacao(v_c);
    return jsonb_build_object('data', financeiro.consorcio_flask(v_c), 'receita_gerada', v_receita);
end
$$;
