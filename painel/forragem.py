"""Page: hydroponic fodder viability (grains, simulation, parts, costs and return, risks, report). UI text is pt-BR."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import agro_calc as A
import forragem_calc as F
import modelo as M
import regiao as RG
from modelo import MESES, brl

FUNDO, TEXTO, TEXTO_2, GRADE = "#1a1a19", "#f0efec", "#c3c2b7", "#2e2e2b"
AZUL, LARANJA, VERDE, CINZA = "#3987e5", "#d95926", "#199e70", "#6b6a63"

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


def cartao(rotulo, valor, detalhe="", cor=None):
    estilo = f' style="color:{cor}"' if cor else ""
    st.markdown(f'<div class="cartao"><div class="rotulo">{rotulo}</div><div class="valor"{estilo}>{valor}</div>'
                f'<div class="detalhe">{detalhe}</div></div>', unsafe_allow_html=True)


def visual(fig, titulo_y, altura=360, sufixo="", prefixo=""):
    fig.update_layout(paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, font=dict(color=TEXTO, size=13), height=altura,
                      margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=1.12, x=0, font=dict(color=TEXTO_2)),
                      hoverlabel=dict(bgcolor="#262624", font_color=TEXTO))
    fig.update_xaxes(showgrid=False, linecolor=GRADE, tickfont=dict(color=TEXTO_2))
    fig.update_yaxes(gridcolor=GRADE, zeroline=False, tickfont=dict(color=TEXTO_2), ticksuffix=sufixo,
                     tickprefix=prefixo, title=dict(text=titulo_y, font=dict(color=TEXTO_2)))
    return fig


def num(v, casas=1):
    if v is None or pd.isna(v):
        return "—"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def meses_txt(n):
    return "não se paga no período" if n is None or pd.isna(n) else f"{num(n, 0)} meses"


@st.cache_data(ttl=3600, show_spinner=False)
def dados():
    return A.carregar()


@st.cache_data(ttl=6 * 3600, show_spinner="Buscando notícias recentes…")
def noticias(nome):
    return F.news(nome)


@st.cache_data(ttl=3600, show_spinner=False)
def clima(polo):
    return F.climate_fit(polo)


lista, mensal, _, _ = dados()
R = F.load_reference()
G, AN, FE, PARTS, Q = R["grains"], R["animals"], R["feeds"], R["parts"], R["quality"]
ipca, ult_ipca = A.ipca_fator(mensal)
precos = {g: F.grain_price(r, mensal, lista) for g, r in G.iterrows()}
leite = mensal[mensal["produto"] == "LEITE"].sort_values("mes").iloc[-1]
leite_ref, leite_mes_ref = float(leite["valor"]), f"{leite['mes']} (R$ {leite['valor']:.2f}/L)"

st.title("🌾 Forragem hidropônica: vale a pena?")
st.markdown(
    "Simule um negócio de **forragem verde hidropônica** (grão que brota em bandejas e vira alimento verde em 8 a 14 dias): "
    "**quanto rende cada grão**, **quanto custa montar e manter**, **em quanto tempo se paga** e **quais os riscos**, "
    "com os preços de grãos, o clima e as notícias do Preço Seguro."
)
st.markdown('<div class="aviso">Estimativa para estudo. Os números de rendimento e nutrição são referências técnicas '
            "e variam com a semente e o manejo. Preços de peças são estimativas: "
            "confirme orçamentos antes de investir e ajuste a dieta com um nutricionista.</div>", unsafe_allow_html=True)

# ---------- inputs used by every tab ----------
st.subheader("Seu cenário")
c1, c2, c3, c4 = st.columns(4)
grao = c1.selectbox("Grão", G.index, format_func=lambda g: G.loc[g, "name"])
animal = c2.selectbox("Animal", AN.index, format_func=lambda a: AN.loc[a, "name"])
cabecas = c3.number_input("Número de animais", 1, 5000, 20)
lim = int(AN.loc[animal, "max_fodder_pct_dm"])
dieta = c4.slider("Parte da dieta (matéria seca) em forragem", 5, lim, min(20, lim), format="%d%%",
                  help=f"Máximo recomendado para {AN.loc[animal, 'name'].lower()}: {lim}% da matéria seca.")
c1, c2, c3, c4 = st.columns(4)
reg = F.regions()
polo = c1.selectbox("Região (clima)", reg.index, index=list(reg.index).index(RG.atual()),
                    format_func=lambda p: f"{reg.loc[p, 'nome']} ({reg.loc[p, 'uf']})")
nivel = c2.radio("Nível do sistema", list(F.TIERS), format_func=F.TIERS.get, horizontal=True, index=0)
sobra = c3.number_input("Forragem extra para vender (kg/dia)", 0.0, 10000.0, 0.0, step=10.0)
preco_venda = c4.number_input("Preço de venda (R$/kg)", 0.0, 5.0, 0.70, step=0.05,
                              help="Referência: forragem hidropônica de milho anunciada a R$ 0,70/kg (nov/2026).")

preco_sem, fonte_sem, ref_sem = precos[grao]
with st.expander("Custos e premissas (pode mudar)"):
    c1, c2, c3, c4 = st.columns(4)
    desc = c1.number_input("Desconto na semente (%)", 0, 60, 20, step=5,
                           help="Você compra os grãos até 20% mais barato que na cooperativa.")
    preco_sem = c2.number_input(f"Semente de {G.loc[grao, 'name'].lower()} (R$/kg)", 0.0, 20.0,
                                round(preco_sem * (1 - desc / 100), 2), step=0.05,
                                help="Preço de referência, já com o desconto acima.")
    tarifa = c3.number_input("Energia (R$/kWh)", 0.0, 3.0, 0.85, step=0.05,
                             help="Média residencial prevista para dez/2026: R$ 0,851/kWh. Veja a conta da sua distribuidora.")
    agua_m3 = c4.number_input("Água (R$/m³)", 0.0, 50.0, 0.0, step=1.0, help="0 se a água é de poço próprio.")
    c1, c2, c3, c4 = st.columns(4)
    nutrientes = c1.number_input("Solução nutritiva (R$/mês)", 0.0, 5000.0, 0.0, step=10.0,
                                 help="Opcional. Kit para 1.000 L de água: R$ 66,40 (nov/2026).")
    taxa = c2.number_input("Juros de comparação (% ao ano)", 0.0, 40.0, 12.0, step=0.5) / 100
    horizonte = c3.selectbox("Horizonte (meses)", [12, 24, 36, 48, 60], index=2)
    alim_ref = c4.selectbox("A forragem substitui", FE.index, format_func=lambda f: FE.loc[f, "name"],
                            help="Alimento que deixa de ser comprado. A economia é calculada pela matéria seca.")
    c1, c2, c3, c4 = st.columns(4)
    salario = c1.number_input("Mão de obra (R$/hora)", 0.0, 100.0, 12.0, step=1.0,
                              help="0 se o trabalho é da família e você não quer contar.")
    benf = c2.number_input("Benfeitorias já existentes (%)", 0, 100, 0, step=10,
                           help="Quanto da sala, da caixa d'água e do molho já existe na fazenda. Estimativa sua.")
    leite_on = c3.checkbox("Contar ganho de leite (teste com vacas)", True)
    ganho = c4.number_input("Ganho de leite por vaca (L/dia)", 0.0, 10.0, 3.0, step=0.5, disabled=not leite_on)
    c1, c2, c3, c4 = st.columns(4)
    preco_leite = c1.number_input("Preço do leite (R$/L)", 0.0, 10.0, round(leite_ref, 2), step=0.05, disabled=not leite_on,
                                  help=f"Média Brasil, último mês disponível: {leite_mes_ref}.")
    modelo = c2.radio("Modelo de negócio", ["Só na minha fazenda", "Vender o sistema", "Alugar o sistema"],
                      help="Venda: recebe o preço de cada sistema vendido. Aluguel: recebe por mês, depois de instalado.")
    clientes = c3.number_input("Clientes por ano", 0, 500, 0, disabled=modelo == "Só na minha fazenda")
    valor_neg = c4.number_input("Preço de venda (R$) ou aluguel (R$/mês)", 0.0, 10000000.0, 0.0, step=500.0,
                                disabled=modelo == "Só na minha fazenda",
                                help="Cada sistema vendido ou alugado custa o mesmo que o seu (investimento acima).")

abas = st.tabs(["🌾 Grãos e nutrição", "🧮 Simulação", "🔧 Sistema (peças)", "💰 Custos e retorno", "⚠️ Riscos",
                "📄 Relatório e comparação"])

# ---------- choices that feed the calculation (parts and good practices) ----------
with abas[2]:
    st.markdown("Marque as peças que vai usar. O nível escolhido em cima já traz uma seleção pronta; "
                "**preços podem ser editados** (clique na célula).")
    cat = PARTS.copy()
    cat["use"] = cat["item"].isin(F.preset(PARTS, nivel))
    cat["tier_name"] = cat["tier"].map(F.TIERS)
    ed = st.data_editor(
        cat[["use", "name", "tier_name", "price", "price_date"]], key=f"pecas_{nivel}", hide_index=True,
        width="stretch", disabled=["name", "tier_name", "price_date"],
        column_config={"use": st.column_config.CheckboxColumn("Usar"), "name": "Peça", "tier_name": "Nível",
                       "price": st.column_config.NumberColumn("Preço (R$)", format="%.2f", min_value=0.0),
                       "price_date": "Data do preço"})
    escolhidas = cat.loc[ed["use"].values, "item"].tolist()
    PARTS = PARTS.assign(price=ed["price"].values)

    st.subheader("Outros materiais (você digita)")
    st.markdown('<p class="dica">Coloque o que não está na lista: material, quantidade e preço aproximado. '
                "Use a linha em branco no fim da tabela para adicionar.</p>", unsafe_allow_html=True)
    extra = st.data_editor(
        pd.DataFrame(columns=["Material", "Quantidade", "Preço unitário (R$)", "Vida útil (anos)"]).astype(
            {"Quantidade": float, "Preço unitário (R$)": float, "Vida útil (anos)": float}),
        num_rows="dynamic", key="materiais_extras", hide_index=True, width="stretch",
        column_config={"Preço unitário (R$)": st.column_config.NumberColumn(format="%.2f", min_value=0.0),
                       "Quantidade": st.column_config.NumberColumn(min_value=0.0, step=1.0)})
    extra = extra.dropna(subset=["Material"])
    extras_total = float((extra["Quantidade"].fillna(0) * extra["Preço unitário (R$)"].fillna(0)).sum())
    extras_depr_mes = float((extra["Quantidade"].fillna(0) * extra["Preço unitário (R$)"].fillna(0)
                             / extra["Vida útil (anos)"].fillna(5).replace(0, 5)).sum()) / 12
    st.markdown(f'<p class="dica">Total dos materiais digitados: <b>{brl(extras_total, 0)}</b>.</p>', unsafe_allow_html=True)

with abas[4]:
    st.subheader("Boas práticas contra mofo e perdas")
    st.markdown('<p class="dica">Desmarque o que você <b>não</b> vai conseguir seguir: cada item desmarcado reduz o rendimento.</p>',
                unsafe_allow_html=True)
    perda_q = 0.0
    cols = st.columns(2)
    for i, (_, q) in enumerate(Q.iterrows()):
        if not cols[i % 2].checkbox(f"{q['name']} (−{q['loss_pct']}% se faltar)", True, help=q["tip"], key=f"q_{q['check']}"):
            perda_q += q["loss_pct"]

# ---------- calculation ----------
g, an = G.loc[grao], AN.loc[animal]
por_mes_clima, quente, frio = clima(polo)
q_exp, f_exp, perda_c = F.climate_exposure(quente, frio, escolhidas) if pd.notna(quente) else (0.0, 0.0, 0.0)
perda = F.total_loss(perda_q, perda_c)
tam = F.size_system(g, an, cabecas, dieta, sobra, perda)
conta = F.bill(PARTS, escolhidas, tam, ipca, benf)
capex = conta["total"].sum() + extras_total
rec = F.resources(tam, conta["kwh_total"].sum())
custos = F.monthly_costs(tam, rec, preco_sem, tarifa, agua_m3, salario, nutrientes)
opex = sum(custos.values())
depr_mes = conta["depr_year"].sum() / 12 + extras_depr_mes
fe = FE.assign(price_kg=[F.feed_price(r, mensal, lista) for _, r in FE.iterrows()])
custo_ref_ms = fe.loc[alim_ref, "price_kg"] / (fe.loc[alim_ref, "dm_pct"] / 100)
economia = 30 * tam["fed_dm_kg"] * custo_ref_ms
vendas = 30 * sobra * preco_venda
leite_mes = F.milk_income_month(cabecas, ganho, preco_leite) if leite_on else 0.0
vendas_mes = vendas + leite_mes
receita = vendas_mes + F.business_flows(modelo, clientes, valor_neg, capex, horizonte)
fluxo = F.cashflow(capex, opex, economia, receita, horizonte, taxa, ramp_days=int(g["cycle_days"]) + 1)
empate = F.break_even_seed_price(custos, economia, vendas_mes, tam["seed_kg"])
custo_fvh_kg = (opex + depr_mes) / (30 * tam["produced_kg"])
proxy = F.series_brl_kg(mensal, lista, g["risk_proxy"])
segue = fe.loc[alim_ref, "price_code"] == g["risk_proxy"]
mc = F.price_scenarios(proxy, custos, economia, receita, capex, segue, horizonte, taxa, int(g["cycle_days"]) + 1)
vol = F.volatility_year(proxy)
melhores, idx_mes = F.best_buy_months(proxy)
hoje = date.today().month
pos_epoca = (idx_mes.get(hoje, idx_mes.mean()) - idx_mes.min()) / (idx_mes.max() - idx_mes.min())
oni = F.latest_oni()
nt = noticias(g["name"])
n_risco = int(((nt["type"] != "mercado") | nt["up"]).sum()) if not nt.empty else 0
risco, partes = F.risk_score(vol, pos_epoca, n_risco, oni[1] if oni else None, perda_c, perda_q, fluxo["payback"])
NOMES_CUSTO = {"seed": "Semente", "energy": "Energia", "water": "Água", "labor": "Mão de obra", "nutrients": "Solução nutritiva"}
NOMES_RISCO = {"price": "Variação do preço do grão", "season": "Época do ano (preço agora)", "news": "Notícias de risco",
               "enso": "El Niño / La Niña", "climate": "Clima da região", "quality": "Boas práticas faltando",
               "finance": "Tempo para se pagar"}

# ---------- 1. grains and nutrition ----------
with abas[0]:
    tg = F.grain_table(G, {k: v[0] for k, v in precos.items()})
    st.subheader("Quanto rende cada grão")
    mostra = pd.DataFrame({
        "Grão": tg["name"], "Ciclo (dias)": tg["cycle_days"], "kg verde por kg de semente": tg["fresh_kg_per_kg_seed"],
        "kg de matéria seca por kg de semente": tg["dm_kg_per_kg_seed"].round(2),
        "Perda de matéria seca no broto": tg["dm_loss_pct"].round(0).astype(int).astype(str) + "%",
        "kg verde por m² por ano": tg["fresh_kg_m2_year"].round(0).astype(int),
        "Semente (R$/kg)": tg["seed_brl_kg"].map(lambda v: brl(v)),
        "Só a semente: R$ por kg de matéria seca": tg["seed_brl_per_kg_dm"].map(lambda v: brl(v)),
    })
    st.dataframe(mostra, hide_index=True, width="stretch")
    st.markdown('<p class="dica">O broto ganha água e peso verde, mas <b>perde matéria seca</b> (gasta energia do grão para crescer). '
                "Por isso o kg de matéria seca da forragem sai mais caro que o do próprio grão: o ganho está na "
                "<b>digestibilidade, no alimento verde na seca e no pouco espaço usado</b>.</p>", unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_bar(x=tg["name"], y=tg["seed_brl_per_kg_dm"], marker_color=AZUL, name="Semente por kg de MS",
                text=[brl(v) for v in tg["seed_brl_per_kg_dm"]], textposition="outside")
    st.plotly_chart(visual(fig, "R$ por kg de matéria seca (só semente)", 320, prefixo="R$ "), width="stretch")

    st.subheader("Nutrição")
    st.dataframe(pd.DataFrame({"Grão": G["name"], "Matéria seca": G["dm_pct"].astype(str) + "%",
                               "Proteína bruta (na MS)": G["cp_pct"].astype(str) + "%",
                               "Energia (NDT)": G["tdn_pct"].astype(str) + "%", "Fibra (FDN)": G["ndf_pct"].astype(str) + "%",
                               "Benefícios": G["benefits"], "Cuidados": G["cautions"]}),
                 hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        cartao(f"Para {an['name'].lower()}: benefícios", "", an["benefits"])
    with c2:
        cartao(f"Para {an['name'].lower()}: cuidados", "", an["cautions"])
    pb_dieta = g["cp_pct"]
    st.markdown(f'<p class="dica">{g["name"]} tem {num(pb_dieta)}% de proteína na matéria seca; '
                f'{an["name"].lower()} precisa de cerca de {num(an["cp_need_pct"], 0)}% na dieta total.</p>', unsafe_allow_html=True)

# ---------- 2. simulation ----------
with abas[1]:
    st.subheader(f"{cabecas} × {an['name'].lower()} com {dieta}% da dieta em forragem de {g['name'].lower()}")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        cartao("Forragem por dia", f"{num(tam['produced_kg'], 0)} kg", f"{num(tam['fed_fresh_kg'], 0)} kg para os animais"
               + (f" + {num(sobra, 0)} kg para vender" if sobra else ""))
    with c2:
        cartao("Semente por dia", f"{num(tam['seed_kg'], 1)} kg", f"{num(tam['seed_kg'] * 30 / 60, 1)} sacas de 60 kg por mês")
    with c3:
        cartao("Bandejas", f"{tam['trays_day']} por dia", f"{tam['trays']} em produção ({int(g['cycle_days'])} dias de ciclo)")
    with c4:
        cartao("Espaço", f"{num(tam['area_m2'], 0)} m²", f"{tam['racks']} estantes de 5 prateleiras")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        cartao("Água", f"{num(rec['water_l'], 0)} L/dia", "rega + molho da semente")
    with c2:
        cartao("Energia", f"{num(rec['kwh'], 1)} kWh/dia", "pelas peças escolhidas")
    with c3:
        cartao("Trabalho", f"{num(rec['labor_h'], 1)} h/dia", "molho, plantio, colheita e limpeza")
    with c4:
        cartao("Perda prevista", f"{num(perda, 0)}%", f"boas práticas {num(perda_q, 0)}% · clima {num(perda_c, 0)}%",
               LARANJA if perda > 15 else None)
    st.markdown(f'<p class="dica">Matéria seca entregue aos animais: <b>{num(tam["fed_dm_kg"], 1)} kg/dia</b>. '
                "A semente já foi aumentada para cobrir a perda prevista.</p>", unsafe_allow_html=True)
    st.subheader("Calendário de início")
    cal = F.schedule(int(g["cycle_days"]), tam).rename(columns={
        "day": "Dia", "soak_seed_kg": "Molho (kg de semente)", "sow_trays": "Plantio (bandejas)",
        "harvest_trays": "Colheita (bandejas)", "harvest_kg": "Colheita (kg)"})
    st.dataframe(cal.round(1), hide_index=True, width="stretch", height=300)
    st.markdown(f'<p class="dica">A primeira colheita sai no dia {int(g["cycle_days"]) + 2}. Depois, todo dia se repete: '
                "um lote vai para o molho, o do dia anterior vai para a bandeja e o mais antigo é colhido.</p>",
                unsafe_allow_html=True)

# ---------- 3. parts (bill) ----------
with abas[2]:
    st.subheader("Lista de compras para o seu tamanho")
    c1, c2, c3 = st.columns(3)
    with c1:
        cartao("Investimento", brl(capex, 0), f"{len(conta)} itens · preços antigos corrigidos pelo IPCA (até {ult_ipca})")
    with c2:
        cartao("Energia das peças", f"{num(rec['kwh'], 1)} kWh/dia", brl(custos["energy"], 0) + " por mês")
    with c3:
        cartao("Desgaste (depreciação)", brl(depr_mes, 0) + "/mês", "valor para trocar as peças no fim da vida útil")
    st.dataframe(conta.rename(columns={"name": "Peça", "qty": "Qtd.", "price": "Preço (R$)", "total": "Total (R$)",
                                       "life_years": "Vida útil (anos)"})[["Peça", "Qtd.", "Preço (R$)", "Total (R$)",
                                                                          "Vida útil (anos)"]].round(2),
                 hide_index=True, width="stretch")

# ---------- 4. costs and return ----------
with abas[3]:
    negocio_mes = float(np.mean(receita - vendas_mes))
    lucro = economia + vendas_mes + negocio_mes - opex
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        cartao("Custo por mês", brl(opex, 0), " · ".join(f"{NOMES_CUSTO[k]} {brl(v, 0)}" for k, v in custos.items() if v))
    with c2:
        cartao("Economia por mês", brl(economia, 0), f"deixa de comprar {num(tam['fed_dm_kg'] * 30, 0)} kg de MS de "
               f"{fe.loc[alim_ref, 'name'].lower()}" + (f" + vendas {brl(vendas, 0)}" if vendas else "")
               + (f" + leite {brl(leite_mes, 0)}" if leite_mes else ""))
    with c3:
        cartao("Resultado por mês", brl(lucro, 0), "economia + vendas − custos", VERDE if lucro > 0 else LARANJA)
    with c4:
        cartao("Tempo para se pagar", meses_txt(fluxo["payback"]), f"investimento de {brl(capex, 0)}",
               VERDE if fluxo["payback"] is not None else LARANJA)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        cartao(f"Valor presente ({horizonte} meses)", brl(fluxo["npv"], 0), f"descontado a {num(taxa * 100)}% ao ano",
               VERDE if fluxo["npv"] > 0 else LARANJA)
    with c2:
        cartao("Retorno ao ano (TIR)", "—" if fluxo["irr_year"] is None else f"{num(fluxo['irr_year'] * 100, 0)}%",
               "comparar com os juros de comparação")
    with c3:
        if empate > 0:
            cartao("Preço da semente de empate", brl(empate), f"hoje: {brl(preco_sem)}/kg",
                   VERDE if empate > preco_sem else LARANJA)
        else:
            cartao("Preço da semente de empate", "não existe", "os outros custos já passam da economia, "
                   "mesmo com semente de graça", LARANJA)
    with c4:
        cartao("Custo da forragem", brl(custo_fvh_kg) + "/kg verde", "com desgaste das peças")

    fig = go.Figure()
    fig.add_scatter(x=list(range(horizonte + 1)), y=fluxo["cum"], mode="lines", line=dict(color=AZUL, width=3),
                    name="Saldo acumulado")
    fig.add_hline(y=0, line_color=CINZA, line_dash="dot")
    st.plotly_chart(visual(fig, "Saldo acumulado (R$)", 320, prefixo="R$ "), width="stretch")

    st.subheader("Comparação com outros alimentos")
    comp = F.feed_comparison(fe, f"Forragem de {g['name'].lower()} (sua)", custo_fvh_kg, g["dm_pct"], g["cp_pct"])
    comp = comp.sort_values("brl_kg_dm")
    fig = go.Figure()
    fig.add_bar(y=comp["name"], x=comp["brl_kg_dm"], orientation="h", name="R$/kg de matéria seca",
                marker_color=[VERDE if i == "FODDER" else CINZA for i in comp.index],
                text=[brl(v) for v in comp["brl_kg_dm"]], textposition="outside")
    fig.update_layout(hovermode="y unified")
    st.plotly_chart(visual(fig, "", 300), width="stretch")
    st.dataframe(pd.DataFrame({"Alimento": comp["name"], "Preço (R$/kg como compra)": comp["price_kg"].map(brl),
                               "Matéria seca": comp["dm_pct"].map(lambda v: f"{num(v, 0)}%"),
                               "R$ por kg de MS": comp["brl_kg_dm"].map(brl),
                               "R$ por kg de proteína": comp["brl_kg_cp"].map(brl)}),
                 hide_index=True, width="stretch")

    st.subheader("Cenários de preço da semente")
    st.markdown(f'<p class="dica">2.000 simulações sorteando as variações mensais reais do preço de '
                f'{lista.set_index("produto").loc[g["risk_proxy"], "nome"].lower()} nos últimos 10 anos (corrigido pela inflação).'
                + (" O alimento substituído segue o mesmo preço, então a economia sobe e desce junto." if segue else "")
                + "</p>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    v, p = mc["npv"], mc["payback"]
    with c1:
        cartao("Valor presente — cenário ruim", brl(v["p10"], 0), "1 em cada 10 simulações fica abaixo")
    with c2:
        cartao("Valor presente — cenário médio", brl(v["p50"], 0))
    with c3:
        cartao("Valor presente — cenário bom", brl(v["p90"], 0), "1 em cada 10 simulações fica acima")
    with c4:
        cartao("Chance de prejuízo", f"{num(mc['loss_pct'], 0)}%", f"não se paga em {num(mc['never_pays_pct'], 0)}% dos casos",
               LARANJA if mc["loss_pct"] > 30 else VERDE)
    fan = mc["seed_cost_fan"]
    fig = go.Figure()
    fig.add_scatter(x=fan.index, y=fan["p90"], line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=fan.index, y=fan["p10"], fill="tonexty", fillcolor="rgba(57,135,229,0.25)", line=dict(width=0),
                    name="80% das simulações")
    fig.add_scatter(x=fan.index, y=fan["p50"], line=dict(color=AZUL, width=3), name="Mediana")
    st.plotly_chart(visual(fig, "Gasto com semente por mês (R$)", 300, prefixo="R$ "), width="stretch")

# ---------- 5. risks ----------
with abas[4]:
    cor = VERDE if risco < 35 else LARANJA if risco < 65 else "#e05252"
    st.subheader("Nota de risco")
    c1, c2 = st.columns([1, 2])
    with c1:
        cartao("Risco geral (0 a 100)", num(risco, 0), "quanto maior, mais arriscado", cor)
    with c2:
        fig = go.Figure()
        fig.add_bar(y=[NOMES_RISCO[k] for k in partes], x=list(partes.values()), orientation="h", marker_color=AZUL,
                    text=[num(x, 0) for x in partes.values()], textposition="outside")
        fig.update_xaxes(range=[0, 115])
        fig.update_layout(hovermode="y unified")
        st.plotly_chart(visual(fig, "", 280), width="stretch")

    st.subheader("Preço da semente")
    s5 = proxy.tail(60)
    fig = go.Figure()
    fig.add_scatter(x=s5.index.to_timestamp(), y=s5.values, line=dict(color=AZUL, width=2.5),
                    name=lista.set_index("produto").loc[g["risk_proxy"], "nome"])
    st.plotly_chart(visual(fig, "R$/kg (corrigido pela inflação)", 300, prefixo="R$ "), width="stretch")
    st.markdown(f'<p class="dica">Variação típica do preço: <b>{num(vol * 100, 0)}% ao ano</b>. '
                f'Meses em que o grão costuma estar mais barato: <b>{", ".join(MESES[m - 1] for m in melhores)}</b> '
                "— uma boa época para fazer estoque de semente.</p>", unsafe_allow_html=True)
    if not isinstance(g["price_code"], str):
        st.markdown(f'<p class="dica">Não há série pública atualizada de {g["name"].lower()}: o risco usa o preço de '
                    f'{lista.set_index("produto").loc[g["risk_proxy"], "nome"].lower()} como referência.</p>',
                    unsafe_allow_html=True)

    st.subheader("Clima da região")
    if por_mes_clima.empty:
        st.info("Sem dados de clima para esta região.")
    else:
        fig = go.Figure()
        fig.add_bar(x=MESES, y=por_mes_clima["hot"] * 100, name=f"Dias acima de {num(F.HOT_C, 0)} °C", marker_color=LARANJA)
        fig.add_bar(x=MESES, y=por_mes_clima["cold"] * 100, name=f"Noites abaixo de {num(F.COLD_C, 0)} °C", marker_color=AZUL)
        st.plotly_chart(visual(fig, "% dos dias (últimos 5 anos)", 300, sufixo="%"), width="stretch")
        dica = ("O ar-condicionado escolhido protege a sala." if "AR_COND" in escolhidas else
                "Considere o nível avançado (ar-condicionado) ou ao menos exaustor e isolamento." if perda_c > 3 else
                "O clima da região dá pouca perda com as peças escolhidas.")
        st.markdown(f'<p class="dica">{num(quente * 100, 0)}% dos dias passam de {num(F.HOT_C, 0)} °C e '
                    f'{num(frio * 100, 0)}% das noites ficam abaixo de {num(F.COLD_C, 0)} °C. Perda estimada pelo clima: '
                    f'<b>{num(perda_c, 0)}%</b>. {dica} (Os dados não têm umidade do ar.)</p>', unsafe_allow_html=True)
    if oni:
        fase = "El Niño" if oni[1] >= 0.5 else "La Niña" if oni[1] <= -0.5 else "neutro"
        st.markdown(f'<p class="dica">Oceano Pacífico (índice ONI) em {oni[0]}: <b>{num(oni[1])}</b> — {fase}. '
                    "Fases fortes mexem com chuva, safra e preço dos grãos.</p>", unsafe_allow_html=True)
    al = F.weather_alerts(polo)
    if not al.empty:
        st.markdown("**Alertas de clima recentes para a região**")
        for _, r in al.iterrows():
            st.markdown(f"- {r['data']} · [{r['titulo']}]({r['url']}) ")

    st.subheader("Notícias recentes (últimos 2 dias)")
    if nt.empty:
        st.info("Não foi possível buscar notícias agora (sem internet?).")
    else:
        TIPO_TXT = {"frio": "❄️ frio", "chuva": "🌧️ chuva", "calor": "🔥 calor/seca", "geopolitica": "🌎 mercado externo",
                    "logistica": "🚚 logística", "mercado": "📈 mercado"}
        for _, r in nt.head(15).iterrows():
            st.markdown(f"- {r['date']} · {TIPO_TXT.get(r['type'], r['type'])}{' · ⬆️ alta' if r['up'] else ''} · "
                        f"[{r['title']}]({r['url']})")
        st.markdown(f'<p class="dica">{n_risco} notícias de risco (clima, mercado externo, logística ou alta de preço) '
                    "entram na nota.</p>", unsafe_allow_html=True)

# ---------- 6. report and comparison ----------
resumo = {
    "nome": "", "grao": g["name"], "animal": an["name"], "cabecas": int(cabecas), "dieta_pct": int(dieta),
    "regiao": reg.loc[polo, "nome"], "nivel": F.TIERS[nivel], "forragem_kg_dia": round(tam["produced_kg"], 1),
    "semente_kg_dia": round(tam["seed_kg"], 1), "area_m2": round(tam["area_m2"], 1), "investimento": round(capex, 2),
    "custo_mes": round(opex, 2), "economia_mes": round(economia, 2), "vendas_mes": round(vendas_mes, 2), "leite_mes": round(leite_mes, 2), "modelo": modelo,
    "payback_meses": fluxo["payback"], "vpl": round(fluxo["npv"], 2), "vpl_ruim": round(v["p10"], 2),
    "chance_prejuizo_pct": round(mc["loss_pct"], 1), "risco": round(risco, 1), "perda_pct": round(perda, 1),
    "custo_forragem_kg": round(custo_fvh_kg, 3),
}
ROTULOS = {"grao": "Grão", "animal": "Animal", "cabecas": "Animais", "dieta_pct": "Dieta em forragem (%)",
           "regiao": "Região", "nivel": "Nível", "forragem_kg_dia": "Forragem (kg/dia)", "semente_kg_dia": "Semente (kg/dia)",
           "area_m2": "Área (m²)", "investimento": "Investimento (R$)", "custo_mes": "Custo/mês (R$)",
           "economia_mes": "Economia/mês (R$)", "vendas_mes": "Vendas/mês (R$)", "payback_meses": "Se paga em (meses)",
           "vpl": "Valor presente (R$)", "vpl_ruim": "Valor presente, cenário ruim (R$)",
           "chance_prejuizo_pct": "Chance de prejuízo (%)", "risco": "Risco (0-100)", "perda_pct": "Perda prevista (%)",
           "custo_forragem_kg": "Custo da forragem (R$/kg)", "modelo": "Modelo de negócio",
           "leite_mes": "Leite extra (R$/mês)"}

with abas[5]:
    st.subheader("Guardar esta simulação")
    c1, c2 = st.columns([3, 1])
    nome = c1.text_input("Nome", f"{g['name']} + {an['name']} ({cabecas})")
    if c2.button("💾 Guardar", width="stretch"):
        F.save_run(dict(resumo, nome=nome))
        st.success("Simulação guardada.")
    salvas = F.load_runs()
    if salvas:
        st.subheader("Comparar simulações guardadas")
        tab = pd.DataFrame(salvas).set_index("nome")
        escolha = st.multiselect("Simulações", list(tab.index), default=list(tab.index)[-3:])
        if escolha:
            st.dataframe(tab.loc[escolha, list(ROTULOS)].rename(columns=ROTULOS).T.astype(str), width="stretch")

    st.subheader("Relatório em PDF")
    secoes = [
        ("Cenário", [(ROTULOS[k], str(resumo[k])) for k in ("grao", "animal", "cabecas", "dieta_pct", "regiao", "nivel",
                                                              "modelo", "leite_mes")]),
        ("Dimensionamento", [("Forragem por dia", f"{num(tam['produced_kg'], 0)} kg"),
                             ("Semente por dia", f"{num(tam['seed_kg'], 1)} kg"),
                             ("Bandejas", f"{tam['trays_day']} por dia, {tam['trays']} em produção"),
                             ("Estantes e área", f"{tam['racks']} estantes, {num(tam['area_m2'], 0)} m²"),
                             ("Água / energia / trabalho", f"{num(rec['water_l'], 0)} L, {num(rec['kwh'], 1)} kWh, "
                                                           f"{num(rec['labor_h'], 1)} h por dia"),
                             ("Perda prevista", f"{num(perda, 0)}% (boas práticas {num(perda_q, 0)}%, clima {num(perda_c, 0)}%)")]),
        ("Investimento", [(r["name"], f"{num(r['qty'], 0)} x {brl(r['price'])} = {brl(r['total'])}") for _, r in conta.iterrows()]
         + [(r["Material"], f"{num(r['Quantidade'], 0)} x {brl(r['Preço unitário (R$)'])}") for _, r in extra.iterrows()]
         + [("Total", brl(capex))]),
        ("Custos e retorno", [(NOMES_CUSTO[k] + " (mês)", brl(v)) for k, v in custos.items()]
         + [("Economia (mês)", brl(economia)), ("Vendas (mês)", brl(vendas)), ("Leite extra (mês)", brl(leite_mes)),
            ("Tempo para se pagar", meses_txt(fluxo["payback"])),
            (f"Valor presente ({horizonte} meses)", brl(fluxo["npv"])),
            ("Preço da semente de empate", brl(empate) + "/kg" if empate > 0 else "não existe (outros custos passam da economia)"), ("Custo da forragem", brl(custo_fvh_kg) + "/kg verde")]),
        ("Cenários de preço", [("Valor presente ruim / médio / bom", f"{brl(v['p10'], 0)} / {brl(v['p50'], 0)} / {brl(v['p90'], 0)}"),
                               ("Chance de prejuízo", f"{num(mc['loss_pct'], 0)}%")]),
        ("Riscos", [("Nota geral (0 a 100)", num(risco, 0))] + [(NOMES_RISCO[k], num(x, 0)) for k, x in partes.items()]
         + [("Melhores meses para comprar semente", ", ".join(MESES[m - 1] for m in melhores))]),
        ("Avisos", [("Aviso", "Estimativa para estudo. Confirme orçamentos e ajuste a dieta com um nutricionista.")]),
    ]
    st.download_button("📄 Baixar relatório (PDF)", F.pdf_report(f"Viabilidade de forragem hidropônica: {nome}", secoes),
                       file_name=f"forragem_{grao.lower()}_{animal.lower()}.pdf", mime="application/pdf")
