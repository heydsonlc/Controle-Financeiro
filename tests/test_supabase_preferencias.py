"""
Testes FIN-PRE-PRODUCAO-1 (2.4) — Preferencias no novo aplicativo (migration 20261201090000): financeiras e
operacionais por perfil, gerais de interface por usuario, em cluster PostgreSQL local descartavel.

Valores-padrao iguais aos que o Flask devolve (GET /api/preferencias num banco sem preferencias); cada campo no seu
escopo; perfil so por quem o gere; um usuario com varios perfis; isolamento entre usuarios; validacao atomica (nada e
gravado se um campo for invalido); campos desconhecidos ignorados (como o Flask); privilegios e a reversao.
"""
import json
import os
import subprocess
import sys

import pytest

from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    ROOT,
    USUARIO_A,
    USUARIO_B,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, EMPRESA, PERFIL_B = ID['PESSOAL'], ID['EMPRESA'], ID['PERFIL_B']
REVERSAO = ROOT / 'supabase' / 'reversao' / '20261201090000_remover_preferencias.sql'
MIGRATION = ROOT / 'supabase' / 'migrations' / '20261201090000_financeiro_preferencias.sql'

_SCRIPT = """
import json, uuid
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    email = f'flask.pref.{uuid.uuid4().hex[:8]}@teste.local'
    u = Usuario(email=email, nome='Pref', ativo=True)
    u.definir_senha('Senha-ficticia-pref-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-pref-2026'}).status_code == 302
print('FLASK_JSON ' + json.dumps(c.get('/api/preferencias').get_json()))
"""


def tela(dsn, perfil=PESSOAL, usuario=USUARIO_A):
    return chamar(dsn, usuario, 'select financeiro.preferencias_tela(%s)', (perfil,))


def salvar(dsn, dados, perfil=PESSOAL, usuario=USUARIO_A):
    return chamar(dsn, usuario, 'select financeiro.salvar_preferencias(%s, %s::jsonb)', (perfil, json.dumps(dados)))


def gravadas(dsn):
    return (sql(dsn, 'select * from financeiro.preferencia_usuario order by user_id'),
            sql(dsn, 'select * from financeiro.preferencia_perfil order by perfil_financeiro_id'))


def test_padroes_iguais_aos_do_flask(cluster):
    dsn = copiar(cluster)
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    flask = json.loads(linha[len('FLASK_JSON '):])['data']
    novo = tela(dsn)
    fora = {'id', 'ultimo_backup', 'backup_automatico'}  # backup: o novo aplicativo usa o backup do banco
    assert {k: v for k, v in flask.items() if k not in fora} == {k: (float(v) if k == 'renda_principal' else v) for k, v in novo['data'].items()}
    assert set(novo['escopo']) == set(flask) - fora
    assert novo['pode_gerir_perfil'] is True


def test_cada_campo_no_seu_escopo_e_um_usuario_com_varios_perfis(cluster):
    dsn = copiar(cluster)
    sql(dsn, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s", (EMPRESA,))
    salvar(dsn, {'nome_usuario': ' Fulano Ficticio ', 'tema_sistema': 'claro', 'cor_principal': '#10B981', 'renda_principal': '8500.456',
                 'mes_inicio_planejamento': 3, 'dia_fechamento_mes': '10', 'vincular_pagamento_cartao_auto': False, 'campo_inexistente': 1})
    salvar(dsn, {'renda_principal': 20000, 'orcamento_por_categoria': False}, perfil=EMPRESA)
    pessoal, empresa = tela(dsn)['data'], tela(dsn, EMPRESA)['data']
    # Interface: a mesma nos dois perfis do usuario.
    for d in (pessoal, empresa):
        assert (d['nome_usuario'], d['tema_sistema'], d['cor_principal']) == ('Fulano Ficticio', 'claro', '#10b981')
    # Financeiras: de cada perfil.
    assert (float(pessoal['renda_principal']), pessoal['mes_inicio_planejamento'], pessoal['dia_fechamento_mes'],
            pessoal['vincular_pagamento_cartao_auto'], pessoal['orcamento_por_categoria']) == (8500.46, 3, 10, False, True)
    assert (float(empresa['renda_principal']), empresa['mes_inicio_planejamento'], empresa['orcamento_por_categoria'],
            empresa['vincular_pagamento_cartao_auto']) == (20000.0, 1, False, True)
    usuarios, perfis = gravadas(dsn)
    assert [u['user_id'] for u in usuarios] == [USUARIO_A['id']]
    assert [p['perfil_financeiro_id'] for p in perfis] == sorted([PESSOAL, EMPRESA])
    assert {p['atualizado_por'] for p in perfis} == {USUARIO_A['id']}


def test_perfil_so_por_quem_gere_e_nada_gravado(cluster):
    dsn = copiar(cluster)  # no cenario, A e LEITOR na Empresa
    assert tela(dsn, EMPRESA)['pode_gerir_perfil'] is False
    with pytest.raises(psycopg2.Error) as e:
        salvar(dsn, {'tema_sistema': 'claro', 'renda_principal': 1}, perfil=EMPRESA)
    assert e.value.pgcode == '42501'
    assert gravadas(dsn) == ([], [])  # nem a parte do usuario foi gravada
    salvar(dsn, {'tema_sistema': 'auto'}, perfil=EMPRESA)  # so interface: o leitor altera as suas
    assert tela(dsn)['data']['tema_sistema'] == 'auto'


def test_isolamento_entre_usuarios(cluster):
    dsn = copiar(cluster)
    salvar(dsn, {'nome_usuario': 'Usuario A (ficticio)', 'renda_principal': 100})
    b = tela(dsn, PERFIL_B, USUARIO_B)['data']
    assert b['nome_usuario'] == 'Usuário' and float(b['renda_principal']) == 0
    for funcao in (lambda: tela(dsn, PESSOAL, USUARIO_B), lambda: salvar(dsn, {'renda_principal': 1}, PESSOAL, USUARIO_B),
                   lambda: tela(dsn, PESSOAL, None)):
        with pytest.raises(psycopg2.Error):
            funcao()
    assert float(tela(dsn)['data']['renda_principal']) == 100


@pytest.mark.parametrize('dados', [{'tema_sistema': 'roxo'}, {'cor_principal': 'blue'}, {'mes_inicio_planejamento': 13},
                                   {'dia_corte_fatura': 0}, {'dia_fechamento_mes': 2.5}, {'renda_principal': -1},
                                   {'renda_principal': 'abc'}, {'abreviar_valores': 'sim'}, {'lancamentos_agrupados': None},
                                   {'nome_usuario': 'x' * 101}])
def test_validacao_atomica(cluster, dados):
    dsn = copiar(cluster)
    with pytest.raises(psycopg2.Error) as e:
        salvar(dsn, {'nome_usuario': 'Antes do erro', **dados})
    assert e.value.pgcode == '22023'
    assert gravadas(dsn) == ([], [])


def test_privilegios(cluster):
    dsn = copiar(cluster)
    linhas = sql(dsn, """select p.proname n, has_function_privilege('authenticated', p.oid, 'EXECUTE') a,
                                has_function_privilege('anon', p.oid, 'EXECUTE') x
                           from pg_proc p join pg_namespace s on s.oid = p.pronamespace
                          where s.nspname = 'financeiro' and (p.proname like 'pref\\_%%' or p.proname like '%%preferencias%%')""")
    assert {r['n']: (r['a'], r['x']) for r in linhas} == {'pref_campos': (False, False), 'pref_valor': (False, False),
                                                          'preferencias_tela': (True, False), 'salvar_preferencias': (True, False)}
    for tabela in ('financeiro.preferencia_usuario', 'financeiro.preferencia_perfil'):
        assert not sql(dsn, f"select 1 where has_table_privilege('authenticated', '{tabela}', 'SELECT') "
                            f"or has_table_privilege('authenticated', '{tabela}', 'UPDATE')")


def _executar(dsn, caminho):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(caminho.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_recusa_com_preferencias_e_reaplica(cluster):
    dsn = copiar(cluster)
    salvar(dsn, {'tema_sistema': 'claro'})
    with pytest.raises(psycopg2.Error, match='Reversao recusada'):
        _executar(dsn, REVERSAO)
    assert tela(dsn)['data']['tema_sistema'] == 'claro'
    sql(dsn, 'delete from financeiro.preferencia_usuario')
    _executar(dsn, REVERSAO)
    assert not sql(dsn, "select 1 from pg_proc where proname in ('preferencias_tela', 'salvar_preferencias')")
    _executar(dsn, MIGRATION)
    assert tela(dsn)['data']['tema_sistema'] == 'escuro'
