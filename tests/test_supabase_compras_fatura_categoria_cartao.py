"""
Testes FIN-CARTAO-AGRUPAMENTO-CATEGORIAS-01 — compras_da_fatura devolve a Categoria do Cartao gravada na compra
(migration 20261207090000), em cluster local descartavel com o cenario FICTICIO do FIN-RECORRENCIA-1: Cartao Teste
(910, Pessoal), limite ativo de Streaming CC (961, R$ 500), Outros CC (962) sem limite ativo; Assinaturas (952) -> 961;
Moradia (951) sem vinculo. Chamadas como o navegador (authenticated).
- categoria vinculada, sem vinculo e sem limite: a coluna nova traz o que esta gravado (nada e resolvido de novo);
- colunas anteriores iguais e na mesma ordem; parcela e recorrencia continuam como antes;
- funcao so le, segura (security definer, search_path vazio, sem anon) e isolada por perfil;
- reversao ao texto de 20261028090000 e reaplicacao.
"""
import re
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import CARTAO, CARTAO_B, MORADIA, comprar, tabela
from tests.test_supabase_recorrencia import (  # noqa: F401  (fixture de modulo reaproveitada)
    ID,
    PG_BIN,
    USUARIO_B,
    atribuir,
    cluster,
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
MES = '2029-05-01'
SUPABASE = Path(__file__).resolve().parent.parent / 'supabase'
MIGRATION = SUPABASE / 'migrations' / '20261207090000_financeiro_compras_fatura_categoria_cartao.sql'
REVERSAO = SUPABASE / 'reversao' / '20261207090000_compras_fatura_categoria_cartao_anterior.sql'
ORIGINAL = SUPABASE / 'migrations' / '20261028090000_financeiro_cartoes.sql'
COLUNAS_ANTERIORES = ['id', 'descricao', 'valor', 'data_compra', 'numero_parcela', 'total_parcelas', 'categoria_nome',
                      'recorrente', 'bloqueio', 'pode_editar']
ASSINATURA = 'financeiro.compras_da_fatura(integer, integer, date)'


@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    return dsn


def compras(dsn, mes=MES, perfil=PESSOAL, cartao=CARTAO, usuario=None):
    return tabela(dsn, 'compras_da_fatura', perfil, cartao, mes, **({'usuario': usuario} if usuario else {}))


def cenario(dsn):
    """Parcelada classificada (952 -> 961), a vista sem vinculo (Moradia) e uma gravada com Categoria sem limite (962)."""
    comprar(dsn, descricao='Notebook')                                               # 3x, Streaming CC
    comprar(dsn, descricao='Mercado', valor='40.00', total_parcelas=1, categoria_id=MORADIA)
    sql(dsn, "insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, categoria_id, categoria_cartao_id, "
             "descricao, valor, data_compra, mes_fatura, numero_parcela, total_parcelas) "
             "values (%s, %s, %s, 962, 'Sem limite', 10.00, '2029-05-02', %s, 1, 1)", (PESSOAL, CARTAO, MORADIA, MES))


def executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_devolve_a_categoria_do_cartao_gravada(banco):
    cenario(banco)
    gravado = {x['id']: x['categoria_cartao_id'] for x in sql(
        banco, 'select id, categoria_cartao_id from public.lancamento_agregado where cartao_id = %s and mes_fatura = %s',
        (CARTAO, MES))}
    lidas = compras(banco)
    assert {x['id']: x['categoria_cartao_id'] for x in lidas} == gravado
    por_descricao = {x['descricao']: x['categoria_cartao_id'] for x in lidas}
    assert por_descricao['Mercado'] is None             # categoria de despesa sem vinculo
    assert por_descricao['Sem limite'] == 962           # vinculo gravado, sem limite ativo no cartao: devolvido como esta
    assert [x['categoria_cartao_id'] for x in lidas if x['descricao'].startswith('Notebook')] == [961]


def test_colunas_anteriores_iguais_e_a_nova_no_fim(banco):
    cenario(banco)
    lidas = compras(banco)
    assert all(list(x) == COLUNAS_ANTERIORES + ['categoria_cartao_id'] for x in lidas)
    notebook = next(x for x in lidas if x['descricao'].startswith('Notebook'))
    assert (notebook['numero_parcela'], notebook['total_parcelas'], notebook['recorrente']) == (1, 3, False)


def test_nada_e_gravado_pela_leitura(banco):
    cenario(banco)
    antes = sql(banco, "select md5(string_agg(l::text, '|' order by l.id)) h from public.lancamento_agregado l")[0]['h']
    compras(banco)
    assert sql(banco, "select md5(string_agg(l::text, '|' order by l.id)) h from public.lancamento_agregado l")[0]['h'] == antes


def test_funcao_segura_e_isolada(banco):
    f = sql(banco, f"select prosecdef, proconfig, has_function_privilege('anon', '{ASSINATURA}', 'execute') anon, "
                   f"has_function_privilege('authenticated', '{ASSINATURA}', 'execute') autenticado, "
                   f"provolatile from pg_proc where oid = '{ASSINATURA}'::regprocedure")[0]
    assert (f['prosecdef'], f['proconfig'], f['anon'], f['autenticado'], f['provolatile']) == \
        (True, ['search_path=""'], False, True, 's')
    cenario(banco)
    with pytest.raises(psycopg2.Error) as erro:  # Perfil B nao le o cartao do Pessoal
        compras(banco, perfil=PESSOAL, usuario=USUARIO_B)
    assert erro.value.pgcode == '42501'
    assert compras(banco, perfil=ID['PERFIL_B'], cartao=CARTAO_B, usuario=USUARIO_B) == []


def test_reversao_volta_ao_texto_anterior_e_reaplica(banco):
    original = re.search(r'create function financeiro\.compras_da_fatura\(.*?\n\$\$;\n', ORIGINAL.read_text(encoding='utf-8'),
                         re.S).group(0)
    assert original in REVERSAO.read_text(encoding='utf-8')
    cenario(banco)
    executar(banco, REVERSAO)
    assert all(list(x) == COLUNAS_ANTERIORES for x in compras(banco))
    executar(banco, MIGRATION)
    assert all(list(x) == COLUNAS_ANTERIORES + ['categoria_cartao_id'] for x in compras(banco))
    assert sql(banco, f"select has_function_privilege('anon', '{ASSINATURA}', 'execute') a")[0]['a'] is False
