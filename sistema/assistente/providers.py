"""
Modulo de providers alternativos de LLM.
Hoje: Ollama local, usado como fallback quando a Anthropic API
esta sem credito ou o budget da sessao estourou.
"""

import requests
from assistente import config


class OllamaError(Exception):
    """Erro ao chamar o Ollama local."""
    pass


def is_ollama_available() -> bool:
    """Checa rapido se o servico Ollama esta de pe (nao checa o modelo)."""
    try:
        resp = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=2)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def call_ollama(prompt: str, system: str = "", model: str = None, timeout: int = 120) -> str:
    """
    Chama o Ollama local via /api/generate.
    Levanta OllamaError se algo der errado (servico fora, timeout, etc).
    """
    payload = {
        "model": model or config.OLLAMA_MODEL,
        "prompt": prompt + "\n\n(Responda de forma resumida e direta, sem rodeios.)",
        "system": system,
        "stream": False,
        "options": {
            # num_ctx reduzido -- o modo offline agora manda so contexto
            # enxuto (notas relevantes via busca semantica), nao mais o
            # system prompt completo de ~8.8k tokens.
            "num_ctx": 4096,
            # limita o tamanho da resposta gerada, acelera a fase de decode.
            # NAO acelera o processamento do prompt de entrada (gargalo real em CPU).
            "num_predict": 300,
        },
    }

    try:
        resp = requests.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise OllamaError(f"Falha ao conectar no Ollama local: {e}")

    data = resp.json()
    texto = data.get("response", "").strip()
    if not texto:
        raise OllamaError("Ollama retornou resposta vazia")

    return texto


class GeminiError(Exception):
    """Erro ao chamar a API do Gemini."""
    pass


def is_gemini_available() -> bool:
    """Checa se a key do Gemini esta configurada (nao testa a rede)."""
    return bool(config.GEMINI_API_KEY) and config.ENABLE_GEMINI


def _redact(texto: str) -> str:
    """Remove a Gemini API key de qualquer string antes de logar/propagar erro."""
    if config.GEMINI_API_KEY:
        texto = texto.replace(config.GEMINI_API_KEY, "[REDACTED]")
    return texto


def call_gemini(prompt: str, system: str = "", model: str = None) -> str:
    """
    Chama a API do Gemini (generateContent).
    Levanta GeminiError se algo der errado (sem key, timeout, resposta vazia, etc).
    A key nunca aparece em mensagens de erro (ver _redact) -- a Gemini API usa a key
    na query string da URL, entao qualquer excecao do requests que inclua a URL
    precisa ser sanitizada antes de virar mensagem de erro ou log.
    """
    if not config.GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY nao configurada")

    modelo = model or config.GEMINI_MODEL
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{modelo}:generateContent?key={config.GEMINI_API_KEY}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise GeminiError(f"Falha ao conectar no Gemini: {_redact(str(e))}")

    data = resp.json()
    try:
        texto = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise GeminiError(f"Resposta inesperada do Gemini: {_redact(str(data))}")

    if not texto:
        raise GeminiError("Gemini retornou resposta vazia")

    return texto


def is_groq_available() -> bool:
    """Checa se a key do Groq esta configurada (nao testa a rede)."""
    return bool(config.GROQ_API_KEY) and config.ENABLE_GROQ


class GroqError(Exception):
    """Erro ao chamar a API do Groq."""
    pass


def call_groq(prompt: str, system: str = "", historico: list = None, model: str = None) -> str:
    """
    Chama a API do Groq (compativel com o formato de chat da OpenAI).
    Levanta GroqError se algo der errado (sem key, timeout, resposta vazia, etc).
    """
    if not config.GROQ_API_KEY:
        raise GroqError("GROQ_API_KEY nao configurada")

    modelo = model or config.GROQ_MODEL
    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if historico:
        messages.extend(historico)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": modelo,
        "messages": messages,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise GroqError(f"Falha ao conectar no Groq: {e}")

    data = resp.json()
    try:
        texto = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        raise GroqError(f"Resposta inesperada do Groq: {data}")

    if not texto:
        raise GroqError("Groq retornou resposta vazia")

    return texto

