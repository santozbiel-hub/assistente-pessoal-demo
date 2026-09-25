"""
Modulo seletor da ASSISTENTE - Sistema hibrido em 2 camadas.

Camada 1: Filtro local por keywords (rapido, gratis, deterministico)
Camada 2: Haiku LLM (inteligente, pago, fallback pra casos ambiguos)

Filosofia: so paga Haiku quando filtro local nao tem certeza.
"""

import json
from anthropic import Anthropic
from assistente import config


# Modelo barato pra fallback
SELECTOR_MODEL = "claude-haiku-4-5-20251001"

# Mostrar logs de debug do selector?
DEBUG = False


# ============================================================
# CAMADA 1 - FILTRO LOCAL
# ============================================================

# Keywords que indicam claramente cada tipo de memoria
KEYWORDS_RELATIONSHIPS = [
    "pai", "mae", "mãe", "irma", "irmã", "irmao", "irmão",
    "familia", "família", "parente", "namorada", "namorado",
    "amigo", "amiga", "amizade", "equipe", "colega",
    "pessoa", "alguem", "alguém", "conhecido"
]

KEYWORDS_DECISIONS = [
    "decidi", "decisao", "decisão", "escolhi", "escolha",
    "vou fazer", "vou comecar", "vou começar",
    "optei", "preferi", "concluido", "concluí",
    "definido", "resolvi"
]

KEYWORDS_TECH = [
    "python", "codigo", "código", "programa", "script",
    "bug", "erro", "como funciona", "explica", "tutorial",
    "javascript", "react", "html", "css", "sql",
    "algoritmo", "funcao", "função", "loop", "variavel",
    "git", "github", "terminal", "comando bash"
]

# Mensagens curtas que sao saudacoes/respostas simples
GREETINGS = [
    "oi", "ola", "olá", "hey", "e ai", "e aí",
    "tudo bem", "bom dia", "boa tarde", "boa noite",
    "valeu", "obrigado", "obrigada", "vlw", "ok",
    "sim", "nao", "não", "tranquilo"
]


def has_keyword(message: str, keywords: list) -> bool:
    """Verifica se a mensagem contem alguma das keywords."""
    msg = message.lower()
    return any(kw in msg for kw in keywords)


def is_short_greeting(message: str) -> bool:
    """Detecta saudacoes ou respostas curtas."""
    msg = message.lower().strip()
    if len(msg) <= 5:
        return True
    return any(msg == g or msg.startswith(g + " ") or msg.startswith(g + ",")
               for g in GREETINGS)


def has_ambiguous_pronoun(message: str) -> bool:
    """Detecta pronomes que podem indicar referencia a pessoa."""
    msg = message.lower()
    pronouns_alone = [" ele ", " ela ", " eles ", " elas ", " dele ", " dela "]
    return any(p in f" {msg} " for p in pronouns_alone)


def local_filter(user_message: str) -> dict:
    """
    Filtro local em camada 1.
    Retorna dict com 'confident' (bool), 'result' (dict) e 'reason' (str).
    """
    msg_lower = user_message.lower()

    # Saudacao -> nao precisa de memoria opcional
    if is_short_greeting(user_message):
        return {
            "confident": True,
            "result": {
                "relationships": False,
                "decisions_log": False,
                "skills_learned": False,
            },
            "reason": "saudacao curta"
        }

    # Detecta sinais
    has_relationship = has_keyword(user_message, KEYWORDS_RELATIONSHIPS)
    has_decision = has_keyword(user_message, KEYWORDS_DECISIONS)
    has_tech = has_keyword(user_message, KEYWORDS_TECH)
    has_pronoun = has_ambiguous_pronoun(user_message)

    # Pergunta tecnica clara, sem pessoas
    if has_tech and not has_relationship and not has_decision:
        return {
            "confident": True,
            "result": {
                "relationships": False,
                "decisions_log": False,
                "skills_learned": True,  # mantem aprendizado tecnico
            },
            "reason": "pergunta tecnica clara"
        }

    # Menciona pessoa explicitamente
    if has_relationship and not has_pronoun:
        return {
            "confident": True,
            "result": {
                "relationships": True,
                "decisions_log": has_decision,
                "skills_learned": True,
            },
            "reason": "pessoa mencionada explicitamente"
        }

    # Decisao clara, sem pessoas envolvidas
    if has_decision and not has_relationship and not has_pronoun:
        return {
            "confident": True,
            "result": {
                "relationships": False,
                "decisions_log": True,
                "skills_learned": True,
            },
            "reason": "decisao mencionada explicitamente"
        }

    # Ambiguo: pronome solto, ou mensagem media sem keywords
    return {
        "confident": False,
        "result": None,
        "reason": "ambiguo - precisa de Haiku"
    }


# ============================================================
# CAMADA 2 - HAIKU LLM (FALLBACK)
# ============================================================

def haiku_decide(user_message: str) -> dict:
    """Camada 2: usa Haiku pra decidir em casos ambiguos."""
    fallback = {
        "relationships": True,
        "decisions_log": True,
        "skills_learned": True,
    }

    if not config.ANTHROPIC_API_KEY:
        return fallback

    try:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

        prompt = f"""Decida quais arquivos de memoria carregar para responder a mensagem.

ARQUIVOS:
- relationships: pessoas (familia, amigos, equipes, namorada)
- decisions_log: decisoes importantes do usuario
- skills_learned: padroes observados sobre o usuario

MENSAGEM: "{user_message}"

Responda APENAS no formato JSON, sem explicacoes:
{{"relationships": true/false, "decisions_log": true/false, "skills_learned": true/false}}"""

        response = client.messages.create(
            model=SELECTOR_MODEL,
            max_tokens=100,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()

        # Limpa possivel markdown
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)

        return {
            "relationships": bool(result.get("relationships", True)),
            "decisions_log": bool(result.get("decisions_log", True)),
            "skills_learned": bool(result.get("skills_learned", True)),
        }

    except Exception as e:
        if DEBUG:
            print(f"[selector] Haiku falhou, fallback: {e}")
        return fallback


# ============================================================
# ORQUESTRADOR (USAR ESTA FUNCAO)
# ============================================================

def decide_optional_memories(user_message: str) -> dict:
    """
    Sistema hibrido em 2 camadas.
    Retorna decisao de quais memorias opcionais carregar.
    """
    # CAMADA 1: Filtro local
    local = local_filter(user_message)

    if local["confident"]:
        if DEBUG:
            print(f"[selector] Local: {local['reason']}")
        return local["result"]

    # CAMADA 2: Haiku (so se local nao teve certeza)
    if DEBUG:
        print(f"[selector] Local: {local['reason']}")
        print(f"[selector] Consultando Haiku...")

    decision = haiku_decide(user_message)

    if DEBUG:
        loaded = [k for k, v in decision.items() if v]
        print(f"[selector] Haiku decidiu: {loaded}")

    return decision


def show_filter_test(user_message: str) -> None:
    """Funcao de debug pra testar o filtro com uma mensagem."""
    print("=" * 60)
    print(f"  TESTE DO SELETOR")
    print(f"  Mensagem: '{user_message}'")
    print("=" * 60)

    local = local_filter(user_message)
    print(f"\n  Camada 1 (local):")
    print(f"    Confiante: {local['confident']}")
    print(f"    Razao: {local['reason']}")

    if local["confident"]:
        print(f"    Resultado: {local['result']}")
        print(f"\n  Haiku NAO foi chamado (economia)")
    else:
        print(f"\n  Camada 2 (Haiku): seria chamada aqui")

    print("=" * 60)

