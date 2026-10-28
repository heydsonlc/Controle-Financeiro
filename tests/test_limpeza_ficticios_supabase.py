"""
Testes FIN-BLOCO-D-1 (7) — scripts/limpeza_ficticios_supabase.py: retirada POR IDENTIDADE dos dados ficticios, num
cluster PostgreSQL local DESCARTAVEL com os cenarios ficticios do E2E.

O "Perfil B" (103, so do usuario B) faz o papel do perfil ficticio: financiamento com o ciclo conta <-> parcela,
categorias de cartao, conta bancaria, gerador NOVO (com a auditoria que o gatilho grava) e uma categoria global
"(demonstracao)" usada so por ele. Os demais perfis (101, 102, 104) sao os preservados.

Prova: inventario sem gravar e sem ambiguidade; ensaio sem gravar; retirada so das linhas da relacao (perfis
preservados, globais, usuarios e estrutura identicos); recusas diante de registro ambiguo, perfil nao declarado,
relacao desatualizada e projeto Supabase sem autorizacao expressa.
"""
import importlib.util

import pytest

from tests import supabase_local as L
from tests.test_supabase_integracao_1123_1126 import resumo_perfil, resumo_tabelas
from tests.test_supabase_recorrencia import PG_BIN, ROOT, copiar, sql

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

_spec = importlib.util.spec_from_file_location('limpeza_ficticios_supabase', ROOT / 'scripts' / 'limpeza_ficticios_supabase.py')
limpeza = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(limpeza)

FICTICIO = L.PERFIS['PERFIL_B']['id']
PRESERVADOS = {L.PERFIS[k]['id']: L.PERFIS[k]['nome'] for k in ('PESSOAL', 'EMPRESA', 'INATIVO_A')}
DEMO = 'Lazer (demonstracao)'


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    with L.ClusterLocal(PG_BIN, tmp_path_factory.mktemp('limpeza')) as c:
        c.preparar()
        conn = c.conectar()
        with conn.cursor() as cur:
            for semear in (L.semear_recorrencia_e2e, L.semear_receitas_e2e, L.semear_cartoes_e2e, L.semear_financiamento_e2e):
                semear(cur)
            cur.execute("update public.perfil_financeiro set nome = 'Perfil B (ficticio)' where id = %s", (FICTICIO,))
            cur.execute("insert into public.categoria (nome, cor, ativo, sistemica, bloquear_edicao, bloquear_exclusao) "
                        "values (%s, '#9333ea', true, false, false, false) returning id", (DEMO,))
            demo = cur.fetchone()[0]
            cur.execute('update public.item_despesa set categoria_id = %s where perfil_financeiro_id = %s', (demo, FICTICIO))
            cur.execute("select financeiro.definir_gerador_recorrencia(%s, 'NOVO', 'administrador de teste', 'cenario ficticio')",
                        (FICTICIO,))
        conn.close()
        yield c


def identidade(dsn):
    demo = sql(dsn, 'select id from public.categoria where nome = %s', (DEMO,))[0]['id']
    return {'projeto_ref_prefixo': 'fzjmge', 'perfis_ficticios': {str(FICTICIO): 'Perfil B (ficticio)'},
            'perfis_preservados': {str(k): v for k, v in PRESERVADOS.items()}, 'usuarios_teste': [L.USUARIO_B['id']],
            'globais_ficticios': {'public.categoria': {'ids': [demo], 'marcador': '(demonstracao)'}}}


def inventario(dsn, ident):
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True)
    try:
        return limpeza.montar_relacao(conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor), ident)[0]
    finally:
        conn.close()


def retirar(dsn, ident, relacao, confirmar):
    conn = psycopg2.connect(dsn)
    try:
        return limpeza.retirar(conn, ident, relacao, confirmar)
    finally:
        conn.close()


def linhas_do_ficticio(dsn):
    total = 0
    for r in sql(dsn, "select c.table_schema || '.' || c.table_name t from information_schema.columns c join information_schema.tables t "
                      "on t.table_schema = c.table_schema and t.table_name = c.table_name and t.table_type = 'BASE TABLE' "
                      "where c.column_name = 'perfil_financeiro_id' and c.table_schema in ('public', 'financeiro')"):
        total += sql(dsn, f"select count(*) n from {r['t']} where perfil_financeiro_id = %s", (FICTICIO,))[0]['n']
    return total


def test_inventario_por_identidade_sem_gravar(cluster):
    d = copiar(cluster)
    ident = identidade(d)
    antes = resumo_tabelas(d)
    rel = inventario(d, ident)
    assert rel['ambiguos'] == [], rel['ambiguos']
    assert resumo_tabelas(d) == antes
    assert rel['quantidades']['public.perfil_financeiro'] == 1
    assert rel['quantidades']['public.categoria'] == 1  # so a global "(demonstracao)"
    # Ciclo conta <-> parcela do financiamento ficticio e a auditoria do gerador entram por identidade.
    for t in ('public.financiamento', 'public.financiamento_parcela', 'public.conta', 'financeiro.gerador_recorrencia',
              'financeiro.gerador_recorrencia_historico', 'financeiro.perfil_acesso', 'public.categoria_cartao'):
        assert rel['quantidades'].get(t), t
    assert rel['preservadas']['public.perfil_financeiro'] == len(PRESERVADOS)


def test_ensaio_sem_confirmar_nao_grava(cluster):
    d = copiar(cluster)
    ident = identidade(d)
    antes = resumo_tabelas(d)
    rel = retirar(d, ident, inventario(d, ident), confirmar=False)
    assert rel['resultado'] == 'ENSAIO (nada gravado)' and rel['conferencia'].startswith('OK')
    assert resumo_tabelas(d) == antes


def test_retirada_so_da_relacao(cluster):
    d = copiar(cluster)
    ident = identidade(d)
    preservados = {p: resumo_perfil(d, p) for p in PRESERVADOS}
    usuarios = sql(d, 'select id, email from auth.users order by id')
    categorias = sql(d, 'select id, md5(x::text) h from public.categoria x where nome <> %s order by id', (DEMO,))
    relacao = inventario(d, ident)
    rel = retirar(d, ident, relacao, confirmar=True)
    assert rel['resultado'] == 'RETIRADO'
    assert rel['total_removido'] == relacao['total'] + sum(rel['geradas_por_gatilho_e_removidas'].values())
    assert rel['geradas_por_gatilho_e_removidas'] == {'financeiro.gerador_recorrencia_historico': 1}
    assert linhas_do_ficticio(d) == 0
    assert not sql(d, 'select 1 from public.perfil_financeiro where id = %s', (FICTICIO,))
    assert not sql(d, 'select 1 from public.categoria where nome = %s', (DEMO,))
    assert {p: resumo_perfil(d, p) for p in PRESERVADOS} == preservados
    assert sql(d, 'select id, email from auth.users order by id') == usuarios  # usuarios do Auth nunca saem
    assert sql(d, 'select id, md5(x::text) h from public.categoria x order by id') == categorias
    # Refazer o inventario depois: nada mais a retirar, mas o perfil declarado nao existe (ambiguo).
    assert 'perfil %s declarado mas inexistente' % FICTICIO in inventario(d, ident)['ambiguos']


def test_registro_real_ligado_a_ficticio_interrompe(cluster):
    d = copiar(cluster)
    ident = identidade(d)
    item = sql(d, 'select min(id) i from public.item_despesa where perfil_financeiro_id = %s', (FICTICIO,))[0]['i']
    sql(d, "insert into public.conta (item_despesa_id, perfil_financeiro_id, mes_referencia, descricao, valor, data_vencimento, "
           "status_pagamento) values (%s, %s, '2040-01-01', 'Conta real ligada a item ficticio', 10, '2040-01-10', 'Pendente')",
        (item, L.PERFIS['PESSOAL']['id']))
    rel = inventario(d, ident)
    assert any('depende de ficticio' in a for a in rel['ambiguos'])
    antes = resumo_tabelas(d)
    with pytest.raises(limpeza.LimpezaRecusada, match='ambiguos'):
        retirar(d, ident, rel, confirmar=True)
    assert resumo_tabelas(d) == antes


def test_perfil_nao_declarado_e_identidade_errada_interrompem(cluster):
    d = copiar(cluster)
    ident = identidade(d)
    sem_empresa = {**ident, 'perfis_preservados': {k: v for k, v in ident['perfis_preservados'].items()
                                                   if k != str(L.PERFIS['EMPRESA']['id'])}}
    assert any('nao declarado' in a for a in inventario(d, sem_empresa)['ambiguos'])
    usuario_real = {**ident, 'usuarios_teste': [L.USUARIO_A['id']]}
    assert any('nao e de teste' in a for a in inventario(d, usuario_real)['ambiguos'])
    global_errado = {**ident, 'globais_ficticios': {'public.categoria': {'ids': [201], 'marcador': '(demonstracao)'}}}
    assert any('nao tem a forma declarada' in a for a in inventario(d, global_errado)['ambiguos'])


def test_relacao_desatualizada_e_recusada(cluster):
    d = copiar(cluster)
    ident = identidade(d)
    relacao = inventario(d, ident)
    sql(d, "insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, cor_display) "
           "values (%s, 'Conta nova (ficticia)', 'Banco ficticio', 'Conta Corrente', 'ATIVO', '#3b82f6')", (FICTICIO,))
    antes = resumo_tabelas(d)
    with pytest.raises(limpeza.LimpezaRecusada, match='relacao mudou'):
        retirar(d, ident, relacao, confirmar=True)
    assert resumo_tabelas(d) == antes


def test_projeto_supabase_exige_autorizacao_expressa(monkeypatch, tmp_path, capsys):
    ident = tmp_path / 'identidade.json'
    ident.write_text('{"projeto_ref_prefixo": "fzjmge", "perfis_ficticios": {}, "perfis_preservados": {}, "usuarios_teste": []}',
                     encoding='utf-8')
    relacao = tmp_path / 'relacao.json'
    relacao.write_text('{"tabelas": {}}', encoding='utf-8')
    monkeypatch.setattr(limpeza.psycopg2, 'connect', lambda *a, **k: pytest.fail('nao pode conectar'))
    monkeypatch.setenv('CF_LIMPEZA_DSN', 'postgresql://postgres.fzjmgeexemplo:x@aws-0.pooler.supabase.com:5432/postgres')
    assert limpeza.main(['retirar', '--identidade', str(ident), '--relacao', str(relacao), '--confirmar']) == 2
    assert 'projeto-autorizado' in capsys.readouterr().err
    assert limpeza.main(['retirar', '--identidade', str(ident), '--relacao', str(relacao), '--projeto-autorizado', 'outro']) == 2
    monkeypatch.setenv('CF_LIMPEZA_DSN', 'postgresql://postgres.abcdefoutro:x@aws-0.pooler.supabase.com:5432/postgres')
    assert limpeza.main(['inventario', '--identidade', str(ident)]) == 2
    assert 'nao aponta para o projeto' in capsys.readouterr().err
