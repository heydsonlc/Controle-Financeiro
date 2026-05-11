function alertaIndexador(mensagem, tipo = 'success') {
    if (typeof mostrarAlerta === 'function') {
        mostrarAlerta(mensagem, tipo);
        return;
    }
    window.alert(mensagem);
}

function formatarTrPercentual(valor) {
    return Number(valor || 0).toLocaleString('pt-BR', {
        minimumFractionDigits: 4,
        maximumFractionDigits: 4
    });
}

function formatarTrDecimal(valor) {
    return Number(valor || 0).toLocaleString('pt-BR', {
        minimumFractionDigits: 8,
        maximumFractionDigits: 8
    });
}

async function carregarTrOficial() {
    const tbody = document.getElementById('tabelaTrOficial');
    if (!tbody) return;

    const ano = document.getElementById('trFiltroAno')?.value;
    const url = ano ? `/api/indexadores/tr?ano=${encodeURIComponent(ano)}` : '/api/indexadores/tr';

    try {
        const response = await fetch(url);
        const resultado = await response.json();

        if (!response.ok || !resultado.success) {
            throw new Error(resultado.error || 'Erro ao carregar TR oficial');
        }

        if (!resultado.items.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;">Nenhuma TR cadastrada</td></tr>';
            return;
        }

        tbody.innerHTML = resultado.items.map(item => `
            <tr>
                <td>${item.competencia}</td>
                <td>${formatarTrPercentual(item.valor_percentual)}%</td>
                <td>${formatarTrDecimal(item.valor_decimal)}</td>
                <td>${item.fonte || 'BACEN'}</td>
                <td>${item.usada_em_financiamento ? 'Sim' : 'Não'}</td>
                <td>
                    <button class="btn btn-secondary" type="button" onclick="editarTrOficial('${item.competencia}', ${Number(item.valor_percentual || 0)})">
                        Editar
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        alertaIndexador('Erro ao carregar TR oficial: ' + error.message, 'error');
    }
}

async function salvarTrOficial(event) {
    event.preventDefault();

    const dados = {
        competencia: document.getElementById('trCompetencia')?.value,
        valor_percentual: document.getElementById('trValorPercentual')?.value,
        fonte: document.getElementById('trFonte')?.value || 'BACEN'
    };

    try {
        const response = await fetch('/api/indexadores/tr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const resultado = await response.json();

        if (!response.ok || !resultado.success) {
            throw new Error(resultado.error || 'Erro ao salvar TR');
        }

        alertaIndexador(resultado.message || 'TR cadastrada com sucesso.', 'success');
        document.getElementById('trValorPercentual').value = '';
        await carregarTrOficial();
    } catch (error) {
        alertaIndexador(error.message, 'error');
    }
}

async function editarTrOficial(competencia, valorAtual) {
    const novoValor = window.prompt(`Nova TR (%) para ${competencia}`, String(valorAtual).replace('.', ','));
    if (novoValor === null) return;

    try {
        const response = await fetch(`/api/indexadores/tr/${competencia}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                valor_percentual: novoValor,
                fonte: document.getElementById('trFonte')?.value || 'BACEN'
            })
        });
        const resultado = await response.json();

        if (!response.ok || !resultado.success) {
            throw new Error(resultado.error || 'Erro ao atualizar TR');
        }

        alertaIndexador(resultado.message || 'TR atualizada com sucesso.', 'success');
        await carregarTrOficial();
    } catch (error) {
        alertaIndexador(error.message, 'error');
    }
}

async function importarTrOficial() {
    const dados = {
        texto: document.getElementById('trImportTexto')?.value,
        fonte: document.getElementById('trImportFonte')?.value || 'BACEN',
        sobrescrever: document.getElementById('trImportSobrescrever')?.checked === true
    };

    try {
        const response = await fetch('/api/indexadores/tr/importar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
        });
        const resultado = await response.json();

        if (!response.ok || !resultado.success) {
            throw new Error(resultado.error || 'Erro ao importar TR');
        }

        const resumo = `Importação concluída: ${resultado.criados} criadas, ${resultado.atualizados} atualizadas, ${resultado.ignorados} ignoradas.`;
        if (resultado.erros && resultado.erros.length) {
            alertaIndexador(`${resumo} ${resultado.erros.length} linha(s) com erro.`, 'error');
        } else {
            alertaIndexador(resumo, 'success');
        }
        await carregarTrOficial();
    } catch (error) {
        alertaIndexador(error.message, 'error');
    }
}

async function verificarTrFaltante() {
    const inicio = document.getElementById('trFaltanteInicio')?.value;
    const fim = document.getElementById('trFaltanteFim')?.value;
    const destino = document.getElementById('trFaltantesResultado');
    if (!destino) return;

    if (!inicio || !fim) {
        destino.textContent = 'Informe início e fim.';
        return;
    }

    try {
        const response = await fetch(`/api/indexadores/tr/faltantes?inicio=${encodeURIComponent(inicio)}&fim=${encodeURIComponent(fim)}`);
        const resultado = await response.json();

        if (!response.ok || !resultado.success) {
            throw new Error(resultado.error || 'Erro ao verificar faltantes');
        }

        destino.textContent = resultado.faltantes.length
            ? `Faltantes: ${resultado.faltantes.join(', ')}`
            : 'Nenhuma competência faltante.';
    } catch (error) {
        destino.textContent = error.message;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const hoje = new Date();
    const anoAtual = hoje.getFullYear();
    const mesAtual = String(hoje.getMonth() + 1).padStart(2, '0');

    if (document.getElementById('trFiltroAno')) document.getElementById('trFiltroAno').value = anoAtual;
    if (document.getElementById('trCompetencia')) document.getElementById('trCompetencia').value = `${anoAtual}-${mesAtual}`;
    if (document.getElementById('trFaltanteInicio')) document.getElementById('trFaltanteInicio').value = `${anoAtual}-${mesAtual}`;
    if (document.getElementById('trFaltanteFim')) document.getElementById('trFaltanteFim').value = `${anoAtual}-12`;

    carregarTrOficial();
});
