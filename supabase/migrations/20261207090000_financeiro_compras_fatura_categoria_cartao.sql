-- FIN-CARTAO-AGRUPAMENTO-CATEGORIAS-01 — compras_da_fatura devolve a Categoria do Cartao gravada na compra.
--
-- Defeito: o detalhe da fatura em Despesas (organizarLancamentosEmBlocos, js/original/despesas.js) agrupa as compras
-- pela categoria_cartao_id, mas compras_da_fatura (20261028090000) nao a devolvia e o adaptador a mandava nula; com o
-- resumo por categoria tambem vazio, toda compra nao parcelada e nao fixa caia em "Outros Lancamentos" (caso real:
-- fatura 11/2026 do Master Card Black, R$ 7.194,80 inteiros em Outros, com 51 compras ja classificadas no importador).
--
-- Correcao so de leitura: a funcao passa a devolver lancamento_agregado.categoria_cartao_id (coluna nova, no fim).
-- Nenhum dado e alterado; o que ja foi classificado volta a agrupar. A mudanca do tipo de retorno exige recriar a
-- funcao (mesmo texto de 20261028090000 + a coluna) e repetir as permissoes.
-- Reversao: supabase/reversao/20261207090000_compras_fatura_categoria_cartao_anterior.sql.

drop function financeiro.compras_da_fatura(integer, integer, date);

create function financeiro.compras_da_fatura(p_perfil_id integer, p_cartao_id integer, p_mes date)
    returns table (id integer, descricao text, valor numeric, data_compra date, numero_parcela integer,
                   total_parcelas integer, categoria_nome text, recorrente boolean, bloqueio text, pode_editar boolean,
                   categoria_cartao_id integer)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_pessoal boolean;
    v_gerir   boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    return query
        select l.id, coalesce(nullif(l.descricao_exibida, ''), l.descricao)::text, l.valor, l.data_compra,
               l.numero_parcela, l.total_parcelas, cat.nome::text, coalesce(l.is_recorrente, false),
               financeiro.bloqueio_da_parcela(l.id), v_gerir and financeiro.bloqueio_da_parcela(l.id) is null,
               l.categoria_cartao_id
          from public.lancamento_agregado l
          left join public.categoria cat on cat.id = l.categoria_id
         where l.cartao_id = p_cartao_id and l.mes_fatura = date_trunc('month', p_mes::timestamp)::date
           and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         order by l.data_compra, l.id;
end
$$;

revoke execute on function financeiro.compras_da_fatura(integer, integer, date) from public, anon;
grant execute on function financeiro.compras_da_fatura(integer, integer, date) to authenticated;
