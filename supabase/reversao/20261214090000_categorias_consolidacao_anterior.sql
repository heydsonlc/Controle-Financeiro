-- Reversao de 20261214090000 (FIN-CATEGORIAS-CONSOLIDACAO-01): volta as funcoes de Mobilidade ao texto anterior (10 categorias sistemicas, revisao
-- em MOB_REVISAO) e remove a incorporacao. Recusada depois de uma incorporacao (a categoria de origem nao existe mais e
-- MOB_REVISAO voltaria a ser exigida). So com autorizacao, retirando a versao de supabase_migrations.schema_migrations.
do $$
begin
    if exists (select 1 from financeiro.operacao_catalogo o where o.operacao = 'incorporar_categoria') then
        raise exception 'Ha categorias incorporadas: a reversao exigiria categorias que nao existem mais';
    end if;
end
$$;

-- categorias_sistemicas_mobilidade: texto de 20261125090000.
create or replace function financeiro.categorias_sistemicas_mobilidade()
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

-- mob_categoria_evento: texto de 20261127090000.
create or replace function financeiro.mob_categoria_evento(p_tipo text)
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

drop function financeiro.incorporar_categoria(integer, integer, jsonb, text, uuid);
drop function financeiro.previa_incorporacao_categoria(integer, integer, jsonb);
drop function financeiro.referencias_categoria(integer);
