// FIN-MVP-MOBILE-06 — pecas dos formularios mobile de cadastro, extraidas da Nova Despesa (FIN-MVP-MOBILE-05, homologada)
// para servir a Nova Despesa e o Registrar Lancamento sem duplicar: campo com o erro logo abaixo, dois campos lado a lado,
// fila de pedidos aos servicos do desktop, a pergunta da fatura consolidada e o tratamento dos erros do servico.
// Sem regra financeira; sem innerHTML (CSP): tudo por createElement.

import { el } from './comum.js';
import { textoConsolidada } from './fechamento.js';
import { FALHA_GERAL, botao, mostrarMensagem, texto } from './mobile-ui.js';

export const mesAno = (iso) => `${String(iso).slice(5, 7)}/${String(iso).slice(0, 4)}`;
export const moeda = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

// Pedidos aos servicos do desktop: um de cada vez (como a ponte-api.js do desktop); o corpo passa por JSON, como o fetch.
// `servico` escolhe o servico de cada pedido (o padrao e o da tela).
export function criarFila(rotulo, servicoPadrao) {
    let fila = Promise.resolve();
    return function api(metodo, caminho, corpo = null, servico = servicoPadrao) {
        const endereco = new URL(caminho, window.location.origin);
        const tarefa = fila.then(async () => {
            try {
                const r = await servico({ metodo, caminho: endereco.pathname, parametros: endereco.searchParams,
                    corpo: corpo === null ? null : JSON.parse(JSON.stringify(corpo)) });
                return r.corpo;
            } catch (erro) {
                console.error(`${rotulo}:`, metodo, endereco.pathname, erro);
                return { success: false, error: FALHA_GERAL };
            }
        });
        fila = tarefa.catch(() => {});
        return tarefa;
    };
}

// Campo com o erro logo abaixo (borda vermelha e foco no primeiro erro, pela tela).
export function campoComErro(rotulo, controle, { obrigatorio = false, ajuda = '' } = {}) {
    const caixa = el('label', 'mob-campo');
    const titulo = el('span', null, rotulo);
    if (obrigatorio) titulo.append(el('span', 'mob-obrigatorio', ' *'));
    const erro = el('span', 'mob-campo-erro');
    erro.hidden = true;
    erro.setAttribute('role', 'alert');
    caixa.append(titulo, controle);
    if (ajuda) caixa.append(el('span', 'mob-ajuda', ajuda));
    caixa.append(erro);
    caixa.erro = (conteudo) => {
        erro.textContent = conteudo || '';
        erro.hidden = !conteudo;
        if (conteudo) controle.setAttribute('aria-invalid', 'true');
        else controle.removeAttribute('aria-invalid');
    };
    // Corrigir o campo apaga o erro dele.
    controle.addEventListener('input', () => caixa.erro(''));
    controle.addEventListener('change', () => caixa.erro(''));
    return caixa;
}

export const par = (...filhos) => {
    const linha = el('div', 'mob-par');
    linha.append(...filhos);
    return linha;
};

// Erros da validacao da tela: cada um no seu campo, foco no primeiro. Devolve true se havia erro.
export function mostrarErros(erros) {
    if (!erros.length) return false;
    erros.forEach(([c, t]) => c.erro(t));
    erros[0][0].querySelector('input, select, textarea').focus();
    return true;
}

// Mensagem do servico junto ao campo que ela cita (o primeiro padrao que casar) e no rodape do formulario.
export function erroDoServico(m, erro, pares) {
    const doCampo = pares.find(([padrao]) => padrao.test(erro));
    if (doCampo) doCampo[1].erro(erro);
    mostrarMensagem(m, erro, 'erro');
}

// Fatura consolidada: a mesma pergunta do desktop (Lancamentos), no proprio formulario, com os totais da previa do banco.
export function perguntaConsolidada(caixa, faturas, { aoConfirmar, aoRecusar }) {
    const sim = botao('Confirmar inclusão', 'primario');
    sim.id = 'mob-confirmar-inclusao';
    const nao = botao('Não incluir');
    nao.id = 'mob-nao-incluir';
    const botoes = el('div', 'mob-acoes');
    botoes.append(nao, sim);
    caixa.replaceChildren(el('p', 'mob-confirmacao-titulo', 'Fatura já consolidada'),
        ...(faturas || []).map((f) => texto(textoConsolidada(f))),
        texto('Confirmar a inclusão? O total consolidado será atualizado e a inclusão ficará registrada.', 'discreto'), botoes);
    caixa.hidden = false;
    nao.addEventListener('click', aoRecusar);
    sim.addEventListener('click', () => aoConfirmar((faturas || []).map((f) => ({ fatura_id: f.fatura_id, total_consolidado: f.total_consolidado }))));
    sim.focus();
}
