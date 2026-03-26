"""
transcriber.py
文字起こし & AI要約サービス

AIモードに応じて以下を切り替える：
  - personal  : Groq API（Whisper文字起こし + LLaMA要約）
  - business  : faster-whisper（文字起こし）+ Ollama（要約）完全ローカル
"""

import sys
import time
from pathlib import Path

from groq import Groq

# ── 設定 ──────────────────────────────────────────
import sys as _sys
if getattr(_sys, "frozen", False):
    UPLOADS_DIR = Path(_sys.executable).resolve().parent / "uploads"
    ENV_PATH    = Path(_sys.executable).resolve().parent / ".env"
else:
    UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
    ENV_PATH    = Path(__file__).resolve().parent.parent.parent / ".env"
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
def transcribe_and_summarize(wav_filename: str, extra_prompt: str = "", record_id: int = None, abort_event=None, progress_callback=None) -> dict:
    """
    WAVファイルを文字起こし & AI要約する。
    progress_callback(step, message, progress): 進捗通知コールバック
    """
    env     = _read_env()
    ai_mode = env.get("AI_MODE", "personal")

    if ai_mode == "business":
        return _transcribe_faster_whisper(wav_filename, extra_prompt, record_id, abort_event=abort_event, progress_callback=progress_callback)
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
        raw_transcript = _call_whisper(client, wav_path)
        print(f"[transcriber] 文字起こし完了: {len(raw_transcript)}文字")

        # ── ② 不要文字列除去（Groq LLaMA） ─────────
        print(f"[transcriber] 不要文字列除去開始")
        transcript = _clean_transcript_groq(client, raw_transcript)

        # ── ③ 要約（Groq LLaMA） ─────────────────
        print(f"[transcriber] 要約開始")
        ai_summary = _call_llama(client, transcript)
        print(f"[transcriber] 要約完了: {len(ai_summary)}文字")

        return {
            "status":             "done",
            "transcript":         raw_transcript,
            "cleaned_transcript": transcript,
            "ai_summary":         ai_summary,
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


def _call_llama_prompt(client, prompt: str) -> str:
    """Groq LLaMAにプロンプトを直接渡して結果を返す"""
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            res = client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8192,
            )
            return res.choices[0].message.content.strip()
        except Exception as e:
            if "429" in str(e) and attempt < RETRY_COUNT:
                print(f"[transcriber] 429 レート制限 - {RETRY_WAIT}秒後にリトライ ({attempt}/{RETRY_COUNT})")
                time.sleep(RETRY_WAIT)
            else:
                raise
    return ""

def _clean_transcript_groq(client, raw_transcript: str) -> str:
    """
    Groq LLaMAを使って文字起こしから不要文字列を除去する（個人用モード）。
    """
    prompt = (
        "以下は会議の音声を文字起こしした生テキストです。\n"
        "以下の種類の文字列を除去して、会議の本質的な内容だけを残してください。\n\n"
        "【除去する文字列の種類】\n"
        "・挨拶（お世話になります、よろしくお願いします、ありがとうございます等）\n"
        "・相槌・短い返答（はい、そうですね、なるほど、とんでもないです等）\n"
        "・フィラー（あー、えーと、うーん、まあ等）\n"
        "・謝罪の定型文（すみません、失礼します等）単独のもの\n"
        "・会議の開始・終了の定型文（では始めます、以上です等）\n\n"
        "【残す文字列】\n"
        "・議題・提案・質問・回答・意見・決定事項\n"
        "・具体的な数字・固有名詞・日付を含む発言\n"
        "・状況説明・背景説明\n\n"
        "除去後のテキストのみ出力してください（説明文・前置きは不要）。\n\n"
        f"【文字起こし】\n{raw_transcript}"
    )
    try:
        cleaned = _call_llama_prompt(client, prompt)
        print(f"[transcriber] Groq クリーニング完了: {len(raw_transcript)}文字 → {len(cleaned)}文字")
        return cleaned if cleaned else raw_transcript
    except Exception as e:
        print(f"[transcriber] Groq クリーニングエラー（元テキストを使用）: {e}")
        return raw_transcript

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

# モデルキャッシュ（再利用してメモリ節約）
_whisper_model      = None
_whisper_model_name = None

FASTER_WHISPER_MODEL = "medium"

# モデルダウンロード状態管理
_model_status = "idle"   # idle / downloading / ready / error
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
    設定画面でビジネス用モードを選択した時点で呼び出す。
    """
    import threading
    t = threading.Thread(target=_preload_model_thread, daemon=True)
    t.start()

def _preload_model_thread():
    global _model_status, _model_error
    if _model_status in ("loading", "ready"):
        return  # すでに進行中またはロード済み
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

    # GPU(CUDA)が使えるか確認
    try:
        import torch
        if torch.cuda.is_available():
            device    = "cuda"
            compute   = "float16"
            print(f"[transcriber] GPU検出: {torch.cuda.get_device_name(0)}")
        else:
            device    = "cpu"
            compute   = "int8"
            print("[transcriber] GPUなし: CPUで実行します（処理に時間がかかる場合があります）")
    except ImportError:
        device    = "cpu"
        compute   = "int8"
        print("[transcriber] torch未インストール: CPUで実行します")

    # キャッシュの有無を確認してメッセージを出し分け
    import os
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    model_cached = any(
        FASTER_WHISPER_MODEL.replace(".", "-") in str(p)
        for p in cache_dir.glob("**/config.json")
    ) if cache_dir.exists() else False

    if model_cached:
        print(f"[transcriber] Whisperモデルをロード中: {FASTER_WHISPER_MODEL} ({device})")
    else:
        print(f"[transcriber] Whisperモデルをロード中: {FASTER_WHISPER_MODEL} ({device})")
        print("[transcriber] 初回のみ：モデルのダウンロードが発生します（約1.5GB）")

    _whisper_model      = WhisperModel(FASTER_WHISPER_MODEL, device=device, compute_type=compute)
    _whisper_model_name = FASTER_WHISPER_MODEL

    print(f"[transcriber] Whisperモデルのロード完了")
    return _whisper_model



def _get_ollama_model() -> str:
    """使用するOllamaモデルを.envから取得（未設定時はllama3.1:8b）"""
    return _read_env().get("OLLAMA_MODEL", "llama3.1:8b")



def _chunk_text(text: str, max_chars: int = 3000) -> list:
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
    """長文対応：チャンク分割してクリーニング"""
    import urllib.request, json

    if abort_event and abort_event.is_set():
        return raw_transcript

    chunks = _chunk_text(raw_transcript, max_chars=3000)
    cleaned_parts = []

    for i, chunk in enumerate(chunks):
        if abort_event and abort_event.is_set():
            print("[transcriber] クリーニング中断")
            return raw_transcript
        if progress_cb:
            progress_cb(i + 1, len(chunks))
        print(f"[transcriber] クリーニング {i+1}/{len(chunks)} チャンク...")
        prompt = (
            "以下は会議の音声を文字起こしした生テキストです。\n"
            "挨拶・相槌・フィラー（あー、えーと等）・謝罪の定型文・会議開始終了の定型文を除去し、"
            "議題・提案・質問・回答・意見・決定事項・数字・固有名詞を含む発言のみ残してください。\n"
            "除去後のテキストのみ出力してください。\n\n"
            f"【文字起こし】\n{chunk}"
        )
        payload = json.dumps({
            "model": _get_ollama_model(), "prompt": prompt, "stream": False,
            "options": {"num_ctx": 4096},
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate", data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=None) as conn:
                data    = json.loads(conn.read().decode("utf-8"))
                cleaned = data.get("response", "").strip()
                cleaned_parts.append(cleaned if cleaned else chunk)
        except Exception as e:
            print(f"[transcriber] クリーニングエラー（チャンク{i+1}）: {e}")
            cleaned_parts.append(chunk)

    result = "\n".join(cleaned_parts)
    print(f"[transcriber] クリーニング完了: {len(raw_transcript)}字 → {len(result)}字")
    return result

def _summarize_ollama(transcript: str, extra_prompt: str = "", abort_event=None, progress_cb=None) -> str:
    """長文対応：チャンクごとに要約してから統合要約"""
    import urllib.request, json

    if abort_event and abort_event.is_set():
        return ""

    chunks = _chunk_text(transcript, max_chars=3000)

    # チャンクが1つなら直接要約
    if len(chunks) == 1:
        partial_summaries = [transcript]
    else:
        # 各チャンクを部分要約
        partial_summaries = []
        for i, chunk in enumerate(chunks):
            if abort_event and abort_event.is_set():
                return ""
            if progress_cb:
                progress_cb(i + 1, len(chunks), final=False)
            print(f"[transcriber] 部分要約 {i+1}/{len(chunks)} チャンク...")
            prompt = (
                "以下は会議の一部分を文字起こしたテキストです。\n"
                "この部分に含まれる議題・意見・決定事項・アクションアイテムを簡潔にまとめてください。\n"
                "箇条書き可・300字以内。\n\n"
                f"【テキスト】\n{chunk}"
            )
            payload = json.dumps({
                "model": _get_ollama_model(), "prompt": prompt, "stream": False,
                "options": {"num_ctx": 4096},
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

    # 統合要約
    if progress_cb:
        progress_cb(0, 0, final=True)
    print("[transcriber] 統合要約開始...")
    combined = "\n\n".join(partial_summaries)
    final_prompt = (
        "あなたは経験豊富な議事録作成の専門家です。\n"
        "以下は会議の内容をまとめたテキストです。\n\n"
        "【議事録の形式】\n"
        "## 会議の概要\n（目的・テーマ・雰囲気を簡潔に）\n\n"
        "## 議題と議論の内容\n（各議題について提起された問題・意見・結論の流れ）\n\n"
        "## 決定事項\n（合意・決定したことをすべて。なければ「特になし」）\n\n"
        "## アクションアイテム\n（誰が・何を・いつまでに。なければ「特になし」）\n\n"
        "## 未解決事項\n（継続検討事項。なければ「特になし」）\n\n"
        "数字・固有名詞・日付は正確に記載。議事録のみ出力してください。\n\n"
        + (f"【追加指示】\n{extra_prompt}\n\n" if extra_prompt else "")
        + f"【会議内容】\n{combined}"
    )
    payload = json.dumps({
        "model": _get_ollama_model(), "prompt": final_prompt, "stream": False,
        "options": {"num_ctx": 8192},
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=None) as conn:
        data = json.loads(conn.read().decode("utf-8"))
        result = data.get("response", "").strip()
    print(f"[transcriber] 要約完了: {len(result)}字")
    return result

def _transcribe_faster_whisper(wav_filename: str, extra_prompt: str = "", record_id: int = None, abort_event=None, progress_callback=None) -> dict:
    """faster-whisper + Ollama によるローカル処理"""

    def _cb(step, message, progress):
        if progress_callback:
            progress_callback(step, message, progress)

    wav_path = UPLOADS_DIR / wav_filename
    if not wav_path.exists():
        return {"status": "error", "message": f"音声ファイルが見つかりません: {wav_filename}"}

    try:
        model = _get_whisper_model()

        # ── ① 文字起こし ──────────────────────────
        print(f"[transcriber] faster-whisper 文字起こし開始: {wav_filename}")
        # 文字起こし精度向上のための事前情報プロンプト
        initial_prompt = (
            "これは会議・打ち合わせの録音です。"
            "複数の参加者による質疑応答、意見交換、議論が含まれています。"
            "専門用語・固有名詞・数字を正確に文字起こしてください。"
            "よく使われる表現：お世話になります、よろしくお願いします、"
            "ありがとうございます、失礼いたします。"
        )
        _cb("transcribe", "🎙️ 文字起こし中…", 10)
        segments, info = model.transcribe(
            str(wav_path),
            language="ja",
            beam_size=5,
            initial_prompt=initial_prompt,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        transcript = " ".join([seg.text.strip() for seg in segments]).strip()
        print(f"[transcriber] faster-whisper 文字起こし完了: {len(transcript)}文字 ({info.duration:.1f}秒)")
        _cb("transcribe_done", f"🎙️ 文字起こし完了（{len(transcript)}文字）", 35)

        if not transcript:
            return {"status": "error", "message": "文字起こし結果が空でした（無音または認識できませんでした）"}

        if abort_event and abort_event.is_set():
            return {"status": "error", "message": "処理が中断されました"}

        # ── ② 不要文字列除去（Ollama） ────────────
        chunks_count = max(1, len(transcript) // 3000 + 1)
        _cb("cleaning", f"🧹 クリーニング中…（約{chunks_count}ブロック）", 40)
        print("[transcriber] Ollama で不要文字列除去開始")

        def clean_progress(i, total):
            pct = 40 + int(20 * i / total)
            _cb("cleaning", f"🧹 クリーニング中… {i}/{total} ブロック", pct)

        cleaned = _clean_transcript_ollama(transcript, abort_event=abort_event, progress_cb=clean_progress)
        if abort_event and abort_event.is_set():
            return {"status": "error", "message": "処理が中断されました"}
        _cb("cleaning_done", "🧹 クリーニング完了", 60)

        if record_id:
            try:
                from app.database import update_cleaned_transcript
                update_cleaned_transcript(record_id, cleaned)
            except Exception as e:
                print(f"[transcriber] クリーニング保存エラー: {e}")
        transcript = cleaned

        # ── ③ 要約（Ollama ローカル） ─────────────
        sum_chunks = max(1, len(transcript) // 3000 + 1)
        _cb("summarizing", f"✨ 要約中…（約{sum_chunks}ブロック）", 65)
        print("[transcriber] Ollama で要約開始（完全ローカル処理）")

        def sum_progress(i, total, final=False):
            if final:
                _cb("summarizing", "✨ 統合要約中…", 90)
            else:
                pct = 65 + int(20 * i / total)
                _cb("summarizing", f"✨ 要約中… {i}/{total} ブロック", pct)

        try:
            ai_summary = _summarize_ollama(transcript, extra_prompt, abort_event=abort_event, progress_cb=sum_progress)
            if abort_event and abort_event.is_set():
                return {"status": "error", "message": "処理が中断されました"}
            _cb("done", "✅ 完了！", 100)
            print(f"[transcriber] Ollama 要約完了: {len(ai_summary)}文字")
        except Exception as e:
            print(f"[transcriber] Ollama 要約エラー: {e}")
            ai_summary = "（要約に失敗しました。Ollamaが起動しているか確認してください）"
            _cb("error", f"⚠️ 要約エラー: {e}", 0)

        return {
            "status":     "done",
            "transcript": transcript,
            "ai_summary": ai_summary,
        }

    except ImportError:
        return {
            "status":  "error",
            "message": "faster-whisperがインストールされていません。`uv add faster-whisper` を実行してください。",
        }
    except Exception as e:
        print(f"[transcriber] faster-whisper エラー: {e}")
        return {"status": "error", "message": f"faster-whisperエラー: {str(e)}"}
