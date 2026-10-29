#!/usr/bin/env python
"""
FIN-BLOCO-D-2 (7) — vinculo da conta do titular (Supabase Auth) aos perfis reais "Pessoal" e "Empresa".

A conta NAO e criada aqui: ela nasce no painel do Supabase (Authentication -> Users -> Invite user), e o proprio titular
define a senha pelo link do convite. O login antigo do Flask (public.usuario) nao e usado: o Auth tem identidade propria.
Este script so liga essa conta, ja confirmada, aos perfis, com papel TITULAR e pode_gerir.

Uso (conexao e e-mail so por variavel de ambiente; nada e impresso deles):
    set CF_VINCULO_DSN=...   set CF_TITULAR_EMAIL=...
    python scripts/vincular_titular_supabase.py conferir --identidade docs/carga/identidade_ficticios_supabase.json
        SOMENTE LEITURA: conta encontrada uma unica vez, e-mail confirmado, nao e conta de teste; perfis existem com os
        nomes esperados e sem nenhum outro acesso.
    python scripts/vincular_titular_supabase.py vincular --identidade ... --confirmar --projeto-autorizado <ref>
        Uma transacao: grava os 2 acessos e confere, antes do commit, que o titular ve exatamente os 2 perfis como gestor
        e que nenhum outro usuario os alcanca. Sem --confirmar: so a conferencia (nada e gravado).
"""
import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.limpeza_ficticios_supabase import ref_do_dsn  # noqa: E402

PERFIS_REAIS = {1: 'Pessoal', 2: 'Empresa'}


class VinculoRecusado(Exception):
    """O vinculo nao pode seguir (nada e gravado)."""


def _q(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def conferir(cur, email, identidade):
    """Pre-condicoes do vinculo (so leitura). Devolve o id da conta e o estado de cada perfil."""
    colunas = {r['column_name'] for r in _q(cur, "select column_name from information_schema.columns "
                                                 "where table_schema = 'auth' and table_name = 'users'")}
    confirmado = 'email_confirmed_at is not null' if 'email_confirmed_at' in colunas else 'true'
    contas = _q(cur, f'select id::text as id, {confirmado} as confirmado from auth.users where lower(email) = lower(%s)', (email,))
    if len(contas) != 1:
        raise VinculoRecusado(f'Conta do titular no Auth: {len(contas)} encontrada(s) para o e-mail informado (esperada 1)')
    conta = contas[0]
    if conta['id'] in identidade.get('usuarios_teste', []):
        raise VinculoRecusado('O e-mail informado e de uma conta de teste')
    if not conta['confirmado']:
        raise VinculoRecusado('E-mail da conta do titular ainda nao confirmado (aceitar o convite antes)')
    estado = {}
    for pid, nome in PERFIS_REAIS.items():
        perfil = _q(cur, 'select nome, ativo from public.perfil_financeiro where id = %s', (pid,))
        if not perfil or perfil[0]['nome'] != nome or not perfil[0]['ativo']:
            raise VinculoRecusado(f'Perfil {pid} nao e o "{nome}" ativo esperado')
        acessos = _q(cur, 'select user_id::text as u, papel, pode_gerir from financeiro.perfil_acesso where perfil_financeiro_id = %s', (pid,))
        outros = [a for a in acessos if a['u'] != conta['id']]
        if outros:
            raise VinculoRecusado(f'Perfil "{nome}" ja tem {len(outros)} acesso(s) de outra conta: resolver antes')
        estado[nome] = 'ja vinculado' if acessos else 'a vincular'
    return conta['id'], estado


def vincular(conn, email, identidade, confirmar):
    conn.rollback()
    conn.set_session(isolation_level=psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE, readonly=not confirmar, autocommit=False)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        uid, estado = conferir(cur, email, identidade)
        relatorio = {'conta': uid[:8], 'perfis': estado}
        if not confirmar:
            relatorio['resultado'] = 'CONFERENCIA (somente leitura: nada gravado)'
            return relatorio
        for pid, nome in PERFIS_REAIS.items():
            if estado[nome] == 'a vincular':
                cur.execute("insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) "
                            "values (%s, %s, 'TITULAR', true)", (uid, pid))
            else:
                cur.execute("update financeiro.perfil_acesso set papel = 'TITULAR', pode_gerir = true "
                            "where user_id = %s and perfil_financeiro_id = %s", (uid, pid))
        # Conferencia antes do commit: como o proprio titular (claims do Auth), ve so os 2 perfis, como gestor.
        cur.execute('set local role authenticated')
        cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({'sub': uid, 'role': 'authenticated'}),))
        vistos = {r['id']: r['papel'] for r in _q(cur, 'select id, papel from financeiro.meus_perfis()')}
        gere = {pid: _q(cur, 'select financeiro.pode_gerir_perfil(%s) as g', (pid,))[0]['g'] for pid in PERFIS_REAIS}
        cur.execute('reset role')
        outros = _q(cur, 'select count(*) as n from financeiro.perfil_acesso where perfil_financeiro_id = any(%s) and user_id <> %s',
                    (list(PERFIS_REAIS), uid))[0]['n']
        if set(vistos) != set(PERFIS_REAIS) or set(vistos.values()) != {'TITULAR'} or not all(gere.values()) or outros:
            raise VinculoRecusado(f'Conferencia falhou (perfis vistos {sorted(vistos)}, gestor {gere}, outros acessos {outros})')
        conn.commit()
        relatorio.update({'resultado': 'VINCULADO', 'perfis_vistos_pelo_titular': sorted(vistos), 'gestor': gere})
        return relatorio
    except Exception:
        conn.rollback()
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = p.add_subparsers(dest='comando', required=True)
    for nome in ('conferir', 'vincular'):
        s = sub.add_parser(nome)
        s.add_argument('--identidade', required=True)
        s.add_argument('--dsn-env', default='CF_VINCULO_DSN')
        s.add_argument('--email-env', default='CF_TITULAR_EMAIL')
        if nome == 'vincular':
            s.add_argument('--confirmar', action='store_true')
            s.add_argument('--projeto-autorizado')
    args = p.parse_args(argv)
    identidade = json.loads(Path(args.identidade).read_text(encoding='utf-8'))
    dsn, email = os.environ.get(args.dsn_env), os.environ.get(args.email_env)
    try:
        if not dsn or not email:
            raise VinculoRecusado(f'Defina {args.dsn_env} e {args.email_env}')
        ref = ref_do_dsn(dsn)
        if ref is not None and not ref.startswith(identidade['projeto_ref_prefixo']):
            raise VinculoRecusado('A conexao nao aponta para o projeto da identidade')
        confirmar = args.comando == 'vincular' and args.confirmar
        if confirmar and ref is not None and args.projeto_autorizado != ref:
            raise VinculoRecusado('Projeto Supabase: informe --projeto-autorizado <ref> (autorizacao expressa do titular)')
        conn = psycopg2.connect(dsn, connect_timeout=20)
        try:
            relatorio = vincular(conn, email, identidade, confirmar)
        finally:
            conn.close()
    except VinculoRecusado as erro:
        print(f'VINCULO_RECUSADO: {erro}', file=sys.stderr)
        return 2
    print(json.dumps(relatorio, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
