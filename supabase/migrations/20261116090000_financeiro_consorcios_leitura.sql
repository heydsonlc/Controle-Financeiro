-- FIN-FIDELIDADE-CONTRATOS-1 (Consorcios, fase 1) — leitura dos consorcios do Flask (GET /api/consorcios/ e /<id>),
-- mostrados na tela original de Recorrencias. So consulta.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261116090000).
-- Validada em cluster local descartavel (tests/test_supabase_consorcios_leitura.py, comparada com o Flask).
-- Docs: docs/FIN_FIDELIDADE_CONTRATOS_1.md.
--
-- Reproduz consorcio_to_dict (routes/consorcios.py): ContratoConsorcio.to_dict + meio de pagamento e categoria da primeira
-- parcela ("<nome> - Parcela%", tipo Consorcio, no perfil do contrato; sem perfil = perfil padrao, como
-- perfil_id_consorcio). Lista: so os ativos, como o Flask.
-- Nada e gravado: cadastro, edicao, exclusao e regeneracao de parcelas continuam no Flask (escritor unico).
-- Diferenca deliberada: o Flask, ao LER um contrato sem perfil, atribui o perfil padrao ao objeto em memoria
-- (perfil_id_consorcio); aqui a leitura nunca altera o contrato.
-- Nenhuma tabela nova. Nenhum dado existente e alterado.

-- perfil_id_consorcio sem efeito colateral: o do contrato ou o padrao (ativo, menor id; senao Pessoal; senao o 1o ativo).
create function financeiro.perfil_do_consorcio(p_c public.contrato_consorcio)
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce((p_c).perfil_financeiro_id,
                    (select p.id from public.perfil_financeiro p where p.padrao and p.ativo order by p.id limit 1),
                    (select p.id from public.perfil_financeiro p where p.nome = 'Pessoal' and p.ativo order by p.id limit 1),
                    (select p.id from public.perfil_financeiro p where p.ativo order by p.id limit 1))
$$;

-- consorcio_to_dict. Interna.
create function financeiro.consorcio_flask(p_c public.contrato_consorcio)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', (p_c).id, 'perfil_financeiro_id', (p_c).perfil_financeiro_id, 'nome', (p_c).nome,
        'valor_inicial', (p_c).valor_inicial, 'taxa_correcao', coalesce(nullif((p_c).taxa_correcao, 0), 0),
        'tipo_reajuste', (p_c).tipo_reajuste, 'valor_reajuste', coalesce(nullif((p_c).valor_reajuste, 0), 0),
        'numero_parcelas', (p_c).numero_parcelas, 'mes_inicio', (p_c).mes_inicio, 'mes_contemplacao', (p_c).mes_contemplacao,
        'valor_premio', nullif((p_c).valor_premio, 0), 'item_despesa_id', (p_c).item_despesa_id,
        'item_receita_id', (p_c).item_receita_id, 'ativo', (p_c).ativo, 'observacoes', (p_c).observacoes,
        'meio_pagamento', pr.meio_pagamento, 'cartao_id', pr.cartao_id, 'conta_bancaria_id', pr.conta_bancaria_id,
        'categoria_cartao_id', pr.categoria_cartao_id, 'categoria_id', pr.categoria_id,
        'categoria_nome', (select c.nome from public.categoria c where c.id = pr.categoria_id))
      from (select 1) x
      left join lateral (
          select i.* from public.item_despesa i
           where i.tipo = 'Consorcio'
             and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, financeiro.perfil_do_consorcio(p_c))
             and i.nome like (p_c).nome || ' - Parcela%'
           order by i.data_vencimento, i.id limit 1) pr on true
$$;

-- GET /api/consorcios/ (ativos) e /api/consorcios/<id> (p_id, ativo ou nao).
create function financeiro.consorcios_tela(p_perfil_id integer, p_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_c public.contrato_consorcio;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_id is not null then
        select * into v_c from public.contrato_consorcio c where c.id = p_id;
        if not found or not financeiro.pertence_ao_perfil(v_c.perfil_financeiro_id, p_perfil_id) then
            raise exception 'Consórcio não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
        end if;
        return financeiro.consorcio_flask(v_c);
    end if;
    return coalesce((select jsonb_agg(financeiro.consorcio_flask(c) order by c.id) from public.contrato_consorcio c
                      where c.ativo and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb);
end
$$;

revoke execute on function financeiro.perfil_do_consorcio(public.contrato_consorcio) from public, anon, authenticated;
revoke execute on function financeiro.consorcio_flask(public.contrato_consorcio) from public, anon, authenticated;
revoke execute on function financeiro.consorcios_tela(integer, integer) from public, anon;
grant execute on function financeiro.consorcios_tela(integer, integer) to authenticated;
