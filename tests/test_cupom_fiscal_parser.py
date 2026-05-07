"""
Testes CUPOM-FISCAL-1 — parser basico de cupom fiscal.
"""
from decimal import Decimal

import pytest

from backend.services.cupom_fiscal_parser import (
    eh_cupom_fiscal,
    extrair_dados_cupom_fiscal,
)

# ---------------------------------------------------------------------------
# Textos de fixture
# ---------------------------------------------------------------------------

TEXTO_NFCE = """
SUPERMERCADO VALE VERDE LTDA
CNPJ: 12.345.678/0001-90
Rua das Flores, 100 - Goiania/GO

NFC-e - Nota Fiscal de Consumidor Eletronica
Emissao: 05/05/2026  10:34:22

CNPJ do consumidor: 000.000.000-00

Valor Total   R$ 145,80
Forma de pagamento: Pix

Chave de acesso:
52260512345678000190650010000012341234567891

QRCode: https://nfce.sefaz.example/...
"""

TEXTO_SAT = """
LOJA DO JOAO ME
CNPJ 98.765.432/0001-11
Data: 03/05/2026  08:22:10

CF-e SAT - Cupom Fiscal Eletronico
Numero: 000456

TOTAL R$ 89,50
Troco: R$ 10,50
"""

TEXTO_SEM_PONTUACAO_CNPJ = """
Farmacia Boa Saude
CNPJ 45678901000123
Data 01/05/2026

Cupom Fiscal
Valor a pagar R$ 38,90
"""

TEXTO_GENERICO = """
Prefeitura Municipal de Goiania
Nota Fiscal de Servico Eletronica - NFS-e
Dados do Prestador de Servico
Clinica Medica ABC Ltda
CPF/CNPJ 11.222.333/0001-44
Data de Competencia
15/04/2026
Vl. Total dos Servicos R$ 500,00
"""

TEXTO_SEM_CUPOM = """
Contrato de prestacao de servicos
Cliente: Empresa XYZ
Vigencia: 01/01/2026 a 31/12/2026
Valor mensal: R$ 2.000,00
"""


# ---------------------------------------------------------------------------
# 1. Detecta NFC-e por termos
# ---------------------------------------------------------------------------
def test_detecta_nfce_por_termos():
    assert eh_cupom_fiscal(TEXTO_NFCE) is True


# ---------------------------------------------------------------------------
# 2. Extrai CNPJ formatado
# ---------------------------------------------------------------------------
def test_extrai_cnpj_formatado():
    dados = extrair_dados_cupom_fiscal(TEXTO_NFCE)
    assert dados['cnpj'] == '12.345.678/0001-90'


# ---------------------------------------------------------------------------
# 3. Extrai CNPJ sem pontuacao
# ---------------------------------------------------------------------------
def test_extrai_cnpj_sem_pontuacao():
    dados = extrair_dados_cupom_fiscal(TEXTO_SEM_PONTUACAO_CNPJ)
    assert dados['cnpj'] == '45678901000123'


# ---------------------------------------------------------------------------
# 4. Extrai data de emissao
# ---------------------------------------------------------------------------
def test_extrai_data_emissao():
    dados = extrair_dados_cupom_fiscal(TEXTO_NFCE)
    assert dados['data_emissao'] == '05/05/2026'


# ---------------------------------------------------------------------------
# 5. Extrai valor total por termo "Valor Total"
# ---------------------------------------------------------------------------
def test_extrai_valor_total_por_rotulo_valor_total():
    dados = extrair_dados_cupom_fiscal(TEXTO_NFCE)
    assert dados['valor_total'] == Decimal('145.80')


# ---------------------------------------------------------------------------
# 6. Extrai valor por termo "TOTAL R$"
# ---------------------------------------------------------------------------
def test_extrai_valor_por_rotulo_total_r():
    dados = extrair_dados_cupom_fiscal(TEXTO_SAT)
    assert dados['valor_total'] == Decimal('89.50')


# ---------------------------------------------------------------------------
# 7. Extrai chave de acesso de 44 digitos
# ---------------------------------------------------------------------------
def test_extrai_chave_acesso_44_digitos():
    dados = extrair_dados_cupom_fiscal(TEXTO_NFCE)
    assert dados['chave_acesso'] == '52260512345678000190650010000012341234567891'
    assert len(dados['chave_acesso']) == 44


# ---------------------------------------------------------------------------
# 8. Evita usar troco como valor total
# ---------------------------------------------------------------------------
def test_evita_troco_como_valor_total():
    dados = extrair_dados_cupom_fiscal(TEXTO_SAT)
    # Valor total deve ser 89,50 e nao 10,50 (troco)
    assert dados['valor_total'] == Decimal('89.50')


# ---------------------------------------------------------------------------
# 9. Gera descricao resumida com estabelecimento
# ---------------------------------------------------------------------------
def test_descricao_resumida_com_estabelecimento():
    dados = extrair_dados_cupom_fiscal(TEXTO_NFCE)
    assert 'Cupom fiscal' in dados['descricao_resumida']
    assert dados['estabelecimento'] is not None
    assert dados['estabelecimento'] in dados['descricao_resumida']


# ---------------------------------------------------------------------------
# 10. Fallback quando nao reconhece cupom
# ---------------------------------------------------------------------------
def test_fallback_quando_nao_reconhece_cupom():
    assert eh_cupom_fiscal(TEXTO_GENERICO) is False
    assert eh_cupom_fiscal(TEXTO_SEM_CUPOM) is False


# ---------------------------------------------------------------------------
# Testes adicionais de robustez
# ---------------------------------------------------------------------------

def test_detecta_sat_por_termo_cf_e():
    assert eh_cupom_fiscal(TEXTO_SAT) is True


def test_tipo_detectado_nfce():
    dados = extrair_dados_cupom_fiscal(TEXTO_NFCE)
    assert dados['tipo_detectado'] == 'NFCE'


def test_tipo_detectado_sat():
    dados = extrair_dados_cupom_fiscal(TEXTO_SAT)
    assert dados['tipo_detectado'] == 'SAT'


def test_campos_alias_prestador():
    dados = extrair_dados_cupom_fiscal(TEXTO_NFCE)
    # prestador_nome e cnpj sao aliases para integracao com IrComprovante
    assert dados['prestador_nome'] == dados['estabelecimento']
    assert dados['prestador_cpf_cnpj'] == dados['cnpj']


def test_ano_calendario_extraido():
    dados = extrair_dados_cupom_fiscal(TEXTO_NFCE)
    assert dados['ano_calendario'] == 2026


def test_confianca_alta_quando_muitos_campos():
    dados = extrair_dados_cupom_fiscal(TEXTO_NFCE)
    assert dados['confianca_extracao'] == 'alta'


def test_confianca_baixa_quando_poucos_campos():
    dados = extrair_dados_cupom_fiscal('NFC-e\nvalor desconhecido\nsem dados')
    assert dados['confianca_extracao'] in ('baixa', 'media')


def test_avisos_gerados_para_campo_faltante():
    dados = extrair_dados_cupom_fiscal('Cupom Fiscal\nValor Total R$ 10,00')
    # Estabelecimento nao encontrado deve gerar aviso
    assert any('Estabelecimento' in a for a in dados['avisos'])


def test_texto_vazio_retorna_sem_erro():
    dados = extrair_dados_cupom_fiscal('')
    assert dados['valor_total'] is None
    assert dados['cnpj'] is None


def test_detecta_por_multiplas_pistas():
    texto = 'Total R$ 50,00\nCNPJ: 11.222.333/0001-44\nSEFAZ\nValor a pagar R$ 50,00'
    assert eh_cupom_fiscal(texto) is True
