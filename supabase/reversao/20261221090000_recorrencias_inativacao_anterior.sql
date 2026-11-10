-- Reversao de 20261221090000 (FIN-RECORRENCIAS-INATIVACAO-01, P22): volta inativar_recorrencia, reativar_recorrencia,
-- definir_situacao_recorrencia_cartao e excluir_despesa aos corpos publicados antes dela (texto lido da producao em
-- 09/11/2026, na 20261220090000) e remove as funcoes novas. Nenhuma tabela muda: as competencias DISPENSADAS gravadas
-- pela interrupcao ou pela retomada continuam validas no modelo anterior (o gerador nao as recria). So com autorizacao,
-- retirando a versao de supabase_migrations.schema_migrations. Finais de linha CRLF, como a copia de trabalho deste
-- repositorio: em producao, inativar/reativar_recorrencia e definir_situacao_recorrencia_cartao tem corpo com CRLF (vieram
-- de arquivos assim); excluir_despesa, sem CR, volta igual a menos dos finais de linha.

CREATE OR REPLACE FUNCTION financeiro.inativar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.travar_recorrencia(p_perfil_id, p_item_id, p_versao);
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    update public.item_despesa set ativo = false where id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'ativo', false);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.reativar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.travar_recorrencia(p_perfil_id, p_item_id, p_versao);
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- nao muda no meio de uma geracao
    update public.item_despesa set ativo = true where id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'ativo', true, 'versao', financeiro.versao_recorrencia(p_item_id));
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.definir_situacao_recorrencia_cartao(p_perfil_id integer, p_item_id integer, p_versao text, p_ativo boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_item public.item_despesa;
begin
    v_item := financeiro.travar_recorrencia_cartao(p_perfil_id, p_item_id, p_versao);
    if p_ativo is null then
        raise exception 'Situacao invalida' using errcode = '22023';
    end if;
    if p_ativo then
        perform financeiro.cartao_do_perfil(p_perfil_id, v_item.cartao_id, true);  -- cartao inativo nao recebe compra nova
    end if;
    update public.item_despesa set ativo = p_ativo where id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'ativo', p_ativo, 'versao', financeiro.versao_recorrencia(p_item_id));
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.excluir_despesa(p_perfil_id integer, p_conta_id integer, p_versao text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_conta        public.conta;
    v_item         public.item_despesa;
    v_item_apagado boolean := false;
    v_ocorrencia   date;  -- FIN-CATEGORIAS-RECORRENCIAS-2
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
    perform financeiro.travar_despesa(p_perfil_id, p_conta_id, p_versao);
    select * into v_conta from public.conta where id = p_conta_id;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id;

    if coalesce(v_item.recorrente, false) then
        if financeiro.gerador_do_perfil(p_perfil_id) <> 'NOVO' then
            raise exception 'Conta recorrente gerada pelo sistema atual: o Flask a recriaria. Exclua pelo sistema atual.'
                using errcode = 'P0001', hint = 'GERADOR_FLASK';
        end if;
        perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao
        if financeiro.semanas_da_recorrencia(v_item.tipo_recorrencia) is not null then
            -- FIN-CATEGORIAS-RECORRENCIAS-2: na semanal, dispensa so a ocorrencia desta conta (a gravada na geracao ou a do ciclo).
            v_ocorrencia := coalesce(
                (select o.data_ocorrencia from financeiro.recorrencia_ocorrencia o
                  where o.item_despesa_id = v_item.id and o.conta_id = p_conta_id),
                financeiro.ocorrencia_semanal(v_item.tipo_recorrencia, v_item.data_vencimento, v_conta.data_vencimento));
            if v_ocorrencia is not null then
                insert into financeiro.recorrencia_ocorrencia (item_despesa_id, data_ocorrencia, situacao, motivo, user_id)
                values (v_item.id, v_ocorrencia, 'DISPENSADA', 'Conta excluida pelo usuario', (select auth.uid()))
                on conflict (item_despesa_id, data_ocorrencia) do update
                   set situacao = 'DISPENSADA', conta_id = null, execucao_id = null,
                       motivo = excluded.motivo, user_id = excluded.user_id, registrado_em = now();
            end if;
        else
        insert into financeiro.recorrencia_competencia
            (item_despesa_id, natureza, competencia, situacao, motivo, user_id)
        values (v_item.id, 'CONTA', date_trunc('month', v_conta.mes_referencia::timestamp)::date, 'DISPENSADA',
                'Conta excluida pelo usuario', (select auth.uid()))
        on conflict (item_despesa_id, natureza, competencia) do update
           set situacao = 'DISPENSADA', conta_id = null, lancamento_id = null, execucao_id = null,
               motivo = excluded.motivo, user_id = excluded.user_id, registrado_em = now();
        end if;
        delete from public.conta where id = p_conta_id;
    else
        delete from public.conta where id = p_conta_id;
        -- Item avulso sem outra referencia sai junto (o Flask o deixava orfao).
        if not exists (select 1 from public.conta c where c.item_despesa_id = v_item.id) then
            begin
                delete from public.item_despesa where id = v_item.id;
                v_item_apagado := true;
            exception when foreign_key_violation then
                v_item_apagado := false;
            end;
        end if;
    end if;
    return jsonb_build_object('conta_id', p_conta_id, 'item_excluido', v_item_apagado,
                              'competencia_dispensada', coalesce(v_item.recorrente, false));
end
$function$;

drop function financeiro.retomar_recorrencia(integer, integer, text, date, boolean);
drop function financeiro.previa_retomada_recorrencia(integer, integer, date);
drop function financeiro.lacunas_da_recorrencia(integer, date);
drop function financeiro.exigir_recorrencia_fora_do_cartao(integer, integer);
drop function financeiro.interromper_recorrencia(integer, integer, text, date, integer, integer);
drop function financeiro.previa_interrupcao_recorrencia(integer, integer, date, integer);
drop function financeiro.ocorrencias_interrupcao(integer, date, integer);
drop function financeiro.motivo_sem_interrupcao(integer, public.item_despesa);
drop function financeiro.efeito_interrupcao(date);
drop function financeiro.dispensar_conta_recorrente(public.item_despesa, public.conta, text);
