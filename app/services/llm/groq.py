"""
llm/groq.py
Groq API LLM処理
文字起こし：Groq Whisper API（クラウドAPIモード共通）
LLM      ：Groq LLaMA
"""

DISPLAY_NAME     = "Groq (Llama-3.3-70b)"
REQUIRES_API_KEY = True
API_KEY_NAME     = "GROQ_API_KEY"      # .envのキー名
API_KEY_LABEL    = "Groq APIキー"
API_KEY_HINT     = "gsk_..."
API_KEY_URL      = "https://console.groq.com/keys"

LLM_MODEL    = "llama-3.3-70b-versatile"
MAX_TOKENS   = 1024


def _get_client(api_key: str):
    from groq import Groq
    return Groq(api_key=api_key)


def chat_stream(messages: list, api_key: str, options: dict = None):
    """
    Groqにメッセージを送信してストリーミングで返す。
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
    Groqにメッセージを送信して結果を返す（非ストリーミング）。
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
