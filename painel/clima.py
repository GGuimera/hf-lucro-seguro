"""Página: Clima e alertas nos polos produtores (previsão de 3 modelos, alertas por cultura e o normal de cada região)."""
import json
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import modelo as M
from modelo import MESES, num

FUNDO, TEXTO, TEXTO_2, GRADE = "#1a1a19", "#f0efec", "#c3c2b7", "#2e2e2b"
# uma cor fixa por modelo (paleta validada para fundo escuro e daltonismo), sempre na mesma ordem
MODELOS = {"ecmwf_ifs025": ("Europeu (ECMWF)", "#3987e5"), "gfs_seamless": ("Americano (GFS)", "#d95926"),
           "icon_seamless": ("Alemão (ICON)", "#199e70")}
POLOS = M.PASTA / "dados" / "polos.csv"
POLOS_CULT = M.PASTA / "dados" / "polos_culturas.csv"
LIMITES = M.PASTA / "dados" / "clima_limites.csv"
TIPOS = {"geada": "❄️ Geada", "calor": "🔥 Calor forte", "chuva": "🌧️ Chuva forte", "chuva3": "🌧️ Chuva acumulada (3 dias)"}

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      .cartao {background:#1f1f1d; border:1px solid #2e2e2b; border-radius:14px; padding:16px 18px; height:100%;}
      .cartao .rotulo {color:#c3c2b7; font-size:0.85rem;}
      .cartao .valor {color:#f0efec; font-size:1.45rem; font-weight:650; line-height:1.25;}
      .cartao .detalhe {color:#9a998f; font-size:0.8rem; margin-top:4px;}
      .dica {color:#c3c2b7; font-size:0.92rem;}
      .aviso {background:#2a2418; border:1px solid #5c4a1f; border-radius:12px; padding:12px 16px; color:#e8dcc0; font-size:0.88rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def cartao(rotulo, valor, detalhe=""):
    st.markdown(f'<div class="cartao"><div class="rotulo">{rotulo}</div><div class="valor">{valor}</div>'
                f'<div class="detalhe">{detalhe}</div></div>', unsafe_allow_html=True)


def visual(fig, titulo_y, altura=360, sufixo=""):
    fig.update_layout(paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, font=dict(color=TEXTO, size=13), height=altura,
                      margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=1.14, x=0, font=dict(color=TEXTO_2)),
                      hoverlabel=dict(bgcolor="#262624", font_color=TEXTO))
    fig.update_xaxes(showgrid=False, linecolor=GRADE, tickfont=dict(color=TEXTO_2))
    fig.update_yaxes(gridcolor=GRADE, zeroline=False, tickfont=dict(color=TEXTO_2), ticksuffix=sufixo,
                     title=dict(text=titulo_y, font=dict(color=TEXTO_2)))
    return fig


@st.cache_data
def carregar_polos():
    polos = pd.read_csv(POLOS, sep=";")
    pc = pd.read_csv(POLOS_CULT, sep=";") if POLOS_CULT.exists() else pd.DataFrame(columns=["polo", "produto", "participacao"])
    lim = pd.read_csv(LIMITES, sep=";").set_index("produto")
    return polos, pc, lim


@st.cache_data(ttl=3 * 3600, show_spinner="Buscando a previsão dos 3 modelos…")
def previsao(lat, lon, polo):
    """Previsão de 16 dias ao vivo (Open-Meteo). Se falhar, usa a última foto guardada pelo coleta\\clima.py."""
    v = "temperature_2m_max,temperature_2m_min,precipitation_sum"
    u = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
        {"latitude": lat, "longitude": lon, "daily": v, "models": ",".join(MODELOS), "forecast_days": 16,
         "timezone": "America/Sao_Paulo"})
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "PrecoSeguro/0.1"}), timeout=30) as r:
            d = json.load(r)["daily"]
        partes = [pd.DataFrame({"modelo": m, "data": d["time"], "tmax": d.get(f"temperature_2m_max_{m}"),
                                "tmin": d.get(f"temperature_2m_min_{m}"), "chuva": d.get(f"precipitation_sum_{m}")})
                  for m in MODELOS]
        return pd.concat(partes, ignore_index=True).assign(data=lambda x: pd.to_datetime(x["data"])), "ao vivo"
    except Exception:
        with sqlite3.connect(M.BANCO) as con:
            if not con.execute("SELECT name FROM sqlite_master WHERE name='previsao_log'").fetchone():
                return pd.DataFrame(), "indisponível"
            ult = con.execute("SELECT MAX(coletado_em) FROM previsao_log WHERE polo = ?", (polo,)).fetchone()[0]
            df = pd.read_sql("SELECT modelo, data, tmax, tmin, chuva FROM previsao_log WHERE polo = ? AND coletado_em = ?",
                             con, params=(polo, ult))
        return df.assign(data=lambda x: pd.to_datetime(x["data"])), f"foto guardada de {ult}"


@st.cache_data(show_spinner="Carregando o histórico de clima…")
def historico(polo):
    with sqlite3.connect(M.BANCO) as con:
        if not con.execute("SELECT name FROM sqlite_master WHERE name='clima_diario'").fetchone():
            return pd.DataFrame()
        h = pd.read_sql("SELECT data, tmax, tmin, chuva, et0 FROM clima_diario WHERE polo = ?", con, params=(polo,))
    h["data"] = pd.to_datetime(h["data"])
    return h


def janela_dias(datas, folga=7):
    """Dias do ano (1-366) das datas, com folga de ±7 dias."""
    alvo = set()
    for d in datas:
        alvo |= {((d.day_of_year - 1 + k) % 366) + 1 for k in range(-folga, folga + 1)}
    return alvo


def normal_do_periodo(h, datas):
    """Chuva e mínima normais (média 2000 em diante) para os mesmos dias do calendário, suavizada em ±7 dias."""
    if h.empty:
        return np.nan, np.nan
    sel = h[h["data"].dt.day_of_year.isin(janela_dias(datas))]
    chuva_dia = sel["chuva"].mean()
    return chuva_dia * len(datas), sel["tmin"].mean()


def alertas(prev, culturas, lim, h=None):
    """Para cada cultura e dia: quantos dos 3 modelos preveem geada, calor ou chuva forte, e se isso
    é comum nesta época no polo (% dos dias do histórico, mesma época ±7 dias, em que aconteceu)."""
    linhas = []
    p = prev.sort_values(["modelo", "data"]).copy()
    p["chuva3"] = p.groupby("modelo")["chuva"].transform(lambda s: s.rolling(3, min_periods=3).sum())
    if h is not None and len(h):
        h = h.sort_values("data").assign(chuva3=lambda x: x["chuva"].rolling(3, min_periods=3).sum(),
                                          doy=lambda x: x["data"].dt.day_of_year)
    freq_cache = {}

    def frequencia(col, sinal, limite, dia):
        if h is None or not len(h):
            return np.nan
        chave = (col, sinal, limite, dia.day_of_year)
        if chave not in freq_cache:
            s = h.loc[h["doy"].isin(janela_dias([dia])), col].dropna()
            freq_cache[chave] = float(((s <= limite) if sinal == "<=" else (s >= limite)).mean()) if len(s) else np.nan
        return freq_cache[chave]
    for prod in culturas:
        if prod not in lim.index:
            continue
        L = lim.loc[prod]
        testes = {"geada": ("tmin", "<=", L["geada_tmin"], f"mínima ≤ {num(L['geada_tmin'], 0)} °C"),
                  "calor": ("tmax", ">=", L["calor_tmax"], f"máxima ≥ {num(L['calor_tmax'], 0)} °C"),
                  "chuva": ("chuva", ">=", L["chuva_dia"], f"≥ {num(L['chuva_dia'], 0)} mm no dia"),
                  "chuva3": ("chuva3", ">=", L["chuva_3dias"], f"≥ {num(L['chuva_3dias'], 0)} mm em 3 dias")}
        for tipo, (col, sinal, limite, regra) in testes.items():
            cond = (p[col] <= limite) if sinal == "<=" else (p[col] >= limite)
            sel = p[cond.fillna(False)]
            for dia, g in sel.groupby("data"):
                vals = g[col]
                linhas.append({"data": dia, "produto": prod, "tipo": tipo, "k": g["modelo"].nunique(), "regra": regra,
                               "valor": f"{num(vals.min(), 0)} a {num(vals.max(), 0)}" if len(vals) > 1 else num(vals.iloc[0], 0),
                               "freq": frequencia(col, sinal, limite, dia)})
    a = pd.DataFrame(linhas)
    if a.empty:
        return a
    return a.sort_values(["data", "k"], ascending=[True, False])


polos, pc, lim = carregar_polos()
_, _, cult, _, _, _ = M.carregar()
nomes_cult = dict(zip(cult["produto"], cult["nome"]))

st.title("🌦️ Clima e alertas nos polos produtores")
st.markdown(
    "O preço da Ceasa nasce no campo: **chuva, geada e calor nas regiões que mais produzem** mudam a oferta semanas depois. "
    "Aqui você vê a previsão dos **3 principais modelos do mundo** para cada polo, os **alertas por cultura** e o **normal** da região."
)

# ---------- Escolha do polo ----------
rotulos = {f"{r.nome} — {r.uf}": r.polo for r in polos.itertuples()}
esc = st.selectbox("Polo produtor", list(rotulos))
P = polos.set_index("polo").loc[rotulos[esc]]
polo = rotulos[esc]
cult_polo = pc[pc["polo"] == polo].sort_values("participacao", ascending=False, na_position="last")


def txt_cult(r):
    n = nomes_cult.get(r.produto, r.produto.title())
    return f"{n} ({r.participacao:.0%} do Brasil)" if pd.notna(r.participacao) and r.participacao != "" else f"{n} (polo conhecido)"


c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    cartao("Altitude", f"{int(P['altitude_m']):,} m".replace(",", "."), f"{P['municipio_ref']} – {P['uf']}")
with c2:
    cartao("Coordenadas", f"{num(P['lat'], 2)}, {num(P['lon'], 2)}", "ponto de referência do polo")
with c3:
    cartao("O que o polo produz", " · ".join(txt_cult(r) for r in cult_polo.itertuples()) or "—",
           "% = parte da produção nacional (IBGE, média 2022–2024)")

prev, origem = previsao(float(P["lat"]), float(P["lon"]), polo)
h = historico(polo)

# ---------- 1. Previsão ----------
st.subheader("1. Próximos 16 dias: o que dizem os 3 modelos")
if prev.empty:
    st.warning("Não foi possível buscar a previsão agora (sem internet?) e ainda não há previsão guardada. Rode coleta\\clima.py.")
    st.stop()
st.markdown(f'<p class="dica">Fonte: Open-Meteo ({origem}). Quando os 3 modelos concordam, a previsão é mais segura; '
            "quando discordam muito, trate como incerta. Previsões além de 7–10 dias erram bem mais.</p>", unsafe_allow_html=True)
med = prev.groupby("data")[["tmax", "tmin", "chuva"]].median()
chuva_prev = med["chuva"].sum()
chuva_norm, tmin_norm = normal_do_periodo(h, med.index)
k1, k2, k3, k4 = st.columns(4)
with k1:
    cartao("Chuva prevista (16 dias)", f"{num(chuva_prev, 0)} mm", "mediana dos 3 modelos")
with k2:
    if pd.notna(chuva_norm) and chuva_norm > 0:
        cartao("Comparado ao normal", f"{chuva_prev / chuva_norm:.0%}".replace(".", ","),
               f"normal para estes dias: {num(chuva_norm, 0)} mm (2000 em diante)")
    else:
        cartao("Comparado ao normal", "—", "rode coleta\\clima.py para ter o histórico")
with k3:
    cartao("Menor mínima prevista", f"{num(prev['tmin'].min(), 1)} °C",
           f"normal da mínima nestes dias: {num(tmin_norm, 1)} °C" if pd.notna(tmin_norm) else "")
with k4:
    tot = prev.groupby("modelo")["chuva"].sum()
    cartao("Diferença entre modelos", f"{num(tot.min(), 0)} a {num(tot.max(), 0)} mm", "chuva total de cada modelo")

fig = go.Figure()
for m, (nome, cor) in MODELOS.items():
    g = prev[prev["modelo"] == m]
    fig.add_trace(go.Bar(x=g["data"], y=g["chuva"], name=nome, marker=dict(color=cor),
                         hovertemplate=f"{nome}: %{{y:.0f}} mm<extra></extra>"))
fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05)
st.markdown('<p class="dica"><b>Chuva por dia</b> (mm), um modelo por cor.</p>', unsafe_allow_html=True)
st.plotly_chart(visual(fig, "mm", altura=300), width="stretch")

fig2 = go.Figure()
for m, (nome, cor) in MODELOS.items():
    g = prev[prev["modelo"] == m]
    fig2.add_trace(go.Scatter(x=g["data"], y=g["tmax"], name=f"{nome} – máxima", mode="lines+markers",
                              line=dict(color=cor, width=2), marker=dict(size=8, line=dict(color=FUNDO, width=2)),
                              hovertemplate=f"{nome} máx: %{{y:.1f}} °C<extra></extra>"))
    fig2.add_trace(go.Scatter(x=g["data"], y=g["tmin"], name=f"{nome} – mínima", mode="lines+markers",
                              line=dict(color=cor, width=2, dash="dot"), marker=dict(size=8, line=dict(color=FUNDO, width=2)),
                              hovertemplate=f"{nome} mín: %{{y:.1f}} °C<extra></extra>"))
fig2.add_hline(y=3, line=dict(color="#8a897f", width=1, dash="dash"),
               annotation_text="3 °C: risco de geada", annotation_font_color=TEXTO_2, annotation_position="bottom right")
st.markdown('<p class="dica"><b>Temperatura</b>: linha cheia = máxima, pontilhada = mínima.</p>', unsafe_allow_html=True)
st.plotly_chart(visual(fig2, "°C", altura=340, sufixo=" °C"), width="stretch")

# ---------- 2. Alertas ----------
st.subheader("2. Alertas para as culturas")
padrao = [p for p in cult_polo["produto"] if p in lim.index] or ["CENOURA"]
escolha = st.multiselect("Culturas", sorted(lim.index, key=lambda p: nomes_cult.get(p, p)), default=padrao,
                         format_func=lambda p: nomes_cult.get(p, p.title()))
a = alertas(prev, escolha, lim, h)
if a.empty:
    st.success("✅ Nenhum alerta nos próximos 16 dias para as culturas escolhidas, em nenhum dos 3 modelos.")
else:
    fortes = a[a["k"] >= 2]
    raros = fortes[fortes["freq"].lt(0.10)]
    st.markdown(f'<p class="dica"><b>{len(fortes)}</b> alertas em que pelo menos 2 dos 3 modelos concordam '
                f"(<b>{len(raros)}</b> deles raros para a época, acontecem em menos de 10% dos dias), "
                f"e {len(a) - len(fortes)} em que só 1 modelo prevê (menos provável).</p>", unsafe_allow_html=True)
    tab = pd.DataFrame({
        "Dia": a["data"].map(lambda d: f"{['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'][d.weekday()]} {d:%d/%m}"),
        "Cultura": a["produto"].map(lambda p: nomes_cult.get(p, p.title())),
        "Alerta": a["tipo"].map(TIPOS),
        "Modelos que preveem": a["k"].map(lambda k: f"{'🔴' if k == 3 else '🟡' if k == 2 else '⚪'} {k} de 3"),
        "Previsto": a["valor"] + np.where(a["tipo"].isin(["geada", "calor"]), " °C", " mm"),
        "Limite usado": a["regra"],
        "Acontece aqui nesta época?": a["freq"].map(
            lambda f: "—" if pd.isna(f) else f"{'⚠️ raro' if f < 0.10 else 'comum'}: {f:.0%} dos dias".replace(".", ",")),
    })
    st.dataframe(tab, hide_index=True, width="stretch")
st.caption("Limites por cultura em dados\\clima_limites.csv (geada: Embrapa Trigo/INMET — mínima a 2 m ≤ 3 °C costuma dar "
           "cerca de −1 °C na folha; calor e chuva: estimativa inicial, ajustável). Baixadas e fundos de vale costumam "
           "ficar alguns graus mais frios que o ponto de referência.")

# ---------- 3. Normal da região ----------
st.subheader("3. Como é o clima normal deste polo, mês a mês")
if h.empty:
    st.info("O histórico de clima ainda não foi baixado. Rode coleta\\clima.py.")
else:
    h = h.assign(ano=h["data"].dt.year, mes=h["data"].dt.month)
    anos_ok = h.groupby("ano")["data"].count()
    hc = h[h["ano"].isin(anos_ok[anos_ok >= 360].index)]
    por_ano = hc.groupby(["ano", "mes"]).agg(chuva=("chuva", "sum"), tmin=("tmin", "mean"), tmax=("tmax", "mean"),
                                              geada=("tmin", lambda s: (s <= 3).sum()))
    norm = por_ano.groupby("mes").mean()
    anos_txt = f"{hc['ano'].min()}–{hc['ano'].max()}"
    st.markdown(f'<p class="dica">Médias de {hc["ano"].nunique()} anos ({anos_txt}), reanálise ERA5 (Copernicus) pelo Open-Meteo. '
                "A barra mostra a chuva do mês; a linha cheia, a máxima média; a pontilhada, a mínima média.</p>", unsafe_allow_html=True)
    fig3 = go.Figure(go.Bar(x=MESES, y=norm["chuva"], marker=dict(color="#3987e5"), name="Chuva do mês",
                            hovertemplate="%{x}: %{y:.0f} mm<extra></extra>"))
    st.plotly_chart(visual(fig3, "mm por mês", altura=260), width="stretch")
    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(x=MESES, y=norm["tmax"], name="Máxima média", mode="lines+markers", line=dict(color="#d95926", width=2),
                              marker=dict(size=8, line=dict(color=FUNDO, width=2)), hovertemplate="máx %{y:.1f} °C<extra></extra>"))
    fig4.add_trace(go.Scatter(x=MESES, y=norm["tmin"], name="Mínima média", mode="lines+markers",
                              line=dict(color="#3987e5", width=2, dash="dot"),
                              marker=dict(size=8, line=dict(color=FUNDO, width=2)), hovertemplate="mín %{y:.1f} °C<extra></extra>"))
    st.plotly_chart(visual(fig4, "°C", altura=260, sufixo=" °C"), width="stretch")
    tabela = pd.DataFrame({"Mês": MESES, "Chuva (mm)": norm["chuva"].round(0).astype(int).values,
                           "Máxima média (°C)": norm["tmax"].map(lambda v: num(v, 1)).values,
                           "Mínima média (°C)": norm["tmin"].map(lambda v: num(v, 1)).values,
                           "Dias com mínima ≤ 3 °C (média por ano)": norm["geada"].map(lambda v: num(v, 1)).values})
    with st.expander("Ver a tabela do clima normal"):
        st.dataframe(tabela, hide_index=True, width="stretch")
    ult30 = h[h["data"] > h["data"].max() - pd.Timedelta(days=30)]
    if len(ult30) >= 25:
        normal30, _ = normal_do_periodo(hc, ult30["data"])
        st.markdown(f'<div class="aviso">Últimos 30 dias com dado ({ult30["data"].min():%d/%m} a {ult30["data"].max():%d/%m}): '
                    f'<b>{num(ult30["chuva"].sum(), 0)} mm</b> de chuva, contra {num(normal30, 0)} mm normais para a época.</div>',
                    unsafe_allow_html=True)

# ---------- 4. Relevo e microclima ----------
st.subheader("4. Relevo e microclima do polo")
RELEVO, GRADE_R = M.PASTA / "dados" / "relevo_polos.csv", M.PASTA / "dados" / "relevo_grade.csv"
if not RELEVO.exists():
    st.info("O relevo ainda não foi calculado. Rode coleta\\relevo.py.")
else:
    rel = pd.read_csv(RELEVO, sep=";")
    rr = rel[rel["polo"] == polo].set_index("escala")
    if rr.empty:
        st.info("Sem relevo calculado para este polo.")
    else:
        esc_r = st.radio("Área", ["regional", "local"], horizontal=True,
                         format_func=lambda e: f"Região (~{num(rr.loc[e, 'lado_km'], 0)} km de lado)" if e == "regional"
                         else f"Perto do ponto (~{num(rr.loc[e, 'lado_km'], 1)} km de lado)")
        r = rr.loc[esc_r]
        outros = rel[rel["escala"] == esc_r]
        mais_plano_que = int((outros["decl_media"] > r["decl_media"]).sum())
        e1, e2, e3, e4 = st.columns(4)
        with e1:
            cartao("Altitude", f"{num(r['alt_p10'], 0)} a {num(r['alt_p90'], 0)} m",
                   f"80% da área nesta faixa · mín {num(r['alt_min'], 0)}, máx {num(r['alt_max'], 0)} m")
        with e2:
            cartao("Diferença de temperatura", f"~{num(r['dif_temp_p10_p90'], 1)} °C",
                   "entre as partes baixas e altas (0,65 °C a cada 100 m)")
        with e3:
            cartao("Relevo comparado aos outros polos", f"{len(outros) - mais_plano_que}º mais acidentado",
                   f"de {len(outros)} polos (1º = mais acidentado)")
        with e4:
            cartao("Declividade aproximada", f"{num(r['decl_media'], 1)}%",
                   "média; serve para COMPARAR polos — o declive real do talhão é maior")
        if GRADE_R.exists():
            g = pd.read_csv(GRADE_R, sep=";")
            g = g[(g["polo"] == polo) & (g["escala"] == esc_r)]
            z = g.pivot(index="lat", columns="lon", values="alt").sort_index(ascending=False)
            f5 = go.Figure(go.Heatmap(z=z.values, x=[num(v, 3) for v in z.columns], y=[num(v, 3) for v in z.index],
                                      colorscale=[[0, "#173052"], [0.5, "#3987e5"], [1, "#e8e4d0"]], xgap=1, ygap=1,
                                      colorbar=dict(ticksuffix=" m", tickfont=dict(color=TEXTO_2)),
                                      hovertemplate="lat %{y} · lon %{x}: %{z:.0f} m<extra></extra>"))
            f5.update_layout(hovermode="closest")
            f5.update_xaxes(showticklabels=False, title=dict(text="oeste ← → leste", font=dict(color=TEXTO_2)))
            f5.update_yaxes(showticklabels=False)
            st.markdown('<p class="dica"><b>Mapa de altitude</b> em volta do ponto de referência (centro): '
                        "claro = alto, escuro = baixo. Passe o mouse para ver a altitude.</p>", unsafe_allow_html=True)
            st.plotly_chart(visual(f5, "sul ← → norte", altura=380), width="stretch")
        st.markdown(
            f'<div class="aviso"><b>O que isso quer dizer no campo:</b> numa mesma região, a parte {num(r["alt_p90"] - r["alt_p10"], 0)} m '
            f"mais alta fica em média ~{num(r['dif_temp_p10_p90'], 1)} °C mais fria — o que alonga o ciclo e muda a época. Mas em noites "
            "frias e sem vento o <b>ar frio escorre e se junta nas baixadas</b>: é ali que a geada pega primeiro, mesmo sendo mais baixo. "
            "Mapa feito com o Copernicus DEM (pontos de 90 m) pelo Open-Meteo, amostrado a cada "
            f"{'~2,2 km' if esc_r == 'regional' else '~560 m'}: isso <b>suaviza os declives</b> (no teste, a Serra do RJ passou de 31% "
            "para 61% de área \"plana ou suave\" só por espaçar mais os pontos). Use a declividade para comparar polos, nunca para "
            "decidir o talhão.</div>", unsafe_allow_html=True)

# ---------- 5. Notícias de previsão ----------
st.subheader("5. Notícias de previsão do tempo para este polo")
NOT_CLIMA = M.PASTA / "dados" / "noticias_clima.csv"
if not NOT_CLIMA.exists():
    st.info("Ainda não há notícias de clima. A busca diária (coleta\\buscar_noticias.py) acrescenta as novas.")
else:
    nc = pd.read_csv(NOT_CLIMA, sep=";", dtype=str)
    nc = nc[nc["polos"].fillna("").str.split("|").map(lambda ps: polo in ps or "TODOS" in ps)]
    nc = nc.sort_values("data", ascending=False).head(10)
    if nc.empty:
        st.info("Nenhuma notícia de previsão recente cita esta região.")
    icone = {"frio": "❄️", "chuva": "🌧️", "calor": "🔥", "enos": "🌊"}
    for n in nc.itertuples():
        tag = " · 🤖 não conferida" if n.conferida != "sim" else ""
        geral = " · notícia geral do país" if "TODOS" in n.polos.split("|") else ""
        st.markdown(f"{icone.get(n.tipo, '🌤️')} **{n.data[8:10]}/{n.data[5:7]}** · [{n.titulo}]({n.url}) — {n.fonte}{geral}{tag}")
    st.caption("Encontradas automaticamente no Google Notícias todo dia (só título, fonte e link). Confira sempre na fonte.")

# ---------- 6. Panorama ----------
st.subheader("6. Panorama: todos os polos nos próximos 16 dias")
if st.toggle("Mostrar o panorama de todos os polos (busca a previsão de cada um)", value=False):
    linhas = []
    for r in polos.itertuples():
        pv, _ = previsao(float(r.lat), float(r.lon), r.polo)
        if pv.empty:
            continue
        hm = historico(r.polo)
        md = pv.groupby("data")[["tmin", "tmax", "chuva"]].median()
        cn, _ = normal_do_periodo(hm, md.index)
        cp = [p for p in pc.loc[pc["polo"] == r.polo, "produto"] if p in lim.index]
        al = alertas(pv, cp, lim, hm)
        fortes = al[al["k"] >= 2] if len(al) else al
        linhas.append({"Polo": f"{r.nome} — {r.uf}", "Chuva prevista (mm)": round(md["chuva"].sum()),
                       "% do normal": f"{md['chuva'].sum() / cn:.0%}" if pd.notna(cn) and cn > 0 else "—",
                       "Menor mínima (°C)": num(pv["tmin"].min(), 1), "Maior máxima (°C)": num(pv["tmax"].max(), 1),
                       "Alertas (2+ modelos)": len(fortes),
                       "Alertas raros p/ a época": int((fortes["freq"].lt(0.10)).sum()) if len(fortes) else 0})
    st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
    st.caption("Chuva muito acima do normal nos polos costuma atrasar a colheita e reduzir a oferta (preço sobe); "
               "clima bom em todos os polos ao mesmo tempo costuma aumentar a oferta (preço cai). A página Notícias × preços "
               "mostra exemplos medidos.")
st.caption("Dados de clima: Open-Meteo.com (CC BY 4.0) — modelos ECMWF IFS, NOAA GFS, DWD ICON e reanálise ERA5 (Copernicus).")
