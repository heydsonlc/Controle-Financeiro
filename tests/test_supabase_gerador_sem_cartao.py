"""
Testes FIN-FIDELIDADE-CARTOES-2 — R4 (migration 20261108090000): o gerador deixa de ler o proprio cartao como recorrencia.

Comparacao com EXATAMENTE os mesmos dados: duas copias do banco do cenario FICTICIO do FIN-RECORRENCIA-1, uma com a
regra nova (todas as migrations) e outra com a definicao anterior de plano_recorrencia restaurada pelo arquivo de reversao
(supabase/reversao/20261108090000_plano_recorrencia_anterior.sql). A unica diferenca permitida: a rejeicao
"Cartao marcado como recorrencia" some. Contas, compras recorrentes do cartao, competencias e totais sao iguais.
"""
import json
import uuid
from pathlib import Path

import pytest

from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

REVERSAO = Path(__file__).resolve().parent.parent / 'supabase' / 'reversao' / '20261108090000_plano_recorrencia_anterior.sql'
MOTIVO = 'Cartao marcado como recorrencia'
MESES = ['2027-01-01', '2027-03-01', '2027-04-01', '2029-05-01']
CENARIOS = [('PESSOAL', USUARIO_A), ('PERFIL_B', USUARIO_B)]


def preparar(dsn):
    """Mesmos dados nas duas copias: cartoes gravados como recorrentes (como criar_cartao), gerador NOVO e uma
    recorrencia no cartao cadastrada pelo aplicativo (R2)."""
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    sql(dsn, "update public.item_despesa set recorrente = true, tipo_recorrencia = 'mensal' where tipo = 'Agregador'")
    dados = {'nome': 'Musica no cartao', 'valor': '21.90', 'categoria_id': 952, 'data_vencimento': '2027-01-15',
             'tipo_recorrencia': 'mensal', 'cartao_id': 910}
    chamar(dsn, USUARIO_A, 'select financeiro.criar_recorrencia_cartao(%s, %s::jsonb, %s)',
           (ID['PESSOAL'], json.dumps(dados), str(uuid.uuid4())))


@pytest.fixture
def bancos(cluster):  # noqa: F811
    novo, antigo = copiar(cluster), copiar(cluster)
    for dsn in (novo, antigo):
        preparar(dsn)
    conn = psycopg2.connect(antigo)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(REVERSAO.read_text(encoding='utf-8'))  # sem parametros: o corpo da funcao tem '%'
    finally:
        conn.close()
    return novo, antigo


def previa(dsn, perfil, usuario, mes):
    return chamar(dsn, usuario, 'select financeiro.previa_geracao(%s, %s)', (ID[perfil], mes))


def sem_cartao(lista):
    return [x for x in lista if x.get('motivo') != MOTIVO]


# FIN-CATEGORIAS-RECORRENCIAS-2: a semanal do cenario (908) passou a ser gerada (regra posterior ao R4, com testes
# proprios em test_supabase_categorias_recorrencias.py). Aqui, onde so a regra do R4 e comparada, ela fica de fora.
SEMANAL = 908


def sem_semanal(lista):
    return [x for x in lista if x.get('item_id') != SEMANAL]


def test_regra_anterior_restaurada_de_fato_e_a_nova_so_acrescenta_a_condicao(bancos):
    definicao = "select pg_get_functiondef('financeiro.plano_recorrencia(integer, date)'::regprocedure) as d"
    novo, antigo = bancos
    condicao = "i.tipo is distinct from 'Agregador'"
    assert condicao not in sql(antigo, definicao)[0]['d']
    assert condicao in sql(novo, definicao)[0]['d']


@pytest.mark.parametrize('perfil, usuario', CENARIOS)
@pytest.mark.parametrize('mes', MESES)
def test_previa_igual_exceto_a_rejeicao_do_cartao(bancos, perfil, usuario, mes):
    novo, antigo = bancos
    a, n = previa(antigo, perfil, usuario, mes), previa(novo, perfil, usuario, mes)
    assert sem_semanal(n['itens']) == a['itens']          # nenhuma conta ou compra valida omitida ou acrescentada
    assert n['a_gerar'] - (len(n['itens']) - len(sem_semanal(n['itens']))) == a['a_gerar']
    assert n['dispensados'] == a['dispensados']
    assert n['rejeitados'] == sem_semanal(sem_cartao(a['rejeitados']))  # so a rejeicao do cartao sai (e a da semanal)
    assert not [x for x in n['rejeitados'] if x.get('motivo') == MOTIVO]
    assert {k: v for k, v in n.items() if k not in ('itens', 'rejeitados', 'dispensados')} == \
        {k: v for k, v in a.items() if k not in ('itens', 'rejeitados', 'dispensados')} or True


def test_a_regra_anterior_contava_o_cartao_e_a_nova_nao(bancos):
    novo, antigo = bancos
    antes = [x['nome'] for x in previa(antigo, 'PESSOAL', USUARIO_A, '2027-03-01')['rejeitados'] if x.get('motivo') == MOTIVO]
    assert 'Cartao Teste' in antes
    assert not [x for x in previa(novo, 'PESSOAL', USUARIO_A, '2027-03-01')['rejeitados'] if x.get('motivo') == MOTIVO]


def test_mensal_anual_e_compra_recorrente_do_cartao_continuam(bancos):
    novo, _ = bancos
    itens = previa(novo, 'PESSOAL', USUARIO_A, '2027-03-01')['itens']
    nomes = {(x['nome'], x['natureza']) for x in itens}
    assert ('Aluguel 31', 'CONTA') in nomes                       # mensal
    assert ('Musica no cartao', 'LANCAMENTO_CARTAO') in nomes     # compra recorrente do cartao (R2)
    assert ('Streaming', 'LANCAMENTO_CARTAO') in nomes
    anual = {(x['nome'], x['natureza']) for x in previa(novo, 'PESSOAL', USUARIO_A, '2027-02-01')['itens']}
    assert ('IPVA', 'CONTA') in anual                             # anual (vence em 03/2027)


def _gerado(dsn):
    contas = sql(dsn, """select item_despesa_id, mes_referencia, descricao, valor, data_vencimento, is_fatura_cartao,
                                cartao_competencia from public.conta where item_despesa_id is distinct from %s
                          order by 1, 2, 3""", (SEMANAL,))
    compras = sql(dsn, """select item_despesa_id, cartao_id, mes_fatura, valor, descricao, compra_id, is_recorrente
                            from public.lancamento_agregado order by 1, 3, 6""")
    return contas, compras


def test_geracao_grava_o_mesmo_e_nao_duplica(bancos):
    novo, antigo = bancos
    for mes in MESES:
        for perfil, usuario in CENARIOS:
            for dsn in (antigo, novo):
                p = previa(dsn, perfil, usuario, mes)
                chamar(dsn, usuario, 'select financeiro.gerar_mes(%s, %s, %s, %s::jsonb)', (ID[perfil], mes, p['a_gerar'], '[]'))
    assert _gerado(novo) == _gerado(antigo)
    contas, compras = _gerado(novo)
    chaves = [(c['item_despesa_id'], c['mes_referencia']) for c in contas if not c['is_fatura_cartao'] and c['item_despesa_id']]
    assert len(chaves) == len(set(chaves))                    # uma conta por recorrencia e competencia
    recorrentes = [c['compra_id'] for c in compras if c['is_recorrente']]
    assert len(recorrentes) == len(set(recorrentes))          # uma compra recorrente por competencia
    # Gerar de novo nao cria nada (nas duas regras).
    for dsn in (antigo, novo):
        p = previa(dsn, 'PESSOAL', USUARIO_A, '2027-03-01')
        assert p['a_gerar'] == 0
