"""Gera a migration 20261209090000 (FIN-CARTAO-PREVISTO-EXECUTADO-01) e a reversao a partir do texto VIGENTE de cada
funcao, com substituicoes conferidas (cada trecho deve ocorrer exatamente uma vez).

As funcoes substituidas sao longas: a migration nao e editada a mao. Para muda-la, edite este gerador e rode-o; as
fontes sao as migrations anteriores (ja aplicadas, imutaveis). So texto SQL: nenhum dado, conexao ou credencial.

    python scripts/gerar_migration_cartao_previsto_executado.py              # grava a migration e a reversao
    python scripts/gerar_migration_cartao_previsto_executado.py --verificar  # so compara com os arquivos versionados

O teste tests/test_gerador_migration_cartao_previsto_executado.py confere que os arquivos versionados sao a saida exata.
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
MARCA = 'FIN-CARTAO-PREVISTO-EXECUTADO-01'
NAT = "financeiro.natureza_da_compra({p}.total_parcelas, {p}.is_recorrente, {p}.item_despesa_id, {p}.categoria_cartao_id)"
SIT = "financeiro.situacao_previsao({p}.id, {n}, {p}.is_importado, {p}.cartao_id, {p}.mes_fatura)"
FIXAS = '20261208090000_financeiro_cartao_despesas_fixas.sql'


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
    'executado_fatura': '20261031090000_financeiro_cartoes_pagamento.sql',
    'recalcular_fatura': '20261028090000_financeiro_cartoes.sql',
    'contas_do_mes': FIXAS,
    'faturas_do_mes': FIXAS,
    'fatura_por_categoria': FIXAS,
    'lancamentos_fatura_por_categoria': FIXAS,
    'dashboard_resumo_tela': FIXAS,
    'analisar_importacao_cartao': FIXAS,
    'reverter_ocorrencia_recorrencia': FIXAS,
    'compras_da_fatura': FIXAS,
}
ORIG = {n: bloco(a, n) for n, a in FONTES.items()}
NOVO = {}

# ---------------------------------------------------------------------------------------------------------------------
# Executado da fatura (pagamento e recalculo): a previsao pendente nao e executada
# ---------------------------------------------------------------------------------------------------------------------
t = como_replace(ORIG['executado_fatura'])
t = trocar(t, "    select coalesce(sum(l.valor), 0)\n",
           f"    -- {MARCA}: previsao de recorrencia ainda sem cobranca (ou nao cobrada) nao e executada\n"
           f"    select coalesce(sum(financeiro.valor_executado_compra(l.valor, {SIT.format(p='l', n=NAT.format(p='l'))})), 0)\n",
           'executado')
NOVO['executado_fatura'] = t

t = como_replace(ORIG['recalcular_fatura'])
t = trocar(t, "    select coalesce(sum(l.valor), 0) into v_exec from public.lancamento_agregado l\n",
           f"    -- {MARCA}: previsao de recorrencia ainda sem cobranca nao e executada\n"
           f"    select coalesce(sum(financeiro.valor_executado_compra(l.valor, {SIT.format(p='l', n=NAT.format(p='l'))})), 0)\n"
           "      into v_exec from public.lancamento_agregado l\n", 'recalcular')
NOVO['recalcular_fatura'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Lista de Despesas e faturas do mes: executado sem previsoes; previsto = executado + previsoes pendentes + limites
# ---------------------------------------------------------------------------------------------------------------------
t = como_replace(ORIG['contas_do_mes'])
t = trocar(t, "        select l.cartao_id, l.categoria_cartao_id, sum(l.valor) as total,\n",
           f"        -- {MARCA}: total = executado (sem previsao pendente); pendente = previsoes aguardando cobranca\n"
           "        select l.cartao_id, l.categoria_cartao_id, sum(financeiro.valor_executado_compra(l.valor, sit.s)) as total,\n"
           "               sum(l.valor) filter (where sit.s = 'PREVISTA') as pendente,\n", 'contas')
t = trocar(t, "          from public.lancamento_agregado l\n"
              "         where (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))\n"
              "           and l.mes_fatura = v_mes\n",
           "          from public.lancamento_agregado l\n"
           f"         cross join lateral (select {SIT.format(p='l', n=NAT.format(p='l'))} as s) sit\n"
           "         where (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))\n"
           "           and l.mes_fatura = v_mes\n", 'contas')
t = trocar(t, "               coalesce((select sum(g.total) from gastos g where g.cartao_id = c.item_despesa_id), 0) as executado,\n",
           "               coalesce((select sum(g.total) from gastos g where g.cartao_id = c.item_despesa_id), 0) as executado,\n"
           "               coalesce((select sum(g.pendente) from gastos g where g.cartao_id = c.item_despesa_id), 0) as pendente,\n", 'contas')
t = trocar(t, "               else f.executado + f.complemento\n", "               else f.executado + f.pendente + f.complemento\n", 'contas')
t = trocar(t, "           case when c.is_fatura_cartao then f.executado + f.complemento end,\n",
           "           case when c.is_fatura_cartao then f.executado + f.pendente + f.complemento end,\n", 'contas')
NOVO['contas_do_mes'] = t

t = como_replace(ORIG['faturas_do_mes'])
t = trocar(t, "        select l.cartao_id, l.categoria_cartao_id, sum(l.valor) as gasto, count(*) as qtd,\n",
           f"        -- {MARCA}: gasto = executado (sem previsao pendente); pendente = previsoes aguardando cobranca\n"
           "        select l.cartao_id, l.categoria_cartao_id, sum(financeiro.valor_executado_compra(l.valor, sit.s)) as gasto,\n"
           "               count(*) as qtd, sum(l.valor) filter (where sit.s = 'PREVISTA') as pendente,\n", 'faturas')
t = trocar(t, "          from public.lancamento_agregado l\n         where l.mes_fatura = v_mes",
           "          from public.lancamento_agregado l\n"
           f"         cross join lateral (select {SIT.format(p='l', n=NAT.format(p='l'))} as s) sit\n"
           "         where l.mes_fatura = v_mes", 'faturas')
t = trocar(t, "                else coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0)\n",
           "                else coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0)\n"
           "                     + coalesce((select sum(g.pendente) from gastos g where g.cartao_id = c.id), 0)\n", 'faturas')
NOVO['faturas_do_mes'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Cartoes: fatura por categoria e lancamentos por filtro
# ---------------------------------------------------------------------------------------------------------------------
t = como_replace(ORIG['fatura_por_categoria'])
t = trocar(t, f"        select l.valor, l.categoria_cartao_id, {NAT.format(p='l')} as natureza  -- FIN-CARTAO-DESPESAS-FIXAS-01\n"
              "          from public.lancamento_agregado l\n",
           f"        -- {MARCA}: valor = executado (a previsao pendente nao entra no gasto nem no total da fatura)\n"
           f"        select financeiro.valor_executado_compra(l.valor, sit.s) as valor, l.categoria_cartao_id, nat.n as natureza,\n"
           "               case when sit.s = 'PREVISTA' then l.valor else 0 end as pendente\n"
           "          from public.lancamento_agregado l\n"
           f"         cross join lateral (select {NAT.format(p='l')} as n) nat\n"
           f"         cross join lateral (select {SIT.format(p='l', n='nat.n')} as s) sit\n", 'fpc')
t = trocar(t, "                                       when 'sem_categoria' then 'OUTROS' else 'CATEGORIA' end,\n",
           "                                       when 'sem_categoria' then 'OUTROS' else 'CATEGORIA' end,\n"
           "               'previsto_pendente', case when g.tipo = 'despesas_fixas' then (select coalesce(sum(x.pendente), 0) from lanc x) end,\n",
           'fpc')
t = trocar(t, "                                     when 'despesas_fixas' then '[\"Recorrencias do cartao: nao consomem limite de Categoria do Cartao.\"]'::jsonb\n",
           "                                     when 'despesas_fixas' then case when (select coalesce(sum(x.pendente), 0) from lanc x) > 0\n"
           "                                         then jsonb_build_array('R$ ' || to_char((select sum(x.pendente) from lanc x), 'FM999999990.00')\n"
           "                                                                || ' previstos aguardando cobranca: fora do executado e do valor a pagar.')\n"
           "                                         else '[\"Recorrencias do cartao: nao consomem limite de Categoria do Cartao.\"]'::jsonb end\n",
           'fpc')
ini = t.index("    select coalesce(sum(l.valor), 0),\n")
fim = t.index("      into v_total, v_com, v_sem, v_fixas, v_parceladas, v_vinculadas\n")
trecho = t[ini:fim]
assert trecho.count('sum(l.valor)') == 6, trecho.count('sum(l.valor)')
t = t[:ini] + trecho.replace('sum(l.valor)', 'sum(ex.v)') \
    + "           , coalesce(sum(l.valor) filter (where sit.s = 'PREVISTA'), 0)\n" + t[fim:]
t = trocar(t, "      into v_total, v_com, v_sem, v_fixas, v_parceladas, v_vinculadas\n",
           "      into v_total, v_com, v_sem, v_fixas, v_parceladas, v_vinculadas, v_pendente\n", 'fpc')
t = trocar(t, f"     cross join lateral (select {NAT.format(p='l')} as n) nat  -- FIN-CARTAO-DESPESAS-FIXAS-01\n",
           f"     cross join lateral (select {NAT.format(p='l')} as n) nat  -- FIN-CARTAO-DESPESAS-FIXAS-01\n"
           f"     cross join lateral (select {SIT.format(p='l', n='nat.n')} as s) sit  -- {MARCA}\n"
           "     cross join lateral (select financeiro.valor_executado_compra(l.valor, sit.s) as v) ex\n", 'fpc')
t = trocar(t, "    v_parceladas numeric;\n", f"    v_parceladas numeric;\n    v_pendente   numeric;  -- {MARCA}\n", 'fpc')
t = trocar(t, "        'total_compras_parceladas', v_parceladas,\n",
           "        'total_compras_parceladas', v_parceladas,\n        'total_previsto_pendente', v_pendente,\n", 'fpc')
NOVO['fatura_por_categoria'] = t

t = como_replace(ORIG['lancamentos_fatura_por_categoria'])
t = trocar(t, "                       'natureza', nat.n,\n",
           "                       'natureza', nat.n,\n"
           f"                       -- {MARCA}: situacao da previsao, previsto e executado da compra\n"
           "                       'situacao_ocorrencia', sit.s,\n"
           "                       'valor_previsto', case when nat.n = 'FIXA' then coalesce((select o.valor_previsto\n"
           "                           from financeiro.ocorrencia_recorrencia_cartao o where o.lancamento_id = l.id and o.revertida_em is null), l.valor) end,\n"
           "                       'valor_executado', financeiro.valor_executado_compra(l.valor, sit.s),\n", 'lfc')
t = trocar(t, f"             cross join lateral (select {NAT.format(p='l')} as n) nat\n",
           f"             cross join lateral (select {NAT.format(p='l')} as n) nat\n"
           f"             cross join lateral (select {SIT.format(p='l', n='nat.n')} as s) sit\n", 'lfc')
NOVO['lancamentos_fatura_por_categoria'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Dashboard: total das faturas do periodo pelo executado atual (nao pelo gravado, que pode incluir previsoes)
# ---------------------------------------------------------------------------------------------------------------------
t = como_replace(ORIG['dashboard_resumo_tela'])
t = trocar(t, "nullif(c.valor_executado, 0)", "nullif(financeiro.executado_fatura(c.id), 0)", 'dash')
t = trocar(t, "    -- _total_faturas_periodo\n",
           f"    -- _total_faturas_periodo ({MARCA}: executado atual, sem previsoes pendentes)\n", 'dash')
NOVO['dashboard_resumo_tela'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Importacao: previsao marcada como nao cobrada (fatura paga sem ela) nao e a ocorrencia; a cobranca entra como compra
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['analisar_importacao_cartao']
t = trocar(t, "             where l.item_despesa_id = v_rec and l.cartao_id = p_cartao_id\n"
              "               and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp\n",
           "             where l.item_despesa_id = v_rec and l.cartao_id = p_cartao_id\n"
           "               and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp\n"
           f"               -- {MARCA}: a previsao que a fatura paga deixou sem cobranca nao e a ocorrencia; a cobranca\n"
           "               -- real que chega depois entra como compra da recorrencia (na proxima fatura aberta)\n"
           "               and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o\n"
           "                                where o.lancamento_id = l.id and o.revertida_em is null and o.origem = 'NAO_COBRADA')\n", 'ana')
NOVO['analisar_importacao_cartao'] = t

t = como_replace(ORIG['reverter_ocorrencia_recorrencia'])
t = trocar(t, "    if v_oc.revertida_em is not null then\n        raise exception 'Ocorrencia ja revertida' using errcode = 'P0001';\n    end if;\n",
           "    if v_oc.revertida_em is not null then\n        raise exception 'Ocorrencia ja revertida' using errcode = 'P0001';\n    end if;\n"
           f"    if v_oc.origem = 'NAO_COBRADA' then  -- {MARCA}: desfeita so pelo estorno do pagamento da fatura\n"
           "        raise exception 'Previsao nao cobrada no pagamento da fatura: e desfeita pelo estorno do pagamento' using errcode = 'P0001';\n"
           "    end if;\n", 'rev')
NOVO['reverter_ocorrencia_recorrencia'] = t

# ---------------------------------------------------------------------------------------------------------------------
# compras_da_fatura: situacao da previsao (PREVISTA, CONFIRMADA, NAO_COBRADA, PAGA) e executado da compra
# ---------------------------------------------------------------------------------------------------------------------
t = ORIG['compras_da_fatura']
t = trocar(t, "valor_previsto numeric, natureza text, situacao_ocorrencia text)\n",
           "valor_previsto numeric, natureza text, situacao_ocorrencia text,\n                   valor_executado numeric)\n", 'cdf')
t = trocar(t, "               case when nat.n = 'FIXA' then case when o.id is not null or coalesce(l.is_importado, false)\n"
              "                                                  then 'CONFIRMADA' else 'PREVISTA' end end\n",
           f"               sit.s,  -- {MARCA}\n"
           "               financeiro.valor_executado_compra(l.valor, sit.s)\n", 'cdf')
t = trocar(t, f"         cross join lateral (select {NAT.format(p='l')} as n) nat\n",
           f"         cross join lateral (select {NAT.format(p='l')} as n) nat\n"
           f"         cross join lateral (select {SIT.format(p='l', n='nat.n')} as s) sit\n", 'cdf')
NOVO['compras_da_fatura'] = t

# ---------------------------------------------------------------------------------------------------------------------
# Objetos novos
# ---------------------------------------------------------------------------------------------------------------------
NOVOS = r"""
-- =====================================================================================================================
-- 1. Situacao da previsao da recorrencia e executado da compra
-- =====================================================================================================================
-- Compra FIXA (recorrencia no cartao):
-- - CONFIRMADA: cobranca real importada, realizada ou conciliada (executado = valor da compra);
-- - PREVISTA: gerada pela recorrencia, sem cobranca, em fatura nao paga (executado = 0; o valor e o previsto);
-- - NAO_COBRADA: a fatura foi paga sem ela (marcada no pagamento; executado = 0; o estorno do pagamento a devolve);
-- - PAGA: em fatura paga antes desta regra (historico preservado: executado = valor, como foi pago).
-- Demais naturezas: sem situacao, executado = valor.
create function financeiro.situacao_previsao(p_lancamento_id integer, p_natureza text, p_importado boolean,
                                             p_cartao_id integer, p_mes_fatura date)
    returns text
    language sql
    stable
    set search_path = ''
as $$
    select case
               when p_natureza is distinct from 'FIXA' then null
               when coalesce(p_importado, false) then 'CONFIRMADA'
               else coalesce((select case o.origem when 'NAO_COBRADA' then 'NAO_COBRADA' else 'CONFIRMADA' end
                                from financeiro.ocorrencia_recorrencia_cartao o
                               where o.lancamento_id = p_lancamento_id and o.revertida_em is null),
                             case when coalesce(financeiro.fatura_esta_paga(financeiro.fatura_do_mes(p_cartao_id, p_mes_fatura)), false)
                                  then 'PAGA' else 'PREVISTA' end)
           end
$$;

create function financeiro.valor_executado_compra(p_valor numeric, p_situacao text)
    returns numeric
    language sql
    immutable
    set search_path = ''
as $$
    select case when p_situacao in ('PREVISTA', 'NAO_COBRADA') then 0 else coalesce(p_valor, 0) end
$$;

-- =====================================================================================================================
-- 2. Pagamento da fatura: previsoes sem cobranca ficam marcadas como nao cobradas; o estorno devolve
-- =====================================================================================================================
alter table financeiro.ocorrencia_recorrencia_cartao drop constraint ocorrencia_recorrencia_cartao_origem_check;
alter table financeiro.ocorrencia_recorrencia_cartao
    add constraint ocorrencia_recorrencia_cartao_origem_check check (origem in ('IMPORTACAO', 'CONCILIACAO', 'NAO_COBRADA')),
    add column pagamento_id bigint references financeiro.pagamento_fatura (id) on delete set null;
comment on column financeiro.ocorrencia_recorrencia_cartao.pagamento_id is
    'FIN-CARTAO-PREVISTO-EXECUTADO-01: pagamento da fatura que deixou a previsao sem cobranca (NAO_COBRADA).';

-- Gatilho em financeiro.pagamento_fatura (pagamento de fatura pelo novo aplicativo): o valor pago foi o executado, sem as
-- previsoes pendentes; elas ficam registradas como nao cobradas naquela fatura (executado 0, a fatura paga continua
-- igual ao que foi pago). No estorno do pagamento, as marcas daquele pagamento sao desfeitas (a previsao volta a
-- aguardar cobranca). Pagamentos de despesa e os registros de estorno do Flask nao sao afetados.
create function financeiro.previsoes_no_pagamento_da_fatura()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
declare
    v_fatura public.conta;
begin
    if tg_op = 'INSERT' then
        if new.origem <> 'NOVO_APP' or new.estorno_movimento_id is not null then
            return null;
        end if;
        select * into v_fatura from public.conta where id = new.fatura_id;
        if not found or not coalesce(v_fatura.is_fatura_cartao, false) then
            return null;
        end if;
        insert into financeiro.ocorrencia_recorrencia_cartao (perfil_financeiro_id, lancamento_id, item_despesa_id, cartao_id,
                                                              competencia, valor_previsto, valor_executado, descricao_cobranca,
                                                              origem, lancamento_antes, pagamento_id, user_id)
        select new.perfil_financeiro_id, l.id, l.item_despesa_id, l.cartao_id, coalesce(l.mes_fatura_original, l.mes_fatura),
               l.valor, 0, null, 'NAO_COBRADA', to_jsonb(l), new.id, new.user_id
          from public.lancamento_agregado l
         where l.cartao_id = v_fatura.item_despesa_id and l.mes_fatura = v_fatura.cartao_competencia
           and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, coalesce(v_fatura.perfil_financeiro_id,
                   (select p.id from public.perfil_financeiro p where p.nome = 'Pessoal' order by p.id limit 1)))
           and financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) = 'FIXA'
           and not coalesce(l.is_importado, false)
           and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                            where o.lancamento_id = l.id and o.revertida_em is null)
         order by l.id;
    elsif old.estorno_movimento_id is null and new.estorno_movimento_id is not null then
        update financeiro.ocorrencia_recorrencia_cartao
           set revertida_em = now(), revertida_por = new.estorno_user_id
         where pagamento_id = new.id and origem = 'NAO_COBRADA' and revertida_em is null;
    end if;
    return null;
end
$$;

create trigger previsoes_no_pagamento_da_fatura
    after insert or update of estorno_movimento_id on financeiro.pagamento_fatura
    for each row execute function financeiro.previsoes_no_pagamento_da_fatura();
"""

PERMISSOES = """
-- Internas: sem EXECUTE para o navegador.
revoke execute on function financeiro.situacao_previsao(integer, text, boolean, integer, date) from public, anon, authenticated;
revoke execute on function financeiro.valor_executado_compra(numeric, text) from public, anon, authenticated;
revoke execute on function financeiro.previsoes_no_pagamento_da_fatura() from public, anon, authenticated;
revoke execute on function financeiro.compras_da_fatura(integer, integer, date) from public, anon;
grant execute on function financeiro.compras_da_fatura(integer, integer, date) to authenticated;
"""

CABECALHO = f"""-- {MARCA} — separacao definitiva entre previsao e execucao das despesas fixas do cartao.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261209090000).
-- Validada em cluster local descartavel (tests/test_supabase_cartao_previsto_executado.py) e ensaiada numa copia fiel
-- da producao. Doc: docs/FIN_CARTAO_DESPESAS_FIXAS_01.md (secao 7). Gerada por
-- scripts/gerar_migration_cartao_previsto_executado.py.
-- Reversao: supabase/reversao/20261209090000_cartao_previsto_executado_anterior.sql.
--
-- Regras:
-- - a compra que a recorrencia preve (gerada, ainda sem cobranca real) e PREVISTA: aparece no planejamento pelo valor
--   previsto, mas nao entra no executado da fatura nem no valor a pagar (pagamento, lista de Despesas, faturas do mes,
--   Cartoes, Dashboard);
-- - a cobranca real (importada, realizada ou conciliada) e CONFIRMADA: o executado e o valor cobrado; o previsto fica em
--   ocorrencia_recorrencia_cartao; o valor-base da recorrencia nao muda;
-- - previsto da fatura = executado + previsoes pendentes + o que falta dos limites (o valor exibido nao muda);
-- - pagamento: paga o executado; as previsoes ainda pendentes ficam NAO_COBRADA naquela fatura (gatilho em
--   pagamento_fatura) e voltam a aguardar cobranca no estorno; a cobranca que chegar depois entra como compra da
--   recorrencia na proxima fatura aberta;
-- - faturas pagas antes desta regra ficam como foram pagas (previsao em fatura paga = PAGA, executada);
-- - nenhum dado existente e alterado; o valor_executado gravado das faturas abertas se atualiza no proximo recalculo
--   (as telas e o pagamento usam o executado calculado na hora).
--
-- Funcoes existentes substituidas pelo texto vigente com os trechos marcados "{MARCA}": executado_fatura,
-- recalcular_fatura, contas_do_mes, faturas_do_mes, fatura_por_categoria, lancamentos_fatura_por_categoria,
-- dashboard_resumo_tela, analisar_importacao_cartao, reverter_ocorrencia_recorrencia; compras_da_fatura recriada (coluna
-- nova no fim: valor_executado).
"""

ORDEM = ['executado_fatura', 'recalcular_fatura', 'contas_do_mes', 'faturas_do_mes', 'fatura_por_categoria',
         'lancamentos_fatura_por_categoria', 'dashboard_resumo_tela', 'analisar_importacao_cartao',
         'reverter_ocorrencia_recorrencia']
partes = [CABECALHO, NOVOS,
          "\n-- =====================================================================================================================\n"
          "-- 3. Leituras, pagamento e importacao: texto vigente + os trechos marcados\n"
          "-- =====================================================================================================================\n"]
for n in ORDEM:
    partes.append(f"\n-- {n}: texto de {FONTES[n][:14]} + os trechos marcados.\n{NOVO[n]}\n")
partes.append("\n-- compras_da_fatura: texto de 20261208090000 + situacao e executado da compra (tipo de retorno muda).\n"
              "drop function financeiro.compras_da_fatura(integer, integer, date);\n\n" + NOVO['compras_da_fatura'] + "\n")
partes.append(PERMISSOES)
destino = MIG / '20261209090000_financeiro_cartao_previsto_executado.sql'

REV = [f"""-- Reversao de 20261209090000 ({MARCA}): volta as leituras, o pagamento e a importacao ao texto anterior e remove
-- os objetos novos. Recusada enquanto houver previsao marcada como nao cobrada vigente (estornar antes o pagamento, para
-- nao perder a marca). So com autorizacao, retirando a versao de supabase_migrations.schema_migrations.

do $$
begin
    if exists (select 1 from financeiro.ocorrencia_recorrencia_cartao where origem = 'NAO_COBRADA' and revertida_em is null) then
        raise exception 'Ha previsao nao cobrada vigente: estorne o pagamento antes de remover a migration 20261209090000';
    end if;
end
$$;

drop trigger previsoes_no_pagamento_da_fatura on financeiro.pagamento_fatura;
drop function financeiro.previsoes_no_pagamento_da_fatura();
"""]
for n in ORDEM:
    REV.append(f"\n-- {n}: texto de {FONTES[n][:14]}.\n{como_replace(ORIG[n])}\n")
REV.append("\n-- compras_da_fatura: texto de 20261208090000.\ndrop function financeiro.compras_da_fatura(integer, integer, date);\n\n"
           + ORIG['compras_da_fatura'] + "\n\nrevoke execute on function financeiro.compras_da_fatura(integer, integer, date) from public, anon;\n"
           "grant execute on function financeiro.compras_da_fatura(integer, integer, date) to authenticated;\n")
REV.append("""
-- As marcas revertidas (historico) saem com a coluna; a restricao volta ao texto de 20261208090000.
delete from financeiro.ocorrencia_recorrencia_cartao where origem = 'NAO_COBRADA';
alter table financeiro.ocorrencia_recorrencia_cartao drop column pagamento_id;
alter table financeiro.ocorrencia_recorrencia_cartao drop constraint ocorrencia_recorrencia_cartao_origem_check;
alter table financeiro.ocorrencia_recorrencia_cartao
    add constraint ocorrencia_recorrencia_cartao_origem_check check (origem in ('IMPORTACAO', 'CONCILIACAO'));
drop function financeiro.valor_executado_compra(numeric, text);
drop function financeiro.situacao_previsao(integer, text, boolean, integer, date);
""")

SAIDAS = {destino: ''.join(partes),
          RAIZ / 'supabase' / 'reversao' / '20261209090000_cartao_previsto_executado_anterior.sql': ''.join(REV)}
if ARGS.verificar:
    # Bytes exatos (UTF-8), sem CR: o checkout no Windows pode trocar LF por CRLF (core.autocrlf).
    diferentes = [str(p.relative_to(RAIZ)) for p, texto in SAIDAS.items()
                  if not p.exists() or p.read_bytes().replace(b'\r\n', b'\n') != texto.encode('utf-8')]
    print('diferente: ' + ', '.join(diferentes) if diferentes else 'igual')
    sys.exit(1 if diferentes else 0)
for caminho, texto in SAIDAS.items():
    caminho.write_text(texto, encoding='utf-8', newline='\n')
print('ok', destino.stat().st_size)
