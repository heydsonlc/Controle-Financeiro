"""
Testes FIN-ESCRITOR-UNICO-GUARDAS-1 — guarda de escritor nas tres escritas do Flask que ficavam sem ela (G1 comprovante
-> despesa, G2 confirmar despesa prevista com meio de pagamento, G3 vinculos PATRIMONIO de documento fiscal), em cluster
PostgreSQL local descartavel e com dados ficticios. Os casos basicos (409 sem gravar no perfil do novo aplicativo e
gravacao normal no perfil do Flask) estao no I8 de tests/test_supabase_integracao_1123_1126.py; aqui: edicao e remocao
de vinculo patrimonial nos dois sentidos, o que continua fora da guarda e a troca de escritor em andamento.
"""
import threading
import time

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_integracao_1123_1126 import (
    CASOS_I8,
    EMPRESA,
    PESSOAL,
    bem_da_empresa,
    comprovante,
    despesa_prevista,
    escrita_flask,
    resumo_tabelas,
    tabelas_alteradas,
)
from tests.test_supabase_receitas_categorias_tela import flask
from tests.test_supabase_recorrencia import (
    PG_BIN,
    atribuir,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')


def vinculos(dsn, doc):
    return sql(dsn, 'select id, tipo_entidade, entidade_id, ativo, md5(v::text) h from public.ir_comprovante_vinculo v '
                    'where comprovante_id = %s order by id', (doc,))


def md5_de(dsn, tabela, ident):
    return sql(dsn, f'select md5(x::text) h from {tabela} x where id = %s', (ident,))[0]['h']


def test_g3_vinculo_patrimonial_do_novo_aplicativo_nao_e_editado_nem_removido_pelo_flask(cluster):  # noqa: F811
    dsn = copiar(cluster)
    bem = bem_da_empresa(dsn)
    doc = comprovante(dsn, EMPRESA)
    atribuir(dsn, 'EMPRESA')
    rpc(dsn, 'vincular_documento_bem', EMPRESA, bem, {'comprovante_id': doc, 'tipo_vinculo': 'RECIBO'})
    vinculo = vinculos(dsn, doc)[0]
    assert (vinculo['tipo_entidade'], vinculo['entidade_id'], vinculo['ativo']) == ('PATRIMONIO', bem, True)
    bem_antes, doc_antes = md5_de(dsn, 'public.bem_patrimonial', bem), md5_de(dsn, 'public.ir_comprovante', doc)
    antes = resumo_tabelas(dsn)
    r = flask(dsn, [('perfil', EMPRESA),
                    ('editar', 'put', f"/api/ir/comprovantes/{doc}/vinculos/{vinculo['id']}", {'observacoes': 'pelo Flask'}),
                    ('remover', 'delete', f"/api/ir/comprovantes/{doc}/vinculos/{vinculo['id']}", None),
                    ('outro_bem', 'post', f'/api/ir/comprovantes/{doc}/vinculos', {'tipo_entidade': 'PATRIMONIO', 'entidade_id': bem})])
    for nome in ('editar', 'remover', 'outro_bem'):
        assert r[nome][0] == 409 and r[nome][1]['codigo'] == 'SISTEMA_NOVO', (nome, r[nome])
    assert tabelas_alteradas(antes, resumo_tabelas(dsn)) == []
    assert vinculos(dsn, doc) == [vinculo]  # vinculo, bem e documento intactos
    assert md5_de(dsn, 'public.bem_patrimonial', bem) == bem_antes and md5_de(dsn, 'public.ir_comprovante', doc) == doc_antes


def test_g3_no_perfil_do_flask_o_flask_cria_edita_e_remove_vinculo_patrimonial(cluster):  # noqa: F811
    dsn = copiar(cluster)
    bem = bem_da_empresa(dsn)  # Empresa no Flask
    doc = comprovante(dsn, EMPRESA)
    bem_antes, doc_antes = md5_de(dsn, 'public.bem_patrimonial', bem), md5_de(dsn, 'public.ir_comprovante', doc)
    r = flask(dsn, [('perfil', EMPRESA),
                    ('criar', 'post', f'/api/ir/comprovantes/{doc}/vinculos', {'tipo_entidade': 'PATRIMONIO', 'entidade_id': bem})])
    assert r['criar'][0] == 201, r['criar']
    vid = r['criar'][1]['data']['id']
    r = flask(dsn, [('perfil', EMPRESA),
                    ('editar', 'put', f'/api/ir/comprovantes/{doc}/vinculos/{vid}', {'observacoes': 'conferido'}),
                    ('remover', 'delete', f'/api/ir/comprovantes/{doc}/vinculos/{vid}', None)])
    assert r['editar'][0] == 200 and r['remover'][0] == 200, r
    assert [(v['id'], v['ativo']) for v in vinculos(dsn, doc)] == [(vid, False)]  # removido = inativo (historico)
    assert sql(dsn, 'select observacoes from public.ir_comprovante_vinculo where id = %s', (vid,))[0]['observacoes'] == 'conferido'
    assert md5_de(dsn, 'public.bem_patrimonial', bem) == bem_antes and md5_de(dsn, 'public.ir_comprovante', doc) == doc_antes


def test_blueprints_inteiros_guardados_depois_de_mobilidade_e_documentos(cluster):  # noqa: F811
    """As guardas pontuais (G1-G3) foram substituidas pela guarda do blueprint quando o novo aplicativo passou a gravar
    nessas tabelas: despesas previstas (FIN-MOBILIDADE-2) e Documentos/IR (FIN-DOCUMENTOS-2). Confirmar sem meio de
    pagamento e vinculo que nao e PATRIMONIO, antes fora da guarda, agora tambem sao recusados sem gravar."""
    dsn = copiar(cluster)
    prevista = despesa_prevista(dsn, PESSOAL)
    doc = comprovante(dsn, PESSOAL)
    atribuir(dsn, 'PESSOAL')
    antes = resumo_tabelas(dsn)
    r = flask(dsn, [('perfil', PESSOAL), ('confirmar', 'post', f'/api/despesas-previstas/{prevista}/confirmar', {}),
                    ('vinculo', 'post', f'/api/ir/comprovantes/{doc}/vinculos', {'tipo_entidade': 'OUTRO'}),
                    ('revisar', 'put', f'/api/ir/comprovantes/{doc}', {'prestador_nome': 'x'})])
    for nome, (status, corpo) in r.items():
        assert status == 409 and corpo['codigo'] == 'SISTEMA_NOVO', (nome, status, corpo)
    assert set(tabelas_alteradas(antes, resumo_tabelas(dsn))) <= {'public.perfil_financeiro'}


def aguardar(condicao, segundos):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(0.2)
    return False


@pytest.mark.parametrize('caso', CASOS_I8)
def test_troca_de_escritor_em_andamento_segura_a_escrita_do_flask_que_entao_e_recusada(cluster, caso):  # noqa: F811
    """A escrita corrigida usa a mesma trava compartilhada do perfil: com a troca para o novo aplicativo ainda aberta, o
    Flask espera na trava; depois do commit da troca, recusa (409) sem gravar."""
    dsn = copiar(cluster)
    perfil, passo = escrita_flask(caso, dsn)  # perfil no Flask
    antes = resumo_tabelas(dsn)
    resultado = []
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute('select financeiro.definir_gerador_recorrencia(%s, %s, %s, %s)',
                        (perfil, 'NOVO', 'administrador de teste', 'troca durante escrita do Flask'))
            t = threading.Thread(target=lambda: resultado.append(flask(dsn, [('perfil', perfil), passo])))
            t.start()
            esperando = aguardar(lambda: sql(dsn, "select count(*) n from pg_locks where locktype = 'advisory' "
                                                  "and not granted")[0]['n'] > 0, 120)
            assert esperando and t.is_alive(), 'o Flask nao parou na trava do perfil'
            conn.commit()
            t.join(timeout=120)
            assert not t.is_alive()
    finally:
        conn.close()
    assert resultado[0]['w'][0] == 409 and resultado[0]['w'][1]['codigo'] == 'SISTEMA_NOVO', resultado[0]['w']
    assert tabelas_alteradas(antes, resumo_tabelas(dsn)) == ['financeiro.gerador_recorrencia',
                                                             'financeiro.gerador_recorrencia_historico']
