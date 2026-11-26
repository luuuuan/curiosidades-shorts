"""Upload para o YouTube pela API oficial (YouTube Data API v3)."""
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def servico():
    creds = Credentials(
        None,
        refresh_token=config.YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.YT_CLIENT_ID,
        client_secret=config.YT_CLIENT_SECRET,
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def titulos_recentes(yt, limite: int = 50) -> list[str]:
    """Títulos já postados no canal, para o Claude não repetir tema."""
    canal = yt.channels().list(part="contentDetails", mine=True).execute()
    if not canal.get("items"):
        return []
    uploads = canal["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    try:
        r = yt.playlistItems().list(
            part="snippet", playlistId=uploads, maxResults=min(limite, 50)
        ).execute()
    except Exception:  # canal sem nenhum vídeo ainda
        return []
    return [i["snippet"]["title"] for i in r.get("items", [])]


def enviar(yt, video: Path, titulo: str, descricao: str, tags: list[str]) -> str:
    titulo_final = f"{titulo} #shorts"[:100]
    descricao_final = (
        f"{descricao}\n\n#curiosidades #vocesabia #shorts\n\n"
        "Vídeo produzido com auxílio de inteligência artificial."
    )
    corpo = {
        "snippet": {
            "title": titulo_final,
            "description": descricao_final,
            "tags": tags[:15],
            "categoryId": "27",  # Educação
            "defaultLanguage": "pt-BR",
            "defaultAudioLanguage": "pt-BR",
        },
        "status": {
            "privacyStatus": config.YT_PRIVACY,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }
    req = yt.videos().insert(
        part="snippet,status",
        body=corpo,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4",
                                   chunksize=-1, resumable=True),
    )
    resposta = None
    while resposta is None:
        _, resposta = req.next_chunk()
    return resposta["id"]
