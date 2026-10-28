"""
Testes FIN-DOCUMENTOS-2 (FIN-BLOCO-B-1, B1) — escrita de Documentos Fiscais no novo aplicativo (migration
20261128090000), em cluster PostgreSQL local descartavel e com arquivos FICTICIOS gerados no proprio teste.

Fidelidade: a mesma sequencia (envio de arquivo, revisao, validacao, vinculo criado/editado/removido e despesa a partir
do documento) e feita pelo PROPRIO Flask numa copia (perfil no Flask; envio em multipart) e pelas funcoes novas noutra
(perfil no novo aplicativo; envio em base64); as linhas sao comparadas, fora carimbos de hora e a leitura automatica
(OCR/observacoes/eventos do OCR, que o novo aplicativo nao faz). Tambem: validacoes do arquivo (tipo, MIME, vazio,
tamanho, assinatura), duplicidade por hash no perfil, armazenamento privado (leitura so no perfil), texto de PDF,
exclusao segura, despesa nao duplicada, lancamento pago pela conta bancaria e no cartao, regra do bem patrimonial,
escritor unico, isolamento, privilegios e a reversao.
"""
import base64
import json
import os
import subprocess
import sys
import uuid
from decimal import Decimal

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_integracao_1123_1126 import resumo_tabelas
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    ROOT,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, EMPRESA, PERFIL_B = ID['PESSOAL'], ID['EMPRESA'], ID['PERFIL_B']
CATEGORIA = 951
MIGRATION = ROOT / 'supabase' / 'migrations' / '20261128090000_financeiro_documentos_escrita.sql'
REVERSAO = ROOT / 'supabase' / 'reversao' / '20261128090000_remover_documentos_escrita.sql'
PNG = b'\x89PNG\r\n\x1a\n' + b'documento ficticio de teste ' * 40
PDF = b'%PDF-1.4\n% documento ficticio\n' + b'0' * 200
SEM_HORA = {'created_at', 'updated_at', 'criado_em', 'atualizado_em'}
REVISAO = {'prestador_nome': 'Clinica Ficticia LTDA', 'prestador_cpf_cnpj': '12.345.678/0001-90', 'data_documento': '2027-03-08',
           'valor': '150.75', 'categoria_id': CATEGORIA, 'observacoes': 'revisado'}
VINCULO = {'tipo_entidade': 'OUTRO', 'tipo_vinculo': 'RECIBO', 'natureza': 'reembolso', 'status_lastro': 'pendente'}
FINANCEIRO = {'tipo_destino': 'DESPESA', 'forma_pagamento': 'pix', 'categoria_id': CATEGORIA, 'valor': '150.75', 'data': '2027-03-10'}


def chave():
    return str(uuid.uuid4())


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


def enviar(dsn, conteudo, nome='nota.png', mime=None, perfil=PESSOAL, usuario=USUARIO_A, texto=None, k=None):
    dados = {'nome_arquivo': nome, 'ano_calendario': 2027, **({'mime_type': mime} if mime else {}),
             **({'texto_extraido': texto} if texto else {})}
    return chamar(dsn, usuario, 'select financeiro.enviar_comprovante(%s, %s::jsonb, %s, %s)',
                  (perfil, json.dumps(dados), base64.b64encode(conteudo).decode(), k or chave()))


_SCRIPT_UPLOAD = """
import io, json, sys, uuid
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    email = f'flask.doc.{uuid.uuid4().hex[:8]}@teste.local'
    u = Usuario(email=email, nome='Doc', ativo=True)
    u.definir_senha('Senha-ficticia-doc-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-doc-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
conteudo = bytes.fromhex(sys.argv[2])
r = c.post('/api/ir/comprovantes/upload', data={'ano_calendario': '2027', 'arquivos': (io.BytesIO(conteudo), 'nota.png')},
           content_type='multipart/form-data')
saida = [['upload', r.status_code, r.get_json()]]
doc = r.get_json()['data'][0]['data']['comprovante']['id']
ids = {'doc': doc}
for nome, metodo, rota, corpo in json.loads(sys.argv[3]):
    for k, v in ids.items():
        rota = rota.replace('{' + k + '}', str(v))
    r = c.open(rota, method=metodo, json=corpo)
    j = r.get_json()
    saida.append([nome, r.status_code, j])
    if nome == 'vinculo':
        ids['vinculo'] = j['data']['id']
print('FLASK_JSON ' + json.dumps(saida))
"""


def pelo_flask(dsn):
    passos = [('revisar', 'PUT', '/api/ir/comprovantes/{doc}', REVISAO), ('validar', 'POST', '/api/ir/comprovantes/{doc}/validar', None),
              ('vinculo', 'POST', '/api/ir/comprovantes/{doc}/vinculos', VINCULO),
              ('editar', 'PUT', '/api/ir/comprovantes/{doc}/vinculos/{vinculo}', {'status_lastro': 'validado', 'observacoes': 'ok'}),
              ('remover', 'DELETE', '/api/ir/comprovantes/{doc}/vinculos/{vinculo}', None),
              ('financeiro', 'POST', '/api/ir/comprovantes/{doc}/criar-financeiro', FINANCEIRO)]
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT_UPLOAD, str(PESSOAL), PNG.hex(), json.dumps(passos)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    saida = {nome: (status, corpo) for nome, status, corpo in json.loads(linha[len('FLASK_JSON '):])}
    assert all(s in (200, 201) for s, _ in saida.values()), saida
    return saida


def pelo_novo(dsn):
    doc = enviar(dsn, PNG)['comprovante_id']
    rpc(dsn, 'atualizar_comprovante', PESSOAL, doc, REVISAO)
    rpc(dsn, 'validar_comprovante', PESSOAL, doc)
    v = rpc(dsn, 'criar_vinculo_documento', PESSOAL, doc, VINCULO)['vinculo_id']
    rpc(dsn, 'atualizar_vinculo_documento', PESSOAL, doc, v, {'status_lastro': 'validado', 'observacoes': 'ok'})
    rpc(dsn, 'remover_vinculo_documento', PESSOAL, doc, v)
    return rpc(dsn, 'criar_financeiro_documento', PESSOAL, doc, FINANCEIRO, chave())


def linhas(dsn):
    saida = {}
    for tabela, filtro in (('ir_comprovante', ''), ('ir_comprovante_arquivo', ''), ('ir_comprovante_vinculo', ''),
                           ('item_despesa', "where nome like 'Clinica%%'"), ('conta', "where descricao like 'Clinica%%'")):
        rows = sql(dsn, f'select * from public.{tabela} {filtro} order by id')
        # Leitura automatica (OCR do Flask x revisao manual no novo aplicativo) fica fora: so no comprovante.
        fora = SEM_HORA | ({'observacoes', 'texto_extraido', 'confianca', 'origem_classificacao'} if tabela == 'ir_comprovante' else set())
        saida[tabela] = [{k: v for k, v in r.items() if k not in fora} for r in rows]
    return saida


@pytest.fixture(scope='module')
def comparacao(cluster):  # noqa: F811
    no_flask, no_novo = copiar(cluster), copiar(cluster)
    atribuir(no_novo, 'PESSOAL')
    return {'flask': no_flask, 'novo': no_novo, 'r_flask': pelo_flask(no_flask), 'r_novo': pelo_novo(no_novo)}


def test_mesmas_linhas_que_o_flask(comparacao):
    f, n = linhas(comparacao['flask']), linhas(comparacao['novo'])
    for tabela in f:
        assert len(n[tabela]) == len(f[tabela]) > 0, tabela
        for a, b in zip(f[tabela], n[tabela]):
            assert b == a, (tabela, {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)})
    # O arquivo e o mesmo, byte a byte, e fica no banco.
    assert bytes(sql(comparacao['novo'], 'select conteudo from public.ir_comprovante_arquivo')[0]['conteudo']) == PNG


def test_texto_de_pdf_e_revisao_manual_sem_ocr(banco):
    texto = 'NOTA FISCAL DE SERVICO ficticia prestador Clinica Ficticia valor 150,75 data 08/03/2027'
    com = enviar(banco, PDF, 'nota.pdf', texto=texto)['comprovante_id']
    sem = enviar(banco, PDF + b'x', 'vazio.pdf')['comprovante_id']
    r = {x['id']: x for x in sql(banco, 'select id, status, texto_extraido, origem_classificacao from public.ir_comprovante where id in (%s, %s)', (com, sem))}
    assert r[com] == {'id': com, 'status': 'PENDENTE_REVISAO', 'texto_extraido': texto, 'origem_classificacao': 'TEXTO_PDF'}
    assert r[sem]['status'] == 'PENDENTE_REVISAO' and r[sem]['texto_extraido'] is None
    eventos = [e['tipo_evento'] for e in sql(banco, 'select tipo_evento from public.ir_comprovante_evento where comprovante_id = %s order by id', (com,))]
    assert eventos == ['IMPORTADO', 'TEXTO_EXTRAIDO']


@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    return dsn


def test_validacoes_do_arquivo_e_duplicidade_por_perfil(banco):
    antes = resumo_tabelas(banco)
    casos = [((PNG, 'nota'), 'Tipo de arquivo nao permitido'), ((PNG, 'nota.gif'), 'Tipo de arquivo nao permitido'),
             ((PNG, 'nota.png', 'text/html'), 'MIME type nao permitido'), ((b'', 'nota.png'), 'Arquivo vazio'),
             ((b'GIF89a' + b'0' * 20, 'nota.png'), 'Assinatura do arquivo invalida'),
             ((b'\x89PNG\r\n\x1a\n' + b'0' * (10 * 1024 * 1024), 'nota.png'), 'Arquivo excede o tamanho maximo permitido'),
             ((PNG, ''), 'Nome de arquivo vazio')]
    for args, mensagem in casos:
        assert mensagem in str(erro(enviar, banco, *args)), mensagem
    assert resumo_tabelas(banco) == antes
    a = enviar(banco, PNG, 'Nota Fiscal Março (1).png')
    assert a['duplicado'] is False
    assert sql(banco, 'select nome_arquivo, tamanho_bytes, hash_arquivo from public.ir_comprovante_arquivo') == [
        {'nome_arquivo': 'Nota_Fiscal_Marco_1.png', 'tamanho_bytes': len(PNG),
         'hash_arquivo': __import__('hashlib').sha256(PNG).hexdigest()}]
    b = enviar(banco, PNG, 'outro nome.png')
    assert b == {'duplicado': True, 'comprovante_id': a['comprovante_id'], 'mensagem': 'Arquivo ja importado anteriormente.'}
    k = chave()
    primeira, repetida = enviar(banco, PDF, 'r.pdf', k=k), enviar(banco, PDF, 'r.pdf', k=k)
    assert repetida == {**primeira, 'repetida': True}
    assert sql(banco, 'select count(*) n from public.ir_comprovante_arquivo')[0]['n'] == 2
    # Outro perfil pode ter o mesmo arquivo; cada um ve so o seu.
    c = enviar(banco, PNG, perfil=PERFIL_B, usuario=USUARIO_B)
    assert c['duplicado'] is False and c['comprovante_id'] != a['comprovante_id']
    assert erro(chamar, banco, USUARIO_A, 'select financeiro.arquivo_comprovante_tela(%s, %s)', (PESSOAL, c['comprovante_id'])).pgcode in ('22023', 'P0001', '42501')


def test_escritor_unico_e_isolamento(banco):
    doc = enviar(banco, PNG)['comprovante_id']
    doc_b = enviar(banco, PDF, 'b.pdf', perfil=PERFIL_B, usuario=USUARIO_B)['comprovante_id']
    antes = resumo_tabelas(banco)
    assert erro(rpc, banco, 'atualizar_comprovante', PESSOAL, doc, REVISAO, usuario=USUARIO_B).pgcode == '42501'
    assert erro(rpc, banco, 'atualizar_comprovante', PESSOAL, doc_b, REVISAO).diag.message_hint == 'NAO_ENCONTRADA'
    assert erro(rpc, banco, 'criar_financeiro_documento', PESSOAL, doc_b, FINANCEIRO, chave()).diag.message_hint == 'NAO_ENCONTRADA'
    conta_b = sql(banco, "select id from public.conta_bancaria where perfil_financeiro_id = %s limit 1", (PERFIL_B,))[0]['id']
    assert 'perfil' in str(erro(rpc, banco, 'criar_vinculo_documento', PESSOAL, doc, {'tipo_entidade': 'CONTA', 'entidade_id': conta_b}))
    atribuir(banco, 'PESSOAL', 'FLASK')
    antes = resumo_tabelas(banco)
    for funcao, args in (('atualizar_comprovante', (doc, REVISAO)), ('validar_comprovante', (doc,)), ('excluir_comprovante', (doc,)),
                         ('criar_vinculo_documento', (doc, VINCULO)), ('criar_financeiro_documento', (doc, FINANCEIRO, chave()))):
        assert erro(rpc, banco, funcao, PESSOAL, *args).diag.message_hint == 'SISTEMA_FLASK', funcao
    assert erro(enviar, banco, PDF + b'z', 'z.pdf').diag.message_hint == 'SISTEMA_FLASK'
    assert resumo_tabelas(banco) == antes


def test_exclusao_segura(banco):
    livre = enviar(banco, PNG)['comprovante_id']
    vinculado = enviar(banco, PDF, 'v.pdf')['comprovante_id']
    v = rpc(banco, 'criar_vinculo_documento', PESSOAL, vinculado, VINCULO)['vinculo_id']
    validado = enviar(banco, PDF + b'1', 'val.pdf')['comprovante_id']
    rpc(banco, 'validar_comprovante', PESSOAL, validado)
    antes = resumo_tabelas(banco)
    assert erro(rpc, banco, 'excluir_comprovante', PESSOAL, vinculado).diag.message_hint == 'COM_VINCULOS'
    rpc(banco, 'remover_vinculo_documento', PESSOAL, vinculado, v)
    assert erro(rpc, banco, 'excluir_comprovante', PESSOAL, vinculado).diag.message_hint == 'COM_VINCULOS'  # historico fica
    assert erro(rpc, banco, 'excluir_comprovante', PESSOAL, validado).diag.message_hint == 'COM_HISTORICO'
    assert {t for t, h in resumo_tabelas(banco).items() if antes[t] != h} == {'public.ir_comprovante_vinculo'}
    assert rpc(banco, 'excluir_comprovante', PESSOAL, livre)['excluido'] is True
    assert sql(banco, 'select count(*) n from public.ir_comprovante_arquivo where comprovante_id = %s', (livre,))[0]['n'] == 0


def test_documento_nao_gera_duas_despesas_e_lancamentos_pagos(banco):
    doc = enviar(banco, PNG)['comprovante_id']
    r = rpc(banco, 'criar_financeiro_documento', PESSOAL, doc, FINANCEIRO, chave())
    antes = resumo_tabelas(banco)
    assert erro(rpc, banco, 'criar_financeiro_documento', PESSOAL, doc, FINANCEIRO, chave()).diag.message_hint == 'DUPLICADO'
    assert resumo_tabelas(banco) == antes
    assert sql(banco, 'select status_pagamento from public.conta where id = %s', (r['conta_id'],)) == [{'status_pagamento': 'Pendente'}]
    # Lancamento realizado pela conta bancaria: paga pelo motor de pagamento (movimento e saldo coerentes).
    doc2 = enviar(banco, PDF, 'pago.pdf')['comprovante_id']
    banco_id = sql(banco, "select id from public.conta_bancaria where perfil_financeiro_id = %s order by id limit 1", (PESSOAL,))[0]['id']
    p = rpc(banco, 'criar_financeiro_documento', PESSOAL, doc2, {**FINANCEIRO, 'tipo_destino': 'LANCAMENTO', 'conta_bancaria_id': banco_id,
                                                                  'valor': '40.00'}, chave())
    assert sql(banco, 'select status_pagamento from public.conta where id = %s', (p['conta_id'],)) == [{'status_pagamento': 'Pago'}]
    mov = sql(banco, 'select tipo, valor from public.movimento_financeiro where conta_id = %s', (p['conta_id'],))
    assert mov == [{'tipo': 'DEBITO', 'valor': Decimal('40.00')}]
    s = sql(banco, 'select saldo_atual, financeiro.saldo_da_conta(id) f from public.conta_bancaria where id = %s', (banco_id,))[0]
    assert s['saldo_atual'] == s['f']
    # No cartao: um lancamento.
    cartao = sql(banco, "select id from public.item_despesa where tipo = 'Agregador' and perfil_financeiro_id = %s order by id limit 1", (PESSOAL,))
    if cartao:
        doc3 = enviar(banco, PDF + b'c', 'cartao.pdf')['comprovante_id']
        c = rpc(banco, 'criar_financeiro_documento', PESSOAL, doc3, {**FINANCEIRO, 'tipo_destino': 'LANCAMENTO', 'forma_pagamento': 'cartao',
                                                                      'cartao_id': cartao[0]['id'], 'valor': '25.00',
                                                                      'mes_fatura': '2027-04-01'}, chave())
        assert c['tipo_entidade'] == 'LANCAMENTO'
        assert sql(banco, 'select valor from public.lancamento_agregado where id = %s', (c['entidade_id'],)) == [{'valor': Decimal('25.00')}]


def test_vinculo_patrimonial_um_documento_um_bem(banco):
    sql(banco, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s", (EMPRESA,))
    atribuir(banco, 'EMPRESA')
    bens = [rpc(banco, 'criar_bem_patrimonial', EMPRESA, {'nome': f'Bem {i} (ficticio)', 'valor_aquisicao': 100}, chave())['bem_id']
            for i in range(2)]
    doc = enviar(banco, PNG, perfil=EMPRESA)['comprovante_id']
    rpc(banco, 'criar_vinculo_documento', EMPRESA, doc, {'tipo_entidade': 'PATRIMONIO', 'entidade_id': bens[0]})
    e = erro(rpc, banco, 'criar_vinculo_documento', EMPRESA, doc, {'tipo_entidade': 'PATRIMONIO', 'entidade_id': bens[1]})
    assert 'ja esta vinculado a um bem' in str(e)


def test_privilegios(banco):
    tela = ('enviar_comprovante', 'atualizar_comprovante', 'validar_comprovante', 'excluir_comprovante', 'criar_vinculo_documento',
            'atualizar_vinculo_documento', 'remover_vinculo_documento', 'criar_financeiro_documento')
    linhas_ = sql(banco, """select p.proname n, has_function_privilege('authenticated', p.oid, 'EXECUTE') a,
                                   has_function_privilege('anon', p.oid, 'EXECUTE') x, p.prosecdef d
                              from pg_proc p join pg_namespace s on s.oid = p.pronamespace
                             where s.nspname = 'financeiro' and (p.proname = any(%s) or p.proname like 'doc\\_%%'
                                   or p.proname in ('repeticao_documento', 'registrar_operacao_documento'))""", (list(tela),))
    for r in linhas_:
        assert (r['a'], r['x']) == ((True, False) if r['n'] in tela else (False, False)), r
    assert sum(r['n'] in tela for r in linhas_) == len(tela)


def test_reversao_remove_as_funcoes_e_preserva_os_dados(banco):
    doc = enviar(banco, PNG)['comprovante_id']
    conn = psycopg2.connect(banco)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(REVERSAO.read_text(encoding='utf-8'))
    conn.close()
    assert sql(banco, "select count(*) n from pg_proc p join pg_namespace s on s.oid = p.pronamespace where s.nspname = 'financeiro' "
                      "and p.proname in ('enviar_comprovante', 'criar_financeiro_documento', 'doc_comprovante')")[0]['n'] == 0
    assert sql(banco, 'select count(*) n from public.ir_comprovante_arquivo where comprovante_id = %s', (doc,))[0]['n'] == 1
    conn = psycopg2.connect(banco)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(MIGRATION.read_text(encoding='utf-8'))
    conn.close()
    assert enviar(banco, PDF, 'depois.pdf')['duplicado'] is False


def test_documento_vinculado_a_financiamento_do_perfil(banco):
    """Documentos x Financiamentos: vinculo ao contrato do perfil (resumo = nome); contrato de outro perfil e recusado."""
    from tests.test_supabase_integracao_1123_1126 import novo_financiamento
    fid = novo_financiamento(banco)
    fid_b = novo_financiamento(banco, perfil=PERFIL_B, usuario=USUARIO_B, nome='Contrato do perfil B (ficticio)')
    doc = enviar(banco, PNG)['comprovante_id']
    v = rpc(banco, 'criar_vinculo_documento', PESSOAL, doc, {'tipo_entidade': 'FINANCIAMENTO', 'entidade_id': fid, 'tipo_vinculo': 'CONTRATO'})
    assert sql(banco, 'select tipo_entidade, entidade_id, resumo_entidade, tipo_vinculo from public.ir_comprovante_vinculo where id = %s',
               (v['vinculo_id'],)) == [{'tipo_entidade': 'FINANCIAMENTO', 'entidade_id': fid, 'resumo_entidade': 'SAC integracao (ficticio)',
                                        'tipo_vinculo': 'CONTRATO'}]
    antes = resumo_tabelas(banco)
    assert 'perfil' in str(erro(rpc, banco, 'criar_vinculo_documento', PESSOAL, doc, {'tipo_entidade': 'FINANCIAMENTO', 'entidade_id': fid_b}))
    assert resumo_tabelas(banco) == antes
