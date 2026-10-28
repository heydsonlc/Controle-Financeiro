"""
Testes FIN-PRE-PRODUCAO-1 (2.2) — Documentos: leituras que a tela original ainda nao alcancava (migration 20261130090000)
e a regra do titular "um documento pode ser vinculado a varios bens", em cluster PostgreSQL local descartavel com os
dados FICTICIOS do E2E e documentos ficticios proprios.

Fidelidade: as mesmas rotas sao chamadas no PROPRIO Flask numa copia e respondidas pelas funcoes novas noutra, e as
respostas sao comparadas: entidades vinculaveis (todos os tipos, com e sem busca), vinculos ativos do documento, resumo
de lastro e sugestao financeira (categoria do documento, por palavra-chave, empate, sem texto, OCR, cupom fiscal,
categoria IR, valor zerado). O mesmo documento vinculado a dois bens pela rota generica gera as mesmas linhas nos dois
sistemas. Tambem: isolamento entre perfis, privilegios e a reversao (que recusa quando a regra nova ja esta em uso).
"""
import json
import os
import subprocess
import sys
import uuid

import pytest

from tests import supabase_local as L
from tests.test_supabase_cartoes import rpc
from tests.test_supabase_recorrencia import PG_BIN, ROOT, USUARIO_A, USUARIO_B, atribuir, chamar, copiar, sql

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

B, EMPRESA = L.PERFIS['PERFIL_B']['id'], L.PERFIS['EMPRESA']['id']
REVERSAO = ROOT / 'supabase' / 'reversao' / '20261130090000_remover_documentos_tela.sql'
TIPOS = ('CONTA', 'DESPESA_PREVISTA', 'LANCAMENTO', 'MOVIMENTO_FINANCEIRO', 'PATRIMONIO', 'FINANCIAMENTO', 'OUTRO', 'xpto', '')
SEM_HORA = {'created_at', 'updated_at'}


def semear_cenario(cur):
    """Documentos FICTICIOS do Perfil B para a sugestao financeira e os vinculos (ids devolvidos em financeiro_teste)."""
    cur.execute('select id from public.categoria where coalesce(ativo, true) order by id limit 2')
    cat_a, cat_b = [r[0] for r in cur.fetchall()]
    cur.execute("insert into public.categoria_palavra_chave (categoria_id, palavra, ativo) values (%s, 'consultaficticia', true), "
                "(%s, 'exameficticio', true), (%s, 'exameficticio', true)", (cat_a, cat_a, cat_b))
    cur.execute("insert into public.ir_categoria (nome, descricao, dedutivel, ativo, ordem, tipo_contexto, natureza, created_at, updated_at) "
                "values ('Medica Sugestao (ficticia)', 'ficticia', true, true, 20, 'PESSOAL', 'DEDUCAO_IRPF', now(), now()) returning id")
    cat_ir = cur.fetchone()[0]
    cur.execute('insert into public.ir_categoria_despesa (perfil_financeiro_id, categoria_ir_id, categoria_id, ativo, created_at, updated_at) '
                'values (%s, %s, %s, true, now(), now())', (B, cat_ir, cat_a))

    def doc(n, **campos):
        dados = {'perfil_financeiro_id': B, 'ano_calendario': 2027, 'status': 'PENDENTE_REVISAO', 'hash_arquivo': f'{9000 + n:064d}',
                 **campos}
        colunas = ', '.join(dados)
        cur.execute(f"insert into public.ir_comprovante ({colunas}, created_at, updated_at) values "
                    f"({', '.join(['%s'] * len(dados))}, now(), now()) returning id", tuple(dados.values()))
        return cur.fetchone()[0]

    ids = {
        'categoria': doc(1, categoria_id=cat_a, origem_classificacao=None, prestador_nome='Clinica Sugestao (ficticia)',
                         prestador_cpf_cnpj='11.222.333/0001-44', valor=120, data_documento='2027-02-10'),
        'palavra': doc(2, texto_extraido='Recibo: Consulta Fictícia ÁGUA consultaficticia!', valor=0, prestador_nome='  Laboratorio (ficticio) '),
        'empate': doc(3, texto_extraido='exameficticio', valor=55.5, data_documento='2027-03-01', categoria_ir_id=cat_ir),
        'cupom': doc(4, valor=10),
        'vazio': doc(5, texto_extraido='   ', prestador_nome='Loja (ficticia)', valor=7, data_documento='2027-04-01'),
    }
    cur.execute("insert into public.ir_comprovante_arquivo (comprovante_id, nome_arquivo, mime_type, tamanho_bytes, hash_arquivo, conteudo, "
                "created_at) values (%s, 'nota-sugestao.pdf', 'application/pdf', 4, %s, '\\x25504446', now())", (ids['categoria'], 'f' * 64))
    cur.execute("insert into public.ir_comprovante_evento (comprovante_id, tipo_evento, descricao, created_at) values "
                "(%s, 'OCR_EXECUTADO', 'ficticio', now()), (%s, 'CUPOM_FISCAL_DETECTADO', 'ficticio', now())", (ids['palavra'], ids['cupom']))
    for n, (tipo, status) in enumerate((('OUTRO', 'PENDENTE'), ('CONTA', 'AGUARDANDO_CONTADOR'))):
        cur.execute("insert into public.ir_comprovante_vinculo (comprovante_id, perfil_financeiro_id, tipo_entidade, entidade_id, "
                    "resumo_entidade, tipo_vinculo, natureza, status_lastro, observacoes, ativo, created_at, updated_at) values "
                    "(%s, %s, %s, null, null, 'COMPROVANTE', 'OUTRO', %s, 'ficticio', true, now() + %s * interval '1 second', now())",
                    (ids['categoria'], B, tipo, status, n))
    cur.execute("insert into public.ir_comprovante_vinculo (comprovante_id, perfil_financeiro_id, tipo_entidade, tipo_vinculo, natureza, "
                "status_lastro, ativo, created_at, updated_at) values (%s, %s, 'OUTRO', 'RECIBO', 'OUTRO', 'VALIDADO', false, now(), now())",
                (ids['categoria'], B))
    cur.execute('create table public.financeiro_teste (chave text primary key, valor integer)')
    cur.executemany('insert into public.financeiro_teste values (%s, %s)', list(ids.items()))


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    with L.ClusterLocal(PG_BIN, tmp_path_factory.mktemp('documentos_tela')) as c:
        c.preparar()
        conn = c.conectar()
        with conn.cursor() as cur:
            for semear in (L.semear_recorrencia_e2e, L.semear_receitas_e2e, L.semear_cartoes_e2e, L.semear_pendencia_e2e,
                           L.semear_financiamento_e2e, L.semear_patrimonio_e2e, L.semear_documentos_fiscais_e2e,
                           L.semear_mobilidade_e2e, semear_cenario):
                semear(cur)
        conn.close()
        yield c


def ids_do_cenario(dsn):
    return {r['chave']: r['valor'] for r in sql(dsn, 'select * from public.financeiro_teste')}


_SCRIPT = """
import json, sys, uuid
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    email = f'flask.doctela.{uuid.uuid4().hex[:8]}@teste.local'
    u = Usuario(email=email, nome='Docs', ativo=True)
    u.definir_senha('Senha-ficticia-doctela-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-doctela-2026'}).status_code == 302
saida = []
for nome, perfil, metodo, rota, corpo in json.loads(sys.argv[1]):
    assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': perfil}).status_code == 200
    r = c.open(rota, method=metodo, json=corpo)
    saida.append([nome, r.status_code, r.get_json()])
print('FLASK_JSON ' + json.dumps(saida))
"""


def pelo_flask(dsn, passos):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT, json.dumps(passos)], cwd=ROOT, env=env, capture_output=True, text=True,
                       timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return {nome: (status, corpo) for nome, status, corpo in json.loads(linha[len('FLASK_JSON '):])}


def normal(valor):
    if isinstance(valor, dict):
        return {k: normal(v) for k, v in valor.items() if k not in SEM_HORA}
    if isinstance(valor, list):
        return [normal(v) for v in valor]
    return float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else valor


def passos_de_leitura(ids):
    passos = []
    for perfil, nome_perfil in ((B, 'b'), (EMPRESA, 'empresa')):
        for tipo in TIPOS:
            passos.append((f'entidades_{nome_perfil}_{tipo}', perfil, 'GET', f'/api/ir/entidades-vinculaveis?tipo={tipo}', None))
        for tipo, busca in (('CONTA', 'E2E'), ('LANCAMENTO', 'e2e'), ('PATRIMONIO', 'Notebook'), ('FINANCIAMENTO', 'nada-assim'),
                            ('DESPESA_PREVISTA', 'previst')):
            passos.append((f'busca_{nome_perfil}_{tipo}', perfil, 'GET', f'/api/ir/entidades-vinculaveis?tipo={tipo}&busca={busca}', None))
        passos.append((f'lastro_{nome_perfil}', perfil, 'GET', '/api/ir/lastro/resumo', None))
        passos.append((f'lastro_{nome_perfil}_2027', perfil, 'GET', '/api/ir/lastro/resumo?ano=2027', None))
    passos.append(('vinculos', B, 'GET', f"/api/ir/comprovantes/{ids['categoria']}/vinculos", None))
    passos.append(('vinculos_outro_perfil', EMPRESA, 'GET', f"/api/ir/comprovantes/{ids['categoria']}/vinculos", None))
    for chave, doc in ids.items():
        passos.append((f'sugestao_{chave}', B, 'GET', f'/api/ir/comprovantes/{doc}/sugestao-financeira', None))
    passos.append(('sugestao_outro_perfil', EMPRESA, 'GET', f"/api/ir/comprovantes/{ids['categoria']}/sugestao-financeira", None))
    return passos


def pelo_novo(dsn, passos):
    saida = {}
    for nome, perfil, _metodo, rota, _corpo in passos:
        caminho, _, consulta = rota.partition('?')
        p = dict(x.split('=', 1) if '=' in x else (x, '') for x in consulta.split('&') if x)
        try:
            if caminho.endswith('/entidades-vinculaveis'):
                dados = chamar(dsn, USUARIO_B if perfil == B else USUARIO_A, 'select financeiro.entidades_vinculaveis_tela(%s, %s, %s)',
                               (perfil, p.get('tipo'), p.get('busca')))
                saida[nome] = (200, {'success': True, 'data': dados, 'total': len(dados)})
            elif caminho.endswith('/lastro/resumo'):
                dados = chamar(dsn, USUARIO_B if perfil == B else USUARIO_A, 'select financeiro.lastro_resumo_tela(%s, %s)', (perfil, p.get('ano')))
                saida[nome] = (200, {'success': True, 'data': dados})
            elif caminho.endswith('/vinculos'):
                dados = chamar(dsn, USUARIO_B if perfil == B else USUARIO_A, 'select financeiro.vinculos_documento_tela(%s, %s)',
                               (perfil, int(caminho.split('/')[-2])))
                saida[nome] = (200, {'success': True, 'data': dados, 'total': len(dados)})
            else:
                dados = chamar(dsn, USUARIO_B if perfil == B else USUARIO_A, 'select financeiro.sugestao_financeira_documento_tela(%s, %s)',
                               (perfil, int(caminho.split('/')[-2])))
                saida[nome] = (200, {'success': True, 'data': dados})
        except psycopg2.Error as e:
            assert e.pgcode == '22023', (nome, e.pgerror)
            saida[nome] = (404 if e.diag.message_hint == 'NAO_ENCONTRADA' else 400, {'success': False, 'error': e.diag.message_primary})
    return saida


@pytest.fixture(scope='module')
def leituras(cluster):
    dsn_flask, dsn_novo = copiar(cluster), copiar(cluster)
    # O usuario A gere a Empresa no novo aplicativo (no cenario do E2E ele e LEITOR); o B gere o Perfil B.
    sql(dsn_novo, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s", (EMPRESA,))
    passos = passos_de_leitura(ids_do_cenario(dsn_novo))
    return {'flask': pelo_flask(dsn_flask, passos), 'novo': pelo_novo(dsn_novo, passos)}


def test_mesmas_respostas_que_o_flask(leituras):
    flask, novo = leituras['flask'], leituras['novo']
    assert set(flask) == set(novo)
    diferencas = {n: (novo[n], flask[n]) for n in flask if (novo[n][0], normal(novo[n][1])) != (flask[n][0], normal(flask[n][1]))}
    assert diferencas == {}


def test_o_cenario_cobre_os_casos(leituras):
    flask = leituras['flask']
    nao_vazios = {n for n, (s, c) in flask.items() if n.startswith('entidades_') and c['data']}
    assert {'entidades_b_CONTA', 'entidades_b_FINANCIAMENTO', 'entidades_b_DESPESA_PREVISTA', 'entidades_empresa_LANCAMENTO',
            'entidades_empresa_PATRIMONIO'} <= nao_vazios
    assert any(c['data'] for n, (s, c) in flask.items() if n.startswith('busca_'))  # alguma busca encontra algo
    assert flask['entidades_b_xpto'][1]['data'] == [] and flask['entidades_b_OUTRO'][1]['data'] == []
    assert [v['tipo_entidade'] for v in flask['vinculos'][1]['data']] == ['CONTA', 'OUTRO']  # ativos, mais recente primeiro
    assert flask['vinculos_outro_perfil'][0] == 404
    assert flask['lastro_b_2027'][1]['data']['documentos_aguardando_contador'] == 0  # o primeiro vinculo ativo (por id) e o OUTRO
    sug = {n[len('sugestao_'):]: c for n, (s, c) in flask.items() if n.startswith('sugestao_') and s == 200}
    assert sug['categoria']['data']['categoria_ir_nome'] == 'Medica Sugestao (ficticia)'
    assert sug['categoria']['data']['descricao'].startswith('Clinica Sugestao (ficticia) - ')
    assert sug['palavra']['data']['categoria_origem'] == 'palavra_chave'
    assert 'Sugestao gerada a partir de texto extraido por OCR' in ' '.join(sug['palavra']['data']['avisos'])
    assert sug['empate']['data']['categoria_id'] is None and sug['empate']['data']['categoria_origem'] == 'ambigua'
    assert sug['cupom']['data']['descricao'].startswith('Cupom fiscal - ')
    assert 'Nenhuma palavra-chave encontrada.' in sug['vazio']['data']['avisos']
    assert flask['sugestao_outro_perfil'][0] == 404


def _vinculos_patrimonio(dsn, doc):
    return [{k: v for k, v in r.items() if k not in SEM_HORA | {'id'}}
            for r in sql(dsn, "select * from public.ir_comprovante_vinculo where comprovante_id = %s and tipo_entidade = 'PATRIMONIO' "
                              "order by entidade_id", (doc,))]


def test_documento_em_varios_bens_como_a_rota_do_flask(cluster):
    dsn_flask, dsn_novo = copiar(cluster), copiar(cluster)
    doc = sql(dsn_novo, 'select id from public.ir_comprovante where perfil_financeiro_id = %s order by id limit 1', (EMPRESA,))[0]['id']
    bens = [r['id'] for r in sql(dsn_novo, 'select id from public.bem_patrimonial where perfil_financeiro_id = %s order by id', (EMPRESA,))]
    assert len(bens) >= 2
    corpo = lambda bem: {'tipo_entidade': 'PATRIMONIO', 'entidade_id': bem, 'tipo_vinculo': 'NOTA_FISCAL', 'natureza': 'PATRIMONIO_IMOBILIZADO',
                         'status_lastro': 'COM_DOCUMENTO', 'observacoes': 'nota com varios itens (ficticia)'}
    flask = pelo_flask(dsn_flask, [(f'bem{i}', EMPRESA, 'POST', f'/api/ir/comprovantes/{doc}/vinculos', corpo(b)) for i, b in enumerate(bens[:2])])
    assert all(s == 201 for s, _ in flask.values()), flask
    sql(dsn_novo, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s", (EMPRESA,))
    atribuir(dsn_novo, EMPRESA)
    for bem in bens[:2]:
        rpc(dsn_novo, 'criar_vinculo_documento', EMPRESA, doc, corpo(bem))
    assert _vinculos_patrimonio(dsn_novo, doc) == _vinculos_patrimonio(dsn_flask, doc)
    assert len(_vinculos_patrimonio(dsn_novo, doc)) == 2
    # A tela de Patrimonio continua oferecendo o documento ja ligado a um bem (para o proximo item da nota).
    docs = rpc(dsn_novo, 'patrimonio_documentos_vinculaveis_tela', EMPRESA, None)
    assert doc in [d['id'] for d in docs]


def test_isolamento_entre_perfis(cluster):
    dsn = copiar(cluster)
    ids = ids_do_cenario(dsn)
    for comando, args in (('select financeiro.entidades_vinculaveis_tela(%s, %s, %s)', (B, 'CONTA', None)),
                          ('select financeiro.lastro_resumo_tela(%s, %s)', (B, None)),
                          ('select financeiro.vinculos_documento_tela(%s, %s)', (B, ids['categoria'])),
                          ('select financeiro.sugestao_financeira_documento_tela(%s, %s)', (B, ids['categoria']))):
        with pytest.raises(psycopg2.Error) as e:
            chamar(dsn, USUARIO_A, comando, args)  # A nao tem acesso ao Perfil B
        assert e.value.pgcode == '42501'
        with pytest.raises(psycopg2.Error):
            chamar(dsn, None, comando, args)


def test_privilegios(cluster):
    dsn = copiar(cluster)
    linhas = sql(dsn, """select p.proname n, has_function_privilege('authenticated', p.oid, 'EXECUTE') a,
                                has_function_privilege('anon', p.oid, 'EXECUTE') x
                           from pg_proc p join pg_namespace s on s.oid = p.pronamespace
                          where s.nspname = 'financeiro' and p.proname in ('entidades_vinculaveis_tela', 'vinculos_documento_tela',
                                'lastro_resumo_tela', 'sugestao_financeira_documento_tela', 'doc_texto_classificacao')""")
    assert {r['n']: (r['a'], r['x']) for r in linhas} == {
        'entidades_vinculaveis_tela': (True, False), 'vinculos_documento_tela': (True, False), 'lastro_resumo_tela': (True, False),
        'sugestao_financeira_documento_tela': (True, False), 'doc_texto_classificacao': (False, False)}


def _executar(dsn, caminho):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(caminho.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_devolve_a_regra_anterior_e_recusa_com_a_regra_nova_em_uso(cluster):
    dsn = copiar(cluster)
    _executar(dsn, REVERSAO)
    assert not sql(dsn, "select 1 from pg_proc where proname in ('entidades_vinculaveis_tela', 'sugestao_financeira_documento_tela')")
    sql(dsn, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s", (EMPRESA,))
    atribuir(dsn, EMPRESA)
    doc = sql(dsn, 'select id from public.ir_comprovante where perfil_financeiro_id = %s order by id limit 1', (EMPRESA,))[0]['id']
    bens = [r['id'] for r in sql(dsn, 'select id from public.bem_patrimonial where perfil_financeiro_id = %s order by id', (EMPRESA,))]
    rpc(dsn, 'criar_vinculo_documento', EMPRESA, doc, {'tipo_entidade': 'PATRIMONIO', 'entidade_id': bens[0]})
    with pytest.raises(psycopg2.Error, match='ja esta vinculado a um bem'):  # regra anterior de volta
        rpc(dsn, 'criar_vinculo_documento', EMPRESA, doc, {'tipo_entidade': 'PATRIMONIO', 'entidade_id': bens[1]})
    # Reaplicada, a regra nova vale; com documento em dois bens, a reversao recusa (nada muda).
    _executar(dsn, ROOT / 'supabase' / 'migrations' / '20261130090000_financeiro_documentos_tela.sql')
    rpc(dsn, 'criar_vinculo_documento', EMPRESA, doc, {'tipo_entidade': 'PATRIMONIO', 'entidade_id': bens[1]})
    with pytest.raises(psycopg2.Error, match='Reversao recusada'):
        _executar(dsn, REVERSAO)
    assert sql(dsn, "select 1 from pg_proc where proname = 'sugestao_financeira_documento_tela'")
