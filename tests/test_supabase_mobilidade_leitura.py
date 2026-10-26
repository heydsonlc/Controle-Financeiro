"""
Testes FIN-FIDELIDADE-PATRIMONIO-1 (Mobilidade, fase 1) — leitura da tela original de Mobilidade (migration 20261115090000).

Fidelidade: o PROPRIO Flask cria, no cluster descartavel, veiculos FICTICIOS (com projecoes geradas por ele), regras de
manutencao por km, financiamento do veiculo, assinatura e um caminho de transporte por app; despesas de combustivel sao
confirmadas e um cenario de mobilidade fica ativo. Depois as rotas GET do Flask sao comparadas campo a campo com as
funcoes novas (chamadas como o navegador). So leitura.
"""
import json
import os
import subprocess
import sys
from datetime import date

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

_CABECALHO = """
import json, sys
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
c = app.test_client()
"""

_CRIAR = _CABECALHO + """
with app.app_context():
    u = Usuario(email='flask.mobilidade@teste.local', nome='Mobilidade', ativo=True)
    u.definir_senha('Senha-ficticia-mobilidade-2026')
    db.session.add(u); db.session.commit()
assert c.post('/login', data={'email': 'flask.mobilidade@teste.local', 'senha': 'Senha-ficticia-mobilidade-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
hoje = sys.argv[2]
def post(url, dados):
    r = c.post(url, json=dados)
    assert r.status_code in (200, 201), (url, r.status_code, r.data[:300])
    return r.get_json()
v1 = post('/api/veiculos', {'nome': 'Carro ficticio', 'tipo': 'Carro', 'combustivel': 'Gasolina', 'status': 'ATIVO',
                            'autonomia_km_l': 12.5, 'data_inicio': hoje, 'combustivel_valor_mensal': 600,
                            'preco_medio_combustivel': 6.1, 'ipva_mes': 3, 'ipva_valor': 1800, 'seguro_mes': 5,
                            'seguro_valor': 2400.55, 'licenciamento_mes': 9, 'licenciamento_valor': 150})['data']['id']
v2 = post('/api/veiculos', {'nome': 'Moto ficticia', 'tipo': 'Moto', 'combustivel': 'Gasolina', 'autonomia_km_l': 30})['data']['id']
post(f'/api/veiculos/{v1}/regras-km', {'tipo_evento': 'TROCA_OLEO', 'intervalo_km': 10000, 'custo_estimado': 350})
post(f'/api/veiculos/{v1}/regras-km', {'tipo_evento': 'PNEUS', 'intervalo_km': 40000, 'meses_intervalo': 24, 'custo_estimado': 2000})
post(f'/api/veiculos/{v2}/regras-km', {'tipo_evento': 'REVISAO', 'intervalo_km': 15000, 'meses_intervalo': 12, 'custo_estimado': 600})
fin = c.post(f'/api/veiculos/{v1}/financiamento', json={'valor_bem': 80000, 'entrada': 20000, 'numero_parcelas': 24, 'iof_percentual': 0.38,
                                                         'taxa_juros_mensal': 1.2, 'data_inicio': hoje})
app_id = post('/api/mobilidade-app', {'nome': 'App ficticio', 'km_mensal_estimado': 300, 'preco_medio_por_km': 2.5})
post('/api/veiculos/mobilidade/assinaturas', {'nome': 'Assinatura ficticia', 'valor_mensal': 1500})
post('/api/veiculos/mobilidade/assinaturas', {'nome': 'Assinatura antiga (ficticia)', 'valor_mensal': 900})
print('FLASK_JSON ' + json.dumps({'v1': v1, 'v2': v2, 'financiamento': fin.status_code, 'financiamento_resposta': fin.get_json(), 'app': app_id}))
"""

_LER = _CABECALHO + """
assert c.post('/login', data={'email': 'flask.mobilidade@teste.local', 'senha': 'Senha-ficticia-mobilidade-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
v1, v2, app_id = (int(x) for x in sys.argv[2:5])
urls = ['/api/categorias', '/api/veiculos', f'/api/veiculos/{v1}', f'/api/veiculos/{v2}', '/api/veiculos/999999',
        f'/api/veiculos/{v1}/projecoes', f'/api/veiculos/{v1}/projecoes?meses=3', f'/api/veiculos/{v1}/projecoes?meses=0',
        f'/api/veiculos/{v1}/uso', f'/api/veiculos/{v1}/uso?janela_meses=20', f'/api/veiculos/{v2}/uso',
        f'/api/veiculos/{v1}/regras-km', f'/api/veiculos/{v1}/manutencoes-km?janela_meses=3',
        f'/api/veiculos/{v2}/manutencoes-km', f'/api/veiculos/{v1}/financiamento', f'/api/veiculos/{v2}/financiamento',
        '/api/veiculos/mobilidade/ativo', '/api/veiculos/mobilidade/assinaturas',
        '/api/veiculos/mobilidade/assinaturas?apenas_ativas=1', '/api/mobilidade-app', f'/api/mobilidade-app/{app_id}',
        '/api/mobilidade-app/999999', f'/api/mobilidade-app/{app_id}/projecoes?meses=6']
print('FLASK_JSON ' + json.dumps({u: [r.status_code, r.get_json()] for u in urls for r in [c.get(u)]}))
"""


def flask(dsn, script, *args):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', script, *map(str, args)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


@pytest.fixture(scope='module')
def cenario(cluster):  # noqa: F811
    dsn = copiar(cluster)
    criado = flask(dsn, _CRIAR, PESSOAL, date.today().isoformat())
    v1, v2 = criado['v1'], criado['v2']
    app_id = criado['app'].get('id') or criado['app'].get('data', {}).get('id') or criado['app'].get('caminho_id')
    # Historico de uso: combustivel do mes confirmado; uma das previstas com litros explicitos no metadata.
    sql(dsn, "update public.despesa_prevista set status = 'CONFIRMADA' where origem_tipo = 'VEICULO' and origem_id = %s "
             "and metadata like '%%COMBUSTIVEL%%' and data_prevista = date_trunc('month', current_date)", (v1,))
    sql(dsn, "update public.veiculo set km_estimado_acumulado = 12345.6 where id = %s", (v1,))
    # Defeito do Flask (docs §4, D-MOB1): salvar o financiamento do veiculo sempre falha (NameError em
    # upsert_financiamento). Para cobrir a LEITURA, o financiamento ficticio entra direto no banco.
    sql(dsn, "insert into public.veiculo_financiamento (perfil_financeiro_id, veiculo_id, valor_bem, entrada, valor_financiado, "
             "numero_parcelas, taxa_juros_mensal, indexador_tipo, iof_percentual, iof_valor, custo_total_financiamento, "
             "criado_em, atualizado_em) values (%s, %s, 80000, 20000, 60000, 24, 1.2, null, 0.38, 228, 72000, now(), now())",
        (PESSOAL, v1))
    item = sql(dsn, "select id from public.item_despesa where perfil_financeiro_id = %s order by id limit 1", (PESSOAL,))[0]['id']
    sql(dsn, "update public.mobilidade_assinatura set status = 'INATIVO' where nome = 'Assinatura antiga (ficticia)'")
    sql(dsn, "insert into public.mobilidade_cenario_ativo (perfil_financeiro_id, tipo_modalidade, origem_id, ativo_desde, "
             "recorrencia_id, status, created_at, updated_at) values (%s, 'VEICULO', %s, current_date, %s, 'ATIVO', now(), now())",
        (PESSOAL, v1, item))
    lido = flask(dsn, _LER, PESSOAL, v1, v2, app_id)
    return dsn, criado, lido, v1, v2, app_id


def novo(dsn, url, v1, v2, app_id):
    """A mesma URL respondida pelas funcoes novas (como o adaptador faz)."""
    from urllib.parse import parse_qs, urlparse
    u = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    partes = u.path.strip('/').split('/')[1:]
    inteiro = lambda nome, padrao: int(q[nome]) if nome in q else padrao  # noqa: E731
    if partes == ['categorias']:
        return rpc(dsn, 'mobilidade_categorias_tela', PESSOAL)
    if partes[0] == 'mobilidade-app':
        if len(partes) == 1:
            return rpc(dsn, 'transporte_app_tela', PESSOAL, None)
        if len(partes) == 2:
            return rpc(dsn, 'transporte_app_tela', PESSOAL, int(partes[1]))
        return rpc(dsn, 'projecoes_mobilidade_tela', PESSOAL, 'TRANSPORTE_APP', int(partes[1]), inteiro('meses', 24))
    if partes[1:2] == ['mobilidade']:
        if partes[2] == 'ativo':
            return rpc(dsn, 'mobilidade_ativa_tela', PESSOAL)
        return rpc(dsn, 'mobilidade_assinaturas_tela', PESSOAL, q.get('apenas_ativas', '').lower() in ('1', 'true', 'yes'))
    if len(partes) == 1:
        return rpc(dsn, 'veiculos_tela', PESSOAL, None)
    vid = int(partes[1])
    if len(partes) == 2:
        return rpc(dsn, 'veiculos_tela', PESSOAL, vid)
    recurso = partes[2]
    if recurso == 'projecoes':
        return rpc(dsn, 'projecoes_mobilidade_tela', PESSOAL, 'VEICULO', vid, inteiro('meses', 24))
    if recurso == 'uso':
        return rpc(dsn, 'veiculo_uso_tela', PESSOAL, vid, inteiro('janela_meses', 3))
    if recurso == 'regras-km':
        return rpc(dsn, 'veiculo_regras_km_tela', PESSOAL, vid)
    if recurso == 'manutencoes-km':
        return rpc(dsn, 'veiculo_manutencoes_km_tela', PESSOAL, vid, inteiro('janela_meses', 3))
    return rpc(dsn, 'veiculo_financiamento_tela', PESSOAL, vid)


def test_privilegios(cenario):
    dsn = cenario[0]
    for funcao, esperado in (('financeiro.veiculos_tela(integer, integer)', (True, False)),
                             ('financeiro.veiculo_manutencoes_km_tela(integer, integer, integer)', (True, False)),
                             ('financeiro.uso_do_veiculo(public.veiculo, integer)', (False, False)),
                             ('financeiro.json_seguro(text)', (False, False))):
        r = sql(dsn, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                     "has_function_privilege('anon', %s, 'execute') as n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == esperado, funcao


def test_cenario_ficticio_completo(cenario):
    _, criado, lido, v1, *_ = cenario
    assert criado['financiamento'] == 500
    assert criado['financiamento_resposta']['error'] == "name 'veiculo' is not defined"  # D-MOB1 do Flask
    assert lido[f'/api/veiculos/{v1}/uso'][1]['data']['km_por_mes']  # ha historico de uso
    assert lido[f'/api/veiculos/{v1}/manutencoes-km?janela_meses=3'][1]['data']['fonte_uso'] == 'HISTORICO'
    assert lido['/api/veiculos/mobilidade/ativo'][1]['data']['nome_origem'] == 'Carro ficticio'


def test_todas_as_leituras_iguais_ao_flask(cenario):
    dsn, _, lido, v1, v2, app_id = cenario
    for url, (status, resposta) in lido.items():
        if status != 200:
            with pytest.raises(psycopg2.Error) as erro:
                novo(dsn, url, v1, v2, app_id)
            assert erro.value.diag.message_primary == resposta['error'].replace('nÇœo', 'não'), url
            continue
        esperado, obtido = resposta['data'], novo(dsn, url, v1, v2, app_id)
        if url == '/api/categorias':  # o Flask nao ordena (ordem fisica da tabela); o novo ordena por id
            esperado = sorted(esperado, key=lambda c: c['id'])
        igual(esperado, obtido, url)


def test_isolamento(cenario):
    dsn, _, _, v1, *_ = cenario
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'veiculos_tela', PESSOAL, None, usuario=USUARIO_B)
    assert erro.value.pgcode == '42501'
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'veiculo_uso_tela', PERFIL_B, v1, 3, usuario=USUARIO_B)
    assert erro.value.diag.message_primary == 'Veículo não encontrado'
    assert rpc(dsn, 'veiculos_tela', PERFIL_B, None, usuario=USUARIO_B) == []
    assert rpc(dsn, 'transporte_app_tela', PERFIL_B, None, usuario=USUARIO_B) == []
