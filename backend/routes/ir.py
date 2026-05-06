from io import BytesIO

from flask import Blueprint, jsonify, request, send_file

try:
    from backend.models import db
    from backend.services.documento_empresarial_service import DocumentoEmpresarialService
    from backend.services.documento_financeiro_sugestao_service import DocumentoFinanceiroSugestaoService
    from backend.services.documento_fiscal_service import DocumentoFiscalService
    from backend.services.ir_documento_service import IrDocumentoService
    from backend.services.ir_relatorio_service import IrRelatorioService
    from backend.services.lastro_financeiro_service import LastroFinanceiroService
    from backend.services.lastro_relatorio_service import LastroRelatorioService
except ImportError:
    from models import db
    from services.documento_empresarial_service import DocumentoEmpresarialService
    from services.documento_financeiro_sugestao_service import DocumentoFinanceiroSugestaoService
    from services.documento_fiscal_service import DocumentoFiscalService
    from services.ir_documento_service import IrDocumentoService
    from services.ir_relatorio_service import IrRelatorioService
    from services.lastro_financeiro_service import LastroFinanceiroService
    from services.lastro_relatorio_service import LastroRelatorioService


ir_bp = Blueprint('ir', __name__)


def _json_error(message, status_code=400):
    return jsonify({'success': False, 'error': message}), status_code


def _json_success(data=None, status_code=200, **extra):
    payload = {'success': True}
    if data is not None:
        payload['data'] = data
    payload.update(extra)
    return jsonify(payload), status_code


@ir_bp.route('/categorias', methods=['GET'])
def listar_categorias_ir():
    categorias = IrDocumentoService.listar_categorias_ir()
    db.session.commit()
    return _json_success([categoria.to_dict() for categoria in categorias], total=len(categorias))


@ir_bp.route('/contexto', methods=['GET'])
def obter_contexto_ir():
    contexto = IrDocumentoService.obter_contexto()
    db.session.commit()
    return _json_success(contexto)


@ir_bp.route('/categorias', methods=['POST'])
def criar_categoria_ir():
    try:
        categoria = IrDocumentoService.criar_categoria_ir(request.get_json(silent=True) or {})
        db.session.commit()
        return _json_success(categoria.to_dict(), 201)
    except ValueError as exc:
        db.session.rollback()
        return _json_error(str(exc), 400)


@ir_bp.route('/categorias-despesa', methods=['GET'])
def listar_vinculos_ir():
    vinculos = IrDocumentoService.listar_vinculos()
    return _json_success([vinculo.to_dict() for vinculo in vinculos], total=len(vinculos))


@ir_bp.route('/categorias-despesa-disponiveis', methods=['GET'])
def listar_categorias_despesa_disponiveis():
    categorias = IrDocumentoService.listar_categorias_despesa_disponiveis()
    return _json_success(categorias, total=len(categorias))


@ir_bp.route('/categorias-despesa', methods=['POST'])
def criar_vinculo_ir():
    try:
        vinculo = IrDocumentoService.criar_vinculo(request.get_json(silent=True) or {})
        db.session.commit()
        return _json_success(vinculo.to_dict(), 201)
    except ValueError as exc:
        db.session.rollback()
        return _json_error(str(exc), 400)


@ir_bp.route('/categorias-despesa/<int:vinculo_id>', methods=['DELETE'])
def inativar_vinculo_ir(vinculo_id):
    try:
        vinculo = IrDocumentoService.inativar_vinculo(vinculo_id)
        db.session.commit()
        return _json_success(vinculo.to_dict())
    except ValueError as exc:
        db.session.rollback()
        return _json_error(str(exc), 404)


@ir_bp.route('/comprovantes', methods=['GET'])
def listar_comprovantes():
    comprovantes = IrDocumentoService.listar_comprovantes(request.args)
    contexto = IrDocumentoService.obter_contexto()
    modo_empresa = contexto.get('modo') == 'DOCUMENTOS_FISCAIS_EMPRESA'
    dados = []
    for comprovante in comprovantes:
        item = comprovante.to_dict()
        if modo_empresa:
            item = DocumentoEmpresarialService.enriquecer_comprovante_dict(comprovante, item)
        dados.append(item)
    return _json_success(
        dados,
        total=len(comprovantes),
        resumo=IrDocumentoService.resumo(comprovantes, request.args),
    )


@ir_bp.route('/comprovantes/<int:comprovante_id>', methods=['GET'])
def obter_comprovante(comprovante_id):
    try:
        comprovante = IrDocumentoService.obter_comprovante(comprovante_id)
        data = comprovante.to_dict(include_texto=True, include_eventos=True)
        contexto = IrDocumentoService.obter_contexto()
        if contexto.get('modo') == 'DOCUMENTOS_FISCAIS_EMPRESA':
            data = DocumentoEmpresarialService.enriquecer_comprovante_dict(comprovante, data)
        return _json_success(data)
    except ValueError as exc:
        return _json_error(str(exc), 404)


@ir_bp.route('/documentos-empresa/taxonomia', methods=['GET'])
def taxonomia_documentos_empresa():
    try:
        DocumentoEmpresarialService.garantir_perfil_empresa()
        return _json_success(DocumentoEmpresarialService.obter_taxonomia())
    except PermissionError as exc:
        return _json_error(str(exc), 403)


@ir_bp.route('/documentos-empresa/resumo', methods=['GET'])
def resumo_documentos_empresa():
    try:
        return _json_success(DocumentoEmpresarialService.resumo_documentos_empresa(request.args))
    except PermissionError as exc:
        return _json_error(str(exc), 403)


@ir_bp.route('/comprovantes/<int:comprovante_id>/metadata-empresarial', methods=['GET'])
def obter_metadata_empresarial(comprovante_id):
    try:
        return _json_success(DocumentoEmpresarialService.obter_metadata(comprovante_id))
    except PermissionError as exc:
        return _json_error(str(exc), 403)
    except ValueError as exc:
        return _json_error(str(exc), 404)


@ir_bp.route('/comprovantes/<int:comprovante_id>/metadata-empresarial', methods=['PUT'])
def atualizar_metadata_empresarial(comprovante_id):
    try:
        metadata = DocumentoEmpresarialService.atualizar_metadata(
            comprovante_id,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
        return _json_success(metadata)
    except PermissionError as exc:
        db.session.rollback()
        return _json_error(str(exc), 403)
    except ValueError as exc:
        db.session.rollback()
        return _json_error(str(exc), 400)


@ir_bp.route('/comprovantes/upload', methods=['POST'])
def upload_comprovantes():
    arquivos = request.files.getlist('arquivos') or request.files.getlist('files')
    arquivo_unico = request.files.get('arquivo')
    if arquivo_unico and not arquivos:
        arquivos = [arquivo_unico]
    if not arquivos:
        return _json_error('Nenhum arquivo enviado', 400)

    resultados = IrDocumentoService.processar_uploads(
        arquivos,
        request.form.get('ano_calendario') or request.form.get('ano') or request.args.get('ano'),
    )
    status_code = 207 if any(not item.get('success') for item in resultados) else 200
    return _json_success(resultados, status_code, total=len(resultados))


@ir_bp.route('/comprovantes/<int:comprovante_id>', methods=['PUT'])
def atualizar_comprovante(comprovante_id):
    try:
        comprovante = IrDocumentoService.atualizar_comprovante(comprovante_id, request.get_json(silent=True) or {})
        db.session.commit()
        return _json_success(comprovante.to_dict(include_texto=True, include_eventos=True))
    except ValueError as exc:
        db.session.rollback()
        return _json_error(str(exc), 400)


@ir_bp.route('/comprovantes/<int:comprovante_id>/validar', methods=['POST'])
def validar_comprovante(comprovante_id):
    try:
        comprovante = IrDocumentoService.validar_comprovante(comprovante_id)
        db.session.commit()
        return _json_success(comprovante.to_dict(include_texto=True, include_eventos=True))
    except ValueError as exc:
        db.session.rollback()
        return _json_error(str(exc), 404)


@ir_bp.route('/comprovantes/<int:comprovante_id>/reprocessar-ocr', methods=['POST'])
def reprocessar_ocr_comprovante(comprovante_id):
    try:
        comprovante = IrDocumentoService.reprocessar_ocr(comprovante_id)
        db.session.commit()
        return _json_success(comprovante.to_dict(include_texto=True, include_eventos=True))
    except ValueError as exc:
        db.session.rollback()
        status = 404 if 'nao encontrado' in str(exc).lower() else 400
        return _json_error(str(exc), status)


@ir_bp.route('/comprovantes/<int:comprovante_id>/sugestao-financeira', methods=['GET'])
def gerar_sugestao_financeira(comprovante_id):
    try:
        sugestao = DocumentoFinanceiroSugestaoService.gerar_sugestao(comprovante_id)
        return _json_success(sugestao)
    except ValueError as exc:
        status = 404 if 'nao encontrado' in str(exc).lower() else 400
        return _json_error(str(exc), status)


@ir_bp.route('/comprovantes/<int:comprovante_id>/criar-financeiro', methods=['POST'])
def criar_financeiro_comprovante(comprovante_id):
    try:
        resultado = DocumentoFinanceiroSugestaoService.criar_financeiro(
            comprovante_id,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
        return _json_success(resultado, 201)
    except ValueError as exc:
        db.session.rollback()
        status = 404 if 'nao encontrado' in str(exc).lower() else 400
        return _json_error(str(exc), status)


@ir_bp.route('/comprovantes/<int:comprovante_id>/arquivo', methods=['GET'])
def obter_arquivo(comprovante_id):
    try:
        arquivo = IrDocumentoService.obter_arquivo(comprovante_id)
        return send_file(
            BytesIO(arquivo.conteudo),
            mimetype=arquivo.mime_type,
            as_attachment=False,
            download_name=arquivo.nome_arquivo,
        )
    except ValueError as exc:
        return _json_error(str(exc), 404)


@ir_bp.route('/comprovantes/<int:comprovante_id>/vinculos', methods=['GET'])
def listar_vinculos_comprovante(comprovante_id):
    try:
        vinculos = DocumentoFiscalService.listar_vinculos(comprovante_id)
        return _json_success([vinculo.to_dict() for vinculo in vinculos], total=len(vinculos))
    except ValueError as exc:
        return _json_error(str(exc), 404)


@ir_bp.route('/comprovantes/<int:comprovante_id>/vinculos', methods=['POST'])
def criar_vinculo_comprovante(comprovante_id):
    try:
        vinculo = DocumentoFiscalService.criar_vinculo(comprovante_id, request.get_json(silent=True) or {})
        db.session.commit()
        return _json_success(vinculo.to_dict(), 201)
    except ValueError as exc:
        db.session.rollback()
        return _json_error(str(exc), 400)


@ir_bp.route('/comprovantes/<int:comprovante_id>/vinculos/<int:vinculo_id>', methods=['PUT'])
def atualizar_vinculo_comprovante(comprovante_id, vinculo_id):
    try:
        vinculo = DocumentoFiscalService.atualizar_vinculo(comprovante_id, vinculo_id, request.get_json(silent=True) or {})
        db.session.commit()
        return _json_success(vinculo.to_dict())
    except ValueError as exc:
        db.session.rollback()
        return _json_error(str(exc), 400)


@ir_bp.route('/comprovantes/<int:comprovante_id>/vinculos/<int:vinculo_id>', methods=['DELETE'])
def remover_vinculo_comprovante(comprovante_id, vinculo_id):
    try:
        vinculo = DocumentoFiscalService.remover_vinculo(comprovante_id, vinculo_id)
        db.session.commit()
        return _json_success(vinculo.to_dict())
    except ValueError as exc:
        db.session.rollback()
        return _json_error(str(exc), 404)


@ir_bp.route('/entidades-vinculaveis', methods=['GET'])
def listar_entidades_vinculaveis():
    entidades = DocumentoFiscalService.listar_entidades_vinculaveis(
        request.args.get('tipo'),
        request.args.get('busca'),
    )
    return _json_success(entidades, total=len(entidades))


@ir_bp.route('/lastro/resumo', methods=['GET'])
def resumo_lastro():
    resumo = DocumentoFiscalService.resumo_lastro(request.args.get('ano'))
    return _json_success(resumo)


@ir_bp.route('/lastro/saidas-sem-documento/resumo', methods=['GET'])
def resumo_saidas_sem_documento():
    try:
        resumo = LastroFinanceiroService.resumo_saidas_sem_documento(request.args)
        return _json_success(resumo)
    except PermissionError as exc:
        return _json_error(str(exc), 403)


@ir_bp.route('/lastro/saidas-sem-documento', methods=['GET'])
def listar_saidas_sem_documento():
    try:
        saidas = LastroFinanceiroService.listar_saidas_sem_documento(request.args)
        return _json_success(saidas, total=len(saidas))
    except PermissionError as exc:
        return _json_error(str(exc), 403)


@ir_bp.route('/lastro/saidas-sem-documento/vincular', methods=['POST'])
def vincular_saida_sem_documento():
    try:
        vinculo = LastroFinanceiroService.vincular_documento(request.get_json(silent=True) or {})
        db.session.commit()
        return _json_success(vinculo.to_dict(), 201)
    except PermissionError as exc:
        db.session.rollback()
        return _json_error(str(exc), 403)
    except ValueError as exc:
        db.session.rollback()
        return _json_error(str(exc), 400)


@ir_bp.route('/lastro/saidas-sem-documento/status', methods=['POST'])
def marcar_status_saida_sem_documento():
    try:
        pendencia = LastroFinanceiroService.marcar_status(request.get_json(silent=True) or {})
        db.session.commit()
        return _json_success(pendencia)
    except PermissionError as exc:
        db.session.rollback()
        return _json_error(str(exc), 403)
    except ValueError as exc:
        db.session.rollback()
        return _json_error(str(exc), 400)


@ir_bp.route('/lastro/saidas-sem-documento/relatorio-excel', methods=['GET'])
def relatorio_saidas_sem_documento_excel():
    try:
        arquivo, nome = LastroRelatorioService.gerar_excel(request.args)
        return send_file(
            arquivo,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=nome,
        )
    except PermissionError as exc:
        return _json_error(str(exc), 403)
    except ValueError as exc:
        return _json_error(str(exc), 400)


@ir_bp.route('/lastro/saidas-sem-documento/relatorio-pdf', methods=['GET'])
def relatorio_saidas_sem_documento_pdf():
    try:
        arquivo, nome = LastroRelatorioService.gerar_pdf(request.args)
        return send_file(
            arquivo,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=nome,
        )
    except PermissionError as exc:
        return _json_error(str(exc), 403)
    except ValueError as exc:
        return _json_error(str(exc), 400)


@ir_bp.route('/relatorios/excel', methods=['GET'])
def relatorio_excel():
    try:
        arquivo, nome = IrRelatorioService.gerar_excel(request.args)
        return send_file(
            arquivo,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=nome,
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)


@ir_bp.route('/relatorios/pdf', methods=['GET'])
def relatorio_pdf():
    try:
        arquivo, nome = IrRelatorioService.gerar_pdf(request.args)
        return send_file(
            arquivo,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=nome,
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)


@ir_bp.route('/relatorios/resumo', methods=['GET'])
def relatorio_resumo():
    try:
        return _json_success(IrRelatorioService.resumo(request.args))
    except ValueError as exc:
        return _json_error(str(exc), 400)
