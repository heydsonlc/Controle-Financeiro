"""Texto SQL de FIN-MVP-MOB-01 (contrato complementar): abastecimentos, quilometragem real e estimada e troca de modalidade.
Usado por scripts/gerar_migration_mobilidade_integridade.py; a migration e a saida do gerador. So texto: nenhuma conexao."""

ESTRUTURA_ABASTECIMENTO = r"""-- =====================================================================================================================
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
"""

AUXILIARES_TROCA = r"""-- =====================================================================================================================
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
"""

AUXILIARES_KM = r"""-- =====================================================================================================================
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
"""

AUXILIARES_ABASTECIMENTO = r"""-- =====================================================================================================================
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
"""

# Funcoes internas (sem execute para ninguem) e as chamadas pelo aplicativo.
INTERNAS_NOVAS = ['mob_situacao_uso(public.veiculo)', 'mob_em_uso_paralelo(text, integer)', 'mob_compra_substituida(integer)',
                  'mob_conflitos_troca(integer, text, integer, date)',
                  'mob_conflitos_previa(integer, text, integer, date)',
                  'mob_aplicar_decisoes(integer, public.mobilidade_cenario_ativo, jsonb)',
                  'mob_validar_hodometro(integer, date, numeric, integer)', 'mob_km_veiculo(public.veiculo, numeric)',
                  'mob_abastecimento_flask(financeiro.abastecimento)', 'mob_dados_abastecimento(integer, jsonb)',
                  'mob_abastecimento(integer, integer)', 'mob_exigir_motivo(jsonb)']
PUBLICAS_NOVAS = ['registrar_abastecimento(integer, jsonb, uuid)', 'corrigir_abastecimento(integer, integer, jsonb)',
                  'anular_abastecimento(integer, integer, jsonb)', 'abastecimentos_veiculo_tela(integer, integer)',
                  'candidatas_abastecimento(integer, integer)', 'custos_veiculos_tela(integer, date)',
                  'vincular_abastecimento(integer, integer, jsonb)',
                  'desvincular_abastecimento(integer, integer)']
