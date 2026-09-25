"""
Modulo de comandos especiais da ASSISTENTE.
"""

import os
import sys
from datetime import datetime
from assistente import config
from assistente import memory
from assistente import trust
from assistente import brain
from assistente import session_memory


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def cmd_help() -> None:
    print()
    print("=" * 60)
    print("  COMANDOS DISPONIVEIS")
    print("=" * 60)
    print("  /ajuda      -> mostra esta lista")
    print("  /limpar     -> limpa a tela")
    print("  /info       -> info da sessao atual")
    print("  /contexto   -> tamanho do contexto enviado")
    print("  /custo      -> custo real desta sessao")
    print("  /historico  -> mensagens trocadas")
    print("  /sessoes    -> historico de sessoes passadas")
    print("  /confianca  -> relatorio de confianca da ASSISTENTE")
    print("  /salvar     -> salva conversa imediatamente")
    print("  /sair       -> encerra a conversa")
    print("=" * 60)
    print()


def cmd_clear() -> None:
    os.system("clear" if sys.platform != "win32" else "cls")


def cmd_info(conversation, started_at: datetime) -> None:
    elapsed = datetime.now() - started_at
    minutes = int(elapsed.total_seconds() // 60)
    seconds = int(elapsed.total_seconds() % 60)
    msg_count = conversation.message_count()

    sent_count = min(msg_count, config.HISTORY_WINDOW)
    skipped = max(0, msg_count - config.HISTORY_WINDOW)

    pending = getattr(conversation, "pending_proposals", [])
    pending_count = len(pending)

    usage = brain.get_last_cost_breakdown()
    total_cost = usage.get("total_cost", 0.0)
    api_msgs = usage.get("messages", 0)

    past_sessions = session_memory.list_past_sessions()
    sessions_loaded = min(len(past_sessions), session_memory.SESSIONS_TO_LOAD)

    print()
    print("=" * 60)
    print("  INFO DA SESSAO")
    print("=" * 60)
    print(f"  Tempo ativo:           {minutes}min {seconds}s")
    print(f"  Mensagens trocadas:    {msg_count}")
    print(f"  Mensagens API:         {api_msgs}")
    print(f"  Custo da sessao:       ${total_cost:.5f}")
    if config.BUDGET_LIMIT_USD > 0:
        remaining = config.BUDGET_LIMIT_USD - total_cost
        print(f"  Budget restante:       ${remaining:.5f}")
    print(f"  Modelo em uso:         {config.MODEL}")
    print(f"  Janela de envio:       {config.HISTORY_WINDOW} mensagens")
    print(f"    Sendo enviadas:      {sent_count}")
    print(f"    Sendo omitidas:      {skipped}")
    print(f"  Seletor:               {'ativo' if config.USE_SELECTOR else 'inativo'}")
    print(f"  Sessoes passadas:      {sessions_loaded} carregadas")
    print(f"  Memorias pendentes:    {pending_count}")
    print(f"  Arquivo da sessao:     {conversation.session_file.name}")
    print("=" * 60)
    print()


def cmd_context() -> None:
    system_prompt = memory.load_system_prompt()
    context_full = memory.build_context()

    sp_chars = len(system_prompt)
    ctx_chars = len(context_full)
    total_chars = sp_chars + ctx_chars

    sp_tokens = estimate_tokens(system_prompt)
    ctx_tokens = estimate_tokens(context_full)
    total_tokens = sp_tokens + ctx_tokens

    print()
    print("=" * 60)
    print("  CONTEXTO MAXIMO POSSIVEL (sem seletor)")
    print("=" * 60)
    print(f"  System prompt:    {sp_chars:,} chars (~{sp_tokens} tokens)")
    print(f"  Memoria do vault: {ctx_chars:,} chars (~{ctx_tokens} tokens)")
    print(f"  TOTAL:            {total_chars:,} chars (~{total_tokens} tokens)")
    print()
    print("  Use /custo pra ver gasto real.")
    print("=" * 60)
    print()


def cmd_custo() -> None:
    usage = brain.get_last_cost_breakdown()

    msgs = usage.get("messages", 0)
    total = usage.get("total_cost", 0.0)
    tokens = usage.get("total_tokens", 0)

    print()
    print("=" * 60)
    print("  CUSTO REAL DA SESSAO")
    print("=" * 60)

    if msgs == 0:
        print("  Nenhuma chamada na API ainda nesta sessao.")
        print("=" * 60)
        print()
        return

    avg_cost = total / msgs if msgs > 0 else 0
    avg_tokens = tokens // msgs if msgs > 0 else 0

    print(f"  Mensagens enviadas:   {msgs}")
    print(f"  Tokens consumidos:    {tokens:,}")
    print(f"  Custo total:          ${total:.5f}")
    print(f"  Media por mensagem:   ${avg_cost:.5f}")
    print(f"  Media de tokens:      ~{avg_tokens}")

    if config.BUDGET_LIMIT_USD > 0:
        remaining = config.BUDGET_LIMIT_USD - total
        pct_used = (total / config.BUDGET_LIMIT_USD) * 100 if config.BUDGET_LIMIT_USD > 0 else 0
        print(f"  Budget desta sessao:  ${config.BUDGET_LIMIT_USD:.2f}")
        print(f"  Usado:                {pct_used:.1f}%")
        print(f"  Restante:             ${remaining:.5f}")

    print()
    if avg_cost > 0:
        msgs_per_5usd = int(5.0 / avg_cost)
        print(f"  Neste ritmo, $5 duram ~{msgs_per_5usd} mensagens.")

    print("=" * 60)
    print()


def cmd_history(conversation) -> None:
    print()
    print(f"[Mensagens trocadas: {conversation.message_count()}]")
    print(f"[Arquivo da sessao: {conversation.session_file.name}]")
    print()


def cmd_save(conversation) -> None:
    conversation.save()
    print()
    print(f"[Conversa salva em: {conversation.session_file.name}]")
    print()


def cmd_trust() -> None:
    trust.show_trust_report()


def cmd_sessoes() -> None:
    """Mostra historico de sessoes passadas."""
    session_memory.show_recent_sessions()


def is_command(text: str) -> bool:
    return text.startswith("/")


def handle_command(text: str, conversation, started_at: datetime):
    cmd = text.lower().strip()

    if cmd == "/sair":
        return "exit"
    if cmd in ("/ajuda", "/help"):
        cmd_help()
        return True
    if cmd == "/limpar":
        cmd_clear()
        return True
    if cmd == "/info":
        cmd_info(conversation, started_at)
        return True
    if cmd == "/contexto":
        cmd_context()
        return True
    if cmd == "/custo":
        cmd_custo()
        return True
    if cmd == "/historico":
        cmd_history(conversation)
        return True
    if cmd == "/salvar":
        cmd_save(conversation)
        return True
    if cmd in ("/confianca", "/confiança"):
        cmd_trust()
        return True
    if cmd in ("/sessoes", "/sessões"):
        cmd_sessoes()
        return True

    print(f"\n[Comando desconhecido: {text}]")
    print("[Digite /ajuda para ver os comandos disponiveis]\n")
    return True

