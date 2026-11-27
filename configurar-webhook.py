"""Liga (ou desliga) o Telegram ao Worker da Cloudflare.

Ligar:      py configurar_webhook.py https://SEU-WORKER.workers.dev
Ver status: py configurar_webhook.py
Desligar:   py configurar_webhook.py --desligar   (volta pro modo de 15 em 15 min)

Precisa do TELEGRAM_BOT_TOKEN no .env.
"""
import secrets
import sys

import telegram_bot as tg

args = sys.argv[1:]

if not args:
    info = tg.chamar("getWebhookInfo")
    print(f"Webhook: {info.get('url') or '(desligado: modo de 15 em 15 min)'}")
    print(f"Mensagens esperando: {info.get('pending_update_count', 0)}")
    if info.get("last_error_message"):
        print(f"Último erro: {info['last_error_message']}")

elif args[0] == "--desligar":
    tg.chamar("deleteWebhook")
    print("Webhook desligado. O robô volta a conferir o Telegram de 15 em 15 minutos.")

else:
    url = args[0].rstrip("/")
    if not url.startswith("https://"):
        sys.exit("O endereço do Worker precisa começar com https://")
    senha = secrets.token_urlsafe(32)
    tg.chamar(
        "setWebhook",
        url=url,
        secret_token=senha,
        allowed_updates=["message", "callback_query"],
    )
    print("Webhook ligado!\n")
    print("Agora, no Worker da Cloudflare (Settings -> Variables and Secrets), crie:")
    print(f"  TELEGRAM_SECRET = {senha}\n")
    print("Sem isso o Worker recusa as mensagens (o Telegram tenta de novo depois).")
