"""
Testes FIN-CARTAO-NUBANK-CREDITOS-01 (migration 20261212090000), em cluster local descartavel com o cenario FICTICIO do
FIN-RECORRENCIA-1 (Cartao Teste 910, Pessoal; Categoria do Cartao 961 com limite de R$ 500 para Assinaturas 952), em
05/2029. Creditos como o leitor do arquivo Nubank os envia (valor negativo -> credito). Chamadas como o navegador.
- previa: estorno (parcial e integral), IOF devolvido e ajuste, com a compra original quando identificada sem duvida;
  mais de uma candidata pede a escolha; pagamento recebido continua fora (nao e credito da fatura);
- confirmacao: o credito abate o valor a pagar uma vez (Despesas, faturas do mes, Cartoes, Dashboard, pagamento), sem
  movimento bancario; compra original preservada e bloqueada; reimportacao integral e complementar; confirmacoes
  simultaneas; falha transacional; fatura fechada e paga; estorno do pagamento; permissoes; reversao da migration.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartao_despesas_fixas import MES, PESSOAL, banco, md5_compras  # noqa: F401
from tests.test_supabase_cartao_previsto_executado import estornar_pelo_app, pagar_pelo_app
from tests.test_supabase_cartoes import ASSINATURAS, CARTAO, comprar, fatura, pagar, tabela
from tests.test_supabase_despesas import _paralelo
from tests.test_supabase_recorrencia import PG_BIN, USUARIO_B, cluster, sql  # noqa: F401
from tests.test_supabase_recorrencia_cartao import falha, rpc

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

SUPABASE = Path(__file__).resolve().parent.parent / 'supabase'
MIGRATION = SUPABASE / 'migrations' / '20261212090000_financeiro_cartao_nubank_creditos.sql'
REVERSAO = SUPABASE / 'reversao' / '20261212090000_cartao_nubank_creditos_anterior.sql'
JUNHO = '2029-06-01'


def D(valor):
    return Decimal(str(valor)).quantize(Decimal('0.01'))


def linha(n, descricao, valor, data='2029-05-26', categoria=ASSINATURAS, **extra):
    normal = ' '.join(''.join(c if c.isalnum() else ' ' for c in descricao.lower()).split())
    credito = str(valor).startswith('-')
    return {'linha_id': f'csv-{n}', 'linha_origem': n, 'data_compra': data, 'descricao_original': descricao,
            'descricao_normalizada': descricao, 'descricao_exibida': descricao, 'descricao_classificacao': normal,
            'valor': str(valor).lstrip('-'), 'parcela_atual': 1, 'total_parcelas': 1,
            'tipo_movimento': 'credito' if credito else 'debito',
            **({'categoria_id': categoria} if categoria and not credito else {}), **extra}


IOF_VOLTA = linha(1, 'IOF de volta de Cloudflare', '-0.99')
ESTORNO_APPLE = linha(2, 'Estorno de "Apple.Com/Bill" (Apple)', '-50.22')
PAGAMENTO = linha(3, 'Pagamento recebido', '-12099.02', data='2029-04-30')


def previa(dsn, *linhas, mes=MES):
    return rpc(dsn, 'analisar_importacao_cartao', PESSOAL, CARTAO, mes, list(linhas))


def importar(dsn, *linhas, mes=MES, chave=None, usuario=None):
    return rpc(dsn, 'importar_fatura_cartao', PESSOAL, CARTAO, mes, list(linhas), chave or str(uuid.uuid4()),
               **({'usuario': usuario} if usuario else {}))


def creditos(dsn):
    return sql(dsn, 'select natureza, descricao, valor, lancamento_id, mes_fatura::text mf, mes_fatura_original::text mfo, '
                    'fatura_id from financeiro.credito_fatura order by id')


def compra(dsn, descricao, valor, data='2029-05-26'):
    comprar(dsn, descricao=descricao, valor=valor, total_parcelas=1, data_compra=data)
    return sql(dsn, 'select max(id) i from public.lancamento_agregado where descricao = %s', (descricao,))[0]['i']


def cenario(dsn):
    """Cloudflare R$ 28,47 + IOF R$ 0,99; Apple R$ 799,90 (a do estorno parcial)."""
    return {'cloudflare': compra(dsn, 'Cloudflare', '28.47'), 'iof': compra(dsn, 'IOF de "Cloudflare"', '0.99'),
            'apple': compra(dsn, 'Apple.Com/Bill', '799.90')}


def a_pagar(dsn, mes=MES):
    """Valor a pagar da fatura em cada leitura: pagamento, Despesas, faturas do mes, Cartoes."""
    f = fatura(dsn, CARTAO, mes)
    lista = next(x for x in tabela(dsn, 'contas_do_mes', PESSOAL, mes) if x['id'] == f['id'])
    mes_ = next(x for x in tabela(dsn, 'faturas_do_mes', PESSOAL, mes) if x['cartao_id'] == CARTAO)
    cartoes = rpc(dsn, 'fatura_por_categoria', PESSOAL, CARTAO, mes)
    executado = sql(dsn, 'select financeiro.executado_fatura(%s) v', (f['id'],))[0]['v']
    valores = {D(executado), D(lista['valor_executado']), D(mes_['valor_executado']), D(cartoes['total_fatura']),
               D(sql(dsn, 'select valor_executado v from public.conta where id = %s', (f['id'],))[0]['v'])}
    assert len(valores) == 1, valores
    return valores.pop()


def md5(dsn, tabela_):
    return sql(dsn, f"select coalesce(md5(string_agg(t::text, '|' order by t.id)), '') h from {tabela_} t")[0]['h']


# ---------------------------------------------------------------------------------------------------------------------
# 1. Previa: natureza, compra original e tratamento; nada gravado; pagamento recebido fora
# ---------------------------------------------------------------------------------------------------------------------

def test_previa_classifica_os_creditos_sem_gravar(banco):
    ids = cenario(banco)
    antes = md5_compras(banco)
    r = previa(banco, IOF_VOLTA, ESTORNO_APPLE, PAGAMENTO, linha(4, 'Credito de ajuste', '-3.00'))
    iof, estorno, pagamento, ajuste = r['linhas']
    assert md5_compras(banco) == antes and creditos(banco) == []
    assert [(l['classificacao_importacao'], l['status'], l['ignorar']) for l in (iof, estorno, pagamento, ajuste)] == [
        ('CREDITO', 'valido', False), ('CREDITO', 'valido', False), ('IGNORADA', 'ignorado', True), ('CREDITO', 'valido', False)]
    assert (iof['credito']['natureza'], iof['credito']['compra']['id']) == ('IOF_DEVOLVIDO', ids['iof'])
    assert (estorno['credito']['natureza'], estorno['credito']['compra']['id'], estorno['credito']['parcial']) == \
        ('ESTORNO', ids['apple'], True)
    assert (ajuste['credito']['natureza'], ajuste['credito']['compra']) == ('AJUSTE', None)
    assert any('abate R$ 50.22 do valor a pagar da fatura 05/2029' in m for m in estorno['mensagens'])
    assert any('Pagamento da fatura' in m for m in pagamento['mensagens'])
    v = r['validacoes']
    assert (v['creditos_a_abater'], D(v['total_creditos_a_abater'])) == (3, D('54.21'))


# ---------------------------------------------------------------------------------------------------------------------
# 2. Confirmacao: abate o valor a pagar uma vez, em todas as leituras; compra original preservada; nenhum movimento
# ---------------------------------------------------------------------------------------------------------------------

def test_credito_novo_abate_o_valor_a_pagar_uma_vez(banco):
    ids = cenario(banco)
    bruto = a_pagar(banco)
    movimentos, contas = md5(banco, 'public.movimento_financeiro'), md5(banco, 'public.conta_bancaria')
    res = importar(banco, IOF_VOLTA, ESTORNO_APPLE, PAGAMENTO)
    assert (res['creditos'], D(res['total_creditos']), res['inseridos']) == (2, D('51.21'), 0)
    assert [(c['natureza'], c['valor'], c['lancamento_id'], c['mf']) for c in creditos(banco)] == [
        ('IOF_DEVOLVIDO', D('0.99'), ids['iof'], MES), ('ESTORNO', D('50.22'), ids['apple'], MES)]
    assert a_pagar(banco) == bruto - D('51.21')
    r = rpc(banco, 'fatura_por_categoria', PESSOAL, CARTAO, MES)
    assert (D(r['total_compras']), D(r['total_creditos'])) == (bruto, D('51.21'))
    grupo = next(g for g in r['categorias'] if g['tipo_grupo'] == 'creditos')
    assert (grupo['categoria_cartao_id'], D(grupo['gasto_atual']), grupo['quantidade_lancamentos'], grupo['status']) == \
        ('creditos', D('-51.21'), 2, 'Abatido')
    # o limite da Categoria do Cartao nao muda (o credito nao e compra negativa)
    cat = next(g for g in r['categorias'] if g['categoria_cartao_id'] == 961)
    assert D(cat['gasto_atual']) == bruto
    # compras originais intactas; nenhum movimento ou saldo bancario
    assert sql(banco, 'select valor from public.lancamento_agregado where id = %s', (ids['apple'],))[0]['valor'] == D('799.90')
    assert (md5(banco, 'public.movimento_financeiro'), md5(banco, 'public.conta_bancaria')) == (movimentos, contas)


def test_lista_da_fatura_mostra_o_credito_sem_acoes_de_compra(banco):
    ids = cenario(banco)
    importar(banco, ESTORNO_APPLE)
    todos = rpc(banco, 'lancamentos_fatura_por_categoria', PESSOAL, CARTAO, MES, 'todos')['lancamentos']
    so = rpc(banco, 'lancamentos_fatura_por_categoria', PESSOAL, CARTAO, MES, 'creditos')['lancamentos']
    credito = next(l for l in todos if l['natureza'] == 'CREDITO')
    assert so == [credito]
    assert (str(credito['id']).startswith('credito-'), D(credito['valor']), credito['pode_editar'], credito['categoria_nome'],
            credito['compra_original']['id']) == (True, D('-50.22'), False, 'Estorno de compra', ids['apple'])
    assert len([l for l in todos if l['natureza'] != 'CREDITO']) == 3


def test_dashboard_e_pagamento_usam_o_valor_liquido_e_o_estorno_do_pagamento_o_preserva(banco):
    cenario(banco)
    importar(banco, ESTORNO_APPLE)
    liquido = a_pagar(banco)
    painel = rpc(banco, 'dashboard_resumo_tela', PESSOAL, '2029-05')
    encontrados = []

    def procurar(no):
        if isinstance(no, dict):
            if 'faturas_em_aberto' in no:
                encontrados.append(no['faturas_em_aberto'])
            for v in no.values():
                procurar(v)
        elif isinstance(no, list):
            for v in no:
                procurar(v)
    procurar(painel)
    assert D(encontrados[0]['valor']) == liquido
    pago = pagar_pelo_app(banco)
    assert D(pago['valor_pago']) == liquido
    assert sql(banco, "select count(*) n from public.movimento_financeiro where id = %s and valor = %s",
               (pago['movimento_id'], liquido))[0]['n'] == 1
    estornar_pelo_app(banco, pago['movimento_id'])
    assert a_pagar(banco) == liquido and len(creditos(banco)) == 1


# ---------------------------------------------------------------------------------------------------------------------
# 3. Estorno parcial e integral; IOF; sem compra; mais de uma candidata
# ---------------------------------------------------------------------------------------------------------------------

def test_estorno_integral_e_o_valor_estornavel(banco):
    apple = compra(banco, 'Apple.Com/Bill', '64.90')
    integral = linha(1, 'Estorno de "Apple.Com/Bill" (Apple)', '-64.90')
    r = previa(banco, integral)['linhas'][0]
    assert (r['credito']['compra']['id'], r['credito']['parcial']) == (apple, False)
    importar(banco, integral)
    # ja estornada por inteiro: um segundo estorno nao a encontra (sem compra vinculada; nada abatido duas vezes da compra)
    outro = previa(banco, linha(2, 'Estorno de "Apple.Com/Bill" (Apple)', '-10.00', data='2029-05-27'))['linhas'][0]
    assert (outro['classificacao_importacao'], outro['credito']['compra'], outro['credito']['candidatas']) == ('CREDITO', None, [])


def test_iof_devolvido_pelo_valor_e_pelo_nome(banco):
    """Duas cobrancas de IOF da mesma loja: o valor identifica; o IOF devolvido de outra loja nao a pega."""
    a = compra(banco, 'IOF de "Dramawave"', '0.73', data='2029-05-18')
    b = compra(banco, 'IOF de "Dramawave"', '1.46', data='2029-05-24')
    r = previa(banco, linha(1, 'IOF de volta de Dramawave', '-1.46', data='2029-05-24'),
               linha(2, 'IOF de volta de Dramawave', '-0.73', data='2029-05-18'),
               linha(3, 'IOF de volta de Cloudflare', '-0.73'))['linhas']
    assert [(l['credito']['natureza'], (l['credito']['compra'] or {}).get('id')) for l in r] == \
        [('IOF_DEVOLVIDO', b), ('IOF_DEVOLVIDO', a), ('IOF_DEVOLVIDO', None)]


def test_estorno_sem_compra_correspondente(banco):
    r = previa(banco, linha(1, 'Estorno de "Loja Fantasma"', '-20.00'))['linhas'][0]
    assert (r['classificacao_importacao'], r['credito']['natureza'], r['credito']['compra']) == ('CREDITO', 'ESTORNO', None)
    assert any('sem compra vinculada' in m for m in r['mensagens'])
    importar(banco, linha(1, 'Estorno de "Loja Fantasma"', '-20.00'))
    assert [(c['natureza'], c['lancamento_id']) for c in creditos(banco)] == [('ESTORNO', None)]


def test_mais_de_uma_compra_candidata_pede_a_escolha(banco):
    c1, c2 = compra(banco, 'Apple.Com/Bill', '99.90', data='2029-05-06'), compra(banco, 'Apple.Com/Bill', '129.90', data='2029-05-06')
    r = previa(banco, ESTORNO_APPLE)['linhas'][0]
    assert (r['classificacao_importacao'], r['status']) == ('REVISAR', 'revisar')
    assert sorted(c['id'] for c in r['credito']['candidatas']) == sorted([c1, c2])
    assert r['status_classificacao'] == 'revisar' and 'podem ser a original' in r['mensagens'][-1]
    antes = md5_compras(banco)
    erro = falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, [ESTORNO_APPLE], str(uuid.uuid4()))
    assert erro[0] == '22023' and 'podem ser a original' in erro[1]  # o motivo, nunca "pronta para importacao"
    assert creditos(banco) == [] and md5_compras(banco) == antes
    assert previa(banco, {**ESTORNO_APPLE, 'credito_compra_id': 999999})['linhas'][0]['classificacao_importacao'] == 'REVISAR'
    escolhida = previa(banco, {**ESTORNO_APPLE, 'credito_compra_id': c2})['linhas'][0]
    assert (escolhida['classificacao_importacao'], escolhida['credito']['compra']['id'], escolhida['credito']['escolhida']) == \
        ('CREDITO', c2, True)
    sem = previa(banco, {**ESTORNO_APPLE, 'credito_compra_id': 0})['linhas'][0]
    assert (sem['classificacao_importacao'], sem['credito']['compra']) == ('CREDITO', None)
    importar(banco, {**ESTORNO_APPLE, 'credito_compra_id': c2})
    assert [c['lancamento_id'] for c in creditos(banco)] == [c2]


# ---------------------------------------------------------------------------------------------------------------------
# 4. Reimportacao, complementar, simultaneas, falha transacional, fatura fechada e paga
# ---------------------------------------------------------------------------------------------------------------------

def test_credito_ja_importado_e_reimportacao_integral(banco):
    cenario(banco)
    arquivo = [linha(10, 'Padaria', '8.00'), IOF_VOLTA, ESTORNO_APPLE, PAGAMENTO]
    assert (importar(banco, *arquivo)['inseridos'], len(creditos(banco))) == (1, 2)
    antes = (md5_compras(banco), md5(banco, 'financeiro.credito_fatura'), a_pagar(banco))
    r = previa(banco, *arquivo)['linhas']
    assert [l['classificacao_importacao'] for l in r] == ['JA_EXISTENTE', 'JA_EXISTENTE', 'JA_EXISTENTE', 'IGNORADA']
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, arquivo, str(uuid.uuid4()))[1] == 'Nenhuma linha para importar'
    assert (md5_compras(banco), md5(banco, 'financeiro.credito_fatura'), a_pagar(banco)) == antes


def test_importacao_complementar_so_os_creditos(banco):
    cenario(banco)
    importar(banco, linha(10, 'Padaria', '8.00'))
    res = importar(banco, linha(10, 'Padaria', '8.00'), IOF_VOLTA, ESTORNO_APPLE)
    assert (res['inseridos'], res['creditos'], res['duplicados']) == (0, 2, 1)


def test_creditos_repetidos_legitimos_no_arquivo(banco):
    igual = linha(1, 'Credito de ajuste', '-3.00')
    r = previa(banco, igual, {**igual, 'linha_id': 'csv-2', 'linha_origem': 2})['linhas']
    assert [(l['classificacao_importacao'], l['duplicidade']) for l in r] == [('CREDITO', None), ('JA_EXISTENTE', 'lote')]
    importar(banco, igual, {**igual, 'linha_id': 'csv-2', 'linha_origem': 2, 'manter_duplicada': True})
    assert len(creditos(banco)) == 2


def test_duas_confirmacoes_simultaneas_gravam_o_credito_uma_vez(banco):
    cenario(banco)
    resultados = _paralelo([lambda: importar(banco, ESTORNO_APPLE) for _ in range(2)])
    assert sorted(r[0] for r in resultados) == ['erro', 'ok']
    assert 'Nenhuma linha para importar' in str(next(r[1] for r in resultados if r[0] == 'erro'))
    assert len(creditos(banco)) == 1


def test_falha_transacional_nada_gravado(banco):
    """A compra valida e o credito: a fatura consolidada recusa o credito; nada fica (nem a compra)."""
    cenario(banco)
    sql(banco, "update public.conta set status_fatura = 'FECHADA' where is_fatura_cartao and item_despesa_id = %s "
               "and cartao_competencia = %s", (CARTAO, MES))
    antes = md5_compras(banco)
    erro = falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, [linha(10, 'Padaria', '8.00'), ESTORNO_APPLE],
                 str(uuid.uuid4()))
    assert erro[0] == 'P0001' and 'consolidada' in erro[1]
    assert (md5_compras(banco), creditos(banco)) == (antes, [])


def test_fatura_paga_preservada_e_credito_na_proxima_aberta(banco):
    ids = cenario(banco)
    pagar(banco, CARTAO, MES)
    fatura_paga = lambda: sql(banco, 'select md5(t::text) h from public.conta t where id = %s',  # noqa: E731
                              (fatura(banco, CARTAO, MES)['id'],))[0]['h']
    paga = fatura_paga()
    importar(banco, ESTORNO_APPLE)
    assert [(c['mf'], c['mfo'], c['lancamento_id']) for c in creditos(banco)] == [(JUNHO, MES, ids['apple'])]
    assert fatura_paga() == paga
    assert a_pagar(banco, JUNHO) == D('-50.22')  # a proxima fatura: so o credito (nenhuma compra)
    # reimportar a fatura paga: o credito ja existe (pela competencia original)
    assert previa(banco, ESTORNO_APPLE)['linhas'][0]['classificacao_importacao'] == 'JA_EXISTENTE'


# ---------------------------------------------------------------------------------------------------------------------
# 5. Compra original bloqueada; permissoes; reversao da migration
# ---------------------------------------------------------------------------------------------------------------------

def test_compra_original_do_credito_nao_e_editada_nem_excluida(banco):
    ids = cenario(banco)
    importar(banco, ESTORNO_APPLE)
    assert sql(banco, 'select financeiro.bloqueio_da_parcela(%s) b', (ids['apple'],))[0]['b'].startswith('Compra com credito vinculado')
    versao = sql(banco, 'select financeiro.versao_compra(%s) v', (ids['apple'],))[0]['v']
    antes = md5_compras(banco)
    assert falha(banco, 'excluir_compra', PESSOAL, ids['apple'], versao)[0] in ('P0001', '22023', '55000')
    assert md5_compras(banco) == antes
    # a compra sem credito continua editavel
    assert sql(banco, 'select financeiro.bloqueio_da_parcela(%s) b', (ids['cloudflare'],))[0]['b'] is None


def test_permissoes(banco):
    cenario(banco)
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, [ESTORNO_APPLE], str(uuid.uuid4()), usuario=USUARIO_B)[0] == '42501'
    assert creditos(banco) == []
    f = sql(banco, "select has_table_privilege('authenticated', 'financeiro.credito_fatura', 'select') t, "
                   "has_table_privilege('anon', 'financeiro.credito_fatura', 'select') a, "
                   "has_function_privilege('authenticated', 'financeiro.creditos_fatura(integer)', 'execute') f, "
                   "(select relrowsecurity and relforcerowsecurity from pg_class where oid = 'financeiro.credito_fatura'::regclass) rls")[0]
    assert (f['t'], f['a'], f['f'], f['rls']) == (False, False, False, True)


def executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_recusada_com_credito_e_reaplicacao(banco):
    cenario(banco)
    bruto = a_pagar(banco)
    executar(banco, REVERSAO)  # sem credito: volta ao texto anterior
    assert previa(banco, ESTORNO_APPLE)['linhas'][0]['classificacao_importacao'] == 'IGNORADA'
    executar(banco, MIGRATION)
    importar(banco, ESTORNO_APPLE)
    with pytest.raises(psycopg2.Error, match='creditos de fatura registrados'):
        executar(banco, REVERSAO)
    assert a_pagar(banco) == bruto - D('50.22')
