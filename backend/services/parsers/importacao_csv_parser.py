import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

try:
    from backend.services.importacao_cartao_service import ImportacaoCartaoService
except ImportError:
    from services.importacao_cartao_service import ImportacaoCartaoService


def _valor_celula(linha, indice):
    if indice is None:
        return None
    try:
        return linha[indice]
    except (IndexError, TypeError):
        return None


def _parse_valor_decimal(valor):
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))

    texto = str(valor).strip()
    if not texto:
        return None
    texto = re.sub(r'[DC]$', '', texto, flags=re.IGNORECASE)
    texto = texto.replace('R$', '').replace(' ', '')
    if texto in {'', '-'}:
        return None
    if ',' in texto and '.' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    elif ',' in texto:
        texto = texto.replace(',', '.')
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return None


def _normalizar_data(valor):
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()

    texto = str(valor or '').strip()
    if not texto:
        return None

    for formato in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%d-%m-%Y', '%d.%m.%Y'):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except (ValueError, TypeError):
            continue
    return texto


def _parse_parcela(descricao, parcela_campo=None):
    descricao_normalizada, numero, total = ImportacaoCartaoService.normalizar_descricao(descricao or '')
    if parcela_campo:
        parsed = ImportacaoCartaoService._parse_parcela_texto(str(parcela_campo))
        if parsed:
            numero, total = parsed
    return descricao_normalizada, numero, total


def _montar_linha(idx, data, descricao, valor, tipo_movimento, parcela_campo=None, origem='csv'):
    descricao = str(descricao or '').strip()
    descricao_normalizada, numero_parcela, total_parcelas = _parse_parcela(descricao, parcela_campo)
    status = 'ignorado' if tipo_movimento == 'credito' else 'revisar'
    mensagens = []
    if tipo_movimento == 'credito':
        mensagens.append('Credito identificado; nao sera importado como despesa por padrao.')

    return {
        'linha_id': f'{origem}-{idx}',
        'linha_origem': idx,
        'status': status,
        'data_compra': _normalizar_data(data),
        'descricao_original': descricao,
        'descricao_normalizada': descricao_normalizada or descricao,
        'descricao_exibida': descricao_normalizada or descricao,
        'cartao_final': None,
        'grupo': None,
        'parcela_atual': numero_parcela,
        'total_parcelas': total_parcelas,
        'parcela': f'{numero_parcela}/{total_parcelas}',
        'valor': float(abs(valor)),
        'tipo_movimento': tipo_movimento,
        'categoria_detectada': None,
        'categoria_despesa_id': None,
        'categoria_cartao_id': None,
        'item_agregado_id': None,
        'confianca_categoria': 'baixa',
        'duplicidade': None,
        'mensagens': mensagens,
        'metadados': {},
        'origem_importacao': origem,
        'ignorar': tipo_movimento == 'credito',
        'gerar_parcelas_futuras': False,
    }


def converter_tabela_para_payload(colunas, linhas_dados, origem='csv', arquivo_nome=None):
    perfil_info = ImportacaoCartaoService.detectar_perfil_csv(colunas)
    perfil = perfil_info.get('perfil')
    mapeamento = perfil_info.get('mapeamento_sugerido') or {}

    payload = {
        'origem': origem,
        'arquivo_nome': arquivo_nome,
        'perfil_detectado': perfil,
        'autodeteccao_confianca': perfil_info.get('confianca'),
        'mapeamento_sugerido': mapeamento,
        'colunas': colunas,
        'linhas_dados': linhas_dados,
        'linhas_amostra': linhas_dados[:5],
        'total_linhas': len(linhas_dados),
        'requer_mapeamento': perfil == ImportacaoCartaoService.PERFIL_MANUAL,
        'fatura': {
            'emissor': None,
            'vencimento': None,
            'valor_total': None,
            'cartoes_detectados': [],
        },
        'linhas': [],
    }

    if payload['requer_mapeamento']:
        return payload

    for idx, linha in enumerate(linhas_dados, start=1):
        data = _valor_celula(linha, mapeamento.get('data_compra'))
        descricao = _valor_celula(linha, mapeamento.get('descricao'))
        parcela = _valor_celula(linha, mapeamento.get('parcela'))

        if perfil == ImportacaoCartaoService.PERFIL_CAIXA:
            debito = _parse_valor_decimal(_valor_celula(linha, mapeamento.get('debito')))
            credito = _parse_valor_decimal(_valor_celula(linha, mapeamento.get('credito')))
            if debito is not None and debito != 0:
                valor = debito
                tipo = 'debito'
            elif credito is not None and credito != 0:
                valor = credito
                tipo = 'credito'
            else:
                continue
        else:
            valor = _parse_valor_decimal(_valor_celula(linha, mapeamento.get('valor')))
            if valor is None or valor == 0:
                continue
            tipo = 'debito'

        if not data or not descricao:
            continue
        payload['linhas'].append(_montar_linha(idx, data, descricao, valor, tipo, parcela, origem))

    payload['total_linhas'] = len(payload['linhas']) or len(linhas_dados)
    return payload


def parse(file_storage, competencia=None):
    delimitador, colunas, linhas_dados, linhas_amostra, total_linhas = ImportacaoCartaoService.ler_csv(file_storage)
    payload = converter_tabela_para_payload(
        colunas=colunas,
        linhas_dados=linhas_dados,
        origem='csv',
        arquivo_nome=getattr(file_storage, 'filename', None),
    )
    payload['delimitador'] = delimitador
    payload['linhas_amostra'] = linhas_amostra
    payload['total_linhas'] = total_linhas if payload.get('requer_mapeamento') else len(payload['linhas'])
    return payload
