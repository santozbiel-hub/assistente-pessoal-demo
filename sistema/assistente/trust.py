"""
Modulo de confianca progressiva da ASSISTENTE.
Cada arquivo tem um score baseado em aprovacoes/rejeicoes.
Conforme ASSISTENTE acerta, ela ganha autonomia.
Conforme erra, perde confianca.
"""

import json
from pathlib import Path
from datetime import datetime
from assistente import config


# Arquivo onde guardamos o score
TRUST_FILE = config.VAULT_PATH / "5-Memory" / ".trust-score.json"


# Limiares de progressao
THRESHOLD_TO_INTERMEDIATE = 5   # 5 aprovacoes = aprovacao simples
THRESHOLD_TO_AUTONOMOUS = 10    # 10 aprovacoes = escreve direto


def load_scores() -> dict:
    """Carrega scores do arquivo. Cria vazio se nao existir."""
    if not TRUST_FILE.exists():
        return {}

    try:
        with open(TRUST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_scores(scores: dict) -> None:
    """Salva scores no arquivo."""
    try:
        with open(TRUST_FILE, "w", encoding="utf-8") as f:
            json.dump(scores, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[trust] Falha ao salvar scores: {e}")


def get_file_score(file_path: str) -> dict:
    """Retorna score de um arquivo. Cria entrada padrao se nao existir."""
    scores = load_scores()
    if file_path not in scores:
        scores[file_path] = {
            "approvals": 0,
            "rejections": 0,
            "last_action": None,
            "last_update": None,
        }
    return scores[file_path]


def get_effective_level(file_path: str, base_level: str) -> str:
    """
    Calcula o nivel efetivo do arquivo baseado no score.
    base_level vem do FILE_LEVELS (ex: 'alto').
    Pode ser reduzido pra 'medio' ou 'baixo' conforme historico.
    """
    if base_level != "alto":
        return base_level  # Niveis baixo/medio ja sao auto

    score = get_file_score(file_path)
    approvals = score.get("approvals", 0)
    last = score.get("last_action")

    # Se ultima acao foi rejeicao, mantem nivel alto (precisa reconquistar)
    if last == "rejected":
        return "alto"

    if approvals >= THRESHOLD_TO_AUTONOMOUS:
        return "baixo"  # ASSISTENTE ganhou autonomia total
    if approvals >= THRESHOLD_TO_INTERMEDIATE:
        return "medio"  # Aprovacao simples (futuramente)

    return "alto"  # Padrao inicial


def register_approval(file_path: str) -> None:
    """Registra aprovacao no score do arquivo."""
    scores = load_scores()

    if file_path not in scores:
        scores[file_path] = {
            "approvals": 0,
            "rejections": 0,
            "last_action": None,
            "last_update": None,
        }

    scores[file_path]["approvals"] += 1
    scores[file_path]["last_action"] = "approved"
    scores[file_path]["last_update"] = datetime.now().isoformat()

    save_scores(scores)


def register_rejection(file_path: str) -> None:
    """Registra rejeicao - reduz drasticamente a confianca."""
    scores = load_scores()

    if file_path not in scores:
        scores[file_path] = {
            "approvals": 0,
            "rejections": 0,
            "last_action": None,
            "last_update": None,
        }

    scores[file_path]["rejections"] += 1
    scores[file_path]["last_action"] = "rejected"
    scores[file_path]["last_update"] = datetime.now().isoformat()

    # Reduz aprovacoes pela metade ao errar (perde rapido)
    scores[file_path]["approvals"] = scores[file_path]["approvals"] // 2

    save_scores(scores)


def show_trust_report() -> None:
    """Imprime relatorio de confianca por arquivo."""
    scores = load_scores()

    print()
    print("=" * 70)
    print("  CONFIANCA DA ASSISTENTE POR ARQUIVO")
    print("=" * 70)
    print(f"  {'Arquivo':<40} {'Aprovou':<10} {'Rejeitou':<10} {'Nivel'}")
    print("  " + "-" * 66)

    if not scores:
        print("  (Sem registros ainda - ASSISTENTE nao escreveu nada autonomo)")
        print("=" * 70)
        print()
        return

    # Tenta importar FILE_LEVELS para mostrar nivel efetivo
    try:
        from assistente.memory_writer import FILE_LEVELS
    except ImportError:
        FILE_LEVELS = {}

    for file_path, data in scores.items():
        approvals = data.get("approvals", 0)
        rejections = data.get("rejections", 0)
        base_level = FILE_LEVELS.get(file_path, "?")
        effective = get_effective_level(file_path, base_level)

        # Indicador visual de evolucao
        marker = ""
        if base_level == "alto" and effective == "medio":
            marker = " (evoluiu)"
        elif base_level == "alto" and effective == "baixo":
            marker = " (autonomo)"

        short_name = file_path.split("/")[-1]
        print(f"  {short_name:<40} {approvals:<10} {rejections:<10} {effective}{marker}")

    print("=" * 70)
    print(f"  Limites: {THRESHOLD_TO_INTERMEDIATE} aprovacoes -> medio | "
          f"{THRESHOLD_TO_AUTONOMOUS} aprovacoes -> autonomo")
    print("=" * 70)
    print()

