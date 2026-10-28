"""
Testes FIN-RELATORIOS-CONFIG-1 (FIN-BLOCO-B-1, B2) — relatorio de bens patrimoniais (Excel e PDF) do novo aplicativo
(web/src/js/relatorio-patrimonio.js, sem biblioteca) conferido com o do PROPRIO Flask (PatrimonioRelatorioService), sobre
os mesmos bens ficticios num cluster PostgreSQL descartavel. A hora de geracao e fixada nos dois lados (no Flask, so
dentro do subprocesso de teste). PDF: byte a byte. XLSX: abas, valores, formato monetario, estilo do cabecalho, painel
congelado, autofiltro e larguras, lidos pelo openpyxl.
"""
import json
import os
import shutil
import subprocess
import sys
import uuid
from io import BytesIO

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_recorrencia import ID, PG_BIN, ROOT, USUARIO_A, atribuir, chamar, cluster, copiar, sql  # noqa: F401

openpyxl = pytest.importorskip('openpyxl')
psycopg2 = pytest.importorskip('psycopg2')
pytestmark = [pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados'),
              pytest.mark.skipif(shutil.which('node') is None, reason='node nao encontrado')]

EMPRESA = ID['EMPRESA']
AGORA = '01/07/2031 10:30'
BENS = [
    {'nome': 'Notebook (ficticio)', 'codigo': 'PAT-001', 'categoria': 'Informatica', 'valor_aquisicao': 7500.55,
     'data_aquisicao': '2031-03-10', 'fornecedor': 'Loja X', 'status_documental': 'COM_LASTRO'},
    {'nome': 'Cadeira (ficticia)', 'categoria': 'Moveis', 'valor_aquisicao': 1200, 'data_aquisicao': '2029-07-01',
     'status_documental': 'PENDENTE'},
    {'nome': 'Monitor (ficticio)', 'categoria': 'Informatica', 'valor_aquisicao': 980.4, 'status_documental': 'SEM_DOCUMENTO'},
    {'nome': 'Impressora (ficticia)', 'categoria': '', 'valor_aquisicao': 0, 'status_documental': 'NAO_APLICAVEL'},
    {'nome': 'Mesa (ficticia)', 'categoria': 'Moveis', 'valor_aquisicao': 1890.125, 'data_aquisicao': '2031-01-02'},
]

_SCRIPT_FLASK = """
import json, sys, uuid
from datetime import datetime
import backend.services.patrimonio_relatorio_service as prs
class _Agora(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2031, 7, 1, 10, 30)
prs.datetime = _Agora  # hora fixa, so neste subprocesso de teste
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    email = f'flask.rel.{uuid.uuid4().hex[:8]}@teste.local'
    u = Usuario(email=email, nome='Rel', ativo=True)
    u.definir_senha('Senha-ficticia-rel-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-rel-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
saida = {}
for tipo in ('excel', 'pdf'):
    r = c.get('/api/patrimonio/bens/exportar-' + tipo + sys.argv[2])
    assert r.status_code == 200, r.data[:300]
    saida[tipo] = {'hex': r.data.hex(), 'nome': r.headers.get('Content-Disposition')}
print('FLASK_JSON ' + json.dumps(saida))
"""

_SCRIPT_NODE = """
import { excelDeBens, pdfDeBens } from %s;
const entrada = JSON.parse(process.argv[1]);
const x = excelDeBens(entrada), p = pdfDeBens(entrada);
console.log(JSON.stringify({ excel: { hex: Buffer.from(x.conteudo).toString('hex'), nome: x.nome },
                             pdf: { hex: Buffer.from(p.conteudo).toString('hex'), nome: p.nome } }));
"""


def pelo_flask(dsn, consulta):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT_FLASK, str(EMPRESA), consulta], cwd=ROOT, env=env, capture_output=True,
                       text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


def pelo_novo(dsn, filtros):
    bens = chamar(dsn, USUARIO_A, 'select financeiro.patrimonio_bens_tela(%s, %s::jsonb, null)', (EMPRESA, json.dumps(filtros)))
    perfil = sql(dsn, 'select nome from public.perfil_financeiro where id = %s', (EMPRESA,))[0]['nome']
    modulo = json.dumps((ROOT / 'web' / 'src' / 'js' / 'relatorio-patrimonio.js').as_uri())
    entrada = {'perfilNome': perfil, 'bens': bens, 'filtros': filtros, 'agora': AGORA, 'anoAtual': 2031}
    r = subprocess.run(['node', '--input-type=module', '-e', _SCRIPT_NODE % modulo, json.dumps(entrada)], cwd=ROOT,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout), bens


@pytest.fixture(scope='module')
def bens_empresa(cluster):  # noqa: F811
    dsn = copiar(cluster)
    sql(dsn, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s", (EMPRESA,))
    atribuir(dsn, 'EMPRESA')
    for dados in BENS:
        rpc(dsn, 'criar_bem_patrimonial', EMPRESA, dados, str(uuid.uuid4()))
    return dsn


def planilha(conteudo):
    wb = openpyxl.load_workbook(BytesIO(bytes.fromhex(conteudo)))
    saida = {}
    for ws in wb.worksheets:
        saida[ws.title] = {
            'valores': [[c.value for c in linha] for linha in ws.iter_rows()],
            'formatos': [[c.number_format for c in linha] for linha in ws.iter_rows(min_row=2)],
            'cabecalho': [(c.font.b, c.font.color.rgb if c.font.color else None, c.fill.fgColor.rgb, c.alignment.horizontal)
                          for c in ws[1]],
            'congelado': ws.freeze_panes, 'filtro': ws.auto_filter.ref,
            'larguras': {k: d.width for k, d in ws.column_dimensions.items() if d.width},
        }
    return saida


@pytest.mark.parametrize('consulta,filtros', [('', {}), ('?categoria=Informatica&ano=2031', {'categoria': 'Informatica', 'ano': '2031'})])
def test_excel_e_pdf_iguais_ao_flask(bens_empresa, consulta, filtros):
    flask, _ = pelo_flask(bens_empresa, consulta), None
    novo, bens = pelo_novo(bens_empresa, filtros)
    assert bens, 'sem bens no cenario'
    assert novo['pdf']['hex'] == flask['pdf']['hex']  # byte a byte
    f, n = planilha(flask['excel']['hex']), planilha(novo['excel']['hex'])
    assert list(n) == list(f) == ['Resumo', 'Bens']
    for aba in f:
        for chave in f[aba]:
            assert n[aba][chave] == f[aba][chave], (aba, chave, f[aba][chave], n[aba][chave])
    for tipo in ('excel', 'pdf'):
        assert novo[tipo]['nome'] in flask[tipo]['nome']  # Content-Disposition: attachment; filename=...
