"""
Testes FIN-MULTIUSUARIO-ACESSO-01 (migration 20270102090000) — entrada por convite, ativacao, situacao das contas e
administracao da plataforma, em cluster PostgreSQL local descartavel e com dados ficticios. Nenhum e-mail e enviado: o
convite e um registro; a identidade e a do Supabase Auth (aqui, o esquema auth simulado).

Conferido: convite valido, expirado, revogado e reutilizado; e-mail que ja tem conta; ativacao incompleta e repetida; conta
suspensa e nunca ativada nao recebem resposta de NENHUMA funcao exposta; usuario comum nao administra; o administrador nao
le dado financeiro de ninguem; isolamento entre a conta nova e as existentes; reversao.
"""
import json
import uuid
from pathlib import Path

import pytest

from tests import isolamento_cenario as I
from tests.test_supabase_cartoes import banco, rpc, tabela  # noqa: F401
from tests.test_supabase_categorias_consolidacao import executar_arquivo
from tests.test_supabase_categorias_recorrencias import catalogo_novo, erro
from tests.test_supabase_isolamento_usuarios import cenario  # noqa: F401
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, USUARIO_B, cluster, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')
RAIZ = Path(__file__).resolve().parent.parent
MIGRATION = RAIZ / 'supabase' / 'migrations' / '20270102090000_financeiro_multiusuario_acesso.sql'
REVERSAO = RAIZ / 'supabase' / 'reversao' / '20270102090000_multiusuario_acesso_anterior.sql'
PESSOAL = ID['PESSOAL']
# Respondem a qualquer sessao, de proposito: a situacao da PROPRIA conta (para a tela de primeiro acesso), a ativacao (que
# recusa por conta propria), o escritor do catalogo (sem dado de usuario) e a lista fixa de imagens do aplicativo.
SEMPRE_RESPONDEM = {'situacao_da_minha_conta', 'situacao_catalogo_categorias', 'imagens_patrimonio'}
VAZIOS = {'[]', '[false]', '[null]', '[[]]', '[{}]', '[0]'}


def usuario_novo(dsn, nome, confirmado=True):
    u = {'id': str(uuid.uuid4()), 'email': f'{nome}.{uuid.uuid4().hex[:6]}@teste.local'}
    sql(dsn, 'insert into auth.users (id, email, email_confirmed_at) values (%s, %s, ' + ('now()' if confirmado else 'null') + ')', (u['id'], u['email']))
    return u


def convidar(dsn, email, **dados):
    return rpc(dsn, 'criar_convite', {'email': email, **dados}, usuario=USUARIO_A)


def situacao(dsn, usuario):
    return rpc(dsn, 'situacao_da_minha_conta', usuario=usuario)


def dica(e):
    return (e.pgcode, e.diag.message_hint)


def retrato_financeiro(dsn):
    """md5 de cada tabela dos esquemas de dados, menos as desta etapa: nada financeiro muda em nenhuma operacao de acesso."""
    tabelas = sql(dsn, """select n.nspname e, c.relname t from pg_class c join pg_namespace n on n.oid = c.relnamespace
                           where c.relkind = 'r' and n.nspname in ('public', 'financeiro')
                             and c.relname not in ('usuario_plataforma', 'convite', 'auditoria_acesso') order by 1, 2""")
    return {f"{x['e']}.{x['t']}": sql(dsn, f"select md5(coalesce(string_agg(x::text, '|' order by x::text), '')) h from {x['e']}.\"{x['t']}\" x")[0]['h']
            for x in tabelas}


# =====================================================================================================================
# 1. Estado inicial e convites
# =====================================================================================================================

def test_contas_existentes_ficam_ativas_e_nada_muda_para_elas(banco):  # noqa: F811
    contas = {x['user_id']: x for x in sql(banco, 'select user_id::text, situacao, origem from financeiro.usuario_plataforma')}
    assert contas[USUARIO_A['id']]['situacao'] == contas[USUARIO_B['id']]['situacao'] == 'ATIVA'
    assert situacao(banco, USUARIO_A) == {'situacao': 'ATIVA', 'administrador': True, 'perfis': situacao(banco, USUARIO_A)['perfis']}
    assert situacao(banco, USUARIO_B)['administrador'] is False and situacao(banco, USUARIO_B)['perfis'] >= 1
    assert tabela(banco, 'meus_perfis', usuario=USUARIO_A) and tabela(banco, 'meus_perfis', usuario=USUARIO_B)
    assert sql(banco, 'select count(*) n from financeiro.convite')[0]['n'] == 0


def test_convite_so_do_administrador_com_email_valido_validade_e_um_pendente_por_email(banco):  # noqa: F811
    for funcao, args in (('criar_convite', ({'email': 'x@teste.local'},)), ('convites_tela', ()), ('usuarios_tela', ()),
                         ('revogar_convite', (str(uuid.uuid4()),)), ('registrar_reenvio_convite', (str(uuid.uuid4()), 7)),
                         ('suspender_usuario', (USUARIO_A['id'], 'x')), ('reativar_usuario', (USUARIO_A['id'],)), ('auditoria_acesso_tela', (10,))):
        assert dica(erro(rpc, banco, funcao, *args, usuario=USUARIO_B)) == ('42501', 'SO_ADMINISTRADOR'), funcao
    assert sql(banco, 'select count(*) n from financeiro.convite')[0]['n'] == 0
    for ruim in ('', 'sem-arroba', 'a@b', 'a b@c.d'):
        assert erro(convidar, banco, ruim).pgcode == '22023'
    assert erro(convidar, banco, 'n@teste.local', validade_dias=0).pgcode == '22023'
    assert erro(convidar, banco, 'n@teste.local', validade_dias=31).pgcode == '22023'
    c = convidar(banco, '  Nova.Pessoa@Teste.Local ', validade_dias=3, observacao='familia')
    assert (c['email'], c['situacao'], c['envios'], c['conta_no_auth'], c['observacao']) == ('nova.pessoa@teste.local', 'PENDENTE', 1, False, 'familia')
    assert dica(erro(convidar, banco, 'NOVA.pessoa@teste.local')) == ('22023', 'CONVITE_PENDENTE')
    # e-mail que ja tem conta no aplicativo nao recebe convite
    assert dica(erro(convidar, banco, USUARIO_B['email'])) == ('22023', 'CONTA_EXISTENTE')
    assert [x['email'] for x in rpc(banco, 'convites_tela')] == ['nova.pessoa@teste.local']
    # nenhuma coluna guarda senha, token ou segredo
    colunas = {x['column_name'] for x in sql(banco, "select column_name from information_schema.columns where table_schema = 'financeiro' and table_name in ('convite', 'usuario_plataforma')")}
    assert not {c for c in colunas if any(p in c for p in ('senha', 'token', 'hash', 'segredo', 'password', 'secret'))}


def test_reenvio_controlado_revogacao_e_expiracao(banco):  # noqa: F811
    c = convidar(banco, 'reenvio@teste.local')
    assert dica(erro(rpc, banco, 'registrar_reenvio_convite', c['id'], 7)) == ('22023', 'ENVIO_RECENTE')
    for n in range(2, 6):
        sql(banco, "update financeiro.convite set ultimo_envio_em = now() - interval '11 minutes' where id = %s", (c['id'],))
        assert rpc(banco, 'registrar_reenvio_convite', c['id'], 10)['envios'] == n
    sql(banco, "update financeiro.convite set ultimo_envio_em = now() - interval '11 minutes' where id = %s", (c['id'],))
    assert dica(erro(rpc, banco, 'registrar_reenvio_convite', c['id'], 7)) == ('22023', 'LIMITE_DE_ENVIOS')
    assert rpc(banco, 'revogar_convite', c['id'])['situacao'] == 'REVOGADO'
    assert erro(rpc, banco, 'revogar_convite', c['id']).pgcode == '22023'
    assert erro(rpc, banco, 'registrar_reenvio_convite', c['id'], 7).pgcode == '22023'
    # expirado: aparece como EXPIRADO; um novo convite para o mesmo e-mail encerra o vencido
    v = convidar(banco, 'vencido@teste.local')
    sql(banco, "update financeiro.convite set expira_em = now() - interval '1 minute' where id = %s", (v['id'],))
    assert {x['email']: x['situacao'] for x in rpc(banco, 'convites_tela')}['vencido@teste.local'] == 'EXPIRADO'
    novo = convidar(banco, 'vencido@teste.local')
    assert novo['id'] != v['id'] and novo['situacao'] == 'PENDENTE'
    assert sql(banco, 'select situacao from financeiro.convite where id = %s', (v['id'],))[0]['situacao'] == 'REVOGADO'
    acoes = [x['acao'] for x in rpc(banco, 'auditoria_acesso_tela', 50)]
    assert acoes.count('CONVITE_REENVIADO') == 4 and 'CONVITE_REVOGADO' in acoes and acoes.count('CONVITE_CRIADO') == 3


# =====================================================================================================================
# 2. Ativacao
# =====================================================================================================================

def test_ativacao_com_convite_valido_e_unica_transacional_e_repetivel(banco):  # noqa: F811
    catalogo_novo(banco)
    antes = retrato_financeiro(banco)
    n = usuario_novo(banco, 'nova')
    # sem convite: nada responde e a ativacao e recusada sem dizer mais nada
    assert situacao(banco, n) == {'situacao': 'SEM_CONVITE', 'administrador': False, 'perfis': 0, 'convite_expira_em': None}
    assert dica(erro(rpc, banco, 'ativar_minha_conta', {'nome': 'Pessoal'}, usuario=n)) == ('42501', 'SEM_CONVITE')
    assert dica(erro(rpc, banco, 'criar_perfil', {'nome': 'Pessoal'}, usuario=n)) == ('42501', 'CONTA_INATIVA')
    assert tabela(banco, 'meus_perfis', usuario=n) == []
    assert retrato_financeiro(banco) == antes
    convidar(banco, n['email'].upper())
    assert situacao(banco, n)['situacao'] == 'CONVIDADA'
    # ativacao incompleta (sem o nome do perfil): nada e criado, o convite continua valendo
    assert erro(rpc, banco, 'ativar_minha_conta', {}, usuario=n).pgcode == '22023'
    assert erro(rpc, banco, 'ativar_minha_conta', {'nome': 'x' * 500}, usuario=n).pgcode is not None
    assert situacao(banco, n)['situacao'] == 'CONVIDADA' and retrato_financeiro(banco) == antes
    assert sql(banco, 'select count(*) n from financeiro.usuario_plataforma where user_id = %s', (n['id'],))[0]['n'] == 0
    r = rpc(banco, 'ativar_minha_conta', {'nome': 'Minhas Financas', 'tipo': 'PESSOAL'}, usuario=n)
    assert (r['ativada'], r['repetida'], r['perfis']) == (True, False, 1)
    perfil = r['perfil']['id']
    assert situacao(banco, n) == {'situacao': 'ATIVA', 'administrador': False, 'perfis': 1}
    meus = tabela(banco, 'meus_perfis', usuario=n)
    assert [(p['id'], p['nome'], p['padrao'], p['papel']) for p in meus] == [(perfil, 'Minhas Financas', True, 'TITULAR')]
    assert sql(banco, 'select user_id::text u from public.perfil_financeiro where id = %s', (perfil,))[0]['u'] == n['id']
    # o que a inicializacao cria: o perfil, o vinculo, o gerador e as categorias de cartao padrao. Nada financeiro.
    depois = retrato_financeiro(banco)
    mudaram = {t for t in depois if depois[t] != antes.get(t)}
    assert mudaram <= {'public.perfil_financeiro', 'financeiro.perfil_acesso', 'financeiro.gerador_recorrencia', 'financeiro.gerador_recorrencia_historico', 'public.categoria_cartao',
                       'public.categoria_cartao_despesa', 'financeiro.preferencia_usuario', 'financeiro.operacao_catalogo'}, mudaram
    for t in ('conta_bancaria', 'conta', 'item_despesa', 'lancamento_agregado', 'cartao'):
        linhas = sql(banco, f'select count(*) n from public.{t} where perfil_financeiro_id = %s', (perfil,)) if t != 'cartao' else [{'n': 0}]
        assert linhas[0]['n'] == 0, t
    # repetir (segundo toque, retomada): mesmo estado, nada novo
    marca = retrato_financeiro(banco)
    r2 = rpc(banco, 'ativar_minha_conta', {'nome': 'Outro nome'}, usuario=n)
    assert (r2['ativada'], r2['repetida'], r2['perfis']) == (True, True, 1) and retrato_financeiro(banco) == marca
    c = sql(banco, 'select situacao, usado_por::text u from financeiro.convite where email = %s', (n['email'],))[0]
    assert c == {'situacao': 'USADO', 'u': n['id']}
    # convite usado nao serve a mais ninguem nem de novo; e-mail com conta nao e convidado outra vez
    assert dica(erro(convidar, banco, n['email'])) == ('22023', 'CONTA_EXISTENTE')
    # a conta nova usa o aplicativo e ve o catalogo padrao; nao ve nada das outras contas
    rpc(banco, 'criar_categoria', {'nome': 'So minha'}, str(uuid.uuid4()), usuario=n)
    minhas = {x['nome']: x for x in rpc(banco, 'categorias_tela', perfil, None, usuario=n)}
    assert minhas['So minha']['padrao'] is False and any(x['padrao'] for x in minhas.values())
    assert 'So minha' not in {x['nome'] for x in tabela(banco, 'categorias_de_despesa', usuario=USUARIO_A)}
    assert erro(rpc, banco, 'categorias_tela', PESSOAL, None, usuario=n).pgcode == '42501'
    assert erro(rpc, banco, 'categorias_tela', perfil, None, usuario=USUARIO_A).pgcode == '42501'  # nem o administrador


def test_convite_expirado_revogado_de_outro_email_e_email_nao_confirmado_nao_ativam(banco):  # noqa: F811
    exp, rev, outro, nconf = (usuario_novo(banco, x) for x in ('exp', 'rev', 'outro', 'nconf'))
    nconf = usuario_novo(banco, 'nconf2', confirmado=False)
    c_exp = convidar(banco, exp['email'])
    sql(banco, "update financeiro.convite set expira_em = now() - interval '1 second' where id = %s", (c_exp['id'],))
    assert situacao(banco, exp)['situacao'] == 'CONVITE_EXPIRADO'
    assert dica(erro(rpc, banco, 'ativar_minha_conta', {'nome': 'P'}, usuario=exp)) == ('42501', 'CONVITE_EXPIRADO')
    c_rev = convidar(banco, rev['email'])
    rpc(banco, 'revogar_convite', c_rev['id'])
    assert situacao(banco, rev)['situacao'] == 'SEM_CONVITE'
    assert dica(erro(rpc, banco, 'ativar_minha_conta', {'nome': 'P'}, usuario=rev)) == ('42501', 'SEM_CONVITE')
    # o convite e do e-mail: outra sessao nao o aproveita, mesmo conhecendo o identificador
    assert dica(erro(rpc, banco, 'ativar_minha_conta', {'nome': 'P', 'convite_id': c_exp['id'], 'email': exp['email']}, usuario=outro)) == ('42501', 'SEM_CONVITE')
    convidar(banco, nconf['email'])
    assert situacao(banco, nconf)['situacao'] == 'EMAIL_NAO_CONFIRMADO'
    assert dica(erro(rpc, banco, 'ativar_minha_conta', {'nome': 'P'}, usuario=nconf)) == ('42501', 'EMAIL_NAO_CONFIRMADO')
    assert sql(banco, 'select count(*) n from financeiro.usuario_plataforma where user_id = any(%s::uuid[])',
               ([exp['id'], rev['id'], outro['id'], nconf['id']],))[0]['n'] == 0
    # reenvio renova a validade do expirado; ai a ativacao passa
    sql(banco, "update financeiro.convite set ultimo_envio_em = now() - interval '11 minutes' where id = %s", (c_exp['id'],))
    rpc(banco, 'registrar_reenvio_convite', c_exp['id'], 7)
    assert rpc(banco, 'ativar_minha_conta', {'nome': 'P'}, usuario=exp)['ativada'] is True


def test_usuario_nao_escolhe_atributo_de_autorizacao_na_ativacao(banco):  # noqa: F811
    n = usuario_novo(banco, 'esperto')
    convidar(banco, n['email'])
    rpc(banco, 'ativar_minha_conta', {'nome': 'P', 'administrador': True, 'situacao': 'ATIVA', 'origem': 'EXISTENTE', 'user_id': USUARIO_A['id'],
                                      'papel': 'ADMIN', 'pode_gerir': True, 'gestor': True}, usuario=n)
    assert situacao(banco, n) == {'situacao': 'ATIVA', 'administrador': False, 'perfis': 1}
    assert sql(banco, 'select count(*) n from financeiro.administrador_plataforma where user_id = %s', (n['id'],))[0]['n'] == 0
    assert sql(banco, 'select count(*) n from financeiro.gestor_catalogo where user_id = %s', (n['id'],))[0]['n'] == 0
    assert sql(banco, 'select origem from financeiro.usuario_plataforma where user_id = %s', (n['id'],))[0]['origem'] == 'CONVITE'
    assert dica(erro(rpc, banco, 'criar_convite', {'email': 'amigo@teste.local'}, usuario=n)) == ('42501', 'SO_ADMINISTRADOR')
    # nenhuma tabela desta etapa e legivel ou gravavel direto pelo usuario
    for t in ('usuario_plataforma', 'convite', 'auditoria_acesso', 'administrador_plataforma'):
        for comando in (f'select * from financeiro.{t}', f"update financeiro.{t} set user_id = user_id" if t != 'convite' and t != 'auditoria_acesso' else f'delete from financeiro.{t}'):
            conn = I.conectar(banco)
            try:
                conn.autocommit = False
                I.como(conn, n)
                with pytest.raises(psycopg2.Error) as e, conn.cursor() as cur:
                    cur.execute(comando)
                assert e.value.pgcode == '42501', (t, comando)
            finally:
                conn.rollback()
                conn.close()


# =====================================================================================================================
# 3. Suspensao e administracao
# =====================================================================================================================

def test_suspender_e_reativar_so_o_administrador_com_motivo_e_auditoria(banco):  # noqa: F811
    assert erro(rpc, banco, 'suspender_usuario', USUARIO_A['id'], 'eu mesmo').pgcode == '22023'
    assert erro(rpc, banco, 'suspender_usuario', USUARIO_B['id'], '  ').pgcode == '22023'
    assert erro(rpc, banco, 'suspender_usuario', str(uuid.uuid4()), 'inexistente').pgcode == '22023'
    antes = retrato_financeiro(banco)
    assert rpc(banco, 'suspender_usuario', USUARIO_B['id'], 'teste de suspensao') == {'user_id': USUARIO_B['id'], 'situacao': 'SUSPENSA'}
    assert erro(rpc, banco, 'suspender_usuario', USUARIO_B['id'], 'de novo').pgcode == '22023'
    assert situacao(banco, USUARIO_B) == {'situacao': 'SUSPENSA', 'administrador': False, 'perfis': 0}
    assert tabela(banco, 'meus_perfis', usuario=USUARIO_B) == []
    assert rpc(banco, 'pode_acessar_perfil', ID['PERFIL_B'], usuario=USUARIO_B) is False
    assert erro(rpc, banco, 'categorias_tela', ID['PERFIL_B'], None, usuario=USUARIO_B).pgcode == '42501'
    assert dica(erro(rpc, banco, 'criar_perfil', {'nome': 'Novo'}, usuario=USUARIO_B)) == ('42501', 'CONTA_INATIVA')
    assert dica(erro(rpc, banco, 'ativar_minha_conta', {'nome': 'Novo'}, usuario=USUARIO_B)) == ('42501', 'CONTA_INATIVA')
    # conta suspensa nao e reativada por convite nem por novo vinculo administrativo
    assert dica(erro(convidar, banco, USUARIO_B['email'])) == ('22023', 'CONTA_EXISTENTE')
    tela = {x['user_id']: x for x in rpc(banco, 'usuarios_tela')}
    assert (tela[USUARIO_B['id']]['situacao'], tela[USUARIO_B['id']]['motivo']) == ('SUSPENSA', 'teste de suspensao')
    assert tela[USUARIO_A['id']]['eu'] is True and tela[USUARIO_A['id']]['administrador'] is True
    assert retrato_financeiro(banco) == antes  # suspender nao apaga nem altera nada do usuario
    assert rpc(banco, 'reativar_usuario', USUARIO_B['id'])['situacao'] == 'ATIVA'
    assert erro(rpc, banco, 'reativar_usuario', USUARIO_B['id']).pgcode == '22023'
    assert tabela(banco, 'meus_perfis', usuario=USUARIO_B) and rpc(banco, 'pode_acessar_perfil', ID['PERFIL_B'], usuario=USUARIO_B) is True
    assert retrato_financeiro(banco) == antes
    acoes = [x['acao'] for x in rpc(banco, 'auditoria_acesso_tela', 50)]
    assert acoes[:2] == ['CONTA_REATIVADA', 'CONTA_SUSPENSA']


def test_administrador_suspenso_perde_a_administracao_e_o_operador_recupera(banco):  # noqa: F811
    assert sql(banco, "select financeiro.definir_conta_plataforma(%s, 'SUSPENSA', 'operador', 'teste') r", (USUARIO_A['id'],))
    assert dica(erro(rpc, banco, 'convites_tela')) == ('42501', 'SO_ADMINISTRADOR')
    assert rpc(banco, 'sou_administrador_plataforma') is False
    assert dica(erro(rpc, banco, 'importar_tr', {'itens': []}, str(uuid.uuid4()))) == ('42501', 'CONTA_INATIVA')
    sql(banco, "select financeiro.definir_conta_plataforma(%s, 'ATIVA', 'operador', 'teste')", (USUARIO_A['id'],))
    assert rpc(banco, 'convites_tela') == [] and rpc(banco, 'sou_administrador_plataforma') is True
    # a operacao administrativa nao e executavel pelo navegador
    assert erro(rpc, banco, 'definir_conta_plataforma', USUARIO_B['id'], 'SUSPENSA', 'eu', 'eu').pgcode == '42501'


def test_funcoes_de_administracao_nao_leem_tabela_financeira(banco):  # noqa: F811
    """O administrador da plataforma nao ganha acesso a dado financeiro: as funcoes desta etapa so tocam as tabelas de acesso."""
    permitidas = ('usuario_plataforma', 'convite', 'auditoria_acesso', 'administrador_plataforma', 'perfil_acesso', 'perfil_financeiro',
                  'preferencia_usuario', 'users')
    nomes = ('criar_convite', 'revogar_convite', 'registrar_reenvio_convite', 'convites_tela', 'situacao_da_minha_conta', 'usuarios_tela',
             'suspender_usuario', 'reativar_usuario', 'auditoria_acesso_tela', 'convite_em_json', 'exigir_administrador', 'auditar_acesso',
             'conta_ativa', 'exigir_conta_ativa', 'definir_conta_plataforma', 'conta_no_vinculo')
    for f in sql(banco, "select proname, prosrc from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro' and proname = any(%s)", (list(nomes),)):
        import re
        usadas = set(re.findall(r'(?:from|join|into|update)\s+(?:public|financeiro|auth)\.(\w+)', f['prosrc'], re.I))
        assert usadas <= set(permitidas), (f['proname'], usadas - set(permitidas))
    assert len(nomes) == sql(banco, "select count(*) n from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro' and proname = any(%s)", (list(nomes),))[0]['n']
    # e, na pratica: o administrador continua recusado no perfil de outro usuario (o Perfil B e do usuario B)
    assert rpc(banco, 'pode_acessar_perfil', ID['PERFIL_B']) is False
    assert erro(rpc, banco, 'categorias_tela', ID['PERFIL_B'], None).pgcode == '42501'
    # usuarios_tela so informa e-mail, situacao, datas e QUANTIDADE de perfis
    assert set(rpc(banco, 'usuarios_tela')[0]) == {'user_id', 'email', 'situacao', 'origem', 'ativada_em', 'suspensa_em', 'motivo', 'administrador', 'perfis', 'eu'}


# =====================================================================================================================
# 4. PERMANENTE: sem conta ativa, nenhuma funcao exposta responde
# =====================================================================================================================

def _sondar(conn, usuario, fs, valores_por_funcao, dono):
    falhas, relatorio = [], []
    for f in fs:
        for valores in valores_por_funcao(f):
            cod, msg, ret = I.chamar(conn, usuario, f, valores)
            relatorio.append((f['nome'], cod))
            if dono and I.vazou(ret, msg, dono):
                falhas.append((f['nome'], 'VAZOU', cod))
            elif f['nome'] in SEMPRE_RESPONDEM:
                continue
            elif cod == 'OK' and ret not in VAZIOS:
                falhas.append((f['nome'], 'RESPONDEU', ret[:80]))
            elif cod not in ('OK', '42501'):
                falhas.append((f['nome'], cod, msg[:80]))
    return falhas, relatorio


def test_conta_suspensa_nao_recebe_resposta_de_nenhuma_funcao_exposta(cenario):  # noqa: F811
    conn, dsn = cenario['conn'], cenario['dsn']
    fs = I.funcoes_expostas(conn)
    assert len(fs) >= 270
    perfis_b = list(cenario['perfis']['B'].values())
    antes = I.retrato(conn, perfis_b)
    sql(dsn, "select financeiro.definir_conta_plataforma(%s, 'SUSPENSA', 'teste', 'teste permanente')", (USUARIO_B['id'],))

    def valores(f):
        nomes = (f['nomes'] or [])[:f['n']]
        return [{'p_perfil_id': p} for p in perfis_b] if 'p_perfil_id' in nomes else [{}]

    falhas, relatorio = _sondar(conn, USUARIO_B, fs, valores, 'B')
    assert not falhas, f'{len(falhas)} resposta(s) a conta suspensa: {sorted(set(falhas))[:15]}'
    assert len(relatorio) >= len(fs)
    assert I.retrato(conn, perfis_b) == antes
    # reativada, tudo volta como estava (nada foi apagado)
    sql(dsn, "select financeiro.definir_conta_plataforma(%s, 'ATIVA', 'teste', 'teste permanente')", (USUARIO_B['id'],))
    assert {p['id'] for p in tabela(dsn, 'meus_perfis', usuario=USUARIO_B)} >= set(perfis_b)
    assert I.retrato(conn, perfis_b) == antes


def test_conta_nunca_ativada_nao_recebe_resposta_de_nenhuma_funcao_exposta(cenario):  # noqa: F811
    conn, dsn = cenario['conn'], cenario['dsn']
    fs = I.funcoes_expostas(conn)
    n = usuario_novo(dsn, 'semconta')
    convidada = usuario_novo(dsn, 'convidada')
    convidar(dsn, convidada['email'])  # convidada mas ainda nao ativada: tambem nada
    todos = [p for d in 'AB' for p in cenario['perfis'][d].values()]
    antes = I.retrato(conn, todos)

    def valores(f):
        nomes = (f['nomes'] or [])[:f['n']]
        return [{'p_perfil_id': p} for p in todos] if 'p_perfil_id' in nomes else [{}]

    for usuario in (n, convidada):
        falhas, _ = _sondar(conn, usuario, [f for f in fs if f['nome'] != 'ativar_minha_conta'], valores, None)
        assert not falhas, f'{len(falhas)} resposta(s) a conta nunca ativada: {sorted(set(falhas))[:15]}'
        for f in fs:  # nem dado de A nem de B em resposta alguma
            if 'p_perfil_id' not in (f['nomes'] or [])[:f['n']]:
                cod, msg, ret = I.chamar(conn, usuario, f, {})
                assert not I.vazou(ret, msg, 'A') and not I.vazou(ret, msg, 'B'), f['nome']
    assert I.retrato(conn, todos) == antes


# =====================================================================================================================
# 5. Reversao
# =====================================================================================================================

def test_reversao_devolve_as_funcoes_e_e_recusada_com_conta_suspensa_ou_convite_pendente(banco):  # noqa: F811
    def funcoes(dsn):
        return {x['a']: x['h'] for x in sql(dsn, """select p.oid::regprocedure::text a, md5(p.prosrc || coalesce(p.proacl::text, '')) h
                                                      from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro'""")}
    com = funcoes(banco)
    c = convidar(banco, 'pendente@teste.local')
    assert 'convite pendente' in str(erro(executar_arquivo, banco, REVERSAO))
    rpc(banco, 'revogar_convite', c['id'])
    rpc(banco, 'suspender_usuario', USUARIO_B['id'], 'teste')
    assert 'conta suspensa' in str(erro(executar_arquivo, banco, REVERSAO))
    rpc(banco, 'reativar_usuario', USUARIO_B['id'])
    executar_arquivo(banco, REVERSAO)
    assert not sql(banco, "select 1 from pg_tables where schemaname = 'financeiro' and tablename in ('usuario_plataforma', 'convite', 'auditoria_acesso')")
    assert not sql(banco, "select 1 from pg_proc where proname in ('conta_ativa', 'ativar_minha_conta', 'criar_convite', 'exigir_conta_ativa')")
    assert not sql(banco, "select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro' and p.prosrc like '%%conta_ativa%%'")
    assert tabela(banco, 'meus_perfis', usuario=USUARIO_B) and rpc(banco, 'pode_acessar_perfil', ID['PERFIL_B'], usuario=USUARIO_B) is True
    executar_arquivo(banco, MIGRATION)  # reaplicavel depois da reversao
    assert funcoes(banco) == com
    assert json.dumps(situacao(banco, USUARIO_B), sort_keys=True) == json.dumps({'situacao': 'ATIVA', 'administrador': False, 'perfis': situacao(banco, USUARIO_B)['perfis']}, sort_keys=True)
