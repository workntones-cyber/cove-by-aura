"""
llm/ollama.py
Ollama ローカルLLM処理
"""

DISPLAY_NAME     = "Ollama（完全ローカル）"
REQUIRES_API_KEY = False

import json
import urllib.request


def _get_model() -> str:
    """使用するOllamaモデルを.envから取得"""
    from app.services.transcriber import _get_ollama_model
    return _get_ollama_model()


def chat_stream(messages: list, options: dict = None):
    """
    Ollamaにメッセージを送信してストリーミングで返す。
    yield: str（チャンク）
    raises: Exception（接続エラー等）
    """
    default_options = {"num_predict": 1024, "num_ctx": 4096, "temperature": 0.7}
    if options:
        default_options.update(options)

    payload = json.dumps({
        "model":   _get_model(),
        "messages": messages,
        "stream":  True,
        "options": default_options,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=None) as res:
        for line in res:
            line = line.decode("utf-8").strip()
            if not line:
                continue
            try:
                obj   = json.loads(line)
                chunk = obj.get("message", {}).get("content", "")
                if chunk:
                    yield chunk
                if obj.get("done"):
                    break
            except Exception:
                pass


def generate(prompt: str, options: dict = None) -> str:
    """
    Ollamaにプロンプトを送信して結果を返す（非ストリーミング）。
    """
    default_options = {"num_ctx": 4096}
    if options:
        default_options.update(options)

    payload = json.dumps({
        "model":   _get_model(),
        "prompt":  prompt,
        "stream":  False,
        "options": default_options,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=None) as res:
        data = json.loads(res.read().decode("utf-8"))
        return data.get("response", "").strip()


def chat(messages: list, options: dict = None) -> str:
    """
    Ollamaにメッセージを送信して結果を返す（非ストリーミング）。
    """
    default_options = {"num_ctx": 4096, "temperature": 0}
    if options:
        default_options.update(options)

    payload = json.dumps({
        "model":    _get_model(),
        "messages": messages,
        "stream":   False,
        "options":  default_options,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=None) as res:
        data = json.loads(res.read().decode("utf-8"))
        return data.get("message", {}).get("content", "").strip()
