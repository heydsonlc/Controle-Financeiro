"""
Testes FIN-FIDELIDADE-PATRIMONIO-1 (fase 1) — leitura da tela original de Patrimonio (migration 20261112090000).

Fidelidade: o PROPRIO Flask cria, no cluster descartavel, caixinhas e transferencias FICTICIAS no Pessoal e bens
FICTICIOS no perfil Empresa (com imagem, depreciacao e um documento fiscal ficticio vinculado); depois as rotas GET de
/api/patrimonio do Flask sao comparadas campo a campo com as funcoes novas (chamadas como o navegador). So leitura.
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

PESSOAL, EMPRESA, PERFIL_B = ID['PESSOAL'], ID['EMPRESA'], ID['PERFIL_B']
ANO = date.today().year

_SCRIPT = """
import json, sys
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    u = Usuario(email='flask.patrimonio@teste.local', nome='Patrimonio', ativo=True)
    u.definir_senha('Senha-ficticia-patrimonio-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.patrimonio@teste.local', 'senha': 'Senha-ficticia-patrimonio-2026'}).status_code == 302
pessoal, empresa, comprovante, ano = (int(x) for x in sys.argv[1:5])
def ativar(perfil):
    assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': perfil}).status_code == 200
ativar(pessoal)
ids = []
for dados in ({'nome': 'Reserva (ficticia)', 'tipo': 'Reserva', 'saldo_inicial': 5000, 'meta': 20000, 'cor': '#123456'},
              {'nome': 'Viagem (ficticia)', 'tipo': 'Poupança', 'saldo_inicial': 800, 'meta': 0, 'observacoes': 'teste'},
              {'nome': 'Antiga (ficticia)', 'tipo': 'Investimento', 'saldo_inicial': 0}):
    r = c.post('/api/patrimonio/contas', json=dados)
    assert r.status_code in (200, 201), r.data[:300]
    ids.append(r.get_json()['data']['id'])
assert c.delete(f'/api/patrimonio/contas/{ids[2]}').status_code == 200
for valor, data, desc in ((300, '2031-01-05', 'Aporte'), (120.5, '2031-02-10', 'Ajuste'), (50, '2031-02-10', None)):
    r = c.post('/api/patrimonio/transferencias', json={'conta_origem_id': ids[0], 'conta_destino_id': ids[1], 'valor': valor,
                                                       'data_transferencia': data, 'descricao': desc})
    assert r.status_code in (200, 201), r.data[:300]
saida = {'contas': c.get('/api/patrimonio/contas').get_json(), 'inativas': c.get('/api/patrimonio/contas?ativo=false').get_json(),
         'conta': c.get(f'/api/patrimonio/contas/{ids[0]}').get_json(),
         'transf': c.get('/api/patrimonio/transferencias').get_json(),
         'transf_filtro': c.get(f'/api/patrimonio/transferencias?data_inicio=2031-02-01&conta_id={ids[1]}').get_json(),
         'bens_pessoal': c.get('/api/patrimonio/bens').get_json(), 'resumo_pessoal': c.get('/api/patrimonio/bens/resumo').get_json(),
         'imagens': c.get('/api/patrimonio/bens/imagens').get_json(), 'ids': ids}
saida['transf_um'] = c.get(f"/api/patrimonio/transferencias/{saida['transf']['data'][0]['id']}").get_json()
ativar(empresa)
bens = []
for dados in ({'nome': 'Notebook de trabalho (ficticio)', 'codigo': 'PAT-001', 'categoria': 'Informatica', 'valor_aquisicao': 7500.55,
               'vida_util_meses': 36, 'data_aquisicao': f'{ano}-03-10', 'imagem_arquivo': 'Patrimonio_notebook.jpg', 'fornecedor': 'Loja X'},
              {'nome': 'Cadeira ergonomica (ficticia)', 'categoria': 'Moveis', 'valor_aquisicao': 1200, 'data_aquisicao': '2029-07-01',
               'status_documental': 'PENDENTE', 'imagem_arquivo': 'nao_existe.png'},
              {'nome': 'Impressora laser (ficticia)', 'categoria': 'Informatica', 'valor_aquisicao': 980.4, 'status': 'BAIXADO',
               'status_documental': 'DIVERGENTE'},
              {'nome': 'Item sem categoria (ficticio)', 'categoria': '', 'valor_aquisicao': 0, 'status_documental': 'NAO_APLICAVEL'}):
    r = c.post('/api/patrimonio/bens', json=dados)
    assert r.status_code == 201, r.data[:300]
    bens.append(r.get_json()['data']['id'])
r = c.post(f'/api/patrimonio/bens/{bens[0]}/vincular-documento', json={'comprovante_id': comprovante, 'tipo_vinculo': 'RECIBO'})
assert r.status_code == 200, r.data[:300]
saida.update({'bens': c.get('/api/patrimonio/bens').get_json(), 'resumo': c.get('/api/patrimonio/bens/resumo').get_json(),
              'bem': c.get(f'/api/patrimonio/bens/{bens[0]}').get_json(), 'bens_ids': bens,
              'filtros': {q: c.get('/api/patrimonio/bens?' + q).get_json() for q in (
                  'categoria=Informatica', 'categoria=TODAS&status=baixado', 'documento=validado', f'ano={ano}',
                  'busca=pat-0', 'q=ergonomica', 'status_documental=SEM_LASTRO', 'ano=xx')}})
print('FLASK_JSON ' + json.dumps(saida))
"""


def flask(dsn, comprovante):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT, str(PESSOAL), str(EMPRESA), str(comprovante), str(ANO)], cwd=ROOT,
                       env=env, capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


@pytest.fixture(scope='module')
def cenario(cluster):  # noqa: F811
    dsn = copiar(cluster)
    comprovante = sql(dsn, "insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, data_documento, prestador_nome, "
                           "valor, status, hash_arquivo, created_at, updated_at) values (%s, %s, '2031-03-09', "
                           "'Fornecedor ficticio LTDA', 7500.55, 'IMPORTADO', repeat('a', 64), now(), now()) returning id",
                      (EMPRESA, ANO))[0]['id']
    return dsn, flask(dsn, comprovante)


def test_privilegios(cenario):
    dsn, _ = cenario
    for funcao, esperado in (('financeiro.patrimonio_contas_tela(integer, boolean)', (True, False)),
                             ('financeiro.patrimonio_conta_tela(integer, integer)', (True, False)),
                             ('financeiro.patrimonio_transferencias_tela(integer, date, date, integer, integer)', (True, False)),
                             ('financeiro.patrimonio_bens_tela(integer, jsonb, integer)', (True, False)),
                             ('financeiro.patrimonio_resumo_tela(integer)', (True, False)),
                             ('financeiro.bem_flask(public.bem_patrimonial)', (False, False)),
                             ('financeiro.documento_do_bem(public.bem_patrimonial)', (False, False))):
        r = sql(dsn, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                     "has_function_privilege('anon', %s, 'execute') as n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == esperado, funcao


def test_caixinhas_iguais_ao_flask(cenario):
    dsn, s = cenario
    novo = rpc(dsn, 'patrimonio_contas_tela', PESSOAL, None)
    assert len(s['contas']['data']) == 2
    igual({k: s['contas'][k] for k in ('data', 'total', 'total_patrimonio')}, novo, 'contas')
    igual({k: s['inativas'][k] for k in ('data', 'total', 'total_patrimonio')}, rpc(dsn, 'patrimonio_contas_tela', PESSOAL, False), 'inativas')
    igual(s['conta']['data'], rpc(dsn, 'patrimonio_conta_tela', PESSOAL, s['ids'][0]), 'conta')
    assert novo['data'][1]['meta'] is None  # meta 0 vira null, como no Flask


def test_transferencias_iguais_ao_flask(cenario):
    dsn, s = cenario
    igual(s['transf']['data'], rpc(dsn, 'patrimonio_transferencias_tela', PESSOAL, None, None, None, None), 'transf')
    igual(s['transf_filtro']['data'], rpc(dsn, 'patrimonio_transferencias_tela', PESSOAL, '2031-02-01', None, s['ids'][1], None), 'filtro')
    um = s['transf_um']['data']
    igual(um, rpc(dsn, 'patrimonio_transferencias_tela', PESSOAL, None, None, None, um['id'])[0], 'transf_um')


def test_bens_resumo_e_filtros_iguais_ao_flask(cenario):
    dsn, s = cenario
    novo = rpc(dsn, 'patrimonio_bens_tela', EMPRESA, {}, None)
    igual(s['bens']['data'], novo, 'bens')
    doc = next(b for b in novo if b['id'] == s['bens_ids'][0])
    assert doc['documento']['tipo_vinculo_label'] == 'Recibo' and doc['documento_label'].startswith('Recibo ')
    assert doc['imagem_url'] == '/static/img/Patrimonio_notebook.jpg'
    igual(s['bem']['data'], rpc(dsn, 'patrimonio_bens_tela', EMPRESA, {}, s['bens_ids'][0]), 'bem')
    resumo = rpc(dsn, 'patrimonio_resumo_tela', EMPRESA)
    igual(s['resumo']['data'], resumo, 'resumo')
    for consulta, resposta in s['filtros'].items():
        filtros = dict(p.split('=', 1) for p in consulta.split('&'))
        igual(resposta['data'], rpc(dsn, 'patrimonio_bens_tela', EMPRESA, filtros, None), consulta)
    igual(s['imagens']['data'], rpc(dsn, 'imagens_patrimonio'), 'imagens')


def test_pessoal_sem_bens_e_isolamento(cenario):
    dsn, s = cenario
    assert s['bens_pessoal']['data'] == [] == rpc(dsn, 'patrimonio_bens_tela', PESSOAL, {}, None)
    igual(s['resumo_pessoal']['data'], rpc(dsn, 'patrimonio_resumo_tela', PESSOAL), 'resumo_pessoal')
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'patrimonio_bens_tela', PESSOAL, {}, s['bens_ids'][0])
    assert erro.value.pgcode == '42501'
    antes = sql(dsn, 'select (select count(*) from public.conta_patrimonio) c, (select count(*) from public.bem_patrimonial) b')[0]
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'patrimonio_contas_tela', PESSOAL, None, usuario=USUARIO_B)
    assert erro.value.pgcode == '42501'
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'patrimonio_conta_tela', PERFIL_B, s['ids'][0], usuario=USUARIO_B)
    assert erro.value.diag.message_primary == 'Conta não encontrada'
    assert rpc(dsn, 'patrimonio_transferencias_tela', PERFIL_B, None, None, None, None, usuario=USUARIO_B) == []
    assert sql(dsn, 'select (select count(*) from public.conta_patrimonio) c, (select count(*) from public.bem_patrimonial) b')[0] == antes
