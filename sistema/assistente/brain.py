"""
Modulo cerebro da ASSISTENTE - Senior-grade com memoria entre sessoes.
"""

import json
from pathlib import Path
from datetime import datetime
from anthropic import Anthropic
from assistente import config
from assistente import memory
from assistente import selector
from assistente import session_memory
from assistente import providers


# Precos por 1M de tokens
PRICE_INPUT_PER_M = 3.00
PRICE_OUTPUT_PER_M = 15.00
PRICE_CACHE_WRITE_PER_M = 3.75
PRICE_CACHE_READ_PER_M = 0.30


SESSION_USAGE_FILE = Path(__file__).resolve().parents[1] / "conversations" / ".session_usage.json"


def create_client() -> Anthropic:
    return Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _contexto_de_data() -> str:
    """Contexto de data/hora atual, pra ASSISTENTE nao perder a nocao de 'hoje'."""
    dias_semana = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                   "sexta-feira", "sábado", "domingo"]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
             "agosto", "setembro", "outubro", "novembro", "dezembro"]
    agora = datetime.now()
    dia_semana = dias_semana[agora.weekday()]
    data_formatada = f"{dia_semana}, {agora.day} de {meses[agora.month - 1]} de {agora.year}"
    return f"CONTEXTO DE DATA E HORA\nHoje e {data_formatada}, {agora.strftime('%H:%M')}.\n"


def build_essential_system() -> str:
    """Bloco 1 do system: prompt-base + memoria essencial + sessoes passadas."""
    base_prompt = memory.load_system_prompt()
    essential_memory = memory.build_context(decision={
        "relationships": False,
        "decisions_log": False,
        "skills_learned": False,
    })

    full = _contexto_de_data() + "\n" + base_prompt + "\n\n" + "=" * 50 + "\n"
    full += "MEMORIA ESSENCIAL DO USUÁRIO\n"
    full += "=" * 50 + "\n\n"
    full += essential_memory

    past_sessions = session_memory.load_recent_sessions()
    if past_sessions:
        full += "\n\n" + past_sessions

    return full


def build_optional_system(decision: dict) -> str:
    """Bloco 2 do system: memoria opcional, varia conforme decisao."""
    optional_parts = []

    if decision.get("relationships"):
        rel_path = config.MEMORY_PATH / "relationships.md"
        if rel_path.exists():
            optional_parts.append("PESSOAS IMPORTANTES")
            optional_parts.append(rel_path.read_text(encoding="utf-8"))
            optional_parts.append("")

    if decision.get("decisions_log"):
        dec_path = config.MEMORY_PATH / "decisions-log.md"
        if dec_path.exists():
            optional_parts.append("HISTORICO DE DECISOES")
            optional_parts.append(dec_path.read_text(encoding="utf-8"))
            optional_parts.append("")

    if decision.get("skills_learned"):
        skills_path = config.MEMORY_PATH / "skills-learned.md"
        if skills_path.exists():
            optional_parts.append("APRENDIDO SOBRE USUÁRIO")
            optional_parts.append(skills_path.read_text(encoding="utf-8"))

    if not optional_parts:
        return ""

    return "\n".join(optional_parts)


def calculate_cost(usage) -> dict:
    input_tokens = getattr(usage, "input_tokens", 0)
    output_tokens = getattr(usage, "output_tokens", 0)
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0)
    cache_read = getattr(usage, "cache_read_input_tokens", 0)

    cost_input = (input_tokens / 1_000_000) * PRICE_INPUT_PER_M
    cost_output = (output_tokens / 1_000_000) * PRICE_OUTPUT_PER_M
    cost_cache_write = (cache_creation / 1_000_000) * PRICE_CACHE_WRITE_PER_M
    cost_cache_read = (cache_read / 1_000_000) * PRICE_CACHE_READ_PER_M

    total = cost_input + cost_output + cost_cache_write + cost_cache_read

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_tokens": cache_creation,
        "cache_read_tokens": cache_read,
        "cost_input": cost_input,
        "cost_output": cost_output,
        "cost_cache_write": cost_cache_write,
        "cost_cache_read": cost_cache_read,
        "total_cost": total,
    }


def load_session_usage() -> dict:
    if not SESSION_USAGE_FILE.exists():
        return {"messages": 0, "total_cost": 0.0, "total_tokens": 0}
    try:
        with open(SESSION_USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"messages": 0, "total_cost": 0.0, "total_tokens": 0}


def save_session_usage(data: dict) -> None:
    SESSION_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(SESSION_USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[brain] Falha ao salvar usage: {e}")


def update_session_usage(cost_data: dict) -> dict:
    session = load_session_usage()
    session["messages"] = session.get("messages", 0) + 1
    session["total_cost"] = session.get("total_cost", 0.0) + cost_data["total_cost"]
    session["total_tokens"] = session.get("total_tokens", 0) + (
        cost_data["input_tokens"] + cost_data["output_tokens"]
    )
    session["last_update"] = datetime.now().isoformat()
    save_session_usage(session)
    return session


def reset_session_usage() -> None:
    save_session_usage({
        "messages": 0,
        "total_cost": 0.0,
        "total_tokens": 0,
        "started_at": datetime.now().isoformat()
    })


def trim_history(history: list, window: int) -> list:
    if len(history) <= window:
        return history
    return history[-window:]


def send_message(
    user_message: str,
    conversation_history: list = None,
    model: str = None,
    fallback_to_ollama: bool = True,
) -> str:
    """
    Envia mensagem pra Claude com cache estavel e tracking.
    Cai pro Ollama local se sem credito/budget -- A MENOS que fallback_to_ollama=False,
    usado por chamadas intermediarias de cascata (ex: degrau Haiku no router.py) que
    preferem falhar rapido e deixar o CHAMADOR decidir o proximo passo, em vez de
    silenciosamente desviar pro Ollama (lento, contexto completo, ~1-5min).
    """
    if conversation_history is None:
        conversation_history = []

    ok, msg = config.validate_vault()
    if not ok:
        return f"[ERRO] {msg}"

    budget_estourado = False
    if config.BUDGET_LIMIT_USD > 0:
        session = load_session_usage()
        if session.get("total_cost", 0) >= config.BUDGET_LIMIT_USD:
            budget_estourado = True

    key_ok, _ = config.validate_api_key()

    if config.USE_SELECTOR:
        decision = selector.decide_optional_memories(user_message)
    else:
        decision = {"relationships": True, "decisions_log": True, "skills_learned": True}

    essential = build_essential_system()
    optional = build_optional_system(decision)
    full_system_text = essential + ("\n\n" + optional if optional else "")

    trimmed_history = trim_history(conversation_history, config.HISTORY_WINDOW)
    messages = trimmed_history + [{"role": "user", "content": user_message}]

    system_blocks = [
        {
            "type": "text",
            "text": essential,
            "cache_control": {"type": "ephemeral"}
        }
    ]
    if optional:
        system_blocks.append({"type": "text", "text": optional})

    def _tentar_ollama(motivo: str) -> str:
        if not fallback_to_ollama:
            return f"[ERRO] {motivo} (fallback Ollama desativado para esta chamada)"
        if not config.ENABLE_OLLAMA_FALLBACK:
            return f"[BUDGET/ERRO] {motivo} e fallback Ollama esta desativado (ASSISTENTE_ENABLE_OLLAMA_FALLBACK=false)."
        print(f"[OLLAMA] {motivo}. Processando com memoria completa em hardware local "
              f"(sem GPU) - isso pode levar de 1 a 5 minutos. Aguarde...")
        try:
            resposta = providers.call_ollama(prompt=user_message, system=full_system_text)
            return f"[OLLAMA LOCAL] {resposta}"
        except providers.OllamaError as e:
            return f"[ERRO] {motivo}. Fallback Ollama tambem falhou: {e}"

    if budget_estourado:
        return _tentar_ollama(f"Limite de ${config.BUDGET_LIMIT_USD:.2f} atingido nesta sessao")

    if not key_ok:
        return _tentar_ollama("API key da Anthropic nao configurada")

    try:
        client = create_client()
        response = client.messages.create(
            model=model or config.MODEL,
            max_tokens=config.MAX_TOKENS,
            temperature=config.TEMPERATURE,
            system=system_blocks,
            messages=messages
        )

        cost_data = calculate_cost(response.usage)
        update_session_usage(cost_data)

        return response.content[0].text

    except Exception as e:
        erro_str = str(e).lower()
        sinais_sem_credito = ["credit", "billing", "insufficient", "quota", "rate_limit", "429", "402"]
        if any(sinal in erro_str for sinal in sinais_sem_credito):
            return _tentar_ollama(f"API Anthropic sem credito/limite ({e})")
        return f"[ERRO na API] {str(e)}"


def get_last_cost_breakdown() -> dict:
    return load_session_usage()


def test_connection() -> None:
    print("=" * 50)
    print("Teste de conexao com a Claude API")
    print("=" * 50)

    ok, msg = config.validate_vault()
    print(f"[{'OK' if ok else 'FALHA'}] Vault: {msg}")

    ok, msg = config.validate_api_key()
    print(f"[{'OK' if ok else 'FALHA'}] API key: {msg}")

    essential = build_essential_system()
    print(f"[OK] System essencial: {len(essential)} caracteres")
    print("=" * 50)

    ok, _ = config.validate_api_key()
    if ok:
        print("Fazendo teste real na API...")
        response = send_message("Oi, esta e uma mensagem de teste. Responda so 'ok'.")
        print(f"Resposta: {response}")
        usage = load_session_usage()
        print(f"\nCusto desta chamada: ~${usage.get('total_cost', 0):.5f}")
        print("=" * 50)
    else:
        print("API key nao configurada - teste real pulado.")
        print("=" * 50)

