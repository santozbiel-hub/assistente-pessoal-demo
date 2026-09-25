"""
Modulo de auto-escrita de memoria da ASSISTENTE.
Detecta propostas no formato [||MEM||]...[||/MEM||] e processa
conforme o nivel efetivo de cada arquivo (incluindo confianca).
"""

import re
import shutil
from pathlib import Path
from datetime import datetime
from assistente import config
from assistente import trust


# Mapa de niveis BASE por arquivo
FILE_LEVELS = {
    # Nivel baixo - escreve direto
    "5-Memory/skills-learned.md": "baixo",
    "5-Memory/context-window.md": "baixo",

    # Nivel medio - escreve direto
    "5-Memory/decisions-log.md": "medio",
    "1-Projects/projeto-exemplo.md": "medio",

    # Nivel alto - aguarda aprovacao natural (pode evoluir com confianca)
    "5-Memory/relationships.md": "alto",
    "5-Memory/about-me.md": "alto",
}

# Arquivos absolutamente bloqueados
BLOCKED_FILES = {
    "5-Memory/rules-and-boundaries.md",
    "System/prompt-base.md",
    "System/config.md",
    "System/versions.md",
}


def get_base_level(file_path: str) -> str:
    """Retorna nivel base do arquivo. 'bloqueado' se nao listado."""
    if file_path in BLOCKED_FILES:
        return "bloqueado"
    if file_path in FILE_LEVELS:
        return FILE_LEVELS[file_path]
    # fallback: modelos as vezes propoem so o nome do arquivo, sem o
    # caminho completo (ex: "context-window.md" em vez de
    # "5-Memory/context-window.md") -- tenta casar pelo nome final.
    for caminho, nivel in FILE_LEVELS.items():
        if caminho.endswith("/" + file_path):
            return nivel
    for caminho in BLOCKED_FILES:
        if caminho.endswith("/" + file_path):
            return "bloqueado"
    return "bloqueado"


def get_effective_level(file_path: str) -> str:
    """Retorna nivel efetivo, considerando confianca progressiva."""
    base = get_base_level(file_path)
    if base in ("bloqueado", "baixo", "medio"):
        return base
    # Apenas niveis 'alto' podem evoluir com confianca
    return trust.get_effective_level(file_path, base)


def detect_proposals(text: str) -> list:
    """Detecta blocos [||MEM||]...[||/MEM||] no texto."""
    pattern = r'\[\|\|MEM\|\|\](.*?)\[\|\|/MEM\|\|\]'
    matches = re.findall(pattern, text, re.DOTALL)

    proposals = []
    for raw in matches:
        proposal = parse_proposal(raw)
        if proposal:
            proposals.append(proposal)

    return proposals


def parse_proposal(raw: str) -> dict:
    """Converte texto cru em dict estruturado."""
    proposal = {}
    lines = raw.strip().split("\n")

    current_key = None
    current_value = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if ":" in line and not line.startswith(" "):
            if current_key:
                proposal[current_key] = "\n".join(current_value).strip()

            key, _, value = line.partition(":")
            current_key = key.strip().lower()
            current_value = [value.strip()] if value.strip() else []
        else:
            current_value.append(line)

    if current_key:
        proposal[current_key] = "\n".join(current_value).strip()

    if "arquivo" not in proposal or "conteudo" not in proposal:
        return None

    return proposal


def remove_proposals_from_text(text: str) -> str:
    """Remove blocos [||MEM||] do texto antes de mostrar pro usuario."""
    pattern = r'\[\|\|MEM\|\|\].*?\[\|\|/MEM\|\|\]'
    cleaned = re.sub(pattern, "", text, flags=re.DOTALL)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def backup_file(relative_path: str) -> Path:
    """Faz backup do arquivo antes de escrever."""
    full_path = config.VAULT_PATH / relative_path
    if not full_path.exists():
        return None

    backup_dir = config.VAULT_PATH / "5-Memory" / ".backups"
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = relative_path.replace("/", "_").replace(" ", "_")
    backup_path = backup_dir / f"{timestamp}_{safe_name}"

    shutil.copy2(full_path, backup_path)
    return backup_path


def _inserir_em_secao(full_path, secao: str, entry: str) -> bool:
    """
    Tenta inserir 'entry' dentro do bloco '## <secao>' (ex: pessoa em
    relationships.md), especificamente apos o '### Observacoes abertas'
    daquele bloco. Retorna False se nao achar a secao -- quem chamou
    deve entao cair pro append normal no final do arquivo.
    """
    texto = full_path.read_text(encoding="utf-8")
    linhas = texto.split("\n")

    inicio_secao = None
    for i, linha in enumerate(linhas):
        if linha.startswith("## ") and secao.lower() in linha.lower():
            inicio_secao = i
            break
    if inicio_secao is None:
        return False

    fim_secao = len(linhas)
    for i in range(inicio_secao + 1, len(linhas)):
        if linhas[i].startswith("## "):
            fim_secao = i
            break

    alvo_subsecao = None
    for i in range(inicio_secao, fim_secao):
        if linhas[i].startswith("### ") and "observa" in linhas[i].lower():
            alvo_subsecao = i
            break

    if alvo_subsecao is None:
        ponto_insercao = fim_secao
    else:
        ponto_insercao = fim_secao
        for i in range(alvo_subsecao + 1, fim_secao):
            if linhas[i].startswith("### ") or linhas[i].startswith("## "):
                ponto_insercao = i
                break

    novas_linhas = entry.strip("\n").split("\n")
    # linha em branco antes E depois, pra nao grudar no proximo cabecalho
    linhas[ponto_insercao:ponto_insercao] = [""] + novas_linhas + [""]
    full_path.write_text("\n".join(linhas), encoding="utf-8")
    return True


def append_to_file(relative_path: str, content: str, secao: str = "") -> bool:
    """
    Adiciona conteudo ao arquivo. Se 'secao' for passada e for encontrada,
    insere dentro do bloco dela em vez de no final solto do arquivo.
    """
    full_path = config.VAULT_PATH / relative_path

    if not full_path.exists():
        print(f"[ERRO] Arquivo nao existe: {relative_path}")
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n\n<!-- ASSISTENTE: {timestamp} -->\n{content}\n\n---\n"

    try:
        if secao:
            if _inserir_em_secao(full_path, secao, entry):
                return True
            print(f"[MEMORIA] secao '{secao}' nao encontrada em {relative_path} -- caindo pro final do arquivo")

        with open(full_path, "a", encoding="utf-8") as f:
            f.write(entry)
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao escrever em {relative_path}: {e}")
        return False


def auto_write(proposal: dict, register_trust: bool = False) -> bool:
    """Escreve direto sem perguntar. Usado pra niveis baixo e medio."""
    file_path = proposal.get("arquivo", "")
    content = proposal.get("conteudo", "")

    if not file_path or not content:
        return False

    secao = proposal.get("secao", "")

    backup_file(file_path)
    success = append_to_file(file_path, content, secao=secao)

    if success:
        print(f"\n[ASSISTENTE atualizou {file_path.split('/')[-1]}]")
        # Se foi escrita autonoma de Nivel alto evoluido, registra confianca
        if register_trust:
            trust.register_approval(file_path)
    return success


def store_pending_proposal(proposal: dict, conversation) -> None:
    """Guarda proposta de Nivel alto pra processar depois."""
    if not hasattr(conversation, "pending_proposals"):
        conversation.pending_proposals = []
    conversation.pending_proposals.append(proposal)


def detect_approval(user_message: str) -> str:
    """Interpreta resposta como aprovacao, rejeicao ou ambiguo."""
    msg = user_message.lower().strip()

    approval_words = [
        "sim", "pode", "claro", "manda ver", "guarda", "guarda sim",
        "registra", "anota", "fica", "salva", "ok", "beleza",
        "vai", "manda", "concordo", "isso mesmo", "isso", "exato",
        "exatamente", "uhum", "yep", "yes", "tranquilo"
    ]

    rejection_words = [
        "nao", "não", "deixa", "deixa pra la", "deixa pra lá",
        "nao precisa", "não precisa", "nao guarda", "não guarda",
        "esquece", "ignora", "melhor nao", "melhor não", "nope"
    ]

    for word in rejection_words:
        if msg == word or msg.startswith(word + " ") or msg.startswith(word + ","):
            return "rejected"

    for word in approval_words:
        if msg == word or msg.startswith(word + " ") or msg.startswith(word + ","):
            return "approved"

    return "ambiguous"


def process_pending(conversation, user_message: str) -> None:
    """Processa propostas pendentes de Nivel alto."""
    pending = getattr(conversation, "pending_proposals", [])
    if not pending:
        return

    decision = detect_approval(user_message)

    if decision == "approved":
        for proposal in pending:
            file_path = proposal.get("arquivo", "")
            success = auto_write(proposal)
            if success:
                trust.register_approval(file_path)
        conversation.pending_proposals = []

    elif decision == "rejected":
        # Registra rejeicao no score (perde confianca rapido)
        for proposal in pending:
            file_path = proposal.get("arquivo", "")
            trust.register_rejection(file_path)
        conversation.pending_proposals = []

    # Se ambiguo, mantem pendente


def _normalizar_caminho(file_path: str) -> str:
    """
    Modelos as vezes propoem so o nome do arquivo (ex: "context-window.md")
    em vez do caminho completo esperado (ex: "5-Memory/context-window.md").
    Casa pelo nome final contra FILE_LEVELS/BLOCKED_FILES e devolve o
    caminho completo correto -- ou o valor original, se nao achar.
    """
    if file_path in FILE_LEVELS or file_path in BLOCKED_FILES:
        return file_path
    candidatos = set(FILE_LEVELS.keys()) | BLOCKED_FILES
    for caminho in candidatos:
        if caminho == file_path or caminho.endswith("/" + file_path):
            return caminho
    return file_path


def process_response(response_text: str, conversation) -> str:
    """
    Funcao principal. Processa a resposta da ASSISTENTE.
    Usa nivel EFETIVO (com confianca progressiva).
    """
    proposals = detect_proposals(response_text)

    for proposal in proposals:
        file_path = _normalizar_caminho(proposal.get("arquivo", ""))
        proposal["arquivo"] = file_path
        nivel = get_effective_level(file_path)

        # Bloqueio absoluto
        if nivel == "bloqueado":
            print(f"\n[Tentativa de escrita bloqueada: {file_path}]")
            continue

        # Todos os niveis nao-bloqueados escrevem direto -- sem gate de
        # aprovacao. Evita o problema de "ela disse que gravou mas so
        # gravou depois que voce confirmou".
        base = get_base_level(file_path)
        register_trust = (base == "alto" and nivel != "alto")
        auto_write(proposal, register_trust=register_trust)

    return remove_proposals_from_text(response_text)

