"""
Testes FIN-REG-04 — pacote ZIP dos documentos da Empresa do novo aplicativo (web/src/js/zip-documentos.js, montado sem
servidor) conferido com o do PROPRIO Flask (DocumentoZipService) sobre a mesma base ficticia, num cluster PostgreSQL
descartavel: lista e organizacao dos arquivos em pastas, nomes seguros (acentos, nomes repetidos), bytes de cada documento
(iguais aos enviados e aos do Flask), indice (abas, valores, formatos, cabecalho, larguras), filtros, documento sem arquivo,
pacote sem documentos, integridade (SHA-256 e tamanho gravados), limites de volume, isolamento de perfis e nenhuma
alteracao no banco. A hora de geracao e fixada nos dois lados (no Flask, so dentro do subprocesso de teste).
"""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from datetime import date, timedelta
from io import BytesIO
from urllib.parse import urlencode

import pytest

from tests.supabase_local import EMPRESA_D, USUARIO_D, ClusterLocal, semear_empresa_vazia, semear_recorrencias
from tests.test_supabase_integracao_1123_1126 import resumo_tabelas
from tests.test_supabase_recorrencia import ID, PG_BIN, ROOT, USUARIO_A, USUARIO_B, atribuir, chamar, sql

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
import backend.services.documento_zip_service as dzs
class _Agora(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2031, 7, 1, 10, 30)
dzs.datetime = _Agora  # hora fixa, so neste subprocesso de teste
from backend.app import create_app
from backend.models import Usuario, db
app = create_app('local')
with app.app_context():
    email = f'flask.zip.{uuid.uuid4().hex[:8]}@teste.local'
    u = Usuario(email=email, nome='Zip', ativo=True)
    u.definir_senha('Senha-ficticia-zip-2026')
    db.session.add(u); db.session.commit()
c = app.test_client()
assert c.post('/login', data={'email': email, 'senha': 'Senha-ficticia-zip-2026'}).status_code == 302
assert c.post('/api/perfis-financeiros/ativo', json={'perfil_id': int(sys.argv[1])}).status_code == 200
saida = []
for rota in json.loads(sys.argv[2]):
    r = c.get(rota)
    saida.append({'status': r.status_code, 'hex': r.data.hex() if r.status_code == 200 else None,
                  'erro': None if r.status_code == 200 else r.get_json(), 'nome': r.headers.get('Content-Disposition')})
print('FLASK_JSON ' + json.dumps(saida))
"""

_SCRIPT_NODE = """
import * as Z from %s;
const pedidos = JSON.parse(await new Promise((ok) => { let t = ''; process.stdin.on('data', (d) => { t += d; }); process.stdin.on('end', () => ok(t)); }));
const saida = [];
for (const { entrada, arquivos, limites } of pedidos) {
    try {
        if (limites) Object.assign(Z.LIMITES, limites);
        entrada.filtros = Z.normalizarFiltros(entrada.filtros);
        if (!entrada.documentos.length) throw new Error(Z.ERRO_SEM_DOCUMENTOS);
        const recusa = Z.recusaPorVolume(entrada.documentos);
        if (recusa) throw new Error(recusa);
        for (const d of entrada.documentos) {
            if (!d.arquivo || arquivos[d.id] === undefined) continue;
            d.conteudo = new Uint8Array(Buffer.from(arquivos[d.id], 'hex'));
            const diferenca = await Z.divergencia(d, d.conteudo);
            if (diferenca) throw new Error('divergencia: ' + diferenca);
        }
        const r = Z.montarPacote(entrada);
        saida.push({ hex: Buffer.from(r.conteudo).toString('hex'), nome: r.nome });
    } catch (erro) {
        saida.push({ erro: erro.message });
    }
}
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
    modulo = json.dumps((ROOT / 'web' / 'src' / 'js' / 'zip-documentos.js').as_uri())
    r = subprocess.run(['node', '--input-type=module', '-e', _SCRIPT_NODE % modulo], cwd=ROOT, input=json.dumps(pedidos),
                       capture_output=True, text=True, encoding='utf-8', timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def pedido(dsn, filtros, usuario=USUARIO_D, perfil=EMPRESA):
    """O que o adaptador da tela monta: filtros normalizados, lista de ir_comprovantes_tela, vinculos ativos (o mais recente
    primeiro) e o arquivo de cada documento por arquivo_comprovante_tela."""
    normalizados = dict(filtros)
    if normalizados.get('status') in ('VALIDO', 'VENCIDO', 'ATIVO', 'PENDENTE') and not normalizados.get('status_documental'):
        normalizados['status_documental'] = normalizados.pop('status')
    documentos = chamar(dsn, usuario, 'select financeiro.ir_comprovantes_tela(%s, %s::jsonb, null)', (perfil, json.dumps(normalizados)))['data']
    arquivos = {}
    for d in documentos:
        d['vinculos'] = chamar(dsn, usuario, 'select financeiro.vinculos_documento_tela(%s, %s)', (perfil, d['id'])) if d['vinculos_count'] else []
        if d['arquivo']:
            lido = chamar(dsn, usuario, 'select financeiro.arquivo_comprovante_tela(%s, %s)', (perfil, d['id']))
            arquivos[d['id']] = base64.b64decode(lido['conteudo_base64']).hex()
    nome = sql(dsn, 'select nome from public.perfil_financeiro where id = %s', (perfil,))[0]['nome']
    return {'entrada': {'perfilNome': nome, 'documentos': documentos, 'filtros': filtros, 'agora': AGORA, 'anoAtual': 2031}, 'arquivos': arquivos}


ENVIADOS = {}  # id do documento -> bytes enviados


def enviar(dsn, nome, campos=None, metadados=None, ano=ANO, conteudo=None, mime='application/pdf'):
    conteudo = conteudo or (b'%PDF-1.4\n' + nome.encode() + bytes(range(256)) + uuid.uuid4().bytes)
    texto = f'Documento ficticio {nome} para o teste do pacote de documentos, sem palavras de classificacao automatica.'
    dados = {'nome_arquivo': nome, 'mime_type': mime, 'ano_calendario': ano, 'texto_extraido': texto}
    doc = chamar(dsn, USUARIO_D, 'select financeiro.enviar_comprovante(%s, %s::jsonb, %s, %s)',
                 (EMPRESA, json.dumps(dados), base64.b64encode(conteudo).decode(), str(uuid.uuid4())))['comprovante_id']
    if campos:
        sql(dsn, 'update public.ir_comprovante set ' + ', '.join(f'{k} = %s' for k in campos) + ' where id = %s', (*campos.values(), doc))
    if metadados:
        chamar(dsn, USUARIO_D, 'select financeiro.salvar_metadata_empresarial(%s, %s, %s::jsonb, %s)',
               (EMPRESA, doc, json.dumps(metadados), str(uuid.uuid4())))
    ENVIADOS[doc] = conteudo
    return doc


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    with ClusterLocal(PG_BIN, tmp_path_factory.mktemp('zipdocs')) as c:
        c.preparar(contas=False)
        conn = c.conectar()
        with conn.cursor() as cur:
            semear_recorrencias(cur)
            semear_empresa_vazia(cur)
        conn.close()
        dsn = c.dsn()
        atribuir(dsn, EMPRESA)
        atribuir(dsn, 'PESSOAL')
        cat = sql(dsn, "insert into public.ir_categoria (nome, descricao, dedutivel, ativo, ordem, tipo_contexto, natureza, created_at, updated_at) "
                       "values ('Servicos tomados (ficticia)', 'Categoria ficticia', false, true, 90, 'EMPRESA', 'DESPESA_OPERACIONAL', now(), now()) "
                       'returning id')[0]['id']
        hoje = date.today()
        nf = enviar(dsn, 'Nota Fiscal nº 123 - São José.pdf', {
            'prestador_nome': 'Fornecedor Fictício & Cia: "Ação"/Sul', 'prestador_cpf_cnpj': '22.222.222/0001-22', 'valor': '300.00',
            'data_documento': date(ANO, 4, 2), 'categoria_ir_id': cat, 'status': 'VALIDADO', 'observacoes': 'nota (ficticia)'},
            {'tipo_documental': 'NOTA_FISCAL_RECEBIDA', 'categoria_documental': 'SERVICO_TOMADO', 'numero_documento': '123',
             'observacoes': 'conferida (ficticia)'})
        pix = enviar(dsn, 'comprovante.pdf', {'prestador_nome': 'Provedor Ficticio', 'valor': '99.90', 'data_documento': date(ANO, 4, 12),
                                              'status': 'PENDENTE_REVISAO'},
                     {'tipo_documental': 'PAGAMENTO_REALIZADO', 'categoria_documental': 'PIX_PAGO'})
        # mesmo prestador e mesmo nome de arquivo do anterior: os nomes no pacote nao podem colidir
        enviar(dsn, 'comprovante.pdf', {'prestador_nome': 'Provedor Ficticio', 'valor': '99.90', 'data_documento': date(ANO, 5, 12),
                                        'status': 'VALIDADO'},
               {'tipo_documental': 'PAGAMENTO_REALIZADO', 'categoria_documental': 'PIX_PAGO'})
        alvara = enviar(dsn, 'alvara.png', {'prestador_nome': None, 'valor': None, 'data_documento': date(ANO, 1, 15), 'status': 'IMPORTADO'},
               {'tipo_documental': 'DOCUMENTO_OBRIGATORIO', 'categoria_documental': 'ALVARA_FUNCIONAMENTO', 'orgao_emissor': 'Prefeitura (ficticia)',
                'data_emissao': date(ANO, 1, 15).isoformat(), 'data_validade': (hoje + timedelta(days=400)).isoformat(), 'obrigatorio': True},
               conteudo=b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 3, mime='image/png')
        # nome gravado sem extensao (o envio exige extensao): no pacote a extensao vem do tipo do arquivo
        sql(dsn, "update public.ir_comprovante_arquivo set nome_arquivo = 'alvara' where comprovante_id = %s", (alvara,))
        enviar(dsn, 'contrato social.PDF', {'prestador_nome': 'Junta Comercial (ficticia)', 'valor': None, 'data_documento': date(ANO, 2, 1)},
               {'tipo_documental': 'DOCUMENTO_SOCIETARIO', 'categoria_documental': 'CONTRATO_SOCIAL'})
        vencido = enviar(dsn, 'certidao.pdf', {'prestador_nome': 'Receita (ficticia)', 'data_documento': date(ANO, 3, 1)},
                         {'tipo_documental': 'CERTIDAO_LICENCA', 'categoria_documental': 'CERTIDAO_FEDERAL',
                          'data_validade': (hoje - timedelta(days=5)).isoformat()})
        sem_arquivo = enviar(dsn, 'perdido.pdf', {'prestador_nome': 'Documento sem arquivo (ficticio)', 'valor': '10.00',
                                                  'data_documento': date(ANO, 6, 1)},
                             {'tipo_documental': 'CONTABIL_FISCAL', 'categoria_documental': 'BALANCETE'})
        sql(dsn, 'delete from public.ir_comprovante_arquivo where comprovante_id = %s', (sem_arquivo,))
        ENVIADOS.pop(sem_arquivo)
        # vinculos: a nota com uma conta a pagar (validado) e o Pix aguardando o contador
        for nome, valor, doc in (('Aluguel sala (teste)', '300.00', nf), ('Internet (teste)', '99.90', pix)):
            chamar(dsn, USUARIO_D, 'select financeiro.criar_despesa(%s, %s::jsonb, %s)', (EMPRESA, json.dumps({
                'nome': nome, 'valor': valor, 'categoria_id': 951, 'data_vencimento': date(ANO, hoje.month, 10).isoformat()}), str(uuid.uuid4())))
            conta = sql(dsn, 'select id from public.conta where perfil_financeiro_id = %s and descricao = %s', (EMPRESA, nome))[0]['id']
            chamar(dsn, USUARIO_D, 'select financeiro.vincular_saida_documento(%s, %s::jsonb)',
                   (EMPRESA, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': conta, 'comprovante_id': doc})))
        sql(dsn, "update public.ir_comprovante_vinculo set status_lastro = 'AGUARDANDO_CONTADOR', resumo_entidade = null where comprovante_id = %s", (pix,))
        # documento de outro ano, sem metadados gravados (classificacao inferida)
        enviar(dsn, 'avulso.pdf', {'prestador_nome': 'Avulso (ficticio)', 'valor': '5.00', 'data_documento': date(ANO - 1, 7, 1)}, None, ano=ANO - 1)
        # documento do perfil Pessoal (outro usuario): nunca pode entrar no pacote da Empresa
        chamar(dsn, USUARIO_A, 'select financeiro.enviar_comprovante(%s, %s::jsonb, %s, %s)',
               (PESSOAL, json.dumps({'nome_arquivo': 'pessoal.pdf', 'mime_type': 'application/pdf', 'ano_calendario': ANO,
                                     'texto_extraido': 'Documento ficticio pessoal para o teste de isolamento do pacote de documentos.'}),
                base64.b64encode(b'%PDF-1.4\npessoal' + uuid.uuid4().bytes).decode(), str(uuid.uuid4())))
        yield {'dsn': dsn, 'vencido': vencido, 'sem_arquivo': sem_arquivo, 'nf': nf}


def planilha(conteudo):
    wb = openpyxl.load_workbook(BytesIO(conteudo))
    saida = {}
    for ws in wb.worksheets:
        celulas = [c for linha in ws.iter_rows() for c in linha]
        saida[ws.title] = {
            'valores': [[c.value or None for c in linha] for linha in ws.iter_rows()],  # '' e celula vazia sao o mesmo conteudo
            'formatos': {c.coordinate: c.number_format for c in celulas if isinstance(c.value, (int, float))},
            'cabecalho': [(c.font.b, c.font.color.rgb if c.font.color else None, str(c.fill.fgColor.rgb).upper(), c.alignment.horizontal)
                          for c in ws[1]],
            'congelado': ws.freeze_panes, 'filtro': ws.auto_filter.ref,
            'larguras': {k: d.width for k, d in ws.column_dimensions.items() if d.width},
        }
    return saida


def abrir(hexa):
    z = zipfile.ZipFile(BytesIO(bytes.fromhex(hexa)))
    assert z.testzip() is None
    return z


def conferir(flask, novo):
    assert flask['status'] == 200, flask
    assert 'erro' not in novo, novo
    assert novo['nome'] in flask['nome']
    zf, zn = abrir(flask['hex']), abrir(novo['hex'])
    assert zn.namelist() == zf.namelist() and zn.namelist()[0] == 'indice_documentos.xlsx'  # mesma lista, mesma ordem, mesmas pastas
    for nome in zf.namelist()[1:]:
        assert zn.read(nome) == zf.read(nome), nome  # bytes de cada documento
    f, n = planilha(zf.read('indice_documentos.xlsx')), planilha(zn.read('indice_documentos.xlsx'))
    assert list(n) == list(f) == ['Indice', 'Resumo']
    for aba in f:
        for chave in f[aba]:
            assert n[aba][chave] == f[aba][chave], (aba, chave, f[aba][chave], n[aba][chave])
    return zn, n


CONSULTAS = [{'ano': str(ANO)}, {'ano': str(ANO), 'tipo_documental': 'PAGAMENTO_REALIZADO'}, {'ano': str(ANO), 'busca': 'ficticio'},
             {'ano': str(ANO), 'mes': '4'}, {'ano': str(ANO), 'status': 'VALIDADO'}, {'ano': str(ANO), 'validade': 'VENCIDOS'},
             {'ano': str(ANO), 'obrigatorio': 'sim'}, {'ano': str(ANO), 'categoria_documental': 'CONTRATO_SOCIAL'},
             {'ano': str(ANO), 'status_documental': 'VENCIDO'}, {'ano': str(ANO), 'status': 'VENCIDO'}]


def test_pacote_igual_ao_do_flask_em_lista_pastas_bytes_e_indice(base):
    dsn = base['dsn']
    antes = resumo_tabelas(dsn)
    flask = pelo_flask(dsn, EMPRESA, ['/api/ir/documentos-empresa/exportar-zip?' + urlencode(f) for f in CONSULTAS])
    novo = pelo_novo([pedido(dsn, f) for f in CONSULTAS])
    lidos = [conferir(f, n) for f, n in zip(flask, novo)]
    pacote, indice = lidos[0]
    nomes = pacote.namelist()
    assert len(nomes) == 7  # indice + 6 arquivos (o documento sem arquivo fica so no indice)
    pastas = {n.split('/')[0] for n in nomes[1:]}
    assert pastas == {'notas_fiscais_recebidas', 'pagamentos_realizados', 'documentos_obrigatorios', 'societarios', 'certidoes_licencas'}
    # nomes seguros: so ASCII, sem caracteres de caminho, numerados (dois documentos de mesmo nome nao colidem)
    assert all(n.isascii() and not set(n) & set('\\:*?"<>| ') for n in nomes) and len(set(nomes)) == len(nomes)
    pix = sorted(n for n in nomes if n.startswith('pagamentos_realizados/'))
    assert len(pix) == 2 and all(n.endswith('_PAGAMENTO_Provedor_Ficticio.pdf') for n in pix)
    assert any(n.endswith('_NF_RECEBIDA_Fornecedor_Ficticio__Cia_Acao_Sul.pdf') for n in nomes)
    assert any(n.endswith('.png') for n in nomes) and any(n.endswith('_SOC_Junta_Comercial_ficticia.pdf') for n in nomes)
    # bytes preservados: cada arquivo do pacote e exatamente um dos enviados, e todos os enviados do ano estao la
    enviados = {hashlib.sha256(c).hexdigest() for d, c in ENVIADOS.items() if d != max(ENVIADOS)}
    assert {hashlib.sha256(pacote.read(n)).hexdigest() for n in nomes[1:]} == enviados
    # sem recompressao: o novo aplicativo guarda os arquivos como estao
    assert all(i.compress_type == zipfile.ZIP_STORED for i in pacote.infolist())
    linhas = indice['Indice']['valores']
    assert len(linhas) == 8 and linhas[0][:3] == ['Nº', 'Nome original', 'Nome no ZIP']
    sem = next(l for l in linhas if l[2] == 'Arquivo nao incluido')
    assert sem[3] == 'Documento sem arquivo (ficticio)' and sem[15].startswith('Arquivo nao encontrado ou indisponivel')
    por_nome = {l[2]: l for l in linhas[1:]}
    nf = next(l for k, l in por_nome.items() if '_NF_RECEBIDA_' in k)
    assert (nf[4], nf[5], nf[11], nf[13], nf[14]) == ('Nota fiscal recebida', 'Servico tomado', 300.0, 'VALIDADO', 'Aluguel sala (teste)')
    assert nf[15] == 'conferida (ficticia); nota (ficticia)' and indice['Indice']['formatos'][f'L{linhas.index(nf) + 1}'] == 'R$ #,##0.00'
    aguardando = next(l for l in linhas[1:] if l[13] == 'AGUARDANDO_CONTADOR')
    assert aguardando[14].startswith('CONTA #')  # sem resumo gravado: tipo e id da entidade
    resumo = {l[0]: l[1] for l in indice['Resumo']['valores'] if l[0]}
    assert resumo['Total de documentos'] == 7 and resumo['Total com lastro'] == 1 and resumo['Total sem lastro'] == 6
    assert resumo['Total de valor documentado'] == pytest.approx(300 + 99.90 + 99.90 + 10) and resumo['Filtros aplicados'] == f'ano={ANO}'
    assert indice['Resumo']['formatos']['B6'] == 'R$ #,##0.00' and indice['Indice']['cabecalho'][0] == (True, '00FFFFFF', '001F2937', 'center')
    # filtros: cada consulta devolve so o que pede
    assert [len(z.namelist()) - 1 for z, _ in lidos[1:]] == [2, 2, 6, 2, 1, 1, 1, 1, 1]  # busca "ficticio": os dois do provedor (o terceiro nao tem arquivo)
    assert novo[3]['nome'] == f'Documentos_Empresa_{ANO}_04_Contador.zip' and novo[0]['nome'] == f'Documentos_Empresa_{ANO}_Contador.zip'
    assert 'certidoes_licencas/' in lidos[5][0].namelist()[1] and lidos[8][0].namelist() == lidos[9][0].namelist()
    assert resumo_tabelas(dsn) == antes  # montar o pacote nao altera nenhuma tabela


def test_pacote_sem_documentos_e_recusado_como_no_flask(base):
    flask = pelo_flask(base['dsn'], EMPRESA, ['/api/ir/documentos-empresa/exportar-zip?ano=1999'])[0]
    novo = pelo_novo([pedido(base['dsn'], {'ano': '1999'})])[0]
    assert flask['status'] == 400 and novo == {'erro': flask['erro']['error']} == {'erro': 'Nenhum documento encontrado para os filtros selecionados.'}


def test_documento_sem_metadados_gravados_usa_a_classificacao_do_novo_aplicativo(base):
    """Unica diferenca de conteudo em relacao ao Flask, ja homologada na tela (FIN-MIGRACAO-LASTRO-EMPRESA-01): documento sem
    classificacao gravada aparece como "Nao classificado" (no Flask, "Outro" / "Sem categoria"). O resto e igual."""
    filtros = {'ano': str(ANO - 1)}
    flask = pelo_flask(base['dsn'], EMPRESA, ['/api/ir/documentos-empresa/exportar-zip?' + urlencode(filtros)])[0]
    novo = pelo_novo([pedido(base['dsn'], filtros)])[0]
    zf, zn = abrir(flask['hex']), abrir(novo['hex'])
    assert zn.namelist() == zf.namelist() == ['indice_documentos.xlsx', 'outros/001_DOC_Avulso_ficticio.pdf']
    assert zn.read(zn.namelist()[1]) == zf.read(zf.namelist()[1])
    f, n = planilha(zf.read('indice_documentos.xlsx')), planilha(zn.read('indice_documentos.xlsx'))
    diferentes = [(i, a, b) for i, (a, b) in enumerate(zip(f['Indice']['valores'][1], n['Indice']['valores'][1])) if a != b]
    assert diferentes == [(4, 'Outro', 'Não classificado'), (5, 'Sem categoria', 'Não classificado')]


def test_integridade_volume_e_falhas_nao_geram_pacote(base):
    dsn = base['dsn']
    bom = pedido(dsn, {'ano': str(ANO)})
    alvo = str(base['nf'])
    # 1) conteudo diferente do registrado (um byte trocado): SHA-256 nao confere
    trocado = json.loads(json.dumps(bom))
    dados = bytearray(bytes.fromhex(trocado['arquivos'][alvo]))
    dados[len(dados) // 2] ^= 0xFF
    trocado['arquivos'][alvo] = bytes(dados).hex()
    # 2) arquivo truncado: tamanho nao confere
    truncado = json.loads(json.dumps(bom))
    truncado['arquivos'][alvo] = truncado['arquivos'][alvo][:-20]
    # 3) arquivo que nao chegou a ser lido
    faltando = json.loads(json.dumps(bom))
    del faltando['arquivos'][alvo]
    # 4) volume acima dos limites (limites reduzidos so neste pedido)
    grande = {**json.loads(json.dumps(bom)), 'limites': {'bytesNoTotal': 500}}
    arquivo_grande = {**json.loads(json.dumps(bom)), 'limites': {'bytesNoTotal': 10 ** 9, 'bytesPorArquivo': 100}}
    muitos = {**json.loads(json.dumps(bom)), 'limites': {'bytesNoTotal': 10 ** 9, 'bytesPorArquivo': 10 ** 9, 'documentos': 3}}
    r = [pelo_novo([p])[0] for p in (trocado, truncado, faltando, grande, arquivo_grande, muitos, bom)]
    assert r[0] == {'erro': 'divergencia: conteúdo diferente do registrado (SHA-256)'}
    assert r[1] == {'erro': 'divergencia: tamanho diferente do registrado'}
    assert 'não foi lido: o pacote não foi gerado' in r[2]['erro']
    assert 'limite do pacote' in r[3]['erro'] and 'limite por arquivo' in r[4]['erro'] and '7 documentos (limite: 3)' in r[5]['erro']
    assert all('hex' not in x for x in r[:6]) and 'hex' in r[6]  # nenhuma falha entrega arquivo, nem parcial
    # o hash gravado no banco e o SHA-256 do conteudo: a conferencia usa o dado real
    gravados = sql(dsn, "select encode(sha256(a.conteudo), 'hex') = a.hash_arquivo ok from public.ir_comprovante_arquivo a "
                        'join public.ir_comprovante c on c.id = a.comprovante_id where c.perfil_financeiro_id = %s', (EMPRESA,))
    assert gravados and all(x['ok'] for x in gravados)


def test_isolamento_entre_perfis_e_restricao_ao_perfil_empresa(base):
    dsn = base['dsn']
    # Flask: 403 fora do perfil Empresa, com a mesma mensagem do novo aplicativo.
    flask = pelo_flask(dsn, PESSOAL, ['/api/ir/documentos-empresa/exportar-zip'])[0]
    fonte = (ROOT / 'web' / 'src' / 'js' / 'zip-documentos.js').read_text(encoding='utf-8')
    assert flask['status'] == 403 and flask['erro']['error'] in fonte
    adaptador = (ROOT / 'web' / 'src' / 'js' / 'documentos-servico.js').read_text(encoding='utf-8')
    assert "if (estado.perfil.tipo !== 'EMPRESA') return falha(ERRO_PERFIL_ZIP, 403);" in adaptador
    # O pacote da Empresa so tem documentos da Empresa; o arquivo do perfil Pessoal nunca entra.
    documentos = pedido(dsn, {})['entrada']['documentos']
    donos = sql(dsn, 'select distinct perfil_financeiro_id p from public.ir_comprovante where id = any(%s)', ([d['id'] for d in documentos],))
    assert donos == [{'p': EMPRESA}] and len(documentos) == 8
    pessoal = sql(dsn, 'select id from public.ir_comprovante where perfil_financeiro_id = %s', (PESSOAL,))[0]['id']
    for usuario, perfil, doc in ((USUARIO_D, EMPRESA, pessoal), (USUARIO_A, PESSOAL, documentos[0]['id']), (USUARIO_D, EMPRESA, 999999)):
        with pytest.raises(psycopg2.Error) as e:  # arquivo de outro perfil ou inexistente
            chamar(dsn, usuario, 'select financeiro.arquivo_comprovante_tela(%s, %s)', (perfil, doc))
        assert e.value.diag.message_hint == 'NAO_ENCONTRADA'
    with pytest.raises(psycopg2.Error) as e:  # documento sem arquivo
        chamar(dsn, USUARIO_D, 'select financeiro.arquivo_comprovante_tela(%s, %s)', (EMPRESA, base['sem_arquivo']))
    assert e.value.diag.message_primary == 'Arquivo do comprovante nao encontrado'
    for usuario in (USUARIO_B, USUARIO_A, None):  # conta sem acesso a Empresa D; sem sessao
        for comando, args in (('select financeiro.ir_comprovantes_tela(%s, %s::jsonb, null)', (EMPRESA, '{}')),
                              ('select financeiro.arquivo_comprovante_tela(%s, %s)', (EMPRESA, documentos[0]['id']))):
            with pytest.raises(psycopg2.Error) as e:
                chamar(dsn, usuario, comando, args)
            assert e.value.pgcode == '42501', (usuario, comando)
    # nada sai do navegador: o modulo nao faz chamada de rede nem usa armazenamento
    assert not any(t in fonte for t in ('fetch(', 'XMLHttpRequest', 'localStorage', 'sessionStorage', 'indexedDB', 'http://', 'https://'))
