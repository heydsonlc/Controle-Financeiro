"""
Testes FIN-PATRIMONIO-2 — escrita de Patrimonio no novo aplicativo (migration 20261126090000), em cluster local.

Fidelidade: a MESMA sequencia de operacoes (caixinhas, transferencias, bens, vinculos e bem a partir de documento) e
feita pelo PROPRIO Flask numa copia do banco (perfis no Flask) e pelas funcoes novas noutra copia identica (perfis no
novo aplicativo); as tabelas resultantes sao comparadas linha a linha (fora os carimbos de hora). Tambem: regras e
correcoes (saldo, exclusao de transferencia, exclusao de bem so sem documento), concorrencia, escritor unico nos dois
sentidos, permissoes e isolamento, repeticao, sugestao a partir de documento igual a do Flask, e a reversao.
"""
import json
import subprocess
from decimal import Decimal
import threading
import uuid
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_receitas_categorias_tela import flask
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
REVERSAO = Path(__file__).resolve().parent.parent / 'supabase' / 'reversao' / '20261126090000_remover_patrimonio_escrita.sql'
TEXTO_NOTEBOOK = 'NFS-e numero 004512 Notebook Dell Inspiron 15 i5-1135G7 garantia 12 meses'
DOCUMENTOS = [  # prestador, valor, data, texto extraido, origem
    ('Fornecedor ficticio LTDA', '7500.55', '2031-03-09', None, None),
    ('Moveis ficticios ME', '1890.00', '2031-04-02', 'Cadeira ergonomica presidente', 'MANUAL'),
    ('Papelaria ficticia', '310.40', None, None, None),
    ('Info ficticia SA', '2450.00', '2031-05-20', None, None),
    ('Loja ficticia de informatica', '6899.90', '2031-06-01', TEXTO_NOTEBOOK, 'OCR_TESSERACT'),
    (None, None, None, None, None),
]


def preparar(dsn):
    """Mesmos dados nas copias: documentos fiscais ficticios da Empresa e o usuario A gerindo a Empresa."""
    sql(dsn, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s",
        (EMPRESA,))
    ids = []
    for prestador, valor, data, texto, origem in DOCUMENTOS:
        ids.append(sql(dsn, "insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, data_documento, "
                            "prestador_nome, valor, status, hash_arquivo, texto_extraido, origem_classificacao, created_at, "
                            "updated_at) values (%s, 2031, %s, %s, %s, 'IMPORTADO', md5(random()::text) || md5(random()::text), "
                            "%s, %s, '2031-07-01 10:00', '2031-07-01 10:00') returning id",
                       (EMPRESA, data, prestador, valor, texto, origem))[0]['id'])
    return ids


CONTAS = [
    ('conta_a', {'nome': 'Reserva (ficticia)', 'tipo': 'Reserva', 'saldo_inicial': 5000, 'meta': 20000, 'cor': '#123456'}),
    ('conta_b', {'nome': 'Viagem (ficticia)', 'tipo': 'Poupança', 'saldo_inicial': 800, 'meta': 0, 'observacoes': 'teste'}),
    ('conta_c', {'nome': 'Antiga (ficticia)', 'tipo': 'Investimento', 'saldo_inicial': 0}),
]
EDICAO_B = {'nome': 'Viagem 2032 (ficticia)', 'meta': 1500, 'cor': '#abcdef', 'observacoes': 'nova'}
TRANSFERENCIAS = [
    ('t1', 'conta_a', 'conta_b', 300, '2031-01-05', 'Aporte'),
    ('t2', 'conta_a', 'conta_b', 120.5, '2031-02-10', 'Ajuste'),
    ('t3', 'conta_b', 'conta_c', 50, '2031-02-10', None),
]
BENS = [
    ('bem0', {'nome': 'Notebook de trabalho (ficticio)', 'codigo': 'PAT-001', 'categoria': 'Informatica', 'valor_aquisicao': 7500.555,
              'vida_util_meses': 36, 'data_aquisicao': '2031-03-10', 'imagem_arquivo': 'Patrimonio_notebook.jpg', 'fornecedor': ' Loja X '}),
    ('bem1', {'nome': 'Cadeira ergonomica (ficticia)', 'categoria': 'Moveis', 'valor_aquisicao': 1200, 'data_aquisicao': '2029-07-01',
              'status_documental': 'pendente', 'imagem_arquivo': 'nao_existe.png'}),
    ('bem2', {'nome': 'Impressora laser (ficticia)', 'categoria': 'Informatica', 'valor_aquisicao': '980.4', 'status': 'BAIXADO',
              'status_documental': 'DIVERGENTE', 'vida_util_meses': 'x', 'data_aquisicao': '31/12/2030'}),
    ('bem3', {'nome': 'Item sem categoria (ficticio)', 'categoria': '', 'valor_aquisicao': 0, 'status_documental': 'NAO_APLICAVEL',
              'status': 'inexistente'}),
]
EDICAO_BEM0 = {'valor_aquisicao': 8000, 'vida_util_meses': 40, 'status': 'em_revisao', 'imagem_arquivo': 'patrimonio_monitor.png',
               'nome': 'Notebook (editado)', 'descricao': '  '}


def pelo_flask(dsn, docs):
    passos = [('perfil', PESSOAL)]
    passos += [(nome, 'post', '/api/patrimonio/contas', dados) for nome, dados in CONTAS]
    passos += [('', 'put', '/api/patrimonio/contas/{conta_b}', EDICAO_B),
               ('', 'delete', '/api/patrimonio/contas/{conta_c}', None),
               ('', 'put', '/api/patrimonio/contas/{conta_c}', {'ativo': True})]
    passos += [(n, 'post', '/api/patrimonio/transferencias', {'conta_origem_id': '{' + o + '}', 'conta_destino_id': '{' + d + '}',
                                                             'valor': v, 'data_transferencia': data, 'descricao': desc})
               for n, o, d, v, data, desc in TRANSFERENCIAS]
    passos += [('', 'delete', '/api/patrimonio/transferencias/{t2}', None), ('perfil', EMPRESA)]
    passos += [(nome, 'post', '/api/patrimonio/bens', dados) for nome, dados in BENS]
    passos += [('', 'put', '/api/patrimonio/bens/{bem0}', EDICAO_BEM0),
               ('', 'post', '/api/patrimonio/bens/{bem0}/vincular-documento', {'comprovante_id': docs[0], 'tipo_vinculo': 'RECIBO'}),
               ('bem4', 'post', '/api/patrimonio/bens/criar-a-partir-documento', {'comprovante_id': docs[1]}),
               ('', 'post', '/api/patrimonio/bens/{bem0}/vincular-documento', {'comprovante_id': docs[2], 'natureza': 'outro',
                                                                               'observacoes': 'troca'}),
               ('', 'post', '/api/patrimonio/bens/{bem3}/vincular-documento', {'comprovante_id': docs[3], 'status_lastro': 'pendente'})]
    r = flask(dsn, passos)
    assert all(status in (200, 201) for status, _ in r.values()), r
    return r


def pelo_novo(dsn, docs):
    ids = {}

    def chave():
        return str(uuid.uuid4())
    for nome, dados in CONTAS:
        ids[nome] = rpc(dsn, 'criar_caixinha', PESSOAL, dados, chave())['conta_id']
    rpc(dsn, 'editar_caixinha', PESSOAL, ids['conta_b'], EDICAO_B)
    rpc(dsn, 'inativar_caixinha', PESSOAL, ids['conta_c'])
    rpc(dsn, 'editar_caixinha', PESSOAL, ids['conta_c'], {'ativo': True})
    for n, o, d, v, data, desc in TRANSFERENCIAS:
        ids[n] = rpc(dsn, 'criar_transferencia_patrimonio', PESSOAL, {'conta_origem_id': ids[o], 'conta_destino_id': ids[d],
                                                                     'valor': v, 'data_transferencia': data, 'descricao': desc},
                     chave())['transferencia_id']
    rpc(dsn, 'excluir_transferencia_patrimonio', PESSOAL, ids['t2'])
    for nome, dados in BENS:
        ids[nome] = rpc(dsn, 'criar_bem_patrimonial', EMPRESA, dados, chave())['bem_id']
    rpc(dsn, 'editar_bem_patrimonial', EMPRESA, ids['bem0'], EDICAO_BEM0)
    rpc(dsn, 'vincular_documento_bem', EMPRESA, ids['bem0'], {'comprovante_id': docs[0], 'tipo_vinculo': 'RECIBO'})
    ids['bem4'] = rpc(dsn, 'criar_bem_de_documento', EMPRESA, {'comprovante_id': docs[1]}, chave())['bem_id']
    rpc(dsn, 'vincular_documento_bem', EMPRESA, ids['bem0'], {'comprovante_id': docs[2], 'natureza': 'outro', 'observacoes': 'troca'})
    rpc(dsn, 'vincular_documento_bem', EMPRESA, ids['bem3'], {'comprovante_id': docs[3], 'status_lastro': 'pendente'})
    return ids


SEM_HORA = {'criado_em', 'created_at', 'updated_at'}


def tabelas(dsn):
    saida = {}
    for tabela in ('conta_patrimonio', 'transferencia', 'bem_patrimonial', 'ir_comprovante_vinculo'):
        linhas = sql(dsn, f'select * from public.{tabela} order by id')
        saida[tabela] = [{k: v for k, v in linha.items() if k not in SEM_HORA} for linha in linhas]
    return saida


@pytest.fixture(scope='module')
def comparacao(cluster):  # noqa: F811
    no_flask, no_novo = copiar(cluster), copiar(cluster)
    docs = preparar(no_flask)
    assert preparar(no_novo) == docs
    r_flask = pelo_flask(no_flask, docs)
    atribuir(no_novo, 'PESSOAL')
    atribuir(no_novo, 'EMPRESA')
    ids = pelo_novo(no_novo, docs)
    return {'flask': no_flask, 'novo': no_novo, 'docs': docs, 'ids': ids, 'r_flask': r_flask}


def test_mesmas_linhas_que_o_flask(comparacao):
    flask_t, novo_t = tabelas(comparacao['flask']), tabelas(comparacao['novo'])
    for tabela in flask_t:
        assert novo_t[tabela] == flask_t[tabela], tabela
    # Conferencias do cenario: saldos depois da exclusao de t2, vinculo trocado (o anterior fica inativo).
    contas = {c['nome']: c for c in novo_t['conta_patrimonio']}
    assert (contas['Reserva (ficticia)']['saldo_atual'], contas['Viagem 2032 (ficticia)']['saldo_atual'],
            contas['Antiga (ficticia)']['saldo_atual']) == (4700, 1050, 50)
    vinculos = [(v['comprovante_id'], v['entidade_id'], v['ativo']) for v in novo_t['ir_comprovante_vinculo']]
    docs, ids = comparacao['docs'], comparacao['ids']
    assert (docs[0], ids['bem0'], False) in vinculos and (docs[2], ids['bem0'], True) in vinculos


def test_leituras_da_tela_iguais_depois_da_escrita(comparacao):
    for funcao, args in (('patrimonio_bens_tela', (EMPRESA, {}, None)), ('patrimonio_resumo_tela', (EMPRESA,)),
                         ('patrimonio_contas_tela', (PESSOAL, None)),
                         ('patrimonio_transferencias_tela', (PESSOAL, None, None, None, None)),
                         ('patrimonio_documentos_vinculaveis_tela', (EMPRESA, None))):
        def ler(dsn):
            texto = json.dumps(rpc(dsn, funcao, *args), sort_keys=True)
            for chave in SEM_HORA:  # carimbos de hora diferem entre as copias
                texto = __import__('re').sub(rf'"{chave}": "[^"]*"', f'"{chave}": "-"', texto)
            return texto
        assert ler(comparacao['novo']) == ler(comparacao['flask']), funcao


def test_documentos_vinculaveis_iguais_ao_flask(comparacao):
    r = flask(comparacao['flask'], [('perfil', EMPRESA), ('docs', 'get', '/api/patrimonio/documentos-vinculaveis', None),
                                    ('busca', 'get', '/api/patrimonio/documentos-vinculaveis?busca=INFO', None)])
    # FIN-PRE-PRODUCAO-1 (regra do titular): um documento ja ligado a um bem continua vinculavel a outro. Fora esses
    # (o Flask os esconde), a lista e a do Flask.
    ligados = {x['comprovante_id'] for x in sql(comparacao['novo'], "select comprovante_id from public.ir_comprovante_vinculo "
                                                                   "where tipo_entidade = 'PATRIMONIO' and ativo")}
    for nome, busca in (('docs', None), ('busca', 'INFO')):
        novo = rpc(comparacao['novo'], 'patrimonio_documentos_vinculaveis_tela', EMPRESA, busca)
        sem_ligados = [d for d in json.loads(json.dumps(novo, default=str)) if d['id'] not in ligados]
        assert sem_ligados == json.loads(json.dumps(r[nome][1]['data'])), nome
    assert ligados  # o cenario tem documento ligado a um bem


def sugestao_no_navegador(dados):
    modulo = (ROOT / 'web' / 'src' / 'js' / 'patrimonio-sugestao.js').as_uri()
    codigo = (f"import {{ gerarSugestao }} from '{modulo}';"
              "let t = ''; process.stdin.on('data', (c) => { t += c; });"
              "process.stdin.on('end', () => { process.stdout.write(JSON.stringify(gerarSugestao(JSON.parse(t)))); });")
    r = subprocess.run(['node', '--input-type=module', '-e', codigo], input=json.dumps(dados, default=str),
                       capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_sugestao_a_partir_de_documento_igual_ao_flask(comparacao):
    docs = comparacao['docs']
    passos = [('perfil', EMPRESA)] + [(f'd{i}', 'get', f'/api/patrimonio/bens/sugestao-a-partir-documento/{d}', None)
                                      for i, d in enumerate(docs)]
    r = flask(comparacao['flask'], passos)
    for i, d in enumerate(docs):
        esperado = r[f'd{i}'][1]['data']
        dados = chamar(comparacao['novo'], USUARIO_A, 'select financeiro.patrimonio_documento_sugestao_tela(%s, %s)', (EMPRESA, d))
        novo = sugestao_no_navegador(dados)
        for s in (novo, esperado):  # o vinculo existente foi criado em copias diferentes: so a hora difere
            if s.get('vinculo_existente'):
                s['vinculo_existente'] = {k: v for k, v in s['vinculo_existente'].items() if k not in SEM_HORA}
        assert json.loads(json.dumps(novo)) == json.loads(json.dumps(esperado)), i
    notebook = r['d4'][1]['data']
    assert (notebook['nome'], notebook['documento_numero'], notebook['imagem_arquivo']) == \
        ('Notebook Dell Inspiron 15 I5-1135G7 Garantia 12 Me', '004512', 'Patrimonio_notebook.jpg')  # corte da regex do Flask


# ---------------------------------------------------------------------------------------------------------------------
# Regras, correcoes, concorrencia
# ---------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    docs = preparar(dsn)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'EMPRESA')
    return dsn, docs


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


def caixinha(dsn, nome, saldo, perfil=PESSOAL, usuario=USUARIO_A):
    return rpc(dsn, 'criar_caixinha', perfil, {'nome': nome, 'saldo_inicial': saldo}, str(uuid.uuid4()), usuario=usuario)['conta_id']


def transferir(dsn, origem, destino, valor, chave=None, data='2031-01-10'):
    return rpc(dsn, 'criar_transferencia_patrimonio', PESSOAL, {'conta_origem_id': origem, 'conta_destino_id': destino,
                                                                'valor': valor, 'data_transferencia': data}, chave or str(uuid.uuid4()))


def saldo(dsn, conta):
    return sql(dsn, 'select saldo_atual from public.conta_patrimonio where id = %s', (conta,))[0]['saldo_atual']


def test_validacoes_de_transferencia_e_caixinha(banco):
    dsn, _ = banco
    a, b = caixinha(dsn, 'A', '100.00'), caixinha(dsn, 'B', 0)
    casos = [({'conta_destino_id': b, 'valor': 1, 'data_transferencia': '2031-01-01'}, 'Conta de origem é obrigatória'),
             ({'conta_origem_id': a, 'conta_destino_id': a, 'valor': 1, 'data_transferencia': '2031-01-01'}, 'não podem ser iguais'),
             ({'conta_origem_id': a, 'conta_destino_id': b, 'valor': 0, 'data_transferencia': '2031-01-01'}, 'maior que zero'),
             ({'conta_origem_id': a, 'conta_destino_id': b, 'valor': 1}, 'Data da transferência é obrigatória'),
             ({'conta_origem_id': a, 'conta_destino_id': b, 'valor': 1, 'data_transferencia': '10/01/2031'}, 'Formato de data'),
             ({'conta_origem_id': a, 'conta_destino_id': b, 'valor': '100.01', 'data_transferencia': '2031-01-01'}, 'Saldo insuficiente'),
             ({'conta_origem_id': a, 'conta_destino_id': b, 'valor': '0.001', 'data_transferencia': '2031-01-01'}, '2 casas')]
    for dados, texto in casos:
        assert texto in str(erro(rpc, dsn, 'criar_transferencia_patrimonio', PESSOAL, dados, str(uuid.uuid4()))), dados
    assert 'Já existe uma conta' in str(erro(caixinha, dsn, 'A', 0))
    assert 'Nome é obrigatório' in str(erro(caixinha, dsn, '  ', 0))
    assert '2 casas' in str(erro(caixinha, dsn, 'Negativa', -1))
    rpc(dsn, 'inativar_caixinha', PESSOAL, b)
    assert 'destino não encontrada ou inativa' in str(erro(transferir, dsn, a, b, 10))
    assert (saldo(dsn, a), saldo(dsn, b)) == (100, 0)  # nada mudou


def test_repeticao_nao_duplica_e_exclusao_que_deixaria_negativo_e_recusada(banco):
    dsn, _ = banco
    a, b, c = caixinha(dsn, 'A', 100), caixinha(dsn, 'B', 0), caixinha(dsn, 'C', 0)
    chave = str(uuid.uuid4())
    t = transferir(dsn, a, b, 60, chave)
    assert transferir(dsn, a, b, 60, chave)['repetida'] is True
    assert (saldo(dsn, a), saldo(dsn, b)) == (40, 60)
    transferir(dsn, b, c, 50)  # B so tem 10 agora
    e = erro(rpc, dsn, 'excluir_transferencia_patrimonio', PESSOAL, t['transferencia_id'])
    assert e.diag.message_hint == 'SALDO_DESTINO'
    assert (saldo(dsn, a), saldo(dsn, b), saldo(dsn, c)) == (40, 10, 50)
    assert sql(dsn, 'select count(*) as n from public.transferencia')[0]['n'] == 2


def test_transferencias_simultaneas_nao_deixam_saldo_negativo(banco):
    dsn, _ = banco
    a, b, c = caixinha(dsn, 'A', 100), caixinha(dsn, 'B', 0), caixinha(dsn, 'C', 0)
    barreira, resultados = threading.Barrier(2), []

    def executar(destino):
        barreira.wait(timeout=10)
        try:
            resultados.append(transferir(dsn, a, destino, 80))
        except psycopg2.Error as e:
            resultados.append(e)

    tarefas = [threading.Thread(target=executar, args=(d,)) for d in (b, c)]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join(timeout=60)
    assert sum(isinstance(r, dict) for r in resultados) == 1
    assert saldo(dsn, a) == 20 and saldo(dsn, b) + saldo(dsn, c) == 80


def test_bens_so_na_empresa_e_exclusao_so_sem_documento(banco):
    dsn, docs = banco
    assert erro(rpc, dsn, 'criar_bem_patrimonial', PESSOAL, {'nome': 'X'}, str(uuid.uuid4())).diag.message_hint == 'SO_EMPRESA'
    assert 'Nome do bem e obrigatorio' in str(erro(rpc, dsn, 'criar_bem_patrimonial', EMPRESA, {'nome': ' '}, str(uuid.uuid4())))
    livre = rpc(dsn, 'criar_bem_patrimonial', EMPRESA, {'nome': 'Sem documento'}, str(uuid.uuid4()))['bem_id']
    com_doc = rpc(dsn, 'criar_bem_patrimonial', EMPRESA, {'nome': 'Com documento', 'comprovante_id': docs[0]},
                  str(uuid.uuid4()))['bem_id']
    assert sql(dsn, 'select status_documental, valor_aquisicao from public.bem_patrimonial where id = %s', (com_doc,))[0] == \
        {'status_documental': 'COM_LASTRO', 'valor_aquisicao': Decimal('7500.55')}
    # FIN-PRE-PRODUCAO-1 (regra do titular, migration 20261130090000): o mesmo documento pode estar em varios bens,
    # vinculado a outro bem ou originando um bem novo (nota com varios itens).
    outro = rpc(dsn, 'criar_bem_patrimonial', EMPRESA, {'nome': 'Outro com o mesmo documento'}, str(uuid.uuid4()))['bem_id']
    rpc(dsn, 'vincular_documento_bem', EMPRESA, outro, {'comprovante_id': docs[0]})
    rpc(dsn, 'criar_bem_de_documento', EMPRESA, {'comprovante_id': docs[0]}, str(uuid.uuid4()))
    assert sql(dsn, "select count(distinct entidade_id) as n from public.ir_comprovante_vinculo where comprovante_id = %s "
                    "and tipo_entidade = 'PATRIMONIO' and ativo", (docs[0],))[0]['n'] == 3
    # Com documento (mesmo trocado: o vinculo anterior fica inativo), nao exclui; sem documento, exclui.
    rpc(dsn, 'vincular_documento_bem', EMPRESA, com_doc, {'comprovante_id': docs[1]})
    assert erro(rpc, dsn, 'excluir_bem_patrimonial', EMPRESA, com_doc).diag.message_hint == 'COM_DOCUMENTO'
    assert rpc(dsn, 'excluir_bem_patrimonial', EMPRESA, livre) == {'bem_id': livre, 'excluido': True}
    assert sql(dsn, 'select count(*) as n from public.ir_comprovante_vinculo where entidade_id = %s', (com_doc,))[0]['n'] == 2
    # Documento de outro perfil: nao encontrado.
    alheio = sql(dsn, "insert into public.ir_comprovante (perfil_financeiro_id, ano_calendario, status, hash_arquivo) "
                      "values (%s, 2031, 'IMPORTADO', repeat('b', 64)) returning id", (PESSOAL,))[0]['id']
    assert 'nao encontrado' in str(erro(rpc, dsn, 'vincular_documento_bem', EMPRESA, com_doc, {'comprovante_id': alheio}))


def test_escritor_unico_permissoes_e_isolamento(banco, cluster):  # noqa: F811
    dsn, _ = banco
    a = caixinha(dsn, 'A', 100)
    # Outro titular (B) nao escreve no Pessoal de A; leitor (sem gestao) tambem nao.
    assert erro(caixinha, dsn, 'Alheia', 0, usuario=USUARIO_B).pgcode == '42501'
    assert erro(rpc, dsn, 'editar_caixinha', PESSOAL, a, {'nome': 'X'}, usuario=USUARIO_B).pgcode == '42501'
    atribuir(dsn, 'PERFIL_B')
    assert erro(rpc, dsn, 'inativar_caixinha', PERFIL_B, a, usuario=USUARIO_B).diag.message_hint == 'NAO_ENCONTRADA'
    # Perfil ainda no Flask: nada e gravado.
    flask_dsn = copiar(cluster)
    antes = sql(flask_dsn, 'select count(*) as n from public.conta_patrimonio')[0]['n']
    assert erro(caixinha, flask_dsn, 'No Flask', 0).diag.message_hint == 'SISTEMA_FLASK'
    assert sql(flask_dsn, 'select count(*) as n from public.conta_patrimonio')[0]['n'] == antes
    # E o Flask recusa o perfil do novo aplicativo (409), sem gravar; consultas continuam.
    r = flask(dsn, [('perfil', PESSOAL), ('criar', 'post', '/api/patrimonio/contas', {'nome': 'Pelo Flask'}),
                    ('transf', 'post', '/api/patrimonio/transferencias', {'conta_origem_id': a, 'conta_destino_id': a, 'valor': 1,
                                                                          'data_transferencia': '2031-01-01'}),
                    ('listar', 'get', '/api/patrimonio/contas', None)])
    assert r['criar'][0] == 409 and r['criar'][1]['codigo'] == 'SISTEMA_NOVO' and r['transf'][0] == 409
    assert r['listar'][0] == 200
    assert sql(dsn, "select count(*) as n from public.conta_patrimonio where nome = 'Pelo Flask'")[0]['n'] == 0


def test_privilegios(banco):
    dsn, _ = banco
    publicas = ('criar_caixinha(integer, jsonb, uuid)', 'editar_caixinha(integer, integer, jsonb)', 'inativar_caixinha(integer, integer)',
                'criar_transferencia_patrimonio(integer, jsonb, uuid)', 'excluir_transferencia_patrimonio(integer, integer)',
                'criar_bem_patrimonial(integer, jsonb, uuid)', 'criar_bem_de_documento(integer, jsonb, uuid)',
                'editar_bem_patrimonial(integer, integer, jsonb)', 'vincular_documento_bem(integer, integer, jsonb)',
                'excluir_bem_patrimonial(integer, integer)', 'patrimonio_documentos_vinculaveis_tela(integer, text)',
                'patrimonio_documento_sugestao_tela(integer, integer)')
    internas = ('repeticao_patrimonio(uuid, integer, text)', 'inserir_bem(integer, jsonb)',
                'vincular_documento_ao_bem(integer, integer, integer, jsonb)', 'travar_caixinha(integer, integer)')
    for f, esperado in [(f, (True, False)) for f in publicas] + [(f, (False, False)) for f in internas]:
        r = sql(dsn, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                     "has_function_privilege('anon', %s, 'execute') as n", (f'financeiro.{f}', f'financeiro.{f}'))[0]
        assert (r['a'], r['n']) == esperado, f
    assert sql(dsn, "select has_table_privilege('authenticated', 'financeiro.operacao_patrimonio', 'select') as s")[0]['s'] is False


def test_reversao_remove_as_funcoes_e_preserva_os_dados(banco):
    dsn, _ = banco
    a = caixinha(dsn, 'Fica', 10)
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(REVERSAO.read_text(encoding='utf-8'))
    finally:
        conn.close()
    assert sql(dsn, 'select saldo_atual from public.conta_patrimonio where id = %s', (a,))[0]['saldo_atual'] == 10
    assert not sql(dsn, "select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro' "
                        "and p.proname in ('criar_caixinha', 'criar_bem_patrimonial', 'repeticao_patrimonio')")
    assert sql(dsn, "select to_regclass('financeiro.operacao_patrimonio') as t")[0]['t'] is None
