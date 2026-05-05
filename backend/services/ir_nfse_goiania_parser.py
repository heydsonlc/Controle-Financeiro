from decimal import Decimal
import re
import unicodedata


def _normalizar(texto):
    texto = str(texto or '').lower()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


def eh_nfse_goiania(texto):
    normalizado = _normalizar(texto)
    return (
        'prefeitura municipal de goiania' in normalizado
        and ('nota fiscal de servico eletronica' in normalizado or 'nfs-e' in normalizado)
        and 'dados do prestador de servico' in normalizado
    ) or 'issnetonline.com.br/goiania' in normalizado


def extrair_dados_nfse_goiania(texto):
    texto = texto or ''
    numero_nota = _extrair_proximo_valor(texto, 'Numero da Nota Fiscal', r'\b\d+\b')
    data_competencia = (
        _extrair_proximo_valor(texto, 'Data de Competencia', r'\b\d{2}/\d{2}/\d{4}\b')
        or _extrair_proximo_valor(texto, 'Data de Geracao da NFS-e', r'\b\d{2}/\d{2}/\d{4}\b')
        or _extrair_proximo_valor(texto, 'Data de Emissao do RPS', r'\b\d{2}/\d{2}/\d{4}\b')
    )
    descricao = _extrair_descricao_servico(texto)
    prestador_nome = _extrair_prestador(texto)
    prestador_doc = _extrair_regex(texto, r'CPF/CNPJ\s+(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})')
    tomador_doc = _extrair_regex(texto, r'CNPJ/CPF\s*:\s*(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})')
    tomador_nome = _extrair_regex(texto, r'Raz[aã]o Social\s*:\s*(.+?)(?:\n|$)')
    valor = _extrair_valor_total(texto)

    texto_classificacao = ' '.join(
        parte for parte in [descricao, prestador_nome, texto] if parte
    ).strip()

    avisos = []
    for campo, valor_campo in {
        'prestador_nome': prestador_nome,
        'prestador_cpf_cnpj': prestador_doc,
        'tomador_nome': tomador_nome,
        'tomador_cpf': tomador_doc,
        'descricao_servico': descricao,
        'valor': valor,
        'data_documento': data_competencia,
    }.items():
        if not valor_campo:
            avisos.append(f'Campo nao extraido: {campo}.')

    return {
        'tipo_documento': 'NFS-e Goiania',
        'numero_nota': numero_nota,
        'data_documento': data_competencia,
        'data_competencia': data_competencia,
        'prestador_nome': prestador_nome,
        'prestador_cpf_cnpj': prestador_doc,
        'tomador_nome': tomador_nome,
        'tomador_cpf': tomador_doc,
        'descricao_servico': descricao,
        'valor': valor,
        'ano_calendario': int(data_competencia[-4:]) if data_competencia else None,
        'texto_classificacao': texto_classificacao,
        'confianca_extracao': 'alta' if len(avisos) <= 1 else 'media',
        'avisos': avisos,
    }


def _linhas(texto):
    return [linha.strip() for linha in (texto or '').splitlines() if linha.strip()]


def _extrair_proximo_valor(texto, rotulo, padrao):
    linhas = _linhas(texto)
    rotulo_norm = _normalizar(rotulo)
    regex = re.compile(padrao)
    for idx, linha in enumerate(linhas):
        if rotulo_norm not in _normalizar(linha):
            continue
        janela = linhas[idx:idx + 8]
        for candidata in janela:
            match = regex.search(candidata)
            if match and rotulo_norm not in _normalizar(candidata):
                return match.group(0)
        trecho = '\n'.join(janela)
        match = regex.search(trecho)
        if match:
            return match.group(0)
    return None


def _extrair_regex(texto, padrao):
    match = re.search(padrao, texto or '', flags=re.IGNORECASE)
    if not match:
        return None
    return ' '.join(match.group(1).strip().split())


def _extrair_prestador(texto):
    linhas = _linhas(texto)
    bloqueios = (
        'data de geracao',
        'data de competencia',
        'serie do documento',
        'numero da nota fiscal',
        'inscricao municipal',
        'cpf/cnpj',
        'identificacao da nota',
        'natureza da operacao',
        'local dos servicos',
        'municipio incidencia',
        'cod. de autenticidade',
        'responsavel pela retencao',
        'prefeitura municipal',
        'secretaria municipal',
    )
    for idx, linha in enumerate(linhas):
        if 'dados do prestador de servico' not in _normalizar(linha):
            continue
        for candidata in linhas[idx + 1:idx + 16]:
            normalizada = _normalizar(candidata)
            if any(bloqueio in normalizada for bloqueio in bloqueios):
                continue
            if re.search(r'\d{2}/\d{2}/\d{4}', candidata):
                continue
            if re.search(r'^\d{5,}$|^\d{2}:\d{2}', candidata):
                continue
            if re.search(r'(rua|avenida|cep|fone|email|@|goiania/go)', normalizada):
                continue
            if re.search(r'[A-Za-z]', candidata):
                return candidata[:255]
    return None


def _extrair_descricao_servico(texto):
    match = re.search(
        r'Descri[cç][aã]o dos Servi[cç]os\s*(.+?)\s*Detalhamento dos Tributos',
        texto or '',
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    descricao = match.group(1)
    descricao = re.split(r'\|?\s*Cond\.?Pagto', descricao, flags=re.IGNORECASE)[0]
    descricao = descricao.replace('|', ' ')
    descricao = re.sub(r'\s+', ' ', descricao).strip()
    return descricao[:500] if descricao else None


def _extrair_valor_total(texto):
    valor = _valor_apos_rotulo(texto, 'Vl. Total dos Servicos')
    if valor is not None:
        return valor
    valor = _valor_apos_rotulo(texto, 'Vl. Liquido da Nota Fiscal')
    if valor is not None:
        return valor
    match = re.search(r'Cond\.?Pagto.*?R\$\s*([\d.]+,\d{2})', texto or '', flags=re.IGNORECASE | re.DOTALL)
    if match:
        return _parse_valor(match.group(1))
    return None


def _valor_apos_rotulo(texto, rotulo):
    normalizado = _normalizar(texto)
    rotulo_norm = _normalizar(rotulo)
    pos = normalizado.find(rotulo_norm)
    if pos < 0:
        return None
    trecho = texto[pos:pos + 500]
    match = re.search(r'R\$\s*([\d.]+,\d{2})', trecho)
    if not match:
        return None
    return _parse_valor(match.group(1))


def _parse_valor(valor):
    try:
        return Decimal(str(valor).replace('.', '').replace(',', '.'))
    except Exception:
        return None
