"""
Testes FIN-CADASTROS-PADRAO-01 (migration 20270101090000) — catalogo padrao do aplicativo e personalizacao por usuario, em
cluster PostgreSQL local descartavel e com dados ficticios.

Dois usuarios independentes (A e B), cada um com dois perfis. Conferido: os dois veem o catalogo padrao; categorias
particulares nao se misturam nem entram em registro de outro dono; a categoria padrao e protegida; palavras-chave em camadas
(ajuste de um nao alcanca o outro; mudanca do administrador respeita os ajustes; nada ja classificado muda); categorias de
cartao copiadas do modelo para cada perfil, sem duplicar, protegidas e independentes; carga inicial e reversao.
"""
import json
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_supabase_cartoes import ASSINATURAS, CARTAO, MORADIA, banco, comprar, rpc, tabela  # noqa: F401
from tests.test_supabase_categorias_consolidacao import executar_arquivo
from tests.test_supabase_categorias_recorrencias import catalogo_novo, erro
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, USUARIO_B, atribuir, cluster, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')
RAIZ = Path(__file__).resolve().parent.parent
REVERSAO = RAIZ / 'supabase' / 'reversao' / '20270101090000_cadastros_padrao_anterior.sql'
PESSOAL = ID['PESSOAL']
chave = lambda: str(uuid.uuid4())  # noqa: E731


@pytest.fixture
def c(banco):
    """A (gestor do catalogo e administrador, como o titular): Pessoal + Empresa. B (usuario comum): Pessoal + Empresa."""
    catalogo_novo(banco)
    perfis = {'A': {'Pessoal': PESSOAL, 'Empresa': rpc(banco, 'criar_perfil', {'nome': 'Empresa'}, usuario=USUARIO_A)['id']},
              'B': {n: rpc(banco, 'criar_perfil', {'nome': n}, usuario=USUARIO_B)['id'] for n in ('Pessoal', 'Empresa')}}
    return {'dsn': banco, 'perfis': perfis, 'pa': PESSOAL, 'pb': perfis['B']['Pessoal']}


def nomes(dsn, usuario):
    return {x['nome'] for x in tabela(dsn, 'categorias_de_despesa', usuario=usuario)}


def tela(dsn, usuario, perfil):
    return {x['id']: x for x in rpc(dsn, 'categorias_tela', perfil, None, usuario=usuario)}


def sugestao(dsn, perfil, texto):
    return sql(dsn, 'select financeiro.sugestao_categoria_importacao(%s, %s, %s, null) s', (perfil, texto.lower(), texto.lower()))[0]['s']


def palavras(dsn, usuario, perfil, categoria):
    return {p['palavra']: p for p in rpc(dsn, 'palavras_chave_tela', perfil, usuario=usuario).get(str(categoria), [])}


def palavra_padrao(dsn, categoria, palavra):
    return sql(dsn, 'insert into public.categoria_palavra_chave (categoria_id, palavra, ativo) values (%s, %s, true) returning id', (categoria, palavra))[0]['id']


def digest(dsn):
    return sql(dsn, """select (select md5(coalesce(string_agg(x::text, '|' order by x.id), '')) from public.categoria x) categorias,
        (select md5(coalesce(string_agg(x::text, '|' order by x.id), '')) from public.categoria_palavra_chave x) palavras,
        (select md5(coalesce(string_agg(x::text, '|' order by x.id), '')) from public.categoria_cartao x) cartao,
        (select md5(coalesce(string_agg(x::text, '|' order by x.id), '')) from public.categoria_cartao_despesa x) vinculos,
        (select md5(coalesce(string_agg(x::text, '|' order by x.id), '')) from public.lancamento_agregado x) compras,
        (select md5(coalesce(string_agg(x::text, '|' order by x.id), '')) from public.item_despesa x) itens,
        (select count(*) from financeiro.palavra_chave_usuario) ajustes, (select count(*) from financeiro.categoria_cartao_padrao) modelo""")[0]


# =====================================================================================================================
# 1. Categorias de despesa: padrao para todos, particulares de cada um
# =====================================================================================================================

def test_os_dois_veem_o_catalogo_padrao_e_as_particulares_nao_se_misturam(c):
    dsn, pa, pb = c['dsn'], c['pa'], c['pb']
    padrao = nomes(dsn, USUARIO_A)
    assert padrao and nomes(dsn, USUARIO_B) == padrao
    assert all(x['padrao'] for x in tela(dsn, USUARIO_B, pb).values())

    pets_a = rpc(dsn, 'criar_categoria', {'nome': 'Pets', 'natureza': 'CONSUMO'}, chave(), usuario=USUARIO_A)
    pets_b = rpc(dsn, 'criar_categoria', {'nome': 'pets'}, chave(), usuario=USUARIO_B)  # mesmo nome, outro dono
    assert pets_a['padrao'] is False and pets_a['categoria_id'] != pets_b['categoria_id']
    assert nomes(dsn, USUARIO_A) == padrao | {'Pets'} and nomes(dsn, USUARIO_B) == padrao | {'pets'}
    for perfil in c['perfis']['A'].values():  # vale em todos os perfis do dono
        assert tela(dsn, USUARIO_A, perfil)[pets_a['categoria_id']]['padrao'] is False
        assert pets_b['categoria_id'] not in tela(dsn, USUARIO_A, perfil)
    assert pets_a['categoria_id'] not in tela(dsn, USUARIO_B, pb)
    assert pets_a['categoria_id'] not in {x['categoria_id'] for x in rpc(dsn, 'naturezas_das_categorias', usuario=USUARIO_B)}
    donos = sql(dsn, 'select id, user_id::text u from public.categoria where id = any(%s) order by id', ([pets_a['categoria_id'], pets_b['categoria_id']],))
    assert [d['u'] for d in donos] == [USUARIO_A['id'], USUARIO_B['id']]

    # nome repetido: nem o de uma categoria padrao, nem o de outra particular do MESMO dono
    um_padrao = sql(dsn, 'select nome from public.categoria where id = %s', (MORADIA,))[0]['nome']
    for nome in (um_padrao, um_padrao.upper(), ' Pets '):
        assert 'Ja existe uma categoria com este nome' in erro(rpc, dsn, 'criar_categoria', {'nome': nome}, chave(), usuario=USUARIO_A).diag.message_primary
    # repetir a mesma chave nao cria outra
    k = chave()
    um = rpc(dsn, 'criar_categoria', {'nome': 'Viagens'}, k, usuario=USUARIO_A)
    assert rpc(dsn, 'criar_categoria', {'nome': 'Viagens'}, k, usuario=USUARIO_A)['categoria_id'] == um['categoria_id']


def test_categoria_particular_de_um_nao_entra_nem_e_alterada_por_outro(c):
    dsn, pa, pb = c['dsn'], c['pa'], c['pb']
    atribuir(dsn, pb)
    pets = rpc(dsn, 'criar_categoria', {'nome': 'Pets'}, chave(), usuario=USUARIO_A)['categoria_id']
    despesa = {'nome': 'Racao', 'valor': '50.00', 'categoria_id': pets, 'data_vencimento': '2029-05-10'}
    # A usa a propria categoria; B nao consegue (nem pelo cadastro, nem por edicao), e nada de B e gravado
    ok = rpc(dsn, 'criar_despesa', pa, despesa, chave(), usuario=USUARIO_A)
    n = sql(dsn, 'select count(*) n from public.item_despesa')[0]['n']
    e = erro(rpc, dsn, 'criar_despesa', pb, despesa, chave(), usuario=USUARIO_B)
    assert 'Categoria' in e.diag.message_primary and sql(dsn, 'select count(*) n from public.item_despesa')[0]['n'] == n
    de_b = rpc(dsn, 'criar_despesa', pb, {**despesa, 'categoria_id': MORADIA}, chave(), usuario=USUARIO_B)
    assert erro(sql, dsn, 'update public.item_despesa set categoria_id = %s where id = %s', (pets, de_b['item_id'])).diag.message_primary == 'Categoria de Despesa nao encontrada'
    # B nao edita, nao exclui, nao muda a natureza: para ele a categoria nao existe
    for funcao, args in (('editar_categoria', ({'nome': 'Tomada'},)), ('excluir_categoria', ()), ('definir_natureza_categoria', ('APORTE', chave()))):
        ex = erro(rpc, dsn, funcao, pets, *args, usuario=USUARIO_B)
        assert ex.diag.message_primary == 'Categoria nao encontrada', funcao
    assert erro(rpc, dsn, 'criar_minha_palavra_chave', pets, 'racao', usuario=USUARIO_B).diag.message_primary == 'Categoria de Despesa nao encontrada'
    # o dono edita; com registro vinculado nao exclui: inativa, e o historico fica
    assert rpc(dsn, 'editar_categoria', pets, {'nome': 'Animais', 'descricao': 'Caes e gatos'}, usuario=USUARIO_A)['nome'] == 'Animais'
    assert 'Inative-a' in erro(rpc, dsn, 'excluir_categoria', pets, usuario=USUARIO_A).diag.message_primary
    assert rpc(dsn, 'editar_categoria', pets, {'ativo': False}, usuario=USUARIO_A)['ativo'] is False
    assert sql(dsn, 'select categoria_id from public.item_despesa where id = %s', (ok['item_id'],))[0]['categoria_id'] == pets
    assert 'Animais' not in nomes(dsn, USUARIO_A)  # inativa: fora das escolhas, mas ainda na tela de categorias
    assert tela(dsn, USUARIO_A, pa)[pets]['ativo'] is False
    # sem registros, a particular e excluida
    livre = rpc(dsn, 'criar_categoria', {'nome': 'Sem uso'}, chave(), usuario=USUARIO_A)['categoria_id']
    assert rpc(dsn, 'excluir_categoria', livre, usuario=USUARIO_A)['excluida'] is True


def test_categoria_padrao_e_protegida_do_usuario_comum_e_mantida_por_quem_administra(c):
    dsn = c['dsn']
    antes = digest(dsn)
    for funcao, args in (('editar_categoria', (MORADIA, {'nome': 'Minha moradia'})), ('excluir_categoria', (MORADIA,)),
                         ('definir_natureza_categoria', (MORADIA, 'APORTE', chave())), ('criar_categoria', ({'nome': 'Global de B', 'padrao': True}, chave())),
                         ('criar_palavra_chave', (MORADIA, 'palavra de b')), ('incorporar_categoria', (MORADIA, ASSINATURAS, {}, 'x', chave()))):
        assert erro(rpc, dsn, funcao, *args, usuario=USUARIO_B).pgcode == '42501', funcao
    assert digest(dsn) == antes
    # quem administra o catalogo (A) cria e edita a padrao; ela aparece para os dois
    nova = rpc(dsn, 'criar_categoria', {'nome': 'Seguros', 'padrao': True}, chave(), usuario=USUARIO_A)
    assert nova['padrao'] is True and 'Seguros' in nomes(dsn, USUARIO_B)
    assert sql(dsn, 'select user_id from public.categoria where id = %s', (nova['categoria_id'],))[0]['user_id'] is None
    assert rpc(dsn, 'editar_categoria', nova['categoria_id'], {'descricao': 'Seguros em geral'}, usuario=USUARIO_A)['padrao'] is True
    # palavra-chave padrao nao pode apontar para categoria particular
    particular = rpc(dsn, 'criar_categoria', {'nome': 'So de A'}, chave(), usuario=USUARIO_A)['categoria_id']
    assert erro(rpc, dsn, 'criar_palavra_chave', particular, 'algo', usuario=USUARIO_A).diag.message_primary == 'Categoria de Despesa nao encontrada'


def test_natureza_da_particular_e_do_dono_e_so_muda_a_classificacao_gerencial(c):
    dsn, pa = c['dsn'], c['pa']
    cofre = rpc(dsn, 'criar_categoria', {'nome': 'Cofrinho', 'natureza': 'APORTE'}, chave(), usuario=USUARIO_A)['categoria_id']
    assert tela(dsn, USUARIO_A, pa)[cofre]['natureza'] == 'APORTE'
    rpc(dsn, 'criar_despesa', pa, {'nome': 'Guardar', 'valor': '300.00', 'categoria_id': cofre, 'data_vencimento': '2029-06-10', 'competencia': '2029-06-01'},
        chave(), usuario=USUARIO_A)
    saldos = sql(dsn, 'select md5(string_agg(id || coalesce(saldo_atual::text, \'\'), \'|\' order by id)) h from public.conta_bancaria')[0]['h']
    i1 = rpc(dsn, 'indicadores_gerenciais', pa, '2029-06', usuario=USUARIO_A)
    assert Decimal(str(i1['aportes'])) == Decimal('300.00')
    rpc(dsn, 'definir_natureza_categoria', cofre, 'CONSUMO', chave(), usuario=USUARIO_A)
    i2 = rpc(dsn, 'indicadores_gerenciais', pa, '2029-06', usuario=USUARIO_A)
    assert Decimal(str(i2['aportes'])) == 0 and Decimal(str(i2['fluxo_total'])) == Decimal(str(i1['fluxo_total']))  # o total nao muda
    assert sql(dsn, 'select md5(string_agg(id || coalesce(saldo_atual::text, \'\'), \'|\' order by id)) h from public.conta_bancaria')[0]['h'] == saldos
    assert erro(rpc, dsn, 'criar_categoria', {'nome': 'Errada', 'natureza': 'QUALQUER'}, chave(), usuario=USUARIO_A).diag.message_primary == 'Natureza gerencial invalida'


# =====================================================================================================================
# 2. Palavras-chave: padrao + ajustes de cada usuario
# =====================================================================================================================

def test_ajuste_de_um_usuario_nao_alcanca_o_outro_e_nada_classificado_muda(c):
    dsn, pa, pb = c['dsn'], c['pa'], c['pb']
    pid = palavra_padrao(dsn, MORADIA, 'xptoloja')
    comprar(dsn, descricao='XPTOLOJA 123', categoria_id=MORADIA)
    compras_antes = digest(dsn)['compras']
    for perfil in (pa, pb):
        s = sugestao(dsn, perfil, 'xptoloja 123')
        assert (s['categoria_id'], s['origem']) == (MORADIA, 'palavra_chave')
    assert palavras(dsn, USUARIO_B, pb, MORADIA)['xptoloja'] == {**palavras(dsn, USUARIO_B, pb, MORADIA)['xptoloja'], 'id': pid, 'origem': 'PADRAO', 'ativo': True}

    # B desliga a palavra padrao: so para B (em todos os perfis dele)
    rpc(dsn, 'desligar_palavra_chave_padrao', pid, usuario=USUARIO_B)
    for perfil in c['perfis']['B'].values():
        assert sugestao(dsn, perfil, 'xptoloja 123')['origem'] == 'sem_sugestao'
    assert sugestao(dsn, pa, 'xptoloja 123')['categoria_id'] == MORADIA
    desligada = palavras(dsn, USUARIO_B, pb, MORADIA)['xptoloja']
    assert (desligada['ativo'], desligada['origem']) == (False, 'DESLIGADA') and desligada['id'] < 0
    assert palavras(dsn, USUARIO_A, pa, MORADIA)['xptoloja']['origem'] == 'PADRAO'
    # o catalogo padrao nao mudou
    assert sql(dsn, 'select ativo from public.categoria_palavra_chave where id = %s', (pid,))[0]['ativo'] is True

    # B restaura; depois reassocia a mesma palavra a uma categoria PARTICULAR dele
    assert rpc(dsn, 'remover_minha_palavra_chave', -desligada['id'], usuario=USUARIO_B)['volta_ao_padrao'] is True
    assert sugestao(dsn, pb, 'xptoloja 123')['categoria_id'] == MORADIA
    casa_b = rpc(dsn, 'criar_categoria', {'nome': 'Casa de B'}, chave(), usuario=USUARIO_B)['categoria_id']
    rpc(dsn, 'reassociar_palavra_chave_padrao', pid, casa_b, usuario=USUARIO_B)
    assert sugestao(dsn, pb, 'xptoloja 123')['categoria_id'] == casa_b
    assert sugestao(dsn, pa, 'xptoloja 123')['categoria_id'] == MORADIA
    # FIN-MULTIUSUARIO-AJUSTES-FINAIS-01: na categoria de origem a palavra aparece INATIVA, como MOVIDA, para poder ser restaurada
    movida = palavras(dsn, USUARIO_B, pb, MORADIA)['xptoloja']
    assert (movida['ativo'], movida['origem']) == (False, 'MOVIDA') and movida['categoria_destino_id'] is not None
    assert palavras(dsn, USUARIO_B, pb, casa_b)['xptoloja']['origem'] == 'REASSOCIADA'
    # A nao reassocia para a categoria particular de B
    assert erro(rpc, dsn, 'reassociar_palavra_chave_padrao', pid, casa_b, usuario=USUARIO_A).diag.message_primary == 'Categoria de Despesa nao encontrada'

    # palavras proprias: cada um a sua, na mesma categoria padrao, sem aparecer para o outro
    propria = rpc(dsn, 'criar_minha_palavra_chave', ASSINATURAS, '  Clube  Do   Livro ', usuario=USUARIO_A)
    assert (propria['palavra'], propria['origem']) == ('clube do livro', 'PROPRIA') and propria['id'] < 0
    assert sugestao(dsn, pa, 'pagamento clube do livro')['categoria_id'] == ASSINATURAS
    assert sugestao(dsn, pb, 'pagamento clube do livro')['origem'] == 'sem_sugestao'
    assert 'clube do livro' not in palavras(dsn, USUARIO_B, pb, ASSINATURAS)
    assert 'Palavra-chave ja cadastrada' in erro(rpc, dsn, 'criar_minha_palavra_chave', ASSINATURAS, 'clube do livro', usuario=USUARIO_A).diag.message_primary
    assert 'Palavra-chave ja cadastrada' in erro(rpc, dsn, 'criar_minha_palavra_chave', MORADIA, 'xptoloja', usuario=USUARIO_A).diag.message_primary
    # nem direto na tabela (rede de protecao nos dados): ajuste de A apontando para a categoria particular de B e recusado
    for coluna, tipo, extra in (('categoria_id', 'NOVA', 'null'), ('categoria_padrao_id', 'DESLIGADA', 'null')):
        campos = 'categoria_id, categoria_padrao_id' if coluna == 'categoria_id' else 'categoria_padrao_id, categoria_id'
        e = erro(sql, dsn, f"insert into financeiro.palavra_chave_usuario (user_id, tipo, palavra, {campos}) values (%s, %s, 'direto', %s, {extra})",
                 (USUARIO_A['id'], tipo, casa_b))
        assert e.diag.message_primary == 'Categoria de Despesa nao encontrada', coluna
    # ninguem remove o ajuste do outro
    assert erro(rpc, dsn, 'remover_minha_palavra_chave', -propria['id'], usuario=USUARIO_B).diag.message_primary == 'Palavra-chave nao encontrada'
    # nenhuma compra ja classificada mudou de categoria
    assert digest(dsn)['compras'] == compras_antes
    assert {r['categoria_id'] for r in sql(dsn, "select categoria_id from public.lancamento_agregado where descricao = 'XPTOLOJA 123'")} == {MORADIA}


def test_mudanca_do_administrador_alcanca_quem_nao_ajustou_e_respeita_quem_ajustou(c):
    dsn, pa, pb = c['dsn'], c['pa'], c['pb']
    pid = palavra_padrao(dsn, MORADIA, 'lojaum')
    rpc(dsn, 'desligar_palavra_chave_padrao', pid, usuario=USUARIO_B)  # B personalizou esta palavra
    # o administrador retira a regra padrao e depois a recoloca: B continua com a propria escolha
    rpc(dsn, 'remover_palavra_chave', MORADIA, pid, usuario=USUARIO_A)
    assert sugestao(dsn, pa, 'lojaum')['origem'] == 'sem_sugestao'
    rpc(dsn, 'criar_palavra_chave', MORADIA, 'lojaum', usuario=USUARIO_A)
    assert sugestao(dsn, pa, 'lojaum')['categoria_id'] == MORADIA       # quem nao ajustou recebe a mudanca
    assert sugestao(dsn, pb, 'lojaum')['origem'] == 'sem_sugestao'      # quem ajustou mantem
    # regra padrao nova: chega aos dois
    rpc(dsn, 'criar_palavra_chave', ASSINATURAS, 'lojadois', usuario=USUARIO_A)
    assert sugestao(dsn, pa, 'lojadois')['categoria_id'] == ASSINATURAS and sugestao(dsn, pb, 'lojadois')['categoria_id'] == ASSINATURAS
    # reassociacao de B: vale enquanto a regra de origem existir; retirada a regra, some para B tambem
    p2 = sql(dsn, "select id from public.categoria_palavra_chave where categoria_id = %s and palavra = 'lojadois'", (ASSINATURAS,))[0]['id']
    rpc(dsn, 'reassociar_palavra_chave_padrao', p2, MORADIA, usuario=USUARIO_B)
    assert sugestao(dsn, pb, 'lojadois')['categoria_id'] == MORADIA
    rpc(dsn, 'remover_palavra_chave', ASSINATURAS, p2, usuario=USUARIO_A)
    assert sugestao(dsn, pb, 'lojadois')['origem'] == 'sem_sugestao' and sugestao(dsn, pa, 'lojadois')['origem'] == 'sem_sugestao'


# =====================================================================================================================
# 3. Categorias de cartao: modelo copiado para cada perfil
# =====================================================================================================================

def modelo(dsn, nome, despesas=(), **extra):
    return rpc(dsn, 'manter_categoria_cartao_padrao', {'nome': nome, 'despesas': list(despesas), **extra}, usuario=USUARIO_A)['id']


def do_perfil(dsn, perfil):
    return sql(dsn, 'select id, nome, ativo, padrao_id, cor from public.categoria_cartao where perfil_financeiro_id = %s order by nome, id', (perfil,))


def test_perfil_novo_recebe_o_modelo_sem_duplicar_e_cada_perfil_e_independente(c):
    dsn, pa, pb = c['dsn'], c['pa'], c['pb']
    existentes_a = do_perfil(dsn, pa)
    nome_existente = existentes_a[0]['nome']
    m1 = modelo(dsn, nome_existente, [ASSINATURAS], cor='#112233')  # mesmo nome de uma categoria que A ja tem
    m2 = modelo(dsn, 'Farmacia', [MORADIA], ordem=2)
    assert erro(rpc, dsn, 'manter_categoria_cartao_padrao', {'nome': 'De B'}, usuario=USUARIO_B).pgcode == '42501'
    assert erro(rpc, dsn, 'propagar_categorias_cartao_padrao', usuario=USUARIO_B).pgcode == '42501'
    assert erro(rpc, dsn, 'categorias_cartao_padrao_tela', usuario=USUARIO_B).pgcode == '42501'

    # perfil novo de B ja nasce com as duas, com os vinculos
    novo = rpc(dsn, 'criar_perfil', {'nome': 'Casa nova'}, usuario=USUARIO_B)['id']
    copias = do_perfil(dsn, novo)
    assert [(x['nome'], x['padrao_id']) for x in copias] == sorted([(nome_existente, m1), ('Farmacia', m2)])
    vinc = sql(dsn, 'select categoria_cartao_id, categoria_id from public.categoria_cartao_despesa where perfil_financeiro_id = %s and ativo order by 2', (novo,))
    assert sorted(v['categoria_id'] for v in vinc) == sorted([ASSINATURAS, MORADIA])

    # perfis que ja existiam: o dono pede; A ADOTA a que ja tinha (mesmo id) e recebe a que faltava; repetir nao muda nada
    assert erro(rpc, dsn, 'inicializar_categorias_cartao_do_perfil', pa, usuario=USUARIO_B).pgcode == '42501'
    r1 = rpc(dsn, 'inicializar_categorias_cartao_do_perfil', pa, usuario=USUARIO_A)
    assert (r1['criadas'], r1['adotadas']) == (1, 1)
    depois = do_perfil(dsn, pa)
    assert {x['id'] for x in existentes_a} <= {x['id'] for x in depois} and len(depois) == len(existentes_a) + 1
    adotada = next(x for x in depois if x['id'] == existentes_a[0]['id'])
    assert adotada['padrao_id'] == m1 and adotada['cor'] == existentes_a[0]['cor']  # adotar nao muda mais nada
    estado = digest(dsn)
    r2 = rpc(dsn, 'inicializar_categorias_cartao_do_perfil', pa, usuario=USUARIO_A)
    assert (r2['criadas'], r2['adotadas'], r2['vinculos']) == (0, 0, 0) and digest(dsn) == estado
    assert rpc(dsn, 'propagar_categorias_cartao_padrao', usuario=USUARIO_A)['perfis'] >= 4
    for perfil in list(c['perfis']['A'].values()) + list(c['perfis']['B'].values()):
        linhas = [x for x in do_perfil(dsn, perfil) if x['padrao_id']]
        assert sorted(x['padrao_id'] for x in linhas) == sorted([m1, m2]), perfil  # uma de cada, sem duplicar
    estado = digest(dsn)
    rpc(dsn, 'propagar_categorias_cartao_padrao', usuario=USUARIO_A)
    assert digest(dsn) == estado

    # protecao: nome e situacao da padrao; cor, descricao e categorias adicionais continuam livres; perfis independentes
    atribuir(dsn, novo)
    farmacia = next(x for x in do_perfil(dsn, novo) if x['padrao_id'] == m2)
    for dados in ({'nome': 'Drogaria'}, {'ativo': False}):
        e = erro(rpc, dsn, 'editar_categoria_cartao', novo, farmacia['id'], dados, usuario=USUARIO_B)
        assert e.diag.message_hint == 'CATEGORIA_PADRAO'
    assert erro(rpc, dsn, 'desativar_categoria_cartao', novo, farmacia['id'], usuario=USUARIO_B).diag.message_hint == 'CATEGORIA_PADRAO'
    assert rpc(dsn, 'editar_categoria_cartao', novo, farmacia['id'], {'cor': '#abcdef', 'nome': ' farmacia '}, usuario=USUARIO_B)['cor'] == '#abcdef'
    assert [x['cor'] for x in do_perfil(dsn, pa) if x['padrao_id'] == m2] != ['#abcdef']
    extra = rpc(dsn, 'criar_categoria_cartao', novo, {'nome': 'Jogos'}, usuario=USUARIO_B)
    assert rpc(dsn, 'editar_categoria_cartao', novo, extra['id'], {'nome': 'Games'}, usuario=USUARIO_B)['nome'] == 'Games'
    assert rpc(dsn, 'desativar_categoria_cartao', novo, extra['id'], usuario=USUARIO_B)['ativo'] is False
    assert erro(rpc, dsn, 'editar_categoria_cartao', pb, farmacia['id'], {'cor': '#000000'}, usuario=USUARIO_B).pgcode is not None  # de outro perfil: nao encontrada
    assert erro(rpc, dsn, 'editar_categoria_cartao', novo, farmacia['id'], {'cor': '#000000'}, usuario=USUARIO_A).pgcode == '42501'
    # o modelo so aceita vinculo com categoria de despesa padrao
    particular = rpc(dsn, 'criar_categoria', {'nome': 'So de A'}, chave(), usuario=USUARIO_A)['categoria_id']
    assert 'categoria de despesa padrao' in erro(rpc, dsn, 'manter_categoria_cartao_padrao', {'id': m2, 'despesas': [particular]}, usuario=USUARIO_A).diag.message_primary


# =====================================================================================================================
# 4. Carga inicial (scripts/cadastros_padrao.py) e reversao
# =====================================================================================================================

def rodar(dsn, *args):
    r = subprocess.run([sys.executable, str(RAIZ / 'scripts' / 'cadastros_padrao.py'), *args, '--dsn', dsn], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    return r.returncode, r.stdout + r.stderr


def test_carga_inicial_preserva_o_que_o_titular_tem_e_e_reversivel(c, tmp_path):
    dsn, pa, pb = c['dsn'], c['pa'], c['pb']
    p_geral = palavra_padrao(dsn, MORADIA, 'aluguelgeral')
    p_pessoal = palavra_padrao(dsn, MORADIA, 'padaria da esquina')
    comprar(dsn, descricao='PADARIA DA ESQUINA', categoria_id=MORADIA)
    cartao_antes = do_perfil(dsn, pa)
    vinculos_antes = sql(dsn, 'select id, categoria_cartao_id, categoria_id, ativo from public.categoria_cartao_despesa where perfil_financeiro_id = %s order by id', (pa,))
    inicial = digest(dsn)
    efetivas_a = sorted((p['categoria_id'], p['palavra']) for p in sql(dsn, 'select * from financeiro.palavras_efetivas(%s)', (USUARIO_A['id'],)))
    pessoais = tmp_path / 'pessoais.json'
    pessoais.write_text(json.dumps([{'categoria_id': MORADIA, 'palavra': 'Padaria da  Esquina'}]), encoding='utf-8')
    previa, feito = tmp_path / 'previa.json', tmp_path / 'feito.json'
    comum = ['--perfil-referencia', str(pa), '--pessoais', str(pessoais), '--preencher-perfis']

    cod, saida = rodar(dsn, 'previa', *comum, '--saida', str(previa))
    assert cod == 0, saida
    p = json.loads(previa.read_text(encoding='utf-8'))
    assert p['categorias_de_cartao_no_modelo'] == len([x for x in cartao_antes if x['ativo']]) and p['palavras_pessoais'] == 1
    assert digest(dsn) == inicial
    for args in (['executar', *comum, '--hash', 'x' * 64, '--confirmo', 'CADASTROS PADRAO'], ['executar', *comum, '--hash', p['impressao'], '--confirmo', 'sim']):
        cod, saida = rodar(dsn, *args)
        assert cod != 0 and digest(dsn) == inicial, saida
    cod, saida = rodar(dsn, 'executar', *comum, '--hash', p['impressao'], '--confirmo', 'CADASTROS PADRAO', '--saida', str(feito))
    assert cod == 0, saida

    # o titular: mesmas categorias de cartao (mesmos ids, agora marcadas), mesmos vinculos, mesma regra efetiva de palavras
    depois = do_perfil(dsn, pa)
    assert [(x['id'], x['nome'], x['ativo'], x['cor']) for x in depois] == [(x['id'], x['nome'], x['ativo'], x['cor']) for x in cartao_antes]
    assert all(x['padrao_id'] for x in depois if x['ativo'])
    assert sql(dsn, 'select id, categoria_cartao_id, categoria_id, ativo from public.categoria_cartao_despesa where perfil_financeiro_id = %s order by id', (pa,)) == vinculos_antes
    assert sorted((p['categoria_id'], p['palavra']) for p in sql(dsn, 'select * from financeiro.palavras_efetivas(%s)', (USUARIO_A['id'],))) == efetivas_a
    assert sugestao(dsn, pa, 'padaria da esquina')['categoria_id'] == MORADIA
    # os demais usuarios: recebem a palavra geral, nao a pessoal; e os perfis deles ganham as categorias de cartao padrao
    assert sugestao(dsn, pb, 'aluguelgeral')['categoria_id'] == MORADIA and sugestao(dsn, pb, 'padaria da esquina')['origem'] == 'sem_sugestao'
    for perfil in c['perfis']['B'].values():
        assert len([x for x in do_perfil(dsn, perfil) if x['padrao_id']]) == p['categorias_de_cartao_no_modelo']
    meio = digest(dsn)
    assert (meio['categorias'], meio['compras'], meio['itens']) == (inicial['categorias'], inicial['compras'], inicial['itens'])  # nada classificado mudou
    cod, saida = rodar(dsn, 'executar', *comum, '--hash', p['impressao'], '--confirmo', 'CADASTROS PADRAO')
    assert cod != 0 and digest(dsn) == meio  # a carga inicial nao se repete

    cod, saida = rodar(dsn, 'reverter', '--feito', str(feito), '--confirmo', 'REVERTER CADASTROS')
    assert cod == 0, saida
    fim = digest(dsn)
    assert {k: v for k, v in fim.items() if k != 'palavras'} == {k: v for k, v in inicial.items() if k != 'palavras'}
    assert sql(dsn, 'select ativo from public.categoria_palavra_chave where id = any(%s)', ([p_geral, p_pessoal],)) == [{'ativo': True}, {'ativo': True}]
    assert sugestao(dsn, pb, 'padaria da esquina')['categoria_id'] == MORADIA
    cod, saida = rodar(dsn, 'reverter', '--feito', str(feito), '--confirmo', 'REVERTER CADASTROS')
    assert cod != 0 and 'ja revertida' in saida


def test_migration_versionada_e_a_saida_do_gerador_e_a_reversao_recusa_com_personalizacoes(c):
    r = subprocess.run([sys.executable, str(RAIZ / 'scripts' / 'gerar_migration_cadastros_padrao.py'), '--verificar'], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    assert r.returncode == 0, r.stdout + r.stderr
    dsn = c['dsn']
    rpc(dsn, 'criar_categoria', {'nome': 'Particular'}, chave(), usuario=USUARIO_B)
    assert 'categorias particulares' in erro(executar_arquivo, dsn, REVERSAO).diag.message_primary


def test_reversao_devolve_a_estrutura_e_as_funcoes_anteriores(banco):
    catalogo_novo(banco)
    antes = sql(banco, "select md5(string_agg(c::text, '|' order by c.id)) h from (select id, nome, ativo from public.categoria) c")[0]['h']
    executar_arquivo(banco, REVERSAO)
    assert sql(banco, """select (select count(*) from information_schema.columns where table_name = 'categoria' and column_name = 'user_id') coluna,
        (select count(*) from pg_tables where schemaname = 'financeiro' and tablename in ('palavra_chave_usuario', 'categoria_cartao_padrao')) tabelas,
        (select count(*) from pg_trigger where tgname like 'categoria_do_dono_%%') gatilhos,
        (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro'
           and p.proname in ('palavras_efetivas', 'categoria_visivel', 'criar_minha_palavra_chave', 'inicializar_categorias_cartao')) funcoes""") == [
        {'coluna': 0, 'tabelas': 0, 'gatilhos': 0, 'funcoes': 0}]
    assert sql(banco, "select md5(string_agg(c::text, '|' order by c.id)) h from (select id, nome, ativo from public.categoria) c")[0]['h'] == antes
    # as regras anteriores voltam: so quem administra o catalogo cria categoria, e ela e de todos
    assert erro(rpc, banco, 'criar_categoria', {'nome': 'De B'}, chave(), usuario=USUARIO_B).pgcode == '42501'
    assert rpc(banco, 'criar_categoria', {'nome': 'De todos'}, chave(), usuario=USUARIO_A)['nome'] == 'De todos'
    assert 'De todos' in {x['nome'] for x in tabela(banco, 'categorias_de_despesa', usuario=USUARIO_B)}
    # e a migration volta a ser aplicada sobre o estado revertido
    executar_arquivo(banco, RAIZ / 'supabase' / 'migrations' / '20270101090000_financeiro_cadastros_padrao.sql')
    assert rpc(banco, 'criar_categoria', {'nome': 'Particular de B'}, chave(), usuario=USUARIO_B)['padrao'] is False
