"""
Testes FIN-CARTAO-DESPESAS-FIXAS-01 (migration 20261208090000), em cluster local descartavel com o cenario FICTICIO do
FIN-RECORRENCIA-1: Cartao Teste (910, Pessoal, vence dia 31), Categoria do Cartao 961 (limite 981, R$ 500) mapeada a
Assinaturas (952); Moradia (951) sem vinculo. Recorrencias criadas aqui, em 05/2029. Chamadas como o navegador.
- natureza da compra: parcelada > fixa > Categoria do Cartao > outros;
- parceladas e fixas nao consomem limite, gasto nem complemento da Categoria do Cartao em nenhuma leitura;
- recorrencia nunca conciliada so pelo valor; reconhecida pela descricao (nome ou apelido), o valor so desempata;
- a cobranca real realiza a previsao (uma ocorrencia, previsto preservado, valor-base da recorrencia intacto);
- conciliacao oficial de previsao + cobranca ja lancada, idempotente e reversivel; seguranca; reversao da migration.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import ASSINATURAS, CARTAO, MORADIA, comprar, fatura, pagar, tabela
from tests.test_supabase_recorrencia import (  # noqa: F401  (fixture de modulo reaproveitada)
    ID,
    PG_BIN,
    USUARIO_B,
    atribuir,
    cluster,
    copiar,
    sql,
)
from tests.test_supabase_recorrencia_cartao import criar, falha, gerar_mes, rpc

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
MES = '2029-05-01'
SUPABASE = Path(__file__).resolve().parent.parent / 'supabase'
MIGRATION = SUPABASE / 'migrations' / '20261208090000_financeiro_cartao_despesas_fixas.sql'
REVERSAO = SUPABASE / 'reversao' / '20261208090000_cartao_despesas_fixas_anterior.sql'


@pytest.fixture
def banco(cluster):
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    sql(dsn, 'update public.cartao_categoria_limite set ativo = false where id = 983')  # so o limite 981 (R$ 500)
    sql(dsn, 'update public.item_despesa set ativo = false where id = 906')  # "Streaming" do cenario: so as daqui
    return dsn


def linha(n, descricao, valor, categoria=ASSINATURAS, data='2029-05-12'):
    normal = ' '.join(''.join(c if c.isalnum() else ' ' for c in descricao.lower()).split())
    return {'linha_id': f'csv-{n}', 'linha_origem': n, 'data_compra': data, 'descricao_original': descricao,
            'descricao_normalizada': descricao, 'descricao_exibida': descricao, 'descricao_classificacao': normal,
            'valor': valor, 'parcela_atual': 1, 'total_parcelas': 1, 'tipo_movimento': 'debito',
            **({'categoria_id': categoria} if categoria else {})}


def analisar(dsn, *linhas, mes=MES):
    return rpc(dsn, 'analisar_importacao_cartao', PESSOAL, CARTAO, mes, list(linhas))['linhas']


def importar(dsn, *linhas, mes=MES, chave=None):
    return rpc(dsn, 'importar_fatura_cartao', PESSOAL, CARTAO, mes, list(linhas), chave or str(uuid.uuid4()))


def recorrencia(dsn, nome, valor, categoria=ASSINATURAS):
    return criar(dsn, nome=nome, valor=valor, categoria_id=categoria)['item_id']


def ocorrencia(dsn, item, mes=MES):
    linhas = sql(dsn, 'select * from public.lancamento_agregado where item_despesa_id = %s and mes_fatura = %s', (item, mes))
    assert len(linhas) == 1, linhas
    return linhas[0]


def versao(dsn, lancamento):
    return sql(dsn, 'select financeiro.versao_compra(%s) v', (lancamento,))[0]['v']


def compras(dsn, mes=MES):
    return {c['id']: c for c in tabela(dsn, 'compras_da_fatura', PESSOAL, CARTAO, mes)}


def md5_compras(dsn):
    return sql(dsn, "select coalesce(md5(string_agg(l::text, '|' order by l.id)), '') h from public.lancamento_agregado l")[0]['h']


# ---------------------------------------------------------------------------------------------------------------------
# 1. Natureza unica
# ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('parcelas, recorrente, item, cc, esperado', [
    (3, False, None, 961, 'PARCELADA'), (3, True, 906, 961, 'PARCELADA'), (1, True, 906, 961, 'FIXA'),
    (1, True, 906, None, 'FIXA'), (1, True, None, 961, 'CATEGORIA'), (1, False, None, 961, 'CATEGORIA'),
    (1, False, None, None, 'OUTROS'), (None, None, None, None, 'OUTROS')])
def test_natureza_da_compra(banco, parcelas, recorrente, item, cc, esperado):
    assert sql(banco, 'select financeiro.natureza_da_compra(%s, %s, %s, %s) n', (parcelas, recorrente, item, cc))[0]['n'] == esperado


# ---------------------------------------------------------------------------------------------------------------------
# 2. Leituras: so a natureza CATEGORIA consome a Categoria do Cartao
# ---------------------------------------------------------------------------------------------------------------------

def cenario_leituras(dsn):
    """Fixa R$ 45,90 (Assinaturas -> 961), parcelada 3x de R$ 300 (961), a vista R$ 40 (961) e Moradia R$ 10."""
    item = recorrencia(dsn, 'Streaming no cartao', '45.90')
    gerar_mes(dsn, MES)
    comprar(dsn, descricao='Notebook', valor='300.00', total_parcelas=3)
    comprar(dsn, descricao='Revista', valor='40.00', total_parcelas=1)
    comprar(dsn, descricao='Chaveiro', valor='10.00', total_parcelas=1, categoria_id=MORADIA)
    fixa = ocorrencia(dsn, item)
    assert (fixa['is_recorrente'], fixa['categoria_cartao_id']) == (True, 961)  # gravada como no Flask (compatibilidade)
    return item


def test_fatura_por_categoria_separa_parceladas_e_fixas(banco):
    cenario_leituras(banco)
    r = rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, MES)
    grupos = {g['tipo_grupo']: g for g in r['categorias']}
    assert (grupos['categoria_cartao']['categoria_cartao_id'], grupos['categoria_cartao']['gasto_atual'],
            grupos['categoria_cartao']['quantidade_lancamentos'], grupos['categoria_cartao']['disponivel']) == (961, 40, 1, 460)
    assert (grupos['despesas_fixas']['gasto_atual'], grupos['despesas_fixas']['categoria_cartao_id'],
            grupos['despesas_fixas']['status'], grupos['despesas_fixas']['limite_mensal']) == (0, 'despesas_fixas', 'Contratada', None)
    # FIN-CARTAO-PREVISTO-EXECUTADO-01: a fixa ainda sem cobranca fica fora do executado, no previsto pendente
    assert grupos['despesas_fixas']['previsto_pendente'] == 45.9
    assert (grupos['compras_parceladas']['gasto_atual'], grupos['compras_parceladas']['categoria_cartao_id']) == (100, 'compras_parceladas')
    assert (grupos['sem_categoria']['gasto_atual'], grupos['sem_categoria']['quantidade_lancamentos']) == (10, 1)
    assert [g['tipo_grupo'] for g in r['categorias']] == ['categoria_cartao', 'compras_parceladas', 'despesas_fixas', 'sem_categoria']
    assert sum(g['gasto_atual'] for g in r['categorias']) == r['total_fatura'] == 150  # nada perdido nem duplicado
    assert (r['total_com_categoria'], r['total_sem_categoria_cartao'], r['total_despesas_fixas'],
            r['total_compras_parceladas'], r['disponivel_total']) == (40, 10, 0, 100, 460)


def test_limites_e_lancamentos_por_filtro(banco):
    cenario_leituras(banco)
    limite = next(x for x in tabela(banco, 'limites_do_cartao', PESSOAL, CARTAO, MES) if x['id'] == 981)
    assert (limite['gasto_atual'], limite['disponivel']) == (40, 460)

    def filtro(f):
        return sorted(l['descricao'] for l in rpc(banco, 'lancamentos_fatura_por_categoria', PESSOAL, CARTAO, MES, f)['lancamentos'])
    assert filtro('961') == ['Revista']
    assert filtro('despesas_fixas') == ['Streaming no cartao']
    assert filtro('compras_parceladas') == ['Notebook']
    assert filtro('sem_categoria') == ['Chaveiro']
    todos = rpc(banco, 'lancamentos_fatura_por_categoria', PESSOAL, CARTAO, MES, 'todos')['lancamentos']
    assert len(todos) == 4
    assert {l['descricao']: (l['natureza'], l['status_classificacao']) for l in todos}['Streaming no cartao'] == ('FIXA', 'classificado')


def test_previsto_da_lista_e_das_faturas_sem_abater_parceladas_e_fixas(banco):
    cenario_leituras(banco)
    f = fatura(banco, CARTAO, MES)
    linha_lista = next(c for c in tabela(banco, 'contas_do_mes', PESSOAL, MES) if c['id'] == f['id'])
    # executado 150,00 (sem a fixa prevista de 45,90: FIN-CARTAO-PREVISTO-EXECUTADO-01); previsto = executado + 45,90
    # previstos + o que falta do limite 961 (500 - 40, so a compra variavel) = 655,90, como antes
    assert (Decimal(str(linha_lista['valor_executado'])), Decimal(str(linha_lista['valor_previsto']))) == \
        (Decimal('150.00'), Decimal('655.90'))
    cartao = next(x for x in tabela(banco, 'faturas_do_mes', PESSOAL, MES) if x['cartao_id'] == CARTAO)
    assert (Decimal(str(cartao['valor_executado'])), Decimal(str(cartao['valor_previsto']))) == (Decimal('150.00'), Decimal('655.90'))


def test_dashboard_sem_parceladas_e_fixas(banco):
    cenario_leituras(banco)
    d = rpc(banco, 'dashboard_resumo_tela', PESSOAL, '2029-05')
    assert next(c for c in d['categorias_cartao'] if c['categoria_cartao_id'] == 961)['gasto'] == 40
    # uso dos limites do cartao: a compra variavel e a sem Categoria do Cartao (40 + 10); parcela e fixa fora
    assert next(c for c in d['cartoes_limites']['itens'] if c['id'] == CARTAO)['utilizado'] == 50


def test_compras_da_fatura_traz_natureza_e_previsto(banco):
    item = cenario_leituras(banco)
    lidas = compras(banco)
    fixa = lidas[ocorrencia(banco, item)['id']]
    assert (fixa['natureza'], fixa['valor_previsto'], fixa['situacao_ocorrencia'], fixa['recorrente']) == ('FIXA', 45.9, 'PREVISTA', True)
    por_nome = {c['descricao']: c for c in lidas.values()}
    assert (por_nome['Notebook']['natureza'], por_nome['Notebook']['valor_previsto']) == ('PARCELADA', 100)
    assert (por_nome['Revista']['natureza'], por_nome['Revista']['valor_previsto'], por_nome['Revista']['situacao_ocorrencia']) == \
        ('CATEGORIA', None, None)
    assert por_nome['Chaveiro']['natureza'] == 'OUTROS'


# ---------------------------------------------------------------------------------------------------------------------
# 3. Reconhecimento: nunca so pelo valor; descricao e apelido; o valor so desempata
# ---------------------------------------------------------------------------------------------------------------------

def assinaturas(dsn):
    ids = {n: recorrencia(dsn, n, v) for n, v in (('Netflix', '59.90'), ('Apple One', '59.90'), ('ChatGPT', '99.90'),
                                                  ('Claude', '109.90'))}
    gerar_mes(dsn, MES)
    return ids


def test_valor_igual_sozinho_nao_concilia_recorrencia(banco):
    ids = assinaturas(banco)
    apple, chatgpt = analisar(banco, linha(1, 'APPLE.COM/BILL', '59.90'), linha(2, 'CHATGPT', '109.90'))
    # Apple One e Netflix tem o mesmo valor: nenhuma das duas e "achada" pelo valor
    assert (apple['status'], apple['conciliacao'], apple['recorrencia_id'], apple['realiza_lancamento_id']) == ('valido', None, None, None)
    # ChatGPT reajustado para o valor do Claude e o ChatGPT, nunca o Claude
    assert (chatgpt['status'], chatgpt['conciliacao'], chatgpt['recorrencia_id']) == ('valido', None, ids['ChatGPT'])
    assert (chatgpt['realiza_lancamento_id'], chatgpt['valor_previsto']) == (ocorrencia(banco, ids['ChatGPT'])['id'], 99.9)


@pytest.mark.parametrize('descricao, valor, nome', [
    ('NETFLIX ENTRETENIMENTO BARUERI', '44.90', 'Netflix'), ('NETFLIX.COM', '59.90', 'Netflix'),
    ('OPENAI*CHATGPT', '99.90', 'ChatGPT'), ('ANTHROPIC*CLAUDE', '109.90', 'Claude'), ('CLAUDE.AI', '120.00', 'Claude')])
def test_descricao_da_administradora_reconhece_a_recorrencia(banco, descricao, valor, nome):
    ids = assinaturas(banco)
    r = analisar(banco, linha(1, descricao, valor, categoria=None))[0]
    assert (r['status'], r['recorrencia_id'], r['recorrencia_nome']) == ('valido', ids[nome], nome)
    assert r['realiza_lancamento_id'] == ocorrencia(banco, ids[nome])['id']
    assert (r['categoria_id'], r['categoria_origem']) == (ASSINATURAS, 'recorrencia')  # a Categoria de Despesa da recorrencia


def test_apelido_de_cobranca(banco):
    ids = assinaturas(banco)
    assert analisar(banco, linha(1, 'APPLE.COM/BILL', '59.90'))[0]['recorrencia_id'] is None
    a = rpc(banco, 'criar_apelido_recorrencia', PESSOAL, ids['Apple One'], 'APPLE.COM/BILL')
    assert a['apelido'] == 'apple com bill'
    assert rpc(banco, 'apelidos_da_recorrencia', PESSOAL, ids['Apple One'])[0]['apelido'] == 'apple com bill'
    r = analisar(banco, linha(1, 'APPLE.COM/BILL', '59.90'))[0]
    assert (r['recorrencia_id'], r['realiza_lancamento_id']) == (ids['Apple One'], ocorrencia(banco, ids['Apple One'])['id'])
    # o mesmo apelido em outra recorrencia do cartao, ou o nome de outra, criaria ambiguidade: recusado
    assert falha(banco, 'criar_apelido_recorrencia', PESSOAL, ids['Netflix'], 'apple.com bill')[0] == '22023'
    assert falha(banco, 'criar_apelido_recorrencia', PESSOAL, ids['Netflix'], 'Claude')[0] == '22023'
    assert falha(banco, 'criar_apelido_recorrencia', PESSOAL, ids['Netflix'], 'tv')[0] == '22023'
    assert falha(banco, 'criar_apelido_recorrencia', PESSOAL, ids['Netflix'], 'apple tv', usuario=USUARIO_B)[0] == '42501'
    rpc(banco, 'remover_apelido_recorrencia', PESSOAL, a['id'])
    assert analisar(banco, linha(1, 'APPLE.COM/BILL', '59.90'))[0]['recorrencia_id'] is None


def test_ambiguidade_desempata_pelo_texto_inteiro_e_pelo_valor(banco):
    duo = recorrencia(banco, 'Spotify Duo', '34.90')
    familia = recorrencia(banco, 'Spotify', '40.90')
    gerar_mes(banco, MES)
    exato, por_valor, ambigua = analisar(banco, linha(1, 'SPOTIFY DUO', '30.00'), linha(2, 'SPOTIFY DUO SP', '40.90'),
                                         linha(3, 'SPOTIFY DUO SP', '31.00'))
    assert exato['recorrencia_id'] == duo
    assert por_valor['recorrencia_id'] == familia
    assert (ambigua['status'], ambigua['recorrencia_id'], ambigua['realiza_lancamento_id']) == ('revisar', None, None)
    assert [c['id'] for c in ambigua['recorrencias_candidatas']] == [duo, familia]
    assert 'Mais de uma recorrencia do cartao' in ' '.join(ambigua['mensagens'])


def test_outro_cartao_nao_reconhece(banco):
    assinaturas(banco)
    r = rpc(banco, 'analisar_importacao_cartao', PESSOAL, 911, MES, [linha(1, 'NETFLIX', '59.90')])
    assert r['linhas'][0]['recorrencia_id'] is None


def test_analise_nao_grava(banco):
    assinaturas(banco)
    antes = md5_compras(banco)
    analisar(banco, linha(1, 'NETFLIX ENTRETENIMENTO BARUERI', '44.90'), linha(2, 'APPLE.COM/BILL', '59.90'))
    assert md5_compras(banco) == antes


# ---------------------------------------------------------------------------------------------------------------------
# 4. A cobranca real realiza a previsao
# ---------------------------------------------------------------------------------------------------------------------

def test_importacao_realiza_a_previsao_sem_duplicar(banco):
    ids = assinaturas(banco)
    prevista = ocorrencia(banco, ids['Netflix'])
    r = importar(banco, linha(1, 'NETFLIX ENTRETENIMENTO BARUERI', '44.90', data='2029-05-17'))
    assert (r['inseridos'], r['realizadas']) == (0, 1)
    real = ocorrencia(banco, ids['Netflix'])  # continua uma so
    assert (real['id'], real['compra_id'], real['valor'], real['is_importado'], real['descricao_original'],
            str(real['data_compra'])) == (prevista['id'], prevista['compra_id'], Decimal('44.90'), True,
                                          'NETFLIX ENTRETENIMENTO BARUERI', '2029-05-17')
    oc = sql(banco, 'select * from financeiro.ocorrencia_recorrencia_cartao where lancamento_id = %s', (real['id'],))[0]
    assert (oc['valor_previsto'], oc['valor_executado'], oc['origem'], oc['lancamento_absorvido']) == \
        (Decimal('59.90'), Decimal('44.90'), 'IMPORTACAO', None)
    lida = compras(banco)[real['id']]
    assert (lida['natureza'], lida['valor'], lida['valor_previsto'], lida['situacao_ocorrencia']) == ('FIXA', 44.9, 59.9, 'CONFIRMADA')
    # so a cobranca real: as previsoes de ChatGPT, Claude e Apple One ficam fora (FIN-CARTAO-PREVISTO-EXECUTADO-01)
    assert fatura(banco, CARTAO, MES)['valor_executado'] == Decimal('44.90')
    # valor-base da recorrencia intacto; a proxima competencia continua prevista em R$ 59,90
    assert sql(banco, 'select valor from public.item_despesa where id = %s', (ids['Netflix'],))[0]['valor'] == Decimal('59.90')
    gerar_mes(banco, '2029-06-01')
    assert ocorrencia(banco, ids['Netflix'], '2029-06-01')['valor'] == Decimal('59.90')
    # reimportar o mesmo arquivo: duplicada; outra cobranca da mesma recorrencia no mes: a compra fica como esta
    dup, outra = analisar(banco, linha(1, 'NETFLIX ENTRETENIMENTO BARUERI', '44.90', data='2029-05-17'),
                          linha(2, 'NETFLIX', '12.00', data='2029-05-20'))
    assert dup['status'] == 'duplicado'
    assert (outra['status'], outra['realiza_lancamento_id'], outra['ignorar']) == ('revisar', None, False)  # FIN-CARTAO-IMPORTACAO-FIXAS-01: pede revisao (nao e descartada)


def test_sem_previsao_a_linha_vira_a_ocorrencia(banco):
    item = recorrencia(banco, 'Netflix', '59.90')  # recorrencia criada, mes ainda nao gerado
    r = importar(banco, linha(1, 'NETFLIX.COM', '59.90', categoria=None))
    assert (r['inseridos'], r['realizadas']) == (1, 0)
    l = ocorrencia(banco, item)
    assert (l['is_recorrente'], l['categoria_id'], l['is_importado']) == (True, ASSINATURAS, True)
    gerar_mes(banco, MES)
    ocorrencia(banco, item)  # o gerador nao lanca outra


def test_previsao_em_fatura_paga_nao_muda(banco):
    ids = assinaturas(banco)
    pagar(banco, CARTAO, MES)
    r = analisar(banco, linha(1, 'NETFLIX ENTRETENIMENTO', '44.90'))[0]
    assert (r['status'], r['realiza_lancamento_id'], r['ignorar']) == ('revisar', None, False)  # FIN-CARTAO-IMPORTACAO-FIXAS-01: pede revisao (nao e descartada)
    assert ocorrencia(banco, ids['Netflix'])['valor'] == Decimal('59.90')


# ---------------------------------------------------------------------------------------------------------------------
# 5. Conciliacao oficial (previsao + cobranca ja lancada) e reversao
# ---------------------------------------------------------------------------------------------------------------------

def caso_netflix(dsn):
    """A previsao de R$ 59,90 e a cobranca real de R$ 44,90 lancada antes como compra comum (o caso de 11/2026)."""
    item = recorrencia(dsn, 'Netflix', '59.90')
    gerar_mes(dsn, MES)
    cobranca = comprar(dsn, descricao='NETFLIX ENTRETENIMENTO BARUERI', valor='44.90', total_parcelas=1,
                       data_compra='2029-05-17')['lancamentos'][0]
    return item, ocorrencia(dsn, item)['id'], cobranca


def conciliar(dsn, previsto, cobranca, chave=None, usuario=None, **kw):
    args = (PESSOAL, previsto, versao(dsn, previsto), cobranca, versao(dsn, cobranca), chave or str(uuid.uuid4()))
    return (falha if kw.get('erro') else rpc)(dsn, 'conciliar_ocorrencia_recorrencia', *args, **({'usuario': usuario} if usuario else {}))


def test_conciliacao_netflix_uma_ocorrencia_e_reversao(banco):
    item, previsto, cobranca = caso_netflix(banco)
    absorvida = sql(banco, 'select * from public.lancamento_agregado where id = %s', (cobranca,))[0]
    # so a cobranca real; a previsao fica fora do executado (FIN-CARTAO-PREVISTO-EXECUTADO-01)
    assert fatura(banco, CARTAO, MES)['valor_executado'] == Decimal('44.90')
    chave = str(uuid.uuid4())
    r = conciliar(banco, previsto, cobranca, chave=chave)
    assert (r['valor_previsto'], r['valor_executado'], r['diferenca']) == (59.9, 44.9, -15.0)
    assert sql(banco, 'select count(*) n from public.lancamento_agregado where id = %s', (cobranca,))[0]['n'] == 0
    l = ocorrencia(banco, item)
    assert (l['id'], l['valor'], l['descricao_original_normalizada'], l['is_recorrente']) == \
        (previsto, Decimal('44.90'), 'NETFLIX ENTRETENIMENTO BARUERI', True)
    assert fatura(banco, CARTAO, MES)['valor_executado'] == Decimal('44.90')
    oc = sql(banco, 'select * from financeiro.ocorrencia_recorrencia_cartao where id = %s', (r['ocorrencia_id'],))[0]
    assert (oc['origem'], oc['lancamento_absorvido']['id'], oc['lancamento_absorvido']['valor']) == ('CONCILIACAO', cobranca, 44.9)
    assert compras(banco)[previsto]['valor_previsto'] == 59.9
    assert sql(banco, 'select valor from public.item_despesa where id = %s', (item,))[0]['valor'] == Decimal('59.90')
    # mesma chave: devolve o mesmo resultado, sem repetir
    repetida = rpc(banco, 'conciliar_ocorrencia_recorrencia', PESSOAL, previsto, 'x', cobranca, 'y', chave)
    assert repetida['repetida'] is True
    # reversao: a previsao volta como era e a cobranca volta inteira, com o mesmo id
    rpc(banco, 'reverter_ocorrencia_recorrencia', PESSOAL, r['ocorrencia_id'], str(uuid.uuid4()))
    assert ocorrencia(banco, item)['valor'] == Decimal('59.90')
    volta = sql(banco, 'select * from public.lancamento_agregado where id = %s', (cobranca,))[0]
    assert dict(volta) == dict(absorvida)
    assert fatura(banco, CARTAO, MES)['valor_executado'] == Decimal('44.90')
    assert falha(banco, 'reverter_ocorrencia_recorrencia', PESSOAL, r['ocorrencia_id'], str(uuid.uuid4()))[0] == 'P0001'


def test_conciliacao_recusada(banco):
    item, previsto, cobranca = caso_netflix(banco)
    parcelada = comprar(banco, descricao='TV', valor='300.00', total_parcelas=3)['lancamentos'][0]
    assert conciliar(banco, previsto, parcelada, erro=True)[0] == '22023'          # parcelada nao e cobranca de fixa
    assert conciliar(banco, cobranca, previsto, erro=True)[0] == '22023'           # invertidas: a "cobranca" e a fixa
    assert falha(banco, 'conciliar_ocorrencia_recorrencia', PESSOAL, previsto, 'versao-velha', cobranca,
                 versao(banco, cobranca), str(uuid.uuid4()))[0] == 'P0001'          # versao
    assert conciliar(banco, previsto, cobranca, usuario=USUARIO_B, erro=True)[0] == '42501'
    pagar(banco, CARTAO, MES)
    assert conciliar(banco, previsto, cobranca, erro=True)[0] == 'P0001'           # fatura paga
    assert sql(banco, 'select count(*) n from financeiro.ocorrencia_recorrencia_cartao')[0]['n'] == 0


def test_reversao_recusada_se_a_compra_mudou(banco):
    item, previsto, cobranca = caso_netflix(banco)
    r = conciliar(banco, previsto, cobranca)
    sql(banco, 'update public.lancamento_agregado set valor = 50.00 where id = %s', (previsto,))  # edicao posterior (simulada)
    assert falha(banco, 'reverter_ocorrencia_recorrencia', PESSOAL, r['ocorrencia_id'], str(uuid.uuid4()))[0] == 'P0001'


# ---------------------------------------------------------------------------------------------------------------------
# 6. Seguranca e reversao da migration
# ---------------------------------------------------------------------------------------------------------------------

TELA = ['financeiro.conciliar_ocorrencia_recorrencia(integer, integer, text, integer, text, uuid)',
        'financeiro.reverter_ocorrencia_recorrencia(integer, bigint, uuid)',
        'financeiro.apelidos_da_recorrencia(integer, integer)',
        'financeiro.criar_apelido_recorrencia(integer, integer, text)',
        'financeiro.remover_apelido_recorrencia(integer, bigint)',
        'financeiro.compras_da_fatura(integer, integer, date)']
INTERNAS = ['financeiro.natureza_da_compra(integer, boolean, integer, integer)', 'financeiro.texto_cobranca(text)',
            'financeiro.realizar_ocorrencia_recorrencia(integer, integer, jsonb, text, jsonb)',
            'financeiro.recorrencia_cartao_do_perfil(integer, integer)']


@pytest.mark.parametrize('funcao', TELA + INTERNAS)
def test_funcoes_seguras(banco, funcao):
    f = sql(banco, f"select prosecdef, proconfig, has_function_privilege('anon', '{funcao}', 'execute') anon, "
                   f"has_function_privilege('authenticated', '{funcao}', 'execute') autenticado "
                   f"from pg_proc where oid = '{funcao}'::regprocedure")[0]
    assert f['proconfig'] == ['search_path=""']
    assert f['anon'] is False
    assert f['autenticado'] is (funcao in TELA)
    assert f['prosecdef'] is (funcao not in INTERNAS[:2])


@pytest.mark.parametrize('tabela_nova', ['ocorrencia_recorrencia_cartao', 'recorrencia_apelido'])
def test_tabelas_fechadas(banco, tabela_nova):
    t = sql(banco, "select relrowsecurity, relforcerowsecurity, "
                   "has_table_privilege('authenticated', c.oid, 'select') sel, has_table_privilege('anon', c.oid, 'select') anon "
                   "from pg_class c where oid = %s::regclass", (f'financeiro.{tabela_nova}',))[0]
    assert (t['relrowsecurity'], t['relforcerowsecurity'], t['sel'], t['anon']) == (True, True, False, False)


def executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_da_migration_e_reaplicacao(banco):
    cenario_leituras(banco)
    item, previsto, cobranca = caso_netflix(banco)
    r = conciliar(banco, previsto, cobranca)
    with pytest.raises(psycopg2.Error):
        executar(banco, REVERSAO)  # ha ocorrencia vigente: recusada, nada muda
    rpc(banco, 'reverter_ocorrencia_recorrencia', PESSOAL, r['ocorrencia_id'], str(uuid.uuid4()))
    sql(banco, 'delete from financeiro.ocorrencia_recorrencia_cartao')  # historico de teste (a tabela e removida na reversao)
    executar(banco, REVERSAO)
    antigo = {g['categoria_cartao_id']: g for g in rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, MES)['categorias']}
    assert antigo[961]['gasto_atual'] > 40  # regra anterior: fixas e parceladas consumiam o limite
    assert 'natureza' not in tabela(banco, 'compras_da_fatura', PESSOAL, CARTAO, MES)[0]
    executar(banco, MIGRATION)
    novo = {g['tipo_grupo']: g for g in rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, MES)['categorias']}
    assert novo['categoria_cartao']['gasto_atual'] == 40 + 44.9  # a Revista e a cobranca comum da Netflix (restaurada)
    assert sql(banco, "select has_function_privilege('anon', 'financeiro.compras_da_fatura(integer, integer, date)', 'execute') a")[0]['a'] is False
