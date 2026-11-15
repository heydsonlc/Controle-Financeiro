"""
FIN-REG-02 — rotina periodica de backup seguro (manual assistida). Coordena scripts/backup_banco.py (exportacao,
verificacao e restauracao homologadas no FIN-REG-01): aqui so ha a ordem das etapas, a cifragem, a copia para os
destinos, o registro e as consultas. Nada e agendado e NENHUM backup e excluido por esta rotina.

  executar [--tipo SEMANAL|PRE_MIGRATION|MANUTENCAO] [--migration ID]
        comando unico: valida a configuracao, identifica o projeto, confere a chave anual e a guarda externa dela, o
        espaco em disco e a conexao somente leitura; exporta; verifica o manifesto; cifra; valida a decifragem; copia
        para os dois destinos; confere os SHA-256 em cada um; registra; apaga o texto claro. So termina como CONCLUIDO
        com as duas copias verificadas.
  situacao                      ultimo backup valido, idade, ultima execucao, aviso de atraso (mais de 10 dias), chave.
  conferir [--backup-id ID]     mensal: hash das copias, decifragem e manifesto do backup mais recente (ou do indicado).
  ensaiar [--backup-id ID]      trimestral: restaura a copia guardada num PostgreSQL DESCARTAVEL local e exige HOMOLOGADO.
  retencao                      lista os backups alem da politica recomendada. So informa: nao exclui nada.
  completar --backup-id ID      termina a copia de um backup que ficou so num destino (nunca sobrescreve).
  decifrar --arquivo A --saida P  recuperacao: extrai manifesto e dumps numa pasta protegida (texto claro).
  limpar-trabalho               apaga restos em texto claro de uma execucao interrompida.
  chave criar --ano AAAA        cria a chave mestra do ano (nunca substitui uma existente).
  chave confirmar-guarda --ano AAAA (--copia CAMINHO | --digitar)   confere a copia guardada fora do computador.
  chave situacao                chaves registradas (identificador e guarda; nunca o conteudo).

Chave mestra anual: um arquivo por ano na pasta de chaves (fora do OneDrive e do repositorio). Cada backup tem sal e
nonce proprios; a chave do arquivo e derivada da mestra (HKDF-SHA256) e a cifra e AES-256-GCM (formato CFBAK2). O
cabecalho do arquivo traz o identificador da chave, nunca a chave. Backups CFBAK1 (FIN-REG-01, chave propria) seguem
legiveis.

Configuracao: os padroes abaixo; um JSON apontado por CF_BACKUP_ROTINA_CONFIG troca qualquer item. A conexao vem do
arquivo de ambiente local e nunca e impressa, registrada ou passada na linha de comando.
"""
import argparse
import datetime as dt
import getpass
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import backup_banco as B  # noqa: E402

VERSAO = '1.0'
TIPOS = ('SEMANAL', 'PRE_MIGRATION', 'MANUTENCAO')
MAGICA1, MAGICA2 = b'CFBAK1\n', b'CFBAK2\n'
VARIAVEL_ORIGEM = 'CF_BACKUP_ROTINA_ORIGEM'
FORMATO = ('CFBAK2: "CFBAK2\\n"(7) + tamanho do cabecalho(2, big-endian) + cabecalho JSON (backup_id, chave_id, sal, nonce) '
           '+ AES-256-GCM(cifrado + etiqueta); chave do arquivo = HKDF-SHA256(chave mestra do ano, sal, info "CFBAK2|"+backup_id); '
           'dado associado = magica + tamanho + cabecalho; conteudo = tar com o manifesto e os 3 dumps')

PADRAO = {
    'projeto': 'fzjmgekasjrgvmfdkdog',
    'arquivo_env': str(RAIZ / '.env.staging'),
    'variavel_env': 'DATABASE_URL',
    'pg_bin': str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'cf-e2e' / 'pg17' / 'pgsql' / 'bin'),
    'trabalho': r'D:\CF-Backups\_trabalho',  # texto claro, temporario, fora do OneDrive
    'destinos': [{'nome': 'local', 'pasta': r'D:\CF-Backups'},
                 {'nome': 'onedrive', 'pasta': r'D:\OneDrive\Backups-Controle-Financeiro'}],
    'pasta_chaves': str(Path.home() / 'CF-Backup-Chave'),  # separada das copias cifradas
    'registro': r'D:\CF-Backups\registro_execucoes.jsonl',
    'espaco_minimo_mb': 300,
    'dias_aviso': 10,
}


class Falha(Exception):
    """Falha classificada (FIN-REG-02, item 11): PREPARACAO, EXPORTACAO, CRIPTOGRAFIA, COPIA, INTEGRIDADE, CHAVE, LIMPEZA."""

    def __init__(self, categoria, mensagem):
        super().__init__(mensagem)
        self.categoria = categoria


def configuracao():
    cfg = json.loads(json.dumps(PADRAO))
    arquivo = os.environ.get('CF_BACKUP_ROTINA_CONFIG')
    if arquivo:
        cfg.update(json.loads(Path(arquivo).read_text(encoding='utf-8')))
    return cfg


# ---------------------------------------------------------------- utilitarios

def _sha256(dados_ou_caminho):
    if isinstance(dados_ou_caminho, (bytes, bytearray)):
        return hashlib.sha256(dados_ou_caminho).hexdigest()
    return B._sha256(dados_ou_caminho)


def _limpo(texto, dsn=None):
    """Mensagem sem conexao, senha ou URL de banco, em uma linha curta."""
    texto = str(texto or '')
    if dsn:
        try:
            texto = B._limpar_saida(texto, dsn)
        except Exception:  # conexao ilegivel: cai no filtro geral
            texto = texto.replace(dsn, '<oculto>')
    texto = re.sub(r'postgres(ql)?://\S+', '<conexao>', texto)
    return ' '.join(texto.split())[:600]


def _sincronizada(pasta):
    return any('onedrive' in parte.lower() for parte in Path(pasta).resolve().parts)


def _volume(caminho):
    """Unidade (Windows) ou dispositivo (demais) onde o caminho esta."""
    caminho = Path(caminho).resolve()
    if os.name == 'nt':
        return caminho.drive.upper()
    while not caminho.exists():
        caminho = caminho.parent
    return str(caminho.stat().st_dev)


def _restringir(pasta):
    """Pasta temporaria de texto claro: acesso so do usuario atual."""
    if os.name == 'nt':
        usuario = os.environ.get('USERNAME') or getpass.getuser()
        dominio = os.environ.get('USERDOMAIN')
        conta = f'{dominio}\\{usuario}' if dominio else usuario
        r = subprocess.run(['icacls', str(pasta), '/inheritance:r', '/grant:r', f'{conta}:(OI)(CI)F'], capture_output=True)
        if r.returncode != 0:
            raise Falha('PREPARACAO', 'nao foi possivel restringir as permissoes da pasta temporaria')
    else:
        os.chmod(pasta, 0o700)


def _apagar_arquivo(caminho):
    """Apaga um temporario; sobrescreve antes (em SSD isso nao garante eliminacao irrecuperavel)."""
    caminho = Path(caminho)
    try:
        os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD)
        tamanho = caminho.stat().st_size
        with open(caminho, 'r+b') as f:
            restante = tamanho
            while restante > 0:
                bloco = min(restante, 1 << 20)
                f.write(b'\0' * bloco)
                restante -= bloco
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass  # a sobrescrita e um reforco; o que decide e a remocao abaixo
    caminho.unlink()


def _apagar_pasta_clara(pasta, manter=()):
    """Remove o conteudo de uma pasta temporaria (menos `manter`) e confere. Levanta Falha('LIMPEZA') com o caminho."""
    pasta = Path(pasta)
    if not pasta.exists():
        return
    try:
        for p in sorted(pasta.rglob('*'), key=lambda x: len(x.parts), reverse=True):
            if p.is_file() and p.name not in manter:
                _apagar_arquivo(p)
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        if not any(pasta.iterdir()):
            pasta.rmdir()
    except OSError as e:
        raise Falha('LIMPEZA', f'restou texto claro em {pasta} ({type(e).__name__}): apague a pasta manualmente '
                               'ou rode "limpar-trabalho"') from None
    restos = [p.name for p in pasta.rglob('*') if p.is_file() and p.name not in manter] if pasta.exists() else []
    if restos:
        raise Falha('LIMPEZA', f'restou texto claro em {pasta}: apague a pasta manualmente ou rode "limpar-trabalho"')


def _versao():
    base = B._identificacao_da_ferramenta()
    return {'rotina': VERSAO, 'rotina_sha256': _sha256(Path(__file__).resolve())[:16],
            'backup_banco_sha256': base['sha256'][:16], 'commit': base['commit']}


def _registrar(cfg, linha):
    caminho = Path(cfg['registro'])
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, 'a', encoding='utf-8') as f:
        f.write(json.dumps(linha, ensure_ascii=False, default=str) + '\n')


def ler_registro(cfg):
    caminho = Path(cfg['registro'])
    if not caminho.exists():
        return []
    return [json.loads(l) for l in caminho.read_text(encoding='utf-8').splitlines() if l.strip()]


def _conexao(cfg):
    """Conexao da origem, lida do arquivo de ambiente local. Nunca impressa."""
    from dotenv import dotenv_values
    arquivo = Path(cfg['arquivo_env'])
    if not arquivo.exists():
        raise Falha('PREPARACAO', f'arquivo de ambiente nao encontrado: {arquivo.name}')
    dsn = dotenv_values(arquivo, encoding='utf-8-sig').get(cfg['variavel_env']) or ''
    if not dsn:
        raise Falha('PREPARACAO', f'{cfg["variavel_env"]} vazia em {arquivo.name}')
    try:
        ref = B._ref(dsn)
    except Exception:
        raise Falha('PREPARACAO', 'conexao ilegivel no arquivo de ambiente') from None
    if ref != cfg['projeto']:
        raise Falha('PREPARACAO', f'o arquivo de ambiente nao aponta para o projeto esperado ({cfg["projeto"] or "banco local"}): '
                                  'nada foi feito')
    return dsn


# ---------------------------------------------------------------- chaves

def _arquivo_registro_chaves(cfg):
    return Path(cfg['pasta_chaves']) / 'chaves.json'


def ler_chaves(cfg):
    arquivo = _arquivo_registro_chaves(cfg)
    return json.loads(arquivo.read_text(encoding='utf-8')) if arquivo.exists() else {'chaves': []}


def _gravar_chaves(cfg, registro):
    arquivo = _arquivo_registro_chaves(cfg)
    provisorio = arquivo.with_suffix('.json.novo')
    provisorio.write_text(json.dumps(registro, indent=1, ensure_ascii=False), encoding='utf-8')
    os.replace(provisorio, arquivo)  # so o indice (sem conteudo de chave); os arquivos .chave nunca sao regravados


def _nome_chave(cfg, ano):
    return f'cf-{cfg["projeto"] or "local"}-mestra-{ano}.chave'


def _ler_arquivo_chave(caminho):
    """(bytes da chave, SHA-256 do arquivo). O SHA-256 e o mesmo que `certutil -hashfile <arquivo> SHA256` mostra."""
    bruto = Path(caminho).read_bytes()
    try:
        chave = bytes.fromhex(bruto.decode('ascii').strip())
    except (UnicodeDecodeError, ValueError):
        raise Falha('CHAVE', 'arquivo de chave ilegivel') from None
    if len(chave) != 32:
        raise Falha('CHAVE', 'arquivo de chave com tamanho inesperado')
    return chave, _sha256(bruto)


def chave_criar(cfg, ano, agora=None):
    agora = agora or dt.datetime.now()
    ano = int(ano)
    if ano not in (agora.year, agora.year + 1):
        raise Falha('CHAVE', 'so e possivel criar a chave do ano corrente ou do proximo')
    pasta = Path(cfg['pasta_chaves'])
    if _sincronizada(pasta) or any(_dentro(pasta, d['pasta']) for d in cfg['destinos']):
        raise Falha('CHAVE', 'a pasta de chaves nao pode ficar no OneDrive nem dentro de um destino de backup')
    registro = ler_chaves(cfg)
    arquivo = pasta / _nome_chave(cfg, ano)
    if arquivo.exists() or any(c['ano'] == ano for c in registro['chaves']):
        raise Falha('CHAVE', f'ja existe chave mestra de {ano}: nada foi substituido')
    pasta.mkdir(parents=True, exist_ok=True)
    conteudo = os.urandom(32).hex().encode('ascii')
    with open(arquivo, 'xb') as f:  # 'x': falha se o arquivo existir
        f.write(conteudo)
    os.chmod(arquivo, stat.S_IREAD)
    impressao = _sha256(conteudo)
    item = {'chave_id': f'{ano}-{impressao[:8]}', 'ano': ano, 'arquivo': arquivo.name, 'sha256_arquivo': impressao,
            'criada_em': agora.isoformat(timespec='seconds'), 'guardas': []}
    registro['chaves'].append(item)
    _gravar_chaves(cfg, registro)
    print(f'Chave mestra de {ano} criada: {arquivo.name} (identificador {item["chave_id"]}).')
    print('PROXIMO PASSO, antes de qualquer backup com ela: copie o arquivo para fora deste computador (pendrive ou cofre '
          'de senhas; nunca o OneDrive) e rode: chave confirmar-guarda --ano', ano, '--copia <caminho da copia>')
    return item


def _dentro(caminho, pasta):
    try:
        Path(caminho).resolve().relative_to(Path(pasta).resolve())
        return True
    except ValueError:
        return False


def _item_chave(cfg, ano=None, chave_id=None):
    for c in ler_chaves(cfg)['chaves']:
        if (ano is not None and c['ano'] == int(ano)) or (chave_id is not None and c['chave_id'] == chave_id):
            return c
    return None


def _carregar(cfg, item):
    arquivo = Path(cfg['pasta_chaves']) / item['arquivo']
    if not arquivo.exists():
        raise Falha('CHAVE', f'arquivo da chave {item["chave_id"]} ausente da pasta de chaves: recupere-o da copia externa')
    chave, impressao = _ler_arquivo_chave(arquivo)
    if impressao != item['sha256_arquivo']:
        raise Falha('CHAVE', f'o arquivo da chave {item["chave_id"]} nao confere com o registro (chave incorreta ou alterada)')
    return chave


def chave_vigente(cfg, ano):
    """Chave mestra do ano, pronta para cifrar: existe, confere com o registro e tem guarda externa confirmada."""
    item = _item_chave(cfg, ano=ano)
    if not item:
        raise Falha('CHAVE', f'nao ha chave mestra de {ano}. Crie com "chave criar --ano {ano}", guarde uma copia fora do '
                             'computador e confirme com "chave confirmar-guarda"')
    chave = _carregar(cfg, item)
    if not item['guardas']:
        raise Falha('CHAVE', f'a chave {item["chave_id"]} ainda nao tem copia externa confirmada. Copie o arquivo '
                             f'{item["arquivo"]} para fora do computador e rode "chave confirmar-guarda --ano {ano} '
                             '--copia <caminho>" (ou --digitar, para a copia num cofre de senhas)')
    return chave, item['chave_id']


def chave_confirmar_guarda(cfg, ano, copia=None, digitar=False, agora=None, ler=getpass.getpass):
    agora = agora or dt.datetime.now()
    item = _item_chave(cfg, ano=ano)
    if not item:
        raise Falha('CHAVE', f'nao ha chave mestra de {ano} registrada')
    _carregar(cfg, item)
    if bool(copia) == bool(digitar):
        raise Falha('CHAVE', 'informe --copia <caminho> ou --digitar')
    if copia:
        copia = Path(copia)
        if not copia.is_file():
            raise Falha('CHAVE', 'copia nao encontrada no caminho informado')
        proibidos = {_volume(cfg['pasta_chaves']), _volume(cfg['trabalho']), *(_volume(d['pasta']) for d in cfg['destinos'])}
        if _volume(copia) in proibidos or _sincronizada(copia):
            raise Falha('CHAVE', 'a copia esta num disco deste computador ou no OneDrive: guarde-a num pendrive, disco '
                                 'externo ou cofre de senhas')
        if _ler_arquivo_chave(copia)[0].hex() != _carregar(cfg, item).hex():
            raise Falha('CHAVE', 'a copia nao e igual a chave registrada')
        guarda = {'meio': 'arquivo em outro volume', 'volume': _volume(copia)}
    else:
        digitado = (ler('Cole a chave guardada no cofre de senhas (nao aparece na tela): ') or '').strip().lower()
        if digitado != _carregar(cfg, item).hex():
            raise Falha('CHAVE', 'o valor digitado nao e igual a chave registrada')
        guarda = {'meio': 'cofre de senhas (valor conferido por digitacao)'}
    guarda['confirmada_em'] = agora.isoformat(timespec='seconds')
    registro = ler_chaves(cfg)
    next(c for c in registro['chaves'] if c['chave_id'] == item['chave_id'])['guardas'].append(guarda)
    _gravar_chaves(cfg, registro)
    print(f'Guarda externa da chave {item["chave_id"]} confirmada ({guarda["meio"]}).')
    return guarda


def chave_situacao(cfg):
    itens = ler_chaves(cfg)['chaves']
    for c in itens:
        presente = (Path(cfg['pasta_chaves']) / c['arquivo']).exists()
        print(f'chave {c["chave_id"]} (ano {c["ano"]}): arquivo {"presente" if presente else "AUSENTE"}; '
              f'guardas externas confirmadas: {len(c["guardas"])}')
    if not itens:
        print('Nenhuma chave mestra anual registrada.')
    return itens


def _chave_por_id(cfg, chave_id):
    """Chave para DECIFRAR. Pelo indice; sem ele (computador novo, so com a copia externa da chave), por qualquer arquivo
    .chave da pasta cuja impressao digital corresponda ao identificador gravado no backup."""
    item = _item_chave(cfg, chave_id=chave_id)
    if item:
        return _carregar(cfg, item)
    pasta = Path(cfg['pasta_chaves'])
    for arquivo in (sorted(pasta.glob('*.chave')) if pasta.is_dir() else []):
        try:
            chave, impressao = _ler_arquivo_chave(arquivo)
        except Falha:
            continue
        if chave_id.split('-', 1)[-1] == impressao[:8]:
            return chave
    raise Falha('CHAVE', f'chave {chave_id} ausente da pasta de chaves: recupere-a da copia externa')


# ---------------------------------------------------------------- cifragem

def cifrar_pacote(claro, chave, backup_id, chave_id):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    sal, nonce = os.urandom(16), os.urandom(12)  # proprios de cada arquivo
    cabecalho = json.dumps({'backup_id': backup_id, 'chave_id': chave_id, 'kdf': 'HKDF-SHA256', 'cifra': 'AES-256-GCM',
                            'sal': sal.hex(), 'nonce': nonce.hex()}, sort_keys=True).encode('ascii')
    prefixo = MAGICA2 + len(cabecalho).to_bytes(2, 'big') + cabecalho
    do_arquivo = HKDF(algorithm=hashes.SHA256(), length=32, salt=sal, info=b'CFBAK2|' + backup_id.encode()).derive(chave)
    return prefixo + AESGCM(do_arquivo).encrypt(nonce, claro, prefixo)


def ler_cabecalho(dados):
    """Cabecalho de um .cfbak: {'formato', 'chave_id', ...}. CFBAK1 nao tem cabecalho (chave propria do backup)."""
    if dados[:7] == MAGICA1:
        return {'formato': 'CFBAK1'}
    if dados[:7] != MAGICA2:
        raise Falha('INTEGRIDADE', 'arquivo nao e um backup CFBAK')
    tamanho = int.from_bytes(dados[7:9], 'big')
    try:
        return {'formato': 'CFBAK2', **json.loads(dados[9:9 + tamanho].decode('ascii')), '_fim': 9 + tamanho}
    except (UnicodeDecodeError, ValueError):
        raise Falha('INTEGRIDADE', 'cabecalho do backup ilegivel') from None


def decifrar_pacote(cfg, dados, backup_id):
    """Pacote claro (tar) de um .cfbak, com a chave indicada no cabecalho (anual) ou a propria do backup (CFBAK1)."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    cab = ler_cabecalho(dados)
    try:
        if cab['formato'] == 'CFBAK1':
            arquivo = Path(cfg['pasta_chaves']) / f'{backup_id}.chave'
            if not arquivo.exists():
                raise Falha('CHAVE', f'chave propria do backup {backup_id} ausente da pasta de chaves')
            chave, _ = _ler_arquivo_chave(arquivo)
            return AESGCM(chave).decrypt(dados[7:19], dados[19:], backup_id.encode())
        if cab['backup_id'] != backup_id:
            raise Falha('INTEGRIDADE', 'o cabecalho do arquivo indica outro backup')
        chave = _chave_por_id(cfg, cab['chave_id'])
        do_arquivo = HKDF(algorithm=hashes.SHA256(), length=32, salt=bytes.fromhex(cab['sal']),
                          info=b'CFBAK2|' + backup_id.encode()).derive(chave)
        return AESGCM(do_arquivo).decrypt(bytes.fromhex(cab['nonce']), dados[cab['_fim']:], dados[:cab['_fim']])
    except InvalidTag:
        raise Falha('CHAVE', 'a decifragem falhou: chave incorreta ou arquivo alterado') from None


# ---------------------------------------------------------------- copias guardadas

def _copiar_arquivo(origem, destino):
    shutil.copyfile(origem, destino)


def _guardar(origem, pasta, sha_esperado):
    """Copia um arquivo para o destino com nome provisorio, confere o SHA-256 relido do destino e so entao da o nome
    final. Nunca sobrescreve."""
    final = Path(pasta) / Path(origem).name
    provisorio = final.with_name(final.name + '.parcial')
    if final.exists() or provisorio.exists():
        raise Falha('COPIA', f'ja existe {final.name} no destino: nada foi sobrescrito')
    try:
        _copiar_arquivo(origem, provisorio)
        confere = _sha256(provisorio) == sha_esperado
        if confere:
            os.rename(provisorio, final)
    except OSError as e:
        if provisorio.exists():
            try:
                provisorio.unlink()  # resto da propria copia que falhou; nunca foi um backup
            except OSError:
                pass
        raise Falha('COPIA', f'copia de {final.name} falhou ({type(e).__name__})') from None
    if not confere:
        try:
            provisorio.unlink()
        except OSError:
            pass
        raise Falha('INTEGRIDADE', f'SHA-256 de {final.name} no destino difere do original: copia recusada')
    if _sha256(final) != sha_esperado:
        raise Falha('INTEGRIDADE', f'SHA-256 de {final.name} no destino difere do original')


def _guardar_no_destino(cfg, destino, cifrado, ficha, sha_cifrado):
    """Copia o .cfbak e a ficha para um destino. Devolve a situacao do destino (para o registro)."""
    try:
        if not Path(destino['pasta']).is_dir():
            raise Falha('COPIA', 'pasta do destino inacessivel')
        _guardar(cifrado, destino['pasta'], sha_cifrado)
        _guardar(ficha, destino['pasta'], _sha256(ficha))
        return {'estado': 'VERIFICADO', 'sha256': sha_cifrado}
    except Falha as f:
        return {'estado': f'FALHA_{f.categoria}', 'erro': _limpo(f)}


def listar(cfg):
    """Backups guardados, pelo que ha nos destinos: {backup_id: {'ficha': {...}, 'destinos': {nome: bool}}}."""
    backups = {}
    for d in cfg['destinos']:
        pasta = Path(d['pasta'])
        if not pasta.is_dir():
            continue
        for arquivo_ficha in pasta.glob('cf-*.ficha.json'):
            try:
                ficha = json.loads(arquivo_ficha.read_text(encoding='utf-8'))
            except ValueError:
                continue
            item = backups.setdefault(ficha['backup_id'], {'ficha': ficha, 'destinos': {x['nome']: False for x in cfg['destinos']}})
            item['destinos'][d['nome']] = (pasta / ficha['arquivo']).is_file()
    return backups


def _data(ficha):
    return dt.datetime.fromisoformat(ficha['gerado_em'])


def _copias_integras(cfg, ficha):
    """{destino: True/False}: o arquivo existe no destino e o SHA-256 confere com a ficha."""
    resultado = {}
    for d in cfg['destinos']:
        arquivo = Path(d['pasta']) / ficha['arquivo']
        resultado[d['nome']] = arquivo.is_file() and _sha256(arquivo) == ficha['sha256_cifrado']
    return resultado


def _escolher(cfg, backup_id=None):
    backups = listar(cfg)
    if not backups:
        raise Falha('INTEGRIDADE', 'nenhum backup encontrado nos destinos')
    if backup_id:
        if backup_id not in backups:
            raise Falha('INTEGRIDADE', f'backup {backup_id} nao encontrado nos destinos')
        return backups[backup_id]['ficha']
    return max((b['ficha'] for b in backups.values()), key=_data)


# ---------------------------------------------------------------- executar

def _preparar(cfg, tipo, migration, agora):
    """Etapas 1 a 5: nada e exportado aqui. Devolve (conexao, chave, chave_id)."""
    if tipo not in TIPOS:
        raise Falha('PREPARACAO', f'tipo invalido: use {", ".join(TIPOS)}')
    if migration and not re.fullmatch(r'[\w.\-]{1,80}', migration):
        raise Falha('PREPARACAO', 'identificador de migration invalido')
    trabalho = Path(cfg['trabalho'])
    if _sincronizada(trabalho):
        raise Falha('PREPARACAO', 'a pasta de trabalho (texto claro) nao pode ficar no OneDrive')
    if _sincronizada(cfg['pasta_chaves']) or any(_dentro(cfg['pasta_chaves'], d['pasta']) for d in cfg['destinos']):
        raise Falha('PREPARACAO', 'a pasta de chaves nao pode ficar no OneDrive nem dentro de um destino de backup')
    if len(cfg['destinos']) < 2 or len({str(Path(d['pasta']).resolve()).lower() for d in cfg['destinos']}) != len(cfg['destinos']):
        raise Falha('PREPARACAO', 'sao exigidos dois destinos distintos')
    for d in cfg['destinos']:
        if not Path(d['pasta']).is_dir() or not os.access(d['pasta'], os.W_OK):
            raise Falha('PREPARACAO', f'destino "{d["nome"]}" inexistente ou sem permissao de escrita')
    for nome in ('pg_dump', 'pg_restore'):
        if not (Path(cfg['pg_bin']) / (nome + ('.exe' if os.name == 'nt' else ''))).exists():
            raise Falha('PREPARACAO', f'{nome} nao encontrado na pasta de ferramentas do PostgreSQL configurada')
    if trabalho.exists() and any(p.is_file() and p.suffix != '.cfbak' and not p.name.endswith('.ficha.json') for p in trabalho.rglob('*')):
        raise Falha('PREPARACAO', f'ha restos em texto claro de uma execucao anterior em {trabalho}: rode "limpar-trabalho"')
    dsn = _conexao(cfg)                                    # 2. projeto
    chave, chave_id = chave_vigente(cfg, agora.year)       # 3. chave e guarda externa
    minimo = int(cfg['espaco_minimo_mb']) * (1 << 20)      # 4. espaco
    trabalho.mkdir(parents=True, exist_ok=True)
    for rotulo, pasta in [('pasta de trabalho', trabalho), *((f'destino "{d["nome"]}"', d['pasta']) for d in cfg['destinos'])]:
        if shutil.disk_usage(pasta).free < minimo:
            raise Falha('PREPARACAO', f'espaco insuficiente em {rotulo} (minimo {cfg["espaco_minimo_mb"]} MB)')
    try:                                                   # 5. conexao somente leitura
        conn = B.conectar(dsn)
    except Exception as e:
        raise Falha('PREPARACAO', f'falha de conexao com o banco ({type(e).__name__}): {_limpo(e, dsn)}') from None
    try:
        with conn.cursor() as cur:
            cur.execute('show transaction_read_only')
            if cur.fetchone()[0] != 'on':
                raise Falha('PREPARACAO', 'a sessao com o banco nao esta em modo somente leitura')
        servidor = conn.server_version // 10000
    finally:
        conn.rollback()
        conn.close()
    saida = subprocess.run([str(Path(cfg['pg_bin']) / 'pg_dump'), '--version'], capture_output=True, text=True).stdout
    achado = re.search(r'(\d+)(\.\d+)?\s*$', saida.strip())
    if not achado or int(achado.group(1)) != servidor:
        raise Falha('PREPARACAO', f'pg_dump configurado nao e da versao {servidor} do servidor')
    return dsn, chave, chave_id


def _exportar(cfg, dsn, pasta):
    """Etapas 6 e 7 pela ferramenta homologada. Devolve (caminho do manifesto, manifesto)."""
    anteriores = {k: os.environ.get(k) for k in (VARIAVEL_ORIGEM, 'CF_PG_BIN_BACKUP')}
    os.environ[VARIAVEL_ORIGEM], os.environ['CF_PG_BIN_BACKUP'] = dsn, cfg['pg_bin']
    try:
        try:
            caminho = Path(B.exportar(argparse.Namespace(dsn_env=VARIAVEL_ORIGEM, saida=str(pasta))))
        except SystemExit as e:
            raise Falha('EXPORTACAO', _limpo(e, dsn)) from None
        except Exception as e:
            raise Falha('EXPORTACAO', f'{type(e).__name__}: {_limpo(e, dsn)}') from None
    finally:
        for k, v in anteriores.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return caminho


def _verificar_manifesto(cfg, caminho, dsn):
    try:
        manifesto = B.verificar(argparse.Namespace(manifesto=str(caminho)))
    except SystemExit as e:
        raise Falha('INTEGRIDADE', _limpo(e, dsn)) from None
    texto = caminho.read_text(encoding='utf-8')
    senha = B._sem_senha(dsn)[2]
    if dsn in texto or (senha and senha in texto):
        raise Falha('INTEGRIDADE', 'o manifesto contem dados da conexao: backup recusado')
    if manifesto.get('projeto_ref') != cfg['projeto'] or not manifesto.get('snapshot_unico'):
        raise Falha('INTEGRIDADE', 'manifesto de outro projeto ou sem snapshot unico')
    if B.TABELA_DOCUMENTOS in manifesto['linhas'] and not manifesto['retrato']['md5'].get(B.TABELA_DOCUMENTOS):
        raise Falha('INTEGRIDADE', 'o manifesto nao cobre o conteudo dos documentos fiscais')
    return manifesto


def executar(cfg, tipo='SEMANAL', migration=None, agora=None):
    """Comando unico. Devolve a linha gravada no registro; `estado` == 'CONCLUIDO' so com as duas copias verificadas."""
    agora = agora or dt.datetime.now()
    reg = {'data_hora': agora.isoformat(timespec='seconds'), 'operacao': 'BACKUP', 'tipo': tipo, 'migration': migration,
           'backup_id': None, 'ferramenta': _versao(), 'chave_id': None, 'bytes_cifrado': None, 'sha256_cifrado': None,
           'exportacao': 'NAO_INICIADA', 'verificacao': 'NAO_INICIADA', 'criptografia': 'NAO_INICIADA',
           'destinos': {d['nome']: {'estado': 'NAO_INICIADA'} for d in cfg['destinos']},
           'limpeza': 'NAO_NECESSARIA', 'estado': None, 'erro': None}
    dsn = pasta = None
    manter = ()
    try:
        print('1-5. Preparacao: configuracao, projeto, chave, espaco e conexao somente leitura...')
        dsn, chave, chave_id = _preparar(cfg, tipo, migration, agora)
        reg['chave_id'] = chave_id
        pasta = Path(cfg['trabalho']) / f'execucao-{agora.strftime("%Y%m%d_%H%M%S")}'
        if pasta.exists():
            raise Falha('PREPARACAO', 'ja existe pasta de trabalho desta execucao')
        pasta.mkdir(parents=True)
        _restringir(pasta)
        print('6. Exportacao (somente leitura)...')
        reg['exportacao'] = 'FALHA'
        caminho = _exportar(cfg, dsn, pasta)
        reg['exportacao'] = 'OK'
        print('7. Manifesto...')
        reg['verificacao'] = 'FALHA'
        manifesto = _verificar_manifesto(cfg, caminho, dsn)
        backup_id = reg['backup_id'] = manifesto['backup_id']
        manifesto['rotina'] = {'versao': VERSAO, 'tipo': tipo, 'migration': migration, 'chave_id': chave_id}
        caminho.write_text(json.dumps(manifesto, indent=1, ensure_ascii=False, default=str), encoding='utf-8')
        reg['verificacao'] = 'OK'
        nome_cifrado, nome_ficha = f'{backup_id}.cfbak', f'{backup_id}.ficha.json'
        for d in cfg['destinos']:
            if any((Path(d['pasta']) / n).exists() for n in (nome_cifrado, nome_ficha, nome_cifrado + '.parcial')):
                raise Falha('COPIA', f'ja existe backup {backup_id} no destino "{d["nome"]}": nada foi sobrescrito')
        print('8. Criptografia (AES-256-GCM, chave', chave_id + ')...')
        reg['criptografia'] = 'FALHA'
        try:
            nomes = [caminho.name, *manifesto['arquivos'].keys()]
            pacote = io.BytesIO()
            with tarfile.open(fileobj=pacote, mode='w') as tar:
                for nome in nomes:
                    tar.add(pasta / nome, arcname=nome)
            claro = pacote.getvalue()
            cifrado = pasta / nome_cifrado
            with open(cifrado, 'xb') as f:
                f.write(cifrar_pacote(claro, chave, backup_id, chave_id))
        except Falha:
            raise
        except Exception as e:
            raise Falha('CRIPTOGRAFIA', f'{type(e).__name__}: {_limpo(e, dsn)}') from None
        print('9. Validacao da decifragem...')
        lido = cifrado.read_bytes()
        try:
            volta = decifrar_pacote(cfg, lido, backup_id)  # rele a chave do arquivo
        except Falha as f:
            raise Falha('CRIPTOGRAFIA', f'o arquivo cifrado nao pode ser decifrado: {f}') from None
        if _sha256(volta) != _sha256(claro):
            raise Falha('CRIPTOGRAFIA', 'a decifragem nao devolveu o pacote original')
        del volta
        reg['criptografia'] = 'OK'
        reg['bytes_cifrado'], reg['sha256_cifrado'] = len(lido), _sha256(lido)
        ficha = pasta / nome_ficha
        ficha.write_text(json.dumps({
            'backup_id': backup_id, 'tipo': tipo, 'migration': migration, 'gerado_em': manifesto['gerado_em'],
            'servidor': manifesto['servidor'], 'formato': FORMATO, 'chave_id': chave_id, 'arquivo': nome_cifrado,
            'bytes': len(lido), 'sha256_cifrado': reg['sha256_cifrado'], 'sha256_pacote_claro': _sha256(claro),
            'conteudo': nomes, 'ferramenta': reg['ferramenta']}, indent=1, ensure_ascii=False), encoding='utf-8')
        del claro, lido
        print('10-11. Copia para os destinos e conferencia dos SHA-256...')
        for d in cfg['destinos']:
            reg['destinos'][d['nome']] = _guardar_no_destino(cfg, d, cifrado, ficha, reg['sha256_cifrado'])
            print(f'   destino "{d["nome"]}":', reg['destinos'][d['nome']]['estado'])
        falhos = {n: s for n, s in reg['destinos'].items() if s['estado'] != 'VERIFICADO'}
        if falhos:
            if len(falhos) == len(cfg['destinos']):
                manter = (nome_cifrado, nome_ficha)  # nenhuma copia guardada: a cifrada integra fica na pasta de trabalho
            categoria = 'INTEGRIDADE' if any(s['estado'] == 'FALHA_INTEGRIDADE' for s in falhos.values()) else 'COPIA'
            raise Falha(categoria, '; '.join(f'destino "{n}": {s["erro"]}' for n, s in falhos.items())
                        + f'. A copia cifrada integra foi preservada; depois de resolver, rode "completar --backup-id {backup_id}"')
        reg['estado'] = 'CONCLUIDO'
    except Falha as f:
        reg['estado'], reg['erro'] = f'FALHA_{f.categoria}', _limpo(f, dsn)
    except KeyboardInterrupt:
        reg['estado'], reg['erro'] = 'INTERROMPIDA', 'execucao interrompida pelo usuario'
    except Exception as e:  # nunca vira sucesso
        reg['estado'], reg['erro'] = 'FALHA_INESPERADA', f'{type(e).__name__}: {_limpo(e, dsn)}'
    finally:
        if pasta is not None:
            try:  # 13. texto claro
                _apagar_pasta_clara(pasta, manter=manter)
                reg['limpeza'] = 'OK'
            except Falha as f:
                reg['limpeza'] = f'FALHA: {f}'
                if reg['estado'] == 'CONCLUIDO':
                    reg['estado'] = 'CONCLUIDO_COM_LIMPEZA_PENDENTE'
                reg['erro'] = '; '.join(x for x in (reg['erro'], str(f)) if x)
        _registrar(cfg, reg)  # 12. registro (sempre, tambem na falha)
    if reg['estado'] == 'CONCLUIDO':
        print(f'BACKUP CONCLUIDO: {reg["backup_id"]} ({tipo}{" " + migration if migration else ""}), {reg["bytes_cifrado"]} bytes, '
              f'sha256 {reg["sha256_cifrado"]}, duas copias verificadas, texto claro removido.')
        if tipo == 'PRE_MIGRATION':
            print('Este backup e requisito da manutencao, nao uma garantia automatica de retorno: a volta exige a restauracao assistida.')
    else:
        print(f'{reg["estado"]}: {reg["erro"]}')
        print('NENHUM BACKUP DESTA EXECUCAO DEVE SER CONSIDERADO VALIDO.' if reg['estado'] != 'CONCLUIDO_COM_LIMPEZA_PENDENTE'
              else 'As duas copias estao verificadas, mas a limpeza do texto claro esta pendente (veja o caminho acima).')
    return reg


def completar(cfg, backup_id):
    """Termina a copia de um backup que nao chegou a todos os destinos, a partir de uma copia integra. Nao sobrescreve."""
    fontes = [Path(d['pasta']) for d in cfg['destinos']] + [p.parent for p in Path(cfg['trabalho']).glob(f'*/{backup_id}.ficha.json')]
    fonte = None
    for pasta in fontes:
        arquivo_ficha = pasta / f'{backup_id}.ficha.json'
        if arquivo_ficha.is_file():
            ficha = json.loads(arquivo_ficha.read_text(encoding='utf-8'))
            if (pasta / ficha['arquivo']).is_file() and _sha256(pasta / ficha['arquivo']) == ficha['sha256_cifrado']:
                fonte = pasta
                break
    if fonte is None:
        raise Falha('INTEGRIDADE', f'nenhuma copia integra de {backup_id} foi encontrada')
    reg = {'data_hora': dt.datetime.now().isoformat(timespec='seconds'), 'operacao': 'COMPLETAR', 'tipo': ficha.get('tipo'),
           'backup_id': backup_id, 'ferramenta': _versao(), 'chave_id': ficha.get('chave_id'), 'bytes_cifrado': ficha['bytes'],
           'sha256_cifrado': ficha['sha256_cifrado'], 'destinos': {}, 'estado': None, 'erro': None}
    for d in cfg['destinos']:
        pasta = Path(d['pasta'])
        if pasta == fonte or ((pasta / ficha['arquivo']).is_file() and (pasta / f'{backup_id}.ficha.json').is_file()):
            integro = _sha256(pasta / ficha['arquivo']) == ficha['sha256_cifrado']
            reg['destinos'][d['nome']] = {'estado': 'VERIFICADO' if integro else 'FALHA_INTEGRIDADE',
                                          **({} if integro else {'erro': 'copia existente difere da ficha; nada foi sobrescrito'})}
        elif (pasta / ficha['arquivo']).exists() or (pasta / f'{backup_id}.ficha.json').exists():
            reg['destinos'][d['nome']] = {'estado': 'FALHA_COPIA', 'erro': 'ha arquivo parcial deste backup no destino; nada foi sobrescrito'}
        else:
            reg['destinos'][d['nome']] = _guardar_no_destino(cfg, d, fonte / ficha['arquivo'], fonte / f'{backup_id}.ficha.json',
                                                             ficha['sha256_cifrado'])
        print(f'destino "{d["nome"]}":', reg['destinos'][d['nome']]['estado'])
    falhos = {n: s for n, s in reg['destinos'].items() if s['estado'] != 'VERIFICADO'}
    reg['estado'] = 'CONCLUIDO' if not falhos else 'FALHA_COPIA'
    reg['erro'] = '; '.join(f'destino "{n}": {s.get("erro")}' for n, s in falhos.items()) or None
    if not falhos and fonte not in [Path(d['pasta']) for d in cfg['destinos']]:
        _apagar_pasta_clara(fonte)  # copia cifrada provisoria da pasta de trabalho, ja guardada e conferida nos destinos
    _registrar(cfg, reg)
    print('COPIAS COMPLETAS E VERIFICADAS.' if not falhos else f'FALHA_COPIA: {reg["erro"]}')
    return reg


# ---------------------------------------------------------------- consultas e verificacoes periodicas

def situacao(cfg, agora=None):
    agora = agora or dt.datetime.now()
    backups = sorted((b['ficha'] for b in listar(cfg).values()), key=_data, reverse=True)
    valido = next((f for f in backups if all(_copias_integras(cfg, f).values())), None)
    execucoes = [r for r in ler_registro(cfg) if r.get('operacao') == 'BACKUP']
    ultima = execucoes[-1] if execucoes else None
    r = {'ultimo_valido': valido and valido['backup_id'], 'data_ultimo_valido': valido and valido['gerado_em'],
         'dias_desde_ultimo_valido': valido and (agora - _data(valido)).days,
         'mais_recente': backups[0]['backup_id'] if backups else None,
         'idade_mais_recente_dias': (agora - _data(backups[0])).days if backups else None,
         'ultima_execucao': ultima and ultima['data_hora'], 'estado_ultima_execucao': ultima and ultima['estado'],
         'dias_desde_ultima_execucao': ultima and (agora - dt.datetime.fromisoformat(ultima['data_hora'])).days,
         'total_guardados': len(backups), 'avisos': []}
    if not valido:
        r['avisos'].append('NAO HA BACKUP VALIDO nos dois destinos.')
    elif r['dias_desde_ultimo_valido'] > int(cfg['dias_aviso']):
        r['avisos'].append(f'BACKUP ATRASADO: o ultimo backup valido tem {r["dias_desde_ultimo_valido"]} dias '
                           f'(limite {cfg["dias_aviso"]}). Rode "executar". Nenhum backup foi gerado por esta consulta.')
    if backups and valido and backups[0]['backup_id'] != valido['backup_id']:
        r['avisos'].append(f'O backup mais recente ({backups[0]["backup_id"]}) nao esta integro nos dois destinos.')
    if ultima and ultima['estado'] != 'CONCLUIDO':
        r['avisos'].append(f'A ultima execucao terminou em {ultima["estado"]}.')
    item = _item_chave(cfg, ano=agora.year)
    r['chave_do_ano'] = item and item['chave_id']
    if not item:
        r['avisos'].append(f'Nao ha chave mestra de {agora.year}.')
    elif not item['guardas']:
        r['avisos'].append(f'A chave {item["chave_id"]} nao tem guarda externa confirmada.')
    print(f'Ultimo backup valido: {r["ultimo_valido"] or "nenhum"}'
          + (f' ({r["data_ultimo_valido"]}, ha {r["dias_desde_ultimo_valido"]} dias)' if valido else ''))
    print(f'Backup mais recente: {r["mais_recente"] or "nenhum"}' + (f' (idade {r["idade_mais_recente_dias"]} dias)' if backups else ''))
    print(f'Ultima execucao: {r["ultima_execucao"] or "nenhuma registrada"}'
          + (f' (ha {r["dias_desde_ultima_execucao"]} dias), situacao {r["estado_ultima_execucao"]}' if ultima else ''))
    print(f'Backups guardados: {r["total_guardados"]} | chave de {agora.year}: {r["chave_do_ano"] or "nao ha"}')
    for aviso in r['avisos']:
        print('AVISO:', aviso)
    return r


def _extrair(cfg, ficha, pasta):
    """Decifra a copia GUARDADA de um backup (conferindo os hashes) e extrai numa pasta protegida. Devolve o manifesto."""
    integras = _copias_integras(cfg, ficha)
    fonte = next((Path(d['pasta']) for d in cfg['destinos'] if integras[d['nome']]), None)
    if fonte is None:
        raise Falha('INTEGRIDADE', f'nenhuma copia integra de {ficha["backup_id"]} nos destinos')
    claro = decifrar_pacote(cfg, (fonte / ficha['arquivo']).read_bytes(), ficha['backup_id'])
    if _sha256(claro) != ficha['sha256_pacote_claro']:
        raise Falha('INTEGRIDADE', 'o pacote decifrado difere do registrado na ficha')
    pasta.mkdir(parents=True)
    _restringir(pasta)
    with tarfile.open(fileobj=io.BytesIO(claro)) as tar:
        tar.extractall(pasta, filter='data')
    return next(pasta.glob('manifesto_*.json')), integras


def _pasta_temporaria(cfg, prefixo):
    if _sincronizada(cfg['trabalho']):
        raise Falha('PREPARACAO', 'a pasta de trabalho (texto claro) nao pode ficar no OneDrive')
    return Path(cfg['trabalho']) / f'{prefixo}-{dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")}'


def conferir(cfg, backup_id=None):
    """Verificacao mensal: SHA-256 das copias guardadas, decifragem e manifesto. Nao acessa a producao."""
    ficha = _escolher(cfg, backup_id)
    reg = {'data_hora': dt.datetime.now().isoformat(timespec='seconds'), 'operacao': 'CONFERENCIA', 'backup_id': ficha['backup_id'],
           'ferramenta': _versao(), 'chave_id': ficha.get('chave_id', 'propria do backup (CFBAK1)'), 'destinos': {}, 'estado': None, 'erro': None}
    pasta = _pasta_temporaria(cfg, 'conferencia')
    try:
        caminho, integras = _extrair(cfg, ficha, pasta)
        reg['destinos'] = {n: {'estado': 'VERIFICADO' if ok else 'FALHA_INTEGRIDADE'} for n, ok in integras.items()}
        try:
            B.verificar(argparse.Namespace(manifesto=str(caminho)))
        except SystemExit as e:
            raise Falha('INTEGRIDADE', _limpo(e)) from None
        if not all(integras.values()):
            raise Falha('INTEGRIDADE', 'copia ausente ou alterada em: ' + ', '.join(n for n, ok in integras.items() if not ok))
        reg['estado'] = 'CONCLUIDO'
    except Falha as f:
        reg['estado'], reg['erro'] = f'FALHA_{f.categoria}', _limpo(f)
    finally:
        try:
            _apagar_pasta_clara(pasta)
        except Falha as f:
            reg['estado'], reg['erro'] = 'FALHA_LIMPEZA', '; '.join(x for x in (reg['erro'], str(f)) if x)
        _registrar(cfg, reg)
    print(f'CONFERENCIA de {ficha["backup_id"]}: ' + ('copias integras nos destinos, decifragem e manifesto conferidos.'
                                                      if reg['estado'] == 'CONCLUIDO' else f'{reg["estado"]}: {reg["erro"]}'))
    return reg


def ensaiar(cfg, backup_id=None):
    """Ensaio trimestral: restaura a copia guardada num PostgreSQL DESCARTAVEL em 127.0.0.1 (criado e destruido aqui),
    pela ferramenta homologada, e exige HOMOLOGADO. Nunca recebe uma conexao de fora: nao ha como apontar para o Supabase."""
    sys.path.insert(0, str(RAIZ))
    from tests.supabase_local import ClusterLocal
    import psycopg2
    ficha = _escolher(cfg, backup_id)
    reg = {'data_hora': dt.datetime.now().isoformat(timespec='seconds'), 'operacao': 'ENSAIO', 'backup_id': ficha['backup_id'],
           'ferramenta': _versao(), 'chave_id': ficha.get('chave_id', 'propria do backup (CFBAK1)'), 'estado': None, 'erro': None}
    pasta = _pasta_temporaria(cfg, 'ensaio')
    anteriores = {k: os.environ.get(k) for k in ('CF_BACKUP_ROTINA_ENSAIO', 'CF_PG_BIN_BACKUP')}
    try:
        caminho, _ = _extrair(cfg, ficha, pasta / 'bk')
        os.environ['CF_PG_BIN_BACKUP'] = cfg['pg_bin']
        with ClusterLocal(cfg['pg_bin'], pasta / 'pg') as destino:
            dsn = destino.dsn()
            if psycopg2.extensions.parse_dsn(dsn).get('host') != '127.0.0.1' or B._destino_supabase(dsn):
                raise Falha('PREPARACAO', 'o destino do ensaio nao e um banco local descartavel')
            destino.aplicar_shim()  # papeis da plataforma (anon, authenticated, service_role)
            conn = psycopg2.connect(dsn)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute('drop table auth.users')  # as contas vem do backup, com a estrutura real
                cur.execute("do $$ begin if not exists (select 1 from pg_roles where rolname = 'supabase_admin') "
                            "then create role supabase_admin; end if; end $$")
            conn.close()
            os.environ['CF_BACKUP_ROTINA_ENSAIO'] = dsn
            try:
                resultado = B.restaurar(argparse.Namespace(manifesto=str(caminho), dsn_env='CF_BACKUP_ROTINA_ENSAIO', confirmar_projeto=None))
            except SystemExit as e:
                raise Falha('INTEGRIDADE', _limpo(e, dsn)) from None
            if not resultado.get('homologacao', '').startswith('HOMOLOGADO'):
                raise Falha('INTEGRIDADE', 'a restauracao nao foi homologada')
            conn = psycopg2.connect(dsn)
            with conn.cursor() as cur:  # cada documento restaurado confere com o hash gravado no envio
                cur.execute("select count(*), count(*) filter (where encode(sha256(conteudo), 'hex') = hash_arquivo) "
                            f'from {B.TABELA_DOCUMENTOS}')
                total, iguais = cur.fetchone()
            conn.close()
            reg['documentos'] = {'total': total, 'sha256_iguais': iguais}
            if total != iguais:
                raise Falha('INTEGRIDADE', f'{total - iguais} documentos restaurados com conteudo diferente do hash gravado')
            reg['homologacao'] = resultado['homologacao']
        reg['estado'] = 'CONCLUIDO'
    except Falha as f:
        reg['estado'], reg['erro'] = f'FALHA_{f.categoria}', _limpo(f)
    except Exception as e:
        reg['estado'], reg['erro'] = 'FALHA_INESPERADA', f'{type(e).__name__}: {_limpo(e)}'
    finally:
        for k, v in anteriores.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        try:
            _apagar_pasta_clara(pasta)
        except Falha as f:
            reg['estado'], reg['erro'] = 'FALHA_LIMPEZA', '; '.join(x for x in (reg['erro'], str(f)) if x)
        _registrar(cfg, reg)
    print(f'ENSAIO de {ficha["backup_id"]}: ' + (f'{reg["homologacao"]}; documentos {reg["documentos"]}; banco descartavel removido.'
                                                 if reg['estado'] == 'CONCLUIDO' else f'{reg["estado"]}: {reg["erro"]}'))
    return reg


def decifrar(cfg, arquivo, saida):
    """Recuperacao: extrai o manifesto e os dumps de um .cfbak numa pasta nova e protegida (texto claro, dados reais)."""
    arquivo, saida = Path(arquivo), Path(saida)
    if _sincronizada(saida):
        raise Falha('PREPARACAO', 'a pasta de saida nao pode ficar no OneDrive (texto claro)')
    if saida.exists() and any(saida.iterdir()):
        raise Falha('PREPARACAO', 'a pasta de saida ja tem arquivos: nada foi sobrescrito')
    dados = arquivo.read_bytes()
    claro = decifrar_pacote(cfg, dados, arquivo.name[:-len('.cfbak')] if arquivo.name.endswith('.cfbak') else arquivo.stem)
    saida.mkdir(parents=True, exist_ok=True)
    _restringir(saida)
    with tarfile.open(fileobj=io.BytesIO(claro)) as tar:
        tar.extractall(saida, filter='data')
    print('sha256 do arquivo cifrado:', _sha256(dados), '| sha256 do pacote decifrado:', _sha256(claro), '(compare com a ficha)')
    print('Extraido em', saida, '- a pasta tem dados reais em texto claro: apague ao final.')
    print('Proximo passo: python scripts/backup_banco.py verificar --manifesto <pasta>/manifesto_<data>.json')
    return saida


def limpar_trabalho(cfg):
    """Apaga restos em texto claro de execucoes interrompidas. Copias cifradas pendentes de "completar" ficam."""
    trabalho = Path(cfg['trabalho'])
    if not trabalho.exists():
        print('Pasta de trabalho inexistente: nada a limpar.')
        return 0
    removidos = 0
    for arquivo_ficha in list(trabalho.rglob('*.ficha.json')):  # copia cifrada provisoria ja guardada e integra nos destinos
        try:
            ficha = json.loads(arquivo_ficha.read_text(encoding='utf-8'))
        except ValueError:
            continue
        if all(_copias_integras(cfg, ficha).values()):
            for p in (arquivo_ficha.parent / ficha['arquivo'], arquivo_ficha):
                if p.is_file():
                    _apagar_arquivo(p)
        else:
            print(f'Copia cifrada pendente mantida: {ficha["backup_id"]} (rode "completar --backup-id {ficha["backup_id"]}").')
    for p in sorted(trabalho.rglob('*'), key=lambda x: len(x.parts), reverse=True):
        if p.is_file() and p.suffix != '.cfbak' and not p.name.endswith('.ficha.json'):
            _apagar_arquivo(p)
            removidos += 1
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    print(f'Pasta de trabalho limpa: {removidos} arquivos em texto claro removidos.')
    return removidos


def politica_retencao(backups, agora):
    """Politica INFORMATIVA (FIN-REG-02, item 8). `backups`: [{'backup_id', 'gerado_em' (datetime), 'tipo', 'completo'}].
    Devolve {'manter': {id: motivo}, 'candidatos': {id: motivo}, 'incompletos': [ids]}. Nao toca em arquivos."""
    manter, candidatos = {}, {}
    completos = sorted((b for b in backups if b['completo']), key=lambda b: b['gerado_em'])
    comuns = [b for b in completos if b['tipo'] != 'PRE_MIGRATION']
    for b in comuns[-8:]:
        manter[b['backup_id']] = 'semanal (8 ultimos)'
    vistos = set()
    for b in comuns:  # o primeiro de cada mes, por 12 meses
        mes = (b['gerado_em'].year, b['gerado_em'].month)
        if mes not in vistos:
            vistos.add(mes)
            if (agora.year - mes[0]) * 12 + agora.month - mes[1] < 12:
                manter.setdefault(b['backup_id'], 'mensal (12 meses)')
    for b in comuns:  # o ultimo de dezembro de cada ano, sem prazo
        if b['gerado_em'].month == 12 and b is max((x for x in comuns if x['gerado_em'].year == b['gerado_em'].year
                                                    and x['gerado_em'].month == 12), key=lambda x: x['gerado_em']):
            manter[b['backup_id']] = 'anual (dezembro)'
    for b in comuns:
        if b['backup_id'] not in manter:
            candidatos[b['backup_id']] = 'fora dos 8 semanais, dos mensais de 12 meses e dos anuais'
    for b in completos:
        if b['tipo'] == 'PRE_MIGRATION':
            if any(x['gerado_em'] > b['gerado_em'] for x in completos):
                candidatos[b['backup_id']] = 'pre-migration com copia posterior valida: so depois de homologada a intervencao'
            else:
                manter[b['backup_id']] = 'pre-migration sem copia posterior'
    return {'manter': manter, 'candidatos': candidatos, 'incompletos': sorted(b['backup_id'] for b in backups if not b['completo'])}


def retencao(cfg, agora=None):
    agora = agora or dt.datetime.now()
    backups = [{'backup_id': i, 'gerado_em': _data(b['ficha']), 'tipo': b['ficha'].get('tipo', 'SEMANAL'), 'completo': all(b['destinos'].values())}
               for i, b in listar(cfg).items()]
    r = politica_retencao(backups, agora)
    print(f'Backups guardados: {len(backups)} | dentro da politica: {len(r["manter"])} | alem do periodo recomendado: {len(r["candidatos"])}')
    for i, motivo in sorted(r['candidatos'].items()):
        print(f'  candidato: {i} ({motivo})')
    for i in r['incompletos']:
        print(f'  incompleto (falta num destino; rode "completar --backup-id {i}"): {i}')
    print('NENHUM ARQUIVO FOI EXCLUIDO: esta rotina nao exclui backups. A exclusao e decisao do titular.')
    return r


# ---------------------------------------------------------------- linha de comando

def main(argv=None, cfg=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='comando', required=True)
    e = sub.add_parser('executar')
    e.add_argument('--tipo', default='SEMANAL', choices=TIPOS)
    e.add_argument('--migration', help='identificador da migration ou da manutencao (opcional)')
    sub.add_parser('situacao')
    for nome in ('conferir', 'ensaiar'):
        sub.add_parser(nome).add_argument('--backup-id')
    sub.add_parser('retencao')
    sub.add_parser('completar').add_argument('--backup-id', required=True)
    d = sub.add_parser('decifrar')
    d.add_argument('--arquivo', required=True)
    d.add_argument('--saida', required=True)
    sub.add_parser('limpar-trabalho')
    c = sub.add_parser('chave').add_subparsers(dest='acao', required=True)
    c.add_parser('criar').add_argument('--ano', type=int, required=True)
    g = c.add_parser('confirmar-guarda')
    g.add_argument('--ano', type=int, required=True)
    g.add_argument('--copia')
    g.add_argument('--digitar', action='store_true')
    c.add_parser('situacao')
    args = p.parse_args(argv)
    cfg = cfg or configuracao()
    try:
        if args.comando == 'executar':
            return 0 if executar(cfg, args.tipo, args.migration)['estado'] == 'CONCLUIDO' else 1
        if args.comando == 'situacao':
            situacao(cfg)
            return 0
        if args.comando in ('conferir', 'ensaiar', 'completar'):
            return 0 if {'conferir': conferir, 'ensaiar': ensaiar, 'completar': completar}[args.comando](cfg, args.backup_id)['estado'] == 'CONCLUIDO' else 1
        if args.comando == 'retencao':
            retencao(cfg)
        elif args.comando == 'decifrar':
            decifrar(cfg, args.arquivo, args.saida)
        elif args.comando == 'limpar-trabalho':
            limpar_trabalho(cfg)
        elif args.acao == 'criar':
            chave_criar(cfg, args.ano)
        elif args.acao == 'confirmar-guarda':
            chave_confirmar_guarda(cfg, args.ano, copia=args.copia, digitar=args.digitar)
        else:
            chave_situacao(cfg)
        return 0
    except Falha as f:
        print(f'FALHA_{f.categoria}: {_limpo(f)}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
