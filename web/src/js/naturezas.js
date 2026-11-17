// FIN-CATEGORIAS-REORGANIZACAO-01 — natureza gerencial nas telas (so leitura e so apresentacao).
// Consumo, aportes e outras saidas sao uma REPARTICAO do total que a tela ja mostra: o total, os saldos e o fluxo nao
// mudam e nenhum pagamento sai da conta. A natureza vem do banco (financeiro.categoria_natureza), nunca do nome da
// categoria; categoria sem natureza gravada e consumo, como sempre foi.
// Se a leitura falhar (funcao ainda nao publicada, rede), a tela fica exatamente como era: sem a linha.

const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const centavos = (valor) => Math.round((Number(valor) || 0) * 100);

// Reparte uma lista de despesas (linhas com categoria_id e valor em reais) pelas naturezas. Devolve centavos; as tres
// partes somam exatamente o total da lista. "outras" = natureza nao definida, ajuste tecnico e transferencia interna.
export function repartirPorNatureza(despesas, naturezas, valorDe = (d) => d.valor) {
    const partes = { consumo: 0, aportes: 0, outras: 0 };
    for (const d of despesas) {
        const natureza = (naturezas && naturezas.get(Number(d.categoria_id))) || 'CONSUMO';
        const chave = natureza === 'CONSUMO' ? 'consumo' : natureza === 'APORTE' ? 'aportes' : 'outras';
        partes[chave] += centavos(valorDe(d));
    }
    return partes;
}

// A reparticao do banco (financeiro.indicadores_gerenciais), em centavos, ou null quando nao fecha com o total da tela:
// nesse caso a linha nao aparece (nunca se mostra uma reparticao que nao soma o total exibido).
export function reparticaoDosIndicadores(indicadores, totalDaTela) {
    if (!indicadores) return null;
    const partes = {
        consumo: centavos(indicadores.consumo),
        aportes: centavos(indicadores.aportes),
        outras: centavos(indicadores.nao_definido) + centavos(indicadores.ajustes_tecnicos) + centavos(indicadores.transferencias_internas),
    };
    if (partes.consumo + partes.aportes + partes.outras !== centavos(totalDaTela)) return null;
    return partes;
}

// "Consumo R$ x · Aportes R$ y" (+ "· Outras saídas R$ z" so quando houver).
export function textoDaReparticao(partes) {
    const trechos = [`Consumo ${moeda.format(partes.consumo / 100)}`, `Aportes ${moeda.format(partes.aportes / 100)}`];
    if (partes.outras) trechos.push(`Outras saídas ${moeda.format(partes.outras / 100)}`);
    // Cada parte nao quebra no meio (espaco inseparavel): em coluna estreita a linha quebra so entre as partes.
    return trechos.map((t) => t.replace(/ /g, ' ')).join(' · ');
}
