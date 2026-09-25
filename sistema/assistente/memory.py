"""
Modulo de memoria da ASSISTENTE.
Le os arquivos do vault e monta o contexto pra Claude.
Suporta carregamento seletivo de memorias opcionais.
"""

from pathlib import Path
from assistente import config


# Memorias sempre carregadas (essenciais)
ALWAYS_LOAD = [
    "rules-and-boundaries.md",
    "about-me.md",
    "context-window.md",
]

# Memorias carregadas sob demanda
OPTIONAL_LOAD = {
    "relationships": "relationships.md",
    "decisions_log": "decisions-log.md",
    "skills_learned": "skills-learned.md",
}


def read_file(file_path) -> str:
    """Le um arquivo de texto."""
    path = Path(file_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_memory(decision: dict = None) -> dict:
    """
    Carrega memorias do vault.
    Se decision for None, carrega tudo.
    Se decision for dict, carrega essenciais + opcionais marcados como True.
    """
    memory = {}

    # Sempre carrega as essenciais
    for filename in ALWAYS_LOAD:
        file_path = config.MEMORY_PATH / filename
        content = read_file(file_path)
        key = filename.replace(".md", "").replace("-", "_")
        memory[key] = content

    # Carrega opcionais conforme decisao
    for key, filename in OPTIONAL_LOAD.items():
        should_load = True if decision is None else decision.get(key, True)
        if should_load:
            file_path = config.MEMORY_PATH / filename
            memory[key] = read_file(file_path)
        else:
            memory[key] = ""

    return memory


def load_system_prompt() -> str:
    """Carrega o prompt-base.md da pasta System."""
    prompt_path = config.SYSTEM_PATH / "prompt-base.md"
    return read_file(prompt_path)


def build_context(decision: dict = None) -> str:
    """
    Monta o contexto pra enviar a Claude.
    Aceita decision opcional pra carregamento seletivo.
    """
    memory = load_memory(decision)
    parts = []

    parts.append("REGRAS E FRONTEIRAS (PRIORIDADE MAXIMA)")
    parts.append(memory.get("rules_and_boundaries", ""))
    parts.append("")

    parts.append("SOBRE MIM (Desenvolvedor)")
    parts.append(memory.get("about_me", ""))
    parts.append("")

    parts.append("CONTEXTO ATUAL")
    parts.append(memory.get("context_window", ""))
    parts.append("")

    if memory.get("relationships"):
        parts.append("PESSOAS IMPORTANTES")
        parts.append(memory["relationships"])
        parts.append("")

    if memory.get("decisions_log"):
        parts.append("HISTORICO DE DECISOES")
        parts.append(memory["decisions_log"])
        parts.append("")

    if memory.get("skills_learned"):
        parts.append("O QUE VOCE APRENDEU SOBRE MIM")
        parts.append(memory["skills_learned"])

    return "\n".join(parts)


def show_memory_status() -> None:
    """Mostra quais arquivos de memoria estao disponiveis."""
    memory = load_memory()
    system_prompt = load_system_prompt()

    print("=" * 50)
    print("Status da memoria da ASSISTENTE")
    print("=" * 50)

    for key, content in memory.items():
        size = len(content)
        status = "OK" if size > 0 else "VAZIO"
        print(f"[{status}] {key}: {size} caracteres")

    sp_size = len(system_prompt)
    sp_status = "OK" if sp_size > 0 else "VAZIO"
    print(f"[{sp_status}] prompt_base: {sp_size} caracteres")

    print("=" * 50)

