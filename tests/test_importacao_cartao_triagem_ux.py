from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / 'frontend' / 'static' / 'js' / 'importar_cartao.js'
TEMPLATE_PATH = ROOT / 'frontend' / 'templates' / 'importar_cartao.html'
CSS_PATH = ROOT / 'frontend' / 'static' / 'css' / 'importar_cartao.css'
SERVICE_PATH = ROOT / 'backend' / 'services' / 'importacao_cartao_service.py'
ROUTE_PATH = ROOT / 'backend' / 'routes' / 'importacao_cartao.py'
CARTOES_JS_PATH = ROOT / 'frontend' / 'static' / 'js' / 'cartoes.js'
CARTOES_TEMPLATE_PATH = ROOT / 'frontend' / 'templates' / 'cartoes.html'
CARTOES_CSS_PATH = ROOT / 'frontend' / 'static' / 'css' / 'cartoes.css'
CARTOES_ROUTE_PATH = ROOT / 'backend' / 'routes' / 'cartoes.py'


def _trecho(texto, inicio, fim):
    start = texto.index(inicio)
    end = texto.index(fim, start)
    return texto[start:end]


def test_tela_unica_operacional_sem_wizard_grande():
    html = TEMPLATE_PATH.read_text(encoding='utf-8')

    assert 'import-topbar-compact' in html
    assert 'Cartão' in html
    assert 'Competência' in html
    assert 'Formato' in html
    assert 'Arquivo selecionado' in html
    assert 'Importar' in html
    assert 'import-step-chip' not in html
    assert '1. Configuração' not in html
    assert '2. Documento' not in html
    assert '3. Validação' not in html
    assert '4. Triagem' not in html
    assert '5. Confronto e Resultado' not in html


def test_layout_tem_tabela_principal_retirados_e_kpis_inferiores():
    html = TEMPLATE_PATH.read_text(encoding='utf-8')

    assert 'Lançamentos em processamento' in html
    assert 'Filtro avançado' in html
    assert 'Confrontar resultado' in html
    assert 'Criar despesas' in html
    assert 'Lançamentos retirados da efetivação' in html
    assert 'KPIs da importação' in html
    assert 'import-bottom-operational' in html
    assert html.index('Lançamentos retirados da efetivação') < html.index('KPIs da importação')
    assert html.index('KPIs da importação') > html.index('Lançamentos em processamento')


def test_tabela_principal_tem_colunas_fixas_paginacao_e_filtros():
    js = JS_PATH.read_text(encoding='utf-8')
    render = _trecho(js, 'function renderizarEditorPrePersistencia', 'function renderizarLinhaOperacional')

    for coluna in [
        'Status',
        'Data',
        'Descrição original',
        'Valor',
        'Tipo detectado',
        'Sugestão',
        'Descrição amigável',
        'Categoria da despesa',
        'Ação',
    ]:
        assert coluna in render

    assert 'Categoria do Cartão' not in render
    assert 'Categoria do cartao' not in render
    assert 'renderizarPaginacaoTabela' in render
    assert "paginarItens(linhasFiltradas, 'principal')" in render
    assert 'linhasPorPagina: 10' in js
    assert "['conhecidas', 'Conhecidas'" in js
    assert "['parcelados', 'Parcelados'" in js
    assert "['novos', 'Novos'" in js
    assert "['usar_sugestao', 'Usar sugestão'" in js


def test_tabela_inferior_tem_colunas_filtros_paginacao_e_acoes():
    js = JS_PATH.read_text(encoding='utf-8')
    retirados = _trecho(js, 'function renderizarTabelaRetirados', 'function renderizarLinhaRetirada')

    for coluna in ['Motivo', 'Data', 'Descrição original', 'Valor', 'Observação', 'Ação']:
        assert coluna in retirados

    assert "paginarItens(retirados, 'retirados')" in retirados
    assert "codigo === 'retirado_usuario'" in js
    assert "iconeBotaoAcao('success', 'undo', 'Restaurar'" in js
    assert "iconeBotaoAcao('neutral', 'eye', 'Ver detalhes'" in js
    assert 'function detalharLinhaRetirada' in js
    assert "['parcelamento', 'Parcelamento tratado'" in js
    assert "['credito', 'Crédito/estorno'" in js


def test_motivos_de_retirada_sao_auditaveis_e_restrigem_restauracao():
    js = JS_PATH.read_text(encoding='utf-8')

    assert 'function motivoRetiradaCodigo' in js
    assert "'duplicado_fatura'" in js
    assert "'ja_existe_fatura'" in js
    assert "'parcelamento_tratado'" in js
    assert 'function observacaoRetiradaLinha' in js
    assert 'function detalheRetiradaLinha' in js
    assert 'linhaDuplicadaPorReconhecimento(linha)' in js
    assert 'linha.ignorar' in _trecho(js, 'function linhaRestauravel', 'function obterInfoOperacional')
    assert '!linhaDuplicadaOperacional(linha)' in _trecho(js, 'function linhaRestauravel', 'function obterInfoOperacional')


def test_kpis_ficam_na_area_inferior_e_nao_na_barra_superior():
    html = TEMPLATE_PATH.read_text(encoding='utf-8')
    js = JS_PATH.read_text(encoding='utf-8')
    css = CSS_PATH.read_text(encoding='utf-8')
    topbar = _trecho(html, '<section class="import-topbar-compact', '<div id="uploadResult"')

    for kpi in [
        'Encontrados',
        'Em processamento',
        'Retirados',
        'Possíveis conhecidas',
        'Parcelamentos',
        'Novos',
        'Valor em processamento',
        'Pendências',
    ]:
        assert kpi in html
        assert kpi not in topbar

    assert 'function calcularKpisImportacao' in js
    assert 'function renderizarKpisImportacao' in js
    assert '.import-bottom-operational' in css
    assert '.import-kpi-panel' in css
    assert 'minmax(760px, 1.75fr) minmax(280px, 0.55fr)' in css
    assert '.import-retired-table th:nth-child(5)' in css


def test_categoria_cartao_permanece_oculta_na_importacao():
    html = TEMPLATE_PATH.read_text(encoding='utf-8')
    js = JS_PATH.read_text(encoding='utf-8')

    assert 'parcelamentoCategoriaCartao' not in html
    assert 'modalCategoriaCartaoPadrao' not in html
    assert 'Categoria do Cartão' not in html
    assert 'opcoesCategoriaCartaoSelect' not in js
    assert 'import-card-category-select' not in js
    assert 'buscarResolucaoCategoriaCartao' in js
    assert 'resolverCategoriaCartaoLinha(index, { manterConfronto: true })' in js
    assert 'CategoriaCartaoService.resolver_categoria_cartao_para_lancamento' in ROUTE_PATH.read_text(encoding='utf-8')


def test_fluxos_existentes_continuam_presentes():
    html = TEMPLATE_PATH.read_text(encoding='utf-8')
    js = JS_PATH.read_text(encoding='utf-8')

    assert 'parcelamentoModal' in html
    assert 'Criar parcelamento a partir do lançamento importado' in html
    assert 'Criar parcelamento' in js
    assert 'Criar despesa' in js
    assert 'Confrontar resultado' in html
    assert 'async function aplicarReconhecimentoFlexivel' in js
    assert 'function usarSugestaoReconhecimento' in js
    assert 'function montarPayloadImportacao' in js


def test_regex_de_parcelamento_e_payload_final_so_usam_novos():
    js = JS_PATH.read_text(encoding='utf-8')
    detector = _trecho(js, 'function detectarParcelamentoTexto', 'function detectarParcelaDescricao')
    payload = _trecho(js, 'function montarPayloadImportacao', 'function validarPendenciasObrigatorias')

    assert r"PARC(?:ELA)?\.?" in detector
    assert r"(\d{1,2})\s*\/\s*(\d{1,2})" in detector
    assert r"(\d{1,2})\s+DE\s+(\d{1,2})" in detector
    assert 'validarNumerosParcelamento(numero, total)' in detector
    assert 'const linhas = linhasNovasConfirmaveis()' in payload
    assert 'gerar_parcelas_futuras: false' in payload


def test_previa_inicial_sinaliza_parcelamento_sem_criar_parcelas():
    js = JS_PATH.read_text(encoding='utf-8')
    operacional = _trecho(js, 'function obterInfoOperacional', 'function linhasProcessamentoBase')

    assert "status: 'A importar'" in operacional
    assert "tipo: parcela ? 'Parcelamento' : '—'" in operacional
    assert "sugestao: parcela ? sugestaoParcelamentoLinha(parcela) : '—'" in operacional
    assert "filtro: 'pendentes'" in operacional
    assert "sugestao: sugestaoParcelamentoLinha(parcela)" in operacional
    assert "gerar_parcelas_futuras: false" in _trecho(js, 'function montarPayloadImportacao', 'function validarPendenciasObrigatorias')


def test_detector_js_aceita_variacoes_e_rejeita_invalidos():
    js = JS_PATH.read_text(encoding='utf-8')
    detector = _trecho(js, 'function validarNumerosParcelamento', 'function detectarParcelaDescricao')
    script = f"""
const MAX_PARCELAS_IMPORTACAO = 60;
{detector}
const validos = [
  'LOJA X 01/10',
  'LOJA X 1/10',
  'BRASIL PARAL*Brpa 07 DE 12 SAO PAULO',
  'ALFA SEGURAD*AUTO 05 DE 05 SAO PAULO',
  'LOJA X 07 de 10',
  'LOJA X 7 de 10',
  'LOJA X 07/12',
  'LOJA X PARCELA 03 DE 05',
  'LOJA X PARC 3 de 5',
  'LOJA X PARC. 3 DE 5',
  'LOJA X 2 de 12'
].map((texto) => detectarParcelamentoTexto(texto)?.rotulo || null);
const invalidos = [
  'LOJA X 10 de 1',
  'LOJA X 0 de 10',
  'LOJA X 1 de 0',
  'LOJA X 0 DE 10',
  'LOJA X 1 DE 0',
  'LOJA X 10 DE 1',
  'LOJA X 13 de 12',
  'LOJA X 99 de 100'
].map((texto) => detectarParcelamentoTexto(texto));
console.log(JSON.stringify({{ validos, invalidos }}));
"""
    resultado = subprocess.run(['node', '-e', script], text=True, capture_output=True, check=True)
    dados = json.loads(resultado.stdout)

    assert dados['validos'] == ['1/10', '1/10', '7/12', '5/5', '7/10', '7/10', '7/12', '3/5', '3/5', '3/5', '2/12']
    assert dados['invalidos'] == [None, None, None, None, None, None, None, None]


def test_sugestao_visual_de_parcelamento_usa_dois_digitos():
    js = JS_PATH.read_text(encoding='utf-8')
    detector = _trecho(js, 'function validarNumerosParcelamento', 'function detectarParcelaDescricao')
    visual = _trecho(js, 'function rotuloParcelamentoVisual', 'function linhaPossivelParcelamento')
    script = f"""
const MAX_PARCELAS_IMPORTACAO = 60;
const toIntOrNull = (valor) => {{
  if (valor === '' || valor === null || valor === undefined) return null;
  const numero = parseInt(valor, 10);
  return Number.isNaN(numero) ? null : numero;
}};
{detector}
{visual}
const descricoes = [
  'BRASIL PARAL*Brpa 07 DE 12 SAO PAULO',
  'ALFA SEGURAD*AUTO 05 DE 05 SAO PAULO',
  'LOJA X PARC. 3 DE 5'
];
const sugestoes = descricoes.map((descricao) => {{
  const detectado = detectarParcelamentoTexto(descricao);
  return sugestaoParcelamentoLinha({{ numero: detectado.parcelaAtual, total: detectado.totalParcelas, rotulo: detectado.rotulo }});
}});
console.log(JSON.stringify(sugestoes));
"""
    resultado = subprocess.run(['node', '-e', script], text=True, capture_output=True, check=True)
    assert json.loads(resultado.stdout) == ['07/12 detectado', '05/05 detectado', '03/05 detectado']


def test_backend_cria_parcelamento_atual_e_futuro_sem_migration():
    service = SERVICE_PATH.read_text(encoding='utf-8')
    route = ROUTE_PATH.read_text(encoding='utf-8')

    assert "MAX_PARCELAS_IMPORTACAO = 60" in service
    assert "numero_inicial = numero_parcela if linha.get('gerar_apenas_atual_e_futuras') else 1" in service
    assert "for numero in range(numero_inicial, total_parcelas + 1)" in service
    assert "@bp.route('/parcelamento', methods=['POST'])" in route
    assert "linha['gerar_parcelas_futuras'] = True" in route
    assert "linha['gerar_apenas_atual_e_futuras'] = True" in route


def test_reconhecimento_flexivel_prioriza_valor_cartao_e_keyword():
    service = SERVICE_PATH.read_text(encoding='utf-8')
    route = ROUTE_PATH.read_text(encoding='utf-8')

    scoring = _trecho(service, 'def _score_candidato_match', 'def _montar_linha_match')
    assert 'score += 50' in scoring
    assert "motivos.append('valor igual/proximo')" in scoring
    assert 'score += 20' in scoring
    assert "motivos.append('mesmo cartao')" in scoring
    assert "motivos.append('palavra-chave forte igual')" in scoring
    assert 'score += 5' in scoring
    assert "motivos.append('categoria igual')" in scoring
    assert "motivos.append('descricao amigavel igual')" in scoring
    assert 'def _fornecedor_compativel' in service
    assert "'confianca': 'alta' if score >= 80 and fornecedor_compativel else 'media'" in service

    assert "('APPLE', None, ('APPLECOMBILL'" in service
    assert "('AMAZON', 'AMAZON MUSIC'" in service
    assert "('AMAZON', 'AMAZON PRIME'" in service
    assert 'AMAZONPRIMEBR' in service
    assert 'DIGITALOCEA' in service
    assert "score < 60" in service
    assert "tipo = 'duplicado_atual'" in service
    assert "@bp.route('/reconhecer', methods=['POST'])" in route


def test_alias_historico_sem_migration_e_com_conflito_para_revisao():
    service = SERVICE_PATH.read_text(encoding='utf-8')
    js = JS_PATH.read_text(encoding='utf-8')

    assert 'LancamentoAgregado.query.filter' in service
    assert 'descricao_original_normalizada' in service
    assert 'descricao_exibida' in service
    assert "'origem_alias': 'historico_lancamento'" in service
    assert "'tipo_sugerido': tratamento_sugerido" in service
    assert "'valor_referencia': float(candidato.get('valor'))" in service
    assert 'historico com decisoes conflitantes' in service
    assert "melhor['confianca'] = 'revisar'" in service
    assert "melhor['score'] = min(melhor['score'], 79)" in service
    assert 'alta confianca exige fornecedor compativel' in service
    assert "status: confiancaReconhecimento === 'alta' ? 'Conhecida' : 'Revisar'" in js
    assert "tipo: reconhecimento?.tipo_sugerido === 'recorrencia'" in js


def test_alias_nao_cria_tabela_ou_migration():
    service = SERVICE_PATH.read_text(encoding='utf-8')

    assert 'Alias' not in service
    assert 'create_table' not in service
    assert 'op.create_table' not in service


def test_modal_edicao_lancamento_cartao_carrega_categoria_despesa_e_oculta_categoria_cartao():
    js = CARTOES_JS_PATH.read_text(encoding='utf-8')
    html = CARTOES_TEMPLATE_PATH.read_text(encoding='utf-8')
    css = CARTOES_CSS_PATH.read_text(encoding='utf-8')
    route = CARTOES_ROUTE_PATH.read_text(encoding='utf-8')
    modal = _trecho(html, '<div id="modal-editar-lancamento"', '{% endblock %}')

    assert 'const API_CATEGORIAS = \'/api/categorias\'' in js
    assert 'async function carregarCategoriasDespesaLancamento' in js
    assert 'async function preencherCategoriasDespesaLancamento' in js
    assert 'Não foi possível carregar as categorias de despesa.' in js
    assert 'fetchJson(`${API_CATEGORIAS}?ativo=true`)' in js
    assert 'categoria_id: document.getElementById(\'lancamento-edit-categoria\').value || null' in js
    assert 'Categoria de Despesa' in modal
    assert 'Categoria do Cartão' not in modal
    assert 'lancamento-edit-aviso' in modal
    assert 'Esta edi&ccedil;&atilde;o altera' in modal
    assert 'modal-content modal-md lancamento-edit-modal' in modal
    assert '.lancamento-edit-modal' in css
    assert 'CategoriaCartaoService.resolver_categoria_cartao_para_lancamento' in route
