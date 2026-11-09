-- FIN-MVP-MOB-02 (P13): projecoes dinamicas de veiculos. O formulario fixo (combustivel, IPVA, seguro e licenciamento em
-- colunas do veiculo) da lugar a um cadastro de itens por veiculo, com tipo, nome, categoria, valor, frequencia, inicio,
-- termino e situacao. Nenhum valor financeiro muda e nenhuma ocorrencia e criada pela migration.
--
-- - O motor continua o mesmo: despesa_prevista, com a identidade obrigacao + periodo_referencia do FIN-MVP-MOB-01. Cada
--   projecao tem uma obrigacao estavel: COMBUSTIVEL, IPVA, SEGURO e LICENCIAMENTO (as mesmas das ocorrencias ja geradas) ou
--   PROJ:<id> nos itens novos. O periodo segue a frequencia: semana, mes, trimestre, semestre, ano ou unico (data programada).
-- - Regerar atualiza a ocorrencia do mesmo periodo (mesmo id) e nunca toca no que o usuario ja agiu (confirmada, adiada,
--   ignorada, suprimida pela recorrencia) nem em vinculos com contas e compras.
-- - Combustivel: o valor continua no veiculo (manual ou calculado, Flex), com a recorrencia como fonte unica quando ativa.
-- - Conversao: os campos fixos viram itens, com as mesmas competencias, valores e categorias; as colunas do veiculo ficam como
--   espelho dos itens anuais (leitura de transicao) e os campos antigos, quando enviados, gravam pelo mesmo caminho.

-- =====================================================================================================================
-- 1. Estrutura
-- =====================================================================================================================
create table financeiro.veiculo_projecao (
    id                   integer        generated always as identity primary key,
    perfil_financeiro_id integer        not null references public.perfil_financeiro (id),
    veiculo_id           integer        not null references public.veiculo (id),
    tipo                 text           not null check (tipo in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO', 'PNEUS', 'REVISAO',
                                                                 'MANUTENCAO_PREVENTIVA', 'MANUTENCAO_CORRETIVA', 'OUTRO')),
    nome                 text           not null check (length(btrim(nome)) between 1 and 80),
    categoria_id         integer        not null references public.categoria (id),
    valor                numeric(12, 2) check (valor > 0),
    frequencia           text           not null check (frequencia in ('SEMANAL', 'MENSAL', 'TRIMESTRAL', 'SEMESTRAL', 'ANUAL', 'DATA')),
    data_inicio          date,
    data_fim             date,
    ativo                boolean        not null default true,
    obrigacao            text           not null,
    user_id              uuid           references auth.users (id) on delete set null,
    criado_em            timestamptz    not null default now(),
    atualizado_em        timestamptz,
    -- Combustivel: valor e inicio seguem o veiculo (custo manual ou calculado e a recorrencia), sempre mensal.
    check ((tipo = 'COMBUSTIVEL') = (valor is null)),
    check (tipo = 'COMBUSTIVEL' or data_inicio is not null),
    check (tipo <> 'COMBUSTIVEL' or (frequencia = 'MENSAL' and data_inicio is null and data_fim is null)),
    check (tipo not in ('IPVA', 'LICENCIAMENTO') or frequencia = 'ANUAL'),
    check (data_fim is null or (frequencia <> 'DATA' and data_fim >= data_inicio)),
    check (frequencia in ('SEMANAL', 'DATA') or data_inicio = date_trunc('month', data_inicio::timestamp)::date),
    -- A obrigacao e a identidade das ocorrencias: a das quatro antigas (mesmas ocorrencias ja geradas) ou PROJ:<id>.
    check (obrigacao = case when tipo in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO') then tipo else 'PROJ:' || id end)
);
comment on table financeiro.veiculo_projecao is
    'FIN-MVP-MOB-02: despesas projetadas de cada veiculo. Gera ocorrencias em despesa_prevista (obrigacao + periodo), sem segundo motor. So as funcoes gravam.';
comment on column financeiro.veiculo_projecao.obrigacao is
    'Identidade estavel das ocorrencias em despesa_prevista.obrigacao. Nao muda: o tipo e fixo depois de criado.';
comment on column financeiro.veiculo_projecao.valor is
    'Valor de cada ocorrencia (semanal: por semana; anual: integral no mes de cobranca). Combustivel: NULL, o valor e o do veiculo.';
create unique index ux_veiculo_projecao_obrigacao on financeiro.veiculo_projecao (veiculo_id, obrigacao);
alter table financeiro.veiculo_projecao enable row level security;
alter table financeiro.veiculo_projecao force row level security;
revoke all on financeiro.veiculo_projecao from public, anon, authenticated;

-- Rastreabilidade: quem, quando e o item antes e depois. Sem chave estrangeira, para sobreviver a exclusao do item.
create table financeiro.veiculo_projecao_historico (
    id                   bigint      generated always as identity primary key,
    projecao_id          integer     not null,
    veiculo_id           integer     not null,
    perfil_financeiro_id integer     not null,
    acao                 text        not null check (acao in ('CONVERSAO', 'CRIACAO', 'EDICAO', 'ATIVACAO', 'DESATIVACAO', 'EXCLUSAO')),
    antes                jsonb,
    depois               jsonb,
    user_id              uuid        references auth.users (id) on delete set null,
    criado_em            timestamptz not null default now()
);
comment on table financeiro.veiculo_projecao_historico is
    'FIN-MVP-MOB-02: alteracoes relevantes das projecoes (conversao dos campos fixos, criacao, edicao, ativacao, desativacao, exclusao). So as funcoes gravam.';
create index ix_veiculo_projecao_historico on financeiro.veiculo_projecao_historico (veiculo_id, projecao_id, id);
alter table financeiro.veiculo_projecao_historico enable row level security;
alter table financeiro.veiculo_projecao_historico force row level security;
revoke all on financeiro.veiculo_projecao_historico from public, anon, authenticated;

-- =====================================================================================================================
-- 2. Funcoes novas (internas)
-- =====================================================================================================================
-- Periodo da ocorrencia pela frequencia. Mensal e anual coincidem com mob_periodo (combustivel e anuais antigas).
create function financeiro.mob_periodo_frequencia(p_frequencia text, p_data date)
    returns date
    language sql
    immutable
    set search_path = ''
as $$
    select case p_frequencia
               when 'SEMANAL' then date_trunc('week', p_data::timestamp)::date
               when 'MENSAL' then date_trunc('month', p_data::timestamp)::date
               when 'TRIMESTRAL' then date_trunc('quarter', p_data::timestamp)::date
               when 'SEMESTRAL' then make_date(extract(year from p_data)::integer, case when extract(month from p_data) <= 6 then 1 else 7 end, 1)
               when 'ANUAL' then date_trunc('year', p_data::timestamp)::date
               when 'DATA' then date '0001-01-01'  -- ocorrencia unica: depois de agir, nao volta em outra data
           end
$$;

create function financeiro.mob_rotulo_tipo_projecao(p_tipo text)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select case p_tipo when 'COMBUSTIVEL' then 'Combustível' when 'IPVA' then 'IPVA' when 'SEGURO' then 'Seguro'
                       when 'LICENCIAMENTO' then 'Licenciamento' when 'PNEUS' then 'Pneus' when 'REVISAO' then 'Revisão programada'
                       when 'MANUTENCAO_PREVENTIVA' then 'Manutenção preventiva' when 'MANUTENCAO_CORRETIVA' then 'Manutenção corretiva'
                       else 'Outra despesa' end
$$;

-- Valor de cada ocorrencia: o do item; no combustivel, o do veiculo.
create function financeiro.mob_valor_projecao(p_p financeiro.veiculo_projecao, p_v public.veiculo)
    returns numeric
    language sql
    stable
    set search_path = ''
as $$
    select case when p_p.tipo = 'COMBUSTIVEL' then nullif(p_v.combustivel_valor_mensal, 0) else p_p.valor end
$$;

-- Custo medio mensal informativo (nao e uma segunda despesa): o anual dividido por 12 e assim por diante. Data programada nao
-- e recorrente e fica fora da media. Item encerrado ou inativo: zero.
create function financeiro.mob_media_mensal_projecao(p_p financeiro.veiculo_projecao, p_v public.veiculo)
    returns numeric
    language sql
    stable
    set search_path = ''
as $$
    select case when not p_p.ativo or (p_p.data_fim is not null and p_p.data_fim < date_trunc('month', financeiro.hoje_brasilia())::date) then 0
                else coalesce(case p_p.frequencia
                                  when 'SEMANAL' then round(x.valor * 52 / 12, 2) when 'MENSAL' then round(x.valor, 2)
                                  when 'TRIMESTRAL' then round(x.valor / 3, 2) when 'SEMESTRAL' then round(x.valor / 6, 2)
                                  when 'ANUAL' then round(x.valor / 12, 2) else 0 end, 0) end
      from (select financeiro.mob_valor_projecao(p_p, p_v) as valor) x
$$;

-- Datas das ocorrencias do item entre p_inicio (inclusive, inicio de mes) e p_fim (exclusive), respeitando o termino. Data
-- programada: a propria data, se nao for anterior a p_inicio (sem limite final: e uma so).
create function financeiro.mob_datas_projecao(p_p financeiro.veiculo_projecao, p_inicio date, p_fim date)
    returns setof date
    language plpgsql
    stable
    set search_path = ''
as $$
declare
    v_d     date := coalesce(p_p.data_inicio, p_inicio);
    v_passo integer := case p_p.frequencia when 'TRIMESTRAL' then 3 when 'SEMESTRAL' then 6 when 'ANUAL' then 12 else 1 end;
    v_k     integer;
begin
    if p_p.frequencia = 'DATA' then
        if p_p.data_inicio >= p_inicio then
            return next p_p.data_inicio;
        end if;
        return;
    end if;
    if v_d < p_inicio then
        if p_p.frequencia = 'SEMANAL' then
            v_d := v_d + (ceil((p_inicio - v_d) / 7.0)::integer * 7);
        else
            v_k := ((extract(year from p_inicio) - extract(year from v_d)) * 12 + extract(month from p_inicio) - extract(month from v_d))::integer;
            v_d := (v_d + make_interval(months => ceil(v_k::numeric / v_passo)::integer * v_passo))::date;
        end if;
    end if;
    while v_d < p_fim and (p_p.data_fim is null or v_d <= p_p.data_fim) loop
        return next v_d;
        v_d := case when p_p.frequencia = 'SEMANAL' then v_d + 7 else (v_d + make_interval(months => v_passo))::date end;
    end loop;
end
$$;

-- Atualiza a ocorrencia PREVISTA do mesmo periodo (mesmo id) ou cria. As quatro obrigacoes antigas gravam o metadata de antes;
-- os itens novos levam tambem o id e o nome do item.
create function financeiro.mob_planejar_projecao(p_perfil_destino integer, p_perfil_id integer, p_p financeiro.veiculo_projecao,
                                                 p_data date, p_valor numeric)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_id      integer;
    v_periodo date := financeiro.mob_periodo_frequencia(p_p.frequencia, p_data);
    v_md      jsonb := jsonb_build_object('tipo_evento', p_p.tipo, 'ciclo_id', null, 'ordem_no_ciclo', null)
                       || case when p_p.tipo in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO') then '{}'::jsonb
                               else jsonb_build_object('projecao_id', p_p.id, 'nome', p_p.nome, 'frequencia', p_p.frequencia) end;
begin
    select d.id into v_id from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
       and d.origem_id = p_p.veiculo_id and d.status = 'PREVISTA' and d.obrigacao = p_p.obrigacao
       and d.periodo_referencia = v_periodo
     for update;
    if v_id is null then
        insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista,
                                             data_original_prevista, data_atual_prevista, valor_previsto, status, metadata,
                                             criado_em, atualizado_em, obrigacao, periodo_referencia)
        values (p_perfil_destino, 'VEICULO', p_p.veiculo_id, p_p.categoria_id, p_data, p_data, p_data, p_valor, 'PREVISTA',
                v_md::text, financeiro.mob_agora(), financeiro.mob_agora(), p_p.obrigacao, v_periodo)
        returning id into v_id;
        return v_id;
    end if;
    update public.despesa_prevista d
       set data_prevista = p_data, data_original_prevista = p_data, data_atual_prevista = p_data, valor_previsto = p_valor,
           categoria_id = p_p.categoria_id, atualizado_em = financeiro.mob_agora()
     where d.id = v_id and (d.data_prevista, d.valor_previsto, d.categoria_id) is distinct from (p_data, p_valor, p_p.categoria_id);
    -- item novo renomeado: o rotulo das ocorrencias ainda abertas acompanha
    update public.despesa_prevista d set metadata = v_md::text
     where d.id = v_id and p_p.tipo not in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO')
       and financeiro.json_seguro(d.metadata) is distinct from v_md;
    return v_id;
end
$$;

create function financeiro.mob_historico_projecao(p_acao text, p_antes financeiro.veiculo_projecao, p_depois financeiro.veiculo_projecao)
    returns void
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into financeiro.veiculo_projecao_historico (projecao_id, veiculo_id, perfil_financeiro_id, acao, antes, depois, user_id)
    select coalesce(p_depois.id, p_antes.id), coalesce(p_depois.veiculo_id, p_antes.veiculo_id),
           coalesce(p_depois.perfil_financeiro_id, p_antes.perfil_financeiro_id), p_acao,
           case when p_antes.id is not null then to_jsonb(p_antes) end, case when p_depois.id is not null then to_jsonb(p_depois) end,
           (select auth.uid())
$$;

-- Primeira ocorrencia anual a partir do mes de inicio da janela do veiculo (o mes de cobranca do formulario antigo).
create function financeiro.mob_inicio_anual(p_v public.veiculo, p_mes integer)
    returns date
    language sql
    stable
    set search_path = ''
as $$
    select case when make_date(extract(year from b.base)::integer, p_mes, 1) < b.base
                then make_date(extract(year from b.base)::integer + 1, p_mes, 1)
                else make_date(extract(year from b.base)::integer, p_mes, 1) end
      from (select date_trunc('month', greatest(coalesce(p_v.data_inicio, financeiro.hoje_brasilia()), financeiro.hoje_brasilia())::timestamp)::date as base) b
$$;

-- Insere o item com a obrigacao certa (o id e conhecido antes, para PROJ:<id>).
create function financeiro.mob_inserir_projecao(p_p financeiro.veiculo_projecao)
    returns financeiro.veiculo_projecao
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v financeiro.veiculo_projecao := p_p;
begin
    v.id := nextval(pg_get_serial_sequence('financeiro.veiculo_projecao', 'id'));
    v.obrigacao := case when v.tipo in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO') then v.tipo else 'PROJ:' || v.id end;
    insert into financeiro.veiculo_projecao (id, perfil_financeiro_id, veiculo_id, tipo, nome, categoria_id, valor, frequencia,
                                             data_inicio, data_fim, ativo, obrigacao, user_id)
    overriding system value
    values (v.id, v.perfil_financeiro_id, v.veiculo_id, v.tipo, v.nome, v.categoria_id, v.valor, v.frequencia, v.data_inicio,
            v.data_fim, coalesce(v.ativo, true), v.obrigacao, (select auth.uid()))
    returning * into v;
    return v;
end
$$;

-- Conversao dos campos fixos em itens: combustivel (sempre, valor do veiculo) e IPVA, seguro e licenciamento anuais quando ha
-- mes e valor, como o gerador antigo os projetava. Mesmas obrigacoes, categorias sistemicas e meses: as ocorrencias ja geradas
-- continuam sendo as deste item. So age em veiculo ainda sem itens (idempotente).
create function financeiro.mob_converter_legado(p_perfil_id integer, p_veiculo_id integer)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v       public.veiculo;
    v_p     financeiro.veiculo_projecao;
    v_e     record;
    v_n     integer := 0;
    v_desde date;
begin
    if exists (select 1 from financeiro.veiculo_projecao p where p.veiculo_id = p_veiculo_id) then
        return 0;
    end if;
    select * into v from public.veiculo where id = p_veiculo_id;
    if v.id is null or coalesce(v.perfil_financeiro_id, p_perfil_id) is null then
        return 0;
    end if;
    v_p := null;
    v_p.perfil_financeiro_id := coalesce(v.perfil_financeiro_id, p_perfil_id);
    v_p.veiculo_id := v.id;
    v_p.tipo := 'COMBUSTIVEL';
    v_p.nome := financeiro.mob_rotulo_tipo_projecao('COMBUSTIVEL');
    v_p.categoria_id := financeiro.mob_categoria_evento('COMBUSTIVEL');
    v_p.frequencia := 'MENSAL';
    v_p.ativo := true;
    v_p := financeiro.mob_inserir_projecao(v_p);
    perform financeiro.mob_historico_projecao('CONVERSAO', null, v_p);
    v_n := 1;
    for v_e in select * from (values ('IPVA', v.ipva_mes, v.ipva_valor, 1), ('SEGURO', v.seguro_mes, v.seguro_valor, 2),
                                     ('LICENCIAMENTO', v.licenciamento_mes, v.licenciamento_valor, 3)) e(tipo, mes, valor, ordem)
                order by ordem
    loop
        continue when not (coalesce(v_e.mes, 0) between 1 and 12 and coalesce(v_e.valor, 0) > 0);
        -- inicio: a primeira ocorrencia ja gerada (qualquer situacao), ou a proxima cobranca a partir da janela
        select min(coalesce(d.data_original_prevista, d.data_prevista)) into v_desde from public.despesa_prevista d
         where d.origem_tipo = 'VEICULO' and d.origem_id = v.id and d.obrigacao = v_e.tipo;
        v_p := null;
        v_p.perfil_financeiro_id := coalesce(v.perfil_financeiro_id, p_perfil_id);
        v_p.veiculo_id := v.id;
        v_p.tipo := v_e.tipo;
        v_p.nome := financeiro.mob_rotulo_tipo_projecao(v_e.tipo);
        v_p.categoria_id := financeiro.mob_categoria_evento(v_e.tipo);
        v_p.valor := v_e.valor;
        v_p.frequencia := 'ANUAL';
        v_p.data_inicio := least(date_trunc('month', v_desde::timestamp)::date, financeiro.mob_inicio_anual(v, v_e.mes));
        v_p.ativo := true;
        v_p := financeiro.mob_inserir_projecao(v_p);
        perform financeiro.mob_historico_projecao('CONVERSAO', null, v_p);
        v_n := v_n + 1;
    end loop;
    return v_n;
end
$$;

-- As colunas antigas do veiculo ficam como espelho dos itens anuais (leitura de transicao). Item inativo, removido ou fora do
-- formato antigo (outra frequencia ou com termino): sem valor.
create function financeiro.mob_espelhar_legado(p_veiculo_id integer)
    returns void
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    update public.veiculo v
       set ipva_valor = case when nullif(v.ipva_valor, 0) is not distinct from e.ipva_valor then v.ipva_valor else e.ipva_valor end,
           ipva_mes = coalesce(e.ipva_mes, v.ipva_mes),
           seguro_valor = case when nullif(v.seguro_valor, 0) is not distinct from e.seguro_valor then v.seguro_valor else e.seguro_valor end,
           seguro_mes = coalesce(e.seguro_mes, v.seguro_mes),
           licenciamento_valor = case when nullif(v.licenciamento_valor, 0) is not distinct from e.lic_valor then v.licenciamento_valor else e.lic_valor end,
           licenciamento_mes = coalesce(e.lic_mes, v.licenciamento_mes)
      from (select max(p.valor) filter (where p.obrigacao = 'IPVA') as ipva_valor,
                   max(extract(month from p.data_inicio)::integer) filter (where p.obrigacao = 'IPVA') as ipva_mes,
                   max(p.valor) filter (where p.obrigacao = 'SEGURO') as seguro_valor,
                   max(extract(month from p.data_inicio)::integer) filter (where p.obrigacao = 'SEGURO') as seguro_mes,
                   max(p.valor) filter (where p.obrigacao = 'LICENCIAMENTO') as lic_valor,
                   max(extract(month from p.data_inicio)::integer) filter (where p.obrigacao = 'LICENCIAMENTO') as lic_mes
              from financeiro.veiculo_projecao p
             where p.veiculo_id = p_veiculo_id and p.ativo and p.frequencia = 'ANUAL' and p.data_fim is null) e
     where v.id = p_veiculo_id
$$;

-- Campos antigos enviados no cadastro do veiculo (formulario do Flask ou tela anterior): gravam pelo mesmo caminho dos itens.
-- Mudou o mes ou o valor de um tipo anual: atualiza o item (ou cria); sem valor: desativa. Item fora do formato antigo e recusado.
create function financeiro.mob_projecao_legada(p_perfil_id integer, p_v public.veiculo, p_tipo text, p_mes integer, p_valor numeric)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_p     financeiro.veiculo_projecao;
    v_antes financeiro.veiculo_projecao;
begin
    select * into v_antes from financeiro.veiculo_projecao p where p.veiculo_id = p_v.id and p.obrigacao = p_tipo for update;
    if coalesce(p_mes, 0) between 1 and 12 and coalesce(p_valor, 0) > 0 then
        if v_antes.id is null then
            v_p := null;
            v_p.perfil_financeiro_id := coalesce(p_v.perfil_financeiro_id, p_perfil_id);
            v_p.veiculo_id := p_v.id;
            v_p.tipo := p_tipo;
            v_p.nome := financeiro.mob_rotulo_tipo_projecao(p_tipo);
            v_p.categoria_id := financeiro.mob_categoria_evento(p_tipo);
            v_p.valor := p_valor;
            v_p.frequencia := 'ANUAL';
            v_p.data_inicio := financeiro.mob_inicio_anual(p_v, p_mes);
            v_p.ativo := true;
            v_p := financeiro.mob_inserir_projecao(v_p);
            perform financeiro.mob_historico_projecao('CRIACAO', null, v_p);
            return;
        end if;
        if v_antes.frequencia <> 'ANUAL' or v_antes.data_fim is not null then
            raise exception '% deste veículo está na lista de Projeções com outra periodicidade: altere por lá. Nada foi gravado.',
                financeiro.mob_rotulo_tipo_projecao(p_tipo) using errcode = '22023', hint = 'PROJECAO_DINAMICA';
        end if;
        update financeiro.veiculo_projecao p
           set valor = p_valor, ativo = true, atualizado_em = now(),
               data_inicio = case when extract(month from p.data_inicio) = p_mes then p.data_inicio else financeiro.mob_inicio_anual(p_v, p_mes) end
         where p.id = v_antes.id
        returning * into v_p;
        perform financeiro.mob_historico_projecao('EDICAO', v_antes, v_p);
    elsif v_antes.id is not null and v_antes.ativo then
        update financeiro.veiculo_projecao p set ativo = false, atualizado_em = now() where p.id = v_antes.id returning * into v_p;
        perform financeiro.mob_historico_projecao('DESATIVACAO', v_antes, v_p);
    end if;
end
$$;

-- O veiculo tem item fora do formato antigo? Entao os totais e a lista saem dos itens (os demais respondem como antes).
create function financeiro.mob_projecoes_dinamicas(p_veiculo_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (select 1 from financeiro.veiculo_projecao p
                    where p.veiculo_id = p_veiculo_id
                      and (p.tipo not in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO')
                           or (p.tipo = 'COMBUSTIVEL' and not p.ativo)
                           or (p.tipo <> 'COMBUSTIVEL' and (p.frequencia <> 'ANUAL' or p.data_fim is not null))))
$$;

create function financeiro.mob_projecao(p_perfil_id integer, p_id integer)
    returns financeiro.veiculo_projecao
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_p financeiro.veiculo_projecao;
begin
    select * into v_p from financeiro.veiculo_projecao p where p.id = p_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_p.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Projeção não encontrada' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return v_p;
end
$$;

-- Ocorrencias do item que nao podem ser apagadas: o usuario agiu (confirmada, adiada, ignorada, suprimida pela recorrencia),
-- ha vinculo com conta ou compra, ou ha registro de acao.
create function financeiro.mob_protegidas_projecao(p_p financeiro.veiculo_projecao)
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select count(*)::integer from public.despesa_prevista d
     where d.origem_tipo = 'VEICULO' and d.origem_id = p_p.veiculo_id and d.obrigacao = p_p.obrigacao
       and (d.status <> 'PREVISTA' or d.conta_id is not null or d.lancamento_id is not null
            or exists (select 1 from public.despesa_prevista_acao_log l where l.despesa_prevista_id = d.id or l.despesa_prevista_criada_id = d.id))
$$;

-- Item para a tela: valor, periodicidade, proxima ocorrencia, situacao e se pode ser excluido.
create function financeiro.mob_projecao_tela(p_p financeiro.veiculo_projecao, p_v public.veiculo)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_p.id, 'veiculo_id', p_p.veiculo_id, 'tipo', p_p.tipo, 'nome', p_p.nome, 'categoria_id', p_p.categoria_id,
        'categoria_nome', (select c.nome from public.categoria c where c.id = p_p.categoria_id),
        'valor', financeiro.mob_valor_projecao(p_p, p_v), 'valor_segue_veiculo', p_p.tipo = 'COMBUSTIVEL',
        'custo_calculado', p_p.tipo = 'COMBUSTIVEL' and p_v.custo_combustivel_modo = 'CALCULADO',
        'frequencia', p_p.frequencia, 'data_inicio', p_p.data_inicio, 'data_fim', p_p.data_fim, 'ativo', p_p.ativo,
        'media_mensal', financeiro.mob_media_mensal_projecao(p_p, p_v),
        'proxima_ocorrencia', coalesce(o.data, t.data), 'proxima_situacao', coalesce(o.status, case when t.data is not null then 'A_GERAR' end),
        'protegidas', pr.n, 'pode_excluir', p_p.tipo <> 'COMBUSTIVEL' and pr.n = 0,
        'motivo_exclusao', case when p_p.tipo = 'COMBUSTIVEL' then 'O combustível segue o cadastro do veículo: desative para não projetar.'
                                when pr.n > 0 then 'Há ocorrências confirmadas, adiadas, ignoradas ou vinculadas: desative em vez de excluir.' end)
      from (select financeiro.mob_protegidas_projecao(p_p) as n) pr
      left join lateral (select coalesce(d.data_atual_prevista, d.data_prevista) as data, d.status from public.despesa_prevista d
                          where d.origem_tipo = 'VEICULO' and d.origem_id = p_p.veiculo_id and d.obrigacao = p_p.obrigacao
                            and d.status in ('PREVISTA', 'ADIADA', 'SUPRIMIDA')
                            and coalesce(d.data_atual_prevista, d.data_prevista) >= date_trunc('month', financeiro.hoje_brasilia())::date
                          order by 1, d.id limit 1) o on true
      left join lateral (select x as data from financeiro.mob_datas_projecao(p_p, date_trunc('month', financeiro.hoje_brasilia())::date,
                                                                             (date_trunc('month', financeiro.hoje_brasilia()) + interval '10 years')::date) x
                          where p_p.ativo and coalesce(financeiro.mob_valor_projecao(p_p, p_v), 0) > 0
                          order by 1 limit 1) t on true
$$;

-- Validacao do item (novo ou editado). O tipo e fixo depois de criado (a obrigacao nao muda).
create function financeiro.mob_dados_projecao(p_atual financeiro.veiculo_projecao, p_v public.veiculo, p_dados jsonb)
    returns financeiro.veiculo_projecao
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    p      financeiro.veiculo_projecao := p_atual;
    v_novo boolean := p_atual.id is null;
    v_tipo text := nullif(upper(btrim(coalesce(p_dados ->> 'tipo', ''))), '');
    v_cat  integer;
    v_txt  text;
begin
    if v_novo then
        if v_tipo is null or v_tipo not in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO', 'PNEUS', 'REVISAO',
                                            'MANUTENCAO_PREVENTIVA', 'MANUTENCAO_CORRETIVA', 'OUTRO') then
            raise exception 'Escolha o tipo da despesa' using errcode = '22023';
        end if;
        p.tipo := v_tipo;
        p.veiculo_id := p_v.id;
        p.perfil_financeiro_id := p_v.perfil_financeiro_id;
        p.ativo := true;
    elsif v_tipo is not null and v_tipo <> p.tipo then
        raise exception 'O tipo não muda depois de criado: crie outra projeção. Nada foi gravado.' using errcode = '22023';
    end if;
    if v_novo or p_dados ? 'nome' then
        p.nome := nullif(btrim(coalesce(p_dados ->> 'nome', '')), '');
        if p.nome is null and v_novo then
            p.nome := financeiro.mob_rotulo_tipo_projecao(p.tipo);
        elsif p.nome is null then
            raise exception 'Informe o nome da despesa' using errcode = '22023';
        end if;
        if length(p.nome) > 80 then
            raise exception 'O nome deve ter até 80 caracteres' using errcode = '22023';
        end if;
    end if;
    if v_novo or p_dados ? 'categoria_id' then
        v_cat := financeiro.mob_inteiro(p_dados -> 'categoria_id');
        if v_cat is null and v_novo then
            v_cat := financeiro.mob_categoria_evento(p.tipo);
        end if;
        if v_cat is null or not exists (select 1 from public.categoria c where c.id = v_cat and c.ativo is not false) then
            raise exception 'Categoria inválida ou inativa' using errcode = '22023';
        end if;
        p.categoria_id := v_cat;
    end if;
    if v_novo or p_dados ? 'valor' then
        p.valor := financeiro.numero_seguro(p_dados -> 'valor');
        if p.valor is null or p.valor <= 0 then
            raise exception 'Informe o valor estimado (maior que zero)' using errcode = '22023';
        end if;
        if p.valor > 9999999999 then
            raise exception 'Valor estimado muito alto' using errcode = '22023';
        end if;
        p.valor := round(p.valor, 2);
    end if;
    if v_novo or p_dados ? 'frequencia' then
        p.frequencia := nullif(upper(btrim(coalesce(p_dados ->> 'frequencia', ''))), '');
        if p.frequencia is null and p.tipo in ('IPVA', 'LICENCIAMENTO') then
            p.frequencia := 'ANUAL';
        end if;
        if p.frequencia is null or p.frequencia not in ('SEMANAL', 'MENSAL', 'TRIMESTRAL', 'SEMESTRAL', 'ANUAL', 'DATA') then
            raise exception 'Escolha a periodicidade (semanal, mensal, trimestral, semestral, anual ou data programada)' using errcode = '22023';
        end if;
        if p.tipo in ('IPVA', 'LICENCIAMENTO') and p.frequencia <> 'ANUAL' then
            raise exception 'IPVA e licenciamento são anuais: informe o mês de cobrança' using errcode = '22023';
        end if;
    end if;
    if v_novo or p_dados ? 'data_inicio' then
        v_txt := btrim(coalesce(p_dados ->> 'data_inicio', ''));
        p.data_inicio := financeiro.mob_data(case when v_txt ~ '^[0-9]{4}-[0-9]{2}$' then v_txt || '-01' else v_txt end);
        if p.data_inicio is null then
            raise exception 'Informe o início (mês ou data)' using errcode = '22023';
        end if;
    end if;
    if v_novo or p_dados ? 'data_fim' then
        v_txt := btrim(coalesce(p_dados ->> 'data_fim', ''));
        p.data_fim := financeiro.mob_data(case when v_txt ~ '^[0-9]{4}-[0-9]{2}$' then v_txt || '-01' else v_txt end);
        if v_txt <> '' and p.data_fim is null then
            raise exception 'Término inválido' using errcode = '22023';
        end if;
    end if;
    if p.frequencia in ('MENSAL', 'TRIMESTRAL', 'SEMESTRAL', 'ANUAL') then
        p.data_inicio := date_trunc('month', p.data_inicio::timestamp)::date;
        p.data_fim := date_trunc('month', p.data_fim::timestamp)::date;
    elsif p.frequencia = 'DATA' then
        p.data_fim := null;
    end if;
    if p.data_inicio < date '2000-01-01' or p.data_inicio > date '2100-12-31' or p.data_fim > date '2100-12-31' then
        raise exception 'Data fora do intervalo aceito' using errcode = '22023';
    end if;
    if p.data_fim < p.data_inicio then
        raise exception 'O término deve ser igual ou posterior ao início' using errcode = '22023';
    end if;
    return p;
end
$$;

-- =====================================================================================================================
-- 3. Funcoes substituidas
-- =====================================================================================================================
-- mob_gerar_projecoes: texto de 20261215090000, agora pelos itens do veiculo. Mesma janela, mesma identidade (obrigacao +
-- periodo), mesmos bloqueios do que o usuario ja agiu e a mesma limpeza do que deixou de ser projetado.
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
    v_bloq      text[];
    v_d         record;
    v_p         financeiro.veiculo_projecao;
    v_data      date;
    v_valor     numeric;
    v_mantidas  integer[] := '{}';
begin
    select * into v_v from public.veiculo where id = p_veiculo_id;
    v_inicio := date_trunc('month', greatest(coalesce(v_v.data_inicio, v_hoje), v_hoje))::date;
    v_fim := (v_inicio + make_interval(months => v_meses))::date;
    v_perfil := coalesce(v_v.perfil_financeiro_id, p_perfil_id);
    -- FIN-MVP-MOB-02: veiculo ainda sem itens (gravado antes desta versao ou por outro caminho) e convertido antes de gerar
    perform financeiro.mob_converter_legado(p_perfil_id, v_v.id);

    for v_p in select p.* from financeiro.veiculo_projecao p where p.veiculo_id = v_v.id and p.ativo
                order by case p.tipo when 'COMBUSTIVEL' then 0 when 'IPVA' then 1 when 'SEGURO' then 2 when 'LICENCIAMENTO' then 3 else 4 end, p.id
    loop
        v_valor := financeiro.mob_valor_projecao(v_p, v_v);
        continue when coalesce(v_valor, 0) <= 0;
        -- periodo em que o usuario ja agiu nao volta, em qualquer data: o periodo da data original na frequencia atual, o
        -- periodo gravado e a data atual da ocorrencia
        v_bloq := '{}';
        for v_d in select d.* from public.despesa_prevista d
                    where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
                      and d.origem_id = v_v.id and d.obrigacao = v_p.obrigacao and d.status is not null and d.status <> 'PREVISTA'
        loop
            v_bloq := v_bloq || ('|' || financeiro.mob_periodo_frequencia(v_p.frequencia, coalesce(v_d.data_original_prevista, v_d.data_prevista)))
                             || ('|' || v_d.periodo_referencia) || ('@' || coalesce(v_d.data_atual_prevista, v_d.data_prevista));
        end loop;
        for v_data in select x from financeiro.mob_datas_projecao(v_p, v_inicio, v_fim) x loop
            continue when ('|' || financeiro.mob_periodo_frequencia(v_p.frequencia, v_data)) = any (v_bloq) or ('@' || v_data) = any (v_bloq);
            v_mantidas := v_mantidas || financeiro.mob_planejar_projecao(v_perfil, p_perfil_id, v_p, v_data, v_valor);
        end loop;
    end loop;

    -- O que deixou de ser projetado sai (so PREVISTA, na janela; data programada, em qualquer data futura); o resto fica com o mesmo id.
    delete from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.origem_tipo = 'VEICULO' and d.origem_id = v_v.id and d.status = 'PREVISTA'
       and d.data_prevista >= v_inicio
       and (d.obrigacao in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO')
            or financeiro.mob_tipo_evento(d.metadata) in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO')
            or exists (select 1 from financeiro.veiculo_projecao p where p.veiculo_id = v_v.id and p.obrigacao = d.obrigacao))
       and (d.data_prevista < v_fim
            or exists (select 1 from financeiro.veiculo_projecao p where p.veiculo_id = v_v.id and p.obrigacao = d.obrigacao and p.frequencia = 'DATA'))
       and not (d.id = any (v_mantidas));
    perform financeiro.mob_suprimir_combustivel(p_perfil_id, v_v.id);
    return cardinality(v_mantidas);
end
$$;

-- veiculo_flask: texto de 20261215090000 + os trechos marcados.
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
        -- FIN-MVP-MOB-02: com item fora do formato antigo, os totais e a lista saem dos itens (media mensal informativa)
        || case when financeiro.mob_projecoes_dinamicas((p_v).id) then (
               select jsonb_build_object(
                          'projecoes', coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'tipo', i.tipo, 'nome', i.nome,
                                                                             'frequencia', i.frequencia, 'valor', i.valor,
                                                                             'media_mensal', i.media, 'ativo', i.ativo)
                                                          order by i.ordem, i.id), '[]'::jsonb),
                          'resumo_mensal_estimado', jsonb_build_object(
                              'combustivel_mensal', coalesce(sum(i.media) filter (where i.tipo = 'COMBUSTIVEL'), 0),
                              'seguro_mensal_diluido', coalesce(sum(i.media) filter (where i.tipo = 'SEGURO'), 0),
                              'ipva_mensal_diluido', coalesce(sum(i.media) filter (where i.tipo = 'IPVA'), 0),
                              'licenciamento_mensal_diluido', coalesce(sum(i.media) filter (where i.tipo = 'LICENCIAMENTO'), 0),
                              'manutencao_mensal_media', coalesce(sum(i.media) filter (where i.tipo in ('PNEUS', 'REVISAO', 'MANUTENCAO_PREVENTIVA', 'MANUTENCAO_CORRETIVA')), 0),
                              'assinatura_mensal', 0, 'transporte_app_mensal', 0,
                              'outros_custos_mensais', coalesce(sum(i.media) filter (where i.tipo = 'OUTRO'), 0)),
                          'total_mensal_estimado', coalesce(sum(i.media), 0))
                 from (select p.id, p.tipo, p.nome, p.frequencia, financeiro.mob_valor_projecao(p, p_v) as valor, p.ativo,
                              financeiro.mob_media_mensal_projecao(p, p_v) as media,
                              case p.tipo when 'COMBUSTIVEL' then 0 when 'IPVA' then 1 when 'SEGURO' then 2 when 'LICENCIAMENTO' then 3 else 4 end as ordem
                         from financeiro.veiculo_projecao p where p.veiculo_id = (p_v).id) i)
                else '{}'::jsonb end
      from (select round(coalesce((p_v).combustivel_valor_mensal, 0), 2) comb,
                   round(coalesce((p_v).seguro_valor, 0) / 12, 2) seg,
                   round(coalesce((p_v).ipva_valor, 0) / 12, 2) ipva,
                   round(coalesce((p_v).licenciamento_valor, 0) / 12, 2) lic) c
$$;

-- criar_veiculo: texto de 20261215090000 + os trechos marcados.
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
    -- FIN-MVP-MOB-02: combustivel e os campos anuais enviados viram os itens do veiculo
    perform financeiro.mob_converter_legado(p_perfil_id, v.id);
    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'criar_veiculo',
        jsonb_build_object('veiculo_id', v.id));
end
$$;

-- editar_veiculo: texto de 20261215090000 + os trechos marcados.
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
    -- FIN-MVP-MOB-02: veiculo ainda sem itens e convertido com os valores de antes da edicao
    perform financeiro.mob_converter_legado(p_perfil_id, v.id);
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
    -- FIN-MVP-MOB-02: os campos anuais antigos, quando mudam, gravam nos itens (o mesmo caminho da lista de Projecoes)
    if (v.ipva_mes, v.ipva_valor) is distinct from (v_antes.ipva_mes, v_antes.ipva_valor) then
        perform financeiro.mob_projecao_legada(p_perfil_id, v, 'IPVA', v.ipva_mes, v.ipva_valor);
    end if;
    if (v.seguro_mes, v.seguro_valor) is distinct from (v_antes.seguro_mes, v_antes.seguro_valor) then
        perform financeiro.mob_projecao_legada(p_perfil_id, v, 'SEGURO', v.seguro_mes, v.seguro_valor);
    end if;
    if (v.licenciamento_mes, v.licenciamento_valor) is distinct from (v_antes.licenciamento_mes, v_antes.licenciamento_valor) then
        perform financeiro.mob_projecao_legada(p_perfil_id, v, 'LICENCIAMENTO', v.licenciamento_mes, v.licenciamento_valor);
    end if;
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

-- excluir_veiculo: texto de 20261215090000 + os trechos marcados.
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
    -- FIN-MVP-MOB-02: os itens saem com o veiculo; o historico deles fica
    insert into financeiro.veiculo_projecao_historico (projecao_id, veiculo_id, perfil_financeiro_id, acao, antes, user_id)
    select p.id, p.veiculo_id, p.perfil_financeiro_id, 'EXCLUSAO', to_jsonb(p), (select auth.uid())
      from financeiro.veiculo_projecao p where p.veiculo_id = v.id;
    delete from financeiro.veiculo_projecao p where p.veiculo_id = v.id;
    delete from public.veiculo where id = v.id;
    return jsonb_build_object('veiculo_id', v.id, 'excluido', true);
end
$$;

-- mob_rotulo_prevista: texto de 20261127090000 + o trecho marcado.
create or replace function financeiro.mob_rotulo_prevista(p_d public.despesa_prevista)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select coalesce(
        -- FIN-MVP-MOB-02: item novo da lista de Projecoes: o nome dado pelo usuario
        case when jsonb_typeof(financeiro.json_seguro(p_d.metadata)) = 'object'
             then nullif(btrim(financeiro.json_seguro(p_d.metadata) ->> 'nome'), '') end,
        case upper(coalesce(financeiro.mob_tipo_evento(p_d.metadata), p_d.origem_tipo, ''))
        when 'COMBUSTIVEL' then 'Combustível' when 'IPVA' then 'IPVA' when 'SEGURO' then 'Seguro'
        when 'LICENCIAMENTO' then 'Licenciamento' when 'PARCELA_FINANCIAMENTO' then 'Parcela de financiamento'
        when 'IOF_FINANCIAMENTO' then 'IOF de financiamento' when 'TRANSPORTE_APP' then 'Transporte por app'
        when 'TROCA_OLEO' then 'Troca de óleo' when 'TROCA_PNEUS' then 'Troca de pneus' when 'REVISAO_GERAL' then 'Revisão geral'
        when 'ALINHAMENTO_BALANCEAMENTO' then 'Alinhamento / Balanceamento' end,
        nullif(coalesce(financeiro.mob_tipo_evento(p_d.metadata), p_d.origem_tipo, ''), ''), 'Despesa prevista')
$$;

-- mob_ajustar_ciclo: texto de 20261127090000 + o trecho marcado.
create or replace function financeiro.mob_ajustar_ciclo(p_perfil_id integer, p_d public.despesa_prevista)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_tipo   text := financeiro.mob_tipo_evento(p_d.metadata);
    v_r      public.veiculo_regra_manutencao_km;
    v_v      public.veiculo;
    v_ciclo  public.veiculo_ciclo_manutencao;
    v_md     jsonb := financeiro.json_seguro(p_d.metadata);
    v_ordem  integer;
    v_media  numeric;
    v_meses  integer;
    v_prox   date;
    v_id     integer;
begin
    if p_d.origem_tipo <> 'VEICULO' or v_tipo is null or v_tipo in ('IPVA', 'SEGURO', 'LICENCIAMENTO', 'COMBUSTIVEL') then
        return jsonb_build_object('ciclo_id', null, 'criada', null);
    end if;
    -- FIN-MVP-MOB-02: ocorrencia de um item da lista de Projecoes segue a periodicidade dele, nunca o ciclo por km (sem duas
    -- obrigacoes para o mesmo servico)
    if p_d.obrigacao is not null then
        return jsonb_build_object('ciclo_id', null, 'criada', null);
    end if;
    select * into v_r from public.veiculo_regra_manutencao_km r
     where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id) and r.veiculo_id = p_d.origem_id
       and r.tipo_evento = v_tipo and r.ativo order by r.id limit 1;
    if not found then
        return jsonb_build_object('ciclo_id', null, 'criada', null);
    end if;
    v_v := financeiro.veiculo_do_perfil(p_perfil_id, p_d.origem_id);
    if v_v.id is null then
        return jsonb_build_object('ciclo_id', null, 'criada', null);
    end if;
    select * into v_ciclo from public.veiculo_ciclo_manutencao c
     where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and c.veiculo_id = v_v.id and c.tipo_evento = v_tipo
     order by c.id limit 1;
    if not found then
        insert into public.veiculo_ciclo_manutencao (perfil_financeiro_id, veiculo_id, tipo_evento, regra_id, intervalo_km, criado_em)
        values (coalesce(v_r.perfil_financeiro_id, p_perfil_id), v_v.id, v_tipo, v_r.id, v_r.intervalo_km, financeiro.mob_agora())
        returning * into v_ciclo;
    end if;
    if jsonb_typeof(v_md) <> 'object' then
        v_md := '{}'::jsonb;
    end if;
    if coalesce((v_md ->> 'ciclo_id'), '') in ('', '0') then
        v_md := v_md || jsonb_build_object('ciclo_id', v_ciclo.id);
    end if;
    if coalesce((v_md ->> 'ordem_no_ciclo'), '') in ('', '0') then
        select coalesce(max(financeiro.mob_inteiro(financeiro.json_seguro(d.metadata) -> 'ordem_no_ciclo')), 0) into v_ordem
          from public.despesa_prevista d
         where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
           and d.status in ('PREVISTA', 'ADIADA', 'CONFIRMADA', 'IGNORADA')
           and financeiro.mob_inteiro(financeiro.json_seguro(d.metadata) -> 'ciclo_id') = v_ciclo.id;
        v_md := v_md || jsonb_build_object('ordem_no_ciclo', case when v_ordem > 0 then v_ordem + 1 else 1 end);
    end if;
    update public.despesa_prevista set metadata = v_md::text where id = p_d.id;

    v_media := (financeiro.uso_do_veiculo(v_v, 3) ->> 'media_movel_km_mes')::numeric;
    if coalesce(v_media, 0) <= 0 or coalesce(v_r.intervalo_km, 0) = 0 then
        return jsonb_build_object('ciclo_id', v_ciclo.id, 'criada', null);
    end if;
    v_meses := ceil(v_r.intervalo_km / v_media)::integer;
    v_prox := date_trunc('month', coalesce(p_d.data_atual_prevista, p_d.data_prevista) + make_interval(months => v_meses))::date;
    if exists (select 1 from public.despesa_prevista d
                where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
                  and d.origem_id = v_v.id and d.status in ('PREVISTA', 'ADIADA', 'CONFIRMADA') and d.data_prevista >= v_prox
                  and d.id <> p_d.id and financeiro.mob_tipo_evento(d.metadata) = v_tipo) then
        return jsonb_build_object('ciclo_id', v_ciclo.id, 'criada', null);
    end if;
    v_id := financeiro.mob_inserir_prevista(coalesce(v_v.perfil_financeiro_id, p_perfil_id), 'VEICULO', v_v.id,
        financeiro.mob_categoria_evento(v_tipo), v_prox, v_r.custo_estimado,
        jsonb_build_object('tipo_evento', v_tipo, 'ciclo_id', v_ciclo.id,
                           'ordem_no_ciclo', (v_md ->> 'ordem_no_ciclo')::integer + 1, 'intervalo_km', v_r.intervalo_km));
    return jsonb_build_object('ciclo_id', v_ciclo.id, 'criada', v_id);
end
$$;

-- =====================================================================================================================
-- 4. Tela e escrita (authenticated). Escritor unico primeiro; o veiculo e travado antes do item, sempre nessa ordem.
-- =====================================================================================================================
-- Lista de Projecoes do veiculo: os itens, as regras de manutencao por km (so leitura, com o proprio cadastro) e os totais.
-- Veiculo ainda sem itens mostra os campos antigos como itens provisorios (sem acoes): a primeira gravacao os converte.
create function financeiro.projecoes_veiculo_tela(p_perfil_id integer, p_veiculo_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v       public.veiculo;
    v_mes   date := date_trunc('month', financeiro.hoje_brasilia())::date;
    v_itens jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v := financeiro.veiculo_do_perfil(p_perfil_id, p_veiculo_id);
    if v.id is null then
        raise exception 'Veículo não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    if exists (select 1 from financeiro.veiculo_projecao p where p.veiculo_id = v.id) then
        select jsonb_agg(financeiro.mob_projecao_tela(p, v)
                         order by case p.tipo when 'COMBUSTIVEL' then 0 when 'IPVA' then 1 when 'SEGURO' then 2 when 'LICENCIAMENTO' then 3 else 4 end, p.id)
          into v_itens from financeiro.veiculo_projecao p where p.veiculo_id = v.id;
    else
        select coalesce(jsonb_agg(jsonb_build_object('id', null, 'provisorio', true, 'tipo', e.tipo, 'nome', financeiro.mob_rotulo_tipo_projecao(e.tipo),
                                                     'valor', e.valor, 'frequencia', e.freq, 'ativo', true, 'pode_excluir', false,
                                                     'valor_segue_veiculo', e.tipo = 'COMBUSTIVEL',
                                                     'media_mensal', case when e.freq = 'ANUAL' then round(e.valor / 12, 2) else round(e.valor, 2) end)
                                  order by e.ordem), '[]'::jsonb)
          into v_itens
          from (values ('COMBUSTIVEL', nullif(v.combustivel_valor_mensal, 0), 'MENSAL', 0, 1),
                       ('IPVA', v.ipva_valor, 'ANUAL', 1, v.ipva_mes), ('SEGURO', v.seguro_valor, 'ANUAL', 2, v.seguro_mes),
                       ('LICENCIAMENTO', v.licenciamento_valor, 'ANUAL', 3, v.licenciamento_mes)) e(tipo, valor, freq, ordem, mes)
         where e.tipo = 'COMBUSTIVEL' or (coalesce(e.mes, 0) between 1 and 12 and coalesce(e.valor, 0) > 0);
    end if;
    return jsonb_build_object(
        'veiculo_id', v.id, 'status', v.status, 'situacao_uso', financeiro.mob_situacao_uso(v),
        'custo_combustivel_modo', v.custo_combustivel_modo,
        'combustivel_coberto', (financeiro.mob_item_combustivel(p_perfil_id, v.id)).id is not null,
        'itens', coalesce(v_itens, '[]'::jsonb),
        'regras_km', coalesce((select jsonb_agg(jsonb_build_object(
                                   'id', r.id, 'tipo_evento', r.tipo_evento, 'intervalo_km', r.intervalo_km,
                                   'meses_intervalo', r.meses_intervalo, 'custo_estimado', r.custo_estimado, 'ativo', coalesce(r.ativo, false),
                                   'proxima_ocorrencia', (select min(coalesce(d.data_atual_prevista, d.data_prevista)) from public.despesa_prevista d
                                                           where d.origem_tipo = 'VEICULO' and d.origem_id = v.id and d.obrigacao is null
                                                             and d.status in ('PREVISTA', 'ADIADA')
                                                             and financeiro.mob_tipo_evento(d.metadata) = r.tipo_evento))
                                   order by r.id)
                                 from public.veiculo_regra_manutencao_km r
                                where r.veiculo_id = v.id and financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)), '[]'::jsonb),
        -- media mensal informativa e as ocorrencias dos proximos 12 meses (o anual entra integral no mes de cobranca)
        'totais', jsonb_build_object(
            'media_mensal', coalesce((select sum((i ->> 'media_mensal')::numeric) from jsonb_array_elements(coalesce(v_itens, '[]'::jsonb)) i
                                       where coalesce((i ->> 'ativo')::boolean, false)), 0),
            'proximos_12_meses', coalesce((select sum(d.valor_previsto) from public.despesa_prevista d
                                            where d.origem_tipo = 'VEICULO' and d.origem_id = v.id and d.obrigacao is not null
                                              and d.status not in ('IGNORADA', 'CANCELADA')
                                              and coalesce(d.data_atual_prevista, d.data_prevista) >= v_mes
                                              and coalesce(d.data_atual_prevista, d.data_prevista) < (v_mes + interval '12 months')::date), 0)));
end
$$;

-- Criar (sem id, com chave de repeticao) ou editar (com id) um item. Combustivel: so o valor, pelo cadastro do veiculo (custo
-- manual, recorrencia e ocorrencias futuras elegiveis); no custo calculado, o valor vem da quilometragem.
create function financeiro.salvar_projecao_veiculo(p_perfil_id integer, p_veiculo_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v       public.veiculo;
    v_dados jsonb := coalesce(p_dados, '{}'::jsonb);
    v_id    integer := financeiro.mob_inteiro(coalesce(p_dados, '{}'::jsonb) -> 'id');
    v_rep   jsonb;
    v_antes financeiro.veiculo_projecao;
    v_p     financeiro.veiculo_projecao;
    v_n     integer;
    v_res   jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if v_id is null then
        v_rep := financeiro.repeticao_mobilidade(p_chave, p_perfil_id, 'salvar_projecao_veiculo');
        if v_rep is not null then
            return v_rep;
        end if;
    end if;
    v := financeiro.mob_veiculo(p_perfil_id, p_veiculo_id);
    perform financeiro.mob_converter_legado(p_perfil_id, v.id);
    if v_id is null then
        v_p := financeiro.mob_dados_projecao(null::financeiro.veiculo_projecao, v, v_dados);
        if v_p.tipo = 'COMBUSTIVEL' then
            raise exception 'O combustível já é uma projeção do veículo: edite o item existente. Nada foi gravado.'
                using errcode = '22023', hint = 'PROJECAO_REPETIDA';
        end if;
        if exists (select 1 from financeiro.veiculo_projecao p where p.veiculo_id = v.id and p.obrigacao = v_p.tipo) then
            raise exception 'Este veículo já tem % na lista de Projeções: edite ou reative o item existente. Nada foi gravado.',
                financeiro.mob_rotulo_tipo_projecao(v_p.tipo) using errcode = '22023', hint = 'PROJECAO_REPETIDA';
        end if;
        -- regra de manutencao por km do mesmo servico (mesma categoria ou mesmo tipo): duas obrigacoes so com confirmacao
        if not financeiro.mob_bool(v_dados -> 'confirmar_km', false)
           and exists (select 1 from public.veiculo_regra_manutencao_km r
                        where r.veiculo_id = v.id and coalesce(r.ativo, false)
                          and (upper(r.tipo_evento) = v_p.tipo
                               or coalesce(r.categoria_id, financeiro.mob_categoria_evento(r.tipo_evento)) = v_p.categoria_id)) then
            raise exception 'Já existe regra de manutenção por quilometragem para este serviço. Confirme para manter as duas previsões. Nada foi gravado.'
                using errcode = '22023', hint = 'PROJECAO_KM_EXISTENTE';
        end if;
        v_p := financeiro.mob_inserir_projecao(v_p);
        perform financeiro.mob_historico_projecao('CRIACAO', null, v_p);
    else
        select * into v_antes from financeiro.veiculo_projecao p where p.id = v_id;
        if v_antes.id is null or v_antes.veiculo_id <> v.id then
            raise exception 'Projeção não encontrada' using errcode = '22023', hint = 'NAO_ENCONTRADA';
        end if;
        v_antes := financeiro.mob_projecao(p_perfil_id, v_id);
        if v_antes.tipo = 'COMBUSTIVEL' then
            if v_dados ? 'valor' and financeiro.numero_seguro(v_dados -> 'valor') is distinct from v.combustivel_valor_mensal then
                if v.custo_combustivel_modo = 'CALCULADO' then
                    raise exception 'O custo do combustível é calculado pela quilometragem: altere a quilometragem, a autonomia ou o preço no cadastro do veículo. Nada foi gravado.'
                        using errcode = '22023', hint = 'CUSTO_CALCULADO';
                end if;
                if coalesce(financeiro.numero_seguro(v_dados -> 'valor'), 0) <= 0 then
                    raise exception 'Informe o valor estimado (maior que zero)' using errcode = '22023';
                end if;
                perform financeiro.editar_veiculo(p_perfil_id, v.id, jsonb_build_object('combustivel_valor_mensal', v_dados -> 'valor'));
                update financeiro.veiculo_projecao p set atualizado_em = now() where p.id = v_antes.id returning * into v_p;
                insert into financeiro.veiculo_projecao_historico (projecao_id, veiculo_id, perfil_financeiro_id, acao, antes, depois, user_id)
                values (v_antes.id, v.id, v_antes.perfil_financeiro_id, 'EDICAO', jsonb_build_object('valor_veiculo', v.combustivel_valor_mensal),
                        jsonb_build_object('valor_veiculo', (select x.combustivel_valor_mensal from public.veiculo x where x.id = v.id)),
                        (select auth.uid()));
                select * into v from public.veiculo x where x.id = v.id;
            end if;
            v_p := v_antes;
        else
            v_p := financeiro.mob_dados_projecao(v_antes, v, v_dados);
            if (v_p.nome, v_p.categoria_id, v_p.valor, v_p.frequencia, v_p.data_inicio, v_p.data_fim)
               is distinct from (v_antes.nome, v_antes.categoria_id, v_antes.valor, v_antes.frequencia, v_antes.data_inicio, v_antes.data_fim) then
                update financeiro.veiculo_projecao p
                   set nome = v_p.nome, categoria_id = v_p.categoria_id, valor = v_p.valor, frequencia = v_p.frequencia,
                       data_inicio = v_p.data_inicio, data_fim = v_p.data_fim, atualizado_em = now()
                 where p.id = v_antes.id
                returning * into v_p;
                perform financeiro.mob_historico_projecao('EDICAO', v_antes, v_p);
            end if;
        end if;
    end if;
    v_n := financeiro.mob_gerar_projecoes(p_perfil_id, v.id, 12);
    perform financeiro.mob_espelhar_legado(v.id);
    select * into v from public.veiculo x where x.id = v.id;
    select * into v_p from financeiro.veiculo_projecao p where p.id = v_p.id;
    v_res := jsonb_build_object('projecao', financeiro.mob_projecao_tela(v_p, v), 'ocorrencias', v_n);
    if v_id is null then
        return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'salvar_projecao_veiculo', v_res);
    end if;
    return v_res;
end
$$;

-- Ativar ou desativar: desativar interrompe a geracao futura (sai so o que ainda e PREVISTA na janela); o historico fica.
create function financeiro.alternar_projecao_veiculo(p_perfil_id integer, p_projecao_id integer, p_ativo boolean)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v       public.veiculo;
    v_antes financeiro.veiculo_projecao;
    v_p     financeiro.veiculo_projecao;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if p_ativo is null then
        raise exception 'Informe se a projeção fica ativa' using errcode = '22023';
    end if;
    select * into v_antes from financeiro.veiculo_projecao p where p.id = p_projecao_id;
    if v_antes.id is null or not financeiro.pertence_ao_perfil(v_antes.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Projeção não encontrada' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    v := financeiro.mob_veiculo(p_perfil_id, v_antes.veiculo_id);
    v_antes := financeiro.mob_projecao(p_perfil_id, p_projecao_id);
    v_p := v_antes;
    if v_antes.ativo is distinct from p_ativo then
        update financeiro.veiculo_projecao p set ativo = p_ativo, atualizado_em = now() where p.id = v_antes.id returning * into v_p;
        perform financeiro.mob_historico_projecao(case when p_ativo then 'ATIVACAO' else 'DESATIVACAO' end, v_antes, v_p);
        perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, 12);
        perform financeiro.mob_espelhar_legado(v.id);
    end if;
    select * into v from public.veiculo x where x.id = v.id;
    return jsonb_build_object('projecao', financeiro.mob_projecao_tela(v_p, v));
end
$$;

-- Exclusao definitiva so sem historico protegido: sai o item e as ocorrencias ainda PREVISTA dele. Com historico, desativar.
create function financeiro.excluir_projecao_veiculo(p_perfil_id integer, p_projecao_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v       public.veiculo;
    v_p     financeiro.veiculo_projecao;
    v_n     integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    select * into v_p from financeiro.veiculo_projecao p where p.id = p_projecao_id;
    if v_p.id is null or not financeiro.pertence_ao_perfil(v_p.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Projeção não encontrada' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    v := financeiro.mob_veiculo(p_perfil_id, v_p.veiculo_id);
    v_p := financeiro.mob_projecao(p_perfil_id, p_projecao_id);
    if v_p.tipo = 'COMBUSTIVEL' then
        raise exception 'O combustível segue o cadastro do veículo: desative a projeção em vez de excluir. Nada foi excluído.'
            using errcode = '22023', hint = 'PROJECAO_PROTEGIDA';
    end if;
    if financeiro.mob_protegidas_projecao(v_p) > 0 then
        raise exception 'A projeção tem ocorrências confirmadas, adiadas, ignoradas ou vinculadas (histórico): desative-a. Nada foi excluído.'
            using errcode = '22023', hint = 'PROJECAO_PROTEGIDA';
    end if;
    delete from public.despesa_prevista d
     where d.origem_tipo = 'VEICULO' and d.origem_id = v.id and d.obrigacao = v_p.obrigacao and d.status = 'PREVISTA'
       and d.conta_id is null and d.lancamento_id is null;
    get diagnostics v_n = row_count;
    delete from financeiro.veiculo_projecao p where p.id = v_p.id;
    perform financeiro.mob_historico_projecao('EXCLUSAO', v_p, null);
    perform financeiro.mob_espelhar_legado(v.id);
    return jsonb_build_object('projecao_id', v_p.id, 'excluida', true, 'ocorrencias_removidas', v_n);
end
$$;

-- =====================================================================================================================
-- 5. Conversao dos cadastros existentes: so os itens (nenhuma ocorrencia, conta, compra ou coluna do veiculo muda)
-- =====================================================================================================================
select financeiro.mob_converter_legado(v.perfil_financeiro_id, v.id)
  from public.veiculo v where v.perfil_financeiro_id is not null order by v.id;

-- =====================================================================================================================
-- Privilegios: internas sem EXECUTE para o navegador; as de tela so para authenticated.
-- =====================================================================================================================
revoke execute on function financeiro.mob_periodo_frequencia(text, date) from public, anon, authenticated;
revoke execute on function financeiro.mob_rotulo_tipo_projecao(text) from public, anon, authenticated;
revoke execute on function financeiro.mob_valor_projecao(financeiro.veiculo_projecao, public.veiculo) from public, anon, authenticated;
revoke execute on function financeiro.mob_media_mensal_projecao(financeiro.veiculo_projecao, public.veiculo) from public, anon, authenticated;
revoke execute on function financeiro.mob_datas_projecao(financeiro.veiculo_projecao, date, date) from public, anon, authenticated;
revoke execute on function financeiro.mob_planejar_projecao(integer, integer, financeiro.veiculo_projecao, date, numeric) from public, anon, authenticated;
revoke execute on function financeiro.mob_historico_projecao(text, financeiro.veiculo_projecao, financeiro.veiculo_projecao) from public, anon, authenticated;
revoke execute on function financeiro.mob_inicio_anual(public.veiculo, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_inserir_projecao(financeiro.veiculo_projecao) from public, anon, authenticated;
revoke execute on function financeiro.mob_converter_legado(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_espelhar_legado(integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_projecao_legada(integer, public.veiculo, text, integer, numeric) from public, anon, authenticated;
revoke execute on function financeiro.mob_projecoes_dinamicas(integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_projecao(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_protegidas_projecao(financeiro.veiculo_projecao) from public, anon, authenticated;
revoke execute on function financeiro.mob_projecao_tela(financeiro.veiculo_projecao, public.veiculo) from public, anon, authenticated;
revoke execute on function financeiro.mob_dados_projecao(financeiro.veiculo_projecao, public.veiculo, jsonb) from public, anon, authenticated;

revoke execute on function financeiro.projecoes_veiculo_tela(integer, integer) from public, anon;
revoke execute on function financeiro.salvar_projecao_veiculo(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.alternar_projecao_veiculo(integer, integer, boolean) from public, anon;
revoke execute on function financeiro.excluir_projecao_veiculo(integer, integer) from public, anon;
grant execute on function financeiro.projecoes_veiculo_tela(integer, integer) to authenticated;
grant execute on function financeiro.salvar_projecao_veiculo(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.alternar_projecao_veiculo(integer, integer, boolean) to authenticated;
grant execute on function financeiro.excluir_projecao_veiculo(integer, integer) to authenticated;
