"""
Testes FIN-RECEITAS-1 — consulta e gestao de receitas PREVISTAS.

Cluster PostgreSQL descartavel (copia por teste) com o cenario FICTICIO de receitas abaixo,
sobre o modelo do Flask (item_receita / receita_orcamento / receita_realizada). As funcoes
do schema `financeiro` sao chamadas como o navegador as chama. A comparacao usa o Flask
real (POST /api/receitas/itens, /orcamento e DELETE /itens) num banco identico.
Regra central conferida em todos os testes de escrita: nenhum recebimento, movimento ou
saldo e criado ou alterado.
"""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import date
from decimal import Decimal

import pytest

from tests.supabase_local import claims_usuario
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    ROOT,
    USUARIO_A,
    USUARIO_B,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    digital,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
from psycopg2 import errors  # noqa: E402

pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

D = date
MES = '2027-03-01'
TABELAS_DINHEIRO = ('conta_bancaria', 'movimento_financeiro', 'receita_realizada')


def conta_bancaria(dsn, nome):
    return sql(dsn, 'select id from public.conta_bancaria where nome = %s', (nome,))[0]['id']


def semear(dsn):
    """Cenario ficticio: previsoes, recebimentos (total, parcial, estornado, pontual) e consorcio."""
    pessoal = conta_bancaria(dsn, 'Conta Pessoal (A)')

    def fonte(nome, tipo, perfil, recorrente=True, valor=None, dia=None, conta=None):
        return sql(dsn, 'insert into public.item_receita (perfil_financeiro_id, nome, tipo, descricao, ativo, valor_base_mensal, '
                        'dia_previsto_pagamento, conta_bancaria_id, recorrente) values (%s, %s, %s, %s, true, %s, %s, %s, %s) '
                        'returning id', (perfil, nome, tipo, '', valor, dia, conta, recorrente))[0]['id']

    def previsao(item, perfil, mes, valor, periodicidade='MENSAL_FIXA'):
        return sql(dsn, 'insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, '
                        'valor_esperado, periodicidade) values (%s, %s, %s, %s, %s) returning id',
                   (perfil, item, mes, valor, periodicidade))[0]['id']

    def recebimento(item, perfil, valor, conta=pessoal, descricao=None, observacoes=None, estornar=False):
        rid = sql(dsn, 'insert into public.receita_realizada (perfil_financeiro_id, item_receita_id, data_recebimento, '
                       'valor_recebido, mes_referencia, conta_bancaria_id, descricao, observacoes) values '
                       "(%s, %s, '2027-03-06', %s, %s, %s, %s, %s) returning id",
                  (perfil, item, valor, MES, conta, descricao, observacoes))[0]['id']
        if conta:
            sql(dsn, "insert into public.movimento_financeiro (conta_bancaria_id, tipo, valor, descricao, data_movimento, "
                     "receita_realizada_id, origem) values (%s, 'CREDITO', %s, 'Recebimento', '2027-03-06', %s, 'RECEITA')",
                (conta, valor, rid))
        if estornar:
            sql(dsn, "insert into public.movimento_financeiro (conta_bancaria_id, tipo, valor, descricao, data_movimento, "
                     "receita_realizada_id, origem) values (%s, 'DEBITO', %s, 'Estorno', '2027-03-07', %s, 'ESTORNO_RECEITA')",
                (conta, valor, rid))
        return rid

    ids = {}
    ids['salario'] = fonte('Salario X', 'SALARIO_FIXO', 101, True, '5000.00', 5, pessoal)
    ids['prev_salario'] = previsao(ids['salario'], 101, MES, '5000.00')
    ids['prev_salario_abril'] = previsao(ids['salario'], 101, '2027-04-01', '5000.00')
    ids['real_salario'] = recebimento(ids['salario'], 101, '3000.00')                       # parcial
    ids['aluguel'] = fonte('Aluguel recebido', 'ALUGUEL', None, True, '1200.00', 31)          # legado NULL = Pessoal
    ids['prev_aluguel'] = previsao(ids['aluguel'], None, MES, '1200.00')
    recebimento(ids['aluguel'], None, '1200.00')                                              # recebida
    ids['bonus'] = fonte('Bonus', 'GRATIFICACAO', 101, False)
    ids['real_bonus'] = recebimento(ids['bonus'], 101, '500.00', estornar=True)               # estornada
    ids['consorcio'] = fonte('Contemplação de Consórcio', 'OUTROS', 101, False)
    recebimento(ids['consorcio'], 101, '40000.00', conta=None, descricao='Consórcio Casa - contemplação',
                observacoes='consorcio_id=7')                                                 # prevista (outro modulo)
    recebimento(None, 101, '800.00', descricao='Venda bicicleta')                             # pontual
    ids['aula'] = fonte('Aulas', 'RENDA_EXTRA', 101, False, None, 10)
    ids['prev_aula'] = previsao(ids['aula'], 101, MES, '600.00', 'UNICA')                     # prevista
    ids['consultoria'] = fonte('Consultoria', 'RENDA_EXTRA', 102, False)
    ids['prev_consultoria'] = previsao(ids['consultoria'], 102, MES, '3000.00', 'UNICA')
    ids['freela'] = fonte('Freela B', 'RENDA_EXTRA', 103, False)
    ids['prev_freela'] = previsao(ids['freela'], 103, MES, '700.00', 'UNICA')
    return ids


@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    dsn_ids = semear(dsn)
    return dsn, dsn_ids


def rpc(dsn, funcao, *args, usuario=USUARIO_A):
    valores = [json.dumps(a) if isinstance(a, dict) else a for a in args]
    marcadores = ', '.join('%s::jsonb' if isinstance(a, dict) else '%s' for a in args)
    return chamar(dsn, usuario, f'select financeiro.{funcao}({marcadores})', valores)


def receitas(dsn, perfil='PESSOAL', mes=MES, usuario=USUARIO_A):
    return chamar(dsn, usuario, "select coalesce(json_agg(x), '[]'::json) from financeiro.receitas_do_mes(%s, %s) x",
                  (ID.get(perfil, perfil), mes))


def por_nome(linhas):
    return {x['nome']: x for x in linhas}


def criar(dsn, dados, perfil='PESSOAL', usuario=USUARIO_A, chave=None):
    return rpc(dsn, 'criar_receita', ID.get(perfil, perfil), dados, chave or str(uuid.uuid4()), usuario=usuario)


def edicao(dsn, orcamento, perfil='PESSOAL', usuario=USUARIO_A):
    return rpc(dsn, 'receita_para_edicao', ID.get(perfil, perfil), orcamento, usuario=usuario)


def editar(dsn, orcamento, dados, perfil='PESSOAL', usuario=USUARIO_A, versao=None):
    versao = versao or edicao(dsn, orcamento, perfil, usuario)['versao']
    return rpc(dsn, 'editar_receita', ID.get(perfil, perfil), orcamento, versao, dados, usuario=usuario)


def excluir(dsn, orcamento, perfil='PESSOAL', usuario=USUARIO_A, versao=None):
    versao = versao or edicao(dsn, orcamento, perfil, usuario)['versao']
    return rpc(dsn, 'excluir_receita', ID.get(perfil, perfil), orcamento, versao, usuario=usuario)


def orcamento(dsn, orc_id):
    linhas = sql(dsn, 'select * from public.receita_orcamento where id = %s', (orc_id,))
    return linhas[0] if linhas else None


def fonte(dsn, item_id):
    linhas = sql(dsn, 'select * from public.item_receita where id = %s', (item_id,))
    return linhas[0] if linhas else None


NOVA = {'nome': 'Plantao extra', 'tipo': 'RENDA_EXTRA', 'valor': '1500.00', 'competencia': '2027-06-01',
        'dia_previsto': 15, 'observacoes': 'Plantao de junho'}


# ---------------------------------------------------------------------------
# Consulta: situacao a partir dos registros reais (como a tela de receitas do Flask)
# ---------------------------------------------------------------------------

def _status_flask(previsto, recebido):
    """Porta de obterStatusReceita (frontend/static/js/receitas.js)."""
    if recebido > 0 and (previsto <= 0 or recebido >= previsto):
        return 'REALIZADA'
    if recebido > 0:
        return 'PARCIAL'
    return 'PREVISTA'


def test_situacoes_refletem_os_registros_reais(banco):
    dsn, ids = banco
    linhas = por_nome(receitas(dsn))
    resumo = {n: (x['origem'], x['situacao'], x['valor_previsto'], x['valor_recebido']) for n, x in linhas.items()}
    assert resumo == {
        'Salario X': ('PREVISAO', 'PARCIAL', 5000.0, 3000.0),
        'Aluguel recebido': ('PREVISAO', 'RECEBIDA', 1200.0, 1200.0),
        'Aulas': ('PREVISAO', 'PREVISTA', 600.0, 0),
        'Bonus': ('RECEBIMENTO', 'ESTORNADA', None, 500.0),
        'Contemplação de Consórcio': ('RECEBIMENTO', 'PREVISTA_CONSORCIO', 40000.0, 0),
        'Venda bicicleta': ('RECEBIMENTO', 'RECEBIDA', None, 800.0),
    }
    assert linhas['Salario X']['data_prevista'] == '2027-03-05'
    assert linhas['Aluguel recebido']['data_prevista'] == '2027-03-31'
    assert linhas['Salario X']['conta_bancaria_nome'] == 'Conta Pessoal (A)'
    # Mesma classificacao da tela do Flask para as previsoes (RECEBIDA = 'REALIZADA' la).
    for nome in ('Salario X', 'Aluguel recebido', 'Aulas'):
        x = linhas[nome]
        esperado = _status_flask(x['valor_previsto'], x['valor_recebido'])
        assert x['situacao'] == {'REALIZADA': 'RECEBIDA'}.get(esperado, esperado)


def test_consulta_nao_grava_nada(banco):
    dsn, _ = banco
    antes = digital(dsn, tabelas=('item_receita', 'receita_orcamento', *TABELAS_DINHEIRO))
    receitas(dsn)
    rpc(dsn, 'fontes_de_receita', ID['PESSOAL'])
    assert digital(dsn, tabelas=('item_receita', 'receita_orcamento', *TABELAS_DINHEIRO)) == antes


def test_perfis_isolados_pessoal_empresa_e_perfil_b(banco):
    dsn, _ = banco
    assert set(por_nome(receitas(dsn, 'EMPRESA'))) == {'Consultoria'}
    assert set(por_nome(receitas(dsn, 'PERFIL_B', usuario=USUARIO_B))) == {'Freela B'}
    assert 'Consultoria' not in por_nome(receitas(dsn)) and 'Freela B' not in por_nome(receitas(dsn))


# ---------------------------------------------------------------------------
# 1-4, 9. Cadastro: avulsa, competencia x data prevista, categoria, conta, recorrencia
# ---------------------------------------------------------------------------

def test_cadastro_de_prevista_nao_cria_recebimento_nem_movimento(banco):
    dsn, _ = banco
    antes = digital(dsn, tabelas=TABELAS_DINHEIRO)
    r = criar(dsn, {**NOVA, 'conta_bancaria_id': conta_bancaria(dsn, 'Conta Pessoal (A)')})
    f, o = fonte(dsn, r['item_receita_id']), orcamento(dsn, r['previsoes'][0])
    assert (f['nome'], f['tipo'], f['recorrente'], f['dia_previsto_pagamento'], f['ativo'], f['perfil_financeiro_id']) == \
        ('Plantao extra', 'RENDA_EXTRA', False, 15, True, ID['PESSOAL'])
    assert (o['mes_referencia'], o['valor_esperado'], o['periodicidade'], o['observacoes']) == \
        (D(2027, 6, 1), Decimal('1500.00'), 'UNICA', 'Plantao de junho')
    junho = por_nome(receitas(dsn, mes='2027-06-01'))['Plantao extra']
    assert (junho['situacao'], junho['valor_recebido'], junho['data_prevista']) == ('PREVISTA', 0, '2027-06-15')
    assert digital(dsn, tabelas=TABELAS_DINHEIRO) == antes  # previsto nao e dinheiro recebido


def test_data_prevista_e_o_dia_da_fonte_na_competencia(banco):
    dsn, _ = banco
    criar(dsn, {**NOVA, 'competencia': '2027-02-01', 'dia_previsto': 31})
    assert por_nome(receitas(dsn, mes='2027-02-01'))['Plantao extra']['data_prevista'] == '2027-02-28'


@pytest.mark.parametrize('dados,mensagem', [
    ({'tipo': 'PIX'}, 'Categoria'),
    ({'valor': '-1'}, 'positivo'),
    ({'valor': '1.234'}, '2 casas'),
    ({'competencia': 'amanha'}, 'Competencia'),
    ({'dia_previsto': 32}, 'Dia previsto'),
    ({'nome': ''}, 'Nome da fonte'),
    ({'nome': 'Salario X'}, 'Ja existe uma fonte'),
    ({'valor_recebido': '10'}, 'Recebimento nao e registrado aqui'),
])
def test_dados_invalidos_recusados_sem_gravar(banco, dados, mensagem):
    dsn, _ = banco
    antes = digital(dsn, tabelas=('item_receita', 'receita_orcamento'))
    with pytest.raises(errors.InvalidParameterValue, match=mensagem):
        criar(dsn, {**NOVA, **dados})
    assert digital(dsn, tabelas=('item_receita', 'receita_orcamento')) == antes


def test_conta_bancaria_de_destino_ativa_e_do_perfil(banco):
    dsn, _ = banco
    for invalida in (conta_bancaria(dsn, 'Conta Empresa (A)'), conta_bancaria(dsn, 'Conta Perfil B')):
        with pytest.raises(errors.InvalidParameterValue, match='Conta bancaria de destino'):
            criar(dsn, {**NOVA, 'conta_bancaria_id': invalida})
    legado = conta_bancaria(dsn, 'Carteira legado sem perfil')
    r = criar(dsn, {**NOVA, 'conta_bancaria_id': legado})
    assert fonte(dsn, r['item_receita_id'])['conta_bancaria_id'] == legado


def test_recorrente_gera_12_previsoes_a_partir_da_competencia(banco):
    dsn, _ = banco
    r = criar(dsn, {**NOVA, 'nome': 'Pro-labore', 'tipo': 'SALARIO_FIXO', 'valor': '7000.00', 'recorrente': True})
    previsoes = sql(dsn, 'select mes_referencia, valor_esperado, periodicidade, observacoes from public.receita_orcamento '
                         'where item_receita_id = %s order by 1', (r['item_receita_id'],))
    assert [p['mes_referencia'] for p in previsoes] == [D(2027 + (5 + i) // 12, (5 + i) % 12 + 1, 1) for i in range(12)]
    assert {(p['valor_esperado'], p['periodicidade'], p['observacoes']) for p in previsoes} == \
        {(Decimal('7000.00'), 'MENSAL_FIXA', 'Gerado automaticamente - Pro-labore')}
    f = fonte(dsn, r['item_receita_id'])
    assert (f['recorrente'], f['valor_base_mensal']) == (True, Decimal('7000.00'))


def test_previsao_de_fonte_existente_e_duplicidade_na_competencia(banco):
    dsn, ids = banco
    r = criar(dsn, {'item_receita_id': ids['aula'], 'valor': '650.00', 'competencia': '2027-04-01'})
    assert orcamento(dsn, r['previsoes'][0])['periodicidade'] == 'UNICA'
    with pytest.raises(errors.InvalidParameterValue, match='Ja existe previsao'):
        criar(dsn, {'item_receita_id': ids['aula'], 'valor': '650.00', 'competencia': '2027-04-01'})
    with pytest.raises(errors.InvalidParameterValue, match='outro modulo'):
        criar(dsn, {'item_receita_id': ids['consorcio'], 'valor': '1.00', 'competencia': '2027-05-01'})


# ---------------------------------------------------------------------------
# 5-8. Edicao, bloqueios apos recebimento (inclusive parcial), exclusao segura
# ---------------------------------------------------------------------------

def test_edicao_antes_do_recebimento(banco):
    dsn, ids = banco
    e = edicao(dsn, ids['prev_aula'])
    assert (e['pode_editar'], e['pode_excluir'], e['pode_mudar_competencia'], e['bloqueio']) == (True, True, True, None)
    novo = editar(dsn, ids['prev_aula'], {'valor': '720.00', 'observacoes': 'Turma extra', 'competencia': '2027-05-01'})
    o = orcamento(dsn, ids['prev_aula'])
    assert (o['valor_esperado'], o['observacoes'], o['mes_referencia']) == (Decimal('720.00'), 'Turma extra', D(2027, 5, 1))
    assert 'Aulas' in por_nome(receitas(dsn, mes='2027-05-01')) and 'Aulas' not in por_nome(receitas(dsn))
    assert novo['versao'] != e['versao']


def test_recorrente_nao_muda_de_competencia(banco):
    dsn, ids = banco
    with pytest.raises(errors.InvalidParameterValue, match='recorrente nao muda'):
        editar(dsn, ids['prev_salario_abril'], {'competencia': '2027-06-01'})


@pytest.mark.parametrize('chave_previsao', ['prev_salario', 'prev_aluguel'])  # parcial e total
def test_previsao_com_recebimento_nao_e_editada_nem_excluida(banco, chave_previsao):
    dsn, ids = banco
    antes = (orcamento(dsn, ids[chave_previsao]), digital(dsn, tabelas=TABELAS_DINHEIRO))
    e = edicao(dsn, ids[chave_previsao])
    assert (e['pode_editar'], e['pode_excluir'], e['bloqueio']) == (False, False, 'Ha recebimento registrado nesta competencia')
    with pytest.raises(errors.RaiseException, match='Operacao bloqueada'):
        editar(dsn, ids[chave_previsao], {'valor': '1.00'}, versao=e['versao'])
    with pytest.raises(errors.RaiseException, match='Operacao bloqueada'):
        excluir(dsn, ids[chave_previsao], versao=e['versao'])
    assert (orcamento(dsn, ids[chave_previsao]), digital(dsn, tabelas=TABELAS_DINHEIRO)) == antes


def test_recebimento_estornado_tambem_preserva_a_previsao(banco):
    dsn, ids = banco
    prev = sql(dsn, "insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, "
                    "valor_esperado, periodicidade) values (101, %s, %s, 500, 'UNICA') returning id",
               (ids['bonus'], MES))[0]['id']
    assert edicao(dsn, prev)['bloqueio'] == 'Ha recebimento registrado nesta competencia'


def test_exclusao_de_avulsa_remove_previsao_e_fonte_sem_orfaos(banco):
    dsn, _ = banco
    r = criar(dsn, NOVA)
    resultado = excluir(dsn, r['previsoes'][0])
    assert resultado == {'orcamento_id': r['previsoes'][0], 'modo': 'EXCLUIDA', 'fonte_excluida': True}
    assert orcamento(dsn, r['previsoes'][0]) is None and fonte(dsn, r['item_receita_id']) is None


def test_exclusao_de_recorrente_zera_como_o_flask_e_aparece_removida(banco):
    dsn, ids = banco
    resultado = excluir(dsn, ids['prev_salario_abril'])
    o = orcamento(dsn, ids['prev_salario_abril'])
    assert resultado['modo'] == 'ZERADA' and (o['valor_esperado'], o['observacoes']) == (Decimal('0.00'), 'Removido pelo usuário')
    assert por_nome(receitas(dsn, mes='2027-04-01'))['Salario X']['situacao'] == 'REMOVIDA'
    assert fonte(dsn, ids['salario']) is not None


def test_fonte_do_modulo_de_consorcios_e_bloqueada(banco):
    dsn, ids = banco
    prev = sql(dsn, "insert into public.receita_orcamento (perfil_financeiro_id, item_receita_id, mes_referencia, "
                    "valor_esperado) values (101, %s, '2027-05-01', 1) returning id", (ids['consorcio'],))[0]['id']
    e = edicao(dsn, prev)
    assert e['bloqueio'] == 'Gerada pelo modulo de consorcios' and not e['pode_editar_fonte']
    with pytest.raises(errors.RaiseException, match='consorcios'):
        rpc(dsn, 'inativar_fonte_receita', ID['PESSOAL'], ids['consorcio'], e['versao_fonte'])


def test_editar_e_inativar_fonte_preservam_previsoes_e_recebimentos(banco):
    dsn, ids = banco
    antes = (sql(dsn, 'select md5(t::text) as h from public.receita_orcamento t where item_receita_id = %s order by id',
                 (ids['salario'],)), digital(dsn, tabelas=TABELAS_DINHEIRO))
    e = edicao(dsn, ids['prev_salario'])
    assert e['pode_editar_fonte'] and e['pode_inativar_fonte']  # a fonte pode, a previsao recebida nao
    novo = rpc(dsn, 'editar_fonte_receita', ID['PESSOAL'], ids['salario'], e['versao_fonte'],
               {'nome': 'Salario Y', 'dia_previsto': 7, 'tipo': 'SALARIO_FIXO'})
    rpc(dsn, 'inativar_fonte_receita', ID['PESSOAL'], ids['salario'], novo['versao'])
    f = fonte(dsn, ids['salario'])
    assert (f['nome'], f['dia_previsto_pagamento'], f['ativo']) == ('Salario Y', 7, False)
    assert (sql(dsn, 'select md5(t::text) as h from public.receita_orcamento t where item_receita_id = %s order by id',
                (ids['salario'],)), digital(dsn, tabelas=TABELAS_DINHEIRO)) == antes
    linhas = por_nome(receitas(dsn, mes='2027-04-01'))
    assert linhas['Salario Y']['situacao'] == 'INATIVA'
    with pytest.raises(errors.InvalidParameterValue, match='outra fonte com este nome'):
        rpc(dsn, 'editar_fonte_receita', ID['PESSOAL'], ids['aula'], edicao(dsn, ids['prev_aula'])['versao_fonte'],
            {'nome': 'Salario Y'})


# ---------------------------------------------------------------------------
# 10-15. Autorizacao
# ---------------------------------------------------------------------------

def test_empresa_com_gestor_cadastra_so_na_empresa(banco):
    dsn, _ = banco
    sql(dsn, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s",
        (ID['EMPRESA'],))
    criar(dsn, {**NOVA, 'nome': 'Contrato empresa'}, perfil='EMPRESA')
    assert 'Contrato empresa' in por_nome(receitas(dsn, 'EMPRESA', '2027-06-01'))
    assert 'Contrato empresa' not in por_nome(receitas(dsn, 'PESSOAL', '2027-06-01'))


def test_leitor_ve_mas_nao_escreve(banco):
    dsn, ids = banco
    e = edicao(dsn, ids['prev_consultoria'], 'EMPRESA')
    assert (e['pode_gerir'], e['pode_editar'], e['pode_excluir'], e['pode_editar_fonte']) == (False, False, False, False)
    antes = digital(dsn, tabelas=('item_receita', 'receita_orcamento'))
    for chamada in (lambda: criar(dsn, NOVA, 'EMPRESA'),
                    lambda: editar(dsn, ids['prev_consultoria'], {'valor': '1.00'}, 'EMPRESA', versao=e['versao']),
                    lambda: excluir(dsn, ids['prev_consultoria'], 'EMPRESA', versao=e['versao']),
                    lambda: rpc(dsn, 'inativar_fonte_receita', ID['EMPRESA'], ids['consultoria'], e['versao_fonte'])):
        with pytest.raises(errors.InsufficientPrivilege):
            chamada()
    assert digital(dsn, tabelas=('item_receita', 'receita_orcamento')) == antes


def test_outro_perfil_e_parametros_manipulados(banco):
    dsn, ids = banco
    versao = edicao(dsn, ids['prev_aula'])['versao']
    for chamada in (lambda: receitas(dsn, 'PESSOAL', usuario=USUARIO_B),
                    lambda: edicao(dsn, ids['prev_aula'], 'PERFIL_B', USUARIO_B),
                    lambda: editar(dsn, ids['prev_aula'], {'valor': '1.00'}, 'PERFIL_B', USUARIO_B, versao=versao),
                    lambda: excluir(dsn, ids['prev_aula'], 'PERFIL_B', USUARIO_B, versao=versao),
                    lambda: criar(dsn, {'item_receita_id': ids['aula'], 'valor': '1', 'competencia': '2027-09-01'},
                                  'PERFIL_B', USUARIO_B),
                    lambda: criar(dsn, NOVA, 'PESSOAL', USUARIO_B)):
        with pytest.raises(errors.InsufficientPrivilege):
            chamada()
    assert orcamento(dsn, ids['prev_aula'])['valor_esperado'] == Decimal('600.00')


@pytest.mark.parametrize('comando', [
    "select count(*) from financeiro.receitas_do_mes(101, '2027-03-01')",
    "select count(*) from financeiro.fontes_de_receita(101)",
    "select financeiro.receita_para_edicao(101, 1)",
    "select financeiro.criar_receita(101, '{}'::jsonb, gen_random_uuid())",
    "select financeiro.editar_receita(101, 1, 'x', '{}'::jsonb)",
    "select financeiro.excluir_receita(101, 1, 'x')",
    "select financeiro.editar_fonte_receita(101, 1, 'x', '{}'::jsonb)",
    "select financeiro.inativar_fonte_receita(101, 1, 'x')",
])
def test_anonimo_nao_executa(banco, comando):
    dsn, _ = banco
    with pytest.raises(errors.InsufficientPrivilege, match='permission denied'):
        chamar(dsn, None, comando)


@pytest.mark.parametrize('comando', [
    "select financeiro.bloqueio_da_previsao(1)",
    "select financeiro.travar_previsao(101, 1, 'x')",
    "select financeiro.ler_dados_receita('{}'::jsonb, 101, true)",
    'select count(*) from financeiro.operacao_receita',
    "insert into public.receita_orcamento (item_receita_id, mes_referencia, valor_esperado) values (1, '2027-01-01', 1)",
    'select count(*) from public.receita_realizada',
])
def test_navegador_nao_acessa_internas_nem_tabelas(banco, comando):
    dsn, _ = banco
    with pytest.raises(errors.InsufficientPrivilege, match='permission denied'):
        chamar(dsn, USUARIO_A, comando)


# ---------------------------------------------------------------------------
# 16-18. Concorrencia e idempotencia; recebimento simultaneo (como o do Flask)
# ---------------------------------------------------------------------------

def _paralelo(funcoes):
    barreira = threading.Barrier(len(funcoes))
    resultados = [None] * len(funcoes)

    def executar(i, funcao):
        barreira.wait(10)
        try:
            resultados[i] = ('ok', funcao())
        except Exception as exc:  # noqa: BLE001
            resultados[i] = ('erro', exc)

    tarefas = [threading.Thread(target=executar, args=(i, f)) for i, f in enumerate(funcoes)]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join(60)
    return resultados


def test_chave_idempotente_repetida_e_simultanea(banco):
    dsn, _ = banco
    chave = str(uuid.uuid4())
    primeira = criar(dsn, NOVA, chave=chave)
    segunda = criar(dsn, NOVA, chave=chave)
    assert segunda == {**primeira, 'repetida': True}
    assert sql(dsn, "select count(*) as n from public.item_receita where nome = 'Plantao extra'")[0]['n'] == 1
    chave2 = str(uuid.uuid4())
    resultados = _paralelo([lambda: criar(dsn, {**NOVA, 'nome': 'Paralela'}, chave=chave2) for _ in range(3)])
    assert [r[0] for r in resultados] == ['ok'] * 3
    assert sql(dsn, "select count(*) as n from public.item_receita where nome = 'Paralela'")[0]['n'] == 1


def test_cadastros_simultaneos_da_mesma_fonte_nao_duplicam(banco):
    dsn, _ = banco
    resultados = _paralelo([lambda: criar(dsn, {**NOVA, 'nome': 'Mesma fonte'}) for _ in range(3)])
    assert sorted(r[0] for r in resultados) == ['erro', 'erro', 'ok']
    assert sql(dsn, "select count(*) as n from public.item_receita where nome = 'Mesma fonte'")[0]['n'] == 1
    assert sql(dsn, "select count(*) as n from public.receita_orcamento o join public.item_receita i "
                    "on i.id = o.item_receita_id where i.nome = 'Mesma fonte'")[0]['n'] == 1


def test_edicoes_simultaneas_da_mesma_versao_so_uma_vale(banco):
    dsn, ids = banco
    versao = edicao(dsn, ids['prev_aula'])['versao']
    resultados = _paralelo([lambda v=v: editar(dsn, ids['prev_aula'], {'valor': v}, versao=versao) for v in ('610.00', '620.00')])
    assert sorted(r[0] for r in resultados) == ['erro', 'ok']
    assert 'alterada por outra operacao' in str(next(r[1] for r in resultados if r[0] == 'erro'))


def test_recebimento_em_andamento_bloqueia_a_edicao_quando_termina(banco):
    """Recebimento (como o do Flask) em transacao aberta: a edicao espera e depois ve o recebimento."""
    dsn, ids = banco
    versao = edicao(dsn, ids['prev_aula'])['versao']
    recebimento = psycopg2.connect(dsn)
    cur = recebimento.cursor()
    cur.execute("insert into public.receita_realizada (perfil_financeiro_id, item_receita_id, data_recebimento, "
                "valor_recebido, mes_referencia) values (101, %s, '2027-03-10', 600, %s)", (ids['aula'], MES))
    resultado = {}

    def tentar():
        try:
            editar(dsn, ids['prev_aula'], {'valor': '999.00'}, versao=versao)
            resultado['ok'] = True
        except Exception as exc:  # noqa: BLE001
            resultado['erro'] = exc

    tarefa = threading.Thread(target=tentar)
    tarefa.start()
    time.sleep(1.5)
    assert tarefa.is_alive()  # esperando o recebimento terminar
    recebimento.commit()
    recebimento.close()
    tarefa.join(30)
    assert 'Ha recebimento registrado' in str(resultado['erro'])
    assert orcamento(dsn, ids['prev_aula'])['valor_esperado'] == Decimal('600.00')


def test_recebimento_durante_a_edicao_espera_a_edicao_terminar(banco):
    dsn, ids = banco
    versao = edicao(dsn, ids['prev_aula'])['versao']
    edicao_conn = psycopg2.connect(dsn)
    cur = edicao_conn.cursor()
    cur.execute('set local role authenticated')
    cur.execute("select set_config('request.jwt.claims', %s, true)",
                (json.dumps(claims_usuario(USUARIO_A)),))
    cur.execute("select financeiro.editar_receita(%s, %s, %s, %s::jsonb)",
                (ID['PESSOAL'], ids['prev_aula'], versao, json.dumps({'valor': '650.00'})))  # transacao aberta
    inicio = {}

    def receber():
        conn = psycopg2.connect(dsn)
        with conn, conn.cursor() as c:
            c.execute("insert into public.receita_realizada (perfil_financeiro_id, item_receita_id, data_recebimento, "
                      "valor_recebido, mes_referencia) values (101, %s, '2027-03-10', 650, %s)", (ids['aula'], MES))
        conn.close()
        inicio['fim'] = time.monotonic()

    tarefa = threading.Thread(target=receber)
    tarefa.start()
    time.sleep(1.5)
    assert 'fim' not in inicio  # o recebimento espera a edicao
    commit = time.monotonic()
    edicao_conn.commit()
    edicao_conn.close()
    tarefa.join(30)
    assert inicio['fim'] >= commit
    assert por_nome(receitas(dsn))['Aulas']['situacao'] == 'RECEBIDA'  # 650 recebido sobre 650 previsto


# ---------------------------------------------------------------------------
# 19-20. Saldos e movimentos preservados em todas as operacoes
# ---------------------------------------------------------------------------

def test_nenhuma_operacao_toca_saldos_movimentos_ou_recebimentos(banco):
    dsn, ids = banco
    antes = digital(dsn, tabelas=TABELAS_DINHEIRO)
    r = criar(dsn, NOVA)
    rec = criar(dsn, {**NOVA, 'nome': 'Mensal novo', 'recorrente': True})
    editar(dsn, r['previsoes'][0], {'valor': '1600.00'})
    excluir(dsn, r['previsoes'][0])
    excluir(dsn, rec['previsoes'][3])
    e = edicao(dsn, ids['prev_aula'])
    rpc(dsn, 'editar_fonte_receita', ID['PESSOAL'], ids['aula'], e['versao_fonte'], {'dia_previsto': 12})
    rpc(dsn, 'inativar_fonte_receita', ID['PESSOAL'], ids['aula'], edicao(dsn, ids['prev_aula'])['versao_fonte'])
    assert digital(dsn, tabelas=TABELAS_DINHEIRO) == antes


# ---------------------------------------------------------------------------
# 21. Equivalencia com as regras validas do Flask
# ---------------------------------------------------------------------------

_SCRIPT_FLASK = """
import json, sys
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    if not Usuario.query.filter_by(email='flask.receitas@teste.local').first():
        u = Usuario(email='flask.receitas@teste.local', nome='Receitas', ativo=True)
        u.definir_senha('Senha-ficticia-receitas-2026')
        db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.receitas@teste.local', 'senha': 'Senha-ficticia-receitas-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': 101}).status_code == 200
saida = []
for metodo, rota, corpo in json.loads(sys.argv[1]):
    r = getattr(c, metodo)(rota, json=corpo)
    saida.append({'status': r.status_code, 'json': r.get_json()})
print('FLASK ' + json.dumps(saida))
"""


def flask(dsn, chamadas):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT_FLASK, json.dumps(chamadas)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads([linha for linha in r.stdout.splitlines() if linha.startswith('FLASK ')][-1][6:])


def _sem_ids(linha, extras=()):
    return {k: v for k, v in linha.items() if k not in ('id', 'item_receita_id', 'criado_em', *extras)}


def test_equivalencia_com_o_flask_no_cadastro_de_fonte_recorrente(cluster):  # noqa: F811
    dsn_flask, dsn_novo = copiar(cluster), copiar(cluster)
    hoje = date.today().replace(day=1)
    conta_f, conta_n = conta_bancaria(dsn_flask, 'Conta Pessoal (A)'), conta_bancaria(dsn_novo, 'Conta Pessoal (A)')
    flask(dsn_flask, [['post', '/api/receitas/itens', {'nome': 'Salario Z', 'tipo': 'SALARIO_FIXO', 'valor_base_mensal': 4321.5,
                                                        'dia_previsto_pagamento': 5, 'conta_bancaria_id': conta_f,
                                                        'recorrente': True}]])
    criar(dsn_novo, {'nome': 'Salario Z', 'tipo': 'SALARIO_FIXO', 'valor': '4321.50', 'dia_previsto': 5,
                     'conta_bancaria_id': conta_n, 'recorrente': True, 'competencia': hoje.isoformat()})
    f = sql(dsn_flask, "select * from public.item_receita where nome = 'Salario Z'")
    n = sql(dsn_novo, "select * from public.item_receita where nome = 'Salario Z'")
    assert [_sem_ids(x) for x in n] == [_sem_ids(x) for x in f]
    consulta = ("select o.* from public.receita_orcamento o join public.item_receita i on i.id = o.item_receita_id "
                "where i.nome = 'Salario Z' order by o.mes_referencia")
    assert [_sem_ids(x) for x in sql(dsn_novo, consulta)] == [_sem_ids(x) for x in sql(dsn_flask, consulta)]
    assert len(sql(dsn_novo, consulta)) == 12


def test_equivalencia_com_o_flask_previsao_exclusao_e_inativacao(cluster):  # noqa: F811
    dsn_flask, dsn_novo = copiar(cluster), copiar(cluster)
    ids_f, ids_n = semear(dsn_flask), semear(dsn_novo)
    # Previsao avulsa de fonte existente (UNICA) e "excluir" previsao recorrente (zera com a marca do Flask).
    flask(dsn_flask, [['post', '/api/receitas/orcamento', {'item_receita_id': ids_f['aula'], 'ano_mes': '2027-04-01',
                                                            'valor_previsto': 650, 'periodicidade': 'UNICA'}],
                      ['post', '/api/receitas/orcamento', {'item_receita_id': ids_f['salario'], 'ano_mes': '2027-04-01',
                                                            'valor_previsto': 0, 'periodicidade': 'MENSAL_FIXA',
                                                            'observacoes': 'Removido pelo usuário'}],
                      ['post', '/api/perfis-financeiros/ativo', {'perfil_id': ID['EMPRESA']}],
                      ['delete', f"/api/receitas/itens/{ids_f['consultoria']}", None]])
    criar(dsn_novo, {'item_receita_id': ids_n['aula'], 'valor': '650.00', 'competencia': '2027-04-01'})
    excluir(dsn_novo, ids_n['prev_salario_abril'])
    sql(dsn_novo, "update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true where perfil_financeiro_id = %s",
        (ID['EMPRESA'],))
    e = rpc(dsn_novo, 'receita_para_edicao', ID['EMPRESA'], ids_n['prev_consultoria'])
    rpc(dsn_novo, 'inativar_fonte_receita', ID['EMPRESA'], ids_n['consultoria'], e['versao_fonte'])
    consulta = 'select * from public.receita_orcamento order by item_receita_id, mes_referencia'
    assert [_sem_ids(x, ('item_receita_id',)) for x in sql(dsn_novo, consulta)] == \
        [_sem_ids(x, ('item_receita_id',)) for x in sql(dsn_flask, consulta)]
    assert [_sem_ids(x) for x in sql(dsn_novo, 'select * from public.item_receita order by id')] == \
        [_sem_ids(x) for x in sql(dsn_flask, 'select * from public.item_receita order by id')]
