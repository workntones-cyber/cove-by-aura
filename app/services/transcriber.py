"""
transcriber.py
文字起こし & AI要約サービス

AIモードに応じて以下を切り替える：
  - personal  : Gemini API（クラウド）
  - business  : faster-whisper（完全ローカル）※ Phase 3後半で実装
"""

import time
from pathlib import Path

from google import genai
from google.genai import types

# ── 設定 ──────────────────────────────────────────
UPLOADS_DIR  = Path(__file__).resolve().parent.parent.parent / "uploads"
ENV_PATH     = Path(__file__).resolve().parent.parent.parent / ".env"
MODEL_NAME   = "gemini-2.0-flash"
RETRY_COUNT  = 3    # リトライ回数
RETRY_WAIT   = 20   # 429エラー時のリトライ間隔（秒）
REQUEST_WAIT = 2    # 文字起こし→要約間のウェイト（秒）


# ── .env 読み込み ─────────────────────────────────
def _read_env() -> dict:
    env = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip()
    return env


# ── メイン関数 ────────────────────────────────────
def transcribe_and_summarize(wav_filename: str) -> dict:
    """
    WAVファイルを文字起こし & AI要約する。

    Args:
        wav_filename: uploads/ 配下のファイル名（例: aura_20260101_120000.wav）

    Returns:
        {"status": "done", "transcript": str, "ai_summary": str}
        or {"status": "error", "message": str}
    """
    env     = _read_env()
    ai_mode = env.get("AI_MODE", "personal")

    if ai_mode == "business":
        return _transcribe_faster_whisper(wav_filename)
    else:
        return _transcribe_gemini(wav_filename, env)


# ── Gemini APIリクエスト（リトライ付き） ──────────
def _call_gemini(client, contents: list) -> str:
    """
    429エラー時に RETRY_WAIT 秒待ってリトライする。
    RETRY_COUNT 回失敗したら例外を raise する。
    """
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
            )
            return response.text.strip()
        except Exception as e:
            if "429" in str(e) and attempt < RETRY_COUNT:
                print(f"[transcriber] 429 レート制限 - {RETRY_WAIT}秒後にリトライ ({attempt}/{RETRY_COUNT})")
                time.sleep(RETRY_WAIT)
            else:
                raise


# ── Gemini API（個人用） ───────────────────────────
def _transcribe_gemini(wav_filename: str, env: dict) -> dict:
    api_key = env.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"status": "error", "message": "Gemini APIキーが設定されていません。設定画面で入力してください。"}

    wav_path = UPLOADS_DIR / wav_filename
    if not wav_path.exists():
        return {"status": "error", "message": f"音声ファイルが見つかりません: {wav_filename}"}

    try:
        client      = genai.Client(api_key=api_key)
        audio_bytes = wav_path.read_bytes()

        # ── ① 文字起こし ──────────────────────────
        transcript_prompt = (
            "この音声を正確に文字起こししてください。\n"
            "・話し言葉をそのまま書き起こしてください。\n"
            "・句読点を適切に追加してください。\n"
            "・文字起こし結果のみを出力してください（説明文は不要です）。"
        )

        transcript = _call_gemini(client, [
            transcript_prompt,
            types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
        ])
        print(f"[transcriber] 文字起こし完了: {len(transcript)}文字")

        # リクエスト間のウェイト（レート制限対策）
        time.sleep(REQUEST_WAIT)

        # ── ② AI要約 ──────────────────────────────
        summary_prompt = (
            f"以下の文字起こし内容を要約してください。\n\n"
            f"【文字起こし】\n{transcript}\n\n"
            f"【要約の形式】\n"
            f"・重要なポイントを3〜5つの箇条書きでまとめてください。\n"
            f"・各ポイントは簡潔に1〜2文で記述してください。\n"
            f"・要約のみを出力してください（説明文は不要です）。"
        )

        ai_summary = _call_gemini(client, [summary_prompt])
        print(f"[transcriber] 要約完了: {len(ai_summary)}文字")

        return {
            "status": "done",
            "transcript": transcript,
            "ai_summary": ai_summary,
        }

    except Exception as e:
        print(f"[transcriber] Gemini エラー: {e}")
        return {"status": "error", "message": f"Gemini APIエラー: {str(e)}"}


# ── faster-whisper（ビジネス用） ───────────────────
def _transcribe_faster_whisper(wav_filename: str) -> dict:
    """
    faster-whisper を使ったローカル文字起こし。
    Phase 3後半で実装予定。
    """
    # TODO: Phase 3後半で実装
    # from faster_whisper import WhisperModel
    # model = WhisperModel("large-v3", device="auto")
    # segments, _ = model.transcribe(str(UPLOADS_DIR / wav_filename))
    # transcript = " ".join([seg.text for seg in segments])
    return {
        "status": "error",
        "message": "ビジネス用モード（faster-whisper）は現在実装中です。設定画面で個人用モードに切り替えてください。",
    }
