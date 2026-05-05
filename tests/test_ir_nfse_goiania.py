import io
from decimal import Decimal
from pathlib import Path

import pytest
from flask import Flask

from backend.models import (
    Categoria,
    CategoriaPalavraChave,
    IrCategoria,
    IrCategoriaDespesa,
    IrComprovante,
    db,
)
from backend.routes.ir import ir_bp
from backend.services.ir_documento_service import IrDocumentoService
from backend.services.ir_nfse_goiania_parser import eh_nfse_goiania, extrair_dados_nfse_goiania


NFSE_GOIANIA_TEXTO = """
Serie do Documento
Prefeitura Municipal de Goiania - GO Nota Fiscal de
Servico Eletronica -
Secretaria Municipal da Fazenda
NFS-e
Fone: (62) 35243335 - https://www.goiania.go.gov.br/ Numero da Nota Fiscal
12137
Dados do Prestador de Servico
Data de Geracao da NFS-e
21/10/2025 20:21:08
Laboratorio Padrao SA
Data de Competencia
Padrao Laboratorio Clinico
21/10/2025
Rua 83,444Lote: 50/52 - Quadra: F18 - Setor Sul
Cod. de Autenticidade
CEP 74083-195 - Fone: (62)3221-9000 - Goiania/GO
athaidesalves@hotmail.com BC13AD872
Inscricao Municipal 34551 - CPF/CNPJ 01.588.888/0001-98
Identificacao da Nota Fiscal Eletronica
Natureza da Operacao Numero do RPS Serie do RPS Data de Emissao do RPS
Exigivel 12152 21/10/2025
Dados do Tomador de Servicos
CNPJ/CPF : 873.674.241-49 IM :
Razao Social : HEYDSON LOPES CARDOSO
Endereco : R R 217 Numero : 15
Complemento : Bairro : ST L UNIVERSITARIO
CEP : 74603-090 Cidade/UF :Goiania/GO
Descricao dos Servicos
SERVICOS PRESTADOS EXAMES LABORATORIAIS| |Cond.Pagto.(Vencimento/Valor Liquido):21-10-2025 - R$ 130,80Unidade: 173-T 7 Pedido:
9023389 Paciente: 8070204146-HEYDSON LOPES CARDOSO Recibo: 34392
Detalhamento dos Tributos
Atividade do Municipio Aliquota Item da LC116/2003 Cod. NBS Cod. CNAE
403 - 04.03 - Hospitais, clinicas, laboratorios, sanatorios, manicomios, casas de saude, prontos-socorros, ambulatorios e congeneres. 3,50 403 8640202 -
Vl. Total dos Servicos Desconto Incondicionado Deducoes Base Calculo Base de Calculo Total do ISSQN ISSQN Retido Desconto Condicionado
R$ 130,80 R$ 0,00 R$ 0,00 R$ 130,80 R$ 4,58 Nao R$ 0,00
PIS COFINS INSS IRRF CSLL Outras Retencoes Vl. ISSQN Retido Vl. Liquido da Nota Fiscal
R$ 0,00 R$ 0,00 R$ 0,00 R$ 0,00 R$ 0,00 R$ 0,00 R$ 0,00 R$ 130,80
Consulte a autenticidade deste documento acessando o site: https://www.issnetonline.com.br/goiania/online/
"""


@pytest.fixture()
def app_context():
    base_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(base_dir / 'frontend' / 'templates'),
        static_folder=str(base_dir / 'frontend' / 'static'),
    )
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY='test',
    )
    db.init_app(app)
    app.register_blueprint(ir_bp, url_prefix='/api/ir')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _pdf_bytes(text='fixture'):
    return io.BytesIO((b'%PDF-1.4\n' + text.encode('utf-8')))


def _criar_mapeamento_exames():
    categoria = Categoria(nome='Consultas e Exames', descricao='Exames laboratoriais', ativo=True)
    ir = IrCategoria(nome='Saude', descricao='Saude', dedutivel=True, ativo=True, ordem=1)
    db.session.add_all([categoria, ir])
    db.session.flush()
    db.session.add_all([
        CategoriaPalavraChave(categoria_id=categoria.id, palavra='exames', ativo=True),
        CategoriaPalavraChave(categoria_id=categoria.id, palavra='laboratoriais', ativo=True),
        CategoriaPalavraChave(categoria_id=categoria.id, palavra='laboratorio', ativo=True),
        IrCategoriaDespesa(categoria_id=categoria.id, categoria_ir_id=ir.id, ativo=True),
    ])
    db.session.commit()
    return categoria, ir


def test_detector_e_parser_nfse_goiania_extraem_campos_reais():
    assert eh_nfse_goiania(NFSE_GOIANIA_TEXTO) is True

    dados = extrair_dados_nfse_goiania(NFSE_GOIANIA_TEXTO)

    assert dados['tipo_documento'] == 'NFS-e Goiania'
    assert dados['numero_nota'] == '12137'
    assert dados['data_documento'] == '21/10/2025'
    assert dados['data_competencia'] == '21/10/2025'
    assert dados['prestador_nome'] == 'Laboratorio Padrao SA'
    assert dados['prestador_nome'] != 'Serie do Documento'
    assert dados['prestador_cpf_cnpj'] == '01.588.888/0001-98'
    assert dados['tomador_nome'] == 'HEYDSON LOPES CARDOSO'
    assert dados['tomador_cpf'] == '873.674.241-49'
    assert dados['valor'] == Decimal('130.80')
    assert 'EXAMES LABORATORIAIS' in dados['descricao_servico']
    assert dados['ano_calendario'] == 2025


def test_upload_nfse_goiania_usa_parser_especifico_classifica_e_resolve_ir(app_context, monkeypatch):
    categoria, ir = _criar_mapeamento_exames()
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _conteudo: NFSE_GOIANIA_TEXTO))

    with app_context.test_client() as client:
        response = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_bytes(), 'notaFiscal-0916993.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )

    data = response.get_json()['data'][0]['data']['comprovante']
    comprovante = IrComprovante.query.get(data['id'])

    assert response.status_code == 200
    assert comprovante.status == 'CLASSIFICADO'
    assert comprovante.prestador_nome == 'Laboratorio Padrao SA'
    assert comprovante.prestador_nome != 'Serie do Documento'
    assert comprovante.prestador_cpf_cnpj == '01.588.888/0001-98'
    assert comprovante.tomador_nome == 'HEYDSON LOPES CARDOSO'
    assert comprovante.tomador_cpf == '873.674.241-49'
    assert comprovante.data_documento.isoformat() == '2025-10-21'
    assert float(comprovante.valor) == 130.8
    assert comprovante.categoria_id == categoria.id
    assert comprovante.categoria_ir_id == ir.id


def test_categorias_despesa_disponiveis_trazem_vinculo_ir_para_revisao(app_context):
    categoria, ir = _criar_mapeamento_exames()

    with app_context.test_client() as client:
        response = client.get('/api/ir/categorias-despesa-disponiveis')

    payload = response.get_json()
    item = next(cat for cat in payload['data'] if cat['id'] == categoria.id)

    assert response.status_code == 200
    assert payload['total'] >= 1
    assert item['nome'] == 'Consultas e Exames'
    assert item['categoria_ir_id'] == ir.id
    assert item['categoria_ir_nome'] == 'Saude'


def test_revisao_manual_preserva_categoria_ir_informada(app_context, monkeypatch):
    categoria, ir = _criar_mapeamento_exames()
    ir_manual = IrCategoria(nome='Exames', descricao='Exames', dedutivel=True, ativo=True, ordem=2)
    db.session.add(ir_manual)
    db.session.commit()
    monkeypatch.setattr(IrDocumentoService, 'extrair_texto_pdf', staticmethod(lambda _conteudo: NFSE_GOIANIA_TEXTO))

    with app_context.test_client() as client:
        upload = client.post(
            '/api/ir/comprovantes/upload',
            data={'ano_calendario': '2026', 'arquivos': (_pdf_bytes(), 'notaFiscal-0916993.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )
        comprovante_id = upload.get_json()['data'][0]['data']['comprovante']['id']
        revisao = client.put(f'/api/ir/comprovantes/{comprovante_id}', json={
            'categoria_id': categoria.id,
            'categoria_ir_id': ir_manual.id,
            'prestador_nome': 'Laboratorio Padrao SA',
            'valor': '130.80',
        })

    assert revisao.status_code == 200
    assert revisao.get_json()['data']['categoria_ir_id'] == ir_manual.id
    assert IrComprovante.query.get(comprovante_id).categoria_ir_id == ir_manual.id
