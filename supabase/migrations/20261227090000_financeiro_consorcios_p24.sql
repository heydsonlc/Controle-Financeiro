-- P24 (FIN-CONSORCIOS-INTEGRACAO-01, retificacao e adendo 02): consorcio em MOEDA, sem mudar a natureza, o modelo de
-- calculo (premio = parcela da posicao de contemplacao x numero de parcelas; reajuste por posicao) nem a geracao.
--
-- A. Contemplacao: a receita prevista (recebimento sem conta, marcador consorcio_id=N, gerada pelo contrato) aparecia em
--    Receitas, mas "Confirmar/realizar" era recusado (o Flask completava o proprio recebimento previsto: PUT
--    /realizadas/:id com a conta, que cria o credito). realizar_contemplacao_consorcio faz o mesmo: grava conta, data e
--    valor no recebimento previsto e cria o credito RECEITA, com a mesma auditoria do recebimento (operacao_receita).
-- B. Edicao de parcelas: editar_parcela_consorcio, como o Flask (valor e vencimento da parcela; "esta e as futuras" leva
--    o valor as seguintes do contrato), so em parcela pendente sem movimento; paga, com movimento ou historica fica.
-- C. Cadastro retroativo: criar_consorcio aceita parcelas_pagas_anteriores (N). O contrato e cadastrado inteiro (inicio
--    original, todas as parcelas, numeracao i/n, premio pela formula de sempre) e as N primeiras parcelas, anteriores
--    ao mes corrente, ficam pagas no historico SEM movimento bancario, registradas em financeiro.regularizacao_historica
--    (o mesmo mecanismo do FIN-REGULARIZACAO-HISTORICO-01; reversiveis por reverter_regularizacao_historica).
-- Nenhuma tabela ou coluna nova; nenhum dado existente muda nesta migration.

-- C1. Quantas parcelas foram pagas antes do cadastro (0 se nao informado). So parcelas de competencia anterior ao mes
--     corrente e menos que o total.
create function financeiro.consorcio_parcelas_anteriores(p_dados jsonb, p_total integer, p_inicio date)
    returns integer
    language plpgsql
    stable
    set search_path = ''
as $$
declare
    v_n     integer;
    v_texto text := btrim(coalesce(p_dados ->> 'parcelas_pagas_anteriores', ''));
begin
    if v_texto in ('', '0') then
        return 0;
    end if;
    if v_texto !~ '^\d{1,4}$' then
        raise exception 'Parcelas ja pagas antes do cadastro: informe um numero inteiro' using errcode = '22023';
    end if;
    v_n := v_texto::integer;
    if v_n >= p_total then
        raise exception 'Parcelas ja pagas antes do cadastro (%) devem ser menos que o total (%)', v_n, p_total using errcode = '22023';
    end if;
    if (p_inicio + make_interval(months => v_n - 1))::date >= date_trunc('month', financeiro.hoje_brasilia())::date then
        raise exception 'As % parcelas ja pagas precisam ser anteriores ao mes corrente: confira o mes de inicio do contrato', v_n
            using errcode = '22023', hint = 'PARCELAS_ANTERIORES';
    end if;
    return v_n;
end
$$;

-- C2. Registra as N primeiras parcelas como pagas no historico: status Pago, data de pagamento = vencimento, sem
--     movimento; uma linha por parcela em regularizacao_historica (lote proprio, estado anterior).
create function financeiro.registrar_parcelas_anteriores_consorcio(p_perfil_id integer, p_c public.contrato_consorcio,
                                                                   p_quantidade integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_lote  uuid := gen_random_uuid();
    v_conta public.conta;
    v_total numeric := 0;
    v_n     integer := 0;
begin
    if coalesce(p_quantidade, 0) = 0 then
        return null;
    end if;
    for v_conta in
        select c.* from public.conta c join public.item_despesa d on d.id = c.item_despesa_id
         where d.tipo = 'Consorcio' and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, financeiro.perfil_do_consorcio(p_c))
           and financeiro.posicao_parcela_consorcio(d.nome, array[p_c.nome]) between 1 and p_quantidade
         order by c.numero_parcela for update of c
    loop
        if v_conta.status_pagamento is distinct from 'Pendente' or v_conta.data_pagamento is not null
           or exists (select 1 from public.movimento_financeiro m where m.conta_id = v_conta.id or m.fatura_id = v_conta.id) then
            raise exception 'Parcela % do consorcio nao esta pendente: nada foi gravado', v_conta.numero_parcela using errcode = 'P0001';
        end if;
        insert into financeiro.regularizacao_historica (lote, perfil_financeiro_id, conta_id, tipo, competencia, descricao, valor,
                                                        data_pagamento, anterior, registrado_por)
        values (v_lote, p_perfil_id, v_conta.id, 'DESPESA', date_trunc('month', v_conta.mes_referencia::timestamp)::date,
                v_conta.descricao, v_conta.valor, v_conta.data_vencimento, to_jsonb(v_conta), (select auth.uid()));
        update public.conta set status_pagamento = 'Pago', data_pagamento = data_vencimento where id = v_conta.id;
        v_total := v_total + v_conta.valor;
        v_n := v_n + 1;
    end loop;
    if v_n <> p_quantidade then
        raise exception 'Parcelas anteriores esperadas %, encontradas %: nada foi gravado', p_quantidade, v_n using errcode = 'P0001';
    end if;
    return jsonb_build_object('lote', v_lote, 'quantidade', v_n, 'valor', v_total, 'sem_movimento', true);
end
$$;

-- A. Realizar a contemplacao: o recebimento previsto do contrato (sem conta) passa a recebido, com o credito.
create function financeiro.realizar_contemplacao_consorcio(p_perfil_id integer, p_receita_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_receita;
    v_rec       public.receita_realizada;
    v_banco     public.conta_bancaria;
    v_data      date;
    v_valor     numeric;
    v_previsto  numeric;
    v_just      text;
    v_mov       integer;
    v_saldo     numeric;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261227));
    select * into v_anterior from financeiro.operacao_receita o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'realizar_contemplacao_consorcio' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    select * into v_rec from public.receita_realizada r where r.id = p_receita_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_rec.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Receita nao encontrada neste perfil' using errcode = '42501';
    end if;
    if coalesce(v_rec.observacoes, '') !~ 'consorcio_id=[0-9]+' then
        raise exception 'Este recebimento nao e a contemplacao de um consorcio' using errcode = '22023', hint = 'NAO_E_CONTEMPLACAO';
    end if;
    if v_rec.conta_bancaria_id is not null
       or exists (select 1 from public.movimento_financeiro m where m.receita_realizada_id = v_rec.id) then
        raise exception 'Esta contemplacao ja foi realizada' using errcode = '22023', hint = 'JA_REALIZADA';
    end if;
    begin
        v_data := coalesce(nullif(p_dados ->> 'data_recebimento', '')::date, v_rec.data_recebimento);
        v_valor := coalesce(nullif(p_dados ->> 'valor_recebido', '')::numeric, v_rec.valor_recebido);
    exception when others then
        raise exception 'Dados do recebimento invalidos' using errcode = '22023';
    end;
    if v_valor is null or v_valor <= 0 or v_valor <> round(v_valor, 2) then
        raise exception 'Valor recebido deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
    end if;
    v_previsto := v_rec.valor_recebido;
    v_just := btrim(coalesce(p_dados ->> 'justificativa', ''));
    if v_valor <> v_previsto and (v_just = '' or length(v_just) > 500) then
        raise exception 'Valor diferente do previsto na contemplacao: a justificativa e obrigatoria (ate 500 caracteres)'
            using errcode = '22023', hint = 'JUSTIFICATIVA_OBRIGATORIA';
    end if;
    v_banco := financeiro.travar_conta_bancaria(p_perfil_id, (p_dados ->> 'conta_bancaria_id')::integer);
    update public.receita_realizada
       set conta_bancaria_id = v_banco.id, data_recebimento = v_data, valor_recebido = v_valor,
           observacoes = concat_ws(E'\n', nullif(observacoes, ''),
                                   case when v_valor <> v_previsto
                                        then '[VALOR DIFERENTE DO PREVISTO: ' || to_char(v_previsto, 'FM999999990.00') || '] ' || v_just end),
           atualizado_em = now() at time zone 'utc'
     where id = v_rec.id;
    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             receita_realizada_id, origem, ajustavel, criado_em)
    values (p_perfil_id, v_banco.id, 'CREDITO', v_valor, left('Receita - ' || coalesce(v_rec.descricao, 'Contemplacao de consorcio'), 200),
            v_data, v_rec.id, 'RECEITA', false, now() at time zone 'utc')
    returning id into v_mov;
    v_saldo := financeiro.atualizar_saldo_conta(v_banco.id);
    v_resultado := jsonb_build_object('receita_realizada_id', v_rec.id, 'movimento_id', v_mov, 'valor_previsto', v_previsto,
                                      'valor_recebido', v_valor, 'data_recebimento', v_data, 'conta_bancaria_id', v_banco.id,
                                      'conta_nome', v_banco.nome, 'saldo_conta', v_saldo);
    insert into financeiro.operacao_receita (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'realizar_contemplacao_consorcio', v_resultado);
    return v_resultado;
end
$$;

-- B. Editar parcela de consorcio (como o Flask): "unica" muda valor e vencimento desta parcela; "futuras" leva o valor a
--    esta e as seguintes do mesmo contrato. So parcela pendente sem movimento e fora do historico; as demais ficam.
create function financeiro.editar_parcela_consorcio(p_perfil_id integer, p_conta_id integer, p_versao text, p_dados jsonb,
                                                    p_escopo text)
    returns jsonb
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_conta   public.conta;
    v_item    public.item_despesa;
    v_c       public.contrato_consorcio;
    v_pos     integer;
    v_valor   numeric;
    v_venc    date;
    v_alvo    record;
    v_feitas  integer := 0;
    v_ficam   jsonb := '[]'::jsonb;
begin
    perform financeiro.exigir_escrita_consorcio(p_perfil_id);
    if coalesce(p_escopo, '') not in ('unica', 'futuras') then
        raise exception 'Escolha editar esta parcela ou esta e as futuras' using errcode = '22023';
    end if;
    select * into v_conta from public.conta where id = p_conta_id for update;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id;
    if v_conta.id is null or v_item.tipo is distinct from 'Consorcio'
       or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Parcela de consorcio nao encontrada neste perfil' using errcode = '42501';
    end if;
    select * into v_c from public.contrato_consorcio c
     where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
       and financeiro.posicao_parcela_consorcio(v_item.nome, array[c.nome]) is not null
     order by c.ativo desc, c.id desc limit 1 for update;
    if v_c.id is null then
        raise exception 'Contrato do consorcio nao encontrado' using errcode = 'P0001';
    end if;
    v_pos := financeiro.posicao_parcela_consorcio(v_item.nome, array[v_c.nome]);
    if p_versao is null or p_versao is distinct from financeiro.versao_despesa(p_conta_id) then
        raise exception 'A despesa foi alterada por outra operacao. Recarregue e tente de novo.' using errcode = 'P0001', hint = 'VERSAO';
    end if;
    if v_conta.status_pagamento is distinct from 'Pendente' or v_conta.data_pagamento is not null then
        raise exception 'Operacao bloqueada: %', 'Despesa paga: correcao so por estorno' using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    if exists (select 1 from public.movimento_financeiro m where m.conta_id = v_conta.id or m.fatura_id = v_conta.id) then
        raise exception 'Operacao bloqueada: %', 'Possui movimento financeiro vinculado' using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    begin
        v_valor := nullif(p_dados ->> 'valor', '')::numeric;
        v_venc := nullif(p_dados ->> 'data_vencimento', '')::date;
    exception when others then
        raise exception 'Dados da parcela invalidos' using errcode = '22023';
    end;
    if v_valor is null or v_valor <= 0 or v_valor <> round(v_valor, 2) then
        raise exception 'Informe um valor positivo, com ate 2 casas decimais' using errcode = '22023';
    end if;
    for v_alvo in
        select c.*, financeiro.posicao_parcela_consorcio(d.nome, array[v_c.nome]) pos, d.id item
          from public.conta c join public.item_despesa d on d.id = c.item_despesa_id
         where d.tipo = 'Consorcio' and financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
           and (c.id = v_conta.id or (p_escopo = 'futuras' and financeiro.posicao_parcela_consorcio(d.nome, array[v_c.nome]) > v_pos))
         order by financeiro.posicao_parcela_consorcio(d.nome, array[v_c.nome]) for update of c
    loop
        if v_alvo.status_pagamento is distinct from 'Pendente' or v_alvo.data_pagamento is not null
           or exists (select 1 from public.movimento_financeiro m where m.conta_id = v_alvo.id or m.fatura_id = v_alvo.id) then
            v_ficam := v_ficam || jsonb_build_object('conta_id', v_alvo.id, 'parcela', v_alvo.pos);
            continue;
        end if;
        update public.conta
           set valor = v_valor, data_vencimento = case when v_alvo.id = v_conta.id then coalesce(v_venc, data_vencimento) else data_vencimento end
         where id = v_alvo.id;
        update public.item_despesa
           set valor = v_valor, data_vencimento = case when v_alvo.id = v_conta.id then coalesce(v_venc, data_vencimento) else data_vencimento end
         where id = v_alvo.item;
        v_feitas := v_feitas + 1;
    end loop;
    return jsonb_build_object('conta_id', p_conta_id, 'contrato_id', v_c.id, 'escopo', p_escopo, 'atualizadas', v_feitas,
                              'preservadas', v_ficam, 'versao', financeiro.versao_despesa(p_conta_id));
end
$$;

-- Funcao existente (texto publicado; so as trocas da P24).

CREATE OR REPLACE FUNCTION financeiro.criar_consorcio(p_perfil_id integer, p_dados jsonb, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_repetida  jsonb;
    v_d         jsonb;
    v_c         public.contrato_consorcio;
    v_categoria integer;
    v_parcelas  jsonb;
    v_receita   boolean;
    v_resultado jsonb;
    v_campo     text;
    v_anteriores integer;  -- P24: parcelas pagas antes do cadastro
    v_historico jsonb;
begin
    perform financeiro.exigir_escrita_consorcio(p_perfil_id);
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'criar_consorcio');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do consorcio invalidos' using errcode = '22023';
    end if;
    foreach v_campo in array array['nome', 'valor_inicial', 'numero_parcelas', 'categoria_id'] loop
        if nullif(btrim(coalesce(p_dados ->> v_campo, '')), '') is null or (p_dados ->> v_campo) in ('0', 'false') then
            raise exception 'Campo % é obrigatório', v_campo using errcode = '22023';
        end if;
    end loop;
    v_categoria := (p_dados ->> 'categoria_id')::integer;
    if not exists (select 1 from public.categoria c where c.id = v_categoria) then
        raise exception 'Categoria não encontrada' using errcode = '22023';
    end if;
    perform financeiro.exigir_nome_consorcio_livre(p_perfil_id, btrim(p_dados ->> 'nome'), null);
    v_d := financeiro.consorcio_normalizar(p_dados, null);
    -- P24: contrato em andamento; as parcelas pagas antes do cadastro (pela posicao no contrato integral)
    v_anteriores := financeiro.consorcio_parcelas_anteriores(p_dados, (v_d ->> 'numero_parcelas')::integer,
                                                             (v_d ->> 'mes_inicio')::date);
    insert into public.contrato_consorcio (perfil_financeiro_id, nome, valor_inicial, tipo_reajuste, valor_reajuste, numero_parcelas,
                                           mes_inicio, mes_contemplacao, valor_premio, item_receita_id, observacoes, ativo, criado_em)
    values (p_perfil_id, btrim(p_dados ->> 'nome'), (v_d ->> 'valor_inicial')::numeric, v_d ->> 'tipo_reajuste',
            (v_d ->> 'valor_reajuste')::numeric, (v_d ->> 'numero_parcelas')::integer, (v_d ->> 'mes_inicio')::date,
            (v_d ->> 'mes_contemplacao')::date, (v_d ->> 'valor_premio')::numeric,
            nullif(p_dados ->> 'item_receita_id', '')::integer, nullif(p_dados ->> 'observacoes', ''), true, now() at time zone 'utc')
    returning * into v_c;
    v_parcelas := financeiro.sincronizar_parcelas_consorcio(v_c, v_categoria, financeiro.consorcio_pagamento(p_dados), '{}');
    v_receita := financeiro.sincronizar_receita_contemplacao(v_c);
    v_historico := financeiro.registrar_parcelas_anteriores_consorcio(p_perfil_id, v_c, v_anteriores);
    v_resultado := jsonb_build_object('data', financeiro.consorcio_flask(v_c), 'parcelas_geradas', (v_parcelas ->> 'criadas')::integer,
                                      'receita_gerada', v_receita, 'parcelas_anteriores', v_historico);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_consorcio', v_resultado);
    return v_resultado;
end
$function$;

revoke execute on function financeiro.consorcio_parcelas_anteriores(jsonb, integer, date) from public, anon, authenticated;
revoke execute on function financeiro.registrar_parcelas_anteriores_consorcio(integer, public.contrato_consorcio, integer) from public, anon, authenticated;
revoke execute on function financeiro.realizar_contemplacao_consorcio(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_parcela_consorcio(integer, integer, text, jsonb, text) from public, anon;
grant execute on function financeiro.realizar_contemplacao_consorcio(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_parcela_consorcio(integer, integer, text, jsonb, text) to authenticated;
