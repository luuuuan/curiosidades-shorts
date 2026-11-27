# Curiosidades Shorts

Gera e posta Shorts de curiosidades sozinho, de graça, rodando no GitHub Actions.

**Fluxo:** Gemini escreve o roteiro → uma segunda chamada checa os fatos → Cloudflare (FLUX)
gera as imagens, com fotos do Pexels de reserva → Gemini TTS narra em pt-BR → Whisper marca o tempo de cada palavra → FFmpeg monta
o vídeo vertical com zoom e legenda → **manda pra você aprovar no Telegram** → se aprovar,
posta no YouTube; se pedir ajuste, refaz com o seu pedido e manda de novo.

Cada pedido de ajuste que vale pra todos os vídeos (ex.: "voz mais calma") vira uma regra
em `estado/diretrizes.md`, e os próximos roteiros já seguem. Pode editar esse arquivo à vontade.

O canal não repete tema: antes de cada vídeo, o script lê os últimos títulos do canal.
Se a voz do Gemini falhar ou bater o limite, o edge-tts entra no lugar automaticamente.

## 1. Chaves

- **Gemini (grátis):** aistudio.google.com → Get API key → Create API key. Serve para o
  roteiro e para a voz.
- **Cloudflare (imagens por IA, grátis):** crie conta em dash.cloudflare.com.
  - `CLOUDFLARE_ACCOUNT_ID`: aparece em **Workers AI** (ou na barra lateral, "Account ID").
  - `CLOUDFLARE_API_TOKEN`: **Workers AI → Use REST API → Create a Workers AI API Token**.
- **Pexels (fotos reais, grátis, reserva):** crie conta em pexels.com/api e peça a chave
  (`PEXELS_API_KEY`). Quando o vídeo usa foto do Pexels, o crédito entra na descrição.
- **Clipes de vídeo reais (opcional, grátis):** crie conta em pixabay.com, pegue a chave em
  pixabay.com/api/docs e salve como `PIXABAY_API_KEY`. As cenas que dão pra filmar viram
  vídeo de verdade; o resto continua imagem de IA com movimento. Sem a chave, só imagens.

Precisa de pelo menos uma das duas fontes de imagem; com as duas, se uma falhar, a outra assume.

## 2. YouTube (feito uma vez só)

1. Crie o canal no YouTube.
2. No console.cloud.google.com, crie um projeto e ative a **YouTube Data API v3**.
3. Em **Tela de consentimento OAuth**: tipo Externo, adicione o seu e-mail e depois clique
   em **Publicar app** (status "Em produção"). Se ficar em "Teste", o token expira
   em 7 dias e o robô para de postar.
4. Em **Credenciais**, crie um ID do cliente OAuth do tipo **App para computador** e baixe o
   JSON como `client_secret.json` nesta pasta.
5. No seu PC:
   ```
   py get_token.py
   ```
   Entre com a conta do canal (vai aparecer o aviso "app não verificado": clique em
   Avançado → continuar). O script imprime `YT_CLIENT_ID`, `YT_CLIENT_SECRET` e
   `YT_REFRESH_TOKEN`.

### ⚠️ Vídeos ficam privados no começo
Projeto novo da API do YouTube **não verificado** só consegue postar vídeo como
**privado**. Para liberar o público, peça a auditoria pelo formulário
"YouTube API Services - Audit and Quota Extension Form". Enquanto ela não sai, os vídeos
sobem privados e você pode deixar públicos manualmente no YouTube Studio.

## 3. Testar no PC

Precisa de FFmpeg instalado. Crie um arquivo `.env` na pasta:
```
GEMINI_API_KEY=sua-chave
DRY_RUN=true
```
E rode:
```
py -m pip install -r requirements.txt
py main.py
```
O vídeo sai na pasta `saida/` sem postar nada.

Opcional: `py -m pip install faster-whisper` deixa a legenda sincronizada certinha. Sem ele
a legenda usa um tempo estimado (fica um pouco menos precisa). No GitHub Actions ele já é
instalado automaticamente.

## 4. Bot do Telegram

1. No Telegram, abra o **@BotFather**, mande `/newbot`, escolha um nome e um usuário
   (tem que terminar em `bot`). Ele te dá o **token** → é o `TELEGRAM_BOT_TOKEN`.
2. Abra o seu bot e mande um "oi" pra ele.
3. No PC, coloque o token no `.env` (`TELEGRAM_BOT_TOKEN=...`) e rode:
   ```
   py telegram_bot.py
   ```
   Ele mostra o `TELEGRAM_CHAT_ID`. O bot só obedece a esse chat; qualquer outra pessoa
   que falar com ele é ignorada.

**Como usar:** o vídeo chega com os botões ✅ **Aprovar** e ✏️ **Refazer**.
- Aprovar → ele posta e te manda o link.
- Refazer → ele pergunta o que melhorar; responda aquela mensagem com o seu pedido.
- Mande `/novo` a qualquer hora para gerar um vídeo extra.

O robô confere suas respostas a cada 15 minutos, então depois de clicar pode levar até uns
15 min (mais o tempo de gerar, no caso de refazer). Vídeo sem resposta fica esperando: nada
é postado sem a sua aprovação.

Sem `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, o robô posta direto, sem aprovação.

**Testar no PC:** com `DRY_RUN=false` e as variáveis do Telegram no `.env`,
`py main.py gerar` manda o vídeo pro Telegram e `py main.py revisar` processa o que você
respondeu.

## 5. Deixar rodando no GitHub Actions (grátis)

1. Crie um repositório **público** no GitHub e suba esta pasta.
   O `.gitignore` já deixa de fora o `.env` e o `client_secret.json`, então nenhuma chave
   vai junto. Público porque em repositório público o Actions é grátis e sem limite de minutos.
2. No repositório: **Settings → Secrets and variables → Actions → New repository secret**.
   Crie um para cada:
   - `GEMINI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `YT_CLIENT_ID`
   - `YT_CLIENT_SECRET`
   - `YT_REFRESH_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID` e `CLOUDFLARE_API_TOKEN`
   - `PEXELS_API_KEY`
   - `PIXABAY_API_KEY`
3. Aba **Actions** → libere os workflows se o GitHub pedir.
4. Para testar na hora: **Actions → Gerar Short → Run workflow**. Clique na execução para
   ver o log. Em poucos minutos o vídeo chega no Telegram.

São dois agendamentos:
- **Gerar Short** (`gerar.yml`): gera um vídeo às 11h e às 19h (Brasília) e manda pro
  Telegram. Para mudar, edite o `cron` (o horário é em UTC: Brasília + 3h).
- **Revisar respostas do Telegram** (`revisar.yml`): a cada 15 min vê se você respondeu.
  Se não tiver nada novo, termina em segundos.

Os workflows salvam os roteiros e as regras na pasta `estado/` com commits automáticos.
Isso também evita que o GitHub pause o agendamento (ele pausa repositório parado há 60 dias).

> O agendamento do GitHub pode atrasar alguns minutos em horário de pico. É normal.

## 6. Resposta na hora (Worker da Cloudflare)

Sem isso, o robô confere o Telegram de 15 em 15 minutos. Com o Worker, cada clique ou
resposta dispara a revisão na hora.

1. **Token do GitHub:** GitHub → Settings (do perfil) → Developer settings → Personal access
   tokens → **Fine-grained tokens** → Generate new token. Repository access: só este
   repositório. Permissions → Repository → **Contents: Read and write**. Copie o token.
2. **Worker:** no painel da Cloudflare, Compute → **Workers & Pages** → Create → Start with
   Hello World → Deploy. Depois **Edit code**, apague tudo, cole o conteúdo de
   `cloudflare-worker/worker.js` e clique em **Deploy**. Anote o endereço
   (`https://....workers.dev`).
3. **Variáveis do Worker** (Settings → Variables and Secrets, tipo Secret):
   `GITHUB_TOKEN`, `GITHUB_REPO` (ex.: `luuuuan/curiosidades-shorts`), `TELEGRAM_CHAT_ID`,
   `TELEGRAM_BOT_TOKEN`.
4. **Ligar o Telegram ao Worker** (no PC, com o `TELEGRAM_BOT_TOKEN` no `.env`):
   ```
   py configurar_webhook.py https://SEU-WORKER.workers.dev
   ```
   Ele mostra uma senha: crie a variável `TELEGRAM_SECRET` no Worker com ela.
5. Teste: clique em um botão no Telegram. Deve aparecer "Recebido! Processando..." e uma
   execução nova em Actions → Revisar respostas do Telegram.

`py configurar_webhook.py` mostra o status (e o último erro, se houver).
`py configurar_webhook.py --desligar` volta para o modo de 15 em 15 minutos.

## Ajustes (no `.env` ou no workflow)

| Variável | Padrão | O que faz |
|---|---|---|
| `GEMINI_TTS_VOICE` | Puck | Voz: Puck, Charon, Kore, Fenrir, Orus, Aoede, Zephyr, Leda... |
| `GEMINI_TTS_STYLE` | narrador animado | Jeito de falar (em inglês funciona melhor) |
| `GEMINI_TTS_MODEL` | gemini-3.8-flash-tts | Ou gemini-3.8-flash-lite-tts |
| `GEMINI_MODEL` | gemini-flash-latest | Modelo do roteiro |
| `VIDEOS_POR_EXECUCAO` | 1 | Vídeos por execução |
| `YT_PRIVACY` | public | public, unlisted ou private |
| `TTS_PROVIDER` | gemini | gemini, edge ou openai |
| `IMAGE_PROVIDER` | cloudflare,pexels | Ordem das fontes de imagem |
| `LLM_PROVIDER` | gemini | gemini ou claude |

**Limite do YouTube:** a cota padrão da API (10.000 unidades/dia) dá uns 6 uploads por dia.
Começar com 1 ou 2 por dia é o ideal até ver o que performa.

## Alternativa: Render
O `Dockerfile` e o `render.yaml` continuam na pasta, caso prefira rodar como Cron Job no
Render (pago, mínimo de US$ 1/mês). Ele está configurado só para o modo sem aprovação;
para usar o Telegram no Render seria preciso um segundo cron job rodando `python main.py revisar`.

## Boas práticas para não perder monetização
- O roteiro é único a cada vídeo e passa por checagem de fatos. Não tire essa etapa.
- O upload já marca o vídeo como conteúdo sintético (IA), como o YouTube exige.
- De vez em quando, assista aos vídeos e ajuste o prompt em `roteiro.py`. Um canal que
  evolui não parece fábrica de vídeo.
