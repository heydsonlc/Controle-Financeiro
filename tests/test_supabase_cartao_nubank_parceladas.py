"""
Testes FIN-CARTAO-NUBANK-PARCELADAS-01 (migration 20261211090000), em cluster local descartavel com o cenario FICTICIO do
FIN-RECORRENCIA-1 (Cartao Teste 910, Pessoal; Categoria do Cartao 961 com limite de R$ 500 para Assinaturas 952; Moradia
951 sem vinculo), em 05/2029. Linhas como o leitor do arquivo Nubank as envia ("Loja - Parcela 3/10" -> 3/10). Chamadas
como o navegador.
- parcela ja cadastrada (manual ou gerada por parcelamento) reconhecida mesmo com a data do ciclo (Nubank), sem duplicar;
- parcela nova sem vinculo anterior: Compra Parcelada (primeira, intermediaria, ultima), com numero, total, descricao,
  valor, data, cartao e competencia preservados;
- texto ambiguo: revisar, sem inventar parcela; a decisao do usuario (parcelada ou a vista) vale na confirmacao;
- Parcelada antes de Fixa; compra a vista e despesa fixa como antes; categoria pendente nao esconde a natureza;
- reimportacao integral e complementar, repetidas legitimas, fatura aberta e paga, limites por categoria e executado.
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
    md5_compras,
)
from tests.test_supabase_cartoes import ASSINATURAS, CARTAO, comprar, fatura, pagar, tabela
from tests.test_supabase_recorrencia import PG_BIN, cluster, sql  # noqa: F401
from tests.test_supabase_recorrencia_cartao import falha, rpc

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

SUPABASE = Path(__file__).resolve().parent.parent / 'supabase'
MIGRATION = SUPABASE / 'migrations' / '20261211090000_financeiro_cartao_nubank_parceladas.sql'
REVERSAO = SUPABASE / 'reversao' / '20261211090000_cartao_nubank_parceladas_anterior.sql'
JUNHO = '2029-06-01'


def D(valor):
    return Decimal(str(valor)).quantize(Decimal('0.01'))


def linha(n, descricao, valor, data='2029-05-12', categoria=ASSINATURAS, parcela=(1, 1), **extra):
    normal = ' '.join(''.join(c if c.isalnum() else ' ' for c in descricao.lower()).split())
    return {'linha_id': f'csv-{n}', 'linha_origem': n, 'data_compra': data, 'descricao_original': descricao,
            'descricao_normalizada': descricao, 'descricao_exibida': descricao, 'descricao_classificacao': normal,
            'valor': valor, 'parcela_atual': parcela[0], 'total_parcelas': parcela[1], 'tipo_movimento': 'debito',
            **({'categoria_id': categoria} if categoria else {}), **extra}


def previa(dsn, *linhas, mes=MES):
    return rpc(dsn, 'analisar_importacao_cartao', PESSOAL, CARTAO, mes, list(linhas))


def classes(dsn, *linhas, mes=MES):
    return [l['classificacao_importacao'] for l in previa(dsn, *linhas, mes=mes)['linhas']]


def importar(dsn, *linhas, mes=MES, chave=None):
    return rpc(dsn, 'importar_fatura_cartao', PESSOAL, CARTAO, mes, list(linhas), chave or str(uuid.uuid4()))


def gravadas(dsn, descricao):
    return sql(dsn, "select descricao, descricao_original, valor, data_compra::text dt, mes_fatura::text mf, "
                    "mes_fatura_original::text mfo, numero_parcela, total_parcelas, cartao_id, is_importado "
                    "from public.lancamento_agregado where descricao = %s order by numero_parcela, id", (descricao,))


def natureza(dsn, descricao, mes=MES):
    return [c['natureza'] for c in tabela(dsn, 'compras_da_fatura', PESSOAL, CARTAO, mes) if c['descricao'] == descricao]


def executado(dsn, mes=MES):
    f = fatura(dsn, CARTAO, mes)
    return D(next(x for x in tabela(dsn, 'contas_do_mes', PESSOAL, mes) if x['id'] == f['id'])['valor_executado'])


def md5(dsn, tabela_):
    return sql(dsn, f"select coalesce(md5(string_agg(t::text, '|' order by t.id)), '') h from {tabela_} t")[0]['h']


# ---------------------------------------------------------------------------------------------------------------------
# 1. Parcela ja cadastrada
# ---------------------------------------------------------------------------------------------------------------------

def test_parcela_ja_cadastrada_e_reconhecida_mesmo_com_a_data_do_ciclo(banco):
    """Compra manual 3x de R$ 100 (10/05, 10/06, 10/07). O Nubank data a 2/3 pelo inicio do ciclo (28/05): 13 dias."""
    comprar(banco, descricao='Notebook', valor='300.00', total_parcelas=3)
    antes = md5_compras(banco)
    r = previa(banco, linha(1, 'NOTEBOOK LOJA', '100.00', data='2029-05-28', parcela=(2, 3)), mes=JUNHO)['linhas'][0]
    assert (r['classificacao_importacao'], r['status'], r['ignorar']) == ('PARCELA_EXISTENTE', 'conciliado', True)
    assert r['conciliacao']['descricao'] == 'Notebook'
    assert md5_compras(banco) == antes
    # outra parcela N/M (ou outro valor) nao e a mesma compra
    assert classes(banco, linha(1, 'NOTEBOOK LOJA', '100.00', data='2029-05-28', parcela=(3, 3)),
                   linha(2, 'NOTEBOOK LOJA', '99.00', data='2029-05-28', parcela=(2, 3)), mes=JUNHO) == ['PARCELADA', 'PARCELADA']


def test_parcela_gerada_pelo_parcelamento_reconhecida_no_mes_seguinte(banco):
    """1/3 importada gerando as futuras (12/06, 12/07): o arquivo de junho traz a 2/3 datada pelo ciclo (29/05)."""
    assert importar(banco, linha(1, 'TV LOJA', '100.00', parcela=(1, 3), gerar_parcelas_futuras=True))['inseridos'] == 3
    antes = md5_compras(banco)
    junho = [linha(1, 'TV LOJA', '100.00', data='2029-05-29', parcela=(2, 3)), linha(2, 'PADARIA', '8.00', data='2029-06-02')]
    assert classes(banco, *junho, mes=JUNHO) == ['PARCELA_EXISTENTE', 'COMPRA']
    assert importar(banco, *junho, mes=JUNHO)['inseridos'] == 1  # so a padaria
    assert [(g['numero_parcela'], g['mf']) for g in gravadas(banco, 'TV LOJA')] == \
        [(1, '2029-05-01'), (2, '2029-06-01'), (3, '2029-07-01')]
    assert md5_compras(banco) != antes and len(gravadas(banco, 'PADARIA')) == 1


def test_entre_duas_parcelas_iguais_fica_a_de_mesma_descricao(banco):
    comprar(banco, descricao='Bicicleta', valor='200.00', total_parcelas=2)
    comprar(banco, descricao='Tenis', valor='200.00', total_parcelas=2)
    r = previa(banco, linha(1, 'Tenis', '100.00', data='2029-05-30', parcela=(2, 2)), mes=JUNHO)['linhas'][0]
    assert (r['classificacao_importacao'], r['conciliacao']['descricao']) == ('PARCELA_EXISTENTE', 'Tenis')


# ---------------------------------------------------------------------------------------------------------------------
# 2. Parcela nova, sem vinculo anterior
# ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('parcela', [(1, 2), (5, 6), (3, 3)], ids=['primeira', 'intermediaria', 'ultima'])
def test_parcela_nova_e_compra_parcelada_com_os_dados_preservados(banco, parcela):
    r = previa(banco, linha(1, 'HAIKAR VEICULOS', '416.81', data='2029-04-28', parcela=parcela))['linhas'][0]
    assert (r['classificacao_importacao'], r['status'], r['parcela'], r['categoria_pendente']) == \
        ('PARCELADA', 'valido', f'{parcela[0]}/{parcela[1]}', False)
    assert r['status_classificacao'] == 'classificada'
    assert importar(banco, linha(1, 'HAIKAR VEICULOS', '416.81', data='2029-04-28', parcela=parcela))['inseridos'] == 1
    assert gravadas(banco, 'HAIKAR VEICULOS') == [{
        'descricao': 'HAIKAR VEICULOS', 'descricao_original': 'HAIKAR VEICULOS', 'valor': D('416.81'), 'dt': '2029-04-28',
        'mf': MES, 'mfo': None, 'numero_parcela': parcela[0], 'total_parcelas': parcela[1], 'cartao_id': CARTAO,
        'is_importado': True}]
    assert natureza(banco, 'HAIKAR VEICULOS') == ['PARCELADA']


def test_categoria_pendente_nao_esconde_a_natureza(banco):
    sql(banco, 'update public.item_despesa set categoria_id = null where id = %s', (CARTAO,))  # sem fallback (como o Black)
    r = previa(banco, linha(1, 'ANACAPRI GOIANIA', '83.30', parcela=(3, 3), categoria=None),
               linha(2, 'PADARIA', '8.00', categoria=None))['linhas']
    assert [(l['classificacao_importacao'], l['status'], l['categoria_pendente']) for l in r] == \
        [('PARCELADA', 'revisar', True), ('COMPRA', 'revisar', True)]
    antes = md5_compras(banco)
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, [linha(1, 'ANACAPRI GOIANIA', '83.30', parcela=(3, 3),
                 categoria=None)], str(uuid.uuid4()))[0] == '22023'
    assert md5_compras(banco) == antes


# ---------------------------------------------------------------------------------------------------------------------
# 3. Texto ambiguo: revisar, sem inventar parcela; a decisao do usuario
# ---------------------------------------------------------------------------------------------------------------------

def test_numero_ambiguo_pede_revisao_e_vale_a_decisao(banco):
    amb = {'parcela_ambigua': {'parcela_atual': 3, 'total_parcelas': 10}}
    r = previa(banco, linha(1, 'MERCADO XYZ', '50.00', **amb))['linhas'][0]
    assert (r['classificacao_importacao'], r['status'], r['parcela'], r['parcela_ambigua']['rotulo'], r['natureza_parcela']) == \
        ('REVISAR', 'revisar', '1/1', '03/10', None)
    assert any('Possivel parcela 03/10' in m for m in r['mensagens'])
    assert previa(banco, linha(1, 'MERCADO XYZ', '50.00', **amb))['validacoes']['parcelas_ambiguas'] == 1
    antes = md5_compras(banco)
    erro = falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, [linha(1, 'MERCADO XYZ', '50.00', **amb)], str(uuid.uuid4()))
    assert erro[0] == '22023' and 'Possivel parcela' in erro[1]
    assert md5_compras(banco) == antes
    parcelada, avista = previa(banco, linha(1, 'MERCADO XYZ', '50.00', natureza_parcela='PARCELADA', **amb),
                               linha(2, 'LOJA 15/11', '20.00', natureza_parcela='avista',
                                     parcela_ambigua={'parcela_atual': 15, 'total_parcelas': 11}),
                               linha(3, 'SHOW 05/12', '30.00', natureza_parcela='AVISTA',
                                     parcela_ambigua={'parcela_atual': 5, 'total_parcelas': 12}))['linhas'][::2]
    assert (parcelada['classificacao_importacao'], parcelada['parcela']) == ('PARCELADA', '3/10')
    assert (avista['classificacao_importacao'], avista['parcela'], avista['natureza_parcela']) == ('COMPRA', '1/1', 'AVISTA')
    # numero impossivel (15/11) nao e parcela: nem revisao
    assert previa(banco, linha(1, 'LOJA 15/11', '20.00', parcela_ambigua={'parcela_atual': 15, 'total_parcelas': 11}))['linhas'][0][
        'classificacao_importacao'] == 'COMPRA'


def test_decisao_gravada_e_reconhecida_na_reimportacao(banco):
    amb = {'parcela_ambigua': {'parcela_atual': 3, 'total_parcelas': 10}}
    assert importar(banco, linha(1, 'MERCADO XYZ', '50.00', natureza_parcela='PARCELADA', **amb),
                    linha(2, 'SHOW', '30.00', natureza_parcela='AVISTA', parcela_ambigua={'parcela_atual': 5, 'total_parcelas': 12})
                    )['inseridos'] == 2
    assert [(g['numero_parcela'], g['total_parcelas']) for g in gravadas(banco, 'MERCADO XYZ')] == [(3, 10)]
    assert [(g['numero_parcela'], g['total_parcelas']) for g in gravadas(banco, 'SHOW')] == [(1, 1)]
    # o mesmo arquivo de novo, sem decidir: as duas ja existem (nada a revisar, nada a gravar)
    r = previa(banco, linha(1, 'MERCADO XYZ', '50.00', **amb),
               linha(2, 'SHOW', '30.00', parcela_ambigua={'parcela_atual': 5, 'total_parcelas': 12}))['linhas']
    assert [(l['classificacao_importacao'], l['parcela']) for l in r] == [('PARCELA_EXISTENTE', '3/10'), ('JA_EXISTENTE', '1/1')]


# ---------------------------------------------------------------------------------------------------------------------
# 4. Compra a vista, despesa fixa e a precedencia Parcelada -> Fixa
# ---------------------------------------------------------------------------------------------------------------------

def test_a_vista_e_despesa_fixa_como_antes_e_parcela_antes_de_fixa(banco):
    ids = assinaturas(banco)
    r = previa(banco, linha(1, 'NETFLIX.COM', '44.90', categoria=None), linha(2, 'PADARIA', '8.00'),
               linha(3, 'NETFLIX.COM', '30.00', parcela=(2, 3)),
               linha(4, 'APPLE COMBO', '20.00', parcela=(1, 2), recorrencia_escolhida_id=ids['Apple One']))['linhas']
    assert [l['classificacao_importacao'] for l in r] == ['DESPESA_FIXA', 'COMPRA', 'PARCELADA', 'REVISAR']
    assert (r[2]['recorrencia_id'], r[2]['realiza_lancamento_id']) == (None, None)
    assert any('nao e despesa fixa' in m for m in r[3]['mensagens'])


# ---------------------------------------------------------------------------------------------------------------------
# 5. Reimportacao integral e complementar; repetidas legitimas
# ---------------------------------------------------------------------------------------------------------------------

ARQUIVO = [linha(1, 'SHOPEE CLASSIC', '79.70', data='2029-05-28', parcela=(1, 2)),
           linha(2, 'DETROIT T9', '314.07', data='2029-04-28', parcela=(2, 4)),
           linha(3, 'FARMACIAS PA', '43.29', data='2029-05-06', parcela=(1, 2)),
           linha(4, 'FARMACIAS PA', '80.31', data='2029-05-06', parcela=(1, 2)),
           linha(5, 'PADARIA', '8.00')]


def test_reimportacao_integral_e_complementar_sem_duplicar(banco):
    assert importar(banco, ARQUIVO[4])['inseridos'] == 1                      # complementar: primeiro so a compra
    assert classes(banco, *ARQUIVO) == ['PARCELADA', 'PARCELADA', 'PARCELADA', 'PARCELADA', 'JA_EXISTENTE']
    assert importar(banco, *ARQUIVO)['inseridos'] == 4                        # depois o arquivo inteiro: so as parcelas
    antes = md5_compras(banco)
    assert classes(banco, *ARQUIVO) == ['PARCELA_EXISTENTE'] * 4 + ['JA_EXISTENTE']
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, ARQUIVO, str(uuid.uuid4()))[1] == 'Nenhuma linha para importar'
    assert md5_compras(banco) == antes
    assert sorted((g['valor'], g['numero_parcela']) for g in gravadas(banco, 'FARMACIAS PA')) == [(D('43.29'), 1), (D('80.31'), 1)]


def test_parcelas_repetidas_legitimas_no_arquivo(banco):
    igual = linha(1, 'FARMACIAS PA', '43.29', data='2029-05-06', parcela=(1, 2))
    r = previa(banco, igual, {**igual, 'linha_id': 'csv-2', 'linha_origem': 2})['linhas']
    assert [(l['classificacao_importacao'], l['duplicidade']) for l in r] == [('PARCELADA', None), ('PARCELA_EXISTENTE', 'lote')]
    assert importar(banco, igual, {**igual, 'linha_id': 'csv-2', 'linha_origem': 2, 'manter_duplicada': True})['inseridos'] == 2
    assert len(gravadas(banco, 'FARMACIAS PA')) == 2


# ---------------------------------------------------------------------------------------------------------------------
# 6. Fatura aberta e paga; limites; executado; movimentos
# ---------------------------------------------------------------------------------------------------------------------

def test_fatura_paga_preservada_e_parcela_na_proxima_aberta(banco):
    comprar(banco, descricao='Revista', valor='40.00', total_parcelas=1)
    pagar(banco, CARTAO, MES)
    fatura_paga = lambda: sql(banco, "select md5(t::text) h from public.conta t where is_fatura_cartao "  # noqa: E731
                                     "and item_despesa_id = %s and cartao_competencia = %s", (CARTAO, MES))[0]['h']
    paga, total_paga = fatura_paga(), executado(banco)
    movimentos = md5(banco, 'public.movimento_financeiro')
    assert importar(banco, linha(1, 'DETROIT T9', '314.07', data='2029-04-28', parcela=(2, 4)))['inseridos'] == 1
    assert [(g['mf'], g['mfo']) for g in gravadas(banco, 'DETROIT T9')] == [(JUNHO, MES)]
    assert (fatura_paga(), executado(banco)) == (paga, total_paga)
    assert md5(banco, 'public.movimento_financeiro') == movimentos
    # reimportar a fatura paga: a parcela ja existe (pela competencia original), nada novo
    assert classes(banco, linha(1, 'DETROIT T9', '314.07', data='2029-04-28', parcela=(2, 4))) == ['PARCELA_EXISTENTE']


def test_parcela_entra_no_executado_e_nao_consome_limite_da_categoria(banco):
    """Assinaturas (952) -> Categoria do Cartao 961 com limite de R$ 500: a parcela de R$ 400 fica no grupo proprio."""
    movimentos = md5(banco, 'public.movimento_financeiro')
    importar(banco, linha(1, 'CURSO ONLINE', '400.00', parcela=(2, 5)), linha(2, 'STREAMING AVULSO', '30.00'))
    r = rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, MES)
    cat = next(g for g in r['categorias'] if g['categoria_cartao_id'] == 961)
    parceladas = next(g for g in r['categorias'] if g.get('natureza') == 'PARCELADA')
    assert (D(cat['gasto_atual']), D(parceladas['gasto_atual'])) == (D('30.00'), D('400.00'))
    assert D(r['total_compras_parceladas']) == D('400.00')
    assert D(r['total_fatura']) == D('430.00') == executado(banco)
    assert natureza(banco, 'CURSO ONLINE') == ['PARCELADA'] and natureza(banco, 'STREAMING AVULSO') == ['CATEGORIA']
    assert md5(banco, 'public.movimento_financeiro') == movimentos


# ---------------------------------------------------------------------------------------------------------------------
# 7. Reversao da migration
# ---------------------------------------------------------------------------------------------------------------------

def executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_da_migration_e_reaplicacao(banco):
    comprar(banco, descricao='Notebook', valor='300.00', total_parcelas=3)
    antes = md5_compras(banco)
    l = linha(1, 'NOTEBOOK LOJA', '100.00', data='2029-05-28', parcela=(2, 3))
    executar(banco, REVERSAO)
    r = previa(banco, l, mes=JUNHO)['linhas'][0]
    assert r['classificacao_importacao'] == 'PARCELADA' and 'parcela_ambigua' not in r  # a regra de 5 dias de antes
    executar(banco, MIGRATION)
    assert previa(banco, l, mes=JUNHO)['linhas'][0]['classificacao_importacao'] == 'PARCELA_EXISTENTE'
    assert md5_compras(banco) == antes
