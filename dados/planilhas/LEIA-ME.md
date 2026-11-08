# Como mandar uma planilha de preços para o sistema

Quanto **mais anos** de preço uma cultura tiver, **mais confiável** fica a análise (🔴 → 🟡 → 🟢).

## Formato (o mesmo do arquivo `MODELO_preencher.csv`)

| produto | mes | preco | ceasa |
|---|---|---|---|
| TOMATE | 2017-01 | 2,35 | CEASAMINAS - BELO HORIZONTE |

- **produto:** o nome como aparece no painel, em MAIÚSCULAS (ex.: TOMATE, BATATA, BETERRABA, REPOLHO).
- **mes:** ano e mês, assim: `2017-01` (janeiro de 2017).
- **preco:** preço médio do mês, em R$ por kg (pode usar vírgula: `2,35`).
- **ceasa:** de onde é o preço (ex.: `CEASAMINAS - BELO HORIZONTE`, `CEASA/RJ - RIO DE JANEIRO`, `CEAGESP - SAO PAULO`).
  Se deixar em branco, o sistema entende que é de BH.

## Passo a passo

1. Copie o `MODELO_preencher.csv`, dê o nome da cultura (ex.: `tomate.csv`) e preencha. Pode ser também em Excel (`.xlsx`) com as mesmas 4 colunas.
2. Salve nesta pasta (`dados\planilhas\`). O arquivo `MODELO_preencher.csv` é ignorado.
3. Rode: `.venv\Scripts\python.exe coleta\importar_planilha.py`
4. Religue o painel. A cultura passa a usar a sua planilha como base, se ela tiver mais anos que a Conab.
