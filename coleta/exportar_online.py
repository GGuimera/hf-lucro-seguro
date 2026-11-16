"""Exporta os dados PÚBLICOS do banco para a pasta online\\ (arquivos .parquet compactados),
que é o que vai para a internet.

A planilha própria de BH (tabela planilha_bh) vai com os valores reais em R$/kg, como está no banco.

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


def main():
    SAIDA.mkdir(exist_ok=True)
    with sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True) as con:
        existe = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        total = 0
        tabelas = {t: (lambda t=t: pd.read_sql(f"SELECT * FROM {t}", con)) for t in PUBLICAS}
        tabelas["planilha_bh"] = lambda: pd.read_sql("SELECT * FROM planilha_bh", con)
        # commodities e artigos (dados públicos: Cepea, Banco Mundial, ANP, Banco Central, OpenAlex, Embrapa)
        tabelas["agro_mensal"] = lambda: pd.read_sql("SELECT * FROM agro_mensal", con)
        tabelas["agro_diario"] = lambda: pd.read_sql("SELECT * FROM agro_diario WHERE data >= date('now', '-400 days')", con)
        tabelas["artigos"] = lambda: pd.read_sql("SELECT * FROM artigos", con)
        tabelas["fatores_mensal"] = lambda: pd.read_sql("SELECT * FROM fatores_mensal", con)
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
