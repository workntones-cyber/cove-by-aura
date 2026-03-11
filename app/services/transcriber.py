"""
transcriber.py
文字起こし & AI要約サービス

AIモードに応じて以下を切り替える：
  - personal  : Groq API（Whisper文字起こし + LLaMA要約）
  - business  : faster-whisper（完全ローカル）※ Phase 3後半で実装
"""

import time
from pathlib import Path

from groq import Groq

# ── 設定 ──────────────────────────────────────────
UPLOADS_DIR        = Path(__file__).resolve().parent.parent.parent / "uploads"
ENV_PATH           = Path(__file__).resolve().parent.parent.parent / ".env"
WHISPER_MODEL      = "whisper-large-v3-turbo"   # 文字起こし用
SUMMARY_MODEL      = "llama-3.3-70b-versatile"  # 要約用
RETRY_COUNT        = 3
RETRY_WAIT         = 30  # 429エラー時のリトライ間隔（秒）


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
        return _transcribe_groq(wav_filename, env)


# ── Groq API（個人用） ────────────────────────────
def _transcribe_groq(wav_filename: str, env: dict) -> dict:
    api_key = env.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "error",
            "message": "Groq APIキーが設定されていません。設定画面で入力してください。",
        }

    wav_path = UPLOADS_DIR / wav_filename
    if not wav_path.exists():
        return {"status": "error", "message": f"音声ファイルが見つかりません: {wav_filename}"}

    try:
        client = Groq(api_key=api_key)

        # ── ① 文字起こし（Whisper） ───────────────
        print(f"[transcriber] 文字起こし開始: {wav_filename}")
        transcript = _call_whisper(client, wav_path)
        print(f"[transcriber] 文字起こし完了: {len(transcript)}文字")

        # ── ② 要約（LLaMA） ──────────────────────
        print(f"[transcriber] 要約開始")
        ai_summary = _call_llama(client, transcript)
        print(f"[transcriber] 要約完了: {len(ai_summary)}文字")

        return {
            "status": "done",
            "transcript": transcript,
            "ai_summary": ai_summary,
        }

    except Exception as e:
        print(f"[transcriber] Groq エラー: {e}")
        return {"status": "error", "message": f"Groq APIエラー: {str(e)}"}


# ── Whisper 文字起こし（チャンク対応・リトライ付き） ──
def _call_whisper(client: Groq, wav_path: Path) -> str:
    """
    WAVファイルを25MB以下のチャンクに分割してWhisperに送信し、
    結果を結合して返す。
    """
    MAX_BYTES = 24 * 1024 * 1024  # 25MB制限に対して余裕を持って24MBに設定

    file_size = wav_path.stat().st_size
    print(f"[transcriber] ファイルサイズ: {file_size / 1024 / 1024:.1f}MB")

    if file_size <= MAX_BYTES:
        # 25MB以下はそのまま送信
        return _send_to_whisper(client, wav_path)

    # 25MB超の場合は時間ベースで分割して送信
    print(f"[transcriber] ファイルが大きいため分割して送信します")
    chunks     = _split_wav(wav_path, MAX_BYTES)
    transcripts = []

    for i, chunk_path in enumerate(chunks):
        print(f"[transcriber] チャンク {i+1}/{len(chunks)} を送信中...")
        text = _send_to_whisper(client, chunk_path)
        transcripts.append(text)
        chunk_path.unlink()  # 一時チャンクを削除

    return " ".join(transcripts)


def _send_to_whisper(client: Groq, wav_path: Path) -> str:
    """単一ファイルをWhisperに送信する（リトライ付き）"""
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            with open(wav_path, "rb") as f:
                response = client.audio.transcriptions.create(
                    file=(wav_path.name, f.read()),
                    model=WHISPER_MODEL,
                    response_format="text",
                    language="ja",
                    temperature=0.0,
                )
            return response.strip() if isinstance(response, str) else response.text.strip()
        except Exception as e:
            if "429" in str(e) and attempt < RETRY_COUNT:
                print(f"[transcriber] 429 レート制限 - {RETRY_WAIT}秒後にリトライ ({attempt}/{RETRY_COUNT})")
                time.sleep(RETRY_WAIT)
            else:
                raise


def _split_wav(wav_path: Path, max_bytes: int) -> list[Path]:
    """WAVファイルをmax_bytes以下のチャンクに分割して一時ファイルとして保存する"""
    import wave as wave_module
    import math

    with wave_module.open(str(wav_path), "rb") as wf:
        n_channels  = wf.getnchannels()
        sampwidth   = wf.getsampwidth()
        framerate   = wf.getframerate()
        n_frames    = wf.getnframes()
        raw         = wf.readframes(n_frames)

    bytes_per_frame  = n_channels * sampwidth
    frames_per_chunk = max_bytes // bytes_per_frame
    total_chunks     = math.ceil(n_frames / frames_per_chunk)
    chunk_paths      = []

    for i in range(total_chunks):
        start      = i * frames_per_chunk * bytes_per_frame
        end        = min(start + frames_per_chunk * bytes_per_frame, len(raw))
        chunk_raw  = raw[start:end]
        chunk_path = wav_path.parent / f"{wav_path.stem}_tmp{i}.wav"

        with wave_module.open(str(chunk_path), "wb") as wf:
            wf.setnchannels(n_channels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(framerate)
            wf.writeframes(chunk_raw)

        chunk_paths.append(chunk_path)
        print(f"[transcriber] 分割チャンク作成: {chunk_path.name} ({len(chunk_raw)/1024/1024:.1f}MB)")

    return chunk_paths


# ── LLaMA 要約（リトライ付き） ────────────────────
def _call_llama(client: Groq, transcript: str) -> str:
    prompt = (
        "以下の文字起こし内容を要約してください。\n\n"
        f"【文字起こし】\n{transcript}\n\n"
        "【要約の形式】\n"
        "・重要なポイントを3〜5つの箇条書きでまとめてください。\n"
        "・各ポイントは簡潔に1〜2文で記述してください。\n"
        "・要約のみを出力してください（説明文は不要です）。"
    )

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            response = client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if "429" in str(e) and attempt < RETRY_COUNT:
                print(f"[transcriber] 429 レート制限 - {RETRY_WAIT}秒後にリトライ ({attempt}/{RETRY_COUNT})")
                time.sleep(RETRY_WAIT)
            else:
                raise


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
