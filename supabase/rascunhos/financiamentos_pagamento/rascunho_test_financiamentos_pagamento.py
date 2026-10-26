"""
Testes FIN-FIDELIDADE-CONTRATOS-1 (fase 2) — pagamento e estorno de parcela de financiamento (migration 20261111090000).

Fidelidade: no cluster descartavel o PROPRIO Flask cria dois financiamentos FICTICIOS iguais; no primeiro paga as parcelas
1 e 2 e estorna a 2 (POST /parcelas/<id>/pagar e /estornar-pagamento). O novo aplicativo faz o mesmo no segundo
(pagar_parcela_financiamento / estornar_parcela_financiamento) e parcelas, saldo devedor, movimentos e saldo bancario
sao comparados. Tambem: correcoes classificadas (estorno de novo pagamento, descricao com o nome), escritor unico,
idempotencia, bloqueios, privilegios e isolamento.
"""
import json
import os
import subprocess
import sys
import uuid

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    ROOT,
    USUARIO_B,
    atribuir,
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
    u = Usuario(email='flask.pagamento.fin@teste.local', nome='Financiamento', ativo=True)
    u.definir_senha('Senha-ficticia-financiamento-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.pagamento.fin@teste.local', 'senha': 'Senha-ficticia-financiamento-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
conta = int(sys.argv[2])
base = {'produto': 'Habitacional ficticio', 'valor_financiado': 60000, 'prazo_total_meses': 12, 'sistema_amortizacao': 'SAC',
        'taxa_juros_nominal_anual': 9.5, 'data_contrato': '2030-01-10', 'data_primeira_parcela': '2030-02-10',
        'seguro_tipo': 'fixo', 'valor_seguro_mensal': 20, 'taxa_administracao_fixa': 25,
        'vigencias_seguro': [{'competencia_inicio': '2030-02-01', 'valor_mensal': 20, 'observacoes': 'apolice ficticia'}]}
ids = [c.post('/api/financiamentos', json={**base, 'nome': nome}).get_json()['data']['id']
       for nome in ('Pagamento Flask (ficticio)', 'Pagamento Novo (ficticio)')]
parcelas = [p['id'] for p in c.get(f'/api/financiamentos/{ids[0]}').get_json()['data']['parcelas']]
r = []
r.append(c.post(f'/api/financiamentos/parcelas/{parcelas[0]}/pagar', json={'conta_bancaria_id': conta, 'data_pagamento': '2030-02-10'}))
r.append(c.post(f'/api/financiamentos/parcelas/{parcelas[1]}/pagar', json={'conta_bancaria_id': conta, 'data_pagamento': '2030-03-11'}))
r.append(c.post(f'/api/financiamentos/parcelas/{parcelas[0]}/estornar-pagamento', json={'data_estorno': '2030-03-12', 'motivo': 'teste'}))
r.append(c.post(f'/api/financiamentos/parcelas/{parcelas[1]}/estornar-pagamento', json={'data_estorno': '2030-03-12', 'motivo': 'engano ficticio'}))
r.append(c.post(f'/api/financiamentos/parcelas/{parcelas[1]}/pagar', json={'conta_bancaria_id': conta, 'data_pagamento': '2030-03-13'}))
r.append(c.post(f'/api/financiamentos/parcelas/{parcelas[1]}/estornar-pagamento', json={'data_estorno': '2030-03-14', 'motivo': 'de novo'}))
print('FLASK_JSON ' + json.dumps({'ids': ids, 'respostas': [[x.status_code, x.get_json()] for x in r]}))
"""


def flask(dsn, perfil, conta):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT, str(perfil), str(conta)], cwd=ROOT, env=env, capture_output=True,
                       text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


def parcelas(dsn, fid):
    return sql(dsn, 'select id, numero_parcela, status, valor_pago::float, dif_apurada::float, '
                    'saldo_devedor_apos_pagamento::float saldo from public.financiamento_parcela '
                    'where financiamento_id = %s order by numero_parcela', (fid,))


def movimentos(dsn, fid):
    return sql(dsn, 'select m.id, m.tipo, m.valor::float, m.data_movimento::text data, m.origem, m.descricao, '
                    'm.conta_bancaria_id, p.numero_parcela, (m.movimento_original_id is not null) ligado '
                    'from public.movimento_financeiro m join public.financiamento_parcela p on p.id = m.financiamento_parcela_id '
                    'where p.financiamento_id = %s order by m.id', (fid,))


def saldo_devedor(dsn, fid):
    return float(sql(dsn, 'select saldo_devedor_atual from public.financiamento where id = %s', (fid,))[0]['saldo_devedor_atual'])


def saldo_bancario(dsn, conta):
    return float(sql(dsn, 'select saldo_atual from public.conta_bancaria where id = %s', (conta,))[0]['saldo_atual'])


def pagar(dsn, parcela, data, conta, chave=None, perfil=PESSOAL, usuario=None):
    extra = {'usuario': usuario} if usuario else {}
    return rpc(dsn, 'pagar_parcela_financiamento', perfil, parcela, {'conta_bancaria_id': conta, 'data_pagamento': data},
               chave or str(uuid.uuid4()), **extra)


def estornar(dsn, parcela, data, motivo='engano ficticio', chave=None):
    return rpc(dsn, 'estornar_parcela_financiamento', PESSOAL, parcela, {'data_estorno': data, 'motivo': motivo},
               chave or str(uuid.uuid4()))


def erro(funcao, *args):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args)
    return e.value.diag.message_primary


@pytest.fixture(scope='module')
def cenario(cluster):  # noqa: F811
    dsn = copiar(cluster)
    conta = sql(dsn, "insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, cor_display, "
                     "saldo_inicial, saldo_atual) values (%s, 'Conta pagamento financiamento (ficticia)', 'Banco ficticio', "
                     "'Conta Corrente', 'ATIVO', '#3b82f6', 10000, 10000) returning id", (PESSOAL,))[0]['id']
    saida = flask(dsn, PESSOAL, conta)
    fid_flask, fid_novo = saida['ids']
    saldo_flask = saldo_bancario(dsn, conta)
    atribuir(dsn, 'PESSOAL', 'NOVO')
    novas = [p['id'] for p in parcelas(dsn, fid_novo)]
    resultados = [pagar(dsn, novas[0], '2030-02-10', conta), pagar(dsn, novas[1], '2030-03-11', conta)]
    msg_nao_ultima = erro(estornar, dsn, novas[0], '2030-03-12', 'teste')
    resultados.append(estornar(dsn, novas[1], '2030-03-12'))
    return {'dsn': dsn, 'conta': conta, 'flask': saida, 'fid_flask': fid_flask, 'fid_novo': fid_novo, 'novas': novas,
            'resultados': resultados, 'msg_nao_ultima': msg_nao_ultima, 'saldo_flask': saldo_flask}


def test_privilegios(cenario):
    dsn = cenario['dsn']
    for funcao, esperado in (('financeiro.pagar_parcela_financiamento(integer, integer, jsonb, uuid)', (True, False)),
                             ('financeiro.estornar_parcela_financiamento(integer, integer, jsonb, uuid)', (True, False)),
                             ('financeiro.travar_parcela_financiamento(integer, integer)', (False, False)),
                             ('financeiro.bloqueio_da_parcela(public.financiamento_parcela, public.financiamento)', (False, False))):
        r = sql(dsn, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                     "has_function_privilege('anon', %s, 'execute') as n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == esperado, funcao


def test_respostas_do_flask_no_mesmo_roteiro(cenario):
    r = cenario['flask']['respostas']
    assert [x[0] for x in r[:4]] == [200, 200, 409, 200]
    assert r[2][1]['error'].startswith('Existe uma parcela paga mais recente (numero 2)')
    assert cenario['msg_nao_ultima'] == r[2][1]['error']
    # Defeito do Flask (corrigido no novo): depois de estornar, pagar de novo e estornar de novo e bloqueado para sempre.
    assert r[4][0] == 200 and r[5] == [409, {'success': False, 'error': 'Este pagamento/recebimento ja foi estornado.'}]


def test_parcelas_saldo_devedor_e_movimentos_iguais_ao_flask(cenario):
    dsn, ff, fn = cenario['dsn'], cenario['fid_flask'], cenario['fid_novo']
    # O Flask terminou com a parcela 2 paga de novo (o segundo estorno foi recusado): compara-se ate o 1o estorno.
    pf, pn = parcelas(dsn, ff), parcelas(dsn, fn)
    assert [p['status'] for p in pn] == ['pago'] + ['pendente'] * 11
    assert [{k: v for k, v in p.items() if k != 'id'} for p in pn[2:]] == [{k: v for k, v in p.items() if k != 'id'} for p in pf[2:]]
    assert {k: v for k, v in pn[0].items() if k != 'id'} == {k: v for k, v in pf[0].items() if k != 'id'}
    assert pn[0]['valor_pago'] > 0 and pn[0]['dif_apurada'] == 0 and pn[1]['valor_pago'] == 0
    assert saldo_devedor(dsn, fn) == pn[0]['saldo'] == cenario['resultados'][2]['saldo_devedor_atual']

    mf, mn = movimentos(dsn, ff), movimentos(dsn, fn)
    campos = ('tipo', 'valor', 'data', 'origem', 'conta_bancaria_id', 'numero_parcela', 'ligado')
    assert [tuple(m[c] for c in campos) for m in mn] == [tuple(m[c] for c in campos) for m in mf[:3]]
    # Correcao classificada: o Flask le 'descricao' (inexistente no modelo) e grava 'Financiamento #id'.
    assert mf[0]['descricao'] == f'Pagamento parcela 1 - Financiamento #{ff}'
    assert [m['descricao'] for m in mn] == ['Pagamento parcela 1 - Pagamento Novo (ficticio)',
                                            'Pagamento parcela 2 - Pagamento Novo (ficticio)',
                                            'Estorno de pagamento da parcela 2 - Pagamento Novo (ficticio)']
    # Saldo bancario so pelos movimentos: o efeito liquido do novo e o da parcela 1.
    esperado = cenario['saldo_flask'] - pn[0]['valor_pago']
    assert abs(saldo_bancario(dsn, cenario['conta']) - esperado) < 0.005
    assert cenario['resultados'][2]['motivo'] == 'engano ficticio'


def test_estorno_de_novo_pagamento_e_idempotencia(cenario):
    dsn, conta, p2 = cenario['dsn'], cenario['conta'], cenario['novas'][1]
    saldo = saldo_bancario(dsn, conta)
    chave = str(uuid.uuid4())
    primeiro = pagar(dsn, p2, '2030-03-13', conta, chave=chave)
    assert pagar(dsn, p2, '2030-03-13', conta, chave=chave) == {**primeiro, 'repetida': True}
    assert erro(pagar, dsn, p2, '2030-03-13', conta) == 'Esta parcela ja foi paga.'
    chave = str(uuid.uuid4())
    estorno = estornar(dsn, p2, '2030-03-14', chave=chave)
    assert estornar(dsn, p2, '2030-03-14', chave=chave)['movimento_estorno_id'] == estorno['movimento_estorno_id']
    assert estorno['movimento_original_id'] == primeiro['movimento_id']
    assert erro(estornar, dsn, p2, '2030-03-14') == 'Apenas parcelas pagas podem ser estornadas.'
    assert abs(saldo_bancario(dsn, conta) - saldo) < 0.005


def test_validacoes_como_no_flask(cenario):
    dsn, conta, p3 = cenario['dsn'], cenario['conta'], cenario['novas'][2]
    assert erro(rpc, dsn, 'pagar_parcela_financiamento', PESSOAL, p3, {'data_pagamento': '2030-04-10'}, str(uuid.uuid4())) \
        == 'Informe a conta bancaria para registrar o pagamento da parcela.'
    assert erro(rpc, dsn, 'pagar_parcela_financiamento', PESSOAL, p3, {'conta_bancaria_id': conta}, str(uuid.uuid4())) \
        == 'data_pagamento e obrigatorio'
    assert erro(pagar, dsn, p3, '10/04/2030', conta) == 'Formato de data_pagamento invalido. Use YYYY-MM-DD'
    assert erro(pagar, dsn, 999999, '2030-04-10', conta) == 'Parcela nao encontrada'
    assert erro(pagar, dsn, p3, '2030-04-10', 999999) == 'Conta bancaria nao encontrada'
    assert erro(estornar, dsn, cenario['novas'][0], '2030-04-10', '  ') == 'Motivo do estorno e obrigatorio.'
    sql(dsn, "update public.conta_bancaria set status = 'INATIVO' where id = %s", (conta,))
    try:
        assert erro(pagar, dsn, p3, '2030-04-10', conta) == 'Conta bancaria esta inativa'
    finally:
        sql(dsn, "update public.conta_bancaria set status = 'ATIVO' where id = %s", (conta,))
    assert parcelas(dsn, cenario['fid_novo'])[2]['status'] == 'pendente'


def test_parcela_com_despesa_vinculada_continua_no_sistema_atual(cenario):
    dsn, conta, p3 = cenario['dsn'], cenario['conta'], cenario['novas'][2]
    item = sql(dsn, 'select id from public.item_despesa order by id limit 1')[0]['id']
    sql(dsn, 'update public.financiamento set item_despesa_id = %s where id = %s', (item, cenario['fid_novo']))
    try:
        assert erro(pagar, dsn, p3, '2030-04-10', conta).startswith('Parcela com despesa vinculada')
        assert erro(estornar, dsn, cenario['novas'][0], '2030-04-10').startswith('Parcela com despesa vinculada')
    finally:
        sql(dsn, 'update public.financiamento set item_despesa_id = null where id = %s', (cenario['fid_novo'],))


def test_escritor_unico_e_isolamento(cenario):
    dsn, conta, p3 = cenario['dsn'], cenario['conta'], cenario['novas'][2]
    atribuir(dsn, 'PESSOAL', 'FLASK')
    try:
        with pytest.raises(psycopg2.Error) as e:
            pagar(dsn, p3, '2030-04-10', conta)
        assert e.value.diag.hint == 'SISTEMA_FLASK'
    finally:
        atribuir(dsn, 'PESSOAL', 'NOVO')
    with pytest.raises(psycopg2.Error) as e:
        pagar(dsn, p3, '2030-04-10', conta, usuario=USUARIO_B)
    assert e.value.pgcode == '42501'
    atribuir(dsn, 'PERFIL_B', 'NOVO')
    assert erro(pagar, dsn, p3, '2030-04-10', conta, None, PERFIL_B, USUARIO_B) == 'Parcela nao encontrada'
    assert parcelas(dsn, cenario['fid_novo'])[2]['status'] == 'pendente'
