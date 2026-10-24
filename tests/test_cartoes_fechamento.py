"""
Testes FIN-CARTOES-FECHAMENTO-1 — competencia sugerida pelo fechamento do cartao, ajuste manual, parcelamento,
fatura consolidada (D6) e compatibilidade Flask x PostgreSQL.

A. Calendario: CartaoService.competencia_da_compra (Python) e financeiro.competencia_da_compra (SQL), casos
   do contrato e uma grade de datas identica nas duas.
B-D. Cluster PostgreSQL descartavel do FIN-RECORRENCIA-1 (copia por teste), com o novo aplicativo como
   `authenticated` (usuario A, gestor do Pessoal) e o Flask real (HTTP, mesmo banco). Cartoes ficticios
   criados aqui; nunca o gastos.db.
E. Alembic c7e2a9d4b8f3 so em bancos ficticios (SQLite temporario e PostgreSQL descartavel).
F. Vencimento 29-31 no Flask (app de teste, SQLite em memoria).
"""
import json
import re
import sqlite3
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.services.cartao_service import CartaoService
from tests.test_supabase_cartoes import MORADIA, banco, cartoes, edicao, fatura, pagar, parcelas, rpc  # noqa: F401
from tests.test_supabase_despesas import flask
from tests.test_supabase_recorrencia import (  # noqa: F401
    ID, PG_BIN, ROOT, USUARIO_A, USUARIO_B, chamar, cluster, copiar, sql,
)

psycopg2 = pytest.importorskip('psycopg2')
from psycopg2 import errors  # noqa: E402

D = date
pg = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')


# ---------------------------------------------------------------------------
# A. Calendario (regra pura)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('data, fechamento, vencimento, regra, esperado', [
    # 1-4. Antes, no dia (padrao: proximo ciclo; alternativa: ciclo atual) e depois do fechamento (contrato)
    ('2026-10-24', 25, 5, 'PROXIMO', D(2026, 11, 1)),
    ('2026-10-25', 25, 5, 'PROXIMO', D(2026, 12, 1)),
    ('2026-10-25', 25, 5, 'ATUAL', D(2026, 11, 1)),
    ('2026-10-26', 25, 5, 'PROXIMO', D(2026, 12, 1)),
    # 5. Fechamento em 28, 29, 30 e 31 (dias curtos viram o ultimo dia do mes)
    ('2027-02-28', 28, 8, 'PROXIMO', D(2027, 4, 1)),
    ('2027-02-28', 29, 9, 'PROXIMO', D(2027, 4, 1)),   # 29/02 nao existe em 2027: fecha 28/02
    ('2027-04-30', 30, 10, 'PROXIMO', D(2027, 6, 1)),
    ('2027-04-30', 31, 10, 'PROXIMO', D(2027, 6, 1)),  # 31/04 nao existe: fecha 30/04
    ('2027-04-30', 31, 10, 'ATUAL', D(2027, 5, 1)),
    ('2027-05-30', 31, 10, 'PROXIMO', D(2027, 6, 1)),
    # 6-7. Fevereiro comum e bissexto
    ('2027-02-27', 31, 10, 'PROXIMO', D(2027, 3, 1)),
    ('2028-02-28', 29, 9, 'PROXIMO', D(2028, 3, 1)),   # 2028 e bissexto: fecha 29/02
    ('2028-02-29', 29, 9, 'PROXIMO', D(2028, 4, 1)),
    # 8. Virada de ano
    ('2026-12-24', 25, 5, 'PROXIMO', D(2027, 1, 1)),
    ('2026-12-26', 25, 5, 'PROXIMO', D(2027, 2, 1)),
    ('2027-01-31', 31, 10, 'PROXIMO', D(2027, 3, 1)),
    # 9. Vencimento no mesmo mes do fechamento (dia maior) e no seguinte (dia menor)
    ('2031-05-02', 3, 10, 'PROXIMO', D(2031, 5, 1)),
    ('2031-05-12', 3, 10, 'PROXIMO', D(2031, 6, 1)),
    # 11. Fechamento igual ao vencimento (valido quando confirmado): vence no mes seguinte ao fechamento
    ('2026-10-05', 10, 10, 'PROXIMO', D(2026, 11, 1)),
    ('2026-10-10', 10, 10, 'PROXIMO', D(2026, 12, 1)),
])
def test_calendario_casos_do_contrato(data, fechamento, vencimento, regra, esperado):
    assert CartaoService.competencia_da_compra(data, fechamento, vencimento, regra) == esperado


@pytest.mark.parametrize('data, fechamento, vencimento, regra', [
    ('2027-02-15', 29, 30, 'PROXIMO'),   # fevereiro: 29 e 30 viram 28 e o vencimento cairia no fechamento
    ('2028-02-15', 29, 30, 'PROXIMO'),   # bissexto: 30 vira 29 = fechamento
    ('2027-02-15', 30, 31, 'PROXIMO'),
    ('2026-10-24', 0, 5, 'PROXIMO'),     # configuracao invalida
    ('2026-10-24', 25, 32, 'PROXIMO'),
    ('2026-10-24', 25, 5, 'OUTRA'),
])
def test_calendario_ciclo_ambiguo_ou_invalido_nao_sugere(data, fechamento, vencimento, regra):
    assert CartaoService.competencia_da_compra(data, fechamento, vencimento, regra) is None


def test_ciclo_ambiguo_so_no_mes_afetado():
    # 29/30: em janeiro o ciclo e claro (fecha 29, vence 30); so fevereiro fica sem sugestao.
    assert CartaoService.competencia_da_compra('2027-01-15', 29, 30, 'PROXIMO') == D(2027, 1, 1)
    assert CartaoService.competencia_da_compra('2027-03-15', 29, 30, 'PROXIMO') == D(2027, 3, 1)


def test_data_civil_perto_da_meia_noite_nao_muda_o_dia():
    # 12. 26/10 02:30 UTC = 25/10 23:30 em Brasilia: dia do fechamento, nao o dia seguinte.
    instante = datetime(2026, 10, 26, 2, 30, tzinfo=timezone.utc)
    assert CartaoService.data_civil(instante) == D(2026, 10, 25)
    assert CartaoService.competencia_da_compra(instante, 25, 5, 'ATUAL') == D(2026, 11, 1)
    assert CartaoService.competencia_da_compra(instante.date(), 25, 5, 'ATUAL') == D(2026, 12, 1)  # a data UTC erraria
    # 25/10 02:30 UTC = 24/10 23:30 em Brasilia: ainda antes do fechamento
    assert CartaoService.competencia_da_compra(datetime(2026, 10, 25, 2, 30, tzinfo=timezone.utc), 25, 5, 'PROXIMO') \
        == D(2026, 11, 1)
    # Texto AAAA-MM-DD e date valem como data civil, sem conversao de fuso
    assert CartaoService.data_civil('2026-10-25') == D(2026, 10, 25)
    assert CartaoService.data_civil(D(2026, 10, 25)) == D(2026, 10, 25)


@pg
def test_grade_identica_no_flask_e_no_postgresql(banco):  # noqa: F811
    inicio, fim = D(2026, 11, 1), D(2028, 4, 30)  # inclui dois anos-novos e o fevereiro bissexto de 2028
    fechamentos = (1, 3, 5, 10, 15, 20, 25, 27, 28, 29, 30, 31)
    vencimentos = (1, 5, 8, 10, 15, 20, 25, 28, 29, 30, 31)
    linhas = sql(banco, """
        select d::date as data, f, v, r, financeiro.competencia_da_compra(d::date, f, v, r) as comp
          from generate_series(%s::date, %s::date, interval '1 day') d,
               unnest(%s::int[]) f, unnest(%s::int[]) v, unnest(array['ATUAL', 'PROXIMO']) r""",
                 (inicio, fim, list(fechamentos), list(vencimentos)))
    divergentes = [x for x in linhas
                   if CartaoService.competencia_da_compra(x['data'], x['f'], x['v'], x['r']) != x['comp']]
    assert len(linhas) == ((fim - inicio).days + 1) * len(fechamentos) * len(vencimentos) * 2
    assert divergentes == []
    assert sum(1 for x in linhas if x['comp'] is None) > 0  # a grade cobre ciclos ambiguos


# ---------------------------------------------------------------------------
# Auxiliares (novo aplicativo e Flask)
# ---------------------------------------------------------------------------

def novo_cartao(dsn, nome='Visa Fechamento', fechamento=25, vencimento=5, confirmado=True, regra='PROXIMO',
                perfil='PESSOAL', usuario=USUARIO_A):
    return rpc(dsn, 'criar_cartao', ID[perfil], {'nome': nome, 'dia_fechamento': fechamento, 'dia_vencimento': vencimento,
                                                'fechamento_confirmado': confirmado, 'compra_no_fechamento': regra},
               str(uuid.uuid4()), usuario=usuario)['cartao_id']


def compra(cartao, data='2029-10-26', valor='90.00', parcelas_=1, mes=None, descricao='Compra', **extra):
    dados = {'cartao_id': cartao, 'descricao': descricao, 'valor': valor, 'total_parcelas': parcelas_,
             'data_compra': data, 'categoria_id': MORADIA, **extra}
    if mes:
        dados['mes_fatura'] = mes
    return dados


def criar(dsn, dados, chave=None, usuario=USUARIO_A):
    return rpc(dsn, 'criar_compra', ID['PESSOAL'], dados, chave or str(uuid.uuid4()), usuario=usuario)


def previa(dsn, dados):
    return rpc(dsn, 'previa_compra', ID['PESSOAL'], dados)


def linhas(dsn, compra_id):
    return [(x['numero_parcela'], x['mes_fatura'], x['mes_fatura_original'], x['mes_fatura_sugerido'], x['valor'],
             x['data_compra'])
            for x in parcelas(dsn, compra_id)]


def consolidar(dsn, cartao, mes):
    """Como a consolidacao do Flask: FECHADA com valor_consolidado = executado."""
    sql(dsn, "update public.conta set status_fatura = 'FECHADA', valor_consolidado = valor_executado, "
             "data_consolidacao = now() where is_fatura_cartao and item_despesa_id = %s and cartao_competencia = %s",
        (cartao, mes))
    return fatura(dsn, cartao, mes)


def auditoria(dsn, fatura_id=None):
    filtro = 'where fatura_id = %s' if fatura_id else ''
    return sql(dsn, f'select * from public.fatura_consolidada_inclusao {filtro} order by id', (fatura_id,) if fatura_id else ())


def md5_compras(dsn):
    return sql(dsn, "select coalesce(md5(string_agg(t::text, '|' order by id)), '') as h from public.lancamento_agregado t")[0]['h']


def confirmacao(faturas):
    return [{'fatura_id': f['fatura_id'], 'total_consolidado': str(f['total_consolidado'])} for f in faturas]


# ---------------------------------------------------------------------------
# B. Parcelamento
# ---------------------------------------------------------------------------

@pg
def test_primeira_parcela_na_competencia_sugerida_e_seguintes_mensais_atravessando_dezembro(banco):  # noqa: F811
    c = novo_cartao(banco)
    p = previa(banco, compra(c, '2029-10-26', '100.00', 3))
    assert p['sugestao']['situacao'] == 'SUGERIDA' and p['sugestao']['competencia'] == '2029-12-01'
    assert p['sugestao']['vencimento'] == '2029-12-05' and p['sugestao']['fechamento'] == '2029-11-25'
    r = criar(banco, compra(c, '2029-10-26', '100.00', 3))
    assert linhas(banco, r['compra_id']) == [
        (1, D(2029, 12, 1), None, D(2029, 12, 1), Decimal('33.34'), D(2029, 10, 26)),
        (2, D(2030, 1, 1), None, D(2030, 1, 1), Decimal('33.33'), D(2029, 11, 26)),
        (3, D(2030, 2, 1), None, D(2030, 2, 1), Decimal('33.33'), D(2029, 12, 26)),
    ]
    assert sum(x[4] for x in linhas(banco, r['compra_id'])) == Decimal('100.00')
    assert fatura(banco, c, D(2029, 12, 1))['data_vencimento'] == D(2029, 12, 5)


@pg
def test_ajuste_manual_preserva_data_e_registra_sugestao(banco):  # noqa: F811
    c = novo_cartao(banco)
    r = criar(banco, compra(c, '2029-10-26', '90.00', 3, mes='2030-01-01'))  # administradora informou janeiro
    assert linhas(banco, r['compra_id']) == [
        (1, D(2030, 1, 1), None, D(2029, 12, 1), Decimal('30.00'), D(2029, 10, 26)),
        (2, D(2030, 2, 1), None, D(2030, 1, 1), Decimal('30.00'), D(2029, 11, 26)),
        (3, D(2030, 3, 1), None, D(2030, 2, 1), Decimal('30.00'), D(2029, 12, 26)),
    ]


@pg
def test_fatura_intermediaria_paga_desvia_e_guarda_original_e_sugestao(banco):  # noqa: F811
    c = novo_cartao(banco)
    criar(banco, compra(c, '2029-11-26', '10.00', mes='2030-01-01', descricao='Antes'))
    pagar(banco, c, D(2030, 1, 1))
    paga = fatura(banco, c, D(2030, 1, 1))
    r = criar(banco, compra(c, '2029-10-26', '90.00', 3))
    assert linhas(banco, r['compra_id']) == [
        (1, D(2029, 12, 1), None, D(2029, 12, 1), Decimal('30.00'), D(2029, 10, 26)),
        (2, D(2030, 2, 1), D(2030, 1, 1), D(2030, 1, 1), Decimal('30.00'), D(2029, 11, 26)),
        (3, D(2030, 3, 1), D(2030, 2, 1), D(2030, 2, 1), Decimal('30.00'), D(2029, 12, 26)),
    ]
    assert fatura(banco, c, D(2030, 1, 1)) == paga  # fatura paga intacta


@pg
def test_sem_mes_e_sem_sugestao_pede_o_mes(banco):  # noqa: F811
    c = novo_cartao(banco, confirmado=False)
    with pytest.raises(errors.InvalidParameterValue, match='fechamento do cartao ainda nao foi confirmado'):
        criar(banco, compra(c))
    r = criar(banco, compra(c, mes='2029-11-01'))  # informado manualmente
    assert linhas(banco, r['compra_id'])[0][1:4] == (D(2029, 11, 1), None, None)
    amb = novo_cartao(banco, nome='Ambiguo', fechamento=29, vencimento=30)
    assert rpc(banco, 'sugerir_competencia', ID['PESSOAL'], amb, '2030-02-15')['situacao'] == 'CICLO_AMBIGUO'
    with pytest.raises(errors.InvalidParameterValue, match='nao definem a fatura desta data'):
        criar(banco, compra(amb, '2030-02-15'))


@pg
def test_nova_configuracao_nao_mexe_em_compras_nem_faturas_antigas(banco):  # noqa: F811
    c = novo_cartao(banco)
    criar(banco, compra(c, '2029-10-26', '90.00', 3))
    antes = (md5_compras(banco), sql(banco, "select md5(string_agg(t::text, '|' order by id)) as h from public.conta t")[0])
    versao = next(x for x in cartoes(banco) if x['id'] == c)['versao']
    rpc(banco, 'editar_cartao', ID['PESSOAL'], c, versao, {'dia_fechamento': 10, 'dia_vencimento': 20,
                                                           'fechamento_confirmado': True})
    assert (md5_compras(banco), sql(banco, "select md5(string_agg(t::text, '|' order by id)) as h from public.conta t")[0]) == antes
    # so as operacoes novas usam a configuracao nova
    r = criar(banco, compra(c, '2029-10-26', '5.00'))
    assert linhas(banco, r['compra_id'])[0][1] == D(2029, 11, 1)  # fecha 10/11, vence 20/11


@pg
def test_flask_e_novo_aplicativo_gravam_as_mesmas_parcelas(cluster):  # noqa: F811
    dsn_flask, dsn_novo = copiar(cluster), copiar(cluster)
    for dsn in (dsn_flask, dsn_novo):
        c = novo_cartao(dsn)
        criar(dsn, compra(c, '2029-11-26', '10.00', mes='2030-01-01', descricao='Antes'))
        pagar(dsn, c, D(2030, 1, 1))
    sug = flask(dsn_flask, [['get', f'/api/cartoes/{c}/competencia-sugerida?data=2029-10-26', None]])[0]
    assert sug['status'] == 200 and sug['json']['competencia'] == '2029-12-01' and sug['json']['fatura_situacao'] == 'SEM_FATURA'
    saida = flask(dsn_flask, [['post', f'/api/cartoes/{c}/lancamentos', {
        'categoria_id': MORADIA, 'descricao': 'Sofa', 'valor': '90.00', 'data_compra': '2029-10-26',
        'mes_fatura': sug['json']['competencia'][:7], 'total_parcelas': 3}]])
    assert saida[0]['status'] == 201, saida
    criar(dsn_novo, compra(c, '2029-10-26', '90.00', 3, descricao='Sofa'))
    consulta = ("select numero_parcela, mes_fatura, mes_fatura_original, mes_fatura_sugerido, valor, data_compra "
                "from public.lancamento_agregado where descricao = 'Sofa' order by numero_parcela")
    assert sql(dsn_flask, consulta) == sql(dsn_novo, consulta)
    assert [x['mes_fatura'] for x in sql(dsn_novo, consulta)] == [D(2029, 12, 1), D(2030, 2, 1), D(2030, 3, 1)]


# ---------------------------------------------------------------------------
# C. Situacao da fatura (D6)
# ---------------------------------------------------------------------------

@pg
def test_fatura_aberta_recebe_sem_confirmacao(banco):  # noqa: F811
    c = novo_cartao(banco)
    r = criar(banco, compra(c, '2029-10-24', '40.00'))
    f = fatura(banco, c, D(2029, 11, 1))
    assert (f['status_fatura'], f['valor_executado'], r['consolidadas']) == ('ABERTA', Decimal('40.00'), [])
    assert auditoria(banco) == []


@pg
def test_fatura_consolidada_sem_confirmacao_nao_muda_nada(banco):  # noqa: F811
    c = novo_cartao(banco)
    criar(banco, compra(c, '2029-10-24', '40.00'))
    f = consolidar(banco, c, D(2029, 11, 1))
    antes = (md5_compras(banco), f)
    p = previa(banco, compra(c, '2029-10-24', '10.00'))
    assert p['parcelas'][0]['situacao_fatura'] == 'FECHADA'
    assert p['consolidadas'] == [{'fatura_id': f['id'], 'competencia': '2029-11-01', 'total_consolidado': 40.00,
                                  'valor_incluido': 10.00, 'total_novo': 50.00}]
    with pytest.raises(errors.RaiseException, match='consolidada') as erro:
        criar(banco, compra(c, '2029-10-24', '10.00'))
    assert erro.value.diag.message_hint == 'CONSOLIDADA'
    assert json.loads(erro.value.diag.message_detail)['total_novo'] == 50
    assert (md5_compras(banco), fatura(banco, c, D(2029, 11, 1))) == antes and auditoria(banco) == []


@pg
def test_fatura_consolidada_com_confirmacao_atualiza_total_e_audita(banco):  # noqa: F811
    c = novo_cartao(banco)
    criar(banco, compra(c, '2029-10-24', '40.00'))
    f = consolidar(banco, c, D(2029, 11, 1))
    p = previa(banco, compra(c, '2029-10-24', '10.00'))
    r = criar(banco, compra(c, '2029-10-24', '10.00', confirmar_consolidadas=confirmacao(p['consolidadas'])))
    depois = fatura(banco, c, D(2029, 11, 1))
    assert (depois['status_fatura'], depois['valor_consolidado'], depois['valor_executado']) == \
        ('FECHADA', Decimal('50.00'), Decimal('50.00'))
    [a] = auditoria(banco, f['id'])
    assert (a['valor_incluido'], a['total_consolidado_anterior'], a['total_consolidado_novo'], a['operacao'], a['origem'],
            a['user_id'], a['compra_id'], a['lancamento_id']) == \
        (Decimal('10.00'), Decimal('40.00'), Decimal('50.00'), 'COMPRA', 'NOVO_APP', USUARIO_A['id'], r['compra_id'],
         r['lancamentos'][0])
    assert r['consolidadas'] == [{'fatura_id': f['id'], 'total_consolidado': 50.00}]


@pg
def test_confirmacao_e_da_operacao_e_do_total_visto(banco):  # noqa: F811
    c = novo_cartao(banco)
    criar(banco, compra(c, '2029-10-24', '40.00'))
    f = consolidar(banco, c, D(2029, 11, 1))
    for errada in ([{'fatura_id': f['id'], 'total_consolidado': '39.99'}],      # total diferente do visto
                   [{'fatura_id': f['id'] + 1000, 'total_consolidado': '40.00'}],  # outra fatura
                   {'fatura_id': f['id'], 'total_consolidado': '40.00'},       # nao e lista
                   [{'confirmar_todas': True}]):                               # sem confirmacao global
        with pytest.raises(errors.RaiseException, match='consolidada'):
            criar(banco, compra(c, '2029-10-24', '10.00', confirmar_consolidadas=errada))
    assert auditoria(banco) == [] and fatura(banco, c, D(2029, 11, 1)) == f


@pg
def test_fatura_paga_continua_protegida_mesmo_com_confirmacao(banco):  # noqa: F811
    c = novo_cartao(banco)
    criar(banco, compra(c, '2029-10-24', '40.00'))
    consolidar(banco, c, D(2029, 11, 1))
    pagar(banco, c, D(2029, 11, 1))
    paga = fatura(banco, c, D(2029, 11, 1))
    r = criar(banco, compra(c, '2029-10-24', '10.00',
                            confirmar_consolidadas=[{'fatura_id': paga['id'], 'total_consolidado': '40.00'}]))
    assert linhas(banco, r['compra_id'])[0][1:3] == (D(2029, 12, 1), D(2029, 11, 1))  # desviada
    assert fatura(banco, c, D(2029, 11, 1)) == paga and auditoria(banco) == []


@pg
def test_situacao_muda_entre_a_previa_e_a_confirmacao(banco):  # noqa: F811
    c = novo_cartao(banco)
    criar(banco, compra(c, '2029-10-24', '40.00'))
    p = previa(banco, compra(c, '2029-10-24', '10.00'))
    assert p['consolidadas'] == []  # aberta na previa
    consolidar(banco, c, D(2029, 11, 1))
    with pytest.raises(errors.RaiseException, match='consolidada'):  # consolidada depois: reavaliada na gravacao
        criar(banco, compra(c, '2029-10-24', '10.00'))
    p = previa(banco, compra(c, '2029-10-24', '10.00'))
    vista = confirmacao(p['consolidadas'])
    criar(banco, compra(c, '2029-10-24', '5.00', confirmar_consolidadas=vista))  # outra inclusao muda o total
    with pytest.raises(errors.RaiseException, match='total R\\$ 45.00'):
        criar(banco, compra(c, '2029-10-24', '10.00', confirmar_consolidadas=vista))
    assert fatura(banco, c, D(2029, 11, 1))['valor_consolidado'] == Decimal('45.00')


@pg
def test_duas_inclusoes_concorrentes_na_mesma_fatura_consolidada(banco):  # noqa: F811
    c = novo_cartao(banco)
    criar(banco, compra(c, '2029-10-24', '40.00'))
    consolidar(banco, c, D(2029, 11, 1))
    vista = confirmacao(previa(banco, compra(c, '2029-10-24', '10.00'))['consolidadas'])
    resultados, barreira = [None, None], threading.Barrier(2)

    def incluir(i):
        barreira.wait(10)
        try:
            resultados[i] = ('ok', criar(banco, compra(c, '2029-10-24', '10.00', descricao=f'Concorrente {i}',
                                                       confirmar_consolidadas=vista)))
        except Exception as exc:  # noqa: BLE001
            resultados[i] = ('erro', exc)

    tarefas = [threading.Thread(target=incluir, args=(i,)) for i in (0, 1)]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join(60)
    assert sorted(r[0] for r in resultados) == ['erro', 'ok']
    assert 'consolidada' in str(next(r[1] for r in resultados if r[0] == 'erro'))
    f = fatura(banco, c, D(2029, 11, 1))
    assert (f['valor_consolidado'], f['valor_executado']) == (Decimal('50.00'), Decimal('50.00'))
    assert len(auditoria(banco)) == 1


@pg
def test_mover_compra_para_fatura_consolidada_exige_confirmacao(banco):  # noqa: F811
    c = novo_cartao(banco)
    criar(banco, compra(c, '2029-10-24', '40.00'))
    f = consolidar(banco, c, D(2029, 11, 1))
    r = criar(banco, compra(c, '2029-11-26', '15.00'))  # dezembro, aberta
    lanc = r['lancamentos'][0]
    with pytest.raises(errors.RaiseException, match='consolidada'):
        rpc(banco, 'editar_compra', ID['PESSOAL'], lanc, edicao(banco, lanc)['versao'], {'mes_fatura': '2029-11-01'})
    rpc(banco, 'editar_compra', ID['PESSOAL'], lanc, edicao(banco, lanc)['versao'],
        {'mes_fatura': '2029-11-01', 'confirmar_consolidadas': [{'fatura_id': f['id'], 'total_consolidado': '40.00'}]})
    assert fatura(banco, c, D(2029, 11, 1))['valor_consolidado'] == Decimal('55.00')
    [a] = auditoria(banco)
    assert (a['operacao'], a['valor_incluido'], a['lancamento_id']) == ('EDICAO', Decimal('15.00'), lanc)


@pg
def test_flask_exige_confirmacao_na_fatura_consolidada_e_audita(banco):  # noqa: F811
    c = novo_cartao(banco)
    criar(banco, compra(c, '2029-10-24', '40.00'))
    consolida = flask(banco, [['post', f'/api/cartoes/{c}/faturas/2029-11/consolidar', None]])[0]
    assert consolida['status'] == 200 and consolida['json']['fatura']['valor_consolidado'] == 40.0
    f = fatura(banco, c, D(2029, 11, 1))
    corpo = {'categoria_id': MORADIA, 'descricao': 'Na consolidada', 'valor': '10.00', 'data_compra': '2029-10-24',
             'mes_fatura': '2029-11'}
    sem, com = flask(banco, [
        ['post', f'/api/cartoes/{c}/lancamentos', corpo],
        ['post', f'/api/cartoes/{c}/lancamentos',
         {**corpo, 'confirmar_consolidadas': [{'fatura_id': f['id'], 'total_consolidado': '40.00'}]}]])
    assert sem['status'] == 409 and sem['json']['codigo'] == 'CONFIRMAR_FATURA_CONSOLIDADA'
    assert sem['json']['faturas'] == [{'fatura_id': f['id'], 'competencia': '2029-11-01', 'total_consolidado': '40.00',
                                       'valor_incluido': '10.00', 'total_novo': '50.00'}]
    assert com['status'] == 201
    assert len(sql(banco, "select 1 from public.lancamento_agregado where descricao = 'Na consolidada'")) == 1
    assert fatura(banco, c, D(2029, 11, 1))['valor_consolidado'] == Decimal('50.00')
    [a] = auditoria(banco)
    assert (a['origem'], a['operacao'], a['total_consolidado_anterior'], a['total_consolidado_novo']) == \
        ('FLASK', 'COMPRA', Decimal('40.00'), Decimal('50.00'))
    # a confirmacao vista antes da inclusao do Flask nao vale mais no novo aplicativo (total mudou)
    with pytest.raises(errors.RaiseException, match='consolidada'):
        criar(banco, compra(c, '2029-10-24', '1.00',
                            confirmar_consolidadas=[{'fatura_id': f['id'], 'total_consolidado': '40.00'}]))


@pg
def test_flask_mover_compra_para_fatura_consolidada_exige_confirmacao(banco):  # noqa: F811
    c = novo_cartao(banco)
    criar(banco, compra(c, '2029-10-24', '40.00'))
    f = consolidar(banco, c, D(2029, 11, 1))
    lanc = criar(banco, compra(c, '2029-11-26', '15.00'))['lancamentos'][0]
    sem, com = flask(banco, [
        ['put', f'/api/cartoes/lancamentos/{lanc}', {'mes_fatura': '2029-11'}],
        ['put', f'/api/cartoes/lancamentos/{lanc}', {'mes_fatura': '2029-11', 'confirmar_consolidadas': [
            {'fatura_id': f['id'], 'total_consolidado': '40.00'}]}]])
    assert (sem['status'], sem['json']['codigo'], com['status']) == (409, 'CONFIRMAR_FATURA_CONSOLIDADA', 200)
    assert fatura(banco, c, D(2029, 11, 1))['valor_consolidado'] == Decimal('55.00')
    assert [(a['origem'], a['operacao']) for a in auditoria(banco)] == [('FLASK', 'EDICAO')]


# ---------------------------------------------------------------------------
# D. Compatibilidade Flask x novo aplicativo
# ---------------------------------------------------------------------------

@pg
def test_cartao_criado_no_flask_e_editado_no_novo(banco):  # noqa: F811
    r = flask(banco, [['post', '/api/cartoes', {'nome': 'Flask Fecha 25', 'dia_fechamento': 25, 'dia_vencimento': 5,
                                                'compra_no_fechamento': 'ATUAL', 'fechamento_confirmado': True}]])[0]
    assert r['status'] == 201 and r['json']['config']['dia_fechamento'] == 25
    c = r['json']['id']
    novo = next(x for x in cartoes(banco) if x['id'] == c)
    assert (novo['dia_fechamento'], novo['dia_vencimento'], novo['compra_no_fechamento'], novo['fechamento_confirmado']) == \
        (25, 5, 'ATUAL', True)
    rpc(banco, 'editar_cartao', ID['PESSOAL'], c, novo['versao'], {'limite_credito': '900.00'})
    lido = flask(banco, [['get', f'/api/cartoes/{c}', None]])[0]['json']['config']
    assert (lido['dia_fechamento'], lido['dia_vencimento'], lido['compra_no_fechamento'], lido['fechamento_confirmado']) == \
        (25, 5, 'ATUAL', True)


@pg
def test_cartao_criado_no_novo_e_editado_no_flask_preserva_o_fechamento(banco):  # noqa: F811
    c = novo_cartao(banco, fechamento=25, vencimento=5, regra='ATUAL')
    saida = flask(banco, [
        ['put', f'/api/cartoes/{c}', {'nome': 'Renomeado no Flask', 'limite_credito': 1000}],  # sem dias: ficam
        ['get', f'/api/cartoes/{c}', None],
        ['put', f'/api/cartoes/{c}', {'dia_vencimento': 7}],  # o Flask antigo mandava fechamento = vencimento
        ['get', f'/api/cartoes/{c}', None],
        ['put', f'/api/cartoes/{c}', {'dia_vencimento': 7, 'fechamento_confirmado': True}],
        ['get', f'/api/cartoes/{c}', None],
    ])
    assert [s['status'] for s in saida] == [200] * 6
    cfg = [s['json']['config'] for s in saida[1::2]]
    assert [(x['dia_fechamento'], x['dia_vencimento'], x['compra_no_fechamento'], x['fechamento_confirmado'])
            for x in cfg] == [(25, 5, 'ATUAL', True), (25, 7, 'ATUAL', False), (25, 7, 'ATUAL', True)]
    novo = next(x for x in cartoes(banco) if x['id'] == c)
    assert (novo['dia_fechamento'], novo['dia_vencimento'], novo['fechamento_confirmado']) == (25, 7, True)


@pg
def test_novo_aplicativo_desconfirma_ao_mudar_o_ciclo_sem_reconfirmar(banco):  # noqa: F811
    c = novo_cartao(banco)
    versao = lambda: next(x for x in cartoes(banco) if x['id'] == c)['versao']  # noqa: E731
    rpc(banco, 'editar_cartao', ID['PESSOAL'], c, versao(), {'limite_credito': '10.00'})
    assert next(x for x in cartoes(banco) if x['id'] == c)['fechamento_confirmado'] is True
    rpc(banco, 'editar_cartao', ID['PESSOAL'], c, versao(), {'compra_no_fechamento': 'ATUAL'})
    assert next(x for x in cartoes(banco) if x['id'] == c)['fechamento_confirmado'] is False
    with pytest.raises(errors.InvalidParameterValue):
        rpc(banco, 'editar_cartao', ID['PESSOAL'], c, versao(), {'compra_no_fechamento': 'DEPOIS'})


@pg
def test_cartao_nao_confirmado_sem_sugestao_nos_dois(banco):  # noqa: F811
    r = flask(banco, [['post', '/api/cartoes', {'nome': 'Legado', 'dia_fechamento': 10, 'dia_vencimento': 10}]])[0]
    c = r['json']['id']
    assert r['json']['config']['fechamento_confirmado'] is False  # nada e confirmado sem acao explicita
    flask_sug = flask(banco, [['get', f'/api/cartoes/{c}/competencia-sugerida?data=2029-10-05', None]])[0]['json']
    novo_sug = rpc(banco, 'sugerir_competencia', ID['PESSOAL'], c, '2029-10-05')
    assert flask_sug['situacao'] == novo_sug['situacao'] == 'NAO_CONFIRMADO'
    assert flask_sug['competencia'] is None and novo_sug['competencia'] is None


@pg
def test_sugestao_igual_pelas_duas_apis(banco):  # noqa: F811
    c = novo_cartao(banco, fechamento=31, vencimento=10)
    criar(banco, compra(c, '2029-12-31', '20.00', mes='2030-02-01'))
    consolidar(banco, c, D(2030, 2, 1))
    for data in ('2029-12-30', '2029-12-31', '2030-01-31', '2030-02-28', '2030-04-30'):
        f = flask(banco, [['get', f'/api/cartoes/{c}/competencia-sugerida?data={data}', None]])[0]['json']
        n = rpc(banco, 'sugerir_competencia', ID['PESSOAL'], c, data)
        for chave in ('situacao', 'competencia', 'fechamento', 'vencimento', 'fatura_situacao'):
            assert f.get(chave) == n.get(chave), (data, chave)
    assert n['vencimento'] == '2030-06-10' and f['fatura_situacao'] == 'SEM_FATURA'


# ---------------------------------------------------------------------------
# Privilegios
# ---------------------------------------------------------------------------

@pg
@pytest.mark.parametrize('comando', [
    "select financeiro.competencia_da_compra('2029-10-24', 25, 5, 'PROXIMO')",
    "select financeiro.sugestao_competencia(910, '2029-10-24')",
    "select financeiro.situacao_fatura(1)",
    "select financeiro.exigir_confirmacao_consolidada(1, '[]'::jsonb, 1)",
    "select * from public.fatura_consolidada_inclusao",
])
def test_navegador_nao_acessa_funcoes_internas_nem_auditoria(banco, comando):  # noqa: F811
    with pytest.raises(errors.InsufficientPrivilege):
        chamar(banco, USUARIO_A, comando)


@pg
def test_sugestao_respeita_perfil_e_anonimo(banco):  # noqa: F811
    c = novo_cartao(banco)
    with pytest.raises(errors.InsufficientPrivilege):
        chamar(banco, None, "select financeiro.sugerir_competencia(101, %s, '2029-10-24')", (c,))
    with pytest.raises(errors.InsufficientPrivilege):
        rpc(banco, 'sugerir_competencia', ID['PESSOAL'], c, '2029-10-24', usuario=USUARIO_B)
    with pytest.raises(errors.InsufficientPrivilege):  # cartao de outro perfil
        rpc(banco, 'sugerir_competencia', ID['PERFIL_B'], c, '2029-10-24', usuario=USUARIO_B)


# ---------------------------------------------------------------------------
# E. Alembic c7e2a9d4b8f3 (so bancos ficticios)
# ---------------------------------------------------------------------------

def _migration():
    import importlib.util
    caminho = ROOT / 'migrations' / 'versions' / 'c7e2a9d4b8f3_cartoes_fechamento.py'
    spec = importlib.util.spec_from_file_location('mig_c7e2', caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _rodar(url, funcao):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine
    motor = create_engine(url)
    with motor.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(_migration(), funcao)()
    motor.dispose()


def test_revisao_encadeada_e_cabeca_unica():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    m = _migration()
    assert (m.revision, m.down_revision) == ('c7e2a9d4b8f3', 'f1c4d8e2a7b9')
    cfg = Config(str(ROOT / 'migrations' / 'alembic.ini'))
    cfg.set_main_option('script_location', str(ROOT / 'migrations'))
    assert ScriptDirectory.from_config(cfg).get_heads() == ['c7e2a9d4b8f3']


def test_alembic_sqlite_ficticio_sobe_idempotente_preserva_e_desce(tmp_path):
    caminho = tmp_path / 'ficticio.db'
    with sqlite3.connect(caminho) as conn:
        conn.executescript("""
            create table conta (id integer primary key);
            create table config_agregador (id integer primary key, item_despesa_id integer, dia_fechamento integer,
                                           dia_vencimento integer);
            create table lancamento_agregado (id integer primary key, descricao text, mes_fatura date);
            insert into config_agregador values (1, 910, 10, 10);
            insert into lancamento_agregado values (1, 'Compra antiga', '2026-05-01');""")
    url = f'sqlite:///{caminho.as_posix()}'
    _rodar(url, 'upgrade')
    _rodar(url, 'upgrade')  # idempotente
    with sqlite3.connect(caminho) as conn:
        assert conn.execute('select id, dia_fechamento, dia_vencimento, compra_no_fechamento, fechamento_confirmado '
                            'from config_agregador').fetchall() == [(1, 10, 10, 'PROXIMO', 0)]  # nada confirmado
        assert conn.execute('select id, descricao, mes_fatura, mes_fatura_sugerido from lancamento_agregado').fetchall() == \
            [(1, 'Compra antiga', '2026-05-01', None)]
        assert conn.execute("select count(*) from sqlite_master where name = 'fatura_consolidada_inclusao'").fetchone()[0] == 1
    _rodar(url, 'downgrade')
    with sqlite3.connect(caminho) as conn:
        assert [r[1] for r in conn.execute("pragma table_info('config_agregador')")] == \
            ['id', 'item_despesa_id', 'dia_fechamento', 'dia_vencimento']
        assert conn.execute("select count(*) from sqlite_master where name = 'fatura_consolidada_inclusao'").fetchone()[0] == 0


@pg
def test_alembic_postgresql_ficticio_sobe_idempotente_preserva_e_desce(cluster):  # noqa: F811
    dsn = copiar(cluster)
    for comando in ('drop table public.fatura_consolidada_inclusao',  # como antes das migrations
                    'alter table public.config_agregador drop column compra_no_fechamento',
                    'alter table public.config_agregador drop column fechamento_confirmado',
                    'alter table public.lancamento_agregado drop column mes_fatura_sugerido'):
        sql(dsn, comando)
    antes = sql(dsn, "select md5(string_agg(t::text, '|' order by id)) as h from public.config_agregador t")
    url = dsn.replace('postgresql://', 'postgresql+psycopg2://')
    _rodar(url, 'upgrade')
    _rodar(url, 'upgrade')
    assert sql(dsn, 'select count(*) as n from public.config_agregador where fechamento_confirmado')[0]['n'] == 0
    assert sql(dsn, "select count(*) as n from public.config_agregador where compra_no_fechamento <> 'PROXIMO'")[0]['n'] == 0
    assert sql(dsn, "select relrowsecurity from pg_class where oid = 'public.fatura_consolidada_inclusao'::regclass")[0][
        'relrowsecurity'] is True  # o cluster simula os papeis do Supabase
    _rodar(url, 'downgrade')
    assert sql(dsn, "select md5(string_agg(t::text, '|' order by id)) as h from public.config_agregador t") == antes


# ---------------------------------------------------------------------------
# F. Vencimento 29-31 no Flask (D4)
# ---------------------------------------------------------------------------

def test_flask_cria_fatura_com_vencimento_29_a_31_em_mes_curto():
    from backend.app import create_app
    from backend.models import ConfigAgregador, ItemDespesa, db
    app = create_app('testing')
    with app.test_request_context():
        db.create_all()
        cartao = ItemDespesa(nome='Vence 31', tipo='Agregador', ativo=True)
        db.session.add(cartao)
        db.session.flush()
        db.session.add(ConfigAgregador(item_despesa_id=cartao.id, dia_fechamento=21, dia_vencimento=31))
        db.session.commit()
        vencimentos = {mes: CartaoService.get_or_create_fatura(cartao.id, mes).data_vencimento
                       for mes in (D(2027, 2, 1), D(2028, 2, 1), D(2027, 4, 1), D(2027, 5, 1))}
        db.session.remove()
        db.drop_all()
    assert vencimentos == {D(2027, 2, 1): D(2027, 2, 28), D(2028, 2, 1): D(2028, 2, 29),
                           D(2027, 4, 1): D(2027, 4, 30), D(2027, 5, 1): D(2027, 5, 31)}


def test_flask_recusa_inclusao_consolidada_sem_auditoria(monkeypatch):
    """Banco sem a tabela de auditoria (migration pendente): nenhuma inclusao em fatura consolidada."""
    from backend.app import create_app
    from backend.models import Conta, ConfigAgregador, ItemDespesa, db
    app = create_app('testing')
    with app.test_request_context():
        db.create_all()
        cartao = ItemDespesa(nome='Sem auditoria', tipo='Agregador', ativo=True)
        db.session.add(cartao)
        db.session.flush()
        db.session.add(ConfigAgregador(item_despesa_id=cartao.id, dia_fechamento=25, dia_vencimento=5))
        db.session.commit()
        f = CartaoService.get_or_create_fatura(cartao.id, D(2029, 11, 1))
        f.status_fatura, f.valor_consolidado = 'FECHADA', Decimal('0')
        db.session.commit()
        monkeypatch.setattr(CartaoService, 'suporta_auditoria_consolidada', staticmethod(lambda: False))
        with pytest.raises(ValueError, match='migration pendente'):
            CartaoService.adicionar_lancamento({
                'cartao_id': cartao.id, 'categoria_id': None, 'descricao': 'X', 'valor': '1.00',
                'data_compra': D(2029, 10, 24), 'mes_fatura': D(2029, 11, 1), 'total_parcelas': 1,
                'confirmar_consolidadas': [{'fatura_id': f.id, 'total_consolidado': '0.00'}]})
        db.session.rollback()
        assert db.session.get(Conta, f.id).valor_consolidado == Decimal('0')
        db.session.remove()
        db.drop_all()


def _remover_objetos_da_migration(conn):
    """Deixa o SQLite como o gastos.db antes de c7e2a9d4b8f3 (sem as colunas e sem a auditoria)."""
    conn.exec_driver_sql('drop table fatura_consolidada_inclusao')
    conn.exec_driver_sql('alter table lancamento_agregado drop column mes_fatura_sugerido')
    ddl = conn.exec_driver_sql("select sql from sqlite_master where name = 'config_agregador'").scalar()
    abre, fecha = ddl.index('('), ddl.rindex(')')
    itens = [i for i in re.split(r',\s*\n', ddl[abre + 1:fecha])
             if 'compra_no_fechamento' not in i and 'fechamento_confirmado' not in i]
    conn.exec_driver_sql('drop table config_agregador')  # vazia; o CHECK impede o drop column no SQLite
    conn.exec_driver_sql(f"{ddl[:abre]}({', '.join(i.strip() for i in itens)})")


def test_flask_em_banco_sem_a_migration_funciona_como_antes(tmp_path, monkeypatch):
    """gastos.db ainda nao migrado: cadastro, edicao, listagem e compra seguem; nada de sugestao nem confirmacao."""
    from flask import Flask
    from backend.models import db
    from backend.routes.cartoes import cartoes_bp
    from sqlalchemy import inspect
    monkeypatch.setattr(CartaoService, '_capacidades', {})
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI=f"sqlite:///{(tmp_path / 'legado.db').as_posix()}",
                      SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    app.register_blueprint(cartoes_bp)
    with app.app_context():
        db.create_all()
        with db.engine.begin() as conn:
            _remover_objetos_da_migration(conn)
        c = app.test_client()
        criado = c.post('/api/cartoes', json={'nome': 'Legado', 'dia_fechamento': 25, 'dia_vencimento': 5,
                                              'compra_no_fechamento': 'ATUAL', 'fechamento_confirmado': True})
        assert criado.status_code == 201, criado.get_json()
        cartao = criado.get_json()['id']
        assert {k: criado.get_json()['config'][k] for k in
                ('dia_fechamento', 'dia_vencimento', 'compra_no_fechamento', 'fechamento_confirmado',
                 'fechamento_configuravel')} ==             {'dia_fechamento': 25, 'dia_vencimento': 5, 'compra_no_fechamento': 'PROXIMO',
             'fechamento_confirmado': False, 'fechamento_configuravel': False}
        assert c.put(f'/api/cartoes/{cartao}', json={'dia_vencimento': 7}).status_code == 200
        lido = c.get(f'/api/cartoes/{cartao}').get_json()['config']
        assert (lido['dia_fechamento'], lido['dia_vencimento']) == (25, 7)  # fechamento preservado
        assert c.get('/api/cartoes').status_code == 200
        sugestao = c.get(f'/api/cartoes/{cartao}/competencia-sugerida?data=2029-10-24').get_json()
        assert (sugestao['situacao'], sugestao['competencia']) == ('NAO_CONFIRMADO', None)
        from backend.models import Categoria
        categoria = Categoria(nome='Moradia T', cor='#2563eb', ativo=True)
        db.session.add(categoria)
        db.session.commit()
        compra_ = c.post(f'/api/cartoes/{cartao}/lancamentos', json={
            'categoria_id': categoria.id, 'descricao': 'Compra legado', 'valor': '30.00', 'data_compra': '2029-10-24',
            'mes_fatura': '2029-11', 'total_parcelas': 2})
        assert compra_.status_code == 201, compra_.get_json()
        meses = db.session.execute(db.text('select mes_fatura from lancamento_agregado order by numero_parcela')).scalars()
        assert [str(m)[:10] for m in meses] == ['2029-11-01', '2029-12-01']
        esquema = inspect(db.engine)
        assert 'fechamento_confirmado' not in {x['name'] for x in esquema.get_columns('config_agregador')}
        assert not esquema.has_table('fatura_consolidada_inclusao')  # nada foi criado pelo Flask
        db.session.remove()


# ---------------------------------------------------------------------------
# Conferencia da migration (preparacao do FIN-CARTOES-FECHAMENTO-REAL-1): banco com dados da versao anterior
# ---------------------------------------------------------------------------

ALVO = '20261030090000'


def _conferencia():
    import importlib.util
    spec = importlib.util.spec_from_file_location('conferencia_migration',
                                                  ROOT / 'scripts' / 'supabase_conferencia_migration.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pg
def test_conferencia_da_migration_sobre_banco_com_dados_da_versao_anterior(tmp_path):
    from tests.supabase_local import semear_recorrencias
    conf = _conferencia()
    esperado = conf.conferencia_local(ALVO, contas=False)
    mudancas = esperado['mudancas']
    novas = {m.split(': ', 1)[1].split('(')[0]: m for m in mudancas if m.startswith('funcao nova')}
    assert set(novas) == {'competencia_da_compra', 'situacao_fatura', 'sugestao_competencia', 'sugerir_competencia',
                          'exigir_confirmacao_consolidada',
                          'fatura_consolidada_no_destino'}  # FIN-CARTOES-D6-INTEGRIDADE-1
    assert 'False/False/True' in novas['sugerir_competencia']  # so authenticated
    assert all('False/False/False' in m for n, m in novas.items() if n != 'sugerir_competencia')  # internas
    alteradas = {m.split(': ', 1)[1].split('(')[0]: m for m in mudancas if m.startswith('funcao alterada')}
    assert set(alteradas) == {'plano_compra', 'previa_compra', 'criar_compra', 'editar_compra', 'ler_dados_cartao',
                              'criar_cartao', 'editar_cartao', 'cartoes_do_perfil',
                              'plano_recorrencia', 'gerar_mes_interno'}  # FIN-CARTOES-D6-INTEGRIDADE-1 (so corpo)
    assert not any(p in m for m in alteradas.values() for p in ('public', 'anon', 'authenticated'))  # sem privilegio
    assert not [m for m in mudancas if m.startswith(('funcao removida', 'tabela removida'))]
    assert 'tabela nova: public.fatura_consolidada_inclusao | rls=[True, False] anon=---- authenticated=----' in mudancas

    def semear(dsn):  # dados criados pelas funcoes da versao anterior (sem regra de fechamento)
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            semear_recorrencias(cur)
        conn.close()
        c = rpc(dsn, 'criar_cartao', ID['PESSOAL'], {'nome': 'Antes da migration', 'dia_fechamento': 10,
                                                      'dia_vencimento': 10}, str(uuid.uuid4()))['cartao_id']
        for mes, valor, n in (('2029-10-01', '90.00', 3), ('2029-11-01', '40.00', 1)):
            rpc(dsn, 'criar_compra', ID['PESSOAL'], {'cartao_id': c, 'descricao': f'Compra {mes}', 'valor': valor,
                                                     'total_parcelas': n, 'data_compra': mes[:8] + '05',
                                                     'mes_fatura': mes, 'categoria_id': MORADIA}, str(uuid.uuid4()))
        pagar(dsn, c, D(2029, 10, 1))
        sql(dsn, "update public.conta set status_fatura = 'FECHADA', valor_consolidado = valor_executado, "
                 "data_consolidacao = now() where item_despesa_id = %s and cartao_competencia = '2029-11-01'", (c,))

    falhas = {}
    resultado = conf.conferencia_local(
        ALVO, semear=semear, contas=False,
        ao_capturar_antes=lambda conn: falhas.setdefault('antes', conf.conferir_banco(
            conn.cursor(), ALVO, 'antes', tmp_path, esperado, exigir_historico=False)),
        ao_capturar_depois=lambda conn: falhas.setdefault('depois', conf.conferir_banco(
            conn.cursor(), ALVO, 'depois', tmp_path, esperado, exigir_historico=False)))
    assert falhas == {'antes': [], 'depois': []}
    assert resultado['falhas'] == []
    assert resultado['antes']['conteudo']['public.lancamento_agregado'][0] >= 4  # 3 parcelas + 1 a vista
    assert (tmp_path / f'conferencia_{ALVO}_definicoes_antes.sql').read_text(encoding='utf-8').count(
        'CREATE OR REPLACE FUNCTION') == 10  # base de rollback: 8 + plano_recorrencia e gerar_mes_interno (D6-INTEGRIDADE-1)


@pytest.mark.parametrize('usuario, aceito', [
    ('postgres.fzjmge0000ficticio0000', True),        # prefixo do projeto de teste (ref ficticio)
    ('postgres.dshqjhyymtpxpxuntzbz', False),         # Calculadora Judicial
    ('postgres.abcdef0000ficticio0000', False),       # outro projeto
    ('postgres', False),                              # sem ref do pooler
])
def test_conferencia_remota_so_no_projeto_de_teste(usuario, aceito):
    conf = _conferencia()
    url = f'postgresql://{usuario}:senha-ficticia@pooler.invalido:6543/postgres'
    if aceito:
        assert conf.projeto_da_url(url) == usuario.split('.', 1)[1]
    else:
        with pytest.raises(SystemExit):
            conf.projeto_da_url(url)
