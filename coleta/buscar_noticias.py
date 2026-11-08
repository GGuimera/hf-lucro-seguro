"""Busca diária de notícias sobre preço de hortifrúti (Google Notícias) e acrescenta em dados\\eventos.csv
como 'não conferida'. Não copia o texto das notícias: guarda só o título, a fonte e o link.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\buscar_noticias.py
Agendado no Windows para rodar todo dia às 8h (tarefa "PrecoSeguro_Noticias").
"""
import csv
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent
EVENTOS = PASTA / "dados" / "eventos.csv"
LOG = PASTA / "dados" / "log_noticias.txt"
MAX_NOVAS = 6
CEAGESP_BOL = "CEAGESP - SAO PAULO (BOLETINS)"

# palavra no título -> código da cultura no sistema
CULTURAS = {
    "alho": "ALHO", "cenoura": "CENOURA", "cebola": "CEBOLA", "tomate": "TOMATE", "batata-doce": "BATATA DOCE",
    "batata doce": "BATATA DOCE", "batata": "BATATA", "alface": "ALFACE", "repolho": "REPOLHO", "beterraba": "BETERRABA",
    "abobrinha": "ABOBRINHA", "abobora": "ABOBORA", "pimentao": "PIMENTAO VERDE", "pepino": "PEPINO", "chuchu": "CHUCHU",
    "mandioquinha": "MANDIOQUINHA", "mandioca": "MANDIOCA", "inhame": "INHAME", "quiabo": "QUIABO", "jilo": "JILO",
    "berinjela": "BERINJELA", "brocolis": "BROCOLO", "couve-flor": "COUVE-FLOR", "couve": "COUVE", "vagem": "VAGEM",
    "melancia": "MELANCIA", "melao": "MELAO AMARELO", "morango": "MORANGO", "milho verde": "MILHO VERDE",
}  # "cará" fica de fora: sem acento vira "cara" (como em "mais cara") e confunde
PRECO = r"\b(preco|precos|cotac|alta|altas|queda|sobe|sobem|subiu|cai|caem|caiu|dispara|disparam|recua|recuam|despenca|encarece|barato|caro|valoriza|desvaloriza|atacado|ceasa|ceagesp|oferta|recorde|safra recorde)"
TIPOS = [  # (tipo, palavras) — a primeira que bater vence
    ("frio", r"\b(geada|geadas|frio|onda de frio|baixas temperaturas)"),
    ("chuva", r"\b(chuva|chuvas|enchente|enchentes|temporal|alagamento|granizo|excesso de umidade)"),
    ("calor", r"\b(calor|seca|estiagem|el nino|la nina|onda de calor|temperaturas altas)"),
    ("geopolitica", r"\b(guerra|importac|importad|antidumping|china|chines|argentina|tarifa|dolar|cambio|exportac|diesel|petroleo|fertilizante)"),
    ("logistica", r"\b(greve|frete|bloqueio|rodovia|transporte|caminhoneiro)"),
]
BUSCAS = [
    "alho preço", "cenoura preço", "cebola preço", "tomate preço atacado", "batata preço atacado",
    "hortaliças preço Ceasa", "hortifruti preço clima", "Ceagesp preço hortaliças", "Conab Prohort preços",
]


def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def registrar(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M} {msg}"
    print(linha)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def buscar(consulta):
    q = urllib.parse.quote(f"{consulta} when:2d")
    url = f"https://news.google.com/rss/search?q={q}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    req = urllib.request.Request(url, headers={"User-Agent": "PrecoSeguro-noticias/0.1"})
    with urllib.request.urlopen(req, timeout=40) as r:
        raiz = ET.fromstring(r.read())
    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        fonte = (item.findtext("source") or "").strip()
        if fonte and titulo.endswith(" - " + fonte):
            titulo = titulo[: -len(fonte) - 3].strip()
        try:
            data = parsedate_to_datetime(item.findtext("pubDate"))
        except Exception:
            continue
        yield {"titulo": titulo, "fonte": fonte or "Google Notícias", "url": (item.findtext("link") or "").strip(), "data": data}


def classificar(titulo):
    t = sem_acento(titulo) + " "
    if not re.search(PRECO, t):
        return None, []
    produtos = []
    for palavra, cod in CULTURAS.items():
        if palavra in t and cod not in produtos and not (cod == "BATATA" and "BATATA DOCE" in produtos):
            produtos.append(cod)
    if not produtos and re.search(r"\b(hortalica|hortifruti|legume|verdura|folhosa)", t):
        produtos = ["TOMATE", "BATATA"]  # notícia geral: medimos nos dois mais negociados
    if not produtos:
        return None, []
    tipo = next((tp for tp, rx in TIPOS if re.search(rx, t)), "mercado")
    return tipo, produtos[:3]


def main():
    with open(EVENTOS, encoding="utf-8") as f:
        existentes = list(csv.DictReader(f, delimiter=";"))
    campos = list(existentes[0].keys()) if existentes else \
        ["id", "mes", "titulo", "resumo", "tipo", "produtos", "ceasa_medida", "fonte", "url", "conferida"]
    urls = {e["url"] for e in existentes}
    titulos = [sem_acento(e["titulo"]) for e in existentes]
    prox_id = max([int(e["id"]) for e in existentes] or [0]) + 1
    novas, vistas = [], 0
    for consulta in BUSCAS:
        try:
            itens = list(buscar(consulta))
        except Exception as e:
            registrar(f"ERRO na busca '{consulta}': {e}")
            continue
        for it in itens:
            vistas += 1
            if len(novas) >= MAX_NOVAS or it["url"] in urls:
                continue
            tipo, produtos = classificar(it["titulo"])
            if not tipo:
                continue
            tn = sem_acento(it["titulo"])
            if any(SequenceMatcher(None, tn, t).ratio() > 0.75 for t in titulos):
                continue
            novas.append({
                "id": str(prox_id), "mes": f"{it['data']:%Y-%m}", "titulo": it["titulo"][:110],
                "resumo": "Notícia encontrada automaticamente e ainda não conferida. Abra a fonte para ler o texto completo.",
                "tipo": tipo, "produtos": "|".join(produtos), "ceasa_medida": CEAGESP_BOL,
                "fonte": it["fonte"], "url": it["url"], "conferida": "nao",
            })
            prox_id += 1
            urls.add(it["url"])
            titulos.append(tn)
        time.sleep(2)  # educado com o servidor
    if novas:
        with open(EVENTOS, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos, delimiter=";")
            for n in novas:
                w.writerow({k: n.get(k, "") for k in campos})
    registrar(f"{vistas} notícias lidas, {len(novas)} novas acrescentadas: " +
              "; ".join(f"[{n['tipo']}] {n['titulo'][:60]}" for n in novas))


if __name__ == "__main__":
    main()
