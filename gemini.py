"""Chamadas HTTP à API do Gemini (texto e voz), com espera automática no limite grátis."""
import json
import time
import urllib.error
import urllib.request

import config

BASE = "https://generativelanguage.googleapis.com/v1beta"


def post(caminho: str, corpo: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        f"{BASE}/{caminho}",
        data=json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": config.GEMINI_API_KEY},
    )
    for n in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detalhe = e.read().decode(errors="ignore")[:600]
            # 429 = limite por minuto da camada grátis; 5xx = servidor ocupado
            if e.code in (429, 500, 502, 503, 504) and n < 3:
                print(f"[gemini] erro {e.code}, esperando {30 * n}s...")
                time.sleep(30 * n)
                continue
            raise RuntimeError(f"Gemini erro {e.code}: {detalhe}") from e
        except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
            # demora ou queda de conexão: tenta de novo
            if n < 3:
                print(f"[gemini] sem resposta ({e}), tentando de novo em {15 * n}s...")
                time.sleep(15 * n)
                continue
            raise RuntimeError(f"Gemini não respondeu depois de 3 tentativas: {e}") from e
    raise RuntimeError("Gemini não respondeu")
