-- FIN-FIDELIDADE-MOVIMENTACOES-1 — telas originais de Contas Bancarias e Lancamentos do Flask sobre o Supabase.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261109090000).
-- Validada em cluster local descartavel (tests/test_supabase_contas_bancarias.py).
-- Docs: docs/FIN_FIDELIDADE_MOVIMENTACOES_1.md.
--
-- Regras do Flask (routes/contas_bancarias.py, services/conta_bancaria_service.py), nas mesmas tabelas:
-- - saldo = saldo_inicial + creditos - debitos (financeiro.saldo_da_conta); saldo_atual e o cache recalculado
--   (financeiro.atualizar_saldo_conta) depois de cada movimento;
-- - saldo inicial so muda sem movimentos; depois disso, "Ajustar saldo" cria um movimento AJUSTE (ajustavel);
-- - so o AJUSTE e editavel ou excluivel; os demais movimentos (DESPESA, RECEITA, FATURA, TRANSFERENCIA, estornos,
--   FINANCIAMENTO) ficam como estao;
-- - transferencia = DEBITO na origem + CREDITO no destino, mesmo transferencia_id, origem TRANSFERENCIA (nao e
--   receita nem despesa), as duas contas do perfil e ativas, travadas em ordem de id;
-- - conferencia de saldo: so leitura.
-- Correcoes em relacao ao Flask (classificadas em docs):
-- - movimento (ajuste e transferencia) so pelo escritor unico do perfil (financeiro.exigir_pagamento_novo) e com chave de
--   idempotencia (o reenvio nao duplica); o Flask nao tem chave;
-- - edicao do cadastro com versao (cadastro alterado por outra operacao e recusado, nada e gravado);
-- - excluir ajuste estornado (referenciado por movimento_original_id) e recusado;
-- - valores com ate 2 casas, data valida, descricao ate 200 caracteres (o Flask grava o que vier).
-- Nenhuma tabela nova; nenhum dado existente e alterado.

-- 1. Internas ------------------------------------------------------------------------------------------------------

-- Versao do cadastro (sem saldo_atual nem data_atualizacao, que mudam a cada movimento).
create function financeiro.versao_conta_bancaria(p_conta public.conta_bancaria)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select md5(concat_ws('|', p_conta.nome, p_conta.instituicao, p_conta.tipo, p_conta.agencia, p_conta.numero_conta,
                         p_conta.digito_conta, p_conta.saldo_inicial::text, p_conta.cor_display, p_conta.icone,
                         p_conta.status))
$$;

-- Conta bancaria no formato do Flask (ContaBancaria.to_dict) + versao do cadastro.
create function financeiro.conta_bancaria_flask(p_conta public.conta_bancaria)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_conta.id, 'perfil_financeiro_id', p_conta.perfil_financeiro_id, 'nome', p_conta.nome,
        'instituicao', p_conta.instituicao, 'tipo', p_conta.tipo, 'agencia', p_conta.agencia,
        'numero_conta', p_conta.numero_conta, 'digito_conta', p_conta.digito_conta,
        'saldo_inicial', coalesce(p_conta.saldo_inicial, 0), 'saldo_atual', coalesce(p_conta.saldo_atual, 0),
        'cor_display', p_conta.cor_display, 'icone', p_conta.icone,
        'data_criacao', to_char(p_conta.data_criacao, 'YYYY-MM-DD HH24:MI:SS'),
        'data_atualizacao', to_char(p_conta.data_atualizacao, 'YYYY-MM-DD HH24:MI:SS'),
        'status', p_conta.status,
        'versao', financeiro.versao_conta_bancaria(p_conta))
$$;

-- Movimento no formato do Flask (MovimentoFinanceiro.to_dict).
create function financeiro.movimento_flask(p_mov public.movimento_financeiro)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_mov.id, 'perfil_financeiro_id', p_mov.perfil_financeiro_id, 'conta_bancaria_id', p_mov.conta_bancaria_id,
        'tipo', p_mov.tipo, 'valor', p_mov.valor, 'descricao', p_mov.descricao, 'data_movimento', p_mov.data_movimento,
        'fatura_id', p_mov.fatura_id, 'conta_id', p_mov.conta_id, 'receita_realizada_id', p_mov.receita_realizada_id,
        'transferencia_id', p_mov.transferencia_id, 'financiamento_parcela_id', p_mov.financiamento_parcela_id,
        'movimento_original_id', p_mov.movimento_original_id, 'origem', coalesce(p_mov.origem, 'MANUAL'),
        'ajustavel', coalesce(p_mov.ajustavel, false),
        'criado_em', to_char(p_mov.criado_em, 'YYYY-MM-DD HH24:MI:SS'))
$$;

-- Conta do perfil travada, ativa ou nao (o Flask ajusta e edita contas inativas). Interna.
create function financeiro.travar_conta_do_perfil(p_perfil_id integer, p_conta_bancaria_id integer)
    returns public.conta_bancaria
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta_bancaria;
begin
    select * into v_conta from public.conta_bancaria cb where cb.id = p_conta_bancaria_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Conta bancaria nao encontrada neste perfil' using errcode = '22023';
    end if;
    return v_conta;
end
$$;

-- Dados do cadastro (criacao: todos; edicao: so os enviados). Normaliza e valida como o Flask, com limites das colunas.
create function financeiro.ler_dados_conta_bancaria(p_dados jsonb, p_parcial boolean)
    returns jsonb
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_saida jsonb := '{}'::jsonb;
    v_campo text;
    v_valor text;
    v_saldo numeric;
    v_limites constant jsonb := '{"nome": 100, "instituicao": 100, "tipo": 50, "agencia": 20, "numero_conta": 50,
                                  "digito_conta": 10, "icone": 50}';
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da conta invalidos' using errcode = '22023';
    end if;
    foreach v_campo in array array['nome', 'instituicao', 'tipo'] loop
        if not p_parcial or p_dados ? v_campo then
            v_valor := btrim(coalesce(p_dados ->> v_campo, ''));
            if v_valor = '' then
                raise exception '% e obrigatori%', case v_campo when 'nome' then 'Nome' when 'tipo' then 'Tipo'
                                                     else 'Instituicao' end,
                                                case v_campo when 'instituicao' then 'a' else 'o' end
                    using errcode = '22023';
            end if;
            if length(v_valor) > (v_limites ->> v_campo)::integer then
                raise exception 'Campo % com mais de % caracteres', v_campo, v_limites ->> v_campo using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object(v_campo, v_valor);
        end if;
    end loop;
    foreach v_campo in array array['agencia', 'numero_conta', 'digito_conta', 'icone'] loop
        if p_dados ? v_campo then
            v_valor := nullif(btrim(coalesce(p_dados ->> v_campo, '')), '');
            if length(v_valor) > (v_limites ->> v_campo)::integer then
                raise exception 'Campo % com mais de % caracteres', v_campo, v_limites ->> v_campo using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object(v_campo, v_valor);
        elsif not p_parcial then
            v_saida := v_saida || jsonb_build_object(v_campo, null);
        end if;
    end loop;
    if p_dados ? 'cor_display' or not p_parcial then
        v_valor := coalesce(nullif(btrim(coalesce(p_dados ->> 'cor_display', '')), ''), '#3b82f6');
        if v_valor !~ '^#[0-9a-fA-F]{6}$' then
            raise exception 'Cor invalida (use #RRGGBB)' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('cor_display', v_valor);
    end if;
    if p_dados ? 'saldo_inicial' or not p_parcial then
        begin
            v_saldo := coalesce(nullif(p_dados ->> 'saldo_inicial', '')::numeric, 0);
        exception when invalid_text_representation or numeric_value_out_of_range then
            raise exception 'saldo_inicial invalido' using errcode = '22023';
        end;
        if v_saldo <> round(v_saldo, 2) or abs(v_saldo) >= 1e13 then
            raise exception 'saldo_inicial invalido' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('saldo_inicial', v_saldo);
    end if;
    if p_dados ? 'status' then
        v_valor := upper(btrim(coalesce(p_dados ->> 'status', '')));
        if v_valor not in ('ATIVO', 'INATIVO') then
            raise exception 'status deve ser ATIVO ou INATIVO' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('status', v_valor);
    end if;
    return v_saida;
end
$$;

-- Valor de movimento: positivo, ate 2 casas (como movimento_financeiro numeric(15,2)).
create function financeiro.ler_valor_movimento(p_valor text, p_rotulo text)
    returns numeric
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v numeric;
begin
    begin
        v := nullif(btrim(coalesce(p_valor, '')), '')::numeric;
    exception when invalid_text_representation or numeric_value_out_of_range then
        raise exception '% invalido', p_rotulo using errcode = '22023';
    end;
    if v is null then
        raise exception '% invalido', p_rotulo using errcode = '22023';
    end if;
    if v <> round(v, 2) or abs(v) >= 1e13 then
        raise exception '% deve ter ate 2 casas decimais', p_rotulo using errcode = '22023';
    end if;
    return v;
end
$$;

-- Data do movimento: vazia = hoje (Brasilia; o Flask usa a data UTC); formato YYYY-MM-DD.
create function financeiro.ler_data_movimento(p_data text)
    returns date
    language plpgsql
    stable
    set search_path = ''
as $$
begin
    if nullif(btrim(coalesce(p_data, '')), '') is null then
        return (now() at time zone 'America/Sao_Paulo')::date;
    end if;
    if left(btrim(p_data), 10) !~ '^\d{4}-\d{2}-\d{2}$' then
        raise exception 'Formato de data invalido. Use YYYY-MM-DD' using errcode = '22023';
    end if;
    return left(btrim(p_data), 10)::date;
exception when datetime_field_overflow or invalid_datetime_format then
    raise exception 'Formato de data invalido. Use YYYY-MM-DD' using errcode = '22023';
end
$$;

-- Chave de idempotencia: devolve o resultado anterior (repetida) ou null. Mesma tabela das despesas.
create function financeiro.operacao_repetida(p_perfil_id integer, p_chave uuid, p_operacao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_despesa;
begin
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261109));
    select * into v_anterior from financeiro.operacao_despesa o where o.chave = p_chave;
    if not found then
        return null;
    end if;
    if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
       or v_anterior.operacao <> p_operacao then
        raise exception 'Chave da operacao ja usada' using errcode = '22023';
    end if;
    return v_anterior.resultado || jsonb_build_object('repetida', true);
end
$$;

-- 2. Leitura -------------------------------------------------------------------------------------------------------

-- GET /api/contas?status=: ativas por padrao (como o Flask), ordem por nome.
create function financeiro.contas_bancarias_tela(p_perfil_id integer, p_status text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_status text := upper(coalesce(nullif(btrim(p_status), ''), 'ATIVO'));
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if v_status not in ('ATIVO', 'INATIVO') then
        raise exception 'status deve ser ATIVO ou INATIVO' using errcode = '22023';
    end if;
    return coalesce((select jsonb_agg(financeiro.conta_bancaria_flask(cb) order by cb.nome, cb.id)
                       from public.conta_bancaria cb
                      where financeiro.pertence_ao_perfil(cb.perfil_financeiro_id, p_perfil_id)
                        and cb.status = v_status), '[]'::jsonb);
end
$$;

-- GET /api/contas/<id>
create function financeiro.conta_bancaria_tela(p_perfil_id integer, p_conta_bancaria_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta_bancaria;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_conta from public.conta_bancaria cb where cb.id = p_conta_bancaria_id;
    if not found or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Conta nao encontrada neste perfil' using errcode = '22023';
    end if;
    return financeiro.conta_bancaria_flask(v_conta);
end
$$;

-- GET /api/contas/<id>/movimentos: extrato do mais recente ao mais antigo (limite 1..1000, padrao 200) e, com
-- p_incluir_saldo, saldo depois de cada movimento (saldo inicial + movimentos anteriores ao inicio + os do periodo).
create function financeiro.extrato_conta_bancaria(p_perfil_id integer, p_conta_bancaria_id integer, p_inicio date,
                                                  p_fim date, p_limite integer, p_incluir_saldo boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_conta  public.conta_bancaria;
    v_limite integer := coalesce(p_limite, 200);
    v_base   numeric;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_conta from public.conta_bancaria cb where cb.id = p_conta_bancaria_id;
    if not found or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Conta nao encontrada neste perfil' using errcode = '22023';
    end if;
    if v_limite <= 0 then
        raise exception 'limit deve ser um inteiro maior que zero' using errcode = '22023';
    end if;
    v_limite := least(v_limite, 1000);
    if p_inicio is not null and p_fim is not null and p_inicio > p_fim then
        raise exception 'inicio nao pode ser maior que fim' using errcode = '22023';
    end if;
    v_base := coalesce(v_conta.saldo_inicial, 0)
              + coalesce((select sum(case when m.tipo = 'CREDITO' then m.valor when m.tipo = 'DEBITO' then -m.valor else 0 end)
                            from public.movimento_financeiro m
                           where m.conta_bancaria_id = v_conta.id and p_inicio is not null
                             and m.data_movimento < p_inicio), 0);
    return coalesce((
        select jsonb_agg(x.dado order by x.data_movimento desc, x.id desc)
          from (select p.id, p.data_movimento,
                       financeiro.movimento_flask(p.m)
                       || jsonb_build_object('saldo_apos_movimento', case when coalesce(p_incluir_saldo, true) then p.saldo end)
                       as dado
                  from (select m.id, m.data_movimento, m,
                               v_base + sum(case when m.tipo = 'CREDITO' then m.valor when m.tipo = 'DEBITO' then -m.valor else 0 end)
                                        over (order by m.data_movimento, m.id) as saldo
                          from public.movimento_financeiro m
                         where m.conta_bancaria_id = v_conta.id
                           and (p_inicio is null or m.data_movimento >= p_inicio)
                           and (p_fim is null or m.data_movimento <= p_fim)) p
                 order by p.data_movimento desc, p.id desc
                 limit v_limite) x), '[]'::jsonb);
end
$$;

-- GET /api/contas/<id>/conferir-saldo (so leitura: nao altera saldo nem cria movimento).
create function financeiro.conferir_saldo_conta(p_perfil_id integer, p_conta_bancaria_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta_bancaria;
    v_cred  numeric;
    v_deb   numeric;
    v_qtd   integer;
    v_calc  numeric;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_conta from public.conta_bancaria cb where cb.id = p_conta_bancaria_id;
    if not found or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Conta bancaria nao encontrada neste perfil' using errcode = '22023';
    end if;
    select coalesce(sum(m.valor) filter (where m.tipo = 'CREDITO'), 0), coalesce(sum(m.valor) filter (where m.tipo = 'DEBITO'), 0),
           count(*)
      into v_cred, v_deb, v_qtd
      from public.movimento_financeiro m where m.conta_bancaria_id = v_conta.id;
    v_calc := coalesce(v_conta.saldo_inicial, 0) + v_cred - v_deb;
    return jsonb_build_object('conta_id', v_conta.id, 'saldo_inicial', coalesce(v_conta.saldo_inicial, 0),
                              'total_creditos', v_cred, 'total_debitos', v_deb, 'saldo_calculado', v_calc,
                              'saldo_atual', coalesce(v_conta.saldo_atual, 0),
                              'divergencia', coalesce(v_conta.saldo_atual, 0) - v_calc,
                              'quantidade_movimentos', v_qtd,
                              'consistente', coalesce(v_conta.saldo_atual, 0) = v_calc);
end
$$;

-- 3. Cadastro ------------------------------------------------------------------------------------------------------

-- POST /api/contas: conta ATIVA do perfil; saldo_atual = saldo inicial (sem movimentos). Chave: o reenvio nao duplica.
create function financeiro.criar_conta_bancaria(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida  jsonb;
    v_d         jsonb;
    v_conta     public.conta_bancaria;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'criar_conta_bancaria');
    if v_repetida is not null then
        return v_repetida;
    end if;
    v_d := financeiro.ler_dados_conta_bancaria(p_dados, false);
    insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, agencia, numero_conta, digito_conta,
                                       saldo_inicial, saldo_atual, cor_display, icone, status, data_criacao, data_atualizacao)
    values (p_perfil_id, v_d ->> 'nome', v_d ->> 'instituicao', v_d ->> 'tipo', v_d ->> 'agencia', v_d ->> 'numero_conta',
            v_d ->> 'digito_conta', (v_d ->> 'saldo_inicial')::numeric, (v_d ->> 'saldo_inicial')::numeric,
            v_d ->> 'cor_display', v_d ->> 'icone', 'ATIVO', now() at time zone 'utc', now() at time zone 'utc')
    returning * into v_conta;
    v_resultado := financeiro.conta_bancaria_flask(v_conta);
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_conta_bancaria', v_resultado);
    return v_resultado;
end
$$;

-- PUT /api/contas/<id> (e ativar / inativar): so os campos enviados; saldo inicial so sem movimentos (depois, ajuste).
create function financeiro.editar_conta_bancaria(p_perfil_id integer, p_conta_bancaria_id integer, p_versao text,
                                                 p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta_bancaria;
    v_d     jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_d := financeiro.ler_dados_conta_bancaria(p_dados, true);
    v_conta := financeiro.travar_conta_do_perfil(p_perfil_id, p_conta_bancaria_id);
    if p_versao is not null and p_versao is distinct from financeiro.versao_conta_bancaria(v_conta) then
        raise exception 'Conta bancaria alterada por outra operacao' using errcode = '40001';
    end if;
    if v_d ? 'saldo_inicial' and (v_d ->> 'saldo_inicial')::numeric is distinct from coalesce(v_conta.saldo_inicial, 0)
       and exists (select 1 from public.movimento_financeiro m where m.conta_bancaria_id = v_conta.id) then
        raise exception 'Nao e permitido alterar saldo inicial apos existirem movimentos. Use "Ajustar Saldo".'
            using errcode = '22023', hint = 'SALDO_INICIAL_COM_MOVIMENTOS';
    end if;
    update public.conta_bancaria cb set
        nome = coalesce(v_d ->> 'nome', cb.nome),
        instituicao = coalesce(v_d ->> 'instituicao', cb.instituicao),
        tipo = coalesce(v_d ->> 'tipo', cb.tipo),
        agencia = case when v_d ? 'agencia' then v_d ->> 'agencia' else cb.agencia end,
        numero_conta = case when v_d ? 'numero_conta' then v_d ->> 'numero_conta' else cb.numero_conta end,
        digito_conta = case when v_d ? 'digito_conta' then v_d ->> 'digito_conta' else cb.digito_conta end,
        icone = case when v_d ? 'icone' then v_d ->> 'icone' else cb.icone end,
        cor_display = coalesce(v_d ->> 'cor_display', cb.cor_display),
        status = coalesce(v_d ->> 'status', cb.status),
        saldo_inicial = coalesce((v_d ->> 'saldo_inicial')::numeric, cb.saldo_inicial),
        data_atualizacao = now() at time zone 'utc'
     where cb.id = v_conta.id;
    perform financeiro.atualizar_saldo_conta(v_conta.id);
    select * into v_conta from public.conta_bancaria cb where cb.id = v_conta.id;
    return financeiro.conta_bancaria_flask(v_conta);
end
$$;

-- 4. Movimentos (escritor unico do perfil) -----------------------------------------------------------------------

-- POST /api/contas/<id>/ajuste-saldo: AJUSTE (ajustavel) pela diferenca para o saldo desejado, ou pelo valor do ajuste
-- (com sinal). Diferenca zero: nada e gravado ("Saldo ja esta no valor desejado").
create function financeiro.ajustar_saldo_conta(p_perfil_id integer, p_conta_bancaria_id integer, p_dados jsonb,
                                               p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida  jsonb;
    v_conta     public.conta_bancaria;
    v_data      date;
    v_desc      text;
    v_delta     numeric;
    v_mov       public.movimento_financeiro;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'ajustar_saldo_conta');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do ajuste invalidos' using errcode = '22023';
    end if;
    v_data := financeiro.ler_data_movimento(p_dados ->> 'data_movimento');
    v_desc := left(coalesce(nullif(btrim(coalesce(p_dados ->> 'descricao', '')), ''), 'Ajuste manual de saldo'), 200);
    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    v_conta := financeiro.travar_conta_do_perfil(p_perfil_id, p_conta_bancaria_id);
    if p_dados -> 'valor_final_desejado' is not null and jsonb_typeof(p_dados -> 'valor_final_desejado') <> 'null' then
        v_delta := financeiro.ler_valor_movimento(p_dados ->> 'valor_final_desejado', 'valor_final_desejado')
                   - financeiro.saldo_da_conta(v_conta.id);
    elsif p_dados -> 'valor_do_ajuste' is not null and jsonb_typeof(p_dados -> 'valor_do_ajuste') <> 'null' then
        v_delta := financeiro.ler_valor_movimento(p_dados ->> 'valor_do_ajuste', 'valor_do_ajuste');
    else
        raise exception 'Informe valor_final_desejado ou valor_do_ajuste' using errcode = '22023';
    end if;
    if v_delta = 0 then
        perform financeiro.atualizar_saldo_conta(v_conta.id);
        select * into v_conta from public.conta_bancaria cb where cb.id = v_conta.id;
        v_resultado := jsonb_build_object('sem_alteracao', true, 'conta', financeiro.conta_bancaria_flask(v_conta));
    else
        insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao,
                                                 data_movimento, origem, ajustavel, criado_em)
        values (p_perfil_id, v_conta.id, case when v_delta > 0 then 'CREDITO' else 'DEBITO' end, abs(v_delta), v_desc,
                v_data, 'AJUSTE', true, now() at time zone 'utc')
        returning * into v_mov;
        perform financeiro.atualizar_saldo_conta(v_conta.id);
        select * into v_conta from public.conta_bancaria cb where cb.id = v_conta.id;
        v_resultado := jsonb_build_object('sem_alteracao', false, 'conta', financeiro.conta_bancaria_flask(v_conta),
                                          'movimento', financeiro.movimento_flask(v_mov));
    end if;
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'ajustar_saldo_conta', v_resultado);
    return v_resultado;
end
$$;

-- Ajuste do perfil e da conta, travado (conta -> movimento). So AJUSTE (ajustavel). Interna.
create function financeiro.travar_ajuste(p_perfil_id integer, p_conta_bancaria_id integer, p_movimento_id integer)
    returns public.movimento_financeiro
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_mov public.movimento_financeiro;
begin
    perform financeiro.travar_conta_do_perfil(p_perfil_id, p_conta_bancaria_id);
    select * into v_mov from public.movimento_financeiro m where m.id = p_movimento_id for update;
    if not found or v_mov.conta_bancaria_id is distinct from p_conta_bancaria_id then
        raise exception 'Movimento nao encontrado neste perfil' using errcode = '22023';
    end if;
    if not coalesce(v_mov.ajustavel, false) then
        raise exception 'Apenas movimentos de AJUSTE podem ser alterados' using errcode = '22023', hint = 'NAO_AJUSTAVEL';
    end if;
    return v_mov;
end
$$;

-- PUT /api/contas/<id>/movimentos/<mov>: tipo, valor, descricao e data de um AJUSTE.
create function financeiro.editar_ajuste_conta(p_perfil_id integer, p_conta_bancaria_id integer, p_movimento_id integer,
                                               p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_mov   public.movimento_financeiro;
    v_tipo  text;
    v_valor numeric;
    v_data  date;
    v_desc  text;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do ajuste invalidos' using errcode = '22023';
    end if;
    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    v_mov := financeiro.travar_ajuste(p_perfil_id, p_conta_bancaria_id, p_movimento_id);
    v_tipo := coalesce(nullif(p_dados ->> 'tipo', ''), v_mov.tipo);
    if v_tipo not in ('CREDITO', 'DEBITO') then
        raise exception 'tipo deve ser CREDITO ou DEBITO' using errcode = '22023';
    end if;
    v_valor := v_mov.valor;
    if p_dados ->> 'valor' is not null then
        v_valor := financeiro.ler_valor_movimento(p_dados ->> 'valor', 'valor');
        if v_valor <= 0 then
            raise exception 'valor deve ser maior que zero' using errcode = '22023';
        end if;
    end if;
    v_data := case when p_dados ->> 'data_movimento' is null then v_mov.data_movimento
                   else financeiro.ler_data_movimento(p_dados ->> 'data_movimento') end;
    v_desc := coalesce(left(nullif(btrim(coalesce(p_dados ->> 'descricao', '')), ''), 200), v_mov.descricao);
    update public.movimento_financeiro set tipo = v_tipo, valor = v_valor, data_movimento = v_data, descricao = v_desc
     where id = v_mov.id
    returning * into v_mov;
    perform financeiro.atualizar_saldo_conta(p_conta_bancaria_id);
    return financeiro.movimento_flask(v_mov);
end
$$;

-- DELETE /api/contas/<id>/movimentos/<mov>: exclui um AJUSTE (como o Flask), salvo se outro movimento o referencia.
create function financeiro.excluir_ajuste_conta(p_perfil_id integer, p_conta_bancaria_id integer, p_movimento_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_mov public.movimento_financeiro;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    v_mov := financeiro.travar_ajuste(p_perfil_id, p_conta_bancaria_id, p_movimento_id);
    if exists (select 1 from public.movimento_financeiro e where e.movimento_original_id = v_mov.id) then
        raise exception 'Operacao bloqueada: Possui movimento financeiro vinculado' using errcode = '22023', hint = 'BLOQUEADA';
    end if;
    delete from public.movimento_financeiro where id = v_mov.id;
    return jsonb_build_object('movimento_id', v_mov.id, 'saldo', financeiro.atualizar_saldo_conta(p_conta_bancaria_id));
end
$$;

-- POST /api/contas/transferir: DEBITO na origem + CREDITO no destino (mesmo transferencia_id), na mesma transacao.
create function financeiro.transferir_entre_contas(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_repetida  jsonb;
    v_origem_id integer;
    v_dest_id   integer;
    v_valor     numeric;
    v_data      date;
    v_desc      text;
    v_conta     public.conta_bancaria;
    v_id        text := gen_random_uuid()::text;
    v_debito    public.movimento_financeiro;
    v_credito   public.movimento_financeiro;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_repetida := financeiro.operacao_repetida(p_perfil_id, p_chave, 'transferir_entre_contas');
    if v_repetida is not null then
        return v_repetida;
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' or nullif(p_dados ->> 'conta_origem_id', '') is null
       or nullif(p_dados ->> 'conta_destino_id', '') is null or p_dados ->> 'valor' is null then
        raise exception 'conta_origem_id, conta_destino_id e valor sao obrigatorios' using errcode = '22023';
    end if;
    begin
        v_origem_id := (p_dados ->> 'conta_origem_id')::integer;
        v_dest_id := (p_dados ->> 'conta_destino_id')::integer;
    exception when invalid_text_representation or numeric_value_out_of_range then
        raise exception 'Parametros invalidos para transferencia' using errcode = '22023';
    end;
    v_valor := financeiro.ler_valor_movimento(p_dados ->> 'valor', 'valor');
    if v_valor <= 0 then
        raise exception 'valor deve ser maior que zero' using errcode = '22023';
    end if;
    if v_origem_id = v_dest_id then
        raise exception 'Conta de origem e destino devem ser diferentes' using errcode = '22023';
    end if;
    v_data := financeiro.ler_data_movimento(p_dados ->> 'data_movimento');
    v_desc := left(coalesce(nullif(btrim(coalesce(p_dados ->> 'descricao', '')), ''), 'Transferência'), 200);

    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    -- As duas contas, em ordem de id (sem deadlock com outra transferencia no sentido contrario).
    for v_conta in select * from public.conta_bancaria cb where cb.id in (v_origem_id, v_dest_id) order by cb.id for update loop
        if not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
            raise exception 'Conta bancaria nao encontrada neste perfil' using errcode = '22023';
        end if;
        if v_conta.status is distinct from 'ATIVO' then
            raise exception 'Conta bancaria inativa' using errcode = '22023';
        end if;
    end loop;
    if (select count(*) from public.conta_bancaria cb where cb.id in (v_origem_id, v_dest_id)) <> 2 then
        raise exception 'Conta bancaria nao encontrada neste perfil' using errcode = '22023';
    end if;

    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             transferencia_id, origem, ajustavel, criado_em)
    values (p_perfil_id, v_origem_id, 'DEBITO', v_valor, v_desc, v_data, v_id, 'TRANSFERENCIA', false, now() at time zone 'utc')
    returning * into v_debito;
    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             transferencia_id, origem, ajustavel, criado_em)
    values (p_perfil_id, v_dest_id, 'CREDITO', v_valor, v_desc, v_data, v_id, 'TRANSFERENCIA', false, now() at time zone 'utc')
    returning * into v_credito;
    v_resultado := jsonb_build_object('transferencia_id', v_id, 'debito', financeiro.movimento_flask(v_debito),
                                      'credito', financeiro.movimento_flask(v_credito),
                                      'saldo_origem', financeiro.atualizar_saldo_conta(v_origem_id),
                                      'saldo_destino', financeiro.atualizar_saldo_conta(v_dest_id));
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'transferir_entre_contas', v_resultado);
    return v_resultado;
end
$$;

-- 5. Privilegios ---------------------------------------------------------------------------------------------------

revoke execute on function financeiro.conta_bancaria_flask(public.conta_bancaria) from public, anon, authenticated;
revoke execute on function financeiro.versao_conta_bancaria(public.conta_bancaria) from public, anon, authenticated;
revoke execute on function financeiro.movimento_flask(public.movimento_financeiro) from public, anon, authenticated;
revoke execute on function financeiro.travar_conta_do_perfil(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.ler_dados_conta_bancaria(jsonb, boolean) from public, anon, authenticated;
revoke execute on function financeiro.ler_valor_movimento(text, text) from public, anon, authenticated;
revoke execute on function financeiro.ler_data_movimento(text) from public, anon, authenticated;
revoke execute on function financeiro.operacao_repetida(integer, uuid, text) from public, anon, authenticated;
revoke execute on function financeiro.travar_ajuste(integer, integer, integer) from public, anon, authenticated;

revoke execute on function financeiro.contas_bancarias_tela(integer, text) from public, anon;
revoke execute on function financeiro.conta_bancaria_tela(integer, integer) from public, anon;
revoke execute on function financeiro.extrato_conta_bancaria(integer, integer, date, date, integer, boolean) from public, anon;
revoke execute on function financeiro.conferir_saldo_conta(integer, integer) from public, anon;
revoke execute on function financeiro.criar_conta_bancaria(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_conta_bancaria(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.ajustar_saldo_conta(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_ajuste_conta(integer, integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.excluir_ajuste_conta(integer, integer, integer) from public, anon;
revoke execute on function financeiro.transferir_entre_contas(integer, jsonb, uuid) from public, anon;

grant execute on function financeiro.contas_bancarias_tela(integer, text) to authenticated;
grant execute on function financeiro.conta_bancaria_tela(integer, integer) to authenticated;
grant execute on function financeiro.extrato_conta_bancaria(integer, integer, date, date, integer, boolean) to authenticated;
grant execute on function financeiro.conferir_saldo_conta(integer, integer) to authenticated;
grant execute on function financeiro.criar_conta_bancaria(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_conta_bancaria(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.ajustar_saldo_conta(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_ajuste_conta(integer, integer, integer, jsonb) to authenticated;
grant execute on function financeiro.excluir_ajuste_conta(integer, integer, integer) to authenticated;
grant execute on function financeiro.transferir_entre_contas(integer, jsonb, uuid) to authenticated;

-- 6. Lancamentos (tela original do Flask, so leitura) ---------------------------------------------------------------
-- A tela junta, de todos os meses: compras de cada cartao, despesas diretas e receitas realizadas (as pontuais sao as
-- sem previsao). Formatos de LancamentoAgregado.to_dict, listar_despesas (contas fora de fatura), ReceitaRealizada,
-- ReceitaOrcamento e ItemReceita.to_dict. Escrita: pelas funcoes ja existentes (criar_compra, criar/editar/excluir
-- despesa, excluir_compra); nada novo aqui.

-- GET /api/cartoes/<id>/lancamentos: todas as compras do cartao, da mais recente a mais antiga.
create function financeiro.compras_do_cartao_tela(p_perfil_id integer, p_cartao_id integer)
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
    if not exists (select 1 from public.item_despesa i
                    where i.id = p_cartao_id and i.tipo = 'Agregador'
                      and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)) then
        raise exception 'Cartao nao encontrado neste perfil' using errcode = '22023';
    end if;
    return coalesce((
        select jsonb_agg(jsonb_build_object(
                   'id', l.id, 'perfil_financeiro_id', l.perfil_financeiro_id, 'item_agregado_id', l.item_agregado_id,
                   'categoria_cartao_id', l.categoria_cartao_id, 'descricao', l.descricao, 'valor', l.valor,
                   'data_compra', l.data_compra, 'mes_fatura', l.mes_fatura, 'numero_parcela', l.numero_parcela,
                   'total_parcelas', l.total_parcelas, 'observacoes', l.observacoes, 'is_recorrente', l.is_recorrente,
                   'item_despesa_id', l.item_despesa_id,
                   'categoria_cartao', case when cc.id is null then null else jsonb_build_object(
                       'id', cc.id, 'nome', to_jsonb(cc) -> 'nome', 'icone', to_jsonb(cc) -> 'icone',
                       'logo_url', to_jsonb(cc) -> 'logo_url') end)
                 order by l.data_compra desc, l.id desc)
          from public.lancamento_agregado l
          left join public.categoria_cartao cc on cc.id = l.categoria_cartao_id
         where l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb);
end
$$;

-- GET /api/despesas/ (sem mes): contas fora de fatura de todos os meses, como listar_despesas (a tela filtra Simples).
create function financeiro.despesas_diretas_tela(p_perfil_id integer)
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
    return coalesce((
        select jsonb_agg(jsonb_build_object(
                   'id', c.id, 'nome', c.descricao, 'descricao', coalesce(c.observacoes, ''),
                   'tipo', coalesce(i.tipo, 'Simples'), 'valor', c.valor, 'conta_bancaria_id', c.conta_bancaria_id,
                   'financiamento_parcela_id', c.financiamento_parcela_id, 'categoria_id', cat.id,
                   'categoria', case when cat.id is null then null else jsonb_build_object(
                       'id', cat.id, 'nome', cat.nome, 'cor', to_jsonb(cat) -> 'cor', 'icone', to_jsonb(cat) -> 'icone',
                       'logo_url', to_jsonb(cat) -> 'logo_url') end,
                   'data_vencimento', c.data_vencimento, 'data_pagamento', c.data_pagamento,
                   'pago', c.status_pagamento = 'Pago', 'status_pagamento', c.status_pagamento,
                   'mes_competencia', to_char(c.mes_referencia, 'YYYY-MM'), 'recorrente', coalesce(i.recorrente, false),
                   'tipo_recorrencia', i.tipo_recorrencia,
                   'meio_pagamento', case when i.id is not null then i.meio_pagamento
                                          when c.debito_automatico then 'debito' end,
                   'debito_automatico', c.debito_automatico, 'numero_parcela', c.numero_parcela,
                   'total_parcelas', c.total_parcelas, 'agrupado', false, 'ativo', true, 'is_fatura_cartao', false)
                 order by c.data_vencimento desc, c.id desc)
          from public.conta c
          left join public.item_despesa i on i.id = c.item_despesa_id
          left join public.categoria cat on cat.id = i.categoria_id
         where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
           and not coalesce(c.is_fatura_cartao, false)), '[]'::jsonb);
end
$$;

-- GET /api/receitas/realizadas[?ano_mes=], /api/receitas/orcamento?ano=, /api/receitas/itens.
create function financeiro.receitas_lancamentos_tela(p_perfil_id integer, p_mes date, p_ano integer)
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
    return jsonb_build_object(
        'realizadas', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', r.id, 'perfil_financeiro_id', r.perfil_financeiro_id, 'item_receita_id', r.item_receita_id,
                       'data_recebimento', r.data_recebimento, 'valor_recebido', r.valor_recebido,
                       'mes_referencia', r.mes_referencia, 'competencia', r.mes_referencia,
                       'conta_origem_id', r.conta_origem_id, 'conta_bancaria_id', r.conta_bancaria_id,
                       'descricao', r.descricao, 'orcamento_id', r.orcamento_id, 'observacoes', r.observacoes,
                       'estornada', financeiro.receita_estornada(r.id),
                       'item_receita', case when i.id is null then null
                                            else jsonb_build_object('id', i.id, 'nome', i.nome, 'tipo', i.tipo) end)
                     order by r.data_recebimento desc, r.id desc)
              from public.receita_realizada r
              left join public.item_receita i on i.id = r.item_receita_id
             where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
               and (p_mes is null or date_trunc('month', r.mes_referencia::timestamp) = date_trunc('month', p_mes::timestamp))),
            '[]'::jsonb),
        'orcamentos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', o.id, 'perfil_financeiro_id', o.perfil_financeiro_id, 'item_receita_id', o.item_receita_id,
                       'mes_referencia', o.mes_referencia, 'valor_esperado', o.valor_esperado,
                       'periodicidade', o.periodicidade, 'observacoes', o.observacoes) order by o.mes_referencia, o.id)
              from public.receita_orcamento o
             where financeiro.pertence_ao_perfil(o.perfil_financeiro_id, p_perfil_id)
               and p_ano is not null and extract(year from o.mes_referencia) = p_ano), '[]'::jsonb),
        'itens', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', i.id, 'perfil_financeiro_id', i.perfil_financeiro_id, 'nome', i.nome, 'tipo', i.tipo,
                       'descricao', i.descricao, 'ativo', i.ativo, 'valor_base_mensal', i.valor_base_mensal,
                       'dia_previsto_pagamento', i.dia_previsto_pagamento, 'conta_origem_id', i.conta_origem_id,
                       'conta_bancaria_id', i.conta_bancaria_id, 'recorrente', i.recorrente) order by i.nome, i.id)
              from public.item_receita i
             where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb));
end
$$;

revoke execute on function financeiro.compras_do_cartao_tela(integer, integer) from public, anon;
revoke execute on function financeiro.despesas_diretas_tela(integer) from public, anon;
revoke execute on function financeiro.receitas_lancamentos_tela(integer, date, integer) from public, anon;
grant execute on function financeiro.compras_do_cartao_tela(integer, integer) to authenticated;
grant execute on function financeiro.despesas_diretas_tela(integer) to authenticated;
grant execute on function financeiro.receitas_lancamentos_tela(integer, date, integer) to authenticated;
