"""
Suite PERMANENTE de isolamento entre usuarios (FIN-MULTIUSUARIO-SEGURANCA-01), em cluster PostgreSQL local descartavel e
com dados ficticios. Deve passar antes de qualquer publicacao que crie ou altere funcao do banco.

Cenario: usuarios A e B, independentes, cada um dono de um perfil "Pessoal" e de um perfil "Empresa" (nomes iguais), com um
registro MARCADO em cada tabela de dados do perfil (tests/isolamento_cenario.py).

  1. Perfil alheio: toda funcao exposta que recebe p_perfil_id recusa (42501) o perfil do outro usuario, ANTES de validar
     os dados, e nenhuma resposta traz a marca do outro.
  2. Registro alheio: no proprio perfil, com o id de um registro do outro usuario em cada parametro de identificador, a
     funcao recusa ou nao encontra; nenhuma resposta traz a marca do outro; nada do outro e alterado. O dono repete a
     mesma chamada (controle): so quando o resultado do dono difere da recusa e que a cobertura conta como EFETIVA.
  3. Sem sessao: nenhuma funcao e executavel por anonimo.
  4. Positivos: nomes iguais entre usuarios, perfil padrao de cada um, operacoes legitimas.
  5. Tentativas especificas (pagar, estornar, usar conta ou cartao alheio, documento, financiamento, consorcio, receita,
     indices de TR) com dados completos, gravando de verdade: o retrato dos dados da vitima fica identico.

A cobertura por funcao e gravada em CF_ISOLAMENTO_RELATORIO (opcional). As funcoes SEM cobertura efetiva ficam listadas em
tests/isolamento_sem_cobertura.json (so a impressao de cada entrada; a lista legivel fica no relatorio privado): uma funcao
nova que caia nessa situacao faz o teste falhar ate ser avaliada.
"""
import hashlib
import json
import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests import isolamento_cenario as I
from tests import isolamento_dirigido as D
from tests.test_supabase_cartoes import rpc, tabela
from tests.test_supabase_categorias_recorrencias import CATEGORIA, banco, erro  # noqa: F401
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, USUARIO_B, atribuir, cluster, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

SEM_COBERTURA = Path(__file__).with_name('isolamento_sem_cobertura.json')
PERGUNTAS = {'pode_acessar_perfil', 'pode_gerir_perfil'}  # respondem "nao" em vez de recusar: e a propria pergunta
USUARIO = {'A': USUARIO_A, 'B': USUARIO_B}
OUTRO = {'A': 'B', 'B': 'A'}


@pytest.fixture
def cenario(banco):
    """A: Pessoal (o do cenario base) e Empresa; B: Pessoal e Empresa. Um registro marcado por tabela e por perfil."""
    perfis = {'A': {'Pessoal': ID['PESSOAL']}, 'B': {}}
    perfis['A']['Empresa'] = rpc(banco, 'criar_perfil', {'nome': 'Empresa', 'tipo': 'EMPRESA'}, usuario=USUARIO_A)['id']
    perfis['B']['Pessoal'] = rpc(banco, 'criar_perfil', {'nome': 'Pessoal', 'tipo': 'PESSOAL'}, usuario=USUARIO_B)['id']
    perfis['B']['Empresa'] = rpc(banco, 'criar_perfil', {'nome': 'Empresa', 'tipo': 'EMPRESA'}, usuario=USUARIO_B)['id']
    conn = I.conectar(banco)
    esquema = I.Esquema(conn)
    semeados = {d: {n: I.Semeador(conn, esquema, d, p, CATEGORIA).tudo() for n, p in perfis[d].items()} for d in 'AB'}
    yield {'dsn': banco, 'conn': conn, 'perfis': perfis, 'semeados': semeados, 'esquema': esquema}
    conn.close()


def gravar_relatorio(nome, linhas):
    pasta = os.environ.get('CF_ISOLAMENTO_RELATORIO')
    if pasta:
        Path(pasta).mkdir(parents=True, exist_ok=True)
        (Path(pasta) / nome).write_text(json.dumps(linhas, ensure_ascii=False, indent=1), encoding='utf-8')


# =====================================================================================================================
# 0. O cenario existe: dois usuarios, mesmos nomes, dados equivalentes
# =====================================================================================================================

def test_cenario_tem_dois_usuarios_com_perfis_de_mesmo_nome_e_dados_em_todos_os_modulos(cenario):
    donos = sql(cenario['dsn'], 'select id, nome, user_id::text dono from public.perfil_financeiro where id = any(%s)',
                ([p for d in cenario['perfis'].values() for p in d.values()],))
    por_dono = {}
    for p in donos:
        por_dono.setdefault(p['dono'], set()).add(p['nome'])
    assert por_dono == {USUARIO_A['id']: {'Pessoal', 'Empresa'}, USUARIO_B['id']: {'Pessoal', 'Empresa'}}
    exigidas = {'public.conta', 'public.conta_bancaria', 'public.item_despesa', 'public.lancamento_agregado', 'public.receita_realizada',
                'public.item_receita', 'public.financiamento', 'public.financiamento_parcela', 'public.contrato_consorcio', 'public.veiculo',
                'public.ir_comprovante', 'public.ir_comprovante_arquivo', 'public.movimento_financeiro', 'public.transferencia',
                'public.despesa_prevista', 'public.categoria_cartao', 'public.bem_patrimonial'}
    for dono in 'AB':
        for nome, s in cenario['semeados'][dono].items():
            faltam = exigidas - {t for t, v in s.ids.items() if v}
            assert not faltam, f'{dono}/{nome}: sem registro em {sorted(faltam)} ({ {t: s.falhas.get(t) for t in faltam} })'
            assert {'cartao', 'fatura', 'compra_no_cartao'} <= set(s.extras), f'{dono}/{nome}: {s.extras}'


# =====================================================================================================================
# 1. Perfil alheio
# =====================================================================================================================

def test_toda_funcao_com_perfil_recusa_o_perfil_de_outro_usuario_antes_de_validar_os_dados(cenario):
    conn, fs = cenario['conn'], I.funcoes_expostas(cenario['conn'])
    com_perfil = [f for f in fs if 'p_perfil_id' in (f['nomes'] or [])[:f['n']]]
    assert len(com_perfil) >= 230
    relatorio, erradas = [], []
    for atacante in 'AB':
        vitima = OUTRO[atacante]
        for nome_perfil, perfil in cenario['perfis'][vitima].items():
            for f in com_perfil:
                cod, msg, ret = I.chamar(conn, USUARIO[atacante], f, {'p_perfil_id': perfil})
                relatorio.append({'funcao': f['nome'], 'atacante': atacante, 'perfil_da_vitima': nome_perfil, 'codigo': cod, 'mensagem': msg})
                assert not I.vazou(ret, msg, vitima), f"{f['nome']}: resposta com dado de {vitima}"
                if f['nome'] in PERGUNTAS:
                    assert (cod, ret) == ('OK', '[false]'), f['nome']
                elif cod != '42501':
                    erradas.append((f['nome'], atacante, cod, msg))
    gravar_relatorio('1_perfil_alheio.json', relatorio)
    assert not erradas, f'{len(erradas)} chamada(s) nao recusaram o perfil alheio com 42501: {sorted(set(erradas))[:12]}'


# =====================================================================================================================
# 2. Registro alheio no proprio perfil
# =====================================================================================================================

def _parametros_de_id(f):
    nomes, tipos = (f['nomes'] or [])[:f['n']], f['tipos'] or []
    return [n for n, t in zip(nomes, tipos) if t in ('integer', 'bigint') and n != 'p_perfil_id'
            and n not in ('p_ano', 'p_limite', 'p_janela', 'p_meses', 'p_total_previsto', 'p_esperadas')]


def test_registro_de_outro_usuario_nunca_e_devolvido_nem_alterado_e_a_cobertura_efetiva_e_medida(cenario):
    conn, fs = cenario['conn'], I.funcoes_expostas(cenario['conn'])
    alvo_funcoes = [f for f in fs if 'p_perfil_id' in (f['nomes'] or [])[:f['n']] and _parametros_de_id(f)]
    todos_perfis = [p for d in cenario['perfis'].values() for p in d.values()]
    antes = I.retrato(conn, todos_perfis)
    relatorio, vazamentos, por_funcao = [], [], {}
    for atacante in 'AB':
        vitima = OUTRO[atacante]
        meu = cenario['perfis'][atacante]['Pessoal']
        dela = cenario['perfis'][vitima]['Pessoal']
        alvos = cenario['semeados'][vitima]['Pessoal'].alvos()
        for f in alvo_funcoes:
            for p in _parametros_de_id(f):
                efetiva, respostas = False, set()
                for rotulo, alvo in alvos.items():
                    cod, msg, ret = I.chamar(conn, USUARIO[atacante], f, {'p_perfil_id': meu, p: alvo})
                    classe = I.classificar(cod, msg, ret)
                    if I.vazou(ret, msg, vitima):
                        vazamentos.append((f['nome'], p, rotulo, cod))
                    respostas.add(classe)
                    # controle: o DONO, no perfil dele, com o mesmo registro. Resultado diferente = a funcao chegou a
                    # procurar o registro, e a recusa ao atacante foi pela posse (cobertura efetiva).
                    c_cod, c_msg, c_ret = I.chamar(conn, USUARIO[vitima], f, {'p_perfil_id': dela, p: alvo})
                    if (c_cod, c_msg) != (cod, msg) and classe != 'respondeu':
                        efetiva = True
                    if classe == 'respondeu' and c_cod == 'OK' and c_ret != ret:
                        efetiva = True  # ao dono, o dado; ao atacante, vazio
                relatorio.append({'funcao': f['nome'], 'parametro': p, 'atacante': atacante, 'respostas': sorted(respostas), 'cobertura_efetiva': efetiva})
                por_funcao.setdefault((f['nome'], p), []).append(efetiva)
    gravar_relatorio('2_registro_alheio.json', relatorio)
    assert not vazamentos, f'RESPOSTA COM DADO DE OUTRO USUARIO: {vazamentos[:10]}'
    assert I.retrato(conn, todos_perfis) == antes  # as chamadas sao desfeitas; nada pode ter mudado

    # FIN-MULTIUSUARIO-AJUSTES-FINAIS-01: as combinacoes que a sonda generica nao alcanca tem sonda DIRIGIDA (teste seguinte) ou
    # estao classificadas, com motivo, como nao aplicaveis. O que sobrar e lacuna a avaliar antes de publicar.
    sem_generica = sorted(f'{n}({p})' for (n, p), vs in por_funcao.items() if not any(vs))
    gravar_relatorio('2_sem_cobertura_generica.json', sem_generica)
    sem = sorted(f'{n}({p})' for (n, p), vs in por_funcao.items() if not any(vs) and (n, p) not in D.CASOS and (n, p) not in D.NAO_APLICAVEIS)
    gravar_relatorio('2_sem_cobertura_efetiva.json', sem)
    # No repositorio fica so a impressao (SHA-256) de cada entrada: a lista legivel vai para o relatorio privado.
    impressao = lambda x: hashlib.sha256(x.encode()).hexdigest()  # noqa: E731
    if os.environ.get('CF_ISOLAMENTO_ATUALIZAR') == '1':
        SEM_COBERTURA.write_text(json.dumps(sorted(impressao(x) for x in sem), indent=1) + '\n', encoding='utf-8')
    conhecidas = set(json.loads(SEM_COBERTURA.read_text(encoding='utf-8'))) if SEM_COBERTURA.exists() else set()
    novas = sorted(x for x in sem if impressao(x) not in conhecidas)
    assert not novas, (f'{len(novas)} funcao(oes) sem cobertura efetiva de registro alheio que nao estao em {SEM_COBERTURA.name}: {novas[:15]}. '
                       'Avalie cada uma (teste especifico ou registro na lista) antes de publicar.')


def test_sondas_dirigidas_dao_cobertura_efetiva_ao_que_a_sonda_generica_nao_alcanca(cenario):
    """Para cada combinacao funcao x parametro com sonda dirigida, nos dois sentidos (A contra B e B contra A): o registro
    proprio e encontrado, e o do outro usuario responde EXATAMENTE como um inexistente, sem alterar nada do dono."""
    conn = cenario['conn']
    fs = {f['nome']: f for f in I.funcoes_expostas(conn)}
    for d in 'AB':
        for semeador in cenario['semeados'][d].values():
            D.semear_dirigido(semeador)
    faltas = {f'{d}/{n}': {k: v for k, v in sem.falhas.items() if k.startswith('dirigido:')} for d in 'AB' for n, sem in cenario['semeados'][d].items()}
    assert not any(faltas.values()), f'registros dirigidos nao semeados: {faltas}'
    # as listas nao podem ficar com entrada velha: toda combinacao citada existe como parametro de funcao exposta
    for nome, parametro in [*D.CASOS, *D.NAO_APLICAVEIS]:
        assert nome in fs and parametro in (fs[nome]['nomes'] or [])[:fs[nome]['n']], f'{nome}({parametro}) nao existe mais'
    assert not set(D.CASOS) & set(D.NAO_APLICAVEIS)
    relatorio, ruins = [], []
    for (nome, parametro), caso in D.CASOS.items():
        tipo = caso.get('perfil', 'Pessoal')
        for atacante in 'AB':
            vitima = OUTRO[atacante]
            r = D.sondar(conn, fs[nome], parametro, caso, atacante, USUARIO[atacante], cenario['semeados'][atacante][tipo].alvos(),
                         cenario['semeados'][vitima][tipo].alvos(), cenario['perfis'][atacante][tipo], list(cenario['perfis'][vitima].values()), CATEGORIA)
            relatorio.append({'funcao': nome, 'parametro': parametro, 'atacante': atacante, **r})
            if r['conclusao'] != 'EFETIVA':
                ruins.append((nome, parametro, atacante, r['conclusao'], r.get('motivo')))
    gravar_relatorio('2b_sondas_dirigidas.json', relatorio)
    gravar_relatorio('2c_nao_aplicaveis.json', [{'funcao': n, 'parametro': p, 'motivo': m} for (n, p), m in D.NAO_APLICAVEIS.items()])
    falhas = [x for x in ruins if x[3] == 'FALHA']
    assert not falhas, f'REGISTRO DE OUTRO USUARIO ALCANCADO OU DISTINGUIDO: {falhas}'
    assert not ruins, f'sondas dirigidas sem conclusao (a logica de posse nao foi alcancada): {ruins}'
    assert len(relatorio) == 2 * len(D.CASOS) >= 80


# =====================================================================================================================
# 3. Sem sessao
# =====================================================================================================================

def test_nenhuma_funcao_e_executavel_sem_sessao_e_nenhuma_tabela_e_legivel_por_usuario(cenario):
    dsn = cenario['dsn']
    assert sql(dsn, """select count(*) n from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                        where n.nspname in ('financeiro', 'public') and p.prokind = 'f' and has_function_privilege('anon', p.oid, 'execute')
                          and n.nspname = 'financeiro'""")[0]['n'] == 0
    abertas = sql(dsn, """select n.nspname || '.' || c.relname t from pg_class c join pg_namespace n on n.oid = c.relnamespace
                           where c.relkind in ('r', 'p') and n.nspname in ('public', 'financeiro')
                             and (has_table_privilege('anon', c.oid, 'select, insert, update, delete')
                                  or has_table_privilege('authenticated', c.oid, 'insert, update, delete')
                                  or (has_table_privilege('authenticated', c.oid, 'select') and c.relname not in ('categorias', 'perfil_acesso')))""")
    assert abertas == []
    assert sql(dsn, """select count(*) n from pg_class c join pg_namespace n on n.oid = c.relnamespace
                        where c.relkind in ('r', 'p') and n.nspname in ('public', 'financeiro') and not c.relrowsecurity
                          and n.nspname = 'financeiro'""")[0]['n'] == 0
    f = next(x for x in I.funcoes_expostas(cenario['conn']) if x['nome'] == 'contas_do_mes')
    cod, _, ret = I.chamar(cenario['conn'], None, f, {'p_perfil_id': cenario['perfis']['A']['Pessoal'], 'p_mes': '2027-03-01'})
    assert cod == '42501' and ret == ''


# =====================================================================================================================
# 4. Positivos
# =====================================================================================================================

def test_nomes_iguais_entre_usuarios_e_unicos_por_dono_sem_diferenca_de_caixa_ou_espacos(cenario):
    dsn = cenario['dsn']
    for u in (USUARIO_A, USUARIO_B):
        for nome in ('Pessoal', '  pessoal ', 'PESSOAL', 'Empresa', 'empresa  '):
            e = erro(rpc, dsn, 'criar_perfil', {'nome': nome}, usuario=u)
            assert e.pgcode == '23505' and 'Ja existe perfil financeiro com este nome' in e.diag.message_primary
    # um nome novo para B que A ja usa em outro perfil: aceito (a existencia do nome em A nao aparece para B)
    a = rpc(dsn, 'criar_perfil', {'nome': 'Casa de praia'}, usuario=USUARIO_A)
    b = rpc(dsn, 'criar_perfil', {'nome': 'Casa  de  Praia'}, usuario=USUARIO_B)
    assert a['id'] != b['id']
    assert erro(rpc, dsn, 'atualizar_perfil', b['id'], {'nome': 'empresa'}, usuario=USUARIO_B).pgcode == '23505'
    assert rpc(dsn, 'atualizar_perfil', b['id'], {'nome': 'Sitio'}, usuario=USUARIO_B)['nome'] == 'Sitio'
    # "Pessoal" nao e mais nome especial: o perfil pode ser renomeado e o nome reutilizado pelo mesmo dono
    pb = cenario['perfis']['B']['Pessoal']
    assert rpc(dsn, 'atualizar_perfil', pb, {'nome': 'Minha casa'}, usuario=USUARIO_B)['nome'] == 'Minha casa'
    assert rpc(dsn, 'criar_perfil', {'nome': 'Pessoal'}, usuario=USUARIO_B)['nome'] == 'Pessoal'


def test_cada_usuario_ve_so_os_proprios_perfis_e_tem_o_proprio_perfil_padrao(cenario):
    dsn, perfis = cenario['dsn'], cenario['perfis']

    def meus(u):
        return {p['id']: p for p in (sql_como(dsn, u, 'select coalesce(json_agg(x), \'[]\') from financeiro.meus_perfis() x'))}

    assert set(perfis['B'].values()) <= set(meus(USUARIO_B)) and not set(perfis['A'].values()) & set(meus(USUARIO_B))
    assert set(perfis['A'].values()) <= set(meus(USUARIO_A)) and not set(perfis['B'].values()) & set(meus(USUARIO_A))
    padrao_a = [i for i, p in meus(USUARIO_A).items() if p['padrao']]
    assert padrao_a == [perfis['A']['Pessoal']]
    # B escolhe o seu: o de A nao muda
    assert rpc(dsn, 'definir_perfil_padrao', perfis['B']['Empresa'], usuario=USUARIO_B)['padrao'] is True
    assert [i for i, p in meus(USUARIO_B).items() if p['padrao']] == [perfis['B']['Empresa']]
    assert [i for i, p in meus(USUARIO_A).items() if p['padrao']] == padrao_a
    rpc(dsn, 'definir_perfil_padrao', perfis['B']['Pessoal'], usuario=USUARIO_B)
    assert [i for i, p in meus(USUARIO_B).items() if p['padrao']] == [perfis['B']['Pessoal']]
    assert [i for i, p in meus(USUARIO_A).items() if p['padrao']] == padrao_a
    # ninguem define, edita, inativa ou reativa o perfil do outro
    for funcao, args in (('definir_perfil_padrao', ()), ('atualizar_perfil', ({'nome': 'Tomado'},)), ('inativar_perfil', ()), ('reativar_perfil', ())):
        assert erro(rpc, dsn, funcao, perfis['A']['Empresa'], *args, usuario=USUARIO_B).pgcode == '42501', funcao
    assert sql(dsn, 'select nome, ativo, padrao from public.perfil_financeiro where id = %s', (perfis['A']['Empresa'],)) == [
        {'nome': 'Empresa', 'ativo': True, 'padrao': False}]
    assert sql(dsn, 'select count(*) n from public.perfil_financeiro where padrao group by user_id having count(*) > 1') == []


def sql_como(dsn, usuario, comando, params=()):
    conn = I.conectar(dsn)
    try:
        conn.autocommit = False
        I.como(conn, usuario)
        with conn.cursor() as cur:
            cur.execute(comando, params)
            return cur.fetchone()[0]
    finally:
        conn.rollback()
        conn.close()


def test_dono_e_fixo_e_so_o_dono_administra(cenario):
    dsn, perfis = cenario['dsn'], cenario['perfis']
    pa = perfis['A']['Empresa']
    assert sql(dsn, 'select user_id::text u from public.perfil_financeiro where id = %s', (pa,))[0]['u'] == USUARIO_A['id']
    # nem o dono do banco troca o dono por engano; nem se cria um segundo administrador
    assert 'dono do perfil financeiro nao pode ser alterado' in erro(sql, dsn, 'update public.perfil_financeiro set user_id = %s where id = %s',
                                                                    (USUARIO_B['id'], pa)).diag.message_primary
    assert 'Somente o dono' in erro(sql, dsn, "insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) "
                                              "values (%s, %s, 'TITULAR', true)", (USUARIO_B['id'], pa)).diag.message_primary
    # um vinculo de leitura dado administrativamente continua so leitura
    sql(dsn, "insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) values (%s, %s, 'LEITOR', false)", (USUARIO_B['id'], pa))
    assert sql_como(dsn, USUARIO_B, 'select financeiro.pode_acessar_perfil(%s)', (pa,)) is True
    assert sql_como(dsn, USUARIO_B, 'select financeiro.pode_gerir_perfil(%s)', (pa,)) is False
    assert erro(rpc, dsn, 'criar_despesa', pa, {'nome': 'x', 'valor': '1.00', 'categoria_id': CATEGORIA, 'data_vencimento': '2027-03-10'},
                str(uuid.uuid4()), usuario=USUARIO_B).pgcode == '42501'


# =====================================================================================================================
# 5. Tentativas especificas, com dados completos e gravando de verdade
# =====================================================================================================================

def _despesa(dsn, usuario, perfil, nome='Despesa propria', valor='50.00'):
    return rpc(dsn, 'criar_despesa', perfil, {'nome': nome, 'valor': valor, 'categoria_id': CATEGORIA, 'data_vencimento': '2027-03-10'},
               str(uuid.uuid4()), usuario=usuario)


def _pagamento(conta_bancaria, valor='50.00'):
    return {'conta_bancaria_id': conta_bancaria, 'data_pagamento': '2027-03-10', 'valor_pago': valor, 'valor_devido': valor}


def test_tentativas_especificas_nao_gravam_nada_nos_dados_do_outro_usuario(cenario):
    dsn, conn, perfis = cenario['dsn'], cenario['conn'], cenario['perfis']
    pa, pb = perfis['A']['Pessoal'], perfis['B']['Pessoal']
    atribuir(dsn, pb)  # pagamentos habilitados no perfil novo de B (o de A ja esta)
    va = cenario['semeados']['A']['Pessoal']
    alvo = va.alvos()
    banco_a = sql(dsn, "select id from public.conta_bancaria where perfil_financeiro_id = %s and nome = 'Conta Pessoal (A)'", (pa,))[0]['id']
    banco_b = sql(dsn, "insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, cor_display) "
                       "values (%s, 'Conta de B', 'Banco ficticio', 'Conta Corrente', 'ATIVO', '#3b82f6') returning id", (pb,))[0]['id']
    # A tem uma despesa pendente e uma paga, feitas pelas funcoes oficiais
    pend_a = _despesa(dsn, USUARIO_A, pa, 'Pendente de A')
    paga_a = rpc(dsn, 'criar_despesa_paga', pa, {'nome': 'Paga de A', 'valor': '70.00', 'categoria_id': CATEGORIA, 'data_vencimento': '2027-03-10'},
                 {'conta_bancaria_id': banco_a, 'data_pagamento': '2027-03-10'}, str(uuid.uuid4()), usuario=USUARIO_A)
    propria_b = _despesa(dsn, USUARIO_B, pb, 'Pendente de B')
    todos_a = list(perfis['A'].values())
    antes = I.retrato(conn, todos_a)
    n_mov = sql(dsn, 'select count(*) n from public.movimento_financeiro')[0]['n']
    chave = lambda: str(uuid.uuid4())  # noqa: E731

    tentativas = {
        'pagar despesa de A dizendo que e do perfil de A': lambda: rpc(dsn, 'pagar_despesa', pa, pend_a['conta_id'], _pagamento(banco_b), chave(), usuario=USUARIO_B),
        'pagar despesa de A pelo proprio perfil': lambda: rpc(dsn, 'pagar_despesa', pb, pend_a['conta_id'], _pagamento(banco_b), chave(), usuario=USUARIO_B),
        'pagar a propria despesa com a conta bancaria de A': lambda: rpc(dsn, 'pagar_despesa', pb, propria_b['conta_id'], _pagamento(banco_a), chave(), usuario=USUARIO_B),
        'cadastrar despesa paga com a conta bancaria de A': lambda: rpc(dsn, 'criar_despesa_paga', pb, {'nome': 'x', 'valor': '5.00', 'categoria_id': CATEGORIA, 'data_vencimento': '2027-03-10'},
                                                                        {'conta_bancaria_id': banco_a, 'data_pagamento': '2027-03-10'}, chave(), usuario=USUARIO_B),
        'cadastrar despesa em debito automatico na conta de A': lambda: rpc(dsn, 'criar_despesa', pb, {'nome': 'x', 'valor': '5.00', 'categoria_id': CATEGORIA, 'data_vencimento': '2027-03-10',
                                                                                                   'debito_automatico': True, 'conta_bancaria_id': banco_a}, chave(), usuario=USUARIO_B),
        'estornar o pagamento de A': lambda: rpc(dsn, 'estornar_pagamento_despesa', pb, paga_a['conta_id'], paga_a['pagamento']['movimento_id'],
                                                 {'motivo': 'tentativa', 'data_estorno': '2027-03-11'}, chave(), usuario=USUARIO_B),
        'estornar o pagamento de A dizendo que e do perfil de A': lambda: rpc(dsn, 'estornar_pagamento_despesa', pa, paga_a['conta_id'], paga_a['pagamento']['movimento_id'],
                                                                              {'motivo': 'tentativa', 'data_estorno': '2027-03-11'}, chave(), usuario=USUARIO_B),
        'pagar em lote despesas de A': lambda: rpc(dsn, 'pagar_despesas_lote', pb, {
            'itens': [{'conta_id': pend_a['conta_id'], 'valor_devido': '50.00'}], 'conta_bancaria_id': banco_b, 'data_pagamento': '2027-03-10',
            'lote': {'descricao': 'Pendente de A', 'competencia': '2027-03', 'recorrencias': [pend_a['item_id']], 'quantidade': 1, 'valor_total': '50.00'}},
            chave(), usuario=USUARIO_B),
        'editar despesa de A': lambda: rpc(dsn, 'editar_despesa', pb, pend_a['conta_id'], 'x', {'valor': '1.00'}, usuario=USUARIO_B),
        'excluir despesa de A': lambda: rpc(dsn, 'excluir_despesa', pb, pend_a['conta_id'], 'x', usuario=USUARIO_B),
        'cancelar despesa de A': lambda: rpc(dsn, 'cancelar_despesa', pb, pend_a['conta_id'], 'x', usuario=USUARIO_B),
        'pagar a fatura de A': lambda: rpc(dsn, 'pagar_fatura', pb, alvo['fatura'], _pagamento(banco_b, '1.00'), chave(), usuario=USUARIO_B),
        'lancar compra no cartao de A': lambda: rpc(dsn, 'criar_compra', pb, {'cartao_id': alvo['cartao'], 'descricao': 'x', 'valor': '10.00', 'data_compra': '2027-03-05',
                                                                         'categoria_id': CATEGORIA, 'mes_fatura': '2027-03-01', 'total_parcelas': 1}, chave(), usuario=USUARIO_B),
        'abrir o arquivo de um documento de A': lambda: rpc(dsn, 'arquivo_comprovante_tela', pb, alvo['public.ir_comprovante'], usuario=USUARIO_B),
        'abrir o arquivo de um documento de A dizendo que e do perfil de A': lambda: rpc(dsn, 'arquivo_comprovante_tela', pa, alvo['public.ir_comprovante'], usuario=USUARIO_B),
        'ler o financiamento de A': lambda: rpc(dsn, 'financiamento_tela', pb, alvo['public.financiamento'], usuario=USUARIO_B),
        'excluir o financiamento de A': lambda: rpc(dsn, 'excluir_financiamento', pb, alvo['public.financiamento'], usuario=USUARIO_B),
        'editar o consorcio de A': lambda: rpc(dsn, 'editar_consorcio', pb, alvo['public.contrato_consorcio'], {'nome': 'Tomado'}, usuario=USUARIO_B),
        'excluir o consorcio de A': lambda: rpc(dsn, 'excluir_consorcio', pb, alvo['public.contrato_consorcio'], usuario=USUARIO_B),
        'estornar o recebimento de A': lambda: rpc(dsn, 'estornar_recebimento', pb, alvo['public.receita_realizada'], {'motivo': 'tentativa', 'data_estorno': '2027-03-11'}, chave(), usuario=USUARIO_B),
        'ler as receitas de A': lambda: rpc(dsn, 'receitas_lancamentos_tela', pa, '2027-03-01', None, usuario=USUARIO_B),
        'editar o veiculo de A': lambda: rpc(dsn, 'editar_veiculo', pb, alvo['public.veiculo'], {'nome': 'Tomado'}, usuario=USUARIO_B),
        'editar a conta bancaria de A': lambda: rpc(dsn, 'editar_conta_bancaria', pb, banco_a, 'x', {'nome': 'Tomada'}, usuario=USUARIO_B),
        'ajustar o saldo da conta de A': lambda: rpc(dsn, 'ajustar_saldo_conta', pb, banco_a, {'saldo_informado': '1.00', 'data': '2027-03-10', 'motivo': 'x'}, chave(), usuario=USUARIO_B),
    }
    resultados = []
    for descricao, tentar in tentativas.items():
        try:
            r = tentar()
            resultados.append((descricao, 'RESPONDEU', json.dumps(r, default=str)[:200]))
        except psycopg2.Error as e:
            resultados.append((descricao, e.pgcode, (e.diag.message_primary or '')[:120]))
            assert not I.vazou('', e.diag.message_primary, 'A'), descricao
    gravar_relatorio('5_tentativas_especificas.json', [dict(tentativa=d, codigo=c, mensagem=m) for d, c, m in resultados])
    responderam = [r for r in resultados if r[1] == 'RESPONDEU']
    assert not responderam, f'tentativa indevida respondeu sem recusa: {responderam}'
    # nenhuma recusa pode ser so "erro de dados": cada tentativa tem de ter sido negada por autorizacao ou por nao encontrar
    fracas = [r for r in resultados if I.classificar(r[1], r[2], '') != 'recusada']
    assert not fracas, f'tentativa barrada so pela validacao dos dados (nao prova o isolamento): {fracas}'
    # os dados de A, os saldos de A e a quantidade de movimentos: identicos
    assert I.retrato(conn, todos_a) == antes
    assert sql(dsn, 'select count(*) n from public.movimento_financeiro')[0]['n'] == n_mov
    assert sql(dsn, 'select status_pagamento s from public.conta where id = %s', (propria_b['conta_id'],))[0]['s'] == 'Pendente'

    # e o legitimo continua funcionando: B paga e estorna a propria despesa na propria conta
    r = rpc(dsn, 'pagar_despesa', pb, propria_b['conta_id'], _pagamento(banco_b), chave(), usuario=USUARIO_B)
    assert Decimal(str(r['valor_pago'])) == Decimal('50.00') and r['conta_bancaria_id'] == banco_b
    rpc(dsn, 'estornar_pagamento_despesa', pb, propria_b['conta_id'], r['movimento_id'], {'motivo': 'teste', 'data_estorno': '2027-03-11'}, chave(), usuario=USUARIO_B)
    paga_b = rpc(dsn, 'criar_despesa_paga', pb, {'nome': 'Paga de B', 'valor': '12.00', 'categoria_id': CATEGORIA, 'data_vencimento': '2027-03-10'},
                 {'conta_bancaria_id': banco_b, 'data_pagamento': '2027-03-10'}, chave(), usuario=USUARIO_B)
    assert paga_b['paga'] is True and paga_b['pagamento']['conta_bancaria_id'] == banco_b
    assert I.retrato(conn, todos_a) == antes


# =====================================================================================================================
# 6. Indices de TR: referencia global, manutencao so do administrador da plataforma
# =====================================================================================================================

def test_indices_de_tr_leitura_para_todos_e_manutencao_so_do_administrador(cenario):
    dsn = cenario['dsn']
    tr = {'competencia': '2031-01', 'valor_percentual': '0.10'}
    # no cenario base A e o administrador (como o titular real): aqui os dois comecam como usuarios comuns
    sql(dsn, 'select financeiro.definir_administrador_plataforma(%s, false, %s, %s)', (USUARIO_A['id'], 'teste', 'cenario ficticio'))
    assert sql_como(dsn, USUARIO_A, 'select financeiro.sou_administrador_plataforma()') is False
    for u in (USUARIO_A, USUARIO_B):
        for funcao, args in (('criar_tr', (tr, str(uuid.uuid4()))), ('importar_tr', ({'texto': '2031-02;0,10'}, str(uuid.uuid4()))),
                             ('editar_tr', ('2031-01', {'valor_percentual': '0.20'}))):
            e = erro(rpc, dsn, funcao, *args, usuario=u)
            assert e.pgcode == '42501' and 'administrador da plataforma' in e.diag.message_primary, funcao
        assert isinstance(rpc(dsn, 'tr_oficial_tela', 2031, None, None, usuario=u), (dict, list))  # leitura continua
    assert sql(dsn, "select count(*) n from public.indice_tr_mensal where competencia like '2031-%%'")[0]['n'] == 0
    # A vira administrador (ato administrativo, pelo dono do banco): mantem os indices, com auditoria
    sql(dsn, 'select financeiro.definir_administrador_plataforma(%s, true, %s, %s)', (USUARIO_A['id'], 'teste', 'cenario ficticio'))
    assert sql_como(dsn, USUARIO_A, 'select financeiro.sou_administrador_plataforma()') is True
    assert rpc(dsn, 'criar_tr', tr, str(uuid.uuid4()), usuario=USUARIO_A)['data']['competencia'] == '2031-01'
    assert sql(dsn, "select count(*) n from financeiro.indice_tr_historico where competencia = '2031-01'")[0]['n'] == 1
    # ser administrador nao da acesso a dado financeiro de ninguem
    pb = cenario['perfis']['B']['Pessoal']
    assert erro(rpc, dsn, 'contas_do_mes', pb, '2027-03-01', usuario=USUARIO_A).pgcode == '42501'
    assert sql_como(dsn, USUARIO_A, 'select financeiro.pode_acessar_perfil(%s)', (pb,)) is False
    assert erro(rpc, dsn, 'criar_tr', {'competencia': '2031-03', 'valor_percentual': '0.10'}, str(uuid.uuid4()), usuario=USUARIO_B).pgcode == '42501'
    # a funcao que concede a administracao nao e executavel por usuarios
    assert sql(dsn, """select has_function_privilege('authenticated', 'financeiro.definir_administrador_plataforma(uuid, boolean, text, text)', 'execute') a,
                              has_function_privilege('authenticated', 'financeiro.definir_guarda_sem_perfil(integer, text, text)', 'execute') g""") == [{'a': False, 'g': False}]


# =====================================================================================================================
# 7. Registros sem perfil: guarda explicita, nunca pelo nome
# =====================================================================================================================

def test_registro_sem_perfil_nao_vai_para_quem_tem_um_perfil_chamado_pessoal(cenario):
    dsn, perfis = cenario['dsn'], cenario['perfis']
    assert sql(dsn, 'select perfil_financeiro_id p from financeiro.guarda_sem_perfil') == [{'p': perfis['A']['Pessoal']}]

    def contas(u, perfil):
        return [c['nome'] for c in tabela(dsn, 'contas_bancarias_do_perfil', perfil, usuario=u)]

    assert 'Carteira legado sem perfil' in contas(USUARIO_A, perfis['A']['Pessoal'])
    assert 'Carteira legado sem perfil' not in contas(USUARIO_B, perfis['B']['Pessoal'])  # B tambem tem um "Pessoal"
    # retirada a guarda, o registro sem perfil nao e de ninguem
    sql(dsn, 'select financeiro.definir_guarda_sem_perfil(null, %s, %s)', ('teste', 'registros regularizados'))
    assert 'Carteira legado sem perfil' not in contas(USUARIO_A, perfis['A']['Pessoal'])
    assert 'Carteira legado sem perfil' not in contas(USUARIO_B, perfis['B']['Pessoal'])
    # nenhuma funcao decide posse pelo nome do perfil
    assert sql(dsn, """select count(*) n from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                        where n.nspname = 'financeiro' and regexp_replace(p.prosrc, '--[^\n]*', '', 'g') ~ 'nome\\s*=\\s*''Pessoal'''""")[0]['n'] == 0
