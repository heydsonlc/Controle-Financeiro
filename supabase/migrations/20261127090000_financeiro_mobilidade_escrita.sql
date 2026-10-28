-- FIN-MOBILIDADE-2 (FIN-BLOCO-A-1, A3) — escrita de Veiculos/Mobilidade no novo aplicativo, com o escritor unico do perfil.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261127090000).
-- Depende de 20261115090000 (leitura de Mobilidade), 20261124090000 (exigir_escrita_novo) e 20261125090000
-- (categorias_sistemicas_mobilidade). Validada em cluster local descartavel (tests/test_supabase_mobilidade_escrita.py,
-- comparada com o Flask). Docs: docs/FIN_MOBILIDADE_2.md. Reversao: supabase/reversao/20261127090000_*.sql.
--
-- Reproduz as rotas de escrita de routes/veiculos.py, routes/mobilidade_app.py e routes/despesas_previstas.py:
-- veiculos (criar, editar, converter, excluir com seguranca), projecoes, regras e manutencao por km, financiamento
-- projetivo do veiculo (D-MOB1 do Flask corrigido), previa e ativacao de modalidade (cenario ativo no banco, por
-- perfil: public.mobilidade_cenario_ativo), assinaturas, caminhos de transporte por app e as acoes sobre despesas
-- previstas (confirmar, adiar com ajuste de ciclo, ignorar).
--
-- Regras mantidas do Flask: projecao nunca vira lancamento por conta propria; so PREVISTA e substituida (CONFIRMADA,
-- ADIADA e IGNORADA bloqueiam a recriacao na mesma competencia); confirmar cria a despesa (Conta) ou o lancamento no
-- cartao so com meio de pagamento; repetir a confirmacao e recusado (a prevista ja nao e PREVISTA).
-- Correcoes (docs/FIN_MOBILIDADE_2.md): categorias sistemicas MOB_* so sao procuradas pelo codigo e NUNCA criadas ou
-- alteradas aqui (o catalogo global e do Flask) — se faltar, a operacao e recusada sem gravar; exclusoes seguras
-- (historico confirmado, modalidade ativa e vinculos recusam em vez do erro 500 do Flask); financiamento do veiculo
-- salva (D-MOB1) e liga as previstas ao financiamento; caminho de app inexistente nao e "editado"; cartao informado tem
-- de ser do perfil. O arquivo global mobilidade_cenario_ativo.json do Flask nao e reproduzido.
-- Uma tabela nova (operacao_mobilidade, vazia, idempotencia dos cadastros). Nenhum dado existente e alterado.

create table financeiro.operacao_mobilidade (
    chave                uuid        primary key,
    user_id              uuid        not null references auth.users (id) on delete cascade,
    perfil_financeiro_id integer     not null,
    operacao             text        not null,
    resultado            jsonb       not null,
    criado_em            timestamptz not null default now()
);
comment on table financeiro.operacao_mobilidade is
    'FIN-MOBILIDADE-2: resultado de cada cadastro de Mobilidade por chave (reenvio nao duplica). So as funcoes gravam.';
alter table financeiro.operacao_mobilidade enable row level security;
alter table financeiro.operacao_mobilidade force row level security;
revoke all on financeiro.operacao_mobilidade from public, anon, authenticated;

-- =====================================================================================================================
-- Apoio (internas)
-- =====================================================================================================================

-- Repeticao por chave: resultado anterior (com repetida=true) ou NULL. Chave de outro usuario/perfil/operacao: erro.
create function financeiro.repeticao_mobilidade(p_chave uuid, p_perfil_id integer, p_operacao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_mobilidade;
begin
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261127));
    select * into v_anterior from financeiro.operacao_mobilidade o where o.chave = p_chave;
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

create function financeiro.registrar_operacao_mobilidade(p_chave uuid, p_perfil_id integer, p_operacao text,
                                                         p_resultado jsonb)
    returns jsonb
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into financeiro.operacao_mobilidade (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, p_operacao, p_resultado)
    returning resultado
$$;

-- Categoria sistemica pelo codigo estavel (obter_categoria_sistemica_id do Flask, sem criar nem alterar o catalogo).
create function financeiro.mob_categoria(p_codigo text)
    returns integer
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_id   integer;
    v_nome text;
begin
    select c.id into v_id from public.categoria c where c.codigo_sistema = p_codigo order by c.id limit 1;
    if v_id is null then
        select s.nome into v_nome from financeiro.categorias_sistemicas_mobilidade() s where s.codigo = p_codigo;
        raise exception 'A categoria sistêmica "%" (%) não existe. Ela é criada pelo sistema atual; nada foi gravado.',
            coalesce(v_nome, p_codigo), p_codigo using errcode = 'P0001', hint = 'CATEGORIA_SISTEMICA_AUSENTE';
    end if;
    return v_id;
end
$$;

-- categoria_sistemica_mobilidade_id_para_tipo_evento do Flask.
create function financeiro.mob_categoria_evento(p_tipo text)
    returns integer
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select financeiro.mob_categoria(case upper(btrim(coalesce(p_tipo, '')))
        when 'COMBUSTIVEL' then 'MOB_COMBUSTIVEL' when 'ABASTECIMENTO' then 'MOB_COMBUSTIVEL'
        when 'SEGURO' then 'MOB_SEGURO_VEICULAR' when 'SEGURO_VEICULAR' then 'MOB_SEGURO_VEICULAR'
        when 'IPVA' then 'MOB_TRIBUTOS_VEICULARES' when 'LICENCIAMENTO' then 'MOB_TRIBUTOS_VEICULARES'
        when 'TRIBUTO' then 'MOB_TRIBUTOS_VEICULARES' when 'TRIBUTOS' then 'MOB_TRIBUTOS_VEICULARES'
        when 'TAXA_OBRIGATORIA' then 'MOB_TRIBUTOS_VEICULARES'
        when 'REVISAO' then 'MOB_REVISAO' when 'REVISAO_GERAL' then 'MOB_REVISAO' when 'REVISAO_PROGRAMADA' then 'MOB_REVISAO'
        when 'TROCA_PNEUS' then 'MOB_PNEUS' when 'PNEUS' then 'MOB_PNEUS' when 'ALINHAMENTO_BALANCEAMENTO' then 'MOB_PNEUS'
        when 'ESTACIONAMENTO' then 'MOB_USO_VEICULO' when 'PEDAGIO' then 'MOB_USO_VEICULO' when 'USO_VEICULO' then 'MOB_USO_VEICULO'
        when 'TRANSPORTE_APP' then 'MOB_APP' when 'APP' then 'MOB_APP' when 'TAXI' then 'MOB_APP' when 'UBER' then 'MOB_APP'
        when 'ASSINATURA' then 'MOB_ASSINATURA' when 'ASSINATURA_VEICULAR' then 'MOB_ASSINATURA'
        when 'LAVAGEM' then 'MOB_LAVAGEM' when 'LAVA_JATO' then 'MOB_LAVAGEM' when 'HIGIENIZACAO' then 'MOB_LAVAGEM'
        else 'MOB_MANUTENCAO' end)
$$;

-- _to_int do Flask sobre um valor do JSON: int(valor); invalido = NULL.
create function financeiro.mob_inteiro(p_valor jsonb)
    returns integer
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_texto text;
begin
    if p_valor is null or jsonb_typeof(p_valor) = 'null' then
        return null;
    elsif jsonb_typeof(p_valor) = 'number' then
        return trunc((p_valor #>> '{}')::numeric)::integer;
    elsif jsonb_typeof(p_valor) = 'boolean' then
        return case when (p_valor #>> '{}')::boolean then 1 else 0 end;
    elsif jsonb_typeof(p_valor) = 'string' then
        v_texto := btrim(p_valor #>> '{}');
        return case when v_texto ~ '^[+-]?[0-9]{1,9}$' then v_texto::integer end;
    end if;
    return null;
end
$$;

-- int(data.get(campo) or padrao) do Flask (texto invalido: erro, como o 500 do Flask).
create function financeiro.mob_meses(p_valor jsonb, p_padrao integer)
    returns integer
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v integer;
begin
    if p_valor is null or jsonb_typeof(p_valor) = 'null' or p_valor in ('""'::jsonb, '0'::jsonb, 'false'::jsonb) then
        return p_padrao;
    end if;
    v := financeiro.mob_inteiro(p_valor);
    if v is null then
        raise exception 'Valor inválido: %', p_valor #>> '{}' using errcode = '22023';
    end if;
    return coalesce(nullif(v, 0), p_padrao);
end
$$;

-- datetime.fromisoformat(str(valor)).date() do Flask; invalido = NULL.
create function financeiro.mob_data(p_valor text)
    returns date
    language plpgsql
    immutable
    set search_path = ''
as $$
begin
    if p_valor is null or btrim(p_valor) !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}([T ].*)?$' then
        return null;
    end if;
    return left(btrim(p_valor), 10)::date;
exception when others then
    return null;
end
$$;

-- bool(valor) do Python sobre um valor do JSON (ausente = padrao).
create function financeiro.mob_bool(p_valor jsonb, p_padrao boolean)
    returns boolean
    language sql
    immutable
    set search_path = ''
as $$
    select case
        when p_valor is null then p_padrao
        when jsonb_typeof(p_valor) = 'null' then false
        when jsonb_typeof(p_valor) = 'boolean' then (p_valor #>> '{}')::boolean
        when jsonb_typeof(p_valor) = 'number' then (p_valor #>> '{}')::numeric <> 0
        when jsonb_typeof(p_valor) = 'string' then (p_valor #>> '{}') <> ''
        when jsonb_typeof(p_valor) = 'array' then jsonb_array_length(p_valor) > 0
        else p_valor <> '{}'::jsonb end
$$;

create function financeiro.mob_agora()
    returns timestamp
    language sql
    stable
    set search_path = ''
as $$
    select (now() at time zone 'utc')::timestamp
$$;

-- Veiculo do perfil, travado (404 do Flask).
create function financeiro.mob_veiculo(p_perfil_id integer, p_veiculo_id integer)
    returns public.veiculo
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_v public.veiculo;
begin
    select * into v_v from public.veiculo v where v.id = p_veiculo_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_v.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Veículo não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    return v_v;
end
$$;

-- aplicar_defaults_categorias_veiculo: as 4 categorias do veiculo sao as sistemicas (por codigo).
create function financeiro.mob_aplicar_categorias(p_veiculo_id integer)
    returns void
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    update public.veiculo
       set categoria_combustivel_id = financeiro.mob_categoria('MOB_COMBUSTIVEL'),
           ipva_categoria_id = financeiro.mob_categoria('MOB_TRIBUTOS_VEICULARES'),
           seguro_categoria_id = financeiro.mob_categoria('MOB_SEGURO_VEICULAR'),
           licenciamento_categoria_id = financeiro.mob_categoria('MOB_TRIBUTOS_VEICULARES')
     where id = p_veiculo_id
$$;

create function financeiro.mob_tipo_evento(p_metadata text)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select case when jsonb_typeof(financeiro.json_seguro(p_metadata)) = 'object'
                then financeiro.json_seguro(p_metadata) ->> 'tipo_evento' end
$$;

create function financeiro.mob_inserir_prevista(p_perfil_id integer, p_origem_tipo text, p_origem_id integer,
                                                 p_categoria_id integer, p_data date, p_valor numeric, p_metadata jsonb)
    returns integer
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista,
                                         data_original_prevista, data_atual_prevista, valor_previsto, status, metadata,
                                         criado_em, atualizado_em)
    values (p_perfil_id, p_origem_tipo, p_origem_id, p_categoria_id, p_data, p_data, p_data, p_valor, 'PREVISTA',
            p_metadata::text, financeiro.mob_agora(), financeiro.mob_agora())
    returning id
$$;

-- gerar_projecoes_mvp do Flask: substitui so as PREVISTA dos eventos do MVP na janela; competencias em que o usuario
-- ja agiu (CONFIRMADA/ADIADA/IGNORADA, pela data original ou atual) nao sao recriadas. Devolve quantas criou.
create function financeiro.mob_gerar_projecoes(p_perfil_id integer, p_veiculo_id integer, p_meses integer)
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
    v_criadas   integer := 0;
    v_evento    record;
    v_ano       integer;
begin
    select * into v_v from public.veiculo where id = p_veiculo_id;
    v_inicio := date_trunc('month', greatest(coalesce(v_v.data_inicio, v_hoje), v_hoje))::date;
    v_fim := (v_inicio + make_interval(months => v_meses))::date;
    v_perfil := coalesce(v_v.perfil_financeiro_id, p_perfil_id);

    for v_d in select d.*, financeiro.mob_tipo_evento(d.metadata) tipo from public.despesa_prevista d
                where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                  and d.origem_tipo = 'VEICULO' and d.origem_id = v_v.id
                  and d.data_prevista >= v_inicio and d.data_prevista < v_fim
    loop
        continue when v_d.tipo is null or v_d.tipo not in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO');
        if v_d.status is not null and v_d.status <> 'PREVISTA' then
            if coalesce(v_d.data_original_prevista, v_d.data_prevista) >= v_inicio
               and coalesce(v_d.data_original_prevista, v_d.data_prevista) < v_fim then
                v_bloq := v_bloq || (v_d.tipo || '|' || coalesce(v_d.data_original_prevista, v_d.data_prevista));
            end if;
            if coalesce(v_d.data_atual_prevista, v_d.data_prevista) >= v_inicio
               and coalesce(v_d.data_atual_prevista, v_d.data_prevista) < v_fim then
                v_bloq := v_bloq || (v_d.tipo || '|' || coalesce(v_d.data_atual_prevista, v_d.data_prevista));
            end if;
        end if;
    end loop;
    delete from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.origem_tipo = 'VEICULO' and d.origem_id = v_v.id and d.status = 'PREVISTA'
       and d.data_prevista >= v_inicio and d.data_prevista < v_fim
       and financeiro.mob_tipo_evento(d.metadata) in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO');

    if coalesce(v_v.combustivel_valor_mensal, 0) > 0 then
        v_ref := v_inicio;
        while v_ref < v_fim loop
            if not (('COMBUSTIVEL|' || v_ref) = any (v_bloq)) then
                perform financeiro.mob_inserir_prevista(v_perfil, 'VEICULO', v_v.id, financeiro.mob_categoria_evento('COMBUSTIVEL'),
                    v_ref, v_v.combustivel_valor_mensal,
                    jsonb_build_object('tipo_evento', 'COMBUSTIVEL', 'ciclo_id', null, 'ordem_no_ciclo', null));
                v_criadas := v_criadas + 1;
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
            continue when v_ref < v_inicio or v_ref >= v_fim or ((v_evento.tipo || '|' || v_ref) = any (v_bloq));
            perform financeiro.mob_inserir_prevista(v_perfil, 'VEICULO', v_v.id, financeiro.mob_categoria_evento(v_evento.tipo),
                v_ref, v_evento.valor, jsonb_build_object('tipo_evento', v_evento.tipo, 'ciclo_id', null, 'ordem_no_ciclo', null));
            v_criadas := v_criadas + 1;
        end loop;
    end loop;
    return v_criadas;
end
$$;

-- Dados do veiculo (criar/editar), com as validacoes e mensagens do Flask. p_atual NULL = cadastro.
create function financeiro.mob_dados_veiculo(p_atual public.veiculo, p_dados jsonb)
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
    return v;
end
$$;

-- =====================================================================================================================
-- Veiculos (POST/PUT/DELETE /api/veiculos, /converter, /projecoes/gerar)
-- =====================================================================================================================

create function financeiro.criar_veiculo(p_perfil_id integer, p_dados jsonb, p_chave uuid)
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
                                licenciamento_valor, preco_medio_combustivel, km_estimado_acumulado, criado_em, atualizado_em)
    values (p_perfil_id, v.nome, v.tipo, v.combustivel, v.autonomia_km_l, v.status, v.data_inicio,
            v.combustivel_valor_mensal, v.ipva_mes, v.ipva_valor, v.seguro_mes, v.seguro_valor, v.licenciamento_mes,
            v.licenciamento_valor, v.preco_medio_combustivel, 0, financeiro.mob_agora(), financeiro.mob_agora())
    returning id into v.id;
    perform financeiro.mob_aplicar_categorias(v.id);
    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'criar_veiculo',
        jsonb_build_object('veiculo_id', v.id));
end
$$;

create function financeiro.editar_veiculo(p_perfil_id integer, p_veiculo_id integer, p_dados jsonb)
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
    v := financeiro.mob_dados_veiculo(financeiro.mob_veiculo(p_perfil_id, p_veiculo_id), coalesce(p_dados, '{}'::jsonb));
    update public.veiculo
       set nome = v.nome, tipo = v.tipo, combustivel = v.combustivel, autonomia_km_l = v.autonomia_km_l,
           status = v.status, data_inicio = v.data_inicio, combustivel_valor_mensal = v.combustivel_valor_mensal,
           ipva_mes = v.ipva_mes, ipva_valor = v.ipva_valor, seguro_mes = v.seguro_mes, seguro_valor = v.seguro_valor,
           licenciamento_mes = v.licenciamento_mes, licenciamento_valor = v.licenciamento_valor,
           preco_medio_combustivel = v.preco_medio_combustivel, atualizado_em = financeiro.mob_agora()
     where id = v.id;
    perform financeiro.mob_aplicar_categorias(v.id);
    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    return jsonb_build_object('veiculo_id', v.id);
end
$$;

-- POST /converter: so SIMULADO vira ATIVO; sem historico retroativo (limpar_projecoes_anteriores).
create function financeiro.converter_veiculo(p_perfil_id integer, p_veiculo_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v      public.veiculo;
    v_data date;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v := financeiro.mob_veiculo(p_perfil_id, p_veiculo_id);
    if v.status <> 'SIMULADO' then
        raise exception 'Apenas veículos SIMULADO podem ser convertidos' using errcode = '22023';
    end if;
    v_data := coalesce(financeiro.mob_data(p_dados ->> 'data_inicio'), financeiro.hoje_brasilia());
    update public.veiculo set status = 'ATIVO', data_inicio = v_data, atualizado_em = financeiro.mob_agora() where id = v.id;
    perform financeiro.mob_aplicar_categorias(v.id);
    delete from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.origem_tipo = 'VEICULO' and d.origem_id = v.id and d.status = 'PREVISTA'
       and d.data_prevista < date_trunc('month', v_data)::date
       and financeiro.mob_tipo_evento(d.metadata) in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO');
    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    return jsonb_build_object('veiculo_id', v.id);
end
$$;

create function financeiro.gerar_projecoes_veiculo(p_perfil_id integer, p_veiculo_id integer, p_dados jsonb)
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
    perform financeiro.mob_aplicar_categorias(v.id);
    return jsonb_build_object('criadas',
        financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12)));
end
$$;

-- DELETE /api/veiculos/<id>. Correcao: recusa (sem gravar) quando ha historico ou vinculos — o Flask apagava as
-- previstas ja confirmadas, e com financiamento, regras, ciclos ou acoes registradas respondia 500.
create function financeiro.excluir_veiculo(p_perfil_id integer, p_veiculo_id integer)
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

-- =====================================================================================================================
-- Regras e manutencao por km (POST/DELETE /regras-km, POST /manutencoes-km/gerar)
-- =====================================================================================================================

-- Correcao: o veiculo tem de ser do perfil (o Flask so conferia a chave estrangeira).
create function financeiro.criar_regra_km_veiculo(p_perfil_id integer, p_veiculo_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep    jsonb;
    v        public.veiculo;
    v_tipo   text := upper(btrim(coalesce(p_dados ->> 'tipo_evento', '')));
    v_km     integer := financeiro.mob_inteiro(p_dados -> 'intervalo_km');
    v_meses  integer := financeiro.mob_inteiro(p_dados -> 'meses_intervalo');
    v_custo  numeric := financeiro.numero_seguro(p_dados -> 'custo_estimado');
    v_cat    integer;
    v_r      public.veiculo_regra_manutencao_km;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_rep := financeiro.repeticao_mobilidade(p_chave, p_perfil_id, 'criar_regra_km');
    if v_rep is not null then
        return v_rep;
    end if;
    v := financeiro.mob_veiculo(p_perfil_id, p_veiculo_id);
    v_cat := financeiro.mob_categoria_evento(v_tipo);
    if v_tipo = '' then raise exception 'tipo_evento é obrigatório' using errcode = '22023'; end if;
    if coalesce(v_km, 0) <= 0 then raise exception 'intervalo_km deve ser > 0' using errcode = '22023'; end if;
    if v_meses is not null and v_meses <= 0 then
        raise exception 'meses_intervalo deve ser > 0 (quando informado)' using errcode = '22023';
    end if;
    if v_custo is null or v_custo <= 0 then raise exception 'custo_estimado deve ser > 0' using errcode = '22023'; end if;
    insert into public.veiculo_regra_manutencao_km (perfil_financeiro_id, veiculo_id, tipo_evento, intervalo_km,
                                                    meses_intervalo, custo_estimado, categoria_id, ativo, criado_em, atualizado_em)
    values (p_perfil_id, v.id, v_tipo, v_km, v_meses, v_custo, v_cat, financeiro.mob_bool(p_dados -> 'ativo', true),
            financeiro.mob_agora(), financeiro.mob_agora())
    returning * into v_r;
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'criar_regra_km',
        jsonb_build_object('regra_id', v_r.id, 'data', financeiro.regra_km_flask(v_r)));
end
$$;

-- Correcao: regra usada por ciclo de manutencao nao e removida (o Flask respondia 500).
create function financeiro.excluir_regra_km_veiculo(p_perfil_id integer, p_veiculo_id integer, p_regra_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_r public.veiculo_regra_manutencao_km;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    select * into v_r from public.veiculo_regra_manutencao_km r
     where r.id = p_regra_id and r.veiculo_id = p_veiculo_id and financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
       for update;
    if not found then
        raise exception 'Regra não encontrada' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    if exists (select 1 from public.veiculo_ciclo_manutencao c where c.regra_id = v_r.id) then
        raise exception 'A regra já tem ciclo de manutenção registrado (histórico). Nada foi removido.'
            using errcode = '22023', hint = 'COM_HISTORICO';
    end if;
    delete from public.veiculo_regra_manutencao_km where id = v_r.id;
    return jsonb_build_object('regra_id', v_r.id, 'removida', true);
end
$$;

-- gerar_despesa_prevista_por_regra: UMA prevista por regra; nada se ja houver PREVISTA/ADIADA/CONFIRMADA do tipo ou
-- sem uso estimado (historico > projetado).
create function financeiro.gerar_manutencao_km_veiculo(p_perfil_id integer, p_veiculo_id integer, p_dados jsonb)
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
    v_km_mes := (financeiro.uso_do_veiculo(v, financeiro.mob_meses(p_dados -> 'janela_meses', 3)) ->> 'media_movel_km_mes')::numeric;
    if coalesce(v_km_mes, 0) <= 0 then
        v_km_mes := case when coalesce(v.combustivel_valor_mensal, 0) > 0 and coalesce(v.preco_medio_combustivel, 0) > 0
                               and coalesce(v.autonomia_km_l, 0) > 0
                         then v.combustivel_valor_mensal / v.preco_medio_combustivel * v.autonomia_km_l else 0 end;
    end if;
    if v_km_mes <= 0 then
        return jsonb_build_object('gerada', false);
    end if;
    v_atual := coalesce(v.km_estimado_acumulado, 0);
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

-- =====================================================================================================================
-- Financiamento projetivo do veiculo (POST/DELETE /financiamento): so despesas previstas, nunca lancamentos.
-- D-MOB1 corrigido (o Flask sempre falhava ao salvar). As previstas levam o id do financiamento.
-- =====================================================================================================================

create function financeiro.mob_limpar_financiamento(p_perfil_id integer, p_veiculo_id integer)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_n integer;
begin
    delete from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
       and d.origem_id = p_veiculo_id and d.status = 'PREVISTA'
       and financeiro.mob_tipo_evento(d.metadata) in ('PARCELA_FINANCIAMENTO', 'IOF_FINANCIAMENTO');
    get diagnostics v_n = row_count;
    return v_n;
end
$$;

create function financeiro.mob_financiamento_flask(p_f public.veiculo_financiamento)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_f.id, 'perfil_financeiro_id', p_f.perfil_financeiro_id, 'veiculo_id', p_f.veiculo_id,
        'valor_bem', p_f.valor_bem, 'entrada', p_f.entrada, 'valor_financiado', p_f.valor_financiado,
        'numero_parcelas', p_f.numero_parcelas, 'taxa_juros_mensal', p_f.taxa_juros_mensal,
        'indexador_tipo', p_f.indexador_tipo, 'iof_percentual', p_f.iof_percentual, 'iof_valor', p_f.iof_valor,
        'categoria_id', p_f.categoria_id, 'custo_total_financiamento', p_f.custo_total_financiamento,
        'criado_em', financeiro.iso_python(p_f.criado_em), 'atualizado_em', financeiro.iso_python(p_f.atualizado_em))
$$;

create function financeiro.salvar_financiamento_veiculo(p_perfil_id integer, p_veiculo_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v          public.veiculo;
    v_f        public.veiculo_financiamento;
    v_bem      numeric := financeiro.numero_seguro(p_dados -> 'valor_bem');
    v_entrada  numeric := coalesce(financeiro.numero_seguro(p_dados -> 'entrada'), 0);
    v_n        integer := financeiro.mob_inteiro(p_dados -> 'numero_parcelas');
    v_taxa     numeric := financeiro.numero_seguro(p_dados -> 'taxa_juros_mensal');
    v_indexador text := nullif(btrim(coalesce(p_dados ->> 'indexador_tipo', '')), '');
    v_iof_pct  numeric := coalesce(financeiro.numero_seguro(p_dados -> 'iof_percentual'), 0);
    v_cat      integer;
    v_financ   numeric;
    v_iof      numeric;
    v_hoje     date := financeiro.hoje_brasilia();
    v_comp     date;
    v_mes      date;
    v_amort    numeric;
    v_saldo    numeric;
    v_total    numeric := 0;
    v_juros    numeric;
    v_idx      numeric;
    v_corr     numeric;
    v_parcela  numeric;
    v_perfil   integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    select * into v from public.veiculo x where x.id = p_veiculo_id for update;
    if not found or not financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Veículo não encontrado' using errcode = '22023';
    end if;
    v_cat := financeiro.mob_categoria('MOB_USO_VEICULO');
    if v_bem is null or v_bem <= 0 then raise exception 'valor_bem é obrigatório e deve ser > 0' using errcode = '22023'; end if;
    if v_entrada < 0 then raise exception 'entrada deve ser >= 0' using errcode = '22023'; end if;
    if v_n is null or v_n < 24 or v_n > 72 then
        raise exception 'numero_parcelas deve estar entre 24 e 72' using errcode = '22023';
    end if;
    if v_taxa is null or v_taxa < 1.2 or v_taxa > 3.5 then
        raise exception 'taxa_juros_mensal deve estar entre 1.20 e 3.50 (%% a.m.)' using errcode = '22023';
    end if;
    if v_iof_pct < 0 then raise exception 'iof_percentual deve ser >= 0' using errcode = '22023'; end if;
    v_financ := v_bem - v_entrada;
    if v_financ <= 0 then
        raise exception 'valor_financiado deve ser > 0 (valor_bem - entrada)' using errcode = '22023';
    end if;
    v_iof := (v_financ * v_iof_pct) / 100;
    v_perfil := coalesce(v.perfil_financeiro_id, p_perfil_id);

    select * into v_f from public.veiculo_financiamento f
     where f.veiculo_id = v.id and financeiro.pertence_ao_perfil(f.perfil_financeiro_id, p_perfil_id) for update;
    if not found then
        insert into public.veiculo_financiamento (perfil_financeiro_id, veiculo_id, valor_bem, entrada, valor_financiado,
                                                  numero_parcelas, taxa_juros_mensal, indexador_tipo, iof_percentual,
                                                  iof_valor, categoria_id, custo_total_financiamento, criado_em, atualizado_em)
        values (v_perfil, v.id, v_bem, v_entrada, v_financ, v_n, v_taxa, v_indexador, v_iof_pct, v_iof, v_cat, 0,
                financeiro.mob_agora(), financeiro.mob_agora())
        returning * into v_f;
    end if;

    perform financeiro.mob_limpar_financiamento(p_perfil_id, v.id);
    v_comp := date_trunc('month', greatest(coalesce(v.data_inicio, v_hoje), v_hoje))::date;

    if v_iof > 0 and not exists (
        select 1 from public.despesa_prevista d
         where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
           and d.origem_id = v.id and d.data_prevista = v_comp and d.status <> 'PREVISTA'
           and financeiro.mob_tipo_evento(d.metadata) = 'IOF_FINANCIAMENTO') then
        perform financeiro.mob_inserir_prevista(v_perfil, 'VEICULO', v.id, v_cat, v_comp, v_iof,
            jsonb_build_object('tipo_evento', 'IOF_FINANCIAMENTO', 'financiamento_id', v_f.id));
    end if;

    v_amort := v_financ / v_n;
    v_saldo := v_financ;
    for i in 1 .. v_n loop
        v_mes := (v_comp + make_interval(months => i - 1))::date;
        if exists (select 1 from public.despesa_prevista d
                    where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'VEICULO'
                      and d.origem_id = v.id and d.data_prevista = v_mes and d.status <> 'PREVISTA'
                      and financeiro.mob_tipo_evento(d.metadata) = 'PARCELA_FINANCIAMENTO') then
            v_saldo := v_saldo - v_amort;
            continue;
        end if;
        v_juros := v_saldo * (v_taxa / 100);
        v_idx := coalesce((select m.valor from public.indexador_mensal m
                            where v_indexador is not null and m.nome = v_indexador and m.data_referencia = v_mes
                            order by m.id limit 1), 0);
        v_corr := v_saldo * (v_idx / 100);
        v_parcela := v_amort + v_juros + v_corr;
        perform financeiro.mob_inserir_prevista(v_perfil, 'VEICULO', v.id, v_cat, v_mes, v_parcela,
            jsonb_build_object('tipo_evento', 'PARCELA_FINANCIAMENTO', 'financiamento_id', v_f.id, 'numero_parcela', i,
                               'total_parcelas', v_n, 'amortizacao_base', v_amort::float8, 'juros_mes', v_juros::float8,
                               'correcao_mes', v_corr::float8, 'taxa_juros_mensal', v_taxa::float8,
                               'indexador_tipo', v_indexador, 'indexador_mes_percentual', v_idx::float8));
        v_total := v_total + v_parcela;
        v_saldo := v_saldo - v_amort;
    end loop;

    update public.veiculo_financiamento
       set valor_bem = v_bem, entrada = v_entrada, valor_financiado = v_financ, numero_parcelas = v_n,
           taxa_juros_mensal = v_taxa, indexador_tipo = v_indexador, iof_percentual = v_iof_pct, iof_valor = v_iof,
           categoria_id = v_cat, custo_total_financiamento = v_total + v_iof, atualizado_em = financeiro.mob_agora()
     where id = v_f.id
    returning * into v_f;
    return jsonb_build_object('financiamento', financeiro.mob_financiamento_flask(v_f), 'resumo', jsonb_build_object(
        'valor_medio_parcela', (v_total / v_n)::float8, 'custo_total_financiamento', v_f.custo_total_financiamento::float8,
        'iof_valor', v_f.iof_valor::float8, 'iof_percentual', v_f.iof_percentual::float8));
end
$$;

create function financeiro.excluir_financiamento_veiculo(p_perfil_id integer, p_veiculo_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_f public.veiculo_financiamento;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    select * into v_f from public.veiculo_financiamento f
     where f.veiculo_id = p_veiculo_id and financeiro.pertence_ao_perfil(f.perfil_financeiro_id, p_perfil_id) for update;
    if not found then
        return jsonb_build_object('removidos', 0);
    end if;
    perform financeiro.mob_limpar_financiamento(p_perfil_id, p_veiculo_id);
    delete from public.veiculo_financiamento where id = v_f.id;
    return jsonb_build_object('removidos', 1);
end
$$;

-- =====================================================================================================================
-- Modalidade ativa (POST /mobilidade/previsualizar e /mobilidade/ativar) e assinaturas
-- =====================================================================================================================

-- resolver_categoria_cartao_para_mobilidade: {id, aviso} (sem cartao: nada; nunca bloqueia).
create function financeiro.mob_resolver_cc(p_perfil_id integer, p_cartao_id integer, p_categoria_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_id integer;
    v_mapeada boolean;
begin
    if p_cartao_id is null then
        return jsonb_build_object('id', null, 'aviso', null);
    end if;
    begin
        v_id := financeiro.resolver_categoria_cartao(p_perfil_id, p_cartao_id, p_categoria_id);
    exception when others then
        return jsonb_build_object('id', null,
            'aviso', 'Categoria do Cartao nao configurada para esta Categoria de Despesa no cartao escolhido.');
    end;
    if v_id is not null then
        return jsonb_build_object('id', v_id, 'aviso', null);
    end if;
    select exists (select 1 from public.categoria_cartao_despesa m join public.categoria_cartao cc on cc.id = m.categoria_cartao_id
                    where m.categoria_id = p_categoria_id and m.ativo and cc.ativo
                      and financeiro.pertence_ao_perfil(m.perfil_financeiro_id, p_perfil_id)) into v_mapeada;
    return jsonb_build_object('id', null, 'aviso', case when v_mapeada
        then 'Categoria do Cartao resolvida mas nao vinculada ao cartao escolhido.'
        else 'Categoria do Cartao nao configurada para esta Categoria de Despesa no cartao escolhido.' end);
end
$$;

create function financeiro.mob_assinatura_flask(p_a public.mobilidade_assinatura)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object('id', p_a.id, 'perfil_financeiro_id', p_a.perfil_financeiro_id, 'nome', p_a.nome,
        'valor_mensal', p_a.valor_mensal, 'categoria_id', p_a.categoria_id, 'status', p_a.status,
        'created_at', financeiro.iso_python(p_a.created_at), 'updated_at', financeiro.iso_python(p_a.updated_at))
$$;

create function financeiro.mob_cenario_flask(p_c public.mobilidade_cenario_ativo)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_c.id, 'perfil_financeiro_id', p_c.perfil_financeiro_id, 'tipo_modalidade', p_c.tipo_modalidade,
        'origem_id', p_c.origem_id, 'ativo_desde', p_c.ativo_desde, 'meio_pagamento', p_c.meio_pagamento,
        'cartao_id', p_c.cartao_id, 'categoria_id', p_c.categoria_id, 'categoria_cartao_id', p_c.categoria_cartao_id,
        'recorrencia_id', p_c.recorrencia_id, 'status', p_c.status,
        'created_at', financeiro.iso_python(p_c.created_at), 'updated_at', financeiro.iso_python(p_c.updated_at))
$$;

-- Configuracao do caminho de app (parse_config do Flask, com as mesmas validacoes) e o valor mensal calculado.
create function financeiro.mob_config_app(p_dados jsonb)
    returns jsonb
    language plpgsql
    stable
    set search_path = ''
as $$
declare
    v_nome   text := coalesce(nullif(btrim(coalesce(p_dados ->> 'nome', '')), ''), 'Transporte por App');
    v_km     numeric := financeiro.numero_seguro(p_dados -> 'km_mensal_estimado');
    v_preco  numeric := financeiro.numero_seguro(p_dados -> 'preco_medio_por_km');
    v_raw    jsonb := p_dados -> 'perfis';
    v_perfis jsonb := '[]'::jsonb;
    v_p      jsonb;
    v_km_p   numeric;
    v_pr_p   numeric;
    v_soma   numeric := 0;
    v_valor  numeric := 0;
    v_media  numeric := financeiro.numero_seguro(p_dados -> 'km_medio_por_corrida');
begin
    if v_km is null or v_km <= 0 then raise exception 'km_mensal_estimado é obrigatório e deve ser > 0' using errcode = '22023'; end if;
    if v_preco is null or v_preco <= 0 then raise exception 'preco_medio_por_km é obrigatório e deve ser > 0' using errcode = '22023'; end if;
    if jsonb_typeof(v_raw) = 'string' then
        v_raw := financeiro.json_seguro(v_raw #>> '{}');
    end if;
    if jsonb_typeof(v_raw) = 'array' then
        for v_p in select * from jsonb_array_elements(v_raw) loop
            continue when jsonb_typeof(v_p) <> 'object';
            v_km_p := financeiro.numero_seguro(v_p -> 'km_mensal');
            v_pr_p := financeiro.numero_seguro(v_p -> 'preco_medio_por_km');
            continue when v_km_p is null or v_km_p <= 0;
            if v_pr_p is null or v_pr_p <= 0 then
                v_pr_p := v_preco;
            end if;
            v_soma := v_soma + v_km_p;
            v_valor := v_valor + v_km_p * v_pr_p;
            v_perfis := v_perfis || jsonb_build_array(jsonb_build_object(
                'nome', coalesce(nullif(btrim(coalesce(v_p ->> 'nome', '')), ''), 'Perfil'),
                'km_mensal', v_km_p::float8, 'preco_medio_por_km', v_pr_p::float8));
        end loop;
    end if;
    if v_soma > v_km then
        raise exception 'A soma de km_mensal dos perfis deve ser <= km_mensal_estimado' using errcode = '22023';
    end if;
    v_valor := v_valor + greatest(v_km - v_soma, 0) * v_preco;
    return jsonb_build_object(
        'caminho', jsonb_build_object('nome', v_nome, 'km_mensal_estimado', v_km::float8, 'preco_medio_por_km', v_preco::float8,
                                      'perfis', v_perfis, 'corridas_mes', financeiro.mob_inteiro(p_dados -> 'corridas_mes'),
                                      'km_medio_por_corrida', v_media::float8),
        'valor_mensal', v_valor);
end
$$;

-- Origem da modalidade: {nome, valor_mensal} do veiculo, caminho ou assinatura do perfil (ou erro do Flask).
create function financeiro.mob_origem(p_perfil_id integer, p_tipo text, p_origem_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_v  public.veiculo;
    v_a  public.mobilidade_assinatura;
    v_md jsonb;
    v_cfg jsonb;
begin
    if p_tipo = 'VEICULO' then
        if p_origem_id is null then raise exception 'origem_id (veiculo.id) e obrigatorio' using errcode = '22023'; end if;
        v_v := financeiro.veiculo_do_perfil(p_perfil_id, p_origem_id);
        if v_v.id is null then raise exception 'Veiculo nao encontrado' using errcode = '22023'; end if;
        return jsonb_build_object('nome', v_v.nome, 'valor', coalesce(v_v.combustivel_valor_mensal, 0),
                                  'codigo', 'MOB_COMBUSTIVEL', 'contexto', 'combustivel_mensal',
                                  'rotulo', 'Combustivel - ' || v_v.nome, 'status', null);
    elsif p_tipo = 'TRANSPORTE_APP' then
        if p_origem_id is null then raise exception 'origem_id (caminho_id) e obrigatorio' using errcode = '22023'; end if;
        v_md := financeiro.caminho_app_md(p_perfil_id, p_origem_id);
        if v_md is null then raise exception 'Caminho de transporte por app nao encontrado' using errcode = '22023'; end if;
        begin
            v_cfg := financeiro.mob_config_app(case when jsonb_typeof(v_md -> 'caminho') = 'object' then v_md -> 'caminho' else '{}' end);
        exception when others then
            v_cfg := jsonb_build_object('caminho', jsonb_build_object('nome',
                coalesce(v_md -> 'caminho' ->> 'nome', 'Caminho ' || p_origem_id)),
                'valor_mensal', coalesce(financeiro.numero_seguro(v_md -> 'caminho' -> 'valor_mensal'), 0));
        end;
        return jsonb_build_object('nome', v_cfg -> 'caminho' ->> 'nome', 'valor', (v_cfg ->> 'valor_mensal')::numeric,
                                  'codigo', 'MOB_APP', 'contexto', 'transporte_app_mensal',
                                  'rotulo', 'Transporte por app - ' || (v_cfg -> 'caminho' ->> 'nome'), 'status', null);
    elsif p_tipo = 'ASSINATURA' then
        if p_origem_id is null then raise exception 'origem_id (assinatura.id) e obrigatorio' using errcode = '22023'; end if;
        select * into v_a from public.mobilidade_assinatura a
         where a.id = p_origem_id and financeiro.pertence_ao_perfil(a.perfil_financeiro_id, p_perfil_id);
        if not found then raise exception 'MobilidadeAssinatura nao encontrada' using errcode = '22023'; end if;
        return jsonb_build_object('nome', v_a.nome, 'valor', v_a.valor_mensal, 'codigo', 'MOB_ASSINATURA',
                                  'contexto', 'assinatura_mensal', 'rotulo', 'Assinatura - ' || v_a.nome, 'status', v_a.status);
    end if;
    raise exception 'tipo_modalidade invalido: %', p_tipo using errcode = '22023';
end
$$;

-- Cartao informado tem de ser do perfil (correcao: o Flask aceitava qualquer id).
create function financeiro.mob_cartao(p_perfil_id integer, p_cartao_id integer)
    returns integer
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if p_cartao_id is not null and not exists (
        select 1 from public.item_despesa i where i.id = p_cartao_id and i.tipo = 'Agregador'
           and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)) then
        raise exception 'Cartao nao encontrado neste perfil' using errcode = '22023';
    end if;
    return p_cartao_id;
end
$$;

-- previsualizar_ativacao_modalidade: so le (nada e gravado; categorias nunca sao criadas).
create function financeiro.previa_mobilidade(p_perfil_id integer, p_dados jsonb)
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
        'avisos', v_avisos);
end
$$;

-- ativar_modalidade: inativa a anterior e as recorrencias automaticas dela, cria/atualiza a recorrencia mensal (com
-- meio de pagamento), suprime as previstas redundantes do caminho de app e grava o cenario ativo do perfil.
create function financeiro.ativar_mobilidade(p_perfil_id integer, p_dados jsonb, p_chave uuid)
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
           and i.origem_id = v_anterior.origem_id and i.recorrente and i.ativo;
        update public.mobilidade_cenario_ativo set status = 'INATIVO', updated_at = financeiro.mob_agora()
         where id = v_anterior.id;
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
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'ativar_mobilidade', jsonb_build_object(
        'cenario', financeiro.mob_cenario_flask(v_c),
        'recorrencia', case when v_rec.id is not null then financeiro.item_despesa_flask(v_rec) end,
        'anterior_inativado', v_anterior.id, 'avisos', v_avisos));
end
$$;

create function financeiro.criar_assinatura_mobilidade(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep   jsonb;
    v_nome  text := btrim(coalesce(p_dados ->> 'nome', ''));
    v_valor numeric := financeiro.numero_seguro(p_dados -> 'valor_mensal');
    v_a     public.mobilidade_assinatura;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_rep := financeiro.repeticao_mobilidade(p_chave, p_perfil_id, 'criar_assinatura');
    if v_rep is not null then
        return v_rep;
    end if;
    if v_nome = '' then raise exception 'nome e obrigatorio' using errcode = '22023'; end if;
    if v_valor is null or v_valor <= 0 then raise exception 'valor_mensal deve ser > 0' using errcode = '22023'; end if;
    insert into public.mobilidade_assinatura (perfil_financeiro_id, nome, valor_mensal, categoria_id, status, metadata_json,
                                              created_at, updated_at)
    values (p_perfil_id, v_nome, v_valor, financeiro.mob_categoria('MOB_ASSINATURA'), 'ATIVO',
            case when jsonb_typeof(p_dados -> 'metadata_json') = 'string' then p_dados ->> 'metadata_json'
                 when jsonb_typeof(p_dados -> 'metadata_json') in ('object', 'array') then (p_dados -> 'metadata_json')::text end,
            financeiro.mob_agora(), financeiro.mob_agora())
    returning * into v_a;
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'criar_assinatura',
        jsonb_build_object('assinatura_id', v_a.id, 'data', financeiro.mob_assinatura_flask(v_a)));
end
$$;

create function financeiro.editar_assinatura_mobilidade(p_perfil_id integer, p_assinatura_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_a     public.mobilidade_assinatura;
    v_valor numeric;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    select * into v_a from public.mobilidade_assinatura a
     where a.id = p_assinatura_id and financeiro.pertence_ao_perfil(a.perfil_financeiro_id, p_perfil_id) for update;
    if not found then
        raise exception 'MobilidadeAssinatura nao encontrada' using errcode = '22023';
    end if;
    if p_dados ? 'nome' then
        v_a.nome := coalesce(nullif(btrim(coalesce(p_dados ->> 'nome', '')), ''), v_a.nome);
    end if;
    if p_dados ? 'valor_mensal' then
        v_valor := financeiro.numero_seguro(p_dados -> 'valor_mensal');
        if v_valor > 0 then
            v_a.valor_mensal := v_valor;
        end if;
    end if;
    if p_dados ? 'categoria_id' then
        v_a.categoria_id := financeiro.mob_categoria('MOB_ASSINATURA');
    end if;
    if p_dados ->> 'status' in ('ATIVO', 'INATIVO') then
        v_a.status := p_dados ->> 'status';
    end if;
    if p_dados ? 'metadata_json' then
        v_a.metadata_json := case when jsonb_typeof(p_dados -> 'metadata_json') = 'string' then p_dados ->> 'metadata_json'
                                  when jsonb_typeof(p_dados -> 'metadata_json') in ('object', 'array')
                                  then (p_dados -> 'metadata_json')::text end;
    end if;
    update public.mobilidade_assinatura
       set nome = v_a.nome, valor_mensal = v_a.valor_mensal, categoria_id = v_a.categoria_id, status = v_a.status,
           metadata_json = v_a.metadata_json, updated_at = financeiro.mob_agora()
     where id = v_a.id
    returning * into v_a;
    return jsonb_build_object('data', financeiro.mob_assinatura_flask(v_a));
end
$$;

-- =====================================================================================================================
-- Transporte por app (POST/PUT/DELETE /api/mobilidade-app): o caminho vive nas previstas TRANSPORTE_APP
-- =====================================================================================================================

-- gerar_projecoes_transporte_app: uma prevista por competencia; so PREVISTA e substituida.
create function financeiro.mob_gerar_projecoes_app(p_perfil_id integer, p_origem_id integer, p_cfg jsonb, p_meses integer)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_inicio  date := date_trunc('month', financeiro.hoje_brasilia())::date;
    v_fim     date := (v_inicio + make_interval(months => greatest(coalesce(p_meses, 12), 1)))::date;
    v_bloq    date[] := '{}';
    v_d       record;
    v_ref     date;
    v_cat     integer := financeiro.mob_categoria('MOB_APP');
    v_valor   numeric := (p_cfg ->> 'valor_mensal')::numeric;
    v_n       integer := 0;
begin
    for v_d in select d.* from public.despesa_prevista d
                where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'TRANSPORTE_APP'
                  and d.origem_id = p_origem_id and d.data_prevista >= v_inicio and d.data_prevista < v_fim
                  and financeiro.mob_tipo_evento(d.metadata) = 'TRANSPORTE_APP' and d.status is not null and d.status <> 'PREVISTA'
    loop
        if coalesce(v_d.data_original_prevista, v_d.data_prevista) >= v_inicio and coalesce(v_d.data_original_prevista, v_d.data_prevista) < v_fim then
            v_bloq := v_bloq || coalesce(v_d.data_original_prevista, v_d.data_prevista);
        end if;
        if coalesce(v_d.data_atual_prevista, v_d.data_prevista) >= v_inicio and coalesce(v_d.data_atual_prevista, v_d.data_prevista) < v_fim then
            v_bloq := v_bloq || coalesce(v_d.data_atual_prevista, v_d.data_prevista);
        end if;
    end loop;
    delete from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'TRANSPORTE_APP'
       and d.origem_id = p_origem_id and d.data_prevista >= v_inicio and d.data_prevista < v_fim and d.status = 'PREVISTA'
       and financeiro.mob_tipo_evento(d.metadata) = 'TRANSPORTE_APP';
    v_ref := v_inicio;
    while v_ref < v_fim loop
        if not (v_ref = any (v_bloq)) then
            perform financeiro.mob_inserir_prevista(p_perfil_id, 'TRANSPORTE_APP', p_origem_id, v_cat, v_ref, v_valor,
                jsonb_build_object('tipo_evento', 'TRANSPORTE_APP', 'caminho', p_cfg -> 'caminho',
                                   'calculo', jsonb_build_object('valor_mensal', v_valor::float8, 'base', 'KM'),
                                   'ciclo_id', null, 'ordem_no_ciclo', null));
            v_n := v_n + 1;
        end if;
        v_ref := (v_ref + interval '1 month')::date;
    end loop;
    return v_n;
end
$$;

create function financeiro.criar_caminho_app(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep jsonb;
    v_id  integer;
    v_cfg jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_rep := financeiro.repeticao_mobilidade(p_chave, p_perfil_id, 'criar_caminho_app');
    if v_rep is not null then
        return v_rep;
    end if;
    select coalesce(max(d.origem_id), 0) + 1 into v_id from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'TRANSPORTE_APP';
    v_cfg := financeiro.mob_config_app(coalesce(p_dados, '{}'::jsonb));
    perform financeiro.mob_gerar_projecoes_app(p_perfil_id, v_id, v_cfg, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    return financeiro.registrar_operacao_mobilidade(p_chave, p_perfil_id, 'criar_caminho_app', jsonb_build_object('id', v_id));
end
$$;

-- Correcao: caminho inexistente nao e "editado" (o Flask criava previstas para qualquer id).
create function financeiro.editar_caminho_app(p_perfil_id integer, p_caminho_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if financeiro.caminho_app_md(p_perfil_id, p_caminho_id) is null then
        raise exception 'Caminho não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    perform financeiro.mob_gerar_projecoes_app(p_perfil_id, p_caminho_id, financeiro.mob_config_app(coalesce(p_dados, '{}'::jsonb)),
        financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    return jsonb_build_object('id', p_caminho_id);
end
$$;

-- Correcao: com historico (confirmadas/adiadas) ou sendo a modalidade ativa, nada e removido (o Flask apagava tudo).
create function financeiro.excluir_caminho_app(p_perfil_id integer, p_caminho_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not exists (select 1 from public.despesa_prevista d
                    where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'TRANSPORTE_APP'
                      and d.origem_id = p_caminho_id) then
        raise exception 'Caminho não encontrado' using errcode = '22023', hint = 'NAO_ENCONTRADA';
    end if;
    if exists (select 1 from public.mobilidade_cenario_ativo c
                where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and c.status = 'ATIVO'
                  and c.tipo_modalidade = 'TRANSPORTE_APP' and c.origem_id = p_caminho_id) then
        raise exception 'Este caminho é a modalidade de mobilidade ativa. Ative outra modalidade antes de remover. Nada foi removido.'
            using errcode = '22023', hint = 'EM_USO';
    end if;
    if exists (select 1 from public.despesa_prevista d
                where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'TRANSPORTE_APP'
                  and d.origem_id = p_caminho_id
                  and (d.status in ('CONFIRMADA', 'ADIADA')
                       or exists (select 1 from public.despesa_prevista_acao_log l
                                   where l.despesa_prevista_id = d.id or l.despesa_prevista_criada_id = d.id))) then
        raise exception 'O caminho tem despesas previstas já confirmadas ou adiadas (histórico). Nada foi removido.'
            using errcode = '22023', hint = 'COM_HISTORICO';
    end if;
    delete from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.origem_tipo = 'TRANSPORTE_APP'
       and d.origem_id = p_caminho_id;
    return jsonb_build_object('id', p_caminho_id, 'removido', true);
end
$$;

-- =====================================================================================================================
-- Despesas previstas (POST /api/despesas-previstas/<id>/confirmar | adiar | ignorar)
-- =====================================================================================================================

-- Prevista do perfil, travada, ainda PREVISTA (_assert_prevista, com o backfill das datas).
create function financeiro.mob_prevista(p_perfil_id integer, p_id integer)
    returns public.despesa_prevista
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d public.despesa_prevista;
begin
    select * into v_d from public.despesa_prevista d where d.id = p_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_d.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Despesa prevista não encontrada' using errcode = '22023';
    end if;
    if v_d.status <> 'PREVISTA' then
        raise exception 'Apenas despesas PREVISTA podem ser alteradas nesta fase' using errcode = '22023';
    end if;
    if v_d.data_original_prevista is null or v_d.data_atual_prevista is null then
        update public.despesa_prevista
           set data_original_prevista = coalesce(data_original_prevista, data_prevista),
               data_atual_prevista = coalesce(data_atual_prevista, data_prevista)
         where id = v_d.id
        returning * into v_d;
    end if;
    return v_d;
end
$$;

-- _descricao_para_prevista do Flask.
create function financeiro.mob_rotulo_prevista(p_d public.despesa_prevista)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select coalesce(case upper(coalesce(financeiro.mob_tipo_evento(p_d.metadata), p_d.origem_tipo, ''))
        when 'COMBUSTIVEL' then 'Combustível' when 'IPVA' then 'IPVA' when 'SEGURO' then 'Seguro'
        when 'LICENCIAMENTO' then 'Licenciamento' when 'PARCELA_FINANCIAMENTO' then 'Parcela de financiamento'
        when 'IOF_FINANCIAMENTO' then 'IOF de financiamento' when 'TRANSPORTE_APP' then 'Transporte por app'
        when 'TROCA_OLEO' then 'Troca de óleo' when 'TROCA_PNEUS' then 'Troca de pneus' when 'REVISAO_GERAL' then 'Revisão geral'
        when 'ALINHAMENTO_BALANCEAMENTO' then 'Alinhamento / Balanceamento' end,
        nullif(coalesce(financeiro.mob_tipo_evento(p_d.metadata), p_d.origem_tipo, ''), ''), 'Despesa prevista')
$$;

-- registrar_despesa_combustivel_confirmada: km estimado acumulado do veiculo (so combustivel CONFIRMADA, cursor por id).
create function financeiro.mob_registrar_combustivel(p_perfil_id integer, p_d public.despesa_prevista)
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
begin
    if p_d.origem_tipo <> 'VEICULO' or p_d.status <> 'CONFIRMADA' or financeiro.mob_tipo_evento(p_d.metadata) is distinct from 'COMBUSTIVEL' then
        return;
    end if;
    select * into v_v from public.veiculo v where v.id = p_d.origem_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_v.perfil_financeiro_id, p_perfil_id) then
        return;
    end if;
    if v_v.km_estimado_ultimo_despesa_prevista_id is not null and p_d.id <= v_v.km_estimado_ultimo_despesa_prevista_id then
        return;
    end if;
    if coalesce(v_v.autonomia_km_l, 0) <= 0 then
        return;
    end if;
    v_litros := financeiro.numero_seguro(v_md -> 'litros_abastecidos');
    if v_litros is null or v_litros <= 0 then
        v_litros := case when coalesce(v_v.preco_medio_combustivel, 0) > 0 and coalesce(p_d.valor_previsto, 0) > 0
                         then p_d.valor_previsto / v_v.preco_medio_combustivel end;
    end if;
    if coalesce(v_litros, 0) <= 0 then
        return;
    end if;
    update public.veiculo
       set km_estimado_acumulado = coalesce(km_estimado_acumulado, 0) + v_litros * autonomia_km_l,
           km_estimado_ultimo_despesa_prevista_id = p_d.id, km_estimado_ultimo_calculo_em = financeiro.mob_agora()
     where id = v_v.id;
end
$$;

-- confirmar: com meio_pagamento cria a Conta (ou o lancamento no cartao, pelo motor de compras); sem, so o status.
-- Repetir e recusado (a prevista ja nao e PREVISTA): nunca duplica.
create function financeiro.confirmar_despesa_prevista(p_perfil_id integer, p_id integer, p_dados jsonb)
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
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_d := financeiro.mob_prevista(p_perfil_id, p_id);
    if p_dados ? 'meio_pagamento' and v_meio is not null then
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
    update public.despesa_prevista set status = 'CONFIRMADA', atualizado_em = financeiro.mob_agora() where id = v_d.id
    returning * into v_d;
    perform financeiro.mob_registrar_combustivel(p_perfil_id, v_d);
    return jsonb_build_object('despesa_prevista', jsonb_build_object('id', v_d.id, 'status', v_d.status),
                              'entidade_criada', v_criada);
end
$$;

-- ajustar_ciclo_um_passo (cascata do Flask): associa a adiada ao ciclo e gera so a PROXIMA ocorrencia estimada.
create function financeiro.mob_ajustar_ciclo(p_perfil_id integer, p_d public.despesa_prevista)
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

create function financeiro.adiar_despesa_prevista(p_perfil_id integer, p_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d      public.despesa_prevista;
    v_nova   date := financeiro.mob_data(p_dados ->> 'nova_data');
    v_ajuste boolean := financeiro.mob_bool(p_dados -> 'ajustar_ciclo', false);
    v_ciclo  jsonb;
    v_criada integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_d := financeiro.mob_prevista(p_perfil_id, p_id);
    if v_nova is null then
        raise exception 'nova_data inválida (use YYYY-MM-DD)' using errcode = '22023';
    end if;
    v_nova := date_trunc('month', v_nova)::date;
    update public.despesa_prevista
       set status = 'ADIADA', data_atual_prevista = v_nova, data_prevista = v_nova, atualizado_em = financeiro.mob_agora()
     where id = v_d.id
    returning * into v_d;
    if v_ajuste then
        v_ciclo := financeiro.mob_ajustar_ciclo(p_perfil_id, v_d);
        v_criada := (v_ciclo ->> 'criada')::integer;
    end if;
    insert into public.despesa_prevista_acao_log (despesa_prevista_id, acao, ajustar_ciclo, despesa_prevista_criada_id, criado_em)
    values (v_d.id, 'ADIAR', v_ajuste, v_criada, financeiro.mob_agora());
    select * into v_d from public.despesa_prevista where id = v_d.id;
    return jsonb_build_object('data', financeiro.despesa_prevista_flask(v_d),
        'ciclo', jsonb_build_object('ajustado', v_criada is not null or v_ajuste, 'despesa_prevista_criada_id', v_criada));
end
$$;

create function financeiro.ignorar_despesa_prevista(p_perfil_id integer, p_id integer)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d public.despesa_prevista;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_d := financeiro.mob_prevista(p_perfil_id, p_id);
    update public.despesa_prevista set status = 'IGNORADA', atualizado_em = financeiro.mob_agora() where id = v_d.id
    returning * into v_d;
    return jsonb_build_object('data', financeiro.despesa_prevista_flask(v_d));
end
$$;

-- =====================================================================================================================
-- Privilegios: internas sem EXECUTE para o navegador; as de tela so para authenticated.
-- =====================================================================================================================

revoke execute on function financeiro.repeticao_mobilidade(uuid, integer, text) from public, anon, authenticated;
revoke execute on function financeiro.registrar_operacao_mobilidade(uuid, integer, text, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.mob_categoria(text) from public, anon, authenticated;
revoke execute on function financeiro.mob_categoria_evento(text) from public, anon, authenticated;
revoke execute on function financeiro.mob_inteiro(jsonb) from public, anon, authenticated;
revoke execute on function financeiro.mob_meses(jsonb, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_data(text) from public, anon, authenticated;
revoke execute on function financeiro.mob_bool(jsonb, boolean) from public, anon, authenticated;
revoke execute on function financeiro.mob_agora() from public, anon, authenticated;
revoke execute on function financeiro.mob_veiculo(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_aplicar_categorias(integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_tipo_evento(text) from public, anon, authenticated;
revoke execute on function financeiro.mob_inserir_prevista(integer, text, integer, integer, date, numeric, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.mob_gerar_projecoes(integer, integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_dados_veiculo(public.veiculo, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.mob_limpar_financiamento(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_financiamento_flask(public.veiculo_financiamento) from public, anon, authenticated;
revoke execute on function financeiro.mob_resolver_cc(integer, integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_assinatura_flask(public.mobilidade_assinatura) from public, anon, authenticated;
revoke execute on function financeiro.mob_cenario_flask(public.mobilidade_cenario_ativo) from public, anon, authenticated;
revoke execute on function financeiro.mob_config_app(jsonb) from public, anon, authenticated;
revoke execute on function financeiro.mob_origem(integer, text, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_cartao(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_gerar_projecoes_app(integer, integer, jsonb, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_prevista(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.mob_rotulo_prevista(public.despesa_prevista) from public, anon, authenticated;
revoke execute on function financeiro.mob_registrar_combustivel(integer, public.despesa_prevista) from public, anon, authenticated;
revoke execute on function financeiro.mob_ajustar_ciclo(integer, public.despesa_prevista) from public, anon, authenticated;

revoke execute on function financeiro.criar_veiculo(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_veiculo(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.converter_veiculo(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.gerar_projecoes_veiculo(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.excluir_veiculo(integer, integer) from public, anon;
revoke execute on function financeiro.criar_regra_km_veiculo(integer, integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.excluir_regra_km_veiculo(integer, integer, integer) from public, anon;
revoke execute on function financeiro.gerar_manutencao_km_veiculo(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.salvar_financiamento_veiculo(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.excluir_financiamento_veiculo(integer, integer) from public, anon;
revoke execute on function financeiro.previa_mobilidade(integer, jsonb) from public, anon;
revoke execute on function financeiro.ativar_mobilidade(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.criar_assinatura_mobilidade(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_assinatura_mobilidade(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.criar_caminho_app(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_caminho_app(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.excluir_caminho_app(integer, integer) from public, anon;
revoke execute on function financeiro.confirmar_despesa_prevista(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.adiar_despesa_prevista(integer, integer, jsonb) from public, anon;
revoke execute on function financeiro.ignorar_despesa_prevista(integer, integer) from public, anon;

grant execute on function financeiro.criar_veiculo(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_veiculo(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.converter_veiculo(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.gerar_projecoes_veiculo(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.excluir_veiculo(integer, integer) to authenticated;
grant execute on function financeiro.criar_regra_km_veiculo(integer, integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.excluir_regra_km_veiculo(integer, integer, integer) to authenticated;
grant execute on function financeiro.gerar_manutencao_km_veiculo(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.salvar_financiamento_veiculo(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.excluir_financiamento_veiculo(integer, integer) to authenticated;
grant execute on function financeiro.previa_mobilidade(integer, jsonb) to authenticated;
grant execute on function financeiro.ativar_mobilidade(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.criar_assinatura_mobilidade(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_assinatura_mobilidade(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.criar_caminho_app(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_caminho_app(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.excluir_caminho_app(integer, integer) to authenticated;
grant execute on function financeiro.confirmar_despesa_prevista(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.adiar_despesa_prevista(integer, integer, jsonb) to authenticated;
grant execute on function financeiro.ignorar_despesa_prevista(integer, integer) to authenticated;
