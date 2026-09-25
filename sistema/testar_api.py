try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import anthropic

client = anthropic.Anthropic()  # le ANTHROPIC_API_KEY do ambiente
resp = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=50,
    messages=[{"role": "user", "content": "Diga apenas: ASSISTENTE online."}],
)
print(resp.content[0].text)

