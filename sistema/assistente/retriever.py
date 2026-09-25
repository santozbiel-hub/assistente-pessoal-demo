"""
ASSISTENTE — Retriever v2: busca semântica por embeddings.

Em vez de procurar PALAVRAS iguais (v1), compara SIGNIFICADOS.
Score = similaridade de cosseno, sempre entre -1 e 1 (escala fixa,
sem inflação com o crescimento do vault).
"""

import sys
import pickle
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

try:
    from assistente.config import VAULT_PATH
except ImportError:
    from config import VAULT_PATH

MODELO_NOME = "paraphrase-multilingual-MiniLM-L12-v2"  # multilíngue: entende PT-BR
MAX_PALAVRAS_CHUNK = 180
CACHE_DIR = Path(VAULT_PATH) / "System" / "cache"
CACHE_FILE = CACHE_DIR / "embeddings_v2.pkl"

_modelo = None  # carregado sob demanda (lazy)


def _carregar_modelo():
    global _modelo
    if _modelo is None:
        print(f"[retriever] carregando modelo {MODELO_NOME}...")
        _modelo = SentenceTransformer(MODELO_NOME)
    return _modelo


def _verificar_vault():
    vault = Path(VAULT_PATH)
    if not vault.exists():
        raise FileNotFoundError(
            f"Vault não encontrado em {VAULT_PATH}. O ASSISTENTE-Brain.dmg está montado?"
        )
    return vault


def _listar_arquivos_md(vault):
    arquivos = []
    for caminho in vault.rglob("*.md"):
        if CACHE_DIR in caminho.parents:
            continue
        arquivos.append(caminho)
    return arquivos


def _dividir_em_chunks(texto):
    """Quebra em blocos de até MAX_PALAVRAS_CHUNK palavras,
    respeitando parágrafos (não corta frase no meio)."""
    paragrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    chunks, atual, contagem = [], [], 0
    for p in paragrafos:
        n = len(p.split())
        if atual and contagem + n > MAX_PALAVRAS_CHUNK:
            chunks.append("\n\n".join(atual))
            atual, contagem = [p], n
        else:
            atual.append(p)
            contagem += n
    if atual:
        chunks.append("\n\n".join(atual))
    return chunks


def _carregar_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "rb") as f:
                return pickle.load(f)
        except Exception:
            print("[retriever] cache corrompido, reindexando do zero")
    return {}


def _salvar_cache(cache):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "wb") as f:
        pickle.dump(cache, f)


def indexar(forcar=False):
    """Atualiza o índice. Reprocessa só arquivos novos/alterados (mtime),
    a menos que forcar=True."""
    vault = _verificar_vault()
    cache = {} if forcar else _carregar_cache()
    atuais = set()
    novos = 0

    for caminho in _listar_arquivos_md(vault):
        rel = str(caminho.relative_to(vault))
        atuais.add(rel)
        mtime = caminho.stat().st_mtime
        if rel in cache and cache[rel]["mtime"] == mtime:
            continue
        texto = caminho.read_text(encoding="utf-8", errors="ignore")
        chunks = _dividir_em_chunks(texto)
        if not chunks:
            continue
        modelo = _carregar_modelo()
        embeddings = modelo.encode(chunks, normalize_embeddings=True)
        cache[rel] = {
            "mtime": mtime,
            "chunks": chunks,
            "embeddings": np.asarray(embeddings, dtype=np.float32),
        }
        novos += 1

    # remove do cache arquivos deletados do vault
    for rel in list(cache.keys()):
        if rel not in atuais:
            del cache[rel]

    _salvar_cache(cache)
    if novos:
        total = sum(len(v["chunks"]) for v in cache.values())
        print(f"[retriever] índice: {len(cache)} arquivos, {total} chunks ({novos} reprocessados)")
    return cache


def buscar(consulta, top_k=5):
    """Top_k trechos mais parecidos em SIGNIFICADO com a consulta.
    Retorna: [{"arquivo": ..., "trecho": ..., "score": ...}]"""
    cache = indexar()  # rápido se nada mudou
    if not cache:
        return []

    modelo = _carregar_modelo()
    vetor = modelo.encode([consulta], normalize_embeddings=True)[0]

    resultados = []
    for rel, dados in cache.items():
        scores = dados["embeddings"] @ vetor  # cosseno (vetores normalizados)
        for i, s in enumerate(scores):
            resultados.append({"arquivo": rel, "trecho": dados["chunks"][i], "score": float(s)})

    resultados.sort(key=lambda r: r["score"], reverse=True)
    return resultados[:top_k]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('uso: python -m assistente.retriever_v2 indexar | "sua pergunta"')
    elif sys.argv[1] == "indexar":
        indexar(forcar=True)
    else:
        for r in buscar(" ".join(sys.argv[1:])):
            print(f"\n[{r['score']:.3f}] {r['arquivo']}")
            print(r["trecho"][:300])


# ============================================================
# PONTE DE COMPATIBILIDADE com o router (cutover v1 -> v2)
# O router espera buscar_notas() devolvendo tuplas (score, arquivo, trecho)
# e usa PLAYBOOKS como caminho. Mantemos os dois nomes sem mexer no resto.
# ============================================================

PLAYBOOKS = Path(VAULT_PATH) / "5-Memory" / "Playbooks"


def buscar_notas(tarefa, pasta=None, top_k=3):
    """Adapta buscar() (dicts) pro formato (score, arquivo, trecho) do router."""
    achados = buscar(tarefa, top_k=top_k)
    return [(a["score"], a["arquivo"], a["trecho"]) for a in achados]

