"""
Testes FIN-CARTOES-MULTIPLOS-01 (migration 20261213090000), em cluster local descartavel com o cenario FICTICIO do
FIN-RECORRENCIA-1 (contrato "Cartao Teste" 910, Pessoal; Categoria do Cartao 961 com limite de R$ 500 para Assinaturas
952), em 05/2029. Cartoes vinculados FICTICIOS (finais 1111/2222/3333). Linhas como o leitor do arquivo as envia: o PDF
traz o final do cartao (cartao_final); o CSV, nao. Chamadas como o navegador.
- contrato com varios cartoes vinculados e uma fatura: por cartao, pagamento unico, limites compartilhados;
- cartao cancelado, virtual ativo, substituicao; dados sensiveis recusados;
- importacao: cartao pelo final ou pela escolha (nunca presumido), compras identicas de cartoes diferentes, reimportacao,
  parcela intermediaria, despesa fixa, creditos com e sem cartao;
- limpeza seletiva: so o que a importacao registrou, protegidos, previa conferida (hash), rollback, idempotencia;
- acesso cruzado entre perfis e contratos; reversao da migration.
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
    ocorrencia,
)
from tests.test_supabase_cartao_previsto_executado import pagar_pelo_app
from tests.test_supabase_cartoes import ASSINATURAS, CARTAO, CARTAO_B, comprar, fatura, pagar
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_B, cluster, sql  # noqa: F401
from tests.test_supabase_recorrencia_cartao import falha, rpc

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

SUPABASE = Path(__file__).resolve().parent.parent / 'supabase'
MIGRATION = SUPABASE / 'migrations' / '20261213090000_financeiro_cartoes_multiplos.sql'
REVERSAO = SUPABASE / 'reversao' / '20261213090000_cartoes_multiplos_anterior.sql'


def D(valor):
    return Decimal(str(valor)).quantize(Decimal('0.01'))


def linha(n, descricao, valor, data='2029-05-12', categoria=ASSINATURAS, parcela=(1, 1), final=None, **extra):
    normal = ' '.join(''.join(c if c.isalnum() else ' ' for c in descricao.lower()).split())
    credito = str(valor).startswith('-')
    return {'linha_id': f'pdf-{n}', 'linha_origem': n, 'data_compra': data, 'descricao_original': descricao,
            'descricao_normalizada': descricao, 'descricao_exibida': descricao, 'descricao_classificacao': normal,
            'valor': str(valor).lstrip('-'), 'parcela_atual': parcela[0], 'total_parcelas': parcela[1],
            'tipo_movimento': 'credito' if credito else 'debito', **({'cartao_final': final} if final else {}),
            **({'categoria_id': categoria} if categoria and not credito else {}), **extra}


def cartao(dsn, final, tipo='FISICO', contrato=CARTAO, usuario=None, **dados):
    return rpc(dsn, 'salvar_cartao_vinculado', PESSOAL, contrato, None, {'nome': f'Cartao {final}', 'final': final, 'tipo': tipo,
                                                                          **dados}, None, **({'usuario': usuario} if usuario else {}))


def editar(dsn, cv, **dados):
    return rpc(dsn, 'salvar_cartao_vinculado', PESSOAL, CARTAO, cv['id'], dados, cv['versao'])


def vinculados(dsn):
    return rpc(dsn, 'cartoes_vinculados', PESSOAL, CARTAO)


def previa(dsn, *linhas, mes=MES):
    return rpc(dsn, 'analisar_importacao_cartao', PESSOAL, CARTAO, mes, list(linhas))


def importar(dsn, *linhas, mes=MES, chave=None):
    return rpc(dsn, 'importar_fatura_cartao', PESSOAL, CARTAO, mes, list(linhas), chave or str(uuid.uuid4()))


def resumo(dsn, mes=MES):
    return rpc(dsn, 'fatura_por_categoria', PESSOAL, CARTAO, mes)


def por_cartao(dsn, mes=MES):
    return {(x['final'] or '-'): (D(x['compras']), D(x['creditos']), D(x['total'])) for x in resumo(dsn, mes)['por_cartao']}


def origem(dsn, descricao):
    return sql(dsn, 'select v.final from public.lancamento_agregado l left join financeiro.cartao_vinculado v '
                    'on v.id = l.cartao_vinculado_id where l.descricao = %s order by l.id', (descricao,))


def md5(dsn, tabela):
    return sql(dsn, f"select coalesce(md5(string_agg(t::text, '|' order by t.id)), '') h from {tabela} t")[0]['h']


def limpeza(dsn, cartao_id=CARTAO, mes=MES):
    return rpc(dsn, 'previa_limpeza_importacoes', PESSOAL, cartao_id, mes)


def limpar(dsn, p, cartao_id=CARTAO, mes=MES, chave=None):
    return rpc(dsn, 'limpar_importacoes_cartao', PESSOAL, cartao_id, mes, p['hash'], chave or str(uuid.uuid4()))


# ---------------------------------------------------------------------------------------------------------------------
# 1. Cartoes vinculados: cadastro, cancelamento, virtual ativo, substituicao, dados sensiveis
# ---------------------------------------------------------------------------------------------------------------------

def test_cadastro_cancelamento_e_substituicao(banco):
    fisico = cartao(banco, '1111', portador='Titular')
    virtual = cartao(banco, '2222', 'VIRTUAL')
    assert (fisico['tipo'], fisico['situacao'], virtual['tipo']) == ('FISICO', 'ATIVO', 'VIRTUAL')
    # o fisico cancelado (compras contestadas) continua no historico; o virtual segue ativo
    cancelado = editar(banco, fisico, situacao='CANCELADO', data_cancelamento='2029-05-20')
    assert (cancelado['situacao'], cancelado['data_cancelamento']) == ('CANCELADO', '2029-05-20')
    assert [(c['final'], c['situacao']) for c in vinculados(banco)] == [('2222', 'ATIVO'), ('1111', 'CANCELADO')]
    # o novo fisico substitui o cancelado sem apagar o historico
    novo = cartao(banco, '3333')
    subst = editar(banco, cancelado, situacao='SUBSTITUIDO', substituto_id=novo['id'])
    assert (subst['situacao'], subst['substituto']['final']) == ('SUBSTITUIDO', '3333')
    assert falha(banco, 'salvar_cartao_vinculado', PESSOAL, CARTAO, novo['id'], {'situacao': 'SUBSTITUIDO'}, novo['versao'])[1] == \
        'Informe o cartao substituto'
    # versao desatualizada, final repetido e dados sensiveis recusados
    assert falha(banco, 'salvar_cartao_vinculado', PESSOAL, CARTAO, fisico['id'], {'nome': 'X'}, fisico['versao'])[0] == '40001'
    assert falha(banco, 'salvar_cartao_vinculado', PESSOAL, CARTAO, None, {'nome': 'Outro', 'final': '2222', 'tipo': 'FISICO'},
                 None)[0] == '23505'
    for dados in ({'numero_cartao': '4111111111111111'}, {'codigo_seguranca': '123'}, {'final': '12345'}):
        assert falha(banco, 'salvar_cartao_vinculado', PESSOAL, CARTAO, None, {'nome': 'X', 'tipo': 'FISICO', 'final': '4444',
                                                                                **dados}, None)[0] == '22023'
    colunas = {r['column_name'] for r in sql(banco, "select column_name from information_schema.columns "
                                                    "where table_schema = 'financeiro' and table_name = 'cartao_vinculado'")}
    assert not colunas & {'numero', 'numero_cartao', 'cvv', 'codigo_seguranca', 'validade'}


def test_final_de_cartao_com_compras_nao_muda(banco):
    cv = cartao(banco, '1111')
    importar(banco, linha(1, 'PADARIA', '8.00', final='1111'))
    cv = next(c for c in vinculados(banco) if c['id'] == cv['id'])
    assert cv['compras'] == 1
    assert 'nao muda' in falha(banco, 'salvar_cartao_vinculado', PESSOAL, CARTAO, cv['id'], {'final': '9999'}, cv['versao'])[1]
    assert editar(banco, cv, nome='Fisico do titular')['nome'] == 'Fisico do titular'


# ---------------------------------------------------------------------------------------------------------------------
# 2. Importacao com o cartao de origem
# ---------------------------------------------------------------------------------------------------------------------

def test_cartao_pelo_final_do_arquivo_nunca_presumido(banco):
    cartao(banco, '1111')
    cartao(banco, '2222', 'VIRTUAL')
    r = previa(banco, linha(1, 'AMAZON BR', '35.70', final='2222'), linha(2, 'IFOOD', '7.95', final='1111'),
               linha(3, 'LOJA X', '10.00', final='9999'), linha(4, 'PADARIA', '8.00'))
    l = r['linhas']
    assert [(x['cartao_vinculado'] or {}).get('final') for x in l] == ['2222', '1111', None, None]
    assert [x['cartao_origem'] for x in l] == ['ARQUIVO', 'ARQUIVO', None, None]
    assert any('final 9999 nao cadastrado' in m for m in l[2]['mensagens']) and l[2]['status'] == 'valido'  # nao bloqueia
    assert (r['validacoes']['cartoes_nao_cadastrados'], r['validacoes']['sem_cartao_identificado']) == (['9999'], 2)
    assert [c['final'] for c in r['cartoes_contrato']] == ['1111', '2222']
    # a escolha do usuario vale (0 = sem cartao); cartao que nao e do contrato pede revisao
    escolhida = previa(banco, linha(4, 'PADARIA', '8.00', cartao_vinculado_escolhido_id=r['cartoes_contrato'][0]['id']),
                       linha(2, 'IFOOD', '7.95', final='1111', cartao_vinculado_escolhido_id=0),
                       linha(5, 'LOJA', '3.00', cartao_vinculado_escolhido_id=999999))['linhas']
    assert [((x['cartao_vinculado'] or {}).get('final'), x['cartao_origem'], x['classificacao_importacao']) for x in escolhida] == \
        [('1111', 'ESCOLHA', 'COMPRA'), (None, 'ESCOLHA', 'COMPRA'), (None, 'ESCOLHA', 'REVISAR')]


def test_compras_identicas_de_cartoes_diferentes_e_reimportacao(banco):
    cartao(banco, '1111')
    cartao(banco, '2222', 'ADICIONAL', portador='Adicional')
    arquivo = [linha(1, 'SUPERMERCADO', '50.00', final='1111'), linha(2, 'SUPERMERCADO', '50.00', final='2222')]
    r = previa(banco, *arquivo)['linhas']
    assert [(x['classificacao_importacao'], x['duplicidade']) for x in r] == [('COMPRA', None), ('COMPRA', None)]
    assert importar(banco, *arquivo)['inseridos'] == 2
    assert [x['final'] for x in origem(banco, 'SUPERMERCADO')] == ['1111', '2222']
    # reimportar o mesmo arquivo: nada novo; a mesma compra do outro cartao nao e duplicata
    assert [x['classificacao_importacao'] for x in previa(banco, *arquivo)['linhas']] == ['JA_EXISTENTE', 'JA_EXISTENTE']
    assert falha(banco, 'importar_fatura_cartao', PESSOAL, CARTAO, MES, arquivo, str(uuid.uuid4()))[1] == 'Nenhuma linha para importar'
    cartao(banco, '3333')
    assert previa(banco, linha(3, 'SUPERMERCADO', '50.00', final='3333'))['linhas'][0]['classificacao_importacao'] == 'COMPRA'


def test_dois_cartoes_uma_fatura_por_cartao_e_pagamento_unico(banco):
    cartao(banco, '1111')
    cartao(banco, '2222', 'VIRTUAL')
    importar(banco, linha(1, 'IFOOD', '7.95', final='1111'), linha(2, 'AMAZON BR', '35.70', final='2222'),
             linha(3, 'NUVEM', '20.00', final='2222'), linha(4, 'AJUSTE CREDITO PARC', '-0.01'))
    r = resumo(banco)
    assert por_cartao(banco) == {'1111': (D('7.95'), D(0), D('7.95')), '2222': (D('55.70'), D(0), D('55.70')),
                                 '-': (D(0), D('0.01'), D('-0.01'))}
    assert sum(D(x['total']) for x in r['por_cartao']) == D(r['total_fatura']) == D('63.64')
    assert len(sql(banco, 'select id from public.conta where is_fatura_cartao and item_despesa_id = %s and cartao_competencia = %s',
                   (CARTAO, MES))) == 1  # uma fatura do contrato
    movimentos = sql(banco, 'select count(*) n from public.movimento_financeiro')[0]['n']
    pago = pagar_pelo_app(banco)
    assert D(pago['valor_pago']) == D('63.64')
    assert sql(banco, 'select count(*) n from public.movimento_financeiro')[0]['n'] == movimentos + 1  # um movimento so
    f = fatura(banco, CARTAO, MES)['id']
    assert falha(banco, 'pagar_fatura', PESSOAL, f, {'conta_bancaria_id': 1, 'data_pagamento': '2029-05-31', 'valor_pago': '63.64',
                                                     'valor_executado': '63.64'}, str(uuid.uuid4()))[0] in ('22023', 'P0001', '42501')


def test_limite_compartilhado_entre_cartoes(banco):
    cartao(banco, '1111')
    cartao(banco, '2222', 'ADICIONAL')
    importar(banco, linha(1, 'STREAMING A', '300.00', final='1111'), linha(2, 'STREAMING B', '250.00', final='2222'))
    cat = next(g for g in resumo(banco)['categorias'] if g['categoria_cartao_id'] == 961)
    assert (D(cat['gasto_atual']), D(cat['disponivel']), cat['status']) == (D('550.00'), D('-50.00'), 'Estourado')


def test_parcela_intermediaria_despesa_fixa_e_recorrencia_preservada(banco):
    ids = assinaturas(banco)
    cartao(banco, '1111')
    recorrencias = md5(banco, 'public.item_despesa')
    res = importar(banco, linha(1, 'HAIKAR VEICULOS', '416.81', data='2029-04-28', parcela=(5, 6), final='1111'),
                   linha(2, 'NETFLIX.COM', '59.90', categoria=None, final='1111'))
    assert (res['inseridos'], res['realizadas']) == (1, 1)  # so a parcela 5/6 (nenhuma futura) e a previsao realizada
    assert sql(banco, "select numero_parcela, total_parcelas from public.lancamento_agregado where descricao = 'HAIKAR VEICULOS'") == \
        [{'numero_parcela': 5, 'total_parcelas': 6}]
    assert sql(banco, 'select v.final from public.lancamento_agregado l join financeiro.cartao_vinculado v '
                      'on v.id = l.cartao_vinculado_id where l.id = %s', (ocorrencia(banco, ids['Netflix'])['id'],))[0]['final'] == '1111'
    assert md5(banco, 'public.item_despesa') == recorrencias  # recorrencias (e o valor-base) intactas


def test_creditos_com_e_sem_cartao(banco):
    cartao(banco, '1111')
    cartao(banco, '2222', 'ADICIONAL')
    compra_1111 = importar(banco, linha(1, 'IOF de "Nuvem"', '0.99', final='1111'))['lancamentos'][0]
    importar(banco, linha(2, 'IOF de "Nuvem"', '0.99', final='2222', data='2029-05-13'))
    r = previa(banco, linha(3, 'IOF de volta de Nuvem', '-0.99', final='1111'), linha(4, 'Credito de ajuste', '-3.00'))['linhas']
    assert (r[0]['credito']['compra']['id'], r[0]['cartao_vinculado']['final']) == (compra_1111, '1111')  # o IOF do proprio cartao
    assert (r[1]['credito']['natureza'], r[1]['cartao_vinculado']) == ('AJUSTE', None)  # o documento nao diz o cartao
    importar(banco, linha(3, 'IOF de volta de Nuvem', '-0.99', final='1111'), linha(4, 'Credito de ajuste', '-3.00'))
    assert por_cartao(banco)['1111'] == (D('0.99'), D('0.99'), D(0))
    assert por_cartao(banco)['-'] == (D(0), D('3.00'), D('-3.00'))
    lista = rpc(banco, 'lancamentos_fatura_por_categoria', PESSOAL, CARTAO, MES, 'cartao-0')['lancamentos']
    assert [(x['descricao'], D(x['valor'])) for x in lista] == [('Credito de ajuste', D('-3.00'))]
    assert len(rpc(banco, 'lancamentos_fatura_por_categoria', PESSOAL, CARTAO, MES,
                   f"cartao-{next(c['id'] for c in vinculados(banco) if c['final'] == '1111')}")['lancamentos']) == 2  # a compra e o credito


# ---------------------------------------------------------------------------------------------------------------------
# 3. Limpeza seletiva das despesas importadas
# ---------------------------------------------------------------------------------------------------------------------

def cenario_limpeza(dsn):
    """Importadas (2 compras, 1 parcela com futuras, 1 credito), manual, previsao de recorrencia e 'importada' sem registro."""
    assinaturas(dsn)
    cartao(dsn, '1111')
    importar(dsn, linha(1, 'SUPERMERCADO', '50.00', final='1111'), linha(2, 'FARMACIA', '20.00'),
             linha(3, 'Credito de ajuste', '-3.00'))
    importar(dsn, linha(4, 'TV LOJA', '100.00', parcela=(1, 3), gerar_parcelas_futuras=True))
    comprar(dsn, descricao='Compra manual', valor='40.00', total_parcelas=1)
    sql(dsn, "insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, categoria_id, descricao, valor, data_compra, "
             "mes_fatura, numero_parcela, total_parcelas, is_importado, origem_importacao) "
             "values (%s, %s, %s, 'Importada pelo Flask', 15.00, '2029-05-05', %s, 1, 1, true, 'csv')",
        (PESSOAL, CARTAO, ASSINATURAS, MES))


def test_previa_da_limpeza_so_o_que_a_importacao_registrou(banco):
    cenario_limpeza(banco)
    antes = md5_compras(banco)
    p = rpc(banco, 'previa_limpeza_importacoes', PESSOAL, CARTAO, None)
    assert md5_compras(banco) == antes  # a previa nao grava
    assert sorted(x['descricao'] for x in p['compras_elegiveis']) == \
        ['FARMACIA', 'SUPERMERCADO', 'TV LOJA (1/3)', 'TV LOJA (2/3)', 'TV LOJA (3/3)']
    assert [x['descricao'] for x in p['creditos_elegiveis']] == ['Credito de ajuste']
    assert [x['descricao'] for x in p['nao_comprovadas']] == ['Importada pelo Flask']  # sem registro: fora
    assert (p['protegidos'], p['executavel']) == ([], True)
    maio = next(f for f in p['por_fatura'] if f['mes_fatura'] == MES)
    assert (D(maio['total_compras']), D(maio['total_creditos']), maio['previsoes_pendentes']) == (D('170.00'), D('3.00'), 4)
    assert D(maio['valor_a_pagar_depois']) == D(maio['valor_a_pagar_atual']) - D('170.00') + D('3.00')
    assert p['totais'] == {'compras_elegiveis': 5, 'valor_compras': 370.0, 'creditos_elegiveis': 1, 'valor_creditos': 3.0,
                           'protegidos': 0, 'nao_comprovadas': 1}


def test_limpeza_remove_so_as_importadas_e_preserva_o_resto(banco):
    cenario_limpeza(banco)
    preservar = {t: md5(banco, t) for t in ('public.movimento_financeiro', 'public.conta_bancaria', 'public.item_despesa',
                                             'public.receita_realizada', 'financeiro.cartao_vinculado')}
    previsoes = sql(banco, "select id from public.lancamento_agregado where is_recorrente and not coalesce(is_importado, false) order by id")
    p = rpc(banco, 'previa_limpeza_importacoes', PESSOAL, CARTAO, None)
    chave = str(uuid.uuid4())
    r = limpar(banco, p, mes=None, chave=chave)
    assert (r['compras_removidas'], r['creditos_removidos']) == (5, 1)
    restantes = sorted(x['descricao'] for x in sql(banco, 'select descricao from public.lancamento_agregado where cartao_id = %s '
                                                         'and not coalesce(is_recorrente, false)', (CARTAO,)))
    assert 'Compra manual' in restantes and 'Importada pelo Flask' in restantes
    assert not {'SUPERMERCADO', 'FARMACIA', 'TV LOJA (1/3)'} & set(restantes)
    assert sql(banco, "select id from public.lancamento_agregado where is_recorrente and not coalesce(is_importado, false) "
                      "order by id") == previsoes
    assert sql(banco, 'select count(*) n from financeiro.credito_fatura')[0]['n'] == 0
    assert {t: md5(banco, t) for t in preservar} == preservar
    # auditoria: as linhas removidas inteiras na operacao; repetir a chave devolve o mesmo resultado sem remover de novo
    fotos = sql(banco, "select resultado -> 'fotos' f from financeiro.operacao_cartao where chave = %s", (chave,))[0]['f']
    assert (len(fotos['compras']), len(fotos['creditos'])) == (5, 1)
    assert limpar(banco, p, mes=None, chave=chave)['repetida'] is True
    assert rpc(banco, 'previa_limpeza_importacoes', PESSOAL, CARTAO, None)['executavel'] is False  # nada mais a limpar
    # e a reconstrucao: o mesmo arquivo importa de novo, com a Categoria de Despesa que a compra tinha (a foto da limpeza)
    sql(banco, 'update public.item_despesa set categoria_id = null where id = %s', (CARTAO,))  # sem fallback do contrato
    volta = previa(banco, linha(1, 'SUPERMERCADO', '50.00', categoria=None, final='1111'),
                   linha(5, 'OUTRA LOJA', '12.00', categoria=None))['linhas']
    assert [(x['categoria_id'], x['categoria_origem']) for x in volta] == [(ASSINATURAS, 'reconstrucao'), (None, 'sem_sugestao')]
    assert importar(banco, linha(1, 'SUPERMERCADO', '50.00', categoria=None, final='1111'))['inseridos'] == 1


def test_fatura_paga_protege_e_interrompe(banco):
    cenario_limpeza(banco)
    pagar(banco, CARTAO, MES)
    p = rpc(banco, 'previa_limpeza_importacoes', PESSOAL, CARTAO, None)
    assert {x['motivo'] for x in p['protegidos']} == {'Fatura paga'} and p['executavel'] is False
    antes = md5_compras(banco)
    erro = falha(banco, 'limpar_importacoes_cartao', PESSOAL, CARTAO, None, p['hash'], str(uuid.uuid4()))
    assert erro[0] == 'P0001' and 'Nada foi removido' in erro[1]
    assert md5_compras(banco) == antes
    # so as faturas abertas (junho e julho, das parcelas futuras) podem ser limpas
    junho = rpc(banco, 'previa_limpeza_importacoes', PESSOAL, CARTAO, '2029-06-01')
    assert ([x['descricao'] for x in junho['compras_elegiveis']], junho['executavel']) == (['TV LOJA (2/3)'], True)


def test_previa_mudou_perfil_e_acesso(banco):
    cenario_limpeza(banco)
    p = limpeza(banco)
    importar(banco, linha(9, 'NOVA COMPRA', '5.00'))
    assert falha(banco, 'limpar_importacoes_cartao', PESSOAL, CARTAO, MES, p['hash'], str(uuid.uuid4()))[0] == '40001'
    assert falha(banco, 'previa_limpeza_importacoes', PESSOAL, CARTAO, MES, usuario=USUARIO_B)[0] == '42501'
    assert falha(banco, 'limpar_importacoes_cartao', PESSOAL, CARTAO, MES, p['hash'], str(uuid.uuid4()), usuario=USUARIO_B)[0] == '42501'
    assert falha(banco, 'limpar_importacoes_cartao', ID['PERFIL_B'], CARTAO_B, MES, 'x', str(uuid.uuid4()), usuario=USUARIO_B)[1] == \
        'A limpeza das importacoes e so do perfil Pessoal'


def test_limpeza_interrompida_volta_tudo(banco):
    cenario_limpeza(banco)
    sql(banco, """create function public.zz_falha() returns trigger language plpgsql as $$
                  begin if old.descricao = 'FARMACIA' then raise exception 'falha simulada'; end if; return old; end $$""")
    sql(banco, 'create trigger zz_falha before delete on public.lancamento_agregado for each row execute function public.zz_falha()')
    antes = (md5_compras(banco), md5(banco, 'financeiro.credito_fatura'), md5(banco, 'public.conta'))
    p = limpeza(banco)
    assert 'falha simulada' in falha(banco, 'limpar_importacoes_cartao', PESSOAL, CARTAO, MES, p['hash'], str(uuid.uuid4()))[1]
    assert (md5_compras(banco), md5(banco, 'financeiro.credito_fatura'), md5(banco, 'public.conta')) == antes
    assert sql(banco, "select count(*) n from financeiro.operacao_cartao where operacao = 'limpar_importacoes'")[0]['n'] == 0


# ---------------------------------------------------------------------------------------------------------------------
# 4. Acesso cruzado, funcoes internas e reversao da migration
# ---------------------------------------------------------------------------------------------------------------------

def test_acesso_cruzado_entre_perfis_e_contratos(banco):
    cv = cartao(banco, '1111')
    assert falha(banco, 'cartoes_vinculados', PESSOAL, CARTAO, usuario=USUARIO_B)[0] == '42501'
    assert falha(banco, 'salvar_cartao_vinculado', PESSOAL, CARTAO, None, {'nome': 'X', 'final': '5555', 'tipo': 'FISICO'}, None,
                 usuario=USUARIO_B)[0] == '42501'
    assert falha(banco, 'salvar_cartao_vinculado', PESSOAL, CARTAO_B, None, {'nome': 'X', 'final': '5555', 'tipo': 'FISICO'}, None)[0] == '42501'
    # o banco recusa a compra ligada a cartao de outro contrato e o cartao de contrato de outro perfil
    outro = sql(banco, "select id from public.item_despesa where tipo = 'Agregador' and id <> %s and perfil_financeiro_id = %s limit 1",
                (CARTAO, PESSOAL))
    if outro:
        with pytest.raises(psycopg2.Error, match='nao e deste contrato'):
            sql(banco, 'update public.lancamento_agregado set cartao_id = %s, cartao_vinculado_id = %s '
                       'where id = (select min(id) from public.lancamento_agregado)', (outro[0]['id'], cv['id']))
    with pytest.raises(psycopg2.Error, match='outro perfil'):
        sql(banco, "insert into financeiro.cartao_vinculado (perfil_financeiro_id, contrato_id, nome, final, tipo) "
                   "values (%s, %s, 'X', '6666', 'FISICO')", (PESSOAL, CARTAO_B))
    f = sql(banco, "select has_table_privilege('authenticated', 'financeiro.cartao_vinculado', 'select') t, "
                   "has_function_privilege('authenticated', 'financeiro.fatura_por_cartao(integer, integer, date)', 'execute') f, "
                   "(select relforcerowsecurity from pg_class where oid = 'financeiro.cartao_vinculado'::regclass) rls")[0]
    assert (f['t'], f['f'], f['rls']) == (False, False, True)


def executar(dsn, arquivo):
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(arquivo.read_text(encoding='utf-8'))
    finally:
        conn.close()


def test_reversao_recusada_com_cartao_e_reaplicacao(banco):
    antes = md5_compras(banco)
    executar(banco, REVERSAO)
    assert sql(banco, "select to_regclass('financeiro.cartao_vinculado') t")[0]['t'] is None
    executar(banco, MIGRATION)
    assert md5_compras(banco) == antes
    cartao(banco, '1111')
    with pytest.raises(psycopg2.Error, match='cartoes vinculados cadastrados'):
        executar(banco, REVERSAO)


def test_procedimento_por_script_previa_e_execucao_confirmada(banco, tmp_path):
    import json
    import subprocess
    import sys
    cenario_limpeza(banco)
    script = Path(__file__).resolve().parent.parent / 'scripts' / 'limpeza_importacoes_cartao.py'
    rodar = lambda *a: subprocess.run([sys.executable, str(script), *a, '--dsn', banco, '--cartao', str(CARTAO),  # noqa: E731
                                       '--competencia', '2029-05'], capture_output=True, text=True)
    antes = md5_compras(banco)
    r = rodar('previa', '--saida', str(tmp_path / 'previa.json'))
    assert r.returncode == 0 and 'Executavel: sim' in r.stdout, r.stdout + r.stderr
    assert md5_compras(banco) == antes
    p = json.loads((tmp_path / 'previa.json').read_text(encoding='utf-8'))
    assert 'Execucao recusada' in rodar('executar', '--hash', p['hash']).stderr  # sem a confirmacao literal
    assert md5_compras(banco) == antes
    r = rodar('executar', '--hash', p['hash'], '--confirmo', 'LIMPAR IMPORTACOES')
    assert r.returncode == 0 and json.loads(r.stdout)['compras_removidas'] == 3, r.stdout + r.stderr  # maio: 2 + a 1/3
