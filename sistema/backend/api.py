"""
ASSISTENTE Web API — ponte entre o frontend (site/app) e o cérebro da ASSISTENTE
(assistente.brain / assistente.router) que já roda no seu Mac.

Como rodar:
    cd sistema
    source .venv312/bin/activate
    pip install -r backend/requirements_web.txt
    uvicorn backend.api:app --host 0.0.0.0 --port 8420

Depois de rodar com Tailscale ativo, você acessa de qualquer lugar em:
    http://<seu-ip-tailscale>:8420

Segurança (ADR-013 continua valendo aqui):
    - API_TOKEN vem do .env, nunca fica hardcoded.
    - Todo endpoint (exceto /health) exige header:
        Authorization: Bearer <API_TOKEN>
    - Não expõe nada além do necessário: sem stack trace bruto pro cliente.
"""

import os
import json
import secrets
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

API_TOKEN = os.getenv("ASSISTENTE_WEB_TOKEN")
if not API_TOKEN:
    # gera um token uma vez e avisa — assim você nunca commita um token fixo
    API_TOKEN = secrets.token_urlsafe(32)
    print(f"[ASSISTENTE-WEB] ASSISTENTE_WEB_TOKEN não estava no .env. Gerado agora:\n{API_TOKEN}")
    print("[ASSISTENTE-WEB] Coloque essa linha no seu .env: ASSISTENTE_WEB_TOKEN=" + API_TOKEN)

DATA_DIR = Path(os.getenv("ASSISTENTE_WEB_DATA_DIR", Path(__file__).parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
FINANCE_FILE = DATA_DIR / "transacoes.json"
AGENDA_FILE = DATA_DIR / "agenda.json"

for f in (FINANCE_FILE, AGENDA_FILE):
    if not f.exists():
        f.write_text("[]", encoding="utf-8")

# --------------------------------------------------------------------------
# Ponte com o cérebro real da ASSISTENTE
# --------------------------------------------------------------------------
# TODO: ajuste o import e a chamada abaixo pro nome real do método em
# assistente/brain.py (ex: Brain().responder(msg) ou Brain().process(msg)).
# Deixei um adaptador com fallback pra você poder testar o site mesmo
# antes de plugar o backend de verdade.

_assistente_brain = None
_assistente_disponivel = False

try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raiz do assistente
    from assistente import router as assistente_router_module
    from assistente import memory_writer as assistente_memory_writer
    from assistente.conversation import Conversation as AssistenteConversation

    _assistente_disponivel = True
except Exception as e:
    assistente_router_module = None
    assistente_memory_writer = None
    AssistenteConversation = None
    _assistente_disponivel = False
    print(f"[ASSISTENTE-WEB] Não consegui importar assistente.router ainda ({e}).")
    print("[ASSISTENTE-WEB] Rodando em modo STUB — o chat responde um eco até você plugar de verdade.")

# uma unica conversa em memoria pra sessao do servidor web (single-user).
# zera quando o uvicorn reinicia -- se quiser persistir entre restarts,
# isso vira um proximo passo (salvar/carregar via Conversation.save()).
_conversa_web = AssistenteConversation() if _assistente_disponivel else None


def perguntar_assistente(mensagem: str) -> str:
    if _assistente_disponivel and assistente_router_module is not None:
        # 1) confere se havia proposta de memoria "nivel alto" aguardando sua aprovacao
        assistente_memory_writer.process_pending(_conversa_web, mensagem)
        # 2) gera a resposta pela cascata Gemini -> Haiku -> Sonnet, com identidade completa
        resposta_bruta = assistente_router_module.conversar(
            mensagem,
            historico=_conversa_web.get_history(),
        )
        # DEBUG TEMPORARIO: confirma se o modelo gerou bloco de proposta de memoria
        tem_proposta = "[||MEM||]" in resposta_bruta
        print(f"[DEBUG-MEM] resposta contem bloco [||MEM||]? {tem_proposta} (tamanho: {len(resposta_bruta)} chars)")

        # 3) processa propostas [||MEM||] novas (escreve direto ou guarda p/ aprovacao)
        resposta_limpa = assistente_memory_writer.process_response(resposta_bruta, _conversa_web)
        _conversa_web.add_user_message(mensagem)
        _conversa_web.add_assistant_message(resposta_limpa)
        return resposta_limpa
    return f"[STUB] ainda não conectada ao assistente.router — você disse: {mensagem}"


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------

app = FastAPI(title="ASSISTENTE Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],  # uso pessoal via Tailscale; aperte isso se expuser publicamente
    allow_methods=["*"],
    allow_headers=["*"],
)


def checar_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, API_TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido")
    return True


# --------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------

class ChatIn(BaseModel):
    mensagem: str = Field(..., min_length=1)


class ChatOut(BaseModel):
    resposta: str
    timestamp: str


@app.post("/api/chat", response_model=ChatOut)
def chat(payload: ChatIn, _=Depends(checar_token)):
    try:
        resposta = perguntar_assistente(payload.mensagem)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar ASSISTENTE: {e}")
    return ChatOut(resposta=resposta, timestamp=datetime.now().isoformat())


# --------------------------------------------------------------------------
# Financeiro
# --------------------------------------------------------------------------
# Estrutura pensada pra já receber dados do Pluggy (Open Finance) depois:
# cada transação tem categoria, valor, data, origem ("manual" | "pluggy").

class Transacao(BaseModel):
    descricao: str
    valor: float  # negativo = gasto, positivo = entrada
    categoria: str = "outros"
    data: str = Field(default_factory=lambda: date.today().isoformat())
    origem: str = "manual"


def _ler_transacoes():
    return json.loads(FINANCE_FILE.read_text(encoding="utf-8"))


def _salvar_transacoes(lista):
    FINANCE_FILE.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/api/finance/summary")
def finance_summary(_=Depends(checar_token)):
    transacoes = _ler_transacoes()
    mes_atual = date.today().strftime("%Y-%m")
    do_mes = [t for t in transacoes if t["data"].startswith(mes_atual)]

    entradas = sum(t["valor"] for t in do_mes if t["valor"] > 0)
    saidas = sum(t["valor"] for t in do_mes if t["valor"] < 0)
    saldo = entradas + saidas

    por_categoria = {}
    for t in do_mes:
        if t["valor"] < 0:
            por_categoria[t["categoria"]] = por_categoria.get(t["categoria"], 0) + abs(t["valor"])

    return {
        "mes": mes_atual,
        "entradas": round(entradas, 2),
        "saidas": round(abs(saidas), 2),
        "saldo": round(saldo, 2),
        "por_categoria": por_categoria,
        "total_transacoes": len(do_mes),
        "open_finance_conectado": False,  # muda pra True quando plugar Pluggy
    }


@app.get("/api/finance/transacoes")
def listar_transacoes(_=Depends(checar_token)):
    return sorted(_ler_transacoes(), key=lambda t: t["data"], reverse=True)


@app.post("/api/finance/transacoes")
def criar_transacao(t: Transacao, _=Depends(checar_token)):
    transacoes = _ler_transacoes()
    transacoes.append(t.model_dump())
    _salvar_transacoes(transacoes)
    return {"ok": True}


# --------------------------------------------------------------------------
# Agenda
# --------------------------------------------------------------------------

class Evento(BaseModel):
    titulo: str
    data: str  # ISO: 2026-07-20 ou 2026-07-20T14:00
    descricao: str = ""
    categoria: str = "geral"  # geral | faculdade | EquipeB | EquipeA | financeiro


def _ler_agenda():
    return json.loads(AGENDA_FILE.read_text(encoding="utf-8"))


def _salvar_agenda(lista):
    AGENDA_FILE.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/api/agenda")
def listar_agenda(_=Depends(checar_token)):
    eventos = _ler_agenda()
    hoje = date.today().isoformat()
    futuros = [e for e in eventos if e["data"] >= hoje]
    return sorted(futuros, key=lambda e: e["data"])


@app.post("/api/agenda")
def criar_evento(e: Evento, _=Depends(checar_token)):
    eventos = _ler_agenda()
    eventos.append(e.model_dump())
    _salvar_agenda(eventos)
    return {"ok": True}


# --------------------------------------------------------------------------
# Status / health
# --------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "assistente_conectada": _assistente_disponivel,
        "timestamp": datetime.now().isoformat(),
    }

