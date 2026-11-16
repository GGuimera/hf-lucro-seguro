"""Checks for the hydroponic fodder calculations. Run (inside the project folder):
    .venv\\Scripts\\python.exe tests\\teste_forragem.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "painel"))
import forragem_calc as F  # noqa: E402
import modelo as M  # noqa: E402

# Sizing by hand: 10 animals x 100 kg x 3% DMI x 50% of diet = 15 kg DM; at 20% DM = 75 kg fresh;
# 5 kg fresh per kg seed -> 15 kg seed; tray holds 2 kg/m2 x 0.375 m2 = 0.75 kg -> 20 trays/day; 10-day cycle.
g = pd.Series({"dm_pct": 20, "fresh_kg_per_kg_seed": 5, "seed_kg_m2": 2, "cycle_days": 10})
a = pd.Series({"weight_kg": 100, "dmi_pct_bw": 3})
s = F.size_system(g, a, 10, 50)
assert abs(s["fed_dm_kg"] - 15) < 1e-9 and abs(s["fed_fresh_kg"] - 75) < 1e-9 and abs(s["seed_kg"] - 15) < 1e-9, s
assert s["trays_day"] == 20 and s["trays"] == 200 and s["racks"] == 20, s
s2 = F.size_system(g, a, 10, 50, surplus_kg_day=25, loss_pct=20)  # 100 kg to produce, 20% lost -> 25 kg seed
assert abs(s2["seed_kg"] - 25) < 1e-9, s2
cal = F.schedule(10, s)
assert cal.loc[cal["harvest_trays"] > 0, "day"].min() == 12  # soak day 1, sow day 2, harvest 10 days later
print("ok: sizing and schedule match the hand calculation")

# Cash flow: invest 1000, earn 300, spend 100 -> +200/month -> pays back in month 5.
c = F.cashflow(1000, 100, 300, 0, months=36, rate_year=0.0)
assert c["payback"] == 5 and abs(c["npv"] - 6200) < 1e-6, c
assert c["irr_year"] is not None and c["irr_year"] > 0
assert F.cashflow(1000, 300, 100, 0)["payback"] is None  # loses money every month: never pays back
assert abs(F.break_even_seed_price({"seed": 600, "energy": 100}, 1000, 0, 10) - 3.0) < 1e-9  # (1000-100)/(30*10)
print("ok: cash flow, payback, NPV, IRR and break-even")

# Feed comparison: R$ 0.35/kg at 35% DM = R$ 1.00/kg DM; at 10% CP = R$ 10.00/kg CP.
feeds = pd.DataFrame([{"name": "silagem", "dm_pct": 35, "cp_pct": 10, "price_kg": 0.35}], index=["S"])
t = F.feed_comparison(feeds, "FVH", 0.20, 20, 10)
assert abs(t.loc["S", "brl_kg_dm"] - 1.0) < 1e-9 and abs(t.loc["S", "brl_kg_cp"] - 10.0) < 1e-9, t
assert abs(t.loc["FODDER", "brl_kg_dm"] - 1.0) < 1e-9
print("ok: cost per kg of dry matter and protein")

# Monte Carlo: percentiles ordered; flat price history -> no spread.
rng = np.random.default_rng(1)
serie = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.05, 150))) * 50)
mc = F.price_scenarios(serie, {"seed": 500, "energy": 100}, 1000, 0, 5000)
assert mc["npv"]["p10"] <= mc["npv"]["p50"] <= mc["npv"]["p90"], mc["npv"]
flat = F.price_scenarios(pd.Series([50.0] * 150), {"seed": 500, "energy": 100}, 1000, 0, 5000, rate_year=0.0)
assert abs(flat["npv"]["p10"] - flat["npv"]["p90"]) < 1e-6 and abs(flat["npv"]["p50"] - (-5000 + 400 * 36)) < 1e-6
print("ok: price scenarios")

# Parts presets and climate gear.
ref = F.load_reference()
p1, p3 = F.preset(ref["parts"], 1), F.preset(ref["parts"], 3)
assert "REGA_MANUAL" in p1 and "REGA_AUTO" not in p1 and "AR_COND" not in p1
assert "REGA_AUTO" in p3 and "REGA_MANUAL" not in p3 and "AR_COND" in p3 and "EXAUSTOR" not in p3
b = F.bill(ref["parts"], p1, s)
assert b.loc[b["item"] == "BANDEJA", "qty"].iloc[0] == 200 + 20 and (b.loc[b["item"] != "BANDEJA", "total"] > 0).all()
iso = F.bill(ref["parts"], ["ISOLAMENTO"], s, None, 50.0)
assert abs(iso["price"].iloc[0] - 60.0) < 1e-9  # existing farm buildings cover half of the room
assert F.milk_income_month(10, 3.0, 2.5) == 2250.0
venda = F.business_flows("Vender o sistema", 12, 1000.0, 400.0, 3)
assert np.allclose(venda, 600.0)
aluguel = F.business_flows("Alugar o sistema", 12, 100.0, 400.0, 4)
assert np.allclose(aluguel, [-400.0, -300.0, -200.0, -100.0])
assert not F.business_flows("Só na minha fazenda", 12, 100.0, 400.0, 3).any()
assert F.climate_exposure(0.4, 0.2, p3)[2] == 0.0
assert abs(F.climate_exposure(0.4, 0.2, ["EXAUSTOR"])[2] - (0.2 * 30 + 0.2 * 20)) < 1e-9
assert abs(F.total_loss(10, 10) - 19.0) < 1e-9
print("ok: presets, bill of materials and climate exposure")

# Risk score stays within 0-100 at the extremes.
lo, _ = F.risk_score(0.0, 0.0, 0, 0.0, 0.0, 0.0, 1)
hi, _ = F.risk_score(2.0, 1.0, 50, 3.0, 50.0, 80.0, None)
assert 0 <= lo < 10 and hi == 100, (lo, hi)
print("ok: risk score within 0-100")

# Reference files: every column parsed (a stray ';' in text would add columns) and PDF renders.
for n, cols in {"grains": 17, "animals": 8, "feeds": 6, "quality": 4}.items():
    assert ref[n].shape[1] == cols, (n, ref[n].columns.tolist())
assert ref["parts"].shape[1] == 11
pdf = F.pdf_report("Teste ção", [("Seção", [("Preço", "R$ 1,00 — ok")])])
assert pdf[:4] == b"%PDF"
print("ok: reference files and PDF")

if not M.ONLINE:
    import agro_calc as A
    lista, mensal, _, _ = A.carregar()
    for gr, row in ref["grains"].iterrows():
        p, _, mes = F.grain_price(row, mensal, lista)
        assert 0.3 < p < 3.0, f"{gr}: R$ {p:.2f}/kg ({mes}) looks wrong"
        assert len(F.series_brl_kg(mensal, lista, row["risk_proxy"])) > 100, gr
    for fd, row in ref["feeds"].iterrows():
        assert 0.01 < F.feed_price(row, mensal, lista) < 5, fd
    by, hot, cold = F.climate_fit("CASCAVEL")
    assert len(by) == 12 and 0 <= hot <= 1 and 0 <= cold <= 1
    print("ok: real prices in R$/kg are plausible and weather data is present")
