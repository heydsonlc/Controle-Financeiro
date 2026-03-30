/**
 * JavaScript para gerenciamento de Categorias
 */

const API_URL = '/api/categorias';
let categoriaEditando = null;

document.addEventListener('DOMContentLoaded', () => {
    carregarCategorias();

    const corInput = document.getElementById('cor');
    if (corInput) {
        corInput.addEventListener('input', (e) => {
            const el = document.getElementById('cor-valor');
            if (el) el.textContent = e.target.value;
        });
    }
});

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
                    <p>Clique em "Nova Categoria" para começar</p>
                </div>
            `;
            return;
        }

        lista.innerHTML = categorias.map((categoria) => `
            <div class="categoria-row">
                <div class="col-descricao">
                    <div class="titulo">
                        <span class="categoria-dot" style="background-color: ${categoria.cor}" aria-hidden="true"></span>
                        <span class="categoria-nome-texto">${categoria.nome}</span>
                    </div>
                    ${categoria.descricao ? `<div class="subtitulo">${categoria.descricao}</div>` : ''}
                </div>

                <div class="col-fill"></div>

                <div class="col-direita">
                    <span class="status ${categoria.ativo ? 'status-ativo' : 'status-inativo'}">
                        ${categoria.ativo ? 'Ativa' : 'Inativa'}
                    </span>

                    <div class="acoes">
                        <button class="btn-icon" onclick="editarCategoria(${categoria.id})" title="Editar">✏️</button>
                        <button class="btn-icon btn-danger" onclick="confirmarDeletar(${categoria.id}, ${JSON.stringify(categoria.nome)})" title="Excluir">❌</button>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Erro ao carregar categorias:', error);
        lista.innerHTML = '<p class="empty-state">Erro ao carregar categorias. Por favor, tente novamente.</p>';
    }
}

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

function fecharModal() {
    document.getElementById('modal-categoria').style.display = 'none';
    categoriaEditando = null;
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

        document.getElementById('modal-titulo').textContent = 'Editar Categoria';
        document.getElementById('categoria-id').value = categoria.id;
        document.getElementById('nome').value = categoria.nome;
        document.getElementById('descricao').value = categoria.descricao || '';
        document.getElementById('cor').value = categoria.cor;
        document.getElementById('cor-valor').textContent = categoria.cor;
        document.getElementById('ativo').checked = categoria.ativo;

        document.getElementById('modal-categoria').style.display = 'block';
    } catch (error) {
        console.error('Erro ao carregar categoria:', error);
        alert('Erro ao carregar categoria. Por favor, tente novamente.');
    }
}

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

function confirmarDeletar(id, nome) {
    if (confirm(`Tem certeza que deseja deletar a categoria "${nome}"?\n\nEsta ação não pode ser desfeita.`)) {
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

