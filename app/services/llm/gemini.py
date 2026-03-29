"""
llm/gemini.py
Google Gemini API LLM処理
"""

DISPLAY_NAME     = "Google (Gemini)"
REQUIRES_API_KEY = True
API_KEY_NAME     = "GEMINI_API_KEY"
API_KEY_LABEL    = "Gemini APIキー"
API_KEY_HINT     = "AIza..."
API_KEY_URL      = "https://aistudio.google.com/app/apikey"

LLM_MODEL  = "gemini-2.0-flash"
MAX_TOKENS = 1024


def _get_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


def chat_stream(messages: list, api_key: str, options: dict = None):
    """
    Geminiにメッセージを送信してストリーミングで返す。
    yield: str（チャンク）
    """
    # Gemini形式に変換（systemメッセージはcontentsの先頭userメッセージに統合）
    system_text = ""
    contents    = []
    for m in messages:
        role    = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_text = content
        elif role == "user":
            text = f"{system_text}\n\n{content}" if system_text and not contents else content
            contents.append({"role": "user", "parts": [{"text": text}]})
            system_text = ""
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})

    client = _get_client(api_key)
    stream = client.models.generate_content_stream(
        model=LLM_MODEL,
        contents=contents,
    )
    for chunk in stream:
        text = chunk.text or ""
        if text:
            yield text


def chat(messages: list, api_key: str, options: dict = None) -> str:
    """
    Geminiにメッセージを送信して結果を返す（非ストリーミング）。
    """
    system_text = ""
    contents    = []
    for m in messages:
        role    = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_text = content
        elif role == "user":
            text = f"{system_text}\n\n{content}" if system_text and not contents else content
            contents.append({"role": "user", "parts": [{"text": text}]})
            system_text = ""
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})

    client   = _get_client(api_key)
    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=contents,
    )
    return response.text.strip()
