"""
Testes FIN-FIDELIDADE-DOCUMENTOS-1 (arquivos, leitura) — arquivo do comprovante (migration 20261118090000).

Fidelidade: comprovantes FICTICIOS com arquivo (PDF e imagem, bytes arbitrarios) e sem arquivo; o PROPRIO Flask responde
GET /api/ir/comprovantes/<id>/arquivo e o conteudo (bytes, tipo) e comparado com arquivo_comprovante_tela, inclusive os
erros. Tambem: isolamento entre titulares. So leitura.
"""
import base64
import json
import os
import subprocess
import sys

import pytest

from tests.test_supabase_cartoes import rpc
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
PDF = b'%PDF-1.4\n% ficticio\n' + bytes(range(256)) * 40
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00\xff' * 3000

_SCRIPT = """
import base64, json, sys
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    u = Usuario(email='flask.arquivo@teste.local', nome='Arquivo', ativo=True)
    u.definir_senha('Senha-ficticia-arquivo-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.arquivo@teste.local', 'senha': 'Senha-ficticia-arquivo-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
saida = {}
for i in json.loads(sys.argv[2]):
    r = c.get(f'/api/ir/comprovantes/{i}/arquivo')
    saida[i] = ([r.status_code, r.mimetype, base64.b64encode(r.data).decode()] if r.status_code == 200
                else [r.status_code, r.get_json()])
print('FLASK_JSON ' + json.dumps(saida))
"""


@pytest.fixture(scope='module')
def cenario(cluster):  # noqa: F811
    dsn = copiar(cluster)

    def comprovante(perfil, hash_):
        return sql(dsn, "insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, status, hash_arquivo, created_at, "
                        "updated_at) values (%s, 2031, 'IMPORTADO', %s, now(), now()) returning id", (perfil, hash_))[0]['id']

    ids = [comprovante(PESSOAL, '1' * 64), comprovante(PESSOAL, '2' * 64), comprovante(PESSOAL, '3' * 64),
           comprovante(PERFIL_B, '4' * 64)]
    for cid, nome, mime, conteudo in ((ids[0], 'nota.pdf', 'application/pdf', PDF), (ids[1], 'foto.png', 'image/png', PNG),
                                      (ids[3], 'outro.pdf', 'application/pdf', PDF)):
        sql(dsn, "insert into public.ir_comprovante_arquivo (comprovante_id, nome_arquivo, mime_type, tamanho_bytes, hash_arquivo, "
                 "conteudo, created_at) values (%s, %s, %s, %s, %s, %s, now())",
            (cid, nome, mime, len(conteudo), 'a' * 64, psycopg2.Binary(conteudo)))
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    consulta = ids + [999999]
    r = subprocess.run([sys.executable, '-c', _SCRIPT, str(PESSOAL), json.dumps(consulta)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return dsn, ids, json.loads(linha[len('FLASK_JSON '):])


def test_privilegio(cenario):
    dsn = cenario[0]
    r = sql(dsn, "select has_function_privilege('authenticated', 'financeiro.arquivo_comprovante_tela(integer, integer)', 'execute') a, "
                 "has_function_privilege('anon', 'financeiro.arquivo_comprovante_tela(integer, integer)', 'execute') n")[0]
    assert (r['a'], r['n']) == (True, False)


def test_conteudo_e_erros_iguais_ao_flask(cenario):
    dsn, ids, flask = cenario
    for i, resposta in flask.items():
        if resposta[0] == 200:
            novo = rpc(dsn, 'arquivo_comprovante_tela', PESSOAL, int(i))
            assert base64.b64decode(novo['conteudo_base64']) == base64.b64decode(resposta[2])
            assert novo['mime_type'] == resposta[1]
            continue
        with pytest.raises(psycopg2.Error) as erro:
            rpc(dsn, 'arquivo_comprovante_tela', PESSOAL, int(i))
        assert erro.value.diag.message_primary == resposta[1]['error'], i
    assert flask[str(ids[2])][1]['error'] == 'Arquivo do comprovante nao encontrado'  # comprovante sem arquivo
    assert flask[str(ids[3])][1]['error'] == 'Comprovante nao encontrado'  # de outro perfil
    assert base64.b64decode(rpc(dsn, 'arquivo_comprovante_tela', PESSOAL, ids[0])['conteudo_base64']) == PDF


def test_isolamento(cenario):
    dsn, ids, _ = cenario
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'arquivo_comprovante_tela', PESSOAL, ids[0], usuario=USUARIO_B)
    assert erro.value.pgcode == '42501'
    assert base64.b64decode(rpc(dsn, 'arquivo_comprovante_tela', PERFIL_B, ids[3], usuario=USUARIO_B)['conteudo_base64']) == PDF
