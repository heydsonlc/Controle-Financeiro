-- FIN-MVP-MOB-01: integridade financeira da Mobilidade e combustivel Flex. Gerada por scripts/gerar_migration_mobilidade_integridade.py
-- a partir do texto vigente de cada funcao. Nenhum valor financeiro muda; o unico preenchimento e o da identidade das
-- previstas existentes (obrigacao e periodo_referencia).
--
-- - Identidade da ocorrencia: obrigacao + periodo (mes do combustivel, ano de IPVA, seguro e licenciamento), com indice
--   unico. Mudar o mes do vencimento nao recria o periodo ja confirmado, e regerar preserva o id da prevista.
-- - Com a recorrencia de combustivel ativa, ela e a fonte unica: as previsoes das competencias dela ficam SUPRIMIDA, a
--   confirmacao que criaria outra despesa e recusada e a recorrencia nao gera competencia ja coberta.
-- - Custo novo do veiculo: atualiza a recorrencia e as ocorrencias de meses futuros ainda abertas, nunca as pagas.
-- - Confirmar guarda o vinculo com a conta ou compra e, no combustivel, os parametros do momento.
-- - Veiculo SIMULADO fica fora do Dashboard, dos alertas e das saidas; confirmar com pagamento e recusado.
-- - Flex: autonomia e preco por combustivel, combustivel de referencia e custo MANUAL (padrao) ou CALCULADO.
-- - Abastecimentos: registro operacional com hodometro, litros calculados e vinculo opcional com compra ou conta ja existente.
--   Registrar nunca cria despesa. A leitura real manda na quilometragem; a estimativa so completa os dias depois dela.
-- - Troca de modalidade: despesas futuras da modalidade anterior sao decididas uma a uma (manter ou substituir), com
--   registro; a substituida fica preservada, fora dos indicadores. O mes corrente, o que foi pago e o que tem movimento nao mudam.
-- - Modalidade inativa fica fora do Dashboard, como o veiculo simulado. Veiculo em uso paralelo conta e mantem a recorrencia.

-- =====================================================================================================================
-- 1. Estrutura: so colunas opcionais. Veiculo existente continua MANUAL, sem nenhum valor alterado.
-- =====================================================================================================================
alter table public.veiculo
    add column autonomia_gasolina_km_l numeric(10, 2),
    add column autonomia_etanol_km_l   numeric(10, 2),
    add column preco_gasolina          numeric(10, 2),
    add column preco_etanol            numeric(10, 2),
    add column combustivel_referencia  character varying(10),
    add column km_mensal_estimado      numeric(10, 2),
    add column custo_combustivel_modo  character varying(10) not null default 'MANUAL',
    add column em_uso_paralelo         boolean not null default false,
    add constraint veiculo_em_uso_nao_simulado check (not em_uso_paralelo or status is distinct from 'SIMULADO'),
    add constraint veiculo_combustivel_referencia_valida check (combustivel_referencia in ('gasolina', 'etanol')),
    add constraint veiculo_custo_combustivel_modo_valido check (custo_combustivel_modo in ('MANUAL', 'CALCULADO'));
comment on column public.veiculo.custo_combustivel_modo is
    'FIN-MVP-MOB-01: MANUAL = vale o valor informado; CALCULADO = km / autonomia x preco, recalculado ao salvar. O padrao nunca muda um valor existente.';
comment on column public.veiculo.autonomia_km_l is
    'Autonomia em uso. No Flex, a do combustivel de referencia (FIN-MVP-MOB-01).';
comment on column public.veiculo.em_uso_paralelo is
    'FIN-MVP-MOB-01: veiculo real em uso junto do cenario financeiro. Na troca do cenario, a recorrencia dele continua e as previsoes seguem contando. Nao cria recorrencia.';

alter table public.despesa_prevista
    add column obrigacao          text,
    add column periodo_referencia date,
    add column conta_id           integer references public.conta (id) on delete set null,
    add column lancamento_id      integer references public.lancamento_agregado (id) on delete set null;
comment on column public.despesa_prevista.obrigacao is
    'FIN-MVP-MOB-01: identidade da ocorrencia com periodo_referencia (mes no combustivel, ano em IPVA, seguro e licenciamento).';
comment on column public.despesa_prevista.conta_id is
    'FIN-MVP-MOB-01: conta criada ao confirmar. Sem cascata: excluir a conta so limpa o vinculo.';
comment on column public.despesa_prevista.lancamento_id is
    'FIN-MVP-MOB-01: compra no cartao criada ao confirmar. Sem cascata: excluir a compra so limpa o vinculo.';

-- Periodo da obrigacao: o ano nas anuais; o mes no combustivel.
create function financeiro.mob_periodo(p_tipo text, p_data date)
    returns date
    language sql
    immutable
    set search_path = ''
as $$
    select case when p_tipo in ('IPVA', 'SEGURO', 'LICENCIAMENTO') then date_trunc('year', p_data::timestamp)::date
                else date_trunc('month', p_data::timestamp)::date end
$$;

-- As previstas existentes ganham a identidade; nenhum outro campo muda.
update public.despesa_prevista d
   set obrigacao = o.tipo, periodo_referencia = financeiro.mob_periodo(o.tipo, coalesce(d.data_original_prevista, d.data_prevista))
  from (select p.id, financeiro.mob_tipo_evento(p.metadata) as tipo from public.despesa_prevista p where p.origem_tipo = 'VEICULO') o
 where o.id = d.id and o.tipo in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO');

do $$
begin
    if exists (select 1 from public.despesa_prevista d where d.obrigacao is not null
                group by d.origem_tipo, d.origem_id, d.obrigacao, d.periodo_referencia having count(*) > 1) then
        raise exception 'Ha previstas repetidas para a mesma obrigacao e periodo: revise antes de aplicar. Nada foi alterado.';
    end if;
end
$$;

create unique index ux_despesa_prevista_obrigacao_periodo
    on public.despesa_prevista (origem_tipo, origem_id, obrigacao, periodo_referencia) where obrigacao is not null;

-- =====================================================================================================================
-- 1b. Abastecimentos: registro operacional do veiculo. Nao e despesa: registrar nunca cria conta nem compra; o vinculo com
-- a compra ou a conta correspondente e feito depois, sem tocar nelas.
-- =====================================================================================================================
create table financeiro.abastecimento (
    id                   integer        generated always as identity primary key,
    perfil_financeiro_id integer        not null references public.perfil_financeiro (id),
    veiculo_id           integer        not null references public.veiculo (id),
    data_abastecimento   date           not null,
    hodometro_km         numeric(10, 1) not null check (hodometro_km >= 0),
    combustivel          text           not null check (combustivel in ('gasolina', 'etanol', 'diesel', 'gnv', 'outro')),
    preco_litro          numeric(10, 3) not null check (preco_litro > 0),
    valor_total          numeric(12, 2) not null check (valor_total > 0),
    litros               numeric        generated always as (valor_total / preco_litro) stored,
    meio_pagamento       text           check (meio_pagamento in ('cartao', 'pix', 'debito', 'dinheiro', 'boleto', 'outro')),
    cartao_id            integer        references public.item_despesa (id) on delete set null,
    cartao_vinculado_id  integer        references financeiro.cartao_vinculado (id) on delete set null,
    estabelecimento      text           check (length(estabelecimento) <= 120),
    observacoes          text           check (length(observacoes) <= 500),
    lancamento_id        integer        references public.lancamento_agregado (id) on delete set null,
    conta_id             integer        references public.conta (id) on delete set null,
    anulado_em           timestamptz,
    anulado_por          uuid           references auth.users (id) on delete set null,
    user_id              uuid           references auth.users (id) on delete set null,
    criado_em            timestamptz    not null default now(),
    atualizado_em        timestamptz,
    check (lancamento_id is null or conta_id is null),
    check (coalesce(meio_pagamento, '') = 'cartao' or (cartao_id is null and cartao_vinculado_id is null)),
    check (anulado_em is null or (lancamento_id is null and conta_id is null))
);
comment on table financeiro.abastecimento is
    'FIN-MVP-MOB-01: registro operacional e fonte da quilometragem real. Nao e despesa financeira; compra ou conta correspondente so se liga depois, sem criar nem alterar nada nelas. So as funcoes gravam.';
comment on column financeiro.abastecimento.litros is
    'Sempre valor_total / preco_litro, sem arredondar (a tela mostra ate tres casas).';
comment on column financeiro.abastecimento.cartao_id is
    'Contrato do cartao (item_despesa Agregador). O cartao fisico, quando identificado, fica em cartao_vinculado_id. Nenhum numero completo e guardado.';
create index ix_abastecimento_veiculo_data on financeiro.abastecimento (veiculo_id, data_abastecimento, hodometro_km) where anulado_em is null;
create unique index ux_abastecimento_lancamento on financeiro.abastecimento (lancamento_id) where lancamento_id is not null;
create unique index ux_abastecimento_conta on financeiro.abastecimento (conta_id) where conta_id is not null;
create unique index ux_abastecimento_repetido on financeiro.abastecimento (veiculo_id, data_abastecimento, hodometro_km, valor_total)
    where anulado_em is null;
alter table financeiro.abastecimento enable row level security;
alter table financeiro.abastecimento force row level security;
revoke all on financeiro.abastecimento from public, anon, authenticated;

-- Correcoes, anulacoes e vinculos: quem, quando, por que e o registro antes e depois.
create table financeiro.abastecimento_historico (
    id               bigint      generated always as identity primary key,
    abastecimento_id integer     not null references financeiro.abastecimento (id),
    acao             text        not null check (acao in ('CORRECAO', 'ANULACAO', 'VINCULO', 'DESVINCULO')),
    motivo           text,
    antes            jsonb       not null,
    depois           jsonb       not null,
    user_id          uuid        references auth.users (id) on delete set null,
    criado_em        timestamptz not null default now()
);
comment on table financeiro.abastecimento_historico is
    'FIN-MVP-MOB-01: rastreabilidade do abastecimento. Corrigir o hodometro nao altera despesa alguma. So as funcoes gravam.';
create index ix_abastecimento_historico on financeiro.abastecimento_historico (abastecimento_id, id);
alter table financeiro.abastecimento_historico enable row level security;
alter table financeiro.abastecimento_historico force row level security;
revoke all on financeiro.abastecimento_historico from public, anon, authenticated;

-- =====================================================================================================================
-- 1c. Troca de modalidade: decisao registrada para cada despesa futura da modalidade anterior. O registro substituido fica
-- preservado, fora dos indicadores: conta com status_pagamento = 'Substituida'; compra como previsao nao cobrada.
-- =====================================================================================================================
create table financeiro.mobilidade_troca_decisao (
    id                   bigint         generated always as identity primary key,
    perfil_financeiro_id integer        not null,
    cenario_id           integer        not null references public.mobilidade_cenario_ativo (id),
    natureza             text           not null check (natureza in ('CONTA', 'COMPRA')),
    conta_id             integer        references public.conta (id) on delete set null,
    lancamento_id        integer        references public.lancamento_agregado (id) on delete set null,
    competencia          date           not null,
    valor                numeric(12, 2) not null,
    descricao            text,
    modalidade_tipo      text           not null,
    modalidade_origem_id integer        not null,
    decisao              text           not null check (decisao in ('MANTER', 'SUBSTITUIR')),
    registro_antes       jsonb          not null,
    user_id              uuid           references auth.users (id) on delete set null,
    criado_em            timestamptz    not null default now()
);
comment on table financeiro.mobilidade_troca_decisao is
    'FIN-MVP-MOB-01: decisao do usuario sobre cada despesa futura da modalidade anterior, uma unica vez por registro (alternar modalidades nao repete). So as funcoes gravam.';
create unique index ux_mobilidade_troca_conta on financeiro.mobilidade_troca_decisao (conta_id) where conta_id is not null;
create unique index ux_mobilidade_troca_lancamento on financeiro.mobilidade_troca_decisao (lancamento_id) where lancamento_id is not null;
alter table financeiro.mobilidade_troca_decisao enable row level security;
alter table financeiro.mobilidade_troca_decisao force row level security;
revoke all on financeiro.mobilidade_troca_decisao from public, anon, authenticated;

-- A regra ja existente (um cenario ativo por perfil) passa a ser garantida pelo banco.
create unique index ux_mobilidade_cenario_ativo_perfil on public.mobilidade_cenario_ativo (perfil_financeiro_id) where status = 'ATIVO';

-- Situacao do veiculo: SIMULADO (so comparacao), CENARIO (a modalidade financeira ativa), EM_USO (real, fora do cenario: marcado
-- em uso paralelo, ou ATIVO que nunca foi o cenario) ou FORA_DE_USO (saiu do cenario e nao esta em uso paralelo).
create function financeiro.mob_situacao_uso(p_v public.veiculo)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select case
               when p_v.status = 'SIMULADO' then 'SIMULADO'
               when exists (select 1 from public.mobilidade_cenario_ativo c
                             where c.tipo_modalidade = 'VEICULO' and c.origem_id = p_v.id and c.status = 'ATIVO') then 'CENARIO'
               when p_v.em_uso_paralelo then 'EM_USO'
               when exists (select 1 from public.mobilidade_cenario_ativo c
                             where c.tipo_modalidade = 'VEICULO' and c.origem_id = p_v.id and c.status = 'INATIVO') then 'FORA_DE_USO'
               else 'EM_USO'
           end
$$;

-- Veiculo em uso paralelo: a recorrencia dele continua na troca do cenario e as despesas dele nao entram em conflito.
create function financeiro.mob_em_uso_paralelo(p_tipo text, p_origem_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select p_tipo = 'VEICULO' and exists (select 1 from public.veiculo v where v.id = p_origem_id and v.em_uso_paralelo)
$$;

-- A compra foi substituida na troca de modalidade?
create function financeiro.mob_compra_substituida(p_lancamento_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from financeiro.mobilidade_troca_decisao d where d.lancamento_id = p_lancamento_id and d.decisao = 'SUBSTITUIR')
$$;

-- =====================================================================================================================
-- 2. Funcoes novas (internas)
-- =====================================================================================================================
-- A prevista conta como obrigacao financeira real? Ficam so nas telas de Mobilidade as de veiculo SIMULADO, as de veiculo que
-- saiu do cenario financeiro sem continuar em uso e as de caminho de app que nao e o cenario ativo. Veiculo em uso conta.
create function financeiro.prevista_financeira(p_origem_tipo text, p_origem_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select case p_origem_tipo
               when 'VEICULO' then
                   not exists (select 1 from public.veiculo v where v.id = p_origem_id
                                 and financeiro.mob_situacao_uso(v) in ('SIMULADO', 'FORA_DE_USO'))
               when 'TRANSPORTE_APP' then
                   exists (select 1 from public.mobilidade_cenario_ativo c
                            where c.tipo_modalidade = 'TRANSPORTE_APP' and c.origem_id = p_origem_id and c.status = 'ATIVO')
               else true
           end
$$;

-- Recorrencia ativa de combustivel do veiculo (a da ativacao da modalidade).
create function financeiro.mob_item_combustivel(p_perfil_id integer, p_veiculo_id integer)
    returns public.item_despesa
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select i.* from public.item_despesa i
     where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.origem_tipo = 'VEICULO'
       and i.origem_id = p_veiculo_id and i.origem_contexto = 'combustivel_mensal' and i.recorrente and i.ativo
     order by i.id limit 1
$$;

-- A competencia ja tem despesa de combustivel pela recorrencia do veiculo (ativa desde esse mes, ou uma ja lancada)?
create function financeiro.mob_competencia_coberta(p_perfil_id integer, p_veiculo_id integer, p_mes date)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce(date_trunc('month', (financeiro.mob_item_combustivel(p_perfil_id, p_veiculo_id)).data_vencimento::timestamp)::date <= p_mes, false)
        or exists (select 1 from public.conta c join public.item_despesa i on i.id = c.item_despesa_id
                    where i.origem_tipo = 'VEICULO' and i.origem_id = p_veiculo_id and i.origem_contexto = 'combustivel_mensal'
                      and date_trunc('month', c.mes_referencia) = p_mes and c.status_pagamento is distinct from 'Substituida')
        or exists (select 1 from public.lancamento_agregado l join public.item_despesa i on i.id = l.item_despesa_id
                    where i.origem_tipo = 'VEICULO' and i.origem_id = p_veiculo_id and i.origem_contexto = 'combustivel_mensal'
                      and l.mes_fatura = p_mes and not financeiro.mob_compra_substituida(l.id))
$$;

-- Com a recorrencia ativa, as previsoes de combustivel das competencias dela deixam de contar. Devolve quantas.
create function financeiro.mob_suprimir_combustivel(p_perfil_id integer, p_veiculo_id integer)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item public.item_despesa := financeiro.mob_item_combustivel(p_perfil_id, p_veiculo_id);
    v_n    integer;
begin
    if v_item.id is null then
        return 0;
    end if;
    update public.despesa_prevista d set status = 'SUPRIMIDA', atualizado_em = financeiro.mob_agora()
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
       and d.origem_id = p_veiculo_id and d.status = 'PREVISTA' and d.obrigacao = 'COMBUSTIVEL'
       and d.data_prevista >= date_trunc('month', v_item.data_vencimento::timestamp)::date;
    get diagnostics v_n = row_count;
    return v_n;
end
$$;

-- Sem a recorrencia, as previsoes futuras voltam, salvo onde ja ha despesa lancada, com o valor atual do veiculo.
create function financeiro.mob_restaurar_combustivel(p_perfil_id integer, p_veiculo_id integer)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    update public.despesa_prevista d set status = 'PREVISTA', atualizado_em = financeiro.mob_agora()
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
       and d.origem_id = p_veiculo_id and d.status = 'SUPRIMIDA' and d.obrigacao = 'COMBUSTIVEL'
       and d.data_prevista >= date_trunc('month', financeiro.hoje_brasilia())::date
       and not financeiro.mob_competencia_coberta(p_perfil_id, p_veiculo_id, date_trunc('month', d.data_prevista::timestamp)::date);
    perform financeiro.mob_gerar_projecoes(p_perfil_id, p_veiculo_id, 12);
end
$$;

-- A recorrencia nao gera competencia ja coberta: por outra recorrencia do mesmo veiculo (reativacao ou troca do meio de
-- pagamento) ou por prevista confirmada com despesa. Fica registrada como dispensada, como uma conta excluida.
create function financeiro.mob_dispensar_cobertas(p_perfil_id integer, p_veiculo_id integer, p_item public.item_despesa)
    returns void
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into financeiro.recorrencia_competencia (item_despesa_id, natureza, competencia, situacao, motivo, user_id)
    select p_item.id, case when p_item.meio_pagamento = 'cartao' then 'LANCAMENTO_CARTAO' else 'CONTA' end, x.mes, 'DISPENSADA',
           'Competencia ja coberta por outra despesa de combustivel do veiculo', (select auth.uid())
      from (select date_trunc('month', c.mes_referencia)::date as mes
              from public.conta c join public.item_despesa i on i.id = c.item_despesa_id
             where i.origem_tipo = 'VEICULO' and i.origem_id = p_veiculo_id and i.origem_contexto = 'combustivel_mensal'
               and i.id <> p_item.id and c.status_pagamento is distinct from 'Substituida'
            union
            select l.mes_fatura
              from public.lancamento_agregado l join public.item_despesa i on i.id = l.item_despesa_id
             where i.origem_tipo = 'VEICULO' and i.origem_id = p_veiculo_id and i.origem_contexto = 'combustivel_mensal'
               and i.id <> p_item.id and not financeiro.mob_compra_substituida(l.id)
            union
            select date_trunc('month', c.mes_referencia)::date
              from public.despesa_prevista d join public.conta c on c.id = d.conta_id
             where d.origem_tipo = 'VEICULO' and d.origem_id = p_veiculo_id and d.obrigacao = 'COMBUSTIVEL'
            union
            select l.mes_fatura
              from public.despesa_prevista d join public.lancamento_agregado l on l.id = d.lancamento_id
             where d.origem_tipo = 'VEICULO' and d.origem_id = p_veiculo_id and d.obrigacao = 'COMBUSTIVEL') x
     where x.mes >= date_trunc('month', p_item.data_vencimento::timestamp)::date
    on conflict do nothing
$$;

-- Custo novo: a recorrencia e so as ocorrencias de meses futuros ainda abertas. Conta paga, com movimento ou fora de
-- Pendente nao muda; compra so enquanto for previsao sem cobranca.
create function financeiro.mob_sincronizar_combustivel(p_perfil_id integer, p_veiculo_id integer, p_valor numeric)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item public.item_despesa := financeiro.mob_item_combustivel(p_perfil_id, p_veiculo_id);
    v_mes  date := date_trunc('month', financeiro.hoje_brasilia())::date;
    v_l    record;
begin
    if v_item.id is null then
        return;
    end if;
    perform 1 from public.item_despesa i where i.id = v_item.id for update;
    update public.item_despesa i set valor = p_valor where i.id = v_item.id;
    update public.conta c set valor = p_valor
     where c.item_despesa_id = v_item.id and not coalesce(c.is_fatura_cartao, false)
       and coalesce(c.status_pagamento, 'Pendente') = 'Pendente' and c.data_pagamento is null
       and date_trunc('month', c.mes_referencia) > v_mes
       and not exists (select 1 from public.movimento_financeiro m where m.conta_id = c.id);
    if v_item.cartao_id is not null then
        perform 1 from public.item_despesa i where i.id = v_item.cartao_id for update;
        for v_l in select l.id, l.mes_fatura from public.lancamento_agregado l
                    where l.item_despesa_id = v_item.id and l.mes_fatura > v_mes
                      and financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id),
                                                       l.is_importado, l.cartao_id, l.mes_fatura) = 'PREVISTA'
                    order by l.mes_fatura
        loop
            update public.lancamento_agregado l set valor = p_valor where l.id = v_l.id;
            perform financeiro.recalcular_fatura(p_perfil_id, v_item.cartao_id, v_l.mes_fatura);
        end loop;
    end if;
end
$$;

-- Atualiza a prevista da obrigacao e do periodo (mesmo id), ou cria.
create function financeiro.mob_planejar_prevista(p_perfil_destino integer, p_perfil_id integer, p_veiculo_id integer, p_tipo text,
                                                 p_data date, p_valor numeric)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_id  integer;
    v_cat integer := financeiro.mob_categoria_evento(p_tipo);
begin
    select d.id into v_id from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
       and d.origem_id = p_veiculo_id and d.status = 'PREVISTA' and d.obrigacao = p_tipo
       and d.periodo_referencia = financeiro.mob_periodo(p_tipo, p_data)
     for update;
    if v_id is null then
        return financeiro.mob_inserir_prevista(p_perfil_destino, 'VEICULO', p_veiculo_id, v_cat, p_data, p_valor,
            jsonb_build_object('tipo_evento', p_tipo, 'ciclo_id', null, 'ordem_no_ciclo', null));
    end if;
    update public.despesa_prevista d
       set data_prevista = p_data, data_original_prevista = p_data, data_atual_prevista = p_data, valor_previsto = p_valor,
           categoria_id = v_cat, atualizado_em = financeiro.mob_agora()
     where d.id = v_id and (d.data_prevista, d.valor_previsto, d.categoria_id) is distinct from (p_data, p_valor, v_cat);
    return v_id;
end
$$;

-- Flex e custo do combustivel. Precedencia: MANUAL (padrao) mantem o valor informado; CALCULADO grava km / autonomia x
-- preco ao salvar, e so aceita com os parametros completos. Os campos em uso (autonomia_km_l, preco_medio_combustivel)
-- seguem o combustivel de referencia do Flex, entao quem os le nao muda.
create function financeiro.mob_dados_flex(p_v public.veiculo, p_dados jsonb)
    returns public.veiculo
    language plpgsql
    stable
    set search_path = ''
as $$
declare
    v public.veiculo := p_v;
begin
    if p_dados ? 'em_uso_paralelo' then
        v.em_uso_paralelo := financeiro.mob_bool(p_dados -> 'em_uso_paralelo', false);
    end if;
    v.em_uso_paralelo := coalesce(v.em_uso_paralelo, false);
    if v.em_uso_paralelo and v.status = 'SIMULADO' then
        raise exception 'Veículo simulado não fica em uso paralelo: converta para ativo antes. Nada foi gravado.' using errcode = '22023';
    end if;
    if p_dados ? 'km_mensal_estimado' then
        v.km_mensal_estimado := financeiro.numero_seguro(p_dados -> 'km_mensal_estimado');
        if v.km_mensal_estimado < 0 then
            raise exception 'Quilometragem mensal deve ser positiva' using errcode = '22023';
        end if;
    end if;
    if p_dados ? 'custo_combustivel_modo' then
        v.custo_combustivel_modo := upper(btrim(coalesce(p_dados ->> 'custo_combustivel_modo', '')));
    end if;
    v.custo_combustivel_modo := coalesce(nullif(v.custo_combustivel_modo, ''), 'MANUAL');
    if v.custo_combustivel_modo not in ('MANUAL', 'CALCULADO') then
        raise exception 'Modo do custo inválido (MANUAL|CALCULADO)' using errcode = '22023';
    end if;
    v.combustivel := case when lower(v.combustivel) = 'flex' then 'flex' else v.combustivel end;
    if v.combustivel = 'flex' then
        if p_dados ? 'autonomia_gasolina_km_l' then v.autonomia_gasolina_km_l := financeiro.numero_seguro(p_dados -> 'autonomia_gasolina_km_l'); end if;
        if p_dados ? 'autonomia_etanol_km_l' then v.autonomia_etanol_km_l := financeiro.numero_seguro(p_dados -> 'autonomia_etanol_km_l'); end if;
        if p_dados ? 'preco_gasolina' then v.preco_gasolina := financeiro.numero_seguro(p_dados -> 'preco_gasolina'); end if;
        if p_dados ? 'preco_etanol' then v.preco_etanol := financeiro.numero_seguro(p_dados -> 'preco_etanol'); end if;
        if p_dados ? 'combustivel_referencia' then v.combustivel_referencia := lower(btrim(coalesce(p_dados ->> 'combustivel_referencia', ''))); end if;
        if coalesce(v.autonomia_gasolina_km_l, 0) <= 0 or coalesce(v.autonomia_etanol_km_l, 0) <= 0 then
            raise exception 'Flex: informe a autonomia com gasolina e com etanol' using errcode = '22023';
        end if;
        if v.combustivel_referencia is null or v.combustivel_referencia not in ('gasolina', 'etanol') then
            raise exception 'Flex: escolha o combustível de referência (gasolina ou etanol)' using errcode = '22023';
        end if;
        if coalesce(v.preco_gasolina, 0) < 0 or coalesce(v.preco_etanol, 0) < 0 then
            raise exception 'Flex: o preço por litro deve ser positivo' using errcode = '22023';
        end if;
        v.autonomia_km_l := case v.combustivel_referencia when 'gasolina' then v.autonomia_gasolina_km_l else v.autonomia_etanol_km_l end;
        v.preco_medio_combustivel := case v.combustivel_referencia when 'gasolina' then v.preco_gasolina else v.preco_etanol end;
    else
        v.autonomia_gasolina_km_l := null;
        v.autonomia_etanol_km_l := null;
        v.preco_gasolina := null;
        v.preco_etanol := null;
        v.combustivel_referencia := null;
    end if;
    if v.custo_combustivel_modo = 'CALCULADO' then
        if coalesce(v.km_mensal_estimado, 0) <= 0 or coalesce(v.autonomia_km_l, 0) <= 0 or coalesce(v.preco_medio_combustivel, 0) <= 0 then
            raise exception 'Para calcular o custo informe a quilometragem mensal, a autonomia e o preço por litro. Nada foi gravado.'
                using errcode = '22023';
        end if;
        v.combustivel_valor_mensal := round(v.km_mensal_estimado / v.autonomia_km_l * v.preco_medio_combustivel, 2);
    end if;
    return v;
end
$$;

-- =====================================================================================================================
-- 2b. Troca de modalidade
-- =====================================================================================================================
-- Despesas abertas das recorrencias de outras modalidades. decidir = mes futuro, ainda sem decisao e alteravel. O mes
-- corrente so aparece como informacao: nada nele muda automaticamente. Conta paga ou com movimento, compra ja cobrada e
-- registro com decisao nao entram.
create function financeiro.mob_conflitos_troca(p_perfil_id integer, p_tipo text, p_origem_id integer, p_inicio date)
    returns table (natureza text, registro_id integer, descricao text, competencia date, valor numeric, modalidade_tipo text,
                   modalidade_origem_id integer, decidir boolean)
    language sql
    stable
    security definer
    set search_path = ''
as $$
    with m as (select date_trunc('month', financeiro.hoje_brasilia()::timestamp)::date as mes,
                      date_trunc('month', coalesce(p_inicio, financeiro.hoje_brasilia())::timestamp)::date as inicio),
    itens as (select i.* from public.item_despesa i
               where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.recorrente
                 and i.origem_contexto in ('combustivel_mensal', 'transporte_app_mensal', 'assinatura_mensal')
                 and (i.origem_tipo, i.origem_id) is distinct from (p_tipo, p_origem_id)
                 and not financeiro.mob_em_uso_paralelo(i.origem_tipo, i.origem_id))
    select x.* from (
        select 'CONTA'::text as natureza, c.id as registro_id, coalesce(c.descricao, i.nome)::text as descricao,
               date_trunc('month', c.mes_referencia)::date as competencia, c.valor as valor, i.origem_tipo::text as modalidade_tipo,
               i.origem_id as modalidade_origem_id, date_trunc('month', c.mes_referencia)::date > m.mes as decidir
          from itens i
          join public.conta c on c.item_despesa_id = i.id
         cross join m
         where not coalesce(c.is_fatura_cartao, false) and coalesce(c.status_pagamento, 'Pendente') = 'Pendente'
           and c.data_pagamento is null
           and date_trunc('month', c.mes_referencia)::date >= m.mes
           and (date_trunc('month', c.mes_referencia)::date = m.mes or date_trunc('month', c.mes_referencia)::date >= m.inicio)
           and not exists (select 1 from public.movimento_financeiro t where t.conta_id = c.id)
           and not exists (select 1 from financeiro.mobilidade_troca_decisao d where d.conta_id = c.id)
        union all
        select 'COMPRA', l.id, l.descricao::text, l.mes_fatura, l.valor, i.origem_tipo::text, i.origem_id,
               l.mes_fatura > m.mes and not exists (select 1 from public.conta f
                                                     where f.id = financeiro.fatura_do_mes(l.cartao_id, l.mes_fatura) and f.status_fatura = 'FECHADA')
          from itens i
          join public.lancamento_agregado l on l.item_despesa_id = i.id
         cross join m
         where l.mes_fatura >= m.mes and (l.mes_fatura = m.mes or l.mes_fatura >= m.inicio)
           and financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id),
                                            l.is_importado, l.cartao_id, l.mes_fatura) = 'PREVISTA'
           and not exists (select 1 from financeiro.mobilidade_troca_decisao d where d.lancamento_id = l.id)
    ) x
    order by x.competencia, x.natureza, x.registro_id
$$;

-- Conflitos para a previa e o veiculo que sai do cenario ({} sem nenhum dos dois: a resposta continua igual a de antes).
create function financeiro.mob_conflitos_previa(p_perfil_id integer, p_tipo text, p_origem_id integer, p_inicio date)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select case when count(*) = 0 then '{}'::jsonb else jsonb_build_object('conflitos', jsonb_build_object(
               'decidir', coalesce(jsonb_agg(to_jsonb(c) - 'decidir' order by c.competencia, c.natureza, c.registro_id) filter (where c.decidir), '[]'::jsonb),
               'sem_alteracao', coalesce(jsonb_agg(to_jsonb(c) - 'decidir' order by c.competencia, c.natureza, c.registro_id) filter (where not c.decidir), '[]'::jsonb)))
           end
           || coalesce((select jsonb_build_object('veiculo_saindo', jsonb_build_object('id', v.id, 'nome', v.nome))
                          from public.mobilidade_cenario_ativo a
                          join public.veiculo v on v.id = a.origem_id
                         where financeiro.pertence_ao_perfil(a.perfil_financeiro_id, p_perfil_id) and a.status = 'ATIVO' and a.tipo_modalidade = 'VEICULO'
                           and ('VEICULO', a.origem_id) is distinct from (p_tipo, p_origem_id) and not v.em_uso_paralelo), '{}'::jsonb)
      from financeiro.mob_conflitos_troca(p_perfil_id, p_tipo, p_origem_id, p_inicio) c
$$;

-- Aplica e registra as decisoes. Sem decisao para todos os conflitos, ou com decisao para o que nao e conflito, nada e gravado.
create function financeiro.mob_aplicar_decisoes(p_perfil_id integer, p_cenario public.mobilidade_cenario_ativo, p_decisoes jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_dec    jsonb := coalesce(p_decisoes, '[]'::jsonb);
    v_lista  jsonb;
    v_inicio date := p_cenario.ativo_desde::date;
    v_c      record;
    v_conta  public.conta;
    v_l      public.lancamento_agregado;
    v_n      integer;
    v_subst  integer := 0;
    v_mant   integer := 0;
begin
    if jsonb_typeof(v_dec) <> 'array' then
        raise exception 'Decisoes devem ser uma lista' using errcode = '22023';
    end if;
    select coalesce(jsonb_agg(jsonb_build_object('natureza', upper(coalesce(d ->> 'natureza', '')), 'id', financeiro.mob_inteiro(d -> 'id'),
                                                 'decisao', upper(coalesce(d ->> 'decisao', '')))), '[]'::jsonb)
      into v_lista from jsonb_array_elements(v_dec) d;
    if exists (select 1 from jsonb_array_elements(v_lista) d where d ->> 'decisao' not in ('MANTER', 'SUBSTITUIR')) then
        raise exception 'Decisao invalida: use manter ou substituir' using errcode = '22023';
    end if;
    select count(*) into v_n
      from financeiro.mob_conflitos_troca(p_perfil_id, p_cenario.tipo_modalidade, p_cenario.origem_id, v_inicio) c
     where c.decidir and not exists (select 1 from jsonb_array_elements(v_lista) d
                                      where d ->> 'natureza' = c.natureza and (d ->> 'id')::integer = c.registro_id);
    if v_n > 0 then
        raise exception 'Ha % despesa(s) futura(s) da modalidade anterior sem decisao: escolha manter ou substituir cada uma. Nada foi gravado.', v_n
            using errcode = '22023', hint = 'CONFLITOS_PENDENTES';
    end if;
    if exists (select 1 from jsonb_array_elements(v_lista) d
                where not exists (select 1 from financeiro.mob_conflitos_troca(p_perfil_id, p_cenario.tipo_modalidade, p_cenario.origem_id, v_inicio) c
                                   where c.decidir and c.natureza = d ->> 'natureza' and c.registro_id = (d ->> 'id')::integer)) then
        raise exception 'A previa mudou desde a escolha: revise as despesas da modalidade anterior. Nada foi gravado.'
            using errcode = '22023', hint = 'PREVIA_DESATUALIZADA';
    end if;
    for v_c in select c.*, d ->> 'decisao' as decisao
                 from jsonb_array_elements(v_lista) d
                 join financeiro.mob_conflitos_troca(p_perfil_id, p_cenario.tipo_modalidade, p_cenario.origem_id, v_inicio) c
                   on c.decidir and c.natureza = d ->> 'natureza' and c.registro_id = (d ->> 'id')::integer
                order by c.competencia, c.natureza, c.registro_id
    loop
        if v_c.natureza = 'CONTA' then
            select * into v_conta from public.conta c where c.id = v_c.registro_id for update;
            insert into financeiro.mobilidade_troca_decisao (perfil_financeiro_id, cenario_id, natureza, conta_id, competencia, valor, descricao,
                                                             modalidade_tipo, modalidade_origem_id, decisao, registro_antes, user_id)
            values (p_perfil_id, p_cenario.id, 'CONTA', v_conta.id, v_c.competencia, v_c.valor, v_c.descricao, v_c.modalidade_tipo,
                    v_c.modalidade_origem_id, v_c.decisao, to_jsonb(v_conta), (select auth.uid()));
            if v_c.decisao = 'SUBSTITUIR' then
                update public.conta c set status_pagamento = 'Substituida' where c.id = v_conta.id;
            end if;
        else
            select * into v_l from public.lancamento_agregado l where l.id = v_c.registro_id for update;
            insert into financeiro.mobilidade_troca_decisao (perfil_financeiro_id, cenario_id, natureza, lancamento_id, competencia, valor, descricao,
                                                             modalidade_tipo, modalidade_origem_id, decisao, registro_antes, user_id)
            values (p_perfil_id, p_cenario.id, 'COMPRA', v_l.id, v_c.competencia, v_c.valor, v_c.descricao, v_c.modalidade_tipo,
                    v_c.modalidade_origem_id, v_c.decisao, to_jsonb(v_l), (select auth.uid()));
            if v_c.decisao = 'SUBSTITUIR' then
                perform 1 from public.item_despesa i where i.id = v_l.cartao_id for update;
                insert into financeiro.ocorrencia_recorrencia_cartao (perfil_financeiro_id, lancamento_id, item_despesa_id, cartao_id, competencia,
                                                                      valor_previsto, valor_executado, descricao_cobranca, origem, lancamento_antes, user_id)
                values (p_perfil_id, v_l.id, v_l.item_despesa_id, v_l.cartao_id, coalesce(v_l.mes_fatura_original, v_l.mes_fatura), v_l.valor, 0,
                        'Substituida na troca de modalidade de Mobilidade', 'NAO_COBRADA', to_jsonb(v_l), (select auth.uid()));
                perform financeiro.recalcular_fatura(p_perfil_id, v_l.cartao_id, v_l.mes_fatura);
            end if;
        end if;
        if v_c.decisao = 'SUBSTITUIR' then v_subst := v_subst + 1; else v_mant := v_mant + 1; end if;
    end loop;
    return case when v_subst + v_mant = 0 then '{}'::jsonb
                else jsonb_build_object('troca', jsonb_build_object('substituidas', v_subst, 'mantidas', v_mant)) end;
end
$$;

-- =====================================================================================================================
-- 2c. Quilometragem: real (ultima leitura do hodometro) e estimada (projecao depois dela)
-- =====================================================================================================================
-- Sequencia do hodometro do veiculo: leitura nao pode ser menor que a anterior nem maior que a posterior. No mesmo dia, vale a
-- ordem de registro.
create function financeiro.mob_validar_hodometro(p_veiculo_id integer, p_data date, p_km numeric, p_ignorar_id integer)
    returns void
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_a financeiro.abastecimento;
begin
    select * into v_a from financeiro.abastecimento a
     where a.veiculo_id = p_veiculo_id and a.anulado_em is null and a.id is distinct from p_ignorar_id
       and (a.data_abastecimento < p_data or (a.data_abastecimento = p_data and a.id < coalesce(p_ignorar_id, 2147483647)))
       and a.hodometro_km > p_km
     order by a.hodometro_km desc limit 1;
    if found then
        raise exception 'Hodômetro menor que a leitura de % (% km). Para corrigir uma leitura errada, use Corrigir no histórico. Nada foi gravado.',
            to_char(v_a.data_abastecimento, 'DD/MM/YYYY'), v_a.hodometro_km using errcode = '22023', hint = 'HODOMETRO_REGRESSAO';
    end if;
    select * into v_a from financeiro.abastecimento a
     where a.veiculo_id = p_veiculo_id and a.anulado_em is null and a.id is distinct from p_ignorar_id
       and (a.data_abastecimento > p_data or (a.data_abastecimento = p_data and a.id > coalesce(p_ignorar_id, 2147483647)))
       and a.hodometro_km < p_km
     order by a.hodometro_km limit 1;
    if found then
        raise exception 'Hodômetro maior que a leitura de % (% km). Para corrigir uma leitura errada, use Corrigir no histórico. Nada foi gravado.',
            to_char(v_a.data_abastecimento, 'DD/MM/YYYY'), v_a.hodometro_km using errcode = '22023', hint = 'HODOMETRO_REGRESSAO';
    end if;
end
$$;

-- Km do veiculo. Com leitura: a ultima leitura + a estimativa so dos dias depois dela (km_estimado_acumulado, feito de
-- confirmacoes, nao soma de novo). Sem leitura: o acumulado + as competencias encerradas cobertas pela recorrencia, que nao
-- passam pela confirmacao. Km por mes: leituras > confirmacoes (p_media) > km mensal do cadastro > projecao do combustivel.
create function financeiro.mob_km_veiculo(p_v public.veiculo, p_media numeric)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_hoje   date := financeiro.hoje_brasilia();
    v_ult    financeiro.abastecimento;
    v_pri    financeiro.abastecimento;
    v_km_mes numeric := 0;
    v_fonte  text := 'INDISPONIVEL';
    v_est    numeric := 0;
    v_atual  numeric;
    v_n      integer;
begin
    select * into v_ult from financeiro.abastecimento a where a.veiculo_id = p_v.id and a.anulado_em is null
     order by a.data_abastecimento desc, a.hodometro_km desc, a.id desc limit 1;
    if v_ult.id is not null then
        select * into v_pri from financeiro.abastecimento a
         where a.veiculo_id = p_v.id and a.anulado_em is null and a.data_abastecimento >= v_ult.data_abastecimento - 365
         order by a.data_abastecimento, a.hodometro_km, a.id limit 1;
    end if;
    if v_ult.id is not null and v_ult.data_abastecimento - v_pri.data_abastecimento >= 7 and v_ult.hodometro_km > v_pri.hodometro_km then
        v_km_mes := (v_ult.hodometro_km - v_pri.hodometro_km) / (v_ult.data_abastecimento - v_pri.data_abastecimento) * 30.4375;
        v_fonte := 'LEITURAS';
    elsif coalesce(p_media, 0) > 0 then
        v_km_mes := p_media;
        v_fonte := 'HISTORICO';
    elsif coalesce(p_v.km_mensal_estimado, 0) > 0 then
        v_km_mes := p_v.km_mensal_estimado;
        v_fonte := 'CADASTRO';
    elsif coalesce(p_v.combustivel_valor_mensal, 0) > 0 and coalesce(p_v.preco_medio_combustivel, 0) > 0 and coalesce(p_v.autonomia_km_l, 0) > 0 then
        v_km_mes := p_v.combustivel_valor_mensal / p_v.preco_medio_combustivel * p_v.autonomia_km_l;
        v_fonte := 'PROJETADO';
    end if;
    if v_ult.id is not null then
        v_est := round(v_km_mes * greatest(v_hoje - v_ult.data_abastecimento, 0) / 30.4375, 1);
        v_atual := v_ult.hodometro_km + v_est;
    else
        select count(*) into v_n from public.despesa_prevista d
         where d.origem_tipo = 'VEICULO' and d.origem_id = p_v.id and d.status = 'SUPRIMIDA' and d.obrigacao = 'COMBUSTIVEL'
           and d.data_prevista < date_trunc('month', v_hoje::timestamp)::date;
        v_est := round(v_n * v_km_mes, 1);
        v_atual := coalesce(p_v.km_estimado_acumulado, 0) + v_est;
    end if;
    return jsonb_build_object('km_real', v_ult.hodometro_km, 'km_real_data', v_ult.data_abastecimento, 'km_estimado', v_est, 'km_atual', v_atual,
                              'km_mes', v_km_mes, 'fonte_km_mes', v_fonte,
                              'leituras', (select count(*) from financeiro.abastecimento a where a.veiculo_id = p_v.id and a.anulado_em is null));
end
$$;

-- =====================================================================================================================
-- 2d. Abastecimentos
-- =====================================================================================================================
create function financeiro.mob_abastecimento_flask(p_a financeiro.abastecimento)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_a.id, 'veiculo_id', p_a.veiculo_id, 'data_abastecimento', p_a.data_abastecimento, 'hodometro_km', p_a.hodometro_km,
        'combustivel', p_a.combustivel, 'preco_litro', p_a.preco_litro, 'valor_total', p_a.valor_total, 'litros', p_a.litros,
        'meio_pagamento', p_a.meio_pagamento, 'cartao_id', p_a.cartao_id,
        'cartao_nome', (select i.nome from public.item_despesa i where i.id = p_a.cartao_id),
        'cartao_vinculado_id', p_a.cartao_vinculado_id,
        'cartao_final', (select v.final from financeiro.cartao_vinculado v where v.id = p_a.cartao_vinculado_id),
        'estabelecimento', p_a.estabelecimento, 'observacoes', p_a.observacoes,
        'lancamento_id', p_a.lancamento_id, 'conta_id', p_a.conta_id,
        'situacao_vinculo', case when p_a.lancamento_id is not null or p_a.conta_id is not null then 'VINCULADO' else 'AGUARDANDO' end,
        'anulado', p_a.anulado_em is not null,
        'corrigido', exists (select 1 from financeiro.abastecimento_historico h where h.abastecimento_id = p_a.id and h.acao = 'CORRECAO'))
$$;

-- Valida os dados e devolve o registro a gravar. O veiculo fica travado: a sequencia do hodometro e conferida um por vez.
create function financeiro.mob_dados_abastecimento(p_perfil_id integer, p_dados jsonb)
    returns financeiro.abastecimento
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    a      financeiro.abastecimento;
    v      public.veiculo;
    v_id   integer := financeiro.mob_inteiro(p_dados -> 'veiculo_id');
    v_comb text := lower(btrim(coalesce(p_dados ->> 'combustivel', '')));
    v_tipo text;
    v_meio text := nullif(lower(btrim(coalesce(p_dados ->> 'meio_pagamento', ''))), '');
    v_cart integer := nullif(financeiro.mob_inteiro(p_dados -> 'cartao_id'), 0);
    v_fis  integer := nullif(financeiro.mob_inteiro(p_dados -> 'cartao_vinculado_id'), 0);
begin
    if v_id is null or v_id = 0 then
        raise exception 'Selecione o veículo do abastecimento' using errcode = '22023';
    end if;
    v := financeiro.mob_veiculo(p_perfil_id, v_id);
    v_tipo := lower(btrim(coalesce(v.combustivel, '')));  -- cadastros antigos gravaram com maiuscula
    if v_tipo = 'eletrico' then
        raise exception 'Veículo elétrico não registra abastecimento por litro. Nada foi gravado.' using errcode = '22023';
    end if;
    a.perfil_financeiro_id := coalesce(v.perfil_financeiro_id, p_perfil_id);
    a.veiculo_id := v.id;
    a.data_abastecimento := financeiro.mob_data(p_dados ->> 'data_abastecimento');
    if a.data_abastecimento is null then
        raise exception 'Informe a data do abastecimento' using errcode = '22023';
    end if;
    if a.data_abastecimento > financeiro.hoje_brasilia() then
        raise exception 'A data do abastecimento não pode ser futura' using errcode = '22023';
    end if;
    a.hodometro_km := round(financeiro.numero_seguro(p_dados -> 'hodometro_km'), 1);
    if a.hodometro_km is null or a.hodometro_km < 0 then
        raise exception 'Informe o hodômetro em quilômetros' using errcode = '22023';
    end if;
    if v_comb not in ('gasolina', 'etanol', 'diesel', 'gnv', 'outro') then
        raise exception 'Informe o combustível abastecido' using errcode = '22023';
    end if;
    if (v_tipo = 'flex' and v_comb not in ('gasolina', 'etanol'))
       or (v_tipo in ('gasolina', 'etanol', 'diesel', 'gnv') and v_comb <> v_tipo) then
        raise exception 'Combustível incompatível com o cadastro do veículo (%). Se o veículo aceita outro, corrija o cadastro. Nada foi gravado.', v.combustivel
            using errcode = '22023';
    end if;
    a.combustivel := v_comb;
    a.preco_litro := round(financeiro.numero_seguro(p_dados -> 'preco_litro'), 3);
    if coalesce(a.preco_litro, 0) <= 0 then
        raise exception 'O preço por litro deve ser maior que zero' using errcode = '22023';
    end if;
    a.valor_total := round(financeiro.numero_seguro(p_dados -> 'valor_total'), 2);
    if coalesce(a.valor_total, 0) <= 0 then
        raise exception 'O valor abastecido deve ser maior que zero' using errcode = '22023';
    end if;
    if v_meio is not null and v_meio not in ('cartao', 'pix', 'debito', 'dinheiro', 'boleto', 'outro') then
        raise exception 'Meio de pagamento inválido' using errcode = '22023';
    end if;
    if v_cart is not null or v_fis is not null then
        v_meio := coalesce(v_meio, 'cartao');
    end if;
    if v_meio is distinct from 'cartao' and (v_cart is not null or v_fis is not null) then
        raise exception 'Cartão informado com outro meio de pagamento' using errcode = '22023';
    end if;
    a.cartao_id := financeiro.mob_cartao(p_perfil_id, v_cart);
    if v_fis is not null and not exists (select 1 from financeiro.cartao_vinculado c where c.id = v_fis and c.contrato_id = v_cart) then
        raise exception 'Cartão físico não pertence ao cartão informado' using errcode = '22023';
    end if;
    a.cartao_vinculado_id := v_fis;
    a.meio_pagamento := v_meio;
    a.estabelecimento := left(nullif(btrim(coalesce(p_dados ->> 'estabelecimento', '')), ''), 120);
    a.observacoes := left(nullif(btrim(coalesce(p_dados ->> 'observacoes', '')), ''), 500);
    perform financeiro.mob_validar_hodometro(a.veiculo_id, a.data_abastecimento, a.hodometro_km, financeiro.mob_inteiro(p_dados -> 'id'));
    return a;
end
$$;

create function financeiro.mob_abastecimento(p_perfil_id integer, p_id integer)
    returns financeiro.abastecimento
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    a financeiro.abastecimento;
begin
    select * into a from financeiro.abastecimento x where x.id = p_id for update;
    if not found or not financeiro.pertence_ao_perfil(a.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Abastecimento não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return a;
end
$$;

create function financeiro.mob_exigir_motivo(p_dados jsonb)
    returns text
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_motivo text := left(nullif(btrim(coalesce(p_dados ->> 'motivo', '')), ''), 300);
begin
    if v_motivo is null then
        raise exception 'Informe o motivo. Nada foi gravado.' using errcode = '22023';
    end if;
    return v_motivo;
end
$$;

create function financeiro.registrar_abastecimento(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep jsonb;
    a     financeiro.abastecimento;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_rep := financeiro.repeticao_mobilidade(p_chave, p_perfil_id, 'registrar_abastecimento');
    if v_rep is not null then
        return v_rep;
    end if;
    a := financeiro.mob_dados_abastecimento(p_perfil_id, coalesce(p_dados, '{}'::jsonb) - 'id');
    if exists (select 1 from financeiro.abastecimento x
                where x.veiculo_id = a.veiculo_id and x.anulado_em is null and x.data_abastecimento = a.data_abastecimento
                  and x.hodometro_km = a.hodometro_km and x.valor_total = a.valor_total) then
        raise exception 'Este abastecimento já foi registrado (mesma data, hodômetro e valor). Nada foi gravado.'
            using errcode = '22023', hint = 'ABASTECIMENTO_REPETIDO';
    end if;
    insert into financeiro.abastecimento (perfil_financeiro_id, veiculo_id, data_abastecimento, hodometro_km, combustivel, preco_litro,
                                          valor_total, meio_pagamento, cartao_id, cartao_vinculado_id, estabelecimento, observacoes, user_id)
    values (a.perfil_financeiro_id, a.veiculo_id, a.data_abastecimento, a.hodometro_km, a.combustivel, a.preco_litro, a.valor_total,
            a.meio_pagamento, a.cartao_id, a.cartao_vinculado_id, a.estabelecimento, a.observacoes, (select auth.uid()))
    returning * into a;
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'registrar_abastecimento',
                                                    jsonb_build_object('abastecimento', financeiro.mob_abastecimento_flask(a)));
end
$$;

-- Corrige com motivo e guarda o antes e o depois. So toca no abastecimento: nenhuma despesa muda.
create function financeiro.corrigir_abastecimento(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    a        financeiro.abastecimento;
    n        financeiro.abastecimento;
    v_motivo text := financeiro.mob_exigir_motivo(p_dados);
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    a := financeiro.mob_abastecimento(p_perfil_id, p_id);
    if a.anulado_em is not null then
        raise exception 'Abastecimento anulado não pode ser corrigido' using errcode = '22023';
    end if;
    n := financeiro.mob_dados_abastecimento(p_perfil_id, to_jsonb(a) || (coalesce(p_dados, '{}'::jsonb) - 'id') || jsonb_build_object('id', a.id));
    if (a.lancamento_id is not null or a.conta_id is not null)
       and (n.veiculo_id <> a.veiculo_id or n.valor_total <> a.valor_total) then
        raise exception 'Desvincule a despesa antes de corrigir o veículo ou o valor. Nada foi gravado.' using errcode = '22023', hint = 'ABASTECIMENTO_VINCULADO';
    end if;
    update financeiro.abastecimento x
       set veiculo_id = n.veiculo_id, perfil_financeiro_id = n.perfil_financeiro_id, data_abastecimento = n.data_abastecimento,
           hodometro_km = n.hodometro_km, combustivel = n.combustivel, preco_litro = n.preco_litro, valor_total = n.valor_total,
           meio_pagamento = n.meio_pagamento, cartao_id = n.cartao_id, cartao_vinculado_id = n.cartao_vinculado_id,
           estabelecimento = n.estabelecimento, observacoes = n.observacoes, atualizado_em = now()
     where x.id = a.id
    returning * into n;
    insert into financeiro.abastecimento_historico (abastecimento_id, acao, motivo, antes, depois, user_id)
    values (a.id, 'CORRECAO', v_motivo, to_jsonb(a), to_jsonb(n), (select auth.uid()));
    return jsonb_build_object('abastecimento', financeiro.mob_abastecimento_flask(n));
end
$$;

-- Registro feito por engano: sai da sequencia e da quilometragem, mas continua no historico.
create function financeiro.anular_abastecimento(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    a        financeiro.abastecimento;
    n        financeiro.abastecimento;
    v_motivo text := financeiro.mob_exigir_motivo(p_dados);
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    a := financeiro.mob_abastecimento(p_perfil_id, p_id);
    if a.anulado_em is not null then
        raise exception 'Abastecimento já anulado' using errcode = '22023';
    end if;
    if a.lancamento_id is not null or a.conta_id is not null then
        raise exception 'Desvincule a despesa antes de anular. Nada foi gravado.' using errcode = '22023', hint = 'ABASTECIMENTO_VINCULADO';
    end if;
    update financeiro.abastecimento x set anulado_em = now(), anulado_por = (select auth.uid()), atualizado_em = now()
     where x.id = a.id
    returning * into n;
    insert into financeiro.abastecimento_historico (abastecimento_id, acao, motivo, antes, depois, user_id)
    values (a.id, 'ANULACAO', v_motivo, to_jsonb(a), to_jsonb(n), (select auth.uid()));
    return jsonb_build_object('abastecimento', financeiro.mob_abastecimento_flask(n));
end
$$;

-- Historico do veiculo, com os km rodados desde a leitura anterior e a quilometragem real e estimada.
create function financeiro.abastecimentos_veiculo_tela(p_perfil_id integer, p_veiculo_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_v public.veiculo;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_v := financeiro.veiculo_do_perfil(p_perfil_id, p_veiculo_id);
    if v_v.id is null then
        raise exception 'Veículo não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return jsonb_build_object(
        'quilometragem', financeiro.mob_km_veiculo(v_v, (financeiro.uso_do_veiculo(v_v, 3) ->> 'media_movel_km_mes')::numeric),
        'abastecimentos', coalesce((
            select jsonb_agg(financeiro.mob_abastecimento_flask(x.a) || jsonb_build_object('km_rodados', x.km_rodados)
                             order by (x.a).anulado_em is not null, (x.a).data_abastecimento desc, (x.a).hodometro_km desc, (x.a).id desc)
              from (select t as a,
                           case when t.anulado_em is null
                                then t.hodometro_km - lag(t.hodometro_km) over (partition by t.anulado_em is null
                                                                                order by t.data_abastecimento, t.hodometro_km, t.id) end as km_rodados
                      from financeiro.abastecimento t where t.veiculo_id = v_v.id) x), '[]'::jsonb));
end
$$;

-- Por veiculo, no mes: o custo estimado (projecao), o que esta financeiramente registrado (contas e compras cobradas do veiculo,
-- pela recorrencia, pela prevista confirmada ou pelo vinculo do abastecimento, cada despesa uma vez) e o abastecido (operacional).
create function financeiro.custos_veiculos_tela(p_perfil_id integer, p_mes date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes date := date_trunc('month', coalesce(p_mes, financeiro.hoje_brasilia())::timestamp)::date;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return coalesce((
        select jsonb_agg(jsonb_build_object('veiculo_id', v.id, 'nome', v.nome, 'situacao_uso', financeiro.mob_situacao_uso(v),
                                            'estimado', e.total, 'registrado', r.total, 'abastecido', a.total, 'abastecimentos', a.n) order by v.id)
          from public.veiculo v
         cross join lateral (select coalesce(sum(d.valor_previsto), 0) as total from public.despesa_prevista d
                              where d.origem_tipo = 'VEICULO' and d.origem_id = v.id and d.status not in ('IGNORADA', 'CANCELADA')
                                and date_trunc('month', coalesce(d.data_atual_prevista, d.data_prevista)::timestamp)::date = v_mes) e
         cross join lateral (select coalesce(sum(x.valor), 0) as total from (
                                 select c.valor from public.conta c
                                  where date_trunc('month', c.mes_referencia)::date = v_mes and not coalesce(c.is_fatura_cartao, false)
                                    and c.status_pagamento is distinct from 'Substituida'
                                    and (exists (select 1 from public.item_despesa i where i.id = c.item_despesa_id and i.origem_tipo = 'VEICULO' and i.origem_id = v.id)
                                         or exists (select 1 from public.despesa_prevista d where d.conta_id = c.id and d.origem_tipo = 'VEICULO' and d.origem_id = v.id)
                                         or exists (select 1 from financeiro.abastecimento b where b.conta_id = c.id and b.veiculo_id = v.id))
                                 union all
                                 select financeiro.valor_executado_compra(l.valor, financeiro.situacao_previsao(l.id,
                                            financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id),
                                            l.is_importado, l.cartao_id, l.mes_fatura))
                                   from public.lancamento_agregado l
                                  where l.mes_fatura = v_mes
                                    and (exists (select 1 from public.item_despesa i where i.id = l.item_despesa_id and i.origem_tipo = 'VEICULO' and i.origem_id = v.id)
                                         or exists (select 1 from public.despesa_prevista d where d.lancamento_id = l.id and d.origem_tipo = 'VEICULO' and d.origem_id = v.id)
                                         or exists (select 1 from financeiro.abastecimento b where b.lancamento_id = l.id and b.veiculo_id = v.id))) x) r
         cross join lateral (select coalesce(sum(b.valor_total), 0) as total, count(*) as n from financeiro.abastecimento b
                              where b.veiculo_id = v.id and b.anulado_em is null
                                and date_trunc('month', b.data_abastecimento::timestamp)::date = v_mes) a
         where financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb);
end
$$;

-- Compras e contas que podem corresponder ao abastecimento. So consulta: nunca escolhe nem vincula sozinha. Mesmo valor,
-- de 3 dias antes a 10 depois (data de processamento), mesmo contrato de cartao quando informado e cartao fisico compativel.
create function financeiro.candidatas_abastecimento(p_perfil_id integer, p_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    a       financeiro.abastecimento;
    v_lista jsonb;
    v_nome  text;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into a from financeiro.abastecimento x where x.id = p_id;
    if not found or not financeiro.pertence_ao_perfil(a.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Abastecimento não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    v_nome := nullif(upper(btrim(coalesce(a.estabelecimento, ''))), '');
    select coalesce(jsonb_agg(y.c order by (y.c ->> 'mesmo_cartao_fisico')::boolean desc, (y.c ->> 'estabelecimento_confere')::boolean desc,
                              abs((y.c ->> 'dias')::integer), y.c ->> 'natureza', (y.c ->> 'id')::integer), '[]'::jsonb)
      into v_lista
      from (select jsonb_build_object('natureza', 'COMPRA', 'id', l.id, 'descricao', l.descricao, 'data', l.data_compra, 'valor', l.valor,
                       'cartao_id', l.cartao_id, 'dias', l.data_compra - a.data_abastecimento,
                       'mesmo_cartao_fisico', a.cartao_vinculado_id is not null and l.cartao_vinculado_id is not distinct from a.cartao_vinculado_id,
                       'estabelecimento_confere', v_nome is not null and position(v_nome in upper(coalesce(l.descricao, ''))) > 0) as c
              from public.lancamento_agregado l
             where financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id) and l.valor = a.valor_total
               and l.data_compra between a.data_abastecimento - 3 and a.data_abastecimento + 10
               and coalesce(a.meio_pagamento, 'cartao') = 'cartao'
               and (a.cartao_id is null or l.cartao_id = a.cartao_id)
               and (a.cartao_vinculado_id is null or l.cartao_vinculado_id is null or l.cartao_vinculado_id = a.cartao_vinculado_id)
               and not exists (select 1 from financeiro.abastecimento x where x.lancamento_id = l.id and x.id <> a.id)
            union all
            select jsonb_build_object('natureza', 'CONTA', 'id', k.id, 'descricao', k.descricao, 'data', k.data_vencimento, 'valor', k.valor,
                       'cartao_id', null, 'dias', k.data_vencimento - a.data_abastecimento, 'mesmo_cartao_fisico', false,
                       'estabelecimento_confere', v_nome is not null and position(v_nome in upper(coalesce(k.descricao, ''))) > 0)
              from public.conta k
             where financeiro.pertence_ao_perfil(k.perfil_financeiro_id, p_perfil_id) and k.valor = a.valor_total
               and not coalesce(k.is_fatura_cartao, false) and k.status_pagamento is distinct from 'Substituida'
               and k.data_vencimento between a.data_abastecimento - 3 and a.data_abastecimento + 10
               and coalesce(a.meio_pagamento, '') <> 'cartao'
               and not exists (select 1 from financeiro.abastecimento x where x.conta_id = k.id and x.id <> a.id)) y;
    return jsonb_build_object('candidatas', v_lista, 'ambigua', jsonb_array_length(v_lista) > 1);
end
$$;

-- Liga o abastecimento a uma compra ou conta ja existente, por escolha do usuario. Nada e criado e a despesa nao muda.
create function financeiro.vincular_abastecimento(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    a       financeiro.abastecimento;
    n       financeiro.abastecimento;
    v_lanc  integer := nullif(financeiro.mob_inteiro(p_dados -> 'lancamento_id'), 0);
    v_conta integer := nullif(financeiro.mob_inteiro(p_dados -> 'conta_id'), 0);
    v_l     public.lancamento_agregado;
    v_c     public.conta;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    a := financeiro.mob_abastecimento(p_perfil_id, p_id);
    if a.anulado_em is not null then
        raise exception 'Abastecimento anulado não pode ser vinculado' using errcode = '22023';
    end if;
    if (v_lanc is null) = (v_conta is null) then
        raise exception 'Informe a compra ou a conta correspondente' using errcode = '22023';
    end if;
    if a.lancamento_id is not null or a.conta_id is not null then
        raise exception 'Abastecimento já vinculado. Desvincule antes de trocar.' using errcode = '22023', hint = 'ABASTECIMENTO_VINCULADO';
    end if;
    if v_lanc is not null then
        select * into v_l from public.lancamento_agregado l
         where l.id = v_lanc and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id) for share;
        if not found then
            raise exception 'Compra não encontrada neste perfil' using errcode = '22023';
        end if;
        if v_l.valor <> a.valor_total then
            raise exception 'O valor da compra é diferente do abastecimento. Nada foi gravado.' using errcode = '22023', hint = 'VALOR_DIVERGENTE';
        end if;
        if a.cartao_id is not null and v_l.cartao_id is distinct from a.cartao_id then
            raise exception 'A compra é de outro cartão. Nada foi gravado.' using errcode = '22023', hint = 'CARTAO_DIVERGENTE';
        end if;
        if a.cartao_vinculado_id is not null and v_l.cartao_vinculado_id is not null and v_l.cartao_vinculado_id <> a.cartao_vinculado_id then
            raise exception 'A compra é de outro cartão físico. Nada foi gravado.' using errcode = '22023', hint = 'CARTAO_DIVERGENTE';
        end if;
        if exists (select 1 from financeiro.abastecimento x where x.lancamento_id = v_lanc) then
            raise exception 'Esta compra já pertence a outro abastecimento. Nada foi gravado.' using errcode = '22023', hint = 'DESPESA_JA_VINCULADA';
        end if;
    else
        select * into v_c from public.conta c
         where c.id = v_conta and financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and not coalesce(c.is_fatura_cartao, false)
           and c.status_pagamento is distinct from 'Substituida' for share;
        if not found then
            raise exception 'Conta não encontrada neste perfil' using errcode = '22023';
        end if;
        if v_c.valor <> a.valor_total then
            raise exception 'O valor da conta é diferente do abastecimento. Nada foi gravado.' using errcode = '22023', hint = 'VALOR_DIVERGENTE';
        end if;
        if exists (select 1 from financeiro.abastecimento x where x.conta_id = v_conta) then
            raise exception 'Esta conta já pertence a outro abastecimento. Nada foi gravado.' using errcode = '22023', hint = 'DESPESA_JA_VINCULADA';
        end if;
    end if;
    update financeiro.abastecimento x set lancamento_id = v_lanc, conta_id = v_conta, atualizado_em = now()
     where x.id = a.id
    returning * into n;
    insert into financeiro.abastecimento_historico (abastecimento_id, acao, antes, depois, user_id)
    values (a.id, 'VINCULO', to_jsonb(a), to_jsonb(n), (select auth.uid()));
    return jsonb_build_object('abastecimento', financeiro.mob_abastecimento_flask(n));
end
$$;

create function financeiro.desvincular_abastecimento(p_perfil_id integer, p_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    a financeiro.abastecimento;
    n financeiro.abastecimento;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    a := financeiro.mob_abastecimento(p_perfil_id, p_id);
    if a.lancamento_id is null and a.conta_id is null then
        return jsonb_build_object('abastecimento', financeiro.mob_abastecimento_flask(a));
    end if;
    update financeiro.abastecimento x set lancamento_id = null, conta_id = null, atualizado_em = now()
     where x.id = a.id
    returning * into n;
    insert into financeiro.abastecimento_historico (abastecimento_id, acao, antes, depois, user_id)
    values (a.id, 'DESVINCULO', to_jsonb(a), to_jsonb(n), (select auth.uid()));
    return jsonb_build_object('abastecimento', financeiro.mob_abastecimento_flask(n));
end
$$;

-- =====================================================================================================================
-- 3. Funcoes substituidas
-- =====================================================================================================================
-- veiculo_flask: texto de 20261115090000 + os trechos marcados.
create or replace function financeiro.veiculo_flask(p_v public.veiculo)
    returns jsonb
    language sql
    stable
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_v.id, 'perfil_financeiro_id', p_v.perfil_financeiro_id, 'nome', p_v.nome, 'tipo', p_v.tipo,
        'combustivel', p_v.combustivel, 'autonomia_km_l', p_v.autonomia_km_l, 'status', p_v.status,
        'data_inicio', p_v.data_inicio,
        'projecao_combustivel', jsonb_build_object('categoria_id', p_v.categoria_combustivel_id,
                                                   'valor_mensal', nullif(p_v.combustivel_valor_mensal, 0)),
        'preco_medio_combustivel', nullif(p_v.preco_medio_combustivel, 0),
        'uso_estimado', jsonb_build_object('km_estimado_acumulado', coalesce(p_v.km_estimado_acumulado, 0),
                                           'km_estimado_ultimo_calculo_em', financeiro.iso_python(p_v.km_estimado_ultimo_calculo_em)),
        'ipva', jsonb_build_object('categoria_id', p_v.ipva_categoria_id, 'mes', p_v.ipva_mes, 'valor', nullif(p_v.ipva_valor, 0)),
        'seguro', jsonb_build_object('categoria_id', p_v.seguro_categoria_id, 'mes', p_v.seguro_mes, 'valor', nullif(p_v.seguro_valor, 0)),
        'licenciamento', jsonb_build_object('categoria_id', p_v.licenciamento_categoria_id, 'mes', p_v.licenciamento_mes,
                                            'valor', nullif(p_v.licenciamento_valor, 0)),
        'criado_em', financeiro.iso_python(p_v.criado_em), 'atualizado_em', financeiro.iso_python(p_v.atualizado_em),
        'resumo_mensal_estimado', jsonb_build_object(
            'combustivel_mensal', c.comb, 'seguro_mensal_diluido', c.seg, 'ipva_mensal_diluido', c.ipva,
            'licenciamento_mensal_diluido', c.lic, 'manutencao_mensal_media', 0, 'assinatura_mensal', 0,
            'transporte_app_mensal', 0, 'outros_custos_mensais', 0),
        'total_mensal_estimado', c.comb + c.seg + c.ipva + c.lic)
        -- FIN-MVP-MOB-01: so nos veiculos que usam os campos novos (os demais respondem como antes)
        || case when (p_v).combustivel = 'flex' or (p_v).custo_combustivel_modo <> 'MANUAL' or (p_v).km_mensal_estimado is not null
                then jsonb_build_object('autonomia_gasolina_km_l', (p_v).autonomia_gasolina_km_l,
                                        'autonomia_etanol_km_l', (p_v).autonomia_etanol_km_l,
                                        'preco_gasolina', (p_v).preco_gasolina, 'preco_etanol', (p_v).preco_etanol,
                                        'combustivel_referencia', (p_v).combustivel_referencia,
                                        'km_mensal_estimado', (p_v).km_mensal_estimado,
                                        'custo_combustivel_modo', (p_v).custo_combustivel_modo)
                else '{}'::jsonb end
        -- FIN-MVP-MOB-01: ultima leitura real do hodometro, quando ha
        || coalesce((select jsonb_build_object('km_real', a.hodometro_km, 'km_real_data', a.data_abastecimento)
                       from financeiro.abastecimento a where a.veiculo_id = (p_v).id and a.anulado_em is null
                      order by a.data_abastecimento desc, a.hodometro_km desc, a.id desc limit 1), '{}'::jsonb)
        || case when (p_v).em_uso_paralelo then jsonb_build_object('em_uso_paralelo', true) else '{}'::jsonb end
      from (select round(coalesce((p_v).combustivel_valor_mensal, 0), 2) comb,
                   round(coalesce((p_v).seguro_valor, 0) / 12, 2) seg,
                   round(coalesce((p_v).ipva_valor, 0) / 12, 2) ipva,
                   round(coalesce((p_v).licenciamento_valor, 0) / 12, 2) lic) c
$$;

-- uso_do_veiculo: texto de 20261115090000 + os trechos marcados.
create or replace function financeiro.uso_do_veiculo(p_v public.veiculo, p_janela integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_janela  integer := least(greatest(coalesce(p_janela, 3), 1), 12);
    v_fim     date := (date_trunc('month', financeiro.hoje_brasilia()) + interval '1 month')::date;
    v_inicio  date;
    v_por_mes jsonb := '{}'::jsonb;
    v_soma    numeric := 0;
    v_d       record;
    v_km      jsonb;
begin
    v_inicio := (v_fim - make_interval(months => v_janela))::date;
    for v_d in
        select coalesce(d.data_atual_prevista, d.data_prevista) data_ref, md, d.valor_previsto
          from public.despesa_prevista d
          cross join lateral (select financeiro.json_seguro(d.metadata) md) j
         where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_v.perfil_financeiro_id)
           and d.origem_tipo = 'VEICULO' and d.origem_id = p_v.id and d.status = 'CONFIRMADA'
           and d.data_prevista >= v_inicio and d.data_prevista < v_fim
         order by d.id
    loop
        continue when jsonb_typeof(v_d.md) <> 'object' or v_d.md ->> 'tipo_evento' is distinct from 'COMBUSTIVEL';
        declare
            v_litros numeric := financeiro.numero_seguro(v_d.md -> 'litros_abastecidos');
            v_km     numeric;
            v_chave  text := to_char(v_d.data_ref, 'YYYY-MM');
            -- FIN-MVP-MOB-01: parametros gravados na confirmacao (sem eles, os atuais do veiculo, como antes)
            v_aut    numeric := coalesce(financeiro.numero_seguro(v_d.md -> 'autonomia_km_l'), p_v.autonomia_km_l);
            v_preco  numeric := coalesce(financeiro.numero_seguro(v_d.md -> 'preco_litro'), p_v.preco_medio_combustivel);
        begin
            if v_litros is null or v_litros <= 0 then
                v_litros := case when coalesce(v_preco, 0) > 0 and coalesce(v_d.valor_previsto, 0) > 0
                                 then v_d.valor_previsto / v_preco end;
            end if;
            continue when coalesce(v_aut, 0) <= 0 or coalesce(v_litros, 0) <= 0;
            v_km := v_litros * v_aut;
            v_por_mes := v_por_mes || jsonb_build_object(v_chave, coalesce((v_por_mes ->> v_chave)::numeric, 0) + v_km);
            v_soma := v_soma + v_km;
        end;
    end loop;
    -- FIN-MVP-MOB-01: quilometragem real e estimada, so quando ha leitura ou competencia coberta (os demais respondem como antes)
    v_km := financeiro.mob_km_veiculo(p_v, v_soma / v_janela);
    return jsonb_build_object(
        'veiculo_id', p_v.id, 'km_estimado_acumulado', coalesce(p_v.km_estimado_acumulado, 0),
        'km_estimado_ultimo_calculo_em', financeiro.iso_python(p_v.km_estimado_ultimo_calculo_em),
        'janela_meses', v_janela, 'km_por_mes', v_por_mes, 'media_movel_km_mes', v_soma / v_janela,
        'observacao', 'Estimativa baseada em consumo. Pode variar.',
        'preco_medio_combustivel', nullif(p_v.preco_medio_combustivel, 0), 'autonomia_km_l', nullif(p_v.autonomia_km_l, 0))
        || case when v_km ->> 'km_real' is not null or (v_km ->> 'km_estimado')::numeric > 0
                then jsonb_build_object('quilometragem', v_km) else '{}'::jsonb end;
end
$$;

-- mob_inserir_prevista: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.mob_inserir_prevista(p_perfil_id integer, p_origem_tipo text, p_origem_id integer,
                                                 p_categoria_id integer, p_data date, p_valor numeric, p_metadata jsonb)
    returns integer
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista,
                                         data_original_prevista, data_atual_prevista, valor_previsto, status, metadata,
                                         criado_em, atualizado_em, obrigacao, periodo_referencia)
    select p_perfil_id, p_origem_tipo, p_origem_id, p_categoria_id, p_data, p_data, p_data, p_valor, 'PREVISTA',
           p_metadata::text, financeiro.mob_agora(), financeiro.mob_agora(), o.tipo,
           case when o.tipo is not null then financeiro.mob_periodo(o.tipo, p_data) end
      -- FIN-MVP-MOB-01: identidade so das obrigacoes projetadas do veiculo (as de manutencao seguem por ciclo)
      from (select case when p_origem_tipo = 'VEICULO' and p_metadata ->> 'tipo_evento' in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO')
                        then p_metadata ->> 'tipo_evento' end as tipo) o
    returning id
$$;

-- mob_dados_veiculo: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.mob_dados_veiculo(p_atual public.veiculo, p_dados jsonb)
    returns public.veiculo
    language plpgsql
    stable
    set search_path = ''
as $$
declare
    v public.veiculo := p_atual;
    v_novo boolean := p_atual.id is null;
    v_auton numeric;
begin
    if v_novo then
        v.nome := btrim(coalesce(p_dados ->> 'nome', ''));
        v.tipo := btrim(coalesce(p_dados ->> 'tipo', ''));
        v.combustivel := btrim(coalesce(p_dados ->> 'combustivel', ''));
        v.status := upper(btrim(coalesce(nullif(p_dados ->> 'status', ''), 'SIMULADO')));
        v.autonomia_km_l := financeiro.numero_seguro(p_dados -> 'autonomia_km_l');
        -- FIN-MVP-MOB-01: no Flex, a autonomia vem do combustivel de referencia (mob_dados_flex)
        if lower(v.combustivel) = 'flex' then
            v.autonomia_km_l := financeiro.numero_seguro(p_dados -> case lower(coalesce(p_dados ->> 'combustivel_referencia', ''))
                when 'etanol' then 'autonomia_etanol_km_l' else 'autonomia_gasolina_km_l' end);
        end if;
        v.data_inicio := financeiro.mob_data(p_dados ->> 'data_inicio');
        if v.nome = '' then raise exception 'Nome é obrigatório' using errcode = '22023'; end if;
        if v.tipo = '' then raise exception 'Tipo é obrigatório' using errcode = '22023'; end if;
        if v.combustivel = '' then raise exception 'Combustível é obrigatório' using errcode = '22023'; end if;
        if v.autonomia_km_l is null or v.autonomia_km_l <= 0 then
            raise exception 'autonomia_km_l é obrigatório e deve ser > 0' using errcode = '22023';
        end if;
        if v.status not in ('SIMULADO', 'ATIVO') then
            raise exception 'Status inválido (SIMULADO|ATIVO)' using errcode = '22023';
        end if;
        if v.status = 'ATIVO' and v.data_inicio is null then
            raise exception 'data_inicio é obrigatório para veículo ATIVO' using errcode = '22023';
        end if;
        v.combustivel_valor_mensal := financeiro.numero_seguro(p_dados -> 'combustivel_valor_mensal');
        v.ipva_mes := financeiro.mob_inteiro(p_dados -> 'ipva_mes');
        v.ipva_valor := financeiro.numero_seguro(p_dados -> 'ipva_valor');
        v.seguro_mes := financeiro.mob_inteiro(p_dados -> 'seguro_mes');
        v.seguro_valor := financeiro.numero_seguro(p_dados -> 'seguro_valor');
        v.licenciamento_mes := financeiro.mob_inteiro(p_dados -> 'licenciamento_mes');
        v.licenciamento_valor := financeiro.numero_seguro(p_dados -> 'licenciamento_valor');
        v.preco_medio_combustivel := financeiro.numero_seguro(p_dados -> 'preco_medio_combustivel');
    else
        if p_dados ? 'nome' then v.nome := btrim(coalesce(p_dados ->> 'nome', '')); end if;
        if p_dados ? 'tipo' then v.tipo := btrim(coalesce(p_dados ->> 'tipo', '')); end if;
        if p_dados ? 'combustivel' then v.combustivel := btrim(coalesce(p_dados ->> 'combustivel', '')); end if;
        if p_dados ? 'autonomia_km_l' then
            v_auton := financeiro.numero_seguro(p_dados -> 'autonomia_km_l');
            if v_auton is null or v_auton <= 0 then
                raise exception 'autonomia_km_l deve ser > 0' using errcode = '22023';
            end if;
            v.autonomia_km_l := v_auton;
        end if;
        if p_dados ? 'status' then
            v.status := upper(btrim(coalesce(p_dados ->> 'status', '')));
            if v.status not in ('SIMULADO', 'ATIVO') then
                raise exception 'Status inválido (SIMULADO|ATIVO)' using errcode = '22023';
            end if;
        end if;
        if p_dados ? 'data_inicio' then v.data_inicio := financeiro.mob_data(p_dados ->> 'data_inicio'); end if;
        if v.status = 'ATIVO' and v.data_inicio is null then
            raise exception 'data_inicio é obrigatório para veículo ATIVO' using errcode = '22023';
        end if;
        if p_dados ? 'combustivel_valor_mensal' then
            v.combustivel_valor_mensal := financeiro.numero_seguro(p_dados -> 'combustivel_valor_mensal');
        end if;
        if p_dados ? 'ipva_mes' then v.ipva_mes := financeiro.mob_inteiro(p_dados -> 'ipva_mes'); end if;
        if p_dados ? 'ipva_valor' then v.ipva_valor := financeiro.numero_seguro(p_dados -> 'ipva_valor'); end if;
        if p_dados ? 'seguro_mes' then v.seguro_mes := financeiro.mob_inteiro(p_dados -> 'seguro_mes'); end if;
        if p_dados ? 'seguro_valor' then v.seguro_valor := financeiro.numero_seguro(p_dados -> 'seguro_valor'); end if;
        if p_dados ? 'licenciamento_mes' then v.licenciamento_mes := financeiro.mob_inteiro(p_dados -> 'licenciamento_mes'); end if;
        if p_dados ? 'licenciamento_valor' then
            v.licenciamento_valor := financeiro.numero_seguro(p_dados -> 'licenciamento_valor');
        end if;
        if p_dados ? 'preco_medio_combustivel' then
            v.preco_medio_combustivel := financeiro.numero_seguro(p_dados -> 'preco_medio_combustivel');
        end if;
    end if;
    if not (coalesce(v.ipva_mes, 1) between 1 and 12 and coalesce(v.seguro_mes, 1) between 1 and 12
            and coalesce(v.licenciamento_mes, 1) between 1 and 12) then
        raise exception 'Mês deve estar entre 1 e 12' using errcode = '22023';
    end if;
    return financeiro.mob_dados_flex(v, p_dados);  -- FIN-MVP-MOB-01
end
$$;

-- criar_veiculo: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.criar_veiculo(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep jsonb;
    v     public.veiculo;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_rep := financeiro.repeticao_mobilidade(p_chave, p_perfil_id, 'criar_veiculo');
    if v_rep is not null then
        return v_rep;
    end if;
    v := financeiro.mob_dados_veiculo(null::public.veiculo, coalesce(p_dados, '{}'::jsonb));
    insert into public.veiculo (perfil_financeiro_id, nome, tipo, combustivel, autonomia_km_l, status, data_inicio,
                                combustivel_valor_mensal, ipva_mes, ipva_valor, seguro_mes, seguro_valor, licenciamento_mes,
                                licenciamento_valor, preco_medio_combustivel, km_estimado_acumulado, criado_em, atualizado_em,
                                autonomia_gasolina_km_l, autonomia_etanol_km_l, preco_gasolina, preco_etanol,
                                combustivel_referencia, km_mensal_estimado, custo_combustivel_modo, em_uso_paralelo)
    values (p_perfil_id, v.nome, v.tipo, v.combustivel, v.autonomia_km_l, v.status, v.data_inicio,
            v.combustivel_valor_mensal, v.ipva_mes, v.ipva_valor, v.seguro_mes, v.seguro_valor, v.licenciamento_mes,
            v.licenciamento_valor, v.preco_medio_combustivel, 0, financeiro.mob_agora(), financeiro.mob_agora(),
            v.autonomia_gasolina_km_l, v.autonomia_etanol_km_l, v.preco_gasolina, v.preco_etanol,
            v.combustivel_referencia, v.km_mensal_estimado, v.custo_combustivel_modo, v.em_uso_paralelo)
    returning id into v.id;
    perform financeiro.mob_aplicar_categorias(v.id);
    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'criar_veiculo',
        jsonb_build_object('veiculo_id', v.id));
end
$$;

-- editar_veiculo: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.editar_veiculo(p_perfil_id integer, p_veiculo_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v       public.veiculo;
    v_antes public.veiculo;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_antes := financeiro.mob_veiculo(p_perfil_id, p_veiculo_id);
    v := financeiro.mob_dados_veiculo(v_antes, coalesce(p_dados, '{}'::jsonb));
    update public.veiculo
       set nome = v.nome, tipo = v.tipo, combustivel = v.combustivel, autonomia_km_l = v.autonomia_km_l,
           status = v.status, data_inicio = v.data_inicio, combustivel_valor_mensal = v.combustivel_valor_mensal,
           ipva_mes = v.ipva_mes, ipva_valor = v.ipva_valor, seguro_mes = v.seguro_mes, seguro_valor = v.seguro_valor,
           licenciamento_mes = v.licenciamento_mes, licenciamento_valor = v.licenciamento_valor,
           preco_medio_combustivel = v.preco_medio_combustivel, atualizado_em = financeiro.mob_agora(),
           autonomia_gasolina_km_l = v.autonomia_gasolina_km_l, autonomia_etanol_km_l = v.autonomia_etanol_km_l,
           preco_gasolina = v.preco_gasolina, preco_etanol = v.preco_etanol, combustivel_referencia = v.combustivel_referencia,
           km_mensal_estimado = v.km_mensal_estimado, custo_combustivel_modo = v.custo_combustivel_modo,
           em_uso_paralelo = v.em_uso_paralelo
     where id = v.id;
    perform financeiro.mob_aplicar_categorias(v.id);
    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    -- FIN-MVP-MOB-01: o custo novo vale para a recorrencia e so para as ocorrencias futuras elegiveis
    if v.combustivel_valor_mensal is distinct from v_antes.combustivel_valor_mensal and coalesce(v.combustivel_valor_mensal, 0) > 0 then
        perform financeiro.mob_sincronizar_combustivel(p_perfil_id, v.id, v.combustivel_valor_mensal);
    end if;
    -- FIN-MVP-MOB-01: deixou de estar em uso sem ser o cenario: a recorrencia se encerra, como na troca. As contas ja lancadas ficam.
    if v_antes.em_uso_paralelo and not v.em_uso_paralelo and financeiro.mob_situacao_uso(v) <> 'CENARIO' then
        update public.item_despesa i set ativo = false
         where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.origem_tipo = 'VEICULO' and i.origem_id = v.id
           and i.recorrente and i.ativo;
        perform financeiro.mob_restaurar_combustivel(p_perfil_id, v.id);
    end if;
    return jsonb_build_object('veiculo_id', v.id);
end
$$;

-- mob_gerar_projecoes: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.mob_gerar_projecoes(p_perfil_id integer, p_veiculo_id integer, p_meses integer)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_v         public.veiculo;
    v_hoje      date := financeiro.hoje_brasilia();
    v_meses     integer := greatest(coalesce(p_meses, 12), 1);
    v_inicio    date;
    v_fim       date;
    v_perfil    integer;
    v_bloq      text[] := '{}';
    v_d         record;
    v_ref       date;
    v_mantidas  integer[] := '{}';
    v_evento    record;
    v_ano       integer;
begin
    select * into v_v from public.veiculo where id = p_veiculo_id;
    v_inicio := date_trunc('month', greatest(coalesce(v_v.data_inicio, v_hoje), v_hoje))::date;
    v_fim := (v_inicio + make_interval(months => v_meses))::date;
    v_perfil := coalesce(v_v.perfil_financeiro_id, p_perfil_id);

    -- FIN-MVP-MOB-01: competencia em que o usuario ja agiu nao volta. A identidade e a obrigacao + o periodo (mes do combustivel,
    -- ano das anuais), em qualquer data, para mudar o mes do vencimento nao recriar o que ja foi confirmado.
    for v_d in select d.*, financeiro.mob_tipo_evento(d.metadata) tipo from public.despesa_prevista d
                where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                  and d.origem_tipo = 'VEICULO' and d.origem_id = v_v.id
                  and d.status is not null and d.status <> 'PREVISTA'
    loop
        continue when v_d.tipo is null or v_d.tipo not in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO');
        v_bloq := v_bloq || (v_d.tipo || '|' || financeiro.mob_periodo(v_d.tipo, coalesce(v_d.data_original_prevista, v_d.data_prevista)));
        v_bloq := v_bloq || (v_d.tipo || '@' || coalesce(v_d.data_atual_prevista, v_d.data_prevista));
    end loop;

    if coalesce(v_v.combustivel_valor_mensal, 0) > 0 then
        v_ref := v_inicio;
        while v_ref < v_fim loop
            if not (('COMBUSTIVEL|' || v_ref) = any (v_bloq) or ('COMBUSTIVEL@' || v_ref) = any (v_bloq)) then
                v_mantidas := v_mantidas || financeiro.mob_planejar_prevista(v_perfil, p_perfil_id, v_v.id, 'COMBUSTIVEL', v_ref, v_v.combustivel_valor_mensal);
            end if;
            v_ref := (v_ref + interval '1 month')::date;
        end loop;
    end if;

    for v_evento in select * from (values ('IPVA', v_v.ipva_mes, v_v.ipva_valor, 1),
                                          ('SEGURO', v_v.seguro_mes, v_v.seguro_valor, 2),
                                          ('LICENCIAMENTO', v_v.licenciamento_mes, v_v.licenciamento_valor, 3)) e(tipo, mes, valor, ordem)
                     order by ordem
    loop
        continue when not (coalesce(v_evento.mes, 0) between 1 and 12 and coalesce(v_evento.valor, 0) > 0);
        for v_ano in extract(year from v_inicio)::integer .. extract(year from (v_fim - 1))::integer loop
            v_ref := make_date(v_ano, v_evento.mes, 1);
            continue when v_ref < v_inicio or v_ref >= v_fim
                or ((v_evento.tipo || '|' || financeiro.mob_periodo(v_evento.tipo, v_ref)) = any (v_bloq))
                or ((v_evento.tipo || '@' || v_ref) = any (v_bloq));
            v_mantidas := v_mantidas || financeiro.mob_planejar_prevista(v_perfil, p_perfil_id, v_v.id, v_evento.tipo, v_ref, v_evento.valor);
        end loop;
    end loop;

    -- O que deixou de ser projetado na janela sai; o resto fica com o mesmo id.
    delete from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.origem_tipo = 'VEICULO' and d.origem_id = v_v.id and d.status = 'PREVISTA'
       and d.data_prevista >= v_inicio and d.data_prevista < v_fim
       and financeiro.mob_tipo_evento(d.metadata) in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO')
       and not (d.id = any (v_mantidas));
    perform financeiro.mob_suprimir_combustivel(p_perfil_id, v_v.id);
    return cardinality(v_mantidas);
end
$$;

-- ativar_mobilidade: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.ativar_mobilidade(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep      jsonb;
    v_tipo     text := upper(coalesce(p_dados ->> 'tipo_modalidade', ''));
    v_origem   integer := financeiro.mob_inteiro(p_dados -> 'origem_id');
    v_meio     text := nullif(lower(coalesce(p_dados ->> 'meio_pagamento', '')), '');
    v_cartao   integer := financeiro.mob_inteiro(p_dados -> 'cartao_id');
    v_inicio   date := coalesce(financeiro.mob_data(p_dados ->> 'data_inicio'), date_trunc('month', financeiro.hoje_brasilia())::date);
    v_criar    boolean := financeiro.mob_bool(p_dados -> 'criar_recorrencia', true);
    v_anterior public.mobilidade_cenario_ativo;
    v_o        jsonb;
    v_cat      integer;
    v_cc       jsonb;
    v_avisos   jsonb := '[]'::jsonb;
    v_rec      public.item_despesa;
    v_c        public.mobilidade_cenario_ativo;
    v_sup      integer;
    v_troca    jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not financeiro.mob_bool(p_dados -> 'confirmado', false) then
        raise exception 'Envie confirmado=true para prosseguir com a ativacao.' using errcode = '22023';
    end if;
    v_rep := financeiro.repeticao_mobilidade(p_chave, p_perfil_id, 'ativar_mobilidade');
    if v_rep is not null then
        return v_rep;
    end if;
    if v_tipo not in ('VEICULO', 'TRANSPORTE_APP', 'ASSINATURA') then
        raise exception 'tipo_modalidade invalido: %', v_tipo using errcode = '22023';
    end if;
    if v_meio is not null and v_meio not in ('cartao', 'pix', 'boleto', 'dinheiro', 'debito') then
        raise exception 'meio_pagamento invalido: %', v_meio using errcode = '22023';
    end if;
    v_cartao := financeiro.mob_cartao(p_perfil_id, v_cartao);

    -- 1. Modalidade anterior e as recorrencias automaticas dela.
    select * into v_anterior from public.mobilidade_cenario_ativo c
     where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and c.status = 'ATIVO'
     order by c.id limit 1 for update;
    if found then
        update public.item_despesa i set ativo = false
         where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.origem_tipo = v_anterior.tipo_modalidade
           and i.origem_id = v_anterior.origem_id and i.recorrente and i.ativo
           -- FIN-MVP-MOB-01: veiculo em uso paralelo so sai do cenario: a recorrencia dele continua
           and not financeiro.mob_em_uso_paralelo(v_anterior.tipo_modalidade, v_anterior.origem_id);
        update public.mobilidade_cenario_ativo set status = 'INATIVO', updated_at = financeiro.mob_agora()
         where id = v_anterior.id;
        -- FIN-MVP-MOB-01: sem a recorrencia, as previsoes de combustivel suprimidas por ela voltam (exceto as ja cobertas)
        if v_anterior.tipo_modalidade = 'VEICULO' and not financeiro.mob_em_uso_paralelo('VEICULO', v_anterior.origem_id) then
            perform financeiro.mob_restaurar_combustivel(p_perfil_id, v_anterior.origem_id);
        end if;
    end if;

    -- 2. Recorrencia mensal.
    if v_origem is null or v_origem = 0 then
        raise exception 'origem_id (%) e obrigatorio',
            case v_tipo when 'VEICULO' then 'veiculo.id' when 'TRANSPORTE_APP' then 'caminho_id' else 'assinatura.id' end
            using errcode = '22023';
    end if;
    v_o := financeiro.mob_origem(p_perfil_id, v_tipo, v_origem);
    v_cat := financeiro.mob_categoria(v_o ->> 'codigo');
    v_cc := financeiro.mob_resolver_cc(p_perfil_id, v_cartao, v_cat);
    if v_cc ->> 'aviso' is not null then
        v_avisos := v_avisos || (v_cc -> 'aviso');
    end if;
    if v_criar and v_meio is not null and (v_tipo = 'ASSINATURA' or (v_o ->> 'valor')::numeric > 0) then
        select * into v_rec from public.item_despesa i
         where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.origem_tipo = v_tipo
           and i.origem_id = v_origem and i.origem_contexto = v_o ->> 'contexto' and i.recorrente and i.ativo
         order by i.id limit 1 for update;
        if v_rec.id is not null then
            update public.item_despesa
               set valor = (v_o ->> 'valor')::numeric, meio_pagamento = v_meio, cartao_id = v_cartao, categoria_id = v_cat,
                   categoria_cartao_id = (v_cc ->> 'id')::integer, ativo = true
             where id = v_rec.id
            returning * into v_rec;
        else
            insert into public.item_despesa (perfil_financeiro_id, nome, tipo, recorrente, tipo_recorrencia, valor, categoria_id,
                                             categoria_cartao_id, meio_pagamento, cartao_id, data_vencimento, mes_competencia,
                                             ativo, pago, origem_tipo, origem_id, origem_contexto, criado_em)
            values (p_perfil_id, v_o ->> 'rotulo', 'Simples', true, 'mensal', (v_o ->> 'valor')::numeric, v_cat,
                    (v_cc ->> 'id')::integer, v_meio, v_cartao, v_inicio, to_char(v_inicio, 'YYYY-MM'), true, false,
                    v_tipo, v_origem, v_o ->> 'contexto', financeiro.mob_agora())
            returning * into v_rec;
        end if;
        -- O Flask resolve de novo ao criar a recorrencia (criar_recorrencia_*): o aviso nao resolvido sai duas vezes.
        if v_cc ->> 'aviso' is not null then
            v_avisos := v_avisos || (v_cc -> 'aviso');
        end if;
        -- FIN-MVP-MOB-01: a recorrencia passa a ser a fonte unica do combustivel: nao gera competencia ja coberta e as previsoes
        -- deixam de contar (continuam na tela de Mobilidade)
        if v_tipo = 'VEICULO' then
            perform financeiro.mob_dispensar_cobertas(p_perfil_id, v_origem, v_rec);
            v_sup := financeiro.mob_suprimir_combustivel(p_perfil_id, v_origem);
            if v_sup > 0 then
                v_avisos := v_avisos || to_jsonb(v_sup || ' DespesaPrevista(s) suprimida(s) por recorrencia ativa.');
            end if;
        end if;
        if v_tipo = 'TRANSPORTE_APP' then
            update public.despesa_prevista d set status = 'SUPRIMIDA', atualizado_em = financeiro.mob_agora()
             where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'TRANSPORTE_APP'
               and d.origem_id = v_origem and d.status = 'PREVISTA'
               and d.data_prevista >= date_trunc('month', financeiro.hoje_brasilia())::date
               and (coalesce(d.metadata, '') = '' or financeiro.mob_tipo_evento(d.metadata) = 'TRANSPORTE_APP');
            get diagnostics v_sup = row_count;
            if v_sup > 0 then
                v_avisos := v_avisos || to_jsonb(v_sup || ' DespesaPrevista(s) suprimida(s) por recorrencia ativa.');
            end if;
        end if;
    elsif v_criar and v_meio is null and (v_tipo = 'ASSINATURA' or (v_o ->> 'valor')::numeric > 0) then
        v_avisos := v_avisos || to_jsonb('meio_pagamento nao informado — recorrencia de ' || case v_tipo
            when 'VEICULO' then 'combustivel' when 'TRANSPORTE_APP' then 'transporte por app' else 'assinatura' end
            || ' nao foi criada.');
    elsif v_criar and v_tipo <> 'ASSINATURA' then
        v_avisos := v_avisos || to_jsonb(case v_tipo when 'VEICULO' then 'Veiculo sem valor de combustivel — recorrencia nao criada.'
                                                     else 'Caminho sem valor mensal — recorrencia nao criada.' end);
    end if;

    -- 3. Cenario ativo do perfil.
    insert into public.mobilidade_cenario_ativo (perfil_financeiro_id, tipo_modalidade, origem_id, ativo_desde, meio_pagamento,
                                                 cartao_id, categoria_id, categoria_cartao_id, recorrencia_id, status,
                                                 created_at, updated_at)
    values (p_perfil_id, v_tipo, coalesce(v_origem, 0), v_inicio, v_meio, v_cartao, v_cat, (v_cc ->> 'id')::integer, v_rec.id,
            'ATIVO', financeiro.mob_agora(), financeiro.mob_agora())
    returning * into v_c;
    -- FIN-MVP-MOB-01: despesas futuras da modalidade anterior: cada uma com a decisao do usuario, ou nada e gravado
    v_troca := financeiro.mob_aplicar_decisoes(p_perfil_id, v_c, p_dados -> 'decisoes');
    -- A competencia substituida deixou de estar coberta: a previsao do veiculo que saiu volta para a tela de Mobilidade.
    if v_anterior.tipo_modalidade = 'VEICULO' and (v_anterior.tipo_modalidade, v_anterior.origem_id) is distinct from (v_tipo, v_origem)
       and not financeiro.mob_em_uso_paralelo('VEICULO', v_anterior.origem_id) then
        perform financeiro.mob_restaurar_combustivel(p_perfil_id, v_anterior.origem_id);
    end if;
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'ativar_mobilidade', v_troca || jsonb_build_object(
        'cenario', financeiro.mob_cenario_flask(v_c),
        'recorrencia', case when v_rec.id is not null then financeiro.item_despesa_flask(v_rec) end,
        'anterior_inativado', v_anterior.id, 'avisos', v_avisos));
end
$$;

-- previa_mobilidade: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.previa_mobilidade(p_perfil_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_tipo   text := upper(coalesce(p_dados ->> 'tipo_modalidade', ''));
    v_origem integer := financeiro.mob_inteiro(p_dados -> 'origem_id');
    v_meio   text := nullif(lower(coalesce(p_dados ->> 'meio_pagamento', '')), '');
    v_cartao integer := financeiro.mob_inteiro(p_dados -> 'cartao_id');
    v_o      jsonb;
    v_cat    integer;
    v_cc     jsonb;
    v_avisos jsonb := '[]'::jsonb;
    v_rec    jsonb := null;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if v_tipo not in ('VEICULO', 'TRANSPORTE_APP', 'ASSINATURA') then
        raise exception 'tipo_modalidade invalido: %', v_tipo using errcode = '22023';
    end if;
    if v_origem is null or v_origem = 0 then
        raise exception 'origem_id (%) e obrigatorio para tipo_modalidade=%',
            case v_tipo when 'VEICULO' then 'veiculo.id' when 'TRANSPORTE_APP' then 'caminho_id' else 'assinatura.id' end,
            v_tipo using errcode = '22023';
    end if;
    v_o := financeiro.mob_origem(p_perfil_id, v_tipo, v_origem);
    if v_tipo = 'ASSINATURA' and v_o ->> 'status' <> 'ATIVO' then
        v_avisos := v_avisos || to_jsonb('Assinatura esta INATIVA.'::text);
    end if;
    v_cat := financeiro.mob_categoria(v_o ->> 'codigo');
    v_cc := financeiro.mob_resolver_cc(p_perfil_id, v_cartao, v_cat);
    if v_cc ->> 'aviso' is not null then
        v_avisos := v_avisos || (v_cc -> 'aviso');
    end if;
    if v_tipo = 'ASSINATURA' or (v_o ->> 'valor')::numeric > 0 then
        v_rec := jsonb_build_object('nome', v_o ->> 'rotulo', 'valor', (v_o ->> 'valor')::float8, 'tipo_recorrencia', 'mensal',
            'categoria_id', v_cat, 'categoria_cartao_id', v_cc -> 'id', 'meio_pagamento', v_meio, 'cartao_id', v_cartao,
            'origem_tipo', v_tipo, 'origem_id', v_origem, 'origem_contexto', v_o ->> 'contexto');
    else
        v_avisos := v_avisos || to_jsonb(case v_tipo
            when 'VEICULO' then 'Veiculo nao possui valor de combustivel mensal configurado — recorrencia nao sera criada.'
            else 'Caminho sem valor mensal calculado — recorrencia nao sera criada.' end);
    end if;
    return jsonb_build_object('tipo_modalidade', v_tipo, 'origem_id', v_origem, 'nome_origem', v_o ->> 'nome',
        'recorrencia', v_rec,
        'despesas_previstas', case when v_tipo = 'VEICULO'
            then '["IPVA (anual)", "Seguro (anual)", "Licenciamento (anual)", "Parcelas de financiamento (se houver)"]'::jsonb
            else '[]'::jsonb end,
        'avisos', v_avisos)
        -- FIN-MVP-MOB-01: despesas futuras da modalidade anterior a decidir antes de trocar
        || financeiro.mob_conflitos_previa(p_perfil_id, v_tipo, v_origem, financeiro.mob_data(p_dados ->> 'data_inicio'));
end
$$;

-- mob_registrar_combustivel: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.mob_registrar_combustivel(p_perfil_id integer, p_d public.despesa_prevista)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_v      public.veiculo;
    v_md     jsonb := financeiro.json_seguro(p_d.metadata);
    v_litros numeric;
    v_aut    numeric;
    v_preco  numeric;
begin
    if p_d.origem_tipo <> 'VEICULO' or p_d.status <> 'CONFIRMADA' or financeiro.mob_tipo_evento(p_d.metadata) is distinct from 'COMBUSTIVEL' then
        return;
    end if;
    select * into v_v from public.veiculo v where v.id = p_d.origem_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_v.perfil_financeiro_id, p_perfil_id) then
        return;
    end if;
    -- FIN-MVP-MOB-01: os ids das previstas agora sao preservados e a confirmacao e unica (so PREVISTA confirma): confirmar fora de
    -- ordem conta o km; e os parametros sao os gravados na confirmacao
    v_aut := coalesce(financeiro.numero_seguro(v_md -> 'autonomia_km_l'), v_v.autonomia_km_l);
    v_preco := coalesce(financeiro.numero_seguro(v_md -> 'preco_litro'), v_v.preco_medio_combustivel);
    if coalesce(v_aut, 0) <= 0 then
        return;
    end if;
    v_litros := financeiro.numero_seguro(v_md -> 'litros_abastecidos');
    if v_litros is null or v_litros <= 0 then
        v_litros := case when coalesce(v_preco, 0) > 0 and coalesce(p_d.valor_previsto, 0) > 0
                         then p_d.valor_previsto / v_preco end;
    end if;
    if coalesce(v_litros, 0) <= 0 then
        return;
    end if;
    update public.veiculo
       set km_estimado_acumulado = coalesce(km_estimado_acumulado, 0) + v_litros * v_aut,
           km_estimado_ultimo_despesa_prevista_id = greatest(km_estimado_ultimo_despesa_prevista_id, p_d.id),
           km_estimado_ultimo_calculo_em = financeiro.mob_agora()
     where id = v_v.id;
end
$$;

-- confirmar_despesa_prevista: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.confirmar_despesa_prevista(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d       public.despesa_prevista;
    v_meio    text := nullif(lower(btrim(coalesce(p_dados ->> 'meio_pagamento', ''))), '');
    v_cat     integer;
    v_venc    date;
    v_obs     text := nullif(btrim(coalesce(p_dados ->> 'observacao', '')), '');
    v_nome    text;
    v_cartao  integer;
    v_item    integer;
    v_conta   integer;
    v_mes     date;
    v_compra  jsonb;
    v_criada  jsonb := null;
    v_lanc    integer;
    v_veiculo public.veiculo;
    v_tipo    text;
    v_md      jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_d := financeiro.mob_prevista(p_perfil_id, p_id);
    v_tipo := financeiro.mob_tipo_evento(v_d.metadata);
    if v_d.origem_tipo = 'VEICULO' then
        select * into v_veiculo from public.veiculo v where v.id = v_d.origem_id;
    end if;
    if p_dados ? 'meio_pagamento' and v_meio is not null then
        -- FIN-MVP-MOB-01: simulacao nao vira obrigacao real
        if v_veiculo.status = 'SIMULADO' then
            raise exception 'Veículo simulado: efetive o veículo antes de gerar a despesa. Nada foi gravado.'
                using errcode = '22023', hint = 'VEICULO_SIMULADO';
        end if;
        if v_meio not in ('cartao', 'pix', 'boleto', 'dinheiro', 'debito') then
            raise exception 'meio_pagamento inválido: %. Use: cartao, pix, boleto, dinheiro, debito', v_meio using errcode = '22023';
        end if;
        v_cat := coalesce(nullif(financeiro.mob_inteiro(p_dados -> 'categoria_id'), 0), v_d.categoria_id);
        if coalesce(v_cat, 0) = 0 then
            raise exception 'categoria_id é obrigatório para conversão' using errcode = '22023';
        end if;
        v_venc := financeiro.mob_data(coalesce(nullif(p_dados ->> 'data_vencimento', ''),
                                               coalesce(v_d.data_atual_prevista, v_d.data_prevista)::text));
        if v_venc is null then
            raise exception 'data_vencimento inválida' using errcode = '22023';
        end if;
        -- FIN-MVP-MOB-01: com a recorrencia do veiculo, ela e a fonte unica da despesa de combustivel da competencia
        if v_veiculo.id is not null and v_tipo = 'COMBUSTIVEL'
           and financeiro.mob_competencia_coberta(p_perfil_id, v_veiculo.id, date_trunc('month', v_venc::timestamp)::date) then
            raise exception 'O combustível desta competência já é lançado pela recorrência do veículo. Nada foi gravado.'
                using errcode = '22023', hint = 'COMBUSTIVEL_COBERTO';
        end if;
        v_nome := financeiro.mob_rotulo_prevista(v_d);
        if v_meio = 'cartao' then
            v_cartao := financeiro.mob_inteiro(p_dados -> 'cartao_id');
            if v_cartao is null or v_cartao = 0 then
                raise exception 'cartao_id é obrigatório quando meio_pagamento=cartao' using errcode = '22023';
            end if;
            v_compra := financeiro.criar_compra(p_perfil_id, jsonb_build_object(
                'cartao_id', v_cartao, 'categoria_id', v_cat, 'descricao', v_nome, 'valor', v_d.valor_previsto,
                'data_compra', v_venc, 'mes_fatura', to_char(v_venc, 'YYYY-MM-DD'), 'total_parcelas', 1, 'observacoes', v_obs),
                gen_random_uuid());
            v_lanc := (v_compra -> 'lancamentos' ->> 0)::integer;
            v_criada := jsonb_build_object('tipo', 'lancamento_agregado', 'compra', v_compra, 'descricao', v_nome,
                                           'valor', v_d.valor_previsto::float8, 'data_vencimento', v_venc);
        else
            v_mes := date_trunc('month', v_venc)::date;
            insert into public.item_despesa (perfil_financeiro_id, nome, tipo, categoria_id, valor, recorrente, ativo, pago,
                                             tipo_recorrencia, meio_pagamento, data_vencimento, mes_competencia, criado_em)
            values (p_perfil_id, v_nome, 'Simples', v_cat, coalesce(v_d.valor_previsto, 0), false, true, false, 'mensal',
                    v_meio, v_venc, to_char(v_mes, 'YYYY-MM'), financeiro.mob_agora())
            returning id into v_item;
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento,
                                      status_pagamento, is_fatura_cartao, observacoes, debito_automatico, estouro_orcamento,
                                      status_fatura, criado_em)
            values (p_perfil_id, v_item, v_mes, v_nome || case when v_obs is not null then ' — ' || v_obs else '' end,
                    coalesce(v_d.valor_previsto, 0), v_venc, 'Pendente', false, v_obs, false, false, 'ABERTA', financeiro.mob_agora())
            returning id into v_conta;
            v_criada := jsonb_build_object('tipo', 'conta', 'id', v_conta,
                'descricao', v_nome || case when v_obs is not null then ' — ' || v_obs else '' end,
                'valor', coalesce(v_d.valor_previsto, 0)::float8, 'data_vencimento', v_venc);
        end if;
    end if;
    -- FIN-MVP-MOB-01: vinculo com a conta ou compra criada e, no combustivel, os parametros do momento (mudar a autonomia ou o
    -- combustivel de referencia depois nao altera o km ja consolidado)
    v_md := financeiro.json_seguro(v_d.metadata);
    if v_veiculo.id is not null and v_tipo = 'COMBUSTIVEL' and jsonb_typeof(v_md) = 'object' then
        v_md := v_md || jsonb_build_object('combustivel', coalesce(v_veiculo.combustivel_referencia, v_veiculo.combustivel),
                                           'autonomia_km_l', v_veiculo.autonomia_km_l, 'preco_litro', v_veiculo.preco_medio_combustivel);
    end if;
    update public.despesa_prevista
       set status = 'CONFIRMADA', atualizado_em = financeiro.mob_agora(), conta_id = v_conta, lancamento_id = v_lanc,
           metadata = case when v_veiculo.id is not null and v_tipo = 'COMBUSTIVEL' and jsonb_typeof(v_md) = 'object'
                           then v_md::text else metadata end
     where id = v_d.id
    returning * into v_d;
    perform financeiro.mob_registrar_combustivel(p_perfil_id, v_d);
    return jsonb_build_object('despesa_prevista', jsonb_build_object('id', v_d.id, 'status', v_d.status),
                              'entidade_criada', v_criada);
end
$$;

-- veiculo_manutencoes_km_tela: texto de 20261115090000 + os trechos marcados.
create or replace function financeiro.veiculo_manutencoes_km_tela(p_perfil_id integer, p_veiculo_id integer, p_janela integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_v        public.veiculo;
    v_janela   integer := coalesce(p_janela, 3);
    v_hoje     date := financeiro.hoje_brasilia();
    v_km_atual numeric;
    v_km_mes   numeric;
    v_fonte    text;
    v_obs      text;
    v_itens    jsonb := '[]'::jsonb;
    v_total    numeric := 0;
    v_fonte_i  text := 'INDISPONIVEL';
    v_r        public.veiculo_regra_manutencao_km;
    v_rest     numeric;
    v_meses    integer;
    v_data     date;
    v_exist    public.despesa_prevista;
    v_mod      numeric;
    v_km       jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_v := financeiro.veiculo_do_perfil(p_perfil_id, p_veiculo_id);
    if v_v.id is null then
        raise exception 'Veículo não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    -- _calcular_km_mes_estimado: historico (media movel) > projetado (combustivel mensal / preco * autonomia).
    v_km_mes := ((financeiro.uso_do_veiculo(v_v, v_janela)) ->> 'media_movel_km_mes')::numeric;
    -- FIN-MVP-MOB-01: a leitura real do hodometro vem primeiro; a estimativa so completa os dias depois dela
    v_km := financeiro.mob_km_veiculo(v_v, v_km_mes);
    v_km_atual := (v_km ->> 'km_atual')::numeric;
    if v_km ->> 'fonte_km_mes' = 'LEITURAS' then
        v_km_mes := (v_km ->> 'km_mes')::numeric;
        v_fonte := 'LEITURAS';
        v_obs := 'Baseado nas leituras reais do hodômetro.';
    elsif v_km ->> 'fonte_km_mes' = 'CADASTRO' then
        v_km_mes := (v_km ->> 'km_mes')::numeric;
        v_fonte := 'CADASTRO';
        v_obs := 'Baseado na quilometragem mensal informada no veículo. Pode variar.';
    elsif v_km_mes > 0 then
        v_fonte := 'HISTORICO';
        v_obs := 'Baseado no uso estimado (histórico via consumo). Pode variar.';
    elsif coalesce(v_v.combustivel_valor_mensal, 0) > 0 and coalesce(v_v.preco_medio_combustivel, 0) > 0
          and coalesce(v_v.autonomia_km_l, 0) > 0 then
        v_km_mes := v_v.combustivel_valor_mensal / v_v.preco_medio_combustivel * v_v.autonomia_km_l;
        v_fonte := 'PROJETADO';
        v_obs := 'Baseado em uso projetado (combustível mensal, preço médio e autonomia). Pode variar.';
    else
        v_km_mes := 0;
        v_fonte := 'INDISPONIVEL';
        v_obs := 'Sem dados suficientes para estimar uso mensal. Informe combustível mensal e preço médio, ou gere histórico.';
    end if;

    for v_r in select * from public.veiculo_regra_manutencao_km r
                where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id) and r.veiculo_id = v_v.id and r.ativo
                order by r.id
    loop
        select d.* into v_exist from public.despesa_prevista d
         where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
           and d.origem_tipo = 'VEICULO' and d.origem_id = v_v.id and d.status in ('PREVISTA', 'ADIADA', 'CONFIRMADA')
           and financeiro.json_seguro(d.metadata) ->> 'tipo_evento' = v_r.tipo_evento
         order by d.id limit 1;
        -- _calcular_km_restante
        if coalesce(v_r.intervalo_km, 0) <= 0 then
            v_rest := 0;
        elsif v_km_atual <= 0 then
            v_rest := v_r.intervalo_km;
        else
            v_mod := mod(v_km_atual, v_r.intervalo_km::numeric);
            v_rest := case when v_mod = 0 then 0 else v_r.intervalo_km - v_mod end;
        end if;
        v_meses := null;
        v_data := null;
        if v_km_mes > 0 and v_rest > 0 then
            v_meses := ceil(v_rest / v_km_mes)::integer;
            v_data := date_trunc('month', v_hoje + make_interval(months => v_meses))::date;
        elsif v_km_mes > 0 and v_rest = 0 then
            v_meses := 0;
            v_data := date_trunc('month', v_hoje)::date;
        end if;
        v_itens := v_itens || jsonb_build_array(jsonb_build_object(
            'regra_id', v_r.id, 'tipo_evento', v_r.tipo_evento, 'intervalo_km', v_r.intervalo_km,
            'meses_intervalo', v_r.meses_intervalo, 'custo_estimado', v_r.custo_estimado, 'categoria_id', v_r.categoria_id,
            'km_atual_estimado', v_km_atual, 'km_restante', v_rest, 'media_movel_km_mes', v_km_mes,
            'meses_estimados', v_meses, 'data_prevista_estimada', v_data,
            'existe_evento', v_exist.id is not null, 'evento_existente_id', v_exist.id,
            'evento_existente_status', v_exist.status));
        -- calcular_impacto_mensal_manutencao
        if coalesce(v_r.custo_estimado, 0) > 0 then
            if v_km_mes > 0 and coalesce(v_r.intervalo_km, 0) > 0 then
                v_total := v_total + v_r.custo_estimado * (v_km_mes / v_r.intervalo_km);
                v_fonte_i := 'KM';
            elsif coalesce(v_r.meses_intervalo, 0) > 0 then
                v_total := v_total + v_r.custo_estimado / v_r.meses_intervalo;
                if v_fonte_i <> 'KM' then
                    v_fonte_i := 'TEMPO';
                end if;
            end if;
        end if;
    end loop;

    return jsonb_build_object(
        'veiculo_id', v_v.id, 'janela_meses', v_janela, 'observacao', v_obs, 'fonte_uso', v_fonte, 'km_mes_estimado', v_km_mes,
        'regras', coalesce((select jsonb_agg(financeiro.regra_km_flask(r) order by r.id) from public.veiculo_regra_manutencao_km r
                             where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
                               and r.veiculo_id = v_v.id and r.ativo), '[]'::jsonb),
        'estimativas', v_itens, 'impacto_mensal_total', v_total, 'fonte_impacto', v_fonte_i,
        'observacao_impacto', case v_fonte_i when 'KM' then 'Impacto mensal estimado via km (uso estimado/projetado). Pode variar.'
                                             when 'TEMPO' then 'Impacto mensal estimado via intervalo informado (meses). Pode variar.' end,
        'tipos_evento_regras', coalesce((select jsonb_agg(r.tipo_evento order by r.id) from public.veiculo_regra_manutencao_km r
                                          where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
                                            and r.veiculo_id = v_v.id and r.ativo), '[]'::jsonb))
        || case when v_km ->> 'km_real' is not null
                then jsonb_build_object('km_real', v_km -> 'km_real', 'km_real_data', v_km -> 'km_real_data', 'km_estimado', v_km -> 'km_estimado')
                else '{}'::jsonb end;
end
$$;

-- gerar_manutencao_km_veiculo: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.gerar_manutencao_km_veiculo(p_perfil_id integer, p_veiculo_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_regra_id integer := financeiro.mob_inteiro(p_dados -> 'regra_id');
    v          public.veiculo;
    v_r        public.veiculo_regra_manutencao_km;
    v_km_mes   numeric;
    v_atual    numeric;
    v_rest     numeric;
    v_mod      numeric;
    v_data     date;
    v_id       integer;
    v_km       jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if v_regra_id is null or v_regra_id = 0 then
        raise exception 'regra_id é obrigatório' using errcode = '22023';
    end if;
    select * into v from public.veiculo x where x.id = p_veiculo_id for update;
    if not found or not financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Veículo não encontrado' using errcode = '22023';
    end if;
    select * into v_r from public.veiculo_regra_manutencao_km r
     where r.id = v_regra_id and r.veiculo_id = v.id and r.ativo and financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id);
    if not found then
        raise exception 'Regra de manutenção não encontrada' using errcode = '22023';
    end if;
    if exists (select 1 from public.despesa_prevista d
                where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
                  and d.origem_id = v.id and d.status in ('PREVISTA', 'ADIADA', 'CONFIRMADA')
                  and financeiro.mob_tipo_evento(d.metadata) = v_r.tipo_evento) then
        return jsonb_build_object('gerada', false);
    end if;
    -- FIN-MVP-MOB-01: leitura real do hodometro + estimativa so depois dela
    v_km := financeiro.mob_km_veiculo(v, (financeiro.uso_do_veiculo(v, financeiro.mob_meses(p_dados -> 'janela_meses', 3)) ->> 'media_movel_km_mes')::numeric);
    v_km_mes := (v_km ->> 'km_mes')::numeric;
    if v_km_mes <= 0 then
        return jsonb_build_object('gerada', false);
    end if;
    v_atual := (v_km ->> 'km_atual')::numeric;
    if coalesce(v_r.intervalo_km, 0) <= 0 then
        v_rest := 0;
    elsif v_atual <= 0 then
        v_rest := v_r.intervalo_km;
    else
        v_mod := mod(v_atual, v_r.intervalo_km::numeric);
        v_rest := case when v_mod = 0 then 0 else v_r.intervalo_km - v_mod end;
    end if;
    v_data := date_trunc('month', financeiro.hoje_brasilia() + make_interval(months => ceil(v_rest / v_km_mes)::integer))::date;
    v_id := financeiro.mob_inserir_prevista(coalesce(v.perfil_financeiro_id, p_perfil_id), 'VEICULO', v.id,
        financeiro.mob_categoria_evento(v_r.tipo_evento), v_data, v_r.custo_estimado,
        jsonb_build_object('tipo_evento', v_r.tipo_evento, 'intervalo_km', v_r.intervalo_km, 'ciclo_id', null,
                           'ordem_no_ciclo', null));
    return jsonb_build_object('gerada', true, 'data',
        (select financeiro.despesa_prevista_flask(d) from public.despesa_prevista d where d.id = v_id));
end
$$;

-- excluir_veiculo: texto de 20261127090000 + os trechos marcados.
create or replace function financeiro.excluir_veiculo(p_perfil_id integer, p_veiculo_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v public.veiculo;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v := financeiro.mob_veiculo(p_perfil_id, p_veiculo_id);
    if exists (select 1 from public.mobilidade_cenario_ativo c
                where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                  and c.status = 'ATIVO' and c.tipo_modalidade = 'VEICULO' and c.origem_id = v.id) then
        raise exception 'Este veículo é a modalidade de mobilidade ativa. Ative outra modalidade antes de excluir. Nada foi excluído.'
            using errcode = '22023', hint = 'EM_USO';
    end if;
    if exists (select 1 from public.despesa_prevista d
                where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                  and d.origem_tipo = 'VEICULO' and d.origem_id = v.id
                  and (d.status in ('CONFIRMADA', 'ADIADA')
                       or exists (select 1 from public.despesa_prevista_acao_log l
                                   where l.despesa_prevista_id = d.id or l.despesa_prevista_criada_id = d.id))) then
        raise exception 'O veículo tem despesas previstas já confirmadas ou adiadas (histórico). Nada foi excluído.'
            using errcode = '22023', hint = 'COM_HISTORICO';
    end if;
    if exists (select 1 from financeiro.abastecimento a where a.veiculo_id = v.id) then  -- FIN-MVP-MOB-01
        raise exception 'O veículo tem abastecimentos registrados (histórico). Nada foi excluído.'
            using errcode = '22023', hint = 'COM_HISTORICO';
    end if;
    if (financeiro.mob_item_combustivel(p_perfil_id, v.id)).id is not null then
        raise exception 'O veículo tem recorrência de combustível ativa. Tire o uso paralelo antes de excluir. Nada foi excluído.'
            using errcode = '22023', hint = 'EM_USO';
    end if;
    if exists (select 1 from public.veiculo_financiamento f where f.veiculo_id = v.id)
       or exists (select 1 from public.veiculo_regra_manutencao_km r where r.veiculo_id = v.id)
       or exists (select 1 from public.veiculo_ciclo_manutencao c where c.veiculo_id = v.id) then
        raise exception 'Remova antes o financiamento e as regras de manutenção do veículo. Nada foi excluído.'
            using errcode = '22023', hint = 'COM_VINCULOS';
    end if;
    delete from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
       and d.origem_id = v.id;
    delete from public.veiculo where id = v.id;
    return jsonb_build_object('veiculo_id', v.id, 'excluido', true);
end
$$;

-- dashboard_resumo_tela: texto de 20261209090000 + os trechos marcados.
create or replace function financeiro.dashboard_resumo_tela(p_perfil_id integer, p_mes_referencia text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_hoje        date := (now() at time zone 'America/Sao_Paulo')::date;
    v_valor       text := btrim(coalesce(p_mes_referencia, ''));
    v_inicio      date;
    v_fim         date;
    v_dias        integer;
    v_saldo       numeric;
    v_receitas    numeric;
    v_recebidas   numeric;
    v_despesas    numeric;
    v_fat_total   numeric;
    v_fat_qtd     integer;
    v_rec_qtd     integer;
    v_rec_total   numeric;
    v_venc        jsonb;
    v_venc_total  numeric;
    v_categorias  jsonb;
    v_cartoes     jsonb;
    v_lim_total   numeric;
    v_uso_total   numeric;
    v_mobilidade  jsonb;
    v_alertas     jsonb := '[]'::jsonb;
    v_fluxo       jsonb;
    v_prev_mes    numeric;
    v_prev_pend   integer;
    v_prev_conf   integer;
    v_qtd         integer;
    v_venc_hoje   integer;
    v_percentual  numeric;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    -- _periodo_mes: YYYY-MM ou YYYY-MM-DD validos; senao, mes atual.
    if length(v_valor) = 7 then
        v_valor := v_valor || '-01';
    end if;
    begin
        if v_valor ~ '^\d{4}-\d{1,2}-\d{1,2}$' then
            v_inicio := date_trunc('month', v_valor::date)::date;
        end if;
    exception when others then
        v_inicio := null;
    end;
    v_inicio := coalesce(v_inicio, date_trunc('month', v_hoje)::date);
    v_fim := (v_inicio + interval '1 month' - interval '1 day')::date;
    v_dias := extract(day from v_fim)::integer;

    select coalesce(sum(cb.saldo_atual), 0) into v_saldo from public.conta_bancaria cb
     where financeiro.pertence_ao_perfil(cb.perfil_financeiro_id, p_perfil_id) and cb.status = 'ATIVO';
    -- D2: previsto = orcado + recebido sem previsao; o recebido de uma previsao nao soma de novo.
    v_receitas := coalesce((select sum(o.valor_esperado) from public.receita_orcamento o
                             where financeiro.pertence_ao_perfil(o.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', o.mes_referencia) = v_inicio), 0)
                + coalesce((select sum(r.valor_recebido) from public.receita_realizada r
                             where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', r.mes_referencia) = v_inicio and r.orcamento_id is null), 0);
    v_recebidas := coalesce((select sum(r.valor_recebido) from public.receita_realizada r
                              where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
                                and date_trunc('month', r.mes_referencia) = v_inicio), 0);
    v_despesas := coalesce((select sum(c.valor) from public.conta c
                             where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', c.mes_referencia) = v_inicio and c.is_fatura_cartao is not true
                               and c.status_pagamento is distinct from 'Substituida'), 0)  -- FIN-MVP-MOB-01
                + coalesce((select sum(d.valor_previsto) from public.despesa_prevista d
                             where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', d.data_atual_prevista) = v_inicio
                               and d.status in ('PREVISTA', 'ADIADA')
                               and financeiro.prevista_financeira(d.origem_tipo, d.origem_id)), 0);  -- FIN-MVP-MOB-01

    -- _fluxo_caixa: 5 pontos lineares no mes.
    select jsonb_build_object(
               'labels', jsonb_agg(to_char(p.dia, 'FM00') || '/' || to_char(v_inicio, 'MM') order by p.ponto),
               'entradas', jsonb_agg(round(v_receitas * p.ponto / 5, 2) order by p.ponto),
               'saidas', jsonb_agg(round(v_despesas * p.ponto / 5, 2) order by p.ponto),
               'saldo_projetado', jsonb_agg(round(v_saldo + v_receitas * p.ponto / 5 - v_despesas * p.ponto / 5, 2) order by p.ponto),
               'resumo', jsonb_build_object('receitas_previstas', round(v_receitas, 2), 'despesas_previstas', round(v_despesas, 2),
                                            'saldo_final_projetado', round(v_saldo + v_receitas - v_despesas, 2),
                                            'receitas_recebidas', round(v_recebidas, 2),
                                            'diferenca_receitas', round(v_recebidas - v_receitas, 2)),
               'tipo', 'projecao_simplificada')
      into v_fluxo
      from (select g ponto, least(v_dias, 1 + (g - 1) * greatest(1, v_dias / 5)) dia from generate_series(1, 5) g) p;

    -- _total_faturas_periodo (FIN-CARTAO-PREVISTO-EXECUTADO-01: executado atual, sem previsoes pendentes)
    select coalesce(sum(coalesce(nullif(c.valor_consolidado, 0), nullif(financeiro.executado_fatura(c.id), 0), nullif(c.valor_planejado, 0), c.valor, 0)), 0),
           count(*)
      into v_fat_total, v_fat_qtd
      from public.conta c
     where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and c.is_fatura_cartao
       and date_trunc('month', c.mes_referencia) = v_inicio and c.status_pagamento is distinct from 'Pago'
       and c.status_pagamento is not null;

    -- _recorrencias_ativas
    select count(*), coalesce(sum(i.valor), 0) into v_rec_qtd, v_rec_total from public.item_despesa i
     where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.recorrente and i.ativo;

    -- _contas_a_vencer_7_dias (contas e faturas pendentes; 8 primeiras)
    select coalesce(jsonb_agg(jsonb_build_object(
               'id', x.id, 'data', x.data_vencimento, 'descricao', x.descricao,
               'origem', case when x.is_fatura_cartao then 'Fatura' else 'Conta' end, 'valor', round(coalesce(x.valor, 0), 2),
               'tipo', case when x.is_fatura_cartao then 'fatura' else 'despesa' end,
               'status_visual', case when x.data_vencimento = v_hoje then 'vence_hoje' else (x.data_vencimento - v_hoje) || ' dias' end)
           order by x.data_vencimento, x.id), '[]'::jsonb),
           coalesce(sum(coalesce(x.valor, 0)), 0),
           count(*) filter (where x.data_vencimento = v_hoje)
      into v_venc, v_venc_total, v_venc_hoje
      from (select c.* from public.conta c
             where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
               and c.data_vencimento between v_hoje and v_hoje + 7 and c.status_pagamento = 'Pendente'
             order by c.data_vencimento, c.id limit 8) x;

    -- _categorias_cartao: limites ativos + gastos do mes da fatura; 6 maiores gastos.
    with limites as (
        select l.categoria_cartao_id id, sum(coalesce(l.limite_mensal, 0)) limite, min(l.id) ordem
          from public.cartao_categoria_limite l join public.categoria_cartao cc on cc.id = l.categoria_cartao_id
         where financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id) and l.ativo
         group by 1),
    gastos as (
        select la.categoria_cartao_id id, sum(coalesce(la.valor, 0)) gasto
          from public.lancamento_agregado la join public.categoria_cartao cc on cc.id = la.categoria_cartao_id
         where financeiro.pertence_ao_perfil(la.perfil_financeiro_id, p_perfil_id)
           and financeiro.natureza_da_compra(la.total_parcelas, la.is_recorrente, la.item_despesa_id, la.categoria_cartao_id) = 'CATEGORIA'  -- FIN-CARTAO-DESPESAS-FIXAS-01
           and date_trunc('month', la.mes_fatura) = v_inicio
         group by 1),
    juntas as (
        select coalesce(l.id, g.id) id, coalesce(l.limite, 0) limite, coalesce(g.gasto, 0) gasto,
               case when l.id is not null then 0 else 1 end grupo, coalesce(l.ordem, g.id) ordem
          from limites l full join gastos g on g.id = l.id)
    select coalesce(jsonb_agg(jsonb_build_object(
               'categoria_cartao_id', j.id, 'nome', cc.nome, 'cor', cc.cor, 'icone', cc.icone,
               'limite', round(j.limite, 2), 'gasto', round(j.gasto, 2), 'disponivel', round(j.limite - j.gasto, 2),
               'percentual', financeiro.percentual_flask(j.gasto, j.limite),
               'status', financeiro.status_consumo_flask(financeiro.percentual_flask(j.gasto, j.limite)))
           order by j.gasto desc, j.grupo, j.ordem), '[]'::jsonb)
      into v_categorias
      from (select * from juntas order by gasto desc, grupo, ordem limit 6) j
      join public.categoria_cartao cc on cc.id = j.id;

    -- _cartoes_limites: cartoes (Agregador) ativos por nome.
    select coalesce(jsonb_agg(jsonb_build_object(
               'id', k.id, 'nome', k.nome, 'final', k.final, 'limite_total', round(k.limite, 2), 'utilizado', round(k.usado, 2),
               'disponivel', round(k.limite - k.usado, 2), 'percentual', financeiro.percentual_flask(k.usado, k.limite),
               'status', financeiro.status_consumo_flask(financeiro.percentual_flask(k.usado, k.limite)),
               'categorias_vinculadas', k.qtd)
           order by k.nome, k.id), '[]'::jsonb),
           coalesce(sum(k.limite), 0), coalesce(sum(k.usado), 0)
      into v_cartoes, v_lim_total, v_uso_total
      from (select i.id, i.nome,
                   coalesce(right((select cfg.numero_cartao::text from public.config_agregador cfg
                                    where cfg.item_despesa_id = i.id order by cfg.id limit 1), 4), '') final,
                   coalesce((select sum(coalesce(l.limite_mensal, 0)) from public.cartao_categoria_limite l
                              where l.cartao_id = i.id and l.ativo
                                and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)), 0) limite,
                   (select count(*) from public.cartao_categoria_limite l
                     where l.cartao_id = i.id and l.ativo and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)) qtd,
                   coalesce((select sum(la.valor) from public.lancamento_agregado la
                              where la.cartao_id = i.id and financeiro.pertence_ao_perfil(la.perfil_financeiro_id, p_perfil_id)
                                -- FIN-CARTAO-DESPESAS-FIXAS-01: uso dos limites sem as obrigacoes ja contratadas
                                and financeiro.natureza_da_compra(la.total_parcelas, la.is_recorrente, la.item_despesa_id, la.categoria_cartao_id) not in ('PARCELADA', 'FIXA')
                                and date_trunc('month', la.mes_fatura) = v_inicio), 0) usado
              from public.item_despesa i
             where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.tipo = 'Agregador' and i.ativo) k;

    -- _mobilidade_ativa
    select jsonb_build_object(
               'tipo', m.tipo_modalidade,
               'nome', case m.tipo_modalidade when 'VEICULO' then 'Veiculo proprio' when 'TRANSPORTE_APP' then 'Transporte por app'
                                               when 'ASSINATURA' then 'Assinatura' else coalesce(nullif(m.tipo_modalidade, ''), 'Mobilidade') end,
               'custo_mensal', round(coalesce(nullif((select r.valor from public.item_despesa r where r.id = m.recorrencia_id), 0), 0), 2),
               'status', 'ativa',
               'categoria_cartao', (select jsonb_build_object('id', cc.id, 'nome', cc.nome) from public.categoria_cartao cc
                                     where cc.id = m.categoria_cartao_id))
      into v_mobilidade
      from public.mobilidade_cenario_ativo m
     where financeiro.pertence_ao_perfil(m.perfil_financeiro_id, p_perfil_id) and m.status = 'ATIVO'
     order by m.updated_at desc nulls first, m.id desc limit 1;
    v_mobilidade := coalesce(v_mobilidade, jsonb_build_object('tipo', null, 'nome', 'Sem modalidade ativa', 'custo_mensal', 0,
                                                              'status', 'nao_configurada', 'categoria_cartao', null))
                    || jsonb_build_object('alternativas', coalesce((
                           select jsonb_agg(jsonb_build_object('tipo', 'ASSINATURA', 'nome', a.nome,
                                                               'custo_mensal', round(coalesce(a.valor_mensal, 0), 2),
                                                               'status', 'alternativa') order by a.id)
                             from (select * from public.mobilidade_assinatura a
                                    where financeiro.pertence_ao_perfil(a.perfil_financeiro_id, p_perfil_id) and a.status = 'ATIVO'
                                    order by a.id limit 3) a), '[]'::jsonb));

    -- _alertas_operacionais
    if v_venc_hoje > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'vencimento', 'nivel', 'critico',
                                                                      'mensagem', v_venc_hoje || ' vencimento(s) hoje'));
    end if;
    select count(*) into v_qtd from jsonb_array_elements(v_categorias) x where (x ->> 'percentual')::numeric > 80;
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'limite', 'nivel', 'atencao',
                                                                      'mensagem', v_qtd || ' limite(s) acima de 80%'));
    end if;
    select count(*) into v_qtd from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.data_atual_prevista < v_hoje
       and d.status in ('PREVISTA', 'ADIADA')
       and financeiro.prevista_financeira(d.origem_tipo, d.origem_id);  -- FIN-MVP-MOB-01
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'prevista', 'nivel', 'atencao',
                                                                      'mensagem', v_qtd || ' despesa(s) prevista(s) atrasada(s)'));
    end if;
    select count(*) into v_qtd from public.documento_empresarial_metadata dm
     where financeiro.pertence_ao_perfil(dm.perfil_financeiro_id, p_perfil_id) and dm.data_validade < v_hoje;
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'documento_empresarial', 'nivel', 'critico',
                         'mensagem', v_qtd || ' documento(s) empresarial(is) com validade vencida'));
    end if;
    select count(*) into v_qtd from public.documento_empresarial_metadata dm
     where financeiro.pertence_ao_perfil(dm.perfil_financeiro_id, p_perfil_id) and dm.data_validade between v_hoje and v_hoje + 30;
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'documento_empresarial', 'nivel', 'atencao',
                         'mensagem', v_qtd || ' documento(s) empresarial(is) com validade vencendo em 30 dias'));
    end if;

    -- Despesas previstas do mes (D1: so do perfil).
    select coalesce(sum(d.valor_previsto), 0), count(*) filter (where d.status in ('PREVISTA', 'ADIADA')),
           count(*) filter (where d.status = 'CONFIRMADA')
      into v_prev_mes, v_prev_pend, v_prev_conf
      from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.data_atual_prevista between v_inicio and v_fim
       and d.status <> 'SUPRIMIDA'
       and financeiro.prevista_financeira(d.origem_tipo, d.origem_id);  -- FIN-MVP-MOB-01

    v_percentual := financeiro.percentual_flask(v_uso_total, v_lim_total);
    return jsonb_build_object(
        'periodo', jsonb_build_object('mes_referencia', to_char(v_inicio, 'YYYY-MM'), 'inicio', v_inicio, 'fim', v_fim,
                                      'rotulo', to_char(v_inicio, 'MM/YYYY')),
        'kpis', jsonb_build_object(
            'saldo_consolidado', jsonb_build_object('valor', round(v_saldo, 2), 'subtitulo', 'Disponivel em contas', 'tendencia', null),
            'fluxo_projetado_30_dias', jsonb_build_object('valor', v_fluxo -> 'resumo' -> 'saldo_final_projetado',
                                                          'subtitulo', 'Saldo projetado', 'tendencia', null),
            'faturas_em_aberto', jsonb_build_object('valor', round(v_fat_total, 2), 'quantidade_cartoes', v_fat_qtd,
                                                    'subtitulo', v_fat_qtd || ' cartao(s)'),
            'recorrencias_ativas', jsonb_build_object('quantidade', v_rec_qtd, 'valor_mensal', round(v_rec_total, 2),
                                                      'subtitulo', 'fixas e variaveis')),
        'operacional', jsonb_build_object(
            'despesas_previstas_mes', jsonb_build_object('valor', round(v_prev_mes, 2), 'pendentes', v_prev_pend,
                                                         'confirmadas', v_prev_conf,
                                                         'percentual_orcamento', case when v_receitas > 0
                                                             then financeiro.percentual_flask(v_prev_mes, v_receitas) else 0 end),
            'contas_a_vencer_7_dias', jsonb_build_object('valor', round(v_venc_total, 2), 'quantidade', jsonb_array_length(v_venc)),
            'alertas_operacionais', jsonb_build_object('quantidade', jsonb_array_length(v_alertas), 'itens', v_alertas),
            'modalidade_mobilidade_ativa', v_mobilidade),
        'fluxo_caixa', v_fluxo,
        'categorias_cartao', v_categorias,
        'proximos_vencimentos', v_venc,
        'cartoes_limites', jsonb_build_object('itens', v_cartoes, 'limite_total', round(v_lim_total, 2),
                                              'utilizado_total', round(v_uso_total, 2),
                                              'disponivel_total', round(v_lim_total - v_uso_total, 2),
                                              'percentual_total', v_percentual, 'status', financeiro.status_consumo_flask(v_percentual)),
        'mobilidade', v_mobilidade,
        'acoes_rapidas', jsonb_build_array(
            jsonb_build_object('label', 'Confirmar despesas previstas', 'url', '/despesas-previstas'),
            jsonb_build_object('label', 'Importar fatura', 'url', '/importar-cartao'),
            jsonb_build_object('label', 'Gerenciar categorias do cartao', 'url', '/categorias'),
            jsonb_build_object('label', 'Revisar recorrencias', 'url', '/recorrencias'),
            jsonb_build_object('label', 'Gerenciar mobilidade', 'url', '/veiculos')),
        'alertas', v_alertas);
end
$$;

-- saidas_lastro: texto de 20261117090000 + os trechos marcados.
create or replace function financeiro.saidas_lastro(p_perfil_id integer, p_f jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_hoje   date := (now() at time zone 'America/Sao_Paulo')::date;
    v_ano    integer;
    v_mes    integer;
    v_ini    date;
    v_fim    date;
    v_origem text := upper(btrim(coalesce(p_f ->> 'origem', '')));
    v_nat    text := upper(btrim(coalesce(p_f ->> 'natureza', '')));
    v_busca  text := financeiro.texto_sem_acento(p_f ->> 'busca');
    v_minimo numeric := 0;
begin
    if btrim(coalesce(p_f ->> 'ano', '')) ~ '^[+-]?\d{1,9}$' then v_ano := nullif(btrim(p_f ->> 'ano')::integer, 0); end if;
    if btrim(coalesce(p_f ->> 'mes', '')) ~ '^[+-]?\d{1,9}$' then v_mes := btrim(p_f ->> 'mes')::integer; end if;
    v_ano := coalesce(v_ano, extract(year from v_hoje)::integer);
    if v_mes between 1 and 12 then
        v_ini := make_date(v_ano, v_mes, 1);
        v_fim := (v_ini + interval '1 month')::date;
    else
        v_ini := make_date(v_ano, 1, 1);
        v_fim := make_date(v_ano + 1, 1, 1);
    end if;
    begin
        v_minimo := coalesce(nullif(btrim(coalesce(nullif(p_f ->> 'valor_minimo', ''), p_f ->> 'valorMinimo', '')), ''), '0')::numeric;
    exception when others then
        v_minimo := 0;
    end;
    return coalesce((
        with saidas as (
            select 'DESPESA_PREVISTA'::text tipo, d.id, coalesce(d.data_atual_prevista, d.data_prevista) data_saida,
                   coalesce(cat.nome, 'Despesa') || ' - ' || coalesce(d.status, 'None') descricao, d.valor_previsto valor,
                   'Despesa prevista'::text origem, cat.nome categoria, d.status status_pagamento
              from public.despesa_prevista d left join public.categoria cat on cat.id = d.categoria_id
             where d.perfil_financeiro_id = p_perfil_id and d.valor_previsto > 0
               and d.data_atual_prevista >= v_ini and d.data_atual_prevista < v_fim
               and d.status not in ('IGNORADA', 'CANCELADA', 'SUPRIMIDA')
               and financeiro.prevista_financeira(d.origem_tipo, d.origem_id)  -- FIN-MVP-MOB-01
            union all
            select 'CONTA', c.id, coalesce(c.data_pagamento, c.data_vencimento),
                   case when nullif(c.descricao, '') is not null then c.descricao when i.id is not null then i.nome
                        else 'Conta #' || c.id end,
                   c.valor, 'Conta a pagar', cat.nome, c.status_pagamento
              from public.conta c
              left join public.item_despesa i on i.id = c.item_despesa_id
              left join public.categoria cat on cat.id = i.categoria_id
             where c.perfil_financeiro_id = p_perfil_id and c.valor > 0
               and c.data_vencimento >= v_ini and c.data_vencimento < v_fim and c.is_fatura_cartao is not true
               and c.status_pagamento is distinct from 'Substituida'  -- FIN-MVP-MOB-01
            union all
            select 'LANCAMENTO', la.id, la.data_compra, la.descricao, la.valor, 'Lancamento no cartao', cat.nome, 'CARTAO'
              from public.lancamento_agregado la left join public.categoria cat on cat.id = la.categoria_id
             where la.perfil_financeiro_id = p_perfil_id and la.valor > 0 and la.data_compra >= v_ini and la.data_compra < v_fim
               and not financeiro.mob_compra_substituida(la.id)  -- FIN-MVP-MOB-01
            union all
            select 'MOVIMENTO_FINANCEIRO', m.id, m.data_movimento, m.descricao, m.valor,
                   coalesce(nullif(m.origem, ''), 'Movimento financeiro'), null, m.tipo
              from public.movimento_financeiro m
             where m.perfil_financeiro_id = p_perfil_id and m.tipo = 'DEBITO' and m.valor > 0
               and m.data_movimento >= v_ini and m.data_movimento < v_fim
               and m.conta_id is null and m.fatura_id is null
               and not (upper(coalesce(m.origem, '')) = 'TRANSFERENCIA' and m.transferencia_id is not null
                        and exists (select 1 from public.movimento_financeiro t
                                     where t.perfil_financeiro_id = p_perfil_id and t.transferencia_id = m.transferencia_id
                                       and t.tipo = 'CREDITO' and t.id <> m.id))
        ),
        enriquecidas as (
            select s.*, financeiro.natureza_sugerida_lastro(s.categoria, s.descricao) sugerida, v.*, pe.*
              from saidas s
              left join lateral (
                  select vv.id vinculo_id, vv.comprovante_id documento_id, vv.status_lastro v_status, vv.natureza v_nat,
                         vv.observacoes v_obs
                    from public.ir_comprovante_vinculo vv join public.ir_comprovante cc on cc.id = vv.comprovante_id
                   where vv.perfil_financeiro_id = p_perfil_id and vv.ativo and cc.perfil_financeiro_id = p_perfil_id
                     and vv.tipo_entidade = s.tipo and vv.entidade_id = s.id
                   order by vv.created_at desc, vv.id desc limit 1) v on true
              left join lateral (
                  select pp.id pendencia_id, pp.status_lastro p_status, pp.natureza p_nat, pp.observacoes p_obs
                    from public.lastro_financeiro_pendencia pp
                   where pp.perfil_financeiro_id = p_perfil_id and pp.ativo and pp.tipo_entidade = s.tipo and pp.entidade_id = s.id
                   order by pp.updated_at desc, pp.id desc limit 1) pe on true
        ),
        finais as (
            select jsonb_build_object(
                       'tipo_entidade', e.tipo, 'entidade_id', e.id, 'data', e.data_saida, 'descricao', e.descricao,
                       'valor', coalesce(e.valor, 0), 'origem', e.origem, 'categoria', e.categoria,
                       'status_pagamento', e.status_pagamento,
                       'status_lastro', case when e.vinculo_id is not null then e.v_status
                                             when e.pendencia_id is not null then e.p_status else 'SEM_DOCUMENTO' end,
                       'natureza_sugerida', coalesce(nullif(case when e.vinculo_id is not null then e.v_nat
                                                                 when e.pendencia_id is not null then e.p_nat
                                                                 else e.sugerida end, ''), e.sugerida),
                       'possui_documento', e.vinculo_id is not null, 'documento_id', e.documento_id,
                       'vinculo_id', e.vinculo_id, 'pendencia_id', e.pendencia_id,
                       'observacoes', case when e.vinculo_id is not null then e.v_obs when e.pendencia_id is not null then e.p_obs end) j
              from enriquecidas e
        )
        select jsonb_agg(f.j order by f.j ->> 'tipo_entidade', (f.j ->> 'entidade_id')::integer)
          from finais f
         where (v_origem in ('', 'TODOS', 'TODAS')
                or v_origem in (upper(btrim(coalesce(f.j ->> 'origem', ''))), upper(btrim(coalesce(f.j ->> 'tipo_entidade', '')))))
           and (v_nat in ('', 'TODOS', 'TODAS') or upper(btrim(coalesce(f.j ->> 'natureza_sugerida', ''))) = v_nat)
           and (v_busca = '' or strpos(financeiro.texto_sem_acento(concat_ws(' ', coalesce(f.j ->> 'descricao', ''),
                       coalesce(f.j ->> 'categoria', ''), coalesce(f.j ->> 'origem', ''), coalesce(f.j ->> 'natureza_sugerida', ''))),
                       v_busca) > 0)
           and (f.j ->> 'valor')::numeric >= v_minimo), '[]'::jsonb);
end
$$;

-- contas_do_mes: texto de 20261212090000 + os trechos marcados.
create or replace function financeiro.contas_do_mes(p_perfil_id integer, p_mes date)
    returns table (
        id integer, grupo text, nome text, valor numeric, valor_previsto numeric, valor_executado numeric,
        data_vencimento date, data_pagamento date, situacao text, status_pagamento text,
        categoria_nome text, categoria_cor text, cartao_id integer, cartao_nome text,
        numero_parcela integer, total_parcelas integer, debito_automatico boolean
    )
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes date;
    v_hoje date := (now() at time zone 'America/Sao_Paulo')::date;
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null then
        raise exception 'Mes de competencia obrigatorio' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes)::date;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');

    return query
    with contas as (
        select c.*
          from public.conta c
         where (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal))
           and c.status_pagamento is distinct from 'Substituida'  -- FIN-MVP-MOB-01: preservada, fora das despesas do mes
           and (
                (coalesce(c.is_fatura_cartao, false) = false and date_trunc('month', c.mes_referencia) = v_mes)
             or (c.is_fatura_cartao = true and date_trunc('month', c.cartao_competencia) = v_mes)
           )
    ),
    gastos as (
        -- gasto do mes por cartao e categoria de cartao, no perfil (mes_fatura = 1o dia, como no Flask)
        -- FIN-CARTAO-PREVISTO-EXECUTADO-01: total = executado (sem previsao pendente); pendente = previsoes aguardando cobranca
        select l.cartao_id, l.categoria_cartao_id, sum(financeiro.valor_executado_compra(l.valor, sit.s)) as total,
               sum(l.valor) filter (where sit.s = 'PREVISTA') as pendente,
               -- FIN-CARTAO-DESPESAS-FIXAS-01: parceladas e fixas nao consomem o limite da Categoria do Cartao
               sum(l.valor) filter (where financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) = 'CATEGORIA') as total_categoria
          from public.lancamento_agregado l
         cross join lateral (select financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id), l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
         where (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
           and l.mes_fatura = v_mes
         group by l.cartao_id, l.categoria_cartao_id
    ),
    faturas as (
        select c.id,
               -- FIN-CARTAO-NUBANK-CREDITOS-01: executado das compras menos os creditos da fatura (valor a pagar)
               coalesce((select sum(g.total) from gastos g where g.cartao_id = c.item_despesa_id), 0)
                   - financeiro.creditos_fatura(c.id) as executado,
               coalesce((select sum(g.pendente) from gastos g where g.cartao_id = c.item_despesa_id), 0) as pendente,
               coalesce((select sum(greatest(lim.limite_mensal - coalesce(g.total_categoria, 0), 0))
                           from public.cartao_categoria_limite lim
                           left join gastos g
                             on g.cartao_id = lim.cartao_id and g.categoria_cartao_id = lim.categoria_cartao_id
                          where lim.cartao_id = c.item_despesa_id and lim.ativo), 0) as complemento
          from contas c
         where c.is_fatura_cartao = true
    )
    select c.id,
           case when c.is_fatura_cartao then 'FATURA' else 'DESPESA' end,
           c.descricao::text,
           case
               when not coalesce(c.is_fatura_cartao, false) then c.valor
               when c.status_pagamento = 'Pago' then f.executado
               else f.executado + f.pendente + f.complemento
           end,
           case when c.is_fatura_cartao then f.executado + f.pendente + f.complemento end,
           case when c.is_fatura_cartao then f.executado end,
           c.data_vencimento,
           c.data_pagamento,
           case
               when c.status_pagamento = 'Pago' then 'PAGA'
               when c.status_pagamento = 'Atrasado' or c.data_vencimento < v_hoje then 'VENCIDA'
               else 'PENDENTE'
           end,
           coalesce(c.status_pagamento, 'Pendente')::text,
           cat.nome::text,
           cat.cor::text,
           case when c.is_fatura_cartao then c.item_despesa_id end,
           case when c.is_fatura_cartao then item.nome::text end,
           c.numero_parcela,
           c.total_parcelas,
           coalesce(c.debito_automatico, false)
      from contas c
      left join faturas f on f.id = c.id
      left join public.item_despesa item on item.id = c.item_despesa_id
      left join public.categoria cat on cat.id = item.categoria_id
     order by 2, c.data_vencimento, c.descricao, c.id;
end
$$;

-- despesas_diretas_tela: texto de 20261109090000 + os trechos marcados.
create or replace function financeiro.despesas_diretas_tela(p_perfil_id integer)
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
           and not coalesce(c.is_fatura_cartao, false)
           and c.status_pagamento is distinct from 'Substituida'), '[]'::jsonb);  -- FIN-MVP-MOB-01
end
$$;

-- bloqueio_do_pagamento: texto de 20261120090000 + os trechos marcados.
create or replace function financeiro.bloqueio_do_pagamento(p_conta_id integer)
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
    if coalesce(v_conta.is_fatura_cartao, false) then
        return 'Fatura de cartao: pague na tela de cartoes';
    end if;
    if v_conta.status_pagamento = 'Substituida' then  -- FIN-MVP-MOB-01
        return 'Despesa substituida na troca de modalidade de Mobilidade';
    end if;
    -- FIN-CONTRATOS-2: parcelas de consorcio (despesa comum do item 'Consorcio') e de financiamento (sincronizada pela
    -- financeiro.sincronizar_parcela_paga) sao pagas aqui, pelo escritor unico do perfil.
    return null;
end
$$;

-- =====================================================================================================================
-- 4. Privilegios: as funcoes novas sao internas
-- =====================================================================================================================
revoke execute on function financeiro.mob_periodo(text, date) from public, anon, authenticated;
revoke execute on function financeiro.prevista_financeira(text, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_item_combustivel(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_competencia_coberta(integer, integer, date) from public, anon, authenticated;
revoke execute on function financeiro.mob_suprimir_combustivel(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_restaurar_combustivel(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_dispensar_cobertas(integer, integer, public.item_despesa) from public, anon, authenticated;
revoke execute on function financeiro.mob_sincronizar_combustivel(integer, integer, numeric) from public, anon, authenticated;
revoke execute on function financeiro.mob_planejar_prevista(integer, integer, integer, text, date, numeric) from public, anon, authenticated;
revoke execute on function financeiro.mob_dados_flex(public.veiculo, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.mob_situacao_uso(public.veiculo) from public, anon, authenticated;
revoke execute on function financeiro.mob_em_uso_paralelo(text, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_compra_substituida(integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_conflitos_troca(integer, text, integer, date) from public, anon, authenticated;
revoke execute on function financeiro.mob_conflitos_previa(integer, text, integer, date) from public, anon, authenticated;
revoke execute on function financeiro.mob_aplicar_decisoes(integer, public.mobilidade_cenario_ativo, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.mob_validar_hodometro(integer, date, numeric, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_km_veiculo(public.veiculo, numeric) from public, anon, authenticated;
revoke execute on function financeiro.mob_abastecimento_flask(financeiro.abastecimento) from public, anon, authenticated;
revoke execute on function financeiro.mob_dados_abastecimento(integer, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.mob_abastecimento(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_exigir_motivo(jsonb) from public, anon, authenticated;
revoke execute on function financeiro.registrar_abastecimento(integer, jsonb, uuid) from public, anon;
grant execute on function financeiro.registrar_abastecimento(integer, jsonb, uuid) to authenticated;
revoke execute on function financeiro.corrigir_abastecimento(integer, integer, jsonb) from public, anon;
grant execute on function financeiro.corrigir_abastecimento(integer, integer, jsonb) to authenticated;
revoke execute on function financeiro.anular_abastecimento(integer, integer, jsonb) from public, anon;
grant execute on function financeiro.anular_abastecimento(integer, integer, jsonb) to authenticated;
revoke execute on function financeiro.abastecimentos_veiculo_tela(integer, integer) from public, anon;
grant execute on function financeiro.abastecimentos_veiculo_tela(integer, integer) to authenticated;
revoke execute on function financeiro.candidatas_abastecimento(integer, integer) from public, anon;
grant execute on function financeiro.candidatas_abastecimento(integer, integer) to authenticated;
revoke execute on function financeiro.custos_veiculos_tela(integer, date) from public, anon;
grant execute on function financeiro.custos_veiculos_tela(integer, date) to authenticated;
revoke execute on function financeiro.vincular_abastecimento(integer, integer, jsonb) from public, anon;
grant execute on function financeiro.vincular_abastecimento(integer, integer, jsonb) to authenticated;
revoke execute on function financeiro.desvincular_abastecimento(integer, integer) from public, anon;
grant execute on function financeiro.desvincular_abastecimento(integer, integer) to authenticated;
