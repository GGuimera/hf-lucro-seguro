# Preço Seguro — Modelo Preditivo Sazonal

Sistema para ajudar o produtor rural a decidir **o que e quando plantar**, a partir do histórico de preços das
Ceasas de MG, RJ e SP (e da média do Brasil), dos custos de produção e das perdas.

## Como abrir o painel

```
.venv\Scripts\streamlit.exe run painel\inicio.py
```
Depois abra **http://localhost:8501** no Chrome.

## Páginas

| Página | Para que serve |
|---|---|
| 📊 Preços | Histórico, comparação entre anos e entre Ceasas, boletins da Ceagesp |
| 🌱 O que plantar agora | Ranking das culturas para a data de plantio, com confiança e lucro esperado |
| 🔬 Análise por cultura | Os 12 meses de plantio, risco, passo a passo e "ano todo × melhores meses" |
| ✅ Dá para confiar? | Prova de acerto no passado, diferença Ceasa → produtor medida, fontes e conferências |

## Pastas

| Pasta | Conteúdo |
|---|---|
| `painel/` | As páginas e o modelo (`modelo.py`) |
| `coleta/` | Programas que baixam, importam e conferem os dados |
| `dados/` | Banco de preços e tabelas de culturas, custos e perdas (`.csv` editáveis) |
| `dados/planilhas/` | Onde colocar planilhas de preço de outras culturas (ver `LEIA-ME.md`) |
| `docs/` | Textos de apoio (ex.: pedido de dados à Conab) |

## Atualizar os dados

```
.venv\Scripts\python.exe coleta\ceagesp.py AAAA-MM-DD AAAA-MM-DD   # boletins da Ceagesp
.venv\Scripts\python.exe coleta\importar_planilha.py                # planilhas do produtor
.venv\Scripts\python.exe coleta\importar_conab_arquivo.py           # arquivos oficiais da Conab
.venv\Scripts\python.exe coleta\validar_dados.py                    # conferência geral
```

O registro de todas as mudanças (com como desfazer) está em `C:\harness\registro.md`.
