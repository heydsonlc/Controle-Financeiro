# OCR local

Este documento descreve a configuracao local das ferramentas de OCR previstas para documentos fiscais, imagens e PDFs escaneados.

## Objetivo

Preparar o ambiente para leitura local de texto em imagens e PDFs escaneados, sem enviar documentos para servicos externos.

## Tesseract

Tesseract e o mecanismo de OCR local. No Windows, o executavel costuma ficar em:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

Para validar manualmente:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

O idioma portugues deve aparecer como:

```text
por
```

Se apenas `eng` estiver disponivel, o OCR ainda pode funcionar, mas tende a errar mais em documentos brasileiros.

## Poppler

Poppler fornece ferramentas para converter paginas de PDFs escaneados em imagens antes do OCR.

As ferramentas esperadas sao:

```text
pdftoppm
pdfinfo
```

No Windows, informe a pasta `bin` onde esses executaveis estiverem.

## Configuracao no sistema

Abra:

```text
Configuracoes > IA e Automacao > OCR local
```

Use:

- `Autodetectar` para procurar instalacoes comuns;
- `Validar ferramentas` para executar `--version` e listar idiomas;
- `Salvar caminhos` para persistir os caminhos locais em `data/ocr/ocr_config.json`.

## Limites atuais

Nesta etapa o sistema apenas valida ferramentas. Ele ainda nao executa OCR em documentos fiscais e nao altera comprovantes.

## Proximos passos

Depois que Tesseract, idioma `por` e Poppler estiverem configurados, o proximo MVP pode integrar OCR ao fluxo de documentos fiscais:

1. tentar texto textual com `pdfplumber`;
2. se nao houver texto suficiente, converter paginas de PDF em imagens;
3. executar OCR local;
4. salvar o texto extraido;
5. aplicar parser e classificacao existentes;
6. manter revisao manual.
