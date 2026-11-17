// FIN-MVP-CADASTRO-UNIFICADO-01 — painel "Novo lancamento" da tela Lancamentos do desktop (js/original/lancamentos.js
// fica igual ao Flask). O cadastro de despesa direta e de compra no cartao passa a ser o do modal unico
// (js/cadastro-despesa.js); o formulario original do painel continua para:
//   - Abastecimento: despesa ou compra com o veiculo, gravadas juntas numa so transacao (salvar_lancamento_abastecimento);
//   - Entrada / credito (fora do contrato do modal);
//   - a edicao de um lancamento existente.
// Nao ha dois caminhos para a mesma gravacao: pelo formulario do painel o adaptador so cria despesa ou compra COM o
// abastecimento (js/lancamentos-adaptador.js); sem ele, o cadastro e o do modal.
// A competencia da despesa direta aberta daqui continua a da tela: o mes da propria data (competencia: 'data').

import { el } from './comum.js';
import { TIPOS, abrirCadastroDespesa, destinosDesktop, prepararCadastro } from './cadastro-despesa.js';

const $ = (id) => document.getElementById(id);
const TITULOS = { escolha: 'Novo lançamento', abastecimento: 'Abastecimento', credito: 'Entrada / crédito' };

export function integrarCadastroDeLancamentos(perfilId) {
    const painel = $('painel-novo-lancamento');
    const form = $('form-lancamento');
    const tipo = $('lancamento-tipo');
    if (!painel || !form || !tipo) return;
    prepararCadastro(perfilId);
    let combustivel = null;  // id da categoria Combustivel do perfil (o banco informa pelo codigo, nunca pelo nome)
    let modo = 'escolha';

    const botao = (id, rotulo, classe = '') => {
        const b = el('button', `cf-lanc-escolha-botao${classe ? ` ${classe}` : ''}`, rotulo);
        b.type = 'button';
        b.id = id;
        return b;
    };
    const despesa = botao('cf-lanc-despesa', 'Despesa direta', 'primario');
    const cartao = botao('cf-lanc-cartao', 'Compra no cartão', 'primario');
    const abastecimento = botao('cf-lanc-abastecimento', 'Abastecimento');
    const credito = botao('cf-lanc-credito', 'Entrada / crédito');
    const escolha = el('div', 'cf-lanc-escolha');
    escolha.id = 'cf-lanc-escolha';
    const botoes = el('div', 'cf-lanc-escolha-botoes');
    botoes.append(despesa, cartao, abastecimento, credito);
    escolha.append(el('p', 'cf-lanc-escolha-texto', 'Escolha o tipo de lançamento.'), botoes,
        el('p', 'cf-lanc-escolha-texto discreto', 'Despesa recorrente e consórcio também podem ser cadastrados: troque o tipo dentro do cadastro.'));
    const dica = el('p', 'cf-lanc-modo-dica');
    dica.id = 'cf-lanc-modo-dica';
    form.before(escolha, dica);

    function definir(novo) {
        modo = novo;
        painel.dataset.modo = novo;
        escolha.hidden = novo !== 'escolha';
        form.hidden = novo === 'escolha';
        for (const o of tipo.options) {
            o.disabled = (novo === 'abastecimento' && o.value === 'credito') || (novo === 'credito' && ['cartao', 'direto'].includes(o.value));
        }
        dica.textContent = novo === 'abastecimento'
            ? 'Despesa ou compra com abastecimento: escolha o tipo, a categoria Combustível e o veículo. Tudo é gravado junto.' : '';
        dica.hidden = !dica.textContent;
        if (TITULOS[novo]) $('modal-lancamento-titulo').textContent = TITULOS[novo];
    }

    // Abrir o painel (botao +, limpar e depois de salvar) volta a escolha; editar mostra o formulario original inteiro.
    const reiniciar = window.abrirModalLancamento;
    window.abrirModalLancamento = function (...args) {
        const r = reiniciar.apply(this, args);
        definir('escolha');
        return r;
    };
    for (const nome of ['cancelarLancamentoInline', 'finalizarLancamentoInline']) window[nome] = () => window.abrirModalLancamento();
    const editar = window.editarLancamento;
    window.editarLancamento = function (...args) {
        const r = editar.apply(this, args);
        definir('edicao');
        return r;
    };

    const abrir = (tipoInicial) => abrirCadastroDespesa({ origem: 'lancamentos', tipoInicial, competencia: 'data',
        mes: $('filtro-mes') ? $('filtro-mes').value : null, destinos: destinosDesktop('lancamentos'),
        aoSalvar: () => window.carregarLancamentos() });
    despesa.addEventListener('click', () => abrir(TIPOS.DESPESA_DIRETA));
    cartao.addEventListener('click', () => abrir(TIPOS.COMPRA_CARTAO));
    abastecimento.addEventListener('click', () => {
        reiniciar();
        definir('abastecimento');
        tipo.focus();
    });
    credito.addEventListener('click', () => {
        reiniciar();
        definir('credito');
        tipo.value = 'credito';
        tipo.dispatchEvent(new Event('change', { bubbles: true }));
    });

    // Abastecimento: a categoria Combustivel ja vem escolhida quando as categorias do tipo (ou do cartao) chegam.
    function escolherCombustivel(select) {
        if (modo !== 'abastecimento' || !combustivel || select.value) return;
        if (![...select.options].some((o) => o.value === String(combustivel))) return;
        select.value = String(combustivel);
        select.dispatchEvent(new Event('change', { bubbles: true }));
    }
    for (const id of ['lancamento-categoria-despesa-cartao', 'lancamento-categoria-geral']) {
        const select = $(id);
        if (!select) continue;
        new MutationObserver(() => escolherCombustivel(select)).observe(select, { childList: true });
        tipo.addEventListener('change', () => setTimeout(() => escolherCombustivel(select), 150));
    }
    fetch('/api/lancamentos/abastecimento/formulario').then((r) => (r.ok ? r.json() : null)).then((j) => {
        const dados = j && j.data;
        combustivel = (dados && dados.categoria_combustivel_id) || null;
        // Sem veiculo ou sem a categoria no perfil nao ha abastecimento a lancar por aqui.
        const disponivel = Boolean(combustivel && dados.veiculos && dados.veiculos.length);
        abastecimento.disabled = !disponivel;
        if (!disponivel) abastecimento.title = 'Cadastre um veículo em Mobilidade para lançar abastecimentos.';
    }).catch(() => { abastecimento.disabled = true; });

    definir(($('lancamento-id') && $('lancamento-id').value) ? 'edicao' : 'escolha');
}
