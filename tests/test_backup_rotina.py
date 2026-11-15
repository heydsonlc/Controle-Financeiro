"""
Testes FIN-REG-02 — scripts/backup_rotina.py em bancos PostgreSQL descartaveis, com dados ficticios: o comando unico
(exportar, verificar, cifrar, validar, copiar para dois destinos, conferir, registrar e limpar), a chave mestra anual
(guarda externa, rotacao, chave anterior), as falhas classificadas (nenhuma vira sucesso), o aviso de atraso, a
retencao so informativa (nada e excluido) e a ausencia de credenciais em saidas, registros e arquivos.
"""
import datetime as dt
import hashlib
import json
import os
import stat
import sys
import time
import types
from pathlib import Path

import pytest

from tests.test_backup_banco import origem  # noqa: F401
from tests.test_supabase_recorrencia import PG_BIN, cluster  # noqa: F401

psycopg2 = pytest.importorskip('psycopg2')
pytest.importorskip('cryptography')
pytestmark = pytest.mark.skipif(PG_BIN is None, reason='binarios do PostgreSQL (initdb/pg_ctl) nao encontrados')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import backup_banco as B  # noqa: E402
import backup_rotina as R  # noqa: E402

SENHA = 'SENHA-FICTICIA-123'
AGORA = dt.datetime.now()


@pytest.fixture
def cfg(origem, tmp_path):  # noqa: F811
    """Configuracao so com pastas temporarias; a conexao (com uma senha ficticia, ignorada pelo banco local) fica num
    arquivo de ambiente, como na producao."""
    dsn = origem.replace('postgres@', f'postgres:{SENHA}@')
    assert SENHA in dsn
    (tmp_path / 'origem.env').write_text(f'DATABASE_URL={dsn}\n', encoding='utf-8')
    for nome in ('destino_local', 'destino_onedrive'):
        (tmp_path / nome).mkdir()
    return {'projeto': None, 'arquivo_env': str(tmp_path / 'origem.env'), 'variavel_env': 'DATABASE_URL', 'pg_bin': str(PG_BIN),
            'trabalho': str(tmp_path / 'trabalho'), 'pasta_chaves': str(tmp_path / 'chaves'),
            'destinos': [{'nome': 'local', 'pasta': str(tmp_path / 'destino_local')},
                         {'nome': 'onedrive', 'pasta': str(tmp_path / 'destino_onedrive')}],
            'registro': str(tmp_path / 'registro' / 'execucoes.jsonl'), 'espaco_minimo_mb': 1, 'dias_aviso': 10, '_dsn': dsn}


@pytest.fixture
def pendrive(tmp_path, monkeypatch):
    """Pasta que faz o papel de um volume fora do computador."""
    pasta = tmp_path / 'pendrive'
    pasta.mkdir()
    real = R._volume
    monkeypatch.setattr(R, '_volume', lambda c: 'X:' if R._dentro(c, pasta) else real(c))
    return pasta


def criar_chave(cfg, pendrive, ano=AGORA.year, agora=AGORA):
    item = R.chave_criar(cfg, ano, agora=agora)
    copia = pendrive / item['arquivo']
    copia.write_bytes((Path(cfg['pasta_chaves']) / item['arquivo']).read_bytes())
    R.chave_confirmar_guarda(cfg, ano, copia=str(copia))
    return item


def arquivos(pasta):
    pasta = Path(pasta)
    return sorted(p.name for p in pasta.rglob('*') if p.is_file()) if pasta.exists() else []


def sha(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def nada_guardado(cfg):
    return all(arquivos(d['pasta']) == [] for d in cfg['destinos'])


def sem_texto_claro(cfg):
    return [a for a in arquivos(cfg['trabalho']) if not a.endswith(('.cfbak', '.ficha.json'))] == []


def ultimo(cfg):
    return R.ler_registro(cfg)[-1]


def falso(cfg, backup_id, quando, tipo='SEMANAL', destinos=None):
    """Backup ficticio ja guardado (arquivo qualquer com a ficha coerente), para as consultas."""
    conteudo = R.MAGICA2 + backup_id.encode()
    ficha = {'backup_id': backup_id, 'tipo': tipo, 'gerado_em': quando.isoformat(timespec='seconds'), 'arquivo': f'{backup_id}.cfbak',
             'bytes': len(conteudo), 'sha256_cifrado': hashlib.sha256(conteudo).hexdigest()}
    for d in cfg['destinos']:
        if destinos is None or d['nome'] in destinos:
            (Path(d['pasta']) / ficha['arquivo']).write_bytes(conteudo)
            (Path(d['pasta']) / f'{backup_id}.ficha.json').write_text(json.dumps(ficha), encoding='utf-8')


# 1. fluxo completo -------------------------------------------------------------------------------------------------

def test_fluxo_completo_duas_copias_verificadas_registro_conferencia_e_ensaio(cfg, pendrive, tmp_path, capsys):
    item = criar_chave(cfg, pendrive)
    assert R.main(['executar'], cfg=cfg) == 0
    reg = ultimo(cfg)
    bid = reg['backup_id']
    assert reg['estado'] == 'CONCLUIDO' and reg['tipo'] == 'SEMANAL' and reg['chave_id'] == item['chave_id']
    assert reg['exportacao'] == reg['verificacao'] == reg['criptografia'] == reg['limpeza'] == 'OK'
    assert reg['ferramenta']['rotina'] == R.VERSAO and reg['erro'] is None
    # as duas copias, com o mesmo SHA-256 do registro e da ficha; so arquivos cifrados e fichas nos destinos
    for d in cfg['destinos']:
        assert arquivos(d['pasta']) == [f'{bid}.cfbak', f'{bid}.ficha.json']
        assert sha(Path(d['pasta']) / f'{bid}.cfbak') == reg['sha256_cifrado'] and reg['destinos'][d['nome']]['estado'] == 'VERIFICADO'
        assert (Path(d['pasta']) / f'{bid}.cfbak').stat().st_size == reg['bytes_cifrado']
    ficha = json.loads((Path(cfg['destinos'][0]['pasta']) / f'{bid}.ficha.json').read_text(encoding='utf-8'))
    assert ficha['sha256_cifrado'] == reg['sha256_cifrado'] and ficha['chave_id'] == item['chave_id'] and ficha['tipo'] == 'SEMANAL'
    # nada em texto claro ficou para tras; o arquivo guardado e cifrado (sem os dumps legiveis)
    assert arquivos(cfg['trabalho']) == []
    cifrado = (Path(cfg['destinos'][1]['pasta']) / f'{bid}.cfbak').read_bytes()
    assert cifrado[:7] == b'CFBAK2\n' and b'PGDMP' not in cifrado and R.ler_cabecalho(cifrado)['chave_id'] == item['chave_id']
    # verificacao mensal e ensaio trimestral (restauracao homologada num banco descartavel), a partir da copia guardada
    assert R.main(['conferir'], cfg=cfg) == 0 and ultimo(cfg)['operacao'] == 'CONFERENCIA'
    assert R.main(['ensaiar'], cfg=cfg) == 0
    ensaio = ultimo(cfg)
    assert ensaio['homologacao'].startswith('HOMOLOGADO') and ensaio['documentos'] == {'total': 1, 'sha256_iguais': 1}
    assert arquivos(cfg['trabalho']) == []
    # recuperacao: decifrar numa pasta protegida e verificar pela ferramenta homologada; o manifesto identifica a chave
    R.decifrar(cfg, Path(cfg['destinos'][0]['pasta']) / f'{bid}.cfbak', tmp_path / 'recuperado')
    manifesto = B.main(['verificar', '--manifesto', str(next((tmp_path / 'recuperado').glob('manifesto_*.json')))])
    assert manifesto['rotina'] == {'versao': R.VERSAO, 'tipo': 'SEMANAL', 'migration': None, 'chave_id': item['chave_id']}
    with pytest.raises(R.Falha):  # nao extrai por cima de uma pasta com arquivos
        R.decifrar(cfg, Path(cfg['destinos'][0]['pasta']) / f'{bid}.cfbak', tmp_path / 'recuperado')
    # backup identificado como PRE_MIGRATION, com o identificador da migration
    time.sleep(1.1)
    assert R.main(['executar', '--tipo', 'PRE_MIGRATION', '--migration', '20261201090000_exemplo'], cfg=cfg) == 0
    pre = ultimo(cfg)
    assert pre['tipo'] == 'PRE_MIGRATION' and pre['migration'] == '20261201090000_exemplo' and pre['backup_id'] != bid
    assert len(arquivos(cfg['destinos'][0]['pasta'])) == 4 and sha(Path(cfg['destinos'][0]['pasta']) / f'{bid}.cfbak') == reg['sha256_cifrado']
    s = R.situacao(cfg)
    assert s['ultimo_valido'] == pre['backup_id'] and s['avisos'] == [] and s['total_guardados'] == 2
    # 17. nenhuma credencial ou chave em saidas, registro, fichas ou manifesto
    chave_hex = (Path(cfg['pasta_chaves']) / item['arquivo']).read_text(encoding='ascii')
    textos = capsys.readouterr()
    tudo = (textos.out + textos.err + Path(cfg['registro']).read_text(encoding='utf-8')
            + (Path(cfg['pasta_chaves']) / 'chaves.json').read_text(encoding='utf-8')
            + ''.join(p.read_text(encoding='utf-8') for d in cfg['destinos'] for p in Path(d['pasta']).glob('*.json'))
            + ''.join(p.read_text(encoding='utf-8') for p in (tmp_path / 'recuperado').glob('*.json')))
    assert SENHA not in tudo and cfg['_dsn'] not in tudo and chave_hex not in tudo and '127.0.0.1:' not in tudo


# 2 e 3. chave ------------------------------------------------------------------------------------------------------

def test_chave_ausente_sem_guarda_ou_incorreta_interrompe_antes_de_exportar(cfg, pendrive, monkeypatch, capsys):
    chamadas = []
    monkeypatch.setattr(B, 'exportar', lambda args: chamadas.append(args))
    # sem chave do ano
    assert R.main(['executar'], cfg=cfg) == 1 and ultimo(cfg)['estado'] == 'FALHA_CHAVE' and 'nao ha chave mestra' in ultimo(cfg)['erro']
    # chave criada, mas sem copia externa confirmada
    item = R.chave_criar(cfg, AGORA.year, agora=AGORA)
    assert R.main(['executar'], cfg=cfg) == 1 and 'copia externa' in ultimo(cfg)['erro']
    arquivo = Path(cfg['pasta_chaves']) / item['arquivo']
    # a "copia" num disco do proprio computador nao vale; uma copia diferente tambem nao
    mesma = Path(cfg['trabalho']).parent / 'copia.chave'
    mesma.write_bytes(arquivo.read_bytes())
    with pytest.raises(R.Falha) as e:
        R.chave_confirmar_guarda(cfg, AGORA.year, copia=str(mesma))
    assert 'disco deste computador' in str(e.value)
    (pendrive / 'outra.chave').write_text(os.urandom(32).hex(), encoding='ascii')
    with pytest.raises(R.Falha) as e:
        R.chave_confirmar_guarda(cfg, AGORA.year, copia=str(pendrive / 'outra.chave'))
    assert 'nao e igual' in str(e.value)
    with pytest.raises(R.Falha):  # cofre de senhas: valor digitado errado
        R.chave_confirmar_guarda(cfg, AGORA.year, digitar=True, ler=lambda _: 'ab' * 32)
    assert R.ler_chaves(cfg)['chaves'][0]['guardas'] == []
    R.chave_confirmar_guarda(cfg, AGORA.year, digitar=True, ler=lambda _: arquivo.read_text(encoding='ascii'))
    assert R.ler_chaves(cfg)['chaves'][0]['guardas'][0]['meio'].startswith('cofre')
    # a chave vigente nao e substituida
    with pytest.raises(R.Falha) as e:
        R.chave_criar(cfg, AGORA.year, agora=AGORA)
    assert 'nada foi substituido' in str(e.value) and not os.access(arquivo, os.W_OK)
    # arquivo de chave trocado (chave incorreta): recusado antes da exportacao
    original = arquivo.read_bytes()
    os.chmod(arquivo, stat.S_IWRITE | stat.S_IREAD)
    arquivo.write_text(os.urandom(32).hex(), encoding='ascii')
    assert R.main(['executar'], cfg=cfg) == 1 and 'nao confere com o registro' in ultimo(cfg)['erro']
    # arquivo de chave ausente
    arquivo.unlink()
    assert R.main(['executar'], cfg=cfg) == 1 and 'ausente' in ultimo(cfg)['erro']
    assert all(r['estado'] == 'FALHA_CHAVE' and r['exportacao'] == 'NAO_INICIADA' for r in R.ler_registro(cfg))
    assert chamadas == [] and nada_guardado(cfg) and arquivos(cfg['trabalho']) == []
    saida = capsys.readouterr().out
    assert original.decode() not in saida and 'BACKUP CONCLUIDO' not in saida


def test_backup_nao_abre_com_a_chave_errada(cfg, pendrive):
    item = criar_chave(cfg, pendrive)
    assert R.executar(cfg)['estado'] == 'CONCLUIDO'
    arquivo = Path(cfg['pasta_chaves']) / item['arquivo']
    os.chmod(arquivo, stat.S_IWRITE | stat.S_IREAD)
    arquivo.write_text(os.urandom(32).hex(), encoding='ascii')
    registro = R.ler_chaves(cfg)  # mesmo que o indice fosse ajustado para a chave errada, a decifragem falha
    registro['chaves'][0]['sha256_arquivo'] = sha(arquivo)
    R._gravar_chaves(cfg, registro)
    assert R.main(['conferir'], cfg=cfg) == 1
    assert ultimo(cfg)['estado'] == 'FALHA_CHAVE' and 'chave incorreta ou arquivo alterado' in ultimo(cfg)['erro']
    assert arquivos(cfg['trabalho']) == []


# 4, 5, 6 e 7. preparacao, exportacao e criptografia -----------------------------------------------------------------

def test_espaco_insuficiente_e_falha_de_conexao_nao_iniciam_a_exportacao(cfg, pendrive, monkeypatch, capsys):
    criar_chave(cfg, pendrive)
    chamadas = []
    exportar = B.exportar
    monkeypatch.setattr(B, 'exportar', lambda args: chamadas.append(args))
    monkeypatch.setattr(R.shutil, 'disk_usage', lambda pasta: types.SimpleNamespace(free=1000))
    assert R.main(['executar'], cfg=cfg) == 1
    assert ultimo(cfg)['estado'] == 'FALHA_PREPARACAO' and 'espaco insuficiente' in ultimo(cfg)['erro']
    monkeypatch.undo()
    monkeypatch.setattr(B, 'exportar', lambda args: chamadas.append(args))
    # conexao recusada (porta sem servidor)
    Path(cfg['arquivo_env']).write_text(f'DATABASE_URL=postgresql://postgres:{SENHA}@127.0.0.1:9/postgres\n', encoding='utf-8')
    assert R.main(['executar'], cfg=cfg) == 1
    assert ultimo(cfg)['estado'] == 'FALHA_PREPARACAO' and 'falha de conexao' in ultimo(cfg)['erro']
    # arquivo de ambiente de outro projeto: recusado sem conectar
    Path(cfg['arquivo_env']).write_text(f'DATABASE_URL=postgresql://postgres.abcdefghijklmnopqrst:{SENHA}@aws-0-us-east-2.pooler.supabase.com:6543/postgres\n',
                                        encoding='utf-8')
    assert R.main(['executar'], cfg=cfg) == 1 and 'projeto esperado' in ultimo(cfg)['erro']
    assert all(r['exportacao'] == 'NAO_INICIADA' for r in R.ler_registro(cfg))
    assert chamadas == [] and nada_guardado(cfg) and arquivos(cfg['trabalho']) == []
    saida = capsys.readouterr().out + Path(cfg['registro']).read_text(encoding='utf-8')
    assert SENHA not in saida and 'pooler.supabase.com' not in saida and 'BACKUP CONCLUIDO' not in saida
    assert exportar is not None


def test_falha_na_exportacao_ou_na_criptografia_nao_guarda_nada_nem_deixa_texto_claro(cfg, pendrive, monkeypatch, capsys):
    criar_chave(cfg, pendrive)
    exportar = B.exportar

    def exportacao_que_falha(args):  # deixa um dump pela metade e falha repetindo a conexao
        (Path(args.saida) / 'banco_parcial.dump').write_bytes(b'PGDMP parcial')
        raise SystemExit(f'pg_dump (banco) falhou (codigo 1): {cfg["_dsn"]}')
    monkeypatch.setattr(B, 'exportar', exportacao_que_falha)
    assert R.main(['executar'], cfg=cfg) == 1
    reg = ultimo(cfg)
    assert reg['estado'] == 'FALHA_EXPORTACAO' and reg['exportacao'] == 'FALHA' and reg['criptografia'] == 'NAO_INICIADA'
    assert reg['limpeza'] == 'OK' and nada_guardado(cfg) and arquivos(cfg['trabalho']) == []
    monkeypatch.setattr(B, 'exportar', exportar)

    def cifragem_que_falha(*a, **k):
        raise RuntimeError('falha simulada na cifragem')
    monkeypatch.setattr(R, 'cifrar_pacote', cifragem_que_falha)
    assert R.main(['executar'], cfg=cfg) == 1
    reg = ultimo(cfg)
    assert reg['estado'] == 'FALHA_CRIPTOGRAFIA' and reg['exportacao'] == 'OK' and reg['criptografia'] == 'FALHA'
    assert all(d['estado'] == 'NAO_INICIADA' for d in reg['destinos'].values())
    assert nada_guardado(cfg) and arquivos(cfg['trabalho']) == []  # nenhum texto claro copiado nem deixado
    saida = capsys.readouterr().out + Path(cfg['registro']).read_text(encoding='utf-8')
    assert SENHA not in saida and cfg['_dsn'] not in saida and 'BACKUP CONCLUIDO' not in saida


def test_manifesto_adulterado_e_recusado(cfg, pendrive, monkeypatch):
    criar_chave(cfg, pendrive)
    exportar = B.exportar

    def exportacao_adulterada(args):
        caminho = Path(exportar(args))
        dump = caminho.parent / json.loads(caminho.read_text(encoding='utf-8'))['documentos']
        dump.write_bytes(dump.read_bytes() + b'x')
        return caminho
    monkeypatch.setattr(B, 'exportar', exportacao_adulterada)
    reg = R.executar(cfg)
    assert reg['estado'] == 'FALHA_INTEGRIDADE' and reg['verificacao'] == 'FALHA' and 'alterados ou corrompidos' in reg['erro']
    assert nada_guardado(cfg) and arquivos(cfg['trabalho']) == []


# 8, 9 e 10. copias --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('falho', ['local', 'onedrive'])
def test_falha_de_copia_num_destino_indica_qual_preserva_a_outra_e_completar_termina(falho, cfg, pendrive, monkeypatch, capsys):
    criar_chave(cfg, pendrive)
    pasta_falha = next(Path(d['pasta']) for d in cfg['destinos'] if d['nome'] == falho)
    copiar = R._copiar_arquivo

    def copia_que_falha(origem, destino):
        if R._dentro(destino, pasta_falha):
            raise PermissionError('destino indisponivel (simulado)')
        copiar(origem, destino)
    monkeypatch.setattr(R, '_copiar_arquivo', copia_que_falha)
    assert R.main(['executar'], cfg=cfg) == 1
    reg = ultimo(cfg)
    outro = next(d for d in cfg['destinos'] if d['nome'] != falho)
    bid = reg['backup_id']
    assert reg['estado'] == 'FALHA_COPIA' and reg['destinos'][falho]['estado'] == 'FALHA_COPIA' and f'destino "{falho}"' in reg['erro']
    assert reg['destinos'][outro['nome']]['estado'] == 'VERIFICADO' and arquivos(pasta_falha) == []
    assert sha(Path(outro['pasta']) / f'{bid}.cfbak') == reg['sha256_cifrado']  # a copia cifrada integra foi preservada
    assert sem_texto_claro(cfg) and 'BACKUP CONCLUIDO' not in capsys.readouterr().out
    s = R.situacao(cfg)
    assert s['ultimo_valido'] is None and any('NAO HA BACKUP VALIDO' in a for a in s['avisos'])
    assert R.retencao(cfg)['incompletos'] == [bid]
    # resolvido o destino, "completar" copia so o que falta, confere e nao sobrescreve a copia boa
    monkeypatch.setattr(R, '_copiar_arquivo', copiar)
    antes = (Path(outro['pasta']) / f'{bid}.cfbak').stat().st_mtime_ns
    assert R.main(['completar', '--backup-id', bid], cfg=cfg) == 0
    assert sha(pasta_falha / f'{bid}.cfbak') == reg['sha256_cifrado'] and (Path(outro['pasta']) / f'{bid}.cfbak').stat().st_mtime_ns == antes
    assert R.situacao(cfg)['ultimo_valido'] == bid and R.main(['conferir'], cfg=cfg) == 0


def test_falha_nos_dois_destinos_preserva_a_copia_cifrada_na_pasta_de_trabalho(cfg, pendrive, monkeypatch):
    criar_chave(cfg, pendrive)
    copiar = R._copiar_arquivo

    def copia_que_falha(origem, destino):
        raise OSError('destinos indisponiveis (simulado)')
    monkeypatch.setattr(R, '_copiar_arquivo', copia_que_falha)
    reg = R.executar(cfg)
    bid = reg['backup_id']
    assert reg['estado'] == 'FALHA_COPIA' and nada_guardado(cfg)
    assert arquivos(cfg['trabalho']) == [f'{bid}.cfbak', f'{bid}.ficha.json']  # so o cifrado e a ficha; nenhum dump
    monkeypatch.setattr(R, '_copiar_arquivo', copiar)
    assert R.completar(cfg, bid)['estado'] == 'CONCLUIDO'
    assert all(sha(Path(d['pasta']) / f'{bid}.cfbak') == reg['sha256_cifrado'] for d in cfg['destinos'])
    assert arquivos(cfg['trabalho']) == [] and R.conferir(cfg)['estado'] == 'CONCLUIDO'


def test_hash_divergente_no_destino_recusa_o_backup(cfg, pendrive, monkeypatch, capsys):
    criar_chave(cfg, pendrive)
    copiar = R._copiar_arquivo
    onedrive = Path(cfg['destinos'][1]['pasta'])

    def copia_corrompida(origem, destino):
        copiar(origem, destino)
        if R._dentro(destino, onedrive) and '.cfbak' in Path(destino).name:
            dados = bytearray(Path(destino).read_bytes())
            dados[len(dados) // 2] ^= 0xFF
            Path(destino).write_bytes(bytes(dados))
    monkeypatch.setattr(R, '_copiar_arquivo', copia_corrompida)
    assert R.main(['executar'], cfg=cfg) == 1
    reg = ultimo(cfg)
    assert reg['estado'] == 'FALHA_INTEGRIDADE' and reg['destinos']['onedrive']['estado'] == 'FALHA_INTEGRIDADE'
    assert reg['destinos']['local']['estado'] == 'VERIFICADO' and arquivos(onedrive) == []  # a copia divergente nao fica com nome de backup
    assert 'BACKUP CONCLUIDO' not in capsys.readouterr().out and R.situacao(cfg)['ultimo_valido'] is None
    # copia guardada que se altera depois: a conferencia mensal acusa
    monkeypatch.setattr(R, '_copiar_arquivo', copiar)
    assert R.completar(cfg, reg['backup_id'])['estado'] == 'CONCLUIDO'
    guardado = onedrive / f'{reg["backup_id"]}.cfbak'
    dados = bytearray(guardado.read_bytes())
    dados[-1] ^= 0xFF
    guardado.write_bytes(bytes(dados))
    conferencia = R.conferir(cfg)
    assert conferencia['estado'] == 'FALHA_INTEGRIDADE' and conferencia['destinos'] == {'local': {'estado': 'VERIFICADO'}, 'onedrive': {'estado': 'FALHA_INTEGRIDADE'}}


# 11. reexecucao -----------------------------------------------------------------------------------------------------

def test_reexecucao_com_nome_existente_nao_sobrescreve(cfg, pendrive, monkeypatch):
    criar_chave(cfg, pendrive)
    fixo = dt.datetime(AGORA.year, AGORA.month, AGORA.day, 3, 4, 5)

    class Relogio(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixo
    monkeypatch.setattr(B, 'dt', types.SimpleNamespace(datetime=Relogio))
    primeira = R.executar(cfg, agora=fixo)
    assert primeira['estado'] == 'CONCLUIDO'
    antes = {d['nome']: (sha(Path(d['pasta']) / f'{primeira["backup_id"]}.cfbak'), (Path(d['pasta']) / f'{primeira["backup_id"]}.cfbak').stat().st_mtime_ns)
             for d in cfg['destinos']}
    segunda = R.executar(cfg, agora=fixo + dt.timedelta(minutes=1))  # o mesmo identificador de backup
    assert segunda['backup_id'] == primeira['backup_id'] and segunda['estado'] == 'FALHA_COPIA' and 'nada foi sobrescrito' in segunda['erro']
    depois = {d['nome']: (sha(Path(d['pasta']) / f'{primeira["backup_id"]}.cfbak'), (Path(d['pasta']) / f'{primeira["backup_id"]}.cfbak').stat().st_mtime_ns)
              for d in cfg['destinos']}
    assert antes == depois and arquivos(cfg['trabalho']) == [] and len(arquivos(cfg['destinos'][0]['pasta'])) == 2
    # restos em texto claro de uma execucao interrompida bloqueiam a seguinte ate a limpeza
    resto = Path(cfg['trabalho']) / 'execucao-antiga' / 'banco_x.dump'
    resto.parent.mkdir(parents=True)
    resto.write_bytes(b'PGDMP resto')
    bloqueada = R.executar(cfg, agora=fixo + dt.timedelta(minutes=2))
    assert bloqueada['estado'] == 'FALHA_PREPARACAO' and 'limpar-trabalho' in bloqueada['erro'] and resto.exists()
    assert R.main(['limpar-trabalho'], cfg=cfg) == 0 and arquivos(cfg['trabalho']) == []


def test_falha_na_limpeza_e_informada_com_o_caminho_e_nao_vira_sucesso(cfg, pendrive, monkeypatch, capsys):
    criar_chave(cfg, pendrive)

    def nao_apaga(caminho):
        raise PermissionError('arquivo em uso (simulado)')
    monkeypatch.setattr(R, '_apagar_arquivo', nao_apaga)
    assert R.main(['executar'], cfg=cfg) == 1
    reg = ultimo(cfg)
    assert reg['estado'] == 'CONCLUIDO_COM_LIMPEZA_PENDENTE' and reg['limpeza'].startswith('FALHA') and cfg['trabalho'] in reg['erro']
    assert all(d['estado'] == 'VERIFICADO' for d in reg['destinos'].values())
    saida = capsys.readouterr().out
    assert 'BACKUP CONCLUIDO' not in saida and 'limpeza do texto claro esta pendente' in saida
    monkeypatch.undo()
    assert R.main(['limpar-trabalho'], cfg=cfg) == 0 and arquivos(cfg['trabalho']) == []


# 12 e 13. rotacao anual ---------------------------------------------------------------------------------------------

def test_rotacao_anual_preserva_a_chave_anterior_e_le_os_backups_antigos(cfg, pendrive, tmp_path):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    ano = AGORA.year
    dezembro, janeiro = dt.datetime(ano, 12, 28, 9, 0), dt.datetime(ano + 1, 1, 4, 9, 0)
    antiga = criar_chave(cfg, pendrive, ano, agora=dezembro)
    a = R.executar(cfg, agora=dezembro)
    assert a['estado'] == 'CONCLUIDO' and a['chave_id'] == antiga['chave_id']
    arquivo_antigo = Path(cfg['pasta_chaves']) / antiga['arquivo']
    conteudo_antigo, hash_a = arquivo_antigo.read_bytes(), sha(Path(cfg['destinos'][0]['pasta']) / f'{a["backup_id"]}.cfbak')
    # virou o ano: sem a chave nova, e depois sem a guarda externa dela, nada e exportado
    sem_chave = R.executar(cfg, agora=janeiro)
    assert sem_chave['estado'] == 'FALHA_CHAVE' and sem_chave['exportacao'] == 'NAO_INICIADA'
    with pytest.raises(R.Falha):
        R.chave_criar(cfg, ano + 3, agora=janeiro)
    nova = R.chave_criar(cfg, ano + 1, agora=janeiro)
    sem_guarda = R.executar(cfg, agora=janeiro)
    assert sem_guarda['estado'] == 'FALHA_CHAVE' and 'copia externa' in sem_guarda['erro']
    (pendrive / nova['arquivo']).write_bytes((Path(cfg['pasta_chaves']) / nova['arquivo']).read_bytes())
    R.chave_confirmar_guarda(cfg, ano + 1, copia=str(pendrive / nova['arquivo']), agora=janeiro)
    time.sleep(1.1)
    b = R.executar(cfg, agora=janeiro)
    assert b['estado'] == 'CONCLUIDO' and b['chave_id'] == nova['chave_id'] != antiga['chave_id']
    # as duas versoes registradas; a anterior intacta; o backup antigo nao foi recifrado nem excluido e segue legivel
    registro = R.ler_chaves(cfg)['chaves']
    assert [c['chave_id'] for c in registro] == [antiga['chave_id'], nova['chave_id']] and all(c['guardas'] for c in registro)
    assert arquivo_antigo.read_bytes() == conteudo_antigo and nova['chave_id'].startswith(str(ano + 1))
    assert sha(Path(cfg['destinos'][0]['pasta']) / f'{a["backup_id"]}.cfbak') == hash_a
    assert R.conferir(cfg, a['backup_id'])['estado'] == 'CONCLUIDO' and R.conferir(cfg, b['backup_id'])['estado'] == 'CONCLUIDO'
    assert R.ensaiar(cfg, a['backup_id'])['estado'] == 'CONCLUIDO'  # restauracao assistida de um backup da chave anterior
    with pytest.raises(R.Falha):
        R.chave_criar(cfg, ano, agora=janeiro)
    # sem a chave anterior no computador, o backup antigo nao abre (e a mensagem diz de onde recupera-la)
    os.chmod(arquivo_antigo, stat.S_IWRITE | stat.S_IREAD)
    guardada = tmp_path / 'chave_antiga_guardada'
    arquivo_antigo.rename(guardada)
    falha = R.conferir(cfg, a['backup_id'])
    assert falha['estado'] == 'FALHA_CHAVE' and 'copia externa' in falha['erro']
    guardada.rename(arquivo_antigo)
    # computador novo: so com os arquivos de chave vindos da copia externa (sem o indice), os backups abrem
    indice = Path(cfg['pasta_chaves']) / 'chaves.json'
    indice.rename(tmp_path / 'indice_guardado')
    assert R.conferir(cfg, a['backup_id'])['estado'] == 'CONCLUIDO' and R.conferir(cfg, b['backup_id'])['estado'] == 'CONCLUIDO'
    assert R.executar(cfg, agora=janeiro)['estado'] == 'FALHA_CHAVE'  # mas cifrar exige a chave registrada e com guarda
    (tmp_path / 'indice_guardado').rename(indice)
    # backup do FIN-REG-01 (formato CFBAK1, chave propria do backup) continua legivel
    chave1, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    (Path(cfg['pasta_chaves']) / 'cf-local-20261115_150732.chave').write_text(chave1.hex(), encoding='ascii')
    antigo = R.MAGICA1 + nonce + AESGCM(chave1).encrypt(nonce, b'pacote do REG-01', b'cf-local-20261115_150732')
    assert R.decifrar_pacote(cfg, antigo, 'cf-local-20261115_150732') == b'pacote do REG-01'


def test_cada_arquivo_tem_sal_e_nonce_proprios_e_o_cabecalho_e_autenticado(cfg):
    chave = os.urandom(32)
    um, outro = (R.cifrar_pacote(b'mesmo conteudo', chave, 'cf-local-x', '2026-abcdef12') for _ in range(2))
    c1, c2 = R.ler_cabecalho(um), R.ler_cabecalho(outro)
    assert c1['sal'] != c2['sal'] and c1['nonce'] != c2['nonce'] and um[c1['_fim']:] != outro[c2['_fim']:]
    assert chave.hex() not in um.decode('latin-1') and c1['chave_id'] == '2026-abcdef12'


# 14. aviso de atraso ------------------------------------------------------------------------------------------------

def test_aviso_de_backup_atrasado_sem_gerar_backup(cfg, capsys):
    assert any('NAO HA BACKUP VALIDO' in a for a in R.situacao(cfg)['avisos'])
    falso(cfg, 'cf-local-20261101_100000', dt.datetime(2026, 11, 1, 10, 0))
    em_dia = R.situacao(cfg, agora=dt.datetime(2026, 11, 11, 9, 0))
    assert em_dia['dias_desde_ultimo_valido'] == 9 and not any('ATRASADO' in a for a in em_dia['avisos'])
    atrasado = R.situacao(cfg, agora=dt.datetime(2026, 11, 12, 11, 0))
    assert atrasado['dias_desde_ultimo_valido'] == 11 and any('BACKUP ATRASADO' in a for a in atrasado['avisos'])
    assert atrasado['ultimo_valido'] == 'cf-local-20261101_100000' and atrasado['idade_mais_recente_dias'] == 11
    assert 'AVISO: BACKUP ATRASADO' in capsys.readouterr().out
    # a consulta nao gera backup nem registro de execucao
    assert len(arquivos(cfg['destinos'][0]['pasta'])) == 2 and R.ler_registro(cfg) == []
    # backup mais recente que so chegou a um destino nao conta como valido
    falso(cfg, 'cf-local-20261110_100000', dt.datetime(2026, 11, 10, 10, 0), destinos=['local'])
    parcial = R.situacao(cfg, agora=dt.datetime(2026, 11, 12, 11, 0))
    assert parcial['ultimo_valido'] == 'cf-local-20261101_100000' and parcial['mais_recente'] == 'cf-local-20261110_100000'
    assert any('nao esta integro' in a for a in parcial['avisos'])


# 15 e 16. retencao --------------------------------------------------------------------------------------------------

def test_retencao_identifica_candidatos_e_nao_exclui_nada(cfg, capsys):
    agora = dt.datetime(2027, 3, 20, 9, 0)
    semanais = [dt.datetime(2026, 11, 15, 15, 7) + dt.timedelta(days=7 * i) for i in range(18)]  # 15/11/2026 a 14/03/2027
    for d in semanais:
        falso(cfg, f'cf-local-{d:%Y%m%d_%H%M%S}', d)
    falso(cfg, 'cf-local-20261201_080000', dt.datetime(2026, 12, 1, 8, 0), tipo='PRE_MIGRATION')
    falso(cfg, 'cf-local-20270319_080000', dt.datetime(2027, 3, 19, 8, 0), tipo='PRE_MIGRATION')
    falso(cfg, 'cf-local-20270318_080000', dt.datetime(2027, 3, 18, 8, 0), destinos=['local'])
    antes = {d['nome']: arquivos(d['pasta']) for d in cfg['destinos']}
    r = R.retencao(cfg, agora=agora)
    ident = lambda d: f'cf-local-{d:%Y%m%d_%H%M%S}'  # noqa: E731
    assert all(r['manter'][ident(d)] == 'semanal (8 ultimos)' for d in semanais[-8:])
    assert r['manter'][ident(semanais[0])] == 'mensal (12 meses)'            # o primeiro de novembro
    assert r['manter'][ident(dt.datetime(2026, 12, 6, 15, 7))] == 'mensal (12 meses)'
    assert r['manter'][ident(dt.datetime(2026, 12, 27, 15, 7))] == 'anual (dezembro)'
    assert r['manter'][ident(dt.datetime(2027, 1, 3, 15, 7))] == 'mensal (12 meses)'
    assert r['manter']['cf-local-20270319_080000'] == 'pre-migration sem copia posterior'
    assert 'homologada a intervencao' in r['candidatos']['cf-local-20261201_080000']
    comuns = sorted(i for i, m in r['candidatos'].items() if m.startswith('fora dos 8'))
    assert comuns == [ident(d) for d in semanais if d not in semanais[-8:] and ident(d) not in r['manter']] and len(comuns) == 6
    assert r['incompletos'] == ['cf-local-20270318_080000']
    # o mensal vence aos 12 meses; o anual nao vence
    futuro = R.politica_retencao([{'backup_id': ident(d), 'gerado_em': d, 'tipo': 'SEMANAL', 'completo': True} for d in semanais],
                                 dt.datetime(2029, 1, 10))
    assert futuro['manter'][ident(dt.datetime(2026, 12, 27, 15, 7))] == 'anual (dezembro)' and ident(semanais[0]) in futuro['candidatos']
    # 16. nenhuma exclusao: a lista e so informativa
    assert {d['nome']: arquivos(d['pasta']) for d in cfg['destinos']} == antes
    assert R.main(['retencao'], cfg=cfg) == 0 and {d['nome']: arquivos(d['pasta']) for d in cfg['destinos']} == antes
    assert 'NENHUM ARQUIVO FOI EXCLUIDO' in capsys.readouterr().out


def test_a_rotina_nao_tem_comando_de_exclusao_de_backups_nem_agendamento():
    fonte = Path(R.__file__).read_text(encoding='utf-8')
    with pytest.raises(SystemExit):
        R.main(['excluir'], cfg={})
    assert 'schtasks' not in fonte and 'Register-ScheduledTask' not in fonte and 'crontab' not in fonte
    # as unicas remocoes sao de temporarios: _apagar_arquivo (pasta de trabalho) e o resto ".parcial" de uma copia que falhou
    assert fonte.count(".unlink()") == 3 and 'rmtree' not in fonte


# 18. protecoes do FIN-REG-01 ----------------------------------------------------------------------------------------

def test_protecoes_do_reg01_preservadas(cfg, monkeypatch):
    # a rotina nao reimplementa exportacao, verificacao nem restauracao: chama a ferramenta homologada
    fonte = Path(R.__file__).read_text(encoding='utf-8')
    assert 'pg_restore' not in fonte.split('def _preparar')[1].split('def _exportar')[1] and 'B.restaurar(' in fonte
    assert 'B.exportar(' in fonte and 'B.verificar(' in fonte
    # nenhum comando da rotina recebe conexao de destino: o ensaio cria o proprio banco local
    with pytest.raises(SystemExit):
        R.main(['ensaiar', '--dsn-env', 'QUALQUER'], cfg=cfg)
    # a conexao nunca vai para a linha de comando do pg_dump (PGPASSWORD no ambiente)
    conexao, ambiente, senha = B._sem_senha(cfg['_dsn'])
    assert SENHA not in conexao and ambiente['PGPASSWORD'] == senha == SENHA
    # pastas sincronizadas nao servem para texto claro nem para chaves
    with pytest.raises(R.Falha) as e:
        R._preparar({**cfg, 'trabalho': str(Path(cfg['trabalho']).parent / 'OneDrive' / 'trabalho')}, 'SEMANAL', None, AGORA)
    assert 'OneDrive' in str(e.value)
    with pytest.raises(R.Falha) as e:
        R.chave_criar({**cfg, 'pasta_chaves': str(Path(cfg['destinos'][1]['pasta']) / 'chaves')}, AGORA.year, agora=AGORA)
    assert 'dentro de um destino' in str(e.value)
    # a configuracao padrao aponta para a producao e para os destinos homologados; chaves fora do OneDrive
    assert R.PADRAO['projeto'] == 'fzjmgekasjrgvmfdkdog' and [d['pasta'] for d in R.PADRAO['destinos']] == [
        r'D:\CF-Backups', r'D:\OneDrive\Backups-Controle-Financeiro']
    assert 'onedrive' not in R.PADRAO['pasta_chaves'].lower() and 'onedrive' not in R.PADRAO['trabalho'].lower()
