"""Exporta os dados PÚBLICOS do banco para a pasta online\\ (arquivos .parquet compactados),
que é o que vai para a internet.

A planilha própria de BH (tabela planilha_bh) vai SÓ COMO DESENHO: cada preço é dividido pela média
do próprio produto (ex.: 0,82 = 18% abaixo da média). Os R$/kg do usuário não saem do computador.
As contas de época, cenários e estratégias usam só proporções, então dão o mesmo resultado; o R$
das contas vem sempre da Conab.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\exportar_online.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
BANCO = PASTA / "dados" / "precos.db"
SAIDA = PASTA / "online"
PUBLICAS = ["precos", "ceagesp", "preco_produtor", "oferta_mensal", "clima_diario", "precos_mensal"]


def planilha_so_desenho(con):
    """A série-base de cada produto da planilha (já emendada com a Conab BH, exatamente como o modelo faz
    no computador) dividida pela própria média: fica só o desenho, sem R$. A emenda é feita aqui porque,
    sem meses em comum com a Conab (caso da cebola, que termina em 2021), não dá para emendar um desenho
    com preços em R$ lá no site."""
    import sys
    sys.path.insert(0, str(PASTA / "painel"))
    import modelo as M  # modo local: usa o banco completo deste computador
    _, mensal, _, pl, _, _ = M.carregar()
    partes = []
    for (prod, ceasa), _g in pl.groupby(["produto", "ceasa"]):
        mod = M.modelo_produto(mensal, pl, prod)
        s = list(mod["series"].values())[0].dropna()
        partes.append(pd.DataFrame({"produto": prod, "mes": [p.strftime("%Y-%m") for p in s.index],
                                    "preco": (s / s.mean()).round(5).values, "ceasa": ceasa}))
    out = pd.concat(partes, ignore_index=True)
    out["unidade"] = "INDICE"
    out["fonte"] = "Planilha de produtor (CeasaMinas BH) emendada com a Conab BH, só o desenho: preço ÷ média, sem R$"
    out["relativo"] = 1
    return out


def main():
    SAIDA.mkdir(exist_ok=True)
    with sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True) as con:
        existe = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        total = 0
        tabelas = {t: (lambda t=t: pd.read_sql(f"SELECT * FROM {t}", con)) for t in PUBLICAS}
        tabelas["planilha_bh"] = lambda: planilha_so_desenho(con)
        # commodities e artigos (dados públicos: Cepea, Banco Mundial, ANP, Banco Central, OpenAlex, Embrapa)
        tabelas["agro_mensal"] = lambda: pd.read_sql("SELECT * FROM agro_mensal", con)
        tabelas["agro_diario"] = lambda: pd.read_sql("SELECT * FROM agro_diario WHERE data >= date('now', '-400 days')", con)
        tabelas["artigos"] = lambda: pd.read_sql("SELECT * FROM artigos", con)
        # só as previsões dos últimos 3 dias (a página mostra a mais nova)
        tabelas["previsao_log"] = lambda: pd.read_sql(
            "SELECT * FROM previsao_log WHERE coletado_em >= date((SELECT MAX(coletado_em) FROM previsao_log), '-2 days')", con)
        for t, ler in tabelas.items():
            if t not in existe:
                print(f"{t}: não existe no banco, pulei")
                continue
            df = ler()
            arq = SAIDA / f"{t}.parquet"
            df.to_parquet(arq, compression="zstd", index=False)
            total += arq.stat().st_size
            print(f"{t}: {len(df):,} linhas -> {arq.name} ({arq.stat().st_size / 2**20:.1f} MB)")
    print(f"Total: {total / 2**20:.1f} MB em {SAIDA}")


if __name__ == "__main__":
    main()
