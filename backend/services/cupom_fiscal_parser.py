"""
Parser basico de cupom fiscal / NFC-e / CF-e / SAT.

Detecta documentos fiscais de consumo e extrai:
- tipo_detectado, estabelecimento, cnpj, data_emissao,
  valor_total, numero_documento, chave_acesso, descricao_resumida.

Nao faz consulta SEFAZ, nao le itens, nao calcula tributos.
"""
from decimal import Decimal, InvalidOperation
import re
import unicodedata


# ---------------------------------------------------------------------------
# Termos de deteccao
# ---------------------------------------------------------------------------

_TERMOS_CUPOM = [
    'cupom fiscal',
    'nfc-e',
    'nfce',
    'nota fiscal de consumidor eletronica',
    'nota fiscal de consumidor eletronico',
    'extrato no.',
    'extrato no',
    'extrato n.',
    'extrato nº',
    'documento auxiliar da nota fiscal de consumidor eletronica',
    'danfe nfc-e',
    'danfe nfce',
    'sat',
    'cf-e',
    'cfe',
    'cupom fiscal eletronico',
]

_TERMOS_PISTAS = [
    'chave de acesso',
    'qrcode',
    'qr code',
    'sefaz',
    'valor total',
    'valor a pagar',
    'total r$',
    'total da nota',
    'valor pago',
]

# Termos que nao devem ser usados como nome do estabelecimento
_BLOQUEIOS_ESTABELECIMENTO = re.compile(
    r'(cupom|fiscal|nfc|nfce|danfe|sat\b|cf-e|cfe|cnpj|cpf|inscri|endere|cep|fone|'
    r'telefone|email|data|hora|emissao|emitido|total|valor|troco|desconto|subtotal|'
    r'sefaz|qr\s*code|chave|acesso|serie|numero|documento auxiliar|nota fiscal|'
    r'consumidor|eletronica|eletronico)',
    re.IGNORECASE,
)


def _normalizar(texto):
    texto = str(texto or '').lower()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


def _linhas(texto):
    return [l.strip() for l in (texto or '').splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Deteccao
# ---------------------------------------------------------------------------

def eh_cupom_fiscal(texto):
    """Retorna True se o texto parece ser um cupom fiscal / NFC-e / SAT / CF-e."""
    norm = _normalizar(texto or '')
    for termo in _TERMOS_CUPOM:
        if termo in norm:
            return True
    pistas = sum(1 for t in _TERMOS_PISTAS if t in norm)
    if pistas >= 2:
        return True
    if re.search(r'\b\d{44}\b', texto or ''):
        return True
    return False


# ---------------------------------------------------------------------------
# Extracao de campos
# ---------------------------------------------------------------------------

def _extrair_tipo_detectado(norm):
    if 'nfc-e' in norm or 'nfce' in norm or 'nota fiscal de consumidor' in norm or 'danfe nfc' in norm:
        return 'NFCE'
    if 'cf-e' in norm or 'cfe' in norm or 'cupom fiscal eletronico' in norm:
        return 'SAT'
    if 'cupom fiscal' in norm:
        return 'CUPOM_FISCAL'
    if 'sat' in norm:
        return 'SAT'
    return 'CUPOM_FISCAL'


def _extrair_cnpj(texto):
    """Retorna primeiro CNPJ encontrado (preferindo inicio do texto, evitando CPF do consumidor)."""
    # Padrao formatado: 00.000.000/0001-00
    formatados = list(re.finditer(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b', texto or ''))
    if formatados:
        # Preferir CNPJ que aparece antes da palavra "consumidor" ou "cpf"
        texto_lower = texto.lower()
        consumidor_pos = texto_lower.find('cpf do consumidor')
        if consumidor_pos < 0:
            consumidor_pos = texto_lower.find('cpf consumidor')
        if consumidor_pos < 0:
            consumidor_pos = len(texto_lower)
        for m in formatados:
            if m.start() < consumidor_pos:
                return m.group(0)
        return formatados[0].group(0)

    # Padrao sem pontuacao: 14 digitos
    raw = list(re.finditer(r'\b(\d{14})\b', texto or ''))
    if raw:
        return raw[0].group(1)
    return None


def _extrair_data(texto):
    """Extrai data de emissao preferindo linhas proximas de termos de emissao."""
    padroes = [
        r'\b(\d{2}/\d{2}/\d{4})\b',
        r'\b(\d{2}-\d{2}-\d{4})\b',
        r'\b(\d{4}-\d{2}-\d{2})\b',
        r'\b(\d{2}/\d{2}/\d{2})\b',
    ]
    termos_emissao = ('emissao', 'emitido', 'emitida', 'data', 'competencia', 'nfc-e', 'cupom')
    linhas = _linhas(texto)
    norm_linhas = [(_normalizar(l), l) for l in linhas]

    # Primeiro: linha com termo de emissao
    for norm_l, linha_orig in norm_linhas:
        if not any(t in norm_l for t in termos_emissao):
            continue
        for padrao in padroes:
            m = re.search(padrao, linha_orig)
            if m:
                return _normalizar_data(m.group(1))

    # Fallback: primeira data encontrada no texto
    for padrao in padroes:
        m = re.search(padrao, texto or '')
        if m:
            return _normalizar_data(m.group(1))
    return None


def _normalizar_data(texto_data):
    """Normaliza data para dd/mm/aaaa."""
    if not texto_data:
        return None
    # aaaa-mm-dd → dd/mm/aaaa
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', texto_data)
    if m:
        return f'{m.group(3)}/{m.group(2)}/{m.group(1)}'
    # dd-mm-aaaa → dd/mm/aaaa
    m = re.match(r'^(\d{2})-(\d{2})-(\d{4})$', texto_data)
    if m:
        return f'{m.group(1)}/{m.group(2)}/{m.group(3)}'
    # dd/mm/aa → dd/mm/20aa
    m = re.match(r'^(\d{2})/(\d{2})/(\d{2})$', texto_data)
    if m:
        return f'{m.group(1)}/{m.group(2)}/20{m.group(3)}'
    return texto_data


def _parse_valor(texto_valor):
    if not texto_valor:
        return None
    limpo = str(texto_valor).strip().replace('R$', '').replace(' ', '')
    if ',' in limpo:
        limpo = limpo.replace('.', '').replace(',', '.')
    try:
        return Decimal(limpo)
    except (InvalidOperation, ValueError):
        return None


# Rotulos de valor total em ordem de prioridade
_ROTULOS_TOTAL = [
    'valor total',
    'total da nota',
    'total r$',
    'valor a pagar',
    'valor pago',
    'total',
]

# Rotulos a EVITAR como valor total
_ROTULOS_EVITAR = re.compile(
    r'(troco|desconto|subtotal|parcela|taxa|tribut|ipi|icms|pis|cofins|frete)',
    re.IGNORECASE,
)


def _extrair_valor_total(texto):
    """
    Extrai valor total priorizando rotulos canonicos.
    Evita troco, desconto e subtotal quando existe um total real.
    """
    linhas = _linhas(texto)
    norm_linhas = [(_normalizar(l), l) for l in linhas]

    # Tenta cada rotulo em ordem
    for rotulo in _ROTULOS_TOTAL:
        for norm_l, linha_orig in norm_linhas:
            if rotulo not in norm_l:
                continue
            if _ROTULOS_EVITAR.search(norm_l):
                continue
            # Procura valor na mesma linha ou na proxima
            janela = linha_orig
            idx = [n for n, _ in norm_linhas].index(norm_l)
            if idx + 1 < len(linhas):
                janela = janela + ' ' + linhas[idx + 1]
            m = re.search(r'R?\$?\s*([\d.,]+)', janela)
            if m:
                valor = _parse_valor(m.group(1))
                if valor is not None and valor > Decimal('0'):
                    return valor

    return None


def _extrair_chave_acesso(texto):
    """Extrai sequencia de 44 digitos (chave de acesso NFC-e)."""
    # Chave pode estar com espacos a cada 4 digitos
    # Tenta sequencia continua primeiro
    m = re.search(r'\b(\d{44})\b', texto or '')
    if m:
        return m.group(1)
    # Tenta com espacos: grupos de 4 com separador espaco/hifen
    m = re.search(r'(\d{4}[\s\-]){10}\d{4}', texto or '')
    if m:
        return re.sub(r'[\s\-]', '', m.group(0))
    return None


def _extrair_numero_documento(texto, norm):
    """Extrai numero do cupom/NFC-e/COO."""
    padroes = [
        (r'(?:COO|Cupom)\s*[:\-]?\s*(\d+)', re.IGNORECASE),
        (r'(?:N[uú]mero|N[oº]\.?)\s*[:\-]?\s*(\d{3,})', re.IGNORECASE),
        (r'(?:NFC-e|NFCE)\s*[:\-]?\s*(\d+)', re.IGNORECASE),
        (r'(?:Extrato\s*N[oº]\.?)\s*[:\-]?\s*(\d+)', re.IGNORECASE),
    ]
    for padrao, flags in padroes:
        m = re.search(padrao, texto or '', flags)
        if m:
            return m.group(1)
    return None


def _extrair_estabelecimento(texto):
    """
    Heuristica: primeiras linhas uteis antes do CNPJ.
    Ignora termos genericos de cabecalho de cupom.
    """
    linhas = _linhas(texto)
    candidatos = []

    # Localiza posicao do primeiro CNPJ ou termo de cabecalho
    pos_cnpj = len(linhas)
    for i, linha in enumerate(linhas):
        if re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', linha):
            pos_cnpj = i
            break
        if re.search(r'\b\d{14}\b', linha):
            pos_cnpj = i
            break

    # Varre linhas antes do CNPJ
    for linha in linhas[:max(pos_cnpj, 8)]:
        norm_l = _normalizar(linha)
        if len(norm_l) < 3:
            continue
        if _BLOQUEIOS_ESTABELECIMENTO.search(norm_l):
            continue
        if re.search(r'^\d+$|^\d{2}/\d{2}|\d{2}:\d{2}', linha):
            continue
        if re.search(r'[A-Za-zÀ-ɏ]', linha):
            candidatos.append(linha[:255])
        if len(candidatos) >= 2:
            break

    if candidatos:
        return candidatos[0]
    return None


# ---------------------------------------------------------------------------
# Interface publica
# ---------------------------------------------------------------------------

def extrair_dados_cupom_fiscal(texto):
    """
    Extrai campos basicos de um cupom fiscal.

    Retorna dict com:
      tipo_detectado, estabelecimento, cnpj, data_emissao,
      valor_total (Decimal|None), numero_documento, chave_acesso,
      descricao_resumida, confianca_extracao, avisos.
    """
    texto = texto or ''
    norm = _normalizar(texto)

    tipo_detectado = _extrair_tipo_detectado(norm)
    estabelecimento = _extrair_estabelecimento(texto)
    cnpj = _extrair_cnpj(texto)
    data_emissao = _extrair_data(texto)
    valor_total = _extrair_valor_total(texto)
    chave_acesso = _extrair_chave_acesso(texto)
    numero_documento = _extrair_numero_documento(texto, norm)

    # Descricao resumida
    estabelecimento_desc = estabelecimento or 'Estabelecimento nao identificado'
    descricao_resumida = f'Cupom fiscal — {estabelecimento_desc}'

    # Avisos por campo nao extraido
    avisos = []
    if not estabelecimento:
        avisos.append('Estabelecimento nao identificado automaticamente.')
    if not cnpj:
        avisos.append('CNPJ nao identificado automaticamente.')
    if not data_emissao:
        avisos.append('Data de emissao nao identificada automaticamente.')
    if valor_total is None:
        avisos.append('Valor total nao identificado automaticamente.')

    campos_ok = sum([
        bool(estabelecimento),
        bool(cnpj),
        bool(data_emissao),
        valor_total is not None,
    ])
    confianca = 'alta' if campos_ok >= 3 else ('media' if campos_ok >= 2 else 'baixa')

    return {
        'tipo_documento': tipo_detectado,
        'tipo_detectado': tipo_detectado,
        'estabelecimento': estabelecimento,
        'cnpj': cnpj,
        'data_emissao': data_emissao,
        'data_documento': data_emissao,
        'prestador_nome': estabelecimento,
        'prestador_cpf_cnpj': cnpj,
        'valor_total': valor_total,
        'valor': valor_total,
        'numero_documento': numero_documento,
        'chave_acesso': chave_acesso,
        'descricao_resumida': descricao_resumida,
        'ano_calendario': _ano_da_data(data_emissao),
        'texto_classificacao': texto,
        'confianca_extracao': confianca,
        'avisos': avisos,
    }


def _ano_da_data(data_str):
    if not data_str:
        return None
    m = re.search(r'(\d{4})', data_str)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None
