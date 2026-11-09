"""Interpretação dos artigos com IA (Claude), em português simples — OPCIONAL e DESLIGADA por padrão.

Só funciona se o arquivo .env tiver a variável ANTHROPIC_API_KEY (chave paga da Anthropic). Sem a chave, este
programa só avisa e sai, sem gastar nada.

O que faz: pega os artigos de MAIOR IMPACTO que ainda não têm resumo da IA (no máximo ARTIGOS_IA_LIMITE por rodada,
padrão 100) e grava, para cada um: um resumo curto em português simples, "o que isso muda na lavoura" e o quanto o
resultado parece confiável. Aparece na página "Artigos científicos" no lugar da frase do resumo original.

Configuração opcional no .env (só os nomes; os valores são seus):
    ANTHROPIC_API_KEY      = sua chave (obrigatória para ligar)
    ARTIGOS_IA_MODELO      = modelo (padrão claude-opus-5-5; o claude-haiku-5-5 sai bem mais barato)
    ARTIGOS_IA_LIMITE      = quantos artigos por rodada (padrão 100)

Como usar (dentro da pasta do projeto, depois de instalar a biblioteca: .venv\\Scripts\\pip.exe install anthropic):
    .venv\\Scripts\\python.exe coleta\\artigos_ia.py
"""
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent
BANCO = PASTA / "dados" / "precos.db"
LOG = PASTA / "dados" / "log_artigos.txt"

ESQUEMA = {
    "type": "object",
    "properties": {
        "resumo": {"type": "string", "description": "2 a 3 frases em português simples, sem jargão, para um produtor rural"},
        "o_que_muda": {"type": "string", "description": "1 frase: o que o produtor pode fazer de diferente com este resultado"},
        "confianca": {"type": "string", "enum": ["alta", "média", "baixa"],
                      "description": "alta = experimento de campo grande/repetido; baixa = laboratório, vaso ou um só local/ano"},
    },
    "required": ["resumo", "o_que_muda", "confianca"],
    "additionalProperties": False,
}
SISTEMA = (
    "Você explica pesquisas agronômicas para produtores rurais brasileiros que não são cientistas. "
    "Escreva em português do Brasil simples, frases curtas, sem siglas sem explicar. Use só o que está no título e no resumo; "
    "se o resumo não trouxer números ou resultado claro, diga isso. Não invente doses, produtos ou números. "
    "Se o estudo foi feito em laboratório, vaso ou fora do Brasil, deixe isso claro no resumo."
)


def registrar(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M} [IA] {msg}"
    print(linha)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def ler_env():
    arq = PASTA / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    ler_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Interpretação com IA desligada: não há ANTHROPIC_API_KEY no arquivo .env. Nada foi feito (custo zero).")
        return
    try:
        import anthropic
    except ImportError:
        print("Falta a biblioteca da Anthropic. Instale com: .venv\\Scripts\\pip.exe install anthropic")
        return
    modelo = os.environ.get("ARTIGOS_IA_MODELO") or "claude-opus-5-5"  # em branco no .env = padrão
    limite = int(os.environ.get("ARTIGOS_IA_LIMITE") or "100")
    client = anthropic.Anthropic()
    con = sqlite3.connect(BANCO)
    feitos, recusados, erros = 0, 0, 0
    try:
        linhas = con.execute("SELECT id, titulo, resumo, culturas FROM artigos WHERE (resumo_ia IS NULL OR resumo_ia = '') "
                             "AND length(resumo) > 200 ORDER BY impacto DESC LIMIT ?", (limite,)).fetchall()
        for id_, titulo, resumo, culturas in linhas:
            pedido = f"Cultura(s): {culturas}\nTítulo: {titulo}\nResumo: {resumo}"
            try:
                kwargs = dict(model=modelo, max_tokens=2000, system=SISTEMA,
                              messages=[{"role": "user", "content": pedido}],
                              output_config={"effort": "low", "format": {"type": "json_schema", "schema": ESQUEMA}})
                if modelo.startswith(("claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")):
                    # se o modelo recusar por segurança, o próprio servidor tenta outro modelo adequado
                    r = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
                else:
                    r = client.messages.create(**kwargs)
            except anthropic.RateLimitError:
                registrar("limite de uso da API atingido; continua na próxima rodada")
                break
            except anthropic.APIStatusError as e:
                erros += 1
                registrar(f"erro da API ({e.status_code}) no artigo {id_}: {str(e)[:150]}")
                if e.status_code in (401, 403):
                    break
                continue
            except anthropic.APIConnectionError:
                registrar("sem conexão com a API; continua na próxima rodada")
                break
            if r.stop_reason == "refusal":
                recusados += 1
                continue
            texto = next((b.text for b in r.content if b.type == "text"), "")
            try:
                d = json.loads(texto)
            except json.JSONDecodeError:
                erros += 1
                continue
            final = f"{d['resumo']} O que pode mudar: {d['o_que_muda']} (confiança {d['confianca']})"
            con.execute("UPDATE artigos SET resumo_ia = ?, ia_em = ? WHERE id = ?",
                        (final, datetime.now().isoformat(timespec="seconds"), id_))
            con.commit()
            feitos += 1
    finally:
        con.close()
    registrar(f"{feitos} artigos interpretados com {modelo}, {recusados} recusados, {erros} erros")


if __name__ == "__main__":
    sys.exit(main())
