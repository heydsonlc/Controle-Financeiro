(function () {
    'use strict';

    const API = '/api/perfis-financeiros';
    const state = { perfis: [], ativo: null, editando: null };

    const $ = (id) => document.getElementById(id);

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

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', ...(options.headers || {}) },
            ...options
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Falha na operacao');
        return data;
    }

    async function carregarPerfis() {
        const data = await requestJson(`${API}/config`);
        state.perfis = data.perfis || [];
        state.ativo = data.perfil_ativo || null;
        renderPerfis();
    }

    function renderPerfis() {
        const destino = $('config-profiles-list');
        if (!destino) return;
        if (!state.perfis.length) {
            destino.innerHTML = '<div class="config-profile-empty">Nenhum perfil financeiro cadastrado.</div>';
            return;
        }
        destino.innerHTML = state.perfis.map((perfil) => `
            <article class="config-profile-card" data-profile-id="${escapeHtml(perfil.id)}">
                <span class="config-profile-avatar" style="--profile-color:${escapeHtml(perfil.cor || '#2563eb')}">${escapeHtml(iniciais(perfil))}</span>
                <div class="config-profile-main">
                    <strong>${escapeHtml(perfil.nome)}</strong>
                    <small>${escapeHtml(tipoLabel(perfil.tipo))}${perfil.documento ? ` · ${escapeHtml(perfil.documento)}` : ''}</small>
                    <div class="config-profile-badges">
                        <span class="config-profile-badge ${perfil.ativo ? 'active' : 'inactive'}">${perfil.ativo ? 'Ativo' : 'Inativo'}</span>
                        ${perfil.padrao ? '<span class="config-profile-badge default">Padrao</span>' : ''}
                        ${Number(state.ativo?.id) === Number(perfil.id) ? '<span class="config-profile-badge default">Em uso</span>' : ''}
                    </div>
                </div>
                <div class="config-profile-actions">
                    <button type="button" class="config-profile-action" data-action="edit">Editar</button>
                    ${perfil.ativo && !perfil.padrao ? '<button type="button" class="config-profile-action" data-action="default">Definir padrao</button>' : ''}
                    ${perfil.ativo
                        ? '<button type="button" class="config-profile-action danger" data-action="deactivate">Inativar</button>'
                        : '<button type="button" class="config-profile-action success" data-action="reactivate">Reativar</button>'}
                </div>
            </article>
        `).join('');
    }

    function mostrarAlerta(message) {
        const alert = $('config-profile-alert');
        if (!alert) return;
        alert.textContent = message || '';
        alert.hidden = !message;
    }

    function abrirModal(perfil = null) {
        state.editando = perfil;
        $('config-profile-title').textContent = perfil ? 'Editar perfil financeiro' : 'Novo perfil financeiro';
        $('config-profile-id').value = perfil?.id || '';
        $('config-profile-nome').value = perfil?.nome || '';
        $('config-profile-tipo').value = perfil?.tipo || 'PESSOAL';
        $('config-profile-documento').value = perfil?.documento || '';
        $('config-profile-cor').value = perfil?.cor || '#2563eb';
        $('config-profile-avatar').value = perfil?.avatar || '';
        $('config-profile-ativo').checked = perfil ? Boolean(perfil.ativo) : true;
        $('config-profile-modal').classList.add('open');
        $('config-profile-modal').setAttribute('aria-hidden', 'false');
    }

    function fecharModal() {
        $('config-profile-modal')?.classList.remove('open');
        $('config-profile-modal')?.setAttribute('aria-hidden', 'true');
        state.editando = null;
    }

    function payloadFormulario() {
        return {
            nome: $('config-profile-nome').value,
            tipo: $('config-profile-tipo').value,
            documento: $('config-profile-documento').value,
            cor: $('config-profile-cor').value,
            avatar: $('config-profile-avatar').value,
            ativo: $('config-profile-ativo').checked
        };
    }

    async function salvarPerfil() {
        mostrarAlerta('');
        const id = $('config-profile-id').value;
        const payload = payloadFormulario();
        try {
            if (id) {
                await requestJson(`${API}/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
            } else {
                await requestJson(API, { method: 'POST', body: JSON.stringify(payload) });
            }
            fecharModal();
            await carregarPerfis();
            if (window.ContextoFinanceiroUI?.init) window.ContextoFinanceiroUI.init();
        } catch (error) {
            mostrarAlerta(error.message);
        }
    }

    async function executarAcao(perfil, action) {
        if (!perfil) return;
        mostrarAlerta('');
        try {
            if (action === 'edit') {
                abrirModal(perfil);
                return;
            }
            if (action === 'deactivate') {
                const ok = window.confirm('Este perfil sera ocultado da selecao, mas os dados vinculados serao preservados.');
                if (!ok) return;
                await requestJson(`${API}/${perfil.id}/inativar`, { method: 'POST' });
            }
            if (action === 'reactivate') {
                await requestJson(`${API}/${perfil.id}/reativar`, { method: 'POST' });
            }
            if (action === 'default') {
                await requestJson(`${API}/${perfil.id}/padrao`, { method: 'POST' });
            }
            await carregarPerfis();
            if (window.ContextoFinanceiroUI?.init) window.ContextoFinanceiroUI.init();
        } catch (error) {
            mostrarAlerta(error.message);
        }
    }

    function bind() {
        $('config-profile-new')?.addEventListener('click', () => abrirModal());
        $('config-profile-close')?.addEventListener('click', fecharModal);
        $('config-profile-cancel')?.addEventListener('click', fecharModal);
        $('config-profile-save')?.addEventListener('click', salvarPerfil);
        $('config-profiles-list')?.addEventListener('click', (event) => {
            const button = event.target.closest('[data-action]');
            if (!button) return;
            const card = event.target.closest('[data-profile-id]');
            const perfil = state.perfis.find((item) => Number(item.id) === Number(card?.dataset.profileId));
            executarAcao(perfil, button.dataset.action);
        });
    }

    async function init() {
        if (!$('config-profiles-list')) return;
        bind();
        try {
            await carregarPerfis();
        } catch (error) {
            mostrarAlerta(error.message);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
