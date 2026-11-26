# Curiosidades Shorts

Gera e posta Shorts de curiosidades sozinho, de graça, rodando no GitHub Actions.

**Fluxo:** Gemini escreve o roteiro → uma segunda chamada checa os fatos → Pollinations gera
as imagens → Gemini TTS narra em pt-BR → Whisper marca o tempo de cada palavra → FFmpeg monta
o vídeo vertical com zoom e legenda → YouTube Data API posta como Short.

O canal não repete tema: antes de cada vídeo, o script lê os últimos títulos do canal.
Se a voz do Gemini falhar ou bater o limite, o edge-tts entra no lugar automaticamente.

## 1. Chaves

- **Gemini (grátis):** aistudio.google.com → Get API key → Create API key. Serve para o
  roteiro e para a voz.
- **Pollinations (opcional):** sem chave funciona, com limite de 1 imagem a cada 15s.
  Uma chave grátis em enter.pollinations.ai tira esse limite (`POLLINATIONS_KEY`).

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

## 4. Deixar rodando no GitHub Actions (grátis)

1. Crie um repositório **público** no GitHub e suba esta pasta.
   O `.gitignore` já deixa de fora o `.env` e o `client_secret.json`, então nenhuma chave
   vai junto. Público porque em repositório público o Actions é grátis e sem limite de minutos.
2. No repositório: **Settings → Secrets and variables → Actions → New repository secret**.
   Crie um para cada:
   - `GEMINI_API_KEY`
   - `YT_CLIENT_ID`
   - `YT_CLIENT_SECRET`
   - `YT_REFRESH_TOKEN`
   - `POLLINATIONS_KEY` (opcional)
3. Aba **Actions** → libere os workflows se o GitHub pedir.
4. Para testar na hora: **Actions → Postar Short → Run workflow**. Clique na execução para
   ver o log.

Depois disso ele roda sozinho às 11h e às 19h (horário de Brasília). Para mudar, edite o
`cron` em `.github/workflows/shorts.yml` (o horário é em UTC: Brasília + 3h).

O GitHub pausa agendamentos de repositório parado há 60 dias. O workflow já faz um commit
automático a cada execução para isso não acontecer.

> O agendamento do GitHub pode atrasar alguns minutos em horário de pico. É normal.

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
| `IMAGE_PROVIDER` | pollinations | pollinations ou openai |
| `LLM_PROVIDER` | gemini | gemini ou claude |

**Limite do YouTube:** a cota padrão da API (10.000 unidades/dia) dá uns 6 uploads por dia.
Começar com 1 ou 2 por dia é o ideal até ver o que performa.

## Alternativa: Render
O `Dockerfile` e o `render.yaml` continuam na pasta, caso prefira rodar como Cron Job no
Render (pago, mínimo de US$ 1/mês).

## Boas práticas para não perder monetização
- O roteiro é único a cada vídeo e passa por checagem de fatos. Não tire essa etapa.
- O upload já marca o vídeo como conteúdo sintético (IA), como o YouTube exige.
- De vez em quando, assista aos vídeos e ajuste o prompt em `roteiro.py`. Um canal que
  evolui não parece fábrica de vídeo.
