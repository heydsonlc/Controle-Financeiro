from io import BytesIO

from backend.services.importacao_cartao_unificado_service import ImportacaoCartaoUnificadoService
from backend.services.parsers.importacao_pdf_caixa_parser import parse_texto_caixa


class DummyUpload:
    def __init__(self, filename, content):
        self.filename = filename
        self.stream = BytesIO(content)


def test_detector_identifica_formatos_basicos():
    assert ImportacaoCartaoUnificadoService.detectar_tipo_arquivo(
        DummyUpload('fatura.pdf', b'%PDF-1.7\n'),
        'automatico',
    ) == 'pdf'
    assert ImportacaoCartaoUnificadoService.detectar_tipo_arquivo(
        DummyUpload('fatura.xlsx', b'PK\x03\x04'),
        'automatico',
    ) == 'xlsx'
    assert ImportacaoCartaoUnificadoService.detectar_tipo_arquivo(
        DummyUpload('fatura.csv', b'date,title,amount\n'),
        'automatico',
    ) == 'csv'


def test_parser_pdf_caixa_extrai_metadados_lancamentos_e_creditos():
    paginas = [
        """
        VENCIMENTO
        05/05/2026
        VALOR TOTAL DESTA FATURA
        R$ 85,90
        """,
        """
        Demonstrativo
        Data Descricao Cidade/Pais Valor U$$ Credito/Debito
        13/04 AJUSTE CREDITO PARC. LOJISTA 0,02C
        CLIENTE TESTE (Cartao 0548)
        ANUIDADE
        ANUIDADE DIFERENCIADA TIT 05/ 12 17,25D
        COMPRAS (Cartao 0548)
        28/03 DM*Roku SAO PAULO 66,90D
        COMPRAS PARCELADAS (Cartao 0548)
        06/10 BRASIL PARAL*Brpa 07 DE 12 SAO PAULO 19,00D
        Total COMPRAS PARCELADAS 19,00D
        Total final (cartao 0548) 103,15D
        Valor total desta fatura R$ 85,90 D
        """,
        "conteudo informativo sem demonstrativo",
    ]

    resultado = parse_texto_caixa(paginas, competencia='2026-05', arquivo_nome='fixture.pdf')

    assert resultado['fatura']['emissor'] == 'Caixa'
    assert resultado['fatura']['vencimento'] == '2026-05-05'
    assert resultado['fatura']['valor_total'] == 85.90
    assert resultado['fatura']['cartoes_detectados'] == ['0548']

    linhas = resultado['linhas']
    assert any(linha['tipo_movimento'] == 'credito' and linha['status'] == 'ignorado' for linha in linhas)
    assert any(linha['grupo'] == 'ANUIDADE' and linha['parcela_atual'] == 5 for linha in linhas)
    assert any(linha['descricao_exibida'].startswith('DM*Roku') and linha['valor'] == 66.90 for linha in linhas)

    parcelada = next(linha for linha in linhas if linha['descricao_exibida'].startswith('BRASIL PARAL'))
    assert parcelada['data_compra'] == '2025-10-06'
    assert parcelada['parcela_atual'] == 7
    assert parcelada['total_parcelas'] == 12
