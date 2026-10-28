#!/usr/bin/env python
"""
FIN-PRE-PRODUCAO-1 (3.1) — carga seletiva dos dados do Flask (PostgreSQL, origem) para o banco do novo aplicativo
(Supabase: tabelas do Flask em public + schema financeiro), sem alterar a origem.

Uso (as conexoes vem SO de variaveis de ambiente; nada e impresso delas):
    python scripts/carga_supabase.py --mapa mapa.json [--origem-env CARGA_ORIGEM_DSN] [--destino-env CARGA_DESTINO_DSN]
                                     [--confirmar] [--relatorio relatorio.json]

Sem --confirmar e um ENSAIO: tudo roda numa transacao do destino que e desfeita no fim (o relatorio mostra o que seria
gravado). Com --confirmar, grava (uma transacao: ou tudo, ou nada).

Mapa (JSON):
    {"titular_user_id": "<uuid do Auth>",
     "perfis": {"1": {"destino_id": 1}, "2": {"destino_id": 2}, "3": "ignorar",
                "5": {"criar": {"nome": "Perfil novo", "tipo": "PESSOAL"}}}}
- destino_id: perfil ja existente no destino, do qual o titular e gestor (pode_gerir) e que nao tem nenhum dado;
- criar: perfil novo (nome unico no destino), com o titular como gestor;
- ignorar: so para perfil da origem sem nenhum registro.

Regras:
- origem so lida (transacao read only) e conferida por hash antes e depois;
- ids novos no destino (o destino pode ja ter dados de outros perfis); chaves estrangeiras traduzidas pelo grafo do
  destino; ciclos (conta <-> parcela, item <-> financiamento) e autorreferencias gravados em duas etapas;
  item_despesa.origem_id traduzido por origem_tipo; qualquer outra referencia sem regra (coluna *_id sem chave
  estrangeira ou JSON preenchido) interrompe a carga;
- tabelas globais por chave natural (reaproveita o que o destino ja tem): categoria (codigo_sistema; sem ele, o nome
  entre as globais), ir_categoria (nome + contexto), indice_tr_mensal (competencia; diferenca de valor vai para o
  relatorio, o destino nao muda) e categoria_palavra_chave (categoria + palavra);
- registros sem perfil continuam sem perfil (como no Flask: pertencem ao perfil chamado "Pessoal"); por isso o
  destino precisa ter o "Pessoal" entre os perfis mapeados;
- cartoes: numero so com os 4 ultimos digitos, sem CVV e sem validade (nunca transportados);
- preferencias: o registro unico do Flask vira as preferencias do titular (interface) e de cada perfil carregado
  (financeiras), sem sobrescrever as que o destino ja tiver;
- nao carregados: alembic_version, usuario (contas de login do Flask; no novo aplicativo o login e o Auth).
Ao fim, cada linha gravada e comparada com a da origem (referencias traduzidas de volta); qualquer diferenca desfaz tudo.
"""
import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import psycopg2
import psycopg2.extras

IGNORADAS = {'alembic_version', 'usuario', 'perfil_financeiro', 'preferencia'}
NATURAIS = {'categoria', 'ir_categoria', 'indice_tr_mensal', 'categoria_palavra_chave'}
# Referencias sem chave estrangeira: (tabela, coluna) -> (coluna do tipo, {tipo: tabela}) ou None (nao e referencia).
POLIMORFICAS = {('item_despesa', 'origem_id'): ('origem_tipo', {'FINANCIAMENTO': 'financiamento', 'CONSORCIO': 'contrato_consorcio',
                                                                'VEICULO': 'veiculo', 'ASSINATURA': 'mobilidade_assinatura'})}
SEM_REFERENCIA = {('lancamento_agregado', 'compra_id')}  # identificador da compra (texto), igual nas parcelas
MASCARA = '••••'
CAMPOS_PREF_USUARIO = ['nome_usuario', 'tema_sistema', 'cor_principal', 'mostrar_icones_coloridos', 'abreviar_valores',
                       'solicitar_confirmacao_exclusao', 'graficos_visiveis', 'insights_inteligentes_ativo',
                       'mostrar_saldo_consolidado', 'mostrar_evolucao_historica', 'modo_inteligente_ativo', 'sugestoes_economia']
CAMPOS_PREF_PERFIL = ['renda_principal', 'mes_inicio_planejamento', 'dia_fechamento_mes', 'ajustar_competencia_automatico',
                      'exibir_aviso_despesa_vencida', 'vincular_pagamento_cartao_auto', 'dia_inicio_fatura', 'dia_corte_fatura',
                      'lancamentos_agrupados', 'orcamento_por_categoria', 'classificacao_automatica', 'correcao_categorias',
                      'parcelas_recorrentes_auto']


class CargaRecusada(Exception):
    """A carga nao pode seguir (nada e gravado)."""


def mascarar(numero):
    digitos = ''.join(c for c in str(numero or '') if c.isdigit())
    return f'{MASCARA} {digitos[-4:]}' if len(digitos) >= 4 else None


def consultar(cur, sql, params=()):
    cur.execute(sql, params or None)
    return cur.fetchall()


def hash_origem(cur, tabelas):
    saida = {}
    for t in tabelas:
        cur.execute(f'select md5(coalesce(string_agg(x::text, \'|\' order by x::text), \'\')) from public."{t}" x')
        saida[t] = cur.fetchone()[0]
    return saida


class Carga:
    def __init__(self, origem, destino, mapa):
        self.o = origem.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        self.d = destino.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        self.mapa = mapa
        self.titular = mapa['titular_user_id']
        self.ids = defaultdict(dict)  # tabela -> {id origem: id destino}
        self.inseridos = defaultdict(set)  # tabela -> ids gravados por esta carga (fora os reaproveitados)
        self.relatorio = {'tabelas': {}, 'perfis': {}, 'reaproveitados': {}, 'tr_divergentes': [], 'preferencias': {},
                          'sensiveis': {}, 'avisos': []}

    # ---- leitura de metadados -------------------------------------------------------------------------------------
    def ler_metadados(self):
        self.tab_origem = {r['table_name'] for r in consultar(self.o, "select table_name from information_schema.tables "
                                                                     "where table_schema='public' and table_type='BASE TABLE'")}
        self.col_origem = defaultdict(dict)
        for r in consultar(self.o, "select table_name, column_name, data_type from information_schema.columns where table_schema='public'"):
            self.col_origem[r['table_name']][r['column_name']] = r['data_type']
        self.col_destino = defaultdict(dict)
        for r in consultar(self.d, "select table_name, column_name, data_type from information_schema.columns where table_schema='public'"):
            self.col_destino[r['table_name']][r['column_name']] = r['data_type']
        self.fks = defaultdict(dict)  # tabela -> {coluna: tabela pai}
        for r in consultar(self.d, """select k.conrelid::regclass::text as filho, a.attname as coluna, k.confrelid::regclass::text as pai
                                        from pg_constraint k join pg_attribute a on a.attrelid = k.conrelid and a.attnum = k.conkey[1]
                                       where k.contype = 'f' and k.connamespace = 'public'::regnamespace and cardinality(k.conkey) = 1
                                         and k.confrelid::regclass::text not like '%.%'"""):
            self.fks[r['filho'].strip('"')][r['coluna']] = r['pai'].strip('"')
        self.com_perfil = {t for t, cols in self.col_destino.items() if 'perfil_financeiro_id' in cols}
        self.linhas = {}
        for t in sorted(self.tab_origem):
            if t in IGNORADAS:
                continue
            self.linhas[t] = consultar(self.o, f'select * from public."{t}" order by 1')
        self.linhas = {t: r for t, r in self.linhas.items() if r}

    # ---- validacoes antes de gravar ---------------------------------------------------------------------------------
    def validar(self):
        sem_destino = sorted(t for t in self.linhas if t not in self.col_destino)
        if sem_destino:
            raise CargaRecusada(f'Tabelas da origem sem correspondente no destino: {sem_destino}')
        for t, linhas in self.linhas.items():
            if 'id' not in self.col_destino[t]:
                raise CargaRecusada(f'Tabela {t} sem coluna id no destino (sem regra de carga)')
            for col in self.col_origem[t]:
                if col not in self.col_destino[t] and any(l[col] is not None for l in linhas):
                    raise CargaRecusada(f'Coluna {t}.{col} preenchida na origem nao existe no destino')
                logica = col.endswith('_id') and col != 'id' and col not in self.fks.get(t, {})
                jsonish = self.col_origem[t][col] in ('json', 'jsonb')
                if (logica or jsonish) and any(l[col] is not None for l in linhas) and (t, col) not in POLIMORFICAS \
                        and (t, col) not in SEM_REFERENCIA and col != 'perfil_financeiro_id':
                    raise CargaRecusada(f'Referencia sem regra de carga: {t}.{col} esta preenchida (nada foi gravado)')
            for col, pai in self.fks.get(t, {}).items():
                if pai not in self.linhas and pai not in IGNORADAS | {'perfil_financeiro'} and any(l.get(col) is not None for l in linhas):
                    raise CargaRecusada(f'{t}.{col} aponta para {pai}, que nao tem dados na origem')
            for (tt, col), (coluna_tipo, alvos) in POLIMORFICAS.items():
                if tt == t:
                    for l in linhas:
                        if l.get(col) is not None and alvos.get(l.get(coluna_tipo)) is None:
                            raise CargaRecusada(f'{t}.{col} com {coluna_tipo} sem regra de carga')
        perfis_origem = {r['id']: r for r in consultar(self.o, 'select * from public.perfil_financeiro order by id')}
        usados = defaultdict(int)
        for t, linhas in self.linhas.items():
            if 'perfil_financeiro_id' in self.col_origem[t]:
                for l in linhas:
                    usados[l['perfil_financeiro_id']] += 1
        self.mapa_perfis = {}
        destinos = []
        for pid, perfil in perfis_origem.items():
            regra = self.mapa['perfis'].get(str(pid))
            if regra is None:
                raise CargaRecusada(f'Perfil {pid} da origem sem regra no mapa')
            if regra == 'ignorar':
                if usados.get(pid):
                    raise CargaRecusada(f'Perfil {pid} da origem tem {usados[pid]} registro(s): nao pode ser ignorado')
                self.relatorio['perfis'][str(pid)] = 'ignorado (sem registros)'
                continue
            if 'destino_id' in regra:
                destino = consultar(self.d, 'select p.id, p.nome from public.perfil_financeiro p join financeiro.perfil_acesso a '
                                            'on a.perfil_financeiro_id = p.id where p.id = %s and a.user_id = %s and a.pode_gerir',
                                    (regra['destino_id'], self.titular))
                if not destino:
                    raise CargaRecusada(f'Perfil de destino {regra["destino_id"]} inexistente ou sem o titular como gestor')
                destinos.append((pid, destino[0]['id'], destino[0]['nome'], perfil))
            elif 'criar' in regra:
                nome = regra['criar']['nome']
                if consultar(self.d, 'select 1 from public.perfil_financeiro where nome = %s', (nome,)):
                    raise CargaRecusada(f'Ja existe perfil com o nome "{nome}" no destino')
                destinos.append((pid, None, nome, {**perfil, **regra['criar']}))
            else:
                raise CargaRecusada(f'Regra invalida para o perfil {pid}')
        for pid, did, nome, _perfil in destinos:
            if did is None:
                continue
            for t in sorted(self.com_perfil):
                if consultar(self.d, f'select 1 from public."{t}" where perfil_financeiro_id = %s limit 1', (did,)):
                    raise CargaRecusada(f'O perfil de destino "{nome}" ja tem dados ({t}): carga recusada (sem duplicar)')
        if usados.get(None) and not any(nome == 'Pessoal' for _p, _d, nome, _x in destinos):
            raise CargaRecusada('Ha registros sem perfil (do "Pessoal" no Flask) e nenhum perfil de destino se chama "Pessoal"')
        self.destinos = destinos

    # ---- gravacao ---------------------------------------------------------------------------------------------------
    def criar_perfis(self):
        for pid, did, nome, perfil in self.destinos:
            if did is None:
                self.d.execute("insert into public.perfil_financeiro (nome, tipo, documento, avatar, logo_url, cor, ativo, padrao, "
                               "created_at, updated_at) values (%s, %s, %s, %s, %s, %s, %s, false, %s, %s) returning id",
                               (nome, perfil['tipo'], perfil.get('documento'), perfil.get('avatar'), perfil.get('logo_url'),
                                perfil.get('cor') or '#2563eb', perfil.get('ativo', True), perfil.get('created_at'), perfil.get('updated_at')))
                did = self.d.fetchone()['id']
                self.d.execute("insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) "
                               "values (%s, %s, 'TITULAR', true)", (self.titular, did))
            self.mapa_perfis[pid] = did
            self.relatorio['perfis'][str(pid)] = {'destino_id': did, 'nome_destino': nome}

    def ordem(self):
        pendentes = set(self.linhas)
        ordem, adiadas = [], set()
        while pendentes:
            prontas = sorted(t for t in pendentes if all(p == t or p not in pendentes for p in self.fks.get(t, {}).values()))
            if not prontas:  # ciclo: a tabela com menos dependencias pendentes vai antes; essas colunas ficam para depois
                t = min(sorted(pendentes), key=lambda x: sum(p in pendentes and p != x for p in self.fks.get(x, {}).values()))
                adiadas |= {(t, c) for c, p in self.fks.get(t, {}).items() if p in pendentes and p != t}
                prontas = [t]
            for t in prontas:
                adiadas |= {(t, c) for c, p in self.fks.get(t, {}).items() if p == t}
                ordem.append(t)
                pendentes.discard(t)
        return ordem, adiadas

    def transformar(self, t, linha):
        """Linha da origem como deve ficar no destino, antes da traducao de referencias (cartao sem dado sensivel)."""
        nova = {c: v for c, v in linha.items() if c in self.col_destino[t]}
        if t == 'config_agregador':
            nova['numero_cartao'] = mascarar(nova.get('numero_cartao'))
            nova['codigo_seguranca'] = None
            nova['data_validade'] = None
        return nova

    def chave_natural(self, t, linha):
        if t == 'categoria':
            if linha.get('codigo_sistema'):
                return 'select id from public.categoria where codigo_sistema = %s order by id limit 1', (linha['codigo_sistema'],)
            if linha.get('perfil_financeiro_id') is None:
                return ('select id from public.categoria where perfil_financeiro_id is null and lower(nome) = lower(%s) '
                        'order by id limit 1', (linha['nome'],))
            return None
        if t == 'ir_categoria':
            return 'select id from public.ir_categoria where nome = %s and tipo_contexto is not distinct from %s order by id limit 1', \
                (linha['nome'], linha.get('tipo_contexto'))
        if t == 'indice_tr_mensal':
            return 'select id, valor_decimal from public.indice_tr_mensal where competencia = %s', (linha['competencia'],)
        if t == 'categoria_palavra_chave':
            return ('select id from public.categoria_palavra_chave where categoria_id = %s and lower(palavra) = lower(%s) '
                    'order by id limit 1', (self.ids['categoria'].get(linha['categoria_id']), linha['palavra']))
        return None

    def gravar(self):
        ordem, self.adiadas = self.ordem()
        self.relatorio['ordem'] = ordem
        self.relatorio['referencias_em_duas_etapas'] = sorted(f'{t}.{c}' for t, c in self.adiadas)
        for t in ordem:
            inseridos = reaproveitados = 0
            for linha in self.linhas[t]:
                nova = self.transformar(t, linha)
                if t in NATURAIS:
                    natural = self.chave_natural(t, nova)
                    if natural:
                        achado = consultar(self.d, *natural)
                        if achado:
                            self.ids[t][linha['id']] = achado[0]['id']
                            reaproveitados += 1
                            if t == 'indice_tr_mensal' and achado[0]['valor_decimal'] != linha['valor_decimal']:
                                self.relatorio['tr_divergentes'].append(linha['competencia'])
                            continue
                valores = {}
                for c, v in nova.items():
                    if c == 'id':
                        continue
                    if c == 'perfil_financeiro_id' and t in self.com_perfil:
                        valores[c] = None if v is None else self.mapa_perfis[v]
                    elif c in self.fks.get(t, {}) and self.fks[t][c] == 'perfil_financeiro':
                        valores[c] = None if v is None else self.mapa_perfis[v]
                    elif (t, c) in self.adiadas:
                        valores[c] = None
                    elif c in self.fks.get(t, {}) and v is not None:
                        valores[c] = self.ids[self.fks[t][c]][v]
                    else:
                        valores[c] = psycopg2.extras.Json(v) if self.col_destino[t][c] in ('json', 'jsonb') and v is not None else v
                colunas = ', '.join(f'"{c}"' for c in valores)
                self.d.execute(f'insert into public."{t}" ({colunas}) values ({", ".join(["%s"] * len(valores))}) returning id',
                               list(valores.values()))
                self.ids[t][linha['id']] = self.d.fetchone()['id']
                self.inseridos[t].add(self.ids[t][linha['id']])
                inseridos += 1
            self.relatorio['tabelas'][t] = {'origem': len(self.linhas[t]), 'inseridos': inseridos, 'reaproveitados': reaproveitados}
        # Segunda etapa: ciclos, autorreferencias e referencias por tipo.
        for t, c in sorted(self.adiadas):
            for linha in self.linhas[t]:
                if linha.get(c) is not None and linha['id'] in self.ids[t]:
                    self.d.execute(f'update public."{t}" set "{c}" = %s where id = %s',
                                   (self.ids[self.fks[t][c]][linha[c]], self.ids[t][linha['id']]))
        for (t, c), (coluna_tipo, alvos) in POLIMORFICAS.items():
            for linha in self.linhas.get(t, []):
                if linha.get(c) is not None:
                    alvo = alvos[linha[coluna_tipo]]
                    self.d.execute(f'update public."{t}" set "{c}" = %s where id = %s', (self.ids[alvo][linha[c]], self.ids[t][linha['id']]))

    def preferencias(self):
        if not consultar(self.d, "select 1 from information_schema.tables where table_schema='financeiro' and table_name='preferencia_usuario'"):
            self.relatorio['avisos'].append('Destino sem as tabelas de preferencias (migration 20261201090000): nao copiadas')
            return
        if 'preferencia' not in self.tab_origem:
            return
        origem = consultar(self.o, 'select * from public.preferencia order by id limit 1')
        if not origem:
            return
        p = origem[0]
        usuario = {c: p.get(c) for c in CAMPOS_PREF_USUARIO if p.get(c) is not None}
        if usuario.get('cor_principal') and not __import__('re').fullmatch(r'#[0-9A-Fa-f]{6}', str(usuario['cor_principal'])):
            usuario.pop('cor_principal')
        if usuario.get('tema_sistema') not in (None, 'claro', 'escuro', 'auto'):
            usuario.pop('tema_sistema')
        self.d.execute(f'insert into financeiro.preferencia_usuario (user_id, {", ".join(usuario)}) values '
                       f'(%s{", %s" * len(usuario)}) on conflict (user_id) do nothing', [self.titular, *usuario.values()])
        self.relatorio['preferencias']['usuario'] = 'copiada' if self.d.rowcount else 'mantida (o destino ja tinha)'
        perfil = {c: p.get(c) for c in CAMPOS_PREF_PERFIL if p.get(c) is not None}
        for pid, did in self.mapa_perfis.items():
            self.d.execute(f'insert into financeiro.preferencia_perfil (perfil_financeiro_id, {", ".join(perfil)}) values '
                           f'(%s{", %s" * len(perfil)}) on conflict (perfil_financeiro_id) do nothing', [did, *perfil.values()])
            self.relatorio['preferencias'][str(pid)] = 'copiada' if self.d.rowcount else 'mantida (o destino ja tinha)'

    # ---- conferencia ------------------------------------------------------------------------------------------------
    def conferir(self):
        inversos = {t: {v: k for k, v in m.items()} for t, m in self.ids.items()}
        perfis_inv = {v: k for k, v in self.mapa_perfis.items()}
        diferencas = []
        for t, linhas in self.linhas.items():
            novos = {lid: did for lid, did in self.ids[t].items()}
            gravados = {r['id']: r for r in consultar(self.d, f'select * from public."{t}" where id = any(%s)', (list(novos.values()),))}
            for linha in linhas:
                esperado = self.transformar(t, linha)
                g = gravados.get(novos.get(linha['id']))
                if g is None:
                    diferencas.append(f'{t}: linha da origem sem correspondente')
                    continue
                if novos[linha['id']] not in self.inseridos[t]:
                    continue  # linha do destino reaproveitada pela chave natural
                for c, v in esperado.items():
                    if c == 'id':
                        continue
                    gv = g.get(c)
                    if c == 'perfil_financeiro_id' or self.fks.get(t, {}).get(c) == 'perfil_financeiro':
                        gv = None if gv is None else perfis_inv.get(gv)
                    elif c in self.fks.get(t, {}) and gv is not None:
                        gv = inversos[self.fks[t][c]].get(gv)
                    elif (t, c) in POLIMORFICAS and gv is not None:
                        gv = inversos[POLIMORFICAS[(t, c)][1][linha[POLIMORFICAS[(t, c)][0]]]].get(gv)
                    if gv != v:
                        diferencas.append(f'{t}.{c}')
        if diferencas:
            raise CargaRecusada(f'Conferencia com a origem falhou: {sorted(set(diferencas))[:20]}')
        if 'config_agregador' in self.linhas:
            novos = list(self.ids['config_agregador'].values())
            sensiveis = consultar(self.d, "select count(*) filter (where codigo_seguranca is not null) cvv, "
                                          "count(*) filter (where data_validade is not null) validade, "
                                          "count(*) filter (where length(regexp_replace(coalesce(numero_cartao, ''), '\\D', '', 'g')) > 4) numero "
                                          "from public.config_agregador where id = any(%s)", (novos,))[0]
            if any(sensiveis.values()):
                raise CargaRecusada('Dado sensivel de cartao no destino')
            self.relatorio['sensiveis'] = {'cartoes': len(novos), 'cvv': 0, 'validade': 0, 'numero_completo': 0}
        self.relatorio['conferencia'] = 'OK: todas as linhas gravadas iguais as da origem (referencias traduzidas)'


def executar(origem_dsn, destino_dsn, mapa, confirmar=False):
    origem = psycopg2.connect(origem_dsn)
    origem.set_session(readonly=True, autocommit=False)
    destino = psycopg2.connect(destino_dsn)
    try:
        carga = Carga(origem, destino, mapa)
        carga.ler_metadados()
        antes = hash_origem(origem.cursor(), sorted(carga.tab_origem))
        carga.validar()
        carga.criar_perfis()
        carga.gravar()
        carga.preferencias()
        carga.conferir()
        depois = hash_origem(origem.cursor(), sorted(carga.tab_origem))
        if antes != depois:
            raise CargaRecusada('A origem mudou durante a carga')
        carga.relatorio['origem_inalterada'] = True
        carga.relatorio['hash_origem'] = hashlib.sha256(json.dumps(antes, sort_keys=True).encode()).hexdigest()
        if confirmar:
            destino.commit()
            carga.relatorio['resultado'] = 'GRAVADO'
        else:
            destino.rollback()
            carga.relatorio['resultado'] = 'ENSAIO (nada gravado)'
        return carga.relatorio
    except Exception:
        destino.rollback()
        raise
    finally:
        origem.rollback()
        origem.close()
        destino.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--mapa', required=True)
    parser.add_argument('--origem-env', default='CARGA_ORIGEM_DSN')
    parser.add_argument('--destino-env', default='CARGA_DESTINO_DSN')
    parser.add_argument('--confirmar', action='store_true')
    parser.add_argument('--relatorio')
    args = parser.parse_args()
    origem, destino = os.environ.get(args.origem_env), os.environ.get(args.destino_env)
    if not origem or not destino:
        print(f'CARGA_RECUSADA: defina {args.origem_env} e {args.destino_env}', file=sys.stderr)
        return 2
    try:
        relatorio = executar(origem, destino, json.loads(Path(args.mapa).read_text(encoding='utf-8')), args.confirmar)
    except CargaRecusada as erro:
        print(f'CARGA_RECUSADA: {erro}', file=sys.stderr)
        return 2
    texto = json.dumps(relatorio, ensure_ascii=False, indent=1, default=str)
    if args.relatorio:
        Path(args.relatorio).write_text(texto, encoding='utf-8')
    print(texto)
    return 0


if __name__ == '__main__':
    sys.exit(main())
