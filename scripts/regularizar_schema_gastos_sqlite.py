from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models import db  # noqa: E402


HEAD_REVISION = '9b8a09ecc52f'


CATEGORIAS_MOBILIDADE = [
    ('MOB_COMBUSTIVEL', 'Combustível', 'Combustível e abastecimento de veículos.', '#f97316', 'fuel'),
    ('MOB_SEGURO_VEICULAR', 'Seguro Veicular', 'Seguro do veículo.', '#2563eb', 'shield'),
    ('MOB_TRIBUTOS_VEICULARES', 'Tributos Veiculares', 'IPVA, licenciamento e taxas obrigatórias similares.', '#7c3aed', 'receipt'),
    ('MOB_REVISAO', 'Revisão', 'Revisões programadas do veículo.', '#0891b2', 'clipboard-check'),
    ('MOB_MANUTENCAO', 'Manutenção Veicular', 'Manutenção geral, preventiva ou corretiva.', '#475569', 'wrench'),
    ('MOB_PNEUS', 'Pneus', 'Pneus, troca de pneus e alinhamento associado.', '#111827', 'circle'),
    ('MOB_USO_VEICULO', 'Uso do Veículo', 'Estacionamento, pedágio e custos de uso do carro próprio.', '#0f766e', 'road'),
    ('MOB_APP', 'Transporte por Aplicativo', 'Uber, 99, táxi e aplicativos similares.', '#16a34a', 'smartphone'),
    ('MOB_ASSINATURA', 'Assinatura Veicular', 'Carro por assinatura.', '#9333ea', 'calendar'),
    ('MOB_LAVAGEM', 'Lavagem Veicular', 'Lavagem, higienização e lava-jato.', '#0284c7', 'sparkles'),
]


TR_SEED = [
    ('2024-05', 2024, 5, '0.0008'),
    ('2024-06', 2024, 6, '0.0003'),
    ('2024-07', 2024, 7, '0.0007'),
    ('2024-08', 2024, 8, '0.0007'),
    ('2024-09', 2024, 9, '0.0006'),
    ('2024-10', 2024, 10, '0.0009'),
    ('2024-11', 2024, 11, '0.0006'),
    ('2024-12', 2024, 12, '0.0008'),
    ('2025-01', 2025, 1, '0.0016'),
    ('2025-02', 2025, 2, '0.0013'),
    ('2025-03', 2025, 3, '0.0010'),
    ('2025-04', 2025, 4, '0.0016'),
    ('2025-05', 2025, 5, '0.0017'),
    ('2025-06', 2025, 6, '0.0016'),
    ('2025-07', 2025, 7, '0.0017'),
    ('2025-08', 2025, 8, '0.0017'),
    ('2025-09', 2025, 9, '0.0017'),
    ('2025-10', 2025, 10, '0.0017'),
    ('2025-11', 2025, 11, '0.0016'),
    ('2025-12', 2025, 12, '0.0017'),
    ('2026-01', 2026, 1, '0.0017'),
    ('2026-02', 2026, 2, '0.0012'),
    ('2026-03', 2026, 3, '0.0017'),
    ('2026-04', 2026, 4, '0.0016'),
    ('2026-05', 2026, 5, '0.0016'),
]


class Regularizador:
    def __init__(self, db_path: Path, apply: bool, stamp_head: bool) -> None:
        self.db_path = db_path
        self.apply = apply
        self.stamp_head = stamp_head
        self.engine = create_engine(f'sqlite:///{db_path.resolve().as_posix()}')
        self.metadata = db.metadata
        self.operacoes: list[str] = []
        self.alertas: list[str] = []

    def executar(self) -> None:
        if not self.db_path.exists():
            raise SystemExit(f'Banco não encontrado: {self.db_path}')

        self._planejar_tabelas_ausentes()
        self._planejar_colunas_ausentes()
        self._planejar_indices()
        self._planejar_seeds()

        if not self.apply:
            self._imprimir_resultado()
            return

        self._aplicar()
        divergencias = self._divergencias_model()
        if divergencias:
            for divergencia in divergencias:
                self.alertas.append(f'Divergência residual: {divergencia}')
        elif self.stamp_head:
            self._stamp_head()

        self._imprimir_resultado()

    def _aplicar(self) -> None:
        with self.engine.begin() as conn:
            self._criar_tabelas_ausentes(conn)
            self._adicionar_colunas_ausentes(conn)
            self._criar_indices(conn)
            self._seed_perfis(conn)
            self._backfill_perfil(conn)
            self._backfill_defaults(conn)
            self._seed_categorias_mobilidade(conn)
            self._seed_tr(conn)

    def _imprimir_resultado(self) -> None:
        modo = 'APPLY' if self.apply else 'DRY-RUN'
        print(f'Modo: {modo}')
        print(f'Banco: {self.db_path}')
        print(f'Operações planejadas/executadas: {len(self.operacoes)}')
        for operacao in self.operacoes:
            print(f'- {operacao}')
        if self.alertas:
            print('Alertas:')
            for alerta in self.alertas:
                print(f'- {alerta}')

    def _planejar_tabelas_ausentes(self) -> None:
        existentes = self._tabelas()
        for table in sorted(self.metadata.tables.values(), key=lambda t: t.name):
            if table.name not in existentes:
                self.operacoes.append(f'criar tabela {table.name}')

    def _planejar_colunas_ausentes(self) -> None:
        existentes = self._tabelas()
        for table in sorted(self.metadata.tables.values(), key=lambda t: t.name):
            if table.name not in existentes:
                continue
            colunas = self._colunas(table.name)
            for column in table.columns:
                if column.name not in colunas:
                    self.operacoes.append(f'adicionar coluna {table.name}.{column.name}')

    def _planejar_indices(self) -> None:
        existentes = self._tabelas()
        for table in sorted(self.metadata.tables.values(), key=lambda t: t.name):
            if table.name not in existentes:
                continue
            colunas = self._colunas(table.name)
            indices = self._indices(table.name)
            for index in table.indexes:
                if index.name not in indices and all(col.name in colunas for col in index.columns):
                    self.operacoes.append(f'criar índice {index.name}')
        if 'categoria' in existentes and 'codigo_sistema' in self._colunas('categoria'):
            if 'ux_categoria_codigo_sistema' not in self._indices('categoria'):
                self.operacoes.append('criar índice único ux_categoria_codigo_sistema')

    def _planejar_seeds(self) -> None:
        if 'perfil_financeiro' not in self._tabelas():
            self.operacoes.append('seed perfis Pessoal/Empresa')
        if 'categoria' in self._tabelas():
            self.operacoes.append('seed categorias sistêmicas de Mobilidade')
        if 'indice_tr_mensal' in self._tabelas() or 'indice_tr_mensal' not in self._tabelas():
            self.operacoes.append('seed TR oficial 2024-05 a 2026-05')

    def _criar_tabelas_ausentes(self, conn) -> None:
        existentes = self._tabelas(conn)
        faltantes = [table for table in self.metadata.sorted_tables if table.name not in existentes]
        if faltantes:
            self.metadata.create_all(bind=conn, tables=faltantes, checkfirst=True)

    def _adicionar_colunas_ausentes(self, conn) -> None:
        existentes = self._tabelas(conn)
        dialect = self.engine.dialect
        for table in sorted(self.metadata.tables.values(), key=lambda t: t.name):
            if table.name not in existentes:
                continue
            colunas = self._colunas(table.name, conn)
            qtd_linhas = self._count(table.name, conn)
            for column in table.columns:
                if column.name in colunas:
                    continue
                ddl = self._ddl_add_column(table.name, column, dialect, qtd_linhas)
                if not ddl:
                    self.alertas.append(
                        f'Coluna não adicionada automaticamente: {table.name}.{column.name}'
                    )
                    continue
                conn.exec_driver_sql(ddl)

    def _criar_indices(self, conn) -> None:
        existentes = self._tabelas(conn)
        for table in sorted(self.metadata.tables.values(), key=lambda t: t.name):
            if table.name not in existentes:
                continue
            colunas = self._colunas(table.name, conn)
            indices = self._indices(table.name, conn)
            for index in table.indexes:
                if index.name in indices:
                    continue
                if not all(col.name in colunas for col in index.columns):
                    continue
                index.create(bind=conn, checkfirst=True)

        if 'categoria' in self._tabelas(conn) and 'codigo_sistema' in self._colunas('categoria', conn):
            if 'ux_categoria_codigo_sistema' not in self._indices('categoria', conn):
                conn.exec_driver_sql(
                    'CREATE UNIQUE INDEX IF NOT EXISTS "ux_categoria_codigo_sistema" '
                    'ON "categoria" ("codigo_sistema")'
                )

    def _seed_perfis(self, conn) -> int | None:
        if 'perfil_financeiro' not in self._tabelas(conn):
            return None

        agora = datetime.utcnow().isoformat(sep=' ', timespec='seconds')
        for nome, tipo, avatar, cor, padrao in [
            ('Pessoal', 'PESSOAL', 'PE', '#2563eb', 1),
            ('Empresa', 'EMPRESA', 'EM', '#0f766e', 0),
        ]:
            existe = conn.execute(
                text('SELECT id FROM perfil_financeiro WHERE nome = :nome ORDER BY id LIMIT 1'),
                {'nome': nome},
            ).scalar()
            if not existe:
                conn.execute(
                    text(
                        """
                        INSERT INTO perfil_financeiro
                            (nome, tipo, avatar, cor, ativo, padrao, created_at, updated_at)
                        VALUES
                            (:nome, :tipo, :avatar, :cor, 1, :padrao, :agora, :agora)
                        """
                    ),
                    {'nome': nome, 'tipo': tipo, 'avatar': avatar, 'cor': cor, 'padrao': padrao, 'agora': agora},
                )

        pessoal_id = conn.execute(
            text("SELECT id FROM perfil_financeiro WHERE nome = 'Pessoal' ORDER BY id LIMIT 1")
        ).scalar()
        if pessoal_id:
            conn.execute(text('UPDATE perfil_financeiro SET padrao = 0'))
            conn.execute(
                text('UPDATE perfil_financeiro SET ativo = 1, padrao = 1 WHERE id = :id'),
                {'id': pessoal_id},
            )
        return int(pessoal_id) if pessoal_id else None

    def _backfill_perfil(self, conn) -> None:
        pessoal_id = conn.execute(
            text("SELECT id FROM perfil_financeiro WHERE nome = 'Pessoal' ORDER BY id LIMIT 1")
        ).scalar()
        if not pessoal_id:
            return

        existentes = self._tabelas(conn)
        for table in sorted(self.metadata.tables.values(), key=lambda t: t.name):
            if table.name not in existentes:
                continue
            if 'perfil_financeiro_id' not in self._colunas(table.name, conn):
                continue
            conn.execute(
                text(f'UPDATE "{table.name}" SET perfil_financeiro_id = :perfil_id WHERE perfil_financeiro_id IS NULL'),
                {'perfil_id': pessoal_id},
            )

    def _backfill_defaults(self, conn) -> None:
        if 'categoria' in self._tabelas(conn):
            colunas = self._colunas('categoria', conn)
            for coluna in ('sistemica', 'bloquear_edicao', 'bloquear_exclusao'):
                if coluna in colunas:
                    conn.execute(text(f'UPDATE categoria SET {coluna} = 0 WHERE {coluna} IS NULL'))

        if 'financiamento' in self._tabelas(conn):
            colunas = self._colunas('financiamento', conn)
            defaults = {
                'modo_calculo_financiamento': 'padrao',
                'modo_taxa_mensal': 'efetiva_equivalente',
                'seguro_modo': 'fixo',
                'seguro_mes_reajuste_idade': 2,
            }
            for coluna, valor in defaults.items():
                if coluna in colunas:
                    conn.execute(
                        text(f'UPDATE financiamento SET {coluna} = :valor WHERE {coluna} IS NULL'),
                        {'valor': valor},
                    )

    def _seed_categorias_mobilidade(self, conn) -> None:
        if 'categoria' not in self._tabelas(conn):
            return
        colunas = self._colunas('categoria', conn)
        obrigatorias = {'nome', 'descricao', 'cor', 'ativo', 'sistemica', 'codigo_sistema', 'modulo_origem'}
        if not obrigatorias.issubset(colunas):
            self.alertas.append('Categorias sistêmicas não semeadas: colunas obrigatórias ausentes em categoria')
            return

        for codigo, nome, descricao, cor, icone in CATEGORIAS_MOBILIDADE:
            params = {
                'codigo': codigo,
                'nome': nome,
                'descricao': descricao,
                'cor': cor,
                'icone': icone,
            }
            set_icone = ', icone = :icone' if 'icone' in colunas else ''
            conn.execute(
                text(
                    f"""
                    UPDATE categoria
                    SET nome = :nome,
                        descricao = :descricao,
                        cor = :cor,
                        ativo = 1,
                        sistemica = 1,
                        codigo_sistema = :codigo,
                        modulo_origem = 'mobilidade',
                        bloquear_edicao = 1,
                        bloquear_exclusao = 1
                        {set_icone}
                    WHERE codigo_sistema = :codigo
                       OR (codigo_sistema IS NULL AND LOWER(TRIM(nome)) = LOWER(:nome))
                    """
                ),
                params,
            )
            insert_cols = ['nome', 'descricao', 'cor', 'ativo', 'sistemica', 'codigo_sistema', 'modulo_origem']
            insert_vals = [':nome', ':descricao', ':cor', '1', '1', ':codigo', "'mobilidade'"]
            if 'bloquear_edicao' in colunas:
                insert_cols.append('bloquear_edicao')
                insert_vals.append('1')
            if 'bloquear_exclusao' in colunas:
                insert_cols.append('bloquear_exclusao')
                insert_vals.append('1')
            if 'icone' in colunas:
                insert_cols.append('icone')
                insert_vals.append(':icone')
            if 'criado_em' in colunas:
                insert_cols.append('criado_em')
                insert_vals.append('CURRENT_TIMESTAMP')
            conn.execute(
                text(
                    f"""
                    INSERT INTO categoria ({', '.join(insert_cols)})
                    SELECT {', '.join(insert_vals)}
                    WHERE NOT EXISTS (
                        SELECT 1 FROM categoria WHERE codigo_sistema = :codigo
                    )
                    """
                ),
                params,
            )

    def _seed_tr(self, conn) -> None:
        if 'indice_tr_mensal' not in self._tabelas(conn):
            return
        for competencia, ano, mes, valor_decimal in TR_SEED:
            conn.execute(
                text(
                    """
                    INSERT INTO indice_tr_mensal
                        (ano, mes, competencia, valor_decimal, fonte, criado_em, atualizado_em)
                    SELECT
                        :ano, :mes, :competencia, :valor_decimal, 'BACEN',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    WHERE NOT EXISTS (
                        SELECT 1 FROM indice_tr_mensal WHERE competencia = :competencia
                    )
                    """
                ),
                {
                    'ano': ano,
                    'mes': mes,
                    'competencia': competencia,
                    'valor_decimal': valor_decimal,
                },
            )

    def _stamp_head(self) -> None:
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                'CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)'
            )
            conn.exec_driver_sql('DELETE FROM alembic_version')
            conn.execute(
                text('INSERT INTO alembic_version (version_num) VALUES (:version)'),
                {'version': HEAD_REVISION},
            )
        self.operacoes.append(f'stamp alembic_version={HEAD_REVISION}')

    def _divergencias_model(self) -> list[str]:
        divergencias: list[str] = []
        existentes = self._tabelas()
        for table in sorted(self.metadata.tables.values(), key=lambda t: t.name):
            if table.name not in existentes:
                divergencias.append(f'tabela ausente {table.name}')
                continue
            colunas = self._colunas(table.name)
            for column in table.columns:
                if column.name not in colunas:
                    divergencias.append(f'coluna ausente {table.name}.{column.name}')
        return divergencias

    def _ddl_add_column(self, table_name: str, column, dialect, qtd_linhas: int) -> str | None:
        if column.primary_key:
            return None

        tipo = column.type.compile(dialect=dialect)
        partes = [self._q(column.name), tipo]
        default = self._default_sql(column)
        if default is not None:
            partes.append(f'DEFAULT {default}')

        if not column.nullable:
            if default is None and qtd_linhas > 0:
                return None
            partes.append('NOT NULL')

        return f'ALTER TABLE {self._q(table_name)} ADD COLUMN {" ".join(partes)}'

    def _default_sql(self, column) -> str | None:
        if column.server_default is not None:
            arg = column.server_default.arg
            return str(arg.compile(compile_kwargs={'literal_binds': True})) if hasattr(arg, 'compile') else str(arg)
        if column.default is None:
            return None
        arg = column.default.arg
        if callable(arg):
            return None
        if isinstance(arg, bool):
            return '1' if arg else '0'
        if isinstance(arg, (int, float, Decimal)):
            return str(arg)
        if isinstance(arg, str):
            return "'" + arg.replace("'", "''") + "'"
        return None

    def _tabelas(self, conn=None) -> set[str]:
        query = "SELECT name FROM sqlite_master WHERE type='table'"
        if conn is not None:
            return {row[0] for row in conn.exec_driver_sql(query).fetchall()}
        with sqlite3.connect(self.db_path) as raw:
            return {row[0] for row in raw.execute(query).fetchall()}

    def _colunas(self, table_name: str, conn=None) -> set[str]:
        query = f'PRAGMA table_info({self._q(table_name)})'
        if conn is not None:
            return {row[1] for row in conn.exec_driver_sql(query).fetchall()}
        with sqlite3.connect(self.db_path) as raw:
            return {row[1] for row in raw.execute(query).fetchall()}

    def _indices(self, table_name: str, conn=None) -> set[str]:
        query = f'PRAGMA index_list({self._q(table_name)})'
        if conn is not None:
            return {row[1] for row in conn.exec_driver_sql(query).fetchall()}
        with sqlite3.connect(self.db_path) as raw:
            return {row[1] for row in raw.execute(query).fetchall()}

    def _count(self, table_name: str, conn) -> int:
        return int(conn.exec_driver_sql(f'SELECT COUNT(*) FROM {self._q(table_name)}').scalar() or 0)

    @staticmethod
    def _q(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'


def criar_backup(db_path: Path) -> Path:
    destino_dir = db_path.parent / 'backups'
    destino_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    destino = destino_dir / f'gastos_antes_regularizacao_schema_{timestamp}.db'
    shutil.copy2(db_path, destino)
    return destino


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Regulariza de forma idempotente o schema SQLite local do Controle Financeiro.'
    )
    parser.add_argument('--db', required=True, help='Caminho do arquivo SQLite a regularizar.')
    parser.add_argument('--dry-run', action='store_true', help='Apenas lista o que seria feito.')
    parser.add_argument('--apply', action='store_true', help='Aplica as alterações.')
    parser.add_argument(
        '--backup',
        action='store_true',
        help='Cria backup antes de aplicar. Recomendado para data/gastos.db.',
    )
    parser.add_argument(
        '--stamp-head',
        action='store_true',
        help='Marca alembic_version como head após schema sem divergências de tabelas/colunas.',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.apply == args.dry_run:
        raise SystemExit('Informe exatamente um modo: --dry-run ou --apply.')

    db_path = Path(args.db)
    if args.apply and args.backup:
        backup = criar_backup(db_path)
        print(f'Backup criado: {backup}')

    regularizador = Regularizador(db_path=db_path, apply=args.apply, stamp_head=args.stamp_head)
    regularizador.executar()


if __name__ == '__main__':
    main()
