"""Gera a migration 20261215090000 (FIN-MVP-MOB-01) e a reversao a partir do texto VIGENTE de cada funcao substituida, com
substituicoes conferidas (cada trecho deve ocorrer o numero de vezes esperado).

Para mudar a migration, edite este gerador e rode-o; as fontes sao as migrations anteriores (versionadas, imutaveis). So
texto SQL: nenhum dado, conexao ou credencial.

    python scripts/gerar_migration_mobilidade_integridade.py              # grava a migration e a reversao
    python scripts/gerar_migration_mobilidade_integridade.py --verificar  # so compara com os arquivos versionados

O teste tests/test_gerador_migration_mobilidade_integridade.py confere que os arquivos versionados sao a saida exata.
"""
import argparse
import re
import sys
from pathlib import Path

_args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
_args.add_argument('raiz', nargs='?', default=str(Path(__file__).resolve().parents[1]), help='raiz do projeto')
_args.add_argument('--verificar', action='store_true', help='nao grava: falha se a saida difere dos arquivos versionados')
ARGS = _args.parse_args()
RAIZ = Path(ARGS.raiz)
MIG = RAIZ / 'supabase' / 'migrations'
MARCA = 'FIN-MVP-MOB-01'
VERSAO = '20261215090000'
F1115 = '20261115090000_financeiro_mobilidade_leitura.sql'
F1117 = '20261117090000_financeiro_lastro_saidas_leitura.sql'
F1127 = '20261127090000_financeiro_mobilidade_escrita.sql'
F1209 = '20261209090000_financeiro_cartao_previsto_executado.sql'


def bloco(arquivo, nome):
    texto = (MIG / arquivo).read_text(encoding='utf-8')
    m = list(re.finditer(r'create (?:or replace )?function financeiro\.' + nome + r'\(', texto))
    assert m, nome
    ini = m[-1].start()
    fim = texto.index('\n$$;', ini) + len('\n$$;')
    return texto[ini:fim]


def trocar(texto, antigo, novo, vezes=1):
    n = texto.count(antigo)
    assert n == vezes, f'trecho encontrado {n} vezes (esperado {vezes}): {antigo[:80]!r}'
    return texto.replace(antigo, novo)


def como_replace(b):
    return re.sub(r'^create function', 'create or replace function', b)


FONTES = {
    'veiculo_flask': F1115,
    'uso_do_veiculo': F1115,
    'saidas_lastro': F1117,
    'dashboard_resumo_tela': F1209,
    'mob_inserir_prevista': F1127,
    'mob_gerar_projecoes': F1127,
    'mob_dados_veiculo': F1127,
    'criar_veiculo': F1127,
    'editar_veiculo': F1127,
    'ativar_mobilidade': F1127,
    'mob_registrar_combustivel': F1127,
    'confirmar_despesa_prevista': F1127,
}
ORIG = {n: bloco(a, n) for n, a in FONTES.items()}
NOVO = {}

# ---------------------------------------------------------------------------------------------------------------------
# Veiculos simulados fora do que e financeiro real
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['dashboard_resumo_tela']
t = trocar(t, """                               and date_trunc('month', d.data_atual_prevista) = v_inicio
                               and d.status in ('PREVISTA', 'ADIADA')), 0);
""", f"""                               and date_trunc('month', d.data_atual_prevista) = v_inicio
                               and d.status in ('PREVISTA', 'ADIADA')
                               and financeiro.prevista_financeira(d.origem_tipo, d.origem_id)), 0);  -- {MARCA}
""")
t = trocar(t, """     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.data_atual_prevista < v_hoje
       and d.status in ('PREVISTA', 'ADIADA');
""", f"""     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.data_atual_prevista < v_hoje
       and d.status in ('PREVISTA', 'ADIADA')
       and financeiro.prevista_financeira(d.origem_tipo, d.origem_id);  -- {MARCA}
""")
t = trocar(t, """     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.data_atual_prevista between v_inicio and v_fim;
""", f"""     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.data_atual_prevista between v_inicio and v_fim
       and d.status <> 'SUPRIMIDA'
       and financeiro.prevista_financeira(d.origem_tipo, d.origem_id);  -- {MARCA}
""")
NOVO['dashboard_resumo_tela'] = t

t = ORIG['saidas_lastro']
t = trocar(t, """               and d.status not in ('IGNORADA', 'CANCELADA', 'SUPRIMIDA')
""", f"""               and d.status not in ('IGNORADA', 'CANCELADA', 'SUPRIMIDA')
               and financeiro.prevista_financeira(d.origem_tipo, d.origem_id)  -- {MARCA}
""")
NOVO['saidas_lastro'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Identidade da ocorrencia (obrigacao + periodo), vinculos e ids preservados
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['mob_inserir_prevista']
t = trocar(t, """                                         data_original_prevista, data_atual_prevista, valor_previsto, status, metadata,
                                         criado_em, atualizado_em)
    values (p_perfil_id, p_origem_tipo, p_origem_id, p_categoria_id, p_data, p_data, p_data, p_valor, 'PREVISTA',
            p_metadata::text, financeiro.mob_agora(), financeiro.mob_agora())
""", f"""                                         data_original_prevista, data_atual_prevista, valor_previsto, status, metadata,
                                         criado_em, atualizado_em, obrigacao, periodo_referencia)
    select p_perfil_id, p_origem_tipo, p_origem_id, p_categoria_id, p_data, p_data, p_data, p_valor, 'PREVISTA',
           p_metadata::text, financeiro.mob_agora(), financeiro.mob_agora(), o.tipo,
           case when o.tipo is not null then financeiro.mob_periodo(o.tipo, p_data) end
      -- {MARCA}: identidade so das obrigacoes projetadas do veiculo (as de manutencao seguem por ciclo)
      from (select case when p_origem_tipo = 'VEICULO' and p_metadata ->> 'tipo_evento' in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO')
                        then p_metadata ->> 'tipo_evento' end as tipo) o
""")
NOVO['mob_inserir_prevista'] = t

NOVO['mob_gerar_projecoes'] = f"""create or replace function financeiro.mob_gerar_projecoes(p_perfil_id integer, p_veiculo_id integer, p_meses integer)
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
    v_bloq      text[] := '{{}}';
    v_d         record;
    v_ref       date;
    v_mantidas  integer[] := '{{}}';
    v_evento    record;
    v_ano       integer;
begin
    select * into v_v from public.veiculo where id = p_veiculo_id;
    v_inicio := date_trunc('month', greatest(coalesce(v_v.data_inicio, v_hoje), v_hoje))::date;
    v_fim := (v_inicio + make_interval(months => v_meses))::date;
    v_perfil := coalesce(v_v.perfil_financeiro_id, p_perfil_id);

    -- {MARCA}: competencia em que o usuario ja agiu nao volta. A identidade e a obrigacao + o periodo (mes do combustivel,
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
$$;"""

t = ORIG['confirmar_despesa_prevista']
t = trocar(t, """    v_compra  jsonb;
    v_criada  jsonb := null;
begin
""", """    v_compra  jsonb;
    v_criada  jsonb := null;
    v_lanc    integer;
    v_veiculo public.veiculo;
    v_tipo    text;
    v_md      jsonb;
begin
""")
t = trocar(t, """    v_d := financeiro.mob_prevista(p_perfil_id, p_id);
    if p_dados ? 'meio_pagamento' and v_meio is not null then
""", f"""    v_d := financeiro.mob_prevista(p_perfil_id, p_id);
    v_tipo := financeiro.mob_tipo_evento(v_d.metadata);
    if v_d.origem_tipo = 'VEICULO' then
        select * into v_veiculo from public.veiculo v where v.id = v_d.origem_id;
    end if;
    if p_dados ? 'meio_pagamento' and v_meio is not null then
        -- {MARCA}: simulacao nao vira obrigacao real
        if v_veiculo.status = 'SIMULADO' then
            raise exception 'Veículo simulado: efetive o veículo antes de gerar a despesa. Nada foi gravado.'
                using errcode = '22023', hint = 'VEICULO_SIMULADO';
        end if;
""")
t = trocar(t, """        v_nome := financeiro.mob_rotulo_prevista(v_d);
        if v_meio = 'cartao' then
""", f"""        -- {MARCA}: com a recorrencia do veiculo, ela e a fonte unica da despesa de combustivel da competencia
        if v_veiculo.id is not null and v_tipo = 'COMBUSTIVEL'
           and financeiro.mob_competencia_coberta(p_perfil_id, v_veiculo.id, date_trunc('month', v_venc::timestamp)::date) then
            raise exception 'O combustível desta competência já é lançado pela recorrência do veículo. Nada foi gravado.'
                using errcode = '22023', hint = 'COMBUSTIVEL_COBERTO';
        end if;
        v_nome := financeiro.mob_rotulo_prevista(v_d);
        if v_meio = 'cartao' then
""")
t = trocar(t, """            v_criada := jsonb_build_object('tipo', 'lancamento_agregado', 'compra', v_compra, 'descricao', v_nome,
""", """            v_lanc := (v_compra -> 'lancamentos' ->> 0)::integer;
            v_criada := jsonb_build_object('tipo', 'lancamento_agregado', 'compra', v_compra, 'descricao', v_nome,
""")
t = trocar(t, """    update public.despesa_prevista set status = 'CONFIRMADA', atualizado_em = financeiro.mob_agora() where id = v_d.id
    returning * into v_d;
""", f"""    -- {MARCA}: vinculo com a conta ou compra criada e, no combustivel, os parametros do momento (mudar a autonomia ou o
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
""")
NOVO['confirmar_despesa_prevista'] = t

t = ORIG['mob_registrar_combustivel']
t = trocar(t, """    v_litros numeric;
begin
""", """    v_litros numeric;
    v_aut    numeric;
    v_preco  numeric;
begin
""")
t = trocar(t, """    if v_v.km_estimado_ultimo_despesa_prevista_id is not null and p_d.id <= v_v.km_estimado_ultimo_despesa_prevista_id then
        return;
    end if;
    if coalesce(v_v.autonomia_km_l, 0) <= 0 then
        return;
    end if;
""", f"""    -- {MARCA}: os ids das previstas agora sao preservados e a confirmacao e unica (so PREVISTA confirma): confirmar fora de
    -- ordem conta o km; e os parametros sao os gravados na confirmacao
    v_aut := coalesce(financeiro.numero_seguro(v_md -> 'autonomia_km_l'), v_v.autonomia_km_l);
    v_preco := coalesce(financeiro.numero_seguro(v_md -> 'preco_litro'), v_v.preco_medio_combustivel);
    if coalesce(v_aut, 0) <= 0 then
        return;
    end if;
""")
t = trocar(t, """        v_litros := case when coalesce(v_v.preco_medio_combustivel, 0) > 0 and coalesce(p_d.valor_previsto, 0) > 0
                         then p_d.valor_previsto / v_v.preco_medio_combustivel end;
""", """        v_litros := case when coalesce(v_preco, 0) > 0 and coalesce(p_d.valor_previsto, 0) > 0
                         then p_d.valor_previsto / v_preco end;
""")
t = trocar(t, """       set km_estimado_acumulado = coalesce(km_estimado_acumulado, 0) + v_litros * autonomia_km_l,
           km_estimado_ultimo_despesa_prevista_id = p_d.id, km_estimado_ultimo_calculo_em = financeiro.mob_agora()
""", """       set km_estimado_acumulado = coalesce(km_estimado_acumulado, 0) + v_litros * v_aut,
           km_estimado_ultimo_despesa_prevista_id = greatest(km_estimado_ultimo_despesa_prevista_id, p_d.id),
           km_estimado_ultimo_calculo_em = financeiro.mob_agora()
""")
NOVO['mob_registrar_combustivel'] = t

t = ORIG['uso_do_veiculo']
t = trocar(t, """            v_km     numeric;
            v_chave  text := to_char(v_d.data_ref, 'YYYY-MM');
        begin
            if v_litros is null or v_litros <= 0 then
                v_litros := case when coalesce(p_v.preco_medio_combustivel, 0) > 0 and coalesce(v_d.valor_previsto, 0) > 0
                                 then v_d.valor_previsto / p_v.preco_medio_combustivel end;
            end if;
            continue when coalesce(p_v.autonomia_km_l, 0) <= 0 or coalesce(v_litros, 0) <= 0;
            v_km := v_litros * p_v.autonomia_km_l;
""", f"""            v_km     numeric;
            v_chave  text := to_char(v_d.data_ref, 'YYYY-MM');
            -- {MARCA}: parametros gravados na confirmacao (sem eles, os atuais do veiculo, como antes)
            v_aut    numeric := coalesce(financeiro.numero_seguro(v_d.md -> 'autonomia_km_l'), p_v.autonomia_km_l);
            v_preco  numeric := coalesce(financeiro.numero_seguro(v_d.md -> 'preco_litro'), p_v.preco_medio_combustivel);
        begin
            if v_litros is null or v_litros <= 0 then
                v_litros := case when coalesce(v_preco, 0) > 0 and coalesce(v_d.valor_previsto, 0) > 0
                                 then v_d.valor_previsto / v_preco end;
            end if;
            continue when coalesce(v_aut, 0) <= 0 or coalesce(v_litros, 0) <= 0;
            v_km := v_litros * v_aut;
""")
NOVO['uso_do_veiculo'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Recorrencia de combustivel: fonte unica da despesa e sincronizada com o veiculo
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['ativar_mobilidade']
t = trocar(t, """        update public.mobilidade_cenario_ativo set status = 'INATIVO', updated_at = financeiro.mob_agora()
         where id = v_anterior.id;
    end if;
""", f"""        update public.mobilidade_cenario_ativo set status = 'INATIVO', updated_at = financeiro.mob_agora()
         where id = v_anterior.id;
        -- {MARCA}: sem a recorrencia, as previsoes de combustivel suprimidas por ela voltam (exceto as ja cobertas)
        if v_anterior.tipo_modalidade = 'VEICULO' then
            perform financeiro.mob_restaurar_combustivel(p_perfil_id, v_anterior.origem_id);
        end if;
    end if;
""")
t = trocar(t, """        if v_tipo = 'TRANSPORTE_APP' then
            update public.despesa_prevista d set status = 'SUPRIMIDA', atualizado_em = financeiro.mob_agora()
""", f"""        -- {MARCA}: a recorrencia passa a ser a fonte unica do combustivel: nao gera competencia ja coberta e as previsoes
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
""")
NOVO['ativar_mobilidade'] = t

t = ORIG['editar_veiculo']
t = trocar(t, """declare
    v public.veiculo;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v := financeiro.mob_dados_veiculo(financeiro.mob_veiculo(p_perfil_id, p_veiculo_id), coalesce(p_dados, '{}'::jsonb));
""", """declare
    v       public.veiculo;
    v_antes public.veiculo;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    v_antes := financeiro.mob_veiculo(p_perfil_id, p_veiculo_id);
    v := financeiro.mob_dados_veiculo(v_antes, coalesce(p_dados, '{}'::jsonb));
""")
t = trocar(t, """           preco_medio_combustivel = v.preco_medio_combustivel, atualizado_em = financeiro.mob_agora()
     where id = v.id;
""", """           preco_medio_combustivel = v.preco_medio_combustivel, atualizado_em = financeiro.mob_agora(),
           autonomia_gasolina_km_l = v.autonomia_gasolina_km_l, autonomia_etanol_km_l = v.autonomia_etanol_km_l,
           preco_gasolina = v.preco_gasolina, preco_etanol = v.preco_etanol, combustivel_referencia = v.combustivel_referencia,
           km_mensal_estimado = v.km_mensal_estimado, custo_combustivel_modo = v.custo_combustivel_modo
     where id = v.id;
""")
t = trocar(t, """    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    return jsonb_build_object('veiculo_id', v.id);
""", f"""    perform financeiro.mob_gerar_projecoes(p_perfil_id, v.id, financeiro.mob_meses(p_dados -> 'meses_futuros', 12));
    -- {MARCA}: o custo novo vale para a recorrencia e so para as ocorrencias futuras elegiveis
    if v.combustivel_valor_mensal is distinct from v_antes.combustivel_valor_mensal and coalesce(v.combustivel_valor_mensal, 0) > 0 then
        perform financeiro.mob_sincronizar_combustivel(p_perfil_id, v.id, v.combustivel_valor_mensal);
    end if;
    return jsonb_build_object('veiculo_id', v.id);
""")
NOVO['editar_veiculo'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Flex
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['mob_dados_veiculo']
t = trocar(t, """        v.autonomia_km_l := financeiro.numero_seguro(p_dados -> 'autonomia_km_l');
        v.data_inicio := financeiro.mob_data(p_dados ->> 'data_inicio');
""", f"""        v.autonomia_km_l := financeiro.numero_seguro(p_dados -> 'autonomia_km_l');
        -- {MARCA}: no Flex, a autonomia vem do combustivel de referencia (mob_dados_flex)
        if lower(v.combustivel) = 'flex' then
            v.autonomia_km_l := financeiro.numero_seguro(p_dados -> case lower(coalesce(p_dados ->> 'combustivel_referencia', ''))
                when 'etanol' then 'autonomia_etanol_km_l' else 'autonomia_gasolina_km_l' end);
        end if;
        v.data_inicio := financeiro.mob_data(p_dados ->> 'data_inicio');
""")
t = trocar(t, """    return v;
end
$$;""", f"""    return financeiro.mob_dados_flex(v, p_dados);  -- {MARCA}
end
$$;""")
NOVO['mob_dados_veiculo'] = t

t = ORIG['criar_veiculo']
t = trocar(t, """                                licenciamento_valor, preco_medio_combustivel, km_estimado_acumulado, criado_em, atualizado_em)
""", """                                licenciamento_valor, preco_medio_combustivel, km_estimado_acumulado, criado_em, atualizado_em,
                                autonomia_gasolina_km_l, autonomia_etanol_km_l, preco_gasolina, preco_etanol,
                                combustivel_referencia, km_mensal_estimado, custo_combustivel_modo)
""")
t = trocar(t, """            v.licenciamento_valor, v.preco_medio_combustivel, 0, financeiro.mob_agora(), financeiro.mob_agora())
""", """            v.licenciamento_valor, v.preco_medio_combustivel, 0, financeiro.mob_agora(), financeiro.mob_agora(),
            v.autonomia_gasolina_km_l, v.autonomia_etanol_km_l, v.preco_gasolina, v.preco_etanol,
            v.combustivel_referencia, v.km_mensal_estimado, v.custo_combustivel_modo)
""")
NOVO['criar_veiculo'] = t

t = ORIG['veiculo_flask']
t = trocar(t, """        'total_mensal_estimado', c.comb + c.seg + c.ipva + c.lic)
      from (select""", f"""        'total_mensal_estimado', c.comb + c.seg + c.ipva + c.lic)
        -- {MARCA}: so nos veiculos que usam os campos novos (os demais respondem como antes)
        || case when (p_v).combustivel = 'flex' or (p_v).custo_combustivel_modo <> 'MANUAL' or (p_v).km_mensal_estimado is not null
                then jsonb_build_object('autonomia_gasolina_km_l', (p_v).autonomia_gasolina_km_l,
                                        'autonomia_etanol_km_l', (p_v).autonomia_etanol_km_l,
                                        'preco_gasolina', (p_v).preco_gasolina, 'preco_etanol', (p_v).preco_etanol,
                                        'combustivel_referencia', (p_v).combustivel_referencia,
                                        'km_mensal_estimado', (p_v).km_mensal_estimado,
                                        'custo_combustivel_modo', (p_v).custo_combustivel_modo)
                else '{{}}'::jsonb end
      from (select""")
NOVO['veiculo_flask'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------------------------------------------------
ESTRUTURA = """-- =====================================================================================================================
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
    add constraint veiculo_combustivel_referencia_valida check (combustivel_referencia in ('gasolina', 'etanol')),
    add constraint veiculo_custo_combustivel_modo_valido check (custo_combustivel_modo in ('MANUAL', 'CALCULADO'));
comment on column public.veiculo.custo_combustivel_modo is
    'FIN-MVP-MOB-01: MANUAL = vale o valor informado; CALCULADO = km / autonomia x preco, recalculado ao salvar. O padrao nunca muda um valor existente.';
comment on column public.veiculo.autonomia_km_l is
    'Autonomia em uso. No Flex, a do combustivel de referencia (FIN-MVP-MOB-01).';

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
"""

AUXILIARES = """-- =====================================================================================================================
-- 2. Funcoes novas (internas)
-- =====================================================================================================================
-- A prevista conta como obrigacao financeira real? As de veiculo SIMULADO ficam so nas telas de Mobilidade.
create function financeiro.prevista_financeira(p_origem_tipo text, p_origem_id integer)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select not (p_origem_tipo = 'VEICULO'
                and exists (select 1 from public.veiculo v where v.id = p_origem_id and v.status = 'SIMULADO'))
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
                      and date_trunc('month', c.mes_referencia) = p_mes)
        or exists (select 1 from public.lancamento_agregado l join public.item_despesa i on i.id = l.item_despesa_id
                    where i.origem_tipo = 'VEICULO' and i.origem_id = p_veiculo_id and i.origem_contexto = 'combustivel_mensal'
                      and l.mes_fatura = p_mes)
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
               and i.id <> p_item.id
            union
            select l.mes_fatura
              from public.lancamento_agregado l join public.item_despesa i on i.id = l.item_despesa_id
             where i.origem_tipo = 'VEICULO' and i.origem_id = p_veiculo_id and i.origem_contexto = 'combustivel_mensal'
               and i.id <> p_item.id
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
"""

ORDEM = ['veiculo_flask', 'uso_do_veiculo', 'mob_inserir_prevista', 'mob_dados_veiculo', 'criar_veiculo', 'editar_veiculo',
         'mob_gerar_projecoes', 'ativar_mobilidade', 'mob_registrar_combustivel', 'confirmar_despesa_prevista',
         'dashboard_resumo_tela', 'saidas_lastro']
INTERNAS = ['mob_periodo(text, date)', 'prevista_financeira(text, integer)', 'mob_item_combustivel(integer, integer)',
            'mob_competencia_coberta(integer, integer, date)', 'mob_suprimir_combustivel(integer, integer)',
            'mob_restaurar_combustivel(integer, integer)', 'mob_dispensar_cobertas(integer, integer, public.item_despesa)',
            'mob_sincronizar_combustivel(integer, integer, numeric)',
            'mob_planejar_prevista(integer, integer, integer, text, date, numeric)', 'mob_dados_flex(public.veiculo, jsonb)']

migration = f"""-- {MARCA}: integridade financeira da Mobilidade e combustivel Flex. Gerada por scripts/gerar_migration_mobilidade_integridade.py
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

{ESTRUTURA}
{AUXILIARES}
-- =====================================================================================================================
-- 3. Funcoes substituidas
-- =====================================================================================================================
""" + '\n'.join(f'-- {n}: texto de {FONTES[n][:14]} + os trechos marcados.\n{como_replace(NOVO[n])}\n' for n in ORDEM) + f"""
-- =====================================================================================================================
-- 4. Privilegios: as funcoes novas sao internas
-- =====================================================================================================================
""" + '\n'.join(f'revoke execute on function financeiro.{f} from public, anon, authenticated;' for f in INTERNAS) + '\n'

reversao = f"""-- Reversao de {VERSAO} ({MARCA}): volta as funcoes ao texto anterior e remove as colunas novas. Recusada com veiculo Flex,
-- custo calculado ou vinculo gravado (a informacao se perderia). So com autorizacao, retirando a versao de
-- supabase_migrations.schema_migrations.
do $$
begin
    if exists (select 1 from public.veiculo v where v.combustivel = 'flex' or v.custo_combustivel_modo <> 'MANUAL' or v.km_mensal_estimado is not null) then
        raise exception 'Ha veiculo Flex ou com custo calculado: a reversao perderia esses dados';
    end if;
    if exists (select 1 from public.despesa_prevista d where d.conta_id is not null or d.lancamento_id is not null) then
        raise exception 'Ha previstas vinculadas a contas ou compras: a reversao perderia os vinculos';
    end if;
end
$$;

-- As previsoes de combustivel suprimidas por esta versao voltam a contar, como antes dela.
update public.despesa_prevista set status = 'PREVISTA'
 where status = 'SUPRIMIDA' and obrigacao = 'COMBUSTIVEL';

""" + '\n'.join(f'-- {n}: texto de {FONTES[n][:14]}.\n{como_replace(ORIG[n])}\n' for n in ORDEM) + '\n' + \
    '\n'.join(f'drop function financeiro.{f};' for f in reversed(INTERNAS[1:])) + f"""

drop index public.ux_despesa_prevista_obrigacao_periodo;
drop function financeiro.mob_periodo(text, date);
alter table public.despesa_prevista
    drop column obrigacao, drop column periodo_referencia, drop column conta_id, drop column lancamento_id;
alter table public.veiculo
    drop constraint veiculo_combustivel_referencia_valida, drop constraint veiculo_custo_combustivel_modo_valido,
    drop column autonomia_gasolina_km_l, drop column autonomia_etanol_km_l, drop column preco_gasolina, drop column preco_etanol,
    drop column combustivel_referencia, drop column km_mensal_estimado, drop column custo_combustivel_modo;
comment on column public.veiculo.autonomia_km_l is null;
"""

SAIDAS = {
    RAIZ / 'supabase' / 'migrations' / f'{VERSAO}_financeiro_mobilidade_integridade.sql': migration,
    RAIZ / 'supabase' / 'reversao' / f'{VERSAO}_mobilidade_integridade_anterior.sql': reversao,
}
if ARGS.verificar:
    falhas = [p.relative_to(RAIZ).as_posix() for p, texto in SAIDAS.items()
              if not p.exists() or p.read_bytes().decode('utf-8').replace('\r\n', '\n') != texto]
    if falhas:
        print('diferente: ' + ', '.join(falhas))
        sys.exit(1)
    print('igual')
else:
    for p, texto in SAIDAS.items():
        p.write_text(texto, encoding='utf-8', newline='\n')
    print(f'{len(SAIDAS)} arquivos gerados')
