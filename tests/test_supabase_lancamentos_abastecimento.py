"""
Testes FIN-MVP-LANCAMENTOS-03, parte A (migration 20261222090000): abastecimento x compra importada, em cluster PostgreSQL local
descartavel com dados ficticios (Cartao Teste 910, Pessoal).

O abastecimento e o evento operacional; a compra, a obrigacao financeira. A previa da importacao sugere o abastecimento
compativel (nunca escolhe sozinha); a confirmacao vincula, na mesma transacao, so o que o usuario confirmou, a compra criada
ou a ja lancada que a analise reconheceu, sem criar outra despesa. Mobilidade mostra a despesa vinculada e vincula ou
desvincula pelas funcoes existentes. Dois veiculos, cartoes fisicos, conflito, periodo, outro perfil, idempotencia,
concorrencia, preservacao de movimentos e saldos, reversao.
"""
import datetime as dt
import uuid
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import ASSINATURAS, CARTAO
from tests.test_supabase_despesas import _paralelo
from tests.test_supabase_mobilidade_abastecimento import ONTEM, abastecer, cartao_fisico, compra, historico
from tests.test_supabase_mobilidade_escrita import PERFIL_B, PESSOAL, banco, cluster, erro  # noqa: F401
from tests.test_supabase_mobilidade_integridade import ATIVO, SIMULADO, criar
from tests.test_supabase_recorrencia import PG_BIN, USUARIO_B, sql
from tests.test_supabase_recorrencia_cartao import rpc  # aceita lista e objeto (jsonb)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

RAIZ = Path(__file__).resolve().parent.parent
MIGRATION = RAIZ / 'supabase/migrations/20261222090000_financeiro_lancamentos_abastecimento.sql'
REVERSAO = RAIZ / 'supabase/reversao/20261222090000_lancamentos_abastecimento_anterior.sql'
MES = ONTEM.replace(day=1).isoformat()
OUTRO_CARTAO = 911  # 'Cartao Sem Config' (Pessoal)
TABELAS = ('public.lancamento_agregado', 'public.conta', 'public.movimento_financeiro', 'public.conta_bancaria',
           'financeiro.abastecimento', 'financeiro.abastecimento_historico')


def linha(n, descricao='POSTO FICTICIO', valor='176.00', data=None, parcela=(1, 1), **extra):
    data = (data or ONTEM).isoformat()
    normal = ' '.join(''.join(c if c.isalnum() else ' ' for c in descricao.lower()).split())
    return {'linha_id': f'csv-{n}', 'linha_origem': n, 'data_compra': data, 'descricao_original': descricao,
            'descricao_normalizada': descricao, 'descricao_exibida': descricao, 'descricao_classificacao': normal,
            'valor': valor, 'parcela_atual': parcela[0], 'total_parcelas': parcela[1], 'tipo_movimento': 'debito',
            'categoria_id': ASSINATURAS, **extra}


def analise(dsn, *linhas, usuario=None):
    kw = {'usuario': usuario} if usuario else {}
    return rpc(dsn, 'analisar_importacao_cartao', PESSOAL, CARTAO, MES, list(linhas), **kw)


def sugestoes(dsn, *linhas, usuario=None):
    """Como o adaptador: a analise e, sobre ela, a situacao do abastecimento de cada linha."""
    a = analise(dsn, *linhas, usuario=usuario)
    kw = {'usuario': usuario} if usuario else {}
    return {s['linha_id']: s for s in rpc(dsn, 'abastecimentos_da_importacao', PESSOAL, CARTAO, a['linhas'], **kw)}


def importar(dsn, *linhas, chave=None):
    return rpc(dsn, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, list(linhas), chave or str(uuid.uuid4()))


def gravado(dsn):
    return {t: sql(dsn, f"select count(*) n, coalesce(md5(string_agg(x::text, '|' order by x::text)), '') h from {t} x")[0] for t in TABELAS}


def vinculo(dsn, abastecimento):
    return sql(dsn, 'select lancamento_id, conta_id from financeiro.abastecimento where id = %s', (abastecimento,))[0]


def manual(dsn, cartao=CARTAO, descricao='POSTO LANCADO A MAO', dia=None):
    """Compra lancada a mao (nao importada), de mesmo valor."""
    c = compra(dsn, cartao=cartao, dia=dia or ONTEM, descricao=descricao)
    sql(dsn, 'update public.lancamento_agregado set is_importado = false where id = %s', (c,))
    return c


def compras_do_posto(dsn):
    return sql(dsn, "select id, valor, data_compra from public.lancamento_agregado where descricao like 'POSTO%%' order by id")


# ---------------------------------------------------------------------------------------------------------------------
# Seguranca
# ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('funcao, publica', [
    ('financeiro.abastecimentos_da_importacao(integer, integer, jsonb)', True),
    ('financeiro.mob_vincular_importacao(integer, integer, integer)', False),
    ('financeiro.mob_despesa_do_abastecimento(integer, integer)', False)])
def test_funcoes_seguras(banco, funcao, publica):  # noqa: F811
    r = sql(banco, f"""select p.prosecdef d, coalesce(array_to_string(p.proconfig, ','), '') c,
                              has_function_privilege('anon', '{funcao}', 'EXECUTE') anon,
                              has_function_privilege('authenticated', '{funcao}', 'EXECUTE') aut
                         from pg_proc p where p.oid = '{funcao}'::regprocedure""")[0]
    assert r['d'] and 'search_path=""' in r['c'] and not r['anon'] and r['aut'] is publica


# ---------------------------------------------------------------------------------------------------------------------
# Previa: sugere, nunca escolhe sozinha
# ---------------------------------------------------------------------------------------------------------------------

def test_previa_sugere_o_abastecimento_livre_sem_gravar(banco):  # noqa: F811
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v, cartao_id=CARTAO)
    antes = gravado(banco)
    s = sugestoes(banco, linha(1))
    assert s['csv-1']['situacao'] == 'SUGERIDA' and [c['id'] for c in s['csv-1']['candidatas']] == [a['id']]
    assert s['csv-1']['candidatas'][0]['veiculo_id'] == v
    assert gravado(banco) == antes


def test_sem_abastecimento_compativel_nao_ha_sugestao(banco):  # noqa: F811
    v = criar(banco, SIMULADO)
    abastecer(banco, v, cartao_id=CARTAO)
    s = sugestoes(banco, linha(1, valor='175.00'), linha(2, data=ONTEM + dt.timedelta(days=11)), linha(3, data=ONTEM - dt.timedelta(days=4)))
    assert s == {}


def test_mesmo_valor_em_dois_veiculos_exige_escolha(banco):  # noqa: F811
    a = abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    b = abastecer(banco, criar(banco, ATIVO), cartao_id=CARTAO)
    s = sugestoes(banco, linha(1))
    assert s['csv-1']['situacao'] == 'MULTIPLA' and {c['id'] for c in s['csv-1']['candidatas']} == {a['id'], b['id']}


def test_mesmo_abastecimento_para_duas_linhas_exige_escolha(banco):  # noqa: F811
    abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    s = sugestoes(banco, linha(1), linha(2, descricao='POSTO OUTRO'))
    assert s['csv-1']['situacao'] == s['csv-2']['situacao'] == 'MULTIPLA'


def test_cartoes_fisicos_distintos_nao_se_misturam(banco):  # noqa: F811
    v = criar(banco, SIMULADO)
    f1, f2 = cartao_fisico(banco, '1111'), cartao_fisico(banco, '2222')
    a = abastecer(banco, v, cartao_id=CARTAO, cartao_vinculado_id=f1)
    s = sugestoes(banco, linha(1, cartao_final='2222'), linha(2, descricao='POSTO DOIS', cartao_final='1111'))
    assert 'csv-1' not in s and s['csv-2']['situacao'] == 'SUGERIDA' and s['csv-2']['candidatas'][0]['id'] == a['id']
    assert s['csv-2']['candidatas'][0]['mesmo_cartao_fisico'] is True
    assert f2


def test_parcelada_e_credito_nao_recebem_sugestao(banco):  # noqa: F811
    abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    s = sugestoes(banco, linha(1, parcela=(1, 2)), linha(2, tipo_movimento='credito', valor='176.00'))
    assert s == {}


def test_abastecimento_ja_vinculado_a_outra_despesa_e_conflito(banco):  # noqa: F811
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v)  # cartao nao informado no registro
    outra = manual(banco, cartao=OUTRO_CARTAO, descricao='OUTRA COMPRA')  # mesmo valor, em outro cartao, ja vinculada
    rpc(banco, 'vincular_abastecimento', PESSOAL, a['id'], {'lancamento_id': outra})
    s = sugestoes(banco, linha(1, descricao='POSTO DIFERENTE'))
    assert s['csv-1']['situacao'] == 'CONFLITO' and s['csv-1']['abastecimento']['despesa']['id'] == outra
    assert importar(banco, linha(1, descricao='POSTO DIFERENTE'))['abastecimentos_vinculados'] == 0  # importa; o vinculo fica


# ---------------------------------------------------------------------------------------------------------------------
# Confirmacao: vincula so o que foi confirmado, sem outra despesa
# ---------------------------------------------------------------------------------------------------------------------

def test_confirmar_vincula_a_compra_importada_sem_duplicar(banco):  # noqa: F811
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v, cartao_id=CARTAO)
    movimentos = sql(banco, 'select count(*) n from public.movimento_financeiro')[0]['n']
    r = importar(banco, linha(1, abastecimento_id=a['id']))
    assert r['inseridos'] == 1 and r['abastecimentos_vinculados'] == 1
    posto = compras_do_posto(banco)
    assert len(posto) == 1 and vinculo(banco, a['id']) == {'lancamento_id': posto[0]['id'], 'conta_id': None}
    assert [h['acao'] for h in sql(banco, 'select acao from financeiro.abastecimento_historico where abastecimento_id = %s order by id', (a['id'],))] == ['VINCULO']
    assert sql(banco, 'select count(*) n from public.movimento_financeiro')[0]['n'] == movimentos  # nenhum movimento
    assert historico(banco, v)['abastecimentos'][0]['despesa']['id'] == posto[0]['id']


def test_sem_confirmacao_importa_e_nao_vincula(banco):  # noqa: F811
    a = abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    r = importar(banco, linha(1))
    assert r['inseridos'] == 1 and r['abastecimentos_vinculados'] == 0
    assert vinculo(banco, a['id']) == {'lancamento_id': None, 'conta_id': None}


def test_compra_ja_lancada_reconhecida_recebe_o_vinculo_sem_compra_nova(banco):  # noqa: F811
    a = abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    lancada = manual(banco)
    s = sugestoes(banco, linha(1))
    assert s['csv-1']['situacao'] == 'SUGERIDA' and s['csv-1']['lancamento_id'] == lancada
    l = analise(banco, linha(1))['linhas'][0]
    assert l['status'] == 'conciliado'
    r = importar(banco, linha(1, ignorar=True, abastecimento_id=a['id']), linha(2, descricao='OUTRA COMPRA', valor='10.00'))
    assert r['inseridos'] == 1 and r['abastecimentos_vinculados'] == 1
    assert [c['id'] for c in compras_do_posto(banco)] == [lancada]
    assert vinculo(banco, a['id'])['lancamento_id'] == lancada


def test_compra_reconhecida_ja_vinculada_aparece_confirmada(banco):  # noqa: F811
    a = abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    lancada = manual(banco)
    rpc(banco, 'vincular_abastecimento', PESSOAL, a['id'], {'lancamento_id': lancada})
    s = sugestoes(banco, linha(1))
    assert s['csv-1']['situacao'] == 'CONFIRMADA' and s['csv-1']['abastecimento']['id'] == a['id']
    antes = gravado(banco)
    with pytest.raises(psycopg2.Error):
        importar(banco, linha(1))  # so a compra ja lancada: nada a importar
    assert gravado(banco) == antes


def test_dois_veiculos_na_mesma_fatura_cada_um_com_a_sua_compra(banco):  # noqa: F811
    v1, v2 = criar(banco, SIMULADO), criar(banco, ATIVO)
    a = abastecer(banco, v1, cartao_id=CARTAO)
    b = abastecer(banco, v2, cartao_id=CARTAO, valor_total=88, preco_litro=4.40)
    s = sugestoes(banco, linha(1), linha(2, descricao='POSTO DOIS', valor='88.00'))
    assert s['csv-1']['candidatas'][0]['veiculo_id'] == v1 and s['csv-2']['candidatas'][0]['veiculo_id'] == v2
    importar(banco, linha(1, abastecimento_id=a['id']), linha(2, descricao='POSTO DOIS', valor='88.00', abastecimento_id=b['id']))
    pares = sql(banco, 'select a.veiculo_id, l.valor from financeiro.abastecimento a join public.lancamento_agregado l on l.id = a.lancamento_id order by a.id')
    assert [(p['veiculo_id'], str(p['valor'])) for p in pares] == [(v1, '176.00'), (v2, '88.00')]


@pytest.mark.parametrize('extra, dica', [
    ({'parcela': (1, 2)}, 'ABASTECIMENTO_LINHA'),
    ({'data': ONTEM + dt.timedelta(days=12)}, 'ABASTECIMENTO_PERIODO'),
    ({'valor': '170.00'}, 'VALOR_DIVERGENTE')])
def test_confirmacao_invalida_desfaz_a_importacao_inteira(banco, extra, dica):  # noqa: F811
    a = abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    antes = gravado(banco)
    e = erro(importar, banco, linha(1, abastecimento_id=a['id'], **extra), linha(2, descricao='OUTRA COMPRA', valor='10.00'))
    assert e.diag.message_hint == dica and gravado(banco) == antes


def test_abastecimento_de_outro_perfil_recusado(banco):  # noqa: F811
    a = abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    sql(banco, 'update financeiro.abastecimento set perfil_financeiro_id = %s where id = %s', (PERFIL_B, a['id']))
    antes = gravado(banco)
    assert erro(importar, banco, linha(1, abastecimento_id=a['id'])).diag.message_hint == 'NAO_ENCONTRADA'
    assert gravado(banco) == antes
    assert erro(sugestoes, banco, linha(1), usuario=USUARIO_B).pgcode == '42501'


def test_importacao_repetida_nao_duplica_o_vinculo(banco):  # noqa: F811
    a = abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    chave = str(uuid.uuid4())
    importar(banco, linha(1, abastecimento_id=a['id']), chave=chave)
    depois = gravado(banco)
    r = importar(banco, linha(1, abastecimento_id=a['id']), chave=chave)
    assert r.get('repetida') is True and gravado(banco) == depois


def test_vincular_compra_de_fatura_paga_nao_muda_o_financeiro(banco):  # noqa: F811
    a = abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    c = compra(banco)
    sql(banco, "update public.conta set status_pagamento = 'Pago' where is_fatura_cartao and item_despesa_id = %s", (CARTAO,))
    financeiro = {t: v for t, v in gravado(banco).items() if not t.startswith('financeiro.abastecimento')}
    rpc(banco, 'vincular_abastecimento', PESSOAL, a['id'], {'lancamento_id': c})
    assert {t: v for t, v in gravado(banco).items() if not t.startswith('financeiro.abastecimento')} == financeiro


# ---------------------------------------------------------------------------------------------------------------------
# Mobilidade: despesa vinculada, vincular e desvincular
# ---------------------------------------------------------------------------------------------------------------------

def test_mobilidade_mostra_vincula_e_desvincula(banco):  # noqa: F811
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v, cartao_id=CARTAO)
    c = compra(banco)
    item = historico(banco, v)['abastecimentos'][0]
    assert item['situacao_vinculo'] == 'AGUARDANDO' and item['despesa'] is None
    cand = rpc(banco, 'candidatas_abastecimento', PESSOAL, a['id'])
    assert [x['id'] for x in cand['candidatas']] == [c] and cand['ambigua'] is False
    compras_antes = sql(banco, 'select * from public.lancamento_agregado order by id')
    rpc(banco, 'vincular_abastecimento', PESSOAL, a['id'], {'lancamento_id': c})
    d = historico(banco, v)['abastecimentos'][0]['despesa']
    assert (d['natureza'], d['id'], d['importada'], float(d['valor'])) == ('COMPRA', c, True, 176.0)
    rpc(banco, 'desvincular_abastecimento', PESSOAL, a['id'])
    assert historico(banco, v)['abastecimentos'][0]['despesa'] is None
    assert sql(banco, 'select * from public.lancamento_agregado order by id') == compras_antes  # compra intacta


def test_duas_vinculacoes_simultaneas_da_mesma_compra_uma_vale(banco):  # noqa: F811
    v = criar(banco, SIMULADO)
    a = abastecer(banco, v, cartao_id=CARTAO, hodometro_km=100)
    b = abastecer(banco, v, cartao_id=CARTAO, hodometro_km=200)
    c = compra(banco)
    r = _paralelo([lambda: rpc(banco, 'vincular_abastecimento', PESSOAL, a['id'], {'lancamento_id': c}),
                   lambda: rpc(banco, 'vincular_abastecimento', PESSOAL, b['id'], {'lancamento_id': c})])
    assert sorted(x[0] for x in r) == ['erro', 'ok']
    assert sql(banco, 'select count(*) n from financeiro.abastecimento where lancamento_id = %s', (c,))[0]['n'] == 1


def test_importacao_e_vinculo_manual_simultaneos_sem_duplicar(banco):  # noqa: F811
    a = abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    outra = manual(banco, dia=ONTEM - dt.timedelta(days=2), descricao='OUTRO POSTO')
    r = _paralelo([lambda: importar(banco, linha(1, abastecimento_id=a['id'])),
                   lambda: rpc(banco, 'vincular_abastecimento', PESSOAL, a['id'], {'lancamento_id': outra})])
    assert sorted(x[0] for x in r) == ['erro', 'ok']
    assert vinculo(banco, a['id'])['lancamento_id'] is not None
    importadas = sql(banco, "select count(*) n from public.lancamento_agregado where descricao = 'POSTO FICTICIO'")[0]['n']
    assert importadas == (1 if r[0][0] == 'ok' else 0)  # a importacao que falhou nao deixou compra


# ---------------------------------------------------------------------------------------------------------------------
# Reversao
# ---------------------------------------------------------------------------------------------------------------------

def test_reversao_e_reaplicacao_preservam_os_vinculos(banco):  # noqa: F811
    a = abastecer(banco, criar(banco, SIMULADO), cartao_id=CARTAO)
    importar(banco, linha(1, abastecimento_id=a['id']))
    antes = gravado(banco)
    conn = psycopg2.connect(banco)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(REVERSAO.read_text(encoding='utf-8'))
            cur.execute("select count(*) from pg_proc where proname in ('abastecimentos_da_importacao', 'mob_vincular_importacao', 'mob_despesa_do_abastecimento')")
            assert cur.fetchone()[0] == 0
            cur.execute("select prosrc from pg_proc where proname = 'importar_fatura_cartao'")
            assert 'mob_vincular_importacao' not in cur.fetchone()[0]
        assert gravado(banco) == antes
        with conn, conn.cursor() as cur:
            cur.execute(MIGRATION.read_text(encoding='utf-8'))
        assert gravado(banco) == antes
    finally:
        conn.close()
