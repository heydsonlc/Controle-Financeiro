// Tela inicial provisoria: contas bancarias do perfil ativo (PERFIS-1) e
// categorias (globais). Tudo somente leitura. Perfis e contas vem de funcoes do
// banco que revalidam a autorizacao a cada chamada; categorias, da RLS por usuario.

import { supabase } from './cliente.js';
import { iniciarMoldura } from './moldura.js';

const COR_VALIDA = /^#[0-9A-Fa-f]{6}$/;

// FIN-MIGRACAO-FIDELIDADE-FASE-1: sessao, menu e perfil pela moldura; trocar de perfil recarrega a pagina.
const contexto = await iniciarMoldura();

if (contexto) {
    await Promise.all([contexto.perfil ? carregarContas(contexto.perfil.id) : null, carregarCategorias()]);
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
