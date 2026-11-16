// FIN-MVP-CADASTRO-UNIFICADO-01 — demonstracao do modal unico (so ambiente local, fora do dist e do deploy).
// Abre o componente de js/cadastro-despesa.js com a sessao e o perfil ativos, nos seis cenarios da homologacao visual.
// ?cenario=1..6 abre direto um cenario (para a pagina de varios tamanhos); &exemplo=1 preenche nome, valor e categoria.

const $ = (id) => document.getElementById(id);

// O build poe ?v=<hash> nas importacoes: o cliente do Supabase precisa ser o MESMO modulo que os servicos usam.
async function enderecoComoEm(arquivo, nome) {
    const fonte = await (await fetch(arquivo)).text();
    const m = fonte.match(new RegExp(`\\./${nome}\\.js(\\?v=[0-9a-f]+)?`));
    return `/js/${nome}.js${(m && m[1]) || ''}`;
}

const SERVICOS = { DESPESA_DIRETA: 'POST /api/despesas → criar_despesa', COMPRA_CARTAO: 'POST /api/cartoes/:id/lancamentos → criar_compra',
    DESPESA_RECORRENTE: 'POST /api/recorrencias → criar_despesa (recorrente) ou criar_recorrencia_cartao', CONSORCIO: 'POST /api/consorcios → criar_consorcio' };

const CENARIOS = [
    { n: 1, rotulo: '1. Despesa direta', tipo: 'DESPESA_DIRETA', exemplo: { nome: 'Conta de luz (fictícia)', valor: '184.90' } },
    { n: 2, rotulo: '2. Compra no cartão', tipo: 'COMPRA_CARTAO', exemplo: { nome: 'Supermercado (fictício)', valor: '356.40' } },
    { n: 3, rotulo: '3. Recorrência mensal em conta', tipo: 'DESPESA_RECORRENTE', exemplo: { nome: 'Aluguel (fictício)', valor: '1500' } },
    { n: 4, rotulo: '4. Recorrência semanal ou quinzenal', tipo: 'DESPESA_RECORRENTE', dados: { frequencia: 'semanal' }, exemplo: { nome: 'Diarista (fictícia)', valor: '180' } },
    { n: 5, rotulo: '5. Recorrência mensal no cartão', tipo: 'DESPESA_RECORRENTE', dados: { meio_pagamento: 'cartao' }, exemplo: { nome: 'Streaming (fictício)', valor: '39.90' } },
    { n: 6, rotulo: '6. Consórcio', tipo: 'CONSORCIO', exemplo: { nome: 'Consórcio do carro (fictício)', valor: '850' } },
];
const ORIGENS = [
    { rotulo: 'Despesas → Nova despesa', origem: 'despesas', tipo: 'DESPESA_DIRETA' },
    { rotulo: 'Lançamentos → Despesa direta', origem: 'lancamentos', tipo: 'DESPESA_DIRETA' },
    { rotulo: 'Lançamentos → Cartão de crédito', origem: 'lancamentos', tipo: 'COMPRA_CARTAO' },
    { rotulo: 'Recorrências → Nova recorrência', origem: 'recorrencias', tipo: 'DESPESA_RECORRENTE' },
];

function estado(texto, link) {
    $('demo-estado').replaceChildren(texto);
    if (link) {
        const a = document.createElement('a');
        a.href = link[1];
        a.textContent = link[0];
        $('demo-estado').append(' ', a);
    }
}

async function iniciar() {
    const { supabase } = await import(await enderecoComoEm('/js/perfil.js', 'cliente'));
    const { data } = await supabase.auth.getUser();
    if (!data || !data.user) {
        estado('Sem sessão. Entre com a conta fictícia (usuario.g@teste.local) e volte a esta página.', ['Abrir o login', '/index.html']);
        return;
    }
    const { carregarPerfis, escolherPerfilAtivo } = await import('/js/perfil.js');
    const perfil = escolherPerfilAtivo(await carregarPerfis(), data.user.id);
    if (!perfil) {
        estado('Nenhum perfil financeiro autorizado para esta conta.');
        return;
    }
    const { abrirCadastroDespesa, prepararCadastro } = await import('/js/cadastro-despesa.js');
    prepararCadastro(perfil.id);
    estado(`Conta ${data.user.email} · perfil “${perfil.nome}” · banco descartável.`);

    const celular = () => window.matchMedia('(max-width: 900px)').matches;
    const destinos = {
        despesas: (mes) => (celular() ? `/despesas-mobile.html?mes=${mes}` : '/contas.html'),
        cartoes: (mes, cartao) => (celular() ? `/cartoes-mobile.html?mes=${mes}&cartao=${cartao}` : '/cartoes.html'),
        recorrencias: () => (celular() ? '/recorrencias-mobile.html' : '/recorrencias.html'),
    };
    function registrar(registro) {
        $('demo-vazio').hidden = true;
        const item = document.createElement('li');
        const corpo = document.createElement('code');
        corpo.textContent = JSON.stringify(registro.corpo, null, 1);
        item.append(`${registro.tipo} — ${SERVICOS[registro.tipo]}`, corpo);
        $('demo-registros').append(item);
    }
    function abrir({ tipo, origem = 'previa', dados = {}, exemplo = {} }) {
        const comExemplo = $('demo-exemplo').checked;
        return abrirCadastroDespesa({ origem, tipoInicial: tipo, destinos, aoSalvar: registrar,
            dados: { ...dados, ...(comExemplo ? exemplo : {}) } });
    }
    for (const [lista, alvo] of [[CENARIOS, 'demo-cenarios'], [ORIGENS, 'demo-origens']]) {
        for (const c of lista) {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = c.rotulo;
            if (c.n) b.id = `demo-cenario-${c.n}`;
            b.addEventListener('click', () => abrir(c));
            $(alvo).append(b);
        }
    }
    $('demo-painel').hidden = false;

    const parametros = new URLSearchParams(window.location.search);
    $('demo-exemplo').checked = parametros.get('exemplo') === '1';
    const direto = CENARIOS.find((c) => String(c.n) === parametros.get('cenario'));
    if (direto) abrir(direto);
}

iniciar().catch((erro) => {
    console.error('Prévia do cadastro:', erro);
    estado(`Não foi possível iniciar a prévia: ${erro.message}`);
});
