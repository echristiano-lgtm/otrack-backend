import json
import os
from typing import Dict

DB_FILE = os.environ.get("MEOS_DB", "events.json")

def load_db() -> Dict[str, dict]:
    """Carrega o banco (dict de eventos) do arquivo JSON."""
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            # Se por algum motivo não for dict, retorna vazio
            return {}
    except Exception:
        # Arquivo corrompido ou inválido → começa vazio
        return {}

def save_db(db: Dict[str, dict]) -> None:
    """Salva o banco no arquivo JSON."""
    # Garante existência do diretório, se definido um caminho com pastas
    os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False)

