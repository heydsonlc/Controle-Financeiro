// Configuracoes e Preferencias — secao Perfis Financeiros (FIN-MIGRACAO-FIDELIDADE-FASE-1).
//
// Porta frontend/static/js/configuracoes.js (perfis, troca de secao e ajuda contextual) sobre as
// funcoes do banco de perfil.js. Mesmo fluxo do Flask ao salvar: dados do perfil, depois ativar ou
// inativar, depois padrao. O banco exige gestao explicita do perfil (pode_gerir) em cada chamada;
// perfis "somente leitura" aparecem, mas o formulario fica bloqueado. Elementos criados por DOM, sem innerHTML.
// FIN-PRE-PRODUCAO-1: Preferencias Gerais, Aparencia, Comportamento e IA (migration 20261201090000): as financeiras e
// operacionais sao do perfil em uso (so quem o gere altera), as de interface sao da conta do usuario (todos os perfis).
// Cada secao salva os seus campos, como o Flask. Backup e OCR continuam fora (avisos na propria secao).

import { supabase } from './cliente.js';
import { atualizarPerfis, definirCor, iniciarMoldura, usarPerfil } from './moldura.js';
import {
    atualizarPerfil, criarPerfil, definirPerfilPadrao, inativarPerfil, perfisParaConfiguracao, reativarPerfil,
} from './perfil.js';

const $ = (id) => document.getElementById(id);
const state = { perfis: [], ativo: null, selecionado: null, secao: 'perfis-financeiros' };

const ajuda = {
    'perfis-financeiros': {
        titulo: 'Como funciona o contexto financeiro',
        itens: [
            ['Perfis independentes', 'Cada perfil possui dados, configurações e relatórios separados.'],
            ['Troca rápida', 'Alterne entre perfis pelo seletor no topo sem sair da aplicação.'],
            ['Personalização total', 'Defina preferências e comportamentos específicos para cada perfil.'],
            ['Dica', 'Crie perfis para separar suas finanças pessoais das da empresa.'],
        ],
    },
    'preferencias-gerais': {
        titulo: 'Preferências gerais',
        itens: [
            ['Da sua conta', 'O nome vale em todos os seus perfis.'],
            ['Deste perfil', 'Renda, início do planejamento e fechamento são de cada perfil; só quem gere o perfil altera.'],
        ],
    },
    aparencia: {
        titulo: 'Aparência',
        itens: [['Da sua conta', 'Tema, cor, ícones e abreviação valem em todos os seus perfis.']],
    },
    comportamento: {
        titulo: 'Comportamento',
        itens: [
            ['Deste perfil', 'Competência automática, aviso de vencida e vínculo do pagamento de cartão.'],
            ['Da sua conta', 'A confirmação de exclusões.'],
        ],
    },
    backup: {
        titulo: 'Backup',
        itens: [['Em migração', 'O novo aplicativo usa o backup próprio do banco (Supabase).']],
    },
    'ia-automacao': {
        titulo: 'IA e Automação',
        itens: [
            ['Da sua conta', 'Modo inteligente e sugestões de economia.'],
            ['Deste perfil', 'Classificação automática e correção de categorias.'],
            ['OCR', 'A leitura de imagens continua no sistema atual.'],
        ],
    },
    'documentos-fiscais': {
        titulo: 'Documentos fiscais por perfil',
        itens: [
            ['Pessoal', 'O perfil pessoal usa Imposto de Renda e comprovantes potencialmente dedutíveis.'],
            ['Empresa', 'O perfil empresa usa Documentos Fiscais e Lastro Empresarial.'],
            ['Revisão fiscal', 'Classificações seguem informativas e sujeitas à validação contábil.'],
        ],
    },
};

function iniciaisDe(perfil) {
    if (perfil?.avatar) return String(perfil.avatar).slice(0, 3).toUpperCase();
    const partes = String(perfil?.nome || 'PF').trim().split(/\s+/).filter(Boolean);
    if (!partes.length) return 'PF';
    if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
    return `${partes[0][0]}${partes[1][0]}`.toUpperCase();
}

function tipoLabel(tipo) {
    const valor = String(tipo || '').toUpperCase();
    if (valor === 'PESSOAL') return 'Pessoal';
    if (valor === 'EMPRESA') return 'Empresa';
    return 'Outro';
}

function mostrarMensagem(mensagem, tipo = 'info') {
    const alerta = $('config-profile-alert');
    alerta.textContent = mensagem || '';
    alerta.dataset.tipo = tipo;
    alerta.hidden = !mensagem;
}

const mesmoId = (a, b) => a !== null && a !== undefined && b !== null && b !== undefined && String(a) === String(b);

function criarEl(tag, classe, texto) {
    const elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto !== undefined) elemento.textContent = texto;
    return elemento;
}

function cartaoDePerfil(perfil) {
    const selecionado = mesmoId(state.selecionado?.id, perfil.id);
    const emUso = mesmoId(state.ativo?.id, perfil.id);
    const cartao = criarEl('button', `config-profile-card${selecionado ? ' active' : ''}`);
    cartao.type = 'button';
    cartao.dataset.profileId = String(perfil.id);
    const avatar = criarEl('span', 'config-profile-avatar', iniciaisDe(perfil));
    definirCor(avatar, '--profile-color', perfil.cor);
    const principal = criarEl('span', 'config-profile-main');
    principal.append(criarEl('strong', null, perfil.nome),
        criarEl('small', null, `${tipoLabel(perfil.tipo)}${perfil.documento ? ` · ${perfil.documento}` : ''}`));
    const selos = criarEl('span', 'config-profile-badges');
    const status = perfil.ativo ? (emUso ? ['active', 'Ativo'] : ['available', 'Disponível']) : ['inactive', 'Inativo'];
    selos.append(criarEl('span', `config-profile-badge ${status[0]}`, status[1]));
    if (perfil.padrao) selos.append(criarEl('span', 'config-profile-badge default', 'Padrão'));
    if (emUso) selos.append(criarEl('span', 'config-profile-badge current', 'Perfil em uso'));
    if (!perfil.pode_gerir) selos.append(criarEl('span', 'config-profile-badge', 'Somente leitura'));
    principal.append(selos);
    const seta = criarEl('span', null, '›');
    seta.setAttribute('aria-hidden', 'true');
    cartao.append(avatar, principal, seta);
    return cartao;
}

function renderPerfis() {
    const destino = $('config-profiles-list');
    const novo = criarEl('button', 'config-profile-new-card');
    novo.type = 'button';
    novo.id = 'config-profile-card-new';
    const mais = criarEl('span', 'config-profile-plus', '+');
    mais.setAttribute('aria-hidden', 'true');
    const texto = criarEl('span', 'config-profile-main');
    texto.append(criarEl('strong', null, 'Novo perfil'), criarEl('small', null, 'Crie um novo perfil financeiro'));
    novo.append(mais, texto);
    if (!state.perfis.length) {
        destino.replaceChildren(criarEl('div', 'config-empty-state',
            'Nenhum perfil financeiro cadastrado. Crie um perfil para começar a organizar seus dados por contexto.'), novo);
        return;
    }
    destino.replaceChildren(...state.perfis.map(cartaoDePerfil), novo);
}

function atualizarChecksConceituais() {
    const tipo = String($('config-profile-tipo').value || '').toUpperCase();
    const ativo = $('config-profile-ativo').checked;
    $('config-profile-irpf').checked = tipo !== 'EMPRESA';
    $('config-profile-docs').checked = tipo === 'EMPRESA';
    $('config-profile-topbar').checked = Boolean(ativo);
    $('config-profile-switch').checked = Boolean(ativo);
}

const CAMPOS = ['config-profile-nome', 'config-profile-tipo', 'config-profile-avatar', 'config-profile-documento',
    'config-profile-cor', 'config-profile-ativo', 'config-profile-padrao', 'config-profile-save'];

function preencherFormularioPerfil(perfil) {
    $('config-profile-id').value = perfil?.id || '';
    $('config-profile-nome').value = perfil?.nome || '';
    $('config-profile-tipo').value = perfil?.tipo || 'PESSOAL';
    $('config-profile-avatar').value = perfil?.avatar || '';
    $('config-profile-documento').value = perfil?.documento || '';
    $('config-profile-cor').value = /^#[0-9A-Fa-f]{6}$/.test(perfil?.cor || '') ? perfil.cor : '#2563eb';
    $('config-profile-ativo').checked = perfil ? Boolean(perfil.ativo) : true;
    $('config-profile-padrao').checked = perfil ? Boolean(perfil.padrao) : false;
    // Perfil so de leitura: visivel, mas nada pode ser alterado (o banco tambem recusa).
    const bloqueado = Boolean(perfil) && !perfil.pode_gerir;
    for (const id of CAMPOS) $(id).disabled = bloqueado;
    $('config-profile-use').disabled = !perfil || !perfil.ativo || mesmoId(perfil.id, state.ativo?.id);
    atualizarChecksConceituais();
    if (bloqueado) mostrarMensagem('Você tem acesso somente de leitura a este perfil: os dados não podem ser alterados.');
}

async function carregarPerfis() {
    state.perfis = await perfisParaConfiguracao();
    const selecionado = state.perfis.find((perfil) => mesmoId(perfil.id, state.selecionado?.id));
    state.selecionado = selecionado
        || state.perfis.find((perfil) => mesmoId(perfil.id, state.ativo?.id))
        || state.perfis[0]
        || null;
    renderPerfis();
    preencherFormularioPerfil(state.selecionado);
}

function novoPerfil() {
    state.selecionado = null;
    renderPerfis();
    preencherFormularioPerfil(null);
    mostrarMensagem('Novo perfil em edição. Preencha os dados e salve para criar.', 'info');
    $('config-profile-nome').focus();
}

function payloadPerfilBase() {
    return {
        nome: $('config-profile-nome').value.trim(),
        tipo: $('config-profile-tipo').value,
        documento: $('config-profile-documento').value.trim(),
        cor: $('config-profile-cor').value || '#2563eb',
        avatar: $('config-profile-avatar').value.trim(),
    };
}

// FIN-ESCRITOR-UNICO-FINAL-1: os dados do perfil so sao gravados se mudaram. Tornar padrao e preferencia do usuario
// (definir_perfil_padrao) e vale tambem para perfil ainda administrado pelo Flask, cujos dados o novo aplicativo nao grava.
function dadosDoPerfilMudaram(perfil, dados) {
    const texto = (valor) => String(valor ?? '').trim();
    return texto(perfil.nome) !== dados.nome || texto(perfil.tipo) !== dados.tipo
        || texto(perfil.documento) !== dados.documento || texto(perfil.cor).toLowerCase() !== dados.cor.toLowerCase()
        || texto(perfil.avatar).toUpperCase() !== dados.avatar.toUpperCase();
}

async function salvarPerfil() {
    mostrarMensagem('');
    const id = $('config-profile-id').value;
    const desejaAtivo = $('config-profile-ativo').checked;
    const desejaPadrao = $('config-profile-padrao').checked;
    const perfilAntes = id ? state.perfis.find((perfil) => mesmoId(perfil.id, id)) : null;
    if (!payloadPerfilBase().nome) {
        mostrarMensagem('Nome do perfil financeiro e obrigatorio');
        return;
    }
    // Regra do Flask que depende do perfil em uso (escolha do navegador): conferida antes de gravar.
    if (perfilAntes?.ativo && !desejaAtivo && mesmoId(id, state.ativo?.id)) {
        mostrarMensagem('Selecione outro perfil antes de inativar o perfil ativo');
        return;
    }

    const botao = $('config-profile-save');
    botao.disabled = true;
    try {
        let perfilSalvo;
        if (perfilAntes) {
            perfilSalvo = dadosDoPerfilMudaram(perfilAntes, payloadPerfilBase())
                ? await atualizarPerfil(perfilAntes.id, payloadPerfilBase()) : perfilAntes;
            if (perfilAntes.ativo && !desejaAtivo) {
                perfilSalvo = await inativarPerfil(perfilAntes.id);
            } else if (!perfilAntes.ativo && desejaAtivo) {
                perfilSalvo = await reativarPerfil(perfilAntes.id);
            }
        } else {
            perfilSalvo = await criarPerfil({ ...payloadPerfilBase(), ativo: desejaAtivo, padrao: desejaPadrao });
        }
        if (desejaPadrao && desejaAtivo && perfilSalvo?.id && !perfilSalvo.padrao) {
            perfilSalvo = await definirPerfilPadrao(perfilSalvo.id);
        }
        state.selecionado = perfilSalvo;
        state.ativo = await atualizarPerfis();  // seletor do topo com o nome, a cor e a lista novos
        await carregarPerfis();
        mostrarMensagem('Configurações do perfil salvas.', 'success');
    } catch (erro) {
        await carregarPerfis().catch(() => {});
        mostrarMensagem(erro?.message || 'Falha na operação');
    } finally {
        botao.disabled = Boolean(state.selecionado) && !state.selecionado.pode_gerir;
    }
}

function definirPerfilAtivo(perfil) {
    if (!perfil || !perfil.ativo) return;
    state.ativo = usarPerfil(perfil.id);
    state.selecionado = perfil;
    renderPerfis();
    preencherFormularioPerfil(perfil);
    mostrarMensagem(`Perfil em uso alterado para ${perfil.nome}.`, 'success');
    carregarPreferencias().catch(() => avisarPreferencias('Não foi possível carregar as preferências.', 'error'));
}

function renderAjuda() {
    const dados = ajuda[state.secao] || ajuda['perfis-financeiros'];
    $('config-help-title').textContent = dados.titulo;
    const lista = criarEl('div', 'config-help-list');
    dados.itens.forEach(([titulo, texto], indice) => {
        const item = criarEl('div', 'config-help-item');
        const marcador = criarEl('span', 'config-help-marker', String(indice + 1));
        marcador.setAttribute('aria-hidden', 'true');
        const corpo = criarEl('span');
        corpo.append(criarEl('strong', null, titulo), criarEl('span', null, texto));
        item.append(marcador, corpo);
        lista.append(item);
    });
    $('config-help-content').replaceChildren(lista);
}

function trocarSecao(secao) {
    state.secao = document.querySelector(`[data-config-section="${CSS.escape(secao || '')}"]`) ? secao : 'perfis-financeiros';
    for (const painel of document.querySelectorAll('[data-config-section]')) {
        painel.classList.toggle('active', painel.dataset.configSection === state.secao);
    }
    for (const link of document.querySelectorAll('[data-config-section-target]')) {
        link.classList.toggle('active', link.dataset.configSectionTarget === state.secao);
    }
    $('config-aviso-geral').hidden = true;
    renderAjuda();
    if (window.location.hash !== `#${state.secao}`) window.history.replaceState(null, '', `#${state.secao}`);
}

function avisarEmMigracao(funcao) {
    const aviso = $('config-aviso-geral');
    aviso.textContent = `${funcao}: em migração para o novo aplicativo. Até lá, continua no sistema atual.`;
    aviso.hidden = false;
}

// ---- Preferencias (FIN-PRE-PRODUCAO-1) ---------------------------------------------------------------------------
const SECOES_PREFERENCIAS = {
    gerais: ['nome_usuario', 'renda_principal', 'mes_inicio_planejamento', 'dia_fechamento_mes'],
    aparencia: ['tema_sistema', 'cor_principal', 'mostrar_icones_coloridos', 'abreviar_valores'],
    comportamento: ['ajustar_competencia_automatico', 'exibir_aviso_despesa_vencida', 'solicitar_confirmacao_exclusao',
        'vincular_pagamento_cartao_auto'],
    ia: ['modo_inteligente_ativo', 'sugestoes_economia', 'classificacao_automatica', 'correcao_categorias'],
};
const preferencias = { escopo: {}, podeGerir: false };

function campoPreferencia(campo) {
    return campo === 'tema_sistema' ? [...document.querySelectorAll('input[name="tema_sistema"]')] : [$(campo)].filter(Boolean);
}

function lerPreferencia(campo) {
    const [primeiro] = campoPreferencia(campo);
    if (campo === 'tema_sistema') return campoPreferencia(campo).find((radio) => radio.checked)?.value ?? null;
    if (!primeiro) return undefined;
    if (primeiro.type === 'checkbox') return primeiro.checked;
    if (campo === 'mes_inicio_planejamento' || campo === 'dia_fechamento_mes') return primeiro.value === '' ? null : Number(primeiro.value);
    return primeiro.value;
}

function escreverPreferencia(campo, valor) {
    const elementos = campoPreferencia(campo);
    for (const el of elementos) {
        if (campo === 'tema_sistema') el.checked = el.value === valor;
        else if (el.type === 'checkbox') el.checked = Boolean(valor);
        else el.value = valor ?? '';
        el.disabled = preferencias.escopo[campo] === 'PERFIL' && !preferencias.podeGerir;
    }
    if (campo === 'cor_principal' && $('cor_preview')) $('cor_preview').textContent = valor || '';
}

function avisarPreferencias(texto, tipo = 'info', secao = null) {
    for (const aviso of document.querySelectorAll('[data-pref-aviso]')) {
        const daSecao = !secao || aviso.closest('[data-config-section]')?.querySelector(`[data-preferences-save="${secao}"]`);
        aviso.textContent = daSecao ? texto : '';
        aviso.dataset.tipo = tipo;
        aviso.hidden = !daSecao || !texto;
    }
}

function preencherPreferencias(resposta) {
    preferencias.escopo = resposta.escopo || {};
    preferencias.podeGerir = Boolean(resposta.pode_gerir_perfil);
    for (const campos of Object.values(SECOES_PREFERENCIAS)) {
        for (const campo of campos) escreverPreferencia(campo, resposta.data?.[campo]);
    }
    avisarPreferencias(preferencias.podeGerir ? ''
        : 'Você só lê este perfil: as preferências do perfil ficam bloqueadas; as da sua conta podem ser alteradas.');
}

async function carregarPreferencias() {
    if (!state.ativo?.id) return;
    const { data, error } = await supabase.rpc('preferencias_tela', { p_perfil_id: state.ativo.id });
    if (error) throw error;
    preencherPreferencias(data);
}

async function salvarPreferencias(secao, botao) {
    const dados = {};
    for (const campo of SECOES_PREFERENCIAS[secao] || []) {
        if (preferencias.escopo[campo] === 'PERFIL' && !preferencias.podeGerir) continue;
        const valor = lerPreferencia(campo);
        if (valor !== undefined) dados[campo] = valor;
    }
    botao.disabled = true;
    try {
        const { data, error } = await supabase.rpc('salvar_preferencias', { p_perfil_id: state.ativo.id, p_dados: dados });
        if (error) throw error;
        preencherPreferencias(data);
        avisarPreferencias('Preferências salvas.', 'success', secao);
    } catch (erro) {
        avisarPreferencias(erro?.message || 'Não foi possível salvar as preferências. Nada foi gravado.', 'error', secao);
    } finally {
        botao.disabled = false;
    }
}

function ligar() {
    for (const botao of document.querySelectorAll('[data-config-section-target]')) {
        botao.addEventListener('click', () => trocarSecao(botao.dataset.configSectionTarget));
    }
    $('config-import-settings').addEventListener('click', () => avisarEmMigracao('Importar configurações'));
    $('config-export-settings').addEventListener('click', () => avisarEmMigracao('Exportar configurações'));
    $('config-profiles-list').addEventListener('click', (evento) => {
        if (evento.target.closest('#config-profile-card-new')) {
            novoPerfil();
            return;
        }
        const cartao = evento.target.closest('[data-profile-id]');
        if (!cartao) return;
        mostrarMensagem('');
        state.selecionado = state.perfis.find((perfil) => mesmoId(perfil.id, cartao.dataset.profileId)) || null;
        renderPerfis();
        preencherFormularioPerfil(state.selecionado);
    });
    $('config-profile-new').addEventListener('click', novoPerfil);
    $('config-profile-cancel').addEventListener('click', () => {
        mostrarMensagem('');
        state.selecionado = state.perfis.find((perfil) => mesmoId(perfil.id, state.ativo?.id)) || state.perfis[0] || null;
        renderPerfis();
        preencherFormularioPerfil(state.selecionado);
    });
    $('config-profile-save').addEventListener('click', salvarPerfil);
    $('config-profile-use').addEventListener('click', () => definirPerfilAtivo(state.selecionado));
    $('config-profile-tipo').addEventListener('change', atualizarChecksConceituais);
    $('config-profile-ativo').addEventListener('change', atualizarChecksConceituais);
    $('config-profile-form').addEventListener('submit', (evento) => evento.preventDefault());
    for (const botao of document.querySelectorAll('[data-preferences-save]')) {
        botao.addEventListener('click', () => salvarPreferencias(botao.dataset.preferencesSave, botao));
    }
    $('cor_principal')?.addEventListener('input', (evento) => { $('cor_preview').textContent = evento.target.value; });
    for (const form of document.querySelectorAll('.config-preferences-form')) {
        form.addEventListener('submit', (evento) => evento.preventDefault());
    }
}

ligar();
trocarSecao(window.location.hash ? decodeURIComponent(window.location.hash.slice(1)) : 'perfis-financeiros');
const contexto = await iniciarMoldura();
if (contexto) {
    state.ativo = contexto.perfil;
    try {
        await carregarPerfis();
    } catch (_erro) {
        $('config-profiles-list').replaceChildren(criarEl('div', 'config-empty-state',
            'Não foi possível carregar os perfis financeiros.'));
    }
    try {
        await carregarPreferencias();
    } catch (_erro) {
        avisarPreferencias('Não foi possível carregar as preferências.', 'error');
    }
}
