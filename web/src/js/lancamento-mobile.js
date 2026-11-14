// FIN-MVP-MOBILE-06 — Registrar Lancamento mobile: o atalho Lancamento da pagina principal e o Lancar da barra abrem esta
// pagina. Um seletor compacto de operacoes e, abaixo, o formulario JA EXISTENTE de cada uma, pelos servicos do desktop:
// - Receita: o "Nova receita" das Receitas mobile (js/receita-formulario.js -> criar_receita): a fonte nasce prevista na
//   competencia; o recebimento continua em Receitas -> Receber (o "Entrada / credito" da tela Lancamentos do desktop, sem
//   conta bancaria, e recusado no novo aplicativo);
// - Despesa e Compra no cartao: o formulario da Nova Despesa (js/despesa-formulario.js), com "Conta a pagar" ou "Cartao de
//   credito" ja escolhido (criar_despesa ou criar_compra pelo servico comum js/compras-servico.js);
// - Transferencia: a da tela Contas Bancarias (js/transferencia-formulario.js -> transferir_entre_contas);
// - Abastecimento: o da tela Lancamentos (js/abastecimento-formulario.js -> salvar_lancamento_abastecimento).
// A competencia da pagina principal so e o ponto de partida: cada operacao segue as suas regras de data e competencia.
// Trocar de operacao com dados preenchidos pede confirmacao; sair da pagina tambem (o navegador pergunta). Nenhuma regra
// financeira nova. Sem innerHTML (CSP): tudo por createElement.

import { el } from './comum.js';
import { configurarAbastecimento, responderAbastecimento } from './abastecimento-servico.js';
import { montarFormularioAbastecimento } from './abastecimento-formulario.js';
import { configurarCompras } from './compras-servico.js';
import { configurarContas, responderContas } from './contas-servico.js';
import { acoesDaConfirmacao, montarFormularioDespesa } from './despesa-formulario.js';
import { configurarDespesas, podeGerirPerfil, responderDespesas } from './despesas-servico.js';
import { formatarCompetencia } from './despesas-grupos.js';
import { MODULOS_ATIVOS, ajustarCadastrosPelaPermissao, competenciaInicial, prepararMais, prepararModulos } from './mobile-comum.js';
import { criarFila } from './mobile-formulario.js';
import { mostrarAviso, texto } from './mobile-ui.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { formularioFonte } from './receita-formulario.js';
import { configurarReceitas, responderReceitas } from './receitas-servico.js';
import { montarFormularioTransferencia } from './transferencia-formulario.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);
const TIPOS = { receita: 'Receita', despesa: 'Despesa', cartao: 'Compra no cartão', transferencia: 'Transferência', abastecimento: 'Abastecimento' };
const estado = { mes: null, tipo: null, sujo: false, pedido: 0, categorias: null, contas: null, abastecimento: null };
const api = criarFila('Registrar Lançamento', responderDespesas);
const apiReceitas = (metodo, caminho, corpo = null) => api(metodo, caminho, corpo, responderReceitas);

// Inicio, Voltar e os modulos ativos levam a competencia aberta (como aplicarCompetencia das outras paginas).
function ligarCompetencia(mes) {
    for (const inicio of document.querySelectorAll('[data-inicio]')) inicio.setAttribute('href', `inicio.html?mes=${mes}`);
    for (const item of document.querySelectorAll('[data-modulo][data-destino]')) {
        if (MODULOS_ATIVOS.has(item.dataset.modulo)) item.setAttribute('href', `${item.dataset.destino}?mes=${mes}`);
    }
}

// Leituras de cada operacao: so na primeira vez que ela e aberta.
async function categorias() {
    if (!estado.categorias) {
        const r = await api('GET', '/api/categorias');
        if (!r.success) mostrarAviso(r.error || 'Não foi possível carregar as categorias.', 'erro');
        estado.categorias = r.success ? (r.data || []) : null;
    }
    return estado.categorias || [];
}

async function contas(recarregar = false) {
    if (!estado.contas || recarregar) {
        const r = await api('GET', '/api/contas?status=ATIVO', null, responderContas);
        if (!r.success) mostrarAviso(r.error || 'Não foi possível carregar as contas bancárias.', 'erro');
        estado.contas = r.success ? (r.data || []) : null;
    }
    return estado.contas || [];
}

async function formularioAbastecimento() {
    if (!estado.abastecimento) {
        const r = await api('GET', '/api/lancamentos/abastecimento/formulario', null, responderAbastecimento);
        if (!r.success) mostrarAviso(r.error || 'Não foi possível carregar os veículos.', 'erro');
        estado.abastecimento = r.success ? r.data : null;
    }
    return estado.abastecimento;
}

function irParaInicio() {
    estado.sujo = false;
    window.location.href = `inicio.html?mes=${estado.mes}`;
}

const opcoesComuns = () => ({
    api, mes: estado.mes, rotuloNovo: 'Novo lançamento',
    aoRecomecar: () => abrir(estado.tipo, true),
    aoConcluir: () => { estado.sujo = false; },
});

// Receita: o formulario das Receitas mobile; depois de salvar, a confirmacao com o caminho para receber.
function abrirReceita(cadastro, listaDeContas) {
    const form = formularioFonte({ api: apiReceitas, mes: estado.mes, contas: listaDeContas, aoCancelar: irParaInicio,
        aoSalvo: (r, corpo) => {
            const caixa = el('div', 'mob-confirmacao');
            caixa.id = 'mob-confirmacao';
            const ver = el('a', 'mob-botao primario', 'Ver em Receitas');
            ver.id = 'mob-ver-receitas';
            ver.href = `receitas-mobile.html?mes=${estado.mes}`;
            caixa.append(el('p', 'mob-confirmacao-titulo', `“${corpo.nome}” cadastrada`), texto(r.message || 'Fonte salva com sucesso.'),
                texto(`Receitas: ${formatarCompetencia(estado.mes)}. O recebimento é registrado em Receitas → Receber, com a conta e o movimento.`, 'discreto'),
                acoesDaConfirmacao(cadastro, opcoesComuns(), ver));
            cadastro.replaceChildren(caixa);
            estado.sujo = false;
        } });
    cadastro.replaceChildren(form);
    form.querySelector('input').focus();
}

async function abrir(tipo, forcar = false) {
    if (!TIPOS[tipo]) return;
    if (!forcar && tipo !== estado.tipo && estado.sujo
        && !window.confirm(`Descartar o que foi preenchido em ${TIPOS[estado.tipo]}?`)) return;
    const pedido = ++estado.pedido;
    estado.tipo = tipo;
    estado.sujo = false;
    for (const b of document.querySelectorAll('.mob-tipo')) b.setAttribute('aria-pressed', b.dataset.tipo === tipo ? 'true' : 'false');
    const endereco = new URL(window.location.href);
    if (endereco.searchParams.get('tipo') !== tipo) {
        endereco.searchParams.set('tipo', tipo);
        window.history.replaceState(null, '', endereco);
    }
    const cadastro = $('mob-cadastro');
    cadastro.setAttribute('aria-busy', 'true');
    cadastro.replaceChildren();
    mostrarAviso('');
    if (tipo === 'despesa' || tipo === 'cartao') {
        const lista = await categorias();
        if (pedido !== estado.pedido) return;
        montarFormularioDespesa(cadastro, { ...opcoesComuns(), categorias: lista, meio: tipo === 'cartao' ? 'cartao' : 'conta' });
    } else if (tipo === 'receita') {
        const lista = await contas();
        if (pedido !== estado.pedido) return;
        abrirReceita(cadastro, lista);
    } else if (tipo === 'transferencia') {
        const lista = await contas(true);  // saldos atuais
        if (pedido !== estado.pedido) return;
        // FIN-MVP-MOBILE-07: aberta pelo atalho Transferir das Contas mobile, ja com a conta de origem.
        const origem = Number(new URLSearchParams(window.location.search).get('origem')) || null;
        montarFormularioTransferencia(cadastro, { ...opcoesComuns(), contas: lista, origem });
    } else {
        const formulario = await formularioAbastecimento();
        if (pedido !== estado.pedido) return;
        montarFormularioAbastecimento(cadastro, { ...opcoesComuns(), formulario });
    }
    cadastro.setAttribute('aria-busy', 'false');
}

const usuario = await exigirUsuario();
if (usuario) {
    estado.mes = competenciaInicial();
    prepararModulos();
    prepararMais();
    ligarCompetencia(estado.mes);
    let perfil = null;
    try {
        const perfis = await carregarPerfis();
        perfil = escolherPerfilAtivo(perfis, usuario.id);
        if (perfil) salvarPerfilAtivo(usuario.id, perfil.id);
    } catch (_erro) {
        mostrarAviso('Não foi possível carregar os perfis financeiros.', 'erro');
    }
    const cadastro = $('mob-cadastro');
    if (perfil) {
        $('mob-perfil').textContent = perfil.nome || '';
        configurarDespesas(perfil.id);
        configurarCompras(perfil.id);
        configurarReceitas(perfil.id, { competencia: () => estado.mes });
        configurarContas(perfil.id);
        configurarAbastecimento(perfil.id);
        if (!await podeGerirPerfil()) {
            // Somente leitura: sem operacoes (o banco recusaria qualquer gravacao); Lancar e Lancamento desabilitados.
            await ajustarCadastrosPelaPermissao(usuario.id);
            const voltar = el('a', 'mob-botao', 'Voltar ao início');
            voltar.href = `inicio.html?mes=${estado.mes}`;
            const acoes = el('div', 'mob-acoes');
            acoes.append(voltar);
            cadastro.replaceChildren(texto('Acesso somente de leitura a este perfil: não é possível registrar lançamentos.'), acoes);
            cadastro.setAttribute('aria-busy', 'false');
        } else {
            $('mob-tipos').hidden = false;
            for (const b of document.querySelectorAll('.mob-tipo')) b.addEventListener('click', () => abrir(b.dataset.tipo));
            // Dados preenchidos: trocar de operacao pede confirmacao e sair da pagina tambem; o Cancelar e intencional.
            cadastro.addEventListener('input', () => { if (cadastro.querySelector('form')) estado.sujo = true; });
            cadastro.addEventListener('click', (evento) => { if (evento.target.closest('#mob-cancelar')) estado.sujo = false; });
            window.addEventListener('beforeunload', (evento) => {
                if (!estado.sujo) return;
                evento.preventDefault();
                evento.returnValue = '';
            });
            const pedido = new URLSearchParams(window.location.search).get('tipo');
            if (TIPOS[pedido]) await abrir(pedido);
            else {
                cadastro.replaceChildren(texto('Escolha o tipo de lançamento.', 'discreto'));
                cadastro.setAttribute('aria-busy', 'false');
            }
        }
    } else {
        if ($('mob-aviso').hidden) mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
        cadastro.setAttribute('aria-busy', 'false');
    }
}
