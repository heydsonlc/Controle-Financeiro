"""
Testes FIN-PRE-PRODUCAO-1 (3.1) — scripts/carga_supabase.py: carga seletiva do Flask para o banco do novo aplicativo,
entre dois clusters PostgreSQL locais DESCARTAVEIS, com dados FICTICIOS.

Origem: tabelas do Flask com os cenarios ficticios do E2E (perfis, contas, recorrencias, receitas, cartoes, compras,
financiamento com o ciclo conta <-> parcela, TR) e os casos que a carga trata: cartao com numero completo, CVV e
validade; item legado sem perfil; item com origem_tipo/origem_id; preferencias do Flask; categoria do sistema.
Destino: como o projeto atual (outro usuario com dados, TR divergente, categoria do sistema ja existente, perfis
Pessoal e Empresa do titular vazios).

Prova: ensaio sem gravar; carga gravada igual a origem (contagens, referencias, ciclo, origem_id); origem inalterada;
dados do outro usuario intactos; isolamento entre usuarios; nada sensivel de cartao; TR divergente reportada sem mudar o
destino; preferencias copiadas; segunda carga recusada (sem duplicar); recusas quando falta regra (referencia sem
regra, perfil ignorado com dados, registros sem perfil sem "Pessoal" no destino).
"""
import datetime
import importlib.util
import uuid

import pytest

from tests import supabase_local as L
from tests.test_supabase_integracao_1123_1126 import resumo_perfil, resumo_tabelas
from tests.test_supabase_recorrencia import PG_BIN, ROOT, chamar, copiar, sql

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

_spec = importlib.util.spec_from_file_location('carga_supabase', ROOT / 'scripts' / 'carga_supabase.py')
carga = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carga)

TITULAR = {'id': str(uuid.UUID('dddddddd-0000-4000-8000-00000000000d')), 'email': 'titular.carga@teste.local'}
OUTRO = {'id': str(uuid.UUID('eeeeeeee-0000-4000-8000-00000000000e')), 'email': 'outro.carga@teste.local'}
PESSOAL_DESTINO, EMPRESA_DESTINO, PERFIL_OUTRO = 1, 2, 50
ORIGEM = {nome: dados['id'] for nome, dados in L.PERFIS.items()}  # 101 Pessoal, 102 Empresa, 103 Perfil B, 104 inativo
MAPA = {'titular_user_id': TITULAR['id'], 'perfis': {
    str(ORIGEM['PESSOAL']): {'destino_id': PESSOAL_DESTINO}, str(ORIGEM['EMPRESA']): {'destino_id': EMPRESA_DESTINO},
    str(ORIGEM['PERFIL_B']): {'criar': {'nome': 'Perfil B (carga)'}}, str(ORIGEM['INATIVO_A']): {'criar': {'nome': 'Inativo (carga)'}}}}


@pytest.fixture(scope='module')
def origem(tmp_path_factory):
    with L.ClusterLocal(PG_BIN, tmp_path_factory.mktemp('carga_origem')) as c:
        c.preparar()
        conn = c.conectar()
        with conn.cursor() as cur:
            for semear in (L.semear_recorrencia_e2e, L.semear_receitas_e2e, L.semear_cartoes_e2e, L.semear_financiamento_e2e):
                semear(cur)
            cur.execute("update public.config_agregador set numero_cartao = '4111 1111 1111 1234', codigo_seguranca = '987', "
                        "data_validade = '12/2030'")
            cur.execute("insert into public.item_despesa (perfil_financeiro_id, nome, tipo, ativo, recorrente) "
                        "values (null, 'Consorcio antigo (ficticio)', 'Consorcio', false, false)")
            cur.execute("update public.item_despesa i set origem_tipo = 'FINANCIAMENTO', origem_id = f.id "
                        "from public.financiamento f where f.item_despesa_id = i.id")
            cur.execute("insert into public.categoria (nome, cor, ativo, sistemica, bloquear_edicao, bloquear_exclusao, codigo_sistema) "
                        "values ('Combustivel (ficticia)', '#f59e0b', true, true, true, true, 'MOB_COMBUSTIVEL_TESTE')")
            cur.execute("insert into public.preferencia (nome_usuario, renda_principal, mes_inicio_planejamento, tema_sistema, "
                        "cor_principal, ajustar_competencia_automatico) values ('Titular (ficticio)', 5000, 3, 'claro', '#123456', false)")
            cur.execute('insert into public.usuario (email, password_hash, nome, ativo) values '
                        "('flask.carga@teste.local', 'hash-ficticio', 'Login do Flask', true)")
        conn.close()
        yield c


@pytest.fixture(scope='module')
def destino(tmp_path_factory):
    with L.ClusterLocal(PG_BIN, tmp_path_factory.mktemp('carga_destino')) as c:
        c.aplicar_shim()
        c.criar_tabelas_legadas()
        conn = c.conectar()
        with conn.cursor() as cur:
            for migration in sorted((ROOT / 'supabase' / 'migrations').glob('*.sql')):
                cur.execute(migration.read_text(encoding='utf-8'))
            for usuario in (TITULAR, OUTRO):
                cur.execute('insert into auth.users (id, email) values (%s, %s)', (usuario['id'], usuario['email']))
            for pid, nome, tipo in ((PESSOAL_DESTINO, 'Pessoal', 'PESSOAL'), (EMPRESA_DESTINO, 'Empresa', 'EMPRESA'),
                                    (PERFIL_OUTRO, 'Outro (ficticio)', 'PESSOAL')):
                cur.execute("insert into public.perfil_financeiro (id, nome, tipo, cor, ativo, padrao) values (%s, %s, %s, '#2563eb', true, false)",
                            (pid, nome, tipo))
            cur.execute("select setval(pg_get_serial_sequence('public.perfil_financeiro', 'id'), 100)")
            for usuario, pid in ((TITULAR, PESSOAL_DESTINO), (TITULAR, EMPRESA_DESTINO), (OUTRO, PERFIL_OUTRO)):
                cur.execute("insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) values (%s, %s, 'TITULAR', true)",
                            (usuario['id'], pid))
            cur.execute("insert into public.conta_bancaria (perfil_financeiro_id, nome, instituicao, tipo, status, cor_display) "
                        "values (%s, 'Conta do outro (ficticia)', 'Banco ficticio', 'Conta Corrente', 'ATIVO', '#3b82f6')", (PERFIL_OUTRO,))
            cur.execute("insert into public.indice_tr_mensal (ano, mes, competencia, valor_decimal, fonte) values (2034, 1, '2034-01', 0.0020, 'DESTINO')")
            cur.execute("insert into public.categoria (nome, cor, ativo, sistemica, bloquear_edicao, bloquear_exclusao, codigo_sistema) "
                        "values ('Combustivel', '#f59e0b', true, true, true, true, 'MOB_COMBUSTIVEL_TESTE')")
        conn.close()
        yield c


@pytest.fixture
def par(origem, destino):
    return copiar(origem), copiar(destino)


def test_ensaio_nao_grava_nada(par):
    o, d = par
    antes_o, antes_d = resumo_tabelas(o), resumo_tabelas(d)
    relatorio = carga.executar(o, d, MAPA, confirmar=False)
    assert relatorio['resultado'] == 'ENSAIO (nada gravado)' and relatorio['origem_inalterada'] is True
    assert resumo_tabelas(o) == antes_o and resumo_tabelas(d) == antes_d


def test_carga_gravada_igual_a_origem(par):
    o, d = par
    antes_o, outro = resumo_tabelas(o), resumo_perfil(d, PERFIL_OUTRO)
    relatorio = carga.executar(o, d, MAPA, confirmar=True)
    assert relatorio['resultado'] == 'GRAVADO' and relatorio['conferencia'].startswith('OK')
    assert resumo_tabelas(o) == antes_o  # origem intacta
    assert resumo_perfil(d, PERFIL_OUTRO) == outro  # dados do outro usuario intactos
    for t, n in relatorio['tabelas'].items():
        assert n['inseridos'] + n['reaproveitados'] == n['origem'], t
    assert {'conta', 'financiamento_parcela', 'lancamento_agregado', 'item_despesa', 'receita_realizada'} <= set(relatorio['tabelas'])
    # Ciclo conta <-> parcela e origem_id traduzidos.
    assert sql(d, 'select count(*) as n from public.financiamento_parcela p join public.conta c on c.id = p.conta_id '
                  'where c.financiamento_parcela_id <> p.id')[0]['n'] == 0
    assert sql(d, "select count(*) as n from public.financiamento_parcela p where p.conta_id is not null")[0]['n'] > 0
    assert sql(d, "select count(*) as n from public.item_despesa i join public.financiamento f on f.id = i.origem_id "
                  "where i.origem_tipo = 'FINANCIAMENTO' and f.item_despesa_id = i.id")[0]['n'] == 1
    # Perfis: Pessoal e Empresa existentes; os outros criados com o titular como gestor.
    novos = {r['nome']: r['id'] for r in sql(d, "select id, nome from public.perfil_financeiro where id > 100")}
    assert set(novos) == {'Perfil B (carga)', 'Inativo (carga)'}
    # Categoria do sistema reaproveitada; TR divergente reportada, destino mantido.
    assert sql(d, "select count(*) as n from public.categoria where codigo_sistema = 'MOB_COMBUSTIVEL_TESTE'")[0]['n'] == 1
    assert '2034-01' in relatorio['tr_divergentes']
    assert sql(d, "select fonte from public.indice_tr_mensal where competencia = '2034-01'") == [{'fonte': 'DESTINO'}]
    # Nada sensivel de cartao.
    assert relatorio['sensiveis']['cartoes'] >= 1
    for r in sql(d, 'select numero_cartao, codigo_seguranca, data_validade from public.config_agregador'):
        assert r['codigo_seguranca'] is None and r['data_validade'] is None and r['numero_cartao'] == '•••• 1234'
    # Preferencias do Flask: do titular e de cada perfil carregado.
    assert sql(d, 'select tema_sistema, cor_principal, nome_usuario from financeiro.preferencia_usuario where user_id = %s', (TITULAR['id'],)) == \
        [{'tema_sistema': 'claro', 'cor_principal': '#123456', 'nome_usuario': 'Titular (ficticio)'}]
    prefs = sql(d, 'select perfil_financeiro_id, renda_principal, mes_inicio_planejamento, ajustar_competencia_automatico '
                   'from financeiro.preferencia_perfil order by 1')
    assert len(prefs) == 4 and all(float(p['renda_principal']) == 5000 and p['mes_inicio_planejamento'] == 3
                                   and p['ajustar_competencia_automatico'] is False for p in prefs)
    # Login do Flask nao vai (no novo aplicativo o login e o Auth).
    assert not sql(d, "select 1 from public.usuario where email = 'flask.carga@teste.local'")


MAIO = datetime.date(2026, 5, 1)


def _compra_recorrente_na_origem(o):
    """Cartao, assinatura recorrente no cartao e a compra dela ja gravada pelo Flask (compra_id deterministico do id
    da origem, 9101), mais uma compra avulsa com compra_id qualquer."""
    pessoal = ORIGEM['PESSOAL']
    categoria = sql(o, 'select min(id) as id from public.categoria')[0]['id']
    sql(o, "insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente) "
           "values (9100, 'Cartao recorrencia (ficticio)', 'Agregador', %s, %s, true, false)", (pessoal, categoria))
    sql(o, "insert into public.config_agregador (item_despesa_id, dia_fechamento, dia_vencimento, numero_cartao) "
           "values (9100, 25, 5, '4111 1111 1111 4321')")
    sql(o, "insert into public.item_despesa (id, nome, tipo, perfil_financeiro_id, categoria_id, ativo, recorrente, "
           "tipo_recorrencia, meio_pagamento, cartao_id, valor, data_vencimento) values (9101, 'Assinatura (ficticia)', "
           "'Simples', %s, %s, true, true, 'mensal', 'cartao', 9100, 39.90, '2026-05-01')", (pessoal, categoria))
    sql(o, "insert into public.lancamento_agregado (item_despesa_id, cartao_id, perfil_financeiro_id, categoria_id, descricao, "
           "valor, data_compra, mes_fatura, numero_parcela, total_parcelas, is_recorrente, compra_id) values "
           "(9101, 9100, %s, %s, 'Assinatura (ficticia)', 39.90, '2026-05-01', '2026-05-01', 1, 1, true, %s), "
           "(null, 9100, %s, %s, 'Compra avulsa (ficticia)', 10, '2026-05-02', '2026-05-01', 1, 1, false, 'compra-avulsa-ficticia')",
        (pessoal, categoria, carga.compra_id_recorrente(9101, MAIO), pessoal, categoria))


def _assinatura_no_destino(d):
    item = sql(d, "select id from public.item_despesa where nome = 'Assinatura (ficticia)'")[0]['id']
    gravados = {r['descricao']: r['compra_id'] for r in sql(
        d, "select descricao, compra_id from public.lancamento_agregado where descricao in ('Assinatura (ficticia)', 'Compra avulsa (ficticia)')")}
    plano = sql(d, 'select situacao from financeiro.plano_recorrencia(%s, %s) where item_despesa_id = %s and competencia = %s',
                (PESSOAL_DESTINO, MAIO, item, MAIO))
    return item, gravados, plano


def test_compra_recorrente_no_cartao_reconhecida_pelo_motor(par):
    """FIN-POS-MIGRACAO-DESPESAS-1: o compra_id deterministico (uuid5 de "<item>-<mes_fatura>") e recalculado com o id
    novo do item; sem isso o plano do motor via a compra ja gravada pelo Flask como "a gerar" (duplicaria)."""
    o, d = par
    _compra_recorrente_na_origem(o)
    relatorio = carga.executar(o, d, MAPA, confirmar=True)
    assert relatorio['resultado'] == 'GRAVADO' and relatorio['conferencia'].startswith('OK')
    assert relatorio['compras_recorrentes_recalculadas'] == 1
    item, gravados, plano = _assinatura_no_destino(d)
    assert item != 9101
    assert gravados == {'Assinatura (ficticia)': carga.compra_id_recorrente(item, MAIO), 'Compra avulsa (ficticia)': 'compra-avulsa-ficticia'}
    assert plano == [{'situacao': 'EXISTENTE'}]


def test_correcao_da_carga_anterior(par, monkeypatch):
    """scripts/corrigir_compra_id_recorrente.py sobre um destino carregado como no FIN-BLOCO-D-3 (compra_id copiado com
    o id antigo): simular nao grava; corrigir recalcula so a compra recorrente, o plano passa a ve-la como EXISTENTE e a
    segunda execucao nao tem o que corrigir."""
    from scripts import corrigir_compra_id_recorrente as correcao
    o, d = par
    _compra_recorrente_na_origem(o)
    with monkeypatch.context() as m:  # carga como era no FIN-BLOCO-D-3
        m.setattr(carga.Carga, 'compra_id_destino', lambda self, linha: linha.get('compra_id'))
        carga.executar(o, d, MAPA, confirmar=True)
    item, gravados, plano = _assinatura_no_destino(d)
    assert gravados['Assinatura (ficticia)'] == carga.compra_id_recorrente(9101, MAIO) and plano == [{'situacao': 'A_GERAR'}]

    antes = resumo_tabelas(d)
    simulacao = correcao.executar(d, o, PESSOAL_DESTINO, MAIO, confirmar=False)
    assert simulacao['linhas'] == 1 and simulacao['resultado'].startswith('SIMULACAO') and resumo_tabelas(d) == antes
    relatorio = correcao.executar(d, o, PESSOAL_DESTINO, MAIO, confirmar=True)
    assert relatorio['resultado'] == 'CORRIGIDO' and relatorio['previa_depois'] == simulacao['previa_esperada_depois']
    assert relatorio['registro'] == simulacao['registro'] and len(relatorio['registro']) == 1
    assert relatorio['registro'][0]['compra_id_anterior'] == carga.compra_id_recorrente(9101, MAIO)
    item, gravados, plano = _assinatura_no_destino(d)
    assert gravados == {'Assinatura (ficticia)': carga.compra_id_recorrente(item, MAIO), 'Compra avulsa (ficticia)': 'compra-avulsa-ficticia'}
    assert plano == [{'situacao': 'EXISTENTE'}]
    with pytest.raises(correcao.CorrecaoRecusada, match='Nada a corrigir'):
        correcao.executar(d, o, PESSOAL_DESTINO, MAIO, confirmar=True)


def test_correcao_recusa_divergencia_e_colisao(par, monkeypatch):
    """Sem identidade inequivoca com a origem, ou com o compra_id novo ja em uso, nada e gravado."""
    from scripts import corrigir_compra_id_recorrente as correcao
    o, d = par
    _compra_recorrente_na_origem(o)
    with monkeypatch.context() as m:
        m.setattr(carga.Carga, 'compra_id_destino', lambda self, linha: linha.get('compra_id'))
        carga.executar(o, d, MAPA, confirmar=True)
    item = sql(d, "select id from public.item_despesa where nome = 'Assinatura (ficticia)'")[0]['id']
    sql(d, "update public.lancamento_agregado set valor = 49.90 where descricao = 'Assinatura (ficticia)'")
    antes = resumo_tabelas(d)
    with pytest.raises(correcao.CorrecaoRecusada, match='diferentes da origem'):
        correcao.executar(d, o, PESSOAL_DESTINO, MAIO, confirmar=True)
    assert resumo_tabelas(d) == antes
    sql(d, "update public.lancamento_agregado set valor = 39.90 where descricao = 'Assinatura (ficticia)'")
    sql(d, "update public.lancamento_agregado set compra_id = %s where descricao = 'Compra avulsa (ficticia)'",
        (carga.compra_id_recorrente(item, MAIO),))
    antes = resumo_tabelas(d)
    with pytest.raises(correcao.CorrecaoRecusada, match='ja existe no destino'):
        correcao.executar(d, o, PESSOAL_DESTINO, MAIO, confirmar=True)
    assert resumo_tabelas(d) == antes


def test_isolamento_e_leitura_pelo_titular(par):
    o, d = par
    carga.executar(o, d, MAPA, confirmar=True)
    contas = chamar(d, TITULAR, 'select financeiro.contas_bancarias_tela(%s, %s)', (PESSOAL_DESTINO, 'ATIVO'))
    nomes = {c['nome'] for c in contas}
    assert 'Conta Pessoal (A)' in nomes and 'Carteira legado sem perfil' in nomes  # sem perfil = do "Pessoal", como no Flask
    assert 'Conta do outro (ficticia)' not in nomes
    with pytest.raises(psycopg2.Error) as e:
        chamar(d, OUTRO, 'select financeiro.contas_bancarias_tela(%s, %s)', (PESSOAL_DESTINO, 'ATIVO'))
    assert e.value.pgcode == '42501'
    assert {c['nome'] for c in chamar(d, OUTRO, 'select financeiro.contas_bancarias_tela(%s, %s)', (PERFIL_OUTRO, 'ATIVO'))} == \
        {'Conta do outro (ficticia)'}


def test_segunda_carga_recusada_sem_duplicar(par):
    o, d = par
    carga.executar(o, d, MAPA, confirmar=True)
    depois = resumo_tabelas(d)
    with pytest.raises(carga.CargaRecusada, match='ja tem dados|Ja existe perfil'):
        carga.executar(o, d, MAPA, confirmar=True)
    assert resumo_tabelas(d) == depois


def test_referencia_sem_fk_no_destino_real_e_traduzida(par):
    """FIN-BLOCO-D-1: no Supabase (esquema do Alembic) lancamento_agregado.categoria_cartao_id nao tem FK."""
    o, d = par
    for r in sql(d, "select conname from pg_constraint where contype = 'f' and conrelid = 'public.lancamento_agregado'::regclass "
                    "and conkey = array[(select attnum from pg_attribute where attrelid = 'public.lancamento_agregado'::regclass "
                    "and attname = 'categoria_cartao_id')]"):
        sql(d, f'alter table public.lancamento_agregado drop constraint "{r["conname"]}"')
    origem = sql(o, 'select l.descricao, c.nome from public.lancamento_agregado l join public.categoria_cartao c on c.id = l.categoria_cartao_id '
                    'order by 1, 2')
    assert origem, 'cenario sem compra com categoria do cartao'
    relatorio = carga.executar(o, d, MAPA, confirmar=True)
    assert relatorio['conferencia'].startswith('OK')
    destino = sql(d, 'select l.descricao, c.nome from public.lancamento_agregado l join public.categoria_cartao c on c.id = l.categoria_cartao_id '
                     'where l.perfil_financeiro_id is distinct from %s order by 1, 2', (PERFIL_OUTRO,))
    assert destino == origem


def test_registro_preexistente_reaproveitado_por_identidade(par):
    """FIN-BLOCO-D-1: a fonte de receita da origem ja copiada para o Pessoal do destino e reaproveitada, nao duplicada."""
    o, d = par
    fonte = sql(o, 'select id, nome from public.item_receita where perfil_financeiro_id = %s or perfil_financeiro_id is null '
                   'order by id limit 1', (ORIGEM['PESSOAL'],))[0]
    previsoes = sql(o, 'select count(*) n from public.receita_orcamento where item_receita_id = %s', (fonte['id'],))[0]['n']
    did = sql(d, "insert into public.item_receita (perfil_financeiro_id, nome, tipo, ativo, recorrente) values (%s, %s, 'OUTROS', false, false) "
                 'returning id', (PESSOAL_DESTINO, fonte['nome']))[0]['id']
    antes = resumo_tabelas(d)
    with pytest.raises(carga.CargaRecusada, match=r'"Pessoal" ja tem dados \(item_receita\)'):
        carga.executar(o, d, MAPA, confirmar=True)
    with pytest.raises(carga.CargaRecusada, match='registro inexistente'):
        carga.executar(o, d, {**MAPA, 'preexistentes': {'item_receita': {str(fonte['id']): did + 1000}}}, confirmar=True)
    sql(d, "update public.item_receita set nome = nome || ' (outro)' where id = %s", (did,))
    with pytest.raises(carga.CargaRecusada, match='nao e o mesmo registro'):
        carga.executar(o, d, {**MAPA, 'preexistentes': {'item_receita': {str(fonte['id']): did}}}, confirmar=True)
    sql(d, 'update public.item_receita set nome = %s where id = %s', (fonte['nome'], did))
    assert resumo_tabelas(d) == antes
    relatorio = carga.executar(o, d, {**MAPA, 'preexistentes': {'item_receita': {str(fonte['id']): did}}}, confirmar=True)
    assert relatorio['resultado'] == 'GRAVADO' and relatorio['conferencia'].startswith('OK')
    assert relatorio['preexistentes']['item_receita'][str(fonte['id'])]['destino_id'] == did
    assert sql(d, 'select count(*) n from public.item_receita where nome = %s', (fonte['nome'],))[0]['n'] == 1
    assert sql(d, 'select count(*) n from public.receita_orcamento where item_receita_id = %s', (did,))[0]['n'] == previsoes


def _destino_sem_titular(d):
    """Como o projeto real antes do vinculo da conta: Pessoal e Empresa sem acesso de nenhuma conta; mais dois perfis vazios
    e sem acesso para os outros perfis da origem."""
    sql(d, 'delete from financeiro.perfil_acesso where perfil_financeiro_id in (%s, %s)', (PESSOAL_DESTINO, EMPRESA_DESTINO))
    for pid, nome in ((60, 'Perfil B destino'), (61, 'Inativo destino')):
        sql(d, "insert into public.perfil_financeiro (id, nome, tipo, cor, ativo, padrao) values (%s, %s, 'PESSOAL', '#2563eb', true, false)",
            (pid, nome))
    return {'titular_user_id': None, 'perfis': {
        str(ORIGEM['PESSOAL']): {'destino_id': PESSOAL_DESTINO, 'nome': 'Pessoal'},
        str(ORIGEM['EMPRESA']): {'destino_id': EMPRESA_DESTINO, 'nome': 'Empresa'},
        str(ORIGEM['PERFIL_B']): {'destino_id': 60, 'nome': 'Perfil B destino'},
        str(ORIGEM['INATIVO_A']): {'destino_id': 61, 'nome': 'Inativo destino'}}}


def test_carga_sem_titular_fica_sem_acesso_ate_o_vinculo(par):
    """FIN-BLOCO-D-3: a conta do titular ainda nao existe; os perfis carregados ficam sem acesso de nenhuma conta."""
    o, d = par
    mapa = _destino_sem_titular(d)
    antes_o, outro = resumo_tabelas(o), resumo_perfil(d, PERFIL_OUTRO)
    relatorio = carga.executar(o, d, mapa, confirmar=True)
    assert relatorio['resultado'] == 'GRAVADO' and relatorio['conferencia'].startswith('OK')
    assert relatorio['titular'].startswith('sem titular')
    assert resumo_tabelas(o) == antes_o and resumo_perfil(d, PERFIL_OUTRO) == outro
    for t, n in relatorio['tabelas'].items():
        assert n['inseridos'] + n['reaproveitados'] == n['origem'], t
    perfis = [PESSOAL_DESTINO, EMPRESA_DESTINO, 60, 61]
    assert sql(d, 'select count(*) n from financeiro.perfil_acesso where perfil_financeiro_id = any(%s)', (perfis,))[0]['n'] == 0
    # Preferencias: as do usuario ficam pendentes (sem conta); as de cada perfil sao copiadas.
    assert relatorio['preferencias']['usuario'].startswith('pendente')
    assert sql(d, 'select count(*) n from financeiro.preferencia_usuario')[0]['n'] == 0
    assert sql(d, 'select count(*) n from financeiro.preferencia_perfil where perfil_financeiro_id = any(%s)', (perfis,))[0]['n'] == 4
    # Ninguem le os dados carregados; depois do vinculo, so o titular.
    for usuario in (TITULAR, OUTRO):
        with pytest.raises(psycopg2.Error) as e:
            chamar(d, usuario, 'select financeiro.contas_bancarias_tela(%s, %s)', (PESSOAL_DESTINO, 'ATIVO'))
        assert e.value.pgcode == '42501'
    for pid in (PESSOAL_DESTINO, EMPRESA_DESTINO):
        sql(d, "insert into financeiro.perfil_acesso (user_id, perfil_financeiro_id, papel, pode_gerir) values (%s, %s, 'TITULAR', true)",
            (TITULAR['id'], pid))
    nomes = {c['nome'] for c in chamar(d, TITULAR, 'select financeiro.contas_bancarias_tela(%s, %s)', (PESSOAL_DESTINO, 'ATIVO'))}
    assert 'Conta Pessoal (A)' in nomes and 'Conta do outro (ficticia)' not in nomes
    with pytest.raises(psycopg2.Error):
        chamar(d, OUTRO, 'select financeiro.contas_bancarias_tela(%s, %s)', (PESSOAL_DESTINO, 'ATIVO'))


def test_carga_sem_titular_recusas(par):
    o, d = par
    antes = resumo_tabelas(d)
    # Perfis de destino ainda com acesso de uma conta (o destino do fixture: titular gestor de Pessoal e Empresa).
    mapa_com_acesso = {'titular_user_id': None, 'perfis': {**MAPA['perfis'],
                       str(ORIGEM['PESSOAL']): {'destino_id': PESSOAL_DESTINO, 'nome': 'Pessoal'},
                       str(ORIGEM['EMPRESA']): {'destino_id': EMPRESA_DESTINO, 'nome': 'Empresa'}}}
    with pytest.raises(carga.CargaRecusada, match='ja tem acesso de alguma conta'):
        carga.executar(o, d, mapa_com_acesso, confirmar=True)
    assert resumo_tabelas(d) == antes
    mapa = _destino_sem_titular(d)
    antes = resumo_tabelas(d)
    # Nome diferente ou ausente: o id sozinho nao identifica o perfil.
    for regra in ({'destino_id': PESSOAL_DESTINO, 'nome': 'Empresa'}, {'destino_id': PESSOAL_DESTINO}):
        with pytest.raises(carga.CargaRecusada, match='nome diferente do mapa'):
            carga.executar(o, d, {**mapa, 'perfis': {**mapa['perfis'], str(ORIGEM['PESSOAL']): regra}}, confirmar=True)
    # Criar perfil sem titular: ficaria sem gestor.
    with pytest.raises(carga.CargaRecusada, match='nao pode ser criado'):
        carga.executar(o, d, {**mapa, 'perfis': {**mapa['perfis'], str(ORIGEM['PERFIL_B']): {'criar': {'nome': 'Novo'}}}}, confirmar=True)
    assert resumo_tabelas(d) == antes


def test_recusas_quando_falta_regra(par):
    o, d = par
    antes = resumo_tabelas(d)
    # Perfil ignorado com dados.
    with pytest.raises(carga.CargaRecusada, match='nao pode ser ignorado'):
        carga.executar(o, d, {**MAPA, 'perfis': {**MAPA['perfis'], str(ORIGEM['PERFIL_B']): 'ignorar'}}, confirmar=True)
    # Registros sem perfil e nenhum destino chamado "Pessoal".
    sql(d, "update public.perfil_financeiro set nome = 'Pessoal antigo' where id = %s", (PESSOAL_DESTINO,))
    with pytest.raises(carga.CargaRecusada, match='nenhum perfil de destino se chama "Pessoal"'):
        carga.executar(o, d, MAPA, confirmar=True)
    sql(d, "update public.perfil_financeiro set nome = 'Pessoal' where id = %s", (PESSOAL_DESTINO,))
    # Referencia sem regra (JSON com ids de outra tabela).
    sql(o, "insert into public.despesa_prevista (perfil_financeiro_id, origem_tipo, origem_id, categoria_id, data_prevista, "
           "data_original_prevista, data_atual_prevista, valor_previsto, status, metadata, criado_em, atualizado_em) values "
           "(%s, 'VEICULO', 1, (select min(id) from public.categoria), '2040-01-01', '2040-01-01', '2040-01-01', 10, 'PREVISTA', "
           "'{\"ciclo_id\": 1}', now(), now())", (ORIGEM['PERFIL_B'],))
    with pytest.raises(carga.CargaRecusada, match='Referencia sem regra'):
        carga.executar(o, d, MAPA, confirmar=True)
    assert resumo_tabelas(d) == antes
