"""
Testes FIN-RECORRENCIA-T1 — gerador unico de recorrencias por perfil financeiro.

Mesmo cenario FICTICIO do FIN-RECORRENCIA-1 (tests/supabase_local.py), num cluster
PostgreSQL descartavel, com o Flask REAL em subprocesso apontando para copias do
banco. Cada teste usa a sua copia. Padrao: todo perfil e gerado pelo Flask; so a
troca administrativa (financeiro.definir_gerador_recorrencia) muda isso.

Os itens do contrato T1 cobertos aqui: 1, 2, 3, 4, 9, 10, 11 (troca concorrente) e
12. Os itens 5-8 e 11 (repeticao/concorrencia da geracao) estao em
tests/test_supabase_recorrencia.py, que agora roda com o gerador atribuido.
"""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date

import pytest

from tests.supabase_local import claims_usuario
from tests.test_supabase_recorrencia import (
    ID,
    MES,
    PG_BIN,
    ROOT,
    USUARIO_A,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    contas_do_item,
    copiar,
    gerar,
    gerar_confirmado,
    ids,
    lancamentos_do_item,
    previa,
    registros_novos,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
from psycopg2 import errors  # noqa: E402

pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

# Executa uma lista de acoes no Flask real e imprime o resultado de cada uma.
_SCRIPT_FLASK = """
import json, sys
import backend.services.debito_automatico_service as debito
debito.executar_baixa_debito_automatico = lambda *a, **k: None  # baixa automatica fora do escopo
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    if not Usuario.query.filter_by(email='flask.t1@teste.local').first():  # varias execucoes no mesmo banco
        u = Usuario(email='flask.t1@teste.local', nome='T1', ativo=True)
        u.definir_senha('Senha-ficticia-t1-2026')
        db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.t1@teste.local', 'senha': 'Senha-ficticia-t1-2026'}).status_code == 302
saida = []
for acao in json.loads(sys.argv[1]):
    if acao.get('perfil'):
        assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': acao['perfil']}).status_code == 200
    if acao['tipo'] == 'listar':
        r = c.get('/api/despesas/?mes_referencia=' + acao['mes'])
        saida.append({'status': r.status_code, 'ids': sorted(x['id'] for x in r.get_json()['data'])})
    elif acao['tipo'] == 'pagar':
        r = c.post('/api/despesas/%s/pagar' % acao['conta'], json={})
        saida.append({'status': r.status_code})
    elif acao['tipo'] == 'criar_recorrencia':
        r = c.post('/api/recorrencias', json=acao['dados'])
        saida.append({'status': r.status_code, 'id': (r.get_json().get('data') or {}).get('id')})
    elif acao['tipo'] == 'job_faturas':
        from backend.services.cartao_service import CartaoService
        with app.app_context():
            saida.append({'faturas': len(CartaoService.gerar_faturas_mes_atual())})
print('FLASK ' + json.dumps(saida))
"""


def flask(dsn, acoes):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT_FLASK, json.dumps(acoes)],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads([linha for linha in r.stdout.splitlines() if linha.startswith('FLASK ')][-1][6:]), r.stderr


def listar(perfil, mes='2027-03'):
    return {'tipo': 'listar', 'perfil': ID[perfil], 'mes': mes}


def snapshot(dsn):
    return ids(dsn, 'conta'), ids(dsn, 'lancamento_agregado')


def novos(dsn, antes):
    return registros_novos(dsn, *antes)


@pytest.fixture
def banco(cluster):  # noqa: F811
    """Copia SEM atribuicao: todos os perfis no gerador padrao (Flask)."""
    return copiar(cluster)


# ---------------------------------------------------------------------------
# 1-4: quem gera cada perfil
# ---------------------------------------------------------------------------

def test_padrao_e_flask_e_nenhum_perfil_migra_sozinho(banco):
    assert sql(banco, 'select count(*) as n from financeiro.gerador_recorrencia')[0]['n'] == 0
    for perfil in ('PESSOAL', 'EMPRESA', 'PERFIL_B'):
        assert sql(banco, 'select financeiro.gerador_do_perfil(%s) as g', (ID[perfil],))[0]['g'] == 'FLASK'


def test_1_perfil_nao_migrado_continua_gerando_pelo_flask(banco):
    atribuir(banco, 'PERFIL_B')  # outro perfil migrado nao afeta este
    antes = snapshot(banco)
    flask(banco, [listar('PESSOAL'), listar('EMPRESA')])
    criadas = novos(banco, antes)
    assert ('CONTA', 901, MES_D(3)) in criadas and ('FATURA', 910, MES_D(3)) in criadas
    assert ('CONTA', 940, MES_D(3)) in criadas


def test_2_perfil_migrado_nao_gera_pelo_flask_mas_lista(banco):
    atribuir(banco, 'PESSOAL')
    antes = snapshot(banco)
    resultado, log = flask(banco, [listar('PESSOAL'), listar('PESSOAL', '2027-06'), listar('EMPRESA')])
    criadas = novos(banco, antes)
    assert not [k for k in criadas if k[1] in (901, 902, 903, 904, 906, 907, 908, 909, 910, 911)]
    assert ('CONTA', 940, MES_D(3)) in criadas  # Empresa (nao migrada) segue gerando
    assert resultado[0] == {'status': 200, 'ids': [960, 961]}  # lista o que existe, sem gerar nada novo
    assert 'gerado pelo novo aplicativo' in log


def test_2_perfil_migrado_flask_cadastra_recorrencia_sem_gerar_contas(banco):
    atribuir(banco, 'PESSOAL')
    dados = {'nome': 'Nova recorrencia T1', 'valor': '45.00', 'categoria_id': 951, 'data_vencimento': '2027-03-20',
             'tipo_recorrencia': 'mensal', 'meio_pagamento': 'boleto'}
    resultado, _ = flask(banco, [{'tipo': 'criar_recorrencia', 'perfil': ID['PESSOAL'], 'dados': dados},
                                 {'tipo': 'criar_recorrencia', 'perfil': ID['EMPRESA'], 'dados': dados}])
    pessoal, empresa = resultado
    assert pessoal['status'] == 201 and empresa['status'] == 201  # cadastro e operacao legitima
    assert contas_do_item(banco, pessoal['id']) == []             # mas a geracao fica com o novo app
    assert len(contas_do_item(banco, empresa['id'])) == 1         # Empresa: Flask gera o primeiro mes


def test_2_job_e_scheduler_de_faturas_respeitam_o_gerador(banco):
    # O job roda no perfil padrao (Pessoal), no mes atual.
    atribuir(banco, 'PESSOAL')
    resultado, _ = flask(banco, [{'tipo': 'job_faturas'}])
    assert resultado == [{'faturas': 0}] and sql(banco, 'select count(*) as n from public.conta where is_fatura_cartao')[0]['n'] == 0
    atribuir(banco, 'PESSOAL', 'FLASK')
    resultado, _ = flask(banco, [{'tipo': 'job_faturas'}])
    assert resultado == [{'faturas': 1}]  # Cartao Teste (o sem configuracao falha, como antes)


def test_3_perfil_migrado_gera_pelo_novo_aplicativo(banco):
    atribuir(banco, 'PESSOAL')
    p = previa(banco)
    assert (p['gerador'], p['pode_gerir'], p['pode_gerar']) == ('NOVO', True, True)
    assert gerar(banco, p['a_gerar'])['criadas']['total'] == 17


def test_4_perfil_nao_migrado_nao_gera_pelo_novo_aplicativo(banco):
    p = previa(banco)
    assert (p['gerador'], p['pode_gerir'], p['pode_gerar'], p['a_gerar']) == ('FLASK', True, False, 17)
    antes = snapshot(banco)
    with pytest.raises(errors.RaiseException, match='ainda e feita pelo sistema atual'):
        gerar(banco, p['a_gerar'])
    with pytest.raises(errors.RaiseException, match='ainda e feita pelo sistema atual'):
        chamar(banco, USUARIO_A, 'select financeiro.reativar_competencia(%s, %s, %s, %s)', (ID['PESSOAL'], 'CONTA', 902, MES))
    assert snapshot(banco) == antes
    assert sql(banco, 'select count(*) as n from financeiro.geracao_execucao')[0]['n'] == 0


def test_4_quem_nao_gerencia_recebe_nao_autorizado_antes_do_gerador(banco):
    with pytest.raises(errors.InsufficientPrivilege, match='nao autorizado'):
        gerar(banco, 2, 'EMPRESA')  # LEITOR: nao revela o gerador do perfil


# ---------------------------------------------------------------------------
# 5-8 de ponta a ponta com o Flask (dispensa, correcao, inativa, cartao)
# ---------------------------------------------------------------------------

def test_5_a_8_flask_depois_do_novo_nao_recria_nem_duplica(banco):
    atribuir(banco, 'PESSOAL')
    gerar_confirmado(banco, dispensar=[{'natureza': 'CONTA', 'item_id': 902, 'competencia': MES}])
    antes = snapshot(banco)
    flask(banco, [listar('PESSOAL'), listar('PESSOAL', '2027-04')])
    assert novos(banco, antes) == {}
    assert [c for c in contas_do_item(banco, 902) if c['mes_referencia'] == MES_D(3)] == []      # 5
    assert [c['data_vencimento'] for c in contas_do_item(banco, 901)][2:] == [MES_D(3, 31), MES_D(4, 30)]  # 6
    assert contas_do_item(banco, 904) == []                                                      # 7
    assert len(lancamentos_do_item(banco, 906)) == 4                                             # 8
    assert len(sql(banco, 'select id from public.conta where item_despesa_id = 910 and is_fatura_cartao')) == 2


def test_voltar_para_flask_reativa_o_comportamento_legado(banco):
    """Evidencia para o administrador: devolver o perfil ao Flask reativa a geracao antiga."""
    atribuir(banco, 'PESSOAL')
    gerar_confirmado(banco, dispensar=[{'natureza': 'CONTA', 'item_id': 902, 'competencia': MES}])
    atribuir(banco, 'PESSOAL', 'FLASK')
    antes = snapshot(banco)
    flask(banco, [listar('PESSOAL')])
    criadas = novos(banco, antes)
    assert ('CONTA', 902, MES_D(3)) in criadas  # a dispensa nao e conhecida pelo Flask


# ---------------------------------------------------------------------------
# 9: troca so por administrador, explicita e auditavel
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('usuario', [None, USUARIO_A])
@pytest.mark.parametrize('comando', [
    "select financeiro.definir_gerador_recorrencia(101, 'NOVO', 'x', 'y')",
    "insert into financeiro.gerador_recorrencia (perfil_financeiro_id, gerador, alterado_por, motivo) "
    "values (101, 'NOVO', 'x', 'y')",
    "update financeiro.gerador_recorrencia set gerador = 'NOVO'",
    'select financeiro.gerador_do_perfil(101)',
])
def test_9_navegador_nao_troca_nem_le_o_gerador(banco, usuario, comando):
    with pytest.raises(errors.InsufficientPrivilege, match='permission denied'):
        chamar(banco, usuario, comando)
    assert sql(banco, 'select count(*) as n from financeiro.gerador_recorrencia')[0]['n'] == 0


def test_9_troca_explicita_e_auditada_inclusive_por_sql_direto(banco):
    assert atribuir(banco, 'PESSOAL') == 'Perfil 101: FLASK (padrao) -> NOVO'
    sql(banco, "update financeiro.gerador_recorrencia set gerador = 'FLASK', alterado_por = 'dba', "
               "motivo = 'reversao manual' where perfil_financeiro_id = 101")
    historico = sql(banco, 'select perfil_financeiro_id, gerador_anterior, gerador_novo, alterado_por, motivo, papel_banco '
                           'from financeiro.gerador_recorrencia_historico order by id')
    assert historico == [
        {'perfil_financeiro_id': 101, 'gerador_anterior': None, 'gerador_novo': 'NOVO',
         'alterado_por': 'administrador de teste', 'motivo': 'cenario ficticio', 'papel_banco': 'postgres'},
        {'perfil_financeiro_id': 101, 'gerador_anterior': 'NOVO', 'gerador_novo': 'FLASK',
         'alterado_por': 'dba', 'motivo': 'reversao manual', 'papel_banco': 'postgres'},
    ]


@pytest.mark.parametrize('args,erro', [
    ((101, 'AMBOS', 'adm', 'motivo'), errors.InvalidParameterValue),
    ((101, 'NOVO', ' ', 'motivo'), errors.InvalidParameterValue),
    ((101, 'NOVO', 'adm', ''), errors.InvalidParameterValue),
    ((99999, 'NOVO', 'adm', 'motivo'), errors.InvalidParameterValue),
])
def test_9_troca_invalida_recusada(banco, args, erro):
    with pytest.raises(erro):
        sql(banco, 'select financeiro.definir_gerador_recorrencia(%s, %s, %s, %s)', args)
    with pytest.raises(errors.CheckViolation):
        sql(banco, "insert into financeiro.gerador_recorrencia (perfil_financeiro_id, gerador, alterado_por, motivo) "
                   "values (101, 'AMBOS', 'adm', 'm')")


# ---------------------------------------------------------------------------
# 10: consultas e pagamentos do Flask seguem funcionando no perfil migrado
# ---------------------------------------------------------------------------

def test_10_flask_consulta_e_nao_paga_no_perfil_migrado(banco):
    # FIN-MOVIMENTACOES-1 (D6): no perfil migrado o Flask continua consultando, mas o pagamento de despesa comum
    # passou a ser so do novo aplicativo (antes do D6 o T1 deixava o Flask pagar aqui).
    atribuir(banco, 'PESSOAL')
    movimentos = sql(banco, 'select count(*) as n from public.movimento_financeiro')[0]['n']
    resultado, _ = flask(banco, [listar('PESSOAL', '2027-01'), {'tipo': 'pagar', 'perfil': ID['PESSOAL'], 'conta': 960}])
    assert resultado[0] == {'status': 200, 'ids': [960, 961]}
    assert resultado[1] == {'status': 409}
    conta = sql(banco, 'select status_pagamento from public.conta where id = 960')[0]
    assert conta['status_pagamento'] != 'Pago'
    assert sql(banco, 'select count(*) as n from public.movimento_financeiro')[0]['n'] == movimentos


# ---------------------------------------------------------------------------
# 11: troca durante uma geracao (concorrencia)
# ---------------------------------------------------------------------------

def _em_paralelo(funcao):
    resultado = {}

    def executar():
        try:
            resultado['valor'] = funcao()
        except Exception as exc:  # noqa: BLE001
            resultado['erro'] = exc
        resultado['fim'] = time.monotonic()

    tarefa = threading.Thread(target=executar)
    tarefa.start()
    return tarefa, resultado


def test_11_troca_espera_a_geracao_do_novo_motor_em_andamento(banco):
    atribuir(banco, 'PESSOAL')
    total = previa(banco)['a_gerar']
    conn = psycopg2.connect(banco)
    cur = conn.cursor()
    cur.execute('set local role authenticated')
    cur.execute("select set_config('request.jwt.claims', %s, true)",
                (json.dumps(claims_usuario(USUARIO_A)),))
    cur.execute('select financeiro.gerar_mes(%s, %s, %s)', (ID['PESSOAL'], MES, total))  # transacao aberta
    tarefa, troca = _em_paralelo(lambda: atribuir(banco, 'PESSOAL', 'FLASK'))
    time.sleep(1.5)
    assert 'fim' not in troca  # a troca esta esperando
    commit = time.monotonic()
    conn.commit()
    conn.close()
    tarefa.join(timeout=30)
    assert troca['valor'] == 'Perfil 101: NOVO -> FLASK' and troca['fim'] >= commit
    with pytest.raises(errors.RaiseException, match='sistema atual'):
        gerar(banco, 0)


def test_11_troca_espera_a_geracao_do_flask_em_andamento(banco):
    # Simula o Flask no meio da geracao: trava compartilhada tomada e transacao aberta.
    conn = psycopg2.connect(banco)
    cur = conn.cursor()
    cur.execute('select pg_advisory_xact_lock_shared(20261023, %s)', (ID['PESSOAL'],))
    tarefa, troca = _em_paralelo(lambda: atribuir(banco, 'PESSOAL'))
    time.sleep(1.5)
    assert 'fim' not in troca
    conn.commit()
    conn.close()
    tarefa.join(timeout=30)
    assert troca['valor'] == 'Perfil 101: FLASK (padrao) -> NOVO'


# ---------------------------------------------------------------------------
# 12: erro na verificacao nunca ativa os dois geradores
# ---------------------------------------------------------------------------

def test_12_erro_na_verificacao_bloqueia_a_geracao_do_flask(banco):
    sql(banco, 'alter table financeiro.gerador_recorrencia rename column gerador to gerador_quebrado')
    antes = snapshot(banco)
    resultado, log = flask(banco, [listar('PESSOAL'), listar('EMPRESA')])
    assert [r['status'] for r in resultado] == [200, 200]  # consulta segue funcionando
    assert novos(banco, antes) == {}                       # nenhum perfil gera, nem os do padrao
    assert 'falha ao verificar o gerador' in log and 'geracao bloqueada' in log


def test_12_sem_a_migration_o_flask_mantem_o_comportamento_legado(banco):
    sql(banco, 'drop table financeiro.gerador_recorrencia cascade')
    antes = snapshot(banco)
    flask(banco, [listar('PESSOAL')])
    assert ('CONTA', 901, MES_D(3)) in novos(banco, antes)


def test_12_erro_na_verificacao_do_novo_motor_nao_gera(banco):
    atribuir(banco, 'PESSOAL')
    sql(banco, 'alter table financeiro.gerador_recorrencia rename column gerador to gerador_quebrado')
    antes = snapshot(banco)
    with pytest.raises(psycopg2.Error):
        gerar(banco, 17)
    assert snapshot(banco) == antes


def MES_D(mes, dia=1):  # noqa: N802
    return date(2027, mes, dia)
