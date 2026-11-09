"""Busca ARTIGOS CIENTÍFICOS (de 2010 em diante) sobre as culturas do sistema (dados\\artigos_culturas.csv),
classifica por cultura e por tema e dá uma NOTA DE IMPACTO de 0 a 100. Grava na tabela "artigos" do banco.

Fontes (grátis):
1. OpenAlex (catálogo mundial, openalex.org): para cada cultura, os mais citados do mundo, os mais citados com
   autores do Brasil e os mais recentes. Só a área "Ciências Agrárias e Biológicas" (e Veterinária na pecuária).
   Sem chave, a cota grátis é de ~100 buscas por dia (dividida com quem usa a mesma internet); por isso cada
   rodada faz no máximo 60 buscas e continua de onde parou no dia seguinte. Com uma chave grátis do OpenAlex
   (variável OPENALEX_API_KEY no arquivo .env), a cota sobe e tudo é feito numa rodada só.
2. Embrapa Alice (repositório de publicações da Embrapa, protocolo OAI-PMH): só "Artigo de periódico" de 2010 em
   diante que fale de alguma das culturas. A primeira carga é grande (~1.500 páginas); salva onde parou.

Nota de impacto = 60% citações (citações por ano, comparadas com os outros artigos da mesma cultura)
                + 40% utilidade prática (experimento de campo, produtividade, custo, resultado em %, Brasil...).
Sem número de citações (alguns artigos da Embrapa), a nota usa só a utilidade prática e isso fica marcado.

"Interpretação" grátis: o resumo original + a frase do resumo que traz o principal resultado + os temas.
(A interpretação com IA, em português simples, fica para depois: coleta\\artigos_ia.py.)

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\artigos.py           (rodada normal: atualiza um pouco a cada dia)
    .venv\\Scripts\\python.exe coleta\\artigos.py --tudo    (carga completa da Embrapa Alice, demora)
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
BANCO = PASTA / "dados" / "precos.db"
CULTURAS = PASTA / "dados" / "artigos_culturas.csv"
LOG = PASTA / "dados" / "log_artigos.txt"
UA = {"User-Agent": "PrecoSeguro-artigos/0.1"}
ANO_MIN = 2010
OA = "https://api.openalex.org/works"
ALICE = "https://www.alice.cnptia.embrapa.br/alice-oai/request"
NS = {"oai": "http://www.openarchives.org/OAI/2.0/", "dc": "http://purl.org/dc/elements/1.1/",
      "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/"}


def _ler_env():
    """Lê o arquivo .env (se existir) para as variáveis do programa. Nada é mostrado na tela."""
    arq = PASTA / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_ler_env()
CHAVE_OA = os.environ.get("OPENALEX_API_KEY", "")  # o valor fica só no .env; aqui só o nome da variável
MAX_BUSCAS_OA = 600 if CHAVE_OA else 60
MAX_PAGINAS_ALICE = 100000 if "--tudo" in sys.argv else 300
PECUARIA = {"BOI", "FRANGO", "SUINO", "LEITE"}
SUBAREAS = "1102|1108|1109|1110|1111"
SUBAREAS_PEC = "1102|1103|3401|3402|3403|3404"

# ---------- temas (português + inglês) ----------
TEMAS = {
    "Pragas e doenças": r"\bpests?\b|\bdiseases?\b|\bpathogen|\bfung(?:al|us|i\b)|\bnematod|\binsect|\bvirus|\bviral\b|"
                        r"\bbacteri|\bblight|\brots?\b|mildew|\baphid|whitefl|caterpillar|\bweevil|\bmites?\b|"
                        r"praga|doença|fungo|nematoide|nematóide|inseto|vírus|bactéri|podridão|míldio|pulgão|mosca[ -]branca|lagarta|ferrugem|rust\b",
    "Plantas daninhas": r"weed|herbicid|daninha|herbicida|glyphosate|glifosato",
    "Adubação e solo": r"fertiliz|nitrogen|phosph|potass|soil|nutrient|liming|lime\b|manure|biochar|aduba|nitrogên|fósforo|potássio|\bsolos?\b|"
                       r"calagem|nutrição (mineral|de plantas)|nutrientes|esterco|micronutri|inoculat|inocula|bradyrhizob|azospirill",
    "Água e irrigação": r"irrigat|water|drought|evapotransp|irriga|água|hídric|seca\b|déficit hídrico",
    "Clima": r"climat|temperature|heat stress|frost|el ni[nñ]o|la ni[nñ]a|warming|clima|temperatura|geada|calor|aqueciment|zoneamento",
    "Variedades e melhoramento": r"cultivar|genotyp|breeding|variet|hybrid|germplasm|genom|transgen|melhoramento|genótipo|variedade|híbrido|germoplasma",
    "Pós-colheita e qualidade": r"postharvest|post-harvest|storage|shelf[ -]life|quality|drying|pós[ -]colheita|armazena|qualidade|secagem|vida útil",
    "Custo, preço e mercado": r"\bprice|cost|profit|market|economic|income|financ|\bpreço|custo|lucr|mercado|econômic|renda|rentab|viabilidade",
    "Manejo e plantio": r"planting date|sowing|spacing|plant density|population density|management|tillage|no-till|intercrop|rotation|"
                        r"época de plantio|semeadura|espaçamento|densidade|manejo|plantio direto|consórcio|rotação",
    "Nutrição e manejo animal": r"\bdiet|feed\b|feeding|weight gain|grazing|pasture|rumen|forage|supplement|carcass|"
                                r"dieta|ração|ganho de peso|pastagem|pastejo|rúmen|forragem|suplementa|carcaça|confinamento",
    "Sustentabilidade": r"carbon|emission|greenhouse|sustainab|biodivers|carbono|emiss|efeito estufa|sustentab|integração lavoura",
}
O_QUE_MUDA = {
    "Pragas e doenças": "pode ajudar a controlar pragas e doenças (e a gastar menos com defensivos)",
    "Plantas daninhas": "pode ajudar no controle do mato",
    "Adubação e solo": "pode ajudar a acertar a adubação e cuidar do solo",
    "Água e irrigação": "pode ajudar a usar melhor a água e a irrigação",
    "Clima": "ajuda a entender o efeito do clima na lavoura",
    "Variedades e melhoramento": "mostra variedades ou materiais genéticos que podem render mais",
    "Pós-colheita e qualidade": "pode ajudar a perder menos depois da colheita e vender com mais qualidade",
    "Custo, preço e mercado": "traz números de custo, preço ou lucro",
    "Manejo e plantio": "pode ajudar no manejo e na época/forma de plantio",
    "Nutrição e manejo animal": "pode ajudar na alimentação e no manejo dos animais",
    "Sustentabilidade": "trata de sustentabilidade (carbono, emissões, integração)",
}
PRATICO = [  # (padrão, peso) — sinais de que o artigo traz algo aplicável no campo
    (r"field (trial|experiment|condition|study)|on-farm|experimento de campo|condições de campo|ensaio de campo", 0.25),
    (r"yield|productivity|produtividade|rendimento|produção por", 0.20),
    (r"\d+(?:[.,]\d+)?\s?%", 0.15),
    (r"recommend|recomend", 0.10),
    (r"\bcost|profit|economic|custo|lucr|econômic|rentab", 0.15),
    (r"brazil|brasil|cerrado|minas gerais|são paulo|paraná|goiás|mato grosso|bahia", 0.15),
]
RESULTADO = re.compile(r"increas|reduc|decreas|improv|higher|lower|greater|significant|resulted|aument|reduz|diminu|"
                       r"melhor|maior|menor|significativ|proporcion|\d+(?:[.,]\d+)?\s?%", re.I)


def registrar(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M} {msg}"
    print(linha)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def pedir(url, tentativas=3, espera=30):
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RuntimeError("cota esgotada (HTTP 429)") from e
            if i == tentativas - 1:
                raise
        except Exception:
            if i == tentativas - 1:
                raise
        time.sleep(espera)


# ---------- textos ----------
def resumo_de_indice(inv):
    """O OpenAlex guarda o resumo como 'palavra -> posições'; aqui volta a ser texto."""
    if not inv:
        return ""
    pos = {}
    for palavra, lista in inv.items():
        for p in lista:
            pos[p] = palavra
    return " ".join(pos[i] for i in sorted(pos))


def frases(texto):
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú])", texto) if len(f.strip()) > 40]


def principal_resultado(resumo):
    """A frase do resumo com mais sinais de resultado (aumentou, reduziu, %...), de preferência perto do fim."""
    fs = frases(resumo)
    if not fs:
        return ""
    notas = [(len(RESULTADO.findall(f)) + 0.3 * i / len(fs), f) for i, f in enumerate(fs)]
    nota, f = max(notas)
    return f[:500] if nota >= 1 else ""


def temas_de(texto, titulo=""):
    """Tema marcado se aparece no título, ou pelo menos 2 vezes no resto do texto (menos alarme falso)."""
    t, tit = texto.lower(), titulo.lower()
    return [tema for tema, p in TEMAS.items() if re.search(p, tit) or len(re.findall(p, t)) >= 2]


def nota_pratica(texto):
    t = texto.lower()
    return min(1.0, sum(peso for p, peso in PRATICO if re.search(p, t)))


# ---------- banco ----------
def preparar(con):
    con.execute("""CREATE TABLE IF NOT EXISTS artigos (
        id TEXT PRIMARY KEY, fonte TEXT, titulo TEXT, autores TEXT, ano INTEGER, revista TEXT, doi TEXT, url TEXT,
        citacoes INTEGER, culturas TEXT, temas TEXT, resumo TEXT, resultado TEXT, pratico REAL, impacto REAL,
        so_pratica INTEGER, idioma TEXT, acesso_aberto INTEGER, coletado_em TEXT, resumo_ia TEXT, ia_em TEXT, area TEXT)""")
    if "area" not in [c[1] for c in con.execute("PRAGMA table_info(artigos)")]:
        con.execute("ALTER TABLE artigos ADD COLUMN area TEXT")
    con.execute("CREATE TABLE IF NOT EXISTS artigos_estado (chave TEXT PRIMARY KEY, valor TEXT, atualizado_em TEXT)")


def estado(con, chave, valor=None):
    if valor is None:
        r = con.execute("SELECT valor, atualizado_em FROM artigos_estado WHERE chave = ?", (chave,)).fetchone()
        return r if r else (None, None)
    con.execute("INSERT OR REPLACE INTO artigos_estado VALUES (?, ?, ?)", (chave, valor, datetime.now().isoformat(timespec="seconds")))


def gravar(con, art):
    """Insere ou junta (mesmo artigo achado por outra cultura/consulta: soma as culturas, atualiza citações)."""
    velho = con.execute("SELECT culturas, resumo_ia, ia_em, fonte, citacoes, resumo, resultado, revista FROM artigos "
                        "WHERE id = ?", (art["id"],)).fetchone()
    if velho:
        cs = sorted(set(filter(None, (velho[0] or "").split("|"))) | set(art["culturas"].split("|")))
        art["culturas"] = "|".join(cs)
        art["resumo_ia"], art["ia_em"] = velho[1], velho[2]
        if velho[3] and velho[3] != art["fonte"] and art["fonte"] not in velho[3]:
            art["fonte"] = " + ".join(sorted({*velho[3].split(" + "), art["fonte"]}))
        if art.get("citacoes") is None or (velho[4] is not None and velho[4] > art["citacoes"]):
            art["citacoes"] = velho[4]
        if len(velho[5] or "") > len(art.get("resumo") or ""):  # fica o resumo mais completo
            art["resumo"], art["resultado"] = velho[5], velho[6]
        art["revista"] = art.get("revista") or velho[7]
        if not art.get("area"):
            art["area"] = (con.execute("SELECT area FROM artigos WHERE id = ?", (art["id"],)).fetchone() or [None])[0]
    cols = ["id", "fonte", "titulo", "autores", "ano", "revista", "doi", "url", "citacoes", "culturas", "temas", "resumo",
            "resultado", "pratico", "impacto", "so_pratica", "idioma", "acesso_aberto", "coletado_em", "resumo_ia", "ia_em", "area"]
    con.execute(f"INSERT OR REPLACE INTO artigos ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [art.get(c) for c in cols])


# ---------- OpenAlex ----------
def consulta_oa(cult, tipo):
    termos = cult["busca_en"].replace(" OR ", "|")
    # subáreas do OpenAlex: Agronomia (1102), Horticultura (1108), Insetos (1109), Plantas (1110), Solos (1111);
    # na pecuária também Ciência Animal (1103) e Veterinária (3401-3404). Fica de fora Ciência de Alimentos (1106).
    sub = SUBAREAS_PEC if cult["cultura"] in PECUARIA else SUBAREAS
    f = [f"title.search:{termos}", "type:article", f"primary_topic.subfield.id:{sub}"]
    if tipo == "recentes":
        f.append(f"from_publication_date:{date.today().year - 2}-01-01")
        sort, n = "publication_date:desc", 50
    else:
        f.append(f"from_publication_date:{ANO_MIN}-01-01")
        sort, n = "cited_by_count:desc", 100
    if tipo == "brasil":
        f.append("authorships.countries:BR")
    p = {"filter": ",".join(f), "sort": sort, "per-page": n,
         "select": "id,doi,title,publication_year,cited_by_count,primary_location,abstract_inverted_index,language,"
                   "authorships,open_access,primary_topic"}
    if CHAVE_OA:
        p["api_key"] = CHAVE_OA
    return OA + "?" + urllib.parse.urlencode(p)


def artigo_oa(r, cultura):
    titulo = (r.get("title") or "").strip()
    resumo = resumo_de_indice(r.get("abstract_inverted_index"))
    fonte_rev = ((r.get("primary_location") or {}).get("source") or {})
    autores = [a.get("author", {}).get("display_name", "") for a in (r.get("authorships") or [])[:4]]
    texto = f"{titulo}. {resumo}"
    doi = (r.get("doi") or "").replace("https://doi.org/", "")
    return {"id": "doi:" + doi.lower() if doi else r["id"], "fonte": "OpenAlex", "titulo": titulo,
            "autores": "; ".join(filter(None, autores)) + (" et al." if len(r.get("authorships") or []) > 4 else ""),
            "ano": r.get("publication_year"), "revista": fonte_rev.get("display_name", ""), "doi": doi,
            "url": r.get("doi") or (r.get("primary_location") or {}).get("landing_page_url") or r["id"],
            "citacoes": r.get("cited_by_count"), "culturas": cultura, "temas": "|".join(temas_de(texto, titulo)),
            "resumo": resumo[:3000], "resultado": principal_resultado(resumo), "pratico": nota_pratica(texto),
            "area": ((r.get("primary_topic") or {}).get("subfield") or {}).get("display_name", ""),
            "idioma": r.get("language") or "", "acesso_aberto": int(bool((r.get("open_access") or {}).get("is_oa"))),
            "coletado_em": date.today().isoformat()}


def rodar_openalex(con, culturas):
    """Fila: primeiro o que nunca foi buscado, depois o mais antigo. Mais citados: renova a cada 30 dias;
    recentes: a cada 7 dias."""
    fila = []
    for _, c in culturas.iterrows():
        for tipo, dias in (("mundo", 30), ("brasil", 30), ("recentes", 7)):
            _, quando = estado(con, f"oa:{c['cultura']}:{tipo}")
            if quando is None or datetime.fromisoformat(quando) < datetime.now() - timedelta(days=dias):
                fila.append((quando or "", c, tipo))
    fila.sort(key=lambda x: x[0])
    feitas, novos = 0, 0
    for _, c, tipo in fila[:MAX_BUSCAS_OA]:
        try:
            d = json.loads(pedir(consulta_oa(c, tipo)))
        except Exception as e:
            registrar(f"OpenAlex parou em {c['cultura']}/{tipo}: {e}")
            break
        for r in d.get("results", []):
            if r.get("title") and (r.get("publication_year") or 0) >= ANO_MIN:
                gravar(con, artigo_oa(r, c["cultura"]))
                novos += 1
        estado(con, f"oa:{c['cultura']}:{tipo}", str(d.get("meta", {}).get("count", "")))
        con.commit()
        feitas += 1
        time.sleep(0.5)
    registrar(f"OpenAlex: {feitas} buscas feitas, {novos} artigos gravados/atualizados, {max(0, len(fila) - feitas)} buscas ficaram para a próxima rodada")


# ---------- Embrapa Alice ----------
def rodar_alice(con, culturas):
    padroes = {c["cultura"]: re.compile(c["palavras"], re.I) for _, c in culturas.iterrows()}
    token, _ = estado(con, "alice:token")
    ultimo_dia, _ = estado(con, "alice:ultimo_dia")
    if token:
        url = f"{ALICE}?verb=ListRecords&resumptionToken={urllib.parse.quote(token)}"
    else:
        desde = f"&from={ultimo_dia}" if ultimo_dia else ""
        url = f"{ALICE}?verb=ListRecords&metadataPrefix=oai_dc{desde}"
        estado(con, "alice:inicio_rodada", date.today().isoformat())
    paginas, guardados, vistos = 0, 0, 0
    while url and paginas < MAX_PAGINAS_ALICE:
        try:
            raiz = ET.fromstring(pedir(url, espera=60))
        except Exception as e:
            registrar(f"Embrapa Alice parou ({e}); continua na próxima rodada")
            break
        erro = raiz.find("oai:error", NS)
        if erro is not None:
            if erro.get("code") == "noRecordsMatch":
                estado(con, "alice:token", "")
                estado(con, "alice:ultimo_dia", date.today().isoformat())
            else:
                registrar(f"Embrapa Alice respondeu erro: {erro.get('code')} {erro.text}")
            break
        for rec in raiz.iterfind(".//oai:record", NS):
            vistos += 1
            md = rec.find(".//oai_dc:dc", NS)
            if md is None:
                continue
            campo = lambda n: [(x.text or "").strip() for x in md.findall(f"dc:{n}", NS)]
            if "Artigo de periódico" not in campo("type"):
                continue
            anos = [int(d) for d in campo("date") if re.fullmatch(r"\d{4}", d)]
            ano = anos[0] if anos else None
            if not ano or ano < ANO_MIN:
                continue
            titulo = " ".join(campo("title"))
            resumo = " ".join(d for d in campo("description") if len(d) > 80)
            assuntos = "; ".join(campo("subject"))
            texto = f"{titulo}. {assuntos}. {resumo}"
            cults = [c for c, p in padroes.items() if p.search(f"{titulo}. {assuntos}")] or \
                    [c for c, p in padroes.items() if p.search(resumo)][:2]
            if not cults:
                continue
            ids = campo("identifier")
            link = next((i for i in ids if "alice/handle" in i), "")
            doi = next((re.sub(r"^.*?(10\.\d{4,}/\S+?)\.?$", r"\1", i) for i in ids if re.search(r"10\.\d{4,}/", i)), "")
            citacao = next((i for i in ids if ", v." in i or ", n." in i or re.search(r", \d{4}\.$", i)), "")
            gravar(con, {"id": "doi:" + doi.lower() if doi else "alice:" + link.rsplit("/", 1)[-1], "fonte": "Embrapa Alice",
                         "titulo": titulo, "autores": "; ".join(campo("creator")[:4]) + (" et al." if len(campo("creator")) > 4 else ""),
                         "ano": ano, "revista": citacao.split(", v.")[0].split(", n.")[0][:200], "doi": doi,
                         "url": (f"https://doi.org/{doi}" if doi else link), "citacoes": None, "culturas": "|".join(cults),
                         "temas": "|".join(temas_de(texto, titulo)), "resumo": resumo[:3000], "resultado": principal_resultado(resumo),
                         "pratico": nota_pratica(texto), "idioma": ",".join(campo("language")), "area": "Embrapa",
                         "acesso_aberto": int("openAccess" in " ".join(campo("rights"))), "coletado_em": date.today().isoformat()})
            guardados += 1
        tok = raiz.find(".//oai:resumptionToken", NS)
        token = (tok.text or "").strip() if tok is not None else ""
        estado(con, "alice:token", token)
        if not token:
            inicio, _ = estado(con, "alice:inicio_rodada")
            estado(con, "alice:ultimo_dia", inicio or date.today().isoformat())
        con.commit()
        paginas += 1
        url = f"{ALICE}?verb=ListRecords&resumptionToken={urllib.parse.quote(token)}" if token else None
        if paginas % 50 == 0:
            registrar(f"Embrapa Alice: {paginas} páginas, {vistos} registros vistos, {guardados} artigos guardados até agora")
        time.sleep(1)
    registrar(f"Embrapa Alice: {paginas} páginas, {vistos} registros vistos, {guardados} artigos guardados" +
              (" — a carga continua na próxima rodada" if url else " — em dia"))


# ---------- citações dos artigos da Embrapa (pelo DOI, no OpenAlex) ----------
def citacoes_alice(con, limite_buscas=10):
    falta = [r[0] for r in con.execute("SELECT doi FROM artigos WHERE fonte = 'Embrapa Alice' AND doi != '' AND citacoes IS NULL "
                                       "ORDER BY pratico DESC LIMIT ?", (limite_buscas * 50,))]
    achados = 0
    for i in range(0, len(falta), 50):
        lote = falta[i:i + 50]
        p = {"filter": "doi:" + "|".join(lote), "per-page": 50, "select": "doi,cited_by_count"}
        if CHAVE_OA:
            p["api_key"] = CHAVE_OA
        try:
            d = json.loads(pedir(OA + "?" + urllib.parse.urlencode(p)))
        except Exception as e:
            registrar(f"citações da Embrapa pararam: {e}")
            break
        vistos = set()
        for r in d.get("results", []):
            doi = (r.get("doi") or "").replace("https://doi.org/", "").lower()
            vistos.add(doi)
            con.execute("UPDATE artigos SET citacoes = ? WHERE lower(doi) = ?", (r.get("cited_by_count"), doi))
            achados += 1
        for doi in set(x.lower() for x in lote) - vistos:  # DOI que o OpenAlex não conhece: marca -1 para não buscar de novo
            con.execute("UPDATE artigos SET citacoes = -1 WHERE lower(doi) = ?", (doi,))
        con.commit()
        time.sleep(0.5)
    if falta:
        registrar(f"citações de artigos da Embrapa: {achados} achadas no OpenAlex")


def reclassificar(con):
    """Refaz os temas de todos os artigos com as regras atuais (título, ou 2+ vezes no resumo)."""
    linhas = con.execute("SELECT id, titulo, resumo FROM artigos").fetchall()
    con.executemany("UPDATE artigos SET temas = ? WHERE id = ?",
                    [("|".join(temas_de(f"{ti}. {re_ or ''}", ti or "")), i) for i, ti, re_ in linhas])
    con.commit()


# ---------- nota de impacto ----------
def recalcular_impacto(con):
    a = pd.read_sql("SELECT id, ano, citacoes, culturas, pratico FROM artigos", con)
    if a.empty:
        return
    idade = (date.today().year - a["ano"].astype(float) + 1).clip(lower=1)
    a["cpa"] = a["citacoes"].where(a["citacoes"] >= 0) / idade
    a["cultura1"] = a["culturas"].str.split("|").str[0]
    a["pct"] = a.groupby("cultura1")["cpa"].rank(pct=True)
    sem = a["pct"].isna()
    a["impacto"] = (100 * (0.6 * a["pct"].fillna(0) + 0.4 * a["pratico"])).where(~sem, 100 * a["pratico"] * 0.7)
    con.executemany("UPDATE artigos SET impacto = ?, so_pratica = ? WHERE id = ?",
                    list(zip(a["impacto"].round(1), sem.astype(int), a["id"])))
    con.commit()


def main():
    culturas = pd.read_csv(CULTURAS, sep=";", dtype=str).fillna("")
    con = sqlite3.connect(BANCO)
    try:
        preparar(con)
        if "--refazer-openalex" in sys.argv:  # refaz as buscas do OpenAlex (ex.: depois de mudar o filtro)
            con.execute("DELETE FROM artigos_estado WHERE chave LIKE 'oa:%'")
            con.commit()
        if "--so-alice" not in sys.argv:
            rodar_openalex(con, culturas)
        rodar_alice(con, culturas)
        citacoes_alice(con)
        reclassificar(con)
        recalcular_impacto(con)
        n = con.execute("SELECT fonte, COUNT(*) FROM artigos GROUP BY fonte").fetchall()
        registrar("artigos no banco: " + ", ".join(f"{f} {k:,}" for f, k in n))
    finally:
        con.close()


if __name__ == "__main__":
    main()
