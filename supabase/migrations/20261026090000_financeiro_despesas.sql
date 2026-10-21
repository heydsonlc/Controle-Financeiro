-- FIN-DESPESAS-1 — cadastro e edicao de despesas (avulsas e recorrentes), por perfil.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261026090000).
-- Validada em cluster local descartavel, com comparacao contra o Flask
-- (tests/test_supabase_despesas.py). Contrato e diagnostico: docs/FIN_DESPESAS_1.md.
--
-- Reutiliza o modelo do Flask: public.item_despesa (cadastro) e public.conta (conta do
-- mes). Nenhuma tabela paralela de despesas; so a de idempotencia (operacao_despesa).
-- Regras (validadas aqui, nunca so no navegador):
-- - so quem tem gestao explicita do perfil (pode_gerir) escreve; LEITOR so le;
-- - so despesas 'Simples' sem origem automatica: cartoes, consorcios, financiamentos,
--   veiculos/mobilidade/assinaturas ficam com os seus modulos (bloqueadas com motivo);
-- - conta paga, com movimento financeiro ou ligada a financiamento: nada muda nem sai;
-- - avulsa: item + uma conta pendente; competencia explicita (padrao = mes do vencimento,
--   como o Flask). Recorrente: so o item; a geracao e a do FIN-RECORRENCIA-1 (sem outro gerador);
-- - excluir conta recorrente registra a competencia como DISPENSADA (nao volta);
-- - calendario de recorrencia (dia/tipo) e exclusao de conta recorrente so quando o perfil
--   esta no novo gerador (T1): o Flask identifica contas pela data e duplicaria;
-- - concorrencia: linhas travadas (FOR UPDATE) e versao (md5) conferida antes de alterar;
--   criacao idempotente por chave (uuid) enviada pelo cliente;
-- - nenhum pagamento, saldo ou movimento e tocado.

create table financeiro.operacao_despesa (
    chave                uuid        primary key,
    user_id              uuid        not null references auth.users (id) on delete cascade,
    perfil_financeiro_id integer     not null,
    operacao             text        not null,
    resultado            jsonb       not null,
    criado_em            timestamptz not null default now()
);

comment on table financeiro.operacao_despesa is
    'FIN-DESPESAS-1: resultado de cada criacao por chave do cliente (repeticao devolve o mesmo resultado).';

alter table financeiro.operacao_despesa enable row level security;
alter table financeiro.operacao_despesa force row level security;
revoke all on financeiro.operacao_despesa from public, anon, authenticated;

-- Linha do perfil (NULL = legado do "Pessoal"). Interna.
create function financeiro.pertence_ao_perfil(p_registro_perfil integer, p_perfil_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select p_registro_perfil = p_perfil_id
        or (p_registro_perfil is null
            and exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal'))
$$;

-- Versao para concorrencia otimista: muda a cada alteracao da conta ou do item. Internas.
create function financeiro.versao_despesa(p_conta_id integer)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select md5(c::text || '|' || i::text)
      from public.conta c join public.item_despesa i on i.id = c.item_despesa_id
     where c.id = p_conta_id
$$;

create function financeiro.versao_recorrencia(p_item_id integer)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select md5(i::text) from public.item_despesa i where i.id = p_item_id
$$;

-- Motivo que impede editar/excluir a conta (NULL = permitido). Interna.
create function financeiro.bloqueio_da_despesa(p_conta_id integer)
    returns text
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta;
    v_item  public.item_despesa;
begin
    select * into v_conta from public.conta where id = p_conta_id;
    if not found then
        return 'Despesa inexistente';
    end if;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id;
    if coalesce(v_conta.is_fatura_cartao, false) or v_item.tipo = 'Agregador' or v_item.meio_pagamento = 'cartao' then
        return 'Fatura ou compra de cartao: fica no modulo de cartoes';
    end if;
    if v_item.tipo = 'Consorcio' then
        return 'Parcela de consorcio: fica no modulo de consorcios';
    end if;
    if v_item.tipo = 'Financiamento' or v_conta.financiamento_parcela_id is not null
       or exists (select 1 from public.financiamento_parcela fp where fp.conta_id = v_conta.id) then
        return 'Parcela de financiamento: fica no modulo de financiamentos';
    end if;
    if v_item.tipo is distinct from 'Simples' or v_item.origem_tipo is not null then
        return 'Gerada por outro modulo (veiculos, mobilidade ou assinaturas)';
    end if;
    if v_conta.status_pagamento = 'Pago' or v_conta.data_pagamento is not null then
        return 'Despesa paga: correcao so por estorno';
    end if;
    if exists (select 1 from public.movimento_financeiro m where m.conta_id = v_conta.id or m.fatura_id = v_conta.id) then
        return 'Possui movimento financeiro vinculado';
    end if;
    return null;
end
$$;

-- Leitura dos dados validados de uma despesa (jsonb do navegador). Interna.
-- p_parcial: so as chaves presentes sao validadas/devolvidas (edicao).
create function financeiro.ler_dados_despesa(p_dados jsonb, p_perfil_id integer, p_parcial boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_saida jsonb := '{}'::jsonb;
    v_texto text;
    v_valor numeric;
    v_data  date;
    v_int   integer;
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da despesa invalidos' using errcode = '22023';
    end if;
    if p_dados ->> 'meio_pagamento' = 'cartao' or p_dados ? 'cartao_id' then
        raise exception 'Despesas de cartao ficam no modulo de cartoes' using errcode = '22023';
    end if;

    if p_dados ? 'nome' or not p_parcial then
        v_texto := btrim(coalesce(p_dados ->> 'nome', ''));
        if v_texto = '' or length(v_texto) > 100 then
            raise exception 'Nome obrigatorio (ate 100 caracteres)' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('nome', v_texto);
    end if;

    if p_dados ? 'valor' or not p_parcial then
        begin
            v_valor := (p_dados ->> 'valor')::numeric;
        exception when others then
            raise exception 'Valor invalido' using errcode = '22023';
        end;
        if v_valor is null or v_valor <= 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
            raise exception 'Valor deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('valor', v_valor);
    end if;

    if p_dados ? 'categoria_id' or not p_parcial then
        begin
            v_int := (p_dados ->> 'categoria_id')::integer;
        exception when others then
            v_int := null;
        end;
        if v_int is null or not exists (select 1 from public.categoria c where c.id = v_int and coalesce(c.ativo, true)) then
            raise exception 'Categoria inexistente ou inativa' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('categoria_id', v_int);
    end if;

    if p_dados ? 'data_vencimento' or not p_parcial then
        begin
            v_data := (p_dados ->> 'data_vencimento')::date;
        exception when others then
            v_data := null;
        end;
        if v_data is null or v_data < date '2000-01-01' or v_data > date '2100-12-31' then
            raise exception 'Data de vencimento invalida' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('data_vencimento', v_data);
    end if;

    if p_dados ? 'competencia' and nullif(p_dados ->> 'competencia', '') is not null then
        begin
            v_data := date_trunc('month', (p_dados ->> 'competencia')::date::timestamp)::date;
        exception when others then
            raise exception 'Competencia invalida' using errcode = '22023';
        end;
        v_saida := v_saida || jsonb_build_object('competencia', v_data);
    end if;

    if p_dados ? 'tipo_recorrencia' then
        if p_dados ->> 'tipo_recorrencia' not in ('mensal', 'anual') then
            raise exception 'Recorrencia deve ser mensal ou anual' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('tipo_recorrencia', p_dados ->> 'tipo_recorrencia');
    end if;

    if p_dados ? 'descricao' then
        v_texto := nullif(btrim(coalesce(p_dados ->> 'descricao', '')), '');
        if length(v_texto) > 1000 then
            raise exception 'Observacoes ate 1000 caracteres' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('descricao', v_texto);
    end if;

    if p_dados ? 'debito_automatico' or not p_parcial then
        if coalesce((p_dados ->> 'debito_automatico')::boolean, false) then
            begin
                v_int := (p_dados ->> 'conta_bancaria_id')::integer;
            exception when others then
                v_int := null;
            end;
            if v_int is null or not exists (
                select 1 from public.conta_bancaria b
                 where b.id = v_int and b.status = 'ATIVO'
                   and financeiro.pertence_ao_perfil(b.perfil_financeiro_id, p_perfil_id)) then
                raise exception 'Debito automatico exige uma conta bancaria ativa do perfil' using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object('debito_automatico', true, 'conta_bancaria_id', v_int);
        else
            v_saida := v_saida || jsonb_build_object('debito_automatico', false, 'conta_bancaria_id', null);
        end if;
    end if;
    return v_saida;
end
$$;

-- Categorias de despesa (globais no Flask), para quem tem algum perfil autorizado.
create function financeiro.categorias_de_despesa()
    returns table (id integer, nome text, cor text)
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select c.id, c.nome::text, c.cor::text
      from public.categoria c
     where coalesce(c.ativo, true)
       and exists (select 1 from financeiro.perfil_acesso a where a.user_id = (select auth.uid()))
     order by c.nome
$$;

-- Dados e permissoes de uma conta para a tela (somente leitura).
create function financeiro.despesa_para_edicao(p_perfil_id integer, p_conta_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_conta     public.conta;
    v_item      public.item_despesa;
    v_bloqueio  text;
    v_gerir     boolean;
    v_novo      boolean;
    v_rec_ok    boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_conta from public.conta where id = p_conta_id;
    if not found or coalesce(v_conta.is_fatura_cartao, false)
       or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Despesa nao encontrada neste perfil' using errcode = '42501';
    end if;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id;
    v_bloqueio := financeiro.bloqueio_da_despesa(p_conta_id);
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    v_novo := financeiro.gerador_do_perfil(p_perfil_id) = 'NOVO';
    v_rec_ok := coalesce(v_item.recorrente, false) and v_item.tipo = 'Simples' and v_item.origem_tipo is null
                and coalesce(v_item.meio_pagamento, '') <> 'cartao';
    return jsonb_build_object(
        'conta', jsonb_build_object(
            'id', v_conta.id, 'nome', v_conta.descricao, 'valor', v_conta.valor,
            'data_vencimento', v_conta.data_vencimento, 'competencia', v_conta.mes_referencia,
            'descricao', v_conta.observacoes, 'debito_automatico', coalesce(v_conta.debito_automatico, false),
            'conta_bancaria_id', v_conta.conta_bancaria_id, 'status_pagamento', v_conta.status_pagamento),
        'item', jsonb_build_object(
            'id', v_item.id, 'nome', v_item.nome, 'categoria_id', v_item.categoria_id,
            'recorrente', coalesce(v_item.recorrente, false), 'tipo_recorrencia', coalesce(v_item.tipo_recorrencia, 'mensal'),
            'ativo', coalesce(v_item.ativo, true), 'data_vencimento', v_item.data_vencimento, 'valor', v_item.valor,
            'descricao', v_item.descricao, 'debito_automatico', v_item.meio_pagamento = 'debito_automatico',
            'conta_bancaria_id', v_item.conta_bancaria_id),
        'bloqueio', v_bloqueio,
        'gerador', case when v_novo then 'NOVO' else 'FLASK' end,
        'pode_gerir', v_gerir,
        'pode_editar', v_gerir and v_bloqueio is null,
        'pode_mudar_vencimento', v_gerir and v_bloqueio is null and (not coalesce(v_item.recorrente, false) or v_novo),
        'pode_excluir', v_gerir and v_bloqueio is null and (not coalesce(v_item.recorrente, false) or v_novo),
        'pode_editar_recorrencia', v_gerir and v_rec_ok,
        'pode_mudar_calendario', v_gerir and v_rec_ok and v_novo,
        'pode_inativar_recorrencia', v_gerir and v_rec_ok and coalesce(v_item.ativo, true),
        'versao', financeiro.versao_despesa(p_conta_id),
        'versao_recorrencia', financeiro.versao_recorrencia(v_item.id));
end
$$;

-- Cadastro: avulsa (item + 1 conta pendente) ou recorrente (so o item).
create function financeiro.criar_despesa(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_despesa;
    v_d         jsonb;
    v_rec       boolean;
    v_venc      date;
    v_comp      date;
    v_item_id   integer;
    v_conta_id  integer;
    v_resultado jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    -- Repeticao (duplo clique, reenvio): a mesma chave devolve o mesmo resultado.
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261026));
    select * into v_anterior from financeiro.operacao_despesa o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;

    v_d := financeiro.ler_dados_despesa(p_dados, p_perfil_id, false);
    v_rec := coalesce((p_dados ->> 'recorrente')::boolean, false);
    v_venc := (v_d ->> 'data_vencimento')::date;
    if v_rec then
        if v_d ? 'competencia' and (v_d ->> 'competencia')::date <> date_trunc('month', v_venc::timestamp)::date then
            raise exception 'Na recorrencia a competencia e o mes de cada vencimento' using errcode = '22023';
        end if;
    else
        v_comp := coalesce((v_d ->> 'competencia')::date, date_trunc('month', v_venc::timestamp)::date);
        if v_comp < (date_trunc('month', v_venc::timestamp) - interval '12 months')::date
           or v_comp > (date_trunc('month', v_venc::timestamp) + interval '12 months')::date then
            raise exception 'Competencia deve ficar a ate 12 meses do vencimento' using errcode = '22023';
        end if;
    end if;

    -- Mesmos campos que o Flask grava (POST /api/despesas e /api/recorrencias).
    insert into public.item_despesa (perfil_financeiro_id, nome, descricao, valor, data_vencimento, categoria_id,
                                     pago, recorrente, tipo_recorrencia, mes_competencia, tipo, meio_pagamento,
                                     conta_bancaria_id, ativo, criado_em)
    values (p_perfil_id, v_d ->> 'nome', v_d ->> 'descricao', (v_d ->> 'valor')::numeric, v_venc,
            (v_d ->> 'categoria_id')::integer, false, v_rec, coalesce(v_d ->> 'tipo_recorrencia', 'mensal'),
            to_char(v_venc - interval '1 month', 'YYYY-MM'), 'Simples',
            case when (v_d ->> 'debito_automatico')::boolean then 'debito_automatico' end,
            (v_d ->> 'conta_bancaria_id')::integer, true, now() at time zone 'utc')
    returning id into v_item_id;

    if not v_rec then
        insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor,
                                  data_vencimento, status_pagamento, debito_automatico, conta_bancaria_id,
                                  numero_parcela, total_parcelas, observacoes, is_fatura_cartao, estouro_orcamento,
                                  status_fatura, criado_em)
        values (p_perfil_id, v_item_id, v_comp, v_d ->> 'nome', (v_d ->> 'valor')::numeric, v_venc, 'Pendente',
                (v_d ->> 'debito_automatico')::boolean, (v_d ->> 'conta_bancaria_id')::integer, 1, 1,
                v_d ->> 'descricao', false, false, 'ABERTA', now() at time zone 'utc')
        returning id into v_conta_id;
    end if;

    v_resultado := jsonb_build_object('item_id', v_item_id, 'conta_id', v_conta_id, 'recorrente', v_rec,
                                      'competencia', coalesce(v_comp, date_trunc('month', v_venc::timestamp)::date));
    insert into financeiro.operacao_despesa (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_despesa', v_resultado);
    return v_resultado;
end
$$;

-- Trava a conta e o item e confere perfil, bloqueio e versao. Interna.
create function financeiro.travar_despesa(p_perfil_id integer, p_conta_id integer, p_versao text)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_conta    public.conta;
    v_bloqueio text;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_conta from public.conta where id = p_conta_id for update;
    if not found or coalesce(v_conta.is_fatura_cartao, false)
       or not financeiro.pertence_ao_perfil(v_conta.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Despesa nao encontrada neste perfil' using errcode = '42501';
    end if;
    perform 1 from public.item_despesa where id = v_conta.item_despesa_id for update;
    v_bloqueio := financeiro.bloqueio_da_despesa(p_conta_id);
    if v_bloqueio is not null then
        raise exception 'Operacao bloqueada: %', v_bloqueio using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    if p_versao is null or p_versao is distinct from financeiro.versao_despesa(p_conta_id) then
        raise exception 'A despesa foi alterada por outra operacao. Recarregue e tente de novo.'
            using errcode = 'P0001', hint = 'VERSAO';
    end if;
end
$$;

-- Edicao de uma conta pendente. Avulsa: tudo, inclusive competencia e categoria.
-- Recorrente: valor, vencimento (so no novo gerador), nome e observacoes; a competencia e
-- a identidade da recorrencia (nao muda) e a categoria e da recorrencia (editar_recorrencia).
create function financeiro.editar_despesa(p_perfil_id integer, p_conta_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_conta public.conta;
    v_item  public.item_despesa;
    v_d     jsonb;
    v_venc  date;
    v_comp  date;
begin
    perform financeiro.travar_despesa(p_perfil_id, p_conta_id, p_versao);
    select * into v_conta from public.conta where id = p_conta_id;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id;
    v_d := financeiro.ler_dados_despesa(p_dados, p_perfil_id, true);
    v_venc := coalesce((v_d ->> 'data_vencimento')::date, v_conta.data_vencimento);

    if coalesce(v_item.recorrente, false) then
        if v_d ? 'competencia' and (v_d ->> 'competencia')::date <> v_conta.mes_referencia then
            raise exception 'A competencia de uma conta recorrente nao muda' using errcode = '22023';
        end if;
        if v_d ? 'categoria_id' and (v_d ->> 'categoria_id')::integer is distinct from v_item.categoria_id then
            raise exception 'A categoria e da recorrencia: edite a recorrencia' using errcode = '22023';
        end if;
        if v_venc <> v_conta.data_vencimento and financeiro.gerador_do_perfil(p_perfil_id) <> 'NOVO' then
            raise exception 'Vencimento de conta recorrente gerada pelo sistema atual nao pode mudar aqui'
                using errcode = 'P0001', hint = 'GERADOR_FLASK';
        end if;
        v_comp := v_conta.mes_referencia;
    else
        v_comp := coalesce((v_d ->> 'competencia')::date, v_conta.mes_referencia);
        if v_comp < (date_trunc('month', v_venc::timestamp) - interval '12 months')::date
           or v_comp > (date_trunc('month', v_venc::timestamp) + interval '12 months')::date then
            raise exception 'Competencia deve ficar a ate 12 meses do vencimento' using errcode = '22023';
        end if;
    end if;

    update public.conta c
       set descricao = coalesce(v_d ->> 'nome', c.descricao),
           valor = coalesce((v_d ->> 'valor')::numeric, c.valor),
           data_vencimento = v_venc,
           mes_referencia = v_comp,
           observacoes = case when v_d ? 'descricao' then v_d ->> 'descricao' else c.observacoes end,
           debito_automatico = case when v_d ? 'debito_automatico' then (v_d ->> 'debito_automatico')::boolean
                                    else c.debito_automatico end,
           conta_bancaria_id = case when v_d ? 'debito_automatico' then (v_d ->> 'conta_bancaria_id')::integer
                                    else c.conta_bancaria_id end
     where c.id = p_conta_id;

    if not coalesce(v_item.recorrente, false) then
        -- Avulsa: o item espelha a sua unica conta (como o Flask cria).
        update public.item_despesa i
           set nome = coalesce(v_d ->> 'nome', i.nome),
               valor = coalesce((v_d ->> 'valor')::numeric, i.valor),
               data_vencimento = v_venc,
               mes_competencia = to_char(v_venc - interval '1 month', 'YYYY-MM'),
               categoria_id = coalesce((v_d ->> 'categoria_id')::integer, i.categoria_id),
               descricao = case when v_d ? 'descricao' then v_d ->> 'descricao' else i.descricao end,
               meio_pagamento = case when v_d ? 'debito_automatico'
                                     then case when (v_d ->> 'debito_automatico')::boolean then 'debito_automatico' end
                                     else i.meio_pagamento end,
               conta_bancaria_id = case when v_d ? 'debito_automatico' then (v_d ->> 'conta_bancaria_id')::integer
                                        else i.conta_bancaria_id end
         where i.id = v_item.id;
    end if;
    return jsonb_build_object('conta_id', p_conta_id, 'competencia', v_comp,
                              'versao', financeiro.versao_despesa(p_conta_id));
end
$$;

-- Exclusao segura de uma conta pendente. Recorrente: a competencia fica DISPENSADA (nao volta).
create function financeiro.excluir_despesa(p_perfil_id integer, p_conta_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_conta        public.conta;
    v_item         public.item_despesa;
    v_item_apagado boolean := false;
begin
    perform financeiro.travar_despesa(p_perfil_id, p_conta_id, p_versao);
    select * into v_conta from public.conta where id = p_conta_id;
    select * into v_item from public.item_despesa where id = v_conta.item_despesa_id;

    if coalesce(v_item.recorrente, false) then
        if financeiro.gerador_do_perfil(p_perfil_id) <> 'NOVO' then
            raise exception 'Conta recorrente gerada pelo sistema atual: o Flask a recriaria. Exclua pelo sistema atual.'
                using errcode = 'P0001', hint = 'GERADOR_FLASK';
        end if;
        perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao
        insert into financeiro.recorrencia_competencia
            (item_despesa_id, natureza, competencia, situacao, motivo, user_id)
        values (v_item.id, 'CONTA', date_trunc('month', v_conta.mes_referencia::timestamp)::date, 'DISPENSADA',
                'Conta excluida pelo usuario', (select auth.uid()))
        on conflict (item_despesa_id, natureza, competencia) do update
           set situacao = 'DISPENSADA', conta_id = null, lancamento_id = null, execucao_id = null,
               motivo = excluded.motivo, user_id = excluded.user_id, registrado_em = now();
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
$$;

-- Recorrencia: trava o item e confere perfil, tipo e versao. Interna.
create function financeiro.travar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text)
    returns public.item_despesa
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item public.item_despesa;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_item from public.item_despesa where id = p_item_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_item.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Recorrencia nao encontrada neste perfil' using errcode = '42501';
    end if;
    if not coalesce(v_item.recorrente, false) or v_item.tipo is distinct from 'Simples' or v_item.origem_tipo is not null
       or coalesce(v_item.meio_pagamento, '') = 'cartao' then
        raise exception 'Operacao bloqueada: recorrencia gerenciada por outro modulo' using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    if p_versao is null or p_versao is distinct from financeiro.versao_recorrencia(p_item_id) then
        raise exception 'A recorrencia foi alterada por outra operacao. Recarregue e tente de novo.'
            using errcode = 'P0001', hint = 'VERSAO';
    end if;
    return v_item;
end
$$;

-- Edicao da recorrencia: vale para as proximas geracoes; contas ja existentes ficam como estao.
create function financeiro.editar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item public.item_despesa;
    v_d    jsonb;
    v_venc date;
    v_tipo text;
begin
    v_item := financeiro.travar_recorrencia(p_perfil_id, p_item_id, p_versao);
    v_d := financeiro.ler_dados_despesa(p_dados, p_perfil_id, true);
    if v_d ? 'competencia' then
        raise exception 'Na recorrencia a competencia e o mes de cada vencimento' using errcode = '22023';
    end if;
    v_venc := coalesce((v_d ->> 'data_vencimento')::date, v_item.data_vencimento);
    v_tipo := coalesce(v_d ->> 'tipo_recorrencia', v_item.tipo_recorrencia, 'mensal');
    if (v_venc is distinct from v_item.data_vencimento or v_tipo is distinct from coalesce(v_item.tipo_recorrencia, 'mensal'))
       and financeiro.gerador_do_perfil(p_perfil_id) <> 'NOVO' then
        raise exception 'Dia e frequencia so mudam quando o novo aplicativo gera este perfil (o Flask duplicaria por data)'
            using errcode = 'P0001', hint = 'GERADOR_FLASK';
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- nao muda no meio de uma geracao
    update public.item_despesa i
       set nome = coalesce(v_d ->> 'nome', i.nome),
           valor = coalesce((v_d ->> 'valor')::numeric, i.valor),
           categoria_id = coalesce((v_d ->> 'categoria_id')::integer, i.categoria_id),
           data_vencimento = v_venc,
           mes_competencia = case when v_venc is distinct from i.data_vencimento
                                  then to_char(v_venc - interval '1 month', 'YYYY-MM') else i.mes_competencia end,
           tipo_recorrencia = v_tipo,
           descricao = case when v_d ? 'descricao' then v_d ->> 'descricao' else i.descricao end,
           meio_pagamento = case when v_d ? 'debito_automatico'
                                 then case when (v_d ->> 'debito_automatico')::boolean then 'debito_automatico' end
                                 else i.meio_pagamento end,
           conta_bancaria_id = case when v_d ? 'debito_automatico' then (v_d ->> 'conta_bancaria_id')::integer
                                    else i.conta_bancaria_id end
     where i.id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'versao', financeiro.versao_recorrencia(p_item_id));
end
$$;

-- Inativacao (como o "excluir recorrencia" do Flask): nada novo e gerado; historico fica.
create function financeiro.inativar_recorrencia(p_perfil_id integer, p_item_id integer, p_versao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.travar_recorrencia(p_perfil_id, p_item_id, p_versao);
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    update public.item_despesa set ativo = false where id = p_item_id;
    return jsonb_build_object('item_id', p_item_id, 'ativo', false);
end
$$;

revoke execute on function financeiro.pertence_ao_perfil(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.versao_despesa(integer) from public, anon, authenticated;
revoke execute on function financeiro.versao_recorrencia(integer) from public, anon, authenticated;
revoke execute on function financeiro.bloqueio_da_despesa(integer) from public, anon, authenticated;
revoke execute on function financeiro.ler_dados_despesa(jsonb, integer, boolean) from public, anon, authenticated;
revoke execute on function financeiro.travar_despesa(integer, integer, text) from public, anon, authenticated;
revoke execute on function financeiro.travar_recorrencia(integer, integer, text) from public, anon, authenticated;
revoke execute on function financeiro.categorias_de_despesa() from public, anon;
revoke execute on function financeiro.despesa_para_edicao(integer, integer) from public, anon;
revoke execute on function financeiro.criar_despesa(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_despesa(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.excluir_despesa(integer, integer, text) from public, anon;
revoke execute on function financeiro.editar_recorrencia(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.inativar_recorrencia(integer, integer, text) from public, anon;
grant execute on function financeiro.categorias_de_despesa() to authenticated;
grant execute on function financeiro.despesa_para_edicao(integer, integer) to authenticated;
grant execute on function financeiro.criar_despesa(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_despesa(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.excluir_despesa(integer, integer, text) to authenticated;
grant execute on function financeiro.editar_recorrencia(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.inativar_recorrencia(integer, integer, text) to authenticated;
