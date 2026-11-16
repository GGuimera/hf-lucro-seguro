"""Shared look of the Preço Seguro pages: colours, info cards and chart styling."""
import streamlit as st

FUNDO, TEXTO, TEXTO_2, GRADE = "#1a1a19", "#f0efec", "#c3c2b7", "#2e2e2b"


def cartao(rotulo, valor, detalhe="", cor=None):
    estilo = f' style="color:{cor}"' if cor else ""
    st.markdown(f'<div class="cartao"><div class="rotulo">{rotulo}</div><div class="valor"{estilo}>{valor}</div>'
                f'<div class="detalhe">{detalhe}</div></div>', unsafe_allow_html=True)


def visual(fig, titulo_y, altura=360, sufixo="", prefixo="", legenda_y=1.12, categoria=False):
    eixo_x = dict(type="category") if categoria else {}
    fig.update_layout(paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, font=dict(color=TEXTO, size=13), height=altura,
                      margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=legenda_y, x=0, font=dict(color=TEXTO_2)),
                      hoverlabel=dict(bgcolor="#262624", font_color=TEXTO))
    fig.update_xaxes(showgrid=False, linecolor=GRADE, tickfont=dict(color=TEXTO_2), **eixo_x)
    fig.update_yaxes(gridcolor=GRADE, zeroline=False, tickfont=dict(color=TEXTO_2), ticksuffix=sufixo,
                     tickprefix=prefixo, title=dict(text=titulo_y, font=dict(color=TEXTO_2)))
    return fig
