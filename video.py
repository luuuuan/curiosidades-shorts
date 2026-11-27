"""Monta o Short (1080x1920) com FFmpeg: clipes reais e imagens com movimento, transições,
narração e legenda."""
import json
import subprocess
from pathlib import Path

LARGURA, ALTURA, FPS = 1080, 1920, 30


def _rodar(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou:\n{' '.join(cmd)}\n{r.stderr[-2000:]}")


def duracao(arquivo: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(arquivo)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def tempos_das_cenas(cenas: list[dict], palavras: list[tuple], duracao_total: float) -> list[float]:
    """Duração de cada cena, trocando a imagem no início da 1ª palavra da cena seguinte."""
    contagens = [len(c["narracao"].split()) for c in cenas]
    total_roteiro = sum(contagens)
    inicios = [0.0]
    acumulado = 0
    for qtd in contagens[:-1]:
        acumulado += qtd
        # mapeia proporcionalmente caso a transcrição tenha contado diferente
        idx = round(acumulado * len(palavras) / total_roteiro)
        idx = min(max(idx, 0), len(palavras) - 1)
        inicios.append(palavras[idx][1] if palavras else duracao_total * acumulado / total_roteiro)
    inicios.append(duracao_total + 0.4)
    duracoes = [max(inicios[i + 1] - inicios[i], 0.8) for i in range(len(cenas))]
    return duracoes


TRANSICAO = 0.3  # segundos de transição entre cenas
_TRANSICOES = ["fade", "smoothup", "smoothleft", "zoomin", "fade", "smoothright"]
_MOVIMENTOS = ["zoom_in", "pan_direita", "zoom_out", "pan_cima", "pan_esquerda"]


def _clipe(imagem: Path, segundos: float, destino: Path, movimento: str) -> None:
    """Imagem parada vira clipe com movimento (zoom ou deslizar)."""
    frames = max(int(round(segundos * FPS)), 1)
    t = f"on/{frames}"
    x_meio, y_meio = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    z, x, y = "1.15", x_meio, y_meio
    if movimento == "zoom_in":
        z = f"1+0.2*{t}"
    elif movimento == "zoom_forte":
        z = f"1+0.3*{t}"
    elif movimento == "zoom_out":
        z = f"1.2-0.2*{t}"
    elif movimento == "pan_direita":
        x = f"(iw-iw/zoom)*{t}"
    elif movimento == "pan_esquerda":
        x = f"(iw-iw/zoom)*(1-{t})"
    elif movimento == "pan_cima":
        y = f"(ih-ih/zoom)*(1-{t})"
    filtro = (
        f"scale={LARGURA * 2}:{ALTURA * 2}:force_original_aspect_ratio=increase,"
        f"crop={LARGURA * 2}:{ALTURA * 2},"
        f"zoompan=z='{z}':x='{x}':y='{y}'"
        f":d={frames}:s={LARGURA}x{ALTURA}:fps={FPS},setsar=1,format=yuv420p"
    )
    _rodar([
        "ffmpeg", "-y", "-i", str(imagem), "-vf", filtro, "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(destino),
    ])


def _clipe_video(origem: Path, segundos: float, destino: Path) -> None:
    """Clipe real recortado em 9:16 no tamanho da cena (repete se for curto)."""
    filtro = (
        f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
        f"crop={LARGURA}:{ALTURA},fps={FPS},setsar=1,format=yuv420p"
    )
    _rodar([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(origem), "-t", f"{segundos:.3f}",
        "-vf", filtro, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-an",
        str(destino),
    ])


def _tempo_ass(s: float) -> str:
    h, resto = divmod(s, 3600)
    m, s = divmod(resto, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def gerar_legenda(palavras: list[tuple], destino: Path, max_palavras: int = 3) -> Path:
    """Legenda estilo Shorts: blocos curtos, caixa alta, contorno grosso."""
    cabecalho = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {LARGURA}
PlayResY: {ALTURA}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Padrao,DejaVu Sans,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,80,80,620,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    blocos, atual = [], []
    for p in palavras:
        atual.append(p)
        if len(atual) >= max_palavras or p[0].rstrip().endswith((".", ",", "!", "?", ":")):
            blocos.append(atual)
            atual = []
    if atual:
        blocos.append(atual)

    linhas = []
    for i, bloco in enumerate(blocos):
        inicio = bloco[0][1]
        fim = blocos[i + 1][0][1] if i + 1 < len(blocos) else bloco[-1][2] + 0.3
        texto = " ".join(w for w, _, _ in bloco).upper().replace("{", "").replace("}", "")
        texto = texto.rstrip(",.")
        linhas.append(
            f"Dialogue: 0,{_tempo_ass(inicio)},{_tempo_ass(fim)},Padrao,,0,0,0,,{texto}"
        )
    destino.write_text(cabecalho + "\n".join(linhas) + "\n", encoding="utf-8")
    return destino


def montar_video(visuais: list[Path], duracoes: list[float], audio: Path,
                 legenda: Path, destino: Path, pasta: Path) -> Path:
    n = len(visuais)
    clipes = []
    for i, (vis, seg) in enumerate(zip(visuais, duracoes)):
        # cada cena (menos a última) ganha a sobra que a transição "come"
        seg_total = seg + (TRANSICAO if i < n - 1 else 0)
        clipe = pasta / f"clipe_{i:02d}.mp4"
        if vis.suffix.lower() in (".mp4", ".mov", ".webm"):
            _clipe_video(vis, seg_total, clipe)
        else:
            movimento = "zoom_forte" if i == 0 else _MOVIMENTOS[i % len(_MOVIMENTOS)]
            _clipe(vis, seg_total, clipe, movimento)
        clipes.append(clipe)

    entradas, partes = [], []
    for i, c in enumerate(clipes):
        entradas += ["-i", str(c)]
        partes.append(f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v{i}]")
    atual, offset = "[v0]", 0.0
    for i in range(1, n):
        offset += duracoes[i - 1]
        saida = f"[x{i}]"
        partes.append(
            f"{atual}[v{i}]xfade=transition={_TRANSICOES[i % len(_TRANSICOES)]}"
            f":duration={TRANSICAO}:offset={offset:.3f}{saida}"
        )
        atual = saida
    legenda_esc = str(legenda.resolve()).replace("\\", "/").replace(":", "\\:")
    partes.append(f"{atual}ass='{legenda_esc}'[final]")

    _rodar([
        "ffmpeg", "-y", *entradas, "-i", str(audio),
        "-filter_complex", ";".join(partes), "-map", "[final]", "-map", f"{n}:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
        str(destino),
    ])
    return _limitar_tamanho(destino, pasta)


def _limitar_tamanho(video: Path, pasta: Path, limite_mb: float = 18) -> Path:
    """O Telegram só deixa o bot baixar arquivos de até 20 MB."""
    if video.stat().st_size <= limite_mb * 1024 * 1024:
        return video
    seg = duracao(video)
    kbps = max(int(limite_mb * 8 * 1024 / seg * 0.92) - 160, 500)
    menor = pasta / "short_menor.mp4"
    _rodar([
        "ffmpeg", "-y", "-i", str(video), "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k",
        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(menor),
    ])
    return menor
