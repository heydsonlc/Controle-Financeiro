"""
Teste FIN-AUDITORIA-GERAL-1 (condicao 6 da aplicacao conjunta) — recuperacao do Supabase de teste se o lote de migrations
20261106..20261118 falhar no meio ou precisar ser desfeito (supabase/reversao/lote_20261106_20261118.sql).

Cluster descartavel com todas as migrations: a reversao remove exatamente as funcoes que o lote cria, devolve as duas
substituidas a definicao anterior (mesmos privilegios), tira as 12 versoes do historico e nao toca em mais nada; e
idempotente; reaplicar as 12 migrations depois devolve o estado de antes da reversao. Nenhum dado e usado.
"""
import re
from pathlib import Path

import pytest

from tests.test_supabase_recorrencia import (
    PG_BIN,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

SUPABASE = Path(__file__).resolve().parent.parent / 'supabase'
REVERSAO = SUPABASE / 'reversao' / 'lote_20261106_20261118.sql'
LOTE = [p for p in sorted((SUPABASE / 'migrations').glob('*.sql')) if '20261106' <= p.name[:8] <= '20261118']
VERSOES = [p.name.split('_', 1)[0] for p in LOTE]
SUBSTITUIDAS = {'financeiro.analisar_importacao_cartao(integer,integer,date,jsonb)': 'analisar_importacao_cartao',
                'financeiro.plano_recorrencia(integer,date)': 'plano_recorrencia'}  # como regprocedure::text

ESTADO = """
select p.oid::regprocedure::text as assinatura, md5(p.prosrc) as corpo, coalesce(p.proacl::text, '') as acl,
       p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '') as config, p.provolatile
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'financeiro'
"""


def estado(dsn):
    return {r['assinatura']: r for r in sql(dsn, ESTADO)}


def executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:  # uma transacao, como a aplicacao manual da reversao
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def corpo_anterior(nome):
    """Corpo da ultima definicao da funcao ANTES do lote (o que a reversao deve devolver)."""
    for p in reversed(sorted((SUPABASE / 'migrations').glob('*.sql'))):
        if p.name[:8] >= '20261106':
            continue
        s = p.read_text(encoding='utf-8')
        m = re.search(rf'function financeiro\.{nome}\(', s)
        if m:
            ini = s.index('$$', m.start()) + 2
            return s[ini:s.index('$$', ini)]
    raise AssertionError(nome)


def test_reversao_do_lote_volta_ao_estado_anterior_e_permite_reaplicar(cluster):  # noqa: F811
    dsn = copiar(cluster)
    sql(dsn, 'create schema if not exists supabase_migrations')
    sql(dsn, 'create table if not exists supabase_migrations.schema_migrations (version text primary key)')
    sql(dsn, 'insert into supabase_migrations.schema_migrations (version) select unnest(%s::text[])',
        (['20261105090000', *VERSOES],))
    com_lote = estado(dsn)
    criadas = {f"financeiro.{m.group(1)}" for p in LOTE for m in re.finditer(r'create function financeiro\.(\w+)\(',
                                                                              p.read_text(encoding='utf-8'))}
    novas = {s for s in com_lote if s.split('(')[0] in criadas}
    assert len(novas) == len(criadas) == 87  # nomes novos, sem sobrecarga de funcao existente

    executar(dsn, REVERSAO)
    depois = estado(dsn)
    assert set(depois) == set(com_lote) - novas
    for assinatura, linha in depois.items():
        if assinatura in SUBSTITUIDAS:
            src = sql(dsn, 'select prosrc from pg_proc where oid = %s::regprocedure', (assinatura,))[0]['prosrc']
            assert src == corpo_anterior(SUBSTITUIDAS[assinatura]), assinatura
            assert {k: linha[k] for k in ('acl', 'prosecdef', 'config')} == \
                   {k: com_lote[assinatura][k] for k in ('acl', 'prosecdef', 'config')}, assinatura
        else:
            assert linha == com_lote[assinatura], assinatura  # nada mais muda
    assert [r['version'] for r in sql(dsn, 'select version from supabase_migrations.schema_migrations')] == ['20261105090000']

    executar(dsn, REVERSAO)  # idempotente (aplicacao parcial, ou repetida)
    assert estado(dsn) == depois

    for migration in LOTE:  # reaplicar o lote depois da recuperacao
        executar(dsn, migration)
    assert estado(dsn) == com_lote
