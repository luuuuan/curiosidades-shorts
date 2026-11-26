"""Curiosidades Shorts.

    py main.py gerar    -> gera um vídeo e manda pro Telegram (ou posta direto, sem Telegram)
    py main.py revisar  -> lê suas respostas no Telegram: aprova/posta ou refaz com o seu pedido

Com DRY_RUN=true, "gerar" só salva o vídeo na pasta saida/.
"""
import shutil
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import config
import estado
from midia import gerar_imagem, gerar_narracao
from roteiro import extrair_regra, gerar_roteiro
from video import duracao, gerar_legenda, montar_video, tempos_das_cenas


# ------------------------------------------------------------------ produção
def produzir(pasta: Path, titulos: list[str], anterior: dict | None = None,
             feedback: str | None = None) -> tuple[dict, Path]:
    roteiro = gerar_roteiro(titulos, estado.diretrizes(), anterior, feedback)
    cenas = roteiro["cenas"]

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
    palavras = gerar_narracao(texto, audio, roteiro.get("estilo_voz"))
    total = duracao(audio)
    print(f"[main] narração com {total:.1f}s")

    duracoes = tempos_das_cenas(cenas, palavras, total)
    legenda = gerar_legenda(palavras, pasta / "legenda.ass")

    print("[main] montando vídeo...")
    video = montar_video(imagens, duracoes, audio, legenda, pasta / "short.mp4", pasta)
    return roteiro, video


def titulos_existentes(yt=None) -> list[str]:
    titulos = estado.titulos_gerados()
    if yt:
        from youtube_upload import titulos_recentes
        titulos += [t for t in titulos_recentes(yt) if t not in titulos]
    return titulos


def youtube():
    if not config.YOUTUBE_OK:
        raise RuntimeError("Faltam YT_CLIENT_ID, YT_CLIENT_SECRET e YT_REFRESH_TOKEN")
    from youtube_upload import servico
    return servico()


def postar(video: Path, dados: dict) -> str:
    from youtube_upload import enviar
    video_id = enviar(youtube(), video, dados["titulo"], dados["descricao"], dados["tags"])
    return f"https://youtube.com/shorts/{video_id}"


def mandar_pra_aprovacao(roteiro: dict, video: Path, aviso: str = "") -> None:
    import telegram_bot as tg

    vid = estado.novo_id()
    estado.salvar_roteiro(vid, roteiro)
    legenda = (aviso + "\n\n" if aviso else "") + tg.montar_legenda(roteiro, vid)
    tg.enviar_video(video, legenda, tg.botoes(vid))
    print(f"[main] enviado pro Telegram (id {vid})")


# ------------------------------------------------------------------ comandos
def cmd_gerar() -> int:
    yt = youtube() if config.YOUTUBE_OK and not config.DRY_RUN else None
    falhas = 0
    for i in range(config.VIDEOS_POR_EXECUCAO):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                roteiro, video = produzir(Path(tmp), titulos_existentes(yt))

                if config.DRY_RUN:
                    saida = Path("saida")
                    saida.mkdir(exist_ok=True)
                    destino = saida / f"{estado.novo_id()}.mp4"
                    shutil.copy(video, destino)
                    print(f"[main] DRY_RUN: vídeo salvo em {destino}")
                elif config.APROVACAO:
                    mandar_pra_aprovacao(roteiro, video)
                else:
                    estado.salvar_roteiro(estado.novo_id(), roteiro)
                    print(f"[main] postado: {postar(video, roteiro)}")
        except Exception as e:  # noqa: BLE001
            falhas += 1
            traceback.print_exc()
            if config.APROVACAO and not config.DRY_RUN:
                import telegram_bot as tg
                tg.enviar_texto(f"❌ Não consegui gerar o vídeo: {e}")
    return 1 if falhas == config.VIDEOS_POR_EXECUCAO else 0


def _aprovar(cq: dict, vid: str) -> None:
    import telegram_bot as tg

    msg = cq["message"]
    tg.responder_clique(cq["id"], "Postando...")
    tg.trocar_botoes(msg["message_id"], None)
    try:
        dados = estado.carregar_roteiro(vid) or tg.ler_legenda(msg.get("caption", ""))
        with tempfile.TemporaryDirectory() as tmp:
            video = tg.baixar(msg["video"]["file_id"], Path(tmp) / "short.mp4")
            link = postar(video, dados)
        tg.enviar_texto(f"✅ Postado!\n{link}", reply_to=msg["message_id"])
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        tg.trocar_botoes(msg["message_id"], tg.botoes(vid))
        tg.enviar_texto(f"❌ Erro ao postar: {e}\nPode tentar Aprovar de novo.",
                        reply_to=msg["message_id"])


def _pedir_ajuste(cq: dict, vid: str) -> None:
    import telegram_bot as tg

    msg = cq["message"]
    tg.responder_clique(cq["id"], "Me conta o que melhorar")
    tg.trocar_botoes(msg["message_id"], None)
    tg.enviar_texto(
        f"✏️ O que precisa melhorar no vídeo #{vid}?\n"
        "Responda esta mensagem (ex.: 'voz mais calma', 'troca o tema', 'imagens mais realistas').",
        reply_to=msg["message_id"],
        forcar_resposta=True,
    )


def _refazer(vid: str, feedback: str) -> None:
    import telegram_bot as tg

    tg.enviar_texto(f"🔄 Refazendo o vídeo #{vid} com o seu pedido. Já te mando.")
    regra = extrair_regra(feedback)
    if regra:
        estado.adicionar_regra(regra)
        tg.enviar_texto(f"📝 Anotei pra todos os próximos vídeos: {regra}")
    anterior = estado.carregar_roteiro(vid)
    with tempfile.TemporaryDirectory() as tmp:
        roteiro, video = produzir(Path(tmp), titulos_existentes(), anterior, feedback)
        mandar_pra_aprovacao(roteiro, video, aviso=f"🔁 Nova versão do #{vid}")


def _id_do_pedido(texto: str) -> str | None:
    if "#" not in texto:
        return None
    candidato = texto.split("#", 1)[1].split("?", 1)[0].strip()
    return candidato if candidato.isdigit() else None


def cmd_revisar() -> int:
    import telegram_bot as tg

    if not config.APROVACAO:
        print("[revisar] TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID não configurados")
        return 1

    updates = sorted(tg.novidades(), key=lambda u: u["update_id"])
    print(f"[revisar] {len(updates)} novidade(s)")
    for u in updates:
        try:
            cq = u.get("callback_query")
            msg = u.get("message")
            chat = ((cq or {}).get("message") or msg or {}).get("chat", {}).get("id")
            if str(chat) != str(config.TELEGRAM_CHAT_ID):
                continue  # ignora qualquer outra pessoa que fale com o bot

            if cq:
                acao, _, vid = (cq.get("data") or "").partition(":")
                if acao == "ok":
                    _aprovar(cq, vid)
                elif acao == "refazer":
                    _pedir_ajuste(cq, vid)

            elif msg and msg.get("text"):
                texto = msg["text"].strip()
                pergunta = (msg.get("reply_to_message") or {}).get("text", "")
                vid = _id_do_pedido(pergunta)
                if vid:
                    _refazer(vid, texto)
                elif texto.lower() in ("/novo", "/gerar", "novo"):
                    tg.enviar_texto("🎬 Gerando um vídeo novo, já te mando.")
                    cmd_gerar()
                else:
                    tg.enviar_texto(
                        "Use os botões embaixo do vídeo.\n"
                        "Para pedir ajuste, responda a mensagem '✏️ O que precisa melhorar'.\n"
                        "Para um vídeo novo agora, mande /novo."
                    )
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            try:
                tg.enviar_texto(f"❌ Deu erro: {e}")
            except Exception:  # noqa: BLE001
                pass
        finally:
            tg.confirmar_ate(u["update_id"])
    return 0


if __name__ == "__main__":
    comando = sys.argv[1] if len(sys.argv) > 1 else "gerar"
    if comando == "revisar":
        sys.exit(cmd_revisar())
    sys.exit(cmd_gerar())
