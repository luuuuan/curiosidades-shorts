"""Rode UMA VEZ no seu PC para pegar o refresh token do YouTube.

1. Baixe o client_secret.json do Google Cloud (OAuth, tipo "App para computador")
   e coloque nesta pasta.
2. pip install google-auth-oauthlib
3. python get_token.py  -> abre o navegador, entre com a conta do canal.
4. Copie os 3 valores impressos para o Environment do Render.
"""
import json

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

with open("client_secret.json") as f:
    dados = json.load(f)
    dados = dados.get("installed") or dados.get("web")

print("\nCopie para o Render:\n")
print(f"YT_CLIENT_ID={dados['client_id']}")
print(f"YT_CLIENT_SECRET={dados['client_secret']}")
print(f"YT_REFRESH_TOKEN={creds.refresh_token}")
