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
            sem_credito = getattr(e, "code", None) == "insufficient_quota" or "credits" in str(e)
            if n == tentativas or sem_credito:
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


def gerar_imagem(prompt: str, destino: Path) -> Path:
    if config.IMAGE_PROVIDER == "openai":
        return _com_retry(_imagem_openai, prompt, destino)
    return _com_retry(_imagem_pollinations, prompt, destino)


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

    corpo = {
        "model": config.GEMINI_TTS_MODEL,
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
    dados = gemini.post("interactions", corpo)
    audios = [
        c["data"]
        for passo in dados.get("steps", []) if passo.get("type") == "model_output"
        for c in passo.get("content", []) if c.get("type") == "audio" and c.get("data")
    ]
    if not audios:
        raise RuntimeError(f"Gemini TTS sem áudio: {str(dados)[:300]}")
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

    modelo = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
    segmentos, _ = modelo.transcribe(str(audio), language="pt", word_timestamps=True)
    palavras = [(w.word.strip(), w.start, w.end) for s in segmentos for w in (s.words or [])]
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
