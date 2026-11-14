// FIN-MVP-MOBILE-07 — Contas e Movimentacoes mobile (atalho Contas da pagina principal). Consulta, pelas rotas do servico
// comum a tela Contas Bancarias do desktop (js/contas-servico.js):
// - contas do perfil (ativas e inativas) com o saldo do banco (contas_bancarias_tela; nada e somado na tela);
// - extrato do periodo (extrato_conta_bancaria: mais recentes primeiro, saldo apos cada movimento calculado no banco,
//   limite de 200 como o desktop); conferencia de saldo (conferir_saldo_conta) so para avisar divergencia, sem ajustar;
// - detalhe do movimento e a sua origem (a despesa, a fatura ou a outra conta da transferencia), so leitura.
// Operacoes: nenhuma nova. A transferencia e a do Registrar Lancamento (FIN-MVP-MOBILE-06), aberta com a conta de origem;
// estornos e cancelamentos ficam nos modulos de origem (Despesas, Receitas, Cartoes); ajustes, so no desktop.
// Sem innerHTML (CSP): tudo por createElement.

import { dataCurta, deslocarMes, el } from './comum.js';
import { configurarContas, responderContas } from './contas-servico.js';
import {
    LIMITE_EXTRATO, TIPOS_DO_FILTRO, ehEntrada, filtrarMovimentos, naturezaDoMovimento, periodoDoMes, rotuloDaConta, sinalDoMovimento,
} from './contas-movimentos.js';
import { formatarCompetencia } from './despesas-grupos.js';
import {
    ajustarCadastrosPelaPermissao, aplicarCompetencia, competenciaInicial, prepararMais, prepararModulos,
} from './mobile-comum.js';
import { criarFila, moeda } from './mobile-formulario.js';
import {
    SETA, abrirFolha, botao, campo, detalhes, diaMes, entrada, fecharFolha, icone, mensagem, mostrarAviso, mostrarMensagem,
    prepararFolha, seletor, texto,
} from './mobile-ui.js';
import { carregarPerfis, escolherPerfilAtivo, podeGerirPerfil, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);
const api = criarFila('Contas', responderContas);
const estado = {
    mes: null,              // 'AAAA-MM' (periodo padrao: o mes)
    contas: [],
    contaId: null,
    movimentos: [],         // extrato do periodo, como o banco devolveu
    filtros: { inicio: '', fim: '', tipo: '' },  // inicio/fim vazios: o mes
    somenteLeitura: true,
    pedido: 0,
};

const contaAtual = () => estado.contas.find((c) => c.id === estado.contaId) || null;
const periodo = () => (estado.filtros.inicio || estado.filtros.fim
    ? { inicio: estado.filtros.inicio || null, fim: estado.filtros.fim || null } : periodoDoMes(estado.mes));
const valorComSinal = (m) => `${sinalDoMovimento(m)} ${moeda(m.valor)}`;

// Endereco: a competencia (aplicarCompetencia) e a conta escolhida (atualizar a pagina mantem as duas).
function guardarConta() {
    const endereco = new URL(window.location.href);
    if (endereco.searchParams.get('conta') !== String(estado.contaId)) {
        endereco.searchParams.set('conta', String(estado.contaId));
        window.history.replaceState(null, '', endereco);
    }
}

// Atalho da transferencia: o formulario do Registrar Lancamento, com esta conta como origem (so quem gere; conta ativa).
function ajustarTransferir() {
    const botaoTransferir = $('mob-transferir');
    const conta = contaAtual();
    const pode = !estado.somenteLeitura && conta && conta.status === 'ATIVO';
    botaoTransferir.hidden = !pode;
    if (pode) botaoTransferir.href = `lancamento-mobile.html?mes=${estado.mes}&tipo=transferencia&origem=${conta.id}`;
}

// ---------------------------------------------------------------------------------------------------------------
// Saldo e lista

function desenharSaldo(conferencia) {
    const conta = contaAtual();
    const caixa = $('mob-saldo');
    if (!conta) { caixa.hidden = true; return; }
    const valor = el('span', `mob-saldo-valor${Number(conta.saldo_atual) < 0 ? ' negativo' : ''}`, moeda(conta.saldo_atual));
    valor.id = 'mob-saldo-valor';
    const info = [conta.tipo, conta.instituicao, conta.status === 'INATIVO' ? 'Inativa' : ''].filter(Boolean).join(' · ');
    caixa.replaceChildren(el('span', 'mob-saldo-rotulo', 'Saldo atual'), valor);
    if (info) caixa.append(el('span', 'mob-saldo-info', info));
    // A conferencia do desktop (so leitura): divergencia entre o saldo registrado e os movimentos e apenas avisada.
    if (conferencia && conferencia.consistente === false) {
        const alerta = el('span', 'mob-saldo-alerta', `Conferência: o saldo registrado difere da soma dos movimentos em ${moeda(conferencia.divergencia)}. `
            + 'Nada foi ajustado; confira no desktop.');
        alerta.id = 'mob-saldo-divergencia';
        caixa.append(alerta);
    }
    caixa.hidden = false;
}

// Periodo: o mes da navegacao, ou o intervalo dos filtros (no lugar do mes).
function desenharPeriodo() {
    aplicarCompetencia(estado.mes);
    const f = estado.filtros;
    if (f.inicio || f.fim) $('mob-competencia').textContent = `${f.inicio ? dataCurta(f.inicio) : '…'} a ${f.fim ? dataCurta(f.fim) : '…'}`;
    $('mob-filtro-marca').hidden = !(f.inicio || f.fim || f.tipo);
    for (const seta of [$('mob-mes-anterior'), $('mob-mes-seguinte')]) seta.disabled = Boolean(f.inicio || f.fim);
}

function linhaMovimento(m) {
    const natureza = naturezaDoMovimento(m);
    const b = el('button', `mob-linha mob-movimento${ehEntrada(m) ? ' entrada' : ''}`);
    b.type = 'button';
    b.dataset.id = m.id;
    b.dataset.natureza = natureza.chave;
    const textoLinha = el('span', 'mob-linha-texto');
    textoLinha.append(el('span', 'mob-linha-nome', m.descricao || natureza.rotulo), el('span', 'mob-linha-data', natureza.rotulo));
    const valor = valorComSinal(m);
    b.append(el('span', 'mob-movimento-data', diaMes(m.data_movimento)), textoLinha, el('span', 'mob-linha-valor', valor), icone(SETA, 'mob-seta'));
    b.title = m.descricao || natureza.rotulo;
    b.setAttribute('aria-label', `${dataCurta(m.data_movimento)}, ${m.descricao || natureza.rotulo}, ${valor}, ${natureza.rotulo}. Ver detalhes`);
    b.addEventListener('click', () => abrirDetalhes(m));
    return b;
}

function desenharLista() {
    const lista = $('mob-lista');
    const visiveis = filtrarMovimentos(estado.movimentos, estado.filtros.tipo);
    if (!visiveis.length) {
        const vazio = el('div', 'mob-vazio');
        vazio.append(el('strong', null, 'Nenhuma movimentação no período'),
            el('span', null, estado.filtros.tipo ? 'Nenhum movimento deste tipo no período escolhido.' : 'Esta conta não tem movimentos no período escolhido.'));
        lista.replaceChildren(vazio);
    } else {
        lista.replaceChildren(...visiveis.map(linhaMovimento));
    }
    // O extrato do desktop traz ate 200 movimentos (os mais recentes): com o limite atingido, a lista avisa.
    const limite = $('mob-limite');
    limite.hidden = estado.movimentos.length < LIMITE_EXTRATO;
    limite.textContent = `Mostrando os ${LIMITE_EXTRATO} movimentos mais recentes do período. Escolha um período menor para ver os anteriores.`;
}

// Carga da conta escolhida: o extrato do periodo e a conferencia do saldo, pelas rotas do desktop. Nada e gravado.
async function carregar() {
    const pedido = ++estado.pedido;
    const conta = contaAtual();
    const lista = $('mob-lista');
    lista.setAttribute('aria-busy', 'true');
    desenharPeriodo();
    ajustarTransferir();
    if (!conta) {
        lista.replaceChildren(texto('Nenhuma conta bancária neste perfil: cadastre a conta no desktop.', 'discreto'));
        lista.setAttribute('aria-busy', 'false');
        return;
    }
    guardarConta();
    const { inicio, fim } = periodo();
    const q = new URLSearchParams({ limit: String(LIMITE_EXTRATO), incluir_saldo: '1' });
    if (inicio) q.set('inicio', inicio);
    if (fim) q.set('fim', fim);
    const [extrato, conferencia] = await Promise.all([
        api('GET', `/api/contas/${conta.id}/movimentos?${q}`),
        api('GET', `/api/contas/${conta.id}/conferir-saldo`),
    ]);
    if (pedido !== estado.pedido) return;  // ja trocaram de conta ou de periodo
    estado.movimentos = extrato.success ? (extrato.data || []) : [];
    if (!extrato.success) mostrarAviso(extrato.error || 'Não foi possível carregar as movimentações.', 'erro');
    desenharSaldo(conferencia.success ? conferencia.data : null);
    desenharLista();
    lista.dataset.carregado = `${conta.id}:${inicio || ''}:${fim || ''}`;
    lista.setAttribute('aria-busy', 'false');
}

// ---------------------------------------------------------------------------------------------------------------
// Detalhe do movimento (so leitura) e a origem

function linkBotao(rotulo, href, id) {
    const a = el('a', 'mob-botao', rotulo);
    a.href = href;
    if (id) a.id = id;
    return a;
}

async function abrirDetalhes(m) {
    const natureza = naturezaDoMovimento(m);
    const conta = contaAtual();
    const original = m.movimento_original_id ? estado.movimentos.find((x) => x.id === m.movimento_original_id) : null;
    const corpo = detalhes([
        ['Data', dataCurta(m.data_movimento)],
        ['Descrição', m.descricao || '—'],
        ['Valor', valorComSinal(m)],
        ['Conta', conta ? conta.nome : ''],
        ['Tipo', ehEntrada(m) ? 'Entrada (crédito)' : 'Saída (débito)'],
        ['Origem', natureza.rotulo],
        ['Saldo após o movimento', m.saldo_apos_movimento !== null && m.saldo_apos_movimento !== undefined ? moeda(m.saldo_apos_movimento) : ''],
        ['Estorno de', natureza.chave === 'estorno'
            ? (original ? `${original.descricao || 'Movimento'} de ${dataCurta(original.data_movimento)} (${valorComSinal(original)})` : 'Movimento anterior ao período')
            : ''],
    ]);
    corpo.id = 'mob-detalhe-movimento';
    const origem = el('div', 'mob-detalhe-origem');
    origem.id = 'mob-detalhe-origem';
    const acoes = el('div', 'mob-acoes');
    const fechar = botao('Fechar');
    fechar.addEventListener('click', fecharFolha);
    acoes.append(fechar);
    // As regras de cada origem ficam no modulo dela: aqui nao se edita, exclui nem estorna.
    const nota = {
        ajuste: 'Ajustes de saldo são incluídos, alterados ou excluídos só no desktop (Contas Bancárias).',
        despesa: 'Estorno e cancelamento do pagamento: na Lista de Despesas, que preserva as regras da despesa.',
        fatura: 'Estorno do pagamento da fatura: nos Cartões, que preservam a relação com a fatura.',
        receita: 'Estorno do recebimento: em Receitas.',
        estorno: 'O estorno devolve o valor do movimento original; o histórico fica preservado.',
        transferencia: 'A transferência registra a saída numa conta e a entrada na outra.',
    }[natureza.chave];
    abrirFolha(natureza.rotulo, corpo, origem, ...(nota ? [texto(nota, 'discreto')] : []), acoes);
    if (natureza.chave === 'receita') {
        acoes.prepend(linkBotao('Ver em Receitas', `receitas-mobile.html?mes=${m.data_movimento.slice(0, 7)}`, 'mob-ver-origem'));
    }
    if (!m.conta_id && !m.fatura_id && !m.transferencia_id) return;
    const q = new URLSearchParams({ conta_bancaria_id: String(m.conta_bancaria_id) });
    if (m.conta_id) q.set('conta_id', String(m.conta_id));
    if (m.fatura_id) q.set('fatura_id', String(m.fatura_id));
    if (m.transferencia_id) { q.set('transferencia_id', String(m.transferencia_id)); q.set('data', m.data_movimento.slice(0, 10)); }
    origem.append(texto('Carregando a origem...', 'discreto'));
    const r = await api('GET', `/api/movimentos/origem?${q}`);
    if (!origem.isConnected) return;  // o painel ja foi fechado
    if (!r.success) { origem.replaceChildren(texto(r.error || 'Não foi possível ler a origem.', 'discreto')); return; }
    const o = r.data || {};
    const pares = [];
    if (o.despesa) {
        const comp = String(o.despesa.competencia || '').slice(0, 7);
        pares.push(['Despesa', `${o.despesa.nome}${comp ? ` · ${formatarCompetencia(comp)}` : ''}`], ['Situação da despesa', o.despesa.situacao]);
        if (comp) acoes.prepend(linkBotao('Ver na Lista de Despesas', `despesas-mobile.html?mes=${comp}`, 'mob-ver-origem'));
    }
    if (o.fatura) {
        const comp = String(o.fatura.competencia || '').slice(0, 7);
        pares.push(['Fatura', `${o.fatura.cartao_nome} · ${formatarCompetencia(comp)}`], ['Situação da fatura', o.fatura.paga ? 'Paga' : 'Em aberto']);
        acoes.prepend(linkBotao('Ver no cartão', `cartoes-mobile.html?mes=${comp}&cartao=${o.fatura.cartao_id}`, 'mob-ver-origem'));
    }
    if (o.contrapartida) {
        pares.push([ehEntrada(m) ? 'Conta de origem' : 'Conta de destino', o.contrapartida.conta_nome]);
        acoes.prepend(linkBotao('Ver a outra conta', `contas-mobile.html?mes=${estado.mes}&conta=${o.contrapartida.conta_id}`, 'mob-ver-origem'));
    }
    origem.replaceChildren(...(pares.length ? [detalhes(pares)] : []));
}

// ---------------------------------------------------------------------------------------------------------------
// Filtros: periodo (de/ate; vazio = o mes da navegacao) e tipo. A consulta ao banco continua a do desktop.

function abrirFiltros() {
    const f = estado.filtros;
    const padrao = periodoDoMes(estado.mes);
    const inicio = entrada('date', f.inicio || padrao.inicio);
    const fim = entrada('date', f.fim || padrao.fim);
    const tipo = seletor(TIPOS_DO_FILTRO, f.tipo || '');
    const form = el('form', 'mob-form');
    form.noValidate = true;
    const m = mensagem();
    const limpar = botao('Limpar');
    limpar.id = 'mob-filtros-limpar';
    const aplicar = botao('Aplicar', 'primario');
    aplicar.type = 'submit';
    aplicar.id = 'mob-filtros-aplicar';
    const acoes = el('div', 'mob-acoes');
    acoes.append(limpar, aplicar);
    form.append(campo('De', inicio), campo('Até', fim), campo('Tipo de movimentação', tipo),
        texto('Sem alterar as datas, vale o mês escolhido na tela.', 'discreto'), m, acoes);
    limpar.addEventListener('click', () => {
        estado.filtros = { inicio: '', fim: '', tipo: '' };
        fecharFolha();
        carregar();
    });
    form.addEventListener('submit', (evento) => {
        evento.preventDefault();
        if (inicio.value && fim.value && inicio.value > fim.value) {
            mostrarMensagem(m, 'A data inicial não pode ser maior que a final.', 'erro');
            return;
        }
        const doMes = inicio.value === padrao.inicio && fim.value === padrao.fim;
        estado.filtros = { inicio: doMes ? '' : inicio.value, fim: doMes ? '' : fim.value, tipo: tipo.value };
        fecharFolha();
        carregar();
    });
    abrirFolha('Filtros', form);
}

function trocarMes(delta) {
    estado.mes = deslocarMes(estado.mes, delta);
    carregar();
}

// ---------------------------------------------------------------------------------------------------------------
// Inicio

const usuario = await exigirUsuario();
if (usuario) {
    estado.mes = competenciaInicial();
    prepararModulos();
    prepararMais();
    prepararFolha();
    aplicarCompetencia(estado.mes);
    let perfil = null;
    try {
        const perfis = await carregarPerfis();
        perfil = escolherPerfilAtivo(perfis, usuario.id);
        if (perfil) salvarPerfilAtivo(usuario.id, perfil.id);
    } catch (_erro) {
        mostrarAviso('Não foi possível carregar os perfis financeiros.', 'erro');
    }
    if (perfil) {
        $('mob-perfil').textContent = perfil.nome || '';
        configurarContas(perfil.id);
        estado.somenteLeitura = !(await podeGerirPerfil(perfil.id).catch(() => false));
        if (estado.somenteLeitura) ajustarCadastrosPelaPermissao(usuario.id);
        // Contas do perfil: as ativas primeiro (como o desktop as lista, por nome) e as inativas, que guardam historico.
        const [ativas, inativas] = await Promise.all([api('GET', '/api/contas?status=ATIVO'), api('GET', '/api/contas?status=INATIVO')]);
        if (!ativas.success) mostrarAviso(ativas.error || 'Não foi possível carregar as contas.', 'erro');
        estado.contas = [...(ativas.success ? ativas.data || [] : []), ...(inativas.success ? inativas.data || [] : [])];
        const pedida = Number(new URLSearchParams(window.location.search).get('conta'));
        estado.contaId = (estado.contas.find((c) => c.id === pedida) || estado.contas[0] || {}).id ?? null;
        const select = $('mob-conta');
        select.replaceChildren(...estado.contas.map((c) => new Option(rotuloDaConta(c, estado.contas), String(c.id))));
        if (estado.contaId !== null) select.value = String(estado.contaId);
        $('mob-conta-caixa').hidden = !estado.contas.length;
        select.addEventListener('change', () => {
            estado.contaId = Number(select.value);
            carregar();
        });
        $('mob-filtros').addEventListener('click', abrirFiltros);
        $('mob-mes-anterior').addEventListener('click', () => trocarMes(-1));
        $('mob-mes-seguinte').addEventListener('click', () => trocarMes(1));
        await carregar();
    } else {
        if ($('mob-aviso').hidden) mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
        $('mob-lista').setAttribute('aria-busy', 'false');
    }
}
