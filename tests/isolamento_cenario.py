"""FIN-MULTIUSUARIO-SEGURANCA-01 — cenario e sondas da suite permanente de isolamento entre usuarios.

Banco PostgreSQL LOCAL descartavel, dados ficticios. Dois usuarios independentes, cada um com os perfis "Pessoal" e
"Empresa" (nomes iguais, donos diferentes) e um registro MARCADO em cada tabela que guarda dado de perfil. As sondas
chamam as funcoes expostas como um usuario, apontando perfis e registros do outro, e conferem:
  - a recusa (ou o "nao encontrado"), e
  - que NENHUMA resposta traz a marca do outro usuario.
Uma chamada que para na validacao dos dados nao prova nada: a funcao fica registrada como "sem cobertura efetiva".
"""
import json
import re
import uuid

import psycopg2
import psycopg2.extras

from tests.supabase_local import PERFIS, USUARIO_A, USUARIO_B, claims_usuario

MARCA = {'A': 'SEGREDO-DO-USUARIO-A-7f3a', 'B': 'SEGREDO-DO-USUARIO-B-9c1e'}
VALOR = {'A': '97531.24', 'B': '86420.13'}
USUARIOS = {'A': USUARIO_A, 'B': USUARIO_B}
BASE_ID = {'A': 7100000, 'B': 7200000}  # ids proprios e distantes: o id de um nunca existe por acaso nos dados do outro
TEXTO_MARCAVEL = ('nome', 'descricao', 'observacoes', 'observacao', 'titulo', 'estabelecimento', 'prestador_nome', 'tomador_nome', 'apelido',
                  'nome_arquivo', 'motivo', 'instituicao', 'modelo', 'placa', 'credor', 'administradora', 'palavra')
PADRAO = {'integer': 1, 'bigint': 1, 'smallint': 1, 'numeric': 1, 'double precision': 1, 'real': 1, 'boolean': False, 'date': '2027-03-10',
          'timestamp without time zone': '2027-03-10 12:00:00', 'timestamp with time zone': '2027-03-10 12:00:00+00', 'uuid': None,
          'jsonb': '{}', 'json': '{}', 'bytea': b'conteudo ficticio', 'text': 'x', 'character varying': 'x', 'character': 'x'}
# Valores exigidos por regras de cada tabela (CHECK, formato, coerencia): so o necessario para o registro existir.
AJUSTES = {
    ('public.item_despesa', 'tipo'): 'Simples', ('public.item_despesa', 'ativo'): True,
    ('public.conta', 'status_pagamento'): 'Pendente', ('public.conta', 'is_fatura_cartao'): False,
    ('public.conta_bancaria', 'status'): 'ATIVO',
    ('financeiro.abastecimento', 'combustivel'): 'gasolina', ('financeiro.abastecimento', 'meio_pagamento'): 'pix',
    ('financeiro.abastecimento', 'lancamento_id'): None, ('financeiro.abastecimento', 'conta_id'): None,
    ('financeiro.abastecimento', 'cartao_id'): None, ('financeiro.abastecimento', 'cartao_vinculado_id'): None,
    ('financeiro.abastecimento', 'anulado_em'): None, ('financeiro.abastecimento', 'anulado_por'): None,
    ('financeiro.abastecimento', 'preco_litro'): '5.00', ('financeiro.abastecimento', 'hodometro_km'): 100,
    ('financeiro.credito_fatura', 'natureza'): 'ESTORNO',
    ('financeiro.mobilidade_troca_decisao', 'decisao'): 'MANTER', ('financeiro.mobilidade_troca_decisao', 'natureza'): 'CONTA',
    ('financeiro.pagamento_fatura', 'origem'): 'NOVO_APP', ('financeiro.pagamento_fatura', 'tipo_ajuste'): None,
    ('financeiro.pagamento_fatura', 'justificativa'): None, ('financeiro.pagamento_fatura', 'estornado_em'): None,
    ('financeiro.pagamento_fatura', 'estorno_motivo'): None,
    ('financeiro.ocorrencia_recorrencia_cartao', 'origem'): 'NAO_COBRADA', ('financeiro.ocorrencia_recorrencia_cartao', 'lancamento_absorvido'): None,
    ('financeiro.veiculo_projecao', 'tipo'): 'OUTRO', ('financeiro.veiculo_projecao', 'frequencia'): 'MENSAL',
    ('financeiro.veiculo_projecao', 'data_inicio'): '2027-03-01', ('financeiro.veiculo_projecao', 'data_fim'): None,
    ('financeiro.veiculo_projecao', 'obrigacao'): lambda s: f'PROJ:{s.seq}',
    ('financeiro.veiculo_projecao_historico', 'acao'): 'CRIACAO',
    ('financeiro.cartao_vinculado', 'final'): '1234', ('financeiro.cartao_vinculado', 'tipo'): 'FISICO',
    ('financeiro.cartao_vinculado', 'situacao'): 'ATIVO', ('financeiro.cartao_vinculado', 'substituto_id'): None,
    ('financeiro.cartao_vinculado', 'data_cancelamento'): None,
}
# Semeadas depois do cartao (precisam apontar para ele).
DEPOIS_DO_CARTAO = ('financeiro.cartao_vinculado',)


def conectar(dsn):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return conn


def consulta(conn, sql, p=()):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, p)
        return [dict(r) for r in cur.fetchall()] if cur.description else None


# Tem a coluna de perfil, mas nao guarda dado financeiro do usuario (configuracao, catalogo, auditoria da propria migracao).
SEM_DADO_DE_USUARIO = ('public.categoria', 'financeiro.guarda_sem_perfil', 'financeiro.perfil_acesso', 'financeiro.gerador_recorrencia',
                       'financeiro.gerador_recorrencia_historico', 'financeiro.preferencia_perfil', 'financeiro.regularizacao_perfil')


class Esquema:
    """Colunas, obrigatoriedade e chaves estrangeiras das tabelas de public e financeiro."""

    def __init__(self, conn):
        self.colunas = {}
        for r in consulta(conn, """select c.table_schema || '.' || c.table_name t, c.column_name col, c.data_type tipo, c.is_nullable = 'NO' obrig,
                                          c.column_default padrao, c.character_maximum_length tam, c.is_generated <> 'NEVER' or c.identity_generation is not null gerada
                                     from information_schema.columns c where c.table_schema in ('public', 'financeiro') order by 1, c.ordinal_position"""):
            self.colunas.setdefault(r['t'], []).append(r)
        self.fks = {}
        for r in consulta(conn, """select n.nspname || '.' || t.relname t, a.attname col, fn.nspname || '.' || ft.relname ref, fa.attname ref_col
                                     from pg_constraint k join pg_class t on t.oid = k.conrelid join pg_namespace n on n.oid = t.relnamespace
                                     join pg_class ft on ft.oid = k.confrelid join pg_namespace fn on fn.oid = ft.relnamespace
                                     join pg_attribute a on a.attrelid = k.conrelid and a.attnum = k.conkey[1]
                                     join pg_attribute fa on fa.attrelid = k.confrelid and fa.attnum = k.confkey[1]
                                    where k.contype = 'f' and n.nspname in ('public', 'financeiro') and array_length(k.conkey, 1) = 1"""):
            self.fks[(r['t'], r['col'])] = (r['ref'], r['ref_col'])
        self.pk = {r['t']: r['col'] for r in consulta(conn, """select n.nspname || '.' || t.relname t, a.attname col from pg_index i
                      join pg_class t on t.oid = i.indrelid join pg_namespace n on n.oid = t.relnamespace
                      join pg_attribute a on a.attrelid = t.oid and a.attnum = i.indkey[0]
                     where i.indisprimary and i.indnatts = 1 and n.nspname in ('public', 'financeiro')""")}

    def com_perfil(self):
        return sorted(t for t, cs in self.colunas.items() if any(c['col'] == 'perfil_financeiro_id' for c in cs)
                      and t not in SEM_DADO_DE_USUARIO)


class Semeador:
    """Um registro marcado por tabela, para um dono (A ou B), no perfil dado. Cria antes o que a chave estrangeira exige."""

    def __init__(self, conn, esquema, dono, perfil_id, categoria_id):
        self.conn, self.e, self.dono, self.perfil, self.categoria = conn, esquema, dono, perfil_id, categoria_id
        self.ids, self.falhas, self.seq = {}, {}, BASE_ID[dono] + perfil_id * 1000
        self.fixos, self.extras = {}, {}

    def _valor(self, tabela, c):
        col, tipo = c['col'], c['tipo']
        if (tabela, col) in self.fixos:
            return self.fixos[(tabela, col)]
        if (tabela, col) in AJUSTES:
            v = AJUSTES[(tabela, col)]
            return v(self) if callable(v) else v
        ref = self.e.fks.get((tabela, col))
        if col == 'perfil_financeiro_id':
            return self.perfil
        if ref:
            if ref[0] == 'auth.users':
                return USUARIOS[self.dono]['id']
            if ref[0] == 'public.perfil_financeiro':
                return self.perfil
            if ref[0] == 'public.categoria':
                return self.categoria
            if ref[0] == tabela:
                return None
            alvo = self.registro(ref[0])
            return alvo if (alvo is not None or not c['obrig']) else '__FALTA__'
        if tipo in ('text', 'character varying', 'character') and col in TEXTO_MARCAVEL:
            texto = f'{MARCA[self.dono]} {tabela.split(".")[1]}'
            return texto[:c['tam']] if c['tam'] else texto
        if tipo == 'numeric' and re.search(r'^valor|^saldo|_valor$|^preco|^limite', col):
            return VALOR[self.dono]
        if not c['obrig'] or c['padrao'] is not None or c['gerada']:
            return '__OMITIR__'
        if tipo == 'uuid':
            return str(uuid.uuid4())
        if tipo in ('character varying', 'character', 'text'):
            texto = f'x{self.dono}{self.perfil}'
            return texto[:c['tam']] if c['tam'] else texto
        return PADRAO.get(tipo, 'x')

    def registro(self, tabela):
        if tabela in self.ids:
            return self.ids[tabela]
        if tabela in self.falhas or tabela not in self.e.colunas:
            return None
        self.ids[tabela] = None  # em construcao (ciclos)
        valores, pk = {}, self.e.pk.get(tabela)
        for c in self.e.colunas[tabela]:
            if c['col'] == pk and c['tipo'] in ('integer', 'bigint'):
                self.seq += 1
                valores[c['col']] = self.seq
                continue
            v = self._valor(tabela, c)
            if v == '__FALTA__':
                self.falhas[tabela] = f'depende de {self.e.fks[(tabela, c["col"])][0]}'
                del self.ids[tabela]
                return None
            if v != '__OMITIR__':
                valores[c['col']] = v
        cols = ', '.join(f'"{k}"' for k in valores)
        esq, nome = tabela.split('.')
        try:
            with self.conn.cursor() as cur:
                cur.execute(f'insert into {esq}."{nome}" ({cols}) overriding system value values ({", ".join(["%s"] * len(valores))})' + (f' returning "{pk}"' if pk else ''),
                            [psycopg2.Binary(v) if isinstance(v, bytes) else v for v in valores.values()])
                self.ids[tabela] = cur.fetchone()[0] if pk else True
        except psycopg2.Error as erro:
            self.falhas[tabela] = (erro.diag.message_primary or str(erro))[:160]
            del self.ids[tabela]
            return None
        return self.ids[tabela]

    def clonar(self, tabela, id_de_origem, /, **mudancas):  # posicional: "origem" tambem e nome de coluna
        """Copia um registro ja semeado, trocando alguns campos (ex.: a despesa comum vira cartao)."""
        pk = self.e.pk[tabela]
        self.seq += 1
        cols = [c['col'] for c in self.e.colunas[tabela] if not c['gerada'] or c['col'] == pk]
        expr = [('%s' if c == pk or c in mudancas else f'"{c}"') for c in cols]
        args = [self.seq if c == pk else mudancas[c] for c in cols if c == pk or c in mudancas]
        esq, nome = tabela.split('.')
        with self.conn.cursor() as cur:
            cur.execute(f'insert into {esq}."{nome}" ({", ".join(chr(34) + c + chr(34) for c in cols)}) overriding system value '
                        f'select {", ".join(expr)} from {esq}."{nome}" where "{pk}" = %s', args + [id_de_origem])
        return self.seq

    def tudo(self):
        for tabela in self.e.com_perfil() + ['public.ir_comprovante_arquivo']:
            if tabela not in DEPOIS_DO_CARTAO:
                self.registro(tabela)
        # cartao (item agregador), fatura dele e compra nele: as funcoes de cartao procuram exatamente esses tipos
        item, conta, compra = self.ids.get('public.item_despesa'), self.ids.get('public.conta'), self.ids.get('public.lancamento_agregado')
        if item and conta:
            cartao = self.clonar('public.item_despesa', item, tipo='Agregador', nome=f'{MARCA[self.dono]} cartao')
            with self.conn.cursor() as cur:
                cur.execute('insert into public.config_agregador (item_despesa_id, dia_fechamento, dia_vencimento, limite_credito) values (%s, 5, 12, 1000)', (cartao,))
            fatura = self.clonar('public.conta', conta, item_despesa_id=cartao, is_fatura_cartao=True, cartao_competencia='2027-03-01',
                                 financiamento_parcela_id=None)
            self.extras = {'cartao': cartao, 'fatura': fatura}
            if compra:
                self.extras['compra_no_cartao'] = self.clonar('public.lancamento_agregado', compra, cartao_id=cartao)
            self.fixos[('financeiro.cartao_vinculado', 'contrato_id')] = cartao
            for tabela in DEPOIS_DO_CARTAO:
                self.registro(tabela)
        return self

    def alvos(self):
        """Todos os ids marcados deste dono neste perfil: {rotulo: id}."""
        return {**{t: i for t, i in self.ids.items() if isinstance(i, int) and not isinstance(i, bool)}, **self.extras}


def como(conn, usuario):
    """Dentro de uma transacao ja aberta: passa a agir como o usuario (ou anonimo)."""
    with conn.cursor() as cur:
        if usuario is None:
            cur.execute('set local role anon')
        else:
            cur.execute('set local role authenticated')
            cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims_usuario(usuario)),))


def funcoes_expostas(conn):
    return consulta(conn, """select p.proname nome, p.proargnames nomes, p.pronargs n, p.provolatile = 'v' escreve,
                                    (select array_agg(format_type(t, null) order by o) from unnest(p.proargtypes::oid[]) with ordinality x(t, o)) tipos
                               from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                              where n.nspname = 'financeiro' and p.prokind = 'f' and has_function_privilege('authenticated', p.oid, 'execute') order by 1""")


DADOS = json.dumps({
    'motivo': 'teste de isolamento', 'justificativa': 'teste de isolamento', 'nome': 'teste', 'descricao': 'teste', 'observacoes': 'teste',
    'valor': '1.00', 'valor_pago': '1.00', 'valor_devido': '1.00', 'valor_recebido': '1.00', 'valor_total': '1.00', 'saldo_informado': '1.00',
    'data': '2027-03-10', 'data_pagamento': '2027-03-10', 'data_estorno': '2027-03-11', 'data_recebimento': '2027-03-10', 'data_vencimento': '2027-03-10',
    'data_compra': '2027-03-10', 'data_quitacao': '2027-03-10', 'data_referencia': '2027-03-10', 'data_abastecimento': '2027-03-10',
    'competencia': '2027-03', 'mes': '2027-03', 'mes_fatura': '2027-03-01', 'escopo': 'esta', 'meio': 'pix', 'meio_pagamento': 'pix', 'tipo': 'OUTRO',
    'ativo': True, 'apelido': 'apelido de teste', 'palavra': 'teste', 'limite': '100.00', 'valor_limite': '100.00', 'hodometro_km': 200,
    'combustivel': 'gasolina', 'preco_litro': '5.00', 'km': 1000, 'total_parcelas': 1, 'numero_parcela': 1})
ARG = {'integer': 1, 'bigint': 1, 'text': '2027-03', 'date': '2027-03-01', 'jsonb': DADOS, 'json': DADOS, 'boolean': False, 'numeric': 1,
       'integer[]': '{}', 'text[]': '{}', 'timestamp with time zone': '2027-03-01', 'timestamp without time zone': '2027-03-01'}


def chamar(conn, usuario, f, valores):
    """Chama a funcao como o usuario e desfaz. Devolve (codigo, mensagem, texto do retorno)."""
    nomes, tipos = (f['nomes'] or [])[:f['n']], f['tipos'] or []
    marc = ', '.join(f'{n} => %s::{t}' for n, t in zip(nomes, tipos))
    args = [valores[n] if n in valores else (str(uuid.uuid4()) if t == 'uuid' else ARG.get(t)) for n, t in zip(nomes, tipos)]
    conn.autocommit = False
    try:
        como(conn, usuario)
        with conn.cursor() as cur:
            try:
                cur.execute(f"select to_jsonb(x) from financeiro.{f['nome']}({marc}) x", args)
                return 'OK', '', json.dumps([r[0] for r in cur.fetchall()], default=str, ensure_ascii=False)
            except psycopg2.Error as e:
                return e.pgcode or '?', (e.diag.message_primary or '')[:200], ''
    finally:
        conn.rollback()
        conn.autocommit = True


RECUSA = re.compile(r'nao autorizad|não autorizad|nao encontrad|não encontrad|inexistente|nao pertence|não pertence|restrita ao administrador'
                    r'|nao administra|do perfil$|deste perfil|de outro perfil|nao identifica o lote|não identifica o lote', re.I)


def classificar(codigo, mensagem, retorno):
    """recusada: a funcao negou o acesso; respondeu: executou sem erro; validacao: parou antes, sem provar a recusa."""
    if codigo == 'OK':
        return 'respondeu'
    if codigo == '42501' or RECUSA.search(mensagem or ''):
        return 'recusada'
    return 'validacao'


def vazou(retorno, mensagem, vitima):
    texto = (retorno or '') + ' ' + (mensagem or '')
    return MARCA[vitima] in texto or VALOR[vitima] in texto


def retrato(conn, perfis):
    """md5 de cada tabela com perfil, so as linhas dos perfis dados: nada disto pode mudar numa tentativa indevida."""
    e = Esquema(conn)
    saida = {}
    for t in e.com_perfil():
        esq, nome = t.split('.')
        saida[t] = consulta(conn, f"select md5(coalesce(string_agg(x::text, '|' order by x::text), '')) h, count(*) n from {esq}.\"{nome}\" x "
                                  'where perfil_financeiro_id = any(%s)', (list(perfis),))[0]
    saida['saldos'] = consulta(conn, 'select id, saldo_atual::text s from public.conta_bancaria where perfil_financeiro_id = any(%s) order by id', (list(perfis),))
    return saida


__all__ = ['MARCA', 'VALOR', 'USUARIOS', 'PERFIS', 'Esquema', 'Semeador', 'conectar', 'consulta', 'como', 'funcoes_expostas', 'chamar', 'classificar',
           'vazou', 'retrato', 'AJUSTES']
