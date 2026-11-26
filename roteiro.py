"""Gera o roteiro e faz uma segunda passada checando os fatos.

LLM_PROVIDER=gemini (padrão, tem camada grátis) ou claude (pago).
"""
import json

import config

PROMPT_ROTEIRO = """Você escreve roteiros de YouTube Shorts de CURIOSIDADES em português do Brasil.

Regras:
- Um único fato ou curiosidade surpreendente, VERDADEIRO e bem documentado. Nada de lenda
  urbana, "dizem que", estatística inventada ou exagero. Na dúvida, escolha outro tema.
- Evite saúde/medicina, política, religião, tragédias recentes e pessoas reais vivas.
- Varie a área: ciência, animais, espaço, história, geografia, corpo humano (sem conselho
  médico), tecnologia, idiomas, comida, objetos do dia a dia.
- Narração total entre 110 e 140 palavras (uns 45 a 55 segundos).
- A primeira cena é o gancho: uma frase curta que prende nos 2 primeiros segundos.
- A última cena fecha a explicação e termina com um convite curto para seguir o canal.
- Linguagem falada, frases curtas, sem emoji, sem hashtag na narração.
- Entre 5 e 7 cenas. Cada cena tem a narração e um prompt de imagem EM INGLÊS: imagem vertical,
  cinematográfica, detalhada, SEM texto escrito, sem logotipos, sem pessoas famosas.
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
    {{"narracao": "texto falado da cena", "prompt_imagem": "english image prompt"}}
  ]
}}"""

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
    if not 4 <= len(r["cenas"]) <= 8:
        raise ValueError(f"{len(r['cenas'])} cenas (esperado 5 a 7)")
    palavras = sum(len(c["narracao"].split()) for c in r["cenas"])
    if not 90 <= palavras <= 170:
        raise ValueError(f"Narração com {palavras} palavras")


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
                  tentativas: int = 4) -> dict:
    if anterior:
        titulos_anteriores = [t for t in titulos_anteriores if t != anterior.get("titulo")]
    anteriores = "\n".join(f"- {t}" for t in titulos_anteriores) or "(nenhum ainda)"
    extras = _extras(diretrizes, anterior, feedback)
    ultimo_erro = None
    for n in range(1, tentativas + 1):
        try:
            roteiro = _perguntar(PROMPT_ROTEIRO.format(anteriores=anteriores, extras=extras))
            _validar(roteiro)
            checagem = _perguntar(
                PROMPT_CHECAGEM.format(roteiro=json.dumps(roteiro, ensure_ascii=False))
            )
            if checagem.get("aprovado"):
                print(f"[roteiro] aprovado: {roteiro['titulo']}")
                return roteiro
            ultimo_erro = f"reprovado na checagem: {checagem.get('problemas')}"
        except (ValueError, KeyError, TypeError) as e:
            ultimo_erro = str(e)
        print(f"[roteiro] tentativa {n} descartada: {ultimo_erro}")
    raise RuntimeError(f"Não consegui um roteiro aprovado: {ultimo_erro}")
