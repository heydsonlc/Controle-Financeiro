"""
Testes FIN-REG-03 — relatorios fiscais do novo aplicativo (web/src/js/relatorio-fiscal.js, gerados sem servidor) conferidos
com os do PROPRIO Flask (IrRelatorioService e LastroRelatorioService) sobre a mesma base ficticia, num cluster PostgreSQL
descartavel:
- Imposto de Renda (perfil Pessoal) e Documentos Fiscais e Lastro (perfil Empresa), Excel e PDF;
- Saidas sem documento (perfil Empresa), Excel e PDF.
PDF: byte a byte. XLSX: abas, valores, formato de cada celula, cabecalhos (linha 1 e rotulos no meio da aba), quebra de
linha, painel congelado, autofiltro e larguras, lidos pelo openpyxl. A hora de geracao e fixada nos dois lados (no Flask, so
dentro do subprocesso de teste). Confere tambem que gerar os relatorios nao altera nenhuma tabela e o isolamento de perfis.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import date
from io import BytesIO

import pytest

from tests.supabase_local import EMPRESA_D, USUARIO_D, ClusterLocal, semear_empresa_vazia, semear_recorrencias
from tests.test_supabase_integracao_1123_1126 import resumo_tabelas
from tests.test_supabase_recorrencia import ID, PG_BIN, ROOT, USUARIO_A, USUARIO_B, atribuir, chamar, copiar, sql

openpyxl = pytest.importorskip('openpyxl')
psycopg2 = pytest.importorskip('psycopg2')
pytestmark = [pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados'),
              pytest.mark.skipif(shutil.which('node') is None, reason='node nao encontrado')]

EMPRESA, PESSOAL = EMPRESA_D['id'], ID['PESSOAL']
ANO = date.today().year
AGORA = '01/07/2031 10:30'

_SCRIPT_FLASK = """
import json, sys, uuid
from datetime import datetime
import backend.services.ir_relatorio_service as irs
import backend.services.lastro_relatorio_service as lrs
class _Agora(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2031, 7, 1, 10, 30)
irs.datetime = _Agora  # hora fixa, so neste subprocesso de teste
lrs.datetime = _Agora
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    email = f'flask.rel.{uuid.uuid4().hex[:8]}@teste.local'
    u = Usuario(email=email, nome='Rel', ativo=True)
    u.definir_senha('Senha-ficticia-rel-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-rel-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
saida = []
for rota in json.loads(sys.argv[2]):
    r = c.get(rota)
    saida.append({'status': r.status_code, 'hex': r.data.hex() if r.status_code == 200 else None,
                  'erro': None if r.status_code == 200 else r.get_json(), 'nome': r.headers.get('Content-Disposition')})
print('FLASK_JSON ' + json.dumps(saida))
"""

_SCRIPT_NODE = """
import * as R from %s;
const pedidos = JSON.parse(await new Promise((ok) => { let t = ''; process.stdin.on('data', (d) => { t += d; }); process.stdin.on('end', () => ok(t)); }));
const saida = pedidos.map(({ funcao, entrada }) => {
    try {
        if (entrada.comprovantes) entrada.comprovantes = R.filtrarComprovantes(entrada.comprovantes, entrada.filtros);
        if (entrada.saidas) R.validarFiltrosSaidas(entrada.filtros);
        const r = R[funcao](entrada);
        return { hex: Buffer.from(r.conteudo).toString('hex'), nome: r.nome };
    } catch (erro) {
        return { erro: erro.message };
    }
});
console.log(JSON.stringify(saida));
"""


def pelo_flask(dsn, perfil, rotas):
    env = {**os.environ, 'APP_ENV': 'local', 'FLASK_DEBUG': '0', 'DATABASE_URL': dsn}
    env.pop('FLASK_ENV', None)
    r = subprocess.run([sys.executable, '-c', _SCRIPT_FLASK, str(perfil), json.dumps(rotas)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    linha = next((l for l in r.stdout.splitlines() if l.startswith('FLASK_JSON ')), None)
    assert r.returncode == 0 and linha, r.stderr[-3000:]
    return json.loads(linha[len('FLASK_JSON '):])


def pelo_novo(pedidos):
    modulo = json.dumps((ROOT / 'web' / 'src' / 'js' / 'relatorio-fiscal.js').as_uri())
    r = subprocess.run(['node', '--input-type=module', '-e', _SCRIPT_NODE % modulo], cwd=ROOT, input=json.dumps(pedidos),
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def comprovantes_do_novo(dsn, usuario, perfil, filtros):
    """O que o adaptador da tela monta: a lista de ir_comprovantes_tela e, para quem tem vinculo, os vinculos ativos de
    vinculos_documento_tela em ordem de id."""
    lista = chamar(dsn, usuario, 'select financeiro.ir_comprovantes_tela(%s, %s::jsonb, null)', (perfil, json.dumps(filtros)))['data']
    for c in lista:
        c['vinculos'] = sorted(chamar(dsn, usuario, 'select financeiro.vinculos_documento_tela(%s, %s)', (perfil, c['id'])),
                               key=lambda v: v['id']) if c['vinculos_count'] else []
    return lista


def enviar(dsn, usuario, perfil, nome, campos):
    conteudo = b'%PDF-1.4\n' + nome.encode() + uuid.uuid4().bytes
    texto = f'Documento ficticio {nome} para o teste dos relatorios fiscais, sem palavras de classificacao automatica.'
    dados = {'nome_arquivo': nome, 'mime_type': 'application/pdf', 'ano_calendario': ANO, 'texto_extraido': texto}
    doc = chamar(dsn, usuario, 'select financeiro.enviar_comprovante(%s, %s::jsonb, %s, %s)',
                 (perfil, json.dumps(dados), base64.b64encode(conteudo).decode(), str(uuid.uuid4())))['comprovante_id']
    if campos:
        sql(dsn, 'update public.ir_comprovante set ' + ', '.join(f'{k} = %s' for k in campos) + ' where id = %s', (*campos.values(), doc))
    return doc


def conta_a_pagar(dsn, nome, valor, dia=10):
    dados = {'nome': nome, 'valor': valor, 'categoria_id': 951, 'data_vencimento': date(ANO, date.today().month, dia).isoformat()}
    chamar(dsn, USUARIO_D, 'select financeiro.criar_despesa(%s, %s::jsonb, %s)', (EMPRESA, json.dumps(dados), str(uuid.uuid4())))
    return sql(dsn, 'select id from public.conta where perfil_financeiro_id = %s and descricao = %s', (EMPRESA, nome))[0]['id']


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    with ClusterLocal(PG_BIN, tmp_path_factory.mktemp('relfiscal')) as c:
        c.preparar(contas=False)
        conn = c.conectar()
        with conn.cursor() as cur:
            semear_recorrencias(cur)
            semear_empresa_vazia(cur)
        conn.close()
        dsn = c.dsn()
        atribuir(dsn, EMPRESA)
        atribuir(dsn, 'PESSOAL')
        def categoria(nome, contexto, natureza):
            return sql(dsn, "insert into public.ir_categoria (nome, descricao, dedutivel, ativo, ordem, tipo_contexto, natureza, created_at, "
                            "updated_at) values (%s, 'Categoria ficticia', %s, true, 90, %s, %s, now(), now()) returning id",
                       (nome, contexto == 'PESSOAL', contexto, natureza))[0]['id']
        cat_p = [categoria('Saúde (fictícia)', 'PESSOAL', 'DESPESA_DEDUTIVEL'), categoria('Educacao (ficticia)', 'PESSOAL', 'DESPESA_DEDUTIVEL')]
        cat_e = [categoria('Servicos tomados (ficticia)', 'EMPRESA', 'DESPESA_OPERACIONAL'), categoria('Comunicacao (ficticia)', 'EMPRESA', 'DESPESA_OPERACIONAL')]
        # ---- Pessoal: dedutivel sim/nao/indefinido, com e sem categoria, validado/pendente/erro, sem prestador, sem valor
        enviar(dsn, USUARIO_A, PESSOAL, 'recibo-medico.pdf', {
            'prestador_nome': 'Clínica Fictícia São José (teste)', 'prestador_cpf_cnpj': '11.111.111/0001-11', 'tomador_nome': 'Titular Ficticio',
            'valor': '1234.56', 'data_documento': date(ANO, 3, 10), 'categoria_ir_id': cat_p[0], 'dedutivel': True, 'status': 'VALIDADO',
            'confianca': 'ALTA', 'origem_classificacao': 'MANUAL', 'observacoes': 'consulta (ficticia)'})
        enviar(dsn, USUARIO_A, PESSOAL, 'escola.pdf', {
            'prestador_nome': 'Escola Ficticia', 'valor': '2500.00', 'data_documento': date(ANO, 2, 5), 'categoria_ir_id': cat_p[-1],
            'dedutivel': False, 'status': 'PENDENTE_REVISAO'})
        enviar(dsn, USUARIO_A, PESSOAL, 'sem-prestador.pdf', {'valor': '0.10', 'dedutivel': None, 'status': 'IMPORTADO'})
        enviar(dsn, USUARIO_A, PESSOAL, 'ilegivel.pdf', {'valor': None, 'dedutivel': None, 'status': 'ERRO_LEITURA',
                                                         'prestador_nome': 'Laboratorio (ficticio) \\ barra'})
        enviar(dsn, USUARIO_A, PESSOAL, 'outro-recibo.pdf', {
            'prestador_nome': 'Clínica Fictícia São José (teste)', 'valor': '99.99', 'data_documento': date(ANO, 3, 11),
            'categoria_ir_id': cat_p[0], 'dedutivel': True, 'status': 'VALIDADO'})
        # ---- Empresa: documentos com um, dois e nenhum vinculo; saidas com e sem situacao manual
        aluguel = conta_a_pagar(dsn, 'Aluguel sala (teste)', '300.00')
        internet = conta_a_pagar(dsn, 'Internet (teste)', '99.90', 12)
        conta_a_pagar(dsn, 'Energia eletrica com descricao bem comprida para o corte do PDF (teste)', '1250.45', 15)
        contador = conta_a_pagar(dsn, 'Honorarios do contador (teste)', '800.00', 20)
        nf = enviar(dsn, USUARIO_D, EMPRESA, 'nf-servico.pdf', {
            'prestador_nome': 'Fornecedor Ficticio Ltda', 'prestador_cpf_cnpj': '22.222.222/0001-22', 'valor': '300.00',
            'data_documento': date(ANO, 4, 2), 'categoria_ir_id': cat_e[0], 'status': 'VALIDADO', 'observacoes': 'nota (ficticia)'})
        pix = enviar(dsn, USUARIO_D, EMPRESA, 'pix-internet.pdf', {
            'prestador_nome': 'Provedor Ficticio', 'valor': '99.90', 'data_documento': date(ANO, 4, 12), 'categoria_ir_id': cat_e[-1],
            'status': 'PENDENTE_REVISAO'})
        enviar(dsn, USUARIO_D, EMPRESA, 'contrato-social.pdf', {'prestador_nome': 'Junta Comercial (ficticia)', 'valor': None,
                                                                'data_documento': date(ANO, 1, 15), 'status': 'IMPORTADO'})
        enviar(dsn, USUARIO_D, EMPRESA, 'recibo-avulso.pdf', {'valor': '45.10', 'categoria_ir_id': cat_e[0], 'status': 'VALIDADO'})
        chamar(dsn, USUARIO_D, 'select financeiro.vincular_saida_documento(%s, %s::jsonb)',
               (EMPRESA, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': aluguel, 'comprovante_id': nf, 'natureza': 'DESPESA_OPERACIONAL'})))
        chamar(dsn, USUARIO_D, 'select financeiro.vincular_saida_documento(%s, %s::jsonb)',
               (EMPRESA, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': internet, 'comprovante_id': pix})))
        chamar(dsn, USUARIO_D, 'select financeiro.vincular_saida_documento(%s, %s::jsonb)',
               (EMPRESA, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': internet, 'comprovante_id': nf})))
        sql(dsn, "update public.ir_comprovante_vinculo set status_lastro = 'AGUARDANDO_CONTADOR', observacoes = 'conferir (ficticio)' "
                 'where comprovante_id = %s', (pix,))
        chamar(dsn, USUARIO_D, 'select financeiro.marcar_status_saida(%s, %s::jsonb)',
               (EMPRESA, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': str(contador), 'status_lastro': 'AGUARDANDO_CONTADOR',
                                     'natureza': 'DESPESA_OPERACIONAL', 'observacoes': 'aguardando nota (ficticia)'})))
        yield dsn


def planilha(conteudo):
    wb = openpyxl.load_workbook(BytesIO(bytes.fromhex(conteudo)))
    saida = {}
    for ws in wb.worksheets:
        celulas = [c for linha in ws.iter_rows() for c in linha]
        saida[ws.title] = {
            'valores': [[c.value for c in linha] for linha in ws.iter_rows()],
            'formatos': {c.coordinate: c.number_format for c in celulas if c.value is not None},
            'cabecalhos': sorted(c.coordinate for c in celulas if str(c.fill.fgColor.rgb).upper() == '001D4ED8' and c.font.b
                                 and (c.font.color.rgb if c.font.color else None) == '00FFFFFF' and (c.value is not None or c.row == 1)),
            'alinhamento': {(c.alignment.wrap_text, c.alignment.vertical, c.alignment.horizontal) for c in celulas if c.value is not None},
            'congelado': ws.freeze_panes, 'filtro': ws.auto_filter.ref,
            'larguras': {k: d.width for k, d in ws.column_dimensions.items() if d.width},
        }
    return saida


def conferir(flask, novo):
    """Cada par (Flask, novo): mesmo PDF byte a byte ou mesma planilha; mesmo nome de arquivo."""
    assert flask['status'] == 200, flask
    assert 'erro' not in novo, novo
    assert novo['nome'] in flask['nome']  # Content-Disposition: attachment; filename=...
    if novo['nome'].endswith('.pdf'):
        assert novo['hex'] == flask['hex'], (bytes.fromhex(flask['hex'])[:1500], bytes.fromhex(novo['hex'])[:1500])
        return bytes.fromhex(novo['hex'])
    f, n = planilha(flask['hex']), planilha(novo['hex'])
    assert list(n) == list(f)
    for aba in f:
        for chave in f[aba]:
            assert n[aba][chave] == f[aba][chave], (aba, chave, f[aba][chave], n[aba][chave])
    return n


CONSULTAS_IR = {
    'PESSOAL': [{'ano': str(ANO)}, {'ano': str(ANO), 'busca': 'clínica'}, {'ano': str(ANO), 'status': 'VALIDADO'},
                {'ano': str(ANO), 'dedutivel': 'false'}, {'ano': str(ANO), 'somente_validados': 'sim'},
                {'ano': str(ANO), 'somente_pendentes': 'true'}, {'ano': '1999'}, {}],
    'EMPRESA': [{'ano': str(ANO)}, {'ano': str(ANO), 'busca': 'ficticio'}, {'ano': str(ANO), 'status_lastro': 'AGUARDANDO_CONTADOR'},
                {'ano': str(ANO), 'natureza': 'DESPESA_OPERACIONAL'}, {'ano': str(ANO), 'tipo_entidade': 'CONTA'},
                {'ano': str(ANO), 'somente_pendentes': '1'}, {'ano': str(ANO), 'tipo_documental': 'OUTRO'}, {'ano': '1999'}],
}


def consulta(filtros):
    from urllib.parse import urlencode
    return ('?' + urlencode(filtros)) if filtros else ''


@pytest.mark.parametrize('tipo', ['PESSOAL', 'EMPRESA'])
def test_relatorio_de_imposto_de_renda_igual_ao_flask(base, tipo):
    perfil, usuario = (PESSOAL, USUARIO_A) if tipo == 'PESSOAL' else (EMPRESA, USUARIO_D)
    nome = sql(base, 'select nome from public.perfil_financeiro where id = %s', (perfil,))[0]['nome']
    antes = resumo_tabelas(base)
    rotas, pedidos = [], []
    for filtros in CONSULTAS_IR[tipo]:
        comprovantes = comprovantes_do_novo(base, usuario, perfil, filtros)
        for formato, funcao in (('excel', 'excelIr'), ('pdf', 'pdfIr')):
            rotas.append(f'/api/ir/relatorios/{formato}{consulta(filtros)}')
            pedidos.append({'funcao': funcao, 'entrada': {'perfilNome': nome, 'empresa': tipo == 'EMPRESA', 'comprovantes': comprovantes,
                                                          'filtros': filtros, 'agora': AGORA, 'anoAtual': 2031}})
    flask, novo = pelo_flask(base, perfil, rotas), pelo_novo(pedidos)
    lidos = [conferir(f, n) for f, n in zip(flask, novo)]
    # O cenario exercita o que importa: agrupamentos, totais, vinculo principal e pendencias.
    geral = lidos[0]
    if tipo == 'PESSOAL':
        assert list(geral) == ['Resumo', 'Comprovantes'] and len(geral['Comprovantes']['valores']) == 6
        resumo = {l[0]: l[1] for l in geral['Resumo']['valores'][:9]}
        assert resumo['Total de comprovantes'] == 5 and resumo['Quantidade validada'] == 2 and resumo['Quantidade com erro de leitura'] == 1
        assert resumo['Valor total potencialmente dedutivel'] == pytest.approx(1234.56 + 0.10 + 99.99)  # o nao dedutivel fica fora
        assert geral['Resumo']['formatos']['B5'] == 'R$ #,##0.00' and geral['Resumo']['formatos']['B4'] == 'General'
        assert 'A11' in geral['Resumo']['cabecalhos'] and 'A3' in geral['Resumo']['cabecalhos']  # "Categoria IR" e "Ano-calendario"
        assert b'Valor potencialmente dedutivel: R$ 1.334,65' in lidos[1]
        assert len(lidos[2]['Comprovantes']['valores']) == 3  # busca com acento: as duas da clinica
    else:
        assert list(geral) == ['Resumo', 'Documentos', 'Lastros'] and len(geral['Documentos']['valores']) == 5
        resumo = {l[0]: l[1] for l in geral['Resumo']['valores'][:9]}
        assert resumo['Total de documentos'] == 4 and resumo['Documentos vinculados'] == 2 and resumo['Aguardando contador'] == 1
        assert resumo['Valor total documentado'] == pytest.approx(300 + 99.90 + 45.10)
        assert len(geral['Lastros']['valores']) == 4  # tres vinculos: a nota tem dois
        assert b'Pendencias:' in lidos[1] and b'Documentos com lastro: 2' in lidos[1]
    vazio = lidos[-2] if tipo == 'EMPRESA' else lidos[-4]
    assert len(vazio[list(vazio)[1]]['valores']) == 1  # ano sem documentos: so o cabecalho
    assert resumo_tabelas(base) == antes  # gerar relatorio nao altera nenhuma tabela


CONSULTAS_SAIDAS = [{'ano': str(ANO)}, {'ano': str(ANO), 'status': 'TODOS'}, {'ano': str(ANO), 'mes': str(date.today().month)},
                    {'ano': str(ANO), 'valor_minimo': '500'}, {'ano': str(ANO), 'busca': 'contador'},
                    {'ano': str(ANO), 'status': 'AGUARDANDO_CONTADOR'}, {'ano': str(ANO), 'origem': 'CONTA'},
                    {'ano': str(ANO), 'natureza': 'DESPESA_OPERACIONAL'}, {'ano': '1999'}]


def test_relatorio_de_saidas_sem_documento_igual_ao_flask(base):
    nome = sql(base, 'select nome from public.perfil_financeiro where id = %s', (EMPRESA,))[0]['nome']
    antes = resumo_tabelas(base)
    rotas, pedidos = [], []
    for filtros in CONSULTAS_SAIDAS:
        saidas = chamar(base, USUARIO_D, 'select financeiro.lastro_saidas_tela(%s, %s::jsonb, false)', (EMPRESA, json.dumps(filtros)))
        for formato, funcao in (('excel', 'excelSaidas'), ('pdf', 'pdfSaidas')):
            rotas.append(f'/api/ir/lastro/saidas-sem-documento/relatorio-{formato}{consulta(filtros)}')
            pedidos.append({'funcao': funcao, 'entrada': {'perfilNome': nome, 'saidas': saidas, 'filtros': filtros, 'agora': AGORA,
                                                          'anoAtual': 2031}})
    flask, novo = pelo_flask(base, EMPRESA, rotas), pelo_novo(pedidos)
    lidos = [conferir(f, n) for f, n in zip(flask, novo)]
    geral = lidos[0]
    assert list(geral) == ['Resumo', 'Saidas_sem_documento', 'Pendencias_contador']
    resumo = {l[0]: l[1] for l in geral['Resumo']['valores'][:10]}
    # padrao (pendentes): energia (sem documento) e contador (aguardando); aluguel e internet tem documento
    assert resumo['Total de saidas sem documento'] == 2 and resumo['Valor total sem documento'] == pytest.approx(2050.45)
    assert resumo['Quantidade aguardando contador'] == 1 and resumo['Quantidade pendente'] == 1
    assert len(geral['Pendencias_contador']['valores']) == 2 and geral['Resumo']['formatos']['B7'] == 'R$ #,##0.00'
    assert b'Valor total sem lastro: R$ 2.050,45' in lidos[1]
    assert len(lidos[6]['Saidas_sem_documento']['valores']) == 3  # valor minimo 500: energia e contador
    assert lidos[-2]['Saidas_sem_documento']['valores'][1][0].startswith('Nenhuma saida sem documento')
    assert resumo_tabelas(base) == antes


def test_filtros_invalidos_tem_a_mesma_recusa_do_flask(base):
    flask = pelo_flask(base, EMPRESA, ['/api/ir/relatorios/excel?ano=abc', '/api/ir/lastro/saidas-sem-documento/relatorio-pdf?ano=abc',
                                       f'/api/ir/lastro/saidas-sem-documento/relatorio-excel?ano={ANO}&mes=13'])
    novo = pelo_novo([{'funcao': 'excelIr', 'entrada': {'perfilNome': 'x', 'empresa': True, 'comprovantes': [], 'filtros': {'ano': 'abc'},
                                                        'agora': AGORA, 'anoAtual': 2031}},
                      {'funcao': 'pdfSaidas', 'entrada': {'perfilNome': 'x', 'saidas': [], 'filtros': {'ano': 'abc'}, 'agora': AGORA, 'anoAtual': 2031}},
                      {'funcao': 'excelSaidas', 'entrada': {'perfilNome': 'x', 'saidas': [], 'filtros': {'ano': str(ANO), 'mes': '13'},
                                                            'agora': AGORA, 'anoAtual': 2031}}])
    for f, n in zip(flask, novo):
        assert f['status'] == 400 and n == {'erro': f['erro']['error']}


def test_isolamento_entre_perfis_e_restricao_ao_perfil_empresa(base):
    # Saidas sem documento: so no perfil Empresa (403 no Flask; o banco recusa a consulta no novo aplicativo).
    flask = pelo_flask(base, PESSOAL, ['/api/ir/lastro/saidas-sem-documento/relatorio-excel', '/api/ir/lastro/saidas-sem-documento/relatorio-pdf'])
    assert [f['status'] for f in flask] == [403, 403]
    with pytest.raises(psycopg2.Error) as e:
        chamar(base, USUARIO_A, 'select financeiro.lastro_saidas_tela(%s, %s::jsonb, false)', (PESSOAL, '{}'))
    assert e.value.pgcode == '42501'
    # Conta sem acesso ao perfil (B nao ve a Empresa D nem o Pessoal de A); sem sessao; leitor le, como na tela.
    for usuario, perfil in ((USUARIO_B, EMPRESA), (USUARIO_B, PESSOAL), (USUARIO_A, EMPRESA), (None, EMPRESA)):
        for comando, args in (('select financeiro.ir_comprovantes_tela(%s, %s::jsonb, null)', (perfil, '{}')),
                              ('select financeiro.lastro_saidas_tela(%s, %s::jsonb, false)', (perfil, '{}'))):
            with pytest.raises(psycopg2.Error) as e:
                chamar(base, usuario, comando, args)
            assert e.value.pgcode == '42501', (usuario, perfil, comando)
    # Os documentos de um perfil nunca aparecem no relatorio do outro.
    pessoais = {c['id'] for c in comprovantes_do_novo(base, USUARIO_A, PESSOAL, {})}
    empresa = {c['id'] for c in comprovantes_do_novo(base, USUARIO_D, EMPRESA, {})}
    assert len(pessoais) == 5 and len(empresa) == 4 and not pessoais & empresa
    alheio = next(iter(empresa))
    with pytest.raises(psycopg2.Error) as e:  # vinculos de documento de outro perfil
        chamar(base, USUARIO_A, 'select financeiro.vinculos_documento_tela(%s, %s)', (PESSOAL, alheio))
    assert e.value.diag.message_hint == 'NAO_ENCONTRADA'
    with pytest.raises(psycopg2.Error):  # documento inexistente
        chamar(base, USUARIO_D, 'select financeiro.vinculos_documento_tela(%s, %s)', (EMPRESA, 999999))
