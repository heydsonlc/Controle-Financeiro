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
