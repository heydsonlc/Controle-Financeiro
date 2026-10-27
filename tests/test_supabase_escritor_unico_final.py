"""
Testes FIN-ESCRITOR-UNICO-FINAL-1 — escritor unico nas escritas antigas (migration 20261124090000) e nas rotas de escrita
do Flask (registrar_guarda_escritor_unico).

Novo aplicativo: as 29 funcoes de cadastro/edicao (despesas, recorrencias, receitas, cartoes, compras, lancamentos,
importacao, perfil) recusam perfil ainda no Flask (SISTEMA_FLASK) antes de qualquer gravacao; usuario sem vinculo
recebe 42501. Flask: com o perfil no novo aplicativo, as rotas de escrita desses modulos respondem 409 SISTEMA_NOVO e
nada gravam; rotas que so leem (analisar/previsualizar importacao, revelar codigo) e o catalogo global de categorias
continuam. Com o perfil no Flask, o Flask grava normalmente.
"""
import hashlib
import uuid

import pytest

from tests.test_supabase_cartoes import rpc
from tests.test_supabase_receitas_categorias_tela import flask
from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    USUARIO_B,
    atribuir,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL = ID['PESSOAL']
GUARDADAS = """atualizar_limite_cartao atualizar_perfil cancelar_parcelas_futuras criar_cartao criar_compra criar_despesa criar_receita
definir_meio_pagamento_recorrencia desativar_limite_cartao dispensar_aviso_recorrencia editar_cartao editar_compra editar_despesa
editar_fonte_receita editar_lancamento_cartao editar_parcelas_futuras editar_receita editar_recorrencia excluir_compra
excluir_despesa excluir_receita importar_fatura_cartao inativar_cartao inativar_fonte_receita inativar_perfil
inativar_recorrencia reativar_perfil reativar_recorrencia vincular_limite_cartao""".split()
VALOR = {'integer': '0', 'bigint': '0', 'numeric': '0', 'jsonb': "'{}'::jsonb", 'uuid': f"'{uuid.uuid4()}'::uuid",
         'text': "''", 'date': "'2030-01-01'::date", 'boolean': 'false', 'integer[]': "'{}'::integer[]"}


def digital(dsn):
    """Digest do conteudo das tabelas financeiras (public e financeiro), para provar que nada foi gravado. Fora: a conta
    de login que o roteiro do Flask cria a cada execucao (public.usuario)."""
    tabelas = [r['t'] for r in sql(dsn, "select table_schema || '.' || table_name t from information_schema.tables "
                                        "where table_schema in ('public', 'financeiro') and table_type = 'BASE TABLE' "
                                        "and table_name <> 'usuario' order by 1")]
    h = hashlib.sha256()
    for t in tabelas:
        for r in sql(dsn, f'select md5(coalesce(string_agg(x::text, \'|\' order by x::text), \'\')) d from {t} x'):
            h.update(f"{t}:{r['d']}".encode())
    return h.hexdigest()


def chamada(dsn, funcao, perfil):
    args = sql(dsn, "select pg_get_function_identity_arguments(p.oid) a from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                    "where n.nspname = 'financeiro' and p.proname = %s", (funcao,))[0]['a']
    valores = []
    for i, arg in enumerate(a.strip() for a in args.split(',')):
        tipo = arg.split(' ', 1)[1]
        valores.append(str(perfil) if i == 0 else VALOR[tipo])
    return f"select financeiro.{funcao}({', '.join(valores)})"


def erro(dsn, comando, usuario=None):
    from tests.test_supabase_recorrencia import chamar, USUARIO_A
    with pytest.raises(psycopg2.Error) as e:
        chamar(dsn, usuario or USUARIO_A, comando)
    return e.value.pgcode, e.value.diag.message_hint


def test_todas_as_escritas_recusam_perfil_no_flask_sem_gravar(cluster):  # noqa: F811
    dsn = copiar(cluster)  # Pessoal segue no Flask
    antes = digital(dsn)
    for funcao in GUARDADAS:
        assert erro(dsn, chamada(dsn, funcao, PESSOAL)) == ('P0001', 'SISTEMA_FLASK'), funcao
    assert digital(dsn) == antes


def test_usuario_sem_vinculo_recebe_42501(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    for funcao in GUARDADAS:
        assert erro(dsn, chamada(dsn, funcao, PESSOAL), usuario=USUARIO_B)[0] == '42501', funcao


def test_perfil_no_novo_aplicativo_grava_e_reenvio_nao_duplica(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    categoria = sql(dsn, 'select id from public.categoria order by id limit 1')[0]['id']
    dados = {'nome': 'Despesa escritor final (ficticia)', 'valor': 42.5, 'categoria_id': categoria, 'tipo': 'Simples',
             'data_vencimento': '2031-03-10', 'recorrente': False}
    chave = str(uuid.uuid4())
    rpc(dsn, 'criar_despesa', PESSOAL, dados, chave)
    b = rpc(dsn, 'criar_despesa', PESSOAL, dados, chave)
    assert b.get('repetida') is True
    assert sql(dsn, "select count(*) n from public.item_despesa where nome = 'Despesa escritor final (ficticia)'")[0]['n'] == 1
    # Volta para o Flask: a mesma escrita e recusada.
    atribuir(dsn, 'PESSOAL', 'FLASK')
    with pytest.raises(psycopg2.Error) as e:
        rpc(dsn, 'criar_despesa', PESSOAL, {**dados, 'nome': 'Outra (ficticia)'}, str(uuid.uuid4()))
    assert e.value.diag.message_hint == 'SISTEMA_FLASK'


ESCRITAS_FLASK = [
    ('despesa', 'post', '/api/despesas/', {'nome': 'Flask escritor (ficticio)', 'valor': 10, 'tipo': 'Simples'}),
    ('recorrencia', 'post', '/api/recorrencias', {'nome': 'Recorrencia escritor (ficticia)', 'valor': 10}),
    ('fonte', 'post', '/api/receitas/itens', {'nome': 'Fonte escritor (ficticia)', 'tipo': 'SALARIO_FIXO', 'valor_base_mensal': 10}),
    ('cartao', 'post', '/api/cartoes', {'nome': 'Cartao escritor (ficticio)', 'dia_fechamento': 1, 'dia_vencimento': 10}),
    ('cat_cartao', 'post', '/api/categorias-cartao', {'nome': 'Categoria cartao escritor (ficticia)'}),
    ('importar', 'post', '/api/importacao-cartao/processar', {'cartao_id': 1, 'lancamentos': []}),
    ('editar_perfil', 'put', f'/api/perfis-financeiros/{PESSOAL}', {'nome': 'Pessoal'}),
]


def test_flask_recusa_escritas_em_perfil_do_novo_aplicativo(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    antes = digital(dsn)
    r = flask(dsn, [('perfil', PESSOAL)] + ESCRITAS_FLASK)
    for nome, *_ in ESCRITAS_FLASK:
        assert r[nome][0] == 409 and r[nome][1]['codigo'] == 'SISTEMA_NOVO', (nome, r[nome])
    assert digital(dsn) == antes
    # So leitura e catalogo global continuam.
    r = flask(dsn, [('perfil', PESSOAL),
                    ('previa', 'post', '/api/importacao-cartao/previsualizar', {'linhas': []}),
                    ('categoria', 'post', '/api/categorias', {'nome': 'Categoria global escritor (ficticia)', 'tipo': 'despesa'})])
    assert r['previa'][0] != 409 and r['categoria'][0] != 409, r


def test_flask_grava_em_perfil_do_flask(cluster):  # noqa: F811
    dsn = copiar(cluster)  # Pessoal no Flask
    r = flask(dsn, [('perfil', PESSOAL), ESCRITAS_FLASK[2], ESCRITAS_FLASK[4]])
    assert r['fonte'][0] in (200, 201) and r['cat_cartao'][0] in (200, 201), r
