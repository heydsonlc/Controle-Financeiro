// ============================================
// PREFERÊNCIAS - JAVASCRIPT PRINCIPAL
// ============================================

const API_BASE = 'http://localhost:5000/api/preferencias';

// ============================================
// INICIALIZAÇÃO
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    carregarPreferencias();

    // Listener para color picker
    const colorPicker = document.getElementById('cor_principal');
    if (colorPicker) {
        colorPicker.addEventListener('input', (e) => {
            document.getElementById('cor_preview').textContent = e.target.value;
        });
    }
});

// ============================================
// NAVEGAÇÃO ENTRE ABAS
// ============================================
function mostrarAba(aba) {
    // Remover active de todos os botões e conteúdos
    document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    // Ativar aba selecionada
    const btnAtivo = Array.from(document.querySelectorAll('.tab-button'))
        .find(btn => btn.getAttribute('onclick').includes(aba));
    if (btnAtivo) btnAtivo.classList.add('active');

    const abaContent = document.getElementById(`aba-${aba}`);
    if (abaContent) abaContent.classList.add('active');
}

// ============================================
// CARREGAR PREFERÊNCIAS DO BACKEND
// ============================================
async function carregarPreferencias() {
    try {
        const response = await fetch(API_BASE);
        const data = await response.json();

        if (data.success) {
            const prefs = data.data;
            preencherFormularios(prefs);
        } else {
            console.error('Erro ao carregar preferências:', data.error);
        }
    } catch (error) {
        console.error('Erro na requisição:', error);
        mostrarErro('Erro ao carregar preferências');
    }
}

// ============================================
// PREENCHER FORMULÁRIOS COM DADOS
// ============================================
function preencherFormularios(prefs) {
    // ABA 1: Dados Pessoais
    setarCampo('nome_usuario', prefs.nome_usuario);
    setarCampo('renda_principal', prefs.renda_principal);
    setarCampo('mes_inicio_planejamento', prefs.mes_inicio_planejamento);
    setarCampo('dia_fechamento_mes', prefs.dia_fechamento_mes);

    // ABA 2: Comportamento - Lançamentos
    setarCheckbox('ajustar_competencia_automatico', prefs.ajustar_competencia_automatico);
    setarCheckbox('exibir_aviso_despesa_vencida', prefs.exibir_aviso_despesa_vencida);
    setarCheckbox('solicitar_confirmacao_exclusao', prefs.solicitar_confirmacao_exclusao);
    setarCheckbox('vincular_pagamento_cartao_auto', prefs.vincular_pagamento_cartao_auto);

    // ABA 2: Comportamento - Dashboard
    const graficosVisiveis = prefs.graficos_visiveis ? prefs.graficos_visiveis.split(',') : [];
    document.querySelectorAll('.grafico-check').forEach(check => {
        check.checked = graficosVisiveis.includes(check.value);
    });
    setarCheckbox('insights_inteligentes_ativo', prefs.insights_inteligentes_ativo);
    setarCheckbox('mostrar_saldo_consolidado', prefs.mostrar_saldo_consolidado);
    setarCheckbox('mostrar_evolucao_historica', prefs.mostrar_evolucao_historica);

    // ABA 2: Comportamento - Cartões
    setarCampo('dia_inicio_fatura', prefs.dia_inicio_fatura);
    setarCampo('dia_corte_fatura', prefs.dia_corte_fatura);
    setarCheckbox('lancamentos_agrupados', prefs.lancamentos_agrupados);
    setarCheckbox('orcamento_por_categoria', prefs.orcamento_por_categoria);

    // ABA 3: Aparência
    setarRadio('tema_sistema', prefs.tema_sistema);
    setarCampo('cor_principal', prefs.cor_principal);
    document.getElementById('cor_preview').textContent = prefs.cor_principal;
    setarCheckbox('mostrar_icones_coloridos', prefs.mostrar_icones_coloridos);
    setarCheckbox('abreviar_valores', prefs.abreviar_valores);

    // ABA 4: Backup
    setarCheckbox('backup_automatico', prefs.backup_automatico);

    // ABA 5: IA
    setarCheckbox('modo_inteligente_ativo', prefs.modo_inteligente_ativo);
    setarCheckbox('sugestoes_economia', prefs.sugestoes_economia);
    setarCheckbox('classificacao_automatica', prefs.classificacao_automatica);
    setarCheckbox('correcao_categorias', prefs.correcao_categorias);
    setarCheckbox('parcelas_recorrentes_auto', prefs.parcelas_recorrentes_auto);
}

// ============================================
// SALVAR PREFERÊNCIAS DE UMA ABA
// ============================================
async function salvarAba(aba) {
    const dados = {};

    switch(aba) {
        case 'dados-pessoais':
            dados.nome_usuario = obterCampo('nome_usuario');
            dados.renda_principal = parseFloat(obterCampo('renda_principal')) || 0;
            dados.mes_inicio_planejamento = parseInt(obterCampo('mes_inicio_planejamento'));
            dados.dia_fechamento_mes = parseInt(obterCampo('dia_fechamento_mes'));
            break;

        case 'comportamento':
            // Lançamentos
            dados.ajustar_competencia_automatico = obterCheckbox('ajustar_competencia_automatico');
            dados.exibir_aviso_despesa_vencida = obterCheckbox('exibir_aviso_despesa_vencida');
            dados.solicitar_confirmacao_exclusao = obterCheckbox('solicitar_confirmacao_exclusao');
            dados.vincular_pagamento_cartao_auto = obterCheckbox('vincular_pagamento_cartao_auto');

            // Dashboard
            const graficosChecked = Array.from(document.querySelectorAll('.grafico-check:checked'))
                .map(check => check.value);
            dados.graficos_visiveis = graficosChecked.join(',');
            dados.insights_inteligentes_ativo = obterCheckbox('insights_inteligentes_ativo');
            dados.mostrar_saldo_consolidado = obterCheckbox('mostrar_saldo_consolidado');
            dados.mostrar_evolucao_historica = obterCheckbox('mostrar_evolucao_historica');

            // Cartões
            dados.dia_inicio_fatura = parseInt(obterCampo('dia_inicio_fatura'));
            dados.dia_corte_fatura = parseInt(obterCampo('dia_corte_fatura'));
            dados.lancamentos_agrupados = obterCheckbox('lancamentos_agrupados');
            dados.orcamento_por_categoria = obterCheckbox('orcamento_por_categoria');
            break;

        case 'aparencia':
            dados.tema_sistema = obterRadio('tema_sistema');
            dados.cor_principal = obterCampo('cor_principal');
            dados.mostrar_icones_coloridos = obterCheckbox('mostrar_icones_coloridos');
            dados.abreviar_valores = obterCheckbox('abreviar_valores');
            break;

        case 'backup':
            dados.backup_automatico = obterCheckbox('backup_automatico');
            break;

        case 'ia':
            dados.modo_inteligente_ativo = obterCheckbox('modo_inteligente_ativo');
            dados.sugestoes_economia = obterCheckbox('sugestoes_economia');
            dados.classificacao_automatica = obterCheckbox('classificacao_automatica');
            dados.correcao_categorias = obterCheckbox('correcao_categorias');
            dados.parcelas_recorrentes_auto = obterCheckbox('parcelas_recorrentes_auto');
            break;
    }

    try {
        const response = await fetch(API_BASE, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso('Preferências salvas com sucesso!');
        } else {
            mostrarErro('Erro ao salvar: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao salvar:', error);
        mostrarErro('Erro ao salvar preferências');
    }
}

// ============================================
// FUNÇÕES AUXILIARES DE FORMULÁRIO
// ============================================
function setarCampo(id, valor) {
    const campo = document.getElementById(id);
    if (campo && valor !== null && valor !== undefined) {
        campo.value = valor;
    }
}

function setarCheckbox(id, valor) {
    const checkbox = document.getElementById(id);
    if (checkbox) {
        checkbox.checked = Boolean(valor);
    }
}

function setarRadio(name, valor) {
    const radio = document.querySelector(`input[name="${name}"][value="${valor}"]`);
    if (radio) {
        radio.checked = true;
    }
}

function obterCampo(id) {
    const campo = document.getElementById(id);
    return campo ? campo.value : '';
}

function obterCheckbox(id) {
    const checkbox = document.getElementById(id);
    return checkbox ? checkbox.checked : false;
}

function obterRadio(name) {
    const radio = document.querySelector(`input[name="${name}"]:checked`);
    return radio ? radio.value : '';
}

// ============================================
// FUNÇÕES DE BACKUP (FUTURAS)
// ============================================
function exportarDados() {
    alert('Funcionalidade de exportação será implementada em breve.\n\nVocê poderá exportar todos os seus dados em formato JSON.');
}

function importarDados() {
    alert('Funcionalidade de importação será implementada em breve.\n\nVocê poderá importar um backup anteriormente exportado.');
}

function resetarConfiguracoes() {
    if (confirm('Deseja resetar as configurações para os valores padrão?\n\nEsta ação não afetará seus dados financeiros.')) {
        alert('Funcionalidade será implementada em breve.');
    }
}

function resetarCompleto() {
    const confirmacao1 = confirm('⚠️ ATENÇÃO! Esta ação APAGARÁ TODOS OS DADOS do sistema!\n\nDeseja continuar?');

    if (!confirmacao1) return;

    const confirmacao2 = confirm('⚠️ CONFIRMAÇÃO FINAL!\n\nTodos os seus lançamentos, categorias, receitas, despesas e configurações serão PERMANENTEMENTE APAGADOS!\n\nTem ABSOLUTA CERTEZA?');

    if (confirmacao2) {
        alert('Funcionalidade será implementada em breve.\n\nPor segurança, esta ação requer autenticação adicional.');
    }
}

// ============================================
// NOTIFICAÇÕES
// ============================================
function mostrarSucesso(mensagem) {
    alert('✅ ' + mensagem);
}

function mostrarErro(mensagem) {
    alert('❌ ' + mensagem);
}
