(function () {
    'use strict';

    const API_PERFIS = '/api/perfis-financeiros';
    const API_PREFERENCIAS = '/api/preferencias';
    const state = {
        perfis: [],
        ativo: null,
        selecionado: null,
        preferencias: {},
        secao: 'perfis-financeiros'
    };

    const $ = (id) => document.getElementById(id);

    const ajuda = {
        'perfis-financeiros': {
            titulo: 'Como funciona o contexto financeiro',
            itens: [
                ['Perfis independentes', 'Cada perfil possui dados, configurações e relatórios separados.'],
                ['Troca rápida', 'Alterne entre perfis pelo seletor no topo sem sair da aplicação.'],
                ['Personalização total', 'Defina preferências e comportamentos específicos para cada perfil.'],
                ['Dica', 'Crie perfis para separar suas finanças pessoais das da empresa.']
            ]
        },
        'preferencias-gerais': {
            titulo: 'Preferências globais',
            itens: [
                ['Dados preservados', 'A tela usa os mesmos campos e a mesma API de Preferências já existente.'],
                ['Escopo atual', 'Estas preferências continuam globais até uma etapa específica de preferências por perfil.']
            ]
        },
        aparencia: {
            titulo: 'Aparência',
            itens: [
                ['Tema e cor', 'As opções visuais existentes foram consolidadas nesta central.'],
                ['Evolução futura', 'Densidade visual e estilos avançados podem ser adicionados depois.']
            ]
        },
        comportamento: {
            titulo: 'Comportamento',
            itens: [
                ['Ações sensíveis', 'Confirmações e avisos continuam controlados como preferências globais.'],
                ['Sem regras novas', 'Nenhuma regra financeira foi alterada nesta tela.']
            ]
        },
        backup: {
            titulo: 'Backup',
            itens: [
                ['Em breve', 'Importação e exportação de configurações ainda são placeholders seguros.'],
                ['Banco oficial', 'Backup operacional do PostgreSQL deve ser tratado em rotina própria.']
            ]
        },
        'ia-automacao': {
            titulo: 'IA e Automação',
            itens: [
                ['Classificação', 'Preferências existentes para automação continuam disponíveis.'],
                ['Sem IA nova', 'Esta etapa não adiciona integração externa nem modelos novos.']
            ]
        },
        'documentos-fiscais': {
            titulo: 'Documentos fiscais por perfil',
            itens: [
                ['Pessoal', 'O perfil pessoal usa Imposto de Renda e comprovantes potencialmente dedutíveis.'],
                ['Empresa', 'O perfil empresa usa Documentos Fiscais e Lastro Empresarial.'],
                ['Revisão fiscal', 'Classificações seguem informativas e sujeitas à validação contábil.']
            ]
        }
    };

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[char]));
    }

    function iniciais(perfil) {
        if (perfil?.avatar) return String(perfil.avatar).slice(0, 3).toUpperCase();
        const partes = String(perfil?.nome || 'PF').trim().split(/\s+/).filter(Boolean);
        if (!partes.length) return 'PF';
        if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
        return `${partes[0][0]}${partes[1][0]}`.toUpperCase();
    }

    function tipoLabel(tipo) {
        const value = String(tipo || '').toUpperCase();
        if (value === 'PESSOAL') return 'Pessoal';
        if (value === 'EMPRESA') return 'Empresa';
        return 'Outro';
    }

    function mostrarMensagem(message, tipo = 'info') {
        const alert = $('config-profile-alert');
        if (!alert) return;
        alert.textContent = message || '';
        alert.dataset.tipo = tipo;
        alert.hidden = !message;
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                ...(options.headers || {})
            },
            ...options
        });
        const data = await response.json();
        if (!response.ok || data?.success === false) {
            throw new Error(data.error || data.message || 'Falha na operação');
        }
        return data;
    }

    async function carregarPerfis() {
        const data = await requestJson(`${API_PERFIS}/config`);
        state.perfis = data.perfis || [];
        state.ativo = data.perfil_ativo || null;
        if (!state.selecionado || !state.perfis.some((perfil) => Number(perfil.id) === Number(state.selecionado.id))) {
            state.selecionado = state.perfis.find((perfil) => Number(perfil.id) === Number(state.ativo?.id)) || state.perfis[0] || null;
        } else {
            state.selecionado = state.perfis.find((perfil) => Number(perfil.id) === Number(state.selecionado.id));
        }
        renderPerfis();
        preencherFormularioPerfil(state.selecionado);
    }

    async function carregarPreferencias() {
        const data = await requestJson(API_PREFERENCIAS);
        state.preferencias = data.data || {};
        preencherPreferencias(state.preferencias);
    }

    function renderPerfis() {
        const destino = $('config-profiles-list');
        if (!destino) return;
        if (!state.perfis.length) {
            destino.innerHTML = '<div class="config-empty-state">Nenhum perfil financeiro cadastrado. Crie um perfil para começar a organizar seus dados por contexto.</div>';
            return;
        }

        const cards = state.perfis.map((perfil) => {
            const selecionado = Number(state.selecionado?.id) === Number(perfil.id);
            const emUso = Number(state.ativo?.id) === Number(perfil.id);
            const statusClasse = perfil.ativo ? (emUso ? 'active' : 'available') : 'inactive';
            const statusLabel = perfil.ativo ? (emUso ? 'Ativo' : 'Disponível') : 'Inativo';
            return `
                <button type="button" class="config-profile-card${selecionado ? ' active' : ''}" data-profile-id="${escapeHtml(perfil.id)}">
                    <span class="config-profile-avatar" style="--profile-color:${escapeHtml(perfil.cor || '#2563eb')}">${escapeHtml(iniciais(perfil))}</span>
                    <span class="config-profile-main">
                        <strong>${escapeHtml(perfil.nome)}</strong>
                        <small>${escapeHtml(tipoLabel(perfil.tipo))}${perfil.documento ? ` · ${escapeHtml(perfil.documento)}` : ''}</small>
                        <span class="config-profile-badges">
                            <span class="config-profile-badge ${statusClasse}">${statusLabel}</span>
                            ${perfil.padrao ? '<span class="config-profile-badge default">Padrão</span>' : ''}
                            ${emUso ? '<span class="config-profile-badge current">Perfil em uso</span>' : ''}
                        </span>
                    </span>
                    <span aria-hidden="true">›</span>
                </button>
            `;
        });

        cards.push(`
            <button type="button" class="config-profile-new-card" id="config-profile-card-new">
                <span class="config-profile-plus" aria-hidden="true">+</span>
                <span class="config-profile-main">
                    <strong>Novo perfil</strong>
                    <small>Crie um novo perfil financeiro</small>
                </span>
            </button>
        `);
        destino.innerHTML = cards.join('');
    }

    function preencherFormularioPerfil(perfil) {
        $('config-profile-id').value = perfil?.id || '';
        $('config-profile-nome').value = perfil?.nome || '';
        $('config-profile-tipo').value = perfil?.tipo || 'PESSOAL';
        $('config-profile-avatar').value = perfil?.avatar || '';
        $('config-profile-documento').value = perfil?.documento || '';
        $('config-profile-cor').value = perfil?.cor || '#2563eb';
        $('config-profile-ativo').checked = perfil ? Boolean(perfil.ativo) : true;
        $('config-profile-padrao').checked = perfil ? Boolean(perfil.padrao) : false;
        atualizarChecksConceituais();
    }

    function novoPerfil() {
        state.selecionado = null;
        renderPerfis();
        preencherFormularioPerfil(null);
        mostrarMensagem('Novo perfil em edição. Preencha os dados e salve para criar.', 'info');
        $('config-profile-nome')?.focus();
    }

    function payloadPerfilBase() {
        return {
            nome: $('config-profile-nome').value.trim(),
            tipo: $('config-profile-tipo').value,
            documento: $('config-profile-documento').value.trim(),
            cor: $('config-profile-cor').value || '#2563eb',
            avatar: $('config-profile-avatar').value.trim()
        };
    }

    async function salvarPerfil() {
        mostrarMensagem('');
        const id = $('config-profile-id').value;
        const desejaAtivo = $('config-profile-ativo').checked;
        const desejaPadrao = $('config-profile-padrao').checked;
        const perfilAntes = id ? state.perfis.find((perfil) => Number(perfil.id) === Number(id)) : null;

        try {
            let perfilSalvo;
            if (id) {
                const payload = payloadPerfilBase();
                const resposta = await requestJson(`${API_PERFIS}/${id}`, {
                    method: 'PUT',
                    body: JSON.stringify(payload)
                });
                perfilSalvo = resposta.perfil;

                if (perfilAntes?.ativo && !desejaAtivo) {
                    await requestJson(`${API_PERFIS}/${id}/inativar`, { method: 'POST' });
                } else if (!perfilAntes?.ativo && desejaAtivo) {
                    await requestJson(`${API_PERFIS}/${id}/reativar`, { method: 'POST' });
                }
            } else {
                const resposta = await requestJson(API_PERFIS, {
                    method: 'POST',
                    body: JSON.stringify({ ...payloadPerfilBase(), ativo: desejaAtivo, padrao: desejaPadrao })
                });
                perfilSalvo = resposta.perfil;
            }

            if (desejaPadrao && desejaAtivo && perfilSalvo?.id) {
                await requestJson(`${API_PERFIS}/${perfilSalvo.id}/padrao`, { method: 'POST' });
            }

            state.selecionado = perfilSalvo;
            await carregarPerfis();
            atualizarTopbar();
            mostrarMensagem('Configurações do perfil salvas.', 'success');
        } catch (error) {
            mostrarMensagem(error.message);
        }
    }

    async function definirPerfilAtivo(perfil) {
        if (!perfil || !perfil.ativo) return;
        try {
            await requestJson(`${API_PERFIS}/ativo`, {
                method: 'POST',
                body: JSON.stringify({ perfil_id: perfil.id })
            });
            state.ativo = perfil;
            state.selecionado = perfil;
            await carregarPerfis();
            atualizarTopbar();
            mostrarMensagem(`Perfil em uso alterado para ${perfil.nome}.`, 'success');
        } catch (error) {
            mostrarMensagem(error.message);
        }
    }

    function atualizarTopbar() {
        if (window.ContextoFinanceiroUI?.init) {
            window.ContextoFinanceiroUI.init();
        }
    }

    function atualizarChecksConceituais() {
        const tipo = String($('config-profile-tipo')?.value || '').toUpperCase();
        const ativo = $('config-profile-ativo')?.checked;
        const irpf = $('config-profile-irpf');
        const docs = $('config-profile-docs');
        const topbar = $('config-profile-topbar');
        const switcher = $('config-profile-switch');
        if (irpf) irpf.checked = tipo !== 'EMPRESA';
        if (docs) docs.checked = tipo === 'EMPRESA';
        if (topbar) topbar.checked = Boolean(ativo);
        if (switcher) switcher.checked = Boolean(ativo);
    }

    function preencherPreferencias(prefs) {
        setCampo('nome_usuario', prefs.nome_usuario);
        setCampo('renda_principal', prefs.renda_principal);
        setCampo('mes_inicio_planejamento', prefs.mes_inicio_planejamento || 1);
        setCampo('dia_fechamento_mes', prefs.dia_fechamento_mes || 1);
        setCheckbox('ajustar_competencia_automatico', prefs.ajustar_competencia_automatico);
        setCheckbox('exibir_aviso_despesa_vencida', prefs.exibir_aviso_despesa_vencida);
        setCheckbox('solicitar_confirmacao_exclusao', prefs.solicitar_confirmacao_exclusao);
        setCheckbox('vincular_pagamento_cartao_auto', prefs.vincular_pagamento_cartao_auto);
        setRadio('tema_sistema', prefs.tema_sistema || 'claro');
        setCampo('cor_principal', prefs.cor_principal || '#3b82f6');
        const preview = $('cor_preview');
        if (preview) preview.textContent = prefs.cor_principal || '#3b82f6';
        setCheckbox('mostrar_icones_coloridos', prefs.mostrar_icones_coloridos);
        setCheckbox('abreviar_valores', prefs.abreviar_valores);
        setCheckbox('modo_inteligente_ativo', prefs.modo_inteligente_ativo);
        setCheckbox('sugestoes_economia', prefs.sugestoes_economia);
        setCheckbox('classificacao_automatica', prefs.classificacao_automatica);
        setCheckbox('correcao_categorias', prefs.correcao_categorias);
    }

    async function salvarPreferencias(escopo) {
        const dados = {};
        if (escopo === 'gerais') {
            dados.nome_usuario = obterCampo('nome_usuario');
            dados.renda_principal = parseFloat(obterCampo('renda_principal')) || 0;
            dados.mes_inicio_planejamento = parseInt(obterCampo('mes_inicio_planejamento'), 10) || 1;
            dados.dia_fechamento_mes = parseInt(obterCampo('dia_fechamento_mes'), 10) || 1;
        }
        if (escopo === 'aparencia') {
            dados.tema_sistema = obterRadio('tema_sistema') || 'claro';
            dados.cor_principal = obterCampo('cor_principal') || '#3b82f6';
            dados.mostrar_icones_coloridos = obterCheckbox('mostrar_icones_coloridos');
            dados.abreviar_valores = obterCheckbox('abreviar_valores');
        }
        if (escopo === 'comportamento') {
            dados.ajustar_competencia_automatico = obterCheckbox('ajustar_competencia_automatico');
            dados.exibir_aviso_despesa_vencida = obterCheckbox('exibir_aviso_despesa_vencida');
            dados.solicitar_confirmacao_exclusao = obterCheckbox('solicitar_confirmacao_exclusao');
            dados.vincular_pagamento_cartao_auto = obterCheckbox('vincular_pagamento_cartao_auto');
        }
        if (escopo === 'ia') {
            dados.modo_inteligente_ativo = obterCheckbox('modo_inteligente_ativo');
            dados.sugestoes_economia = obterCheckbox('sugestoes_economia');
            dados.classificacao_automatica = obterCheckbox('classificacao_automatica');
            dados.correcao_categorias = obterCheckbox('correcao_categorias');
        }

        try {
            await requestJson(API_PREFERENCIAS, {
                method: 'PUT',
                body: JSON.stringify(dados)
            });
            await carregarPreferencias();
            mostrarMensagem('Preferências salvas.', 'success');
        } catch (error) {
            mostrarMensagem(error.message);
        }
    }

    function trocarSecao(secao) {
        state.secao = secao || 'perfis-financeiros';
        document.querySelectorAll('[data-config-section]').forEach((panel) => {
            panel.classList.toggle('active', panel.dataset.configSection === state.secao);
        });
        document.querySelectorAll('[data-config-section-target]').forEach((link) => {
            link.classList.toggle('active', link.dataset.configSectionTarget === state.secao);
        });
        renderAjuda();
        if (window.location.hash !== `#${state.secao}`) {
            history.replaceState(null, '', `#${state.secao}`);
        }
    }

    function renderAjuda() {
        const data = ajuda[state.secao] || ajuda['perfis-financeiros'];
        const title = $('config-help-title');
        const content = $('config-help-content');
        if (title) title.textContent = data.titulo;
        if (!content) return;
        content.innerHTML = `
            <div class="config-help-list">
                ${data.itens.map((item, index) => `
                    <div class="config-help-item">
                        <span class="config-help-marker" aria-hidden="true">${index + 1}</span>
                        <span>
                            <strong>${escapeHtml(item[0])}</strong>
                            <span>${escapeHtml(item[1])}</span>
                        </span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    function setCampo(id, valor) {
        const campo = $(id);
        if (campo && valor !== null && valor !== undefined) campo.value = valor;
    }

    function setCheckbox(id, valor) {
        const campo = $(id);
        if (campo) campo.checked = Boolean(valor);
    }

    function setRadio(name, valor) {
        const campo = document.querySelector(`input[name="${name}"][value="${valor}"]`);
        if (campo) campo.checked = true;
    }

    function obterCampo(id) {
        return $(id)?.value || '';
    }

    function obterCheckbox(id) {
        return Boolean($(id)?.checked);
    }

    function obterRadio(name) {
        return document.querySelector(`input[name="${name}"]:checked`)?.value || '';
    }

    function bind() {
        document.querySelectorAll('[data-config-section-target]').forEach((button) => {
            button.addEventListener('click', () => trocarSecao(button.dataset.configSectionTarget));
        });

        document.querySelectorAll('[data-config-placeholder]').forEach((button) => {
            button.addEventListener('click', () => mostrarMensagem(`${button.dataset.configPlaceholder} será disponibilizado em etapa futura.`, 'info'));
        });

        $('config-profiles-list')?.addEventListener('click', (event) => {
            const newCard = event.target.closest('#config-profile-card-new');
            if (newCard) {
                novoPerfil();
                return;
            }
            const card = event.target.closest('[data-profile-id]');
            if (!card) return;
            const perfil = state.perfis.find((item) => Number(item.id) === Number(card.dataset.profileId));
            state.selecionado = perfil;
            renderPerfis();
            preencherFormularioPerfil(perfil);
            mostrarMensagem('');
        });

        $('config-profile-new')?.addEventListener('click', novoPerfil);
        $('config-profile-cancel')?.addEventListener('click', () => {
            state.selecionado = state.perfis.find((perfil) => Number(perfil.id) === Number(state.ativo?.id)) || state.perfis[0] || null;
            renderPerfis();
            preencherFormularioPerfil(state.selecionado);
            mostrarMensagem('');
        });
        $('config-profile-save')?.addEventListener('click', salvarPerfil);
        $('config-profile-use')?.addEventListener('click', () => definirPerfilAtivo(state.selecionado));
        $('config-profile-manage')?.addEventListener('click', () => mostrarMensagem('Use os cards e o formulário para gerenciar perfis nesta central.', 'info'));
        $('config-profile-tipo')?.addEventListener('change', atualizarChecksConceituais);
        $('config-profile-ativo')?.addEventListener('change', atualizarChecksConceituais);
        $('config-preferences-save')?.addEventListener('click', () => salvarPreferencias('gerais'));

        document.querySelectorAll('[data-preferences-save]').forEach((button) => {
            button.addEventListener('click', () => salvarPreferencias(button.dataset.preferencesSave));
        });

        $('cor_principal')?.addEventListener('input', (event) => {
            const preview = $('cor_preview');
            if (preview) preview.textContent = event.target.value;
        });
    }

    async function init() {
        if (!document.querySelector('[data-config-page]')) return;
        bind();
        const secaoInicial = window.location.hash ? window.location.hash.slice(1) : 'perfis-financeiros';
        trocarSecao(document.querySelector(`[data-config-section="${secaoInicial}"]`) ? secaoInicial : 'perfis-financeiros');
        try {
            await Promise.all([carregarPerfis(), carregarPreferencias()]);
        } catch (error) {
            mostrarMensagem(error.message);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
