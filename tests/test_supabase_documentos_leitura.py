"""
Testes FIN-REG-08 (migration 20261228090000) em cluster PostgreSQL local descartavel, com arquivos FICTICIOS:
- texto lido por OCR de imagem e de PDF digitalizado guardado com a origem (antes so PDF digital) e os eventos do Flask;
- envio sem a origem continua como antes (compatibilidade com a tela atual);
- dados conferidos pelo usuario gravados na mesma transacao, com o documento PENDENTE (nunca VALIDADO nem CLASSIFICADO) e a
  Categoria IR resolvida pelo vinculo; nenhuma despesa, compra ou pagamento criado;
- arquivo repetido devolve o existente SEM aplicar a revisao (nada sobrescrito);
- recusas sem gravacao parcial: origem incompativel, modelo invalido, revisao invalida, categoria inexistente, perfil so
  leitura, outro perfil, sem sessao;
- reversao devolve a definicao anterior sem tocar nos dados.
"""
import base64
import json
import uuid

import pytest

from tests.test_supabase_integracao_1123_1126 import resumo_tabelas
from tests.test_supabase_recorrencia import ID, PG_BIN, ROOT, USUARIO_A, USUARIO_B, atribuir, chamar, cluster, copiar, sql  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

PESSOAL, EMPRESA = ID['PESSOAL'], ID['EMPRESA']
CATEGORIA = 951
REVERSAO = ROOT / 'supabase' / 'reversao' / '20261228090000_documentos_leitura_ocr_anterior.sql'
TEXTO_OCR = 'MERCADO FICTICIO LTDA\nCNPJ: 12.345.678/0001-95\nCUPOM FISCAL ELETRONICO - SAT\n15/11/2026\nTOTAL R$ 40,00'


def png(marca):
    return b'\x89PNG\r\n\x1a\n' + f'imagem ficticia {marca} '.encode() * 20


def pdf(marca):
    return b'%PDF-1.4\n% ficticio ' + marca.encode() + b'\n' + b'0' * 200


def enviar(dsn, conteudo, nome, usuario=USUARIO_A, perfil=PESSOAL, chave=None, **dados):
    corpo = {'nome_arquivo': nome, 'ano_calendario': 2026, **dados}
    return chamar(dsn, usuario, 'select financeiro.enviar_comprovante(%s, %s::jsonb, %s, %s)',
                  (perfil, json.dumps(corpo), base64.b64encode(conteudo).decode(), chave or str(uuid.uuid4())))


def doc(dsn, i):
    return sql(dsn, 'select status, texto_extraido, origem_classificacao, observacoes, prestador_nome, prestador_cpf_cnpj, valor, data_documento, '
                    'categoria_id, categoria_ir_id, dedutivel, ano_calendario from public.ir_comprovante where id = %s', (i,))[0]


def eventos(dsn, i):
    return [e['tipo_evento'] for e in sql(dsn, 'select tipo_evento from public.ir_comprovante_evento where comprovante_id = %s order by id', (i,))]


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


@pytest.fixture
def banco(cluster):  # noqa: F811
    dsn = copiar(cluster)
    atribuir(dsn, 'PESSOAL')
    atribuir(dsn, 'PERFIL_B')
    return dsn


def test_texto_de_ocr_guardado_com_a_origem_e_eventos(banco):
    img = enviar(banco, png('a'), 'cupom.png', texto_extraido=TEXTO_OCR, texto_origem='OCR_IMAGEM', leitura='CUPOM_FISCAL')['comprovante_id']
    dig = enviar(banco, pdf('b'), 'digitalizado.pdf', texto_extraido=TEXTO_OCR + ' pagina digitalizada', texto_origem='OCR_PDF')['comprovante_id']
    nfse = enviar(banco, pdf('c'), 'nfse.pdf', texto_extraido=TEXTO_OCR + ' prefeitura', texto_origem='TEXTO_PDF', leitura='NFSE_GOIANIA')['comprovante_id']
    d = doc(banco, img)
    assert (d['status'], d['texto_extraido'], d['origem_classificacao']) == ('PENDENTE_REVISAO', TEXTO_OCR, 'OCR_IMAGEM')
    assert d['observacoes'].startswith('Texto lido por OCR no navegador. Confira valor, data e CPF/CNPJ')
    assert d['valor'] is None and d['prestador_nome'] is None  # a leitura so guarda o texto: nenhum campo preenchido
    assert eventos(banco, img) == ['IMPORTADO', 'TEXTO_EXTRAIDO_OCR', 'CUPOM_FISCAL_DETECTADO']
    assert doc(banco, dig)['origem_classificacao'] == 'OCR_PDF' and eventos(banco, dig) == ['IMPORTADO', 'TEXTO_EXTRAIDO_OCR']
    assert doc(banco, nfse)['origem_classificacao'] == 'TEXTO_PDF' and eventos(banco, nfse) == ['IMPORTADO', 'TEXTO_EXTRAIDO', 'TEXTO_EXTRAIDO']
    assert sql(banco, "select count(*) n from public.ir_comprovante where status in ('VALIDADO', 'CLASSIFICADO')")[0]['n'] == 0


def test_envio_sem_origem_continua_como_antes(banco):
    texto = 'NOTA FISCAL DE SERVICO ficticia prestador Clinica Ficticia valor 150,75 data 08/03/2027'
    com = enviar(banco, pdf('d'), 'nota.pdf', texto_extraido=texto)['comprovante_id']
    imagem = enviar(banco, png('e'), 'foto.png', texto_extraido=texto)['comprovante_id']  # imagem sem a origem: texto ignorado
    assert doc(banco, com)['origem_classificacao'] == 'TEXTO_PDF' and eventos(banco, com) == ['IMPORTADO', 'TEXTO_EXTRAIDO']
    d = doc(banco, imagem)
    assert d['texto_extraido'] is None and d['observacoes'].startswith('Arquivo armazenado sem texto legivel')
    assert eventos(banco, imagem) == ['IMPORTADO', 'PENDENTE_REVISAO']
    curto = enviar(banco, png('f'), 'curta.png', texto_extraido='pouco texto', texto_origem='OCR_IMAGEM')['comprovante_id']
    assert doc(banco, curto)['texto_extraido'] is None  # abaixo do minimo de 50 caracteres: revisao manual


def test_dados_conferidos_gravados_juntos_sem_validar_nem_gerar_financeiro(banco):
    sql(banco, "insert into public.ir_categoria (id, nome, descricao, dedutivel, ativo, ordem, tipo_contexto, natureza, created_at, updated_at) "
               "values (9901, 'Saude (ficticia)', 'x', true, true, 90, 'PESSOAL', 'DESPESA_DEDUTIVEL', now(), now())")
    sql(banco, 'insert into public.ir_categoria_despesa (perfil_financeiro_id, categoria_ir_id, categoria_id, ativo, created_at, updated_at) '
               'values (%s, 9901, %s, true, now(), now())', (PESSOAL, CATEGORIA))
    antes = resumo_tabelas(banco)
    revisao = {'data_documento': '2026-11-15', 'prestador_nome': 'Mercado Ficticio LTDA', 'prestador_cpf_cnpj': '12.345.678/0001-95',
               'valor': '40.00', 'ano_calendario': 2026, 'categoria_id': CATEGORIA, 'observacoes': 'conferido no celular'}
    r = enviar(banco, png('g'), 'cupom.png', texto_extraido=TEXTO_OCR, texto_origem='OCR_IMAGEM', leitura='CUPOM_FISCAL', revisao=revisao)
    d = doc(banco, r['comprovante_id'])
    assert r['duplicado'] is False and d['status'] == 'PENDENTE_REVISAO'
    assert (d['prestador_nome'], d['prestador_cpf_cnpj'], str(d['valor']), str(d['data_documento']), d['categoria_id']) == \
        ('Mercado Ficticio LTDA', '12.345.678/0001-95', '40.00', '2026-11-15', CATEGORIA)
    assert (d['categoria_ir_id'], d['dedutivel'], d['observacoes'], d['texto_extraido']) == (9901, True, 'conferido no celular', TEXTO_OCR)
    assert eventos(banco, r['comprovante_id']) == ['IMPORTADO', 'TEXTO_EXTRAIDO_OCR', 'CUPOM_FISCAL_DETECTADO', 'PENDENTE_REVISAO']
    depois = resumo_tabelas(banco)
    mudaram = sorted(t for t in set(antes) | set(depois) if antes.get(t) != depois.get(t))
    # So o documento, o arquivo, os eventos e a idempotencia: nenhuma despesa, compra, movimento ou pagamento.
    assert set(mudaram) <= {'public.ir_comprovante', 'public.ir_comprovante_arquivo', 'public.ir_comprovante_evento', 'financeiro.operacao_documento'}, mudaram


def test_arquivo_repetido_nao_aplica_a_revisao(banco):
    original = enviar(banco, png('h'), 'nota.png', revisao={'prestador_nome': 'Corrigido a mao', 'valor': '10.00'})['comprovante_id']
    repetido = enviar(banco, png('h'), 'nota-de-novo.png', texto_extraido=TEXTO_OCR, texto_origem='OCR_IMAGEM',
                      revisao={'prestador_nome': 'Outro nome', 'valor': '999.00'})
    assert repetido == {'duplicado': True, 'comprovante_id': original, 'mensagem': 'Arquivo ja importado anteriormente.'}
    d = doc(banco, original)
    assert (d['prestador_nome'], str(d['valor']), d['texto_extraido']) == ('Corrigido a mao', '10.00', None)  # nada sobrescrito
    assert sql(banco, 'select count(*) n from public.ir_comprovante')[0]['n'] == 1


def test_mesma_chave_nao_duplica(banco):
    k = str(uuid.uuid4())
    a = enviar(banco, png('i'), 'a.png', chave=k, texto_extraido=TEXTO_OCR, texto_origem='OCR_IMAGEM')
    b = enviar(banco, png('i'), 'a.png', chave=k, texto_extraido=TEXTO_OCR, texto_origem='OCR_IMAGEM')
    assert b == {**a, 'repetida': True} and sql(banco, 'select count(*) n from public.ir_comprovante')[0]['n'] == 1


@pytest.mark.parametrize('arquivo, nome, dados, mensagem', [
    ('png', 'foto.png', {'texto_extraido': TEXTO_OCR, 'texto_origem': 'TEXTO_PDF'}, 'Origem da leitura invalida para este arquivo'),
    ('pdf', 'doc.pdf', {'texto_extraido': TEXTO_OCR, 'texto_origem': 'OCR_IMAGEM'}, 'Origem da leitura invalida para este arquivo'),
    ('pdf', 'doc.pdf', {'texto_extraido': TEXTO_OCR, 'texto_origem': 'IA_EXTERNA'}, 'Origem da leitura invalida para este arquivo'),
    ('pdf', 'doc.pdf', {'leitura': 'BOLETO'}, 'Modelo de documento invalido'),
    ('pdf', 'doc.pdf', {'revisao': 'texto'}, 'Dados conferidos invalidos'),
    ('pdf', 'doc.pdf', {'revisao': {'categoria_id': 987654}}, 'Categoria de Despesa nao encontrada'),
    ('pdf', 'doc.pdf', {'revisao': {'ano_calendario': 'abc'}}, 'Ano-calendario invalido'),
])
def test_recusas_sem_gravacao_parcial(banco, arquivo, nome, dados, mensagem):
    antes = resumo_tabelas(banco)
    e = erro(enviar, banco, png('j') if arquivo == 'png' else pdf('j'), nome, **dados)
    assert e.diag.message_primary == mensagem
    assert resumo_tabelas(banco) == antes  # a recusa desfaz tudo, inclusive o arquivo


def test_permissoes_e_isolamento(banco):
    # Leitor da Empresa (A le, nao gere), outro perfil, sem sessao: recusados sem gravar.
    antes = resumo_tabelas(banco)
    for usuario, perfil in ((USUARIO_A, EMPRESA), (USUARIO_B, PESSOAL), (None, PESSOAL)):
        e = erro(enviar, banco, png('k'), 'x.png', usuario=usuario, perfil=perfil, texto_extraido=TEXTO_OCR, texto_origem='OCR_IMAGEM',
                 revisao={'valor': '1.00'})
        assert e.pgcode in ('42501', 'P0001') or 'perfil' in (e.diag.message_primary or '').lower(), (usuario, perfil, e.diag.message_primary)
    assert resumo_tabelas(banco) == antes
    # Mesmo arquivo em outro perfil (B) nao e "repetido" do perfil de A: cada perfil so ve os seus.
    a = enviar(banco, png('l'), 'mesmo.png')['comprovante_id']
    b = enviar(banco, png('l'), 'mesmo.png', usuario=USUARIO_B, perfil=ID['PERFIL_B'])
    assert b['duplicado'] is False and b['comprovante_id'] != a


def test_reversao_devolve_o_comportamento_anterior_e_preserva_os_dados(banco):
    feito = enviar(banco, png('m'), 'ocr.png', texto_extraido=TEXTO_OCR, texto_origem='OCR_IMAGEM')['comprovante_id']
    sql(banco, REVERSAO.read_text(encoding='utf-8'))
    assert doc(banco, feito)['texto_extraido'] == TEXTO_OCR  # o que ja foi gravado fica
    nova = enviar(banco, png('n'), 'ocr2.png', texto_extraido=TEXTO_OCR, texto_origem='OCR_IMAGEM')['comprovante_id']
    d = doc(banco, nova)
    assert d['texto_extraido'] is None and d['observacoes'].startswith('Arquivo armazenado. Leitura automatica (OCR) nao disponivel')
