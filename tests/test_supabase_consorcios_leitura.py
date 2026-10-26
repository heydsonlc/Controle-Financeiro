"""
Testes FIN-FIDELIDADE-CONTRATOS-1 (Consorcios, fase 1) — leitura dos consorcios (migration 20261116090000).

Fidelidade: o PROPRIO Flask cria, no cluster descartavel, consorcios FICTICIOS (com reajuste, contemplacao/premio, debito
automatico em conta bancaria e um sem meio de pagamento) e inativa um; depois GET /api/consorcios/ e /<id> do Flask sao
comparados campo a campo com consorcios_tela. So leitura.
"""
import json
import os
import subprocess
import sys

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_financiamentos_leitura import igual
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    ROOT,
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
    u = Usuario(email='flask.consorcio@teste.local', nome='Consorcio', ativo=True)
    u.definir_senha('Senha-ficticia-consorcio-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.consorcio@teste.local', 'senha': 'Senha-ficticia-consorcio-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
categoria, conta = int(sys.argv[2]), int(sys.argv[3])
ids = []
for dados in ({'nome': 'Consorcio Imovel (ficticio)', 'valor_inicial': 850.5, 'numero_parcelas': 12, 'categoria_id': categoria,
               'mes_inicio': '2031-01', 'tipo_reajuste': 'percentual', 'valor_reajuste': 2.5, 'mes_contemplacao': '2031-06',
               'valor_premio': 60000, 'meio_pagamento': 'debito_automatico', 'conta_bancaria_id': conta, 'observacoes': 'teste'},
              {'nome': 'Consorcio Moto (ficticio)', 'valor_inicial': 300, 'numero_parcelas': 6, 'categoria_id': categoria,
               'mes_inicio': '2031-03'},
              {'nome': 'Consorcio Antigo (ficticio)', 'valor_inicial': 100, 'numero_parcelas': 3, 'categoria_id': categoria,
               'mes_inicio': '2030-01'}):
    r = c.post('/api/consorcios/', json=dados)
    assert r.status_code in (200, 201), r.data[:400]
    ids.append(r.get_json()['data']['id'])
assert c.delete(f'/api/consorcios/{ids[2]}').status_code == 200
print('FLASK_JSON ' + json.dumps({'ids': ids, 'lista': c.get('/api/consorcios/').get_json(),
                                  'detalhes': {i: c.get(f'/api/consorcios/{i}').get_json() for i in ids},
                                  'inexistente': [c.get('/api/consorcios/999999').status_code, c.get('/api/consorcios/999999').get_json()]}))
"""


def flask(dsn, *args):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT, *map(str, args)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


@pytest.fixture(scope='module')
def cenario(cluster):  # noqa: F811
    dsn = copiar(cluster)
    categoria = sql(dsn, 'select id from public.categoria where ativo order by id limit 1')[0]['id']
    conta = sql(dsn, "select id from public.conta_bancaria where perfil_financeiro_id = %s and status = 'ATIVO' order by id limit 1",
                (PESSOAL,))[0]['id']
    antes = sql(dsn, 'select count(*) n from public.contrato_consorcio')[0]['n']
    return dsn, flask(dsn, PESSOAL, categoria, conta), antes


def test_privilegios(cenario):
    dsn = cenario[0]
    for funcao, esperado in (('financeiro.consorcios_tela(integer, integer)', (True, False)),
                             ('financeiro.consorcio_flask(public.contrato_consorcio)', (False, False))):
        r = sql(dsn, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                     "has_function_privilege('anon', %s, 'execute') as n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == esperado, funcao


def test_lista_e_detalhes_iguais_ao_flask(cenario):
    dsn, s, _ = cenario
    novo = rpc(dsn, 'consorcios_tela', PESSOAL, None)
    assert len(s['lista']['data']) == 2  # o inativado nao aparece
    igual(sorted(s['lista']['data'], key=lambda c: c['id']), novo, 'lista')
    for i, resposta in s['detalhes'].items():
        igual(resposta['data'], rpc(dsn, 'consorcios_tela', PESSOAL, int(i)), f'detalhe {i}')
    imovel = next(c for c in novo if c['nome'].startswith('Consorcio Imovel'))
    assert imovel['meio_pagamento'] == 'debito_automatico' and imovel['categoria_nome']
    status, corpo = s['inexistente']
    assert status == 404
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'consorcios_tela', PESSOAL, 999999)
    assert erro.value.diag.message_primary == corpo['error']


def test_isolamento_e_nada_gravado(cenario):
    dsn, s, antes = cenario
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'consorcios_tela', PESSOAL, None, usuario=USUARIO_B)
    assert erro.value.pgcode == '42501'
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'consorcios_tela', PERFIL_B, s['ids'][0], usuario=USUARIO_B)
    assert erro.value.diag.message_primary == 'Consórcio não encontrado'
    assert rpc(dsn, 'consorcios_tela', PERFIL_B, None, usuario=USUARIO_B) == []
    assert sql(dsn, 'select count(*) n from public.contrato_consorcio')[0]['n'] == antes + 3
