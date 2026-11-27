"""Imagens e narração (com o tempo de cada palavra, para legenda e troca de cena).

Modo grátis (padrão):
  - Imagens: Pollinations (sem cadastro)
  - Narração: Gemini TTS (reserva: edge-tts)
Modo pago (opcional): OpenAI para imagem e/ou voz.
"""
import asyncio
import base64
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import config

ESTILO_IMAGEM = (
    " Vertical 9:16 composition, cinematic lighting, highly detailed, vibrant colors, "
    "no text, no letters, no watermark, no logos."
)

_ultima_pollinations = 0.0


def _com_retry(func, *args, tentativas: int = 3, **kwargs):
    for n in range(1, tentativas + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            codigo = getattr(e, "code", None)
            sem_credito = codigo == "insufficient_quota" or "credits" in str(e)
            definitivo = isinstance(codigo, int) and 400 <= codigo < 500 and codigo != 429
            if n == tentativas or sem_credito or definitivo:
                raise
            espera = 20 * n
            print(f"[midia] erro ({e}); tentando de novo em {espera}s")
            time.sleep(espera)


# ---------------------------------------------------------------- imagens
def _imagem_pollinations(prompt: str, destino: Path) -> Path:
    global _ultima_pollinations
    # sem chave o limite é ~1 imagem a cada 15s
    if not config.POLLINATIONS_KEY:
        espera = 16 - (time.time() - _ultima_pollinations)
        if espera > 0:
            time.sleep(espera)

    texto = urllib.parse.quote(prompt + ESTILO_IMAGEM, safe="")
    params = {"width": 1080, "height": 1920, "model": config.POLLINATIONS_MODEL,
              "nologo": "true", "seed": int(time.time() * 1000) % 1_000_000}
    if config.POLLINATIONS_KEY:
        params["key"] = config.POLLINATIONS_KEY
        url = f"https://gen.pollinations.ai/image/{texto}?{urllib.parse.urlencode(params)}"
    else:
        url = f"https://image.pollinations.ai/prompt/{texto}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(url, headers={"User-Agent": "curiosidades-shorts/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            dados = r.read()
            tipo = r.headers.get("Content-Type", "")
    finally:
        _ultima_pollinations = time.time()
    if not tipo.startswith("image/") or len(dados) < 5000:
        raise RuntimeError(f"Pollinations não devolveu imagem ({tipo})")
    destino.write_bytes(dados)
    return destino


def _imagem_openai(prompt: str, destino: Path) -> Path:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    r = client.images.generate(
        model=config.OPENAI_IMAGE_MODEL,
        prompt=prompt + ESTILO_IMAGEM,
        size="1024x1536",
        quality=config.OPENAI_IMAGE_QUALITY,
        n=1,
    )
    item = r.data[0]
    if getattr(item, "b64_json", None):
        destino.write_bytes(base64.b64decode(item.b64_json))
    else:
        urllib.request.urlretrieve(item.url, destino)
    return destino


def _baixar(url: str, headers: dict | None = None, timeout: int = 120) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "curiosidades-shorts/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "")


def _imagem_cloudflare(prompt: str, destino: Path, busca: str | None = None) -> Path:
    """FLUX.1 schnell na Cloudflare Workers AI (cota grátis diária)."""
    import json

    url = (f"https://api.cloudflare.com/client/v4/accounts/{config.CLOUDFLARE_ACCOUNT_ID}"
           f"/ai/run/{config.CLOUDFLARE_IMAGE_MODEL}")
    # o modelo só aceita "prompt" e "steps"; qualquer campo a mais dá erro 400
    corpo = json.dumps({"prompt": (prompt + ESTILO_IMAGEM)[:2048], "steps": 6}).encode()
    req = urllib.request.Request(url, data=corpo, headers={
        "Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "curiosidades-shorts/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            dados, tipo = r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        # a Cloudflare explica o motivo no corpo da resposta
        try:
            erros = json.loads(e.read()).get("errors", [])
            motivo = "; ".join(f"{x.get('code')}: {x.get('message')}" for x in erros) or e.reason
        except Exception:  # noqa: BLE001
            motivo = e.reason
        erro = RuntimeError(f"Cloudflare {e.code}: {motivo}")
        erro.code = e.code
        raise erro from e
    if tipo.startswith("image/"):
        destino.write_bytes(dados)
        return destino
    resposta = json.loads(dados)
    imagem = (resposta.get("result") or {}).get("image")
    if not imagem:
        raise RuntimeError(f"Cloudflare sem imagem: {str(resposta)[:300]}")
    destino.write_bytes(base64.b64decode(imagem))
    return destino


_pexels_usadas: set[int] = set()


def _imagem_pexels(prompt: str, destino: Path, busca: str | None = None) -> Path:
    """Foto real do Pexels (grátis), buscada pelas palavras-chave da cena."""
    import json
    import random

    termo = busca or " ".join(prompt.replace(",", " ").split()[:4])
    url = ("https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
        {"query": termo, "orientation": "portrait", "per_page": 15}))
    dados, _ = _baixar(url, {"Authorization": config.PEXELS_API_KEY}, timeout=30)
    fotos = [f for f in json.loads(dados).get("photos", []) if f["id"] not in _pexels_usadas]
    if not fotos:
        raise RuntimeError(f"Pexels sem foto para '{termo}'")
    foto = random.choice(fotos[:5])
    _pexels_usadas.add(foto["id"])
    imagem, _ = _baixar(foto["src"]["large2x"])
    destino.write_bytes(imagem)
    return destino


# ---------------------------------------------------------------- clipes de vídeo
_pixabay_usados: set = set()
_trava_pixabay = __import__("threading").Lock()


def buscar_clipe(busca: str, destino: Path) -> Path:
    """Baixa um clipe real do Pixabay (grátis) para a cena. Levanta erro se não achar."""
    import json
    import random

    if not config.PIXABAY_API_KEY:
        raise RuntimeError("sem PIXABAY_API_KEY")
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode({
        "key": config.PIXABAY_API_KEY, "q": busca[:100], "per_page": 20,
        "safesearch": "true", "video_type": "film",
    })
    dados, _ = _baixar(url, timeout=30)
    hits = [h for h in json.loads(dados).get("hits", []) if h.get("duration", 0) >= 4]
    with _trava_pixabay:
        livres = [h for h in hits if h["id"] not in _pixabay_usados]
        if not livres:
            raise RuntimeError(f"Pixabay sem clipe para '{busca}'")
        # prefere clipes em pé (ficam melhores em 9:16) e depois os mais bem avaliados
        livres.sort(key=lambda h: (h["videos"]["medium"]["height"] < h["videos"]["medium"]["width"],
                                   -h.get("likes", 0)))
        hit = random.choice(livres[:4])
        _pixabay_usados.add(hit["id"])
    versoes = hit["videos"]
    escolha = next((versoes[k] for k in ("large", "medium", "small")
                    if versoes.get(k, {}).get("url") and versoes[k].get("size", 0) < 60_000_000), None)
    if not escolha:
        raise RuntimeError("clipe do Pixabay sem versão baixável")
    conteudo, _ = _baixar(escolha["url"], timeout=120)
    destino.write_bytes(conteudo)
    print(f"[midia] clipe Pixabay #{hit['id']} para '{busca}' ({escolha['width']}x{escolha['height']})")
    return destino


def visual_da_cena(cena: dict, pasta: Path, n: int) -> Path:
    """Clipe real quando a cena pede vídeo e o Pixabay tem; senão, imagem de IA."""
    if cena.get("visual") == "video" and config.PIXABAY_API_KEY and cena.get("busca"):
        try:
            return _com_retry(buscar_clipe, cena["busca"], pasta / f"cena_{n:02d}.mp4", tentativas=2)
        except Exception as e:  # noqa: BLE001
            print(f"[midia] cena {n}: sem clipe ({config.ocultar(e)[:120]}); usando imagem")
    return gerar_imagem(cena["prompt_imagem"], pasta / f"cena_{n:02d}.png", cena.get("busca"))


def _provedores_imagem() -> list:
    disponiveis = {
        "cloudflare": (_imagem_cloudflare, bool(config.CLOUDFLARE_ACCOUNT_ID and config.CLOUDFLARE_API_TOKEN)),
        "pexels": (_imagem_pexels, bool(config.PEXELS_API_KEY)),
        "openai": (lambda p, d, b=None: _imagem_openai(p, d), bool(config.OPENAI_API_KEY)),
        "pollinations": (lambda p, d, b=None: _imagem_pollinations(p, d), True),
    }
    ordem = [n.strip() for n in config.IMAGE_PROVIDER.split(",") if n.strip()]
    lista = [(n, disponiveis[n][0]) for n in ordem if n in disponiveis and disponiveis[n][1]]
    if not lista:
        raise RuntimeError(
            "Nenhuma fonte de imagem configurada. Coloque CLOUDFLARE_ACCOUNT_ID + "
            "CLOUDFLARE_API_TOKEN e/ou PEXELS_API_KEY."
        )
    return lista


usou_pexels = False


def gerar_imagem(prompt: str, destino: Path, busca: str | None = None) -> Path:
    """Tenta cada fonte de imagem em ordem (IMAGE_PROVIDER); se uma falhar, usa a próxima."""
    global usou_pexels
    ultimo = None
    for nome, func in _provedores_imagem():
        try:
            resultado = _com_retry(func, prompt, destino, busca, tentativas=2)
            if nome == "pexels":
                usou_pexels = True
            return resultado
        except Exception as e:  # noqa: BLE001
            ultimo = e
            print(f"[midia] imagem via {nome} falhou ({config.ocultar(e)[:150]}); tentando a próxima fonte")
    raise RuntimeError(f"Nenhuma fonte de imagem funcionou. Último erro: {config.ocultar(ultimo)}")


# ---------------------------------------------------------------- narração
async def _edge_async(texto: str, destino: Path) -> list[tuple[str, float, float]]:
    import edge_tts

    com = edge_tts.Communicate(texto, config.EDGE_VOICE, rate=config.EDGE_RATE,
                               boundary="WordBoundary")
    palavras = []
    with open(destino, "wb") as f:
        async for parte in com.stream():
            if parte["type"] == "audio":
                f.write(parte["data"])
            elif parte["type"] == "WordBoundary":
                inicio = parte["offset"] / 10_000_000
                fim = inicio + parte["duration"] / 10_000_000
                palavras.append((parte["text"], inicio, fim))
    return palavras


def _narracao_edge(texto: str, destino: Path) -> list[tuple[str, float, float]]:
    palavras = asyncio.run(_edge_async(texto, destino))
    if not palavras:
        raise RuntimeError("edge-tts não devolveu os tempos das palavras")
    return palavras


def _narracao_openai(texto: str, destino: Path) -> list[tuple[str, float, float]]:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    extras = {"instructions": config.TTS_INSTRUCOES} if config.TTS_MODEL.startswith("gpt-4o") else {}
    with client.audio.speech.with_streaming_response.create(
        model=config.TTS_MODEL, voice=config.TTS_VOICE, input=texto,
        response_format="mp3", **extras,
    ) as resp:
        resp.stream_to_file(destino)
    with open(destino, "rb") as f:
        r = client.audio.transcriptions.create(
            model="whisper-1", file=f, language="pt",
            response_format="verbose_json", timestamp_granularities=["word"],
        )
    return [(w.word, float(w.start), float(w.end)) for w in r.words]


def _narracao_gemini(texto: str, destino: Path, estilo: str | None = None) -> list[tuple[str, float, float]]:
    import gemini

    audios, ultimo = [], None
    for modelo in [m.strip() for m in config.GEMINI_TTS_MODEL.split(",") if m.strip()]:
        corpo = {
            "model": modelo,
            "input": [{
                "type": "user_input",
                "content": [{
                    "type": "text",
                    "text": texto,
                    "annotations": [{"type": "speech_metadata",
                                     "style": f"{config.GEMINI_TTS_STYLE} {estilo or ''}".strip()}],
                }],
            }],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": config.GEMINI_TTS_VOICE}]},
        }
        try:
            dados = gemini.post("interactions", corpo, tentativas=1)
        except gemini.GeminiErro as e:
            ultimo = e
            print(f"[midia] voz {modelo} falhou ({str(e)[:120].strip()}); indo pro próximo")
            continue
        audios = [
            c["data"]
            for passo in dados.get("steps", []) if passo.get("type") == "model_output"
            for c in passo.get("content", []) if c.get("type") == "audio" and c.get("data")
        ]
        if audios:
            print(f"[midia] narração com {modelo}, voz {config.GEMINI_TTS_VOICE}")
            break
        ultimo = RuntimeError(f"{modelo} sem áudio: {str(dados)[:200]}")
    if not audios:
        raise RuntimeError(f"Nenhum modelo de voz do Gemini funcionou: {ultimo}")
    bruto = base64.b64decode(audios[-1])

    wav = destino.with_suffix(".wav")
    if bruto[:4] == b"RIFF":
        wav.write_bytes(bruto)
    else:  # PCM puro: 24 kHz, mono, 16 bits
        import wave
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(bruto)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                    "-c:a", "libmp3lame", "-b:a", "160k", str(destino)], check=True)
    return _tempos_por_audio(destino, texto)


def _tempos_por_audio(audio: Path, texto: str) -> list[tuple[str, float, float]]:
    """Marca o tempo das palavras com Whisper local; sem ele, faz uma estimativa."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[midia] faster-whisper não instalado: legenda com tempo estimado")
        return _tempos_estimados(audio, texto)

    try:
        import numpy as np

        # decodifica com o ffmpeg (16 kHz mono) em vez de deixar o Whisper abrir o arquivo:
        # versões novas do PyAV quebram a leitura interna do faster-whisper
        pcm = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-i", str(audio), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
            capture_output=True, check=True,
        ).stdout
        amostras = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        modelo = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        segmentos, _ = modelo.transcribe(amostras, language="pt", word_timestamps=True)
        palavras = [(w.word.strip(), w.start, w.end) for s in segmentos for w in (s.words or [])]
    except Exception as e:  # noqa: BLE001
        print(f"[midia] Whisper falhou ({e}); legenda com tempo estimado")
        palavras = []
    return palavras or _tempos_estimados(audio, texto)


def _tempos_estimados(audio: Path, texto: str) -> list[tuple[str, float, float]]:
    """Divide a duração pelas palavras, proporcional ao tamanho e às pausas."""
    from video import duracao

    total = duracao(audio)
    palavras = texto.split()
    pesos = []
    for p in palavras:
        peso = len(p) + 2
        if p.endswith((".", "!", "?")):
            peso += 7
        elif p.endswith((",", ":", ";")):
            peso += 3
        pesos.append(peso)
    escala = total / sum(pesos)
    tempos, t = [], 0.0
    for p, peso in zip(palavras, pesos):
        dur = peso * escala
        tempos.append((p, t, t + dur * 0.85))
        t += dur
    return tempos


def gerar_narracao(texto: str, destino: Path, estilo: str | None = None) -> list[tuple[str, float, float]]:
    """Gera o áudio e devolve [(palavra, início, fim), ...]."""
    if config.TTS_PROVIDER == "openai":
        palavras = _com_retry(_narracao_openai, texto, destino)
    elif config.TTS_PROVIDER == "gemini":
        try:
            palavras = _narracao_gemini(texto, destino, estilo)
        except Exception as e:  # noqa: BLE001
            print(f"[midia] Gemini TTS falhou ({e}); usando edge-tts")
            palavras = _com_retry(_narracao_edge, texto, destino)
    else:
        palavras = _com_retry(_narracao_edge, texto, destino)

    # usa a grafia do roteiro (com pontuação) quando a contagem bate
    originais = texto.split()
    if len(originais) == len(palavras):
        palavras = [(o, s, e) for o, (_, s, e) in zip(originais, palavras)]
    return palavras
