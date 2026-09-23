# Assistente Pessoal

Protótipo interativo, independente, com identidade genérica e dados fictícios.

## Problema

Tarefas e notas separadas tornam mais difícil consultar o contexto do dia.

## Experimente

Consultar respostas programadas; criar, concluir e remover tarefas; criar e remover notas; consultar o estado atual da agenda e das notas pela conversa.

1. Adicione uma tarefa na Agenda.
2. Pergunte sobre sua agenda na Conversa.
3. Crie uma nota e use Consultar notas para verificar seu conteúdo.

## Executar localmente

Com Python 3 instalado, execute na pasta do repositório:

```bash
python3 -m http.server 8080
```

Abra http://localhost:8080. Não são necessárias contas, credenciais, instalação de pacotes ou configuração de banco.

## Tecnologias e decisões

- HTML semântico, CSS responsivo e JavaScript sem dependências de execução.
- Estado somente em memória: recarregar restaura o cenário de demonstração.
- Conteúdo de formulários escapado antes de ser inserido no HTML.
- Política de conteúdo bloqueia conexões externas da aplicação.
- Nomes, clientes, veículos e registros são demonstrativos.

## Limites

As respostas são programadas: não há modelo de IA, RAG, acesso a documentos, automação externa ou envio de mensagens. Não use este protótipo para registros reais. Os dados desaparecem ao recarregar.

## Estrutura

- `index.html`: estrutura e navegação.
- `style.css`: estilos responsivos.
- `app.js`: conversa programada, tarefas e notas.

## Licença

Nenhuma licença de código aberto foi concedida neste repositório.
