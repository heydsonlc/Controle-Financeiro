"""
Testes FIN-FIDELIDADE-CONTRATOS-1 (fase 1) — leitura da tela original de Financiamentos (migration 20261110090000).

Fidelidade: o PROPRIO Flask cria financiamentos FICTICIOS (SAC e PRICE, com seguro) no cluster descartavel, paga uma
parcela e faz uma amortizacao extraordinaria; depois GET /api/financiamentos e GET /api/financiamentos/<id> do Flask sao
comparados campo a campo com financiamentos_tela / financiamento_tela (chamadas como o navegador). So leitura.
"""
import json
import os
import subprocess
import sys

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    ROOT,
    USUARIO_A,
    USUARIO_B,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, PERFIL_B = ID['PESSOAL'], ID['PERFIL_B']

_SCRIPT = """
import json, sys
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    u = Usuario(email='flask.financiamento@teste.local', nome='Financiamento', ativo=True)
    u.definir_senha('Senha-ficticia-financiamento-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.financiamento@teste.local', 'senha': 'Senha-ficticia-financiamento-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
base = {'produto': 'Habitacional ficticio', 'valor_financiado': 120000, 'prazo_total_meses': 24,
        'taxa_juros_nominal_anual': 9.5, 'data_contrato': '2030-01-10', 'data_primeira_parcela': '2030-02-10',
        'seguro_tipo': 'fixo', 'valor_seguro_mensal': 35.5, 'taxa_administracao_fixa': 25,
        'vigencias_seguro': [{'competencia_inicio': '2030-02-01', 'valor_mensal': 35.5, 'observacoes': 'apolice ficticia'}]}
ids = []
for nome, sistema in (('Casa SAC (ficticio)', 'SAC'), ('Carro PRICE (ficticio)', 'PRICE')):
    r = c.post('/api/financiamentos', json={**base, 'nome': nome, 'sistema_amortizacao': sistema})
    assert r.status_code in (200, 201), r.data[:400]
    ids.append(r.get_json()['data']['id'])
# Historico: amortizacao extraordinaria no primeiro (o detalhe passa a sugerir a nova vigencia do seguro).
r = c.post(f'/api/financiamentos/{ids[0]}/amortizacao-extra', json={'data': '2030-04-15', 'valor': 5000, 'tipo': 'reduzir_parcela'})
saida = {'amortizacao': r.status_code, 'lista': c.get('/api/financiamentos').get_json(),
         'ativos': c.get('/api/financiamentos?ativo=true').get_json(),
         'detalhes': [c.get(f'/api/financiamentos/{i}').get_json() for i in ids]}
print('FLASK_JSON ' + json.dumps(saida))
"""


def flask(dsn, perfil):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT, str(perfil)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


def igual(flask_valor, novo, caminho=''):
    """Cada campo que o Flask devolve existe igual no novo (numeros com tolerancia de centavo; extras do novo ignorados)."""
    if isinstance(flask_valor, dict):
        assert isinstance(novo, dict), caminho
        for k, v in flask_valor.items():
            assert k in novo, f'{caminho}.{k} ausente'
            igual(v, novo[k], f'{caminho}.{k}')
    elif isinstance(flask_valor, list):
        assert isinstance(novo, list) and len(novo) == len(flask_valor), f'{caminho}: {len(flask_valor)} x {len(novo or [])}'
        for i, (a, b) in enumerate(zip(flask_valor, novo)):
            igual(a, b, f'{caminho}[{i}]')
    elif isinstance(flask_valor, (int, float)) and not isinstance(flask_valor, bool) and novo is not None:
        assert abs(float(flask_valor) - float(novo)) < 0.005, f'{caminho}: {flask_valor} x {novo}'
    elif isinstance(flask_valor, str) and isinstance(novo, str) and len(flask_valor) == 19 and flask_valor[10] == ' ':
        assert novo.replace('T', ' ')[:19] == flask_valor, f'{caminho}: {flask_valor} x {novo}'  # timestamp
    else:
        assert flask_valor == novo, f'{caminho}: {flask_valor!r} x {novo!r}'


@pytest.fixture(scope='module')
def cenario(cluster):  # noqa: F811
    dsn = copiar(cluster)
    return dsn, flask(dsn, PESSOAL)


def test_privilegios(cenario):
    dsn, _ = cenario
    for funcao, esperado in (('financeiro.financiamentos_tela(integer, boolean)', (True, False)),
                             ('financeiro.financiamento_tela(integer, integer)', (True, False)),
                             ('financeiro.financiamento_flask(public.financiamento)', (False, False)),
                             ('financeiro.vigencia_seguro_info(integer)', (False, False))):
        r = sql(dsn, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                     "has_function_privilege('anon', %s, 'execute') as n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == esperado, funcao


def test_lista_igual_ao_flask(cenario):
    dsn, saida = cenario
    assert saida['amortizacao'] in (200, 201)
    assert len(saida['lista']['data']) == 2
    igual(saida['lista']['data'], rpc(dsn, 'financiamentos_tela', PESSOAL, None), 'lista')
    igual(saida['ativos']['data'], rpc(dsn, 'financiamentos_tela', PESSOAL, True), 'ativos')
    assert rpc(dsn, 'financiamentos_tela', PESSOAL, False) == []


def test_detalhe_igual_ao_flask_com_parcelas_seguro_e_ajuste(cenario):
    dsn, saida = cenario
    for detalhe in saida['detalhes']:
        dados = detalhe['data']
        novo = rpc(dsn, 'financiamento_tela', PESSOAL, dados['id'])
        igual(dados, novo, f"detalhe {dados['nome']}")
        assert len(novo['parcelas']) == dados['total_parcelas'] > 0
    sac = saida['detalhes'][0]['data']
    assert sac['vigencia_seguro_info'] == rpc(dsn, 'financiamento_tela', PESSOAL, sac['id'])['vigencia_seguro_info']


def test_isolamento_e_nada_gravado(cenario):
    dsn, saida = cenario
    antes = sql(dsn, 'select (select count(*) from public.financiamento) f, (select count(*) from public.financiamento_parcela) p')[0]
    fid = saida['detalhes'][0]['data']['id']
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'financiamento_tela', PERFIL_B, fid, usuario=USUARIO_B)
    assert erro.value.diag.message_primary == 'Financiamento nao encontrado neste perfil'
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'financiamentos_tela', PESSOAL, None, usuario=USUARIO_B)
    assert erro.value.pgcode == '42501'
    assert rpc(dsn, 'financiamentos_tela', PERFIL_B, None, usuario=USUARIO_B) == []
    assert sql(dsn, 'select (select count(*) from public.financiamento) f, (select count(*) from public.financiamento_parcela) p')[0] == antes
    _ = USUARIO_A
