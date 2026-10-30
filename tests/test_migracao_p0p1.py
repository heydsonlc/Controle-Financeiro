"""
FIN-MIGRACAO-P0P1-01 (Etapa 1) — Empresa no novo aplicativo e catalogo de categorias, em cluster PostgreSQL local descartavel.

Reproduz o estado da producao antes da Etapa 2: Pessoal no novo aplicativo (com recorrencias, cartao, contas e um item
legado SEM perfil e ativo), Empresa VAZIA ainda sem escritor (padrao FLASK) com o titular gestor, catalogo de categorias
sem escritor nem gestor e as 10 categorias sistemicas de Mobilidade. Prova:
- Empresa FLASK: toda escrita recusada (SISTEMA_FLASK), nada gravado;
- a ativacao (definir_gerador_recorrencia, a operacao oficial) so grava a linha do escritor e a do historico: nenhuma
  outra tabela muda (ativar != gerar), a previa da Empresa e zero em qualquer competencia (inclusive a retroativa) e a
  geracao com zero nao grava nada; o Pessoal continua igual;
- Empresa NOVO: envio de documento grava os bytes, o nome, o MIME e o tamanho no perfil certo; conta bancaria tambem;
- catalogo: recusado (CATALOGO_FLASK) ate o escritor NOVO; conta nao gestora recusada (42501); gestor cria, edita
  (nome, descricao, cor, icone, ativa), cadastra e remove palavras-chave e exclui; sistemica nunca e editada nem excluida;
  categoria em uso nao e excluida (COM_VINCULOS); as sistemicas ficam intactas.
"""
import base64
import json
import uuid

import pytest

from tests.supabase_local import EMPRESA_D, USUARIO_D, ClusterLocal, semear_empresa_vazia, semear_recorrencias
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, atribuir, chamar, copiar, sql

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

EMPRESA = EMPRESA_D['id']
PESSOAL = ID['PESSOAL']
PNG = b'\x89PNG\r\n\x1a\n' + b'documento ficticio P0P1 ' * 30
# Tabelas que a ativacao do escritor PODE mudar (e so com uma linha a mais cada).
ADMINISTRATIVAS = {'financeiro.gerador_recorrencia', 'financeiro.gerador_recorrencia_historico'}


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    from backend.services.categoria_default import CATEGORIAS_SISTEMICAS_MOBILIDADE
    with ClusterLocal(PG_BIN, tmp_path_factory.mktemp('p0p1')) as c:
        c.preparar(contas=False)
        conn = c.conectar()
        with conn.cursor() as cur:
            semear_recorrencias(cur)
            semear_empresa_vazia(cur)
            for codigo, d in CATEGORIAS_SISTEMICAS_MOBILIDADE.items():
                cur.execute("insert into public.categoria (nome, descricao, cor, icone, ativo, sistemica, codigo_sistema, "
                            "modulo_origem, bloquear_edicao, bloquear_exclusao) values (%s, %s, %s, %s, true, true, %s, "
                            "'mobilidade', true, true)", (d['nome'], d.get('descricao'), d.get('cor'), d.get('icone'), codigo))
        conn.close()
        yield c


@pytest.fixture
def banco(cluster):
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')  # como a producao: Pessoal no novo aplicativo desde 29/10/2026
    return dsn


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


def retrato(dsn):
    """Contagem e md5 de todas as tabelas de public e financeiro (o que a ativacao nao pode mudar)."""
    tabelas = sql(dsn, "select table_schema || '.' || table_name as t from information_schema.tables "
                       "where table_type = 'BASE TABLE' and table_schema in ('public', 'financeiro') order by 1")
    saida = {}
    for linha in tabelas:
        esquema, nome = linha['t'].split('.')
        saida[linha['t']] = sql(dsn, f'select count(*) as n, md5(coalesce(string_agg(x::text, \'|\' order by x::text), \'\')) as h '
                                     f'from "{esquema}"."{nome}" x')[0]
    return saida


def como_d(dsn, comando, params=()):
    return chamar(dsn, USUARIO_D, comando, params)


def enviar(dsn, perfil=EMPRESA, usuario=USUARIO_D, conteudo=PNG, nome='nota-p0p1.png'):
    return chamar(dsn, usuario, 'select financeiro.enviar_comprovante(%s, %s::jsonb, %s, %s)',
                  (perfil, json.dumps({'nome_arquivo': nome, 'mime_type': 'image/png', 'ano_calendario': 2026}),
                   base64.b64encode(conteudo).decode(), str(uuid.uuid4())))


def conta_bancaria(dsn, perfil=EMPRESA, usuario=USUARIO_D):
    dados = {'nome': 'Conta Empresa (teste)', 'instituicao': 'Banco ficticio', 'tipo': 'Conta Corrente', 'saldo_inicial': 0,
             'cor_display': '#0f766e'}
    return chamar(dsn, usuario, 'select financeiro.criar_conta_bancaria(%s, %s::jsonb, %s)',
                  (perfil, json.dumps(dados), str(uuid.uuid4())))


def previa(dsn, mes, perfil=EMPRESA, usuario=USUARIO_D):
    return chamar(dsn, usuario, 'select financeiro.previa_geracao(%s, %s)', (perfil, mes))


MESES = ['2025-01-01', '2026-10-01', '2026-11-01', '2026-12-01', '2027-01-01', '2027-03-01', '2028-02-01']


# ---- Empresa ----

def test_empresa_flask_recusa_escritas_sem_gravar(banco):
    antes = retrato(banco)
    for tentativa in (lambda: enviar(banco), lambda: conta_bancaria(banco),
                      lambda: como_d(banco, 'select financeiro.criar_despesa(%s, %s::jsonb, %s)',
                                     (EMPRESA, json.dumps({'nome': 'Aluguel (teste)', 'valor': '10.00'}), str(uuid.uuid4())))):
        e = erro(tentativa)
        assert (e.pgcode, e.diag.message_hint) == ('P0001', 'SISTEMA_FLASK')
    assert retrato(banco) == antes


def test_ativar_empresa_nao_gera_nada(banco):
    antes = retrato(banco)
    previas_pessoal = {m: previa(banco, m, PESSOAL, USUARIO_A)['a_gerar'] for m in MESES}
    assert previa(banco, MESES[0])['gerador'] == 'FLASK'

    assert atribuir(banco, EMPRESA) == f'Perfil {EMPRESA}: FLASK (padrao) -> NOVO'

    depois = retrato(banco)
    mudaram = {t for t in antes if antes[t] != depois[t]}
    assert mudaram == ADMINISTRATIVAS
    for t in ADMINISTRATIVAS:
        assert depois[t]['n'] == antes[t]['n'] + 1
    assert sql(banco, 'select gerador_anterior, gerador_novo from financeiro.gerador_recorrencia_historico '
                      'where perfil_financeiro_id = %s', (EMPRESA,)) == [{'gerador_anterior': None, 'gerador_novo': 'NOVO'}]

    # Previa zero em toda competencia (inclusive a retroativa e com o legado sem perfil ativo, que e so do Pessoal).
    for mes in MESES:
        p = previa(banco, mes)
        assert (p['gerador'], p['pode_gerar'], p['a_gerar'], p['existentes'], p['rejeitadas'], p['competencias']) == \
            ('NOVO', True, 0, 0, 0, []), mes
        # Como a tela de Despesas: com zero a gerar ela nem chama; chamando com zero, nada e gravado.
        r = como_d(banco, 'select financeiro.gerar_mes(%s, %s, 0, %s::jsonb)', (EMPRESA, mes, '[]'))
        assert r['execucao_id'] is None, mes
    assert retrato(banco) == depois
    # Pessoal intocado: a mesma previa de antes.
    assert {m: previa(banco, m, PESSOAL, USUARIO_A)['a_gerar'] for m in MESES} == previas_pessoal


def test_empresa_novo_grava_documento_e_conta(banco):
    atribuir(banco, EMPRESA)
    doc = enviar(banco)
    assert doc['duplicado'] is False
    linha = sql(banco, """select c.perfil_financeiro_id, a.nome_arquivo, a.mime_type, a.tamanho_bytes, a.conteudo,
                                 a.comprovante_id = c.id as vinculado
                            from public.ir_comprovante c join public.ir_comprovante_arquivo a on a.comprovante_id = c.id
                           where c.id = %s""", (doc['comprovante_id'],))
    assert len(linha) == 1
    assert {k: v for k, v in linha[0].items() if k != 'conteudo'} == {
        'perfil_financeiro_id': EMPRESA, 'nome_arquivo': 'nota-p0p1.png', 'mime_type': 'image/png',
        'tamanho_bytes': len(PNG), 'vinculado': True}
    assert bytes(linha[0]['conteudo']) == PNG
    # O titular de outro perfil nao ve nem grava nele.
    assert erro(enviar, banco, usuario=USUARIO_A).pgcode == '42501'
    conta_bancaria(banco)
    assert sql(banco, 'select count(*) as n from public.conta_bancaria where perfil_financeiro_id = %s', (EMPRESA,))[0]['n'] == 1


# ---- Catalogo de categorias ----

def sistemicas(dsn):
    return sql(dsn, "select md5(string_agg(c::text, '|' order by c.id)) as h, count(*) as n from public.categoria c where c.sistemica")[0]


def catalogo(dsn, funcao, *args, usuario=USUARIO_D):
    marcadores = ', '.join('%s::jsonb' if isinstance(a, dict) else '%s' for a in args)
    valores = [json.dumps(a) if isinstance(a, dict) else a for a in args]
    return chamar(dsn, usuario, f'select financeiro.{funcao}({marcadores})', valores)


def test_catalogo_so_com_escritor_novo_e_gestor(banco):
    intactas = sistemicas(banco)
    assert intactas['n'] == 10
    nova = {'nome': 'Teste Migracao Catalogo', 'descricao': 'ficticia', 'cor': '#123456', 'icone': 'tag', 'ativo': True}
    assert como_d(banco, 'select financeiro.situacao_catalogo_categorias()') == {'escritor': 'FLASK', 'gestor': False}
    e = erro(catalogo, banco, 'criar_categoria', nova, str(uuid.uuid4()))
    assert (e.pgcode, e.diag.message_hint) == ('P0001', 'CATALOGO_FLASK')

    assert sql(banco, "select financeiro.definir_escritor_catalogo('NOVO', 'administrador de teste', 'cenario P0P1') as r")[0]['r'] == \
        'Catalogo de categorias: FLASK (padrao) -> NOVO'
    assert erro(catalogo, banco, 'criar_categoria', nova, str(uuid.uuid4())).pgcode == '42501'  # nao gestora

    sql(banco, "select financeiro.definir_gestor_catalogo(%s, true, 'administrador de teste', 'cenario P0P1')", (USUARIO_D['id'],))
    assert como_d(banco, 'select financeiro.situacao_catalogo_categorias()') == {'escritor': 'NOVO', 'gestor': True}
    assert chamar(banco, USUARIO_A, 'select financeiro.situacao_catalogo_categorias()') == {'escritor': 'NOVO', 'gestor': False}

    criada = catalogo(banco, 'criar_categoria', nova, str(uuid.uuid4()))
    cid = criada['categoria_id']
    assert sql(banco, 'select nome, descricao, cor, icone, ativo, sistemica, perfil_financeiro_id from public.categoria where id = %s',
               (cid,)) == [{**nova, 'sistemica': False, 'perfil_financeiro_id': None}]
    editada = {'nome': 'Teste Migracao Catalogo (editada)', 'descricao': 'outra', 'cor': '#654321', 'icone': 'star', 'ativo': False}
    catalogo(banco, 'editar_categoria', cid, editada)
    assert sql(banco, 'select nome, descricao, cor, icone, ativo from public.categoria where id = %s', (cid,)) == [editada]

    palavra = catalogo(banco, 'criar_palavra_chave', cid, '  Teste   P0P1 ')
    assert (palavra['palavra'], palavra['created']) == ('teste p0p1', True)
    lidas = como_d(banco, 'select financeiro.palavras_chave_tela(%s)', (EMPRESA,))
    assert [p['palavra'] for p in lidas[str(cid)]] == ['teste p0p1']
    catalogo(banco, 'remover_palavra_chave', cid, palavra['id'])
    assert sql(banco, 'select ativo from public.categoria_palavra_chave where id = %s', (palavra['id'],)) == [{'ativo': False}]

    # Sistemica: nem edicao nem exclusao. Em uso (item de despesa do Pessoal): nao exclui.
    mob = sql(banco, "select id from public.categoria where codigo_sistema = 'MOB_COMBUSTIVEL'")[0]['id']
    for funcao, args in (('editar_categoria', (mob, {'descricao': 'x'})), ('excluir_categoria', (mob,))):
        e = erro(catalogo, banco, funcao, *args)
        assert e.diag.message_hint == 'SISTEMICA', funcao
    e = erro(catalogo, banco, 'excluir_categoria', 951)
    assert e.diag.message_hint == 'COM_VINCULOS'
    # O nome de uma sistemica nao e reaproveitado por categoria comum (ja existe; sem diferenciar maiusculas ASCII: o
    # cluster local e criado sem locale, em que lower() nao muda letras acentuadas).
    e = erro(catalogo, banco, 'criar_categoria', {**nova, 'nome': 'COMBUSTível'}, str(uuid.uuid4()))
    assert e.diag.message_primary == 'Ja existe uma categoria com este nome'

    assert catalogo(banco, 'excluir_categoria', cid) == {'categoria_id': cid, 'excluida': True}
    assert sql(banco, 'select count(*) as n from public.categoria where id = %s', (cid,))[0]['n'] == 0
    assert sql(banco, 'select count(*) as n from public.categoria_palavra_chave where categoria_id = %s', (cid,))[0]['n'] == 0
    assert sistemicas(banco) == intactas
    # Outra conta continua sem gravar no catalogo.
    assert erro(catalogo, banco, 'criar_categoria', nova, str(uuid.uuid4()), usuario=USUARIO_A).pgcode == '42501'


def test_catalogo_novo_exige_as_sistemicas(banco):
    sql(banco, "delete from public.categoria where codigo_sistema = 'MOB_LAVAGEM'")
    e = erro(sql, banco, "select financeiro.definir_escritor_catalogo('NOVO', 'administrador de teste', 'cenario P0P1')")
    assert 'MOB_LAVAGEM' in e.diag.message_primary
    assert sql(banco, 'select count(*) as n from financeiro.catalogo_categorias')[0]['n'] == 0


def test_ativacoes_sao_independentes_do_pessoal(banco):
    """A operacao da Etapa 2 inteira (Empresa + catalogo + gestor) nao muda nenhuma linha de dados."""
    antes = retrato(banco)
    atribuir(banco, EMPRESA)
    sql(banco, "select financeiro.definir_escritor_catalogo('NOVO', 'administrador de teste', 'cenario P0P1')")
    sql(banco, "select financeiro.definir_gestor_catalogo(%s, true, 'administrador de teste', 'cenario P0P1')", (USUARIO_D['id'],))
    depois = retrato(banco)
    assert {t for t in antes if antes[t] != depois[t]} == ADMINISTRATIVAS | {'financeiro.catalogo_categorias',
                                                                            'financeiro.gestor_catalogo'}
