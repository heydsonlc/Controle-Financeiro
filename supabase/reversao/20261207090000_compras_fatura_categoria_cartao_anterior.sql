-- Reversao de 20261207090000 (Categoria do Cartao em compras_da_fatura): devolve a funcao ao texto de 20261028090000,
-- sem a coluna categoria_cartao_id. Nenhum dado e alterado (a funcao so le). Com a reversao, o detalhe da fatura em
-- Despesas volta a receber a Categoria do Cartao nula.
-- So com autorizacao, retirando a versao de supabase_migrations.schema_migrations.

drop function financeiro.compras_da_fatura(integer, integer, date);

create function financeiro.compras_da_fatura(p_perfil_id integer, p_cartao_id integer, p_mes date)
    returns table (id integer, descricao text, valor numeric, data_compra date, numero_parcela integer,
                   total_parcelas integer, categoria_nome text, recorrente boolean, bloqueio text, pode_editar boolean)
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
               financeiro.bloqueio_da_parcela(l.id), v_gerir and financeiro.bloqueio_da_parcela(l.id) is null
          from public.lancamento_agregado l
          left join public.categoria cat on cat.id = l.categoria_id
         where l.cartao_id = p_cartao_id and l.mes_fatura = date_trunc('month', p_mes::timestamp)::date
           and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         order by l.data_compra, l.id;
end
$$;

revoke execute on function financeiro.compras_da_fatura(integer, integer, date) from public, anon;
grant execute on function financeiro.compras_da_fatura(integer, integer, date) to authenticated;
