"""
ServiÃ§o de ImportaÃ§Ã£o Assistida de Fatura de CartÃ£o (CSV)

FASE 6.2 - ImportaÃ§Ã£o de CSV de fatura de cartÃ£o

Este serviÃ§o:
- Processa arquivo CSV de fatura
- Normaliza descriÃ§Ãµes
- Extrai parcelamento explÃ­cito
- Reconhece despesas fixas existentes
- Gera parcelas passadas, atual e futuras baseado na COMPETÃŠNCIA escolhida
- Garante idempotÃªncia total

REGRAS INVIOLÃVEIS:
âœ… Apenas cria LancamentoAgregado
âœ… NÃ£o cria Conta (fatura consolidada)
âœ… NÃ£o infere categorias automaticamente
âœ… NÃ£o calcula mes_fatura baseado em data - usa competÃªncia do usuÃ¡rio
âœ… Sistema 100% baseado em COMPETÃŠNCIA (nÃ£o em datas de fechamento)
"""

import re
import csv
import io
import uuid
import unicodedata
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, or_

try:
    from backend.models import db, ItemDespesa, LancamentoAgregado
    from backend.services.categoria_cartao_service import CategoriaCartaoService
    from backend.services.perfil_financeiro_service import PerfilFinanceiroService
except ImportError:
    from models import db, ItemDespesa, LancamentoAgregado
    from services.categoria_cartao_service import CategoriaCartaoService
    from services.perfil_financeiro_service import PerfilFinanceiroService


class ImportacaoCartaoService:
    """
    ServiÃ§o especializado em importar CSV de faturas de cartÃ£o
    """

    PERFIL_NUBANK = 'nubank_csv_simples'
    PERFIL_CAIXA = 'caixa_credito_debito'
    PERFIL_MANUAL = 'manual_generico'
    MAX_PARCELAS_IMPORTACAO = 60
    TERMOS_GENERICOS_MATCH = {
        'SAO', 'PAULO', 'BRASIL', 'COM', 'BILL', 'PAG', 'PAGAMENTO',
        'COMPRA', 'CARTAO', 'CARTAO', 'BR', 'BRA', 'LTDA', 'SA',
        'PAYPAL', 'PAGSEGURO', 'AUT', 'AUTORIZACAO'
    }
    FORNECEDORES_FORTES = [
        ('DIGITAL OCEAN', 'DIGITAL OCEAN', ('DIGITALOCEAN', 'DIGITALOCEA', 'DIGITAL OCEAN')),
        ('AMAZON', 'AMAZON MUSIC', ('AMAZONMUSIC', 'AMAZON MUSIC')),
        ('AMAZON', 'AMAZON PRIME', ('AMAZONPRIME', 'AMAZON PRIME', 'AMAZONPRIMEBR')),
        ('APPLE', None, ('APPLECOMBILL', 'APPLE COM BILL', 'APPLE BILL', 'APPLE')),
        ('NETFLIX', None, ('NETFLIX',)),
        ('GOOGLE', None, ('GOOGLE',)),
        ('MICROSOFT', None, ('MICROSOFT', 'MSFT')),
        ('OPENAI', 'CHATGPT', ('CHATGPT', 'OPENAI')),
        ('ALFA', 'ALFA SEGURAD', ('ALFASEGURAD', 'ALFA SEGURAD')),
        ('BRASIL PARAL', None, ('BRASILPARAL', 'BRASIL PARAL')),
        ('AMAZON', None, ('AMAZON',)),
    ]

    @staticmethod
    def _normalizar_coluna(coluna):
        texto = str(coluna or '').strip().lower()
        texto = texto.replace('\ufeff', '')
        texto = unicodedata.normalize('NFKD', texto)
        texto = ''.join(char for char in texto if not unicodedata.combining(char))
        texto = re.sub(r'\s+', ' ', texto)
        return texto.strip()

    @staticmethod
    def detectar_perfil_csv(colunas):
        """
        Detecta perfil com base no cabecalho do CSV.
        Retorna perfil + confianca + mapeamento sugerido (indices).
        """
        colunas_norm = [ImportacaoCartaoService._normalizar_coluna(c) for c in (colunas or [])]

        def idx_any(nomes):
            for nome in nomes:
                try:
                    return colunas_norm.index(nome)
                except ValueError:
                    continue
            return None

        nubank_map = {
            'data_compra': idx_any(['date']),
            'descricao': idx_any(['title']),
            'valor': idx_any(['amount']),
            'parcela': None,
            'credito': None,
            'debito': None
        }
        if all(v is not None for v in [nubank_map['data_compra'], nubank_map['descricao'], nubank_map['valor']]):
            return {
                'perfil': ImportacaoCartaoService.PERFIL_NUBANK,
                'confianca': 'alta',
                'mapeamento_sugerido': nubank_map
            }

        caixa_map = {
            'data_compra': idx_any(['data']),
            'descricao': idx_any(['descritivo']),
            'valor': None,
            'parcela': None,
            'credito': idx_any(['credito', 'cr?dito']),
            'debito': idx_any(['debito', 'd?bito'])
        }
        if all(v is not None for v in [caixa_map['data_compra'], caixa_map['descricao'], caixa_map['credito'], caixa_map['debito']]):
            return {
                'perfil': ImportacaoCartaoService.PERFIL_CAIXA,
                'confianca': 'alta',
                'mapeamento_sugerido': caixa_map
            }

        return {
            'perfil': ImportacaoCartaoService.PERFIL_MANUAL,
            'confianca': 'baixa',
            'mapeamento_sugerido': {
                'data_compra': None,
                'descricao': None,
                'valor': None,
                'parcela': None,
                'credito': None,
                'debito': None
            }
        }

    # ========================================================================
    # NORMALIZAÃ‡ÃƒO E EXTRAÃ‡ÃƒO
    # ========================================================================

    @staticmethod
    def detectar_parcelamento_texto(descricao_bruta):
        texto = str(descricao_bruta or '').strip()
        if not texto:
            return None

        padroes = [
            r'\b(?:PARC(?:ELA)?\.?)\s*(\d{1,2})\s*(?:/|DE)\s*(\d{1,2})\b',
            r'\b(\d{1,2})\s*/\s*(\d{1,2})\b',
            r'\b(\d{1,2})\s+DE\s+(\d{1,2})\b',
        ]

        for padrao in padroes:
            match = re.search(padrao, texto, re.IGNORECASE)
            if not match:
                continue

            numero_parcela = int(match.group(1))
            total_parcelas = int(match.group(2))
            if (
                numero_parcela < 1
                or total_parcelas <= 1
                or numero_parcela > total_parcelas
                or total_parcelas > ImportacaoCartaoService.MAX_PARCELAS_IMPORTACAO
            ):
                return None

            descricao_limpa = f'{texto[:match.start()]} {texto[match.end():]}'.strip()
            descricao_limpa = re.sub(r'\s+', ' ', descricao_limpa).strip(' -–|')

            return {
                'eh_parcelamento': True,
                'parcela_atual': numero_parcela,
                'total_parcelas': total_parcelas,
                'padrao_detectado': match.group(0),
                'descricao_limpa': descricao_limpa or texto,
            }

        return None

    @staticmethod
    def normalizar_descricao(descricao_bruta):
        """
        Normaliza descriÃ§Ã£o e extrai informaÃ§Ãµes de parcelamento

        Formatos reconhecidos:
        - NN/TT
        - N/T
        - NN DE TT
        - N DE T

        Args:
            descricao_bruta (str): Texto original do CSV

        Returns:
            tuple: (descricao_normalizada, numero_parcela, total_parcelas)
                Se nÃ£o houver parcelamento: (descricao, 1, 1)
        """
        descricao = descricao_bruta.strip()

        detectado = ImportacaoCartaoService.detectar_parcelamento_texto(descricao)
        if detectado:
            return (
                detectado['descricao_limpa'],
                detectado['parcela_atual'],
                detectado['total_parcelas'],
            )

        # Sem parcelamento explÃ­cito
        return descricao, 1, 1

    @staticmethod
    def detectar_delimitador(conteudo_csv):
        """
        Detecta o delimitador do CSV (;, vÃ­rgula, tab)

        Args:
            conteudo_csv (str): ConteÃºdo bruto do CSV

        Returns:
            str: Delimitador detectado
        """
        sniffer = csv.Sniffer()
        amostra = '\n'.join(conteudo_csv.split('\n')[:5])  # Primeiras 5 linhas

        try:
            dialeto = sniffer.sniff(amostra, delimiters=';,\t')
            return dialeto.delimiter
        except:
            # Fallback: ponto-e-vÃ­rgula (padrÃ£o brasileiro)
            return ';'

    @staticmethod
    def ler_csv(arquivo_csv):
        """
        LÃª arquivo CSV e retorna cabeÃ§alho + linhas

        Args:
            arquivo_csv: FileStorage do Flask ou conteÃºdo string

        Returns:
            tuple: (delimitador, colunas, linhas_dados, linhas_amostra, total_linhas)
        """
        # Ler conteÃºdo
        if hasattr(arquivo_csv, 'read'):
            conteudo_bytes = arquivo_csv.read()
            conteudo = None
            for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
                try:
                    conteudo = conteudo_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if conteudo is None:
                conteudo = conteudo_bytes.decode('utf-8', errors='ignore')
            arquivo_csv.seek(0)  # Resetar para leitura posterior
        else:
            conteudo = arquivo_csv

        # Detectar delimitador
        delimitador = ImportacaoCartaoService.detectar_delimitador(conteudo)

        # Ler CSV
        leitor = csv.reader(io.StringIO(conteudo), delimiter=delimitador)

        linhas = list(leitor)
        if not linhas:
            raise ValueError("CSV vazio")

        colunas = linhas[0]
        linhas_dados = [linha for linha in linhas[1:] if any(str(c).strip() for c in linha)]
        linhas_amostra = linhas_dados[:5]  # Primeiras 5 linhas de dados
        total_linhas = len(linhas_dados)

        return delimitador, colunas, linhas_dados, linhas_amostra, total_linhas

    # ========================================================================
    # RECONHECIMENTO DE DESPESAS FIXAS
    # ========================================================================

    @staticmethod
    def reconhecer_despesa_fixa(descricao_normalizada, cartao_id):
        """
        Verifica se a descriÃ§Ã£o corresponde a uma despesa fixa jÃ¡ cadastrada

        Args:
            descricao_normalizada (str): DescriÃ§Ã£o sem parcelamento
            cartao_id (int): ID do cartÃ£o

        Returns:
            ItemDespesa ou None: Despesa fixa encontrada, ou None
        """
        despesa_fixa = ItemDespesa.query.filter(
            ItemDespesa.recorrente == True,
            PerfilFinanceiroService.condicao_perfil(ItemDespesa),
            ItemDespesa.meio_pagamento == 'cartao',
            ItemDespesa.cartao_id == cartao_id,
            func.lower(ItemDespesa.nome) == descricao_normalizada.lower()
        ).first()

        return despesa_fixa

    # ========================================================================
    # GERAÃ‡ÃƒO DE PARCELAS
    # ========================================================================

    @staticmethod
    def gerar_parcelas(
        descricao_normalizada,
        descricao_exibida,
        descricao_original,
        valor_total,
        data_compra,
        numero_parcela_atual,
        total_parcelas,
        cartao_id,
        categoria_id,
        competencia_base,
        categoria_cartao_id=None,
        compra_id=None,
        origem_importacao='csv',
        numero_inicial=1
    ):
        """
        Gera parcelas de uma compra.

        Args:
            descricao_normalizada (str): DescriÃ§Ã£o sem parcelamento
            descricao_exibida (str): DescriÃ§Ã£o editÃ¡vel
            descricao_original (str): Texto bruto do CSV
            valor_total (Decimal): Valor da parcela
            data_compra (date): Data original da compra
            numero_parcela_atual (int): NÃºmero da parcela lida do CSV
            total_parcelas (int): Total de parcelas
            cartao_id (int): ID do cartÃ£o
            categoria_id (int): Categoria da despesa
            categoria_cartao_id (int): Categoria do cartao global (opcional)
            competencia_base (date): CompetÃªncia escolhida pelo usuÃ¡rio (YYYY-MM-01)
            compra_id (str): UUID da compra (se None, gera novo)

        Returns:
            list: Lista de dicts representando parcelas
        """
        if not compra_id:
            compra_id = str(uuid.uuid4())

        parcelas = []
        try:
            numero_inicial = int(numero_inicial or 1)
        except (TypeError, ValueError):
            numero_inicial = 1
        numero_inicial = max(1, min(numero_inicial, total_parcelas))

        for numero in range(numero_inicial, total_parcelas + 1):
            # Calcular meses de diferenÃ§a em relaÃ§Ã£o Ã  parcela atual
            meses_diff = numero - numero_parcela_atual

            # Data de compra desta parcela
            data_parcela = data_compra + relativedelta(months=meses_diff)

            # MÃªs de fatura: usar competÃªncia base + diferenÃ§a de meses
            mes_fatura = competencia_base + relativedelta(months=meses_diff)

            parcela = {
                'descricao': descricao_normalizada,
                'descricao_original': descricao_original,
                'descricao_original_normalizada': descricao_normalizada,
                'descricao_exibida': f"{descricao_exibida} ({numero}/{total_parcelas})" if total_parcelas > 1 else descricao_exibida,
                'valor': valor_total,
                'data_compra': data_parcela,
                'mes_fatura': mes_fatura,
                'numero_parcela': numero,
                'total_parcelas': total_parcelas,
                'cartao_id': cartao_id,
                'categoria_id': categoria_id,
                'categoria_cartao_id': categoria_cartao_id,
                'compra_id': compra_id,
                'is_importado': True,
                'origem_importacao': origem_importacao
            }

            parcelas.append(parcela)

        return parcelas

    # ========================================================================
    # PROCESSAMENTO E PERSISTÃŠNCIA
    # ========================================================================

    @staticmethod
    def _parse_valor(valor_str):
        """
        Converte string monetaria para Decimal de forma pragmatica.
        Aceita formatos como:
        - 1234.56
        - 1.234,56
        - 1234,56
        """
        if valor_str is None:
            raise InvalidOperation("Valor ausente")

        valor_limpo = str(valor_str).strip().replace('R$', '').replace(' ', '')
        if ',' in valor_limpo and '.' in valor_limpo:
            valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
        elif ',' in valor_limpo:
            valor_limpo = valor_limpo.replace(',', '.')

        return Decimal(valor_limpo)

    @staticmethod
    def _parse_data_compra(data_str):
        if isinstance(data_str, date):
            return data_str

        formatos_data = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']
        for formato in formatos_data:
            try:
                return datetime.strptime(str(data_str or '').strip(), formato).date()
            except (ValueError, TypeError):
                continue
        raise ValueError(f'Data invalida: {data_str}')

    @staticmethod
    def _parse_parcela_texto(parcela_str):
        if not parcela_str:
            return None
        detectado = ImportacaoCartaoService.detectar_parcelamento_texto(parcela_str)
        if detectado:
            return detectado['parcela_atual'], detectado['total_parcelas']
        return None

    @staticmethod
    def normalizar_texto_match(texto):
        texto = str(texto or '').strip().upper()
        texto = unicodedata.normalize('NFKD', texto)
        texto = ''.join(char for char in texto if not unicodedata.combining(char))
        texto = re.sub(r'[^A-Z0-9]+', ' ', texto)
        texto = re.sub(r'\b\d{6,}\b', ' ', texto)
        texto = re.sub(r'\s+', ' ', texto).strip()
        return texto

    @staticmethod
    def extrair_assinatura_flexivel(descricao):
        normalizada = ImportacaoCartaoService.normalizar_texto_match(descricao)
        compacta = normalizada.replace(' ', '')

        keyword_principal = None
        keyword_secundaria = None
        for principal, secundaria, padroes in ImportacaoCartaoService.FORNECEDORES_FORTES:
            if any(padrao.replace(' ', '') in compacta or padrao in normalizada for padrao in padroes):
                keyword_principal = principal
                keyword_secundaria = secundaria
                break

        tokens = [
            token for token in normalizada.split()
            if token not in ImportacaoCartaoService.TERMOS_GENERICOS_MATCH and len(token) > 1
        ]

        if not keyword_principal and tokens:
            keyword_principal = tokens[0]
            if len(tokens) > 1:
                keyword_secundaria = f'{tokens[0]} {tokens[1]}'

        return {
            'descricao_normalizada': normalizada,
            'tokens': tokens,
            'keyword_principal': keyword_principal,
            'keyword_secundaria': keyword_secundaria,
            'keywords': [item for item in [keyword_principal, keyword_secundaria] if item]
        }

    @staticmethod
    def _valores_proximos(valor_a, valor_b):
        try:
            a = Decimal(str(valor_a)).quantize(Decimal('0.01'))
            b = Decimal(str(valor_b)).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError, ValueError):
            return False
        return abs(a - b) <= Decimal('0.01')

    @staticmethod
    def _descricao_parecida(assinatura_a, assinatura_b):
        tokens_a = set(assinatura_a.get('tokens') or [])
        tokens_b = set(assinatura_b.get('tokens') or [])
        if not tokens_a or not tokens_b:
            return False
        intersecao = tokens_a.intersection(tokens_b)
        return len(intersecao) >= 1 and (len(intersecao) / max(len(tokens_a), len(tokens_b))) >= 0.34

    @staticmethod
    def _fornecedor_compativel(assinatura_a, assinatura_b):
        keywords_a = set(assinatura_a.get('keywords') or [])
        keywords_b = set(assinatura_b.get('keywords') or [])
        if keywords_a and keywords_b and keywords_a.intersection(keywords_b):
            return True
        return ImportacaoCartaoService._descricao_parecida(assinatura_a, assinatura_b)

    @staticmethod
    def _decisao_alias(candidato):
        descricao = ImportacaoCartaoService.normalizar_texto_match(candidato.get('descricao_exibida'))
        tipo = 'parcelamento' if int(candidato.get('total_parcelas') or 1) > 1 else 'despesa_avulsa'
        if candidato.get('origem') == 'recorrencia' or candidato.get('is_recorrente'):
            tipo = 'recorrencia'
        return (
            descricao,
            int(candidato.get('categoria_id') or 0),
            tipo,
        )

    @staticmethod
    def _score_candidato_match(linha_match, candidato):
        score = 0
        motivos = []
        assinatura_linha = linha_match['assinatura']
        assinatura_candidato = candidato['assinatura']

        if ImportacaoCartaoService._valores_proximos(linha_match['valor'], candidato['valor']):
            score += 50
            motivos.append('valor igual/proximo')

        if int(linha_match['cartao_id']) == int(candidato.get('cartao_id') or 0):
            score += 20
            motivos.append('mesmo cartao')

        keywords_linha = set(assinatura_linha.get('keywords') or [])
        keywords_candidato = set(assinatura_candidato.get('keywords') or [])
        if keywords_linha and keywords_linha.intersection(keywords_candidato):
            score += 20
            motivos.append('palavra-chave forte igual')

        if ImportacaoCartaoService._descricao_parecida(assinatura_linha, assinatura_candidato):
            score += 10
            motivos.append('descricao normalizada parecida')

        if (
            linha_match.get('numero_parcela')
            and candidato.get('numero_parcela')
            and int(linha_match['numero_parcela']) == int(candidato['numero_parcela'])
            and int(linha_match.get('total_parcelas') or 1) == int(candidato.get('total_parcelas') or 1)
        ):
            score += 20
            motivos.append('mesma parcela/total')

        if linha_match.get('competencia') and candidato.get('mes_fatura') == linha_match.get('competencia'):
            score += 10
            motivos.append('mesma competencia/fatura')

        if linha_match.get('categoria_id') and candidato.get('categoria_id') == linha_match.get('categoria_id'):
            score += 5
            motivos.append('categoria igual')

        desc_amigavel_linha = ImportacaoCartaoService.normalizar_texto_match(linha_match.get('descricao_exibida'))
        desc_amigavel_candidato = ImportacaoCartaoService.normalizar_texto_match(candidato.get('descricao_exibida'))
        if desc_amigavel_linha and desc_amigavel_linha == desc_amigavel_candidato:
            score += 5
            motivos.append('descricao amigavel igual')

        return score, motivos

    @staticmethod
    def _montar_linha_match(linha, cartao_id, competencia):
        descricao_original = (
            linha.get('descricao_original')
            or linha.get('descricao_cartao')
            or linha.get('descricao')
            or linha.get('descricao_exibida')
            or ''
        )
        descricao_limpa, numero_parcela, total_parcelas = ImportacaoCartaoService.normalizar_descricao(descricao_original)
        numero_manual = linha.get('numero_parcela')
        total_manual = linha.get('total_parcelas')
        if numero_manual and total_manual:
            try:
                numero_parcela = int(numero_manual)
                total_parcelas = int(total_manual)
            except (TypeError, ValueError):
                pass

        return {
            'indice': linha.get('indice'),
            'cartao_id': cartao_id,
            'competencia': competencia,
            'valor': ImportacaoCartaoService._parse_valor(linha.get('valor')),
            'descricao_original': descricao_original,
            'descricao_exibida': linha.get('descricao_exibida') or linha.get('descricao') or descricao_limpa,
            'assinatura': ImportacaoCartaoService.extrair_assinatura_flexivel(descricao_original),
            'numero_parcela': numero_parcela,
            'total_parcelas': total_parcelas,
            'categoria_id': linha.get('categoria_id') or linha.get('categoria_despesa_id'),
        }

    @staticmethod
    def _candidato_lancamento_match(lancamento):
        descricao_ref = (
            lancamento.descricao_original_normalizada
            or lancamento.descricao_original
            or lancamento.descricao_exibida
            or lancamento.descricao
        )
        return {
            'origem': 'lancamento',
            'id': lancamento.id,
            'cartao_id': lancamento.cartao_id,
            'valor': lancamento.valor,
            'descricao_original': lancamento.descricao_original,
            'descricao_exibida': lancamento.descricao_exibida or lancamento.descricao,
            'assinatura': ImportacaoCartaoService.extrair_assinatura_flexivel(descricao_ref),
            'numero_parcela': lancamento.numero_parcela,
            'total_parcelas': lancamento.total_parcelas,
            'mes_fatura': lancamento.mes_fatura,
            'categoria_id': lancamento.categoria_id,
            'categoria_cartao_id': lancamento.categoria_cartao_id,
            'is_recorrente': lancamento.is_recorrente,
            'item_despesa_id': lancamento.item_despesa_id,
        }

    @staticmethod
    def _candidato_recorrencia_match(item):
        valor = item.valor_pago or item.valor
        return {
            'origem': 'recorrencia',
            'id': item.id,
            'cartao_id': item.cartao_id,
            'valor': valor,
            'descricao_original': item.descricao or item.nome,
            'descricao_exibida': item.nome,
            'assinatura': ImportacaoCartaoService.extrair_assinatura_flexivel(f'{item.nome} {item.descricao or ""}'),
            'numero_parcela': 1,
            'total_parcelas': 1,
            'mes_fatura': None,
            'categoria_id': item.categoria_id,
            'categoria_cartao_id': item.categoria_cartao_id,
            'is_recorrente': True,
            'item_despesa_id': item.id,
        }

    @staticmethod
    def reconhecer_linhas_flexivel(linhas, cartao_id, competencia):
        reconhecimentos = []
        for idx, linha in enumerate(linhas, start=1):
            try:
                linha_match = ImportacaoCartaoService._montar_linha_match(linha, cartao_id, competencia)
            except (InvalidOperation, ValueError, TypeError):
                continue

            valor = Decimal(str(linha_match['valor'])).quantize(Decimal('0.01'))
            valor_min = valor - Decimal('0.01')
            valor_max = valor + Decimal('0.01')

            lancamentos = LancamentoAgregado.query.filter(
                PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
                LancamentoAgregado.valor >= valor_min,
                LancamentoAgregado.valor <= valor_max,
            ).order_by(LancamentoAgregado.id.desc()).limit(200).all()

            recorrencias = ItemDespesa.query.filter(
                PerfilFinanceiroService.condicao_perfil(ItemDespesa),
                ItemDespesa.recorrente == True,  # noqa: E712
                ItemDespesa.ativo == True,  # noqa: E712
                or_(ItemDespesa.tipo.is_(None), ItemDespesa.tipo != 'Agregador'),
            ).all()

            candidatos = [ImportacaoCartaoService._candidato_lancamento_match(item) for item in lancamentos]
            for item in recorrencias:
                if item.valor is None and item.valor_pago is None:
                    continue
                if ImportacaoCartaoService._valores_proximos(valor, item.valor_pago or item.valor):
                    candidatos.append(ImportacaoCartaoService._candidato_recorrencia_match(item))

            melhor = None
            sugestoes = []
            for candidato in candidatos:
                score, motivos = ImportacaoCartaoService._score_candidato_match(linha_match, candidato)
                if score < 60:
                    continue
                fornecedor_compativel = ImportacaoCartaoService._fornecedor_compativel(
                    linha_match['assinatura'],
                    candidato['assinatura']
                )
                tipo = 'historico'
                if candidato.get('origem') == 'recorrencia' or candidato.get('is_recorrente'):
                    tipo = 'recorrencia'
                if (
                    candidato.get('mes_fatura') == competencia
                    and int(candidato.get('cartao_id') or 0) == int(cartao_id)
                    and score >= 80
                    and fornecedor_compativel
                ):
                    tipo = 'duplicado_atual'
                if candidato.get('total_parcelas', 1) and int(candidato.get('total_parcelas') or 1) > 1:
                    tipo = 'parcelamento_existente' if tipo != 'duplicado_atual' else tipo

                tratamento_sugerido = 'despesa_avulsa'
                if tipo == 'recorrencia':
                    tratamento_sugerido = 'recorrencia'
                elif tipo == 'parcelamento_existente':
                    tratamento_sugerido = 'parcelamento'

                sugestao = {
                    'indice': linha.get('indice', idx - 1),
                    'tipo': tipo,
                    'tipo_sugerido': tratamento_sugerido,
                    'origem_alias': 'historico_lancamento' if candidato.get('origem') == 'lancamento' else candidato.get('origem'),
                    'score': score,
                    'confianca': 'alta' if score >= 80 and fornecedor_compativel else 'media',
                    'motivos': motivos if fornecedor_compativel or score < 80 else motivos + ['alta confianca exige fornecedor compativel'],
                    'keyword_principal': linha_match['assinatura'].get('keyword_principal'),
                    'keyword_secundaria': linha_match['assinatura'].get('keyword_secundaria'),
                    'descricao_original': linha_match['descricao_original'],
                    'descricao_sugerida': candidato.get('descricao_exibida'),
                    'descricao_original_referencia': candidato.get('descricao_original'),
                    'valor_referencia': float(candidato.get('valor')) if candidato.get('valor') is not None else None,
                    'categoria_id': candidato.get('categoria_id'),
                    'categoria_cartao_id': candidato.get('categoria_cartao_id'),
                    'cartao_id_referencia': candidato.get('cartao_id'),
                    'mes_fatura_referencia': candidato.get('mes_fatura').isoformat() if candidato.get('mes_fatura') else None,
                    'numero_parcela_referencia': candidato.get('numero_parcela'),
                    'total_parcelas_referencia': candidato.get('total_parcelas'),
                    'origem': candidato.get('origem'),
                    'referencia_id': candidato.get('id'),
                    'item_despesa_id': candidato.get('item_despesa_id'),
                    '_decisao_alias': ImportacaoCartaoService._decisao_alias(candidato),
                }
                sugestoes.append(sugestao)
                if not melhor or sugestao['score'] > melhor['score']:
                    melhor = sugestao

            if melhor:
                candidatos_conflitantes = [
                    item for item in sugestoes
                    if item['score'] >= max(60, melhor['score'] - 10)
                    and item.get('_decisao_alias') != melhor.get('_decisao_alias')
                ]
                if candidatos_conflitantes:
                    melhor['confianca'] = 'revisar'
                    melhor['tipo'] = 'historico'
                    melhor['score'] = min(melhor['score'], 79)
                    melhor['motivos'] = list(melhor.get('motivos') or []) + ['historico com decisoes conflitantes']

                melhor.pop('_decisao_alias', None)
                reconhecimentos.append(melhor)

        return reconhecimentos

    @staticmethod
    def vincular_linha_recorrencia(linha, cartao_id, competencia, item_despesa_id):
        """
        Cria a ocorrencia de cartao vinculada a uma recorrencia existente.
        Nao altera a recorrencia matriz e nao cria despesa avulsa paralela.
        """
        if not linha:
            raise ValueError('Linha da importacao ausente')

        recorrencia = ItemDespesa.query.filter(
            PerfilFinanceiroService.condicao_perfil(ItemDespesa),
            ItemDespesa.id == item_despesa_id,
            ItemDespesa.recorrente == True,  # noqa: E712
            ItemDespesa.ativo == True,  # noqa: E712
            or_(ItemDespesa.tipo.is_(None), ItemDespesa.tipo != 'Agregador'),
        ).first()
        if not recorrencia:
            raise ValueError('Recorrencia nao encontrada ou inativa')

        if recorrencia.cartao_id and int(recorrencia.cartao_id) != int(cartao_id):
            raise ValueError('Recorrencia vinculada a outro cartao')

        categoria_id = recorrencia.categoria_id
        if not categoria_id:
            raise ValueError('Recorrencia sem Categoria da Despesa')

        resolucao_cartao = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
            cartao_id=cartao_id,
            categoria_id=categoria_id,
            categoria_cartao_id=recorrencia.categoria_cartao_id,
        )
        categoria_cartao_id = resolucao_cartao.get('categoria_cartao_id')

        data_compra = ImportacaoCartaoService._parse_data_compra(linha.get('data_compra'))
        valor = ImportacaoCartaoService._parse_valor(linha.get('valor'))
        descricao_original = (
            linha.get('descricao_original')
            or linha.get('descricao_cartao')
            or linha.get('descricao')
            or linha.get('descricao_exibida')
            or recorrencia.nome
        )
        descricao_normalizada, numero_parcela, total_parcelas = ImportacaoCartaoService.normalizar_descricao(descricao_original)
        if linha.get('numero_parcela') and linha.get('total_parcelas'):
            try:
                numero_parcela = int(linha.get('numero_parcela'))
                total_parcelas = int(linha.get('total_parcelas'))
            except (TypeError, ValueError):
                raise ValueError('Parametros de parcela invalidos')

        existente_recorrencia = LancamentoAgregado.query.filter(
            PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
            LancamentoAgregado.cartao_id == cartao_id,
            LancamentoAgregado.mes_fatura == competencia,
            LancamentoAgregado.item_despesa_id == recorrencia.id,
        ).first()
        if existente_recorrencia:
            return {
                'criado': False,
                'duplicado': True,
                'lancamento': existente_recorrencia.to_dict(),
                'recorrencia': recorrencia.to_dict(),
                'message': 'Recorrencia ja possui lancamento nesta fatura',
            }

        lancamento_base = {
            'cartao_id': cartao_id,
            'categoria_id': categoria_id,
            'categoria_cartao_id': categoria_cartao_id,
            'descricao': descricao_normalizada,
            'descricao_original': descricao_original,
            'descricao_original_normalizada': descricao_normalizada,
            'descricao_exibida': recorrencia.nome,
            'valor': valor,
            'data_compra': data_compra,
            'mes_fatura': competencia,
            'numero_parcela': numero_parcela,
            'total_parcelas': total_parcelas,
            'compra_id': str(uuid.uuid4()),
            'is_importado': True,
            'origem_importacao': 'recorrencia',
            'is_recorrente': True,
            'item_despesa_id': recorrencia.id,
        }

        if ImportacaoCartaoService._existe_duplicado_banco(lancamento_base):
            return {
                'criado': False,
                'duplicado': True,
                'lancamento': None,
                'recorrencia': recorrencia.to_dict(),
                'message': 'Lancamento equivalente ja existe na fatura',
            }

        novo_lancamento = LancamentoAgregado(
            perfil_financeiro_id=PerfilFinanceiroService.obter_perfil_ativo_id(),
            descricao=lancamento_base['descricao'],
            descricao_original=lancamento_base['descricao_original'],
            descricao_original_normalizada=lancamento_base['descricao_original_normalizada'],
            descricao_exibida=lancamento_base['descricao_exibida'],
            valor=lancamento_base['valor'],
            data_compra=lancamento_base['data_compra'],
            mes_fatura=lancamento_base['mes_fatura'],
            numero_parcela=lancamento_base['numero_parcela'],
            total_parcelas=lancamento_base['total_parcelas'],
            cartao_id=lancamento_base['cartao_id'],
            categoria_id=lancamento_base['categoria_id'],
            item_agregado_id=None,
            categoria_cartao_id=lancamento_base['categoria_cartao_id'],
            compra_id=lancamento_base['compra_id'],
            is_importado=True,
            origem_importacao='recorrencia',
            is_recorrente=True,
            item_despesa_id=recorrencia.id,
        )
        db.session.add(novo_lancamento)
        db.session.commit()

        try:
            from backend.services.cartao_service import CartaoService
        except ImportError:
            from services.cartao_service import CartaoService
        CartaoService.recalcular_fatura(cartao_id, competencia)

        return {
            'criado': True,
            'duplicado': False,
            'lancamento': novo_lancamento.to_dict(),
            'recorrencia': recorrencia.to_dict(),
            'categoria_cartao_id': categoria_cartao_id,
            'categoria_cartao_origem': resolucao_cartao.get('origem'),
        }

    @staticmethod
    def sugerir_categoria_por_descricao(descricao_bruta, categoria_fallback_id=None):
        descricao_normalizada, _, _ = ImportacaoCartaoService.normalizar_descricao(descricao_bruta or '')
        if not descricao_normalizada:
            return categoria_fallback_id, 'fallback'

        registro = LancamentoAgregado.query.filter(
            func.lower(
                func.coalesce(
                    LancamentoAgregado.descricao_original_normalizada,
                    LancamentoAgregado.descricao
                )
            ) == descricao_normalizada.lower(),
            LancamentoAgregado.categoria_id.isnot(None),
            PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
        ).order_by(LancamentoAgregado.id.desc()).first()

        if registro and registro.categoria_id:
            return int(registro.categoria_id), 'historico'

        return categoria_fallback_id, 'fallback'

    @staticmethod
    def processar_linhas_mapeadas(linhas_mapeadas, cartao_id, competencia_alvo):
        """
        Processa linhas jÃ¡ mapeadas e gera lanÃ§amentos

        Args:
            linhas_mapeadas (list): Lista de dicts com campos mapeados
            cartao_id (int): ID do cartÃ£o
            competencia_alvo (date): MÃªs de competÃªncia (YYYY-MM-01)

        Returns:
            dict: {
                'lancamentos': list,
                'linhas_invalidas': list,
                'total_linhas_recebidas': int
            }
        """
        lancamentos = []
        linhas_invalidas = []

        for idx, linha in enumerate(linhas_mapeadas, start=1):
            if linha.get('ignorar'):
                continue

            # Extrair campos
            data_compra_str = linha.get('data_compra')
            descricao_bruta = linha.get('descricao')
            valor_str = linha.get('valor')
            parcela_str = linha.get('parcela', '1/1')  # Opcional
            categoria_id = linha.get('categoria_id')
            categoria_cartao_id = linha.get('categoria_cartao_id')
            origem_importacao = linha.get('origem_importacao') or 'csv'

            # Validar obrigatÃ³rios
            if not all([data_compra_str, descricao_bruta, valor_str, categoria_id]):
                linhas_invalidas.append({
                    'linha': idx,
                    'erro': 'Campos obrigatorios ausentes (data_compra, descricao, valor, categoria_id)'
                })
                continue

            # Parsear data (tentar mÃºltiplos formatos)
            data_compra = None
            formatos_data = ['%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']

            for formato in formatos_data:
                try:
                    data_compra = datetime.strptime(data_compra_str, formato).date()
                    break
                except (ValueError, TypeError):
                    continue

            if not data_compra:
                linhas_invalidas.append({
                    'linha': idx,
                    'erro': f'Data invalida: {data_compra_str}'
                })
                continue  # Data invÃ¡lida - pular linha

            # Parsear valor
            try:
                valor = ImportacaoCartaoService._parse_valor(valor_str)
            except (InvalidOperation, ValueError):
                linhas_invalidas.append({
                    'linha': idx,
                    'erro': f'Valor invalido: {valor_str}'
                })
                continue  # Valor invÃ¡lido

            # Normalizar descriÃ§Ã£o e extrair parcelamento
            descricao_normalizada, numero_parcela, total_parcelas = ImportacaoCartaoService.normalizar_descricao(descricao_bruta)

            numero_parcela_manual = linha.get('numero_parcela')
            total_parcelas_manual = linha.get('total_parcelas')
            if numero_parcela_manual and total_parcelas_manual:
                try:
                    numero_parcela = int(numero_parcela_manual)
                    total_parcelas = int(total_parcelas_manual)
                except (ValueError, TypeError):
                    linhas_invalidas.append({
                        'linha': idx,
                        'erro': 'Parametros de parcela invalidos'
                    })
                    continue
            else:
                parsed = ImportacaoCartaoService._parse_parcela_texto(parcela_str)
                if parsed:
                    numero_parcela, total_parcelas = parsed

            if numero_parcela < 1 or total_parcelas < 1 or numero_parcela > total_parcelas:
                linhas_invalidas.append({
                    'linha': idx,
                    'erro': f'Parcela fora do intervalo: {numero_parcela}/{total_parcelas}'
                })
                continue
            if total_parcelas > ImportacaoCartaoService.MAX_PARCELAS_IMPORTACAO:
                linhas_invalidas.append({
                    'linha': idx,
                    'erro': f'Total de parcelas acima do limite: {total_parcelas}'
                })
                continue

            resolucao_cartao = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
                cartao_id=cartao_id,
                categoria_id=categoria_id,
                categoria_cartao_id=categoria_cartao_id,
            )
            categoria_cartao_id = resolucao_cartao.get('categoria_cartao_id')

            # Reconhecer despesa fixa
            despesa_fixa = ImportacaoCartaoService.reconhecer_despesa_fixa(descricao_normalizada, cartao_id)
            is_recorrente = despesa_fixa is not None
            item_despesa_id = despesa_fixa.id if despesa_fixa else None

            # Gerar todas as parcelas (passadas, atual, futuras)
            gerar_futuras = bool(linha.get('gerar_parcelas_futuras'))
            if gerar_futuras and total_parcelas > 1:
                numero_inicial = numero_parcela if linha.get('gerar_apenas_atual_e_futuras') else 1
                parcelas = ImportacaoCartaoService.gerar_parcelas(
                    descricao_normalizada=descricao_normalizada,
                    descricao_exibida=linha.get('descricao_exibida', descricao_normalizada),
                    descricao_original=descricao_bruta,
                    valor_total=valor,
                    data_compra=data_compra,
                    numero_parcela_atual=numero_parcela,
                    total_parcelas=total_parcelas,
                    cartao_id=cartao_id,
                    categoria_id=categoria_id,
                    competencia_base=competencia_alvo,
                    categoria_cartao_id=categoria_cartao_id,
                    compra_id=None,
                    origem_importacao=origem_importacao,
                    numero_inicial=numero_inicial
                )
            else:
                compra_id = str(uuid.uuid4())
                parcelas = [{
                    'descricao': descricao_normalizada,
                    'descricao_original': descricao_bruta,
                    'descricao_original_normalizada': descricao_normalizada,
                    'descricao_exibida': linha.get('descricao_exibida', descricao_normalizada),
                    'valor': valor,
                    'data_compra': data_compra,
                    'mes_fatura': competencia_alvo,
                    'numero_parcela': numero_parcela,
                    'total_parcelas': total_parcelas,
                    'cartao_id': cartao_id,
                    'categoria_id': categoria_id,
                    'categoria_cartao_id': categoria_cartao_id,
                    'compra_id': compra_id,
                    'is_importado': True,
                    'origem_importacao': origem_importacao
                }]

            # Adicionar flag de recorrÃªncia
            for parcela in parcelas:
                parcela['is_recorrente'] = is_recorrente
                parcela['item_despesa_id'] = item_despesa_id

            lancamentos.extend(parcelas)

        return {
            'lancamentos': lancamentos,
            'linhas_invalidas': linhas_invalidas,
            'total_linhas_recebidas': len(linhas_mapeadas)
        }

    @staticmethod
    def _normalizar_chave_texto(valor):
        return (valor or '').strip().lower()

    @staticmethod
    def _chave_negocio_lancamento(lanc):
        valor = Decimal(str(lanc['valor'])).quantize(Decimal('0.01'))
        return (
            int(lanc['cartao_id']),
            lanc['mes_fatura'].isoformat(),
            lanc['data_compra'].isoformat(),
            str(valor),
            ImportacaoCartaoService._normalizar_chave_texto(lanc.get('descricao_original_normalizada') or lanc.get('descricao')),
            int(lanc['numero_parcela']),
            int(lanc['total_parcelas'])
        )

    @staticmethod
    def _existe_duplicado_banco(lanc):
        descricao_ref = ImportacaoCartaoService._normalizar_chave_texto(
            lanc.get('descricao_original_normalizada') or lanc.get('descricao')
        )

        existente = LancamentoAgregado.query.filter(
            LancamentoAgregado.cartao_id == lanc['cartao_id'],
            PerfilFinanceiroService.condicao_perfil(LancamentoAgregado),
            LancamentoAgregado.mes_fatura == lanc['mes_fatura'],
            LancamentoAgregado.data_compra == lanc['data_compra'],
            LancamentoAgregado.valor == lanc['valor'],
            LancamentoAgregado.numero_parcela == lanc['numero_parcela'],
            LancamentoAgregado.total_parcelas == lanc['total_parcelas'],
            func.lower(
                func.coalesce(
                    LancamentoAgregado.descricao_original_normalizada,
                    LancamentoAgregado.descricao
                )
            ) == descricao_ref
        ).first()

        return existente is not None

    @staticmethod
    def persistir_lancamentos(lancamentos, dry_run=False):
        """
        Persiste lanÃ§amentos com garantia de idempotÃªncia

        IdempotÃªncia MVP:
        - Detecta duplicidade no lote atual (chave de negÃ³cio)
        - Detecta duplicidade no banco (chave de negÃ³cio estÃ¡vel)

        Args:
            lancamentos (list): Lista de dicts de lanÃ§amentos
            dry_run (bool): Se True, nÃ£o persiste. Apenas analisa.

        Returns:
            dict: {'inseridos': int, 'duplicados': int, 'erros': []}
        """
        inseridos = 0
        duplicados = 0
        erros = []
        chaves_lote = set()
        amostra_duplicados = []
        amostra_erros = []

        for lanc in lancamentos:
            try:
                chave_lote = ImportacaoCartaoService._chave_negocio_lancamento(lanc)
                duplicado_lote = chave_lote in chaves_lote
                duplicado_banco = ImportacaoCartaoService._existe_duplicado_banco(lanc)
                existe = duplicado_lote or duplicado_banco

                if existe:
                    duplicados += 1
                    if len(amostra_duplicados) < 20:
                        amostra_duplicados.append({
                            'descricao': lanc.get('descricao_exibida') or lanc.get('descricao'),
                            'data_compra': lanc['data_compra'].isoformat(),
                            'valor': float(lanc['valor']),
                            'numero_parcela': lanc['numero_parcela'],
                            'total_parcelas': lanc['total_parcelas'],
                            'origem': 'lote' if duplicado_lote else 'banco'
                        })
                    continue  # Pular duplicado

                chaves_lote.add(chave_lote)

                if dry_run:
                    inseridos += 1
                    continue

                # Criar novo lanÃ§amento
                novo_lanc = LancamentoAgregado(
                    perfil_financeiro_id=PerfilFinanceiroService.obter_perfil_ativo_id(),
                    descricao=lanc['descricao'],
                    descricao_original=lanc['descricao_original'],
                    descricao_original_normalizada=lanc['descricao_original_normalizada'],
                    descricao_exibida=lanc['descricao_exibida'],
                    valor=lanc['valor'],
                    data_compra=lanc['data_compra'],
                    mes_fatura=lanc['mes_fatura'],
                    numero_parcela=lanc['numero_parcela'],
                    total_parcelas=lanc['total_parcelas'],
                    cartao_id=lanc['cartao_id'],
                    categoria_id=lanc['categoria_id'],
                    item_agregado_id=None,
                    categoria_cartao_id=lanc.get('categoria_cartao_id'),
                    compra_id=lanc['compra_id'],
                    is_importado=lanc['is_importado'],
                    origem_importacao=lanc['origem_importacao'],
                    is_recorrente=lanc.get('is_recorrente', False),
                    item_despesa_id=lanc.get('item_despesa_id')
                )

                db.session.add(novo_lanc)
                inseridos += 1

            except Exception as e:
                erro_item = {
                    'descricao': lanc.get('descricao', 'Desconhecido'),
                    'erro': str(e)
                }
                erros.append(erro_item)
                if len(amostra_erros) < 20:
                    amostra_erros.append(erro_item)

        if dry_run:
            return {
                'inseridos': inseridos,
                'duplicados': duplicados,
                'erros': erros,
                'amostra_duplicados': amostra_duplicados,
                'amostra_erros': amostra_erros
            }

        # Commit atÃ´mico
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise Exception(f"Erro ao persistir: {str(e)}")

        return {
            'inseridos': inseridos,
            'duplicados': duplicados,
            'erros': erros,
            'amostra_duplicados': amostra_duplicados,
            'amostra_erros': amostra_erros
        }
