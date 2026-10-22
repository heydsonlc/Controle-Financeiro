"""
Testes FIN-DESPESAS-1 — cadastro, edicao, inativacao e exclusao segura de despesas.

Cluster PostgreSQL descartavel com o cenario FICTICIO do FIN-RECORRENCIA-1 (copia por
teste). As operacoes passam pelas funcoes do schema `financeiro` como o navegador as
chama (papel authenticated + claims). A comparacao com o Flask usa o Flask real
(POST/PUT/DELETE de /api/despesas e POST /api/recorrencias) num banco identico.
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

from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    ROOT,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    digital,
    gerar,
    previa,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
from psycopg2 import errors  # noqa: E402

pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

D = date
MORADIA, ASSINATURAS = 951, 952
AVULSA = {'nome': 'Conserto geladeira', 'valor': '350.40', 'categoria_id': MORADIA, 'data_vencimento': '2029-07-05'}


@pytest.fixture
def banco(cluster):  # noqa: F811
    """Copia com Pessoal e Perfil B no novo gerador (T1); Empresa no Flask, A so LEITOR nela."""
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    return dsn


def rpc(dsn, funcao, *args, usuario=USUARIO_A):
    valores = [json.dumps(a) if isinstance(a, dict) else a for a in args]
    marcadores = ', '.join('%s::jsonb' if isinstance(a, dict) else '%s' for a in args)
    return chamar(dsn, usuario, f'select financeiro.{funcao}({marcadores})', valores)


def criar(dsn, dados=None, perfil='PESSOAL', usuario=USUARIO_A, chave=None):
    return rpc(dsn, 'criar_despesa', ID.get(perfil, perfil), dados or AVULSA, chave or str(uuid.uuid4()), usuario=usuario)


def edicao(dsn, conta_id, perfil='PESSOAL', usuario=USUARIO_A):
    return rpc(dsn, 'despesa_para_edicao', ID.get(perfil, perfil), conta_id, usuario=usuario)


def editar(dsn, conta_id, dados, perfil='PESSOAL', usuario=USUARIO_A, versao=None):
    versao = versao or edicao(dsn, conta_id, perfil, usuario)['versao']
    return rpc(dsn, 'editar_despesa', ID.get(perfil, perfil), conta_id, versao, dados, usuario=usuario)


def excluir(dsn, conta_id, perfil='PESSOAL', usuario=USUARIO_A, versao=None):
    versao = versao or edicao(dsn, conta_id, perfil, usuario)['versao']
    return rpc(dsn, 'excluir_despesa', ID.get(perfil, perfil), conta_id, versao, usuario=usuario)


def contas_mes(dsn, mes, perfil='PESSOAL', usuario=USUARIO_A):
    return chamar(dsn, usuario, "select coalesce(json_agg(x), '[]'::json) from financeiro.contas_do_mes(%s, %s) x",
                  (ID.get(perfil, perfil), mes))


def conta(dsn, conta_id):
    linhas = sql(dsn, 'select * from public.conta where id = %s', (conta_id,))
    return linhas[0] if linhas else None


def item(dsn, item_id):
    linhas = sql(dsn, 'select * from public.item_despesa where id = %s', (item_id,))
    return linhas[0] if linhas else None


def md5_conta(dsn, conta_id):
    return sql(dsn, 'select md5(t::text) as h from public.conta t where id = %s', (conta_id,))[0]['h']


def da_recorrencia(dsn, mes, nome):
    return next(x['id'] for x in contas_mes(dsn, mes) if x['nome'] == nome)


def conta_bancaria(dsn, nome):
    return sql(dsn, 'select id from public.conta_bancaria where nome = %s', (nome,))[0]['id']


# ---------------------------------------------------------------------------
# 1, 7, 8. Avulsa, competencia distinta do vencimento, troca de mes
# ---------------------------------------------------------------------------

def test_avulsa_cria_item_e_conta_pendente_no_mes_da_competencia(banco):
    r = criar(banco, {**AVULSA, 'competencia': '2029-06-01', 'descricao': 'Assistencia tecnica'})
    c, i = conta(banco, r['conta_id']), item(banco, r['item_id'])
    assert (c['mes_referencia'], c['data_vencimento'], c['valor'], c['status_pagamento'], c['data_pagamento']) == \
        (D(2029, 6, 1), D(2029, 7, 5), Decimal('350.40'), 'Pendente', None)
    assert (c['perfil_financeiro_id'], c['descricao'], c['observacoes'], c['numero_parcela'], c['total_parcelas']) == \
        (ID['PESSOAL'], 'Conserto geladeira', 'Assistencia tecnica', 1, 1)
    assert (i['tipo'], i['recorrente'], i['categoria_id'], i['mes_competencia'], i['ativo']) == \
        ('Simples', False, MORADIA, '2029-06', True)
    assert [x['id'] for x in contas_mes(banco, '2029-06-01')] == [r['conta_id']]  # competencia, nao vencimento
    assert contas_mes(banco, '2029-07-01') == []


def test_competencia_padrao_e_o_mes_do_vencimento_como_no_flask(banco):
    r = criar(banco)
    assert conta(banco, r['conta_id'])['mes_referencia'] == D(2029, 7, 1)


def test_troca_de_competencia_muda_o_mes_em_que_a_conta_aparece(banco):
    r = criar(banco)
    editar(banco, r['conta_id'], {'competencia': '2029-08-01'})
    assert contas_mes(banco, '2029-07-01') == []
    assert [x['id'] for x in contas_mes(banco, '2029-08-01')] == [r['conta_id']]


@pytest.mark.parametrize('dados,mensagem', [
    ({'competencia': '2031-01-01'}, 'ate 12 meses'),
    ({'nome': '  '}, 'Nome obrigatorio'),
    ({'valor': '0'}, 'positivo'),
    ({'valor': '10.555'}, '2 casas'),
    ({'valor': 'abc'}, 'Valor invalido'),
    ({'data_vencimento': '2029-02-30'}, 'vencimento invalida'),
    ({'categoria_id': 999999}, 'Categoria'),
    ({'meio_pagamento': 'cartao'}, 'modulo de cartoes'),
    ({'recorrente': True, 'tipo_recorrencia': 'semanal'}, 'mensal ou anual'),
])
def test_dados_invalidos_recusados_sem_gravar(banco, dados, mensagem):
    antes = sql(banco, 'select (select count(*) from public.item_despesa) + (select count(*) from public.conta) as n')
    with pytest.raises(errors.InvalidParameterValue, match=mensagem):
        criar(banco, {**AVULSA, **dados})
    assert sql(banco, 'select (select count(*) from public.item_despesa) + (select count(*) from public.conta) as n') == antes


# ---------------------------------------------------------------------------
# 2, 15. Recorrencia mensal e anual pelo mecanismo do FIN-RECORRENCIA-1
# ---------------------------------------------------------------------------

def test_recorrencias_mensal_e_anual_geradas_so_pelo_fin_recorrencia(banco):
    mensal = criar(banco, {**AVULSA, 'nome': 'Condominio', 'valor': '900.00', 'data_vencimento': '2029-05-31',
                           'recorrente': True, 'tipo_recorrencia': 'mensal'})
    anual = criar(banco, {**AVULSA, 'nome': 'Seguro anual', 'valor': '1200.00', 'data_vencimento': '2029-05-15',
                          'recorrente': True, 'tipo_recorrencia': 'anual'})
    assert mensal['conta_id'] is None and anual['conta_id'] is None  # nenhum segundo gerador
    i = item(banco, mensal['item_id'])
    assert (i['recorrente'], i['tipo_recorrencia'], i['data_vencimento'], i['ativo']) == (True, 'mensal', D(2029, 5, 31), True)
    p = previa(banco, mes='2029-06-01')
    novos = {(x['item_id'], x['competencia'], x['data_vencimento']) for x in p['itens']
             if x['item_id'] in (mensal['item_id'], anual['item_id'])}
    assert novos == {(mensal['item_id'], '2029-05-01', '2029-05-31'), (mensal['item_id'], '2029-06-01', '2029-06-30'),
                     (mensal['item_id'], '2029-07-01', '2029-07-31'), (anual['item_id'], '2029-05-01', '2029-05-15')}
    gerar(banco, p['a_gerar'], mes='2029-06-01')
    assert {x['nome'] for x in contas_mes(banco, '2029-06-01')} >= {'Condominio'}


def test_excluir_conta_recorrente_dispensa_a_competencia_e_ela_nao_volta(banco):
    r = criar(banco, {**AVULSA, 'nome': 'Condominio', 'data_vencimento': '2029-05-10', 'recorrente': True})
    gerar(banco, previa(banco, mes='2029-05-01')['a_gerar'], mes='2029-05-01')
    maio = next(x for x in contas_mes(banco, '2029-05-01') if x['nome'] == 'Condominio')
    resultado = excluir(banco, maio['id'])
    assert resultado['competencia_dispensada'] is True and conta(banco, maio['id']) is None
    for mes in ('2029-05-01', '2029-06-01'):
        p = previa(banco, mes=mes)
        assert (r['item_id'], '2029-05-01') not in {(x['item_id'], x['competencia']) for x in p['itens']}
        gerar(banco, p['a_gerar'], mes=mes)
    assert not [x for x in contas_mes(banco, '2029-05-01') if x['nome'] == 'Condominio']
    assert {(x['item_id'], x['competencia'], x['motivo']) for x in previa(banco, mes='2029-05-01')['dispensados']} >= \
        {(r['item_id'], '2029-05-01', 'Conta excluida pelo usuario')}


def test_perfil_no_flask_nao_exclui_nem_move_conta_recorrente(banco):
    """T1: o Flask recriaria a conta excluida e duplicaria a de vencimento movido (identifica pela data)."""
    atribuir(banco, 'PESSOAL', 'FLASK')
    escola_marco = sql(banco, "insert into public.conta (item_despesa_id, perfil_financeiro_id, mes_referencia, descricao, "
                              "valor, data_vencimento, status_pagamento, is_fatura_cartao) values (902, 101, '2027-03-01', "
                              "'Escola', 800, '2027-03-10', 'Pendente', false) returning id")[0]['id']
    e = edicao(banco, escola_marco)
    assert (e['pode_editar'], e['pode_mudar_vencimento'], e['pode_excluir'], e['gerador']) == (True, False, False, 'FLASK')
    with pytest.raises(errors.RaiseException, match='Flask a recriaria'):
        excluir(banco, escola_marco)
    with pytest.raises(errors.RaiseException, match='nao pode mudar aqui'):
        editar(banco, escola_marco, {'data_vencimento': '2027-03-12'})
    editar(banco, escola_marco, {'valor': '820.00'})  # valor pode (nao muda a identidade no Flask)
    assert conta(banco, escola_marco)['valor'] == Decimal('820.00')


def test_editar_recorrencia_vale_para_as_proximas_geracoes_sem_mudar_as_existentes(banco):
    r = criar(banco, {**AVULSA, 'nome': 'Internet', 'valor': '100.00', 'data_vencimento': '2029-05-10', 'recorrente': True})
    gerar(banco, previa(banco, mes='2029-05-01')['a_gerar'], mes='2029-05-01')  # maio e junho
    existentes = sql(banco, 'select md5(t::text) as h from public.conta t where item_despesa_id = %s order by id',
                     (r['item_id'],))
    versao = edicao(banco, da_recorrencia(banco, '2029-05-01', 'Internet'))['versao_recorrencia']
    rpc(banco, 'editar_recorrencia', ID['PESSOAL'], r['item_id'], versao,
        {'valor': '120.00', 'data_vencimento': '2029-05-20', 'categoria_id': ASSINATURAS})
    assert sql(banco, 'select md5(t::text) as h from public.conta t where item_despesa_id = %s order by id',
               (r['item_id'],)) == existentes
    gerar(banco, previa(banco, mes='2029-07-01')['a_gerar'], mes='2029-07-01')
    julho = sql(banco, "select valor, data_vencimento from public.conta where item_despesa_id = %s "
                       "and mes_referencia = '2029-07-01'", (r['item_id'],))
    assert julho == [{'valor': Decimal('120.00'), 'data_vencimento': D(2029, 7, 20)}]


def test_perfil_no_flask_nao_muda_o_calendario_da_recorrencia(banco):
    atribuir(banco, 'PESSOAL', 'FLASK')
    versao = sql(banco, 'select md5(t::text) as h from public.item_despesa t where id = 902')[0]['h']
    with pytest.raises(errors.RaiseException, match='Dia e frequencia'):
        rpc(banco, 'editar_recorrencia', ID['PESSOAL'], 902, versao, {'data_vencimento': '2026-12-15'})
    r = rpc(banco, 'editar_recorrencia', ID['PESSOAL'], 902, versao, {'valor': '850.00'})
    assert item(banco, 902)['valor'] == Decimal('850.00') and r['versao'] != versao


# ---------------------------------------------------------------------------
# 3, 4, 5, 6. Edicao, bloqueio apos pagamento/movimento, exclusao, inativacao
# ---------------------------------------------------------------------------

def test_edicao_antes_da_execucao_atualiza_conta_e_item(banco):
    r = criar(banco)
    e = edicao(banco, r['conta_id'])
    assert (e['pode_editar'], e['pode_excluir'], e['bloqueio']) == (True, True, None)
    novo = editar(banco, r['conta_id'], {'nome': 'Geladeira (peca)', 'valor': '410.00', 'data_vencimento': '2029-07-12',
                                         'categoria_id': ASSINATURAS, 'descricao': 'Troca do compressor'})
    c, i = conta(banco, r['conta_id']), item(banco, r['item_id'])
    assert (c['descricao'], c['valor'], c['data_vencimento'], c['observacoes']) == \
        ('Geladeira (peca)', Decimal('410.00'), D(2029, 7, 12), 'Troca do compressor')
    assert (i['nome'], i['valor'], i['categoria_id'], i['data_vencimento']) == \
        ('Geladeira (peca)', Decimal('410.00'), ASSINATURAS, D(2029, 7, 12))
    assert novo['versao'] != e['versao']


@pytest.mark.parametrize('execucao', ['pagamento', 'movimento'])
def test_conta_com_execucao_financeira_nao_e_editada_nem_excluida(banco, execucao):
    r = criar(banco)
    if execucao == 'pagamento':
        sql(banco, "update public.conta set status_pagamento = 'Pago', data_pagamento = '2029-07-05' where id = %s",
            (r['conta_id'],))
    else:
        sql(banco, "insert into public.movimento_financeiro (conta_bancaria_id, tipo, valor, descricao, data_movimento, "
                   "conta_id, origem) values (%s, 'DEBITO', 350.40, 'Pagamento', '2029-07-05', %s, 'DESPESA')",
            (conta_bancaria(banco, 'Conta Pessoal (A)'), r['conta_id']))
    antes = (md5_conta(banco, r['conta_id']), digital(banco))
    e = edicao(banco, r['conta_id'])
    assert (e['pode_editar'], e['pode_excluir']) == (False, False)
    assert e['bloqueio'] in ('Despesa paga: correcao so por estorno', 'Possui movimento financeiro vinculado')
    with pytest.raises(errors.RaiseException, match='Operacao bloqueada'):
        editar(banco, r['conta_id'], {'valor': '1.00'}, versao=e['versao'])
    with pytest.raises(errors.RaiseException, match='Operacao bloqueada'):
        excluir(banco, r['conta_id'], versao=e['versao'])
    assert (md5_conta(banco, r['conta_id']), digital(banco)) == antes


@pytest.mark.parametrize('tipo,motivo', [('Consorcio', 'consorcios'), ('Financiamento', 'financiamentos')])
def test_contas_de_outros_modulos_ficam_bloqueadas(banco, tipo, motivo):
    item_id = sql(banco, "insert into public.item_despesa (nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente) "
                         "values ('Modulo', %s, 101, 951, true, false) returning id", (tipo,))[0]['id']
    conta_id = sql(banco, "insert into public.conta (item_despesa_id, perfil_financeiro_id, mes_referencia, descricao, valor, "
                          "data_vencimento, status_pagamento, numero_parcela, total_parcelas, is_fatura_cartao) "
                          "values (%s, 101, '2029-07-01', 'Parcela', 100, '2029-07-10', 'Pendente', 3, 60, false) "
                          "returning id", (item_id,))[0]['id']
    e = edicao(banco, conta_id)
    assert motivo in e['bloqueio'] and not e['pode_editar'] and not e['pode_excluir']
    with pytest.raises(errors.RaiseException, match=motivo):
        excluir(banco, conta_id, versao=e['versao'])


def test_fatura_nao_e_tratada_como_despesa(banco):
    gerar(banco, previa(banco)['a_gerar'])
    fatura = sql(banco, 'select id from public.conta where is_fatura_cartao limit 1')[0]['id']
    with pytest.raises(errors.InsufficientPrivilege, match='nao encontrada'):
        edicao(banco, fatura)
    with pytest.raises(errors.InsufficientPrivilege):
        excluir(banco, fatura, versao='x')


def test_exclusao_de_avulsa_remove_conta_e_item_sem_tocar_o_resto(banco):
    r = criar(banco)
    antes = digital(banco, tabelas=('conta_bancaria', 'movimento_financeiro', 'categoria'))
    resultado = excluir(banco, r['conta_id'])
    assert resultado == {'conta_id': r['conta_id'], 'item_excluido': True, 'competencia_dispensada': False}
    assert conta(banco, r['conta_id']) is None and item(banco, r['item_id']) is None
    assert digital(banco, tabelas=('conta_bancaria', 'movimento_financeiro', 'categoria')) == antes


def test_inativacao_para_a_geracao_e_mantem_o_historico(banco):
    r = criar(banco, {**AVULSA, 'nome': 'Academia', 'data_vencimento': '2029-05-08', 'recorrente': True})
    gerar(banco, previa(banco, mes='2029-05-01')['a_gerar'], mes='2029-05-01')
    historico = sql(banco, 'select md5(t::text) as h from public.conta t where item_despesa_id = %s order by id',
                    (r['item_id'],))
    versao = edicao(banco, da_recorrencia(banco, '2029-05-01', 'Academia'))['versao_recorrencia']
    rpc(banco, 'inativar_recorrencia', ID['PESSOAL'], r['item_id'], versao)
    assert item(banco, r['item_id'])['ativo'] is False
    assert r['item_id'] not in {x['item_id'] for x in previa(banco, mes='2029-09-01')['itens']}
    assert sql(banco, 'select md5(t::text) as h from public.conta t where item_despesa_id = %s order by id',
               (r['item_id'],)) == historico
    assert edicao(banco, da_recorrencia(banco, '2029-05-01', 'Academia'))['pode_inativar_recorrencia'] is False


# ---------------------------------------------------------------------------
# 9. Categoria e conta bancaria
# ---------------------------------------------------------------------------

def test_debito_automatico_exige_conta_bancaria_ativa_do_proprio_perfil(banco):
    propria = conta_bancaria(banco, 'Conta Pessoal (A)')
    r = criar(banco, {**AVULSA, 'debito_automatico': True, 'conta_bancaria_id': propria})
    c = conta(banco, r['conta_id'])
    assert (c['debito_automatico'], c['conta_bancaria_id']) == (True, propria)
    legado = conta_bancaria(banco, 'Carteira legado sem perfil')  # NULL = Pessoal
    criar(banco, {**AVULSA, 'debito_automatico': True, 'conta_bancaria_id': legado})
    for invalida in (None, conta_bancaria(banco, 'Conta Empresa (A)'), conta_bancaria(banco, 'Conta Perfil B')):
        with pytest.raises(errors.InvalidParameterValue, match='conta bancaria ativa do perfil'):
            criar(banco, {**AVULSA, 'debito_automatico': True, 'conta_bancaria_id': invalida})
    sql(banco, "update public.conta_bancaria set status = 'INATIVO' where id = %s", (propria,))
    with pytest.raises(errors.InvalidParameterValue):
        criar(banco, {**AVULSA, 'debito_automatico': True, 'conta_bancaria_id': propria})


def test_sem_debito_a_conta_bancaria_nao_e_gravada(banco):
    r = criar(banco, {**AVULSA, 'conta_bancaria_id': conta_bancaria(banco, 'Conta Pessoal (A)')})
    assert conta(banco, r['conta_id'])['conta_bancaria_id'] is None


def test_categorias_globais_ativas_para_quem_tem_perfil(banco):
    sql(banco, "insert into public.categoria (nome, cor, ativo, sistemica, bloquear_edicao, bloquear_exclusao) "
               "values ('Inativa R', '#000000', false, false, false, false)")
    nomes = [x['nome'] for x in chamar(banco, USUARIO_A, "select json_agg(x) from financeiro.categorias_de_despesa() x")]
    assert nomes == ['Assinaturas R', 'Moradia R']
    with pytest.raises(errors.InvalidParameterValue, match='inativa'):
        criar(banco, {**AVULSA, 'categoria_id': sql(banco, "select id from public.categoria where nome = 'Inativa R'")[0]['id']})


# ---------------------------------------------------------------------------
# 10, 11, 12. Autorizacao por perfil
# ---------------------------------------------------------------------------

def test_leitor_ve_mas_nao_cadastra_edita_nem_exclui(banco):
    conta_empresa = sql(banco, "insert into public.conta (item_despesa_id, perfil_financeiro_id, mes_referencia, descricao, "
                               "valor, data_vencimento, status_pagamento, is_fatura_cartao) values (940, 102, "
                               "'2027-03-01', 'Aluguel sala', 300, '2027-03-10', 'Pendente', false) returning id")[0]['id']
    e = edicao(banco, conta_empresa, 'EMPRESA')
    assert (e['pode_gerir'], e['pode_editar'], e['pode_excluir'], e['pode_editar_recorrencia']) == (False, False, False, False)
    antes = md5_conta(banco, conta_empresa)
    with pytest.raises(errors.InsufficientPrivilege):
        criar(banco, perfil='EMPRESA')
    with pytest.raises(errors.InsufficientPrivilege):
        editar(banco, conta_empresa, {'valor': '1.00'}, 'EMPRESA', versao=e['versao'])
    with pytest.raises(errors.InsufficientPrivilege):
        excluir(banco, conta_empresa, 'EMPRESA', versao=e['versao'])
    with pytest.raises(errors.InsufficientPrivilege):
        rpc(banco, 'inativar_recorrencia', ID['EMPRESA'], 940, e['versao_recorrencia'])
    assert md5_conta(banco, conta_empresa) == antes


def test_outro_usuario_e_perfil_trocado_nao_alcancam_a_despesa(banco):
    r = criar(banco)
    versao = edicao(banco, r['conta_id'])['versao']
    with pytest.raises(errors.InsufficientPrivilege):
        edicao(banco, r['conta_id'], 'PESSOAL', USUARIO_B)
    with pytest.raises(errors.InsufficientPrivilege):
        editar(banco, r['conta_id'], {'valor': '1.00'}, 'PERFIL_B', USUARIO_B, versao=versao)  # perfil proprio, conta alheia
    with pytest.raises(errors.InsufficientPrivilege):
        excluir(banco, r['conta_id'], 'PERFIL_B', USUARIO_B, versao=versao)
    with pytest.raises(errors.InsufficientPrivilege):
        criar(banco, perfil='PESSOAL', usuario=USUARIO_B)
    assert conta(banco, r['conta_id'])['valor'] == Decimal('350.40')


@pytest.mark.parametrize('comando', [
    "select financeiro.criar_despesa(101, '{}'::jsonb, gen_random_uuid())",
    "select financeiro.editar_despesa(101, 1, 'x', '{}'::jsonb)",
    "select financeiro.excluir_despesa(101, 1, 'x')",
    "select financeiro.editar_recorrencia(101, 902, 'x', '{}'::jsonb)",
    "select financeiro.inativar_recorrencia(101, 902, 'x')",
    "select financeiro.despesa_para_edicao(101, 1)",
    "select count(*) from financeiro.categorias_de_despesa()",
])
def test_anonimo_nao_executa(banco, comando):
    with pytest.raises(errors.InsufficientPrivilege, match='permission denied'):
        chamar(banco, None, comando)


@pytest.mark.parametrize('comando', [
    "select financeiro.bloqueio_da_despesa(1)",
    "select financeiro.versao_despesa(1)",
    "select financeiro.travar_despesa(101, 1, 'x')",
    "select financeiro.ler_dados_despesa('{}'::jsonb, 101, true)",
    'select count(*) from financeiro.operacao_despesa',
    "update public.conta set valor = 1",
    "delete from public.item_despesa",
])
def test_navegador_nao_acessa_funcoes_internas_nem_tabelas(banco, comando):
    with pytest.raises(errors.InsufficientPrivilege, match='permission denied'):
        chamar(banco, USUARIO_A, comando)


# ---------------------------------------------------------------------------
# 13, 14. Concorrencia, repeticao e preservacao financeira
# ---------------------------------------------------------------------------

def test_repetir_a_mesma_criacao_nao_duplica(banco):
    chave = str(uuid.uuid4())
    primeira = criar(banco, chave=chave)
    segunda = criar(banco, chave=chave)
    assert segunda == {**primeira, 'repetida': True}
    assert sql(banco, "select count(*) as n from public.item_despesa where nome = 'Conserto geladeira'")[0]['n'] == 1
    with pytest.raises(errors.InvalidParameterValue, match='ja usada'):
        criar(banco, perfil='PERFIL_B', usuario=USUARIO_B, chave=chave)


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


def test_criacoes_simultaneas_com_a_mesma_chave_criam_uma_despesa(banco):
    chave = str(uuid.uuid4())
    resultados = _paralelo([lambda: criar(banco, chave=chave) for _ in range(3)])
    assert [r[0] for r in resultados] == ['ok'] * 3
    assert len({r[1]['item_id'] for r in resultados}) == 1
    assert sql(banco, "select count(*) as n from public.conta where descricao = 'Conserto geladeira'")[0]['n'] == 1


def test_edicoes_simultaneas_da_mesma_versao_so_uma_vale(banco):
    r = criar(banco)
    versao = edicao(banco, r['conta_id'])['versao']
    resultados = _paralelo([lambda v=v: editar(banco, r['conta_id'], {'valor': v}, versao=versao)
                            for v in ('400.00', '500.00')])
    estados = sorted(x[0] for x in resultados)
    assert estados == ['erro', 'ok']
    erro = next(x[1] for x in resultados if x[0] == 'erro')
    assert 'alterada por outra operacao' in str(erro)


def test_edicao_esperando_um_pagamento_em_andamento_e_bloqueada_depois_dele(banco):
    """Pagamento (como o do Flask) em transacao aberta: a edicao espera a linha e depois ve a conta paga."""
    r = criar(banco)
    versao = edicao(banco, r['conta_id'])['versao']
    pagamento = psycopg2.connect(banco)
    cur = pagamento.cursor()
    cur.execute("update public.conta set status_pagamento = 'Pago', data_pagamento = '2029-07-05' where id = %s",
                (r['conta_id'],))
    resultado = {}
    tarefa = threading.Thread(target=lambda: resultado.setdefault(
        'erro', pytest.raises(errors.RaiseException, editar, banco, r['conta_id'], {'valor': '1.00'}, versao=versao)))
    tarefa.start()
    time.sleep(1.5)
    assert tarefa.is_alive()  # esperando a linha travada pelo pagamento
    pagamento.commit()
    pagamento.close()
    tarefa.join(30)
    assert 'Operacao bloqueada' in str(resultado['erro'].value)
    assert conta(banco, r['conta_id'])['valor'] == Decimal('350.40')


def test_operacoes_nao_tocam_saldos_movimentos_compras_nem_faturas(banco):
    gerar(banco, previa(banco)['a_gerar'])  # faturas e compras recorrentes existentes
    rec = criar(banco, {**AVULSA, 'nome': 'Condominio', 'recorrente': True, 'data_vencimento': '2029-05-05'})
    gerar(banco, previa(banco, mes='2029-05-01')['a_gerar'], mes='2029-05-01')
    antes = (digital(banco, tabelas=('conta_bancaria', 'movimento_financeiro', 'lancamento_agregado')),
             sql(banco, "select md5(string_agg(t::text, '|' order by id)) as h from public.conta t where is_fatura_cartao"))
    a = criar(banco)
    editar(banco, a['conta_id'], {'valor': '360.00'})
    excluir(banco, a['conta_id'])
    maio = da_recorrencia(banco, '2029-05-01', 'Condominio')
    editar(banco, maio, {'valor': '910.00'})
    excluir(banco, maio)
    assert rec['item_id'] == item(banco, rec['item_id'])['id']
    depois = (digital(banco, tabelas=('conta_bancaria', 'movimento_financeiro', 'lancamento_agregado')),
              sql(banco, "select md5(string_agg(t::text, '|' order by id)) as h from public.conta t where is_fatura_cartao"))
    assert depois == antes


# ---------------------------------------------------------------------------
# 17. Equivalencia com as regras validas do Flask
# ---------------------------------------------------------------------------

_SCRIPT_FLASK = """
import json, sys
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    if not Usuario.query.filter_by(email='flask.despesas@teste.local').first():
        u = Usuario(email='flask.despesas@teste.local', nome='Despesas', ativo=True)
        u.definir_senha('Senha-ficticia-despesas-2026')
        db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': 'flask.despesas@teste.local', 'senha': 'Senha-ficticia-despesas-2026'}).status_code == 302
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


def _sem_ids(linha):
    return {k: v for k, v in linha.items() if k not in ('id', 'item_despesa_id', 'criado_em')}


def test_equivalencia_com_o_flask_no_cadastro(cluster):  # noqa: F811
    dsn_flask, dsn_novo = copiar(cluster), copiar(cluster)
    conta_debito = conta_bancaria(dsn_novo, 'Conta Pessoal (A)')
    avulsa = {'nome': 'Conserto', 'valor': '350.40', 'categoria_id': MORADIA, 'data_vencimento': '2029-07-05',
              'descricao': 'Assistencia'}
    recorrente = {'nome': 'Plano celular', 'valor': '79.90', 'categoria_id': ASSINATURAS, 'data_vencimento': '2029-05-12',
                  'tipo_recorrencia': 'mensal', 'meio_pagamento': 'debito_automatico', 'conta_bancaria_id': conta_debito}
    atribuir(dsn_flask, 'PESSOAL')  # o Flask nao gera no perfil migrado: compara so o cadastro
    flask(dsn_flask, [['post', '/api/despesas/', avulsa], ['post', '/api/recorrencias', recorrente]])
    atribuir(dsn_novo, 'PESSOAL')
    criar(dsn_novo, avulsa)
    criar(dsn_novo, {**{k: v for k, v in recorrente.items() if k != 'meio_pagamento'},
                     'recorrente': True, 'debito_automatico': True})
    for nome in ('Conserto', 'Plano celular'):
        f = sql(dsn_flask, 'select * from public.item_despesa where nome = %s', (nome,))
        n = sql(dsn_novo, 'select * from public.item_despesa where nome = %s', (nome,))
        assert [_sem_ids(x) for x in n] == [_sem_ids(x) for x in f], nome
    f = sql(dsn_flask, "select * from public.conta where descricao = 'Conserto'")
    n = sql(dsn_novo, "select * from public.conta where descricao = 'Conserto'")
    assert [_sem_ids(x) for x in n] == [_sem_ids(x) for x in f]


def test_equivalencia_com_o_flask_na_edicao_e_exclusao_de_pendentes(cluster):  # noqa: F811
    dsn_flask, dsn_novo = copiar(cluster), copiar(cluster)
    resultados = {}
    for dsn in (dsn_flask, dsn_novo):
        atribuir(dsn, 'PESSOAL')
        resultados[dsn] = criar(dsn, AVULSA)
    ids = resultados[dsn_flask]
    alteracao = {'descricao': 'Conserto (corrigido)', 'valor': '399.99', 'data_vencimento': '2029-07-15',
                 'observacoes': 'Nova data'}
    flask(dsn_flask, [['put', f"/api/despesas/{ids['conta_id']}", alteracao]])
    editar(dsn_novo, resultados[dsn_novo]['conta_id'], {'nome': 'Conserto (corrigido)', 'valor': '399.99',
                                                        'data_vencimento': '2029-07-15', 'descricao': 'Nova data'})
    campos = ('descricao', 'valor', 'data_vencimento', 'observacoes', 'status_pagamento', 'mes_referencia')
    assert {k: conta(dsn_novo, resultados[dsn_novo]['conta_id'])[k] for k in campos} == \
        {k: conta(dsn_flask, ids['conta_id'])[k] for k in campos}
    flask(dsn_flask, [['delete', f"/api/despesas/{ids['conta_id']}", None]])
    excluir(dsn_novo, resultados[dsn_novo]['conta_id'])
    assert conta(dsn_flask, ids['conta_id']) is None and conta(dsn_novo, resultados[dsn_novo]['conta_id']) is None
    # Diferenca intencional: o Flask deixa o item avulso orfao; o novo aplicativo o remove.
    assert item(dsn_flask, ids['item_id']) is not None and item(dsn_novo, resultados[dsn_novo]['item_id']) is None


def test_conta_paga_nao_muda_de_valor_no_flask_nem_no_novo(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    r = criar(dsn)
    sql(dsn, "update public.conta set status_pagamento = 'Pago', data_pagamento = '2029-07-05' where id = %s",
        (r['conta_id'],))
    versao = edicao(dsn, r['conta_id'])['versao']
    with pytest.raises(errors.RaiseException, match='paga'):
        editar(dsn, r['conta_id'], {'valor': '1.00'}, versao=versao)
    saida = flask(dsn, [['put', f"/api/despesas/{r['conta_id']}", {'valor': '1.00'}],
                        ['put', f"/api/despesas/{r['conta_id']}", {'observacoes': 'nota'}]])
    # FIN-PAGAMENTO-TRAVA-1: o Flask tambem recusa mudar o valor de conta paga (antes: 200 e valor 1,00,
    # divergente do movimento); campos descritivos continuam editaveis.
    assert [s['status'] for s in saida] == [409, 200]
    assert (conta(dsn, r['conta_id'])['valor'], conta(dsn, r['conta_id'])['observacoes']) == (Decimal('350.40'), 'nota')
