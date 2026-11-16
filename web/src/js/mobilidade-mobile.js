// FIN-MOBILE-12 — Mobilidade mobile (atalho Mobilidade da pagina principal). Tudo pelo servico comum a tela do desktop
// (js/mobilidade-servico.js: veiculos_tela e abastecimentos_veiculo_tela); nenhuma regra nova e nenhuma gravacao aqui:
// - veiculos do perfil, com a quilometragem que o banco informa (leitura real do ultimo abastecimento ou estimativa) e o
//   combustivel;
// - Abastecer: abre o formulario de abastecimento ja homologado no Registrar Lancamento (FIN-MVP-MOBILE-06), com o veiculo
//   escolhido; a despesa (conta a pagar ou compra no cartao) e o abastecimento sao gravados la, juntos. O endereco leva
//   retorno=mobilidade: o Voltar e o Cancelar de la devolvem a esta pagina (so navegacao);
// - Historico: os abastecimentos do veiculo, como o banco devolve (mais recentes primeiro; anulados marcados);
// - Resumo do veiculo na competencia: gasto do mes, consumo medio, custo por km, ultimos abastecimentos e o gasto dos
//   ultimos meses. Sao somas de apresentacao sobre o historico; nada e calculado para gravar.
// So no desktop: cadastro e edicao de veiculos, projecoes, modalidades, assinaturas, correcao e anulacao de abastecimento.
// Sem innerHTML (CSP): tudo por createElement.

import { dataCurta, deslocarMes, el } from './comum.js';
import {
    ajustarCadastrosPelaPermissao, aplicarCompetencia, competenciaInicial, prepararMais, prepararModulos, rotuloCompetencia,
} from './mobile-comum.js';
import { criarFila, moeda } from './mobile-formulario.js';
import { abrirFolha, botao, detalhes, fecharFolha, mostrarAviso, prepararFolha, texto } from './mobile-ui.js';
import { configurarMobilidade, responderMobilidade } from './mobilidade-servico.js';
import { carregarPerfis, escolherPerfilAtivo, podeGerirPerfil, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario } from './sessao.js';

const $ = (id) => document.getElementById(id);
const SVG = 'http://www.w3.org/2000/svg';
const api = criarFila('Mobilidade', responderMobilidade);
const estado = { mes: null, veiculos: [], historicos: new Map(), somenteLeitura: true };

const COMBUSTIVEIS = { flex: 'Flex', gasolina: 'Gasolina', etanol: 'Etanol', diesel: 'Diesel', gnv: 'GNV', eletrico: 'Elétrico', outro: 'Outro' };
const SITUACOES = { SIMULADO: 'Simulado', FORA_DE_USO: 'Fora de uso' };
const combustivel = (c) => COMBUSTIVEIS[String(c || '').toLowerCase()] || (c ? String(c) : '—');
const numero = (v, casas = 0) => Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
const km = (v) => `${numero(v, Number.isInteger(Number(v)) ? 0 : 1)} km`;
const litros = (v) => `${numero(v, 3)} L`;
const precoLitro = (v) => `${Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 3 })}/L`;
const validos = (lista) => lista.filter((a) => !a.anulado);
const doMes = (lista, mes) => validos(lista).filter((a) => String(a.data_abastecimento).slice(0, 7) === mes);
const soma = (lista, campo) => lista.reduce((s, a) => s + Number(a[campo] || 0), 0);

// ---------------------------------------------------------------------------------------------------------------
// Indicadores de apresentacao (sobre o historico que o banco devolve)

// Consumo e custo por km: so abastecimentos com os km rodados desde a leitura anterior de hodometro (o banco os informa);
// abastecimento sem essa referencia (o primeiro, ou anulado) nao entra em nenhum dos dois. Nenhum dado e alterado.
// - Consumo (km/L) e ESTIMATIVA: supoe o tanque completado a cada abastecimento, o que o sistema nao registra.
// - Custo por km (R$/km) e financeiro: o valor pago nesses abastecimentos pelos km rodados entre as leituras.
export function indicadores(abastecimentos) {
    const comKm = validos(abastecimentos).filter((a) => Number(a.km_rodados) > 0 && Number(a.litros) > 0);
    const kmTotal = soma(comKm, 'km_rodados');
    const litrosTotal = soma(comKm, 'litros');
    const valorTotal = soma(comKm, 'valor_total');
    return {
        leituras: comKm.length,
        consumo: kmTotal > 0 && litrosTotal > 0 ? kmTotal / litrosTotal : null,   // km por litro
        custoKm: kmTotal > 0 ? valorTotal / kmTotal : null,                        // R$ por km
    };
}

// Gasto com abastecimento nos `quantos` meses que terminam em `mes`.
export function gastoPorMes(abastecimentos, mes, quantos = 6) {
    return [...Array(quantos).keys()].map((i) => deslocarMes(mes, i - quantos + 1))
        .map((m) => ({ mes: m, valor: soma(doMes(abastecimentos, m), 'valor_total') }));
}

// ---------------------------------------------------------------------------------------------------------------
// Veiculos

async function historico(veiculoId) {
    if (!estado.historicos.has(veiculoId)) {
        const r = await api('GET', `/api/veiculos/${veiculoId}/abastecimentos`);
        if (!r.success) return { erro: r.error || 'Não foi possível ler os abastecimentos.', quilometragem: {}, abastecimentos: [] };
        estado.historicos.set(veiculoId, { quilometragem: (r.data && r.data.quilometragem) || {}, abastecimentos: (r.data && r.data.abastecimentos) || [] });
    }
    return estado.historicos.get(veiculoId);
}

function textoDaQuilometragem(q) {
    if (q.km_atual === null || q.km_atual === undefined) return { valor: '—', nota: 'sem leitura' };
    if (q.km_real !== null && q.km_real !== undefined && Number(q.km_estimado || 0) === 0) return { valor: km(q.km_atual), nota: `leitura de ${dataCurta(q.km_real_data)}` };
    return { valor: km(q.km_atual), nota: q.km_real !== null && q.km_real !== undefined ? `estimada; leitura de ${km(q.km_real)} em ${dataCurta(q.km_real_data)}` : 'estimada' };
}

function cartaoDoVeiculo(v, h) {
    const cartao = el('article', 'mob-veiculo');
    cartao.dataset.id = v.id;
    const topo = el('header', 'mob-veiculo-topo');
    topo.append(el('h3', 'mob-veiculo-nome', v.nome));
    const situacao = SITUACOES[v.situacao_uso] || (v.status && v.status !== 'ATIVO' ? 'Simulado' : '');
    if (situacao) topo.append(el('span', 'mob-veiculo-situacao', situacao));
    const q = textoDaQuilometragem(h.quilometragem || {});
    const mes = doMes(h.abastecimentos, estado.mes);
    const dados = el('dl', 'mob-veiculo-dados');
    const par = (rotulo, valor, nota, classe) => {
        const d = el('div', classe || null);
        d.append(el('dt', null, rotulo), el('dd', null, valor));
        if (nota) d.append(el('span', 'mob-veiculo-nota', nota));
        return d;
    };
    dados.append(par('Quilometragem', q.valor, q.nota, 'mob-veiculo-km'), par('Combustível', combustivel(v.combustivel), null, 'mob-veiculo-combustivel'),
        par(`Abastecido em ${rotuloCompetencia(estado.mes)}`, moeda(soma(mes, 'valor_total')), `${mes.length} abastecimento${mes.length === 1 ? '' : 's'}`, 'mob-veiculo-mes'));
    const acoes = el('div', 'mob-veiculo-acoes');
    if (!estado.somenteLeitura && String(v.combustivel || '').toLowerCase() !== 'eletrico') {
        // O formulario homologado no Registrar Lancamento, com este veiculo: despesa e abastecimento gravados juntos.
        const abastecer = el('a', 'mob-botao primario', 'Abastecer');
        abastecer.dataset.acao = 'abastecer';
        abastecer.href = `lancamento-mobile.html?mes=${estado.mes}&tipo=abastecimento&veiculo=${v.id}&retorno=mobilidade`;
        acoes.append(abastecer);
    }
    const verHistorico = botao('Histórico');
    verHistorico.dataset.acao = 'historico';
    verHistorico.addEventListener('click', () => abrirHistorico(v));
    const verResumo = botao('Resumo');
    verResumo.dataset.acao = 'resumo';
    verResumo.addEventListener('click', () => abrirResumo(v));
    acoes.append(verHistorico, verResumo);
    cartao.append(topo, dados, acoes);
    if (h.erro) cartao.append(texto(h.erro, 'discreto'));
    return cartao;
}

async function desenhar() {
    const lista = $('mob-lista');
    lista.setAttribute('aria-busy', 'true');
    aplicarCompetencia(estado.mes);
    if (!estado.veiculos.length) {
        const vazio = el('div', 'mob-vazio');
        vazio.append(el('strong', null, 'Nenhum veículo neste perfil'), el('span', null, 'O cadastro de veículos é feito na Mobilidade, no desktop.'));
        lista.replaceChildren(vazio);
    } else {
        const historicos = await Promise.all(estado.veiculos.map((v) => historico(v.id)));
        lista.replaceChildren(...estado.veiculos.map((v, i) => cartaoDoVeiculo(v, historicos[i])));
    }
    lista.dataset.carregado = estado.mes;
    lista.setAttribute('aria-busy', 'false');
}

// ---------------------------------------------------------------------------------------------------------------
// Historico e resumo (so leitura)

function linhaDoAbastecimento(a) {
    const item = el('li', `mob-abastecimento${a.anulado ? ' anulado' : ''}`);
    item.dataset.id = a.id;
    const principal = el('span', 'mob-abastecimento-principal');
    principal.append(el('strong', null, dataCurta(a.data_abastecimento)), el('span', 'mob-linha-valor', moeda(a.valor_total)));
    const partes = [km(a.hodometro_km), combustivel(a.combustivel), litros(a.litros), precoLitro(a.preco_litro)];
    if (Number(a.km_rodados) > 0) partes.push(`${km(a.km_rodados)} rodados`);
    if (a.anulado) partes.push('anulado');
    item.append(principal, el('span', 'mob-abastecimento-detalhe', partes.join(' · ')));
    return item;
}

function listaDeAbastecimentos(itens, vazio) {
    if (!itens.length) return texto(vazio, 'discreto');
    const ul = el('ul', 'mob-abastecimentos');
    ul.append(...itens.map(linhaDoAbastecimento));
    return ul;
}

function fecharBotao() {
    const acoes = el('div', 'mob-acoes');
    const fechar = botao('Fechar');
    fechar.addEventListener('click', fecharFolha);
    acoes.append(fechar);
    return acoes;
}

async function abrirHistorico(v) {
    const h = await historico(v.id);
    let soDoMes = false;
    const filtro = el('div', 'mob-mob-segmento');
    filtro.setAttribute('role', 'group');
    filtro.setAttribute('aria-label', 'Período');
    const caixa = el('div');
    caixa.id = 'mob-historico';
    const desenharHistorico = () => {
        for (const b of filtro.querySelectorAll('button')) b.setAttribute('aria-pressed', String((b.dataset.periodo === 'mes') === soDoMes));
        const itens = soDoMes ? h.abastecimentos.filter((a) => String(a.data_abastecimento).slice(0, 7) === estado.mes) : h.abastecimentos;
        caixa.replaceChildren(listaDeAbastecimentos(itens, soDoMes ? `Nenhum abastecimento em ${rotuloCompetencia(estado.mes)}.` : 'Nenhum abastecimento registrado.'));
    };
    for (const [periodo, rotulo] of [['todos', 'Todos'], ['mes', rotuloCompetencia(estado.mes)]]) {
        const b = el('button', null, rotulo);
        b.type = 'button';
        b.dataset.periodo = periodo;
        b.addEventListener('click', () => { soDoMes = periodo === 'mes'; desenharHistorico(); });
        filtro.append(b);
    }
    desenharHistorico();
    abrirFolha(`Histórico · ${v.nome}`, ...(h.erro ? [texto(h.erro, 'discreto')] : []), filtro, caixa,
        texto('Correção e anulação de abastecimento são feitas na Mobilidade, no desktop.', 'discreto'), fecharBotao());
}

// Barras do gasto mensal, leves (SVG sem biblioteca).
function grafico(meses) {
    const maior = Math.max(...meses.map((m) => m.valor), 1);
    const [largura, altura, base] = [300, 96, 74];
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', `0 0 ${largura} ${altura}`);
    svg.setAttribute('class', 'mob-grafico');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `Gasto com abastecimento por mês: ${meses.map((m) => `${rotuloCompetencia(m.mes)} ${moeda(m.valor)}`).join(', ')}`);
    const passo = largura / meses.length;
    meses.forEach((m, i) => {
        const h = Math.round((m.valor / maior) * (base - 14));
        const barra = document.createElementNS(SVG, 'rect');
        barra.setAttribute('x', String(i * passo + passo * 0.22));
        barra.setAttribute('y', String(base - Math.max(h, m.valor > 0 ? 2 : 0)));
        barra.setAttribute('width', String(passo * 0.56));
        barra.setAttribute('height', String(Math.max(h, m.valor > 0 ? 2 : 0)));
        barra.setAttribute('rx', '3');
        barra.setAttribute('class', i === meses.length - 1 ? 'mob-grafico-barra atual' : 'mob-grafico-barra');
        const rotulo = document.createElementNS(SVG, 'text');
        rotulo.setAttribute('x', String(i * passo + passo / 2));
        rotulo.setAttribute('y', String(altura - 6));
        rotulo.setAttribute('text-anchor', 'middle');
        rotulo.setAttribute('class', 'mob-grafico-rotulo');
        rotulo.textContent = rotuloCompetencia(m.mes).slice(0, 3);
        svg.append(barra, rotulo);
    });
    return svg;
}

async function abrirResumo(v) {
    const h = await historico(v.id);
    const todos = validos(h.abastecimentos);
    const mes = doMes(h.abastecimentos, estado.mes);
    const ind = indicadores(h.abastecimentos);
    const ultimo = todos[0] || null;
    const q = textoDaQuilometragem(h.quilometragem || {});
    const corpo = detalhes([
        [`Gasto em ${rotuloCompetencia(estado.mes)}`, `${moeda(soma(mes, 'valor_total'))} (${mes.length} abastecimento${mes.length === 1 ? '' : 's'}, ${litros(soma(mes, 'litros'))})`],
        ['Consumo médio (estimado)', ind.consumo === null ? 'Sem dados suficientes' : `≈ ${numero(ind.consumo, 1)} km/L`],
        ['Custo por km (combustível)', ind.custoKm === null ? 'Sem dados suficientes' : `${Number(ind.custoKm).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}/km`],
        ['Quilometragem', `${q.valor} (${q.nota})`],
        ['Último abastecimento', ultimo ? `${dataCurta(ultimo.data_abastecimento)} · ${moeda(ultimo.valor_total)} · ${litros(ultimo.litros)}` : 'Nenhum'],
    ]);
    corpo.id = 'mob-resumo-veiculo';
    const titulo = el('h3', 'mob-mob-subtitulo', 'Gasto por mês');
    const ultimos = el('h3', 'mob-mob-subtitulo', 'Últimos abastecimentos');
    const caixaUltimos = el('div');
    caixaUltimos.id = 'mob-resumo-ultimos';
    caixaUltimos.append(listaDeAbastecimentos(todos.slice(0, 5), 'Nenhum abastecimento registrado.'));
    abrirFolha(`Resumo · ${v.nome}`, ...(h.erro ? [texto(h.erro, 'discreto')] : []), corpo, titulo, grafico(gastoPorMes(h.abastecimentos, estado.mes)), ultimos, caixaUltimos,
        notaDosIndicadores(ind), fecharBotao());
}

// O que cada indicador significa e de onde vem (o consumo e estimativa; o custo por km e o gasto pelos km rodados).
function notaDosIndicadores(ind) {
    const nota = texto(ind.leituras
        ? `Consumo estimado: km rodados entre as leituras de hodômetro ÷ litros de ${ind.leituras} abastecimento${ind.leituras === 1 ? '' : 's'}. `
            + 'É uma estimativa: supõe o tanque completado a cada abastecimento, o que não é registrado. '
            + 'Custo por km: valor pago nesses abastecimentos ÷ km rodados. Abastecimento sem leitura anterior de hodômetro não entra na conta.'
        : 'Consumo e custo por km aparecem a partir do segundo abastecimento com hodômetro (precisam dos km rodados entre duas leituras).', 'discreto');
    nota.id = 'mob-resumo-nota';
    return nota;
}

function trocarMes(delta) {
    estado.mes = deslocarMes(estado.mes, delta);
    desenhar();
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
        perfil = escolherPerfilAtivo(await carregarPerfis(), usuario.id);
        if (perfil) salvarPerfilAtivo(usuario.id, perfil.id);
    } catch (_erro) {
        mostrarAviso('Não foi possível carregar os perfis financeiros.', 'erro');
    }
    if (perfil) {
        $('mob-perfil').textContent = perfil.nome || '';
        configurarMobilidade(perfil.id);
        estado.somenteLeitura = !(await podeGerirPerfil(perfil.id).catch(() => false));
        $('mob-somente-leitura').hidden = !estado.somenteLeitura;
        if (estado.somenteLeitura) ajustarCadastrosPelaPermissao(usuario.id);
        const r = await api('GET', '/api/veiculos');
        if (!r.success) mostrarAviso(r.error || 'Não foi possível carregar os veículos.', 'erro');
        estado.veiculos = r.success ? (r.data || []) : [];
        // "+" do cabecalho: novo abastecimento sem veiculo escolhido (o formulario pede o veiculo); so para quem gere.
        const novo = $('mob-abastecer');
        novo.hidden = estado.somenteLeitura || !estado.veiculos.length;
        novo.addEventListener('click', () => { window.location.href = `lancamento-mobile.html?mes=${estado.mes}&tipo=abastecimento&retorno=mobilidade`; });
        $('mob-mes-anterior').addEventListener('click', () => trocarMes(-1));
        $('mob-mes-seguinte').addEventListener('click', () => trocarMes(1));
        await desenhar();
    } else {
        if ($('mob-aviso').hidden) mostrarAviso('Nenhum perfil financeiro autorizado para esta conta.', 'erro');
        $('mob-lista').setAttribute('aria-busy', 'false');
    }
}
