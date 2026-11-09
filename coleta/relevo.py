"""Relevo de cada polo produtor (dados\\polos.csv) a partir do mapa de altitude Copernicus DEM GLO-90 (90 m),
pelo Open-Meteo (grátis, sem chave). Duas escalas em volta do ponto de referência:
  - regional: quadrado de ~22 km, pontos a cada ~2,2 km;
  - local:    quadrado de ~5,5 km, pontos a cada ~560 m.
Cada ponto conta como 1 pedido no Open-Meteo (limite grátis: 600 por minuto, 10 mil por dia), por isso
são 11 x 11 pontos por escala e o programa vai devagar.
Grava dados\\relevo_polos.csv (resumo) e dados\\relevo_grade.csv (os pontos, para o mapa).

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\relevo.py
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
POLOS = PASTA / "dados" / "polos.csv"
RESUMO = PASTA / "dados" / "relevo_polos.csv"
GRADE = PASTA / "dados" / "relevo_grade.csv"
ESCALAS = {"regional": 0.02, "local": 0.005}  # graus entre pontos (11 x 11 pontos)
N = 11
GRADIENTE = 0.65  # °C a menos a cada 100 m de subida (atmosfera padrão)
# classes de relevo da Embrapa (Sistema Brasileiro de Classificação de Solos), declividade em %
CLASSES = [("plano", 0, 3), ("suave ondulado", 3, 8), ("ondulado", 8, 20), ("forte ondulado", 20, 45),
           ("montanhoso", 45, 75), ("escarpado", 75, 1e9)]


def altitudes(lats, lons):
    out = []
    for i in range(0, len(lats), 100):
        u = "https://api.open-meteo.com/v1/elevation?" + urllib.parse.urlencode(
            {"latitude": ",".join(f"{v:.5f}" for v in lats[i:i + 100]),
             "longitude": ",".join(f"{v:.5f}" for v in lons[i:i + 100])})
        for tentativa in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "PrecoSeguro-relevo/0.1"}),
                                            timeout=60) as r:
                    out += json.load(r)["elevation"]
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or tentativa == 3:
                    raise
                print("  limite por minuto do Open-Meteo: esperando 65 s")
                time.sleep(65)
        time.sleep(12)  # ~500 pontos por minuto, abaixo do limite de 600
    return np.array(out, dtype=float)


def main():
    polos = pd.read_csv(POLOS, sep=";")
    resumo, grades = [], []
    for p in polos.itertuples():
        for escala, passo in ESCALAS.items():
            offs = (np.arange(N) - N // 2) * passo
            LA, LO = np.meshgrid(p.lat + offs, p.lon + offs, indexing="ij")
            z = altitudes(LA.ravel(), LO.ravel()).reshape(N, N)
            dy = passo * 111_320
            dx = passo * 111_320 * np.cos(np.radians(p.lat))
            gy, gx = np.gradient(z, dy, dx)
            decl = np.hypot(gx, gy) * 100  # %
            linha = {"polo": p.polo, "escala": escala, "lado_km": round((N - 1) * passo * 111.3, 1),
                     "alt_ref": float(z[N // 2, N // 2]), "alt_min": float(z.min()), "alt_p10": float(np.percentile(z, 10)),
                     "alt_mediana": float(np.median(z)), "alt_p90": float(np.percentile(z, 90)), "alt_max": float(z.max()),
                     "decl_media": float(decl.mean()), "decl_p90": float(np.percentile(decl, 90)),
                     "dif_temp_p10_p90": round((np.percentile(z, 90) - np.percentile(z, 10)) / 100 * GRADIENTE, 1)}
            for nome, a, b in CLASSES:
                linha[f"pct_{nome}"] = float(((decl >= a) & (decl < b)).mean())
            resumo.append(linha)
            grades.append(pd.DataFrame({"polo": p.polo, "escala": escala, "lat": LA.ravel().round(5),
                                        "lon": LO.ravel().round(5), "alt": z.ravel()}))
        r = resumo[-2]
        print(f"{p.polo:12} regional: {r['alt_min']:.0f}-{r['alt_max']:.0f} m, declividade média {r['decl_media']:.1f}%, "
              f"plano+suave {r['pct_plano'] + r['pct_suave ondulado']:.0%}")
    pd.DataFrame(resumo).round(4).to_csv(RESUMO, sep=";", index=False, encoding="utf-8")
    pd.concat(grades).to_csv(GRADE, sep=";", index=False, encoding="utf-8")
    print(f"Gravados {RESUMO.name} e {GRADE.name}")


if __name__ == "__main__":
    main()
