"""Região escolhida na landing: um polo produtor (estado + região). Vale para todas as páginas.

Guardada na sessão e no link da página (?regiao=POLO), para a pessoa salvar o link como favorito.
"""
import pandas as pd
import streamlit as st

import modelo as M

PADRAO = "SAO_GOTARDO"
CEASA_DO_ESTADO = {"MG": "CEASAMINAS - BELO HORIZONTE", "SP": "CEAGESP - SAO PAULO", "RJ": "CEASA/RJ - RIO DE JANEIRO"}
CALENDARIO_PADRAO = "cal_planalto"  # polos sem calendário próprio usam o calendário do planalto


@st.cache_data
def polos():
    p = pd.concat([pd.read_csv(M.PASTA / "dados" / f, sep=";", usecols=["polo", "nome", "uf", "regiao_calendario"])
                   for f in ("polos.csv", "polos_agro.csv")])
    return p.drop_duplicates("polo").set_index("polo")


def atual():
    polo = st.session_state.get("polo") or st.query_params.get("regiao", PADRAO)
    return polo if polo in polos().index else PADRAO


def escolher(polo):
    st.session_state["polo"] = polo
    st.query_params["regiao"] = polo


def rotulo(polo):
    r = polos().loc[polo]
    return f"{r['nome']} — {r['uf']}"


def calendario(polo):
    c = polos().loc[polo, "regiao_calendario"]
    return c if isinstance(c, str) else CALENDARIO_PADRAO


def ceasa(polo):
    return CEASA_DO_ESTADO.get(polos().loc[polo, "uf"], M.BRASIL)
