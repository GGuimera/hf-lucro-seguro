"""Clima dos polos produtores (dados\\polos.csv), grátis pelo Open-Meteo (sem chave):

1. HISTÓRICO diário desde 2000 (reanálise ERA5: temperatura máx/mín, chuva, evapotranspiração)
   -> tabela clima_diario. Nas próximas vezes baixa só os dias que faltam.
2. PREVISÃO de 16 dias de 3 modelos (europeu ECMWF, americano GFS, alemão ICON), guardada como uma
   "foto" por dia -> tabela previsao_log. Serve para medir depois qual modelo acerta mais em cada polo.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\clima.py
Uso dos dados: Open-Meteo é grátis para uso não comercial (atribuição: Open-Meteo.com, dados ERA5/Copernicus).
"""
import json
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
BANCO = PASTA / "dados" / "precos.db"
POLOS = PASTA / "dados" / "polos.csv"
LOG = PASTA / "dados" / "log_clima.txt"
INICIO = date(2000, 1, 1)
VARS = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "et0_fao_evapotranspiration"]
NOMES = {"temperature_2m_max": "tmax", "temperature_2m_min": "tmin", "precipitation_sum": "chuva",
         "et0_fao_evapotranspiration": "et0"}
MODELOS = {"ecmwf_ifs025": "Europeu (ECMWF)", "gfs_seamless": "Americano (GFS)", "icon_seamless": "Alemão (ICON)"}


def registrar(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M} {msg}"
    print(linha)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def pedir(url, params, tentativas=3):
    u = url + "?" + urllib.parse.urlencode(params)
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "PrecoSeguro-clima/0.1"}),
                                        timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            corpo = e.read().decode("utf-8", "replace")[:300]
            if e.code == 429 and i < tentativas - 1:  # limite de pedidos: espera e tenta de novo
                registrar(f"limite do Open-Meteo, esperando 70 s ({corpo})")
                time.sleep(70)
                continue
            raise RuntimeError(f"HTTP {e.code}: {corpo}") from e


def historico(con, p):
    ult = con.execute("SELECT MAX(data) FROM clima_diario WHERE polo = ?", (p["polo"],)).fetchone()[0]
    ini = (date.fromisoformat(ult) + timedelta(days=1)) if ult else INICIO
    fim = date.today() - timedelta(days=6)  # a reanálise chega com uns 5 dias de atraso
    if ini > fim:
        return 0
    d = pedir("https://archive-api.open-meteo.com/v1/archive",
              {"latitude": p["lat"], "longitude": p["lon"], "start_date": ini.isoformat(), "end_date": fim.isoformat(),
               "daily": ",".join(VARS), "timezone": "America/Sao_Paulo"})
    df = pd.DataFrame(d["daily"]).rename(columns={"time": "data", **NOMES})
    df = df.dropna(subset=["tmax", "tmin", "chuva"], how="all")
    df.insert(0, "polo", p["polo"])
    df.to_sql("clima_diario", con, if_exists="append", index=False)
    return len(df)


def previsao(p):
    v = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"]
    d = pedir("https://api.open-meteo.com/v1/forecast",
              {"latitude": p["lat"], "longitude": p["lon"], "daily": ",".join(v), "models": ",".join(MODELOS),
               "forecast_days": 16, "timezone": "America/Sao_Paulo"})
    dia = d["daily"]
    partes = []
    for m in MODELOS:
        partes.append(pd.DataFrame({"polo": p["polo"], "modelo": m, "data": dia["time"],
                                    "tmax": dia.get(f"temperature_2m_max_{m}"), "tmin": dia.get(f"temperature_2m_min_{m}"),
                                    "chuva": dia.get(f"precipitation_sum_{m}")}))
    return pd.concat(partes, ignore_index=True)


def main():
    polos = pd.read_csv(POLOS, sep=";")
    con = sqlite3.connect(BANCO)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS clima_diario (polo TEXT, data TEXT, tmax REAL, tmin REAL, chuva REAL, et0 REAL)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clima ON clima_diario (polo, data)")
        con.execute("CREATE TABLE IF NOT EXISTS previsao_log (coletado_em TEXT, polo TEXT, modelo TEXT, data TEXT, "
                    "tmax REAL, tmin REAL, chuva REAL)")
        hoje = date.today().isoformat()
        n_hist, n_prev, erros = 0, 0, 0
        for _, p in polos.iterrows():
            try:
                n = historico(con, p)
                con.commit()
                n_hist += n
                if n > 1000:
                    time.sleep(20)  # pedido grande: dá um respiro ao servidor
            except Exception as e:
                erros += 1
                registrar(f"ERRO histórico {p['polo']}: {e}")
            try:
                if not con.execute("SELECT 1 FROM previsao_log WHERE polo = ? AND coletado_em = ?", (p["polo"], hoje)).fetchone():
                    pv = previsao(p).assign(coletado_em=hoje)
                    pv.to_sql("previsao_log", con, if_exists="append", index=False)
                    con.commit()
                    n_prev += len(pv)
            except Exception as e:
                erros += 1
                registrar(f"ERRO previsão {p['polo']}: {e}")
            time.sleep(1)
        registrar(f"clima: {n_hist} dias de histórico novos, {n_prev} linhas de previsão, {erros} erros")
    finally:
        con.close()


if __name__ == "__main__":
    main()
