"""
ASSISTENTE Bridge - Chat interativo no terminal.
"""

import sys
from datetime import datetime
from assistente import config
from assistente import brain
from assistente import commands
from assistente import memory_writer
from assistente import session_memory
from assistente.conversation import Conversation


def print_header():
    print("=" * 60)
    print("  ASSISTENTE - Adaptive Reasoning & Intelligence Assistant")
    print("=" * 60)
    print("  Digite /ajuda para ver comandos disponiveis.")
    if config.BUDGET_LIMIT_USD > 0:
        print(f"  Budget desta sessao: ${config.BUDGET_LIMIT_USD:.2f}")

    # Mostra se tem sessoes passadas carregadas
    past = session_memory.list_past_sessions()
    if past:
        loaded = min(len(past), session_memory.SESSIONS_TO_LOAD)
        print(f"  Memoria entre sessoes: {loaded} sessao(oes) carregada(s)")
    print("=" * 60)
    print()


def validate_environment():
    ok, msg = config.validate_vault()
    if not ok:
        print(f"[ERRO] Vault: {msg}")
        print("Dica: monte o ASSISTENTE-Brain.dmg antes de rodar.")
        sys.exit(1)

    ok, msg = config.validate_api_key()
    if not ok:
        print(f"[ERRO] API key: {msg}")
        sys.exit(1)


def close_session(conversation):
    """Encerra a sessao - salva conversa e gera resumo."""
    if conversation.message_count() > 0:
        # Salva o JSON da conversa
        conversation.save()
        print(f"\n[Conversa salva em: {conversation.session_file.name}]")
        print(f"[Total: {conversation.message_count()} mensagens]")

        # Gera resumo da sessao (Etapa A)
        try:
            session_memory.close_session_with_summary(conversation.get_history())
        except Exception as e:
            print(f"[Falha ao gerar resumo: {e}]")

    # Mostra custo final
    usage = brain.get_last_cost_breakdown()
    if usage.get("messages", 0) > 0:
        print(f"[Custo desta sessao: ${usage.get('total_cost', 0):.5f}]")


def main():
    print_header()
    validate_environment()

    brain.reset_session_usage()

    conversation = Conversation()
    started_at = datetime.now()

    print("ASSISTENTE online. Pode falar comigo.\n")

    while True:
        try:
            user_input = input("Voce: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nEncerrando...")
            break

        if not user_input:
            continue

        if commands.is_command(user_input):
            result = commands.handle_command(user_input, conversation, started_at)
            if result == "exit":
                break
            continue

        memory_writer.process_pending(conversation, user_input)

        print("\nASSISTENTE: ", end="", flush=True)

        raw_response = brain.send_message(
            user_message=user_input,
            conversation_history=conversation.get_history()
        )

        clean_response = memory_writer.process_response(raw_response, conversation)

        conversation.add_user_message(user_input)
        conversation.add_assistant_message(clean_response)

        print(clean_response)
        print()

    close_session(conversation)
    print("\nAte logo, Desenvolvedor.")


if __name__ == "__main__":
    main()

