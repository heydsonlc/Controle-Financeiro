/**
 * JavaScript para o módulo de Contas Bancárias
 */

const API_BASE = 'http://localhost:5000/api/contas';

let contaAtual = null;
let contaParaInativar = null;

// Carregar contas ao iniciar a página
document.addEventListener('DOMContentLoaded', () => {
    carregarContas();
});

/**
 * Carrega todas as contas bancárias
 */
async function carregarContas() {
    try {
        const status = document.getElementById('filtro-status').value;
        const url = status ? `${API_BASE}?status=${status}` : `${API_BASE}?status=ATIVO`;

        const response = await fetch(url);
        const result = await response.json();

        if (result.success) {
            exibirContas(result.data);
            atualizarResumo(result.data);
        } else {
            mostrarErro('Erro ao carregar contas: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao carregar contas:', error);
        mostrarErro('Erro ao conectar com o servidor');
    }
}

/**
 * Exibe as contas na grade
 */
function exibirContas(contas) {
    const lista = document.getElementById('contas-lista');

    if (!contas || contas.length === 0) {
        lista.innerHTML = '<p class="empty-state">Nenhuma conta encontrada. Cadastre sua primeira conta!</p>';
        return;
    }

    lista.innerHTML = contas.map(conta => criarCardConta(conta)).join('');
}

/**
 * Cria o HTML de um card de conta
 */
function criarCardConta(conta) {
    const saldoClass = conta.saldo_atual < 0 ? 'negativo' : '';
    const statusClass = conta.status === 'INATIVO' ? 'inativo' : '';
    const statusText = conta.status === 'INATIVO' ? 'INATIVA' : 'ATIVA';

    return `
        <div class="conta-card" style="--cor-conta: ${conta.cor_display}">
            <div class="conta-header">
                <div class="conta-info">
                    <h3>${conta.nome}</h3>
                    <div class="instituicao">${conta.instituicao}</div>
                    <div class="tipo">${conta.tipo}</div>
                </div>
                <span class="conta-badge ${statusClass}">${statusText}</span>
            </div>

            ${conta.agencia || conta.numero_conta ? `
                <div class="conta-dados">
                    ${conta.agencia ? `
                        <div class="dado">
                            <span class="dado-label">Agência</span>
                            <span class="dado-valor">${conta.agencia}</span>
                        </div>
                    ` : ''}
                    ${conta.numero_conta ? `
                        <div class="dado">
                            <span class="dado-label">Conta</span>
                            <span class="dado-valor">${conta.numero_conta}${conta.digito_conta ? '-' + conta.digito_conta : ''}</span>
                        </div>
                    ` : ''}
                </div>
            ` : ''}

            <div class="conta-saldo">
                <div class="conta-saldo-label">Saldo Atual</div>
                <div class="conta-saldo-valor ${saldoClass}">
                    ${formatarMoedaDisplay(conta.saldo_atual)}
                </div>
            </div>

            <div class="conta-actions">
                <button class="btn-editar" onclick="editarConta(${conta.id})">
                    ✏️ Editar
                </button>
                ${conta.status === 'ATIVO' ? `
                    <button class="btn-inativar" onclick="abrirModalInativar(${conta.id})">
                        🚫 Inativar
                    </button>
                ` : `
                    <button class="btn-ativar" onclick="ativarConta(${conta.id})">
                        ✓ Ativar
                    </button>
                `}
            </div>
        </div>
    `;
}

/**
 * Atualiza os cards de resumo
 */
function atualizarResumo(contas) {
    const contasAtivas = contas.filter(c => c.status === 'ATIVO');
    const totalSaldo = contasAtivas.reduce((sum, c) => sum + c.saldo_atual, 0);
    const maiorSaldo = contasAtivas.length > 0 ?
        Math.max(...contasAtivas.map(c => c.saldo_atual)) : 0;

    document.getElementById('total-saldo').textContent = formatarMoedaDisplay(totalSaldo);
    document.getElementById('total-contas').textContent = contasAtivas.length;
    document.getElementById('maior-saldo').textContent = formatarMoedaDisplay(maiorSaldo);
}

/**
 * Abre modal para nova conta
 */
function abrirModalNovaConta() {
    contaAtual = null;
    document.getElementById('modal-titulo').textContent = 'Nova Conta Bancária';
    document.getElementById('btn-deletar-modal').style.display = 'none';
    document.getElementById('form-conta').reset();
    document.getElementById('conta-id').value = '';
    document.getElementById('conta-cor').value = '#3b82f6';
    abrirModal('modal-conta');
}

/**
 * Edita uma conta existente
 */
async function editarConta(id) {
    try {
        const response = await fetch(`${API_BASE}/${id}`);
        const result = await response.json();

        if (result.success) {
            contaAtual = result.data;
            preencherFormulario(result.data);
            document.getElementById('modal-titulo').textContent = 'Editar Conta Bancária';
            document.getElementById('btn-deletar-modal').style.display = 'block';
            abrirModal('modal-conta');
        } else {
            mostrarErro('Erro ao carregar conta: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao carregar conta:', error);
        mostrarErro('Erro ao conectar com o servidor');
    }
}

/**
 * Preenche o formulário com os dados da conta
 */
function preencherFormulario(conta) {
    document.getElementById('conta-id').value = conta.id;
    document.getElementById('conta-nome').value = conta.nome;
    document.getElementById('conta-instituicao').value = conta.instituicao;
    document.getElementById('conta-tipo').value = conta.tipo;
    document.getElementById('conta-agencia').value = conta.agencia || '';
    document.getElementById('conta-numero').value = conta.numero_conta || '';
    document.getElementById('conta-digito').value = conta.digito_conta || '';
    document.getElementById('conta-saldo-inicial').value = formatarMoedaDisplay(conta.saldo_inicial);
    document.getElementById('conta-cor').value = conta.cor_display || '#3b82f6';
}

/**
 * Salva a conta (criar ou atualizar)
 */
async function salvarConta(event) {
    event.preventDefault();

    const id = document.getElementById('conta-id').value;
    const dados = {
        nome: document.getElementById('conta-nome').value,
        instituicao: document.getElementById('conta-instituicao').value,
        tipo: document.getElementById('conta-tipo').value,
        agencia: document.getElementById('conta-agencia').value || null,
        numero_conta: document.getElementById('conta-numero').value || null,
        digito_conta: document.getElementById('conta-digito').value || null,
        saldo_inicial: parseMoeda(document.getElementById('conta-saldo-inicial').value),
        cor_display: document.getElementById('conta-cor').value
    };

    try {
        const url = id ? `${API_BASE}/${id}` : API_BASE;
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dados)
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso(result.message);
            fecharModal('modal-conta');
            carregarContas();
        } else {
            mostrarErro('Erro ao salvar conta: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao salvar conta:', error);
        mostrarErro('Erro ao conectar com o servidor');
    }
}

/**
 * Abre modal de confirmação para inativar
 */
function abrirModalInativar(id) {
    contaParaInativar = id;
    abrirModal('modal-confirmar');
}

/**
 * Inativar conta via modal de edição
 */
function inativarContaModal() {
    const id = document.getElementById('conta-id').value;
    if (id) {
        abrirModalInativar(id);
        fecharModal('modal-conta');
    }
}

/**
 * Confirma a inativação da conta
 */
async function confirmarInativacao() {
    if (!contaParaInativar) return;

    try {
        const response = await fetch(`${API_BASE}/${contaParaInativar}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso('Conta inativada com sucesso');
            fecharModal('modal-confirmar');
            contaParaInativar = null;
            carregarContas();
        } else {
            mostrarErro('Erro ao inativar conta: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao inativar conta:', error);
        mostrarErro('Erro ao conectar com o servidor');
    }
}

/**
 * Ativar uma conta inativa
 */
async function ativarConta(id) {
    try {
        const response = await fetch(`${API_BASE}/${id}/ativar`, {
            method: 'PUT'
        });

        const result = await response.json();

        if (result.success) {
            mostrarSucesso('Conta reativada com sucesso');
            carregarContas();
        } else {
            mostrarErro('Erro ao ativar conta: ' + result.error);
        }
    } catch (error) {
        console.error('Erro ao ativar conta:', error);
        mostrarErro('Erro ao conectar com o servidor');
    }
}

/**
 * Abre um modal
 */
function abrirModal(modalId) {
    document.getElementById(modalId).style.display = 'block';
}

/**
 * Fecha um modal
 */
function fecharModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

/**
 * Formata valor monetário para exibição
 */
function formatarMoedaDisplay(valor) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(valor);
}

/**
 * Formata input de moeda
 */
function formatarMoeda(input) {
    let valor = input.value.replace(/\D/g, '');
    valor = (parseInt(valor) / 100).toFixed(2);
    input.value = 'R$ ' + valor.replace('.', ',').replace(/(\d)(?=(\d{3})+\,)/g, '$1.');
}

/**
 * Converte string de moeda para número
 */
function parseMoeda(valor) {
    if (!valor) return 0;
    return parseFloat(valor.replace('R$', '').replace(/\./g, '').replace(',', '.').trim());
}

/**
 * Mostra mensagem de sucesso
 */
function mostrarSucesso(mensagem) {
    alert(mensagem);
}

/**
 * Mostra mensagem de erro
 */
function mostrarErro(mensagem) {
    alert(mensagem);
}

// Fechar modal ao clicar fora
window.onclick = function (event) {
    const modals = document.getElementsByClassName('modal');
    for (let modal of modals) {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    }
}
