"""Coleta os preços das COMMODITIES do agro (lista em dados\\commodities.csv) e grava no banco:

- Cepea/Esalq (via biblioteca agrobr): soja, milho, trigo, arroz, café, açúcar, etanol, boi, bezerro,
  frango, suíno e leite — preço diário desde 2010 -> tabela agro_diario.
- Banco Mundial ("Pink Sheet", mensal, em dólar): petróleo, gás natural, ureia, potássio, DAP, TSP,
  rocha fosfática, óleos e preços mundiais de referência.
- ANP (via agrobr): diesel S10 na bomba, média do Brasil.
- Banco Central: dólar (média do mês) e IPCA, para converter para reais e descontar a inflação.
- Conab (via agrobr): custo de produção e produtividade das culturas de grãos e café -> dados\\custos_agro.csv
  (só é baixado de novo depois de 30 dias).

Tudo vira média mensal na tabela agro_mensal (produto, mes, valor, unidade, fonte).

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\commodities.py
Uso dos dados: Cepea sob CC BY-NC 4.0 (citar a fonte; uso comercial precisa de autorização da Cepea);
Banco Mundial CC BY 4.0; ANP, Banco Central e Conab são dados públicos.
"""
import io
import json
import re
import sqlite3
import time
import urllib.request
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")  # avisos de licença e de layout da agrobr vão para o log, não para a tela

PASTA = Path(__file__).resolve().parent.parent
BANCO = PASTA / "dados" / "precos.db"
LISTA = PASTA / "dados" / "commodities.csv"
CUSTOS = PASTA / "dados" / "custos_agro.csv"
LOG = PASTA / "dados" / "log_commodities.txt"
INICIO = "2010-01-01"
UA = {"User-Agent": "PrecoSeguro-commodities/0.1"}
PAGINA_BM = "https://www.worldbank.org/en/research/commodity-markets"
URLS_BM = [  # se a página mudar, tenta os endereços conhecidos (o mais novo primeiro)
    "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx",
    "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/related/CMO-Historical-Data-Monthly.xlsx",
]


def registrar(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M} {msg}"
    print(linha)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def baixar(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


# ---------- Cepea (diário) ----------
def cepea(con, item):
    from agrobr.sync import cepea as cp
    ult = con.execute("SELECT MAX(data) FROM agro_diario WHERE produto = ?", (item["produto"],)).fetchone()[0]
    ini = (date.fromisoformat(ult) - timedelta(days=20)).isoformat() if ult else INICIO
    df = cp.indicador(item["codigo"], inicio=ini)
    if df.empty:
        return 0
    if item["praca"]:
        df = df[df["praca"] == item["praca"]]
    d = (df.assign(data=pd.to_datetime(df["data"]).dt.strftime("%Y-%m-%d"))
           .groupby("data", as_index=False)["valor"].mean())  # várias praças (ex.: suíno) -> média
    d.insert(0, "produto", item["produto"])
    d["unidade"] = item["unidade"]
    d["fonte"] = "Cepea/Esalq (via agrobr)" + (f" — {item['praca']}" if item["praca"] else "")
    con.execute("DELETE FROM agro_diario WHERE produto = ? AND data >= ?", (item["produto"], d["data"].min()))
    d.to_sql("agro_diario", con, if_exists="append", index=False)
    return len(d)


# ---------- Banco Mundial (mensal, US$) ----------
def endereco_bm():
    try:
        html = baixar(PAGINA_BM, 60).decode("utf-8", "replace")
        achou = re.findall(r'https?://[^"\']+CMO-Historical-Data-Monthly\.xlsx', html)
        if achou:
            return [achou[0]] + URLS_BM
    except Exception as e:
        registrar(f"página do Banco Mundial não abriu ({e}); usando endereços conhecidos")
    return URLS_BM


def banco_mundial():
    ultimo_erro = None
    for u in endereco_bm():
        try:
            bruto = baixar(u, 180)
            break
        except Exception as e:
            ultimo_erro = e
    else:
        raise RuntimeError(f"não consegui baixar a planilha do Banco Mundial: {ultimo_erro}")
    t = pd.read_excel(io.BytesIO(bruto), sheet_name="Monthly Prices", header=None, engine="openpyxl")
    nomes = [str(x).strip() if pd.notna(x) else "" for x in t.iloc[4]]
    unid = [str(x).strip() if pd.notna(x) else "" for x in t.iloc[5]]
    dados = t.iloc[6:].copy()
    dados = dados[dados[0].astype(str).str.match(r"^\d{4}M\d{2}$")]
    meses = dados[0].str.replace("M", "-")
    saida = {}
    for j, nome in enumerate(nomes):
        if not nome:
            continue
        chave = nome.replace("*", "").strip()
        v = pd.to_numeric(dados[j], errors="coerce")
        saida[chave] = (pd.Series(v.values, index=meses.values).dropna(), unid[j])
    return saida


# ---------- Banco Central ----------
def sgs(serie):
    d = json.loads(baixar(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados?formato=json&dataInicial=01/01/2009"))
    s = pd.Series({datetime.strptime(x["data"], "%d/%m/%Y").strftime("%Y-%m"): float(x["valor"]) for x in d})
    return s.sort_index()


# ---------- Conab: custo de produção ----------
def custos_conab(lista):
    import asyncio

    import agrobr.conab._custo_producao.api as api
    from agrobr.sync import datasets
    linhas = []
    for _, it in lista[lista["custo_cultura"] != ""].iterrows():
        try:
            pls = asyncio.run(api.catalogo_custos(it["custo_cultura"]))
            if "planilha" not in pls.columns or pls.empty:
                raise RuntimeError("catálogo vazio")
            if it["custo_planilha"]:
                pls = pls[pls["planilha"].str.contains(it["custo_planilha"], case=False)]
            planilha = sorted(pls["planilha"].unique())[-1]
            cat = asyncio.run(api.catalogo_custos(it["custo_cultura"], planilha=planilha))
            cat = cat[cat["status"] != "unresolved"].dropna(subset=["local", "ano_referencia"])
            escolha = None
            for local in it["custo_locais"].split("|"):
                c = cat[cat["local"].str.contains(local, case=False, na=False)]
                if not c.empty:
                    escolha = c.sort_values(["ano_referencia", "aba"]).iloc[-1]
                    break
            if escolha is None:
                escolha = cat.sort_values("ano_referencia").iloc[-1]
            df = datasets.custo_producao(it["custo_cultura"], planilha=planilha, aba=escolha["aba"])
            tot = df[df["tipo_linha"] == "total"].set_index("item")
            ct = tot[tot.index.str.contains("CUSTO TOTAL")].iloc[0]
            co = tot[tot.index.str.contains("CUSTO OPERACIONAL")].iloc[0]
            prod = float(ct["valor_ha"]) / float(ct["valor_unidade_produto"])
            linhas.append({"produto": it["produto"], "custo_total_ha": round(float(ct["valor_ha"]), 2),
                           "custo_operacional_ha": round(float(co["valor_ha"]), 2),
                           "produtividade": round(prod, 1), "unidade_prod": str(ct["unidade_produto"]).replace("CUSTO /", "").strip(),
                           "local": f"{escolha['local']}-{escolha['uf']}", "safra": escolha.get("safra", ""),
                           "referencia": escolha.get("referencia", ""), "sistema": escolha.get("sistema", ""),
                           "fonte": f"Conab — Custos de produção ({planilha}, aba {escolha['aba']})"})
            registrar(f"custo {it['produto']}: R$ {ct['valor_ha']:,.0f}/ha em {escolha['local']} ({escolha.get('safra', '')}), "
                      f"{prod:.0f} por ha")
        except Exception as e:
            registrar(f"ERRO custo {it['produto']}: {type(e).__name__}: {str(e)[:200]}")
    return pd.DataFrame(linhas)


def main():
    lista = pd.read_csv(LISTA, sep=";", dtype=str).fillna("")
    con = sqlite3.connect(BANCO)
    erros = 0
    try:
        con.execute("CREATE TABLE IF NOT EXISTS agro_diario (produto TEXT, data TEXT, valor REAL, unidade TEXT, fonte TEXT)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_agro_d ON agro_diario (produto, data)")
        con.execute("CREATE TABLE IF NOT EXISTS agro_mensal (produto TEXT, mes TEXT, valor REAL, unidade TEXT, fonte TEXT)")
        mensal = []

        # 1) Cepea
        for _, it in lista[lista["origem"] == "cepea"].iterrows():
            try:
                n = cepea(con, it)
                con.commit()
                registrar(f"cepea {it['produto']}: {n} dias atualizados")
            except Exception as e:
                erros += 1
                registrar(f"ERRO cepea {it['produto']}: {type(e).__name__}: {str(e)[:200]}")
        d = pd.read_sql("SELECT * FROM agro_diario", con)
        if not d.empty:
            d["mes"] = d["data"].str[:7]
            mensal.append(d.groupby(["produto", "mes", "unidade", "fonte"], as_index=False)["valor"].mean())

        # 2) Dólar e IPCA (Banco Central)
        dolar = sgs(3698)  # dólar comercial venda, média do mês
        ipca = sgs(433)    # IPCA, % ao mês
        ind = (1 + ipca / 100).cumprod()
        mensal.append(pd.DataFrame({"produto": "DOLAR", "mes": dolar.index, "valor": dolar.values,
                                    "unidade": "R$/US$", "fonte": "Banco Central (SGS 3698)"}))
        mensal.append(pd.DataFrame({"produto": "IPCA_INDICE", "mes": ind.index, "valor": ind.values,
                                    "unidade": "índice", "fonte": "Banco Central (SGS 433), acumulado"}))
        registrar(f"dólar até {dolar.index[-1]} (R$ {dolar.iloc[-1]:.2f}); IPCA até {ipca.index[-1]}")

        # 3) Banco Mundial
        try:
            bm = banco_mundial()
            for _, it in lista[lista["origem"] == "wb"].iterrows():
                if it["codigo"] not in bm:
                    erros += 1
                    registrar(f"ERRO Banco Mundial: coluna '{it['codigo']}' não encontrada")
                    continue
                s, un = bm[it["codigo"]]
                s = s[s.index >= INICIO[:7]]
                fx = dolar.reindex(s.index)
                ok = fx.notna()
                fator = 1000 if "/mt" in un and "tonelada" not in it["unidade"] else 1
                mensal.append(pd.DataFrame({"produto": it["produto"], "mes": s.index[ok], "valor": (s[ok] * fx[ok] / fator).values,
                                            "unidade": it["unidade"],
                                            "fonte": f"Banco Mundial Pink Sheet ({it['codigo']}, {un}) × dólar do Banco Central"}))
                mensal.append(pd.DataFrame({"produto": it["produto"] + "_USD", "mes": s.index, "valor": s.values,
                                            "unidade": un.strip("()"), "fonte": f"Banco Mundial Pink Sheet ({it['codigo']})"}))
            registrar(f"Banco Mundial: até {max(s.index.max() for s, _ in bm.values() if len(s))}")
        except Exception as e:
            erros += 1
            registrar(f"ERRO Banco Mundial: {type(e).__name__}: {str(e)[:200]}")

        # 4) Diesel (ANP)
        try:
            from agrobr.sync import datasets
            for _, it in lista[lista["origem"] == "anp"].iterrows():
                dz = datasets.precos_diesel(it["codigo"], inicio=INICIO, nivel="brasil", agregacao="mensal")
                dz["mes"] = pd.to_datetime(dz["data"]).dt.strftime("%Y-%m")
                g = dz.groupby("mes", as_index=False)["preco_venda"].mean().rename(columns={"preco_venda": "valor"})
                mensal.append(g.assign(produto=it["produto"], unidade=it["unidade"], fonte="ANP — levantamento de preços (via agrobr)"))
                registrar(f"diesel {it['codigo']}: {g['mes'].min()} a {g['mes'].max()}")
        except Exception as e:
            erros += 1
            registrar(f"ERRO diesel: {type(e).__name__}: {str(e)[:200]}")

        tudo = pd.concat(mensal, ignore_index=True)[["produto", "mes", "valor", "unidade", "fonte"]]
        con.execute("DELETE FROM agro_mensal")
        tudo.to_sql("agro_mensal", con, if_exists="append", index=False)
        con.commit()
        registrar(f"agro_mensal: {len(tudo):,} linhas, {tudo['produto'].nunique()} séries")
    finally:
        con.close()

    # 5) Custos da Conab (a cada 30 dias)
    import sys
    if "--custos" in sys.argv or not CUSTOS.exists() or (time.time() - CUSTOS.stat().st_mtime) > 30 * 86400:
        c = custos_conab(lista)
        if not c.empty:
            c.to_csv(CUSTOS, sep=";", index=False, encoding="utf-8")
            registrar(f"custos Conab gravados: {len(c)} culturas")
    registrar(f"commodities: fim, {erros} erros")


if __name__ == "__main__":
    main()
