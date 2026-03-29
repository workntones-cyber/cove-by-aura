"""
llm/claude.py
Anthropic Claude API LLM処理
"""

DISPLAY_NAME     = "Anthropic (Claude)"
REQUIRES_API_KEY = True
API_KEY_NAME     = "ANTHROPIC_API_KEY"
API_KEY_LABEL    = "Anthropic APIキー"
API_KEY_HINT     = "sk-ant-..."
API_KEY_URL      = "https://console.anthropic.com/settings/keys"

LLM_MODEL  = "claude-sonnet-4-6"
MAX_TOKENS = 1024


def _get_client(api_key: str):
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def chat_stream(messages: list, api_key: str, options: dict = None):
    """
    Claudeにメッセージを送信してストリーミングで返す。
    yield: str（チャンク）
    """
    temperature = (options or {}).get("temperature", 0.7)

    # Anthropic APIはsystemを別パラメータで渡す
    system_text    = ""
    filtered_msgs  = []
    for m in messages:
        role    = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_text = content
        else:
            filtered_msgs.append({"role": role, "content": content})

    client = _get_client(api_key)
    kwargs = dict(
        model=LLM_MODEL,
        max_tokens=MAX_TOKENS,
        messages=filtered_msgs,
        temperature=temperature,
    )
    if system_text:
        kwargs["system"] = system_text

    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            if text:
                yield text


def chat(messages: list, api_key: str, options: dict = None) -> str:
    """
    Claudeにメッセージを送信して結果を返す（非ストリーミング）。
    """
    temperature   = (options or {}).get("temperature", 0.0)
    max_tokens    = (options or {}).get("max_tokens", MAX_TOKENS)
    system_text   = ""
    filtered_msgs = []
    for m in messages:
        role    = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_text = content
        else:
            filtered_msgs.append({"role": role, "content": content})

    client = _get_client(api_key)
    kwargs = dict(
        model=LLM_MODEL,
        max_tokens=max_tokens,
        messages=filtered_msgs,
        temperature=temperature,
    )
    if system_text:
        kwargs["system"] = system_text

    resp = client.messages.create(**kwargs)
    return resp.content[0].text.strip()
