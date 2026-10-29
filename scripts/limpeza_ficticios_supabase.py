#!/usr/bin/env python
"""
FIN-BLOCO-D-1 (7) — retirada, POR IDENTIDADE, dos dados ficticios do projeto Supabase antes da conversao para producao.

Nada e apagado por tabela inteira, por marca ou por data. Uma linha so entra na relacao a retirar se:
- pertencer a um perfil ficticio declarado no arquivo de identidade (e conferido: nome declarado com "(ficticio)" e
  acessos so de usuarios de teste);
- for um registro global ficticio declarado (conferido: sem perfil e com o marcador no nome); ou
- depender, por chave estrangeira, de uma linha ja identificada, sem ter perfil real.
Qualquer linha ambigua (perfil nao declarado, registro real ligado a ficticio, ficticio ligado a registro real, usuario
que nao e de teste) interrompe tudo. Usuarios do Auth, perfis preservados, tabelas globais, migrations, politicas,
funcoes e privilegios nunca sao tocados (e sao conferidos antes do commit).

Uso (a conexao vem SO de variavel de ambiente e nunca e impressa):
    python scripts/limpeza_ficticios_supabase.py inventario --identidade ARQ [--dsn-env CF_LIMPEZA_DSN] [--saida REL]
        SOMENTE LEITURA: confere a identidade e grava a relacao (tabela -> chaves) a retirar.
    python scripts/limpeza_ficticios_supabase.py retirar --identidade ARQ --relacao REL [--dsn-env ...]
                                                         [--confirmar] [--projeto-autorizado REF] [--saida RELATORIO]
        Sem --confirmar: SIMULACAO numa transacao somente leitura (FIN-BLOCO-D-2) — nenhum comando de escrita, gatilho,
        sequencia ou auditoria; devolve so o plano (ordem, linhas a apagar, auditoria que os gatilhos gravariam).
        Com --confirmar: uma transacao (serializable) refaz a relacao, que tem de ser IGUAL a salva; apaga so essas
        chaves, dos dependentes para os principais; confere quantidades antes/depois, o md5 de cada linha preservada e
        a estrutura antes do commit. Num projeto Supabase exige --projeto-autorizado com o ref completo.
"""
import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2
import psycopg2.extras

ESQUEMAS = ('public', 'financeiro')
# Referencias sem chave estrangeira que ligam linhas (tabela.coluna -> tabela alvo).
REFERENCIAS_LOGICAS = {('public.lancamento_agregado', 'categoria_cartao_id'): 'public.categoria_cartao'}
POLIMORFICAS = {('public.item_despesa', 'origem_id'): ('origem_tipo', {
    'FINANCIAMENTO': 'public.financiamento', 'CONSORCIO': 'public.contrato_consorcio', 'VEICULO': 'public.veiculo',
    'ASSINATURA': 'public.mobilidade_assinatura'})}
# Linhas que gatilhos de auditoria criam durante a propria retirada: apagar uma linha da tabela de origem grava uma na
# de destino (o historico do gerador ganha uma linha por perfil removido). Sao do perfil ficticio e saem tambem;
# qualquer outra linha nova interrompe. A simulacao so as preve (nada executa).
GATILHOS_DE_AUDITORIA = {'financeiro.gerador_recorrencia': 'financeiro.gerador_recorrencia_historico'}
GERADAS_POR_GATILHO = tuple(GATILHOS_DE_AUDITORIA.values())


class LimpezaRecusada(Exception):
    """A retirada nao pode seguir (nada e gravado)."""


def _q(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def ref_do_dsn(dsn):
    """Ref do projeto Supabase pelo DSN (usuario postgres.<ref> do pooler ou host db.<ref>.supabase.co)."""
    partes = urlsplit(dsn)
    usuario, host = partes.username or '', partes.hostname or ''
    if usuario.startswith('postgres.'):
        return usuario.split('.', 1)[1]
    if host.endswith('.supabase.co') and host.startswith('db.'):
        return host.split('.')[1]
    return None


class Grafo:
    """Metadados (tabelas, chaves primarias, FKs) e linhas de public + financeiro."""

    def __init__(self, cur):
        self.cur = cur
        self.tabelas = [r['t'] for r in _q(cur, "select table_schema || '.' || table_name as t from information_schema.tables "
                                                "where table_schema = any(%s) and table_type = 'BASE TABLE' order by 1", (list(ESQUEMAS),))]
        self.colunas = defaultdict(dict)
        for r in _q(cur, "select table_schema || '.' || table_name as t, column_name as c, is_nullable as n "
                         "from information_schema.columns where table_schema = any(%s)", (list(ESQUEMAS),)):
            self.colunas[r['t']][r['c']] = r['n'] == 'YES'
        self.pk = {}
        for r in _q(cur, """select n.nspname || '.' || c.relname as t, array_agg(a.attname order by k.ord) as cols
                              from pg_index i join pg_class c on c.oid = i.indrelid join pg_namespace n on n.oid = c.relnamespace
                              cross join lateral unnest(i.indkey) with ordinality k(attnum, ord)
                              join pg_attribute a on a.attrelid = c.oid and a.attnum = k.attnum
                             where i.indisprimary and n.nspname = any(%s) group by 1""", (list(ESQUEMAS),)):
            self.pk[r['t']] = list(r['cols'])
        sem_pk = [t for t in self.tabelas if t not in self.pk]
        if sem_pk:
            raise LimpezaRecusada(f'Tabelas sem chave primaria (sem identidade de linha): {sem_pk}')
        self.fks = []  # (filho, coluna, pai, coluna do pai)
        for r in _q(cur, """select fn.nspname || '.' || fc.relname as filho, fa.attname as coluna,
                                   pn.nspname || '.' || pc.relname as pai, pa.attname as coluna_pai
                              from pg_constraint k
                              join pg_class fc on fc.oid = k.conrelid join pg_namespace fn on fn.oid = fc.relnamespace
                              join pg_class pc on pc.oid = k.confrelid join pg_namespace pn on pn.oid = pc.relnamespace
                              join pg_attribute fa on fa.attrelid = k.conrelid and fa.attnum = k.conkey[1]
                              join pg_attribute pa on pa.attrelid = k.confrelid and pa.attnum = k.confkey[1]
                             where k.contype = 'f' and fn.nspname = any(%s)""", (list(ESQUEMAS),)):
            if r['pai'] != 'public.perfil_financeiro':
                self.fks.append((r['filho'], r['coluna'], r['pai'], r['coluna_pai']))
        for (t, c), alvo in REFERENCIAS_LOGICAS.items():
            if c in self.colunas.get(t, {}) and alvo in self.pk:
                self.fks.append((t, c, alvo, self.pk[alvo][0]))
        self.linhas = {}  # tabela -> {chave: {coluna: valor}}
        for t in self.tabelas:
            precisa = set(self.pk[t]) | {c for f, c, _p, _cp in self.fks if f == t} | {cp for _f, _c, p, cp in self.fks if p == t}
            precisa |= {c for c in ('perfil_financeiro_id', 'user_id', 'origem_tipo', 'origem_id', 'nome') if c in self.colunas[t]}
            esquema, nome = t.split('.')
            chave_sql = ', '.join(f'"{c}"::text' for c in self.pk[t])
            cols = ', '.join(f'"{c}"' for c in sorted(precisa))
            linhas = _q(cur, f'select jsonb_build_array({chave_sql})::text as _k, md5(x::text) as _h, {cols} '
                             f'from "{esquema}"."{nome}" x')
            self.linhas[t] = {r['_k']: dict(r) for r in linhas}
        self.indice = {}  # (tabela, coluna) -> {valor texto: chave}

    def achar(self, t, coluna, valor):
        """Chave da linha de `t` cuja `coluna` vale `valor` (None se nao houver)."""
        if (t, coluna) not in self.indice:
            self.indice[(t, coluna)] = {str(l[coluna]): k for k, l in self.linhas.get(t, {}).items() if l.get(coluna) is not None}
        return self.indice[(t, coluna)].get(str(valor))

    def perfil(self, t, linha):
        return linha.get('perfil_financeiro_id') if 'perfil_financeiro_id' in self.colunas[t] else None


def montar_relacao(cur, identidade):
    """Relacao das linhas ficticias por identidade + ambiguidades. Nao grava nada."""
    g = Grafo(cur)
    fict = {int(k): v for k, v in identidade['perfis_ficticios'].items()}
    preservados = {int(k): v for k, v in identidade['perfis_preservados'].items()}
    usuarios_teste = set(identidade['usuarios_teste'])
    ambiguos, avisos = [], []

    # 1. Perfis: todos classificados, nomes conferidos, acessos so de usuarios de teste nos ficticios.
    perfis = {int(l['id']): l['nome'] for l in g.linhas['public.perfil_financeiro'].values()}
    for pid, nome in sorted(perfis.items()):
        if pid in fict:
            if nome != fict[pid] or '(ficticio)' not in nome:
                ambiguos.append(f'perfil {pid}: nome no banco difere do declarado como ficticio')
        elif pid in preservados:
            if nome != preservados[pid]:
                ambiguos.append(f'perfil {pid}: nome no banco difere do declarado como preservado')
        else:
            ambiguos.append(f'perfil {pid} nao declarado (nem ficticio nem preservado)')
    for pid in set(fict) | set(preservados):
        if pid not in perfis:
            ambiguos.append(f'perfil {pid} declarado mas inexistente')
    for l in g.linhas.get('financeiro.perfil_acesso', {}).values():
        pid, uid = int(l['perfil_financeiro_id']), str(l['user_id'])
        if pid in fict and uid not in usuarios_teste:
            ambiguos.append(f'perfil ficticio {pid} acessado por usuario que nao e de teste ({uid[:8]})')
        if pid in preservados and uid in usuarios_teste:
            ambiguos.append(f'perfil preservado {pid} acessado por usuario de teste ({uid[:8]})')

    # 2. Sementes: linhas dos perfis ficticios, os proprios perfis e os globais declarados.
    relacao = defaultdict(set)
    motivo = {}
    for t, linhas in g.linhas.items():
        for k, l in linhas.items():
            p = g.perfil(t, l)
            if p is not None and int(p) in fict:
                relacao[t].add(k)
                motivo[(t, k)] = 'perfil'
    for k, l in g.linhas['public.perfil_financeiro'].items():
        if int(l['id']) in fict:
            relacao['public.perfil_financeiro'].add(k)
    for t, regra in identidade.get('globais_ficticios', {}).items():
        for gid in regra['ids']:
            k = json.dumps([str(gid)])
            l = g.linhas.get(t, {}).get(k)
            if l is None:
                ambiguos.append(f'{t} {gid}: global ficticio declarado mas inexistente')
            elif g.perfil(t, l) is not None or not str(l.get('nome') or '').endswith(regra['marcador']):
                ambiguos.append(f'{t} {gid}: nao tem a forma declarada (sem perfil e com "{regra["marcador"]}")')
            else:
                relacao[t].add(k)
                motivo[(t, k)] = 'global declarado'

    # 3. Fecho: dependentes (por FK) das linhas identificadas.
    mudou = True
    while mudou:
        mudou = False
        for f, c, p, cp in g.fks:
            if p not in relacao or f not in g.linhas:
                continue
            alvos = {str(g.linhas[p][k][cp]) for k in relacao[p] if g.linhas[p][k].get(cp) is not None}
            for k, l in g.linhas[f].items():
                if k in relacao[f] or l.get(c) is None or str(l[c]) not in alvos:
                    continue
                perfil = g.perfil(f, l)
                if perfil is not None and int(perfil) not in fict:
                    ambiguos.append(f'{f} {k}: do perfil {perfil} e depende de ficticio ({p} por {c})')
                    continue
                relacao[f].add(k)
                motivo[(f, k)] = f'dependente de {p}'
                mudou = True

    # 4. Conferencias no sentido contrario: ficticio nao pode apontar para registro de perfil preservado nem usuario real.
    referencias_globais = defaultdict(int)
    for f, c, p, cp in g.fks:
        for k in relacao.get(f, ()):
            v = g.linhas[f][k].get(c)
            if v is None:
                continue
            if p == 'auth.users':
                if str(v) not in usuarios_teste:
                    ambiguos.append(f'{f} {k}: ficticio ligado a usuario que nao e de teste ({str(v)[:8]})')
                continue
            alvo = g.achar(p, cp, v)
            if alvo is None or alvo in relacao.get(p, ()):
                continue
            perfil_alvo = g.perfil(p, g.linhas[p][alvo])
            if perfil_alvo is not None:
                ambiguos.append(f'{f} {k}: ficticio ligado a {p} do perfil {perfil_alvo}')
            else:
                referencias_globais[p] += 1
    for t, linhas in g.linhas.items():
        if 'user_id' in g.colunas[t] and not any(f == t and c == 'user_id' for f, c, _p, _cp in g.fks):
            for k in relacao.get(t, ()):
                uid = linhas[k].get('user_id')
                if uid is not None and str(uid) not in usuarios_teste:
                    ambiguos.append(f'{t} {k}: ficticio com user_id que nao e de teste')
    for (t, c), (coluna_tipo, alvos) in POLIMORFICAS.items():
        for k, l in g.linhas.get(t, {}).items():
            if l.get(c) is None:
                continue
            alvo_t = alvos.get(l.get(coluna_tipo))
            alvo = g.achar(alvo_t, 'id', l[c]) if alvo_t else None
            if alvo_t is None:
                ambiguos.append(f'{t} {k}: {coluna_tipo} sem regra')
            elif (k in relacao.get(t, ())) != (alvo is not None and alvo in relacao.get(alvo_t, ())):
                ambiguos.append(f'{t} {k}: origem ({alvo_t}) e item em lados diferentes da retirada')

    # 5. Usuarios de teste referenciados por linhas que ficam (nao impede a retirada; impede apagar o usuario depois).
    fica_com_usuario_teste = defaultdict(int)
    for t, linhas in g.linhas.items():
        if 'user_id' in g.colunas[t]:
            for k, l in linhas.items():
                if k not in relacao.get(t, ()) and str(l.get('user_id')) in usuarios_teste:
                    fica_com_usuario_teste[t] += 1
    if fica_com_usuario_teste:
        avisos.append(f'linhas preservadas que citam usuario de teste: {dict(fica_com_usuario_teste)}')

    tabelas = {t: sorted(ks) for t, ks in sorted(relacao.items()) if ks}
    por_motivo = defaultdict(int)
    for (t, _k), m in motivo.items():
        por_motivo[f'{t}: {m}'] += 1
    return {
        'tabelas': tabelas,
        'quantidades': {t: len(ks) for t, ks in tabelas.items()},
        'total': sum(len(ks) for ks in tabelas.values()),
        'por_motivo': dict(sorted(por_motivo.items())),
        'preservadas': {t: len(l) - len(relacao.get(t, ())) for t, l in g.linhas.items() if len(l) - len(relacao.get(t, ()))},
        'referencias_a_globais_preservados': dict(referencias_globais),
        'ambiguos': sorted(set(ambiguos)),
        'avisos': avisos,
    }, g


def estrutura(cur):
    """Impressao digital do que a retirada nao pode mudar."""
    tem_migrations = _q(cur, "select to_regclass('supabase_migrations.schema_migrations') is not null as x")[0]['x']
    partes = {
        'migrations': [r['version'] for r in _q(cur, 'select version from supabase_migrations.schema_migrations order by 1')]
        if tem_migrations else [],
        'politicas': _q(cur, "select md5(coalesce(string_agg(schemaname||tablename||policyname||coalesce(qual,'')||coalesce(with_check,''), '|' "
                             "order by schemaname, tablename, policyname), '')) as h from pg_policies"),
        'funcoes': _q(cur, "select md5(coalesce(string_agg(p.oid::regprocedure::text || md5(p.prosrc) || coalesce(array_to_string(p.proacl, ','), ''), '|' "
                           "order by p.oid::regprocedure::text), '')) as h from pg_proc p where p.pronamespace in "
                           "('public'::regnamespace, 'financeiro'::regnamespace)"),
        'privilegios': _q(cur, "select md5(coalesce(string_agg(grantee||table_schema||table_name||privilege_type, '|' order by 1), '')) as h "
                               "from (select grantee, table_schema, table_name, privilege_type from information_schema.role_table_grants "
                               "where table_schema = any(%s)) x", (list(ESQUEMAS),)),
        'rls': _q(cur, "select md5(coalesce(string_agg(c.oid::regclass::text || c.relrowsecurity::text, '|' order by 1), '')) as h "
                       "from pg_class c where c.relkind = 'r' and c.relnamespace in ('public'::regnamespace, 'financeiro'::regnamespace)"),
        'usuarios_auth': _q(cur, "select count(*) as n, md5(coalesce(string_agg(id::text, ',' order by id), '')) as h from auth.users"),
    }
    return hashlib.sha256(json.dumps(partes, sort_keys=True, default=str).encode()).hexdigest(), partes


def ordem_de_retirada(g, tabelas):
    """Dependentes antes dos principais. Ciclos: as colunas do ciclo (nas linhas retiradas) sao anuladas antes."""
    pendentes = set(tabelas)
    ordem, anular = [], set()
    while pendentes:
        prontas = sorted(t for t in pendentes
                         if not any(p == t and f in pendentes and f != t for f, _c, p, _cp in g.fks))
        if not prontas:
            t = min(sorted(pendentes), key=lambda x: sum(p == x and f in pendentes and f != x for f, _c, p, _cp in g.fks))
            anular |= {(f, c) for f, c, p, _cp in g.fks if p == t and f in pendentes and f != t}
            prontas = [t]
        for t in prontas:
            anular |= {(f, c) for f, c, p, _cp in g.fks if f == t and p == t}
            ordem.append(t)
            pendentes.discard(t)
    # O perfil (referenciado por quase todas as tabelas; fora do grafo de identidade) sai por ultimo; a auditoria que os
    # gatilhos gravam durante a retirada, depois dele.
    fim = [t for t in ('public.perfil_financeiro', *GERADAS_POR_GATILHO) if t in ordem]
    return [t for t in ordem if t not in fim] + fim, sorted(anular)


def _onde(g, t):
    return 'jsonb_build_array(' + ', '.join(f'"{c}"::text' for c in g.pk[t]) + ') in (select jsonb_array_elements(%s::jsonb))'


def _chaves(chaves):
    return json.dumps([json.loads(k) for k in chaves])


def _plano(cur, identidade, relacao_salva):
    """Conferencias comuns a simulacao e a retirada (so leitura): relacao sem ambiguidade e igual a salva, ordem de
    retirada e colunas de ciclo que aceitam nulo."""
    relacao, g = montar_relacao(cur, identidade)
    if relacao['ambiguos']:
        raise LimpezaRecusada(f'Registros ambiguos: {relacao["ambiguos"][:20]}')
    if relacao['tabelas'] != relacao_salva['tabelas']:
        difs = sorted(set(relacao['tabelas']) ^ set(relacao_salva['tabelas'])
                      | {t for t in relacao['tabelas'] if relacao['tabelas'][t] != relacao_salva['tabelas'].get(t)})
        raise LimpezaRecusada(f'A relacao mudou desde o inventario (tabelas {difs}): refaca o inventario')
    ordem, anular = ordem_de_retirada(g, relacao['tabelas'])
    anular = [(t, c) for t, c in anular if t in relacao['tabelas']]
    for t, c in anular:
        if not g.colunas[t][c]:
            raise LimpezaRecusada(f'{t}.{c} esta num ciclo e nao aceita nulo')
    return relacao, g, ordem, anular


def simular(conn, identidade, relacao_salva):
    """Modo de simulacao: transacao SOMENTE LEITURA; nenhum comando de escrita e executado (nenhum gatilho dispara,
    nenhuma sequencia avanca). Devolve so o plano: o que seria anulado e apagado, em que ordem, e as linhas de auditoria
    que os gatilhos gravariam (e que a retirada apagaria em seguida). Deterministico: repetir da o mesmo resultado."""
    conn.rollback()
    conn.set_session(isolation_level=psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ, readonly=True, autocommit=False)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        relacao, g, ordem, anular = _plano(cur, identidade, relacao_salva)
        removeria = {t: len(relacao['tabelas'][t]) for t in ordem}
        auditoria = {destino: len(relacao['tabelas'].get(origem, ())) for origem, destino in GATILHOS_DE_AUDITORIA.items()
                     if relacao['tabelas'].get(origem)}
        impressao, partes = estrutura(cur)
        return {
            'resultado': 'SIMULACAO (somente leitura: nada executado)', 'ordem': ordem,
            'colunas_anuladas_antes': [f'{t}.{c}' for t, c in anular], 'removeria': removeria,
            'auditoria_que_os_gatilhos_gravariam_e_seria_removida': auditoria,
            'total_previsto': sum(removeria.values()) + sum(auditoria.values()),
            'linhas_atuais': {t: len(l) for t, l in sorted(g.linhas.items()) if l},
            'estrutura': {'impressao_digital': impressao, 'migrations': len(partes['migrations']),
                          'usuarios_auth': partes['usuarios_auth'][0]['n']},
        }
    finally:
        conn.rollback()


def retirar(conn, identidade, relacao_salva, confirmar):
    """Sem confirmar: simulacao somente leitura (simular). Com confirmar: retirada numa transacao serializable."""
    if not confirmar:
        return simular(conn, identidade, relacao_salva)
    conn.rollback()
    conn.set_session(isolation_level=psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE, readonly=False, autocommit=False)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    relatorio = {}
    try:
        relacao, g, ordem, anular = _plano(cur, identidade, relacao_salva)
        fict = [int(k) for k in identidade['perfis_ficticios']]
        antes = {t: len(l) for t, l in g.linhas.items()}
        hash_preservadas = {t: sorted(l[k]['_h'] for k in l if k not in relacao['tabelas'].get(t, ())) for t, l in g.linhas.items()}
        estrutura_antes, _ = estrutura(cur)
        relatorio['ordem'] = ordem
        relatorio['colunas_anuladas_antes'] = [f'{t}.{c}' for t, c in anular]
        for t, c in anular:
            if t in relacao['tabelas']:
                esquema, nome = t.split('.')
                cur.execute(f'update "{esquema}"."{nome}" set "{c}" = null where "{c}" is not null and ' + _onde(g, t),
                            (_chaves(relacao['tabelas'][t]),))
        removidas, geradas = {}, {}
        for t in ordem:
            esquema, nome = t.split('.')
            chaves = relacao['tabelas'][t]
            cur.execute(f'delete from "{esquema}"."{nome}" where ' + _onde(g, t), (_chaves(chaves),))
            if cur.rowcount != len(chaves):
                raise LimpezaRecusada(f'{t}: {cur.rowcount} linhas apagadas, esperadas {len(chaves)}')
            removidas[t] = cur.rowcount
            if t in GERADAS_POR_GATILHO:
                cur.execute(f'delete from "{esquema}"."{nome}" where perfil_financeiro_id = any(%s)', (fict,))
                geradas[t] = cur.rowcount
        for t in GERADAS_POR_GATILHO:  # tabela de auditoria sem linha previa na relacao
            if t not in removidas and t in g.linhas:
                esquema, nome = t.split('.')
                cur.execute(f'delete from "{esquema}"."{nome}" where perfil_financeiro_id = any(%s)', (fict,))
                if cur.rowcount:
                    geradas[t] = cur.rowcount
        # Conferencias antes do commit.
        depois_g = Grafo(cur)
        depois = {t: len(l) for t, l in depois_g.linhas.items()}
        erros = []
        for t in antes:
            esperado = antes[t] - removidas.get(t, 0)
            if depois.get(t) != esperado:
                erros.append(f'{t}: {depois.get(t)} linhas depois, esperadas {esperado}')
            if sorted(l['_h'] for l in depois_g.linhas.get(t, {}).values()) != hash_preservadas[t]:
                erros.append(f'{t}: linhas preservadas alteradas')
            if 'perfil_financeiro_id' in depois_g.colunas.get(t, {}):
                sobra = [k for k, l in depois_g.linhas[t].items() if l.get('perfil_financeiro_id') is not None
                         and int(l['perfil_financeiro_id']) in fict]
                if sobra:
                    erros.append(f'{t}: {len(sobra)} linha(s) de perfil ficticio sobraram')
        estrutura_depois, partes = estrutura(cur)
        if estrutura_depois != estrutura_antes:
            erros.append('estrutura (migrations, politicas, funcoes, privilegios, RLS ou usuarios) mudou')
        if erros:
            raise LimpezaRecusada(f'Conferencia falhou: {erros[:20]}')
        relatorio.update({
            'antes': antes, 'removidas': removidas, 'geradas_por_gatilho_e_removidas': geradas, 'depois': depois,
            'total_removido': sum(removidas.values()) + sum(geradas.values()),
            'estrutura': {'impressao_digital': estrutura_depois, 'migrations': len(partes['migrations']),
                          'usuarios_auth': partes['usuarios_auth'][0]['n']},
            'conferencia': 'OK: so as linhas da relacao sairam; preservadas, estrutura e usuarios identicos',
        })
        conn.commit()
        relatorio['resultado'] = 'RETIRADO'
        return relatorio
    except Exception:
        conn.rollback()
        raise


def _dsn(variavel):
    valor = os.environ.get(variavel or '')
    if not valor:
        raise SystemExit(f'Variavel de ambiente {variavel!r} vazia: informe a conexao por ela (nunca na linha de comando).')
    return valor


def _conferir_projeto(dsn, identidade, autorizado):
    ref = ref_do_dsn(dsn)
    if ref is None:
        return 'banco nao Supabase (descartavel)'
    if not ref.startswith(identidade['projeto_ref_prefixo']):
        raise LimpezaRecusada('A conexao nao aponta para o projeto da identidade')
    if autorizado is not None and autorizado != ref:
        raise LimpezaRecusada('--projeto-autorizado nao confere com a conexao')
    return ref


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = p.add_subparsers(dest='comando', required=True)
    for nome in ('inventario', 'retirar'):
        s = sub.add_parser(nome)
        s.add_argument('--identidade', required=True)
        s.add_argument('--dsn-env', default='CF_LIMPEZA_DSN')
        s.add_argument('--saida')
        if nome == 'retirar':
            s.add_argument('--relacao', required=True)
            s.add_argument('--confirmar', action='store_true')
            s.add_argument('--projeto-autorizado')
    args = p.parse_args(argv)
    identidade = json.loads(Path(args.identidade).read_text(encoding='utf-8'))
    dsn = _dsn(args.dsn_env)
    try:
        projeto = _conferir_projeto(dsn, identidade, getattr(args, 'projeto_autorizado', None))
        if args.comando == 'retirar' and projeto != 'banco nao Supabase (descartavel)' and not args.projeto_autorizado:
            raise LimpezaRecusada('Projeto Supabase: informe --projeto-autorizado <ref> (autorizacao expressa do titular)')
        conn = psycopg2.connect(dsn, connect_timeout=20)
        try:
            if args.comando == 'inventario':
                conn.set_session(readonly=True)
                relacao, _ = montar_relacao(conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor), identidade)
                conn.rollback()
                saida = relacao
                codigo = 1 if relacao['ambiguos'] else 0
            else:
                relacao_salva = json.loads(Path(args.relacao).read_text(encoding='utf-8'))
                saida = retirar(conn, identidade, relacao_salva, args.confirmar)
                codigo = 0
        finally:
            conn.close()
    except LimpezaRecusada as erro:
        print(f'LIMPEZA_RECUSADA: {erro}', file=sys.stderr)
        return 2
    texto = json.dumps(saida, ensure_ascii=False, indent=1, default=str)
    if args.saida:
        Path(args.saida).write_text(texto, encoding='utf-8')
    resumo = {k: v for k, v in saida.items() if k != 'tabelas'}
    print(json.dumps(resumo, ensure_ascii=False, indent=1, default=str))
    return codigo


if __name__ == '__main__':
    sys.exit(main())
