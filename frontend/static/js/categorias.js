/**
 * JavaScript para gerenciamento de Categorias
 */

const API_URL = '/api/categorias';
let categoriaEditando = null;

// Carregar categorias ao iniciar a página
document.addEventListener('DOMContentLoaded', () => {
    carregarCategorias();

    // Atualizar preview da cor quando mudar
    const corInput = document.getElementById('cor');
    if (corInput) {
        corInput.addEventListener('input', (e) => {
            document.getElementById('cor-valor').textContent = e.target.value;
        });
    }
});

/**
 * Carrega todas as categorias da API
 */
async function carregarCategorias() {
    try {
        const response = await fetch(API_URL);
        const data = await response.json();

        const lista = document.getElementById('categorias-lista');

        if (!data.success) {
            lista.innerHTML = `<p class="empty-state">Erro ao carregar categorias: ${data.error}</p>`;
            return;
        }

        if (data.data.length === 0) {
            lista.innerHTML = `
                <div class="empty-state">
                    <h3>Nenhuma categoria cadastrada</h3>
                    <p>Clique em "Nova Categoria" para começar</p>
                </div>
            `;
            return;
        }

        // Renderizar categorias
        lista.innerHTML = data.data.map(categoria => `
            <div class="categoria-card" style="border-left-color: ${categoria.cor}">
                <div class="categoria-header">
                    <div class="categoria-nome">${categoria.nome}</div>
                    <span class="categoria-status ${categoria.ativo ? 'status-ativo' : 'status-inativo'}">
                        ${categoria.ativo ? 'Ativa' : 'Inativa'}
                    </span>
                </div>

                <div class="categoria-descricao">
                    ${categoria.descricao || '<em>Sem descrição</em>'}
                </div>

                <div style="margin: 10px 0;">
                    <span class="categoria-cor-preview" style="background-color: ${categoria.cor}"></span>
                    <span style="color: #666; font-size: 0.9em;">${categoria.cor}</span>
                </div>

                <div class="categoria-actions">
                    <button class="btn btn-edit" onclick="editarCategoria(${categoria.id})">
                        Editar
                    </button>
                    <button class="btn btn-danger" onclick="confirmarDeletar(${categoria.id}, '${categoria.nome}')">
                        Deletar
                    </button>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Erro ao carregar categorias:', error);
        document.getElementById('categorias-lista').innerHTML =
            `<p class="empty-state">Erro ao carregar categorias. Por favor, tente novamente.</p>`;
    }
}

/**
 * Abre o modal para criar nova categoria
 */
function abrirModal() {
    categoriaEditando = null;
    document.getElementById('modal-titulo').textContent = 'Nova Categoria';
    document.getElementById('form-categoria').reset();
    document.getElementById('categoria-id').value = '';
    document.getElementById('cor').value = '#6c757d';
    document.getElementById('cor-valor').textContent = '#6c757d';
    document.getElementById('ativo').checked = true;
    document.getElementById('modal-categoria').style.display = 'block';
}

/**
 * Fecha o modal
 */
function fecharModal() {
    document.getElementById('modal-categoria').style.display = 'none';
    categoriaEditando = null;
}

/**
 * Edita uma categoria existente
 */
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

        // Preencher formulário
        document.getElementById('modal-titulo').textContent = 'Editar Categoria';
        document.getElementById('categoria-id').value = categoria.id;
        document.getElementById('nome').value = categoria.nome;
        document.getElementById('descricao').value = categoria.descricao || '';
        document.getElementById('cor').value = categoria.cor;
        document.getElementById('cor-valor').textContent = categoria.cor;
        document.getElementById('ativo').checked = categoria.ativo;

        // Abrir modal
        document.getElementById('modal-categoria').style.display = 'block';

    } catch (error) {
        console.error('Erro ao carregar categoria:', error);
        alert('Erro ao carregar categoria. Por favor, tente novamente.');
    }
}

/**
 * Salva categoria (criar ou atualizar)
 */
async function salvarCategoria(event) {
    event.preventDefault();

    const id = document.getElementById('categoria-id').value;
    const dados = {
        nome: document.getElementById('nome').value.trim(),
        descricao: document.getElementById('descricao').value.trim(),
        cor: document.getElementById('cor').value,
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

/**
 * Confirma antes de deletar categoria
 */
function confirmarDeletar(id, nome) {
    if (confirm(`Tem certeza que deseja deletar a categoria "${nome}"?\n\nEsta ação não pode ser desfeita.`)) {
        deletarCategoria(id);
    }
}

/**
 * Deleta uma categoria
 */
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

// Fechar modal ao clicar fora dele
window.onclick = function(event) {
    const modal = document.getElementById('modal-categoria');
    if (event.target === modal) {
        fecharModal();
    }
}
