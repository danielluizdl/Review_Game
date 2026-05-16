"""
Salva e retoma o progresso de processamento de vídeo.
Evita reprocessar frames já analisados quando o processo é interrompido.
"""
import json
import os

_VERSION = 1


def save_checkpoint(ocr_results: list[dict], checkpoint_path: str) -> None:
    """Salva os resultados OCR acumulados em JSON."""
    os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump({"checkpoint_version": _VERSION, "results": ocr_results},
                  f, ensure_ascii=False)


def load_checkpoint(checkpoint_path: str) -> list[dict] | None:
    """
    Carrega checkpoint se existir e for válido.
    Retorna None se o arquivo não existir ou a versão for incompatível.
    """
    if not os.path.exists(checkpoint_path):
        return None
    try:
        with open(checkpoint_path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("checkpoint_version") != _VERSION:
            return None
        return data["results"]
    except (json.JSONDecodeError, KeyError):
        return None
