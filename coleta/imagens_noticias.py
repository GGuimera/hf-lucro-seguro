"""Preenche a coluna 'imagem' de dados\\eventos.csv com a imagem de capa de cada notícia (og:image da própria página).

A imagem não é copiada: o quadro mostra o endereço da imagem da fonte e leva à notícia original.
Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\imagens_noticias.py
"""
import csv
import re
import urllib.request

from buscar_noticias import EVENTOS, registrar

PADRAO = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I)
PADRAO_INV = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I)


def imagem_da_pagina(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        pagina = r.read(300_000).decode("utf-8", "replace")
    m = PADRAO.search(pagina) or PADRAO_INV.search(pagina)
    return m.group(1).strip() if m and m.group(1).startswith("http") else ""


def main():
    with open(EVENTOS, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    campos = list(linhas[0].keys())
    if "imagem" not in campos:
        campos.append("imagem")
    achadas = 0
    for e in linhas:
        e.setdefault("imagem", "")
        if e["imagem"] or not e["url"].startswith("http"):
            continue
        try:
            e["imagem"] = imagem_da_pagina(e["url"])
        except Exception:
            continue  # a fonte bloqueou ou não respondeu: o quadro fica sem imagem
        achadas += bool(e["imagem"])
    with open(EVENTOS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    registrar(f"imagens: {achadas} novas de {len(linhas)} notícias")


if __name__ == "__main__":
    main()
