"""
Testes FIN-FIDELIDADE-DOCUMENTOS-1 (fase 1) — leitura da tela original de Imposto de Renda, modo IRPF
(migration 20261113090000).

Fidelidade: comprovantes FICTICIOS (com arquivo, eventos, vinculo de lastro, sem data, nao dedutivel) sao gravados no
cluster descartavel; o PROPRIO Flask le /api/ir/contexto, /categorias (que semeia as categorias iniciais),
/categorias-despesa, /categorias-despesa-disponiveis, /comprovantes (com filtros) e /comprovantes/<id>; o resultado e
comparado campo a campo com as funcoes novas. A leitura nova nunca grava.
"""
import json
import os
import subprocess
import sys

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
FILTROS = ('ano=2031', 'status=pendente_revisao', 'status=TODOS&busca=clinica', 'busca=123.456', 'ano=xx&categoria_ir_id=0')

_SCRIPT = """
import json, sys
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    u = Usuario(email='flask.ir@teste.local', nome='IR', ativo=True)
    u.definir_senha('Senha-ficticia-ir-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.ir@teste.local', 'senha': 'Senha-ficticia-ir-2026'}).status_code == 302
pessoal, categoria = int(sys.argv[1]), int(sys.argv[2])
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': pessoal}).status_code == 200
cats = c.get('/api/ir/categorias').get_json()
saude = next(x['id'] for x in cats['data'] if x['nome'] == 'Saude')
assert c.post('/api/ir/categorias-despesa', json={'categoria_id': categoria, 'categoria_ir_id': saude}).status_code == 201
print('FLASK_JSON ' + json.dumps({'saude': saude}))
"""

_LEITURA = """
import json, sys
from backend.app import create_app
from backend.models import Usuario
app = create_app('local')
c = app.test_client()
assert c.post('/login', data={'email': 'flask.ir@teste.local', 'senha': 'Senha-ficticia-ir-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
ids = json.loads(sys.argv[2]); filtros = json.loads(sys.argv[3])
saida = {'contexto': c.get('/api/ir/contexto').get_json(), 'categorias': c.get('/api/ir/categorias').get_json(),
         'vinculos': c.get('/api/ir/categorias-despesa').get_json(),
         'disponiveis': c.get('/api/ir/categorias-despesa-disponiveis').get_json(),
         'lista': c.get('/api/ir/comprovantes').get_json(),
         'filtros': {q: c.get('/api/ir/comprovantes?' + q).get_json() for q in filtros},
         'detalhes': [c.get(f'/api/ir/comprovantes/{i}').get_json() for i in ids]}
if len(sys.argv) > 4:  # perfil Empresa: rotas da central de documentos empresariais
    saida['taxonomia'] = c.get('/api/ir/documentos-empresa/taxonomia').get_json()
    saida['resumo_empresa'] = {q: [r.status_code, r.get_json()] for q in json.loads(sys.argv[4])
                               for r in [c.get('/api/ir/documentos-empresa/resumo?' + q)]}
    saida['metadata'] = {i: [r.status_code, r.get_json()] for i in ids + [999999]
                         for r in [c.get(f'/api/ir/comprovantes/{i}/metadata-empresarial')]}
print('FLASK_JSON ' + json.dumps(saida))
"""

_QUEBRA = """
import json, sys
from backend.app import create_app
app = create_app('local')
c = app.test_client()
assert c.post('/login', data={'email': 'flask.ir@teste.local', 'senha': 'Senha-ficticia-ir-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
saida = {}
for nome, url in (('resumo', '/api/ir/documentos-empresa/resumo'), ('lista', '/api/ir/comprovantes')):
    try:
        r = c.get(url)
        saida[nome] = r.status_code
    except Exception as e:
        saida[nome] = f'{type(e).__name__}: {e}'
print('FLASK_JSON ' + json.dumps(saida))
"""


def flask(dsn, script, *args):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', script, *map(str, args)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


def comprovante(dsn, perfil, **campos):
    comprovante.n = getattr(comprovante, 'n', 0) + 1
    dados = {'perfil_financeiro_id': perfil, 'ano_calendario': 2031, 'status': 'IMPORTADO',
             'hash_arquivo': f'{comprovante.n:064d}', **campos}
    colunas = ', '.join(dados)
    return sql(dsn, f"insert into public.ir_comprovante ({colunas}, created_at, updated_at) values "
                    f"({', '.join(['%s'] * len(dados))}, now(), now()) returning id", tuple(dados.values()))[0]['id']


@pytest.fixture(scope='module')
def cenario(cluster):  # noqa: F811
    dsn = copiar(cluster)
    categoria = sql(dsn, 'select id from public.categoria where ativo order by id limit 1')[0]['id']
    saude = flask(dsn, _SCRIPT, PESSOAL, categoria)['saude']
    ids = [
        comprovante(dsn, PESSOAL, data_documento='2031-05-10', prestador_nome='Clinica Ficticia', prestador_cpf_cnpj='12.345.678/0001-00',
                    valor=350.75, categoria_id=categoria, categoria_ir_id=saude, dedutivel=True, status='PENDENTE_REVISAO',
                    confianca='MEDIA', texto_extraido='texto ficticio do comprovante'),
        comprovante(dsn, PESSOAL, data_documento='2031-03-01', prestador_nome='Escola Ficticia', valor=1200, dedutivel=False,
                    status='VALIDADO', observacoes='mensalidade (ficticia)'),
        comprovante(dsn, PESSOAL, prestador_nome=None, valor=None, ano_calendario=2030),
    ]
    sql(dsn, "insert into public.ir_comprovante_arquivo (comprovante_id, nome_arquivo, mime_type, tamanho_bytes, hash_arquivo, "
             "conteudo, created_at) values (%s, 'clinica.pdf', 'application/pdf', 4, %s, '\\x25504446'::bytea, now())",
        (ids[0], 'b' * 64))
    for tipo in ('UPLOAD', 'OCR'):
        sql(dsn, "insert into public.ir_comprovante_evento (comprovante_id, tipo_evento, descricao, created_at) "
                 "values (%s, %s, 'evento ficticio', now())", (ids[0], tipo))
    sql(dsn, "insert into public.ir_comprovante_vinculo (comprovante_id, perfil_financeiro_id, tipo_entidade, entidade_id, "
             "resumo_entidade, tipo_vinculo, natureza, status_lastro, ativo, created_at, updated_at) values "
             "(%s, %s, 'DESPESA', 1, 'Despesa ficticia', 'COMPROVANTE', 'OUTRO', 'AGUARDANDO_CONTADOR', true, now(), now())",
        (ids[1], PESSOAL))
    antes = sql(dsn, 'select (select count(*) from public.ir_categoria) c, (select count(*) from public.ir_comprovante) d')[0]
    saida = flask(dsn, _LEITURA, PESSOAL, json.dumps(ids), json.dumps(FILTROS))
    return dsn, ids, saida, antes


def test_privilegios(cenario):
    dsn = cenario[0]
    for funcao, esperado in (('financeiro.ir_contexto_tela(integer)', (True, False)),
                             ('financeiro.ir_categorias_tela(integer)', (True, False)),
                             ('financeiro.ir_categorias_despesa_tela(integer, boolean)', (True, False)),
                             ('financeiro.ir_comprovantes_tela(integer, jsonb, integer)', (True, False)),
                             ('financeiro.comprovante_flask(public.ir_comprovante, boolean)', (False, False)),
                             ('financeiro.tipo_perfil_ir(integer)', (False, False))):
        r = sql(dsn, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                     "has_function_privilege('anon', %s, 'execute') as n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == esperado, funcao


def test_contexto_e_categorias_iguais_ao_flask(cenario):
    dsn, _, s, _ = cenario
    igual(s['contexto']['data'], rpc(dsn, 'ir_contexto_tela', PESSOAL), 'contexto')
    igual(s['categorias']['data'], rpc(dsn, 'ir_categorias_tela', PESSOAL), 'categorias')
    igual(s['vinculos']['data'], rpc(dsn, 'ir_categorias_despesa_tela', PESSOAL, False), 'vinculos')
    igual(s['disponiveis']['data'], rpc(dsn, 'ir_categorias_despesa_tela', PESSOAL, True), 'disponiveis')
    assert any(x['categoria_ir_nome'] == 'Saude' for x in s['disponiveis']['data'])


def test_comprovantes_resumo_filtros_e_detalhe_iguais_ao_flask(cenario):
    dsn, ids, s, _ = cenario
    novo = rpc(dsn, 'ir_comprovantes_tela', PESSOAL, {}, None)
    igual({k: s['lista'][k] for k in ('data', 'total', 'resumo')}, novo, 'lista')
    assert novo['resumo']['lastro']['documentos_aguardando_contador'] == 1
    for consulta, resposta in s['filtros'].items():
        filtros = dict(p.split('=', 1) for p in consulta.split('&'))
        igual({k: resposta[k] for k in ('data', 'total', 'resumo')}, rpc(dsn, 'ir_comprovantes_tela', PESSOAL, filtros, None), consulta)
    for detalhe in s['detalhes']:
        igual(detalhe['data'], rpc(dsn, 'ir_comprovantes_tela', PESSOAL, {}, detalhe['data']['id']), 'detalhe')
    assert len(rpc(dsn, 'ir_comprovantes_tela', PESSOAL, {}, ids[0])['eventos']) == 2


def test_isolamento_e_nada_gravado(cenario):
    dsn, ids, _, antes = cenario
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'ir_documentos_empresa_tela', PESSOAL, 'taxonomia', {}, None)
    assert erro.value.diag.message_primary == 'Central de Documentos Empresariais disponivel apenas no perfil Empresa.'
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'ir_comprovantes_tela', PESSOAL, {}, None, usuario=USUARIO_B)
    assert erro.value.pgcode == '42501'
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, 'ir_comprovantes_tela', PERFIL_B, {}, ids[0], usuario=USUARIO_B)
    assert erro.value.diag.message_primary == 'Comprovante nao encontrado'
    assert rpc(dsn, 'ir_comprovantes_tela', PERFIL_B, {}, None, usuario=USUARIO_B)['total'] == 0
    assert sql(dsn, 'select (select count(*) from public.ir_categoria) c, (select count(*) from public.ir_comprovante) d')[0] == antes


# --- Modo Documentos da Empresa (perfil Empresa) ---------------------------------------------------------------------

FILTROS_EMPRESA = ('tipo_documental=DOCUMENTO_SOCIETARIO', 'categoria_documental=certificado_bombeiros', 'obrigatorio=sim',
                   'obrigatorio=nao', 'validade=VENCIDOS', 'validade=VENCENDO', 'validade=SEM_VALIDADE',
                   'status_documental=TODOS&ano=2031', 'busca=pix')
RESUMO_EMPRESA = ('', 'ano=2031', 'obrigatorio=1', 'validade=VENCENDO')


def metadados(dsn, comprovante_id, **campos):
    dados = {'comprovante_id': comprovante_id, 'perfil_financeiro_id': EMPRESA, 'tipo_documental': 'OUTRO',
             'categoria_documental': 'SEM_CATEGORIA', 'status_documental': 'ATIVO', 'obrigatorio': False, 'renovavel': False,
             **campos}
    sql(dsn, f"insert into public.documento_empresarial_metadata ({', '.join(dados)}, created_at, updated_at) values "
             f"({', '.join(['%s'] * len(dados))}, now(), now())", tuple(dados.values()))


@pytest.fixture(scope='module')
def empresa(cenario):
    from datetime import date, timedelta
    dsn = cenario[0]
    hoje = date.today()
    patrimonio = sql(dsn, "select id from public.ir_categoria where natureza = 'PATRIMONIO_IMOBILIZADO' order by id limit 1")[0]['id']
    ids = [
        comprovante(dsn, EMPRESA, data_documento='2031-02-01', prestador_nome='Junta Comercial (ficticia)', valor=0),
        comprovante(dsn, EMPRESA, data_documento='2031-03-01', prestador_nome='Bombeiros (ficticio)', valor=150),
        comprovante(dsn, EMPRESA, data_documento='2031-04-01', prestador_nome='Loja de equipamentos', categoria_ir_id=patrimonio,
                    valor=3200),
        comprovante(dsn, EMPRESA, data_documento='2031-05-01', prestador_nome='Fornecedor', observacoes='pago via PIX', valor=80),
        comprovante(dsn, EMPRESA, data_documento='2031-06-01', prestador_nome='Prefeitura (ficticia)', valor=0, ano_calendario=2030),
    ]
    metadados(dsn, ids[0], tipo_documental='DOCUMENTO_SOCIETARIO', categoria_documental='CONTRATO_SOCIAL', obrigatorio=True)
    metadados(dsn, ids[1], tipo_documental='DOCUMENTO_OBRIGATORIO', categoria_documental='CERTIFICADO_BOMBEIROS',
              obrigatorio=True, data_validade=hoje + timedelta(days=10), renovavel=True, alerta_dias_antes=15)
    metadados(dsn, ids[4], tipo_documental='DOCUMENTO_SOCIETARIO', categoria_documental='INSCRICAO_MUNICIPAL',
              data_validade=hoje - timedelta(days=3), status_documental='AGUARDANDO_CONTADOR')
    sql(dsn, "insert into public.ir_comprovante_vinculo (comprovante_id, perfil_financeiro_id, tipo_entidade, entidade_id, "
             "resumo_entidade, tipo_vinculo, natureza, status_lastro, ativo, created_at, updated_at) values "
             "(%s, %s, 'DESPESA', 1, 'Despesa ficticia', 'NOTA_FISCAL', 'OUTRO', 'AGUARDANDO_CONTADOR', true, now(), now())",
        (ids[2], EMPRESA))
    saida = flask(dsn, _LEITURA, EMPRESA, json.dumps(ids), json.dumps(FILTROS_EMPRESA), json.dumps(RESUMO_EMPRESA))
    return dsn, ids, saida


@pytest.fixture(scope='module')
def quebra(cluster):  # noqa: F811
    """D-DOC1, em outra copia descartavel: documento com validade, sem prestador e sem arquivo."""
    from datetime import date, timedelta
    dsn = copiar(cluster)
    categoria = sql(dsn, 'select id from public.categoria where ativo order by id limit 1')[0]['id']
    flask(dsn, _SCRIPT, PESSOAL, categoria)  # usuario do Flask e categorias iniciais
    doc = comprovante(dsn, EMPRESA, data_documento='2031-07-01', prestador_nome=None)
    metadados(dsn, doc, tipo_documental='CERTIDAO_LICENCA', categoria_documental='CERTIDAO_FEDERAL',
              data_validade=date.today() + timedelta(days=90))
    return dsn, doc, flask(dsn, _QUEBRA, EMPRESA)


def test_empresa_contexto_lista_filtros_e_detalhe_iguais_ao_flask(empresa):
    dsn, ids, s = empresa
    contexto = rpc(dsn, 'ir_contexto_tela', EMPRESA)
    igual(s['contexto']['data'], contexto, 'contexto')
    assert contexto['modo'] == 'DOCUMENTOS_FISCAIS_EMPRESA'
    igual(s['categorias']['data'], rpc(dsn, 'ir_categorias_tela', EMPRESA), 'categorias')
    igual({k: s['lista'][k] for k in ('data', 'total', 'resumo')}, rpc(dsn, 'ir_comprovantes_tela', EMPRESA, {}, None), 'lista')
    for consulta, resposta in s['filtros'].items():
        filtros = dict(p.split('=', 1) for p in consulta.split('&'))
        igual({k: resposta[k] for k in ('data', 'total', 'resumo')}, rpc(dsn, 'ir_comprovantes_tela', EMPRESA, filtros, None), consulta)
    for detalhe in s['detalhes']:
        igual(detalhe['data'], rpc(dsn, 'ir_comprovantes_tela', EMPRESA, {}, detalhe['data']['id']), 'detalhe')
    pix = next(d['data'] for d in s['detalhes'] if d['data']['id'] == ids[3])
    assert pix['categoria_documental'] == 'PIX_PAGO' and pix['metadata_empresarial']['origem_documental'] == 'INFERIDO'


def test_empresa_taxonomia_resumo_e_metadados_iguais_ao_flask(empresa):
    dsn, ids, s = empresa
    igual(s['taxonomia']['data'], rpc(dsn, 'ir_documentos_empresa_tela', EMPRESA, 'taxonomia', {}, None), 'taxonomia')
    for consulta, (status, resposta) in s['resumo_empresa'].items():
        assert status == 200, consulta
        filtros = dict(p.split('=', 1) for p in consulta.split('&') if p)
        igual(resposta['data'], rpc(dsn, 'ir_documentos_empresa_tela', EMPRESA, 'resumo', filtros, None), f'resumo {consulta!r}')
    resumo = rpc(dsn, 'ir_documentos_empresa_tela', EMPRESA, 'resumo', {'ano': '2031'}, None)
    assert [c['status'] for c in resumo['checklist_empresarial']] == ['ok', 'pendente', 'pendente', 'vencendo']
    for i, (status, resposta) in s['metadata'].items():
        if status != 200:
            with pytest.raises(psycopg2.Error) as erro:
                rpc(dsn, 'ir_documentos_empresa_tela', EMPRESA, 'metadata', {}, int(i))
            assert erro.value.diag.message_primary == resposta['error']
            continue
        igual(resposta['data'], rpc(dsn, 'ir_documentos_empresa_tela', EMPRESA, 'metadata', {}, int(i)), f'metadata {i}')


def test_empresa_d_doc1_resumo_do_flask_quebra_e_o_novo_responde(quebra):
    dsn, doc, depois = quebra
    # No Flask a excecao escapa da rota (500 no servidor) tanto no resumo quanto na lista de comprovantes.
    assert depois == {'resumo': "AttributeError: 'NoneType' object has no attribute 'get'",
                      'lista': "AttributeError: 'NoneType' object has no attribute 'get'"}
    resumo = rpc(dsn, 'ir_documentos_empresa_tela', EMPRESA, 'resumo', {}, None)
    item = next(p for p in resumo['proximos_vencimentos'] if p['id'] == doc)
    assert item['documento'] == f'Documento #{doc}'
