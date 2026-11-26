"""Chamadas HTTP à API do Gemini (texto e voz), com espera automática no limite grátis."""
import json
import time
import urllib.error
import urllib.request

import config

BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiErro(RuntimeError):
    def __init__(self, msg: str, codigo: int | None = None):
        super().__init__(msg)
        self.codigo = codigo


def _headers() -> dict:
    return {"Content-Type": "application/json", "x-goog-api-key": config.GEMINI_API_KEY}


def get(caminho: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(f"{BASE}/{caminho}", headers=_headers())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def post(caminho: str, corpo: dict, timeout: int = 180, tentativas: int = 3) -> dict:
    req = urllib.request.Request(
        f"{BASE}/{caminho}", data=json.dumps(corpo).encode(), headers=_headers()
    )
    for n in range(1, tentativas + 1):
        inicio = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                dados = json.loads(r.read())
            print(f"[gemini] {caminho.split(':')[0]} respondeu em {time.time() - inicio:.0f}s")
            return dados
        except urllib.error.HTTPError as e:
            detalhe = e.read().decode(errors="ignore")[:600]
            # 429 = limite por minuto da camada grátis; 5xx = servidor ocupado
            if e.code in (429, 500, 502, 503, 504) and n < tentativas:
                print(f"[gemini] erro {e.code}, esperando {30 * n}s...")
                time.sleep(30 * n)
                continue
            raise GeminiErro(f"Gemini erro {e.code}: {detalhe}", e.code) from e
        except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
            print(f"[gemini] sem resposta em {time.time() - inicio:.0f}s ({e})")
            if n < tentativas:
                time.sleep(10)
                continue
            raise GeminiErro(f"Gemini não respondeu: {e}") from e
    raise GeminiErro("Gemini não respondeu")


def texto(prompt: str, json_saida: bool = True) -> str:
    """Pede texto ao Gemini. Tenta cada modelo de GEMINI_MODEL (separados por vírgula),
    com raciocínio reduzido para responder rápido."""
    modelos = [m.strip() for m in config.GEMINI_MODEL.split(",") if m.strip()]
    ultimo = None
    for modelo in modelos:
        geracao = {"temperature": 1.0, "thinkingConfig": {"thinkingLevel": "low"}}
        if json_saida:
            geracao["responseMimeType"] = "application/json"
        corpo = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                 "generationConfig": geracao}
        try:
            try:
                dados = post(f"models/{modelo}:generateContent", corpo,
                             timeout=config.GEMINI_TIMEOUT, tentativas=2)
            except GeminiErro as e:
                if e.codigo != 400:
                    raise
                # modelo não aceita o ajuste de raciocínio: tenta sem ele
                geracao.pop("thinkingConfig", None)
                dados = post(f"models/{modelo}:generateContent", corpo,
                             timeout=config.GEMINI_TIMEOUT, tentativas=2)
            partes = dados["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in partes if not p.get("thought"))
        except (GeminiErro, KeyError, IndexError) as e:
            ultimo = e
            print(f"[gemini] modelo {modelo} falhou ({str(e)[:200]}); tentando o próximo")
    raise GeminiErro(f"Nenhum modelo do Gemini respondeu. Último erro: {ultimo}")
