"""
FIN-BLOCO-C-1 (C6) / FIN-PRE-PRODUCAO-1 (3.3) — ensaio das migrations ainda nao aplicadas no Supabase remoto (20261127
Mobilidade, 20261128 Documentos, 20261129 Indexadores, 20261130 Documentos na tela e 20261201 Preferencias) num cluster
PostgreSQL descartavel no MESMO estado do remoto (migrations ate 20261126) e com dados
ficticios representativos de todos os modulos (os cenarios do E2E). Prova: aplicar as pendentes nao altera nenhum
dado existente (so cria as duas tabelas de idempotencia, vazias); as funcoes novas operam sobre os dados que ja
existiam; reverter (ordem inversa) tambem nao altera dado algum e a reaplicacao funciona.
"""
import base64
import json
import uuid
from pathlib import Path

import pytest

from tests import supabase_local as L
from tests.test_supabase_cartoes import rpc
from tests.test_supabase_integracao_1123_1126 import resumo_tabelas
from tests.test_supabase_recorrencia import PG_BIN, USUARIO_B, chamar, sql

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

RAIZ = Path(__file__).resolve().parent.parent
MIGRATIONS = RAIZ / 'supabase' / 'migrations'
REVERSAO = RAIZ / 'supabase' / 'reversao'
PENDENTES = ('20261127090000', '20261128090000', '20261129090000', '20261130090000', '20261201090000')  # pendentes no remoto
NOVAS_TABELAS = {'financeiro.operacao_mobilidade', 'financeiro.operacao_documento', 'financeiro.operacao_indexador',
                 'financeiro.indice_tr_historico', 'financeiro.preferencia_usuario', 'financeiro.preferencia_perfil'}
PERFIL_B = L.PERFIS['PERFIL_B']['id']


def executar(dsn, caminho):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(Path(caminho).read_text(encoding='utf-8'))
    finally:
        conn.close()


@pytest.fixture(scope='module')
def remoto_simulado(tmp_path_factory):
    """Mesmo estado do remoto: tabelas do Flask + migrations ate 20261126 + dados ficticios de todos os modulos."""
    with L.ClusterLocal(PG_BIN, tmp_path_factory.mktemp('ensaio')) as c:
        c.aplicar_shim()
        c.criar_tabelas_legadas()
        for m in sorted(MIGRATIONS.glob('*.sql')):
            if m.name[:14] < PENDENTES[0]:
                executar(c.dsn(), m)
        conn = c.conectar()
        with conn.cursor() as cur:
            for usuario in (L.USUARIO_A, L.USUARIO_B):
                cur.execute('insert into auth.users (id, email) values (%s, %s)', (usuario['id'], usuario['email']))
            for usuario, nomes in ((L.USUARIO_A, L.CATEGORIAS_A), (L.USUARIO_B, L.CATEGORIAS_B)):
                for nome in nomes:
                    cur.execute('insert into financeiro.categorias (user_id, nome, descricao) values (%s, %s, %s)',
                                (usuario['id'], nome, 'Dado ficticio de teste'))
            L.semear_perfis(cur)
            L.semear_contas(cur)
            for semear in (L.semear_recorrencia_e2e, L.semear_receitas_e2e, L.semear_cartoes_e2e, L.semear_pendencia_e2e,
                           L.semear_financiamento_e2e, L.semear_patrimonio_e2e, L.semear_documentos_fiscais_e2e,
                           L.semear_mobilidade_e2e):
                semear(cur)
        conn.close()
        yield c


def test_aplicar_as_pendentes_nao_altera_dados_e_as_funcoes_operam_sobre_eles(remoto_simulado):
    dsn = remoto_simulado.dsn()
    antes = resumo_tabelas(dsn)
    assert sum(1 for t in antes if t.startswith('public.')) > 40  # cenario representativo (tabelas do Flask)
    for versao in PENDENTES:
        executar(dsn, next(MIGRATIONS.glob(f'{versao}_*.sql')))
    depois = resumo_tabelas(dsn)
    assert set(depois) - set(antes) == NOVAS_TABELAS
    assert {t: h for t, h in depois.items() if t in antes} == antes  # nenhum dado existente mudou
    # As funcoes novas sobre os dados que ja existiam (Perfil B, no novo aplicativo nos cenarios do E2E).
    veiculo = sql(dsn, 'select id from public.veiculo where perfil_financeiro_id = %s order by id limit 1', (PERFIL_B,))[0]['id']
    r = rpc(dsn, 'gerar_projecoes_veiculo', PERFIL_B, veiculo, {'meses_futuros': 3}, usuario=USUARIO_B)
    assert r['criadas'] >= 1
    doc = chamar(dsn, USUARIO_B, 'select financeiro.enviar_comprovante(%s, %s::jsonb, %s, %s)',
                 (PERFIL_B, json.dumps({'nome_arquivo': 'ensaio.png', 'ano_calendario': 2027}),
                  base64.b64encode(b'\x89PNG\r\n\x1a\nensaio ficticio').decode(), str(uuid.uuid4())))
    assert doc['duplicado'] is False
    # FIN-PRE-PRODUCAO-1: TR, sugestao financeira do documento e preferencias sobre os dados existentes.
    assert any(i['competencia'] == '2034-01' for i in chamar(dsn, USUARIO_B, 'select financeiro.tr_oficial_tela(2034)', ()))
    sugestao = chamar(dsn, USUARIO_B, 'select financeiro.sugestao_financeira_documento_tela(%s, %s)', (PERFIL_B, doc['comprovante_id']))
    assert sugestao['comprovante_id'] == doc['comprovante_id']
    assert chamar(dsn, USUARIO_B, 'select financeiro.preferencias_tela(%s)', (PERFIL_B,))['data']['tema_sistema'] == 'escuro'


def test_reverter_em_ordem_inversa_nao_altera_dados_e_reaplica(remoto_simulado):
    dsn = remoto_simulado.dsn()
    antes = {t: h for t, h in resumo_tabelas(dsn).items() if t not in NOVAS_TABELAS}
    for versao in reversed(PENDENTES):
        executar(dsn, next(REVERSAO.glob(f'{versao}_*.sql')))
    depois = resumo_tabelas(dsn)
    assert not (NOVAS_TABELAS & set(depois)) and depois == antes
    for versao in PENDENTES:
        executar(dsn, next(MIGRATIONS.glob(f'{versao}_*.sql')))
    assert NOVAS_TABELAS <= set(resumo_tabelas(dsn))
