import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import func

try:
    from backend.models import ItemDespesa, ItemAgregado, LancamentoAgregado
    from backend.services.categoria_cartao_service import CategoriaCartaoService
    from backend.services.importacao_cartao_service import ImportacaoCartaoService
    from backend.services.parsers import (
        importacao_csv_parser,
        importacao_pdf_caixa_parser,
        importacao_xlsx_parser,
    )
except ImportError:
    from models import ItemDespesa, ItemAgregado, LancamentoAgregado
    from services.categoria_cartao_service import CategoriaCartaoService
    from services.importacao_cartao_service import ImportacaoCartaoService
    from services.parsers import (
        importacao_csv_parser,
        importacao_pdf_caixa_parser,
        importacao_xlsx_parser,
    )


class ImportacaoCartaoUnificadoService:
    FORMATOS_VALIDOS = {'automatico', 'auto', 'csv', 'xlsx', 'pdf'}

    @staticmethod
    def analisar_arquivo_cartao(file_storage, cartao_id, competencia, formato='automatico'):
        if not file_storage or not getattr(file_storage, 'filename', ''):
            raise ValueError('Nenhum arquivo enviado.')

        cartao = ImportacaoCartaoUnificadoService._validar_cartao(cartao_id)
        competencia_base = ImportacaoCartaoUnificadoService._parse_competencia(competencia)
        formato_detectado = ImportacaoCartaoUnificadoService.detectar_tipo_arquivo(file_storage, formato)

        parser = {
            'csv': importacao_csv_parser.parse,
            'xlsx': importacao_xlsx_parser.parse,
            'pdf': importacao_pdf_caixa_parser.parse,
        }.get(formato_detectado)
        if not parser:
            raise ValueError('Formato de arquivo nao suportado para importacao de cartao.')

        resultado_parser = parser(file_storage, competencia=competencia_base)
        if resultado_parser.get('requer_mapeamento'):
            return ImportacaoCartaoUnificadoService._payload_mapeamento_manual(
                resultado_parser,
                cartao_id=cartao.id,
                competencia_base=competencia_base,
            )

        linhas = ImportacaoCartaoUnificadoService.normalizar_linhas(
            resultado_parser.get('linhas') or [],
            origem=formato_detectado,
            cartao_id=cartao.id,
        )
        linhas = ImportacaoCartaoUnificadoService.aplicar_sugestoes_categoria(linhas, cartao)
        linhas = ImportacaoCartaoUnificadoService.validar_linhas(linhas, cartao, competencia_base)
        validacoes = ImportacaoCartaoUnificadoService.calcular_validacoes(
            linhas,
            resultado_parser.get('fatura') or {},
        )

        return {
            'origem': formato_detectado,
            'arquivo_nome': getattr(file_storage, 'filename', None),
            'cartao_id': cartao.id,
            'competencia': competencia_base.strftime('%Y-%m'),
            'fatura': resultado_parser.get('fatura') or {},
            'linhas': linhas,
            'validacoes': validacoes,
            'requer_mapeamento': False,
            'perfil_detectado': resultado_parser.get('perfil_detectado'),
        }

    @staticmethod
    def _payload_mapeamento_manual(resultado_parser, cartao_id, competencia_base):
        return {
            'origem': resultado_parser.get('origem') or 'csv',
            'arquivo_nome': resultado_parser.get('arquivo_nome'),
            'cartao_id': cartao_id,
            'competencia': competencia_base.strftime('%Y-%m'),
            'fatura': resultado_parser.get('fatura') or {},
            'linhas': [],
            'validacoes': {
                'total_linhas': resultado_parser.get('total_linhas') or 0,
                'validas': 0,
                'revisar': 0,
                'duplicadas': 0,
                'sem_categoria_cartao': 0,
                'total_importavel': 0,
                'total_fatura': 0,
                'creditos': 0,
                'ignorados': 0,
                'diferenca': 0,
                'revisar_totais': False,
            },
            'requer_mapeamento': True,
            'perfil_detectado': resultado_parser.get('perfil_detectado'),
            'autodeteccao_confianca': resultado_parser.get('autodeteccao_confianca'),
            'mapeamento_sugerido': resultado_parser.get('mapeamento_sugerido') or {},
            'colunas': resultado_parser.get('colunas') or [],
            'linhas_dados': resultado_parser.get('linhas_dados') or [],
            'linhas_amostra': resultado_parser.get('linhas_amostra') or [],
            'total_linhas': resultado_parser.get('total_linhas') or 0,
            'delimitador': resultado_parser.get('delimitador'),
        }

    @staticmethod
    def _validar_cartao(cartao_id):
        try:
            cartao_id_int = int(cartao_id)
        except (TypeError, ValueError):
            raise ValueError('cartao_id invalido.')

        cartao = ItemDespesa.query.get(cartao_id_int)
        if not cartao or cartao.tipo != 'Agregador':
            raise ValueError('Cartao invalido.')
        return cartao

    @staticmethod
    def _parse_competencia(competencia):
        if isinstance(competencia, date):
            return competencia.replace(day=1)
        texto = str(competencia or '').strip()
        for formato in ('%Y-%m-%d', '%Y-%m', '%m/%Y'):
            try:
                return datetime.strptime(texto, formato).date().replace(day=1)
            except ValueError:
                continue
        raise ValueError('competencia deve estar no formato YYYY-MM ou YYYY-MM-DD.')

    @staticmethod
    def detectar_tipo_arquivo(file_storage, formato='automatico'):
        formato_normalizado = (formato or 'automatico').strip().lower()
        if formato_normalizado not in ImportacaoCartaoUnificadoService.FORMATOS_VALIDOS:
            raise ValueError('Formato solicitado invalido.')
        if formato_normalizado == 'auto':
            formato_normalizado = 'automatico'

        nome = (getattr(file_storage, 'filename', '') or '').lower()
        extensao = Path(nome).suffix.lstrip('.')
        assinatura = ImportacaoCartaoUnificadoService._ler_assinatura(file_storage)

        if assinatura.startswith(b'%PDF'):
            real = 'pdf'
        elif assinatura.startswith(b'PK') or extensao in {'xlsx', 'xlsm'}:
            real = 'xlsx'
        elif extensao == 'pdf':
            real = 'pdf'
        elif extensao in {'csv', 'txt'}:
            real = 'csv'
        else:
            real = 'csv'

        if formato_normalizado != 'automatico':
            esperado = 'xlsx' if formato_normalizado == 'xlsx' else formato_normalizado
            if esperado != real:
                raise ValueError(f'O arquivo enviado parece ser {real.upper()}, mas o formato selecionado foi {esperado.upper()}.')
        return real

    @staticmethod
    def _ler_assinatura(file_storage):
        origem = getattr(file_storage, 'stream', file_storage)
        posicao = None
        if hasattr(origem, 'tell'):
            try:
                posicao = origem.tell()
            except OSError:
                posicao = None
        try:
            if hasattr(origem, 'seek'):
                origem.seek(0)
            assinatura = origem.read(8)
            if isinstance(assinatura, str):
                assinatura = assinatura.encode('utf-8', errors='ignore')
            return assinatura or b''
        finally:
            if hasattr(origem, 'seek'):
                origem.seek(posicao or 0)

    @staticmethod
    def normalizar_linhas(linhas, origem, cartao_id):
        normalizadas = []
        for idx, linha in enumerate(linhas, start=1):
            descricao_original = linha.get('descricao_original') or linha.get('descricao') or ''
            descricao_normalizada = linha.get('descricao_normalizada') or descricao_original
            parcela_atual = linha.get('parcela_atual') or linha.get('numero_parcela') or 1
            total_parcelas = linha.get('total_parcelas') or 1
            item_agregado_id = linha.get('item_agregado_id')
            categoria_cartao_id = linha.get('categoria_cartao_id')
            categoria_id = linha.get('categoria_id') or linha.get('categoria_despesa_id')

            normalizadas.append({
                'linha_id': linha.get('linha_id') or f'{origem}-{uuid.uuid4()}',
                'linha_origem': linha.get('linha_origem') or idx,
                'status': linha.get('status') or 'revisar',
                'data_compra': linha.get('data_compra'),
                'descricao_original': descricao_original,
                'descricao_normalizada': descricao_normalizada,
                'descricao': descricao_normalizada,
                'descricao_exibida': linha.get('descricao_exibida') or descricao_normalizada,
                'cartao_final': linha.get('cartao_final'),
                'grupo': linha.get('grupo'),
                'parcela_atual': int(parcela_atual or 1),
                'numero_parcela': int(parcela_atual or 1),
                'total_parcelas': int(total_parcelas or 1),
                'parcela': linha.get('parcela') or f'{int(parcela_atual or 1)}/{int(total_parcelas or 1)}',
                'valor': ImportacaoCartaoUnificadoService._float_valor(linha.get('valor')),
                'tipo_movimento': linha.get('tipo_movimento') or 'debito',
                'categoria_detectada': linha.get('categoria_detectada'),
                'categoria_despesa_id': categoria_id,
                'categoria_id': categoria_id,
                'categoria_cartao_id': categoria_cartao_id,
                'item_agregado_id': item_agregado_id,
                'categoria_cartao_origem': linha.get('categoria_cartao_origem'),
                'confianca_categoria': linha.get('confianca_categoria') or 'baixa',
                'categoria_sugerida_origem': linha.get('categoria_sugerida_origem'),
                'duplicidade': linha.get('duplicidade'),
                'mensagens': list(linha.get('mensagens') or []),
                'metadados': linha.get('metadados') or {},
                'cartao_id': cartao_id,
                'origem_importacao': linha.get('origem_importacao') or origem,
                'ignorar': bool(linha.get('ignorar')),
                'gerar_parcelas_futuras': bool(linha.get('gerar_parcelas_futuras')),
            })
        return normalizadas

    @staticmethod
    def _float_valor(valor):
        if valor is None or valor == '':
            return None
        try:
            return float(valor)
        except (TypeError, ValueError):
            try:
                return float(ImportacaoCartaoService._parse_valor(valor))
            except Exception:
                return None

    @staticmethod
    def aplicar_sugestoes_categoria(linhas, cartao):
        for linha in linhas:
            if linha.get('tipo_movimento') == 'credito':
                continue

            categoria_id, origem = ImportacaoCartaoService.sugerir_categoria_por_descricao(
                linha.get('descricao_normalizada') or linha.get('descricao_original'),
                categoria_fallback_id=cartao.categoria_id,
            )
            if categoria_id:
                linha['categoria_id'] = categoria_id
                linha['categoria_despesa_id'] = categoria_id
                linha['categoria_detectada'] = linha.get('categoria_detectada') or 'historico'
                linha['categoria_sugerida_origem'] = origem
                linha['confianca_categoria'] = 'alta' if origem == 'historico' else 'media'

            if linha.get('categoria_id') or linha.get('categoria_cartao_id'):
                resolucao_cartao = CategoriaCartaoService.resolver_categoria_cartao_para_lancamento(
                    cartao_id=cartao.id,
                    categoria_id=linha.get('categoria_id'),
                    categoria_cartao_id=linha.get('categoria_cartao_id'),
                )
                categoria_cartao_id = resolucao_cartao.get('categoria_cartao_id')
                if categoria_cartao_id:
                    linha['categoria_cartao_id'] = int(categoria_cartao_id)
                    linha['categoria_cartao_origem'] = resolucao_cartao.get('origem')
                    linha['categoria_cartao_sugerida_id'] = int(categoria_cartao_id)
                    linha['categoria_cartao_sugerida_origem'] = resolucao_cartao.get('origem')
                    if resolucao_cartao.get('vinculada_ao_cartao') is False:
                        linha.setdefault('mensagens', []).append(
                            'Esta Categoria do Cartao ainda nao possui limite definido neste cartao.'
                        )
                elif resolucao_cartao.get('origem') == 'categoria_cartao_nao_vinculada':
                    linha.setdefault('mensagens', []).append(
                        'Esta Categoria do Cartao ainda nao possui limite definido neste cartao.'
                    )
                    linha['categoria_cartao_origem'] = resolucao_cartao.get('origem')
                else:
                    linha.setdefault('mensagens', []).append(
                        'Categoria do Cartao ainda nao configurada para esta Categoria de Despesa.'
                    )
        return linhas

    @staticmethod
    def _sugerir_categoria_cartao(linha, cartao_id, categorias_cartao):
        descricao_ref = ImportacaoCartaoService._normalizar_chave_texto(
            linha.get('descricao_normalizada') or linha.get('descricao_original')
        )
        if descricao_ref:
            registro = LancamentoAgregado.query.filter(
                LancamentoAgregado.cartao_id == cartao_id,
                LancamentoAgregado.item_agregado_id.isnot(None),
                func.lower(
                    func.coalesce(
                        LancamentoAgregado.descricao_original_normalizada,
                        LancamentoAgregado.descricao,
                    )
                ) == descricao_ref,
            ).order_by(LancamentoAgregado.id.desc()).first()
            if registro and registro.item_agregado_id:
                item = next((cat for cat in categorias_cartao if cat.id == registro.item_agregado_id), None)
                if item:
                    return item, 'historico'

        texto = f"{linha.get('descricao_normalizada') or ''} {linha.get('grupo') or ''}".lower()
        for item in categorias_cartao:
            nome = (item.nome or '').strip().lower()
            if nome and nome in texto:
                return item, 'palavra_chave'
        return None, None

    @staticmethod
    def validar_linhas(linhas, cartao, competencia_base):
        chaves_lote = set()
        ids_categorias_cartao = {
            item.id for item in ItemAgregado.query.filter_by(item_despesa_id=cartao.id, ativo=True).all()
        }

        for linha in linhas:
            mensagens = linha.setdefault('mensagens', [])
            linha['status'] = 'valido'

            if linha.get('tipo_movimento') == 'credito':
                linha['status'] = 'ignorado'
                linha['ignorar'] = True
                continue

            if linha.get('valor') in (None, 0):
                linha['status'] = 'ignorado'
                linha['ignorar'] = True
                mensagens.append('Valor ausente ou zero.')
                continue

            if not linha.get('data_compra'):
                linha['status'] = 'revisar'
                mensagens.append('Data de compra ausente.')
            if not (linha.get('descricao_normalizada') or linha.get('descricao_original')):
                linha['status'] = 'revisar'
                mensagens.append('Descricao ausente.')

            item_agregado_id = linha.get('item_agregado_id')
            if item_agregado_id:
                try:
                    item_agregado_id = int(item_agregado_id)
                except (TypeError, ValueError):
                    item_agregado_id = None
                if item_agregado_id not in ids_categorias_cartao:
                    linha['item_agregado_id'] = None
                    mensagens.append('Categoria do cartao nao pertence ao cartao selecionado.')

            if linha.get('categoria_cartao_id'):
                try:
                    linha['categoria_cartao_id'] = int(linha.get('categoria_cartao_id'))
                except (TypeError, ValueError):
                    linha['categoria_cartao_id'] = None
                    mensagens.append('Categoria do cartao global invalida.')

            if not linha.get('categoria_cartao_id') and not linha.get('item_agregado_id'):
                mensagens.append('Categoria do Cartao ainda nao configurada para esta Categoria de Despesa.')

            if not linha.get('categoria_id') and linha['status'] == 'valido':
                linha['status'] = 'revisar'
                mensagens.append('Informe a categoria da despesa.')

            chave = ImportacaoCartaoUnificadoService._chave_linha(linha, cartao.id, competencia_base)
            if chave:
                duplicado_lote = chave in chaves_lote
                duplicado_banco = ImportacaoCartaoUnificadoService._existe_duplicado_banco(linha, cartao.id, competencia_base)
                if duplicado_lote or duplicado_banco:
                    linha['status'] = 'duplicado'
                    linha['ignorar'] = True
                    linha['duplicidade'] = 'lote' if duplicado_lote else 'banco'
                    mensagens.append('Possivel duplicidade detectada.')
                else:
                    chaves_lote.add(chave)

        return linhas

    @staticmethod
    def _parse_data(data_str):
        if isinstance(data_str, date):
            return data_str
        for formato in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.strptime(str(data_str), formato).date()
            except (ValueError, TypeError):
                continue
        return None

    @staticmethod
    def _decimal_valor(valor):
        try:
            return Decimal(str(valor)).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _chave_linha(linha, cartao_id, competencia_base):
        data_compra = ImportacaoCartaoUnificadoService._parse_data(linha.get('data_compra'))
        valor = ImportacaoCartaoUnificadoService._decimal_valor(linha.get('valor'))
        descricao = ImportacaoCartaoService._normalizar_chave_texto(
            linha.get('descricao_normalizada') or linha.get('descricao_original')
        )
        if not all([data_compra, valor is not None, descricao]):
            return None
        return (
            int(cartao_id),
            competencia_base.isoformat(),
            data_compra.isoformat(),
            str(valor),
            descricao,
            int(linha.get('parcela_atual') or linha.get('numero_parcela') or 1),
            int(linha.get('total_parcelas') or 1),
        )

    @staticmethod
    def _existe_duplicado_banco(linha, cartao_id, competencia_base):
        data_compra = ImportacaoCartaoUnificadoService._parse_data(linha.get('data_compra'))
        valor = ImportacaoCartaoUnificadoService._decimal_valor(linha.get('valor'))
        descricao = ImportacaoCartaoService._normalizar_chave_texto(
            linha.get('descricao_normalizada') or linha.get('descricao_original')
        )
        if not all([data_compra, valor is not None, descricao]):
            return False

        existente = LancamentoAgregado.query.filter(
            LancamentoAgregado.cartao_id == cartao_id,
            LancamentoAgregado.mes_fatura == competencia_base,
            LancamentoAgregado.data_compra == data_compra,
            LancamentoAgregado.valor == valor,
            LancamentoAgregado.numero_parcela == int(linha.get('parcela_atual') or linha.get('numero_parcela') or 1),
            LancamentoAgregado.total_parcelas == int(linha.get('total_parcelas') or 1),
            func.lower(
                func.coalesce(
                    LancamentoAgregado.descricao_original_normalizada,
                    LancamentoAgregado.descricao,
                )
            ) == descricao,
        ).first()
        return existente is not None

    @staticmethod
    def calcular_validacoes(linhas, fatura):
        total_fatura = fatura.get('valor_total') or 0
        total_importavel = sum(
            float(linha.get('valor') or 0)
            for linha in linhas
            if linha.get('tipo_movimento') == 'debito' and linha.get('status') not in {'duplicado', 'ignorado'}
        )
        diferenca = round(float(total_fatura or 0) - total_importavel, 2)
        return {
            'total_linhas': len(linhas),
            'validas': sum(1 for linha in linhas if linha.get('status') == 'valido'),
            'revisar': sum(1 for linha in linhas if linha.get('status') == 'revisar'),
            'duplicadas': sum(1 for linha in linhas if linha.get('status') == 'duplicado'),
            'sem_categoria_cartao': sum(
                1 for linha in linhas
                if linha.get('tipo_movimento') == 'debito'
                and linha.get('status') not in {'duplicado', 'ignorado'}
                and not linha.get('categoria_cartao_id')
                and not linha.get('item_agregado_id')
            ),
            'total_importavel': round(total_importavel, 2),
            'total_fatura': float(total_fatura or 0),
            'creditos': sum(1 for linha in linhas if linha.get('tipo_movimento') == 'credito'),
            'ignorados': sum(1 for linha in linhas if linha.get('status') == 'ignorado'),
            'diferenca': diferenca,
            'revisar_totais': abs(diferenca) > 0.01,
        }
