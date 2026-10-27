-- FIN-CATEGORIAS-RECORRENCIAS-2 — recorrencias semanais e a cada 2 semanas, pendencias de Receitas e escrita do
-- catalogo global de categorias (preparada, sem escrita concorrente).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261125090000).
-- Validada em cluster PostgreSQL local descartavel (tests/test_supabase_categorias_recorrencias.py).
-- Docs: docs/FIN_CATEGORIAS_RECORRENCIAS_2.md. Reversao: supabase/reversao/20261125090000_categorias_recorrencias_anterior.sql.
--
-- Nenhum dado existente e alterado pela migration: tres tabelas novas de controle (vazias), funcoes novas e seis
-- funcoes existentes substituidas pelo texto vigente com os trechos marcados "FIN-CATEGORIAS-RECORRENCIAS-2"
-- (plano_recorrencia, gerar_mes_interno, ler_dados_despesa, excluir_despesa, recorrencias_do_perfil,
-- receita_orcamento_flask). O caminho mensal e anual do gerador nao muda. O escritor unico por perfil
-- (exigir_escrita_novo, FIN-ESCRITOR-UNICO-FINAL-1) continua em todas as escritas de perfil; o catalogo global ganha o
-- seu proprio escritor, que nasce FLASK.

-- =====================================================================================================================
-- 1. Recorrencias semanais e a cada 2 semanas (R1)
-- =====================================================================================================================
--
-- Frequencias do Flask (item_despesa.tipo_recorrencia): 'semanal_N_D' (a cada N semanas no dia D, 0 = domingo, como a
-- tela e o banco do Flask), e as antigas 'semanal' (N = 1) e 'a_cada_2_semanas' (N = 2), sem dia (vale o do
-- vencimento). 'semanal_N' (sem dia) tambem e lida, como no Flask.
--
-- Regra de datas: a primeira ocorrencia e o vencimento cadastrado levado ao dia da semana escolhido; as seguintes,
-- a cada N semanas a partir dela. E a regra do "proximo vencimento" do Flask (routes/recorrencias.py,
-- _proximo_vencimento) e a do gerador do Flask como a tela o chama (desde o primeiro vencimento): mesmas datas,
-- conferidas para semanal_N_D, semanal e a_cada_2_semanas. So quando chamado com uma janela que comeca depois
-- (mes_referencia, caminho que a tela nao usa) o Flask recomeca a contagem no inicio da janela; aqui a fase e sempre a
-- do primeiro vencimento. Descricao de cada conta como no Flask: "<nome> - dd/mm".
--
-- Identidade: uma linha por recorrencia + data da ocorrencia (financeiro.recorrencia_ocorrencia), no lugar da linha
-- por competencia das mensais (que continua para mensal e anual, sem mudanca). Gerada ou dispensada uma vez, a
-- ocorrencia nao e recriada. Conta ja gravada pelo Flask no mesmo ciclo (de N semanas a partir da ocorrencia) e
-- reconhecida, mesmo em outro dia: nada e duplicado na transicao do perfil.
--
-- Compra recorrente semanal no cartao: o Flask nao a lanca (so mensal e anual); aqui ela fica REJEITADA com o motivo.

create table financeiro.recorrencia_ocorrencia (
    item_despesa_id integer     not null,
    data_ocorrencia date        not null,
    situacao        text        not null check (situacao in ('GERADA', 'DISPENSADA')),
    conta_id        integer,
    execucao_id     bigint      references financeiro.geracao_execucao (id),
    motivo          text,
    user_id         uuid        references auth.users (id) on delete set null,
    registrado_em   timestamptz not null default now(),
    primary key (item_despesa_id, data_ocorrencia),
    check (situacao <> 'GERADA' or conta_id is not null)
);

comment on table financeiro.recorrencia_ocorrencia is
    'FIN-CATEGORIAS-RECORRENCIAS-2: ocorrencias de recorrencias semanais geradas pelo novo motor ou dispensadas. Nunca recriadas.';

alter table financeiro.recorrencia_ocorrencia enable row level security;
alter table financeiro.recorrencia_ocorrencia force row level security;
revoke all on financeiro.recorrencia_ocorrencia from public, anon, authenticated;

-- Intervalo em semanas (NULL: nao e semanal).
create function financeiro.semanas_da_recorrencia(p_tipo text)
    returns integer
    language sql
    immutable
    set search_path = ''
as $$
    select case
               when p_tipo = 'semanal' then 1
               when p_tipo = 'a_cada_2_semanas' then 2
               when p_tipo ~ '^semanal_[0-9]{1,2}(_[0-6])?$' then greatest(split_part(p_tipo, '_', 2)::integer, 1)
           end
$$;

-- Primeira ocorrencia: o vencimento levado ao dia da semana da frequencia (0 = domingo, como extract(dow)).
create function financeiro.ancora_semanal(p_tipo text, p_vencimento date)
    returns date
    language sql
    immutable
    set search_path = ''
as $$
    select p_vencimento + case
               when p_tipo ~ '^semanal_[0-9]{1,2}_[0-6]$'
                   then ((split_part(p_tipo, '_', 3)::integer - extract(dow from p_vencimento)::integer) % 7 + 7) % 7
               else 0
           end
$$;

-- Ocorrencia (data do ciclo) a que uma data pertence; NULL antes da primeira.
create function financeiro.ocorrencia_semanal(p_tipo text, p_vencimento date, p_data date)
    returns date
    language sql
    immutable
    set search_path = ''
as $$
    select case when p_data >= a.d
                then a.d + ((p_data - a.d) / (7 * n.s)) * 7 * n.s end
      from (select financeiro.ancora_semanal(p_tipo, p_vencimento) as d) a,
           (select financeiro.semanas_da_recorrencia(p_tipo) as s) n
$$;

-- Proxima ocorrencia a partir de p_hoje (inclusive), como _proximo_vencimento do Flask.
create function financeiro.proxima_ocorrencia_semanal(p_tipo text, p_vencimento date, p_hoje date)
    returns date
    language sql
    immutable
    set search_path = ''
as $$
    select case when a.d >= p_hoje then a.d
                else a.d + ((p_hoje - a.d + 7 * n.s - 1) / (7 * n.s)) * 7 * n.s end
      from (select financeiro.ancora_semanal(p_tipo, p_vencimento) as d) a,
           (select financeiro.semanas_da_recorrencia(p_tipo) as s) n
$$;

create function financeiro.semanas_do_item(p_item_id integer)
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select financeiro.semanas_da_recorrencia(i.tipo_recorrencia) from public.item_despesa i where i.id = p_item_id
$$;

-- Linhas do plano de uma recorrencia semanal (conta), da primeira ocorrencia ate o fim do mes seguinte ao pedido
-- (o mesmo alcance das mensais). p_base traz o que vale para todas (natureza, item, valor, perfil, conta bancaria...).
create function financeiro.ocorrencias_semanais(p_base financeiro.linha_plano, p_tipo text, p_vencimento date,
                                                p_limite date)
    returns setof financeiro.linha_plano
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_semanas integer := financeiro.semanas_da_recorrencia(p_tipo);
    v_data    date := financeiro.ancora_semanal(p_tipo, p_vencimento);
    v_fim     date := (p_limite + interval '1 month')::date;
    v_linha   financeiro.linha_plano;
    v_oc      financeiro.recorrencia_ocorrencia;
    v_id      integer;
begin
    while v_data < v_fim loop
        v_linha := p_base;
        v_linha.competencia := date_trunc('month', v_data::timestamp)::date;
        v_linha.data_vencimento := v_data;
        v_linha.nome := p_base.nome || ' - ' || to_char(v_data, 'DD/MM');  -- _descricao_recorrencia_com_data do Flask
        select * into v_oc from financeiro.recorrencia_ocorrencia o
         where o.item_despesa_id = p_base.item_despesa_id and o.data_ocorrencia = v_data;
        if found then
            if v_oc.situacao = 'GERADA' and exists (select 1 from public.conta c where c.id = v_oc.conta_id) then
                v_linha.situacao := 'EXISTENTE';
                v_linha.registro_id := v_oc.conta_id;
            else
                v_linha.situacao := 'DISPENSADA';
                v_linha.motivo := case when v_oc.situacao = 'DISPENSADA' then coalesce(v_oc.motivo, 'Ocorrencia dispensada')
                                       else 'Registro gerado foi removido; nao sera recriado' end;
            end if;
        else
            -- O que o Flask (ou outro caminho) ja gravou neste ciclo, em qualquer dia dele.
            select c.id into v_id
              from public.conta c
             where c.item_despesa_id = p_base.item_despesa_id
               and coalesce(c.is_fatura_cartao, false) = false
               and c.data_vencimento >= v_data and c.data_vencimento < v_data + 7 * v_semanas
             order by c.data_vencimento, c.id
             limit 1;
            v_linha.situacao := case when v_id is null then 'A_GERAR' else 'EXISTENTE' end;
            v_linha.registro_id := v_id;
        end if;
        return next v_linha;
        v_data := v_data + 7 * v_semanas;
    end loop;
end
$$;

revoke execute on function financeiro.semanas_da_recorrencia(text) from public, anon, authenticated;
revoke execute on function financeiro.ancora_semanal(text, date) from public, anon, authenticated;
revoke execute on function financeiro.ocorrencia_semanal(text, date, date) from public, anon, authenticated;
revoke execute on function financeiro.proxima_ocorrencia_semanal(text, date, date) from public, anon, authenticated;
revoke execute on function financeiro.semanas_do_item(integer) from public, anon, authenticated;
revoke execute on function financeiro.ocorrencias_semanais(financeiro.linha_plano, text, date, date) from public, anon, authenticated;

-- =====================================================================================================================
-- 2. Receitas: valor base, recorrencia e reativacao da fonte; recebimento sem previsao
-- =====================================================================================================================
--
-- Regra original (Flask, PUT /api/receitas/itens/<id>): grava valor base e recorrencia e, se a fonte fica recorrente com
-- valor base, cria as previsoes que FALTAM nos 12 meses a partir do mes atual, pelo valor base. Previsoes ja gravadas
-- (inclusive futuras, inclusive as zeradas por "remover previsao") nunca mudam. Aqui a mesma regra, so para fonte
-- ativa (o Flask criava previsoes ate para fonte inativa), com a data prevista pelo dia da fonte (como criar_receita
-- sem data). Reativar e o "ativo" do mesmo PUT.

create function financeiro.redefinir_fonte_receita(p_perfil_id integer, p_item_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item  public.item_receita;
    v_base  numeric;
    v_rec   boolean;
    v_mes0  date := date_trunc('month', (now() at time zone 'America/Sao_Paulo'))::date;
    v_mes   date;
    v_id    integer;
    v_ids   integer[] := '{}';
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    perform financeiro.travar_fonte(p_perfil_id, p_item_id, p_versao);
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da fonte invalidos' using errcode = '22023';
    end if;
    select * into v_item from public.item_receita where id = p_item_id;

    if p_dados ? 'valor_base_mensal' then
        begin
            v_base := nullif(p_dados ->> 'valor_base_mensal', '')::numeric;
        exception when others then
            raise exception 'Valor base invalido' using errcode = '22023';
        end;
        if v_base is not null and (v_base < 0 or v_base >= 100000000 or v_base <> round(v_base, 2)) then
            raise exception 'Valor base deve ser zero ou positivo, com ate 2 casas decimais' using errcode = '22023';
        end if;
    else
        v_base := v_item.valor_base_mensal;
    end if;
    if p_dados ? 'recorrente' then
        if jsonb_typeof(p_dados -> 'recorrente') <> 'boolean' then
            raise exception 'Recorrente deve ser verdadeiro ou falso' using errcode = '22023';
        end if;
        v_rec := (p_dados ->> 'recorrente')::boolean;
    else
        v_rec := coalesce(v_item.recorrente, false);
    end if;
    if p_dados ? 'ativo' and (p_dados -> 'ativo') is distinct from 'true'::jsonb then
        raise exception 'Para inativar a fonte use a inativacao' using errcode = '22023';
    end if;

    update public.item_receita i
       set valor_base_mensal = v_base,
           recorrente = v_rec,
           ativo = case when p_dados ? 'ativo' then true else i.ativo end
     where i.id = p_item_id
    returning * into v_item;

    if coalesce(v_item.ativo, true) and v_rec and coalesce(v_base, 0) > 0 then
        for i in 0..11 loop
            v_mes := (v_mes0 + make_interval(months => i))::date;
            continue when exists (select 1 from public.receita_orcamento o
                                   where o.item_receita_id = p_item_id and o.mes_referencia = v_mes);
            insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, valor_esperado,
                                                  periodicidade, observacoes, data_prevista, criado_em)
            values (coalesce(v_item.perfil_financeiro_id, p_perfil_id), p_item_id, v_mes, v_base, 'MENSAL_FIXA',
                    'Gerado automaticamente - ' || v_item.nome, null, now() at time zone 'utc')
            returning id into v_id;
            v_ids := v_ids || v_id;
        end loop;
    end if;
    return jsonb_build_object('item_receita_id', p_item_id, 'versao', financeiro.versao_fonte(p_item_id),
                              'ativo', coalesce(v_item.ativo, true), 'recorrente', v_rec, 'valor_base_mensal', v_base,
                              'previsoes_criadas', to_jsonb(v_ids));
end
$$;

-- Recebimento sem previsao (Flask: POST /api/receitas/realizadas sem orcamento na competencia). Mesmo motor do
-- receber_receita (FIN-MOVIMENTACOES-1): escritor do perfil, conta bancaria ativa e travada, credito no extrato e saldo,
-- chave contra repeticao. Com previsao gravada na competencia, recusa: o recebimento vai pela previsao (Consolidar),
-- que confere o que falta; assim a mesma receita nao entra duas vezes. Uma previsao criada depois conta este
-- recebimento (recebido_da_previsao soma por fonte e mes).
create function financeiro.receber_sem_previsao(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_receita;
    v_item      public.item_receita;
    v_banco     public.conta_bancaria;
    v_data      date;
    v_comp      date;
    v_valor     numeric;
    v_desc      text;
    v_obs       text;
    v_real      integer;
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
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261101));
    select * into v_anterior from financeiro.operacao_receita o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id
           or v_anterior.operacao <> 'receber_sem_previsao' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do recebimento invalidos' using errcode = '22023';
    end if;
    begin
        v_data := (p_dados ->> 'data_recebimento')::date;
        v_valor := (p_dados ->> 'valor_recebido')::numeric;
        v_comp := date_trunc('month', coalesce((nullif(p_dados ->> 'competencia', ''))::date, v_data)::timestamp)::date;
    exception when invalid_text_representation or datetime_field_overflow or invalid_datetime_format
                   or numeric_value_out_of_range then
        raise exception 'Dados do recebimento invalidos' using errcode = '22023';
    end;
    if v_data is null then
        raise exception 'Informe a data do recebimento' using errcode = '22023';
    end if;
    if v_valor is null or v_valor <= 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
        raise exception 'Valor recebido deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
    end if;
    v_desc := btrim(coalesce(p_dados ->> 'descricao', ''));
    v_obs := btrim(coalesce(p_dados ->> 'observacoes', ''));
    if length(v_desc) > 200 or length(v_obs) > 1000 then
        raise exception 'Descricao ate 200 e observacoes ate 1000 caracteres' using errcode = '22023';
    end if;

    perform financeiro.exigir_pagamento_novo(p_perfil_id);
    -- Mesma ordem do receber_receita: tabela de recebimentos, depois a fonte e a previsao.
    lock table public.receita_realizada in share row exclusive mode;
    select * into v_item from public.item_receita i where i.id = (p_dados ->> 'item_receita_id')::integer for update;
    if not found or not financeiro.pertence_ao_perfil(v_item.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Fonte de receita nao encontrada neste perfil' using errcode = '42501';
    end if;
    if financeiro.fonte_de_outro_modulo(v_item.id) then
        raise exception 'Operacao bloqueada: Gerada pelo modulo de consorcios' using errcode = 'P0001', hint = 'BLOQUEIO';
    end if;
    if exists (select 1 from public.receita_orcamento o where o.item_receita_id = v_item.id and o.mes_referencia = v_comp) then
        raise exception 'Esta fonte tem previsao em %: registre o recebimento pela previsao (Consolidar)',
            to_char(v_comp, 'MM/YYYY') using errcode = 'P0001', hint = 'TEM_PREVISAO';
    end if;
    v_banco := financeiro.travar_conta_bancaria(p_perfil_id,
        coalesce((nullif(p_dados ->> 'conta_bancaria_id', ''))::integer, v_item.conta_bancaria_id));
    v_desc := coalesce(nullif(v_desc, ''), v_item.nome);

    insert into public.receita_realizada (perfil_financeiro_id, item_receita_id, data_recebimento, valor_recebido,
                                         mes_referencia, conta_bancaria_id, descricao, orcamento_id, observacoes,
                                         criado_em, atualizado_em)
    values (coalesce(v_item.perfil_financeiro_id, p_perfil_id), v_item.id, v_data, v_valor, v_comp, v_banco.id,
            left(v_desc, 200), null, v_obs, now() at time zone 'utc', now() at time zone 'utc')
    returning id into v_real;
    insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento,
                                             receita_realizada_id, origem, ajustavel, criado_em)
    values (p_perfil_id, v_banco.id, 'CREDITO', v_valor, left('Receita - ' || v_desc, 200), v_data,
            v_real, 'RECEITA', false, now() at time zone 'utc')
    returning id into v_mov;
    v_saldo := financeiro.atualizar_saldo_conta(v_banco.id);
    v_resultado := jsonb_build_object('receita_realizada_id', v_real, 'movimento_id', v_mov, 'item_receita_id', v_item.id,
                                      'competencia', v_comp, 'valor_recebido', v_valor, 'data_recebimento', v_data,
                                      'conta_bancaria_id', v_banco.id, 'conta_nome', v_banco.nome, 'saldo_conta', v_saldo);
    insert into financeiro.operacao_receita (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'receber_sem_previsao', v_resultado);
    return v_resultado;
end
$$;

revoke execute on function financeiro.redefinir_fonte_receita(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.receber_sem_previsao(integer, jsonb, uuid) from public, anon;
grant execute on function financeiro.redefinir_fonte_receita(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.receber_sem_previsao(integer, jsonb, uuid) to authenticated;

-- =====================================================================================================================
-- 3. Catalogo global de categorias de despesa: escrita preparada, sem escrita concorrente
-- =====================================================================================================================
--
-- O catalogo (public.categoria e public.categoria_palavra_chave) e um so para todos os perfis. Enquanto houver perfil
-- no Flask, ele continua sendo o escritor (decisao do titular). Aqui fica pronto o escritor do novo aplicativo, com a
-- mesma regra do escritor por perfil:
-- - financeiro.catalogo_categorias: quem escreve o catalogo. Sem linha = FLASK. So administrador troca
--   (definir_escritor_catalogo, sem EXECUTE para o navegador), com responsavel e motivo; NOVO so com as 10 categorias
--   sistemicas de Mobilidade presentes (o Flask as cria sob demanda; depois da troca ele nao pode criar nada).
-- - financeiro.gestor_catalogo: contas que podem escrever no catalogo pelo novo aplicativo (concedido so por
--   administrador). Ter perfil nao basta: o catalogo atinge todos os perfis.
-- - Escritas (criar, editar, excluir categoria; criar e remover palavra-chave) exigem as duas coisas. A trava
--   consultiva (20261125, 0) e compartilhada com a guarda do Flask (routes/categorias.py), que recusa a escrita global
--   quando o escritor e NOVO.
-- Regras do Flask preservadas: nome unico sem diferenciar maiusculas; categoria sistemica (ou bloqueada) nao e editada
-- nem excluida; palavra-chave normalizada (minusculas, espacos simples), unica por categoria, removida = inativada,
-- recadastrada = reativada. Correcoes: exclusao recusa qualquer vinculo (o Flask so olhava as despesas e falhava com
-- erro 500 nos outros), cor so #RRGGBB, e os nomes das categorias sistemicas ficam reservados (o Flask promoveria a
-- categoria comum com esse nome a sistemica). Logos: arquivos no servidor do Flask; Storage fica para FIN-DOCUMENTOS-2.

create table financeiro.catalogo_categorias (
    id           boolean     primary key default true check (id),
    escritor     text        not null check (escritor in ('FLASK', 'NOVO')),
    alterado_em  timestamptz not null default now(),
    alterado_por text        not null,
    motivo       text        not null
);

create table financeiro.gestor_catalogo (
    user_id      uuid        primary key references auth.users (id) on delete cascade,
    concedido_em timestamptz not null default now(),
    concedido_por text       not null,
    motivo       text        not null
);

create table financeiro.operacao_catalogo (
    chave     uuid        primary key,
    user_id   uuid        not null references auth.users (id) on delete cascade,
    operacao  text        not null,
    resultado jsonb       not null,
    criado_em timestamptz not null default now()
);

comment on table financeiro.catalogo_categorias is
    'FIN-CATEGORIAS-RECORRENCIAS-2: escritor do catalogo global de categorias. Sem linha = FLASK. So administrador altera.';
comment on table financeiro.gestor_catalogo is
    'FIN-CATEGORIAS-RECORRENCIAS-2: contas que escrevem o catalogo global pelo novo aplicativo. So administrador concede.';

alter table financeiro.catalogo_categorias enable row level security;
alter table financeiro.catalogo_categorias force row level security;
alter table financeiro.gestor_catalogo enable row level security;
alter table financeiro.gestor_catalogo force row level security;
alter table financeiro.operacao_catalogo enable row level security;
alter table financeiro.operacao_catalogo force row level security;
revoke all on financeiro.catalogo_categorias from public, anon, authenticated;
revoke all on financeiro.gestor_catalogo from public, anon, authenticated;
revoke all on financeiro.operacao_catalogo from public, anon, authenticated;

-- As 10 categorias sistemicas de Mobilidade (backend/services/categoria_default.py, CATEGORIAS_SISTEMICAS_MOBILIDADE).
create function financeiro.categorias_sistemicas_mobilidade()
    returns table (codigo text, nome text)
    language sql
    immutable
    set search_path = ''
as $$
    values ('MOB_COMBUSTIVEL', 'Combustível'), ('MOB_SEGURO_VEICULAR', 'Seguro Veicular'),
           ('MOB_TRIBUTOS_VEICULARES', 'Tributos Veiculares'), ('MOB_REVISAO', 'Revisão'),
           ('MOB_MANUTENCAO', 'Manutenção Veicular'), ('MOB_PNEUS', 'Pneus'), ('MOB_USO_VEICULO', 'Uso do Veículo'),
           ('MOB_APP', 'Transporte por Aplicativo'), ('MOB_ASSINATURA', 'Assinatura Veicular'),
           ('MOB_LAVAGEM', 'Lavagem Veicular')
$$;

-- Troca administrativa do escritor (auditada). Sem EXECUTE para o navegador.
create function financeiro.definir_escritor_catalogo(p_escritor text, p_responsavel text, p_motivo text)
    returns text
    language plpgsql
    security invoker
    set search_path = ''
as $$
declare
    v_anterior text;
    v_faltam   text;
begin
    if p_escritor not in ('FLASK', 'NOVO') then
        raise exception 'Escritor invalido: use FLASK ou NOVO' using errcode = '22023';
    end if;
    if nullif(btrim(p_responsavel), '') is null or nullif(btrim(p_motivo), '') is null then
        raise exception 'Responsavel e motivo sao obrigatorios (auditoria)' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(20261125, 0);  -- espera escritas em andamento (Flask e novo aplicativo)
    if p_escritor = 'NOVO' then
        select string_agg(s.codigo, ', ' order by s.codigo) into v_faltam
          from financeiro.categorias_sistemicas_mobilidade() s
         where not exists (select 1 from public.categoria c where c.codigo_sistema = s.codigo and c.sistemica);
        if v_faltam is not null then
            raise exception 'Categorias sistemicas ausentes (%): o Flask as cria sob demanda e, com o catalogo no novo aplicativo, nao poderia mais',
                v_faltam using errcode = 'P0001';
        end if;
    end if;
    select c.escritor into v_anterior from financeiro.catalogo_categorias c for update;
    insert into financeiro.catalogo_categorias (id, escritor, alterado_em, alterado_por, motivo)
    values (true, p_escritor, now(), btrim(p_responsavel), btrim(p_motivo))
    on conflict (id) do update
       set escritor = excluded.escritor, alterado_em = excluded.alterado_em,
           alterado_por = excluded.alterado_por, motivo = excluded.motivo;
    return format('Catalogo de categorias: %s -> %s', coalesce(v_anterior, 'FLASK (padrao)'), p_escritor);
end
$$;

-- Concede (p_gestor) ou retira a gestao do catalogo de uma conta. Sem EXECUTE para o navegador.
create function financeiro.definir_gestor_catalogo(p_user_id uuid, p_gestor boolean, p_responsavel text, p_motivo text)
    returns text
    language plpgsql
    security invoker
    set search_path = ''
as $$
begin
    if nullif(btrim(p_responsavel), '') is null or nullif(btrim(p_motivo), '') is null then
        raise exception 'Responsavel e motivo sao obrigatorios (auditoria)' using errcode = '22023';
    end if;
    if p_gestor then
        insert into financeiro.gestor_catalogo (user_id, concedido_por, motivo)
        values (p_user_id, btrim(p_responsavel), btrim(p_motivo))
        on conflict (user_id) do update set concedido_em = now(), concedido_por = excluded.concedido_por,
                                            motivo = excluded.motivo;
        return 'Gestao do catalogo concedida';
    end if;
    delete from financeiro.gestor_catalogo where user_id = p_user_id;
    return 'Gestao do catalogo retirada';
end
$$;

-- Guarda das escritas no catalogo: escritor NOVO (CATALOGO_FLASK) e conta gestora (42501), com a trava exclusiva
-- (a do Flask e compartilhada). O escritor vem primeiro: e estado global do catalogo, nao dado de um perfil, e enquanto
-- for o Flask qualquer conta recebe o mesmo aviso.
create function financeiro.exigir_escrita_catalogo()
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_escritor text;
begin
    if (select auth.uid()) is null then
        raise exception 'Esta conta nao administra o catalogo de categorias' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(20261125, 0);
    select c.escritor into v_escritor from financeiro.catalogo_categorias c for share;
    if v_escritor is distinct from 'NOVO' then
        raise exception 'O catalogo de categorias ainda e administrado pelo sistema atual (Flask). Nada foi gravado.'
            using errcode = 'P0001', hint = 'CATALOGO_FLASK';
    end if;
    if not exists (select 1 from financeiro.gestor_catalogo g where g.user_id = (select auth.uid())) then
        raise exception 'Esta conta nao administra o catalogo de categorias' using errcode = '42501';
    end if;
end
$$;

-- Leitura para a tela: quem escreve o catalogo e se a conta pode escrever.
create function financeiro.situacao_catalogo_categorias()
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'escritor', coalesce((select c.escritor from financeiro.catalogo_categorias c), 'FLASK'),
        'gestor', exists (select 1 from financeiro.gestor_catalogo g where g.user_id = (select auth.uid())))
$$;

-- Nome, descricao, cor, icone e ativo, como o Flask le (POST/PUT /api/categorias). Interna.
create function financeiro.ler_dados_categoria(p_dados jsonb, p_parcial boolean)
    returns jsonb
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_saida jsonb := '{}'::jsonb;
    v_texto text;
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados nao fornecidos' using errcode = '22023';
    end if;
    if p_dados ? 'nome' or not p_parcial then
        v_texto := btrim(coalesce(p_dados ->> 'nome', ''));
        if v_texto = '' then
            raise exception 'Nome e obrigatorio' using errcode = '22023';
        end if;
        if length(v_texto) > 100 then
            raise exception 'Nome ate 100 caracteres' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('nome', v_texto);
    end if;
    if p_dados ? 'descricao' or not p_parcial then
        v_saida := v_saida || jsonb_build_object('descricao', btrim(coalesce(p_dados ->> 'descricao', '')));
    end if;
    if p_dados ? 'cor' then
        if coalesce(p_dados ->> 'cor', '') !~ '^#[0-9A-Fa-f]{6}$' then
            raise exception 'Cor deve ser #RRGGBB' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('cor', p_dados ->> 'cor');
    end if;
    if p_dados ? 'icone' then
        v_saida := v_saida || jsonb_build_object('icone', nullif(left(btrim(coalesce(p_dados ->> 'icone', '')), 50), ''));
    end if;
    if p_dados ? 'ativo' then
        if jsonb_typeof(p_dados -> 'ativo') <> 'boolean' then
            raise exception 'Ativo deve ser verdadeiro ou falso' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('ativo', p_dados -> 'ativo');
    end if;
    return v_saida;
end
$$;

-- Nome unico (sem diferenciar maiusculas) e nomes sistemicos reservados. Interna.
create function financeiro.validar_nome_categoria(p_nome text, p_id integer)
    returns void
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_codigo text;
begin
    if exists (select 1 from public.categoria c
                where lower(c.nome) = lower(p_nome) and c.id is distinct from p_id) then
        raise exception '%', case when p_id is null then 'Ja existe uma categoria com este nome'
                                  else 'Ja existe outra categoria com este nome' end using errcode = '22023';
    end if;
    select s.codigo into v_codigo from financeiro.categorias_sistemicas_mobilidade() s
     where lower(s.nome) = lower(btrim(p_nome));
    if v_codigo is not null then
        raise exception 'Nome reservado para a categoria sistemica de Mobilidade (%)', v_codigo
            using errcode = '22023', hint = 'NOME_SISTEMICO';
    end if;
end
$$;

create function financeiro.criar_categoria(p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_catalogo;
    v_d        jsonb;
    v_cat      public.categoria;
    v_resultado jsonb;
begin
    perform financeiro.exigir_escrita_catalogo();
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    select * into v_anterior from financeiro.operacao_catalogo o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.operacao <> 'criar_categoria' then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    v_d := financeiro.ler_dados_categoria(p_dados, false);
    perform financeiro.validar_nome_categoria(v_d ->> 'nome', null);
    insert into public.categoria (perfil_financeiro_id, nome, descricao, cor, icone, ativo, sistemica, bloquear_edicao,
                                  bloquear_exclusao, criado_em)
    values (null, v_d ->> 'nome', v_d ->> 'descricao', coalesce(v_d ->> 'cor', '#6c757d'), v_d ->> 'icone',
            coalesce((v_d ->> 'ativo')::boolean, true), false, false, false, now() at time zone 'utc')
    returning * into v_cat;
    v_resultado := jsonb_build_object('categoria_id', v_cat.id, 'nome', v_cat.nome);
    insert into financeiro.operacao_catalogo (chave, user_id, operacao, resultado)
    values (p_chave, (select auth.uid()), 'criar_categoria', v_resultado);
    return v_resultado;
end
$$;

create function financeiro.editar_categoria(p_categoria_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_cat public.categoria;
    v_d   jsonb;
begin
    perform financeiro.exigir_escrita_catalogo();
    select * into v_cat from public.categoria c where c.id = p_categoria_id for update;
    if not found then
        raise exception 'Categoria nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    v_d := financeiro.ler_dados_categoria(p_dados, true);
    if coalesce(v_cat.sistemica, false) or coalesce(v_cat.bloquear_edicao, false) then
        raise exception 'Esta categoria e sistemica e nao pode ser editada.' using errcode = 'P0001', hint = 'SISTEMICA';
    end if;
    if v_d ? 'nome' then
        perform financeiro.validar_nome_categoria(v_d ->> 'nome', p_categoria_id);
    end if;
    update public.categoria c
       set nome = coalesce(v_d ->> 'nome', c.nome),
           descricao = case when v_d ? 'descricao' then v_d ->> 'descricao' else c.descricao end,
           cor = coalesce(v_d ->> 'cor', c.cor),
           icone = case when v_d ? 'icone' then v_d ->> 'icone' else c.icone end,
           ativo = coalesce((v_d ->> 'ativo')::boolean, c.ativo)
     where c.id = p_categoria_id
    returning * into v_cat;
    return jsonb_build_object('categoria_id', v_cat.id, 'nome', v_cat.nome, 'ativo', v_cat.ativo);
end
$$;

-- Registros de outros modulos que apontam para a categoria (todas as chaves estrangeiras, menos as palavras-chave,
-- que sao da propria categoria). Interna.
create function financeiro.vinculos_da_categoria(p_categoria_id integer)
    returns text
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_fk     record;
    v_achou  boolean;
    v_lista  text[] := '{}';
begin
    for v_fk in
        select n.nspname as esquema, t.relname as tabela, a.attname as coluna
          from pg_constraint k
          join pg_class t on t.oid = k.conrelid
          join pg_namespace n on n.oid = t.relnamespace
          join pg_attribute a on a.attrelid = k.conrelid and a.attnum = k.conkey[1]
         where k.contype = 'f' and k.confrelid = 'public.categoria'::regclass and cardinality(k.conkey) = 1
           and k.conrelid <> 'public.categoria_palavra_chave'::regclass
         order by 2, 3
    loop
        execute format('select exists (select 1 from %I.%I where %I = $1)', v_fk.esquema, v_fk.tabela, v_fk.coluna)
           into v_achou using p_categoria_id;
        if v_achou then
            v_lista := v_lista || (v_fk.tabela || '.' || v_fk.coluna);
        end if;
    end loop;
    return nullif(array_to_string(v_lista, ', '), '');
end
$$;

-- Exclusao segura: sistemica nunca; com qualquer vinculo, recusa (inativar continua possivel). Sai com as
-- palavras-chave dela.
create function financeiro.excluir_categoria(p_categoria_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_cat     public.categoria;
    v_vinculo text;
begin
    perform financeiro.exigir_escrita_catalogo();
    select * into v_cat from public.categoria c where c.id = p_categoria_id for update;
    if not found then
        raise exception 'Categoria nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if coalesce(v_cat.sistemica, false) or coalesce(v_cat.bloquear_exclusao, false) then
        raise exception 'Esta categoria e sistemica e nao pode ser excluida.' using errcode = 'P0001', hint = 'SISTEMICA';
    end if;
    v_vinculo := financeiro.vinculos_da_categoria(p_categoria_id);
    if v_vinculo is not null then
        raise exception 'Nao e possivel excluir categoria com registros vinculados (%). Inative-a.', v_vinculo
            using errcode = 'P0001', hint = 'COM_VINCULOS';
    end if;
    begin
        delete from public.categoria_palavra_chave p where p.categoria_id = p_categoria_id;
        delete from public.categoria c where c.id = p_categoria_id;
    exception when foreign_key_violation then
        raise exception 'Nao e possivel excluir categoria com registros vinculados. Inative-a.'
            using errcode = 'P0001', hint = 'COM_VINCULOS';
    end;
    return jsonb_build_object('categoria_id', p_categoria_id, 'excluida', true);
end
$$;

-- Palavra-chave: normalizada como CategoriaPalavraChaveService.normalizar_palavra.
create function financeiro.criar_palavra_chave(p_categoria_id integer, p_palavra text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_palavra text := regexp_replace(btrim(lower(coalesce(p_palavra, ''))), '\s+', ' ', 'g');
    v_reg     public.categoria_palavra_chave;
begin
    perform financeiro.exigir_escrita_catalogo();
    perform 1 from public.categoria c where c.id = p_categoria_id for update;
    if not found then
        raise exception 'Categoria de Despesa nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    if v_palavra = '' then
        raise exception 'Palavra-chave e obrigatoria' using errcode = '22023';
    end if;
    if length(v_palavra) > 120 then
        raise exception 'Palavra-chave ate 120 caracteres' using errcode = '22023';
    end if;
    select * into v_reg from public.categoria_palavra_chave p
     where p.categoria_id = p_categoria_id and p.palavra = v_palavra for update;
    if found and v_reg.ativo then
        raise exception 'Palavra-chave ja cadastrada para esta categoria' using errcode = '22023';
    end if;
    if found then
        update public.categoria_palavra_chave set ativo = true, updated_at = now() at time zone 'utc'
         where id = v_reg.id returning * into v_reg;
        return jsonb_build_object('id', v_reg.id, 'categoria_id', p_categoria_id, 'palavra', v_palavra, 'ativo', true,
                                  'created', false);
    end if;
    insert into public.categoria_palavra_chave (categoria_id, palavra, ativo, created_at, updated_at)
    values (p_categoria_id, v_palavra, true, now() at time zone 'utc', now() at time zone 'utc')
    returning * into v_reg;
    return jsonb_build_object('id', v_reg.id, 'categoria_id', p_categoria_id, 'palavra', v_palavra, 'ativo', true,
                              'created', true);
end
$$;

create function financeiro.remover_palavra_chave(p_categoria_id integer, p_palavra_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_reg public.categoria_palavra_chave;
begin
    perform financeiro.exigir_escrita_catalogo();
    update public.categoria_palavra_chave p set ativo = false, updated_at = now() at time zone 'utc'
     where p.id = p_palavra_id and p.categoria_id = p_categoria_id
    returning * into v_reg;
    if not found then
        raise exception 'Palavra-chave nao encontrada' using errcode = 'P0001', hint = 'NAO_ENCONTRADA';
    end if;
    return jsonb_build_object('id', v_reg.id, 'categoria_id', p_categoria_id, 'palavra', v_reg.palavra, 'ativo', false);
end
$$;

revoke execute on function financeiro.categorias_sistemicas_mobilidade() from public, anon, authenticated;
revoke execute on function financeiro.definir_escritor_catalogo(text, text, text) from public, anon, authenticated;
revoke execute on function financeiro.definir_gestor_catalogo(uuid, boolean, text, text) from public, anon, authenticated;
revoke execute on function financeiro.exigir_escrita_catalogo() from public, anon, authenticated;
revoke execute on function financeiro.ler_dados_categoria(jsonb, boolean) from public, anon, authenticated;
revoke execute on function financeiro.validar_nome_categoria(text, integer) from public, anon, authenticated;
revoke execute on function financeiro.vinculos_da_categoria(integer) from public, anon, authenticated;
revoke execute on function financeiro.situacao_catalogo_categorias() from public, anon;
revoke execute on function financeiro.criar_categoria(jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_categoria(integer, jsonb) from public, anon;
revoke execute on function financeiro.excluir_categoria(integer) from public, anon;
revoke execute on function financeiro.criar_palavra_chave(integer, text) from public, anon;
revoke execute on function financeiro.remover_palavra_chave(integer, integer) from public, anon;
grant execute on function financeiro.situacao_catalogo_categorias() to authenticated;
grant execute on function financeiro.criar_categoria(jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_categoria(integer, jsonb) to authenticated;
grant execute on function financeiro.excluir_categoria(integer) to authenticated;
grant execute on function financeiro.criar_palavra_chave(integer, text) to authenticated;
grant execute on function financeiro.remover_palavra_chave(integer, integer) to authenticated;

-- plano_recorrencia: texto de 20261108090000 + os trechos marcados.
create or replace function financeiro.plano_recorrencia(p_perfil_id integer, p_mes date)
    returns setof financeiro.linha_plano
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes     date := date_trunc('month', p_mes::timestamp)::date;
    v_limite  date := (date_trunc('month', p_mes::timestamp) + interval '1 month')::date;
    v_ns      constant uuid := '7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c';  -- namespace do Flask
    v_pessoal boolean;
    v_consolidada date;  -- FIN-CARTOES-D6-INTEGRIDADE-1
    v_item    record;
    v_cartao  record;
    v_reg     record;
    v_linha   financeiro.linha_plano;
    v_comp    date;
    v_passo   interval;
    v_dia     integer;
    v_motivo  text;
    v_ccs     integer[];
    v_qtd     integer;
    v_id      integer;
begin
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');

    -- 1) Recorrencias: conta (boleto, debito, pix...) ou compra no cartao.
    for v_item in
        select i.*
          from public.item_despesa i
         where (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))
           and coalesce(i.recorrente, false)
           -- FIN-FIDELIDADE-CARTOES-2 (R4): o proprio cartao (Agregador) e gravado como recorrente (como no Flask), mas a
           -- fatura dele e gerada pela parte de cartoes; ele nao e uma recorrencia que produz despesa.
           and i.tipo is distinct from 'Agregador'
         order by i.id
    loop
        v_linha := null;
        v_linha.natureza := case when v_item.meio_pagamento = 'cartao' then 'LANCAMENTO_CARTAO' else 'CONTA' end;
        v_linha.item_despesa_id := v_item.id;
        v_linha.nome := v_item.nome;
        v_linha.valor := v_item.valor;
        v_linha.perfil_destino := v_item.perfil_financeiro_id;
        v_linha.observacoes := coalesce(v_item.descricao, '');
        v_motivo := null;

        if not coalesce(v_item.ativo, true) then
            v_linha.situacao := 'INATIVA';
            v_linha.motivo := 'Recorrencia inativa: nao gera novos lancamentos';
            return next v_linha;
            continue;
        end if;

        if v_item.tipo = 'Agregador' then
            v_motivo := 'Cartao marcado como recorrencia';
        elsif v_item.data_vencimento is null then
            v_motivo := 'Sem data de vencimento';
        elsif coalesce(v_item.tipo_recorrencia, 'mensal') not in ('mensal', 'anual')
              and financeiro.semanas_da_recorrencia(v_item.tipo_recorrencia) is null then  -- FIN-CATEGORIAS-RECORRENCIAS-2
            v_motivo := 'Tipo de recorrencia fora do escopo: ' || v_item.tipo_recorrencia;
        elsif v_linha.natureza = 'LANCAMENTO_CARTAO'
              and financeiro.semanas_da_recorrencia(v_item.tipo_recorrencia) is not null then  -- FIN-CATEGORIAS-RECORRENCIAS-2
            v_motivo := 'Recorrencia semanal no cartao: o sistema original tambem nao a lanca (so mensal e anual)';
        elsif v_item.valor is null or v_item.valor < 0 then
            v_motivo := 'Sem valor valido';
        elsif v_linha.natureza = 'LANCAMENTO_CARTAO' then
            if v_item.cartao_id is null then
                v_motivo := 'Sem cartao';
            elsif v_item.categoria_id is null then
                v_motivo := 'Sem categoria';
            else
                select c.* into v_cartao
                  from public.item_despesa c
                 where c.id = v_item.cartao_id
                   and c.tipo = 'Agregador'
                   and coalesce(c.ativo, true)
                   and (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal));
                if not found then
                    v_motivo := 'Cartao inexistente, inativo ou de outro perfil';
                end if;
            end if;

            -- Categoria do cartao como CategoriaCartaoService.resolver_categoria_cartao_para_lancamento.
            if v_motivo is null then
                v_linha.cartao_id := v_item.cartao_id;
                v_linha.categoria_id := v_item.categoria_id;
                if v_item.categoria_cartao_id is not null then
                    if exists (select 1 from public.categoria_cartao cc
                                where cc.id = v_item.categoria_cartao_id
                                  and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal))) then
                        v_linha.categoria_cartao_id := v_item.categoria_cartao_id;
                    else
                        v_motivo := 'Categoria do cartao nao encontrada';
                    end if;
                else
                    select array_agg(v.categoria_cartao_id order by v.id) into v_ccs
                      from public.categoria_cartao_despesa v
                      join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
                     where v.categoria_id = v_item.categoria_id
                       and v.ativo and cc.ativo
                       and (v.perfil_financeiro_id = p_perfil_id or (v.perfil_financeiro_id is null and v_pessoal))
                       and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal));
                    if cardinality(v_ccs) > 1 then
                        v_motivo := 'Categoria de despesa com mais de uma categoria do cartao ativa';
                    elsif cardinality(v_ccs) = 1 and exists (
                        select 1 from public.cartao_categoria_limite lim
                          join public.categoria_cartao cc on cc.id = lim.categoria_cartao_id
                         where lim.cartao_id = v_item.cartao_id
                           and lim.categoria_cartao_id = v_ccs[1]
                           and lim.ativo and cc.ativo
                           and (lim.perfil_financeiro_id = p_perfil_id or (lim.perfil_financeiro_id is null and v_pessoal))
                           and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal))) then
                        v_linha.categoria_cartao_id := v_ccs[1];
                    end if;
                end if;
            end if;
        else
            v_linha.conta_bancaria_id := v_item.conta_bancaria_id;
            v_linha.debito_automatico := coalesce(v_item.meio_pagamento = 'debito_automatico', false);
        end if;

        if v_motivo is not null then
            v_linha.situacao := 'REJEITADA';
            v_linha.motivo := v_motivo;
            v_linha.cartao_id := null;
            v_linha.categoria_id := null;
            v_linha.categoria_cartao_id := null;
            return next v_linha;
            continue;
        end if;

        -- FIN-CATEGORIAS-RECORRENCIAS-2 (R1): semanal e a cada 2 semanas, uma linha por ocorrencia.
        if financeiro.semanas_da_recorrencia(v_item.tipo_recorrencia) is not null then
            return query select * from financeiro.ocorrencias_semanais(v_linha, v_item.tipo_recorrencia,
                                                                       v_item.data_vencimento, v_limite);
            continue;
        end if;

        v_dia := extract(day from v_item.data_vencimento)::integer;
        v_passo := case when coalesce(v_item.tipo_recorrencia, 'mensal') = 'anual' then interval '1 year' else interval '1 month' end;
        v_comp := date_trunc('month', v_item.data_vencimento::timestamp)::date;
        while v_comp <= v_limite loop
            v_linha.competencia := v_comp;
            v_linha.data_vencimento := financeiro.dia_contratual(v_comp, v_dia);
            v_linha.registro_id := null;
            v_linha.motivo := null;
            v_linha.compra_id := case when v_linha.natureza = 'LANCAMENTO_CARTAO' then
                extensions.uuid_generate_v5(v_ns, format('%s-%s', v_item.id, to_char(v_comp, 'YYYY-MM-DD')))::text end;

            select r.* into v_reg
              from financeiro.recorrencia_competencia r
             where r.item_despesa_id = v_item.id and r.natureza = v_linha.natureza and r.competencia = v_comp;
            if found then
                if v_reg.situacao = 'GERADA' and (
                       exists (select 1 from public.conta c where c.id = v_reg.conta_id)
                    or exists (select 1 from public.lancamento_agregado l where l.id = v_reg.lancamento_id)) then
                    v_linha.situacao := 'EXISTENTE';
                    v_linha.registro_id := coalesce(v_reg.conta_id, v_reg.lancamento_id);
                else
                    v_linha.situacao := 'DISPENSADA';
                    v_linha.motivo := case when v_reg.situacao = 'DISPENSADA'
                                           then coalesce(v_reg.motivo, 'Competencia dispensada')
                                           else 'Registro gerado foi removido; nao sera recriado' end;
                end if;
            else
                -- Reconhece o que o Flask (ou outro caminho) ja gravou, sem depender da data.
                if v_linha.natureza = 'CONTA' then
                    select c.id into v_id
                      from public.conta c
                     where c.item_despesa_id = v_item.id
                       and coalesce(c.is_fatura_cartao, false) = false
                       and (date_trunc('month', c.mes_referencia) = v_comp or date_trunc('month', c.data_vencimento) = v_comp)
                     order by c.id
                     limit 1;
                else
                    select l.id into v_id
                      from public.lancamento_agregado l
                     where l.compra_id = v_linha.compra_id
                        -- FIN-FATURA-INTEGRIDADE-1: pelo mes so os antigos, sem compra_id (uma compra de outra
                        -- competencia desviada para este mes por fatura paga nao e a deste mes).
                        or (l.item_despesa_id = v_item.id and l.mes_fatura = v_comp and l.is_recorrente
                            and l.compra_id is null)
                     order by l.id
                     limit 1;
                end if;
                v_linha.situacao := case when v_id is null then 'A_GERAR' else 'EXISTENTE' end;
                -- FIN-CARTOES-D6-INTEGRIDADE-1: a geracao automatica nao e confirmacao do usuario (D6) e nao muda a
                -- competencia (D5): compra recorrente cujo destino e fatura consolidada nao e gerada (nem em silencio,
                -- nem em outro mes). Fica REJEITADA, com o motivo na previa, ate o usuario lancar pela compra, com a
                -- confirmacao. Nada e gravado; a proxima previa reavalia (idempotente).
                if v_linha.natureza = 'LANCAMENTO_CARTAO' and v_linha.situacao = 'A_GERAR' then
                    v_consolidada := financeiro.fatura_consolidada_no_destino(v_linha.cartao_id, v_comp);
                    if v_consolidada is not null then
                        v_linha.situacao := 'REJEITADA';
                        v_linha.motivo := 'Fatura de ' || to_char(v_consolidada, 'MM/YYYY')
                            || ' consolidada: a compra recorrente nao entra sem confirmacao (lance-a pela compra no cartao)';
                    end if;
                end if;
                v_linha.registro_id := v_id;
            end if;
            return next v_linha;
            v_comp := (v_comp + v_passo)::date;
        end loop;
    end loop;

    -- 2) Faturas do mes e do seguinte para cada cartao ativo do perfil.
    for v_cartao in
        select c.id, c.nome, c.perfil_financeiro_id, cfg.dia_vencimento
          from public.item_despesa c
          left join public.config_agregador cfg on cfg.item_despesa_id = c.id
         where (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal))
           and c.tipo = 'Agregador'
           and coalesce(c.ativo, true)
         order by c.id
    loop
        foreach v_comp in array array[v_mes, v_limite] loop
            v_linha := null;
            v_linha.natureza := 'FATURA';
            v_linha.item_despesa_id := v_cartao.id;
            v_linha.nome := v_cartao.nome;
            v_linha.competencia := v_comp;
            v_linha.perfil_destino := v_cartao.perfil_financeiro_id;
            v_linha.cartao_id := v_cartao.id;

            select c.id into v_id
              from public.conta c
             where c.item_despesa_id = v_cartao.id
               and c.is_fatura_cartao
               and date_trunc('month', c.cartao_competencia) = v_comp
             order by c.id
             limit 1;
            if v_id is not null then
                v_linha.situacao := 'EXISTENTE';
                v_linha.registro_id := v_id;
            elsif v_cartao.dia_vencimento is null or v_cartao.dia_vencimento not between 1 and 31 then
                v_linha.situacao := 'REJEITADA';
                v_linha.motivo := 'Cartao sem dia de vencimento configurado';
            else
                -- Planejado como CartaoService.calcular_planejado: limites ativos do cartao
                -- no perfil; sem limites, orcamento legado vigente por item agregado.
                select count(*), coalesce(sum(lim.limite_mensal), 0) into v_qtd, v_linha.valor
                  from public.cartao_categoria_limite lim
                 where lim.cartao_id = v_cartao.id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo;
                if v_qtd = 0 then
                    select coalesce(sum(o.valor_teto), 0) into v_linha.valor
                      from public.item_agregado ia
                      cross join lateral (
                          select oa.valor_teto
                            from public.orcamento_agregado oa
                           where oa.item_agregado_id = ia.id
                             and oa.ativo
                             and oa.vigencia_inicio <= v_comp
                             and (oa.vigencia_fim is null or oa.vigencia_fim >= v_comp)
                           order by oa.id
                           limit 1
                      ) o
                     where ia.item_despesa_id = v_cartao.id;
                end if;
                v_linha.situacao := 'A_GERAR';
                v_linha.data_vencimento := financeiro.dia_contratual(v_comp, v_cartao.dia_vencimento);
            end if;
            return next v_linha;
        end loop;
    end loop;
end
$$;

-- gerar_mes_interno: texto de 20261030090000 + os trechos marcados.
create or replace function financeiro.gerar_mes_interno(p_perfil_id integer, p_mes date, p_total_previsto integer,
                                                        p_dispensar jsonb default '[]'::jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_mes        date;
    v_linhas     financeiro.linha_plano[];
    v_linha      financeiro.linha_plano;
    v_disp       record;
    v_a_gerar    integer;
    v_exec       bigint;
    v_id         integer;
    v_contas     integer := 0;
    v_lancs      integer := 0;
    v_faturas    integer := 0;
    v_dispensas  integer := 0;
    v_destino    date;  -- FIN-FATURA-INTEGRIDADE-1: mes da compra recorrente (desvia de fatura paga)
    v_corrida    integer := 0;  -- faturas criadas ao mesmo tempo por outro caminho
    v_registros  jsonb := '[]'::jsonb;
    v_resumo     jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null or p_total_previsto is null or p_total_previsto < 0 then
        raise exception 'Mes e total previsto sao obrigatorios' using errcode = '22023';
    end if;
    p_dispensar := coalesce(p_dispensar, '[]'::jsonb);
    if jsonb_typeof(p_dispensar) <> 'array' then
        raise exception 'Dispensas devem ser uma lista' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes::timestamp)::date;

    -- Uma geracao por perfil de cada vez (abas ou cliques concorrentes).
    perform pg_advisory_xact_lock(20261023, p_perfil_id);

    select coalesce(array_agg(p order by p.competencia, p.natureza, p.item_despesa_id), '{}')
      into v_linhas
      from financeiro.plano_recorrencia(p_perfil_id, v_mes) p;
    select count(*) into v_a_gerar from unnest(v_linhas) l where l.situacao = 'A_GERAR';
    -- FIN-CARTOES-RECORRENCIA-PENDENCIA-1: a tentativa registra as compras recorrentes rejeitadas por fatura consolidada
    -- (uma ocorrencia por recorrencia + competencia; se a geracao falhar, o registro e desfeito junto).
    perform financeiro.registrar_rejeicoes_consolidadas(v_linhas, 'NOVO_APP');

    if v_a_gerar = 0 and jsonb_array_length(p_dispensar) = 0 then
        return jsonb_build_object('execucao_id', null, 'mes', v_mes,
            'criadas', jsonb_build_object('contas', 0, 'lancamentos', 0, 'faturas', 0, 'total', 0),
            'existentes', (select count(*) from unnest(v_linhas) l where l.situacao = 'EXISTENTE'),
            'dispensadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'DISPENSADA'),
            'dispensadas_agora', 0,
            'rejeitadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'REJEITADA'),
            'registros', '[]'::jsonb);
    end if;
    if v_a_gerar <> p_total_previsto then
        raise exception 'A previa mudou desde a confirmacao (previstos %, agora %). Revise e confirme de novo.',
            p_total_previsto, v_a_gerar;
    end if;
    if v_a_gerar > 500 then
        raise exception 'Geracao excede o limite de 500 registros (%).', v_a_gerar;
    end if;

    -- FIN-FATURA-INTEGRIDADE-1: ordem global de travas (cartao -> faturas): os cartoes das linhas a
    -- gerar ficam travados, em ordem de id, antes de qualquer fatura.
    perform 1 from public.item_despesa i
     where i.id in (select l.cartao_id from unnest(v_linhas) l where l.situacao = 'A_GERAR' and l.cartao_id is not null)
     order by i.id
       for update;

    insert into financeiro.geracao_execucao (perfil_financeiro_id, mes, user_id, resumo)
    values (p_perfil_id, v_mes, (select auth.uid()), '{}'::jsonb)
    returning id into v_exec;

    for v_disp in
        select d.natureza, d.item_id, date_trunc('month', d.competencia::timestamp)::date as competencia, d.motivo,
               d.data_vencimento  -- FIN-CATEGORIAS-RECORRENCIAS-2: a ocorrencia, na semanal
          from jsonb_to_recordset(p_dispensar) as d(natureza text, item_id integer, competencia date, motivo text,
                                                    data_vencimento date)
    loop
        if not exists (select 1 from unnest(v_linhas) l
                        where l.situacao = 'A_GERAR' and l.natureza in ('CONTA', 'LANCAMENTO_CARTAO')
                          and l.natureza = v_disp.natureza and l.item_despesa_id = v_disp.item_id
                          and l.competencia = v_disp.competencia
                          and (v_disp.data_vencimento is null or l.data_vencimento = v_disp.data_vencimento)) then
            raise exception 'Dispensa invalida: so competencias a gerar de recorrencias podem ser dispensadas'
                using errcode = '22023';
        end if;
        if financeiro.semanas_do_item(v_disp.item_id) is not null then  -- FIN-CATEGORIAS-RECORRENCIAS-2: dispensa so a ocorrencia
            if v_disp.data_vencimento is null then
                raise exception 'Dispensa de recorrencia semanal exige a data da ocorrencia' using errcode = '22023';
            end if;
            insert into financeiro.recorrencia_ocorrencia
                (item_despesa_id, data_ocorrencia, situacao, execucao_id, motivo, user_id)
            values (v_disp.item_id, v_disp.data_vencimento, 'DISPENSADA', v_exec,
                    coalesce(left(nullif(btrim(v_disp.motivo), ''), 200), 'Dispensada pelo usuario'), (select auth.uid()));
        else
        insert into financeiro.recorrencia_competencia
            (item_despesa_id, natureza, competencia, situacao, execucao_id, motivo, user_id)
        values (v_disp.item_id, v_disp.natureza, v_disp.competencia, 'DISPENSADA', v_exec,
                coalesce(left(nullif(btrim(v_disp.motivo), ''), 200), 'Dispensada pelo usuario'), (select auth.uid()));
        end if;
        v_dispensas := v_dispensas + 1;
    end loop;

    foreach v_linha in array v_linhas loop
        continue when v_linha.situacao <> 'A_GERAR';
        continue when financeiro.semanas_do_item(v_linha.item_despesa_id) is null  -- FIN-CATEGORIAS-RECORRENCIAS-2
                  and exists (select 1 from financeiro.recorrencia_competencia r
                               where r.item_despesa_id = v_linha.item_despesa_id and r.natureza = v_linha.natureza
                                 and r.competencia = v_linha.competencia and r.situacao = 'DISPENSADA');
        continue when v_linha.natureza = 'CONTA' and financeiro.semanas_do_item(v_linha.item_despesa_id) is not null
                  and exists (select 1 from financeiro.recorrencia_ocorrencia o
                               where o.item_despesa_id = v_linha.item_despesa_id
                                 and o.data_ocorrencia = v_linha.data_vencimento and o.situacao = 'DISPENSADA');
        if v_linha.natureza = 'CONTA' then
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor,
                                      data_vencimento, status_pagamento, debito_automatico, conta_bancaria_id,
                                      observacoes, is_fatura_cartao, estouro_orcamento, status_fatura, criado_em)
            values (v_linha.perfil_destino, v_linha.item_despesa_id, v_linha.competencia, v_linha.nome, v_linha.valor,
                    v_linha.data_vencimento, 'Pendente', v_linha.debito_automatico, v_linha.conta_bancaria_id,
                    v_linha.observacoes, false, false, 'ABERTA', now() at time zone 'utc')
            returning id into v_id;
            if financeiro.semanas_do_item(v_linha.item_despesa_id) is not null then  -- FIN-CATEGORIAS-RECORRENCIAS-2
                insert into financeiro.recorrencia_ocorrencia
                    (item_despesa_id, data_ocorrencia, situacao, conta_id, execucao_id, user_id)
                values (v_linha.item_despesa_id, v_linha.data_vencimento, 'GERADA', v_id, v_exec, (select auth.uid()));
            else
            insert into financeiro.recorrencia_competencia
                (item_despesa_id, natureza, competencia, situacao, conta_id, execucao_id, user_id)
            values (v_linha.item_despesa_id, 'CONTA', v_linha.competencia, 'GERADA', v_id, v_exec, (select auth.uid()));
            end if;
            v_contas := v_contas + 1;
        elsif v_linha.natureza = 'LANCAMENTO_CARTAO' then
            -- FIN-FATURA-INTEGRIDADE-1: fatura paga nao recebe a compra recorrente; ela vai para a
            -- proxima fatura nao paga, com a competencia original registrada. A identidade continua a
            -- da competencia (recorrencia_competencia e compra_id), entao ela nao e gerada de novo.
            v_destino := financeiro.fatura_elegivel_existente(v_linha.cartao_id, v_linha.competencia);
            -- FIN-CARTOES-D6-INTEGRIDADE-1: a fatura de destino (travada acima) foi consolidada depois da previa:
            -- nada entra em silencio. Erro controlado; a geracao inteira e desfeita e a nova previa mostra o motivo.
            if exists (select 1 from public.conta c
                        where c.id = financeiro.fatura_do_mes(v_linha.cartao_id, v_destino) and c.status_fatura = 'FECHADA') then
                raise exception 'A fatura de % foi consolidada depois da previa: a compra recorrente "%" nao entra sem confirmacao. Revise e confirme de novo.',
                    to_char(v_destino, 'MM/YYYY'), v_linha.nome using errcode = 'P0001', hint = 'CONSOLIDADA';
            end if;
            insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, item_agregado_id, categoria_cartao_id,
                                                    categoria_id, descricao, valor, data_compra, mes_fatura,
                                                    numero_parcela, total_parcelas, observacoes, is_recorrente,
                                                    item_despesa_id, compra_id, is_importado, criado_em,
                                                    mes_fatura_original)
            values (v_linha.perfil_destino, v_linha.cartao_id, null, v_linha.categoria_cartao_id,
                    v_linha.categoria_id, v_linha.nome, v_linha.valor, v_linha.data_vencimento, v_destino,
                    1, 1, v_linha.observacoes, true,
                    v_linha.item_despesa_id, v_linha.compra_id, false, now() at time zone 'utc',
                    nullif(v_linha.competencia, v_destino))
            returning id into v_id;
            insert into financeiro.recorrencia_competencia
                (item_despesa_id, natureza, competencia, situacao, lancamento_id, execucao_id, user_id)
            values (v_linha.item_despesa_id, 'LANCAMENTO_CARTAO', v_linha.competencia, 'GERADA', v_id, v_exec,
                    (select auth.uid()));
            v_lancs := v_lancs + 1;
        else
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor,
                                      valor_planejado, valor_executado, data_vencimento, status_pagamento,
                                      is_fatura_cartao, cartao_competencia, estouro_orcamento, debito_automatico,
                                      status_fatura, criado_em)
            values (v_linha.perfil_destino, v_linha.item_despesa_id, v_linha.competencia,
                    'Fatura ' || v_linha.nome || ' - ' || to_char(v_linha.competencia, 'MM/YYYY'),
                    v_linha.valor, v_linha.valor, 0, v_linha.data_vencimento, 'Pendente',
                    true, v_linha.competencia, false, false, 'ABERTA', now() at time zone 'utc')
            on conflict (item_despesa_id, cartao_competencia) where is_fatura_cartao do nothing
            returning id into v_id;
            -- FIN-FATURA-UNICA-1: outra transacao (ex.: compra no Flask) criou a mesma fatura
            -- depois do plano; o indice unico decidiu e a existente e reconhecida.
            if v_id is null then
                v_corrida := v_corrida + 1;
                continue;
            end if;
            v_faturas := v_faturas + 1;
        end if;
        v_registros := v_registros || jsonb_build_object('natureza', v_linha.natureza, 'item_id', v_linha.item_despesa_id,
                                                         'competencia', v_linha.competencia, 'registro_id', v_id);
    end loop;

    v_resumo := jsonb_build_object(
        'execucao_id', v_exec,
        'mes', v_mes,
        'criadas', jsonb_build_object('contas', v_contas, 'lancamentos', v_lancs, 'faturas', v_faturas,
                                      'total', v_contas + v_lancs + v_faturas),
        'existentes', (select count(*) from unnest(v_linhas) l where l.situacao = 'EXISTENTE') + v_corrida,
        'dispensadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'DISPENSADA') + v_dispensas,
        'dispensadas_agora', v_dispensas,
        'rejeitadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'REJEITADA'),
        'rejeicoes', coalesce((select jsonb_agg(jsonb_build_object('item_id', l.item_despesa_id, 'nome', l.nome,
                                                                    'natureza', l.natureza, 'competencia', l.competencia,
                                                                    'motivo', l.motivo))
                                 from unnest(v_linhas) l where l.situacao = 'REJEITADA'), '[]'::jsonb),
        'registros', v_registros);
    update financeiro.geracao_execucao set resumo = v_resumo where id = v_exec;
    return v_resumo;
end
$$;

-- ler_dados_despesa: texto de 20261026090000 + os trechos marcados.
create or replace function financeiro.ler_dados_despesa(p_dados jsonb, p_perfil_id integer, p_parcial boolean)
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
        -- FIN-CATEGORIAS-RECORRENCIAS-2: semanal_N_D (semanal ou a cada 2 semanas, com o dia da semana), como grava o Flask.
        if p_dados ->> 'tipo_recorrencia' not in ('mensal', 'anual')
           and coalesce(p_dados ->> 'tipo_recorrencia', '') !~ '^semanal_[12]_[0-6]$' then
            raise exception 'Recorrencia deve ser mensal ou anual, semanal ou a cada 2 semanas (com o dia da semana)'
                using errcode = '22023';
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

-- excluir_despesa: texto de 20261124090000 + os trechos marcados.
create or replace function financeiro.excluir_despesa(p_perfil_id integer, p_conta_id integer, p_versao text)
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
$$;

-- recorrencias_do_perfil: texto de 20261103090000 + os trechos marcados.
create or replace function financeiro.recorrencias_do_perfil(p_perfil_id integer)
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
                   -- FIN-CATEGORIAS-RECORRENCIAS-2: semanal como _proximo_vencimento do Flask (vencimento levado ao dia da semana).
                   when financeiro.semanas_da_recorrencia(i.tipo_recorrencia) is not null
                       then financeiro.proxima_ocorrencia_semanal(i.tipo_recorrencia, i.data_vencimento, v_hoje)
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

-- receita_orcamento_flask: texto de 20261119090000 + os trechos marcados.
create or replace function financeiro.receita_orcamento_flask(p_o public.receita_orcamento)
    returns jsonb
    language sql
    stable
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_o.id, 'perfil_financeiro_id', p_o.perfil_financeiro_id, 'item_receita_id', p_o.item_receita_id,
        'mes_referencia', to_char(p_o.mes_referencia, 'YYYY-MM-DD'), 'valor_esperado', p_o.valor_esperado,
        'periodicidade', p_o.periodicidade, 'observacoes', p_o.observacoes,
        -- FIN-CATEGORIAS-RECORRENCIAS-2: data prevista (FIN-RECEITAS-DATA-REAL-1) explicita e efetiva (explicita ou o dia da fonte).
        'data_prevista', to_char(p_o.data_prevista, 'YYYY-MM-DD'),
        'data_prevista_efetiva', to_char(coalesce(p_o.data_prevista,
            (select financeiro.dia_contratual(p_o.mes_referencia, i.dia_previsto_pagamento)
               from public.item_receita i
              where i.id = p_o.item_receita_id and i.dia_previsto_pagamento between 1 and 31)), 'YYYY-MM-DD'))
$$;
