"""Pipeline completo: roteiro -> imagens -> narração -> vídeo -> YouTube Shorts."""
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import config
from midia import gerar_imagem, gerar_narracao
from roteiro import gerar_roteiro
from video import duracao, gerar_legenda, montar_video, tempos_das_cenas


def produzir(yt, titulos_anteriores: list[str]) -> str:
    roteiro = gerar_roteiro(titulos_anteriores)
    cenas = roteiro["cenas"]

    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)

        print(f"[main] gerando {len(cenas)} imagens...")
        paralelo = 4 if config.IMAGE_PROVIDER == "openai" or config.POLLINATIONS_KEY else 1
        with ThreadPoolExecutor(max_workers=paralelo) as ex:
            imagens = list(ex.map(
                lambda par: gerar_imagem(par[1]["prompt_imagem"], pasta / f"cena_{par[0]:02d}.png"),
                enumerate(cenas),
            ))

        print("[main] gerando narração...")
        texto = " ".join(c["narracao"].strip() for c in cenas)
        audio = pasta / "narracao.mp3"
        palavras = gerar_narracao(texto, audio)
        total = duracao(audio)
        print(f"[main] narração com {total:.1f}s")

        duracoes = tempos_das_cenas(cenas, palavras, total)
        legenda = gerar_legenda(palavras, pasta / "legenda.ass")

        print("[main] montando vídeo...")
        video = montar_video(imagens, duracoes, audio, legenda, pasta / "short.mp4", pasta)

        if config.DRY_RUN:
            saida = Path("saida")
            saida.mkdir(exist_ok=True)
            nome = saida / f"{datetime.now():%Y%m%d_%H%M%S}.mp4"
            shutil.copy(video, nome)
            print(f"[main] DRY_RUN: vídeo salvo em {nome}")
            return roteiro["titulo"]

        from youtube_upload import enviar
        video_id = enviar(yt, video, roteiro["titulo"], roteiro["descricao"], roteiro["tags"])
        print(f"[main] postado: https://youtube.com/shorts/{video_id}")
        return roteiro["titulo"]


def main() -> int:
    yt = None
    titulos: list[str] = []
    if not config.DRY_RUN:
        from youtube_upload import servico, titulos_recentes
        yt = servico()
        titulos = titulos_recentes(yt)

    falhas = 0
    for i in range(config.VIDEOS_POR_EXECUCAO):
        try:
            titulos.insert(0, produzir(yt, titulos))
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print(f"[main] vídeo {i + 1} falhou: {e}", file=sys.stderr)
    return 1 if falhas == config.VIDEOS_POR_EXECUCAO else 0


if __name__ == "__main__":
    sys.exit(main())
