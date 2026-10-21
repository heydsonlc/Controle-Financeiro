"""
Testes FIN-RECORRENCIA-1 — geracao explicita de recorrencias e faturas.

Cluster PostgreSQL descartavel com tabelas do Flask, migrations de supabase/ e o
cenario FICTICIO de tests/supabase_local.py (semear_recorrencias). Cada teste que
grava usa uma COPIA do banco semeado (create database ... template), entao a ordem
dos testes nao importa.

Comparacao com o Flask: o mesmo estado inicial e gerado pelo Flask real
(GET /api/despesas/?mes_referencia=, em subprocesso, com a baixa automatica de
debito neutralizada) e pelo novo motor. Cada divergencia precisa estar
classificada em DIVERGENCIAS_INTENCIONAIS; qualquer outra e regressao.
"""
import itertools
import json
import os
import subprocess
import sys
import threading
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tests.supabase_local import (
    PERFIS,
    USUARIO_A,
    USUARIO_B,
    ClusterLocal,
    claims_usuario,
    encontrar_pg_bin,
    semear_recorrencias,
)

psycopg2 = pytest.importorskip('psycopg2')
import psycopg2.extras  # noqa: E402
from psycopg2 import errors  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PG_BIN = encontrar_pg_bin()
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

ID = {chave: perfil['id'] for chave, perfil in PERFIS.items()}
MES = '2027-03-01'
NS_FLASK = uuid.UUID('7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c')
CONTAS_PRE = {960, 961}
LANCAMENTOS_PRE = {970}
D = date


def _meses(*pares):
    return [D(a, m, 1) for a, m in pares]


# Toda divergencia entre o que o Flask gera e o que o novo motor gera, a partir do
# mesmo estado, com a justificativa. Nao exigimos equivalencia com defeitos conhecidos.
DIVERGENCIAS_INTENCIONAIS = {
    **{('CONTA', 901, m): 'CORRECAO D5: dia contratual 31 preservado (Flask deriva para 28)'
       for m in _meses((2027, 3), (2027, 4))},
    **{('LANCAMENTO_CARTAO', 906, m): 'CORRECAO D5: dia contratual da compra recorrente (Flask deriva para 28)'
       for m in _meses((2027, 3), (2027, 4))},
    ('CONTA', 902, D(2027, 2, 1)): 'CORRECAO: duplicata evitada (vencimento editado reconhecido pela competencia)',
    **{('CONTA', 904, m): 'CORRECAO D4: recorrencia inativa nao gera'
       for m in _meses((2027, 1), (2027, 2), (2027, 3), (2027, 4))},
    ('CONTA', 907, D(2028, 1, 1)): 'CORRECAO D2: nao gera competencia alem do mes seguinte',
    ('FATURA', 910, D(2027, 4, 1)): 'CORRECAO D6: fatura com vencimento 31 em mes de 30 dias (Flask nao cria)',
    **{('CONTA', 920, m): 'CORRECAO D7: falha isolada por item (Flask desfaz o perfil inteiro)'
       for m in _meses((2027, 3), (2027, 4))},
    **{('FATURA', 930, m): 'CORRECAO D7: falha isolada por item (Flask desfaz o perfil inteiro)'
       for m in _meses((2027, 3), (2027, 4))},
    **{('CONTA', 908, m): 'FORA DO ESCOPO D3: recorrencia semanal'
       for m in _meses((2027, 1), (2027, 2), (2027, 3), (2027, 4))},
}

_SCRIPT_FLASK = """
import sys
import backend.services.debito_automatico_service as debito
debito.executar_baixa_debito_automatico = lambda *a, **k: None  # pagamento fora do escopo (D9)
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    u = Usuario(email='flask.recorrencia@teste.local', nome='Recorrencia', ativo=True)
    u.definir_senha('Senha-ficticia-recorrencia-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.recorrencia@teste.local', 'senha': 'Senha-ficticia-recorrencia-2026'}).status_code == 302
for perfil_id in sys.argv[2:]:
    assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(perfil_id)}).status_code == 200
    r = c.get('/api/despesas/?mes_referencia=' + sys.argv[1])
    assert r.status_code == 200, r.data[:300]
print('FLASK OK')
"""

_copias = itertools.count()


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    with ClusterLocal(PG_BIN, tmp_path_factory.mktemp('recorrencia')) as c:
        c.preparar(contas=False)
        conn = c.conectar()
        with conn.cursor() as cur:
            semear_recorrencias(cur)
        conn.close()
        yield c


def _dsn(cluster, banco):
    return f'postgresql://postgres@127.0.0.1:{cluster.porta}/{banco}'


def copiar(cluster):
    """Novo banco identico ao semeado (o banco `postgres` nunca e alterado pelos testes)."""
    nome = f'copia_{next(_copias)}'
    conn = psycopg2.connect(_dsn(cluster, 'template1'))
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'create database {nome} template postgres')
    conn.close()
    return _dsn(cluster, nome)


@pytest.fixture
def banco(cluster):
    return copiar(cluster)


def chamar(dsn, usuario, sql, params=()):
    """Executa como `authenticated` (claims do usuario), numa transacao propria."""
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            if usuario is None:
                cur.execute('set local role anon')
            else:
                cur.execute('set local role authenticated')
                cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims_usuario(usuario)),))
            cur.execute(sql, params)
            return cur.fetchone()[0] if cur.description else None
    finally:
        conn.close()


def sql(dsn, comando, params=()):
    """Como postgres (administrador do teste)."""
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(comando, params)
            return [dict(x) for x in cur.fetchall()] if cur.description else None
    finally:
        conn.close()


def previa(dsn, perfil='PESSOAL', usuario=USUARIO_A, mes=MES):
    return chamar(dsn, usuario, 'select financeiro.previa_geracao(%s, %s)', (ID.get(perfil, perfil), mes))


def gerar(dsn, total, perfil='PESSOAL', usuario=USUARIO_A, mes=MES, dispensar=()):
    return chamar(dsn, usuario, 'select financeiro.gerar_mes(%s, %s, %s, %s)',
                  (ID.get(perfil, perfil), mes, total, json.dumps(list(dispensar))))


def gerar_confirmado(dsn, perfil='PESSOAL', usuario=USUARIO_A, mes=MES, dispensar=()):
    """Fluxo da tela: previa -> confirmacao -> geracao com o total confirmado."""
    return gerar(dsn, previa(dsn, perfil, usuario, mes)['a_gerar'], perfil, usuario, mes, dispensar)


def contas_do_item(dsn, item):
    return sql(dsn, 'select * from public.conta where item_despesa_id = %s order by data_vencimento, id', (item,))


def lancamentos_do_item(dsn, item):
    return sql(dsn, 'select * from public.lancamento_agregado where item_despesa_id = %s order by mes_fatura, id', (item,))


def faturas_do_cartao(dsn, cartao):
    return sql(dsn, 'select * from public.conta where item_despesa_id = %s and is_fatura_cartao order by cartao_competencia',
               (cartao,))


def contagens(dsn):
    linhas = sql(dsn, """select (select count(*) from public.conta) as contas,
                                (select count(*) from public.lancamento_agregado) as lancamentos,
                                (select count(*) from financeiro.recorrencia_competencia) as registro,
                                (select count(*) from financeiro.geracao_execucao) as execucoes""")
    return linhas[0]


def digital(dsn, tabelas=('item_despesa', 'conta_bancaria', 'movimento_financeiro', 'cartao_categoria_limite',
                          'config_agregador', 'categoria', 'categoria_cartao', 'perfil_financeiro')):
    saida = {}
    for tabela in tabelas:
        saida[tabela] = sql(dsn, f"select count(*) as n, coalesce(md5(string_agg(t::text, '|' order by t.id)), '') as h "
                                 f"from public.{tabela} t")[0]
    return saida


def preexistentes(dsn):
    return (sql(dsn, 'select md5(t::text) as h from public.conta t where id = any(%s) order by id', (list(CONTAS_PRE),)),
            sql(dsn, 'select md5(t::text) as h from public.lancamento_agregado t where id = any(%s) order by id',
                (list(LANCAMENTOS_PRE),)))


def rodar_flask(dsn, mes='2027-03', perfis=('PESSOAL', 'EMPRESA', 'PERFIL_B')):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT_FLASK, mes, *(str(ID[p]) for p in perfis)],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and 'FLASK OK' in r.stdout, r.stderr[-2000:]


def registros_novos(dsn, ignorar_contas=(), ignorar_lancamentos=()):
    """{(natureza, item, competencia): [linha sem id/criado_em, ...]} das linhas fora dos conjuntos ignorados."""
    saida = defaultdict(list)
    for c in sql(dsn, 'select * from public.conta'):
        if c['id'] in ignorar_contas:
            continue
        chave = ('FATURA', c['item_despesa_id'], c['cartao_competencia']) if c['is_fatura_cartao'] \
            else ('CONTA', c['item_despesa_id'], c['mes_referencia'])
        saida[chave].append(tuple(sorted((k, v) for k, v in c.items() if k not in ('id', 'criado_em'))))
    for l in sql(dsn, 'select * from public.lancamento_agregado'):
        if l['id'] in ignorar_lancamentos:
            continue
        saida[('LANCAMENTO_CARTAO', l['item_despesa_id'], l['mes_fatura'])].append(
            tuple(sorted((k, v) for k, v in l.items() if k not in ('id', 'criado_em')))
        )
    return {k: sorted(v, key=repr) for k, v in saida.items()}


def ids(dsn, tabela):
    return {x['id'] for x in sql(dsn, f'select id from public.{tabela}')}


# ---------------------------------------------------------------------------
# Comparacao com o Flask (mesmo estado inicial, dois motores)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def comparacao(cluster):
    dsn_flask, dsn_novo = copiar(cluster), copiar(cluster)
    rodar_flask(dsn_flask)
    flask = registros_novos(dsn_flask, CONTAS_PRE, LANCAMENTOS_PRE)
    # No novo motor, a Empresa precisa de quem a gerencie (no cenario, A e LEITOR).
    sql(dsn_novo, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true "
                  "where perfil_financeiro_id = %s", (ID['EMPRESA'],))
    for perfil, usuario in (('PESSOAL', USUARIO_A), ('EMPRESA', USUARIO_A), ('PERFIL_B', USUARIO_B)):
        gerar_confirmado(dsn_novo, perfil, usuario)
    novo = registros_novos(dsn_novo, CONTAS_PRE, LANCAMENTOS_PRE)
    return {'dsn_flask': dsn_flask, 'dsn_novo': dsn_novo, 'flask': flask, 'novo': novo}


def test_toda_divergencia_com_o_flask_e_correcao_intencional_classificada(comparacao):
    flask, novo = comparacao['flask'], comparacao['novo']
    divergentes = {k for k in set(flask) | set(novo) if flask.get(k) != novo.get(k)}
    nao_classificadas = divergentes - set(DIVERGENCIAS_INTENCIONAIS)
    assert not nao_classificadas, f'REGRESSAO (divergencia nao classificada): {sorted(nao_classificadas, key=repr)}'
    assert divergentes == set(DIVERGENCIAS_INTENCIONAIS), 'correcao esperada nao ocorreu'


def test_registros_iguais_ao_flask_onde_nao_ha_correcao(comparacao):
    flask, novo = comparacao['flask'], comparacao['novo']
    iguais = {k for k in set(flask) & set(novo) if flask[k] == novo[k]}
    esperadas = {('CONTA', 902, D(2026, 12, 1)), ('CONTA', 902, D(2027, 3, 1)), ('CONTA', 902, D(2027, 4, 1)),
                 ('CONTA', 901, D(2027, 1, 1)), ('CONTA', 901, D(2027, 2, 1)),
                 ('CONTA', 903, D(2026, 3, 1)), ('CONTA', 903, D(2027, 3, 1)),
                 ('LANCAMENTO_CARTAO', 906, D(2027, 2, 1)),
                 ('CONTA', 909, D(2027, 2, 1)), ('CONTA', 909, D(2027, 3, 1)), ('CONTA', 909, D(2027, 4, 1)),
                 ('FATURA', 910, D(2027, 3, 1)),
                 ('CONTA', 940, D(2027, 3, 1)), ('CONTA', 940, D(2027, 4, 1))}
    assert iguais == esperadas  # todos os campos, inclusive perfil NULL, debito, conta bancaria, compra_id


def test_flask_primeiro_registros_reconhecidos_sem_duplicar(comparacao, cluster):
    dsn = comparacao['dsn_flask']
    antes_contas, antes_lancs = ids(dsn, 'conta'), ids(dsn, 'lancamento_agregado')
    p = previa(dsn)
    # So falta o que o Flask nao consegue criar: a fatura de abril (dia 31).
    assert [(i['natureza'], i['item_id'], i['competencia']) for i in p['itens']] == [('FATURA', 910, '2027-04-01')]
    r = gerar(dsn, p['a_gerar'])
    assert r['criadas'] == {'contas': 0, 'lancamentos': 0, 'faturas': 1, 'total': 1}
    assert ids(dsn, 'lancamento_agregado') == antes_lancs
    novas = ids(dsn, 'conta') - antes_contas
    assert [x['item_despesa_id'] for x in sql(dsn, 'select * from public.conta where id = any(%s)', (list(novas),))] == [910]


def test_correcao_do_vencimento_nao_duplica_registro_antigo_do_flask(comparacao):
    dsn = comparacao['dsn_flask']
    gerar_confirmado(dsn)  # idempotente se o teste anterior ja gerou
    marco = [c['data_vencimento'] for c in contas_do_item(dsn, 901) if c['mes_referencia'] == D(2027, 3, 1)]
    assert marco == [D(2027, 3, 28)]  # mantido como o Flask gravou; nada de 31/03 a mais
    compras_marco = [l for l in lancamentos_do_item(dsn, 906) if l['mes_fatura'] == D(2027, 3, 1)]
    assert len(compras_marco) == 1


@pytest.fixture(scope='module')
def flask_depois_do_novo(cluster):
    """Novo motor gera (com uma competencia dispensada); depois o Flask navega no mesmo mes."""
    dsn = copiar(cluster)
    gerar_confirmado(dsn, dispensar=[{'natureza': 'CONTA', 'item_id': 902, 'competencia': MES}])
    contas, lancs = ids(dsn, 'conta'), ids(dsn, 'lancamento_agregado')
    rodar_flask(dsn, perfis=('PESSOAL',))
    return {'dsn': dsn, 'flask': registros_novos(dsn, contas, lancs)}


def test_incompatibilidade_documentada_flask_recria_dispensada_e_duplica_corrigidas(flask_depois_do_novo):
    """Evidencia do item 6 do contrato: enquanto o Flask gerar por GET, ele desfaz as correcoes."""
    criadas = flask_depois_do_novo['flask']
    datas = {k: [dict(linha)['data_vencimento' if k[0] != 'LANCAMENTO_CARTAO' else 'data_compra'] for linha in v]
             for k, v in criadas.items()}
    assert datas[('CONTA', 902, D(2027, 3, 1))] == [D(2027, 3, 10)]   # competencia dispensada recriada
    assert datas[('CONTA', 901, D(2027, 3, 1))] == [D(2027, 3, 28)]   # duplicata da conta de 31/03
    assert datas[('CONTA', 901, D(2027, 4, 1))] == [D(2027, 4, 28)]   # duplicata da conta de 30/04
    assert len(datas[('CONTA', 904, D(2027, 3, 1))]) == 1             # inativa volta a gerar
    # Compras de cartao NAO duplicam: o compra_id deterministico e o mesmo nos dois motores.
    assert not any(k[0] == 'LANCAMENTO_CARTAO' for k in criadas)
    # Faturas tambem nao: a identidade e cartao + competencia.
    assert not any(k[0] == 'FATURA' for k in criadas)


@pytest.mark.xfail(strict=True, reason='Item 6 do contrato: exige escritor unico (o GET do Flask ainda gera). '
                                       'Ver docs/FIN_RECORRENCIA_1_CONTRATO.md, secao "Transicao".')
def test_flask_nao_recria_competencias_dispensadas_nem_corrigidas(flask_depois_do_novo):
    criadas = flask_depois_do_novo['flask']
    assert not {('CONTA', 902, D(2027, 3, 1)), ('CONTA', 901, D(2027, 3, 1)), ('CONTA', 901, D(2027, 4, 1))} & set(criadas)


# ---------------------------------------------------------------------------
# Previa e confirmacao (D1, D2)
# ---------------------------------------------------------------------------

def test_previa_e_somente_leitura_e_informa_competencias_e_registros(banco):
    antes = (contagens(banco), digital(banco), preexistentes(banco))
    p = previa(banco)
    assert (contagens(banco), digital(banco), preexistentes(banco)) == antes
    assert p['pode_gerar'] is True
    assert (p['a_gerar'], p['existentes'], p['rejeitadas'], p['inativas'], p['dispensadas']) == (17, 3, 3, 1, 0)
    assert p['competencias'] == ['2026-03-01', '2026-12-01', '2027-01-01', '2027-02-01', '2027-03-01', '2027-04-01']
    assert p['retroativo'] is True and p['extenso'] is True
    assert len(p['itens']) == 17


def test_mes_sem_lacunas_nao_e_extenso(banco):
    gerar_confirmado(banco)
    p = previa(banco, mes='2027-04-01')
    assert p['competencias'] == ['2027-05-01']
    assert (p['retroativo'], p['extenso']) == (False, False)


def test_previa_desatualizada_nao_grava_nada(banco):
    antes = contagens(banco)
    with pytest.raises(errors.RaiseException, match='previa mudou'):
        gerar(banco, 5)
    assert contagens(banco) == antes


def test_dispensa_fora_da_previa_e_recusada_sem_gravar(banco):
    antes = contagens(banco)
    total = previa(banco)['a_gerar']
    for invalida in ({'natureza': 'FATURA', 'item_id': 910, 'competencia': MES},
                     {'natureza': 'CONTA', 'item_id': 902, 'competencia': '2027-01-01'},  # ja existe
                     {'natureza': 'CONTA', 'item_id': 920, 'competencia': MES}):          # outro perfil
        with pytest.raises(errors.InvalidParameterValue):
            gerar(banco, total, dispensar=[invalida])
    assert contagens(banco) == antes


# ---------------------------------------------------------------------------
# Regras de geracao (D3-D6)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('competencia,dia,esperado', [
    ('2027-01-01', 31, '2027-01-31'), ('2027-02-01', 31, '2027-02-28'), ('2027-03-01', 31, '2027-03-31'),
    ('2027-04-01', 31, '2027-04-30'), ('2028-02-01', 31, '2028-02-29'), ('2028-02-01', 30, '2028-02-29'),
    ('2027-02-01', 29, '2027-02-28'), ('2027-03-01', 15, '2027-03-15'),
])
def test_dia_contratual(cluster, competencia, dia, esperado):
    assert sql(_dsn(cluster, 'postgres'), 'select financeiro.dia_contratual(%s, %s)::text as d',
               (competencia, dia))[0]['d'] == esperado


def test_vencimento_31_volta_ao_dia_contratual_depois_de_fevereiro(banco):
    gerar_confirmado(banco)
    assert [c['data_vencimento'] for c in contas_do_item(banco, 901)] == \
        [D(2027, 1, 31), D(2027, 2, 28), D(2027, 3, 31), D(2027, 4, 30)]
    assert [l['data_compra'] for l in lancamentos_do_item(banco, 906)] == \
        [D(2027, 1, 31), D(2027, 2, 28), D(2027, 3, 31), D(2027, 4, 30)]  # janeiro e o legado preexistente


def test_fevereiro_de_ano_bissexto(banco):
    gerar_confirmado(banco, mes='2028-02-01')
    assert [c['data_vencimento'] for c in contas_do_item(banco, 907)] == [D(2028, 1, 31), D(2028, 2, 29), D(2028, 3, 31)]
    assert [f['data_vencimento'] for f in faturas_do_cartao(banco, 910)] == [D(2028, 2, 29), D(2028, 3, 31)]
    assert [c['data_vencimento'] for c in contas_do_item(banco, 901)][12:15] == \
        [D(2028, 1, 31), D(2028, 2, 29), D(2028, 3, 31)]


def test_recorrencia_anual_so_no_mes_de_aniversario(banco):
    gerar_confirmado(banco)
    assert [(c['mes_referencia'], c['data_vencimento']) for c in contas_do_item(banco, 903)] == \
        [(D(2026, 3, 1), D(2026, 3, 15)), (D(2027, 3, 1), D(2027, 3, 15))]


def test_lacunas_retroativas_preenchidas_sem_duplicar_existentes(banco):
    gerar_confirmado(banco)
    escola = contas_do_item(banco, 902)
    assert [(c['mes_referencia'], c['data_vencimento']) for c in escola] == [
        (D(2026, 12, 1), D(2026, 12, 10)), (D(2027, 1, 1), D(2027, 1, 10)), (D(2027, 2, 1), D(2027, 2, 15)),
        (D(2027, 3, 1), D(2027, 3, 10)), (D(2027, 4, 1), D(2027, 4, 10))]
    assert {c['id'] for c in escola} >= CONTAS_PRE


def test_campos_da_conta_gerada(banco):
    gerar_confirmado(banco)
    conta = next(c for c in contas_do_item(banco, 902) if c['mes_referencia'] == D(2027, 3, 1))
    conta_bancaria = sql(banco, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']
    assert (conta['perfil_financeiro_id'], conta['descricao'], conta['valor'], conta['status_pagamento'],
            conta['data_pagamento'], conta['debito_automatico'], conta['conta_bancaria_id'], conta['observacoes'],
            conta['is_fatura_cartao']) == \
        (ID['PESSOAL'], 'Escola', Decimal('800.00'), 'Pendente', None, True, conta_bancaria, 'Mensalidade escolar', False)
    legado = contas_do_item(banco, 909)
    assert {c['perfil_financeiro_id'] for c in legado} == {None}  # legado sem perfil continua do Pessoal


def test_inativa_nao_gera_e_inativacao_preserva_historico(banco):
    gerar_confirmado(banco)
    assert contas_do_item(banco, 904) == []
    historico = contas_do_item(banco, 909)
    sql(banco, 'update public.item_despesa set ativo = false where id = 909')
    p = previa(banco, mes='2027-06-01')
    assert 909 not in {i['item_id'] for i in p['itens']}
    gerar(banco, p['a_gerar'], mes='2027-06-01')
    assert contas_do_item(banco, 909) == historico


def test_faturas_e_compras_recorrentes_do_cartao(banco):
    gerar_confirmado(banco)
    faturas = faturas_do_cartao(banco, 910)
    assert [(f['cartao_competencia'], f['data_vencimento'], f['descricao']) for f in faturas] == [
        (D(2027, 3, 1), D(2027, 3, 31), 'Fatura Cartao Teste - 03/2027'),
        (D(2027, 4, 1), D(2027, 4, 30), 'Fatura Cartao Teste - 04/2027')]
    for f in faturas:  # planejado: so o limite ativo do perfil (500); inativo e perfil NULL fora, como no Flask
        assert (f['valor'], f['valor_planejado'], f['valor_executado'], f['status_pagamento'], f['mes_referencia']) == \
            (Decimal('500.00'), Decimal('500.00'), Decimal('0.00'), 'Pendente', f['cartao_competencia'])
    compras = lancamentos_do_item(banco, 906)
    assert [l['id'] for l in compras][0] == 970  # legado reconhecido: janeiro nao duplicou
    for l in compras[1:]:
        assert l['compra_id'] == str(uuid.uuid5(NS_FLASK, f"906-{l['mes_fatura'].isoformat()}"))
        assert (l['cartao_id'], l['categoria_id'], l['categoria_cartao_id'], l['is_recorrente'], l['valor']) == \
            (910, 952, 961, True, Decimal('39.90'))
    assert faturas_do_cartao(banco, 911) == []


def test_itens_invalidos_sao_rejeitados_com_motivo_sem_impedir_os_validos(banco):
    r = gerar_confirmado(banco, 'PERFIL_B', USUARIO_B)
    assert r['criadas'] == {'contas': 2, 'lancamentos': 0, 'faturas': 2, 'total': 4}
    motivos = {(x['item_id'], x['motivo']) for x in r['rejeicoes']}
    assert motivos == {(921, 'Sem valor valido'), (922, 'Sem categoria')}
    assert [c['data_vencimento'] for c in contas_do_item(banco, 920)] == [D(2027, 3, 5), D(2027, 4, 5)]
    assert contas_do_item(banco, 921) == [] and lancamentos_do_item(banco, 922) == []


# ---------------------------------------------------------------------------
# Competencias dispensadas e registros removidos (D5)
# ---------------------------------------------------------------------------

def test_competencia_dispensada_permanece_dispensada(banco):
    dispensa = {'natureza': 'CONTA', 'item_id': 902, 'competencia': MES, 'motivo': 'Ferias escolares'}
    r = gerar_confirmado(banco, dispensar=[dispensa])
    assert (r['criadas']['total'], r['dispensadas_agora']) == (16, 1)
    marco = [c for c in contas_do_item(banco, 902) if c['mes_referencia'] == D(2027, 3, 1)]
    assert marco == []
    for mes in (MES, '2027-05-01', '2027-08-01'):
        p = previa(banco, mes=mes)
        assert ('CONTA', 902, MES) not in {(i['natureza'], i['item_id'], i['competencia']) for i in p['itens']}
        gerar(banco, p['a_gerar'], mes=mes)
    assert [c for c in contas_do_item(banco, 902) if c['mes_referencia'] == D(2027, 3, 1)] == []
    assert previa(banco)['dispensados'] == [
        {'natureza': 'CONTA', 'item_id': 902, 'nome': 'Escola', 'competencia': MES, 'motivo': 'Ferias escolares'}]


def test_reativar_competencia_dispensada(banco):
    gerar_confirmado(banco, dispensar=[{'natureza': 'CONTA', 'item_id': 902, 'competencia': MES}])
    assert chamar(banco, USUARIO_A, 'select financeiro.reativar_competencia(%s, %s, %s, %s)',
                  (ID['PESSOAL'], 'CONTA', 902, MES)) is True
    p = previa(banco)
    assert [(i['natureza'], i['item_id'], i['competencia']) for i in p['itens']] == [('CONTA', 902, MES)]
    gerar(banco, 1)
    assert [c['data_vencimento'] for c in contas_do_item(banco, 902) if c['mes_referencia'] == D(2027, 3, 1)] == \
        [D(2027, 3, 10)]


def test_conta_removida_apos_geracao_vira_dispensada_e_pode_ser_reativada(banco):
    gerar_confirmado(banco)
    conta = next(c for c in contas_do_item(banco, 901) if c['mes_referencia'] == D(2027, 3, 1))
    sql(banco, 'delete from public.conta where id = %s', (conta['id'],))
    p = previa(banco)
    assert p['a_gerar'] == 0
    assert {(x['item_id'], x['competencia'], x['motivo']) for x in p['dispensados']} == \
        {(901, MES, 'Registro gerado foi removido; nao sera recriado')}
    assert chamar(banco, USUARIO_A, 'select financeiro.reativar_competencia(%s, %s, %s, %s)',
                  (ID['PESSOAL'], 'CONTA', 901, MES)) is True
    assert previa(banco)['a_gerar'] == 1


# ---------------------------------------------------------------------------
# Idempotencia, concorrencia e atomicidade (D7)
# ---------------------------------------------------------------------------

def test_executar_duas_vezes_nao_duplica(banco):
    total = previa(banco)['a_gerar']
    primeira = gerar(banco, total)
    depois = contagens(banco)
    segunda = gerar(banco, total)
    assert primeira['criadas']['total'] == 17
    assert segunda['criadas']['total'] == 0 and segunda['execucao_id'] is None
    assert contagens(banco) == depois


def test_duas_solicitacoes_concorrentes_nao_duplicam(banco):
    total = previa(banco)['a_gerar']
    barreira = threading.Barrier(2)
    resultados, falhas = [], []

    def executar():
        try:
            barreira.wait(timeout=10)
            resultados.append(gerar(banco, total))
        except Exception as exc:  # noqa: BLE001
            falhas.append(exc)

    tarefas = [threading.Thread(target=executar) for _ in range(2)]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join(timeout=60)
    assert falhas == []
    assert sorted(r['criadas']['total'] for r in resultados) == [0, 17]
    duplicadas = sql(banco, """select item_despesa_id, mes_referencia, count(*) from public.conta
                                where not coalesce(is_fatura_cartao, false) group by 1, 2 having count(*) > 1""")
    assert duplicadas == []
    assert sql(banco, 'select count(*) as n from public.lancamento_agregado')[0]['n'] == 4


def test_falha_no_meio_desfaz_tudo(banco):
    sql(banco, """create function public.falha_injetada() returns trigger language plpgsql as $$
                  begin if new.descricao = 'Streaming' then raise exception 'falha injetada'; end if; return new; end $$;
                  create trigger falha_injetada before insert on public.lancamento_agregado
                  for each row execute function public.falha_injetada()""")
    antes = (contagens(banco), preexistentes(banco))
    with pytest.raises(errors.RaiseException, match='falha injetada'):
        gerar(banco, previa(banco)['a_gerar'])
    assert (contagens(banco), preexistentes(banco)) == antes


def test_relatorio_verificavel(banco):
    r = gerar_confirmado(banco, dispensar=[{'natureza': 'CONTA', 'item_id': 902, 'competencia': MES}])
    gravado = sql(banco, 'select * from financeiro.geracao_execucao where id = %s', (r['execucao_id'],))[0]
    assert gravado['resumo'] == r and gravado['perfil_financeiro_id'] == ID['PESSOAL']
    assert str(gravado['user_id']) == USUARIO_A['id'] and gravado['mes'] == D(2027, 3, 1)
    assert r['criadas'] == {'contas': 11, 'lancamentos': 3, 'faturas': 2, 'total': 16}
    assert (r['existentes'], r['dispensadas'], r['rejeitadas']) == (3, 1, 3)
    for registro in r['registros']:
        tabela = 'lancamento_agregado' if registro['natureza'] == 'LANCAMENTO_CARTAO' else 'conta'
        linha = sql(banco, f'select * from public.{tabela} where id = %s', (registro['registro_id'],))[0]
        assert linha['item_despesa_id'] == registro['item_id']
    identidade = sql(banco, 'select situacao, count(*) as n from financeiro.recorrencia_competencia group by 1 order by 1')
    assert identidade == [{'situacao': 'DISPENSADA', 'n': 1}, {'situacao': 'GERADA', 'n': 14}]


# ---------------------------------------------------------------------------
# Sem pagamento, sem movimento, historico preservado (D9)
# ---------------------------------------------------------------------------

def test_sem_pagamento_baixa_ou_movimento_bancario(banco):
    antes = digital(banco)
    gerar_confirmado(banco)
    assert digital(banco) == antes  # inclui movimento_financeiro e conta_bancaria (saldo)
    novas = sql(banco, 'select * from public.conta where id <> all(%s)', (list(CONTAS_PRE),))
    assert novas and all(c['status_pagamento'] == 'Pendente' and c['data_pagamento'] is None for c in novas)


def test_historico_financeiro_preservado(banco):
    antes = (preexistentes(banco), digital(banco))
    gerar_confirmado(banco)
    gerar_confirmado(banco, mes='2027-09-01')
    assert (preexistentes(banco), digital(banco)) == antes  # o Flask grava compra_id no legado; o novo motor nao


# ---------------------------------------------------------------------------
# Autorizacao (D8)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('usuario,perfil', [
    (USUARIO_B, 'PESSOAL'),      # perfil de outro usuario
    (USUARIO_A, 'PERFIL_B'),
    (USUARIO_A, 'INATIVO_A'),    # vinculo com gestao, mas perfil inativo
    (USUARIO_A, 99999),          # inexistente
])
def test_previa_e_geracao_negadas_fora_do_perfil(banco, usuario, perfil):
    with pytest.raises(errors.InsufficientPrivilege, match='Perfil financeiro nao autorizado'):
        previa(banco, perfil, usuario)
    with pytest.raises(errors.InsufficientPrivilege, match='Perfil financeiro nao autorizado'):
        gerar(banco, 1, perfil, usuario)


def test_leitor_ve_a_previa_mas_nao_gera(banco):
    p = previa(banco, 'EMPRESA')
    assert (p['pode_gerar'], p['a_gerar']) == (False, 2)
    antes = contagens(banco)
    with pytest.raises(errors.InsufficientPrivilege):
        gerar(banco, 2, 'EMPRESA')
    with pytest.raises(errors.InsufficientPrivilege):
        chamar(banco, USUARIO_A, 'select financeiro.reativar_competencia(%s, %s, %s, %s)', (ID['EMPRESA'], 'CONTA', 940, MES))
    assert contagens(banco) == antes


def test_titular_sem_permissao_explicita_de_gestao_nao_gera(banco):
    sql(banco, 'update financeiro.perfil_acesso set pode_gerir = false where perfil_financeiro_id = %s', (ID['PERFIL_B'],))
    assert previa(banco, 'PERFIL_B', USUARIO_B)['pode_gerar'] is False
    with pytest.raises(errors.InsufficientPrivilege):
        gerar(banco, 4, 'PERFIL_B', USUARIO_B)


def test_leitor_nao_pode_receber_permissao_de_gestao(banco):
    with pytest.raises(errors.CheckViolation):
        sql(banco, 'update financeiro.perfil_acesso set pode_gerir = true where perfil_financeiro_id = %s', (ID['EMPRESA'],))


def test_reativar_item_de_outro_perfil_negado(banco):
    gerar_confirmado(banco, 'PERFIL_B', USUARIO_B)
    with pytest.raises(errors.InsufficientPrivilege):  # item 920 e do Perfil B, pedido pelo Pessoal
        chamar(banco, USUARIO_A, 'select financeiro.reativar_competencia(%s, %s, %s, %s)', (ID['PESSOAL'], 'CONTA', 920, MES))
    with pytest.raises(errors.InsufficientPrivilege):
        chamar(banco, USUARIO_B, 'select financeiro.reativar_competencia(%s, %s, %s, %s)', (ID['PESSOAL'], 'CONTA', 901, MES))


@pytest.mark.parametrize('comando', [
    "select financeiro.previa_geracao(101, '2027-03-01')",
    "select financeiro.gerar_mes(101, '2027-03-01', 17, '[]')",
    "select financeiro.reativar_competencia(101, 'CONTA', 902, '2027-03-01')",
])
def test_anonimo_nao_executa(banco, comando):
    with pytest.raises(errors.InsufficientPrivilege, match='permission denied'):
        chamar(banco, None, comando)


@pytest.mark.parametrize('comando', [
    "select count(*) from financeiro.plano_recorrencia(101, '2027-03-01')",
    "select financeiro.dia_contratual('2027-03-01', 31)",
    'select count(*) from financeiro.recorrencia_competencia',
    'select count(*) from financeiro.geracao_execucao',
    "insert into financeiro.recorrencia_competencia (item_despesa_id, natureza, competencia, situacao) "
    "values (901, 'CONTA', '2027-03-01', 'DISPENSADA')",
    "insert into public.conta (item_despesa_id, mes_referencia, descricao, valor, data_vencimento) "
    "values (901, '2027-03-01', 'x', 1, '2027-03-01')",
])
def test_navegador_nao_acessa_plano_interno_nem_tabelas(banco, comando):
    with pytest.raises(errors.InsufficientPrivilege, match='permission denied'):
        chamar(banco, USUARIO_A, comando)
