"""
Testes FIN-CONTRATOS-2 — pagamento e estorno das parcelas de financiamento e de consorcio pelas despesas, no novo
aplicativo (migration 20261120090000), e a guarda de escritor unico do Flask (financiamentos, consorcios e despesas).

Fidelidade: no cluster descartavel o PROPRIO Flask cria um financiamento FICTICIO (1 parcela = 1 despesa) e paga as
parcelas 1 e 2 pelas despesas, estorna a 2, paga de novo e tenta estornar de novo. O novo aplicativo faz o mesmo noutra
copia (perfil atribuido a ele). Pagamentos: mesmo estado do Flask (parcela, despesa, saldo devedor). Estornos: o Flask
deixa a parcela 'pago' (Defeito A) e bloqueia o segundo estorno (Defeito B); aqui a parcela reabre e o ciclo se repete.
"""
import json
import os
import subprocess
import sys
import uuid
from decimal import Decimal

import pytest

from tests.test_supabase_cartoes import rpc
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

PESSOAL, EMPRESA = ID['PESSOAL'], ID['EMPRESA']
FIN = {'nome': 'Casa SAC (ficticio)', 'sistema_amortizacao': 'SAC', 'produto': 'Habitacional ficticio',
       'valor_financiado': 120000, 'prazo_total_meses': 24, 'taxa_juros_nominal_anual': 9.5, 'data_contrato': '2030-01-10',
       'data_primeira_parcela': '2030-02-10', 'seguro_tipo': 'fixo', 'valor_seguro_mensal': 35.5,
       'taxa_administracao_fixa': 25,
       'vigencias_seguro': [{'competencia_inicio': '2030-02-01', 'valor_mensal': 35.5, 'observacoes': 'apolice ficticia'}]}

# Roteiro do Flask. argv: perfil, conta bancaria, modo ('criar' ou 'roteiro'), dados do financiamento.
_SCRIPT = """
import json, sys, uuid
from backend.app import create_app
from backend.models import Conta, Financiamento, FinanciamentoParcela, Usuario, db
app = create_app('local')
email = f'flask.{uuid.uuid4().hex[:8]}@teste.local'
with app.app_context():
    u = Usuario(email=email, nome='Contratos', ativo=True)
    u.definir_senha('Senha-ficticia-contratos-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-contratos-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
banco, modo, dados = int(sys.argv[2]), sys.argv[3], json.loads(sys.argv[4])
r = c.post('/api/financiamentos', json=dados)
assert r.status_code in (200, 201), r.data[:400]
fin = r.get_json()['data']['id']

def despesa(numero):
    with app.app_context():
        p = FinanciamentoParcela.query.filter_by(financiamento_id=fin, numero_parcela=numero).first()
        conta = Conta.query.filter_by(financiamento_parcela_id=p.id).first()
        return conta.id

def estado():
    with app.app_context():
        f = db.session.get(Financiamento, fin)
        ps = FinanciamentoParcela.query.filter_by(financiamento_id=fin).filter(FinanciamentoParcela.numero_parcela <= 3).order_by(FinanciamentoParcela.numero_parcela).all()
        return {'saldo': str(f.saldo_devedor_atual), 'parcelas': [[p.numero_parcela, p.status, str(p.valor_pago), str(p.dif_apurada)] for p in ps],
                'despesas': [db.session.get(Conta, despesa(n)).status_pagamento for n in (1, 2)]}

saida = {'fin': fin, 'despesas': {n: despesa(n) for n in (1, 2, 3)}, 'inicial': estado()}
if modo == 'roteiro':
    passos = [('pagar1', 1, 'pagar', {'conta_bancaria_id': banco, 'data_pagamento': '2030-02-10'}),
              ('pagar2', 2, 'pagar', {'conta_bancaria_id': banco, 'data_pagamento': '2030-03-10'}),
              ('estornar2', 2, 'estornar-pagamento', {'motivo': 'Debito em duplicidade', 'data_estorno': '2030-03-12'}),
              ('repagar2', 2, 'pagar', {'conta_bancaria_id': banco, 'data_pagamento': '2030-03-15'}),
              ('reestornar2', 2, 'estornar-pagamento', {'motivo': 'Valor errado', 'data_estorno': '2030-03-16'})]
    for nome, numero, acao, corpo in passos:
        r = c.post(f'/api/despesas/{despesa(numero)}/{acao}', json=corpo)
        saida[nome] = {'status': r.status_code, 'json': r.get_json(), 'estado': estado()}
print('FLASK_JSON ' + json.dumps(saida))
"""


def flask(dsn, perfil, banco, modo):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT, str(perfil), str(banco), modo, json.dumps(FIN)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


def banco_de(dsn):
    return sql(dsn, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']


def estado(dsn, fin, despesas):
    f = sql(dsn, 'select saldo_devedor_atual from public.financiamento where id = %s', (fin,))[0]
    ps = sql(dsn, 'select numero_parcela, status, valor_pago, dif_apurada from public.financiamento_parcela '
                  'where financiamento_id = %s and numero_parcela <= 3 order by numero_parcela', (fin,))
    return {'saldo': str(f['saldo_devedor_atual']),
            'parcelas': [[p['numero_parcela'], p['status'], str(p['valor_pago']), str(p['dif_apurada'])] for p in ps],
            'despesas': [sql(dsn, 'select status_pagamento from public.conta where id = %s', (despesas[n],))[0]['status_pagamento']
                         for n in ('1', '2')]}


def valor_da(dsn, conta):
    return str(sql(dsn, 'select valor from public.conta where id = %s', (conta,))[0]['valor'])


def pagar(dsn, conta, banco, data, chave=None):
    valor = valor_da(dsn, conta)
    return rpc(dsn, 'pagar_despesa', PESSOAL, conta, {'conta_bancaria_id': banco, 'data_pagamento': data, 'valor_pago': valor,
                                                     'valor_devido': valor}, chave or str(uuid.uuid4()))


def estornar(dsn, conta, movimento, motivo, data):
    return rpc(dsn, 'estornar_pagamento_despesa', PESSOAL, conta, movimento, {'motivo': motivo, 'data_estorno': data},
               str(uuid.uuid4()))


def falha(dsn, funcao, *args, usuario=None):
    with pytest.raises(psycopg2.Error) as erro:
        rpc(dsn, funcao, *args, **({'usuario': usuario} if usuario else {}))
    return erro.value.diag.message_primary, erro.value.diag.message_hint


@pytest.fixture(scope='module')
def referencia(cluster):  # noqa: F811
    """O roteiro inteiro no Flask (perfil no Flask)."""
    dsn = copiar(cluster)
    return flask(dsn, PESSOAL, banco_de(dsn), 'roteiro')


@pytest.fixture
def novo(cluster):  # noqa: F811
    """Financiamento criado pelo Flask (antes da transicao) e o perfil depois atribuido ao novo aplicativo."""
    dsn = copiar(cluster)
    r = flask(dsn, PESSOAL, banco_de(dsn), 'criar')
    atribuir(dsn, 'PESSOAL')
    return dsn, r['fin'], r['despesas'], banco_de(dsn)


def test_pagamentos_iguais_ao_flask_e_estornos_corrigidos(referencia, novo):
    dsn, fin, despesas, banco = novo
    assert estado(dsn, fin, despesas) == referencia['inicial']
    p1 = pagar(dsn, despesas['1'], banco, '2030-02-10')
    assert estado(dsn, fin, despesas) == referencia['pagar1']['estado']
    p2 = pagar(dsn, despesas['2'], banco, '2030-03-10')
    assert estado(dsn, fin, despesas) == referencia['pagar2']['estado']  # parcela, despesa e saldo devedor como o Flask

    # Defeito A: o Flask devolve a despesa a Pendente e deixa a parcela 'pago' (saldo devedor reduzido).
    assert referencia['estornar2']['status'] == 200
    assert referencia['estornar2']['estado']['parcelas'][1][1] == 'pago'
    assert referencia['estornar2']['estado']['despesas'][1] == 'Pendente'
    estornar(dsn, despesas['2'], p2['movimento_id'], 'Debito em duplicidade', '2030-03-12')
    depois = estado(dsn, fin, despesas)
    assert depois['parcelas'][1][1:] == ['pendente', '0.00', '0.00'] and depois['despesas'][1] == 'Pendente'
    assert depois['saldo'] == referencia['pagar1']['estado']['saldo']  # volta a cadeia: saldo apos a parcela 1

    # Defeito B: pagar de novo e estornar de novo (no Flask o novo pagamento ja falha, pela parcela que ficou 'pago').
    p2b = pagar(dsn, despesas['2'], banco, '2030-03-15')
    assert estado(dsn, fin, despesas) == referencia['pagar2']['estado']
    assert referencia['reestornar2']['status'] == 409
    estornar(dsn, despesas['2'], p2b['movimento_id'], 'Valor errado', '2030-03-16')
    assert estado(dsn, fin, despesas)['parcelas'][1][1] == 'pendente'
    movs = sql(dsn, 'select tipo, origem, movimento_original_id from public.movimento_financeiro where conta_id = %s order by id',
               (despesas['2'],))
    assert [(m['tipo'], m['origem']) for m in movs] == [('DEBITO', 'DESPESA'), ('CREDITO', 'ESTORNO_DESPESA')] * 2
    assert [m['movimento_original_id'] for m in movs[1::2]] == [p2['movimento_id'], p2b['movimento_id']]  # identidade propria
    assert p1['movimento_id'] not in [m['movimento_original_id'] for m in movs]


def test_estorno_so_da_parcela_paga_mais_recente(novo):
    dsn, fin, despesas, banco = novo
    p1 = pagar(dsn, despesas['1'], banco, '2030-02-10')
    pagar(dsn, despesas['2'], banco, '2030-03-10')
    antes = estado(dsn, fin, despesas)
    msg, dica = falha(dsn, 'estornar_pagamento_despesa', PESSOAL, despesas['1'], p1['movimento_id'],
                      {'motivo': 'x', 'data_estorno': '2030-03-11'}, str(uuid.uuid4()))
    assert dica == 'PARCELA_POSTERIOR_PAGA' and 'numero 2' in msg
    assert estado(dsn, fin, despesas) == antes  # nada gravado (nem o credito)
    assert sql(dsn, "select count(*) n from public.movimento_financeiro where conta_id = %s and tipo = 'CREDITO'",
               (despesas['1'],))[0]['n'] == 0


def test_pagamento_e_atomico_e_idempotente(novo):
    dsn, fin, despesas, banco = novo
    # Estado inconsistente herdado do Defeito A (parcela 'pago', despesa 'Pendente'): o pagamento inteiro e recusado.
    parcela = sql(dsn, 'select financiamento_parcela_id id from public.conta where id = %s', (despesas['1'],))[0]['id']
    sql(dsn, "update public.financiamento_parcela set status = 'pago' where id = %s", (parcela,))
    antes = (estado(dsn, fin, despesas), sql(dsn, 'select * from public.movimento_financeiro order by id'))
    msg, dica = falha(dsn, 'pagar_despesa', PESSOAL, despesas['1'], {'conta_bancaria_id': banco, 'data_pagamento': '2030-02-10',
                      'valor_pago': valor_da(dsn, despesas['1']), 'valor_devido': valor_da(dsn, despesas['1'])}, str(uuid.uuid4()))
    assert dica == 'PARCELA_PAGA'
    assert (estado(dsn, fin, despesas), sql(dsn, 'select * from public.movimento_financeiro order by id')) == antes
    sql(dsn, "update public.financiamento_parcela set status = 'pendente' where id = %s", (parcela,))
    chave = str(uuid.uuid4())
    a = pagar(dsn, despesas['1'], banco, '2030-02-10', chave)
    b = pagar(dsn, despesas['1'], banco, '2030-02-10', chave)  # reenvio: um debito so
    assert a['movimento_id'] == b['movimento_id'] and b['repetida'] is True
    assert sql(dsn, "select count(*) n from public.movimento_financeiro where conta_id = %s", (despesas['1'],))[0]['n'] == 1


def test_perfil_no_flask_e_quem_so_le_nao_pagam_parcela(cluster):  # noqa: F811
    dsn = copiar(cluster)
    r = flask(dsn, PESSOAL, banco_de(dsn), 'criar')
    conta = r['despesas']['1']
    valor = valor_da(dsn, conta)
    dados = {'conta_bancaria_id': banco_de(dsn), 'data_pagamento': '2030-02-10', 'valor_pago': valor, 'valor_devido': valor}
    assert falha(dsn, 'pagar_despesa', PESSOAL, conta, dados, str(uuid.uuid4()))[1] == 'SISTEMA_FLASK'
    atribuir(dsn, 'PESSOAL')
    assert 'nao autorizado' in falha(dsn, 'pagar_despesa', PESSOAL, conta, dados, str(uuid.uuid4()), usuario=USUARIO_B)[0]


# --- Consorcio --------------------------------------------------------------------------------------------------

_CONSORCIO = """
import json, sys, uuid
from backend.app import create_app
from backend.models import Conta, ItemDespesa, Usuario, db
app = create_app('local')
email = f'flask.{uuid.uuid4().hex[:8]}@teste.local'
with app.app_context():
    u = Usuario(email=email, nome='Consorcio', ativo=True)
    u.definir_senha('Senha-ficticia-consorcio-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-consorcio-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
r = c.post('/api/consorcios/', json={'nome': 'Consorcio Moto (ficticio)', 'valor_inicial': 300, 'numero_parcelas': 6,
                                     'categoria_id': int(sys.argv[2]), 'mes_inicio': '2031-03'})
assert r.status_code in (200, 201), r.data[:400]
cid = r.get_json()['data']['id']
with app.app_context():
    contas = [c.id for c in Conta.query.join(ItemDespesa, ItemDespesa.id == Conta.item_despesa_id)
              .filter(ItemDespesa.tipo == 'Consorcio', ItemDespesa.nome.like('Consorcio Moto%')).order_by(Conta.data_vencimento)]
print('FLASK_JSON ' + json.dumps({'id': cid, 'contas': contas}))
"""


def test_parcela_de_consorcio_paga_e_estornada_mantendo_o_contrato(cluster):  # noqa: F811
    dsn = copiar(cluster)
    categoria = sql(dsn, 'select id from public.categoria order by id limit 1')[0]['id']
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _CONSORCIO, str(PESSOAL), str(categoria)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    contas = json.loads(linha[len('FLASK_JSON '):])['contas']
    assert len(contas) == 6
    atribuir(dsn, 'PESSOAL')
    banco = banco_de(dsn)
    item_antes = sql(dsn, 'select i.* from public.item_despesa i join public.conta c on c.item_despesa_id = i.id where c.id = %s',
                     (contas[0],))
    p = pagar(dsn, contas[0], banco, '2031-03-10')
    conta = sql(dsn, 'select status_pagamento, valor, item_despesa_id from public.conta where id = %s', (contas[0],))[0]
    assert conta['status_pagamento'] == 'Pago' and conta['valor'] == Decimal('300.00')
    assert sql(dsn, 'select i.* from public.item_despesa i where i.id = %s', (conta['item_despesa_id'],)) == item_antes  # contrato intacto
    estornar(dsn, contas[0], p['movimento_id'], 'Boleto em duplicidade', '2031-03-11')
    p2 = pagar(dsn, contas[0], banco, '2031-03-12')
    estornar(dsn, contas[0], p2['movimento_id'], 'Outro motivo', '2031-03-13')  # segundo ciclo tambem
    assert sql(dsn, 'select status_pagamento from public.conta where id = %s', (contas[0],))[0]['status_pagamento'] == 'Pendente'
    assert sql(dsn, 'select saldo_atual = financeiro.saldo_da_conta(id) ok, saldo_atual from public.conta_bancaria where id = %s',
               (banco,))[0]['ok'] is True


# --- Escritor unico do lado do Flask ----------------------------------------------------------------------------

_GUARDA = """
import json, sys, uuid
from backend.app import create_app
from backend.models import Conta, FinanciamentoParcela, Usuario, db
app = create_app('local')
email = f'flask.{uuid.uuid4().hex[:8]}@teste.local'
with app.app_context():
    u = Usuario(email=email, nome='Guarda', ativo=True)
    u.definir_senha('Senha-ficticia-guarda-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-guarda-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
fin, consorcio, parcela, despesa, banco, dados = (int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]),
                                                   int(sys.argv[6]), json.loads(sys.argv[7]))
escritas = [('post', '/api/financiamentos', dados), ('put', f'/api/financiamentos/{fin}', {'nome': 'Outro'}),
            ('post', f'/api/financiamentos/{fin}/regenerar-parcelas', {}),
            ('post', f'/api/financiamentos/{fin}/amortizacao-extra', {'data': '2030-04-15', 'valor': 5000, 'tipo': 'reduzir_parcela'}),
            ('post', f'/api/financiamentos/{fin}/ajustar-saldo', {'novo_saldo': 100000, 'motivo': 'teste'}),
            ('post', f'/api/financiamentos/{fin}/vigencias-seguro', {'competencia_inicio': '2030-06-01', 'valor_mensal': 40}),
            ('post', f'/api/financiamentos/{fin}/conferencias-caixa', {}),
            ('post', f'/api/financiamentos/parcelas/{parcela}/pagar', {'conta_bancaria_id': banco, 'data_pagamento': '2030-02-10'}),
            ('post', f'/api/financiamentos/parcelas/{parcela}/estornar-pagamento', {'motivo': 'x', 'data_estorno': '2030-02-11'}),
            ('delete', f'/api/financiamentos/{fin}', None),
            ('post', '/api/consorcios/', {'nome': 'Novo', 'valor_inicial': 100, 'numero_parcelas': 2, 'mes_inicio': '2031-01'}),
            ('put', f'/api/consorcios/{consorcio}', {'nome': 'Outro'}),
            ('post', f'/api/consorcios/{consorcio}/regenerar-parcelas', {}),
            ('delete', f'/api/consorcios/{consorcio}', None),
            ('post', f'/api/despesas/{despesa}/pagar', {'conta_bancaria_id': banco, 'data_pagamento': '2030-02-10'}),
            ('post', f'/api/despesas/{despesa}/estornar-pagamento', {'motivo': 'x', 'data_estorno': '2030-02-11'})]
saida = {'escritas': [], 'leituras': []}
for metodo, rota, corpo in escritas:
    r = getattr(c, metodo)(rota, json=corpo) if corpo is not None else getattr(c, metodo)(rota)
    j = r.get_json() or {}
    saida['escritas'].append([rota, r.status_code, j.get('codigo')])
for rota in ('/api/financiamentos', f'/api/financiamentos/{fin}', '/api/consorcios/', f'/api/consorcios/{consorcio}'):
    saida['leituras'].append([rota, c.get(rota).status_code])
saida['simular'] = c.post(f'/api/financiamentos/{fin}/simular-quitacao', json={'data_quitacao': '2030-06-10'}).status_code
print('FLASK_JSON ' + json.dumps(saida))
"""


def _tabelas(dsn):
    return {t: sql(dsn, f'select * from public.{t} order by id') for t in
            ('financiamento', 'financiamento_parcela', 'contrato_consorcio', 'conta', 'item_despesa', 'movimento_financeiro')}


def test_flask_recusa_escritas_de_contratos_em_perfil_do_novo_aplicativo(cluster):  # noqa: F811
    dsn = copiar(cluster)
    r = flask(dsn, PESSOAL, banco_de(dsn), 'criar')
    categoria = sql(dsn, 'select id from public.categoria order by id limit 1')[0]['id']
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    c = subprocess.run([sys.executable, '-c', _CONSORCIO, str(PESSOAL), str(categoria)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    consorcio = json.loads(next(l for l in c.stdout.splitlines() if l.startswith('FLASK_JSON '))[len('FLASK_JSON '):])['id']
    parcela = sql(dsn, 'select financiamento_parcela_id id from public.conta where id = %s', (r['despesas']['1'],))[0]['id']
    atribuir(dsn, 'PESSOAL')
    antes = _tabelas(dsn)
    g = subprocess.run([sys.executable, '-c', _GUARDA, str(PESSOAL), str(r['fin']), str(consorcio), str(parcela),
                        str(r['despesas']['1']), str(banco_de(dsn)), json.dumps(FIN)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    linha = next((l for l in g.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert g.returncode == 0 and linha, g.stderr[-3000:]
    saida = json.loads(linha[len('FLASK_JSON '):])
    assert [(rota, s, cod) for rota, s, cod in saida['escritas'] if (s, cod) != (409, 'SISTEMA_NOVO')] == []
    assert [s for _, s in saida['leituras']] == [200, 200, 200, 200] and saida['simular'] == 200
    assert _tabelas(dsn) == antes  # nada gravado


def test_flask_continua_escrevendo_contratos_em_perfil_do_flask(referencia):
    """Perfil no Flask (sem atribuicao): a guarda nao muda nada; criar, pagar e estornar pelas despesas como antes.
    Consequencia do Defeito A no Flask: depois do estorno a parcela segue 'pago' e pagar de novo da erro 500
    (registrar_pagamento_parcela recusa "Esta parcela ja foi paga"); o novo aplicativo paga de novo (teste acima)."""
    assert [referencia[p]['status'] for p in ('pagar1', 'pagar2', 'estornar2')] == [200, 200, 200]
    assert referencia['repagar2']['status'] == 500
    assert referencia['repagar2']['estado']['despesas'][1] == 'Pendente'  # nada gravado no erro
    assert referencia['reestornar2']['status'] == 409


# --- Reversao ---------------------------------------------------------------------------------------------------

def test_reversao_devolve_as_definicoes_anteriores_e_volta(cluster):  # noqa: F811
    from pathlib import Path
    supabase = Path(ROOT) / 'supabase'
    dsn = copiar(cluster)
    estado_funcoes = ("select p.oid::regprocedure::text s, md5(p.prosrc) c, coalesce(p.proacl::text, '') a from pg_proc p "
                      "join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro'")
    com = {r['s']: r for r in sql(dsn, estado_funcoes)}

    def executar(arquivo):
        conn = psycopg2.connect(dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(arquivo.read_text(encoding='utf-8'))
        finally:
            conn.close()

    executar(supabase / 'reversao' / '20261120090000_pagamento_despesa_anterior.sql')
    sem = {r['s']: r for r in sql(dsn, estado_funcoes)}
    internas = {'financeiro.parcela_da_despesa(integer)', 'financeiro.saldo_devedor_pelas_parcelas(integer)',
                'financeiro.sincronizar_parcela_paga(integer,numeric)', 'financeiro.reabrir_parcela_estornada(integer)'}
    assert set(com) - set(sem) == internas and set(sem) <= set(com)
    trocadas = {s for s in sem if sem[s] != com[s]}
    assert trocadas == {'financeiro.bloqueio_do_pagamento(integer)', 'financeiro.pagar_despesa(integer,integer,jsonb,uuid)',
                        'financeiro.estornar_pagamento_despesa(integer,integer,integer,jsonb,uuid)'}
    assert all(sem[s]['a'] == com[s]['a'] for s in trocadas)  # mesmos privilegios
    origem = (supabase / 'migrations' / '20261101090000_financeiro_movimentacoes.sql').read_text(encoding='utf-8')
    corpo = sql(dsn, "select prosrc from pg_proc where oid = 'financeiro.pagar_despesa(integer,integer,jsonb,uuid)'::regprocedure")[0]['prosrc']
    assert corpo in origem  # a definicao de 20261101090000, sem as linhas FIN-CONTRATOS-2
    executar(supabase / 'migrations' / '20261120090000_financeiro_contratos_pagamento.sql')
    # FIN-FINANCIAMENTOS-MOTOR-1 (20261123090000) redefine o saldo pela cadeia; reaplicar so a 1120 traz a versao dela.
    redefinidas_depois = {'financeiro.saldo_devedor_pelas_parcelas(integer)'}
    depois = {r['s']: r for r in sql(dsn, estado_funcoes)}
    assert {s: r for s, r in depois.items() if s not in redefinidas_depois} ==         {s: r for s, r in com.items() if s not in redefinidas_depois}
