"""
Testes FIN-MVP-MOB-02 (P13) — projecoes dinamicas de veiculos (migration 20261220090000), em cluster PostgreSQL local
descartavel e com dados ficticios.

O cadastro de itens por veiculo (tipo, nome, categoria, valor, frequencia, inicio, termino, situacao) gera as ocorrencias
em despesa_prevista pelo mesmo motor do FIN-MVP-MOB-01 (obrigacao + periodo): periodicidades, termino, mudanca de
competencia, edicao e desativacao so no que ainda e PREVISTA, exclusao so sem historico, ids e vinculos preservados,
combustivel pela logica do veiculo (Flex, custo calculado, recorrencia), veiculos simulado, ativo e em uso paralelo,
abastecimentos, manutencao por km, escritor unico e isolamento. A conversao dos campos fixos e comparada com o gerador
anterior numa copia com a migration revertida (mesmas ocorrencias, mesmos ids) e a reversao recusa perder itens novos.
"""
import datetime as dt
import uuid

import pytest
from dateutil.relativedelta import relativedelta

from tests.test_supabase_cartoes import CARTAO, rpc
from tests.test_supabase_mobilidade_abastecimento import abastecer
from tests.test_supabase_mobilidade_escrita import (  # noqa: F401  (fixtures de modulo reaproveitadas)
    HOJE,
    MIGRATION_1220,
    PESSOAL,
    PERFIL_B,
    REGRA,
    REVERSAO_1220,
    VEICULO_1,
    VEICULO_2,
    banco,
    chave,
    cluster,
    erro,
)
from tests.test_supabase_mobilidade_integridade import (
    ATIVO,
    FLEX,
    SIMULADO,
    ativar,
    conta_bancaria,
    criar,
    dados_financeiros,
    despesas_do_mes,
    executar,
    pagar,
)
from tests.test_supabase_integracao_1123_1126 import resumo_tabelas
from tests.test_supabase_recorrencia import PG_BIN, USUARIO_B, atribuir, sql

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

MES = HOJE.replace(day=1)
FIM = MES + relativedelta(months=12)


def mes(n):
    return MES + relativedelta(months=n)


def salvar(dsn, veiculo, dados, perfil=PESSOAL, usuario=None):
    extra = {'usuario': usuario} if usuario else {}
    return rpc(dsn, 'salvar_projecao_veiculo', perfil, veiculo, dados, chave(), **extra)['projecao']


def item(dsn, veiculo, tipo='OUTRO', valor=100, frequencia='MENSAL', inicio=None, **extra):
    return salvar(dsn, veiculo, {'tipo': tipo, 'valor': valor, 'frequencia': frequencia,
                                 'data_inicio': (inicio or MES).isoformat(), **extra})


def editar(dsn, veiculo, projecao, **campos):
    return salvar(dsn, veiculo, {'id': projecao, **campos})


def alternar(dsn, projecao, ativo):
    return rpc(dsn, 'alternar_projecao_veiculo', PESSOAL, projecao, ativo)['projecao']


def excluir(dsn, projecao):
    return rpc(dsn, 'excluir_projecao_veiculo', PESSOAL, projecao)


def tela(dsn, veiculo, perfil=PESSOAL, **kw):
    return rpc(dsn, 'projecoes_veiculo_tela', perfil, veiculo, **kw)


def itens(dsn, veiculo):
    return {i['tipo'] if i['tipo'] in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO') else i['id']: i
            for i in tela(dsn, veiculo)['itens']}


def ocorrencias(dsn, veiculo, obrigacao):
    return sql(dsn, 'select * from public.despesa_prevista where origem_tipo = %s and origem_id = %s and obrigacao = %s '
                    'order by data_prevista, id', ('VEICULO', veiculo, obrigacao))


def obrigacao(p):
    return p['tipo'] if p['tipo'] in ('COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO') else f"PROJ:{p['id']}"


def previstas_do_veiculo(dsn, veiculo):
    return sql(dsn, 'select * from public.despesa_prevista where origem_tipo = %s and origem_id = %s order by id', ('VEICULO', veiculo))


def dica(e):
    return e.diag.message_hint


def confirmar(dsn, prevista, **dados):
    return rpc(dsn, 'confirmar_despesa_prevista', PESSOAL, prevista, dados)


def historico(dsn, projecao):
    return [h['acao'] for h in sql(dsn, 'select acao from financeiro.veiculo_projecao_historico where projecao_id = %s order by id', (projecao,))]


# =====================================================================================================================
# Cadastro
# =====================================================================================================================

def test_criar_projecao_personalizada(banco):
    v = criar(banco, SIMULADO)
    p = item(banco, v, 'OUTRO', 85.5, 'MENSAL', nome='Estacionamento do trabalho', categoria_id=None)
    assert p['nome'] == 'Estacionamento do trabalho' and p['valor'] == 85.5 and p['frequencia'] == 'MENSAL' and p['ativo']
    linhas = ocorrencias(banco, v, obrigacao(p))
    assert [o['data_prevista'] for o in linhas] == [mes(n) for n in range(12)]
    assert all(o['status'] == 'PREVISTA' and o['valor_previsto'] == 85.5 and o['categoria_id'] == p['categoria_id'] for o in linhas)
    # o rotulo da ocorrencia e o nome dado; a categoria padrao do tipo, quando nao informada
    md = linhas[0]['metadata']
    assert '"nome": "Estacionamento do trabalho"' in md and f'"projecao_id": {p["id"]}' in md
    assert p['categoria_nome']
    assert tela(banco, v)['itens'][-1]['proxima_ocorrencia'] == MES.isoformat()
    assert historico(banco, p['id']) == ['CRIACAO']


def test_editar_atualiza_so_as_previstas_e_preserva_ids(banco):
    v = criar(banco, SIMULADO)
    p = item(banco, v, 'PNEUS', 1200, 'SEMESTRAL', mes(1))
    antes = ocorrencias(banco, v, obrigacao(p))
    assert [o['data_prevista'] for o in antes] == [mes(1), mes(7)]
    e = editar(banco, v, p['id'], valor=1350, nome='Pneus dianteiros')
    depois = ocorrencias(banco, v, obrigacao(p))
    assert [o['id'] for o in depois] == [o['id'] for o in antes]
    assert all(o['valor_previsto'] == 1350 and '"nome": "Pneus dianteiros"' in o['metadata'] for o in depois)
    assert e['nome'] == 'Pneus dianteiros' and historico(banco, p['id']) == ['CRIACAO', 'EDICAO']
    # editar sem mudar nada nao grava historico
    editar(banco, v, p['id'], valor=1350)
    assert historico(banco, p['id']) == ['CRIACAO', 'EDICAO']
    with pytest.raises(psycopg2.Error, match='tipo não muda'):
        editar(banco, v, p['id'], tipo='REVISAO')


def test_desativar_e_reativar(banco):
    v = criar(banco, SIMULADO)
    p = item(banco, v, 'REVISAO', 900, 'TRIMESTRAL', mes(1))
    primeira = ocorrencias(banco, v, obrigacao(p))[0]
    confirmar(banco, primeira['id'])  # sem pagamento: so muda a situacao
    assert alternar(banco, p['id'], False)['ativo'] is False
    restantes = ocorrencias(banco, v, obrigacao(p))
    assert [(o['id'], o['status']) for o in restantes] == [(primeira['id'], 'CONFIRMADA')]
    assert tela(banco, v)['itens'][-1]['proxima_ocorrencia'] is None
    alternar(banco, p['id'], True)
    assert [o['data_prevista'] for o in ocorrencias(banco, v, obrigacao(p))] == [mes(1), mes(4), mes(7), mes(10)]
    assert ocorrencias(banco, v, obrigacao(p))[0]['id'] == primeira['id']
    assert historico(banco, p['id']) == ['CRIACAO', 'DESATIVACAO', 'ATIVACAO']


def test_excluir_sem_historico(banco):
    v = criar(banco, SIMULADO)
    p = item(banco, v, 'OUTRO', 40, 'SEMANAL', MES)
    assert itens(banco, v)[p['id']]['pode_excluir'] is True
    r = excluir(banco, p['id'])
    assert r['excluida'] and r['ocorrencias_removidas'] == len([d for d in range(0, 400, 7) if MES + dt.timedelta(days=d) < FIM])
    assert ocorrencias(banco, v, obrigacao(p)) == [] and p['id'] not in itens(banco, v)
    assert historico(banco, p['id']) == ['CRIACAO', 'EXCLUSAO']


def test_recusa_exclusao_indevida(banco):
    v = criar(banco, SIMULADO)
    p = item(banco, v, 'MANUTENCAO_CORRETIVA', 300, 'DATA', MES + dt.timedelta(days=20))
    rpc(banco, 'ignorar_despesa_prevista', PESSOAL, ocorrencias(banco, v, obrigacao(p))[0]['id'])
    e = erro(excluir, banco, p['id'])
    assert dica(e) == 'PROJECAO_PROTEGIDA' and 'desative' in str(e)
    assert itens(banco, v)[p['id']]['pode_excluir'] is False and ocorrencias(banco, v, obrigacao(p))[0]['status'] == 'IGNORADA'
    comb = itens(banco, v)['COMBUSTIVEL']
    assert dica(erro(excluir, banco, comb['id'])) == 'PROJECAO_PROTEGIDA' and comb['pode_excluir'] is False


def test_vinculo_ao_veiculo_e_ao_perfil(banco):
    v, w = criar(banco, SIMULADO), criar(banco, ATIVO)
    p = item(banco, v, 'OUTRO', 50)
    # item de outro veiculo, perfil sem acesso, perfil no Flask (escritor unico antes de tudo)
    assert dica(erro(editar, banco, w, p['id'], valor=60)) == 'NAO_ENCONTRADA'
    assert dica(erro(tela, banco, v, PERFIL_B, usuario=USUARIO_B)) == 'NAO_ENCONTRADA'
    assert erro(tela, banco, v, PESSOAL, usuario=USUARIO_B).pgcode == '42501'
    with pytest.raises(psycopg2.Error):
        salvar(banco, v, {'tipo': 'OUTRO', 'valor': 10, 'frequencia': 'MENSAL', 'data_inicio': MES.isoformat()}, PERFIL_B, USUARIO_B)
    assert dica(erro(rpc, banco, 'excluir_projecao_veiculo', PERFIL_B, p['id'], usuario=USUARIO_B)) == 'NAO_ENCONTRADA'
    assert sql(banco, 'select perfil_financeiro_id p, veiculo_id v from financeiro.veiculo_projecao where id = %s', (p['id'],)) == [{'p': PESSOAL, 'v': v}]
    # perfil no Flask: o escritor unico recusa antes de tudo, sem gravar
    atribuir(banco, 'PESSOAL', 'FLASK')
    antes = resumo_tabelas(banco), sql(banco, 'select * from financeiro.veiculo_projecao order by id')
    for funcao, args in (('salvar_projecao_veiculo', (v, {'tipo': 'OUTRO', 'valor': 10, 'frequencia': 'MENSAL', 'data_inicio': MES.isoformat()}, chave())),
                         ('salvar_projecao_veiculo', (v, {'id': p['id'], 'valor': 60}, chave())),
                         ('alternar_projecao_veiculo', (p['id'], False)), ('excluir_projecao_veiculo', (p['id'],))):
        assert dica(erro(rpc, banco, funcao, PESSOAL, *args)) == 'SISTEMA_FLASK', funcao
    assert (resumo_tabelas(banco), sql(banco, 'select * from financeiro.veiculo_projecao order by id')) == antes
    atribuir(banco, 'PESSOAL')


def test_validacoes(banco):
    v = criar(banco, SIMULADO)
    for dados, trecho in (({'valor': 10, 'frequencia': 'MENSAL', 'data_inicio': MES.isoformat()}, 'tipo'),
                          ({'tipo': 'OUTRO', 'valor': 0, 'frequencia': 'MENSAL', 'data_inicio': MES.isoformat()}, 'valor'),
                          ({'tipo': 'OUTRO', 'valor': 10, 'frequencia': 'QUINZENAL', 'data_inicio': MES.isoformat()}, 'periodicidade'),
                          ({'tipo': 'OUTRO', 'valor': 10, 'frequencia': 'MENSAL'}, 'início'),
                          ({'tipo': 'OUTRO', 'valor': 10, 'frequencia': 'MENSAL', 'data_inicio': mes(3).isoformat(),
                            'data_fim': mes(1).isoformat()}, 'término'),
                          ({'tipo': 'OUTRO', 'valor': 10, 'frequencia': 'MENSAL', 'data_inicio': MES.isoformat(), 'categoria_id': 999999}, 'Categoria'),
                          ({'tipo': 'IPVA', 'valor': 10, 'frequencia': 'MENSAL', 'data_inicio': MES.isoformat()}, 'anuais'),
                          ({'tipo': 'COMBUSTIVEL', 'valor': 10, 'frequencia': 'MENSAL', 'data_inicio': MES.isoformat()}, 'combustível já')):
        with pytest.raises(psycopg2.Error, match=trecho):
            salvar(banco, v, dados)
    assert len(tela(banco, v)['itens']) == 4  # combustivel, IPVA, seguro e licenciamento convertidos; nada novo
    # mes no formato do campo de mes da tela
    p = salvar(banco, v, {'tipo': 'OUTRO', 'valor': 10, 'frequencia': 'ANUAL', 'data_inicio': mes(2).strftime('%Y-%m')})
    assert p['data_inicio'] == mes(2).isoformat()


def test_repeticao_da_criacao_nao_duplica(banco):
    v = criar(banco, SIMULADO)
    k = chave()
    dados = {'tipo': 'OUTRO', 'valor': 70, 'frequencia': 'MENSAL', 'data_inicio': MES.isoformat()}
    a = rpc(banco, 'salvar_projecao_veiculo', PESSOAL, v, dados, k)
    b = rpc(banco, 'salvar_projecao_veiculo', PESSOAL, v, dados, k)
    assert b['repetida'] and b['projecao']['id'] == a['projecao']['id']
    assert sql(banco, "select count(*) n from financeiro.veiculo_projecao where veiculo_id = %s and tipo = 'OUTRO'", (v,))[0]['n'] == 1


# =====================================================================================================================
# Periodicidades
# =====================================================================================================================

def test_semanal(banco):
    v = criar(banco, SIMULADO)
    inicio = MES + dt.timedelta(days=2)
    p = item(banco, v, 'OUTRO', 25, 'SEMANAL', inicio)
    datas = [o['data_prevista'] for o in ocorrencias(banco, v, obrigacao(p))]
    esperado, d = [], inicio
    while d < FIM:
        esperado.append(d)
        d += dt.timedelta(days=7)
    assert datas == esperado
    assert itens(banco, v)[p['id']]['media_mensal'] == round(25 * 52 / 12, 2)


@pytest.mark.parametrize('frequencia,inicio,esperado,media', [
    ('MENSAL', 0, list(range(12)), 600),
    ('TRIMESTRAL', 1, [1, 4, 7, 10], 200),
    ('SEMESTRAL', 2, [2, 8], 100),
    ('ANUAL', 3, [3], 50),
])
def test_periodicidades_por_competencia(banco, frequencia, inicio, esperado, media):
    v = criar(banco, SIMULADO)
    p = item(banco, v, 'OUTRO', 600, frequencia, mes(inicio))
    linhas = ocorrencias(banco, v, obrigacao(p))
    assert [o['data_prevista'] for o in linhas] == [mes(n) for n in esperado]
    assert all(o['valor_previsto'] == 600 for o in linhas)  # o anual entra integral no mes de cobranca
    assert itens(banco, v)[p['id']]['media_mensal'] == media  # a media e so informativa


def test_inicio_no_passado_segue_a_cadencia(banco):
    v = criar(banco, SIMULADO)
    p = item(banco, v, 'OUTRO', 300, 'TRIMESTRAL', mes(-5))  # -5, -2, +1, +4 ...
    assert [o['data_prevista'] for o in ocorrencias(banco, v, obrigacao(p))] == [mes(1), mes(4), mes(7), mes(10)]


def test_data_programada(banco):
    v = criar(banco, SIMULADO)
    quando = mes(14) + dt.timedelta(days=9)  # fora da janela de 12 meses: e uma so, entra mesmo assim
    p = item(banco, v, 'MANUTENCAO_CORRETIVA', 2500, 'DATA', quando)
    assert [(o['data_prevista'], o['valor_previsto']) for o in ocorrencias(banco, v, obrigacao(p))] == [(quando, 2500)]
    assert itens(banco, v)[p['id']]['media_mensal'] == 0
    editar(banco, v, p['id'], data_inicio=(quando + dt.timedelta(days=5)).isoformat())
    linhas = ocorrencias(banco, v, obrigacao(p))
    assert len(linhas) == 1 and linhas[0]['data_prevista'] == quando + dt.timedelta(days=5)
    # depois de agir, nao volta em outra data
    confirmar(banco, linhas[0]['id'])
    editar(banco, v, p['id'], data_inicio=mes(20).isoformat())
    assert [o['status'] for o in ocorrencias(banco, v, obrigacao(p))] == ['CONFIRMADA']


def test_data_de_termino(banco):
    v = criar(banco, SIMULADO)
    p = item(banco, v, 'OUTRO', 80, 'MENSAL', MES, data_fim=mes(2).strftime('%Y-%m'))
    assert [o['data_prevista'] for o in ocorrencias(banco, v, obrigacao(p))] == [mes(0), mes(1), mes(2)]
    ids = [o['id'] for o in ocorrencias(banco, v, obrigacao(p))]
    editar(banco, v, p['id'], data_fim=mes(4).isoformat())
    assert [o['id'] for o in ocorrencias(banco, v, obrigacao(p))][:3] == ids and len(ocorrencias(banco, v, obrigacao(p))) == 5
    editar(banco, v, p['id'], data_fim=mes(1).isoformat())
    assert [o['id'] for o in ocorrencias(banco, v, obrigacao(p))] == ids[:2]
    editar(banco, v, p['id'], data_fim=None)
    assert len(ocorrencias(banco, v, obrigacao(p))) == 12


def test_mudanca_de_competencia(banco):
    v = criar(banco, {**SIMULADO, 'ipva_mes': mes(2).month, 'ipva_valor': 1200})
    ipva = itens(banco, v)['IPVA']
    antes = ocorrencias(banco, v, 'IPVA')
    assert [o['data_prevista'] for o in antes] == [mes(2)]
    editar(banco, v, ipva['id'], data_inicio=mes(3).strftime('%Y-%m'))
    depois = ocorrencias(banco, v, 'IPVA')
    assert [(o['id'], o['data_prevista']) for o in depois] == [(antes[0]['id'], mes(3))]  # mesmo id, reprogramado
    confirmar(banco, depois[0]['id'])
    editar(banco, v, ipva['id'], data_inicio=mes(4).strftime('%Y-%m'))
    final = ocorrencias(banco, v, 'IPVA')
    # o ano ja confirmado nao ganha outro IPVA; o confirmado fica como estava
    assert [(o['id'], o['status'], o['data_prevista']) for o in final if o['periodo_referencia'].year == mes(3).year] == \
        [(antes[0]['id'], 'CONFIRMADA', mes(3))]
    assert len({o['periodo_referencia'] for o in final}) == len(final)


def test_mudanca_de_frequencia_sem_repetir_periodo(banco):
    v = criar(banco, SIMULADO)
    p = item(banco, v, 'OUTRO', 100, 'MENSAL', MES)
    linhas = ocorrencias(banco, v, obrigacao(p))
    confirmar(banco, linhas[1]['id'])
    editar(banco, v, p['id'], frequencia='TRIMESTRAL', valor=300)
    final = ocorrencias(banco, v, obrigacao(p))
    assert linhas[1]['id'] in [o['id'] for o in final if o['status'] == 'CONFIRMADA']
    assert len({o['periodo_referencia'] for o in final}) == len(final)
    editar(banco, v, p['id'], frequencia='MENSAL', valor=100)
    final = ocorrencias(banco, v, obrigacao(p))
    assert len({o['periodo_referencia'] for o in final}) == len(final)
    assert sum(1 for o in final if o['data_prevista'] == mes(1)) == 1


# =====================================================================================================================
# Integridade
# =====================================================================================================================

def test_regerar_sem_duplicidade_e_com_os_mesmos_ids(banco):
    v = criar(banco, {**SIMULADO, 'ipva_mes': mes(2).month, 'ipva_valor': 1200})
    for tipo, freq, inicio in (('PNEUS', 'SEMESTRAL', 1), ('OUTRO', 'SEMANAL', 0), ('REVISAO', 'DATA', 5)):
        item(banco, v, tipo, 100, freq, mes(inicio) + (dt.timedelta(days=3) if freq != 'SEMESTRAL' else dt.timedelta()))
    antes = previstas_do_veiculo(banco, v)
    for _ in range(3):
        rpc(banco, 'gerar_projecoes_veiculo', PESSOAL, v, {'meses_futuros': 12})
    assert previstas_do_veiculo(banco, v) == antes  # nenhuma linha muda, nem a data de atualizacao
    repetidas = sql(banco, 'select obrigacao, periodo_referencia, count(*) n from public.despesa_prevista where origem_id = %s '
                           'group by 1, 2 having count(*) > 1', (v,))
    assert repetidas == []


def test_preserva_confirmadas_pagas_e_vinculos(banco):
    v = criar(banco, ATIVO)
    p = item(banco, v, 'OUTRO', 150, 'MENSAL', MES)
    linhas = ocorrencias(banco, v, obrigacao(p))
    conta = confirmar(banco, linhas[0]['id'], meio_pagamento='pix')['entidade_criada']['id']
    compra = confirmar(banco, linhas[1]['id'], meio_pagamento='cartao', cartao_id=CARTAO)['entidade_criada']['compra']['lancamentos'][0]
    pagar(banco, conta, conta_bancaria(banco))
    base = dados_financeiros(banco)
    contas_antes = sql(banco, 'select * from public.conta where id = %s', (conta,))
    for passo in (lambda: editar(banco, v, p['id'], valor=999, nome='Outro nome'),
                  lambda: editar(banco, v, p['id'], data_inicio=mes(3).isoformat()),
                  lambda: alternar(banco, p['id'], False),
                  lambda: alternar(banco, p['id'], True)):
        passo()
        atual = {o['id']: o for o in ocorrencias(banco, v, obrigacao(p))}
        assert atual[linhas[0]['id']]['conta_id'] == conta and atual[linhas[0]['id']]['valor_previsto'] == 150
        assert atual[linhas[1]['id']]['lancamento_id'] == compra and atual[linhas[1]['id']]['status'] == 'CONFIRMADA'
        assert dados_financeiros(banco) == base  # contas, compras, movimentos e saldos
    assert sql(banco, 'select * from public.conta where id = %s', (conta,)) == contas_antes
    # os meses ja confirmados nao ganham outra ocorrencia
    final = ocorrencias(banco, v, obrigacao(p))
    assert [o['data_prevista'] for o in final if o['status'] == 'PREVISTA'][0] == mes(3)
    assert dica(erro(excluir, banco, p['id'])) == 'PROJECAO_PROTEGIDA'


def test_ipva_sem_duplicidade_anual(banco):
    v = criar(banco, {**SIMULADO, 'ipva_mes': mes(2).month, 'ipva_valor': 1200})
    assert dica(erro(item, banco, v, 'IPVA', 900, 'ANUAL', mes(5))) == 'PROJECAO_REPETIDA'
    ipva = itens(banco, v)['IPVA']
    alternar(banco, ipva['id'], False)
    assert dica(erro(item, banco, v, 'IPVA', 900, 'ANUAL', mes(5))) == 'PROJECAO_REPETIDA'  # reative o existente
    alternar(banco, ipva['id'], True)
    assert len(ocorrencias(banco, v, 'IPVA')) == 1


def test_combustivel_sem_duplicidade_com_a_recorrencia(banco):
    v = criar(banco, ATIVO)
    item_id = ativar(banco, v)['recorrencia']['id']
    comb = itens(banco, v)['COMBUSTIVEL']
    assert comb['valor'] == 200 and comb['valor_segue_veiculo'] and tela(banco, v)['combustivel_coberto']
    assert all(o['status'] == 'SUPRIMIDA' for o in ocorrencias(banco, v, 'COMBUSTIVEL'))
    contas = sql(banco, 'select count(*) n from public.conta where item_despesa_id = %s', (item_id,))[0]['n']
    editar(banco, v, comb['id'], valor=320)
    assert sql(banco, 'select valor from public.item_despesa where id = %s', (item_id,))[0]['valor'] == 320
    assert sql(banco, 'select combustivel_valor_mensal c from public.veiculo where id = %s', (v,))[0]['c'] == 320
    assert sql(banco, 'select count(*) n from public.conta where item_despesa_id = %s', (item_id,))[0]['n'] == contas
    assert all(o['status'] == 'SUPRIMIDA' for o in ocorrencias(banco, v, 'COMBUSTIVEL'))  # nenhuma prevista volta a contar
    assert historico(banco, comb['id'])[-1] == 'EDICAO'
    # desativar o item nao mexe na recorrencia nem no que ja foi suprimido
    alternar(banco, comb['id'], False)
    assert sql(banco, 'select ativo from public.item_despesa where id = %s', (item_id,))[0]['ativo'] is True
    assert ocorrencias(banco, v, 'COMBUSTIVEL') and all(o['status'] == 'SUPRIMIDA' for o in ocorrencias(banco, v, 'COMBUSTIVEL'))


def test_valores_financeiros_nao_mudam(banco):
    v = criar(banco, ATIVO)
    base, painel = dados_financeiros(banco), despesas_do_mes(banco)
    p = item(banco, v, 'OUTRO', 100, 'MENSAL', mes(1))
    editar(banco, v, p['id'], valor=110)
    alternar(banco, p['id'], False)
    excluir(banco, p['id'])
    assert dados_financeiros(banco) == base and despesas_do_mes(banco) == painel


def test_isolamento_por_perfil(banco):
    v = criar(banco, SIMULADO)
    item(banco, v, 'OUTRO', 10)
    vb = rpc(banco, 'criar_veiculo', PERFIL_B, VEICULO_2, chave(), usuario=USUARIO_B)['veiculo_id']
    assert [i['tipo'] for i in tela(banco, vb, PERFIL_B, usuario=USUARIO_B)['itens']] == ['COMBUSTIVEL']
    assert dica(erro(tela, banco, vb)) == 'NAO_ENCONTRADA'


# =====================================================================================================================
# Mobilidade
# =====================================================================================================================

def test_flex_com_custo_calculado(banco):
    v = criar(banco, FLEX)
    comb = itens(banco, v)['COMBUSTIVEL']
    assert comb['valor'] == 600 and comb['custo_calculado']  # 1000 km / 10 km/L x R$ 6
    assert dica(erro(editar, banco, v, comb['id'], valor=500)) == 'CUSTO_CALCULADO'
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'custo_combustivel_modo': 'MANUAL'})
    editar(banco, v, comb['id'], valor=450)
    assert {o['valor_previsto'] for o in ocorrencias(banco, v, 'COMBUSTIVEL')} == {450}
    assert sql(banco, 'select combustivel, combustivel_referencia from public.veiculo where id = %s', (v,)) == [{'combustivel': 'flex', 'combustivel_referencia': 'gasolina'}]


def test_combustivel_unico_e_desativacao(banco):
    v = criar(banco, SIMULADO)
    comb = itens(banco, v)['COMBUSTIVEL']
    assert comb['valor'] == 600 and comb['frequencia'] == 'MENSAL'
    ids = [o['id'] for o in ocorrencias(banco, v, 'COMBUSTIVEL')]
    alternar(banco, comb['id'], False)
    assert ocorrencias(banco, v, 'COMBUSTIVEL') == []
    lido = rpc(banco, 'veiculos_tela', PESSOAL, v)
    assert lido['resumo_mensal_estimado']['combustivel_mensal'] == 0 and lido['projecoes']
    alternar(banco, comb['id'], True)
    assert len(ocorrencias(banco, v, 'COMBUSTIVEL')) == len(ids)


def test_simulado_e_ativo_no_dashboard(banco):
    base = despesas_do_mes(banco)
    s = criar(banco, SIMULADO)
    item(banco, s, 'OUTRO', 100, 'MENSAL', MES)
    assert despesas_do_mes(banco) == base  # simulacao: so nas telas de Mobilidade
    a = criar(banco, {**ATIVO, 'combustivel_valor_mensal': None})
    item(banco, a, 'OUTRO', 100, 'MENSAL', MES)
    saidas, previstas = despesas_do_mes(banco)
    assert previstas == base[1] + 100 and saidas == base[0] + 100


def test_veiculos_em_uso_paralelo_independentes(banco):
    v = criar(banco, {**ATIVO, 'em_uso_paralelo': True})
    w = criar(banco, {**ATIVO, 'nome': 'Segundo (ficticio)'})
    antes_w = previstas_do_veiculo(banco, w)
    item(banco, v, 'PNEUS', 800, 'ANUAL', mes(2))
    alternar(banco, itens(banco, v)['COMBUSTIVEL']['id'], False)
    assert previstas_do_veiculo(banco, w) == antes_w
    assert [i['tipo'] for i in tela(banco, w)['itens']] == ['COMBUSTIVEL']


def test_abastecimento_nao_mexe_nas_projecoes(banco):
    v = criar(banco, ATIVO)
    item(banco, v, 'OUTRO', 50)
    antes = previstas_do_veiculo(banco, v)
    itens_antes = sql(banco, 'select * from financeiro.veiculo_projecao where veiculo_id = %s order by id', (v,))
    abastecer(banco, v)
    assert previstas_do_veiculo(banco, v) == antes
    assert sql(banco, 'select * from financeiro.veiculo_projecao where veiculo_id = %s order by id', (v,)) == itens_antes
    assert rpc(banco, 'veiculos_tela', PESSOAL, v)['km_real'] == 10000


def test_manutencao_por_km_sem_duas_obrigacoes(banco):
    v = criar(banco, ATIVO)
    rpc(banco, 'criar_regra_km_veiculo', PESSOAL, v, REGRA, chave())  # troca de oleo: categoria de manutencao
    t = tela(banco, v)
    assert [r['tipo_evento'] for r in t['regras_km']] == ['TROCA_OLEO']
    e = erro(item, banco, v, 'MANUTENCAO_PREVENTIVA', 300, 'SEMESTRAL', mes(1))
    assert dica(e) == 'PROJECAO_KM_EXISTENTE'
    p = item(banco, v, 'MANUTENCAO_PREVENTIVA', 300, 'SEMESTRAL', mes(1), confirmar_km=True)
    assert item(banco, v, 'PNEUS', 1000, 'ANUAL', mes(2))  # outro servico: sem aviso
    # adiar a ocorrencia do item com ajuste de ciclo nao abre ciclo por km para ela
    o = ocorrencias(banco, v, obrigacao(p))[0]
    rpc(banco, 'adiar_despesa_prevista', PESSOAL, o['id'], {'nova_data': mes(2).isoformat(), 'ajustar_ciclo': True})
    assert sql(banco, 'select count(*) n from public.veiculo_ciclo_manutencao where veiculo_id = %s', (v,))[0]['n'] == 0
    assert ocorrencias(banco, v, obrigacao(p))[0]['status'] == 'ADIADA'


# =====================================================================================================================
# Campos antigos (formulario do Flask ou tela anterior) e leitura de transicao
# =====================================================================================================================

def test_campos_antigos_gravam_nos_itens(banco):
    v = criar(banco, VEICULO_1)
    ipva = itens(banco, v)['IPVA']
    ids = [o['id'] for o in ocorrencias(banco, v, 'IPVA')]
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'ipva_valor': 1500})
    assert itens(banco, v)['IPVA']['valor'] == 1500 and [o['id'] for o in ocorrencias(banco, v, 'IPVA')] == ids
    assert historico(banco, ipva['id'])[-1] == 'EDICAO'
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'licenciamento_valor': None})
    assert itens(banco, v)['LICENCIAMENTO']['ativo'] is False and ocorrencias(banco, v, 'LICENCIAMENTO') == []
    # o item mudou de periodicidade na lista: o campo antigo nao sobrescreve
    seguro = itens(banco, v)['SEGURO']
    editar(banco, v, seguro['id'], frequencia='MENSAL', valor=200, data_inicio=MES.isoformat())
    assert sql(banco, 'select seguro_valor from public.veiculo where id = %s', (v,))[0]['seguro_valor'] is None  # espelho: fora do formato antigo
    assert dica(erro(rpc, banco, 'editar_veiculo', PESSOAL, v, {'seguro_valor': 2400, 'seguro_mes': 3})) == 'PROJECAO_DINAMICA'
    rpc(banco, 'editar_veiculo', PESSOAL, v, {'nome': 'Renomeado (ficticio)', 'seguro_valor': None})  # sem mudanca: aceito
    assert itens(banco, v)['SEGURO']['frequencia'] == 'MENSAL'


def test_espelho_das_colunas_antigas(banco):
    v = criar(banco, VEICULO_1)
    ipva = itens(banco, v)['IPVA']
    editar(banco, v, ipva['id'], valor=1300, data_inicio=mes(4).strftime('%Y-%m'))
    assert sql(banco, 'select ipva_valor, ipva_mes from public.veiculo where id = %s', (v,)) == [{'ipva_valor': 1300, 'ipva_mes': mes(4).month}]
    alternar(banco, ipva['id'], False)
    assert sql(banco, 'select ipva_valor from public.veiculo where id = %s', (v,))[0]['ipva_valor'] is None
    lido = rpc(banco, 'veiculos_tela', PESSOAL, v)
    assert lido['ipva']['valor'] is None and 'projecoes' not in lido  # ainda no formato antigo: responde como antes


def test_leitura_com_itens_novos(banco):
    v = criar(banco, VEICULO_1)
    antes = rpc(banco, 'veiculos_tela', PESSOAL, v)
    assert 'projecoes' not in antes
    item(banco, v, 'PNEUS', 1200, 'SEMESTRAL', mes(1))
    item(banco, v, 'OUTRO', 30, 'MENSAL', MES)
    lido = rpc(banco, 'veiculos_tela', PESSOAL, v)
    r = lido['resumo_mensal_estimado']
    assert r['combustivel_mensal'] == 600 and r['ipva_mensal_diluido'] == 100 and r['seguro_mensal_diluido'] == 200
    assert r['licenciamento_mensal_diluido'] == 15 and r['manutencao_mensal_media'] == 200 and r['outros_custos_mensais'] == 30
    assert lido['total_mensal_estimado'] == antes['total_mensal_estimado'] + 230
    assert [p['tipo'] for p in lido['projecoes']] == ['COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO', 'PNEUS', 'OUTRO']
    t = tela(banco, v)
    assert t['totais']['media_mensal'] == lido['total_mensal_estimado']


def test_excluir_veiculo_leva_os_itens_e_guarda_o_historico(banco):
    v = criar(banco, SIMULADO)
    p = item(banco, v, 'OUTRO', 10)
    rpc(banco, 'excluir_veiculo', PESSOAL, v)
    assert sql(banco, 'select count(*) n from financeiro.veiculo_projecao where veiculo_id = %s', (v,))[0]['n'] == 0
    assert historico(banco, p['id']) == ['CRIACAO', 'EXCLUSAO']


# =====================================================================================================================
# Conversao (cópia com a migration revertida = antes) e reversao
# =====================================================================================================================

def _clonar(dsn):
    base, nome = dsn.rsplit('/', 1)
    novo = f'{nome}_c{uuid.uuid4().hex[:6]}'
    conn = psycopg2.connect(f'{base}/template1')
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'create database {novo} template {nome}')
    conn.close()
    return f'{base}/{novo}'


def _cenario_antigo(dsn):
    """Veiculos e acoes feitos com as funcoes anteriores (migration revertida)."""
    executar(dsn, REVERSAO_1220)
    s = criar(dsn, VEICULO_1)
    a = criar(dsn, {**ATIVO, 'ipva_mes': mes(1).month, 'ipva_valor': 800, 'seguro_mes': mes(5).month, 'seguro_valor': 1800})
    ipva = sql(dsn, "select id from public.despesa_prevista where origem_id = %s and obrigacao = 'IPVA'", (a,))[0]['id']
    confirmar(dsn, ipva, meio_pagamento='pix')
    comb = sql(dsn, "select id from public.despesa_prevista where origem_id = %s and obrigacao = 'COMBUSTIVEL' order by data_prevista", (a,))
    rpc(dsn, 'adiar_despesa_prevista', PESSOAL, comb[2]['id'], {'nova_data': mes(4).isoformat()})
    rpc(dsn, 'ignorar_despesa_prevista', PESSOAL, comb[3]['id'])
    return s, a


def _retrato(dsn):
    return {'previstas': sql(dsn, 'select * from public.despesa_prevista order by id'),
            'veiculos': sql(dsn, 'select * from public.veiculo order by id'),
            'financeiro': dados_financeiros(dsn)}


def _sem_hora(linhas):
    return [{k: v for k, v in x.items() if k not in ('criado_em', 'atualizado_em')} for x in linhas]


def test_conversao_produz_as_mesmas_ocorrencias(banco):
    s, a = _cenario_antigo(banco)
    for v in (s, a):
        rpc(banco, 'gerar_projecoes_veiculo', PESSOAL, v, {})
    antes = _retrato(banco)
    tela_antes = rpc(banco, 'veiculos_tela', PESSOAL, None)
    executar(banco, MIGRATION_1220)
    assert _retrato(banco) == antes  # a conversao so cria os itens
    assert rpc(banco, 'veiculos_tela', PESSOAL, None) == tela_antes  # leitura de transicao: igual
    itens_s, itens_a = itens(banco, s), itens(banco, a)
    assert sorted(itens_s) == ['COMBUSTIVEL', 'IPVA', 'LICENCIAMENTO', 'SEGURO'] and sorted(itens_a) == ['COMBUSTIVEL', 'IPVA', 'SEGURO']
    assert itens_s['IPVA']['valor'] == 1200 and itens_s['SEGURO']['valor'] == 2400 and itens_s['LICENCIAMENTO']['valor'] == 180
    assert all(i['frequencia'] == 'ANUAL' for k, i in itens_s.items() if k != 'COMBUSTIVEL')
    assert sql(banco, "select count(*) n from financeiro.veiculo_projecao_historico where acao = 'CONVERSAO'")[0]['n'] == 7
    # o gerador novo, sobre os itens convertidos, produz exatamente as mesmas ocorrencias (mesmos ids, sem atualizar nada)
    for v in (s, a):
        rpc(banco, 'gerar_projecoes_veiculo', PESSOAL, v, {})
    assert _retrato(banco) == antes


def test_conversao_equivale_ao_gerador_antigo_nas_edicoes(banco):
    s, a = _cenario_antigo(banco)
    novo = _clonar(banco)
    executar(novo, MIGRATION_1220)
    edicoes = [(s, {'ipva_valor': 1500, 'seguro_mes': mes(6).month}), (a, {'combustivel_valor_mensal': 260, 'ipva_mes': mes(2).month}),
               (s, {'licenciamento_valor': None}), (a, {'seguro_valor': 2000})]
    for v, dados in edicoes:
        rpc(banco, 'editar_veiculo', PESSOAL, v, dados)  # funcoes anteriores
        rpc(novo, 'editar_veiculo', PESSOAL, v, dados)   # campos antigos gravando nos itens
        assert _sem_hora(_retrato(novo)['previstas']) == _sem_hora(_retrato(banco)['previstas']), dados
    assert _retrato(novo)['financeiro'] == _retrato(banco)['financeiro']
    # pela lista de Projecoes, o mesmo resultado que pelo campo antigo
    outro = _clonar(novo)
    rpc(novo, 'editar_veiculo', PESSOAL, s, {'ipva_valor': 1700})
    editar(outro, s, itens(outro, s)['IPVA']['id'], valor=1700)
    assert _sem_hora(_retrato(outro)['previstas']) == _sem_hora(_retrato(novo)['previstas'])


def test_reversao_recusa_itens_novos_e_reaplicacao(banco):
    v = criar(banco, VEICULO_1)
    p = item(banco, v, 'PNEUS', 900, 'ANUAL', mes(2))
    assert 'formulario antigo nao representa' in str(erro(executar, banco, REVERSAO_1220))
    excluir(banco, p['id'])
    antes = _retrato(banco)
    executar(banco, REVERSAO_1220)
    assert sql(banco, "select to_regclass('financeiro.veiculo_projecao') is null r")[0]['r']
    assert _retrato(banco) == antes
    rpc(banco, 'gerar_projecoes_veiculo', PESSOAL, v, {})  # o gerador anterior produz o mesmo
    assert _sem_hora(_retrato(banco)['previstas']) == _sem_hora(antes['previstas'])
    executar(banco, MIGRATION_1220)
    assert sorted(itens(banco, v)) == ['COMBUSTIVEL', 'IPVA', 'LICENCIAMENTO', 'SEGURO']
    rpc(banco, 'gerar_projecoes_veiculo', PESSOAL, v, {})
    assert _sem_hora(_retrato(banco)['previstas']) == _sem_hora(antes['previstas'])


def test_veiculo_sem_itens_e_convertido_na_primeira_gravacao(banco):
    v = criar(banco, VEICULO_1)
    sql(banco, 'delete from financeiro.veiculo_projecao_historico')
    sql(banco, 'delete from financeiro.veiculo_projecao where veiculo_id = %s', (v,))  # como um veiculo gravado por outro caminho
    antes = previstas_do_veiculo(banco, v)
    t = tela(banco, v)
    assert [i['tipo'] for i in t['itens']] == ['COMBUSTIVEL', 'IPVA', 'SEGURO', 'LICENCIAMENTO'] and all(i['provisorio'] for i in t['itens'])
    rpc(banco, 'gerar_projecoes_veiculo', PESSOAL, v, {'meses_futuros': VEICULO_1['meses_futuros']})
    assert previstas_do_veiculo(banco, v) == antes
    assert not any(i.get('provisorio') for i in tela(banco, v)['itens'])


def test_funcoes_internas_e_de_tela(banco):
    for assinatura in ('mob_periodo_frequencia(text, date)', 'mob_converter_legado(integer, integer)',
                       'mob_planejar_projecao(integer, integer, financeiro.veiculo_projecao, date, numeric)',
                       'mob_dados_projecao(financeiro.veiculo_projecao, public.veiculo, jsonb)', 'mob_espelhar_legado(integer)'):
        for papel in ('anon', 'authenticated'):
            assert sql(banco, f"select has_function_privilege('{papel}', 'financeiro.{assinatura}', 'execute') p")[0]['p'] is False, (assinatura, papel)
    for assinatura in ('projecoes_veiculo_tela(integer, integer)', 'salvar_projecao_veiculo(integer, integer, jsonb, uuid)',
                       'alternar_projecao_veiculo(integer, integer, boolean)', 'excluir_projecao_veiculo(integer, integer)'):
        assert sql(banco, f"select has_function_privilege('anon', 'financeiro.{assinatura}', 'execute') p")[0]['p'] is False
        assert sql(banco, f"select has_function_privilege('authenticated', 'financeiro.{assinatura}', 'execute') p")[0]['p'] is True
        definer = sql(banco, "select p.prosecdef d, p.proconfig c from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                             "where n.nspname = 'financeiro' and p.proname = %s", (assinatura.split('(')[0],))[0]
        assert definer['d'] and definer['c'] == ['search_path=""']
    for tabela in ('veiculo_projecao', 'veiculo_projecao_historico'):
        r = sql(banco, "select relrowsecurity r, relforcerowsecurity f from pg_class where oid = %s::regclass", (f'financeiro.{tabela}',))[0]
        assert r['r'] and r['f']
        assert sql(banco, f"select has_table_privilege('authenticated', 'financeiro.{tabela}', 'select') p")[0]['p'] is False


def test_incorporacao_de_categoria_leva_os_itens(banco):
    """A incorporacao de categorias (FIN-CATEGORIAS-CONSOLIDACAO-01) descobre as chaves estrangeiras no catalogo: o item
    passa a apontar a categoria de destino, como as ocorrencias dele."""
    from tests.test_supabase_categorias_consolidacao import incorporar, nova_categoria
    from tests.test_supabase_categorias_recorrencias import gestor
    sql(banco, "select financeiro.definir_escritor_catalogo('NOVO', 'administrador de teste', 'cenario ficticio')")
    gestor(banco)  # o titular ficticio administra o catalogo
    v = criar(banco, SIMULADO)
    origem = nova_categoria(banco, 'Oficina do bairro (ficticia)')
    destino = sql(banco, "select id from public.categoria where codigo_sistema = 'MOB_MANUTENCAO'")[0]['id']
    p = item(banco, v, 'MANUTENCAO_CORRETIVA', 400, 'TRIMESTRAL', mes(1), categoria_id=origem)
    assert {o['categoria_id'] for o in ocorrencias(banco, v, obrigacao(p))} == {origem}
    incorporar(banco, origem, destino)
    assert sql(banco, 'select categoria_id from financeiro.veiculo_projecao where id = %s', (p['id'],))[0]['categoria_id'] == destino
    assert {o['categoria_id'] for o in ocorrencias(banco, v, obrigacao(p))} == {destino}
    editar(banco, v, p['id'], valor=420)  # o item segue gravando normalmente
    assert {(o['categoria_id'], o['valor_previsto']) for o in ocorrencias(banco, v, obrigacao(p))} == {(destino, 420)}
