"""
Testes FIN-RELATORIOS-CONFIG-1 (B2) — scripts/backup_banco.py em clusters PostgreSQL descartaveis: o backup do banco
(com documentos ficticios) restaura num banco novo com o mesmo conteudo; o arquivo separado de documentos existe; a
integridade e conferida por SHA-256 (arquivo alterado e recusado); restaurar sobre banco existente e recusado; a
conexao nunca aparece na saida.
"""
import base64
import os
import json
import sys
import uuid
from pathlib import Path

import pytest

from tests.supabase_local import ClusterLocal
from tests.test_supabase_cartoes import rpc
from tests.test_supabase_integracao_1123_1126 import resumo_tabelas
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, atribuir, chamar, cluster, copiar  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import backup_banco as B  # noqa: E402

PNG = b'\x89PNG\r\n\x1a\n' + b'arquivo ficticio de backup ' * 30


@pytest.fixture
def origem(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    chamar(dsn, USUARIO_A, 'select financeiro.enviar_comprovante(%s, %s::jsonb, %s, %s)',
           (ID['PESSOAL'], json.dumps({'nome_arquivo': 'backup.png', 'ano_calendario': 2027}), base64.b64encode(PNG).decode(),
            str(uuid.uuid4())))
    rpc(dsn, 'criar_despesa', ID['PESSOAL'], {'nome': 'Despesa backup (ficticia)', 'valor': 10, 'categoria_id': 951,
                                              'data_vencimento': '2027-03-10', 'recorrente': False}, str(uuid.uuid4()))
    return dsn


def test_backup_restaura_igual_num_banco_novo_e_recusa_banco_existente(origem, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('CF_BACKUP_ORIGEM', origem)
    manifesto = B.main(['exportar', '--dsn-env', 'CF_BACKUP_ORIGEM', '--saida', str(tmp_path / 'bk')])
    dados = json.loads(Path(manifesto).read_text(encoding='utf-8'))
    assert dados['linhas']['public.ir_comprovante_arquivo'] == 1 and len(dados['arquivos']) == 3
    B.main(['verificar', '--manifesto', str(manifesto)])
    # Destino: banco novo e vazio num outro cluster descartavel (so o shim do Supabase: papeis e auth).
    with ClusterLocal(PG_BIN, tmp_path / 'destino') as destino:
        destino.aplicar_shim()
        monkeypatch.setenv('CF_BACKUP_DESTINO', destino.dsn())
        B.main(['restaurar', '--manifesto', str(manifesto), '--dsn-env', 'CF_BACKUP_DESTINO'])
        assert resumo_tabelas(destino.dsn()) == resumo_tabelas(origem)
        conn = psycopg2.connect(destino.dsn())
        with conn.cursor() as cur:
            cur.execute('select conteudo from public.ir_comprovante_arquivo')
            assert bytes(cur.fetchone()[0]) == PNG
        conn.close()
        with pytest.raises(SystemExit) as e:  # de novo no mesmo banco (ja tem tabelas)
            B.main(['restaurar', '--manifesto', str(manifesto), '--dsn-env', 'CF_BACKUP_DESTINO'])
        assert 'nao esta vazio' in str(e.value)
    saida = capsys.readouterr()
    assert origem not in saida.out + saida.err


def _como_supabase(dsn):
    """FIN-BLOCO-D-2: o que o projeto real tem a mais que o shim: historico das migrations e auth.identities (com FK para
    auth.users e coluna gerada), e o e-mail confirmado das contas."""
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute('create schema supabase_migrations')
        cur.execute('create table supabase_migrations.schema_migrations (version text primary key, statements text[], name text)')
        cur.execute("insert into supabase_migrations.schema_migrations (version, name) values ('20261020120000', 'base'), "
                    "('20261126090000', 'patrimonio')")
        cur.execute('alter table auth.users add column email_confirmed_at timestamptz')
        cur.execute('update auth.users set email_confirmed_at = now()')
        cur.execute("create table auth.identities (id uuid primary key default gen_random_uuid(), provider text not null, "
                    "user_id uuid not null references auth.users (id) on delete cascade, identity_data jsonb not null, "
                    "email text generated always as (lower(identity_data ->> 'email')) stored)")
        cur.execute("insert into auth.identities (provider, user_id, identity_data) "
                    "select 'email', id, jsonb_build_object('email', email) from auth.users")
    conn.close()


def test_backup_completo_homologado_num_banco_sem_auth(origem, tmp_path, monkeypatch, capsys):
    """FIN-BLOCO-D-2: backup com privilegios, historico das migrations e contas do Auth; restaurado num banco de
    conferencia (sem o Auth do Supabase e com os privilegios padrao da plataforma para anon/authenticated) fica IGUAL."""
    _como_supabase(origem)
    monkeypatch.setenv('CF_BACKUP_ORIGEM', origem)
    manifesto = B.main(['exportar', '--dsn-env', 'CF_BACKUP_ORIGEM', '--saida', str(tmp_path / 'bk')])
    dados = json.loads(Path(manifesto).read_text(encoding='utf-8'))
    assert dados['esquemas'] == ['public', 'financeiro', 'supabase_migrations'] and dados['snapshot_unico']
    assert dados['auth'] == ['auth.users', 'auth.identities'] and dados['linhas_auth']['auth.identities'] >= 2
    assert dados['retrato']['migrations'] == ['20261020120000', '20261126090000'] and dados['retrato']['privilegios']
    assert origem not in Path(manifesto).read_text(encoding='utf-8')
    with ClusterLocal(PG_BIN, tmp_path / 'destino') as destino:
        destino.aplicar_shim()  # traz os privilegios padrao da plataforma (ALL para anon/authenticated no public)
        conn = psycopg2.connect(destino.dsn())
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute('drop table auth.users')  # banco de conferencia: as contas vem do backup, com a estrutura
        conn.close()
        monkeypatch.setenv('CF_BACKUP_DESTINO', destino.dsn())
        resultado = B.main(['restaurar', '--manifesto', str(manifesto), '--dsn-env', 'CF_BACKUP_DESTINO'])
        assert resultado['homologacao'].startswith('HOMOLOGADO')
        assert any('auth.identities' in r for r in resultado['restaurado']) and resultado['depende_do_supabase']
        assert B.comparar(dados['retrato'], B.retrato_dsn(destino.dsn())) == []
        assert resumo_tabelas(destino.dsn()) == resumo_tabelas(origem)
        # Nenhum privilegio a mais para anon que na origem (a armadilha dos privilegios padrao).
        anon = "select count(*) from pg_class c, aclexplode(c.relacl) a where c.relnamespace = 'public'::regnamespace " \
               "and a.grantee = 'anon'::regrole"
        for dsn in (origem, destino.dsn()):
            c = psycopg2.connect(dsn)
            with c.cursor() as cur:
                cur.execute(anon)
                n = cur.fetchone()[0]
            c.close()
            assert n == 0
    assert origem not in capsys.readouterr().out


def test_restauracao_divergente_nao_e_homologada(origem, tmp_path, monkeypatch):
    monkeypatch.setenv('CF_BACKUP_ORIGEM', origem)
    manifesto = B.main(['exportar', '--dsn-env', 'CF_BACKUP_ORIGEM', '--saida', str(tmp_path / 'bk')])
    original = B.retrato_dsn
    monkeypatch.setattr(B, 'retrato_dsn', lambda dsn, **kw: {**original(dsn, **kw), 'funcoes': {}})
    with ClusterLocal(PG_BIN, tmp_path / 'destino') as destino:
        destino.aplicar_shim()
        monkeypatch.setenv('CF_BACKUP_DESTINO', destino.dsn())
        with pytest.raises(SystemExit) as e:
            B.main(['restaurar', '--manifesto', str(manifesto), '--dsn-env', 'CF_BACKUP_DESTINO'])
        assert 'NAO HOMOLOGADO' in str(e.value)


def test_arquivo_alterado_e_recusado(origem, tmp_path, monkeypatch):
    monkeypatch.setenv('CF_BACKUP_ORIGEM', origem)
    manifesto = Path(B.main(['exportar', '--dsn-env', 'CF_BACKUP_ORIGEM', '--saida', str(tmp_path)]))
    banco = manifesto.parent / json.loads(manifesto.read_text(encoding='utf-8'))['banco']
    conteudo = bytearray(banco.read_bytes())
    conteudo[len(conteudo) // 2] ^= 0xFF  # um byte trocado no meio do arquivo
    banco.write_bytes(bytes(conteudo))
    with pytest.raises(SystemExit) as e:
        B.main(['verificar', '--manifesto', str(manifesto)])
    assert 'alterados ou corrompidos' in str(e.value)


def test_conexao_so_por_variavel_de_ambiente(monkeypatch):
    monkeypatch.delenv('CF_BACKUP_VAZIA', raising=False)
    with pytest.raises(SystemExit) as e:
        B.main(['exportar', '--dsn-env', 'CF_BACKUP_VAZIA', '--saida', 'x'])
    assert 'vazia' in str(e.value)


# FIN-PRE-PRODUCAO-1 (3.2): o Supabase usa PostgreSQL 17. Com CF_PG17_BIN (pasta bin do PostgreSQL 17), o backup e a
# restauracao sao ensaiados em servidores 17 descartaveis: com as ferramentas 17 (procedimento recomendado,
# CF_PG_BIN_BACKUP) e com as ferramentas da maquina (18) extraindo de um 17 e restaurando noutro 17.
PG17_BIN = os.environ.get('CF_PG17_BIN')


def _origem_17(cluster17):
    from tests.supabase_local import semear_recorrencias
    cluster17.preparar(contas=False)  # o mesmo cenario do cluster de 18 (test_supabase_recorrencia)
    conn = cluster17.conectar()
    with conn.cursor() as cur:
        semear_recorrencias(cur)
    conn.close()
    dsn = cluster17.dsn()
    atribuir(dsn, 'PESSOAL')
    chamar(dsn, USUARIO_A, 'select financeiro.enviar_comprovante(%s, %s::jsonb, %s, %s)',
           (ID['PESSOAL'], json.dumps({'nome_arquivo': 'backup17.png', 'ano_calendario': 2027}), base64.b64encode(PNG).decode(),
            str(uuid.uuid4())))
    rpc(dsn, 'criar_despesa', ID['PESSOAL'], {'nome': 'Despesa backup 17 (ficticia)', 'valor': 10, 'categoria_id': 951,
                                              'data_vencimento': '2027-03-10', 'recorrente': False}, str(uuid.uuid4()))
    return dsn


@pytest.mark.skipif(not PG17_BIN, reason='CF_PG17_BIN (binarios do PostgreSQL 17) nao definida')
@pytest.mark.parametrize('ferramentas', ['17', 'maquina'])
def test_pg17_backup_restaura_igual_e_recusa_banco_existente(ferramentas, tmp_path, monkeypatch):
    if ferramentas == '17':
        monkeypatch.setenv('CF_PG_BIN_BACKUP', PG17_BIN)
    else:
        monkeypatch.delenv('CF_PG_BIN_BACKUP', raising=False)
    with ClusterLocal(PG17_BIN, tmp_path / 'origem17') as c17:
        origem = _origem_17(c17)
        assert psycopg2.connect(origem).server_version // 10000 == 17
        monkeypatch.setenv('CF_BACKUP_ORIGEM', origem)
        manifesto = B.main(['exportar', '--dsn-env', 'CF_BACKUP_ORIGEM', '--saida', str(tmp_path / 'bk')])
        B.main(['verificar', '--manifesto', str(manifesto)])
        with ClusterLocal(PG17_BIN, tmp_path / 'destino17') as destino:
            destino.aplicar_shim()
            monkeypatch.setenv('CF_BACKUP_DESTINO', destino.dsn())
            B.main(['restaurar', '--manifesto', str(manifesto), '--dsn-env', 'CF_BACKUP_DESTINO'])
            assert resumo_tabelas(destino.dsn()) == resumo_tabelas(origem)
            with pytest.raises(SystemExit) as e:
                B.main(['restaurar', '--manifesto', str(manifesto), '--dsn-env', 'CF_BACKUP_DESTINO'])
            assert 'nao esta vazio' in str(e.value)
