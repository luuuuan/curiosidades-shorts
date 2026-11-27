"""Configurações lidas das variáveis de ambiente (no Render: Environment)."""
import os
from pathlib import Path


def _carregar_env() -> None:
    """Lê o arquivo .env da pasta do projeto (só no PC; no Render usa o Environment)."""
    arquivo = Path(__file__).with_name(".env")
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, valor = linha.split("=", 1)
        os.environ.setdefault(nome.strip(), valor.strip().strip('"').strip("'"))


_carregar_env()


_SEGREDOS: list[str] = []


def _env(nome: str, padrao: str | None = None, obrigatoria: bool = False) -> str | None:
    valor = os.getenv(nome, padrao)
    if isinstance(valor, str):
        # tira espaços e quebras de linha coladas sem querer junto com a chave
        valor = valor.strip()
        if any(p in nome for p in ("KEY", "TOKEN", "SECRET")) and len(valor) >= 8:
            _SEGREDOS.append(valor)
    if obrigatoria and not valor:
        raise RuntimeError(f"Variável de ambiente {nome} não configurada")
    return valor


# Modo teste: gera o vídeo e salva em ./saida sem postar
DRY_RUN = _env("DRY_RUN", "false").lower() in ("1", "true", "sim", "yes")

# Claude (roteiro + checagem dos fatos)
# Quem gera imagem e voz
IMAGE_PROVIDER = _env("IMAGE_PROVIDER", "cloudflare,pexels").lower()  # ordem de tentativa
TTS_PROVIDER = _env("TTS_PROVIDER", "gemini").lower()  # gemini | edge | openai

# Quem escreve o roteiro: "gemini" (grátis) ou "claude" (pago)
LLM_PROVIDER = _env("LLM_PROVIDER", "gemini").lower()

# Gemini: chave grátis em aistudio.google.com -> Get API key
GEMINI_API_KEY = _env(
    "GEMINI_API_KEY", obrigatoria="gemini" in (LLM_PROVIDER, TTS_PROVIDER)
)
# Modelos do roteiro, em ordem de preferência (se um travar, usa o próximo)
GEMINI_MODEL = _env(
    "GEMINI_MODEL",
    "gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-3.1-flash-lite,"
    "gemini-2.5-flash-lite,gemini-flash-latest,gemini-3.5-flash,gemini-2.5-flash",
)
GEMINI_TIMEOUT = int(_env("GEMINI_TIMEOUT", "90"))  # segundos esperando cada resposta

# Claude (só se LLM_PROVIDER=claude)
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY", obrigatoria=LLM_PROVIDER == "claude")
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-sonnet-5-5")


# Voz do Gemini (grátis). Vozes: Puck, Charon, Kore, Fenrir, Orus, Aoede, Zephyr, Leda...
# Modelos de voz em ordem (se todos falharem, usa o edge-tts)
GEMINI_TTS_MODEL = _env("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts,gemini-3.8-flash-lite-tts")
GEMINI_TTS_VOICE = _env("GEMINI_TTS_VOICE", "Puck")
GEMINI_TTS_STYLE = _env(
    "GEMINI_TTS_STYLE",
    "Brazilian Portuguese narrator of fun-fact videos: energetic, intriguing, "
    "fast-paced but clear, natural Brazilian accent.",
)

# Whisper local (faster-whisper) para marcar o tempo das palavras na legenda
WHISPER_MODEL = _env("WHISPER_MODEL", "base")

# Cloudflare Workers AI (imagens por IA, cota grátis diária)
CLOUDFLARE_ACCOUNT_ID = _env("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = _env("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_IMAGE_MODEL = _env("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")

# Pexels (fotos reais grátis): chave em pexels.com/api
PEXELS_API_KEY = _env("PEXELS_API_KEY", "")

# Pollinations (só funciona com saldo hoje). Chave opcional em enter.pollinations.ai: tira o limite de 15s
POLLINATIONS_KEY = _env("POLLINATIONS_KEY", "")
POLLINATIONS_MODEL = _env("POLLINATIONS_MODEL", "flux")

# edge-tts (voz grátis). Vozes pt-BR: pt-BR-AntonioNeural, pt-BR-FranciscaNeural, pt-BR-ThalitaMultilingualNeural
EDGE_VOICE = _env("EDGE_VOICE", "pt-BR-AntonioNeural")
EDGE_RATE = _env("EDGE_RATE", "+10%")

# OpenAI (só se escolher openai acima)
OPENAI_API_KEY = _env(
    "OPENAI_API_KEY", obrigatoria=IMAGE_PROVIDER == "openai" or TTS_PROVIDER == "openai"
)
OPENAI_IMAGE_MODEL = _env("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")  # gpt-image-1 foi desligado em out/2026
OPENAI_IMAGE_QUALITY = _env("OPENAI_IMAGE_QUALITY", "low")  # low | medium | high
TTS_MODEL = _env("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = _env("TTS_VOICE", "onyx")
TTS_INSTRUCOES = _env(
    "TTS_INSTRUCOES",
    "Fale em português do Brasil, com sotaque brasileiro natural. Tom de narrador "
    "de curiosidades: animado, intrigante, ritmo rápido mas claro.",
)

# YouTube
YT_CLIENT_ID = _env("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = _env("YT_CLIENT_SECRET", "")
YT_REFRESH_TOKEN = _env("YT_REFRESH_TOKEN", "")
YOUTUBE_OK = bool(YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN)
YT_PRIVACY = _env("YT_PRIVACY", "public")  # public | unlisted | private

# Telegram (aprovação antes de postar). Sem token, posta direto sem aprovação.
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID", "")
APROVACAO = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# Quantos vídeos cada execução do cron produz
VIDEOS_POR_EXECUCAO = int(_env("VIDEOS_POR_EXECUCAO", "1"))


def ocultar(texto: str) -> str:
    """Troca qualquer chave/token por *** antes de mostrar um erro (log ou Telegram)."""
    texto = str(texto)
    for segredo in _SEGREDOS:
        texto = texto.replace(segredo, "***")
    return texto
