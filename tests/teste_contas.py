"""Teste das contas mais importantes. Como rodar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe tests\\teste_contas.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "painel"))
import agro_calc as A  # noqa: E402
import modelo as M  # noqa: E402

# Série inventada: preço 100 todo mês, novembro sempre 110 e um pico de 200 em março SÓ em 2022.
meses = pd.period_range("2019-01", "2024-12", freq="M")
s = pd.Series([200.0 if (p.year == 2022 and p.month == 3) else 110.0 if p.month == 11 else 100.0 for p in meses],
              index=meses)
tab, cont, todos, _ = A.teste_justo(s, "fluxo", [], 1, 0.0)

# Teste justo: o mês de 2022 é escolhido SEM olhar 2022 -> novembro (110), nunca o pico de março (200).
assert tab.loc[2022, "B"] == 110.0, tab.loc[2022]
# Nos outros anos o pico de 2022 puxa a escolha para março, que nesses anos vale só 100.
assert tab.loc[2020, "B"] == 100.0, tab.loc[2020]

# Veredito: B ganha todos os 6 anos por pouco, sem nenhuma perda -> diferença consistente.
r = M.resumo_teste(pd.Series([5.0, 6, 4, 5, 7, 5], index=range(2019, 2025)))
assert r["veredito"] == "B é melhor — diferença consistente" and r["k"] == 6, r
assert M.resumo_teste(pd.Series([5.0, -4, 6], index=[1, 2, 3]))["veredito"].startswith("Inconclusivo")

print("ok: teste justo não olha o próprio ano; veredito correto")
