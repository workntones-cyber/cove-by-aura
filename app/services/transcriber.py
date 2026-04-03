"""
transcriber.py
文字起こし & AI要約サービス

AIモードに応じて以下を切り替える：
  - ollama  : faster-whisper（文字起こし）+ Ollama（要約）完全ローカル
  - groq    : Groq Whisper API（文字起こし）+ Groq LLaMA（要約）
  - openai  : Groq Whisper API（文字起こし）+ OpenAI GPT-4o（要約）
  - gemini  : Groq Whisper API（文字起こし）+ Google Gemini（要約）
  - claude  : Groq Whisper API（文字起こし）+ Anthropic Claude（要約）
"""

import sys
import time
from pathlib import Path

# ── 設定 ──────────────────────────────────────────
import sys as _sys
if getattr(_sys, "frozen", False):
    UPLOADS_DIR = Path(_sys.executable).resolve().parent / "uploads"
    ENV_PATH    = Path(_sys.executable).resolve().parent / ".env"
else:
    UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
    ENV_PATH    = Path(__file__).resolve().parent.parent.parent / ".env"

WHISPER_MODEL      = "whisper-large-v3-turbo"   # Groq Whisper文字起こし用
SUMMARY_MODEL      = "llama-3.3-70b-versatile"  # Groq要約用
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
def transcribe_and_summarize(wav_filename: str, extra_prompt: str = "", record_id: int = None, abort_event=None, progress_callback=None) -> dict:
    """
    WAVファイルを文字起こし & AI要約する。
    progress_callback(step, message, progress): 進捗通知コールバック
    """
    env     = _read_env()
    ai_mode = env.get("AI_MODE", "ollama")

    if ai_mode == "ollama":
        # 旧business互換も含む完全ローカル処理
        return _transcribe_faster_whisper(wav_filename, extra_prompt, record_id, abort_event=abort_event, progress_callback=progress_callback)
    else:
        # クラウドAPIモード：文字起こしはGroq Whisper共通
        return _transcribe_groq_whisper_cloud(wav_filename, extra_prompt, env, record_id=record_id, abort_event=abort_event, progress_callback=progress_callback)


# ── Groq Whisper文字起こし + クラウドLLM要約 ──────
def _transcribe_groq_whisper_cloud(wav_filename: str, extra_prompt: str, env: dict, record_id: int = None, abort_event=None, progress_callback=None) -> dict:
    """
    文字起こし：Groq Whisper API（クラウドAPIモード共通）
    要約      ：選択されたクラウドLLM（groq / openai / gemini / claude）
    """
    def _cb(step, message, progress, transcript=None, cleaned_transcript=None):
        if progress_callback:
            progress_callback(step, message, progress, transcript=transcript, cleaned_transcript=cleaned_transcript)

    ai_mode = env.get("AI_MODE", "groq")
    groq_key = env.get("GROQ_API_KEY", "").strip()

    if not groq_key:
        return {
            "status":  "error",
            "message": "Groq APIキーが設定されていません。設定画面で入力してください。",
        }

    wav_path = UPLOADS_DIR / wav_filename
    if not wav_path.exists():
        return {"status": "error", "message": f"音声ファイルが見つかりません: {wav_filename}"}

    try:
        from groq import Groq
        client = Groq(api_key=groq_key)

        # ── ① 文字起こし（Groq Whisper）──────────
        _cb("transcribe", "🎙️ 文字起こし中…", 10)
        print(f"[transcriber] Groq Whisper 文字起こし開始: {wav_filename}")
        raw_transcript = _call_whisper(client, wav_path)
        print(f"[transcriber] Groq Whisper 文字起こし完了: {len(raw_transcript)}文字")
        _cb("transcribe_done", f"🎙️ 文字起こし完了（{len(raw_transcript)}文字）", 35)

        if not raw_transcript:
            return {"status": "error", "message": "文字起こし結果が空でした（無音または認識できませんでした）"}

        if abort_event and abort_event.is_set():
            return {"status": "error", "message": "処理が中断されました"}

        # ── ② クリーニング（選択LLM）──────────────
        _cb("cleaning", "🧹 クリーニング中…", 40)
        cleaned = _clean_transcript_cloud(client, raw_transcript, ai_mode, env)
        _cb("cleaning_done", "🧹 クリーニング完了", 60)

        if abort_event and abort_event.is_set():
            return {"status": "error", "message": "処理が中断されました"}

        if record_id:
            try:
                from app.database import update_cleaned_transcript
                update_cleaned_transcript(record_id, cleaned)
            except Exception as e:
                print(f"[transcriber] クリーニング保存エラー: {e}")

        # ── ③ 要約（選択LLM）─────────────────────
        _cb("summarizing", "✨ 要約中…", 65)
        ai_summary = _summarize_cloud(cleaned, extra_prompt, ai_mode, env)
        _cb("done", "✅ 完了！", 100)

        return {
            "status":             "done",
            "transcript":         raw_transcript,
            "cleaned_transcript": cleaned,
            "ai_summary":         ai_summary,
        }

    except Exception as e:
        print(f"[transcriber] クラウド処理エラー: {e}")
        from app.services.llm import get_provider as _gp
        _prov   = _gp(ai_mode)
        _pname  = getattr(_prov, "DISPLAY_NAME", ai_mode) if _prov else ai_mode
        err_str = str(e)
        if "unexpected keyword argument" in err_str or "got an unexpected" in err_str:
            err_msg = "内部処理エラーが発生しました。アプリを再起動してください。"
        else:
            err_msg = _parse_api_error(e, _pname)
        return {"status": "error", "message": err_msg}


def _clean_transcript_cloud(groq_client, raw_transcript: str, ai_mode: str, env: dict) -> str:
    """機械的クリーニング：LLMを使わずフィラー除去＋改行挿入"""
    try:
        result = _mechanical_clean(raw_transcript)
        print(f"[transcriber] クリーニング完了: {len(raw_transcript)}字 → {len(result)}字")
        return result
    except Exception as e:
        print(f"[transcriber] クリーニングエラー（元テキストを使用）: {e}")
        raise


def _summarize_cloud(transcript: str, extra_prompt: str, ai_mode: str, env: dict) -> str:
    """クラウドLLMで要約する"""
    final_prompt = (
"以下のテキストの内容を整理して箇条書きでまとめてください。\n\n"
        "## 概要\n"
        "（何についての話し合いか・目的を1〜2文で）\n\n"
        "## 主なポイント\n"
        "・何が → どうなったか、という形式で記載してください\n"
        "・数字・金額・固有名詞・日付・具体的な内容は省略しないでください\n\n"
        "## 決定事項\n"
        "（決まったこと。なければ省略）\n\n"
        "## 次のアクション\n"
        "（誰が何をするか。なければ省略）\n\n"
        "テキストに書かれている内容のみ記載してください。\n\n"
        + (f"【追加指示】\n{extra_prompt}\n\n" if extra_prompt else "")
        + f"【テキスト】\n{transcript}"
    )
    messages = [{"role": "user", "content": final_prompt}]
    try:
        return _call_cloud_llm(messages, ai_mode, env, options={"temperature": 0.3, "max_tokens": 2048})
    except Exception as e:
        print(f"[transcriber] 要約エラー: {e}")
        from app.services.llm import get_provider
        provider = get_provider(ai_mode)
        pname = getattr(provider, "DISPLAY_NAME", ai_mode) if provider else ai_mode
        return f"（{_parse_api_error(e, pname)}）"


def _call_cloud_llm(messages: list, ai_mode: str, env: dict, options: dict = None) -> str:
    """
    選択されたクラウドLLMを呼び出す（非ストリーミング）。
    Ollamaモードでは呼ばれない。
    """
    from app.services.llm import get_provider
    provider = get_provider(ai_mode)
    if provider is None:
        raise ValueError(f"不明なAIモード: {ai_mode}")

    api_key_name = getattr(provider, "API_KEY_NAME", "")
    api_key      = env.get(api_key_name, "").strip() if api_key_name else ""

    if provider.REQUIRES_API_KEY and not api_key:
        raise ValueError(f"{provider.DISPLAY_NAME} のAPIキーが設定されていません")

    if provider.REQUIRES_API_KEY:
        return provider.chat(messages, api_key=api_key, options=options)
    else:
        return provider.chat(messages, options=options)


# ── Groq Whisper 文字起こし（チャンク対応・リトライ付き） ──
def _call_whisper(client, wav_path: Path) -> str:
    """
    WAVファイルを25MB以下のチャンクに分割してWhisperに送信し、
    結果を結合して返す。
    """
    MAX_BYTES = 24 * 1024 * 1024

    file_size = wav_path.stat().st_size
    print(f"[transcriber] ファイルサイズ: {file_size / 1024 / 1024:.1f}MB")

    if file_size <= MAX_BYTES:
        return _send_to_whisper(client, wav_path)

    print(f"[transcriber] ファイルが大きいため分割して送信します")
    chunks      = _split_wav(wav_path, MAX_BYTES)
    transcripts = []

    for i, chunk_path in enumerate(chunks):
        print(f"[transcriber] チャンク {i+1}/{len(chunks)} を送信中...")
        text = _send_to_whisper(client, chunk_path)
        transcripts.append(text)
        chunk_path.unlink()

    return " ".join(transcripts)


def _send_to_whisper(client, wav_path: Path) -> str:
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


def _split_wav(wav_path: Path, max_bytes: int) -> list:
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


# ── Groq LLaMA 要約（旧groqモード用・後方互換） ──────
# ── faster-whisper（Ollamaモード） ───────────────────

_whisper_model      = None
_whisper_model_name = None
FASTER_WHISPER_MODEL = "large-v3-turbo"
_model_status = "idle"
_model_error  = ""


def get_model_status() -> dict:
    """モデルのダウンロード・ロード状態を返す"""
    return {
        "status": _model_status,
        "error":  _model_error,
        "model":  FASTER_WHISPER_MODEL,
    }


def preload_model():
    """
    バックグラウンドスレッドでモデルをプリロードする。
    設定画面でOllamaモードを選択した時点で呼び出す。
    """
    import threading
    t = threading.Thread(target=_preload_model_thread, daemon=True)
    t.start()


def _preload_model_thread():
    global _model_status, _model_error
    if _model_status in ("loading", "ready"):
        return
    try:
        _model_status = "loading"
        print("[transcriber] バックグラウンドでモデルをプリロード中...")
        _get_whisper_model()
        _model_status = "ready"
        print("[transcriber] モデルプリロード完了")
    except Exception as e:
        _model_status = "error"
        _model_error  = str(e)
        print(f"[transcriber] モデルプリロードエラー: {e}")


def _get_whisper_model():
    """
    faster-whisperモデルをロードして返す（キャッシュ済みなら再利用）。
    初回はGPU/CPUを自動検出してダウンロードする。
    """
    global _whisper_model, _whisper_model_name

    if _whisper_model is not None and _whisper_model_name == FASTER_WHISPER_MODEL:
        return _whisper_model

    from faster_whisper import WhisperModel

    try:
        import torch
        if torch.cuda.is_available():
            device  = "cuda"
            compute = "float16"
            print(f"[transcriber] GPU検出: {torch.cuda.get_device_name(0)}")
        else:
            device  = "cpu"
            compute = "int8"
            print("[transcriber] GPUなし: CPUで実行します（処理に時間がかかる場合があります）")
    except ImportError:
        device  = "cpu"
        compute = "int8"
        print("[transcriber] torch未インストール: CPUで実行します")

    import os
    cache_dir    = Path.home() / ".cache" / "huggingface" / "hub"
    model_cached = any(
        FASTER_WHISPER_MODEL.replace(".", "-") in str(p)
        for p in cache_dir.glob("**/config.json")
    ) if cache_dir.exists() else False

    if not model_cached:
        print("[transcriber] 初回のみ：モデルのダウンロードが発生します（約1.5GB）")

    print(f"[transcriber] Whisperモデルをロード中: {FASTER_WHISPER_MODEL} ({device})")
    _whisper_model      = WhisperModel(FASTER_WHISPER_MODEL, device=device, compute_type=compute)
    _whisper_model_name = FASTER_WHISPER_MODEL
    print(f"[transcriber] Whisperモデルのロード完了")
    return _whisper_model


def _get_ollama_model() -> str:
    """使用するOllamaモデルを.envから取得（未設定時はgemma3:27b）"""
    return _read_env().get("OLLAMA_MODEL", "gemma3:27b")


def _get_cleaning_model() -> str:
    """クリーニング・要約用モデルを.envから取得（未設定時はOLLAMA_MODELを使用）"""
    env = _read_env()
    return env.get("CLEANING_MODEL", env.get("OLLAMA_MODEL", "gemma3:27b"))



# ── フィラー・単独挨拶の辞書（機械的除去用） ────────────
_STANDALONE_REMOVE = [
    "はい", "ええ", "うん", "そうですね", "なるほど", "なるほどね",
    "あー", "あ", "えー", "うーん", "まあ", "えーと", "えっと", "あの",
    "すみません", "すみません。", "すみませんでした", "失礼しました",
    "ありがとうございます", "ありがとうございました",
    "よろしくお願いします", "よろしくお願いいたします",
    "お世話になります", "お世話になっております",
    "以上です", "では以上です", "失礼いたします",
]

def _mechanical_clean(text: str) -> str:
    """
    LLMを使わず機械的にテキストを整形する。
    1. 単独フィラー・挨拶を除去（文として単独の場合のみ）
    2. 連続する同一文を集約（最大2回まで）
    3. 句読点の後に改行を挿入
    """
    import re

    # 句読点で文を分割
    sentences = re.split(r'(?<=[。．！？.!?])', text)
    result = []
    prev = ""
    rep_count = 0
    for s in sentences:
        stripped = s.strip()
        if not stripped:
            continue
        # 句読点を除いた本体が辞書の単語と完全一致する場合のみ除去
        body = re.sub(r'[。．！？.!?、,]+$', '', stripped).strip()
        if body in _STANDALONE_REMOVE:
            continue
        # 同一文の連続重複を最大2回までに制限
        if stripped == prev:
            rep_count += 1
            if rep_count >= 2:
                continue
        else:
            rep_count = 0
        prev = stripped
        result.append(stripped)

    return '\n'.join(result)



def _parse_api_error(e: Exception, provider_name: str = "") -> str:
    """APIエラーを利用者向けのメッセージに変換する"""
    msg = str(e)
    prefix = f"{provider_name} の" if provider_name else ""
    if "429" in msg or "rate_limit" in msg.lower() or "Rate limit" in msg:
        return f"{prefix}利用制限に達しました。しばらく待ってから再試行してください。"
    if "401" in msg or "invalid_api_key" in msg.lower() or "authentication" in msg.lower():
        return f"{prefix}APIキーが無効です。設定画面で確認してください。"
    if "api_key" in msg.lower() and ("not set" in msg.lower() or "設定されていません" in msg):
        return f"{prefix}APIキーが設定されていません。設定画面で入力してください。"
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return "タイムアウトしました。再試行してください。"
    if "connection" in msg.lower() or "network" in msg.lower() or "ConnectionError" in msg:
        return "サーバーに接続できません。インターネット接続を確認してください。"
    if "ollama" in msg.lower() or "11434" in msg or "Connection refused" in msg:
        return "Ollamaが起動していません。起動後に再試行してください。"
    return f"エラーが発生しました: {msg[:100]}"

def _get_summary_num_ctx() -> int:
    """MAX_RECORDING_MINUTESからnum_ctxを動的決定する"""
    minutes = int(_read_env().get("MAX_RECORDING_MINUTES", "60"))
    ctx_table = {
        30:  16384,
        60:  32768,
        90:  65536,
        120: 131072,
    }
    # 30分単位で切り捨て、対応するnum_ctxを返す
    rounded = max(30, (minutes // 30) * 30)
    return ctx_table.get(rounded, 32768)


def _chunk_text(text: str, max_chars: int = 2000) -> list:
    """テキストを行単位で分割する"""
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) > max_chars and current:
            chunks.append(current.strip())
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _clean_transcript_ollama(raw_transcript: str, abort_event=None, progress_cb=None) -> str:
    """機械的クリーニング：LLMを使わずフィラー除去＋改行挿入"""
    if abort_event and abort_event.is_set():
        return raw_transcript
    try:
        result = _mechanical_clean(raw_transcript)
        print(f"[transcriber] クリーニング完了: {len(raw_transcript)}字 → {len(result)}字")
        return result
    except Exception as e:
        print(f"[transcriber] クリーニングエラー（元テキストを使用）: {e}")
        raise  # 呼び出し元でエラーカラムに保存させる


def _summarize_ollama(transcript: str, extra_prompt: str = "", abort_event=None, progress_cb=None) -> str:
    """長文対応：チャンクごとに要約してから統合要約（Ollamaモード専用）"""
    import urllib.request, json

    if abort_event and abort_event.is_set():
        return ""

    chunks = _chunk_text(transcript, max_chars=3000)

    if len(chunks) == 1:
        partial_summaries = [transcript]
    else:
        partial_summaries = []
        for i, chunk in enumerate(chunks):
            if abort_event and abort_event.is_set():
                return ""
            if progress_cb:
                progress_cb(i + 1, len(chunks), final=False)
            print(f"[transcriber] 部分要約 {i+1}/{len(chunks)} チャンク...")
            prompt = (
                "以下のテキストに含まれる情報を箇条書きでまとめてください。\n"
                "数字・固有名詞・日付・金額・具体的な内容は省略しないでください。\n\n"
                f"【テキスト】\n{chunk}"
            )
            payload = json.dumps({
                "model": _get_cleaning_model(), "prompt": prompt, "stream": False,
                "options": {"num_ctx": 8192, "num_predict": 2048, "temperature": 0.1, "repeat_penalty": 1.3, "top_p": 0.3},
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate", data=payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=None) as conn:
                    data = json.loads(conn.read().decode("utf-8"))
                    partial_summaries.append(data.get("response", "").strip() or chunk[:500])
            except Exception as e:
                print(f"[transcriber] 部分要約エラー: {e}")
                partial_summaries.append(chunk[:500])

    if progress_cb:
        progress_cb(0, 0, final=True)
    print("[transcriber] 統合要約開始...")
    combined    = "\n\n".join(partial_summaries)
    final_prompt = (
"以下のテキストの内容を整理して箇条書きでまとめてください。\n\n"
        "## 概要\n"
        "（何についての話し合いか・目的を1〜2文で）\n\n"
        "## 主なポイント\n"
        "・何が → どうなったか、という形式で記載してください\n"
        "・数字・金額・固有名詞・日付・具体的な内容は省略しないでください\n\n"
        "## 決定事項\n"
        "（決まったこと。なければ省略）\n\n"
        "## 次のアクション\n"
        "（誰が何をするか。なければ省略）\n\n"
        "テキストに書かれている内容のみ記載してください。\n\n"
        + (f"【追加指示】\n{extra_prompt}\n\n" if extra_prompt else "")
        + f"【テキスト】\n{combined}"
    )
    payload = json.dumps({
        "model": _get_cleaning_model(), "prompt": final_prompt, "stream": False,
        "options": {"num_ctx": _get_summary_num_ctx(), "temperature": 0.1, "repeat_penalty": 1.3, "top_p": 0.3},
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=None) as conn:
        data   = json.loads(conn.read().decode("utf-8"))
        result = data.get("response", "").strip()
    print(f"[transcriber] 要約完了: {len(result)}字")
    return result


def _transcribe_faster_whisper(wav_filename: str, extra_prompt: str = "", record_id: int = None, abort_event=None, progress_callback=None) -> dict:
    """faster-whisper + Ollama によるローカル処理（Ollamaモード専用）"""

    def _cb(step, message, progress, transcript=None, cleaned_transcript=None):
        if progress_callback:
            progress_callback(step, message, progress, transcript=transcript, cleaned_transcript=cleaned_transcript)

    wav_path = UPLOADS_DIR / wav_filename
    if not wav_path.exists():
        return {"status": "error", "message": f"音声ファイルが見つかりません: {wav_filename}"}

    try:
        model = _get_whisper_model()

        # ── ① 音声ノーマライズ（小声・音量ムラ対策） ──
        import subprocess as _sp, tempfile as _tmp, os as _os
        normalized_path = None
        try:
            tmp = _tmp.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close()
            normalized_path = tmp.name
            _sp.run([
                "ffmpeg", "-y", "-i", str(wav_path),
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                normalized_path
            ], capture_output=True, timeout=300)
            print(f"[transcriber] 音声ノーマライズ完了: {normalized_path}")
            transcribe_path = normalized_path
        except Exception as e:
            print(f"[transcriber] ノーマライズ失敗（元ファイルで継続）: {e}")
            transcribe_path = str(wav_path)

        # ── ② 文字起こし ──────────────────────────
        print(f"[transcriber] faster-whisper 文字起こし開始: {wav_filename}")
        initial_prompt = (
            "これは会議・打ち合わせの録音です。"
            "複数の参加者による質疑応答、意見交換、議論が含まれています。"
            "専門用語・固有名詞・数字を正確に文字起こしてください。"
            "よく使われる表現：お世話になります、よろしくお願いします、"
            "ありがとうございます、失礼いたします。"
        )
        _cb("transcribe", "🎙️ 文字起こし中…", 10)
        segments, info = model.transcribe(
            transcribe_path,
            language="ja",
            beam_size=5,
            initial_prompt=initial_prompt,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 500,
                "speech_pad_ms": 400,
            },
            word_timestamps=True,
            condition_on_previous_text=True,
            no_speech_threshold=0.5,
            compression_ratio_threshold=1.8,
            temperature=0,
        )
        # 繰り返しセグメントを除外してから結合
        import re as _re
        filtered_segments = []
        prev_seg = ""
        rep_seg_count = 0
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            # 同一文字・単語の異常な繰り返しを検出
            if _re.search(r'(.{1,6})(\1){2,}', text):
                print(f"[transcriber] 繰り返しセグメントをスキップ: {text[:50]}")
                continue
            # 同一セグメントが連続する場合は最大2回まで
            if text == prev_seg:
                rep_seg_count += 1
                if rep_seg_count >= 2:
                    print(f"[transcriber] 連続重複セグメントをスキップ: {text[:50]}")
                    continue
            else:
                rep_seg_count = 0
            prev_seg = text
            filtered_segments.append(text)
        transcript = " ".join(filtered_segments).strip()
        print(f"[transcriber] faster-whisper 文字起こし完了: {len(transcript)}文字 ({info.duration:.1f}秒)")
        # 一時ファイル削除
        if normalized_path and _os.path.exists(normalized_path):
            try: _os.unlink(normalized_path)
            except: pass
        _cb("transcribe_done", f"🎙️ 文字起こし完了（{len(transcript)}文字）", 35, transcript=transcript)

        if not transcript:
            return {"status": "error", "message": "文字起こし結果が空でした（無音または認識できませんでした）"}

        if abort_event and abort_event.is_set():
            return {"status": "error", "message": "処理が中断されました"}

        # 生テキストを保持（返却用）
        raw_transcript = transcript

        # ── ② クリーニング（Ollama）────────────────
        chunks_count = max(1, len(transcript) // 3000 + 1)
        _cb("cleaning", f"🧹 クリーニング中…（約{chunks_count}ブロック）", 40)
        print("[transcriber] Ollama で不要文字列除去開始")

        def clean_progress(i, total):
            pct = 40 + int(20 * i / total)
            _cb("cleaning", f"🧹 クリーニング中… {i}/{total} ブロック", pct)

        cleaned = _clean_transcript_ollama(transcript, abort_event=abort_event, progress_cb=clean_progress)
        if abort_event and abort_event.is_set():
            return {"status": "error", "message": "処理が中断されました"}
        _cb("cleaning_done", "🧹 クリーニング完了", 60, cleaned_transcript=cleaned)

        if record_id:
            try:
                from app.database import update_cleaned_transcript
                update_cleaned_transcript(record_id, cleaned)
                # 文字起こし生テキストもこのタイミングでDBに保存
                from app.database import update_transcript_and_summary
                update_transcript_and_summary(record_id, raw_transcript, '')
            except Exception as e:
                print(f"[transcriber] クリーニング保存エラー: {e}")

        # ── ③ 要約（Ollama）──────────────────────
        sum_chunks = max(1, len(cleaned) // 3000 + 1)
        _cb("summarizing", f"✨ 要約中…（約{sum_chunks}ブロック）", 65)
        print("[transcriber] Ollama で要約開始（完全ローカル処理）")

        def sum_progress(i, total, final=False):
            if final:
                _cb("summarizing", "✨ 統合要約中…", 90)
            else:
                pct = 65 + int(20 * i / total)
                _cb("summarizing", f"✨ 要約中… {i}/{total} ブロック", pct)

        try:
            ai_summary = _summarize_ollama(cleaned, extra_prompt, abort_event=abort_event, progress_cb=sum_progress)
            if abort_event and abort_event.is_set():
                return {"status": "error", "message": "処理が中断されました"}
            _cb("done", "✅ 完了！", 100)
            print(f"[transcriber] Ollama 要約完了: {len(ai_summary)}文字")
        except Exception as e:
            print(f"[transcriber] Ollama 要約エラー: {e}")
            err_msg = _parse_api_error(e, "Ollama")
            ai_summary = f"（{err_msg}）"
            _cb("error", f"⚠️ {err_msg}", 0)

        return {
            "status":             "done",
            "transcript":         raw_transcript,
            "cleaned_transcript": cleaned,
            "ai_summary":         ai_summary,
        }

    except ImportError:
        return {
            "status":  "error",
            "message": "faster-whisperがインストールされていません。`uv add faster-whisper` を実行してください。",
        }
    except Exception as e:
        print(f"[transcriber] faster-whisper エラー: {e}")
        return {"status": "error", "message": _parse_api_error(e, "faster-whisper")}
