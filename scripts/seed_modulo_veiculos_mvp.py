"""
Seed / exemplo do Módulo de Veículos (FASE 1)

Objetivo:
- Criar 1 veículo SIMULADO e gerar projeções (DespesaPrevista)
- Converter para ATIVO e garantir:
  - não cria histórico retroativo
  - nenhuma despesa real (ItemDespesa/Conta/LancamentoAgregado) foi criada automaticamente
"""

from datetime import date
import sys
from pathlib import Path

# Garantir import do pacote "backend" ao executar via "python scripts\\...".
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app
from backend.models import (
    db,
    Categoria,
    Veiculo,
    VeiculoRegraManutencaoKm,
    DespesaPrevista,
    VeiculoFinanciamento,
    ItemDespesa,
    Conta,
    LancamentoAgregado,
)
from backend.services.veiculo_service import (
    aplicar_defaults_categorias_veiculo,
    gerar_projecoes_mvp,
    limpar_projecoes_anteriores,
)
from backend.services.despesa_prevista_service import confirmar, adiar, ignorar
from backend.services.veiculo_manutencao_km_service import gerar_despesa_prevista_por_regra
from backend.services.veiculo_financiamento_service import upsert_financiamento


def _categoria_por_nomes(nomes):
    for nome in nomes:
        cat = Categoria.query.filter(Categoria.nome.ilike(nome)).first()
        if cat:
            return cat
    return Categoria.query.first()


def main():
    app = create_app('testing')

    with app.app_context():
        # Criar tabelas novas se ainda não existirem (não altera tabelas existentes)
        db.create_all()

        # Garantir categorias mínimas no banco de teste
        if Categoria.query.count() == 0:
            db.session.add_all([
                Categoria(nome='Combustível', ativo=True),
                Categoria(nome='IPVA', ativo=True),
                Categoria(nome='Seguro', ativo=True),
                Categoria(nome='Licenciamento', ativo=True),
            ])
            db.session.commit()

        nome_seed = 'Veículo SIMULADO (Seed MVP)'

        # Estado antes (para validar "nenhuma despesa real foi criada automaticamente")
        antes_item = ItemDespesa.query.count()
        antes_conta = Conta.query.count()
        antes_lanc = LancamentoAgregado.query.count()

        veiculo = Veiculo.query.filter_by(nome=nome_seed).first()
        if not veiculo:
            veiculo = Veiculo(
                nome=nome_seed,
                tipo='carro',
                combustivel='gasolina',
                autonomia_km_l=12,
                status='SIMULADO',
                data_inicio=None,
                preco_medio_combustivel=6,
                combustivel_valor_mensal=500,
                ipva_mes=3,
                ipva_valor=2500,
                seguro_mes=8,
                seguro_valor=1800,
                licenciamento_mes=4,
                licenciamento_valor=200,
            )

            # Categorias existentes (sem criar categoria nova)
            veiculo.categoria_combustivel_id = _categoria_por_nomes(['Combustível', 'Combustivel', 'Transporte']).id
            veiculo.ipva_categoria_id = _categoria_por_nomes(['IPVA', 'Impostos', 'Imposto']).id
            veiculo.seguro_categoria_id = _categoria_por_nomes(['Seguro']).id
            veiculo.licenciamento_categoria_id = _categoria_por_nomes(['Licenciamento', 'Impostos', 'Imposto']).id

            db.session.add(veiculo)

        aplicar_defaults_categorias_veiculo(veiculo)
        gerar_projecoes_mvp(veiculo, meses_futuros=12)
        db.session.commit()

        proj_sim = DespesaPrevista.query.filter_by(origem_tipo='VEICULO', origem_id=veiculo.id).count()
        print(f'[OK] Veículo SIMULADO: id={veiculo.id} | projeções={proj_sim}')

        # Converter para ativo (sem retroativo)
        veiculo.status = 'ATIVO'
        veiculo.data_inicio = date.today()
        limpar_projecoes_anteriores(veiculo.id, veiculo.data_inicio)
        gerar_projecoes_mvp(veiculo, meses_futuros=12)
        db.session.commit()

        proj_apos = DespesaPrevista.query.filter_by(origem_tipo='VEICULO', origem_id=veiculo.id).count()
        print(f'[OK] Convertido -> ATIVO: data_inicio={veiculo.data_inicio} | projeções={proj_apos}')

        # =========================
        # FASE 2: Interação humana
        # =========================
        todas = DespesaPrevista.query.filter_by(
            origem_tipo='VEICULO',
            origem_id=veiculo.id
        ).all()
        snapshot = {
            p.id: (p.status, p.data_original_prevista, p.data_atual_prevista, p.data_prevista)
            for p in todas
        }

        previstas = DespesaPrevista.query.filter_by(
            origem_tipo='VEICULO',
            origem_id=veiculo.id,
            status='PREVISTA'
        ).order_by(DespesaPrevista.data_prevista.asc()).all()

        if len(previstas) >= 3:
            def tipo_evento(p):
                try:
                    return (p.to_dict().get('metadata') or {}).get('tipo_evento')
                except Exception:
                    return None

            combustiveis = [p for p in previstas if tipo_evento(p) == 'COMBUSTIVEL']
            alvo_confirmar = combustiveis[0] if combustiveis else previstas[0]
            restantes = [p for p in previstas if p.id != alvo_confirmar.id]
            alvo_adiar = restantes[0]
            alvo_ignorar = restantes[1]

            confirmar(alvo_confirmar.id)
            adiar(alvo_adiar.id, date.today().replace(day=1), ajustar_ciclo=False)
            ignorar(alvo_ignorar.id)
            db.session.commit()

            c = DespesaPrevista.query.get(alvo_confirmar.id)
            a = DespesaPrevista.query.get(alvo_adiar.id)
            i = DespesaPrevista.query.get(alvo_ignorar.id)

            assert c.status == 'CONFIRMADA', 'Confirmar não alterou status para CONFIRMADA'
            assert i.status == 'IGNORADA', 'Ignorar não alterou status para IGNORADA'
            assert a.status == 'ADIADA', 'Adiar não alterou status para ADIADA'
            assert a.data_original_prevista == alvo_adiar.data_original_prevista, 'Data original foi alterada (proibido)'
            assert a.data_atual_prevista == a.data_prevista, 'data_prevista deve espelhar data_atual_prevista'

            # Segurança: não pode alterar novamente nesta fase
            try:
                confirmar(alvo_confirmar.id)
                raise AssertionError('CONFIRMADA não deveria permitir nova alteração nesta fase')
            except ValueError:
                db.session.rollback()

            # FASE 3: confirmação de combustível soma km estimado (se tiver preço médio configurado)
            veiculo_atual = Veiculo.query.get(veiculo.id)
            if tipo_evento(alvo_confirmar) == 'COMBUSTIVEL' and veiculo_atual.preco_medio_combustivel:
                assert (veiculo_atual.km_estimado_acumulado or 0) > 0, 'km_estimado_acumulado deveria ser > 0 após combustível confirmado'

            # Outras despesas não mudaram
            todas_depois = DespesaPrevista.query.filter_by(
                origem_tipo='VEICULO',
                origem_id=veiculo.id
            ).all()
            for p in todas_depois:
                antes = snapshot.get(p.id)
                if not antes:
                    continue
                if p.id in (alvo_confirmar.id, alvo_adiar.id, alvo_ignorar.id):
                    continue
                depois = (p.status, p.data_original_prevista, p.data_atual_prevista, p.data_prevista)
                assert antes == depois, 'Outra despesa foi alterada (proibido nesta fase)'

            print('[OK] FASE 2: confirmar/adiar/ignorar aplicados sem cascata e sem lançamento real')
        else:
            print('[WARN] FASE 2: não há 3 despesas PREVISTA para testar interação')

        # =========================
        # FASE 4: Manutenção por km
        # =========================
        cat_manut = _categoria_por_nomes(['Manutenção', 'Manutencao'])
        if not cat_manut:
            cat_manut = Categoria(nome='Manutenção', ativo=True)
            db.session.add(cat_manut)
            db.session.commit()

        regra = VeiculoRegraManutencaoKm.query.filter_by(veiculo_id=veiculo.id, tipo_evento='TROCA_OLEO').first()
        if not regra:
            regra = VeiculoRegraManutencaoKm(
                veiculo_id=veiculo.id,
                tipo_evento='TROCA_OLEO',
                intervalo_km=10000,
                custo_estimado=350,
                categoria_id=cat_manut.id,
                ativo=True
            )
            db.session.add(regra)
            db.session.commit()

        desp_manut = gerar_despesa_prevista_por_regra(veiculo.id, regra.id, janela_meses=3)
        db.session.commit()

        if desp_manut:
            print('[OK] FASE 4: manutenção por km gerou 1 despesa prevista (TROCA_OLEO)')
            # FASE 5: Adiar + decisão explícita de ajustar ciclo (gera apenas 1 próxima ocorrência)
            _, criada_id = adiar(desp_manut.id, date.today().replace(day=1), ajustar_ciclo=True)
            db.session.commit()
            if criada_id:
                print('[OK] FASE 5: ajuste de ciclo gerou apenas 1 próxima ocorrência')
            else:
                print('[WARN] FASE 5: ajuste de ciclo não gerou próxima ocorrência (bloqueado ou sem média)')
        else:
            print('[WARN] FASE 4: manutenção por km não gerou (uso insuficiente ou já existia evento)')

        # =========================
        # FASE 6: Financiamento (simulação projetiva)
        # =========================
        cat_fin = _categoria_por_nomes(['Financiamento', 'Juros'])
        if not cat_fin:
            cat_fin = Categoria(nome='Financiamento', ativo=True)
            db.session.add(cat_fin)
            db.session.commit()

        # Criar/atualizar financiamento
        resultado = upsert_financiamento(veiculo.id, {
            'valor_bem': 50000,
            'entrada': 10000,
            'numero_parcelas': 48,
            'taxa_juros_mensal': 2.02,
            'indexador_tipo': 'TR',
            'iof_percentual': 0.38,
            'categoria_id': cat_fin.id
        })
        db.session.commit()

        fin = VeiculoFinanciamento.query.filter_by(veiculo_id=veiculo.id).first()
        assert fin is not None, 'Financiamento não foi criado'
        assert fin.valor_financiado == fin.valor_bem - fin.entrada, 'valor_financiado inválido'

        def contar_eventos(tipo_evento, status=None):
            itens = DespesaPrevista.query.filter_by(origem_tipo='VEICULO', origem_id=veiculo.id).all()
            c = 0
            for d in itens:
                if status and d.status != status:
                    continue
                md = d.to_dict().get('metadata') or {}
                if md.get('tipo_evento') == tipo_evento:
                    c += 1
            return c

        parcelas_previstas = contar_eventos('PARCELA_FINANCIAMENTO', status='PREVISTA')
        iof_previsto = contar_eventos('IOF_FINANCIAMENTO', status='PREVISTA')
        assert parcelas_previstas == 48, f'Parcelas previstas esperadas=48, atual={parcelas_previstas}'
        assert iof_previsto == 1, f'IOF previsto esperado=1, atual={iof_previsto}'

        # Confirmar uma parcela e alterar parâmetros: não pode apagar CONFIRMADA
        uma_parcela = DespesaPrevista.query.filter_by(origem_tipo='VEICULO', origem_id=veiculo.id, status='PREVISTA').all()
        parcela_fin = None
        for d in uma_parcela:
            if (d.to_dict().get('metadata') or {}).get('tipo_evento') == 'PARCELA_FINANCIAMENTO':
                parcela_fin = d
                break
        assert parcela_fin is not None, 'Nenhuma parcela de financiamento encontrada'
        confirmar(parcela_fin.id)
        db.session.commit()

        # Atualizar financiamento (regera apenas PREVISTA)
        upsert_financiamento(veiculo.id, {
            'valor_bem': 50000,
            'entrada': 5000,
            'numero_parcelas': 48,
            'taxa_juros_mensal': 2.5,
            'indexador_tipo': 'TR',
            'iof_percentual': 0.38,
            'categoria_id': cat_fin.id
        })
        db.session.commit()
        assert DespesaPrevista.query.get(parcela_fin.id).status == 'CONFIRMADA', 'Parcela confirmada foi alterada (proibido)'

        print('[OK] FASE 6: financiamento simulado gerou parcelas previstas e preservou confirmadas ao recalcular')

        depois_item = ItemDespesa.query.count()
        depois_conta = Conta.query.count()
        depois_lanc = LancamentoAgregado.query.count()

        print('[CHECK] Despesas reais (não deve mudar):')
        print(f'  ItemDespesa: {antes_item} -> {depois_item}')
        print(f'  Conta: {antes_conta} -> {depois_conta}')
        print(f'  LancamentoAgregado: {antes_lanc} -> {depois_lanc}')

        if (antes_item, antes_conta, antes_lanc) != (depois_item, depois_conta, depois_lanc):
            raise SystemExit('[ERRO] Houve alteração em tabelas de despesas reais; isso viola o contrato.')

        print('[SUCESSO] Seed concluído sem criar lançamentos reais.')


if __name__ == '__main__':
    main()
