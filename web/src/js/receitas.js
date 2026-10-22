// FIN-RECEITAS-1 — Receitas do mes (previstas), por perfil.
//
// Consulta: financeiro.receitas_do_mes (situacao derivada dos registros reais, como a tela de
// receitas do Flask), fontes_de_receita, receita_para_edicao (permissoes calculadas no banco).
// Escrita so por RPC (criar_receita, editar_receita, excluir_receita, editar_fonte_receita,
// inativar_fonte_receita): previsao nunca e recebimento — nada aqui movimenta conta bancaria.
// Nao ha botao de recebimento: esse modulo ainda nao existe no novo aplicativo.

import { supabase } from './cliente.js';
import {
    MES_VALIDO, botao, campo, centavos, competenciaCurta, dataCurta, deslocarMes, el, entrada, formatarValor,
    linhaDetalhe, mesAtualBrasilia, normalizarValor, reais, seletor, tituloDoMes,
} from './comum.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario, sair } from './sessao.js';

const TIPOS = [
    ['SALARIO_FIXO', 'Salário'], ['GRATIFICACAO', 'Gratificação'], ['RENDA_EXTRA', 'Renda extra'],
    ['ALUGUEL', 'Aluguel'], ['RENDIMENTO_FINANCEIRO', 'Rendimento financeiro'], ['OUTROS', 'Outros'],
];
const NOME_TIPO = Object.fromEntries([...TIPOS, ['PONTUAL', 'Pontual']]);
const SITUACAO = {
    PREVISTA: 'Prevista', PARCIAL: 'Parcial', RECEBIDA: 'Recebida', INATIVA: 'Fonte inativa',
    REMOVIDA: 'Removida', ESTORNADA: 'Estornada', PREVISTA_CONSORCIO: 'Prevista (consórcio)',
};
const BLOQUEIOS = {
    'Ha recebimento registrado nesta competencia': 'Há recebimento registrado nesta competência: a previsão fica preservada.',
    'Gerada pelo modulo de consorcios': 'Gerada pelo módulo de consórcios.',
};
const textoBloqueio = (motivo) => BLOQUEIOS[motivo] || `${motivo}.`;

function mensagemDeErro(error) {
    const texto = (error && error.message) || '';
    if (/alterad[ao] por outra operacao/i.test(texto)) return 'A receita foi alterada por outra operação. Recarregue e tente de novo.';
    if (/nao autorizado|nao encontrada neste perfil/i.test(texto)) return 'Operação não autorizada para este perfil.';
    if (/Operacao bloqueada: /i.test(texto)) return `Operação bloqueada: ${textoBloqueio(texto.replace(/^.*Operacao bloqueada: /i, ''))}`;
    if (texto && error.code && /^(22023|P0001)$/.test(error.code)) return texto;
    return 'Não foi possível concluir a operação. Nada foi gravado.';
}

const cache = new Map();
async function contasBancarias(perfilId) {
    if (!cache.has(perfilId)) {
        const { data, error } = await supabase.rpc('contas_bancarias_do_perfil', { p_perfil_id: perfilId });
        cache.set(perfilId, error ? [] : (data || []).filter((c) => c.status === 'ATIVO'));
    }
    return cache.get(perfilId);
}

function formulario(titulo) {
    const painel = document.getElementById('receita-painel');
    painel.replaceChildren();
    painel.hidden = false;
    const form = el('form', 'despesa-form');
    form.noValidate = true;
    form.append(el('h2', 'geracao-titulo', titulo));
    const erro = el('p', 'login-error');
    erro.setAttribute('role', 'alert');
    erro.hidden = true;
    const salvar = botao('Salvar', 'botao-principal');
    salvar.type = 'submit';
    const cancelar = botao('Cancelar');
    const botoes = el('div', 'geracao-botoes');
    botoes.append(salvar, cancelar);
    cancelar.addEventListener('click', () => { painel.replaceChildren(); painel.hidden = true; });
    const fechar = () => { painel.replaceChildren(); painel.hidden = true; };
    const falhar = (texto) => {
        erro.textContent = texto;
        erro.hidden = false;
        salvar.disabled = false;
        cancelar.disabled = false;
    };
    return { painel, form, erro, salvar, cancelar, botoes, fechar, falhar };
}

async function abrirNovaReceita(contexto) {
    const { data: fontes } = await supabase.rpc('fontes_de_receita', { p_perfil_id: contexto.perfilId });
    const disponiveis = (fontes || []).filter((f) => f.ativo && !f.de_outro_modulo);
    const contas = await contasBancarias(contexto.perfilId);
    const f = formulario('Nova receita prevista');

    const fonte = seletor([['nova', 'Nova fonte'], ...disponiveis.map((x) => [x.id, x.nome])], 'nova');
    const nome = entrada('text');
    nome.maxLength = 100;
    const tipo = seletor([['', 'Selecione'], ...TIPOS], '');
    const recorrencia = seletor([['avulsa', 'Avulsa (só nesta competência)'], ['mensal', 'Mensal (próximos 12 meses)']], 'avulsa');
    const conta = seletor([['', 'Sem conta definida'], ...contas.map((c) => [c.id, c.nome])], '');
    const valor = entrada('text');
    valor.inputMode = 'decimal';
    valor.placeholder = '0,00';
    const competencia = entrada('month', contexto.mes);
    // Competencia = mes do orcamento; data prevista = quando se espera receber (pode cair em outro mes).
    const dataPrevista = entrada('date');
    const dicaData = el('p', 'geracao-dica', 'Opcional. Pode cair em outro mês (ex.: competência 10, recebimento em 05/11). '
        + 'Na recorrência, define o dia e a defasagem de todas as competências.');
    const observacoes = el('textarea');
    observacoes.rows = 2;
    observacoes.maxLength = 1000;

    const novaFonte = el('div', 'form-grupo');
    novaFonte.append(campo('Nome da fonte', nome, 'receita-nome'), campo('Categoria', tipo, 'receita-tipo'),
        campo('Recorrência', recorrencia, 'receita-recorrencia'), campo('Conta de destino', conta, 'receita-conta'));
    fonte.addEventListener('change', () => { novaFonte.hidden = fonte.value !== 'nova'; });
    f.form.append(campo('Fonte', fonte, 'receita-fonte'), novaFonte, campo('Valor previsto (R$)', valor, 'receita-valor'),
        campo('Competência', competencia, 'receita-competencia'), campo('Data prevista', dataPrevista, 'receita-data'),
        dicaData, campo('Observações', observacoes, 'receita-observacoes'), f.erro, f.botoes);
    f.painel.append(f.form);

    const chave = crypto.randomUUID();
    f.form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        f.erro.hidden = true;
        const nova = fonte.value === 'nova';
        const valorNormal = normalizarValor(valor.value);
        const problemas = [];
        if (nova && !nome.value.trim()) problemas.push('informe o nome da fonte');
        if (nova && !tipo.value) problemas.push('escolha a categoria');
        if (!valorNormal || Number(valorNormal) <= 0) problemas.push('informe um valor válido');
        if (!competencia.value) problemas.push('informe a competência');
        if (problemas.length) {
            f.falhar(`Verifique: ${problemas.join(', ')}.`);
            return;
        }
        const dados = { valor: valorNormal, competencia: `${competencia.value}-01` };
        if (dataPrevista.value) dados.data_prevista = dataPrevista.value;
        if (nova) {
            Object.assign(dados, {
                nome: nome.value.trim(), tipo: tipo.value, recorrente: recorrencia.value === 'mensal',
                conta_bancaria_id: conta.value ? Number(conta.value) : null,
            });
            if (recorrencia.value === 'mensal') dados.descricao = observacoes.value.trim();
            else dados.observacoes = observacoes.value.trim();
        } else {
            Object.assign(dados, { item_receita_id: Number(fonte.value), observacoes: observacoes.value.trim() });
        }
        f.salvar.disabled = true;
        f.cancelar.disabled = true;
        const { data, error } = await supabase.rpc('criar_receita', { p_perfil_id: contexto.perfilId, p_dados: dados, p_chave: chave });
        if (error) {
            f.falhar(mensagemDeErro(error));
            return;
        }
        f.fechar();
        await contexto.recarregar(data.recorrente
            ? `Receita prevista cadastrada: ${data.previsoes.length} competências a partir de ${competenciaCurta(data.competencia)}.`
            : `Receita prevista cadastrada na competência ${competenciaCurta(data.competencia)}.`);
    });
}

function abrirEdicaoPrevisao(contexto, dados) {
    const f = formulario('Editar receita prevista');
    const valor = entrada('text', formatarValor(dados.previsao.valor));
    valor.inputMode = 'decimal';
    const competencia = entrada('month', dados.previsao.competencia.slice(0, 7));
    competencia.disabled = !dados.pode_mudar_competencia;
    const dataPrevista = entrada('date', dados.previsao.data_prevista || '');
    const dicaData = el('p', 'geracao-dica', 'Só desta competência. Vazio: usa o dia previsto da fonte.');
    const observacoes = el('textarea');
    observacoes.rows = 2;
    observacoes.maxLength = 1000;
    observacoes.value = dados.previsao.observacoes || '';
    f.form.append(campo('Valor previsto (R$)', valor, 'receita-valor'), campo('Competência', competencia, 'receita-competencia'),
        campo('Data prevista', dataPrevista, 'receita-data'), dicaData,
        campo('Observações', observacoes, 'receita-observacoes'), f.erro, f.botoes);
    f.painel.append(f.form);
    f.form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        const valorNormal = normalizarValor(valor.value);
        if (!valorNormal || Number(valorNormal) <= 0) {
            f.falhar('Verifique: informe um valor válido.');
            return;
        }
        const alteracao = { valor: valorNormal, observacoes: observacoes.value.trim(), data_prevista: dataPrevista.value || null };
        if (!competencia.disabled) alteracao.competencia = `${competencia.value}-01`;
        f.salvar.disabled = true;
        f.cancelar.disabled = true;
        const { data, error } = await supabase.rpc('editar_receita', {
            p_perfil_id: contexto.perfilId, p_orcamento_id: dados.previsao.id, p_versao: dados.versao, p_dados: alteracao,
        });
        if (error) {
            f.falhar(mensagemDeErro(error));
            return;
        }
        f.fechar();
        await contexto.recarregar(`Receita prevista salva na competência ${competenciaCurta(data.competencia)}.`);
    });
}

async function abrirEdicaoFonte(contexto, dados) {
    const contas = await contasBancarias(contexto.perfilId);
    const f = formulario('Editar fonte de receita');
    const nome = entrada('text', dados.fonte.nome);
    nome.maxLength = 100;
    const tipo = seletor(TIPOS, dados.fonte.tipo);
    const dia = entrada('number', dados.fonte.dia_previsto);
    dia.min = '1';
    dia.max = '31';
    const conta = seletor([['', 'Sem conta definida'], ...contas.map((c) => [c.id, c.nome])], dados.fonte.conta_bancaria_id || '');
    const descricao = el('textarea');
    descricao.rows = 2;
    descricao.maxLength = 1000;
    descricao.value = dados.fonte.descricao || '';
    f.form.append(campo('Nome da fonte', nome, 'fonte-nome'), campo('Categoria', tipo, 'fonte-tipo'),
        campo('Dia previsto (1 a 31)', dia, 'fonte-dia'), campo('Conta de destino', conta, 'fonte-conta'),
        campo('Descrição', descricao, 'fonte-descricao'), f.erro, f.botoes);
    f.painel.append(f.form);
    f.form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        if (!nome.value.trim()) {
            f.falhar('Verifique: informe o nome da fonte.');
            return;
        }
        f.salvar.disabled = true;
        f.cancelar.disabled = true;
        const { error } = await supabase.rpc('editar_fonte_receita', {
            p_perfil_id: contexto.perfilId, p_item_id: dados.fonte.id, p_versao: dados.versao_fonte,
            p_dados: {
                nome: nome.value.trim(), tipo: tipo.value, dia_previsto: dia.value ? Number(dia.value) : null,
                conta_bancaria_id: conta.value ? Number(conta.value) : null, descricao: descricao.value.trim(),
            },
        });
        if (error) {
            f.falhar(mensagemDeErro(error));
            return;
        }
        f.fechar();
        await contexto.recarregar('Fonte atualizada. Previsões e recebimentos registrados não mudam.');
    });
}

function confirmarAcao(area, pergunta, rotulo, executar) {
    area.replaceChildren();
    const confirmar = botao(rotulo, 'botao-perigo');
    const cancelar = botao('Cancelar');
    const erro = el('p', 'login-error');
    erro.setAttribute('role', 'alert');
    erro.hidden = true;
    const botoes = el('div', 'geracao-botoes');
    botoes.append(confirmar, cancelar);
    area.append(el('p', 'despesa-pergunta', pergunta), erro, botoes);
    cancelar.addEventListener('click', () => area.replaceChildren());
    confirmar.addEventListener('click', async () => {
        confirmar.disabled = true;
        cancelar.disabled = true;
        const { error } = await executar();
        if (error) {
            erro.textContent = mensagemDeErro(error);
            erro.hidden = false;
            cancelar.disabled = false;
        }
    });
}

async function carregarAcoes(caixa, orcamentoId, contexto) {
    const { data, error } = await supabase.rpc('receita_para_edicao', { p_perfil_id: contexto.perfilId, p_orcamento_id: orcamentoId });
    if (error || !data || !data.pode_gerir) return;
    if (data.bloqueio) caixa.append(el('p', 'despesa-bloqueio', textoBloqueio(data.bloqueio)));
    const acoes = el('div', 'despesa-acoes');
    const confirmacao = el('div', 'despesa-confirmacao');
    if (data.pode_editar) {
        const editar = botao('Editar');
        editar.addEventListener('click', () => abrirEdicaoPrevisao(contexto, data));
        acoes.append(editar);
    }
    if (data.pode_excluir) {
        const excluir = botao('Excluir');
        excluir.addEventListener('click', () => confirmarAcao(confirmacao,
            data.fonte.recorrente
                ? 'Remover a previsão desta competência? A fonte continua; nada foi recebido.'
                : 'Excluir esta receita prevista? Nada foi recebido.',
            'Confirmar exclusão',
            async () => {
                const resposta = await supabase.rpc('excluir_receita', {
                    p_perfil_id: contexto.perfilId, p_orcamento_id: orcamentoId, p_versao: data.versao,
                });
                if (!resposta.error) await contexto.recarregar('Receita prevista excluída.');
                return resposta;
            }));
        acoes.append(excluir);
    }
    if (data.pode_editar_fonte) {
        const editarFonte = botao('Editar fonte');
        editarFonte.addEventListener('click', () => abrirEdicaoFonte(contexto, data));
        acoes.append(editarFonte);
    }
    if (data.pode_inativar_fonte) {
        const inativar = botao('Inativar fonte');
        inativar.addEventListener('click', () => confirmarAcao(confirmacao,
            'Inativar a fonte? Previsões e recebimentos registrados continuam; ela deixa de ser oferecida no cadastro.',
            'Confirmar inativação',
            async () => {
                const resposta = await supabase.rpc('inativar_fonte_receita', {
                    p_perfil_id: contexto.perfilId, p_item_id: data.fonte.id, p_versao: data.versao_fonte,
                });
                if (!resposta.error) await contexto.recarregar('Fonte inativada.');
                return resposta;
            }));
        acoes.append(inativar);
    }
    if (acoes.childElementCount) caixa.append(acoes, confirmacao);
}

function itemReceita(receita, contexto) {
    const item = el('li', 'conta');
    item.dataset.receitaId = `${receita.origem}-${receita.id}`;
    const detalhe = el('details');
    const resumo = el('summary', 'conta-resumo');
    const principal = el('span', 'conta-principal');
    const quando = receita.origem === 'RECEBIMENTO' ? 'Recebida em' : 'Prevista para';
    let textoData = receita.data_prevista ? `${quando} ${dataCurta(receita.data_prevista)}` : 'Sem data prevista';
    if (receita.data_prevista && receita.data_prevista.slice(0, 7) !== receita.competencia.slice(0, 7)) {
        textoData += ` · competência ${competenciaCurta(receita.competencia)}`;  // recebimento em outro mes
    }
    principal.append(el('span', 'conta-nome', receita.nome), el('span', 'conta-vencimento', textoData));
    const lado = el('span', 'conta-lado');
    const valor = receita.valor_previsto !== null && receita.valor_previsto !== undefined ? receita.valor_previsto : receita.valor_recebido;
    lado.append(el('span', 'conta-valor', reais(centavos(valor))),
        el('span', `situacao situacao-receita-${receita.situacao.toLowerCase()}`, SITUACAO[receita.situacao] || receita.situacao));
    resumo.append(principal, lado);
    const lista = el('dl', 'conta-detalhe');
    linhaDetalhe(lista, 'Categoria', NOME_TIPO[receita.tipo] || receita.tipo);
    linhaDetalhe(lista, 'Competência', competenciaCurta(receita.competencia));
    if (receita.valor_previsto !== null && receita.valor_previsto !== undefined) linhaDetalhe(lista, 'Previsto', reais(centavos(receita.valor_previsto)));
    linhaDetalhe(lista, 'Recebido', reais(centavos(receita.valor_recebido)));
    linhaDetalhe(lista, 'Conta', receita.conta_bancaria_nome);
    if (receita.recorrente && receita.origem === 'PREVISAO') linhaDetalhe(lista, 'Fonte', 'Recorrente');
    const caixa = el('div', 'despesa-caixa');
    detalhe.append(resumo, lista, caixa);
    if (receita.origem === 'PREVISAO') {
        let carregadas = false;
        detalhe.addEventListener('toggle', () => {
            if (!detalhe.open || carregadas) return;
            carregadas = true;
            carregarAcoes(caixa, receita.id, contexto);
        });
    }
    item.append(detalhe);
    return item;
}

function limpar() {
    for (const id of ['totais', 'receitas-nota', 'receitas-erro', 'receitas-vazio', 'secao-receitas']) {
        document.getElementById(id).hidden = true;
    }
    document.getElementById('lista-receitas').replaceChildren();
}

async function carregarMes(perfilId, mes) {
    limpar();
    const [lista, gestao] = await Promise.all([
        supabase.rpc('receitas_do_mes', { p_perfil_id: perfilId, p_mes: `${mes}-01` }),
        supabase.rpc('pode_gerir_perfil', { p_perfil_id: perfilId }),
    ]);
    const contexto = {
        perfilId,
        mes,
        recarregar: async (mensagem) => {
            const aviso = document.getElementById('acao-resultado');
            aviso.textContent = mensagem;
            aviso.hidden = false;
            await carregarMes(perfilId, mes);
        },
    };
    const acoes = document.getElementById('acoes-mes');
    acoes.replaceChildren();
    document.getElementById('receita-painel').hidden = true;
    document.getElementById('receita-painel').replaceChildren();
    if (lista.error) {
        const erro = document.getElementById('receitas-erro');
        erro.textContent = 'Perfil não autorizado ou indisponível.';
        erro.hidden = false;
        return;
    }
    if (!gestao.error && gestao.data === true) {
        const nova = botao('Nova receita', 'botao-principal');
        nova.id = 'nova-receita';
        nova.addEventListener('click', () => abrirNovaReceita(contexto));
        acoes.append(nova);
    }
    const receitas = lista.data || [];
    // Totais em centavos: previsto sem removidas/inativas; recebido so o efetivamente recebido.
    const contaPrevisto = (r) => (r.origem === 'PREVISAO' && !['REMOVIDA', 'INATIVA'].includes(r.situacao))
        || r.situacao === 'PREVISTA_CONSORCIO';
    const previsto = receitas.filter(contaPrevisto).reduce((s, r) => s + centavos(r.valor_previsto), 0);
    const recebido = receitas.filter((r) => r.origem === 'PREVISAO' || r.situacao === 'RECEBIDA')
        .reduce((s, r) => s + centavos(r.valor_recebido), 0);
    const aReceber = receitas.filter(contaPrevisto)
        .reduce((s, r) => s + Math.max(0, centavos(r.valor_previsto) - centavos(r.valor_recebido)), 0);
    document.getElementById('total-previsto').textContent = reais(previsto);
    document.getElementById('total-recebido').textContent = reais(recebido);
    document.getElementById('total-a-receber').textContent = reais(aReceber);
    document.getElementById('totais').hidden = false;
    document.getElementById('receitas-nota').hidden = false;
    if (!receitas.length) {
        document.getElementById('receitas-vazio').hidden = false;
        return;
    }
    const destino = document.getElementById('lista-receitas');
    for (const receita of receitas) destino.append(itemReceita(receita, contexto));
    document.getElementById('secao-receitas').hidden = false;
}

const parametro = new URLSearchParams(window.location.search).get('mes');
const mes = MES_VALIDO.test(parametro || '') ? parametro : mesAtualBrasilia();
document.getElementById('mes-titulo').textContent = tituloDoMes(mes);
document.getElementById('mes-anterior').href = `receitas.html?mes=${deslocarMes(mes, -1)}`;
document.getElementById('mes-proximo').href = `receitas.html?mes=${deslocarMes(mes, 1)}`;
document.getElementById('aba-contas').href = `contas.html?mes=${mes}`;
document.getElementById('aba-receitas').href = `receitas.html?mes=${mes}`;

const usuario = await exigirUsuario();
if (usuario) {
    document.getElementById('usuario-email').textContent = usuario.email || '';
    document.getElementById('sair').addEventListener('click', sair);
    let perfis = [];
    try {
        perfis = await carregarPerfis();
    } catch (_erro) {
        const erro = document.getElementById('perfis-erro');
        erro.textContent = 'Não foi possível carregar os perfis financeiros.';
        erro.hidden = false;
    }
    if (!perfis.length) {
        document.getElementById('perfis-vazio').hidden = !document.getElementById('perfis-erro').hidden;
    } else {
        const seletorPerfil = document.getElementById('perfil-ativo');
        for (const perfil of perfis) {
            const opcao = el('option', null, perfil.nome);
            opcao.value = String(perfil.id);
            seletorPerfil.append(opcao);
        }
        const ativo = escolherPerfilAtivo(perfis, usuario.id);
        seletorPerfil.value = String(ativo.id);
        document.getElementById('perfil-rotulo').hidden = false;
        seletorPerfil.addEventListener('change', async () => {
            salvarPerfilAtivo(usuario.id, seletorPerfil.value);
            document.getElementById('acao-resultado').hidden = true;
            await carregarMes(Number(seletorPerfil.value), mes);
        });
        await carregarMes(ativo.id, mes);
    }
}
