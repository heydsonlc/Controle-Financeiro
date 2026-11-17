"""FIN-CATEGORIAS-REORGANIZACAO-01 — ensaio completo numa copia fiel da producao, em PostgreSQL DESCARTAVEL local.

    python scripts/ensaio_categorias_reorganizacao.py --saida <pasta privada> [--backup-id ID]

Restaura o backup guardado (o mais recente, ou o indicado) pela ferramenta homologada do FIN-REG-01/02, num cluster local
criado e destruido aqui (nunca recebe uma conexao de fora: nao ha como apontar para o Supabase), aplica a migration
20261229090000 e roda scripts/reorganizar_categorias.py (previa, execucao e reversao), medindo antes, depois e depois da
reversao: o banco inteiro fora a coluna da categoria, saldos, pagamentos, movimentos, faturas, Dashboard, indicadores por
natureza, totais por categoria, sugestoes da importacao e as excecoes que nao podem mudar. O relatorio (com dados
financeiros individuais) vai SO para a pasta privada indicada, fora do repositorio. Nada e impresso alem do resumo.
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'scripts'))

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402

import backup_banco as B  # noqa: E402
import backup_rotina as R  # noqa: E402
import reorganizar_categorias as P  # noqa: E402
from tests.supabase_local import ClusterLocal  # noqa: E402

MIGRATION = RAIZ / 'supabase' / 'migrations' / '20261229090000_financeiro_categorias_reorganizacao.sql'
CATALOGO = {'categoria', 'categoria_palavra_chave', 'operacao_catalogo', 'categoria_natureza'}
MESES = ['2026-06', '2026-07', '2026-08', '2026-09', '2026-10', '2026-11', '2026-12', '2027-01', '2027-02']
CORTE = '2026-11-01'
PERFIL = 1


def consulta(cur, sql, params=()):
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def retrato(cur):
    """md5 de cada tabela (public e financeiro) sem as colunas que apontam a categoria e sem o proprio catalogo."""
    fks = {}
    for r in consulta(cur, "select t.relname tabela, a.attname coluna from pg_constraint k join pg_class t on t.oid = k.conrelid "
                           "join pg_attribute a on a.attrelid = k.conrelid and a.attnum = k.conkey[1] "
                           "where k.contype = 'f' and k.confrelid = 'public.categoria'::regclass"):
        fks.setdefault(r['tabela'], []).append(r['coluna'])
    saida = {}
    for t in consulta(cur, "select n.nspname esquema, c.relname tabela from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                           "where c.relkind = 'r' and n.nspname in ('public', 'financeiro', 'auth') order by 1, 2"):
        if t['tabela'] in CATALOGO:
            continue
        menos = ''.join(f" - '{c}'" for c in fks.get(t['tabela'], []))
        saida[f"{t['esquema']}.{t['tabela']}"] = consulta(
            cur, f"select md5(coalesce(string_agg(x, '|' order by x), '')) h, count(*) n from "
                 f"(select (to_jsonb(t){menos})::text x from {t['esquema']}.\"{t['tabela']}\" t) z")[0]
    return saida


def por_categoria(cur):
    """Base aditiva (contas diretas nao dispensadas + compras de cartao), por categoria, ate o corte e depois dele."""
    return consulta(cur, """
        with base as (
            select i.categoria_id, c.mes_referencia mes, c.valor from public.conta c join public.item_despesa i on i.id = c.item_despesa_id
             where c.is_fatura_cartao is not true and i.tipo <> 'Agregador' and lower(coalesce(c.status_pagamento, '')) not in ('dispensada', 'cancelada', 'anulada')
            union all
            select l.categoria_id, l.mes_fatura, l.valor from public.lancamento_agregado l)
        select coalesce(k.id::text, '-') id, coalesce(k.nome, '(sem categoria)') categoria,
               count(*) filter (where b.mes <= %s) quantidade_ate, coalesce(sum(b.valor) filter (where b.mes <= %s), 0)::float valor_ate,
               count(*) filter (where b.mes > %s) quantidade_depois, coalesce(sum(b.valor) filter (where b.mes > %s), 0)::float valor_depois
          from base b left join public.categoria k on k.id = b.categoria_id group by 1, 2 order by 2""", (CORTE,) * 4)


def medir(conn, gestor):
    """Tudo o que o ensaio compara, numa transacao so de leitura (como dono e, para as funcoes, como o titular)."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    m = {'retrato': retrato(cur), 'por_categoria': por_categoria(cur)}
    m['categorias_dos_registros'] = consulta(cur, "select md5(string_agg(x, '|' order by x)) h from (select 'i' || id || ':' || coalesce(categoria_id::text, '-') x "
                                                  "from public.item_despesa union all select 'l' || id || ':' || coalesce(categoria_id::text, '-') from public.lancamento_agregado) z")[0]['h']
    m['catalogo'] = consulta(cur, "select (select md5(string_agg((to_jsonb(c) - 'criado_em')::text, '|' order by c.id)) from public.categoria c) categorias, "
                                  "(select md5(string_agg((to_jsonb(p) - 'updated_at')::text, '|' order by p.id)) from public.categoria_palavra_chave p) palavras, "
                                  "(select count(*) from public.categoria) n_categorias, (select count(*) from public.categoria_palavra_chave where ativo) palavras_ativas, "
                                  "(select count(*) from financeiro.categoria_natureza) naturezas")[0]
    m['saldos'] = consulta(cur, 'select id, nome, saldo_atual::float saldo from public.conta_bancaria order by id')
    m['totais'] = consulta(cur, """select (select count(*) from public.conta) contas, (select sum(valor)::float from public.conta) valor_contas,
        (select count(*) from public.conta where status_pagamento = 'Pago') contas_pagas,
        (select count(*) from public.lancamento_agregado) compras, (select sum(valor)::float from public.lancamento_agregado) valor_compras,
        (select count(*) from public.movimento_financeiro) movimentos, (select sum(valor)::float from public.movimento_financeiro) valor_movimentos,
        (select count(*) from public.conta where is_fatura_cartao) faturas, (select sum(valor)::float from public.conta where is_fatura_cartao) valor_faturas,
        (select count(*) from public.item_despesa where recorrente) recorrencias, (select count(*) from financeiro.recorrencia_ocorrencia) ocorrencias,
        (select count(*) from public.contrato_consorcio) consorcios, (select count(*) from public.financiamento) financiamentos,
        (select count(*) from financeiro.pagamento_fatura) pagamentos_fatura, (select count(*) from public.receita_realizada) receitas""")[0]
    m['intocados'] = {
        'compras_718_719': consulta(cur, 'select to_jsonb(l) j from public.lancamento_agregado l where id = any(%s) order by id', (list(P.INTOCADAS),)),
        'faturas_dos_ajustes': consulta(cur, "select to_jsonb(c) j from public.conta c where c.is_fatura_cartao and exists (select 1 from public.lancamento_agregado l "
                                             "where l.id = any(%s) and l.cartao_id = c.item_despesa_id and date_trunc('month', l.mes_fatura) = date_trunc('month', coalesce(c.cartao_competencia, c.mes_referencia))) order by c.id",
                                        (list(P.INTOCADAS),)),
        'diferenca_das_faturas': consulta(cur, """select l.id, round((select sum(x.valor) from public.lancamento_agregado x where x.cartao_id = l.cartao_id and x.mes_fatura = l.mes_fatura)
                   - (select sum(coalesce(nullif(c.valor_executado, 0), c.valor)) from public.conta c where c.is_fatura_cartao and c.item_despesa_id = l.cartao_id
                       and date_trunc('month', coalesce(c.cartao_competencia, c.mes_referencia)) = date_trunc('month', l.mes_fatura)), 2)::float sobra
              from public.lancamento_agregado l where l.id = any(%s) order by l.id""", (list(P.INTOCADAS),)),
        'consorcios_inativos': consulta(cur, "select md5(string_agg(to_jsonb(i)::text, '|' order by i.id)) h, count(*) n from public.item_despesa i where i.tipo = 'Consorcio' "
                                             "and not exists (select 1 from public.contrato_consorcio c where c.id = any(%s) and financeiro.posicao_parcela_consorcio(i.nome, array[c.nome]) is not null)",
                                        (list(P.CONSORCIOS),))[0],
        'contratos_de_consorcio': consulta(cur, "select md5(string_agg(to_jsonb(c)::text, '|' order by c.id)) h from public.contrato_consorcio c")[0]['h'],
        'emprestimo': consulta(cur, "select to_jsonb(i) j from public.item_despesa i where i.categoria_id = %s and lower(i.nome) like 'empr%%' order by id", (P.OUTROS,)),
        'servicos_domesticos': consulta(cur, "select to_jsonb(c) - 'criado_em' c, (select jsonb_agg(p.palavra order by p.id) from public.categoria_palavra_chave p "
                                             "where p.categoria_id = c.id and p.ativo) palavras from public.categoria c where c.id = %s", (P.DOMESTICOS,)),
        'sistemicas': consulta(cur, "select md5(string_agg((to_jsonb(c) - 'criado_em')::text, '|' order by c.id)) h, count(*) n from public.categoria c where c.sistemica")[0],
        'categoria_ajustes_de_saldo': consulta(cur, "select count(*) n from public.categoria where lower(nome) like 'ajuste%%de saldo%%'")[0]['n'],
    }
    descricoes = consulta(cur, "select distinct lower(coalesce(descricao_original_normalizada, descricao)) d from public.lancamento_agregado "
                               "where coalesce(descricao_original_normalizada, descricao) is not null order by 1")
    m['sugestoes'] = {r['d']: consulta(cur, 'select financeiro.sugestao_categoria_importacao(%s, %s, %s, null) s', (PERFIL, r['d'], r['d']))[0]['s'] for r in descricoes}
    cur.execute('savepoint titular')
    cur.execute('set local role authenticated')
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({'sub': gestor, 'role': 'authenticated'}),))
    m['dashboard'] = {mes: consulta(cur, 'select financeiro.dashboard_resumo_tela(%s, %s) j', (PERFIL, mes))[0]['j'] for mes in MESES}
    m['indicadores'] = {mes: consulta(cur, 'select financeiro.indicadores_gerenciais(%s, %s) j', (PERFIL, mes))[0]['j'] for mes in MESES}
    m['poupanca'] = consulta(cur, 'select financeiro.poupanca_programada_tela(%s) j', (PERFIL,))[0]['j']
    m['naturezas'] = consulta(cur, 'select financeiro.naturezas_das_categorias() j')[0]['j']
    cur.execute('rollback to savepoint titular')
    conn.rollback()
    return m


def diferencas(a, b):
    return sorted(t for t in set(a) | set(b) if a.get(t) != b.get(t))


def ensaiar(saida, backup_id=None):
    cfg = R.configuracao()
    ficha = R._escolher(cfg, backup_id)
    pasta = R._pasta_temporaria(cfg, 'ensaio-categorias')
    rel = {'data_hora': dt.datetime.now().isoformat(timespec='seconds'), 'backup_id': ficha['backup_id'], 'verificacoes': [], 'falhas': []}

    def conferir(nome, ok, detalhe=''):
        rel['verificacoes'].append({'verificacao': nome, 'resultado': 'ok' if ok else 'FALHA', 'detalhe': detalhe})
        if not ok:
            rel['falhas'].append(nome)

    anteriores = {k: os.environ.get(k) for k in ('CF_BACKUP_ROTINA_ENSAIO', 'CF_PG_BIN_BACKUP')}
    try:
        caminho, _ = R._extrair(cfg, ficha, pasta / 'bk')
        os.environ['CF_PG_BIN_BACKUP'] = cfg['pg_bin']
        with ClusterLocal(cfg['pg_bin'], pasta / 'pg') as destino:
            dsn = destino.dsn()
            if psycopg2.extensions.parse_dsn(dsn).get('host') != '127.0.0.1' or B._destino_supabase(dsn):
                raise SystemExit('o destino do ensaio nao e um banco local descartavel')
            destino.aplicar_shim()
            conn = psycopg2.connect(dsn)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute('drop table auth.users')
                cur.execute("do $$ begin if not exists (select 1 from pg_roles where rolname = 'supabase_admin') then create role supabase_admin; end if; end $$")
            conn.close()
            os.environ['CF_BACKUP_ROTINA_ENSAIO'] = dsn
            restaurado = B.restaurar(argparse.Namespace(manifesto=str(caminho), dsn_env='CF_BACKUP_ROTINA_ENSAIO', confirmar_projeto=None))
            rel['restauracao'] = restaurado.get('homologacao')
            conferir('copia restaurada identica ao backup', str(rel['restauracao']).startswith('HOMOLOGADO'), str(rel['restauracao'])[:60])

            conn = psycopg2.connect(dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            rel['migrations_antes'] = consulta(cur, 'select count(*) n from supabase_migrations.schema_migrations')[0]['n']
            sem_migration = retrato(cur)
            cur.execute(MIGRATION.read_text(encoding='utf-8'))
            conn.commit()
            com_migration = retrato(cur)
            conferir('a migration nao altera nenhum dado', diferencas(sem_migration, com_migration) == [], str(diferencas(sem_migration, com_migration)))
            gestor = consulta(cur, 'select user_id::text u from financeiro.gestor_catalogo')[0]['u']
            conn.rollback()

            antes = medir(conn, gestor)
            conferir('antes: sugestoes iguais as de hoje (natureza ainda nao definida)', True, f"{len(antes['sugestoes'])} descricoes")

            # --- previa e execucao (uma transacao)
            estado = P.estado(cur)
            conn.rollback()
            rel['impressao'] = estado['impressao']
            rel['resumo_da_previa'] = estado['resumo']
            estado2 = P.estado(cur)
            conferir('previa repetida da a mesma impressao', estado2['impressao'] == estado['impressao'])
            P.como_gestor(cur)
            feito = P.executar(cur, estado2)
            conn.commit()
            rel['feito'] = {k: v for k, v in feito.items() if k != 'incorporacao'}
            depois = medir(conn, gestor)

            # --- o que mudou e o que nao podia mudar
            conferir('nenhuma tabela mudou fora a coluna da categoria e o catalogo', diferencas(antes['retrato'], depois['retrato']) == [],
                     str(diferencas(antes['retrato'], depois['retrato'])))
            conferir('saldos bancarios identicos', antes['saldos'] == depois['saldos'])
            conferir('contas, valores, pagamentos, compras, faturas, movimentos, recorrencias, consorcios e financiamentos identicos', antes['totais'] == depois['totais'])
            for chave, rotulo in (('compras_718_719', 'compras 718 e 719 identicas (categoria Outros, valores e faturas)'), ('faturas_dos_ajustes', 'faturas dos ajustes identicas'),
                                  ('diferenca_das_faturas', 'diferenca das faturas (R$ 653,07) inalterada'), ('consorcios_inativos', 'consorcios inativos intactos'),
                                  ('contratos_de_consorcio', 'contratos de consorcio identicos'), ('emprestimo', 'emprestimo em Outros intacto'),
                                  ('servicos_domesticos', 'Servicos domesticos (93) independente, com as mesmas palavras-chave'), ('sistemicas', 'categorias sistemicas preservadas')):
                conferir(rotulo, antes['intocados'][chave] == depois['intocados'][chave])
            sobra = round(sum(x['sobra'] for x in depois['intocados']['diferenca_das_faturas']), 2)
            conferir('diferenca total das duas faturas = 653,07', sobra == 653.07, str(sobra))
            conferir('nao existe categoria Ajustes de Saldo', depois['intocados']['categoria_ajustes_de_saldo'] == 0)
            conferir('Dashboard identico em todos os meses conferidos', antes['dashboard'] == depois['dashboard'])
            conferir('quatro categorias criadas e uma incorporada (36 -> 39)', (antes['catalogo']['n_categorias'], depois['catalogo']['n_categorias']) == (36, 39),
                     f"{antes['catalogo']['n_categorias']} -> {depois['catalogo']['n_categorias']}")
            cats = {r['id']: r for r in consulta(cur, 'select id::text id, nome from public.categoria')}
            conn.rollback()
            conferir('Servicos gerais (95) incorporada', str(P.GERAIS) not in cats and str(P.MANUTENCAO) in cats)
            esperado = {**{i: (para if isinstance(para, int) else feito['categorias'][para]) for i, (_, para, _) in P.ITENS.items()}}
            atual = {r['id']: r['categoria_id'] for r in consulta(cur, 'select id, categoria_id from public.item_despesa where id = any(%s)', (list(esperado),))}
            conferir('itens reclassificados no destino aprovado', atual == esperado)
            parcelas = [p['id'] for c in P.CONSORCIOS for p in estado['parcelas'][c]]
            conferir('20 parcelas dos consorcios 18 e 19 em Poupanca Programada',
                     consulta(cur, 'select count(*) n from public.item_despesa where id = any(%s) and categoria_id = %s', (parcelas, feito['categorias']['poupanca']))[0]['n'] == 20)
            compras = {r['id']: r['categoria_id'] for r in consulta(cur, 'select id, categoria_id from public.lancamento_agregado where id = any(%s)', (list(P.COMPRAS),))}
            conferir('compras 616, 615 e 614 no destino aprovado', compras == {k: v[0] for k, v in P.COMPRAS.items()})
            conn.rollback()
            # totais por categoria: a soma geral nao muda
            soma = lambda m: (sum(r['quantidade_ate'] + r['quantidade_depois'] for r in m), round(sum(r['valor_ate'] + r['valor_depois'] for r in m), 2))  # noqa: E731
            conferir('total geral por categoria identico (so muda a distribuicao)', soma(antes['por_categoria']) == soma(depois['por_categoria']), str(soma(depois['por_categoria'])))
            # indicadores: o fluxo total de cada mes nao muda; aportes aparecem a parte
            fluxo = lambda m: {mes: m['indicadores'][mes]['fluxo_total'] for mes in MESES}  # noqa: E731
            conferir('fluxo total de cada mes identico antes e depois (nenhuma saida some)', fluxo(antes) == fluxo(depois))
            conferir('fluxo total = despesas previstas do Dashboard, mes a mes',
                     all(float(depois['indicadores'][mes]['fluxo_total']) == float(depois['dashboard'][mes]['fluxo_caixa']['resumo']['despesas_previstas']) for mes in MESES))
            conferir('partes por natureza somam o fluxo (sem dupla contagem)',
                     all(round(sum(float(depois['indicadores'][mes][k]) for k in ('consumo', 'aportes', 'ajustes_tecnicos', 'transferencias_internas', 'nao_definido')), 2)
                         == round(float(depois['indicadores'][mes]['fluxo_total']), 2) for mes in MESES))
            conferir('antes: nenhum aporte nem ajuste tecnico', all(float(antes['indicadores'][mes]['aportes']) == 0 and float(antes['indicadores'][mes]['ajustes_tecnicos']) == 0 for mes in MESES))
            conferir('depois: nenhum ajuste tecnico (718 e 719 seguem em Outros)', all(float(depois['indicadores'][mes]['ajustes_tecnicos']) == 0 for mes in MESES))
            conferir('poupanca programada: so os contratos 18 e 19', sorted(x['contrato_id'] for x in depois['poupanca']) == list(P.CONSORCIOS), str(len(depois['poupanca'])))
            # sugestoes da importacao: so muda o que vinha de Outros pelo historico ou pelas palavras retiradas
            mudou = {d: (antes['sugestoes'][d], depois['sugestoes'][d]) for d in antes['sugestoes'] if antes['sugestoes'][d] != depois['sugestoes'][d]}
            rel['sugestoes'] = {'descricoes': len(antes['sugestoes']), 'mudaram': len(mudou),
                                'antes_por_origem': contar(antes['sugestoes']), 'depois_por_origem': contar(depois['sugestoes']),
                                'outros_com_confianca_alta_antes': sum(1 for s in antes['sugestoes'].values() if s['categoria_id'] == P.OUTROS and s['confianca'] == 'alta'),
                                'outros_com_confianca_alta_depois': sum(1 for s in depois['sugestoes'].values() if s['categoria_id'] == P.OUTROS and s['confianca'] == 'alta'),
                                'detalhe': [{'descricao': d, 'antes': resumir(a, cats), 'depois': resumir(b, cats)} for d, (a, b) in sorted(mudou.items())]}
            conferir('importacao: Outros deixa de ser sugerido com confianca alta', rel['sugestoes']['outros_com_confianca_alta_depois'] == 0,
                     f"{rel['sugestoes']['outros_com_confianca_alta_antes']} -> 0")
            conferir('importacao: nenhuma compra antiga mudou por causa das sugestoes', antes['retrato']['public.lancamento_agregado'] == depois['retrato']['public.lancamento_agregado'])

            # --- regenerar as parcelas de um consorcio mantem a categoria (transacao desfeita)
            P.como_gestor(cur)
            cur.execute("select financeiro.regenerar_parcelas_consorcio(%s, %s, '{}'::jsonb)", (PERFIL, P.CONSORCIOS[0]))
            cur.execute('reset role')
            conferir('regenerar as parcelas do consorcio mantem Poupanca Programada',
                     consulta(cur, 'select count(*) n from public.item_despesa where id = any(%s) and categoria_id = %s', (parcelas, feito['categorias']['poupanca']))[0]['n'] == 20)
            conn.rollback()

            # --- repetir a execucao nao duplica (estado ja mudou: a previa recusa)
            try:
                P.estado(cur)
                conferir('repetir o roteiro depois de feito e recusado na previa', False)
            except SystemExit as e:
                conferir('repetir o roteiro depois de feito e recusado na previa', True, str(e)[:70])
            conn.rollback()

            # --- reversao
            P.como_gestor(cur)
            rel['reversao'] = P.reverter(cur, feito)
            cur.execute('reset role')
            rel['reversao'].update(P.restaurar_catalogo(cur, feito))
            conn.commit()
            volta = medir(conn, gestor)
            conferir('reversao: banco identico ao inicial (fora a auditoria)', diferencas(antes['retrato'], volta['retrato']) == [], str(diferencas(antes['retrato'], volta['retrato'])))
            conferir('reversao: categoria de cada item e compra como antes', antes['categorias_dos_registros'] == volta['categorias_dos_registros'])
            conferir('reversao: catalogo e palavras-chave como antes', {k: antes['catalogo'][k] for k in ('categorias', 'palavras', 'n_categorias', 'palavras_ativas', 'naturezas')}
                     == {k: volta['catalogo'][k] for k in ('categorias', 'palavras', 'n_categorias', 'palavras_ativas', 'naturezas')}, json.dumps(volta['catalogo'], default=str))
            conferir('reversao: saldos, totais, Dashboard, indicadores e sugestoes como antes',
                     all(antes[k] == volta[k] for k in ('saldos', 'totais', 'dashboard', 'indicadores', 'sugestoes', 'por_categoria', 'intocados')))
            estado3 = P.estado(cur)
            conn.rollback()
            conferir('reversao: a impressao do estado volta a ser a da previa', estado3['impressao'] == estado['impressao'])
            conn.close()

            rel['categorias'] = {'criadas': {k: {'id': v, 'nome': next(n for kk, n, _, _ in P.NOVAS if kk == k), 'natureza': next(nt for kk, _, _, nt in P.NOVAS if kk == k)}
                                             for k, v in feito['categorias'].items()}, 'incorporada': {'origem': P.GERAIS, 'destino': P.MANUTENCAO}}
            rel['por_categoria'] = {'antes': antes['por_categoria'], 'depois': depois['por_categoria']}
            rel['indicadores'] = {'antes': antes['indicadores'], 'depois': depois['indicadores']}
            rel['dashboard_despesas_previstas'] = {mes: depois['dashboard'][mes]['fluxo_caixa']['resumo']['despesas_previstas'] for mes in MESES}
            rel['poupanca_programada'] = depois['poupanca']
            rel['naturezas'] = [n for n in depois['naturezas'] if n['definida']]
            rel['totais'] = depois['totais']
            rel['saldos'] = depois['saldos']
            rel['intocados'] = depois['intocados']
        rel['banco_descartavel'] = 'removido'
    finally:
        for k, v in anteriores.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        R._apagar_pasta_clara(pasta)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / 'ENSAIO_RESULTADO.json').write_text(json.dumps(rel, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    return rel


def contar(sugestoes):
    c = {}
    for s in sugestoes.values():
        c[s['origem']] = c.get(s['origem'], 0) + 1
    return c


def resumir(s, cats):
    return {'categoria': cats.get(str(s['categoria_id']), {}).get('nome') if s['categoria_id'] else None, 'origem': s['origem'], 'confianca': s['confianca']}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--saida', required=True, help='pasta PRIVADA do relatorio (fora do repositorio)')
    ap.add_argument('--backup-id')
    a = ap.parse_args(argv)
    saida = Path(a.saida).resolve()
    if RAIZ in saida.parents or saida == RAIZ:
        raise SystemExit('A pasta do relatorio nao pode ficar dentro do repositorio (dados financeiros individuais).')
    rel = ensaiar(saida, a.backup_id)
    ok = sum(v['resultado'] == 'ok' for v in rel['verificacoes'])
    for v in rel['verificacoes']:
        print(f"{v['resultado']:5} {v['verificacao']}" + (f" — {v['detalhe']}" if v['detalhe'] and v['resultado'] != 'ok' else ''))
    print(f"\n{ok}/{len(rel['verificacoes'])} verificacoes ok | backup {rel['backup_id']} | banco descartavel {rel.get('banco_descartavel', 'NAO removido')}")
    return 1 if rel['falhas'] else 0


if __name__ == '__main__':
    sys.exit(main())
