(function () {
    'use strict';

    const API_BASE = '/api/perfis-financeiros';

    function qs(selector) {
        return document.querySelector(selector);
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[char]));
    }

    function tipoLabel(tipo) {
        const value = String(tipo || '').toUpperCase();
        if (value === 'PESSOAL') return 'Pessoal';
        if (value === 'EMPRESA') return 'Empresa';
        return 'Perfil financeiro';
    }

    function iniciais(perfil) {
        if (perfil?.avatar) return String(perfil.avatar).slice(0, 3).toUpperCase();
        const partes = String(perfil?.nome || 'PF').trim().split(/\s+/).filter(Boolean);
        if (!partes.length) return 'PF';
        if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
        return `${partes[0][0]}${partes[1][0]}`.toUpperCase();
    }

    function setAberto(aberto) {
        const switcher = qs('#perfil-financeiro-switcher');
        const trigger = qs('#perfil-financeiro-trigger');
        if (!switcher || !trigger) return;
        switcher.classList.toggle('open', aberto);
        trigger.setAttribute('aria-expanded', aberto ? 'true' : 'false');
    }

    function renderPerfilAtivo(perfil) {
        if (!perfil) return;
        const name = qs('#perfil-financeiro-name');
        const type = qs('#perfil-financeiro-type');
        const avatar = qs('#perfil-financeiro-avatar');
        const switcher = qs('#perfil-financeiro-switcher');

        if (name) name.textContent = perfil.nome || 'Perfil';
        if (type) type.textContent = tipoLabel(perfil.tipo);
        if (avatar) {
            avatar.textContent = iniciais(perfil);
            avatar.style.setProperty('--perfil-color', perfil.cor || '#2563eb');
        }
        if (switcher) {
            switcher.dataset.perfilAtivoId = perfil.id || '';
            switcher.dataset.loading = 'false';
        }
    }

    function renderOpcoes(perfis, perfilAtivo) {
        const container = qs('#perfil-financeiro-options');
        if (!container) return;

        container.innerHTML = (perfis || []).map((perfil) => {
            const ativo = Number(perfil.id) === Number(perfilAtivo?.id);
            return `
                <button class="perfil-financeiro-option${ativo ? ' active' : ''}" type="button" data-perfil-id="${escapeHtml(perfil.id)}" role="menuitem">
                    <span class="perfil-financeiro-option-avatar" style="--perfil-color:${escapeHtml(perfil.cor || '#2563eb')}">${escapeHtml(iniciais(perfil))}</span>
                    <span class="perfil-financeiro-option-text">
                        <strong>${escapeHtml(perfil.nome || 'Perfil')}</strong>
                        <small>${escapeHtml(tipoLabel(perfil.tipo))}${ativo ? ' atual' : ''}</small>
                    </span>
                    ${ativo ? '<span class="perfil-financeiro-option-check" aria-hidden="true">✓</span>' : ''}
                </button>
            `.trim();
        }).join('');
    }

    async function carregarPerfis() {
        const response = await fetch(API_BASE, {
            headers: { 'Accept': 'application/json' }
        });
        if (!response.ok) throw new Error('Falha ao carregar perfis financeiros');
        return response.json();
    }

    async function trocarPerfil(perfilId) {
        const response = await fetch(`${API_BASE}/ativo`, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ perfil_id: perfilId })
        });
        if (!response.ok) throw new Error('Falha ao trocar perfil financeiro');
        return response.json();
    }

    function bindEventos() {
        const trigger = qs('#perfil-financeiro-trigger');
        const options = qs('#perfil-financeiro-options');

        if (trigger) {
            trigger.addEventListener('click', (event) => {
                event.stopPropagation();
                const switcher = qs('#perfil-financeiro-switcher');
                setAberto(!switcher?.classList.contains('open'));
            });
        }

        if (options) {
            options.addEventListener('click', async (event) => {
                const option = event.target.closest('.perfil-financeiro-option');
                if (!option) return;

                const perfilId = option.dataset.perfilId;
                const switcher = qs('#perfil-financeiro-switcher');
                if (String(switcher?.dataset.perfilAtivoId || '') === String(perfilId || '')) {
                    setAberto(false);
                    return;
                }

                option.disabled = true;
                try {
                    await trocarPerfil(perfilId);
                    window.location.reload();
                } catch (error) {
                    option.disabled = false;
                    console.error(error);
                }
            });
        }

        document.addEventListener('click', () => setAberto(false));
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') setAberto(false);
        });
    }

    async function init() {
        const switcher = qs('#perfil-financeiro-switcher');
        if (!switcher) return;

        bindEventos();

        try {
            const data = await carregarPerfis();
            renderPerfilAtivo(data.perfil_ativo);
            renderOpcoes(data.perfis || [], data.perfil_ativo);
        } catch (error) {
            switcher.dataset.loading = 'error';
            console.error(error);
        }
    }

    window.ContextoFinanceiroUI = {
        carregarPerfis,
        trocarPerfil,
        init
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
