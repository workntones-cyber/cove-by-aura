"""
llm/openai.py
OpenAI API LLM処理
"""

DISPLAY_NAME     = "OpenAI (GPT-4o)"
REQUIRES_API_KEY = True
API_KEY_NAME     = "OPENAI_API_KEY"
API_KEY_LABEL    = "OpenAI APIキー"
API_KEY_HINT     = "sk-..."
API_KEY_URL      = "https://platform.openai.com/api-keys"

LLM_MODEL  = "gpt-4o"
MAX_TOKENS = 1024


def _get_client(api_key: str):
    from openai import OpenAI
    return OpenAI(api_key=api_key)


def chat_stream(messages: list, api_key: str, options: dict = None):
    """
    OpenAIにメッセージを送信してストリーミングで返す。
    yield: str（チャンク）
    """
    temperature = (options or {}).get("temperature", 0.7)
    client = _get_client(api_key)
    stream = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        max_tokens=MAX_TOKENS,
        temperature=temperature,
        stream=True,
    )
    for chunk_obj in stream:
        chunk = chunk_obj.choices[0].delta.content or ""
        if chunk:
            yield chunk


def chat(messages: list, api_key: str, options: dict = None) -> str:
    """
    OpenAIにメッセージを送信して結果を返す（非ストリーミング）。
    """
    temperature = (options or {}).get("temperature", 0.0)
    max_tokens  = (options or {}).get("max_tokens", MAX_TOKENS)
    client = _get_client(api_key)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()
