// FIN-MULTIUSUARIO-ACESSO-01 — Administracao da Plataforma: convites, contas e auditoria de acesso.
//
// Tudo passa por funcoes do banco que exigem o administrador da plataforma em cada chamada; a tela so apresenta. Nenhuma
// funcao daqui le dado financeiro. O e-mail do convite e enviado pelo Supabase Auth (painel do projeto): o navegador nao
// tem, e nao deve ter, a credencial que envia convites. Elementos criados por DOM (sem innerHTML): a CSP nao permite outro jeito.

import { supabase } from './cliente.js';
import { iniciarMoldura } from './moldura.js';

const $ = (id) => document.getElementById(id);
const DATA = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' });
const quando = (texto) => (texto ? DATA.format(new Date(texto)) : '—');
const SITUACAO_CONVITE = { PENDENTE: 'Pendente', USADO: 'Usado', REVOGADO: 'Revogado', EXPIRADO: 'Expirado' };
const ACOES = {
    CONVITE_CRIADO: 'Convite registrado', CONVITE_REVOGADO: 'Convite revogado', CONVITE_REENVIADO: 'Reenvio registrado',
    CONTA_ATIVADA: 'Conta ativada', CONTA_SUSPENSA: 'Conta suspensa', CONTA_REATIVADA: 'Conta reativada',
    CONTA_DEFINIDA_PELO_OPERADOR: 'Situação definida pelo operador',
};
const POR_DICA = {
    SO_ADMINISTRADOR: 'Esta área é restrita ao administrador da plataforma. Nada foi gravado.',
    CONTA_EXISTENTE: 'Este e-mail já tem conta no aplicativo.',
    CONVITE_PENDENTE: 'Já existe um convite pendente para este e-mail.',
    LIMITE_DE_ENVIOS: 'Limite de envios deste convite atingido: revogue-o e registre outro.',
    ENVIO_RECENTE: 'Aguarde 10 minutos entre um envio e outro.',
};

function mensagem(erro) {
    if (erro && POR_DICA[erro.hint]) return POR_DICA[erro.hint];
    if (erro && erro.code === '22023' && erro.message) return erro.message;
    return 'Não foi possível concluir a operação. Nada foi gravado.';
}

function avisar(texto, tipo = 'ok') {
    const alerta = $('adm-alerta');
    alerta.textContent = texto;
    alerta.dataset.tipo = tipo;
    alerta.hidden = !texto;
}

// Cada chamada com o nome literal da funcao (a lista de funcoes liberadas e conferida nos testes do build).
async function dado(chamada) {
    const { data, error } = await chamada;
    if (error) throw error;
    return data;
}

function elemento(tag, classe, texto) {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined) e.textContent = texto;
    return e;
}

function botao(texto, acao, classe = '') {
    const b = elemento('button', `adm-botao ${classe}`.trim(), texto);
    b.type = 'button';
    b.addEventListener('click', async () => {
        b.disabled = true;
        try {
            await acao();
        } catch (erro) {
            avisar(mensagem(erro), 'erro');
        } finally {
            b.disabled = false;
        }
    });
    return b;
}

function linha(titulo, selo, tipoSelo, detalhes, acoes = []) {
    const item = elemento('div', 'adm-item');
    const cabeca = elemento('div', 'adm-item-cabeca');
    cabeca.append(elemento('strong', 'adm-item-titulo', titulo));
    if (selo) {
        const marca = elemento('span', 'adm-selo', selo);
        marca.dataset.tipo = tipoSelo || '';
        cabeca.append(marca);
    }
    const corpo = elemento('div', 'adm-item-detalhes', detalhes.filter(Boolean).join(' · '));
    const lado = elemento('div', 'adm-item-acoes');
    lado.append(...acoes);
    const texto = elemento('div', 'adm-item-texto');
    texto.append(cabeca, corpo);
    item.append(texto, lado);
    return item;
}

function vazio(texto) {
    return elemento('p', 'adm-vazio', texto);
}

async function carregarConvites() {
    const convites = await dado(supabase.rpc('convites_tela'));
    $('adm-lista-convites').replaceChildren(...(convites.length ? convites.map((c) => {
        const acoes = [];
        if (c.situacao === 'PENDENTE' || c.situacao === 'EXPIRADO') {
            acoes.push(botao('Registrar reenvio', async () => {
                await dado(supabase.rpc('registrar_reenvio_convite', { p_convite_id: c.id, p_validade_dias: 7 }));
                avisar('Reenvio registrado e validade renovada por 7 dias. Envie o convite de novo pelo painel do Supabase.');
                await carregarConvites();
            }));
            acoes.push(botao('Revogar', async () => {
                if (!window.confirm(`Revogar o convite de ${c.email}?`)) return;
                await dado(supabase.rpc('revogar_convite', { p_convite_id: c.id }));
                avisar('Convite revogado.');
                await carregarConvites();
            }, 'adm-botao-perigo'));
        }
        const item = linha(c.email, SITUACAO_CONVITE[c.situacao] || c.situacao, c.situacao, [
            `registrado em ${quando(c.criado_em)}`,
            c.situacao === 'PENDENTE' || c.situacao === 'EXPIRADO' ? `validade até ${quando(c.expira_em)}` : null,
            c.situacao === 'USADO' ? `usado em ${quando(c.usado_em)}` : null,
            c.situacao === 'REVOGADO' ? `revogado em ${quando(c.revogado_em)}` : null,
            `${c.envios} envio${c.envios === 1 ? '' : 's'}`,
            c.conta_no_auth && c.situacao !== 'USADO' ? 'já tem login criado' : null,
            c.observacao,
        ], acoes);
        item.dataset.convite = c.email;
        return item;
    }) : [vazio('Nenhum convite registrado.')]));
}

async function carregarUsuarios() {
    const usuarios = await dado(supabase.rpc('usuarios_tela'));
    $('adm-lista-usuarios').replaceChildren(...usuarios.map((u) => {
        const acoes = [];
        if (u.situacao === 'ATIVA' && !u.eu && !u.administrador) {
            acoes.push(botao('Suspender', async () => {
                const motivo = window.prompt(`Motivo da suspensão de ${u.email}:`);
                if (motivo === null) return;
                await dado(supabase.rpc('suspender_usuario', { p_user_id: u.user_id, p_motivo: motivo }));
                avisar('Conta suspensa. Os dados dela foram preservados.');
                await carregarUsuarios();
            }, 'adm-botao-perigo'));
        }
        if (u.situacao === 'SUSPENSA') {
            acoes.push(botao('Reativar', async () => {
                await dado(supabase.rpc('reativar_usuario', { p_user_id: u.user_id }));
                avisar('Conta reativada.');
                await carregarUsuarios();
            }));
        }
        const item = linha(u.email || '(sem e-mail)', u.situacao === 'ATIVA' ? 'Ativa' : 'Suspensa', u.situacao, [
            u.administrador ? 'administrador' : null,
            u.eu ? 'esta conta' : null,
            `${u.perfis} perfi${u.perfis === 1 ? 'l' : 's'}`,
            `ativada em ${quando(u.ativada_em)}`,
            u.situacao === 'SUSPENSA' ? `suspensa em ${quando(u.suspensa_em)}${u.motivo ? ` (${u.motivo})` : ''}` : null,
        ], acoes);
        item.dataset.usuario = u.email || '';
        return item;
    }));
}

async function carregarAuditoria() {
    const registros = await dado(supabase.rpc('auditoria_acesso_tela', { p_limite: 50 }));
    $('adm-lista-auditoria').replaceChildren(...(registros.length ? registros.map((r) => linha(ACOES[r.acao] || r.acao, null, null, [
        quando(r.quando), r.ator ? `por ${r.ator}` : 'pelo operador', r.detalhe && r.detalhe.motivo ? `motivo: ${r.detalhe.motivo}` : null,
    ])) : [vazio('Nenhum registro.')]));
}

const CARGAS = { convites: carregarConvites, usuarios: carregarUsuarios, auditoria: carregarAuditoria };

async function abrir(aba) {
    for (const b of document.querySelectorAll('.adm-aba')) {
        const ativa = b.dataset.aba === aba;
        b.classList.toggle('ativa', ativa);
        b.setAttribute('aria-selected', ativa ? 'true' : 'false');
    }
    for (const s of document.querySelectorAll('.adm-secao')) s.hidden = s.dataset.secao !== aba;
    try {
        await CARGAS[aba]();
    } catch (erro) {
        avisar(mensagem(erro), 'erro');
    }
}

const moldura = await iniciarMoldura();
if (moldura) {
    let administrador = false;
    try {
        administrador = (await dado(supabase.rpc('sou_administrador_plataforma'))) === true;
    } catch (_erro) {
        administrador = false;
    }
    if (!administrador) {
        $('adm-restrito').hidden = false;
    } else {
        $('adm-pagina').hidden = false;
        for (const b of document.querySelectorAll('.adm-aba')) {
            b.addEventListener('click', () => {
                avisar('');
                abrir(b.dataset.aba);
            });
        }
        $('adm-form-convite').addEventListener('submit', async (evento) => {
            evento.preventDefault();
            avisar('');
            const email = $('adm-convite-email').value.trim().toLowerCase();
            $('adm-convite-enviar').disabled = true;
            try {
                await dado(supabase.rpc('criar_convite', { p_dados: {
                    email, validade_dias: Number($('adm-convite-validade').value), observacao: $('adm-convite-observacao').value.trim(),
                } }));
                $('adm-form-convite').reset();
                avisar(`Convite registrado para ${email}. Agora envie o convite pelo painel do Supabase para o mesmo endereço.`);
                await carregarConvites();
            } catch (erro) {
                avisar(mensagem(erro), 'erro');
            } finally {
                $('adm-convite-enviar').disabled = false;
            }
        });
        await abrir('convites');
    }
}
