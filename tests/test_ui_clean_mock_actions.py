from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_receitas_nao_expoe_acoes_mockadas():
    html = read('frontend/templates/receitas.html')
    js = read('frontend/static/js/receitas.js')

    assert 'onclick="mostrarFiltrosAvancados()"' not in html
    assert 'onclick="exportarReceitas()"' not in html
    assert 'onclick="mostrarMenuReceitas()"' not in html
    assert 'title="Mais ações"' not in js
    assert 'exportarReceitas' not in js
    assert 'mostrarMenuReceitas' not in js


def test_contas_bancarias_nao_expoe_acoes_mockadas():
    html = read('frontend/templates/contas_bancarias.html')
    js = read('frontend/static/js/contas_bancarias.js')

    assert 'onclick="mostrarFiltrosAvancados()"' not in html
    assert 'onclick="exportarContas()"' not in html
    assert 'aria-label="Ver em cards"' not in html
    assert 'aria-label="Ver em lista"' not in html
    assert 'mostrarFiltrosAvancados' not in js
    assert 'exportarContas' not in js


def test_recorrencias_nao_expoe_agenda_exportacao_sem_fluxo():
    html = read('frontend/templates/recorrencias.html')

    assert 'Ver agenda completa' not in html
    assert 'title="Exportar"' not in html
    assert '<span>Exportar</span>' not in html


def test_configuracoes_nao_expoe_placeholders_de_perfil_ou_backup():
    html = read('frontend/templates/configuracoes.html')
    js = read('frontend/static/js/configuracoes.js')

    assert 'data-config-placeholder' not in html
    assert 'config-profile-manage' not in html
    assert 'config-profile-duplicate' not in html
    assert '<strong>Exportar configurações</strong><span>Em breve</span>' not in html
    assert '<strong>Importar configurações</strong><span>Em breve</span>' not in html
    assert 'será disponibilizado em etapa futura' not in js


def test_preferencias_legada_foi_consolidada_em_configuracoes():
    assert not (ROOT / 'frontend/templates/preferencias.html').exists()
    assert not (ROOT / 'frontend/static/js/preferencias.js').exists()
    assert not (ROOT / 'frontend/static/css/preferencias.css').exists()


def test_ajuda_nao_expoe_abertura_de_chamado_placeholder():
    html = read('frontend/templates/ajuda.html')
    js = read('frontend/static/js/ajuda.js')

    assert 'data-help-placeholder' not in html
    assert 'Abrir chamado' not in html
    assert 'data-help-placeholder' not in js


def test_dashboard_nao_expoe_botao_filtros_sem_painel():
    html = read('frontend/templates/index.html')
    js = read('frontend/static/js/dashboard.js')

    assert 'id="dashboard-filtros"' not in html
    assert 'dashboard-filtros' not in js
