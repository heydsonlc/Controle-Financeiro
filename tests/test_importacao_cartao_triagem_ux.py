from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / 'frontend' / 'static' / 'js' / 'importar_cartao.js'
TEMPLATE_PATH = ROOT / 'frontend' / 'templates' / 'importar_cartao.html'
CSS_PATH = ROOT / 'frontend' / 'static' / 'css' / 'importar_cartao.css'
SERVICE_PATH = ROOT / 'backend' / 'services' / 'importacao_cartao_service.py'
ROUTE_PATH = ROOT / 'backend' / 'routes' / 'importacao_cartao.py'


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

    for coluna in ['Motivo', 'Data', 'Descrição original', 'Valor', 'Ação']:
        assert coluna in retirados

    assert "paginarItens(retirados, 'retirados')" in retirados
    assert "motivo === 'Retirado pelo usuário'" in js
    assert "botaoOperacional('success', 'Restaurar'" in js
    assert "botaoOperacional('', 'Ver'" in js
    assert "['parcelamento', 'Parcelamento tratado'" in js
    assert "['credito', 'Crédito/estorno'" in js


def test_kpis_ficam_na_area_inferior_e_nao_na_barra_superior():
    html = TEMPLATE_PATH.read_text(encoding='utf-8')
    js = JS_PATH.read_text(encoding='utf-8')
    css = CSS_PATH.read_text(encoding='utf-8')
    topbar = _trecho(html, '<section class="import-topbar-compact"', '<div id="uploadResult"')

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


def test_detector_js_aceita_variacoes_e_rejeita_invalidos():
    js = JS_PATH.read_text(encoding='utf-8')
    detector = _trecho(js, 'function validarNumerosParcelamento', 'function detectarParcelaDescricao')
    script = f"""
const MAX_PARCELAS_IMPORTACAO = 60;
{detector}
const validos = [
  'LOJA X 01/10',
  'LOJA X 1/10',
  'LOJA X 07 de 10',
  'LOJA X 7 de 10',
  'LOJA X PARCELA 03 DE 05',
  'LOJA X PARC 3 de 5',
  'LOJA X PARC. 3 DE 5',
  'LOJA X 2 de 12'
].map((texto) => detectarParcelamentoTexto(texto)?.rotulo || null);
const invalidos = [
  'LOJA X 10 de 1',
  'LOJA X 0 de 10',
  'LOJA X 1 de 0',
  'LOJA X 13 de 12',
  'LOJA X 99 de 100'
].map((texto) => detectarParcelamentoTexto(texto));
console.log(JSON.stringify({{ validos, invalidos }}));
"""
    resultado = subprocess.run(['node', '-e', script], text=True, capture_output=True, check=True)
    dados = json.loads(resultado.stdout)

    assert dados['validos'] == ['1/10', '1/10', '7/10', '7/10', '3/5', '3/5', '3/5', '2/12']
    assert dados['invalidos'] == [None, None, None, None, None]


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

    assert "('APPLE', None, ('APPLECOMBILL'" in service
    assert "('AMAZON', 'AMAZON MUSIC'" in service
    assert "('AMAZON', 'AMAZON PRIME'" in service
    assert "score < 60" in service
    assert "tipo = 'duplicado_atual'" in service
    assert "@bp.route('/reconhecer', methods=['POST'])" in route
