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
from sqlalchemy import func

try:
    from backend.models import db, ItemDespesa, LancamentoAgregado, ItemAgregado
except ImportError:
    from models import db, ItemDespesa, LancamentoAgregado, ItemAgregado


class ImportacaoCartaoService:
    """
    ServiÃ§o especializado em importar CSV de faturas de cartÃ£o
    """

    PERFIL_NUBANK = 'nubank_csv_simples'
    PERFIL_CAIXA = 'caixa_credito_debito'
    PERFIL_MANUAL = 'manual_generico'

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

        # PadrÃµes de parcelamento (em ordem de especificidade)
        padroes = [
            r'(\d{1,2})/(\d{1,2})$',  # 12/12 ou 1/3
            r'(\d{1,2})\s+DE\s+(\d{1,2})$',  # 12 DE 12 ou 1 DE 3
            r'PARCELA\s+(\d{1,2})/(\d{1,2})$',  # PARCELA 1/12
            r'PARC\s+(\d{1,2})/(\d{1,2})$',  # PARC 1/12
        ]

        for padrao in padroes:
            match = re.search(padrao, descricao, re.IGNORECASE)
            if match:
                numero_parcela = int(match.group(1))
                total_parcelas = int(match.group(2))

                # Remover trecho de parcelamento da descriÃ§Ã£o
                descricao_normalizada = descricao[:match.start()].strip()

                return descricao_normalizada, numero_parcela, total_parcelas

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
        item_agregado_id,
        competencia_base,
        compra_id=None,
        origem_importacao='csv'
    ):
        """
        Gera todas as parcelas (passadas, atual, futuras) de uma compra

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
            item_agregado_id (int): Categoria do cartÃ£o (opcional)
            competencia_base (date): CompetÃªncia escolhida pelo usuÃ¡rio (YYYY-MM-01)
            compra_id (str): UUID da compra (se None, gera novo)

        Returns:
            list: Lista de dicts representando parcelas
        """
        if not compra_id:
            compra_id = str(uuid.uuid4())

        parcelas = []

        for numero in range(1, total_parcelas + 1):
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
                'item_agregado_id': item_agregado_id,
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
    def _parse_parcela_texto(parcela_str):
        if not parcela_str:
            return None
        texto = str(parcela_str).strip()
        match = re.search(r'(\d{1,2})\s*[/\-]\s*(\d{1,2})', texto)
        if match:
            return int(match.group(1)), int(match.group(2))
        match = re.search(r'parcela\s*(\d{1,2})\s*de\s*(\d{1,2})', texto, re.IGNORECASE)
        if match:
            return int(match.group(1)), int(match.group(2))
        return None

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
            LancamentoAgregado.categoria_id.isnot(None)
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
            item_agregado_id = linha.get('item_agregado_id')  # Opcional
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

            # Reconhecer despesa fixa
            despesa_fixa = ImportacaoCartaoService.reconhecer_despesa_fixa(descricao_normalizada, cartao_id)
            is_recorrente = despesa_fixa is not None
            item_despesa_id = despesa_fixa.id if despesa_fixa else None

            # Gerar todas as parcelas (passadas, atual, futuras)
            gerar_futuras = bool(linha.get('gerar_parcelas_futuras'))
            if gerar_futuras and total_parcelas > 1:
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
                    item_agregado_id=item_agregado_id,
                    competencia_base=competencia_alvo,
                    compra_id=None,
                    origem_importacao=origem_importacao
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
                    'item_agregado_id': item_agregado_id,
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
                    item_agregado_id=lanc.get('item_agregado_id'),
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
