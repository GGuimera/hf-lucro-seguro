# Resumo para a nova sessão — foco: previsibilidade de preços

Leia este arquivo e `C:\harness\CLAUDE.md` antes de começar. O histórico completo de mudanças está em `C:\harness\registro.md`.

## O projeto em 1 minuto
- **"Preço Seguro"**: um painel em Streamlit. O código fica em `painel/`, com entrada por `painel/inicio.py`. Os coletores ficam em `coleta/`. O banco SQLite é `dados/precos.db` (157 MB, só no computador).
- **Site:** https://hf-lucro-seguro.streamlit.app, público. Ele lê os arquivos `online/*.parquet`. O repositório no GitHub é privado: GGuimera/hf-lucro-seguro, branch main, versão 80c72a3 em 09/11/2026. Para publicar, use `publicar.bat` ou faça o envio só com o OK do usuário.
- **Modo site:** quando `M.ONLINE` é verdadeiro, ficam escondidas as páginas de previsão (plantar, analise, clima_preco, confiabilidade) e a metodologia. No computador, aparece tudo.
- **Teste:** `.venv\Scripts\python.exe tests\teste_contas.py`. As 9 páginas são testadas com AppTest, nos modos PC e site (`PRECO_SEGURO_ONLINE=1`).

## O modelo de previsão (painel/modelo.py, "Modelo Preditivo Sazonal v2")
1. **Série mensal por produto:**
   - alho, cenoura e cebola: a planilha do produtor de BH (2017+), que é igual à CeasaMinas, emendada com a Conab;
   - as outras culturas: índice combinado das Ceasas com 3 anos ou mais de dados.
2. **Época:** preço ÷ média móvel de 12 meses; a mediana entre anos dá o índice sazonal.
3. **Cenários:** o preço ÷ tendência log, ano a ano.
4. **Preço normal:** os últimos 24 meses sem a época, mais a inflação.
5. **Lucro/ha:** preço × (1 − desconto de 15%) × produção vendável − custo (`dados/custos.csv`).
6. **"Teste justo":** os meses da estratégia B são escolhidos só com os outros anos (deixa um ano de fora). O veredito vem de `M.resumo_teste` (bootstrap 90% + teste do sinal).
7. **Clima × preço** (`clima_preco_calc.py`): Spearman, permutação circular e Benjamini-Hochberg.
   - HF: 96 testes, 0 aprovados;
   - agro: 99 testes, 0 aprovados;
   - sinais fracos: alho e cenoura com chuva; boi com chuva e calor.

## Fontes que JÁ estão no sistema
| Fonte | O que traz | Coletor |
|---|---|---|
| Conab/Prohort diário | Ceasas do Brasil, 06/2022–01/2026 (arquivo do Internet Archive; o link oficial está quebrado) | preparar_dados.py |
| Planilha do produtor (BH) | alho e cenoura 2017–2025; cebola 2017–2021 | importar_planilha.py |
| CeasaMinas (site oficial) | preço médio mensal R$/kg em BH, 29 produtos, 2022–hoje | ceasaminas.py |
| Ceagesp | boletins 3 vezes por semana, 2022–hoje | ceagesp.py |
| Conab Boletim Hortigranjeiro | preço médio mensal em 10 Ceasas (só o formato de jul/2026+) | boletim_conab.py |
| Conab PrecosMensalUF / ProhortMensal | preço ao produtor e oferta (kg) por origem | importar_conab_arquivo.py |
| Clima Open-Meteo | ERA5 desde 2000 + previsão de 16 dias (3 modelos) em 31 polos | clima.py |
| IBGE PAM | participação dos polos na produção | polos.py |
| Relevo (Copernicus DEM) | declividade e altitude dos polos | relevo.py |
| Notícias (Google News RSS) | eventos de preço e clima | buscar_noticias.py |
| Cepea (agrobr), Banco Mundial, ANP, BCB, Conab custos | commodities, fertilizantes, diesel, dólar, IPCA | commodities.py |
| OpenAlex + Embrapa Alice | artigos científicos desde 2010 | artigos.py |
| **Fatores (novo, 15/11/2026):** NOAA ONI, IBGE IPCA por produto (7060), BCB 1635, IBGE LSPA (6588), Comex Stat | El Niño desde 1950; IPCA de cenoura, cebola, alho, tomate, batata desde 2020; estimativa de safra desde 2006; importação de alho e cebola desde 2010 → tabela `fatores_mensal` (só no computador) | fatores_mercado.py |

## Prova dos fatores (painel/fatores_calc.py, página fatores.py) — 15/11/2026
- 78 combinações escritas antes de olhar os números; 5 com p < 0,05; **0 aprovadas** (q < 0,10).
- Sinais fracos: dólar → alho (3 defasagens); safra estimada → tomate e trigo; El Niño → cebola 6 meses depois.
- O IPCA por produto foi coletado, mas ainda não entrou em nenhuma prova.
- **LSPA:** alho, cebola e "café total" param em 2017; não tem cenoura. Cada valor é a estimativa da safra do ano inteiro.

## Fontes testadas em 15/11/2026 e ainda NÃO ligadas
- **IPH CeasaMinas-UFV** (dee.ufv.br, PDF mensal em texto, 58 produtos em R$/kg, desde dez/2024) e **Ceasa-RJ semanal** (rj.gov.br/ceasa, PDF em texto, 10 produtos): legíveis, falta o coletor.
- **Descartadas ou travadas:** dw.ceasa.gov.br (o usuário abriu e não achou nada útil); Hortifruti Brasil (erro 403 para programa); frete (sem série oficial gratuita); CeasaMinas oferta por município (pede senha); boletins Conab jan–mai/2026 (mais de 10 MB, não lidos).

## Lacunas conhecidas (por onde começar)
- **Conab diário a partir de 2026:** existe só pela consulta "zona cinza" da agrobr (`preco_atacado`, com senha embutida, só o dia atual). O usuário preferiu fontes oficiais.
- **Boletins Conab de jan–mai/2026 e mais antigos:** outro formato, às vezes tabela em imagem. Não foram lidos.
- **Modelo:** ainda não usa a CeasaMinas, a Ceagesp de 2026 nem o boletim. A apresentação de 4 meses (+R$ 50,5 mil/ha, cenoura) depende dos números atuais.
- **Sem dados de oferta e volume recentes:** quantidade que entra nas Ceasas em 2026, área plantada e intenção de plantio.
- **Sem fatores de mercado:** índices de clima global (El Niño / La Niña), câmbio e diesel ligados ao HF, IPCA de alimentos, importação de alho e cebola (Comex).
- **Fontes candidatas citadas, mas não testadas:**
  - Ceasa-RJ (relatórios semanais em PDF);
  - IPH CeasaMinas-UFV (índice mensal);
  - Hortifruti Brasil/Cepea (preços de HF ao produtor);
  - Comex Stat (importação de alho e cebola);
  - NOAA ONI (El Niño / La Niña);
  - IBGE LSPA;
  - Conab ProhortMensal (oferta), mais recente.

## Pedido do usuário para a nova sessão (15/11/2026)
- **"Precisamos de mais fontes de dados"**, com foco em previsibilidade de preços.
- **Tipos escolhidos:**
  - **oferta e volume:** chegada às Ceasas por origem, área plantada, intenção de plantio;
  - **mais preços recentes:** Ceasa-RJ semanal, boletins antigos da Conab, IPH CeasaMinas-UFV, Hortifruti Brasil/Cepea;
  - **fatores de mercado:** El Niño / La Niña, dólar, diesel, frete, importação Comex, IPCA de alimentos.
- **Culturas:** HF **e** commodities.
- **Informação nova do usuário:** a diferença entre o preço da Ceasa e o que o produtor recebe passa de 20% e às vezes chega a 25%. Hoje `DESCONTO_PADRAO = 15` em `painel/modelo.py`. **Confirmar com o usuário antes de trocar**: muda todos os lucros e a apresentação.

## Regras de trabalho (resumo do CLAUDE.md)
- Português simples, explicar antes de cada ação.
- Nada de apagar, mover ou sobrescrever sem lista + OK.
- Segredos só no `.env`.
- Só a pasta `C:\harness`.
- Testar de verdade e mostrar a prova.
- Separar verificado de suposição.
- Anotar no `registro.md`.
- Para pedido vago, perguntar antes.
