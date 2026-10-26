"""
Testes FIN-FIDELIDADE-RECEITAS-CATEGORIAS-1 — telas originais de Receitas e Categorias (migration 20261119090000).

Fidelidade: no cluster descartavel o PROPRIO Flask monta um cenario FICTICIO pelas rotas dele (fonte recorrente com as 12
previsoes geradas, fonte avulsa, recebimento parcial, recebimento pontual, estorno, Categoria do Cartao, vinculo e
palavra-chave) e responde os GETs que as telas originais chamam; o resultado e comparado campo a campo com as leituras
novas, para Pessoal, Empresa e Perfil B. Escrita de Categorias do Cartao: a mesma sequencia no Flask (perfil no Flask) e
no novo aplicativo (perfil atribuido a ele) deixa o mesmo estado; escritor unico, quem so le, isolamento e privilegios.
"""
import json
import os
import subprocess
import sys
from datetime import date

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_financiamentos_leitura import igual
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    ROOT,
    USUARIO_B,
    atribuir,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, EMPRESA, PERFIL_B = ID['PESSOAL'], ID['EMPRESA'], ID['PERFIL_B']
HOJE = date.today()
ANO = HOJE.year
MES = HOJE.strftime('%Y-%m-01')

# Script do Flask: login, perfil ativo e uma lista de requisicoes; '{nome}' no corpo/rota vem de respostas anteriores.
_SCRIPT = """
import json, sys, uuid
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    email = f'flask.rc.{uuid.uuid4().hex[:8]}@teste.local'  # uma conta por execucao
    u = Usuario(email=email, nome='RC', ativo=True)
    u.definir_senha('Senha-ficticia-rc-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-rc-2026'}).status_code == 302
ids = {}
def preencher(v):
    if isinstance(v, str):
        if v.startswith('{') and v.endswith('}') and v[1:-1] in ids:
            return ids[v[1:-1]]  # valor inteiro: o id
        for k, x in ids.items():
            v = v.replace('{' + k + '}', str(x))  # dentro da rota
        return v
    if isinstance(v, dict):
        return {k: preencher(x) for k, x in v.items()}
    return v
saida = []
for passo in json.loads(sys.argv[1]):
    if passo[0] == 'perfil':
        assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': passo[1]}).status_code == 200
        continue
    nome, metodo, rota, corpo = passo
    corpo = preencher(corpo)
    chamada = getattr(c, metodo)
    r = chamada(preencher(rota), json=corpo) if corpo is not None else chamada(preencher(rota))
    j = r.get_json()
    saida.append([nome, r.status_code, j])
    dados = (j or {}).get('data') if isinstance(j, dict) else None
    if nome and isinstance(dados, dict) and 'id' in dados:
        ids[nome] = dados['id']
print('FLASK_JSON ' + json.dumps(saida))
"""


def flask(dsn, passos):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT, json.dumps(passos)], cwd=ROOT, env=env, capture_output=True,
                       text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return {nome: (status, corpo) for nome, status, corpo in json.loads(linha[len('FLASK_JSON '):]) if nome}


def conta_bancaria(dsn, nome='Conta Pessoal (A)'):
    return sql(dsn, 'select id from public.conta_bancaria where nome = %s', (nome,))[0]['id']


def leituras(perfil):
    return [('perfil', perfil),
            (f'itens-{perfil}', 'get', '/api/receitas/itens', None),
            (f'orc-{perfil}', 'get', f'/api/receitas/orcamento?ano={ANO}', None),
            (f'orc2-{perfil}', 'get', f'/api/receitas/orcamento?ano={ANO + 1}', None),
            (f'real-{perfil}', 'get', f'/api/receitas/realizadas?ano_mes_inicio={ANO}-01-01&ano_mes_fim={MES}', None),
            (f'realtudo-{perfil}', 'get', '/api/receitas/realizadas', None),
            (f'cat-{perfil}', 'get', '/api/categorias', None),
            (f'catc-{perfil}', 'get', '/api/categorias-cartao', None)]


@pytest.fixture(scope='module')
def cenario(cluster):  # noqa: F811
    dsn = copiar(cluster)
    banco = conta_bancaria(dsn)
    categoria = sql(dsn, 'select id from public.categoria order by id limit 1')[0]['id']
    passos = [
        ('perfil', PESSOAL),
        ('fonte_rec', 'post', '/api/receitas/itens', {'nome': 'Salario RC (ficticio)', 'tipo': 'SALARIO_FIXO',
                                                    'descricao': 'Mensal', 'valor_base_mensal': 10000,
                                                    'dia_previsto_pagamento': 5, 'conta_bancaria_id': banco,
                                                    'recorrente': True, 'ativo': True}),
        ('fonte_avulsa', 'post', '/api/receitas/itens', {'nome': 'Freela RC (ficticio)', 'tipo': 'RENDA_EXTRA',
                                                       'valor_base_mensal': 800, 'recorrente': False, 'ativo': True}),
        ('receb', 'post', '/api/receitas/realizadas', {'item_receita_id': '{fonte_rec}', 'data_recebimento': HOJE.isoformat(),
                                                    'valor_recebido': 9500, 'competencia': MES,
                                                    'conta_bancaria_id': banco, 'descricao': 'Salario RC (ficticio)'}),
        ('pontual', 'post', '/api/receitas/realizadas/pontual', {'conta_bancaria_id': banco, 'descricao': 'PIX RC (ficticio)',
                                                              'valor_recebido': 300, 'data_recebimento': HOJE.isoformat(),
                                                              'competencia': MES}),
        ('estorno', 'post', '/api/receitas/realizadas/{pontual}/estornar', {'motivo': 'Credito devolvido', 'data_estorno': HOJE.isoformat()}),
        ('cc', 'post', '/api/categorias-cartao', {'nome': 'Mercado RC (ficticio)', 'cor': '#16a34a', 'descricao': 'Supermercado'}),
        ('vinc', 'post', '/api/categorias-cartao/{cc}/despesas', {'categoria_id': categoria}),
        ('palavra', 'post', f'/api/categorias/{categoria}/palavras-chave', {'palavra': 'supermercado rc'}),
    ]
    for perfil in (PESSOAL, EMPRESA, PERFIL_B):
        passos += leituras(perfil)
    passos += [('perfil', PESSOAL), ('despesas-cc', 'get', '/api/categorias-cartao/{cc}/despesas?ativo=true', None),
               ('palavras', 'get', f'/api/categorias/{categoria}/palavras-chave', None)]
    saida = flask(dsn, passos)
    for nome in ('fonte_rec', 'fonte_avulsa', 'receb', 'pontual', 'estorno', 'cc', 'vinc', 'palavra'):
        assert saida[nome][0] in (200, 201), (nome, saida[nome])
    return dsn, saida, categoria


def chamar(dsn, perfil, funcao, *args):
    return rpc(dsn, funcao, perfil, *args, **({'usuario': USUARIO_B} if perfil == PERFIL_B else {}))


def test_privilegios(cenario):
    dsn = cenario[0]
    for funcao, esperado in (
            ('financeiro.receitas_fontes_tela(integer)', (True, False)),
            ('financeiro.receitas_orcamentos_tela(integer, integer)', (True, False)),
            ('financeiro.receitas_realizadas_tela(integer, text, text)', (True, False)),
            ('financeiro.categorias_tela(integer, boolean)', (True, False)),
            ('financeiro.palavras_chave_tela(integer)', (True, False)),
            ('financeiro.categorias_cartao_tela(integer, boolean)', (True, False)),
            ('financeiro.categoria_cartao_despesas_tela(integer, boolean)', (True, False)),
            ('financeiro.criar_categoria_cartao(integer, jsonb)', (True, False)),
            ('financeiro.editar_categoria_cartao(integer, integer, jsonb)', (True, False)),
            ('financeiro.desativar_categoria_cartao(integer, integer)', (True, False)),
            ('financeiro.vincular_despesa_categoria_cartao(integer, integer, integer, boolean)', (True, False)),
            ('financeiro.desvincular_despesa_categoria_cartao(integer, integer, integer)', (True, False)),
            ('financeiro.item_receita_flask(public.item_receita)', (False, False)),
            ('financeiro.exigir_escrita_categoria_cartao(integer)', (False, False)),
            ('financeiro.ler_dados_categoria_cartao(integer, jsonb, boolean, integer)', (False, False))):
        r = sql(dsn, "select has_function_privilege('authenticated', %s, 'execute') a, "
                     "has_function_privilege('anon', %s, 'execute') n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == esperado, funcao


@pytest.mark.parametrize('perfil', [PESSOAL, EMPRESA, PERFIL_B])
def test_receitas_iguais_ao_flask(cenario, perfil):
    dsn, saida, _ = cenario
    for chave, funcao, args in ((f'itens-{perfil}', 'receitas_fontes_tela', ()),
                                (f'orc-{perfil}', 'receitas_orcamentos_tela', (ANO,)),
                                (f'orc2-{perfil}', 'receitas_orcamentos_tela', (ANO + 1,)),
                                (f'real-{perfil}', 'receitas_realizadas_tela', (f'{ANO}-01-01', MES)),
                                (f'realtudo-{perfil}', 'receitas_realizadas_tela', (None, None))):
        status, corpo = saida[chave]
        assert status == 200 and corpo['success'], (chave, corpo)
        novo = chamar(dsn, perfil, funcao, *args)
        igual(corpo['data'], novo, chave)  # mesma ordem do Flask, campo a campo
    if perfil == PESSOAL:
        fontes = {f['nome']: f for f in chamar(dsn, perfil, 'receitas_fontes_tela')}
        assert fontes['Salario RC (ficticio)']['versao'] and fontes['Salario RC (ficticio)']['de_outro_modulo'] is False
        orc = [o for o in chamar(dsn, perfil, 'receitas_orcamentos_tela', ANO) + chamar(dsn, perfil, 'receitas_orcamentos_tela', ANO + 1)
               if o['item_receita_id'] == fontes['Salario RC (ficticio)']['id']]
        assert len(orc) == 12 and all(o['versao'] for o in orc)  # as 12 previsoes que o Flask gerou
        real = {r['descricao']: r for r in chamar(dsn, perfil, 'receitas_realizadas_tela', None, None)}
        assert real['PIX RC (ficticio)']['estornada'] is True and real['Salario RC (ficticio)']['estornada'] is False


@pytest.mark.parametrize('perfil', [PESSOAL, EMPRESA, PERFIL_B])
def test_categorias_iguais_ao_flask(cenario, perfil):
    dsn, saida, categoria = cenario
    status, corpo = saida[f'cat-{perfil}']
    assert status == 200
    novo = {c['id']: c for c in chamar(dsn, perfil, 'categorias_tela', None)}
    flask_cat = sorted(corpo['data'], key=lambda c: c['id'])  # o Flask nao ordena
    assert [c['id'] for c in flask_cat] == sorted(novo)
    for c in flask_cat:
        igual(c, novo[c['id']], f'categoria {c["id"]}')
    status, corpo = saida[f'catc-{perfil}']
    igual(corpo['data'], chamar(dsn, perfil, 'categorias_cartao_tela', None), f'categorias-cartao {perfil}')
    if perfil == PESSOAL:
        cc = saida['cc'][1]['data']['id']
        igual(saida['despesas-cc'][1]['data'], chamar(dsn, perfil, 'categoria_cartao_despesas_tela', True)[str(cc)], 'vinculos')
        igual(saida['palavras'][1]['data'], chamar(dsn, perfil, 'palavras_chave_tela')[str(categoria)], 'palavras-chave')
        assert next(c for c in novo.values() if c['id'] == categoria)['palavras_chave_count'] >= 1


def test_isolamento(cenario):
    dsn = cenario[0]
    for funcao, args in (('receitas_fontes_tela', ()), ('receitas_orcamentos_tela', (ANO,)),
                         ('receitas_realizadas_tela', (None, None)), ('categorias_cartao_tela', (None,)),
                         ('categoria_cartao_despesas_tela', (None,)), ('categorias_tela', (None,))):
        with pytest.raises(psycopg2.Error) as erro:
            rpc(dsn, funcao, PESSOAL, *args, usuario=USUARIO_B)
        assert erro.value.pgcode == '42501', funcao
    nomes_b = {c['nome'] for c in chamar(dsn, PERFIL_B, 'categorias_cartao_tela', None)}
    assert 'Mercado RC (ficticio)' not in nomes_b
    assert all(f['perfil_financeiro_id'] == PERFIL_B for f in chamar(dsn, PERFIL_B, 'receitas_fontes_tela'))


# --- Escrita de Categorias do Cartao ------------------------------------------------------------------------------

SEQUENCIA = [  # mesma sequencia nos dois sistemas
    ('criar', {'nome': 'Farmacia RC (ficticio)', 'cor': '#0ea5e9', 'descricao': ' Remedios ', 'icone': 'pill'}),
    ('editar', {'nome': 'Farmacia e Saude RC (ficticio)', 'descricao': '', 'icone': None}),
    ('vincular', None),
    ('desvincular', None),
    ('vincular', None),
    ('desativar', None),
]
CAMPOS = ('nome', 'descricao', 'cor', 'icone', 'ativo', 'perfil_financeiro_id')


def _estado_categoria(dsn, nome_like):
    cc = sql(dsn, 'select * from public.categoria_cartao where nome like %s', (nome_like,))
    vinculos = sql(dsn, 'select v.categoria_id, v.ativo, v.perfil_financeiro_id from public.categoria_cartao_despesa v '
                        'join public.categoria_cartao cc on cc.id = v.categoria_cartao_id where cc.nome like %s', (nome_like,))
    return [{k: c[k] for k in CAMPOS} for c in cc], vinculos


@pytest.fixture
def categoria_livre(cluster):  # noqa: F811
    """Categoria de despesa sem vinculo ativo no Pessoal (a mesma nos dois bancos)."""
    def escolher(dsn):
        return sql(dsn, 'select c.id from public.categoria c where not exists (select 1 from public.categoria_cartao_despesa v '
                        'where v.categoria_id = c.id and v.ativo) order by c.id limit 1')[0]['id']
    return escolher


def test_escrita_categoria_cartao_igual_ao_flask(cluster, categoria_livre):  # noqa: F811
    antigo, novo = copiar(cluster), copiar(cluster)
    categoria = categoria_livre(antigo)
    assert categoria == categoria_livre(novo)
    passos = [('perfil', PESSOAL)]
    for i, (acao, dados) in enumerate(SEQUENCIA):
        if acao == 'criar':
            passos.append(('cc', 'post', '/api/categorias-cartao', dados))
        elif acao == 'editar':
            passos.append((f'p{i}', 'put', '/api/categorias-cartao/{cc}', dados))
        elif acao == 'vincular':
            passos.append((f'p{i}', 'post', '/api/categorias-cartao/{cc}/despesas', {'categoria_id': categoria}))
        elif acao == 'desvincular':
            passos.append((f'p{i}', 'delete', f'/api/categorias-cartao/{{cc}}/despesas/{categoria}', None))
        else:
            passos.append((f'p{i}', 'delete', '/api/categorias-cartao/{cc}', None))
    r = flask(antigo, passos)
    assert all(s in (200, 201) for s, _ in r.values()), r

    atribuir(novo, 'PESSOAL')
    cc = None
    for acao, dados in SEQUENCIA:
        if acao == 'criar':
            cc = rpc(novo, 'criar_categoria_cartao', PESSOAL, dados)['id']
        elif acao == 'editar':
            rpc(novo, 'editar_categoria_cartao', PESSOAL, cc, dados)
        elif acao == 'vincular':
            rpc(novo, 'vincular_despesa_categoria_cartao', PESSOAL, cc, categoria, True)
        elif acao == 'desvincular':
            rpc(novo, 'desvincular_despesa_categoria_cartao', PESSOAL, cc, categoria)
        else:
            rpc(novo, 'desativar_categoria_cartao', PESSOAL, cc)
    assert _estado_categoria(novo, 'Farmacia%RC%') == _estado_categoria(antigo, 'Farmacia%RC%')
    assert _estado_categoria(novo, 'Farmacia%RC%')[0][0]['nome'] == 'Farmacia e Saude RC (ficticio)'


def test_recusas_de_categoria_cartao_como_o_flask(cluster, categoria_livre):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    existente = sql(dsn, 'select nome from public.categoria_cartao where perfil_financeiro_id = %s order by id limit 1',
                    (PESSOAL,))[0]['nome']

    def falha(funcao, *args, usuario=None):
        with pytest.raises(psycopg2.Error) as erro:
            rpc(dsn, funcao, *args, **({'usuario': usuario} if usuario else {}))
        return erro.value.pgcode, erro.value.diag.message_primary

    assert falha('criar_categoria_cartao', PESSOAL, {'nome': '  '})[1] == 'Nome e obrigatorio'
    assert falha('criar_categoria_cartao', PESSOAL, {'nome': existente.upper()})[1] == 'Ja existe uma Categoria do Cartao com este nome'
    assert falha('criar_categoria_cartao', PESSOAL, {'nome': 'Cor ruim', 'cor': 'red;x'})[1] == 'Cor invalida (use #RRGGBB)'
    a = rpc(dsn, 'criar_categoria_cartao', PESSOAL, {'nome': 'A RC (ficticio)'})['id']
    b = rpc(dsn, 'criar_categoria_cartao', PESSOAL, {'nome': 'B RC (ficticio)'})['id']
    categoria = categoria_livre(dsn)
    rpc(dsn, 'vincular_despesa_categoria_cartao', PESSOAL, a, categoria, True)
    assert falha('vincular_despesa_categoria_cartao', PESSOAL, b, categoria, True)[1] == \
        'Categoria de despesa ja vinculada a outra Categoria do Cartao ativa'
    assert falha('vincular_despesa_categoria_cartao', PESSOAL, b, 999999, True)[1] == 'Categoria de despesa nao encontrada'
    assert falha('desvincular_despesa_categoria_cartao', PESSOAL, b, categoria)[1] == 'Vinculo nao encontrado'
    assert falha('editar_categoria_cartao', PESSOAL, b, {'nome': 'a rc (ficticio)'})[1] == 'Ja existe uma Categoria do Cartao com este nome'
    # Outro perfil (B nao gere o Pessoal) e categoria de outro perfil.
    assert falha('criar_categoria_cartao', PESSOAL, {'nome': 'Invasao'}, usuario=USUARIO_B)[0] == '42501'
    atribuir(dsn, 'PERFIL_B')
    assert falha('editar_categoria_cartao', PERFIL_B, a, {'nome': 'Tomada'}, usuario=USUARIO_B)[1] == 'Categoria do Cartao nao encontrada'
    # Quem so le (A e LEITOR da Empresa).
    assert falha('criar_categoria_cartao', EMPRESA, {'nome': 'Leitor RC'})[0] == '42501'


def test_escritor_unico_categoria_cartao(cluster):  # noqa: F811
    """Perfil ainda no Flask: nenhuma escrita de Categoria do Cartao pelo novo aplicativo, nada muda."""
    dsn = copiar(cluster)
    cc = sql(dsn, 'select id from public.categoria_cartao where perfil_financeiro_id = %s order by id limit 1', (PESSOAL,))[0]['id']
    categoria = sql(dsn, 'select id from public.categoria order by id desc limit 1')[0]['id']
    antes = (sql(dsn, 'select * from public.categoria_cartao order by id'), sql(dsn, 'select * from public.categoria_cartao_despesa order by id'))
    for funcao, args in (('criar_categoria_cartao', ({'nome': 'Nao grava'},)), ('editar_categoria_cartao', (cc, {'nome': 'X'})),
                         ('desativar_categoria_cartao', (cc,)), ('vincular_despesa_categoria_cartao', (cc, categoria, True)),
                         ('desvincular_despesa_categoria_cartao', (cc, categoria))):
        with pytest.raises(psycopg2.Error) as erro:
            rpc(dsn, funcao, PESSOAL, *args)
        assert erro.value.diag.message_hint == 'SISTEMA_FLASK', funcao
    assert (sql(dsn, 'select * from public.categoria_cartao order by id'),
            sql(dsn, 'select * from public.categoria_cartao_despesa order by id')) == antes


def test_vinculo_nao_reclassifica_compras(cluster, categoria_livre):  # noqa: F811
    """Vincular, desvincular e desativar nao mudam a Categoria do Cartao de compras ja lancadas."""
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    antes = sql(dsn, 'select id, categoria_cartao_id, categoria_id from public.lancamento_agregado order by id')
    cc = rpc(dsn, 'criar_categoria_cartao', PESSOAL, {'nome': 'Nova RC (ficticio)'})['id']
    existente = sql(dsn, 'select categoria_cartao_id from public.lancamento_agregado where categoria_cartao_id is not null '
                         'order by id limit 1')
    categoria = categoria_livre(dsn)
    rpc(dsn, 'vincular_despesa_categoria_cartao', PESSOAL, cc, categoria, True)
    rpc(dsn, 'desvincular_despesa_categoria_cartao', PESSOAL, cc, categoria)
    if existente:
        try:
            rpc(dsn, 'desativar_categoria_cartao', PESSOAL, existente[0]['categoria_cartao_id'])
        except psycopg2.Error:
            pass  # categoria de outro perfil: recusada (isolamento)
    assert sql(dsn, 'select id, categoria_cartao_id, categoria_id from public.lancamento_agregado order by id') == antes
