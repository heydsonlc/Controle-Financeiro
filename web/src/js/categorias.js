// Categorias em modo somente leitura. A RLS limita as linhas ao usuario logado;
// nenhuma operacao de escrita existe nesta pagina.

import { supabase } from './cliente.js';
import { exigirUsuario, sair } from './sessao.js';

const usuario = await exigirUsuario();

if (usuario) {
    document.getElementById('usuario-email').textContent = usuario.email || '';
    document.getElementById('sair').addEventListener('click', sair);
    await carregarCategorias();
}

async function carregarCategorias() {
    const erro = document.getElementById('categorias-erro');
    const vazio = document.getElementById('categorias-vazio');
    const tabela = document.getElementById('categorias-tabela');
    const corpo = document.getElementById('categorias-corpo');

    const { data, error } = await supabase
        .from('categorias')
        .select('id, nome, descricao, cor, ativo')
        .order('nome', { ascending: true });

    if (error) {
        erro.textContent = 'Não foi possível carregar as categorias.';
        erro.hidden = false;
        return;
    }

    if (!data.length) {
        vazio.hidden = false;
        return;
    }

    // textContent (nunca innerHTML): conteudo do banco nao vira HTML.
    for (const categoria of data) {
        const linha = document.createElement('tr');
        linha.dataset.categoriaId = String(categoria.id);

        const celulaCor = document.createElement('td');
        const amostra = document.createElement('span');
        amostra.className = 'app-cor';
        if (/^#[0-9A-Fa-f]{6}$/.test(categoria.cor || '')) {
            amostra.style.backgroundColor = categoria.cor;
        }
        celulaCor.append(amostra);

        const celulaNome = document.createElement('td');
        celulaNome.textContent = categoria.nome;

        const celulaDescricao = document.createElement('td');
        celulaDescricao.textContent = categoria.descricao || '';

        const celulaSituacao = document.createElement('td');
        celulaSituacao.textContent = categoria.ativo ? 'Ativa' : 'Inativa';
        if (!categoria.ativo) celulaSituacao.className = 'app-situacao-inativa';

        linha.append(celulaCor, celulaNome, celulaDescricao, celulaSituacao);
        corpo.append(linha);
    }
    tabela.hidden = false;
}
