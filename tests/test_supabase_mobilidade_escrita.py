"""
Testes FIN-MOBILIDADE-2 (FIN-BLOCO-A-1, A3) — escrita de Veiculos/Mobilidade no novo aplicativo (migration
20261127090000), em cluster PostgreSQL local descartavel e com dados ficticios.

Fidelidade: a MESMA sequencia (veiculos, edicao, conversao, projecoes, regra e manutencao por km, assinatura, caminho de
transporte por app, financiamento do veiculo, ativacao das tres modalidades, confirmar/adiar com ciclo/ignorar
previstas) e feita pelo PROPRIO Flask numa copia (perfil no Flask) e pelas funcoes novas noutra copia identica (perfil
no novo aplicativo); as tabelas sao comparadas linha a linha (fora carimbos de hora; metadata comparado como JSON).
Para comparar o financiamento, o roteiro do Flask contorna o D-MOB1 (variavel `veiculo` inexistente em
upsert_financiamento) so dentro do subprocesso de teste; o novo aplicativo corrige o defeito.
Tambem: escritor unico nos dois sentidos, isolamento, categorias sistemicas nunca criadas, exclusoes seguras,
idempotencia, ativacoes concorrentes, previa sem gravar, confirmacao no cartao e a reversao.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from dateutil.relativedelta import relativedelta

from backend.services.categoria_default import CATEGORIAS_SISTEMICAS_MOBILIDADE
from tests.test_supabase_cartoes import rpc
from tests.test_supabase_integracao_1123_1126 import resumo_tabelas, tabelas_alteradas
from tests.test_supabase_receitas_categorias_tela import _SCRIPT as SCRIPT_FLASK
from tests.test_supabase_receitas_categorias_tela import flask
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
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, PERFIL_B = ID['PESSOAL'], ID['PERFIL_B']
REVERSAO = ROOT / 'supabase' / 'reversao' / '20261127090000_remover_mobilidade_escrita.sql'
MIGRATION = ROOT / 'supabase' / 'migrations' / '20261127090000_financeiro_mobilidade_escrita.sql'
HOJE = dt.date.today()
M2, M3 = (HOJE + relativedelta(months=2)).month, (HOJE + relativedelta(months=3)).month
SEM_HORA = {'criado_em', 'atualizado_em', 'created_at', 'updated_at', 'km_estimado_ultimo_calculo_em', 'registrado_em'}
TABELAS = ('veiculo', 'despesa_prevista', 'veiculo_regra_manutencao_km', 'veiculo_ciclo_manutencao', 'veiculo_financiamento',
           'mobilidade_assinatura', 'mobilidade_cenario_ativo', 'despesa_prevista_acao_log', 'item_despesa', 'conta', 'categoria')

VEICULO_1 = {'nome': 'Carro integ (ficticio)', 'tipo': 'carro', 'combustivel': 'gasolina', 'autonomia_km_l': 12,
             'status': 'SIMULADO', 'combustivel_valor_mensal': 600, 'preco_medio_combustivel': 6, 'ipva_mes': M2,
             'ipva_valor': 1200, 'seguro_mes': M3, 'seguro_valor': 2400, 'licenciamento_mes': M2,
             'licenciamento_valor': 180, 'meses_futuros': 6}
VEICULO_2 = {'nome': 'Moto integ (ficticia)', 'tipo': 'moto', 'combustivel': 'gasolina', 'autonomia_km_l': 30,
             'status': 'ATIVO', 'data_inicio': HOJE.isoformat(), 'combustivel_valor_mensal': 200}
REGRA = {'tipo_evento': 'TROCA_OLEO', 'intervalo_km': 5000, 'custo_estimado': 300, 'meses_intervalo': 6}
ASSINATURA = {'nome': 'Carro por assinatura (ficticio)', 'valor_mensal': 2100}
CAMINHO = {'nome': 'App integ (ficticio)', 'km_mensal_estimado': 300, 'preco_medio_por_km': 2.5,
           'perfis': [{'nome': 'Trabalho', 'km_mensal': 100, 'preco_medio_por_km': 3}], 'corridas_mes': 20, 'meses_futuros': 6}
FINANCIAMENTOS = [{'valor_bem': 30000, 'entrada': 5000, 'numero_parcelas': 24, 'taxa_juros_mensal': 1.5, 'iof_percentual': 3},
                  {'valor_bem': 30000, 'entrada': 6000, 'numero_parcelas': 30, 'taxa_juros_mensal': 1.6, 'iof_percentual': 3}]


def chave():
    return str(uuid.uuid4())


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


def semear_categorias_mobilidade(dsn):
    """As 10 categorias sistemicas MOB_* como o Flask as cria (categoria_default.py), nas duas copias."""
    for codigo, d in CATEGORIAS_SISTEMICAS_MOBILIDADE.items():
        sql(dsn, "insert into public.categoria (nome, descricao, cor, icone, ativo, sistemica, codigo_sistema, modulo_origem, "
                 "bloquear_edicao, bloquear_exclusao) values (%s, %s, %s, %s, true, true, %s, 'mobilidade', true, true)",
            (d['nome'], d.get('descricao'), d.get('cor'), d.get('icone'), codigo))


@pytest.fixture
def banco(cluster):  # noqa: F811
    """Copia com as categorias MOB_*, Pessoal e Perfil B no novo aplicativo; recorrencias semeadas inativas."""
    dsn = copiar(cluster)
    semear_categorias_mobilidade(dsn)
    sql(dsn, "update public.item_despesa set ativo = false where tipo is distinct from 'Agregador'")
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    return dsn


def flask_mob(dsn, passos, perfil=PESSOAL):
    """flask() do teste de Receitas/Categorias com o contorno do D-MOB1 (so neste subprocesso de teste)."""
    preludio = ('import types, backend.services.veiculo_financiamento_service as _vfs\n'
                f'_vfs.veiculo = types.SimpleNamespace(perfil_financeiro_id={perfil})\n')
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', preludio + SCRIPT_FLASK, json.dumps(passos)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return {nome: (status, corpo) for nome, status, corpo in json.loads(linha[len('FLASK_JSON '):]) if nome}


def tabelas(dsn):
    saida = {}
    for tabela in TABELAS:
        linhas = sql(dsn, f'select * from public.{tabela} order by id')
        normal = []
        for linha in linhas:
            linha = {k: v for k, v in linha.items() if k not in SEM_HORA}
            for campo in ('metadata', 'metadata_json'):
                if isinstance(linha.get(campo), str):
                    try:
                        linha[campo] = _arredondar(json.loads(linha[campo]))
                    except ValueError:
                        pass
            normal.append(linha)
        saida[tabela] = normal
    return saida


def _arredondar(valor):
    if isinstance(valor, float):
        return round(valor, 6)
    if isinstance(valor, dict):
        return {k: _arredondar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_arredondar(v) for v in valor]
    return valor


def prevista(dsn, origem_tipo, origem_id, tipo_evento):
    return sql(dsn, "select id from public.despesa_prevista where origem_tipo = %s and origem_id = %s and status = 'PREVISTA' "
                    "and metadata::jsonb ->> 'tipo_evento' = %s order by data_prevista, id limit 1",
               (origem_tipo, origem_id, tipo_evento))[0]['id']


def acoes_previstas(dsn, v1):
    """Ids logicos das previstas da fase 2 (os mesmos nas duas copias)."""
    return {'combustivel': prevista(dsn, 'VEICULO', v1, 'COMBUSTIVEL'), 'oleo': prevista(dsn, 'VEICULO', v1, 'TROCA_OLEO'),
            'seguro': prevista(dsn, 'VEICULO', v1, 'SEGURO')}


ADIAMENTO = {'nova_data': (HOJE + relativedelta(months=4)).isoformat(), 'ajustar_ciclo': True}
CONFIRMACAO = {'meio_pagamento': 'pix', 'observacao': 'abastecido'}


def pelo_flask(dsn):
    r = flask_mob(dsn, [
        ('perfil', PESSOAL),
        ('v1', 'post', '/api/veiculos', VEICULO_1),
        ('', 'put', '/api/veiculos/{v1}', {'combustivel_valor_mensal': 650, 'meses_futuros': 6}),
        ('', 'post', '/api/veiculos/{v1}/converter', {'data_inicio': HOJE.isoformat()}),
        ('', 'post', '/api/veiculos/{v1}/projecoes/gerar', {'meses_futuros': 12}),
        ('v2', 'post', '/api/veiculos', VEICULO_2),
        ('regra', 'post', '/api/veiculos/{v1}/regras-km', REGRA),
        ('', 'post', '/api/veiculos/{v1}/manutencoes-km/gerar', {'regra_id': '{regra}'}),
        ('ass', 'post', '/api/veiculos/mobilidade/assinaturas', ASSINATURA),
        ('', 'put', '/api/veiculos/mobilidade/assinaturas/{ass}', {'valor_mensal': 2200}),
        ('app', 'post', '/api/mobilidade-app', CAMINHO),
        ('', 'put', '/api/mobilidade-app/{app}', {**CAMINHO, 'km_mensal_estimado': 320}),
        ('', 'post', '/api/veiculos/{v2}/financiamento', FINANCIAMENTOS[0]),
        ('', 'post', '/api/veiculos/{v2}/financiamento', FINANCIAMENTOS[1]),
        ('previa_v', 'post', '/api/veiculos/mobilidade/previsualizar', {'tipo_modalidade': 'VEICULO', 'origem_id': '{v1}'}),
        ('previa_a', 'post', '/api/veiculos/mobilidade/previsualizar', {'tipo_modalidade': 'TRANSPORTE_APP', 'origem_id': '{app}'}),
        ('previa_s', 'post', '/api/veiculos/mobilidade/previsualizar', {'tipo_modalidade': 'ASSINATURA', 'origem_id': '{ass}'}),
        ('', 'post', '/api/veiculos/mobilidade/ativar', {'tipo_modalidade': 'VEICULO', 'origem_id': '{v1}', 'meio_pagamento': 'pix', 'confirmado': True}),
        ('', 'post', '/api/veiculos/mobilidade/ativar', {'tipo_modalidade': 'TRANSPORTE_APP', 'origem_id': '{app}', 'meio_pagamento': 'pix', 'confirmado': True}),
        ('', 'post', '/api/veiculos/mobilidade/ativar', {'tipo_modalidade': 'ASSINATURA', 'origem_id': '{ass}', 'meio_pagamento': 'boleto', 'confirmado': True}),
    ])
    assert all(s in (200, 201) for s, _ in r.values()), {k: v for k, v in r.items() if v[0] not in (200, 201)}
    ids = {'v1': r['v1'][1]['data']['id'], 'v2': r['v2'][1]['data']['id'], 'regra': r['regra'][1]['data']['id'],
           'ass': r['ass'][1]['data']['id'], 'app': r['app'][1]['data']['id']}
    alvo = acoes_previstas(dsn, ids['v1'])
    r2 = flask_mob(dsn, [('perfil', PESSOAL),
                         ('confirmar', 'post', f"/api/despesas-previstas/{alvo['combustivel']}/confirmar", CONFIRMACAO),
                         ('adiar', 'post', f"/api/despesas-previstas/{alvo['oleo']}/adiar", ADIAMENTO),
                         ('ignorar', 'post', f"/api/despesas-previstas/{alvo['seguro']}/ignorar", {})])
    assert all(s == 200 for s, _ in r2.values()), r2
    return ids, {k: r[k][1]['data'] for k in ('previa_v', 'previa_a', 'previa_s')}, r2


def pelo_novo(dsn):
    ids = {'v1': rpc(dsn, 'criar_veiculo', PESSOAL, VEICULO_1, chave())['veiculo_id']}
    rpc(dsn, 'editar_veiculo', PESSOAL, ids['v1'], {'combustivel_valor_mensal': 650, 'meses_futuros': 6})
    rpc(dsn, 'converter_veiculo', PESSOAL, ids['v1'], {'data_inicio': HOJE.isoformat()})
    rpc(dsn, 'gerar_projecoes_veiculo', PESSOAL, ids['v1'], {'meses_futuros': 12})
    ids['v2'] = rpc(dsn, 'criar_veiculo', PESSOAL, VEICULO_2, chave())['veiculo_id']
    ids['regra'] = rpc(dsn, 'criar_regra_km_veiculo', PESSOAL, ids['v1'], REGRA, chave())['regra_id']
    rpc(dsn, 'gerar_manutencao_km_veiculo', PESSOAL, ids['v1'], {'regra_id': ids['regra']})
    ids['ass'] = rpc(dsn, 'criar_assinatura_mobilidade', PESSOAL, ASSINATURA, chave())['assinatura_id']
    rpc(dsn, 'editar_assinatura_mobilidade', PESSOAL, ids['ass'], {'valor_mensal': 2200})
    ids['app'] = rpc(dsn, 'criar_caminho_app', PESSOAL, CAMINHO, chave())['id']
    rpc(dsn, 'editar_caminho_app', PESSOAL, ids['app'], {**CAMINHO, 'km_mensal_estimado': 320})
    for dados in FINANCIAMENTOS:
        rpc(dsn, 'salvar_financiamento_veiculo', PESSOAL, ids['v2'], dados)
    previas = {nome: chamar(dsn, USUARIO_A, 'select financeiro.previa_mobilidade(%s, %s::jsonb)',
                            (PESSOAL, json.dumps({'tipo_modalidade': tipo, 'origem_id': ids[k]})))
               for nome, tipo, k in (('previa_v', 'VEICULO', 'v1'), ('previa_a', 'TRANSPORTE_APP', 'app'),
                                     ('previa_s', 'ASSINATURA', 'ass'))}
    for tipo, k, meio in (('VEICULO', 'v1', 'pix'), ('TRANSPORTE_APP', 'app', 'pix'), ('ASSINATURA', 'ass', 'boleto')):
        rpc(dsn, 'ativar_mobilidade', PESSOAL, {'tipo_modalidade': tipo, 'origem_id': ids[k], 'meio_pagamento': meio,
                                                'confirmado': True}, chave())
    alvo = acoes_previstas(dsn, ids['v1'])
    r2 = {'confirmar': rpc(dsn, 'confirmar_despesa_prevista', PESSOAL, alvo['combustivel'], CONFIRMACAO),
          'adiar': rpc(dsn, 'adiar_despesa_prevista', PESSOAL, alvo['oleo'], ADIAMENTO),
          'ignorar': rpc(dsn, 'ignorar_despesa_prevista', PESSOAL, alvo['seguro'])}
    return ids, previas, r2


@pytest.fixture(scope='module')
def comparacao(cluster):  # noqa: F811
    no_flask, no_novo = copiar(cluster), copiar(cluster)
    for dsn in (no_flask, no_novo):
        semear_categorias_mobilidade(dsn)
        sql(dsn, "update public.item_despesa set ativo = false where tipo is distinct from 'Agregador'")
    atribuir(no_novo, 'PESSOAL')
    ids_f, previas_f, acoes_f = pelo_flask(no_flask)
    ids_n, previas_n, acoes_n = pelo_novo(no_novo)
    return {'flask': no_flask, 'novo': no_novo, 'ids': (ids_f, ids_n), 'previas': (previas_f, previas_n),
            'acoes': (acoes_f, acoes_n)}


# =====================================================================================================================
# Fidelidade
# =====================================================================================================================

def test_mesmas_linhas_que_o_flask(comparacao):
    assert comparacao['ids'][0] == comparacao['ids'][1]
    flask_t, novo_t = tabelas(comparacao['flask']), tabelas(comparacao['novo'])
    for tabela in TABELAS:
        assert len(novo_t[tabela]) == len(flask_t[tabela]), tabela
        for a, b in zip(flask_t[tabela], novo_t[tabela]):
            assert b == a, (tabela, {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)})


def test_cenario_ficticio_completo(comparacao):
    dsn = comparacao['novo']
    ids = comparacao['ids'][1]
    status = {r['tipo']: r['n'] for r in sql(dsn, "select metadata::jsonb ->> 'tipo_evento' tipo, count(*) n "
                                                   "from public.despesa_prevista where origem_tipo = 'VEICULO' and origem_id = %s "
                                                   "group by 1", (ids['v1'],))}
    assert status['COMBUSTIVEL'] == 12 and status['TROCA_OLEO'] == 2  # a adiada e a proxima do ciclo
    parcelas = sql(dsn, "select count(*) n, min(metadata::jsonb ->> 'financiamento_id') f from public.despesa_prevista "
                        "where origem_id = %s and metadata::jsonb ->> 'tipo_evento' = 'PARCELA_FINANCIAMENTO'", (ids['v2'],))[0]
    fin = sql(dsn, 'select id from public.veiculo_financiamento where veiculo_id = %s', (ids['v2'],))[0]['id']
    assert parcelas == {'n': 30, 'f': str(fin)}  # D-MOB1 corrigido: previstas ligadas ao financiamento
    cenarios = sql(dsn, 'select tipo_modalidade, status from public.mobilidade_cenario_ativo order by id')
    assert [c['status'] for c in cenarios] == ['INATIVO', 'INATIVO', 'ATIVO'] and cenarios[-1]['tipo_modalidade'] == 'ASSINATURA'
    recorrencias = sql(dsn, 'select origem_tipo, ativo from public.item_despesa where origem_tipo is not null order by id')
    assert recorrencias == [{'origem_tipo': 'VEICULO', 'ativo': False}, {'origem_tipo': 'TRANSPORTE_APP', 'ativo': False},
                            {'origem_tipo': 'ASSINATURA', 'ativo': True}]
    assert sql(dsn, "select count(*) n from public.despesa_prevista where origem_tipo = 'TRANSPORTE_APP' and status = 'SUPRIMIDA'")[0]['n'] == 6
    assert sql(dsn, 'select km_estimado_acumulado k from public.veiculo where id = %s', (ids['v1'],))[0]['k'] == Decimal('1300.00')


def test_respostas_iguais_ao_flask(comparacao):
    previas_f, previas_n = comparacao['previas']
    for nome in previas_f:
        assert previas_n[nome] == previas_f[nome], nome
    acoes_f, acoes_n = comparacao['acoes']
    assert acoes_n['confirmar']['despesa_prevista'] == acoes_f['confirmar'][1]['data']['despesa_prevista']
    criada_f, criada_n = acoes_f['confirmar'][1]['data']['entidade_criada'], acoes_n['confirmar']['entidade_criada']
    assert {k: criada_n[k] for k in ('tipo', 'id', 'descricao', 'valor', 'data_vencimento')} == \
        {k: criada_f[k] for k in ('tipo', 'id', 'descricao', 'valor', 'data_vencimento')}
    assert acoes_n['adiar']['ciclo'] == acoes_f['adiar'][1]['ciclo']
    for acao in ('adiar', 'ignorar'):
        f, n = acoes_f[acao][1]['data'], acoes_n[acao]['data']
        assert {k: v for k, v in n.items() if k not in SEM_HORA} == {k: v for k, v in f.items() if k not in SEM_HORA}, acao


# =====================================================================================================================
# Regras, correcoes e seguranca
# =====================================================================================================================

def test_escritor_unico_nos_dois_sentidos_e_isolamento(banco):
    v = rpc(banco, 'criar_veiculo', PESSOAL, VEICULO_2, chave())['veiculo_id']
    vb = rpc(banco, 'criar_veiculo', PERFIL_B, {**VEICULO_2, 'nome': 'Do perfil B'}, chave(), usuario=USUARIO_B)['veiculo_id']
    antes = resumo_tabelas(banco)
    # Perfil de outro titular e identificador de outro perfil.
    assert erro(rpc, banco, 'criar_veiculo', PESSOAL, VEICULO_2, chave(), usuario=USUARIO_B).pgcode == '42501'
    assert erro(rpc, banco, 'editar_veiculo', PESSOAL, vb, {'nome': 'x'}).diag.message_hint == 'NAO_ENCONTRADA'
    assert erro(rpc, banco, 'excluir_veiculo', PERFIL_B, v, usuario=USUARIO_B).diag.message_hint == 'NAO_ENCONTRADA'
    assert erro(rpc, banco, 'salvar_financiamento_veiculo', PESSOAL, vb, FINANCIAMENTOS[0]).pgcode == '22023'
    assert resumo_tabelas(banco) == antes
    # Perfil no Flask: o novo aplicativo recusa sem gravar.
    atribuir(banco, 'PESSOAL', 'FLASK')
    antes = resumo_tabelas(banco)
    for funcao, args in (('criar_veiculo', (VEICULO_2, chave())), ('editar_veiculo', (v, {'nome': 'x'})),
                         ('criar_caminho_app', (CAMINHO, chave())), ('excluir_veiculo', (v,)),
                         ('ativar_mobilidade', ({'tipo_modalidade': 'VEICULO', 'origem_id': v, 'confirmado': True}, chave()))):
        assert erro(rpc, banco, funcao, PESSOAL, *args).diag.message_hint == 'SISTEMA_FLASK', funcao
    assert resumo_tabelas(banco) == antes
    # Perfil no novo aplicativo: o Flask recusa (409) cada blueprint de Mobilidade, sem gravar.
    atribuir(banco, 'PESSOAL')
    antes = resumo_tabelas(banco)
    previa = sql(banco, "select id from public.despesa_prevista where origem_id = %s and status = 'PREVISTA' limit 1", (v,))[0]['id']
    r = flask(banco, [('perfil', PESSOAL), ('criar', 'post', '/api/veiculos', VEICULO_2),
                      ('editar', 'put', f'/api/veiculos/{v}', {'nome': 'x'}), ('app', 'post', '/api/mobilidade-app', CAMINHO),
                      ('adiar', 'post', f'/api/despesas-previstas/{previa}/adiar', {'nova_data': '2031-01-01'}),
                      ('ignorar', 'post', f'/api/despesas-previstas/{previa}/ignorar', {})])
    for nome, (status, corpo) in r.items():
        assert status == 409 and corpo['codigo'] == 'SISTEMA_NOVO', (nome, status, corpo)
    assert tabelas_alteradas(antes, resumo_tabelas(banco)) in ([], ['public.perfil_financeiro'])


def test_categorias_sistemicas_nunca_criadas_e_ausencia_recusa_sem_gravar(cluster):  # noqa: F811
    dsn = copiar(cluster)  # sem as categorias MOB_*
    atribuir(dsn, 'PESSOAL')
    antes = resumo_tabelas(dsn)
    e = erro(rpc, dsn, 'criar_veiculo', PESSOAL, VEICULO_2, chave())
    assert e.diag.message_hint == 'CATEGORIA_SISTEMICA_AUSENTE' and 'Combustível' in str(e)
    e = erro(chamar, dsn, USUARIO_A, 'select financeiro.previa_mobilidade(%s, %s::jsonb)',
             (PESSOAL, json.dumps({'tipo_modalidade': 'ASSINATURA', 'origem_id': 1})))
    assert e.pgcode == '22023'  # assinatura inexistente; nada lido grava
    assert resumo_tabelas(dsn) == antes
    # Com elas, nada do catalogo muda nas escritas (o Flask regravava metadados e criava as que faltavam).
    semear_categorias_mobilidade(dsn)
    catalogo = sql(dsn, 'select md5(string_agg(c::text, \'|\' order by id)) h from public.categoria c')
    v = rpc(dsn, 'criar_veiculo', PESSOAL, VEICULO_1, chave())['veiculo_id']
    rpc(dsn, 'criar_regra_km_veiculo', PESSOAL, v, REGRA, chave())
    assert sql(dsn, 'select md5(string_agg(c::text, \'|\' order by id)) h from public.categoria c') == catalogo
    codigos = {r['codigo_sistema'] for r in sql(dsn, 'select c.codigo_sistema from public.despesa_prevista d '
                                                     'join public.categoria c on c.id = d.categoria_id where d.origem_id = %s', (v,))}
    assert codigos == {'MOB_COMBUSTIVEL', 'MOB_TRIBUTOS_VEICULARES', 'MOB_SEGURO_VEICULAR'}


def test_exclusoes_seguras(banco):
    livre = rpc(banco, 'criar_veiculo', PESSOAL, VEICULO_2, chave())['veiculo_id']
    com_fin = rpc(banco, 'criar_veiculo', PESSOAL, {**VEICULO_2, 'nome': 'Com financiamento'}, chave())['veiculo_id']
    rpc(banco, 'salvar_financiamento_veiculo', PESSOAL, com_fin, FINANCIAMENTOS[0])
    com_hist = rpc(banco, 'criar_veiculo', PESSOAL, {**VEICULO_2, 'nome': 'Com historico'}, chave())['veiculo_id']
    rpc(banco, 'confirmar_despesa_prevista', PESSOAL, prevista(banco, 'VEICULO', com_hist, 'COMBUSTIVEL'), {})
    ativo = rpc(banco, 'criar_veiculo', PESSOAL, {**VEICULO_2, 'nome': 'Ativo'}, chave())['veiculo_id']
    rpc(banco, 'ativar_mobilidade', PESSOAL, {'tipo_modalidade': 'VEICULO', 'origem_id': ativo, 'confirmado': True}, chave())
    antes = resumo_tabelas(banco)
    for veiculo, motivo in ((com_fin, 'COM_VINCULOS'), (com_hist, 'COM_HISTORICO'), (ativo, 'EM_USO')):
        assert erro(rpc, banco, 'excluir_veiculo', PESSOAL, veiculo).diag.message_hint == motivo
    assert resumo_tabelas(banco) == antes
    # Sem vinculos: sai com as previstas (como no Flask).
    assert rpc(banco, 'excluir_veiculo', PESSOAL, livre)['excluido'] is True
    assert sql(banco, "select count(*) n from public.despesa_prevista where origem_tipo = 'VEICULO' and origem_id = %s", (livre,))[0]['n'] == 0
    # Financiamento removido: so as PREVISTA saem; depois o veiculo pode sair.
    assert rpc(banco, 'excluir_financiamento_veiculo', PESSOAL, com_fin) == {'removidos': 1}
    assert rpc(banco, 'excluir_veiculo', PESSOAL, com_fin)['excluido'] is True
    # Caminho de app: ativo nao sai; com historico nao sai; livre sai.
    app = rpc(banco, 'criar_caminho_app', PESSOAL, CAMINHO, chave())['id']
    rpc(banco, 'ativar_mobilidade', PESSOAL, {'tipo_modalidade': 'TRANSPORTE_APP', 'origem_id': app, 'confirmado': True}, chave())
    assert erro(rpc, banco, 'excluir_caminho_app', PESSOAL, app).diag.message_hint == 'EM_USO'
    assert erro(rpc, banco, 'editar_caminho_app', PESSOAL, 999, CAMINHO).diag.message_hint == 'NAO_ENCONTRADA'
    app2 = rpc(banco, 'criar_caminho_app', PESSOAL, {**CAMINHO, 'nome': 'Outro'}, chave())['id']
    assert app2 == app + 1 and rpc(banco, 'excluir_caminho_app', PESSOAL, app2)['removido'] is True


def test_idempotencia_e_confirmacao_nao_duplica(banco):
    k = chave()
    a = rpc(banco, 'criar_veiculo', PESSOAL, VEICULO_2, k)
    b = rpc(banco, 'criar_veiculo', PESSOAL, VEICULO_2, k)
    assert a['veiculo_id'] == b['veiculo_id'] and b['repetida'] is True
    assert sql(banco, 'select count(*) n from public.veiculo where nome = %s', (VEICULO_2['nome'],))[0]['n'] == 1
    alvo = prevista(banco, 'VEICULO', a['veiculo_id'], 'COMBUSTIVEL')
    rpc(banco, 'confirmar_despesa_prevista', PESSOAL, alvo, CONFIRMACAO)
    antes = resumo_tabelas(banco)
    e = erro(rpc, banco, 'confirmar_despesa_prevista', PESSOAL, alvo, CONFIRMACAO)
    assert 'Apenas despesas PREVISTA' in str(e) and resumo_tabelas(banco) == antes
    assert sql(banco, "select count(*) n from public.conta where descricao like 'Combustível%%'")[0]['n'] == 1
    # Projecoes de novo: a confirmada bloqueia a competencia (nao renasce PREVISTA nem duplica).
    rpc(banco, 'gerar_projecoes_veiculo', PESSOAL, a['veiculo_id'], {})
    comp = sql(banco, 'select data_prevista from public.despesa_prevista where id = %s', (alvo,))[0]['data_prevista']
    assert sql(banco, "select count(*) n from public.despesa_prevista where origem_id = %s and data_prevista = %s "
                      "and metadata::jsonb ->> 'tipo_evento' = 'COMBUSTIVEL'", (a['veiculo_id'], comp))[0]['n'] == 1
    k = chave()
    dados = {'tipo_modalidade': 'VEICULO', 'origem_id': a['veiculo_id'], 'meio_pagamento': 'pix', 'confirmado': True}
    assert rpc(banco, 'ativar_mobilidade', PESSOAL, dados, k)['cenario'] == rpc(banco, 'ativar_mobilidade', PESSOAL, dados, k)['cenario']
    assert sql(banco, "select count(*) n from public.mobilidade_cenario_ativo where status = 'ATIVO'")[0]['n'] == 1


def test_ativacoes_simultaneas_deixam_um_unico_cenario_ativo(banco):
    v = rpc(banco, 'criar_veiculo', PESSOAL, VEICULO_2, chave())['veiculo_id']
    ass = rpc(banco, 'criar_assinatura_mobilidade', PESSOAL, ASSINATURA, chave())['assinatura_id']
    barreira, falhas = threading.Barrier(2), []

    def ativar(tipo, origem):
        try:
            barreira.wait(timeout=10)
            rpc(banco, 'ativar_mobilidade', PESSOAL, {'tipo_modalidade': tipo, 'origem_id': origem, 'meio_pagamento': 'pix',
                                                      'confirmado': True}, chave())
        except Exception as exc:  # noqa: BLE001
            falhas.append(exc)

    tarefas = [threading.Thread(target=ativar, args=a) for a in (('VEICULO', v), ('ASSINATURA', ass))]
    for t in tarefas:
        t.start()
    for t in tarefas:
        t.join(timeout=60)
    assert falhas == []
    ativos = sql(banco, "select tipo_modalidade from public.mobilidade_cenario_ativo where status = 'ATIVO'")
    assert len(ativos) == 1
    rec = sql(banco, 'select origem_tipo from public.item_despesa where origem_tipo is not null and ativo and recorrente')
    assert [r['origem_tipo'] for r in rec] == [ativos[0]['tipo_modalidade']]


def test_recorrencia_da_modalidade_entra_no_gerador_e_sai_ao_trocar(banco):
    """Mobilidade x Recorrencias: a recorrencia mensal criada na ativacao gera a conta do mes pelo gerador do novo
    aplicativo (uma vez so); trocada a modalidade, ela fica inativa e nao gera mais."""
    from tests.test_supabase_recorrencia import gerar_confirmado
    v = rpc(banco, 'criar_veiculo', PESSOAL, VEICULO_2, chave())['veiculo_id']
    r = rpc(banco, 'ativar_mobilidade', PESSOAL, {'tipo_modalidade': 'VEICULO', 'origem_id': v, 'meio_pagamento': 'pix',
                                                  'data_inicio': '2031-03-01', 'confirmado': True}, chave())
    item = r['recorrencia']['id']
    mes = '2031-03-01'
    gerar_confirmado(banco, mes=mes)
    gerar_confirmado(banco, mes=mes)
    contas = sql(banco, 'select valor, data_vencimento from public.conta where item_despesa_id = %s order by data_vencimento', (item,))
    assert contas and contas[0]['valor'] == Decimal('200.00') and len({c['data_vencimento'] for c in contas}) == len(contas)
    ass = rpc(banco, 'criar_assinatura_mobilidade', PESSOAL, ASSINATURA, chave())['assinatura_id']
    rpc(banco, 'ativar_mobilidade', PESSOAL, {'tipo_modalidade': 'ASSINATURA', 'origem_id': ass, 'confirmado': True}, chave())
    assert sql(banco, 'select ativo from public.item_despesa where id = %s', (item,)) == [{'ativo': False}]
    antes = len(contas)
    gerar_confirmado(banco, mes='2031-06-01')
    assert sql(banco, 'select count(*) n from public.conta where item_despesa_id = %s', (item,))[0]['n'] == antes


def test_confirmar_no_cartao_cria_um_lancamento(banco):
    cartao = sql(banco, "select id from public.item_despesa where tipo = 'Agregador' and perfil_financeiro_id = %s "
                        "order by id limit 1", (PESSOAL,))
    if not cartao:
        pytest.skip('cluster sem cartao do Pessoal')
    v = rpc(banco, 'criar_veiculo', PESSOAL, VEICULO_2, chave())['veiculo_id']
    alvo = prevista(banco, 'VEICULO', v, 'COMBUSTIVEL')
    antes = sql(banco, 'select count(*) n from public.lancamento_agregado')[0]['n']
    r = rpc(banco, 'confirmar_despesa_prevista', PESSOAL, alvo, {'meio_pagamento': 'cartao', 'cartao_id': cartao[0]['id']})
    assert r['entidade_criada']['tipo'] == 'lancamento_agregado'
    assert sql(banco, 'select count(*) n from public.lancamento_agregado')[0]['n'] == antes + 1
    novos = sql(banco, "select valor, numero_parcela, total_parcelas from public.lancamento_agregado where descricao = 'Combustível'")
    assert novos == [{'valor': Decimal('200.00'), 'numero_parcela': 1, 'total_parcelas': 1}]
    assert erro(rpc, banco, 'confirmar_despesa_prevista', PESSOAL, prevista(banco, 'VEICULO', v, 'COMBUSTIVEL'),
                {'meio_pagamento': 'cartao'}).pgcode == '22023'  # sem cartao_id


def test_privilegios(banco):
    linhas = sql(banco, """select p.proname n, has_function_privilege('authenticated', p.oid, 'EXECUTE') a,
                                  has_function_privilege('anon', p.oid, 'EXECUTE') x
                             from pg_proc p join pg_namespace s on s.oid = p.pronamespace
                            where s.nspname = 'financeiro' and (p.proname like 'mob\\_%%' or p.proname in (
                                  'repeticao_mobilidade', 'registrar_operacao_mobilidade'))""")
    assert linhas and all(not r['a'] and not r['x'] for r in linhas), [r for r in linhas if r['a'] or r['x']]
    tela = ('criar_veiculo', 'editar_veiculo', 'converter_veiculo', 'gerar_projecoes_veiculo', 'excluir_veiculo',
            'criar_regra_km_veiculo', 'excluir_regra_km_veiculo', 'gerar_manutencao_km_veiculo', 'salvar_financiamento_veiculo',
            'excluir_financiamento_veiculo', 'previa_mobilidade', 'ativar_mobilidade', 'criar_assinatura_mobilidade',
            'editar_assinatura_mobilidade', 'criar_caminho_app', 'editar_caminho_app', 'excluir_caminho_app',
            'confirmar_despesa_prevista', 'adiar_despesa_prevista', 'ignorar_despesa_prevista')
    linhas = sql(banco, """select p.proname n, has_function_privilege('authenticated', p.oid, 'EXECUTE') a,
                                  has_function_privilege('anon', p.oid, 'EXECUTE') x, p.prosecdef d
                             from pg_proc p join pg_namespace s on s.oid = p.pronamespace
                            where s.nspname = 'financeiro' and p.proname = any(%s)""", (list(tela),))
    assert len(linhas) == len(tela) and all(r['a'] and not r['x'] and r['d'] for r in linhas)
    assert sql(banco, "select relrowsecurity r, relforcerowsecurity f from pg_class where oid = 'financeiro.operacao_mobilidade'::regclass")[0] == \
        {'r': True, 'f': True}


def test_reversao_remove_as_funcoes_e_preserva_os_dados(banco):
    v = rpc(banco, 'criar_veiculo', PESSOAL, VEICULO_1, chave())['veiculo_id']
    dados = sql(banco, "select md5(string_agg(x::text, '|' order by x.id)) h from public.despesa_prevista x where origem_id = %s", (v,))
    conn = psycopg2.connect(banco)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(REVERSAO.read_text(encoding='utf-8'))
    conn.close()
    restantes = sql(banco, "select count(*) n from pg_proc p join pg_namespace s on s.oid = p.pronamespace "
                           "where s.nspname = 'financeiro' and (p.proname like 'mob\\_%%' or p.proname in ('criar_veiculo', "
                           "'ativar_mobilidade', 'confirmar_despesa_prevista'))")[0]['n']
    assert restantes == 0 and sql(banco, "select to_regclass('financeiro.operacao_mobilidade') is null r")[0]['r']
    assert sql(banco, "select md5(string_agg(x::text, '|' order by x.id)) h from public.despesa_prevista x where origem_id = %s", (v,)) == dados
    conn = psycopg2.connect(banco)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(MIGRATION.read_text(encoding='utf-8'))  # reaplica
    conn.close()
    assert rpc(banco, 'criar_veiculo', PESSOAL, VEICULO_2, chave())['veiculo_id']
