"""
Modulo de configuracao da ASSISTENTE.
Centraliza todas as configuracoes do sistema.
"""

import os
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()


# API KEY
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()


# CAMINHOS DO VAULT
VAULT_PATH = Path(os.getenv("ASSISTENTE_VAULT_PATH", ""))
MEMORY_PATH = VAULT_PATH / "5-Memory"
SYSTEM_PATH = VAULT_PATH / "System"


# PARAMETROS DA API
MODEL = os.getenv("ASSISTENTE_MODEL", "claude-sonnet-4-6")
TEMPERATURE = float(os.getenv("ASSISTENTE_TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("ASSISTENTE_MAX_TOKENS", "2048"))


# OTIMIZACAO
HISTORY_WINDOW = int(os.getenv("ASSISTENTE_HISTORY_WINDOW", "20"))
USE_SELECTOR = os.getenv("ASSISTENTE_USE_SELECTOR", "true").lower() == "true"


# BUDGET PROTECTION
# Limite de gasto por sessao em USD. 0 = sem limite.
# Quando atingir, ASSISTENTE recusa enviar novas mensagens.
BUDGET_LIMIT_USD = float(os.getenv("ASSISTENTE_BUDGET_LIMIT_USD", "0.50"))


def validate_vault():
    """Verifica se o vault esta montado e acessivel."""
    if not VAULT_PATH.exists():
        return False, "Vault nao encontrado"
    if not MEMORY_PATH.exists():
        return False, "Pasta 5-Memory nao encontrada"
    if not SYSTEM_PATH.exists():
        return False, "Pasta System nao encontrada"
    return True, "Vault acessivel"


def validate_api_key():
    """Verifica se a API key esta configurada."""
    if not ANTHROPIC_API_KEY:
        return False, "API key vazia"
    if not ANTHROPIC_API_KEY.startswith("sk-ant-"):
        return False, "API key parece invalida"
    return True, "API key configurada"


def show_config():
    """Exibe as configuracoes atuais."""
    print("=" * 50)
    print("Configuracao atual da ASSISTENTE")
    print("=" * 50)
    print(f"Vault: {VAULT_PATH}")
    print(f"Memoria: {MEMORY_PATH}")
    print(f"Sistema: {SYSTEM_PATH}")
    print(f"Modelo: {MODEL}")
    print(f"Temperatura: {TEMPERATURE}")
    print(f"Max tokens: {MAX_TOKENS}")
    print(f"Janela de historico: {HISTORY_WINDOW} mensagens")
    print(f"Seletor de memoria: {'ativo' if USE_SELECTOR else 'inativo'}")
    if BUDGET_LIMIT_USD > 0:
        print(f"Budget por sessao: ${BUDGET_LIMIT_USD:.2f}")
    else:
        print("Budget por sessao: sem limite")
    if ANTHROPIC_API_KEY:
        print("API key: configurada")
    else:
        print("API key: nao configurada")
    print("=" * 50)


# OLLAMA (fallback local, sem custo)
OLLAMA_BASE_URL = os.getenv("ASSISTENTE_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("ASSISTENTE_OLLAMA_MODEL", "llama3.2:3b")
ENABLE_OLLAMA_FALLBACK = os.getenv("ASSISTENTE_ENABLE_OLLAMA_FALLBACK", "true").lower() == "true"

# GEMINI (caminho mais barato da cascata fraca)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
ENABLE_GEMINI = os.getenv("ASSISTENTE_ENABLE_GEMINI", "true").lower() == "true"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
ENABLE_GROQ = os.getenv("ASSISTENTE_ENABLE_GROQ", "true").lower() == "true"

