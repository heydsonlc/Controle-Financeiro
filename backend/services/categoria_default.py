from __future__ import annotations

try:
    from backend.models import db, Categoria
except ImportError:
    from models import db, Categoria


MODULO_MOBILIDADE = 'mobilidade'

MOB_COMBUSTIVEL = 'MOB_COMBUSTIVEL'
MOB_SEGURO_VEICULAR = 'MOB_SEGURO_VEICULAR'
MOB_TRIBUTOS_VEICULARES = 'MOB_TRIBUTOS_VEICULARES'
MOB_REVISAO = 'MOB_REVISAO'
MOB_MANUTENCAO = 'MOB_MANUTENCAO'
MOB_PNEUS = 'MOB_PNEUS'
MOB_USO_VEICULO = 'MOB_USO_VEICULO'
MOB_APP = 'MOB_APP'
MOB_ASSINATURA = 'MOB_ASSINATURA'
MOB_LAVAGEM = 'MOB_LAVAGEM'


CATEGORIAS_SISTEMICAS_MOBILIDADE = {
    MOB_COMBUSTIVEL: {
        'nome': 'Combustível',
        'descricao': 'Combustível e abastecimento de veículos.',
        'cor': '#f97316',
        'icone': 'fuel',
    },
    MOB_SEGURO_VEICULAR: {
        'nome': 'Seguro Veicular',
        'descricao': 'Seguro do veículo.',
        'cor': '#2563eb',
        'icone': 'shield',
    },
    MOB_TRIBUTOS_VEICULARES: {
        'nome': 'Tributos Veiculares',
        'descricao': 'IPVA, licenciamento e taxas obrigatórias similares.',
        'cor': '#7c3aed',
        'icone': 'receipt',
    },
    MOB_REVISAO: {
        'nome': 'Revisão',
        'descricao': 'Revisões programadas do veículo.',
        'cor': '#0891b2',
        'icone': 'clipboard-check',
    },
    MOB_MANUTENCAO: {
        'nome': 'Manutenção Veicular',
        'descricao': 'Manutenção geral, preventiva ou corretiva.',
        'cor': '#475569',
        'icone': 'wrench',
    },
    MOB_PNEUS: {
        'nome': 'Pneus',
        'descricao': 'Pneus, troca de pneus e alinhamento associado.',
        'cor': '#111827',
        'icone': 'circle',
    },
    MOB_USO_VEICULO: {
        'nome': 'Uso do Veículo',
        'descricao': 'Estacionamento, pedágio e custos de uso do carro próprio.',
        'cor': '#0f766e',
        'icone': 'road',
    },
    MOB_APP: {
        'nome': 'Transporte por Aplicativo',
        'descricao': 'Uber, 99, táxi e aplicativos similares.',
        'cor': '#16a34a',
        'icone': 'smartphone',
    },
    MOB_ASSINATURA: {
        'nome': 'Assinatura Veicular',
        'descricao': 'Carro por assinatura.',
        'cor': '#9333ea',
        'icone': 'calendar',
    },
    MOB_LAVAGEM: {
        'nome': 'Lavagem Veicular',
        'descricao': 'Lavagem, higienização e lava-jato.',
        'cor': '#0284c7',
        'icone': 'sparkles',
    },
}


def _normalizar_tipo(tipo_evento: str | None) -> str:
    return str(tipo_evento or '').strip().upper()


def _definicao(codigo_sistema: str) -> dict:
    try:
        return CATEGORIAS_SISTEMICAS_MOBILIDADE[codigo_sistema]
    except KeyError:
        raise ValueError(f'Categoria sistêmica desconhecida: {codigo_sistema}')


def _aplicar_metadados_sistemicos(categoria: Categoria, codigo_sistema: str, definicao: dict) -> Categoria:
    categoria.nome = definicao['nome']
    categoria.descricao = definicao.get('descricao')
    categoria.cor = definicao.get('cor') or categoria.cor or '#6c757d'
    categoria.icone = definicao.get('icone') or categoria.icone
    categoria.ativo = True
    categoria.sistemica = True
    categoria.codigo_sistema = codigo_sistema
    categoria.modulo_origem = MODULO_MOBILIDADE
    categoria.bloquear_edicao = True
    categoria.bloquear_exclusao = True
    return categoria


def obter_categoria_sistemica(codigo_sistema: str) -> Categoria:
    """
    Retorna uma Categoria de Despesa sistêmica por código estável.

    O helper não depende de ID fixo nem do nome "Mobilidade". Se a categoria
    não existir, cria de forma idempotente. Se existir pelo nome esperado sem
    codigo_sistema, promove o registro existente para categoria sistêmica.
    """
    codigo_sistema = str(codigo_sistema or '').strip().upper()
    definicao = _definicao(codigo_sistema)

    categoria = Categoria.query.filter_by(codigo_sistema=codigo_sistema).first()
    if categoria:
        _aplicar_metadados_sistemicos(categoria, codigo_sistema, definicao)
        db.session.add(categoria)
        db.session.flush()
        return categoria

    categoria = Categoria.query.filter(
        db.func.lower(db.func.trim(Categoria.nome)) == definicao['nome'].strip().lower()
    ).first()
    if categoria:
        _aplicar_metadados_sistemicos(categoria, codigo_sistema, definicao)
        db.session.add(categoria)
        db.session.flush()
        return categoria

    categoria = Categoria()
    _aplicar_metadados_sistemicos(categoria, codigo_sistema, definicao)
    db.session.add(categoria)
    db.session.flush()
    return categoria


def obter_categoria_sistemica_id(codigo_sistema: str) -> int:
    return obter_categoria_sistemica(codigo_sistema).id


def categoria_sistemica_mobilidade_id_para_tipo_evento(tipo_evento: str | None) -> int:
    tipo = _normalizar_tipo(tipo_evento)
    codigo = {
        'COMBUSTIVEL': MOB_COMBUSTIVEL,
        'ABASTECIMENTO': MOB_COMBUSTIVEL,
        'SEGURO': MOB_SEGURO_VEICULAR,
        'SEGURO_VEICULAR': MOB_SEGURO_VEICULAR,
        'IPVA': MOB_TRIBUTOS_VEICULARES,
        'LICENCIAMENTO': MOB_TRIBUTOS_VEICULARES,
        'TRIBUTO': MOB_TRIBUTOS_VEICULARES,
        'TRIBUTOS': MOB_TRIBUTOS_VEICULARES,
        'TAXA_OBRIGATORIA': MOB_TRIBUTOS_VEICULARES,
        'REVISAO': MOB_REVISAO,
        'REVISAO_GERAL': MOB_REVISAO,
        'REVISAO_PROGRAMADA': MOB_REVISAO,
        'TROCA_PNEUS': MOB_PNEUS,
        'PNEUS': MOB_PNEUS,
        'ALINHAMENTO_BALANCEAMENTO': MOB_PNEUS,
        'ESTACIONAMENTO': MOB_USO_VEICULO,
        'PEDAGIO': MOB_USO_VEICULO,
        'USO_VEICULO': MOB_USO_VEICULO,
        'TRANSPORTE_APP': MOB_APP,
        'APP': MOB_APP,
        'TAXI': MOB_APP,
        'UBER': MOB_APP,
        'ASSINATURA': MOB_ASSINATURA,
        'ASSINATURA_VEICULAR': MOB_ASSINATURA,
        'LAVAGEM': MOB_LAVAGEM,
        'LAVA_JATO': MOB_LAVAGEM,
        'HIGIENIZACAO': MOB_LAVAGEM,
    }.get(tipo)

    if codigo:
        return obter_categoria_sistemica_id(codigo)
    return obter_categoria_sistemica_id(MOB_MANUTENCAO)


def garantir_categorias_sistemicas_mobilidade() -> list[Categoria]:
    return [obter_categoria_sistemica(codigo) for codigo in CATEGORIAS_SISTEMICAS_MOBILIDADE]


def get_categoria_padrao_veiculos() -> int:
    """
    Compatibilidade com chamadas legadas.

    A categoria genérica "Mobilidade" deixou de ser fallback operacional; para
    fluxos antigos que ainda chamem este helper, retornamos Combustivel.
    """
    return obter_categoria_sistemica_id(MOB_COMBUSTIVEL)
