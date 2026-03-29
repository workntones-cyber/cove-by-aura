"""
llm/__init__.py
LLMプロバイダーの動的読み込みユーティリティ
"""

import importlib
from pathlib import Path

# 除外ファイル（選択肢に表示しない）
_EXCLUDE = {"__init__", "base"}


def get_all_providers() -> list[dict]:
    """
    llm/配下の.pyファイルをスキャンしてプロバイダー一覧を返す。
    DISPLAY_NAMEが定義されているファイルのみ対象。

    Returns:
        [{"id": "ollama", "name": "Ollama（完全ローカル）", "requires_api_key": False, ...}, ...]
    """
    providers = []
    llm_dir   = Path(__file__).resolve().parent

    for py_file in sorted(llm_dir.glob("*.py")):
        module_name = py_file.stem
        if module_name in _EXCLUDE:
            continue
        try:
            mod = importlib.import_module(f"app.services.llm.{module_name}")
            if not hasattr(mod, "DISPLAY_NAME"):
                continue
            entry = {
                "id":               module_name,
                "name":             mod.DISPLAY_NAME,
                "requires_api_key": getattr(mod, "REQUIRES_API_KEY", False),
                "api_key_name":     getattr(mod, "API_KEY_NAME",     ""),
                "api_key_label":    getattr(mod, "API_KEY_LABEL",    "APIキー"),
                "api_key_hint":     getattr(mod, "API_KEY_HINT",     ""),
                "api_key_url":      getattr(mod, "API_KEY_URL",      ""),
            }
            providers.append(entry)
        except Exception as e:
            print(f"[llm] {module_name} の読み込みをスキップ: {e}")

    return providers


def get_provider(mode: str):
    """
    指定されたモード名のプロバイダーモジュールを返す。
    見つからない場合はNoneを返す。
    """
    if mode in _EXCLUDE:
        return None
    try:
        return importlib.import_module(f"app.services.llm.{mode}")
    except Exception as e:
        print(f"[llm] プロバイダー '{mode}' の読み込みに失敗: {e}")
        return None


def is_local_mode(mode: str) -> bool:
    """OllamaモードはTrue（完全ローカル）、それ以外はFalse"""
    return mode == "ollama"
