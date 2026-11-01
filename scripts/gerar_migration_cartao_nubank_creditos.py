"""Gera a migration 20261212090000 (FIN-CARTAO-NUBANK-CREDITOS-01) e a reversao a partir do texto VIGENTE de cada funcao,
com substituicoes conferidas (cada trecho deve ocorrer o numero de vezes esperado).

As funcoes substituidas sao longas: a migration nao e editada a mao. Para muda-la, edite este gerador e rode-o; as
fontes sao as migrations anteriores (versionadas, imutaveis). So texto SQL: nenhum dado, conexao ou credencial.

    python scripts/gerar_migration_cartao_nubank_creditos.py              # grava a migration e a reversao
    python scripts/gerar_migration_cartao_nubank_creditos.py --verificar  # so compara com os arquivos versionados

O teste tests/test_gerador_migration_cartao_nubank_creditos.py confere que os arquivos versionados sao a saida exata.
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
MARCA = 'FIN-CARTAO-NUBANK-CREDITOS-01'
VERSAO = '20261212090000'


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
    'bloqueio_da_parcela': '20261028090000_financeiro_cartoes.sql',
    'executado_fatura': '20261209090000_financeiro_cartao_previsto_executado.sql',
    'recalcular_fatura': '20261209090000_financeiro_cartao_previsto_executado.sql',
    'contas_do_mes': '20261209090000_financeiro_cartao_previsto_executado.sql',
    'faturas_do_mes': '20261209090000_financeiro_cartao_previsto_executado.sql',
    'fatura_por_categoria': '20261209090000_financeiro_cartao_previsto_executado.sql',
    'lancamentos_fatura_por_categoria': '20261209090000_financeiro_cartao_previsto_executado.sql',
    'analisar_importacao_cartao': '20261211090000_financeiro_cartao_nubank_parceladas.sql',
    'importar_fatura_cartao': '20261210090000_financeiro_cartao_importacao_fixas.sql',
}
ORIG = {n: bloco(a, n) for n, a in FONTES.items()}
NOVO = {}
CRED = 'financeiro.creditos_fatura'

# ---------------------------------------------------------------------------------------------------------------------
# Compra com credito vinculado: corrigida pelo credito (nao some, nao muda de valor por baixo do credito)
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['bloqueio_da_parcela']
t = trocar(t, "    v_fat := financeiro.fatura_do_mes(v_l.cartao_id, v_l.mes_fatura);\n",
           f"    -- {MARCA}: a compra original de um credito (estorno, IOF devolvido) fica preservada\n"
           "    if exists (select 1 from financeiro.credito_fatura cf where cf.lancamento_id = p_lancamento_id) then\n"
           "        return 'Compra com credito vinculado (estorno ou IOF devolvido): preservada como no extrato';\n"
           "    end if;\n"
           "    v_fat := financeiro.fatura_do_mes(v_l.cartao_id, v_l.mes_fatura);\n")
NOVO['bloqueio_da_parcela'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Valor a pagar = executado das compras - creditos da fatura (uma vez, pela propria fatura)
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['executado_fatura']
t = trocar(t, "    select coalesce(sum(financeiro.valor_executado_compra(",
           f"    -- {MARCA}: menos os creditos da fatura (estorno, IOF devolvido, ajuste): o valor a pagar\n"
           "    select coalesce(sum(financeiro.valor_executado_compra(")
t = trocar(t, "l.is_importado, l.cartao_id, l.mes_fatura))), 0)\n      from public.conta c",
           f"l.is_importado, l.cartao_id, l.mes_fatura))), 0)\n           - {CRED}(p_fatura_id)\n      from public.conta c")
NOVO['executado_fatura'] = t

t = ORIG['recalcular_fatura']
t = trocar(t, "    update public.conta set valor_planejado = v_plan,",
           f"    -- {MARCA}: creditos da fatura abatem o executado e o planejado (valor a pagar)\n"
           f"    v_exec := v_exec - {CRED}(v_id);\n"
           f"    v_plan := v_plan - {CRED}(v_id);\n"
           "    update public.conta set valor_planejado = v_plan,")
NOVO['recalcular_fatura'] = t

t = ORIG['contas_do_mes']
t = trocar(t, "               coalesce((select sum(g.total) from gastos g where g.cartao_id = c.item_despesa_id), 0) as executado,\n",
           f"               -- {MARCA}: executado das compras menos os creditos da fatura (valor a pagar)\n"
           "               coalesce((select sum(g.total) from gastos g where g.cartao_id = c.item_despesa_id), 0)\n"
           f"                   - {CRED}(c.id) as executado,\n")
NOVO['contas_do_mes'] = t

t = ORIG['faturas_do_mes']
t = trocar(t, "coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0)",
           f"(coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0) - {CRED}(f.id))", vezes=3)
t = trocar(t, "    select c.id, c.nome::text, f.id, v_mes, f.data_vencimento,\n",
           f"    -- {MARCA}: executado e previsto ja descontam os creditos da fatura\n"
           "    select c.id, c.nome::text, f.id, v_mes, f.data_vencimento,\n")
NOVO['faturas_do_mes'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Cartoes: compras (bruto), creditos e valor a pagar; grupo "Creditos e ajustes"; creditos na lista de lancamentos
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['fatura_por_categoria']
t = trocar(t, "    v_pendente   numeric;  -- FIN-CARTAO-PREVISTO-EXECUTADO-01\nbegin\n",
           "    v_pendente   numeric;  -- FIN-CARTAO-PREVISTO-EXECUTADO-01\n"
           f"    v_fatura     integer;  -- {MARCA}\n"
           "    v_creditos   numeric;\n"
           "begin\n")
t = trocar(t, "    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);\n    with lanc as (\n",
           "    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);\n"
           "    v_fatura := financeiro.fatura_do_mes(p_cartao_id, v_mes);\n"
           f"    v_creditos := {CRED}(v_fatura);\n"
           "    with lanc as (\n")
t = trocar(t, "        select 5, 0, null, null, sum(x.valor), count(*), 'sem_categoria'\n"
              "          from lanc x where x.natureza = 'OUTROS' having count(*) > 0\n",
           "        select 5, 0, null, null, sum(x.valor), count(*), 'sem_categoria'\n"
           "          from lanc x where x.natureza = 'OUTROS' having count(*) > 0\n"
           "        union all\n"
           f"        -- 6. {MARCA}: creditos da fatura (estorno, IOF devolvido, ajuste), negativos: abatem o valor a pagar\n"
           "        select 6, 0, null, null, -sum(cf.valor), count(*), 'creditos'\n"
           "          from financeiro.credito_fatura cf where cf.fatura_id = v_fatura having count(*) > 0\n")
t = trocar(t, "               'categoria_cartao_id', case when g.tipo in ('compras_parceladas', 'despesas_fixas') then to_jsonb(g.tipo)\n",
           "               'categoria_cartao_id', case when g.tipo in ('compras_parceladas', 'despesas_fixas', 'creditos') then to_jsonb(g.tipo)\n")
t = trocar(t, "                                                    when 'despesas_fixas' then 'Despesas fixas'\n",
           "                                                    when 'despesas_fixas' then 'Despesas fixas'\n"
           "                                                    when 'creditos' then 'Creditos e ajustes'\n")
t = trocar(t, "               'natureza', case g.tipo when 'compras_parceladas' then 'PARCELADA' when 'despesas_fixas' then 'FIXA'\n",
           "               'natureza', case g.tipo when 'compras_parceladas' then 'PARCELADA' when 'despesas_fixas' then 'FIXA'\n"
           "                                       when 'creditos' then 'CREDITO'\n")
t = trocar(t, "                              when g.tipo in ('compras_parceladas', 'despesas_fixas') then 'Contratada'\n",
           "                              when g.tipo in ('compras_parceladas', 'despesas_fixas') then 'Contratada'\n"
           "                              when g.tipo = 'creditos' then 'Abatido'\n")
t = trocar(t, "                                     when 'compras_parceladas' then '[\"Parcelas ja contratadas: nao consomem limite de Categoria do Cartao.\"]'::jsonb\n",
           "                                     when 'compras_parceladas' then '[\"Parcelas ja contratadas: nao consomem limite de Categoria do Cartao.\"]'::jsonb\n"
           "                                     when 'creditos' then '[\"Estornos, IOF devolvido e ajustes da administradora: abatem o valor a pagar; a compra original continua registrada.\"]'::jsonb\n")
t = trocar(t, "        'total_fatura', v_total,\n",
           f"        -- {MARCA}: total da fatura = valor a pagar (compras executadas - creditos)\n"
           "        'total_fatura', v_total - v_creditos,\n"
           "        'total_compras', v_total,\n"
           "        'total_creditos', v_creditos,\n")
NOVO['fatura_por_categoria'] = t

t = ORIG['lancamentos_fatura_por_categoria']
t = trocar(t, "    if v_filtro not in ('todos', 'sem_categoria', 'despesas_fixas', 'compras_parceladas') then  -- FIN-CARTAO-DESPESAS-FIXAS-01\n",
           f"    if v_filtro not in ('todos', 'sem_categoria', 'despesas_fixas', 'compras_parceladas', 'creditos') then  -- FIN-CARTAO-DESPESAS-FIXAS-01, {MARCA}\n")
t = trocar(t, "                    or (nat.n = 'CATEGORIA' and l.categoria_cartao_id = v_cc))), '[]'::jsonb));\n",
           "                    or (nat.n = 'CATEGORIA' and l.categoria_cartao_id = v_cc))), '[]'::jsonb)\n"
           f"            -- {MARCA}: creditos da fatura, negativos e sem acoes de compra (identificador proprio)\n"
           "            || coalesce((\n"
           "            select jsonb_agg(jsonb_build_object(\n"
           "                       'id', 'credito-' || cf.id,\n"
           "                       'credito_id', cf.id,\n"
           "                       'data', cf.data_credito,\n"
           "                       'descricao', cf.descricao,\n"
           "                       'descricao_original', coalesce(cf.descricao_original, cf.descricao),\n"
           "                       'valor', -cf.valor,\n"
           "                       'categoria_id', null,\n"
           "                       'categoria_nome', case cf.natureza when 'ESTORNO' then 'Estorno de compra'\n"
           "                                                         when 'IOF_DEVOLVIDO' then 'Devolucao de IOF'\n"
           "                                                         else 'Credito ou ajuste da fatura' end,\n"
           "                       'categoria_cartao_id', null,\n"
           "                       'categoria_cartao_nome', null,\n"
           "                       'origem', cf.origem_importacao,\n"
           "                       'parcela_atual', null,\n"
           "                       'parcelas_total', null,\n"
           "                       'compra_id', null,\n"
           "                       'natureza', 'CREDITO',\n"
           "                       'natureza_credito', cf.natureza,\n"
           "                       'compra_original', case when o.id is not null then jsonb_build_object(\n"
           "                           'id', o.id, 'descricao', coalesce(nullif(o.descricao_exibida, ''), o.descricao), 'valor', o.valor,\n"
           "                           'data_compra', o.data_compra) end,\n"
           "                       'valor_executado', -cf.valor,\n"
           "                       'status_classificacao', 'classificado',\n"
           "                       'bloqueio', 'Credito da fatura',\n"
           "                       'pode_editar', false,\n"
           "                       'versao', null)\n"
           "                   order by cf.data_credito, cf.id)\n"
           "              from financeiro.credito_fatura cf\n"
           "              left join public.lancamento_agregado o on o.id = cf.lancamento_id\n"
           "             where v_filtro in ('todos', 'creditos')\n"
           "               and cf.fatura_id = financeiro.fatura_do_mes(p_cartao_id, v_mes)), '[]'::jsonb));\n")
NOVO['lancamentos_fatura_por_categoria'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Previa: credito da fatura classificado, com a compra original quando identificada sem duvida
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['analisar_importacao_cartao']
t = trocar(t, "    v_amb_res   text;     -- decisao do usuario na previa: PARCELADA ou AVISTA\nbegin\n",
           "    v_amb_res   text;     -- decisao do usuario na previa: PARCELADA ou AVISTA\n"
           f"    v_cred      jsonb;            -- {MARCA}: credito da fatura (natureza, compra original, candidatas)\n"
           "    v_cred_nat  text;\n"
           "    v_alvo      text;             -- texto da compra no credito (\"IOF de volta de Cloudflare\" -> cloudflare)\n"
           "    v_cred_cands jsonb;\n"
           "    v_cred_esc  integer;\n"
           "    v_cred_compra integer;\n"
           "    v_cred_usados integer[] := '{}';  -- compras ja vinculadas a um credito deste arquivo\n"
           "begin\n")
t = trocar(t, "        v_amb := null;\n        v_amb_res := null;\n",
           "        v_amb := null;\n        v_amb_res := null;\n        v_cred := null;\n        v_cred_compra := null;\n"
           "        v_cred_cands := '[]'::jsonb;\n")
t = trocar(t, "        -- Credito na fatura nao e despesa negativa: pagamento da fatura, estorno de compra e ajuste tem efeitos\n"
              "        -- diferentes e nenhum entra como compra nem reduz a fatura por aqui (como o Flask, que nao importa credito).\n",
           "        -- Credito na fatura nao e despesa negativa: pagamento da fatura, estorno de compra e ajuste tem efeitos\n"
           f"        -- diferentes e nenhum entra como compra. {MARCA}: estorno, IOF devolvido e ajuste abatem o valor a pagar\n"
           "        -- da fatura (credito_fatura); o pagamento recebido nao (e registrado em Despesas, pagar fatura).\n")
t = trocar(t, "            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(estorno|estornad|devolu|reembolso|cancelamento|chargeback)' then 'estorno'\n",
           "            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(\\miof\\M.*(de volta|devolv|estorn|reembols)|(estorno|devolu[a-z]*|reembolso) d[eo] iof)' then 'iof_devolvido'\n"
           "            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(estorno|estornad|devolu|reembolso|cancelamento|chargeback)' then 'estorno'\n")
t = trocar(t, "        if v_tipo = 'credito' then\n"
              "            v_status := 'ignorado';\n"
              "            v_ignorar := true;\n"
              "            v_msgs := v_msgs || case v_credito\n"
              "                when 'pagamento_fatura' then '\"Pagamento da fatura: nao e compra nem desconto; o pagamento e registrado em Despesas (pagar fatura).\"'::jsonb\n"
              "                when 'estorno' then '\"Estorno de compra: nao importado; a compra original continua na fatura. Se ela deve sair, corrija pela propria compra.\"'::jsonb\n"
              "                else '\"Credito ou ajuste da administradora: nao importado como despesa.\"'::jsonb end;\n",
           "        if v_tipo = 'credito' and v_credito = 'pagamento_fatura' then\n"
           "            v_status := 'ignorado';\n"
           "            v_ignorar := true;\n"
           "            v_msgs := v_msgs || '\"Pagamento da fatura: nao e compra nem credito desta fatura; o pagamento e registrado em Despesas (pagar fatura).\"'::jsonb;\n"
           f"        -- {MARCA}: estorno, IOF devolvido e ajuste: credito da fatura (sem Categoria de Despesa), conferido abaixo\n"
           "        elsif v_tipo = 'credito' and v_valor is not null and v_valor > 0 then\n"
           "            if v_data is null then\n"
           "                v_status := 'revisar';\n"
           "                v_rev_nat := true;\n"
           "                v_msgs := v_msgs || '\"Data do credito ausente.\"'::jsonb;\n"
           "            end if;\n"
           "            if v_norm = '' then\n"
           "                v_status := 'revisar';\n"
           "                v_rev_nat := true;\n"
           "                v_msgs := v_msgs || '\"Descricao ausente.\"'::jsonb;\n"
           "            end if;\n")

CREDITO = f"""        -- {MARCA}: credito da fatura (estorno de compra, IOF devolvido ou ajuste da administradora). Nao e compra
        -- negativa nem receita: abate uma vez o valor a pagar da fatura; a compra original continua (vinculada quando
        -- identificada sem duvida pelo texto do credito, com valor estornavel suficiente; mais de uma candidata pede a
        -- escolha do usuario, credito_compra_id, ou 0 = sem compra vinculada). Duplicidade pela chave do credito.
        if v_tipo = 'credito' and v_status <> 'ignorado' and v_data is not null and v_norm <> '' and v_valor is not null then
            v_chave := concat_ws('|', p_cartao_id, v_comp, v_data, v_valor, lower(v_norm), 'credito');
            v_cred_nat := case v_credito when 'iof_devolvido' then 'IOF_DEVOLVIDO' when 'estorno' then 'ESTORNO' else 'AJUSTE' end;
            if v_chave = any(v_chaves) and not coalesce((v_l ->> 'manter_duplicada')::boolean, false) then
                v_dup := 'lote';
            elsif exists (select 1 from financeiro.credito_fatura cf
                           where cf.cartao_id = p_cartao_id and coalesce(cf.mes_fatura_original, cf.mes_fatura) = v_comp
                             and cf.chave = v_chave and financeiro.pertence_ao_perfil(cf.perfil_financeiro_id, p_perfil_id)) then
                v_dup := 'banco';
            end if;
            if v_dup is not null then
                v_status := 'duplicado';
                v_ignorar := true;
                v_msgs := v_msgs || '"Credito ja registrado nesta fatura (ou repetido no arquivo): nao e abatido de novo."'::jsonb;
                -- a natureza, para a tela manter o repetido legitimo como credito (manter_duplicada)
                v_cred := jsonb_build_object('natureza', v_cred_nat, 'rotulo', case v_cred_nat when 'ESTORNO' then 'Estorno de compra' when 'IOF_DEVOLVIDO' then 'Devolucao de IOF'
                                              else 'Credito ou ajuste da fatura' end,
                    'compra', null, 'candidatas', '[]'::jsonb, 'fatura_destino', to_char(v_comp, 'MM/YYYY'));
            else
                v_chaves := v_chaves || v_chave;
                v_alvo := case v_cred_nat
                    when 'IOF_DEVOLVIDO' then btrim(regexp_replace(financeiro.texto_cobranca(v_l ->> 'descricao_original'),
                                                  '^.*\\miof\\M( de volta| devolvido| estornado| devolucao)?( de| do| da)?', ''))
                    when 'ESTORNO' then financeiro.texto_cobranca(coalesce(substring(v_l ->> 'descricao_original' from '"([^"]+)"'),
                        regexp_replace(v_l ->> 'descricao_original',
                                       '^\\s*(estorno|estornado|devolucao|devolução|reembolso|cancelamento|chargeback)\\s+(de|do|da)?\\s*', '', 'i')))
                    end;
                select coalesce(jsonb_agg(jsonb_build_object('id', l.id, 'descricao', coalesce(nullif(l.descricao_exibida, ''), l.descricao),
                                                             'valor', l.valor, 'data_compra', l.data_compra,
                                                             'fatura', to_char(coalesce(l.mes_fatura_original, l.mes_fatura), 'MM/YYYY'),
                                                             'estornavel', l.valor - coalesce(cr.total, 0))
                                          order by l.data_compra desc, l.id), '[]'::jsonb)
                  into v_cred_cands
                  from public.lancamento_agregado l
                  left join lateral (select sum(cf.valor) as total from financeiro.credito_fatura cf
                                      where cf.lancamento_id = l.id) cr on true
                 where v_cred_nat in ('IOF_DEVOLVIDO', 'ESTORNO') and coalesce(v_alvo, '') <> ''
                   and l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
                   and coalesce(l.mes_fatura_original, l.mes_fatura) between (v_comp - interval '3 months')::date and v_comp
                   -- previsao de recorrencia ainda sem cobranca nao e compra a estornar
                   and (not coalesce(l.is_recorrente, false) or coalesce(l.is_importado, false)
                        or exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                    where o.lancamento_id = l.id and o.revertida_em is null))
                   and l.valor - coalesce(cr.total, 0) >= v_valor
                   and not l.id = any(v_cred_usados)
                   and position(' ' || v_alvo || ' ' in ' ' || financeiro.texto_cobranca(coalesce(l.descricao_original, l.descricao)) || ' ') > 0
                   and case v_cred_nat
                       when 'IOF_DEVOLVIDO' then l.valor = v_valor
                            and position(' iof ' in ' ' || financeiro.texto_cobranca(coalesce(l.descricao_original, l.descricao)) || ' ') > 0
                       else position(' iof ' in ' ' || financeiro.texto_cobranca(coalesce(l.descricao_original, l.descricao)) || ' ') = 0 end;
                if v_l ? 'credito_compra_id' then
                    begin
                        v_cred_esc := coalesce(nullif(v_l ->> 'credito_compra_id', '')::integer, 0);
                    exception when others then
                        v_cred_esc := -1;
                    end;
                    if v_cred_esc > 0 and exists (select 1 from jsonb_array_elements(v_cred_cands) c where (c ->> 'id')::integer = v_cred_esc) then
                        v_cred_compra := v_cred_esc;
                    elsif v_cred_esc <> 0 then
                        v_status := 'revisar';
                        v_rev_nat := true;
                        v_msgs := v_msgs || '"Compra escolhida nao e candidata a este credito (outro cartao, valor estornavel menor ou ja vinculada): escolha outra ou registre sem compra vinculada."'::jsonb;
                    end if;
                elsif jsonb_array_length(v_cred_cands) = 1 then
                    v_cred_compra := (v_cred_cands -> 0 ->> 'id')::integer;
                elsif jsonb_array_length(v_cred_cands) > 1 then
                    v_status := 'revisar';
                    v_rev_nat := true;
                    v_msgs := v_msgs || to_jsonb(format('%s compras podem ser a original deste credito: escolha a compra ou registre sem compra vinculada.',
                        jsonb_array_length(v_cred_cands)));
                end if;
                if v_cred_compra is not null then
                    v_cred_usados := v_cred_usados || v_cred_compra;
                end if;
                v_cred := jsonb_build_object(
                    'natureza', v_cred_nat,
                    'rotulo', case v_cred_nat when 'ESTORNO' then 'Estorno de compra' when 'IOF_DEVOLVIDO' then 'Devolucao de IOF'
                                              else 'Credito ou ajuste da fatura' end,
                    'compra', (select c from jsonb_array_elements(v_cred_cands) c where (c ->> 'id')::integer = v_cred_compra),
                    'candidatas', v_cred_cands,
                    'parcial', (select v_valor < (c ->> 'estornavel')::numeric from jsonb_array_elements(v_cred_cands) c
                                 where (c ->> 'id')::integer = v_cred_compra),
                    'escolhida', v_l ? 'credito_compra_id',
                    'fatura_destino', to_char(v_comp, 'MM/YYYY'));
                if v_status <> 'revisar' then
                    v_msgs := v_msgs || to_jsonb(format('%s: abate R$ %s do valor a pagar da fatura %s (nao e compra nem receita)%s.',
                        v_cred ->> 'rotulo', to_char(v_valor, 'FM999999990.00'), to_char(v_comp, 'MM/YYYY'),
                        case when v_cred_compra is not null
                             then format('; compra original preservada: %s (R$ %s)', v_cred -> 'compra' ->> 'descricao',
                                         to_char((v_cred -> 'compra' ->> 'valor')::numeric, 'FM999999990.00'))
                             else '; sem compra vinculada' end));
                end if;
            end if;
        end if;

"""
t = trocar(t, "        -- Duplicidade (chave de negocio do Flask) no lote e no banco; depois, conciliacao com compra ja lancada.\n"
              "        v_chave := null;\n"
              "        if v_status <> 'ignorado' and v_data is not null and v_norm <> '' and v_valor is not null then\n",
           "        -- Duplicidade (chave de negocio do Flask) no lote e no banco; depois, conciliacao com compra ja lancada.\n"
           "        v_chave := null;\n" + CREDITO +
           "        if v_status <> 'ignorado' and v_tipo <> 'credito' and v_data is not null and v_norm <> '' and v_valor is not null then\n")
t = trocar(t, "            when v_ignorar or v_status = 'ignorado' then 'ignorada'\n",
           "            when v_ignorar or v_status = 'ignorado' then 'ignorada'\n"
           f"            -- {MARCA}: credito nao tem Categoria de Despesa\n"
           "            when v_tipo = 'credito' then case when v_status = 'revisar' then 'revisar' else 'classificada' end\n")
t = trocar(t, "            when v_tipo = 'credito' or v_status = 'ignorado' then 'IGNORADA'\n",
           "            when v_status = 'ignorado' then 'IGNORADA'\n")
t = trocar(t, "            when v_status = 'revisar' and v_rev_nat then 'REVISAR'\n            when v_total > 1 then 'PARCELADA'\n",
           "            when v_status = 'revisar' and v_rev_nat then 'REVISAR'\n"
           f"            when v_tipo = 'credito' then 'CREDITO'  -- {MARCA}\n"
           "            when v_total > 1 then 'PARCELADA'\n")
t = trocar(t, "            'categoria_pendente', v_tipo <> 'credito' and v_cat is null));\n",
           "            'categoria_pendente', v_tipo <> 'credito' and v_cat is null,\n"
           f"            'credito', v_cred));  -- {MARCA}\n")
t = trocar(t, "            'total_creditos', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'credito'), 0),\n",
           "            'total_creditos', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'credito'), 0),\n"
           f"            -- {MARCA}: creditos que a confirmacao abate da fatura\n"
           "            'creditos_a_abater', count(*) filter (where l ->> 'classificacao_importacao' = 'CREDITO' and not (l ->> 'ignorar')::boolean),\n"
           "            'total_creditos_a_abater', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'classificacao_importacao' = 'CREDITO'\n"
           "                                                                                      and not (l ->> 'ignorar')::boolean), 0),\n")
NOVO['analisar_importacao_cartao'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Confirmacao: os creditos gravados na mesma transacao, na fatura aberta (paga nao recebe; consolidada recusa)
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['importar_fatura_cartao']
t = trocar(t, "    v_r          jsonb;\nbegin\n",
           "    v_r          jsonb;\n"
           f"    v_creditos   jsonb := '[]'::jsonb;  -- {MARCA}\n"
           "    v_cred_ids   bigint[] := '{}';\n"
           "    v_cid        bigint;\n"
           "    v_total_cred numeric := 0;\n"
           "begin\n")
t = trocar(t, "        continue when (v_l ->> 'ignorar')::boolean;\n",
           "        continue when (v_l ->> 'ignorar')::boolean;\n"
           f"        -- {MARCA}: credito da fatura (sem Categoria de Despesa): gravado a parte, abate o valor a pagar\n"
           "        if v_l ->> 'tipo_movimento' = 'credito' then\n"
           "            if v_l ->> 'status' <> 'valido' then\n"
           "                v_pendentes := v_pendentes || format('linha %s (%s): %s', v_l ->> 'linha_origem',\n"
           "                    coalesce(v_l ->> 'descricao_exibida', '-'), coalesce(v_l -> 'mensagens' ->> -1, v_l ->> 'status'));\n"
           "            else\n"
           "                v_creditos := v_creditos || v_l;\n"
           "            end if;\n"
           "            continue;\n"
           "        end if;\n")
t = trocar(t, "    if jsonb_array_length(v_a_gravar) = 0 and jsonb_array_length(v_conciliar) = 0 then\n",
           "    if jsonb_array_length(v_a_gravar) = 0 and jsonb_array_length(v_conciliar) = 0 and jsonb_array_length(v_creditos) = 0 then\n")
t = trocar(t, "    -- FIN-CARTAO-IMPORTACAO-FIXAS-01: conciliacoes pedidas na previa (previsao + cobranca ja lancada), sob as mesmas travas\n",
           f"    -- {MARCA}: creditos da fatura. Fatura paga nao recebe credito (vai para a proxima aberta, como as compras);\n"
           "    -- consolidada recusa a importacao inteira.\n"
           "    for v_l in select e from jsonb_array_elements(v_creditos) e loop\n"
           "        v_alvo := v_comp;\n"
           "        v_passos := 0;\n"
           "        loop\n"
           "            v_fat := financeiro.fatura_do_mes(p_cartao_id, v_alvo);\n"
           "            exit when v_fat is null or not financeiro.fatura_esta_paga(v_fat);\n"
           "            v_alvo := (v_alvo + interval '1 month')::date;\n"
           "            v_passos := v_passos + 1;\n"
           "            if v_passos > 24 then\n"
           "                raise exception 'Nao ha fatura aberta nos proximos 24 meses' using errcode = '22023';\n"
           "            end if;\n"
           "        end loop;\n"
           "        v_fat := financeiro.garantir_fatura(p_perfil_id, p_cartao_id, v_alvo);\n"
           "        perform 1 from public.conta where id = v_fat for update;\n"
           "        if financeiro.fatura_esta_paga(v_fat) then\n"
           "            raise exception 'A fatura de % foi paga durante a importacao. Revise e tente de novo.',\n"
           "                to_char(v_alvo, 'MM/YYYY') using errcode = 'P0001';\n"
           "        end if;\n"
           "        if exists (select 1 from public.conta c where c.id = v_fat and c.status_fatura = 'FECHADA') then\n"
           "            raise exception 'Importacao nao realizada: a fatura de % esta consolidada e o credito \"%\" cairia nela. Retire a linha ou importe em outra competencia.',\n"
           "                to_char(v_alvo, 'MM/YYYY'), v_l ->> 'descricao_exibida' using errcode = 'P0001', hint = 'CONSOLIDADA';\n"
           "        end if;\n"
           "        insert into financeiro.credito_fatura (perfil_financeiro_id, cartao_id, fatura_id, mes_fatura, mes_fatura_original,\n"
           "                                               natureza, descricao, descricao_original, data_credito, valor, lancamento_id,\n"
           "                                               chave, origem_importacao, operacao_chave, user_id)\n"
           "        values (coalesce((select c.perfil_financeiro_id from public.conta c where c.id = v_fat), p_perfil_id), p_cartao_id,\n"
           "                v_fat, v_alvo, nullif(v_comp, v_alvo), v_l -> 'credito' ->> 'natureza',\n"
           "                left(coalesce(nullif(v_l ->> 'descricao_exibida', ''), v_l ->> 'descricao_normalizada'), 200),\n"
           "                v_l ->> 'descricao_original', (v_l ->> 'data_compra')::date, (v_l ->> 'valor')::numeric,\n"
           "                (v_l -> 'credito' -> 'compra' ->> 'id')::integer, v_l ->> 'hash_deduplicacao',\n"
           "                left(coalesce(v_l ->> 'origem_importacao', 'csv'), 20), p_chave, (select auth.uid()))\n"
           "        returning id into v_cid;\n"
           "        v_cred_ids := v_cred_ids || v_cid;\n"
           "        v_total_cred := v_total_cred + (v_l ->> 'valor')::numeric;\n"
           "        if not v_alvo = any(v_meses) then\n"
           "            v_meses := v_meses || v_alvo;\n"
           "        end if;\n"
           "    end loop;\n"
           "    -- FIN-CARTAO-IMPORTACAO-FIXAS-01: conciliacoes pedidas na previa (previsao + cobranca ja lancada), sob as mesmas travas\n")
t = trocar(t, "        'conciliadas', v_conciliadas, 'apelidos', v_apelidos,\n",
           "        'conciliadas', v_conciliadas, 'apelidos', v_apelidos,\n"
           "        'creditos', cardinality(v_cred_ids), 'total_creditos', v_total_cred, 'creditos_ids', to_jsonb(v_cred_ids),\n")
NOVO['importar_fatura_cartao'] = t

NOVOS = f"""
-- =====================================================================================================================
-- 1. Creditos da fatura (estorno de compra, IOF devolvido, ajuste da administradora)
-- =====================================================================================================================
create table financeiro.credito_fatura (
    id                   bigint      generated always as identity primary key,
    perfil_financeiro_id integer     not null,
    cartao_id            integer     not null references public.item_despesa (id),
    fatura_id            integer     not null references public.conta (id),
    mes_fatura           date        not null,
    mes_fatura_original  date,
    natureza             text        not null check (natureza in ('ESTORNO', 'IOF_DEVOLVIDO', 'AJUSTE')),
    descricao            text        not null,
    descricao_original   text,
    data_credito         date        not null,
    valor                numeric(12, 2) not null check (valor > 0),
    lancamento_id        integer     references public.lancamento_agregado (id),
    chave                text        not null,
    origem_importacao    varchar(20) not null default 'csv',
    operacao_chave       uuid,
    user_id              uuid        references auth.users (id) on delete set null,
    criado_em            timestamptz not null default now()
);
create index credito_fatura_fatura on financeiro.credito_fatura (fatura_id);
create index credito_fatura_cartao_mes on financeiro.credito_fatura (cartao_id, mes_fatura);
create index credito_fatura_compra on financeiro.credito_fatura (lancamento_id) where lancamento_id is not null;
comment on table financeiro.credito_fatura is
    '{MARCA}: credito da fatura do cartao (estorno de compra, IOF devolvido, ajuste). Nao e compra nem receita: abate o valor a pagar da fatura uma vez; a compra original continua (lancamento_id).';
alter table financeiro.credito_fatura enable row level security;
alter table financeiro.credito_fatura force row level security;
revoke all on financeiro.credito_fatura from public, anon, authenticated;

-- Creditos da fatura (soma), para o valor a pagar.
create function financeiro.creditos_fatura(p_fatura_id integer)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce(sum(cf.valor), 0) from financeiro.credito_fatura cf where cf.fatura_id = p_fatura_id
$$;
revoke execute on function financeiro.creditos_fatura(integer) from public, anon, authenticated;
"""

CABECALHO = f"""-- {MARCA} — creditos da fatura do cartao na importacao (estorno de compra, IOF devolvido, ajuste).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes {VERSAO}). Depende de 20261211090000.
-- Validada em cluster local descartavel (tests/test_supabase_cartao_nubank_creditos.py) e ensaiada numa copia fiel da
-- producao. Doc: docs/FIN_CARTAO_NUBANK_CREDITOS_01.md. Gerada por scripts/gerar_migration_cartao_nubank_creditos.py.
-- Reversao: supabase/reversao/{VERSAO}_cartao_nubank_creditos_anterior.sql (recusada com credito registrado).
--
-- Credito nao e compra negativa nem receita bancaria: fica em financeiro.credito_fatura, na fatura aberta, e abate o valor
-- a pagar uma vez (executado da fatura = compras executadas - creditos). A compra original continua, vinculada quando o
-- texto do credito a identifica sem duvida, e fica bloqueada para edicao e exclusao. Pagamento recebido nao e credito da
-- fatura (continua ignorado: o pagamento e registrado em Despesas). Nenhum movimento ou saldo bancario e criado.
-- Na previa: classificacao CREDITO (ou REVISAR com as compras candidatas; JA_EXISTENTE na reimportacao), natureza,
-- compra original, tratamento proposto. Na confirmacao: tudo numa transacao, sob as travas da importacao.
-- Nenhum dado existente e alterado pela migration.
--
-- Funcoes existentes substituidas pelo texto vigente com os trechos marcados "{MARCA}": {', '.join(FONTES)}.
"""

ORDEM = list(FONTES)
partes = [CABECALHO, NOVOS,
          "\n-- =====================================================================================================================\n"
          "-- 2. Valor a pagar, Cartoes, previa e confirmacao da importacao: texto vigente + os trechos marcados\n"
          "-- =====================================================================================================================\n"]
for n in ORDEM:
    partes.append(f"\n-- {n}: texto de {FONTES[n][:14]} + os trechos marcados.\n{como_replace(NOVO[n])}\n")
destino = MIG / f'{VERSAO}_financeiro_cartao_nubank_creditos.sql'

REV = [f"""-- Reversao de {VERSAO} ({MARCA}): volta as funcoes ao texto anterior e remove a tabela de creditos.
-- Recusada se houver credito registrado (o valor a pagar das faturas mudaria). So com autorizacao, retirando a versao de
-- supabase_migrations.schema_migrations.
do $$
begin
    if exists (select 1 from financeiro.credito_fatura) then
        raise exception 'Ha creditos de fatura registrados: a reversao mudaria o valor a pagar das faturas';
    end if;
end
$$;
"""]
for n in ORDEM:
    REV.append(f"\n-- {n}: texto de {FONTES[n][:14]}.\n{como_replace(ORIG[n])}\n")
REV.append("""
drop function financeiro.creditos_fatura(integer);
drop table financeiro.credito_fatura;
""")

SAIDAS = {destino: ''.join(partes),
          RAIZ / 'supabase' / 'reversao' / f'{VERSAO}_cartao_nubank_creditos_anterior.sql': ''.join(REV)}
if ARGS.verificar:
    # Bytes exatos (UTF-8), sem CR: o checkout no Windows pode trocar LF por CRLF (core.autocrlf).
    diferentes = [str(p.relative_to(RAIZ)) for p, texto in SAIDAS.items()
                  if not p.exists() or p.read_bytes().replace(b'\r\n', b'\n') != texto.encode('utf-8')]
    print('diferente: ' + ', '.join(diferentes) if diferentes else 'igual')
    sys.exit(1 if diferentes else 0)
for caminho, texto in SAIDAS.items():
    caminho.write_text(texto, encoding='utf-8', newline='\n')
print('ok', destino.stat().st_size)
