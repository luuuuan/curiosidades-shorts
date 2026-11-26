"""Monta o Short (1080x1920) com FFmpeg: imagens com zoom, narração e legenda."""
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


def _clipe(imagem: Path, segundos: float, destino: Path, zoom_in: bool) -> None:
    frames = max(int(round(segundos * FPS)), 1)
    if zoom_in:
        z = "min(1+0.18*on/{f},1.18)".format(f=frames)
    else:
        z = "max(1.18-0.18*on/{f},1)".format(f=frames)
    filtro = (
        f"scale={LARGURA * 2}:{ALTURA * 2}:force_original_aspect_ratio=increase,"
        f"crop={LARGURA * 2}:{ALTURA * 2},"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={LARGURA}x{ALTURA}:fps={FPS},setsar=1,format=yuv420p"
    )
    _rodar([
        "ffmpeg", "-y", "-i", str(imagem), "-vf", filtro, "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(destino),
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


def montar_video(imagens: list[Path], duracoes: list[float], audio: Path,
                 legenda: Path, destino: Path, pasta: Path) -> Path:
    clipes = []
    for i, (img, seg) in enumerate(zip(imagens, duracoes)):
        clipe = pasta / f"clipe_{i:02d}.mp4"
        _clipe(img, seg, clipe, zoom_in=(i % 2 == 0))
        clipes.append(clipe)

    lista = pasta / "clipes.txt"
    lista.write_text("".join(f"file '{c.resolve()}'\n" for c in clipes))
    sem_audio = pasta / "sem_audio.mp4"
    _rodar(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
            "-c", "copy", str(sem_audio)])

    legenda_esc = str(legenda.resolve()).replace("\\", "/").replace(":", "\\:")
    _rodar([
        "ffmpeg", "-y", "-i", str(sem_audio), "-i", str(audio),
        "-vf", f"ass='{legenda_esc}'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
        str(destino),
    ])
    return destino
