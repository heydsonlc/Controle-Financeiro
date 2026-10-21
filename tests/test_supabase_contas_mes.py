"""
Testes MOBILE-CONTAS-1 — contas do mes: equivalencia com o Flask e autorizacao.

Cluster PostgreSQL descartavel com tabelas do Flask, migrations de supabase/ e
dados FICTICIOS (tests/supabase_local.py: semear_perfis + semear_contas).

Equivalencia: o MESMO banco e lido pelo Flask real (GET /api/despesas/) e pela
fachada financeiro.contas_do_mes. Os efeitos colaterais do Flask sao isolados:
- a listagem e chamada SEM mes_referencia (nao ha geracao preguicosa) e filtrada
  por mes_competencia, como o proprio resumo do Flask faz;
- a baixa automatica de debito automatico e neutralizada no processo do Flask;
- uma impressao digital das tabelas financeiras prova que nada foi gravado.
"""
import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

import pytest

from tests.supabase_local import (
    CONTAS_MES_ESPERADO,
    PERFIS,
    USUARIO_A,
    USUARIO_B,
    ClusterLocal,
    PostgrestLocal,
    assinar_jwt,
    claims_usuario,
    encontrar_pg_bin,
    encontrar_postgrest,
)

psycopg2 = pytest.importorskip('psycopg2')
from psycopg2 import errors  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PG_BIN = encontrar_pg_bin()
POSTGREST_BIN = encontrar_postgrest()
SEGREDO_JWT = secrets.token_urlsafe(48)
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

ID = {chave: perfil['id'] for chave, perfil in PERFIS.items()}
DONO = {'PESSOAL': USUARIO_A, 'EMPRESA': USUARIO_A, 'PERFIL_B': USUARIO_B}
TABELAS_FINANCEIRAS = ['conta', 'lancamento_agregado', 'item_despesa', 'perfil_financeiro', 'cartao_categoria_limite',
                       'categoria', 'categoria_cartao', 'conta_bancaria', 'movimento_financeiro']

_SCRIPT_FLASK = """
import json, sys
import backend.services.debito_automatico_service as debito
debito.executar_baixa_debito_automatico = lambda *a, **k: None  # isola a baixa automatica (D2)
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    u = Usuario(email='flask.equivalencia@teste.local', nome='Equivalencia', ativo=True)
    u.definir_senha('Senha-ficticia-equivalencia-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.equivalencia@teste.local', 'senha': 'Senha-ficticia-equivalencia-2026'}).status_code == 302
saida = {}
for perfil_id in sys.argv[1:]:
    assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(perfil_id)}).status_code == 200
    r = c.get('/api/despesas/')  # sem mes_referencia: sem geracao preguicosa
    assert r.status_code == 200, r.data[:300]
    saida[perfil_id] = [{k: x.get(k) for k in ('id', 'valor', 'data_vencimento', 'pago', 'is_fatura_cartao', 'mes_competencia')}
                        for x in r.get_json()['data']]
print('FLASK ' + json.dumps(saida))
"""


def _digital(conn):
    with conn.cursor() as cur:
        partes = []
        for tabela in TABELAS_FINANCEIRAS:
            cur.execute(f"select count(*), coalesce(md5(string_agg(t::text, '|' order by t.id)), '') from public.{tabela} t")
            partes.append((tabela, *cur.fetchone()))
        return partes


@pytest.fixture(scope='module')
def ambiente(tmp_path_factory):
    with ClusterLocal(PG_BIN, tmp_path_factory.mktemp('contas_mes')) as cluster:
        cluster.preparar()
        conn = cluster.conectar()
        antes = _digital(conn)
        conn.close()

        env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': cluster.dsn()}
        env.pop('FLASK_ENV', None)
        r = subprocess.run([sys.executable, '-c', _SCRIPT_FLASK, *(str(v) for v in ID.values() if v != ID['INATIVO_A'])],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stderr[-2000:]
        flask = json.loads([l for l in r.stdout.splitlines() if l.startswith('FLASK ')][-1][6:])

        conn = cluster.conectar()
        depois = _digital(conn)
        conn.close()
        yield {'cluster': cluster, 'flask': flask, 'antes': antes, 'depois': depois}


def _como(conn, usuario):
    cur = conn.cursor()
    cur.execute('set local role authenticated')
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims_usuario(usuario)),))
    return cur


def _fachada(cluster, chave, mes):
    conn = cluster.conectar()
    conn.autocommit = False
    try:
        cur = _como(conn, DONO[chave])
        cur.execute('select * from financeiro.contas_do_mes(%s, %s)', (ID[chave], f'{mes}-01'))
        colunas = [d[0] for d in cur.description]
        return [dict(zip(colunas, linha)) for linha in cur.fetchall()]
    finally:
        conn.rollback()
        conn.close()


def _cent(valor):
    return Decimal(str(valor)).quantize(Decimal('0.01'))


CASOS = list(CONTAS_MES_ESPERADO)


# ---------------------------------------------------------------------------
# Isolamento dos efeitos colaterais do Flask
# ---------------------------------------------------------------------------

def test_flask_nao_gravou_nada_durante_a_comparacao(ambiente):
    assert ambiente['antes'] == ambiente['depois']


# ---------------------------------------------------------------------------
# Equivalencia com o Flask
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('chave,mes', CASOS)
def test_mesmas_contas_valores_e_situacao_de_pagamento_que_o_flask(ambiente, chave, mes):
    flask = {x['id']: x for x in ambiente['flask'][str(ID[chave])] if x['mes_competencia'] == mes}
    fachada = {x['id']: x for x in _fachada(ambiente['cluster'], chave, mes)}
    assert set(fachada) == set(flask)
    for cid, f in flask.items():
        m = fachada[cid]
        assert _cent(m['valor']) == _cent(f['valor']), f'conta {cid}: valor'
        assert m['data_vencimento'].isoformat() == f['data_vencimento'], f'conta {cid}: vencimento'
        assert (m['situacao'] == 'PAGA') is bool(f['pago']), f'conta {cid}: pago'
        assert (m['grupo'] == 'FATURA') is bool(f['is_fatura_cartao']), f'conta {cid}: grupo'


@pytest.mark.parametrize('chave,mes', CASOS)
def test_totais_iguais_ao_resumo_do_flask_e_ao_esperado(ambiente, chave, mes):
    flask = [x for x in ambiente['flask'][str(ID[chave])] if x['mes_competencia'] == mes]
    total_flask = sum(_cent(x['valor']) for x in flask)
    pago_flask = sum(_cent(x['valor']) for x in flask if x['pago'])
    fachada = _fachada(ambiente['cluster'], chave, mes)
    total = sum(_cent(x['valor']) for x in fachada)
    pago = sum(_cent(x['valor']) for x in fachada if x['situacao'] == 'PAGA')
    esperado = CONTAS_MES_ESPERADO[(chave, mes)]
    assert total == total_flask == Decimal(esperado['total'])
    assert pago == pago_flask == Decimal(esperado['pago'])


@pytest.mark.parametrize('chave,mes', CASOS)
def test_ordem_e_valor_de_cada_conta_como_esperado(ambiente, chave, mes):
    fachada = _fachada(ambiente['cluster'], chave, mes)
    esperado = CONTAS_MES_ESPERADO[(chave, mes)]
    assert [x['id'] for x in fachada if x['grupo'] == 'DESPESA'] == esperado['despesas']
    assert [x['id'] for x in fachada if x['grupo'] == 'FATURA'] == esperado['faturas']
    assert {x['id']: str(_cent(x['valor'])) for x in fachada} == esperado['valores']


# ---------------------------------------------------------------------------
# Regras financeiras especificas
# ---------------------------------------------------------------------------

def test_competencia_gravada_e_nao_o_mes_do_vencimento(ambiente):
    nov = {x['id']: x for x in _fachada(ambiente['cluster'], 'PESSOAL', '2026-11')}
    dez = {x['id'] for x in _fachada(ambiente['cluster'], 'PESSOAL', '2026-12')}
    assert nov[501]['data_vencimento'].isoformat() == '2026-12-05'  # vence em dezembro...
    assert 501 not in dez                                          # ...mas pertence a novembro


def test_fatura_pendente_usa_previsto_e_paga_usa_executado(ambiente):
    contas = {x['id']: x for x in _fachada(ambiente['cluster'], 'PESSOAL', '2026-11')}
    azul, verde = contas[509], contas[510]
    assert (_cent(azul['valor_executado']), _cent(azul['valor_previsto']), _cent(azul['valor'])) == \
        (Decimal('1220.00'), Decimal('1320.00'), Decimal('1320.00'))  # Mercado +100, Restaurantes +0, limite inativo fora
    assert (_cent(verde['valor_executado']), _cent(verde['valor'])) == (Decimal('120.00'), Decimal('120.00'))


def test_sem_dupla_contagem_das_compras_de_cartao(ambiente):
    contas = _fachada(ambiente['cluster'], 'PESSOAL', '2026-11')
    total = sum(_cent(x['valor']) for x in contas)
    compras = Decimal('1340.00')  # soma das compras de novembro nos dois cartoes
    assert total == Decimal('4390.50')
    assert total != total + compras
    assert all(x['grupo'] in ('DESPESA', 'FATURA') for x in contas)  # compras nunca viram linhas de conta


def test_situacao_paga_pendente_e_vencida(ambiente):
    jan = {x['id']: x['situacao'] for x in _fachada(ambiente['cluster'], 'PESSOAL', '2026-01')}
    assert jan == {504: 'VENCIDA', 505: 'VENCIDA', 506: 'PAGA', 512: 'PAGA'}  # 506 vencida no passado, mas paga
    nov = {x['id']: x['situacao'] for x in _fachada(ambiente['cluster'], 'PESSOAL', '2026-11')}
    assert nov[501] == 'PENDENTE' and nov[502] == 'PAGA'


def test_pessoal_inclui_legado_sem_perfil_e_empresa_nao(ambiente):
    pessoal = {x['id'] for x in _fachada(ambiente['cluster'], 'PESSOAL', '2026-11')}
    empresa = {x['id'] for x in _fachada(ambiente['cluster'], 'EMPRESA', '2026-11')}
    assert {502, 510} <= pessoal       # conta e fatura sem perfil
    assert not ({502, 510} & empresa)
    assert not (pessoal & empresa)


def test_detalhe_da_fatura_lista_as_compras_do_mes(ambiente):
    conn = ambiente['cluster'].conectar()
    conn.autocommit = False
    try:
        cur = _como(conn, USUARIO_A)
        cur.execute('select descricao, valor from financeiro.lancamentos_da_fatura(%s, %s)', (ID['PESSOAL'], 509))
        compras = cur.fetchall()
    finally:
        conn.rollback()
        conn.close()
    nomes = [n for n, _ in compras]
    assert sorted(nomes) == sorted(['Supermercado X', 'Supermercado Y', 'Restaurante Z', 'Posto',
                                    'Compra parcelada', 'Farmacia (legado)'])
    assert 'Supermercado dezembro' not in nomes
    assert sum(_cent(v) for _, v in compras) == Decimal('1220.00')


def test_aviso_de_mes_possivelmente_nao_gerado(ambiente):
    conn = ambiente['cluster'].conectar()
    conn.autocommit = False
    try:
        resultados = {}
        for chave, mes in (('PESSOAL', '2026-11'), ('PESSOAL', '2026-06'), ('PERFIL_B', '2026-06')):
            cur = _como(conn, DONO[chave])
            cur.execute('select financeiro.mes_pode_estar_incompleto(%s, %s)', (ID[chave], f'{mes}-01'))
            resultados[(chave, mes)] = cur.fetchone()[0]
            conn.rollback()
    finally:
        conn.close()
    assert resultados == {
        ('PESSOAL', '2026-11'): False,  # recorrencia e faturas presentes
        ('PESSOAL', '2026-06'): True,   # aluguel mensal sem conta e cartoes sem fatura: indicio
        ('PERFIL_B', '2026-06'): False,  # mes vazio sem indicio: sem aviso
    }


# ---------------------------------------------------------------------------
# Seguranca: somente leitura e autorizacao
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('funcao', [
    'financeiro.contas_do_mes(integer, date)',
    'financeiro.lancamentos_da_fatura(integer, integer)',
    'financeiro.mes_pode_estar_incompleto(integer, date)',
])
def test_funcoes_estaveis_seguras_e_restritas(ambiente, funcao):
    conn = ambiente['cluster'].conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(f"""select p.provolatile, p.prosecdef, array_to_string(p.proconfig, ','),
                                   has_function_privilege('anon', '{funcao}', 'EXECUTE'),
                                   has_function_privilege('authenticated', '{funcao}', 'EXECUTE')
                              from pg_proc p where p.oid = '{funcao}'::regprocedure""")
            volatilidade, definer, config, anon, autenticado = cur.fetchone()
    finally:
        conn.close()
    assert volatilidade == 's'  # STABLE: o PostgreSQL recusa escrita dentro da funcao
    assert definer is True and 'search_path=""' in config
    assert anon is False and autenticado is True


@pytest.mark.parametrize('usuario,chave', [
    (USUARIO_A, 'PERFIL_B'), (USUARIO_A, 'INATIVO_A'), (USUARIO_B, 'PESSOAL'), (USUARIO_B, 'EMPRESA'),
])
def test_contas_de_perfil_nao_autorizado_sao_recusadas(ambiente, usuario, chave):
    conn = ambiente['cluster'].conectar()
    conn.autocommit = False
    try:
        cur = _como(conn, usuario)
        with pytest.raises(errors.InsufficientPrivilege):
            cur.execute('select * from financeiro.contas_do_mes(%s, %s)', (ID[chave], '2026-11-01'))
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize('perfil,conta', [
    ('PESSOAL', 511),  # fatura da Empresa pedida pelo Pessoal
    ('PESSOAL', 501),  # despesa (nao e fatura)
    ('PESSOAL', 999999),
    ('EMPRESA', 509),  # fatura do Pessoal pedida pela Empresa
])
def test_detalhe_de_fatura_de_outro_perfil_ou_inexistente_e_recusado(ambiente, perfil, conta):
    conn = ambiente['cluster'].conectar()
    conn.autocommit = False
    try:
        cur = _como(conn, USUARIO_A)
        with pytest.raises(errors.InsufficientPrivilege):
            cur.execute('select * from financeiro.lancamentos_da_fatura(%s, %s)', (ID[perfil], conta))
    finally:
        conn.rollback()
        conn.close()


def test_anon_nao_executa(ambiente):
    conn = ambiente['cluster'].conectar()
    conn.autocommit = False
    try:
        cur = conn.cursor()
        cur.execute('set local role anon')
        with pytest.raises(errors.InsufficientPrivilege):
            cur.execute('select * from financeiro.contas_do_mes(%s, %s)', (ID['PESSOAL'], '2026-11-01'))
    finally:
        conn.rollback()
        conn.close()


def test_consultas_da_fachada_nao_alteram_nada(ambiente):
    conn = ambiente['cluster'].conectar()
    antes = _digital(conn)
    conn.close()
    for chave, mes in CASOS:
        _fachada(ambiente['cluster'], chave, mes)
    conn = ambiente['cluster'].conectar()
    assert _digital(conn) == antes
    conn.close()


# ---------------------------------------------------------------------------
# Camada REST
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def rest(ambiente, tmp_path_factory):
    if POSTGREST_BIN is None:
        pytest.skip('POSTGREST_BIN nao definido')
    with PostgrestLocal(POSTGREST_BIN, ambiente['cluster'], SEGREDO_JWT, tmp_path_factory.mktemp('pgrst_contas')) as p:
        yield p


def _rpc(rest, funcao, corpo, usuario=None):
    req = urllib.request.Request(f'{rest.url}/rpc/{funcao}', method='POST', data=json.dumps(corpo).encode())
    req.add_header('Content-Type', 'application/json')
    req.add_header('Content-Profile', 'financeiro')
    if usuario:
        req.add_header('Authorization', f'Bearer {assinar_jwt(claims_usuario(usuario), SEGREDO_JWT)}')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'null')


def test_rest_contas_do_mes_autorizado_e_campos_minimos(rest):
    status, corpo = _rpc(rest, 'contas_do_mes', {'p_perfil_id': ID['PESSOAL'], 'p_mes': '2026-11-01'}, USUARIO_A)
    assert status == 200 and len(corpo) == 5
    proibidos = {'conta_bancaria_id', 'observacoes', 'agencia', 'numero_conta', 'numero_cartao', 'codigo_seguranca'}
    assert not (set(corpo[0]) & proibidos)


def test_rest_perfil_alheio_e_anonimo_recusados(rest):
    assert _rpc(rest, 'contas_do_mes', {'p_perfil_id': ID['PERFIL_B'], 'p_mes': '2026-11-01'}, USUARIO_A)[0] == 403
    assert _rpc(rest, 'lancamentos_da_fatura', {'p_perfil_id': ID['PESSOAL'], 'p_conta_id': 511}, USUARIO_A)[0] == 403
    assert _rpc(rest, 'contas_do_mes', {'p_perfil_id': ID['PESSOAL'], 'p_mes': '2026-11-01'})[0] in (401, 403)
