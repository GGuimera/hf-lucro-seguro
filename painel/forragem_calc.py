"""Hydroponic fodder viability: sizing, costs, cash flow, price scenarios and risk (pure logic, no Streamlit).

Prices come from the Preço Seguro database (Cepea series, IPCA-adjusted); grains without a free series use the
manual quote in dados/forragem/graos.csv and a proxy series (corn or wheat) for volatility and seasonality.
"""
import json
import re
import math
import sqlite3
import sys
from datetime import datetime

import numpy as np
import pandas as pd

import agro_calc as A
import modelo as M

DATA = M.PASTA / "dados" / "forragem"
RUNS = DATA / "simulacoes.json"
TIERS = {1: "Básico", 2: "Intermediário", 3: "Avançado"}

TRAY_M2 = 0.375            # 25 x 150 cm tray from a pallet protector
TRAYS_PER_RACK = 10        # 5 shelves x 2 trays
RACK_FLOOR_M2 = 1.0        # rack footprint plus aisle
AC_M2, FAN_M2, SENSOR_M2 = 25, 100, 50  # m² of room covered by one unit
WATER_L_PER_KG = 1.5       # irrigation water per kg of fresh fodder (FAO FVH manual)
SOAK_L_PER_KG_SEED = 2.0
LABOR_H_FIXED, LABOR_H_PER_TRAY = 0.5, 0.02  # ~1.2 min per tray: wash, sow, harvest
HOT_C, COLD_C = 28.0, 12.0  # outside daily max/min that push the room out of the 18-24 °C range
RISK_WEIGHTS = {"price": 20, "season": 10, "news": 10, "enso": 10, "climate": 15, "quality": 15, "finance": 20}


# ---------- reference data ----------
def load_reference():
    r = lambda n: pd.read_csv(DATA / f"{n}.csv", sep=";")
    return {"grains": r("graos").set_index("grain"), "animals": r("animais").set_index("animal"),
            "feeds": r("alimentos").set_index("feed"), "parts": r("componentes"), "quality": r("qualidade")}


def _has(v):
    return isinstance(v, str) and v != ""


def series_brl_kg(mensal, lista, code):
    """IPCA-adjusted monthly price of a Preço Seguro series, in R$/kg."""
    unit = lista.set_index("produto").loc[code, "unidade"]
    return A.serie(mensal, code).dropna() / A.kg_por_unidade(unit)


def grain_price(g, mensal, lista):
    """(R$/kg, source, reference month): latest series value, or the manual quote per 60 kg bag."""
    if _has(g["price_code"]):
        s = series_brl_kg(mensal, lista, g["price_code"])
        if len(s):
            return float(s.iloc[-1]), g["price_source"], str(s.index[-1])
    return float(g["manual_price_bag60"]) / 60, g["price_source"], g["price_date"]


def feed_price(f, mensal, lista):
    if _has(f["price_code"]):
        s = series_brl_kg(mensal, lista, f["price_code"])
        if len(s):
            return float(s.iloc[-1])
    return float(f["price_kg"])


def grain_table(grains, prices):
    """Yield and nutrition per grain; prices = {grain: R$/kg of seed}."""
    t = grains.copy()
    t["dm_kg_per_kg_seed"] = t["fresh_kg_per_kg_seed"] * t["dm_pct"] / 100
    t["dm_loss_pct"] = (1 - t["dm_kg_per_kg_seed"] / 0.88) * 100  # seed is ~88% dry matter
    t["fresh_kg_m2_year"] = t["seed_kg_m2"] * t["fresh_kg_per_kg_seed"] * 365 / t["cycle_days"]
    t["seed_brl_kg"] = pd.Series(prices)
    t["seed_brl_per_kg_dm"] = t["seed_brl_kg"] / t["dm_kg_per_kg_seed"]
    return t


# ---------- sizing and operation ----------
def size_system(grain, animal, heads, diet_pct, surplus_kg_day=0.0, loss_pct=0.0):
    fed_dm = heads * animal["weight_kg"] * animal["dmi_pct_bw"] / 100 * diet_pct / 100
    fed_fresh = fed_dm / (grain["dm_pct"] / 100)
    produced = fed_fresh + surplus_kg_day
    seed = produced / (grain["fresh_kg_per_kg_seed"] * (1 - loss_pct / 100))
    trays_day = math.ceil(seed / (grain["seed_kg_m2"] * TRAY_M2)) if seed > 0 else 0
    trays = trays_day * int(grain["cycle_days"])
    racks = math.ceil(trays / TRAYS_PER_RACK)
    return {"fed_dm_kg": fed_dm, "fed_fresh_kg": fed_fresh, "surplus_kg": surplus_kg_day, "produced_kg": produced,
            "seed_kg": seed, "trays_day": trays_day, "trays": trays, "racks": racks, "area_m2": racks * RACK_FLOOR_M2}


def schedule(cycle_days, size, days=None):
    """Start-up calendar: day 1 soak, day 2 sow, first harvest `cycle_days` after sowing, then every day."""
    days = days or 2 * cycle_days + 2
    rows = []
    for d in range(1, days + 1):
        harvest = d >= cycle_days + 2
        rows.append({"day": d, "soak_seed_kg": size["seed_kg"], "sow_trays": size["trays_day"] if d >= 2 else 0,
                     "harvest_trays": size["trays_day"] if harvest else 0,
                     "harvest_kg": size["produced_kg"] if harvest else 0.0})
    return pd.DataFrame(rows)


def preset(parts, tier):
    """Items of a tier: everything up to it; in exclusive categories only the most advanced option."""
    p = parts[parts["tier"] <= tier]
    excl = p[p["exclusive"] == "yes"]
    keep = excl.loc[excl.groupby("category")["tier"].idxmax()]
    return pd.concat([p[p["exclusive"] != "yes"], keep]).sort_index()["item"].tolist()


EXISTING_CATEGORIES = ("sala", "agua", "molho")


def bill(parts, selected, size, ipca=None, existing_pct=0.0):
    """Bill of materials with quantities scaled to the system size (prices brought to today by IPCA if given).
    existing_pct: share of room, water and soak-tank costs already paid for by existing farm buildings."""
    area = math.ceil(size["area_m2"])
    qty = {"tray": size["trays"] + size["trays_day"], "rack": size["racks"], "m2": area, "unit": 1,
           "ac": math.ceil(area / AC_M2), "fan": math.ceil(area / FAN_M2), "sensor": math.ceil(area / SENSOR_M2)}
    b = parts[parts["item"].isin(selected)].copy()
    b["qty"] = b["scale"].map(qty)
    if ipca is not None:
        b["price"] = b["price"] * ipca(b["price_date"].str[:7].tolist())
    existing = b["category"].isin(EXISTING_CATEGORIES)
    b.loc[existing, "price"] = b.loc[existing, "price"] * (1 - existing_pct / 100)
    return totals(b)


def milk_income_month(cows, gain_l_day, price_l):
    return 30 * cows * gain_l_day * price_l


def business_flows(model, clients_year, unit_value, unit_cost, months):
    """Monthly cash from selling or renting out the system (cost of building each unit = unit_cost).
    Rent starts the month after each unit is installed."""
    novos = np.full(months, clients_year / 12)
    if model == "Vender o sistema":
        return novos * (unit_value - unit_cost)
    if model == "Alugar o sistema":
        ativos = np.concatenate([[0.0], np.cumsum(novos)[:-1]])
        return ativos * unit_value - novos * unit_cost
    return np.zeros(months)


def totals(b):
    b = b.copy()
    b["total"] = b["price"] * b["qty"]
    b["kwh_total"] = b["kwh_day"] * b["qty"]
    b["depr_year"] = b["total"] / b["life_years"]
    return b


def resources(size, kwh_day):
    water = size["produced_kg"] * WATER_L_PER_KG + size["seed_kg"] * SOAK_L_PER_KG_SEED
    labor = LABOR_H_FIXED + size["trays_day"] * LABOR_H_PER_TRAY if size["trays_day"] else 0.0
    return {"water_l": water, "kwh": kwh_day, "labor_h": labor}


def monthly_costs(size, res, seed_price, tariff, water_m3, wage, nutrients_month=0.0):
    return {"seed": 30 * size["seed_kg"] * seed_price, "energy": 30 * res["kwh"] * tariff,
            "water": 30 * res["water_l"] / 1000 * water_m3, "labor": 30 * res["labor_h"] * wage,
            "nutrients": nutrients_month}


def feed_comparison(feeds, fodder_name, fodder_brl_kg, fodder_dm_pct, fodder_cp_pct):
    """R$ per kg of dry matter and per kg of crude protein; feeds needs name, dm_pct, cp_pct, price_kg."""
    t = pd.concat([feeds[["name", "dm_pct", "cp_pct", "price_kg"]],
                   pd.DataFrame([{"name": fodder_name, "dm_pct": fodder_dm_pct, "cp_pct": fodder_cp_pct,
                                  "price_kg": fodder_brl_kg}], index=["FODDER"])])
    t["brl_kg_dm"] = t["price_kg"] / (t["dm_pct"] / 100)
    t["brl_kg_cp"] = t["brl_kg_dm"] / (t["cp_pct"] / 100)
    return t


# ---------- money ----------
def _monthly_rate(rate_year):
    return (1 + rate_year) ** (1 / 12) - 1


def cashflow(capex, opex, savings, sales, months=36, rate_year=0.12, ramp_days=0):
    """Monthly cash flow (month 0 = investment). opex/savings/sales may be scalars or arrays of `months`."""
    income = np.broadcast_to(np.asarray(savings, float) + np.asarray(sales, float), (months,)).copy()
    income[0] *= 1 - min(ramp_days, 30) / 30  # no fodder while the first batch grows
    flows = np.concatenate([[-capex], income - np.broadcast_to(np.asarray(opex, float), (months,))])
    cum = flows.cumsum()
    pos = np.nonzero(cum >= 0)[0]
    r = _monthly_rate(rate_year)
    npv = float((flows / (1 + r) ** np.arange(months + 1)).sum())
    return {"flows": flows, "cum": cum, "payback": int(pos[0]) if len(pos) else None, "npv": npv,
            "irr_year": _irr_year(flows)}


def _irr_year(flows):
    f = lambda r: (flows / (1 + r) ** np.arange(len(flows))).sum()
    lo, hi = -0.99, 10.0
    if f(lo) * f(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(lo) * f(mid) > 0 else (lo, mid)
    return (1 + mid) ** 12 - 1


def break_even_seed_price(costs, savings, sales, seed_kg):
    other = sum(v for k, v in costs.items() if k != "seed")
    return (savings + sales - other) / (30 * seed_kg) if seed_kg else float("nan")


def price_scenarios(series, costs, savings, sales, capex, seed_follows_feed=False, months=36, rate_year=0.12,
                    ramp_days=0, n=2000, seed=42):
    """Monte Carlo: seed cost follows resampled real monthly returns of the price series (last 10 years).
    If the replaced feed is priced by the same series, the savings move with it too."""
    ret = np.log(series.tail(121)).diff().dropna().values
    rng = np.random.default_rng(seed)
    factor = np.exp(np.cumsum(rng.choice(ret, size=(n, months)), axis=1))
    other = sum(v for k, v in costs.items() if k != "seed")
    opex = other + costs["seed"] * factor
    sav = savings * factor if seed_follows_feed else np.full((n, months), float(savings))
    income = sav + sales
    income[:, 0] *= 1 - min(ramp_days, 30) / 30
    flows = np.hstack([np.full((n, 1), -capex), income - opex])
    r = _monthly_rate(rate_year)
    npv = (flows / (1 + r) ** np.arange(months + 1)).sum(axis=1)
    cum = flows.cumsum(axis=1)
    ok = (cum >= 0).any(axis=1)
    payback = np.where(ok, (cum >= 0).argmax(axis=1), np.nan)
    q = lambda x: dict(zip(("p10", "p50", "p90"), np.nanpercentile(x, [10, 50, 90]))) if np.isfinite(x).any() else {}
    return {"npv": q(npv), "payback": q(payback), "never_pays_pct": float((~ok).mean() * 100),
            "loss_pct": float((npv < 0).mean() * 100),
            "seed_cost_fan": pd.DataFrame(np.percentile(costs["seed"] * factor, [10, 50, 90], axis=0).T,
                                          columns=["p10", "p50", "p90"], index=range(1, months + 1))}


# ---------- climate ----------
def regions():
    cols = ["polo", "nome", "uf"]
    p = pd.concat([pd.read_csv(M.PASTA / "dados" / f, sep=";", usecols=cols) for f in ("polos.csv", "polos_agro.csv")])
    return p.drop_duplicates("polo").set_index("polo")


def climate_fit(polo, years=5):
    """Share of days per month with outside max above HOT_C or min below COLD_C (local daily weather table)."""
    with sqlite3.connect(M.BANCO) as con:
        d = pd.read_sql("SELECT data, tmax, tmin FROM clima_diario WHERE polo = ? AND data >= date('now', ?)",
                        con, params=[polo, f"-{years} years"])
    if d.empty:
        return pd.DataFrame(), float("nan"), float("nan")
    d["month"] = pd.to_datetime(d["data"]).dt.month
    d["hot"], d["cold"] = d["tmax"] > HOT_C, d["tmin"] < COLD_C
    return d.groupby("month")[["hot", "cold"]].mean().reindex(range(1, 13)), d["hot"].mean(), d["cold"].mean()


def climate_exposure(hot, cold, selected):
    """Hot/cold day shares left after the climate gear; yield loss % from those days."""
    if "AR_COND" in selected:
        h = c = 0.0
    else:
        h = hot * (0.5 if "EXAUSTOR" in selected else 1)
        c = cold * (0.5 if "ISOLAMENTO" in selected else 1)
    return h, c, h * 30 + c * 20


def total_loss(quality_loss_pct, climate_loss_pct):
    return (1 - (1 - quality_loss_pct / 100) * (1 - climate_loss_pct / 100)) * 100


# ---------- market risk ----------
def latest_oni():
    with sqlite3.connect(M.BANCO) as con:
        try:
            r = con.execute("SELECT mes, valor FROM fatores_mensal WHERE produto = 'ENSO_ONI' "
                            "ORDER BY mes DESC LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            return None
    return r


def volatility_year(series, months=60):
    ret = np.log(series.tail(months + 1)).diff().dropna()
    return float(ret.std() * math.sqrt(12)) if len(ret) > 12 else float("nan")


def best_buy_months(series, k=3):
    por_mes, _ = A.indices(series)
    m = por_mes["mean"].dropna()
    return list(m.sort_values().head(k).index), m


UP = r"\b(alta|altas|sobe|sobem|subiu|dispara|disparam|encarece|valoriza|recorde de preco)"


def news(grain_name, n_max=40):
    """Recent headlines (last 2 days, Google News RSS) about the grain, feed and power prices, classified with the
    same keywords as the Preço Seguro news collector."""
    if str(M.PASTA / "coleta") not in sys.path:
        sys.path.insert(0, str(M.PASTA / "coleta"))
    import buscar_noticias as N
    rows, seen = [], set()
    for q in (f"{grain_name.lower()} preço", "ração animal preço", "tarifa energia elétrica"):
        try:
            for it in N.buscar(q):
                if it["titulo"] in seen:
                    continue
                seen.add(it["titulo"])
                t = N.sem_acento(it["titulo"]) + " "
                tipo = next((tp for tp, rx in N.TIPOS if re.search(rx, t)), "mercado")
                rows.append({"date": it["data"].date(), "title": it["titulo"], "type": tipo,
                             "up": bool(re.search(UP, t)), "source": it["fonte"], "url": it["url"], "query": q})
        except Exception:
            continue
    return pd.DataFrame(rows).sort_values("date", ascending=False).head(n_max) if rows else pd.DataFrame()


def weather_alerts(polo, days=30):
    f = M.PASTA / "dados" / "noticias_clima.csv"
    if not f.exists():
        return pd.DataFrame()
    a = pd.read_csv(f, sep=";", dtype=str).fillna("")
    a = a[a["polos"].str.split("|").apply(lambda ps: polo in ps)]
    return a[pd.to_datetime(a["data"]) >= pd.Timestamp.now() - pd.Timedelta(days=days)]


def _clip(v):
    return float(np.clip(v, 0, 100)) if pd.notna(v) else 50.0  # unknown -> middle


def risk_score(vol, season_pos, n_risk_news, oni, climate_loss_pct, quality_loss_pct, payback):
    """0-100 per factor (higher = riskier) and their weighted mean."""
    parts = {
        "price": _clip((vol - 0.10) / 0.30 * 100),
        "season": _clip(season_pos * 100),
        "news": _clip(n_risk_news * 15),
        "enso": _clip(abs(oni) * 100 if oni is not None else np.nan),
        "climate": _clip(climate_loss_pct * 5),
        "quality": _clip(quality_loss_pct * 2.5),
        "finance": 100.0 if payback is None else _clip((payback - 6) / 30 * 100),
    }
    total = sum(parts[k] * w for k, w in RISK_WEIGHTS.items()) / sum(RISK_WEIGHTS.values())
    return total, parts


# ---------- saved runs and report ----------
def load_runs():
    return json.loads(RUNS.read_text(encoding="utf-8")) if RUNS.exists() else []


def save_run(run):
    runs = load_runs() + [dict(run, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M"))]
    RUNS.write_text(json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8")
    return runs


def _latin1(t):
    t = str(t).replace("—", "-").replace("−", "-").replace("–", "-").replace("²", "2").replace("≥", ">=")
    return t.encode("latin-1", "replace").decode("latin-1")


def pdf_report(title, sections):
    """sections = [(heading, [(label, value), ...]), ...] -> PDF bytes (text and tables only)."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(True, 15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 9, _latin1(title))
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, _latin1(f"Gerado em {datetime.now():%d/%m/%Y %H:%M} pelo Preço Seguro"), new_x="LMARGIN", new_y="NEXT")
    for heading, rows in sections:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, _latin1(heading), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for label, value in rows:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(70, 6, _latin1(label), new_x="RIGHT", new_y="TOP")
            pdf.multi_cell(0, 6, _latin1(value), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
