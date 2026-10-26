"""
Testes FIN-FIDELIDADE-DOCUMENTOS-1 (Documentos da Empresa) — "saidas sem documento" (migration 20261117090000).

Fidelidade: no cluster descartavel, saidas FICTICIAS do perfil Empresa em todas as origens (despesa prevista, conta, lancamento
no cartao, debito avulso, transferencia interna que deve ficar de fora), uma com documento vinculado e outras com pendencia
(aguardando contador, nao aplicavel); o PROPRIO Flask responde GET /api/ir/lastro/saidas-sem-documento e /resumo com varios
filtros, comparados campo a campo com lastro_saidas_tela. So leitura.
"""
import json
import os
import subprocess
import sys
import uuid
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

PESSOAL, EMPRESA = ID['PESSOAL'], ID['EMPRESA']
ANO = date.today().year
CONSULTAS = ('', f'ano={ANO}', f'ano={ANO}&mes=3', 'status=TODOS', 'status=nao_aplicavel', 'status=AGUARDANDO_CONTADOR',
             'origem=CONTA', 'origem=Lancamento no cartao', 'natureza=IMPOSTO_TAXA', 'busca=GUIA', 'busca=notebook',
             'valor_minimo=100', 'valorMinimo=abc', 'ano=2027')

_SCRIPT = """
import json, sys
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    u = Usuario(email='flask.lastro@teste.local', nome='Lastro', ativo=True)
    u.definir_senha('Senha-ficticia-lastro-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.lastro@teste.local', 'senha': 'Senha-ficticia-lastro-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
saida = {}
for q in json.loads(sys.argv[2]):
    lista = c.get('/api/ir/lastro/saidas-sem-documento?' + q)
    resumo = c.get('/api/ir/lastro/saidas-sem-documento/resumo?' + q)
    saida[q] = [lista.status_code, lista.get_json(), resumo.status_code, resumo.get_json()]
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[3])}).status_code == 200
r = c.get('/api/ir/lastro/saidas-sem-documento')
saida['pessoal'] = [r.status_code, r.get_json()]
print('FLASK_JSON ' + json.dumps(saida))
"""


def flask(dsn):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT, str(EMPRESA), json.dumps(CONSULTAS), str(PESSOAL)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


@pytest.fixture(scope='module')
def cenario(cluster):  # noqa: F811
    dsn = copiar(cluster)
    um = lambda q, p=(): sql(dsn, q, p)[0]['id']  # noqa: E731
    categoria = um("insert into public.categoria (nome, descricao, ativo, sistemica, bloquear_edicao, bloquear_exclusao, criado_em) "
                   "values ('Impostos (ficticia)', 'x', true, false, false, false, now()) "
                   "returning id")
    item = um("insert into public.item_despesa (perfil_financeiro_id, categoria_id, nome, tipo, ativo, recorrente) "
              "values (%s, %s, 'Guia municipal (ficticia)', 'Simples', true, false) returning id", (EMPRESA, categoria))
    banco = um("select id from public.conta_bancaria where perfil_financeiro_id = %s order by id limit 1", (EMPRESA,))
    d = lambda mes, dia=10: date(ANO, mes, dia)  # noqa: E731
    contas = [um("insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento, "
                 "status_pagamento, is_fatura_cartao) values (%s, %s, %s, %s, %s, %s, %s, false) returning id",
                 (EMPRESA, item, d(m, 1), desc, valor, d(m), status))
              for m, desc, valor, status in ((3, 'Guia ISS (ficticia)', 250.4, 'Pendente'), (3, '', 99.9, 'Pago'),
                                             (5, 'Notebook novo (ficticio)', 4800, 'Pendente'))]
    prevista = um("insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, "
                  "data_original_prevista, data_atual_prevista, valor_previsto, status, criado_em, atualizado_em) values "
                  "(%s, 'VEICULO', 1, %s, %s, %s, %s, 320, 'PREVISTA', now(), now()) returning id",
                  (EMPRESA, categoria, d(4, 1), d(4), d(4)))
    um("insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, "
       "data_original_prevista, data_atual_prevista, valor_previsto, status, criado_em, atualizado_em) values "
       "(%s, 'VEICULO', 1, %s, %s, %s, %s, 50, 'IGNORADA', now(), now()) returning id", (EMPRESA, categoria, d(4, 1), d(4), d(4)))
    avulso = um("insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, "
                "data_movimento, origem, ajustavel, criado_em) values (%s, %s, 'DEBITO', 75, 'Tarifa assinatura software', %s, "
                "'MANUAL', false, now()) returning id", (EMPRESA, banco, d(3, 20)))
    par = str(uuid.uuid4())
    for tipo in ('DEBITO', 'CREDITO'):
        um("insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao, data_movimento, "
           "origem, transferencia_id, ajustavel, criado_em) values (%s, %s, %s, 500, 'Transferencia interna', %s, 'TRANSFERENCIA', %s, "
           "false, now()) returning id", (EMPRESA, banco, tipo, d(3, 21), par))
    comprovante = um("insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, status, hash_arquivo, created_at, "
                     "updated_at) values (%s, %s, 'VALIDADO', repeat('f', 64), now(), now()) returning id", (EMPRESA, ANO))
    um("insert into public.ir_comprovante_vinculo (comprovante_id, perfil_financeiro_id, tipo_entidade, entidade_id, resumo_entidade, "
       "tipo_vinculo, natureza, status_lastro, ativo, created_at, updated_at) values (%s, %s, 'CONTA', %s, 'x', 'NOTA_FISCAL', "
       "'IMPOSTO_TAXA', 'VALIDADO', true, now(), now()) returning id", (comprovante, EMPRESA, contas[1]))
    for tipo, entidade, status, natureza in (('CONTA', contas[0], 'AGUARDANDO_CONTADOR', 'IMPOSTO_TAXA'),
                                             ('DESPESA_PREVISTA', prevista, 'NAO_APLICAVEL', 'OUTRO'),
                                             ('MOVIMENTO_FINANCEIRO', avulso, 'PENDENTE', '')):
        um("insert into public.lastro_financeiro_pendencia (perfil_financeiro_id, tipo_entidade, entidade_id, status_lastro, natureza, "
           "observacoes, ativo, created_at, updated_at) values (%s, %s, %s, %s, %s, 'pendencia ficticia', true, now(), now()) "
           "returning id", (EMPRESA, tipo, entidade, status, natureza))
    return dsn, flask(dsn)


def test_privilegios(cenario):
    dsn = cenario[0]
    for funcao, esperado in (('financeiro.lastro_saidas_tela(integer, jsonb, boolean)', (True, False)),
                             ('financeiro.saidas_lastro(integer, jsonb)', (False, False))):
        r = sql(dsn, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                     "has_function_privilege('anon', %s, 'execute') as n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == esperado, funcao


def test_lista_e_resumo_iguais_ao_flask(cenario):
    dsn, s = cenario
    for consulta in CONSULTAS:
        st_lista, lista, st_resumo, resumo = s[consulta]
        assert st_lista == 200 and st_resumo == 200, consulta
        filtros = dict(p.split('=', 1) for p in consulta.split('&') if p)
        igual(lista['data'], rpc(dsn, 'lastro_saidas_tela', EMPRESA, filtros, False), f'lista {consulta!r}')
        igual(resumo['data'], rpc(dsn, 'lastro_saidas_tela', EMPRESA, filtros, True), f'resumo {consulta!r}')
    todas = s['status=TODOS'][1]['data']
    assert {x['tipo_entidade'] for x in todas} == {'CONTA', 'DESPESA_PREVISTA', 'MOVIMENTO_FINANCEIRO'} | (
        {'LANCAMENTO'} if any(x['tipo_entidade'] == 'LANCAMENTO' for x in todas) else set())
    assert not any(x['descricao'] == 'Transferencia interna' for x in todas)
    assert s[''][3]['data']['saidas_com_documento'] >= 1


def test_so_perfil_empresa_e_isolamento(cenario):
    dsn, s = cenario
    status, corpo = s['pessoal']
    assert status == 403
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'lastro_saidas_tela', PESSOAL, {}, False)
    assert erro.value.diag.message_primary == corpo['error'] and erro.value.pgcode == '42501'
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'lastro_saidas_tela', EMPRESA, {}, False, usuario=USUARIO_B)
    assert erro.value.pgcode == '42501'
