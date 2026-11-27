"""Gera o roteiro e faz uma segunda passada checando os fatos.

LLM_PROVIDER=gemini (padrão, tem camada grátis) ou claude (pago).
"""
import json
import random

import config

PROMPT_ROTEIRO = """Você escreve roteiros de YouTube Shorts de CURIOSIDADES em português do Brasil.

Regras:
- Um único fato ou curiosidade surpreendente, VERDADEIRO e bem documentado. Nada de lenda
  urbana, "dizem que", estatística inventada ou exagero. Na dúvida, escolha outro tema.
- Evite saúde/medicina, política, religião, tragédias recentes e pessoas reais vivas.
- Varie a área: ciência, animais, espaço, história, geografia, corpo humano (sem conselho
  médico), tecnologia, idiomas, comida, objetos do dia a dia.
- TAMANHO: narração total entre 75 e 105 palavras (uns 30 a 40 segundos). A cena 1 (gancho)
  é curta, mas CADA UMA das outras cenas precisa ter de 18 a 25 palavras. Conte antes de
  responder: menos de 75 palavras no total é rejeitado.
- FORMATO deste vídeo: {formato}
- GANCHO (cena 1): no máximo 12 palavras, já com a parte mais chocante do fato. Proibido
  começar com 'Você sabia', 'Olá', 'Hoje', 'Neste vídeo', 'Vamos' ou qualquer apresentação.
  Bons exemplos: 'Existe um animal que nunca morre de velhice.' / 'O Brasil já teve dois
  imperadores e nenhum nasceu aqui.'
- Cada cena seguinte traz uma informação nova que aumenta a curiosidade; nada de repetir.
- FINAL EM LOOP: a última frase deve emendar naturalmente com a primeira, como se o vídeo
  recomeçasse (ex.: termina com '...e é por isso que' e o gancho completa a ideia). NÃO
  termine pedindo para seguir, curtir ou comentar.
- Linguagem falada, frases curtas, sem emoji, sem hashtag na narração.
- Entre 4 e 6 cenas. Cada cena tem a narração e um prompt de imagem EM INGLÊS: imagem vertical,
  cinematográfica, detalhada, SEM texto escrito, sem logotipos, sem pessoas famosas.
- Em cada cena escolha o "visual":
  "video" quando dá para mostrar com uma filmagem real e genérica de banco de vídeos
  (natureza, animais, oceano, espaço, cidade, comida, pessoas fazendo algo comum, objetos);
  "imagem" quando a cena é específica demais, histórica, impossível de filmar ou precisa de
  ilustração. Use "video" em pelo menos metade das cenas quando o tema permitir.
- Dentro dos textos, use aspas simples (') em vez de aspas duplas.

NÃO repita nenhum destes temas já publicados:
{anteriores}
{extras}
Responda SOMENTE com JSON válido neste formato:
{{
  "tema": "resumo do tema em poucas palavras",
  "titulo": "título chamativo, até 70 caracteres, sem hashtag",
  "descricao": "2 ou 3 frases explicando o fato",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "estilo_voz": "how the narrator should sound, IN ENGLISH (energy, pace, tone)",
  "cenas": [
    {{"narracao": "texto falado da cena", "visual": "video ou imagem",
      "prompt_imagem": "english image prompt",
      "busca": "2-3 simple english keywords to find real stock footage of this scene"}}
  ]
}}"""

FORMATOS = [
    "FATO ÚNICO: um fato surpreendente explicado do gancho ao porquê.",
    "3 FATOS: três curiosidades curtas sobre o mesmo assunto, da menos para a mais chocante.",
    "MITO OU VERDADE: uma crença popular, o suspense e a resposta com o fato real.",
    "E SE...: o que aconteceria se algo mudasse, usando só ciência real e bem aceita.",
    "ORIGEM: de onde veio algo do dia a dia (palavra, objeto, costume) — história verificada.",
    "COMPARAÇÃO: dois números ou tamanhos reais comparados de um jeito visual e surpreendente.",
]

PROMPT_CHECAGEM = """Você é um checador de fatos rigoroso. Verifique se TODAS as afirmações do
roteiro abaixo são verdadeiras, precisas e bem estabelecidas (sem exagero, sem número errado,
sem mito popular apresentado como fato).

Roteiro:
{roteiro}

Responda SOMENTE com JSON válido: {{"aprovado": true ou false, "problemas": ["..."]}}"""


def _extrair_json(texto: str) -> dict:
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fim == -1:
        raise ValueError("Resposta sem JSON")
    try:
        return json.loads(texto[inicio : fim + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido: {e}") from e


# ---------------------------------------------------------------- Gemini
def _gemini(prompt: str) -> str:
    import gemini

    return gemini.texto(prompt)


# ---------------------------------------------------------------- Claude
def _claude(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def _perguntar(prompt: str) -> dict:
    texto = _claude(prompt) if config.LLM_PROVIDER == "claude" else _gemini(prompt)
    return _extrair_json(texto)


def _validar(r: dict) -> None:
    for campo in ("tema", "titulo", "descricao", "tags", "cenas"):
        if campo not in r:
            raise ValueError(f"Roteiro sem o campo {campo}")
    if not 3 <= len(r["cenas"]) <= 7:
        raise ValueError(f"{len(r['cenas'])} cenas (esperado 4 a 6)")
    palavras = sum(len(c["narracao"].split()) for c in r["cenas"])
    if not 55 <= palavras <= 125:
        raise ValueError(f"Narração com {palavras} palavras")
    gancho = len(r["cenas"][0]["narracao"].split())
    if gancho > 16:
        raise ValueError(f"Gancho com {gancho} palavras (máximo 12)")
    inicio = r["cenas"][0]["narracao"].strip().lower()
    for proibido in ("você sabia", "voce sabia", "olá", "ola,", "hoje", "neste vídeo", "vamos"):
        if inicio.startswith(proibido):
            raise ValueError(f"Gancho começa com '{proibido}'")


def _extras(diretrizes: str, anterior: dict | None, feedback: str | None) -> str:
    partes = []
    if diretrizes:
        partes.append(
            "\nREGRAS DA DONA DO CANAL (têm prioridade sobre as regras acima):\n" + diretrizes
        )
    if anterior and feedback:
        partes.append(
            "\nESTE É UM ROTEIRO REFEITO. Versão anterior, que foi reprovada:\n"
            + json.dumps(anterior, ensure_ascii=False)
            + f"\n\nPedido de ajuste da dona do canal: {feedback}\n"
            "Atenda exatamente ao pedido. Mantenha o mesmo tema, a não ser que o pedido "
            "diga para trocar. Se o pedido for sobre a voz, ajuste o campo estilo_voz."
        )
    return "\n".join(partes) + "\n" if partes else ""


def extrair_regra(feedback: str) -> str | None:
    """Transforma um pedido de ajuste em regra permanente, se ele valer pra todos os vídeos."""
    prompt = (
        "A dona de um canal de Shorts de curiosidades deu este pedido de ajuste sobre um "
        f"vídeo:\n\n\"{feedback}\"\n\nSe o pedido traz uma preferência que deve valer para "
        "TODOS os próximos vídeos (estilo do texto, ritmo, voz, visual das imagens, tipo de "
        "tema, tamanho), reescreva como uma regra curta e geral em português. Se for algo só "
        "deste vídeo (trocar este tema específico, corrigir um fato deste vídeo), deixe vazio."
        '\n\nResponda SOMENTE com JSON: {"regra": "texto da regra ou vazio"}'
    )
    try:
        regra = (_perguntar(prompt).get("regra") or "").strip()
    except Exception as e:  # noqa: BLE001
        print(f"[roteiro] não consegui extrair regra: {e}")
        return None
    return regra or None


def gerar_roteiro(titulos_anteriores: list[str], diretrizes: str = "",
                  anterior: dict | None = None, feedback: str | None = None,
                  tentativas: int = 5) -> dict:
    if anterior:
        titulos_anteriores = [t for t in titulos_anteriores if t != anterior.get("titulo")]
    anteriores = "\n".join(f"- {t}" for t in titulos_anteriores) or "(nenhum ainda)"
    extras = _extras(diretrizes, anterior, feedback)
    formato = random.choice(FORMATOS)
    if anterior and anterior.get("formato"):
        formato = next((f for f in FORMATOS if f.startswith(anterior["formato"].upper())), formato)
    print(f"[roteiro] formato: {formato.split(':')[0]}")
    ultimo_erro = None
    correcao = ""
    for n in range(1, tentativas + 1):
        try:
            roteiro = _perguntar(
                PROMPT_ROTEIRO.format(anteriores=anteriores, extras=extras, formato=formato) + correcao
            )
            _validar(roteiro)
            checagem = _perguntar(
                PROMPT_CHECAGEM.format(roteiro=json.dumps(roteiro, ensure_ascii=False))
            )
            if checagem.get("aprovado"):
                roteiro["formato"] = formato.split(":")[0]
                print(f"[roteiro] aprovado: {roteiro['titulo']}")
                return roteiro
            ultimo_erro = f"reprovado na checagem: {checagem.get('problemas')}"
            correcao = (
                "\n\nATENÇÃO: o roteiro anterior foi reprovado na checagem de fatos por isto: "
                f"{checagem.get('problemas')}. Escolha um fato sólido e sem polêmica.\n"
            )
        except (ValueError, KeyError, TypeError) as e:
            ultimo_erro = str(e)
            if ultimo_erro.startswith("Narração"):
                correcao = (
                    f"\n\nATENÇÃO: a versão anterior saiu com {ultimo_erro.split()[2]} palavras. "
                    "A narração TOTAL (somando todas as cenas) precisa ter entre 75 e 105 "
                    "palavras. Mantenha o gancho curto, mas escreva 4 ou 5 cenas depois dele "
                    "com 18 a 25 palavras CADA, trazendo mais detalhes do fato.\n"
                )
            elif ultimo_erro.startswith("Gancho"):
                correcao = (
                    f"\n\nATENÇÃO: a versão anterior foi descartada: {ultimo_erro}. A cena 1 "
                    "precisa ter no máximo 12 palavras e ir direto ao fato chocante.\n"
                )
        print(f"[roteiro] tentativa {n} descartada: {ultimo_erro}")
    raise RuntimeError(f"Não consegui um roteiro aprovado: {ultimo_erro}")
