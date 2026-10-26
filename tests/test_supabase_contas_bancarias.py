"""
Testes FIN-FIDELIDADE-MOVIMENTACOES-1 — tela original de Contas Bancarias (migration 20261109090000).

Cenario FICTICIO do FIN-RECORRENCIA-1 (tests/supabase_local.py), copia por teste: Pessoal (101, usuario A titular, com a
conta "Conta Pessoal (A)" e a legada sem perfil), Empresa (102, A so leitor), Perfil B (103, usuario B). Chamadas como
o navegador (authenticated). Regras do Flask: saldo pelos movimentos, saldo inicial so sem movimentos, so AJUSTE
editavel, transferencia = debito + credito com o mesmo transferencia_id, conferencia so leitura.
"""
import json
import os
import subprocess
import sys
import uuid
from decimal import Decimal

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_fatura_unica import em_thread
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    ROOT,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, EMPRESA, PERFIL_B = ID['PESSOAL'], ID['EMPRESA'], ID['PERFIL_B']
DA_TELA = [
    'financeiro.contas_bancarias_tela(integer, text)', 'financeiro.conta_bancaria_tela(integer, integer)',
    'financeiro.extrato_conta_bancaria(integer, integer, date, date, integer, boolean)',
    'financeiro.conferir_saldo_conta(integer, integer)', 'financeiro.criar_conta_bancaria(integer, jsonb, uuid)',
    'financeiro.editar_conta_bancaria(integer, integer, text, jsonb)',
    'financeiro.ajustar_saldo_conta(integer, integer, jsonb, uuid)',
    'financeiro.editar_ajuste_conta(integer, integer, integer, jsonb)',
    'financeiro.excluir_ajuste_conta(integer, integer, integer)', 'financeiro.transferir_entre_contas(integer, jsonb, uuid)',
]
INTERNAS = [
    'financeiro.conta_bancaria_flask(public.conta_bancaria)', 'financeiro.versao_conta_bancaria(public.conta_bancaria)',
    'financeiro.movimento_flask(public.movimento_financeiro)', 'financeiro.travar_conta_do_perfil(integer, integer)',
    'financeiro.ler_dados_conta_bancaria(jsonb, boolean)', 'financeiro.ler_valor_movimento(text, text)',
    'financeiro.ler_data_movimento(text)', 'financeiro.operacao_repetida(integer, uuid, text)',
    'financeiro.travar_ajuste(integer, integer, integer)',
]
NOVA = {'nome': 'Reserva (teste)', 'instituicao': 'Banco ficticio', 'tipo': 'Poupança', 'agencia': '0001',
        'numero_conta': '12345', 'digito_conta': '6', 'saldo_inicial': 1000, 'cor_display': '#10b981'}


@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    return dsn


def falha(dsn, funcao, *args, usuario=USUARIO_A):
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, funcao, *args, usuario=usuario)
    return erro.value.pgcode, erro.value.diag.message_primary


def conta_id(dsn, nome):
    return sql(dsn, 'select id from public.conta_bancaria where nome = %s', (nome,))[0]['id']


def criar(dsn, perfil=PESSOAL, usuario=USUARIO_A, chave=None, **campos):
    return rpc(dsn, 'criar_conta_bancaria', perfil, {**NOVA, **campos}, chave or str(uuid.uuid4()), usuario=usuario)


def saldo(dsn, conta):
    r = sql(dsn, 'select saldo_atual, financeiro.saldo_da_conta(id) as calc from public.conta_bancaria where id = %s', (conta,))[0]
    assert r['saldo_atual'] == r['calc']  # cache sempre igual ao saldo pelos movimentos
    return r['saldo_atual']


def movimentos(dsn, conta):
    return sql(dsn, 'select * from public.movimento_financeiro where conta_bancaria_id = %s order by id', (conta,))


def transferir(dsn, origem, destino, valor='250.00', chave=None, perfil=PESSOAL, usuario=USUARIO_A, **extra):
    return rpc(dsn, 'transferir_entre_contas', perfil,
               {'conta_origem_id': origem, 'conta_destino_id': destino, 'valor': valor, 'data_movimento': '2027-05-10',
                'descricao': 'Transferência entre contas', **extra}, chave or str(uuid.uuid4()), usuario=usuario)


def ajustar(dsn, conta, chave=None, perfil=PESSOAL, usuario=USUARIO_A, **dados):
    return rpc(dsn, 'ajustar_saldo_conta', perfil, conta, {'data_movimento': '2027-05-12', **dados},
               chave or str(uuid.uuid4()), usuario=usuario)


# --- Privilegios --------------------------------------------------------------------------------------------------

def test_privilegios_tela_so_authenticated_e_internas_fechadas(banco):
    for funcao in DA_TELA:
        r = sql(banco, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                       "has_function_privilege('anon', %s, 'execute') as n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == (True, False), funcao
    for funcao in INTERNAS:
        r = sql(banco, "select has_function_privilege('authenticated', %s, 'execute') as a, "
                       "has_function_privilege('anon', %s, 'execute') as n", (funcao, funcao))[0]
        assert (r['a'], r['n']) == (False, False), funcao
    definicoes = sql(banco, """select p.proname, p.prosecdef, p.proconfig from pg_proc p
                                join pg_namespace n on n.oid = p.pronamespace
                               where n.nspname = 'financeiro' and p.proname = any(%s)""",
                     ([f.split('.')[1].split('(')[0] for f in DA_TELA],))
    assert len(definicoes) == len(DA_TELA)
    assert all(d['prosecdef'] and d['proconfig'] == ['search_path=""'] for d in definicoes)


# --- Leitura ------------------------------------------------------------------------------------------------------

def test_lista_ativas_por_padrao_no_formato_do_flask_com_a_legada_do_pessoal(banco):
    contas = rpc(banco, 'contas_bancarias_tela', PESSOAL, None)
    assert [c['nome'] for c in contas] == ['Carteira legado sem perfil', 'Conta Pessoal (A)']
    assert set(contas[0]) >= {'id', 'perfil_financeiro_id', 'nome', 'instituicao', 'tipo', 'agencia', 'numero_conta',
                              'digito_conta', 'saldo_inicial', 'saldo_atual', 'cor_display', 'icone', 'data_criacao',
                              'data_atualizacao', 'status', 'versao'}
    assert rpc(banco, 'contas_bancarias_tela', PESSOAL, 'INATIVO') == []
    assert falha(banco, 'contas_bancarias_tela', PESSOAL, 'TODAS')[1] == 'status deve ser ATIVO ou INATIVO'
    # Outro titular nao ve nem le conta alheia.
    assert falha(banco, 'contas_bancarias_tela', PESSOAL, None, usuario=USUARIO_B)[0] == '42501'
    assert 'nao encontrada' in falha(banco, 'conta_bancaria_tela', PERFIL_B, conta_id(banco, 'Conta Pessoal (A)'),
                                     usuario=USUARIO_B)[1]
    # Leitor ve as contas do perfil.
    assert [c['nome'] for c in rpc(banco, 'contas_bancarias_tela', EMPRESA, 'ATIVO')] == ['Conta Empresa (A)']


# --- Cadastro -----------------------------------------------------------------------------------------------------

def test_criar_conta_idempotente_validada_e_so_por_quem_gere(banco):
    chave = str(uuid.uuid4())
    nova = criar(banco, chave=chave)
    assert (nova['nome'], nova['status'], nova['saldo_inicial'], nova['saldo_atual']) == ('Reserva (teste)', 'ATIVO', 1000, 1000)
    assert nova['perfil_financeiro_id'] == PESSOAL
    assert criar(banco, chave=chave)['repetida'] is True                         # reenvio nao duplica
    assert len(sql(banco, "select id from public.conta_bancaria where nome = 'Reserva (teste)'")) == 1
    assert falha(banco, 'criar_conta_bancaria', PESSOAL, {**NOVA, 'nome': ' '}, str(uuid.uuid4()))[1] == 'Nome e obrigatorio'
    assert falha(banco, 'criar_conta_bancaria', PESSOAL, {**NOVA, 'instituicao': ''}, str(uuid.uuid4()))[1] == \
        'Instituicao e obrigatoria'
    assert falha(banco, 'criar_conta_bancaria', PESSOAL, {**NOVA, 'saldo_inicial': '1.001'}, str(uuid.uuid4()))[1] == \
        'saldo_inicial invalido'
    assert falha(banco, 'criar_conta_bancaria', PESSOAL, {**NOVA, 'cor_display': 'red'}, str(uuid.uuid4()))[1].startswith('Cor')
    assert falha(banco, 'criar_conta_bancaria', EMPRESA, NOVA, str(uuid.uuid4()))[0] == '42501'  # leitor
    assert falha(banco, 'criar_conta_bancaria', PESSOAL, NOVA, str(uuid.uuid4()), usuario=USUARIO_B)[0] == '42501'
    assert falha(banco, 'criar_conta_bancaria', PESSOAL, NOVA, chave, usuario=USUARIO_B)[0] == '42501'


def test_editar_so_os_campos_enviados_com_versao(banco):
    nova = criar(banco)
    editada = rpc(banco, 'editar_conta_bancaria', PESSOAL, nova['id'], nova['versao'], {'nome': 'Reserva 2', 'agencia': ''})
    assert (editada['nome'], editada['agencia'], editada['numero_conta'], editada['tipo']) == ('Reserva 2', None, '12345', 'Poupança')
    # Versao antiga: cadastro alterado por outra operacao, nada gravado.
    codigo, msg = falha(banco, 'editar_conta_bancaria', PESSOAL, nova['id'], nova['versao'], {'nome': 'Outra'})
    assert (codigo, msg) == ('40001', 'Conta bancaria alterada por outra operacao')
    assert rpc(banco, 'conta_bancaria_tela', PESSOAL, nova['id'])['nome'] == 'Reserva 2'
    # Movimento (saldo_atual) nao muda a versao do cadastro.
    ajustar(banco, nova['id'], valor_final_desejado='1100.00')
    assert rpc(banco, 'conta_bancaria_tela', PESSOAL, nova['id'])['versao'] == editada['versao']
    assert falha(banco, 'editar_conta_bancaria', PESSOAL, nova['id'], None, {'status': 'X'})[1] == \
        'status deve ser ATIVO ou INATIVO'
    assert falha(banco, 'editar_conta_bancaria', EMPRESA, conta_id(banco, 'Conta Empresa (A)'), None, {'nome': 'x'})[0] == '42501'
    assert 'nao encontrada' in falha(banco, 'editar_conta_bancaria', PERFIL_B, nova['id'], None, {'nome': 'x'},
                                     usuario=USUARIO_B)[1]


def test_saldo_inicial_so_sem_movimentos(banco):
    nova = criar(banco)
    r = rpc(banco, 'editar_conta_bancaria', PESSOAL, nova['id'], None, {'saldo_inicial': '1500.50'})
    assert (r['saldo_inicial'], r['saldo_atual']) == (1500.5, 1500.5)
    ajustar(banco, nova['id'], valor_do_ajuste='-0.50')
    codigo, msg = falha(banco, 'editar_conta_bancaria', PESSOAL, nova['id'], None, {'saldo_inicial': '2000'})
    assert msg.startswith('Nao e permitido alterar saldo inicial apos existirem movimentos')
    # O mesmo valor (o formulario do Flask sempre o envia) continua aceito.
    assert rpc(banco, 'editar_conta_bancaria', PESSOAL, nova['id'], None, {'saldo_inicial': '1500.50', 'nome': 'X'})['nome'] == 'X'
    assert saldo(banco, nova['id']) == Decimal('1500.00')


def test_inativar_e_reativar_preservam_saldo_e_historico(banco):
    nova = criar(banco)
    ajustar(banco, nova['id'], valor_final_desejado='900.00')
    antes = movimentos(banco, nova['id'])
    assert rpc(banco, 'editar_conta_bancaria', PESSOAL, nova['id'], None, {'status': 'INATIVO'})['status'] == 'INATIVO'
    assert [c['id'] for c in rpc(banco, 'contas_bancarias_tela', PESSOAL, 'INATIVO')] == [nova['id']]
    assert rpc(banco, 'editar_conta_bancaria', PESSOAL, nova['id'], None, {'status': 'ativo'})['status'] == 'ATIVO'
    assert movimentos(banco, nova['id']) == antes and saldo(banco, nova['id']) == Decimal('900.00')


# --- Ajuste de saldo ----------------------------------------------------------------------------------------------

def test_ajuste_pela_diferenca_e_pelo_valor_idempotente(banco):
    nova = criar(banco)
    chave = str(uuid.uuid4())
    r = ajustar(banco, nova['id'], chave=chave, valor_final_desejado='1234.56', descricao='Conferido com extrato')
    assert (r['movimento']['tipo'], r['movimento']['valor'], r['movimento']['origem'], r['movimento']['ajustavel']) == \
        ('CREDITO', 234.56, 'AJUSTE', True)
    assert r['conta']['saldo_atual'] == 1234.56
    assert ajustar(banco, nova['id'], chave=chave, valor_final_desejado='1234.56')['repetida'] is True
    assert len(movimentos(banco, nova['id'])) == 1
    r = ajustar(banco, nova['id'], valor_do_ajuste='-34.56')
    assert (r['movimento']['tipo'], r['movimento']['valor'], r['movimento']['descricao']) == ('DEBITO', 34.56, 'Ajuste manual de saldo')
    assert saldo(banco, nova['id']) == Decimal('1200.00')
    # Ja no valor desejado: nada gravado.
    assert ajustar(banco, nova['id'], valor_final_desejado='1200')['sem_alteracao'] is True
    assert len(movimentos(banco, nova['id'])) == 2
    assert falha(banco, 'ajustar_saldo_conta', PESSOAL, nova['id'], {}, str(uuid.uuid4()))[1] == \
        'Informe valor_final_desejado ou valor_do_ajuste'
    assert falha(banco, 'ajustar_saldo_conta', PESSOAL, nova['id'], {'valor_do_ajuste': '1,5'}, str(uuid.uuid4()))[1] == \
        'valor_do_ajuste invalido'
    assert falha(banco, 'ajustar_saldo_conta', PESSOAL, nova['id'], {'valor_do_ajuste': 1, 'data_movimento': '2027-13-01'},
                 str(uuid.uuid4()))[1].startswith('Formato de data invalido')


def test_cadastro_e_movimento_so_pelo_escritor_unico_do_perfil(cluster):  # noqa: F811
    """FIN-ESCRITOR-UNICO-CONTAS-1: perfil ainda no Flask = o novo aplicativo nao grava nada, nem cadastro."""
    dsn = copiar(cluster)  # Pessoal ainda no Flask
    conta = conta_id(dsn, 'Conta Pessoal (A)')
    legada = sql(dsn, "select id from public.conta_bancaria where perfil_financeiro_id is null")[0]['id']
    antes = estado_das_contas(dsn)
    flask = ('P0001', 'Os pagamentos deste perfil ainda sao feitos pelo sistema atual (Flask)')
    assert falha(dsn, 'ajustar_saldo_conta', PESSOAL, conta, {'valor_do_ajuste': 10}, str(uuid.uuid4())) == flask
    assert falha(dsn, 'criar_conta_bancaria', PESSOAL, NOVA, str(uuid.uuid4())) == flask
    for dados in ({'nome': 'Outro nome'}, {'status': 'INATIVO'}):
        assert falha(dsn, 'editar_conta_bancaria', PESSOAL, conta, None, dados) == flask
    assert falha(dsn, 'transferir_entre_contas', PESSOAL, {'conta_origem_id': conta, 'conta_destino_id': legada,
                                                          'valor': 1}, str(uuid.uuid4()))[0] == 'P0001'
    assert estado_das_contas(dsn) == antes


def estado_das_contas(dsn):
    return (sql(dsn, 'select * from public.conta_bancaria order by id'),
            sql(dsn, 'select * from public.movimento_financeiro order by id'))


# FIN-ESCRITOR-UNICO-CONTAS-1: o lado do Flask. O proprio Flask (processo real, cluster descartavel) tenta as 8 escritas
# de Contas Bancarias; ids entre chaves vem do cenario ou da resposta anterior (perfil no Flask: ele mesmo cria).
_ESCRITAS = [
    ('post', '/api/contas', {'nome': 'Conta Flask (teste)', 'instituicao': 'Banco ficticio', 'tipo': 'Corrente',
                             'saldo_inicial': 500}),
    ('put', '/api/contas/{c}', {'nome': 'Conta Flask (editada)'}),
    ('post', '/api/contas/{c}/ajuste-saldo', {'valor_do_ajuste': 30, 'data_movimento': '2027-05-12'}),
    ('put', '/api/contas/{c}/movimentos/{m}', {'valor': 20}),
    ('delete', '/api/contas/{c}/movimentos/{m}', None),
    ('post', '/api/contas/transferir', {'conta_origem_id': '{c}', 'conta_destino_id': '{d}', 'valor': 15,
                                        'data_movimento': '2027-05-13'}),
    ('delete', '/api/contas/{c}', None),
    ('put', '/api/contas/{c}/ativar', None),
]
_SCRIPT_FLASK = """
import json, sys
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    u = Usuario(email='flask.contas@teste.local', nome='Contas', ativo=True)
    u.definir_senha('Senha-ficticia-contas-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.contas@teste.local', 'senha': 'Senha-ficticia-contas-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
ids = json.loads(sys.argv[3])
def preencher(v):
    if isinstance(v, str) and v.startswith('{') and v.endswith('}') and v[1:-1] in ids:
        return ids[v[1:-1]]
    if isinstance(v, dict):
        return {k: preencher(x) for k, x in v.items()}
    return v
saida = []
for metodo, rota, corpo in json.loads(sys.argv[2]):
    chamada = getattr(c, metodo)
    r = chamada(rota.format(**ids), json=preencher(corpo)) if corpo is not None else chamada(rota.format(**ids))
    j = r.get_json() or {}
    saida.append([metodo, rota, r.status_code, j.get('codigo'), j.get('error')])
    dados = j.get('data') or {}
    if rota == '/api/contas' and r.status_code == 201:
        ids['c'] = dados['id']
    if rota.endswith('/ajuste-saldo') and r.status_code == 201:
        ids['m'] = dados['movimento']['id']
conta = '/api/contas/' + str(ids['c'])
leituras = [c.get('/api/contas').status_code, c.get(conta).status_code, c.get(conta + '/conferir-saldo').status_code]
print('FLASK_JSON ' + json.dumps({'escritas': saida, 'leituras': leituras}))
"""


def flask_escreve(dsn, ids):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT_FLASK, str(PESSOAL), json.dumps(_ESCRITAS), json.dumps(ids)],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


def test_flask_recusa_as_8_escritas_de_contas_em_perfil_do_novo_aplicativo(banco):
    """Perfil NOVO: cada escrita do Flask responde 409 SISTEMA_NOVO e nada muda (contas, movimentos, saldos).
    Consultas continuam."""
    c = criar(banco)['id']  # pelo escritor do perfil (novo aplicativo)
    m = ajustar(banco, c, valor_do_ajuste=30)['movimento']['id']
    d = conta_id(banco, 'Conta Pessoal (A)')
    antes = estado_das_contas(banco)
    r = flask_escreve(banco, {'c': c, 'm': m, 'd': d})
    assert [(e[2], e[3]) for e in r['escritas']] == [(409, 'SISTEMA_NOVO')] * len(_ESCRITAS), r['escritas']
    assert all('Nada foi gravado' in e[4] for e in r['escritas'])
    assert r['leituras'] == [200, 200, 200]
    assert estado_das_contas(banco) == antes


def test_flask_continua_gravando_contas_em_perfil_do_flask(cluster):  # noqa: F811
    """Perfil sem atribuicao (Flask): comportamento legado, as 8 escritas gravam; o novo aplicativo recusa."""
    dsn = copiar(cluster)
    d = conta_id(dsn, 'Conta Pessoal (A)')
    r = flask_escreve(dsn, {'d': d})
    assert [e[2] for e in r['escritas']] == [201, 200, 201, 200, 200, 201, 200, 200], r['escritas']
    nova = conta_id(dsn, 'Conta Flask (editada)')
    assert sql(dsn, 'select status from public.conta_bancaria where id = %s', (nova,))[0]['status'] == 'ATIVO'
    assert [(x['tipo'], x['valor'], x['origem']) for x in movimentos(dsn, nova)] == [
        ('DEBITO', Decimal('15.00'), 'TRANSFERENCIA')]
    assert falha(dsn, 'editar_conta_bancaria', PESSOAL, nova, None, {'nome': 'X'})[0] == 'P0001'


def test_editar_e_excluir_so_ajuste(banco):
    nova = criar(banco)
    mov = ajustar(banco, nova['id'], valor_do_ajuste='50')['movimento']
    r = rpc(banco, 'editar_ajuste_conta', PESSOAL, nova['id'], mov['id'],
            {'tipo': 'DEBITO', 'valor': '20.00', 'descricao': 'Tarifa', 'data_movimento': '2027-05-01'})
    assert (r['tipo'], r['valor'], r['descricao'], r['data_movimento']) == ('DEBITO', 20.0, 'Tarifa', '2027-05-01')
    assert saldo(banco, nova['id']) == Decimal('980.00')
    assert falha(banco, 'editar_ajuste_conta', PESSOAL, nova['id'], mov['id'], {'valor': 0})[1] == 'valor deve ser maior que zero'
    assert falha(banco, 'editar_ajuste_conta', PESSOAL, nova['id'], mov['id'], {'tipo': 'X'})[1] == 'tipo deve ser CREDITO ou DEBITO'
    # Transferencia (e qualquer outro movimento) nao e ajustavel.
    outra = criar(banco, nome='Outra (teste)')
    t = transferir(banco, nova['id'], outra['id'])
    assert falha(banco, 'editar_ajuste_conta', PESSOAL, nova['id'], t['debito']['id'], {'valor': 1})[1] == \
        'Apenas movimentos de AJUSTE podem ser alterados'
    assert falha(banco, 'excluir_ajuste_conta', PESSOAL, nova['id'], t['debito']['id'])[1] == \
        'Apenas movimentos de AJUSTE podem ser alterados'
    # Movimento de outra conta pela rota desta: nao encontrado.
    assert 'nao encontrado' in falha(banco, 'excluir_ajuste_conta', PESSOAL, outra['id'], mov['id'])[1]
    assert rpc(banco, 'excluir_ajuste_conta', PESSOAL, nova['id'], mov['id'])['movimento_id'] == mov['id']
    assert saldo(banco, nova['id']) == Decimal('750.00')
    assert falha(banco, 'excluir_ajuste_conta', EMPRESA, nova['id'], mov['id'])[0] == '42501'


def test_ajuste_estornado_nao_e_excluido(banco):
    nova = criar(banco)
    mov = ajustar(banco, nova['id'], valor_do_ajuste='50')['movimento']
    sql(banco, """insert into public.movimento_financeiro (perfil_financeiro_id, conta_bancaria_id, tipo, valor, descricao,
                  data_movimento, origem, ajustavel, movimento_original_id) values (%s, %s, 'DEBITO', 50, 'estorno', '2027-05-13',
                  'MANUAL', false, %s)""", (PESSOAL, nova['id'], mov['id']))
    assert falha(banco, 'excluir_ajuste_conta', PESSOAL, nova['id'], mov['id'])[1] == \
        'Operacao bloqueada: Possui movimento financeiro vinculado'


# --- Transferencia ------------------------------------------------------------------------------------------------

def test_transferencia_debito_e_credito_pareados_sem_receita_nem_despesa(banco):
    origem, destino = criar(banco), criar(banco, nome='Destino (teste)', saldo_inicial=0)
    total_antes = sum(c['saldo_atual'] for c in rpc(banco, 'contas_bancarias_tela', PESSOAL, None))
    despesas = sql(banco, 'select count(*) as n from public.conta')[0]['n']
    receitas = sql(banco, 'select count(*) as n from public.receita_realizada')[0]['n']
    chave = str(uuid.uuid4())
    r = transferir(banco, origem['id'], destino['id'], chave=chave)
    d, c = r['debito'], r['credito']
    assert (d['tipo'], d['conta_bancaria_id'], c['tipo'], c['conta_bancaria_id']) == \
        ('DEBITO', origem['id'], 'CREDITO', destino['id'])
    assert d['transferencia_id'] == c['transferencia_id'] == r['transferencia_id']
    assert {d['origem'], c['origem']} == {'TRANSFERENCIA'} and not d['ajustavel'] and d['valor'] == c['valor'] == 250
    assert all(m[k] is None for m in (d, c) for k in ('conta_id', 'fatura_id', 'receita_realizada_id'))
    assert (saldo(banco, origem['id']), saldo(banco, destino['id'])) == (Decimal('750.00'), Decimal('250.00'))
    assert transferir(banco, origem['id'], destino['id'], chave=chave)['repetida'] is True   # reenvio nao duplica
    assert len(movimentos(banco, origem['id'])) == 1
    # Total do perfil igual: transferencia nao e receita nem despesa.
    assert sum(c['saldo_atual'] for c in rpc(banco, 'contas_bancarias_tela', PESSOAL, None)) == total_antes
    assert sql(banco, 'select count(*) as n from public.conta')[0]['n'] == despesas
    assert sql(banco, 'select count(*) as n from public.receita_realizada')[0]['n'] == receitas


def test_transferencia_recusada_sem_gravar(banco):
    origem, destino = criar(banco), criar(banco, nome='Destino (teste)')
    alheia = conta_id(banco, 'Conta Perfil B')
    assert falha(banco, 'transferir_entre_contas', PESSOAL, {'conta_origem_id': origem['id'], 'conta_destino_id': origem['id'],
                 'valor': 1}, str(uuid.uuid4()))[1] == 'Conta de origem e destino devem ser diferentes'
    assert falha(banco, 'transferir_entre_contas', PESSOAL, {'conta_origem_id': origem['id'], 'conta_destino_id': alheia,
                 'valor': 1}, str(uuid.uuid4()))[1] == 'Conta bancaria nao encontrada neste perfil'
    assert falha(banco, 'transferir_entre_contas', PESSOAL, {'conta_origem_id': origem['id'], 'conta_destino_id': 999999,
                 'valor': 1}, str(uuid.uuid4()))[1] == 'Conta bancaria nao encontrada neste perfil'
    for valor in ('0', '-5', '1.234', 'abc'):
        assert falha(banco, 'transferir_entre_contas', PESSOAL, {'conta_origem_id': origem['id'],
                     'conta_destino_id': destino['id'], 'valor': valor}, str(uuid.uuid4()))[0] == '22023'
    assert falha(banco, 'transferir_entre_contas', PESSOAL, {'conta_origem_id': origem['id']}, str(uuid.uuid4()))[1] == \
        'conta_origem_id, conta_destino_id e valor sao obrigatorios'
    rpc(banco, 'editar_conta_bancaria', PESSOAL, destino['id'], None, {'status': 'INATIVO'})
    assert falha(banco, 'transferir_entre_contas', PESSOAL, {'conta_origem_id': origem['id'], 'conta_destino_id': destino['id'],
                 'valor': 1}, str(uuid.uuid4()))[1] == 'Conta bancaria inativa'
    assert movimentos(banco, origem['id']) == [] and movimentos(banco, destino['id']) == []


def test_transferencias_simultaneas_em_sentidos_opostos_sem_impasse(banco):
    a, b = criar(banco, nome='A (teste)'), criar(banco, nome='B (teste)')
    tarefas = [em_thread(lambda o=o, d=d: transferir(banco, o, d, valor='10.00'))
               for o, d in [(a['id'], b['id']), (b['id'], a['id'])] * 5]
    for tarefa, _ in tarefas:
        tarefa.join(timeout=60)
    assert all('erro' not in r for _, r in tarefas), [r.get('erro') for _, r in tarefas]
    assert (saldo(banco, a['id']), saldo(banco, b['id'])) == (Decimal('1000.00'), Decimal('1000.00'))
    assert len(movimentos(banco, a['id'])) == len(movimentos(banco, b['id'])) == 10


# --- Extrato e conferencia ----------------------------------------------------------------------------------------

def test_extrato_ordem_saldo_apos_periodo_e_limite(banco):
    nova = criar(banco)
    for valor, data in (('100', '2027-01-10'), ('-30', '2027-02-05'), ('45.50', '2027-02-20'), ('-15.50', '2027-03-01')):
        ajustar(banco, nova['id'], valor_do_ajuste=valor, data_movimento=data)
    tudo = rpc(banco, 'extrato_conta_bancaria', PESSOAL, nova['id'], None, None, None, True)
    assert [(m['data_movimento'], m['saldo_apos_movimento']) for m in tudo] == [
        ('2027-03-01', 1100.0), ('2027-02-20', 1115.5), ('2027-02-05', 1070.0), ('2027-01-10', 1100.0)]
    # Periodo: saldo base = inicial + movimentos anteriores ao inicio (como o Flask).
    fev = rpc(banco, 'extrato_conta_bancaria', PESSOAL, nova['id'], '2027-02-01', '2027-02-28', None, True)
    assert [m['saldo_apos_movimento'] for m in fev] == [1115.5, 1070.0]
    # Limite: os mais recentes, com o saldo calculado sobre o periodo inteiro.
    assert [m['saldo_apos_movimento'] for m in rpc(banco, 'extrato_conta_bancaria', PESSOAL, nova['id'], None, None, 2, True)] == \
        [1100.0, 1115.5]
    assert all(m['saldo_apos_movimento'] is None
               for m in rpc(banco, 'extrato_conta_bancaria', PESSOAL, nova['id'], None, None, None, False))
    assert falha(banco, 'extrato_conta_bancaria', PESSOAL, nova['id'], '2027-03-01', '2027-02-01', None, True)[1] == \
        'inicio nao pode ser maior que fim'
    assert falha(banco, 'extrato_conta_bancaria', PESSOAL, nova['id'], None, None, 0, True)[1] == \
        'limit deve ser um inteiro maior que zero'
    assert falha(banco, 'extrato_conta_bancaria', PERFIL_B, nova['id'], None, None, None, True, usuario=USUARIO_B)[0] == '22023'


def test_conferencia_so_leitura(banco):
    nova = criar(banco)
    ajustar(banco, nova['id'], valor_do_ajuste='25')
    r = rpc(banco, 'conferir_saldo_conta', PESSOAL, nova['id'])
    assert (r['saldo_inicial'], r['total_creditos'], r['total_debitos'], r['saldo_calculado'], r['saldo_atual'],
            r['divergencia'], r['quantidade_movimentos'], r['consistente']) == (1000, 25, 0, 1025, 1025, 0, 1, True)
    sql(banco, 'update public.conta_bancaria set saldo_atual = 1000 where id = %s', (nova['id'],))  # cache divergente
    r = rpc(banco, 'conferir_saldo_conta', PESSOAL, nova['id'])
    assert (r['divergencia'], r['consistente']) == (-25, False)
    assert sql(banco, 'select saldo_atual from public.conta_bancaria where id = %s', (nova['id'],))[0]['saldo_atual'] == 1000
    # Leitor confere; outro titular nao.
    assert rpc(banco, 'conferir_saldo_conta', EMPRESA, conta_id(banco, 'Conta Empresa (A)'))['consistente'] in (True, False)
    assert falha(banco, 'conferir_saldo_conta', PESSOAL, nova['id'], usuario=USUARIO_B)[0] == '42501'


def test_movimentos_do_mes_listam_ajuste_e_transferencia(banco):
    """P1 de Despesas: os movimentos do mes (movimentos_do_mes) incluem o que a tela de Contas Bancarias grava."""
    a, b = criar(banco, nome='A (teste)'), criar(banco, nome='B (teste)')
    transferir(banco, a['id'], b['id'])
    ajustar(banco, a['id'], valor_do_ajuste='5', data_movimento='2027-05-20')
    r = rpc(banco, 'movimentos_do_mes', PESSOAL, '2027-05-01')
    origens = sorted(m['origem'] for m in r['movimentos'] if m['conta_bancaria_id'] in (a['id'], b['id']))
    assert origens == ['AJUSTE', 'TRANSFERENCIA', 'TRANSFERENCIA']
    saldos = {c['id']: c['saldo'] for c in r['contas']}
    assert (saldos[a['id']], saldos[b['id']]) == (755, 1250)
