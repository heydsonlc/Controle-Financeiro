"""
Serviço de Importação Assistida de Fatura de Cartão (CSV)

FASE 6.2 - Importação de CSV de fatura de cartão

Este serviço:
- Processa arquivo CSV de fatura
- Normaliza descrições
- Extrai parcelamento explícito
- Reconhece despesas fixas existentes
- Gera parcelas passadas, atual e futuras baseado na COMPETÊNCIA escolhida
- Garante idempotência total

REGRAS INVIOLÁVEIS:
✅ Apenas cria LancamentoAgregado
✅ Não cria Conta (fatura consolidada)
✅ Não infere categorias automaticamente
✅ Não calcula mes_fatura baseado em data - usa competência do usuário
✅ Sistema 100% baseado em COMPETÊNCIA (não em datas de fechamento)
"""

import re
import csv
import io
import uuid
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
    Serviço especializado em importar CSV de faturas de cartão
    """

    # ========================================================================
    # NORMALIZAÇÃO E EXTRAÇÃO
    # ========================================================================

    @staticmethod
    def normalizar_descricao(descricao_bruta):
        """
        Normaliza descrição e extrai informações de parcelamento

        Formatos reconhecidos:
        - NN/TT
        - N/T
        - NN DE TT
        - N DE T

        Args:
            descricao_bruta (str): Texto original do CSV

        Returns:
            tuple: (descricao_normalizada, numero_parcela, total_parcelas)
                Se não houver parcelamento: (descricao, 1, 1)
        """
        descricao = descricao_bruta.strip()

        # Padrões de parcelamento (em ordem de especificidade)
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

                # Remover trecho de parcelamento da descrição
                descricao_normalizada = descricao[:match.start()].strip()

                return descricao_normalizada, numero_parcela, total_parcelas

        # Sem parcelamento explícito
        return descricao, 1, 1

    @staticmethod
    def detectar_delimitador(conteudo_csv):
        """
        Detecta o delimitador do CSV (;, vírgula, tab)

        Args:
            conteudo_csv (str): Conteúdo bruto do CSV

        Returns:
            str: Delimitador detectado
        """
        sniffer = csv.Sniffer()
        amostra = '\n'.join(conteudo_csv.split('\n')[:5])  # Primeiras 5 linhas

        try:
            dialeto = sniffer.sniff(amostra, delimiters=';,\t')
            return dialeto.delimiter
        except:
            # Fallback: ponto-e-vírgula (padrão brasileiro)
            return ';'

    @staticmethod
    def ler_csv(arquivo_csv):
        """
        Lê arquivo CSV e retorna cabeçalho + linhas

        Args:
            arquivo_csv: FileStorage do Flask ou conteúdo string

        Returns:
            tuple: (delimitador, colunas, linhas_amostra)
        """
        # Ler conteúdo
        if hasattr(arquivo_csv, 'read'):
            conteudo = arquivo_csv.read().decode('utf-8', errors='ignore')
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
        linhas_amostra = linhas[1:6]  # Primeiras 5 linhas de dados

        return delimitador, colunas, linhas_amostra

    # ========================================================================
    # RECONHECIMENTO DE DESPESAS FIXAS
    # ========================================================================

    @staticmethod
    def reconhecer_despesa_fixa(descricao_normalizada, cartao_id):
        """
        Verifica se a descrição corresponde a uma despesa fixa já cadastrada

        Args:
            descricao_normalizada (str): Descrição sem parcelamento
            cartao_id (int): ID do cartão

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
    # GERAÇÃO DE PARCELAS
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
        compra_id=None
    ):
        """
        Gera todas as parcelas (passadas, atual, futuras) de uma compra

        Args:
            descricao_normalizada (str): Descrição sem parcelamento
            descricao_exibida (str): Descrição editável
            descricao_original (str): Texto bruto do CSV
            valor_total (Decimal): Valor da parcela
            data_compra (date): Data original da compra
            numero_parcela_atual (int): Número da parcela lida do CSV
            total_parcelas (int): Total de parcelas
            cartao_id (int): ID do cartão
            categoria_id (int): Categoria da despesa
            item_agregado_id (int): Categoria do cartão (opcional)
            competencia_base (date): Competência escolhida pelo usuário (YYYY-MM-01)
            compra_id (str): UUID da compra (se None, gera novo)

        Returns:
            list: Lista de dicts representando parcelas
        """
        if not compra_id:
            compra_id = str(uuid.uuid4())

        parcelas = []

        for numero in range(1, total_parcelas + 1):
            # Calcular meses de diferença em relação à parcela atual
            meses_diff = numero - numero_parcela_atual

            # Data de compra desta parcela
            data_parcela = data_compra + relativedelta(months=meses_diff)

            # Mês de fatura: usar competência base + diferença de meses
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
                'origem_importacao': 'csv'
            }

            parcelas.append(parcela)

        return parcelas

    # ========================================================================
    # PROCESSAMENTO E PERSISTÊNCIA
    # ========================================================================

    @staticmethod
    def processar_linhas_mapeadas(linhas_mapeadas, cartao_id, competencia_alvo):
        """
        Processa linhas já mapeadas e gera lançamentos

        Args:
            linhas_mapeadas (list): Lista de dicts com campos mapeados
            cartao_id (int): ID do cartão
            competencia_alvo (date): Mês de competência (YYYY-MM-01)

        Returns:
            list: Lista de lançamentos prontos para persistência
        """
        lancamentos = []

        for linha in linhas_mapeadas:
            # Extrair campos
            data_compra_str = linha.get('data_compra')
            descricao_bruta = linha.get('descricao')
            valor_str = linha.get('valor')
            parcela_str = linha.get('parcela', '1/1')  # Opcional
            categoria_id = linha.get('categoria_id')
            item_agregado_id = linha.get('item_agregado_id')  # Opcional

            # Validar obrigatórios
            if not all([data_compra_str, descricao_bruta, valor_str, categoria_id]):
                continue  # Pular linha inválida

            # Parsear data (tentar múltiplos formatos)
            data_compra = None
            formatos_data = ['%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']

            for formato in formatos_data:
                try:
                    data_compra = datetime.strptime(data_compra_str, formato).date()
                    break
                except (ValueError, TypeError):
                    continue

            if not data_compra:
                continue  # Data inválida - pular linha

            # Parsear valor
            try:
                valor = Decimal(valor_str.replace(',', '.'))
            except (InvalidOperation, ValueError):
                continue  # Valor inválido

            # Normalizar descrição e extrair parcelamento
            descricao_normalizada, numero_parcela, total_parcelas = ImportacaoCartaoService.normalizar_descricao(descricao_bruta)

            # Se parcela foi mapeada explicitamente no CSV, usar
            if parcela_str and parcela_str != '1/1':
                match = re.match(r'(\d+)/(\d+)', parcela_str)
                if match:
                    numero_parcela = int(match.group(1))
                    total_parcelas = int(match.group(2))

            # Reconhecer despesa fixa
            despesa_fixa = ImportacaoCartaoService.reconhecer_despesa_fixa(descricao_normalizada, cartao_id)
            is_recorrente = despesa_fixa is not None
            item_despesa_id = despesa_fixa.id if despesa_fixa else None

            # Gerar todas as parcelas (passadas, atual, futuras)
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
                competencia_base=competencia_alvo,  # Usar competência escolhida pelo usuário
                compra_id=None  # Será gerado automaticamente
            )

            # Adicionar flag de recorrência
            for parcela in parcelas:
                parcela['is_recorrente'] = is_recorrente
                parcela['item_despesa_id'] = item_despesa_id

            lancamentos.extend(parcelas)

        return lancamentos

    @staticmethod
    def persistir_lancamentos(lancamentos):
        """
        Persiste lançamentos com garantia de idempotência

        Idempotência: (compra_id + numero_parcela) é único

        Args:
            lancamentos (list): Lista de dicts de lançamentos

        Returns:
            dict: {'inseridos': int, 'duplicados': int, 'erros': []}
        """
        inseridos = 0
        duplicados = 0
        erros = []

        for lanc in lancamentos:
            try:
                # Verificar se já existe (idempotência)
                existe = LancamentoAgregado.query.filter_by(
                    compra_id=lanc['compra_id'],
                    numero_parcela=lanc['numero_parcela']
                ).first()

                if existe:
                    duplicados += 1
                    continue  # Pular duplicado

                # Criar novo lançamento
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
                erros.append({
                    'descricao': lanc.get('descricao', 'Desconhecido'),
                    'erro': str(e)
                })

        # Commit atômico
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise Exception(f"Erro ao persistir: {str(e)}")

        return {
            'inseridos': inseridos,
            'duplicados': duplicados,
            'erros': erros
        }
