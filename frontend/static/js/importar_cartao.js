/**
 * Importação Assistida de Fatura de Cartão (CSV)
 * FASE 6.2
 */

const API_BASE = '/api/importacao-cartao';

// Estado global da importação
const estado = {
    cartoes: [],
    categorias: [],
    categoriasCartao: [],
    csvData: null,
    linhasMapeadas: []
};

// ============================================================================
// INICIALIZAÇÃO
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
    await carregarCartoes();
    configurarUpload();
    configurarMascaraCompetencia();
});

// Máscara para MM/AAAA
function configurarMascaraCompetencia() {
    const input = document.getElementById('competenciaInput');

    input.addEventListener('input', (e) => {
        let valor = e.target.value.replace(/\D/g, ''); // Remove não-dígitos

        if (valor.length >= 2) {
            valor = valor.substring(0, 2) + '/' + valor.substring(2, 6);
        }

        e.target.value = valor;
    });
}

async function carregarCartoes() {
    try {
        const response = await fetch('/api/cartoes');
        const cartoes = await response.json();

        if (Array.isArray(cartoes)) {
            estado.cartoes = cartoes;
            const select = document.getElementById('cartaoSelect');
            select.innerHTML = '<option value="">Selecione um cartão</option>';

            cartoes.forEach(cartao => {
                const option = document.createElement('option');
                option.value = cartao.id;
                option.textContent = cartao.nome;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Erro ao carregar cartões:', error);
        alert('Erro ao carregar cartões. Verifique o console.');
    }
}

async function carregarCategorias() {
    try {
        const response = await fetch(`${API_BASE}/categorias`);
        const data = await response.json();

        if (data.success) {
            estado.categorias = data.categorias;
        }

        // Carregar categorias do cartão
        const cartaoId = document.getElementById('cartaoSelect').value;
        if (cartaoId) {
            const respCartao = await fetch(`${API_BASE}/categorias-cartao/${cartaoId}`);
            const dataCartao = await respCartao.json();

            if (dataCartao.success) {
                estado.categoriasCartao = dataCartao.categorias_cartao;
            }
        }
    } catch (error) {
        console.error('Erro ao carregar categorias:', error);
    }
}

// ============================================================================
// NAVEGAÇÃO ENTRE ETAPAS
// ============================================================================

async function proximaEtapa(numero) {
    // Validações por etapa
    if (numero === 2) {
        const cartaoId = document.getElementById('cartaoSelect').value;
        const competencia = document.getElementById('competenciaInput').value;

        if (!cartaoId || !competencia) {
            alert('Selecione o cartão e a competência');
            return;
        }

        // Validar formato MM/AAAA
        if (!/^\d{2}\/\d{4}$/.test(competencia)) {
            alert('Formato de competência inválido. Use MM/AAAA (ex: 12/2025)');
            return;
        }
    }

    if (numero === 3 && !estado.csvData) {
        alert('Faça upload do arquivo CSV primeiro');
        return;
    }

    if (numero === 4 && estado.linhasMapeadas.length === 0) {
        alert('Mapeie as colunas antes de continuar');
        return;
    }

    // Esconder todas as etapas
    document.querySelectorAll('.step').forEach(step => step.classList.remove('active'));

    // Mostrar etapa solicitada
    document.getElementById(`step${numero}`).classList.add('active');

    // Executar ações específicas da etapa
    if (numero === 3) {
        renderizarMapeamento();
    } else if (numero === 4) {
        await renderizarPrevia();
    }
}

function voltarEtapa(numero) {
    proximaEtapa(numero);
}

// ============================================================================
// UPLOAD CSV
// ============================================================================

function configurarUpload() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('csvFile');

    uploadArea.addEventListener('click', () => fileInput.click());

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('drag-over');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('drag-over');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');

        const file = e.dataTransfer.files[0];
        if (file) {
            processarCSV(file);
        }
    });

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            processarCSV(file);
        }
    });
}

async function processarCSV(file) {
    const formData = new FormData();
    formData.append('arquivo', file);

    try {
        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            estado.csvData = data;

            document.getElementById('uploadResult').innerHTML = `
                <div class="result-message success">
                    CSV carregado com sucesso!<br>
                    <strong>${data.total_linhas}</strong> linhas detectadas<br>
                    Delimitador: <strong>${data.delimitador}</strong>
                </div>
            `;

            document.getElementById('btnStep3').disabled = false;
        } else {
            throw new Error(data.message);
        }
    } catch (error) {
        document.getElementById('uploadResult').innerHTML = `
            <div class="result-message error">
                Erro ao processar CSV: ${error.message}
            </div>
        `;
    }
}

// ============================================================================
// MAPEAMENTO
// ============================================================================

function renderizarMapeamento() {
    const container = document.getElementById('mapeamentoContainer');

    const camposObrigatorios = [
        { id: 'data_compra', nome: 'Data da Compra' },
        { id: 'descricao', nome: 'Descrição' },
        { id: 'valor', nome: 'Valor' }
    ];

    const camposOpcionais = [
        { id: 'parcela', nome: 'Parcela (ex: 1/12)' }
    ];

    let html = '<div style="display:grid; grid-template-columns: 1fr 1fr; gap: 20px;">';

    [...camposObrigatorios, ...camposOpcionais].forEach(campo => {
        html += `
            <div class="form-group">
                <label>${campo.nome} ${camposObrigatorios.includes(campo) ? '<span style="color:red">*</span>' : ''}</label>
                <select id="map_${campo.id}">
                    <option value="">-- Não mapear --</option>
                    ${estado.csvData.colunas.map((col, idx) =>
                        `<option value="${idx}">${col}</option>`
                    ).join('')}
                </select>
            </div>
        `;
    });

    html += '</div>';
    html += '<button class="btn btn-primary" onclick="validarMapeamento()" style="margin-top:20px">Validar Mapeamento</button>';

    container.innerHTML = html;
}

function validarMapeamento() {
    const mapa = {
        data_compra: document.getElementById('map_data_compra').value,
        descricao: document.getElementById('map_descricao').value,
        valor: document.getElementById('map_valor').value,
        parcela: document.getElementById('map_parcela').value
    };

    if (!mapa.data_compra || !mapa.descricao || !mapa.valor) {
        alert('Preencha todos os campos obrigatórios');
        return;
    }

    // Processar linhas
    estado.linhasMapeadas = estado.csvData.linhas_amostra.map(linha => {
        return {
            data_compra: linha[parseInt(mapa.data_compra)],
            descricao: linha[parseInt(mapa.descricao)],
            valor: linha[parseInt(mapa.valor)],
            parcela: mapa.parcela ? linha[parseInt(mapa.parcela)] : '1/1',
            categoria_id: null,  // Será preenchido na etapa 4
            item_agregado_id: null,  // Opcional
            descricao_exibida: linha[parseInt(mapa.descricao)]  // Editável
        };
    });

    alert(`Mapeamento validado! ${estado.linhasMapeadas.length} linhas processadas.`);
    document.getElementById('btnStep4').disabled = false;
}

// ============================================================================
// PRÉVIA E CLASSIFICAÇÃO
// ============================================================================

async function renderizarPrevia() {
    await carregarCategorias();

    const container = document.getElementById('previaContainer');

    let html = '<table><thead><tr>';
    html += '<th>Data</th><th>Descrição</th><th>Valor</th><th>Categoria *</th><th>Cat. Cartão</th>';
    html += '</tr></thead><tbody>';

    estado.linhasMapeadas.forEach((linha, idx) => {
        html += `<tr>
            <td>${linha.data_compra}</td>
            <td><input type="text" value="${linha.descricao_exibida}" onchange="estado.linhasMapeadas[${idx}].descricao_exibida = this.value" style="width:100%; padding:4px"></td>
            <td>${linha.valor}</td>
            <td>
                <select onchange="estado.linhasMapeadas[${idx}].categoria_id = parseInt(this.value)" required>
                    <option value="">Selecione</option>
                    ${estado.categorias.map(cat => `<option value="${cat.id}">${cat.nome}</option>`).join('')}
                </select>
            </td>
            <td>
                <select onchange="estado.linhasMapeadas[${idx}].item_agregado_id = this.value ? parseInt(this.value) : null">
                    <option value="">Nenhuma</option>
                    ${estado.categoriasCartao.map(cat => `<option value="${cat.id}">${cat.nome}</option>`).join('')}
                </select>
            </td>
        </tr>`;
    });

    html += '</tbody></table>';

    container.innerHTML = html;
}

// ============================================================================
// FINALIZAÇÃO
// ============================================================================

async function finalizarImportacao() {
    // Validar categorias
    const faltaCategoria = estado.linhasMapeadas.some(l => !l.categoria_id);
    if (faltaCategoria) {
        alert('Todas as linhas devem ter uma categoria selecionada');
        return;
    }

    const cartaoId = parseInt(document.getElementById('cartaoSelect').value);
    const competenciaInput = document.getElementById('competenciaInput').value; // MM/AAAA

    // Converter MM/AAAA para AAAA-MM-01
    const [mes, ano] = competenciaInput.split('/');
    const competencia = `${ano}-${mes}-01`;

    const payload = {
        cartao_id: cartaoId,
        competencia: competencia,
        linhas: estado.linhasMapeadas
    };

    console.log('Payload de importação:', payload); // Debug

    try {
        const response = await fetch(`${API_BASE}/processar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.success) {
            document.getElementById('resultadoContainer').innerHTML = `
                <div class="result-message success">
                    <h3>Importação Concluída!</h3>
                    <p>Lançamentos inseridos: <strong>${data.inseridos}</strong></p>
                    <p>Duplicados ignorados: <strong>${data.duplicados}</strong></p>
                    ${data.erros.length > 0 ? `<p>Erros: <strong>${data.erros.length}</strong></p>` : ''}
                </div>
            `;
            proximaEtapa(5);
        } else {
            throw new Error(data.message);
        }
    } catch (error) {
        alert(`Erro na importação: ${error.message}`);
    }
}
