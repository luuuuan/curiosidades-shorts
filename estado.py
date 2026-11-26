"""Memória do robô, salva no próprio repositório (pasta estado/).

- estado/roteiros/<id>.json : roteiro de cada vídeo enviado pra aprovação
- estado/diretrizes.md      : regras que você foi ensinando com os pedidos de ajuste
"""
import json
from datetime import datetime
from pathlib import Path

PASTA = Path(__file__).with_name("estado")
ROTEIROS = PASTA / "roteiros"
DIRETRIZES = PASTA / "diretrizes.md"


def novo_id() -> str:
    base = int(datetime.now().strftime("%Y%m%d%H%M%S"))
    while (ROTEIROS / f"{base}.json").exists():
        base += 1
    return str(base)


def salvar_roteiro(video_id: str, roteiro: dict) -> None:
    ROTEIROS.mkdir(parents=True, exist_ok=True)
    (ROTEIROS / f"{video_id}.json").write_text(
        json.dumps(roteiro, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def carregar_roteiro(video_id: str) -> dict | None:
    arquivo = ROTEIROS / f"{video_id}.json"
    if arquivo.exists():
        return json.loads(arquivo.read_text(encoding="utf-8"))
    return None


def titulos_gerados(limite: int = 60) -> list[str]:
    """Títulos já gerados (aprovados ou não), para não repetir tema."""
    if not ROTEIROS.exists():
        return []
    arquivos = sorted(ROTEIROS.glob("*.json"), reverse=True)[:limite]
    titulos = []
    for a in arquivos:
        try:
            titulos.append(json.loads(a.read_text(encoding="utf-8"))["titulo"])
        except (KeyError, json.JSONDecodeError):
            pass
    return titulos


def diretrizes() -> str:
    if not DIRETRIZES.exists():
        return ""
    linhas = [l for l in DIRETRIZES.read_text(encoding="utf-8").splitlines()
              if l.startswith("- ")]
    return "\n".join(linhas)


def adicionar_regra(regra: str) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    if not DIRETRIZES.exists():
        DIRETRIZES.write_text(
            "# Regras do canal\n\nAprendidas com os seus pedidos de ajuste no Telegram. "
            "Pode editar ou apagar linhas à vontade.\n\n", encoding="utf-8"
        )
    with open(DIRETRIZES, "a", encoding="utf-8") as f:
        f.write(f"- {regra.strip()}\n")
