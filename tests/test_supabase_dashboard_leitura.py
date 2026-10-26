"""
Testes FIN-FIDELIDADE-CONSOLIDACAO-1 — leitura do Dashboard Financeiro (migration 20261114090000).

Fidelidade: sobre os dados FICTICIOS do cluster descartavel (contas, faturas, cartoes, receitas dos seeds) e mais linhas
FICTICIAS que acionam todos os blocos (despesas previstas atrasadas, conta vencendo hoje, cenario de mobilidade,
assinaturas, documentos empresariais vencidos e vencendo), o PROPRIO Flask responde GET /api/dashboard/resumo para
3 perfis e varios meses; o resultado e comparado campo a campo com dashboard_resumo_tela.
Unica diferenca aceita: D1 (o Flask soma as despesas previstas do mes de todos os perfis).
"""
import json
import os
import subprocess
import sys
from datetime import date, timedelta

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

HOJE = date.today()
MESES = ('', HOJE.strftime('%Y-%m'), '2027-03', '2027-02-15', 'mes-invalido')
PERFIS = ('PESSOAL', 'EMPRESA', 'PERFIL_B')

_SCRIPT = """
import json, sys
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    u = Usuario(email='flask.dashboard@teste.local', nome='Dashboard', ativo=True)
    u.definir_senha('Senha-ficticia-dashboard-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.dashboard@teste.local', 'senha': 'Senha-ficticia-dashboard-2026'}).status_code == 302
perfis, meses = json.loads(sys.argv[1]), json.loads(sys.argv[2])
saida = {}
for chave, perfil in perfis.items():
    assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': perfil}).status_code == 200
    saida[chave] = {m: c.get('/api/dashboard/resumo?mes_referencia=' + m).get_json() for m in meses}
print('FLASK_JSON ' + json.dumps(saida))
"""


def flask(dsn):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT, json.dumps({p: ID[p] for p in PERFIS}), json.dumps(MESES)], cwd=ROOT,
                       env=env, capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


@pytest.fixture(scope='module')
def cenario(cluster):  # noqa: F811
    dsn = copiar(cluster)
    pessoal, empresa = ID['PESSOAL'], ID['EMPRESA']
    item = sql(dsn, "select id from public.item_despesa where perfil_financeiro_id = %s and tipo <> 'Agregador' order by id limit 1",
               (pessoal,))[0]['id']
    categoria = sql(dsn, 'select id from public.categoria order by id limit 1')[0]['id']
    for dias, status, valor in ((-10, 'PREVISTA', 80), (-3, 'ADIADA', 45.5), (2, 'CONFIRMADA', 120)):
        d = HOJE + timedelta(days=dias)
        sql(dsn, "insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, "
                 "data_original_prevista, data_atual_prevista, valor_previsto, status, criado_em, atualizado_em) "
                 "values (%s, 'VEICULO', 1, %s, %s, %s, %s, %s, %s, now(), now())",
            (pessoal, categoria, d.replace(day=1), d, d, valor, status))
    sql(dsn, "insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento, "
             "status_pagamento, is_fatura_cartao) values (%s, %s, %s, 'Conta vencendo hoje (ficticia)', 77.7, %s, 'Pendente', false)",
        (pessoal, item, HOJE.replace(day=1), HOJE))
    sql(dsn, "insert into public.mobilidade_cenario_ativo (perfil_financeiro_id, tipo_modalidade, origem_id, ativo_desde, "
             "recorrencia_id, status, created_at, updated_at) values (%s, 'TRANSPORTE_APP', 1, %s, %s, 'ATIVO', now(), now())",
        (pessoal, HOJE, item))
    for nome, valor in (('Assinatura A (ficticia)', 199.9), ('Assinatura B (ficticia)', 89)):
        sql(dsn, "insert into public.mobilidade_assinatura (perfil_financeiro_id, nome, valor_mensal, status, created_at, updated_at) "
                 "values (%s, %s, %s, 'ATIVO', now(), now())", (pessoal, nome, valor))
    for dias in (-5, 12):
        comprovante = sql(dsn, "insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, status, hash_arquivo, "
                               "created_at, updated_at) values (%s, 2031, 'IMPORTADO', %s, now(), now()) returning id",
                          (empresa, ('d' if dias < 0 else 'e') * 64))[0]['id']
        sql(dsn, "insert into public.documento_empresarial_metadata (comprovante_id, perfil_financeiro_id, tipo_documental, "
                 "categoria_documental, data_validade, status_documental, obrigatorio, renovavel, created_at, updated_at) "
                 "values (%s, %s, 'CERTIDAO', 'FISCAL', %s, 'VALIDO', true, true, now(), now())",
            (comprovante, empresa, HOJE + timedelta(days=dias)))
    return dsn, flask(dsn)


def test_privilegios(cenario):
    dsn, _ = cenario
    for funcao, esperado in (('financeiro.dashboard_resumo_tela(integer, text)', (True, False)),
                             ('financeiro.percentual_flask(numeric, numeric)', (False, False))):
        r = sql(dsn, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                     "has_function_privilege('anon', %s, 'execute') as n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == esperado, funcao


@pytest.mark.parametrize('perfil', PERFIS)
def test_resumo_igual_ao_flask(cenario, perfil):
    dsn, saida = cenario
    for mes, resposta in saida[perfil].items():
        assert resposta['success'], resposta
        esperado = resposta['data']
        novo = rpc(dsn, 'dashboard_resumo_tela', ID[perfil], mes, **({'usuario': USUARIO_B} if perfil == 'PERFIL_B' else {}))
        if perfil != 'PESSOAL':  # D1: o Flask mistura as despesas previstas de todos os perfis
            esperado = {**esperado, 'operacional': {**esperado['operacional'], 'despesas_previstas_mes': novo['operacional']['despesas_previstas_mes']}}
        igual(esperado, novo, f'{perfil} {mes!r}')


def test_cenario_aciona_todos_os_blocos(cenario):
    dsn, saida = cenario
    pessoal = rpc(dsn, 'dashboard_resumo_tela', ID['PESSOAL'], '')
    tipos = {a['tipo'] for a in pessoal['alertas']}
    assert {'vencimento', 'prevista'} <= tipos
    assert pessoal['mobilidade']['status'] == 'ativa' and len(pessoal['mobilidade']['alternativas']) == 2
    empresa = rpc(dsn, 'dashboard_resumo_tela', ID['EMPRESA'], '')
    assert [a['nivel'] for a in empresa['alertas'] if a['tipo'] == 'documento_empresarial'] == ['critico', 'atencao']
    # D1 documentado: o Flask mostra na Empresa as despesas previstas do Pessoal; o novo, so as da Empresa.
    assert saida['EMPRESA']['']['data']['operacional']['despesas_previstas_mes']['valor'] > 0
    assert empresa['operacional']['despesas_previstas_mes']['valor'] == 0


def test_isolamento(cenario):
    dsn, _ = cenario
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'dashboard_resumo_tela', ID['PESSOAL'], '', usuario=USUARIO_B)
    assert erro.value.pgcode == '42501'
