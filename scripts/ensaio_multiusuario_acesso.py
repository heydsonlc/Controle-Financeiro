"""FIN-MULTIUSUARIO-ACESSO-01 — ensaio completo numa copia fiel da producao, em PostgreSQL DESCARTAVEL local.

    python scripts/ensaio_multiusuario_acesso.py --saida <pasta privada> --pessoais <arquivo.json> [--backup-id ID]

Parte do estado final do ensaio da etapa anterior (scripts/ensaio_cadastros_padrao.py: migrations e cargas das duas etapas
anteriores aplicadas na copia restaurada, com um segundo usuario ficticio) e ensaia, medindo:
  1. a migration 20270102090000: nenhuma tabela de dados muda; a conta do titular fica ATIVA e administradora; TODAS as
     leituras de tela do titular identicas; logins do Supabase Auth sem perfil ficam sem acesso (como ja estavam);
  2. convite e ativacao de um terceiro usuario FICTICIO (nenhum e-mail enviado): o que a inicializacao cria; nada do titular
     muda nem aparece para ele; o administrador nao alcanca o perfil dele;
  3. suspensao e reativacao: nada responde a conta suspensa; nada e apagado;
  4. a reversao: banco identico ao de antes da migration; reaplicacao sem erro.
O relatorio vai SO para a pasta privada indicada. Nada e impresso alem do resumo.
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'scripts'))

import psycopg2  # noqa: E402

import ensaio_cadastros_padrao as E2  # noqa: E402
import ensaio_multiusuario_seguranca as E1  # noqa: E402

MIGRATION = RAIZ / 'supabase' / 'migrations' / '20270102090000_financeiro_multiusuario_acesso.sql'
REVERSAO = RAIZ / 'supabase' / 'reversao' / '20270102090000_multiusuario_acesso_anterior.sql'
NOVAS_ESTRUTURAS = {'financeiro.usuario_plataforma', 'financeiro.convite', 'financeiro.auditoria_acesso'}
NOVAS_FUNCOES = {'situacao_da_minha_conta', 'convites_tela', 'usuarios_tela', 'auditoria_acesso_tela'}
consulta, diferencas, como = E1.consulta, E1.diferencas, E1.como


def chamar(conn, cur, usuario, sql, params=()):
    """Como o usuario, numa transacao propria. Devolve ('OK', valor) ou (codigo, dica)."""
    conn.rollback()
    como(cur, usuario)
    try:
        cur.execute(sql, params)
        valor = cur.fetchone()
        conn.commit()
        return 'OK', (list(valor.values())[0] if valor else None)
    except psycopg2.Error as e:
        conn.rollback()
        return e.pgcode, e.diag.message_hint


def etapa_acesso(x):
    conferir, rel, titular, perfis, outro = x['conferir'], x['rel'], x['titular'], x['perfis'], x['outro']
    conn, cur = x['abrir']()
    E1.NOVAS_ESTRUTURAS.update(NOVAS_ESTRUTURAS)
    E1.NOVAS_FUNCOES.update(NOVAS_FUNCOES)

    def retrato():
        r = E2.retrato(cur)
        conn.rollback()
        return r

    def funcoes():
        r = {f['a']: (f['s'], f['acl']) for f in consulta(cur, """select p.oid::regprocedure::text a, p.prosrc s, coalesce(p.proacl::text, '') acl
                                                                     from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro'""")}
        conn.rollback()
        return r

    base = {'retrato': retrato(), 'leituras': E2.leituras(conn, titular, perfis), 'funcoes': funcoes(),
            'leituras_outro': E2.leituras(conn, outro, [x['perfil_do_outro']])}
    sem_perfil = consulta(cur, """select count(*) n from auth.users u where not exists (select 1 from financeiro.perfil_acesso a where a.user_id = u.id)
                                    and not exists (select 1 from financeiro.administrador_plataforma a where a.user_id = u.id)""")[0]['n']
    conn.rollback()

    # ------------------------------------------------------------ 1. migration
    cur.execute(MIGRATION.read_text(encoding='utf-8'))
    conn.commit()
    conferir('acesso/migration: nenhuma tabela de dados muda', diferencas(base['retrato'], retrato()) == [], diferencas(base['retrato'], retrato()))
    contas = consulta(cur, 'select user_id::text u, situacao, origem from financeiro.usuario_plataforma')
    conferir('acesso/migration: as contas que ja usam o aplicativo ficam ATIVAS (titular e o segundo usuario ficticio)',
             {c['u']: (c['situacao'], c['origem']) for c in contas} == {titular: ('ATIVA', 'EXISTENTE'), outro: ('ATIVA', 'EXISTENTE')}, len(contas))
    conferir('acesso/migration: logins do Supabase Auth sem perfil continuam sem acesso (nenhuma conta criada para eles)',
             consulta(cur, 'select count(*) n from auth.users')[0]['n'] - len(contas) == sem_perfil, sem_perfil)
    conn.rollback()
    rel['acesso'] = {'logins_sem_conta_no_aplicativo': sem_perfil, 'leituras_do_titular': len(base['leituras'])}
    l1 = E2.leituras(conn, titular, perfis)
    conferir('acesso/migration: TODAS as leituras de tela do titular identicas', diferencas(base['leituras'], l1) == [], diferencas(base['leituras'], l1)[:8])
    conferir('acesso/migration: leituras do segundo usuario identicas', diferencas(base['leituras_outro'], E2.leituras(conn, outro, [x['perfil_do_outro']])) == [])
    s = chamar(conn, cur, titular, 'select financeiro.situacao_da_minha_conta() j')
    conferir('acesso/migration: o titular e conta ativa e administrador da plataforma', s[0] == 'OK' and s[1]['situacao'] == 'ATIVA' and s[1]['administrador'] is True, s)
    conferir('acesso/migration: nenhum convite existe', consulta(cur, 'select count(*) n from financeiro.convite')[0]['n'] == 0)
    conn.rollback()

    # ------------------------------------------------------------ 2. convite e ativacao de um terceiro usuario ficticio
    terceiro, email = str(uuid.uuid4()), 'terceiro.usuario@teste.local'
    cur.execute('insert into auth.users (id, email, email_confirmed_at) values (%s, %s, now())', (terceiro, email))
    conn.commit()
    antes = retrato()
    r = chamar(conn, cur, terceiro, 'select financeiro.ativar_minha_conta(%s::jsonb) j', (json.dumps({'nome': 'Pessoal'}),))
    conferir('acesso/convite: sem convite a ativacao e recusada e nada e criado', r == ('42501', 'SEM_CONVITE') and diferencas(antes, retrato()) == [], r)
    r = chamar(conn, cur, outro, 'select financeiro.criar_convite(%s::jsonb) j', (json.dumps({'email': email}),))
    conferir('acesso/convite: usuario comum nao convida', r == ('42501', 'SO_ADMINISTRADOR'), r)
    r = chamar(conn, cur, titular, 'select financeiro.criar_convite(%s::jsonb) j', (json.dumps({'email': email, 'validade_dias': 7}),))
    conferir('acesso/convite: o administrador registra o convite; nenhum dado e criado', r[0] == 'OK' and diferencas(antes, retrato()) == [], r[0])
    r = chamar(conn, cur, terceiro, 'select financeiro.ativar_minha_conta(%s::jsonb) j', (json.dumps({'nome': 'Pessoal', 'tipo': 'PESSOAL'}),))
    conferir('acesso/ativacao: conta ativada com o primeiro perfil', r[0] == 'OK' and r[1]['ativada'] and not r[1]['repetida'], r[0])
    perfil3 = r[1]['perfil']['id'] if r[0] == 'OK' else None
    depois = retrato()
    mudaram = set(diferencas(antes, depois))
    conferir('acesso/ativacao: so o perfil, o vinculo, o gerador, as preferencias e as categorias de cartao padrao sao criados',
             mudaram <= {'public.perfil_financeiro', 'financeiro.perfil_acesso', 'financeiro.gerador_recorrencia', 'financeiro.gerador_recorrencia_historico',
                         'financeiro.preferencia_usuario', 'public.categoria_cartao', 'public.categoria_cartao_despesa'}, sorted(mudaram))
    conferir('acesso/ativacao: o perfil novo nao tem conta bancaria, despesa nem compra',
             consulta(cur, """select (select count(*) from public.conta_bancaria where perfil_financeiro_id = %s) + (select count(*) from public.conta where perfil_financeiro_id = %s)
                                     + (select count(*) from public.lancamento_agregado where perfil_financeiro_id = %s) n""", (perfil3,) * 3)[0]['n'] == 0)
    conn.rollback()
    r = chamar(conn, cur, terceiro, 'select financeiro.ativar_minha_conta(%s::jsonb) j', (json.dumps({'nome': 'De novo'}),))
    conferir('acesso/ativacao: repetir nao cria nada', r[0] == 'OK' and r[1]['repetida'] and diferencas(depois, retrato()) == [], r[0])
    conferir('acesso/ativacao: TODAS as leituras de tela do titular identicas', diferencas(base['leituras'], E2.leituras(conn, titular, perfis)) == [])
    r = chamar(conn, cur, titular, 'select financeiro.categorias_tela(%s, null) j', (perfil3,))
    conferir('acesso/isolamento: o administrador NAO alcanca o perfil do usuario novo', r[0] == '42501', r)
    r = chamar(conn, cur, terceiro, 'select financeiro.categorias_tela(%s, null) j', (perfis[0],))
    conferir('acesso/isolamento: o usuario novo NAO alcanca o perfil do titular', r[0] == '42501', r)
    r = chamar(conn, cur, terceiro, 'select financeiro.usuarios_tela() j')
    conferir('acesso/isolamento: o usuario novo nao administra', r == ('42501', 'SO_ADMINISTRADOR'), r)

    # ------------------------------------------------------------ 3. suspensao e reativacao
    marca = retrato()
    r = chamar(conn, cur, titular, 'select financeiro.suspender_usuario(%s, %s) j', (terceiro, 'ensaio'))
    conferir('acesso/suspensao: o administrador suspende a conta', r[0] == 'OK', r)
    r1 = chamar(conn, cur, terceiro, 'select financeiro.categorias_tela(%s, null) j', (perfil3,))
    r2 = chamar(conn, cur, terceiro, "select coalesce(json_agg(x), '[]'::json) j from financeiro.meus_perfis() x")
    r3 = chamar(conn, cur, terceiro, 'select financeiro.criar_perfil(%s::jsonb) j', (json.dumps({'nome': 'Outro'}),))
    conferir('acesso/suspensao: a conta suspensa nao recebe resposta (perfil proprio recusado, lista vazia, criacao recusada)',
             r1[0] == '42501' and r2 == ('OK', []) and r3 == ('42501', 'CONTA_INATIVA'), (r1, r2, r3))
    conferir('acesso/suspensao: nada do usuario e apagado ou alterado', diferencas(marca, retrato()) == [], diferencas(marca, retrato()))
    r = chamar(conn, cur, titular, 'select financeiro.reativar_usuario(%s) j', (terceiro,))
    r1 = chamar(conn, cur, terceiro, 'select financeiro.categorias_tela(%s, null) j', (perfil3,))
    conferir('acesso/suspensao: reativada, a conta volta a usar o proprio perfil', r[0] == 'OK' and r1[0] == 'OK', (r[0], r1[0]))

    # ------------------------------------------------------------ 4. reversao
    try:
        cur.execute(REVERSAO.read_text(encoding='utf-8'))
        conn.commit()
        revertida = True
    except psycopg2.Error as e:
        conn.rollback()
        revertida = (e.diag.message_primary or '')[:120]
    conferir('acesso/reversao: aplicada', revertida is True, revertida)
    E1.NOVAS_ESTRUTURAS.difference_update(NOVAS_ESTRUTURAS)
    rf = retrato()
    conferir('acesso/reversao: estrutura retirada e dados identicos aos de depois da ativacao', not (NOVAS_ESTRUTURAS & set(rf))
             and diferencas({k: v for k, v in depois.items()}, rf) == [], diferencas(depois, rf))
    fr = funcoes()
    outras = sorted(k for k in set(fr) | set(base['funcoes']) if fr.get(k) != base['funcoes'].get(k))
    so_fim_de_linha = [k for k in outras if k in fr and k in base['funcoes'] and fr[k][1] == base['funcoes'][k][1]
                       and fr[k][0].replace('\r', '') == base['funcoes'][k][0].replace('\r', '')]
    rel['acesso']['funcoes_devolvidas_com_fim_de_linha_normalizado'] = len(so_fim_de_linha)
    conferir('acesso/reversao: funcoes identicas as de antes da migration (a menos do fim de linha do texto)', outras == so_fim_de_linha,
             [k for k in outras if k not in so_fim_de_linha][:6])
    conferir('acesso/reversao: leituras do titular identicas', diferencas(base['leituras'], E2.leituras(conn, titular, perfis)) == [])
    E1.NOVAS_ESTRUTURAS.update(NOVAS_ESTRUTURAS)
    cur.execute(MIGRATION.read_text(encoding='utf-8'))
    conn.commit()
    contas = {c['u']: c['situacao'] for c in consulta(cur, 'select user_id::text u, situacao from financeiro.usuario_plataforma')}
    conferir('acesso/reversao: migration reaplicada; as tres contas com perfil ficam ativas', contas == {titular: 'ATIVA', outro: 'ATIVA', terceiro: 'ATIVA'}, contas)
    conferir('acesso/reversao: leituras do titular identicas depois de reaplicar', diferencas(base['leituras'], E2.leituras(conn, titular, perfis)) == [])
    conn.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--saida', required=True, help='pasta privada do relatorio (fora do repositorio)')
    ap.add_argument('--pessoais', required=True, help='JSON com a lista de palavras-chave pessoais (a mesma do ensaio da etapa anterior)')
    ap.add_argument('--backup-id')
    a = ap.parse_args(argv)
    saida = Path(a.saida).resolve()
    if RAIZ in saida.parents or saida == RAIZ:
        raise SystemExit('A pasta do relatorio tem de ficar FORA do repositorio.')
    rel = E2.ensaiar(saida, json.loads(Path(a.pessoais).read_text(encoding='utf-8')), a.backup_id, depois=etapa_acesso)
    proprias = [v for v in rel['verificacoes'] if v['verificacao'].startswith('acesso/')]
    for v in proprias:
        print(('ok    ' if v['resultado'] == 'ok' else 'FALHA ') + v['verificacao'] + (f" [{v['detalhe']}]" if v['resultado'] != 'ok' and v['detalhe'] else ''))
    print(f"backup {rel['backup_id']} | {len(rel['verificacoes'])} verificacoes ({len(proprias)} desta etapa) | {len(rel['falhas'])} falha(s)")
    return 1 if rel['falhas'] else 0


if __name__ == '__main__':
    sys.exit(main())
