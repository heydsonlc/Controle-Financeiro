"""
Testes FIN-MULTIUSUARIO-HOMOLOGACAO-01 — homologacao INTEGRADA das tres etapas (propriedade e isolamento, catalogo padrao e
personalizacao, entrada por convite), em cluster PostgreSQL local descartavel e com dados ficticios.

Tres contas: o ADMINISTRADOR (o titular ficticio, com os dados do cenario base) e dois usuarios, X e Y, que ENTRAM PELO
FLUXO REAL (convite -> ativacao), cada um com dois perfis de MESMO NOME ("Pessoal" e "Empresa") e os mesmos nomes de conta,
cartao e categoria, com valores diferentes. Conferido: cada um usa o aplicativo de ponta a ponta e so ve o que e seu; toda
funcao com perfil recusa o perfil alheio nos seis sentidos (inclusive o administrador nos perfis dos usuarios); as funcoes de
administracao recusam o usuario comum; nada do administrador muda com a entrada e o uso de X e Y; suspensao de um nao afeta
os outros; e o backup do banco multiusuario restaura identico num banco novo, com as contas, convites e personalizacoes.
"""
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests import isolamento_cenario as I
from tests.supabase_local import ClusterLocal
from tests.test_supabase_cartoes import banco, rpc, tabela  # noqa: F401
from tests.test_supabase_categorias_recorrencias import catalogo_novo, erro
from tests.test_supabase_integracao_1123_1126 import resumo_tabelas
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, cluster, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import backup_banco as B  # noqa: E402

ADMIN = USUARIO_A
PESSOAL_DO_ADMIN = ID['PESSOAL']
MARCA = {'X': 'SEGREDO-DO-USUARIO-X-41c7', 'Y': 'SEGREDO-DO-USUARIO-Y-8e02'}
SALDO = {'X': {'Pessoal': '1111.11', 'Empresa': '3333.33'}, 'Y': {'Pessoal': '2222.22', 'Empresa': '4444.44'}}
VALOR = {'X': '137.41', 'Y': '259.83'}
chave = lambda: str(uuid.uuid4())  # noqa: E731


def entrar_por_convite(dsn, letra):
    """O fluxo real: o administrador registra o convite; a pessoa (login criado pelo convite do Auth) ativa a conta."""
    u = {'id': str(uuid.uuid4()), 'email': f'usuario.{letra.lower()}.{uuid.uuid4().hex[:6]}@teste.local'}
    sql(dsn, 'insert into auth.users (id, email, email_confirmed_at) values (%s, %s, now())', (u['id'], u['email']))
    rpc(dsn, 'criar_convite', {'email': u['email']}, usuario=ADMIN)
    r = rpc(dsn, 'ativar_minha_conta', {'nome': 'Pessoal', 'tipo': 'PESSOAL'}, usuario=u)
    return u, r['perfil']['id']


def usar(dsn, letra, u, perfil, nome_perfil):
    """Uso de ponta a ponta num perfil: conta bancaria, despesa cadastrada e paga, cartao e compra, categoria e palavra proprias."""
    conta = rpc(dsn, 'criar_conta_bancaria', perfil, {'nome': 'Conta Principal', 'instituicao': f'Banco {MARCA[letra]}', 'tipo': 'Conta Corrente',
                                                     'saldo_inicial': SALDO[letra][nome_perfil]}, chave(), usuario=u)
    conta_id = conta['id'] if 'id' in conta else conta['conta_bancaria']['id']
    categoria = next(c['id'] for c in tabela(dsn, 'categorias_de_despesa', usuario=u))
    rpc(dsn, 'criar_despesa_paga', perfil, {'nome': f'Despesa {MARCA[letra]}', 'valor': VALOR[letra], 'categoria_id': categoria,
                                            'data_vencimento': '2027-03-10'},
        {'conta_bancaria_id': conta_id, 'data_pagamento': '2027-03-10'}, chave(), usuario=u)
    cartao = rpc(dsn, 'criar_cartao', perfil, {'nome': 'Cartao Principal', 'dia_fechamento': 3, 'dia_vencimento': 10}, chave(), usuario=u)
    cartao_id = cartao.get('item_id') or cartao.get('cartao_id') or cartao.get('id')
    rpc(dsn, 'criar_compra', perfil, {'cartao_id': cartao_id, 'descricao': f'Compra {MARCA[letra]}', 'valor': VALOR[letra], 'total_parcelas': 2,
                                      'data_compra': '2027-03-05', 'mes_fatura': '2027-03-01', 'categoria_id': categoria}, chave(), usuario=u)
    return {'conta': conta_id, 'cartao': cartao_id, 'categoria_padrao': categoria}


@pytest.fixture
def plataforma(banco):  # noqa: F811
    catalogo_novo(banco)
    conn = I.conectar(banco)
    perfis_admin = [p['id'] for p in tabela(banco, 'meus_perfis', usuario=ADMIN)]
    antes_admin = {'retrato': I.retrato(conn, perfis_admin), 'leituras': leituras(banco, ADMIN, perfis_admin)}
    p = {'conn': conn, 'dsn': banco, 'usuarios': {}, 'perfis': {'ADMIN': {'Pessoal': PESSOAL_DO_ADMIN}}, 'ids': {}, 'antes_admin': antes_admin,
         'perfis_admin': perfis_admin}
    for letra in 'XY':
        u, pessoal = entrar_por_convite(banco, letra)
        empresa = rpc(banco, 'criar_perfil', {'nome': 'Empresa', 'tipo': 'EMPRESA'}, usuario=u)['id']
        p['usuarios'][letra] = u
        p['perfis'][letra] = {'Pessoal': pessoal, 'Empresa': empresa}
        p['ids'][letra] = {n: usar(banco, letra, u, pid, n) for n, pid in p['perfis'][letra].items()}
        pets = rpc(banco, 'criar_categoria', {'nome': 'Pets', 'natureza': 'CONSUMO'}, chave(), usuario=u)['categoria_id']
        rpc(banco, 'criar_minha_palavra_chave', pets, f'petshop {letra.lower()}', usuario=u)
        p['ids'][letra]['pets'] = pets
    yield p
    conn.close()


def leituras(dsn, usuario, perfis):
    """O que as telas mostram: as principais leituras de cada perfil, em dois meses."""
    saida = {}
    for perfil in perfis:
        for nome, args in (('contas_bancarias_tela', (perfil, None)), ('categorias_tela', (perfil, None)), ('categorias_cartao_tela', (perfil, None)),
                           ('palavras_chave_tela', (perfil,)), ('dashboard_resumo_tela', (perfil, '2027-03')), ('dashboard_resumo_tela', (perfil, '2029-05'))):
            try:
                saida[f'{nome}{args}'] = json.dumps(rpc(dsn, nome, *args, usuario=usuario), sort_keys=True, default=str)
            except psycopg2.Error as e:
                saida[f'{nome}{args}'] = f'ERRO {e.pgcode}'
    return saida


# =====================================================================================================================
# 1. Fluxos funcionais: cada um usa o aplicativo e so ve o que e seu
# =====================================================================================================================

def test_cada_usuario_usa_o_aplicativo_de_ponta_a_ponta_e_so_ve_o_que_e_seu(plataforma):
    p, dsn = plataforma, plataforma['dsn']
    for letra, outra in (('X', 'Y'), ('Y', 'X')):
        u = p['usuarios'][letra]
        meus = tabela(dsn, 'meus_perfis', usuario=u)
        assert sorted((x['nome'], x['papel']) for x in meus) == [('Empresa', 'TITULAR'), ('Pessoal', 'TITULAR')]
        assert {x['id'] for x in meus} == set(p['perfis'][letra].values()) and [x['nome'] for x in meus if x['padrao']] == ['Pessoal']
        for nome_perfil, perfil in p['perfis'][letra].items():
            contas = rpc(dsn, 'contas_bancarias_tela', perfil, None, usuario=u)
            assert [c['nome'] for c in contas] == ['Conta Principal']
            # saldo = saldo inicial - a despesa paga (a mesma operacao oficial de pagamento)
            assert Decimal(str(contas[0]['saldo_atual'])) == Decimal(SALDO[letra][nome_perfil]) - Decimal(VALOR[letra])
            texto = json.dumps([contas, rpc(dsn, 'categorias_tela', perfil, None, usuario=u), rpc(dsn, 'palavras_chave_tela', perfil, usuario=u),
                                rpc(dsn, 'dashboard_resumo_tela', perfil, '2027-03', usuario=u), tabela(dsn, 'cartoes_do_perfil', perfil, usuario=u)],
                               default=str, ensure_ascii=False)
            assert MARCA[letra] in texto and MARCA[outra] not in texto and f'petshop {outra.lower()}' not in texto
            cats = {c['nome']: c for c in rpc(dsn, 'categorias_tela', perfil, None, usuario=u)}
            assert cats['Pets']['padrao'] is False and cats['Pets']['id'] == p['ids'][letra]['pets']  # a particular vale nos dois perfis
            assert sum(1 for c in cats.values() if c['padrao']) >= 5  # e o catalogo padrao, igual para todos
    # mesmos nomes, registros distintos
    assert p['ids']['X']['pets'] != p['ids']['Y']['pets']
    padrao = lambda u: sorted(c['id'] for c in rpc(dsn, 'categorias_tela', p['perfis'][u]['Pessoal'], None, usuario=p['usuarios'][u]) if c['padrao'])  # noqa: E731
    assert padrao('X') == padrao('Y')


# =====================================================================================================================
# 2. Isolamento nos seis sentidos, inclusive o administrador nos perfis dos usuarios
# =====================================================================================================================

def test_toda_funcao_com_perfil_recusa_o_perfil_alheio_nos_seis_sentidos(plataforma):
    p, conn = plataforma, plataforma['conn']
    contas = {'ADMIN': ADMIN, 'X': p['usuarios']['X'], 'Y': p['usuarios']['Y']}
    com_perfil = [f for f in I.funcoes_expostas(conn) if 'p_perfil_id' in (f['nomes'] or [])[:f['n']]]
    assert len(com_perfil) >= 230
    marcas = list(MARCA.values()) + list(I.MARCA.values())
    antes = {d: I.retrato(conn, list(p['perfis'][d].values())) for d in contas}
    erradas, chamadas = [], 0
    for atacante, usuario in contas.items():
        for vitima in contas:
            if vitima == atacante:
                continue
            for perfil in p['perfis'][vitima].values():
                for f in com_perfil:
                    cod, msg, ret = I.chamar(conn, usuario, f, {'p_perfil_id': perfil})
                    chamadas += 1
                    assert not any(m in ret + msg for m in marcas), f"{f['nome']}: {atacante} recebeu dado de {vitima}"
                    if f['nome'] in ('pode_acessar_perfil', 'pode_gerir_perfil'):
                        assert (cod, ret) == ('OK', '[false]'), f['nome']
                    elif cod != '42501':
                        erradas.append((f['nome'], atacante, vitima, cod))
    assert not erradas, f'{len(erradas)} chamada(s) sem recusa: {sorted(set(erradas))[:10]}'
    assert chamadas >= 6 * 230
    assert {d: I.retrato(conn, list(p['perfis'][d].values())) for d in contas} == antes  # nada gravado em ninguem


def test_registro_alheio_pelo_identificador_nao_e_lido_nem_alterado(plataforma):
    p, dsn = plataforma, plataforma['dsn']
    x, y = p['usuarios']['X'], p['usuarios']['Y']
    px, py = p['perfis']['X']['Pessoal'], p['perfis']['Y']['Pessoal']
    alvo = p['ids']['Y']['Pessoal']
    antes = I.retrato(p['conn'], list(p['perfis']['Y'].values()))
    # X, no PROPRIO perfil, apontando para registros de Y pelo identificador
    tentativas = [
        ('criar_despesa_paga', (px, {'nome': 'x', 'valor': '1.00', 'categoria_id': p['ids']['Y']['pets'], 'data_vencimento': '2027-03-10'},
                                {'conta_bancaria_id': p['ids']['X']['Pessoal']['conta'], 'data_pagamento': '2027-03-10'}, chave())),
        ('criar_despesa_paga', (px, {'nome': 'x', 'valor': '1.00', 'categoria_id': alvo['categoria_padrao'], 'data_vencimento': '2027-03-10'},
                                {'conta_bancaria_id': alvo['conta'], 'data_pagamento': '2027-03-10'}, chave())),
        ('criar_compra', (px, {'cartao_id': alvo['cartao'], 'descricao': 'x', 'valor': '1.00', 'total_parcelas': 1, 'data_compra': '2027-03-05',
                               'mes_fatura': '2027-03-01', 'categoria_id': alvo['categoria_padrao']}, chave())),
        ('editar_categoria', (p['ids']['Y']['pets'], {'nome': 'Tomada'})),
        ('excluir_categoria', (p['ids']['Y']['pets'],)),
        ('definir_natureza_categoria', (p['ids']['Y']['pets'], 'APORTE', chave())),
        ('criar_minha_palavra_chave', (p['ids']['Y']['pets'], 'intrusa')),
    ]
    for funcao, args in tentativas:
        e = erro(rpc, dsn, funcao, *args, usuario=x)
        assert MARCA['Y'] not in str(e), funcao
    assert I.retrato(p['conn'], list(p['perfis']['Y'].values())) == antes
    assert {c['nome'] for c in rpc(dsn, 'categorias_tela', py, None, usuario=y) if not c['padrao']} == {'Pets'}
    assert 'intrusa' not in json.dumps(rpc(dsn, 'palavras_chave_tela', py, usuario=y))


# =====================================================================================================================
# 3. Administracao: so o administrador; e ele nao le dado financeiro de ninguem
# =====================================================================================================================

def test_funcoes_de_administracao_recusam_o_usuario_comum_e_o_administrador_nao_ve_dado_financeiro(plataforma):
    p, dsn = plataforma, plataforma['dsn']
    x = p['usuarios']['X']
    alguma = next(c['id'] for c in tabela(dsn, 'categorias_de_despesa', usuario=x))
    restritas = [('criar_convite', ({'email': 'amigo@teste.local'},)), ('convites_tela', ()), ('usuarios_tela', ()), ('auditoria_acesso_tela', (10,)),
                 ('suspender_usuario', (p['usuarios']['Y']['id'], 'x')), ('reativar_usuario', (p['usuarios']['Y']['id'],)),
                 ('revogar_convite', (chave(),)), ('registrar_reenvio_convite', (chave(), 7)),
                 ('criar_categoria', ({'nome': 'Padrao indevida', 'padrao': True}, chave())), ('editar_categoria', (alguma, {'nome': 'Tomada'})),
                 ('excluir_categoria', (alguma,)), ('definir_natureza_categoria', (alguma, 'APORTE', chave())),
                 ('criar_palavra_chave', (alguma, 'indevida')), ('manter_categoria_cartao_padrao', ({'nome': 'Indevida'},)),
                 ('propagar_categorias_cartao_padrao', ()), ('categorias_cartao_padrao_tela', ()),
                 ('criar_tr', ({'competencia': '2027-03', 'valor_percentual': '0.10'}, chave())), ('importar_tr', ({'itens': []}, chave()))]
    antes = resumo_tabelas(dsn)
    for funcao, args in restritas:
        assert erro(rpc, dsn, funcao, *args, usuario=x).pgcode == '42501', funcao
    assert resumo_tabelas(dsn) == antes
    assert rpc(dsn, 'sou_administrador_plataforma', usuario=x) is False and rpc(dsn, 'sou_administrador_plataforma', usuario=ADMIN) is True
    # o administrador administra...
    tela = rpc(dsn, 'usuarios_tela', usuario=ADMIN)
    assert {u['email'] for u in tela} >= {p['usuarios']['X']['email'], p['usuarios']['Y']['email']}
    texto = json.dumps([tela, rpc(dsn, 'convites_tela', usuario=ADMIN), rpc(dsn, 'auditoria_acesso_tela', 200, usuario=ADMIN)], default=str)
    # ... e o que ele ve dos usuarios e so e-mail, situacao, datas e quantidade de perfis
    assert not any(m in texto for m in MARCA.values()) and not any(v in texto for d in SALDO.values() for v in d.values())
    assert {u['perfis'] for u in tela if u['email'] in (p['usuarios']['X']['email'], p['usuarios']['Y']['email'])} == {2}
    # as categorias particulares e as palavras dos usuarios nao aparecem nem para o administrador
    assert 'Pets' not in {c['nome'] for c in tabela(dsn, 'categorias_de_despesa', usuario=ADMIN)}
    assert 'petshop' not in json.dumps(rpc(dsn, 'palavras_chave_tela', PESSOAL_DO_ADMIN, usuario=ADMIN))


# =====================================================================================================================
# 4. Preservacao: nada do administrador (o titular) muda com a entrada e o uso dos outros
# =====================================================================================================================

def test_nada_do_titular_muda_com_a_entrada_e_o_uso_dos_outros_usuarios(plataforma):
    p = plataforma
    assert I.retrato(p['conn'], p['perfis_admin']) == p['antes_admin']['retrato']  # tabelas e saldos dos perfis dele
    assert leituras(p['dsn'], ADMIN, p['perfis_admin']) == p['antes_admin']['leituras']  # o que as telas dele mostram
    assert {x['id'] for x in tabela(p['dsn'], 'meus_perfis', usuario=ADMIN)} == set(p['perfis_admin'])


def test_administrador_muda_o_catalogo_padrao_e_respeita_as_personalizacoes(plataforma):
    p, dsn = plataforma, plataforma['dsn']
    x, y = p['usuarios']['X'], p['usuarios']['Y']
    px, py = p['perfis']['X']['Pessoal'], p['perfis']['Y']['Pessoal']
    cat = next(c['id'] for c in tabela(dsn, 'categorias_de_despesa', usuario=x))
    registros = I.retrato(p['conn'], list(p['perfis']['X'].values()) + list(p['perfis']['Y'].values()))  # despesas, compras, saldos
    nova = rpc(dsn, 'criar_palavra_chave', cat, 'mercadinho padrao', usuario=ADMIN)['id']
    tem = lambda u, perfil, palavra: any(w['palavra'] == palavra and w.get('ativo', True) and w.get('origem') != 'DESLIGADA'  # noqa: E731
                                         for w in rpc(dsn, 'palavras_chave_tela', perfil, usuario=u).get(str(cat), []))
    assert tem(x, px, 'mercadinho padrao') and tem(y, py, 'mercadinho padrao')  # regra padrao nova chega a todos
    rpc(dsn, 'desligar_palavra_chave_padrao', nova, usuario=x)
    assert not tem(x, px, 'mercadinho padrao') and tem(y, py, 'mercadinho padrao')  # o ajuste de X e so dele
    nova_cat = rpc(dsn, 'criar_categoria', {'nome': 'Categoria padrao nova', 'padrao': True}, chave(), usuario=ADMIN)['categoria_id']
    for u, perfil in ((x, px), (y, py)):
        assert {c['id']: c['padrao'] for c in rpc(dsn, 'categorias_tela', perfil, None, usuario=u)}.get(nova_cat) is True
    # nenhuma despesa ja classificada muda
    assert I.retrato(p['conn'], list(p['perfis']['X'].values()) + list(p['perfis']['Y'].values())) == registros


# =====================================================================================================================
# 5. Suspensao de um usuario nao afeta os outros
# =====================================================================================================================

def test_suspensao_de_um_usuario_nao_afeta_os_outros_e_nao_apaga_nada(plataforma):
    p, dsn, conn = plataforma, plataforma['dsn'], plataforma['conn']
    x, y = p['usuarios']['X'], p['usuarios']['Y']
    px, py = p['perfis']['X']['Pessoal'], p['perfis']['Y']['Pessoal']
    de_x, de_y = I.retrato(conn, list(p['perfis']['X'].values())), leituras(dsn, y, list(p['perfis']['Y'].values()))
    rpc(dsn, 'suspender_usuario', x['id'], 'homologacao', usuario=ADMIN)
    assert tabela(dsn, 'meus_perfis', usuario=x) == [] and erro(rpc, dsn, 'contas_bancarias_tela', px, None, usuario=x).pgcode == '42501'
    assert leituras(dsn, y, list(p['perfis']['Y'].values())) == de_y
    assert leituras(dsn, ADMIN, p['perfis_admin']) == p['antes_admin']['leituras']
    assert I.retrato(conn, list(p['perfis']['X'].values())) == de_x
    assert erro(rpc, dsn, 'contas_bancarias_tela', px, None, usuario=ADMIN).pgcode == '42501'  # nem suspensa o administrador a alcanca
    rpc(dsn, 'reativar_usuario', x['id'], usuario=ADMIN)
    assert [c['nome'] for c in rpc(dsn, 'contas_bancarias_tela', px, None, usuario=x)] == ['Conta Principal']
    assert rpc(dsn, 'contas_bancarias_tela', py, None, usuario=y)


# =====================================================================================================================
# 6. Backup e restauracao do banco multiusuario (sempre em banco local descartavel)
# =====================================================================================================================

def test_backup_do_banco_multiusuario_restaura_identico_num_banco_novo(plataforma, tmp_path, monkeypatch):
    p, dsn = plataforma, plataforma['dsn']
    x, y = p['usuarios']['X'], p['usuarios']['Y']
    rpc(dsn, 'suspender_usuario', y['id'], 'fica suspensa no backup', usuario=ADMIN)
    rpc(dsn, 'criar_convite', {'email': 'pendente.no.backup@teste.local'}, usuario=ADMIN)
    de_x = leituras(dsn, x, list(p['perfis']['X'].values()))
    de_admin = leituras(dsn, ADMIN, p['perfis_admin'])
    monkeypatch.setenv('CF_BACKUP_ORIGEM', dsn)
    manifesto = B.main(['exportar', '--dsn-env', 'CF_BACKUP_ORIGEM', '--saida', str(tmp_path / 'bk')])
    linhas = json.loads(Path(manifesto).read_text(encoding='utf-8'))['linhas']
    # as tabelas do multiusuario estao no backup
    for t, minimo in (('financeiro.usuario_plataforma', 3), ('financeiro.convite', 3), ('financeiro.auditoria_acesso', 5), ('financeiro.palavra_chave_usuario', 2),
                      ('financeiro.administrador_plataforma', 1), ('financeiro.perfil_acesso', 5)):
        assert linhas.get(t, 0) >= minimo, (t, linhas.get(t))
    B.main(['verificar', '--manifesto', str(manifesto)])
    with ClusterLocal(PG_BIN, tmp_path / 'destino') as destino:
        destino.aplicar_shim()
        monkeypatch.setenv('CF_BACKUP_DESTINO', destino.dsn())
        B.main(['restaurar', '--manifesto', str(manifesto), '--dsn-env', 'CF_BACKUP_DESTINO'])
        d = destino.dsn()
        assert resumo_tabelas(d) == resumo_tabelas(dsn)
        # no banco restaurado: mesmos donos, mesmas telas, mesmo isolamento, mesma situacao das contas e dos convites
        assert leituras(d, x, list(p['perfis']['X'].values())) == de_x
        assert leituras(d, ADMIN, p['perfis_admin']) == de_admin
        assert erro(rpc, d, 'contas_bancarias_tela', p['perfis']['X']['Pessoal'], None, usuario=ADMIN).pgcode == '42501'
        assert tabela(d, 'meus_perfis', usuario=y) == []  # a suspensa continua suspensa
        assert rpc(d, 'situacao_da_minha_conta', usuario=y)['situacao'] == 'SUSPENSA'
        convites = {c['email']: c['situacao'] for c in rpc(d, 'convites_tela', usuario=ADMIN)}
        assert convites['pendente.no.backup@teste.local'] == 'PENDENTE' and convites[x['email']] == 'USADO'
        assert sql(d, 'select user_id::text u from public.perfil_financeiro where id = %s', (p['perfis']['X']['Empresa'],))[0]['u'] == x['id']
