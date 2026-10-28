"""
Testes FIN-RELATORIOS-CONFIG-1 (B2) — scripts/backup_banco.py em clusters PostgreSQL descartaveis: o backup do banco
(com documentos ficticios) restaura num banco novo com o mesmo conteudo; o arquivo separado de documentos existe; a
integridade e conferida por SHA-256 (arquivo alterado e recusado); restaurar sobre banco existente e recusado; a
conexao nunca aparece na saida.
"""
import base64
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
