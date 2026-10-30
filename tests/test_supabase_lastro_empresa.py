"""
Testes FIN-MIGRACAO-LASTRO-EMPRESA-01 (migration 20261202090000), em cluster PostgreSQL local descartavel.

Empresa ficticia (usuario D, Empresa D) no novo aplicativo:
- classificacao automatica segura: contrato social que cita Pix NAO vira pagamento; comprovante de Pix, boleto pago e
  procuracao reconhecidos; "pixel" nao e Pix; sem evidencia = "Nao classificado";
- conteudo antes da categoria de IR (20261203090000): "Documento contabil" ou "Imposto/taxa" sem evidencia de pagamento =
  Contabil / fiscal, "Nao classificado", fora do "sem lastro"; classificacao gravada prevalece; reversao da correcao;
- "sem lastro" conta so o documento que comprova operacao financeira;
- metadados empresariais (revisao da tela): reclassificacao, regras do Flask (categoria define o tipo, datas, situacao pela
  validade), campos ausentes preservados, evento antes -> depois, auditoria com conta e hora, repeticao pela chave,
  recusas (perfil nao Empresa, escritor Flask, outra conta);
- saidas sem documento: vincular (padrao VALIDADO, pendencia desativada, sem duplicar), situacao manual, desvincular;
- vinculo com conta bancaria gravado como CONTA_BANCARIA (CONTA = conta a pagar);
- exclusao: com metadados, sem vinculo; recusada com vinculo (inclusive historico).
"""
import base64
import json
import uuid
from datetime import date, timedelta

import pytest

from tests.supabase_local import EMPRESA_D, USUARIO_D, ClusterLocal, semear_empresa_vazia, semear_recorrencias
from tests.test_supabase_recorrencia import ID, PG_BIN, USUARIO_A, atribuir, chamar, copiar, sql

psycopg2 = pytest.importorskip('psycopg2')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

EMPRESA = EMPRESA_D['id']
HOJE = date.today()
TEXTOS = {
    'contrato': 'CONTRATO SOCIAL da Empresa Ficticia Ltda. Os socios poderao movimentar contas, emitir boletos e '
                'transferencias via PIX. Procuracao anexa.',
    'pix': 'Comprovante de transferencia Pix. Pix enviado em 10/10/2026. ID da transacao E123. Valor R$ 50,00.',
    'boleto': 'Comprovante de pagamento de boleto. Linha digitavel 23790.00000. Pagamento efetuado.',
    'procuracao': 'Instrumento particular de procuracao: outorgante Empresa Ficticia, outorgado contador.',
    'pixel': 'Monitor 4K com densidade de pixel elevada, tela antirreflexo e garantia de 12 meses.',
    'pago_pix': 'Fornecedor ficticio de material de escritorio, servico pago via PIX no mesmo dia.',
    'neutro': 'Documento qualquer sem palavras reconhecidas pela classificacao automatica da empresa.',
}


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    with ClusterLocal(PG_BIN, tmp_path_factory.mktemp('lastro')) as c:
        c.preparar(contas=False)
        conn = c.conectar()
        with conn.cursor() as cur:
            semear_recorrencias(cur)
            semear_empresa_vazia(cur)
        conn.close()
        yield c


@pytest.fixture
def banco(cluster):
    dsn = copiar(cluster)
    atribuir(dsn, EMPRESA)
    atribuir(dsn, 'PESSOAL')
    return dsn


def erro(funcao, *args, **kw):
    with pytest.raises(psycopg2.Error) as e:
        funcao(*args, **kw)
    return e.value


def enviar(dsn, texto, nome='doc.pdf', perfil=EMPRESA, usuario=USUARIO_D):
    # PDF textual ficticio: o envio so guarda o texto extraido de PDF (50+ caracteres). Bytes unicos (sem duplicidade).
    conteudo = b'%PDF-1.4\n' + texto.encode() + uuid.uuid4().bytes
    dados = {'nome_arquivo': nome, 'mime_type': 'application/pdf', 'ano_calendario': HOJE.year, 'texto_extraido': texto}
    return chamar(dsn, usuario, 'select financeiro.enviar_comprovante(%s, %s::jsonb, %s, %s)',
                  (perfil, json.dumps(dados), base64.b64encode(conteudo).decode(), str(uuid.uuid4())))['comprovante_id']


def metadata(dsn, doc, usuario=USUARIO_D):
    return chamar(dsn, usuario, "select financeiro.ir_documentos_empresa_tela(%s, 'metadata', '{}'::jsonb, %s)", (EMPRESA, doc))


def resumo(dsn):
    return chamar(dsn, USUARIO_D, "select financeiro.ir_documentos_empresa_tela(%s, 'resumo', '{}'::jsonb, null)", (EMPRESA,))


def salvar(dsn, doc, dados, chave=None, perfil=EMPRESA, usuario=USUARIO_D):
    return chamar(dsn, usuario, 'select financeiro.salvar_metadata_empresarial(%s, %s, %s::jsonb, %s)',
                  (perfil, doc, json.dumps(dados), chave or str(uuid.uuid4())))


def conta_a_pagar(dsn, nome='Aluguel sala (teste)', valor='300.00'):
    dados = {'nome': nome, 'valor': valor, 'categoria_id': 951, 'data_vencimento': HOJE.replace(day=10).isoformat()}
    chamar(dsn, USUARIO_D, 'select financeiro.criar_despesa(%s, %s::jsonb, %s)', (EMPRESA, json.dumps(dados), str(uuid.uuid4())))
    return sql(dsn, 'select id from public.conta where perfil_financeiro_id = %s and descricao = %s', (EMPRESA, nome))[0]['id']


def saidas(dsn, status='TODOS'):
    return chamar(dsn, USUARIO_D, 'select financeiro.lastro_saidas_tela(%s, %s::jsonb, false)',
                  (EMPRESA, json.dumps({'ano': HOJE.year, 'status': status})))


# ---- Classificacao automatica ----

@pytest.mark.parametrize('chave, esperado', [
    ('contrato', ('DOCUMENTO_SOCIETARIO', 'CONTRATO_SOCIAL', 'Documento societario/cadastral', 'Contrato Social')),
    ('pix', ('PAGAMENTO_REALIZADO', 'PIX_PAGO', 'Pagamento realizado', 'Pix pago')),
    ('boleto', ('PAGAMENTO_REALIZADO', 'BOLETO_PAGO', 'Pagamento realizado', 'Boleto pago')),
    ('procuracao', ('PROCURACAO_REPRESENTACAO', 'REPRESENTACAO_LEGAL', 'Procuracao / representacao', 'Representacao Legal')),
    ('pago_pix', ('PAGAMENTO_REALIZADO', 'PIX_PAGO', 'Pagamento realizado', 'Pix pago')),
    ('pixel', ('OUTRO', 'SEM_CATEGORIA', 'Não classificado', 'Não classificado')),
    ('neutro', ('OUTRO', 'SEM_CATEGORIA', 'Não classificado', 'Não classificado')),
])
def test_classificacao_automatica_segura(banco, chave, esperado):
    m = metadata(banco, enviar(banco, TEXTOS[chave]))
    assert (m['tipo_documental'], m['categoria_documental'], m['tipo_documental_label'], m['categoria_documental_label']) == esperado
    assert m['origem_documental'] == 'INFERIDO'
    assert sql(banco, 'select count(*) as n from public.documento_empresarial_metadata')[0]['n'] == 0  # inferir nao grava


def test_sem_lastro_so_para_documento_financeiro(banco):
    enviar(banco, TEXTOS['contrato'])
    enviar(banco, TEXTOS['procuracao'])
    assert resumo(banco)['sem_lastro'] == 0
    pix = enviar(banco, TEXTOS['pix'])
    r = resumo(banco)
    assert (r['documentos_cadastrados'], r['sem_lastro']) == (3, 1)
    assert metadata(banco, pix)['tipo_documental'] == 'PAGAMENTO_REALIZADO'
    assert [x for x in r['checklist_empresarial'] if x['label'] == 'Contrato Social'] == [{'label': 'Contrato Social', 'status': 'ok'}]


# ---- Categoria de IR x conteudo (correcao 20261203090000) ----

def com_categoria_ir(dsn, doc, natureza):
    """Categoria de IR ficticia da Empresa com a natureza pedida, atribuida ao documento (como a revisao faria)."""
    cat = sql(dsn, "insert into public.ir_categoria (nome, descricao, dedutivel, ativo, ordem, tipo_contexto, natureza, created_at, "
                   "updated_at) values (%s, 'Categoria ficticia', false, true, 90, 'EMPRESA', %s, now(), now()) returning id",
              (f'{natureza} (ficticia) {uuid.uuid4().hex[:6]}', natureza))[0]['id']
    sql(dsn, 'update public.ir_comprovante set categoria_ir_id = %s where id = %s', (cat, doc))
    return doc


@pytest.mark.parametrize('chave, natureza, esperado', [
    # "Documento contabil" sozinho nao e pagamento: Contabil / fiscal, "Nao classificado".
    ('neutro', 'DOCUMENTO_CONTABIL', ('CONTABIL_FISCAL', 'SEM_CATEGORIA', 'Contabil / fiscal', 'Não classificado')),
    ('neutro', 'IMPOSTO_TAXA', ('CONTABIL_FISCAL', 'SEM_CATEGORIA', 'Contabil / fiscal', 'Não classificado')),
    # O conteudo decide primeiro (caso do id 4 real: contrato social com categoria de IR "Documento contabil").
    ('contrato', 'DOCUMENTO_CONTABIL', ('DOCUMENTO_SOCIETARIO', 'CONTRATO_SOCIAL', 'Documento societario/cadastral', 'Contrato Social')),
    ('procuracao', 'IMPOSTO_TAXA', ('PROCURACAO_REPRESENTACAO', 'REPRESENTACAO_LEGAL', 'Procuracao / representacao', 'Representacao Legal')),
    # Pagamento so com evidencia de transacao; imposto/taxa com evidencia = guia/taxa paga.
    ('pix', 'DOCUMENTO_CONTABIL', ('PAGAMENTO_REALIZADO', 'PIX_PAGO', 'Pagamento realizado', 'Pix pago')),
    ('boleto', 'IMPOSTO_TAXA', ('CONTABIL_FISCAL', 'GUIA_TAXA_PAGA', 'Contabil / fiscal', 'Guia/taxa paga')),
    # As demais naturezas seguem o Flask quando o texto nao reconhece nada.
    ('neutro', 'DOCUMENTO_FISCAL', ('NOTA_FISCAL_RECEBIDA', 'DESPESA_OPERACIONAL', 'Nota fiscal recebida', 'Despesa operacional')),
    ('neutro', 'PATRIMONIO_IMOBILIZADO', ('PATRIMONIO_IMOBILIZADO', 'NOTA_BEM_PATRIMONIAL', 'Patrimonio / imobilizado', 'Nota de bem patrimonial')),
])
def test_conteudo_antes_da_categoria_de_ir(banco, chave, natureza, esperado):
    m = metadata(banco, com_categoria_ir(banco, enviar(banco, TEXTOS[chave]), natureza))
    assert (m['tipo_documental'], m['categoria_documental'], m['tipo_documental_label'], m['categoria_documental_label']) == esperado
    assert m['origem_documental'] == 'INFERIDO'
    assert sql(banco, 'select count(*) as n from public.documento_empresarial_metadata')[0]['n'] == 0


def test_sem_lastro_nao_conta_contabil_nem_societario(banco):
    com_categoria_ir(banco, enviar(banco, TEXTOS['neutro']), 'DOCUMENTO_CONTABIL')
    com_categoria_ir(banco, enviar(banco, TEXTOS['contrato']), 'DOCUMENTO_CONTABIL')
    com_categoria_ir(banco, enviar(banco, TEXTOS['neutro']), 'IMPOSTO_TAXA')
    assert resumo(banco)['sem_lastro'] == 0
    com_categoria_ir(banco, enviar(banco, TEXTOS['boleto']), 'IMPOSTO_TAXA')  # guia paga: documento financeiro
    r = resumo(banco)
    assert (r['documentos_cadastrados'], r['sem_lastro']) == (4, 1)
    assert [x for x in r['checklist_empresarial'] if x['label'] == 'Contrato Social'] == [{'label': 'Contrato Social', 'status': 'ok'}]


def test_classificacao_gravada_prevalece_sobre_a_sugestao(banco):
    doc = com_categoria_ir(banco, enviar(banco, TEXTOS['pix']), 'IMPOSTO_TAXA')
    assert metadata(banco, doc)['categoria_documental'] == 'GUIA_TAXA_PAGA'
    salvar(banco, doc, {'categoria_documental': 'CONTRATO_SOCIAL'})
    com_categoria_ir(banco, doc, 'DOCUMENTO_CONTABIL')  # nova categoria de IR depois da revisao: nada muda
    m = metadata(banco, doc)
    assert (m['tipo_documental'], m['categoria_documental'], m['origem_documental']) == ('DOCUMENTO_SOCIETARIO', 'CONTRATO_SOCIAL', 'USUARIO')
    assert resumo(banco)['sem_lastro'] == 0


def test_reversao_da_correcao_devolve_a_regra_anterior(banco):
    from pathlib import Path
    neutro = com_categoria_ir(banco, enviar(banco, TEXTOS['neutro']), 'DOCUMENTO_CONTABIL')
    contrato = enviar(banco, TEXTOS['contrato'])
    conn = psycopg2.connect(banco)
    with conn, conn.cursor() as cur:
        cur.execute((Path(__file__).resolve().parent.parent / 'supabase' / 'reversao' /
                     '20261203090000_inferencia_documento_contabil_anterior.sql').read_bytes().decode('utf-8'))
    conn.close()
    assert metadata(banco, neutro)['categoria_documental'] == 'GUIA_TAXA_PAGA'  # a regra de 20261202090000
    assert metadata(banco, contrato)['categoria_documental'] == 'CONTRATO_SOCIAL'  # o resto da 20261202090000 continua


# ---- Metadados (revisao) ----

def test_reclassificar_e_editar_metadados_com_auditoria(banco):
    doc = enviar(banco, TEXTOS['neutro'])
    validade = (HOJE + timedelta(days=10)).isoformat()
    dados = {'tipo_documental': 'OUTRO', 'categoria_documental': 'CERTIDAO_FEDERAL', 'numero_documento': ' 123/2026 ',
             'orgao_emissor': 'Receita Federal', 'data_emissao': HOJE.strftime('%d/%m/%Y'), 'data_validade': validade,
             'status_documental': 'ATIVO', 'obrigatorio': True, 'renovavel': 'sim', 'alerta_dias_antes': '15',
             'responsavel_interno': 'Titular', 'origem_documental': 'USUARIO'}
    chave = str(uuid.uuid4())
    m = salvar(banco, doc, dados, chave)
    # A categoria define o tipo; situacao pela validade (10 dias = vencendo).
    assert (m['tipo_documental'], m['categoria_documental'], m['status_documental'], m['origem_documental']) == \
        ('CERTIDAO_LICENCA', 'CERTIDAO_FEDERAL', 'VENCENDO', 'USUARIO')
    gravado = sql(banco, 'select * from public.documento_empresarial_metadata where comprovante_id = %s', (doc,))
    assert len(gravado) == 1
    g = gravado[0]
    assert (g['numero_documento'], g['orgao_emissor'], g['data_emissao'], g['data_validade'].isoformat(), g['obrigatorio'],
            g['renovavel'], g['alerta_dias_antes'], g['responsavel_interno'], g['perfil_financeiro_id']) == \
        ('123/2026', 'Receita Federal', HOJE, validade, True, True, 15, 'Titular', EMPRESA)
    assert sql(banco, "select descricao from public.ir_comprovante_evento where comprovante_id = %s "
                      "and tipo_evento = 'METADATA_EMPRESARIAL_ATUALIZADA'", (doc,)) == [
        {'descricao': 'Metadados empresariais revisados pelo usuario: Não classificado / Não classificado (inferido) -> '
                      'Certidao / licenca / Certidao Federal.'}]
    auditoria = sql(banco, "select user_id::text, resultado from financeiro.operacao_documento where chave = %s", (chave,))[0]
    assert auditoria['user_id'] == USUARIO_D['id']
    assert (auditoria['resultado']['antes']['tipo_documental'], auditoria['resultado']['depois']['categoria_documental']) == \
        ('OUTRO', 'CERTIDAO_FEDERAL')
    # Repeticao com a mesma chave: nada novo. Tags/observacoes gravadas nao somem quando a tela nao as envia.
    assert salvar(banco, doc, dados, chave)['repetida'] is True
    sql(banco, "update public.documento_empresarial_metadata set tags = 'manter', observacoes = 'obs' where comprovante_id = %s", (doc,))
    salvar(banco, doc, {**dados, 'categoria_documental': 'CONTRATO_SOCIAL', 'data_validade': ''})
    g = sql(banco, 'select * from public.documento_empresarial_metadata where comprovante_id = %s', (doc,))[0]
    assert (g['tipo_documental'], g['categoria_documental'], g['status_documental'], g['tags'], g['observacoes']) == \
        ('DOCUMENTO_SOCIETARIO', 'CONTRATO_SOCIAL', 'ATIVO', 'manter', 'obs')
    assert sql(banco, "select count(*) as n from public.ir_comprovante_evento where comprovante_id = %s "
                      "and tipo_evento = 'METADATA_EMPRESARIAL_ATUALIZADA'", (doc,))[0]['n'] == 2


def test_metadados_recusas(banco, cluster):
    doc = enviar(banco, TEXTOS['neutro'])
    assert erro(salvar, banco, doc, {}, usuario=USUARIO_A).pgcode == '42501'  # conta sem gestao da Empresa
    pessoal = enviar(banco, TEXTOS['neutro'], perfil=ID['PESSOAL'], usuario=USUARIO_A)
    e = erro(salvar, banco, pessoal, {}, perfil=ID['PESSOAL'], usuario=USUARIO_A)
    assert (e.pgcode, e.diag.message_primary) == ('42501', 'Central de Documentos Empresariais disponivel apenas no perfil Empresa.')
    e = erro(salvar, banco, pessoal, {})  # documento de outro perfil
    assert e.diag.message_hint == 'NAO_ENCONTRADA'
    flask = copiar(cluster)  # Empresa D ainda sem escritor NOVO
    e = erro(salvar, flask, 1, {})
    assert e.diag.message_hint == 'SISTEMA_FLASK'


# ---- Saidas sem documento ----

def test_vincular_saida_desvincular_e_situacao(banco):
    conta = conta_a_pagar(banco)
    outra = conta_a_pagar(banco, 'Internet (teste)', '99.90')
    pix = enviar(banco, TEXTOS['pix'])
    situacao = {(s['tipo_entidade'], s['entidade_id']): s['status_lastro'] for s in saidas(banco)}
    assert situacao[('CONTA', conta)] == 'SEM_DOCUMENTO'

    # Situacao manual: aguardando contador; depois volta a sem documento.
    r = chamar(banco, USUARIO_D, 'select financeiro.marcar_status_saida(%s, %s::jsonb)',
               (EMPRESA, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': str(outra), 'status_lastro': 'AGUARDANDO_CONTADOR',
                                     'natureza': 'DESPESA_OPERACIONAL', 'observacoes': 'conferir'})))
    assert (r['status_lastro'], r['ativo']) == ('AGUARDANDO_CONTADOR', True)
    assert {(s['entidade_id']): s['status_lastro'] for s in saidas(banco)}[outra] == 'AGUARDANDO_CONTADOR'

    # Vincular: padrao VALIDADO, pendencia da saida desativada, saida sai da lista de pendentes.
    v = chamar(banco, USUARIO_D, 'select financeiro.vincular_saida_documento(%s, %s::jsonb)',
               (EMPRESA, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': outra, 'comprovante_id': pix})))
    assert (v['tipo_entidade'], v['entidade_id'], v['status_lastro'], v['resumo_entidade']) == ('CONTA', outra, 'VALIDADO', 'Internet (teste)')
    assert sql(banco, 'select ativo from public.lastro_financeiro_pendencia where entidade_id = %s', (outra,)) == [{'ativo': False}]
    assert outra not in [s['entidade_id'] for s in saidas(banco, 'PENDENTES')]
    assert resumo(banco)['sem_lastro'] == 0  # o comprovante de Pix agora tem lastro
    e = erro(chamar, banco, USUARIO_D, 'select financeiro.vincular_saida_documento(%s, %s::jsonb)',
             (EMPRESA, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': outra, 'comprovante_id': pix})))
    assert e.diag.message_hint == 'DUPLICADO'
    e = erro(chamar, banco, USUARIO_D, 'select financeiro.marcar_status_saida(%s, %s::jsonb)',
             (EMPRESA, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': outra, 'status_lastro': 'PENDENTE'})))
    assert e.diag.message_primary == 'Saida ja possui documento vinculado'

    # Desvincular (inativa, historico preservado): a saida volta a sem documento.
    chamar(banco, USUARIO_D, 'select financeiro.remover_vinculo_documento(%s, %s, %s)', (EMPRESA, pix, v['id']))
    assert {(s['entidade_id']): s['status_lastro'] for s in saidas(banco)}[outra] == 'SEM_DOCUMENTO'

    # Saida de outro perfil: recusada.
    alheia = sql(banco, 'select id from public.conta where perfil_financeiro_id = %s limit 1', (ID['PESSOAL'],))
    if alheia:
        e = erro(chamar, banco, USUARIO_D, 'select financeiro.vincular_saida_documento(%s, %s::jsonb)',
                 (EMPRESA, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': alheia[0]['id'], 'comprovante_id': pix})))
        assert e.diag.message_primary == 'Recurso nao encontrado no perfil financeiro ativo'


def test_vinculo_com_conta_bancaria_nao_documenta_conta_a_pagar(banco):
    conta = conta_a_pagar(banco)
    chamar(banco, USUARIO_D, 'select financeiro.criar_conta_bancaria(%s, %s::jsonb, %s)', (EMPRESA, json.dumps({
        'nome': 'Conta Empresa (teste)', 'instituicao': 'Banco ficticio', 'tipo': 'Conta Corrente', 'saldo_inicial': 0,
        'cor_display': '#0f766e'}), str(uuid.uuid4())))
    banco_id = sql(banco, 'select id from public.conta_bancaria where perfil_financeiro_id = %s', (EMPRESA,))[0]['id']
    doc = enviar(banco, TEXTOS['pix'])
    chamar(banco, USUARIO_D, 'select financeiro.criar_vinculo_documento(%s, %s, %s::jsonb)',
           (EMPRESA, doc, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': banco_id})))
    assert sql(banco, 'select tipo_entidade, entidade_id from public.ir_comprovante_vinculo where comprovante_id = %s', (doc,)) == \
        [{'tipo_entidade': 'CONTA_BANCARIA', 'entidade_id': banco_id}]
    # Mesmo que a conta bancaria e a conta a pagar tenham o mesmo numero, a saida continua sem documento.
    sql(banco, "update public.ir_comprovante_vinculo set entidade_id = %s where comprovante_id = %s", (conta, doc))
    assert {(s['tipo_entidade'], s['entidade_id']): s['status_lastro'] for s in saidas(banco)}[('CONTA', conta)] == 'SEM_DOCUMENTO'


# ---- Exclusao ----

def test_excluir_documento_com_metadados_e_recusas(banco):
    doc = enviar(banco, TEXTOS['contrato'])
    salvar(banco, doc, {'categoria_documental': 'CONTRATO_SOCIAL'})
    assert chamar(banco, USUARIO_D, 'select financeiro.excluir_comprovante(%s, %s)', (EMPRESA, doc)) == {'comprovante_id': doc, 'excluido': True}
    for tabela in ('ir_comprovante', 'ir_comprovante_arquivo', 'ir_comprovante_evento', 'documento_empresarial_metadata'):
        coluna = 'id' if tabela == 'ir_comprovante' else 'comprovante_id'
        assert sql(banco, f'select count(*) as n from public.{tabela} where {coluna} = %s', (doc,))[0]['n'] == 0, tabela

    conta = conta_a_pagar(banco)
    pix = enviar(banco, TEXTOS['pix'])
    v = chamar(banco, USUARIO_D, 'select financeiro.vincular_saida_documento(%s, %s::jsonb)',
               (EMPRESA, json.dumps({'tipo_entidade': 'CONTA', 'entidade_id': conta, 'comprovante_id': pix})))
    assert erro(chamar, banco, USUARIO_D, 'select financeiro.excluir_comprovante(%s, %s)', (EMPRESA, pix)).diag.message_hint == 'COM_VINCULOS'
    chamar(banco, USUARIO_D, 'select financeiro.remover_vinculo_documento(%s, %s, %s)', (EMPRESA, pix, v['id']))
    # Vinculo inativo e historico: continua preservado.
    assert erro(chamar, banco, USUARIO_D, 'select financeiro.excluir_comprovante(%s, %s)', (EMPRESA, pix)).diag.message_hint == 'COM_VINCULOS'
    assert erro(chamar, banco, USUARIO_A, 'select financeiro.excluir_comprovante(%s, %s)', (EMPRESA, pix)).pgcode == '42501'


def test_reversao_devolve_o_comportamento_anterior(banco):
    from pathlib import Path
    doc = enviar(banco, TEXTOS['contrato'])
    conn = psycopg2.connect(banco)
    with conn, conn.cursor() as cur:
        cur.execute((Path(__file__).resolve().parent.parent / 'supabase' / 'reversao' / '20261202090000_lastro_empresa_anterior.sql')
                    .read_text(encoding='utf-8'))
    conn.close()
    assert metadata(banco, doc)['categoria_documental'] == 'PIX_PAGO'  # a inferencia antiga ("pix" antes de "contrato")
    restantes = sql(banco, "select proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'financeiro' "
                           "and proname in ('salvar_metadata_empresarial', 'vincular_saida_documento', 'marcar_status_saida', "
                           "'inferir_documento_empresa', 'documento_exige_lastro', 'lastro_saida_entidade', 'exigir_documentos_empresa', 'doc_data')")
    assert restantes == []
