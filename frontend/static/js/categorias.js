/**
 * JavaScript para gerenciamento de Categorias
 */

const API_URL = '/api/categorias';
let categoriaEditando = null;
let categoriaAtual = null;

function categoriasIcon(nome) {
    const icons = {
        edit: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 19h4L19 9a2.1 2.1 0 0 0-3-3L6 16l-1 3Z"/><path d="M14 6l4 4"/></svg>',
        remove: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5"/><path d="M14 11v5"/></svg>'
    };
    return icons[nome] || '';
}

document.addEventListener('DOMContentLoaded', () => {
    carregarCategorias();
    montarSeletorIcones();

    const corInput = document.getElementById('cor');
    if (corInput) {
        corInput.addEventListener('input', (e) => {
            const el = document.getElementById('cor-valor');
            if (el) el.textContent = e.target.value;
        });
    }

    const iconeInput = document.getElementById('icone');
    if (iconeInput) {
        iconeInput.addEventListener('input', (e) => {
            atualizarIconeSelecionado(e.target.value.trim());
        });
    }

    const limparIcone = document.getElementById('icone-limpar');
    if (limparIcone) {
        limparIcone.addEventListener('click', () => {
            definirIconeCategoria('');
        });
    }

    const enviarLogo = document.getElementById('logo-enviar');
    if (enviarLogo) {
        enviarLogo.addEventListener('click', enviarLogoCategoria);
    }

    const removerLogo = document.getElementById('logo-remover');
    if (removerLogo) {
        removerLogo.addEventListener('click', removerLogoCategoria);
    }
});

function montarSeletorIcones() {
    const grid = document.getElementById('icone-picker-grid');
    if (!grid || typeof getIconKeys !== 'function' || typeof renderIcon !== 'function') return;

    const keys = getIconKeys();
    grid.innerHTML = keys.map((key) => `
        <button type="button" class="icone-picker-option" data-icon-key="${key}" title="${key}" aria-label="Selecionar icone ${key}">
            <span class="icone-picker-option-icon" aria-hidden="true">${renderIcon(key, { size: '18px' })}</span>
            <span class="icone-picker-option-label">${key}</span>
        </button>
    `).join('');

    grid.querySelectorAll('.icone-picker-option').forEach((button) => {
        button.addEventListener('click', () => {
            definirIconeCategoria(button.dataset.iconKey || '');
        });
    });
}

function definirIconeCategoria(key) {
    const iconeInput = document.getElementById('icone');
    if (iconeInput) {
        iconeInput.value = key || '';
    }
    atualizarIconeSelecionado(key || '');
}

function atualizarIconeSelecionado(key) {
    const chave = (key || '').trim();
    const preview = document.getElementById('icone-preview');
    if (preview) {
        preview.innerHTML = chave && typeof renderIcon === 'function'
            ? renderIcon(chave, { size: '22px' })
            : '';
    }

    document.querySelectorAll('.icone-picker-option').forEach((button) => {
        const ativo = button.dataset.iconKey === chave;
        button.classList.toggle('active', ativo);
        button.setAttribute('aria-pressed', ativo ? 'true' : 'false');
    });

    const limparIcone = document.getElementById('icone-limpar');
    if (limparIcone) {
        limparIcone.classList.toggle('active', !chave);
        limparIcone.setAttribute('aria-pressed', !chave ? 'true' : 'false');
    }
}

function atualizarLogoPanel(categoria) {
    const temCategoria = Boolean(categoria && categoria.id);
    const preview = document.getElementById('logo-preview');
    const input = document.getElementById('logo-upload-input');
    const enviar = document.getElementById('logo-enviar');
    const remover = document.getElementById('logo-remover');
    const status = document.getElementById('logo-upload-status');

    if (preview) {
        preview.innerHTML = categoria?.logo_url
            ? `<img src="${categoria.logo_url}" alt="" loading="lazy" onerror="this.remove()">`
            : '';
    }

    if (input) {
        input.value = '';
        input.disabled = !temCategoria;
    }

    if (enviar) {
        enviar.disabled = !temCategoria;
    }

    if (remover) {
        remover.disabled = !temCategoria || !categoria?.logo_url;
    }

    if (status) {
        if (!temCategoria) {
            status.textContent = 'Salve a categoria antes de enviar logo.';
        } else if (categoria?.logo_url) {
            status.textContent = 'Logo personalizado ativo. Ao remover, o icone do catalogo volta a aparecer.';
        } else {
            status.textContent = 'Nenhum logo personalizado. O icone do catalogo sera usado como fallback.';
        }
    }
}

async function enviarLogoCategoria() {
    if (!categoriaEditando) {
        alert('Salve a categoria antes de enviar logo.');
        return;
    }

    const input = document.getElementById('logo-upload-input');
    const arquivo = input?.files?.[0];
    if (!arquivo) {
        alert('Selecione um arquivo PNG, JPG ou WebP.');
        return;
    }

    const formData = new FormData();
    formData.append('file', arquivo);

    try {
        const response = await fetch(`${API_URL}/${categoriaEditando}/logo`, {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (!data.success) {
            alert('Erro ao enviar logo: ' + data.error);
            return;
        }

        categoriaAtual = data.data;
        atualizarLogoPanel(categoriaAtual);
        carregarCategorias();
    } catch (error) {
        console.error('Erro ao enviar logo:', error);
        alert('Erro ao enviar logo. Por favor, tente novamente.');
    }
}

async function removerLogoCategoria() {
    if (!categoriaEditando) {
        alert('Salve a categoria antes de remover logo.');
        return;
    }

    try {
        const response = await fetch(`${API_URL}/${categoriaEditando}/logo`, {
            method: 'DELETE'
        });
        const data = await response.json();

        if (!data.success) {
            alert('Erro ao remover logo: ' + data.error);
            return;
        }

        categoriaAtual = data.data;
        atualizarLogoPanel(categoriaAtual);
        carregarCategorias();
    } catch (error) {
        console.error('Erro ao remover logo:', error);
        alert('Erro ao remover logo. Por favor, tente novamente.');
    }
}

async function carregarCategorias() {
    const lista = document.getElementById('categorias-lista');
    if (!lista) return;

    try {
        const response = await fetch(API_URL);
        const data = await response.json();

        if (!data.success) {
            lista.innerHTML = `<p class="empty-state">Erro ao carregar categorias: ${data.error}</p>`;
            return;
        }

        const categorias = data.data || [];
        if (categorias.length === 0) {
            lista.innerHTML = `
                <div class="empty-state">
                    <h3>Nenhuma categoria cadastrada</h3>
                    <p>Clique em "Nova Categoria" para comecar</p>
                </div>
            `;
            return;
        }

        const linhas = categorias.map((categoria) => {
            const visualHtml = typeof renderCategoryVisual === 'function'
                ? renderCategoryVisual(categoria, { size: '16px', alt: categoria.nome })
                : '';
            const iconeHtml = visualHtml
                ? `<span class="category-icon" style="color:${categoria.cor}">${visualHtml}</span>`
                : `<span class="categoria-dot" style="background-color: ${categoria.cor}" aria-hidden="true"></span>`;
            return `
            <div class="compact-row categoria-row categorias-compact-row">
                <div class="compact-cell col-descricao">
                    <span class="titulo">
                        ${iconeHtml}
                        <span class="categoria-nome-texto">${categoria.nome}</span>
                    </span>
                </div>
                <div class="compact-cell compact-meta">
                    ${categoria.descricao || '-'}
                </div>
                <div class="compact-cell">
                    <span class="compact-pill status ${categoria.ativo ? 'status-ativo' : 'status-inativo'}">
                        ${categoria.ativo ? 'Ativa' : 'Inativa'}
                    </span>
                </div>
                <div class="compact-cell row-actions acoes">
                    <button class="row-action-button" onclick="editarCategoria(${categoria.id})" title="Editar" aria-label="Editar">${categoriasIcon('edit')}</button>
                    <button class="row-action-button danger" onclick="confirmarDeletar(${categoria.id}, ${JSON.stringify(categoria.nome)})" title="Excluir" aria-label="Excluir">${categoriasIcon('remove')}</button>
                </div>
            </div>
        `;
        }).join('');

        lista.innerHTML = `
            <div class="compact-table categorias-compact-table">
                <div class="compact-table-header categorias-compact-row">
                    <div>Categoria</div>
                    <div>Descricao</div>
                    <div>Status</div>
                    <div class="compact-actions">Acoes</div>
                </div>
                ${linhas}
            </div>
        `;
    } catch (error) {
        console.error('Erro ao carregar categorias:', error);
        lista.innerHTML = '<p class="empty-state">Erro ao carregar categorias. Por favor, tente novamente.</p>';
    }
}

function abrirModal() {
    categoriaEditando = null;
    categoriaAtual = null;
    document.getElementById('modal-titulo').textContent = 'Nova Categoria';
    document.getElementById('form-categoria').reset();
    document.getElementById('categoria-id').value = '';
    document.getElementById('cor').value = '#6c757d';
    document.getElementById('cor-valor').textContent = '#6c757d';
    document.getElementById('ativo').checked = true;
    const iconeEl = document.getElementById('icone');
    if (iconeEl) iconeEl.value = '';
    atualizarIconeSelecionado('');
    atualizarLogoPanel(null);
    document.getElementById('modal-categoria').style.display = 'block';
}

function fecharModal() {
    document.getElementById('modal-categoria').style.display = 'none';
    categoriaEditando = null;
    categoriaAtual = null;
}

async function editarCategoria(id) {
    try {
        const response = await fetch(`${API_URL}/${id}`);
        const data = await response.json();

        if (!data.success) {
            alert('Erro ao carregar categoria: ' + data.error);
            return;
        }

        const categoria = data.data;
        categoriaEditando = id;
        categoriaAtual = categoria;

        document.getElementById('modal-titulo').textContent = 'Editar Categoria';
        document.getElementById('categoria-id').value = categoria.id;
        document.getElementById('nome').value = categoria.nome;
        document.getElementById('descricao').value = categoria.descricao || '';
        document.getElementById('cor').value = categoria.cor;
        document.getElementById('cor-valor').textContent = categoria.cor;
        document.getElementById('ativo').checked = categoria.ativo;
        const iconeEl = document.getElementById('icone');
        if (iconeEl) iconeEl.value = categoria.icone || '';
        atualizarIconeSelecionado(categoria.icone || '');
        atualizarLogoPanel(categoria);

        document.getElementById('modal-categoria').style.display = 'block';
    } catch (error) {
        console.error('Erro ao carregar categoria:', error);
        alert('Erro ao carregar categoria. Por favor, tente novamente.');
    }
}

async function salvarCategoria(event) {
    event.preventDefault();

    const id = document.getElementById('categoria-id').value;
    const iconeEl = document.getElementById('icone');
    const dados = {
        nome: document.getElementById('nome').value.trim(),
        descricao: document.getElementById('descricao').value.trim(),
        cor: document.getElementById('cor').value,
        icone: iconeEl ? (iconeEl.value.trim() || null) : null,
        ativo: document.getElementById('ativo').checked
    };

    try {
        const url = id ? `${API_URL}/${id}` : API_URL;
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const data = await response.json();

        if (!data.success) {
            alert('Erro: ' + data.error);
            return;
        }

        alert(data.message);
        fecharModal();
        carregarCategorias();
    } catch (error) {
        console.error('Erro ao salvar categoria:', error);
        alert('Erro ao salvar categoria. Por favor, tente novamente.');
    }
}

function confirmarDeletar(id, nome) {
    if (confirm(`Tem certeza que deseja deletar a categoria "${nome}"?\n\nEsta acao nao pode ser desfeita.`)) {
        deletarCategoria(id);
    }
}

async function deletarCategoria(id) {
    try {
        const response = await fetch(`${API_URL}/${id}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (!data.success) {
            alert('Erro ao deletar: ' + data.error);
            return;
        }

        alert(data.message);
        carregarCategorias();
    } catch (error) {
        console.error('Erro ao deletar categoria:', error);
        alert('Erro ao deletar categoria. Por favor, tente novamente.');
    }
}

window.onclick = function(event) {
    const modal = document.getElementById('modal-categoria');
    if (event.target === modal) {
        fecharModal();
    }
};
