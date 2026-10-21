// Tela inicial provisoria: contas bancarias do perfil ativo (PERFIS-1) e
// categorias (globais). Tudo somente leitura. Perfis e contas vem de funcoes do
// banco que revalidam a autorizacao a cada chamada; categorias, da RLS por usuario.

import { supabase } from './cliente.js';
import { carregarPerfis, escolherPerfilAtivo, salvarPerfilAtivo } from './perfil.js';
import { exigirUsuario, sair } from './sessao.js';

const COR_VALIDA = /^#[0-9A-Fa-f]{6}$/;

const usuario = await exigirUsuario();

if (usuario) {
    document.getElementById('usuario-email').textContent = usuario.email || '';
    document.getElementById('sair').addEventListener('click', sair);
    await Promise.all([iniciarPerfis(usuario.id), carregarCategorias()]);
}

function mostrar(id, texto) {
    const elemento = document.getElementById(id);
    if (texto !== undefined) elemento.textContent = texto;
    elemento.hidden = false;
}

function amostraDeCor(cor) {
    const celula = document.createElement('td');
    const amostra = document.createElement('span');
    amostra.className = 'app-cor';
    if (COR_VALIDA.test(cor || '')) amostra.style.backgroundColor = cor;
    celula.append(amostra);
    return celula;
}

function celulaTexto(texto) {
    const celula = document.createElement('td');
    celula.textContent = texto || '';
    return celula;
}

async function iniciarPerfis(usuarioId) {
    let perfis;
    try {
        perfis = await carregarPerfis();
    } catch (_erro) {
        mostrar('perfis-erro', 'Não foi possível carregar os perfis financeiros.');
        return;
    }
    if (!perfis.length) {
        mostrar('perfis-vazio');
        return;
    }

    const seletor = document.getElementById('perfil-ativo');
    for (const perfil of perfis) {
        const opcao = document.createElement('option');
        opcao.value = String(perfil.id);
        opcao.textContent = perfil.nome;
        seletor.append(opcao);
    }
    const ativo = escolherPerfilAtivo(perfis, usuarioId);
    seletor.value = String(ativo.id);
    document.getElementById('perfil-rotulo').hidden = false;

    seletor.addEventListener('change', async () => {
        salvarPerfilAtivo(usuarioId, seletor.value);
        await carregarContas(Number(seletor.value));
    });
    await carregarContas(ativo.id);
}

async function carregarContas(perfilId) {
    const tabela = document.getElementById('contas-tabela');
    const corpo = document.getElementById('contas-corpo');
    const erro = document.getElementById('contas-erro');
    const vazio = document.getElementById('contas-vazio');
    corpo.replaceChildren();
    tabela.hidden = true;
    erro.hidden = true;
    vazio.hidden = true;

    const { data, error } = await supabase.rpc('contas_bancarias_do_perfil', { p_perfil_id: perfilId });
    if (error) {
        mostrar('contas-erro', 'Perfil não autorizado ou indisponível.');
        return;
    }
    if (!data.length) {
        vazio.hidden = false;
        return;
    }
    for (const conta of data) {
        const linha = document.createElement('tr');
        linha.dataset.contaId = String(conta.id);
        linha.append(amostraDeCor(conta.cor), celulaTexto(conta.nome), celulaTexto(conta.instituicao), celulaTexto(conta.tipo));
        corpo.append(linha);
    }
    tabela.hidden = false;
}

async function carregarCategorias() {
    const { data, error } = await supabase
        .from('categorias')
        .select('id, nome, descricao, cor, ativo')
        .order('nome', { ascending: true });

    if (error) {
        mostrar('categorias-erro', 'Não foi possível carregar as categorias.');
        return;
    }
    if (!data.length) {
        mostrar('categorias-vazio');
        return;
    }

    const corpo = document.getElementById('categorias-corpo');
    for (const categoria of data) {
        const linha = document.createElement('tr');
        linha.dataset.categoriaId = String(categoria.id);
        const situacao = celulaTexto(categoria.ativo ? 'Ativa' : 'Inativa');
        if (!categoria.ativo) situacao.className = 'app-situacao-inativa';
        linha.append(amostraDeCor(categoria.cor), celulaTexto(categoria.nome), celulaTexto(categoria.descricao), situacao);
        corpo.append(linha);
    }
    document.getElementById('categorias-tabela').hidden = false;
}
