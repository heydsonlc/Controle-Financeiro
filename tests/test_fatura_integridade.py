"""
Testes FIN-FATURA-INTEGRIDADE-1 — fatura paga imutavel nas compras e ordem global de travas.

Bancos ISOLADOS e dados FICTICIOS: copia do cluster PostgreSQL descartavel (cenario do
FIN-RECORRENCIA-1: perfil "Pessoal" ficticio 101, Cartao Teste 910, recorrencia "Streaming" 906 no
cartao) e arquivos SQLite temporarios. Nunca o gastos.db nem o Supabase.

Concorrencia efetiva: cada operacao do Flask roda num processo proprio (conexao e transacao
proprias) que para numa barreira antes do commit, com as travas ja tomadas; o novo aplicativo e
chamado como `authenticated` em outra conexao. O teste confere que a segunda operacao ESPERA a trava
(pg_stat_activity) antes de liberar a primeira.
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
    ID,
    PG_BIN,
    ROOT,
    USUARIO_A,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    gerar,
    previa,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
from psycopg2 import errors  # noqa: E402

pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PERFIL, CARTAO, STREAMING, MORADIA, ASSINATURAS = 101, 910, 906, 951, 952
EMAIL, SENHA = 'flask.integridade@teste.local', 'Senha-ficticia-integridade-2026'
D = date

_WORKER = r'''
import json, sys, time
from datetime import date
from decimal import Decimal
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
    escreveu, feito = [], []
    event.listen(db.session, 'after_flush', lambda *a: escreveu.append(1))
    commit_original = db.session.commit
    def commit_pausado():
        if escreveu and not feito:
            feito.append(1)
            esperar('pausa')
        return commit_original()
    db.session.commit = commit_pausado

def lanc(d):
    d = dict(d)
    d['data_compra'] = date.fromisoformat(d['data_compra'])
    d['mes_fatura'] = date.fromisoformat(d['mes_fatura'])
    d['valor'] = Decimal(d['valor'])
    return d

with app.app_context():
    with app.test_request_context():
        session['perfil_financeiro_id'] = cfg['perfil']
        if cfg.get('pausa'):
            instalar_pausa()
        if cfg.get('pausa_segunda_fatura'):
            # Para logo DEPOIS da primeira trava de fatura. Sem a ordem global (codigo anterior), o Flask
            # segura so a 1a fatura e ainda vai pedir a 2a: e o ponto exato de um ciclo de espera. Com ela,
            # o Flask ja segura o cartao e todas as faturas da compra.
            from backend.services import trava_financeira
            from backend.models import Conta
            original_tv = trava_financeira.travar
            vistas = []
            def travar_pausado(modelo, ids):
                linhas = original_tv(modelo, ids)
                if modelo is Conta and not vistas:
                    vistas.append(1)
                    esperar('pausa')
                return linhas
            trava_financeira.travar = travar_pausado
            import backend.services.cartao_service as cs
            cs.travar = travar_pausado
            cs.travar_um = lambda modelo, id_: (travar_pausado(modelo, [id_]) or [None])[0]
        if cfg.get('falhar'):
            from backend.services.cartao_service import CartaoService
            original = CartaoService.registrar_desvio
            def falha(lancamento, mes_original, exigir_coluna=False):
                if lancamento.numero_parcela == cfg['falhar']:
                    raise RuntimeError('falha simulada na parcela')
                return original(lancamento, mes_original, exigir_coluna)
            CartaoService.registrar_desvio = staticmethod(falha)
        resultado = None
        try:
            if cfg['acao'] == 'compra':
                from backend.services.cartao_service import CartaoService
                l, f = CartaoService.adicionar_lancamento(lanc(cfg['dados']))
                resultado = {'compra_id': l.compra_id}
            elif cfg['acao'] == 'importar':
                from backend.services.importacao_cartao_service import ImportacaoCartaoService
                r = ImportacaoCartaoService.persistir_lancamentos([lanc(x) for x in cfg['lancamentos']])
                resultado = {'inseridos': r['inseridos'], 'duplicados': r['duplicados'],
                             'erros': [e['erro'] for e in r['erros']]}
            elif cfg['acao'] == 'recorrencia':
                from backend.routes.despesas import gerar_execucao_despesa_recorrente
                criados = gerar_execucao_despesa_recorrente(cfg['item'], meses_futuros=cfg['meses'],
                                                            mes_referencia=date.fromisoformat(cfg['mes']))
                db.session.commit()  # a funcao nao confirma: o chamador controla a transacao
                resultado = {'criados': len(criados)}
            elif cfg['acao'] == 'preparar_sqlite':
                from backend.models import (Usuario, PerfilFinanceiro, Categoria, ItemDespesa, ConfigAgregador,
                                            LancamentoAgregado)
                db.create_all()
                db.session.add(PerfilFinanceiro(id=cfg['perfil'], nome='Pessoal', tipo='PESSOAL', cor='#2563eb',
                                                ativo=True, padrao=True, avatar='PE'))
                db.session.add(Categoria(id=951, nome='Moradia T', cor='#2563eb', ativo=True))
                db.session.add(ItemDespesa(id=910, perfil_financeiro_id=cfg['perfil'], categoria_id=951,
                                           nome='Cartao Teste', tipo='Agregador', ativo=True, recorrente=False))
                db.session.add(ConfigAgregador(item_despesa_id=910, dia_fechamento=25, dia_vencimento=10))
                db.session.add(ItemDespesa(id=906, perfil_financeiro_id=cfg['perfil'], categoria_id=951,
                                           nome='Streaming', tipo='Simples', ativo=True, recorrente=True,
                                           tipo_recorrencia='mensal', data_vencimento=date(2027, 1, 31),
                                           valor=Decimal('39.90'), meio_pagamento='cartao', cartao_id=910))
                db.session.commit()
                if cfg.get('sem_coluna'):  # banco como o gastos.db antes da migration local
                    db.session.execute(db.text('alter table lancamento_agregado drop column mes_fatura_original'))
                    db.session.commit()
                resultado = {'ok': True}
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            resultado = {'erro': f'{type(exc).__name__}: {exc}'}
        print('RESULTADO ' + json.dumps(resultado))
'''


class Flask:
    """Processo Flask real (conexao e transacao proprias)."""

    def __init__(self, url, pasta, nome, **cfg):
        env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': url}
        env.pop('FLASK_ENV', None)
        self.pasta, self.nome = Path(pasta), nome
        self.saida, self.erro = self.pasta / f'{nome}.out', self.pasta / f'{nome}.err'
        with open(self.saida, 'w') as saida, open(self.erro, 'w') as erro:
            self.processo = subprocess.Popen(
                [sys.executable, '-c', _WORKER, json.dumps({'pasta': str(pasta), 'nome': nome, 'perfil': PERFIL, **cfg})],
                cwd=ROOT, env=env, stdout=saida, stderr=erro, stdin=subprocess.DEVNULL)

    def log(self):
        return self.erro.read_text(errors='replace')

    def resultado(self):
        self.processo.wait(timeout=180)
        assert self.processo.returncode == 0, self.erro.read_text(errors='replace')[-2500:]
        linhas = self.saida.read_text(errors='replace').splitlines()
        return json.loads([linha for linha in linhas if linha.startswith('RESULTADO ')][-1][10:])

    def pausado(self):
        aguardar(self.pasta, [f'{self.nome}_pausa'], [self])

    def liberar(self):
        liberar(self.pasta, 'pausa')


def compra(descricao, mes, valor='100.00', parcelas=1, categoria=MORADIA):
    return {'cartao_id': CARTAO, 'descricao': descricao, 'valor': valor, 'total_parcelas': parcelas,
            'data_compra': mes[:8] + '05', 'mes_fatura': mes, 'categoria_id': categoria}


def importada(descricao, mes, valor='50.00', numero=1, total=1, compra_id='imp-1'):
    return {'cartao_id': CARTAO, 'descricao': descricao, 'descricao_original': descricao,
            'descricao_original_normalizada': descricao, 'descricao_exibida': descricao, 'valor': valor,
            'data_compra': mes[:8] + '03', 'mes_fatura': mes, 'numero_parcela': numero, 'total_parcelas': total,
            'categoria_id': MORADIA, 'compra_id': compra_id, 'is_importado': True, 'origem_importacao': 'csv'}


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def base(cluster):  # noqa: F811
    dsn = cluster.dsn()
    sql(dsn, "update public.perfil_financeiro set avatar = upper(left(nome, 2))")  # o Flask nao grava na leitura
    sql(dsn, 'update public.config_agregador set dia_vencimento = 10 where item_despesa_id = %s', (CARTAO,))
    return dsn


@pytest.fixture
def pg(base, cluster, tmp_path):  # noqa: F811
    return copiar(cluster), tmp_path


def fatura(dsn, mes, pagar=False):
    """Fatura FICTICIA do cartao no mes (criada se faltar); pagar=True simula o pagamento do Flask."""
    linhas = sql(dsn, 'select id from public.conta where is_fatura_cartao and item_despesa_id = %s '
                      'and cartao_competencia = %s', (CARTAO, mes))
    if not linhas:
        linhas = sql(dsn, "insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, "
                          "valor, valor_planejado, valor_executado, data_vencimento, status_pagamento, is_fatura_cartao, "
                          "cartao_competencia, estouro_orcamento, debito_automatico, status_fatura) values "
                          "(%s, %s, %s, 'Fatura teste', 0, 0, 0, %s, 'Pendente', true, %s, false, false, 'ABERTA') "
                          "returning id", (PERFIL, CARTAO, mes, mes[:8] + '10', mes))
    if pagar:
        sql(dsn, "update public.conta set status_pagamento = 'Pago', data_pagamento = %s, valor = valor_executado "
                 "where id = %s", (mes[:8] + '10', linhas[0]['id']))
    return linhas[0]['id']


def compras(dsn, filtro, params=()):
    return sql(dsn, f'select descricao, numero_parcela, mes_fatura, mes_fatura_original, valor from '
                    f'public.lancamento_agregado where {filtro} order by descricao, numero_parcela, id', params)


def md5_pagas(dsn):
    return sql(dsn, "select coalesce(md5(string_agg(t::text, '|' order by id)), '') as h from public.conta t "
                    "where is_fatura_cartao and status_pagamento = 'Pago'")[0]['h']


def sem_duplicidade(dsn):
    return sql(dsn, "select count(*) as n from (select 1 from public.conta where is_fatura_cartao "
                    "group by item_despesa_id, cartao_competencia having count(*) > 1) d")[0]['n'] == 0


def financeiro(dsn):
    return sql(dsn, "select (select count(*) from public.movimento_financeiro) as m, "
                    "(select md5(string_agg(t::text, '|' order by id)) from public.conta_bancaria t) as b")[0]


# 1. Recorrencia em competencia cuja fatura ja esta paga — novo motor e Flask
def test_recorrencia_do_novo_motor_nao_entra_em_fatura_paga(pg):
    d, _ = pg
    atribuir(d, 'PESSOAL')
    fatura(d, '2027-03-01', pagar=True)
    antes = (md5_pagas(d), financeiro(d))
    gerar(d, previa(d)['a_gerar'])  # gera 03 e 04/2027
    assert compras(d, 'item_despesa_id = %s and mes_fatura >= %s', (STREAMING, D(2027, 3, 1))) == [
        {'descricao': 'Streaming', 'numero_parcela': 1, 'mes_fatura': D(2027, 4, 1), 'mes_fatura_original': D(2027, 3, 1),
         'valor': Decimal('39.90')},
        {'descricao': 'Streaming', 'numero_parcela': 1, 'mes_fatura': D(2027, 4, 1), 'mes_fatura_original': None,
         'valor': Decimal('39.90')}]
    assert previa(d)['a_gerar'] == 0  # identidade da competencia: nao gera de novo
    assert (md5_pagas(d), financeiro(d)) == antes and sem_duplicidade(d)


def test_recorrencia_do_flask_nao_entra_em_fatura_paga(pg):
    d, p = pg
    fatura(d, '2027-03-01', pagar=True)
    antes = md5_pagas(d)
    for i in (1, 2):  # a segunda chamada nao duplica
        r = Flask(d, p, f'rec{i}', acao='recorrencia', item=STREAMING, meses=2, mes='2027-03-01').resultado()
        assert 'erro' not in r
    linhas = compras(d, 'item_despesa_id = %s and mes_fatura >= %s', (STREAMING, D(2027, 3, 1)))
    assert [(x['mes_fatura'], x['mes_fatura_original']) for x in linhas] == \
        [(D(2027, 4, 1), D(2027, 3, 1)), (D(2027, 4, 1), None)]
    assert md5_pagas(d) == antes and sem_duplicidade(d)


# 2 e 3. Importacao para fatura paga; importacao repetida
def test_importacao_desvia_de_fatura_paga_e_reimportacao_nao_duplica(pg):
    d, p = pg
    fatura(d, '2028-02-01', pagar=True)
    antes = md5_pagas(d)
    lote = [importada('Loja A', '2028-02-01', compra_id='imp-a'), importada('Loja B', '2028-03-01', compra_id='imp-b'),
            importada('Parcelado C', '2028-02-01', '30.00', 1, 2, 'imp-c'),
            importada('Parcelado C', '2028-03-01', '30.00', 2, 2, 'imp-c')]
    r1 = Flask(d, p, 'imp1', acao='importar', lancamentos=lote).resultado()
    r2 = Flask(d, p, 'imp2', acao='importar', lancamentos=lote).resultado()
    assert (r1['inseridos'], r1['erros'], r2['inseridos'], r2['duplicados']) == (4, [], 0, 4)
    assert [(x['descricao'], x['numero_parcela'], x['mes_fatura'], x['mes_fatura_original'])
            for x in compras(d, "descricao in ('Loja A', 'Loja B', 'Parcelado C')")] == [
        ('Loja A', 1, D(2028, 3, 1), D(2028, 2, 1)),
        ('Loja B', 1, D(2028, 3, 1), None),
        ('Parcelado C', 1, D(2028, 3, 1), D(2028, 2, 1)),
        ('Parcelado C', 2, D(2028, 4, 1), D(2028, 3, 1))]  # parcelas seguem uma por fatura
    assert md5_pagas(d) == antes and sem_duplicidade(d)


def test_importacoes_simultaneas_do_mesmo_arquivo_nao_duplicam(pg):
    d, p = pg
    lote = [importada('Loja D', '2028-05-01', compra_id='imp-d')]
    primeira = Flask(d, p, 'imp1', acao='importar', lancamentos=lote, pausa=True)
    primeira.pausado()
    segunda = Flask(d, p, 'imp2', acao='importar', lancamentos=lote)
    aguardar_bloqueio(d)  # a segunda espera o cartao
    primeira.liberar()
    r1, r2 = primeira.resultado(), segunda.resultado()
    assert (r1['inseridos'], r2['inseridos'], r2['duplicados']) == (1, 0, 1)
    assert len(compras(d, "descricao = 'Loja D'")) == 1


# 4. Compra parcelada atravessando fatura paga — Flask e novo aplicativo com o mesmo resultado
def test_parcelada_atravessando_fatura_paga_igual_no_flask_e_no_novo(pg):
    d, p = pg
    fatura(d, '2028-07-01', pagar=True)
    antes = md5_pagas(d)
    assert 'erro' not in Flask(d, p, 'f', acao='compra', dados=compra('Flask 3x', '2028-06-01', '90.00', 3)).resultado()
    chamar(d, USUARIO_A, 'select financeiro.criar_compra(%s, %s::jsonb, gen_random_uuid())',
           (PERFIL, json.dumps(compra('Novo 3x', '2028-06-01', '90.00', 3))))
    flask_ = [(x['numero_parcela'], x['mes_fatura'], x['mes_fatura_original'], x['valor'])
              for x in compras(d, "descricao = 'Flask 3x'")]
    novo = [(x['numero_parcela'], x['mes_fatura'], x['mes_fatura_original'], x['valor'])
            for x in compras(d, "descricao = 'Novo 3x'")]
    assert flask_ == novo == [(1, D(2028, 6, 1), None, Decimal('30.00')),
                              (2, D(2028, 8, 1), D(2028, 7, 1), Decimal('30.00')),
                              (3, D(2028, 9, 1), D(2028, 8, 1), Decimal('30.00'))]
    assert md5_pagas(d) == antes and sem_duplicidade(d)


# 6. Recorrencia (novo motor) concorrente com compra do Flask
def test_geracao_espera_a_compra_do_flask_no_mesmo_cartao(pg):
    d, p = pg
    atribuir(d, 'PESSOAL')
    total = previa(d)['a_gerar']
    compra_flask = Flask(d, p, 'c', acao='compra', dados=compra('Compra marco', '2027-03-01', '80.00', 2), pausa=True)
    compra_flask.pausado()  # segura o cartao e as faturas de 03 e 04/2027
    tarefa, geracao = em_thread(lambda: gerar(d, total))
    aguardar_bloqueio(d)
    compra_flask.liberar()
    assert 'erro' not in compra_flask.resultado()
    tarefa.join(120)
    # A compra criou as faturas de 03 e 04 antes: a previa mudou e a geracao pede nova confirmacao
    # (nada gravado); confirmada de novo, gera sem duplicar.
    if 'erro' in geracao:
        assert 'previa mudou' in str(geracao['erro'])
        gerar(d, previa(d)['a_gerar'])
    assert sem_duplicidade(d)
    assert len(compras(d, "descricao = 'Compra marco'")) == 2
    assert len(compras(d, 'item_despesa_id = %s and mes_fatura in (%s, %s)', (STREAMING, D(2027, 3, 1), D(2027, 4, 1)))) == 2


# 7. Importacao concorrente com a geracao
def test_importacao_e_geracao_simultaneas(pg):
    d, p = pg
    atribuir(d, 'PESSOAL')
    fatura(d, '2027-03-01')
    fatura(d, '2027-04-01')  # as faturas ja existem: a previa nao muda por causa da importacao
    total = previa(d)['a_gerar']
    imp = Flask(d, p, 'imp', acao='importar', lancamentos=[importada('Loja marco', '2027-03-01')], pausa=True)
    imp.pausado()
    tarefa, geracao = em_thread(lambda: gerar(d, total))
    aguardar_bloqueio(d)
    imp.liberar()
    assert imp.resultado()['inseridos'] == 1
    tarefa.join(120)
    assert 'erro' not in geracao, geracao
    assert sem_duplicidade(d)
    assert len(compras(d, "descricao = 'Loja marco'")) == 1
    assert len(compras(d, 'item_despesa_id = %s and mes_fatura in (%s, %s)', (STREAMING, D(2027, 3, 1), D(2027, 4, 1)))) == 2


# 8 e 9. Operacoes com varias faturas em ordens opostas (ids x meses invertidos): sem deadlock
def test_ordens_opostas_de_faturas_sem_deadlock(pg):
    d, p = pg
    novembro = fatura(d, '2028-11-01')  # criada antes: id MENOR que a de outubro
    outubro = fatura(d, '2028-10-01')   # id MAIOR, mes anterior
    assert novembro < outubro
    r = chamar(d, USUARIO_A, 'select financeiro.criar_compra(%s, %s::jsonb, gen_random_uuid())',
               (PERFIL, json.dumps(compra('Existente 2x', '2028-10-01', '60.00', 2))))
    versao = chamar(d, USUARIO_A, 'select financeiro.compra_para_edicao(%s, %s)', (PERFIL, r['lancamentos'][0]))['versao']
    # Flask: compra 2x em 10 e 11; para JA com uma fatura travada e antes de travar a outra.
    flask_ = Flask(d, p, 'c', acao='compra', dados=compra('Flask 2x', '2028-10-01', '40.00', 2),
                   pausa_segunda_fatura=True)
    flask_.pausado()
    # Novo aplicativo: exclusao da compra 2x (faturas por id). Sem a ordem global (cartao antes), ele
    # travaria uma fatura e esperaria a outra, enquanto o Flask esperaria a primeira: ciclo.
    tarefa, exclusao = em_thread(lambda: chamar(d, USUARIO_A, 'select financeiro.excluir_compra(%s, %s, %s)',
                                                (PERFIL, r['lancamentos'][0], versao)))
    aguardar_bloqueio(d)
    flask_.liberar()
    assert 'erro' not in flask_.resultado()
    tarefa.join(120)
    assert 'erro' not in exclusao, exclusao  # nenhum deadlock
    assert exclusao['valor']['excluidas'] == 2 and len(compras(d, "descricao = 'Flask 2x'")) == 2


def test_recalculos_de_varias_faturas_simultaneos(pg):
    """Parcelas futuras (Flask, varias faturas) x edicao parcelada (novo aplicativo, varias faturas)."""
    d, p = pg
    r = chamar(d, USUARIO_A, 'select financeiro.criar_compra(%s, %s::jsonb, gen_random_uuid())',
               (PERFIL, json.dumps(compra('Parcelada 4x', '2029-01-01', '400.00', 4))))
    outra = chamar(d, USUARIO_A, 'select financeiro.criar_compra(%s, %s::jsonb, gen_random_uuid())',
                   (PERFIL, json.dumps(compra('Outra 3x', '2029-01-01', '300.00', 3))))
    versao = chamar(d, USUARIO_A, 'select financeiro.compra_para_edicao(%s, %s)', (PERFIL, outra['lancamentos'][0]))['versao']
    tarefa1, a = em_thread(lambda: chamar(d, USUARIO_A, 'select financeiro.editar_compra(%s, %s, %s, %s::jsonb)',
                                          (PERFIL, outra['lancamentos'][0], versao, json.dumps({'descricao': 'Outra'}))))
    tarefa2, b = em_thread(lambda: Flask(d, p, 'c', acao='compra', dados=compra('Nova 4x', '2029-01-01', '40.00', 4)).resultado())
    tarefa1.join(120)
    tarefa2.join(180)
    assert 'erro' not in a and 'erro' not in b and 'erro' not in b.get('valor', {})
    for mes in ('2029-01-01', '2029-02-01', '2029-03-01', '2029-04-01'):
        f = sql(d, 'select valor_executado from public.conta where is_fatura_cartao and item_despesa_id = %s '
                   'and cartao_competencia = %s', (CARTAO, mes))[0]['valor_executado']
        soma = sql(d, 'select sum(valor) as s from public.lancamento_agregado where cartao_id = %s and mes_fatura = %s',
                   (CARTAO, mes))[0]['s']
        assert f == soma, (mes, f, soma)  # recalculo final ve todas as compras
    assert sem_duplicidade(d)


# 10. Rollback em caso de erro no meio da compra
def test_erro_no_meio_da_compra_nao_deixa_parcelas_nem_altera_pagas(pg):
    d, p = pg
    fatura(d, '2029-08-01', pagar=True)
    antes = (md5_pagas(d), financeiro(d))
    r = Flask(d, p, 'f', acao='compra', dados=compra('Com falha', '2029-07-01', '90.00', 3), falhar=2).resultado()
    assert 'falha simulada' in r['erro']
    assert compras(d, "descricao = 'Com falha'") == []
    assert (md5_pagas(d), financeiro(d)) == antes and sem_duplicidade(d)


# 11-13. Fatura FECHADA continua elegivel (estado proprio); paga intacta; movimentos e saldos intactos.
# FIN-CARTOES-FECHAMENTO-1 (D6): so recebe a compra com a confirmacao explicita do total visto; sem ela nada e gravado.
def test_fatura_fechada_nao_e_tratada_como_paga(pg):
    d, p = pg
    fechada = fatura(d, '2029-10-01')
    sql(d, "update public.conta set status_fatura = 'FECHADA', valor_consolidado = 0 where id = %s", (fechada,))
    antes = financeiro(d)
    sem = Flask(d, p, 'f', acao='compra', dados=compra('Na fechada', '2029-10-01')).resultado()
    assert sem['erro'].startswith('ConfirmacaoConsolidadaNecessaria')
    assert compras(d, "descricao = 'Na fechada'") == []
    confirmada = {**compra('Na fechada', '2029-10-01'),
                  'confirmar_consolidadas': [{'fatura_id': fechada, 'total_consolidado': '0.00'}]}
    assert 'erro' not in Flask(d, p, 'g', acao='compra', dados=confirmada).resultado()
    assert compras(d, "descricao = 'Na fechada'")[0]['mes_fatura'] == D(2029, 10, 1)  # nao desviada: nao e paga
    assert sql(d, 'select status_fatura, valor_consolidado from public.conta where id = %s', (fechada,)) == \
        [{'status_fatura': 'FECHADA', 'valor_consolidado': Decimal('100.00')}]
    assert financeiro(d) == antes


# ---------------------------------------------------------------------------
# 14. SQLite (arquivos temporarios; nunca o gastos.db)
# ---------------------------------------------------------------------------

def _sqlite(caminho, comando, params=()):
    import sqlite3
    with sqlite3.connect(caminho) as conn:
        return conn.execute(comando, params).fetchall()


@pytest.fixture(params=['migrado', 'sem_coluna'])
def sqlite(request, tmp_path):
    caminho = tmp_path / 'integridade.db'
    url = f'sqlite:///{caminho.as_posix()}'
    assert Flask(url, tmp_path, 'prep', acao='preparar_sqlite', sem_coluna=request.param == 'sem_coluna').resultado()['ok']
    _sqlite(caminho, "insert into conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, "
                     "valor_planejado, valor_executado, data_vencimento, status_pagamento, is_fatura_cartao, "
                     "cartao_competencia, estouro_orcamento, debito_automatico, status_fatura) values "
                     "(101, 910, '2028-02-01', 'Fatura paga', 0, 0, 0, '2028-02-10', 'Pago', 1, '2028-02-01', 0, 0, 'ABERTA')")
    return url, caminho, tmp_path, request.param


def test_sqlite_compra_recorrencia_e_importacao_respeitam_fatura_paga(sqlite):
    url, caminho, p, modo = sqlite
    assert 'erro' not in Flask(url, p, 'c', acao='compra', dados=compra('Compra', '2028-02-01')).resultado()
    assert 'erro' not in Flask(url, p, 'r', acao='recorrencia', item=STREAMING, meses=1, mes='2028-02-01').resultado()
    imp = Flask(url, p, 'i', acao='importar', lancamentos=[importada('Importada', '2028-02-01')]).resultado()
    meses = dict(_sqlite(caminho, "select descricao, mes_fatura from lancamento_agregado"))
    assert meses['Compra'] == meses['Streaming'] == '2028-03-01'  # nenhuma na fatura paga
    if modo == 'migrado':
        assert imp['inseridos'] == 1 and meses['Importada'] == '2028-03-01'
        assert set(_sqlite(caminho, 'select mes_fatura_original from lancamento_agregado')) == {('2028-02-01',)}
    else:  # banco sem a coluna (como o gastos.db hoje): desvio auditado nas observacoes; importacao recusada
        assert imp['inseridos'] == 0 and 'migration pendente' in imp['erros'][0] and 'Importada' not in meses
        obs = dict(_sqlite(caminho, "select descricao, observacoes from lancamento_agregado"))
        assert '[Fatura de 02/2028 paga: lancada em 03/2028]' in obs['Compra']
        assert '[Fatura de 02/2028 paga: lancada em 03/2028]' in obs['Streaming']
    assert _sqlite(caminho, "select count(*) from lancamento_agregado where mes_fatura = '2028-02-01'") == [(0,)]
