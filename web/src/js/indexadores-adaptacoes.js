// FIN-PRE-PRODUCAO-1 (2.1) — mostrarAlerta do script inline de frontend/templates/indexadores.html (a CSP do novo
// aplicativo nao permite script inline). js/original/indexadores.js usa esta funcao quando ela existe.
function mostrarAlerta(mensagem, tipo = 'success') {
    const container = document.getElementById('alertContainer');
    const alerta = document.createElement('div');
    alerta.className = `alert alert-${tipo}`;
    alerta.textContent = mensagem;
    container.appendChild(alerta);

    setTimeout(() => alerta.remove(), 5000);
}
