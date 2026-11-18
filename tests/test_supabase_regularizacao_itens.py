"""
Testes FIN-MULTIUSUARIO-SEGURANCA-01 — regularizacao dos itens de despesa sem perfil (scripts/regularizar_itens_sem_perfil.py)
e gerador da migration, em cluster PostgreSQL local descartavel e com dados ficticios.

Cenario como o real: parcelas de consorcio inativo, sem perfil e sem conta, cujo contrato e de um perfil conhecido. A posse
vem do vinculo com o contrato (ou com contas e compras), nunca do nome do perfil. Sem evidencia ou com evidencias
divergentes, o item nao e atribuido. So a coluna do perfil muda; a execucao exige a impressao da previa e e reversivel.
"""
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from tests.test_supabase_cartao_despesas_fixas import PESSOAL, banco  # noqa: F401
from tests.test_supabase_categorias_recorrencias import CATEGORIA
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, USUARIO_B, cluster, copiar, sql  # noqa: F401
from tests.test_supabase_recorrencia_cartao import rpc

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
import regularizar_itens_sem_perfil as REG  # noqa: E402


def cenario(dsn):
    """Consorcio inativo do Pessoal com as parcelas sem perfil (legado) + um item orfao + um item com conta de outro perfil."""
    rpc(dsn, 'criar_consorcio', PESSOAL, {'nome': 'Legado (ficticio)', 'valor_inicial': 200, 'numero_parcelas': 3, 'categoria_id': CATEGORIA,
                                         'mes_inicio': '2030-01'}, str(uuid.uuid4()))
    sql(dsn, "update public.contrato_consorcio set ativo = false where nome = 'Legado (ficticio)'")
    legado = [r['id'] for r in sql(dsn, "select id from public.item_despesa where tipo = 'Consorcio' and nome like 'Legado%%' order by id")]
    sql(dsn, 'delete from public.conta where item_despesa_id = any(%s)', (legado,))
    sql(dsn, 'update public.item_despesa set perfil_financeiro_id = null, ativo = false where id = any(%s)', (legado,))
    sem_perfil_antes = {r['id'] for r in sql(dsn, 'select id from public.item_despesa where perfil_financeiro_id is null')} - set(legado)
    return legado, sem_perfil_antes


def rodar(dsn, *args):
    """O roteiro como processo, como sera usado: (codigo de saida, saida)."""
    r = subprocess.run([sys.executable, str(RAIZ / 'scripts' / 'regularizar_itens_sem_perfil.py'), *args, '--dsn', dsn], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    return r.returncode, r.stdout + r.stderr


def retrato(dsn, sem_perfil=False):
    col = " - 'perfil_financeiro_id'" if sem_perfil else ''
    return sql(dsn, f"""select (select md5(string_agg((to_jsonb(i){col})::text, '|' order by i.id)) from public.item_despesa i) itens,
        (select md5(coalesce(string_agg(c::text, '|' order by c.id), '')) from public.conta c) contas,
        (select md5(coalesce(string_agg(l::text, '|' order by l.id), '')) from public.lancamento_agregado l) compras,
        (select md5(coalesce(string_agg(k::text, '|' order by k.id), '')) from public.contrato_consorcio k) contratos,
        (select md5(coalesce(string_agg(m::text, '|' order by m.id), '')) from public.movimento_financeiro m) movimentos,
        (select md5(coalesce(string_agg(b::text, '|' order by b.id), '')) from public.conta_bancaria b) contas_bancarias""")[0]


def test_posse_demonstrada_pelo_contrato_so_a_coluna_do_perfil_muda_e_a_reversao_devolve_tudo(banco, tmp_path):
    legado, outros = cenario(banco)
    inicial, inicial_sem = retrato(banco), retrato(banco, True)
    guarda = sql(banco, 'select perfil_financeiro_id p from financeiro.guarda_sem_perfil')[0]['p']
    previa, feito = tmp_path / 'previa.json', tmp_path / 'feito.json'

    cod, saida = rodar(banco, 'previa', '--perfil', str(PESSOAL), '--saida', str(previa))
    assert cod == 0, saida
    p = json.loads(previa.read_text(encoding='utf-8'))
    assert p['com_posse_demonstrada'] == len(legado) and p['contas_ligadas'] == 0
    # os outros itens sem perfil do cenario base nao tem contrato, conta nem compra: ficam para decisao, nao sao atribuidos
    assert {d['id'] for d in p['divergentes_lista']} == outros and p['divergentes'] == len(outros)
    assert retrato(banco) == inicial  # a previa nao grava

    # sem a impressao, com impressao errada ou sem a confirmacao literal: recusado, nada muda
    for args in (['executar', '--perfil', str(PESSOAL), '--confirmo', 'REGULARIZAR ITENS'],
                 ['executar', '--perfil', str(PESSOAL), '--hash', 'x' * 64, '--confirmo', 'REGULARIZAR ITENS'],
                 ['executar', '--perfil', str(PESSOAL), '--hash', p['impressao'], '--confirmo', 'sim']):
        cod, saida = rodar(banco, *args)
        assert cod != 0 and retrato(banco) == inicial, saida

    cod, saida = rodar(banco, 'executar', '--perfil', str(PESSOAL), '--hash', p['impressao'], '--confirmo', 'REGULARIZAR ITENS', '--saida', str(feito))
    assert cod == 0, saida
    f = json.loads(feito.read_text(encoding='utf-8'))
    assert f['atribuidos'] == len(legado) and sorted(f['ids']) == legado
    assert sql(banco, 'select count(*) n from public.item_despesa where id = any(%s) and perfil_financeiro_id = %s', (legado, PESSOAL))[0]['n'] == len(legado)
    assert {r['id'] for r in sql(banco, 'select id from public.item_despesa where perfil_financeiro_id is null')} == outros  # divergentes intocados
    depois = retrato(banco, True)
    assert depois == inicial_sem  # nenhum valor, vencimento, conta, compra, contrato, movimento ou saldo mudou
    aud = sql(banco, 'select perfil_destino, impressao, revertida_em, jsonb_array_length(registros -> \'itens\') n from financeiro.regularizacao_perfil')
    assert aud == [{'perfil_destino': PESSOAL, 'impressao': p['impressao'], 'revertida_em': None, 'n': len(legado)}]

    # repetir com a mesma impressao: o estado mudou, recusado
    cod, saida = rodar(banco, 'executar', '--perfil', str(PESSOAL), '--hash', p['impressao'], '--confirmo', 'REGULARIZAR ITENS')
    assert cod != 0 and 'estado mudou' in saida
    # a guarda nao sai enquanto houver registro sem perfil ou o catalogo depender dela
    cod, saida = rodar(banco, 'retirar-guarda', '--confirmo', 'RETIRAR GUARDA')
    assert cod != 0 and sql(banco, 'select perfil_financeiro_id p from financeiro.guarda_sem_perfil')[0]['p'] == guarda

    cod, saida = rodar(banco, 'reverter', '--feito', str(feito), '--confirmo', 'REVERTER ITENS')
    assert cod == 0, saida
    assert retrato(banco) == inicial
    assert sql(banco, 'select perfil_financeiro_id p from financeiro.guarda_sem_perfil')[0]['p'] == guarda
    assert sql(banco, 'select count(*) n from financeiro.regularizacao_perfil where revertida_em is not null')[0]['n'] == 1
    cod, saida = rodar(banco, 'reverter', '--feito', str(feito), '--confirmo', 'REVERTER ITENS')
    assert cod != 0 and 'ja revertida' in saida


def test_evidencia_de_outro_perfil_ou_ausente_nao_e_atribuida(banco):
    legado, _ = cenario(banco)
    # uma parcela passa a ter conta em OUTRO perfil: evidencias divergentes; outra fica sem contrato (nome alterado): sem evidencia
    sql(banco, "insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor, data_vencimento, status_pagamento, "
               "debito_automatico, numero_parcela, total_parcelas, is_fatura_cartao, estouro_orcamento, status_fatura) "
               "values (%s, %s, '2030-01-01', 'x', 10, '2030-01-10', 'Pendente', false, 1, 1, false, false, 'ABERTA')", (ID['PERFIL_B'], legado[0]))
    sql(banco, "update public.item_despesa set nome = 'Sem contrato (ficticio)' where id = %s", (legado[1],))
    conn = psycopg2.connect(banco)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        e = REG.estado(cur, PESSOAL)
    finally:
        conn.rollback()
        conn.close()
    motivos = {d['id']: d['motivo'] for d in e['divergentes']}
    assert 'evidencias apontam' in motivos[legado[0]] and 'sem evidencia' in motivos[legado[1]]
    assert [i['id'] for i in e['atribuir']] == legado[2:]
    # o perfil informado tem de ser o que as evidencias apontam, e tem de ter dono
    conn = psycopg2.connect(banco)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        outro = REG.estado(cur, ID['PERFIL_B'])
        assert outro['atribuir'] == []  # nada e do Perfil B so porque foi pedido
        with pytest.raises(SystemExit):
            REG.estado(cur, ID['EMPRESA'])  # perfil sem dono definido
    finally:
        conn.rollback()
        conn.close()


def test_migration_versionada_e_a_saida_exata_do_gerador():
    r = subprocess.run([sys.executable, str(RAIZ / 'scripts' / 'gerar_migration_multiusuario_seguranca.py'), '--verificar'], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    assert r.returncode == 0, r.stdout + r.stderr
