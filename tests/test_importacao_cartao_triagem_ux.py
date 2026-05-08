from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / 'frontend' / 'static' / 'js' / 'importar_cartao.js'
TEMPLATE_PATH = ROOT / 'frontend' / 'templates' / 'importar_cartao.html'
SERVICE_PATH = ROOT / 'backend' / 'services' / 'importacao_cartao_service.py'
ROUTE_PATH = ROOT / 'backend' / 'routes' / 'importacao_cartao.py'


def _trecho(texto, inicio, fim):
    start = texto.index(inicio)
    end = texto.index(fim, start)
    return texto[start:end]


def test_primeira_tabela_e_triagem_bruta_sem_classificacao():
    js = JS_PATH.read_text(encoding='utf-8')

    tabela = _trecho(js, 'function renderizarEditorPrePersistencia', 'function renderizarLinhaPrevia')
    linha = _trecho(js, 'function renderizarLinhaPrevia', 'function renderizarConfrontoClassificacao')

    assert 'Descrição original' in tabela
    assert 'Categoria da Despesa' not in tabela
    assert 'Categoria do Cartão' not in tabela
    assert '<th>Parcela</th>' not in tabela

    assert 'opcoesCategoriaSelect' not in linha
    assert 'opcoesCategoriaCartaoSelect' not in linha
    assert "atualizarLinhaEdicao" not in linha
    assert 'gerar_parcelas_futuras' not in linha


def test_triagem_tem_filtros_contadores_e_payload_filtrado():
    js = JS_PATH.read_text(encoding='utf-8')

    assert "['a_importar', 'A importar'" in js
    assert "['ignorados', 'Ignorados'" in js
    assert "['todas', 'Todos'" in js
    assert 'function linhaImportavel' in js
    assert '.filter(linhaImportavel)' in js
    assert 'Nenhum lançamento selecionado para importação.' in js


def test_confronto_separa_novos_duplicados_e_parcelamentos():
    js = JS_PATH.read_text(encoding='utf-8')
    confronto = _trecho(js, 'function montarAnaliseConfronto', 'function linhasNovasConfirmaveis')

    assert 'grupos.novos.push' in confronto
    assert 'grupos.duplicados.push' in confronto
    assert 'grupos.parcelamentos.push' in confronto
    assert 'if (linha.ignorar && !linhaDuplicada(linha) && !linhaComErro(linha)) return;' in confronto
    assert 'linhaDuplicada(linha)' in confronto
    assert 'detectarParcelamentoLinha(linha)' in confronto


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


def test_categoria_aparece_somente_no_confronto_de_novos():
    js = JS_PATH.read_text(encoding='utf-8')
    triagem = _trecho(js, 'function renderizarEditorPrePersistencia', 'function renderizarConfrontoClassificacao')
    novos = _trecho(js, 'function renderizarGrupoNovosConfronto', 'function renderizarLinhaNovoConfronto')
    linha_novo = _trecho(js, 'function renderizarLinhaNovoConfronto', 'function renderizarGrupoAlertaConfronto')
    alertas = _trecho(js, 'function renderizarGrupoAlertaConfronto', 'function statusConfrontoLabel')
    parcelamentos = _trecho(js, 'function renderizarGrupoParcelamentosConfronto', 'function renderizarGrupoAlertaConfronto')

    assert 'Categoria da despesa' not in triagem
    assert 'Categoria do cartao' not in triagem
    assert 'Categoria da despesa' in novos
    assert 'opcoesCategoriaSelect' in linha_novo
    assert 'opcoesCategoriaCartaoSelect' in linha_novo
    assert 'Criar parcelamento' in parcelamentos
    assert 'opcoesCategoriaSelect' not in parcelamentos
    assert 'opcoesCategoriaCartaoSelect' not in parcelamentos
    assert 'opcoesCategoriaSelect' not in alertas
    assert 'opcoesCategoriaCartaoSelect' not in alertas


def test_template_nao_exibe_classificacao_como_etapa_principal():
    html = TEMPLATE_PATH.read_text(encoding='utf-8')

    assert '4. Triagem' in html
    assert '4. Classificação' not in html
    assert '5. Confronto e Resultado' in html
    assert 'confrontoContainer' in html
    assert 'Confrontar selecionados' in html
    assert 'parcelamentoModal' in html
    assert 'Criar parcelamento a partir do lançamento importado' in html
    assert 'Categoria da despesa' in html
    assert 'Valor a importar' in html
    assert 'Duplicados protegidos' in html


def test_backend_cria_parcelamento_atual_e_futuro_sem_migration():
    service = SERVICE_PATH.read_text(encoding='utf-8')
    route = ROUTE_PATH.read_text(encoding='utf-8')

    assert "MAX_PARCELAS_IMPORTACAO = 60" in service
    assert "numero_inicial = numero_parcela if linha.get('gerar_apenas_atual_e_futuras') else 1" in service
    assert "for numero in range(numero_inicial, total_parcelas + 1)" in service
    assert "@bp.route('/parcelamento', methods=['POST'])" in route
    assert "linha['gerar_parcelas_futuras'] = True" in route
    assert "linha['gerar_apenas_atual_e_futuras'] = True" in route
