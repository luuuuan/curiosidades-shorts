"""Comunicação com o bot do Telegram (API oficial de bots).

Para descobrir o seu chat id: mande qualquer mensagem pro bot e rode
    py telegram_bot.py
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import config

TIMEOUT = 120


def _url(metodo: str) -> str:
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{metodo}"


def chamar(metodo: str, **params) -> dict:
    dados = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
             for k, v in params.items() if v is not None}
    req = urllib.request.Request(_url(metodo), data=urllib.parse.urlencode(dados).encode())
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            resposta = json.loads(r.read())
    except urllib.error.HTTPError as e:
        resposta = json.loads(e.read() or b"{}")
    if not resposta.get("ok"):
        raise RuntimeError(f"Telegram {metodo}: {resposta.get('description')}")
    return resposta["result"]


def botoes(video_id: str) -> dict:
    return {"inline_keyboard": [[
        {"text": "✅ Aprovar", "callback_data": f"ok:{video_id}"},
        {"text": "✏️ Refazer", "callback_data": f"refazer:{video_id}"},
    ]]}


def enviar_video(caminho: Path, legenda: str, markup: dict | None = None) -> dict:
    import requests

    dados = {"chat_id": config.TELEGRAM_CHAT_ID, "caption": legenda[:1024],
             "supports_streaming": "true"}
    if markup:
        dados["reply_markup"] = json.dumps(markup)
    with open(caminho, "rb") as f:
        r = requests.post(_url("sendVideo"), data=dados, files={"video": f}, timeout=300)
    resposta = r.json()
    if not resposta.get("ok"):
        raise RuntimeError(f"Telegram sendVideo: {resposta.get('description')}")
    return resposta["result"]


def enviar_texto(texto: str, reply_to: int | None = None, forcar_resposta: bool = False) -> dict:
    return chamar(
        "sendMessage",
        chat_id=config.TELEGRAM_CHAT_ID,
        text=texto,
        reply_to_message_id=reply_to,
        reply_markup={"force_reply": True} if forcar_resposta else None,
        disable_web_page_preview="true",
    )


def trocar_botoes(message_id: int, markup: dict | None) -> None:
    try:
        chamar("editMessageReplyMarkup", chat_id=config.TELEGRAM_CHAT_ID,
               message_id=message_id, reply_markup=markup or {"inline_keyboard": []})
    except RuntimeError as e:
        print(f"[telegram] não consegui trocar os botões: {e}")


def responder_clique(callback_id: str, texto: str) -> None:
    try:
        chamar("answerCallbackQuery", callback_query_id=callback_id, text=texto)
    except RuntimeError:
        pass  # clique antigo demais: o Telegram não aceita mais resposta, sem problema


def baixar(file_id: str, destino: Path) -> Path:
    info = chamar("getFile", file_id=file_id)
    url = f"https://api.telegram.org/file/bot{config.TELEGRAM_BOT_TOKEN}/{info['file_path']}"
    urllib.request.urlretrieve(url, destino)
    return destino


def novidades() -> list[dict]:
    return chamar("getUpdates", timeout=0, allowed_updates=["message", "callback_query"])


def confirmar_ate(update_id: int) -> None:
    """Marca como lido no Telegram tudo até este update."""
    chamar("getUpdates", offset=update_id + 1, timeout=0, limit=1)


# ------------------------------------------------- legenda do vídeo no Telegram
def montar_legenda(roteiro: dict, video_id: str) -> str:
    tags = ", ".join(roteiro.get("tags", []))
    return (f"🎬 {roteiro['titulo']}\n\n{roteiro['descricao']}\n\n"
            f"🏷️ {tags}\nid: {video_id}")


def ler_legenda(legenda: str) -> dict:
    linhas = legenda.splitlines()
    titulo = linhas[0].removeprefix("🎬").strip()
    tags, descricao = [], []
    for linha in linhas[1:]:
        if linha.startswith("🏷️"):
            tags = [t.strip() for t in linha.removeprefix("🏷️").split(",") if t.strip()]
        elif linha.startswith("id: "):
            continue
        elif linha.strip():
            descricao.append(linha.strip())
    return {"titulo": titulo, "descricao": " ".join(descricao), "tags": tags}


if __name__ == "__main__":
    vistos = set()
    for u in novidades():
        chat = (u.get("message") or u.get("callback_query", {}).get("message") or {}).get("chat")
        if chat and chat["id"] not in vistos:
            vistos.add(chat["id"])
            nome = chat.get("first_name") or chat.get("title") or ""
            print(f"TELEGRAM_CHAT_ID={chat['id']}   ({nome})")
    if not vistos:
        print("Nenhuma mensagem encontrada. Mande um 'oi' pro bot e rode de novo.")
