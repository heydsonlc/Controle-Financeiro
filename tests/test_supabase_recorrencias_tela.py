"""
Testes FIN-FIDELIDADE-RECORRENCIAS-1 — funcoes da tela de Recorrencias (migration 20261103090000).

Cenario FICTICIO do FIN-RECORRENCIA-1 (tests/supabase_local.py), copia por teste, Pessoal e Perfil B no novo
gerador; Empresa no Flask com A so LEITOR. Chamadas como o navegador (papel authenticated + claims).
"""
import uuid
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from tests.test_supabase_recorrencia import (
    ID,
    PG_BIN,
    USUARIO_A,
    USUARIO_B,
    atribuir,
    chamar,
    cluster,  # noqa: F401  (fixture de modulo reaproveitada)
    copiar,
    previa,
    sql,
)

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

NOVAS = ['financeiro.recorrencias_do_perfil(integer)', 'financeiro.reativar_recorrencia(integer, integer, text)',
         'financeiro.definir_meio_pagamento_recorrencia(integer, integer, text, text)']


@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    return dsn


def lista(dsn, perfil='PESSOAL', usuario=USUARIO_A):
    return chamar(dsn, usuario, "select coalesce(json_agg(x), '[]'::json) from financeiro.recorrencias_do_perfil(%s) x",
                  (ID.get(perfil, perfil),))


def por_nome(dsn, nome, perfil='PESSOAL', usuario=USUARIO_A):
    return next(r for r in lista(dsn, perfil, usuario) if r['nome'] == nome)


def falha(dsn, usuario, comando, params):
    with pytest.raises(psycopg2.Error) as erro:
        chamar(dsn, usuario, comando, params)
    return erro.value.pgcode, erro.value.diag.message_primary


def reativar(dsn, item, versao, perfil='PESSOAL', usuario=USUARIO_A):
    return chamar(dsn, usuario, 'select financeiro.reativar_recorrencia(%s, %s, %s)', (ID.get(perfil, perfil), item, versao))


def inativar(dsn, item, versao, perfil='PESSOAL', usuario=USUARIO_A):
    return chamar(dsn, usuario, 'select financeiro.inativar_recorrencia(%s, %s, %s)', (ID.get(perfil, perfil), item, versao))


def meio(dsn, item, versao, valor, perfil='PESSOAL', usuario=USUARIO_A):
    return chamar(dsn, usuario, 'select financeiro.definir_meio_pagamento_recorrencia(%s, %s, %s, %s)',
                  (ID.get(perfil, perfil), item, versao, valor))


def proximo(base, passo, hoje):
    """Regra do Flask (_proximo_vencimento) sem deslizar o dia: base + k passos a partir da data original."""
    k = 0
    while True:
        data = base + (relativedelta(years=k) if passo == 'anual' else relativedelta(months=k))
        if data >= hoje:
            return data
        k += 1


def hoje_brasilia(dsn):
    return sql(dsn, "select (now() at time zone 'America/Sao_Paulo')::date as d")[0]['d']


@pytest.mark.parametrize('funcao', NOVAS)
def test_funcoes_seguras(banco, funcao):
    r = sql(banco, f"""select p.prosecdef as definer, coalesce(array_to_string(p.proconfig, ','), '') as config,
                              has_function_privilege('anon', '{funcao}', 'EXECUTE') as anon,
                              has_function_privilege('authenticated', '{funcao}', 'EXECUTE') as autenticado
                         from pg_proc p where p.oid = '{funcao}'::regprocedure""")[0]
    assert r['definer'] is True and 'search_path=""' in r['config']
    assert r['anon'] is False and r['autenticado'] is True


def test_lista_do_perfil_como_o_flask_com_legado_e_sem_consorcio_nem_cartao_agregador(banco):
    nomes = [r['nome'] for r in lista(banco)]
    # Recorte do Flask: recorrentes do perfil (NULL -> Pessoal), inclusive inativas, semanais e de cartao; sem o cartao.
    assert nomes == ['Academia', 'Aluguel 31', 'Bissexto', 'Escola', 'Feira semanal', 'IPVA', 'Legado sem perfil', 'Streaming']
    academia = por_nome(banco, 'Academia')
    assert academia['ativo'] is False and academia['gerenciavel'] is True and academia['meio_pagamento'] == 'pix'
    streaming = por_nome(banco, 'Streaming')
    assert streaming['gerenciavel'] is False and streaming['cartao_nome'] is not None  # cartao: fica no modulo de cartoes
    escola = por_nome(banco, 'Escola')
    assert (escola['meio_pagamento'], escola['conta_bancaria_nome']) == ('debito_automatico', 'Conta Pessoal (A)')
    assert escola['categoria_nome'] and escola['versao']
    assert [r['nome'] for r in lista(banco, 'PERFIL_B', USUARIO_B)] == ['Cartao sem categoria B', 'Sem valor B', 'Valido B']


def test_proximo_vencimento_sem_deslizar_o_dia(banco):
    hoje = hoje_brasilia(banco)
    ipva = por_nome(banco, 'IPVA')  # anual, ancora 15/03/2026
    assert date.fromisoformat(ipva['proximo_vencimento']) == proximo(date(2026, 3, 15), 'anual', hoje)
    aluguel = por_nome(banco, 'Aluguel 31')  # mensal, ancora 31/01/2027 (futura: a propria ancora)
    assert date.fromisoformat(aluguel['proximo_vencimento']) == proximo(date(2027, 1, 31), 'mensal', hoje)
    sql(banco, "update public.item_despesa set data_vencimento = '2026-01-31' where id = 901")
    assert date.fromisoformat(por_nome(banco, 'Aluguel 31')['proximo_vencimento']) == proximo(date(2026, 1, 31), 'mensal', hoje)


def test_lista_isolada_por_perfil_e_usuario(banco):
    assert falha(banco, USUARIO_A, 'select * from financeiro.recorrencias_do_perfil(%s)', (ID['PERFIL_B'],))[0] == '42501'
    assert falha(banco, USUARIO_B, 'select * from financeiro.recorrencias_do_perfil(%s)', (ID['PESSOAL'],))[0] == '42501'
    assert falha(banco, None, 'select * from financeiro.recorrencias_do_perfil(%s)', (ID['PESSOAL'],))[0] == '42501'
    assert [r['nome'] for r in lista(banco, 'EMPRESA')] == ['Aluguel sala']  # LEITOR so le


def test_inativar_e_reativar_com_versao_e_previa(banco):
    item = por_nome(banco, 'Aluguel 31')
    assert any(i['item_id'] == 901 for i in previa(banco, mes='2027-02-01')['itens'])
    inativar(banco, 901, item['versao'])
    assert por_nome(banco, 'Aluguel 31')['ativo'] is False
    assert not any(i['item_id'] == 901 for i in previa(banco, mes='2027-02-01')['itens'])  # nada novo e gerado
    # Versao antiga (anterior a inativacao): recusada sem mudar nada.
    codigo, mensagem = falha(banco, USUARIO_A, 'select financeiro.reativar_recorrencia(%s, %s, %s)', (ID['PESSOAL'], 901, item['versao']))
    assert codigo == 'P0001' and 'alterada por outra operacao' in mensagem
    r = reativar(banco, 901, por_nome(banco, 'Aluguel 31')['versao'])
    assert r['ativo'] is True and por_nome(banco, 'Aluguel 31')['ativo'] is True
    assert any(i['item_id'] == 901 for i in previa(banco, mes='2027-02-01')['itens'])  # volta a ser oferecida (com confirmacao)


def test_reativar_e_meio_exigem_gestao_e_recorrencia_do_perfil(banco):
    sala = por_nome(banco, 'Aluguel sala', 'EMPRESA')
    assert falha(banco, USUARIO_A, 'select financeiro.reativar_recorrencia(%s, %s, %s)', (ID['EMPRESA'], 940, sala['versao']))[0] == '42501'
    aluguel = por_nome(banco, 'Aluguel 31')
    assert falha(banco, USUARIO_B, 'select financeiro.definir_meio_pagamento_recorrencia(%s, %s, %s, %s)',
                 (ID['PERFIL_B'], 901, aluguel['versao'], 'pix'))[0] == '42501'
    streaming = por_nome(banco, 'Streaming')  # de cartao: outro modulo
    assert falha(banco, USUARIO_A, 'select financeiro.reativar_recorrencia(%s, %s, %s)', (ID['PESSOAL'], 906, streaming['versao']))[0] == 'P0001'


def test_meio_de_pagamento_informativo(banco):
    aluguel = por_nome(banco, 'Aluguel 31')
    r = meio(banco, 901, aluguel['versao'], 'PIX')
    assert r['meio_pagamento'] == 'pix' and por_nome(banco, 'Aluguel 31')['meio_pagamento'] == 'pix'
    for invalido in ('cartao', 'debito_automatico', 'cheque'):
        assert falha(banco, USUARIO_A, 'select financeiro.definir_meio_pagamento_recorrencia(%s, %s, %s, %s)',
                     (ID['PESSOAL'], 901, por_nome(banco, 'Aluguel 31')['versao'], invalido))[0] == '22023'
    # Sair do debito automatico solta a conta do debito; contas ja geradas nao mudam.
    antes = sql(banco, "select md5(string_agg(t::text, '|' order by id)) as h from public.conta t where item_despesa_id = 902")[0]['h']
    meio(banco, 902, por_nome(banco, 'Escola')['versao'], 'boleto')
    escola = por_nome(banco, 'Escola')
    assert (escola['meio_pagamento'], escola['conta_bancaria_id']) == ('boleto', None)
    assert sql(banco, "select md5(string_agg(t::text, '|' order by id)) as h from public.conta t where item_despesa_id = 902")[0]['h'] == antes
    meio(banco, 901, por_nome(banco, 'Aluguel 31')['versao'], None)
    assert por_nome(banco, 'Aluguel 31')['meio_pagamento'] is None


def test_meio_informativo_nao_muda_a_geracao(banco):
    natureza = {i['item_id']: i['natureza'] for i in previa(banco, mes='2027-02-01')['itens']}
    meio(banco, 901, por_nome(banco, 'Aluguel 31')['versao'], 'debito')
    depois = {i['item_id']: i['natureza'] for i in previa(banco, mes='2027-02-01')['itens']}
    assert depois == natureza and natureza.get(901) == 'CONTA'


def test_recorrencia_criada_pela_tela_aparece_e_e_gerenciavel(banco):
    r = chamar(banco, USUARIO_A, 'select financeiro.criar_despesa(%s, %s::jsonb, %s)', (
        ID['PESSOAL'], '{"nome": "Internet fibra", "valor": "99.90", "categoria_id": 951, "data_vencimento": "2027-04-12", '
        '"recorrente": true, "tipo_recorrencia": "mensal"}', str(uuid.uuid4())))
    nova = por_nome(banco, 'Internet fibra')
    assert nova['id'] == r['item_id'] and nova['ativo'] is True and nova['gerenciavel'] is True
    assert (nova['tipo_recorrencia'], nova['data_vencimento'], float(nova['valor'])) == ('mensal', '2027-04-12', 99.9)
