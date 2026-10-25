// FIN-FIDELIDADE-DESPESAS-1: script inline de frontend/templates/despesas.html, sem alteracao (a CSP nao aceita
// script inline). Carregado depois de js/original/despesas.js, como no template.
function toggleMobileView() {
    document.body.classList.toggle('mobile-view');
    const btn = document.getElementById('mobile-btn');
    if (document.body.classList.contains('mobile-view')) {
        btn.innerHTML = 'Ver em Desktop';
    } else {
        btn.innerHTML = 'Ver em Mobile';
    }
}

// Mostrar/esconder campo de tipo de recorrência
document.getElementById('recorrente').addEventListener('change', function() {
    const tipoGroup = document.getElementById('tipo-recorrencia-group');
    const meioPagamentoGroup = document.getElementById('meio-pagamento-group');

    tipoGroup.style.display = this.checked ? 'block' : 'none';
    meioPagamentoGroup.style.display = this.checked ? 'block' : 'none';

    // Se desmarcar, esconder campos semanais e cartão também
    if (!this.checked) {
        document.getElementById('campos-semanal').style.display = 'none';
        document.getElementById('campos-cartao').style.display = 'none';
        document.getElementById('meio_pagamento').value = '';
    } else {
        // Se marcar, verificar se é semanal
        alternarCamposSemanal();
    }
});

// Mostrar/esconder campos específicos de recorrência semanal
function alternarCamposSemanal() {
    const tipoRecorrencia = document.getElementById('tipo_recorrencia').value;
    const camposSemanal = document.getElementById('campos-semanal');

    if (tipoRecorrencia === 'semanal') {
        camposSemanal.style.display = 'block';
    } else {
        camposSemanal.style.display = 'none';
    }
}

// Mostrar/esconder campos de cartão
function alternarCamposCartao() {
    console.log('DEBUG HTML: alternarCamposCartao() foi chamada');
    const meioPagamento = document.getElementById('meio_pagamento').value;
    console.log('DEBUG HTML: meio_pagamento =', meioPagamento);
    const camposCartao = document.getElementById('campos-cartao');

    if (meioPagamento === 'cartao') {
        console.log('DEBUG HTML: Mostrando campos de cartão e chamando carregarCartoes()');
        camposCartao.style.display = 'block';

        if (typeof carregarCartoes === 'function') {
            carregarCartoes();
        } else {
            console.error('DEBUG HTML: Função carregarCartoes() NÃO está definida!');
        }
    } else {
        camposCartao.style.display = 'none';
        document.getElementById('cartao_id').value = '';
        document.getElementById('categoria_cartao_id').value = '';
    }
}

function abrirAtalhoDespesaPorHash() {
    const hashActions = {
        '#nova-despesa': 'abrirModal'
    };
    const actionName = hashActions[window.location.hash];

    if (actionName) {
        // Aguardar um pouco para garantir que o DOM esta completamente carregado
        setTimeout(function() {
            if (typeof window[actionName] === 'function') {
                window[actionName]();
                // Limpar o hash da URL
                history.replaceState(null, null, ' ');
            }
        }, 300);
    }
}

// Abrir modal automaticamente se a URL contem atalhos conhecidos
window.addEventListener('load', abrirAtalhoDespesaPorHash);
window.addEventListener('hashchange', abrirAtalhoDespesaPorHash);
