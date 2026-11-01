"""
Testes FIN-CARTAO-PREVISTO-EXECUTADO-01 (migration 20261209090000), em cluster local descartavel com o cenario FICTICIO
do FIN-RECORRENCIA-1 (Cartao Teste 910, Pessoal; Categoria do Cartao 961 com limite 981 de R$ 500, mapeada a
Assinaturas 952; Moradia 951 sem vinculo). Recorrencias criadas aqui, em 05/2029. Chamadas como o navegador.
- previsao da recorrencia sem cobranca: previsto no planejamento, fora do executado e do valor a pagar;
- cobranca igual, menor ou maior: executado = cobrado, previsto preservado, valor-base intacto;
- compra nao reconhecida: compra comum, executada uma vez;
- conciliacao e reversao; fatura aberta, fechada (consolidada) e paga (historico preservado);
- pagamento: paga o executado e marca as previsoes como nao cobradas; o estorno as devolve; repeticao e concorrencia;
- recorrencia futura; perfis separados; historico intacto; limites preservados; seguranca; reversao da migration.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartao_despesas_fixas import (  # noqa: F401  (fixture e ajudantes reaproveitados)
    MES,
    PESSOAL,
    analisar,
    banco,
    caso_netflix,
    compras,
    conciliar,
    importar,
    linha,
    md5_compras,
    ocorrencia,
    recorrencia,
)
from tests.test_supabase_cartoes import CARTAO, comprar, fatura, pagar, tabela
from tests.test_supabase_despesas import _paralelo
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, USUARIO_B, cluster, sql  # noqa: F401
from tests.test_supabase_recorrencia_cartao import falha, gerar_mes, rpc

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

JUNHO = '2029-06-01'
SUPABASE = Path(__file__).resolve().parent.parent / 'supabase'
MIGRATION = SUPABASE / 'migrations' / '20261209090000_financeiro_cartao_previsto_executado.sql'
REVERSAO = SUPABASE / 'reversao' / '20261209090000_cartao_previsto_executado_anterior.sql'


def D(valor):
    return Decimal(str(valor)).quantize(Decimal('0.01'))


def lista(dsn, mes=MES):
    """Linha da fatura do cartao na lista de Despesas: (valor, previsto, executado)."""
    f = fatura(dsn, CARTAO, mes)
    c = next(x for x in tabela(dsn, 'contas_do_mes', PESSOAL, mes) if x['id'] == f['id'])
    return D(c['valor']), D(c['valor_previsto']), D(c['valor_executado'])


def do_mes(dsn, mes=MES):
    c = next(x for x in tabela(dsn, 'faturas_do_mes', PESSOAL, mes) if x['cartao_id'] == CARTAO)
    return D(c['valor_previsto']), D(c['valor_executado'])


def resumo(dsn, mes=MES):
    return rpc(dsn, 'fatura_por_categoria', PESSOAL, CARTAO, mes)


def fixa(dsn, item, mes=MES):
    return compras(dsn, mes)[ocorrencia(dsn, item, mes)['id']]


def dados_pagamento(dsn, mes=MES):
    return rpc(dsn, 'dados_pagamento_fatura', PESSOAL, fatura(dsn, CARTAO, mes)['id'])


def conta_bancaria(dsn):
    return sql(dsn, "select id from public.conta_bancaria where nome = 'Conta Pessoal (A)'")[0]['id']


def pagar_pelo_app(dsn, mes=MES, chave=None):
    f = fatura(dsn, CARTAO, mes)['id']
    exe = f"{D(dados_pagamento(dsn, mes)['fatura']['valor_executado'])}"
    return rpc(dsn, 'pagar_fatura', PESSOAL, f, {'conta_bancaria_id': conta_bancaria(dsn), 'data_pagamento': '2029-05-31',
                                                 'valor_pago': exe, 'valor_executado': exe}, chave or str(uuid.uuid4()))


def estornar_pelo_app(dsn, movimento, mes=MES):
    return rpc(dsn, 'estornar_pagamento_fatura', PESSOAL, fatura(dsn, CARTAO, mes)['id'], movimento,
               {'motivo': 'Pagamento lancado por engano', 'data_estorno': '2029-06-01'}, str(uuid.uuid4()))


def cenario(dsn):
    """Netflix prevista (R$ 59,90, sem cobranca) e uma compra variavel real (R$ 40, Categoria do Cartao 961)."""
    item = recorrencia(dsn, 'Netflix', '59.90')
    gerar_mes(dsn, MES)
    comprar(dsn, descricao='Revista', valor='40.00', total_parcelas=1)
    return item


def procurar(obj, chave):
    if isinstance(obj, dict):
        if chave in obj:
            return obj[chave]
        for v in obj.values():
            r = procurar(v, chave)
            if r is not None:
                return r
    return None


# ---------------------------------------------------------------------------------------------------------------------
# 1. Previsao sem cobranca
# ---------------------------------------------------------------------------------------------------------------------

def test_previsao_sem_cobranca_fica_fora_do_executado_e_do_valor_a_pagar(banco):
    item = cenario(banco)
    f = fixa(banco, item)
    assert (f['situacao_ocorrencia'], f['valor_previsto'], f['valor_executado'], f['valor']) == ('PREVISTA', 59.9, 0, 59.9)
    # Lista de Despesas: executado so a compra real; previsto = 40 + 59,90 previstos + (500 - 40) do limite
    assert lista(banco) == (D('559.90'), D('559.90'), D('40.00'))
    assert do_mes(banco) == (D('559.90'), D('40.00'))
    r = resumo(banco)
    grupos = {g['tipo_grupo']: g for g in r['categorias']}
    assert (r['total_fatura'], r['total_previsto_pendente'], r['total_despesas_fixas']) == (40, 59.9, 0)
    assert (grupos['despesas_fixas']['gasto_atual'], grupos['despesas_fixas']['previsto_pendente']) == (0, 59.9)
    assert 'previstos aguardando cobranca' in grupos['despesas_fixas']['avisos'][0]
    assert sum(g['gasto_atual'] for g in r['categorias']) == r['total_fatura']
    linhas = rpc(banco, 'lancamentos_fatura_por_categoria', PESSOAL, CARTAO, MES, 'despesas_fixas')['lancamentos']
    assert [(l['situacao_ocorrencia'], l['valor_executado'], l['valor_previsto'], l['valor']) for l in linhas] == \
        [('PREVISTA', 0, 59.9, 59.9)]
    assert D(dados_pagamento(banco)['fatura']['valor_executado']) == D('40.00')  # o que se paga
    assert fatura(banco, CARTAO, MES)['valor_executado'] == D('40.00')          # gravado no recalculo
    # Dashboard (faturas em aberto): a previsao so entra quando a cobranca chega
    antes = D(procurar(rpc(banco, 'dashboard_resumo_tela', PESSOAL, '2029-05'), 'faturas_em_aberto')['valor'])
    importar(banco, linha(1, 'NETFLIX.COM', '59.90', categoria=None))
    depois = D(procurar(rpc(banco, 'dashboard_resumo_tela', PESSOAL, '2029-05'), 'faturas_em_aberto')['valor'])
    assert depois - antes == D('59.90')


def test_recorrencia_futura_so_no_previsto(banco):
    cenario(banco)  # a geracao de 05/2029 ja preve 06/2029
    assert lista(banco, JUNHO) == (D('559.90'), D('559.90'), D('0.00'))
    assert resumo(banco, JUNHO)['total_fatura'] == 0


# ---------------------------------------------------------------------------------------------------------------------
# 2. Cobranca real: igual, menor e maior; nao reconhecida
# ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('cobrado, diferenca', [('59.90', '0.00'), ('44.90', '-15.00'), ('70.00', '10.10')])
def test_cobranca_realiza_a_previsao(banco, cobrado, diferenca):
    item = cenario(banco)
    assert importar(banco, linha(1, 'NETFLIX.COM', cobrado, categoria=None))['realizadas'] == 1
    f = fixa(banco, item)
    assert (f['situacao_ocorrencia'], D(f['valor_executado']), D(f['valor_previsto'])) == ('CONFIRMADA', D(cobrado), D('59.90'))
    assert D(f['valor_executado']) - D(f['valor_previsto']) == D(diferenca)
    exe = D('40.00') + D(cobrado)
    assert lista(banco) == (exe + D('460.00'), exe + D('460.00'), exe)
    assert resumo(banco)['total_fatura'] == float(exe)
    assert sql(banco, 'select valor from public.item_despesa where id = %s', (item,))[0]['valor'] == D('59.90')
    assert fixa(banco, item, JUNHO)['situacao_ocorrencia'] == 'PREVISTA'  # o mes seguinte continua previsto


def test_compra_nao_reconhecida_e_executada_uma_vez(banco):
    netflix = cenario(banco)
    apple = recorrencia(banco, 'Apple One', '59.90')
    gerar_mes(banco, MES)
    r = analisar(banco, linha(1, 'APPLE.COM/BILL', '59.90'))[0]
    assert (r['status'], r['recorrencia_id'], r['realiza_lancamento_id'], r['conciliacao']) == ('valido', None, None, None)
    importar(banco, linha(1, 'APPLE.COM/BILL', '59.90'))
    assert lista(banco)[2] == D('99.90')  # 40 + 59,90 da compra comum; as duas previsoes seguem fora
    assert {fixa(banco, i)['situacao_ocorrencia'] for i in (netflix, apple)} == {'PREVISTA'}


# ---------------------------------------------------------------------------------------------------------------------
# 3. Conciliacao e reversao
# ---------------------------------------------------------------------------------------------------------------------

def test_conciliacao_e_reversao_voltam_os_valores(banco):
    item, previsto, cobranca = caso_netflix(banco)
    # Antes: a cobranca (compra comum, 961) e executada; a previsao, nao
    assert lista(banco) == (D('559.90'), D('559.90'), D('44.90'))
    r = conciliar(banco, previsto, cobranca)
    assert fixa(banco, item)['situacao_ocorrencia'] == 'CONFIRMADA'
    assert lista(banco) == (D('544.90'), D('544.90'), D('44.90'))  # uma ocorrencia: 44,90 executado + 500 do limite
    rpc(banco, 'reverter_ocorrencia_recorrencia', PESSOAL, r['ocorrencia_id'], str(uuid.uuid4()))
    assert fixa(banco, item)['situacao_ocorrencia'] == 'PREVISTA'
    assert lista(banco) == (D('559.90'), D('559.90'), D('44.90'))
    assert fatura(banco, CARTAO, MES)['valor_executado'] == D('44.90')


# ---------------------------------------------------------------------------------------------------------------------
# 4. Fatura fechada (consolidada) e paga
# ---------------------------------------------------------------------------------------------------------------------

def test_fatura_fechada_previsao_continua_fora_e_nao_e_realizada(banco):
    item = cenario(banco)
    sql(banco, "update public.conta set status_fatura = 'FECHADA' where id = %s", (fatura(banco, CARTAO, MES)['id'],))
    assert lista(banco)[2] == D('40.00')
    r = analisar(banco, linha(1, 'NETFLIX.COM', '59.90', categoria=None))[0]
    assert (r['status'], r['realiza_lancamento_id'], r['ignorar']) == ('revisar', None, False)  # FIN-CARTAO-IMPORTACAO-FIXAS-01: pede revisao (nao e descartada)
    assert fixa(banco, item)['situacao_ocorrencia'] == 'PREVISTA'


def test_fatura_paga_antes_da_regra_fica_como_foi_paga(banco):
    """Pagamento gravado sem a marca (historico do Flask): a previsao foi paga com a fatura e continua executada."""
    item = cenario(banco)
    pagar(banco, CARTAO, MES)
    f = fixa(banco, item)
    assert (f['situacao_ocorrencia'], f['valor_executado']) == ('PAGA', 59.9)
    assert lista(banco) == (D('99.90'), D('559.90'), D('99.90'))  # paga: o valor e o executado (previsto como antes)


# ---------------------------------------------------------------------------------------------------------------------
# 5. Pagamento e estorno; repeticao e concorrencia
# ---------------------------------------------------------------------------------------------------------------------

def test_pagamento_paga_o_executado_e_o_estorno_devolve_a_previsao(banco):
    item = cenario(banco)
    chave = str(uuid.uuid4())
    p = pagar_pelo_app(banco, chave=chave)
    assert D(p['valor_pago']) == D('40.00')
    f = fixa(banco, item)
    assert (f['situacao_ocorrencia'], f['valor_executado'], f['valor_previsto']) == ('NAO_COBRADA', 0, 59.9)
    assert lista(banco) == (D('40.00'), D('500.00'), D('40.00'))  # paga: o valor e o que foi pago
    marcas = sql(banco, "select * from financeiro.ocorrencia_recorrencia_cartao where origem = 'NAO_COBRADA'")
    assert [(m['lancamento_id'], m['pagamento_id'], m['valor_previsto'], m['revertida_em']) for m in marcas] == \
        [(ocorrencia(banco, item)['id'], p['pagamento_id'], D('59.90'), None)]
    # repetir o pagamento com a mesma chave nao marca de novo
    assert rpc(banco, 'pagar_fatura', PESSOAL, fatura(banco, CARTAO, MES)['id'], {}, chave)['repetida'] is True
    assert sql(banco, "select count(*) n from financeiro.ocorrencia_recorrencia_cartao where origem = 'NAO_COBRADA'")[0]['n'] == 1
    # a marca so e desfeita pelo estorno do pagamento
    assert falha(banco, 'reverter_ocorrencia_recorrencia', PESSOAL, marcas[0]['id'], str(uuid.uuid4()))[0] == 'P0001'
    estornar_pelo_app(banco, p['movimento_id'])
    f = fixa(banco, item)
    assert (f['situacao_ocorrencia'], f['valor_executado']) == ('PREVISTA', 0)
    assert lista(banco) == (D('559.90'), D('559.90'), D('40.00'))
    assert fatura(banco, CARTAO, MES)['valor_executado'] == D('40.00')
    # pagar de novo marca de novo
    pagar_pelo_app(banco)
    assert fixa(banco, item)['situacao_ocorrencia'] == 'NAO_COBRADA'


def test_cobranca_depois_do_pagamento_entra_na_proxima_fatura(banco):
    item = cenario(banco)
    pagar_pelo_app(banco)
    r = analisar(banco, linha(1, 'NETFLIX.COM', '59.90', categoria=None))[0]
    assert (r['status'], r['recorrencia_id'], r['realiza_lancamento_id']) == ('valido', item, None)
    importar(banco, linha(1, 'NETFLIX.COM', '59.90', categoria=None))
    nova = sql(banco, 'select * from public.lancamento_agregado where item_despesa_id = %s and is_importado', (item,))
    assert [(str(n['mes_fatura']), str(n['mes_fatura_original']), n['is_recorrente']) for n in nova] == [(JUNHO, MES, True)]
    assert lista(banco) == (D('40.00'), D('500.00'), D('40.00'))  # a fatura paga nao muda
    assert lista(banco, JUNHO)[2] == D('59.90')                  # a cobranca e executada em junho


def test_pagamento_sem_compra_real_e_recusado(banco):
    recorrencia(banco, 'Netflix', '59.90')
    gerar_mes(banco, MES)  # so a previsao: nada a pagar
    d = dados_pagamento(banco)
    assert (D(d['fatura']['valor_executado']), d['pode_pagar']) == (D('0.00'), False)


def test_concorrencia_a_mesma_cobranca_realiza_uma_vez(banco):
    item = cenario(banco)
    resultados = _paralelo([lambda: importar(banco, linha(1, 'NETFLIX.COM', '44.90', categoria=None)) for _ in range(2)])
    assert sorted(r[0] for r in resultados) == ['erro', 'ok']
    assert sql(banco, "select count(*) n from financeiro.ocorrencia_recorrencia_cartao where origem = 'IMPORTACAO'")[0]['n'] == 1
    assert len(sql(banco, 'select id from public.lancamento_agregado where item_despesa_id = %s and mes_fatura = %s',
                   (item, MES))) == 1
    assert lista(banco)[2] == D('84.90')


# ---------------------------------------------------------------------------------------------------------------------
# 6. Perfis, historico e limites
# ---------------------------------------------------------------------------------------------------------------------

def test_perfis_separados(banco):
    cenario(banco)
    assert falha(banco, 'compras_da_fatura', PESSOAL, CARTAO, MES, usuario=USUARIO_B)[0] == '42501'
    assert all(c['cartao_id'] != CARTAO for c in tabela(banco, 'faturas_do_mes', ID['PERFIL_B'], MES, usuario=USUARIO_B))
    assert all(c['cartao_id'] != CARTAO for c in tabela(banco, 'faturas_do_mes', ID['EMPRESA'], MES))


def test_limites_da_categoria_preservados(banco):
    item = cenario(banco)
    importar(banco, linha(1, 'NETFLIX.COM', '44.90', categoria=None))  # fixa confirmada com Categoria do Cartao 961
    assert fixa(banco, item)['situacao_ocorrencia'] == 'CONFIRMADA'
    limite = next(x for x in tabela(banco, 'limites_do_cartao', PESSOAL, CARTAO, MES) if x['id'] == 981)
    assert (limite['gasto_atual'], limite['disponivel']) == (40, 460)


# ---------------------------------------------------------------------------------------------------------------------
# 7. Seguranca e reversao da migration (historico intacto)
# ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('funcao, definer', [
    ('financeiro.situacao_previsao(integer, text, boolean, integer, date)', False),
    ('financeiro.valor_executado_compra(numeric, text)', False),
    ('financeiro.previsoes_no_pagamento_da_fatura()', True)])
def test_funcoes_internas(banco, funcao, definer):
    f = sql(banco, f"select prosecdef, proconfig, has_function_privilege('anon', '{funcao}', 'execute') anon, "
                   f"has_function_privilege('authenticated', '{funcao}', 'execute') autenticado "
                   f"from pg_proc where oid = '{funcao}'::regprocedure")[0]
    assert (f['prosecdef'], f['proconfig'], f['anon'], f['autenticado']) == (definer, ['search_path=""'], False, False)


def executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def md5_faturas(dsn):
    return sql(dsn, "select coalesce(md5(string_agg(c::text, '|' order by c.id)), '') h from public.conta c")[0]['h']


def test_reversao_da_migration_e_reaplicacao_sem_alterar_dados(banco):
    item = cenario(banco)
    p = pagar_pelo_app(banco)
    with pytest.raises(psycopg2.Error):
        executar(banco, REVERSAO)  # previsao nao cobrada vigente: recusada, nada muda
    estornar_pelo_app(banco, p['movimento_id'])
    antes = (md5_compras(banco), md5_faturas(banco))
    executar(banco, REVERSAO)
    assert lista(banco)[2] == D('99.90')  # regra anterior: a previsao contava no executado
    assert 'valor_executado' not in tabela(banco, 'compras_da_fatura', PESSOAL, CARTAO, MES)[0]
    assert (md5_compras(banco), md5_faturas(banco)) == antes  # a reversao nao muda dado
    executar(banco, MIGRATION)
    assert (md5_compras(banco), md5_faturas(banco)) == antes  # a migration tambem nao
    assert lista(banco)[2] == D('40.00')
    assert fixa(banco, item)['situacao_ocorrencia'] == 'PREVISTA'
