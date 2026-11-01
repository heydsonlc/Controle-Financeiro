"""Gera a migration 20261208090000 (FIN-CARTAO-DESPESAS-FIXAS-01) e a reversao a partir do texto VIGENTE de cada funcao,
com substituicoes conferidas (cada trecho deve ocorrer exatamente uma vez).

As oito funcoes substituidas sao longas: a migration nao e editada a mao. Para muda-la, edite este gerador e rode-o;
as fontes sao as migrations anteriores (ja aplicadas, imutaveis). So texto SQL: nenhum dado, conexao ou credencial.

    python scripts/gerar_migration_cartao_despesas_fixas.py              # grava a migration e a reversao
    python scripts/gerar_migration_cartao_despesas_fixas.py --verificar  # so compara com os arquivos versionados

O teste tests/test_gerador_migration_cartao_despesas_fixas.py confere que os arquivos versionados sao a saida exata.
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
MARCA = 'FIN-CARTAO-DESPESAS-FIXAS-01'
NAT = "financeiro.natureza_da_compra({p}.total_parcelas, {p}.is_recorrente, {p}.item_despesa_id, {p}.categoria_cartao_id)"


def bloco(arquivo, nome):
    texto = (MIG / arquivo).read_text(encoding='utf-8')
    m = list(re.finditer(r'create (?:or replace )?function financeiro\.' + nome + r'\(', texto))
    assert m, nome
    ini = m[-1].start()
    fim = texto.index('\n$$;', ini) + len('\n$$;')
    return texto[ini:fim]


def trocar(texto, antigo, novo, nome):
    n = texto.count(antigo)
    assert n == 1, f'{nome}: trecho encontrado {n} vezes: {antigo[:80]!r}'
    return texto.replace(antigo, novo)


def como_replace(b):
    return re.sub(r'^create function', 'create or replace function', b)


FONTES = {
    'gasto_categoria_fatura': '20261104090000_financeiro_cartoes_tela.sql',
    'fatura_por_categoria': '20261104090000_financeiro_cartoes_tela.sql',
    'lancamentos_fatura_por_categoria': '20261104090000_financeiro_cartoes_tela.sql',
    'contas_do_mes': '20261022090000_financeiro_contas_do_mes.sql',
    'faturas_do_mes': '20261028090000_financeiro_cartoes.sql',
    'dashboard_resumo_tela': '20261114090000_financeiro_dashboard_leitura.sql',
    'compras_da_fatura': '20261207090000_financeiro_compras_fatura_categoria_cartao.sql',
    'analisar_importacao_cartao': '20261107090000_financeiro_importacao_recorrencia.sql',
    'importar_fatura_cartao': '20261124090000_financeiro_escritor_unico_final.sql',
}
ORIG = {n: bloco(a, n) for n, a in FONTES.items()}
NOVO = {}

# ---------------------------------------------------------------------------------------------------------------------
# Leituras por Categoria do Cartao: so a natureza CATEGORIA consome limite e gasto da categoria
# ---------------------------------------------------------------------------------------------------------------------
t = como_replace(ORIG['gasto_categoria_fatura'])
t = trocar(t, "       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)\n$$;",
           "       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)\n"
           f"       and {NAT.format(p='l')} = 'CATEGORIA'  -- {MARCA}\n$$;", 'gasto')
NOVO['gasto_categoria_fatura'] = t

t = como_replace(ORIG['contas_do_mes'])
t = trocar(t, "        select l.cartao_id, l.categoria_cartao_id, sum(l.valor) as total\n",
           "        select l.cartao_id, l.categoria_cartao_id, sum(l.valor) as total,\n"
           f"               -- {MARCA}: parceladas e fixas nao consomem o limite da Categoria do Cartao\n"
           f"               sum(l.valor) filter (where {NAT.format(p='l')} = 'CATEGORIA') as total_categoria\n", 'contas')
t = trocar(t, "greatest(lim.limite_mensal - coalesce(g.total, 0), 0)", "greatest(lim.limite_mensal - coalesce(g.total_categoria, 0), 0)", 'contas')
NOVO['contas_do_mes'] = t

t = como_replace(ORIG['faturas_do_mes'])
t = trocar(t, "        select l.cartao_id, l.categoria_cartao_id, sum(l.valor) as gasto, count(*) as qtd\n",
           "        select l.cartao_id, l.categoria_cartao_id, sum(l.valor) as gasto, count(*) as qtd,\n"
           f"               -- {MARCA}: parceladas e fixas nao consomem o limite da Categoria do Cartao\n"
           f"               sum(l.valor) filter (where {NAT.format(p='l')} = 'CATEGORIA') as gasto_categoria\n", 'faturas')
t = trocar(t, "greatest(lim.limite_mensal - coalesce(g.gasto, 0), 0)", "greatest(lim.limite_mensal - coalesce(g.gasto_categoria, 0), 0)", 'faturas')
NOVO['faturas_do_mes'] = t

t = como_replace(ORIG['fatura_por_categoria'])
t = trocar(t, "        select l.valor, l.categoria_cartao_id from public.lancamento_agregado l\n",
           f"        select l.valor, l.categoria_cartao_id, {NAT.format(p='l')} as natureza  -- {MARCA}\n"
           "          from public.lancamento_agregado l\n", 'fpc')
t = trocar(t, "(select sum(x.valor) from lanc x where x.categoria_cartao_id = lim.categoria_cartao_id)",
           "(select sum(x.valor) from lanc x where x.natureza = 'CATEGORIA' and x.categoria_cartao_id = lim.categoria_cartao_id)", 'fpc')
t = trocar(t, "(select count(*) from lanc x where x.categoria_cartao_id = lim.categoria_cartao_id)",
           "(select count(*) from lanc x where x.natureza = 'CATEGORIA' and x.categoria_cartao_id = lim.categoria_cartao_id)", 'fpc')
t = trocar(t, "         where x.categoria_cartao_id is not null\n",
           "         where x.categoria_cartao_id is not null and x.natureza = 'CATEGORIA'\n", 'fpc')
t = trocar(t, "        -- 3. sem Categoria do Cartao\n        select 3, 0, null, null, sum(x.valor), count(*), 'sem_categoria'\n"
              "          from lanc x where x.categoria_cartao_id is null having count(*) > 0\n",
           f"        -- 3 e 4. {MARCA}: obrigacoes ja contratadas, fora das Categorias do Cartao (nao consomem limite)\n"
           "        select 3, 0, null, null, sum(x.valor), count(*), 'compras_parceladas'\n"
           "          from lanc x where x.natureza = 'PARCELADA' having count(*) > 0\n"
           "        union all\n"
           "        select 4, 0, null, null, sum(x.valor), count(*), 'despesas_fixas'\n"
           "          from lanc x where x.natureza = 'FIXA' having count(*) > 0\n"
           "        union all\n"
           "        -- 5. sem Categoria do Cartao (o que nao e parcelada nem fixa)\n"
           "        select 5, 0, null, null, sum(x.valor), count(*), 'sem_categoria'\n"
           "          from lanc x where x.natureza = 'OUTROS' having count(*) > 0\n", 'fpc')
t = trocar(t, "               'categoria_cartao_id', g.categoria_cartao_id,\n"
              "               'categoria_cartao_nome', case when g.tipo = 'sem_categoria' then 'Sem Categoria do Cartao'\n"
              "                                             else coalesce(cc.nome, 'Categoria do Cartao') end,\n",
           "               -- os grupos de parceladas e fixas levam o proprio filtro de \"Ver lancamentos\" (tela de Cartoes)\n"
           "               'categoria_cartao_id', case when g.tipo in ('compras_parceladas', 'despesas_fixas') then to_jsonb(g.tipo)\n"
           "                                           else to_jsonb(g.categoria_cartao_id) end,\n"
           "               'categoria_cartao_nome', case g.tipo when 'sem_categoria' then 'Sem Categoria do Cartao'\n"
           "                                                    when 'compras_parceladas' then 'Compras parceladas'\n"
           "                                                    when 'despesas_fixas' then 'Despesas fixas'\n"
           "                                                    else coalesce(cc.nome, 'Categoria do Cartao') end,\n"
           "               'natureza', case g.tipo when 'compras_parceladas' then 'PARCELADA' when 'despesas_fixas' then 'FIXA'\n"
           "                                       when 'sem_categoria' then 'OUTROS' else 'CATEGORIA' end,\n", 'fpc')
t = trocar(t, "               'status', case when g.tipo = 'categoria_cartao' then financeiro.status_consumo(g.gasto, g.limite_mensal)\n"
              "                              else 'Revisar' end,\n",
           "               'status', case when g.tipo = 'categoria_cartao' then financeiro.status_consumo(g.gasto, g.limite_mensal)\n"
           "                              when g.tipo in ('compras_parceladas', 'despesas_fixas') then 'Contratada'\n"
           "                              else 'Revisar' end,\n", 'fpc')
t = trocar(t, "                                     when 'categoria_sem_limite' then '[\"Categoria sem limite neste cartao.\"]'::jsonb\n",
           "                                     when 'categoria_sem_limite' then '[\"Categoria sem limite neste cartao.\"]'::jsonb\n"
           "                                     when 'compras_parceladas' then '[\"Parcelas ja contratadas: nao consomem limite de Categoria do Cartao.\"]'::jsonb\n"
           "                                     when 'despesas_fixas' then '[\"Recorrencias do cartao: nao consomem limite de Categoria do Cartao.\"]'::jsonb\n", 'fpc')
t = trocar(t, "    select coalesce(sum(l.valor), 0),\n"
              "           coalesce(sum(l.valor) filter (where l.categoria_cartao_id is not null), 0),\n"
              "           coalesce(sum(l.valor) filter (where l.categoria_cartao_id is null), 0),\n"
              "           coalesce(sum(l.valor) filter (where l.categoria_cartao_id in (\n",
           "    select coalesce(sum(l.valor), 0),\n"
           "           coalesce(sum(l.valor) filter (where nat.n = 'CATEGORIA'), 0),\n"
           "           coalesce(sum(l.valor) filter (where nat.n = 'OUTROS'), 0),\n"
           "           coalesce(sum(l.valor) filter (where nat.n = 'FIXA'), 0),\n"
           "           coalesce(sum(l.valor) filter (where nat.n = 'PARCELADA'), 0),\n"
           "           coalesce(sum(l.valor) filter (where nat.n = 'CATEGORIA' and l.categoria_cartao_id in (\n", 'fpc')
t = trocar(t, "      into v_total, v_com, v_sem, v_vinculadas\n      from public.lancamento_agregado l\n",
           "      into v_total, v_com, v_sem, v_fixas, v_parceladas, v_vinculadas\n      from public.lancamento_agregado l\n"
           f"     cross join lateral (select {NAT.format(p='l')} as n) nat  -- {MARCA}\n", 'fpc')
t = trocar(t, "    v_vinculadas numeric;\n", "    v_vinculadas numeric;\n    v_fixas      numeric;  -- " + MARCA + "\n    v_parceladas numeric;\n", 'fpc')
t = trocar(t, "        'total_sem_categoria_cartao', v_sem,\n",
           "        'total_sem_categoria_cartao', v_sem,\n        'total_despesas_fixas', v_fixas,\n"
           "        'total_compras_parceladas', v_parceladas,\n", 'fpc')
NOVO['fatura_por_categoria'] = t

t = como_replace(ORIG['lancamentos_fatura_por_categoria'])
t = trocar(t, "    if v_filtro not in ('todos', 'sem_categoria') then\n",
           f"    if v_filtro not in ('todos', 'sem_categoria', 'despesas_fixas', 'compras_parceladas') then  -- {MARCA}\n", 'lfc')
t = trocar(t, "                       'compra_id', l.compra_id,\n",
           "                       'compra_id', l.compra_id,\n                       'natureza', nat.n,\n", 'lfc')
t = trocar(t, "                       'status_classificacao', case\n",
           "                       'status_classificacao', case\n"
           "                           when nat.n in ('PARCELADA', 'FIXA') then 'classificado'  -- nao precisam de Categoria do Cartao\n", 'lfc')
t = trocar(t, "              left join public.categoria_cartao cc on cc.id = l.categoria_cartao_id\n",
           "              left join public.categoria_cartao cc on cc.id = l.categoria_cartao_id\n"
           f"             cross join lateral (select {NAT.format(p='l')} as n) nat\n", 'lfc')
t = trocar(t, "               and (v_filtro = 'todos' or (v_filtro = 'sem_categoria' and l.categoria_cartao_id is null)\n"
              "                    or l.categoria_cartao_id = v_cc)), '[]'::jsonb));\n",
           "               and (v_filtro = 'todos' or (v_filtro = 'sem_categoria' and nat.n = 'OUTROS')\n"
           "                    or (v_filtro = 'despesas_fixas' and nat.n = 'FIXA')\n"
           "                    or (v_filtro = 'compras_parceladas' and nat.n = 'PARCELADA')\n"
           "                    or (nat.n = 'CATEGORIA' and l.categoria_cartao_id = v_cc))), '[]'::jsonb));\n", 'lfc')
NOVO['lancamentos_fatura_por_categoria'] = t

t = como_replace(ORIG['dashboard_resumo_tela'])
t = trocar(t, "          from public.lancamento_agregado la join public.categoria_cartao cc on cc.id = la.categoria_cartao_id\n"
              "         where financeiro.pertence_ao_perfil(la.perfil_financeiro_id, p_perfil_id)\n",
           "          from public.lancamento_agregado la join public.categoria_cartao cc on cc.id = la.categoria_cartao_id\n"
           "         where financeiro.pertence_ao_perfil(la.perfil_financeiro_id, p_perfil_id)\n"
           f"           and {NAT.format(p='la')} = 'CATEGORIA'  -- {MARCA}\n", 'dash')
t = trocar(t, "                   coalesce((select sum(la.valor) from public.lancamento_agregado la\n"
              "                              where la.cartao_id = i.id and financeiro.pertence_ao_perfil(la.perfil_financeiro_id, p_perfil_id)\n",
           "                   coalesce((select sum(la.valor) from public.lancamento_agregado la\n"
           "                              where la.cartao_id = i.id and financeiro.pertence_ao_perfil(la.perfil_financeiro_id, p_perfil_id)\n"
           f"                                -- {MARCA}: uso dos limites sem as obrigacoes ja contratadas\n"
           f"                                and {NAT.format(p='la')} not in ('PARCELADA', 'FIXA')\n", 'dash')
NOVO['dashboard_resumo_tela'] = t

# ---------------------------------------------------------------------------------------------------------------------
# compras_da_fatura: previsto da ocorrencia, natureza e situacao (prevista / confirmada)
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['compras_da_fatura']
t = trocar(t, "                   categoria_cartao_id integer)\n",
           "                   categoria_cartao_id integer, valor_previsto numeric, natureza text, situacao_ocorrencia text)\n", 'cdf')
t = trocar(t, "               l.categoria_cartao_id\n          from public.lancamento_agregado l\n"
              "          left join public.categoria cat on cat.id = l.categoria_id\n",
           "               l.categoria_cartao_id,\n"
           f"               -- {MARCA}: previsto da ocorrencia (o valor antes da cobranca real; sem cobranca, o proprio valor)\n"
           "               case when nat.n = 'FIXA' then coalesce(o.valor_previsto, l.valor) when nat.n = 'PARCELADA' then l.valor end,\n"
           "               nat.n,\n"
           "               case when nat.n = 'FIXA' then case when o.id is not null or coalesce(l.is_importado, false)\n"
           "                                                  then 'CONFIRMADA' else 'PREVISTA' end end\n"
           "          from public.lancamento_agregado l\n"
           "          left join public.categoria cat on cat.id = l.categoria_id\n"
           "          left join financeiro.ocorrencia_recorrencia_cartao o on o.lancamento_id = l.id and o.revertida_em is null\n"
           f"         cross join lateral (select {NAT.format(p='l')} as n) nat\n", 'cdf')
NOVO['compras_da_fatura'] = t

# ---------------------------------------------------------------------------------------------------------------------
# analisar_importacao_cartao: reconhecimento pela descricao/apelido, nunca so pelo valor; realizacao da previsao
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['analisar_importacao_cartao']
t = trocar(t, "    v_credito   text;\nbegin\n",
           "    v_credito   text;\n"
           f"    v_cands     jsonb;    -- {MARCA}: recorrencias do cartao que combinam com a descricao\n"
           "    v_desempate jsonb;\n"
           "    v_texto     text;\n"
           "    v_rec_cat   integer;\n"
           "    v_rec_nome  text;\n"
           "    v_realiza   integer;  -- compra prevista que esta linha realiza\n"
           "    v_prev      numeric;\n"
           "    v_occ       public.lancamento_agregado;\n"
           "    v_fat_occ   integer;\nbegin\n", 'ana')
t = trocar(t, "        v_norm := btrim(coalesce(nullif(v_l ->> 'descricao_normalizada', ''), v_l ->> 'descricao_original', ''));\n",
           "        v_norm := btrim(coalesce(nullif(v_l ->> 'descricao_normalizada', ''), v_l ->> 'descricao_original', ''));\n"
           "\n"
           f"        -- {MARCA}: recorrencia do cartao pela descricao. O nome da recorrencia ou um apelido de cobranca\n"
           "        -- (financeiro.recorrencia_apelido) aparece como palavras inteiras no texto normalizado da linha: mesmo\n"
           "        -- cartao, recorrencia ativa paga no cartao. O valor nunca identifica; so desempata quando ha mais de uma.\n"
           "        v_cands := '[]'::jsonb;\n"
           "        v_rec_cat := null;\n"
           "        v_rec_nome := null;\n"
           "        v_realiza := null;\n"
           "        v_prev := null;\n"
           "        v_texto := ' ' || financeiro.texto_cobranca(v_norm) || ' ';\n"
           "        if v_tipo <> 'credito' and btrim(v_texto) <> '' then\n"
           "            select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'nome', i.nome, 'categoria_id', i.categoria_id,\n"
           "                                                         'valor', i.valor,\n"
           "                                                         'exato', financeiro.texto_cobranca(i.nome) = btrim(v_texto)\n"
           "                                                                  or exists (select 1 from financeiro.recorrencia_apelido a\n"
           "                                                                              where a.item_despesa_id = i.id and a.ativo\n"
           "                                                                                and a.apelido = btrim(v_texto)))\n"
           "                                      order by i.id), '[]'::jsonb)\n"
           "              into v_cands\n"
           "              from public.item_despesa i\n"
           "             where coalesce(i.recorrente, false) and coalesce(i.ativo, true) and i.tipo <> 'Agregador'\n"
           "               and i.meio_pagamento = 'cartao' and i.cartao_id = p_cartao_id\n"
           "               and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)\n"
           "               and ((financeiro.texto_cobranca(i.nome) <> ''\n"
           "                     and position(' ' || financeiro.texto_cobranca(i.nome) || ' ' in v_texto) > 0)\n"
           "                    or exists (select 1 from financeiro.recorrencia_apelido a\n"
           "                                where a.item_despesa_id = i.id and a.ativo\n"
           "                                  and position(' ' || a.apelido || ' ' in v_texto) > 0));\n"
           "            -- Desempate: a que bate com o texto inteiro; depois, a de valor igual. Persistindo, nenhuma (revisar).\n"
           "            if jsonb_array_length(v_cands) > 1 then\n"
           "                select coalesce(jsonb_agg(c), '[]'::jsonb) into v_desempate\n"
           "                  from jsonb_array_elements(v_cands) c where (c ->> 'exato')::boolean;\n"
           "                if jsonb_array_length(v_desempate) = 1 then\n"
           "                    v_cands := v_desempate;\n"
           "                else\n"
           "                    select coalesce(jsonb_agg(c), '[]'::jsonb) into v_desempate\n"
           "                      from jsonb_array_elements(v_cands) c where (c ->> 'valor')::numeric = round(abs(v_bruto), 2);\n"
           "                    if jsonb_array_length(v_desempate) = 1 then\n"
           "                        v_cands := v_desempate;\n"
           "                    end if;\n"
           "                end if;\n"
           "            end if;\n"
           "        end if;\n"
           "        v_rec := case when jsonb_array_length(v_cands) = 1 then (v_cands -> 0 ->> 'id')::integer end;\n"
           "        v_rec_cat := (v_cands -> 0 ->> 'categoria_id')::integer;\n"
           "        v_rec_nome := v_cands -> 0 ->> 'nome';\n", 'ana')
t = trocar(t, "            else\n"
              "                v_sug := financeiro.sugestao_categoria_importacao(",
           f"            -- {MARCA}: linha reconhecida como a recorrencia usa a Categoria de Despesa dela\n"
           "            elsif v_rec is not null and exists (select 1 from public.categoria c where c.id = v_rec_cat and coalesce(c.ativo, true)) then\n"
           "                v_cat := v_rec_cat;\n"
           "                v_cat_origem := 'recorrencia';\n"
           "            else\n"
           "                v_sug := financeiro.sugestao_categoria_importacao(", 'ana')
t = trocar(t, "                   and (abs(l.data_compra - v_data) <= 5 or coalesce(l.is_recorrente, false))\n",
           "                   and abs(l.data_compra - v_data) <= 5\n"
           f"                   -- {MARCA}: compra de recorrencia (prevista ou realizada) nunca e conciliada so pelo valor\n"
           "                   -- (ChatGPT de R$ 109,90 nao e o Claude); ela e encontrada pela descricao, abaixo.\n"
           "                   and not (coalesce(l.is_recorrente, false) and l.item_despesa_id is not null)\n", 'ana')
antigo_rec = t[t.index("        -- Compra recorrente do cartao (reconhecer_despesa_fixa do Flask"):t.index("        -- Categoria do Cartao (resolver_categoria_cartao_para_lancamento)")]
t = trocar(t, antigo_rec,
           f"        -- {MARCA}: ocorrencia da recorrencia reconhecida pela descricao (acima). Com a previsao do mes ainda sem\n"
           "        -- cobranca, a linha a realiza: a compra prevista fica (identidade da recorrencia) com o valor real, e o\n"
           "        -- previsto vai para financeiro.ocorrencia_recorrencia_cartao. Previsao ja realizada, ou em fatura paga ou\n"
           "        -- consolidada: a linha sai da efetivacao, a compra existente fica como esta.\n"
           "        if v_status in ('ignorado', 'duplicado', 'conciliado') or v_norm = '' then\n"
           "            v_rec := null;\n"
           "        elsif jsonb_array_length(v_cands) > 1 then\n"
           "            v_status := 'revisar';\n"
           "            v_msgs := v_msgs || to_jsonb(format('Mais de uma recorrencia do cartao combina com a descricao (%s): a linha nao foi vinculada; revise os nomes ou os apelidos de cobranca.',\n"
           "                (select string_agg(c ->> 'nome', ', ' order by (c ->> 'id')::integer) from jsonb_array_elements(v_cands) c)));\n"
           "        elsif v_rec is not null then\n"
           "            select l.* into v_occ\n"
           "              from public.lancamento_agregado l\n"
           "             where l.item_despesa_id = v_rec and l.cartao_id = p_cartao_id\n"
           "               and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp\n"
           "             order by l.id limit 1;\n"
           "            if found then\n"
           "                v_fat_occ := financeiro.fatura_do_mes(p_cartao_id, v_occ.mes_fatura);\n"
           "                if coalesce(v_occ.is_recorrente, false) and coalesce(v_occ.total_parcelas, 1) = 1\n"
           "                   and not coalesce(v_occ.is_importado, false)\n"
           "                   and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o\n"
           "                                    where o.lancamento_id = v_occ.id and o.revertida_em is null)\n"
           "                   and (v_fat_occ is null or not (financeiro.fatura_esta_paga(v_fat_occ)\n"
           "                        or exists (select 1 from public.conta c where c.id = v_fat_occ and c.status_fatura = 'FECHADA'))) then\n"
           "                    v_realiza := v_occ.id;\n"
           "                    v_prev := v_occ.valor;\n"
           "                    v_msgs := v_msgs || to_jsonb(format('Cobranca real da recorrencia \"%s\": confirma a previsao de R$ %s desta fatura (executado R$ %s%s).',\n"
           "                        v_rec_nome, to_char(v_prev, 'FM999999990.00'), to_char(v_valor, 'FM999999990.00'),\n"
           "                        case when v_valor <> v_prev then '; diferenca R$ ' || to_char(v_valor - v_prev, 'FM999999990.00') else '' end));\n"
           "                else\n"
           "                    v_conc := jsonb_build_object('lancamento_id', v_occ.id,\n"
           "                                                 'descricao', coalesce(nullif(v_occ.descricao_exibida, ''), v_occ.descricao),\n"
           "                                                 'data_compra', v_occ.data_compra, 'valor', v_occ.valor, 'categoria_id', v_occ.categoria_id,\n"
           "                                                 'recorrente', true, 'mantida', false);\n"
           "                    v_status := 'conciliado';\n"
           "                    v_ignorar := true;\n"
           "                    v_msgs := v_msgs || to_jsonb(format('Recorrencia ja lancada nesta fatura: %s (R$ %s); a compra existente fica como esta%s.',\n"
           "                        v_conc ->> 'descricao', to_char((v_conc ->> 'valor')::numeric, 'FM999999990.00'),\n"
           "                        case when (v_conc ->> 'valor')::numeric <> v_valor\n"
           "                             then format(' (no arquivo, R$ %s: para corrigir, edite a compra)', to_char(v_valor, 'FM999999990.00'))\n"
           "                             else '' end));\n"
           "                    v_rec := null;\n"
           "                end if;\n"
           "            else\n"
           "                v_msgs := v_msgs || to_jsonb(format('Reconhecida como compra recorrente do cartao (\"%s\"): o gerador nao a lanca de novo nesta competencia.', v_rec_nome));\n"
           "            end if;\n"
           "        end if;\n\n", 'ana')
t = trocar(t, "            else\n                select v.categoria_cartao_id into v_cc_res\n",
           f"            elsif v_rec is null then  -- {MARCA}: recorrencia nao precisa de Categoria do Cartao\n"
           "                select v.categoria_cartao_id into v_cc_res\n", 'ana')
t = trocar(t, "            when v_cc is null then 'categoria_cartao_pendente'\n",
           "            when v_rec is not null then 'classificada'\n            when v_cc is null then 'categoria_cartao_pendente'\n", 'ana')
t = trocar(t, "            'recorrencia_id', v_rec,\n",
           "            'recorrencia_id', v_rec,\n"
           "            'recorrencia_nome', case when v_rec is not null then v_rec_nome end,\n"
           "            'recorrencias_candidatas', case when jsonb_array_length(v_cands) > 1 then v_cands end,\n"
           "            'realiza_lancamento_id', v_realiza,\n"
           "            'valor_previsto', v_prev,\n", 'ana')
t = trocar(t, "            'conciliadas', count(*) filter (where jsonb_typeof(l -> 'conciliacao') = 'object'),\n",
           "            'conciliadas', count(*) filter (where jsonb_typeof(l -> 'conciliacao') = 'object'),\n"
           "            'realizacoes', count(*) filter (where l ->> 'realiza_lancamento_id' is not null and not (l ->> 'ignorar')::boolean),\n", 'ana')
t = trocar(t, "                                                       and l ->> 'categoria_cartao_id' is null),\n",
           "                                                       and l ->> 'categoria_cartao_id' is null\n"
           "                                                       and l ->> 'recorrencia_id' is null and (l ->> 'total_parcelas')::integer <= 1),\n", 'ana')
NOVO['analisar_importacao_cartao'] = t

# ---------------------------------------------------------------------------------------------------------------------
# importar_fatura_cartao: a linha que realiza a previsao atualiza a compra prevista (sem compra nova)
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['importar_fatura_cartao']
t = trocar(t, "    v_dup       integer;\nbegin\n", f"    v_dup       integer;\n    v_realizadas integer := 0;  -- {MARCA}\nbegin\n", 'imp')
t = trocar(t, "    for v_l in select e from jsonb_array_elements(v_a_gravar) e loop\n        v_n := (v_l ->> 'total_parcelas')::integer;\n",
           "    for v_l in select e from jsonb_array_elements(v_a_gravar) e loop\n"
           f"        -- {MARCA}: cobranca real da previsao da recorrencia: uma ocorrencia so, previsto preservado\n"
           "        if (v_l ->> 'realiza_lancamento_id') is not null then\n"
           "            v_id := financeiro.realizar_ocorrencia_recorrencia(p_perfil_id, (v_l ->> 'realiza_lancamento_id')::integer,\n"
           "                jsonb_build_object('valor', v_l ->> 'valor', 'data_compra', v_l ->> 'data_compra',\n"
           "                                   'descricao_original', v_l ->> 'descricao_original',\n"
           "                                   'descricao_original_normalizada', v_l ->> 'descricao_normalizada',\n"
           "                                   'is_importado', true, 'origem_importacao', coalesce(v_l ->> 'origem_importacao', 'csv')),\n"
           "                'IMPORTACAO', null);\n"
           "            v_realizadas := v_realizadas + 1;\n"
           "            v_alvo := (select l.mes_fatura from public.lancamento_agregado l where l.id = v_id);\n"
           "            if not v_alvo = any(v_meses) then\n"
           "                v_meses := v_meses || v_alvo;\n"
           "            end if;\n"
           "            continue;\n"
           "        end if;\n"
           "        v_n := (v_l ->> 'total_parcelas')::integer;\n", 'imp')
t = trocar(t, "        'inseridos', cardinality(v_ids), 'linhas_importadas', jsonb_array_length(v_a_gravar), 'duplicados', v_dup,\n",
           "        'inseridos', cardinality(v_ids), 'linhas_importadas', jsonb_array_length(v_a_gravar), 'duplicados', v_dup,\n"
           "        'realizadas', v_realizadas,\n", 'imp')
NOVO['importar_fatura_cartao'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Objetos novos
# ---------------------------------------------------------------------------------------------------------------------
NOVOS = r"""
-- =====================================================================================================================
-- 1. Natureza da compra: uma regra so, usada por todas as leituras
-- =====================================================================================================================
-- 1 PARCELADA (total_parcelas > 1) > 2 FIXA (compra de recorrencia: is_recorrente + item_despesa_id) > 3 CATEGORIA
-- (Categoria do Cartao gravada) > 4 OUTROS. So CATEGORIA consome limite, gasto e complemento da Categoria do Cartao; a
-- fixa e a parcelada continuam com a categoria_cartao_id gravada (compatibilidade com o Flask), sem efeito no orcamento.
create function financeiro.natureza_da_compra(p_total_parcelas integer, p_recorrente boolean, p_item_despesa_id integer,
                                              p_categoria_cartao_id integer)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select case when coalesce(p_total_parcelas, 1) > 1 then 'PARCELADA'
                when coalesce(p_recorrente, false) and p_item_despesa_id is not null then 'FIXA'
                when p_categoria_cartao_id is not null then 'CATEGORIA'
                else 'OUTROS' end
$$;

-- Texto de cobranca para comparar descricoes: minusculas, sem acento, so letras e numeros separados por um espaco.
create function financeiro.texto_cobranca(p_texto text)
    returns text
    language sql
    immutable
    set search_path = ''
as $$
    select btrim(regexp_replace(lower(translate(coalesce(p_texto, ''),
               'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ',
               'AAAAAEEEEIIIIOOOOOUUUUCNaaaaaeeeeiiiiooooouuuucn')), '[^a-z0-9]+', ' ', 'g'))
$$;

-- =====================================================================================================================
-- 2. Ocorrencia reconciliada (previsto x executado) e apelidos de cobranca
-- =====================================================================================================================
-- A compra prevista pela recorrencia continua sendo a ocorrencia do mes (identidade: recorrencia_competencia e
-- compra_id). Quando a cobranca real chega, o valor da compra passa a ser o executado e o previsto fica aqui, com a
-- compra como era (reversao) e, na conciliacao de duas compras, a compra absorvida inteira (auditoria e reversao).
create table financeiro.ocorrencia_recorrencia_cartao (
    id                   bigint      generated always as identity primary key,
    perfil_financeiro_id integer     not null,
    lancamento_id        integer     not null,
    item_despesa_id      integer     not null,
    cartao_id            integer     not null,
    competencia          date        not null,
    valor_previsto       numeric(12, 2) not null,
    valor_executado      numeric(12, 2) not null,
    descricao_cobranca   text,
    origem               text        not null check (origem in ('IMPORTACAO', 'CONCILIACAO')),
    lancamento_antes     jsonb       not null,
    lancamento_absorvido jsonb,
    user_id              uuid        references auth.users (id) on delete set null,
    conciliada_em        timestamptz not null default now(),
    revertida_em         timestamptz,
    revertida_por        uuid        references auth.users (id) on delete set null,
    check (origem <> 'CONCILIACAO' or lancamento_absorvido is not null)
);
create unique index ocorrencia_recorrencia_cartao_vigente on financeiro.ocorrencia_recorrencia_cartao (lancamento_id)
    where revertida_em is null;
comment on table financeiro.ocorrencia_recorrencia_cartao is
    'FIN-CARTAO-DESPESAS-FIXAS-01: previsao de recorrencia no cartao realizada pela cobranca real (previsto x executado).';

create table financeiro.recorrencia_apelido (
    id                   bigint      generated always as identity primary key,
    perfil_financeiro_id integer     not null,
    item_despesa_id      integer     not null,
    apelido              text        not null check (length(apelido) between 3 and 80),
    ativo                boolean     not null default true,
    user_id              uuid        references auth.users (id) on delete set null,
    criado_em            timestamptz not null default now(),
    unique (item_despesa_id, apelido)
);
comment on table financeiro.recorrencia_apelido is
    'FIN-CARTAO-DESPESAS-FIXAS-01: apelidos de cobranca (texto normalizado) que reconhecem a recorrencia na fatura importada.';

alter table financeiro.ocorrencia_recorrencia_cartao enable row level security;
alter table financeiro.ocorrencia_recorrencia_cartao force row level security;
alter table financeiro.recorrencia_apelido enable row level security;
alter table financeiro.recorrencia_apelido force row level security;
revoke all on financeiro.ocorrencia_recorrencia_cartao from public, anon, authenticated;
revoke all on financeiro.recorrencia_apelido from public, anon, authenticated;

-- Realiza a previsao com a cobranca real. Interna (importacao e conciliacao); quem chama ja autorizou e travou o perfil.
create function financeiro.realizar_ocorrencia_recorrencia(p_perfil_id integer, p_previsto_id integer, p_cobranca jsonb,
                                                           p_origem text, p_absorvido jsonb)
    returns integer
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_prev  public.lancamento_agregado;
    v_fat   integer;
    v_valor numeric;
begin
    select * into v_prev from public.lancamento_agregado where id = p_previsto_id for update;
    if not found or not financeiro.pertence_ao_perfil(v_prev.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Previsao da recorrencia nao encontrada neste perfil' using errcode = '42501';
    end if;
    if financeiro.natureza_da_compra(v_prev.total_parcelas, v_prev.is_recorrente, v_prev.item_despesa_id,
                                     v_prev.categoria_cartao_id) <> 'FIXA' then
        raise exception 'A compra prevista nao e ocorrencia de recorrencia do cartao' using errcode = 'P0001';
    end if;
    if coalesce(v_prev.is_importado, false) or exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                                        where o.lancamento_id = v_prev.id and o.revertida_em is null) then
        raise exception 'A ocorrencia desta recorrencia ja tem cobranca real' using errcode = 'P0001';
    end if;
    v_fat := financeiro.fatura_do_mes(v_prev.cartao_id, v_prev.mes_fatura);
    perform 1 from public.conta where id = v_fat for update;
    if v_fat is not null and (financeiro.fatura_esta_paga(v_fat)
                              or exists (select 1 from public.conta c where c.id = v_fat and c.status_fatura = 'FECHADA')) then
        raise exception 'A fatura de % esta paga ou consolidada: a previsao fica como esta', to_char(v_prev.mes_fatura, 'MM/YYYY')
            using errcode = 'P0001';
    end if;
    begin
        v_valor := round((p_cobranca ->> 'valor')::numeric, 2);
    exception when others then
        v_valor := null;
    end;
    if v_valor is null or v_valor <= 0 or v_valor >= 100000000 then
        raise exception 'Valor da cobranca invalido' using errcode = '22023';
    end if;
    insert into financeiro.ocorrencia_recorrencia_cartao (perfil_financeiro_id, lancamento_id, item_despesa_id, cartao_id,
                                                          competencia, valor_previsto, valor_executado, descricao_cobranca,
                                                          origem, lancamento_antes, lancamento_absorvido, user_id)
    values (p_perfil_id, v_prev.id, v_prev.item_despesa_id, v_prev.cartao_id,
            coalesce(v_prev.mes_fatura_original, v_prev.mes_fatura), v_prev.valor, v_valor, p_cobranca ->> 'descricao_original',
            p_origem, to_jsonb(v_prev), p_absorvido, (select auth.uid()));
    update public.lancamento_agregado
       set valor = v_valor,
           data_compra = coalesce((p_cobranca ->> 'data_compra')::date, data_compra),
           descricao_original = coalesce(nullif(p_cobranca ->> 'descricao_original', ''), descricao_original),
           descricao_original_normalizada = coalesce(nullif(p_cobranca ->> 'descricao_original_normalizada', ''),
                                                     descricao_original_normalizada),
           is_importado = coalesce((p_cobranca ->> 'is_importado')::boolean, is_importado),
           origem_importacao = coalesce(left(nullif(p_cobranca ->> 'origem_importacao', ''), 20), origem_importacao)
     where id = v_prev.id;
    return v_prev.id;
end
$$;

-- Conciliacao oficial de uma previsao da recorrencia com uma compra comum ja lancada (a cobranca real, importada ou
-- manual): a previsao fica (identidade da recorrencia) com os dados da cobranca; a compra da cobranca sai, inteira na
-- auditoria. Mesmo cartao e mesma fatura, aberta. Reversivel por reverter_ocorrencia_recorrencia.
create function financeiro.conciliar_ocorrencia_recorrencia(p_perfil_id integer, p_previsto_id integer, p_versao_previsto text,
                                                            p_cobranca_id integer, p_versao_cobranca text, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_cartao;
    v_prev     public.lancamento_agregado;
    v_cob      public.lancamento_agregado;
    v_res      jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261028));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao e das compras do perfil
    if p_previsto_id is null or p_cobranca_id is null or p_previsto_id = p_cobranca_id then
        raise exception 'Informe a previsao e a cobranca (compras diferentes)' using errcode = '22023';
    end if;
    select * into v_prev from public.lancamento_agregado where id = p_previsto_id for update;
    select * into v_cob from public.lancamento_agregado where id = p_cobranca_id for update;
    if v_prev.id is null or v_cob.id is null
       or not financeiro.pertence_ao_perfil(v_prev.perfil_financeiro_id, p_perfil_id)
       or not financeiro.pertence_ao_perfil(v_cob.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Compra nao encontrada neste perfil' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, v_prev.cartao_id, false);
    if p_versao_previsto is distinct from financeiro.versao_compra(v_prev.id)
       or p_versao_cobranca is distinct from financeiro.versao_compra(v_cob.id) then
        raise exception 'A compra foi alterada por outra operacao. Recarregue e tente de novo.' using errcode = 'P0001', hint = 'VERSAO';
    end if;
    if v_cob.cartao_id <> v_prev.cartao_id or v_cob.mes_fatura <> v_prev.mes_fatura then
        raise exception 'A previsao e a cobranca devem estar no mesmo cartao e na mesma fatura' using errcode = '22023';
    end if;
    if financeiro.natureza_da_compra(v_cob.total_parcelas, v_cob.is_recorrente, v_cob.item_despesa_id, v_cob.categoria_cartao_id)
       not in ('CATEGORIA', 'OUTROS') or v_cob.item_despesa_id is not null then
        raise exception 'A cobranca deve ser uma compra comum (nem parcelada, nem de recorrencia)' using errcode = '22023';
    end if;
    if exists (select 1 from public.fatura_consolidada_inclusao i where i.lancamento_id = v_cob.id) then
        raise exception 'A cobranca foi incluida numa fatura consolidada: concilie pela propria fatura' using errcode = 'P0001';
    end if;
    perform financeiro.realizar_ocorrencia_recorrencia(p_perfil_id, v_prev.id,
        jsonb_build_object('valor', v_cob.valor, 'data_compra', v_cob.data_compra,
                           'descricao_original', coalesce(v_cob.descricao_original, v_cob.descricao),
                           'descricao_original_normalizada', coalesce(v_cob.descricao_original_normalizada, v_cob.descricao),
                           'is_importado', coalesce(v_cob.is_importado, false), 'origem_importacao', v_cob.origem_importacao),
        'CONCILIACAO', to_jsonb(v_cob));
    delete from public.lancamento_agregado where id = v_cob.id;  -- inteira em ocorrencia_recorrencia_cartao.lancamento_absorvido
    perform financeiro.recalcular_fatura(p_perfil_id, v_prev.cartao_id, v_prev.mes_fatura);
    v_res := jsonb_build_object(
        'ocorrencia_id', (select o.id from financeiro.ocorrencia_recorrencia_cartao o
                           where o.lancamento_id = v_prev.id and o.revertida_em is null),
        'lancamento_id', v_prev.id, 'cobranca_absorvida_id', v_cob.id, 'item_despesa_id', v_prev.item_despesa_id,
        'valor_previsto', v_prev.valor, 'valor_executado', v_cob.valor, 'diferenca', v_cob.valor - v_prev.valor,
        'fatura', v_prev.mes_fatura);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'conciliar_ocorrencia_recorrencia', v_res);
    return v_res;
end
$$;

-- Reversao de uma ocorrencia reconciliada: a compra volta a ser a previsao (como era) e a compra absorvida, se houver,
-- volta com o mesmo id. Recusada se a compra mudou depois ou se a fatura foi paga ou consolidada.
create function financeiro.reverter_ocorrencia_recorrencia(p_perfil_id integer, p_ocorrencia_id bigint, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_cartao;
    v_oc       financeiro.ocorrencia_recorrencia_cartao;
    v_l        public.lancamento_agregado;
    v_antes    public.lancamento_agregado;
    v_abs      public.lancamento_agregado;
    v_fat      integer;
    v_res      jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261028));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    select * into v_oc from financeiro.ocorrencia_recorrencia_cartao where id = p_ocorrencia_id for update;
    if not found or v_oc.perfil_financeiro_id <> p_perfil_id then
        raise exception 'Ocorrencia nao encontrada neste perfil' using errcode = '42501';
    end if;
    if v_oc.revertida_em is not null then
        raise exception 'Ocorrencia ja revertida' using errcode = 'P0001';
    end if;
    select * into v_l from public.lancamento_agregado where id = v_oc.lancamento_id for update;
    if not found then
        raise exception 'A compra da ocorrencia foi excluida: nada a reverter' using errcode = 'P0001';
    end if;
    v_antes := jsonb_populate_record(null::public.lancamento_agregado, v_oc.lancamento_antes);
    if v_l.valor <> v_oc.valor_executado or v_l.mes_fatura <> v_antes.mes_fatura or v_l.cartao_id <> v_antes.cartao_id then
        raise exception 'A compra foi alterada depois da conciliacao: a reversao nao e feita' using errcode = 'P0001';
    end if;
    v_fat := financeiro.fatura_do_mes(v_l.cartao_id, v_l.mes_fatura);
    perform 1 from public.conta where id = v_fat for update;
    if v_fat is not null and (financeiro.fatura_esta_paga(v_fat)
                              or exists (select 1 from public.conta c where c.id = v_fat and c.status_fatura = 'FECHADA')) then
        raise exception 'A fatura de % esta paga ou consolidada: a reversao nao e feita', to_char(v_l.mes_fatura, 'MM/YYYY')
            using errcode = 'P0001';
    end if;
    update public.lancamento_agregado
       set valor = v_antes.valor, data_compra = v_antes.data_compra, descricao_original = v_antes.descricao_original,
           descricao_original_normalizada = v_antes.descricao_original_normalizada, is_importado = v_antes.is_importado,
           origem_importacao = v_antes.origem_importacao
     where id = v_l.id;
    if v_oc.lancamento_absorvido is not null then
        v_abs := jsonb_populate_record(null::public.lancamento_agregado, v_oc.lancamento_absorvido);
        if exists (select 1 from public.lancamento_agregado where id = v_abs.id) then
            raise exception 'Ja existe compra com o id da cobranca absorvida (%)', v_abs.id using errcode = 'P0001';
        end if;
        insert into public.lancamento_agregado select (v_abs).*;
    end if;
    update financeiro.ocorrencia_recorrencia_cartao set revertida_em = now(), revertida_por = (select auth.uid())
     where id = v_oc.id;
    perform financeiro.recalcular_fatura(p_perfil_id, v_l.cartao_id, v_l.mes_fatura);
    v_res := jsonb_build_object('ocorrencia_id', v_oc.id, 'lancamento_id', v_l.id, 'valor_restaurado', v_antes.valor,
                                'cobranca_restaurada_id', v_abs.id);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'reverter_ocorrencia_recorrencia', v_res);
    return v_res;
end
$$;

-- Recorrencia do cartao do perfil (para os apelidos). Interna.
create function financeiro.recorrencia_cartao_do_perfil(p_perfil_id integer, p_item_id integer)
    returns public.item_despesa
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_item public.item_despesa;
begin
    select * into v_item from public.item_despesa where id = p_item_id;
    if not found or not financeiro.pertence_ao_perfil(v_item.perfil_financeiro_id, p_perfil_id)
       or not coalesce(v_item.recorrente, false) or v_item.tipo = 'Agregador' or coalesce(v_item.meio_pagamento, '') <> 'cartao' then
        raise exception 'Recorrencia do cartao nao encontrada neste perfil' using errcode = '42501';
    end if;
    return v_item;
end
$$;

create function financeiro.apelidos_da_recorrencia(p_perfil_id integer, p_item_id integer)
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
    perform financeiro.recorrencia_cartao_do_perfil(p_perfil_id, p_item_id);
    return coalesce((select jsonb_agg(jsonb_build_object('id', a.id, 'apelido', a.apelido, 'criado_em', a.criado_em) order by a.apelido)
                       from financeiro.recorrencia_apelido a where a.item_despesa_id = p_item_id and a.ativo), '[]'::jsonb);
end
$$;

create function financeiro.criar_apelido_recorrencia(p_perfil_id integer, p_item_id integer, p_apelido text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item   public.item_despesa;
    v_texto  text := financeiro.texto_cobranca(p_apelido);
    v_outra  text;
    v_id     bigint;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    v_item := financeiro.recorrencia_cartao_do_perfil(p_perfil_id, p_item_id);
    if length(v_texto) < 3 or length(v_texto) > 80 then
        raise exception 'Apelido deve ter de 3 a 80 letras ou numeros' using errcode = '22023';
    end if;
    select i.nome into v_outra
      from financeiro.recorrencia_apelido a join public.item_despesa i on i.id = a.item_despesa_id
     where a.apelido = v_texto and a.ativo and a.item_despesa_id <> p_item_id and i.cartao_id = v_item.cartao_id
     limit 1;
    if v_outra is null then
        select i.nome into v_outra from public.item_despesa i
         where i.id <> p_item_id and i.cartao_id = v_item.cartao_id and coalesce(i.recorrente, false) and coalesce(i.ativo, true)
           and i.meio_pagamento = 'cartao' and financeiro.texto_cobranca(i.nome) = v_texto
         limit 1;
    end if;
    if v_outra is not null then
        raise exception 'Apelido ja reconhece outra recorrencia deste cartao: %', v_outra using errcode = '22023';
    end if;
    insert into financeiro.recorrencia_apelido (perfil_financeiro_id, item_despesa_id, apelido, user_id)
    values (p_perfil_id, p_item_id, v_texto, (select auth.uid()))
    on conflict (item_despesa_id, apelido) do update set ativo = true
    returning id into v_id;
    return jsonb_build_object('id', v_id, 'item_despesa_id', p_item_id, 'apelido', v_texto);
end
$$;

create function financeiro.remover_apelido_recorrencia(p_perfil_id integer, p_apelido_id bigint)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_item integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select a.item_despesa_id into v_item from financeiro.recorrencia_apelido a
     where a.id = p_apelido_id and a.perfil_financeiro_id = p_perfil_id;
    if v_item is null then
        raise exception 'Apelido nao encontrado neste perfil' using errcode = '42501';
    end if;
    update financeiro.recorrencia_apelido set ativo = false where id = p_apelido_id;
    return jsonb_build_object('id', p_apelido_id, 'ativo', false);
end
$$;
"""

PERMISSOES = """
-- Funcoes nascem com EXECUTE para PUBLIC: internas sem EXECUTE para o navegador; as de uso da tela para authenticated.
revoke execute on function financeiro.natureza_da_compra(integer, boolean, integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.texto_cobranca(text) from public, anon, authenticated;
revoke execute on function financeiro.realizar_ocorrencia_recorrencia(integer, integer, jsonb, text, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.recorrencia_cartao_do_perfil(integer, integer) from public, anon, authenticated;
revoke execute on function financeiro.conciliar_ocorrencia_recorrencia(integer, integer, text, integer, text, uuid) from public, anon;
revoke execute on function financeiro.reverter_ocorrencia_recorrencia(integer, bigint, uuid) from public, anon;
revoke execute on function financeiro.apelidos_da_recorrencia(integer, integer) from public, anon;
revoke execute on function financeiro.criar_apelido_recorrencia(integer, integer, text) from public, anon;
revoke execute on function financeiro.remover_apelido_recorrencia(integer, bigint) from public, anon;
grant execute on function financeiro.conciliar_ocorrencia_recorrencia(integer, integer, text, integer, text, uuid) to authenticated;
grant execute on function financeiro.reverter_ocorrencia_recorrencia(integer, bigint, uuid) to authenticated;
grant execute on function financeiro.apelidos_da_recorrencia(integer, integer) to authenticated;
grant execute on function financeiro.criar_apelido_recorrencia(integer, integer, text) to authenticated;
grant execute on function financeiro.remover_apelido_recorrencia(integer, bigint) to authenticated;
revoke execute on function financeiro.compras_da_fatura(integer, integer, date) from public, anon;
grant execute on function financeiro.compras_da_fatura(integer, integer, date) to authenticated;
"""

CABECALHO = f"""-- {MARCA} — Despesas Fixas do cartao: natureza unica da compra, previsto x executado da recorrencia e
-- reconhecimento seguro da cobranca real.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261208090000).
-- Validada em cluster local descartavel (tests/test_supabase_cartao_despesas_fixas.py) e ensaiada numa copia fiel da
-- producao. Doc: docs/FIN_CARTAO_DESPESAS_FIXAS_01.md.
-- Reversao: supabase/reversao/20261208090000_cartao_despesas_fixas_anterior.sql.
--
-- Decisoes do titular (31/10/2026):
-- - natureza da compra, nesta prioridade: PARCELADA (total_parcelas > 1), FIXA (is_recorrente + item_despesa_id),
--   CATEGORIA (categoria_cartao_id), OUTROS. Parceladas e fixas sao obrigacoes ja contratadas: continuam com a
--   categoria_cartao_id gravada (compatibilidade), mas nao consomem limite, gasto nem complemento da Categoria do Cartao
--   em nenhuma leitura (fatura por categoria, limites, lista de Despesas, faturas do mes, Dashboard). Divergencia aceita
--   em relacao ao Flask (melhoria do novo aplicativo);
-- - a cobranca real substitui o EXECUTADO da ocorrencia do mes; o valor-base da recorrencia nao muda. O previsto fica em
--   financeiro.ocorrencia_recorrencia_cartao; a compra prevista continua a ser a ocorrencia (uma so por mes);
-- - recorrencia nunca e conciliada so pelo valor: reconhecimento por cartao, competencia, recorrencia ativa e descricao
--   (nome ou apelido de cobranca como palavras inteiras); o valor so desempata;
-- - conciliacao oficial de previsao + cobranca ja lancada (conciliar_ocorrencia_recorrencia), reversivel, com a compra
--   absorvida inteira na auditoria. Nenhum dado existente e alterado por esta migration.
--
-- Funcoes existentes substituidas pelo texto vigente com os trechos marcados "{MARCA}": gasto_categoria_fatura,
-- fatura_por_categoria, lancamentos_fatura_por_categoria, contas_do_mes, faturas_do_mes, dashboard_resumo_tela,
-- analisar_importacao_cartao, importar_fatura_cartao; compras_da_fatura recriada (tipo de retorno com 3 colunas novas no
-- fim: valor_previsto, natureza, situacao_ocorrencia).
"""

ORDEM = ['gasto_categoria_fatura', 'fatura_por_categoria', 'lancamentos_fatura_por_categoria', 'contas_do_mes', 'faturas_do_mes',
         'dashboard_resumo_tela', 'analisar_importacao_cartao', 'importar_fatura_cartao']
partes = [CABECALHO, NOVOS,
          "\n-- =====================================================================================================================\n"
          "-- 3. Leituras e importacao: texto vigente + os trechos marcados\n"
          "-- =====================================================================================================================\n"]
for n in ORDEM:
    partes.append(f"\n-- {n}: texto de {FONTES[n][:14]} + os trechos marcados.\n{NOVO[n]}\n")
partes.append("\n-- compras_da_fatura: texto de 20261207090000 + previsto, natureza e situacao da ocorrencia (tipo de retorno muda).\n"
              "drop function financeiro.compras_da_fatura(integer, integer, date);\n\n" + NOVO['compras_da_fatura'] + "\n")
partes.append(PERMISSOES)
destino = MIG / '20261208090000_financeiro_cartao_despesas_fixas.sql'

REV = [f"""-- Reversao de 20261208090000 ({MARCA}): volta as leituras e a importacao ao texto anterior e remove os objetos
-- novos. Recusada enquanto houver ocorrencia reconciliada vigente (reverter antes com
-- financeiro.reverter_ocorrencia_recorrencia, para nao perder o previsto e as compras absorvidas) ou apelido ativo. So com
-- autorizacao, retirando a versao de supabase_migrations.schema_migrations.

do $$
begin
    if exists (select 1 from financeiro.ocorrencia_recorrencia_cartao where revertida_em is null) then
        raise exception 'Ha ocorrencia reconciliada vigente: reverta-as antes de remover a migration 20261208090000';
    end if;
    if exists (select 1 from financeiro.recorrencia_apelido where ativo) then
        raise exception 'Ha apelido de cobranca ativo: remova-os antes de remover a migration 20261208090000';
    end if;
end
$$;
"""]
for n in ORDEM:
    REV.append(f"\n-- {n}: texto de {FONTES[n][:14]}.\n{como_replace(ORIG[n])}\n")
REV.append("\n-- compras_da_fatura: texto de 20261207090000.\ndrop function financeiro.compras_da_fatura(integer, integer, date);\n\n"
           + ORIG['compras_da_fatura'] + "\n\nrevoke execute on function financeiro.compras_da_fatura(integer, integer, date) from public, anon;\n"
           "grant execute on function financeiro.compras_da_fatura(integer, integer, date) to authenticated;\n")
REV.append("""
drop function financeiro.remover_apelido_recorrencia(integer, bigint);
drop function financeiro.criar_apelido_recorrencia(integer, integer, text);
drop function financeiro.apelidos_da_recorrencia(integer, integer);
drop function financeiro.recorrencia_cartao_do_perfil(integer, integer);
drop function financeiro.reverter_ocorrencia_recorrencia(integer, bigint, uuid);
drop function financeiro.conciliar_ocorrencia_recorrencia(integer, integer, text, integer, text, uuid);
drop function financeiro.realizar_ocorrencia_recorrencia(integer, integer, jsonb, text, jsonb);
drop table financeiro.recorrencia_apelido;
drop table financeiro.ocorrencia_recorrencia_cartao;
drop function financeiro.texto_cobranca(text);
drop function financeiro.natureza_da_compra(integer, boolean, integer, integer);
""")
SAIDAS = {destino: ''.join(partes),
          RAIZ / 'supabase' / 'reversao' / '20261208090000_cartao_despesas_fixas_anterior.sql': ''.join(REV)}
if ARGS.verificar:
    # Bytes exatos (UTF-8), sem CR: o checkout no Windows pode trocar LF por CRLF (core.autocrlf).
    diferentes = [str(p.relative_to(RAIZ)) for p, texto in SAIDAS.items()
                  if not p.exists() or p.read_bytes().replace(b'\r\n', b'\n') != texto.encode('utf-8')]
    print('diferente: ' + ', '.join(diferentes) if diferentes else 'igual')
    sys.exit(1 if diferentes else 0)
for caminho, texto in SAIDAS.items():
    caminho.write_text(texto, encoding='utf-8', newline='\n')
print('ok', destino.stat().st_size)
