"""DATA-HYGIENE-RECEITA-1: saneamento controlado de receitas realizadas sem conta bancaria.

Audita ReceitaRealizada sem conta_bancaria_id e sem MovimentoFinanceiro vinculado,
classifica cada uma de forma deterministica (sem inferir conta, data ou valor) e,
apenas quando ha evidencia suficiente, regulariza criando o movimento financeiro
via ContaBancariaService.criar_movimento() (mesmo service usado pelo fluxo normal
de recebimento, CORE-RECEITA-1).

Opera no banco configurado em DATABASE_URL (.env.local) atraves do app Flask —
o mesmo banco que a aplicacao usa em producao/dev — nao em arquivos SQLite legados.

Uso:
    venv\\Scripts\\python.exe scripts\\data_hygiene_receitas_historicas.py --dry-run
    venv\\Scripts\\python.exe scripts\\data_hygiene_receitas_historicas.py --apply
    venv\\Scripts\\python.exe scripts\\data_hygiene_receitas_historicas.py --dry-run --only-id 20
    venv\\Scripts\\python.exe scripts\\data_hygiene_receitas_historicas.py --dry-run --export-csv data/tmp/receitas_historicas_sem_movimento.csv

Classificacoes:
    REGULARIZAR_MOVIMENTO   - conta bancaria, data e valor confirmados; sem movimento -> cria movimento
    REABRIR_COMO_PENDENTE   - valor_recebido ausente/<=0 (nao ha evidencia de recebimento real,
                              mesmo com data preenchida — data_recebimento e NOT NULL no schema) -> exclui ReceitaRealizada
    PENDENTE_DECISAO_USUARIO- tem valor valido, mas conta bancaria nao pode ser inferida com seguranca
    IGNORAR_JA_CONSISTENTE  - ja tem conta_bancaria_id e movimento (nao deveria aparecer na consulta-base)
    BLOQUEADO_INCONSISTENTE - ja possui MovimentoFinanceiro vinculado apesar de conta_bancaria_id NULL (nao deveria ocorrer)

Nenhuma conta bancaria e inferida por "unica conta", "conta mais usada" ou heuristica
similar — apenas campo explicito (ReceitaRealizada.conta_bancaria_id ou
ItemReceita.conta_bancaria_id da fonte vinculada).
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('FLASK_ENV', 'development')

REGULARIZAR_MOVIMENTO = 'REGULARIZAR_MOVIMENTO'
REABRIR_COMO_PENDENTE = 'REABRIR_COMO_PENDENTE'
PENDENTE_DECISAO_USUARIO = 'PENDENTE_DECISAO_USUARIO'
IGNORAR_JA_CONSISTENTE = 'IGNORAR_JA_CONSISTENTE'
BLOQUEADO_INCONSISTENTE = 'BLOQUEADO_INCONSISTENTE'


@dataclass
class Diagnostico:
    receita_id: int
    descricao: str
    valor_recebido: float | None
    data_recebimento: str | None
    mes_referencia: str | None
    conta_bancaria_id: int | None
    conta_inferida_id: int | None
    conta_inferida_origem: str | None
    tem_movimento: bool
    observacoes: str
    classificacao: str
    acao: str
    motivo: str


def _diagnosticar_uma(receita, item_receita, mov_existente) -> Diagnostico:
    valor = float(receita.valor_recebido) if receita.valor_recebido is not None else None
    data_rec = receita.data_recebimento.isoformat() if receita.data_recebimento else None

    if mov_existente:
        return Diagnostico(
            receita_id=receita.id,
            descricao=receita.descricao or '',
            valor_recebido=valor,
            data_recebimento=data_rec,
            mes_referencia=receita.mes_referencia.isoformat() if receita.mes_referencia else None,
            conta_bancaria_id=receita.conta_bancaria_id,
            conta_inferida_id=None,
            conta_inferida_origem=None,
            tem_movimento=True,
            observacoes=receita.observacoes or '',
            classificacao=BLOQUEADO_INCONSISTENTE,
            acao='nenhuma (ja possui movimento; investigar manualmente)',
            motivo='Existe MovimentoFinanceiro vinculado apesar de conta_bancaria_id ausente na receita.',
        )

    # Unica fonte de conta aceita: campo explicito da propria fonte de receita vinculada.
    conta_inferida_id = None
    conta_inferida_origem = None
    if item_receita is not None and item_receita.conta_bancaria_id:
        conta_inferida_id = item_receita.conta_bancaria_id
        conta_inferida_origem = f'item_receita.id={item_receita.id}.conta_bancaria_id'

    valor_valido = valor is not None and valor > 0
    data_valida = data_rec is not None

    if valor_valido and data_valida and conta_inferida_id:
        return Diagnostico(
            receita_id=receita.id,
            descricao=receita.descricao or '',
            valor_recebido=valor,
            data_recebimento=data_rec,
            mes_referencia=receita.mes_referencia.isoformat() if receita.mes_referencia else None,
            conta_bancaria_id=receita.conta_bancaria_id,
            conta_inferida_id=conta_inferida_id,
            conta_inferida_origem=conta_inferida_origem,
            tem_movimento=False,
            observacoes=receita.observacoes or '',
            classificacao=REGULARIZAR_MOVIMENTO,
            acao=f'criar MovimentoFinanceiro CREDITO na conta_bancaria_id={conta_inferida_id}',
            motivo=f'Conta explicita da fonte de receita ({conta_inferida_origem}); valor e data validos.',
        )

    # data_recebimento e NOT NULL no model: "sem data" nao ocorre em dado nao-corrompido.
    # A unica evidencia de "nao foi de fato recebida" que o schema permite e valor invalido.
    if not valor_valido:
        return Diagnostico(
            receita_id=receita.id,
            descricao=receita.descricao or '',
            valor_recebido=valor,
            data_recebimento=data_rec,
            mes_referencia=receita.mes_referencia.isoformat() if receita.mes_referencia else None,
            conta_bancaria_id=receita.conta_bancaria_id,
            conta_inferida_id=None,
            conta_inferida_origem=None,
            tem_movimento=False,
            observacoes=receita.observacoes or '',
            classificacao=REABRIR_COMO_PENDENTE,
            acao='excluir ReceitaRealizada (nao ha evidencia de recebimento efetivo)',
            motivo='valor_recebido ausente ou <= 0 — nao ha registro de recebimento real, apesar de data_recebimento preenchida (campo NOT NULL no schema).',
        )

    return Diagnostico(
        receita_id=receita.id,
        descricao=receita.descricao or '',
        valor_recebido=valor,
        data_recebimento=data_rec,
        mes_referencia=receita.mes_referencia.isoformat() if receita.mes_referencia else None,
        conta_bancaria_id=receita.conta_bancaria_id,
        conta_inferida_id=None,
        conta_inferida_origem=None,
        tem_movimento=False,
        observacoes=receita.observacoes or '',
        classificacao=PENDENTE_DECISAO_USUARIO,
        acao='nenhuma (aguarda decisao do usuario sobre a conta bancaria)',
        motivo='Ha valor e/ou data, mas nenhuma conta bancaria explicita pode ser inferida com seguranca.',
    )


def diagnosticar(only_id: int | None = None) -> list[Diagnostico]:
    try:
        from backend.models import ReceitaRealizada, ItemReceita, MovimentoFinanceiro
    except ImportError:
        from models import ReceitaRealizada, ItemReceita, MovimentoFinanceiro

    query = ReceitaRealizada.query.filter(ReceitaRealizada.conta_bancaria_id.is_(None))
    if only_id is not None:
        query = query.filter(ReceitaRealizada.id == only_id)
    receitas = query.order_by(ReceitaRealizada.id).all()

    resultados = []
    for receita in receitas:
        item_receita = None
        if receita.item_receita_id:
            item_receita = ItemReceita.query.get(receita.item_receita_id)
        mov = MovimentoFinanceiro.query.filter_by(
            receita_realizada_id=receita.id,
            origem='RECEITA',
        ).first()
        resultados.append(_diagnosticar_uma(receita, item_receita, mov))
    return resultados


def imprimir_diagnostico(resultados: list[Diagnostico], *, modo: str) -> None:
    print(f'Modo: {modo}')
    print(f'Total analisado: {len(resultados)}')
    print()

    contagem: dict[str, int] = {}
    for r in resultados:
        contagem[r.classificacao] = contagem.get(r.classificacao, 0) + 1

    print('Resumo por classificacao:')
    for classe in (REGULARIZAR_MOVIMENTO, REABRIR_COMO_PENDENTE, PENDENTE_DECISAO_USUARIO,
                   IGNORAR_JA_CONSISTENTE, BLOQUEADO_INCONSISTENTE):
        if contagem.get(classe):
            print(f'  {classe}: {contagem[classe]}')
    print()

    if not resultados:
        print('Nenhuma receita realizada sem conta bancaria encontrada. Nada a analisar.')
        return

    for r in resultados:
        print(f'--- Receita id={r.receita_id} ---')
        print(f'  Descricao: {r.descricao}')
        print(f'  Valor recebido: {r.valor_recebido}')
        print(f'  Data recebimento: {r.data_recebimento}')
        print(f'  Competencia: {r.mes_referencia}')
        print(f'  Observacoes: {r.observacoes}')
        print(f'  Classificacao: {r.classificacao}')
        if r.conta_inferida_id:
            print(f'  Conta identificada: id={r.conta_inferida_id} (origem: {r.conta_inferida_origem})')
        print(f'  Acao: {r.acao}')
        print(f'  Motivo: {r.motivo}')
        print()

    saldo_por_conta: dict[int, float] = {}
    for r in resultados:
        if r.classificacao == REGULARIZAR_MOVIMENTO and r.conta_inferida_id:
            saldo_por_conta[r.conta_inferida_id] = saldo_por_conta.get(r.conta_inferida_id, 0.0) + (r.valor_recebido or 0.0)
    if saldo_por_conta:
        print('Impacto estimado de saldo por conta (se REGULARIZAR_MOVIMENTO for aplicado):')
        for conta_id, total in saldo_por_conta.items():
            print(f'  conta_bancaria_id={conta_id}: +{total:.2f}')
        print()

    pendentes = [r for r in resultados if r.classificacao == PENDENTE_DECISAO_USUARIO]
    if pendentes:
        print('IDs pendentes de decisao do usuario:', ', '.join(str(r.receita_id) for r in pendentes))

    bloqueados = [r for r in resultados if r.classificacao == BLOQUEADO_INCONSISTENTE]
    if bloqueados:
        print('IDs bloqueados/inconsistentes (investigar manualmente):', ', '.join(str(r.receita_id) for r in bloqueados))


def exportar_csv(resultados: list[Diagnostico], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    campos = [
        'receita_id', 'descricao', 'valor_recebido', 'data_recebimento', 'mes_referencia',
        'conta_bancaria_id', 'conta_inferida_id', 'conta_inferida_origem', 'tem_movimento',
        'observacoes', 'classificacao', 'acao', 'motivo',
    ]
    with caminho.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for r in resultados:
            writer.writerow({campo: getattr(r, campo) for campo in campos})
    print(f'CSV exportado: {caminho}')


def criar_backup() -> dict:
    try:
        from backend.services.backup_service import BackupService
    except ImportError:
        from services.backup_service import BackupService

    resultado = BackupService.executar_backup_manual()
    if resultado.get('status') != 'concluido':
        raise RuntimeError(f"Falha ao criar backup obrigatorio: {resultado.get('mensagem')}")
    return resultado


def aplicar(resultados: list[Diagnostico]) -> dict:
    try:
        from backend.models import db, ReceitaRealizada, MovimentoFinanceiro
        from backend.services.conta_bancaria_service import ContaBancariaService
    except ImportError:
        from models import db, ReceitaRealizada, MovimentoFinanceiro
        from services.conta_bancaria_service import ContaBancariaService

    a_regularizar = [r for r in resultados if r.classificacao == REGULARIZAR_MOVIMENTO]
    a_reabrir = [r for r in resultados if r.classificacao == REABRIR_COMO_PENDENTE]

    if not a_regularizar and not a_reabrir:
        return {'movimentos_criados': [], 'receitas_reabertas': [], 'contas_recalculadas': {}}

    movimentos_criados = []
    receitas_reabertas = []
    contas_recalculadas: dict[int, float] = {}

    try:
        for r in a_regularizar:
            receita = ReceitaRealizada.query.get(r.receita_id)
            if receita is None:
                raise RuntimeError(f'Receita id={r.receita_id} nao encontrada durante apply (mudou entre dry-run e apply?)')
            if receita.conta_bancaria_id is not None:
                raise RuntimeError(f'Receita id={r.receita_id} ja possui conta_bancaria_id; revalidacao falhou')
            existe_mov = MovimentoFinanceiro.query.filter_by(
                receita_realizada_id=receita.id, origem='RECEITA',
            ).first()
            if existe_mov:
                raise RuntimeError(f'Receita id={r.receita_id} ja possui movimento; revalidacao falhou')

            receita.conta_bancaria_id = r.conta_inferida_id
            receita.observacoes = (
                (receita.observacoes or '').rstrip() +
                (f'\nregularizado_data_hygiene_receita_1={r.conta_inferida_origem}')
            ).strip()

            mov = ContaBancariaService.criar_movimento(
                r.conta_inferida_id,
                tipo='CREDITO',
                valor=Decimal(str(r.valor_recebido)),
                descricao=f'Regularização de receita histórica: {receita.descricao or "Receita"}',
                data_movimento=receita.data_recebimento,
                origem='RECEITA',
                ajustavel=False,
                receita_realizada_id=receita.id,
            )
            movimentos_criados.append({'receita_id': receita.id, 'movimento_id': mov.id, 'conta_bancaria_id': r.conta_inferida_id, 'valor': r.valor_recebido})
            contas_recalculadas[r.conta_inferida_id] = contas_recalculadas.get(r.conta_inferida_id, 0.0) + r.valor_recebido

        for r in a_reabrir:
            receita = ReceitaRealizada.query.get(r.receita_id)
            if receita is None:
                raise RuntimeError(f'Receita id={r.receita_id} nao encontrada durante apply')
            if receita.conta_bancaria_id is not None:
                raise RuntimeError(f'Receita id={r.receita_id} ganhou conta bancaria entre dry-run e apply; abortando')
            existe_mov = MovimentoFinanceiro.query.filter_by(
                receita_realizada_id=receita.id, origem='RECEITA',
            ).first()
            if existe_mov:
                raise RuntimeError(f'Receita id={r.receita_id} ganhou movimento entre dry-run e apply; abortando')
            db.session.delete(receita)
            receitas_reabertas.append(r.receita_id)

        db.session.commit()
    except Exception:
        db.session.rollback()
        # rollback() so expira automaticamente objetos "dirty" no momento da falha;
        # objetos ja flushados com sucesso em iteracoes anteriores do loop (ex.: receita.conta_bancaria_id
        # setado + criar_movimento() com flush interno) ficam limpos e nao sao revertidos em memoria
        # sem expire_all() explicito, mesmo com o dado ja revertido no banco.
        db.session.expire_all()
        raise

    return {
        'movimentos_criados': movimentos_criados,
        'receitas_reabertas': receitas_reabertas,
        'contas_recalculadas': contas_recalculadas,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='DATA-HYGIENE-RECEITA-1: saneamento de receitas historicas sem conta bancaria.')
    parser.add_argument('--db', default=None, help='Ignorado: o script usa DATABASE_URL de .env.local (banco real da aplicacao).')
    parser.add_argument('--dry-run', action='store_true', help='Mostra o diagnostico sem gravar (padrao).')
    parser.add_argument('--apply', action='store_true', help='Aplica as correcoes seguras com backup e transacao.')
    parser.add_argument('--only-id', type=int, default=None, help='Restringe a analise/aplicacao a uma unica receita.')
    parser.add_argument('--export-csv', default=None, help='Exporta o diagnostico para um CSV.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and args.dry_run:
        raise SystemExit('Use apenas uma flag: --dry-run ou --apply')
    if not args.apply:
        args.dry_run = True

    from backend.app import create_app
    app = create_app()

    with app.app_context():
        resultados = diagnosticar(only_id=args.only_id)

        if args.export_csv:
            exportar_csv(resultados, Path(args.export_csv))

        if args.dry_run:
            imprimir_diagnostico(resultados, modo='dry-run')
            return 0

        imprimir_diagnostico(resultados, modo='apply-validacao')

        a_regularizar = [r for r in resultados if r.classificacao == REGULARIZAR_MOVIMENTO]
        a_reabrir = [r for r in resultados if r.classificacao == REABRIR_COMO_PENDENTE]

        if not a_regularizar and not a_reabrir:
            print('Nada seguro a aplicar (nenhum item REGULARIZAR_MOVIMENTO ou REABRIR_COMO_PENDENTE).')
            return 0

        backup = criar_backup()
        print(f"Backup criado: {backup.get('caminho')}")

        resultado_apply = aplicar(resultados)

        print()
        print('Aplicado:')
        print(f"  Movimentos criados: {len(resultado_apply['movimentos_criados'])}")
        for m in resultado_apply['movimentos_criados']:
            print(f"    receita_id={m['receita_id']} -> movimento_id={m['movimento_id']} conta_bancaria_id={m['conta_bancaria_id']} valor={m['valor']}")
        print(f"  Receitas reabertas (excluidas): {resultado_apply['receitas_reabertas']}")
        print(f"  Saldo impactado por conta: {resultado_apply['contas_recalculadas']}")

        if resultado_apply['movimentos_criados']:
            try:
                from backend.services.conta_bancaria_service import ContaBancariaService
            except ImportError:
                from services.conta_bancaria_service import ContaBancariaService
            print()
            print('Conferencia de saldo pos-aplicacao:')
            for conta_id in resultado_apply['contas_recalculadas']:
                conferencia = ContaBancariaService.conferir_saldo(conta_id)
                print(f"  conta_bancaria_id={conta_id}: consistente={conferencia['consistente']} saldo_atual={conferencia['saldo_atual']}")

        print(f"BACKUP={backup.get('caminho')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
