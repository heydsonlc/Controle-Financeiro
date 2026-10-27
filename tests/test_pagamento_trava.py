"""
Testes FIN-PAGAMENTO-TRAVA-1 — concorrencia real nas operacoes financeiras do Flask.

Bancos ISOLADOS e dados FICTICIOS: copia do cluster PostgreSQL descartavel (cenario do
FIN-RECORRENCIA-1, perfil "Pessoal" ficticio 101) e um arquivo SQLite temporario. Nunca o
gastos.db nem o Supabase.

Cada operacao roda num PROCESSO Flask real (conexao e transacao proprias). Um processo para
numa barreira imediatamente antes do commit — com tudo ja gravado na transacao — enquanto o
outro e iniciado; so entao o primeiro e liberado. Assim a corrida e efetiva (nao sequencial):
sem a trava, o segundo processo leria o estado antigo (foi o que ocorreu no Supabase de teste:
conta paga por R$ 500,00 com movimento de R$ 350,40).
"""
import json
import os
import subprocess
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_fatura_unica import aguardar, aguardar_bloqueio, em_thread, liberar
from tests.test_supabase_recorrencia import (
    PG_BIN,
    ROOT,
    USUARIO_A,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')

PERFIL = 101
CONTA = 7001          # despesa ficticia de R$ 350,40 (cenario reproduzido no Supabase de teste)
CONTA_B = 7002        # outra despesa na mesma conta bancaria
CONTA_DA = 7003       # debito automatico vencido
CARTAO = 910
FATURA_MES = '2027-06-01'
EMAIL, SENHA = 'flask.trava@teste.local', 'Senha-ficticia-trava-2026'

_WORKER = r'''
import json, sys, time
from datetime import date
from pathlib import Path
cfg = json.loads(sys.argv[1])
pasta = Path(cfg['pasta'])

def esperar(etapa):
    (pasta / f"{cfg['nome']}_{etapa}").touch()
    limite = time.time() + 120
    while not (pasta / f'liberar_{etapa}').exists():
        if time.time() > limite:
            raise SystemExit('barreira expirou: ' + etapa)
        time.sleep(0.02)

from flask import session
from sqlalchemy import event
from backend.app import create_app
from backend.models import db

app = create_app('local')

def instalar_pausa():
    # Para no primeiro commit que confirma escrita (a transacao ja tem tudo; travas seguras).
    escreveu, feito = [], []
    event.listen(db.session, 'after_flush', lambda *a: escreveu.append(1))
    commit_original = db.session.commit
    def commit_pausado():
        if escreveu and not feito:
            feito.append(1)
            esperar('pausa')
        return commit_original()
    db.session.commit = commit_pausado

def instalar_falha():
    from backend.services.conta_bancaria_service import ContaBancariaService
    def falha(conta_id):
        raise RuntimeError('falha simulada depois de gravar o movimento')
    ContaBancariaService.recalcular_saldo_conta = staticmethod(falha)

with app.app_context():
    if cfg['acao'] == 'http':
        c = app.test_client()
        assert c.post('/login', data={'email': cfg['email'], 'senha': cfg['senha']}).status_code == 302
        assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': cfg['perfil']}).status_code == 200
        if cfg.get('pausa'):
            instalar_pausa()
        if cfg.get('falhar'):
            instalar_falha()
        r = getattr(c, cfg['metodo'])(cfg['rota'], json=cfg.get('corpo'))
        print('RESULTADO ' + json.dumps({'status': r.status_code, 'json': r.get_json()}))
    else:
        with app.test_request_context():
            session['perfil_financeiro_id'] = cfg['perfil']
            if cfg.get('pausa'):
                instalar_pausa()
            if cfg['acao'] == 'recalcular':
                from backend.services.cartao_service import CartaoService
                f = CartaoService.recalcular_fatura(cfg['cartao'], date.fromisoformat(cfg['competencia']))
                print('RESULTADO ' + json.dumps({'valor': str(f.valor)}))
            elif cfg['acao'] == 'baixa_da':
                from backend.services.debito_automatico_service import executar_baixa_debito_automatico
                print('RESULTADO ' + json.dumps({'baixadas': executar_baixa_debito_automatico(perfil_id=cfg['perfil'])}))
            elif cfg['acao'] == 'preparar_sqlite':
                from backend.models import Usuario, PerfilFinanceiro, ContaBancaria, ItemDespesa, Conta, Categoria
                db.create_all()
                u = Usuario(email=cfg['email'], nome='Trava', ativo=True)
                u.definir_senha(cfg['senha'])
                db.session.add(u)
                perfil = PerfilFinanceiro(id=cfg['perfil'], nome='Pessoal', tipo='PESSOAL', cor='#2563eb', ativo=True,
                                          padrao=True, avatar='PE')
                db.session.add(perfil)
                db.session.add(Categoria(id=951, nome='Moradia T', cor='#2563eb', ativo=True))
                db.session.add(ContaBancaria(id=1, perfil_financeiro_id=cfg['perfil'], nome='Conta ficticia',
                                             instituicao='Banco ficticio', tipo='Conta Corrente', status='ATIVO',
                                             saldo_inicial=1000, saldo_atual=1000, cor_display='#3b82f6'))
                db.session.add(ItemDespesa(id=901, perfil_financeiro_id=cfg['perfil'], categoria_id=951, nome='Aluguel',
                                           tipo='Simples', ativo=True))
                db.session.add(Conta(id=cfg['conta'], perfil_financeiro_id=cfg['perfil'], item_despesa_id=901,
                                     mes_referencia=date(2027, 5, 1), descricao='Conserto (teste)', valor=350.40,
                                     data_vencimento=date(2027, 5, 10), status_pagamento='Pendente',
                                     is_fatura_cartao=False, estouro_orcamento=False, status_fatura='ABERTA'))
                db.session.commit()
                print('RESULTADO ' + json.dumps({'ok': True}))
'''


class Flask:
    """Processo Flask real (conexao e transacao proprias) executando uma operacao."""

    def __init__(self, url, pasta, nome, **cfg):
        env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': url}
        env.pop('FLASK_ENV', None)
        self.pasta, self.nome = Path(pasta), nome
        self.saida, self.erro = self.pasta / f'{nome}.out', self.pasta / f'{nome}.err'
        corpo = {'pasta': str(pasta), 'nome': nome, 'perfil': PERFIL, 'email': EMAIL, 'senha': SENHA, **cfg}
        with open(self.saida, 'w') as saida, open(self.erro, 'w') as erro:
            self.processo = subprocess.Popen([sys.executable, '-c', _WORKER, json.dumps(corpo)], cwd=ROOT, env=env,
                                             stdout=saida, stderr=erro, stdin=subprocess.DEVNULL)

    def log(self):
        return self.erro.read_text(errors='replace')

    def resultado(self):
        self.processo.wait(timeout=180)
        assert self.processo.returncode == 0, self.log()[-2500:]
        linhas = self.saida.read_text(errors='replace').splitlines()
        return json.loads([linha for linha in linhas if linha.startswith('RESULTADO ')][-1][10:])

    def pausado(self):
        aguardar(self.pasta, [f'{self.nome}_pausa'], [self])

    def liberar(self):
        liberar(self.pasta, 'pausa')


def http(url, pasta, nome, metodo, rota, corpo=None, **cfg):
    return Flask(url, pasta, nome, acao='http', metodo=metodo, rota=rota, corpo=corpo, **cfg)


def pagar_corpo(conta_bancaria):
    return {'conta_bancaria_id': conta_bancaria, 'data_pagamento': '2027-05-10'}


def corrida(primeiro, segundo_fabrica, dsn=None):
    """Para `primeiro` antes do commit, inicia o segundo, confere que ele ESPERA, e libera o primeiro."""
    primeiro.pausado()
    segundo = segundo_fabrica()
    if dsn:
        aguardar_bloqueio(dsn)  # o segundo esta parado na trava (corrida efetiva)
    else:
        time.sleep(2)
    assert segundo.processo.poll() is None
    primeiro.liberar()
    return primeiro.resultado(), segundo.resultado()


# ---------------------------------------------------------------------------
# PostgreSQL (cluster descartavel)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def base(cluster, tmp_path_factory):  # noqa: F811
    """Ajusta o banco-modelo do modulo (as copias herdam): usuario do Flask, saldo, despesas e fatura."""
    dsn = cluster.dsn()
    sql(dsn, "update public.perfil_financeiro set avatar = upper(left(nome, 2))")  # o Flask nao grava na leitura
    sql(dsn, "update public.conta_bancaria set saldo_inicial = 1000, saldo_atual = 1000 where nome = 'Conta Pessoal (A)'")
    banco_id = sql(dsn, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']
    for cid, descricao, valor, debito in ((CONTA, 'Conserto geladeira', '350.40', False),
                                          (CONTA_B, 'Internet', '120.00', False),
                                          (CONTA_DA, 'Escola (debito)', '80.00', True)):
        sql(dsn, "insert into public.conta (id, perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, "
                 "data_vencimento, status_pagamento, debito_automatico, conta_bancaria_id, is_fatura_cartao, "
                 "estouro_orcamento, status_fatura) values (%s, %s, 901, '2027-05-01', %s, %s, '2026-05-10', "
                 "'Pendente', %s, %s, false, false, 'ABERTA')",
            (cid, PERFIL, descricao, valor, debito, banco_id if debito else None))
    sql(dsn, 'update public.config_agregador set dia_vencimento = 10 where item_despesa_id = %s', (CARTAO,))
    pasta = tmp_path_factory.mktemp('trava_base')
    # Usuario do Flask e a fatura de 06/2027 com duas compras (pelo proprio Flask).
    script = ("from backend.app import create_app\nfrom backend.models import Usuario, db\n"
              "app = create_app('local')\nwith app.app_context():\n"
              f"    u = Usuario(email='{EMAIL}', nome='Trava', ativo=True)\n    u.definir_senha('{SENHA}')\n"
              "    db.session.add(u); db.session.commit()\n")
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', script], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    for i, valor in enumerate(('200.00', '50.00')):
        compra = {'descricao': f'Compra base {i}', 'valor': valor, 'data_compra': '2027-06-05', 'mes_fatura': '2027-06',
                  'categoria_id': 951, 'total_parcelas': 1}
        assert http(dsn, pasta, f'base{i}', 'post', f'/api/cartoes/{CARTAO}/lancamentos', compra).resultado()['status'] == 201
    return {'banco': banco_id, 'fatura': sql(dsn, "select id from public.conta where is_fatura_cartao and "
                                                  "item_despesa_id = %s and cartao_competencia = %s",
                                             (CARTAO, FATURA_MES))[0]['id']}


@pytest.fixture
def pg(base, cluster, tmp_path):  # noqa: F811
    return {**base, 'dsn': copiar(cluster), 'pasta': tmp_path}


def conta(dsn, conta_id):
    return sql(dsn, 'select * from public.conta where id = %s', (conta_id,))[0]


def movimentos(dsn, conta_id):
    return sql(dsn, 'select tipo, valor, origem, movimento_original_id from public.movimento_financeiro '
                    'where conta_id = %s order by id', (conta_id,))


def saldo(dsn, banco_id):
    linha = sql(dsn, 'select saldo_inicial, saldo_atual from public.conta_bancaria where id = %s', (banco_id,))[0]
    calculado = linha['saldo_inicial'] + sql(
        dsn, "select coalesce(sum(case when tipo = 'CREDITO' then valor else -valor end), 0) as s "
             "from public.movimento_financeiro where conta_bancaria_id = %s", (banco_id,))[0]['s']
    return linha['saldo_atual'], calculado


def coerente(dsn, conta_id):
    """Situacao, valor e movimentos contam a mesma historia (debitos - estornos)."""
    c, ms = conta(dsn, conta_id), movimentos(dsn, conta_id)
    liquido = sum(m['valor'] if m['tipo'] == 'DEBITO' else -m['valor'] for m in ms)
    if c['status_pagamento'] == 'Pago':
        return liquido == c['valor'] and ms[-1]['tipo'] == 'DEBITO' and ms[-1]['valor'] == c['valor']
    return liquido == 0


# 1. Edicao durante pagamento (o cenario reproduzido no Supabase de teste)
def test_edicao_durante_pagamento_nao_diverge(pg):
    d, p = pg['dsn'], pg['pasta']
    pagamento = http(d, p, 'pag', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco']), pausa=True)
    rp, re_ = corrida(pagamento, lambda: http(d, p, 'ed', 'put', f'/api/despesas/{CONTA}', {'valor': '500.00'}), d)
    assert rp['status'] == 200 and re_['status'] == 409  # a edicao esperou e viu a conta paga
    assert conta(d, CONTA)['valor'] == Decimal('350.40') and coerente(d, CONTA)
    assert [m['valor'] for m in movimentos(d, CONTA)] == [Decimal('350.40')]
    assert saldo(d, pg['banco']) == (Decimal('649.60'), Decimal('649.60'))


# 2. Pagamento durante edicao
def test_pagamento_durante_edicao_paga_o_valor_novo(pg):
    d, p = pg['dsn'], pg['pasta']
    edicao = http(d, p, 'ed', 'put', f'/api/despesas/{CONTA}', {'valor': '500.00'}, pausa=True)
    re_, rp = corrida(edicao, lambda: http(d, p, 'pag', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco'])), d)
    assert (re_['status'], rp['status']) == (200, 200)
    assert conta(d, CONTA)['valor'] == Decimal('500.00') and coerente(d, CONTA)
    assert [m['valor'] for m in movimentos(d, CONTA)] == [Decimal('500.00')]


# 3 e 4. Dois pagamentos simultaneos; repeticao depois de concluido
def test_dois_pagamentos_simultaneos_e_repeticao_um_debito(pg):
    d, p = pg['dsn'], pg['pasta']
    primeiro = http(d, p, 'p1', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco']), pausa=True)
    r1, r2 = corrida(primeiro, lambda: http(d, p, 'p2', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco'])), d)
    r3 = http(d, p, 'p3', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco'])).resultado()  # reenvio
    assert (r1['status'], r2['status'], r3['status']) == (200, 409, 409)
    assert 'ja foi paga' in r2['json']['error'] or 'já foi paga' in r2['json']['error']
    assert len(movimentos(d, CONTA)) == 1 and coerente(d, CONTA)
    assert saldo(d, pg['banco']) == (Decimal('649.60'), Decimal('649.60'))


# 5 e 11. Falha no meio da transacao: nada fica (nem conta paga sem movimento, nem saldo)
def test_falha_no_meio_nao_deixa_conta_paga_nem_movimento(pg):
    d, p = pg['dsn'], pg['pasta']
    antes = (conta(d, CONTA), saldo(d, pg['banco']))
    r = http(d, p, 'falha', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco']), falhar=True).resultado()
    assert r['status'] == 500
    assert (conta(d, CONTA), saldo(d, pg['banco'])) == antes and movimentos(d, CONTA) == []
    r = http(d, p, 'depois', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco'])).resultado()
    assert r['status'] == 200 and coerente(d, CONTA)  # a nova tentativa repete a transacao inteira


# 11. Saldo: pagamentos simultaneos de contas diferentes na mesma conta bancaria
def test_pagamentos_na_mesma_conta_bancaria_nao_perdem_saldo(pg):
    d, p = pg['dsn'], pg['pasta']
    a = http(d, p, 'a', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco']), pausa=True)
    ra, rb = corrida(a, lambda: http(d, p, 'b', 'post', f'/api/despesas/{CONTA_B}/pagar', pagar_corpo(pg['banco'])), d)
    assert (ra['status'], rb['status']) == (200, 200)
    assert saldo(d, pg['banco']) == (Decimal('529.60'), Decimal('529.60'))  # 1000 - 350,40 - 120,00


# 9. Dois estornos do mesmo movimento
def test_dois_estornos_simultaneos_um_credito(pg):
    d, p = pg['dsn'], pg['pasta']
    assert http(d, p, 'pag', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco'])).resultado()['status'] == 200
    corpo = {'motivo': 'teste', 'data_estorno': '2027-05-11'}
    e1 = http(d, p, 'e1', 'post', f'/api/despesas/{CONTA}/estornar-pagamento', corpo, pausa=True)
    r1, r2 = corrida(e1, lambda: http(d, p, 'e2', 'post', f'/api/despesas/{CONTA}/estornar-pagamento', corpo), d)
    assert (r1['status'], r2['status']) == (200, 409)
    ms = movimentos(d, CONTA)
    assert [(m['tipo'], m['origem']) for m in ms] == [('DEBITO', 'DESPESA'), ('CREDITO', 'ESTORNO_DESPESA')]
    assert ms[1]['movimento_original_id'] is not None and coerente(d, CONTA)
    assert saldo(d, pg['banco']) == (Decimal('1000.00'), Decimal('1000.00'))


# 10. Estorno concorrente com outro pagamento da mesma conta
def test_estorno_e_novo_pagamento_simultaneos_em_ordem_valida(pg):
    d, p = pg['dsn'], pg['pasta']
    assert http(d, p, 'pag', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco'])).resultado()['status'] == 200
    estorno = http(d, p, 'est', 'post', f'/api/despesas/{CONTA}/estornar-pagamento',
                   {'motivo': 'teste', 'data_estorno': '2027-05-11'}, pausa=True)
    re_, rp = corrida(estorno, lambda: http(d, p, 'pag2', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco'])), d)
    assert (re_['status'], rp['status']) == (200, 200)  # pago -> estornado -> pago de novo
    assert [m['tipo'] for m in movimentos(d, CONTA)] == ['DEBITO', 'CREDITO', 'DEBITO'] and coerente(d, CONTA)
    assert saldo(d, pg['banco']) == (Decimal('649.60'), Decimal('649.60'))


# 8. Duas baixas automaticas simultaneas
def test_duas_baixas_automaticas_um_debito(pg):
    d, p = pg['dsn'], pg['pasta']
    b1 = Flask(d, p, 'da1', acao='baixa_da', pausa=True)
    r1, r2 = corrida(b1, lambda: Flask(d, p, 'da2', acao='baixa_da'), d)
    assert sorted([r1['baixadas'], r2['baixadas']]) == [[], [CONTA_DA]]
    assert len(movimentos(d, CONTA_DA)) == 1 and coerente(d, CONTA_DA)
    assert saldo(d, pg['banco']) == (Decimal('920.00'), Decimal('920.00'))


def test_baixa_automatica_nao_marca_paga_um_debito_ja_estornado(pg):
    d, p = pg['dsn'], pg['pasta']
    assert Flask(d, p, 'da1', acao='baixa_da').resultado()['baixadas'] == [CONTA_DA]
    r = http(d, p, 'est', 'post', f'/api/despesas/{CONTA_DA}/estornar-pagamento',
             {'motivo': 'banco nao debitou', 'data_estorno': '2027-05-11'}).resultado()
    assert r['status'] == 200
    assert Flask(d, p, 'da2', acao='baixa_da').resultado()['baixadas'] == []
    # Antes: voltava a 'Pago' sem movimento valido. Agora fica Pendente (o usuario decide).
    assert conta(d, CONTA_DA)['status_pagamento'] == 'Pendente' and coerente(d, CONTA_DA)


# 6 e 13. Pagamento de fatura em paralelo com compra (Flask e novo aplicativo)
def test_pagamento_de_fatura_com_compra_simultanea(pg):
    d, p, fatura = pg['dsn'], pg['pasta'], pg['fatura']
    compras_antes = sql(d, "select md5(string_agg(t::text, '|' order by id)) as h from public.lancamento_agregado t "
                           "where mes_fatura = %s", (FATURA_MES,))
    pagamento = http(d, p, 'pag', 'post', f'/api/despesas/{fatura}/pagar', pagar_corpo(pg['banco']), pausa=True)
    compra = {'descricao': 'Compra durante o pagamento', 'valor': '30.00', 'data_compra': '2027-06-20',
              'mes_fatura': '2027-06', 'categoria_id': 951, 'total_parcelas': 1}
    rp, rc = corrida(pagamento, lambda: http(d, p, 'compra', 'post', f'/api/cartoes/{CARTAO}/lancamentos', compra), d)
    assert (rp['status'], rc['status']) == (200, 201)
    f = conta(d, fatura)
    assert f['status_pagamento'] == 'Pago' and f['valor'] == f['valor_executado'] == Decimal('250.00') and coerente(d, fatura)
    # A compra esperou e foi para a fatura seguinte; as compras da fatura paga nao mudaram.
    assert sql(d, "select mes_fatura from public.lancamento_agregado where descricao = 'Compra durante o pagamento'") == \
        [{'mes_fatura': date(2027, 7, 1)}]
    assert sql(d, "select md5(string_agg(t::text, '|' order by id)) as h from public.lancamento_agregado t "
                  "where mes_fatura = %s", (FATURA_MES,)) == compras_antes


def test_compra_do_novo_aplicativo_espera_o_pagamento_do_flask(pg):
    d, p, fatura = pg['dsn'], pg['pasta'], pg['fatura']
    pagamento = http(d, p, 'pag', 'post', f'/api/despesas/{fatura}/pagar', pagar_corpo(pg['banco']), pausa=True)
    pagamento.pausado()
    dados = {'cartao_id': CARTAO, 'descricao': 'Compra nova', 'valor': '30.00', 'total_parcelas': 1,
             'data_compra': '2027-06-20', 'mes_fatura': FATURA_MES, 'categoria_id': 951}
    tarefa, resposta = em_thread(lambda: chamar(d, USUARIO_A, 'select financeiro.criar_compra(%s, %s::jsonb, gen_random_uuid())',
                                                (PERFIL, json.dumps(dados))))
    aguardar_bloqueio(d)
    pagamento.liberar()
    assert pagamento.resultado()['status'] == 200
    tarefa.join(60)
    # FIN-CARTOES-PAGAMENTO-1: o pagamento de fatura do Flask confere o sistema do perfil (D5) com a trava consultiva do
    # perfil, que o novo aplicativo tambem toma: a compra espera. FIN-ESCRITOR-UNICO-FINAL-1: o perfil e do Flask, entao,
    # liberada a trava, a compra do novo aplicativo e recusada (antes: ia para a fatura seguinte). A fatura paga nao muda.
    assert 'valor' not in resposta and 'SISTEMA_FLASK' in str(resposta.get('erro'))
    assert sql(d, "select count(*) as n from public.lancamento_agregado where descricao = 'Compra nova'")[0]['n'] == 0
    assert conta(d, fatura)['valor'] == Decimal('250.00') and coerente(d, fatura)


# 7. Pagamento de fatura em paralelo com recalculo
def test_recalculo_nao_sobrescreve_fatura_paga(pg):
    d, p, fatura = pg['dsn'], pg['pasta'], pg['fatura']
    pagamento = http(d, p, 'pag', 'post', f'/api/despesas/{fatura}/pagar', pagar_corpo(pg['banco']), pausa=True)
    rp, rr = corrida(pagamento, lambda: Flask(d, p, 'rec', acao='recalcular', cartao=CARTAO, competencia=FATURA_MES), d)
    assert rp['status'] == 200 and rr['valor'] == '250.00'
    f = conta(d, fatura)
    assert (f['status_pagamento'], f['valor']) == ('Pago', Decimal('250.00')) and coerente(d, fatura)  # nao virou o planejado


def test_compra_de_fatura_paga_nao_muda_pelo_flask(pg):
    d, p, fatura = pg['dsn'], pg['pasta'], pg['fatura']
    assert http(d, p, 'pag', 'post', f'/api/despesas/{fatura}/pagar', pagar_corpo(pg['banco'])).resultado()['status'] == 200
    lanc = sql(d, "select id from public.lancamento_agregado where descricao = 'Compra base 0'")[0]['id']
    r1 = http(d, p, 'ed', 'put', f'/api/cartoes/lancamentos/{lanc}', {'valor': '1.00'}).resultado()
    r2 = http(d, p, 'ex', 'delete', f'/api/cartoes/lancamentos/{lanc}').resultado()
    assert (r1['status'], r2['status']) == (409, 409) and coerente(d, fatura)


# 14. Compatibilidade com FIN-DESPESAS-1: a edicao do novo aplicativo espera o pagamento do Flask
def test_edicao_do_novo_aplicativo_espera_o_pagamento_do_flask(pg):
    d, p = pg['dsn'], pg['pasta']
    versao = chamar(d, USUARIO_A, 'select financeiro.despesa_para_edicao(%s, %s)', (PERFIL, CONTA))['versao']
    pagamento = http(d, p, 'pag', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco']), pausa=True)
    pagamento.pausado()
    tarefa, resposta = em_thread(lambda: chamar(d, USUARIO_A, 'select financeiro.editar_despesa(%s, %s, %s, %s::jsonb)',
                                                (PERFIL, CONTA, versao, json.dumps({'valor': '500.00'}))))
    aguardar_bloqueio(d)
    pagamento.liberar()
    assert pagamento.resultado()['status'] == 200
    tarefa.join(60)
    assert 'erro' in resposta and conta(d, CONTA)['valor'] == Decimal('350.40') and coerente(d, CONTA)


def test_trava_expira_com_erro_controlado(pg):
    """Sem espera indefinida: com a conta presa alem do limite, a operacao desiste sem gravar (409)."""
    d, p = pg['dsn'], pg['pasta']
    preso = psycopg2.connect(d)
    cur = preso.cursor()
    cur.execute('select 1 from public.conta where id = %s for update', (CONTA,))
    try:
        r = http(d, p, 'pag', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(pg['banco'])).resultado()
    finally:
        preso.rollback()
        preso.close()
    assert r['status'] == 409 and 'tente novamente' in r['json']['error']
    assert movimentos(d, CONTA) == [] and conta(d, CONTA)['status_pagamento'] == 'Pendente'


# ---------------------------------------------------------------------------
# 15. SQLite (arquivo temporario; nunca o gastos.db)
# ---------------------------------------------------------------------------

@pytest.fixture
def sqlite(tmp_path):
    url = f"sqlite:///{(tmp_path / 'trava.db').as_posix()}"
    Flask(url, tmp_path, 'prep', acao='preparar_sqlite', conta=CONTA).resultado()
    return url, tmp_path


def _sqlite(url, comando):
    import sqlite3
    caminho = url.replace('sqlite:///', '')
    with sqlite3.connect(caminho) as conn:
        return conn.execute(comando).fetchall()


def test_sqlite_edicao_durante_pagamento_nao_diverge(sqlite):
    url, p = sqlite
    pagamento = http(url, p, 'pag', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(1), pausa=True)
    rp, re_ = corrida(pagamento, lambda: http(url, p, 'ed', 'put', f'/api/despesas/{CONTA}', {'valor': '500.00'}))
    assert (rp['status'], re_['status']) == (200, 409)
    assert _sqlite(url, f'select status_pagamento, valor from conta where id = {CONTA}') == [('Pago', 350.4)]
    assert _sqlite(url, f'select valor from movimento_financeiro where conta_id = {CONTA}') == [(350.4,)]


def test_sqlite_dois_pagamentos_simultaneos_um_debito(sqlite):
    url, p = sqlite
    primeiro = http(url, p, 'p1', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(1), pausa=True)
    r1, r2 = corrida(primeiro, lambda: http(url, p, 'p2', 'post', f'/api/despesas/{CONTA}/pagar', pagar_corpo(1)))
    assert (r1['status'], r2['status']) == (200, 409)
    assert _sqlite(url, f'select count(*) from movimento_financeiro where conta_id = {CONTA}') == [(1,)]
    assert _sqlite(url, 'select saldo_atual from conta_bancaria where id = 1') == [(649.6,)]
