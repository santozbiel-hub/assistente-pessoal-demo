# assistente/router.py
"""Decide entre modelo FRACO (usa memoria) e modelo FORTE (aprende e grava)."""
import re
from datetime import date
from assistente.retriever import buscar_notas, PLAYBOOKS
from assistente import brain
from assistente import providers
from assistente import config

LIMIAR = 0.40                                  # score minimo pra confiar
WEAK_MODEL = "claude-haiku-4-5-20251001"    # barato/rapido
STRONG_MODEL = config.MODEL                 # o que ja esta configurado (Opus/Sonnet)


def executar_tarefa(tarefa: str) -> str:
    notas = buscar_notas(tarefa)
    melhor_score = notas[0][0] if notas else 0

    if melhor_score >= LIMIAR:
        print(f"[ROUTER] memoria encontrada (score {melhor_score}) -> modelo FRACO")
        contexto = "\n\n---\n\n".join(n[2] for n in notas)
        return _executar_fraco(tarefa, contexto)

    print("[ROUTER] tarefa nova -> modelo FORTE (vai aprender e gravar)")
    resultado, playbook = _executar_forte(tarefa)
    if _verificar(tarefa, resultado):
        _salvar_playbook(tarefa, playbook)
        print("[ROUTER] playbook salvo na memoria")
    return resultado


# ---- caminho barato (cascata: Gemini -> Haiku -> Sonnet) -----------
def _executar_fraco(tarefa: str, contexto: str) -> str:
    prompt = (
        "Use SOMENTE o procedimento abaixo pra executar a tarefa. "
        "Siga os passos na ordem.\n\n"
        f"=== MEMORIA ===\n{contexto}\n\n=== TAREFA ===\n{tarefa}"
    )

    # degrau 1: Gemini (mais barato)
    if providers.is_gemini_available():
        try:
            resultado = providers.call_gemini(prompt)
            print("[ROUTER] respondido por: gemini")
            return resultado
        except providers.GeminiError as e:
            print(f"[ROUTER] gemini falhou ({e}) -> tentando haiku")

    # degrau 2: Haiku
    try:
        resultado = brain.send_message(prompt, model=WEAK_MODEL, fallback_to_ollama=False)
        if _verificar(tarefa, resultado):
            print("[ROUTER] respondido por: haiku")
            return resultado
        print("[ROUTER] haiku nao resolveu -> escalando pra sonnet")
    except Exception as e:
        print(f"[ROUTER] haiku falhou ({e}) -> escalando pra sonnet")

    # degrau 3: Sonnet (rede de seguranca)
    resultado = brain.send_message(prompt, model=STRONG_MODEL)
    print("[ROUTER] respondido por: sonnet (fallback da cascata fraca)")
    return resultado


# ---- caminho de CONVERSA (nao tarefa) -------------------------------
def conversar(mensagem: str, historico: list = None) -> str:
    """
    Diferente de executar_tarefa(): usa a identidade completa da ASSISTENTE
    (build_essential_system/build_optional_system) e tenta a cascata
    Gemini -> Haiku -> Sonnet, cada degrau falhando rapido
    (fallback_to_ollama=False) pra nao travar 30+ min numa requisicao web.
    O texto retornado pode conter blocos [||MEM||]...[||/MEM||] -- quem
    chama essa funcao e responsavel por passar o resultado pelo
    memory_writer, igual o main.py ja faz.
    """
    if historico is None:
        historico = []

    essential = brain.build_essential_system()
    decision = {"relationships": True, "decisions_log": True, "skills_learned": True}
    optional = brain.build_optional_system(decision)
    system_completo = essential + ("\n\n" + optional if optional else "")

    # degrau 1: Gemini (mais barato, identidade completa via param 'system')
    if providers.is_gemini_available():
        historico_texto = "\n".join(
            f"{'Voce' if m['role'] == 'user' else 'ASSISTENTE'}: {m['content']}"
            for m in historico[-6:]
        )
        prompt_gemini = f"{historico_texto}\n\nVoce: {mensagem}" if historico_texto else mensagem
        try:
            resultado = providers.call_gemini(prompt_gemini, system=system_completo)
            print("[ROUTER] conversa respondida por: gemini")
            return resultado
        except providers.GeminiError as e:
            print(f"[ROUTER] gemini falhou ({e}) -> tentando haiku")

    # degrau 2: Haiku (falha rapido, sem cair pro Ollama)
    resultado = brain.send_message(
        mensagem,
        conversation_history=historico,
        model=WEAK_MODEL,
        fallback_to_ollama=False,
    )
    if not _resposta_com_erro(resultado):
        print("[ROUTER] conversa respondida por: haiku")
        return resultado
    print(f"[ROUTER] haiku falhou ({resultado[:80]}) -> escalando pra sonnet")

    # degrau 3: Sonnet (rede de seguranca, tambem falha rapido)
    resultado = brain.send_message(
        mensagem,
        conversation_history=historico,
        model=STRONG_MODEL,
        fallback_to_ollama=False,
    )
    if _resposta_com_erro(resultado):
        if _parece_erro_de_rede(resultado):
            print(f"[ROUTER] sonnet falhou por rede ({resultado[:80]}) -- tentando Ollama local (sem internet)")
            return _conversar_ollama(mensagem)
        print(f"[ROUTER] sonnet tambem falhou ({resultado[:80]}) -- cascata inteira sem resposta")
        return (
            "Opa, deu ruim aqui do meu lado -- nao consegui gerar uma resposta agora "
            "(deve ser questao de credito ou conexao). Tenta de novo daqui a pouco?"
        )
    print("[ROUTER] conversa respondida por: sonnet")
    return resultado


def _parece_erro_de_rede(texto: str) -> bool:
    """
    Tenta diferenciar 'sem internet' de 'sem credito/limite'. Nao e
    perfeito, mas cobre os sinais mais comuns de falha de conexao.
    """
    sinais_rede = [
        "connection", "timeout", "timed out", "network", "unreachable",
        "resolve", "getaddrinfo", "max retries", "connectionpool",
        "econnrefused", "name or service not known",
    ]
    texto_lower = texto.lower()
    return any(sinal in texto_lower for sinal in sinais_rede)


def _conversar_ollama(mensagem: str) -> str:
    """
    Ultimo recurso: Ollama local, usado so quando a nuvem inteira falhou
    por rede (nao por credito). Nao tenta manter personalidade/conversa
    -- so responde com base no que a busca semantica encontrar na
    memoria (buscar_notas), com um prompt minimo -- bem mais rapido em
    CPU do que carregar o prompt-base.md inteiro. Nunca escreve
    memoria -- qualquer bloco [||MEM||] que aparecer e removido a
    forca, mesmo que o modelo tente (defesa em profundidade).
    """
    notas = buscar_notas(mensagem)
    contexto = "\n\n---\n\n".join(n[2] for n in notas) if notas else "(nenhuma memoria relevante encontrada)"

    system_minimo = (
        "Voce esta respondendo em modo offline de emergencia (sem internet). "
        "Responda de forma direta e objetiva, usando APENAS o contexto de memoria abaixo. "
        "Se a memoria nao tiver a resposta, diga que nao sabe. Nao invente informacao.\n\n"
        f"=== MEMORIA RELEVANTE ===\n{contexto}"
    )

    try:
        resultado = providers.call_ollama(mensagem, system=system_minimo, timeout=180)
    except providers.OllamaError as e:
        print(f"[ROUTER] Ollama tambem falhou ({e})")
        return (
            "Opa, parece que nem minha conexao nem o modelo local aqui estao respondendo agora. "
            "Tenta de novo daqui a pouco?"
        )
    resultado_limpo = re.sub(r"\[\|\|MEM\|\|\].*?\[\|\|/MEM\|\|\]", "", resultado, flags=re.DOTALL)
    print("[ROUTER] conversa respondida por: ollama local (sem internet, modo minimo)")
    return resultado_limpo.strip()


def _resposta_com_erro(resultado: str) -> bool:
    """
    Mesma ideia do _verificar(), mas cobre tambem o prefixo [BUDGET/ERRO]
    que o _verificar() atual nao pega (so cobre "[ERRO").
    """
    if not resultado:
        return True
    return resultado.startswith("[ERRO") or resultado.startswith("[BUDGET/ERRO")


# ---- caminho caro (aprende) ----------------------------------------
def _executar_forte(tarefa: str) -> tuple[str, str]:
    # 1) modelo forte executa a tarefa
    resultado = brain.send_message(tarefa, model=STRONG_MODEL)

    # 2) modelo forte DESTILA um playbook pro modelo fraco repetir sozinho
    prompt_destilacao = (
        "Voce acabou de resolver a tarefa abaixo. Escreva um PLAYBOOK que um "
        "modelo de IA mais simples consiga seguir sozinho no futuro, SEM voce. "
        "Use: passos numerados curtos + 1 exemplo concreto. Seja literal.\n\n"
        f"TAREFA: {tarefa}\n\nSOLUCAO: {resultado}"
    )
    playbook = brain.send_message(prompt_destilacao, model=STRONG_MODEL)
    return resultado, playbook


# ---- guarda-corpo anti-envenenamento -------------------------------
def _verificar(tarefa: str, resultado: str) -> bool:
    if not resultado or resultado.startswith("[ERRO"):
        return False
    # Respostas vindas do fallback Ollama local nunca viram playbook -
    # contexto cortado/modelo mais fraco pode gravar erro como se fosse
    # conhecimento solido. Ollama so responde, nunca ensina a ASSISTENTE.
    if resultado.startswith("[OLLAMA LOCAL]"):
        print("[ROUTER] Resposta veio do Ollama local - playbook NAO sera salvo")
        return False
    return True


# ---- escreve na memoria (formato otimizado pro fraco) --------------
def _salvar_playbook(tarefa: str, playbook: str) -> None:
    PLAYBOOKS.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"\W+", "-", tarefa.lower()).strip("-")[:50]
    arquivo = PLAYBOOKS / f"{slug}.md"
    arquivo.write_text(
        f"# Playbook: {tarefa}\n\n"
        f"**Aprendido em:** {date.today()}\n"
        f"**Origem:** modelo forte destilou pra modelos fracos\n\n"
        f"---\n\n{playbook}\n",
        encoding="utf-8",
    )

