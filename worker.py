// Worker da Cloudflare: recebe os cliques e respostas do Telegram na hora
// e manda o GitHub rodar a revisão ("Revisar respostas do Telegram").
//
// Variáveis (Settings -> Variables and Secrets do Worker):
//   GITHUB_TOKEN        token do GitHub (Contents: Read and write no repositório)
//   GITHUB_REPO         ex.: luuuuan/curiosidades-shorts
//   TELEGRAM_SECRET     senha que o configurar_webhook.py mostra
//   TELEGRAM_CHAT_ID    o mesmo do GitHub
//   TELEGRAM_BOT_TOKEN  o mesmo do GitHub (usado só pra responder o clique na hora)

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Worker do curiosidades-shorts funcionando.");
    }

    // Só aceita chamadas do próprio Telegram (que manda a senha no cabeçalho)
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TELEGRAM_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    const update = await request.json();
    const mensagem = update.callback_query?.message ?? update.message;
    const chat = mensagem?.chat?.id;

    // Ignora qualquer pessoa que não seja você
    if (String(chat) !== String(env.TELEGRAM_CHAT_ID)) {
      return new Response("ignorado");
    }

    // Tira o "carregando" do botão na hora
    if (update.callback_query && env.TELEGRAM_BOT_TOKEN) {
      await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          callback_query_id: update.callback_query.id,
          text: "Recebido! Processando...",
        }),
      });
    }

    // Dispara o workflow no GitHub, levando a mensagem junto
    const resposta = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "curiosidades-shorts-worker",
      },
      body: JSON.stringify({ event_type: "telegram", client_payload: { update } }),
    });

    if (!resposta.ok) {
      // Erro 500 faz o Telegram tentar entregar de novo daqui a pouco
      const detalhe = await resposta.text();
      return new Response(`GitHub ${resposta.status}: ${detalhe}`, { status: 500 });
    }
    return new Response("ok");
  },
};
