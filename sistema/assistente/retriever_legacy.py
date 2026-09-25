# assistente/retriever.py
"""Recupera notas relevantes do vault Obsidian para uma tarefa."""
import re
import unicodedata
from pathlib import Path
from assistente import config

VAULT = config.VAULT_PATH                  # mesmo vault do resto da ASSISTENTE (vem do .env)
PLAYBOOKS = config.VAULT_PATH / "5-Memory" / "Playbooks"   # playbooks dentro da memoria

STOPWORDS = {
    "a", "o", "e", "de", "da", "do", "das", "dos", "para", "pra", "por",
    "com", "sem", "que", "se", "na", "no", "nas", "nos", "um", "uma",
    "uns", "umas", "minha", "meu", "minhas", "meus", "sua", "seu", "as",
    "os", "em", "ao", "aos", "ou", "the", "to", "of", "and", "is", "in",
    "3", "2", "1",
}


def _normalizar(texto: str) -> set[str]:
    """Minusculas, sem acento, sem stopwords. Tokens que importam."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = texto.encode("ascii", "ignore").decode("ascii")
    palavras = set(re.findall(r"\w+", texto))
    return palavras - STOPWORDS


def buscar_notas(tarefa: str, pasta: Path = None, top_k: int = 3):
    """Retorna as top_k notas mais relevantes (score = palavras uteis em comum)."""
    if pasta is None:
        pasta = VAULT
    alvo = _normalizar(tarefa)
    resultados = []
    for nota in pasta.rglob("*.md"):
        conteudo = nota.read_text(encoding="utf-8", errors="ignore")
        score = len(alvo & _normalizar(conteudo))
        if score > 0:
            resultados.append((score, nota, conteudo))
    resultados.sort(key=lambda x: x[0], reverse=True)
    return resultados[:top_k]

