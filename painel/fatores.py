"""Página: os fatores de mercado e de oferta explicam o preço? (mesma prova da página do clima).
Só no computador: a tabela fatores_mensal não vai para o site."""
import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import fatores_calc as F


@st.cache_data(ttl=6 * 3600, show_spinner="Rodando a prova em todos os fatores (uns 20 segundos)…")
def rodar():
    return F.testar_tudo(), F.fatores()


st.title("🧮 Fatores de mercado explicam o preço?")
st.markdown(
    "Aqui testamos se **El Niño, importação, dólar, diesel e a safra estimada pelo IBGE** antecipam o preço. "
    "É a mesma prova da página do clima: o preço **sem o efeito da época**, comparado com a média dos 3 meses "
    "anteriores, contra cada fator — com teste contra o acaso e correção para muitos testes. "
    "As combinações foram escolhidas **antes** de olhar os resultados."
)
R, T = rodar()
ok = R[R["p"].notna()]
aprovados = ok[ok["q"] < 0.10]
c1, c2, c3 = st.columns(3)
c1.metric("Combinações testadas", len(ok))
c2.metric("Deram “forte” (chance de acaso < 5%)", int((ok["p"] < 0.05).sum()),
          help=f"Por puro acaso, esperaríamos uns {0.05 * len(ok):.0f}.")
c3.metric("Aprovadas depois da correção", len(aprovados))
if aprovados.empty:
    st.warning("**Conclusão honesta:** com os dados de hoje, nenhum destes fatores antecipa o preço com segurança. "
               "Os primeiros da tabela são **sinais para acompanhar**, não previsão.")
else:
    st.success("Aprovadas mesmo depois da correção: " + "; ".join(
        f"{r.fator} → {r.produto} ({r.k} meses depois)" for r in aprovados.itertuples()))

st.subheader("Todas as combinações (as mais fortes primeiro)")
st.dataframe(
    R.sort_values("p").assign(ini=lambda d: d["ini"].astype(str), fim=lambda d: d["fim"].astype(str)).rename(columns={
        "fator": "Fator", "produto": "Preço de", "k": "Meses depois", "n": "Meses testados", "rho": "Correlação (−1 a +1)",
        "p": "Chance de acaso", "q": "Chance de acaso corrigida", "ext_media": "Preço após os 15% meses mais altos",
        "resto_media": "Preço nos outros meses", "ini": "De", "fim": "Até"}),
    hide_index=True, width="stretch",
    column_config={c: st.column_config.NumberColumn(format="%.2f") for c in
                   ("Correlação (−1 a +1)", "Chance de acaso", "Chance de acaso corrigida",
                    "Preço após os 15% meses mais altos", "Preço nos outros meses")})
st.caption("As duas colunas de preço mostram a variação contra a média dos 3 meses anteriores (0,10 = +10%).")

st.subheader("Ver uma série ao longo do tempo")
serie = st.selectbox("Série", sorted(T.columns), index=sorted(T.columns).index("ENSO_ONI") if "ENSO_ONI" in T else 0)
st.line_chart(T[serie].dropna().to_timestamp())
st.caption("Fontes: NOAA (El Niño), IBGE (IPCA e LSPA — o valor de cada mês é a estimativa da safra do ano inteiro), "
           "MDIC/Comex Stat (importação), Banco Central (dólar) e ANP (diesel). Atualize com coleta\\fatores_mercado.py.")
