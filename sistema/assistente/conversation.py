"""
Modulo de conversacao da ASSISTENTE.
Gerencia o historico de mensagens da sessao atual.
"""

import json
from pathlib import Path
from datetime import datetime
from assistente import config


# Caminho onde salvamos o historico (fora do vault)
HISTORY_DIR = Path(__file__).resolve().parents[1] / "conversations"


def ensure_history_dir():
    """Garante que a pasta de historico existe."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def new_session_filename():
    """Cria nome de arquivo para a sessao atual."""
    now = datetime.now()
    return HISTORY_DIR / f"session_{now.strftime('%Y%m%d_%H%M%S')}.json"


class Conversation:
    """Mantem o historico de uma conversa."""

    def __init__(self):
        self.messages = []
        ensure_history_dir()
        self.session_file = new_session_filename()

    def add_user_message(self, text):
        """Adiciona mensagem do usuario ao historico."""
        self.messages.append({
            "role": "user",
            "content": text
        })

    def add_assistant_message(self, text):
        """Adiciona resposta da ASSISTENTE ao historico."""
        self.messages.append({
            "role": "assistant",
            "content": text
        })

    def get_history(self):
        """Retorna o historico para enviar a Claude."""
        return self.messages

    def save(self):
        """Salva conversa em arquivo JSON."""
        data = {
            "started_at": datetime.now().isoformat(),
            "messages": self.messages
        }
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def message_count(self):
        """Retorna numero de mensagens trocadas."""
        return len(self.messages)

