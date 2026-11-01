"""
Testes FIN-CARTAO-IMPORTACAO-FIXAS-01 (migration 20261210090000), em cluster local descartavel com o cenario FICTICIO do
FIN-RECORRENCIA-1 (Cartao Teste 910, Pessoal; Categoria do Cartao 961 com limite de R$ 500 para Assinaturas 952; Moradia
951 sem vinculo). Recorrencias criadas aqui, em 05/2029. Chamadas como o navegador.
- previa: classificacao proposta (ja existente, parcela existente, despesa fixa com previsto/cobrado/diferenca, parcelada,
  compra comum, revisar) e as recorrencias que a tela pode escolher; nada e gravado;
- correcao do usuario: outra recorrencia, compra comum, apelido (gravado so na confirmacao);
- confirmacao: realiza a previsao, concilia a compra ja lancada quando pedido, grava as compras; transacional e idempotente;
- reimportacao integral e complementar; repetida no arquivo; duas cobrancas do mesmo servico; ambiguidade; recorrencia
  inativada; fatura fechada e paga; reversao; concorrencia; permissoes; reversao da migration.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartao_despesas_fixas import (  # noqa: F401  (fixture e ajudantes reaproveitados)
    MES,
    PESSOAL,
    assinaturas,
    banco,
    caso_netflix,
    md5_compras,
    ocorrencia,
    recorrencia,
)
from tests.test_supabase_cartoes import ASSINATURAS, CARTAO, comprar, fatura, pagar, tabela
from tests.test_supabase_despesas import _paralelo
from tests.test_supabase_recorrencia import PG_BIN, USUARIO_B, cluster, sql  # noqa: F401
from tests.test_supabase_recorrencia_cartao import falha, gerar_mes, rpc

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

SUPABASE = Path(__file__).resolve().parent.parent / 'supabase'
MIGRATION = SUPABASE / 'migrations' / '20261210090000_financeiro_cartao_importacao_fixas.sql'
REVERSAO = SUPABASE / 'reversao' / '20261210090000_cartao_importacao_fixas_anterior.sql'


def D(valor):
    return Decimal(str(valor)).quantize(Decimal('0.01'))


def linha(n, descricao, valor, data='2029-05-12', categoria=ASSINATURAS, parcela=(1, 1), **extra):
    normal = ' '.join(''.join(c if c.isalnum() else ' ' for c in descricao.lower()).split())
    return {'linha_id': f'csv-{n}', 'linha_origem': n, 'data_compra': data, 'descricao_original': descricao,
            'descricao_normalizada': descricao, 'descricao_exibida': descricao, 'descricao_classificacao': normal,
            'valor': valor, 'parcela_atual': parcela[0], 'total_parcelas': parcela[1], 'tipo_movimento': 'debito',
            **({'categoria_id': categoria} if categoria else {}), **extra}


def previa(dsn, *linhas, mes=MES, usuario=None):
    return rpc(dsn, 'analisar_importacao_cartao', PESSOAL, CARTAO, mes, list(linhas), **({'usuario': usuario} if usuario else {}))


def importar(dsn, *linhas, mes=MES, chave=None):
    return rpc(dsn, 'importar_fatura_cartao', PESSOAL, CARTAO, mes, list(linhas), chave or str(uuid.uuid4()))


def executado(dsn, mes=MES):
    f = fatura(dsn, CARTAO, mes)
    c = next(x for x in tabela(dsn, 'contas_do_mes', PESSOAL, mes) if x['id'] == f['id'])
    return D(c['valor_executado'])


def situacao(dsn, item, mes=MES):
    lid = ocorrencia(dsn, item, mes)['id']
    return next(c for c in tabela(dsn, 'compras_da_fatura', PESSOAL, CARTAO, mes) if c['id'] == lid)['situacao_ocorrencia']


# ---------------------------------------------------------------------------------------------------------------------
# 1. Previa: classificacao proposta, sem gravar nada
# ---------------------------------------------------------------------------------------------------------------------

def test_previa_classifica_cada_linha_sem_gravar(banco):
    ids = assinaturas(banco)
    comprar(banco, descricao='Revista', valor='40.00', total_parcelas=1)        # ja existente
    comprar(banco, descricao='Notebook', valor='300.00', total_parcelas=3)      # parcela 1/3 de 100,00 ja existente
    spotify = (recorrencia(banco, 'Spotify Duo', '34.90'), recorrencia(banco, 'Spotify', '40.90'))
    gerar_mes(banco, MES)
    antes = md5_compras(banco)
    r = previa(banco,
               linha(1, 'NETFLIX.COM', '44.90', categoria=None),
               linha(2, 'APPLE.COM/BILL', '59.90'),
               linha(3, 'TV LOJA', '150.00', parcela=(1, 3)),  # valor diferente da parcela do Notebook
               linha(4, 'Revista', '40.00', data='2029-05-10'),
               linha(5, 'Notebook', '100.00', data='2029-05-10', parcela=(1, 3)),
               linha(6, 'SPOTIFY DUO SP', '31.00'))
    assert md5_compras(banco) == antes
    c = {l['linha_origem']: l for l in r['linhas']}
    assert [c[i]['classificacao_importacao'] for i in range(1, 7)] == \
        ['DESPESA_FIXA', 'COMPRA', 'PARCELADA', 'JA_EXISTENTE', 'PARCELA_EXISTENTE', 'REVISAR']
    fixa = c[1]['despesa_fixa']
    assert (fixa['nome'], fixa['valor_previsto'], fixa['valor_cobrado'], fixa['diferenca'], fixa['competencia'],
            fixa['fatura_destino'], fixa['realiza_lancamento_id']) == \
        ('Netflix', 59.9, 44.9, -15.0, '05/2029', '05/2029', ocorrencia(banco, ids['Netflix'])['id'])
    assert [x['id'] for x in c[6]['recorrencias_candidatas']] == list(spotify)
    assert {x['nome'] for x in r['recorrencias_cartao']} >= {'Netflix', 'Claude', 'ChatGPT', 'Apple One', 'Spotify', 'Spotify Duo'}
    assert (r['validacoes']['despesas_fixas'], r['validacoes']['realizacoes']) == (1, 1)


# ---------------------------------------------------------------------------------------------------------------------
# 2. Correcao do usuario na previa
# ---------------------------------------------------------------------------------------------------------------------

def test_escolher_recorrencia_e_lembrar_o_apelido_so_na_confirmacao(banco):
    ids = assinaturas(banco)
    r = previa(banco, linha(1, 'APPLE.COM/BILL', '59.90', recorrencia_escolhida_id=ids['Apple One'], salvar_apelido=True))['linhas'][0]
    assert (r['classificacao_importacao'], r['despesa_fixa']['nome'], r['apelido_sugerido'], r['salvar_apelido']) == \
        ('DESPESA_FIXA', 'Apple One', 'apple com bill', True)
    assert sql(banco, 'select count(*) n from financeiro.recorrencia_apelido')[0]['n'] == 0  # a previa nao grava
    res = importar(banco, linha(1, 'APPLE.COM/BILL', '59.90', recorrencia_escolhida_id=ids['Apple One'], salvar_apelido=True))
    assert (res['realizadas'], res['apelidos']) == (1, 1)
    assert situacao(banco, ids['Apple One']) == 'CONFIRMADA'
    assert sql(banco, 'select apelido from financeiro.recorrencia_apelido where item_despesa_id = %s',
               (ids['Apple One'],))[0]['apelido'] == 'apple com bill'
    # no mes seguinte o apelido reconhece sozinho
    junho = previa(banco, linha(1, 'APPLE.COM/BILL', '59.90', data='2029-06-12'), mes='2029-06-01')['linhas'][0]
    assert (junho['classificacao_importacao'], junho['despesa_fixa']['nome']) == ('DESPESA_FIXA', 'Apple One')


def test_tratar_como_compra_comum(banco):
    ids = assinaturas(banco)
    r = previa(banco, linha(1, 'NETFLIX.COM', '44.90', recorrencia_escolhida_id=0))['linhas'][0]
    assert (r['classificacao_importacao'], r['recorrencia_id'], r['realiza_lancamento_id']) == ('COMPRA', None, None)
    importar(banco, linha(1, 'NETFLIX.COM', '44.90', recorrencia_escolhida_id=0))
    assert situacao(banco, ids['Netflix']) == 'PREVISTA'
    assert executado(banco) == D('44.90')  # a compra comum; a previsao segue fora


def test_escolha_invalida_pede_revisao(banco):
    assinaturas(banco)
    outra = sql(banco, "select id from public.item_despesa where tipo <> 'Agregador' and coalesce(recorrente, false) "
                       "and meio_pagamento is distinct from 'cartao' order by id limit 1")[0]['id']
    r = previa(banco, linha(1, 'NETFLIX.COM', '44.90', recorrencia_escolhida_id=outra))['linhas'][0]
    assert (r['status'], r['classificacao_importacao']) == ('revisar', 'REVISAR')


# ---------------------------------------------------------------------------------------------------------------------
# 3. Conciliacao na confirmacao (compra ja lancada e ainda nao conciliada)
# ---------------------------------------------------------------------------------------------------------------------

def test_compra_ja_lancada_conciliada_na_confirmacao(banco):
    item, previsto, cobranca = caso_netflix(banco)  # previsao 59,90 + compra comum 44,90 em 17/05
    l = linha(1, 'NETFLIX ENTRETENIMENTO BARUERI', '44.90', data='2029-05-17')
    r = previa(banco, l)['linhas'][0]
    assert (r['classificacao_importacao'], r['conciliar_previsao']) == ('JA_EXISTENTE', False)
    s = r['conciliacao_sugerida']
    assert (s['previsto_id'], s['cobranca_id'], s['recorrencia_nome'], s['valor_previsto'], s['valor_cobrado'], s['diferenca']) == \
        (previsto, cobranca, 'Netflix', 59.9, 44.9, -15.0)
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, [l], str(uuid.uuid4()))[1] == 'Nenhuma linha para importar'
    assert executado(banco) == D('44.90')
    res = importar(banco, {**l, 'conciliar_previsao': True})
    assert (res['conciliadas'], res['inseridos'], res['realizadas']) == (1, 0, 0)
    assert situacao(banco, item) == 'CONFIRMADA'
    assert sql(banco, 'select count(*) n from public.lancamento_agregado where id = %s', (cobranca,))[0]['n'] == 0
    assert executado(banco) == D('44.90')  # uma cobranca so: a previsao confirmada pelo valor cobrado
    oc = sql(banco, "select * from financeiro.ocorrencia_recorrencia_cartao where origem = 'CONCILIACAO'")[0]
    assert (oc['lancamento_id'], oc['valor_previsto'], oc['valor_executado'], oc['lancamento_absorvido']['id']) == \
        (previsto, D('59.90'), D('44.90'), cobranca)
    # reimportar: a linha agora e a propria ocorrencia (duplicada), sem nova sugestao
    de_novo = previa(banco, l)['linhas'][0]
    assert (de_novo['classificacao_importacao'], de_novo['conciliacao_sugerida']) == ('JA_EXISTENTE', None)
    # reversao pela funcao oficial
    rpc(banco, 'reverter_ocorrencia_recorrencia', PESSOAL, oc['id'], str(uuid.uuid4()))
    assert situacao(banco, item) == 'PREVISTA'
    assert sql(banco, 'select count(*) n from public.lancamento_agregado where id = %s', (cobranca,))[0]['n'] == 1


def test_concorrencia_conciliacao_uma_vez(banco):
    item, previsto, cobranca = caso_netflix(banco)
    l = {**linha(1, 'NETFLIX ENTRETENIMENTO BARUERI', '44.90', data='2029-05-17'), 'conciliar_previsao': True}
    resultados = _paralelo([lambda: importar(banco, l) for _ in range(2)])
    assert sorted(r[0] for r in resultados) == ['erro', 'ok']
    assert sql(banco, "select count(*) n from financeiro.ocorrencia_recorrencia_cartao where origem = 'CONCILIACAO'")[0]['n'] == 1
    assert executado(banco) == D('44.90')


# ---------------------------------------------------------------------------------------------------------------------
# 4. Reimportacao, complementar, idempotencia e repetidas
# ---------------------------------------------------------------------------------------------------------------------

def test_reimportacao_integral_e_complementar(banco):
    ids = assinaturas(banco)
    arquivo = [linha(1, 'NETFLIX.COM', '44.90', categoria=None), linha(2, 'PADARIA', '12.00')]
    chave = str(uuid.uuid4())
    primeira = importar(banco, *arquivo, chave=chave)
    assert (primeira['realizadas'], primeira['inseridos']) == (1, 1)
    assert importar(banco, *arquivo, chave=chave)['repetida'] is True  # mesma chave: mesmo resultado
    antes = md5_compras(banco)
    r = previa(banco, *arquivo)['linhas']
    assert [l['classificacao_importacao'] for l in r] == ['JA_EXISTENTE', 'JA_EXISTENTE']
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, arquivo, str(uuid.uuid4()))[1] == 'Nenhuma linha para importar'
    assert md5_compras(banco) == antes  # reimportacao integral: nada muda
    complementar = importar(banco, *arquivo, linha(3, 'FARMACIA', '25.00'))
    assert (complementar['inseridos'], complementar['realizadas'], complementar['duplicados']) == (1, 0, 2)
    assert executado(banco) == D('81.90')  # 44,90 + 12 + 25; as outras previsoes seguem fora
    assert situacao(banco, ids['Claude']) == 'PREVISTA'


def test_compra_casada_pelo_valor_mantida_como_diferente(banco):
    """Regra herdada: mesmo valor e parcela, ate 5 dias, casa com a compra ja lancada; o usuario pode manter a nova."""
    assinaturas(banco)
    comprar(banco, descricao='Mercado do bairro', valor='50.00', total_parcelas=1, data_compra='2029-05-10')
    l = linha(1, 'MERCADO BAIRRO*LOJA 2', '50.00', data='2029-05-12')
    r = previa(banco, l)['linhas'][0]
    assert (r['status'], r['classificacao_importacao']) == ('conciliado', 'JA_EXISTENTE')
    mantida = previa(banco, {**l, 'manter_conciliada': True})['linhas'][0]
    assert (mantida['status'], mantida['classificacao_importacao']) == ('valido', 'COMPRA')
    importar(banco, {**l, 'manter_conciliada': True})
    assert len(sql(banco, "select id from public.lancamento_agregado where valor = 50.00 and mes_fatura = %s", (MES,))) == 2


def test_repetida_no_arquivo_so_entra_se_mantida(banco):
    assinaturas(banco)
    a, b = linha(1, 'CAFE', '5.00'), linha(2, 'CAFE', '5.00')
    r = previa(banco, a, b)['linhas']
    assert [(l['classificacao_importacao'], l['duplicidade']) for l in r] == [('COMPRA', None), ('JA_EXISTENTE', 'lote')]
    importar(banco, a, {**b, 'manter_duplicada': True})
    assert len(sql(banco, "select id from public.lancamento_agregado where descricao = 'CAFE'")) == 2


# ---------------------------------------------------------------------------------------------------------------------
# 5. Duas cobrancas, ambiguidade, recorrencia inativada, fatura fechada e paga
# ---------------------------------------------------------------------------------------------------------------------

def test_duas_cobrancas_do_mesmo_servico_nao_somem(banco):
    ids = assinaturas(banco)
    a, b = linha(1, 'NETFLIX.COM', '59.90', categoria=None), linha(2, 'NETFLIX.COM', '15.90', data='2029-05-20', categoria=None)
    r = previa(banco, a, b)['linhas']
    assert [l['classificacao_importacao'] for l in r] == ['DESPESA_FIXA', 'REVISAR']
    assert 'Segunda cobranca de "Netflix"' in ' '.join(r[1]['mensagens'])
    importar(banco, a, {**b, 'recorrencia_escolhida_id': 0, 'categoria_id': ASSINATURAS})
    assert situacao(banco, ids['Netflix']) == 'CONFIRMADA'
    assert executado(banco) == D('75.80')  # as duas cobrancas reais
    # depois de cobrada, outra linha diferente da Netflix tambem pede revisao (nao e descartada)
    c = previa(banco, linha(3, 'NETFLIX.COM', '9.90', data='2029-05-25', categoria=None))['linhas'][0]
    assert (c['status'], c['ignorar']) == ('revisar', False)
    assert '"Netflix" ja tem cobranca nesta fatura' in ' '.join(c['mensagens'])


def test_ambiguidade_resolvida_pela_escolha(banco):
    duo = recorrencia(banco, 'Spotify Duo', '34.90')
    recorrencia(banco, 'Spotify', '40.90')
    gerar_mes(banco, MES)
    l = linha(1, 'SPOTIFY DUO SP', '31.00', categoria=None)
    assert previa(banco, l)['linhas'][0]['classificacao_importacao'] == 'REVISAR'
    r = previa(banco, {**l, 'recorrencia_escolhida_id': duo})['linhas'][0]
    assert (r['classificacao_importacao'], r['despesa_fixa']['nome'], r['apelido_sugerido']) == ('DESPESA_FIXA', 'Spotify Duo', None)
    assert importar(banco, {**l, 'recorrencia_escolhida_id': duo})['realizadas'] == 1


def test_recorrencia_inativada_reconhece_a_previsao_pendente(banco):
    ids = assinaturas(banco)
    versao = next(r['versao'] for r in tabela(banco, 'recorrencias_do_perfil', PESSOAL) if r['id'] == ids['Netflix'])
    rpc(banco, 'definir_situacao_recorrencia_cartao', PESSOAL, ids['Netflix'], versao, False)
    r = previa(banco, linha(1, 'NETFLIX.COM', '44.90', categoria=None))['linhas'][0]
    assert (r['classificacao_importacao'], r['despesa_fixa']['realiza_lancamento_id']) == \
        ('DESPESA_FIXA', ocorrencia(banco, ids['Netflix'])['id'])
    # sem previsao na competencia, a inativada nao reconhece mais
    julho = previa(banco, linha(1, 'NETFLIX.COM', '44.90', data='2029-07-12'), mes='2029-07-01')['linhas'][0]
    assert (julho['classificacao_importacao'], julho['recorrencia_id']) == ('COMPRA', None)


def test_fatura_fechada_e_paga_pedem_revisao(banco):
    assinaturas(banco)
    sql(banco, "update public.conta set status_fatura = 'FECHADA' where id = %s", (fatura(banco, CARTAO, MES)['id'],))
    r = previa(banco, linha(1, 'NETFLIX.COM', '44.90', categoria=None))['linhas'][0]
    assert (r['status'], r['ignorar']) == ('revisar', False) and 'fatura consolidada' in ' '.join(r['mensagens'])
    sql(banco, "update public.conta set status_fatura = 'ABERTA' where id = %s", (fatura(banco, CARTAO, MES)['id'],))
    pagar(banco, CARTAO, MES)  # paga antes da regra (historico): a previsao foi paga com a fatura
    r = previa(banco, linha(1, 'NETFLIX.COM', '44.90', categoria=None))['linhas'][0]
    assert (r['status'], r['ignorar']) == ('revisar', False) and 'fatura paga' in ' '.join(r['mensagens'])


# ---------------------------------------------------------------------------------------------------------------------
# 6. Parceladas e compras comuns na confirmacao
# ---------------------------------------------------------------------------------------------------------------------

def test_parcelada_nova_e_reimportada_sem_duplicar(banco):
    assinaturas(banco)
    nova = linha(1, 'TV LOJA', '100.00', parcela=(1, 3), gerar_parcelas_futuras=True)
    assert importar(banco, nova)['inseridos'] == 3
    r = previa(banco, linha(1, 'TV LOJA', '100.00', parcela=(1, 3)))['linhas'][0]
    assert r['classificacao_importacao'] == 'PARCELA_EXISTENTE'
    assert len(sql(banco, "select id from public.lancamento_agregado where descricao like 'TV LOJA%%'")) == 3


# ---------------------------------------------------------------------------------------------------------------------
# 7. Permissoes, seguranca e reversao da migration
# ---------------------------------------------------------------------------------------------------------------------

def test_sem_permissao_de_escrita_nada_e_gravado(banco):
    assinaturas(banco)
    antes = md5_compras(banco)
    l = linha(1, 'NETFLIX.COM', '44.90', categoria=None)
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, [l], str(uuid.uuid4()), usuario=USUARIO_B)[0] == '42501'
    assert falha(banco, 'analisar_importacao_cartao', PESSOAL, CARTAO, MES, [l], usuario=USUARIO_B)[0] == '42501'
    assert md5_compras(banco) == antes


@pytest.mark.parametrize('funcao', ['financeiro.conciliar_previsao_interna(integer, integer, integer)',
                                    'financeiro.registrar_apelido_recorrencia(integer, integer, text)'])
def test_funcoes_internas(banco, funcao):
    f = sql(banco, f"select prosecdef, proconfig, has_function_privilege('anon', '{funcao}', 'execute') anon, "
                   f"has_function_privilege('authenticated', '{funcao}', 'execute') autenticado "
                   f"from pg_proc where oid = '{funcao}'::regprocedure")[0]
    assert (f['prosecdef'], f['proconfig'], f['anon'], f['autenticado']) == (True, ['search_path=""'], False, False)


def executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_da_migration_e_reaplicacao(banco):
    assinaturas(banco)
    antes = md5_compras(banco)
    executar(banco, REVERSAO)
    r = previa(banco, linha(1, 'NETFLIX.COM', '44.90', categoria=None))['linhas'][0]
    assert 'classificacao_importacao' not in r and r['realiza_lancamento_id'] is not None
    executar(banco, MIGRATION)
    assert previa(banco, linha(1, 'NETFLIX.COM', '44.90', categoria=None))['linhas'][0]['classificacao_importacao'] == 'DESPESA_FIXA'
    assert md5_compras(banco) == antes
