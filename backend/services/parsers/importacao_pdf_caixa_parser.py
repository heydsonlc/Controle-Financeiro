import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


GRUPOS_LANCAMENTOS = {
    'ANUIDADE',
    'COMPRAS',
    'COMPRAS PARCELADAS',
    'COMPRAS INTERNACIONAIS',
}


def _limpar_linha(linha):
    return re.sub(r'\s+', ' ', str(linha or '')).strip()


def _parse_competencia(competencia):
    if isinstance(competencia, date):
        return competencia.replace(day=1)
    texto = str(competencia or '').strip()
    for formato in ('%Y-%m-%d', '%Y-%m', '%m/%Y'):
        try:
            return datetime.strptime(texto, formato).date().replace(day=1)
        except ValueError:
            continue
    raise ValueError('competencia invalida para parser PDF.')


def _parse_data_com_ano(data_curta, competencia_base):
    dia, mes = [int(parte) for parte in data_curta.split('/')]
    ano = competencia_base.year - 1 if mes > competencia_base.month else competencia_base.year
    return date(ano, mes, dia).isoformat()


def _parse_valor(valor):
    texto = str(valor or '').replace('.', '').replace(',', '.')
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return None


def _float_decimal(valor):
    return float(valor) if valor is not None else None


def _money_regex():
    return r'(\d{1,3}(?:\.\d{3})*,\d{2})'


def _extrair_metadados(texto_total):
    fatura = {
        'emissor': 'Caixa',
        'vencimento': None,
        'valor_total': None,
        'cartoes_detectados': [],
        'totais_por_cartao': {},
        'totais_por_grupo': {},
        'boleto': None,
        'titular': None,
    }

    vencimento = re.search(r'VENCIMENTO\s+(\d{2}/\d{2}/\d{4})', texto_total, re.IGNORECASE)
    if vencimento:
        fatura['vencimento'] = datetime.strptime(vencimento.group(1), '%d/%m/%Y').date().isoformat()

    total = re.search(
        rf'VALOR TOTAL DESTA FATURA[\s\S]{{0,160}}?R\$\s*{_money_regex()}',
        texto_total,
        re.IGNORECASE,
    )
    if not total:
        total = re.search(rf'Valor total desta fatura\s+R\$\s*{_money_regex()}', texto_total, re.IGNORECASE)
    if total:
        fatura['valor_total'] = _float_decimal(_parse_valor(total.group(1)))

    boleto = re.search(r'(104\d{2}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d+)', texto_total)
    if boleto:
        fatura['boleto'] = boleto.group(1)

    cartoes = sorted(set(re.findall(r'Cart[aã]o\s+(\d{4})', texto_total, flags=re.IGNORECASE)))
    fatura['cartoes_detectados'] = cartoes
    return fatura


def _detectar_grupo(linha):
    texto = linha.upper()
    if 'TOTAL COMPRAS' in texto:
        return None
    if 'COMPRAS INTERNACIONAIS' in texto:
        return 'COMPRAS INTERNACIONAIS'
    if 'COMPRAS PARCELADAS' in texto:
        return 'COMPRAS PARCELADAS'
    if re.search(r'(^|\s)COMPRAS(\s|\(|$)', texto):
        return 'COMPRAS'
    if re.search(r'\bANUIDADE\b', texto):
        return 'ANUIDADE'
    return None


def _parse_parcela(descricao):
    for padrao in (
        r'(\d{1,2})\s+DE\s+(\d{1,2})',
        r'(\d{1,2})\s*/\s*(\d{1,2})',
    ):
        match = re.search(padrao, descricao, flags=re.IGNORECASE)
        if match:
            atual = int(match.group(1))
            total = int(match.group(2))
            if 1 <= atual <= total:
                descricao_limpa = (descricao[:match.start()] + descricao[match.end():]).strip()
                descricao_limpa = re.sub(r'\s+', ' ', descricao_limpa)
                return descricao_limpa, atual, total
    return descricao, 1, 1


def _anexar_cotacao_internacional(linha, lancamento):
    if not lancamento or lancamento.get('grupo') != 'COMPRAS INTERNACIONAIS':
        return False
    if re.search(rf'{_money_regex()}\s*[DC]\b', linha, flags=re.IGNORECASE):
        return False
    match = re.search(r'(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d+,\d{4})$', linha)
    if not match:
        return False
    lancamento.setdefault('metadados', {})['valor_original_brl'] = _float_decimal(_parse_valor(match.group(1)))
    lancamento.setdefault('metadados', {})['cotacao'] = float(match.group(2).replace(',', '.'))
    return True


def _extrair_lancamento_linha(linha, cartao_final, grupo, competencia_base, pagina, numero_linha):
    if not cartao_final or grupo not in GRUPOS_LANCAMENTOS:
        return None

    texto_upper = linha.upper()
    if 'TOTAL ' in texto_upper or 'VALOR TOTAL DESTA FATURA' in texto_upper:
        return None
    if texto_upper.startswith('DATA ') or texto_upper.startswith('CRÉDITO/DÉBITO') or texto_upper.startswith('CREDITO/DEBITO'):
        return None

    valores = list(re.finditer(rf'{_money_regex()}\s*([DC])\b', linha, flags=re.IGNORECASE))
    if not valores:
        return None

    valor_match = valores[-1]
    valor = _parse_valor(valor_match.group(1))
    sufixo = valor_match.group(2).upper()
    if valor is None:
        return None

    data_match = re.search(r'(?<!\d)(\d{2}/\d{2})(?!\d)', linha)
    mensagens = []
    if data_match:
        data_compra = _parse_data_com_ano(data_match.group(1), competencia_base)
        inicio_descricao = data_match.end()
    elif grupo == 'ANUIDADE':
        data_compra = competencia_base.isoformat()
        inicio_descricao = 0
        mensagens.append('Data nao informada na anuidade; usada a competencia da fatura.')
    else:
        return None

    descricao = linha[inicio_descricao:valor_match.start()].strip()
    descricao = re.sub(r'^(Programa de Pontos|Pontos Fatura|Pontos a Expirar|Saldo Anterior)\s+\d+\s+', '', descricao, flags=re.IGNORECASE)
    descricao = re.sub(r'\s+', ' ', descricao).strip()

    metadados = {
        'pagina': pagina,
        'linha_pdf': numero_linha,
        'linha_texto': linha,
    }
    if grupo == 'COMPRAS INTERNACIONAIS':
        moeda = re.search(rf'\s{_money_regex()}$', descricao)
        if moeda:
            metadados['moeda_original'] = 'USD'
            metadados['valor_moeda_original'] = _float_decimal(_parse_valor(moeda.group(1)))
            descricao = descricao[:moeda.start()].strip()

    descricao_sem_parcela, parcela_atual, total_parcelas = _parse_parcela(descricao)
    tipo = 'credito' if sufixo == 'C' else 'debito'
    status = 'ignorado' if tipo == 'credito' or valor == 0 else 'revisar'
    if tipo == 'credito':
        mensagens.append('Credito identificado; nao sera importado como despesa por padrao.')
    if valor == 0:
        mensagens.append('Lancamento com valor zero ignorado por padrao.')

    return {
        'linha_id': f'pdf-{pagina}-{numero_linha}',
        'linha_origem': numero_linha,
        'status': status,
        'data_compra': data_compra,
        'descricao_original': descricao,
        'descricao_normalizada': descricao_sem_parcela or descricao,
        'descricao_exibida': descricao_sem_parcela or descricao,
        'cartao_final': cartao_final,
        'grupo': grupo,
        'parcela_atual': parcela_atual,
        'total_parcelas': total_parcelas,
        'parcela': f'{parcela_atual}/{total_parcelas}',
        'valor': _float_decimal(abs(valor)),
        'tipo_movimento': tipo,
        'categoria_detectada': None,
        'categoria_despesa_id': None,
        'categoria_cartao_id': None,
        'item_agregado_id': None,
        'confianca_categoria': 'baixa',
        'duplicidade': None,
        'mensagens': mensagens,
        'metadados': metadados,
        'origem_importacao': 'pdf',
        'ignorar': status == 'ignorado',
        'gerar_parcelas_futuras': False,
    }


def _extrair_credito_pre_cartao(linha, competencia_base, pagina, numero_linha):
    texto_upper = linha.upper()
    if 'TOTAL DA FATURA ANTERIOR' in texto_upper or 'OBRIGADO PELO PAGAMENTO' in texto_upper:
        return None

    valor_match = re.search(rf'{_money_regex()}\s*C\b', linha, flags=re.IGNORECASE)
    data_match = re.search(r'(?<!\d)(\d{2}/\d{2})(?!\d)', linha)
    if not valor_match or not data_match:
        return None

    valor = _parse_valor(valor_match.group(1))
    if valor is None:
        return None

    descricao = linha[data_match.end():valor_match.start()].strip()
    descricao = re.sub(r'\s+', ' ', descricao)
    return {
        'linha_id': f'pdf-{pagina}-{numero_linha}',
        'linha_origem': numero_linha,
        'status': 'ignorado',
        'data_compra': _parse_data_com_ano(data_match.group(1), competencia_base),
        'descricao_original': descricao,
        'descricao_normalizada': descricao,
        'descricao_exibida': descricao,
        'cartao_final': None,
        'grupo': 'CREDITOS',
        'parcela_atual': 1,
        'total_parcelas': 1,
        'parcela': '1/1',
        'valor': _float_decimal(abs(valor)),
        'tipo_movimento': 'credito',
        'categoria_detectada': None,
        'categoria_despesa_id': None,
        'categoria_cartao_id': None,
        'item_agregado_id': None,
        'confianca_categoria': 'baixa',
        'duplicidade': None,
        'mensagens': ['Credito identificado; nao sera importado como despesa por padrao.'],
        'metadados': {
            'pagina': pagina,
            'linha_pdf': numero_linha,
            'linha_texto': linha,
        },
        'origem_importacao': 'pdf',
        'ignorar': True,
        'gerar_parcelas_futuras': False,
    }


def parse_texto_caixa(paginas_texto, competencia, arquivo_nome=None):
    competencia_base = _parse_competencia(competencia)
    texto_total = '\n'.join(paginas_texto or [])
    fatura = _extrair_metadados(texto_total)
    linhas = []
    ultimo_internacional = None

    for pagina, texto in enumerate(paginas_texto or [], start=1):
        if 'Demonstrativo' not in texto:
            continue

        cartao_atual = None
        grupo_atual = None
        for numero_linha, linha_bruta in enumerate(texto.splitlines(), start=1):
            linha = _limpar_linha(linha_bruta)
            if not linha:
                continue

            if _anexar_cotacao_internacional(linha, ultimo_internacional):
                continue

            cartao_match = re.search(r'\(Cart[aã]o\s+(\d{4})\)', linha, flags=re.IGNORECASE)
            if cartao_match:
                cartao_atual = cartao_match.group(1)
                if cartao_atual not in fatura['cartoes_detectados']:
                    fatura['cartoes_detectados'].append(cartao_atual)

            total_cartao = re.search(rf'Total final\s+\(cart[aã]o\s+(\d{{4}})\)\s+{_money_regex()}\s*([DC])', linha, flags=re.IGNORECASE)
            if total_cartao:
                fatura['totais_por_cartao'][total_cartao.group(1)] = {
                    'valor': _float_decimal(_parse_valor(total_cartao.group(2))),
                    'tipo': 'credito' if total_cartao.group(3).upper() == 'C' else 'debito',
                }
                continue

            total_grupo = re.search(rf'Total\s+(COMPRAS INTERNACIONAIS|COMPRAS PARCELADAS|COMPRAS)\s+{_money_regex()}\s*([DC])', linha, flags=re.IGNORECASE)
            if total_grupo and cartao_atual:
                chave = f'{cartao_atual}:{total_grupo.group(1).upper()}'
                fatura['totais_por_grupo'][chave] = {
                    'valor': _float_decimal(_parse_valor(total_grupo.group(2))),
                    'tipo': 'credito' if total_grupo.group(3).upper() == 'C' else 'debito',
                }
                continue

            total_fatura = re.search(rf'Valor total desta fatura\s+R\$\s*{_money_regex()}\s*([DC])', linha, flags=re.IGNORECASE)
            if total_fatura:
                fatura['valor_total'] = _float_decimal(_parse_valor(total_fatura.group(1)))
                continue

            if not cartao_atual:
                credito = _extrair_credito_pre_cartao(linha, competencia_base, pagina, numero_linha)
                if credito:
                    linhas.append(credito)
                continue

            grupo_detectado = _detectar_grupo(linha)
            if grupo_detectado:
                grupo_atual = grupo_detectado
                if not re.search(rf'{_money_regex()}\s*[DC]\b', linha, flags=re.IGNORECASE):
                    continue

            lancamento = _extrair_lancamento_linha(
                linha=linha,
                cartao_final=cartao_atual,
                grupo=grupo_atual,
                competencia_base=competencia_base,
                pagina=pagina,
                numero_linha=numero_linha,
            )
            if lancamento:
                linhas.append(lancamento)
                ultimo_internacional = lancamento if lancamento.get('grupo') == 'COMPRAS INTERNACIONAIS' else None

    fatura['cartoes_detectados'] = sorted(set(fatura['cartoes_detectados']))
    return {
        'origem': 'pdf',
        'arquivo_nome': arquivo_nome,
        'perfil_detectado': 'caixa_pdf',
        'requer_mapeamento': False,
        'fatura': fatura,
        'linhas': linhas,
        'total_linhas': len(linhas),
    }


def parse(file_storage, competencia=None):
    try:
        import pdfplumber
    except ImportError as exc:
        raise ValueError('Dependencia pdfplumber nao instalada. Execute pip install -r requirements.txt.') from exc

    if hasattr(file_storage, 'seek'):
        file_storage.seek(0)
    elif hasattr(file_storage, 'stream') and hasattr(file_storage.stream, 'seek'):
        file_storage.stream.seek(0)

    origem = getattr(file_storage, 'stream', file_storage)
    paginas_texto = []
    with pdfplumber.open(origem) as pdf:
        for page in pdf.pages:
            paginas_texto.append(page.extract_text(x_tolerance=1, y_tolerance=3) or '')

    if not any(paginas_texto):
        raise ValueError('PDF sem texto extraivel. OCR e PDF escaneado estao fora do escopo deste MVP.')

    return parse_texto_caixa(
        paginas_texto=paginas_texto,
        competencia=competencia,
        arquivo_nome=getattr(file_storage, 'filename', None),
    )
