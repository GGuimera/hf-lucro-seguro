"""Exporta os dados PÚBLICOS do banco para a pasta online\\ (arquivos .parquet compactados),
que é o que vai para a internet. A planilha própria de BH (tabela planilha_bh) NÃO entra.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\exportar_online.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
BANCO = PASTA / "dados" / "precos.db"
SAIDA = PASTA / "online"
PUBLICAS = ["precos", "ceagesp", "preco_produtor", "oferta_mensal", "clima_diario"]  # planilha_bh fica de fora (dado do usuário)


def main():
    SAIDA.mkdir(exist_ok=True)
    with sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True) as con:
        existe = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        total = 0
        for t in PUBLICAS:
            if t not in existe:
                print(f"{t}: não existe no banco, pulei")
                continue
            df = pd.read_sql(f"SELECT * FROM {t}", con)
            arq = SAIDA / f"{t}.parquet"
            df.to_parquet(arq, compression="zstd", index=False)
            total += arq.stat().st_size
            print(f"{t}: {len(df):,} linhas -> {arq.name} ({arq.stat().st_size / 2**20:.1f} MB)")
    print(f"Total: {total / 2**20:.1f} MB em {SAIDA}")


if __name__ == "__main__":
    main()
