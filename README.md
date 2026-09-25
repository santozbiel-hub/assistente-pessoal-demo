# Assistente Pessoal

O código do assistente está em [`sistema/`](sistema/): backend Python/FastAPI, roteamento de provedores, memória, controles de confiança e interface HTML. A demonstração estática antiga na raiz permanece separada e usa respostas simuladas.

Conversas, memórias, documentos pessoais, tokens e arquivos de ambiente do projeto original não foram incluídos. Agenda e transações começam vazias. O nome foi generalizado, inclusive no namespace Python e variáveis de configuração.

## Executar
```sh
cd sistema
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r backend/requirements_web.txt
cp .env.example .env
# Defina um token próprio e configure o provedor escolhido.
mkdir -p vault/System vault/5-Memory
uvicorn backend.api:app --host 127.0.0.1 --port 8420
```
Em outro terminal, rode `python -m http.server 8080 --directory sistema/frontend` na raiz do repositório. Abra http://localhost:8080 e informe a URL local da API e o token configurado.

Personalize o prompt em `vault/System/prompt-base.md`. O conteúdo de vault não é versionado. Confira o restante dos arquivos esperados em `assistente/memory.py` para ampliar a memória. O fluxo de terminal é iniciado com `python main.py` dentro de sistema.

## Limites
O chat real depende de um provedor e configuração local. O adaptador original pode retornar um eco quando o núcleo não está disponível; isso não é uma resposta de modelo. O servidor mantém uma conversa em memória e não é uma aplicação multiusuário. Esta publicação não inclui a interface experimental separada nem pressupõe sua integração com a API.

O objetivo é tornar o código inspecionável e reutilizável, mantendo privados os dados do projeto original. Use um ambiente próprio para testar integrações e persistência.
