// Utilitarios de tela compartilhados (FIN-RECEITAS-1). Sem acesso a dados.

export const MES_VALIDO = /^\d{4}-(0[1-9]|1[0-2])$/;
const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

export function mesAtualBrasilia() {
    const partes = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit' })
        .formatToParts(new Date());
    const valor = (tipo) => partes.find((p) => p.type === tipo).value;
    return `${valor('year')}-${valor('month')}`;
}

export function deslocarMes(mes, delta) {
    const [ano, m] = mes.split('-').map(Number);
    const data = new Date(Date.UTC(ano, m - 1 + delta, 1));
    return `${data.getUTCFullYear()}-${String(data.getUTCMonth() + 1).padStart(2, '0')}`;
}

export function tituloDoMes(mes) {
    const [ano, m] = mes.split('-').map(Number);
    const texto = new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric', timeZone: 'UTC' })
        .format(new Date(Date.UTC(ano, m - 1, 1)));
    return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export function dataCurta(iso) {
    if (!iso) return '';
    const [ano, m, d] = iso.split('-');
    return `${d}/${m}/${ano}`;
}

export const competenciaCurta = (iso) => `${iso.slice(5, 7)}/${iso.slice(0, 4)}`;

// Soma em centavos: evita erro de ponto flutuante nos totais.
export const centavos = (valor) => Math.round(Number(valor || 0) * 100);
export const reais = (c) => moeda.format(c / 100);

// "1.234,56" ou "1234.56" -> "1234.56"; o banco valida de novo.
export function normalizarValor(texto) {
    const limpo = String(texto || '').trim().replace(/\s|R\$/g, '');
    const numero = limpo.includes(',') ? limpo.replace(/\./g, '').replace(',', '.') : limpo;
    return /^\d+(\.\d{1,2})?$/.test(numero) ? numero : null;
}

export const formatarValor = (valor) => (valor === null || valor === undefined ? ''
    : Number(valor).toFixed(2).replace('.', ','));

export function el(tag, classe, texto) {
    const elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto !== undefined && texto !== null) elemento.textContent = String(texto);
    return elemento;
}

export function botao(texto, classe) {
    const elemento = el('button', classe ? `botao ${classe}` : 'botao', texto);
    elemento.type = 'button';
    return elemento;
}

export function campo(rotulo, controle, id) {
    const linha = el('label', 'form-campo');
    linha.htmlFor = id;
    controle.id = id;
    linha.append(el('span', 'form-rotulo', rotulo), controle);
    return linha;
}

export function seletor(opcoes, valor) {
    const select = el('select');
    for (const [chave, texto] of opcoes) {
        const opcao = el('option', null, texto);
        opcao.value = String(chave);
        select.append(opcao);
    }
    if (valor !== undefined && valor !== null) select.value = String(valor);
    return select;
}

export function entrada(tipo, valor) {
    const input = el('input');
    input.type = tipo;
    if (valor !== undefined && valor !== null) input.value = String(valor);
    return input;
}

export function linhaDetalhe(lista, rotulo, valor) {
    if (valor === undefined || valor === null || valor === '') return;
    lista.append(el('dt', null, rotulo), el('dd', null, valor));
}
