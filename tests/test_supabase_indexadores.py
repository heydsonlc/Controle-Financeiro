"""
Testes FIN-PRE-PRODUCAO-1 (2.1) — Indexadores: TR mensal dos financiamentos SAC/TR no novo aplicativo (migration
20261129090000), em cluster PostgreSQL local descartavel e com valores de TR FICTICIOS (competencias de 2036).

Fidelidade: a mesma sequencia (cadastro, erros de validacao, edicao, importacao com e sem sobrescrever, TR ja usada em
financiamento SAC/TR, listagens e faltantes) e feita pelo PROPRIO Flask numa copia e pelas funcoes novas noutra; as
respostas e as linhas de public.indice_tr_mensal sao comparadas, fora carimbos de hora. Tambem: acesso (consulta com
perfil, gravacao so de quem gere um perfil ativo), idempotencia, auditoria, o motor lendo a TR cadastrada, privilegios
e a reversao.
"""
import json
import os
import subprocess
import sys
import uuid

import pytest

from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    ROOT,
    USUARIO_A,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
REVERSAO = ROOT / 'supabase' / 'reversao' / '20261129090000_remover_indexadores.sql'
MIGRATION = ROOT / 'supabase' / 'migrations' / '20261129090000_financeiro_indexadores.sql'
SEM_HORA = {'criado_em', 'atualizado_em'}
TEXTO_IMPORTACAO = 'competencia;valor\n2036-03;0,15\n2036-04;0.2\nlixo\n2036-13;1\n2036-01;0,5\n2036-05;12\n\n2036-03 , 0,3'
LEITOR = {'id': 'c0ffee00-0000-4000-8000-0000000000aa', 'email': 'leitor.tr@teste.local'}

# (nome, metodo, rota, corpo): a mesma sequencia nos dois sistemas.
PASSOS = [
    ('criar', 'POST', '/api/indexadores/tr', {'competencia': '2036-01', 'valor_percentual': '0,16', 'fonte': 'BACEN'}),
    ('duplicada', 'POST', '/api/indexadores/tr', {'competencia': '2036-01', 'valor_percentual': '0,16'}),
    ('mes_invalido', 'POST', '/api/indexadores/tr', {'competencia': '2036-13', 'valor_percentual': '0,1'}),
    ('formato_invalido', 'POST', '/api/indexadores/tr', {'competencia': '2036/01', 'valor_percentual': '0,1'}),
    ('acima_de_10', 'POST', '/api/indexadores/tr', {'competencia': '2036-02', 'valor_percentual': '10,5'}),
    ('negativa', 'POST', '/api/indexadores/tr', {'competencia': '2036-02', 'valor_percentual': '-0,1'}),
    ('nao_numerica', 'POST', '/api/indexadores/tr', {'competencia': '2036-02', 'valor_percentual': 'abc'}),
    ('sem_valor', 'POST', '/api/indexadores/tr', {'competencia': '2036-02', 'valor_percentual': ''}),
    ('criar_usada', 'POST', '/api/indexadores/tr', {'competencia': '2036-02', 'valor_percentual': '0.0812345', 'fonte': ''}),
    ('editar', 'PUT', '/api/indexadores/tr/2036-01', {'valor_percentual': '0,1234 %', 'fonte': 'Manual'}),
    ('editar_sem_fonte', 'PUT', '/api/indexadores/tr/2036-01', {'valor_percentual': '0,12345'}),
    ('editar_inexistente', 'PUT', '/api/indexadores/tr/2036-09', {'valor_percentual': '0,1'}),
    ('editar_usada', 'PUT', '/api/indexadores/tr/2036-02', {'valor_percentual': '0,2'}),
    ('importar', 'POST', '/api/indexadores/tr/importar', {'texto': TEXTO_IMPORTACAO, 'fonte': 'IMP'}),
    ('importar_sobrescrever', 'POST', '/api/indexadores/tr/importar',
     {'texto': '2036-03;0,31\n2036-02;0,4\n2036-06;0,06', 'fonte': '', 'sobrescrever': True}),
    ('importar_vazio', 'POST', '/api/indexadores/tr/importar', {'texto': '   '}),
    ('listar', 'GET', '/api/indexadores/tr', None),
    ('listar_ano', 'GET', '/api/indexadores/tr?ano=2036', None),
    ('listar_intervalo', 'GET', '/api/indexadores/tr?inicio=2036-02&fim=2036-04', None),
    ('listar_invalido', 'GET', '/api/indexadores/tr?inicio=2036-1', None),
    ('faltantes', 'GET', '/api/indexadores/tr/faltantes?inicio=2035-11&fim=2036-08', None),
    ('faltantes_invertido', 'GET', '/api/indexadores/tr/faltantes?inicio=2036-08&fim=2036-01', None),
]

_SCRIPT = """
import json, sys, uuid
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    email = f'flask.tr.{uuid.uuid4().hex[:8]}@teste.local'
    u = Usuario(email=email, nome='TR', ativo=True)
    u.definir_senha('Senha-ficticia-tr-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-tr-2026'}).status_code == 302
saida = []
for nome, metodo, rota, corpo in json.loads(sys.argv[1]):
    r = c.open(rota, method=metodo, json=corpo)
    saida.append([nome, r.status_code, r.get_json()])
print('FLASK_JSON ' + json.dumps(saida))
"""


def chave():
    return str(uuid.uuid4())


def com_financiamento_sac_tr(dsn):
    """Financiamento SAC/TR FICTICIO com parcela em 2036-02 (a TR dessa competencia fica 'usada')."""
    fin = sql(dsn, "insert into public.financiamento (perfil_financeiro_id, nome, produto, sistema_amortizacao, indexador_saldo, "
                   "valor_financiado, prazo_total_meses, prazo_remanescente_meses, taxa_juros_nominal_anual, taxa_juros_mensal, "
                   "data_contrato, data_primeira_parcela, seguro_tipo, valor_seguro_mensal, ativo) values (%s, 'Imovel TR ficticio', "
                   "'Imovel', 'SAC', 'TR', 1000, 1, 1, 12, 0.009489, '2036-01-10', '2036-02-10', 'fixo', 0, true) returning id",
               (PESSOAL,))[0]['id']
    sql(dsn, "insert into public.financiamento_parcela (perfil_financeiro_id, financiamento_id, numero_parcela, data_vencimento, "
             "valor_amortizacao, valor_juros, valor_seguro, valor_taxa_adm, valor_previsto_total, valor_pago, saldo_devedor_apos_pagamento, "
             "status) values (%s, %s, 1, '2036-02-10', 1000, 0, 0, 0, 1000, 0, 0, 'pendente')", (PESSOAL, fin))


def pelo_flask(dsn):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT, json.dumps(PASSOS)], cwd=ROOT, env=env, capture_output=True, text=True,
                       timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return {nome: (status, corpo) for nome, status, corpo in json.loads(linha[len('FLASK_JSON '):])}


def _parametros(rota):
    base, _, consulta = rota.partition('?')
    return base, dict(p.split('=') for p in consulta.split('&') if p)


def pelo_novo(dsn, usuario=USUARIO_A):
    """As mesmas rotas, respondidas pelas funcoes novas no formato do Flask (como o adaptador da tela)."""
    saida = {}
    for nome, metodo, rota, corpo in PASSOS:
        base, p = _parametros(rota)
        try:
            if base == '/api/indexadores/tr' and metodo == 'GET':
                itens = chamar(dsn, usuario, 'select financeiro.tr_oficial_tela(%s, %s, %s)',
                               (int(p['ano']) if 'ano' in p else None, p.get('inicio'), p.get('fim')))
                saida[nome] = (200, {'success': True, 'items': itens})
            elif base == '/api/indexadores/tr/faltantes':
                saida[nome] = (200, {'success': True, 'faltantes': chamar(dsn, usuario, 'select financeiro.tr_faltantes(%s, %s)',
                                                                           (p['inicio'], p['fim']))})
            elif base == '/api/indexadores/tr/importar':
                r = chamar(dsn, usuario, 'select financeiro.importar_tr(%s::jsonb, %s)', (json.dumps(corpo), chave()))
                saida[nome] = (200, {'success': True, **r})
            elif base == '/api/indexadores/tr':
                r = chamar(dsn, usuario, 'select financeiro.criar_tr(%s::jsonb, %s)', (json.dumps(corpo), chave()))
                saida[nome] = (201, {'success': True, 'message': 'TR cadastrada com sucesso.', **r})
            else:
                r = chamar(dsn, usuario, 'select financeiro.editar_tr(%s, %s::jsonb)', (base.rsplit('/', 1)[1], json.dumps(corpo)))
                saida[nome] = (200, {'success': True, 'message': 'TR atualizada com sucesso.', **r})
        except psycopg2.Error as e:
            assert e.pgcode == '22023', (nome, e.pgcode, e.pgerror)
            saida[nome] = (400, {'success': False, 'error': e.diag.message_primary})
    return saida


def sem_hora(valor):
    if isinstance(valor, dict):
        return {k: sem_hora(v) for k, v in valor.items() if k not in SEM_HORA}
    if isinstance(valor, list):
        return [sem_hora(v) for v in valor]
    return float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else valor


def linhas(dsn):
    return [{k: (float(v) if k == 'valor_decimal' else v) for k, v in r.items() if k not in SEM_HORA}
            for r in sql(dsn, "select * from public.indice_tr_mensal where competencia like '2036-%%' order by competencia")]


@pytest.fixture(scope='module')
def comparacao(cluster):
    dsn_flask, dsn_novo = copiar(cluster), copiar(cluster)
    for dsn in (dsn_flask, dsn_novo):
        com_financiamento_sac_tr(dsn)
    return {'flask': pelo_flask(dsn_flask), 'novo': pelo_novo(dsn_novo), 'linhas_flask': linhas(dsn_flask),
            'linhas_novo': linhas(dsn_novo), 'dsn_novo': dsn_novo}


def test_mesmas_respostas_que_o_flask(comparacao):
    flask, novo = comparacao['flask'], comparacao['novo']
    assert set(flask) == set(novo)
    for nome in flask:
        assert novo[nome][0] == flask[nome][0], (nome, novo[nome], flask[nome])
        assert sem_hora(novo[nome][1]) == sem_hora(flask[nome][1]), nome
    # O cenario cobre os casos que importam (nao e uma comparacao vazia).
    assert flask['editar_usada'][0] == 400 and 'já é usada' in flask['editar_usada'][1]['error']
    assert flask['importar'][1]['criados'] == 2 and flask['importar'][1]['ignorados'] == 2 and len(flask['importar'][1]['erros']) == 3
    assert len(flask['importar_sobrescrever'][1]['erros']) == 1 and flask['importar_sobrescrever'][1]['atualizados'] == 1
    assert [i['competencia'] for i in flask['listar_intervalo'][1]['items']] == ['2036-04', '2036-03', '2036-02']
    assert flask['faltantes'][1]['faltantes'] == ['2035-11', '2035-12', '2036-05', '2036-07', '2036-08']


def test_mesmas_linhas_que_o_flask(comparacao):
    assert comparacao['linhas_novo'] == comparacao['linhas_flask']
    por_comp = {r['competencia']: r for r in comparacao['linhas_novo']}
    assert por_comp['2036-01']['valor_decimal'] == 0.0012345 and por_comp['2036-01']['fonte'] == 'Manual'
    assert por_comp['2036-02']['valor_decimal'] == 0.00081235  # 8 casas, meio para cima
    assert por_comp['2036-03']['fonte'] == 'BACEN'  # fonte vazia na importacao = BACEN


def test_auditoria_de_cada_gravacao(comparacao):
    hist = sql(comparacao['dsn_novo'], 'select competencia, operacao, valor_anterior, valor_novo, user_id::text from '
                                       'financeiro.indice_tr_historico order by id')
    assert [(h['competencia'], h['operacao']) for h in hist] == [
        ('2036-01', 'CADASTRO'), ('2036-02', 'CADASTRO'), ('2036-01', 'EDICAO'), ('2036-01', 'EDICAO'),
        ('2036-03', 'IMPORTACAO'), ('2036-04', 'IMPORTACAO'), ('2036-03', 'IMPORTACAO'), ('2036-06', 'IMPORTACAO')]
    assert {h['user_id'] for h in hist} == {USUARIO_A['id']}
    edicao = hist[2]
    assert float(edicao['valor_anterior']) == 0.0016 and float(edicao['valor_novo']) == 0.001234


def test_motor_le_a_tr_cadastrada(cluster):
    dsn = copiar(cluster)
    with pytest.raises(psycopg2.Error, match='Nao ha TR cadastrada para a competencia 2036-07'):
        sql(dsn, "select financeiro.fin_tr('2036-07-10')")
    chamar(dsn, USUARIO_A, 'select financeiro.criar_tr(%s::jsonb, %s)', (json.dumps({'competencia': '2036-07', 'valor_percentual': '0,17'}), chave()))
    assert float(sql(dsn, "select financeiro.fin_tr('2036-07-10') as v")[0]['v']) == 0.0017


def test_acesso_consulta_com_perfil_e_gravacao_so_de_quem_gere(cluster):
    dsn = copiar(cluster)
    sql(dsn, 'insert into auth.users (id, email) values (%s, %s)', (LEITOR['id'], LEITOR['email']))
    sql(dsn, "insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) values (%s, %s, 'LEITOR', false)",
        (LEITOR['id'], PESSOAL))
    assert isinstance(chamar(dsn, LEITOR, 'select financeiro.tr_oficial_tela()'), list)
    for comando, args in (('select financeiro.criar_tr(%s::jsonb, %s)', (json.dumps({'competencia': '2036-01', 'valor_percentual': '1'}), chave())),
                          ('select financeiro.importar_tr(%s::jsonb, %s)', (json.dumps({'texto': '2036-01;1'}), chave())),
                          ('select financeiro.editar_tr(%s, %s::jsonb)', ('2034-01', json.dumps({'valor_percentual': '1'})))):
        with pytest.raises(psycopg2.Error) as e:
            chamar(dsn, LEITOR, comando, args)
        assert e.value.pgcode == '42501'
    # Sem nenhum perfil: nem consulta.
    sql(dsn, 'delete from financeiro.perfil_acesso where user_id = %s', (LEITOR['id'],))
    with pytest.raises(psycopg2.Error) as e:
        chamar(dsn, LEITOR, 'select financeiro.tr_oficial_tela()')
    assert e.value.pgcode == '42501'
    with pytest.raises(psycopg2.Error):
        chamar(dsn, None, 'select financeiro.tr_oficial_tela()')
    assert not sql(dsn, "select 1 from public.indice_tr_mensal where competencia = '2036-01'")


def test_reenvio_com_a_mesma_chave_nao_duplica(cluster):
    dsn = copiar(cluster)
    k = chave()
    dados = json.dumps({'competencia': '2036-08', 'valor_percentual': '0,1'})
    primeira = chamar(dsn, USUARIO_A, 'select financeiro.criar_tr(%s::jsonb, %s)', (dados, k))
    segunda = chamar(dsn, USUARIO_A, 'select financeiro.criar_tr(%s::jsonb, %s)', (dados, k))
    assert segunda['repetida'] is True and segunda['data'] == primeira['data']
    with pytest.raises(psycopg2.Error, match='Chave da operacao ja usada'):
        chamar(dsn, USUARIO_A, 'select financeiro.importar_tr(%s::jsonb, %s)', (json.dumps({'texto': '2036-09;0,1'}), k))
    imp = json.dumps({'texto': '2036-10;0,1\n2036-11;0,1'})
    k2 = chave()
    assert chamar(dsn, USUARIO_A, 'select financeiro.importar_tr(%s::jsonb, %s)', (imp, k2))['criados'] == 2
    assert chamar(dsn, USUARIO_A, 'select financeiro.importar_tr(%s::jsonb, %s)', (imp, k2))['repetida'] is True
    assert sql(dsn, "select count(*) as n from public.indice_tr_mensal where competencia in ('2036-08', '2036-10', '2036-11')")[0]['n'] == 3
    assert sql(dsn, 'select count(*) as n from financeiro.indice_tr_historico')[0]['n'] == 3


def test_privilegios(cluster):
    dsn = copiar(cluster)
    expostas = {r['proname'] for r in sql(dsn, "select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                                               "where n.nspname = 'financeiro' and (p.proname like 'idx\\_%%' or p.proname like '%%\\_tr' "
                                               "or p.proname like 'tr\\_%%') and has_function_privilege('authenticated', p.oid, 'EXECUTE')")}
    assert expostas == {'tr_oficial_tela', 'tr_faltantes', 'criar_tr', 'editar_tr', 'importar_tr'}
    assert not sql(dsn, "select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro' "
                        "and p.proname in ('tr_oficial_tela', 'criar_tr', 'idx_tr_usada') and has_function_privilege('anon', p.oid, 'EXECUTE')")
    for tabela in ('financeiro.operacao_indexador', 'financeiro.indice_tr_historico', 'public.indice_tr_mensal'):
        assert not sql(dsn, f"select 1 where has_table_privilege('authenticated', '{tabela}', 'SELECT') "
                            f"or has_table_privilege('authenticated', '{tabela}', 'INSERT')")


def test_reversao_preserva_a_tr_e_reaplica(cluster):
    dsn = copiar(cluster)
    chamar(dsn, USUARIO_A, 'select financeiro.criar_tr(%s::jsonb, %s)', (json.dumps({'competencia': '2036-12', 'valor_percentual': '0,1'}), chave()))
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(REVERSAO.read_text(encoding='utf-8'))
            cur.execute("select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro' "
                        "and p.proname in ('criar_tr', 'idx_tr_json', 'tr_oficial_tela')")
            assert cur.fetchone()[0] == 0
            cur.execute("select count(*) from public.indice_tr_mensal where competencia = '2036-12'")
            assert cur.fetchone()[0] == 1
            cur.execute(MIGRATION.read_text(encoding='utf-8'))
    finally:
        conn.close()
    assert chamar(dsn, USUARIO_A, 'select financeiro.tr_oficial_tela(2036)')[0]['competencia'] == '2036-12'
