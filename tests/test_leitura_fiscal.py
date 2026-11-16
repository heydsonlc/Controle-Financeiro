"""
Testes FIN-REG-08 — leitura fiscal do novo aplicativo (web/src/js/leitura-fiscal.js, no navegador) conferida com os
leitores do PROPRIO Flask sobre os mesmos textos FICTICIOS:
- ir_nfse_goiania_parser.py (NFS-e de Goiania): deteccao e campos;
- cupom_fiscal_parser.py (cupom fiscal, NFC-e, SAT): deteccao e campos;
- IrDocumentoService._extrair_dados_simples (demais documentos): data, CPF/CNPJ, prestador e o maior valor;
- CategoriaPalavraChaveService (palavras-chave): categoria sugerida, ambiguidade e ausencia de sugestao.
E as diferencas deliberadas do novo aplicativo (decisao do titular): situacao de cada campo, total do cupom contraditorio sem
escolha automatica, documento com varios valores sem escolha automatica, CPF/CNPJ invalido para conferencia e OCR sempre
para conferencia. Nenhum banco, rede ou documento real.
"""
import json
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services.cupom_fiscal_parser import eh_cupom_fiscal, extrair_dados_cupom_fiscal
from backend.services.ir_nfse_goiania_parser import eh_nfse_goiania, extrair_dados_nfse_goiania
from tests.test_cupom_fiscal_parser import TEXTO_GENERICO, TEXTO_NFCE, TEXTO_SAT, TEXTO_SEM_CUPOM, TEXTO_SEM_PONTUACAO_CNPJ
from tests.test_ir_nfse_goiania import NFSE_GOIANIA_TEXTO

pytestmark = pytest.mark.skipif(shutil.which('node') is None, reason='node nao encontrado')

ROOT = Path(__file__).resolve().parent.parent
MODULO = (ROOT / 'web' / 'src' / 'js' / 'leitura-fiscal.js').as_uri()

CUPOM_OCR_ERRADO = """MERCADO FICTICIO LTDA
CNPJ: 12.345.678/0001-95
CUPOM FISCAL ELETRONICO - SAT
15/11/2026 10:32:11
ARROZ 5KG 24,90
CAFE 500G 18,50
SUBTOTAL 43,40
DESCONTO 3,40
TOTAL R$ 409,00
Dinheiro 50,00
Troco 19,00"""

CUPOM_COERENTE = CUPOM_OCR_ERRADO.replace('TOTAL R$ 409,00', 'TOTAL R$ 40,00').replace('Troco 19,00', 'Troco 10,00')

RECIBO_VARIOS_VALORES = """Recibo de prestacao de servico
Fisioterapeuta Ficticia Souza
Sessao 1 em 03/10/2026 R$ 150,00
Sessao 2 em 10/10/2026 R$ 150,00
Material R$ 35,50
Recebi a quantia acima de Paciente Ficticio
CPF 123.456.789-09"""

RECIBO_UM_VALOR = """Recibo de consulta odontologica
Clinica Sorriso Ficticio
Data 12/09/2026
Recebemos o valor de R$ 380,00 referente a limpeza
CNPJ 11.222.333/0001-81"""

PALAVRAS = [{'categoria_id': 10, 'palavra': 'farmacia'}, {'categoria_id': 10, 'palavra': 'drogaria'},
            {'categoria_id': 20, 'palavra': 'mercado'}, {'categoria_id': 30, 'palavra': 'consulta odontologica'},
            {'categoria_id': 40, 'palavra': 'fisioterapia'}, {'categoria_id': 41, 'palavra': 'fisioterapia'}]
CATEGORIAS = [{'id': 10, 'nome': 'Saude', 'categoria_ir_id': 7}, {'id': 20, 'nome': 'Mercado', 'categoria_ir_id': None},
              {'id': 30, 'nome': 'Odontologia', 'categoria_ir_id': 8}, {'id': 40, 'nome': 'Fisio A', 'categoria_ir_id': None},
              {'id': 41, 'nome': 'Fisio B', 'categoria_ir_id': None}]

_SCRIPT = """
import * as L from %s;
const pedidos = JSON.parse(await new Promise((ok) => { let t = ''; process.stdin.on('data', (d) => { t += d; }); process.stdin.on('end', () => ok(t)); }));
const saida = pedidos.map(([funcao, ...args]) => L[funcao](...args));
console.log(JSON.stringify(saida));
"""


def js(*pedidos):
    r = subprocess.run(['node', '--input-type=module', '-e', _SCRIPT % json.dumps(MODULO)], cwd=ROOT, input=json.dumps(pedidos),
                       capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def num(v):
    return None if v is None else Decimal(str(v))


TEXTOS = [NFSE_GOIANIA_TEXTO, TEXTO_NFCE, TEXTO_SAT, TEXTO_SEM_PONTUACAO_CNPJ, TEXTO_GENERICO, TEXTO_SEM_CUPOM, CUPOM_OCR_ERRADO,
          CUPOM_COERENTE, RECIBO_VARIOS_VALORES, RECIBO_UM_VALOR, '']


def test_deteccao_igual_ao_flask():
    novo = js(*[['ehNfseGoiania', t] for t in TEXTOS], *[['ehCupomFiscal', t] for t in TEXTOS])
    assert novo == [eh_nfse_goiania(t) for t in TEXTOS] + [eh_cupom_fiscal(t) for t in TEXTOS]
    assert novo[0] is True and novo[len(TEXTOS) + 1] is True  # a NFS-e e a NFC-e de exemplo sao reconhecidas


def test_nfse_goiania_campos_iguais_ao_flask():
    f = extrair_dados_nfse_goiania(NFSE_GOIANIA_TEXTO)
    n = js(['dadosNfseGoiania', NFSE_GOIANIA_TEXTO])[0]
    for campo in ('numero_nota', 'data_documento', 'prestador_nome', 'prestador_cpf_cnpj', 'tomador_nome', 'tomador_cpf', 'descricao_servico',
                  'texto_classificacao'):
        assert n[campo] == f[campo], campo
    assert num(n['valor']) == f['valor'] and f['valor'] is not None


@pytest.mark.parametrize('texto', [TEXTO_NFCE, TEXTO_SAT, TEXTO_SEM_PONTUACAO_CNPJ, TEXTO_GENERICO, TEXTO_SEM_CUPOM, CUPOM_OCR_ERRADO,
                                   CUPOM_COERENTE, ''])
def test_cupom_fiscal_campos_iguais_ao_flask(texto):
    f = extrair_dados_cupom_fiscal(texto)
    n = js(['dadosCupomFiscal', texto])[0]
    for campo in ('tipo_detectado', 'estabelecimento', 'cnpj', 'data_emissao', 'numero_documento', 'chave_acesso', 'descricao_resumida',
                  'texto_classificacao'):
        assert n[campo] == f[campo], campo
    assert num(n['valor_total']) == f['valor_total']


@pytest.mark.parametrize('texto', [RECIBO_VARIOS_VALORES, RECIBO_UM_VALOR, TEXTO_SEM_CUPOM, NFSE_GOIANIA_TEXTO, ''])
def test_documento_generico_igual_ao_flask(texto):
    from backend.services.ir_documento_service import IrDocumentoService
    alvo = SimpleNamespace(data_documento=None, ano_calendario=None, valor=None, prestador_cpf_cnpj=None, prestador_nome=None)
    IrDocumentoService._extrair_dados_simples(alvo, texto)
    n = js(['dadosGenericos', texto])[0]
    assert (alvo.data_documento.strftime('%d/%m/%Y') if alvo.data_documento else None) == n['data_documento']
    assert alvo.prestador_cpf_cnpj == n['prestador_cpf_cnpj']
    assert alvo.prestador_nome == n['prestador_nome']
    assert alvo.valor == num(n['maior_valor'])  # o Flask escolhia o maior; o novo so o usa se for o unico (teste abaixo)


def test_palavras_chave_iguais_ao_flask(monkeypatch):
    from backend.services import categoria_palavra_chave_service as servico
    linhas = [SimpleNamespace(categoria_id=p['categoria_id'], palavra=p['palavra']) for p in PALAVRAS]
    nomes = {c['id']: SimpleNamespace(nome=c['nome']) for c in CATEGORIAS}
    monkeypatch.setattr(servico, 'CategoriaPalavraChave', SimpleNamespace(query=SimpleNamespace(filter_by=lambda **k: SimpleNamespace(all=lambda: linhas))))
    monkeypatch.setattr(servico, 'Categoria', SimpleNamespace(query=SimpleNamespace(get=lambda i: nomes.get(i))))
    S = servico.CategoriaPalavraChaveService
    casos = ['Drogaria Ficticia - farmacia popular', 'MERCADO FICTICIO LTDA cupom', 'Recibo de consulta odontológica',
             'sessao de fisioterapia', 'texto sem nenhuma palavra', '']
    # Pela funcao publica (sugerirCategoria), que recebe as categorias do perfil em lista.
    novo = js(*[['sugerirCategoria', {'tipo': 'GENERICO', 'textoClassificacao': t, 'campos': {'prestador_cpf_cnpj': {'valor': None}}},
                 {'palavras': PALAVRAS, 'categorias': CATEGORIAS, 'historico': []}] for t in casos])
    for texto, n in zip(casos, novo):
        f = S.classificar_por_palavras_chave(S.normalizar_descricao_importacao(texto))
        assert n['categoria_id'] == f['categoria_id'], texto
        assert bool(n['candidatas']) == bool(f['categorias_candidatas']) and (f['origem'] == 'ambigua') == ('Mais de uma' in n['aviso']), texto
    assert [n['categoria_id'] for n in novo] == [10, 20, 30, None, None, None]
    assert novo[0]['categoria_ir_id'] == 7 and novo[0]['fonte'] == 'palavra_chave'


# ---- Diferencas deliberadas do novo aplicativo ---------------------------------------------------------------------

def test_cupom_com_total_contraditorio_nao_escolhe_valor():
    lido, coerente = js(['lerDocumento', CUPOM_OCR_ERRADO, {'origem': 'OCR_IMAGEM'}], ['lerDocumento', CUPOM_COERENTE, {'origem': 'TEXTO_PDF'}])
    assert extrair_dados_cupom_fiscal(CUPOM_OCR_ERRADO)['valor_total'] == Decimal('409.00')  # o Flask aceitava o total errado
    assert lido['tipo'] == 'CUPOM_FISCAL' and lido['campos']['valor'] == {'valor': None, 'situacao': 'conferir'}
    assert lido['valoresCandidatos'] == ['409.00', '40.00', '31.00']  # lido, subtotal - desconto, dinheiro - troco
    assert any('não confere com subtotal' in a for a in lido['avisos'])
    # OCR: os demais campos sempre para conferencia
    assert all(c['situacao'] in ('conferir', 'nao_reconhecido') for c in lido['campos'].values())
    assert lido['campos']['data_documento'] == {'valor': '2026-11-15', 'situacao': 'conferir'}
    # Coerente e lido do texto do PDF: o total e aceito como identificado
    assert coerente['campos']['valor'] == {'valor': '40.00', 'situacao': 'identificado'} and coerente['valoresCandidatos'] == []


def test_documento_com_varios_valores_nao_escolhe():
    varios, um = js(['lerDocumento', RECIBO_VARIOS_VALORES, {'origem': 'TEXTO_PDF'}], ['lerDocumento', RECIBO_UM_VALOR, {'origem': 'TEXTO_PDF'}])
    assert varios['tipo'] == 'GENERICO' and varios['campos']['valor'] == {'valor': None, 'situacao': 'conferir'}
    assert varios['valoresCandidatos'] == ['150.00', '35.50']
    assert um['campos']['valor'] == {'valor': '380.00', 'situacao': 'conferir'}  # generico: sempre para conferencia
    assert um['campos']['prestador_cpf_cnpj'] == {'valor': '11.222.333/0001-81', 'situacao': 'conferir'}


def test_nfse_lida_do_pdf_e_identificada_e_cpf_cnpj_invalido_pede_conferencia():
    nfse, invalido, curto = js(['lerDocumento', NFSE_GOIANIA_TEXTO, {'origem': 'TEXTO_PDF'}],
                               ['lerDocumento', RECIBO_UM_VALOR.replace('11.222.333/0001-81', '11.222.333/0001-82'), {'origem': 'TEXTO_PDF'}],
                               ['lerDocumento', 'curto', {'origem': 'OCR_IMAGEM'}])
    f = extrair_dados_nfse_goiania(NFSE_GOIANIA_TEXTO)
    assert nfse['tipo'] == 'NFSE_GOIANIA' and nfse['campos']['valor'] == {'valor': f'{f["valor"]:.2f}', 'situacao': 'identificado'}
    assert nfse['campos']['prestador_nome']['valor'] == f['prestador_nome']
    assert invalido['campos']['prestador_cpf_cnpj']['situacao'] == 'conferir' and any('dígito verificador' in a for a in invalido['avisos'])
    assert curto['tipo'] == 'SEM_TEXTO' and all(c['situacao'] == 'nao_reconhecido' for c in curto['campos'].values())


def test_categoria_pelo_emitente_so_quando_unanime_e_do_perfil():
    base = {'tipo': 'GENERICO', 'textoClassificacao': 'sem palavras', 'campos': {'prestador_cpf_cnpj': {'valor': '11.222.333/0001-81'}}}
    unanime = [{'prestador_cpf_cnpj': '11222333000181', 'categoria_id': 30}, {'prestador_cpf_cnpj': '11.222.333/0001-81', 'categoria_id': 30}]
    dividido = unanime + [{'prestador_cpf_cnpj': '11222333000181', 'categoria_id': 20}]
    fora_do_perfil = [{'prestador_cpf_cnpj': '11222333000181', 'categoria_id': 99}]
    r = js(*[['sugerirCategoria', base, {'palavras': [], 'categorias': CATEGORIAS, 'historico': h}] for h in (unanime, dividido, fora_do_perfil)])
    assert (r[0]['categoria_id'], r[0]['fonte'], r[0]['categoria_ir_id']) == (30, 'emitente', 8)
    assert r[1]['categoria_id'] is None and r[2]['categoria_id'] is None


def test_normalizacao_do_texto_ocr_igual_ao_flask():
    from backend.services.ocr_service import OcrService
    texto = '  MERCADO\t FICTICIO  \r\n\r\n\r\n\r\nTOTAL   R$ 40,00 \x00\n\n\n\n fim  '
    assert js(['normalizarTextoOcr', texto])[0] == OcrService.normalizar_texto_ocr(texto)
