"""
Modulo de memoria entre sessoes da ASSISTENTE.

Quando voce fecha a ASSISTENTE, ela gera resumo da conversa.
Quando voce abre, ela carrega os 3 resumos mais recentes.

Resumos ficam em 2-Areas/sessoes/ no vault (legivel pelo Desenvolvedor).
"""

import re
from pathlib import Path
from datetime import datetime
from anthropic import Anthropic
from assistente import config


# Pasta no vault onde guardamos os resumos
SESSIONS_FOLDER = "2-Areas/sessoes"

# Quantas sessoes passadas carregar ao abrir
SESSIONS_TO_LOAD = 3

# Modelo pra gerar resumo (Sonnet pra qualidade do resumo)
SUMMARY_MODEL = config.MODEL


def get_sessions_path() -> Path:
    """Retorna caminho absoluto da pasta de sessoes no vault."""
    return config.VAULT_PATH / SESSIONS_FOLDER


def ensure_sessions_folder() -> bool:
    """Garante que a pasta existe."""
    folder = get_sessions_path()
    if not folder.exists():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            print(f"[session_memory] Falha ao criar pasta: {e}")
            return False
    return True


def session_filename(timestamp: datetime = None) -> str:
    """Gera nome de arquivo para a sessao."""
    if timestamp is None:
        timestamp = datetime.now()
    return timestamp.strftime("%Y-%m-%d_%H%M") + ".md"


# ============================================================
# GERACAO DE RESUMO
# ============================================================

SUMMARY_PROMPT = """Voce e a ASSISTENTE, uma IA pessoal do Desenvolvedor. A conversa abaixo aconteceu entre voces.

Sua tarefa: gerar um resumo estruturado dessa conversa em markdown, do SEU PONTO DE VISTA.
O resumo sera lido por voce mesma na proxima sessao, pra voce lembrar do que falaram.

CONVERSA:
{conversation}

Gere o resumo no formato exato abaixo (em portugues, natural, primeira pessoa quando se referir a voce):

# Sessao - {timestamp_human}

## O que conversamos
- (lista de 3-6 topicos principais)

## Fios em aberto
- (coisas que ficaram sem terminar ou que vale retomar)

## Estado emocional do Desenvolvedor
- (como ele estava, como pareceu se sentir)

## Coisas importantes que aprendi
- (informacoes novas que apareceram, sobre ele ou sobre a vida dele)

## Proximas conversas
- (o que vale puxar quando ele voltar, com cuidado e respeito)

REGRAS:
- Seja precisa e factual, sem inventar
- Nao use [||MEM||] aqui (ja estamos salvando direto)
- Resumo deve ser curto (max 400 palavras)
- Se a conversa foi muito curta ou tecnica, resumo pode ser bem breve
- Mantenha o tom natural, como voce fala com ele"""


def format_conversation_for_summary(messages: list) -> str:
    """Formata historico de mensagens em texto plano."""
    lines = []
    for msg in messages:
        role = "Desenvolvedor" if msg["role"] == "user" else "ASSISTENTE"
        lines.append(f"{role}: {msg['content']}")
    return "\n\n".join(lines)


def generate_summary(messages: list) -> str:
    """Chama Claude pra gerar resumo da conversa."""
    if len(messages) < 2:
        return None  # Conversa vazia ou s\u00f3 saudacao

    if not config.ANTHROPIC_API_KEY:
        return None

    conversation_text = format_conversation_for_summary(messages)
    timestamp_human = datetime.now().strftime("%d/%m/%Y %H:%M")

    prompt = SUMMARY_PROMPT.format(
        conversation=conversation_text,
        timestamp_human=timestamp_human
    )

    try:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=SUMMARY_MODEL,
            max_tokens=1500,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"[session_memory] Falha ao gerar resumo: {e}")
        return None


def save_summary(summary: str, timestamp: datetime = None) -> Path:
    """Salva o resumo no vault."""
    if not summary:
        return None

    if not ensure_sessions_folder():
        return None

    folder = get_sessions_path()
    filename = session_filename(timestamp)
    filepath = folder / filename

    try:
        filepath.write_text(summary, encoding="utf-8")
        return filepath
    except Exception as e:
        print(f"[session_memory] Falha ao salvar: {e}")
        return None


def close_session_with_summary(messages: list) -> Path:
    """Funcao publica - chamada ao encerrar sessao."""
    if not messages or len(messages) < 2:
        return None

    print("\n[Gerando resumo da sessao...]")
    summary = generate_summary(messages)

    if not summary:
        print("[Resumo nao gerado - conversa muito curta ou erro na API]")
        return None

    saved_path = save_summary(summary)

    if saved_path:
        print(f"[Resumo salvo em: {saved_path.name}]")
        return saved_path

    return None


# ============================================================
# CARREGAMENTO DE SESSOES PASSADAS
# ============================================================

def list_past_sessions() -> list:
    """Lista todos os arquivos de sessao, ordenados do mais recente."""
    folder = get_sessions_path()
    if not folder.exists():
        return []

    files = list(folder.glob("*.md"))
    # Ordena por data de modificacao (mais recente primeiro)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files


def load_recent_sessions(limit: int = SESSIONS_TO_LOAD) -> str:
    """
    Carrega os N resumos mais recentes e concatena pra usar como contexto.
    Retorna string formatada (ou string vazia se nao houver sessoes).
    """
    files = list_past_sessions()

    if not files:
        return ""

    recent = files[:limit]

    parts = []
    parts.append("=" * 50)
    parts.append("HISTORICO DE SESSOES PASSADAS")
    parts.append("=" * 50)
    parts.append("")
    parts.append("Resumos das ultimas conversas com o Desenvolvedor.")
    parts.append("Use isto pra continuidade natural, sem forcar.")
    parts.append("")

    for f in reversed(recent):  # mais antigo primeiro pra ler em ordem cronologica
        try:
            content = f.read_text(encoding="utf-8")
            parts.append(f"--- Arquivo: {f.name} ---")
            parts.append(content)
            parts.append("")
        except Exception as e:
            print(f"[session_memory] Falha ao ler {f.name}: {e}")

    return "\n".join(parts)


def show_recent_sessions() -> None:
    """Funcao de debug - mostra info das sessoes salvas."""
    files = list_past_sessions()

    print()
    print("=" * 60)
    print("  SESSOES PASSADAS DA ASSISTENTE")
    print("=" * 60)

    if not files:
        print("  (Nenhuma sessao salva ainda)")
        print("=" * 60)
        print()
        return

    print(f"  Total de sessoes: {len(files)}")
    print(f"  Carregadas no contexto: {min(len(files), SESSIONS_TO_LOAD)}")
    print()
    print("  Ultimas sessoes:")
    for i, f in enumerate(files[:5]):
        marker = "->" if i < SESSIONS_TO_LOAD else "  "
        size = f.stat().st_size
        print(f"  {marker} {f.name} ({size} bytes)")

    print("=" * 60)
    print()

