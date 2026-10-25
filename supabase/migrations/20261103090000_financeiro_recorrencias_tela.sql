-- FIN-FIDELIDADE-RECORRENCIAS-1 — o que a tela original de Recorrencias do Flask precisa e o Supabase nao tinha.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica. Validada em cluster PostgreSQL local descartavel
-- (tests/test_supabase_recorrencias_tela.py). Sem tabela nova; nenhum dado existente e alterado pela migration.
--
-- Reaproveita as regras ja centralizadas (FIN-DESPESAS-1): travar_recorrencia (gestao do perfil, recorrencia do
-- perfil, tipo Simples, fora de outro modulo, versao contra edicao concorrente) e a trava de geracao (20261023).
-- - recorrencias_do_perfil: a listagem do GET /api/recorrencias do Flask (so leitura), com o proximo vencimento
--   calculado aqui (no Flask era a rota). Mesmo recorte do Flask: item recorrente do perfil (NULL -> Pessoal), menos
--   consorcio. Recorrencia de cartao ou de outro modulo aparece, marcada como nao gerenciavel por esta tela;
-- - reativar_recorrencia: o "ativo" do PUT do Flask (inativar ja existia). Reativada, a recorrencia volta a ser
--   oferecida pela previa, com confirmacao: nada e gerado aqui;
-- - definir_meio_pagamento_recorrencia: boleto, PIX ou debito, so informativos (o gerador so trata de forma
--   diferente cartao e debito automatico, que continuam pelos seus caminhos). Nao aceita cartao nem debito automatico.

create function financeiro.recorrencias_do_perfil(p_perfil_id integer)
    returns table (id integer, nome text, descricao text, valor numeric, categoria_id integer, categoria_nome text,
                   categoria_cor text, tipo_recorrencia text, data_vencimento date, proximo_vencimento date,
                   meio_pagamento text, cartao_id integer, cartao_nome text, conta_bancaria_id integer,
                   conta_bancaria_nome text, ativo boolean, gerenciavel boolean, versao text)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_pessoal boolean;
    v_hoje date := (now() at time zone 'America/Sao_Paulo')::date;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');
    return query
        select i.id, i.nome::text, i.descricao::text, i.valor, i.categoria_id, cat.nome::text, cat.cor::text,
               coalesce(i.tipo_recorrencia, 'mensal')::text, i.data_vencimento,
               -- Mesmo calculo do Flask (_proximo_vencimento) para mensal e anual, sem deslizar o dia contratual
               -- (soma a partir da data original, como o gerador). Outras frequencias: so a data se ainda vier.
               case
                   when i.data_vencimento is null then null
                   when i.data_vencimento >= v_hoje then i.data_vencimento
                   when coalesce(i.tipo_recorrencia, 'mensal') in ('mensal', 'anual') then (
                       select min(d)::date
                         from generate_series(0, 1200) k,
                              lateral (select case when coalesce(i.tipo_recorrencia, 'mensal') = 'anual'
                                                   then i.data_vencimento + make_interval(years => k)
                                                   else i.data_vencimento + make_interval(months => k) end as d) x
                        where x.d >= v_hoje)
               end,
               i.meio_pagamento::text, i.cartao_id, cartao.nome::text, i.conta_bancaria_id, cb.nome::text,
               coalesce(i.ativo, true),
               i.tipo = 'Simples' and i.origem_tipo is null and coalesce(i.meio_pagamento, '') <> 'cartao',
               financeiro.versao_recorrencia(i.id)
          from public.item_despesa i
          left join public.categoria cat on cat.id = i.categoria_id
          left join public.item_despesa cartao on cartao.id = i.cartao_id
          left join public.conta_bancaria cb on cb.id = i.conta_bancaria_id
         where (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))
           and coalesce(i.recorrente, false)
           and i.tipo is distinct from 'Consorcio'
           and i.tipo is distinct from 'Agregador'
         order by i.nome, i.id;
end
$$;

create function financeiro.reativar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.travar_recorrencia(p_perfil_id, p_item_id, p_versao);
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- nao muda no meio de uma geracao
    update public.item_despesa set ativo = true where id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'ativo', true, 'versao', financeiro.versao_recorrencia(p_item_id));
end
$$;

create function financeiro.definir_meio_pagamento_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text,
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

revoke execute on function financeiro.recorrencias_do_perfil(integer) from public, anon;
revoke execute on function financeiro.reativar_recorrencia(integer, integer, text) from public, anon;
revoke execute on function financeiro.definir_meio_pagamento_recorrencia(integer, integer, text, text) from public, anon;
grant execute on function financeiro.recorrencias_do_perfil(integer) to authenticated;
grant execute on function financeiro.reativar_recorrencia(integer, integer, text) to authenticated;
grant execute on function financeiro.definir_meio_pagamento_recorrencia(integer, integer, text, text) to authenticated;
