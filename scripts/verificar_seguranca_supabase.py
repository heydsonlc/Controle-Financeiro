#!/usr/bin/env python
"""
FIN-BLOCO-D-2 (9) — revisao de seguranca do projeto Supabase, SOMENTE LEITURA (sessao read only + GET publico do Auth).
Diferente de verificar_exposicao_supabase.py, nao faz nenhuma sondagem de escrita.

Confere: RLS em todas as tabelas de public e financeiro; nenhum privilegio do anon em tabelas nem funcoes; o que o
authenticated alcanca direto (tabelas) e por funcoes; funcoes security definer com search_path fixo; documentos so no
banco (sem bucket); nenhum CVV, validade ou numero completo de cartao; contas do Auth (rotuladas, sem e-mail) e a
configuracao publica do Auth (cadastro, provedores, confirmacao).

Uso (conexao so por variavel de ambiente, nunca impressa):
    set CF_SEGURANCA_DSN=...   python scripts/verificar_seguranca_supabase.py [--usuarios-teste ID ...] [--saida ARQ]
Saida: relatorio JSON; codigo 1 se houver achado bloqueante.
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

import psycopg2

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.limpeza_ficticios_supabase import ref_do_dsn  # noqa: E402

NSP = "('public'::regnamespace, 'financeiro'::regnamespace)"
COLUNAS_SENSIVEIS = ('codigo_seguranca', 'cvv', 'data_validade', 'numero_cartao')


def verificar(cur, usuarios_teste=()):
    def q(sql, p=None):
        cur.execute(sql, p)
        return cur.fetchall()

    r, bloqueios = {}, []
    r['tabelas_sem_rls'] = [t for (t,) in q(f"select c.oid::regclass::text from pg_class c where c.relkind = 'r' "
                                            f"and c.relnamespace in {NSP} and not c.relrowsecurity order by 1")]
    r['politicas'] = [f'{s}.{t}:{p}:{cmd}:{roles}' for s, t, p, cmd, roles in q(
        "select schemaname, tablename, policyname, cmd, roles::text from pg_policies where schemaname in ('public', 'financeiro') order by 1, 2, 3")]
    acl = ("select a.grantee::regrole::text, c.oid::regclass::text, a.privilege_type from pg_class c "
           f"cross join lateral aclexplode(c.relacl) a where c.relnamespace in {NSP} and c.relkind in ('r', 'v', 'm', 'S') "
           "and a.grantee <> 0 and a.grantee::regrole::text = %s order by 2, 3")
    r['anon_tabelas'] = [f'{t}:{p}' for _g, t, p in q(acl, ('anon',))]
    r['authenticated_tabelas'] = [f'{t}:{p}' for _g, t, p in q(acl, ('authenticated',))]
    r['public_tabelas'] = [f'{t}:{p}' for t, p in q(
        f"select c.oid::regclass::text, a.privilege_type from pg_class c cross join lateral aclexplode(c.relacl) a "
        f"where c.relnamespace in {NSP} and a.grantee = 0 order by 1, 2")]
    funcs = f"select count(*) from pg_proc p where p.pronamespace in {NSP} and has_function_privilege(%s, p.oid, 'execute')"
    r['anon_funcoes'] = q(funcs, ('anon',))[0][0]
    r['authenticated_funcoes'] = q(funcs, ('authenticated',))[0][0]
    r['definer_sem_search_path'] = [f for (f,) in q(
        f"select p.oid::regprocedure::text from pg_proc p where p.pronamespace in {NSP} and p.prosecdef "
        "and not exists (select 1 from unnest(coalesce(p.proconfig, '{}')) c where c like 'search_path=%%')")]
    r['schemas_com_usage_anon'] = [s for (s,) in q("select nspname from pg_namespace where nspname in ('public', 'financeiro') "
                                                   "and has_schema_privilege('anon', oid, 'usage')")]
    r['storage'] = {'buckets': q('select count(*) from storage.buckets')[0][0], 'objetos': q('select count(*) from storage.objects')[0][0]} \
        if q("select to_regclass('storage.buckets') is not null")[0][0] else 'sem storage'
    r['documentos_no_banco'] = q('select count(*) from public.ir_comprovante_arquivo')[0][0] \
        if q("select to_regclass('public.ir_comprovante_arquivo') is not null")[0][0] else 0
    sensiveis = {}
    for s, t, c in q("select table_schema, table_name, column_name from information_schema.columns "
                     "where table_schema in ('public', 'financeiro') and column_name = any(%s)", (list(COLUNAS_SENSIVEIS),)):
        if c == 'numero_cartao':
            n = q(f"select count(*) from \"{s}\".\"{t}\" where length(regexp_replace(coalesce(numero_cartao::text, ''), '\\D', '', 'g')) > 4")[0][0]
        else:
            n = q(f'select count(*) from "{s}"."{t}" where "{c}" is not null')[0][0]
        sensiveis[f'{s}.{t}.{c}'] = n
    r['cartao_sensivel_preenchido'] = sensiveis
    contas = q("select id::text, email_confirmed_at is not null, last_sign_in_at::date::text, "
               "(select count(*) from auth.sessions s where s.user_id = u.id), "
               "(select string_agg(distinct i.provider, ',') from auth.identities i where i.user_id = u.id) from auth.users u order by created_at")
    r['contas_auth'] = [{'rotulo': 'TESTE' if uid in usuarios_teste else 'OUTRA', 'id_prefixo': uid[:8], 'confirmada': conf,
                         'ultimo_login': ult, 'sessoes': ses, 'provedores': prov} for uid, conf, ult, ses, prov in contas]
    r['acessos_por_conta'] = {uid[:8]: n for uid, n in q("select user_id::text, count(*) from financeiro.perfil_acesso group by 1")}

    if r['tabelas_sem_rls']:
        bloqueios.append('tabelas sem RLS')
    if r['anon_tabelas'] or r['anon_funcoes'] or r['public_tabelas']:
        bloqueios.append('anon/PUBLIC com privilegio em tabela ou funcao')
    if r['definer_sem_search_path']:
        bloqueios.append('security definer sem search_path')
    if any(sensiveis.values()):
        bloqueios.append('dado sensivel de cartao preenchido')
    r['bloqueios'] = bloqueios
    return r


def auth_publico(ref):
    from scripts.verificar_exposicao_supabase import chave_publica_via_cli
    chave, _ = chave_publica_via_cli()
    req = urllib.request.Request(f'https://{ref}.supabase.co/auth/v1/settings', headers={'apikey': chave})
    cfg = json.loads(urllib.request.urlopen(req, timeout=20).read())
    return {'disable_signup': cfg.get('disable_signup'), 'mailer_autoconfirm': cfg.get('mailer_autoconfirm'),
            'phone_autoconfirm': cfg.get('phone_autoconfirm'), 'anonymous_users': cfg.get('anonymous_users'),
            'saml_enabled': cfg.get('saml_enabled'), 'provedores_ativos': sorted(k for k, v in (cfg.get('external') or {}).items() if v)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--dsn-env', default='CF_SEGURANCA_DSN')
    p.add_argument('--usuarios-teste', nargs='*', default=[])
    p.add_argument('--saida')
    args = p.parse_args(argv)
    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        print(f'Defina {args.dsn_env}', file=sys.stderr)
        return 2
    conn = psycopg2.connect(dsn, connect_timeout=20)
    conn.set_session(readonly=True)
    try:
        r = verificar(conn.cursor(), set(args.usuarios_teste))
    finally:
        conn.rollback()
        conn.close()
    ref = ref_do_dsn(dsn)
    if ref:
        r['projeto'] = ref[:6] + '...'
        os.environ.setdefault('CF_SUPABASE_PROJECT_REF', ref)
        try:
            r['auth_publico'] = auth_publico(ref)
            if r['auth_publico']['disable_signup'] is not True or r['auth_publico']['mailer_autoconfirm']:
                r['bloqueios'].append('cadastro publico aberto ou e-mail sem confirmacao')
        except Exception as erro:  # noqa: BLE001
            r['auth_publico'] = f'nao lido: {type(erro).__name__}'
    texto = json.dumps(r, ensure_ascii=False, indent=1, default=str)
    if args.saida:
        Path(args.saida).write_text(texto, encoding='utf-8')
    print(texto)
    return 1 if r['bloqueios'] else 0


if __name__ == '__main__':
    sys.exit(main())
