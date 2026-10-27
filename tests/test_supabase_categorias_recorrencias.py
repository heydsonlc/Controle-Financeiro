"""
Testes FIN-CATEGORIAS-RECORRENCIAS-2 (migration 20261125090000), em cluster PostgreSQL local descartavel.

Recorrencias semanais e a cada 2 semanas (R1): uma conta por ocorrencia, no dia da semana, com a descricao do Flask,
identidade por ocorrencia (geracao repetida, concorrente ou dispensada nao duplica nem recria), fase fixa, contas do
Flask reconhecidas no ciclo, pagamentos e contas geradas preservados nas alteracoes, cartao semanal rejeitado, as
mesmas datas do Flask. Receitas: valor base, recorrencia e reativacao da fonte (so as previsoes que faltam),
recebimento sem previsao (credito, sem duplicar), data prevista na tela. Catalogo global de categorias: escritor
proprio (padrao Flask) e gestor, nomes, sistemicas, exclusao segura, palavras-chave e a guarda do Flask.
"""
import datetime as dt
import json
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_receitas_categorias_tela import flask
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    gerar,
    gerar_confirmado,
    previa,
    rodar_flask,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

D = dt.date
PESSOAL = ID['PESSOAL']
CATEGORIA = 951  # 'Moradia R' (cenario ficticio)


@pytest.fixture
def banco(cluster):  # noqa: F811
    """Pessoal e Perfil B no novo aplicativo; recorrencias do cenario inativas (so as deste teste geram contas)."""
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    sql(dsn, "update public.item_despesa set ativo = false where tipo is distinct from 'Agregador'")
    return dsn


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


def nova_recorrencia(dsn, nome, tipo, vencimento, valor='30.00', perfil='PESSOAL', usuario=USUARIO_A):
    dados = {'nome': nome, 'valor': valor, 'categoria_id': CATEGORIA, 'data_vencimento': vencimento,
             'recorrente': True, 'tipo_recorrencia': tipo}
    return rpc(dsn, 'criar_despesa', ID[perfil], dados, str(uuid.uuid4()), usuario=usuario)['item_id']


def contas(dsn, item):
    return sql(dsn, 'select id, data_vencimento, mes_referencia, descricao, valor, status_pagamento from public.conta '
                    'where item_despesa_id = %s order by data_vencimento, id', (item,))


def datas(dsn, item):
    return [c['data_vencimento'] for c in contas(dsn, item)]


def a_cada(primeira, dias, ate):
    saida, d = [], primeira
    while d <= ate:
        saida.append(d)
        d += dt.timedelta(days=dias)
    return saida


def versao_recorrencia(dsn, item):
    return sql(dsn, 'select financeiro.versao_recorrencia(%s) as v', (item,))[0]['v']


def versao_despesa(dsn, conta):
    return sql(dsn, 'select financeiro.versao_despesa(%s) as v', (conta,))[0]['v']


def conta_bancaria(dsn, nome='Conta Pessoal (A)'):
    return sql(dsn, 'select id from public.conta_bancaria where nome = %s', (nome,))[0]['id']


# =====================================================================================================================
# Recorrencias semanais e a cada 2 semanas
# =====================================================================================================================

def test_semanal_gera_uma_conta_por_ocorrencia_no_dia_da_semana(banco):
    item = nova_recorrencia(banco, 'Diarista', 'semanal_1_3', '2027-03-02')  # terca; dia 3 = quarta
    r = gerar_confirmado(banco, mes='2027-03-01')
    esperado = a_cada(D(2027, 3, 3), 7, D(2027, 4, 30))
    assert datas(banco, item) == esperado and len(esperado) == 9
    for c in contas(banco, item):
        assert c['descricao'] == f"Diarista - {c['data_vencimento']:%d/%m}"  # como o Flask
        assert c['mes_referencia'] == c['data_vencimento'].replace(day=1)
        assert (c['valor'], c['status_pagamento']) == (30, 'Pendente')
    assert r['criadas']['contas'] >= 9
    # Geracao repetida: nada novo, nada alterado.
    antes = contas(banco, item)
    assert gerar_confirmado(banco, mes='2027-03-01')['criadas']['total'] == 0
    assert contas(banco, item) == antes
    registro = sql(banco, 'select data_ocorrencia, situacao, conta_id from financeiro.recorrencia_ocorrencia '
                          'where item_despesa_id = %s order by 1', (item,))
    assert [x['data_ocorrencia'] for x in registro] == esperado
    assert {x['situacao'] for x in registro} == {'GERADA'}


def test_quinzenal_mantem_a_fase_entre_geracoes(banco):
    item = nova_recorrencia(banco, 'Jardinagem', 'semanal_2_1', '2027-03-01')  # segunda, a cada 2 semanas
    gerar_confirmado(banco, mes='2027-03-01')
    assert datas(banco, item) == a_cada(D(2027, 3, 1), 14, D(2027, 4, 30))
    gerar_confirmado(banco, mes='2027-05-01')
    todas = datas(banco, item)
    assert todas == a_cada(D(2027, 3, 1), 14, D(2027, 6, 30))
    assert {(b - a).days for a, b in zip(todas, todas[1:])} == {14}


def test_geracoes_concorrentes_nao_duplicam_ocorrencias(banco):
    item = nova_recorrencia(banco, 'Feira', 'semanal_1_6', '2027-03-06')
    total = previa(banco, mes='2027-03-01')['a_gerar']
    barreira, resultados, falhas = threading.Barrier(2), [], []

    def executar():
        try:
            barreira.wait(timeout=10)
            resultados.append(gerar(banco, total, mes='2027-03-01'))
        except Exception as exc:  # noqa: BLE001
            falhas.append(exc)

    tarefas = [threading.Thread(target=executar) for _ in range(2)]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join(timeout=60)
    assert falhas == [] and sorted(r['criadas']['total'] for r in resultados) == [0, total]
    assert len(datas(banco, item)) == len(set(datas(banco, item))) == 8  # sabados de 06/03 a 24/04


def test_ocorrencia_dispensada_nao_volta_e_dispensa_sem_data_e_recusada(banco):
    item = nova_recorrencia(banco, 'Aula', 'semanal_1_2', '2027-03-02')
    p = previa(banco, mes='2027-03-01')
    alvo = next(x for x in p['itens'] if x['item_id'] == item and x['data_vencimento'] == '2027-03-16')
    sem_data = {'natureza': 'CONTA', 'item_id': item, 'competencia': '2027-03-01'}
    e = erro(gerar, banco, p['a_gerar'], mes='2027-03-01', dispensar=[sem_data])
    assert 'exige a data' in str(e)
    gerar(banco, p['a_gerar'], mes='2027-03-01', dispensar=[{**sem_data, 'data_vencimento': alvo['data_vencimento']}])
    assert D(2027, 3, 16) not in datas(banco, item) and D(2027, 3, 9) in datas(banco, item)
    depois = previa(banco, mes='2027-03-01')
    assert any(x['item_id'] == item for x in depois['dispensados'])
    gerar_confirmado(banco, mes='2027-05-01')
    assert D(2027, 3, 16) not in datas(banco, item)


def test_excluir_conta_semanal_dispensa_so_a_ocorrencia(banco):
    item = nova_recorrencia(banco, 'Faxina', 'semanal_1_4', '2027-03-04')
    gerar_confirmado(banco, mes='2027-03-01')
    conta = next(c for c in contas(banco, item) if c['data_vencimento'] == D(2027, 3, 11))
    r = rpc(banco, 'excluir_despesa', PESSOAL, conta['id'], versao_despesa(banco, conta['id']))
    assert r['competencia_dispensada'] is True
    situacao = sql(banco, 'select situacao, conta_id from financeiro.recorrencia_ocorrencia '
                          'where item_despesa_id = %s and data_ocorrencia = %s', (item, D(2027, 3, 11)))
    assert situacao == [{'situacao': 'DISPENSADA', 'conta_id': None}]
    gerar_confirmado(banco, mes='2027-05-01')
    assert D(2027, 3, 11) not in datas(banco, item)
    assert {D(2027, 3, 4), D(2027, 3, 18), D(2027, 3, 25)} <= set(datas(banco, item))  # as outras semanas ficam


def test_pagamento_preservado_e_alteracao_vale_para_as_proximas(banco):
    item = nova_recorrencia(banco, 'Personal', 'semanal_1_1', '2027-03-01')
    gerar_confirmado(banco, mes='2027-03-01')
    primeira = contas(banco, item)[0]
    pago = rpc(banco, 'pagar_despesa', PESSOAL, primeira['id'],
               {'conta_bancaria_id': conta_bancaria(banco), 'data_pagamento': '2027-03-01', 'valor_pago': '30.00',
                'valor_devido': '30.00'}, str(uuid.uuid4()))
    assert pago['movimento_id']
    paga_antes = sql(banco, 'select md5(c::text) as h from public.conta c where id = %s', (primeira['id'],))
    geradas_antes = {c['id']: c['valor'] for c in contas(banco, item)}

    rpc(banco, 'editar_recorrencia', PESSOAL, item, versao_recorrencia(banco, item), {'valor': '45.00'})
    gerar_confirmado(banco, mes='2027-05-01')
    depois = contas(banco, item)
    assert sql(banco, 'select md5(c::text) as h from public.conta c where id = %s', (primeira['id'],)) == paga_antes
    assert {c['id']: c['valor'] for c in depois if c['id'] in geradas_antes} == geradas_antes  # geradas nao mudam
    assert {c['valor'] for c in depois if c['id'] not in geradas_antes} == {45}               # proximas: valor novo
    # Conta paga nao e excluida (nem a semanal).
    e = erro(rpc, banco, 'excluir_despesa', PESSOAL, primeira['id'], versao_despesa(banco, primeira['id']))
    assert 'bloqueada' in str(e).lower() or 'paga' in str(e).lower()
    assert sql(banco, 'select count(*) as n from public.conta where id = %s', (primeira['id'],))[0]['n'] == 1


def test_contas_do_flask_no_ciclo_sao_reconhecidas_sem_duplicar(banco):
    sql(banco, "insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, "
               "tipo_recorrencia, data_vencimento, valor, meio_pagamento) values (7101, 'Lavanderia', 'Simples', %s, %s, "
               "true, true, 'semanal_2_1', '2027-03-01', 20, 'pix')", (PESSOAL, CATEGORIA))
    # Gravadas pelo Flask: uma em outro dia do 1o ciclo (01/03 a 14/03) e outra na data do 2o.
    for venc in ('2027-03-03', '2027-03-15'):
        sql(banco, "insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, "
                   "data_vencimento, status_pagamento, is_fatura_cartao, estouro_orcamento) values "
                   "(%s, 7101, '2027-03-01', 'Lavanderia', 20, %s, 'Pendente', false, false)", (PESSOAL, venc))
    linhas = {x['data_vencimento']: x for x in previa(banco, mes='2027-03-01')['itens'] if x['item_id'] == 7101}
    assert '2027-03-01' not in linhas and '2027-03-15' not in linhas  # existentes: fora dos "a gerar"
    assert '2027-03-29' in linhas
    gerar_confirmado(banco, mes='2027-03-01')
    assert datas(banco, 7101) == [D(2027, 3, 3), D(2027, 3, 15), D(2027, 3, 29), D(2027, 4, 12), D(2027, 4, 26)]


def test_semanal_no_cartao_fica_rejeitada_e_nao_e_cadastrada(banco):
    sql(banco, "insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, "
               "tipo_recorrencia, data_vencimento, valor, meio_pagamento, cartao_id) values (7102, 'App semanal', "
               "'Simples', %s, 952, true, true, 'semanal_1_5', '2027-03-05', 12, 'cartao', 910)", (PESSOAL,))
    p = previa(banco, mes='2027-03-01')
    assert [x['motivo'] for x in p['rejeitados'] if x['item_id'] == 7102] == \
        ['Recorrencia semanal no cartao: o sistema original tambem nao a lanca (so mensal e anual)']
    gerar_confirmado(banco, mes='2027-03-01')
    assert sql(banco, 'select count(*) as n from public.lancamento_agregado where item_despesa_id = 7102')[0]['n'] == 0
    dados = {'nome': 'Cartao semanal', 'valor': '10.00', 'categoria_id': 952, 'data_vencimento': '2027-03-05',
             'tipo_recorrencia': 'semanal_1_5', 'cartao_id': 910}
    assert 'mensal' in str(erro(rpc, banco, 'criar_recorrencia_cartao', PESSOAL, dados, str(uuid.uuid4())))


@pytest.mark.parametrize('tipo', ['semanal', 'a_cada_2_semanas', 'semanal_3_1', 'semanal_1_7', 'semanal_1'])
def test_frequencias_gravadas_so_no_formato_do_flask(banco, tipo):
    e = erro(nova_recorrencia, banco, 'X', tipo, '2027-03-01')
    assert e.pgcode == '22023' and 'semanal' in str(e)


def test_mensal_vira_semanal_e_inativa_nao_gera(banco):
    item = nova_recorrencia(banco, 'Mensal que vira', 'mensal', '2027-03-10')
    rpc(banco, 'editar_recorrencia', PESSOAL, item, versao_recorrencia(banco, item), {'tipo_recorrencia': 'semanal_1_3'})
    assert sql(banco, 'select tipo_recorrencia from public.item_despesa where id = %s', (item,))[0]['tipo_recorrencia'] \
        == 'semanal_1_3'
    rpc(banco, 'inativar_recorrencia', PESSOAL, item, versao_recorrencia(banco, item))
    p = previa(banco, mes='2027-03-01')
    assert not [x for x in p['itens'] if x['item_id'] == item]
    gerar_confirmado(banco, mes='2027-03-01')
    assert datas(banco, item) == []
    rpc(banco, 'reativar_recorrencia', PESSOAL, item, versao_recorrencia(banco, item))
    assert [x['data_vencimento'] for x in previa(banco, mes='2027-03-01')['itens'] if x['item_id'] == item][:2] == \
        ['2027-03-10', '2027-03-17']


def test_permissoes_e_escritor(banco, cluster):  # noqa: F811
    item = nova_recorrencia(banco, 'Do Pessoal', 'semanal_1_1', '2027-03-01')
    assert erro(gerar, banco, 0, usuario=USUARIO_B, mes='2027-03-01').pgcode == '42501'
    assert erro(nova_recorrencia, banco, 'Alheia', 'semanal_1_1', '2027-03-01', usuario=USUARIO_B).pgcode == '42501'
    assert erro(rpc, banco, 'editar_recorrencia', PESSOAL, item, versao_recorrencia(banco, item),
                {'tipo_recorrencia': 'semanal_2_1'}, usuario=USUARIO_B).pgcode == '42501'
    flask_dsn = copiar(cluster)  # Pessoal no Flask
    e = erro(nova_recorrencia, flask_dsn, 'No Flask', 'semanal_1_1', '2027-03-01')
    assert e.diag.message_hint == 'SISTEMA_FLASK'


def test_proximo_vencimento_como_o_flask(banco):
    from backend.routes.recorrencias import _proximo_vencimento
    hoje = dt.datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    casos = [('semanal_1_3', hoje - dt.timedelta(days=40)), ('semanal_2_1', hoje - dt.timedelta(days=100)),
             ('semanal_2_0', hoje + dt.timedelta(days=3)), ('semanal_1_5', hoje)]
    itens = {nova_recorrencia(banco, f'Prox {i}', tipo, str(venc)): (tipo, venc) for i, (tipo, venc) in enumerate(casos)}
    sql(banco, "insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, "
               "tipo_recorrencia, data_vencimento, valor) values (7103, 'Legado quinzenal', 'Simples', %s, %s, true, true, "
               "'a_cada_2_semanas', %s, 10)", (PESSOAL, CATEGORIA, hoje - dt.timedelta(days=30)))
    itens[7103] = ('a_cada_2_semanas', hoje - dt.timedelta(days=30))
    lista = {r['id']: r for r in chamar(banco, USUARIO_A, "select coalesce(json_agg(x), '[]'::json) "
                                                         'from financeiro.recorrencias_do_perfil(%s) x', (PESSOAL,))}
    for item, (tipo, venc) in itens.items():
        flask_prox = _proximo_vencimento(SimpleNamespace(data_vencimento=venc, tipo_recorrencia=tipo))
        assert lista[item]['proximo_vencimento'] == str(flask_prox), (tipo, venc)


def test_mesmas_datas_e_descricoes_do_flask_nas_frequencias_semanais(cluster):  # noqa: F811
    itens = [(7201, 'semanal_1_3'), (7202, 'semanal_2_1'), (7203, 'semanal'), (7204, 'a_cada_2_semanas')]

    def semear(dsn):
        for iid, tipo in itens:
            sql(dsn, "insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, "
                     "recorrente, tipo_recorrencia, data_vencimento, valor, meio_pagamento) values (%s, %s, 'Simples', "
                     "%s, %s, true, true, %s, '2027-01-06', 100, 'pix')", (iid, f'Semanal {iid}', PESSOAL, CATEGORIA, tipo))

    no_flask, no_novo = copiar(cluster), copiar(cluster)
    semear(no_flask)
    semear(no_novo)
    rodar_flask(no_flask, mes='2027-03', perfis=('PESSOAL',))
    atribuir(no_novo, 'PESSOAL')
    gerar_confirmado(no_novo, mes='2027-03-01')
    campos = 'item_despesa_id, mes_referencia, descricao, valor, data_vencimento, status_pagamento, debito_automatico'
    consulta = f'select {campos} from public.conta where item_despesa_id between 7201 and 7204 order by 1, 5'
    flask_contas, novo_contas = sql(no_flask, consulta), sql(no_novo, consulta)
    assert novo_contas == flask_contas and len(novo_contas) == 17 + 8 + 17 + 9


# =====================================================================================================================
# Receitas
# =====================================================================================================================

def mes_atual():
    return dt.datetime.now(ZoneInfo('America/Sao_Paulo')).date().replace(day=1)


def somar_meses(d, n):
    m = d.month - 1 + n
    return D(d.year + m // 12, m % 12 + 1, 1)


def nova_fonte(dsn, nome, competencia, recorrente=True, valor='5000.00', perfil='PESSOAL', usuario=USUARIO_A):
    dados = {'nome': nome, 'tipo': 'SALARIO_FIXO', 'valor': valor, 'competencia': str(competencia), 'recorrente': recorrente,
             'dia_previsto': 5}
    return rpc(dsn, 'criar_receita', ID[perfil], dados, str(uuid.uuid4()), usuario=usuario)['item_receita_id']


def previsoes(dsn, item):
    return {r['mes_referencia']: r['valor_esperado'] for r in
            sql(dsn, 'select mes_referencia, valor_esperado from public.receita_orcamento where item_receita_id = %s', (item,))}


def versao_fonte(dsn, item):
    return sql(dsn, 'select financeiro.versao_fonte(%s) as v', (item,))[0]['v']


def redefinir(dsn, item, dados, usuario=USUARIO_A, versao=None):
    return rpc(dsn, 'redefinir_fonte_receita', PESSOAL, item, versao or versao_fonte(dsn, item), dados, usuario=usuario)


def test_valor_base_cria_so_as_previsoes_que_faltam(banco):
    atual = mes_atual()
    item = nova_fonte(banco, 'Salario base', somar_meses(atual, -3))  # 12 previsoes: -3 .. +8
    zerada = sql(banco, 'select id from public.receita_orcamento where item_receita_id = %s and mes_referencia = %s',
                 (item, somar_meses(atual, 2)))[0]['id']
    rpc(banco, 'excluir_receita', PESSOAL, zerada, sql(banco, 'select financeiro.versao_previsao(%s) as v', (zerada,))[0]['v'])
    antes = previsoes(banco, item)
    r = redefinir(banco, item, {'valor_base_mensal': '6000.00'})
    depois = previsoes(banco, item)
    novas = {somar_meses(atual, i) for i in (9, 10, 11)}
    assert set(depois) - set(antes) == novas and len(r['previsoes_criadas']) == 3
    assert {depois[m] for m in novas} == {6000}
    assert {m: depois[m] for m in antes} == antes                 # gravadas (inclusive futura e zerada) nao mudam
    assert depois[somar_meses(atual, 2)] == 0
    assert redefinir(banco, item, {'valor_base_mensal': '6000.00'})['previsoes_criadas'] == []  # repetida: nada


def test_recorrencia_desligada_e_fonte_inativa_nao_criam_previsoes(banco):
    atual = mes_atual()
    item = nova_fonte(banco, 'Avulsa vira', atual, recorrente=False, valor='800.00')
    assert redefinir(banco, item, {'valor_base_mensal': '800.00', 'recorrente': False})['previsoes_criadas'] == []
    rpc(banco, 'inativar_fonte_receita', PESSOAL, item, versao_fonte(banco, item))
    r = redefinir(banco, item, {'valor_base_mensal': '900.00', 'recorrente': True})
    assert r['previsoes_criadas'] == [] and r['ativo'] is False and r['valor_base_mensal'] == 900
    # Reativar (o "ativo" do PUT do Flask): ativa e completa as que faltam.
    r = redefinir(banco, item, {'ativo': True})
    assert r['ativo'] is True and len(r['previsoes_criadas']) == 11  # o mes atual ja tinha a avulsa
    assert erro(redefinir, banco, item, {'ativo': False}).pgcode == '22023'


def test_fonte_respeita_versao_escritor_e_permissao(banco, cluster):  # noqa: F811
    item = nova_fonte(banco, 'Com versao', mes_atual())
    assert erro(redefinir, banco, item, {'valor_base_mensal': '1.00'}, versao='x').diag.message_hint == 'VERSAO'
    assert erro(redefinir, banco, item, {'valor_base_mensal': '1.00'}, usuario=USUARIO_B).pgcode == '42501'
    flask_dsn = copiar(cluster)
    sql(flask_dsn, "insert into public.item_receita (id, perfil_financeiro_id, nome, tipo, ativo, valor_base_mensal, "
                   "recorrente) values (7301, %s, 'No Flask', 'SALARIO_FIXO', true, 100, true)", (PESSOAL,))
    e = erro(rpc, flask_dsn, 'redefinir_fonte_receita', PESSOAL, 7301, versao_fonte(flask_dsn, 7301), {'ativo': True})
    assert e.diag.message_hint == 'SISTEMA_FLASK'


def receber_sem(dsn, dados, chave=None, usuario=USUARIO_A):
    return rpc(dsn, 'receber_sem_previsao', PESSOAL, dados, chave or str(uuid.uuid4()), usuario=usuario)


def test_recebimento_sem_previsao_credita_e_nao_duplica(banco):
    atual = mes_atual()
    item = nova_fonte(banco, 'Bico', atual, recorrente=False, valor='500.00')
    competencia = somar_meses(atual, 1)
    banco_id = conta_bancaria(banco)
    saldo_antes = sql(banco, 'select financeiro.saldo_da_conta(%s) as s', (banco_id,))[0]['s']
    dados = {'item_receita_id': item, 'data_recebimento': str(competencia), 'valor_recebido': '320.00',
             'competencia': str(competencia), 'conta_bancaria_id': banco_id, 'descricao': 'Bico extra'}
    chave = str(uuid.uuid4())
    r = receber_sem(banco, dados, chave)
    assert receber_sem(banco, dados, chave)['repetida'] is True
    real = sql(banco, 'select * from public.receita_realizada where item_receita_id = %s', (item,))
    assert len(real) == 1 and real[0]['orcamento_id'] is None and real[0]['mes_referencia'] == competencia
    mov = sql(banco, 'select tipo, valor, origem from public.movimento_financeiro where receita_realizada_id = %s', (real[0]['id'],))
    assert mov == [{'tipo': 'CREDITO', 'valor': 320, 'origem': 'RECEITA'}]
    assert sql(banco, 'select financeiro.saldo_da_conta(%s) as s', (banco_id,))[0]['s'] == saldo_antes + 320
    assert r['receita_realizada_id'] == real[0]['id']
    # Previsao criada depois conta este recebimento: falta so a diferenca (a receita nao entra duas vezes).
    nova = rpc(banco, 'criar_receita', PESSOAL, {'item_receita_id': item, 'valor': '500.00', 'competencia': str(competencia)},
               str(uuid.uuid4()))['previsoes'][0]
    falta = chamar(banco, USUARIO_A, 'select financeiro.dados_recebimento_receita(%s, %s)', (PESSOAL, nova))['receita']['falta']
    assert float(falta) == 180
    # Com previsao na competencia, o recebimento vai pela previsao.
    assert erro(receber_sem, banco, dados).diag.message_hint == 'TEM_PREVISAO'
    # O recebimento sem previsao tambem e estornavel.
    estorno = rpc(banco, 'estornar_recebimento', PESSOAL, real[0]['id'], {'motivo': 'teste', 'data_estorno': str(competencia)},
                  str(uuid.uuid4()))
    assert estorno['valor_estornado'] == 320


def test_recebimento_sem_previsao_respeita_escritor_e_perfil(banco, cluster):  # noqa: F811
    item = nova_fonte(banco, 'Do Pessoal', mes_atual(), recorrente=False)
    dados = {'item_receita_id': item, 'data_recebimento': str(somar_meses(mes_atual(), 2)), 'valor_recebido': '10.00',
             'conta_bancaria_id': conta_bancaria(banco)}
    assert erro(receber_sem, banco, dados, usuario=USUARIO_B).pgcode == '42501'
    b = nova_fonte(banco, 'Do B', mes_atual(), recorrente=False, perfil='PERFIL_B', usuario=USUARIO_B)
    assert erro(receber_sem, banco, {**dados, 'item_receita_id': b}).pgcode == '42501'  # fonte de outro perfil
    assert erro(receber_sem, banco, {**dados, 'valor_recebido': '0'}).pgcode == '22023'
    flask_dsn = copiar(cluster)
    sql(flask_dsn, "insert into public.item_receita (id, perfil_financeiro_id, nome, tipo, ativo, recorrente) "
                   "values (7302, %s, 'Flask', 'RENDA_EXTRA', true, false)", (PESSOAL,))
    e = erro(receber_sem, flask_dsn, {**dados, 'item_receita_id': 7302, 'conta_bancaria_id': conta_bancaria(flask_dsn)})
    assert e.diag.message_hint == 'SISTEMA_FLASK'
    assert sql(flask_dsn, 'select count(*) as n from public.receita_realizada where item_receita_id = 7302')[0]['n'] == 0


def test_data_prevista_na_tela(banco):
    atual = mes_atual()
    item = nova_fonte(banco, 'Com data', atual, recorrente=False, valor='100.00')
    orc = sql(banco, 'select id from public.receita_orcamento where item_receita_id = %s', (item,))[0]['id']
    tela = lambda: next(o for o in chamar(banco, USUARIO_A, 'select financeiro.receitas_orcamentos_tela(%s, %s)',  # noqa: E731
                                          (PESSOAL, atual.year)) if o['id'] == orc)
    assert (tela()['data_prevista'], tela()['data_prevista_efetiva']) == (None, str(atual.replace(day=5)))
    seguinte = somar_meses(atual, 1).replace(day=5)
    rpc(banco, 'editar_receita', PESSOAL, orc, sql(banco, 'select financeiro.versao_previsao(%s) as v', (orc,))[0]['v'],
        {'data_prevista': str(seguinte)})
    assert (tela()['data_prevista'], tela()['data_prevista_efetiva']) == (str(seguinte), str(seguinte))


# =====================================================================================================================
# Catalogo global de categorias
# =====================================================================================================================

def gestor(dsn, usuario=USUARIO_A):
    sql(dsn, "select financeiro.definir_gestor_catalogo(%s, true, 'administrador de teste', 'cenario ficticio')", (usuario['id'],))


def sistemicas(dsn):
    """As 10 categorias sistemicas de Mobilidade, como o Flask as cria (categoria_default.obter_categoria_sistemica)."""
    from backend.services.categoria_default import CATEGORIAS_SISTEMICAS_MOBILIDADE
    for codigo, d in CATEGORIAS_SISTEMICAS_MOBILIDADE.items():
        sql(dsn, "insert into public.categoria (nome, descricao, cor, icone, ativo, sistemica, codigo_sistema, modulo_origem, "
                 "bloquear_edicao, bloquear_exclusao) values (%s, %s, %s, %s, true, true, %s, 'mobilidade', true, true)",
            (d['nome'], d['descricao'], d['cor'], d['icone'], codigo))


def catalogo_novo(dsn):
    sistemicas(dsn)
    sql(dsn, "select financeiro.definir_escritor_catalogo('NOVO', 'administrador de teste', 'cenario ficticio')")
    gestor(dsn)


def digest_catalogo(dsn):
    return sql(dsn, "select md5(coalesce(string_agg(c::text, '|' order by c.id), '')) as c, "
                    "(select md5(coalesce(string_agg(p::text, '|' order by p.id), '')) from public.categoria_palavra_chave p) as p "
                    'from public.categoria c')[0]


def cat(dsn, funcao, *args, usuario=USUARIO_A):
    valores = [json.dumps(a) if isinstance(a, dict) else a for a in args]
    marcadores = ', '.join('%s::jsonb' if isinstance(a, dict) else '%s' for a in args)
    return chamar(dsn, usuario, f'select financeiro.{funcao}({marcadores})', valores)


def test_catalogo_nasce_no_flask_e_nada_e_gravado(banco):
    gestor(banco)
    antes = digest_catalogo(banco)
    assert chamar(banco, USUARIO_A, 'select financeiro.situacao_catalogo_categorias()') == {'escritor': 'FLASK', 'gestor': True}
    assert erro(cat, banco, 'criar_categoria', {'nome': 'Nova'}, str(uuid.uuid4())).diag.message_hint == 'CATALOGO_FLASK'
    assert erro(cat, banco, 'editar_categoria', CATEGORIA, {'nome': 'X'}).diag.message_hint == 'CATALOGO_FLASK'
    assert erro(cat, banco, 'excluir_categoria', CATEGORIA).diag.message_hint == 'CATALOGO_FLASK'
    assert erro(cat, banco, 'criar_palavra_chave', CATEGORIA, 'posto').diag.message_hint == 'CATALOGO_FLASK'
    # Sem ser gestora, a conta recebe o mesmo aviso enquanto o catalogo e do Flask; com ele no novo aplicativo, 42501.
    assert erro(cat, banco, 'criar_categoria', {'nome': 'Nova'}, str(uuid.uuid4()), usuario=USUARIO_B).diag.message_hint         == 'CATALOGO_FLASK'
    assert digest_catalogo(banco) == antes
    catalogo_novo(banco)
    antes = digest_catalogo(banco)
    assert erro(cat, banco, 'criar_categoria', {'nome': 'Nova'}, str(uuid.uuid4()), usuario=USUARIO_B).pgcode == '42501'
    assert erro(cat, banco, 'criar_palavra_chave', CATEGORIA, 'x', usuario=USUARIO_B).pgcode == '42501'
    assert digest_catalogo(banco) == antes


def test_troca_do_escritor_exige_sistemicas_auditoria_e_administrador(banco):
    e = erro(sql, banco, "select financeiro.definir_escritor_catalogo('NOVO', 'adm', 'motivo')")
    assert 'MOB_COMBUSTIVEL' in str(e)
    assert 'obrigatorios' in str(erro(sql, banco, "select financeiro.definir_escritor_catalogo('NOVO', '', 'motivo')"))
    for comando in ("select financeiro.definir_escritor_catalogo('NOVO', 'eu', 'eu')",
                    "select financeiro.definir_gestor_catalogo(auth.uid(), true, 'eu', 'eu')"):
        assert erro(chamar, banco, USUARIO_A, comando).pgcode == '42501'  # sem EXECUTE para o navegador
    sistemicas(banco)
    assert sql(banco, "select financeiro.definir_escritor_catalogo('NOVO', 'adm', 'motivo') as r")[0]['r'] == \
        'Catalogo de categorias: FLASK (padrao) -> NOVO'


def test_codigos_sistemicos_iguais_aos_do_flask(banco):
    from backend.services.categoria_default import CATEGORIAS_SISTEMICAS_MOBILIDADE
    banco_sql = {r['codigo']: r['nome'] for r in sql(banco, 'select * from financeiro.categorias_sistemicas_mobilidade()')}
    assert banco_sql == {codigo: d['nome'] for codigo, d in CATEGORIAS_SISTEMICAS_MOBILIDADE.items()}


def test_cadastro_edicao_nomes_e_sistemicas(banco):
    catalogo_novo(banco)
    chave = str(uuid.uuid4())
    criada = cat(banco, 'criar_categoria', {'nome': ' Pets ', 'cor': '#10b981', 'icone': 'paw'}, chave)
    assert cat(banco, 'criar_categoria', {'nome': ' Pets ', 'cor': '#10b981', 'icone': 'paw'}, chave)['repetida'] is True
    linha = sql(banco, 'select * from public.categoria where id = %s', (criada['categoria_id'],))[0]
    assert (linha['nome'], linha['cor'], linha['icone'], linha['ativo'], linha['sistemica'], linha['descricao']) == \
        ('Pets', '#10b981', 'paw', True, False, '')
    assert 'Ja existe' in str(erro(cat, banco, 'criar_categoria', {'nome': 'PETS'}, str(uuid.uuid4())))
    assert 'Ja existe' in str(erro(cat, banco, 'criar_categoria', {'nome': 'combustível'}, str(uuid.uuid4())))
    # Nome reservado mesmo se a sistemica estiver com outro nome no legado (o Flask promoveria a comum a sistemica).
    sql(banco, "update public.categoria set nome = 'Combustivel legado' where codigo_sistema = 'MOB_COMBUSTIVEL'")
    assert erro(cat, banco, 'criar_categoria', {'nome': 'combustível'}, str(uuid.uuid4())).diag.message_hint == 'NOME_SISTEMICO'
    assert 'RRGGBB' in str(erro(cat, banco, 'criar_categoria', {'nome': 'Cor', 'cor': 'red'}, str(uuid.uuid4())))
    cat(banco, 'editar_categoria', criada['categoria_id'], {'nome': 'Animais', 'ativo': False})
    assert sql(banco, 'select nome, ativo from public.categoria where id = %s', (criada['categoria_id'],))[0] == \
        {'nome': 'Animais', 'ativo': False}
    combustivel = sql(banco, "select id from public.categoria where codigo_sistema = 'MOB_COMBUSTIVEL'")[0]['id']
    assert erro(cat, banco, 'editar_categoria', combustivel, {'cor': '#000000'}).diag.message_hint == 'SISTEMICA'
    assert erro(cat, banco, 'excluir_categoria', combustivel).diag.message_hint == 'SISTEMICA'
    assert erro(cat, banco, 'editar_categoria', 999999, {'nome': 'X'}).diag.message_hint == 'NAO_ENCONTRADA'


def test_exclusao_segura_recusa_qualquer_vinculo(banco):
    catalogo_novo(banco)
    com_despesa = cat(banco, 'criar_categoria', {'nome': 'Com despesa'}, str(uuid.uuid4()))['categoria_id']
    sql(banco, "insert into public.item_despesa (nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente) "
               "values ('Antiga', 'Simples', %s, %s, true, false)", (PESSOAL, com_despesa))
    e = erro(cat, banco, 'excluir_categoria', com_despesa)
    assert e.diag.message_hint == 'COM_VINCULOS' and 'item_despesa.categoria_id' in str(e)
    com_compra = cat(banco, 'criar_categoria', {'nome': 'Com compra'}, str(uuid.uuid4()))['categoria_id']
    sql(banco, "insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, categoria_id, descricao, valor, "
               "data_compra, mes_fatura, numero_parcela, total_parcelas) values (%s, 910, %s, 'Historica', 10, '2026-01-10', "
               "'2026-02-01', 1, 1)", (PESSOAL, com_compra))
    e = erro(cat, banco, 'excluir_categoria', com_compra)
    assert e.diag.message_hint == 'COM_VINCULOS' and 'lancamento_agregado.categoria_id' in str(e)
    livre = cat(banco, 'criar_categoria', {'nome': 'Livre'}, str(uuid.uuid4()))['categoria_id']
    cat(banco, 'criar_palavra_chave', livre, 'livre')
    assert cat(banco, 'excluir_categoria', livre) == {'categoria_id': livre, 'excluida': True}
    assert sql(banco, 'select count(*) as n from public.categoria_palavra_chave where categoria_id = %s', (livre,))[0]['n'] == 0
    assert sql(banco, 'select count(*) as n from public.categoria where id in (%s, %s)', (com_despesa, com_compra))[0]['n'] == 2


def test_palavras_chave_normalizadas_reativadas_e_unicas(banco):
    catalogo_novo(banco)
    p = cat(banco, 'criar_palavra_chave', CATEGORIA, '  Posto   SHELL ')
    assert (p['palavra'], p['created']) == ('posto shell', True)
    assert 'ja cadastrada' in str(erro(cat, banco, 'criar_palavra_chave', CATEGORIA, 'posto shell'))
    assert cat(banco, 'remover_palavra_chave', CATEGORIA, p['id'])['ativo'] is False
    de_novo = cat(banco, 'criar_palavra_chave', CATEGORIA, 'POSTO shell')
    assert (de_novo['id'], de_novo['created'], de_novo['ativo']) == (p['id'], False, True)
    assert 'obrigatoria' in str(erro(cat, banco, 'criar_palavra_chave', CATEGORIA, '   '))
    assert erro(cat, banco, 'criar_palavra_chave', 999999, 'x').diag.message_hint == 'NAO_ENCONTRADA'
    assert erro(cat, banco, 'remover_palavra_chave', CATEGORIA, 999999).diag.message_hint == 'NAO_ENCONTRADA'


def test_flask_recusa_escrita_do_catalogo_quando_e_do_novo_aplicativo(banco):
    passos = [('perfil', PESSOAL),
              ('criar', 'post', '/api/categorias', {'nome': 'Flask categoria (ficticia)'}),
              ('palavra', 'post', f'/api/categorias/{CATEGORIA}/palavras-chave', {'palavra': 'flaskpalavra'}),
              ('listar', 'get', '/api/categorias', None)]
    r = flask(banco, passos)  # catalogo no Flask (padrao): grava
    assert r['criar'][0] == 201 and r['palavra'][0] in (200, 201) and r['listar'][0] == 200
    catalogo_novo(banco)
    antes = digest_catalogo(banco)
    r = flask(banco, [('perfil', PESSOAL),
                      ('criar', 'post', '/api/categorias', {'nome': 'Outra Flask (ficticia)'}),
                      ('editar', 'put', f'/api/categorias/{CATEGORIA}', {'nome': 'Renomeada'}),
                      ('palavra', 'post', f'/api/categorias/{CATEGORIA}/palavras-chave', {'palavra': 'outra'}),
                      ('listar', 'get', '/api/categorias', None)])
    for nome in ('criar', 'editar', 'palavra'):
        assert r[nome][0] == 409 and r[nome][1]['codigo'] == 'CATALOGO_NOVO', (nome, r[nome])
    assert r['listar'][0] == 200
    assert digest_catalogo(banco) == antes


# =====================================================================================================================
# Reversao
# =====================================================================================================================

REVERSAO = Path(__file__).resolve().parent.parent / 'supabase' / 'reversao' / '20261125090000_categorias_recorrencias_anterior.sql'


def reverter(dsn):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(REVERSAO.read_text(encoding='utf-8'))  # sem parametros: o texto tem '%'
    finally:
        conn.close()


def test_reversao_recusa_com_ocorrencias_e_restaura_sem_elas(banco, cluster):  # noqa: F811
    nova_recorrencia(banco, 'Gerada', 'semanal_1_1', '2027-03-01')
    gerar_confirmado(banco, mes='2027-03-01')
    assert 'ocorrencias semanais' in str(erro(reverter, banco))
    limpo = copiar(cluster)
    reverter(limpo)
    definicao = sql(limpo, "select pg_get_functiondef('financeiro.plano_recorrencia(integer, date)'::regprocedure) as d")[0]['d']
    assert 'semanas_da_recorrencia' not in definicao and "not in ('mensal', 'anual')" in definicao
    assert sql(limpo, "select to_regclass('financeiro.recorrencia_ocorrencia') as t, "
                      "to_regclass('financeiro.catalogo_categorias') as c")[0] == {'t': None, 'c': None}
    assert not sql(limpo, "select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = "
                          "'financeiro' and p.proname in ('receber_sem_previsao', 'redefinir_fonte_receita', 'criar_categoria')")
