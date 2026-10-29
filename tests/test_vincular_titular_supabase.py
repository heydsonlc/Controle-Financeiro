"""
Testes FIN-BLOCO-D-2 (7) — scripts/vincular_titular_supabase.py: vinculo da conta do titular (Auth) aos perfis
"Pessoal" e "Empresa", num cluster PostgreSQL local DESCARTAVEL com dados ficticios (perfis 101 e 102 fazem o papel
dos perfis 1 e 2 do projeto).

Prova: recusas (conta inexistente, conta de teste, e-mail nao confirmado, perfil com acesso de outra conta); conferencia
sem gravar; vinculo com papel TITULAR e gestao; isolamento (outras contas nao alcancam os perfis; o titular nao alcanca
perfis de outros); repeticao sem duplicar; projeto Supabase so com autorizacao expressa.
"""
import importlib.util
import uuid

import pytest

from tests import supabase_local as L
from tests.test_supabase_integracao_1123_1126 import resumo_tabelas
from tests.test_supabase_recorrencia import PG_BIN, ROOT, chamar, copiar, sql

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

_spec = importlib.util.spec_from_file_location('vincular_titular_supabase', ROOT / 'scripts' / 'vincular_titular_supabase.py')
vinculo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vinculo)

TITULAR = {'id': str(uuid.UUID('f1f1f1f1-0000-4000-8000-0000000000f1')), 'email': 'titular.vinculo@teste.local'}
PESSOAL, EMPRESA, PERFIL_B = L.PERFIS['PESSOAL']['id'], L.PERFIS['EMPRESA']['id'], L.PERFIS['PERFIL_B']['id']
IDENTIDADE = {'projeto_ref_prefixo': 'fzjmge', 'usuarios_teste': [L.USUARIO_B['id']]}


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    with L.ClusterLocal(PG_BIN, tmp_path_factory.mktemp('vinculo')) as c:
        c.preparar()
        conn = c.conectar()
        with conn.cursor() as cur:
            cur.execute('alter table auth.users add column email_confirmed_at timestamptz')  # como no Supabase
            cur.execute('update auth.users set email_confirmed_at = now()')
            cur.execute('insert into auth.users (id, email, email_confirmed_at) values (%s, %s, now())', (TITULAR['id'], TITULAR['email']))
        conn.close()
        yield c


@pytest.fixture
def d(cluster, monkeypatch):
    monkeypatch.setattr(vinculo, 'PERFIS_REAIS', {PESSOAL: 'Pessoal', EMPRESA: 'Empresa'})
    return copiar(cluster)


def executar(dsn, email, confirmar, identidade=IDENTIDADE):
    conn = psycopg2.connect(dsn)
    try:
        return vinculo.vincular(conn, email, identidade, confirmar)
    finally:
        conn.close()


def sem_acessos_previos(dsn):
    sql(dsn, 'delete from financeiro.perfil_acesso where perfil_financeiro_id = any(%s)', ([PESSOAL, EMPRESA],))


def test_recusas_antes_de_vincular(d):
    antes = resumo_tabelas(d)
    with pytest.raises(vinculo.VinculoRecusado, match='0 encontrada'):
        executar(d, 'ninguem@teste.local', confirmar=True)
    with pytest.raises(vinculo.VinculoRecusado, match='conta de teste'):
        executar(d, L.USUARIO_B['email'], confirmar=True)
    with pytest.raises(vinculo.VinculoRecusado, match='acesso\\(s\\) de outra conta'):
        executar(d, TITULAR['email'], confirmar=True)  # o usuario A ainda tem acesso aos perfis
    sem_acessos_previos(d)
    sql(d, 'update auth.users set email_confirmed_at = null where id = %s', (TITULAR['id'],))
    with pytest.raises(vinculo.VinculoRecusado, match='nao confirmado'):
        executar(d, TITULAR['email'], confirmar=True)
    assert not sql(d, 'select 1 from financeiro.perfil_acesso where user_id = %s', (TITULAR['id'],))
    assert set(resumo_tabelas(d)) == set(antes)


def test_conferencia_sem_gravar(d):
    sem_acessos_previos(d)
    antes = resumo_tabelas(d)
    rel = executar(d, TITULAR['email'].upper(), confirmar=False)
    assert rel['resultado'].startswith('CONFERENCIA') and rel['perfis'] == {'Pessoal': 'a vincular', 'Empresa': 'a vincular'}
    assert resumo_tabelas(d) == antes


def test_vinculo_titular_gestor_e_isolamento(d):
    sem_acessos_previos(d)
    rel = executar(d, TITULAR['email'], confirmar=True)
    assert rel['resultado'] == 'VINCULADO' and rel['perfis_vistos_pelo_titular'] == sorted([PESSOAL, EMPRESA])
    meus = chamar(d, TITULAR, 'select json_agg(json_build_object(\'id\', id, \'papel\', papel)) from financeiro.meus_perfis()')
    assert sorted((p['id'], p['papel']) for p in meus) == sorted([(PESSOAL, 'TITULAR'), (EMPRESA, 'TITULAR')])
    for pid in (PESSOAL, EMPRESA):
        assert chamar(d, TITULAR, 'select financeiro.pode_gerir_perfil(%s)', (pid,)) is True
        for outro in (L.USUARIO_A, L.USUARIO_B):  # outras contas nao alcancam os perfis do titular
            assert chamar(d, outro, 'select financeiro.pode_acessar_perfil(%s)', (pid,)) is False
    assert chamar(d, TITULAR, 'select financeiro.pode_acessar_perfil(%s)', (PERFIL_B,)) is False
    with pytest.raises(psycopg2.Error) as e:
        chamar(d, L.USUARIO_B, 'select financeiro.contas_bancarias_tela(%s, %s)', (PESSOAL, 'ATIVO'))
    assert e.value.pgcode == '42501'
    # Repetir nao duplica.
    assert executar(d, TITULAR['email'], confirmar=True)['perfis'] == {'Pessoal': 'ja vinculado', 'Empresa': 'ja vinculado'}
    assert sql(d, 'select count(*) n from financeiro.perfil_acesso where user_id = %s', (TITULAR['id'],))[0]['n'] == 2


def test_projeto_supabase_exige_autorizacao_expressa(monkeypatch, tmp_path, capsys):
    ident = tmp_path / 'identidade.json'
    ident.write_text('{"projeto_ref_prefixo": "fzjmge", "usuarios_teste": []}', encoding='utf-8')
    monkeypatch.setattr(vinculo.psycopg2, 'connect', lambda *a, **k: pytest.fail('nao pode conectar'))
    monkeypatch.setenv('CF_TITULAR_EMAIL', 'titular@teste.local')
    monkeypatch.setenv('CF_VINCULO_DSN', 'postgresql://postgres.fzjmgeexemplo:x@aws-0.pooler.supabase.com:5432/postgres')
    assert vinculo.main(['vincular', '--identidade', str(ident), '--confirmar']) == 2
    assert 'projeto-autorizado' in capsys.readouterr().err
    monkeypatch.setenv('CF_VINCULO_DSN', 'postgresql://postgres.abcdefoutro:x@aws-0.pooler.supabase.com:5432/postgres')
    assert vinculo.main(['conferir', '--identidade', str(ident)]) == 2
    assert 'nao aponta para o projeto' in capsys.readouterr().err
