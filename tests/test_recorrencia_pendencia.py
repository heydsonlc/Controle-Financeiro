"""
Testes FIN-CARTOES-RECORRENCIA-PENDENCIA-1 — ocorrencia persistente, aviso e dispensa auditavel de compra recorrente
nao lancada porque a fatura de destino estava consolidada.

Bancos ISOLADOS e dados FICTICIOS: copia do cluster PostgreSQL descartavel (cenario do FIN-RECORRENCIA-1: perfil
"Pessoal" ficticio 101, Cartao Teste 910, recorrencia "Streaming" 906; base do FIN-PAGAMENTO-TRAVA-1) e SQLite
temporario. Nunca o gastos.db nem o Supabase. Flask real em processo proprio; novo aplicativo como `authenticated`.
"""
import json
import sqlite3
import threading
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_cartoes_d6_integridade import compras, consolidar, md5_fatura
from tests.test_fatura_integridade import Flask as FlaskServico
from tests.test_pagamento_trava import PERFIL, base, http, pg  # noqa: F401  (fixtures reaproveitadas)
from tests.test_supabase_fatura_unica import em_thread
from tests.test_supabase_recorrencia import (  # noqa: F401
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,
    gerar,
    previa,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
from psycopg2 import errors  # noqa: E402

pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

D = date
STREAMING = 906


def ocorrencias(dsn):
    return sql(dsn, 'select * from public.recorrencia_rejeicao order by competencia, id')


def financeiro_intacto(dsn):
    """Compras, faturas, recorrencias e identidades do motor (para conferir que a dispensa nao muda nada)."""
    return sql(dsn, "select (select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.lancamento_agregado t) as l, "
                    "(select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.conta t) as c, "
                    "(select md5(coalesce(string_agg(t::text, '|' order by id), '')) from public.item_despesa t) as i, "
                    "(select count(*) from financeiro.recorrencia_competencia) as r")[0]


def dispensar(dsn, item=STREAMING, competencia='2027-03-01', usuario=USUARIO_A, perfil=PERFIL):
    return chamar(dsn, usuario, 'select financeiro.dispensar_aviso_recorrencia(%s, %s, %s)', (perfil, item, competencia))


def listar(dsn, incluir=False, usuario=USUARIO_A, perfil=PERFIL):
    return chamar(dsn, usuario, "select coalesce(json_agg(x), '[]'::json) from financeiro.recorrencias_rejeitadas(%s, %s) x",
                  (perfil, incluir))


def recorrencia_flask(dsn, pasta, nome, mes='2027-03-01', meses=2):
    r = FlaskServico(dsn, pasta, nome, acao='recorrencia', item=STREAMING, meses=meses, mes=mes).resultado()
    assert 'erro' not in r, r
    return r


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def test_geracao_do_novo_motor_registra_a_ocorrencia(pg):
    d = pg['dsn']
    atribuir(d, 'PESSOAL')
    marco = consolidar(d, '2027-03-01')
    gerar(d, previa(d)['a_gerar'])
    [o] = ocorrencias(d)
    assert (o['item_despesa_id'], o['competencia'], o['perfil_financeiro_id'], o['cartao_id'], o['fatura_id'], o['valor'],
            o['situacao'], o['origem'], o['tentativas'], o['aviso_dispensado_em']) == \
        (STREAMING, D(2027, 3, 1), PERFIL, 910, marco['id'], Decimal('39.90'), 'PENDENTE', 'NOVO_APP', 1, None)
    assert 'Fatura de 03/2027 consolidada' in o['motivo'] and o['primeira_tentativa_em'] == o['ultima_tentativa_em']
    assert compras(d, 'item_despesa_id = %s and mes_fatura = %s', (STREAMING, D(2027, 3, 1))) == []  # D6: nada lancado


def test_geracao_do_flask_registra_e_reexecucao_nao_duplica(pg):
    d, p = pg['dsn'], pg['pasta']
    marco = consolidar(d, '2027-03-01')
    antes = md5_fatura(d, marco['id'])
    recorrencia_flask(d, p, 'r1')
    recorrencia_flask(d, p, 'r2')  # novo processo = aplicacao reiniciada
    [o] = ocorrencias(d)
    assert (o['origem'], o['tentativas'], o['competencia'], o['fatura_id'], o['situacao']) == \
        ('FLASK', 2, D(2027, 3, 1), marco['id'], 'PENDENTE')
    assert o['ultima_tentativa_em'] >= o['primeira_tentativa_em']
    assert md5_fatura(d, marco['id']) == antes
    # D5: abril (aberta) continua lancado em abril; nada levado de marco para outro mes.
    assert [(x['mes_fatura'], x['mes_fatura_original']) for x in
            compras(d, 'item_despesa_id = %s and mes_fatura >= %s', (STREAMING, D(2027, 3, 1)))] == [(D(2027, 4, 1), None)]


def test_competencias_diferentes_sao_ocorrencias_distintas(pg):
    d, p = pg['dsn'], pg['pasta']
    consolidar(d, '2027-03-01')
    consolidar(d, '2027-04-01')
    recorrencia_flask(d, p, 'r')
    assert [(o['competencia'], o['tentativas']) for o in ocorrencias(d)] == [(D(2027, 3, 1), 1), (D(2027, 4, 1), 1)]


def test_fatura_aberta_e_paga_nao_geram_ocorrencia(pg):
    d, p = pg['dsn'], pg['pasta']
    sql(d, "update public.conta set status_pagamento = 'Pago' where id = %s", (consolidar(d, '2027-03-01')['id'],))
    recorrencia_flask(d, p, 'r')
    assert ocorrencias(d) == []  # paga: desvio do FIN-FATURA-INTEGRIDADE-1, nao pendencia
    assert [(x['mes_fatura'], x['mes_fatura_original']) for x in
            compras(d, 'item_despesa_id = %s and mes_fatura >= %s', (STREAMING, D(2027, 3, 1)))] == \
        [(D(2027, 4, 1), D(2027, 3, 1)), (D(2027, 4, 1), None)]


# ---------------------------------------------------------------------------
# Idempotencia e concorrencia
# ---------------------------------------------------------------------------

def test_duas_geracoes_simultaneas_do_flask_uma_ocorrencia(pg):
    d, p = pg['dsn'], pg['pasta']
    consolidar(d, '2027-03-01')
    barreira = threading.Barrier(2)

    def rodar(nome):
        barreira.wait(30)
        return recorrencia_flask(d, p, nome)

    tarefas = [em_thread(lambda n=n: rodar(n)) for n in ('a', 'b')]
    for t, _ in tarefas:
        t.join(180)
    assert all('valor' in r for _, r in tarefas), tarefas
    [o] = ocorrencias(d)
    assert o['tentativas'] == 2


def test_consolidacao_entre_previa_e_geracao_nao_grava_ocorrencia(pg):
    d = pg['dsn']
    atribuir(d, 'PESSOAL')
    total = previa(d)['a_gerar']
    consolidar(d, '2027-03-01')
    with pytest.raises(errors.RaiseException, match='previa mudou'):
        gerar(d, total)
    assert ocorrencias(d) == []  # a tentativa foi desfeita inteira
    gerar(d, previa(d)['a_gerar'])  # nova previa: a ocorrencia e registrada
    assert [o['competencia'] for o in ocorrencias(d)] == [D(2027, 3, 1)]


def test_dispensa_concorrente_com_a_geracao(pg):
    d = pg['dsn']
    atribuir(d, 'PESSOAL')
    consolidar(d, '2027-03-01')
    total = previa(d)['a_gerar']
    barreira = threading.Barrier(2)
    tarefas = [em_thread(lambda: (barreira.wait(30), gerar(d, total))[1]),
               em_thread(lambda: (barreira.wait(30), dispensar(d))[1])]
    for t, _ in tarefas:
        t.join(120)
    assert all('valor' in r for _, r in tarefas), tarefas
    [o] = ocorrencias(d)  # uma so, pela identidade recorrencia + competencia
    assert o['aviso_dispensado_em'] is not None and o['situacao'] == 'PENDENTE'


# ---------------------------------------------------------------------------
# Avisos e dispensa auditavel (novo aplicativo)
# ---------------------------------------------------------------------------

def test_dispensa_e_auditada_idempotente_e_nao_muda_nada_financeiro(pg):
    d = pg['dsn']
    atribuir(d, 'PESSOAL')
    consolidar(d, '2027-03-01')
    gerar(d, previa(d)['a_gerar'])
    assert [x['competencia'] for x in listar(d)] == ['2027-03-01']
    antes = financeiro_intacto(d)
    r1 = dispensar(d)
    r2 = dispensar(d)  # de novo: mesma dispensa, nenhum evento a mais
    assert (r1['ja_dispensado'], r2['ja_dispensado'], r1['aviso_dispensado_em']) == (False, True, r2['aviso_dispensado_em'])
    [o] = ocorrencias(d)
    assert (o['situacao'], o['aviso_dispensado_user_id'], o['tentativas']) == ('PENDENTE', USUARIO_A['id'], 1)
    assert 'Fatura de 03/2027 consolidada' in o['motivo']  # motivo original preservado
    assert financeiro_intacto(d) == antes  # nao cancela recorrencia, nao cria compra, nao muda fatura
    assert listar(d) == [] and [x['situacao'] for x in listar(d, incluir=True)] == ['PENDENTE']  # historico consultavel
    assert previa(d)['rejeitadas'] >= 1  # a previa continua informando a rejeicao


def test_dispensa_antes_da_geracao_registra_a_ocorrencia_validada_no_banco(pg):
    d = pg['dsn']
    atribuir(d, 'PESSOAL')
    consolidar(d, '2027-03-01')
    r = dispensar(d)  # sem geracao: o banco confere no plano que a linha e rejeitada por consolidacao
    [o] = ocorrencias(d)
    assert (r['ja_dispensado'], o['origem'], o['aviso_dispensado_em'] is not None) == (False, 'NOVO_APP', True)
    with pytest.raises(errors.InvalidParameterValue, match='Nao ha aviso'):
        dispensar(d, competencia='2027-04-01')  # abril nao esta rejeitada: nada a dispensar, nada registrado
    assert len(ocorrencias(d)) == 1


def test_isolamento_entre_perfis_e_permissoes(pg):
    d = pg['dsn']
    atribuir(d, 'PESSOAL')
    consolidar(d, '2027-03-01')
    gerar(d, previa(d)['a_gerar'])
    with pytest.raises(errors.InsufficientPrivilege):
        listar(d, usuario=USUARIO_B)  # outro usuario, outro perfil
    with pytest.raises(errors.InsufficientPrivilege):
        dispensar(d, usuario=USUARIO_B)
    atribuir(d, 'PERFIL_B')  # FIN-ESCRITOR-UNICO-FINAL-1: Perfil B no novo aplicativo, para chegar a regra de isolamento
    with pytest.raises(errors.InsufficientPrivilege):
        dispensar(d, perfil=103, usuario=USUARIO_B)  # item do Pessoal pelo Perfil B
    sql(d, "update financeiro.perfil_acesso set pode_gerir = false, papel = 'LEITOR' where perfil_financeiro_id = %s", (PERFIL,))
    assert len(listar(d)) == 1  # quem so le ve o aviso...
    with pytest.raises(errors.InsufficientPrivilege):
        dispensar(d)  # ...mas nao dispensa
    for comando in ('select * from public.recorrencia_rejeicao',
                    'update public.recorrencia_rejeicao set aviso_dispensado_em = now()',
                    "select financeiro.registrar_rejeicoes_consolidadas('{}', 'NOVO_APP')"):
        with pytest.raises(errors.InsufficientPrivilege):
            chamar(d, USUARIO_A, comando)
    for comando in ('select * from financeiro.recorrencias_rejeitadas(101)',
                    "select financeiro.dispensar_aviso_recorrencia(101, 906, '2027-03-01')"):
        with pytest.raises(errors.InsufficientPrivilege):
            chamar(d, None, comando)  # anonimo
    assert ocorrencias(d)[0]['aviso_dispensado_em'] is None


# ---------------------------------------------------------------------------
# Flask: API e tela
# ---------------------------------------------------------------------------

def test_flask_lista_e_dispensa_o_aviso_do_perfil_ativo(pg):
    d, p = pg['dsn'], pg['pasta']
    consolidar(d, '2027-03-01')
    recorrencia_flask(d, p, 'r')
    lista = http(d, p, 'l', 'get', '/api/recorrencias/pendencias').resultado()
    assert lista['status'] == 200 and lista['json']['disponivel'] is True
    [item] = lista['json']['data']
    assert (item['nome'], item['competencia'], item['valor'], item['situacao']) == ('Streaming', '2027-03-01', '39.90', 'PENDENTE')
    antes = financeiro_intacto(d)
    r1 = http(d, p, 'd1', 'post', f"/api/recorrencias/pendencias/{item['id']}/dispensar").resultado()
    r2 = http(d, p, 'd2', 'post', f"/api/recorrencias/pendencias/{item['id']}/dispensar").resultado()
    assert (r1['status'], r1['json']['ja_dispensado'], r2['status'], r2['json']['ja_dispensado']) == (200, False, 200, True)
    assert financeiro_intacto(d) == antes
    o = ocorrencias(d)[0]
    assert o['aviso_dispensado_usuario_id'] is not None and o['situacao'] == 'PENDENTE'
    assert http(d, p, 'l2', 'get', '/api/recorrencias/pendencias').resultado()['json']['data'] == []
    historico = http(d, p, 'l3', 'get', '/api/recorrencias/pendencias?incluir_dispensadas=1').resultado()['json']['data']
    assert [h['aviso_dispensado_em'] is not None for h in historico] == [True]
    # Outro perfil ativo no Flask (Empresa) nao ve nem dispensa a ocorrencia do Pessoal.
    assert http(d, p, 'e1', 'get', '/api/recorrencias/pendencias', perfil=102).resultado()['json']['data'] == []
    assert http(d, p, 'e2', 'post', f"/api/recorrencias/pendencias/{item['id']}/dispensar", perfil=102).resultado()['status'] == 404


def test_flask_tela_de_despesas_mostra_o_aviso():
    raiz = Path(__file__).resolve().parent.parent
    html = (raiz / 'frontend/templates/despesas.html').read_text(encoding='utf-8')
    js = (raiz / 'frontend/static/js/despesas.js').read_text(encoding='utf-8')
    assert 'id="pendencias-recorrencia"' in html
    assert "fetch('/api/recorrencias/pendencias')" in js and '/dispensar`' in js
    assert 'Dispensar aviso' in js and 'a recorrência não é cancelada' in js
    corpo = js[js.index('function renderizarPendenciasRecorrencia'):]
    assert 'innerHTML' not in corpo[:corpo.index('async function dispensarPendenciaRecorrencia')]  # texto so por textContent


# ---------------------------------------------------------------------------
# SQLite (arquivo temporario; nunca o gastos.db): com a tabela e sem ela (banco nao migrado)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('com_tabela', [True, False])
def test_sqlite_registra_ou_degrada_sem_lancar_na_consolidada(tmp_path, com_tabela):
    caminho = tmp_path / 'pendencia.db'
    url = f'sqlite:///{caminho.as_posix()}'
    assert FlaskServico(url, tmp_path, 'prep', acao='preparar_sqlite').resultado()['ok']
    with sqlite3.connect(caminho) as conn:
        conn.execute("insert into conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, "
                     "valor_planejado, valor_executado, valor_consolidado, data_vencimento, status_pagamento, "
                     "is_fatura_cartao, cartao_competencia, estouro_orcamento, debito_automatico, status_fatura) values "
                     "(101, 910, '2028-02-01', 'Fatura consolidada', 0, 0, 0, 0, '2028-02-10', 'Pendente', 1, '2028-02-01', "
                     "0, 0, 'FECHADA')")
        if not com_tabela:
            conn.execute('drop table recorrencia_rejeicao')
    for nome in ('r1', 'r2'):
        r = FlaskServico(url, tmp_path, nome, acao='recorrencia', item=STREAMING, meses=1, mes='2028-02-01').resultado()
        assert 'erro' not in r, r
    with sqlite3.connect(caminho) as conn:
        assert conn.execute("select count(*) from lancamento_agregado where mes_fatura = '2028-02-01'").fetchall() == [(0,)]
        if com_tabela:
            assert conn.execute('select competencia, origem, tentativas, situacao from recorrencia_rejeicao').fetchall() == \
                [('2028-02-01', 'FLASK', 2, 'PENDENTE')]
